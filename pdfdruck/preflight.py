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
import logging
import re
from dataclasses import dataclass, field

from .fontlib import suggest_font
from .l10n import tr
from .pdflayers import layers_outside, list_layers
from .pdfutil import obj_key, page_resources

log = logging.getLogger(__name__)

STANDARD14 = {
    "Courier",
    "Courier-Bold",
    "Courier-Oblique",
    "Courier-BoldOblique",
    "Helvetica",
    "Helvetica-Bold",
    "Helvetica-Oblique",
    "Helvetica-BoldOblique",
    "Times-Roman",
    "Times-Bold",
    "Times-Italic",
    "Times-BoldItalic",
    "Symbol",
    "ZapfDingbats",
}


SEV_ORDER = {"error": 0, "warning": 1, "info": 2}


@dataclass
class Spot:
    """One location: page (1-based), optionally the area on the page (pt, page coordinates)."""

    page: int
    box: tuple | None = None
    label: str = ""  # what exactly is there ("72 dpi, 400 × 300 px", font name …)


@dataclass
class Issue:
    """One finding of the document check: severity, category, message and where it occurs."""

    severity: str  # error | warning | info
    category: str  # font | layer | transparency | text | image
    message: str
    pages: list = field(default_factory=list)
    spots: list = field(default_factory=list)  # [Spot] – where exactly (empty: only the pages)


@dataclass
class FontInfo:
    """A font used in the document: name, type, whether it is embedded and on which pages it is used."""

    key: str
    name: str  # without subset prefix
    raw: str
    subtype: str
    embedded: bool
    subset: bool
    tounicode: bool
    encoding: str
    cid: bool
    standard14: bool
    pages: set = field(default_factory=set)
    suggestion: str = ""  # path of the substitute font
    suggestion_name: str = ""

    @property
    def status(self) -> str:
        """Status key of the font: ok (embedded), type3, std14 (one of the 14 standard fonts) or missing."""
        if self.subtype == "Type3":
            return "type3"
        if self.embedded:
            return "ok"
        if self.standard14:
            return "std14"
        return "missing"


@dataclass
class Report:
    """Result of the document check: fonts, layers, findings and facts about the pages."""

    pages: int = 0
    fonts: list = field(default_factory=list)
    layers: list = field(default_factory=list)
    transparency: dict = field(default_factory=dict)  # page -> {kind}
    garbled: dict = field(default_factory=dict)  # page -> count
    hdr: list = field(default_factory=list)  # HDR photo: [{"main": i, "aux": j, …}] (0-based)
    colors: object = None  # imagecheck.ColorReport: images (dpi, colour space), colours
    size: object = None  # shrink.SizeReport: what takes up the space
    issues: list = field(default_factory=list)
    boxes: dict = field(default_factory=dict)  # page -> MediaBox (x0, y0, x1, y1) – for "where on the page"
    located: dict = field(default_factory=dict)  # ("font", name) / ("transparency",) -> {page: [area]}
    hairlines: dict = field(default_factory=dict)  # page -> number of lines thinner than HAIRLINE_MM
    geometry: dict = field(default_factory=dict)  # page -> {media, crop, trim, bleed (pt, None = missing), rotate, uu}
    security: dict = field(default_factory=dict)  # {encrypted, print, print_high}
    pdfx: dict = field(default_factory=dict)  # {version, intent, missing_trim: [pages]}
    forms: dict = field(default_factory=dict)  # {fields, widgets: [(page, rect, prints)], need_ap}
    blank: list = field(default_factory=list)  # blank pages (1-based)
    edge_ink: dict = field(default_factory=dict)  # page -> {side of the box: bleed mm} – content up to the edge
    near_edge: dict = field(default_factory=dict)  # page -> [box] – text/logo closer than SAFETY_MM to the trim
    overprint: dict = field(default_factory=dict)  # overprint.scan(): {"white": {page: [box]}, "black_text": …}
    _blank_candidates: list = field(default_factory=list)

    def counts(self):
        """Number of findings per severity."""
        c = {"error": 0, "warning": 0, "info": 0}
        for i in self.issues:
            c[i.severity] += 1
        return c


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
    """Visit resources including (nested) form XObjects. seen: key -> object, per page."""
    import pikepdf

    if res is None:
        return
    rk = obj_key(res)
    if rk in seen:
        return
    seen[rk] = res  # hold on to the object: a key made from id() must not be handed out again while we walk
    visit(res, page_no)
    xo = res.get("/XObject")
    if xo is not None:
        for _n, x in xo.items():
            try:
                if x.get("/Subtype") == pikepdf.Name.Form:
                    _walk_resources(x.get("/Resources"), page_no, visit, seen)
            except Exception:  # noqa: BLE001 – malformed PDF object: skipped or default value
                pass


# --------------------------------------------------------------------------- #
# analysis
# --------------------------------------------------------------------------- #
class _ResourceScan:
    """Collects fonts and transparency while walking the resources of all pages."""

    def __init__(self):
        self.fonts: dict[str, FontInfo] = {}
        self.trans: dict[int, set] = {}
        self._alive: list = []

    def visit(self, res, pno):
        """Note the fonts and the kinds of transparency one resource dictionary of page pno brings along."""
        import pikepdf

        for _n, f in (res.get("/Font") or {}).items():
            k = obj_key(f)
            if k not in self.fonts:
                self.fonts[k] = _font_info(f, k)
                self._alive.append(f)  # as above: keeps id()-based keys unique
            self.fonts[k].pages.add(pno)
        for _n, gs in (res.get("/ExtGState") or {}).items():
            sm = gs.get("/SMask")
            if sm is not None and str(sm) != "/None":
                self.trans.setdefault(pno, set()).add("smask")
            bm = gs.get("/BM")
            if bm is not None:
                names = [str(b) for b in (bm if isinstance(bm, pikepdf.Array) else [bm])]
                if any(n not in ("/Normal", "/Compatible") for n in names):
                    self.trans.setdefault(pno, set()).add("blend")
            for k in ("/CA", "/ca"):
                try:
                    if k in gs and float(gs[k]) < 0.999:
                        self.trans.setdefault(pno, set()).add("alpha")
                except Exception:  # noqa: BLE001 – malformed PDF object: skipped or default value
                    pass
            if gs.get("/OP") is True or gs.get("/op") is True:
                self.trans.setdefault(pno, set()).add("overprint")
        for _n, pat in (res.get("/Pattern") or {}).items():
            # gradient with a soft mask in the pattern (Chrome/Skia, Canva …): RIPs that ignore the mask
            # print it as a black area – images underneath disappear
            try:
                from .softmask import pattern_has_softmask

                if pattern_has_softmask(pat):
                    self.trans.setdefault(pno, set()).add("pattern_smask")
            except Exception:  # noqa: BLE001 – optional module
                pass
        for _n, x in (res.get("/XObject") or {}).items():
            try:
                if x.get("/Subtype") == pikepdf.Name.Image and "/SMask" in x:
                    self.trans.setdefault(pno, set()).add("image_alpha")
                if (
                    x.get("/Subtype") == pikepdf.Name.Form
                    and "/Group" in x
                    and x.Group.get("/S") == pikepdf.Name.Transparency
                ):
                    self.trans.setdefault(pno, set()).add("group")
            except Exception:  # noqa: BLE001 – malformed PDF object: skipped or default value
                pass


def _scan_page(page, i: int, rep: Report, scan: _ResourceScan):
    """Boxes, geometry and form fields of page i; then its resources, those of its annotations, and its group."""
    import pikepdf

    try:
        rep.boxes[i] = tuple(float(v) for v in page.MediaBox)
    except Exception:  # noqa: BLE001 – malformed PDF object: skipped or default value
        pass
    try:
        rep.geometry[i] = _page_geometry(page.obj)
        _page_forms(page.obj, i, rep)
        if _content_len(page.obj) < 20000 and not (page_resources(page).get("/XObject") or {}):
            rep._blank_candidates.append(i)
    except Exception:  # noqa: BLE001 – malformed PDF object: skipped or default value
        pass
    seen: dict = {}
    _walk_resources(page_resources(page), i, scan.visit, seen)
    for a in page.obj.get("/Annots") or []:
        try:
            ap = a.get("/AP")
            n = ap.get("/N") if ap is not None else None
            if isinstance(n, pikepdf.Stream):
                _walk_resources(n.get("/Resources"), i, scan.visit, seen)
        except Exception:  # noqa: BLE001 – malformed PDF object: skipped or default value
            pass
    g = page.obj.get("/Group")
    if g is not None and g.get("/S") == pikepdf.Name.Transparency:
        scan.trans.setdefault(i, set()).add("group")


def _suggest_fonts(rep: Report):
    """A replacement for every font that is missing and can be replaced by its name."""
    for f in rep.fonts:
        if (
            f.status in ("missing", "std14")
            and f.encoding != "private"
            and not (f.cid and f.encoding.startswith("Identity"))
        ):
            f.suggestion, f.suggestion_name = suggest_font(f.name)


def _confirm_pattern_masks(pdf, trans: dict):
    """Soft masks in patterns: only report where one is really painted with (after the repair: no longer)."""
    flagged = [p for p, k in trans.items() if "pattern_smask" in k]
    if flagged:  # only report where it is really painted with (after the repair: no longer)
        try:
            from .softmask import scan

            painted = {t.page + 1 for t in scan(pdf).targets}
            for p in flagged:
                if p not in painted:
                    trans[p].discard("pattern_smask")
                    trans[p].add("smask")
        except Exception:
            log.warning("Prüfung: Softmasken nicht geprüft", exc_info=True)


def _sub_reports(pdf, data: bytes, rep: Report):
    """HDR auxiliary pages, the colour report and the size report – each one optional if it fails."""
    try:
        rep.hdr = hdr_aux_pages(pdf)
    except Exception:
        log.warning("Prüfung: HDR-Hilfsseiten nicht geprüft", exc_info=True)
        rep.hdr = []
    try:
        from . import imagecheck

        rep.colors = imagecheck.analyze(pdf)
    except Exception:
        log.warning("Prüfung: Farben/Bilder nicht geprüft", exc_info=True)
        rep.colors = None
    try:
        from . import shrink

        rep.size = shrink.analyze(data, pdf, rep.colors)
    except Exception:
        log.warning("Prüfung: Dateigröße nicht analysiert", exc_info=True)
        rep.size = None


def analyze(data: bytes, deep_layers: bool = True, pdfium_parts: bool = True) -> Report:
    """Check the document. pdfium_parts=False: only the parts without pdfium (for background threads – pdfium is not
    thread-safe); complete the rest afterwards in the main thread with finish().
    """
    import pikepdf

    rep = Report()
    pdf = pikepdf.open(io.BytesIO(data))
    try:
        rep.pages = len(pdf.pages)
        scan = _ResourceScan()
        for i, page in enumerate(pdf.pages, start=1):
            _scan_page(page, i, rep, scan)
        rep.fonts = sorted(scan.fonts.values(), key=lambda f: (f.status == "ok", f.name.lower()))
        _suggest_fonts(rep)
        _confirm_pattern_masks(pdf, scan.trans)
        rep.transparency = scan.trans
        try:
            _doc_checks(pdf, rep)
        except Exception:
            log.warning("Prüfung: Dokumentprüfungen unvollständig", exc_info=True)
        rep.layers = list_layers(pdf)
        try:
            from . import overprint

            rep.overprint = overprint.scan(pdf)
        except Exception:
            log.warning("Prüfung: Überdrucken nicht geprüft", exc_info=True)
            rep.overprint = {}
        _sub_reports(pdf, data, rep)
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
        log.warning("Prüfung: Fundstellen nicht ermittelt", exc_info=True)
        rep.located = {}
    try:
        _hairlines(data, rep)
    except Exception:
        log.warning("Prüfung: Haarlinien nicht geprüft", exc_info=True)
        rep.hairlines = {}
    try:
        _render_checks(data, rep)
    except Exception:
        log.warning("Prüfung: Render-Prüfungen nicht ausgeführt", exc_info=True)
    try:
        _safety_checks(data, rep)
    except Exception:
        log.warning("Prüfung: Sicherheitsabstand nicht geprüft", exc_info=True)
        rep.near_edge = {}
    if deep_layers and rep.layers:
        try:
            layers_outside(data, rep.layers)
        except Exception:
            log.warning("Prüfung: Ebenen außerhalb nicht geprüft", exc_info=True)
    rep.issues = _issues(rep)
    return rep


# --------------------------------------------------------------------------- #
# page geometry, permissions, PDF/X, forms, blank pages
# --------------------------------------------------------------------------- #
BOX_TOL_MM = 0.5
BLEED_MIN_MM = 2.0  # below this: check whether content reaches the trim edge
INHERITABLE = ("/MediaBox", "/CropBox", "/Rotate")


def _inh(obj, key):
    """Page attribute, also inherited from the page tree (MediaBox, CropBox, Rotate)."""
    o, depth = obj, 0
    while o is not None and depth < 50:
        v = o.get(key)
        if v is not None:
            return v
        if key not in INHERITABLE:
            return None
        o = o.get("/Parent")
        depth += 1
    return None


def _box(v):
    try:
        a = [float(x) for x in v]
        if len(a) != 4:
            return None
        return (min(a[0], a[2]), min(a[1], a[3]), max(a[0], a[2]), max(a[1], a[3]))
    except Exception:  # noqa: BLE001 – malformed PDF object: skipped or default value
        return None


def _page_geometry(obj) -> dict:
    media = _box(_inh(obj, "/MediaBox")) or (0.0, 0.0, 612.0, 792.0)
    try:
        rot = int(_inh(obj, "/Rotate") or 0) % 360
    except Exception:  # noqa: BLE001 – malformed PDF object: skipped or default value
        rot = 0
    try:
        uu = float(obj.get("/UserUnit") or 1.0)
    except Exception:  # noqa: BLE001 – malformed PDF object: skipped or default value
        uu = 1.0
    return {
        "media": media,
        "crop": _box(_inh(obj, "/CropBox")),
        "trim": _box(obj.get("/TrimBox")),
        "bleed": _box(obj.get("/BleedBox")),
        "art": _box(obj.get("/ArtBox")),
        "rotate": rot,
        "uu": uu,
    }


def _isect(a, b):
    r = (max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))
    return r if r[2] > r[0] and r[3] > r[1] else None


def _differs(a, b, tol_mm: float = BOX_TOL_MM) -> bool:
    return any(abs(x - y) > tol_mm * MM_PT for x, y in zip(a, b, strict=False))


def _inside(a, b, tol_mm: float = BOX_TOL_MM) -> bool:
    """a lies inside b."""
    t = tol_mm * MM_PT
    return a[0] >= b[0] - t and a[1] >= b[1] - t and a[2] <= b[2] + t and a[3] <= b[3] + t


def effective(g: dict) -> tuple:
    """(crop, bleed, trim) as a printer interprets them: crop ∩ media, bleed/trim fall back to crop."""
    crop = _isect(g["crop"], g["media"]) if g["crop"] else g["media"]
    crop = crop or g["media"]
    bleed = _isect(g["bleed"], crop) if g["bleed"] else crop
    trim = g["trim"] or g["art"] or crop
    return crop, bleed or crop, trim


def bleed_mm(g: dict) -> dict:
    """Bleed per side of the box (l, b, r, t) in mm – only with a TrimBox, otherwise {}."""
    if not g.get("trim"):
        return {}
    _c, bl, tr_ = effective(g)
    return {
        "l": (tr_[0] - bl[0]) / MM_PT,
        "b": (tr_[1] - bl[1]) / MM_PT,
        "r": (bl[2] - tr_[2]) / MM_PT,
        "t": (bl[3] - tr_[3]) / MM_PT,
    }


def _content_len(obj) -> int:
    c = obj.get("/Contents")
    if c is None:
        return 0
    items = c if not hasattr(c, "read_raw_bytes") else [c]
    n = 0
    for st in items:
        try:
            n += int(st.get("/Length") or 0)
        except Exception:  # noqa: BLE001 – malformed PDF object: skipped or default value
            n += 100000
    if obj.get("/Annots"):
        n += 100000  # annotations/forms: do not count as empty
    return n


def _page_forms(obj, pno: int, rep: Report):
    f = rep.forms.setdefault("widgets", [])
    for a in obj.get("/Annots") or []:
        try:
            if a.get("/Subtype") != "/Widget":
                continue
            fl = int(a.get("/F") or 0)
            prints = bool(fl & 4) and not (fl & 2) and a.get("/AP") is not None
            f.append((pno, _box(a.get("/Rect")), prints))
        except Exception:  # noqa: BLE001 – malformed PDF object: skipped or default value
            pass


def _doc_checks(pdf, rep: Report):
    import pikepdf

    sec = {"encrypted": bool(pdf.is_encrypted), "print": True, "print_high": True}
    try:
        if pdf.is_encrypted:
            sec["print"] = bool(pdf.allow.print_lowres)
            sec["print_high"] = bool(pdf.allow.print_highres)
    except Exception:  # noqa: BLE001 – malformed PDF object: skipped or default value
        pass
    rep.security = sec
    ver = ""
    try:
        info = pdf.trailer.get("/Info")
        if info is not None and info.get("/GTS_PDFXVersion") is not None:
            ver = str(info.GTS_PDFXVersion)
    except Exception:  # noqa: BLE001 – malformed PDF object: skipped or default value
        pass
    if not ver:
        try:
            with pdf.open_metadata() as md:
                ver = str(md.get("pdfxid:GTS_PDFXVersion") or md.get("pdfx:GTS_PDFXVersion") or "")
        except Exception:  # noqa: BLE001 – malformed PDF object: skipped or default value
            ver = ""
    intent, noprof = "", False
    try:
        for oi in pdf.Root.get("/OutputIntents") or []:
            if oi.get("/S") == pikepdf.Name("/GTS_PDFX"):
                intent = str(oi.get("/OutputConditionIdentifier") or oi.get("/Info") or "?")
                noprof = oi.get("/DestOutputProfile") is None
                break
    except Exception:  # noqa: BLE001 – malformed PDF object: skipped or default value
        pass
    rep.pdfx = {
        "version": ver,
        "intent": intent,
        "no_profile": noprof,
        "missing_trim": [p for p, g in sorted(rep.geometry.items()) if not g["trim"] and not g["art"]],
    }
    try:
        af = pdf.Root.get("/AcroForm")
        rep.forms["fields"] = len(af.get("/Fields") or []) if af is not None else 0
        rep.forms["need_ap"] = bool(af is not None and af.get("/NeedAppearances") is True)
    except Exception:  # noqa: BLE001 – malformed PDF object: skipped or default value
        rep.forms.setdefault("fields", 0)


def _render_checks(data: bytes, rep: Report, max_pages: int = 300, max_bleed: int = 50):
    """pdfium: blank pages (only candidates with little content) and content up to the trim edge with too little
    bleed.
    """
    import pypdfium2 as pdfium

    from .planprint import _render_gray

    edge = [
        p
        for p, g in sorted(rep.geometry.items())
        if g["rotate"] == 0 and any(v < BLEED_MIN_MM - 0.05 for v in bleed_mm(g).values())
    ][:max_bleed]
    todo = sorted(set(rep._blank_candidates[:max_pages]) | set(edge))
    if not todo:
        return
    doc = pdfium.PdfDocument(data)
    try:
        for p in todo:
            if p - 1 >= len(doc):
                continue
            pg = doc[p - 1]
            try:
                if p in rep._blank_candidates:
                    a = _render_gray(pg, 0.6 / MM_PT)  # ~0,6 px/mm
                    if a.size and int(a.min()) >= 250:
                        rep.blank.append(p)
                        continue
                if p in edge:
                    g = rep.geometry[p]
                    crop, _bl, trim = effective(g)
                    sc = 2.0 / MM_PT  # 2 px/mm
                    a = _render_gray(pg, sc)
                    H, W = a.shape[:2]

                    def px(X, Y, crop=crop, sc=sc):
                        return int(round((X - crop[0]) * sc)), int(round((crop[3] - Y) * sc))

                    band = 1.5 * MM_PT
                    sides = {
                        "l": (trim[0], trim[1], trim[0] + band, trim[3]),
                        "r": (trim[2] - band, trim[1], trim[2], trim[3]),
                        "b": (trim[0], trim[1], trim[2], trim[1] + band),
                        "t": (trim[0], trim[3] - band, trim[2], trim[3]),
                    }
                    hit = {}
                    for k, v in bleed_mm(g).items():
                        if v >= BLEED_MIN_MM - 0.05:
                            continue
                        x0, y1 = px(sides[k][0], sides[k][1])
                        x1, y0 = px(sides[k][2], sides[k][3])
                        x0, x1 = max(0, min(x0, x1)), min(W, max(x0, x1, min(x0, x1) + 1))
                        y0, y1 = max(0, min(y0, y1)), min(H, max(y0, y1, min(y0, y1) + 1))
                        reg = a[y0:y1, x0:x1]
                        if reg.size and (reg < 235).mean() > 0.2:  # a fifth of the edge strip is printed
                            hit[k] = round(max(0.0, v), 1)
                    if hit:
                        rep.edge_ink[p] = hit
            finally:
                pg.close()
    finally:
        doc.close()


SAFETY_MM = 3.0  # text and logos keep this distance from the final format (cutting tolerance)
LOGO_MAX_SHARE = 0.25  # images up to this share of the page count as logo/photo; larger ones are backgrounds


def _safety_checks(data: bytes, rep: Report, max_pages: int = 100):
    """pdfium: text and small images inside the final format but closer than SAFETY_MM to its edge (or cut by
    it) – they may be cut off. Objects that reach beyond the edge on purpose (backgrounds) are not reported."""
    import pypdfium2 as pdfium
    import pypdfium2.raw as raw

    d = SAFETY_MM * MM_PT
    doc = pdfium.PdfDocument(data)
    try:
        for p, g in sorted(rep.geometry.items())[:max_pages]:
            if p - 1 >= len(doc):
                continue
            _crop, _bl, trim = effective(g)
            tw, th = trim[2] - trim[0], trim[3] - trim[1]
            if tw < 6 * d or th < 6 * d:  # tiny formats (labels): the rule does not apply
                continue
            pg = doc[p - 1]
            boxes = []
            try:
                tp = pg.get_textpage()
                try:
                    n = tp.count_chars()
                    text = tp.get_text_range(0, n) if n else ""
                    same = len(text) == n
                    for i in range(n):
                        if same and text[i].isspace():
                            continue
                        box = tp.get_charbox(i)
                        if _too_close(box, trim, d, allow_beyond=False):
                            boxes.append(box)
                finally:
                    tp.close()
                area = tw * th
                for obj in pg.get_objects(filter=[raw.FPDF_PAGEOBJ_IMAGE], max_depth=2):
                    try:
                        b = obj.get_bounds()
                    except Exception:  # noqa: BLE001
                        continue
                    if (b[2] - b[0]) * (b[3] - b[1]) > LOGO_MAX_SHARE * area:
                        continue
                    if _too_close(b, trim, d, allow_beyond=True):
                        boxes.append(b)
            finally:
                pg.close()
            if boxes:
                rep.near_edge[p] = _merge_boxes(boxes)
    finally:
        doc.close()


def _too_close(box, trim, d: float, allow_beyond: bool) -> bool:
    """Inside the final format (at least partly) and closer than d to one of its edges. allow_beyond: objects that
    touch or cross the edge count as intended (bleed) – for images; text crossing the edge is always reported."""
    x0, y0, x1, y1 = box
    if x1 <= trim[0] or x0 >= trim[2] or y1 <= trim[1] or y0 >= trim[3]:
        return False  # completely outside: slug, bleed, crop marks
    if x1 - x0 <= 0 or y1 - y0 <= 0:
        return False
    tol = 0.3 * MM_PT
    dist = min(x0 - trim[0], y0 - trim[1], trim[2] - x1, trim[3] - y1)
    if dist < -tol:  # crosses the edge
        return not allow_beyond
    if allow_beyond and dist <= tol:  # image up to the edge: meant to bleed (the bleed check covers that)
        return False
    return dist < d - 0.05 * MM_PT


SIDE_TEXT = {"l": "links", "r": "rechts", "t": "oben", "b": "unten"}


def _fmt_box(b) -> str:
    return f"{(b[2] - b[0]) / MM_PT:.1f} × {(b[3] - b[1]) / MM_PT:.1f} mm".replace(".", ",")


def _group(pages: dict) -> list:
    """{page: text} -> [(text, [pages])] – combine identical findings."""
    by = {}
    for p, t in sorted(pages.items()):
        by.setdefault(t, []).append(p)
    return list(by.items())


def _geometry_issues(rep: Report) -> list:
    out = []
    uu, crop, trim_out, bleed_out, rot = {}, {}, {}, {}, {}
    for p, g in rep.geometry.items():
        if abs(g["uu"] - 1.0) > 1e-6:
            uu[p] = f"{g['uu']:g}"
        if g["crop"]:
            if not _inside(g["crop"], g["media"]):
                crop[p] = tr("Sichtbarer Bereich (CropBox) ragt über die Seite (MediaBox) hinaus")
            elif _differs(g["crop"], g["media"]):
                crop[p] = tr("Sichtbarer Bereich (CropBox) {0} kleiner als die Seite (MediaBox) {1}").format(
                    _fmt_box(g["crop"]), _fmt_box(g["media"])
                )
        c, bl, tr_ = effective(g)
        if g["trim"] and not _inside(g["trim"], c):
            trim_out[p] = tr("Endformat (TrimBox) liegt außerhalb des sichtbaren Bereichs")
        if g["bleed"] and g["trim"] and not _inside(g["trim"], g["bleed"]):
            bleed_out[p] = tr("Endformat (TrimBox) größer als der Beschnitt (BleedBox)")
        if g["rotate"]:
            rot[p] = g["rotate"]
    for v, pg in _group(uu):
        out.append(
            Issue(
                "error",
                "geometry",
                tr(
                    "Seitenmaße mit Faktor (UserUnit {0}) – viele Drucker und RIPs "
                    "ignorieren ihn und drucken im falschen Format."
                ).format(v),
                pg,
            )
        )
    for t, pg in _group(crop):
        out.append(
            Issue(
                "warning",
                "geometry",
                t
                + tr(
                    " – manche Drucker/Plotter drucken die ganze MediaBox: "
                    "Inhalt verschoben oder weißer Rand. Abhilfe: Seiten auf "
                    "den sichtbaren Bereich zuschneiden."
                ),
                pg,
            )
        )
    for t, pg in _group(trim_out) + _group(bleed_out):
        out.append(Issue("warning", "geometry", t + tr(" – widersprüchliche Seitenrahmen."), pg))
    for v, pg in _group(rot):
        out.append(
            Issue(
                "info",
                "geometry",
                tr("Seite um {0}° gedreht (/Rotate) – bei Duplex und Plotter auf die Ausrichtung achten.").format(v),
                pg,
            )
        )
    sizes = {}
    for p, g in rep.geometry.items():
        t = effective(g)[2]
        w, h = sorted((round((t[2] - t[0]) / MM_PT), round((t[3] - t[1]) / MM_PT)))
        sizes.setdefault((w, h), []).append(p)
    if len(sizes) > 1:
        parts = [
            tr("{0} × {1} mm ({2} S.)").format(w, h, len(pg))
            for (w, h), pg in sorted(sizes.items(), key=lambda kv: -len(kv[1]))
        ]
        main = max(sizes.values(), key=len)
        other = sorted(p for pg in sizes.values() if pg is not main for p in pg)
        out.append(
            Issue(
                "info",
                "geometry",
                tr("Unterschiedliche Seitenformate: {0} – wichtig für Nutzen, Broschüre und Step & Repeat.").format(
                    ", ".join(parts[:6]) + (" …" if len(parts) > 6 else "")
                ),
                other,
            )
        )
    for hit, pg in _group({p: tuple(sorted(h.items())) for p, h in rep.edge_ink.items()}):
        txt = ", ".join(tr("{0} {1} mm").format(tr(SIDE_TEXT[k]), f"{v:.1f}".replace(".", ",")) for k, v in hit)
        out.append(
            Issue(
                "warning",
                "geometry",
                tr(
                    "Inhalt geht bis an den Endformat-Rand, aber zu wenig Beschnitt "
                    "({0}; empfohlen 3 mm) – beim Schneiden blitzt weißer Rand. "
                    "Abhilfe: Seiten → Anschnitt erzeugen …"
                ).format(txt),
                pg,
            )
        )
    if rep.near_edge:
        pages = sorted(rep.near_edge)
        out.append(
            Issue(
                "warning",
                "geometry",
                tr(
                    "Text oder Bild näher als {0:g} mm am Endformat – kann beim Schneiden angeschnitten werden "
                    "(Seite {1}). Abhilfe: im Layout weiter nach innen setzen."
                ).format(SAFETY_MM, _pages_str(pages)),
                pages,
                [Spot(p, b, "") for p in pages for b in rep.near_edge[p][:20]],
            )
        )
    return out


def device_issues(rep: Report, caps, printer: str, rolls: list | None = None) -> list:
    """Size against the device: does every page (visible area incl. bleed) fit 1:1 on a paper size of the
    printer or on one of its rolls? Category "device". Without a printer/sizes: [].
    """
    if caps is None or not rep.geometry:
        return []
    key = caps.roles.get("pagesize")
    texts = {c.value: c.text for c in (caps.options[key].choices if key and key in caps.options else [])}
    custom = any(str(v).lower().startswith("custom") for v in texts) or any(
        str(t).lower().startswith(("custom", "benutzer", "sonder")) for t in texts.values()
    )
    papers = [
        (w / MM_PT, h / MM_PT, texts.get(n, n))
        for n, (w, h) in (caps.page_sizes or {}).items()
        if w > 1 and h > 1 and not str(n).lower().startswith("custom")
    ]
    widths = [float(r.width_mm) for r in (rolls or []) if not getattr(r, "empty", False) and r.width_mm]
    if not papers and not widths:
        return []
    tol = 0.6
    bad = {}
    for p, g in sorted(rep.geometry.items()):
        c = effective(g)[0]
        w, h = (c[2] - c[0]) / MM_PT, (c[3] - c[1]) / MM_PT
        if widths:  # roll printer: short side across the roll
            ok = min(w, h) <= max(widths) + tol
        else:
            ok = any((w <= pw + tol and h <= ph + tol) or (w <= ph + tol and h <= pw + tol) for pw, ph, _n in papers)
        if not ok:
            bad.setdefault((round(w), round(h)), []).append(p)
    out = []
    for (w, h), pages in bad.items():
        size = tr("{0} × {1} mm").format(w, h)
        if widths:
            out.append(
                Issue(
                    "warning",
                    "device",
                    tr(
                        "{0} ist breiter als jede Rolle von {1} (breiteste {2} mm) – "
                        "wird abgeschnitten oder in Bahnen geteilt."
                    ).format(size, printer, f"{max(widths):g}"),
                    pages,
                )
            )
            continue
        big = max(papers, key=lambda x: x[0] * x[1])
        bigtxt = f"{big[2]} ({round(min(big[0], big[1]))} × {round(max(big[0], big[1]))} mm)"
        if custom:
            out.append(
                Issue(
                    "info",
                    "device",
                    tr(
                        "{0} ist größer als jedes Standardformat von {1} (größtes: {2}) – "
                        "geht nur als Sonderformat, falls das Gerät es kann."
                    ).format(size, printer, bigtxt),
                    pages,
                )
            )
        else:
            out.append(
                Issue(
                    "warning",
                    "device",
                    tr(
                        "{0} passt auf kein Papierformat von {1} (größtes: {2}) – wird verkleinert oder abgeschnitten."
                    ).format(size, printer, bigtxt),
                    pages,
                )
            )
    return out


def add_device_issues(rep: Report, caps, printer: str, rolls: list | None = None) -> Report:
    """Add the findings "size against the device" (once per report and printer)."""
    if getattr(rep, "_device_for", None) == printer:
        return rep
    rep.issues = [i for i in rep.issues if i.category != "device"]
    extra = device_issues(rep, caps, printer, rolls)
    for i in extra:
        if not i.spots:
            i.spots = [Spot(p) for p in i.pages]
    rep.issues = sorted(rep.issues + extra, key=lambda i: (SEV_ORDER[i.severity], i.category))
    try:
        rep._device_for = printer
    except Exception:  # noqa: BLE001
        pass
    return rep


def _doc_issues(rep: Report) -> list:
    out = []
    sec = rep.security or {}
    if sec.get("encrypted"):
        if not sec.get("print", True):
            out.append(Issue("error", "security", tr("Dokument ist geschützt: Drucken ist nicht erlaubt.")))
        elif not sec.get("print_high", True):
            out.append(
                Issue(
                    "warning",
                    "security",
                    tr(
                        "Dokument ist geschützt: nur Drucken in niedriger Auflösung "
                        "erlaubt – manche Programme drucken dann gerastert/unscharf."
                    ),
                )
            )
        else:
            out.append(Issue("info", "security", tr("Dokument ist verschlüsselt (Rechte-Passwort) – Drucken erlaubt.")))
    px = rep.pdfx or {}
    if px.get("version"):
        if not px.get("intent"):
            out.append(
                Issue(
                    "warning",
                    "pdfx",
                    tr(
                        "Datei gibt sich als {0} aus, hat aber keinen PDF/X-Output-Intent – die Angabe stimmt nicht."
                    ).format(px["version"]),
                )
            )
        elif px.get("no_profile"):
            out.append(
                Issue(
                    "warning",
                    "pdfx",
                    tr("{0}: Output-Intent „{1}“ ohne eingebettetes Profil.").format(px["version"], px["intent"]),
                )
            )
        if px.get("missing_trim"):
            out.append(
                Issue(
                    "warning",
                    "pdfx",
                    tr("{0} verlangt ein Endformat (TrimBox) – fehlt auf {1} Seite(n).").format(
                        px["version"], len(px["missing_trim"])
                    ),
                    px["missing_trim"],
                )
            )
    fm = rep.forms or {}
    w = fm.get("widgets") or []
    if w or fm.get("fields"):
        pages = sorted({p for p, _r, _pr in w})
        no = [(p, r) for p, r, pr in w if not pr]
        msg = tr("{0} Formularfeld(er)").format(len(w) or fm.get("fields", 0))
        if no:
            msg += tr(", davon {0} werden nicht gedruckt (ausgeblendet, Druck aus oder ohne Darstellung)").format(
                len(no)
            )
        if fm.get("need_ap"):
            msg += tr(
                " – die Darstellung erzeugt erst das Programm: Passermark druckt die Werte mit, andere "
                "Programme/RIPs ggf. nicht oder anders"
            )
        out.append(
            Issue(
                "warning" if no else "info",
                "form",
                msg + ".",
                pages,
                [Spot(p, r, tr("nicht gedruckt")) for p, r in no if r] or [],
            )
        )
    if rep.blank:
        out.append(Issue("info", "page", tr("{0} leere Seite(n).").format(len(rep.blank)), list(rep.blank)))
    return out


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
        except Exception:  # noqa: BLE001 – malformed PDF object: skipped or default value
            desc = None
    else:
        desc = f.get("/FontDescriptor")
    embedded = subtype == "Type3" or (
        desc is not None and any(k in desc for k in ("/FontFile", "/FontFile2", "/FontFile3"))
    )
    enc = f.get("/Encoding")
    encoding = str(enc)[1:] if isinstance(enc, pikepdf.Name) else ("custom" if enc is not None else "")
    if isinstance(enc, pikepdf.Dictionary):
        # own glyph names (g01, glyph12, cid45 …) -> the meaning of the characters exists only in the original font
        names = [str(x) for x in (enc.get("/Differences") or []) if isinstance(x, pikepdf.Name)]
        if names and sum(bool(re.match(r"^/(g|glyph|cid|G|uni)?[0-9A-Fa-f]{1,5}$", n)) for n in names) > 0.5 * len(
            names
        ):
            encoding = "private"
    return FontInfo(
        k,
        name,
        raw,
        subtype,
        embedded,
        subset,
        "/ToUnicode" in f,
        encoding,
        cid,
        name in STANDARD14 and subtype == "Type1",
    )


def _locate(data: bytes, rep: Report, max_pages: int = 300, max_objs: int = 4000) -> dict:
    """Where exactly? Text objects per non-embedded/conspicuous font and objects with transparency – areas per
    page (pdfium, page coordinates). Only for fonts that have a finding.
    """
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
                n_text = sum(
                    1 for k in range(n) if r.FPDFPageObj_GetType(r.FPDFPage_GetObject(pg.raw, k)) == r.FPDF_PAGEOBJ_TEXT
                )
                seq = order.get(p) or []
                use_seq = len(seq) == n_text  # the font per text object according to the content stream
                ti = -1
                for k in range(n):
                    obj = r.FPDFPage_GetObject(pg.raw, k)
                    typ = r.FPDFPageObj_GetType(obj)
                    left, b, rr, t = (ctypes.c_float() for _ in range(4))
                    if not r.FPDFPageObj_GetBounds(
                        obj, ctypes.byref(left), ctypes.byref(b), ctypes.byref(rr), ctypes.byref(t)
                    ):
                        continue
                    box = (left.value, b.value, rr.value, t.value)
                    if has_tr is not None and p in tpages and has_tr(obj):
                        out.setdefault(("transparency",), {}).setdefault(p, []).append(box)
                    if typ == r.FPDF_PAGEOBJ_TEXT:
                        ti += 1
                    if typ == r.FPDF_PAGEOBJ_TEXT and want:
                        if use_seq:
                            name = seq[ti]
                        else:  # for substituted fonts pdfium often names the substitute
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
    """Page -> [font name per text output (Tj, TJ, ', ")] in the order of the page's content stream
    (without forms) – as many as pdfium has text objects directly on the page.
    """
    import pikepdf

    out = {}
    pdf = pikepdf.open(io.BytesIO(data))
    try:
        for i, page in enumerate(pdf.pages, start=1):
            fonts = (page_resources(page).get("/Font") or {}) if page_resources(page) is not None else {}
            cur, seq = "", []
            try:
                ops = pikepdf.parse_content_stream(page)
            except Exception:  # noqa: BLE001 – malformed PDF object: skipped or default value
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
    """Combine many boxes of a page (e.g. every text row) into a few: close together -> one area."""
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
    """ "Seite 3 – oben links, 40 × 20 mm" (position by thirds of the page, size) – without an area just "Seite 3"."""
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
            bad = sum(
                1 for ch in t if ch == "\ufffd" or "\ue000" <= ch <= "\uf8ff" or (ord(ch) < 32 and ch not in "\r\n\t")
            )
            if bad >= 3 and bad > 0.02 * max(1, len(t)):
                out[i + 1] = bad
    finally:
        doc.close()
    return out


# --------------------------------------------------------------------------- #
# images and colours (imagecheck)
# --------------------------------------------------------------------------- #
def _mm(t) -> str:
    return f"{t[0]:.0f} × {t[1]:.0f} mm"


def _img_spot(u) -> Spot:
    return Spot(
        u.page,
        getattr(u, "bbox", None),
        tr("{0:.0f} dpi, {1} × {2} px, {3}").format(u.dpi, u.px[0], u.px[1], u.space or "?"),
    )


def _image_issues(rep: Report) -> list:
    from . import imagecheck as ic

    cr = rep.colors
    if cr is None:
        return []
    out = []
    by_page: dict = {}
    hdr_aux = {h["aux"] + 1 for h in (rep.hdr or [])}  # grey HDR extra page: a finding of its own
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
            worst.good, _mm(a), worst.ok, _mm(b)
        )
        if lim and p in cr.page_size_mm and lim[1] < 0.995:
            ps = cr.page_size_mm[p]
            txt += " " + tr(
                "Ganze Seite höchstens {0:.0f} % ({1}) bei {2} dpi bzw. {3:.0f} % ({4}) bei {5} dpi."
            ).format(
                lim[1] * 100,
                _mm((ps[0] * lim[1], ps[1] * lim[1])),
                ic.GOOD_DPI,
                min(lim[2], 9.99) * 100,
                _mm((ps[0] * min(lim[2], 9.99), ps[1] * min(lim[2], 9.99))),
                ic.OK_DPI,
            )
        return txt

    for pages, sev, kind in ((low_pages, "warning", "low"), (ok_pages, "info", "ok")):
        if len(pages) > 8:  # many pages: one collective message
            worst = min((u for p in pages for u in by_page[p] if u.rating == kind), key=lambda u: u.dpi)
            msg = (
                tr("Bilder unter {0} dpi auf {1} Seiten – niedrigste {2:.0f} dpi (Seite {3}).")
                if kind == "low"
                else tr("Bilder mit {0}–{1} dpi auf {2} Seiten – gut für Plakat/Großformat, für Nahbetrachtung knapp.")
            )
            out.append(
                Issue(
                    sev,
                    "image",
                    msg.format(worst.ok, len(pages), worst.dpi, worst.page)
                    if kind == "low"
                    else msg.format(ic.OK_DPI, ic.GOOD_DPI - 1, len(pages)),
                    pages,
                    [_img_spot(u) for p in pages for u in by_page[p] if u.rating == kind],
                )
            )
            continue
        for p in pages:
            us = [u for u in by_page[p] if u.rating == kind]
            worst = min(us, key=lambda u: u.dpi)
            head = (
                tr("Seite {0}: {1} Bild(er) unter {2} dpi – niedrigste {3:.0f} dpi ({4} × {5} px auf {6}).")
                if kind == "low"
                else tr(
                    "Seite {0}: {1} Bild(er) mit {3:.0f}–{2} dpi ({4} × {5} px auf {6}) – gut für Plakat/"
                    "Großformat, für Nahbetrachtung knapp."
                )
            )
            msg = head.format(
                p,
                len(us),
                worst.ok if kind == "low" else worst.good - 1,
                worst.dpi,
                worst.px[0],
                worst.px[1],
                _mm(worst.placed_mm),
            )
            out.append(Issue(sev, "image", msg + " " + advice(p, worst), [p], [_img_spot(u) for u in us]))
    rgb = sorted(p for p, c in cr.page_colors.items() if "RGB" in c)
    if rgb:
        n_img = sum(1 for u in cr.images if u.space == "RGB")
        spots = [_img_spot(u) for u in cr.images if u.space == "RGB" and u.page in rgb]
        with_img = {sp.page for sp in spots}
        spots += [Spot(p, None, tr("RGB-Farben (Text/Grafik)")) for p in rgb if p not in with_img]
        out.append(
            Issue(
                "info",
                "image",
                tr(
                    "RGB-Inhalte auf {0} Seite(n) ({1} Bildplatzierung(en) in RGB) – für "
                    "Offset/Digitaldruck nach CMYK umwandeln (Druckaufbereitung → CMYK); "
                    "Plotter/Großformat drucken RGB meist direkt."
                ).format(len(rgb), n_img),
                rgb,
                sorted(spots, key=lambda sp: sp.page),
            )
        )
    names = sorted({n for ns in cr.spots.values() for n in ns})
    if names:
        out.append(
            Issue(
                "info",
                "image",
                tr("Sonderfarben: {0}.").format(", ".join(names)),
                sorted(cr.spots),
                [Spot(p, None, ", ".join(sorted(cr.spots[p]))) for p in sorted(cr.spots)],
            )
        )
    return out


def colors_text(rep: Report) -> list:
    """Images and colours as text lines (for the report and the panel)."""
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
# HDR photos opened as two pages (photo + grey gain map)
# --------------------------------------------------------------------------- #
def _single_image(page):
    """Page that consists of a single image only (as when opening a photo) -> (name, image) or None."""
    import pikepdf

    try:
        ops = list(pikepdf.parse_content_stream(page))
    except Exception:  # noqa: BLE001 – malformed PDF object: skipped or default value
        return None
    names = [str(getattr(i, "operator", "")) for i in ops]
    if any(n not in ("q", "Q", "cm", "Do") for n in names) or names.count("Do") != 1:
        return None
    nm = str(ops[names.index("Do")].operands[0])
    x = (page_resources(page).get("/XObject") or {}).get(nm)
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
    except Exception:  # noqa: BLE001 – malformed PDF object: skipped or default value
        pass
    return 0


def hdr_aux_pages(pdf) -> list:
    """Pairs (photo, grey gain map) of consecutive image pages – that is how img2pdf opens HDR photos
    from a phone if they were not repaired. Same aspect ratio, map grey and not larger.
    """
    out, pages = [], list(pdf.pages)
    i = 0
    while i + 1 < len(pages):
        a, b = _single_image(pages[i]), _single_image(pages[i + 1])
        if a and b:
            ia, ib = a[1], b[1]
            try:
                aw, ah, bw, bh = int(ia.Width), int(ia.Height), int(ib.Width), int(ib.Height)
            except Exception:  # noqa: BLE001 – malformed PDF object: skipped or default value
                aw = ah = bw = bh = 0
            if (
                aw
                and bw
                and _components(ia) >= 3
                and _components(ib) == 1
                and bw <= aw
                and bh <= ah
                and abs(aw / ah - bw / bh) <= 0.02 * aw / ah
            ):
                pa, pb = [float(v) for v in pages[i].mediabox], [float(v) for v in pages[i + 1].mediabox]
                out.append(
                    {
                        "main": i,
                        "aux": i + 1,
                        "main_px": (aw, ah),
                        "aux_px": (bw, bh),
                        "main_dpi": aw / ((pa[2] - pa[0]) / 72.0),
                        "aux_dpi": bw / ((pb[2] - pb[0]) / 72.0),
                        "aux_mode": "L",
                        "kind": tr("HDR-Foto"),
                    }
                )
                i += 2
                continue
        i += 1
    return out


def remove_hdr_aux(data: bytes, size: str = "aux", merge: bool = False) -> bytes:
    """Remove the HDR extra pages. size: "aux" = the photo page gets the size of the extra page,
    "main" = size stays. merge: apply the gain map to the photo (new JPEG).
    """
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
                except Exception:  # noqa: BLE001 – malformed PDF object: skipped or default value
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
# findings
# --------------------------------------------------------------------------- #
HAIRLINE_MM = 0.1  # thinner lines are hardly or not at all visible on plotters/laser printers


def _mm_num(v: float) -> str:
    from .planprint import mm_text

    return mm_text(v)


def _hairlines(data: bytes, rep: Report, max_pages: int = 200) -> None:
    """Hairlines per page (count + areas in rep.located[("line",)])."""
    import pypdfium2 as pdfium

    from .planprint import hairline_boxes

    doc = pdfium.PdfDocument(data)
    try:
        rep.hairlines = {}
        for i in range(min(len(doc), max_pages)):
            n, boxes = hairline_boxes(doc, i, HAIRLINE_MM)
            if n:
                rep.hairlines[i + 1] = n
                rep.located.setdefault(("line",), {})[i + 1] = boxes
    finally:
        doc.close()


def _located_spots(rep: Report, key: tuple, pages, label: str = "") -> list:
    """Locations from rep.located (areas per page), pages without an area as a whole page."""
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


def _font_issues(rep: Report) -> list[Issue]:
    """Fonts: not embedded, standard fonts, Type3, no Unicode mapping."""
    out = []
    for f in rep.fonts:
        pg = sorted(f.pages)
        n0 = len(out)
        if f.status == "missing":
            if f.encoding == "private":
                out.append(
                    Issue(
                        "error",
                        "font",
                        tr(
                            "Schrift „{0}“ ist nicht eingebettet und verwendet eigene Zeichennamen – "
                            "ohne die Originalschrift nicht reparierbar (Text fehlt oder wird "
                            "zu Fremdzeichen)."
                        ).format(f.name),
                        pg,
                    )
                )
            elif f.cid and f.encoding.startswith("Identity"):
                out.append(
                    Issue(
                        "error",
                        "font",
                        tr(
                            "Schrift „{0}“ ist nicht eingebettet (CID, Identity) – ohne die "
                            "Originalschrift nicht reparierbar."
                        ).format(f.name),
                        pg,
                    )
                )
            else:
                hint = (
                    tr(" Ersatz: {0}.").format(f.suggestion_name) if f.suggestion_name else tr(" Kein Ersatz gefunden.")
                )
                out.append(
                    Issue(
                        "error",
                        "font",
                        tr("Schrift „{0}“ ist nicht eingebettet – Darstellung kann abweichen.").format(f.name) + hint,
                        pg,
                    )
                )
        elif f.status == "std14":
            out.append(
                Issue(
                    "info",
                    "font",
                    tr("Standardschrift „{0}“ nicht eingebettet (wird meist korrekt ersetzt).").format(f.name),
                    pg,
                )
            )
        elif f.status == "type3":
            out.append(
                Issue(
                    "info",
                    "font",
                    tr("Type3-Schrift „{0}“ (oft aus CAD) – Text ggf. nicht durchsuchbar.").format(f.name),
                    pg,
                )
            )
        if (
            not f.tounicode
            and f.status != "std14"
            and f.encoding not in ("WinAnsiEncoding", "MacRomanEncoding", "StandardEncoding")
        ):
            out.append(
                Issue(
                    "info",
                    "font",
                    tr("Schrift „{0}“ ohne Unicode-Zuordnung – Kopieren/Suchen kann falsche Zeichen liefern.").format(
                        f.name
                    ),
                    pg,
                )
            )
        for i in out[n0:]:
            i.spots = _located_spots(rep, ("font", f.name), pg, f.name)
    return out


def _text_issues(rep: Report) -> list[Issue]:
    """Characters without a valid mapping (garbled text)."""
    out = []
    for p, n in sorted(rep.garbled.items()):
        out.append(
            Issue(
                "warning",
                "text",
                tr("Seite {0}: {1} Zeichen ohne gültige Zuordnung (seltsame Zeichen).").format(p, n),
                [p],
            )
        )
    return out


def _layer_issues(rep: Report) -> list[Issue]:
    """Layers: hidden, different for view and print, content outside the page."""
    out = []
    hidden = [L for L in rep.layers if not L.view_on or L.print_on is False]
    if hidden:
        out.append(
            Issue(
                "warning",
                "layer",
                tr(
                    "{0} ausgeblendete Ebene(n) – viele Drucker/RIPs ignorieren das und "
                    "drucken sie trotzdem. Empfehlung: „Sichtbaren Zustand festschreiben“."
                ).format(len(hidden)),
                sorted(set().union(*[L.pages for L in hidden])),
            )
        )
    for L in rep.layers:
        if L.print_on is not None and L.print_on != L.view_on:
            out.append(
                Issue(
                    "warning",
                    "layer",
                    tr("Ebene „{0}“: Ansicht {1}, Druck {2}.").format(
                        L.name, tr("an") if L.view_on else tr("aus"), tr("an") if L.print_on else tr("aus")
                    ),
                    sorted(L.pages),
                )
            )
        if L.outside_pct is not None and L.outside_pct > 25:
            out.append(
                Issue(
                    "warning",
                    "layer",
                    tr("Ebene „{0}“: {1:.0f} % des Inhalts liegen außerhalb der Seite (verrutscht?).").format(
                        L.name, L.outside_pct
                    ),
                    sorted(L.pages),
                )
            )
    return out


def _line_issues(rep: Report) -> list[Issue]:
    """Hairlines."""
    out = []
    if rep.hairlines:
        pg = sorted(rep.hairlines)
        out.append(
            Issue(
                "warning",
                "line",
                tr(
                    "{0} Linie(n) dünner als {1} mm auf {2} Seite(n) – auf Plottern und "
                    "Laserdruckern kaum oder gar nicht sichtbar. Beim Plandruck lassen sie "
                    "sich mit „Haarlinien anheben“ verstärken."
                ).format(sum(rep.hairlines.values()), _mm_num(HAIRLINE_MM), len(pg)),
                pg,
                _located_spots(rep, ("line",), pg),
            )
        )
    return out


def _size_issues(rep: Report) -> list[Issue]:
    """File size (see shrink.issues)."""
    out = []
    if rep.size is not None:
        from . import shrink

        out += [Issue(sev, "size", msg, []) for sev, msg in shrink.issues(rep.size)]
    return out


def _hdr_issues(rep: Report) -> list[Issue]:
    """Auxiliary pages of HDR photos (gain maps)."""
    out = []
    for h in rep.hdr:
        out.append(
            Issue(
                "warning",
                "image",
                tr(
                    "Seite {0}: graues Zusatzbild eines HDR-Fotos (Helligkeitskarte zu Seite "
                    "{1}) – wird in anderer Größe mitgedruckt, am Plotter mit falschen "
                    "Farben. Reparatur: „HDR-Zusatzseiten entfernen“."
                ).format(h["aux"] + 1, h["main"] + 1),
                [h["aux"] + 1],
            )
        )
    return out


def _transparency_issues(rep: Report) -> list[Issue]:
    """Transparency: gradients with a soft mask, blend modes and groups, overprint."""
    out = []
    grad = sorted(p for p, k in rep.transparency.items() if "pattern_smask" in k)
    if grad:
        out.append(
            Issue(
                "warning",
                "transparency",
                tr(
                    "Transparente Verläufe (Soft-Maske im Muster) auf {0} Seite(n) – "
                    "manche RIPs/Plotter drucken sie als schwarze Fläche und decken "
                    "darunterliegende Bilder ab. Reparatur: „Transparente Verläufe in "
                    "Bilder umwandeln“."
                ).format(len(grad)),
                grad,
                _located_spots(rep, ("transparency",), grad),
            )
        )
    risky = {p for p, k in rep.transparency.items() if k & {"smask", "blend", "group"} and "pattern_smask" not in k}
    if risky:
        out.append(
            Issue(
                "info",
                "transparency",
                tr(
                    "Transparenzen auf {0} Seite(n) – auf älteren Druckern/RIPs ggf. „Transparenzen reduzieren“."
                ).format(len(risky)),
                sorted(risky),
                _located_spots(rep, ("transparency",), risky),
            )
        )
    op = {p for p, k in rep.transparency.items() if "overprint" in k}
    if op:
        out.append(Issue("info", "transparency", tr("Überdrucken auf {0} Seite(n).").format(len(op)), sorted(op)))
    return out


def _box_spots(found: dict, label: str = "") -> list:
    return [Spot(p, b, label) for p in sorted(found) for b in _merge_boxes(found[p])]


def _overprint_issues(rep: Report) -> list[Issue]:
    """White objects that overprint (disappear), small black text that knocks out (white edges)."""
    out = []
    op = rep.overprint or {}
    white = op.get("white") or {}
    if white:
        out.append(
            Issue(
                "error",
                "overprint",
                tr(
                    "{0} weiße(s) Objekt(e) auf Überdrucken gestellt – sie verschwinden im Druck "
                    "(Druckmaschine, RIP mit Überdrucken). Reparatur: „Überdrucken korrigieren“."
                ).format(sum(len(v) for v in white.values())),
                sorted(white),
                _box_spots(white),
            )
        )
    black = op.get("black_text") or {}
    if black:
        out.append(
            Issue(
                "warning",
                "overprint",
                tr(
                    "Kleiner schwarzer Text (bis 12 pt) spart aus statt zu überdrucken – schon kleinste "
                    "Passerschwankungen zeigen weiße Ränder ({0} Stelle(n)). Reparatur: „Überdrucken korrigieren“."
                ).format(sum(len(v) for v in black.values())),
                sorted(black),
                _box_spots(black),
            )
        )
    return out


def _issues_raw(rep: Report) -> list[Issue]:
    out = []
    for part in (
        _font_issues,
        _text_issues,
        _layer_issues,
        _line_issues,
        _image_issues,
        _size_issues,
        _hdr_issues,
        _transparency_issues,
        _overprint_issues,
        _geometry_issues,
        _doc_issues,
    ):
        out += part(rep)
    out.sort(key=lambda i: (SEV_ORDER[i.severity], i.category))
    return out


def report_text(rep: Report, title: str = "") -> str:
    """Report as text (for saving/passing on)."""
    lines = [tr("Passermark – Prüfbericht") + (f": {title}" if title else ""), ""]
    c = rep.counts()
    lines.append(
        tr("{0} Fehler, {1} Warnung(en), {2} Hinweis(e) · {3} Seiten").format(
            c["error"], c["warning"], c["info"], rep.pages
        )
    )
    lines.append("")
    sev = {"error": tr("FEHLER"), "warning": tr("WARNUNG"), "info": tr("HINWEIS")}
    for i in rep.issues:
        lines.append(
            f"[{sev[i.severity]}] {i.message}" + (tr("  (Seiten {0})").format(_pages_str(i.pages)) if i.pages else "")
        )
        located = [sp for sp in i.spots if sp.box is not None or sp.label]
        for sp in located[:12]:
            lines.append("    · " + where_text(rep, sp))
        if len(located) > 12:
            lines.append("    · " + tr("… und {0} weitere").format(len(located) - 12))
    lines += ["", tr("Schriften:")]
    for f in rep.fonts:
        st = {
            "ok": tr("eingebettet"),
            "std14": tr("Standard, nicht eingebettet"),
            "missing": tr("NICHT eingebettet"),
            "type3": "Type3",
        }[f.status]
        lines.append(
            f"  {f.name}  ·  {f.subtype}  ·  {st}"
            + (tr("  ·  Teilmenge") if f.subset else "")
            + (f"  ·  → {f.suggestion_name}" if f.suggestion_name else "")
        )
    if rep.colors is not None and (rep.colors.images or rep.colors.page_colors):
        lines += ["", tr("Farben:")] + ["  " + x for x in colors_text(rep)]
        if rep.colors.images:
            lines += ["", tr("Bilder (Seite · Pixel · platziert · Auflösung · Farbraum · max. bei 300 / 150 dpi):")]
            for u in rep.colors.images:
                from .imagecheck import space_label

                lines.append(
                    f"  {u.page} · {u.px[0]}×{u.px[1]} px · {_mm(u.placed_mm)} · {u.dpi:.0f} dpi · {space_label(u.space)}"
                    + (f" ({u.profile})" if u.profile else "")
                    + f" · {_mm(u.max_mm(u.good))} / {_mm(u.max_mm(u.ok))}"
                )
    if rep.size is not None:
        from . import shrink

        lines += ["", tr("Dateigröße:")] + ["  " + x for x in shrink.summary_lines(rep.size, top=8)]
    if rep.geometry:
        lines += ["", tr("Seitenrahmen (erste Seite):")]
        g = rep.geometry[min(rep.geometry)]
        for k, lab in (
            ("media", "MediaBox"),
            ("crop", "CropBox"),
            ("bleed", "BleedBox"),
            ("trim", "TrimBox"),
            ("art", "ArtBox"),
        ):
            if g[k]:
                lines.append(f"  {lab}: {_fmt_box(g[k])}")
        b = bleed_mm(g)
        if b:
            lines.append(
                "  "
                + tr("Beschnitt:")
                + " "
                + ", ".join(f"{tr(SIDE_TEXT[k])} {v:.1f} mm".replace(".", ",") for k, v in b.items())
            )
    if rep.layers:
        lines += ["", tr("Ebenen:")]
        for L in rep.layers:
            lines.append(
                f"  {L.name}  ·  "
                + tr("Ansicht {0}, Druck {1}").format(
                    tr("an") if L.view_on else tr("aus"),
                    tr("wie Ansicht") if L.print_on is None else (tr("an") if L.print_on else tr("aus")),
                )
            )
    return "\n".join(lines) + "\n"
