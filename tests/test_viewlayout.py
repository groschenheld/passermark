# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""View modes (gui/viewlayout.py): facing pages with and without the cover alone, grid with 2/3/4 columns,
fitting per spread/row, next/previous by spread or row, the current page at the end of the document."""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "_qtstub"), os.path.join(HERE, "..")]

from pdfdruck.gui import viewlayout as VL  # noqa: E402

A4 = (595, 842)
A4_LANDSCAPE = (842, 595)


class Bar:
    def __init__(self):
        self.v, self.mx = 0, 0

    def value(self):
        return self.v

    def maximum(self):
        return self.mx

    def setValue(self, v):
        self.v = max(0, min(int(v), self.mx))


class Size:
    def __init__(self, w, h):
        self.w, self.h = w, h

    def width(self):
        return self.w

    def height(self):
        return self.h


class Page:
    def __init__(self, i):
        self.index, self.g, self.shown = i, (0, 0, 0, 0), False

    def setGeometry(self, x, y, w, h):
        self.g = (x, y, w, h)

    def x(self):
        return self.g[0]

    def y(self):
        return self.g[1]

    def width(self):
        return self.g[2]

    def height(self):
        return self.g[3]

    def show(self):
        self.shown = True

    def hide(self):
        self.shown = False


class View:
    """Just what a view mode uses of PageView: fixed zoom 0.5 (or fitted into the mode's area)."""

    def __init__(self, sizes, mode, vw=900, vh=700, fit=False):
        self.sizes, self.view_mode, self.current, self.fit = sizes, mode, 0, fit
        self.pages = [Page(i) for i in range(len(sizes))]
        self.bar, self.vp = Bar(), Size(vw, vh)
        view = self

        class Container:
            def resize(self, w, h):
                view.cw, view.ch = w, h
                view.bar.mx = max(0, h - vh)

        self.container = Container()

    def viewport(self):
        return self.vp

    def verticalScrollBar(self):
        return self.bar

    def _rot_size(self, i):
        return self.sizes[i]

    def _rotate_master(self, w):
        pass

    def page_zoom(self, i):
        if not self.fit:
            return 0.5
        vw, vh = self.view_mode.fit_area(self, i)
        pw, ph = self.sizes[i]
        return min(vw / pw, vh / ph)

    def layout(self):
        self.view_mode.place(self, 1.0)
        return self


def test_rows():
    assert VL.Facing(True).rows(5) == [[None, 0], [1, 2], [3, 4]]
    assert VL.Facing(True).rows(4) == [[None, 0], [1, 2], [3, None]]  # last page alone (left)
    assert VL.Facing(False).rows(5) == [[0, 1], [2, 3], [4, None]]
    assert VL.Facing(False).rows(1) == [[0, None]]
    assert VL.Grid(3).rows(7) == [[0, 1, 2], [3, 4, 5], [6]]
    assert VL.Grid(4).rows(4) == [[0, 1, 2, 3]]
    assert VL.Grid(7).columns == 3  # only 2/3/4


def test_make_and_spec():
    for spec in (
        {"mode": "single"},
        {"mode": "continuous"},
        {"mode": "facing", "cover_alone": False},
        {"mode": "grid", "columns": 4},
    ):
        assert VL.make(spec).spec() == spec
    assert isinstance(VL.make(None), VL.SinglePage) and isinstance(VL.make({"mode": "x"}), VL.SinglePage)
    assert VL.make({"mode": "facing"}).cover_alone is True


def test_facing_meets_at_the_spine():
    v = View([A4] * 5, VL.Facing(True)).layout()
    w = int(595 * 0.5)
    spine = v.cw // 2
    p = v.pages
    assert p[0].x() > spine - 4 and p[0].y() == VL.PAGE_GAP  # cover alone on the right
    assert p[1].x() + w <= spine <= p[2].x() and p[2].x() - (p[1].x() + w) == VL.Facing.gap  # a spread
    assert p[1].y() == p[2].y() > p[0].y() and p[3].y() == p[4].y() > p[1].y()
    assert all(x.shown for x in p)


def test_facing_mixed_sizes():
    v = View([A4, A4, A4_LANDSCAPE, A4], VL.Facing(False)).layout()
    p = v.pages
    assert p[0].y() == p[1].y() and p[2].x() + p[2].width() == p[0].x() + p[0].width()  # left column: at the spine
    assert p[3].x() == p[1].x() and p[3].y() > p[1].y()  # right page of the second spread
    row_h = int(842 * 0.5)
    assert p[2].y() == p[3].y() + (row_h - int(595 * 0.5)) // 2  # landscape page centred in its row


def test_grid_columns_aligned():
    v = View([A4] * 7, VL.Grid(3)).layout()
    p = v.pages
    assert p[0].x() == p[3].x() == p[6].x() and p[1].x() == p[4].x() and p[2].x() == p[5].x()
    assert p[0].y() == p[1].y() == p[2].y() < p[3].y() < p[6].y()
    assert p[1].x() - (p[0].x() + p[0].width()) == VL.PAGE_GAP


def test_fit_per_spread_and_row():
    for mode, per_row in ((VL.Facing(False), 2), (VL.Grid(2), 2), (VL.Grid(3), 3), (VL.Grid(4), 4)):
        v = View([A4] * 8, mode, fit=True).layout()
        p = v.pages
        row = [x for x in p if x.y() == p[0].y()]
        assert len(row) == per_row, (mode.spec(), len(row))
        assert row[-1].x() + row[-1].width() <= v.vp.width() - VL.PAGE_GAP + 2  # the row fits the window
    single = View([A4] * 2, VL.Continuous(), fit=True)
    assert VL.Facing(True).fit_area(single, 0)[0] < VL.Continuous().fit_area(single, 0)[0]


def test_step_by_spread_and_row():
    v = View([A4] * 7, VL.Facing(True)).layout()
    m = v.view_mode
    assert m.step(v, 0, 1) == 1 and m.step(v, 1, 1) == 3 and m.step(v, 2, 1) == 3 and m.step(v, 3, -1) == 1
    assert m.step(v, 0, -1) < 0 and m.step(v, 5, 1) == 7  # beyond the document (goto ignores it)
    g = View([A4] * 7, VL.Grid(3)).layout()
    assert g.view_mode.step(g, 1, 1) == 3 and g.view_mode.step(g, 4, 1) == 6 and g.view_mode.step(g, 6, -1) == 3
    assert VL.Continuous().step(g, 4, 1) == 5


def test_goto_and_current_page_after_scrolling():
    v = View([A4] * 9, VL.Grid(3), vh=500).layout()
    m = v.view_mode
    m.goto(v, 4, False, False)
    assert v.current == 4 and v.bar.value() == v.pages[3].y() - VL.PAGE_GAP
    assert m.page_at_scroll(v) == 4  # current page is in the row: stays
    v.bar.setValue(0)
    assert m.page_at_scroll(v) == 0
    m.goto(v, 8, False, False)  # last row cannot reach the top: the view stays on page 9
    assert v.bar.value() == v.bar.maximum() and v.current == 8
    assert m.page_at_scroll(v) is None


if __name__ == "__main__":
    for k, fn in list(globals().items()):
        if k.startswith("test_"):
            fn()
            print("ok", k)
