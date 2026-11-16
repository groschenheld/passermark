# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Parts of the 1.19.0 main window at its edges: the tabs at the right edge (Werkzeuge, Plan, Poster), the tools
panel that "Werkzeuge" opens, and the small tool box at the bottom left.

With the own title bar the tabs stand outside the page area, in the transparent margin of the window (tabhost.py);
with the system frame they are placed inside the window. The tool box lies over the page, right of the sidebar,
and folds away with an arrow. Every button only triggers an
action of the main window, so menus, shortcuts and these buttons always do the same.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QToolButton, QVBoxLayout, QWidget

from ..l10n import tr
from . import icons, theme


class RailTab(QToolButton):
    """Vertical tab at the right window edge: text from top to bottom, icon underneath (design sheet: dark box
    with a grey inner frame; open = frame and text in the accent)."""

    W = 48
    ICON = 30
    PAD = 12

    def __init__(self, text: str, icon_name: str, parent=None):
        super().__init__(parent)
        self._text = text
        self._icon = icon_name
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(text)
        self.setAccessibleName(text)
        f = QFont(self.font())
        f.setBold(True)
        f.setPointSizeF(max(f.pointSizeF(), 9.0) * 1.15)
        self._font = f
        tw = QFontMetrics(f).horizontalAdvance(text)
        self.setFixedSize(self.W, tw + self.ICON + 3 * self.PAD + 4)

    def sizeHint(self):
        return QSize(self.width(), self.height())

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        on = self.isChecked()
        hover = self.underMouse()
        p.fillRect(self.rect(), QColor(theme.PANEL))
        inner = QRectF(self.rect()).adjusted(4.5, 4.5, -4.5, -4.5)
        p.setPen(QPen(QColor(theme.ACCENT if (on or hover) else theme.BORDER), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(inner)
        # text, rotated: reads from top to bottom
        p.save()
        p.setFont(self._font)
        fm = p.fontMetrics()
        p.translate(self.width() / 2 - (fm.ascent() - fm.descent()) / 2, self.PAD + 2)
        p.rotate(90)
        p.setPen(QColor(theme.ACCENT_TEXT if on else theme.TEXT))
        p.drawText(0, 0, self._text)
        p.restore()
        size = self.ICON
        pm = icons.pixmap(self._icon, theme.ACCENT_TEXT if (hover and not on) else theme.ICON, size * 2)
        p.drawPixmap(
            QRectF((self.width() - size) / 2, self.height() - size - self.PAD, size, size), pm, QRectF(pm.rect())
        )
        p.end()


def build_rail(window) -> QWidget:
    """The column of tabs at the right edge: Werkzeuge opens the tools panel, Plan and Poster their windows."""
    rail = QWidget()
    rail.setObjectName("rail")
    v = QVBoxLayout(rail)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(8)
    window.tab_tools = RailTab(tr("Werkzeuge"), "tools")
    window.tab_tools.setToolTip(tr("Werkzeuge: Farbe, Beschneiden, Konturen, Variable Daten, Prüfung"))
    window.tab_tools.toggled.connect(lambda on: window.tools_dock.setVisible(on))
    window.tools_dock.visibilityChanged.connect(window.tab_tools.setChecked)
    tab_plan = RailTab(tr("Plan"), "plan")
    tab_plan.setCheckable(False)
    tab_plan.setToolTip(window.a_plan.toolTip() or window.a_plan.text())
    tab_plan.clicked.connect(window.a_plan.trigger)
    tab_poster = RailTab(tr("Poster"), "poster")
    tab_poster.setCheckable(False)
    tab_poster.setToolTip(window.a_poster.toolTip() or window.a_poster.text())
    tab_poster.clicked.connect(window.a_poster.trigger)
    rail.tabs = [window.tab_tools, tab_plan, tab_poster]
    for t in rail.tabs:
        v.addWidget(t, 0, Qt.AlignmentFlag.AlignLeft)
    v.addStretch(1)
    rail.setFixedWidth(RailTab.W)
    return rail


class Dashed(QWidget):
    """A dashed white line across (the separators of the design sheet)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(9)

    def paintEvent(self, _e):
        p = QPainter(self)
        pen = QPen(QColor(theme.TEXT), 1)
        pen.setDashPattern([2.0, 2.0])
        p.setPen(pen)
        y = self.height() // 2 + 0.5
        p.drawLine(0, int(y), self.width(), int(y))
        p.end()


class _ToolsHead(QWidget):
    """Head of the tools panel; when narrow only close button and symbol remain."""

    def resizeEvent(self, e):
        super().resizeEvent(e)
        need = 2 * 28 + self.title.sizeHint().width() + 10 + 26 + 40
        self.title.setVisible(self.width() >= need)


def tools_header(window) -> QWidget:
    """Head of the tools panel: close button, "Werkzeuge" with its symbol, dashed line."""
    head = _ToolsHead()
    head.setObjectName("toolsHead")
    v = QVBoxLayout(head)
    v.setContentsMargins(8, 6, 8, 0)
    v.setSpacing(4)
    row = QHBoxLayout()
    close = QToolButton()
    close.setObjectName("toolsClose")
    close.setIcon(icons.icon_in("win_close", theme.ACCENT_TEXT))
    close.setIconSize(QSize(18, 18))
    close.setFixedSize(28, 28)
    close.setToolTip(tr("Werkzeuge schließen"))
    close.clicked.connect(window.tools_dock.hide)
    title = QLabel(tr("Werkzeuge"))
    f = QFont(title.font())
    f.setBold(True)
    f.setPointSizeF(max(f.pointSizeF(), 9.0) * 1.3)
    title.setFont(f)
    title.setMinimumWidth(1)  # may get narrow – resizeEvent hides it then
    head.title = title
    sym = QLabel()
    sym.setPixmap(_crisp("tools", theme.ICON, 26, head))
    row.addWidget(close)
    row.addStretch(1)
    row.addWidget(title)
    row.addSpacing(10)
    row.addWidget(sym)
    row.addStretch(1)
    row.addSpacing(28)  # as wide as the close button: the title stays in the middle
    v.addLayout(row)
    v.addWidget(Dashed())
    return head


def _crisp(name: str, color: str, size: int, widget):
    """Icon pixmap for the screen of ``widget`` (sharp on HiDPI)."""
    dpr = max(1.0, widget.devicePixelRatioF())
    pm = icons.pixmap(name, color, round(size * dpr))
    pm.setDevicePixelRatio(dpr)
    return pm


def tools_panel(window) -> QWidget:
    """The tools grouped as in the design sheet: heading with "?" (short explanation as tooltip), one wide button
    per tool (text in the middle, icon at the right), dashed lines between them."""
    groups = [
        (
            tr("Farben und Material"),
            tr(
                "Farbmanagement kurz erklärt: Ein ICC-Profil beschreibt, wie ein Drucker auf einem bestimmten Papier "
                "Farben wiedergibt. Passermark rechnet Farben damit um – für den Softproof am Bildschirm (so wird es "
                "gedruckt aussehen), für die CMYK-Umwandlung und für Dateien an die Druckerei."
            ),
            [
                (window.a_manip_cmyk, tr("CMYK-Umwandlung")),
                (window.a_softproof_setup, tr("Softproof einrichten")),
                (window.a_materials, tr("Papiere und Messungen")),
                (window.a_std_profiles, tr("Standardprofile holen")),
                (window.a_press, tr("Für Druckerei ausgeben")),
                (window.a_colorcheck, tr("Farbprüfung")),
            ],
        ),
        (
            tr("Schneiden, Trennen und Konturen"),
            tr(
                "Seiten auf das Endformat beschneiden, Objekte auf eigene Seiten trennen und Schneidekonturen "
                "(CutContour) für den Schneideplotter erzeugen."
            ),
            [
                (window.a_manip_crop, tr("Auf Format beschneiden")),
                (window.a_separate, tr("Objekte trennen")),
                (window.a_cut, tr("CutContour erzeugen")),
            ],
        ),
        (
            tr("Variable Daten"),
            tr(
                "Daten aus einer Tabelle (Namen, Nummern, QR-Codes …) in eine Vorlage einsetzen – z. B. für "
                "Namensschilder, Gutscheine oder Etiketten."
            ),
            [(window.a_vdp, tr("Variable Daten")), (window.a_data, tr("Variable Daten erfassen"))],
        ),
        (
            tr("Dokument und Prüfung"),
            tr(
                "Das Dokument prüfen, die Datei verkleinern, beschädigte PDFs reparieren und optimieren, "
                "mit Passwort schützen."
            ),
            [
                (window.a_preflight, tr("Dokumentprüfung")),
                (window.a_shrink, tr("Datei verkleinern")),
                (window.a_repair, tr("Reparieren, optimieren, Passwort")),
            ],
        ),
    ]
    box = _ToolsPanel()
    box.setObjectName("toolsPanel")
    v = QVBoxLayout(box)
    v.setContentsMargins(12, 4, 12, 10)
    v.setSpacing(4)
    for title, help_text, items in groups:
        row = QHBoxLayout()
        row.setContentsMargins(0, 12, 0, 4)
        head = QLabel(title)
        head.setObjectName("toolsGroup")
        f = QFont(head.font())
        f.setBold(True)
        f.setPointSizeF(max(f.pointSizeF(), 9.0) * 1.15)
        head.setFont(f)
        head.setWordWrap(True)  # narrow: the heading breaks into lines, very narrow: only "?" remains
        head.setAlignment(Qt.AlignmentFlag.AlignCenter)
        head.setToolTip(help_text)
        box.headings.append(head)
        q = QLabel("?")
        q.setObjectName("toolsHelp")
        q.setAlignment(Qt.AlignmentFlag.AlignCenter)
        q.setFixedSize(16, 16)
        q.setToolTip(f"<b>{title}</b><br>{help_text}")
        row.addStretch(1)
        row.addWidget(head)
        row.addWidget(q, 0, Qt.AlignmentFlag.AlignTop)
        row.addStretch(1)
        v.addLayout(row)
        for action, text in items:
            v.addWidget(_ToolButton(action, text))
            v.addWidget(Dashed())
    v.addStretch(1)
    return box


class _ToolsPanel(QWidget):
    """The body of the tools panel; below COMPACT pixels the group headings give way (only "?" stays)."""

    COMPACT = 150

    def __init__(self):
        super().__init__()
        self.headings = []

    def resizeEvent(self, e):
        super().resizeEvent(e)
        wide = self.width() >= self.COMPACT
        for h in self.headings:
            if h.isVisibleTo(self) != wide:
                h.setVisible(wide)


class _ToolButton(QPushButton):
    """A wide button of the tools panel that triggers ``action``: text in the middle, larger icon at the right."""

    ICON = 26

    def __init__(self, action, text: str):
        super().__init__(text)
        self._action = action
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        tip = action.toolTip()
        self.setToolTip(tip if tip and tip.replace("&", "") != text else text)
        self.setMinimumHeight(40)
        self.clicked.connect(action.trigger)
        action.changed.connect(lambda: self.setEnabled(action.isEnabled()))
        self.setEnabled(action.isEnabled())

    def sizeHint(self):
        fm = self.fontMetrics()
        return QSize(fm.horizontalAdvance(self.text()) + 2 * self.ICON + 40, 40)

    def minimumSizeHint(self):
        return QSize(self.ICON + 20, 40)  # narrow: only the symbol (see paintEvent)

    def _text_room(self) -> QRectF:
        n = self.ICON
        return QRectF(n + 10, 2, self.width() - 2 * (n + 10), self.height() - 4)

    def _text_fits(self, f: QFont) -> bool:
        """Does the text fit next to the symbol – in one line or broken into two?"""
        fm = QFontMetrics(f)
        room = self._text_room()
        if room.width() <= 0 or any(fm.horizontalAdvance(w) > room.width() for w in self.text().split()):
            return False
        used = fm.boundingRect(room.toRect(), int(Qt.TextFlag.TextWordWrap), self.text())
        return used.height() <= room.height()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        on = self.isEnabled()
        hover = on and self.underMouse()
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setBrush(QColor(theme.BUTTON))
        p.setPen(QPen(QColor(theme.ACCENT if hover else theme.BORDER), 1))
        p.drawRect(r)
        n = self.ICON
        pm = self._action.icon().pixmap(QSize(n, n), self.devicePixelRatioF(), mode=_icon_mode(on, hover))
        f = QFont(self.font())
        f.setBold(True)
        with_text = self._text_fits(f)
        x = self.width() - n - 10 if with_text else (self.width() - n) / 2  # too narrow: symbol in the middle
        p.drawPixmap(QRectF(x, (self.height() - n) / 2, n, n), pm, QRectF(pm.rect()))
        if with_text:
            p.setFont(f)
            p.setPen(QColor(theme.TEXT if on else theme.ICON_OFF))
            p.drawText(
                self._text_room(), int(Qt.AlignmentFlag.AlignCenter) | int(Qt.TextFlag.TextWordWrap), self.text()
            )
        p.end()


def _icon_mode(enabled: bool, hover: bool):
    if not enabled:
        return QIcon.Mode.Disabled
    return QIcon.Mode.Active if hover else QIcon.Mode.Normal


class _FramedBox(QFrame):
    """Dark box with a grey inner frame (tool box and tabs look alike)."""

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.PANEL))
        p.setPen(QPen(QColor(theme.BORDER), 1))
        p.drawRect(QRectF(self.rect()).adjusted(4.5, 4.5, -4.5, -4.5))
        p.end()


class ToolboxOverlay(QWidget):
    """The tool box over the page, right of the sidebar (bottom left of the page area): a box with merge, split
    and edit and an arrow at its side that folds it away to a narrow strip. Open/closed is remembered."""

    SETTING = "toolbox_open"
    MARGIN = 8

    def __init__(self, window, parent: QWidget, view: QWidget):
        super().__init__(parent)
        self.setObjectName("toolboxOverlay")
        self._view = view
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.box = toolbox(window)
        self.arrow = QToolButton()
        self.arrow.setObjectName("toolboxArrow")
        self.arrow.setCursor(Qt.CursorShape.PointingHandCursor)
        self.arrow.setFixedWidth(18)
        self.arrow.setIconSize(QSize(12, 12))
        self.arrow.clicked.connect(lambda: self.set_open(not self.box.isVisible()))
        lay.addWidget(self.box)
        lay.addWidget(self.arrow)
        from .. import l10n

        self.set_open(l10n.load_settings().get(self.SETTING, True) is not False, remember=False)
        view.installEventFilter(self)
        if hasattr(view, "viewport"):
            view.viewport().installEventFilter(self)

    def set_open(self, on: bool, remember: bool = True):
        """Show the box (arrow points left: fold away) or only the strip (arrow points right: open)."""
        self.box.setVisible(on)
        self.arrow.setIcon(icons.icon_in("left" if on else "right", theme.ACCENT_TEXT))
        self.arrow.setToolTip(tr("Werkzeugbox einklappen") if on else tr("Werkzeugbox ausklappen"))
        self.arrow.setFixedHeight(self.box.sizeHint().height() if on else 56)
        if remember:
            from .. import l10n

            st = l10n.load_settings()
            st[self.SETTING] = on
            l10n.save_settings(st)
        self.place()

    def place(self):
        """Bottom left of the visible page area (above a horizontal scroll bar)."""
        self.adjustSize()
        vp = self._view.viewport() if hasattr(self._view, "viewport") else self._view
        corner = vp.mapTo(self.parentWidget(), vp.rect().bottomLeft())
        self.move(corner.x(), corner.y() - self.height() - self.MARGIN + 1)
        self.raise_()

    def eventFilter(self, obj, ev):
        if ev.type() in (QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.Show):
            self.place()
        return False


def toolbox(window) -> QWidget:
    """The small box (design sheet): merge, split, edit – symbol over a short label."""
    box = _FramedBox()
    box.setObjectName("toolbox")
    v = QVBoxLayout(box)
    v.setContentsMargins(7, 10, 7, 10)
    v.setSpacing(8)
    for action, text in (
        (window.a_merge, tr("Zusammenführen")),
        (window.a_split, tr("Teilen")),
        (window.a_edit, tr("Bearbeiten")),
    ):
        b = QToolButton()
        b.setIcon(action.icon())
        b.setText(text)
        b.setToolTip(action.toolTip() or action.text())  # the full name ("Seiten teilen (halbieren, Raster)")
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        b.setIconSize(QSize(26, 26))
        b.setAutoRaise(True)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        f = QFont(b.font())
        f.setItalic(True)
        f.setPointSizeF(max(f.pointSizeF() * 0.8, 7.0))
        b.setFont(f)
        b.clicked.connect(action.trigger)
        action.changed.connect(lambda b=b, a=action: b.setEnabled(a.isEnabled()))
        b.setEnabled(action.isEnabled())
        v.addWidget(b, 0, Qt.AlignmentFlag.AlignHCenter)
    return box
