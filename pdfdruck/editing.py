# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Edit mode: change text rows (text, font, size) and edit layers.

Text (pdfium, directly in the open document):
  A page's text objects are grouped into rows (same font/size, same baseline, small gap).
  Text only: the first object keeps font, color, position and layer; the row's other objects are dropped.
  Font change: a new text object at the same place (pdfium cannot swap an object's font) –
  if the row lies in a layer, the new text is no longer part of that layer afterwards (reported).
Layers (pikepdf, bytes -> bytes): position/extent per page, hit test at a point, show/hide,
  remove, scale/move, replace content with a page from another PDF.
"""
from __future__ import annotations

import ctypes
import io
from dataclasses import dataclass, field

from . import preflight
from .l10n import tr

MM = 72.0 / 25.4
STANDARD_FONTS = ["Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Times-Roman", "Times-Bold", "Times-Italic",
                  "Courier", "Courier-Bold"]
_font_data_keep = []        # geladene Schriftdaten am Leben halten


# --------------------------------------------------------------------------- #
# Text
# --------------------------------------------------------------------------- #
@dataclass
class TextLine:
    index: int
    objs: list                   # Objektnummern in der Seite (Reihenfolge)
    text: str
    font: str
    size: float
    bbox: tuple                  # (x0, y0, x1, y1) pt
    in_layer: bool = False
    subset: bool = False
    tops: list = field(default_factory=list)   # laufende Nummern der Textobjekte (= Textbefehle im Inhalt)
    path_center: tuple | None = None           # Bogenzentrum bei Pfadtext (Kreistext), sonst None
    no_text: bool = False                      # pdfium kann den Text nicht dekodieren (z. B. Subset ohne Encoding)


def _obj_text(obj, tp) -> str:
    import pypdfium2.raw as r
    n = r.FPDFTextObj_GetText(obj, tp, None, 0)
    if n <= 2:
        return ""
    buf = ctypes.create_string_buffer(n)
    r.FPDFTextObj_GetText(obj, tp, ctypes.cast(buf, ctypes.POINTER(ctypes.c_ushort)), n)
    return buf.raw[:n - 2].decode("utf-16-le", "replace")


def _font_name(obj) -> str:
    import pypdfium2.raw as r
    f = r.FPDFTextObj_GetFont(obj)
    if not f:
        return "?"
    n = r.FPDFFont_GetBaseFontName(f, None, 0)
    buf = ctypes.create_string_buffer(max(1, n))
    r.FPDFFont_GetBaseFontName(f, ctypes.cast(buf, ctypes.c_char_p), n)
    return buf.value.decode("latin-1", "replace") or "?"


def _bounds(obj):
    import pypdfium2.raw as r
    l, b, rr, t = (ctypes.c_float() for _ in range(4))
    r.FPDFPageObj_GetBounds(obj, ctypes.byref(l), ctypes.byref(b), ctypes.byref(rr), ctypes.byref(t))
    return l.value, b.value, rr.value, t.value


def _size(obj) -> float:
    import pypdfium2.raw as r
    s = ctypes.c_float()
    r.FPDFTextObj_GetFontSize(obj, ctypes.byref(s))
    return float(s.value)


def _marked(obj) -> bool:
    import pypdfium2.raw as r
    for i in range(r.FPDFPageObj_CountMarks(obj)):
        m = r.FPDFPageObj_GetMark(obj, i)
        n = ctypes.c_ulong()
        buf = ctypes.create_string_buffer(64)
        r.FPDFPageObjMark_GetName(m, ctypes.cast(buf, ctypes.POINTER(ctypes.c_ushort)), 64, ctypes.byref(n))
        if buf.raw[:max(0, n.value - 2)].decode("utf-16-le", "ignore") == "OC":
            return True
    return False


@dataclass
class PageObject:
    """Nicht-Text-Objekt (Vektor/Bild) der Seite für die Objektliste (1.12)."""
    index: int
    objs: list                   # Objektnummern (Reihenfolge im Seiteninhalt)
    kind: str                    # "path" | "image"
    text: str                    # Anzeigename („Vektor", „Bild")
    bbox: tuple
    in_layer: bool = False


MAX_LISTED_OBJECTS = 3000


def limit_objects(objs: list, n: int = MAX_LISTED_OBJECTS) -> tuple[list, int]:
    """Sehr viele Objekte (CAD, Schraffuren): alle Bilder + die größten Vektoren, in Seitenreihenfolge, neu
        nummeriert (index = Zeile der Liste). -> (Auswahl, Gesamtzahl). Eine Liste mit 100.000 Einträgen
        legt sonst die Oberfläche lahm."""
    total = len(objs)
    if total <= n:
        return objs, total
    imgs = [o for o in objs if o.kind == "image"]
    paths = sorted((o for o in objs if o.kind != "image"),
                   key=lambda o: -(o.bbox[2] - o.bbox[0]) * (o.bbox[3] - o.bbox[1]))[:max(0, n - len(imgs))]
    keep = sorted(imgs + paths, key=lambda o: o.objs[0] if o.objs else 0)
    for i, o in enumerate(keep):
        o.index = i
    return keep, total


def page_objects(doc, page_index: int) -> list[PageObject]:
    """Vektor- und Bildobjekte der Seite (oberste Ebene) für die Objektliste."""
    import pypdfium2.raw as r
    page = doc[page_index]
    try:
        n = r.FPDFPage_CountObjects(page.raw)
        out = []
        for i in range(n):
            o = r.FPDFPage_GetObject(page.raw, i)
            t = r.FPDFPageObj_GetType(o)
            if t not in (r.FPDF_PAGEOBJ_PATH, r.FPDF_PAGEOBJ_IMAGE):
                continue
            b = _bounds(o)
            if b[2] - b[0] < 0.5 or b[3] - b[1] < 0.5:      # Nadelobjekte (Füll-Punkte) weglassen
                continue
            out.append(PageObject(len(out), [i], "path" if t == r.FPDF_PAGEOBJ_PATH else "image",
                                  tr("Vektor") if t == r.FPDF_PAGEOBJ_PATH else tr("Bild"),
                                  b, _marked(o)))
        return out
    finally:
        page.close()


def text_lines(doc, page_index: int, include_undecodable: bool = False) -> list[TextLine]:
    """Textobjekte der Seite (oberste Ebene) zu Zeilen gruppieren.
        include_undecodable=True: Zeilen, deren Text pdfium nicht dekodieren kann
        (z. B. eingebettete Subset-Schrift ohne Encoding), trotzdem listen (no_text=True) –
        Verschieben/Skalieren/Löschen funktioniert, Text ändern nicht.
    """
    import ctypes
    import math
    import pypdfium2.raw as r
    page = doc[page_index]
    tp = page.get_textpage()
    items = []
    rots: dict[int, tuple] = {}          # Objektnummer -> (Drehung in Grad, Ursprung x, y)
    scales: dict[int, float] = {}        # Objektnummer -> Skalierung der Objektmatrix (Tm × CTM)
    try:
        ordinal = -1
        for i in range(r.FPDFPage_CountObjects(page.raw)):
            o = r.FPDFPage_GetObject(page.raw, i)
            if r.FPDFPageObj_GetType(o) != r.FPDF_PAGEOBJ_TEXT:
                continue
            ordinal += 1
            t = _obj_text(o, tp.raw)
            if not t.strip():
                if include_undecodable and _size(o) > 0:
                    b = _bounds(o)
                    if b[2] > b[0] and b[3] > b[1]:
                        items.append((i, "", _font_name(o), _size(o), b, _marked(o), ordinal, True))
                continue
            items.append((i, t, _font_name(o), _size(o), _bounds(o), _marked(o), ordinal, False))
            m = r.FS_MATRIX()
            if r.FPDFPageObj_GetMatrix(o, ctypes.byref(m)):
                rots[i] = (math.degrees(math.atan2(m.b, m.a)), float(m.e), float(m.f))
                scales[i] = math.sqrt(abs(m.a * m.d - m.b * m.c))
    finally:
        tp.close()
        page.close()
    lines: list[TextLine] = []
    for i, t, font, size, (x0, y0, x1, y1), mk, ordn, notext in items:
        if lines:
            L = lines[-1]
            h = max(1.0, L.bbox[3] - L.bbox[1])
            # is the object inside the row band? (including small characters like "." or "-" that are not full height)
            same_line = (y0 >= L.bbox[1] - 0.35 * h and y1 <= L.bbox[3] + 0.35 * h
                         and min(y1, L.bbox[3]) - max(y0, L.bbox[1]) > -0.1 * h)
            near = -0.5 * h < x0 - L.bbox[2] < 2.5 * h
            if same_line and near and abs(size - L.size) < 0.01 and mk == L.in_layer:
                gap = " " if x0 - L.bbox[2] > 0.15 * h and not L.text.endswith(" ") and not t.startswith(" ") else ""
                L.objs.append(i)
                L.tops.append(ordn)
                L.text += gap + t
                L.bbox = (min(L.bbox[0], x0), min(L.bbox[1], y0), max(L.bbox[2], x1), max(L.bbox[3], y1))
                continue
        lines.append(TextLine(len(lines), [i], t, font, size, (x0, y0, x1, y1), mk, "+" in font[:8], [ordn],
                               no_text=notext))
    _merge_arc_lines(lines, rots)
    for L in lines:
        # kurze, eng stehende Bögen wurden oben schon als normale Zeile zusammengefasst –
        # trotzdem als Pfadtext erkennen, wenn die Buchstaben verschieden gedreht auf einem Kreis liegen
        if L.path_center is None and len(L.objs) >= 3 and all(i in rots for i in L.objs):
            L.path_center = _arc_center([rots[i][1:] for i in L.objs],
                                        [math.radians(rots[i][0]) for i in L.objs])
        if L.path_center is not None and L.objs[0] in scales and scales[L.objs[0]] > 1e-6:
            # wirksame Größe: Schriftgröße × Skalierung der Matrix (nach „Größe ändern“ steckt die
            # Vergrößerung im cm, nicht im Tf – sonst zeigt die Liste weiter die alte Größe und
            # jede weitere Änderung vergrößert erneut)
            L.size = L.size * scales[L.objs[0]]
    # row text from pdfium text analysis over the row area (real word gaps instead of guessed ones;
    # wichtig z. B. bei Chrome-PDFs, die jeden Buchstaben einzeln setzen)
    page = doc[page_index]
    tp = page.get_textpage()
    try:
        for k, L in enumerate(lines):
            L.index = k
            if L.path_center is not None:
                continue                 # Pfadtext: Objektreihenfolge ist korrekt; räumliches
                                          # Nachlesen verwürfelt den Bogen (Reading-Order ≠ Pfad-Order)
            if len(L.objs) > 1:
                x0, y0, x1, y1 = L.bbox
                h = y1 - y0
                t = tp.get_text_bounded(x0 - 0.5, y0 + 0.25 * h, x1 + 0.5, y1 - 0.25 * h)
                t = " ".join(t.split())
                if t and abs(len(t.replace(" ", "")) - len(L.text.replace(" ", ""))) <= max(2, len(L.text) // 10):
                    L.text = t
    finally:
        tp.close()
        page.close()
    return lines


def _merge_arc_lines(lines: list[TextLine], rots: dict) -> None:
    """Pfadtext (Kreistext): benachbarte Ein-Zeichen-„Zeilen“ mit fortlaufender Drehung und
        Ursprüngen auf einem gemeinsamen Kreis zu EINER Zeile verschmelzen (Affinity/Illustrator
        setzen jeden Buchstaben einzeln mit eigener Matrix). setzt path_center; Indices neu."""
    import math
    runs, k = [], 0
    while k < len(lines):
        L = lines[k]
        one = (len(L.objs) == 1 and len(L.text.strip()) <= 1 and not L.no_text
               and L.objs[0] in rots)      # Drehung prüft erst die Spreizung unten:
                                            # ein Buchstabe genau oben (Drehung 0°) darf den
                                            # Run nicht verhindern
        if not one:
            k += 1
            continue
        j = k
        while (j + 1 < len(lines)
               and len(lines[j + 1].objs) == 1 and len(lines[j + 1].text.strip()) <= 1
               and not lines[j + 1].no_text and lines[j + 1].objs[0] in rots
               and lines[j + 1].font == L.font and abs(lines[j + 1].size - L.size) < 0.01):
            j += 1
        if j - k >= 2:                                     # mindestens 3 Buchstaben
            c = _circle_fit([rots[lines[m].objs[0]][1:] for m in range(k, j + 1)])
            angs = [rots[lines[m].objs[0]][0] for m in range(k, j + 1)]
            if c is not None:
                a0 = angs[0]
                sp = [math.atan2(math.sin(math.radians(a - a0)), math.cos(math.radians(a - a0)))
                      for a in angs]
                if math.degrees(max(sp) - min(sp)) > 10.0:
                    runs.append((k, j, c[0], c[1]))
        k = j + 1
    for k, j, cx, cy in reversed(runs):                    # von hinten: Indices bleiben stabil
        grp = lines[k:j + 1]
        merged = TextLine(0, [i for g in grp for i in g.objs],
                          "".join(g.text for g in grp), grp[0].font, grp[0].size,
                          (min(g.bbox[0] for g in grp), min(g.bbox[1] for g in grp),
                           max(g.bbox[2] for g in grp), max(g.bbox[3] for g in grp)),
                          grp[0].in_layer, grp[0].subset,
                          [t for g in grp for t in g.tops], path_center=(cx, cy))
        lines[k:j + 1] = [merged]
    for n, L in enumerate(lines):
        L.index = n


def line_at(lines: list[TextLine], x: float, y: float, tol: float = 2.0) -> TextLine | None:
    hits = [L for L in lines if L.bbox[0] - tol <= x <= L.bbox[2] + tol and L.bbox[1] - tol <= y <= L.bbox[3] + tol]
    return min(hits, key=lambda L: (L.bbox[2] - L.bbox[0]) * (L.bbox[3] - L.bbox[1])) if hits else None


def _load_font(doc, font: tuple):
    import pypdfium2.raw as r
    kind, val = font
    if kind == "std":
        return r.FPDFText_LoadStandardFont(doc.raw, val.encode("ascii"))
    if kind == "file":
        with open(val, "rb") as f:
            data = f.read()
        buf = ctypes.create_string_buffer(data, len(data))
        _font_data_keep.append(buf)
        return r.FPDFText_LoadFont(doc.raw, ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)), len(data),
                                   r.FPDF_FONT_TRUETYPE, 1)
    return None


_wide_keep = []


def _wide(text: str):
    """UTF-16 pointer for pdfium (the buffer stays alive until the next call)."""
    buf = ctypes.create_string_buffer((text + "\0").encode("utf-16-le"))
    _wide_keep[:] = [buf]
    return ctypes.cast(buf, ctypes.POINTER(ctypes.c_ushort))


def edit_line(doc, page_index: int, line: TextLine, new_text: str, font: tuple | None = None,
              size: float | None = None) -> list[str]:
    """Change a row. font: None (original font) | ("std", "Helvetica") | ("file", "/path/font.ttf").
        Returns hints. Modifies the document directly (re-render afterwards).
    """
    import pypdfium2.raw as r
    notes = []
    page = doc[page_index]
    try:
        objs = [r.FPDFPage_GetObject(page.raw, i) for i in line.objs]
        first = objs[0]
        if font is None and (size is None or abs(size - line.size) < 0.01):
            # text only: the first object keeps font, color, position, layer
            if line.subset and any(ch not in line.text for ch in new_text if not ch.isspace()):
                notes.append(tr("Die Originalschrift ist nur als Teilmenge eingebettet – neue Zeichen fehlen evtl. "
                                "in der Darstellung. Dann bitte eine andere Schrift wählen."))
            r.FPDFText_SetText(first, _wide(new_text))
            for o in objs[1:]:
                r.FPDFPage_RemoveObject(page.raw, o)
                r.FPDFPageObj_Destroy(o)
        else:
            fh = _load_font(doc, font) if font is not None else r.FPDFTextObj_GetFont(first)
            if not fh:
                raise RuntimeError(tr("Schrift konnte nicht geladen werden."))
            new = r.FPDFPageObj_CreateTextObj(doc.raw, fh, ctypes.c_float(size or line.size))
            r.FPDFText_SetText(new, _wide(new_text))
            m = r.FS_MATRIX()
            r.FPDFPageObj_GetMatrix(first, ctypes.byref(m))
            r.FPDFPageObj_SetMatrix(new, ctypes.byref(m))
            cr, cg, cb, ca = (ctypes.c_uint() for _ in range(4))
            if r.FPDFPageObj_GetFillColor(first, ctypes.byref(cr), ctypes.byref(cg), ctypes.byref(cb), ctypes.byref(ca)):
                r.FPDFPageObj_SetFillColor(new, cr.value, cg.value, cb.value, ca.value)
            for o in objs:
                r.FPDFPage_RemoveObject(page.raw, o)
                r.FPDFPageObj_Destroy(o)
            r.FPDFPage_InsertObject(page.raw, new)
            if line.in_layer:
                notes.append(tr("Der Text lag in einer Ebene – mit neuer Schrift gehört er nicht mehr zu dieser Ebene."))
        r.FPDFPage_GenerateContent(page.raw)
    finally:
        page.close()
    return notes


def transform_object(doc, page_index: int, obj: "PageObject", scale: float = 1.0, dx: float = 0.0, dy: float = 0.0,
                      origin: tuple = (0.0, 0.0)):
    """Vektor-/Bildobjekt verschieben/skalieren (um origin). Analysiert wie transform_line."""
    import pypdfium2.raw as r
    ox, oy = float(origin[0]), float(origin[1])
    s = float(scale)
    page = doc[page_index]
    try:
        for o in [r.FPDFPage_GetObject(page.raw, i) for i in obj.objs]:
            r.FPDFPageObj_Transform(o, s, 0.0, 0.0, s, ox - s * ox + float(dx), oy - s * oy + float(dy))
        r.FPDFPage_GenerateContent(page.raw)
    finally:
        page.close()


def delete_object(doc, page_index: int, obj: "PageObject"):
    import pypdfium2.raw as r
    page = doc[page_index]
    try:
        for o in [r.FPDFPage_GetObject(page.raw, i) for i in obj.objs]:
            r.FPDFPage_RemoveObject(page.raw, o)
            r.FPDFPageObj_Destroy(o)
        r.FPDFPage_GenerateContent(page.raw)
    finally:
        page.close()


def transform_objects(doc, page_index: int, objs: list, scale: float = 1.0, dx: float = 0.0, dy: float = 0.0,
                        origin: tuple = (0.0, 0.0)):
    """Mehrere Vektor-/Bildobjekte gemeinsam verschieben/skalieren (ein GenerateContent)."""
    import pypdfium2.raw as r
    ox, oy = float(origin[0]), float(origin[1])
    s = float(scale)
    page = doc[page_index]
    try:
        idx = [i for o in objs for i in o.objs]
        for o in [r.FPDFPage_GetObject(page.raw, i) for i in idx]:
            r.FPDFPageObj_Transform(o, s, 0.0, 0.0, s, ox - s * ox + float(dx), oy - s * oy + float(dy))
        r.FPDFPage_GenerateContent(page.raw)
    finally:
        page.close()


def delete_objects(doc, page_index: int, objs: list):
    import pypdfium2.raw as r
    page = doc[page_index]
    try:
        # alle Handles zuerst holen: Entfernen verschiebt die Indizes der uebrigen Objekte
        handles = [r.FPDFPage_GetObject(page.raw, i) for ob in objs for i in ob.objs]
        for o in handles:
            r.FPDFPage_RemoveObject(page.raw, o)
            r.FPDFPageObj_Destroy(o)
        r.FPDFPage_GenerateContent(page.raw)
    finally:
        page.close()


def transform_lines_bulk(doc, page_index: int, lines: list, scale: float = 1.0, dx: float = 0.0, dy: float = 0.0,
                         origin: tuple = (0.0, 0.0)):
    """Mehrere Textzeilen gemeinsam verschieben/skalieren (pdfium, ein GenerateContent)."""
    import pypdfium2.raw as r
    s = float(scale)
    page = doc[page_index]
    try:
        for L in lines:
            transform_line(doc, page_index, L, s, dx, dy, origin, _page=page)
        r.FPDFPage_GenerateContent(page.raw)
    finally:
        page.close()


def delete_lines(doc, page_index: int, lines: list):
    import pypdfium2.raw as r
    page = doc[page_index]
    try:
        handles = [r.FPDFPage_GetObject(page.raw, i) for L in lines for i in L.objs]
        for o in handles:
            r.FPDFPage_RemoveObject(page.raw, o)
            r.FPDFPageObj_Destroy(o)
        r.FPDFPage_GenerateContent(page.raw)
    finally:
        page.close()


def transform_objects_bulk(doc, page_index: int, objs: list, scale: float = 1.0,
                           dx: float = 0.0, dy: float = 0.0, origin: tuple = (0.0, 0.0)):
    """Mehrere Vektor-/Bildobjekte gemeinsam verschieben/skalieren (pdfium, ein GenerateContent)."""
    import pypdfium2.raw as r
    page = doc[page_index]
    try:
        for O in objs:
            for i in O.objs:
                o = r.FPDFPage_GetObject(page.raw, i)
                ox, oy = float(origin[0]), float(origin[1])
                s = float(scale)
                r.FPDFPageObj_Transform(o, s, 0.0, 0.0, s, ox - s * ox + float(dx), oy - s * oy + float(dy))
        r.FPDFPage_GenerateContent(page.raw)
    finally:
        page.close()


def delete_objects_bulk(doc, page_index: int, objs: list):
    """Mehrere Vektor-/Bildobjekte gemeinsam löschen (pdfium, ein GenerateContent)."""
    import pypdfium2.raw as r
    page = doc[page_index]
    try:
        for O in objs:
            for o in [r.FPDFPage_GetObject(page.raw, i) for i in O.objs]:
                r.FPDFPage_RemoveObject(page.raw, o)
                r.FPDFPageObj_Destroy(o)
        r.FPDFPage_GenerateContent(page.raw)
    finally:
        page.close()


# --------------------------------------------------------------------------- #
# Z-Order (1.12): Objekte und Ebenen-Blöcke im Seiteninhalt umordnen.
# Kernlogik (_z_runs/_z_permute) ist pure Funktion -> ohne pikepdf testbar.
# --------------------------------------------------------------------------- #
PATH_CONSTR_OPS = {"m", "l", "c", "v", "y", "h", "re"}
PATH_PAINT_OPS = {"S", "s", "f", "F", "f*", "B", "B*", "b", "b*"}
CLIP_MARK_OPS = {"W", "W*"}
# ZSTATE_OPS wird erst nach STATE_OPS definiert (siehe unten bei SHOW_OPS/STATE_OPS).


def _z_runs(ops: list, image_dos: set) -> list:
    """Content-Operatorenliste (Namen) in Objekt-Runs zerlegen.
        ops: Operatorennamen in Reihenfolge; image_dos: Indizes der Bild-Do-Aufrufe.
        -> [(start, end, "path"|"image")] – nur verschiebbare Objekte, Clips bleiben draußen.
        Ein Pfad-Run beginnt bei der ersten Konstruktions-Operation und endet mit dem Paint;
        vorangestellte Zustands-Operationen (Farbe, Strichstärke) wandern mit."""
    runs = []
    cur, clip = None, False
    bt, has_show = None, False
    for i, op in enumerate(ops):
        if op in PATH_CONSTR_OPS and cur is None and bt is None:
            cur = i
        elif op in CLIP_MARK_OPS and cur is not None:
            clip = True
        elif op in PATH_PAINT_OPS:
            if cur is not None:
                runs.append((cur, i, "path"))
                cur, clip = None, False
        elif op == "n":
            if cur is not None:
                if not clip:
                    runs.append((cur, i, "path"))
                cur, clip = None, False
        elif op == "BT":
            cur, clip = None, False
            if bt is None:
                bt, has_show = i, False
        elif op == "ET":
            cur, clip = None, False
            if bt is not None and has_show:
                runs.append((bt, i, "text"))
            bt, has_show = None, False
        elif op in SHOW_OPS and bt is not None:
            has_show = True
        elif op in ("q", "Q"):
            cur, clip = None, False
    # Zustands-Ops vor dem Konstruktionsstart mitnehmen; steht direkt davor ein q,
    # gehoert der Zustand zum q-Rahmen -> ganzen q..Q-Block als Run verschieben
    fixed = []
    for (st, en, kind) in runs:
        s0 = st
        while s0 - 1 >= 0 and ops[s0 - 1] in ZSTATE_OPS:
            s0 -= 1
        if s0 - 1 >= 0 and ops[s0 - 1] == "q":
            depth, j = 1, en
            while j + 1 < len(ops):
                j += 1
                if ops[j] == "q":
                    depth += 1
                elif ops[j] == "Q":
                    depth -= 1
                    if depth == 0:
                        break
            if depth == 0:
                fixed.append((s0 - 1, j, kind))
                continue
        fixed.append((s0, en, kind))
    # Bilder: Do ggf. mit umschließendem q..Q
    out = list(fixed)
    for i in sorted(image_dos):
        s0 = i
        while s0 - 1 >= 0 and ops[s0 - 1] in ZSTATE_OPS:      # cm/gs direkt davor gehoert zum Bild
            s0 -= 1
        if s0 - 1 >= 0 and ops[s0 - 1] == "q":                # im q-Rahmen -> ganzen Block verschieben
            depth, j = 1, i
            while j + 1 < len(ops):
                j += 1
                if ops[j] == "q":
                    depth += 1
                elif ops[j] == "Q":
                    depth -= 1
                    if depth == 0:
                        break
            if depth == 0:
                out.append((s0 - 1, j, "image"))
                continue
        out.append((s0, i, "image"))
    return sorted(out, key=lambda x: x[0])


def _z_permute(n: int, targets: set, where: str) -> list | None:
    """Run-Permutation: Slots 0..n-1, targets = Auswahl (Indices).
        where: "up" | "down" | "front" | "back" -> neue Slot-Reihenfolge (Liste alter Slots)."""
    rest = [i for i in range(n) if i not in targets]
    tg = sorted(targets)
    if where == "front":
        return rest + tg
    if where == "back":
        return tg + rest
    order = list(range(n))
    if where == "up":
        for t in sorted(targets, reverse=True):          # oberstes zuerst
            i = order.index(t)
            if i + 1 >= len(order) or order[i + 1] in targets:
                continue                                 # schon ganz vorn (bzw. hinter einem anderen Ziel)
            order[i], order[i + 1] = order[i + 1], order[i]
        return order
    if where == "down":
        for t in tg:                                      # unterstes zuerst
            i = order.index(t)
            if i == 0 or order[i - 1] in targets:
                continue                                 # schon ganz hinten
            order[i], order[i - 1] = order[i - 1], order[i]
        return order
    return None


def reorder_objects(data: bytes, page_index: int, objs: list, where: str) -> bytes | None:
    """Objekte in der Zeichenreihenfolge verschieben (up/down/front/back), ohne Neuaufbau.
        objs: PageObject-Liste (Auswahl). None, wenn die Struktur nicht sicher erkannt wurde."""
    import pypdfium2 as pdfium
    import pypdfium2.raw as r
    import pikepdf
    # Ordinalen der Ziel-Objekte je Art (pdfium-Reihenfolge = ursprüngliche Content-Reihenfolge)
    want = []
    d = pdfium.PdfDocument(data)
    try:
        page = d[page_index]
        pcnt = icnt = tcnt = -1
        ordinal_map = {}                       # Seiten-Objektindex -> (Art, Ordinal)
        for i in range(r.FPDFPage_CountObjects(page.raw)):
            o = r.FPDFPage_GetObject(page.raw, i)
            t = r.FPDFPageObj_GetType(o)
            if t == r.FPDF_PAGEOBJ_PATH:
                pcnt += 1
                ordinal_map[i] = ("path", pcnt)
            elif t == r.FPDF_PAGEOBJ_IMAGE:
                icnt += 1
                ordinal_map[i] = ("image", icnt)
            elif t == r.FPDF_PAGEOBJ_TEXT:
                tcnt += 1
                ordinal_map[i] = ("text", tcnt)
        page.close()
        for ob in objs:
            for i in ob.objs:
                if i in ordinal_map:
                    want.append(ordinal_map[i])
    finally:
        d.close()
    pdf = pikepdf.open(io.BytesIO(data))
    try:
        page = pdf.pages[page_index]
        res = page.obj.get("/Resources") or {}
        xo = res.get("/XObject") or {}
        ops = list(pikepdf.parse_content_stream(page))
        names = [str(getattr(ins, "operator", "")) for ins in ops]
        image_dos = set()
        for k, ins in enumerate(ops):
            if names[k] == "Do" and getattr(ins, "operands", None):
                x = xo.get(str(ins.operands[0]))
                try:
                    if x is not None and x.get("/Subtype") == pikepdf.Name.Image:
                        image_dos.add(k)
                except Exception:
                    pass
        runs = _z_runs(names, image_dos)
        path_runs = [(s, e) for s, e, k in runs if k == "path"]
        image_runs = [(s, e) for s, e, k in runs if k == "image"]
        text_runs = [(s, e) for s, e, k in runs if k == "text"]
        if not path_runs and not image_runs and not text_runs:
            return None
        # Text: passt die Zahl der BT-Runs zu den Text-Objekten? Sonst ist keine
        # sichere Zuordnung moeglich (z. B. ein BT-Block mit vielen Zeilen).
        want_text = any(k == "text" for k, _o in want)
        if want_text and len(text_runs) != tcnt + 1:
            return None
        # targets als Run-Slots: je Art Ordinal -> Run-Index
        slots = set()
        for kind, ordinal in want:
            lst = path_runs if kind == "path" else image_runs if kind == "image" else text_runs
            if not (0 <= ordinal < len(lst)):
                return None
            slots.add(runs.index((lst[ordinal][0], lst[ordinal][1], kind)))
        order = _z_permute(len(runs), slots, where)
        if order is None or order == list(range(len(runs))):
            return data if order == list(range(len(runs))) else None
        # neu zusammensetzen: Lücken bleiben auf ihrem Platz, Runs werden durchvertauscht
        segs = []                       # pro Slot: (Luecke davor, Run)
        for k in range(len(runs)):
            st, en, _kind = runs[k]
            prev_end = runs[k - 1][1] + 1 if k else 0
            segs.append((ops[prev_end:st], ops[st:en + 1]))
        tail = ops[runs[-1][1] + 1:]
        out = []
        for k in order:
            out += segs[k][0] + segs[k][1]
        out += tail
        page.obj.Contents = pikepdf.Stream(pdf, pikepdf.unparse_content_stream(out))
        buf = io.BytesIO()
        pdf.save(buf)
        return buf.getvalue()
    finally:
        pdf.close()


def reorder_layer_blocks(data: bytes, page_index: int, key: str, where: str) -> bytes | None:
    """Ebene in der Zeichenreihenfolge der Seite verschieben: ihre /OC BDC..EMC-Blöcke
        wandern (up/down/front/back) relativ zu den Blöcken der anderen Ebenen."""
    import pikepdf
    pdf = pikepdf.open(io.BytesIO(data))
    try:
        page = pdf.pages[page_index]
        res = page.obj.get("/Resources") or {}
        props = res.get("/Properties") or {}
        keys = {}                        # Properties-Name -> OCG-Key
        for n, oc in props.items():
            for g in preflight._ocgs_of(oc):
                keys[str(n)] = preflight._key(g)
                break
        ops = list(pikepdf.parse_content_stream(page))
        names = [str(getattr(ins, "operator", "")) for ins in ops]
        runs, depth, cur, start_key = [], 0, None, None
        for i, op in enumerate(names):
            if op in ("BDC", "BMC"):
                if depth == 0:
                    ins = ops[i]
                    operands = getattr(ins, "operands", [])
                    if op == "BDC" and len(operands) >= 2 and str(operands[0]) == "/OC":
                        nm = str(operands[1])
                        start_key = keys.get(nm[1:] if nm.startswith("/") else nm)
                        cur = i if start_key else None
                    else:
                        cur = None
                depth += 1
            elif op == "EMC":
                depth -= 1
                if depth == 0 and cur is not None:
                    runs.append((cur, i, start_key))
                    cur, start_key = None, None
        if not runs:
            return None
        targets = {k for k, (s, e, ky) in enumerate(runs) if ky == key}
        if not targets:
            return None
        order = _z_permute(len(runs), targets, where)
        if order is None or order == list(range(len(runs))):
            return data if order == list(range(len(runs))) else None
        segs = []
        for k in range(len(runs)):
            st, en, _ky = runs[k]
            prev_end = runs[k - 1][1] + 1 if k else 0
            segs.append((ops[prev_end:st], ops[st:en + 1]))
        tail = ops[runs[-1][1] + 1:]
        out = []
        for k in order:
            out += segs[k][0] + segs[k][1]
        out += tail
        page.obj.Contents = pikepdf.Stream(pdf, pikepdf.unparse_content_stream(out))
        buf = io.BytesIO()
        pdf.save(buf)
        return buf.getvalue()
    finally:
        pdf.close()


def transform_line(doc, page_index: int, line: TextLine, scale: float = 1.0, dx: float = 0.0, dy: float = 0.0,
                   origin: tuple = (0.0, 0.0), _page=None):
    """Zeile verschieben/skalieren (um origin). Schrift, Farbe und Ebene bleiben erhalten.
        _page: bereits geöffnete Seite (für Bulk-Operationen) – dann kein GenerateContent."""
    import pypdfium2.raw as r
    ox, oy = float(origin[0]), float(origin[1])
    s = float(scale)
    page = _page or doc[page_index]
    try:
        for o in [r.FPDFPage_GetObject(page.raw, i) for i in line.objs]:
            r.FPDFPageObj_Transform(o, s, 0.0, 0.0, s, ox - s * ox + float(dx), oy - s * oy + float(dy))
        if _page is None:
            r.FPDFPage_GenerateContent(page.raw)
    finally:
        if _page is None:
            page.close()


SHOW_OPS = {"Tj", "TJ", "'", '"'}
STATE_OPS = {"Tf", "Tc", "Tw", "Tz", "TL", "Ts", "Tr", "rg", "RG", "g", "G", "k", "K", "cs", "CS", "sc", "SC", "scn",
             "SCN", "gs", "w", "J", "j", "M", "d", "ri", "i"}
ZSTATE_OPS = STATE_OPS | {"cm"} - {"q"}


def _show_nonempty(ins) -> bool:
    import pikepdf
    arg = ins.operands[-1] if ins.operands else b""
    if str(ins.operator) == "TJ":
        return any(isinstance(x, pikepdf.String) and len(bytes(x)) for x in arg)
    return isinstance(arg, pikepdf.String) and len(bytes(arg)) > 0


POS_OPS = {"Td", "TD", "Tm", "T*"}


def _mmul(m, n):
    """Matrixprodukt m·n (PDF-Zeilenvektor-Konvention, 6 Werte)."""
    a, b, c, d, e, f = m
    A, B, C, D, E, F = n
    return (a * A + b * C, a * B + b * D, c * A + d * C, c * B + d * D, e * A + f * C + E, e * B + f * D + F)


def _minv(m):
    a, b, c, d, e, f = m
    det = a * d - b * c
    if abs(det) < 1e-12:
        return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    ia, ib, ic, id_ = d / det, -b / det, -c / det, a / det
    return (ia, ib, ic, id_, -(e * ia + f * ic), -(e * ib + f * id_))


def _local_cm(ctm, page_cm):
    """Convert a page transformation into the coordinate system valid at that point: CTM · T · CTM⁻¹."""
    return [float(v) for v in _mmul(_mmul(ctm, page_cm), _minv(ctm))]


def _num_ops(ins):
    import pikepdf
    out = []
    for x in getattr(ins, "operands", []):
        if isinstance(x, (pikepdf.String, pikepdf.Name, pikepdf.Array, pikepdf.Dictionary)):
            return []
        try:
            out.append(float(x))
        except (TypeError, ValueError):
            return []
    return out


def _mul_td(m, tx, ty):
    a, b, c, d, e, f = m
    return (a, b, c, d, tx * a + ty * c + e, tx * b + ty * d + f)


def transform_line_blocks(data: bytes, page_index: int, line: TextLine, scale=1.0, dx=0.0, dy=0.0,
                          origin=(0.0, 0.0)) -> bytes | None:
    """Move/scale a row WITHOUT re-creating the page.

        The row's text operators are lifted out of their text block (BT…ET) and wrapped with q/cm/Q; before and
        after, the block continues at exactly the same text position (the row matrix is carried along). Everything else
        stays unchanged. Also works with Type3 fonts (e.g. Chrome PDFs), which pdfium cannot re-write.
        None if a part continues directly at foreign text without its own positioning (then fallback).
    """
    import pikepdf
    ox, oy, s = float(origin[0]), float(origin[1]), float(scale)
    page_cm = (s, 0.0, 0.0, s, ox - s * ox + float(dx), oy - s * oy + float(dy))
    targets = set(line.tops)
    I = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

    def O(name, args=()):
        return pikepdf.ContentStreamInstruction(list(args), pikepdf.Operator(name))

    pdf = pikepdf.open(io.BytesIO(data))
    try:
        page = pdf.pages[page_index]
        ops = list(pikepdf.parse_content_stream(page))
        # 1) Durchlauf: je Befehl Textzeilenmatrix (vorher/nachher), Ordnungsnummer der Textausgaben
        info = []                      # (op, ordinal oder None, tlm_vorher, tlm_nachher, in_bt, ctm)
        tlm, TL, in_bt, ordinal = I, 0.0, False, -1
        ctm, stack = I, []
        for ins in ops:
            op = str(getattr(ins, "operator", ""))
            before = tlm
            ordn = None
            vals = _num_ops(ins) if op in POS_OPS | {"TL", "cm"} else []
            if op == "q":
                stack.append(ctm)
            elif op == "Q":
                ctm = stack.pop() if stack else I
            elif op == "cm" and len(vals) == 6:
                ctm = _mmul(tuple(vals), ctm)
            if op == "BT":
                tlm, in_bt = I, True
            elif op == "ET":
                in_bt = False
            elif op == "Tm" and len(vals) == 6:
                tlm = tuple(vals)
            elif op == "Td" and len(vals) == 2:
                tlm = _mul_td(tlm, vals[0], vals[1])
            elif op == "TD" and len(vals) == 2:
                TL = -vals[1]
                tlm = _mul_td(tlm, vals[0], vals[1])
            elif op == "TL" and vals:
                TL = vals[0]
            elif op in ("T*", "'", '"'):
                tlm = _mul_td(tlm, 0.0, -TL)
            if op in SHOW_OPS and _show_nonempty(ins):
                ordinal += 1
                ordn = ordinal
            info.append((op, ordn, before, tlm, in_bt, ctm))
        if not targets <= {x[1] for x in info if x[1] is not None}:
            return None
        # 2) build sections: contiguous runs with target text within one BT block
        segs, k = [], 0
        while k < len(info):
            op, ordn, _b, _a, in_bt, _c = info[k]
            if ordn is not None and ordn in targets and in_bt:
                # Beginn: nach der letzten fremden Textausgabe bzw. nach BT
                st = k
                while st - 1 >= 0 and info[st - 1][0] != "BT" and not (info[st - 1][1] is not None and info[st - 1][1] not in targets):
                    st -= 1
                en = k
                j = k + 1
                while j < len(info) and info[j][0] != "ET" and not (info[j][1] is not None and info[j][1] not in targets):
                    if info[j][1] is not None:
                        en = j
                    j += 1
                # erste Ausgabe im Abschnitt braucht eine Positionierung (oder Blockanfang)
                first_show = next(i for i in range(st, en + 1) if info[i][1] is not None)
                has_pos = any(info[i][0] in POS_OPS | {"'", '"'} for i in range(st, first_show + 1)) or info[st - 1][0] == "BT"
                # after the section: the next output needs its own positioning
                nxt_ok = True
                for i in range(en + 1, len(info)):
                    if info[i][0] in POS_OPS or info[i][0] in ("'", '"') or info[i][0] == "ET":
                        break
                    if info[i][1] is not None:
                        nxt_ok = False
                        break
                if not (has_pos and nxt_ok):
                    return None
                segs.append((st, en))
                k = en + 1
                continue
            k += 1
        if not segs or {info[i][1] for st, en in segs for i in range(st, en + 1) if info[i][1] is not None} != targets:
            return None
        # 3) Neu zusammensetzen
        out, seg_at = [], {st: en for st, en in segs}
        k = 0
        while k < len(ops):
            if k in seg_at:
                st, en = k, seg_at[k]
                out += [O("ET"), O("q"), O("cm", _local_cm(info[st][5], page_cm)), O("BT"), O("Tm", info[st][2])]
                out += ops[st:en + 1]
                out += [O("ET"), O("Q")]
                out += [ops[i] for i in range(st, en + 1) if str(getattr(ops[i], "operator", "")) in STATE_OPS]
                out += [O("BT"), O("Tm", info[en][3])]
                k = en + 1
                continue
            out.append(ops[k])
            k += 1
        page.obj.Contents = pikepdf.Stream(pdf, pikepdf.unparse_content_stream(out))
        buf = io.BytesIO()
        pdf.save(buf)
        return buf.getvalue()
    finally:
        pdf.close()


# --------------------------------------------------------------------------- #
# Pfadtext (Kreistext): Einzelbuchstaben mit eigener Drehung auf einem Bogen.
# Zeilengröße ändern = als Gruppe um das Bogenzentrum skalieren (ohne Neuaufbau
# der Seite); neu setzen geht nicht (Buchstaben haben je eigene Matrix).
# --------------------------------------------------------------------------- #
def _circle_fit(pts: list) -> tuple | None:
    """Kreis durch Punkte (algebraische Kleinstquadrate, Kasa) -> (cx, cy, r) oder None."""
    n = len(pts)
    if n < 3:
        return None
    sx = sum(x for x, y in pts); sy = sum(y for x, y in pts)
    sxx = sum(x * x for x, y in pts); syy = sum(y * y for x, y in pts); sxy = sum(x * y for x, y in pts)
    sxz = sum(x * (x * x + y * y) for x, y in pts); syz = sum(y * (x * x + y * y) for x, y in pts)
    sz = sum(x * x + y * y for x, y in pts)
    # Normalgleichungen: D·sxx + E·sxy + F·sx = -sxz usw. (x²+y² = -D·x - E·y - F)
    rows = [[sxx, sxy, sx, -sxz], [sxy, syy, sy, -syz], [sx, sy, n, -sz]]

    def solve(m):
        det = (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
               - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
               + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))
        if abs(det) < 1e-9:
            return None
        out = []
        for col in range(3):
            mm = [row[:] for row in m]
            for i in range(3):
                mm[i][col] = m[i][3]
            d = (mm[0][0] * (mm[1][1] * mm[2][2] - mm[1][2] * mm[2][1])
                 - mm[0][1] * (mm[1][0] * mm[2][2] - mm[1][2] * mm[2][0])
                 + mm[0][2] * (mm[1][0] * mm[2][1] - mm[1][1] * mm[2][0]))
            out.append(d / det)
        return out

    sol = solve(rows)
    if sol is None:
        return None
    D, E, F = sol
    cx, cy = -D / 2.0, -E / 2.0
    r2 = D * D / 4.0 + E * E / 4.0 - F
    if r2 <= 0:
        return None
    import math
    return (cx, cy, math.sqrt(r2))


def path_text_center(doc, page_index: int, line: TextLine) -> tuple | None:
    """Bogenzentrum, wenn die Zeile Pfadtext ist (>= 3 einzeln gesetzte Buchstaben mit
        unterschiedlicher Drehung, deren Ursprünge auf einem Kreis liegen), sonst None."""
    import ctypes
    import math
    import pypdfium2.raw as r
    if len(line.objs) < 3:
        return None
    page = doc[page_index]
    try:
        pts, angles = [], []
        for i in line.objs:
            o = r.FPDFPage_GetObject(page.raw, i)
            m = r.FS_MATRIX()
            if not r.FPDFPageObj_GetMatrix(o, ctypes.byref(m)):
                return None
            pts.append((float(m.e), float(m.f)))
            angles.append(math.atan2(m.b, m.a))
        return _arc_center(pts, angles)
    finally:
        page.close()


def _arc_center(pts: list, angles: list) -> tuple | None:
    """Bogenzentrum (cx, cy), wenn die Buchstaben-Ursprünge pts mit Drehungen angles (Bogenmaß)
        Pfadtext sind: >= 3 Buchstaben, Drehung streut um mindestens 10°, Ursprünge auf einem Kreis."""
    import math
    if len(pts) < 3 or len(pts) != len(angles):
        return None
    # unterschiedliche Drehung (kreisumlaufend gemessen) -> Bogen, keine gerade Zeile
    a0 = angles[0]
    spread = [math.atan2(math.sin(a - a0), math.cos(a - a0)) for a in angles]
    if max(spread) - min(spread) < math.radians(10):
        return None
    c = _circle_fit(pts)
    if c is None:
        return None
    cx, cy, rad = c
    if not (1e-3 < rad < 1e5):
        return None
    ds = [math.hypot(x - cx, y - cy) for x, y in pts]
    mid = (max(ds) + min(ds)) / 2.0
    if mid < 1e-3 or (max(ds) - min(ds)) / mid > 0.8:
        return None
    return (cx, cy)


def _path_center_of(data: bytes, page_index: int, line: TextLine) -> tuple | None:
    import pypdfium2 as pdfium
    d = pdfium.PdfDocument(data)
    try:
        return path_text_center(d, page_index, line)
    finally:
        d.close()


def verify_edit(before: bytes, after: bytes, page_index: int, ignore_boxes: list) -> str:
    """Verify that nothing outside the edited areas was lost (image pixels and characters).
        Returns "" or an error description.
    """
    import numpy as np
    import pypdfium2 as pdfium

    def outside(x, y):
        return not any(x0 - 2 <= x <= x1 + 2 and y0 - 2 <= y <= y1 + 2 for (x0, y0, x1, y1) in ignore_boxes)

    def measure(data):
        d = pdfium.PdfDocument(data)
        try:
            pg = d[page_index]
            _w, h = pg.get_size()
            a = np.asarray(pg.render(scale=1.0).to_pil().convert("L")) < 160
            tp = pg.get_textpage()
            n = 0
            for i in range(tp.count_chars()):
                l, b, r, t = tp.get_charbox(i)
                if r > l and outside((l + r) / 2, (b + t) / 2):
                    n += 1
            tp.close()
            pg.close()
            return a, n, h
        finally:
            d.close()
    a0, n0, h = measure(before)
    a1, n1, _h = measure(after)
    if n0 >= 3 and n1 < 0.7 * n0:
        return tr("Nach der Änderung fehlt Text außerhalb der bearbeiteten Zeile ({0} → {1} Zeichen).").format(n0, n1)
    if a0.shape == a1.shape:
        mask = np.ones_like(a0)
        for (x0, y0, x1, y1) in ignore_boxes:
            r0, r1 = max(0, int(h - y1) - 3), min(a0.shape[0], int(h - y0) + 4)
            c0, c1 = max(0, int(x0) - 3), min(a0.shape[1], int(x1) + 4)
            mask[r0:r1, c0:c1] = False
        ink0, ink1 = int((a0 & mask).sum()), int((a1 & mask).sum())
        if ink0 > 50 and ink1 < 0.7 * ink0:
            return tr("Nach der Änderung fehlt Inhalt außerhalb der bearbeiteten Zeile ({0} → {1} Bildpunkte).").format(ink0, ink1)
    return ""


def remove_line_ops(data: bytes, page_index: int, line: TextLine) -> bytes:
    """Textausgaben der Zeile aus dem Inhalt entfernen – ohne die Seite neu zu erzeugen. Positionierungen bleiben
    erhalten (' und \" werden durch T* ersetzt), damit nachfolgender Text an seiner Stelle bleibt."""
    return remove_lines_ops(data, page_index, [line])


def remove_lines_ops(data: bytes, page_index: int, lines: list) -> bytes:
    """Wie remove_line_ops, für mehrere Zeilen in einem Durchgang (Ordnungsnummern bleiben gültig)."""
    import pikepdf
    targets = {t for L in lines for t in L.tops}
    pdf = pikepdf.open(io.BytesIO(data))
    try:
        page = pdf.pages[page_index]
        out, ordinal = [], -1
        for ins in pikepdf.parse_content_stream(page):
            op = str(getattr(ins, "operator", ""))
            if op in SHOW_OPS and _show_nonempty(ins):
                ordinal += 1
                if ordinal in targets:
                    if op == "'":
                        out.append(pikepdf.ContentStreamInstruction([], pikepdf.Operator("T*")))
                    elif op == '"':
                        a = list(ins.operands)
                        out += [pikepdf.ContentStreamInstruction([a[0]], pikepdf.Operator("Tw")),
                                pikepdf.ContentStreamInstruction([a[1]], pikepdf.Operator("Tc")),
                                pikepdf.ContentStreamInstruction([], pikepdf.Operator("T*"))]
                    continue
            out.append(ins)
        page.obj.Contents = pikepdf.Stream(pdf, pikepdf.unparse_content_stream(out))
        buf = io.BytesIO()
        pdf.save(buf)
        return buf.getvalue()
    finally:
        pdf.close()


# --------------------------------------------------------------------------- #
# Farbe ändern (1.12): direkt im Seiteninhalt, damit CMYK möglich ist (pdfium kann nur RGB).
# Vor dem Objekt wird die neue Farbe gesetzt, danach die vorherige wiederhergestellt –
# alles Nachfolgende zeichnet unverändert.
# --------------------------------------------------------------------------- #
_FILL_SET = {"g": "/DeviceGray", "rg": "/DeviceRGB", "k": "/DeviceCMYK"}
_STROKE_SET = {"G": "/DeviceGray", "RG": "/DeviceRGB", "K": "/DeviceCMYK"}


def color_ops(color, stroke: bool = False) -> list:
    """("gray", (g,)) | ("rgb", (r, g, b)) | ("cmyk", (c, m, y, k)), Werte 0..1 -> Operatoren."""
    import pikepdf
    kind, vals = color
    op = {"gray": "g", "rgb": "rg", "cmyk": "k"}[kind]
    return [pikepdf.ContentStreamInstruction([round(float(v), 4) for v in vals],
                                             pikepdf.Operator(op.upper() if stroke else op))]


def recolor(data: bytes, page_index: int, color, lines: list = (), objs: list = (),
            fill: bool = True, stroke: bool = True) -> bytes | None:
    """Gewählte Textzeilen und Vektorobjekte umfärben (Fläche und/oder Kontur).
        Bilder bleiben unverändert. None, wenn die Zuordnung Objekt -> Inhalt nicht sicher ist."""
    import pikepdf
    import pypdfium2 as pdfium
    import pypdfium2.raw as r
    text_targets = {t for L in lines for t in L.tops}
    path_targets, n_paths = set(), 0
    if objs:
        d = pdfium.PdfDocument(data)
        try:
            page = d[page_index]
            pord, wanted = -1, {i for O in objs for i in O.objs}
            for i in range(r.FPDFPage_CountObjects(page.raw)):
                if r.FPDFPageObj_GetType(r.FPDFPage_GetObject(page.raw, i)) == r.FPDF_PAGEOBJ_PATH:
                    pord += 1
                    if i in wanted:
                        path_targets.add(pord)
            n_paths = pord + 1
            page.close()
        finally:
            d.close()
    if not text_targets and not path_targets:
        return data
    I = pikepdf.ContentStreamInstruction
    O = pikepdf.Operator

    def cs_for(ins, table, cs_op):
        """Für sc/scn nach g/rg/k: den passenden Farbraum ausdrücklich setzen."""
        return I([pikepdf.Name(table[str(ins.operator)])], O(cs_op))

    pdf = pikepdf.open(io.BytesIO(data))
    try:
        pg = pdf.pages[page_index]
        out = []
        fcol, scol = [I([0], O("g"))], [I([0], O("G"))]     # Anfangszustand: Schwarz
        stack = []
        in_bt, path_start, pord, tord = False, None, -1, -1
        new_fill = color_ops(color) if fill else []
        new_stroke = color_ops(color, stroke=True) if stroke else []
        for ins in pikepdf.parse_content_stream(pg):
            op = str(getattr(ins, "operator", ""))
            if op == "q":
                stack.append((fcol, scol))
            elif op == "Q":
                if stack:
                    fcol, scol = stack.pop()
            elif op in _FILL_SET:
                fcol = [ins]
            elif op == "cs":
                fcol = [ins]
            elif op in ("sc", "scn"):
                base = fcol[0] if str(fcol[0].operator) == "cs" else cs_for(fcol[0], _FILL_SET, "cs") \
                    if str(fcol[0].operator) in _FILL_SET else None
                fcol = [base, ins] if base is not None else [ins]
            elif op in _STROKE_SET:
                scol = [ins]
            elif op == "CS":
                scol = [ins]
            elif op in ("SC", "SCN"):
                base = scol[0] if str(scol[0].operator) == "CS" else cs_for(scol[0], _STROKE_SET, "CS") \
                    if str(scol[0].operator) in _STROKE_SET else None
                scol = [base, ins] if base is not None else [ins]
            elif op == "BT":
                in_bt = True
            elif op == "ET":
                in_bt = False
            if not in_bt and op in PATH_CONSTR_OPS and path_start is None:
                path_start = len(out)
            if op in SHOW_OPS and in_bt and _show_nonempty(ins):
                tord += 1
                if tord in text_targets:
                    out += new_fill + new_stroke + [ins] + (fcol if fill else []) + (scol if stroke else [])
                    continue
            if not in_bt and op in PATH_PAINT_OPS:
                pord += 1
                if pord in path_targets and path_start is not None:
                    out[path_start:path_start] = new_fill + new_stroke
                    out.append(ins)
                    out += (fcol if fill else []) + (scol if stroke else [])
                    path_start = None
                    continue
                path_start = None
            elif op == "n":
                path_start = None
            out.append(ins)
        if objs and pord + 1 != n_paths:
            return None                  # Pfade im Inhalt passen nicht zu pdfiums Objekten -> nicht sicher
        pg.obj.Contents = pikepdf.Stream(pdf, pikepdf.unparse_content_stream(out))
        buf = io.BytesIO()
        pdf.save(buf)
        return buf.getvalue()
    finally:
        pdf.close()


def _line_style(data: bytes, page_index: int, line: TextLine):
    """Position (page coordinates, including the font-size reference) and color of the row's first object."""
    import pypdfium2 as pdfium
    import pypdfium2.raw as r
    d = pdfium.PdfDocument(data)
    try:
        p = d[page_index]
        o = r.FPDFPage_GetObject(p.raw, line.objs[0])
        m = r.FS_MATRIX()
        r.FPDFPageObj_GetMatrix(o, ctypes.byref(m))
        cr, cg, cb, ca = (ctypes.c_uint() for _ in range(4))
        ok = r.FPDFPageObj_GetFillColor(o, ctypes.byref(cr), ctypes.byref(cg), ctypes.byref(cb), ctypes.byref(ca))
        col = (cr.value, cg.value, cb.value, ca.value) if ok else (0, 0, 0, 255)
        size = d.get_page_size(page_index)
        p.close()
        return (m.a, m.b, m.c, m.d, m.e, m.f), col, size
    finally:
        d.close()


def overlay_text(data: bytes, page_index: int, text: str, font: tuple, size: float, matrix, color) -> bytes:
    """Place a new text row OVER the page (its own small form), without re-creating the page content."""
    import pikepdf
    import pypdfium2 as pdfium
    import pypdfium2.raw as r
    # 1) create the row on an empty scratch page of the same size (pdfium may write freely here)
    pdf0 = pikepdf.open(io.BytesIO(data))
    try:
        mb = [float(v) for v in pdf0.pages[page_index].MediaBox]
    finally:
        pdf0.close()
    tmp = pdfium.PdfDocument.new()
    pg = tmp.new_page(mb[2] - mb[0], mb[3] - mb[1])
    fh = _load_font(tmp, font)
    obj = r.FPDFPageObj_CreateTextObj(tmp.raw, fh, ctypes.c_float(size))
    r.FPDFText_SetText(obj, _wide(text))
    a, b, c, d_, e, f = matrix
    m = r.FS_MATRIX(a, b, c, d_, e - mb[0], f - mb[1])
    r.FPDFPageObj_SetMatrix(obj, ctypes.byref(m))
    r.FPDFPageObj_SetFillColor(obj, *[int(v) for v in color])
    r.FPDFPage_InsertObject(pg.raw, obj)
    r.FPDFPage_GenerateContent(pg.raw)
    pg.close()
    buf = io.BytesIO()
    tmp.save(buf)
    tmp.close()
    # 2) Hilfsseite als Form auf die Zielseite legen; Original in q/Q (es kann das Koordinatensystem verstellen)
    pdf = pikepdf.open(io.BytesIO(data))
    try:
        src = pikepdf.open(io.BytesIO(buf.getvalue()))
        form = pdf.copy_foreign(src.pages[0].as_form_xobject())
        src.close()
        page = pdf.pages[page_index]
        res = preflight._resources(page)
        xo = res.get("/XObject")
        if xo is None:
            xo = res.XObject = pikepdf.Dictionary()
        name = pikepdf.Name("/PMText%d" % len(xo))
        xo[name] = form
        ops = list(pikepdf.parse_content_stream(page))
        q_, Q_ = (pikepdf.ContentStreamInstruction([], pikepdf.Operator(n)) for n in ("q", "Q"))
        add = pikepdf.parse_content_stream(pikepdf.Stream(pdf, f"q 1 0 0 1 {mb[0]:.4f} {mb[1]:.4f} cm {name} Do Q".encode()))
        page.obj.Contents = pikepdf.Stream(pdf, pikepdf.unparse_content_stream([q_] + ops + [Q_] + list(add)))
        out = io.BytesIO()
        pdf.save(out)
        return out.getvalue()
    finally:
        pdf.close()


def line_zone(data: bytes, page_index: int, line: TextLine) -> tuple:
    """Area in which a changed row may vary: its height (+30 %), full page width."""
    import pypdfium2 as pdfium
    d = pdfium.PdfDocument(data)
    try:
        pw = d.get_page_size(page_index)[0]
    finally:
        d.close()
    h = line.bbox[3] - line.bbox[1]
    return (0.0, line.bbox[1] - 0.3 * h, pw, line.bbox[3] + 0.3 * h)


def edit_line_bytes(data: bytes, page_index: int, line: TextLine, new_text: str, font: tuple | None = None,
                    size: float | None = None) -> tuple[bytes, list]:
    """Change a row, safely: first directly (pdfium); if the page loses content that way (e.g. Type3 fonts
        from Chrome), the old row is removed and the new one placed on top – the rest of the page stays unchanged.
        Pfadtext (Einzelbuchstaben mit Drehung auf einem Bogen) wird nicht neu gesetzt, sondern
        als Gruppe um sein Zentrum skaliert – Neusetzen wäre falsch (Buchstaben haben je eigene Matrix).
    """
    import pypdfium2 as pdfium
    if font is None and new_text == line.text and (size is None or abs(size - line.size) <= 0.01):
        return data, []              # nichts geändert: Seite nicht anfassen (Pfadtext würde sonst neu gesetzt)
    if line.no_text and (font is not None or new_text != line.text):
        raise ValueError(tr("Der Text dieser Zeile lässt sich nicht dekodieren (z. B. eingebettete "
                            "Teilmenge ohne Zeichenzuordnung) – Verschieben, Skalieren und Löschen "
                            "funktionieren, das Ändern von Text und Schrift nicht."))
    if (font is not None or new_text != line.text
            or (size is not None and abs(size - line.size) > 0.01)):
        c = line.path_center or _path_center_of(data, page_index, line)
        if c is not None:
            if font is not None or new_text != line.text:
                raise ValueError(tr("Text auf einem Pfad (Einzelbuchstaben mit Drehung) lässt sich nicht neu "
                                     "setzen – Schriftgröße, Position und Löschen funktionieren."))
            out = transform_line_blocks(data, page_index, line, float(size) / max(line.size, 0.1),
                                        0.0, 0.0, origin=c)
            if out is not None:
                return out, [tr("Text auf einem Pfad: als Gruppe um sein Zentrum skaliert – die Buchstaben "
                                "bleiben auf dem Bogen.")]
            raise ValueError(tr("Der Pfadtext dieser Datei lässt sich nicht skalieren – bitte die Datei an den "
                                "Entwickler schicken."))
    d = pdfium.PdfDocument(data)
    try:
        notes = edit_line(d, page_index, line, new_text, font, size) or []
        buf = io.BytesIO()
        d.save(buf)
        new = buf.getvalue()
    finally:
        d.close()
    if not verify_edit(data, new, page_index, [line_zone(data, page_index, line)]):
        return new, notes
    # fallback: overlay
    matrix, color, _size = _line_style(data, page_index, line)
    use = font or ("std", "Helvetica-Bold" if "bold" in line.font.lower() else "Helvetica")
    out = overlay_text(remove_line_ops(data, page_index, line), page_index, new_text, use, size or line.size,
                       matrix, color)
    notes = [n for n in notes if "Ebene" not in n]
    if font is None:
        notes.append(tr("Die Schrift dieser Datei lässt sich nicht neu schreiben (z. B. Type3 aus Chrome) – die Zeile "
                        "wurde in {0} neu gesetzt.").format(use[1]))
    if line.in_layer:
        notes.append(tr("Der Text lag in einer Ebene – die neue Zeile gehört nicht mehr zu dieser Ebene."))
    return out, notes


def delete_line(doc, page_index: int, line: TextLine):
    import pypdfium2.raw as r
    page = doc[page_index]
    try:
        for o in [r.FPDFPage_GetObject(page.raw, i) for i in line.objs]:
            r.FPDFPage_RemoveObject(page.raw, o)
            r.FPDFPageObj_Destroy(o)
        r.FPDFPage_GenerateContent(page.raw)
    finally:
        page.close()


# --------------------------------------------------------------------------- #
# Ebenen
# --------------------------------------------------------------------------- #
@dataclass
class LayerMap:
    """Per layer: extent on the page and coverage mask (for mouse selection)."""
    page: int
    scale: float
    boxes: dict = field(default_factory=dict)     # key -> (x0, y0, x1, y1) pt
    masks: dict = field(default_factory=dict)     # key -> numpy bool (page area)
    page_box: tuple = (0, 0, 0, 0)


def layer_map(data: bytes, page_index: int, keys: list[str] | None = None, max_side: int = 900) -> LayerMap:
    """Render every layer separately (page generously enlarged) -> position and coverage per layer."""
    import numpy as np
    import pikepdf
    import pypdfium2 as pdfium
    pdf = pikepdf.open(io.BytesIO(data))
    try:
        ocp = pdf.Root.get("/OCProperties")
        if ocp is None:
            return LayerMap(page_index, 1.0)
        ocgs = list(ocp.OCGs)
        if keys is not None:
            ocgs = [g for g in ocgs if preflight._key(g) in keys]
        pg = pdf.pages[page_index]
        x0, y0, x1, y1 = [float(v) for v in (pg.obj.get("/CropBox") or pg.MediaBox)]
        w, h = x1 - x0, y1 - y0
        big = [x0 - w, y0 - h, x1 + w, y1 + h]
    finally:
        pdf.close()
    scale = max_side / (3 * max(w, h))
    lm = LayerMap(page_index, scale, page_box=(x0, y0, x1, y1))

    def render(on_keys):
        pdf = pikepdf.open(io.BytesIO(data))
        try:
            ocp = pdf.Root.OCProperties
            tgt = [g for g in ocp.OCGs if preflight._key(g) in on_keys]
            d = ocp.get("/D") or pikepdf.Dictionary()
            ocp.D = d
            d.BaseState = pikepdf.Name.OFF
            d.ON = pikepdf.Array(tgt)
            d.OFF = pikepdf.Array()
            if "/AS" in d:
                del d["/AS"]
            keep = pdf.pages[page_index]
            keep.MediaBox = big
            keep.CropBox = big
            buf = io.BytesIO()
            pdf.save(buf)
        finally:
            pdf.close()
        doc = pdfium.PdfDocument(buf.getvalue())
        try:
            return doc[page_index].render(scale=scale, fill_color=(255, 255, 255, 0)).to_numpy().astype(np.int16)
        finally:
            doc.close()

    # base content (no layer visible) as reference – only what the layer changes is counted
    base = render(set())
    for g_key in [preflight._key(g) for g in ocgs]:
        img = render({g_key})
        a = np.abs(img - base).max(axis=2) > 24
        if not a.any():
            continue
        ys, xs = np.where(a)
        bx0 = big[0] + xs.min() / scale
        bx1 = big[0] + (xs.max() + 1) / scale
        by1 = big[3] - ys.min() / scale
        by0 = big[3] - (ys.max() + 1) / scale
        lm.boxes[g_key] = (float(bx0), float(by0), float(bx1), float(by1))
        lm.masks[g_key] = (a, big)
    return lm


def layers_at(lm: LayerMap, x: float, y: float, tol_pt: float = 3.0) -> list[str]:
    """Ebenen mit Inhalt an diesem Punkt (± Toleranz)."""
    out = []
    for k, (a, big) in lm.masks.items():
        col = int((x - big[0]) * lm.scale)
        row = int((big[3] - y) * lm.scale)
        t = max(1, int(tol_pt * lm.scale))
        r0, r1, c0, c1 = max(0, row - t), min(a.shape[0], row + t + 1), max(0, col - t), min(a.shape[1], col + t + 1)
        if r0 < r1 and c0 < c1 and a[r0:r1, c0:c1].any():
            out.append(k)
    return out


def set_visible(data: bytes, key: str, visible: bool) -> bytes:
    rep = preflight.analyze(data, deep_layers=False)
    st = {L.key: (L.view_on, L.view_on if L.print_on is None else L.print_on) for L in rep.layers}
    st[key] = (visible, visible)
    return preflight.set_layer_states(data, st)


def _layer_props(res, key):
    """Namen in /Properties, die auf diese Ebene zeigen."""
    names = set()
    props = res.get("/Properties") or {}
    for n, oc in props.items():
        if any(preflight._key(g) == key for g in preflight._ocgs_of(oc)):
            names.add(n)
    return names


def _matches(oc, key) -> bool:
    return oc is not None and any(preflight._key(g) == key for g in preflight._ocgs_of(oc))


def transform_layer(data: bytes, key: str, scale: float = 1.0, dx: float = 0.0, dy: float = 0.0,
                    origin: tuple = (0.0, 0.0), pages: list[int] | None = None) -> bytes:
    """Ebeneninhalt skalieren (um origin) und verschieben (pt). pages: None = alle Seiten."""
    import pikepdf
    ox, oy = float(origin[0]), float(origin[1])
    scale, dx, dy = float(scale), float(dx), float(dy)
    page_cm = (scale, 0.0, 0.0, scale, ox - scale * ox + dx, oy - scale * oy + dy)
    I = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    pdf = pikepdf.open(io.BytesIO(data))
    try:
        for pi, page in enumerate(pdf.pages):
            if pages is not None and pi not in pages:
                continue
            res = preflight._resources(page)
            props = res.get("/Properties") or {}
            xo = res.get("/XObject") or {}
            out, stack = [], []
            ctm, gstack = I, []
            for ins in pikepdf.parse_content_stream(page):
                op = str(getattr(ins, "operator", ""))
                operands = getattr(ins, "operands", [])
                if op == "q":
                    gstack.append(ctm)
                elif op == "Q":
                    ctm = gstack.pop() if gstack else I
                elif op == "cm":
                    v = _num_ops(ins)
                    if len(v) == 6:
                        ctm = _mmul(tuple(v), ctm)
                cm = _local_cm(ctm, page_cm)
                if op in ("BDC", "BMC"):
                    hit = False
                    if op == "BDC" and len(operands) >= 2 and operands[0] == pikepdf.Name.OC:
                        oc = props.get(operands[1]) if isinstance(operands[1], pikepdf.Name) else operands[1]
                        hit = _matches(oc, key)
                    out.append(ins)
                    if hit:
                        out.append(pikepdf.ContentStreamInstruction([], pikepdf.Operator("q")))
                        out.append(pikepdf.ContentStreamInstruction(cm, pikepdf.Operator("cm")))
                    stack.append(hit)
                    continue
                if op == "EMC":
                    if stack and stack.pop():
                        out.append(pikepdf.ContentStreamInstruction([], pikepdf.Operator("Q")))
                    out.append(ins)
                    continue
                if op == "Do" and operands and operands[0] in xo and _matches(xo[operands[0]].get("/OC"), key):
                    out += [pikepdf.ContentStreamInstruction([], pikepdf.Operator("q")),
                            pikepdf.ContentStreamInstruction(cm, pikepdf.Operator("cm")), ins,
                            pikepdf.ContentStreamInstruction([], pikepdf.Operator("Q"))]
                    continue
                out.append(ins)
            page.obj.Contents = pikepdf.Stream(pdf, pikepdf.unparse_content_stream(out))
        buf = io.BytesIO()
        pdf.save(buf)
        return buf.getvalue()
    finally:
        pdf.close()


def replace_layer(data: bytes, key: str, page_index: int, src: bytes, src_page: int = 0,
                  box: tuple | None = None) -> bytes:
    """Replace this page's layer content with a page from another PDF (fitted into the box or the page).
        The new content belongs to the layer again (stays toggleable).
    """
    import pikepdf
    pdf = pikepdf.open(io.BytesIO(data))
    try:
        page = pdf.pages[page_index]
        res = preflight._resources(page)
        props = res.get("/Properties")
        if props is None:
            props = res.Properties = pikepdf.Dictionary()
        names = _layer_props(res, key)
        # alten Inhalt der Ebene auf dieser Seite entfernen
        out, stack, skip = [], [], 0
        for ins in pikepdf.parse_content_stream(page):
            op = str(getattr(ins, "operator", ""))
            operands = getattr(ins, "operands", [])
            if skip:
                if op in ("BDC", "BMC"):
                    skip += 1
                elif op == "EMC":
                    skip -= 1
                continue
            if op == "BDC" and len(operands) >= 2 and operands[0] == pikepdf.Name.OC:
                oc = props.get(operands[1]) if isinstance(operands[1], pikepdf.Name) else operands[1]
                if _matches(oc, key):
                    skip = 1
                    continue
            out.append(ins)
        # property name for the layer
        ocg = next(g for g in pdf.Root.OCProperties.OCGs if preflight._key(g) == key)
        name = next(iter(sorted(names)), None)
        if name is None:
            name = pikepdf.Name("/PMOC")
            props[name] = ocg
        # Quellseite als Form-XObject
        spdf = pikepdf.open(io.BytesIO(src))
        try:
            form = pdf.copy_foreign(spdf.pages[src_page].as_form_xobject())
            sx0, sy0, sx1, sy1 = [float(v) for v in spdf.pages[src_page].MediaBox]
        finally:
            spdf.close()
        xo = res.get("/XObject")
        if xo is None:
            xo = res.XObject = pikepdf.Dictionary()
        xname = pikepdf.Name("/PMRepl%d" % len(xo))
        xo[xname] = form
        if box is None:
            box = [float(v) for v in (page.obj.get("/CropBox") or page.MediaBox)]
        bx0, by0, bx1, by1 = (float(v) for v in box)
        sw, sh = sx1 - sx0, sy1 - sy0
        s = min((bx1 - bx0) / sw, (by1 - by0) / sh)
        tx = bx0 + ((bx1 - bx0) - sw * s) / 2 - sx0 * s
        ty = by0 + ((by1 - by0) - sh * s) / 2 - sy0 * s
        add = pikepdf.parse_content_stream(pikepdf.Stream(pdf, (
            f"/OC {name} BDC q {s:.6f} 0 0 {s:.6f} {tx:.3f} {ty:.3f} cm {xname} Do Q EMC").encode()))
        q_, Q_ = (pikepdf.ContentStreamInstruction([], pikepdf.Operator(n)) for n in ("q", "Q"))
        page.obj.Contents = pikepdf.Stream(pdf, pikepdf.unparse_content_stream([q_] + out + [Q_] + list(add)))
        buf = io.BytesIO()
        pdf.save(buf)
        return buf.getvalue()
    finally:
        pdf.close()
