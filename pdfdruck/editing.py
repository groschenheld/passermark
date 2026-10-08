# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Bearbeiten-Modus: Textzeilen ändern (Text, Schrift, Größe) und Ebenen bearbeiten.

Text (pdfium, direkt im geöffneten Dokument):
  Textobjekte einer Seite werden zu Zeilen gruppiert (gleiche Schrift/Größe, gleiche Grundlinie, kleiner Abstand).
  Nur Text ändern: das erste Objekt behält Schrift, Farbe, Lage und Ebene; die übrigen Objekte der Zeile entfallen.
  Schrift ändern: neues Textobjekt an gleicher Stelle (pdfium kann die Schrift eines Objekts nicht tauschen) –
  liegt die Zeile in einer Ebene, ist der neue Text danach nicht mehr Teil dieser Ebene (wird gemeldet).
Ebenen (pikepdf, Bytes -> Bytes): Lage/Ausdehnung je Seite, Treffer an einer Stelle, ein-/ausblenden,
  entfernen, skalieren/verschieben, Inhalt durch eine Seite aus einer anderen PDF ersetzen.
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


def text_lines(doc, page_index: int) -> list[TextLine]:
    """Textobjekte der Seite (oberste Ebene) zu Zeilen gruppieren."""
    import pypdfium2.raw as r
    page = doc[page_index]
    tp = page.get_textpage()
    items = []
    try:
        ordinal = -1
        for i in range(r.FPDFPage_CountObjects(page.raw)):
            o = r.FPDFPage_GetObject(page.raw, i)
            if r.FPDFPageObj_GetType(o) != r.FPDF_PAGEOBJ_TEXT:
                continue
            ordinal += 1
            t = _obj_text(o, tp.raw)
            if not t.strip():
                continue
            items.append((i, t, _font_name(o), _size(o), _bounds(o), _marked(o), ordinal))
    finally:
        tp.close()
        page.close()
    lines: list[TextLine] = []
    for i, t, font, size, (x0, y0, x1, y1), mk, ordn in items:
        if lines:
            L = lines[-1]
            h = max(1.0, L.bbox[3] - L.bbox[1])
            # liegt das Objekt im Zeilenband? (auch kleine Zeichen wie „.“ oder „-“, die nicht die volle Höhe haben)
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
        lines.append(TextLine(len(lines), [i], t, font, size, (x0, y0, x1, y1), mk, "+" in font[:8], [ordn]))
    # Zeilentext aus pdfiums Textauswertung über den Zeilenbereich (echte Wortabstände statt geratener;
    # wichtig z. B. bei Chrome-PDFs, die jeden Buchstaben einzeln setzen)
    page = doc[page_index]
    tp = page.get_textpage()
    try:
        for k, L in enumerate(lines):
            L.index = k
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
    """UTF-16-Zeiger für pdfium (Puffer bleibt bis zum nächsten Aufruf erhalten)."""
    buf = ctypes.create_string_buffer((text + "\0").encode("utf-16-le"))
    _wide_keep[:] = [buf]
    return ctypes.cast(buf, ctypes.POINTER(ctypes.c_ushort))


def edit_line(doc, page_index: int, line: TextLine, new_text: str, font: tuple | None = None,
              size: float | None = None) -> list[str]:
    """Zeile ändern. font: None (Originalschrift) | ("std", "Helvetica") | ("file", "/pfad/schrift.ttf").
    Liefert Hinweise. Ändert das Dokument direkt (danach neu rendern)."""
    import pypdfium2.raw as r
    notes = []
    page = doc[page_index]
    try:
        objs = [r.FPDFPage_GetObject(page.raw, i) for i in line.objs]
        first = objs[0]
        if font is None and (size is None or abs(size - line.size) < 0.01):
            # nur Text: erstes Objekt behält Schrift, Farbe, Lage, Ebene
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


def transform_line(doc, page_index: int, line: TextLine, scale: float = 1.0, dx: float = 0.0, dy: float = 0.0,
                   origin: tuple = (0.0, 0.0)):
    """Zeile verschieben/skalieren (um origin). Schrift, Farbe und Ebene bleiben erhalten."""
    import pypdfium2.raw as r
    ox, oy = float(origin[0]), float(origin[1])
    s = float(scale)
    page = doc[page_index]
    try:
        for o in [r.FPDFPage_GetObject(page.raw, i) for i in line.objs]:
            r.FPDFPageObj_Transform(o, s, 0.0, 0.0, s, ox - s * ox + float(dx), oy - s * oy + float(dy))
        r.FPDFPage_GenerateContent(page.raw)
    finally:
        page.close()


SHOW_OPS = {"Tj", "TJ", "'", '"'}
STATE_OPS = {"Tf", "Tc", "Tw", "Tz", "TL", "Ts", "Tr", "rg", "RG", "g", "G", "k", "K", "cs", "CS", "sc", "SC", "scn",
             "SCN", "gs", "w", "J", "j", "M", "d", "ri", "i"}


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
    """Seiten-Transformation in das an dieser Stelle gültige Koordinatensystem umrechnen: CTM · T · CTM⁻¹."""
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
    """Zeile verschieben/skalieren OHNE die Seite neu zu erzeugen.

    Die Textbefehle der Zeile werden aus ihrem Textblock (BT…ET) herausgelöst und mit q/cm/Q umschlossen; davor und
    danach wird der Block an exakt derselben Textposition fortgesetzt (Zeilenmatrix wird mitgerechnet). Alles andere
    bleibt unverändert. Funktioniert auch mit Type3-Schriften (z. B. Chrome-PDFs), die pdfium nicht neu schreiben kann.
    None, wenn ein Teil ohne eigene Positionierung direkt an fremden Text anschließt (dann Rückfall)."""
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
        # 2) Abschnitte bilden: zusammenhängende Läufe mit Zieltext innerhalb eines BT-Blocks
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
                # nach dem Abschnitt: nächste Ausgabe braucht eine eigene Positionierung
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


def verify_edit(before: bytes, after: bytes, page_index: int, ignore_boxes: list) -> str:
    """Prüfen, dass außerhalb der bearbeiteten Bereiche nichts verloren ging (Bildpunkte und Zeichen).
    Liefert "" oder eine Fehlerbeschreibung."""
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
    import pikepdf
    targets = set(line.tops)
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


def _line_style(data: bytes, page_index: int, line: TextLine):
    """Lage (Seitenkoordinaten, inkl. Schriftgröße-Bezug) und Farbe des ersten Objekts der Zeile."""
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
    """Neue Textzeile ÜBER die Seite legen (eigene kleine Form), ohne den Seiteninhalt neu zu erzeugen."""
    import pikepdf
    import pypdfium2 as pdfium
    import pypdfium2.raw as r
    # 1) Zeile in einer leeren Hilfsseite gleicher Größe erzeugen (pdfium darf hier frei schreiben)
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
    """Bereich, in dem sich eine geänderte Zeile verändern darf: ihre Höhe (+30 %), ganze Seitenbreite."""
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
    """Zeile ändern, sicher: zuerst direkt (pdfium); verliert die Seite dabei Inhalt (z. B. Type3-Schriften aus
    Chrome), wird die alte Zeile entfernt und die neue darübergelegt – die übrige Seite bleibt unverändert."""
    import pypdfium2 as pdfium
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
    # Rückfall: überlagern
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
    """Je Ebene: Ausdehnung auf der Seite und Deckungsmaske (für Mausauswahl)."""
    page: int
    scale: float
    boxes: dict = field(default_factory=dict)     # Schlüssel -> (x0, y0, x1, y1) pt
    masks: dict = field(default_factory=dict)     # Schlüssel -> numpy bool (Seitenbereich)
    page_box: tuple = (0, 0, 0, 0)


def layer_map(data: bytes, page_index: int, keys: list[str] | None = None, max_side: int = 900) -> LayerMap:
    """Jede Ebene einzeln rendern (Seite großzügig erweitert) -> Lage und Deckung je Ebene."""
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

    # Grundinhalt (keine Ebene sichtbar) als Vergleich – gezählt wird nur, was die Ebene ändert
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
    """Ebeneninhalt dieser Seite durch eine Seite einer anderen PDF ersetzen (eingepasst in box bzw. Seite).
    Der neue Inhalt gehört wieder zur Ebene (bleibt ein-/ausblendbar)."""
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
        # Eigenschaftsname für die Ebene
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
