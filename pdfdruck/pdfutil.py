# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Small helpers for pikepdf objects that several checks share: a stable key for an object, the resources of a page."""

from __future__ import annotations


def obj_key(obj) -> str:
    """Stable key of a PDF object: its object number, or – for a direct object – its identity."""
    try:
        og = obj.objgen
        if og != (0, 0):
            return f"{og[0]} {og[1]}"
    except Exception:  # noqa: BLE001 – malformed PDF object: skipped or default value
        pass
    return f"id{id(obj)}"


def page_resources(page):
    """Resources of a page, inherited from the page tree if the page has none of its own."""
    import pikepdf

    node = page.obj
    while node is not None:
        if "/Resources" in node:
            return node.Resources
        node = node.get("/Parent")
    return pikepdf.Dictionary()
