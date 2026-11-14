# SPDX-License-Identifier: GPL-3.0-or-later
"""Scroll bar for the whole document in the single-page view: the mapping between position and value."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pdfdruck.gui import docscroll as d


def test_range_covers_all_pages():
    """One page spans UNITS steps; no document, no range."""
    assert d.maximum(0) == 0 and d.maximum(1) == d.UNITS - 1 and d.maximum(12) == 12 * d.UNITS - 1


def test_position_to_value():
    """Top of a page is the start of its span, the bottom its end; a page that fits has no inner position."""
    assert d.to_value(0, 0, 500) == 0
    assert d.to_value(3, 0, 500) == 3 * d.UNITS
    assert d.to_value(3, 500, 500) == 4 * d.UNITS - 1
    assert d.to_value(3, 250, 500) == 3 * d.UNITS + round((d.UNITS - 1) / 2)
    assert d.to_value(3, 0, 0) == 3 * d.UNITS  # page fits into the window
    assert d.to_value(3, 900, 500) == 4 * d.UNITS - 1  # out of range: stays on its page


def test_value_to_position():
    """The value names the page and how far down it is; values outside the range are clamped."""
    assert d.from_value(0, 5) == (0, 0.0)
    assert d.from_value(2 * d.UNITS, 5) == (2, 0.0)
    assert d.from_value(3 * d.UNITS - 1, 5) == (2, 1.0)
    assert d.from_value(10**9, 5) == (4, 1.0) and d.from_value(-7, 5) == (0, 0.0)


def test_round_trip():
    """Value -> position -> value gives the same value again, for every step of a document."""
    pages, inner_max = 7, 999
    for v in range(d.maximum(pages) + 1):
        page, share = d.from_value(v, pages)
        assert d.to_value(page, round(share * inner_max), inner_max) == v, v


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
