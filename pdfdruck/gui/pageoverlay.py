# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""What the document view draws on top of the page image: text selection, measuring, snap cross, page boxes, object frames and the location of a finding of the document check."""

from __future__ import annotations

import logging

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor

from . import theme

log = logging.getLogger(__name__)


class PageOverlayMixin:
    """Painting on top of the pages of PageView."""

    def show_spot(self, i: int, box=None):
        """Check: jump to the location and mark it (frame around the area, otherwise around the page)."""
        if not (0 <= i < len(self.pages)):
            return
        self.goto(i, force=True)
        self.pf_mark = (i, tuple(box) if box else None)
        w = self.pages[i]
        if box:
            try:
                r = self._rect_widget(w, box[0], box[1], box[2], box[3])
                vb, hb = self.verticalScrollBar(), self.horizontalScrollBar()
                vh, vw = self.viewport().height(), self.viewport().width()
                if r.height() < vh:  # bring the location into the upper third
                    vb.setValue(int(w.y() + r.center().y() - vh / 3))
                else:
                    vb.setValue(int(w.y() + r.top() - 20))
                if r.width() < vw:
                    hb.setValue(int(w.x() + r.center().x() - vw / 2))
            except Exception:
                log.warning("Markierung nicht gezeichnet", exc_info=True)
        for pw in self.pages:
            pw.update()
        if not hasattr(self, "_pf_mark_timer"):
            self._pf_mark_timer = QTimer(self, singleShot=True, interval=6000, timeout=self._clear_spot)
        self._pf_mark_timer.start()

    def _clear_spot(self):
        mk = getattr(self, "pf_mark", None)
        self.pf_mark = None
        if mk and 0 <= mk[0] < len(self.pages):
            self.pages[mk[0]].update()

    def paint_overlay(self, w, p):
        """Paint everything that lies on top of the page image: selection, marks, boxes, measurement."""
        try:
            self._paint_selection(w, p)
            self._paint_measure(w, p)
            self._paint_snap_cross(w, p)
            self._paint_page_boxes(w, p)
            self._paint_overlay_items(w, p)
            self._paint_check_mark(w, p)
        except Exception:
            log.warning("Auswahl nicht gezeichnet", exc_info=True)

    def _paint_selection(self, w, p):
        """Selected text."""
        if self.sel is not None and self.sel[0] == w.index:
            _pg, tp = self._textpage(w.index)
            n = tp.count_rects(self.sel[1], self.sel[2] - self.sel[1] + 1)
            col = QColor(theme.ACCENT)
            col.setAlpha(90)
            for k in range(n):
                p.fillRect(self._rect_widget(w, *tp.get_rect(k)), col)

    def _paint_measure(self, w, p):
        """Measuring: the line with its end points, or the cross of the first point."""
        from PySide6.QtGui import QPen

        m = self.meas
        if m is not None and m["page"] == w.index and m["b"] is not None:
            ax, ay = self.to_widget(w, *m["a"])
            bx, by = self.to_widget(w, *m["b"])
            col = QColor(theme.ACCENT)
            pen = QPen(col, 2)
            if not m["done"]:
                pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawLine(ax, ay, bx, by)
            p.setBrush(col)
            for x, y in ((ax, ay), (bx, by)):
                p.drawEllipse(QPointF(x, y), 3.5, 3.5)
        elif m is not None and m["page"] == w.index:
            ax, ay = self.to_widget(w, *m["a"])
            p.setPen(QPen(QColor(theme.ACCENT), 2))
            p.drawLine(ax - 6, ay, ax + 6, ay)
            p.drawLine(ax, ay - 6, ax, ay + 6)

    def _paint_snap_cross(self, w, p):
        """Ctrl preview cross hairs; bold with a circle when snapped to an edge."""
        from PySide6.QtGui import QPen

        sp = self._snap_prev
        if sp is not None and sp[0] == w.index:
            # Ctrl preview cross hairs; bold + circle when snapped to an edge
            px, py = self.to_widget(w, sp[1], sp[2])
            col = QColor(theme.MARK_OK) if sp[3] else QColor(theme.MUTED)
            pen = QPen(col, 2 if sp[3] else 1)
            if not sp[3]:
                pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawLine(px - 10, py, px + 10, py)
            p.drawLine(px, py - 10, px, py + 10)
            if sp[3]:
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(px, py), 4, 4)

    def _paint_page_boxes(self, w, p):
        """Trim size as a green inner boundary, page edge as a fine red frame, bleed box dashed red."""
        from PySide6.QtGui import QPen

        bx = self.page_boxes(w.index) if getattr(self, "show_boxes", True) else None
        if bx and bx[0] is not None:
            # trim size = green inner boundary, bleed = subtle red outline
            # (no solid red area); BleedBox dashed red (is not printed)
            trim, bleed = bx
            info = self.page_info(w.index)
            if info is not None:
                crop = info["crop"]
            else:
                pg_, _tp = self._textpage(w.index)
                crop = pg_.get_cropbox()
            green = QColor(theme.MARK_OK)
            red = QColor(theme.MARK_ERROR)
            outer = self._rect_widget(w, crop[0], crop[1], crop[2], crop[3])
            inner = self._rect_widget(w, trim[0], trim[1], trim[2], trim[3])
            # ring between page edge and trim size: only a fine red frame
            ring_pen = QPen(red, 1.0)
            ring_pen.setStyle(Qt.PenStyle.DotLine)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(ring_pen)
            p.drawRect(outer)
            # inner boundary (trim size) strong green – as in the VDP preview
            p.setPen(QPen(green, 1.5))
            p.drawRect(inner)
            if bleed is not None:
                pen = QPen(red, 1.2)
                pen.setStyle(Qt.PenStyle.DashLine)
                p.setPen(pen)
                p.drawRect(self._rect_widget(w, bleed[0], bleed[1], bleed[2], bleed[3]))

    def _paint_overlay_items(self, w, p):
        """Frames of chosen objects, guide lines when snapping, and the object that is being dragged."""
        from PySide6.QtGui import QPen

        items = self.overlay.get(w.index, [])
        for item in items:
            x0, y0, x1, y1, c = item[:5]
            style = item[5] if len(item) > 5 else ""
            if style == "guide":  # guide line when snapping
                pen = QPen(QColor(c), 1)
                pen.setStyle(Qt.PenStyle.DashLine)
                p.setPen(pen)
                a, b = self.to_widget(w, x0, y0), self.to_widget(w, x1, y1)
                p.drawLine(a[0], a[1], b[0], b[1])
                continue
            if style == "dash" and items and w.master is not None and w.width() > 0:
                # dragging: move the object along as an image (from the page image, without rendering anew)
                sx0, sy0, sx1, sy1 = items[0][:4]
                src = self._rect_widget(w, sx0, sy1, sx1, sy0)
                f = w.master.width() / w.width()
                p.setOpacity(0.6)
                p.drawImage(
                    self._rect_widget(w, x0, y1, x1, y0),
                    w.master,
                    QRectF(src.x() * f, src.y() * f, src.width() * f, src.height() * f),
                )
                p.setOpacity(1.0)
            pen = QPen(QColor(c), 2)
            fill = QColor(c)
            fill.setAlpha(40)
            if style == "dash":
                pen.setStyle(Qt.PenStyle.DashLine)
                fill.setAlpha(15)
            elif style == "handle":
                fill = QColor("#ffffff")
            p.setPen(pen)
            p.setBrush(fill)
            p.drawRect(self._rect_widget(w, x0, y1, x1, y0))

    def _paint_check_mark(self, w, p):
        """The location a finding of the document check points to."""
        from PySide6.QtGui import QPen

        mk = getattr(self, "pf_mark", None)
        if mk and mk[0] == w.index:  # location from the check
            col = QColor(theme.ERROR)
            pen = QPen(col, 3)
            fill = QColor(col)
            fill.setAlpha(45)
            p.setPen(pen)
            p.setBrush(fill)
            if mk[1]:
                x0, y0, x1, y1 = mk[1]
                p.drawRect(self._rect_widget(w, x0, y0, x1, y1).adjusted(-4, -4, 4, 4))
            else:
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(QRectF(1.5, 1.5, w.width() - 3, w.height() - 3))
