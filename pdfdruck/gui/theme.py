# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Dunkles Design mit gelbem Akzent („Konsole“, aber sachlich) + globaler Mausrad-Schutz."""
from __future__ import annotations

import os
import tempfile

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import (QAbstractScrollArea, QAbstractSpinBox, QApplication, QComboBox,
                               QSlider)

BG = "#15171a"          # Fenster
PANEL = "#1e2124"       # Leisten, Gruppen
FIELD = "#0e1012"       # Eingabefelder
VIEW = "#2a2d31"        # Hintergrund hinter den Seiten
BORDER = "#5a6068"      # Rahmen (bewusst hell genug für Kontrast)
TEXT = "#f3f4f5"
MUTED = "#a9afb6"
ACCENT = "#ffc62b"      # Gelb
ACCENT_SOFT = "rgba(255, 198, 43, 0.20)"
ERROR = "#ff6b6b"
ICON = "#d9dde1"
ICON_OFF = "#5c6168"

UI_FONTS = ["IBM Plex Sans", "Inter", "Segoe UI Variable Text", "Segoe UI", "Ubuntu", "Noto Sans", "DejaVu Sans"]
MONO_FONTS = ["IBM Plex Mono", "JetBrains Mono", "Cascadia Mono", "Consolas", "Ubuntu Mono", "DejaVu Sans Mono"]


def _first_available(names):
    fams = set(QFontDatabase.families())
    return next((n for n in names if n in fams), None)


def mono_font(size: float = 9.5) -> QFont:
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
QWidget {{ selection-background-color: {ACCENT}; selection-color: #000; }}
QToolTip {{ background: #000; color: {TEXT}; border: 1px solid {ACCENT}; padding: 4px; }}

QMenuBar {{ background: {PANEL}; border-bottom: 1px solid {BORDER}; }}
QMenuBar::item {{ padding: 4px 10px; background: transparent; }}
QMenuBar::item:selected {{ background: {ACCENT_SOFT}; color: {ACCENT}; }}
QMenu {{ background: {PANEL}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 5px 24px 5px 22px; }}
QMenu::item:selected {{ background: {ACCENT_SOFT}; color: {ACCENT}; }}
QMenu::item:disabled {{ color: {ICON_OFF}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}

QToolBar {{ background: {PANEL}; border: none; border-bottom: 1px solid {BORDER}; spacing: 3px; padding: 3px; }}
QToolBar::separator {{ background: {BORDER}; width: 1px; margin: 4px 6px; }}
QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 4px; padding: 4px; }}
QToolButton:hover {{ border-color: {ACCENT}; background: {ACCENT_SOFT}; }}
QToolButton:pressed, QToolButton:checked {{ background: {ACCENT_SOFT}; border-color: {ACCENT}; color: {ACCENT}; }}
QToolButton:disabled {{ color: {ICON_OFF}; }}

QPushButton {{ background: #2a2e33; border: 1px solid {BORDER}; border-radius: 4px; padding: 5px 14px; }}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:pressed, QPushButton:checked {{ background: {ACCENT}; color: #000; border-color: {ACCENT}; }}
QPushButton:default {{ border: 2px solid {ACCENT}; }}
QPushButton:disabled {{ color: {ICON_OFF}; border-color: #34383d; }}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit {{
    background: {FIELD}; border: 1px solid {BORDER}; border-radius: 3px; padding: 4px 6px; min-height: 18px; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus {{
    border: 1px solid {ACCENT}; }}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover {{ border-color: #8a9099; }}
QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QLineEdit:disabled {{
    color: {ICON_OFF}; border-color: #2e3236; }}
QComboBox QAbstractItemView {{ background: {FIELD}; border: 1px solid {ACCENT}; outline: none;
    selection-background-color: {ACCENT}; selection-color: #000; }}

QGroupBox {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 5px; margin-top: 14px; padding-top: 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {ACCENT}; font-weight: 600; }}

QCheckBox::indicator, QRadioButton::indicator {{ width: 14px; height: 14px; border: 1px solid #8a9099; background: {FIELD}; }}
QCheckBox::indicator {{ border-radius: 2px; }}
QRadioButton::indicator {{ border-radius: 7px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox:disabled, QRadioButton:disabled {{ color: {ICON_OFF}; }}

QTabWidget::pane {{ border: 1px solid {BORDER}; top: -1px; background: {BG}; }}
QTabBar::tab {{ background: {PANEL}; border: 1px solid {BORDER}; padding: 6px 14px; margin-right: 2px; }}
QTabBar::tab:selected {{ border-bottom: 2px solid {ACCENT}; color: {ACCENT}; }}
QTabBar::tab:hover {{ color: {ACCENT}; }}

QDockWidget {{ titlebar-close-icon: none; }}
QDockWidget::title {{ background: {PANEL}; padding: 5px; border-bottom: 1px solid {BORDER}; }}
QStatusBar {{ background: {PANEL}; border-top: 1px solid {BORDER}; }}
QStatusBar QLabel {{ color: {TEXT}; }}

QListWidget {{ background: {FIELD}; border: 1px solid {BORDER}; outline: none; }}
QListWidget::item:selected {{ background: {ACCENT_SOFT}; color: {ACCENT}; }}
QScrollArea {{ border: none; }}

QScrollBar:vertical {{ background: {BG}; width: 11px; margin: 0; }}
QScrollBar:horizontal {{ background: {BG}; height: 11px; margin: 0; }}
QScrollBar::handle {{ background: #4a5057; border-radius: 4px; min-height: 30px; min-width: 30px; margin: 2px; }}
QScrollBar::handle:hover {{ background: {ACCENT}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
"""


def _indicator_qss() -> str:
    """Schwarzes Häkchen bzw. Punkt auf gelbem Grund (QSS braucht dafür Bilddateien)."""
    from .. import platform as _platform
    d = os.path.join(tempfile.gettempdir(), f"pdfdruck-theme-{_platform.user_id()}")
    os.makedirs(d, exist_ok=True)
    files = {
        "check.svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path d="M3.2 8.4l3 3 6.6-7" '
                     'fill="none" stroke="#000" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        "dot.svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><circle cx="8" cy="8" r="3.6" fill="#000"/></svg>',
    }
    for name, svg in files.items():
        with open(os.path.join(d, name), "w") as f:
            f.write(svg)
    chk = os.path.join(d, "check.svg").replace("\\", "/")      # QSS will Schrägstriche, auch unter Windows
    dot = os.path.join(d, "dot.svg").replace("\\", "/")
    return f"""
QCheckBox::indicator:checked, QListView::indicator:checked, QGroupBox::indicator:checked {{
    image: url({chk}); background: {ACCENT}; border-color: {ACCENT}; }}
QRadioButton::indicator:checked {{ image: url({dot}); background: {ACCENT}; border-color: {ACCENT}; }}
QListView::indicator {{ width: 14px; height: 14px; border: 1px solid #8a9099; background: {FIELD}; border-radius: 2px; }}
QCheckBox::indicator:checked:disabled, QRadioButton::indicator:checked:disabled {{ background: #6b5a1f; border-color: #6b5a1f; }}
"""


class WheelGuard(QObject):
    """Mausrad verändert NIE Auswahlfelder/Zahlenfelder – es scrollt immer die Umgebung.
    Werte ändert man per Klick bzw. Tastatur."""

    TYPES = (QComboBox, QAbstractSpinBox, QSlider)

    def eventFilter(self, obj, ev):
        if ev.type() != QEvent.Type.Wheel:
            return False
        w, target = obj, None
        for _ in range(3):                       # auch innere Editfelder von Spin-/Comboboxen
            if w is None or not hasattr(w, "parentWidget"):
                break
            if isinstance(w, self.TYPES):
                target = w
                break
            w = w.parentWidget()
        if target is None:
            return False
        area = target.parentWidget()
        while area is not None and not isinstance(area, QAbstractScrollArea):
            area = area.parentWidget()
        if area is not None and area.verticalScrollBar().isVisible():
            QApplication.sendEvent(area.verticalScrollBar(), ev)
        return True


_guard = None


def apply(app: QApplication):
    global _guard
    app.setStyle("Fusion")
    pal = QPalette()
    for role, col in [(QPalette.ColorRole.Window, BG), (QPalette.ColorRole.WindowText, TEXT),
                      (QPalette.ColorRole.Base, FIELD), (QPalette.ColorRole.AlternateBase, PANEL),
                      (QPalette.ColorRole.Text, TEXT), (QPalette.ColorRole.Button, "#2a2e33"),
                      (QPalette.ColorRole.ButtonText, TEXT), (QPalette.ColorRole.Highlight, ACCENT),
                      (QPalette.ColorRole.HighlightedText, "#000000"), (QPalette.ColorRole.ToolTipBase, "#000000"),
                      (QPalette.ColorRole.ToolTipText, TEXT), (QPalette.ColorRole.PlaceholderText, MUTED),
                      (QPalette.ColorRole.Link, ACCENT)]:
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
    _guard = WheelGuard(app)
    app.installEventFilter(_guard)
