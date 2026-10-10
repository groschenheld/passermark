# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Document manipulation: cropping to a target size and CMYK conversion.

Crop (default, crop_scale): the page is scaled so it fully covers the target size – the matching
edge exactly onto the target – and the overhang of the other edge is cut away half on each
side (centered). Example: A4 to A6 = 50 %, nothing cut; a narrow poster onto A4 =
width to 210 mm, the same amount cut top and bottom. Content stays vectorial.

Crop only (crop_scale = False): without scaling; if an edge sticks out, the overhang is trimmed
on both sides; if the page is smaller than the target, it stays unchanged in that direction (hint) –
for files that already come at the right size with bleed. Only the page boxes are set.
"""
from __future__ import annotations

import io
import os
import tempfile

from . import cmyk as _cmyk
from .l10n import tr

MM = 72.0 / 25.4

FORMATS = {  # Anzeige-Reihenfolge; mm, Hochformat
    "A0": (841, 1189), "A1": (594, 841), "A2": (420, 594), "A3": (297, 420), "A4": (210, 297), "A5": (148, 210),
    "A6": (105, 148), "A7": (74, 105), "B4": (250, 353), "B5": (176, 250), "C4": (229, 324), "C5": (162, 229),
    "C6": (114, 162), "DL": (99, 210), "SRA3": (320, 450), "A3+": (329, 483), "Letter": (215.9, 279.4),
    "Legal": (215.9, 355.6), "Tabloid": (279.4, 431.8), "Visitenkarte 85×55": (55, 85),
    "Visitenkarte 90×50": (50, 90), "Quadrat 210": (210, 210), "Quadrat 148": (148, 148),
}


def target_pt(s: _cmyk.ManipSettings) -> tuple[float, float]:
    if s.crop_size in FORMATS:
        w, h = FORMATS[s.crop_size]
    else:
        w, h = s.crop_w_mm, s.crop_h_mm
    return w * MM, h * MM


def _inset_box(box, s) -> tuple:
    """First subtract the original's white margin all around (crop_inset_mm); never smaller than 1 mm."""
    m = max(0.0, getattr(s, "crop_inset_mm", 0.0)) * MM
    l, b, r, t = box
    m = min(m, (r - l - MM) / 2, (t - b - MM) / 2)
    return (l + m, b + m, r - m, t - m) if m > 0 else tuple(box)


def _oriented(W: float, H: float, target, follow: bool):
    tw, th = target
    if follow and abs(W - H) > 1 and (W > H) != (tw > th):
        tw, th = th, tw                    # Querformat-Seite -> Querformat-Ziel
    return tw, th


def fill_geometry(W: float, H: float, target, follow: bool):
    """Visible page W×H (pt) -> (target tw, th, factor k, overhang per side left/right, top/bottom in pt)."""
    tw, th = _oriented(W, H, target, follow)
    k = max(tw / W, th / H)
    return tw, th, k, max(W * k - tw, 0) / 2, max(H * k - th, 0) / 2


def crop_box_for(box, rotation: int, target, follow: bool):
    """Neue Box (l, b, r, t) im ungedrehten Seitensystem + Hinweise. box: (l, b, r, t) der sichtbaren Seite."""
    l, b, r, t = box
    W, H = r - l, t - b
    tw, th = target
    if rotation % 180:                     # Ziel ist in Leserichtung angegeben
        tw, th = th, tw
    if follow and abs(W - H) > 1 and (W > H) != (tw > th):
        tw, th = th, tw                    # Querformat-Seite -> Querformat-Ziel
    dx, dy = W - tw, H - th
    notes = []
    if dx > 0.05:
        l, r = l + dx / 2, r - dx / 2
    elif dx < -0.5:
        notes.append("w")
    if dy > 0.05:
        b, t = b + dy / 2, t - dy / 2
    elif dy < -0.5:
        notes.append("h")
    return (l, b, r, t), max(dx, 0) / 2, max(dy, 0) / 2, notes


def describe_crop(doc, s: _cmyk.ManipSettings, page: int) -> str:
    """Brief info for the GUI: what happens to page x."""
    pg = doc[page]
    try:
        box, rot = pg.get_cropbox(), pg.get_rotation()
    finally:
        pg.close()
    box = _inset_box(box, s)
    if getattr(s, "crop_scale", True):
        W, H = box[2] - box[0], box[3] - box[1]
        if rot % 180:
            W, H = H, W
        tw, th, k, cx, cy = fill_geometry(W, H, target_pt(s), s.crop_follow)
        txt = tr("Seite {0}: {1:.1f} × {2:.1f} mm → {3:.1f} × {4:.1f} mm").format(
            page + 1, W / MM, H / MM, tw / MM, th / MM) + tr(", skaliert auf {0:.1f} %").format(k * 100)
        if cx > 0.05 or cy > 0.05:
            txt += tr(" (je {0:.1f} mm links/rechts, {1:.1f} mm oben/unten)").format(cx / MM, cy / MM)
        return txt
    new, cx, cy, notes = crop_box_for(box, rot, target_pt(s), s.crop_follow)
    w0, h0 = (box[2] - box[0]) / MM, (box[3] - box[1]) / MM
    w1, h1 = (new[2] - new[0]) / MM, (new[3] - new[1]) / MM
    if rot % 180:
        w0, h0, w1, h1, cx, cy = h0, w0, h1, w1, cy, cx
    txt = tr("Seite {0}: {1:.1f} × {2:.1f} mm → {3:.1f} × {4:.1f} mm").format(page + 1, w0, h0, w1, h1)
    if cx > 0.05 or cy > 0.05:
        txt += tr(" (je {0:.1f} mm links/rechts, {1:.1f} mm oben/unten)").format(cx / MM, cy / MM)
    if notes:
        txt += " – " + tr("⚠ kleiner als das Zielformat, dort nicht beschnitten")
    return txt


def fill_doc(doc, s: _cmyk.ManipSettings):
    """Copy: every page scaled until it covers the target, overhang trimmed on both sides (vectorial)."""
    import pypdfium2 as pdfium
    from .layout import flattened
    from .objects import normalized
    flat = flattened(doc)                  # Formularwerte/Kommentare mitnehmen
    try:
        norm = normalized(flat)            # ungedreht, ab (0,0): sichtbare Seite = Seite
    finally:
        if flat is not doc:
            flat.close()
    out = pdfium.PdfDocument.new()
    tgt = target_pt(s)
    try:
        for i in range(len(norm)):
            W0, H0 = norm.get_page_size(i)
            l, b, r, t = _inset_box((0.0, 0.0, W0, H0), s)
            W, H = r - l, t - b
            tw, th, k, _cx, _cy = fill_geometry(W, H, tgt, s.crop_follow)
            pg = out.new_page(tw, th)
            xo = norm.page_as_xobject(i, out)
            po = xo.as_pageobject()
            po.transform(pdfium.PdfMatrix().translate(-l, -b).scale(k, k).translate((tw - W * k) / 2, (th - H * k) / 2))
            pg.insert_obj(po)
            pg.gen_content()
            pg.close()
            xo.close()
        buf = io.BytesIO()
        out.save(buf)
    finally:
        out.close()
        norm.close()
    return pdfium.PdfDocument(buf.getvalue()), []


def crop_doc(doc, s: _cmyk.ManipSettings):
    """Kopie mit beschnittenen Seiten + Liste der Seiten, die kleiner als das Ziel sind."""
    import pypdfium2 as pdfium
    if getattr(s, "crop_scale", True):
        return fill_doc(doc, s)
    buf = io.BytesIO()
    doc.save(buf)
    out = pdfium.PdfDocument(buf.getvalue())
    small = []
    tgt = target_pt(s)
    for i in range(len(out)):
        pg = out[i]
        new, _cx, _cy, notes = crop_box_for(_inset_box(pg.get_cropbox(), s), pg.get_rotation(), tgt, s.crop_follow)
        pg.set_mediabox(*new)
        pg.set_cropbox(*new)
        pg.set_trimbox(*new)
        pg.set_bleedbox(*new)
        pg.close()
        if notes:
            small.append(i + 1)
    b2 = io.BytesIO()
    out.save(b2)
    out.close()
    return pdfium.PdfDocument(b2.getvalue()), small


def apply(doc, s: _cmyk.ManipSettings):
    """Apply all active manipulations. Returns (new document, hints). The original stays unchanged."""
    import pypdfium2 as pdfium
    notes = []
    cur = doc
    if s.crop:
        cur, small = crop_doc(cur, s)
        if small:
            notes.append(tr("Seiten kleiner als das Zielformat (nicht beschnitten): {0}").format(
                ", ".join(map(str, small[:20])) + (" …" if len(small) > 20 else "")))
    if s.cmyk and (s.target or s.cmyk_mode == "gray"):
        tmp = tempfile.mkdtemp(prefix="passermark-manip-")
        try:
            src, dst = os.path.join(tmp, "in.pdf"), os.path.join(tmp, "out.pdf")
            cur.save(src)
            _cmyk.convert_pdf(src, dst, s)
            with open(dst, "rb") as f:
                data = f.read()
            if cur is not doc:
                cur.close()
            cur = pdfium.PdfDocument(data)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
    return cur, notes
