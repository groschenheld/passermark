# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Thumbnails of the pages in the side bar: list, drawing of an entry, loading in the background."""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QListWidget,
    QStyle,
    QStyledItemDelegate,
)

from . import theme

THUMB_PIX = int(Qt.ItemDataRole.UserRole) + 1


THUMB_ASPECT = int(Qt.ItemDataRole.UserRole) + 2


THUMB_W = int(Qt.ItemDataRole.UserRole) + 3


class ThumbList(QListWidget):
    """Page overview. Two arrangements: one column (the preview fills the width) or a grid
    (fixed tile size, as many side by side as fit). Ctrl + mouse wheel scales.
    """

    resized = Signal()
    zoomed = Signal(int)  # Ctrl + mouse wheel: +1 larger, -1 smaller
    pagesMoved = Signal(list, int)  # selected pages (rows), insertion point (before this row; count = at the end)
    TILE_MIN, TILE_MAX = 60, 600

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.grid_mode = False
        self.tile = 140
        self._press = None  # (position, row, selection change postponed)
        self._drop_ins = None  # insertion point while dragging (yellow bar)
        self._scroll_timer = QTimer(self, interval=40, timeout=self._auto_scroll)
        self._scroll_dir = 0

    # ---------------- dragging pages (reordering with a yellow bar) ---------------- #
    def mousePressEvent(self, e):
        self._drop_ins = None
        if e.button() == Qt.MouseButton.LeftButton:
            it = self.itemAt(e.position().toPoint())
            plain = not (e.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))
            if it is not None and it.isSelected() and plain and len(self.selectedItems()) > 1:
                # click on a page that is already selected: resolve the multiple selection only on release (otherwise it
                # would be gone before one can drag)
                self._press = (e.position().toPoint(), self.row(it), True)
                return
            self._press = (e.position().toPoint(), self.row(it) if it is not None else -1, False)
        super().mousePressEvent(e)

    def _insert_at(self, pos) -> int:
        n = self.count()
        it = self.itemAt(pos)
        if it is None:
            if n == 0:
                return 0
            last = self.visualItemRect(self.item(n - 1))
            first = self.visualItemRect(self.item(0))
            if pos.y() > last.bottom() or (self.grid_mode and pos.y() >= last.top() and pos.x() > last.right()):
                return n
            if pos.y() < first.top():
                return 0
            best = min(range(n), key=lambda i: (self.visualItemRect(self.item(i)).center() - pos).manhattanLength())
            it = self.item(best)
        r = self.visualItemRect(it)
        row = self.row(it)
        after = pos.x() > r.center().x() if self.grid_mode else pos.y() > r.center().y()
        return row + 1 if after else row

    def mouseMoveEvent(self, e):
        if self._press is not None and e.buttons() & Qt.MouseButton.LeftButton and self._press[1] >= 0:
            pos = e.position().toPoint()
            if self._drop_ins is None and (pos - self._press[0]).manhattanLength() < QApplication.startDragDistance():
                return
            if self._drop_ins is None and not self.item(self._press[1]).isSelected():
                super().mouseMoveEvent(e)  # rubber band/selection as usual
                return
            ins = self._insert_at(pos)
            if ins != self._drop_ins:
                self._drop_ins = ins
                self.viewport().update()
            h = self.viewport().height()
            self._scroll_dir = -1 if pos.y() < 24 else 1 if pos.y() > h - 24 else 0
            if self._scroll_dir and not self._scroll_timer.isActive():
                self._scroll_timer.start()
            self.setCursor(Qt.CursorShape.DragMoveCursor)
            return
        super().mouseMoveEvent(e)

    def _auto_scroll(self):
        if not self._scroll_dir or self._drop_ins is None:
            self._scroll_timer.stop()
            return
        sb = self.verticalScrollBar()
        sb.setValue(sb.value() + self._scroll_dir * 24)
        pos = self.viewport().mapFromGlobal(QCursor.pos())
        self._drop_ins = self._insert_at(pos)
        self.viewport().update()

    def mouseReleaseEvent(self, e):
        press, ins = self._press, self._drop_ins
        self._press, self._drop_ins = None, None
        self._scroll_timer.stop()
        self.unsetCursor()
        if ins is not None:
            self.viewport().update()
            rows = sorted(self.row(i) for i in self.selectedItems())
            if rows:
                self.pagesMoved.emit(rows, ins)
            return
        if press is not None and press[2]:  # postponed click: now select only this page
            it = self.item(press[1])
            if it is not None:
                self.clearSelection()
                it.setSelected(True)
                self.setCurrentItem(it)
                self.itemClicked.emit(it)
            return
        super().mouseReleaseEvent(e)

    def paintEvent(self, e):
        super().paintEvent(e)
        ins = self._drop_ins
        if ins is None or self.count() == 0:
            return
        if self.grid_mode:
            # vertical bar between two pages; at the start of a row behind the last page of the previous row
            prev = self.visualItemRect(self.item(ins - 1)) if ins > 0 else None
            cur = self.visualItemRect(self.item(ins)) if ins < self.count() else None
            if prev is not None and (cur is None or abs(prev.top() - cur.top()) > 4):
                x, r = prev.right() + 1, prev
            elif prev is not None:
                x, r = (prev.right() + cur.left()) // 2, cur
            else:
                x, r = cur.left() + 1, cur
            line = QRect(max(1, x - 2), r.top() + 4, 5, r.height() - 8)
        elif ins < self.count():
            r = self.visualItemRect(self.item(ins))
            line = QRect(r.left() + 6, r.top() - 3, r.width() - 12, 5)
        else:
            r = self.visualItemRect(self.item(self.count() - 1))
            line = QRect(r.left() + 6, r.bottom() - 1, r.width() - 12, 5)
        p = QPainter(self.viewport())
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.ACCENT))
        p.drawRoundedRect(line, 2, 2)

    def tile_width(self) -> int:
        """Width of one thumbnail tile in the current arrangement."""
        vw = max(80, self.viewport().width() - 2)
        return vw if not self.grid_mode else max(self.TILE_MIN, min(self.tile, vw))

    def set_grid(self, on: bool):
        """Switch between grid and single-column arrangement."""
        self.grid_mode = bool(on)
        self.setFlow(QListWidget.Flow.LeftToRight if on else QListWidget.Flow.TopToBottom)
        self.setWrapping(bool(on))
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.doItemsLayout()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.resized.emit()

    def wheelEvent(self, e):
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            d = e.angleDelta().y()
            if d:
                self.zoomed.emit(1 if d > 0 else -1)
            e.accept()
            return
        super().wheelEvent(e)


class ThumbDelegate(QStyledItemDelegate):
    """All thumbnails the same size: fixed tile, image fitted inside.
    The rest of the tile gray, selected with a yellow background and border.
    """

    PAD, LABEL, BOX_ASPECT = 8, 20, 1.30

    def __init__(self, view):
        super().__init__(view)
        self.view = view

    def box_rect(self, rect):
        """Rectangle of the thumbnail box inside an item."""
        bw = rect.width() - 2 * self.PAD
        return QRect(rect.x() + self.PAD, rect.y() + self.PAD, bw, int(bw * self.BOX_ASPECT))

    def image_rect(self, rect, aspect):
        """Rectangle of the page image inside the box for a page with this aspect ratio."""
        box = self.box_rect(rect)
        inner = box.adjusted(5, 5, -5, -5)
        iw, ih = inner.width(), int(inner.width() * aspect)
        if ih > inner.height():
            ih = inner.height()
            iw = int(ih / aspect)
        return QRect(inner.x() + (inner.width() - iw) // 2, inner.y() + (inner.height() - ih) // 2, iw, ih)

    def sizeHint(self, option, index):
        w = self.view.tile_width()
        return QSize(w, self.box_rect(QRect(0, 0, w, 0)).height() + self.PAD + self.LABEL)

    def paint(self, p, option, index):
        """Paint one thumbnail: box, page image, page number, selection."""
        r = option.rect
        p.save()
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        sel = bool(option.state & QStyle.StateFlag.State_Selected)
        box = self.box_rect(r)
        if sel:
            p.setBrush(theme.alpha(theme.ACCENT, 60))
            p.setPen(QPen(QColor(theme.ACCENT), 2))
        else:
            p.setBrush(QColor(theme.PLACEHOLDER))
            p.setPen(QPen(QColor(theme.BORDER_SUBTLE), 1))
        p.drawRoundedRect(box, 4, 4)
        img = self.image_rect(r, index.data(THUMB_ASPECT) or 1.414)
        p.setPen(Qt.PenStyle.NoPen)
        p.fillRect(img.translated(2, 2), QColor(0, 0, 0, 90))
        p.fillRect(img, Qt.GlobalColor.white)
        pm = index.data(THUMB_PIX)
        if pm is not None:
            p.drawPixmap(img, pm)
        p.setPen(QColor(theme.ACCENT) if sel else QColor(theme.TEXT))
        f = p.font()
        f.setBold(sel)
        p.setFont(f)
        p.drawText(
            QRect(r.x(), box.bottom() + 2, r.width(), self.LABEL),
            int(Qt.AlignmentFlag.AlignCenter),
            str(index.data(Qt.ItemDataRole.DisplayRole)),
        )
        p.restore()


class ThumbSource:
    """Thumbnails for RenderService: renders only what cannot be derived from a page image already."""

    def __init__(self, win):
        self.win = win
        self.failed = set()

    def usable(self) -> bool:
        """Whether thumbnails can be rendered by the render process right now."""
        from .renderclient import RenderService

        v = self.win.view
        return RenderService.get().ok and not v._local and v._rkey is not None

    def kick(self):
        """Tell the render service that thumbnails are needed."""
        from .renderclient import RenderService

        svc = RenderService.get()
        svc.register(self)
        svc.kick()

    def release(self):
        """Unregister from the render service."""
        from .renderclient import RenderService

        RenderService.get().unregister(self)

    def render_priority(self) -> int:
        """Priority for the render service (thumbnails come after the page view)."""
        try:
            return 1 if self.win.isActiveWindow() else 3
        except RuntimeError:
            return 9

    def next_render(self):
        """The next thumbnail request, or None if nothing is needed."""
        win = self.win
        if win.doc is None or not self.usable():
            return None
        q = win._thumb_queue
        while q:
            i = q[0]
            if i >= len(win.doc) or i >= win.thumbs.count() or (win.view._gen, i) in self.failed:
                q.pop(0)
                continue
            it = win.thumbs.item(i)
            iw, sc = win._thumb_target(i)
            if it.data(THUMB_W) == iw and it.data(THUMB_PIX) is not None:
                q.pop(0)
                continue
            win._thumb_from_master(i)  # page image already there?
            if it.data(THUMB_W) == iw:
                q.pop(0)
                continue
            return {
                "doc": win.view._rkey,
                "gen": win.view._gen,
                "page": i,
                "scale": sc,
                "rotation": win._view_rot(),
                "kind": "thumb",
                "iw": iw,
            }
        return None

    def render_done(self, req, img, err):
        """Take over a rendered thumbnail."""
        win = self.win
        if req.get("gen") != win.view._gen or win.doc is None:
            return
        i = req["page"]
        if err or img is None:
            if err != "render process ended":
                self.failed.add((req["gen"], i))  # stays empty instead of requesting anew endlessly
            return
        if 0 <= i < win.thumbs.count():
            it = win.thumbs.item(i)
            pm = QPixmap.fromImage(img)
            pm.setDevicePixelRatio(win.devicePixelRatioF())
            it.setData(THUMB_PIX, pm)
            it.setData(THUMB_W, req["iw"])
        if win._thumb_queue and win._thumb_queue[0] == i:
            win._thumb_queue.pop(0)

    def render_reset(self):
        """The render process was restarted: nothing to do for thumbnails."""
        pass

    def render_fallback(self):
        """The render process is not usable: render thumbnails in the program."""
        self.win._thumb_timer.start()
