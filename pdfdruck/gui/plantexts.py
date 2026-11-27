# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Display texts and small helpers shared by the plan and poster window modules (plandialog, planbuild, plansetup)."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox

FRAME_TEXT = {
    "auto": "Automatisch (zwei Außenlinien, sonst Inhalt + Rand)",
    "frame": "Auf die äußere Linie",
    "margin": "Inhalt + Rand",
    "none": "Ganze Seite",
}
ROTATE_TEXT = {
    "auto": "Kürzeste Länge auf der Rolle (drehen erlaubt)",
    "keep": "Wie angeliefert",
    "short": "Kurze Seite quer zur Rolle",
    "long": "Lange Seite quer zur Rolle",
}
ORDER_TEXT = {"list": "Reihenfolge der Liste", "roll": "Nach Rollenbreite (schmal zuerst)"}
COLOR_TEXT = {"": "Wie im Treiber", "color": "Farbe", "gray": "Graustufen"}
QMODE_TEXT = {
    "production": "Produktionsdruck (schnell)",
    "quality": "Qualitätsdruck (höchste Qualität)",
    "driver": "Wie im Treiber",
}
BLEED_TEXT = {"mirror": "Gespiegelt", "blank": "Leerraum", "color": "Einzelfarbe"}
OVER_TEXT = {
    "none": "Auslassen (Warnung)",
    "crop": "Abschneiden (was nicht passt)",
    "tile": "In Bahnen teilen (mit Überlappung)",
}
COPIES_TEXT = {
    "sheets": "Ein Auftrag, je Exemplar ein Blatt",
    "jobs": "Je Exemplar ein eigener Auftrag",
    "count": "Kopienzahl (Gerät entscheidet übers Schneiden)",
}
SCALE_TEXT = {"pct": "Prozent", "short": "Kurze Kante auf", "long": "Lange Kante auf"}
ALIGN_TEXT = {"center": "Mittig", "left": "Am Rand (links)", "right": "Am Rand (rechts)"}
KIND_SHORT = {"frame": "Außenlinie", "margin": "Rand", "page": "Seite", "empty": "leer"}
PREVIEW_PX = 150  # preview image: longer edge in pixels
PREVIEW_MAX = 24  # at most this many print pages in the preview
ORIGIN_TEXT = {
    "ipp": "vom Gerät (IPP)",
    "snmp": "vom Gerät (SNMP)",
    "manual": "von Hand eingetragen",
    "settings": "aus den Einstellungen",
    "roland": "vom Gerät (Roland)",
}
COLOR_MODE_TEXT = {"convert": "Umwandeln", "embed": "Nur einbetten", "none": "Nichts"}
SOURCE_TEXT = {"hand": "von Hand", "device": "vom Gerät", "import": "importiert"}
CAT_TEXT = {"plan": "Plandruck", "quality": "Qualitätsdruck"}


def fill_combo(combo: QComboBox, choices, current):
    """(value, text) – without driver value tooltips (own choice, not a driver option)."""
    combo.blockSignals(True)
    combo.clear()
    for val, text in choices:
        combo.addItem(text, val)
    i = combo.findData(current)
    combo.setCurrentIndex(i if i >= 0 else 0)
    combo.blockSignals(False)
