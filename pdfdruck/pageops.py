# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Page operations on the open document (pdfium), no user interface."""

from __future__ import annotations

A4 = (595.2756, 841.8898)


def insert_blank(doc, index: int, ref: int | None = None, count: int = 1) -> int:
    """Insert count blank pages before page index (index = len(doc) -> at the end).

    The new page takes size, rotation and the boxes (crop, trim, bleed box) from the template page ref –
    so it fits imposition, duplex and print preparation like its neighbours.
    Without a template: A4 portrait. Returns the number of inserted pages.
    """
    n = len(doc)
    index = max(0, min(int(index), n))
    count = max(1, int(count))
    boxes, rot = None, 0
    if ref is not None and 0 <= ref < n:
        pg = doc[ref]
        try:
            boxes = {
                "media": tuple(pg.get_mediabox()),
                "crop": pg.get_cropbox(fallback_ok=False),
                "bleed": pg.get_bleedbox(fallback_ok=False),
                "trim": pg.get_trimbox(fallback_ok=False),
                "art": pg.get_artbox(fallback_ok=False),
            }
            rot = pg.get_rotation()
        finally:
            pg.close()
    for k in range(count):
        if boxes:
            left, b, r, t = boxes["media"]
            new = doc.new_page(r - left, t - b, index + k)
            try:
                new.set_mediabox(left, b, r, t)
                for name in ("crop", "bleed", "trim", "art"):
                    if boxes[name] is not None:
                        getattr(new, f"set_{name}box")(*boxes[name])
                if rot:
                    new.set_rotation(rot)
            finally:
                new.close()
        else:
            doc.new_page(*A4, index + k).close()
    return count
