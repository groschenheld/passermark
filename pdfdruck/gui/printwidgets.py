# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Widgets of the print dialog: page stack, sheet preview, side tab and the helper that keeps the dialog responsive while sending."""

from __future__ import annotations

import os

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import layout
from ..l10n import tr
from . import theme


class PageBox(QWidget):
    """Instead of QStackedWidget: only the visible page is in the layout — the group
    adapts its height exactly in EVERY mode (no empty space, no huge reserve).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pages: list[QWidget] = []
        self._idx = -1
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._lay = lay

    def addWidget(self, w: QWidget):
        """Add a page (hidden until it is made current)."""
        self._pages.append(w)
        self._lay.addWidget(w)
        w.hide()
        if self._idx < 0:
            self.setCurrentIndex(0)

    def count(self) -> int:
        return len(self._pages)

    def currentIndex(self) -> int:
        """Index of the visible page."""
        return self._idx

    def currentWidget(self):
        """The visible page, or None."""
        return self._pages[self._idx] if 0 <= self._idx < len(self._pages) else None

    def setCurrentIndex(self, i: int):
        """Show page ``i`` and hide the previous one."""
        if i == self._idx or not (0 <= i < len(self._pages)):
            return
        if 0 <= self._idx < len(self._pages):
            self._pages[self._idx].hide()
        self._idx = i
        self._pages[i].show()


class Preview(QWidget):
    """Shows an imposed sheet in reading direction + the printable area.
    With duplex also the back side – left/right/below, depending on the flip edge.
    """

    def __init__(self):
        super().__init__()
        self.setMinimumSize(380, 460)
        self.pixmap = None
        self.back = None  # back side (pixmap) or None
        self.back_side = None  # "left" | "right" | "below" | "above"
        self.sheet = None
        self.landscape = False

    def set_content(self, pixmap, sheet, landscape, back=None, back_side=None):
        """Set the sheet image to show, with its sheet, orientation and optional back side."""
        self.pixmap, self.sheet, self.landscape = pixmap, sheet, landscape
        self.back, self.back_side = back, back_side
        self.update()

    def _rects(self):
        """Rechtecke (vorne, hinten|None) in Vorschaukoordinaten, gemeinsam skaliert."""
        if not self.sheet:
            return None, None
        w, h = self.sheet.width, self.sheet.height
        if self.landscape:
            w, h = h, w
        m, gap, lab = 16, 10, 14
        pair = self.back is not None and self.back_side in ("left", "right", "below", "above")
        nx = 2 if pair and self.back_side in ("left", "right") else 1
        ny = 2 if pair and self.back_side in ("below", "above") else 1
        s = min(
            (self.width() - 2 * m) / max(1.0, w * nx + gap * (nx - 1)),
            (self.height() - 2 * m - lab) / max(1.0, h * ny + gap * (ny - 1)),
        )
        pw, ph = w * s, h * s
        x0 = (self.width() - (pw * nx + gap * (nx - 1))) / 2
        y0 = lab + (self.height() - lab - (ph * ny + gap * (ny - 1))) / 2
        front = QRectF(x0, y0, pw, ph)
        back = None
        if pair:
            bx = x0 + (pw + gap if self.back_side == "right" else -(pw + gap) if self.back_side == "left" else 0)
            by = y0 + (ph + gap if self.back_side == "below" else -(ph + gap) if self.back_side == "above" else 0)
            back = QRectF(bx, by, pw, ph)
        return front, back

    def _draw_sheet(self, p, r, pixmap, label):
        p.fillRect(r.translated(3, 3), QColor(0, 0, 0, 120))
        p.fillRect(r, Qt.GlobalColor.white)
        if pixmap is not None:
            p.drawPixmap(r, pixmap, QRectF(pixmap.rect()))
        # printable area (dashed)
        LW, LH, (x, y, w, h) = layout._logical(self.sheet, self.landscape)
        s = r.width() / LW
        pen = QPen(QColor(theme.ACCENT), 1, Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.drawRect(QRectF(r.left() + x * s, r.top() + (LH - y - h) * s, w * s, h * s))
        p.setPen(QColor(theme.BORDER))
        p.drawRect(r)
        p.setPen(QColor(theme.MUTED))
        p.drawText(int(r.left()), int(r.top()) - 4, label)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.VIEW))
        if not self.sheet:
            return
        front, back = self._rects()
        self._draw_sheet(p, front, self.pixmap, tr("Vorderseite"))
        if back is not None:
            self._draw_sheet(p, back, self.back, tr("Rückseite"))


class SideTab(QPushButton):
    """Vertical tab at the left edge of the dialog (yellow, text from bottom to top, arrow for opening).
    Opens/closes an associated window; the arrow shows whether it is open, the dot
    whether the function is active.
    """

    W = 30

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._text = text
        self.window_fn = lambda: None  # -> the associated window (for the open state)
        self.active_fn = lambda: False  # -> function switched on?
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(self.W)
        fm = self.fontMetrics()
        self.setFixedHeight(fm.horizontalAdvance(text) + 2 * self.W + 24)
        self.setAccessibleName(text)

    def watch(self, w):
        """Follow show/hide events of the window this tab belongs to."""
        w.installEventFilter(self)

    def eventFilter(self, obj, ev):
        from PySide6.QtCore import QEvent

        if ev.type() in (QEvent.Type.Show, QEvent.Type.Hide, QEvent.Type.WindowStateChange):
            self.update()
        return False

    def _open(self) -> bool:
        w = self.window_fn()
        return bool(w is not None and w.isVisible() and not w.isMinimized())

    def paintEvent(self, _e):
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QPainterPath, QPolygonF

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        bg = QColor(theme.ACCENT)
        if self.isDown() or self._open():
            bg = bg.darker(118)
        elif self.underMouse():
            bg = bg.lighter(110)
        # rounded on the left, flush with the dialog on the right
        rad = 7.0
        path = QPainterPath()
        path.moveTo(r.right(), r.top())
        path.lineTo(r.left() + rad, r.top())
        path.quadTo(r.left(), r.top(), r.left(), r.top() + rad)
        path.lineTo(r.left(), r.bottom() - rad)
        path.quadTo(r.left(), r.bottom(), r.left() + rad, r.bottom())
        path.lineTo(r.right(), r.bottom())
        path.closeSubpath()
        p.fillPath(path, bg)
        ink = QColor(theme.PAPER_INK)
        # arrow at the top: ◀ = open (the window opens to the left), ▶ = close
        cx, cy, a = r.center().x(), r.top() + self.W / 2 + 2, 5.5
        pts = (
            [QPointF(cx + a * 0.6, cy - a), QPointF(cx - a * 0.6, cy), QPointF(cx + a * 0.6, cy + a)]
            if not self._open()
            else [QPointF(cx - a * 0.6, cy - a), QPointF(cx + a * 0.6, cy), QPointF(cx - a * 0.6, cy + a)]
        )
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(ink)
        p.drawPolygon(QPolygonF(pts))
        # text from bottom to top
        p.save()
        p.translate(r.center().x(), r.center().y() + self.W / 2 - 4)
        p.rotate(-90)
        f = p.font()
        f.setBold(True)
        p.setFont(f)
        p.setPen(ink)
        h = self.height() - self.W - 20
        p.drawText(QRectF(-h / 2, -self.W / 2, h, self.W), int(Qt.AlignmentFlag.AlignCenter), self._text)
        p.restore()
        # active: dot at the bottom
        if self.active_fn():
            p.setBrush(ink)
            p.drawEllipse(QPointF(cx, r.bottom() - 10), 3.5, 3.5)
        if self.hasFocus():
            p.setPen(QPen(ink, 1, Qt.PenStyle.DotLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(r.adjusted(3, 3, -3, -3))
        p.end()

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)


class _print_pump:
    """Windows printing rasterises page by page in the main window (2–6 s for large sheets). In between the window
    may repaint and the heartbeat keeps running – input stays blocked until the end.
    """

    def __init__(self):
        self._mod = None
        if os.name != "nt":
            return
        try:
            from PySide6.QtCore import QEventLoop

            from .. import printers_win

            flags = QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
            printers_win.PUMP = lambda: QApplication.processEvents(flags)
            self._mod = printers_win
        except Exception:  # noqa: BLE001 – without the pump it prints as before
            self._mod = None

    def close(self):
        """Remove the hook again."""
        if self._mod is not None:
            self._mod.PUMP = None
            self._mod = None
