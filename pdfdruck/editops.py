# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Edit mode: the changes as named operations (no user interface).

This lets them run in the analysis process (renderproc "edit"): loading, changing, saving and the safety check
of a large file no longer block the window. Every operation: (data, page, …) -> (new data | None,
notes); None = cannot be changed safely, the document stays as it is.
"""

from __future__ import annotations

import io

from . import editing
from .l10n import tr


def pdfium_edit(data: bytes, page: int, fn):
    """pdfium change on a freshly loaded copy -> (new data, notes)."""
    import pypdfium2 as pdfium

    d = pdfium.PdfDocument(data)
    try:
        notes = fn(d) or []
        buf = io.BytesIO()
        d.save(buf)
        return buf.getvalue(), notes
    finally:
        d.close()


def match_line(L0, lines):
    """Find the same row again after a change: same text, nearest centre."""
    cx, cy = (L0.bbox[0] + L0.bbox[2]) / 2, (L0.bbox[1] + L0.bbox[3]) / 2
    same = [L for L in lines if L.text == L0.text] or lines
    if not same:
        return None
    best = min(same, key=lambda L: abs((L.bbox[0] + L.bbox[2]) / 2 - cx) + abs((L.bbox[1] + L.bbox[3]) / 2 - cy))
    h = max(1.0, L0.bbox[3] - L0.bbox[1])
    d = abs((best.bbox[0] + best.bbox[2]) / 2 - cx) + abs((best.bbox[1] + best.bbox[3]) / 2 - cy)
    return best if d <= max(20.0, 4 * h) else None


def move_lines(data, page, lines, s, dx, dy, origin):
    """Preferably wrap only the text blocks (the page otherwise stays unchanged), the rest via pdfium."""
    new, pending = data, []
    for L in lines:
        b = editing.transform_line_blocks(new, page, L, s, dx, dy, origin)
        if b is not None:
            new = b
        else:
            pending.append(L)
    if pending:
        new = pdfium_edit(new, page, lambda d: editing.transform_lines_bulk(d, page, pending, s, dx, dy, origin))[0]
    return new, []


def move_objects(data, page, objs, s, dx, dy, origin):
    """Preferably wrap only the objects in the page content (the rest of the page stays unchanged), otherwise pdfium."""
    new = editing.edit_objects_content(data, page, objs, "transform", s, dx, dy, origin)
    if new is not None:
        return new, []
    return pdfium_edit(data, page, lambda d: editing.transform_objects_bulk(d, page, objs, s, dx, dy, origin))[0], []


def delete_objects(data, page, objs):
    """Preferably take only the objects out of the page content, otherwise pdfium (rewrites the whole page)."""
    new = editing.edit_objects_content(data, page, objs, "delete")
    if new is not None:
        return new, []
    return pdfium_edit(data, page, lambda d: editing.delete_objects(d, page, objs))[0], []


def remove_lines(data, page, lines):
    return editing.remove_lines_ops(data, page, lines), []


def recolor(data, page, color, lines, objs, fill, stroke):
    return editing.recolor(data, page, color, lines=lines, objs=objs, fill=fill, stroke=stroke), []


def edit_line(data, page, line, text, font, size):
    return editing.edit_line_bytes(data, page, line, text, font, size)


def edit_lines(data, page, lines, font, size):
    """Several rows: font/size for all; after every change look up the next row again
    (object numbers can shift because of the change).
    """
    import pypdfium2 as pdfium

    cur, notes = data, []
    for L0 in lines:
        d = pdfium.PdfDocument(cur)
        try:
            found = editing.text_lines(d, page, include_undecodable=True)
        finally:
            d.close()
        L = match_line(L0, found)
        if L is None:
            raise ValueError(
                tr("Zeile „{0}“ nach der Änderung nicht mehr gefunden – Änderung abgebrochen.").format(L0.text[:40])
            )
        size_arg = size if (abs(size - L.size) > 0.01 or font is not None) else None
        cur, n = editing.edit_line_bytes(cur, page, L, L.text, font, size_arg)
        notes += [x for x in n if x not in notes]
    return cur, notes


OPS = {
    "move_lines": move_lines,
    "move_objects": move_objects,
    "delete_objects": delete_objects,
    "remove_lines": remove_lines,
    "recolor": recolor,
    "edit_line": edit_line,
    "edit_lines": edit_lines,
}


def apply_and_verify(data: bytes, page: int, op: str, kwargs: dict, boxes: list) -> dict:
    """Run the operation and check it. -> {"new": bytes | None, "unsafe": bool, "err": text, "notes": […],
    "error": text}  (error = the operation itself failed, e.g. row not found).
    """
    try:
        new, notes = OPS[op](data, page, **kwargs)
    except Exception as e:
        return {"new": None, "error": str(e), "notes": []}
    if new is None:
        return {"new": None, "unsafe": True, "notes": notes}
    if new == data:
        return {"new": None, "notes": notes}
    err = editing.verify_edit(data, new, page, [tuple(b) for b in boxes])
    if err:
        return {"new": None, "err": err, "notes": notes}
    return {"new": new, "notes": notes}
