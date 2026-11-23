# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Create bleed for customer files without it: the page grows by the bleed on every side, the strips around the
final format are filled from the content at the edge.

  mirror   the edge of the page is mirrored outward (seamless, the usual way – also in Nutzen/Step & Repeat)
  stretch  a narrow strip at the edge is stretched outward (for edges where a mirror image would be visible,
           e.g. text or lines near the edge)

The page is wrapped as a form XObject (vector stays vector), the boxes are set: TrimBox = final format,
BleedBox = MediaBox = CropBox = final format + bleed. Pages that already have enough bleed stay as they are.
Only pikepdf – safe in background threads.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from .l10n import tr

MM = 72.0 / 25.4
STRETCH_BAND_MM = 1.0  # stretch: this strip inside the edge is pulled over the bleed


@dataclass
class BleedSettings:
    """Settings of the job ``bleed`` (pages: step option "pages", default all)."""

    bleed_mm: float = 3.0
    mode: str = "mirror"  # mirror | stretch


def _box(obj, key):
    v = obj.get(key)
    return [float(x) for x in v] if v is not None and len(v) == 4 else None


def _norm(b):
    return [min(b[0], b[2]), min(b[1], b[3]), max(b[0], b[2]), max(b[1], b[3])]


def _inherited(page, key):
    node = page.obj
    while node is not None:
        v = node.get(key)
        if v is not None:
            return [float(x) for x in v]
        node = node.get("/Parent")
    return None


def final_format(page) -> list:
    """Final format of a page: TrimBox, otherwise ArtBox, otherwise the visible page (CropBox ∩ MediaBox)."""
    media = _norm(_inherited(page, "/MediaBox") or [0, 0, 612, 792])
    crop = _inherited(page, "/CropBox")
    vis = media
    if crop:
        c = _norm(crop)
        vis = [max(c[0], media[0]), max(c[1], media[1]), min(c[2], media[2]), min(c[3], media[3])]
    for key in ("/TrimBox", "/ArtBox"):
        b = _box(page.obj, key)
        if b:
            return _norm(b)
    return vis


def existing_bleed(page) -> float:
    """Smallest bleed (pt) the page already has around its final format (visible page beyond the TrimBox)."""
    media = _norm(_inherited(page, "/MediaBox") or [0, 0, 612, 792])
    crop = _inherited(page, "/CropBox")
    vis = _norm(crop) if crop else media
    vis = [max(vis[0], media[0]), max(vis[1], media[1]), min(vis[2], media[2]), min(vis[3], media[3])]
    bl = _box(page.obj, "/BleedBox")
    if bl:
        b = _norm(bl)
        vis = [max(vis[0], b[0]), max(vis[1], b[1]), min(vis[2], b[2]), min(vis[3], b[3])]
    t = final_format(page)
    return max(0.0, min(t[0] - vis[0], t[1] - vis[1], vis[2] - t[2], vis[3] - t[3]))


def strip_matrices(trim: list, bleed: float, mode: str) -> list:
    """For every strip around the final format (4 sides, 4 corners): (clip rectangle x, y, w, h, matrix).
    The matrix places a copy of the page so that its edge fills the strip (mirrored or stretched)."""
    x0, y0, x1, y1 = trim
    b = bleed
    band = min(STRETCH_BAND_MM * MM, (x1 - x0) / 4, (y1 - y0) / 4)

    def axis(lo, hi, side):
        """1-D map for one axis -> (a, c) with x' = a·x + c. side −1: strip below lo, +1: above hi, 0: none."""
        if side == 0:
            return 1.0, 0.0
        edge = lo if side < 0 else hi
        if mode == "mirror":
            return -1.0, 2 * edge  # x' = 2·edge − x
        # stretch: the strip of width "band" inside the edge is pulled outward over the bleed, order kept –
        # the inner end of the strip stays put, the page edge lands on the outer edge of the bleed
        anchor = edge + band if side < 0 else edge - band
        k = (band + b) / band if band > 0 else 1.0
        return k, anchor * (1 - k)  # x' = anchor + k·(x − anchor)

    out = []
    for sx in (-1, 0, 1):
        for sy in (-1, 0, 1):
            if sx == 0 and sy == 0:
                continue
            ax, cx = axis(x0, x1, sx)
            ay, cy = axis(y0, y1, sy)
            rx = x0 - b if sx < 0 else (x1 if sx > 0 else x0)
            rw = b if sx else x1 - x0
            ry = y0 - b if sy < 0 else (y1 if sy > 0 else y0)
            rh = b if sy else y1 - y0
            out.append(((rx, ry, rw, rh), (ax, 0.0, 0.0, ay, cx, cy)))
    return out


def _fmt(v: float) -> str:
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


def add_bleed(data: bytes, pages=None, bleed_mm: float = 3.0, mode: str = "mirror") -> tuple:
    """Create bleed on the pages (0-based indices, None = all) -> (bytes, notes)."""
    import pikepdf

    if mode not in ("mirror", "stretch"):
        raise ValueError(mode)
    b = max(0.0, float(bleed_mm)) * MM
    notes: list = []
    if b <= 0:
        return data, [tr("Anschnitt 0 mm – nichts zu tun.")]
    pdf = pikepdf.open(io.BytesIO(data))
    try:
        idx = list(range(len(pdf.pages))) if pages is None else [i for i in pages if 0 <= i < len(pdf.pages)]
        done, had = [], []
        for i in idx:
            page = pdf.pages[i]
            if existing_bleed(page) >= b - 0.05 * MM:
                had.append(i + 1)
                continue
            trim = final_format(page)
            media = _norm(_inherited(page, "/MediaBox") or [0, 0, 612, 792])
            form = page.as_form_xobject(handle_transformations=False)
            form.write(form.read_bytes())  # qpdf fills the form lazily from the page: take the content now
            form.BBox = media  # all of the page's content, also what already lies beyond the final format
            res = pikepdf.Dictionary(XObject=pikepdf.Dictionary(PMpage=form))
            parts = []
            for (rx, ry, rw, rh), m in strip_matrices(trim, b, mode):
                parts.append(
                    f"q {_fmt(rx)} {_fmt(ry)} {_fmt(rw)} {_fmt(rh)} re W n "
                    f"{' '.join(_fmt(v) for v in m)} cm /PMpage Do Q"
                )
            # the page itself on top: real content beyond the final format (partial bleed) wins over the copies
            parts.append("q /PMpage Do Q")
            page.obj.Contents = pdf.make_stream("\n".join(parts).encode("ascii"))
            page.obj.Resources = res
            new = [trim[0] - b, trim[1] - b, trim[2] + b, trim[3] + b]
            page.obj.MediaBox = new
            page.obj.CropBox = new
            page.obj.BleedBox = new
            page.obj.TrimBox = trim
            if "/ArtBox" in page.obj:
                del page.obj["/ArtBox"]
            done.append(i + 1)
        from .preflight import _pages_str

        if done:
            how = tr("gespiegelt") if mode == "mirror" else tr("gestreckt")
            notes.append(
                tr("Anschnitt {0} mm ({1}) erzeugt: Seite {2}.").format(
                    f"{bleed_mm:g}".replace(".", ","), how, _pages_str(done)
                )
            )
        if had:
            notes.append(tr("Hat schon genug Anschnitt, unverändert: Seite {0}.").format(_pages_str(had)))
        if not done:
            return data, notes
        out = io.BytesIO()
        pdf.save(out)
        return out.getvalue(), notes
    finally:
        pdf.close()
