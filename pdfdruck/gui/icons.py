# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Eigene, einfarbige Linien-Icons (24×24, als SVG gezeichnet) – sachlich, zum dunklen Theme passend."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from . import theme

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
    "merge": '<rect x="3" y="3" width="9" height="12" rx="1"/><rect x="12" y="9" width="9" height="12" rx="1"/>',
    "settings": '<path d="M4 6h16M4 12h16M4 18h16"/><circle cx="9" cy="6" r="2" fill="{bg}"/><circle cx="15" cy="12" r="2" fill="{bg}"/><circle cx="7" cy="18" r="2" fill="{bg}"/>',
    "export": '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
    "insert": '<rect x="5" y="3" width="14" height="18" rx="1"/><path d="M12 8v8M8 12h8"/>',
    "delete": '<path d="M4 7h16M9 7V4h6v3M6.5 7l1 13h9l1-13M10 11v6M14 11v6"/>',
    "fit_width": '<rect x="3" y="5" width="18" height="14" rx="1"/><path d="M7 12h10M9 10l-2 2 2 2M15 10l2 2-2 2"/>',
    "fit_page": '<rect x="6" y="3" width="12" height="18" rx="1"/><path d="M12 7v10M10 9l2-2 2 2M10 15l2 2 2-2"/>',
    "ruler": '<path d="M3 17L17 3l4 4L7 21z"/><path d="M7.5 12.5l2 2M10.5 9.5l2 2M13.5 6.5l2 2"/>',
    "actual": '<rect x="4" y="4" width="16" height="16" rx="1"/><path d="M8 9.5l2-1.5v8M14 9.5l2-1.5v8"/>',
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
}


def _svg(name: str, color: str) -> bytes:
    body = _SHAPES[name].replace("{bg}", theme.PANEL)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{body}</svg>').encode()


def _pixmap(name: str, color: str, size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    r = QSvgRenderer(QByteArray(_svg(name, color)))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r.render(p, QRectF(0, 0, size, size))
    p.end()
    return pm


_cache: dict[str, QIcon] = {}


def icon(name: str) -> QIcon:
    if name not in _cache:
        ic = QIcon()
        for size in (16, 20, 24, 32, 48):
            ic.addPixmap(_pixmap(name, theme.ICON, size), QIcon.Mode.Normal, QIcon.State.Off)
            ic.addPixmap(_pixmap(name, theme.ACCENT, size), QIcon.Mode.Active, QIcon.State.Off)
            ic.addPixmap(_pixmap(name, theme.ACCENT, size), QIcon.Mode.Normal, QIcon.State.On)
            ic.addPixmap(_pixmap(name, theme.ICON_OFF, size), QIcon.Mode.Disabled, QIcon.State.Off)
        _cache[name] = ic
    return _cache[name]
