# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Check images and colours: colour space (RGB/CMYK/grey/spot) with the ICC profile name,
the effective resolution of every placed image (also inside forms, also when used several times) and
the resulting maximum print size. pikepdf only – may run in the background.

Effective resolution = pixels / placed size on the page (via the transformation matrix),
i.e. what actually arrives when printing at original size.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .l10n import tr

MM = 72.0 / 25.4
GOOD_DPI, OK_DPI = 300, 150  # close viewing / poster, large format
GOOD_DPI_1BIT, OK_DPI_1BIT = 600, 300  # line art (1 bit)
MIN_PLACED_MM = 2.0  # do not rate tiny placements (dots, lines)


@dataclass
class ImageUse:
    """One placement of an image on a page: pixel size, placed size, effective resolution, colour space."""

    page: int  # 1-based
    name: str
    px: tuple  # (width, height) in pixels
    placed_mm: tuple  # (width, height) on the page
    dpi: float  # effective (smaller direction)
    space: str  # "RGB" | "CMYK" | "Grau" | "Sonderfarbe …" | …
    profile: str = ""  # ICC profile name (if embedded)
    bits: int = 8
    codec: str = ""  # JPEG | ZIP | JPEG 2000 | CCITT | JBIG2 | …
    mask: bool = False  # 1-bit mask (line art)
    key: tuple | None = None  # Objektnummer des Bildes (None = eingebettet/inline)
    bbox: tuple | None = None  # (x0, y0, x1, y1) in pt, page coordinates – where it lies on the page

    def max_mm(self, dpi: float) -> tuple:
        """Largest print size at this resolution."""
        return (self.px[0] / dpi * 25.4, self.px[1] / dpi * 25.4)

    @property
    def good(self) -> float:
        """Resolution from which this image counts as good (higher for 1-bit line art)."""
        return GOOD_DPI_1BIT if self.bits == 1 else GOOD_DPI

    @property
    def ok(self) -> float:
        """Resolution from which this image counts as acceptable."""
        return OK_DPI_1BIT if self.bits == 1 else OK_DPI

    @property
    def rating(self) -> str:
        """Rating of the resolution: good, ok, low – or tiny for placements too small to judge."""
        if min(self.placed_mm) < MIN_PLACED_MM:
            return "tiny"
        return "good" if self.dpi >= self.good * 0.98 else "ok" if self.dpi >= self.ok * 0.98 else "low"


@dataclass
class ColorReport:
    """Images and colours of a document: image placements, colour spaces and spot colours per page."""

    images: list = field(default_factory=list)  # [ImageUse]
    page_colors: dict = field(default_factory=dict)  # page -> {"RGB", "CMYK", "Grau", "Sonderfarbe X", …}
    page_size_mm: dict = field(default_factory=dict)  # page -> (w, h)
    output_intent: str = ""  # Profilname des Output-Intents (PDF/X)
    spots: dict = field(default_factory=dict)  # page -> {spot colour name}
    truncated: bool = False


# --------------------------------------------------------------------------- #
# ICC profile name
# --------------------------------------------------------------------------- #
def icc_name(data: bytes) -> str:
    """Description (tag "desc") of an ICC profile – v2 (desc) and v4 (mluc)."""
    try:
        n = int.from_bytes(data[128:132], "big")
        for k in range(min(n, 200)):
            e = 132 + 12 * k
            sig = data[e : e + 4]
            off = int.from_bytes(data[e + 4 : e + 8], "big")
            if sig != b"desc":
                continue
            typ = data[off : off + 4]
            if typ == b"desc":
                cnt = int.from_bytes(data[off + 8 : off + 12], "big")
                return data[off + 12 : off + 12 + max(0, cnt - 1)].decode("latin-1").strip("\x00 ").strip()
            if typ == b"mluc":
                rlen = int.from_bytes(data[off + 20 : off + 24], "big")
                roff = int.from_bytes(data[off + 24 : off + 28], "big")
                return data[off + roff : off + roff + rlen].decode("utf-16-be", "replace").strip("\x00 ").strip()
    except Exception:
        pass
    return ""


def _icc_of(stream) -> str:
    try:
        return icc_name(stream.read_bytes())
    except Exception:
        return ""


# --------------------------------------------------------------------------- #
# colour spaces
# --------------------------------------------------------------------------- #
def describe_space(cs, res=None, depth=0) -> tuple[str, str]:
    """PDF colour space -> (kind, ICC profile name). Kind: RGB, CMYK, Grau, Lab, Sonderfarbe „X“, DeviceN, Muster."""
    import pikepdf

    if cs is None or depth > 4:
        return "", ""
    if isinstance(cs, pikepdf.Name):
        n = str(cs)
        base = {
            "/DeviceRGB": "RGB",
            "/DeviceCMYK": "CMYK",
            "/DeviceGray": "Grau",
            "/RGB": "RGB",
            "/CMYK": "CMYK",
            "/G": "Grau",
            "/Pattern": "Muster",
        }.get(n)
        if base:
            return base, ""
        named = (res.get("/ColorSpace") or {}).get(n) if res is not None else None
        return describe_space(named, res, depth + 1) if named is not None else ("", "")
    if isinstance(cs, pikepdf.Array) and len(cs) == 1:
        return describe_space(cs[0], res, depth + 1)  # [/DeviceCMYK] and the like
    if isinstance(cs, pikepdf.Array) and len(cs):
        kind = str(cs[0])
        if kind == "/ICCBased":
            st = cs[1]
            ncomp = int(st.get("/N", 0))
            return {1: "Grau", 3: "RGB", 4: "CMYK"}.get(ncomp, f"ICC ({ncomp})"), _icc_of(st)
        if kind in ("/CalRGB",):
            return "RGB", ""
        if kind in ("/CalGray",):
            return "Grau", ""
        if kind == "/Lab":
            return "Lab", ""
        if kind in ("/Indexed", "/I"):
            b, p = describe_space(cs[1], res, depth + 1)
            return f"{tr('Indiziert')} ({b})", p
        if kind == "/Separation":
            name = str(cs[1]).lstrip("/")
            if name in ("All", "None"):
                return "", ""
            label = tr("Sonderfarbe „{0}“").format(name)
            SPOT_NAMES[label] = [name]
            return label, ""
        if kind == "/DeviceN":
            names = [str(x).lstrip("/") for x in cs[1]]
            if set(names) <= {"Cyan", "Magenta", "Yellow", "Black", "None"}:
                return "CMYK", ""
            label = "DeviceN (" + ", ".join(names[:4]) + ")"
            SPOT_NAMES[label] = [n for n in names if n not in ("Cyan", "Magenta", "Yellow", "Black", "None")]
            return label, ""
        if kind == "/Pattern":
            return "Muster", ""
    return "", ""


_BASE = {"RGB", "CMYK", "Grau", "Lab"}
SPOT_NAMES: dict = {}  # display label -> spot colour names


def space_label(s: str) -> str:
    """Colour space for display (basic kinds translated, e.g. RGB -> RVB in French)."""
    if s in _BASE:
        return {"RGB": tr("RGB"), "CMYK": tr("CMYK"), "Grau": tr("Grau"), "Lab": tr("Lab")}[s]
    if s.startswith(tr("Indiziert")) and "(" in s:
        inner = s[s.index("(") + 1 : s.rindex(")")]
        return f"{tr('Indiziert')} ({space_label(inner)})"
    return s


def _codec(img) -> str:
    import pikepdf

    f = img.get("/Filter")
    fl = [str(x) for x in f] if isinstance(f, pikepdf.Array) else ([str(f)] if f is not None else [])
    names = {
        "/DCTDecode": "JPEG",
        "/DCT": "JPEG",
        "/FlateDecode": "ZIP",
        "/Fl": "ZIP",
        "/JPXDecode": "JPEG 2000",
        "/CCITTFaxDecode": "CCITT",
        "/JBIG2Decode": "JBIG2",
        "/RunLengthDecode": "RLE",
        "/LZWDecode": "LZW",
    }
    return " + ".join(names.get(x, x.lstrip("/")) for x in fl) or tr("unkomprimiert")


def _mul(a, b):
    return (
        a[0] * b[0] + a[1] * b[2],
        a[0] * b[1] + a[1] * b[3],
        a[2] * b[0] + a[3] * b[2],
        a[2] * b[1] + a[3] * b[3],
        a[4] * b[0] + a[5] * b[2] + b[4],
        a[4] * b[1] + a[5] * b[3] + b[5],
    )


def _nums(ins):
    out = []
    for o in ins.operands:
        try:
            out.append(float(o))
        except (TypeError, ValueError):
            return []
    return out


# --------------------------------------------------------------------------- #
# analysis
# --------------------------------------------------------------------------- #
def analyze(pdf, max_uses: int = 2000) -> ColorReport:
    """pikepdf-Dokument -> ColorReport."""
    import math
    import pikepdf

    rep = ColorReport()
    try:
        for oi in pdf.Root.get("/OutputIntents") or []:
            prof = oi.get("/DestOutputProfile")
            name = _icc_of(prof) if prof is not None else ""
            rep.output_intent = name or str(oi.get("/OutputConditionIdentifier", "") or "")
            if rep.output_intent:
                break
    except Exception:
        pass

    def add_color(pno, label):
        if label and label != "Muster":
            rep.page_colors.setdefault(pno, set()).add(label)
            if label in SPOT_NAMES:
                rep.spots.setdefault(pno, set()).update(SPOT_NAMES[label])

    def image_use(pno, name, img, ctm, res):
        if len(rep.images) >= max_uses:
            rep.truncated = True
            return
        try:
            w, h = int(img.get("/Width", 0)), int(img.get("/Height", 0))
        except Exception:
            return
        if not w or not h:
            return
        pw = math.hypot(ctm[0], ctm[1]) / MM  # image unit square -> page
        ph = math.hypot(ctm[2], ctm[3]) / MM
        if pw <= 0 or ph <= 0:
            return
        dpi = min(w / (pw / 25.4), h / (ph / 25.4))
        is_mask = bool(img.get("/ImageMask", False))
        bits = 1 if is_mask else int(img.get("/BitsPerComponent", 8) or 8)
        if is_mask:
            space, prof = tr("Maske (1 Bit)"), ""
        else:
            space, prof = describe_space(img.get("/ColorSpace"), res)
            if not space and _codec(img) == "JPEG 2000":
                space = tr("im JPEG 2000 enthalten")
        try:
            key = img.objgen if img.objgen != (0, 0) else None
        except Exception:
            key = None
        pts = [
            (ctm[4] + ctm[0] * u + ctm[2] * v, ctm[5] + ctm[1] * u + ctm[3] * v)
            for u, v in ((0, 0), (1, 0), (0, 1), (1, 1))
        ]
        bbox = (min(x for x, _ in pts), min(y for _, y in pts), max(x for x, _ in pts), max(y for _, y in pts))
        rep.images.append(
            ImageUse(pno, name, (w, h), (pw, ph), dpi, space, prof, bits, _codec(img), is_mask, key, bbox)
        )
        if not is_mask:
            add_color(pno, space)

    def walk(pno, ops, res, ctm, depth, seen_forms):
        if depth > 10:
            return
        stack = []
        for ins in ops:
            op = str(getattr(ins, "operator", ""))
            if op == "q":
                stack.append(ctm)
            elif op == "Q":
                ctm = stack.pop() if stack else ctm
            elif op == "cm":
                v = _nums(ins)
                if len(v) == 6:
                    ctm = _mul(tuple(v), ctm)
            elif op in ("rg", "RG"):
                add_color(pno, "RGB")
            elif op in ("k", "K"):
                add_color(pno, "CMYK")
            elif op in ("g", "G"):
                add_color(pno, "Grau")
            elif op in ("cs", "CS") and ins.operands:
                add_color(pno, describe_space(ins.operands[0], res)[0])
            elif op == "Do" and ins.operands:
                nm = str(ins.operands[0])
                x = (res.get("/XObject") or {}).get(nm)
                if x is None:
                    continue
                try:
                    sub = x.get("/Subtype")
                except Exception:
                    continue
                if sub == pikepdf.Name.Image:
                    image_use(pno, nm, x, ctm, res)
                elif sub == pikepdf.Name.Form:
                    og = x.objgen
                    if og in seen_forms:  # prevent recursion
                        continue
                    m = tuple(float(v) for v in x.get("/Matrix", [1, 0, 0, 1, 0, 0]))
                    try:
                        sub_ops = pikepdf.parse_content_stream(x)
                    except Exception:
                        continue
                    walk(pno, sub_ops, x.get("/Resources") or res, _mul(m, ctm), depth + 1, seen_forms | {og})
            elif op == "INLINE IMAGE":
                try:
                    ii = ins.iimage
                    d = ii.obj if hasattr(ii, "obj") else None
                    if d is not None:
                        image_use(pno, tr("(eingebettet)"), d, ctm, res)
                except Exception:
                    pass

    for pno, page in enumerate(pdf.pages, start=1):
        try:
            mb = [float(v) for v in page.mediabox]
            rep.page_size_mm[pno] = ((mb[2] - mb[0]) / MM, (mb[3] - mb[1]) / MM)
            res = page.obj.get("/Resources")
            if res is None:
                node = page.obj.get("/Parent")
                while node is not None and res is None:
                    res = node.get("/Resources")
                    node = node.get("/Parent")
            walk(
                pno,
                pikepdf.parse_content_stream(page),
                res or pikepdf.Dictionary(),
                (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
                0,
                frozenset(),
            )
        except Exception:
            continue
    return rep


def page_limits(rep: ColorReport) -> dict:
    """Page -> (lowest dpi, max. enlargement at 300 dpi, at 150 dpi) – only images that can be rated."""
    out = {}
    for u in rep.images:
        if u.mask or u.rating == "tiny":
            continue
        cur = out.get(u.page)
        if cur is None or u.dpi < cur[0]:
            out[u.page] = (u.dpi, u.dpi / GOOD_DPI, u.dpi / OK_DPI)
    return out
