# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Bilder und Farben prüfen: Farbraum (RGB/CMYK/Grau/Sonderfarbe) mit ICC-Profilname,
effektive Auflösung jedes platzierten Bildes (auch in Formularen, auch mehrfach verwendet) und
die daraus folgende maximale Druckgröße. Nur pikepdf – darf im Hintergrund laufen.

Effektive Auflösung = Pixel / platzierte Größe auf der Seite (über die Transformationsmatrix),
also das, was beim Druck in Originalgröße tatsächlich ankommt.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .l10n import tr

MM = 72.0 / 25.4
GOOD_DPI, OK_DPI = 300, 150              # Nahbetrachtung / Plakat, Großformat
GOOD_DPI_1BIT, OK_DPI_1BIT = 600, 300    # Strichbilder (1 Bit)
MIN_PLACED_MM = 2.0                      # winzige Platzierungen (Punkte, Linien) nicht bewerten


@dataclass
class ImageUse:
    page: int                  # 1-basiert
    name: str
    px: tuple                  # (Breite, Höhe) in Pixeln
    placed_mm: tuple           # (Breite, Höhe) auf der Seite
    dpi: float                 # effektiv (kleinere Richtung)
    space: str                 # "RGB" | "CMYK" | "Grau" | "Sonderfarbe …" | …
    profile: str = ""          # ICC-Profilname (falls eingebettet)
    bits: int = 8
    codec: str = ""            # JPEG | ZIP | JPEG 2000 | CCITT | JBIG2 | …
    mask: bool = False         # 1-Bit-Maske (Strich)
    key: tuple | None = None   # Objektnummer des Bildes (None = eingebettet/inline)

    def max_mm(self, dpi: float) -> tuple:
        """Größte Druckgröße bei dieser Auflösung."""
        return (self.px[0] / dpi * 25.4, self.px[1] / dpi * 25.4)

    @property
    def good(self) -> float:
        return GOOD_DPI_1BIT if self.bits == 1 else GOOD_DPI

    @property
    def ok(self) -> float:
        return OK_DPI_1BIT if self.bits == 1 else OK_DPI

    @property
    def rating(self) -> str:
        if min(self.placed_mm) < MIN_PLACED_MM:
            return "tiny"
        return "good" if self.dpi >= self.good * 0.98 else "ok" if self.dpi >= self.ok * 0.98 else "low"


@dataclass
class ColorReport:
    images: list = field(default_factory=list)            # [ImageUse]
    page_colors: dict = field(default_factory=dict)       # Seite -> {"RGB", "CMYK", "Grau", "Sonderfarbe X", …}
    page_size_mm: dict = field(default_factory=dict)      # Seite -> (b, h)
    output_intent: str = ""                               # Profilname des Output-Intents (PDF/X)
    spots: dict = field(default_factory=dict)             # Seite -> {Sonderfarbenname}
    truncated: bool = False


# --------------------------------------------------------------------------- #
# ICC-Profilname
# --------------------------------------------------------------------------- #
def icc_name(data: bytes) -> str:
    """Beschreibung (Tag „desc“) eines ICC-Profils – v2 (desc) und v4 (mluc)."""
    try:
        n = int.from_bytes(data[128:132], "big")
        for k in range(min(n, 200)):
            e = 132 + 12 * k
            sig = data[e:e + 4]
            off = int.from_bytes(data[e + 4:e + 8], "big")
            if sig != b"desc":
                continue
            typ = data[off:off + 4]
            if typ == b"desc":
                cnt = int.from_bytes(data[off + 8:off + 12], "big")
                return data[off + 12:off + 12 + max(0, cnt - 1)].decode("latin-1").strip("\x00 ").strip()
            if typ == b"mluc":
                rlen = int.from_bytes(data[off + 20:off + 24], "big")
                roff = int.from_bytes(data[off + 24:off + 28], "big")
                return data[off + roff:off + roff + rlen].decode("utf-16-be", "replace").strip("\x00 ").strip()
    except Exception:
        pass
    return ""


def _icc_of(stream) -> str:
    try:
        return icc_name(stream.read_bytes())
    except Exception:
        return ""


# --------------------------------------------------------------------------- #
# Farbräume
# --------------------------------------------------------------------------- #
def describe_space(cs, res=None, depth=0) -> tuple[str, str]:
    """PDF-Farbraum -> (Art, ICC-Profilname). Art: RGB, CMYK, Grau, Lab, Sonderfarbe „X“, DeviceN (…), Muster."""
    import pikepdf
    if cs is None or depth > 4:
        return "", ""
    if isinstance(cs, pikepdf.Name):
        n = str(cs)
        base = {"/DeviceRGB": "RGB", "/DeviceCMYK": "CMYK", "/DeviceGray": "Grau", "/RGB": "RGB",
                "/CMYK": "CMYK", "/G": "Grau", "/Pattern": "Muster"}.get(n)
        if base:
            return base, ""
        named = (res.get("/ColorSpace") or {}).get(n) if res is not None else None
        return describe_space(named, res, depth + 1) if named is not None else ("", "")
    if isinstance(cs, pikepdf.Array) and len(cs) == 1:
        return describe_space(cs[0], res, depth + 1)     # [/DeviceCMYK] u. Ä.
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
SPOT_NAMES: dict = {}                    # Anzeige-Bezeichnung -> Sonderfarbennamen


def space_label(s: str) -> str:
    """Farbraum für die Anzeige (Grundarten übersetzt, z. B. RGB -> RVB auf Französisch)."""
    if s in _BASE:
        return {"RGB": tr("RGB"), "CMYK": tr("CMYK"), "Grau": tr("Grau"), "Lab": tr("Lab")}[s]
    if s.startswith(tr("Indiziert")) and "(" in s:
        inner = s[s.index("(") + 1:s.rindex(")")]
        return f"{tr('Indiziert')} ({space_label(inner)})"
    return s


def _codec(img) -> str:
    import pikepdf
    f = img.get("/Filter")
    fl = [str(x) for x in f] if isinstance(f, pikepdf.Array) else ([str(f)] if f is not None else [])
    names = {"/DCTDecode": "JPEG", "/DCT": "JPEG", "/FlateDecode": "ZIP", "/Fl": "ZIP", "/JPXDecode": "JPEG 2000",
             "/CCITTFaxDecode": "CCITT", "/JBIG2Decode": "JBIG2", "/RunLengthDecode": "RLE", "/LZWDecode": "LZW"}
    return " + ".join(names.get(x, x.lstrip("/")) for x in fl) or tr("unkomprimiert")


def _mul(a, b):
    return (a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3],
            a[2] * b[0] + a[3] * b[2], a[2] * b[1] + a[3] * b[3],
            a[4] * b[0] + a[5] * b[2] + b[4], a[4] * b[1] + a[5] * b[3] + b[5])


def _nums(ins):
    out = []
    for o in ins.operands:
        try:
            out.append(float(o))
        except (TypeError, ValueError):
            return []
    return out


# --------------------------------------------------------------------------- #
# Analyse
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
        pw = math.hypot(ctm[0], ctm[1]) / MM          # Bild-Einheitsquadrat -> Seite
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
        rep.images.append(ImageUse(pno, name, (w, h), (pw, ph), dpi, space, prof, bits, _codec(img), is_mask, key))
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
                    if og in seen_forms:                  # Rekursion verhindern
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
            walk(pno, pikepdf.parse_content_stream(page), res or pikepdf.Dictionary(),
                 (1.0, 0.0, 0.0, 1.0, 0.0, 0.0), 0, frozenset())
        except Exception:
            continue
    return rep


def page_limits(rep: ColorReport) -> dict:
    """Seite -> (niedrigste dpi, max. Vergrößerung bei 300 dpi, bei 150 dpi) – nur bewertbare Bilder."""
    out = {}
    for u in rep.images:
        if u.mask or u.rating == "tiny":
            continue
        cur = out.get(u.page)
        if cur is None or u.dpi < cur[0]:
            out[u.page] = (u.dpi, u.dpi / GOOD_DPI, u.dpi / OK_DPI)
    return out
