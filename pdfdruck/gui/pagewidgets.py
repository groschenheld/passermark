# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Small widgets of the document view: one page, the rulers, smooth scrolling and the page number field."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QLineEdit,
    QWidget,
)

from . import theme

log = logging.getLogger(__name__)


class _Smoother(QObject):
    """Clean downscaling of the page image in a background thread. When zooming, a coarse scale is shown at once
    (fractions of a second) and the clean image follows shortly – a large page image never blocks the
    window this way (QImage.scaled releases the Python lock). Per page only the newest request counts.
    """

    done = Signal(object, object, object)  # page, key, QImage

    _inst = None

    @classmethod
    def get(cls):
        """The shared instance (created on first use)."""
        if cls._inst is None:
            cls._inst = _Smoother()
        return cls._inst

    def __init__(self):
        super().__init__()
        import threading

        self._jobs: dict = {}
        self._cv = threading.Condition()
        # queued: the result is created in the worker thread, but QPixmap and repainting belong to the main thread
        self.done.connect(self._deliver, Qt.ConnectionType.QueuedConnection)
        threading.Thread(target=self._run, daemon=True, name="passermark-smooth").start()

    def request(self, widget, key, img, tw, th):
        """Ask for a cleanly scaled version of ``img`` for ``widget``; replaces an older request for it."""
        with self._cv:
            self._jobs[id(widget)] = (widget, key, img, tw, th)
            self._cv.notify()

    def _run(self):
        while True:
            with self._cv:
                while not self._jobs:
                    self._cv.wait()
                _k, job = self._jobs.popitem()
            widget, key, img, tw, th = job
            try:
                out = img.scaled(
                    tw, th, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
            except Exception:
                log.warning("Seitenbild nicht geglättet", exc_info=True)
                continue
            self.done.emit(widget, key, out)

    def _deliver(self, widget, key, img):
        try:
            widget.smooth_ready(key, img)
        except RuntimeError:  # the page is gone in the meantime
            pass


class PageWidget(QWidget):
    """One page in the view: holds its rendered image and paints it with overlays."""

    def __init__(self, index: int, view=None):
        super().__init__()
        self.index = index
        # Page image: rendered once per page (about twice the view size); zoom levels and the thumbnail
        # are only scaled from it – photos are not decoded again at every zoom step
        self.master = None  # QImage (device pixels), whole page, with the view rotation
        self.mkey = None  # (scale, rotation) of the page image
        self.mstale = False  # the page was edited: show the old image until the new one is there
        # zooming far beyond the page image: only the visible section, sharp
        self.tile = None  # QImage
        self.tile_rect = None  # QRectF in Widget-Koordinaten
        self.tkey = None  # (scale, rotation)
        self._scaled = None  # page image scaled to the widget size (once per size)
        self._skey = None
        self.view = view
        self.setMouseTracking(True)

    def drop(self, tile_only: bool = False):
        """Forget the rendered images of the page (``tile_only``: only the zoomed section)."""
        self.tile, self.tile_rect, self.tkey = None, None, None
        if not tile_only:
            self.master, self.mkey, self.mstale = None, None, False
            self._scaled, self._skey = None, None

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect().adjusted(3, 3, 3, 3), QColor(0, 0, 0, 60))  # shadow
        if self.master is not None and self._enlarged():
            # zoomed beyond the page image: no enlarged copy (that would be the whole page at full zoom size);
            # Qt scales only the visible part while painting, the sharp section is drawn on top anyway
            self._scaled, self._skey = None, None
            p.save()
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.drawImage(QRectF(0, 0, self.width(), self.height()), self.master)
            p.restore()
        elif self.master is not None:
            dpr = self.devicePixelRatioF()
            tw, th = max(1, round(self.width() * dpr)), max(1, round(self.height() * dpr))
            key = (tw, th, self.master.cacheKey())
            if self._skey != key:
                img = self.master
                if (img.width(), img.height()) != (tw, th):
                    if img.width() * img.height() <= 2_000_000:
                        img = img.scaled(
                            tw, th, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
                        )
                    else:  # large: coarse at once, the clean one comes from the background
                        _Smoother.get().request(self, key, img, tw, th)
                        img = img.scaled(
                            tw, th, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation
                        )
                pm = QPixmap.fromImage(img)
                pm.setDevicePixelRatio(dpr)
                self._scaled, self._skey = pm, key
            p.drawPixmap(0, 0, self._scaled)
        else:
            p.fillRect(self.rect(), Qt.GlobalColor.white)
        if self.tile is not None and self.view is not None and self.tkey == self.view.tile_key(self):
            p.drawImage(self.tile_rect, self.tile)
        if self.view is not None:
            self.view.paint_overlay(self, p)

    def _enlarged(self) -> bool:
        """Is the page shown larger than its page image (more device pixels than the image has)?"""
        dpr = self.devicePixelRatioF()
        return self.width() * dpr * self.height() * dpr > self.master.width() * self.master.height() * 1.01

    def smooth_ready(self, key, img):
        """Cleanly downscaled page image from the background (main thread) – accept only if it still fits."""
        if key != self._skey or self.master is None:
            return
        pm = QPixmap.fromImage(img)
        pm.setDevicePixelRatio(self.devicePixelRatioF())
        self._scaled = pm
        self.update()

    # mouse -> view (text selection or edit mode)
    def mousePressEvent(self, e):
        if self.view is not None and e.button() == Qt.MouseButton.LeftButton:
            self.view.mouse_press(self, e)
        else:
            super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self.view is not None:
            self.view.mouse_move(self, e)

    def mouseReleaseEvent(self, e):
        if self.view is not None:
            self.view.mouse_release(self, e)

    def mouseDoubleClickEvent(self, e):
        if self.view is not None and e.button() == Qt.MouseButton.LeftButton:
            self.view.mouse_double(self, e)


class Ruler(QWidget):
    """Ruler in mm at the edge of the page view; origin = top left corner of the current page.
    It stays put while scrolling, and the scale follows (zoom, page, rotation).
    """

    SIZE = 22

    def __init__(self, view, horizontal: bool):
        super().__init__()
        self.view, self.horizontal = view, horizontal
        self.cursor_px = None  # mouse position (screen, global) for the selection stroke
        if horizontal:
            self.setFixedHeight(self.SIZE)
        else:
            self.setFixedWidth(self.SIZE)

    def paintEvent(self, _):
        from .. import measure as ms

        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.PANEL))
        geo = self.view.ruler_geometry()
        if geo is None:
            return
        origin_vp, ppm = geo  # page corner (viewport pixels), pixels per mm
        g = self.view.viewport().mapToGlobal(origin_vp)
        o = self.mapFromGlobal(g)
        o0 = o.x() if self.horizontal else o.y()
        length = self.width() if self.horizontal else self.height()
        minor, major = ms.ruler_steps(ppm)
        p.setPen(QPen(QColor(theme.MUTED), 1))
        p.setFont(theme.mono_font(7.5))
        first = int((0 - o0) / (minor * ppm)) - 1
        last = int((length - o0) / (minor * ppm)) + 1
        for k in range(first, last + 1):
            mm = k * minor
            pos = int(round(o0 + mm * ppm))
            is_major = abs(mm / major - round(mm / major)) < 1e-9
            tick = self.SIZE - 2 if is_major else (self.SIZE // 3)
            if self.horizontal:
                p.drawLine(pos, self.SIZE, pos, self.SIZE - tick)
                if is_major:
                    p.drawText(pos + 3, 10, f"{mm:g}")
            else:
                p.drawLine(self.SIZE, pos, self.SIZE - tick, pos)
                if is_major:
                    p.save()
                    p.translate(10, pos - 3)
                    p.rotate(-90)
                    p.drawText(0, 0, f"{mm:g}")
                    p.restore()
        if self.cursor_px is not None:
            c = self.mapFromGlobal(self.cursor_px)
            p.setPen(QPen(QColor(theme.ACCENT), 1))
            if self.horizontal:
                p.drawLine(c.x(), 0, c.x(), self.SIZE)
            else:
                p.drawLine(0, c.y(), self.SIZE, c.y())
        p.setPen(QPen(QColor(theme.MUTED), 1))
        if self.horizontal:
            p.drawLine(0, self.SIZE - 1, self.width(), self.SIZE - 1)
        else:
            p.drawLine(self.SIZE - 1, 0, self.SIZE - 1, self.height())


class PageEdit(QLineEdit):
    """Page display "current / total" in ONE field. QLineEdit instead of QSpinBox:
    the theme renders it reliably everywhere (the QSpinBox was sometimes rendered
    empty). Just type the page number and press Enter – or click somewhere else.
    """

    gotoRequested = Signal(int)

    def __init__(self):
        super().__init__()
        self._n = 0
        self._cur = 0
        self._typed = False  # the user has typed since the field got the focus
        self.textEdited.connect(self._on_typed)
        # only a click puts the cursor here: the field must not get the focus by itself (when a dialog closes
        # or a panel is locked) – it would then hold on to an old page number
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFont(theme.mono_font(10))
        self.setFixedWidth(64)
        self.setClearButtonEnabled(False)
        self.setStyleSheet(
            "QLineEdit { border: 1px solid " + theme.BORDER_SUBTLE + "; border-radius: 3px; padding: 1px 4px;"
            " background: " + theme.PANEL + "; color: " + theme.TEXT + "; }"
            "QLineEdit:focus { border-color: " + theme.BORDER_HOVER + "; }"
        )

    # ---- update the display ----
    def set_count(self, n: int):
        """Set the number of pages."""
        self._n = max(0, n)
        self._refresh()

    def set_current(self, i: int):
        """Set the current page (0-based)."""
        self._cur = i
        self._refresh()

    def _refresh(self):
        if not self.hasFocus():
            self.setText(f"{self._cur + 1} / {self._n}" if self._n else "")
        fm = self.fontMetrics()
        self.setFixedWidth(max(56, fm.horizontalAdvance(f"{self._n} / {self._n}") + 24))

    # ---- input: leading number, Enter/leaving jumps to the page ----
    def _on_typed(self, _text):
        self._typed = True

    def _page_from_text(self) -> int | None:
        """The page number that was typed (1-based); None if nothing was typed since the field got the focus –
        the text it shows may be older than the page the view is on by now."""
        if not self._typed:
            return None
        digits = ""
        for ch in self.text():
            if ch.isdigit():
                digits += ch
            else:
                break
        if not digits:
            return None
        p = int(digits)
        return min(max(p, 1), max(1, self._n)) if self._n else None

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            p = self._page_from_text()
            self._typed = False
            self.clearFocus()
            if p is not None and p - 1 != self._cur:
                self.gotoRequested.emit(p - 1)
            self._refresh()
            return
        super().keyPressEvent(e)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        p = self._page_from_text()
        self._typed = False
        if p is not None and self._n and p - 1 != self._cur:
            self.gotoRequested.emit(p - 1)
        self._refresh()

    def focusInEvent(self, e):
        """On focus show only the page number, selected, ready for typing."""
        super().focusInEvent(e)
        self._typed = False
        self.setText(str(self._cur + 1))  # when typing only the bare number
        self.selectAll()
