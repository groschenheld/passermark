# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Set the trim format: trim box (where it is cut) and bleed box (colour beyond the cut) on the pages.

The user gives what he knows – the final format and how much bleed – and the rest follows: the trim box is
centred on the visible page, the bleed box lies around it (as far as the sheet has content), and on request a
sheet that is larger than trim + bleed is cut down to it. Nothing is drawn: the boxes only label what is there
(adding bleed to a page without one is "create bleed", a different tool).
"""

from __future__ import annotations

import io

from .l10n import tr
from .papersizes import UI_FORMATS

MM = 72.0 / 25.4


def _rect(v) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = (float(a) for a in v)
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def _size_mm(r) -> tuple[float, float]:
    return (r[2] - r[0]) / MM, (r[3] - r[1]) / MM


def read(data: bytes, page: int) -> dict:
    """Boxes of one page as seen (rotation applied to the sizes): sheet, trim and bleed in mm.

    {"sheet": (w, h), "trim": (w, h) | None, "bleed": mm | None, "rotate": 0/90/180/270}"""
    import pikepdf

    with pikepdf.open(io.BytesIO(data)) as pdf:
        pg = pdf.pages[page]
        rot = int(pg.obj.get("/Rotate", 0)) % 360
        media = _rect(pg.mediabox)
        crop = _rect(pg.obj["/CropBox"]) if "/CropBox" in pg.obj else media
        sheet = _size_mm(crop)
        trim = _rect(pg.obj["/TrimBox"]) if "/TrimBox" in pg.obj else None
        bleed = _rect(pg.obj["/BleedBox"]) if "/BleedBox" in pg.obj else None
    turn = rot in (90, 270)

    def seen(wh):
        return (wh[1], wh[0]) if turn else wh

    out = {"sheet": seen(sheet), "trim": seen(_size_mm(trim)) if trim else None, "bleed": None, "rotate": rot}
    if trim and bleed:
        out["bleed"] = round(
            min(trim[0] - bleed[0], bleed[2] - trim[2], trim[1] - bleed[1], bleed[3] - trim[3]) / MM, 2
        )
    return out


def guess_format(sheet_w: float, sheet_h: float, max_bleed: float = 10.0):
    """A known format with bleed that matches the sheet: e.g. 216 × 303 mm -> ("A4", 210, 297, 3.0).
    -> (name, width, height, bleed) or None (same bleed on all sides, at most ``max_bleed``)."""
    best = None
    for name, (w, h) in UI_FORMATS.items():
        for fw, fh in ((w, h), (h, w)):
            ew, eh = sheet_w - fw, sheet_h - fh
            if -0.5 <= ew <= 2 * max_bleed and -0.5 <= eh <= 2 * max_bleed and abs(ew - eh) <= 1.0:
                bleed = max(0.0, round((ew + eh) / 4, 1))
                if best is None or bleed < best[3]:
                    best = (name, fw, fh, bleed)
    return best


def apply_format(
    data: bytes, pages: list[int], trim_w: float, trim_h: float, bleed: float, cut_excess: bool = True
) -> tuple[bytes, list[str]]:
    """Set the trim format ``trim_w`` × ``trim_h`` mm (as seen, centred on the visible page) and ``bleed`` mm
    bleed around it on ``pages``; ``cut_excess``: a larger sheet is cut down to trim + bleed.
    -> (new PDF, notes). ValueError if a page is smaller than the trim format."""
    import pikepdf

    notes: list[str] = []
    short: list[str] = []
    with pikepdf.open(io.BytesIO(data)) as pdf:
        for i in pages:
            pg = pdf.pages[i]
            rot = int(pg.obj.get("/Rotate", 0)) % 360
            tw, th = (trim_h, trim_w) if rot in (90, 270) else (trim_w, trim_h)
            media = _rect(pg.mediabox)
            vis = _rect(pg.obj["/CropBox"]) if "/CropBox" in pg.obj else media
            cx, cy = (vis[0] + vis[2]) / 2, (vis[1] + vis[3]) / 2
            hw, hh = tw * MM / 2, th * MM / 2
            trim = (cx - hw, cy - hh, cx + hw, cy + hh)
            tol = 0.5
            if trim[0] < vis[0] - tol or trim[1] < vis[1] - tol or trim[2] > vis[2] + tol or trim[3] > vis[3] + tol:
                sw, sh = _size_mm(vis)
                raise ValueError(
                    tr(
                        "Seite {0} ({1:.1f} × {2:.1f} mm) ist kleiner als das Endformat {3:g} × {4:g} mm – "
                        "bitte Format bzw. Hoch-/Querformat prüfen."
                    ).format(i + 1, *((sh, sw) if rot in (90, 270) else (sw, sh)), trim_w, trim_h)
                )
            trim = (max(trim[0], vis[0]), max(trim[1], vis[1]), min(trim[2], vis[2]), min(trim[3], vis[3]))
            b = bleed * MM
            want = (trim[0] - b, trim[1] - b, trim[2] + b, trim[3] + b)
            box = (max(want[0], vis[0]), max(want[1], vis[1]), min(want[2], vis[2]), min(want[3], vis[3]))
            have = min(trim[0] - box[0], trim[1] - box[1], box[2] - trim[2], box[3] - trim[3]) / MM
            if have < bleed - 0.05:
                short.append(tr("Seite {0}: {1:.1f} mm").format(i + 1, max(0.0, have)))
            pg.obj["/TrimBox"] = pikepdf.Array([round(v, 3) for v in trim])
            pg.obj["/BleedBox"] = pikepdf.Array([round(v, 3) for v in box])
            if cut_excess:
                arr = pikepdf.Array([round(v, 3) for v in box])
                pg.obj["/MediaBox"] = arr
                pg.obj["/CropBox"] = pikepdf.Array(list(arr))
                if "/ArtBox" in pg.obj:
                    del pg.obj["/ArtBox"]
        out = io.BytesIO()
        pdf.save(out)
    if short:
        notes.append(
            tr("Weniger Anschnitt vorhanden als {0:g} mm – das Blatt hat dort keinen Inhalt mehr: {1}").format(
                bleed, ", ".join(short[:8]) + (" …" if len(short) > 8 else "")
            )
        )
    return out.getvalue(), notes
