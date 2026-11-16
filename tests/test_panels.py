# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Narrow panels break texts into lines instead of cutting them off (common.wrap_buttons), and a change of the
page arrangement keeps the place in the page (pageview.set_view_mode)."""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "_qtstub"), os.path.join(HERE, "..")]

from pdfdruck.gui import common  # noqa: E402
from pdfdruck.gui.pageview import PageView  # noqa: E402
from pdfdruck.gui.viewlayout import PAGE_GAP  # noqa: E402


class FM:
    """Every character 7 px wide."""

    def horizontalAdvance(self, t):
        return 7 * len(t)


def test_wrap_words():
    w = common._wrap_words
    assert w("Neu prüfen", FM(), 500) == "Neu prüfen"
    assert w("Freie Schrift herunterladen …", FM(), 100) == "Freie Schrift\nherunterladen …"
    assert w("Bericht …", FM(), 30) == "Bericht …"  # "…" stays with its word, a long word stays whole
    assert w("a b c", FM(), 7) == "a\nb\nc"


class Bar:
    def __init__(self, v):
        self.v = v

    def value(self):
        return self.v


class Page:
    def __init__(self, y, h):
        self._y, self._h = y, h

    def y(self):
        return self._y

    def height(self):
        return self._h


class View:
    def __init__(self, value):
        self.pages = [Page(PAGE_GAP, 1000), Page(PAGE_GAP * 2 + 1000, 1000)]
        self.bar = Bar(value)

    def verticalScrollBar(self):
        return self.bar


def test_share_in_page():
    share = PageView._share_in_page
    v = View(1000 + PAGE_GAP + 500)  # half way down the second page
    assert abs(share(v, 1) - 0.5) < 1e-6
    assert share(View(0), 0) == 0.0
    assert share(View(10**6), 1) == 1.0
    assert share(View(0), 5) == 0.0  # no such page


if __name__ == "__main__":
    for k, fn in list(globals().items()):
        if k.startswith("test_"):
            fn()
            print("ok", k)
