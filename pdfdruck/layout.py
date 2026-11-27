# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Page selection, scaling and N-up imposition.

Pure geometry (plan_*) is decoupled from pdfium and testable.
impose() builds a vector PDF from it with pypdfium2 (form XObjects)
that fits the chosen paper 1:1 and is printed with print-scaling=none.

Coordinates: PDF points (1/72 inch), origin bottom left.
"Physical" = sheet in portrait as reported by the driver (PaperDimension).
"Logical"   = sheet in the chosen orientation (rotated 90° for landscape).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from .l10n import tr

log = logging.getLogger(__name__)

MM = 72.0 / 25.4

POSTER_FORMATS = {  # width x height in mm (portrait)
    "A0": (841, 1189),
    "A1": (594, 841),
    "A2": (420, 594),
    "A3": (297, 420),
    "A4": (210, 297),
    "B1": (707, 1000),
    "B2": (500, 707),
    "B3": (353, 500),
}
LABEL_H = 9.0  # height of the caption line (pt)

# default grid (columns, rows) for landscape; portrait = swapped
NUP_GRIDS = {2: (2, 1), 4: (2, 2), 6: (3, 2), 8: (4, 2), 9: (3, 3), 16: (4, 4)}

ORDERS = {
    "horizontal": "Horizontal (Z)",
    "horizontal_rev": "Horizontal umgekehrt",
    "vertical": "Vertikal (N)",
    "vertical_rev": "Vertikal umgekehrt",
}


# --------------------------------------------------------------------------- #
# dataclasses
# --------------------------------------------------------------------------- #
@dataclass
class Sheet:
    """A physical sheet: size in points and, if known, the printable area of the device."""

    width: float  # physical, points
    height: float
    imageable: tuple[float, float, float, float] | None = None  # llx,lly,urx,ury

    def __post_init__(self):
        if self.width > self.height:  # always portrait as the reference
            self.width, self.height = self.height, self.width
            if self.imageable:
                left, b, r, t = self.imageable
                # Querformat-Angabe in Hochformat drehen (selten, defensiv)
                self.imageable = (b, self.height - r, t, self.height - left)


@dataclass
class LayoutSettings:
    """Everything the print dialog offers for placing pages on a sheet (scaling, N-up, booklet, poster, marks)."""

    mode: str = "fit"  # fit | actual | shrink | custom
    custom_percent: float = 100.0
    custom_by: str = "percent"  # percent | short | long  (custom: percent or edge measure)
    custom_mm: float = 210.0  # target size of the short or long edge in mm
    nup: int = 1  # 1 = off, otherwise pages per sheet
    cols: int = 0  # >0 and rows>0 => user-defined grid
    rows: int = 0
    order: str = "horizontal"
    tile_mode: str = "fit"  # fit | actual | custom
    tile_percent: float = 100.0
    gap_mm: float = 0.0
    borders: bool = False
    orientation: str = "auto"  # auto | portrait | landscape
    autorotate: bool = True
    center: bool = True
    use_margins: bool = True  # take the unprintable margin of the printer into account
    borderless: bool = False  # borderless: whole sheet; with a trim size in the document the trim size lies on the
    # sheet and the bleed runs beyond the edge (instead of the driver's expansion)
    handling: str = "size"  # size | multiple | booklet | poster
    # booklet
    booklet_sides: str = "both"  # both | front | back
    booklet_binding: str = "left"  # left | right
    booklet_sheets: str = ""  # sheet range, e.g. "1-3" (empty = all)
    booklet_gutter_mm: float = 0.0
    booklet_kind: str = "saddle"  # saddle = saddle stitching (one signature) | stack = single sheets stacked
    # (perfect binding/pad binding) | grouped = signatures of booklet_per_sig sheets each
    booklet_per_sig: int = 4  # grouped: sheets per signature
    booklet_creep_mm: float = 0.0  # creep: per-sheet inward shift (≈ paper thickness)
    booklet_spread: str = "side"  # printer's spreads: side = pages side by side (bound at the side),
    # top = one above the other (bound at the top, calendar)
    booklet_nutzen: bool = False  # impose the booklet as opened printer's spreads (step-and-repeat logic:
    # arrangement, bleed, crop marks, step 2) instead of a folded sheet
    booklet_blanks: str = "end"  # end | before_back (the back of the cover stays the last page)
    booklet_blank_text: str = ""  # note about added blank pages (blank = completely empty)
    booklet_fold_marks: bool = False
    booklet_reg_marks: bool = False  # register marks
    booklet_collation_marks: bool = False  # collation marks on the spine (check the signature order)
    # poster / oversize
    poster_mode: str = "scale"  # scale | sheets | target
    poster_percent: float = 200.0
    poster_cols: int = 2
    poster_rows: int = 2
    poster_target: str = "A2"  # key from POSTER_FORMATS or "custom"
    poster_target_w_mm: float = 420.0
    poster_target_h_mm: float = 594.0
    poster_overlap_mm: float = 10.0
    poster_marks: bool = True  # cut/glue lines
    poster_labels: bool = True  # label per tile
    poster_large_only: bool = False
    # further options
    mirror_h: bool = False  # mirror horizontally (transfer printing)
    mirror_v: bool = False
    step_repeat: bool = False  # one page several times per sheet (step and repeat)
    sr_mode: str = "auto"  # auto (as many as fit) | grid
    sr_cols: int = 2
    sr_rows: int = 5
    sr_gap_mm: float = 0.0
    sr_percent: float = 100.0
    sr_by: str = "percent"  # percent | short | long  (step & repeat size: percent or edge measure)
    sr_mm: float = 85.0  # target size of the short or long edge per step & repeat tile in mm
    sr_orientation: str = "auto"  # sheet: auto | portrait | landscape
    sr_rotate: str = "auto"  # copies: auto | 0 | 90
    sr_join: str = "bleed"  # edge = edge to edge | bleed = bleed to bleed | gap = gap
    sr_sequence: bool = False  # the next page per tile (variable data) instead of repeating one page
    sr_stack: str = "row"  # row = sheet by sheet | stack = cut and stack (stacks stay in sequence)
    sr_pass2: bool = False  # step 2: place the imposed result on a target size once more
    sr_multi: bool = False  # step and repeat switched on (own window) – otherwise e.g. every
    # booklet spread is placed exactly once, centred
    sr2_format: str = "custom"  # target size (value from the device's size list or "custom")
    sr2_w_mm: float = 320.0  # target size, width in mm (adjustable for "custom")
    sr2_h_mm: float = 450.0  # target size, height in mm
    sr2_cols: int = 0  # step 2: grid (columns × rows); 0 × 0 = automatically as many as fit
    sr2_rows: int = 0
    crop_marks: bool = False  # crop marks
    bleed_mm: float = 0.0  # bleed area around the final format; missing bleed is mirrored/stretched
    doc_bleed: bool = True  # final format and bleed from the document (TrimBox/BleedBox) – also without marks
    bleed_mode: str = "mirror"  # missing bleed: mirror | stretch the page edges
    bleed_fill: bool = True  # create missing bleed; off: only the bleed the document has is printed

    @classmethod
    def from_dict(cls, d: dict | None) -> LayoutSettings:
        """Create settings from a dict; unknown keys are ignored and values are cast to the field's type."""
        s = cls()
        d = d or {}
        for k, v in d.items():
            if hasattr(s, k):
                setattr(s, k, type(getattr(s, k))(v))
        if "handling" not in d and (s.nup > 1 or s.cols * s.rows > 1):
            s.handling = "multiple"  # old configurations
        return s

    def to_dict(self) -> dict:
        """Plain dict of all fields."""
        return dict(self.__dict__)

    @property
    def is_nup(self) -> bool:
        """Whether more than one page is placed on a sheet."""
        return self.handling == "multiple" and (
            self.nup > 1 or (self.cols > 0 and self.rows > 0 and self.cols * self.rows > 1)
        )


@dataclass
class ImposeSettings(LayoutSettings):
    """Imposition without a printer (command line, print presets): layout + sheet size."""

    sheet: str = "A4"  # A0–A6, A3+, SRA3, B4–B6, LETTER, LEGAL, TABLOID … or "custom"
    sheet_w_mm: float = 0.0  # for "custom"
    sheet_h_mm: float = 0.0

    def sheet_obj(self) -> Sheet:
        """Return the target sheet as a :class:`Sheet` (named size or custom measures)."""
        if self.sheet.lower() == "custom":
            if self.sheet_w_mm <= 0 or self.sheet_h_mm <= 0:
                raise ValueError(tr("Bogenformat „custom“: sheet_w_mm und sheet_h_mm angeben"))
            w, h = self.sheet_w_mm, self.sheet_h_mm
        else:
            from .printers import STD_SIZES_MM

            key = self.sheet.upper()
            if key not in STD_SIZES_MM:
                raise ValueError(tr("Unbekanntes Bogenformat: {0}").format(self.sheet))
            w, h = STD_SIZES_MM[key]
        return Sheet(w * MM, h * MM, None)


@dataclass
class Placement:
    """One source page on a sheet: rotation, scale, position and optional clip."""

    src: int  # Quellseiten-Index (0-basiert)
    rot: int  # 0 or 90 (additional, counterclockwise)
    scale: float
    x: float  # logical, bottom left corner of the placed page
    y: float
    w: float  # placed size
    h: float
    clip: tuple[float, float, float, float] | None  # logical cell (x,y,w,h) for N-up
    bleed: float = 0.0  # mirrored bleed in pt (around the placed page)
    bleed_sides: tuple = (True, True, True, True)  # left, bottom, right, top
    mirror_h: bool = False
    mirror_v: bool = False
    bleed_mode: str = "mirror"  # how missing bleed is created: mirror | stretch
    bleed_fill: bool = True  # False: no mirrored/stretched bleed, only the document's own (up to own_bleed)
    own_bleed: float = -1.0  # the document's bleed (BleedBox) in pt of the source page; -1 = up to the page edge
    trim: tuple | None = None  # trim size in the document: (left, bottom, right, top) pt -> real bleed
    trim_show_edge: tuple = (False, False, False, False)  # outer sides of the step-and-repeat block: also show the real
    # document edge (incl. existing crop marks)


@dataclass
class SheetPlan:
    """One output sheet: orientation, the placements on it, marks and warnings."""

    landscape: bool
    placements: list[Placement] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Zusatzgrafik in logischen Koordinaten:
    #   ("line", x0, y0, x1, y1, dashed)  |  ("text", x, y, size, text)
    marks: list[tuple] = field(default_factory=list)
    label: str = ""  # description for the preview
    duplex_short: bool = False  # booklet: duplex on the short edge needed


# --------------------------------------------------------------------------- #
# page selection
# --------------------------------------------------------------------------- #
def parse_ranges(text: str, count: int) -> list[int]:
    """'1-3, 5, 8-' -> 0-based indexes. Raises ValueError for nonsense."""
    text = (text or "").strip()
    if not text:
        return list(range(count))
    out: list[int] = []
    for part in re.split(r"[,;]\s*", text):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"(\d*)\s*-\s*(\d*)", part)
        if m:
            a = int(m.group(1)) if m.group(1) else 1
            b = int(m.group(2)) if m.group(2) else count
        elif part.isdigit():
            a = b = int(part)
        else:
            raise ValueError(tr("Ungültiger Bereich: {0!r}").format(part))
        if a < 1 or b > count or a > b:
            raise ValueError(tr("Bereich außerhalb 1–{0}: {1!r}").format(count, part))
        out.extend(range(a - 1, b))
    return out


def select_pages(
    count: int, ranges: str = "", subset: str = "all", reverse: bool = False, current: int | None = None
) -> list[int]:
    """Return the 0-based page indexes to print from a range string, the odd/even subset and the order."""
    pages = [current] if current is not None else parse_ranges(ranges, count)
    if subset == "odd":
        pages = [p for p in pages if (p + 1) % 2 == 1]
    elif subset == "even":
        pages = [p for p in pages if (p + 1) % 2 == 0]
    if reverse:
        pages = pages[::-1]
    return pages


# --------------------------------------------------------------------------- #
# geometry
# --------------------------------------------------------------------------- #
def _logical(sheet: Sheet, landscape: bool):
    """Logical sheet size and printable area (x,y,w,h)."""
    W, H = sheet.width, sheet.height
    left, b, r, t = sheet.imageable or (0.0, 0.0, W, H)
    if not landscape:
        return W, H, (left, b, r - left, t - b)
    # physical (X,Y) -> logical (x,y) = (Y, W - X)
    return H, W, (b, W - r, t - b, r - left)


def _area(sheet: Sheet, landscape: bool, use_margins: bool):
    LW, LH, printable = _logical(sheet, landscape)
    return LW, LH, (printable if use_margins else (0.0, 0.0, LW, LH)), printable


def _fits(rect, area, tol=0.5) -> bool:
    x, y, w, h = rect
    ax, ay, aw, ah = area
    return x >= ax - tol and y >= ay - tol and x + w <= ax + aw + tol and y + h <= ay + ah + tol


def _cell_order(n_cells: int, cols: int, rows: int, order: str) -> list[tuple[int, int]]:
    """Return (column, row) per tile index; row 0 = top."""
    cells = []
    for i in range(n_cells):
        if order.startswith("vertical"):
            c, r = divmod(i, rows)
        else:
            r, c = divmod(i, cols)
        if order.endswith("_rev"):
            c = cols - 1 - c
        cells.append((c, r))
    return cells


def _pick_grid(first_size, sheet: Sheet, s: LayoutSettings):
    """Chooses orientation + grid with the largest fit scale (like Acrobat's 'Auto')."""
    if s.cols > 0 and s.rows > 0:
        grids = [(s.cols, s.rows)]
        if s.orientation == "auto":
            grids.append((s.rows, s.cols))  # the grid may rotate along
    else:
        base = NUP_GRIDS.get(s.nup)
        if base is None:  # e.g. 3, 5 … -> 1 column n rows or the other way round
            base = (s.nup, 1)
        grids = [base, (base[1], base[0])]
    orients = [False, True] if s.orientation == "auto" else [s.orientation == "landscape"]
    gap = s.gap_mm * MM
    pw, ph = first_size
    best = None
    for land in orients:
        _, _, area, _ = _area(sheet, land, s.use_margins)
        for cols, rows in grids:
            cw = (area[2] - gap * (cols - 1)) / cols
            ch = (area[3] - gap * (rows - 1)) / rows
            if cw <= 0 or ch <= 0:
                continue
            w, h = pw, ph
            rotated = s.autorotate and (w > h) != (cw > ch) and abs(w - h) > 1
            if rotated:
                w, h = h, w
            sc = min(cw / w, ch / h)
            # the largest scale wins; on a tie: prefer no rotation
            score = (round(sc, 3), not rotated)
            if best is None or score > best[0]:
                best = (score, land, cols, rows)
    if best is None:
        raise ValueError(tr("Raster passt nicht auf das Blatt (Abstand zu groß?)"))
    return best[1], best[2], best[3]


MAX_PER_SHEET = 400  # guard: more copies/tiles per sheet are practically never wanted
MAX_SHEETS = 2000  # safeguard: more output sheets per job (poster) likewise
MARK_OFFSET = 2.0 * MM  # distance of the crop mark from the bleed
MARK_LEN = 5.0 * MM


def _reserve(s: LayoutSettings) -> float:
    """Space around the trim-size edge for the bleed area + trim marks."""
    if s.handling in ("booklet", "poster") and not s.step_repeat:
        return 0.0
    r = s.bleed_mm * MM
    if s.crop_marks:
        r += MARK_OFFSET + MARK_LEN
    return r


def _inset(area, r):
    x, y, w, h = area
    return (x + r, y + r, max(1.0, w - 2 * r), max(1.0, h - 2 * r))


def edge_scale(pw: float, ph: float, by: str, mm: float, percent: float) -> float:
    """Scale from a percentage or from "short/long edge to mm" (the other edge follows)."""
    if by == "short":
        return max(0.001, mm * MM / min(pw, ph))
    if by == "long":
        return max(0.001, mm * MM / max(pw, ph))
    return percent / 100.0


def custom_scale(pw: float, ph: float, s: LayoutSettings) -> float:
    """Custom scale ("Size" area)."""
    return edge_scale(pw, ph, s.custom_by, s.custom_mm, s.custom_percent)


def global_scale(s: LayoutSettings, pw: float, ph: float, base: float) -> float:
    """Global scaling ("How onto the sheet?") applies in EVERY print mode.
    fit = the mode's own default (base, previous behaviour), actual = original size,
    shrink = at most 100 %, custom = scale / custom size."""
    if s.mode == "actual":
        return 1.0
    if s.mode == "custom":
        return max(0.001, custom_scale(pw, ph, s))
    if s.mode == "shrink":
        return min(1.0, base)
    return base  # fit: mode default unchanged


def plan_single(sizes, pages, sheet: Sheet, s: LayoutSettings) -> list[SheetPlan]:
    """Plan one page per sheet (fit, actual size, shrink or custom scale)."""
    plans = []
    for p in pages:
        pw, ph = sizes[p]
        if s.orientation == "auto":
            land = pw > ph
        else:
            land = s.orientation == "landscape"
        LW, LH, area, printable = _area(sheet, land, s.use_margins)
        rot = 0
        if s.orientation != "auto" and s.autorotate and (pw > ph) != (LW > LH) and abs(pw - ph) > 1:
            rot = 90
            pw, ph = ph, pw
        area = _inset(area, _reserve(s))
        fit = min(area[2] / pw, area[3] / ph)
        if s.mode == "fit":
            sc, ref = fit, area
        elif s.mode == "shrink":
            sc, ref = min(1.0, fit), area
        elif s.mode == "custom":
            sc, ref = custom_scale(pw, ph, s), (0.0, 0.0, LW, LH)
        else:  # actual
            sc, ref = 1.0, (0.0, 0.0, LW, LH)
        w, h = pw * sc, ph * sc
        if s.center:
            x = ref[0] + (ref[2] - w) / 2
            y = ref[1] + (ref[3] - h) / 2
        else:  # top left in the reference area
            x, y = ref[0], ref[1] + ref[3] - h
        plan = SheetPlan(land, [Placement(p, rot, sc, x, y, w, h, None)])
        if not _fits((x, y, w, h), printable):
            plan.warnings.append(tr("Seite {0} ragt über den bedruckbaren Bereich – wird beschnitten.").format(p + 1))
        plans.append(plan)
    return plans


def plan_nup(sizes, pages, sheet: Sheet, s: LayoutSettings) -> list[SheetPlan]:
    """Plan several pages per sheet in a grid, including step and repeat."""
    if not pages:
        return []
    land, cols, rows = _pick_grid(sizes[pages[0]], sheet, s)
    LW, LH, area, printable = _area(sheet, land, s.use_margins)
    area = _inset(area, _reserve(s))
    # The step-and-repeat arrangement also applies to "several per sheet" – it OVERRIDES the
    # gap of the "several" section (multi-finishers often need fixed min/max
    # gaps): edge = edge to edge (0 mm, bleed only on the outside),
    # bleed = bleed to bleed (2 × bleed; without bleed the old gap of "several per sheet"
    # stays in effect so that nothing breaks silently),
    # gap = gap as set under "gap between copies" (at least 2 × bleed).
    if s.sr_join == "edge":
        gap = 0.0
    elif s.sr_join == "bleed" and s.bleed_mm > 0:
        gap = 2 * s.bleed_mm * MM
    elif s.sr_join == "gap":
        # The spin box is the VISIBLE white gap between the cards; the bleed
        # needs its room on every side and is added on top.
        gap = s.sr_gap_mm * MM + 2 * s.bleed_mm * MM
    else:
        gap = max(s.gap_mm * MM, 2 * s.bleed_mm * MM)
    # Step-and-repeat logic for "several per sheet": the gap ALWAYS applies to the
    # CONTENT – cells shrink to the cards, the block is centred.
    # There is no "cells fill the sheet" mode and there are no silent exceptions:
    #   edge  = cards touch (0 mm, bleed only on the outside of the block)
    #   bleed = 2 × bleed (bleeds touch, cut in the middle);
    #           without bleed the gap of the "several" section applies here
    #   gap   = spin box "gap between copies" as the VISIBLE white gap,
    #           the bleed is added on top on every side
    # EXCEPTION tile_mode "fit" (handout default): there the pages fill the
    # cells (cell logic) – otherwise "fit" would measure the pages against
    # the LARGE CELL and enlarge them more than necessary. So the
    # step-and-repeat logic applies to "actual size" and "custom size" –
    # exactly the modes used to produce multi-finisher jobs.
    join_override = s.tile_mode != "fit"
    cw = (area[2] - gap * (cols - 1)) / cols
    ch = (area[3] - gap * (rows - 1)) / rows
    per = cols * rows
    order = _cell_order(per, cols, rows, s.order)
    plans = []
    for start in range(0, len(pages), per):
        plan = SheetPlan(land)
        rcs = []  # (col, row) per placement – for shrinking the cells
        for i, p in enumerate(pages[start : start + per]):
            c, r = order[i]
            cx = area[0] + c * (cw + gap)
            cy = area[1] + area[3] - (r + 1) * ch - r * gap
            pw, ph = sizes[p]
            rot = 0
            if s.autorotate and (pw > ph) != (cw > ch) and abs(pw - ph) > 1:
                rot = 90
                pw, ph = ph, pw
            fit = min(cw / pw, ch / ph)
            if s.tile_mode == "actual":
                sc = 1.0
            elif s.tile_mode == "custom":
                sc = s.tile_percent / 100.0
            else:
                sc = fit
            sc = global_scale(s, pw, ph, sc)  # the global scale applies here too
            w, h = pw * sc, ph * sc
            x = cx + (cw - w) / 2
            y = cy + (ch - h) / 2
            if sc > fit + 1e-6:
                plan.warnings.append(tr("Seite {0} größer als Kachel – wird beschnitten.").format(p + 1))
            plan.placements.append(Placement(p, rot, sc, x, y, w, h, (cx, cy, cw, ch)))
            rcs.append((c, r))
        if join_override:
            # Shrink the cells to the content (the largest card per column/row) and
            # centre the block – the gap between the CARDS is then exactly
            # the gap that was set (edge: they really touch).
            colw = [0.0] * cols
            rowh = [0.0] * rows
            for pl, (c, r) in zip(plan.placements, rcs, strict=False):
                colw[c] = max(colw[c], pl.w)
                rowh[r] = max(rowh[r], pl.h)
            bw = sum(colw) + gap * (cols - 1)
            bh = sum(rowh) + gap * (rows - 1)
            x0 = area[0] + (area[2] - bw) / 2
            bottom0 = area[1] + (area[3] - bh) / 2
            for pl, (c, r) in zip(plan.placements, rcs, strict=False):
                cx = x0 + sum(colw[:c]) + gap * c
                cw2, ch2 = colw[c], rowh[r]
                cy = bottom0 + sum(rowh[r + 1 :]) + gap * (rows - 1 - r)
                pl.clip = (cx, cy, cw2, ch2)
                pl.x = cx + (cw2 - pl.w) / 2
                pl.y = cy + (ch2 - pl.h) / 2
        if s.sr_join == "edge" and s.bleed_mm > 0:
            # Edge to edge: bleed only on the outer edges of the block –
            # one cut in the middle separates two tiles (as in step and repeat).
            for pl in plan.placements:
                cx, cy, cw, ch = pl.clip if pl.clip else (pl.x, pl.y, pl.w, pl.h)
                pl.bleed_sides = (
                    cx <= area[0] + 0.5,
                    cy <= area[1] + 0.5,
                    cx + cw >= area[0] + area[2] - 0.5,
                    cy + ch >= area[1] + area[3] - 0.5,
                )
        if join_override and s.bleed_mm > 0:
            # The shrunken cells MUST be extended by the bleed –
            # otherwise impose() clips the mirrored edge at
            # the cell edge and the gap between the cards would stay white
            # (the bleed would be invisible). Only sides that show bleed
            # according to bleed_sides are extended: inside, the mirrors fill
            # the gap exactly (bleed to bleed: 2 × bleed, they touch; with a
            # gap: 2 × bleed filled, the spin box value stays white), outside
            # the bleed reaches into the margin reserved for it (_reserve).
            b = s.bleed_mm * MM
            for pl in plan.placements:
                sl, sb, sr_, st = pl.bleed_sides
                cx, cy, cw, ch = pl.clip
                pl.clip = (cx - b if sl else cx, cy - b if sb else cy, cw + b * (sl + sr_), ch + b * (sb + st))
        plans.append(plan)
    return plans


def booklet_order(n: int, binding: str = "left") -> list[tuple[list, list]]:
    """Page order for saddle stitching.

    Returns per sheet (front, back) as [left, right]; indices >= n are blank pages.
    Example 8 pages, binding on the left: sheet 1 front [8,1] back [2,7], sheet 2 front [6,3] back [4,5].
    """
    N = max(4, -(-n // 4) * 4)
    out = []
    for i in range(N // 4):
        front = [N - 1 - 2 * i, 2 * i]
        back = [2 * i + 1, N - 2 - 2 * i]
        if binding == "right":
            front.reverse()
            back.reverse()
        out.append((front, back))
    return out


def booklet_sequence(n: int, blanks: str = "end") -> list[int | None]:
    """Logical page sequence padded to a multiple of 4 (None = blank page).

    blanks="before_back": blank pages before the last page (the cover back stays at the end).
    """
    N = max(4, -(-n // 4) * 4)
    seq = list(range(n))
    fill = [None] * (N - n)
    if blanks == "before_back" and n >= 2:
        return seq[:-1] + fill + seq[-1:]
    return seq + fill


def signatures(N: int, kind: str = "saddle", per_sig: int = 4) -> list[list[int]]:
    """Split positions 0..N-1 (N a multiple of 4) into signatures; one list of positions per signature."""
    if kind == "stack":
        size = 4
    elif kind == "grouped":
        size = 4 * max(1, int(per_sig))
    else:
        size = N
    return [list(range(a, min(a + size, N))) for a in range(0, N, size)]


def signature_sheets(sig: list[int], binding: str = "left") -> list[tuple[list, list]]:
    """One signature (nested sheets) -> per sheet (front [left, right], back [left, right]).

    Sheet 0 is the outer one. Binding on the left: front [last, first], back [second, second-to-last].
    """
    k = len(sig) // 4
    out = []
    for j in range(k):
        front = [sig[4 * k - 1 - 2 * j], sig[2 * j]]
        back = [sig[2 * j + 1], sig[4 * k - 2 - 2 * j]]
        if binding == "right":
            front.reverse()
            back.reverse()
        out.append((front, back))
    return out


def booklet_layout(n: int, s: LayoutSettings):
    """All sheets: list of (signature, sheet_in_signature, sheets_in_signature, (front, back)) with values
    from booklet_sequence (page index in `pages` or None = blank page).
    """
    seq = booklet_sequence(n, s.booklet_blanks)
    sigs = signatures(len(seq), s.booklet_kind, s.booklet_per_sig)
    out = []
    for li, sig in enumerate(sigs):
        sh = signature_sheets(sig, s.booklet_binding)
        for j, (front, back) in enumerate(sh):
            out.append((li, j, len(sh), ([seq[i] for i in front], [seq[i] for i in back])))
    return out, len(seq) - n, len(sigs)


def _circle(cx, cy, r):
    """Circle as four Bézier arcs: ("bezier", start point, [(c1, c2, p), …])."""
    k = 0.5523 * r
    pts = [
        ((cx + r, cy + k), (cx + k, cy + r), (cx, cy + r)),
        ((cx - k, cy + r), (cx - r, cy + k), (cx - r, cy)),
        ((cx - r, cy - k), (cx - k, cy - r), (cx, cy - r)),
        ((cx + k, cy - r), (cx + r, cy - k), (cx + r, cy)),
    ]
    return ("bezier", (cx + r, cy), pts)


def _reg_mark(marks, x, y, r=2.5 * MM):
    """Register mark: circle with cross hairs."""
    marks.append(_circle(x, y, r))
    marks.append(("line", x - 1.6 * r, y, x + 1.6 * r, y, False))
    marks.append(("line", x, y - 1.6 * r, x, y + 1.6 * r, False))


def plan_booklet(sizes, pages, sheet: Sheet, s: LayoutSettings) -> list[SheetPlan]:
    """Plan a booklet: page pairs in imposition order, with creep and optional fold and register marks."""
    if not pages:
        return []
    pw0, ph0 = sizes[pages[0]]
    land = ph0 >= pw0  # portrait pages -> landscape sheet, fold vertical
    LW, LH, area, printable = _area(sheet, land, s.use_margins)
    if s.booklet_fold_marks or s.booklet_reg_marks:
        # keep the margin free for the marks (fold marks 5 mm, registration marks at 4 mm) – only where missing
        need = 8 * MM
        ax0, ay0, aw0, ah0 = area
        left, b = max(ax0, need), max(ay0, need)
        r, t = min(ax0 + aw0, LW - need), min(ay0 + ah0, LH - need)
        area = (left, b, r - left, t - b)
    g = s.booklet_gutter_mm * MM / 2
    ax, ay, aw, ah = area
    if land:  # left | right, fold at LW/2
        cells = [(ax, ay, LW / 2 - g - ax, ah), (LW / 2 + g, ay, ax + aw - LW / 2 - g, ah)]
        inner = ["right", "left"]  # edge towards the fold
    else:  # top | bottom (landscape pages), fold at LH/2
        cells = [(ax, LH / 2 + g, aw, ay + ah - LH / 2 - g), (ax, ay, aw, LH / 2 - g - ay)]
        inner = ["bottom", "top"]
    if min(c[2] for c in cells) <= 0 or min(c[3] for c in cells) <= 0:
        raise ValueError(tr("Bundsteg zu groß für das Papier"))

    sheets_, blanks, n_sigs = booklet_layout(len(pages), s)
    n_bogen = len(sheets_)
    chosen = parse_ranges(s.booklet_sheets, n_bogen) if s.booklet_sheets.strip() else range(n_bogen)
    sides = {"both": (0, 1), "front": (0,), "back": (1,)}.get(s.booklet_sides, (0, 1))
    creep = max(0.0, s.booklet_creep_mm) * MM
    multi = n_sigs > 1

    plans = []
    for b in chosen:
        li, j, k, faces = sheets_[b]
        shift = creep * j  # inner sheets further toward the fold (creep)
        for side in sides:
            what = tr("Vorderseite") if side == 0 else tr("Rückseite")
            if multi:
                lab = tr("Lage {0}/{1} · Bogen {2}/{3} – {4}").format(li + 1, n_sigs, j + 1, k, what)
            else:
                lab = tr("Bogen {0}/{1} – {2}").format(b + 1, n_bogen, what)
            sp = SheetPlan(land, label=lab, duplex_short=(s.booklet_sides == "both"))
            for slot, idx in enumerate(faces[side]):
                cx, cy, cw, ch = cells[slot]
                if idx is None:  # blank page
                    if s.booklet_blank_text.strip():
                        sp.marks.append(
                            (
                                "text",
                                cx + cw / 2 - len(s.booklet_blank_text) * 2.2,
                                cy + ch / 2,
                                8,
                                s.booklet_blank_text.strip(),
                            )
                        )
                    continue
                p = pages[idx]
                pw, ph = sizes[p]
                rot = 0
                if s.autorotate and (pw > ph) != (cw > ch) and abs(pw - ph) > 1:
                    rot, pw, ph = 90, ph, pw
                sc = min(cw / pw, ch / ph)
                sc = global_scale(s, pw, ph, sc)  # the global scale applies to booklets too
                w, h = pw * sc, ph * sc
                x, y = cx + (cw - w) / 2, cy + (ch - h) / 2
                # move toward the fold (+ creep: beyond the fold, trimmed at the cell)
                if inner[slot] == "right":
                    x = cx + cw - w + shift
                elif inner[slot] == "left":
                    x = cx - shift
                elif inner[slot] == "bottom":
                    y = cy - shift
                else:
                    y = cy + ch - h + shift
                sp.placements.append(Placement(p, rot, sc, x, y, w, h, (cx, cy, cw, ch)))
                if w > cw + 0.5 or h > ch + 0.5:
                    sp.warnings.append(
                        tr(
                            "Seite {0} größer als die Bogenhälfte – wird beschnitten. "
                            "Skalierung verkleinern oder größeres Papier wählen."
                        ).format(p + 1)
                    )
            _booklet_marks(sp, s, land, LW, LH, area, li, n_sigs, j, side)
            plans.append(sp)
    if blanks and plans:
        where = tr("vor der letzten Seite") if s.booklet_blanks == "before_back" else tr("am Ende")
        plans[0].warnings.append(
            tr("{0} Leerseite(n) {1} ergänzt (Seitenzahl auf Vielfaches von 4).").format(blanks, where)
        )
    return plans


def _booklet_marks(sp: SheetPlan, s: LayoutSettings, land: bool, LW, LH, area, li, n_sigs, j, side):
    """Fold marks (dashed, outside the type area), registration marks, collation marks on the spine."""
    ax, ay, aw, ah = area
    L = 5 * MM
    if s.booklet_fold_marks:
        if land:
            sp.marks.append(("line", LW / 2, 0, LW / 2, L, True))
            sp.marks.append(("line", LW / 2, LH - L, LW / 2, LH, True))
        else:
            sp.marks.append(("line", 0, LH / 2, L, LH / 2, True))
            sp.marks.append(("line", LW - L, LH / 2, LW, LH / 2, True))
    if s.booklet_reg_marks:
        r = 2.5 * MM
        m = max(4 * MM, r + 1.5 * MM)
        if land:  # centred at top and bottom, next to the fold
            for y in (m, LH - m):
                _reg_mark(sp.marks, LW / 2 - 4 * r, y)
                _reg_mark(sp.marks, LW / 2 + 4 * r, y)
        else:
            for x in (m, LW - m):
                _reg_mark(sp.marks, x, LH / 2 - 4 * r)
                _reg_mark(sp.marks, x, LH / 2 + 4 * r)
    if s.booklet_collation_marks and side == 0 and j == 0 and n_sigs > 1:
        # a bar on the outside of each signature spine, offset further per signature -> staircase on the book block
        bw, bh = 3 * MM, 6 * MM
        span = (LH if land else LW) - 2 * 10 * MM - bh
        off = 10 * MM + (span * li / max(1, n_sigs - 1))
        if land:
            sp.marks.append(("rect", LW / 2 - bw / 2, LH - off - bh, bw, bh))
        else:
            sp.marks.append(("rect", off, LH / 2 - bw / 2, bh, bw))


def _poster_geometry(pw, ph, sheet: Sheet, s: LayoutSettings, land: bool):
    LW, LH, area, _ = _area(sheet, land, s.use_margins)
    ax, ay, aw, ah = area
    if s.poster_labels:
        ay, ah = ay + LABEL_H, ah - LABEL_H
    ov = s.poster_overlap_mm * MM
    sw, sh = aw - ov, ah - ov
    if sw <= 0 or sh <= 0:
        raise ValueError(tr("Überlappung größer als der bedruckbare Bereich"))
    if s.poster_mode == "sheets":
        sc = min((s.poster_cols * sw + ov) / pw, (s.poster_rows * sh + ov) / ph)
    elif s.poster_mode == "target":
        tw, th = POSTER_FORMATS.get(s.poster_target, (s.poster_target_w_mm, s.poster_target_h_mm))
        tw, th = tw * MM, th * MM
        if (pw > ph) != (tw > th):
            tw, th = th, tw
        sc = min(tw / pw, th / ph)
    else:
        sc = s.poster_percent / 100.0
    sc = global_scale(s, pw, ph, sc)  # the global scale applies to posters too
    W, H = pw * sc, ph * sc
    cols = max(1, -(-(W - ov - 0.01) // sw)) if aw < W else 1
    rows = max(1, -(-(H - ov - 0.01) // sh)) if ah < H else 1
    cols, rows = int(cols), int(rows)
    return dict(area=(ax, ay, aw, ah), ov=ov, sw=sw, sh=sh, sc=sc, W=W, H=H, cols=cols, rows=rows)


def plan_poster(sizes, pages, sheet: Sheet, s: LayoutSettings) -> list[SheetPlan]:
    """Plan a page that is tiled over several sheets, with overlap and cut marks."""
    plans = []
    for p in pages:
        pw, ph = sizes[p]
        if s.poster_large_only:
            land = pw > ph
            _, _, area, _ = _area(sheet, land, s.use_margins)
            if pw <= area[2] + 0.5 and ph <= area[3] + 0.5:
                single = LayoutSettings(
                    mode="actual",
                    center=True,
                    orientation="landscape" if land else "portrait",
                    use_margins=s.use_margins,
                )
                plans.extend(plan_single(sizes, [p], sheet, single))
                continue
        orients = [False, True] if s.orientation == "auto" else [s.orientation == "landscape"]
        best = None
        for land in orients:
            geo = _poster_geometry(pw, ph, sheet, s, land)
            # fewer sheets wins; for "number of sheets" the larger scale
            key = (
                (-geo["sc"], geo["cols"] * geo["rows"])
                if s.poster_mode == "sheets"
                else (geo["cols"] * geo["rows"], -geo["sc"])
            )
            if best is None or key < best[0]:
                best = (key, land, geo)
        _, land, geo = best
        ax, ay, aw, ah = geo["area"]
        ov, sw, sh, sc = geo["ov"], geo["sw"], geo["sh"], geo["sc"]
        cols, rows = geo["cols"], geo["rows"]
        if len(plans) + cols * rows > MAX_SHEETS:
            raise ValueError(
                tr(
                    "Das Poster ergäbe {0} Blätter pro Seite – Maßstab bzw. Zielformat prüfen (Grenze {1} Blätter)."
                ).format(cols * rows, MAX_SHEETS)
            )
        TW, TH = cols * sw + ov, rows * sh + ov
        px, py = (TW - geo["W"]) / 2, (TH - geo["H"]) / 2
        rot_w, rot_h = geo["W"], geo["H"]
        for r in range(rows):
            for c in range(cols):
                x = ax + px - c * sw
                y = ay + py - (TH - r * sh - ah)
                sp = SheetPlan(
                    land,
                    label=tr("Seite {0} – Kachel Zeile {1}/{2}, Spalte {3}/{4}").format(
                        p + 1, r + 1, rows, c + 1, cols
                    ),
                )
                sp.placements.append(Placement(p, 0, sc, x, y, rot_w, rot_h, (ax, ay, aw, ah)))
                if s.poster_marks and ov > 0:
                    if c > 0:  # cut here and glue onto the overlap strip on the left
                        sp.marks.append(("line", ax + ov, ay, ax + ov, ay + ah, True))
                    if r > 0:
                        sp.marks.append(("line", ax, ay + ah - ov, ax + aw, ay + ah - ov, True))
                if s.poster_labels:
                    sp.marks.append(
                        (
                            "text",
                            ax,
                            ay - LABEL_H + 2,
                            7.0,
                            f"Seite {p + 1}  ·  Zeile {r + 1}/{rows}  ·  Spalte {c + 1}/{cols}  ·  "
                            f"{sc * 100:.0f} %  ·  {geo['W'] / MM:.0f} × {geo['H'] / MM:.0f} mm",
                        )
                    )
                plans.append(sp)
    return plans


def _over_rank(over: float) -> float:
    """Overhang for comparing: rounded to whole mm (fractions do not decide about rotation),
    negative – less overhang is better. If everything fits (≤ 0.5 pt) it does not count.
    """
    return 0.0 if over <= 0.5 else -round(over / MM)


def _sr_gap(s: LayoutSettings) -> float:
    bleed = s.bleed_mm * MM
    if s.sr_join == "edge":
        return 0.0  # edge to edge: one shared cut
    if s.sr_join == "bleed":
        return 2 * bleed  # bleed to bleed
    # "with gap": spin box = visible white gap; the bleed is added
    return s.sr_gap_mm * MM + 2 * bleed


def plan_step_repeat(sizes, pages, sheet: Sheet, s: LayoutSettings) -> list[SheetPlan]:
    """Step & repeat: each page as often as possible (or in a grid) onto its own sheet."""
    plans = []
    gap = _sr_gap(s)
    orients = {"portrait": [False], "landscape": [True]}.get(s.sr_orientation, [False, True])
    rots = {"0": [0], "90": [90]}.get(s.sr_rotate, [0, 90])
    if s.sr_sequence and pages:
        # determine the grid from the first page, then place the next page per tile
        import dataclasses

        proto = plan_step_repeat(sizes, pages[:1], sheet, dataclasses.replace(s, sr_sequence=False))
        if not proto:
            return []
        cells = proto[0].placements
        n = len(cells)
        n_sheets = -(-len(pages) // n)
        for k in range(n_sheets):
            sp = SheetPlan(
                proto[0].landscape,
                warnings=list(proto[0].warnings) if k == 0 else [],
                label=tr("Bogen {0}/{1} – {2} Nutzen, je Nutzen eine eigene Seite").format(k + 1, n_sheets, n),
            )
            for j, cell in enumerate(cells):
                idx = j * n_sheets + k if s.sr_stack == "stack" else k * n + j
                if idx >= len(pages):
                    continue
                p = pages[idx]
                pw0, ph0 = sizes[p]
                pw, ph = (ph0, pw0) if cell.rot else (pw0, ph0)
                sc = min(cell.w / pw, cell.h / ph) if pw and ph else cell.scale
                w, h = pw * sc, ph * sc
                pl = Placement(p, cell.rot, sc, cell.x + (cell.w - w) / 2, cell.y + (cell.h - h) / 2, w, h, None)
                pl.bleed_sides = cell.bleed_sides
                pl.trim_show_edge = cell.trim_show_edge
                sp.placements.append(pl)
            plans.append(sp)
        return plans
    for p in pages:
        pw0, ph0 = sizes[p]
        sc = edge_scale(pw0, ph0, s.sr_by, s.sr_mm, s.sr_percent)  # per page (the edge measure applies per tile)
        sc = global_scale(s, pw0, ph0, sc)  # the global scale applies to step and repeat too
        best = None
        for land in orients:
            _, _, area, printable = _area(sheet, land, s.use_margins)
            # leave room outside for the bleed area + trim marks -> area for the trim sizes
            ax, ay, aw, ah = _inset(area, _reserve(s))
            for rot in rots:
                w, h = (ph0 * sc, pw0 * sc) if rot else (pw0 * sc, ph0 * sc)
                if s.sr_mode == "grid":
                    cols, rows = s.sr_cols, s.sr_rows
                else:
                    cols = int((aw + gap + 0.01) // (w + gap))
                    rows = int((ah + gap + 0.01) // (h + gap))
                if cols < 1 or rows < 1:
                    continue
                bw, bh = cols * w + (cols - 1) * gap, rows * h + (rows - 1) * gap
                over = max(bw - aw, bh - ah, 0.0)
                # fits > (does not fit: smaller overhang) > UNROTATED > more copies > less overhang >
                # sheet upright. Copies are never rotated so that MORE fit – instead the sheet
                # rotates (the content arrives head-up at the printer). Rotation happens when nothing fits
                # unrotated in ANY sheet orientation – and also when nothing fits completely but rotated
                # overhangs clearly less (grid 2 × 4 with bleed: portrait data like landscape data).
                key = (over <= 0.5, _over_rank(over), rot == 0, cols * rows, -over, not land)
                if best is None or key > best[0]:
                    best = (key, land, rot, cols, rows, (ax, ay, aw, ah), w, h, bw, bh)
        if best is None:  # does not fit even once -> 1 copy, clipped: orientation with the smallest overhang
            for land in orients:
                _, _, area, _ = _area(sheet, land, s.use_margins)
                for rot in rots:
                    w, h = (ph0 * sc, pw0 * sc) if rot else (pw0 * sc, ph0 * sc)
                    over = max(w - area[2], h - area[3], 0.0)
                    key = (_over_rank(over), rot == 0, land == (pw0 > ph0))
                    if best is None or key > best[0]:
                        best = (key, land, rot, 1, 1, area, w, h, w, h)
        _, land, rot, cols, rows, (ax, ay, aw, ah), w, h, bw, bh = best
        n = cols * rows
        if n > MAX_PER_SHEET:
            raise ValueError(
                tr(
                    "{0} Nutzen pro Blatt ({1:.1f} × {2:.1f} mm) – das ist sicher nicht gewollt (Grenze {3}). Nutzengröße bzw. Maßstab größer wählen."
                ).format(n, w / MM, h / MM, MAX_PER_SHEET)
            )
        x0, y0 = ax + (aw - bw) / 2, ay + (ah - bh) / 2
        sp = SheetPlan(
            land,
            label=tr("Seite {0} – {1} Nutzen ({2} × {3}), Blatt {4}{5}").format(
                p + 1, n, cols, rows, tr("quer") if land else tr("hoch"), tr(", Nutzen gedreht") if rot else ""
            ),
        )
        for r in range(rows):
            for c in range(cols):
                x = x0 + c * (w + gap)
                y = y0 + bh - (r + 1) * h - r * gap
                pl = Placement(p, rot, sc, x, y, w, h, None)
                if s.sr_join == "edge":  # bleed area only on the outer edges of the block
                    pl.bleed_sides = (c == 0, r == rows - 1, c == cols - 1, r == 0)
                # outer sides of the block: show up to the real document edge
                # (crop marks that exist in the document are thus used unchanged)
                pl.trim_show_edge = (c == 0, r == rows - 1, c == cols - 1, r == 0)
                sp.placements.append(pl)
        if bw > aw + 0.5 or bh > ah + 0.5:
            sp.warnings.append(
                tr(
                    "Seite {0}: {1} × {2} passt nicht aufs Blatt – wird beschnitten. Blatt drehen, Nutzen drehen oder Maßstab verkleinern."
                ).format(p + 1, cols, rows)
            )
        plans.append(sp)
    return plans


def _crop_marks(sp: SheetPlan, bleed: float):
    """Trim marks outside around the block of all tiles, extended at every cut edge."""
    if not sp.placements:
        return
    xs = sorted({round(v, 2) for pl in sp.placements for v in (pl.x, pl.x + pl.w)})
    ys = sorted({round(v, 2) for pl in sp.placements for v in (pl.y, pl.y + pl.h)})
    X0, X1, Y0, Y1 = xs[0], xs[-1], ys[0], ys[-1]
    o = bleed + MARK_OFFSET
    for x in xs:
        sp.marks.append(("line", x, Y1 + o, x, Y1 + o + MARK_LEN, False))
        sp.marks.append(("line", x, Y0 - o, x, Y0 - o - MARK_LEN, False))
    for y in ys:
        sp.marks.append(("line", X0 - o, y, X0 - o - MARK_LEN, y, False))
        sp.marks.append(("line", X1 + o, y, X1 + o + MARK_LEN, y, False))


STRETCH_BAND_MM = 1.0  # stretched bleed: this strip inside the page edge is pulled outward (as bleedgen)


def _apply_extras(plans, s: LayoutSettings):
    special = s.handling in ("booklet", "poster") and not s.step_repeat
    bleed = 0.0 if special else s.bleed_mm * MM
    for sp in plans:
        for pl in sp.placements:
            pl.bleed = bleed
            pl.mirror_h, pl.mirror_v = s.mirror_h, s.mirror_v
            pl.bleed_mode = s.bleed_mode
            pl.bleed_fill = s.bleed_fill
        if s.crop_marks and not special:
            _crop_marks(sp, bleed)
    return plans


def uses_trim(s: LayoutSettings) -> bool:
    """Use the trim size (TrimBox) instead of the whole page: for imposition in post-processing."""
    return bool(s.step_repeat or s.handling == "booklet" or s.crop_marks or s.bleed_mm > 0 or s.borderless)


# --------------------------------------------------------------------------- #
# step 2: the imposed sheet is placed on a target size once more
# --------------------------------------------------------------------------- #
def is_step2(s: LayoutSettings) -> bool:
    """Step 2 active: step and repeat active, step 2 ticked and a target size present."""
    return bool(s.step_repeat and s.sr_pass2 and s.sr2_w_mm > 0 and s.sr2_h_mm > 0)


def step2_sheet(s: LayoutSettings) -> Sheet:
    """Target size of the second pass – physical, without a printable area."""
    return Sheet(s.sr2_w_mm * MM, s.sr2_h_mm * MM, None)


def plan_step2(tile_size, n_sheets: int, s: LayoutSettings, target: Sheet | None = None):
    """Step 2 plans: place the imposed step 1 sheets on the target size once more.

    Every step 1 sheet is placed as often as possible (or in the grid that was set)
    on its own step 2 sheet – edge to edge, unchanged
    (100 %, never additional bleed/crop marks). The grid block is
    always centred, even if it overhangs (symmetrically). There is no silent fallback
    as in plan_step_repeat: if the sheet does not fit the target size (even rotated),
    it is imposed anyway and a clear warning is written into the plan –
    that may well be intended. Rotation/orientation follow the
    step 1 settings (auto = try both variants).
    """
    tw, th = tile_size
    target = target or step2_sheet(s)
    n_sheets = max(1, int(n_sheets))
    gap = 0.0  # edge to edge
    orients = {"portrait": [False], "landscape": [True]}.get(s.sr_orientation, [False, True])
    rots = {"0": [0], "90": [90]}.get(s.sr_rotate, [0, 90])
    best = None
    for land in orients:
        _, _, area, _ = _area(
            target, land, False
        )  # target size: plan without margins (not a printer sheet but a cutting size)
        ax, ay, aw, ah = area
        for rot in rots:
            w, h = (th, tw) if rot else (tw, th)
            if s.sr2_cols > 0 and s.sr2_rows > 0:
                cols, rows = s.sr2_cols, s.sr2_rows  # grid as set
            else:
                cols = int((aw + gap + 0.01) // (w + gap))  # automatic: as many as fit
                rows = int((ah + gap + 0.01) // (h + gap))
            cols, rows = max(1, cols), max(1, rows)  # never 0: at least 1, with a warning
            bw, bh = cols * w + (cols - 1) * gap, rows * h + (rows - 1) * gap
            over = max(bw - aw, bh - ah, 0.0)
            # fits > (does not fit: smaller overhang) > UNROTATED > more sheets > less overhang >
            # target size upright (rotate the sheet as rarely as possible – same principle as for the copies)
            key = (over <= 0.5, _over_rank(over), rot == 0, cols * rows, -over, not land)
            if best is None or key > best[0]:
                best = (key, land, rot, cols, rows, (ax, ay, aw, ah), w, h, bw, bh)
    _, land, rot, cols, rows, (ax, ay, aw, ah), w, h, bw, bh = best
    n = cols * rows
    if n > MAX_PER_SHEET:
        raise ValueError(
            tr("{0} Bögen pro Zielformat – das ist sicher nicht gewollt (Grenze {1}). Zielformat vergrößern.").format(
                n, MAX_PER_SHEET
            )
        )
    x0, y0 = ax + (aw - bw) / 2, ay + (ah - bh) / 2  # grid block always centred
    plans = []
    for p in range(n_sheets):
        sp = SheetPlan(
            land,
            label=tr("Schritt-2-Bogen {0}/{1} – {2} × {3} montiert{4}{5}").format(
                p + 1,
                n_sheets,
                cols,
                rows,
                tr(", Bogen gedreht") if rot else "",
                tr(", Zielformat quer") if land else "",
            ),
        )
        for r in range(rows):
            for c in range(cols):
                x = x0 + c * (w + gap)
                y = y0 + bh - (r + 1) * h - r * gap
                sp.placements.append(Placement(p, rot, 1.0, x, y, w, h, None))
        if bw > aw + 0.5 or bh > ah + 0.5:
            sp.warnings.append(
                tr(
                    "Schritt 2: Der montierte Bogen ({0:.0f} × {1:.0f} mm) samt Raster "
                    "{2} × {3} passt nicht aufs Zielformat ({4:.0f} × {5:.0f} mm) – "
                    "am Rand wird beschnitten."
                ).format(tw / MM, th / MM, cols, rows, aw / MM, ah / MM)
            )
        plans.append(sp)
    return plans


def booklet_spreads(src, pages: list[int], s: LayoutSettings, trims=None):
    """Booklet -> document of printer's spreads (for step and repeat in the second step).

    One page per sheet side (front, back, …) in imposition order (binding type, binding edge,
    blank pages, "sheets" and "booklet pages" as in booklet mode). Every page is exactly the
    trim size of the opened booklet: two pages at the fold without a gap, side by side
    (s.booklet_spread == "side", bound at the side) or one above the other ("top", bound at the top – both
    pages upright, the earlier one on top). Bleed only on the OUTSIDE, real bleed from the document (TrimBox); at
    the fold the cut is at the trim size. Common bleed = smallest bleed of all pages; if a page has
    no trim size there is no bleed (step-and-repeat mode then creates it by mirroring).
    TrimBox/BleedBox are set – step-and-repeat mode imposes the spreads like any document page.
    No creep and no marks here – marks/bleed/gaps come from step-and-repeat mode.
    Returns (pypdfium2 document, notes).
    """
    import io

    import pikepdf
    import pypdfium2 as pdfium

    if not pages:
        raise ValueError(tr("Keine Seiten für die Broschüre."))
    if trims is None:
        trims = page_trims(src)
    notes = []
    sizes = {p: src.get_page_size(p) for p in pages}
    tr_of = {p: (trims[p] if p < len(trims) else None) for p in pages}
    if all(tr_of[p] for p in pages):
        bleed = min(min(tr_of[p]) for p in pages)
    else:
        bleed = 0.0
        if any(tr_of[p] for p in pages):
            notes.append(
                tr(
                    "Nicht alle Seiten haben ein Endformat (TrimBox) – Druckbögen ohne Anschnitt; "
                    "den Überfüller erzeugt dann der Nutzen-Modus (gespiegelt)."
                )
            )

    def trim_size(p):
        w, h = sizes[p]
        t = tr_of[p] if bleed > 0 else None
        return (w - t[0] - t[2], h - t[1] - t[3]) if t else (w, h)

    W, H = trim_size(pages[0])
    if any(abs(trim_size(p)[0] - W) > 1 or abs(trim_size(p)[1] - H) > 1 for p in pages):
        notes.append(
            tr(
                "Seiten haben unterschiedliche Endformate – jede Seite wird mittig in ihre "
                "Bogenhälfte gesetzt (Format der ersten Seite)."
            )
        )
    top = s.booklet_spread == "top"
    b = bleed
    sw, sh = (W + 2 * b, 2 * H + 2 * b) if top else (2 * W + 2 * b, H + 2 * b)
    # halves of the sheet (trim size) in slot order as in plan_booklet: side = left|right, top = top|bottom
    halves = [(b, b + H), (b, b)] if top else [(b, b), (b + W, b)]
    # bleed per half only on the outside (left, bottom, right, top)
    outer = (
        [(True, False, True, True), (True, True, True, False)]
        if top
        else [(True, True, False, True), (False, True, True, True)]
    )

    sheets_, blanks, _n = booklet_layout(len(pages), s)
    chosen = parse_ranges(s.booklet_sheets, len(sheets_)) if s.booklet_sheets.strip() else range(len(sheets_))
    sides = {"both": (0, 1), "front": (0,), "back": (1,)}.get(s.booklet_sides, (0, 1))
    plans = []
    for k in chosen:
        _li, _j, _k, faces = sheets_[k]
        for side in sides:
            sp = SheetPlan(
                False,
                label=tr("Bogen {0}/{1} – {2}").format(
                    k + 1, len(sheets_), tr("Vorderseite") if side == 0 else tr("Rückseite")
                ),
            )
            for slot, idx in enumerate(faces[side]):
                if idx is None:
                    continue  # blank page: the half stays empty
                p = pages[idx]
                pw, ph = trim_size(p)
                hx, hy = halves[slot]
                x, y = hx + (W - pw) / 2, hy + (H - ph) / 2
                t = tr_of[p] if bleed > 0 else None
                sp.placements.append(Placement(p, 0, 1.0, x, y, pw, ph, None, bleed=b, bleed_sides=outer[slot], trim=t))
            plans.append(sp)
    if blanks:
        where = tr("vor der letzten Seite") if s.booklet_blanks == "before_back" else tr("am Ende")
        notes.append(tr("{0} Leerseite(n) {1} ergänzt (Seitenzahl auf Vielfaches von 4).").format(blanks, where))
    target = Sheet(sw, sh, None)
    target.width, target.height = sw, sh  # Sheet would otherwise turn to portrait – the spread stays as it is
    doc = impose(src, target, plans)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    pdf = pikepdf.open(io.BytesIO(buf.getvalue()))
    for pg in pdf.pages:
        pg.TrimBox = [b, b, sw - b, sh - b]
        pg.BleedBox = [0, 0, sw, sh]
    out = io.BytesIO()
    pdf.save(out)
    pdf.close()
    notes.insert(
        0,
        tr(
            "Druckbögen {0:.0f} × {1:.0f} mm (Endformat), Anschnitt {2:.1f} mm außen – jetzt im "
            "Druckdialog „Nutzen“ wählen: Anordnung, Überfüller, Schnittmarken, Schritt 2."
        ).format((sw - 2 * b) / MM, (sh - 2 * b) / MM, b / MM),
    )
    return pdfium.PdfDocument(out.getvalue()), notes


def is_booklet_spreads(s: LayoutSettings) -> bool:
    """Booklet = opened printer's spreads, placed on the sheet with the step-and-repeat logic (the older
    folded-sheet path plan_booklet is kept only for the programming interface/command line).
    """
    return s.handling == "booklet"


def spread_settings(s: LayoutSettings) -> LayoutSettings:
    """Settings for imposing the spreads: step-and-repeat logic with all its options (arrangement, gap,
    bleed, crop marks, grid, step 2) – page by page.
    """
    import dataclasses

    s2 = dataclasses.replace(s, handling="size", step_repeat=True, sr_sequence=False)
    if not getattr(s, "sr_multi", False):
        # simple placement: every spread exactly ONCE, centred, original size, unrotated
        s2 = dataclasses.replace(
            s2, sr_mode="grid", sr_cols=1, sr_rows=1, sr_by="percent", sr_percent=100.0, sr_rotate="0"
        )
    return s2


def mark_spread_duplex(plans: list, s: LayoutSettings) -> list:
    """Duplex flip edge for printer's spreads: the sheet is flipped around the edge PARALLEL to the fold –
    otherwise the back is not behind the front. Side by side (fold vertical): landscape sheet -> short edge,
    portrait sheet -> long edge; one above the other (fold horizontal) the other way round.
    """
    side = s.booklet_spread != "top"
    for sp in plans:
        sp.duplex_short = (sp.landscape == side) and s.booklet_sides == "both"
    return plans


def spread_source(doc, pages: list[int], s: LayoutSettings, trims=None):
    """(document of spreads, its pages, step-and-repeat settings, notes) – input for preview and printing."""
    spreads, notes = booklet_spreads(doc, pages, s, trims)
    return spreads, list(range(len(spreads))), spread_settings(s), notes


def impose_step2(src, sheet: Sheet, plans1: list, s: LayoutSettings, plans2=None, only=None):
    """Two passes: step 1 onto the chosen sheet, the result saved flat to a temporary file
    and reloaded, then placed unchanged and centred on the target size.

    Saving in between matters: impose() embeds the tiles as form XObjects.
    If the result were nested directly as an XObject into the second pass,
    real PDFium would lose content (e.g. the crop marks of the first pass) and
    the placement would shift. After reloading, the sheet is an ordinary
    PDF page – step 2 imposes it exactly like any document page.
    """
    if plans2 is None:
        plans2 = plan_step2((sheet.width, sheet.height), len(plans1), s)
    import os
    import tempfile

    import pypdfium2 as pdfium

    mid = impose(src, sheet, plans1)
    fd, tmp = tempfile.mkstemp(prefix="passermark-sr2-", suffix=".pdf")
    os.close(fd)
    flat = None
    try:
        mid.save(tmp)
        mid.close()
        mid = None
        flat = pdfium.PdfDocument(tmp)  # reloaded: nested XObjects are resolved
        return impose(flat, step2_sheet(s), plans2, only)
    finally:
        if mid is not None:
            mid.close()
        if flat is not None:
            flat.close()
        try:
            os.unlink(tmp)
        except OSError:
            pass


def plan(sizes, pages, sheet: Sheet, s: LayoutSettings, trims=None, bleeds=None) -> list[SheetPlan]:
    """Plan the sheets. trims (from page_trims): pages with a defined trim size are set to their trim size,
    their bleed area comes from the document (not mirrored). bleeds (from page_doc_bleeds): bleed area per the
    BleedBox – with step & repeat "bleed to bleed" and no configured bleed area, it is adopted
    (e.g. CutContour objects: the bleeds touch each other).
    """
    if s.borderless:  # borderless: no printer margin, whole sheet
        import dataclasses

        s = dataclasses.replace(s, use_margins=False)
        sheet = Sheet(sheet.width, sheet.height, None)
    # without "bleed from the document" the final format always counts (bleed 0 = exactly the final format)
    if not trims or not any(trims) or not (uses_trim(s) or not s.doc_bleed):
        return _plan(sizes, pages, sheet, s)
    sz = list(sizes)
    for i, t in enumerate(trims):
        if t and i < len(sz):
            w, h = sz[i]
            sz[i] = (w - t[0] - t[2], h - t[1] - t[3])
    if s.step_repeat and s.sr_join == "bleed" and s.bleed_mm <= 0 and bleeds and any(bleeds):
        import dataclasses

        plans = []
        groups = [pages] if s.sr_sequence else [[p] for p in pages]  # continuous: one shared grid
        for grp in groups:
            p = grp[0]
            b = bleeds[p] if p < len(bleeds) and trims[p] else 0.0
            sc = edge_scale(sz[p][0], sz[p][1], s.sr_by, s.sr_mm, s.sr_percent)
            s2 = dataclasses.replace(s, bleed_mm=b * sc / MM) if b > 0 else s
            plans += _plan(sz, grp, sheet, s2)
    else:
        plans = _plan(sz, pages, sheet, s)
    for sp in plans:
        for pl in sp.placements:
            t = trims[pl.src] if pl.src < len(trims) else None
            if t:
                pl.trim = t
                b = bleeds[pl.src] if bleeds and pl.src < len(bleeds) else 0.0
                pl.own_bleed = b if b > 0 else -1.0
                if s.borderless and not s.step_repeat and s.handling != "booklet":
                    pl.trim_show_edge = (True, True, True, True)  # real bleed beyond the sheet edge
    return plans


def _plan(sizes, pages, sheet: Sheet, s: LayoutSettings) -> list[SheetPlan]:
    if s.step_repeat:
        return _apply_extras(plan_step_repeat(sizes, pages, sheet, s), s)
    if s.handling == "booklet":
        return _apply_extras(plan_booklet(sizes, pages, sheet, s), s)
    if s.handling == "poster":
        return _apply_extras(plan_poster(sizes, pages, sheet, s), s)
    return _apply_extras(plan_nup(sizes, pages, sheet, s) if s.is_nup else plan_single(sizes, pages, sheet, s), s)


# --------------------------------------------------------------------------- #
# affine matrices (a b c d e f) – x' = a x + c y + e ; y' = b x + d y + f
# --------------------------------------------------------------------------- #
def _mul(m1, m2):
    """Apply m1 first, then m2."""
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (
        a1 * a2 + b1 * c2,
        a1 * b2 + b1 * d2,
        c1 * a2 + d1 * c2,
        c1 * b2 + d1 * d2,
        e1 * a2 + f1 * c2 + e2,
        e1 * b2 + f1 * d2 + f2,
    )


def _translate(x, y):
    return (1, 0, 0, 1, x, y)


def _scale(s):
    return (s, 0, 0, s, 0, 0)


def _rot90ccw(h0):
    """Rotates the box [0,w0]x[0,h0] back into the first quadrant, 90° counterclockwise."""
    return (0, 1, -1, 0, h0, 0)


def _log2phys(sheet: Sheet, landscape: bool):
    # logical (x,y) -> physical (W - y, x)
    return (0, 1, -1, 0, sheet.width, 0) if landscape else (1, 0, 0, 1, 0, 0)


def placement_matrix(pl: Placement, src_size) -> tuple:
    """PDF transformation matrix ``(a, b, c, d, e, f)`` that puts a source page at its placement."""
    w0, h0 = src_size
    m = (1, 0, 0, 1, 0, 0)
    if pl.rot == 90:
        m = _mul(m, _rot90ccw(h0))
    m = _mul(m, _scale(pl.scale))
    return _mul(m, _translate(pl.x, pl.y))


# --------------------------------------------------------------------------- #
# create the PDF
# --------------------------------------------------------------------------- #
def impose(src, sheet: Sheet, plans: list[SheetPlan], only: list[int] | None = None, borders: bool = False):
    """Create a new pypdfium2 document. `src` is a pdfium.PdfDocument."""
    import pypdfium2 as pdfium

    out = pdfium.PdfDocument.new()
    tiles = pdfium.PdfDocument.new()  # intermediate pages for clipping the tiles
    sizes = {}

    def size(i):
        if i not in sizes:
            sizes[i] = src.get_page_size(i)
        return sizes[i]

    xobjs = {}
    tile_xobjs = {}  # identical tiles (step & repeat): one XObject in the output, placed many times

    def xobj(i, dest):
        key = (i, id(dest))
        if key not in xobjs:
            xobjs[key] = src.page_as_xobject(i, dest)
        return xobjs[key]

    for idx, sp in enumerate(plans):
        if only is not None and idx not in only:
            continue
        page = out.new_page(sheet.width, sheet.height)
        to_phys = _log2phys(sheet, sp.landscape)
        for pl in sp.placements:
            if pl.trim:
                w0, h0 = size(pl.src)
                L_, B_, R_, T_ = pl.trim
                m = _mul(_translate(-L_, -B_), placement_matrix(pl, (w0 - L_ - R_, h0 - B_ - T_)))
            else:
                m = placement_matrix(pl, size(pl.src))
            b = pl.bleed
            if pl.clip is None and b <= 0 and not pl.trim and not (pl.mirror_h or pl.mirror_v):
                obj = xobj(pl.src, out).as_pageobject()
                obj.transform(pdfium.PdfMatrix(*_mul(m, to_phys)))
                page.insert_obj(obj)
                continue
            # tile: area that should be visible (page + bleed, limited to the cell if needed)
            sl, sb, sr_, st = pl.bleed_sides
            # precompute the distance from the trim size to the real page edge (for trim_show_edge)
            eL0 = eB0 = eR0 = eT0 = 0.0
            if pl.trim:
                tL, tB, tR, tT = pl.trim
                if pl.rot == 90:
                    tL, tB, tR, tT = tT, tL, tB, tR
                eL0, eB0, eR0, eT0 = tL * pl.scale, tB * pl.scale, tR * pl.scale, tT * pl.scale
            show = pl.trim_show_edge
            # per side: the configured bleed; on the outer sides of the block additionally
            # up to the real document edge (use existing crop marks instead of cutting them off)
            # without "create missing bleed" only what the document has is shown (no mirroring/stretching)
            fill = getattr(pl, "bleed_fill", True)
            own = getattr(pl, "own_bleed", -1.0)
            lim = own * pl.scale if own >= 0 else float("inf")
            cL, cB, cR, cT = (
                (b, b, b, b) if fill else (min(b, eL0, lim), min(b, eB0, lim), min(b, eR0, lim), min(b, eT0, lim))
            )
            bL = max(cL if sl else 0.0, eL0 if show[0] else 0.0)
            bB = max(cB if sb else 0.0, eB0 if show[1] else 0.0)
            bR = max(cR if sr_ else 0.0, eR0 if show[2] else 0.0)
            bT = max(cT if st else 0.0, eT0 if show[3] else 0.0)
            bx, by = pl.x - bL, pl.y - bB
            bw, bh = pl.w + bL + bR, pl.h + bB + bT
            if pl.clip is not None:
                cx, cy, cw, ch = pl.clip
                nx, ny = max(bx, cx), max(by, cy)
                bw, bh = min(bx + bw, cx + cw) - nx, min(by + bh, cy + ch) - ny
                bx, by = nx, ny
            if bw <= 0 or bh <= 0:
                continue
            local = _mul(m, _translate(-bx, -by))
            X0, Y0 = pl.x - bx, pl.y - by
            tkey = (
                pl.src,
                tuple(round(v, 3) for v in (bw, bh, X0, Y0, pl.w, pl.h, bL, bB, bR, bT, eL0, eB0, eR0, eT0)),
                tuple(round(v, 5) for v in local),
                getattr(pl, "bleed_mode", "mirror"),
                bool(borders),
            )
            cx_obj = tile_xobjs.get(tkey)
            if cx_obj is not None:  # same tile as before (step & repeat): reuse, no copy of the page
                cell = cx_obj.as_pageobject()
                place = (1, 0, 0, 1, 0, 0)
                if pl.mirror_h:
                    place = _mul(place, (-1, 0, 0, 1, bw, 0))
                if pl.mirror_v:
                    place = _mul(place, (1, 0, 0, -1, 0, bh))
                cell.transform(pdfium.PdfMatrix(*_mul(_mul(place, _translate(bx, by)), to_phys)))
                page.insert_obj(cell)
                continue
            tpage = tiles.new_page(bw, bh)
            X1, Y1 = X0 + pl.w, Y0 + pl.h
            # bleed area from the document (TrimBox): real content up to the page edge; only what goes beyond
            # is needed is mirrored at the page edge
            eL, eB, eR, eT = eL0, eB0, eR0, eT0
            xs_ = [0] + ([-1] if sl and bL > eL + 0.05 else []) + ([1] if sr_ and bR > eR + 0.05 else [])
            ys_ = [0] + ([-1] if sb and bB > eB + 0.05 else []) + ([1] if st and bT > eT + 0.05 else [])
            # corners first, then the sides, the page itself last (on top): a stretched copy also covers the
            # inside of the page, the original hides that again
            offsets = sorted(((dx, dy) for dx in xs_ for dy in ys_), key=lambda o: -(abs(o[0]) + abs(o[1])))
            stretch = getattr(pl, "bleed_mode", "mirror") == "stretch"
            band = min(STRETCH_BAND_MM * MM * pl.scale, (X1 - X0) / 4, (Y1 - Y0) / 4)
            for dx, dy in offsets:
                mm = local
                if dx:  # mirror/stretch at the left/right edge
                    c = X0 - eL if dx < 0 else X1 + eR
                    if stretch and band > 0:
                        need = (bL - eL) if dx < 0 else (bR - eR)
                        k = (band + max(0.0, need)) / band
                        anchor = c + band if dx < 0 else c - band
                        mm = _mul(mm, (k, 0, 0, 1, anchor * (1 - k), 0))
                    else:
                        mm = _mul(mm, (-1, 0, 0, 1, 2 * c, 0))
                if dy:
                    c = Y0 - eB if dy < 0 else Y1 + eT
                    if stretch and band > 0:
                        need = (bB - eB) if dy < 0 else (bT - eT)
                        k = (band + max(0.0, need)) / band
                        anchor = c + band if dy < 0 else c - band
                        mm = _mul(mm, (1, 0, 0, k, 0, anchor * (1 - k)))
                    else:
                        mm = _mul(mm, (1, 0, 0, -1, 0, 2 * c))
                tobj = xobj(pl.src, tiles).as_pageobject()
                tobj.transform(pdfium.PdfMatrix(*mm))
                tpage.insert_obj(tobj)
            if borders:
                _add_border(tpage, X0, Y0, pl.w, pl.h, bw, bh)
            tpage.gen_content()
            tindex = len(tiles) - 1
            tpage.close()
            cx_obj = tiles.page_as_xobject(tindex, out)
            cell = cx_obj.as_pageobject()
            place = (1, 0, 0, 1, 0, 0)
            if pl.mirror_h:
                place = _mul(place, (-1, 0, 0, 1, bw, 0))
            if pl.mirror_v:
                place = _mul(place, (1, 0, 0, -1, 0, bh))
            cell.transform(pdfium.PdfMatrix(*_mul(_mul(place, _translate(bx, by)), to_phys)))
            page.insert_obj(cell)
            tile_xobjs[tkey] = cx_obj  # closed at the end – further identical tiles reuse it
        for m in sp.marks:
            _add_mark(out, page, m, to_phys)
        page.gen_content()
        page.close()
    for x in xobjs.values():
        x.close()
    for x in tile_xobjs.values():
        x.close()
    tiles.close()
    return out


def impose_with(src, sheet: Sheet, plans, settings: LayoutSettings, only=None):
    """Run :func:`impose` with the border option taken from ``settings``."""
    return impose(src, sheet, plans, only, borders=settings.borders and settings.is_nup)


def _add_border(tpage, x, y, w, h, cw, ch):
    import pypdfium2.raw as r

    lw = 0.5
    x0, y0 = max(x, 0) + lw / 2, max(y, 0) + lw / 2
    x1, y1 = min(x + w, cw) - lw / 2, min(y + h, ch) - lw / 2
    if x1 <= x0 or y1 <= y0:
        return
    path = r.FPDFPageObj_CreateNewRect(x0, y0, x1 - x0, y1 - y0)
    r.FPDFPageObj_SetStrokeColor(path, 0, 0, 0, 255)
    r.FPDFPageObj_SetStrokeWidth(path, lw)
    r.FPDFPath_SetDrawMode(path, r.FPDF_FILLMODE_NONE, True)
    r.FPDFPage_InsertObject(tpage.raw, path)


def _add_mark(doc, page, m, to_phys):
    import ctypes

    import pypdfium2.raw as r

    if m[0] == "line":
        _, x0, y0, x1, y1, dashed = m
        obj = r.FPDFPageObj_CreateNewPath(x0, y0)
        r.FPDFPath_LineTo(obj, x1, y1)
        if dashed:
            r.FPDFPageObj_SetStrokeColor(obj, 90, 90, 90, 255)
            r.FPDFPageObj_SetStrokeWidth(obj, 0.4)
        else:  # trim mark: similar to registration black, thin
            r.FPDFPageObj_SetStrokeColor(obj, 0, 0, 0, 255)
            r.FPDFPageObj_SetStrokeWidth(obj, 0.25)
        if dashed:
            arr = (ctypes.c_float * 2)(3.0, 2.0)
            r.FPDFPageObj_SetDashArray(obj, arr, 2, 0.0)
        r.FPDFPath_SetDrawMode(obj, r.FPDF_FILLMODE_NONE, True)
    elif m[0] == "bezier":
        _, (x0, y0), segs = m
        obj = r.FPDFPageObj_CreateNewPath(x0, y0)
        for c1, c2, pt in segs:
            r.FPDFPath_BezierTo(obj, c1[0], c1[1], c2[0], c2[1], pt[0], pt[1])
        r.FPDFPath_Close(obj)
        r.FPDFPageObj_SetStrokeColor(obj, 0, 0, 0, 255)
        r.FPDFPageObj_SetStrokeWidth(obj, 0.25)
        r.FPDFPath_SetDrawMode(obj, r.FPDF_FILLMODE_NONE, True)
    elif m[0] == "rect":
        _, x, y, w, h = m
        obj = r.FPDFPageObj_CreateNewRect(x, y, w, h)
        r.FPDFPageObj_SetFillColor(obj, 0, 0, 0, 255)
        r.FPDFPath_SetDrawMode(obj, r.FPDF_FILLMODE_WINDING, False)
    elif m[0] == "text":
        _, x, y, size, text = m
        obj = r.FPDFPageObj_NewTextObj(doc.raw, b"Helvetica", float(size))
        buf = ctypes.create_string_buffer((text + "\0").encode("utf-16-le"))
        r.FPDFText_SetText(obj, ctypes.cast(buf, r.FPDF_WIDESTRING))
        r.FPDFPageObj_SetFillColor(obj, 60, 60, 60, 255)
        r.FPDFPageObj_Transform(obj, 1, 0, 0, 1, x, y)
    else:
        return
    r.FPDFPageObj_Transform(obj, *to_phys)
    r.FPDFPage_InsertObject(page.raw, obj)


def page_trims(doc) -> list:
    """Per page the trim size (TrimBox) as the distance to the visible page edge in reading direction:
    (left, bottom, right, top) in pt, or None if no bleed is defined.
    """
    out = []
    for i in range(len(doc)):
        pg = doc[i]
        try:
            crop = pg.get_cropbox()
            trim = pg.get_trimbox(fallback_ok=False) if _has_box(pg, "TrimBox") else None
            if trim is None and _has_box(pg, "ArtBox"):
                trim = pg.get_artbox(fallback_ok=False)
            rot = pg.get_rotation() % 360
        finally:
            pg.close()
        if trim is None:
            out.append(None)
            continue
        cl, cb, cr, ct = crop
        tl, tb, tr_, tt = (max(trim[0], cl), max(trim[1], cb), min(trim[2], cr), min(trim[3], ct))
        o = (tl - cl, tb - cb, cr - tr_, ct - tt)  # unrotated: left, bottom, right, top
        if rot == 90:  # clockwise: bottom -> left, right -> bottom, top -> right, left -> top
            o = (o[1], o[2], o[3], o[0])
        elif rot == 180:
            o = (o[2], o[3], o[0], o[1])
        elif rot == 270:
            o = (o[3], o[0], o[1], o[2])
        out.append(o if max(o) > 0.5 and min(o) >= 0 and (tr_ - tl) > 10 and (tt - tb) > 10 else None)
    return out


def trims_from_info(info: list) -> list:
    """Like page_trims, but from renderproc.page_info (pikepdf, without loading a page)."""
    out = []
    for pi in info:
        crop, rot = pi["crop"], (pi.get("rotate", 0) * 90) % 360
        trim = pi.get("trim_raw") or pi.get("art")
        if trim is None:
            out.append(None)
            continue
        cl, cb, cr, ct = crop
        tl, tb, tr_, tt = (max(trim[0], cl), max(trim[1], cb), min(trim[2], cr), min(trim[3], ct))
        o = (tl - cl, tb - cb, cr - tr_, ct - tt)
        if rot == 90:
            o = (o[1], o[2], o[3], o[0])
        elif rot == 180:
            o = (o[2], o[3], o[0], o[1])
        elif rot == 270:
            o = (o[3], o[0], o[1], o[2])
        out.append(o if max(o) > 0.5 and min(o) >= 0 and (tr_ - tl) > 10 and (tt - tb) > 10 else None)
    return out


def available_bleeds(trims: list, doc_bleeds: list, n: int) -> list:
    """Bleed per page in mm that the file has around its final format (BleedBox, otherwise the visible page
    beyond the TrimBox); None for pages without a final format in the file."""
    out = []
    for i in range(n):
        t = trims[i] if i < len(trims) else None
        if not t:
            out.append(None)
            continue
        b = doc_bleeds[i] if i < len(doc_bleeds) else 0.0
        out.append((min(b, min(t)) if b > 0 else min(t)) / MM)
    return out


def doc_bleeds_from_info(info: list) -> list:
    """Like page_doc_bleeds, from renderproc.page_info."""
    out = []
    for pi in info:
        trim, bleed = pi.get("trim"), pi.get("bleed")
        if trim is None or bleed is None:
            out.append(0.0)
            continue
        d = min(trim[0] - bleed[0], trim[1] - bleed[1], bleed[2] - trim[2], bleed[3] - trim[3])
        out.append(max(0.0, d))
    return out


def _has_box(pg, name: str) -> bool:
    import ctypes

    import pypdfium2.raw as r

    f = {"TrimBox": r.FPDFPage_GetTrimBox, "ArtBox": r.FPDFPage_GetArtBox, "BleedBox": r.FPDFPage_GetBleedBox}[name]
    v = [ctypes.c_float() for _ in range(4)]
    return bool(f(pg.raw, *[ctypes.byref(x) for x in v]))


def page_boxes(doc) -> list:
    """Per page (TrimBox, BleedBox) in PDF coordinates (unrotated) – None where undefined. For display."""
    out = []
    for i in range(len(doc)):
        pg = doc[i]
        try:
            trim = pg.get_trimbox(fallback_ok=False) if _has_box(pg, "TrimBox") else None
            bleed = pg.get_bleedbox(fallback_ok=False) if _has_box(pg, "BleedBox") else None
            media = pg.get_cropbox()
        finally:
            pg.close()
        if (
            trim is not None
            and abs(trim[0] - media[0]) < 0.5
            and abs(trim[1] - media[1]) < 0.5
            and abs(trim[2] - media[2]) < 0.5
            and abs(trim[3] - media[3]) < 0.5
        ):
            trim = None  # trim size = page: no bleed
        if bleed is not None and trim is None:
            bleed = None
        out.append((trim, bleed))
    return out


def page_doc_bleeds(doc) -> list:
    """Per page the bleed from the BleedBox around the TrimBox (smallest margin, pt) – 0 where none is defined."""
    out = []
    for trim, bleed in page_boxes(doc):
        if trim is None or bleed is None:
            out.append(0.0)
            continue
        d = min(trim[0] - bleed[0], trim[1] - bleed[1], bleed[2] - trim[2], bleed[3] - trim[3])
        out.append(max(0.0, d))
    return out


def trim_info(doc, i: int):
    """(trim-size width and height in mm in reading direction, bleed area in mm (smallest margin)) or None."""
    t = page_trims_one(doc, i)
    if not t:
        return None
    w, h = doc.get_page_size(i)
    return ((w - t[0] - t[2]) / MM, (h - t[1] - t[3]) / MM, min(t) / MM)


def page_trims_one(doc, i: int):
    """Like :func:`page_trims`, but for the single page ``i`` only."""

    class _One:
        def __len__(self):
            return 1

        def __getitem__(self, _k):
            return doc[i]

    return page_trims(_One())[0]


def flattened(doc):
    """Copy with form values, comments and stamps burned in (like printing from Acrobat).

    Imposition only carries over the page content – annotations (filled form fields,
    comments, stamps) would otherwise not end up on the sheet. Only annotations the PDF says
    should be printed are included (FLAT_PRINT). Without annotations, the original is
    returned unchanged.
    """
    import io

    import pypdfium2 as pdfium
    import pypdfium2.raw as r

    has = False
    for i in range(len(doc)):
        pg = doc[i]
        n = r.FPDFPage_GetAnnotCount(pg.raw)
        pg.close()
        if n:
            has = True
            break
    if not has:
        return doc
    buf = io.BytesIO()
    doc.save(buf)
    cp = pdfium.PdfDocument(buf.getvalue())
    try:
        cp.init_forms()  # creates missing field appearances
    except Exception:
        log.warning("Formularfelder ohne Darstellung", exc_info=True)
    for i in range(len(cp)):
        pg = cp[i]
        if r.FPDFPage_GetAnnotCount(pg.raw):
            r.FPDFPage_Flatten(pg.raw, r.FLAT_PRINT)
        pg.close()
    out = io.BytesIO()
    cp.save(out)
    cp.close()
    return pdfium.PdfDocument(out.getvalue())


def build_pdf(src, sheet: Sheet, pages: list[int], settings: LayoutSettings, path: str):
    """Plan and impose ``pages`` of ``src`` onto ``sheet`` and save the result to ``path``; returns the sheet plans."""
    sizes = [src.get_page_size(i) for i in range(len(src))]
    plans = plan(sizes, pages, sheet, settings, page_trims(src), page_doc_bleeds(src))
    doc = impose_with(src, sheet, plans, settings)
    doc.save(path)
    doc.close()
    return plans
