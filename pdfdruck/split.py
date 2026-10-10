# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Splitting pages: halve a page vertically/horizontally or cut it into a grid – every piece becomes its
own page. Typical case: a booklet was exported as double pages (page 1 alone on A4, pages 2+3
side by side on A3 …) – "double pages only" splits exactly those.

Lossless: the page content is not modified or rasterized; each piece just shows a different
section (MediaBox/CropBox). Shared content is not copied. Rotated pages are split the way you
see them. If the page has a trim size (TrimBox), the split lines lie in the trim size and the bleed
area is preserved outside.
"""
from __future__ import annotations

from dataclasses import dataclass

from .l10n import tr

MODES = ("halves_v", "halves_h", "grid")


@dataclass
class SplitSettings:
    mode: str = "halves_v"        # halves_v = links|rechts · halves_h = oben|unten · grid = Spalten × Zeilen
    cols: int = 2                 # nur bei grid
    rows: int = 2                 # nur bei grid
    only_spreads: bool = False    # only split pages that are twice as wide (or tall) as the others
    rtl: bool = False             # Reihenfolge rechts nach links (Bindung rechts)
    use_trim: bool = True         # split at the trim size (TrimBox), keep the bleed area outside


def grid_of(s: SplitSettings) -> tuple[int, int]:
    if s.mode == "halves_v":
        return 2, 1
    if s.mode == "halves_h":
        return 1, 2
    if s.mode == "grid":
        return max(1, int(s.cols)), max(1, int(s.rows))
    raise ValueError(tr("Unbekannte Teilung: {0}").format(s.mode))


# --------------------------------------------------------------------------- #
# Geometrie: sichtbare Koordinaten (u nach rechts, v nach unten, 0…1) <-> PDF-Koordinaten
# --------------------------------------------------------------------------- #
def _to_user(box, rot, u, v):
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    if rot == 90:
        return x0 + v * W, y0 + u * H
    if rot == 180:
        return x1 - u * W, y0 + v * H
    if rot == 270:
        return x1 - v * W, y1 - u * H
    return x0 + u * W, y1 - v * H


def _to_vis(box, rot, x, y):
    x0, y0, x1, y1 = box
    W, H = (x1 - x0) or 1, (y1 - y0) or 1
    if rot == 90:
        return (y - y0) / H, (x - x0) / W
    if rot == 180:
        return (x1 - x) / W, (y - y0) / H
    if rot == 270:
        return (y1 - y) / H, (x1 - x) / W
    return (x - x0) / W, (y1 - y) / H


def _rect(box, rot, u0, u1, v0, v1):
    a = _to_user(box, rot, u0, v0)
    b = _to_user(box, rot, u1, v1)
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])]


def _vis_rect(box, rot, r):
    a = _to_vis(box, rot, r[0], r[1])
    b = _to_vis(box, rot, r[2], r[3])
    return min(a[0], b[0]), max(a[0], b[0]), min(a[1], b[1]), max(a[1], b[1])


def _cuts(lo, hi, n):
    """Split lines in the range lo…hi (visible, 0…1); the outer edges stay 0 and 1."""
    inner = [lo + (hi - lo) * k / n for k in range(1, n)]
    return [0.0] + inner + [1.0], [lo] + inner + [hi]


def cells(box, rot, trim, cols, rows, rtl=False):
    """Pieces of a page in reading order: list of (clip, trim size|None) in PDF coordinates."""
    if trim:
        tu0, tu1, tv0, tv1 = _vis_rect(box, rot, trim)
    else:
        tu0, tu1, tv0, tv1 = 0.0, 1.0, 0.0, 1.0
    us, tus = _cuts(tu0, tu1, cols)
    vs, tvs = _cuts(tv0, tv1, rows)
    out = []
    order = range(cols - 1, -1, -1) if rtl else range(cols)
    for r in range(rows):
        for c in order:
            piece = _rect(box, rot, us[c], us[c + 1], vs[r], vs[r + 1])
            t = _rect(box, rot, tus[c], tus[c + 1], tvs[r], tvs[r + 1]) if trim else None
            out.append((piece, t))
    return out


# --------------------------------------------------------------------------- #
def _inh(obj, key):
    """Seitenattribut auch aus dem Seitenbaum geerbt (Resources, MediaBox, CropBox, Rotate)."""
    seen = 0
    while obj is not None and seen < 50:
        if key in obj:
            return obj[key]
        obj = obj.get("/Parent")
        seen += 1
    return None


def _box(obj, key):
    import pikepdf
    v = _inh(obj, key) if key in ("/MediaBox", "/CropBox") else obj.get(key)
    if v is None or not isinstance(v, pikepdf.Array) or len(v) != 4:
        return None
    a = [float(x) for x in v]
    return [min(a[0], a[2]), min(a[1], a[3]), max(a[0], a[2]), max(a[1], a[3])]


def _intersect(a, b):
    r = [max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])]
    return r if r[2] > r[0] and r[3] > r[1] else None


def page_info(obj):
    """(visible clip, rotation, trim size|None, visible width, visible height)."""
    media = _box(obj, "/MediaBox") or [0, 0, 612, 792]
    crop = _box(obj, "/CropBox")
    box = _intersect(media, crop) if crop else media
    box = box or media
    rot = int(_inh(obj, "/Rotate") or 0) % 360
    trim = _box(obj, "/TrimBox")
    trim = _intersect(trim, box) if trim else None
    w, h = box[2] - box[0], box[3] - box[1]
    if rot in (90, 270):
        w, h = h, w
    return box, rot, trim, w, h


def spreads(sizes: list, cols: int, rows: int) -> set:
    """Pages (0-based) that are as large as cols × rows of the other pages – e.g. double pages at 2 × 1.
        The reference is the smallest size occurring.
    """
    if not sizes:
        return set()
    bw = min(w for w, h in sizes)
    bh = min(h for w, h in sizes)
    out = set()
    for i, (w, h) in enumerate(sizes):
        if (cols > 1 and abs(w / (bw * cols) - 1) < 0.08 and (rows == 1 and abs(h / bh - 1) < 0.08
                                                               or rows > 1 and abs(h / (bh * rows) - 1) < 0.08)) \
                or (cols == 1 and rows > 1 and abs(h / (bh * rows) - 1) < 0.08 and abs(w / bw - 1) < 0.08):
            out.add(i)
    return out


def split(src: str, s: SplitSettings, pages=None, progress=None, cancel=None) -> tuple[bytes, dict]:
    """Split the selected pages (pages, 0-based; None = all or all double pages). Result PDF + info."""
    import io
    import pikepdf
    cols, rows = grid_of(s)
    if cols * rows < 2:
        raise ValueError(tr("Raster mit nur einem Feld – nichts zu teilen."))
    src_pdf = pikepdf.open(src)
    try:
        objs = [p.obj for p in src_pdf.pages]
        infos = [page_info(o) for o in objs]
        chosen = set(range(len(objs))) if pages is None else {p for p in pages if 0 <= p < len(objs)}
        if s.only_spreads:
            chosen &= spreads([(i[3], i[4]) for i in infos], cols, rows)
        out = pikepdf.new()
        n_split = 0
        for i, o in enumerate(objs):
            if cancel is not None and cancel():
                from .core import Cancelled
                raise Cancelled(tr("Abgebrochen."))
            if progress is not None and i % 20 == 0:
                progress(i, len(objs), tr("Seite {0}/{1}").format(i + 1, len(objs)))
            if i not in chosen:
                out.pages.append(src_pdf.pages[i])
                continue
            n_split += 1
            box, rot, trim, _w, _h = infos[i]
            res = _inh(o, "/Resources")
            for piece, t in cells(box, rot, trim if s.use_trim else None, cols, rows, s.rtl):
                d = pikepdf.Dictionary(Type=pikepdf.Name.Page, MediaBox=piece, CropBox=piece,
                                       Contents=o.get("/Contents", pikepdf.Array()))
                if res is not None:
                    d.Resources = res
                if rot:
                    d.Rotate = rot
                for k in ("/Group", "/UserUnit"):
                    if k in o:
                        d[k] = o[k]
                if t:
                    d.TrimBox = t
                    d.BleedBox = piece
                out.pages.append(pikepdf.Page(src_pdf.make_indirect(d)))
        buf = io.BytesIO()
        out.save(buf, object_stream_mode=pikepdf.ObjectStreamMode.generate)
        info = {"pages_in": len(objs), "pages_out": len(out.pages), "split": n_split}
        out.close()
    finally:
        src_pdf.close()
    if n_split == 0:
        raise ValueError(tr("Keine Seite zum Teilen gefunden – bei „nur Doppelseiten“ müssen manche Seiten doppelt so "
                            "breit sein wie die übrigen."))
    return buf.getvalue(), info
