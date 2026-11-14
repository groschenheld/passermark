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
from .papersizes import UI_FORMATS as _UI_FORMATS

MM = 72.0 / 25.4

TRIM_MODE = "__trim__"
WHITEOUT_MODE = "__whiteout__"

FORMATS = {  # display order; mm, portrait – standard sizes from the shared table (papersizes.py)
    **_UI_FORMATS,
    "Visitenkarte 85×55": (55, 85),
    "Visitenkarte 90×50": (50, 90),
    "Quadrat 210": (210, 210),
    "Quadrat 148": (148, 148),
}


def target_pt(s: _cmyk.ManipSettings) -> tuple[float, float]:
    """Target size of the crop in pt as ``(width, height)``."""
    w, h = FORMATS.get(s.crop_size, (s.crop_w_mm, s.crop_h_mm))
    return w * MM, h * MM


def _inset_box(box, s) -> tuple:
    """First subtract the original's white margin all around (crop_inset_mm); never smaller than 1 mm."""
    m = max(0.0, getattr(s, "crop_inset_mm", 0.0)) * MM
    left, b, r, t = box
    m = min(m, (r - left - MM) / 2, (t - b - MM) / 2)
    return (left + m, b + m, r - m, t - m) if m > 0 else tuple(box)


def _oriented(W: float, H: float, target, follow: bool):
    tw, th = target
    if follow and abs(W - H) > 1 and (W > H) != (tw > th):
        tw, th = th, tw  # landscape page -> landscape target
    return tw, th


def fill_geometry(W: float, H: float, target, follow: bool):
    """Visible page W×H (pt) -> (target tw, th, factor k, overhang per side left/right, top/bottom in pt)."""
    tw, th = _oriented(W, H, target, follow)
    k = max(tw / W, th / H)
    return tw, th, k, max(W * k - tw, 0) / 2, max(H * k - th, 0) / 2


def crop_box_for(box, rotation: int, target, follow: bool):
    """New box (l, b, r, t) in the unrotated page system + notes. box: (l, b, r, t) of the visible page."""
    left, b, r, t = box
    W, H = r - left, t - b
    tw, th = target
    if rotation % 180:  # the target is given in reading direction
        tw, th = th, tw
    if follow and abs(W - H) > 1 and (W > H) != (tw > th):
        tw, th = th, tw  # landscape page -> landscape target
    dx, dy = W - tw, H - th
    notes = []
    if dx > 0.05:
        left, r = left + dx / 2, r - dx / 2
    elif dx < -0.5:
        notes.append("w")
    if dy > 0.05:
        b, t = b + dy / 2, t - dy / 2
    elif dy < -0.5:
        notes.append("h")
    return (left, b, r, t), max(dx, 0) / 2, max(dy, 0) / 2, notes


def trim_box_for(box, rotation, s):
    """Cut off edges without a target size: new box + (l, t, r, b) in reading direction."""
    left, b, r, t = box
    lmm, tmm, rmm, bmm = s.trim_l_mm, s.trim_t_mm, s.trim_r_mm, s.trim_b_mm
    rot = rotation % 360
    if rot == 90:  # display rotated 90° clockwise
        lmm, tmm, rmm, bmm = tmm, rmm, bmm, lmm
    elif rot == 180:
        lmm, tmm, rmm, bmm = rmm, bmm, lmm, tmm
    elif rot == 270:
        lmm, tmm, rmm, bmm = bmm, lmm, tmm, rmm
    left, b, r, t = left + lmm * MM, b + bmm * MM, r - rmm * MM, t - tmm * MM
    return (left, b, r, t), (s.trim_l_mm, s.trim_t_mm, s.trim_r_mm, s.trim_b_mm)


def _white_bbox(pg, dpi=72, tol=12):
    """Content bbox (l, b, r, t in pt, in the unrotated page system) – None if the page is empty/white.

    Background = median of the EDGE PIXELS (outermost strip of the page; mostly white, may be slightly tinted).
    Not the median of the whole page: if the content fills more than half, that would be the content colour.
    JPEG noise in the white is suppressed by two filters:
    tolerance against the background + single pixels need neighbours (3×3, at least 3).
    Note: the rendered image has y=0 at the TOP, PDF has y=0 at the BOTTOM -> y is converted here.
    """
    import numpy as np

    W0, H0 = pg.get_size()
    scale = dpi / 72.0
    bmp = pg.render(scale=scale)
    a = np.asarray(bmp.to_pil().convert("RGB"), dtype=np.int16)
    k = max(1, min(a.shape[0], a.shape[1]) // 100)  # edge strip ~1 % of the shorter side
    edge = np.concatenate(
        [a[:k].reshape(-1, 3), a[-k:].reshape(-1, 3), a[:, :k].reshape(-1, 3), a[:, -k:].reshape(-1, 3)]
    )
    bg = np.median(edge, axis=0)
    diff = np.abs(a - bg).max(axis=2)
    mask = diff > tol
    if not mask.any():
        return None
    n = (
        mask[:-2, :-2].astype(np.int32)
        + mask[:-2, 1:-1]
        + mask[:-2, 2:]
        + mask[1:-1, :-2]
        + mask[1:-1, 1:-1]
        + mask[1:-1, 2:]
        + mask[2:, :-2]
        + mask[2:, 1:-1]
        + mask[2:, 2:]
    )
    m = np.zeros_like(mask)
    m[1:-1, 1:-1] = n >= 3  # single pixels = noise, out
    if not m.any():
        return None
    ys, xs = np.where(m)
    return (
        xs.min() / scale,  # left
        H0 - (ys.max() + 1) / scale,  # bottom  (y image top -> PDF bottom)
        (xs.max() + 1) / scale,  # right
        H0 - ys.min() / scale,
    )  # top


def whiteout_doc(doc, s: _cmyk.ManipSettings):
    """Remove white space: detected bbox + margin = new page size (content stays 1:1)."""
    import pypdfium2 as pdfium

    from .layout import flattened
    from .objects import normalized

    flat = flattened(doc)
    try:
        norm = normalized(flat)
    finally:
        if flat is not doc:
            flat.close()
    out = pdfium.PdfDocument.new()
    skipped = []
    try:
        for i in range(len(norm)):
            W0, H0 = norm.get_page_size(i)
            pg = norm[i]
            try:
                bb = _white_bbox(pg)
            finally:
                pg.close()
            if bb is None:
                out.new_page(W0, H0)  # take over a blank page unchanged
                skipped.append(i + 1)
                continue
            m = s.white_margin_mm * MM
            left, b, r, t = bb[0] - m, bb[1] - m, bb[2] + m, bb[3] + m
            left, b = max(left, 0.0), max(b, 0.0)
            r, t = min(r, W0), min(t, H0)  # the margin must not extend beyond the page
            pg_out = out.new_page(max(r - left, 1.0), max(t - b, 1.0))
            xo = norm.page_as_xobject(i, out)
            po = xo.as_pageobject()
            po.transform(pdfium.PdfMatrix().translate(-left, -b))  # only move, do not scale
            pg_out.insert_obj(po)
            pg_out.gen_content()
            pg_out.close()
            xo.close()
        buf = io.BytesIO()
        out.save(buf)
    finally:
        out.close()
        norm.close()
    return pdfium.PdfDocument(buf.getvalue()), skipped


def describe_crop(doc, s: _cmyk.ManipSettings, page: int) -> str:
    """Brief info for the GUI: what happens to page x."""
    pg = doc[page]
    try:
        box, rot = pg.get_cropbox(), pg.get_rotation()
    finally:
        pg.close()
    box = _inset_box(box, s)
    if s.crop_size == TRIM_MODE:
        new, (l_, t_, r_, b_) = trim_box_for(box, rot, s)
        return tr(
            "Seite {0}: {1:.1f} × {2:.1f} mm → {3:.1f} × {4:.1f} mm (−{5:.1f} l, −{6:.1f} o, −{7:.1f} r, −{8:.1f} u mm)"
        ).format(
            page + 1,
            (box[2] - box[0]) / MM,
            (box[3] - box[1]) / MM,
            (new[2] - new[0]) / MM,
            (new[3] - new[1]) / MM,
            l_,
            t_,
            r_,
            b_,
        )
    if s.crop_size == WHITEOUT_MODE:
        return tr(
            "Seite {0}: {1:.1f} × {2:.1f} mm – Weißraum wird entfernt, neues Format = Inhalt + {3:.1f} mm Rand"
        ).format(page + 1, (box[2] - box[0]) / MM, (box[3] - box[1]) / MM, getattr(s, "white_margin_mm", 0.0))
    if getattr(s, "crop_scale", True):
        W, H = box[2] - box[0], box[3] - box[1]
        if rot % 180:
            W, H = H, W
        tw, th, k, cx, cy = fill_geometry(W, H, target_pt(s), s.crop_follow)
        txt = tr("Seite {0}: {1:.1f} × {2:.1f} mm → {3:.1f} × {4:.1f} mm").format(
            page + 1, W / MM, H / MM, tw / MM, th / MM
        ) + tr(", skaliert auf {0:.1f} %").format(k * 100)
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

    flat = flattened(doc)  # take form values/comments along
    try:
        norm = normalized(flat)  # unrotated, from (0,0): visible page = page
    finally:
        if flat is not doc:
            flat.close()
    out = pdfium.PdfDocument.new()
    tgt = target_pt(s)
    try:
        for i in range(len(norm)):
            W0, H0 = norm.get_page_size(i)
            left, b, r, t = _inset_box((0.0, 0.0, W0, H0), s)
            W, H = r - left, t - b
            tw, th, k, _cx, _cy = fill_geometry(W, H, tgt, s.crop_follow)
            pg = out.new_page(tw, th)
            xo = norm.page_as_xobject(i, out)
            po = xo.as_pageobject()
            po.transform(
                pdfium.PdfMatrix().translate(-left, -b).scale(k, k).translate((tw - W * k) / 2, (th - H * k) / 2)
            )
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
    """Crop all pages of ``doc`` as described by ``s`` (target size, trim box or white space)."""
    import pypdfium2 as pdfium

    if s.crop_size == WHITEOUT_MODE:
        return whiteout_doc(doc, s)
    if s.crop_size == TRIM_MODE:
        buf = io.BytesIO()
        doc.save(buf)
        out = pdfium.PdfDocument(buf.getvalue())
        for i in range(len(out)):
            pg = out[i]
            new, *_ = trim_box_for(pg.get_cropbox(), pg.get_rotation(), s)
            pg.set_mediabox(*new)
            pg.set_cropbox(*new)
            pg.set_trimbox(*new)
            pg.set_bleedbox(*new)
            pg.close()
        b2 = io.BytesIO()
        out.save(b2)
        out.close()
        return pdfium.PdfDocument(b2.getvalue()), []

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
            if s.crop_size == WHITEOUT_MODE:
                notes.append(
                    tr("Leere/weiße Seiten (unverändert übernommen): {0}").format(
                        ", ".join(map(str, small[:20])) + (" …" if len(small) > 20 else "")
                    )
                )
            else:
                notes.append(
                    tr("Seiten kleiner als das Zielformat (nicht beschnitten): {0}").format(
                        ", ".join(map(str, small[:20])) + (" …" if len(small) > 20 else "")
                    )
                )
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
