# SPDX-License-Identifier: GPL-3.0-or-later
"""Scroll bar for the whole document in the single-page view.

In the single-page view the scroll area only holds the current page, so its own scroll bar only covers that
page (and disappears when the page fits). This module maps a position in the whole document – page plus how far
that page is scrolled – to one scroll bar value and back. Pure arithmetic, no Qt: the widget lives in viewer.py.
"""

from __future__ import annotations

UNITS = 1000  # scroll bar steps per page


def maximum(pages: int) -> int:
    """Largest value of the document scroll bar for a document of ``pages`` pages."""
    return max(0, pages * UNITS - 1)


def to_value(page: int, inner: int, inner_max: int) -> int:
    """Document position -> scroll bar value. inner / inner_max: how far the page itself is scrolled."""
    part = round((UNITS - 1) * inner / inner_max) if inner_max > 0 else 0
    return max(0, page) * UNITS + min(max(part, 0), UNITS - 1)


def from_value(value: int, pages: int) -> tuple[int, float]:
    """Scroll bar value -> (page, share of the way down that page from 0.0 to 1.0)."""
    value = min(max(int(value), 0), maximum(pages))
    return value // UNITS, (value % UNITS) / (UNITS - 1)
