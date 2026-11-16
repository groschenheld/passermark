# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""The document view: a scroll area with one widget per page. Rendering, page geometry, mouse handling and painting on top of the pages come from mixins (pagerender, pagegeometry, pageinteraction, pageoverlay); how the pages are arranged comes from the view mode (viewlayout)."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QScrollArea,
    QScrollBar,
    QWidget,
)

from . import docscroll, theme, viewlayout
from .pagegeometry import PageGeometryMixin
from .pageinteraction import PageInteractionMixin
from .pageoverlay import PageOverlayMixin
from .pagerender import PageRenderMixin
from .pagewidgets import PageWidget
from .viewlayout import PAGE_GAP


class PageView(PageOverlayMixin, PageInteractionMixin, PageGeometryMixin, PageRenderMixin, QScrollArea):
    """Page view. How the pages are arranged is the view mode (gui/viewlayout.py):

    single page (default): always exactly one page, centred. Inside the page it scrolls; at the end of the page
                 the next wheel-/page-down jumps to the next page (start), at the start to the previous one (end).
    continuous, facing pages, grid: all pages in the scroll area, one row below the other.
    """

    pageChanged = Signal(int)
    zoomChanged = Signal(float)
    viewMoved = Signal()  # scrolling/zoom/page -> redraw the rulers
    masterReady = Signal(int)  # page image ready -> derive the thumbnail from it
    infoReady = Signal()  # page data (boxes, rotation) arrived from the render process

    MASTER_FACTOR = 2.0  # page image = twice the whole-page size: zooming up to there without rendering anew
    MASTER_PIXELS = 16_000_000
    KEEP_MASTERS = 2  # keep page images ± this many pages around the visible ones

    JUMP_THRESHOLD = 120  # one mouse wheel notch; touchpad fractions are accumulated
    JUMP_COOLDOWN = 0.30  # s – prevents kinetic scrolling from skipping several pages

    def __init__(self, single: bool = True, mode: dict | None = None):
        super().__init__()
        self.setWidgetResizable(False)
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.setStyleSheet(f"QScrollArea {{ background: {theme.VIEW}; }} #pages {{ background: {theme.VIEW}; }}")
        self.doc = None
        self.sizes = []
        self.base = "page"  # width | page | actual – reference per page
        self.factor = 1.0  # zoom relative to the reference (Ctrl+mouse wheel, +/-)
        self.zoom = 1.0  # actual scale of the current page (display only)
        self.rotation = 0
        self.current = 0
        # how the pages are arranged (gui/viewlayout.py); mode = viewlayout.make() values, else the single switch
        self.view_mode = viewlayout.make(mode) if mode else viewlayout.for_single(single)
        self.ruler_page = None  # page under the mouse: the rulers and measuring refer to it
        self._acc = 0.0
        self._block_until = 0.0
        self.pages: list[PageWidget] = []
        self.sel = None  # text selection: (page, start character, end character)
        self._drag = None
        self._tp = {}  # page -> (PdfPage, PdfTextPage)
        self.imode = "text"  # mouse: text = select text; edit = edit mode (clicks go to edit_click)
        self.edit_click = None  # callback (page, x, y in page coordinates, shift)
        self.meas = None  # measuring: {"page", "a": (x, y) pt, "b": (x, y) pt | None, "done": bool}
        self.on_measure = None  # callback (text for the status bar)
        self.on_cursor = None  # callback (page widget, mouse position) for the rulers
        self.on_pipette = None  # callback (page, x, y) – colour pipette (imode "pipette")
        self.on_pipette_exit = None
        self.editor = None  # edit sidebar: press/drag/release/cursor (page coordinates)
        self._edrag = False
        self.overlay = {}  # page -> [(x0, y0, x1, y1, colour)] in page coordinates
        self._snap = {}  # page -> ([x edges], [y edges]) – snapping when measuring
        self._snap_prev = None  # Ctrl preview: (page, x, y, snapped?) – cross hairs before the first click
        self._snap_stuck = None  # hysteresis: {"x": edge, "y": edge} – where the cross hairs currently stick
        self.container = QWidget()
        self.container.setObjectName("pages")
        self.setWidget(self.container)
        self._timer = QTimer(self, singleShot=True, interval=30, timeout=self._render_visible)
        self._gen = 0  # document state: results of older states are discarded
        self.proof = None  # soft proof of the view (proof.proofed_render) or None
        self._pkey = ()  # and its key – images with a different soft proof are discarded
        self._rkey = None  # document in the render process
        self._src_path = None
        self._tmp = None  # own intermediate file for the render process
        self._local = False  # render in the program (render process not available / document cannot be loaded there)
        self._rfail = set()  # pages that failed in the render process
        self._pinfo = None  # per page boxes/rotation (renderproc.page_info) – without loading a page
        self._lazy_boxes = {}  # fallback: boxes via pdfium, only when needed
        self._chars = {}  # page -> character boxes (numpy) for the text cursor, "pending" = requested
        # single-page view: the scroll area only holds one page, so a scroll bar of our own stands for the
        # whole document (see docscroll.py); the area's own vertical bar is hidden meanwhile
        self._docbar = QScrollBar(Qt.Orientation.Vertical, self)
        self._docbar.setObjectName("bigScroll")  # Hias' scroll symbol on the handle, as on the normal bar
        self._docbar.setPageStep(docscroll.UNITS)
        self._docbar.setSingleStep(docscroll.UNITS // 10)
        self._docbar.hide()
        self._docbar_on = False
        self._docbar_busy = False  # the user is moving the bar: do not set its value from the view
        self._docbar.valueChanged.connect(self._docbar_moved)
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.verticalScrollBar().valueChanged.connect(lambda _v: self._sync_docbar())
        self.verticalScrollBar().valueChanged.connect(lambda _v: self.viewMoved.emit())
        self.horizontalScrollBar().valueChanged.connect(lambda _v: self.viewMoved.emit())

    # --------------------------------------------------------------- #
    def set_document(self, doc, keep_page: int | None = None, src=None, changed_pages=None):
        """src: path or bytes of the document for the render process (None = save from doc).
        changed_pages: editing (same number of pages) – the previous images stay as placeholders
        until the new ones are there; the edited pages are done first.
        """
        old = self.pages
        keep = changed_pages is not None and len(old) == len(doc)
        # editing: stay where the work is happening (do not jump to the top of the page)
        stay = (self.verticalScrollBar().value(), self.horizontalScrollBar().value()) if keep else None
        for w in self.pages:  # dispose of the pages of the previous document
            w.deleteLater()
        self._close_textpages()
        self.sel, self._drag = None, None
        self.meas = None
        self._snap = {}
        self._snap_prev = None
        self._snap_stuck = None
        self.doc = doc
        self.sizes = [doc.get_page_size(i) for i in range(len(doc))]
        # trim size/bleed and page orientation come from the render process (without loading pages in the program)
        self._pinfo, self._lazy_boxes, self._chars = None, {}, {}
        self.pages = [PageWidget(i, self) for i in range(len(doc))]
        for w in self.pages:
            w.setParent(self.container)
        if keep:
            # keep showing the old images as placeholders (no white flash), but render all anew:
            # an element used on several pages may have changed everywhere
            for w, o in zip(self.pages, old, strict=False):
                w.master, w.mkey, w.mstale = o.master, o.mkey, o.master is not None
        self._gen += 1
        self._rfail = set()
        self._open_render(src)
        self.current = min(keep_page or 0, max(0, len(self.pages) - 1))
        self.relayout()
        if stay is not None:
            self._restore_scroll(stay)
            QTimer.singleShot(0, lambda s=stay, g=self._gen: g == self._gen and self._restore_scroll(s))
            self.pageChanged.emit(self.current)
        else:
            self.goto(self.current, force=True)

    def _restore_scroll(self, pos):
        """Restore the scroll position (same page sizes and same zoom as before)."""
        self.verticalScrollBar().setValue(pos[0])
        self.horizontalScrollBar().setValue(pos[1])

    # ---------------- rendering (own process, see renderclient.py) ---------------- #

    @property
    def single(self) -> bool:
        """Single-page view: only the current page is shown."""
        return self.view_mode.shows_one_page

    def set_single(self, single: bool):
        """Switch between single-page and continuous view."""
        self.set_view_mode(viewlayout.for_single(single))

    def set_view_mode(self, mode):
        """Arrange the pages differently (a viewlayout.ViewMode). The zoom stays; with "fit width/page" the
        pages are fitted anew in the new arrangement. The view stays on the same page, as far down it as before."""
        cur = self.current
        share = self._share_in_page(cur)
        self._switching = True  # scroll signals of the rearrangement must not change the current page
        try:
            self.view_mode = mode
            self.ruler_page = None
            self.relayout()
            self._back_to(cur, share)
        finally:
            self._switching = False
        # the scroll ranges of the new arrangement may only be final after Qt's layout pass: once more then
        QTimer.singleShot(0, lambda: self._back_to(cur, share) if self.view_mode is mode else None)

    def _share_in_page(self, i: int) -> float:
        """How far down page i the top of the view is (0.0 = its top, 1.0 = its bottom)."""
        if not (0 <= i < len(self.pages)) or self.pages[i].height() <= 0:
            return 0.0
        w = self.pages[i]
        return min(max((self.verticalScrollBar().value() + PAGE_GAP - w.y()) / w.height(), 0.0), 1.0)

    def _back_to(self, i: int, share: float):
        """Show page i again, scrolled to ``share`` of its height (after a change of the arrangement)."""
        if not (0 <= i < len(self.pages)):
            return
        self._switching = True
        try:
            self.goto(i, force=True)
            if share > 0:
                vb = self.verticalScrollBar()
                vb.setValue(vb.value() + round(share * self.pages[i].height()))
        finally:
            self._switching = False
        self._sync_docbar()

    def _dpi_scale(self) -> float:
        return self.logicalDpiX() / 72.0

    @property
    def mode(self) -> str:
        """For the zoom display: width/page only without an extra factor, otherwise fixed."""
        return self.base if self.base != "actual" and abs(self.factor - 1) < 1e-3 else "fixed"

    def page_zoom(self, i: int) -> float:
        """Scale (1.0 = actual size) for page i. With width/page EVERY page is
        fitted on its own -> all pages appear equally large, no matter how large they really are.
        """
        pw, ph = self._rot_size(i)
        s = self._dpi_scale()
        vw, vh = self.view_mode.fit_area(self, i)
        if self.base == "width":
            base = vw / (pw * s)
        elif self.base == "page":
            base = min(vw / (pw * s), vh / (ph * s))
        else:
            base = 1.0
        return max(0.01, min(base * self.factor, 64.0))

    def effective_zoom(self) -> float:
        """Zoom factor of the current page."""
        return self.page_zoom(self.current) if self.sizes else self.zoom

    def relayout(self):
        """Recompute the sizes and positions of all page widgets for the current zoom and rotation."""
        if not self.doc:
            return
        dpi = self._dpi_scale()
        self.zoom = self.effective_zoom()
        self.view_mode.place(self, dpi)
        self._sync_docbar()
        self.zoomChanged.emit(self.zoom)
        self.viewMoved.emit()
        self._timer.start()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.relayout()

    # ---------------- scroll bar for the whole document (single-page view) ---------------- #
    def _sync_docbar(self):
        """Show the document scroll bar when it is needed and move it to where the view is."""
        bar = self._docbar
        want = bool(self.single and self.doc is not None and len(self.pages) > 1)
        if want != self._docbar_on:
            self._docbar_on = want
            self.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff if want else Qt.ScrollBarPolicy.ScrollBarAsNeeded
            )
            self.setViewportMargins(0, 0, bar.sizeHint().width() if want else 0, 0)
            bar.setVisible(want)
        if not want:
            return
        w = bar.sizeHint().width()
        hb = self.horizontalScrollBar()
        bar.setGeometry(self.width() - w, 0, w, self.height() - (hb.height() if hb.isVisible() else 0))
        bar.raise_()
        if self._docbar_busy:
            return
        vb = self.verticalScrollBar()
        bar.blockSignals(True)
        bar.setRange(0, docscroll.maximum(len(self.pages)))
        bar.setValue(docscroll.to_value(self.current, vb.value(), vb.maximum()))
        bar.blockSignals(False)

    def _docbar_moved(self, value: int):
        """The user moved the document scroll bar: show that page, scrolled as far as the bar says."""
        if not self._docbar_on or self._docbar_busy:
            return
        page, share = docscroll.from_value(value, len(self.pages))
        self._docbar_busy = True
        try:
            if page != self.current:
                self.goto(page)
            vb = self.verticalScrollBar()
            vb.setValue(round(share * vb.maximum()))
        finally:
            self._docbar_busy = False

    def _on_scroll(self, _):
        self._timer.start()
        if getattr(self, "_switching", False):
            return
        i = self.view_mode.page_at_scroll(self)
        if i is not None and i != self.current:
            self.current = i
            self.pageChanged.emit(i)

    # --------------------------------------------------------------- #
    def goto(self, i: int, at_end: bool = False, force: bool = False):
        """Show page ``i`` (``at_end``: scrolled to its bottom)."""
        if not (0 <= i < len(self.pages)):
            return
        self.view_mode.goto(self, i, at_end, force)
        self._acc = 0.0
        self.pageChanged.emit(i)

    def next_page(self):
        """Go to the next page (facing pages: the next spread, grid: the next row)."""
        self.goto(self.view_mode.step(self, self.current, 1))

    def prev_page(self, at_end: bool = False):
        """Go to the previous page (spread, row)."""
        self.goto(self.view_mode.step(self, self.current, -1), at_end=at_end)

    def set_zoom(self, mode: str, value: float | None = None):
        """mode: width | page  (factor 1)  or  fixed + value (scale, 1.0 = actual size)."""
        cur = self.current
        if mode in ("width", "page"):
            self.base, self.factor = mode, 1.0
        else:
            self.base, self.factor = "actual", max(0.01, min(value or 1.0, 64.0))
        self.relayout()
        self.goto(cur, force=True)

    def step_zoom(self, factor: float):
        """Zoom by ``factor`` around the centre of the view."""
        c = self.viewport().rect().center()
        self.zoom_at(factor, c)

    def zoom_at(self, factor: float, pos):
        """Zoom by `factor`; the point under `pos` (viewport coordinates) stays in place."""
        if not self.doc:
            return
        new_factor = max(0.02, min(self.factor * factor, 64.0))
        if abs(new_factor - self.factor) < 1e-5:
            return
        hb, vb = self.horizontalScrollBar(), self.verticalScrollBar()
        cx, cy = hb.value() + pos.x(), vb.value() + pos.y()
        in_row = [
            w for w in self.pages if w.isVisibleTo(self.container) and w.y() <= cy <= w.y() + w.height() + PAGE_GAP
        ]
        # several pages side by side (facing pages, grid): the one under the mouse, else the first of the row
        page = next((w for w in in_row if w.x() <= cx <= w.x() + w.width()), in_row[0] if in_row else None)
        if page is not None:
            fx = (cx - page.x()) / max(1, page.width())
            fy = (cy - page.y()) / max(1, page.height())
        self.factor = new_factor  # reference stays -> pages keep the same size relative to each other
        self.relayout()
        if page is not None:
            hb.setValue(int(page.x() + fx * page.width() - pos.x()))
            vb.setValue(int(page.y() + fy * page.height() - pos.y()))

    def _edge_jump(self, delta: float) -> bool:
        """delta < 0 = downwards. True if the view jumped to another page."""
        import time

        vb = self.verticalScrollBar()
        now = time.monotonic()
        if now < self._block_until:
            return True  # swallow the overrun after a jump
        down = delta < 0
        at_edge = vb.value() >= vb.maximum() if down else vb.value() <= vb.minimum()
        if not at_edge:
            self._acc = 0.0
            return False
        self._acc += abs(delta)
        if self._acc < self.JUMP_THRESHOLD:
            return True
        target = self.current + (1 if down else -1)
        if 0 <= target < len(self.pages):
            self.goto(target, at_end=not down)
            self._block_until = now + self.JUMP_COOLDOWN
        self._acc = 0.0
        return True

    def wheelEvent(self, e):
        # touchpads (esp. Windows Precision/macOS-like) often deliver only pixelDelta, angleDelta = 0
        ady = e.angleDelta().y() or e.pixelDelta().y() * 3
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            steps = ady / 120.0  # 1 notch = 120; touchpads deliver fractions
            if steps:
                self.zoom_at(1.15**steps, e.position().toPoint())
            e.accept()
            return
        dy = ady
        if self.view_mode.pages_at_edge and dy and self._edge_jump(dy):
            e.accept()
            return
        super().wheelEvent(e)

    def keyPressEvent(self, e):
        if self.imode == "measure" and e.key() == Qt.Key.Key_Escape:
            self.measure_clear()
            return
        if self.imode == "pipette" and e.key() == Qt.Key.Key_Escape:
            if self.on_pipette_exit is not None:
                self.on_pipette_exit()
            return
        arrows = {Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0), Qt.Key.Key_Up: (0, -1), Qt.Key.Key_Down: (0, 1)}
        if (
            self.imode == "edit"
            and e.key() in arrows
            and self.editor is not None
            and getattr(self.editor, "sel_box", None) is not None
            and hasattr(self.editor, "nudge")
        ):
            dx, dy = arrows[e.key()]  # move the selection step by step (Shift = ×10)
            self.editor.nudge(dx, dy, 10.0 if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1.0)
            return
        if self.view_mode.pages_at_edge and self.doc is not None:
            k = e.key()
            vb, hb = self.verticalScrollBar(), self.horizontalScrollBar()
            if k in (Qt.Key.Key_PageDown, Qt.Key.Key_Space) and vb.value() >= vb.maximum():
                self.next_page()
                return
            if k == Qt.Key.Key_PageUp and vb.value() <= vb.minimum():
                self.prev_page(at_end=True)
                return
            if k == Qt.Key.Key_Down and vb.value() >= vb.maximum():
                self.next_page()
                return
            if k == Qt.Key.Key_Up and vb.value() <= vb.minimum():
                self.prev_page(at_end=True)
                return
            if k in (Qt.Key.Key_Right, Qt.Key.Key_Left) and not hb.isVisible():
                self.next_page() if k == Qt.Key.Key_Right else self.prev_page()
                return
        super().keyPressEvent(e)

    # --------------------------------------------------------------- #
    # text selection
    # --------------------------------------------------------------- #

    # ---------------- page data without loading the page ---------------- #

    # --------------------------------------------------------------- #
    # ruler and measuring
    # --------------------------------------------------------------- #

    def rotate(self, delta: int):
        """Rotate the view by ``delta`` degrees (the document is not changed)."""
        cur = self.current
        self.rotation = (self.rotation + delta) % 360
        self.relayout()
        self.goto(cur, force=True)
