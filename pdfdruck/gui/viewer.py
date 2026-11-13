# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Acrobat-like main window: thumbnails on the left, continuous view, toolbar, page operations."""

from __future__ import annotations

from ..l10n import tr

import ctypes
import os

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_r
from PySide6.QtCore import QObject, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QCursor, QImage, QKeySequence, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QFrame,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStyle,
    QStyledItemDelegate,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import images
from . import theme
from .common import MAX_RENDER_EDGE, render_pixmap, responsive
from .icons import icon as svg_icon

from .. import convert as _convert

_ALL_EXT = sorted({".pdf"} | images.IMAGE_EXT | _convert.OFFICE_EXT)
OPEN_FILTER = ";;".join(
    [
        tr("Alle unterstützten") + " (" + " ".join(f"*{e} *{e.upper()}" for e in _ALL_EXT) + ")",
        tr("PDF-Dateien (*.pdf *.PDF)"),
        tr("Bilder") + " (" + " ".join(f"*{e}" for e in sorted(images.IMAGE_EXT)) + ")",
        tr("Office-Dokumente") + " (" + " ".join(f"*{e}" for e in sorted(_convert.OFFICE_EXT)) + ")",
    ]
)


def merge_files(parent, ctl, paths: list[str]):
    """Any files in order into one PDF document. Returns (doc, notes) or (None, [])."""
    import shutil
    import tempfile
    from PySide6.QtWidgets import QApplication, QProgressDialog

    work = tempfile.mkdtemp(prefix="passermark-merge-")
    out = pdfium.PdfDocument.new()
    notes = []
    dlg = QProgressDialog(tr("Füge zusammen …"), tr("Abbrechen"), 0, len(paths), parent)
    dlg.setWindowModality(Qt.WindowModality.WindowModal)
    dlg.setMinimumDuration(300)
    try:
        for i, p in enumerate(paths):
            dlg.setValue(i)
            dlg.setLabelText((tr("Wandle um: ") if _convert.is_office(p) else tr("Füge hinzu: ")) + os.path.basename(p))
            QApplication.processEvents()
            if dlg.wasCanceled():
                out.close()
                return None, []
            try:
                part = load_any(parent, ctl, p, work, notes)
            except Exception as e:
                lines = str(e).splitlines()
                box = QMessageBox(
                    QMessageBox.Icon.Warning,
                    tr("Umwandeln fehlgeschlagen"),
                    tr(
                        "„{0}“ konnte nicht umgewandelt werden.\n\nDiese Datei überspringen und mit den anderen weitermachen?"
                    ).format(os.path.basename(p)),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    parent,
                )
                box.setDetailedText("\n".join(lines))
                box.button(QMessageBox.StandardButton.Yes).setText(tr("Überspringen"))
                box.button(QMessageBox.StandardButton.No).setText(tr("Abbrechen"))
                r = box.exec()
                if r != QMessageBox.StandardButton.Yes:
                    out.close()
                    return None, []
                notes.append(tr("übersprungen: {0}").format(os.path.basename(p)))
                continue
            if part is None:  # password prompt cancelled
                notes.append(tr("übersprungen: {0} (Passwort)").format(os.path.basename(p)))
                continue
            out.import_pages(part)
            part.close()
        dlg.setValue(len(paths))
        return out, notes
    finally:
        dlg.close()
        shutil.rmtree(work, ignore_errors=True)


def ask_hdr(parent, paths: list[str], default_dpi: float = 96.0):
    """Report HDR photos with an extra image (gain map) and let the user choose the repair.
    -> options for images_to_document (None = no such images).
    """
    from .hdrdialog import hdr_options

    found = [(p, images.hdr_aux_info(p)) for p in paths]
    found = [(p, i) for p, i in found if i is not None]
    if not found:
        return None
    names = ", ".join(f"„{os.path.basename(p)}“" for p, _i in found[:3]) + (" …" if len(found) > 3 else "")
    opts = hdr_options(parent, [i for _p, i in found], names, default_dpi, tr("Unverändert öffnen (2 Seiten)"))
    return {"keep": True} if opts is None else opts


def load_any(parent, ctl, path, workdir=None, notes=None):
    """PDF (with password prompt), image or Office file -> pypdfium2 document (None = cancelled)."""
    import tempfile

    if images.is_image(path):
        return images.images_to_document([path], ctl.image_dpi, ask_hdr(parent, [path], ctl.image_dpi))
    if _convert.is_office(path):
        from PySide6.QtWidgets import QApplication

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            pdf, used = _convert.office_to_pdf(
                path, workdir or tempfile.mkdtemp(prefix="passermark-conv-"), ctl.cfg.get("office_converter", "auto")
            )
        finally:
            QApplication.restoreOverrideCursor()
        if notes is not None:
            notes.append(tr("{0}: umgewandelt mit {1}").format(os.path.basename(path), used))
        # load into memory so the working folder may be deleted
        with open(pdf, "rb") as f:
            return pdfium.PdfDocument(f.read())
    return load_pdf(parent, path)


from ..papersizes import UI_FORMATS as PAPER_NAMES  # mm, Hochformat – gemeinsame Formattabelle


def page_size_text(w_pt: float, h_pt: float) -> str:
    """Page size as text in mm, with the name of the paper size if it is a known one."""
    w, h = w_pt * 25.4 / 72, h_pt * 25.4 / 72
    lo, hi = sorted((w, h))
    name = next((n for n, (a, b) in PAPER_NAMES.items() if abs(lo - a) <= 1.5 and abs(hi - b) <= 1.5), None)
    orient = tr("quer") if w > h + 0.5 else tr("hoch")
    txt = tr("{0:.0f} × {1:.0f} mm").format(w, h)
    return f"{txt}  ({name} {orient})" if name else txt


def load_pdf(parent, path: str):
    """Open a PDF, asking for a password if needed. None on cancel/error."""
    password = None
    while True:
        try:
            return pdfium.PdfDocument(path, password=password)
        except pdfium.PdfiumError as e:
            if "password" in str(e).lower():
                password, ok = QInputDialog.getText(
                    parent,
                    tr("Passwort"),
                    tr("Passwort für {0}:").format(os.path.basename(path)),
                    QLineEdit.EchoMode.Password,
                )
                if not ok:
                    return None
            else:
                QMessageBox.critical(parent, tr("Fehler"), tr("Kann {0} nicht öffnen:\n{1}").format(path, e))
                return None


ZOOM_STEPS = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0, 6.4]
PAGE_GAP = 22


def _remove_quiet(path):
    if path:
        try:
            os.remove(path)
        except OSError:
            pass


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
        self.done.connect(self._deliver)
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
                continue
            self.done.emit(widget, key, out)

    @staticmethod
    def _deliver(widget, key, img):
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
        if self.master is not None:
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

    def smooth_ready(self, key, img):
        """Cleanly downscaled page image from the background – accept only if it still fits."""
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


class PageView(QScrollArea):
    """Page view.

    single=True  (default): always exactly one page, centered. Inside the page it
                 scrolls; at the end of the page the next wheel-/page-down jumps to
                 the next page (start), at the start of the page to the previous one (end).
    single=False: continuous as before.
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

    def __init__(self, single: bool = True):
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
        self.single = single
        self._acc = 0.0
        self._block_until = 0.0
        self.pages: list[PageWidget] = []
        self.sel = None  # text selection: (page, start character, end character)
        self._drag = None
        self._tp = {}  # page -> (PdfPage, PdfTextPage)
        self.imode = "text"  # Maus: text = Textauswahl; edit = Bearbeiten-Modus (Klicks an edit_click)
        self.edit_click = None  # callback (page, x, y in page coordinates, shift)
        self.meas = None  # Messung: {"page", "a": (x, y) pt, "b": (x, y) pt | None, "done": bool}
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
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)
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
            for w, o in zip(self.pages, old):
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

    def set_single(self, single: bool):
        """Switch between single-page and continuous view."""
        cur = self.current
        self.single = single
        self.relayout()
        self.goto(cur, force=True)

    def _dpi_scale(self) -> float:
        return self.logicalDpiX() / 72.0

    def _rot_size(self, i):
        w, h = self.sizes[i]
        return (h, w) if self.rotation % 180 else (w, h)

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
        vw = max(50, self.viewport().width() - 2 * PAGE_GAP - 4)
        vh = max(50, self.viewport().height() - 2 * PAGE_GAP)
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
        vw, vh = self.viewport().width(), self.viewport().height()
        if self.single:
            for w in self.pages:
                if w.index != self.current:
                    w.hide()
            w = self.pages[self.current]
            s = self.page_zoom(self.current) * dpi
            pw, ph = self._rot_size(self.current)
            ww, hh = int(pw * s), int(ph * s)
            cw, ch = max(ww + 2 * PAGE_GAP, vw), max(hh + 2 * PAGE_GAP, vh)
            w.setGeometry((cw - ww) // 2, max(PAGE_GAP, (ch - hh) // 2), ww, hh)
            self._rotate_master(w)
            w.show()
            self.container.resize(cw, ch)
        else:
            geo = []
            for i in range(len(self.sizes)):
                s = self.page_zoom(i) * dpi
                pw, ph = self._rot_size(i)
                geo.append((int(pw * s), int(ph * s), s))
            cw = max((max(g[0] for g in geo) if geo else 0) + 2 * PAGE_GAP, vw)
            y = PAGE_GAP
            for w, (ww, hh, s) in zip(self.pages, geo):
                w.setGeometry((cw - ww) // 2, y, ww, hh)
                self._rotate_master(w)
                w.show()
                y += hh + PAGE_GAP
            self.container.resize(cw, y)
        self.zoomChanged.emit(self.zoom)
        self.viewMoved.emit()
        self._timer.start()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.relayout()

    def _on_scroll(self, _):
        self._timer.start()
        if self.single:
            return
        mid = self.verticalScrollBar().value() + self.viewport().height() // 3
        for w in self.pages:
            if w.y() <= mid <= w.y() + w.height() + PAGE_GAP:
                if w.index != self.current:
                    self.current = w.index
                    self.pageChanged.emit(w.index)
                break

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
                self._rfail.add(req["page"])
                continue
            self.render_done(dict(req, doc=self._rkey), img, None)

    # --------------------------------------------------------------- #
    def goto(self, i: int, at_end: bool = False, force: bool = False):
        """Show page ``i`` (``at_end``: scrolled to its bottom)."""
        if not (0 <= i < len(self.pages)):
            return
        vb = self.verticalScrollBar()
        if self.single:
            if i != self.current or force:
                self.current = i
                self.relayout()
            vb.setValue(vb.maximum() if at_end else 0)
        else:
            self.current = i
            vb.setValue(self.pages[i].y() - PAGE_GAP)
        self._acc = 0.0
        self.pageChanged.emit(i)

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
                pass
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

    def next_page(self):
        """Go to the next page."""
        self.goto(self.current + 1)

    def prev_page(self, at_end: bool = False):
        """Go to the previous page."""
        self.goto(self.current - 1, at_end=at_end)

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
        page = next(
            (w for w in self.pages if w.isVisibleTo(self.container) and w.y() <= cy <= w.y() + w.height() + PAGE_GAP),
            None,
        )
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
        if self.single and dy and self._edge_jump(dy):
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
        if self.single and self.doc is not None:
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
    def _close_textpages(self):
        for pg, tp in self._tp.values():
            try:
                tp.close()
                pg.close()
            except Exception:
                pass
        self._tp = {}

    def _textpage(self, i):
        if i not in self._tp:
            if len(self._tp) > 6:
                self._close_textpages()
            pg = self.doc[i]
            self._tp[i] = (pg, pg.get_textpage())
        return self._tp[i]

    # ---------------- page data without loading the page ---------------- #
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
            except Exception:
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

    # --------------------------------------------------------------- #
    # ruler and measuring
    # --------------------------------------------------------------- #
    def ruler_geometry(self):
        """(top left page corner in viewport pixels, pixels per mm) of the current page – or None."""
        from PySide6.QtCore import QPoint

        if not self.doc or not (0 <= self.current < len(self.pages)):
            return None
        w = self.pages[self.current]
        pw, _ph = self._rot_size(self.current)
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
                import pypdfium2.raw as _r
                import ctypes as _ct

                for obj in pg.get_objects():
                    try:
                        t = obj.type
                        if t == _r.FPDF_PAGEOBJ_IMAGE:
                            l, b, r, t_ = obj.get_pos()
                            if r - l < 2000 and t_ - b < 2000:
                                ox |= {l, r}
                                oy |= {b, t_}
                        elif t == _r.FPDF_PAGEOBJ_PATH:
                            # single path segments: line ends, curve control points –
                            # precise snapping to real vector lines
                            l, b, r, t_ = obj.get_pos()
                            if r - l < 2000 and t_ - b < 2000:
                                ox |= {l, r}
                                oy |= {b, t_}
                                n_seg = 0
                                try:
                                    n_seg = _r.FPDFPath_CountSegments(obj.raw)
                                except Exception:
                                    pass
                                for si in range(min(n_seg, 4000)):
                                    try:
                                        seg = _r.FPDFPath_GetSegment(obj.raw, si)
                                        sx_, sy_ = _ct.c_float(), _ct.c_float()
                                        if _r.FPDFPath_GetSegmentPoint(seg, _ct.byref(sx_), _ct.byref(sy_)):
                                            ox.add(sx_.value)
                                            oy.add(sy_.value)
                                    except Exception:
                                        pass
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception:
            pass
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

    def paint_overlay(self, w, p):
        """Paint everything that lies on top of the page image: selection, marks, boxes, measurement."""
        from PySide6.QtGui import QPen

        try:
            if self.sel is not None and self.sel[0] == w.index:
                _pg, tp = self._textpage(w.index)
                n = tp.count_rects(self.sel[1], self.sel[2] - self.sel[1] + 1)
                col = QColor(theme.ACCENT)
                col.setAlpha(90)
                for k in range(n):
                    p.fillRect(self._rect_widget(w, *tp.get_rect(k)), col)
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
            sp = self._snap_prev
            if sp is not None and sp[0] == w.index:
                # Ctrl preview cross hairs; bold + circle when snapped to an edge
                px, py = self.to_widget(w, sp[1], sp[2])
                col = QColor("#2e9e4f") if sp[3] else QColor(theme.MUTED)
                pen = QPen(col, 2 if sp[3] else 1)
                if not sp[3]:
                    pen.setStyle(Qt.PenStyle.DashLine)
                p.setPen(pen)
                p.drawLine(px - 10, py, px + 10, py)
                p.drawLine(px, py - 10, px, py + 10)
                if sp[3]:
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawEllipse(QPointF(px, py), 4, 4)
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
                green = QColor("#2e9e4f")
                red = QColor("#e0301e")
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
        except Exception:
            pass

    def rotate(self, delta: int):
        """Rotate the view by ``delta`` degrees (the document is not changed)."""
        cur = self.current
        self.rotation = (self.rotation + delta) % 360
        self.relayout()
        self.goto(cur, force=True)


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
            p.setBrush(QColor(255, 198, 43, 60))
            p.setPen(QPen(QColor(theme.ACCENT), 2))
        else:
            p.setBrush(QColor("#2c2f33"))
            p.setPen(QPen(QColor("#3a3e43"), 1))
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


class _ThumbSource:
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


class _MergeList(QListWidget):
    """List in the merge dialog: reorder internally and drag files/folders in from the file manager."""

    dropped = Signal(list)
    reordered = Signal()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e):
        if e.mimeData().hasUrls():
            self.dropped.emit([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])
            e.acceptProposedAction()
            return
        super().dropEvent(e)
        self.reordered.emit()


class MergeDialog(QDialog):
    """Merge several PDFs/images in the desired order into one document. For large numbers (e.g. 110 plans):
    add a folder, drag files in, sort by name; files arriving later (Explorer) end up here.
    """

    def __init__(self, parent, start: list[str] | None = None):
        super().__init__(parent)
        self.setWindowTitle(tr("Dokumente zusammenführen"))
        self.resize(620, 520)
        self._manual = False  # reordered by hand: new files are only appended
        v = QVBoxLayout(self)
        v.addWidget(QLabel(tr("Reihenfolge = Reihenfolge im neuen Dokument (Bilder in tatsächlicher Größe):")))
        h = QHBoxLayout()
        self.lst = _MergeList()
        self.lst.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.lst.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.lst.setAcceptDrops(True)
        self.lst.dropped.connect(self.add_paths)
        self.lst.reordered.connect(self._set_manual)
        h.addWidget(self.lst, 1)
        b = QVBoxLayout()
        for text, fn in [
            (tr("Hinzufügen…"), self._add),
            (tr("Ordner hinzufügen …"), self._add_folder),
            (tr("Entfernen"), self._remove),
            ("▲ " + tr("Nach oben"), lambda: self._move(-1)),
            ("▼ " + tr("Nach unten"), lambda: self._move(1)),
            (tr("Nach Name sortieren"), self._sort),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(fn)
            b.addWidget(btn)
        b.addStretch()
        h.addLayout(b)
        v.addLayout(h, 1)
        self.lbl_count = QLabel()
        v.addWidget(self.lbl_count)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Zusammenführen"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        for p in start or []:
            self._append(p)
        self._count()

    def _count(self):
        n = self.lst.count()
        self.lbl_count.setText(tr("{0} Datei(en)").format(n))

    def _set_manual(self):
        self._manual = True

    def _append(self, p):
        it = QListWidgetItem(os.path.basename(p))
        it.setToolTip(p)
        it.setData(Qt.ItemDataRole.UserRole, p)
        self.lst.addItem(it)

    def add_paths(self, paths):
        """Add files (or folders) – no duplicates; sorted by name as long as the user has not reordered."""
        from .. import convert

        have = set(self.paths())
        new = []
        for p in paths:
            p = os.path.abspath(p)
            cand = [os.path.join(p, f) for f in sorted(os.listdir(p))] if os.path.isdir(p) else [p]
            for c in cand:
                if os.path.isfile(c) and convert.is_supported(c) and c not in have:
                    have.add(c)
                    new.append(c)
        if not new:
            return
        self.lst.setUpdatesEnabled(False)
        for p in new:
            self._append(p)
        if not self._manual:
            self._sort(manual=False)
        self.lst.setUpdatesEnabled(True)
        self._count()
        self.raise_()
        self.activateWindow()

    def _add(self):
        paths, _ = QFileDialog.getOpenFileNames(self, tr("Dateien hinzufügen"), "", OPEN_FILTER)
        self.add_paths(paths)

    def _add_folder(self):
        d = QFileDialog.getExistingDirectory(self, tr("Ordner hinzufügen …"))
        if d:
            self.add_paths([d])

    def _sort(self, manual=True):
        """By file name (natural: Plan 2 before Plan 10)."""
        import re

        def key(p):
            return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", os.path.basename(p))]

        paths = sorted(self.paths(), key=key)
        self.lst.clear()
        for p in paths:
            self._append(p)
        if manual:
            self._manual = False

    def _remove(self):
        for it in self.lst.selectedItems():
            self.lst.takeItem(self.lst.row(it))
        self._count()

    def _move(self, d):
        rows = sorted(self.lst.row(i) for i in self.lst.selectedItems())
        if not rows or (d < 0 and rows[0] == 0) or (d > 0 and rows[-1] == self.lst.count() - 1):
            return
        self._manual = True
        for r in rows if d < 0 else reversed(rows):
            it = self.lst.takeItem(r)
            self.lst.insertItem(r + d, it)
            it.setSelected(True)

    def paths(self):
        """The files in the order shown in the list."""
        return [self.lst.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.lst.count())]


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
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFont(theme.mono_font(10))
        self.setFixedWidth(64)
        self.setClearButtonEnabled(False)
        self.setStyleSheet(
            "QLineEdit { border: 1px solid #3a3e43; border-radius: 3px; padding: 1px 4px;"
            " background: " + theme.PANEL + "; color: " + theme.TEXT + "; }"
            "QLineEdit:focus { border-color: #8a9099; }"
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
    def _page_from_text(self) -> int | None:
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
            self.clearFocus()
            if p is not None and p - 1 != self._cur:
                self.gotoRequested.emit(p - 1)
            self._refresh()
            return
        super().keyPressEvent(e)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        p = self._page_from_text()
        if p is not None and self._n and p - 1 != self._cur:
            self.gotoRequested.emit(p - 1)
        self._refresh()

    def focusInEvent(self, e):
        """On focus show only the page number, selected, ready for typing."""
        super().focusInEvent(e)
        self.setText(str(self._cur + 1))  # when typing only the bare number
        self.selectAll()


class MainWindow(QMainWindow):
    """The document window: page view, sidebars, menus and toolbars for one open document."""

    def __init__(self, ctl):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.ctl = ctl
        self.resize(1280, 860)
        self.setAcceptDrops(True)
        self.doc = None
        self.path = None  # file on disk (None = never saved)
        self.display_name = ""
        self.modified = False

        self.view = PageView(single=getattr(ctl, "view_single", True))
        self._jobs = []  # running jobs (separate processes)
        # rulers at the top/left edge of the view (stay in place when scrolling)
        from PySide6.QtWidgets import QGridLayout

        central = QWidget()
        grid = QGridLayout(central)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)
        self.ruler_h = Ruler(self.view, True)
        self.ruler_v = Ruler(self.view, False)
        self.ruler_corner = QWidget()
        self.ruler_corner.setFixedSize(Ruler.SIZE, Ruler.SIZE)
        self.ruler_corner.setStyleSheet(f"background: {theme.PANEL};")
        grid.addWidget(self.ruler_corner, 0, 0)
        grid.addWidget(self.ruler_h, 0, 1)
        grid.addWidget(self.ruler_v, 1, 0)
        grid.addWidget(self.view, 1, 1)
        for r in (self.ruler_corner, self.ruler_h, self.ruler_v):
            r.hide()
        self._rulers_on = False
        self.setCentralWidget(central)
        self.view.viewMoved.connect(self._rulers_update)
        self.view.on_cursor = self._rulers_cursor
        self.view.pageChanged.connect(self._page_changed)
        self.view.infoReady.connect(lambda: self._page_changed(self.view.current))
        self.view.zoomChanged.connect(self._zoom_changed)

        # thumbnails (multi-selection for page operations)
        self.thumbs = ThumbList()
        self.thumbs.setViewMode(QListWidget.ViewMode.ListMode)
        self.thumbs.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.thumbs.setUniformItemSizes(False)
        self.thumbs.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.thumbs.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.thumbs.setItemDelegate(ThumbDelegate(self.thumbs))
        self.thumbs.setStyleSheet(
            f"QListWidget {{ background: {theme.BG}; border: none; }}"
            "QListWidget::item, QListWidget::item:selected { background: transparent; }"
        )
        self.thumbs.setMinimumWidth(110)
        self._thumb_resize = QTimer(self, singleShot=True, interval=200, timeout=self._requeue_thumbs)
        self.thumbs.resized.connect(self._thumb_resize.start)
        self.thumbs.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.thumbs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.thumbs.customContextMenuRequested.connect(self._thumb_menu)
        self.thumbs.itemClicked.connect(lambda it: self.view.goto(self.thumbs.row(it)))
        self.thumbs.pagesMoved.connect(self.move_pages_to)
        self.thumbs.zoomed.connect(self._thumb_zoom)
        dock = QDockWidget(tr("Seiten"), self)
        dock.setWidget(self._thumb_panel())
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable | QDockWidget.DockWidgetFeature.DockWidgetMovable
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self.resizeDocks([dock], [165], Qt.Orientation.Horizontal)
        self._thumb_queue = []
        self._thumb_timer = QTimer(self, interval=0, timeout=self._render_thumbs)
        self._thumb_src = _ThumbSource(self)  # thumbnails via the render process
        self.view.masterReady.connect(self._thumb_from_master)

        self._build_actions(dock)
        self.lbl_size = QLabel()
        self.lbl_size.setContentsMargins(8, 0, 8, 0)
        self.lbl_size.setFont(theme.mono_font(9.5))
        self.statusBar().addPermanentWidget(self.lbl_size)
        self._build_preflight(dock)
        self._build_color(dock)
        self._build_edit(dock)
        self._dock_widths = {}
        for d in (dock, self.pf_dock, self.color_dock, self.edit_dock):
            d.visibilityChanged.connect(lambda vis, d=d: self._dock_vis(d, vis))
        self._build_workspaces(dock)
        self.lbl_measure = QLabel()
        self.lbl_measure.setContentsMargins(8, 0, 8, 0)
        self.lbl_measure.setFont(theme.mono_font(9.5))
        self.lbl_measure.setToolTip(tr("Messung: Länge, waagrechter und senkrechter Abstand, Winkel"))
        self.statusBar().addPermanentWidget(self.lbl_measure)  # bottom far right, does not get in the way
        self.view.on_measure = self.lbl_measure.setText
        self.lbl_proof = QLabel()
        self.lbl_proof.setContentsMargins(8, 0, 8, 0)
        self.lbl_proof.setStyleSheet(f"color: {theme.ACCENT};")
        self.lbl_proof.hide()
        self.statusBar().addPermanentWidget(self.lbl_proof)
        self._update_title()

    # ---------------- workspaces ---------------- #
    WORKSPACES = ("view", "prep", "edit", "vdp", "plot", "auto")

    def _build_workspaces(self, pages_dock):
        """Second bar: choose the work area; the tools of that area to its right."""
        from PySide6.QtGui import QActionGroup

        self._pages_dock = pages_dock
        self.a_presets = self._act(tr("Preset-Ordner öffnen"), self._open_presets_dir, None, "folder_gear")
        self.a_cli = self._act(tr("Kommandozeile – Anleitung (PDF)"), self._open_cli_howto, None, "terminal")
        self.a_vdp_howto = self._act(tr("Variable Daten – Anleitung (PDF)"), self._open_vdp_howto, None, "book")
        self.a_examples = self._act(tr("Beispiele für Variable Daten holen …"), self._get_examples, None, "qr")
        tools = {
            "view": [(self.a_copy, tr("Text kopieren"))],
            "prep": [
                (self.a_preflight, tr("Prüfen")),
                (self.a_colorcheck, tr("Farbe")),
                (self.a_pipette, tr("Pipette")),
                (self.a_press, tr("Für Druckerei")),
                (self.a_manip_cmyk, tr("CMYK")),
                (self.a_manip_crop, tr("Beschneiden")),
                (self.a_cut, tr("CutContour")),
                (self.a_separate, tr("Objekte trennen")),
                (self.a_repair, tr("Reparieren")),
            ],
            "edit": [
                (self.a_edit, tr("Text/Ebenen")),
                (self.a_pipette, tr("Pipette")),
                (self.a_ins_after, tr("Einfügen")),
                (self.a_delete, tr("Löschen")),
                (self.a_rot_l, tr("Links drehen")),
                (self.a_rot_r, tr("Rechts drehen")),
                (self.a_up, tr("Nach vorne")),
                (self.a_down, tr("Nach hinten")),
                (self.a_split, tr("Teilen")),
                (self.a_merge, tr("Zusammenführen")),
                (self.a_export, tr("Exportieren")),
            ],
            "vdp": [
                (self.a_vdp, tr("Variable Daten")),
                (self.a_data, tr("Daten erfassen")),
                (self.a_examples, tr("Beispiele")),
                (self.a_vdp_howto, tr("Anleitung")),
            ],
            "plot": [(self.a_plan, tr("Plandruck")), (self.a_poster, tr("Posterdruck")), (self.a_rolls, tr("Rollen"))],
            "auto": [(self.a_presets, tr("Presets")), (self.a_cli, tr("Anleitung"))],
        }
        self.addToolBarBreak()
        tb = self.ws_bar = self.addToolBar(tr("Arbeitsbereich"))
        tb.setObjectName("workspaces")
        tb.setMovable(False)
        tb.setIconSize(QSize(18, 18))
        grp = QActionGroup(self)
        grp.setExclusive(True)
        self.ws_actions = {}
        names = {
            "view": tr("Anzeigen & Drucken"),
            "prep": tr("Druckaufbereitung"),
            "edit": tr("Bearbeiten"),
            "vdp": tr("Variable Daten"),
            "plot": tr("Plan & Poster"),
            "auto": tr("Automatisierung"),
        }
        for key in self.WORKSPACES:
            a = QAction(names[key], self)
            a.setCheckable(True)
            a.setData(key)
            grp.addAction(a)
            tb.addAction(a)
            btn = tb.widgetForAction(a)
            if isinstance(btn, QToolButton):
                btn.setObjectName("workspace")
            self.ws_actions[key] = a
        tb.setStyleSheet(
            f"QToolButton#workspace {{ padding: 3px 10px; border-bottom: 2px solid transparent; }}"
            f"QToolButton#workspace:checked {{ color: {theme.ACCENT}; border-bottom: 2px solid {theme.ACCENT};"
            f" background: transparent; }}"
        )
        # The tools of the workspace live in their own bar: if the window gets narrow, it moves to the next
        # row (instead of disappearing behind the » arrow) – see _fit_toolbars
        tb = self.ws_tools_bar = self.addToolBar(tr("Werkzeuge des Arbeitsbereichs"))
        tb.setObjectName("workspace_tools")
        tb.setMovable(False)
        tb.setIconSize(QSize(18, 18))
        self.ws_tools = {}
        for key, acts in tools.items():
            holders = []
            for a, text in acts:
                a.setIconText(text)  # short text for bars; menus keep showing the full text
                b = QToolButton()
                b.setDefaultAction(a)
                b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                holders.append(tb.addWidget(b))
            self.ws_tools[key] = holders
        grp.triggered.connect(lambda a: self.set_workspace(a.data()))
        from .. import l10n

        key = l10n.load_settings().get("workspace", "view")
        self.set_workspace(key if key in self.ws_actions else "view", remember=False)

    def _fit_toolbars(self):
        """Toolbar of the workspace next to the workspaces if there is room – otherwise in its own row."""
        tb, tt = getattr(self, "ws_bar", None), getattr(self, "ws_tools_bar", None)
        if tb is None or tt is None:
            return
        want = tb.sizeHint().width() + tt.sizeHint().width() + 24 > self.width()
        if want != bool(self.toolBarBreak(tt)):
            if want:
                self.insertToolBarBreak(tt)
            else:
                self.removeToolBarBreak(tt)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit_toolbars()

    def set_workspace(self, key: str, remember: bool = True):
        """Switch to workspace ``key`` and show its tools (``remember``: store it as the user's choice)."""
        self.workspace = key
        self.ws_actions[key].setChecked(True)
        for k, holders in self.ws_tools.items():
            for h in holders:
                h.setVisible(k == key)
        self._fit_toolbars()
        if key != "edit" and self.a_edit.isChecked():
            self.a_edit.setChecked(False)  # edit mode belongs to the Edit area
        if key == "prep":
            self.pf_dock.show()
            self.pf_dock.raise_()
        elif key == "edit":
            self._pages_dock.show()
            if not self.a_edit.isChecked():
                self.a_edit.setChecked(True)  # start edit mode: fill the dock + lists
            self.edit_dock.raise_()  # bring the dock in front of the page overview
        elif self._pages_dock.isVisible():
            self._pages_dock.raise_()
        if remember:
            from .. import l10n

            st = l10n.load_settings()
            if st.get("workspace") != key:
                st["workspace"] = key
                try:
                    l10n.save_settings(st)
                except OSError:
                    pass

    @staticmethod
    def licenses_path() -> str:
        """Folder "licenses" next to the program (installer/AppImage); from the source code: LICENSE."""
        from .. import platform as _pl

        for d in _pl.app_dirs():
            p = os.path.join(d, "licenses")
            if os.path.isdir(p):
                return p
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        return os.path.join(root, "LICENSE")

    def _open_licenses(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        p = self.licenses_path()
        if not os.path.exists(p):
            QMessageBox.information(self, tr("Lizenzen"), tr("Passermark steht unter der GPL-3.0 (oder später)."))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(p))

    def _open_presets_dir(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from .. import presets

        d = presets.root_dir()
        os.makedirs(d, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(d))

    # ---------------- edit mode (text and layers) ---------------- #
    def _build_edit(self, pages_dock):
        from .editpanel import EditPanel

        self.edit_panel = EditPanel(self)

        class _Dock(QDockWidget):
            def closeEvent(dock_self, e):  # the close button ends edit mode
                self.a_edit.setChecked(False)
                e.accept()

        self.edit_dock = _Dock(tr("Bearbeiten"), self)
        self.edit_dock.setWidget(self._dock_scroll(self.edit_panel))
        self.edit_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable | QDockWidget.DockWidgetFeature.DockWidgetMovable
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.edit_dock)
        self.tabifyDockWidget(pages_dock, self.edit_dock)
        self.edit_dock.hide()
        pages_dock.raise_()
        self.edit_dock.visibilityChanged.connect(lambda vis: vis and self.edit_panel.refresh())
        self.view.edit_click = self.edit_panel.page_click
        self.view.editor = self.edit_panel
        self.view.pageChanged.connect(lambda _p: self.a_edit.isChecked() and self.edit_panel.refresh())

    # ---------------- rulers and measuring ---------------- #
    def _show_rulers(self, on: bool):
        self._rulers_on = bool(on)
        for r in (self.ruler_corner, self.ruler_h, self.ruler_v):
            r.setVisible(on)
        if not on and self.a_measure.isChecked():
            self.a_measure.setChecked(False)
        self._rulers_update()

    def _rulers_update(self):
        if self._rulers_on:
            self.ruler_h.update()
            self.ruler_v.update()

    def _rulers_cursor(self, w, pos):
        if not self._rulers_on:
            return  # only compute when the rulers are visible
        gpos = w.mapToGlobal(pos.toPoint())
        self.ruler_h.cursor_px = gpos
        self.ruler_v.cursor_px = gpos
        self._rulers_update()

    # ---------------- soft proof ---------------- #
    def _toggle_proof(self, on: bool):
        from .softproofdialog import build_spec, load_saved

        spec = build_spec(self.session.cfg, load_saved()) if on else None
        if on and spec is None:
            self.softproof_dialog()  # nothing chosen yet (or the profile is gone): set up
            return
        self._apply_proof(spec)

    def _apply_proof(self, spec):
        from .. import proof

        self.view.set_proof(spec)
        self.lbl_proof.setText(proof.describe_spec(spec))
        self.lbl_proof.setVisible(bool(spec))
        if bool(spec) != self.a_proof.isChecked():
            self.a_proof.blockSignals(True)
            self.a_proof.setChecked(bool(spec))
            self.a_proof.blockSignals(False)

    def softproof_dialog(self):
        """Open the dialog for setting up the soft proof."""
        from .softproofdialog import SoftproofDialog, build_spec, load_saved

        dlg = getattr(self, "_proof_dlg", None)
        if dlg is None:
            dlg = SoftproofDialog(self, self.session.cfg)
            responsive(dlg)  # not modal (show instead of exec): adapt ourselves
            dlg.changed.connect(self._apply_proof)
            self._proof_dlg = dlg
        dlg.show()
        dlg.raise_()
        spec = build_spec(self.session.cfg, load_saved())
        if spec:
            self._apply_proof(spec)
        else:
            self._apply_proof(None)

    def _proof_for_choice(self, choice):
        """Colour check → soft proof: show this printing condition in the soft proof."""
        from .softproofdialog import build_spec, load_saved, save

        saved = dict(load_saved(), key=choice["key"])
        save(saved)
        self._proof_dlg = None  # read the selection anew
        spec = build_spec(self.session.cfg, saved)
        if spec:
            self._apply_proof(spec)

    # ---------------- colour ---------------- #
    def _build_color(self, pages_dock):
        from .colorpanel import ColorPanel

        self.color_panel = ColorPanel(self)
        responsive(self.color_panel)
        self.color_panel.data_fn = lambda: self._doc_bytes() if self.doc is not None else None
        self.color_panel.cfg_fn = lambda: self.session.cfg
        self.color_panel.goto_spot.connect(lambda p, box: self.view.show_spot(p - 1, box))
        self.color_panel.action_requested.connect(self._color_action)
        self.color_panel.proof_requested.connect(self._proof_for_choice)
        self.color_dock = QDockWidget(tr("Farbe"), self)
        self.color_dock.setWidget(self._dock_scroll(self.color_panel))
        self.color_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable | QDockWidget.DockWidgetFeature.DockWidgetMovable
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.color_dock)
        self.tabifyDockWidget(pages_dock, self.color_dock)
        self.color_dock.hide()

    def color_check(self):
        """Show the colour panel and start the colour check."""
        if self.doc is None:
            return
        self.color_panel.reload_choices()
        self.color_dock.show()
        self.color_dock.raise_()
        self.color_panel.start()

    def _color_refresh(self):
        """Papers/profiles changed: read the selection in colour check and soft proof anew."""
        from .. import colorlab

        colorlab._WHITE_CACHE.clear()
        self._proof_dlg = None
        if hasattr(self, "color_panel"):
            self.color_panel.reload_choices()
            if self.color_dock.isVisible() and self.color_panel.facts is not None:
                self.color_panel.start()

    def materials_dialog(self, select: str = "", measure: bool = False):
        """Open "Papiere und Messungen"."""
        from .materialsdialog import MaterialsDialog

        dlg = MaterialsDialog(self, self.session.cfg, select, measure)
        dlg.changed.connect(self._color_refresh)
        dlg.exec()

    def standard_profiles(self, surface: str = ""):
        """Open the dialog for downloading standard profiles."""
        from .materialsdialog import StandardProfilesDialog

        dlg = StandardProfilesDialog(self, surface)
        dlg.exec()
        if dlg.fetched:
            self._color_refresh()

    def _color_help(self):
        from .materialsdialog import show_help

        show_help(self)

    def press_dialog(self):
        """Open the wizard "Für Druckerei ausgeben"."""
        if self.doc is None:
            return
        from .colorpanel import load_choice
        from .pressdialog import PressDialog

        ch = load_choice()
        base = os.path.splitext(self.display_name or tr("Dokument"))[0]
        folder = (
            os.path.dirname(self.path) if self.path else (getattr(self, "_suggest_dir", "") or os.path.expanduser("~"))
        )
        dlg = PressDialog(
            self,
            self._doc_bytes,
            self.session.cfg,
            os.path.join(folder, base + tr("_Druck") + ".pdf"),
            ch.get("key", ""),
            ch.get("intent", ""),
            int(ch.get("tac", 0) or 0),
        )
        dlg.open_result.connect(lambda path: self.ctl.open_paths([path], tab_of=self))
        dlg.exec()

    def _ask_rgb(self, target_name: str) -> str:
        """Always ask about RGB: "convert" | "keep" | "" (cancelled)."""
        box = QMessageBox(
            QMessageBox.Icon.Question,
            tr("RGB im Dokument"),
            tr(
                "Die Datei enthält RGB. Nach „{0}“ umwandeln oder RGB mit Profil weitergeben (die Druckerei rechnet "
                "um)?"
            ).format(target_name),
            parent=self,
        )
        b_conv = box.addButton(tr("Umwandeln"), QMessageBox.ButtonRole.AcceptRole)
        b_keep = box.addButton(tr("Mit Profil weitergeben"), QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        return "convert" if box.clickedButton() is b_conv else "keep" if box.clickedButton() is b_keep else ""

    def _color_action(self, kind: str, p: dict):
        from .. import colorlab, core, pressexport

        p = p or {}
        if kind == "press":
            self.press_dialog()
        elif kind in ("convert", "embed_oi"):
            if self.doc is None or not p.get("target"):
                return
            rgb = "convert"
            if p.get("has_rgb"):
                rgb = self._ask_rgb(colorlab.profile_desc(p["target"]))
                if not rgb:
                    return
            s = pressexport.PressSettings(
                target=p["target"],
                intent=p.get("intent") or "relative",
                cmyk_mode=p.get("cmyk_mode") or "rgb_only" if kind == "convert" else "none",
                source=p.get("source") or "",
                rgb=rgb,
                tac_limit=int(p.get("tac_limit") or 0),
                material=p.get("material") or "",
            )
            self.start_job("press", core.settings_to_dict(s), suffix=tr("_Druck"), title=tr("Farbe"))
        elif kind == "preflight":
            self.pf_dock.show()
            self.pf_dock.raise_()
            self._pf_start(force=True)
        elif kind == "measure":
            mid = p.get("material") or ""
            m = colorlab.material_by_id(self.session.cfg, mid) if mid else None
            if m is not None and m.get("scope") == "admin":
                if (
                    QMessageBox.question(
                        self,
                        tr("Papier messen"),
                        tr(
                            "„{0}“ ist ein Papier der Verwaltung (für alle). Als eigenes Papier übernehmen und messen? "
                            "Ändern für alle geht unter Verwaltung → Standardeinstellungen → Materialien."
                        ).format(m.get("name") or mid),
                    )
                    != QMessageBox.StandardButton.Yes
                ):
                    return
                from .. import usercolor

                mats = usercolor.load_materials()
                n = {k: v for k, v in m.items() if k in usercolor.FIELDS}
                n["id"] = usercolor.new_id(m.get("name") or mid, {x["id"] for x in mats})
                mats.append(n)
                try:
                    usercolor.save_materials(mats)
                except (OSError, ValueError) as e:
                    QMessageBox.warning(self, tr("Papiere"), str(e))
                    return
                mid = n["id"]
            self.materials_dialog(mid, measure=bool(mid))
        elif kind == "get_profiles":
            self.standard_profiles(p.get("surface") or "")
        elif kind == "choose_target":
            self.color_panel.focus_choice()

    def _show_boxes(self, on: bool):
        self.view.show_boxes = bool(on)
        for w in self.view.pages:
            w.update()
        from .. import l10n

        st = l10n.load_settings()
        if st.get("show_trim", True) != bool(on):
            st["show_trim"] = bool(on)
            try:
                l10n.save_settings(st)
            except OSError:
                pass

    # ---------------- colour pipette ---------------- #
    def _pipette_mode(self, on: bool):
        if on:
            if self.a_measure.isChecked():
                self.a_measure.setChecked(False)
            if getattr(self, "pipette_dlg", None) is None:
                from .pipettedialog import PipetteDialog

                self.pipette_dlg = PipetteDialog(self)
                self.pipette_dlg.picked.connect(self._pipette_picked)
                self.pipette_dlg.closed.connect(lambda: self.a_pipette.setChecked(False))
            self.view.on_pipette = self.pipette_dlg.measure
            self.view.on_pipette_exit = lambda: self.a_pipette.setChecked(False)
            self.view.imode = "pipette"
            self.view.sel = None
            self.pipette_dlg.show()
            self.pipette_dlg.raise_()
            self.statusBar().showMessage(tr("Farbpipette: auf die Seite klicken · Esc = beenden"), 6000)
        else:
            if self.view.imode == "pipette":
                self.view.imode = "edit" if self.a_edit.isChecked() else "text"
            dlg = getattr(self, "pipette_dlg", None)
            if dlg is not None and dlg.isVisible():
                dlg.blockSignals(True)
                dlg.hide()
                dlg.blockSignals(False)

    def _pipette_picked(self, kind: str, vals):
        self.edit_panel._last_color = (kind, tuple(vals))
        self.statusBar().showMessage(tr("Farbe übernommen – Bearbeiten → „Farbe …“ verwendet sie."), 5000)

    def _measure_mode(self, on: bool):
        if on and self.a_pipette.isChecked():
            self.a_pipette.setChecked(False)
        if on:
            if self.a_edit.isChecked():
                self.a_edit.setChecked(False)  # Edit and Measure are mutually exclusive
            self.view.imode = "measure"
            self.view.sel = None
            if not self.a_rulers.isChecked():
                self.a_rulers.setChecked(True)
            self.statusBar().showMessage(
                tr("Messen: 1. Klick Anfang, 2. Klick Ende · Umschalt = waagrecht/senkrecht/45° · Esc = abbrechen"),
                8000,
            )
        else:
            if self.view.imode == "measure":
                self.view.imode = "text"
            self.view.measure_clear()

    def _edit_mode(self, on: bool):
        if on and self.a_measure.isChecked():
            self.a_measure.setChecked(False)
        if self.a_pipette.isChecked():
            self.a_pipette.setChecked(False)
        if on and self.edit_panel.rulers_wanted() and not self.a_rulers.isChecked():
            self.a_rulers.setChecked(True)  # rulers while editing (can be switched off in the Move section)
        if on and getattr(self, "workspace", "edit") != "edit":
            self.set_workspace("edit")
        self.view.imode = "edit" if on else "text"
        self.view.sel = None
        if on:
            self.edit_dock.show()
            self.edit_dock.raise_()
            self.edit_panel.refresh()
            self.statusBar().showMessage(tr("Bearbeiten-Modus: Textzeile bzw. Ebene auf der Seite anklicken."), 6000)
        else:
            self.view.overlay = {}
            self.edit_dock.hide()
            for w in self.view.pages:
                w.update()

    # ---------------- Preflight (document check) ---------------- #
    def _build_preflight(self, pages_dock):
        from .preflightpanel import PreflightPanel

        self.pf_panel = PreflightPanel(self)
        responsive(self.pf_panel)
        self.pf_panel.data_fn = self._doc_bytes
        self.pf_panel.file_fn = self._file_bytes
        self.pf_panel.result_ready.connect(self._pf_result)
        self.pf_panel.job_requested.connect(
            lambda kind, s, suffix, title: self.start_job(
                kind,
                s,
                suffix=suffix,
                title=title,
                src_data=self.pf_panel.take_job_data() if kind == "shrink" else None,
            )
        )
        self.pf_panel.goto_page.connect(lambda p: self.view.goto(p - 1))
        self.pf_panel.goto_spot.connect(lambda p, box: self.view.show_spot(p - 1, box))
        self.pf_panel.recheck.connect(lambda: self._pf_start(force=True))
        self.pf_dock = QDockWidget(tr("Prüfung"), self)
        self.pf_dock.setWidget(self._dock_scroll(self.pf_panel))
        self.pf_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable | QDockWidget.DockWidgetFeature.DockWidgetMovable
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.pf_dock)
        self.tabifyDockWidget(pages_dock, self.pf_dock)
        pages_dock.raise_()
        self.btn_pf = QPushButton("")
        self.btn_pf.setFlat(True)
        self.btn_pf.setToolTip(tr("Dokumentprüfung anzeigen"))
        self.btn_pf.clicked.connect(lambda: (self.pf_dock.show(), self.pf_dock.raise_()))
        self.btn_pf.hide()
        self.statusBar().addPermanentWidget(self.btn_pf)
        self._pf_timer = QTimer(self, singleShot=True, interval=700, timeout=self._pf_start)
        self._pf_gen = 0
        self._pf_worker = None

    def _doc_bytes(self) -> bytes:
        import io

        buf = io.BytesIO()
        self.doc.save(buf)
        return buf.getvalue()

    def _file_bytes(self) -> bytes:
        """The file as on disk (opened unchanged, not encrypted) – otherwise the current state.
        For size/shrinking: pdfium re-saves and would otherwise blur what is really in the file.
        """
        p = self.path
        if p and not self.modified and p.lower().endswith(".pdf") and os.path.isfile(p):
            try:
                import pikepdf

                with pikepdf.open(p) as pdf:
                    enc = pdf.is_encrypted
                if not enc:
                    with open(p, "rb") as f:
                        return f.read()
            except Exception:
                pass
        return self._doc_bytes()

    def _pf_start(self, force=False):
        from .. import l10n

        if self.doc is None:
            return
        if not force and not l10n.load_settings().get("preflight_on_open", True):
            return
        self._pf_gen += 1
        gen = self._pf_gen
        self.pf_panel.set_busy()
        self.btn_pf.setText("… " + tr("Prüfe"))
        self.btn_pf.show()
        # own process: does not slow the interface down (Python threads share one lock), no pdfium
        # in the program; the file (unchanged) is checked, or the state that the preview shows too
        from .renderclient import RenderService

        svc = RenderService.get("analysis")
        path = None
        if svc.ok:
            if (
                not self.modified
                and self.path
                and self.path.lower().endswith(".pdf")
                and os.path.isfile(self.path)
                and not self.view._local
            ):
                path = self.path
            elif self.view._src_path and os.path.isfile(self.view._src_path) and not self.view._local:
                path = self.view._src_path
        if path is None:
            self._pf_start_thread(gen)
            return

        def got(err, rep, gen=gen):
            if gen != self._pf_gen or self.doc is None:
                return  # outdated (the document has changed in the meantime)
            if err or rep is None:
                self._pf_start_thread(gen)  # fallback: in the program
            else:
                self._pf_show(rep)

        svc.call("preflight", {"path": path, "deep_layers": True}, got)

    def _pf_show(self, rep):
        try:  # size against the default printer (paper sizes)
            from .. import preflight, printjob

            prn = printjob.default_printer(self.session)
            if prn:
                preflight.add_device_issues(rep, self.session.caps_for(prn), prn)
        except Exception:  # noqa: BLE001 – die Prüfung darf daran nie scheitern
            pass
        self.pf_panel.set_report(rep)
        c = rep.counts()
        if c["error"] or c["warning"]:
            self.btn_pf.setText("⚠ " + tr("{0} Fehler · {1} Warnung(en)").format(c["error"], c["warning"]))
            self.btn_pf.setStyleSheet(f"color: {theme.ERROR if c['error'] else theme.ACCENT};")
        else:
            self.btn_pf.setText("✓ " + tr("Prüfung OK"))
            self.btn_pf.setStyleSheet(f"color: {theme.MUTED};")

    def _pf_start_thread(self, gen):
        """Fallback without the analysis process: pikepdf part in a background thread, pdfium part in the window."""
        from .preflightpanel import _Worker
        from .. import preflight

        try:
            # unchanged: check the file itself (no re-saving in the main window, size as on disk)
            data = self._doc_bytes() if self.modified else self._file_bytes()
        except Exception as e:
            self.pf_panel.set_error(str(e))
            return
        w = _Worker(lambda d: preflight.analyze(d, True, pdfium_parts=False), data)

        def done(rep, err, gen=gen, w=w):
            if gen != self._pf_gen:
                return  # outdated (document has changed in the meantime)
            if err:
                self.pf_panel.set_error(err)
                self.btn_pf.setText("⚠ " + tr("Prüfung fehlgeschlagen"))
                return
            try:
                preflight.finish(rep, data)  # pdfium parts in the main thread
            except Exception:
                pass
            self._pf_show(rep)

        w.done.connect(done)
        self._pf_worker = w
        w.start()

    def _pf_result(self, data: bytes, suffix: str, notes: list):
        import pypdfium2 as pdfium

        self._open_result(pdfium.PdfDocument(data), suffix, notes)

    @property
    def session(self):
        """The print session shared by all windows."""
        return self.ctl.session

    # ================================================================ #
    # actions / menus / toolbar
    # ================================================================ #
    def _act(self, text, slot, shortcut=None, icon=None):
        if isinstance(icon, str):
            a = QAction(svg_icon(icon), text, self)
        elif icon is not None:
            a = QAction(self.style().standardIcon(icon), text, self)
        else:
            a = QAction(text, self)
        a.triggered.connect(slot)
        if shortcut:
            seq = shortcut if isinstance(shortcut, list) else [shortcut]
            a.setShortcuts([QKeySequence(k) for k in seq])
        self.addAction(a)
        return a

    def _build_actions(self, dock):
        SP = QStyle.StandardPixmap
        A = self._act
        self.a_open = A(tr("Öffnen…"), self.open_dialog, QKeySequence.StandardKey.Open, "open")
        self.a_newwin = A(tr("Neues Fenster"), lambda: self.ctl.new_window(), "Ctrl+N")
        self.a_newtab = A(tr("Neuer Reiter"), lambda: self._new_tab(), "Ctrl+Shift+N")
        self.a_detach = A(tr("Reiter in eigenes Fenster lösen"), self._detach, None)
        self.a_save = A(tr("Speichern"), self.save, QKeySequence.StandardKey.Save, "save")
        self.a_saveas = A(tr("Speichern unter…"), self.save_as, "Ctrl+Shift+S")
        self.a_merge = A(tr("Dokumente zusammenführen…"), self.merge_dialog, "Ctrl+M", "merge")
        self.a_print = A(tr("Drucken…"), self.print_dialog, QKeySequence.StandardKey.Print, "print")
        self.a_repair = A(tr("Reparieren, optimieren, Passwort…"), self.repair_dialog, "Ctrl+Shift+R", "repair")
        self.a_shrink = A(tr("Datei verkleinern …"), self.shrink_dialog, None, "repair")
        self.a_close = A(tr("Schließen"), self.close, QKeySequence.StandardKey.Close)
        self.a_props = A(tr("Eigenschaften …"), self.properties_dialog, "Ctrl+D", "info")
        self.a_copy = A(tr("Markierten Text kopieren"), self.copy_text, QKeySequence.StandardKey.Copy, "copy")
        self.a_seltext = A(tr("Text der Seite markieren"), lambda: self.view.select_page_text(), "Ctrl+Alt+A", "select")
        self.a_settings = A(tr("Einstellungen …"), self.settings_dialog, "Ctrl+,", "settings")
        self.a_manip = A(
            tr("CMYK und Beschneiden in einem Schritt …"), lambda: self.manip_dialog("all"), "Ctrl+Shift+M", "cmyk"
        )
        self.a_manip_cmyk = A(tr("CMYK-Umwandlung …"), lambda: self.manip_dialog("cmyk"), None, "cmyk")
        self.a_manip_crop = A(tr("Auf Format beschneiden …"), lambda: self.manip_dialog("crop"), None, "crop")
        self.a_separate = A(
            tr("Objekte trennen (Einzelseiten ohne Weißraum) …"), self.separate_dialog, None, "separate"
        )
        self.a_cut = A(tr("CutContour erzeugen (Schneideplotter) …"), self.cut_dialog, None, "cut")
        self.a_vdp = A(tr("Variable Daten (Nummern, QR-/Barcodes, CSV) …"), self.vdp_dialog, "Ctrl+Shift+D", "vdp")
        self.a_data = A(
            tr("Daten erfassen (Tabelle für Visitenkarten, WLAN, Codes …) …"), self.data_dialog, None, "table"
        )
        self.a_edit = A(tr("Text und Ebenen bearbeiten"), lambda: None, "Ctrl+T", "edit")
        self.a_edit.setCheckable(True)
        self.a_edit.toggled.connect(self._edit_mode)

        self.a_ins_before = A(tr("Seiten einfügen – vor Auswahl…"), lambda: self.insert_dialog("before"))
        self.a_ins_after = A(
            tr("Seiten einfügen – nach Auswahl…"), lambda: self.insert_dialog("after"), "Ctrl+I", "insert"
        )
        self.a_ins_end = A(tr("Seiten anhängen (am Ende)…"), lambda: self.insert_dialog("end"), "Ctrl+Shift+I")
        self.a_blank_before = A(tr("Leerseite einfügen – vor Auswahl"), lambda: self.insert_blank("before"))
        self.a_blank_after = A(
            tr("Leerseite einfügen – nach Auswahl"), lambda: self.insert_blank("after"), "Ctrl+Alt+I"
        )
        self.a_export = A(tr("Auswahl als ein PDF exportieren…"), self.export_selection, "Ctrl+E", "export")
        self.a_export_each = A(tr("Auswahl als einzelne PDFs exportieren…"), self.export_each, "Ctrl+Shift+E")
        self.a_delete = A(tr("Seiten löschen"), self.delete_pages, QKeySequence.StandardKey.Delete, "delete")
        self.a_split = A(tr("Seiten teilen (halbieren, Raster) …"), self.split_dialog, None, "split")
        self.a_split_spreads = A(
            tr("Doppelseiten teilen (falsch exportierte Broschüre)"), self.split_spreads, None, "split"
        )
        self.a_rot_l = A(tr("Seiten links drehen (dauerhaft)"), lambda: self.rotate_pages(-90), None, "rot_l")
        self.a_rot_r = A(tr("Seiten rechts drehen (dauerhaft)"), lambda: self.rotate_pages(90), None, "rot_r")
        self.a_up = A(tr("Seiten nach vorne verschieben"), lambda: self.move_pages(-1), "Alt+Up", "move_up")
        self.a_down = A(tr("Seiten nach hinten verschieben"), lambda: self.move_pages(1), "Alt+Down", "move_down")
        self.a_selall = A(tr("Alle Seiten auswählen"), lambda: self.thumbs.selectAll(), "Ctrl+Shift+A")

        mb = self.menuBar()
        m = mb.addMenu(tr("&Datei"))
        for a in (
            self.a_open,
            self.a_newwin,
            self.a_newtab,
            self.a_detach,
            None,
            self.a_save,
            self.a_saveas,
            None,
            self.a_props,
            None,
            self.a_print,
            None,
            self.a_settings,
            None,
            self.a_close,
        ):
            m.addSeparator() if a is None else m.addAction(a)
        m = mb.addMenu(tr("&Seiten"))
        for a in (
            self.a_ins_before,
            self.a_ins_after,
            self.a_ins_end,
            self.a_blank_before,
            self.a_blank_after,
            None,
            self.a_export,
            self.a_export_each,
            None,
            self.a_rot_l,
            self.a_rot_r,
            self.a_up,
            self.a_down,
            None,
            self.a_split,
            self.a_split_spreads,
            None,
            self.a_delete,
            None,
            self.a_selall,
            None,
            self.a_copy,
            self.a_seltext,
        ):
            m.addSeparator() if a is None else m.addAction(a)
        self.page_menu = m
        m = mb.addMenu(tr("D&okument"))
        m.addAction(self.a_merge)
        m.addAction(self.a_repair)
        m.addAction(self.a_shrink)
        m.addSeparator()
        self.a_preflight = A(
            tr("Dokumentprüfung (Preflight) …"),
            lambda: (self.pf_dock.show(), self.pf_dock.raise_(), self._pf_start(force=True)),
            "Ctrl+Shift+P",
            "check",
        )
        m.addAction(self.a_preflight)
        m = mb.addMenu(tr("Dokument-&Manipulation"))
        for a in (
            self.a_edit,
            None,
            self.a_manip_cmyk,
            self.a_manip_crop,
            None,
            self.a_manip,
            None,
            self.a_separate,
            self.a_cut,
            None,
            self.a_vdp,
            self.a_data,
        ):
            m.addSeparator() if a is None else m.addAction(a)
        m = mb.addMenu(tr("&Farbe"))
        self.a_proof = A(tr("Softproof (Druckfarben anzeigen)"), lambda: None, "Ctrl+Y", "proof")
        self.a_proof.setCheckable(True)
        self.a_proof.toggled.connect(self._toggle_proof)
        self.a_colorcheck = A(tr("Farbprüfung …"), self.color_check, "Ctrl+Shift+F", "check")
        self.a_colorcheck.setToolTip(tr("Dokument gegen eine Druckbedingung prüfen – mit Empfehlungen"))
        self.a_press = A(tr("Für Druckerei ausgeben …"), lambda: self.press_dialog(), None, "export")
        self.a_press.setToolTip(tr("Umwandeln, Output Intent einbetten, prüfen, speichern – optional als Paket"))
        self.a_pipette = A(tr("Farbpipette"), lambda: None, "Ctrl+Shift+C", "pipette")
        self.a_pipette.setCheckable(True)
        self.a_pipette.setToolTip(
            tr(
                "Farbe an einer Stelle messen: Werte im PDF, Farbauftrag im Druck je Kanal, "
                "Farbe übernehmen (Esc = beenden)"
            )
        )
        self.a_pipette.toggled.connect(self._pipette_mode)
        for a in (self.a_colorcheck, self.a_pipette, self.a_proof):
            m.addAction(a)
        m.addAction(A(tr("Softproof einrichten …"), self.softproof_dialog, "Ctrl+Shift+Y"))
        m.addSeparator()
        m.addAction(self.a_press)
        m.addAction(self.a_manip_cmyk)
        m.addSeparator()
        m.addAction(A(tr("Papiere und Messungen …"), lambda: self.materials_dialog(), None, "material"))
        m.addAction(A(tr("Standardprofile holen …"), lambda: self.standard_profiles(), None))
        m.addSeparator()
        m.addAction(A(tr("Farbmanagement kurz erklärt"), self._color_help, None, "info"))
        m = mb.addMenu(tr("Pla&n && Poster"))
        self.a_plan = A(tr("Plandruck (Rollen, Laufmeter) …"), lambda: self.plan_dialog("plan"), "Ctrl+Alt+P", "plan")
        self.a_plan.setToolTip(tr("Pläne auf Rollendrucker: Außenlinien, Rollenwahl, Laufmeter, Reihenfolge"))
        self.a_rolls = A(tr("Rollen der Drucker …"), self.rolls_dialog, None, "roll")
        self.a_rolls.setToolTip(tr("Geladene Rollen vom Gerät lesen oder von Hand eintragen"))
        self.a_poster = A(
            tr("Posterdruck (Qualität, nebeneinander, Banner) …"), lambda: self.plan_dialog("poster"), None, "print"
        )
        self.a_poster.setToolTip(tr("Poster und Banner auf Rollen: nebeneinander, Überbreite, Saum, Ösen, Print & Cut"))
        m.addAction(self.a_plan)
        m.addAction(self.a_poster)
        self.m_plan_hist = m.addMenu(svg_icon("history"), tr("Letzte Drucke"))
        self.m_plan_hist.aboutToShow.connect(self._fill_plan_history)
        m.addSeparator()
        m.addAction(self.a_rolls)
        m = mb.addMenu(tr("&Ansicht"))
        self.a_single = A(tr("Einzelseite (zur nächsten Seite springen)"), self._toggle_single, "Ctrl+4", "single")
        self.a_single.setCheckable(True)
        self.a_single.setChecked(self.view.single)
        m.addAction(self.a_single)
        m.addSeparator()
        self.a_rulers = A(tr("Lineale anzeigen"), lambda: None, "Ctrl+R", "ruler")
        self.a_rulers.setCheckable(True)
        self.a_rulers.toggled.connect(self._show_rulers)
        self.a_measure = A(tr("Messen"), lambda: None, "Ctrl+Shift+L", "measure")
        self.a_measure.setCheckable(True)
        self.a_measure.toggled.connect(self._measure_mode)
        self.a_boxes = A(tr("Endformat und Anschnitt anzeigen"), lambda: None, "Ctrl+Shift+B", "crop")
        self.a_boxes.setCheckable(True)
        from .. import l10n as _l10n

        self.a_boxes.setChecked(bool(_l10n.load_settings().get("show_trim", True)))
        self.view.show_boxes = self.a_boxes.isChecked()
        self.a_boxes.toggled.connect(self._show_boxes)
        m.addAction(self.a_rulers)
        m.addAction(self.a_measure)
        m.addAction(self.a_boxes)
        m.addSeparator()
        m.addAction(self.a_proof)
        m.addSeparator()
        m.addAction(dock.toggleViewAction())
        self.a_actual = A(tr("Tatsächliche Größe"), lambda: self.view.set_zoom("fixed", 1.0), "Ctrl+0", "actual")
        self.a_fitpage = A(tr("Ganze Seite"), lambda: self.view.set_zoom("page"), "Ctrl+1", "fit_page")
        self.a_fitwidth = A(tr("Seitenbreite"), lambda: self.view.set_zoom("width"), "Ctrl+2", "fit_width")
        for a in (self.a_fitpage, self.a_fitwidth, self.a_actual):
            m.addAction(a)
        m.addSeparator()
        self.a_vrot_l = A(tr("Ansicht links drehen"), lambda: self.rotate_view(-90), "Ctrl+Shift+-", "rot_l")
        self.a_vrot_r = A(tr("Ansicht rechts drehen"), lambda: self.rotate_view(90), "Ctrl+Shift++", "rot_r")
        m.addAction(self.a_vrot_l)
        m.addAction(self.a_vrot_r)
        m = mb.addMenu(tr("&Verwaltung"))
        m.addAction(A(tr("Standardeinstellungen (Admin)…"), self.admin_dialog, None, "settings"))
        m = mb.addMenu(tr("&Hilfe"))
        a = QAction(tr("Kommandozeile – Anleitung (PDF)"), self)
        a.triggered.connect(self._open_cli_howto)
        m.addAction(a)
        a = QAction(tr("Variable Daten – Anleitung (PDF)"), self)
        a.triggered.connect(self._open_vdp_howto)
        m.addAction(a)
        a = QAction(tr("Beispiele für Variable Daten holen …"), self)
        a.triggered.connect(self._get_examples)
        m.addAction(a)
        from .. import platform as _pl

        if _pl.IS_WIN:
            a = QAction(tr("Windows-Druck testen …"), self)
            a.triggered.connect(self._win_print_test)
            m.addAction(a)
        a = QAction(tr("Fehlerprotokolle öffnen"), self)
        a.triggered.connect(lambda: __import__("pdfdruck.gui.crashui", fromlist=["x"]).open_log_dir())
        m.addAction(a)
        a = QAction(tr("Lizenzen …"), self)
        a.setToolTip(tr("Lizenz von Passermark (GPL-3.0) und aller mitgelieferten Komponenten (Qt, Ghostscript, …)"))
        a.triggered.connect(self._open_licenses)
        m.addAction(a)

        dock_act = dock.toggleViewAction()
        dock_act.setIcon(svg_icon("sidebar"))
        dock_act.setText(tr("Seitenleiste"))
        tb = self.addToolBar(tr("Werkzeuge"))
        tb.setMovable(False)
        tb.setIconSize(QSize(20, 20))
        for a in (self.a_open, self.a_save, self.a_print):
            tb.addAction(a)
            btn = tb.widgetForAction(a)
            if isinstance(btn, QToolButton):  # the three main actions with text
                btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        tb.addSeparator()
        tb.addAction(dock_act)
        tb.addSeparator()
        tb.addAction(A(tr("Vorherige Seite"), lambda: self.view.goto(self.view.current - 1), None, "prev"))
        self.page_edit = PageEdit()
        self.page_edit.gotoRequested.connect(lambda p: self.view.goto(p))
        tb.addWidget(self.page_edit)
        tb.addAction(A(tr("Nächste Seite"), lambda: self.view.goto(self.view.current + 1), None, "next"))
        tb.addSeparator()
        # rulers/tape measure/trim size always available – not only in the workspace "Anzeigen"
        tb.addAction(self.a_rulers)
        tb.addAction(self.a_measure)
        tb.addAction(self.a_boxes)
        tb.addAction(self.a_proof)
        tb.addSeparator()
        tb.addAction(
            A(tr("Verkleinern"), lambda: self.view.step_zoom(1 / 1.2), QKeySequence.StandardKey.ZoomOut, "zoom_out")
        )
        self.zoom_combo = QComboBox()
        self.zoom_combo.setEditable(True)
        self.zoom_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.zoom_combo.setMinimumWidth(130)
        self.zoom_combo.addItem(tr("Seitenbreite"), "width")
        self.zoom_combo.addItem(tr("Ganze Seite"), "page")
        for z in ZOOM_STEPS:
            self.zoom_combo.addItem(f"{z * 100:.0f} %", z)
        self.zoom_combo.activated.connect(self._zoom_combo_activated)
        self.zoom_combo.lineEdit().returnPressed.connect(self._zoom_text_entered)
        tb.addWidget(self.zoom_combo)
        tb.addAction(
            A(
                tr("Vergrößern"),
                lambda: self.view.step_zoom(1.2),
                [QKeySequence.StandardKey.ZoomIn, "Ctrl+="],
                "zoom_in",
            )
        )
        tb.addSeparator()
        tb.addAction(self.a_fitpage)
        tb.addAction(self.a_fitwidth)
        tb.addAction(self.a_single)
        tb.addSeparator()
        tb.addAction(self.a_vrot_l)
        tb.addAction(self.a_vrot_r)
        A(tr("Erste Seite"), lambda: self.view.goto(0), "Home")
        A(tr("Letzte Seite"), lambda: self.view.goto(len(self.view.pages) - 1), "End")
        self._update_actions()

    def _toggle_single(self, checked=None):
        single = self.a_single.isChecked()
        self.ctl.view_single = single  # applies to new windows of this session
        self.view.set_single(single)
        self.view.setFocus()

    def _update_actions(self):
        has = self.doc is not None
        for a in (
            self.a_save,
            self.a_saveas,
            self.a_print,
            self.a_ins_before,
            self.a_ins_after,
            self.a_ins_end,
            self.a_blank_before,
            self.a_blank_after,
            self.a_export,
            self.a_export_each,
            self.a_delete,
            self.a_rot_l,
            self.a_rot_r,
            self.a_up,
            self.a_down,
            self.a_selall,
            self.a_manip,
            self.a_manip_cmyk,
            self.a_manip_crop,
            self.a_repair,
            self.a_separate,
            self.a_cut,
            self.a_edit,
            self.a_vdp,
            self.a_split,
            self.a_split_spreads,
        ):
            a.setEnabled(has)
        # save only when there is something to save (otherwise "nothing happens")
        self.a_save.setEnabled(has and (self.modified or not self.path))
        self.a_save.setToolTip(tr("Speichern") if self.a_save.isEnabled() else tr("Keine ungespeicherten Änderungen"))

    def _new_tab(self):
        if getattr(self, "_host", None) is None or not self.ctl.tabs_enabled():
            self.ctl.new_window()
            return
        self.ctl.new_window(tab_of=self)

    def _detach(self):
        host = getattr(self, "_host", None)
        if host is not None:
            host.detach(self)

    def _update_title(self):
        name = self.display_name or "Passermark"
        self.setWindowTitle(("● " if self.modified else "") + name + (tr(" – Passermark") if self.doc else ""))
        host = getattr(self, "_host", None)
        if host is not None:
            host.update_tab(self)

    # ================================================================ #
    # Open
    # ================================================================ #
    def open_dialog(self):
        """Ask for files and open them."""
        paths, _ = QFileDialog.getOpenFileNames(self, tr("Öffnen"), os.path.dirname(self.path or ""), OPEN_FILTER)
        if paths:
            self.open_paths_here(paths)

    def open_paths_here(self, paths):
        """First document into this (empty) window, the rest into new windows.
        Several images at once become one document.
        """
        if self.doc is not None:
            self.ctl.open_paths(paths, tab_of=self)
            return
        imgs = [p for p in paths if images.is_image(p)]
        rest = [p for p in paths if not images.is_image(p)]
        if imgs:
            self.open_images(imgs)
        elif rest:
            self.open_any(rest.pop(0))
        if rest:
            self.ctl.open_paths(rest, tab_of=self)

    def _set_doc(self, doc, path, display, modified, keep_page=None, src=None, changed_pages=None):
        """src: bytes of the document if already available (saves the render process the intermediate save).
        changed_pages: pages that were edited – old preview/thumbnails stay as placeholders
        until the new ones are there (these pages first).
        """
        if self.doc is not None and self.doc is not doc:
            self.doc.close()
        same_count = self.doc is not None and changed_pages is not None and self.thumbs.count() == len(doc)
        self.doc, self.path, self.display_name, self.modified = doc, path, display, modified
        if src is None and not modified and path and path.lower().endswith(".pdf") and os.path.isfile(path):
            src = path  # unchanged: the render process reads the file itself
        self.view.set_document(doc, keep_page, src=src, changed_pages=changed_pages if same_count else None)
        n = len(doc)
        self.page_edit.set_count(n)
        if same_count:
            for i in range(self.thumbs.count()):  # old thumbnails stay until the new ones are there
                self.thumbs.item(i).setData(THUMB_W, None)
            self._requeue_thumbs()
            first = [i for i in changed_pages if i in self._thumb_queue]
            self._thumb_queue = first + [i for i in self._thumb_queue if i not in first]
        else:
            self._rebuild_thumbs()
        self._update_actions()
        self._update_title()
        self._page_changed(self.view.current)
        if hasattr(self, "_pf_timer"):
            self._pf_timer.start()  # document check in the background

    def open(self, path: str):
        """Open the file ``path`` in this window."""
        doc = load_pdf(self, path)
        if doc is not None:
            self._sources = []
            self._set_doc(doc, path, os.path.basename(path), False)

    def open_any(self, path: str):
        """Open PDFs directly, convert Office files and open them as (unsaved) PDFs."""
        if not _convert.is_office(path):
            self.open(path)
            return
        try:
            doc = load_any(self, self.ctl, path)
        except Exception as e:
            QMessageBox.critical(self, tr("Umwandeln"), str(e))
            return
        self._sources = [tr("{0} (umgewandelt)").format(path)]
        self._set_doc(doc, None, os.path.splitext(os.path.basename(path))[0] + ".pdf", False)
        self._suggest_dir = os.path.dirname(path)

    def open_images(self, paths: list[str]):
        """Open several images as one document in this window."""
        try:
            doc = images.images_to_document(paths, self.ctl.image_dpi, ask_hdr(self, paths, self.ctl.image_dpi))
        except Exception as e:
            QMessageBox.critical(self, tr("Bild öffnen"), str(e))
            return
        base = os.path.splitext(os.path.basename(paths[0]))[0]
        name = f"{base}.pdf" if len(paths) == 1 else f"{base} (+{len(paths) - 1} Bilder).pdf"
        self._sources = list(paths)
        self._set_doc(doc, None, name, False)
        self._suggest_dir = os.path.dirname(paths[0])

    def properties_dialog(self):
        """Open the document properties."""
        if self.doc is None:
            return
        from .propsdialog import PropertiesDialog

        PropertiesDialog(self).exec()

    def merge_dialog(self):
        """Open the merge dialog and show the merged document."""
        dlg = MergeDialog(self, [self.path] if self.path and not self.modified else None)
        if not dlg.exec() or not dlg.paths():
            return
        self.ctl.merge_into_window(dlg.paths(), self if self.doc is None else None)

    def _load_any(self, path):
        return load_any(self, self.ctl, path)

    # ================================================================ #
    # save / export
    # ================================================================ #
    def _write(self, doc, path):
        """Save safely – even over the file that is just open."""
        tmp = path + ".pdfdruck-tmp"
        doc.save(tmp)
        return tmp

    def save(self):
        """Save to the current file (asks for a name if there is none). True if saved."""
        if self.doc is None:
            return False
        if not self.path:
            return self.save_as()
        return self._save_to(self.path)

    def save_as(self):
        """Ask for a file name and save. True if saved."""
        if self.doc is None:
            return False
        start = self.path or os.path.join(
            getattr(self, "_suggest_dir", os.path.expanduser("~")), self.display_name or "Dokument.pdf"
        )
        path, _ = QFileDialog.getSaveFileName(self, tr("Speichern unter"), start, tr("PDF-Dateien (*.pdf)"))
        if not path:
            return False
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        return self._save_to(path)

    def _save_to(self, path):
        cur = self.view.current
        try:
            tmp = self._write(self.doc, path)
            self.doc.close()  # release the file if it is the same one
            self.doc = None
            os.replace(tmp, path)
        except Exception as e:
            QMessageBox.critical(self, tr("Speichern"), tr("Speichern fehlgeschlagen:\n{0}").format(e))
            if self.doc is None and self.path and os.path.exists(self.path):
                self.open(self.path)
            return False
        doc = load_pdf(self, path)
        if doc is None:
            return False
        self._set_doc(doc, path, os.path.basename(path), False, cur)
        self.statusBar().showMessage(tr("Gespeichert: {0}").format(path), 6000)
        return True

    def selected_pages(self) -> list[int]:
        """The pages selected in the sidebar; the current page if none is selected."""
        rows = sorted(self.thumbs.row(i) for i in self.thumbs.selectedItems())
        return rows or ([self.view.current] if self.doc is not None else [])

    def export_selection(self):
        """Export the selected pages as one PDF."""
        pages = self.selected_pages()
        if not pages:
            return
        base = os.path.splitext(self.display_name or "Dokument")[0]
        rng = f"S{pages[0] + 1}" if len(pages) == 1 else f"S{pages[0] + 1}-{pages[-1] + 1}"
        start = os.path.join(
            os.path.dirname(self.path) if self.path else getattr(self, "_suggest_dir", ""), f"{base}_{rng}.pdf"
        )
        path, _ = QFileDialog.getSaveFileName(
            self, tr("{0} Seite(n) exportieren").format(len(pages)), start, tr("PDF-Dateien (*.pdf)")
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        if self.path and os.path.abspath(path) == os.path.abspath(self.path):
            QMessageBox.warning(self, tr("Exportieren"), tr("Bitte nicht über das geöffnete Dokument exportieren."))
            return
        try:
            out = pdfium.PdfDocument.new()
            out.import_pages(self.doc, pages)
            out.save(path)
            out.close()
        except Exception as e:
            QMessageBox.critical(self, tr("Exportieren"), tr("Export fehlgeschlagen:\n{0}").format(e))
            return
        QMessageBox.information(
            self, tr("Exportiert"), tr("{0} Seite(n) gespeichert als:\n{1}").format(len(pages), path)
        )

    def export_each(self):
        """Export every selected page as a PDF of its own."""
        pages = self.selected_pages()
        if not pages:
            return
        folder = QFileDialog.getExistingDirectory(
            self,
            tr("Zielordner für Einzelseiten"),
            os.path.dirname(self.path) if self.path else getattr(self, "_suggest_dir", ""),
        )
        if not folder:
            return
        base = os.path.splitext(self.display_name or "Dokument")[0]
        digits = max(3, len(str(len(self.doc))))
        names = [f"{base}_S{p + 1:0{digits}d}.pdf" for p in pages]
        exist = [n for n in names if os.path.exists(os.path.join(folder, n))]
        if (
            exist
            and QMessageBox.question(
                self,
                tr("Überschreiben?"),
                tr("{0} Datei(en) existieren bereits (z. B. {1}). Überschreiben?").format(len(exist), exist[0]),
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        done, errors = 0, []
        for p, name in zip(pages, names):
            try:
                out = pdfium.PdfDocument.new()
                out.import_pages(self.doc, [p])
                out.save(os.path.join(folder, name))
                out.close()
                done += 1
            except Exception as e:
                errors.append(f"{name}: {e}")
        if errors:
            QMessageBox.critical(
                self,
                tr("Exportieren"),
                tr("{0} gespeichert, {1} Fehler:\n").format(done, len(errors)) + "\n".join(errors[:8]),
            )
        else:
            QMessageBox.information(
                self,
                tr("Exportiert"),
                tr("{0} Einzelseite(n) gespeichert in:\n{1}\n\n{2}").format(done, folder, names[0])
                + (f" … {names[-1]}" if len(names) > 1 else ""),
            )

    # ================================================================ #
    # page operations
    # ================================================================ #
    def _changed_doc(self, keep_page=None, select=None):
        self.modified = True
        self._set_doc(
            self.doc, self.path, self.display_name, True, self.view.current if keep_page is None else keep_page
        )
        if select:
            self.thumbs.clearSelection()
            for i in select:
                if 0 <= i < self.thumbs.count():
                    self.thumbs.item(i).setSelected(True)

    def insert_dialog(self, where: str):
        """Ask for files and insert their pages (``where``: before, after or end)."""
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr("Seiten einfügen aus …"), os.path.dirname(self.path or ""), OPEN_FILTER
        )
        if not paths:
            return
        sel = self.selected_pages()
        pos = {"before": sel[0] if sel else 0, "after": (sel[-1] + 1) if sel else len(self.doc), "end": len(self.doc)}[
            where
        ]
        start = pos
        try:
            for p in paths:
                part = self._load_any(p)
                if part is None:
                    return
                n = len(part)
                self.doc.import_pages(part, index=pos)
                part.close()
                pos += n
        except Exception as e:
            QMessageBox.critical(self, tr("Einfügen"), str(e))
        self._changed_doc(start, list(range(start, pos)))
        self.statusBar().showMessage(tr("{0} Seite(n) eingefügt.").format(pos - start), 6000)

    def insert_blank(self, where: str, count: int = 1):
        """Blank page(s) before/after the selection – in the size of the neighbouring page (boxes and rotation
        included).
        """
        if self.doc is None:
            return
        from .. import pageops

        sel = self.selected_pages()
        n = len(self.doc)
        if where == "before":
            pos = sel[0] if sel else 0
            ref = pos if pos < n else n - 1
        else:
            pos = (sel[-1] + 1) if sel else n
            ref = pos - 1 if pos > 0 else 0
        try:
            k = pageops.insert_blank(self.doc, pos, ref if n else None, count)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, tr("Leerseite einfügen"), str(e))
            return
        self._changed_doc(pos, list(range(pos, pos + k)))
        self.statusBar().showMessage(tr("{0} Leerseite(n) eingefügt.").format(k), 6000)

    def delete_pages(self):
        """Delete the selected pages."""
        pages = self.selected_pages()
        if not pages:
            return
        if len(pages) >= len(self.doc):
            QMessageBox.warning(self, tr("Löschen"), tr("Es muss mindestens eine Seite übrig bleiben."))
            return
        if (
            QMessageBox.question(
                self,
                tr("Seiten löschen"),
                tr("{0} Seite(n) aus dem Dokument entfernen?\n(Die Datei ändert sich erst beim Speichern.)").format(
                    len(pages)
                ),
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        for i in reversed(pages):
            self.doc.del_page(i)
        self._changed_doc(min(pages[0], len(self.doc) - 1))

    def rotate_pages(self, delta: int):
        """Rotate the selected pages permanently by ``delta`` degrees."""
        pages = self.selected_pages()
        for i in pages:
            pg = self.doc[i]
            pg.set_rotation((pg.get_rotation() + delta) % 360)
            pg.close()
        self._changed_doc(select=pages)

    def move_pages(self, d: int):
        """Move the selected pages one position forwards or backwards."""
        pages = self.selected_pages()
        if not pages:
            return
        n = len(self.doc)
        dest = pages[0] + d
        if dest < 0 or dest + len(pages) > n:
            return
        arr = (ctypes.c_int * len(pages))(*pages)
        if not pdfium_r.FPDF_MovePages(self.doc.raw, arr, len(pages), dest):
            QMessageBox.warning(self, tr("Verschieben"), tr("Verschieben fehlgeschlagen."))
            return
        self._changed_doc(dest, list(range(dest, dest + len(pages))))

    def move_pages_to(self, pages: list, ins: int):
        """Sidebar: drag the selected pages to the insertion point (ins = before this page, len = at the end)."""
        if self.doc is None or not pages:
            return
        pages = sorted(set(p for p in pages if 0 <= p < len(self.doc)))
        dest = ins - sum(1 for p in pages if p < ins)  # index of the first page after moving
        dest = max(0, min(dest, len(self.doc) - len(pages)))
        if pages == list(range(dest, dest + len(pages))):
            return  # already there
        arr = (ctypes.c_int * len(pages))(*pages)
        if not pdfium_r.FPDF_MovePages(self.doc.raw, arr, len(pages), dest):
            QMessageBox.warning(self, tr("Verschieben"), tr("Verschieben fehlgeschlagen."))
            return
        self._changed_doc(dest, list(range(dest, dest + len(pages))))

    def _thumb_menu(self, pos):
        if self.doc is None:
            return
        it = self.thumbs.itemAt(pos)
        if it is not None and not it.isSelected():
            self.thumbs.clearSelection()
            it.setSelected(True)
        n = len(self.selected_pages())
        m = QMenu(self)
        m.addSection(tr("{0} Seite(n) ausgewählt").format(n))
        for a in (
            self.a_ins_before,
            self.a_ins_after,
            self.a_blank_before,
            self.a_blank_after,
            None,
            self.a_export,
            self.a_export_each,
            None,
            self.a_rot_l,
            self.a_rot_r,
            self.a_up,
            self.a_down,
            None,
        ):
            m.addSeparator() if a is None else m.addAction(a)
        sm = m.addMenu(svg_icon("split"), tr("Teilen"))
        sm.addAction(tr("Senkrecht halbieren (links | rechts)"), lambda: self.split_selected("halves_v"))
        sm.addAction(tr("Waagrecht halbieren (oben / unten)"), lambda: self.split_selected("halves_h"))
        sm.addSeparator()
        sm.addAction(tr("Raster / weitere Optionen …"), lambda: self.split_dialog(selection=True))
        m.addSeparator()
        m.addAction(self.a_delete)
        m.exec(self.thumbs.mapToGlobal(pos))

    # ================================================================ #
    # thumbnails / display
    # ================================================================ #
    def rotate_view(self, delta: int):
        """Rotate the view – the thumbnails in the sidebar rotate along (the document stays unchanged)."""
        self.view.rotate(delta)
        if self.doc is not None:
            self._rebuild_thumbs()

    def _view_rot(self) -> int:
        r = getattr(self.view, "rotation", 0)
        return r % 360 if isinstance(r, int) else 0

    # ---------------- sidebar: width, arrangement, preview size ---------------- #
    @staticmethod
    def _dock_scroll(w):
        """Put a panel into a scroll area: the tabs on the left share one width – without this
        the widest panel (check/edit) forces its minimum width on "Seiten" too.
        """
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.Shape.NoFrame)
        sc.setWidget(w)
        # panels wrap (common.responsive) – scroll horizontally only when there is no other way
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        return sc

    def _dock_vis(self, d, vis):
        """Every tab on the left remembers its own width (pages narrow, check wider …)."""
        shown = self.__dict__.setdefault("_dock_shown", set())
        if not vis:
            if d in shown:  # remember only real, visible widths
                shown.discard(d)
                self._dock_widths[d] = d.width()
            return
        shown.add(d)
        want = self._dock_widths.get(d)
        if want is None and d is not self._pages_dock:
            inner = d.widget().widget() if isinstance(d.widget(), QScrollArea) else d.widget()
            want = max(d.width(), inner.minimumSizeHint().width() + 4)
        if want and want != d.width():
            QTimer.singleShot(0, lambda: self.resizeDocks([d], [want], Qt.Orientation.Horizontal))

    def _thumb_panel(self):
        from .. import l10n

        st = l10n.load_settings()
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        bar = QHBoxLayout()
        bar.setContentsMargins(6, 3, 6, 3)
        bar.setSpacing(2)
        self.btn_thumb_col = QToolButton()
        self.btn_thumb_col.setIcon(svg_icon("single"))
        self.btn_thumb_col.setToolTip(tr("Eine Spalte – Vorschau füllt die Breite"))
        self.btn_thumb_grid = QToolButton()
        self.btn_thumb_grid.setIcon(svg_icon("grid"))
        self.btn_thumb_grid.setToolTip(tr("Raster – mehrere Seiten nebeneinander"))
        self.btn_thumb_minus = QToolButton()
        self.btn_thumb_minus.setIcon(svg_icon("zoom_out"))
        self.btn_thumb_minus.setToolTip(tr("Vorschau verkleinern (Strg + Mausrad)"))
        self.btn_thumb_plus = QToolButton()
        self.btn_thumb_plus.setIcon(svg_icon("zoom_in"))
        self.btn_thumb_plus.setToolTip(tr("Vorschau vergrößern (Strg + Mausrad)"))
        for b in (self.btn_thumb_col, self.btn_thumb_grid):
            b.setCheckable(True)
            b.setAutoRaise(True)
            bar.addWidget(b)
        bar.addStretch(1)
        for b in (self.btn_thumb_minus, self.btn_thumb_plus):
            b.setAutoRaise(True)
            bar.addWidget(b)
        self.btn_thumb_col.clicked.connect(lambda: self._set_thumb_grid(False))
        self.btn_thumb_grid.clicked.connect(lambda: self._set_thumb_grid(True))
        self.btn_thumb_minus.clicked.connect(lambda: self._thumb_zoom(-1))
        self.btn_thumb_plus.clicked.connect(lambda: self._thumb_zoom(1))
        v.addLayout(bar)
        v.addWidget(self.thumbs, 1)
        try:
            self.thumbs.tile = int(st.get("thumb_tile", 140))
        except (TypeError, ValueError):
            pass
        self._set_thumb_grid(bool(st.get("thumb_grid", False)), remember=False)
        return box

    def _set_thumb_grid(self, on: bool, remember: bool = True):
        self.btn_thumb_col.setChecked(not on)
        self.btn_thumb_grid.setChecked(on)
        if on and self.thumbs.grid_mode != on:
            self.thumbs.tile = min(self.thumbs.tile, max(ThumbList.TILE_MIN, self.thumbs.viewport().width() // 2))
        self.thumbs.set_grid(on)
        self._requeue_thumbs()
        if remember:
            self._save_thumb_settings()

    def _thumb_zoom(self, step: int):
        """Grid: change the tile size. One column: make the sidebar itself wider/narrower."""
        f = 1.15 if step > 0 else 1 / 1.15
        if self.thumbs.grid_mode:
            t = int(round(self.thumbs.tile * f))
            if t == self.thumbs.tile:
                t += 1 if step > 0 else -1
            self.thumbs.tile = max(ThumbList.TILE_MIN, min(ThumbList.TILE_MAX, t))
            self.thumbs.doItemsLayout()
            self._thumb_resize.start()
            self._save_thumb_settings()
        else:
            d = self._pages_dock
            if not d.isFloating():
                w = max(110, min(int(d.width() * f), max(200, self.width() - 300)))
                self.resizeDocks([d], [w], Qt.Orientation.Horizontal)
            else:
                d.resize(max(110, int(d.width() * f)), d.height())

    def _save_thumb_settings(self):
        from .. import l10n

        st = l10n.load_settings()
        if st.get("thumb_grid") == self.thumbs.grid_mode and st.get("thumb_tile") == self.thumbs.tile:
            return
        st["thumb_grid"] = self.thumbs.grid_mode
        st["thumb_tile"] = self.thumbs.tile
        try:
            l10n.save_settings(st)
        except OSError:
            pass

    def _rebuild_thumbs(self):
        self.thumbs.clear()
        rot = self._view_rot()
        for i in range(len(self.doc)):
            it = QListWidgetItem(str(i + 1))
            w, h = self.doc.get_page_size(i)
            if rot % 180:
                w, h = h, w
            it.setData(THUMB_ASPECT, h / w if w else 1.414)
            it.setToolTip(tr("Seite {0}: {1}").format(i + 1, page_size_text(w, h)))
            self.thumbs.addItem(it)
        self._requeue_thumbs()

    def _requeue_thumbs(self):
        if self.doc is None:
            return
        self.thumbs.doItemsLayout()
        # visible ones first, then the rest
        first = self.thumbs.indexAt(self.thumbs.viewport().rect().topLeft()).row()
        first = max(0, first)
        n = self.thumbs.count()
        self._thumb_queue = list(range(first, n)) + list(range(0, first))
        if self._thumb_src.usable():
            self._thumb_timer.stop()
            self._thumb_src.kick()
        else:
            self._thumb_timer.start()

    def _thumb_target(self, i):
        """(image width in the list, scale in device pixels) for thumbnail i."""
        dlg = self.thumbs.itemDelegate()
        it = self.thumbs.item(i)
        iw = dlg.image_rect(QRect(0, 0, self.thumbs.tile_width(), 10000), it.data(THUMB_ASPECT)).width()
        w, h = self.doc.get_page_size(i)
        rot = self._view_rot()
        return iw, iw / (h if rot % 180 else w) * self.devicePixelRatioF()

    def _thumb_from_master(self, i):
        """Page image of the preview is ready -> scale the thumbnail from it (no second rendering)."""
        if self.doc is None or not (0 <= i < self.thumbs.count()) or not (0 <= i < len(self.view.pages)):
            return
        w = self.view.pages[i]
        if w.master is None or w.mstale or w.mkey is None or w.mkey[1] != self._view_rot():
            return
        it = self.thumbs.item(i)
        iw, _sc = self._thumb_target(i)
        dpr = self.devicePixelRatioF()
        tw = max(1, round(iw * dpr))
        img = w.master.scaledToWidth(tw, Qt.TransformationMode.SmoothTransformation)
        pm = QPixmap.fromImage(img)
        pm.setDevicePixelRatio(dpr)
        it.setData(THUMB_PIX, pm)
        it.setData(THUMB_W, iw)

    def _render_thumbs(self):
        if not self._thumb_queue or self.doc is None:
            self._thumb_timer.stop()
            return
        dlg = self.thumbs.itemDelegate()
        vw = self.thumbs.tile_width()
        dpr = self.devicePixelRatioF()
        for _ in range(3):
            if not self._thumb_queue:
                break
            i = self._thumb_queue.pop(0)
            if i >= len(self.doc) or i >= self.thumbs.count():
                continue
            it = self.thumbs.item(i)
            iw = dlg.image_rect(QRect(0, 0, vw, 10000), it.data(THUMB_ASPECT)).width()
            if it.data(THUMB_W) == iw and it.data(THUMB_PIX) is not None:
                continue
            w, h = self.doc.get_page_size(i)
            rot = self._view_rot()
            page = self.doc[i]
            pm = render_pixmap(page, iw / (h if rot % 180 else w), rot, dpr)
            page.close()
            it.setData(THUMB_PIX, pm)
            it.setData(THUMB_W, iw)

    def _page_changed(self, i):
        if self.doc is None:
            self.lbl_size.setText("")
            return
        self.page_edit.set_current(i)
        if len(self.thumbs.selectedItems()) <= 1 and 0 <= i < self.thumbs.count():
            self.thumbs.blockSignals(True)
            self.thumbs.setCurrentRow(i)
            self.thumbs.blockSignals(False)
            self.thumbs.scrollToItem(self.thumbs.item(i))
        w, h = self.doc.get_page_size(i)
        txt = tr("Seite {0}/{1}   ·   {2}").format(i + 1, len(self.doc), page_size_text(w, h))
        try:
            ti = self.view.trim_info(i)  # without loading the page in the program
        except Exception:
            ti = None
        if ti:
            txt += "   ·   " + tr("Endformat {0:.1f} × {1:.1f} mm, Anschnitt {2:.1f} mm").format(*ti)
        self.lbl_size.setText(txt)

    def _zoom_changed(self, z):
        if self.view.mode == "fixed":
            self.zoom_combo.setEditText(f"{z * 100:.0f} %")
        else:
            self.zoom_combo.setCurrentIndex(0 if self.view.mode == "width" else 1)

    def _zoom_combo_activated(self, idx):
        d = self.zoom_combo.itemData(idx)
        if d in ("width", "page"):
            self.view.set_zoom(d)
        elif d is not None:
            self.view.set_zoom("fixed", float(d))

    def _zoom_text_entered(self):
        t = self.zoom_combo.currentText().replace("%", "").replace(",", ".").strip()
        try:
            self.view.set_zoom("fixed", float(t) / 100.0)
        except ValueError:
            pass

    def _step_zoom(self, d):
        self.view.step_zoom(1.2 if d > 0 else 1 / 1.2)

    # ================================================================ #
    def manip_dialog(self, mode: str = "all"):
        """Open the dialog for CMYK conversion and/or cropping."""
        if self.doc is None:
            return
        from .manipdialog import ManipDialog

        dlg = ManipDialog(self, self.doc, self.session, self.view.current, mode)
        if not dlg.exec() or not dlg.job:
            return
        suffix = {"cmyk": tr("_CMYK"), "crop": tr("_beschnitten")}.get(mode, tr("_bearbeitet"))
        title = {"cmyk": tr("CMYK"), "crop": tr("Beschneiden")}.get(mode, tr("Bearbeiten"))
        self.start_job(*dlg.job, suffix=suffix, title=title)

    def separate_dialog(self):
        """Open the dialog "Objekte trennen"."""
        if self.doc is None:
            return
        from .objectsdialog import SeparateDialog

        dlg = SeparateDialog(self, self.doc, self.view.current)
        if dlg.exec() and getattr(dlg, "job", None):
            self.start_job(
                *dlg.job,
                suffix=tr("_einzeln"),
                title=tr("Objekte trennen"),
                notes=lambda info: [tr("{0} Objekt(e) als Einzelseiten.").format(info.get("objects", 0))],
            )

    def split_selected(self, mode: str):
        """Right-click → Split: immediately halve the selected pages (no dialog, no comparison page)."""
        if self.doc is None:
            return
        from .. import core, split

        pages = self.selected_pages()
        if not pages:
            return
        self.start_job(
            "split",
            core.settings_to_dict(split.SplitSettings(mode=mode)),
            pages,
            suffix=tr("_geteilt"),
            title=tr("Seiten teilen"),
        )

    def split_dialog(self, selection: bool = False):
        """Open the dialog "Seiten teilen" (``selection``: only for the selected pages)."""
        if self.doc is None:
            return
        from .splitdialog import SplitDialog

        dlg = SplitDialog(
            self, self.doc, self.view.current, self.selected_pages(), which="selected" if selection else "all"
        )
        if dlg.exec() and getattr(dlg, "job", None):
            self.start_job(*dlg.job, suffix=tr("_geteilt"), title=tr("Seiten teilen"))

    def split_spreads(self):
        """One click: halve all double pages vertically (e.g. a booklet exported as press sheets)."""
        if self.doc is None:
            return
        from .. import core, split

        sizes = [self.doc.get_page_size(i) for i in range(len(self.doc))]
        if not split.spreads(sizes, 2, 1):
            QMessageBox.information(
                self,
                tr("Doppelseiten teilen"),
                tr(
                    "Keine Doppelseiten gefunden – keine Seite ist doppelt so breit wie die übrigen. Für andere Fälle: "
                    "Seiten → Seiten teilen …"
                ),
            )
            return
        self.start_job(
            "split",
            core.settings_to_dict(split.SplitSettings(only_spreads=True)),
            None,
            suffix=tr("_geteilt"),
            title=tr("Doppelseiten teilen"),
        )

    def cut_dialog(self):
        """Open the dialog "CutContour erzeugen"."""
        if self.doc is None:
            return
        from .objectsdialog import CutContourDialog

        try:
            dlg = CutContourDialog(self, self.doc, self.view.current)
        except Exception as e:
            from .objectsdialog import show_error

            show_error(self, tr("Fehler"), e)
            return
        if dlg.exec() and getattr(dlg, "job", None):
            self.start_job(
                *dlg.job,
                suffix=tr("_CutContour"),
                title=tr("CutContour"),
                notes=lambda info: [tr("{0} Schnittkontur(en) erzeugt.").format(info.get("cuts", 0))],
            )

    def vdp_dialog(self, data=None):
        """data = (csv_path, data kind) from "Enter data": adopt the table right away as the data source with a field."""
        if self.doc is None:
            return
        from .vdpdialog import VdpDialog

        try:
            dlg = VdpDialog(self, self.doc, self.view.current)
            if data:
                dlg.use_data(*data)
        except Exception as e:
            from .objectsdialog import show_error

            show_error(self, tr("Fehler"), e)
            return
        if dlg.exec() and getattr(dlg, "job", None):
            self.start_job(
                *dlg.job,
                suffix=tr("_Daten"),
                title=tr("Variable Daten"),
                notes=lambda info: [
                    tr("{0} Datensätze, {1} Seiten erzeugt.").format(info.get("records", 0), info.get("pages", 0))
                ],
            )

    def data_dialog(self):
        """Create a data table; "Use for variable data" opens Variable Data with this table."""
        from .datadialog import DataDialog

        dlg = DataDialog(self)
        if not (dlg.exec() and dlg.use and dlg.path):
            return
        if self.doc is None:
            QMessageBox.information(
                self,
                tr("Daten erfassen"),
                tr(
                    "Die Tabelle ist gespeichert:\n{0}\n\nJetzt die Vorlage (PDF) öffnen und unter Variable Daten → "
                    "„CSV öffnen …“ diese Datei wählen."
                ).format(dlg.path),
            )
            return
        self.vdp_dialog((dlg.path, dlg.kind))

    # ---------------- Background jobs (separate process) ---------------- #
    def start_job(self, kind, settings, pages=None, suffix="", title="", notes=None, src_data=None):
        """Document into the cache, start the command line as its own process, show progress at the bottom."""
        from .. import jobproc, l10n
        from .jobs import JobReader, JobWidget

        base = os.path.splitext(self.display_name or "Dokument")[0]
        src = self.ctl.cache_file(base + "_eingabe.pdf")
        dst = self.ctl.cache_file(base + suffix + ".pdf")
        try:
            if src_data is not None:  # e.g. the file as on disk
                with open(src, "wb") as f:
                    f.write(src_data)
            else:
                self.doc.save(src)  # current state (including unsaved changes)
            open(dst, "wb").close()  # reserve names (several jobs at once)
            job = jobproc.JobProcess(kind, src, dst, settings, pages, lang=l10n.current())
            job.start()
        except Exception as e:
            from .objectsdialog import show_error

            show_error(self, tr("Fehler"), e)
            return
        entry = {"job": job, "src": src, "dst": dst}
        widget = JobWidget(title or kind, lambda: self._cancel_job(entry))
        reader = JobReader(job)
        entry.update(widget=widget, reader=reader)
        reader.progress.connect(widget.set_progress)
        reader.finished_job.connect(lambda res: self._job_finished(entry, res, suffix, notes))
        self.statusBar().addWidget(widget)
        self._jobs.append(entry)
        reader.start()

    def _cancel_job(self, entry):
        entry["widget"].set_cancelling()
        entry["job"].cancel()

    def _job_finished(self, entry, res, suffix, notes):
        if entry in self._jobs:
            self._jobs.remove(entry)
        self.statusBar().removeWidget(entry["widget"])
        entry["widget"].deleteLater()
        entry["reader"].wait(2000)
        try:
            os.remove(entry["src"])
        except OSError:
            pass
        ev = res.get("event")
        if ev == "done":
            info = res.get("info") or {}
            extra = list(notes(info)) if notes else []
            self._open_result_path(entry["dst"], extra + list(res.get("notes") or []))
            return
        try:
            os.remove(entry["dst"])
        except OSError:
            pass
        if ev == "cancelled":
            self.statusBar().showMessage(tr("Abgebrochen."), 6000)
            return
        from .. import crashlog

        crashlog.record(
            f"Auftrag {entry['job'].kind} fehlgeschlagen (Code {res.get('returncode')}): {res.get('message')}",
            res.get("details") or "",
        )
        box = QMessageBox(
            QMessageBox.Icon.Critical, tr("Fehler"), res.get("message") or tr("Unbekannter Fehler"), parent=self
        )
        if res.get("details"):
            box.setDetailedText(res["details"])
        box.exec()

    def _stop_jobs(self):
        """Window is closing: cancel running jobs."""
        cp = self.__dict__.get("color_panel")
        if cp is not None:  # colour check in the background: cancel and wait
            if cp._worker is not None:
                cp._worker.cancel()
            for th in list(cp._threads):
                th.wait(10000)
        for entry in list(self._jobs):
            entry["job"].cancel()
        for entry in list(self._jobs):
            entry["reader"].wait(5000)

    def _open_result(self, new_doc, suffix: str, notes=()):
        """Write the result to the cache and open it from there in a new window."""
        base = os.path.splitext(self.display_name or "Dokument")[0]
        path = self.ctl.cache_file(base + suffix + ".pdf")
        try:
            new_doc.save(path)
        except Exception as e:
            from .objectsdialog import show_error

            show_error(self, tr("Fehler"), e)
            return
        finally:
            new_doc.close()
        self._open_result_path(path, notes)

    def _open_result_path(self, path: str, notes=()):
        """Open the finished file from the cache in a new window (temporary, "Save as")."""
        doc = load_pdf(self, path)
        if doc is None:
            return
        w = self.ctl.new_window(tab_of=self)
        # temporary: no fixed location -> "Save" asks, closing reminds to save
        w._sources = [tr("Ergebnis aus {0}").format(self.path or self.display_name or "–")]
        w._set_doc(doc, None, os.path.basename(path), True)
        w._temp_path = path
        w._suggest_dir = os.path.dirname(self.path) if self.path else getattr(self, "_suggest_dir", "")
        w.raise_()
        msg = tr("Temporär im Zwischenspeicher – zum Behalten „Speichern unter …“.")
        if notes:
            msg += "  " + "  ".join(notes)
        w.statusBar().showMessage(msg, 20000)

    @staticmethod
    def _lang_pdf(path: str) -> str:
        """Language version of a manual (e.g. …-anleitung.en.pdf), otherwise the German one."""
        from .. import l10n

        lang = l10n.current()
        for code in (lang, "en"):  # interface language, then English instead of German
            if code and code != "de":
                root, ext = os.path.splitext(path)
                p = f"{root}.{code}{ext}"
                if os.path.isfile(p):
                    return p
        return path

    @staticmethod
    def cli_howto_path() -> str:
        """Manual for the command line in the program package (Linux installation, AppImage, Windows setup)."""
        from .. import __file__ as pkg

        return MainWindow._lang_pdf(os.path.join(os.path.dirname(pkg), "docs", "passermark-cli-anleitung.pdf"))

    def _open_cli_howto(self):
        p = self.cli_howto_path()
        if not os.path.isfile(p):
            QMessageBox.warning(self, tr("Hilfe"), tr("Anleitung nicht gefunden: {0}").format(p))
            return
        self.ctl.open_paths([p], tab_of=self)

    def _open_vdp_howto(self):
        from .. import examples

        p = MainWindow._lang_pdf(examples.VDP_HOWTO)
        if not os.path.isfile(p):
            QMessageBox.warning(self, tr("Hilfe"), tr("Anleitung nicht gefunden: {0}").format(p))
            return
        self.ctl.open_paths([p], tab_of=self)

    def _get_examples(self):
        """Copy the examples to the user folder, register the presets, open the template in a tab."""
        from .. import examples

        try:
            d = examples.install()
        except OSError as e:
            QMessageBox.critical(self, tr("Beispiele"), tr("Fehler: {0}").format(e))
            return
        self.ctl.open_paths([os.path.join(d, "vorlage-a6.pdf")], tab_of=self)
        QMessageBox.information(
            self,
            tr("Beispiele"),
            tr(
                "Die Beispiele liegen in:\n{0}\n\nDie Vorlage ist geöffnet. Unter Variable Daten (Strg+Umschalt+D) "
                "in der Preset-Leiste „Beispiel 1“ bis „Beispiel 4“ wählen – die CSV ist schon eingetragen.\n\n"
                "Im Ordner „ergebnis“ liegen die fertigen PDFs zum Vergleich, die Anleitung liegt daneben."
            ).format(d),
        )

    def _win_print_test(self):
        """Print one test page per method – shows what the driver can really do (blank sheets?)."""
        from PySide6.QtWidgets import QInputDialog
        from .. import printers, printers_win

        try:
            names = [p.name for p in printers.list_printers()]
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, tr("Windows-Druck testen"), str(e))
            return
        if not names:
            QMessageBox.information(self, tr("Windows-Druck testen"), tr("Kein Drucker gefunden."))
            return
        name, ok = QInputDialog.getItem(
            self,
            tr("Windows-Druck testen"),
            tr("Je Verfahren wird eine A4-Testseite gedruckt (4 Blätter).\nDrucker:"),
            names,
            0,
            False,
        )
        if not ok:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            res = printers_win.test_print(name)
        finally:
            QApplication.restoreOverrideCursor()
        lines = "\n".join(f"• {label}: {r}" for label, r in res)
        QMessageBox.information(
            self,
            tr("Windows-Druck testen"),
            tr("Gesendet an {0}:").format(name)
            + "\n"
            + lines
            + "\n\n"
            + tr(
                "Auf jedem Blatt steht das Verfahren. Wählen Sie unter Datei → Einstellungen → Drucken "
                "unter Windows das Verfahren, dessen Blatt richtig ankommt."
            ),
        )

    def copy_text(self):
        """Copy the selected text to the clipboard."""
        t = self.view.selected_text()
        if t:
            QApplication.clipboard().setText(t)
            self.statusBar().showMessage(tr("{0} Zeichen kopiert.").format(len(t)), 3000)

    def settings_dialog(self):
        """Open the program settings."""
        from .settingsdialog import SettingsDialog

        SettingsDialog(self).exec()

    def shrink_dialog(self):
        """Break down and reduce the file size – also for files that do not count as too large."""
        if self.doc is None:
            return
        from .shrinkdialog import ShrinkDialog

        data = self._file_bytes()
        dlg = ShrinkDialog(self, None, data)
        if dlg.exec():
            self.start_job("shrink", dlg.options(), suffix=tr("_klein"), title=tr("Datei verkleinern"), src_data=data)

    def repair_dialog(self):
        """Open the repair dialog for the current document."""
        import tempfile
        from .. import repair
        from .repairdialog import RepairDialog

        names, out_dir = {}, None
        if self.doc is None:
            files, _ = QFileDialog.getOpenFileNames(
                self, tr("PDFs reparieren / optimieren"), "", tr("PDF-Dateien (*.pdf *.PDF)")
            )
            if not files:
                return
        elif self.path and not self.modified and not repair.needs_password(self.path):
            files = [self.path]
        else:
            # current state (edited, from images, or unlocked) -> unencrypted working copy
            tmp = os.path.join(tempfile.mkdtemp(prefix="passermark-"), "dokument.pdf")
            self.doc.save(tmp, flags=pdfium_r.FPDF_REMOVE_SECURITY)
            files = [tmp]
            names = {tmp: self.display_name or "Dokument.pdf"}
            out_dir = (
                os.path.dirname(self.path) if self.path else getattr(self, "_suggest_dir", os.path.expanduser("~"))
            )
        RepairDialog(self, files, names, out_dir, open_cb=lambda p: self.ctl.open_paths([p], tab_of=self)).exec()

    def print_dialog(self):
        """Open the print dialog for the current document."""
        if self.doc is None:
            return
        from .printdialog import PrintDialog

        PrintDialog(
            self,
            self.doc,
            self.display_name,
            self.view.current,
            self.session,
            src_path=getattr(self.view, "_src_path", None),
            pinfo=getattr(self.view, "_pinfo", None),
        ).exec()

    def plan_dialog(self, kind: str = "plan", entry: dict | None = None):
        """Plan & Poster → plan/poster printing: own window, independent of this document (the open
        document is not taken over). entry: open an earlier print from the history.
        """
        from .plandialog import open_window

        open_window(self.session, self.ctl, entry.get("kind", kind) if entry else kind, entry)

    def _fill_plan_history(self):
        """Plan & Poster → recent prints: plan and poster prints, newest first; clean-up at the bottom."""
        from .. import planhistory

        m = self.m_plan_hist
        m.clear()
        ents = planhistory.entries()
        if not ents:
            a = m.addAction(tr("Noch keine Drucke im Verlauf"))
            a.setEnabled(False)
            return
        for e in ents[:20]:
            pre = tr("Plan") if e.get("kind") != "poster" else tr("Poster")
            m.addAction(
                svg_icon("plan" if e.get("kind") != "poster" else "print"),
                f"{pre}: {planhistory.label(e)}",
                lambda e=e: self.plan_dialog(e.get("kind", "plan"), e),
            )
        m.addSeparator()
        m.addAction(tr("Verlauf aufräumen …"), self._clear_plan_history)

    def _clear_plan_history(self):
        from .. import planhistory
        from ..planprint import num as planhistory_num

        n = len(planhistory.entries())
        mb = round(planhistory.size_bytes() / 1e6, 1)
        if (
            QMessageBox.question(
                self,
                tr("Verlauf aufräumen"),
                tr("Alle {0} Plan- und Posterdrucke im Verlauf verwerfen ({1} MB)?").format(n, planhistory_num(mb)),
            )
            == QMessageBox.StandardButton.Yes
        ):
            planhistory.clear()
            self.statusBar().showMessage(tr("Verlauf aufgeräumt."), 5000)

    def rolls_dialog(self):
        """Open the dialog with the rolls of the printers."""
        from .plandialog import RollsDialog
        from .. import printjob, printers as _pr

        try:
            names = [p.name for p in _pr.list_printers() if p.name != _pr.PDF_TARGET]
        except Exception:
            names = []
        if not names:
            QMessageBox.information(self, tr("Rollen"), tr("Kein Drucker eingerichtet."))
            return
        cur = printjob.default_printer(self.session)
        if len(names) > 1:
            name, ok = QInputDialog.getItem(
                self, tr("Rollen"), tr("Drucker:"), names, names.index(cur) if cur in names else 0, False
            )
            if not ok:
                return
        else:
            name = names[0]
        RollsDialog(self, self.session, name).exec()

    def admin_dialog(self):
        """Open the management dialog and reload the configuration after saving."""
        from .admindialog import AdminDialog

        if AdminDialog(self, self.session).exec():
            self.ctl.reload_config()
            self.statusBar().showMessage(tr("Admin-Standards gespeichert und übernommen."), 6000)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        paths = [p for p in paths if _convert.is_supported(p)]
        if not paths:
            return
        if self.doc is not None and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Ctrl + drop = append to the current document
            start = len(self.doc)
            for p in paths:
                part = self._load_any(p)
                if part is not None:
                    self.doc.import_pages(part)
                    part.close()
            self._changed_doc(start, list(range(start, len(self.doc))))
        else:
            self.open_paths_here(paths)

    def _pf_stop(self):
        w = getattr(self, "_pf_worker", None)
        if w is not None and w.isRunning():
            w.wait(15000)

    def closeEvent(self, e):
        self._stop_jobs()
        self._pf_stop()
        if self.doc is not None and self.modified:
            r = QMessageBox.question(
                self,
                tr("Ungespeicherte Änderungen"),
                tr("Änderungen an „{0}“ speichern?").format(self.display_name),
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
            )
            if r == QMessageBox.StandardButton.Cancel or (r == QMessageBox.StandardButton.Save and not self.save()):
                e.ignore()
                return
        # The print settings of the session stay until the last window – then they expire.
        try:
            self.view._timer.stop()
            self.view.release_render()  # close the document in the render process
            self._thumb_src.release()
            self.view.doc = None  # the view must no longer touch the document that is about to be closed
        except Exception:
            pass
        if self.doc is not None:
            self.doc.close()
            self.doc = None
        super().closeEvent(e)
        host = getattr(self, "_host", None)
        if host is not None:
            host.tab_closed()
