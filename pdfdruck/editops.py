# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Bearbeiten-Modus: die Änderungen als benannte Operationen (ohne Oberfläche).

Damit laufen sie im Analyse-Prozess (renderproc „edit“): Laden, Ändern, Speichern und die Sicherheitsprüfung
einer großen Datei blockieren das Fenster nicht mehr. Jede Operation: (Daten, Seite, …) -> (neue Daten | None,
Hinweise); None = lässt sich nicht sicher ändern, Dokument bleibt wie es ist.
"""
from __future__ import annotations

import io

from . import editing
from .l10n import tr


def pdfium_edit(data: bytes, page: int, fn):
    """pdfium-Änderung an einer frisch geladenen Kopie -> (neue Daten, Hinweise)."""
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
    """Dieselbe Zeile nach einer Änderung wiederfinden: gleicher Text, nächstgelegene Mitte."""
    cx, cy = (L0.bbox[0] + L0.bbox[2]) / 2, (L0.bbox[1] + L0.bbox[3]) / 2
    same = [L for L in lines if L.text == L0.text] or lines
    if not same:
        return None
    best = min(same, key=lambda L: abs((L.bbox[0] + L.bbox[2]) / 2 - cx) + abs((L.bbox[1] + L.bbox[3]) / 2 - cy))
    h = max(1.0, L0.bbox[3] - L0.bbox[1])
    d = abs((best.bbox[0] + best.bbox[2]) / 2 - cx) + abs((best.bbox[1] + best.bbox[3]) / 2 - cy)
    return best if d <= max(20.0, 4 * h) else None


def move_lines(data, page, lines, s, dx, dy, origin):
    """Bevorzugt nur die Textblöcke umschließen (Seite bleibt sonst unverändert), Rest über pdfium."""
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
    return pdfium_edit(data, page, lambda d: editing.transform_objects_bulk(d, page, objs, s, dx, dy, origin))[0], []


def delete_objects(data, page, objs):
    return pdfium_edit(data, page, lambda d: editing.delete_objects(d, page, objs))[0], []


def remove_lines(data, page, lines):
    return editing.remove_lines_ops(data, page, lines), []


def recolor(data, page, color, lines, objs, fill, stroke):
    return editing.recolor(data, page, color, lines=lines, objs=objs, fill=fill, stroke=stroke), []


def edit_line(data, page, line, text, font, size):
    return editing.edit_line_bytes(data, page, line, text, font, size)


def edit_lines(data, page, lines, font, size):
    """Mehrere Zeilen: Schrift/Größe für alle; nach jeder Änderung die nächste Zeile neu suchen
        (Objektnummern können sich durch die Änderung verschieben)."""
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
            raise ValueError(tr("Zeile „{0}“ nach der Änderung nicht mehr gefunden – Änderung abgebrochen.")
                             .format(L0.text[:40]))
        size_arg = size if (abs(size - L.size) > 0.01 or font is not None) else None
        cur, n = editing.edit_line_bytes(cur, page, L, L.text, font, size_arg)
        notes += [x for x in n if x not in notes]
    return cur, notes


OPS = {"move_lines": move_lines, "move_objects": move_objects, "delete_objects": delete_objects,
       "remove_lines": remove_lines, "recolor": recolor, "edit_line": edit_line, "edit_lines": edit_lines}


def apply_and_verify(data: bytes, page: int, op: str, kwargs: dict, boxes: list) -> dict:
    """Operation ausführen und prüfen. -> {"new": Bytes | None, "unsafe": bool, "err": Text, "notes": […],
        "error": Text}  (error = Operation selbst gescheitert, z. B. Zeile nicht gefunden)."""
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
