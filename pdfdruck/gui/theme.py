# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Dark theme in Hias' colours (1.19.0: blue accent #007DAF, black/#272727 surfaces) + global mouse wheel guard."""

from __future__ import annotations

import os
import tempfile

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QAbstractScrollArea, QAbstractSpinBox, QApplication, QComboBox, QSlider

# All colours of the user interface live here – nothing else in gui/ names a colour of its own (paper white and
# the colours a user picks for their document are not interface colours).

# Hias' palette (13.11.2026): #007DAF main colour, #F20D0D error, #50BC26 ok, #E5F20D warning, #F4A122 selection,
# #000000 and #272727 surfaces. The in-between greys are derived from the two surfaces (neutral, no tint – the
# surroundings of the page must not change how colours look, soft proof).

# surfaces
BG = "#000000"  # window frame: title bar, status bar
PANEL = "#272727"  # bars, side panels, groups
FIELD = "#161616"  # input fields
VIEW = "#2f2f2f"  # background behind the pages (neutral grey)
BUTTON = "#1c1c1c"  # push buttons
PLACEHOLDER = "#3a3a3a"  # thumbnail that is not selected
TIP_BG = "#000000"  # tool tips
SCROLL = "#4d4d4d"  # handle of the scroll bars

# lines
BORDER = "#4a4a4a"  # border (light enough for contrast on both surfaces)
BORDER_HOVER = "#808080"  # border under the mouse / with focus; check boxes
BORDER_SUBTLE = "#383838"  # faint border (thumbnails, page number field)
BORDER_OFF = "#333333"  # disabled button
BORDER_OFF_FIELD = "#2c2c2c"  # disabled input field

# text and icons
TEXT = "#f2f2f2"
MUTED = "#a6a6a6"
ICON = "#e6e6e6"
ICON_OFF = "#5e5e5e"

# accent: what is active, chosen or to be clicked next
ACCENT = "#007DAF"  # blue: fills, frames, icons
ACCENT_TEXT = "#3AAEE0"  # the accent as text or thin line on the dark surfaces (#007DAF has only ~3.3:1 there)
ACCENT_OFF = "#1d4252"  # checked but disabled – a dimmed ACCENT, change both together
ON_ACCENT = "#FFFFFF"  # text and check marks on the accent colour

# status
ERROR = "#F20D0D"
OK = "#50BC26"
WARN = "#E5F20D"  # warnings (always together with a symbol, never colour alone)
SELECT = "#F4A122"  # chosen / marked
INVALID_FIELD = "#ffd6d6"  # background of a field with an invalid entry

# drawn on top of the page (must stand out against paper and artwork, not against the dark interface)
MARK = "#ec008c"  # magenta: cut lines, handles, variable-data fields
MARK_OBJECT = "#00a0ff"  # detected objects
MARK_OK = "#2e9e4f"  # inside the limits (trim size, measured value fits)
MARK_ERROR = "#e0301e"  # outside the limits
SELECT_TEXT = "#ff8a00"  # edit mode: chosen text / object
SELECT_LAYER = "#00a8ff"  # edit mode: chosen layer
PAPER_INK = "#1b1d20"  # schematic drawing on the paper preview
PAPER_LINE = "#999999"  # auxiliary lines on the paper preview


def alpha(color: str, a: int) -> QColor:
    """The colour with an opacity of a (0–255) – for translucent fills."""
    c = QColor(color)
    c.setAlpha(a)
    return c


def _rgba(color: str, opacity: str) -> str:
    """ "#rrggbb" as "rgba(r, g, b, opacity)" for style sheets."""
    r, g, b = (int(color[i : i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r}, {g}, {b}, {opacity})"


ACCENT_SOFT = _rgba(ACCENT, "0.36")  # Hias: backgrounds in the accent at 36 % opacity

UI_FONTS = ["IBM Plex Sans", "Inter", "Segoe UI Variable Text", "Segoe UI", "Ubuntu", "Noto Sans", "DejaVu Sans"]
MONO_FONTS = ["IBM Plex Mono", "JetBrains Mono", "Cascadia Mono", "Consolas", "Ubuntu Mono", "DejaVu Sans Mono"]


def _first_available(names):
    fams = set(QFontDatabase.families())
    return next((n for n in names if n in fams), None)


def mono_font(size: float = 9.5) -> QFont:
    """A monospaced font that is available on this system."""
    f = QFont()
    fam = _first_available(MONO_FONTS)
    if fam:
        f.setFamily(fam)
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setPointSizeF(size)
    return f


QSS = f"""
* {{ color: {TEXT}; }}
QMainWindow, QDialog {{ background: {BG}; }}
QMainWindow#passermarkHost, QWidget#hostFrame {{ background: transparent; }}
QWidget {{ selection-background-color: {ACCENT}; selection-color: {ON_ACCENT}; }}
QToolTip {{ background: {TIP_BG}; color: {TEXT}; border: 1px solid {ACCENT}; padding: 4px; }}

QMenuBar {{ background: {PANEL}; border-bottom: 1px solid {BORDER}; }}
QMenuBar::item {{ padding: 4px 10px; background: transparent; }}
QMenuBar::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}
QMenu {{ background: {PANEL}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 5px 24px 5px 22px; }}
QMenu::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}
QMenu::item:disabled {{ color: {ICON_OFF}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}

QToolBar {{ background: {PANEL}; border: none; border-bottom: 1px solid {BORDER}; spacing: 3px; padding: 3px; }}
QToolBar::separator {{ background: {BORDER}; width: 1px; margin: 4px 6px; }}
QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 4px; padding: 4px; }}
QToolButton:hover {{ border-color: {ACCENT}; background: {ACCENT_SOFT}; }}
QToolButton:pressed, QToolButton:checked {{ background: {ACCENT_SOFT}; border-color: {ACCENT}; color: {TEXT}; }}
QToolButton:disabled {{ color: {ICON_OFF}; }}

QPushButton {{ background: {BUTTON}; border: 1px solid {BORDER}; border-radius: 4px; padding: 5px 14px; }}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:pressed, QPushButton:checked {{ background: {ACCENT}; color: {ON_ACCENT}; border-color: {ACCENT}; }}
QPushButton:default {{ border: 2px solid {ACCENT}; }}
QPushButton:disabled {{ color: {ICON_OFF}; border-color: {BORDER_OFF}; }}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit {{
    background: {FIELD}; border: 1px solid {BORDER}; border-radius: 3px; padding: 4px 6px; min-height: 18px; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus {{
    border: 1px solid {ACCENT}; }}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover {{ border-color: {BORDER_HOVER}; }}
QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QLineEdit:disabled {{
    color: {ICON_OFF}; border-color: {BORDER_OFF_FIELD}; }}
QComboBox QAbstractItemView {{ background: {FIELD}; border: 1px solid {ACCENT}; outline: none;
    selection-background-color: {ACCENT}; selection-color: {ON_ACCENT}; }}

QGroupBox {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 5px; margin-top: 14px; padding-top: 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {ACCENT_TEXT}; font-weight: 600; }}

QCheckBox::indicator, QRadioButton::indicator {{ width: 14px; height: 14px; border: 1px solid {BORDER_HOVER}; background: {FIELD}; }}
QCheckBox::indicator {{ border-radius: 2px; }}
QRadioButton::indicator {{ border-radius: 7px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox:disabled, QRadioButton:disabled {{ color: {ICON_OFF}; }}

QTabWidget::pane {{ border: 1px solid {BORDER}; top: -1px; background: {BG}; }}
QTabBar::tab {{ background: {PANEL}; border: 1px solid {BORDER}; padding: 6px 14px; margin-right: 2px; }}
QTabBar::tab:selected {{ border-bottom: 2px solid {ACCENT}; color: {ACCENT_TEXT}; }}
QTabBar::tab:hover {{ color: {ACCENT_TEXT}; }}

QDockWidget {{ titlebar-close-icon: none; }}
QDockWidget::title {{ background: {PANEL}; padding: 5px; border-bottom: 1px solid {BORDER}; }}
QStatusBar {{ background: {BG}; border-top: 1px solid {BORDER_SUBTLE}; }}
QStatusBar::item {{ border: none; }}
QStatusBar QLabel {{ color: {TEXT}; }}

QListWidget {{ background: {FIELD}; border: 1px solid {BORDER}; outline: none; }}
QListWidget::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}
QScrollArea {{ border: none; }}

QToolBar#mainBar {{ background: {PANEL}; border: none; border-bottom: 2px solid {BG}; padding: 4px 8px; spacing: 4px; }}
QToolBar#rail {{ background: {BG}; border: none; padding: 0; spacing: 0; }}
QWidget#rail {{ background: transparent; }}
QWidget#sideStrip {{ background: {PANEL}; border-right: 1px solid {BG}; }}
QFrame#toolbox {{ background: transparent; border: none; }}
QFrame#toolbox QToolButton {{ border: none; padding: 2px 0; }}
QFrame#toolbox QToolButton:hover {{ color: {ACCENT_TEXT}; }}
QToolButton#toolboxArrow {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 0; padding: 0; }}
QToolButton#toolboxArrow:hover {{ border-color: {ACCENT}; }}
QWidget#toolsPanel, QWidget#toolsHead {{ background: {PANEL}; }}
QToolButton#toolsClose {{ border: 1px solid {ACCENT}; border-radius: 3px; background: {BG}; }}
QLabel#toolsGroup {{ color: {ACCENT_TEXT}; border-bottom: 1px dotted {ACCENT}; padding: 0 6px 2px 6px; }}
QLabel#toolsHelp {{ color: {TEXT}; border: 1px solid {TEXT}; border-radius: 8px; font-size: 7pt; font-weight: 600; }}
QPushButton#updateNow {{ padding: 1px 8px; background: {PANEL}; border-color: {WARN}; color: {TEXT}; }}
QStatusBar QSizeGrip {{ width: 14px; height: 14px; }}
QScrollBar#bigScroll {{ background: {FIELD}; }}

QScrollBar:vertical {{ background: {BG}; width: 11px; margin: 0; }}
QScrollBar:horizontal {{ background: {BG}; height: 11px; margin: 0; }}
QScrollBar::handle {{ background: {SCROLL}; border-radius: 4px; min-height: 30px; min-width: 30px; margin: 2px; }}
QScrollBar::handle:hover {{ background: {ACCENT}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
"""


def _svg_file(name: str) -> str:
    """One of Hias' symbols (gui/svgicons) in the accent colour, as SVG text ("" if missing)."""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "svgicons", name + ".svg")
    try:
        with open(p, encoding="utf-8") as f:
            return f.read().replace("currentColor", ACCENT)
    except OSError:
        return ""


def _rotated(svg: str, degrees: float) -> str:
    """``svg`` turned by ``degrees`` about its middle, in a box that just holds the turned symbol."""
    import math
    import re

    m = re.search(r'viewBox="\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*"', svg)
    start, end = svg.find(">", svg.find("<svg")) + 1, svg.rfind("</svg>")
    if not m or start <= 0 or end < 0:
        return svg
    x, y, w, h = (float(v) for v in m.groups())
    c, s = abs(math.cos(math.radians(degrees))), abs(math.sin(math.radians(degrees)))
    bw, bh = round(w * c + h * s, 3), round(w * s + h * c, 3)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {bw:g} {bh:g}" width="{bw:g}" height="{bh:g}" '
        f'fill="none"><g transform="translate({bw / 2:g} {bh / 2:g}) rotate({degrees:g}) '
        f'translate({-(x + w / 2):g} {-(y + h / 2):g})">{svg[start:end]}</g></svg>'
    )


def _indicator_qss() -> str:
    """Check mark and dot of check boxes/radio buttons, grip and scroll symbols (QSS needs image files for them)."""
    from .. import platform as _platform

    d = os.path.join(tempfile.gettempdir(), f"pdfdruck-theme-{_platform.user_id()}")
    os.makedirs(d, exist_ok=True)
    files = {
        "check.svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path d="M3.2 8.4l3 3 6.6-7" '
        'fill="none" stroke="'
        + ON_ACCENT
        + '" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        "dot.svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><circle cx="8" cy="8" r="3.6" fill="'
        + ON_ACCENT
        + '"/></svg>',
    }
    # Hias' grip and scroll symbols in the accent: separators and window corner (grip), large scroll bars (scroll)
    grip = _svg_file("greifer_fuer_fenster_vergroesserung")
    scroll = _svg_file("scrolling")
    if grip:
        files["grip.svg"] = grip
        files["grip_corner.svg"] = _rotated(grip, -45)
    if scroll:
        files["scroll_v.svg"] = scroll
        files["scroll_h.svg"] = _rotated(scroll, -90)
    for name, svg in files.items():
        with open(os.path.join(d, name), "w", encoding="utf-8") as f:
            f.write(svg)

    def url(name: str) -> str:
        return os.path.join(d, name).replace("\\", "/")  # QSS wants forward slashes, even on Windows

    chk, dot = url("check.svg"), url("dot.svg")
    extra = ""
    if grip:
        extra += f"""
QMainWindow::separator {{ background: {BG}; width: 12px; height: 12px; image: url({url("grip.svg")}); }}
QStatusBar QSizeGrip {{ width: 16px; height: 16px; image: url({url("grip_corner.svg")}); }}
"""
    if scroll:
        extra += f"""
QScrollBar#bigScroll:vertical {{ width: 15px; }}
QScrollBar#bigScroll:horizontal {{ height: 15px; }}
QScrollBar#bigScroll::handle:vertical {{ image: url({url("scroll_v.svg")}); min-height: 52px; }}
QScrollBar#bigScroll::handle:horizontal {{ image: url({url("scroll_h.svg")}); min-width: 52px; }}
"""
    return (
        extra
        + f"""
QCheckBox::indicator:checked, QListView::indicator:checked, QGroupBox::indicator:checked {{
    image: url({chk}); background: {ACCENT}; border-color: {ACCENT}; }}
QRadioButton::indicator:checked {{ image: url({dot}); background: {ACCENT}; border-color: {ACCENT}; }}
QListView::indicator {{ width: 14px; height: 14px; border: 1px solid {BORDER_HOVER}; background: {FIELD}; border-radius: 2px; }}
QCheckBox::indicator:checked:disabled, QRadioButton::indicator:checked:disabled {{ background: {ACCENT_OFF}; border-color: {ACCENT_OFF}; }}
"""
    )


def _scroll_area_of(target):
    area = target.parentWidget()
    while area is not None and not isinstance(area, QAbstractScrollArea):
        area = area.parentWidget()
    return area


def _guarded_wheel(self, ev):
    """Replaces wheelEvent of combo boxes/spin boxes/sliders: never change the value but scroll the
    surroundings (as the event filter did before – only without the cost for all other events).
    """
    global _wheel_hit
    _wheel_hit = True
    area = _scroll_area_of(self)
    if area is not None and area.verticalScrollBar().isVisible():
        QApplication.sendEvent(area.verticalScrollBar(), ev)
        ev.accept()
        return
    ev.ignore()


_wheel_hit = False


class WheelGuard(QObject):
    """The mouse wheel NEVER changes selection fields/spin boxes – it always scrolls the surroundings.
    Values are changed by clicking or via the keyboard.

    Only a fallback now: as a filter on the whole application every single event (painting, layout,
    focus …) ran through Python – tens of thousands of times when opening a tab/window, which caused
    stalls of 0.4–0.5 s. Normally wheelEvent of the three widget kinds is replaced instead (install_wheel_guard).
    """

    TYPES = (QComboBox, QAbstractSpinBox, QSlider)

    def eventFilter(self, obj, ev):
        if ev.type() != QEvent.Type.Wheel:
            return False
        w, target = obj, None
        for _ in range(3):  # also the inner edit fields of spin/combo boxes
            if w is None or not hasattr(w, "parentWidget"):
                break
            if isinstance(w, self.TYPES):
                target = w
                break
            w = w.parentWidget()
        if target is None:
            return False
        area = _scroll_area_of(target)
        if area is not None and area.verticalScrollBar().isVisible():
            QApplication.sendEvent(area.verticalScrollBar(), ev)
        return True


def install_wheel_guard(app) -> bool:
    """Replace wheelEvent of the combo boxes/spin boxes/sliders and check whether Qt really calls the replacement.
    True = it worked (no global filter needed).
    """
    global _wheel_hit
    from PySide6.QtCore import QPoint, QPointF
    from PySide6.QtGui import QWheelEvent

    for cls in WheelGuard.TYPES:
        cls.wheelEvent = _guarded_wheel
    try:
        probe = QComboBox()
        probe.addItems(["a", "b"])
        _wheel_hit = False
        ev = QWheelEvent(
            QPointF(1, 1),
            QPointF(1, 1),
            QPoint(0, 0),
            QPoint(0, -120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        QApplication.sendEvent(probe, ev)
        ok = _wheel_hit and probe.currentIndex() == 0
        probe.deleteLater()
        return ok
    except Exception:  # noqa: BLE001
        return False


_guard = None


def apply(app: QApplication):
    """Apply the dark theme to the application and install the mouse wheel guard."""
    global _guard
    app.setStyle("Fusion")
    pal = QPalette()
    for role, col in [
        (QPalette.ColorRole.Window, BG),
        (QPalette.ColorRole.WindowText, TEXT),
        (QPalette.ColorRole.Base, FIELD),
        (QPalette.ColorRole.AlternateBase, PANEL),
        (QPalette.ColorRole.Text, TEXT),
        (QPalette.ColorRole.Button, BUTTON),
        (QPalette.ColorRole.ButtonText, TEXT),
        (QPalette.ColorRole.Highlight, ACCENT),
        (QPalette.ColorRole.HighlightedText, ON_ACCENT),
        (QPalette.ColorRole.ToolTipBase, TIP_BG),
        (QPalette.ColorRole.ToolTipText, TEXT),
        (QPalette.ColorRole.PlaceholderText, MUTED),
        (QPalette.ColorRole.Link, ACCENT),
    ]:
        pal.setColor(role, QColor(col))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(ICON_OFF))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(ICON_OFF))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(ICON_OFF))
    app.setPalette(pal)
    f = QFont()
    fam = _first_available(UI_FONTS)
    if fam:
        f.setFamily(fam)
    f.setPointSizeF(10)
    app.setFont(f)
    app.setStyleSheet(QSS + _indicator_qss())
    if not install_wheel_guard(app):  # fallback: as a filter for the whole application
        _guard = WheelGuard(app)
        app.installEventFilter(_guard)
