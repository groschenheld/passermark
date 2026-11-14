# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Mouse in the document view: selecting text, measuring with snapping to edges, edit mode and pipette clicks."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt

log = logging.getLogger(__name__)


class PageInteractionMixin:
    """Mouse handling of PageView (the page widgets pass their events on to these methods)."""

    def _hover_text(self, w, pos, tol=4.0) -> bool:
        """Is there text under the mouse? For the cursor – does NOT load the page in the program (character boxes come
        from the render process); if the text page is already loaded, it is used.
        """
        if w.index in self._tp or self._local or self._rkey is None:
            return self._char_at(w, pos, tol) >= 0
        ch = self._chars.get(w.index)
        if ch is None:
            from .renderclient import RenderService

            self._chars[w.index] = "pending"
            key, gen = self._rkey, self._gen

            def got(err, boxes, i=w.index):
                if gen == self._gen and key == self._rkey:
                    import numpy as np

                    self._chars[i] = np.asarray(boxes if (not err and boxes) else [], dtype=float).reshape(-1, 4)

            RenderService.get().chars(key, w.index, got)
            return False
        if isinstance(ch, str) or len(ch) == 0:
            return False
        x, y = self.to_page(w, pos)
        return bool(
            ((ch[:, 0] - tol <= x) & (x <= ch[:, 2] + tol) & (ch[:, 1] - tol <= y) & (y <= ch[:, 3] + tol)).any()
        )

    def _char_at(self, w, pos, tol=4.0):
        _pg, tp = self._textpage(w.index)
        x, y = self.to_page(w, pos)
        i = tp.get_index(x, y, tol, tol)
        return i if i is not None and i >= 0 else -1

    def _snap_candidates(self, w):
        """Snap candidates of the page (pt), separated by priority:
        1) cut/inner lines (page edge, TrimBox, BleedBox) – precedence,
        2) image edges and points of vector lines.
        Text/letters are deliberately NOT snappable. Cached per page.
        """
        if w.index in self._snap:
            return self._snap[w.index]
        bx, by, ox, oy = set(), set(), set(), set()
        try:
            pg, _tp = self._textpage(w.index)  # measuring: the objects of the page are needed
            crop = pg.get_cropbox()
            bx |= {crop[0], crop[2]}
            by |= {crop[1], crop[3]}
            if True:
                for b in self.page_boxes(w.index):
                    if b is not None:
                        bx |= {b[0], b[2]}
                        by |= {b[1], b[3]}
            try:  # objects: images and vector paths – no text
                import ctypes as _ct

                import pypdfium2.raw as _r

                for obj in pg.get_objects():
                    try:
                        t = obj.type
                        if t == _r.FPDF_PAGEOBJ_IMAGE:
                            left, b, r, t_ = obj.get_pos()
                            if r - left < 2000 and t_ - b < 2000:
                                ox |= {left, r}
                                oy |= {b, t_}
                        elif t == _r.FPDF_PAGEOBJ_PATH:
                            # single path segments: line ends, curve control points –
                            # precise snapping to real vector lines
                            left, b, r, t_ = obj.get_pos()
                            if r - left < 2000 and t_ - b < 2000:
                                ox |= {left, r}
                                oy |= {b, t_}
                                n_seg = 0
                                try:
                                    n_seg = _r.FPDFPath_CountSegments(obj.raw)
                                except Exception:  # noqa: BLE001 – malformed PDF object: skipped or default value
                                    pass
                                for si in range(min(n_seg, 4000)):
                                    try:
                                        seg = _r.FPDFPath_GetSegment(obj.raw, si)
                                        sx_, sy_ = _ct.c_float(), _ct.c_float()
                                        if _r.FPDFPath_GetSegmentPoint(seg, _ct.byref(sx_), _ct.byref(sy_)):
                                            ox.add(sx_.value)
                                            oy.add(sy_.value)
                                    except Exception:  # noqa: BLE001 – malformed PDF object: skipped or default value
                                        pass
                    except Exception:  # noqa: BLE001 – malformed PDF object: skipped or default value
                        pass
            except Exception:  # noqa: BLE001 – optional part: works without it
                pass
        except Exception:
            log.warning("Objekte zum Messen nicht gelesen", exc_info=True)
        out = (sorted(bx), sorted(by), sorted(ox), sorted(oy))
        self._snap[w.index] = out
        # diagnostics (once per page in the terminal): shows whether candidates were found
        print(
            f"[Passermark] Einrasten Seite {w.index + 1}: {len(out[0])} Schnitt-/Innen-X, "
            f"{len(out[1])} -Y, {len(out[2])} Bild-/Vektor-X, {len(out[3])} -Y",
            flush=True,
        )
        return out

    def _snap_point(self, w, x, y, ctrl):
        """Snap the cross hairs – only with Ctrl pressed. Priority:
        1) cut/inner lines (page edge/TrimBox/BleedBox) fix first,
        2) otherwise image edges/points of vector lines.
        Magnetic with hysteresis: snap from ~8 screen pixels proximity, but
        let go only when the mouse is ~24 px away – this way the cross hairs
        "stick" to the edge during a slight mouse movement and move on
        only with a real swing.
        """
        if not ctrl:
            self._snap_stuck = None
            return x, y
        bxs, bys, oxs, oys = self._snap_candidates(w)
        pw, ph = self._rot_size(w.index)
        sx = 10.0 * pw / max(1, w.width())
        sy = 10.0 * ph / max(1, w.height())

        def near(vals_pri, vals_obj, v, tol, key):
            release = tol * 8.0  # release threshold: 8× the snap tolerance
            # (~80 px) – the cross should really
            # stay on the edge
            stuck = self._snap_stuck or {}
            old = stuck.get(key)
            if old is not None and abs(old - v) <= release:
                return old  # sticks to the edge
            best, bd = None, tol
            for c in vals_pri:  # cut/inner lines first
                d = abs(c - v)
                if d <= bd:
                    best, bd = c, d
            if best is None:  # otherwise image/vector edges
                for c in vals_obj:
                    d = abs(c - v)
                    if d <= bd:
                        best, bd = c, d
            stuck[key] = best  # None = not snapped (remember that too)
            self._snap_stuck = stuck
            return best if best is not None else v

        return near(bxs, oxs, x, sx, "x"), near(bys, oys, y, sy, "y")

    def _measure_point(self, w, pos, shift, ctrl):
        """Mouse position -> page point; with Shift snapped horizontally/vertically/at 45° to the start point."""
        from .. import measure as ms

        if shift and self.meas and self.meas["a"] is not None and not self.meas["done"]:
            sx, sy = self.to_widget(w, *self.meas["a"])
            vx, vy = ms.snap(pos.x() - sx, pos.y() - sy, True)
            # convert the snapped screen vector exactly into page measures (not via whole pixels)
            a, b, c, d = self.page_matrix(w)
            det = a * d - b * c
            if abs(det) > 1e-12:
                px = (d * vx - c * vy) / det
                py = (-b * vx + a * vy) / det
                ax, ay = self.meas["a"]
                return ax + px, ay + py
        x, y = self.to_page(w, pos)
        return self._snap_point(w, x, y, ctrl)  # Ctrl = snap to cut/image/vector lines

    def _measure_report(self, w):
        from .. import l10n
        from .. import measure as ms

        if self.on_measure is None or not self.meas:
            return
        if self.meas["b"] is None:
            return
        r = ms.measure(self.meas["a"], self.meas["b"], self.page_matrix(w))
        self.on_measure(ms.describe(r, l10n.current()))

    def measure_clear(self):
        """Remove the current measurement."""
        if self.meas is not None and 0 <= self.meas["page"] < len(self.pages):
            self.pages[self.meas["page"]].update()
        self.meas = None
        if self.on_measure is not None:
            self.on_measure("")

    def _measure_press(self, w, e):
        shift = bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        m = self.meas
        if m is None or m["done"] or m["page"] != w.index:
            ctrl = bool(e.modifiers() & Qt.KeyboardModifier.ControlModifier)
            a = self._measure_point(w, e.position(), False, ctrl)  # 1st click: start
            self.meas = {"page": w.index, "a": a, "b": None, "done": False}
        else:
            m["b"] = self._measure_point(
                w, e.position(), shift, bool(e.modifiers() & Qt.KeyboardModifier.ControlModifier)
            )  # 2nd click: end
            m["done"] = True
            self._measure_report(w)
        w.update()

    def _measure_move(self, w, e):
        from .. import l10n
        from .. import measure as ms

        if self.on_cursor is not None:
            self.on_cursor(w, e.position())
        m = self.meas
        if m is not None and not m["done"] and m["page"] == w.index:
            shift = bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            m["b"] = self._measure_point(
                w, e.position(), shift, bool(e.modifiers() & Qt.KeyboardModifier.ControlModifier)
            )  # rubber band
            self._measure_report(w)
            w.update()
        elif self.on_measure is not None and (m is None or m["done"]):
            geo = self.ruler_geometry()
            if geo is not None and w.index == self.current:
                ppm = geo[1]
                if m is None:
                    self.on_measure(ms.describe_pos(e.position().x() / ppm, e.position().y() / ppm, l10n.current()))
            # Ctrl held: preview cross hairs that snap to the nearest edge
            # (visible before the first click – afterwards the end of the rubber band snaps)
            ctrl = bool(e.modifiers() & Qt.KeyboardModifier.ControlModifier)
            if ctrl and w.index == self.current:
                x, y = self.to_page(w, e.position())
                sx, sy = self._snap_point(w, x, y, True)
                self._snap_prev = (w.index, sx, sy, x != sx or y != sy)
            elif self._snap_prev is not None:
                self._snap_prev = None
            if self._snap_prev is not None or not ctrl:
                w.update()

    def mouse_press(self, w, e):
        """Mouse pressed on page widget ``w``: dispatch to measuring, pipette, editing or text selection."""
        self.setFocus()
        if self.imode == "measure":
            self._measure_press(w, e)
            return
        if self.imode == "pipette":
            if self.on_pipette is not None and e.button() == Qt.MouseButton.LeftButton:
                x, y = self.to_page(w, e.position())
                self.on_pipette(w.index, x, y)
            return
        if self.imode == "edit":
            x, y = self.to_page(w, e.position())
            if self.editor is not None:
                self._edrag = True
                self.editor.press(
                    w.index, x, y, self._tol_pt(w), bool(e.modifiers() & Qt.KeyboardModifier.ControlModifier)
                )
            elif self.edit_click is not None:
                self.edit_click(
                    w.index,
                    x,
                    y,
                    bool(e.modifiers() & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier)),
                )
            return
        i = self._char_at(w, e.position(), 12.0)
        self._drag = (w.index, i) if i >= 0 else None
        old = self.sel
        self.sel = None
        if old is not None and 0 <= old[0] < len(self.pages):
            self.pages[old[0]].update()

    def mouse_move(self, w, e):
        """Mouse moved over page widget ``w``: update the cursor and the running interaction."""
        self.ruler_page = w.index  # rulers: zero at the corner of this page
        if self.imode == "measure":
            w.setCursor(Qt.CursorShape.CrossCursor)
            self._measure_move(w, e)
            return
        if self.imode == "pipette":
            w.setCursor(Qt.CursorShape.CrossCursor)
            if self.on_cursor is not None:
                self.on_cursor(w, e.position())
            return
        if self.on_cursor is not None:
            self.on_cursor(w, e.position())
        if self.imode == "edit":
            x, y = self.to_page(w, e.position())
            if self.editor is not None and self._edrag:
                self.editor.drag(w.index, x, y)
                return
            kind = self.editor.cursor(w.index, x, y, self._tol_pt(w)) if self.editor is not None else None
            w.setCursor(
                {"move": Qt.CursorShape.SizeAllCursor, "scale": Qt.CursorShape.SizeFDiagCursor}.get(
                    kind, Qt.CursorShape.PointingHandCursor
                )
            )
            return
        if self._drag is None:
            w.setCursor(Qt.CursorShape.IBeamCursor if self._hover_text(w, e.position()) else Qt.CursorShape.ArrowCursor)
            return
        page, start = self._drag
        if page != w.index:
            return
        j = self._char_at(w, e.position(), 30.0)
        if j >= 0:
            self.sel = (page, min(start, j), max(start, j))
            w.update()

    def mouse_release(self, w, e):
        """Mouse released: finish the running interaction."""
        self._drag = None
        if self.imode == "edit" and self._edrag:
            self._edrag = False
            if self.editor is not None:
                x, y = self.to_page(w, e.position())
                self.editor.release(w.index, x, y)

    def _tol_pt(self, w) -> float:
        """Greif-Toleranz: ~7 Bildschirmpixel in Seitenkoordinaten."""
        pw, _ph = self._rot_size(w.index)
        return 7.0 * pw / max(1, w.width())

    def mouse_double(self, w, e):
        """Double click: select the word under the mouse."""
        if self.imode in ("edit", "measure", "pipette"):
            return
        i = self._char_at(w, e.position(), 12.0)
        if i < 0:
            return
        _pg, tp = self._textpage(w.index)
        text = tp.get_text_range()
        a = b = min(i, len(text) - 1)
        while a > 0 and text[a - 1].isalnum():
            a -= 1
        while b + 1 < len(text) and text[b + 1].isalnum():
            b += 1
        self.sel = (w.index, a, b)
        w.update()

    def selected_text(self) -> str:
        """The selected text (empty if nothing is selected)."""
        if self.sel is None:
            return ""
        page, a, b = self.sel
        _pg, tp = self._textpage(page)
        return tp.get_text_range(a, b - a + 1).replace("\r\n", "\n").replace("\r", "\n")

    def select_page_text(self):
        """Select all text of the current page."""
        if not self.doc:
            return
        _pg, tp = self._textpage(self.current)
        n = tp.count_chars()
        if n:
            self.sel = (self.current, 0, n - 1)
            self.pages[self.current].update()
