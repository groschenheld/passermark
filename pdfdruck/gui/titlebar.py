# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Own title bar (1.19.0 design): settings gear, menu, "PasserMark" in the middle, window buttons – one black row.

The window is then frameless; ``EdgeGrips`` lets it be resized at its edges, the title bar moves it (the system
does both: ``startSystemMove``/``startSystemResize``, so snapping and Wayland work). It can be switched off in
File → Settings ("Eigene Titelleiste"): then the system frame and the normal menu bar are used again – for
desktops where frameless windows do not behave.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QToolButton, QWidget

from ..l10n import tr
from . import icons, theme

SETTING = "custom_titlebar"  # user settings: own title bar on (default) or the system frame
HEIGHT = 34


def wanted() -> bool:
    """Should windows get the own title bar (user setting, on by default)?"""
    from .. import l10n

    return l10n.load_settings().get(SETTING, True) is not False


class TitleBar(QWidget):
    """The black top row: gear, menu bar, centred word mark, window buttons. Acts on its top-level window."""

    def __init__(self, menubar, on_settings, parent=None):
        super().__init__(parent)
        self.setObjectName("titleBar")
        self.setFixedHeight(HEIGHT)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"QWidget#titleBar {{ background: {theme.BG}; }}"
            f"QWidget#titleBar QMenuBar {{ background: transparent; border: none; }}"
            f"QToolButton#winBtn {{ border: none; border-radius: 3px; padding: 3px; }}"
            f"QToolButton#winBtn:hover {{ background: {theme.ACCENT_SOFT}; }}"
            f"QToolButton#winClose:hover {{ background: {theme.ERROR}; }}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 0, 6, 0)
        lay.setSpacing(4)
        gear = QToolButton()
        gear.setObjectName("winBtn")
        gear.setIcon(icons.icon("settings"))
        gear.setToolTip(tr("Einstellungen"))
        gear.clicked.connect(on_settings)
        lay.addWidget(gear)
        menubar.setNativeMenuBar(False)
        menubar.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        lay.addWidget(menubar)
        lay.addStretch(1)
        self.doc_label = QLabel()  # document name, quietly at the right of the middle
        self.doc_label.setStyleSheet(f"color: {theme.MUTED};")
        lay.addWidget(self.doc_label)
        self.btns = {}
        for key, tip, name in (
            ("min", tr("Minimieren"), "win_min"),
            ("max", tr("Maximieren"), "win_max"),
            ("close", tr("Schließen"), "win_close"),
        ):
            b = QToolButton()
            b.setObjectName("winClose" if key == "close" else "winBtn")
            if key == "close":
                b.setStyleSheet(
                    "QToolButton { border: none; border-radius: 3px; padding: 3px; }"
                    f"QToolButton:hover {{ background: {theme.ERROR}; }}"
                )
            b.setIcon(icons.icon_in(name, theme.ACCENT_TEXT))
            b.setToolTip(tip)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            lay.addWidget(b)
            self.btns[key] = b
        self.btns["min"].clicked.connect(lambda: self.window().showMinimized())
        self.btns["max"].clicked.connect(self.toggle_maximized)
        self.btns["close"].clicked.connect(lambda: self.window().close())
        # word mark in the exact middle of the bar, independent of the menu width; mouse goes through it
        self.mark = QLabel(self)
        self.mark.setTextFormat(Qt.TextFormat.RichText)
        self.mark.setText(
            f'<span style="color:{theme.TEXT}">Passer</span><span style="color:{theme.ACCENT_TEXT}">Mark</span>'
        )
        f = self.mark.font()
        f.setPointSizeF(f.pointSizeF() * 1.35)
        self.mark.setFont(f)
        self.mark.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def set_document(self, name: str):
        """Show the name of the open document next to the window buttons."""
        self.doc_label.setText(name)

    def toggle_maximized(self):
        """Maximise or restore the window."""
        w = self.window()
        w.showNormal() if w.isMaximized() else w.showMaximized()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.mark.adjustSize()
        self.mark.move((self.width() - self.mark.width()) // 2, (self.height() - self.mark.height()) // 2)

    def mousePressEvent(self, e):
        """Drag on free space of the bar: the system moves the window (snapping, Wayland)."""
        if e.button() == Qt.MouseButton.LeftButton:
            h = self.window().windowHandle()
            if h is not None and h.startSystemMove():
                e.accept()
                return
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.toggle_maximized()
            e.accept()
            return
        super().mouseDoubleClickEvent(e)


class EdgeGrips(QObject):
    """Resize a frameless window at its edges and corners (``GRIP`` pixels wide; not while maximised)."""

    GRIP = 6

    def __init__(self, window: QWidget, insets=None):
        super().__init__(window)
        self.win = window
        self.insets = insets or (lambda: (0, 0))  # transparent margins left/right: the grips sit inside them
        self.grips = []
        E = Qt.Edge
        spec = (
            (E.LeftEdge, Qt.CursorShape.SizeHorCursor),
            (E.RightEdge, Qt.CursorShape.SizeHorCursor),
            (E.TopEdge, Qt.CursorShape.SizeVerCursor),
            (E.BottomEdge, Qt.CursorShape.SizeVerCursor),
            (E.TopEdge | E.LeftEdge, Qt.CursorShape.SizeFDiagCursor),
            (E.BottomEdge | E.RightEdge, Qt.CursorShape.SizeFDiagCursor),
            (E.TopEdge | E.RightEdge, Qt.CursorShape.SizeBDiagCursor),
            (E.BottomEdge | E.LeftEdge, Qt.CursorShape.SizeBDiagCursor),
        )
        for edges, cursor in spec:
            g = _Grip(window, edges)
            g.setCursor(QCursor(cursor))
            self.grips.append(g)
        window.installEventFilter(self)
        self.place()

    def place(self):
        """Put the grips on the edges (again) and on top of everything."""
        h, g = self.win.height(), self.GRIP
        x0, right = self.insets()
        w = self.win.width() - x0 - right
        E = Qt.Edge
        show = not (self.win.isMaximized() or self.win.isFullScreen())
        for grip in self.grips:
            e = grip.edges
            if e == E.LeftEdge:
                grip.setGeometry(x0, g, g, h - 2 * g)
            elif e == E.RightEdge:
                grip.setGeometry(x0 + w - g, g, g, h - 2 * g)
            elif e == E.TopEdge:
                grip.setGeometry(x0 + g, 0, w - 2 * g, g)
            elif e == E.BottomEdge:
                grip.setGeometry(x0 + g, h - g, w - 2 * g, g)
            else:
                x = x0 if e & E.LeftEdge else x0 + w - g
                y = 0 if e & E.TopEdge else h - g
                grip.setGeometry(x, y, g, g)
            grip.setVisible(show)
            grip.raise_()

    def eventFilter(self, obj, ev):
        if obj is self.win and ev.type() in (QEvent.Type.Resize, QEvent.Type.WindowStateChange, QEvent.Type.Show):
            self.place()
        return False


class _Grip(QWidget):
    """One invisible strip at the edge: pressing it lets the system resize the window."""

    def __init__(self, window, edges):
        super().__init__(window)
        self.edges = edges
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            h = self.window().windowHandle()
            if h is not None:
                h.startSystemResize(self.edges)
                e.accept()
                return
        super().mousePressEvent(e)


def make_frameless(window: QWidget, insets=None):
    """Switch a top-level window to the own frame (frameless + edge grips) if the user wants that.
    ``insets``: function -> (left, right) width of transparent margins at the sides."""
    if not wanted():
        return None
    window.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
    return EdgeGrips(window, insets)
