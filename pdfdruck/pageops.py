# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Seitenoperationen am geöffneten Dokument (pdfium), ohne Oberfläche."""
from __future__ import annotations

A4 = (595.2756, 841.8898)


def insert_blank(doc, index: int, ref: int | None = None, count: int = 1) -> int:
    """count Leerseiten vor Seite index einfügen (index = len(doc) -> ans Ende).

        Die neue Seite übernimmt von der Vorlagenseite ref Format, Drehung und die Rahmen (Beschnitt-, Endformat-,
        Anschnittrahmen) – so passt sie in Ausschießen, Duplex und Druckaufbereitung wie die Nachbarseiten.
        Ohne Vorlage: A4 hoch. Rückgabe: Anzahl eingefügter Seiten."""
    n = len(doc)
    index = max(0, min(int(index), n))
    count = max(1, int(count))
    boxes, rot = None, 0
    if ref is not None and 0 <= ref < n:
        pg = doc[ref]
        try:
            boxes = {"media": tuple(pg.get_mediabox()),
                     "crop": pg.get_cropbox(fallback_ok=False),
                     "bleed": pg.get_bleedbox(fallback_ok=False),
                     "trim": pg.get_trimbox(fallback_ok=False),
                     "art": pg.get_artbox(fallback_ok=False)}
            rot = pg.get_rotation()
        finally:
            pg.close()
    for k in range(count):
        if boxes:
            l, b, r, t = boxes["media"]
            new = doc.new_page(r - l, t - b, index + k)
            try:
                new.set_mediabox(l, b, r, t)
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
