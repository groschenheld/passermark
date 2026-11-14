# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Geometry of the document view: page data without loading the page (boxes, rotation), text pages, and the conversion between page coordinates (pt) and screen coordinates."""

from __future__ import annotations

from PySide6.QtCore import QPointF


class PageGeometryMixin:
    """Page data and coordinate conversion of PageView."""

    def _rot_size(self, i):
        w, h = self.sizes[i]
        return (h, w) if self.rotation % 180 else (w, h)

    def _close_textpages(self):
        for pg, tp in self._tp.values():
            try:
                tp.close()
                pg.close()
            except Exception:  # noqa: BLE001 – cleanup
                pass
        self._tp = {}

    def _textpage(self, i):
        if i not in self._tp:
            if len(self._tp) > 6:
                self._close_textpages()
            pg = self.doc[i]
            self._tp[i] = (pg, pg.get_textpage())
        return self._tp[i]

    def page_info(self, i):
        """Boxes and rotation of page ``i`` from the render process, or None while unknown."""
        return self._pinfo[i] if self._pinfo is not None and 0 <= i < len(self._pinfo) else None

    def page_boxes(self, i):
        """(TrimBox, BleedBox) for display – None while unknown (render process) or not defined."""
        info = self.page_info(i)
        if info is not None:
            return info["trim"], info["bleed"]
        if not (self._local or (self._rkey is None and self.doc is not None)):
            return None, None  # arrives from the render process shortly
        if i not in self._lazy_boxes:  # fallback: pdfium, only this page
            try:
                from ..layout import page_boxes as _pb

                class _One:
                    def __len__(s):
                        return 1

                    def __getitem__(s, _k):
                        return self.doc[i]

                self._lazy_boxes[i] = _pb(_One())[0]
            except Exception:  # noqa: BLE001 – boxes not readable: the page is shown without them
                self._lazy_boxes[i] = (None, None)
        return self._lazy_boxes[i]

    def trim_info(self, i):
        """Like layout.trim_info, from the page data (None = unknown/no bleed)."""
        info = self.page_info(i)
        if info is None:
            if self._local or self._rkey is None:
                from ..layout import trim_info

                return trim_info(self.doc, i)
            return None
        trim = info.get("trim_raw") or info.get("art")
        if trim is None:
            return None
        cl, cb, cr, ct = info["crop"]
        tl, tb, tr_, tt = (max(trim[0], cl), max(trim[1], cb), min(trim[2], cr), min(trim[3], ct))
        o = (tl - cl, tb - cb, cr - tr_, ct - tt)
        rot = info["rotate"]
        if rot == 1:
            o = (o[1], o[2], o[3], o[0])
        elif rot == 2:
            o = (o[2], o[3], o[0], o[1])
        elif rot == 3:
            o = (o[3], o[0], o[1], o[2])
        if not (max(o) > 0.5 and min(o) >= 0 and (tr_ - tl) > 10 and (tt - tb) > 10):
            return None
        w, h = self.sizes[i]
        mm = 72 / 25.4
        return ((w - o[0] - o[2]) / mm, (h - o[1] - o[3]) / mm, min(o) / mm)

    def _display_matrix(self, w):
        """Page -> widget like pdfium, from the page data (see pagegeom.py). None = page data missing."""
        info = self.page_info(w.index)
        if info is None:
            return None
        from ..pagegeom import display_matrix

        return display_matrix(info, w.width(), w.height(), self.rotation)

    def to_page(self, w, pos):
        """Widget pixels -> page coordinates (pt, PDF system) – rotation/CropBox like pdfium."""
        m = self._display_matrix(w)
        if m is not None:
            from ..pagegeom import to_page

            p = to_page(m, pos.x(), pos.y())
            if p is not None:
                return p
        import ctypes

        import pypdfium2.raw as r

        pg, _tp = self._textpage(w.index)
        px, py = ctypes.c_double(), ctypes.c_double()
        r.FPDF_DeviceToPage(
            pg.raw,
            0,
            0,
            w.width(),
            w.height(),
            (self.rotation // 90) % 4,
            int(pos.x()),
            int(pos.y()),
            ctypes.byref(px),
            ctypes.byref(py),
        )
        return px.value, py.value

    def to_widget(self, w, x, y):
        """Map a page point (pt) to coordinates of page widget ``w``."""
        m = self._display_matrix(w)
        if m is not None:
            from ..pagegeom import to_device

            dx, dy = to_device(m, x, y)
            return round(dx), round(dy)
        import ctypes

        import pypdfium2.raw as r

        pg, _tp = self._textpage(w.index)
        dx, dy = ctypes.c_int(), ctypes.c_int()
        r.FPDF_PageToDevice(
            pg.raw, 0, 0, w.width(), w.height(), (self.rotation // 90) % 4, x, y, ctypes.byref(dx), ctypes.byref(dy)
        )
        return dx.value, dy.value

    def _rect_widget(self, w, x0, y0, x1, y1):
        from PySide6.QtCore import QRectF

        a = self.to_widget(w, x0, y0)
        b = self.to_widget(w, x1, y1)
        return QRectF(min(a[0], b[0]), min(a[1], b[1]), abs(a[0] - b[0]), abs(a[1] - b[1]))

    def ruler_geometry(self):
        """(top left page corner in viewport pixels, pixels per mm) of the page under the mouse (else the current
        page) – or None."""
        from PySide6.QtCore import QPoint

        if not self.doc or not (0 <= self.current < len(self.pages)):
            return None
        i = self.ruler_page
        if i is None or not (0 <= i < len(self.pages)) or not self.pages[i].isVisibleTo(self.container):
            i = self.current
        w = self.pages[i]
        pw, _ph = self._rot_size(i)
        if pw <= 0 or w.width() <= 0:
            return None
        return w.mapTo(self.viewport(), QPoint(0, 0)), w.width() / pw * 72.0 / 25.4

    def page_matrix(self, w):
        """Linear mapping page -> screen (a, b, c, d) incl. zoom and rotation, derived from pdfium."""
        x0, y0 = self.to_page(w, QPointF(w.width() / 2, w.height() / 2))
        far = 1000.0
        p0 = self.to_widget(w, x0, y0)
        px = self.to_widget(w, x0 + far, y0)
        py = self.to_widget(w, x0, y0 + far)
        return ((px[0] - p0[0]) / far, (px[1] - p0[1]) / far, (py[0] - p0[0]) / far, (py[1] - p0[1]) / far)
