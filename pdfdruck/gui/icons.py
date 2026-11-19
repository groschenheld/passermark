# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Line icons of the interface. Since 1.19.0 Hias' own set (gui/svgicons/*.svg, drawn with ``currentColor`` so the
program colours them per state); the few names without a file of their own keep the older built-in shapes below.
"""

from __future__ import annotations

import os

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap, QTransform
from PySide6.QtSvg import QSvgRenderer

from . import theme

SVG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "svgicons")

# icon name used in the program -> (file in svgicons/, mirrored)
_FILES = {
    "actual": ("tatsaechliche_groesse", False),
    "fit_page": ("ganze_seite", False),
    "copy": ("text_kopieren", False),
    "select": ("text_markieren", False),
    "delete": ("seiten_loeschen", False),
    "move_up": ("seiten_nach_vorne", False),
    "move_down": ("seiten_nach_hinten", False),
    "export": ("export", False),
    "info": ("info", False),
    "history": ("letzte_drucke", False),
    "roll": ("rollen", False),
    "open": ("oeffnen", False),
    "save": ("speichern", False),
    "print": ("drucken", False),
    "prev": ("nach_oben", False),
    "next": ("nach_unten", False),
    "zoom_in": ("groesser", False),
    "zoom_out": ("kleiner", False),
    "rot_r": ("aktualisieren", False),
    "rot_l": ("aktualisieren", True),
    "update": ("aktualisieren", False),
    "single": ("einzelseite", False),
    "multi": ("mehrere_seiten", False),
    "facing": ("mehrere_seiten", False),
    "grid": ("mehrere_seiten", False),
    "continuous": ("scrollen", False),
    "scroll": ("scrollen", False),
    "merge": ("zusammenfuehren", False),
    "split": ("teilen", False),
    "edit": ("bearbeiten", False),
    "settings": ("einstellungen", False),
    "insert": ("einfuegen", False),
    "fit_width": ("seitenbreite", False),
    "proof": ("softproof", False),
    "material": ("papiermessung", False),
    "ruler": ("lineal", False),
    "measure": ("messen", False),
    "pipette": ("pipette", False),
    "vdp": ("variable_daten", False),
    "table": ("daten_erfassen", False),
    "qr": ("beispiele", False),
    "book": ("anleitung", False),
    "folder_gear": ("automatisierung", False),
    "plan": ("plan", False),
    "poster": ("poster", False),
    "cut": ("cutcontour", False),
    "cmyk": ("cmyk", False),
    "color": ("farbe", False),
    "crop": ("beschneiden", False),
    "boxes": ("endformat_und_anschnitt", False),
    "bleed": ("beschnitt", False),
    "separate": ("objekte_trennen", False),
    "check": ("preflight", False),
    "repair": ("reparieren", False),
    "shrink": ("komprimieren", False),
    "step_repeat": ("step_repeat", False),
    "tools": ("werkzeuge", False),
    "sidebar": ("seitenleiste_schliessen", False),
    "sidebar_open": ("seitenleiste_oeffnen", False),
    "sidebar_close": ("seitenleiste_schliessen", False),
    "win_min": ("minimieren", False),
    "win_max": ("vergroessern", False),
    "win_close": ("schliessen", False),
    "grip": ("greifer_fuer_fenster_vergroesserung", False),
    "scroll_grip": ("scrolling", False),
    "left": ("links", False),
    "right": ("rechts", False),
}

_SHAPES = {
    "open": '<path d="M3 7.5A1.5 1.5 0 0 1 4.5 6H9l2 2h8.5A1.5 1.5 0 0 1 21 9.5v8A1.5 1.5 0 0 1 19.5 19h-15A1.5 1.5 0 0 1 3 17.5z"/>',
    "save": '<path d="M5 4h11l3 3v12a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1z"/><path d="M8 4v5h7V4"/><rect x="8" y="13" width="8" height="7"/>',
    "print": '<path d="M7 9V4h10v5"/><rect x="3.5" y="9" width="17" height="7.5" rx="1.5"/><rect x="7" y="13.5" width="10" height="6.5"/><path d="M17 12h.01"/>',
    "sidebar": '<rect x="3" y="4" width="18" height="16" rx="1.5"/><path d="M9 4v16"/><path d="M5.5 8h1.5M5.5 11h1.5M5.5 14h1.5"/>',
    "prev": '<path d="M6 15l6-6 6 6"/>',
    "next": '<path d="M6 9l6 6 6-6"/>',
    "zoom_in": '<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5 5M8 10.5h5M10.5 8v5"/>',
    "zoom_out": '<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5 5M8 10.5h5"/>',
    "rot_l": '<path d="M4.5 12.5A7.5 7.5 0 1 0 7 6.6"/><path d="M4 3.5V8h4.5"/>',
    "rot_r": '<path d="M19.5 12.5A7.5 7.5 0 1 1 17 6.6"/><path d="M20 3.5V8h-4.5"/>',
    "single": '<rect x="6" y="3" width="12" height="18" rx="1"/><path d="M9 8h6M9 11h6M9 14h4"/>',
    "continuous": '<path d="M6 2v7a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V2"/><rect x="6" y="13" width="12" height="9" rx="1"/>',
    "facing": '<rect x="2.5" y="5" width="9" height="14" rx="1"/><rect x="12.5" y="5" width="9" height="14" rx="1"/>',
    "grid": '<rect x="4" y="4" width="7" height="7" rx="1"/><rect x="13" y="4" width="7" height="7" rx="1"/><rect x="4" y="13" width="7" height="7" rx="1"/><rect x="13" y="13" width="7" height="7" rx="1"/>',
    "merge": '<rect x="3" y="3" width="9" height="12" rx="1"/><rect x="12" y="9" width="9" height="12" rx="1"/>',
    "settings": '<path d="M4 6h16M4 12h16M4 18h16"/><circle cx="9" cy="6" r="2" fill="{bg}"/><circle cx="15" cy="12" r="2" fill="{bg}"/><circle cx="7" cy="18" r="2" fill="{bg}"/>',
    "export": '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
    "insert": '<rect x="5" y="3" width="14" height="18" rx="1"/><path d="M12 8v8M8 12h8"/>',
    "delete": '<path d="M4 7h16M9 7V4h6v3M6.5 7l1 13h9l1-13M10 11v6M14 11v6"/>',
    "fit_width": '<rect x="3" y="5" width="18" height="14" rx="1"/><path d="M7 12h10M9 10l-2 2 2 2M15 10l2 2-2 2"/>',
    "proof": '<rect x="3.5" y="5" width="13" height="15" rx="1"/><path d="M14 3.5h5.5a1 1 0 0 1 1 1V16"/><path d="M10 8.5c-2 2.6-3 4.3-3 5.5a3 3 0 0 0 6 0c0-1.2-1-2.9-3-5.5z"/>',
    "material": '<path d="M4 6l8-3 8 3-8 3z"/><path d="M4 10.5l8 3 8-3"/><path d="M4 15l8 3 8-3"/>',
    "fit_page": '<rect x="6" y="3" width="12" height="18" rx="1"/><path d="M12 7v10M10 9l2-2 2 2M10 15l2 2 2-2"/>',
    "ruler": '<path d="M3 17L17 3l4 4L7 21z"/><path d="M7.5 12.5l2 2M10.5 9.5l2 2M13.5 6.5l2 2"/>',
    "actual": '<rect x="4" y="4" width="16" height="16" rx="1"/><path d="M8 9.5l2-1.5v8M14 9.5l2-1.5v8"/>',
    "history": '<path d="M3.5 12a8.5 8.5 0 1 0 2.5-6"/><path d="M3.5 4v4h4"/><path d="M12 7.5V12l3 2"/>',
    "pipette": '<path d="M15 4.5a2.1 2.1 0 0 1 3 0l1.5 1.5a2.1 2.1 0 0 1 0 3L17 11.5 12.5 7z"/>'
    '<path d="M11 8.5l4.5 4.5M13.5 10l-8 8H3.5v-2l8-8"/>',
    "measure": '<path d="M4 20L20 4"/><path d="M4 16v4h4M20 8V4h-4"/><path d="M9 13l2 2M12 10l2 2"/>',
    "cut": '<circle cx="6.5" cy="17.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/><path d="M8.3 15.7L18 4M15.7 15.7L6 4"/>',
    "cmyk": '<circle cx="9" cy="9" r="4.5"/><circle cx="15" cy="9" r="4.5"/><circle cx="12" cy="14.5" r="4.5"/>',
    "crop": '<path d="M7 3v14h14"/><path d="M3 7h14v14"/>',
    "separate": '<rect x="3" y="3" width="7.5" height="7.5" rx="1"/><rect x="13.5" y="3" width="7.5" height="7.5" rx="1"/><rect x="3" y="13.5" width="7.5" height="7.5" rx="1"/><path d="M14 17.5h6M17 14.5v6" stroke-dasharray="1.5 2"/>',
    "edit": '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
    "check": '<path d="M12 3l7.5 3v6c0 4.2-3.2 7.6-7.5 9-4.3-1.4-7.5-4.8-7.5-9V6z"/><path d="M8.5 12l2.5 2.5 4.5-5"/>',
    "repair": '<path d="M14.5 6.5a4 4 0 0 0 5 5L12 19a2.1 2.1 0 0 1-3-3l7.5-7.5a4 4 0 0 0-2-2z"/><path d="M14.5 6.5l3-3a4 4 0 0 1 2 5"/>',
    "copy": '<rect x="8" y="8" width="12" height="12" rx="1"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/>',
    "select": '<rect x="4" y="4" width="16" height="16" rx="1" stroke-dasharray="2 2.5"/><path d="M8 10h8M8 14h6"/>',
    "table": '<rect x="3.5" y="4.5" width="17" height="15" rx="1.5"/><path d="M3.5 9.5h17M3.5 14.5h17M9.5 9.5v10"/>',
    "split": '<rect x="3.5" y="5" width="17" height="14" rx="1"/><path d="M12 3v18" stroke-dasharray="2 2"/>',
    "book": '<path d="M4 5.5C4 4.7 4.7 4 5.5 4H11v16H5.5C4.7 20 4 19.3 4 18.5z"/><path d="M20 5.5c0-.8-.7-1.5-1.5-1.5H13v16h5.5c.8 0 1.5-.7 1.5-1.5z"/>',
    "terminal": '<rect x="3" y="4.5" width="18" height="15" rx="1.5"/><path d="M7 10l3 2.5L7 15M12.5 15H17"/>',
    "folder_gear": '<path d="M3 7.5A1.5 1.5 0 0 1 4.5 6H9l2 2h8.5A1.5 1.5 0 0 1 21 9.5v8A1.5 1.5 0 0 1 19.5 19h-15A1.5 1.5 0 0 1 3 17.5z"/><circle cx="12" cy="13.5" r="2.2"/>',
    "vdp": '<rect x="3" y="4" width="18" height="16" rx="1.5"/><path d="M6 8h2M6 11h2M6 14h2M10 8h8M10 11h8M10 14h5"/><path d="M15 17l1.5 1.5L20 15"/>',
    "qr": '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><path d="M14 14h3v3h-3zM18 18h3v3M14 21h2"/>',
    "lock": '<rect x="5" y="11" width="14" height="9.5" rx="1.5"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/><path d="M12 15v2"/>',
    "move_up": '<rect x="6" y="9" width="12" height="12" rx="1"/><path d="M12 3v3.5M9.5 5L12 2.5 14.5 5"/>',
    "move_down": '<rect x="6" y="3" width="12" height="12" rx="1"/><path d="M12 21v-3.5M9.5 19l2.5 2.5 2.5-2.5"/>',
    "info": '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v6"/><path d="M12 7.6v.4"/>',
    "roll": '<ellipse cx="7" cy="8.5" rx="3.5" ry="4.5"/><ellipse cx="7" cy="8.5" rx="1.2" ry="1.6"/>'
    '<path d="M7 4h10.5c1.9 0 3.5 2 3.5 4.5S19.4 13 17.5 13H10"/><path d="M10 13v7.5h10V13"/>',
    "plan": '<rect x="3" y="5" width="18" height="14" rx="0.5"/><rect x="5.2" y="7.2" width="13.6" height="9.6"/>'
    '<path d="M12.5 13.3h6.3M12.5 13.3v3.5"/>',
}


def has_file(name: str) -> bool:
    """Does ``name`` come from Hias' icon set (gui/svgicons)?"""
    return name in _FILES


# drawn in black and white for a light ground: on the dark interface black becomes ``color`` and white the
# panel colour (the blue slider knob of "Werkzeuge" stays blue)
_BLACK_WHITE = {"tools"}


def _svg(name: str, color: str) -> bytes:
    if name in _FILES:
        with open(os.path.join(SVG_DIR, _FILES[name][0] + ".svg"), encoding="utf-8") as f:
            text = f.read().replace("currentColor", color)
        if name in _BLACK_WHITE:
            text = (
                text.replace("stroke:black", f"stroke:{color}")
                .replace("fill:white", f"fill:{theme.PANEL}")
                .replace("stroke:white", f"stroke:{theme.PANEL}")
                .replace("<svg ", f'<svg fill="{color}" ', 1)
            )
        return text.encode()
    body = _SHAPES[name].replace("{bg}", theme.PANEL)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
        f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
    ).encode()


def pixmap(name: str, color: str, size: int) -> QPixmap:
    """Icon ``name`` in ``color``, ``size`` pixels square; icons that are not square keep their proportions."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    r = QSvgRenderer(QByteArray(_svg(name, color)))
    vb = r.viewBoxF()
    w, h = (vb.width(), vb.height()) if vb.width() > 0 and vb.height() > 0 else (1.0, 1.0)
    k = size / max(w, h)
    target = QRectF((size - w * k) / 2, (size - h * k) / 2, w * k, h * k)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r.render(p, target)
    p.end()
    if name in _FILES and _FILES[name][1]:
        pm = pm.transformed(QTransform().scale(-1, 1))
    return pm


_cache: dict[str, QIcon] = {}


def icon_in(name: str, color: str) -> QIcon:
    """Icon ``name`` always in ``color`` (e.g. the window buttons in the accent), dimmed when disabled."""
    key = f"{name}@{color}"
    if key not in _cache:
        ic = QIcon()
        for size in (16, 20, 24, 32):
            ic.addPixmap(pixmap(name, color, size), QIcon.Mode.Normal, QIcon.State.Off)
            ic.addPixmap(pixmap(name, theme.ICON_OFF, size), QIcon.Mode.Disabled, QIcon.State.Off)
        _cache[key] = ic
    return _cache[key]


def icon(name: str) -> QIcon:
    """The line icon ``name`` as a QIcon in several sizes (cached): normal, under the mouse/checked in the accent,
    disabled dimmed."""
    if name not in _cache:
        ic = QIcon()
        for size in (16, 20, 24, 32, 48):
            ic.addPixmap(pixmap(name, theme.ICON, size), QIcon.Mode.Normal, QIcon.State.Off)
            ic.addPixmap(pixmap(name, theme.ACCENT_TEXT, size), QIcon.Mode.Active, QIcon.State.Off)
            ic.addPixmap(pixmap(name, theme.ACCENT_TEXT, size), QIcon.Mode.Normal, QIcon.State.On)
            ic.addPixmap(pixmap(name, theme.ICON_OFF, size), QIcon.Mode.Disabled, QIcon.State.Off)
        _cache[name] = ic
    return _cache[name]
