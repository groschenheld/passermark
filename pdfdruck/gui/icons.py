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
    "actual": '<rect x="4" y="4" width="16" height="16" rx="1"/><path d="M8 9.5l2-1.5v8M14 9.5l2-1.5v8"/>',
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
