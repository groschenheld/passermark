# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Rendering of the document view: the pages are drawn in a process of their own (renderclient.py), with priorities, a few sharp page images kept, and a fallback that renders in the program."""

from __future__ import annotations

import logging
import os

from PySide6.QtCore import QRect, QRectF
from PySide6.QtGui import QImage

from .common import MAX_RENDER_EDGE
from .viewlayout import PAGE_GAP

log = logging.getLogger(__name__)


def _remove_quiet(path):
    if path:
        try:
            os.remove(path)
        except OSError:
            pass


class PageRenderMixin:
    """Rendering part of PageView: requests page images, takes them in, keeps or discards them."""

    def _open_render(self, src):
        from .renderclient import RenderService

        svc = RenderService.get()
        old_key, old_tmp = self._rkey, self._tmp
        self._rkey, self._tmp, self._src_path = None, None, None
        self._local = not svc.ok
        if old_key is not None:
            svc.close_doc(old_key, on_done=lambda _e, t=old_tmp: _remove_quiet(t))
        elif old_tmp:
            _remove_quiet(old_tmp)
        if self._local or self.doc is None:
            return
        try:
            if isinstance(src, str) and os.path.isfile(src):
                path = src
                if os.path.basename(src).startswith("passermark-view-"):
                    self._tmp = src  # take over the intermediate file of the check (deleted later)
            else:
                import tempfile

                fd, path = tempfile.mkstemp(prefix="passermark-view-", suffix=".pdf")
                with os.fdopen(fd, "wb") as f:
                    if isinstance(src, (bytes, bytearray)):
                        f.write(src)
                    else:
                        self.doc.save(f)
                self._tmp = path
        except Exception:
            log.warning("Render-Prozess nicht nutzbar, Ansicht rendert im Programm", exc_info=True)
            self._local = True
            return
        self._src_path = path
        self._rkey = f"v{id(self)}-{self._gen}"
        svc.register(self)
        svc.open_doc(self._rkey, path, on_done=lambda err, info=None, k=self._rkey: self._render_opened(k, err, info))

    def _render_opened(self, key, err, info=None):
        if key != self._rkey:
            return
        if err:  # e.g. password: this view renders in the program
            self._local = True
            self._timer.start()
        elif isinstance(info, list) and len(info) == len(self.pages):
            self._pinfo = info
            self._snap = {}
            for w in self.pages:
                w.update()
            self.infoReady.emit()

    def release_render(self):
        """Window/tab closed: close the document in the render process, delete the intermediate file."""
        from .renderclient import RenderService

        svc = RenderService.get()
        svc.unregister(self)
        if self._rkey is not None:
            svc.close_doc(self._rkey, on_done=lambda _e, t=self._tmp: _remove_quiet(t))
        elif self._tmp:
            _remove_quiet(self._tmp)
        self._rkey, self._tmp = None, None

    # interface for RenderService
    def render_priority(self) -> int:
        """Priority for the render service: lower is more urgent (active, visible windows first)."""
        try:
            return 0 if self.isVisible() and self.window().isActiveWindow() else 2
        except RuntimeError:
            return 9

    def render_reset(self):
        """Render process restarted: reopen the document there."""
        from .renderclient import RenderService

        if self._rkey is not None and self._src_path and os.path.isfile(self._src_path):
            RenderService.get().open_doc(
                self._rkey,
                self._src_path,
                on_done=lambda err, info=None, k=self._rkey: self._render_opened(k, err, info),
            )

    def render_fallback(self):
        """The render process is not usable: render in the program from now on."""
        self._local = True
        self._timer.start()

    def _dev_scale(self, i: int) -> float:
        """Device pixels per pt for page i in the current view."""
        return self.page_zoom(i) * self._dpi_scale() * self.devicePixelRatioF()

    def _master_scale(self, i: int) -> float:
        pw, ph = self._rot_size(i)
        s = self._dpi_scale()
        vw = max(50, self.viewport().width() - 2 * PAGE_GAP - 4)
        vh = max(50, self.viewport().height() - 2 * PAGE_GAP)
        fit = min(vw / (pw * s), vh / (ph * s)) * s * self.devicePixelRatioF()
        cap = min(
            MAX_RENDER_EDGE / max(1.0, pw),
            MAX_RENDER_EDGE / max(1.0, ph),
            (self.MASTER_PIXELS / max(1.0, pw * ph)) ** 0.5,
        )
        # zoomed far out (many pages): smaller; from whole-page size: twice as large, sections above that
        S = self._dev_scale(i)
        want = self.MASTER_FACTOR * max(fit * 0.5, min(S, fit))
        return max(0.02, min(want, cap))

    def set_proof(self, spec):
        """Soft proof on (spec) or off (None): all page images anew, the old ones stay until then."""
        from .. import proof

        key = proof.spec_key(spec) if spec else ()
        if key == self._pkey:
            return
        self.proof, self._pkey = (dict(spec) if spec else None), key
        for w in self.pages:
            if w.master is not None:
                w.mstale = True
            w.drop(tile_only=True)
            w.update()
        self._timer.start()

    def tile_key(self, w):
        """Key ``(scale, rotation)`` identifying the zoomed section of page widget ``w``."""
        return (round(self._dev_scale(w.index), 4), self.rotation)

    def _visible_rect(self, w) -> QRect:
        vp = self.viewport().rect()
        top_left = w.mapFrom(self.viewport(), vp.topLeft())
        return QRect(top_left, vp.size()).intersected(w.rect())

    def _wanted_pages(self) -> list:
        """Visible pages (current one first)."""
        vis = [w for w in self.pages if w.isVisibleTo(self.container) and not self._visible_rect(w).isEmpty()]
        vis.sort(key=lambda w: (w.index != self.current, abs(w.index - self.current)))
        return vis

    def next_render(self):
        """What should be rendered next – or None. (Also for rendering in the program.)"""
        if self.doc is None or getattr(self.doc, "raw", None) is None or not self.pages:
            return None
        rot = self.rotation
        base = {"doc": self._rkey, "gen": self._gen, "rotation": rot, "pkey": self._pkey}
        if self.proof:
            base["proof"] = self.proof
        vis = self._wanted_pages()
        for w in vis:
            i = w.index
            if i in self._rfail:
                continue
            S, M = self._dev_scale(i), self._master_scale(i)
            have = w.mkey
            if w.master is None or w.mstale or have[1] != rot or have[0] < min(M, S) * 0.98:
                return dict(base, page=i, scale=M, kind="master")
        for w in vis:  # strong zoom: sharp section
            i = w.index
            if i in self._rfail or w.mkey is None:
                continue
            S = self._dev_scale(i)
            if w.mkey[0] * 1.02 >= S:
                continue
            vis_r = self._visible_rect(w)
            if vis_r.isEmpty():
                continue
            need = self.tile_key(w)
            if w.tile is not None and w.tkey == need and w.tile_rect.contains(QRectF(vis_r)):
                continue
            mx, my = vis_r.width() // 4, vis_r.height() // 4
            r = vis_r.adjusted(-mx, -my, mx, my).intersected(w.rect())
            dpr = self.devicePixelRatioF()
            W, H = w.width() * dpr, w.height() * dpr
            x0, y0, x1, y1 = r.left() * dpr, r.top() * dpr, (r.right() + 1) * dpr, (r.bottom() + 1) * dpr
            crop = [x0 / S, (H - y1) / S, (W - x1) / S, y0 / S]
            return dict(
                base, page=i, scale=S, kind="tile", crop=crop, tkey=need, rect=(r.x(), r.y(), r.width(), r.height())
            )
        if self.single and not self._local:  # prepare neighbouring pages (only useful in the background)
            for i in (self.current + 1, self.current - 1):
                if 0 <= i < len(self.pages) and i not in self._rfail:
                    w = self.pages[i]
                    if w.master is None or w.mstale or w.mkey[1] != rot:
                        return dict(base, page=i, scale=self._master_scale(i), kind="master")
        return None

    def render_done(self, req, img, err):
        """Take over a rendered image from the render service (ignored if it is outdated)."""
        if req.get("gen") != self._gen or (req.get("doc") is not None and req.get("doc") != self._rkey):
            return
        if req.get("pkey", ()) != self._pkey:
            return  # rendered with a different soft proof
        i = req["page"]
        if not (0 <= i < len(self.pages)):
            return
        w = self.pages[i]
        if err or img is None:
            if err == "render process ended":
                return  # requested again after the restart
            self._rfail.add(i)
            self._render_one_local(w, req)  # render this page in the program
            return
        if req["kind"] == "master":
            w.master, w.mkey, w.mstale = img, (req["scale"], req["rotation"]), False
            w._skey = None
            self.masterReady.emit(i)
        elif req["kind"] == "tile":
            if req["tkey"] != self.tile_key(w):
                return
            w.tile, w.tile_rect, w.tkey = img, QRectF(*req["rect"]), req["tkey"]
        w.update()

    def _render_image(self, req):
        """Render in the program (fallback) – same request as to the render process."""
        page = self.doc[req["page"]]
        try:
            crop = tuple(req["crop"]) if req.get("crop") else (0, 0, 0, 0)
            if req.get("proof"):
                from .. import proof

                im = proof.proofed_render(
                    page, req["scale"], req["rotation"], crop, req["proof"], self._src_path, req["page"]
                )
                return QImage(
                    im.tobytes("raw", "RGB"), im.width, im.height, im.width * 3, QImage.Format.Format_RGB888
                ).copy()
            bmp = page.render(
                scale=req["scale"],
                rotation=req["rotation"] % 360,
                crop=crop,
                prefer_bgrx=True,
                may_draw_forms=True,
                draw_annots=True,
            )
            fmt = QImage.Format.Format_RGB32 if bmp.n_channels == 4 else QImage.Format.Format_BGR888
            img = QImage(bytes(bmp.buffer), bmp.width, bmp.height, bmp.stride, fmt).copy()
            bmp.close()
            return img
        finally:
            page.close()

    def _render_one_local(self, w, req):
        try:
            img = self._render_image(req)
        except Exception:
            log.warning("Seite nicht gerendert (im Programm)", exc_info=True)
            return
        saved = self._rkey
        self.render_done(dict(req, doc=saved), img, None)

    def _evict(self):
        """Memory: keep page images only around the visible pages, sections only while visible."""
        vis = {w.index for w in self._wanted_pages()} or {self.current}
        lo, hi = min(vis) - self.KEEP_MASTERS, max(vis) + self.KEEP_MASTERS
        for w in self.pages:
            if w.index not in vis and w.tile is not None:
                w.drop(tile_only=True)
            if not (lo <= w.index <= hi) and w.master is not None:
                w.drop()

    def _rotate_master(self, w):
        """View rotated: rotate the existing page image along at once (the sharp one follows)."""
        if w.master is None or w.mkey is None or w.mkey[1] == self.rotation:
            return
        from PySide6.QtGui import QTransform

        w.master = w.master.transformed(QTransform().rotate((self.rotation - w.mkey[1]) % 360))
        w.mkey = (w.mkey[0], self.rotation)
        w.mstale = True  # render anew (aspect ratio/edges exact)
        w._skey = None
        w.drop(tile_only=True)

    def _render_visible(self):
        """After scrolling/zooming/layout: report what is needed to the render process (or render in the program)."""
        if self.doc is None or getattr(self.doc, "raw", None) is None:
            return  # document already closed (window/tab closed, the timer fired afterwards)
        self._evict()
        for w in self._wanted_pages():
            w.update()  # no longer show the section of another zoom level
        if not self._local:
            from .renderclient import RenderService

            RenderService.get().kick()
            return
        for _ in range(12):  # fallback: in the program, same determination of what is needed
            req = self.next_render()
            if req is None:
                break
            try:
                img = self._render_image(req)
            except Exception:
                log.warning("Seite nicht gerendert (im Programm)", exc_info=True)
                self._rfail.add(req["page"])
                continue
            self.render_done(dict(req, doc=self._rkey), img, None)
