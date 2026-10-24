# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Preflight: check a document (fonts, layers, transparency, characters) and repair it in a targeted way.

The original is never modified – all functions work on bytes and return new bytes.

Analysis:
  Fonts        embedded / subset / not embedded, type (TrueType, Type1, CID, Type3), ToUnicode,
               standard-14, on which pages; replacement suggestion (metrically compatible free fonts)
  Characters   pages with unreadable characters (no valid Unicode mapping)
  Layers       optional content: state for view and print, pages, content outside the page
  Transparency soft masks, blend modes, opacity, transparency groups, overprint
Repairs:
  set the layer state, flatten layers (visible state, marker removed), remove layers,
  embed fonts (with replacements), text to paths, reduce transparency (Ghostscript),
  transparent gradients (soft mask in patterns) to opaque images (softmask.py, without Ghostscript)
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field

from . import platform as _platform
from .l10n import tr

STANDARD14 = {"Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique", "Helvetica", "Helvetica-Bold",
              "Helvetica-Oblique", "Helvetica-BoldOblique", "Times-Roman", "Times-Bold", "Times-Italic",
              "Times-BoldItalic", "Symbol", "ZapfDingbats"}

# Metrisch kompatible freie Ersatzschriften (gleiche Zeichenbreiten -> Text verrutscht nicht)
METRIC = [
    (r"arial|helvetica|arimo", "Liberation Sans"),
    (r"timesnewroman|times|tinos", "Liberation Serif"),
    (r"couriernew|courier|cousine", "Liberation Mono"),
    (r"calibri", "Carlito"),
    (r"cambria", "Caladea"),
    (r"isocp|isoct|isocpeur|isocteur", "osifont"),
    (r"^symbol$|symbolmt", "Standard Symbols PS"),
    (r"zapfdingbats", "D050000L"),
    (r"verdana", "DejaVu Sans"),
    (r"tahoma|segoeui", "DejaVu Sans"),
    (r"georgia", "Gelasio"),
]

SEV_ORDER = {"error": 0, "warning": 1, "info": 2}


@dataclass
class Spot:
    """Eine Fundstelle: Seite (1-basiert), optional der Bereich auf der Seite (pt, Seitenkoordinaten)."""
    page: int
    box: tuple | None = None
    label: str = ""            # was genau dort ist („72 dpi, 400 × 300 px“, Schriftname …)


@dataclass
class Issue:
    severity: str              # error | warning | info
    category: str              # font | layer | transparency | text | image
    message: str
    pages: list = field(default_factory=list)
    spots: list = field(default_factory=list)   # [Spot] – wo genau (leer: nur die Seiten)


@dataclass
class FontInfo:
    key: str
    name: str                  # without subset prefix
    raw: str
    subtype: str
    embedded: bool
    subset: bool
    tounicode: bool
    encoding: str
    cid: bool
    standard14: bool
    pages: set = field(default_factory=set)
    suggestion: str = ""       # Pfad der Ersatzschrift
    suggestion_name: str = ""

    @property
    def status(self) -> str:
        if self.subtype == "Type3":
            return "type3"
        if self.embedded:
            return "ok"
        if self.standard14:
            return "std14"
        return "missing"


@dataclass
class LayerInfo:
    key: str
    name: str
    view_on: bool
    print_on: bool | None      # None = keine eigene Druck-Einstellung (folgt der Ansicht)
    locked: bool = False
    pages: set = field(default_factory=set)
    outside_pct: float | None = None


@dataclass
class Report:
    pages: int = 0
    fonts: list = field(default_factory=list)
    layers: list = field(default_factory=list)
    transparency: dict = field(default_factory=dict)   # Seite -> {Art}
    garbled: dict = field(default_factory=dict)        # Seite -> Anzahl
    hdr: list = field(default_factory=list)            # HDR-Foto: [{"main": i, "aux": j, …}] (0-basiert)
    colors: object = None                              # imagecheck.ColorReport: Bilder (dpi, Farbraum), Farben
    size: object = None                                # shrink.SizeReport: wofür der Platz draufgeht
    issues: list = field(default_factory=list)
    boxes: dict = field(default_factory=dict)          # Seite -> MediaBox (x0, y0, x1, y1) – für „wo auf der Seite“
    located: dict = field(default_factory=dict)        # ("font", Name) / ("transparency",) -> {Seite: [Bereich]}

    def counts(self):
        c = {"error": 0, "warning": 0, "info": 0}
        for i in self.issues:
            c[i.severity] += 1
        return c


# --------------------------------------------------------------------------- #
# Hilfen
# --------------------------------------------------------------------------- #
def _key(obj) -> str:
    try:
        og = obj.objgen
        if og != (0, 0):
            return f"{og[0]} {og[1]}"
    except Exception:
        pass
    return f"id{id(obj)}"


def _resources(page):
    import pikepdf
    node = page.obj
    while node is not None:
        if "/Resources" in node:
            return node.Resources
        node = node.get("/Parent")
    return pikepdf.Dictionary()


def _pages_str(pages) -> str:
    ps = sorted(pages)
    if not ps:
        return ""
    out, start, prev = [], ps[0], ps[0]
    for p in ps[1:] + [None]:
        if p is not None and p == prev + 1:
            prev = p
            continue
        out.append(f"{start}" if start == prev else f"{start}–{prev}")
        if p is not None:
            start = prev = p
    return ", ".join(out[:8]) + (" …" if len(out) > 8 else "")


def _walk_resources(res, page_no, visit, seen):
    """Ressourcen inkl. Form-XObjects (verschachtelt) besuchen."""
    import pikepdf
    if res is None:
        return
    rk = _key(res)
    if rk in seen:
        return
    seen.add(rk)
    visit(res, page_no)
    xo = res.get("/XObject")
    if xo is not None:
        for _n, x in xo.items():
            try:
                if x.get("/Subtype") == pikepdf.Name.Form:
                    _walk_resources(x.get("/Resources"), page_no, visit, seen)
            except Exception:
                pass


# --------------------------------------------------------------------------- #
# Analyse
# --------------------------------------------------------------------------- #
def analyze(data: bytes, deep_layers: bool = True, pdfium_parts: bool = True) -> Report:
    """Check the document. pdfium_parts=False: only the parts without pdfium (for background threads – pdfium is not
        thread-safe); complete the rest afterwards in the main thread with finish().
    """
    import pikepdf
    rep = Report()
    pdf = pikepdf.open(io.BytesIO(data))
    try:
        rep.pages = len(pdf.pages)
        fonts: dict[str, FontInfo] = {}
        trans: dict[int, set] = {}

        def visit(res, pno):
            for _n, f in (res.get("/Font") or {}).items():
                k = _key(f)
                if k not in fonts:
                    fonts[k] = _font_info(f, k)
                fonts[k].pages.add(pno)
            for _n, gs in (res.get("/ExtGState") or {}).items():
                sm = gs.get("/SMask")
                if sm is not None and str(sm) != "/None":
                    trans.setdefault(pno, set()).add("smask")
                bm = gs.get("/BM")
                if bm is not None:
                    names = [str(b) for b in (bm if isinstance(bm, pikepdf.Array) else [bm])]
                    if any(n not in ("/Normal", "/Compatible") for n in names):
                        trans.setdefault(pno, set()).add("blend")
                for k in ("/CA", "/ca"):
                    try:
                        if k in gs and float(gs[k]) < 0.999:
                            trans.setdefault(pno, set()).add("alpha")
                    except Exception:
                        pass
                if gs.get("/OP") is True or gs.get("/op") is True:
                    trans.setdefault(pno, set()).add("overprint")
            for _n, pat in (res.get("/Pattern") or {}).items():
                # Verlauf mit Soft-Maske im Muster (Chrome/Skia, Canva …): RIPs, die die Maske ignorieren,
                # drucken ihn als schwarze Fläche – darunterliegende Bilder verschwinden
                try:
                    from .softmask import pattern_has_softmask
                    if pattern_has_softmask(pat):
                        trans.setdefault(pno, set()).add("pattern_smask")
                except Exception:
                    pass
            for _n, x in (res.get("/XObject") or {}).items():
                try:
                    if x.get("/Subtype") == pikepdf.Name.Image and "/SMask" in x:
                        trans.setdefault(pno, set()).add("image_alpha")
                    if x.get("/Subtype") == pikepdf.Name.Form and "/Group" in x:
                        if x.Group.get("/S") == pikepdf.Name.Transparency:
                            trans.setdefault(pno, set()).add("group")
                except Exception:
                    pass

        for i, page in enumerate(pdf.pages, start=1):
            try:
                rep.boxes[i] = tuple(float(v) for v in page.MediaBox)
            except Exception:
                pass
            seen = set()
            _walk_resources(_resources(page), i, visit, seen)
            for a in page.obj.get("/Annots") or []:
                try:
                    ap = a.get("/AP")
                    n = ap.get("/N") if ap is not None else None
                    if isinstance(n, pikepdf.Stream):
                        _walk_resources(n.get("/Resources"), i, visit, seen)
                except Exception:
                    pass
            g = page.obj.get("/Group")
            if g is not None and g.get("/S") == pikepdf.Name.Transparency:
                trans.setdefault(i, set()).add("group")
        rep.fonts = sorted(fonts.values(), key=lambda f: (f.status == "ok", f.name.lower()))
        for f in rep.fonts:
            if f.status in ("missing", "std14") and f.encoding != "private" and not (f.cid and f.encoding.startswith("Identity")):
                f.suggestion, f.suggestion_name = suggest_font(f.name)
        flagged = [p for p, k in trans.items() if "pattern_smask" in k]
        if flagged:                     # nur melden, wo wirklich damit gemalt wird (nach Reparatur: nicht mehr)
            try:
                from .softmask import scan
                painted = {t.page + 1 for t in scan(pdf).targets}
                for p in flagged:
                    if p not in painted:
                        trans[p].discard("pattern_smask")
                        trans[p].add("smask")
            except Exception:
                pass
        rep.transparency = trans
        rep.layers = _layers(pdf)
        try:
            rep.hdr = hdr_aux_pages(pdf)
        except Exception:
            rep.hdr = []
        try:
            from . import imagecheck
            rep.colors = imagecheck.analyze(pdf)
        except Exception:
            rep.colors = None
        try:
            from . import shrink
            rep.size = shrink.analyze(data, pdf, rep.colors)
        except Exception:
            rep.size = None
    finally:
        pdf.close()
    if pdfium_parts:
        finish(rep, data, deep_layers)
    else:
        rep.issues = _issues(rep)
    return rep


def finish(rep: Report, data: bytes, deep_layers: bool = True) -> Report:
    """pdfium parts of the check (strange characters, layers outside the page) – call in the main thread."""
    rep.garbled = _garbled(data)
    try:
        rep.located = _locate(data, rep)
    except Exception:
        rep.located = {}
    if deep_layers and rep.layers:
        try:
            _layers_outside(data, rep.layers)
        except Exception:
            pass
    rep.issues = _issues(rep)
    return rep


def _font_info(f, k) -> FontInfo:
    import pikepdf
    raw = str(f.get("/BaseFont", "/?"))[1:]
    subset = bool(re.match(r"^[A-Z]{6}\+", raw))
    name = raw.split("+", 1)[1] if subset else raw
    subtype = str(f.get("/Subtype", "/?"))[1:]
    cid = subtype == "Type0"
    desc = None
    if cid:
        try:
            d = f.DescendantFonts[0]
            desc = d.get("/FontDescriptor")
        except Exception:
            desc = None
    else:
        desc = f.get("/FontDescriptor")
    embedded = subtype == "Type3" or (desc is not None and any(k in desc for k in ("/FontFile", "/FontFile2", "/FontFile3")))
    enc = f.get("/Encoding")
    encoding = str(enc)[1:] if isinstance(enc, pikepdf.Name) else ("custom" if enc is not None else "")
    if isinstance(enc, pikepdf.Dictionary):
        # eigene Glyphennamen (g01, glyph12, cid45 …) -> Zeichenbedeutung nur in der Originalschrift
        names = [str(x) for x in (enc.get("/Differences") or []) if isinstance(x, pikepdf.Name)]
        if names and sum(bool(re.match(r"^/(g|glyph|cid|G|uni)?[0-9A-Fa-f]{1,5}$", n)) for n in names) > 0.5 * len(names):
            encoding = "private"
    return FontInfo(k, name, raw, subtype, embedded, subset, "/ToUnicode" in f, encoding, cid,
                    name in STANDARD14 and subtype == "Type1")


def _locate(data: bytes, rep: Report, max_pages: int = 300, max_objs: int = 4000) -> dict:
    """Wo genau? Text-Objekte je nicht eingebetteter/auffälliger Schrift und Objekte mit Transparenz – Bereiche je
        Seite (pdfium, Seitenkoordinaten). Nur für Schriften, zu denen es einen Befund gibt."""
    import ctypes
    import pypdfium2 as pdfium
    import pypdfium2.raw as r
    want = {f.name for f in rep.fonts if f.status in ("missing", "std14", "type3") or not f.tounicode}
    tpages = set(rep.transparency)
    if not want and not tpages:
        return {}
    get_name = getattr(r, "FPDFFont_GetBaseFontName", None) or getattr(r, "FPDFFont_GetFontName", None)
    has_tr = getattr(r, "FPDFPageObj_HasTransparency", None)
    out: dict = {}
    doc = pdfium.PdfDocument(data)
    order = _text_fonts_in_order(data) if want else {}
    try:
        pages = sorted({p for f in rep.fonts if f.name in want for p in f.pages} | tpages)[:max_pages]
        for p in pages:
            if not 1 <= p <= len(doc):
                continue
            pg = doc[p - 1]
            try:
                n = min(r.FPDFPage_CountObjects(pg.raw), max_objs)
                n_text = sum(1 for k in range(n) if r.FPDFPageObj_GetType(r.FPDFPage_GetObject(pg.raw, k))
                             == r.FPDF_PAGEOBJ_TEXT)
                seq = order.get(p) or []
                use_seq = len(seq) == n_text                 # je Textobjekt die Schrift laut Inhaltsstrom
                ti = -1
                for k in range(n):
                    obj = r.FPDFPage_GetObject(pg.raw, k)
                    typ = r.FPDFPageObj_GetType(obj)
                    l, b, rr, t = (ctypes.c_float() for _ in range(4))
                    if not r.FPDFPageObj_GetBounds(obj, ctypes.byref(l), ctypes.byref(b), ctypes.byref(rr),
                                                   ctypes.byref(t)):
                        continue
                    box = (l.value, b.value, rr.value, t.value)
                    if has_tr is not None and p in tpages and has_tr(obj):
                        out.setdefault(("transparency",), {}).setdefault(p, []).append(box)
                    if typ == r.FPDF_PAGEOBJ_TEXT:
                        ti += 1
                    if typ == r.FPDF_PAGEOBJ_TEXT and want:
                        if use_seq:
                            name = seq[ti]
                        else:                              # pdfium nennt bei Ersatzschriften oft den Ersatz
                            if get_name is None:
                                continue
                            font = r.FPDFTextObj_GetFont(obj)
                            size = get_name(font, None, 0) if font else 0
                            if not size:
                                continue
                            buf = ctypes.create_string_buffer(size)
                            get_name(font, buf, size)
                            name = buf.value.decode("latin-1", "replace")
                        name = name.split("+", 1)[1] if re.match(r"^[A-Z]{6}\+", name) else name
                        if name in want:
                            out.setdefault(("font", name), {}).setdefault(p, []).append(box)
            finally:
                pg.close()
    finally:
        doc.close()
    return out


def _text_fonts_in_order(data: bytes) -> dict:
    """Seite -> [Schriftname je Text-Ausgabe (Tj, TJ, ', ")] in der Reihenfolge des Inhaltsstroms der Seite
        (ohne Formulare) – so viele, wie pdfium Textobjekte direkt auf der Seite hat."""
    import pikepdf
    out = {}
    pdf = pikepdf.open(io.BytesIO(data))
    try:
        for i, page in enumerate(pdf.pages, start=1):
            fonts = (_resources(page).get("/Font") or {}) if _resources(page) is not None else {}
            cur, seq = "", []
            try:
                ops = pikepdf.parse_content_stream(page)
            except Exception:
                continue
            for ins in ops:
                op = str(getattr(ins, "operator", ""))
                if op == "Tf" and ins.operands:
                    f = fonts.get(str(ins.operands[0]))
                    raw = str(f.get("/BaseFont", "/?"))[1:] if f is not None else ""
                    cur = raw.split("+", 1)[1] if re.match(r"^[A-Z]{6}\+", raw) else raw
                elif op in ("Tj", "TJ", "'", '"'):
                    seq.append(cur)
            out[i] = seq
    finally:
        pdf.close()
    return out


def _merge_boxes(boxes: list, limit: int = 6) -> list:
    """Viele Kästen einer Seite (z. B. jede Textzeile) zu wenigen zusammenfassen: nahe beieinander -> ein Bereich."""
    out = []
    for b in sorted(boxes, key=lambda b: (-b[3], b[0])):
        for i, m in enumerate(out):
            if b[0] <= m[2] + 20 and b[2] >= m[0] - 20 and b[1] <= m[3] + 20 and b[3] >= m[1] - 20:
                out[i] = (min(m[0], b[0]), min(m[1], b[1]), max(m[2], b[2]), max(m[3], b[3]))
                break
        else:
            out.append(tuple(b))
    if len(out) > limit:
        out = [(min(b[0] for b in out), min(b[1] for b in out), max(b[2] for b in out), max(b[3] for b in out))]
    return out


def where_text(rep: Report, spot: Spot) -> str:
    """„Seite 3 – oben links, 40 × 20 mm“ (Lage im Seitendrittel, Größe) – ohne Bereich nur „Seite 3“."""
    head = tr("Seite {0}").format(spot.page)
    if spot.box is None:
        return head + (f" – {spot.label}" if spot.label else "")
    x0, y0, x1, y1 = spot.box
    mb = rep.boxes.get(spot.page) or (0.0, 0.0, max(x1, 1.0), max(y1, 1.0))
    W, H = (mb[2] - mb[0]) or 1.0, (mb[3] - mb[1]) or 1.0
    cx, cy = ((x0 + x1) / 2 - mb[0]) / W, ((y0 + y1) / 2 - mb[1]) / H
    v = tr("oben") if cy > 2 / 3 else tr("unten") if cy < 1 / 3 else ""
    h = tr("links") if cx < 1 / 3 else tr("rechts") if cx > 2 / 3 else ""
    pos = " ".join(x for x in (v, h) if x) or tr("Mitte")
    size = tr("{0:.0f} × {1:.0f} mm").format((x1 - x0) / MM_PT, (y1 - y0) / MM_PT)
    return f"{head} – {pos}, {size}" + (f" · {spot.label}" if spot.label else "")


MM_PT = 72 / 25.4


def _garbled(data: bytes) -> dict:
    """Pages with characters without a valid Unicode mapping (replacement characters, private use area, control characters)."""
    import pypdfium2 as pdfium
    out = {}
    doc = pdfium.PdfDocument(data)
    try:
        for i in range(len(doc)):
            pg = doc[i]
            tp = pg.get_textpage()
            try:
                t = tp.get_text_range()
            finally:
                tp.close()
                pg.close()
            bad = sum(1 for ch in t if ch == "\ufffd" or "\ue000" <= ch <= "\uf8ff"
                      or (ord(ch) < 32 and ch not in "\r\n\t"))
            if bad >= 3 and bad > 0.02 * max(1, len(t)):
                out[i + 1] = bad
    finally:
        doc.close()
    return out


# --------------------------------------------------------------------------- #
# Ebenen
# --------------------------------------------------------------------------- #
def _ocp(pdf):
    return pdf.Root.get("/OCProperties")


def _layers(pdf) -> list[LayerInfo]:
    import pikepdf
    ocp = _ocp(pdf)
    if ocp is None:
        return []
    d = ocp.get("/D") or pikepdf.Dictionary()
    base_on = d.get("/BaseState", pikepdf.Name.ON) != pikepdf.Name.OFF
    on = {_key(o) for o in d.get("/ON") or []}
    off = {_key(o) for o in d.get("/OFF") or []}
    locked = {_key(o) for o in d.get("/Locked") or []}
    out = {}
    for g in ocp.get("/OCGs") or []:
        k = _key(g)
        view = (k in on) or (base_on and k not in off)
        pr = None
        try:
            ps = g.Usage.Print.PrintState
            pr = ps == pikepdf.Name.ON
        except Exception:
            pass
        out[k] = LayerInfo(k, str(g.get("/Name", "?")), view, pr, k in locked)
    # Seiten je Ebene (BDC /OC in Inhalten und XObjects mit /OC)
    for i, page in enumerate(pdf.pages, start=1):
        res = _resources(page)
        props = res.get("/Properties") or {}
        for kk in _oc_keys_in_stream(page, props, res, set()):
            if kk in out:
                out[kk].pages.add(i)
    return list(out.values())


def _ocgs_of(oc) -> list:
    import pikepdf
    if oc is None:
        return []
    if oc.get("/Type") == pikepdf.Name.OCMD:
        o = oc.get("/OCGs")
        if o is None:
            return []
        return list(o) if isinstance(o, pikepdf.Array) else [o]
    return [oc]


def _oc_keys_in_stream(obj, props, res, seen) -> set:
    import pikepdf
    keys = set()
    try:
        ops = pikepdf.parse_content_stream(obj)
    except Exception:
        return keys
    xo = res.get("/XObject") if res is not None else None
    for ins in ops:
        op = str(getattr(ins, "operator", ""))
        operands = getattr(ins, "operands", [])
        if op == "BDC" and len(operands) >= 2 and operands[0] == pikepdf.Name.OC:
            oc = props.get(operands[1]) if isinstance(operands[1], pikepdf.Name) else operands[1]
            for g in _ocgs_of(oc):
                keys.add(_key(g))
        elif op == "Do" and xo is not None and operands:
            x = xo.get(operands[0])
            if x is None:
                continue
            if "/OC" in x:
                for g in _ocgs_of(x.OC):
                    keys.add(_key(g))
            xk = _key(x)
            if x.get("/Subtype") == pikepdf.Name.Form and xk not in seen:
                seen.add(xk)
                xr = x.get("/Resources") or res
                keys |= _oc_keys_in_stream(x, xr.get("/Properties") or {}, xr, seen)
    return keys


def _layers_outside(data: bytes, layers: list[LayerInfo], max_layers=40, max_pages=6):
    """Per layer: how much of its content lies outside the page? (Rendered individually, page enlarged.)"""
    import numpy as np
    import pikepdf
    import pypdfium2 as pdfium
    for L in layers[:max_layers]:
        if not L.pages:
            continue
        pdf = pikepdf.open(io.BytesIO(data))
        try:
            ocp = _ocp(pdf)
            target = [g for g in ocp.OCGs if _key(g) == L.key]
            if not target:
                continue
            d = ocp.D
            d.BaseState = pikepdf.Name.OFF
            d.ON = pikepdf.Array(target)
            d.OFF = pikepdf.Array()
            if "/AS" in d:
                del d["/AS"]
            pages = sorted(L.pages)[:max_pages]
            boxes = {}
            for p in pages:
                pg = pdf.pages[p - 1]
                x0, y0, x1, y1 = [float(v) for v in (pg.obj.get("/CropBox") or pg.MediaBox)]
                w, h = x1 - x0, y1 - y0
                boxes[p] = (w, h)
                big = [x0 - w, y0 - h, x1 + w, y1 + h]
                pg.MediaBox = big
                pg.CropBox = big
            buf = io.BytesIO()
            pdf.save(buf)
        finally:
            pdf.close()
        doc = pdfium.PdfDocument(buf.getvalue())
        tot = outside = 0
        try:
            for p in pages:
                w, h = boxes[p]
                scale = 160.0 / max(w, h)
                bmp = doc[p - 1].render(scale=scale, fill_color=(255, 255, 255, 0))
                a = bmp.to_numpy()[:, :, 3] > 20
                H, W = a.shape
                ys, xs = slice(H // 3, H - H // 3), slice(W // 3, W - W // 3)
                inner = a[ys, xs].sum()
                total = a.sum()
                tot += total
                outside += total - inner
        finally:
            doc.close()
        L.outside_pct = (100.0 * outside / tot) if tot else None


def _visible(oc, visible: set) -> bool:
    import pikepdf
    if oc is None:
        return True
    if oc.get("/Type") == pikepdf.Name.OCMD:
        groups = [_key(g) for g in _ocgs_of(oc)]
        if not groups:
            return True
        states = [g in visible for g in groups]
        pol = str(oc.get("/P", "/AnyOn"))
        return {"/AllOn": all(states), "/AnyOff": not all(states), "/AllOff": not any(states)}.get(pol, any(states))
    return _key(oc) in visible


def _rewrite(pdf, obj, props, res, visible, strip, done):
    """Inhaltsstrom filtern: unsichtbare OC-Inhalte entfernen; bei strip auch die OC-Marker entfernen."""
    import pikepdf
    ok = _key(obj)
    if ok in done:
        return
    done.add(ok)
    try:
        ops = pikepdf.parse_content_stream(obj)
    except Exception:
        return
    xo = res.get("/XObject") if res is not None else None
    out, stack, skip = [], [], 0
    for ins in ops:
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
            if not _visible(oc, visible):
                skip = 1
                continue
            stack.append("drop" if strip else "keep")
            if not strip:
                out.append(ins)
            continue
        if op in ("BDC", "BMC"):
            stack.append("keep")
        elif op == "EMC":
            if (stack.pop() if stack else "keep") == "drop":
                continue
        elif op == "Do" and xo is not None and operands:
            x = xo.get(operands[0])
            if x is not None:
                if "/OC" in x and not _visible(x.OC, visible):
                    continue
                if x.get("/Subtype") == pikepdf.Name.Form:
                    xr = x.get("/Resources") or res
                    _rewrite(pdf, x, xr.get("/Properties") or {}, xr, visible, strip, done)
                    if strip and "/OC" in x:
                        del x["/OC"]
        out.append(ins)
    data = pikepdf.unparse_content_stream(out)
    if isinstance(obj, pikepdf.Page):
        obj.obj.Contents = pikepdf.Stream(pdf, data)
    else:
        obj.write(data)


def _apply_visibility(pdf, visible: set, strip: bool):
    import pikepdf
    done = set()
    for page in pdf.pages:
        res = _resources(page)
        props = res.get("/Properties") or {}
        _rewrite(pdf, page, props, res, visible, strip, done)
        annots = page.obj.get("/Annots")
        if annots is not None:
            keep = pikepdf.Array([a for a in annots if "/OC" not in a or _visible(a.OC, visible)])
            if strip:
                for a in keep:
                    if "/OC" in a:
                        del a["/OC"]
            page.obj.Annots = keep


def current_visible(pdf, use_print=True) -> set:
    """Visible layers: for printing (print setting, otherwise view) or for the view."""
    vis = set()
    for L in _layers(pdf):
        on = L.print_on if (use_print and L.print_on is not None) else L.view_on
        if on:
            vis.add(L.key)
    return vis


def has_layers(data: bytes) -> bool:
    import pikepdf
    with pikepdf.open(io.BytesIO(data)) as pdf:
        return _ocp(pdf) is not None


def flatten_layers(data: bytes, visible: set | None = None) -> bytes:
    """Pin the visible state: remove hidden layer content, dissolve the layers.
        Afterwards every printer/viewer prints exactly what is visible.
    """
    import pikepdf
    pdf = pikepdf.open(io.BytesIO(data))
    try:
        if _ocp(pdf) is None:
            raise ValueError(tr("Das Dokument hat keine Ebenen."))
        vis = current_visible(pdf) if visible is None else visible
        _apply_visibility(pdf, vis, strip=True)
        del pdf.Root["/OCProperties"]
        out = io.BytesIO()
        pdf.save(out)
        return out.getvalue()
    finally:
        pdf.close()


def remove_layers(data: bytes, keys: set) -> bytes:
    """Remove layers including their content; the remaining layers are preserved."""
    import pikepdf
    pdf = pikepdf.open(io.BytesIO(data))
    try:
        ocp = _ocp(pdf)
        if ocp is None:
            raise ValueError(tr("Das Dokument hat keine Ebenen."))
        all_keys = {_key(g) for g in ocp.OCGs}
        _apply_visibility(pdf, all_keys - set(keys), strip=False)

        def clean(arr):
            out = pikepdf.Array()
            for it in arr:
                if isinstance(it, pikepdf.Array):
                    sub = clean(it)
                    if len(sub):
                        out.append(sub)
                elif isinstance(it, pikepdf.Dictionary) and _key(it) in keys:
                    continue
                else:
                    out.append(it)
            return out
        ocp.OCGs = clean(ocp.OCGs)
        d = ocp.get("/D")
        if d is not None:
            for k in ("/ON", "/OFF", "/Order", "/Locked", "/RBGroups"):
                if k in d:
                    d[k] = clean(d[k])
        if not len(ocp.OCGs):
            del pdf.Root["/OCProperties"]
        out = io.BytesIO()
        pdf.save(out)
        return out.getvalue()
    finally:
        pdf.close()


def set_layer_states(data: bytes, states: dict) -> bytes:
    """states: {key: (view on, print on)} -> set the default state in the document (layers stay)."""
    import pikepdf
    pdf = pikepdf.open(io.BytesIO(data))
    try:
        ocp = _ocp(pdf)
        if ocp is None:
            raise ValueError(tr("Das Dokument hat keine Ebenen."))
        d = ocp.get("/D")
        if d is None:
            d = ocp.D = pikepdf.Dictionary()
        on, off = pikepdf.Array(), pikepdf.Array()
        printers = []
        for g in ocp.OCGs:
            view, prn = states.get(_key(g), (True, True))
            (on if view else off).append(g)
            usage = g.get("/Usage")
            if usage is None:
                usage = g.Usage = pikepdf.Dictionary()
            usage.Print = pikepdf.Dictionary(PrintState=pikepdf.Name.ON if prn else pikepdf.Name.OFF)
            usage.View = pikepdf.Dictionary(ViewState=pikepdf.Name.ON if view else pikepdf.Name.OFF)
            printers.append(g)
        d.BaseState = pikepdf.Name.ON
        d.ON, d.OFF = on, off
        # Druck-Zustand automatisch anwenden (Viewer, die Usage auswerten)
        d.AS = pikepdf.Array([pikepdf.Dictionary(Event=pikepdf.Name.Print, Category=pikepdf.Array([pikepdf.Name.Print]),
                                                 OCGs=pikepdf.Array(printers)),
                              pikepdf.Dictionary(Event=pikepdf.Name.View, Category=pikepdf.Array([pikepdf.Name.View]),
                                                 OCGs=pikepdf.Array(printers))])
        out = io.BytesIO()
        pdf.save(out)
        return out.getvalue()
    finally:
        pdf.close()


# --------------------------------------------------------------------------- #
# Schriften
# --------------------------------------------------------------------------- #
def _norm(name: str) -> tuple[str, bool, bool]:
    """BaseFont -> (Familie normalisiert, fett, kursiv)."""
    n = name.split("+", 1)[-1]
    low = n.lower()
    bold = bool(re.search(r"bold|black|heavy|semibold|demi", low))
    italic = bool(re.search(r"italic|oblique|kursiv", low))
    fam = re.split(r"[,-]", n)[0]
    fam = re.sub(r"(PSMT|MT|PS)$", "", fam)
    fam = re.sub(r"(Bold|Italic|Oblique|Regular)+$", "", fam, flags=re.I)
    return re.sub(r"[^a-z0-9]", "", fam.lower()), bold, italic


def font_dirs() -> list[str]:
    home = os.path.expanduser("~")
    if _platform.IS_WIN:
        win = os.environ.get("WINDIR", r"C:\Windows")
        return [os.path.join(win, "Fonts"), os.path.join(os.environ.get("LOCALAPPDATA", home), "Microsoft", "Windows", "Fonts"),
                user_font_dir()]
    return ["/usr/share/fonts", "/usr/local/share/fonts", os.path.join(home, ".local", "share", "fonts"),
            os.path.join(home, ".fonts"), user_font_dir()]


def user_font_dir() -> str:
    if _platform.IS_WIN:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "Passermark", "fonts")
    return os.path.join(os.path.expanduser("~"), ".local", "share", "fonts", "passermark")


def _fc_match(family: str, bold: bool, italic: bool) -> str:
    fc = shutil.which("fc-match")
    if not fc:
        return ""
    style = ("Bold " if bold else "") + ("Italic" if italic else "")
    pat = family + (f":style={style.strip()}" if style.strip() else "")
    try:
        r = subprocess.run([fc, "-f", "%{family}|%{file}", pat], capture_output=True, text=True, timeout=10)
        fam, _, path = r.stdout.partition("|")
        if path and family.split()[0].lower() in fam.lower().replace(" ", ""):
            return path
        if path and family.lower() in fam.lower():
            return path
    except (OSError, subprocess.SubprocessError):
        pass
    return ""


def _scan_files(family: str, bold: bool, italic: bool) -> str:
    want = re.sub(r"[^a-z0-9]", "", family.lower())
    best, score_best = "", -1
    for d in font_dirs():
        if not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for fn in files:
                if not fn.lower().endswith((".ttf", ".otf")):
                    continue
                base = re.sub(r"[^a-z0-9]", "", fn.lower().rsplit(".", 1)[0])
                if not base.startswith(want):
                    continue
                rest = base[len(want):]
                b, i = "bold" in rest, ("italic" in rest or "oblique" in rest)
                score = (b == bold) * 2 + (i == italic) * 2 - len(rest) / 100
                if score > score_best:
                    best, score_best = os.path.join(root, fn), score
    return best


def find_font_file(family: str, bold=False, italic=False) -> str:
    return _fc_match(family, bold, italic) or _scan_files(family, bold, italic)


def suggest_font(name: str) -> tuple[str, str]:
    """(Pfad, Anzeigename) einer passenden Ersatzschrift – bevorzugt metrisch kompatibel."""
    fam, bold, italic = _norm(name)
    for pat, repl in METRIC:
        if re.search(pat, fam):
            p = find_font_file(repl, bold, italic)
            if p:
                return p, repl + (" Bold" if bold else "") + (" Italic" if italic else "")
    # gleichnamige Schrift im System?
    p = _scan_files(fam, bold, italic)
    if p:
        return p, os.path.basename(p)
    # CAD-Normschriften ohne osifont: schmale serifenlose Ausweichschrift (Breiten bleiben aus dem PDF)
    if re.search(r"isocp|isoct|romans|simplex|txt|cad|norm", fam):
        for fb in ("DejaVu Sans Condensed", "Liberation Sans Narrow", "DejaVu Sans"):
            p = find_font_file(fb, bold, italic)
            if p:
                return p, fb + tr(" (Ausweichschrift)")
    return "", ""


# Kommerzielle Schriften -> freier, metrisch gleicher Zwilling auf fontsource.org (gleiche Zeichenbreiten)
DOWNLOAD_ALIAS = [
    (r"arial|helvetica|arimo", "Arimo"),
    (r"timesnewroman|times|tinos", "Tinos"),
    (r"couriernew|courier|cousine", "Cousine"),
    (r"calibri|carlito", "Carlito"),
    (r"cambria|caladea", "Caladea"),
    (r"georgia|gelasio", "Gelasio"),
    (r"segoeui|tahoma|verdana", "Open Sans"),
]
FONTSOURCE = "https://api.fontsource.org/v1/fonts"


def free_alternative(name: str) -> str:
    """Freier, (meist metrisch kompatibler) Zwilling einer kommerziellen Schrift – oder ""."""
    fam = _norm(name)[0]
    for pat, alt in DOWNLOAD_ALIAS:
        if re.search(pat, fam):
            return alt
    return ""


def _get_json(url):
    import urllib.request                        # erst bei Bedarf: lädt SSL – kostete beim ersten Fenster spürbar Zeit
    req = urllib.request.Request(url, headers={"User-Agent": "Passermark"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def similar_fonts(family: str, n: int = 6) -> list[str]:
    """Similarly named free fonts on fontsource.org (for "Did you mean …?")."""
    import difflib
    try:
        lst = _get_json(FONTSOURCE)
    except Exception:
        return []
    fams = [f.get("family", "") for f in lst if isinstance(f, dict)]
    low = {f.lower(): f for f in fams}
    q = family.lower().strip()
    hits = [low[k] for k in difflib.get_close_matches(q, list(low), n=n, cutoff=0.6)]
    hits += [f for f in fams if q and q in f.lower() and f not in hits]
    return hits[:n]


class FontNotFound(RuntimeError):
    def __init__(self, family, suggestions):
        self.family, self.suggestions = family, suggestions
        msg = tr("Schrift „{0}“ gibt es auf fontsource.org nicht (dort liegen nur freie Schriften).").format(family)
        if suggestions:
            msg += "\n" + tr("Ähnliche freie Schriften: {0}").format(", ".join(suggestions))
        super().__init__(msg)


def download_font(family: str, progress=None) -> tuple[list[str], str]:
    """Fetch a free font (OFL/Apache) from fontsource.org -> (file paths, family actually loaded).
        Commercial names (Arial, Calibri …) are redirected to their free twin.
    """
    import urllib.error
    import urllib.request
    used = free_alternative(family) or family.strip()
    fid = re.sub(r"[^a-z0-9]+", "-", used.lower()).strip("-")
    cdn = "https://cdn.jsdelivr.net/fontsource/fonts/{0}@latest/latin-{1}-{2}.ttf"
    try:
        meta = _get_json(f"{FONTSOURCE}/{fid}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise FontNotFound(used, similar_fonts(used))
        meta = None
        api_err = e
    except Exception as e:
        meta = None
        api_err = e
    if meta is None:
        # API nicht erreichbar: direkt vom fontsource-CDN (gleiche Dateien)
        meta = {"family": used, "variants": {w: {st: {"latin": {"url": {"ttf": cdn.format(fid, w, st)}}}
                                                 for st in ("normal", "italic")} for w in ("400", "700")}}
    variants = meta.get("variants") or {}
    out_dir = user_font_dir()
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for weight in ("400", "700"):
        for style in ("normal", "italic"):
            v = (variants.get(weight) or {}).get(style) or {}
            sub = v.get("latin") or (next(iter(v.values())) if v else None)
            if not sub:
                continue
            u = (sub.get("url") or {}).get("ttf")
            if not u:
                continue
            fn = f"{fid}-{weight}-{style}.ttf"
            dst = os.path.join(out_dir, fn)
            try:
                with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Passermark"}),
                                            timeout=30) as r:
                    data = r.read()
            except Exception:
                continue                      # Schnitt nicht vorhanden (z. B. keine Kursive)
            with open(dst, "wb") as f:
                f.write(data)
            paths.append(dst)
            if progress:
                progress(fn)
    if not paths:
        if "api_err" in locals():
            raise RuntimeError(tr("Kein Zugriff auf fontsource.org ({0}).").format(api_err))
        raise RuntimeError(tr("Für „{0}“ gibt es keine TTF-Dateien zum Herunterladen.").format(used))
    if shutil.which("fc-cache"):
        subprocess.run(["fc-cache", "-f", out_dir], capture_output=True, timeout=60)
    return paths, meta.get("family", used)


def _gs(args: list, src: bytes) -> bytes:
    gs = _platform.ghostscript()
    if not gs:
        raise RuntimeError(tr("Für diese Reparatur wird Ghostscript benötigt."))
    tmp = tempfile.mkdtemp(prefix="passermark-pf-")
    try:
        i, o = os.path.join(tmp, "in.pdf"), os.path.join(tmp, "out.pdf")
        with open(i, "wb") as f:
            f.write(src)
        cmd = [gs, "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=pdfwrite", "-dAutoRotatePages=/None",
               "-dDownsampleColorImages=false", "-dDownsampleGrayImages=false", "-dDownsampleMonoImages=false",
               *[a.replace("{TMP}", tmp) for a in args], "-o", o, i]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, **_platform.hidden_subprocess_kwargs())
        if r.returncode != 0 or not os.path.exists(o):
            raise RuntimeError(tr("Ghostscript-Fehler:\n") + (r.stderr or r.stdout or "")[-1500:])
        with open(o, "rb") as f:
            return f.read()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _ps_str(s: str) -> str:
    return "(" + s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ")"


def embed_fonts(data: bytes, mapping: dict) -> bytes:
    """Embed all fonts; replace missing ones via the mapping {font name: path} (Ghostscript fontmap)."""
    tmp = tempfile.mkdtemp(prefix="passermark-fm-")
    try:
        fm = os.path.join(tmp, "Fontmap")
        dirs = set()
        with open(fm, "w", encoding="utf-8") as f:
            for name, path in mapping.items():
                if path and os.path.exists(path):
                    f.write(f"/{name} {_ps_str(path)} ;\n")
                    dirs.add(os.path.dirname(path))
        permits = [f"--permit-file-read={d.rstrip(os.sep)}{os.sep}" for d in dirs | {tmp}]
        args = ["-dCompatibilityLevel=1.7", "-dEmbedAllFonts=true", "-dSubsetFonts=true",
                f"-sFONTMAP={fm}", *permits]
        if dirs:
            args.append("-sFONTPATH=" + os.pathsep.join(sorted(dirs)))
        return _gs(args, data)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def outline_text(data: bytes) -> bytes:
    """Convert text to paths (looks the same everywhere, but is no longer searchable)."""
    return _gs(["-dCompatibilityLevel=1.7", "-dNoOutputFonts"], data)


def flatten_transparency(data: bytes, dpi: int = 300) -> bytes:
    """Reduce transparency (PDF 1.3) – for older printers/RIPs. Transparent areas are rasterized."""
    return _gs(["-dCompatibilityLevel=1.3", f"-r{dpi}"], data)


# --------------------------------------------------------------------------- #
# Bilder und Farben (imagecheck)
# --------------------------------------------------------------------------- #
def _mm(t) -> str:
    return f"{t[0]:.0f} × {t[1]:.0f} mm"


def _img_spot(u) -> "Spot":
    return Spot(u.page, getattr(u, "bbox", None),
                tr("{0:.0f} dpi, {1} × {2} px, {3}").format(u.dpi, u.px[0], u.px[1], u.space or "?"))


def _image_issues(rep: Report) -> list:
    from . import imagecheck as ic
    cr = rep.colors
    if cr is None:
        return []
    out = []
    by_page: dict = {}
    hdr_aux = {h["aux"] + 1 for h in (rep.hdr or [])}     # graue HDR-Zusatzseite: eigener Befund
    for u in cr.images:
        if (u.mask and u.rating == "tiny") or u.page in hdr_aux:
            continue
        by_page.setdefault(u.page, []).append(u)
    limits = ic.page_limits(cr)
    low_pages = sorted(p for p, us in by_page.items() if any(u.rating == "low" for u in us))
    ok_pages = sorted(p for p, us in by_page.items() if p not in low_pages and any(u.rating == "ok" for u in us))

    def advice(p, worst):
        lim = limits.get(p)
        a, b = worst.max_mm(worst.good), worst.max_mm(worst.ok)
        txt = tr("Empfehlung: dieses Bild bei {0} dpi max. {1}, bei {2} dpi max. {3}.").format(
            worst.good, _mm(a), worst.ok, _mm(b))
        if lim and p in cr.page_size_mm and lim[1] < 0.995:
            ps = cr.page_size_mm[p]
            txt += " " + tr("Ganze Seite höchstens {0:.0f} % ({1}) bei {2} dpi bzw. {3:.0f} % ({4}) bei {5} dpi.").format(
                lim[1] * 100, _mm((ps[0] * lim[1], ps[1] * lim[1])), ic.GOOD_DPI,
                min(lim[2], 9.99) * 100, _mm((ps[0] * min(lim[2], 9.99), ps[1] * min(lim[2], 9.99))), ic.OK_DPI)
        return txt

    for pages, sev, kind in ((low_pages, "warning", "low"), (ok_pages, "info", "ok")):
        if len(pages) > 8:                               # viele Seiten: eine Sammelmeldung
            worst = min((u for p in pages for u in by_page[p] if u.rating == kind), key=lambda u: u.dpi)
            msg = (tr("Bilder unter {0} dpi auf {1} Seiten – niedrigste {2:.0f} dpi (Seite {3}).")
                   if kind == "low" else
                   tr("Bilder mit {0}–{1} dpi auf {2} Seiten – gut für Plakat/Großformat, für Nahbetrachtung knapp."))
            out.append(Issue(sev, "image", msg.format(worst.ok, len(pages), worst.dpi, worst.page) if kind == "low"
                             else msg.format(ic.OK_DPI, ic.GOOD_DPI - 1, len(pages)), pages,
                             [_img_spot(u) for p in pages for u in by_page[p] if u.rating == kind]))
            continue
        for p in pages:
            us = [u for u in by_page[p] if u.rating == kind]
            worst = min(us, key=lambda u: u.dpi)
            head = (tr("Seite {0}: {1} Bild(er) unter {2} dpi – niedrigste {3:.0f} dpi ({4} × {5} px auf {6}).")
                    if kind == "low" else
                    tr("Seite {0}: {1} Bild(er) mit {3:.0f}–{2} dpi ({4} × {5} px auf {6}) – gut für Plakat/"
                       "Großformat, für Nahbetrachtung knapp."))
            msg = head.format(p, len(us), worst.ok if kind == "low" else worst.good - 1, worst.dpi,
                              worst.px[0], worst.px[1], _mm(worst.placed_mm))
            out.append(Issue(sev, "image", msg + " " + advice(p, worst), [p], [_img_spot(u) for u in us]))
    rgb = sorted(p for p, c in cr.page_colors.items() if "RGB" in c)
    if rgb:
        n_img = sum(1 for u in cr.images if u.space == "RGB")
        spots = [_img_spot(u) for u in cr.images if u.space == "RGB" and u.page in rgb]
        with_img = {sp.page for sp in spots}
        spots += [Spot(p, None, tr("RGB-Farben (Text/Grafik)")) for p in rgb if p not in with_img]
        out.append(Issue("info", "image", tr("RGB-Inhalte auf {0} Seite(n) ({1} Bildplatzierung(en) in RGB) – für "
                                             "Offset/Digitaldruck nach CMYK umwandeln (Druckaufbereitung → CMYK); "
                                             "Plotter/Großformat drucken RGB meist direkt.").format(len(rgb), n_img), rgb,
                         sorted(spots, key=lambda sp: sp.page)))
    names = sorted({n for ns in cr.spots.values() for n in ns})
    if names:
        out.append(Issue("info", "image", tr("Sonderfarben: {0}.").format(", ".join(names)), sorted(cr.spots),
                         [Spot(p, None, ", ".join(sorted(cr.spots[p]))) for p in sorted(cr.spots)]))
    return out


def colors_text(rep: Report) -> list:
    """Bilder und Farben als Textzeilen (für Bericht und Panel)."""
    cr = rep.colors
    if cr is None:
        return []
    lines = []
    if cr.output_intent:
        lines.append(tr("Ausgabeprofil (Output Intent): {0}").format(cr.output_intent))
    for p in sorted(cr.page_colors):
        from .imagecheck import space_label
        lines.append(tr("Seite {0}: {1}").format(p, ", ".join(sorted(space_label(c) for c in cr.page_colors[p]))))
    return lines


# --------------------------------------------------------------------------- #
# HDR-Fotos, als zwei Seiten geöffnet (Foto + graue Helligkeitskarte)
# --------------------------------------------------------------------------- #
def _single_image(page):
    """Seite, die nur aus einem Bild besteht (wie beim Öffnen eines Fotos) -> (Name, Bild) oder None."""
    import pikepdf
    try:
        ops = list(pikepdf.parse_content_stream(page))
    except Exception:
        return None
    names = [str(getattr(i, "operator", "")) for i in ops]
    if any(n not in ("q", "Q", "cm", "Do") for n in names) or names.count("Do") != 1:
        return None
    nm = str(ops[names.index("Do")].operands[0])
    x = (_resources(page).get("/XObject") or {}).get(nm)
    if x is None or x.get("/Subtype") != pikepdf.Name.Image:
        return None
    return nm, x


def _components(img) -> int:
    import pikepdf
    cs = img.get("/ColorSpace")
    if cs == pikepdf.Name.DeviceGray:
        return 1
    if cs == pikepdf.Name.DeviceRGB:
        return 3
    if cs == pikepdf.Name.DeviceCMYK:
        return 4
    try:
        if isinstance(cs, pikepdf.Array) and cs[0] == pikepdf.Name.ICCBased:
            return int(cs[1].get("/N", 0))
    except Exception:
        pass
    return 0


def hdr_aux_pages(pdf) -> list:
    """Paare (Foto, graue Helligkeitskarte) aufeinanderfolgender Bildseiten – so öffnet img2pdf HDR-Fotos
        vom Handy, wenn nicht repariert wurde. Gleiches Seitenverhältnis, Karte grau und nicht größer."""
    out, pages = [], list(pdf.pages)
    i = 0
    while i + 1 < len(pages):
        a, b = _single_image(pages[i]), _single_image(pages[i + 1])
        if a and b:
            ia, ib = a[1], b[1]
            try:
                aw, ah, bw, bh = int(ia.Width), int(ia.Height), int(ib.Width), int(ib.Height)
            except Exception:
                aw = ah = bw = bh = 0
            if (aw and bw and _components(ia) >= 3 and _components(ib) == 1 and bw <= aw and bh <= ah
                    and abs(aw / ah - bw / bh) <= 0.02 * aw / ah):
                pa, pb = [float(v) for v in pages[i].mediabox], [float(v) for v in pages[i + 1].mediabox]
                out.append({"main": i, "aux": i + 1, "main_px": (aw, ah), "aux_px": (bw, bh),
                            "main_dpi": aw / ((pa[2] - pa[0]) / 72.0), "aux_dpi": bw / ((pb[2] - pb[0]) / 72.0),
                            "aux_mode": "L", "kind": tr("HDR-Foto")})
                i += 2
                continue
        i += 1
    return out


def remove_hdr_aux(data: bytes, size: str = "aux", merge: bool = False) -> bytes:
    """HDR-Zusatzseiten entfernen. size: "aux" = Fotoseite bekommt die Größe der Zusatzseite,
        "main" = Größe bleibt. merge: Helligkeitskarte ins Foto einrechnen (neues JPEG)."""
    import pikepdf
    pdf = pikepdf.open(io.BytesIO(data))
    try:
        pairs = hdr_aux_pages(pdf)
        for h in sorted(pairs, key=lambda x: -x["main"]):
            mp, ap = pdf.pages[h["main"]], pdf.pages[h["aux"]]
            nm, img = _single_image(mp)
            if merge:
                from . import images
                _an, aux = _single_image(ap)
                base = pikepdf.PdfImage(img).as_pil_image()
                gm = pikepdf.PdfImage(aux).as_pil_image()
                icc = None
                try:
                    icc = pikepdf.PdfImage(img).icc.tobytes() if pikepdf.PdfImage(img).icc else None
                except Exception:
                    icc = None
                jpg = images.merge_gain_map(base, gm, icc)
                img.write(jpg, filter=pikepdf.Name.DCTDecode)
                img.Width, img.Height = base.size[0], base.size[1]
                img.BitsPerComponent = 8
                if "/DecodeParms" in img:
                    del img["/DecodeParms"]
            box = ap.mediabox if size == "aux" else mp.mediabox
            w, h_ = float(box[2]) - float(box[0]), float(box[3]) - float(box[1])
            mp.obj.MediaBox = pikepdf.Array([0, 0, w, h_])
            for k in ("/CropBox", "/TrimBox", "/BleedBox", "/ArtBox"):
                if k in mp.obj:
                    del mp.obj[k]
            mp.obj.Contents = pikepdf.Stream(pdf, f"q\n{w:.4f} 0 0 {h_:.4f} 0 0 cm\n{nm} Do\nQ".encode("ascii"))
            del pdf.pages[h["aux"]]
        buf = io.BytesIO()
        pdf.save(buf)
        return buf.getvalue()
    finally:
        pdf.close()


# --------------------------------------------------------------------------- #
# Befunde
# --------------------------------------------------------------------------- #
def _located_spots(rep: Report, key: tuple, pages, label: str = "") -> list:
    """Fundstellen aus rep.located (Bereiche je Seite), Seiten ohne Bereich als ganze Seite."""
    loc = rep.located.get(key) or {}
    out = []
    for p in sorted(pages):
        boxes = _merge_boxes(loc.get(p) or [])
        out += [Spot(p, b, label) for b in boxes] or [Spot(p, None, label)]
    return out


def _issues(rep: Report) -> list[Issue]:
    out = _issues_raw(rep)
    for i in out:
        if not i.spots:
            i.spots = [Spot(p) for p in i.pages]
    return out


def _issues_raw(rep: Report) -> list[Issue]:
    out = []
    for f in rep.fonts:
        pg = sorted(f.pages)
        n0 = len(out)
        if f.status == "missing":
            if f.encoding == "private":
                out.append(Issue("error", "font", tr("Schrift „{0}“ ist nicht eingebettet und verwendet eigene Zeichennamen – "
                                                     "ohne die Originalschrift nicht reparierbar (Text fehlt oder wird "
                                                     "zu Fremdzeichen).").format(f.name), pg))
            elif f.cid and f.encoding.startswith("Identity"):
                out.append(Issue("error", "font", tr("Schrift „{0}“ ist nicht eingebettet (CID, Identity) – ohne die "
                                                     "Originalschrift nicht reparierbar.").format(f.name), pg))
            else:
                hint = tr(" Ersatz: {0}.").format(f.suggestion_name) if f.suggestion_name else tr(" Kein Ersatz gefunden.")
                out.append(Issue("error", "font", tr("Schrift „{0}“ ist nicht eingebettet – Darstellung kann abweichen.")
                                 .format(f.name) + hint, pg))
        elif f.status == "std14":
            out.append(Issue("info", "font", tr("Standardschrift „{0}“ nicht eingebettet (wird meist korrekt ersetzt).")
                             .format(f.name), pg))
        elif f.status == "type3":
            out.append(Issue("info", "font", tr("Type3-Schrift „{0}“ (oft aus CAD) – Text ggf. nicht durchsuchbar.")
                             .format(f.name), pg))
        if not f.tounicode and f.status != "std14" and f.encoding not in ("WinAnsiEncoding", "MacRomanEncoding",
                                                                            "StandardEncoding"):
            out.append(Issue("info", "font", tr("Schrift „{0}“ ohne Unicode-Zuordnung – Kopieren/Suchen kann falsche "
                                                "Zeichen liefern.").format(f.name), pg))
        for i in out[n0:]:
            i.spots = _located_spots(rep, ("font", f.name), pg, f.name)
    for p, n in sorted(rep.garbled.items()):
        out.append(Issue("warning", "text", tr("Seite {0}: {1} Zeichen ohne gültige Zuordnung (seltsame Zeichen).")
                         .format(p, n), [p]))
    hidden = [L for L in rep.layers if not L.view_on or L.print_on is False]
    if hidden:
        out.append(Issue("warning", "layer", tr("{0} ausgeblendete Ebene(n) – viele Drucker/RIPs ignorieren das und "
                                                "drucken sie trotzdem. Empfehlung: „Sichtbaren Zustand festschreiben“.")
                         .format(len(hidden)), sorted(set().union(*[L.pages for L in hidden]))))
    for L in rep.layers:
        if L.print_on is not None and L.print_on != L.view_on:
            out.append(Issue("warning", "layer", tr("Ebene „{0}“: Ansicht {1}, Druck {2}.").format(
                L.name, tr("an") if L.view_on else tr("aus"), tr("an") if L.print_on else tr("aus")), sorted(L.pages)))
        if L.outside_pct is not None and L.outside_pct > 25:
            out.append(Issue("warning", "layer", tr("Ebene „{0}“: {1:.0f} % des Inhalts liegen außerhalb der Seite "
                                                    "(verrutscht?).").format(L.name, L.outside_pct), sorted(L.pages)))
    out += _image_issues(rep)
    if rep.size is not None:
        from . import shrink
        out += [Issue(sev, "size", msg, []) for sev, msg in shrink.issues(rep.size)]
    for h in rep.hdr:
        out.append(Issue("warning", "image", tr("Seite {0}: graues Zusatzbild eines HDR-Fotos (Helligkeitskarte zu Seite "
                                                "{1}) – wird in anderer Größe mitgedruckt, am Plotter mit falschen "
                                                "Farben. Reparatur: „HDR-Zusatzseiten entfernen“.")
                         .format(h["aux"] + 1, h["main"] + 1), [h["aux"] + 1]))
    grad = sorted(p for p, k in rep.transparency.items() if "pattern_smask" in k)
    if grad:
        out.append(Issue("warning", "transparency", tr("Transparente Verläufe (Soft-Maske im Muster) auf {0} Seite(n) – "
                                                       "manche RIPs/Plotter drucken sie als schwarze Fläche und decken "
                                                       "darunterliegende Bilder ab. Reparatur: „Transparente Verläufe in "
                                                       "Bilder umwandeln“.").format(len(grad)), grad,
                         _located_spots(rep, ("transparency",), grad)))
    risky = {p for p, k in rep.transparency.items() if k & {"smask", "blend", "group"} and "pattern_smask" not in k}
    if risky:
        out.append(Issue("info", "transparency", tr("Transparenzen auf {0} Seite(n) – auf älteren Druckern/RIPs ggf. "
                                                    "„Transparenzen reduzieren“.").format(len(risky)), sorted(risky),
                         _located_spots(rep, ("transparency",), risky)))
    op = {p for p, k in rep.transparency.items() if "overprint" in k}
    if op:
        out.append(Issue("info", "transparency", tr("Überdrucken auf {0} Seite(n).").format(len(op)), sorted(op)))
    out.sort(key=lambda i: (SEV_ORDER[i.severity], i.category))
    return out


def report_text(rep: Report, title: str = "") -> str:
    """Bericht als Text (zum Speichern/Weitergeben)."""
    lines = [tr("Passermark – Prüfbericht") + (f": {title}" if title else ""), ""]
    c = rep.counts()
    lines.append(tr("{0} Fehler, {1} Warnung(en), {2} Hinweis(e) · {3} Seiten").format(
        c["error"], c["warning"], c["info"], rep.pages))
    lines.append("")
    sev = {"error": tr("FEHLER"), "warning": tr("WARNUNG"), "info": tr("HINWEIS")}
    for i in rep.issues:
        lines.append(f"[{sev[i.severity]}] {i.message}" + (tr("  (Seiten {0})").format(_pages_str(i.pages)) if i.pages else ""))
        located = [sp for sp in i.spots if sp.box is not None or sp.label]
        for sp in located[:12]:
            lines.append("    · " + where_text(rep, sp))
        if len(located) > 12:
            lines.append("    · " + tr("… und {0} weitere").format(len(located) - 12))
    lines += ["", tr("Schriften:")]
    for f in rep.fonts:
        st = {"ok": tr("eingebettet"), "std14": tr("Standard, nicht eingebettet"), "missing": tr("NICHT eingebettet"),
              "type3": "Type3"}[f.status]
        lines.append(f"  {f.name}  ·  {f.subtype}  ·  {st}" + (tr("  ·  Teilmenge") if f.subset else "")
                     + (f"  ·  → {f.suggestion_name}" if f.suggestion_name else ""))
    if rep.colors is not None and (rep.colors.images or rep.colors.page_colors):
        lines += ["", tr("Farben:")] + ["  " + x for x in colors_text(rep)]
        if rep.colors.images:
            lines += ["", tr("Bilder (Seite · Pixel · platziert · Auflösung · Farbraum · max. bei 300 / 150 dpi):")]
            for u in rep.colors.images:
                from .imagecheck import space_label
                lines.append(f"  {u.page} · {u.px[0]}×{u.px[1]} px · {_mm(u.placed_mm)} · {u.dpi:.0f} dpi · {space_label(u.space)}"
                             + (f" ({u.profile})" if u.profile else "")
                             + f" · {_mm(u.max_mm(u.good))} / {_mm(u.max_mm(u.ok))}")
    if rep.size is not None:
        from . import shrink
        lines += ["", tr("Dateigröße:")] + ["  " + x for x in shrink.summary_lines(rep.size, top=8)]
    if rep.layers:
        lines += ["", tr("Ebenen:")]
        for L in rep.layers:
            lines.append(f"  {L.name}  ·  " + tr("Ansicht {0}, Druck {1}").format(
                tr("an") if L.view_on else tr("aus"),
                tr("wie Ansicht") if L.print_on is None else (tr("an") if L.print_on else tr("aus"))))
    return "\n".join(lines) + "\n"
