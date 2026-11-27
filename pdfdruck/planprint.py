# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Plan printing on roll printers (production print, usually 75/80 g paper). No Qt.

Per plan (= PDF page):
  * Frame: plans usually come with two outer lines. The outer one is the cut line – printing is limited to it, so
    it disappears and an exact margin stays around the inner frame. Without two outer lines: content + 5 mm.
  * Roll: the one with the shortest run length (rotating is allowed: an A1 goes across the 841 roll instead of
    upright on the 594 – one manual cut more, but less paper). Same length -> the narrower roll.
  * Run length: only the plan sizes (no gaps, no lead-in) – per roll for one set and for all copies.
Printing: one job per plan, page = exact plan size, paper = custom size (roll width × length), feed = the roll.
Order: unsorted by default (plan 1 ×3, plan 2 ×3 …), optionally sorted and/or grouped by roll width.
"""

from __future__ import annotations

import dataclasses
import os
import re
import tempfile
from dataclasses import dataclass, field

from . import layout
from .l10n import tr

MM = layout.MM
PLAN_WEIGHTS = (75, 80)
FRAME_MODES = ("auto", "frame", "margin", "none")
ROTATE_MODES = ("auto", "keep", "short", "long")
BLEED_MODES = ("mirror", "blank", "color")
ORDERS = ("list", "roll")
ALIGNS = ("center", "left", "right")  # position across the roll
TOL_MM = 0.5  # tolerance of the roll width


@dataclass
class PlanSettings:
    """All settings of a plan or poster print job (dialog, command line and the workflow job ``plan``)."""

    printer: str = ""  # empty = default printer
    color: str = ""  # color | gray | "" (as set in the driver)
    media: str = ""  # media type in the driver ("" = as set)
    frame: str = "auto"  # auto | frame (two outer lines) | margin (content + margin) | none (page)
    margin_mm: float = 5.0  # margin when there are no two outer lines
    rotate: str = "auto"  # auto (shortest length) | keep (as supplied) | short (short side across) | long
    scale_pct: float = 100.0  # default: actual size
    bleed_mm: float = 0.0  # bleed all round
    bleed_mode: str = "mirror"  # mirror (gespiegelt) | blank (Leerraum) | color (Einzelfarbe)
    bleed_color: str = "#ffffff"
    crop_marks: bool = False  # crop marks
    copies: int = 1  # copies (sets)
    collate: bool = False  # collated: set by set – default: each plan n times in a row
    order: str = "list"  # list (order of the list) | roll (by roll width, narrow first)
    weights: list = field(default_factory=lambda: list(PLAN_WEIGHTS))  # plan paper g/m² (roll selection)
    rolls: list = field(default_factory=list)  # rolls entered by hand [594, 841, …] or [{"width_mm": …, "slot": …}]
    live_rolls: bool = True  # read the rolls from the device
    fix_hairlines: bool = False  # raise hairlines
    hairline_mm: float = 0.1
    options: dict = field(default_factory=dict)  # raw driver options
    profile: str = "admin"  # colour profile as for printing: admin | none | profile id (window: this print only)
    intent: str = ""
    driver_color_off: bool = False  # switch the driver's own colour adjustment off (window: this print only)
    title: str = ""
    dry_run: bool = False
    # poster/quality print, banner, print & cut, material
    kind: str = "plan"  # plan (production print) | poster (quality print)
    quality_mode: str = ""  # production (lowest driver quality) | quality (highest); "" = by kind
    material: str = ""  # print material (printmat) – name or id; "" = none
    nest: bool = False  # several pieces side by side on the roll (poster: on by default)
    gap_mm: float = 5.0  # gap between pieces placed side by side
    max_page_m: float = 10.0  # no longer used (every row is its own page)
    overwidth: str = "none"  # wider than every roll: none (skip) | crop (cut off) | tile (strips)
    overlap_mm: float = 20.0  # overlap of the strips
    fold_marks: bool = False  # fold marks to DIN 824 (simplified)
    hem_mm: float = 0.0  # hem/pole pocket allowance
    hem_sides: str = "lrtb"  # sides with a hem: l r t b (as the page stands)
    grommet_spacing_mm: float = 0.0  # eyelets: maximum spacing (0 = no eyelet marks)
    grommet_inset_mm: float = 20.0  # eyelets: centre measured from the trim edge
    grommet_d_mm: float = 10.0  # eyelets: diameter of the mark
    grommet_sides: str = "lrtb"
    cut_contour: bool = False  # CutContour (spot colour) at the image edge – for print & cut (VersaWorks, CutStudio)
    printcut_marks: bool = False  # additionally register marks (angles) at the corners
    roll_pick: str = ""  # fixed roll (roll_key) – "" = automatic
    align: str = "left"  # center | left | right: position across the roll (page = roll width)
    split_copies: bool = True  # old settings: False = copy count – today copies_mode
    copies_mode: str = "sheets"  # sheets: one job, one sheet per copy | jobs: one job per copy |
    # count: one sheet with a copy count (the device decides about cutting)
    scale_mode: str = "pct"  # pct (scale_pct) | short (short edge to scale_mm) | long (long edge)
    scale_mm: float = 0.0
    overrides: dict = field(default_factory=dict)  # per page (1-based, "3") overrides: {"scale_pct": 200, …}
    cut_sheets: bool = True  # set the printer's cut option to "after every page" (IPP trim, CutMedia …)


KINDS = ("plan", "poster")
COPIES_MODES = ("sheets", "jobs", "count")
SCALE_MODES = ("pct", "short", "long")
# settings that may differ per plan/poster (dialog: selection; CLI/workflow: "overrides")
OV_KEYS = (
    "scale_mode",
    "scale_pct",
    "scale_mm",
    "rotate",
    "frame",
    "margin_mm",
    "bleed_mm",
    "bleed_mode",
    "bleed_color",
    "roll_pick",
    "align",
    "material",
)


def copies_mode(s) -> str:
    """How copies are sent – split_copies=False (old settings) means a copy count."""
    if not getattr(s, "split_copies", True):
        return "count"
    m = getattr(s, "copies_mode", "sheets")
    return m if m in COPIES_MODES else "sheets"


def clean_ov(d) -> dict:
    """Only the permitted overrides (unknown keys are dropped)."""
    return {k: v for k, v in (d or {}).items() if k in OV_KEYS} if isinstance(d, dict) else {}


def eff(s, it):
    """Settings for this plan: those of the job plus its overrides."""
    ov = dict(getattr(it, "ov", None) or {})
    if getattr(it, "frame", "") and "frame" not in ov:
        ov["frame"] = it.frame
    return dataclasses.replace(s, **ov) if ov else s


def factor(area, s) -> float:
    """Scale factor: percentage, or short/long edge to a measure (mm, without bleed)."""
    mode = getattr(s, "scale_mode", "pct")
    if mode in ("short", "long") and s.scale_mm > 0 and area is not None:
        edge = min(area.w_mm, area.h_mm) if mode == "short" else max(area.w_mm, area.h_mm)
        if edge > 0.1:
            return max(0.01, s.scale_mm / edge)
    return max(1.0, s.scale_pct) / 100.0


def scale_text(s) -> str:
    """Human-readable description of the scaling in ``s`` (percentage, or length of the short/long edge)."""
    mode = getattr(s, "scale_mode", "pct")
    if mode == "short" and s.scale_mm > 0:
        return tr("kurze Kante {0} mm").format(mm_text(s.scale_mm))
    if mode == "long" and s.scale_mm > 0:
        return tr("lange Kante {0} mm").format(mm_text(s.scale_mm))
    return f"{mm_text(s.scale_pct)} %"


OVERWIDTH = ("none", "crop", "tile")


def defaults_for(kind: str) -> dict:
    """Defaults per kind: poster = quality print, side by side, crop when too wide, no plan paper selection."""
    if kind == "poster":
        return {
            "kind": "poster",
            "nest": False,
            "overwidth": "crop",
            "weights": [],
            "frame": "none",
            "align": "center",
            "quality_mode": "quality",
        }
    return {"kind": "plan", "quality_mode": "production"}


QUALITY_MODES = ("production", "quality")


def quality_mode_of(s) -> str:
    """Production print (plan) or quality print (poster) – can be switched with quality_mode."""
    m = getattr(s, "quality_mode", "") or ""
    return m if m in QUALITY_MODES else ("quality" if getattr(s, "kind", "plan") == "poster" else "production")


def apply_quality_mode(caps, vals: dict, s, mat: dict | None = None) -> dict:
    """Set the driver's quality option to the lowest (production print) or highest level (quality print).
    Precedence: set by hand in options; a material of the same category (plan ↔ production,
    quality ↔ quality) with its own quality.
    """
    from . import printers

    if caps is None:
        return vals
    key = caps.roles.get("quality")
    opt = caps.options.get(key) if key else None
    if opt is None or key in (s.options or {}):
        return vals
    mode = quality_mode_of(s)
    mat = mat or {}
    if (mat.get("quality") or key in (mat.get("options") or {})) and (mat.get("category") == "plan") == (
        mode == "production"
    ):
        return vals
    v = printers.quality_choice(opt, mode, vals.get(key, ""))
    if v:
        vals[key] = v
    return vals


# --------------------------------------------------------------------------- #
# frame / print area
# --------------------------------------------------------------------------- #
@dataclass
class Area:
    """The part of a page that is printed: its rectangle and how it was found (frame, margin, page, empty)."""

    rect: tuple  # (x0, y0, x1, y1) in pt, coordinates of the displayed page (may extend beyond it)
    kind: str  # frame | margin | page | empty
    note: str = ""

    @property
    def w_mm(self) -> float:
        """Width of the area in mm."""
        return (self.rect[2] - self.rect[0]) / MM

    @property
    def h_mm(self) -> float:
        """Height of the area in mm."""
        return (self.rect[3] - self.rect[1]) / MM

    def to_dict(self) -> dict:
        """Plain dict for JSON output."""
        return {
            "rect_pt": [round(v, 2) for v in self.rect],
            "kind": self.kind,
            "w_mm": round(self.w_mm, 1),
            "h_mm": round(self.h_mm, 1),
            "note": self.note,
        }


def num(v: float, digits: int = 2) -> str:
    """Number in the notation of the interface language (comma or point)."""
    from . import l10n, measure

    return measure.fmt(float(v), l10n.current(), digits)


def mm_text(v: float) -> str:
    """594 -> „594“, 599.6 -> „599,6“, 0.1 -> „0,1“."""
    for d in (0, 1, 2):
        if abs(v - round(v, d)) < 0.5 * 10 ** -(d + 1):
            return num(v, d)
    return num(v, 2)


KIND_TEXT = {
    "frame": "Zwei Außenlinien – auf die äußere beschnitten",
    "margin": "Inhalt + Rand",
    "page": "Seite unverändert",
    "empty": "Leere Seite",
}


def _render_gray(page, scale: float, crop=(0, 0, 0, 0)):
    import numpy as np

    bm = page.render(scale=scale, grayscale=True, no_smoothpath=True, may_draw_forms=True, crop=crop)
    a = bm.to_numpy()
    if a.ndim == 3:
        a = a[..., :3].min(axis=2) if a.shape[2] >= 3 else a[..., 0]
    return np.asarray(a)


def _runs(flags) -> list:
    """[(start, end)] of contiguous True ranges (end inclusive)."""
    out, start = [], None
    for i, f in enumerate(flags):
        if f and start is None:
            start = i
        elif not f and start is not None:
            out.append((start, i - 1))
            start = None
    if start is not None:
        out.append((start, len(flags) - 1))
    return out


INK = 230
LONG = 0.6  # line: at least 60 % of the width/height
MAX_GAP_MM = 60.0  # maximum distance from the outer to the inner frame line


def _frames(ink, px_mm: float):
    """Coarse: outer and inner frame in pixels {"outer": (t, b, l, r) lines, "inner": …}, parts may be None."""
    import numpy as np

    H, W = ink.shape
    ys, xs = np.nonzero(ink)
    if len(ys) == 0:
        return None, None, None
    y0, y1, x0, x1 = int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max())
    bbox = (y0, y1, x0, x1)
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    rows = _runs((ink[:, x0 : x1 + 1].sum(axis=1) / bw) >= LONG)
    cols = _runs((ink[y0 : y1 + 1, :].sum(axis=0) / bh) >= LONG)
    if len(rows) < 2 or len(cols) < 2:
        return bbox, None, None
    top, bot, lef, rig = rows[0], rows[-1], cols[0], cols[-1]

    def spans(r0, r1, c0, c1, horizontal, frac=0.9):
        seg = ink[r0 : r1 + 1, c0 : c1 + 1]
        cov = seg.any(axis=0).mean() if horizontal else seg.any(axis=1).mean()
        return cov >= frac

    # outer frame: all four lines continuous between the others
    if not (
        spans(top[0], top[1], lef[0], rig[1], True)
        and spans(bot[0], bot[1], lef[0], rig[1], True)
        and spans(top[0], bot[1], lef[0], lef[1], False)
        and spans(top[0], bot[1], rig[0], rig[1], False)
    ):
        return bbox, None, None
    outer = (top, bot, lef, rig)
    gap = MAX_GAP_MM / px_mm
    it = [r for r in rows[1:-1] if top[1] < r[0] <= top[1] + gap]
    ib = [r for r in rows[1:-1] if bot[0] - gap <= r[1] < bot[0]]
    il = [c for c in cols[1:-1] if lef[1] < c[0] <= lef[1] + gap]
    ir = [c for c in cols[1:-1] if rig[0] - gap <= c[1] < rig[0]]
    if not (it and ib and il and ir):
        return bbox, outer, None
    t2, b2, l2, r2 = it[0], ib[-1], il[0], ir[-1]
    if not (
        spans(t2[0], t2[1], l2[0], r2[1], True, 0.85)
        and spans(b2[0], b2[1], l2[0], r2[1], True, 0.85)
        and spans(t2[0], b2[1], l2[0], l2[1], False, 0.85)
        and spans(t2[0], b2[1], r2[0], r2[1], False, 0.85)
    ):
        return bbox, outer, None
    return bbox, outer, (t2, b2, l2, r2)


def _refine(page, W: float, H: float, side: str, approx: float, lo: float, hi: float) -> float | None:
    """Inner edge of the outer line, fine (300 dpi) – side t/b/l/r, approx = coarse position in pt (page
    coordinates), lo..hi = range along the line in pt. -> coordinate in pt or None.
    """

    band = 3.0 * MM
    scale = 300 / 72
    if side in ("t", "b"):
        y0, y1 = max(0.0, approx - band), min(H, approx + band)
        crop = (lo, y0, W - hi, H - y1)  # cut off left, bottom, right, top
    else:
        x0, x1 = max(0.0, approx - band), min(W, approx + band)
        crop = (x0, lo, W - x1, H - hi)
    if min(crop) < 0 or crop[0] + crop[2] >= W or crop[1] + crop[3] >= H:
        return None
    a = _render_gray(page, scale, crop)
    ink = a < INK
    if side in ("t", "b"):
        runs = _runs(ink.mean(axis=1) >= 0.5)
        if not runs:
            return None
        # row 0 = top (y1)
        if side == "t":
            r = runs[0]  # topmost line in the band -> inner edge at the bottom
            return y1 - (r[1] + 1) / scale
        r = runs[-1]
        return y1 - r[0] / scale  # bottommost line -> inner edge at the top
    runs = _runs(ink.mean(axis=0) >= 0.5)
    if not runs:
        return None
    if side == "l":
        r = runs[0]
        return x0 + (r[1] + 1) / scale
    r = runs[-1]
    return x0 + r[0] / scale


def detect(doc, i: int, mode: str = "auto", margin_mm: float = 5.0) -> Area:
    """Print area of a plan page."""
    W, H = doc.get_page_size(i)
    if mode == "none":
        return Area((0.0, 0.0, W, H), "page")
    page = doc[i]
    try:
        longest_in = max(W, H) / 72
        dpi = max(20.0, min(50.0, 3200 / longest_in))
        scale = dpi / 72
        a = _render_gray(page, scale)
        ink = a < INK
        px_mm = 25.4 / dpi
        bbox, outer, inner = _frames(ink, px_mm)
        if bbox is None:
            return Area((0.0, 0.0, W, H), "empty", tr("Leere Seite"))
        h_px, w_px = ink.shape

        def ypt(row):  # Pixelzeile (Oberkante) -> pt
            return H - row * H / h_px

        def xpt(col):
            return col * W / w_px

        note = ""
        if mode in ("auto", "frame") and inner is not None:
            (t, b, ln, r) = outer
            x0, x1 = xpt(ln[1] + 1), xpt(r[0])
            y1, y0 = ypt(t[1] + 1), ypt(b[0])
            span_x = (x0 + (x1 - x0) * 0.3, x1 - (x1 - x0) * 0.3)
            span_y = (y0 + (y1 - y0) * 0.3, y1 - (y1 - y0) * 0.3)
            ft = _refine(page, W, H, "t", (ypt(t[0]) + ypt(t[1] + 1)) / 2, span_x[0], span_x[1])
            fb = _refine(page, W, H, "b", (ypt(b[0]) + ypt(b[1] + 1)) / 2, span_x[0], span_x[1])
            fl = _refine(page, W, H, "l", (xpt(ln[0]) + xpt(ln[1] + 1)) / 2, span_y[0], span_y[1])
            fr = _refine(page, W, H, "r", (xpt(r[0]) + xpt(r[1] + 1)) / 2, span_y[0], span_y[1])
            # slightly inwards so that nothing of the line remains
            e = 0.15 * MM
            rect = (
                (fl if fl is not None else x0) + e,
                (fb if fb is not None else y0) + e,
                (fr if fr is not None else x1) - e,
                (ft if ft is not None else y1) - e,
            )
            return Area(rect, "frame")
        if mode == "frame":
            note = tr("Keine zwei Außenlinien gefunden – Inhalt + Rand")
        y0p, y1p, x0p, x1p = bbox
        m = margin_mm * MM
        rect = (xpt(x0p) - m, ypt(y1p + 1) - m, xpt(x1p + 1) + m, ypt(y0p) + m)
        return Area(rect, "margin", note)
    finally:
        page.close()


# --------------------------------------------------------------------------- #
# rolls and run length
# --------------------------------------------------------------------------- #
@dataclass
class Fit:
    """How one print area fits on one roll: size across and along the roll and whether it is rotated."""

    roll: int  # index in the list of rolls
    width_mm: float  # roll width
    across: float  # across the roll (mm)
    along: float  # length on the roll (mm)
    rotated: bool  # rotated by 90° relative to the page


MARKS_MM = (layout.MARK_OFFSET + layout.MARK_LEN) / MM + 1.0


def margins_mm(s: PlanSettings) -> tuple:
    """Addition per side (left, bottom, right, top) in mm, as the page stands: a hem replaces the bleed
    there; plus room for cut/register marks.
    """
    marks = MARKS_MM if (s.crop_marks or s.printcut_marks) else 0.0
    out = []
    for side in "lbrt":
        e = max(0.0, s.hem_mm) if (s.hem_mm > 0 and side in s.hem_sides) else max(0.0, s.bleed_mm)
        out.append(e + marks)
    return tuple(out)


def extra_mm(s: PlanSettings) -> float:
    """Largest addition per side (bleed/hem + marks)."""
    return max(margins_mm(s))


def finished_size(area: Area, s: PlanSettings) -> tuple:
    """Size ``(width, height)`` in mm of the printed piece: the scaled print area plus the margins."""
    f = factor(area, s)
    left, b, r, t = margins_mm(s)
    return area.w_mm * f + left + r, area.h_mm * f + b + t


def choose(w: float, h: float, rolls: list, rotate: str = "auto") -> Fit | None:
    """Roll and orientation for a plan w × h (mm, as the page stands)."""
    best = None
    for i, r in enumerate(rolls):
        if getattr(r, "empty", False):
            continue
        for rot in (False, True):
            across, along = (h, w) if rot else (w, h)
            if rotate == "keep" and rot:
                continue
            if rotate == "short" and across > along + 1e-6:
                continue
            if rotate == "long" and across < along - 1e-6:
                continue
            if across > r.width_mm + TOL_MM:
                continue
            key = (round(along, 1), r.width_mm, rot)
            if best is None or key < best[0]:
                best = (key, Fit(i, r.width_mm, across, along, rot))
    if best is None and rotate in ("short", "long"):
        return choose(w, h, rolls, "auto")  # fits only the other way round
    return best[1] if best else None


def eligible(rolls: list, weights) -> tuple:
    """Rolls with plan paper (grammage matches or is unknown). -> (rolls, note)."""
    ws = {int(w) for w in (weights or []) if w}
    if not ws or not rolls:
        return list(rolls), ""
    ok = [r for r in rolls if not r.weight or r.weight in ws]
    if ok:
        return ok, ""
    return list(rolls), tr("Keine Rolle mit {0} g/m² geladen – alle Rollen werden verwendet.").format(
        " / ".join(str(w) for w in sorted(ws))
    )


@dataclass
class Item:
    """One page to print: document, page, quantity, detected print area and per-plan overrides."""

    page: int  # page in the document
    qty: int = 1  # quantity per set
    area: Area | None = None
    fit: Fit | None = None
    size: tuple = (0.0, 0.0)  # finished size (mm) as the page stands
    hairlines: int = 0
    source: str = ""  # file
    doc: object = None  # pdfium document (not in the log)
    frame: str = ""  # frame per plan ("" = as set)
    ov: dict = field(default_factory=dict)  # overrides of the job settings (OV_KEYS)

    @property
    def label(self) -> str:
        """Display text: file name and page number."""
        return f"{os.path.basename(self.source) or tr('Dokument')} · " + tr("S. {0}").format(self.page + 1)


def place(items: list, rolls: list, s: PlanSettings) -> None:
    """Finished size and roll for every plan (area must be set)."""
    for it in items:
        if it.area is None:
            it.fit = None
            continue
        es = eff(s, it)
        it.size = finished_size(it.area, es)
        it.fit = choose(it.size[0], it.size[1], rolls, es.rotate)


def run_lengths(items: list, rolls: list, copies: int) -> list:
    """Run length per roll: [{"roll", "width_mm", "label", "plans", "single_m", "total_m"}] (plan sizes only)."""
    out = {}
    for it in items:
        if it.fit is None:
            continue
        d = out.setdefault(
            it.fit.roll,
            {
                "roll": it.fit.roll,
                "width_mm": it.fit.width_mm,
                "label": rolls[it.fit.roll].label(),
                "plans": 0,
                "single_m": 0.0,
            },
        )
        d["plans"] += max(0, it.qty)
        d["single_m"] += it.fit.along * max(0, it.qty) / 1000.0
    res = []
    for k in sorted(out, key=lambda k: (out[k]["width_mm"], k)):
        d = out[k]
        d["single_m"] = round(d["single_m"], 3)
        d["total_m"] = round(d["single_m"] * max(1, copies), 3)
        rem = rolls[k].remaining_m
        d["short"] = rem is not None and d["total_m"] > rem
        res.append(d)
    return res


def job_order(items: list, copies: int, collate: bool, order: str, rolls: list | None = None) -> list:
    """[(Item, count)] in print order. Uncollated: every plan with all its copies in a row."""
    seq = [it for it in items if it.fit is not None and it.qty > 0]
    if order == "roll":
        seq.sort(key=lambda it: (it.fit.width_mm, it.fit.roll))  # stable: within a roll as in the list
    copies = max(1, int(copies))
    if not collate:
        return [(it, it.qty * copies) for it in seq]
    return [(it, it.qty) for _c in range(copies) for it in seq]


# --------------------------------------------------------------------------- #
# hairlines
# --------------------------------------------------------------------------- #
def _walk_paths(container, count_fn, get_fn, matrix, out: list, depth: int = 0):
    import ctypes

    import pypdfium2.raw as r

    n = count_fn(container)
    for k in range(n):
        obj = get_fn(container, k)
        m = r.FS_MATRIX()
        if r.FPDFPageObj_GetMatrix(obj, ctypes.byref(m)):
            own = (m.a, m.b, m.c, m.d, m.e, m.f)
        else:
            own = (1, 0, 0, 1, 0, 0)
        t = r.FPDFPageObj_GetType(obj)
        if t == r.FPDF_PAGEOBJ_FORM and depth < 8:
            _walk_paths(
                obj, r.FPDFFormObj_CountObjects, r.FPDFFormObj_GetObject, layout._mul(own, matrix), out, depth + 1
            )
        elif t == r.FPDF_PAGEOBJ_PATH:
            fm, st = ctypes.c_int(0), ctypes.c_int(0)
            if not r.FPDFPath_GetDrawMode(obj, ctypes.byref(fm), ctypes.byref(st)) or not st.value:
                continue
            w = ctypes.c_float(0)
            if not r.FPDFPageObj_GetStrokeWidth(obj, ctypes.byref(w)):
                continue
            # the path's matrix (CTM) also affects the stroke width, as do the enclosing forms
            a, b, c, d = layout._mul(own, matrix)[:4]
            f = abs(a * d - b * c) ** 0.5 or 1.0
            out.append((obj, w.value, f, matrix if depth else None))


def hairlines(doc, i: int, min_mm: float = 0.1, scale_pct: float = 100.0) -> int:
    """Number of drawn lines thinner than min_mm (stroke width 0 = thinnest device line counts too)."""
    import pypdfium2.raw as r

    page = doc[i]
    try:
        found = []
        _walk_paths(page.raw, r.FPDFPage_CountObjects, r.FPDFPage_GetObject, (1, 0, 0, 1, 0, 0), found)
        lim = min_mm * MM
        f2 = max(1.0, scale_pct) / 100.0
        return sum(1 for _o, w, f, _m in found if w * f * f2 < lim - 1e-6)
    finally:
        page.close()


def hairline_boxes(doc, i: int, min_mm: float = 0.1, max_objs: int = 200000) -> tuple:
    """(count, [area (x0, y0, x1, y1) pt]) of the lines thinner than min_mm – for the preflight."""
    import ctypes

    import pypdfium2.raw as r

    page = doc[i]
    try:
        if r.FPDFPage_CountObjects(page.raw) > max_objs:
            return 0, []
        found = []
        _walk_paths(page.raw, r.FPDFPage_CountObjects, r.FPDFPage_GetObject, (1, 0, 0, 1, 0, 0), found)
        lim = min_mm * MM
        n, boxes = 0, []
        for obj, w, f, parent in found:
            if w * f >= lim - 1e-6:
                continue
            n += 1
            left, b, rr, t = (ctypes.c_float() for _ in range(4))
            if not r.FPDFPageObj_GetBounds(obj, ctypes.byref(left), ctypes.byref(b), ctypes.byref(rr), ctypes.byref(t)):
                continue
            box = (left.value, b.value, rr.value, t.value)
            if parent is not None:
                pts = [
                    (x * parent[0] + y * parent[2] + parent[4], x * parent[1] + y * parent[3] + parent[5])
                    for x in (box[0], box[2])
                    for y in (box[1], box[3])
                ]
                box = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
            boxes.append(box)
        return n, boxes
    finally:
        page.close()


def fix_hairlines(doc, pages, min_mm: float = 0.1, scale_pct: float = 100.0):
    """Copy of the document in which lines thinner than min_mm are raised to min_mm. -> (copy, count)."""
    import io

    import pypdfium2 as pdfium
    import pypdfium2.raw as r

    buf = io.BytesIO()
    doc.save(buf)
    cp = pdfium.PdfDocument(buf.getvalue())
    n = 0
    lim = min_mm * MM / (max(1.0, scale_pct) / 100.0)
    for i in pages:
        page = cp[i]
        found = []
        _walk_paths(page.raw, r.FPDFPage_CountObjects, r.FPDFPage_GetObject, (1, 0, 0, 1, 0, 0), found)
        changed = False
        for obj, w, f, _m in found:
            if w * f < lim - 1e-6:
                r.FPDFPageObj_SetStrokeWidth(obj, lim / f)
                n += 1
                changed = True
        if changed:
            r.FPDFPage_GenerateContent(page.raw)
        page.close()
    return cp, n


# --------------------------------------------------------------------------- #
# pieces and print pages
# --------------------------------------------------------------------------- #
@dataclass
class Piece:
    """One piece on the roll: a plan/poster or one strip of it (wider than the roll)."""

    item: Item
    rect: tuple  # section of the page (pt) – the print area or one strip of it
    across: float  # mm across the roll (incl. bleed/hem/marks)
    along: float  # mm length on the roll
    rotated: bool
    roll: int
    width_mm: float
    tile: int = 0
    tiles: int = 1
    clipped: bool = False  # wider than the roll – cut off

    @property
    def label(self) -> str:
        """Display text of the piece; for a page split over several strips the strip number is added."""
        t = self.item.label
        if self.tiles > 1:
            t += " · " + tr("Bahn {0}/{1}").format(self.tile + 1, self.tiles)
        return t


@dataclass
class Run:
    """One print page = one job: one piece or several side by side."""

    roll: int
    width_mm: float
    across: float  # paper width (mm)
    along: float  # paper length (mm)
    pieces: list  # [(Piece, x_mm, y_mm)] – position on the page (bottom left)
    copies: int = 1

    @property
    def label(self) -> str:
        """Display text of the run: the first piece, plus the number of further pieces."""
        if not self.pieces:
            return ""
        first = self.pieces[0][0].label
        n = len(self.pieces)
        return first if n == 1 else first + " " + tr("+ {0} weitere").format(n - 1)


def roll_key(r) -> str:
    """Identifier of a roll for the fixed selection: source slot in the driver, else name on the device, else width."""
    return r.slot or r.device or r.name or f"{round(r.width_mm, 1)}"


def find_roll(rolls: list, key: str):
    """Index of the roll with this identifier (or None)."""
    if not key:
        return None
    live = [(k, r) for k, r in enumerate(rolls) if not getattr(r, "empty", False)]
    for k, r in live:
        if roll_key(r) == key:
            return k
    low = str(key).strip().lower()
    for k, r in live:  # source slot, name on the device, display name
        if low in {x.lower() for x in (r.slot, r.device, r.name) if x}:
            return k
    try:
        w = float(str(key).replace(",", ".").lower().removesuffix("mm").strip())
    except ValueError:
        return None
    for k, r in live:  # width
        if abs(r.width_mm - w) <= TOL_MM:
            return k
    return None


def _words(t: str) -> set:
    return {w for w in re.findall(r"[a-zäöüß]{3,}", (t or "").lower())}


def match_material(rolls: list, mat: dict) -> list:
    """Rolls that match the material: same grammage, otherwise similar media/material name. [] = none."""
    if mat.get("device"):  # from the device: exactly the roll(s) with this media
        hit = [
            r
            for r in rolls
            if not getattr(r, "empty", False)
            and (r.media or r.name) == mat["device_media"]
            and (not mat["weight"] or r.weight == mat["weight"])
        ]
        if hit:
            return hit
    w = int(mat.get("weight") or 0)
    by_w = [r for r in rolls if w and r.weight == w and not getattr(r, "empty", False)]
    if by_w:
        return by_w
    names = _words(mat.get("name", "")) | _words(mat.get("media", ""))
    if not names:
        return []
    return [r for r in rolls if not getattr(r, "empty", False) and names & _words(f"{r.media} {r.name}")]


def eligible_for(rolls: list, s: PlanSettings) -> tuple:
    """Rolls for this job. A fixed roll comes first; then the material (grammage or name); plan:
    plan paper grammage. -> (rolls, note).
    """
    if s.roll_pick:
        k = find_roll(rolls, s.roll_pick)
        if k is not None:
            return [rolls[k]], ""
        note = tr("Gewählte Rolle ist nicht geladen – Rolle wird automatisch gewählt.")
    else:
        note = ""
    mat = material_of(s)
    if mat is not None:
        hit = match_material(rolls, mat)
        if hit:
            return hit, note
        if mat.get("device"):
            n2 = tr(
                "Material „{0}“ ist am Gerät angelegt, aber nicht geladen – Rolle einlegen bzw. eine Rolle wählen."
            ).format(mat["name"])
            return list(rolls), " ".join(x for x in (note, n2) if x)
        if mat.get("weight"):
            use, n2 = eligible(rolls, [int(mat["weight"])])
            return use, " ".join(x for x in (note, n2) if x)
    if s.kind == "plan":
        use, n2 = eligible(rolls, s.weights)
        return use, " ".join(x for x in (note, n2) if x)
    return list(rolls), note


DEV_PREFIX = "dev:"  # material as reported by the printer: "dev:<g/m²>:<media name>"


def device_material_id(roll) -> str:
    """Identifier of a material that is reported by the device (not in the materials list)."""
    return f"{DEV_PREFIX}{int(roll.weight or 0)}:{roll.media or roll.name}"


def device_materials(rolls: list, catalog: list | None = None) -> list:
    """Materials according to the device: first the media of the loaded rolls, then those defined in the
    device's media catalogue but not loaded. [{"id", "name", "weight", "loaded", …}], without duplicates.
    """
    out, seen = [], set()
    for r in rolls:
        if getattr(r, "empty", False) or not (r.media or r.weight):
            continue
        mid = device_material_id(r)
        if mid in seen:
            continue
        seen.add(mid)
        out.append(dict(_dev_mat(mid), loaded=True))
    names = {m["device_media"].lower() for m in out}
    for c in catalog or []:
        name = str(c.get("name") or "").strip()
        if not name or name.lower() in names:
            continue
        mid = f"{DEV_PREFIX}{int(c.get('weight') or 0)}:{name}"
        if mid in seen:
            continue
        seen.add(mid)
        out.append(dict(_dev_mat(mid), loaded=False, type=c.get("type", "")))
    return out


def _dev_mat(mid: str) -> dict:
    w, _sep, name = mid[len(DEV_PREFIX) :].partition(":")
    return {
        "id": mid,
        "name": name or tr("Gerät"),
        "weight": int(w) if w.isdigit() else 0,
        "media": "",
        "category": "",
        "printer": "",
        "device": True,
        "device_media": name,
    }


def material_of(s: PlanSettings):
    """Return the material selected in ``s`` as a dict, or None if none is selected or it no longer exists."""
    if not s.material:
        return None
    if s.material.startswith(DEV_PREFIX):
        return _dev_mat(s.material)
    try:
        from . import printmat

        return printmat.find(s.material, s.printer)
    except Exception:  # noqa: BLE001 – optional module
        return None


def _narrowest(rolls: list, across: float, idx: list):
    best = None
    for k, r in zip(idx, rolls, strict=False):
        if getattr(r, "empty", False) or across > r.width_mm + TOL_MM:
            continue
        if best is None or r.width_mm < best[1]:
            best = (k, r.width_mm)
    return best


def nest_fit(w: float, h: float, rolls: list, use: list, count: int, gap: float):
    """Side by side: roll and orientation with the least paper (roll width × length) for count pieces."""
    best = None
    for r in use:
        k = rolls.index(r)
        for rot in (False, True):
            across, along = (h, w) if rot else (w, h)
            if across > r.width_mm + TOL_MM:
                continue
            per_row = max(1, int((r.width_mm + gap + TOL_MM) // (across + gap)))
            rows = -(-count // per_row)
            length = rows * along + (rows - 1) * gap
            key = (round(r.width_mm * length / 1e6, 4), round(length, 1), rot)
            if best is None or key < best[0]:
                best = (key, Fit(k, r.width_mm, across, along, rot))
    return best[1] if best else None


def pieces_for(it: Item, rolls: list, s: PlanSettings, use: list | None = None, count: int = 1) -> list:
    """Pieces of a plan/poster. If it fits on a roll: one. Otherwise, depending on the setting: crop it or
    split it into strips with overlap (only on the matching rolls).
    """
    if it.area is None:
        return []
    s = eff(s, it)
    if it.ov.get("roll_pick") or it.ov.get("material"):  # own roll/own material: own selection
        use = eligible_for(rolls, s)[0]
    use = [r for r in (use if use is not None else rolls) if not getattr(r, "empty", False)]
    if it.fit is not None and s.nest and s.rotate == "auto" and count > 1:
        nf = nest_fit(it.size[0], it.size[1], rolls, use, count, max(0.0, s.gap_mm))
        if nf is not None:
            return [Piece(it, it.area.rect, nf.across, nf.along, nf.rotated, nf.roll, nf.width_mm)]
    if it.fit is not None:
        return [Piece(it, it.area.rect, it.fit.across, it.fit.along, it.fit.rotated, it.fit.roll, it.fit.width_mm)]
    if s.overwidth not in ("crop", "tile") or not use:
        return []
    idx = [rolls.index(r) for r in use]
    widest = max(r.width_mm for r in use)
    f = factor(it.area, s)
    left, b, r_, t = margins_mm(s)
    x0, y0, x1, y1 = it.area.rect
    cw, ch = it.area.w_mm * f, it.area.h_mm * f
    best = None
    for rot in (False, True):
        if rot and s.rotate == "keep":
            continue
        # across the roll: unrotated the page width, rotated the height
        c_across, m_across = (ch, b + t) if rot else (cw, left + r_)
        c_along, m_along = (cw, left + r_) if rot else (ch, b + t)
        avail = widest - m_across
        if avail <= 10:
            continue
        if s.overwidth == "crop":
            key = (c_across - avail, c_along)  # cut off little, then short
        else:
            n = max(1, -(-(c_across - s.overlap_mm) // max(1.0, avail - s.overlap_mm)))
            key = (n, c_along)
        if best is None or key < best[0]:
            best = (key, rot, c_across, m_across, c_along, m_along, avail)
    if best is None:
        return []
    _k, rot, c_across, m_across, c_along, m_along, avail = best
    along = c_along + m_along

    def sub(a0, a1):
        """Range a0..a1 (mm, across the roll, from the start) as a section of the page (pt)."""
        if rot:  # across = page height (rotated: the top comes first)
            return (x0, y1 - a1 * MM / f, x1, y1 - a0 * MM / f)
        return (x0 + a0 * MM / f, y0, x0 + a1 * MM / f, y1)

    if s.overwidth == "crop":
        w = min(c_across, avail)
        k = _narrowest(use, w + m_across, idx)
        return [Piece(it, sub(0, w), w + m_across, along, rot, k[0], k[1], clipped=c_across > avail + TOL_MM)]
    ov = max(0.0, s.overlap_mm)
    n = int(max(1, -(-(c_across - ov) // max(1.0, avail - ov))))
    sw = (c_across + (n - 1) * ov) / n
    out = []
    for j in range(n):
        a0 = j * (sw - ov)
        k = _narrowest(use, sw + m_across, idx)
        out.append(Piece(it, sub(a0, a0 + sw), sw + m_across, along, rot, k[0], k[1], tile=j, tiles=n))
    return out


def _shelf(pieces: list, width: float, gap: float, max_len: float, roll: int) -> list:
    """Pieces side by side (shelf algorithm, tallest first) -> print pages (Run) on one roll.
    Every row is its own print page: the printer cuts after every row (never several rows or copies
    below each other on one sheet). Identical rows are combined into one page with a copy count –
    "cut individually" turns that back into one job per copy. max_len: no longer used.
    """
    pcs = sorted(pieces, key=lambda p: (-p.along, -p.across))
    rows = []  # [height, used width, [(piece, x)]]
    for p in pcs:
        for row in rows:
            if row[1] + gap + p.across <= width + TOL_MM and p.along <= row[0] + TOL_MM:
                row[2].append((p, row[1] + gap))
                row[1] += gap + p.across
                break
        else:
            rows.append([p.along, p.across, [(p, 0.0)]])
    runs, keys = [], []
    for h, w, items in rows:
        key = tuple((id(p.item), p.item.page, p.tile, round(x, 1), round(p.along, 1)) for p, x in items)
        if runs and keys[-1] == key:  # same row as the one before: only raise the copy count
            runs[-1].copies += 1
            continue
        placed = [(p, x, h - p.along) for p, x in items]
        runs.append(Run(roll, pieces[0].width_mm, w, h, placed))
        keys.append(key)
    return runs


def build_runs(items: list, rolls: list, s: PlanSettings, copies: int | None = None) -> list:
    """Print pages in print order. Without side by side: one piece per page (uncollated: all copies of a
    piece in a row, collated: set by set, optionally by roll width). With side by side: all copies
    distributed over the rolls together, one page per row (cut off).
    """
    return [_aligned(r, s) for r in _build_runs(items, rolls, s, copies)]


def _aligned(run: Run, s: PlanSettings) -> Run:
    """Page at the full roll width, content at the edge (left/right) or in the middle. That way the printer
    places nothing itself: at the edge only a lengthwise cut remains, in the middle it hides nothing.
    """
    if len(run.pieces) == 1:  # one piece: position as set for this plan
        s = eff(s, run.pieces[0][0].item)
    if s.align not in ALIGNS or run.width_mm <= 0 or run.across >= run.width_mm - 0.05:
        return run
    free = run.width_mm - run.across
    dx = {"left": 0.0, "right": free, "center": free / 2.0}[s.align]
    return Run(run.roll, run.width_mm, run.width_mm, run.along, [(p, x + dx, y) for p, x, y in run.pieces], run.copies)


def _build_runs(items: list, rolls: list, s: PlanSettings, copies: int | None = None) -> list:
    copies = max(1, int(s.copies if copies is None else copies))
    use, _n = eligible_for(rolls, s)
    seq = []
    for it in items:
        if it.qty > 0:
            seq += [(p, it.qty) for p in pieces_for(it, rolls, s, use, it.qty * copies)]
    if not s.nest:
        if s.order == "roll":
            seq.sort(key=lambda x: (x[0].width_mm, x[0].roll))
        one = [(p, q) for p, q in seq]
        if not s.collate:
            return [Run(p.roll, p.width_mm, p.across, p.along, [(p, 0.0, 0.0)], q * copies) for p, q in one]
        return [Run(p.roll, p.width_mm, p.across, p.along, [(p, 0.0, 0.0)], q) for _c in range(copies) for p, q in one]
    by_roll = {}
    for p, q in seq:
        by_roll.setdefault(p.roll, []).extend([p] * (q * copies))
    runs = []
    for k in sorted(by_roll, key=lambda k: (rolls[k].width_mm, k)):
        runs += _shelf(by_roll[k], rolls[k].width_mm, max(0.0, s.gap_mm), max(0.5, s.max_page_m), k)
    return runs


def lengths(items: list, rolls: list, s: PlanSettings) -> list:
    """Run length per roll for one set and for all copies (side by side: distributed anew each time)."""

    def per_roll(runs):
        d = {}
        for run in runs:
            e = d.setdefault(run.roll, [0.0, 0])
            e[0] += run.along * run.copies / 1000.0
            e[1] += len(run.pieces) * run.copies
        return d

    one = per_roll(build_runs(items, rolls, s, 1))
    allc = per_roll(build_runs(items, rolls, s)) if max(1, int(s.copies)) > 1 else one
    res = []
    for k in sorted(set(one) | set(allc), key=lambda k: (rolls[k].width_mm, k)):
        single, plans = one.get(k, (0.0, 0))
        total = allc.get(k, (0.0, 0))[0]
        rem = rolls[k].remaining_m
        res.append(
            {
                "roll": k,
                "width_mm": rolls[k].width_mm,
                "label": rolls[k].label(),
                "plans": plans,
                "single_m": round(single, 3),
                "total_m": round(total, 3),
                "short": rem is not None and total > rem,
            }
        )
    return res


# --------------------------------------------------------------------------- #
# drawing
# --------------------------------------------------------------------------- #
def _hex_rgb(c: str) -> tuple:
    c = str(c or "#ffffff").lstrip("#")
    try:
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    except (ValueError, IndexError):
        return 255, 255, 255


def _rect(page, x, y, w, h, rgb, m):
    import pypdfium2.raw as r

    ro = r.FPDFPageObj_CreateNewRect(x, y, w, h)
    r.FPDFPageObj_SetFillColor(ro, rgb[0], rgb[1], rgb[2], 255)
    r.FPDFPath_SetDrawMode(ro, r.FPDF_FILLMODE_WINDING, False)
    r.FPDFPageObj_Transform(ro, *m)
    r.FPDFPage_InsertObject(page.raw, ro)


def _line(page, x0, y0, x1, y1, m, width=0.25, gray=0, dash=None):
    import ctypes

    import pypdfium2.raw as r

    o = r.FPDFPageObj_CreateNewPath(x0, y0)
    r.FPDFPath_LineTo(o, x1, y1)
    r.FPDFPageObj_SetStrokeColor(o, gray, gray, gray, 255)
    r.FPDFPageObj_SetStrokeWidth(o, width)
    if dash:
        arr = (ctypes.c_float * len(dash))(*dash)
        r.FPDFPageObj_SetDashArray(o, arr, len(dash), 0.0)
    r.FPDFPath_SetDrawMode(o, r.FPDF_FILLMODE_NONE, True)
    r.FPDFPageObj_Transform(o, *m)
    r.FPDFPage_InsertObject(page.raw, o)


def _circle_obj(page, cx, cy, rad, m, width=0.4, gray=90):
    import pypdfium2.raw as r

    _kind, (sx, sy), segs = layout._circle(cx, cy, rad)
    o = r.FPDFPageObj_CreateNewPath(sx, sy)
    for c1, c2, pt in segs:
        r.FPDFPath_BezierTo(o, c1[0], c1[1], c2[0], c2[1], pt[0], pt[1])
    r.FPDFPath_Close(o)
    r.FPDFPageObj_SetStrokeColor(o, gray, gray, gray, 255)
    r.FPDFPageObj_SetStrokeWidth(o, width)
    r.FPDFPath_SetDrawMode(o, r.FPDF_FILLMODE_NONE, True)
    r.FPDFPageObj_Transform(o, *m)
    r.FPDFPage_InsertObject(page.raw, o)


def grommet_points(w: float, h: float, inset: float, spacing: float, sides: str = "lrtb") -> list:
    """Eyelets on a trim size w × h (any unit): always in the corners, evenly in between, spacing at most
    spacing. -> [(x, y)] from bottom left.
    """
    if spacing <= 0 or w <= 2 * inset or h <= 2 * inset:
        return []
    pts = set()

    def edge(p0, p1):
        (ax, ay), (bx, by) = p0, p1
        L = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
        n = max(1, int(-(-L // spacing)))
        for k in range(n + 1):
            pts.add((round(ax + (bx - ax) * k / n, 3), round(ay + (by - ay) * k / n, 3)))

    a, b_, c, d = (inset, inset), (w - inset, inset), (w - inset, h - inset), (inset, h - inset)
    if "b" in sides:
        edge(a, b_)
    if "r" in sides:
        edge(b_, c)
    if "t" in sides:
        edge(d, c)
    if "l" in sides:
        edge(a, d)
    return sorted(pts)


def fold_positions(w: float, h: float) -> tuple:
    """Folding to DIN 824 (simplified, form A): vertically from the right in 190 mm panels until 210 mm
    (incl. 20 mm filing margin) remain on the left; horizontally in 297 mm panels from the bottom. -> ([x mm], [y mm]).
    """
    xs, x = [], w
    while x - 190.0 >= 210.0 - 1e-6:
        x -= 190.0
        xs.append(round(x, 2))
    if w > 210.0 + 1e-6 and (not xs or xs[-1] > 210.0 + 1e-6):
        xs.append(210.0)
    ys, y = [], 297.0
    while y < h - 1e-6:
        ys.append(round(y, 2))
        y += 297.0
    return sorted(set(v for v in xs if 0 < v < w)), ys


def _draw_piece(out, page, tiles, src, p: Piece, s: PlanSettings, ox: float, oy: float, cuts: list):
    """One piece at (ox, oy) pt on the page: content, bleed, hem, marks, eyelets, fold marks."""
    import pypdfium2 as pdfium

    M = pdfium.PdfMatrix
    s = eff(s, p.item)
    f = factor(p.item.area, s)
    x0, y0, x1, y1 = p.rect
    cw, ch = (x1 - x0) * f, (y1 - y0) * f
    left, b, r_, t = (v * MM for v in margins_mm(s))
    hem = {k: (max(0.0, s.hem_mm) * MM if (s.hem_mm > 0 and k in s.hem_sides) else 0.0) for k in "lbrt"}
    bl, bb, br, bt = ((0.0 if hem[k] else max(0.0, s.bleed_mm) * MM) for k in "lbrt")
    PH = ch + b + t
    rot = layout._rot90ccw(PH) if p.rotated else (1, 0, 0, 1, 0, 0)
    m = layout._mul(rot, layout._translate(ox, oy))
    # 1 content clipped to the section
    t1 = tiles.new_page(cw, ch)
    o = src.page_as_xobject(p.item.page, tiles).as_pageobject()
    o.transform(M(*layout._mul(layout._translate(-x0, -y0), layout._scale(f))))
    t1.insert_obj(o)
    t1.gen_content()
    t1.close()
    k1 = len(tiles) - 1
    content, cx, cy = k1, left, b
    if s.bleed_mode == "mirror" and (bl or bb or br or bt):
        t2 = tiles.new_page(cw + bl + br, ch + bb + bt)
        for dx in ([-1] if bl else []) + [0] + ([1] if br else []):
            for dy in ([-1] if bb else []) + [0] + ([1] if bt else []):
                mm_ = (1, 0, 0, 1, 0, 0)
                if dx == -1:
                    mm_ = layout._mul(mm_, (-1, 0, 0, 1, 0, 0))
                elif dx == 1:
                    mm_ = layout._mul(mm_, (-1, 0, 0, 1, 2 * cw, 0))
                if dy == -1:
                    mm_ = layout._mul(mm_, (1, 0, 0, -1, 0, 0))
                elif dy == 1:
                    mm_ = layout._mul(mm_, (1, 0, 0, -1, 0, 2 * ch))
                xo = tiles.page_as_xobject(k1, tiles).as_pageobject()
                xo.transform(M(*layout._mul(mm_, layout._translate(bl, bb))))
                t2.insert_obj(xo)
        t2.gen_content()
        t2.close()
        content, cx, cy = len(tiles) - 1, left - bl, b - bb
    if s.bleed_mode == "color" and (bl or bb or br or bt):
        rgb = _hex_rgb(s.bleed_color)
        for rx, ry, rw, rh in (
            (left - bl, b - bb, cw + bl + br, bb),
            (left - bl, b + ch, cw + bl + br, bt),
            (left - bl, b, bl, ch),
            (left + cw, b, br, ch),
        ):
            if rw > 0 and rh > 0:
                _rect(page, rx, ry, rw, rh, rgb, m)
    xo = tiles.page_as_xobject(content, out).as_pageobject()
    xo.transform(M(*layout._mul(layout._translate(cx, cy), m)))
    page.insert_obj(xo)
    # cut edge = trim size + hem
    CX0, CY0, CX1, CY1 = left - hem["l"], b - hem["b"], left + cw + hem["r"], b + ch + hem["t"]
    if s.crop_marks:
        o_ = max(bl, bb, br, bt) + layout.MARK_OFFSET
        L = layout.MARK_LEN
        for xa, ya, xb, yb in (
            (CX0, CY1 + o_, CX0, CY1 + o_ + L),
            (CX1, CY1 + o_, CX1, CY1 + o_ + L),
            (CX0, CY0 - o_, CX0, CY0 - o_ - L),
            (CX1, CY0 - o_, CX1, CY0 - o_ - L),
            (CX0 - o_, CY0, CX0 - o_ - L, CY0),
            (CX0 - o_, CY1, CX0 - o_ - L, CY1),
            (CX1 + o_, CY0, CX1 + o_ + L, CY0),
            (CX1 + o_, CY1, CX1 + o_ + L, CY1),
        ):
            _line(page, xa, ya, xb, yb, m)
    if s.printcut_marks:  # angles at the corners (sensor register marks)
        o_, L, w_ = max(bl, bb, br, bt) + 2.0 * MM, 5.0 * MM, 1.0 * MM
        for cx_, cy_, sx, sy in ((CX0, CY0, -1, -1), (CX1, CY0, 1, -1), (CX0, CY1, -1, 1), (CX1, CY1, 1, 1)):
            ax, ay = cx_ + sx * o_, cy_ + sy * o_
            _rect(page, min(ax, ax + sx * L), min(ay, ay + sy * w_), L, w_, (0, 0, 0), m)
            _rect(page, min(ax, ax + sx * w_), min(ay, ay + sy * L), w_, L, (0, 0, 0), m)
    for k, (xa, ya, xb, yb) in (
        ("l", (left, b, left, b + ch)),
        ("r", (left + cw, b, left + cw, b + ch)),
        ("b", (left, b, left + cw, b)),
        ("t", (left, b + ch, left + cw, b + ch)),
    ):
        if hem[k]:  # fold line of the hem: dashed inside the hem
            dx, dy = {"l": (-1, 0), "r": (1, 0), "b": (0, -1), "t": (0, 1)}[k]
            e = 1.0 * MM
            _line(page, xa + dx * e, ya + dy * e, xb + dx * e, yb + dy * e, m, 0.3, 120, (3.0, 3.0))
    if s.grommet_spacing_mm > 0:
        rad = max(1.0, s.grommet_d_mm / 2) * MM
        for gx, gy in grommet_points(cw / MM, ch / MM, s.grommet_inset_mm, s.grommet_spacing_mm, s.grommet_sides):
            X, Y = left + gx * MM, b + gy * MM
            _circle_obj(page, X, Y, rad, m)
            _line(page, X - 1.5 * MM, Y, X + 1.5 * MM, Y, m, 0.3, 90)
            _line(page, X, Y - 1.5 * MM, X, Y + 1.5 * MM, m, 0.3, 90)
    if s.fold_marks:
        xs, ys = fold_positions(cw / MM, ch / MM)
        T = 5.0 * MM
        for x in xs:
            X = left + x * MM
            _line(page, X, b, X, b + T, m, 0.3, 0)
            _line(page, X, b + ch - T, X, b + ch, m, 0.3, 0)
        for y in ys:
            Y = b + y * MM
            _line(page, left, Y, left + T, Y, m, 0.3, 0)
            _line(page, left + cw - T, Y, left + cw, Y, m, 0.3, 0)
    if s.cut_contour:
        pts = [(X * m[0] + Y * m[2] + m[4], X * m[1] + Y * m[3] + m[5]) for X in (CX0, CX1) for Y in (CY0, CY1)]
        cuts.append((min(q[0] for q in pts), min(q[1] for q in pts), max(q[0] for q in pts), max(q[1] for q in pts)))


def make_run(run: Run, s: PlanSettings, out=None) -> tuple:
    """Print page of a job (width = across the roll). -> (pdfium document, [CutContour rectangles (pt)])."""
    import pypdfium2 as pdfium

    out = out if out is not None else pdfium.PdfDocument.new()
    tiles = pdfium.PdfDocument.new()
    fixed = {}
    cuts = []
    try:
        page = out.new_page(run.across * MM, run.along * MM)
        for p, x, y in run.pieces:
            src = p.item.doc
            if s.fix_hairlines and p.item.hairlines:
                key = (id(src), p.item.page)
                if key not in fixed:
                    fixed[key], _n = fix_hairlines(
                        src, [p.item.page], s.hairline_mm, factor(p.item.area, eff(s, p.item)) * 100.0
                    )
                src = fixed[key]
            _draw_piece(out, page, tiles, src, p, s, x * MM, y * MM, cuts)
        page.gen_content()
        page.close()
    finally:
        tiles.close()
        for d in fixed.values():
            d.close()
    return out, cuts


def make_page(src, i: int, area: Area, fit: Fit, s: PlanSettings, out=None):
    """One plan as a print page (without CutContour). -> pdfium document."""
    it = Item(i, 1, area, fit, doc=src)
    p = Piece(it, area.rect, fit.across, fit.along, fit.rotated, fit.roll, fit.width_mm)
    doc, _c = make_run(Run(fit.roll, fit.width_mm, fit.across, fit.along, [(p, 0.0, 0.0)]), s, out)
    return doc


def add_cut_contour(path: str, cuts_by_page: dict, spot: str = "CutContour", width_pt: float = 0.25) -> None:
    """Draw rectangles as a cut line in the spot colour (separation, 100 % magenta, overprint) –
    VersaWorks, CutStudio, Summa, Graphtec … recognise that as a contour cut.
    """
    if not any(cuts_by_page.values()):
        return
    import pikepdf

    pdf = pikepdf.open(path, allow_overwriting_input=True)
    try:
        fn = pikepdf.Dictionary(FunctionType=2, Domain=[0, 1], C0=[0, 0, 0, 0], C1=[0, 1, 0, 0], N=1)
        cs = pikepdf.Array([pikepdf.Name.Separation, pikepdf.Name("/" + spot), pikepdf.Name.DeviceCMYK, fn])
        gs = pikepdf.Dictionary(Type=pikepdf.Name.ExtGState, OP=True, op=True, OPM=1)
        for i, page in enumerate(pdf.pages):
            rects = cuts_by_page.get(i) or []
            if not rects:
                continue
            res = page.obj.get("/Resources")
            if res is None:
                page.obj.Resources = res = pikepdf.Dictionary()
            for key, val in (("/ColorSpace", ("/PMCut", cs)), ("/ExtGState", ("/PMCutGS", gs))):
                if key not in res:
                    res[key] = pikepdf.Dictionary()
                res[key][val[0]] = val[1]
            ops = ["q /PMCutGS gs /PMCut CS 1 SCN", f"{width_pt:.3f} w"]
            for a, b_, c, d in rects:
                ops.append(f"{a:.3f} {b_:.3f} {c - a:.3f} {d - b_:.3f} re S")
            ops.append("Q")
            page.contents_add(pikepdf.Stream(pdf, ("\n" + "\n".join(ops) + "\n").encode()), prepend=False)
        pdf.save(path)
    finally:
        pdf.close()


def page_value(caps, across: float, along: float) -> str:
    """Paper value for the driver: exactly the size of the print page as a custom size (width across × length)."""
    from . import printers

    return printers.custom_value(round(across, 1), round(along, 1))


IPP_TRIM = ("61", "60", "63", "62", "64")  # trim-after-pages, trim, -after-copies, -after-documents, -after-job
_CUT_KEY = re.compile(r"cut|trim|schneid|abschnitt|schnitt", re.I)
_CUT_SKIP = re.compile(r"contour|kontur|cutcontour|plotter.?cut", re.I)
_CUT_NO = re.compile(r"(^|\b)(none|never|off|no|not|false|aus|kein\w*|nicht|manual|manuell|disabled?)(\b|$)|^0$", re.I)
_CUT_RANK = (
    (re.compile(r"page|seite|sheet|blatt|each|jede", re.I), 5),
    (re.compile(r"auto", re.I), 4),
    (re.compile(r"(^|\b)(on|yes|true|ein|an|enabled?|1)(\b|$)", re.I), 3),
    (re.compile(r"copy|kopie|set|satz|document|dokument", re.I), 2),
    (re.compile(r"job|auftrag", re.I), 1),
)


def cut_values(caps) -> dict:
    """Driver values that make the roll printer cut after every page: IPP finishings trim (61 …), CUPS/PPD
    CutMedia/cupsFinishings, vendor options with cut names. {} = the printer offers no such option.
    """
    if caps is None:
        return {}
    out = {}
    for k, o in caps.options.items():
        if o.installable or _CUT_SKIP.search(f"{k} {o.text}"):
            continue
        vals = {c.value: c.text for c in o.choices}
        if k == "finishings" or k.lower().startswith("cupsfinishing"):
            for v in IPP_TRIM:
                if v in vals:
                    out[k] = v
                    break
            else:
                hit = [v for v, t in vals.items() if re.search(r"trim|cut|schneid", f"{v} {t}", re.I)]
                if hit:
                    out[k] = hit[0]
            continue
        if not _CUT_KEY.search(f"{k} {o.text}"):
            continue
        best, score = None, 0
        for v, t in vals.items():
            txt = f"{v} {t}"
            if _CUT_NO.search(v) or _CUT_NO.search(t):
                continue
            sc = max((r for rx, r in _CUT_RANK if rx.search(txt)), default=0)
            if sc > score:
                best, score = v, sc
        if best is not None:
            out[k] = best
    return out


def config_profile(session, pid: str):
    """Colour profile (entry from the admin configuration) for the id – or None."""
    if not pid:
        return None
    from . import config

    return config.profile_by_id(getattr(session, "cfg", {}) or {}, pid)


def media_for_roll(caps, roll) -> str:
    """Media type in the driver matching the roll (media name or grammage as reported). "" = nothing matches."""
    key = caps.roles.get("mediatype") if caps is not None else None
    if not key or key not in caps.options or roll is None:
        return ""
    want = _words(roll.media)
    best, score = "", 0
    for ch in caps.options[key].choices:
        t = f"{ch.value} {ch.text}"
        sc = len(want & _words(t)) * 2
        if roll.weight and re.search(rf"(?<!\d){roll.weight}\s*g", t, re.I):
            sc += 3
        if sc > score:
            best, score = ch.value, sc
    return best


def write_run(run: Run, s: PlanSettings, path: str, copies: int = 1) -> None:
    """Print page as a PDF (copies > 1: the page that many times – for folders/hot folders without a copy count)."""
    doc, cuts = make_run(run, s)
    try:
        for _k in range(max(1, copies) - 1):
            doc.import_pages(doc, [0])
        doc.save(path)
    finally:
        doc.close()
    if s.cut_contour:
        add_cut_contour(path, {k: cuts for k in range(max(1, copies))})


# --------------------------------------------------------------------------- #
# assemble and print
# --------------------------------------------------------------------------- #
FOLDER_PREFIX = "folder:"  # output into a (hot) folder, e.g. for VersaWorks
FOLDERS_KEY = "plan_hotfolders"  # Benutzereinstellung: [{"name", "dir"}]


def hotfolders() -> list:
    """Output folders configured by the user as ``[{"name": …, "dir": …}]``."""
    from . import l10n

    out = []
    for e in l10n.load_settings().get(FOLDERS_KEY) or []:
        if isinstance(e, dict) and e.get("name") and e.get("dir"):
            out.append({"name": str(e["name"]), "dir": str(e["dir"])})
    return out


def save_hotfolders(lst: list) -> None:
    """Store the list of output folders in the user settings (incomplete entries are dropped)."""
    from . import l10n

    st = l10n.load_settings()
    st[FOLDERS_KEY] = [{"name": str(e["name"]), "dir": str(e["dir"])} for e in lst if e.get("name") and e.get("dir")]
    l10n.save_settings(st)


def is_folder(printer: str) -> bool:
    """Whether ``printer`` names an output folder instead of a printer."""
    return str(printer or "").startswith(FOLDER_PREFIX)


def folder_dir(printer: str) -> str:
    """Directory of the output folder ``printer``; raises ValueError if it is not configured."""
    name = printer[len(FOLDER_PREFIX) :]
    for e in hotfolders():
        if e["name"] == name:
            return e["dir"]
    raise ValueError(tr("Ausgabe-Ordner nicht eingerichtet: {0}").format(name))


def rolls_for(session, printer: str, s: PlanSettings) -> tuple:
    """(rolls, origin, notes). Rolls from the settings take precedence."""
    from . import rolls as rl

    if s.rolls:
        out = []
        for k, e in enumerate(s.rolls):
            r = rl.Roll.from_dict(e) if isinstance(e, dict) else rl.Roll(float(e))
            if not r.name:
                r.name = tr("Rolle {0}").format(k + 1)
            out.append(r)
        caps = session.caps_for(printer) if (session is not None and printer and not is_folder(printer)) else None
        if caps is not None:
            for k, r in enumerate(out):
                if not r.slot:
                    r.slot = rl.slot_for(caps, r.device or r.name, k)
        return out, "settings", []
    if is_folder(printer):
        st = rl.RollState(rl.manual(printer), "manual")
    else:
        st = rl.for_printer(session, printer, live=s.live_rolls)
    notes = []
    if not st.rolls:
        notes.append(
            tr("Keine Rollen bekannt – vom Gerät nichts gemeldet ({0}). Rollen von Hand eintragen.").format(
                st.error or tr("keine Adresse")
            )
        )
    return st.rolls, st.origin, notes


def analyze(doc, pages: list, s: PlanSettings, rolls: list, source: str = "", qty: int = 1) -> list:
    """Create one :class:`Item` per page: detect the print area and find hairlines."""
    items = []
    for p in pages:
        it = Item(p, qty, None, source=source, doc=doc, ov=clean_ov((s.overrides or {}).get(str(p + 1))))
        es = eff(s, it)
        it.area = detect(doc, p, es.frame, es.margin_mm)
        it.hairlines = hairlines(doc, p, s.hairline_mm, factor(it.area, es) * 100.0)
        items.append(it)
    place_all(items, rolls, s)
    return items


def place_all(items: list, rolls: list, s: PlanSettings) -> str:
    """Roll per plan on the matching rolls (plan paper/material). -> note about the roll selection."""
    use, note = eligible_for(rolls, s)
    plain = [it for it in items if not (it.ov.get("roll_pick") or it.ov.get("material"))]
    _place_on(plain, rolls, use, s)
    notes = [note] if note else []
    for it in items:  # own roll/own material per plan
        if it in plain:
            continue
        u, n = eligible_for(rolls, eff(s, it))
        _place_on([it], rolls, u, s)
        if n and n not in notes:
            notes.append(n)
    return " ".join(notes)


def _place_on(items: list, rolls: list, use: list, s: PlanSettings):
    """Place only on the matching rolls, but relate the index to the full list."""
    idx = [rolls.index(r) for r in use]
    place(items, use, s)
    for it in items:
        if it.fit is not None:
            it.fit.roll = idx[it.fit.roll]


def values_for(session, printer: str, caps, s: PlanSettings) -> dict:
    """Driver option values for a plan job: session defaults, then the material, then the settings in ``s``."""
    from .printcli import PrintSettings, resolve

    mat = material_of(s) or {}
    opts = dict(mat.get("options") or {})
    if mat.get("density_key") and mat.get("density"):
        opts[mat["density_key"]] = mat["density"]
    opts.update(s.options or {})
    ps = PrintSettings(
        color=s.color, media=s.media or mat.get("media", ""), quality=mat.get("quality", ""), options=opts
    )
    vals, probs = resolve(caps, session.values_for(printer), ps)
    if probs:
        raise ValueError("; ".join(f"{w}: {m}" for w, m in probs))
    apply_quality_mode(caps, vals, s, mat)
    _set_color(session, printer, s, mat)
    return vals


def _set_color(session, printer: str, s: PlanSettings, mat: dict):
    """Colour profile and intent of this print: a choice in s (profile/intent – e.g. for tests) before the material,
    the material before the setting of the printer (snapshot from print_items, otherwise the current one)."""
    if not hasattr(session, "color"):
        return
    base = getattr(session, "_plan_color_base", {}).get(printer)
    pid, intent = base if base is not None else session.color_for(printer)
    if s.profile not in ("", "admin"):
        pid = "" if s.profile == "none" else s.profile
    elif mat.get("profile"):
        pid, intent = mat["profile"], mat.get("intent") or intent
    session.color[printer] = (pid, s.intent or intent)


def _neutral_media(caps, key: str) -> str:
    """Media type value that requests nothing specific (auto/any/device chooses) – otherwise the driver default."""
    opt = caps.options.get(key)
    if opt is None:
        return ""
    for ch in opt.choices:
        if re.search(
            r"^(auto|any|automatic|none|default|printer\s*default)$|automatisch|beliebig|druckereinst",
            f"{ch.value}".strip(),
            re.I,
        ) or re.search(r"^(auto|automatisch|beliebig)", ch.text.strip(), re.I):
            return ch.value
    return opt.default or ""


def run_values(session, printer: str, caps, base_vals: dict, run: Run, rolls: list, s: PlanSettings) -> tuple:
    """Driver values for one print page (also for --dry-run): size, roll, cut, media type. -> (values, material)."""
    roll = rolls[run.roll] if 0 <= run.roll < len(rolls) else None
    vals = dict(base_vals)
    rs = eff(s, run.pieces[0][0].item) if run.pieces else s  # material/media of this plan
    if rs.material != s.material and caps is not None and not is_folder(printer):
        try:
            vals = dict(values_for(session, printer, caps, rs))
        except ValueError:
            pass
    if caps is None:
        return vals, material_of(rs) or {}
    pkey, skey = caps.roles.get("pagesize"), caps.roles.get("source")
    if pkey:
        vals[pkey] = page_value(caps, run.across, run.along)
    if skey and roll is not None and roll.slot:
        vals[skey] = roll.slot
    if s.cut_sheets:  # cut after every page – unless set differently by hand
        for k, v in cut_values(caps).items():
            if k not in (s.options or {}):
                vals[k] = v
    mkey = caps.roles.get("mediatype")
    rmat = material_of(rs) or {}
    if (
        mkey
        and roll is not None
        and roll.media
        and not s.media
        and mkey not in (s.options or {})
        and not rmat.get("device")
    ):
        # The device reports the roll's media: request exactly that. Another media type from the material
        # (import, by hand) would make the printer wait for a media that is not loaded. If no media type
        # of the driver matches the roll: request nothing specific – the device takes the roll (source).
        mv = media_for_roll(caps, roll) or _neutral_media(caps, mkey)
        if mv:
            vals[mkey] = mv
    elif mkey and roll is not None and not s.media and not rmat.get("media"):
        src = roll  # media type not given: that of the roll (the device chooses accordingly)
        if rmat.get("device"):  # material from the device: exactly this media
            from .rolls import Roll

            src = Roll(roll.width_mm, weight=int(rmat.get("weight") or 0), media=rmat["device_media"])
        mv = media_for_roll(caps, src)
        if mv:
            vals[mkey] = mv
    if s.driver_color_off:
        from .printers import COLOR_OFF_KEY

        vals[COLOR_OFF_KEY] = "1"
    return vals, rmat


def submit_run(
    session, printer: str, caps, base_vals: dict, run: Run, rolls: list, s: PlanSettings, log: bool = True
) -> int | None:
    """Print one print page run.copies times (one job). With a print log entry incl. run length."""
    from . import printjob, printlog

    roll = rolls[run.roll] if 0 <= run.roll < len(rolls) else None
    n = max(1, run.copies)
    vals, rmat = dict(base_vals), {}
    title = s.title or run.label
    jid, err = None, None
    tmp = tempfile.mkdtemp(prefix="passermark-plan-")
    try:
        if is_folder(printer):
            d = folder_dir(printer)
            os.makedirs(d, exist_ok=True)
            import re
            import time

            it0 = run.pieces[0][0].item
            stem = re.sub(r"[^\w.\-]+", "_", os.path.splitext(os.path.basename(it0.source or "plan"))[0])[:50]
            stem += f"_p{it0.page + 1}" + (f"+{len(run.pieces) - 1}" if len(run.pieces) > 1 else "")
            path = os.path.join(d, f"{time.strftime('%Y%m%d-%H%M%S')}_{stem}_{n}x.pdf")
            k = 1
            while os.path.exists(path):
                path = path[:-4] + f"-{k}.pdf"
                k += 1
            part = path + ".part"
            write_run(run, s, part, n)
            os.replace(part, path)
            jid = os.path.basename(path)
            return jid
        vals, rmat = run_values(session, printer, caps, base_vals, run, rolls, s)
        job = os.path.join(tmp, "plan.pdf")
        mode = copies_mode(s)
        cmode = (rmat.get("color_mode") or "convert") if rmat else "convert"
        old_color = session.color.get(printer) if hasattr(session, "color") else None
        icc = ""
        if cmode in ("embed", "none"):
            # colour per material: do not convert – only embed the profile, or nothing at all (device/RIP does it)
            pid, intent = session.color_for(printer)
            prof = config_profile(session, rmat.get("profile") or pid)
            icc = prof.get("file", "") if (prof and cmode == "embed") else ""
            session.color[printer] = ("", intent)

        def prep(path):
            if icc and os.path.isfile(icc):
                from .cmyk import embed_output_intent

                embed_output_intent(path, icc)

        try:
            if mode == "sheets":
                # one job, one page per copy: the printer cuts after every page
                write_run(run, s, job, n)
                prep(job)
                jid = printjob.send_prepared(
                    session, printer, caps, job, title + (f" ×{n}" if n > 1 else ""), vals, 1, True, {}
                )
            elif mode == "jobs" and n > 1:
                write_run(run, s, job)
                prep(job)
                ids = []
                for k in range(n):
                    ids.append(
                        printjob.send_prepared(session, printer, caps, job, f"{title} ({k + 1}/{n})", vals, 1, True, {})
                    )
                jid = ", ".join(str(x) for x in ids if x is not None) or None
            else:
                write_run(run, s, job)
                prep(job)
                jid = printjob.send_prepared(session, printer, caps, job, title, vals, n, True, {})
        except Exception as e:
            err = str(e)
            raise
        finally:
            if cmode in ("embed", "none"):
                if old_color is None:
                    session.color.pop(printer, None)
                else:
                    session.color[printer] = old_color
        return jid
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
        if log and printlog.enabled(session.cfg):
            printlog.write(log_record(caps, printer, run, roll, s, vals, session, jid, err), session.cfg)


def log_record(caps, printer, run: Run, roll, s: PlanSettings, vals: dict, session, jid, err) -> dict:
    """Build the print log record for one run (successful or failed)."""
    from . import printlog

    first = run.pieces[0][0].item
    n = max(1, run.copies)
    pages = sorted({p.item.page for p, _x, _y in run.pieces})
    rec = printlog.build(
        caps if not is_folder(printer) else None,
        printer,
        first.source or None,
        s.title or run.label,
        pages,
        s,
        vals,
        n,
        False,
        False,
        session.color_for(printer) if not is_folder(printer) else ("", ""),
        jid,
        error=err,
        sheet_mm=[round(run.across, 1), round(run.along, 1)],
    )
    e = rec["job"]
    e["kind"] = s.kind
    e["roll_mm"] = round(run.width_mm, 1)
    e["roll"] = roll.label() if roll is not None else None
    e["length_mm"] = round(run.along * n, 1)
    e["run_m"] = round(run.along * n / 1000.0, 3)
    e["pieces"] = [
        {
            "plan": p.label,
            "page": p.item.page + 1,
            "x_mm": round(x, 1),
            "y_mm": round(y, 1),
            "size_mm": [round(p.across, 1), round(p.along, 1)],
            "rotated": p.rotated,
            "clipped": p.clipped,
        }
        for p, x, y in run.pieces
    ]
    e["area"] = first.area.to_dict() if first.area else None
    if len({id(p.item.doc) for p, _x, _y in run.pieces}) == 1 and len(run.pieces) == 1:
        st = compact(
            dataclasses.replace(
                s, printer=printer, copies=n, collate=False, order="list", nest=False, title=s.title, dry_run=False
            )
        )
        st["rolls"] = [{"width_mm": round(run.width_mm, 1), "slot": roll.slot if roll is not None else ""}]
        if first.ov or first.frame:  # log this plan's overrides as well
            st["overrides"] = {
                str(first.page + 1): clean_ov(dict(first.ov, **({"frame": first.frame} if first.frame else {})))
            }
        step = {"job": "plan", "settings": st, "pages": str(first.page + 1)}
        rec["workflow"]["steps"] = list(rec["workflow"]["steps"][:-1]) + [step]
    else:  # several pieces on one page: reprint of all pages of this file
        st = compact(dataclasses.replace(s, printer=printer, copies=1, title=s.title, dry_run=False))
        st["rolls"] = [{"width_mm": round(run.width_mm, 1), "slot": roll.slot if roll is not None else ""}]
        ovs = {str(p.item.page + 1): clean_ov(p.item.ov) for p, _x, _y in run.pieces if p.item.ov}
        if ovs:
            st["overrides"] = ovs
        step = {"job": "plan", "settings": st, "pages": ",".join(str(p + 1) for p in pages)}
        rec["workflow"]["steps"] = list(rec["workflow"]["steps"][:-1]) + [step]
    return rec


def compact(s: PlanSettings) -> dict:
    """Settings as a dict with only the values that differ from the defaults (``printer`` is always kept)."""
    d = dataclasses.asdict(s)
    base = dataclasses.asdict(PlanSettings())
    return {k: v for k, v in d.items() if v != base.get(k) or k == "printer"}


def _job_info(run: Run, rolls: list, s: PlanSettings | None = None) -> dict:
    mode = copies_mode(s) if s is not None else "sheets"
    n = max(1, run.copies)
    return {
        "plan": run.label,
        "pages": [p.item.page + 1 for p, _x, _y in run.pieces],
        "copies": run.copies,
        "copies_mode": mode,
        "jobs_sent": n if mode == "jobs" else 1,
        "sheets_per_job": n if mode == "sheets" else 1,
        "cuts": n,
        "roll_mm": run.width_mm,
        "size_mm": [round(run.across, 1), round(run.along, 1)],
        "rotated": run.pieces[0][0].rotated if len(run.pieces) == 1 else None,
        "pieces": len(run.pieces),
        "slot": rolls[run.roll].slot if 0 <= run.roll < len(rolls) else "",
    }


def print_items(session, printer: str, items: list, rolls: list, s: PlanSettings, progress=None, cancel=None) -> dict:
    """Print plans/posters (order as set). -> info incl. run length and job numbers. The colour profile of the
    session stays as it was (material and test choice only apply to this print)."""
    had = hasattr(session, "color") and printer in session.color
    before = session.color_for(printer) if hasattr(session, "color") else None
    if before is not None:
        session._plan_color_base = {printer: before}
    try:
        return _print_items(session, printer, items, rolls, s, progress, cancel)
    finally:
        if before is not None:
            session._plan_color_base = {}
            if had:
                session.color[printer] = before
            else:
                session.color.pop(printer, None)


def _print_items(session, printer: str, items: list, rolls: list, s: PlanSettings, progress=None, cancel=None) -> dict:
    caps = None if is_folder(printer) else session.caps_for(printer)
    if is_folder(printer):
        base = {}
    else:
        base = values_for(session, printer, caps, s) if not s.dry_run else _try_values(session, printer, caps, s)
    runs = build_runs(items, rolls, s)
    info = summary(printer, items, rolls, s)
    info["cut_options"] = cut_values(caps) if (s.cut_sheets and caps is not None) else {}
    info["jobs"] = []
    for k, run in enumerate(runs):
        if cancel is not None and cancel():
            break
        if progress:
            progress(k, len(runs), run.label)
        rec = _job_info(run, rolls, s)
        if caps is not None:  # what goes to the device (also in a dry run) – to look up when there are problems
            try:
                rv, _m = run_values(session, printer, caps, base, run, rolls, s)
                rec["options"] = caps.job_options(rv)
                r0 = rolls[run.roll] if 0 <= run.roll < len(rolls) else None
                rec["roll_media"] = getattr(r0, "media", "") if r0 is not None else ""
            except Exception as e:  # noqa: BLE001
                rec["options_error"] = str(e)
        if not s.dry_run:
            rec["job_id"] = submit_run(session, printer, caps, base, run, rolls, s)
        info["jobs"].append(rec)
    if progress:
        progress(len(runs), len(runs), "")
    return info


def _try_values(session, printer, caps, s):
    try:
        return values_for(session, printer, caps, s)
    except ValueError:
        return dict(session.values_for(printer))


def summary(printer: str, items: list, rolls: list, s: PlanSettings) -> dict:
    """Overview of a job for the dialog and ``--json``: run length per roll and which plans are clipped or split."""
    lens = lengths(items, rolls, s)
    use, _n = eligible_for(rolls, s)
    clipped, tiled = [], []
    for it in items:
        ps = pieces_for(it, rolls, s, use)
        if any(p.clipped for p in ps):
            clipped.append(it.label)
        if len(ps) > 1:
            tiled.append(it.label)
    return {
        "printer": printer,
        "kind": s.kind,
        "dry_run": s.dry_run,
        "copies": max(1, int(s.copies)),
        "collate": s.collate,
        "nest": s.nest,
        "rolls": [dict(r.to_dict(), label=r.label()) for r in rolls],
        "lengths": lens,
        "single_m": round(sum(d["single_m"] for d in lens), 3),
        "total_m": round(sum(d["total_m"] for d in lens), 3),
        "plans": [
            {
                "plan": it.label,
                "page": it.page + 1,
                "qty": it.qty,
                "area": it.area.to_dict() if it.area else None,
                "size_mm": [round(it.size[0], 1), round(it.size[1], 1)],
                "roll_mm": it.fit.width_mm if it.fit else None,
                "rotated": it.fit.rotated if it.fit else None,
                "length_mm": round(it.fit.along, 1) if it.fit else None,
                "hairlines": it.hairlines,
            }
            for it in items
        ],
        "unfit": [it.label for it in items if it.area is not None and not pieces_for(it, rolls, s, use)],
        "clipped": clipped,
        "tiled": tiled,
        "notes": [],
    }


def cut_file(items: list, rolls: list, s: PlanSettings, path: str, force: int = 0, speed: int = 0) -> int:
    """Cut job (HP-GL/CAMM-GL) for one set: the cut edges of all pieces, page after page along the roll
    (for cutting plotters without printing, e.g. vinyl). -> number of cuts.
    """
    from . import roland

    runs = build_runs(items, rolls, dataclasses.replace(s, collate=False, cut_contour=True), 1)
    rects, base = [], 0.0
    for run in runs:
        _d, cuts = make_run(run, dataclasses.replace(s, cut_contour=True))
        _d.close()
        for a, b_, c, d in cuts:
            rects.append((a / MM, base + b_ / MM, c / MM, base + d / MM))
        base += run.along + max(0.0, s.gap_mm)
    with open(path, "wb") as f:
        f.write(roland.hpgl(roland.rect_paths(rects), force, speed))
    return len(rects)


def save_pdf(items: list, rolls: list, s: PlanSettings, path: str) -> int:
    """All print pages (one copy each) in one PDF – for checking or passing on. -> page count."""
    import pypdfium2 as pdfium

    runs = build_runs(items, rolls, dataclasses.replace(s, collate=False), 1)
    out = pdfium.PdfDocument.new()
    cuts = {}
    try:
        for k, run in enumerate(runs):
            _d, c = make_run(run, s, out)
            cuts[k] = c
        out.save(path)
    finally:
        out.close()
    if s.cut_contour:
        add_cut_contour(path, cuts)
    return len(runs)


def print_pdf(path: str, s: PlanSettings, pages: list | None = None, session=None, progress=None) -> dict:
    """Workflow step "plan": all (selected) pages of the PDF as plans/posters."""
    return plan_files([path], s, pages, session, progress)


def _open(path: str):
    import pypdfium2 as pdfium

    from . import images

    if images.is_image(path):
        return images.images_to_document([path], 96.0)
    return pdfium.PdfDocument(path)


def plan_files(
    paths: list, s: PlanSettings, pages: list | None = None, session=None, progress=None, plt: str = ""
) -> dict:
    """passermark-cli plan / workflow: plans from one or more files – run length, rolls, print.
    pages applies to a single file only. dry_run: calculate only (also without a printer, then with the rolls
    from s.rolls).
    """
    from . import config, printers, printjob
    from .session import Session

    if session is None:
        session = Session(config.load())
    printer = s.printer or ("" if (s.dry_run and s.rolls) else printjob.default_printer(session)) or ""
    if not printer and not s.dry_run:
        raise RuntimeError(tr("Kein Drucker eingerichtet."))
    if printer == printers.PDF_TARGET:
        raise ValueError(tr("Plandruck geht nur auf einen Drucker – zum Prüfen im Programm „Als PDF speichern“."))
    if is_folder(printer):
        folder_dir(printer)  # does the folder exist in the settings?
    elif printer and not s.dry_run:
        try:
            names = [p.name for p in printers.list_printers()]
        except Exception:  # noqa: BLE001 – printer/driver query: works without the value
            names = None
        if names is not None and printer not in names:
            raise ValueError(
                tr("Drucker nicht gefunden: {0} (vorhanden: {1})").format(printer, ", ".join(names) or "–")
            )
    if s.material and material_of(s) is None:
        raise ValueError(tr("Material nicht gefunden: {0}").format(s.material))
    rolls, origin, notes = rolls_for(session, printer, s)
    if not rolls:
        raise ValueError(notes[0] if notes else tr("Keine Rollen bekannt."))
    docs, items = [], []
    try:
        for path in paths:
            doc = _open(path)
            docs.append(doc)
            sel = list(range(len(doc)))
            if pages and len(paths) == 1:
                sel = [p for p in pages if 0 <= p < len(doc)]
            items += analyze(doc, sel, s, rolls, path)
        _use, wnote = eligible_for(rolls, s)
        info = None
        if s.dry_run and printer and not is_folder(printer) and session is not None:
            try:  # dry run with a printer: also shows what would go to the device
                info = print_items(session, printer, items, rolls, s)
            except Exception:  # noqa: BLE001 – printer not reachable: only calculate
                info = None
        if info is not None:
            pass
        elif s.dry_run or not printer:
            info = summary(printer, items, rolls, s)
            info["jobs"] = [_job_info(run, rolls, s) for run in build_runs(items, rolls, s)]
            if s.cut_sheets and printer and not is_folder(printer) and session is not None:
                info["cut_options"] = {}
                try:
                    info["cut_options"] = cut_values(session.caps_for(printer))
                except Exception:  # noqa: BLE001 – dry run also without a reachable printer
                    pass
        else:
            from . import printlog

            with printlog.source(printlog.current() if printlog.current() != "dialog" else "cli"):
                info = print_items(session, printer, items, rolls, s, progress)
        info["roll_origin"] = origin
        info["notes"] = (
            notes
            + ([wnote] if wnote else [])
            + [tr("Passt auf keine Rolle: {0}").format(u) for u in info["unfit"]]
            + [tr("Breiter als die Rolle – abgeschnitten: {0}").format(u) for u in info["clipped"]]
            + [tr("In Bahnen geteilt: {0}").format(u) for u in info["tiled"]]
        )
        hl = sum(it.hairlines for it in items)
        if hl and not s.fix_hairlines:
            info["notes"].append(
                tr("{0} Linie(n) dünner als {1} mm – fix_hairlines hebt sie an.").format(hl, mm_text(s.hairline_mm))
            )
        from . import printmat

        info["notes"] += printmat.notes(material_of(s), session.cfg)
        info["pages"] = len(items)
        if plt:
            info["cut_file"] = {"path": os.path.abspath(plt), "cuts": cut_file(items, rolls, s, plt)}
        return info
    finally:
        for d in docs:
            d.close()
