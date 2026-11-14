# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""View modes of the document view: how the pages are arranged in the scroll area.

PageView (gui/pageview.py) keeps the document, the zoom and the page widgets; a view mode only decides where the
pages go. Every mode has the same interface, so that a new mode is one more class here:

- ``place(view, dpi)``: size and position the page widgets and the container for the current zoom
- ``fit_area(view, i)``: the space page ``i`` is fitted into for "fit width" / "fit page"
- ``goto(view, i, at_end, force)``: bring page ``i`` into view
- ``page_at_scroll(view)``: which page the view is on after scrolling (None = unchanged)
- ``step(view, i, direction)``: the page "next/previous page" goes to (facing pages: the next spread)
- ``shows_one_page``: only the current page is in the scroll area
- ``pages_at_edge``: the mouse wheel and the arrow keys at the edge of a page go on to the next one
"""

from __future__ import annotations

PAGE_GAP = 22  # space between the pages and around them, in pixels
ZOOM_STEPS = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0, 6.4]  # choices of the zoom box


class ViewMode:
    """Interface of a view mode (see the module description)."""

    name = ""
    shows_one_page = False
    pages_at_edge = False

    def place(self, view, dpi: float):
        """Size and position the page widgets and the container for the current zoom."""
        raise NotImplementedError

    def fit_area(self, view, i: int) -> tuple[int, int]:
        """Width and height available for page i: the window minus the gaps."""
        vw = max(50, view.viewport().width() - 2 * PAGE_GAP - 4)
        vh = max(50, view.viewport().height() - 2 * PAGE_GAP)
        return vw, vh

    def goto(self, view, i: int, at_end: bool, force: bool):
        """Bring page i into view (at its end with at_end; force: lay out again even if it is shown)."""
        raise NotImplementedError

    def page_at_scroll(self, view) -> int | None:
        """The page the view is on after scrolling; None = unchanged."""
        return None

    def step(self, view, i: int, direction: int) -> int:
        """The page "next" (direction 1) or "previous" (-1) goes to from page i."""
        return i + direction

    def spec(self) -> dict:
        """The mode as plain values (for remembering it, see make())."""
        return {"mode": self.name}


class SinglePage(ViewMode):
    """Always exactly one page, centred. Inside the page it scrolls; at its edge the view goes to the next page."""

    name = "single"
    shows_one_page = True
    pages_at_edge = True

    def place(self, view, dpi: float):
        """Hide all pages but the current one and centre it."""
        vw, vh = view.viewport().width(), view.viewport().height()
        for w in view.pages:
            if w.index != view.current:
                w.hide()
        w = view.pages[view.current]
        s = view.page_zoom(view.current) * dpi
        pw, ph = view._rot_size(view.current)
        ww, hh = int(pw * s), int(ph * s)
        cw, ch = max(ww + 2 * PAGE_GAP, vw), max(hh + 2 * PAGE_GAP, vh)
        w.setGeometry((cw - ww) // 2, max(PAGE_GAP, (ch - hh) // 2), ww, hh)
        view._rotate_master(w)
        w.show()
        view.container.resize(cw, ch)

    def goto(self, view, i: int, at_end: bool, force: bool):
        """Show page i alone, scrolled to its top (or its end)."""
        vb = view.verticalScrollBar()
        if i != view.current or force:
            view.current = i
            view.relayout()
        vb.setValue(vb.maximum() if at_end else 0)


class Continuous(ViewMode):
    """All pages one below the other."""

    name = "continuous"

    def place(self, view, dpi: float):
        """All pages below each other, centred horizontally."""
        vw = view.viewport().width()
        view.viewport().height()  # (asked for as before – keeps the order of the calls)
        geo = []
        for i in range(len(view.sizes)):
            s = view.page_zoom(i) * dpi
            pw, ph = view._rot_size(i)
            geo.append((int(pw * s), int(ph * s), s))
        cw = max((max(g[0] for g in geo) if geo else 0) + 2 * PAGE_GAP, vw)
        y = PAGE_GAP
        for w, (ww, hh, _s) in zip(view.pages, geo, strict=False):
            w.setGeometry((cw - ww) // 2, y, ww, hh)
            view._rotate_master(w)
            w.show()
            y += hh + PAGE_GAP
        view.container.resize(cw, y)

    def goto(self, view, i: int, at_end: bool, force: bool):
        """Scroll so that page i is at the top."""
        vb = view.verticalScrollBar()
        view.current = i
        vb.setValue(view.pages[i].y() - PAGE_GAP)

    def page_at_scroll(self, view) -> int | None:
        """The page at a third of the window height."""
        mid = view.verticalScrollBar().value() + view.viewport().height() // 3
        for w in view.pages:
            if w.y() <= mid <= w.y() + w.height() + PAGE_GAP:
                return w.index
        return None


class _Rows(ViewMode):
    """Several pages side by side in rows, the rows one below the other (base of Facing and Grid).

    A subclass says which pages share a row (``rows``) and how wide a page may be when fitted (``fit_area``).
    Empty places in a row (``None``) keep the columns where they belong, e.g. the cover alone on the right.
    """

    gap = PAGE_GAP  # space between the pages of a row

    def __init__(self):
        self._rows: list[list[int | None]] = []  # as laid out by the last place()
        self._row_of: dict[int, int] = {}  # page -> its row

    def rows(self, n: int) -> list[list[int | None]]:
        """The pages of each row, ``None`` for an empty place."""
        raise NotImplementedError

    def _cols(self) -> int:
        return 1

    def fit_area(self, view, i: int) -> tuple[int, int]:
        """A page gets its share of the window width (fitting works per spread or per row)."""
        vw, vh = super().fit_area(view, i)
        n = self._cols()
        return max(20, (vw - (n - 1) * self.gap) // n), vh

    def place(self, view, dpi: float):
        """Lay out the rows: every column as wide as its widest page, pages centred in their place."""
        vw = view.viewport().width()
        size = {}
        for i in range(len(view.sizes)):
            s = view.page_zoom(i) * dpi
            pw, ph = view._rot_size(i)
            size[i] = (int(pw * s), int(ph * s))
        rows = self.rows(len(view.sizes))
        cols = max((len(r) for r in rows), default=1)
        colw = [max((size[r[c]][0] for r in rows if c < len(r) and r[c] is not None), default=0) for c in range(cols)]
        for c in range(cols):  # a column without any page (e.g. only the cover) as wide as its neighbours
            if not colw[c]:
                colw[c] = max(colw, default=0)
        total = sum(colw) + (cols - 1) * self.gap
        cw = max(total + 2 * PAGE_GAP, vw)
        x0 = (cw - total) // 2
        y = PAGE_GAP
        self._row_of = {}
        for k, r in enumerate(rows):
            hh = max((size[i][1] for i in r if i is not None), default=0)
            x = x0
            for c, i in enumerate(r):
                if i is not None:
                    ww, ph = size[i]
                    w = view.pages[i]
                    w.setGeometry(x + self._align(c, cols, colw[c], ww), y + (hh - ph) // 2, ww, ph)
                    view._rotate_master(w)
                    w.show()
                    self._row_of[i] = k
                x += colw[c] + self.gap
            y += hh + PAGE_GAP
        self._rows = rows
        view.container.resize(cw, y)

    def _align(self, col: int, cols: int, width: int, page_w: int) -> int:
        """Offset of a page in its column (centred; facing pages lean on the spine)."""
        return (width - page_w) // 2

    def _row_top(self, view, k: int) -> int:
        return min(view.pages[i].y() for i in self._rows[k] if i is not None)

    def goto(self, view, i: int, at_end: bool, force: bool):
        """Scroll so that the row of page i is at the top."""
        view.current = i
        k = self._row_of.get(i)
        if k is None:
            return
        view.verticalScrollBar().setValue(self._row_top(view, k) - PAGE_GAP)

    def page_at_scroll(self, view) -> int | None:
        """The row at a third of the window height; the current page if it is in it, else its first page.
        At the end of the document (the last rows cannot reach the top) a visible current page stays."""
        vb = view.verticalScrollBar()
        if vb.value() >= vb.maximum() and view.current in self._row_of:
            w = view.pages[view.current]
            if w.y() < vb.value() + view.viewport().height() and w.y() + w.height() > vb.value():
                return None
        mid = vb.value() + view.viewport().height() // 3
        for r in self._rows:
            pages = [i for i in r if i is not None]
            top = min(view.pages[i].y() for i in pages)
            bottom = max(view.pages[i].y() + view.pages[i].height() for i in pages)
            if top <= mid <= bottom + PAGE_GAP:
                return view.current if view.current in pages else pages[0]
        return None

    def step(self, view, i: int, direction: int) -> int:
        """Next/previous row: its first page."""
        rows = self._rows
        k = self._row_of.get(i)
        if not rows or k is None:
            return i + direction
        k += direction
        if not (0 <= k < len(rows)):
            return -1 if direction < 0 else len(view.pages)  # beyond the document: goto ignores it
        return next(p for p in rows[k] if p is not None)


class Facing(_Rows):
    """Facing pages (spreads) like an open book. ``cover_alone``: the first page alone on the right."""

    name = "facing"
    gap = 4  # the two pages of a spread almost touch

    def __init__(self, cover_alone: bool = True):
        super().__init__()
        self.cover_alone = cover_alone

    def _cols(self) -> int:
        return 2

    def rows(self, n: int) -> list[list[int | None]]:
        """Pairs of pages; with the cover alone it is (–, 1), (2, 3), …; an odd last page stays alone."""
        order: list[int | None] = ([None] if self.cover_alone else []) + list(range(n))
        rows = [order[k : k + 2] for k in range(0, len(order), 2)]
        return [r + [None] * (2 - len(r)) for r in rows]

    def _align(self, col: int, cols: int, width: int, page_w: int) -> int:
        return width - page_w if col == 0 else 0  # both pages meet at the spine

    def spec(self) -> dict:
        """The mode as plain values."""
        return {"mode": self.name, "cover_alone": self.cover_alone}


class Grid(_Rows):
    """Pages in a grid of ``columns`` columns, row by row."""

    name = "grid"
    COLUMNS = (2, 3, 4)

    def __init__(self, columns: int = 3):
        super().__init__()
        self.columns = columns if columns in self.COLUMNS else 3

    def _cols(self) -> int:
        return self.columns

    def rows(self, n: int) -> list[list[int | None]]:
        """Rows of ``columns`` pages; the last row is filled from the left."""
        return [list(range(k, min(k + self.columns, n))) for k in range(0, n, self.columns)]

    def spec(self) -> dict:
        """The mode as plain values."""
        return {"mode": self.name, "columns": self.columns}


MODES = ("single", "continuous", "facing", "grid")


def make(spec: dict | None) -> ViewMode:
    """View mode from plain values ({"mode": …, "cover_alone": …, "columns": …}); unknown -> single page."""
    spec = spec or {}
    mode = spec.get("mode")
    if mode == "continuous":
        return Continuous()
    if mode == "facing":
        return Facing(bool(spec.get("cover_alone", True)))
    if mode == "grid":
        return Grid(int(spec.get("columns", 3) or 3))
    return SinglePage()


def for_single(single: bool) -> ViewMode:
    """The view mode for the single-page switch (single page or continuous)."""
    return SinglePage() if single else Continuous()
