# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""View modes of the document view: how the pages are arranged in the scroll area.

PageView (gui/pageview.py) keeps the document, the zoom and the page widgets; a view mode only decides where the
pages go. Every mode has the same interface, so that a new mode (facing pages, grid) is one more class here:

- ``place(view, dpi)``: size and position the page widgets and the container for the current zoom
- ``fit_area(view, i)``: the space page ``i`` is fitted into for "fit width" / "fit page"
- ``goto(view, i, at_end, force)``: bring page ``i`` into view
- ``page_at_scroll(view)``: which page the view is on after scrolling (None = unchanged)
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


def for_single(single: bool) -> ViewMode:
    """The view mode for the single-page switch (until the mode chooser replaces it)."""
    return SinglePage() if single else Continuous()
