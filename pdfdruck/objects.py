# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Object detection on PDF pages (vector and raster) and splitting into individual pages.

Artwork mask:
  transparent – render the page without a background; everything that covers is artwork (exact for vector
                graphics; white areas inside the artwork count as well)
  color       – subtract the background color (most frequent edge color) with a tolerance (scans, pages with a solid area)
  auto        – transparent, unless the page is practically fully opaque -> color

Splitting: objects less than "merge" apart count as one; each object becomes its own page via a
clip box – vectorial, images at original resolution (nothing is recomputed).
Coordinates: pages are first "normalized" (page rotation applied vectorially), then
x to the right, y up, origin bottom left, unit pt.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

from .l10n import tr

MM = 72.0 / 25.4


@dataclass
class DetectSettings:
    dpi: int = 150
    mode: str = "auto"            # auto | transparent | color
    tolerance: int = 28           # 0–255 Abstand zur Hintergrundfarbe
    min_size_mm: float = 5.0      # kleinere Objekte (Staub, Schmutz) ignorieren
    gap_mm: float = 1.0           # parts lying closer together belong together
    margin_mm: float = 0.0        # Rand um jedes Objekt (negativ = nach innen)


@dataclass
class Box:
    x0: float
    y0: float
    x1: float
    y1: float                     # pt, normalisierte Seite (y nach oben)

    @property
    def w(self):
        return self.x1 - self.x0

    @property
    def h(self):
        return self.y1 - self.y0


# --------------------------------------------------------------------------- #
def normalized(doc):
    """Kopie, in der jede Seite ungedreht ist und bei (0,0) beginnt (Drehung/CropBox eingerechnet)."""
    import pypdfium2 as pdfium
    out = pdfium.PdfDocument.new()
    for i in range(len(doc)):
        w, h = doc.get_page_size(i)
        pg = out.new_page(w, h)
        xo = doc.page_as_xobject(i, out)
        pg.insert_obj(xo.as_pageobject())
        pg.gen_content()
        pg.close()
        xo.close()
    buf = io.BytesIO()
    out.save(buf)
    out.close()
    return pdfium.PdfDocument(buf.getvalue())


def render_rgba(page, dpi: int):
    """Page without a background as an RGBA numpy array (height, width, 4)."""
    import numpy as np
    bmp = page.render(scale=dpi / 72.0, fill_color=(255, 255, 255, 0), may_draw_forms=True, draw_annots=True)
    arr = bmp.to_numpy().copy()
    mode = bmp.mode
    bmp.close()
    if mode == "BGRA":
        arr = arr[:, :, [2, 1, 0, 3]]
    elif mode == "BGR":
        arr = np.dstack([arr[:, :, [2, 1, 0]], np.full(arr.shape[:2], 255, np.uint8)])
    return arr


def motif_mask(rgba, s: DetectSettings):
    """(Maske bool, verwendeter Modus)."""
    import numpy as np
    alpha = rgba[:, :, 3]
    mode = s.mode
    if mode == "auto":
        ring = np.concatenate([alpha[:3].ravel(), alpha[-3:].ravel(), alpha[:, :3].ravel(), alpha[:, -3:].ravel()])
        mode = "color" if ((alpha > 250).mean() > 0.97 or (ring > 250).mean() > 0.9) else "transparent"
    if mode == "transparent":
        return alpha > 96, mode
    rgb = rgba[:, :, :3].astype(np.int16)
    # Hintergrund = Median der Randpixel (robust gegen einzelne Objekte am Rand)
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    bg = np.median(border, axis=0)
    # border not uniform -> there is no background: the artwork fills the entire page
    # (z. B. Visitenkarte/Sticker im Endformat) -> die ganze Seite ist ein Objekt
    if (np.abs(border - bg).max(axis=1) <= s.tolerance).mean() < 0.6:
        return alpha > 96, "page"
    # ganzzahlig rechnen (schnell); doppelte Werte, damit ein „halber“ Median exakt gleich verglichen wird
    bg2 = np.rint(bg * 2).astype(np.int16)
    diff2 = np.abs(rgb * 2 - bg2).max(axis=2)
    return (diff2 > 2 * s.tolerance) & (alpha > 96), mode


def detect(page, s: DetectSettings) -> list[Box]:
    """Objekte einer (normalisierten) Seite finden. Reihenfolge: zeilenweise von oben links."""
    import numpy as np
    from scipy import ndimage as ndi
    W, H = page.get_size()
    rgba = render_rgba(page, s.dpi)
    mask, _mode = motif_mask(rgba, s)
    px = s.dpi / 72.0
    gap = max(0, int(round(s.gap_mm * MM * px / 2)))
    work = mask
    if gap:
        # close gaps < gap_mm: distance to mask <= gap/2 -> connected
        work = ndi.distance_transform_edt(~mask) <= gap
    lab, n = ndi.label(work)
    boxes = []
    minpx = s.min_size_mm * MM * px
    for sl in ndi.find_objects(lab):
        if sl is None:
            continue
        ys, xs = sl
        # wahre Ausdehnung aus der Originalmaske (ohne die Verbindungs-Dilatation)
        sub = mask[ys, xs]
        if not sub.any():
            continue
        rows = np.where(sub.any(axis=1))[0]
        cols = np.where(sub.any(axis=0))[0]
        y0p, y1p = ys.start + rows[0], ys.start + rows[-1] + 1
        x0p, x1p = xs.start + cols[0], xs.start + cols[-1] + 1
        if (x1p - x0p) < minpx or (y1p - y0p) < minpx:
            continue
        m = s.margin_mm * MM                      # negativ = nach innen beschneiden
        b = Box(max(0.0, x0p / px - m), max(0.0, H - y1p / px - m), min(W, x1p / px + m), min(H, H - y0p / px + m))
        if b.w > 1 and b.h > 1:
            boxes.append(b)
    return reading_order(boxes)


def reading_order(boxes: list[Box]) -> list[Box]:
    """Zeilen von oben nach unten, in der Zeile von links nach rechts."""
    rest = sorted(boxes, key=lambda b: -b.y1)
    out = []
    while rest:
        top = rest[0]
        row = [b for b in rest if b.y1 > top.y1 - top.h / 2]       # overlaps the upper half -> same row
        row.sort(key=lambda b: b.x0)
        out += row
        rest = [b for b in rest if b not in row]
    return out


def with_margin(b: Box, margin_mm: float, page_w: float, page_h: float) -> Box:
    """Apply a margin: positive = larger (up to the page edge), negative = inward."""
    m = margin_mm * MM
    return Box(max(0.0, b.x0 - m), max(0.0, b.y0 - m), min(page_w, b.x1 + m), min(page_h, b.y1 + m))


def separate(norm_doc, boxes_by_page: dict[int, list[Box]], margin_mm: float = 0.0):
    """Neues Dokument: jedes Objekt eine Seite (Reihenfolge: Seiten, darin Lesereihenfolge)."""
    import pypdfium2 as pdfium
    out = pdfium.PdfDocument.new()
    for pi in sorted(boxes_by_page):
        pw, ph = norm_doc.get_page_size(pi)
        for b0 in boxes_by_page[pi]:
            b = with_margin(b0, margin_mm, pw, ph) if margin_mm else b0
            if b.w < 1 or b.h < 1:
                continue
            out.import_pages(norm_doc, [pi])
            pg = out[len(out) - 1]
            for setter in (pg.set_mediabox, pg.set_cropbox, pg.set_bleedbox):
                setter(b.x0, b.y0, b.x1, b.y1)
            # trim size = the object itself; a positive margin is bleed area (detected during imposition)
            t = Box(max(b.x0, b0.x0), max(b.y0, b0.y0), min(b.x1, b0.x1), min(b.y1, b0.y1)) if margin_mm > 0 else b
            pg.set_trimbox(t.x0, t.y0, t.x1, t.y1)
            pg.close()
    if len(out) == 0:
        out.close()
        raise ValueError(tr("Keine Objekte gefunden."))
    buf = io.BytesIO()
    out.save(buf)
    out.close()
    return pdfium.PdfDocument(buf.getvalue())
