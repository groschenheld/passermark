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
from PySide6.QtGui import QAction, QColor, QCursor, QIcon, QImage, QKeySequence, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QDialog, QDialogButtonBox, QDockWidget,
                               QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
                               QFrame, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPushButton,
                               QScrollArea, QSpinBox, QStyle, QStyledItemDelegate, QToolButton,
                               QVBoxLayout, QWidget)

from .. import images
from . import theme
from .common import MAX_RENDER_EDGE, render_pixmap
from .icons import icon as svg_icon

from .. import convert as _convert

_ALL_EXT = sorted({".pdf"} | images.IMAGE_EXT | _convert.OFFICE_EXT)
OPEN_FILTER = ";;".join([
    tr("Alle unterstützten") + " (" + " ".join(f"*{e} *{e.upper()}" for e in _ALL_EXT) + ")",
    tr("PDF-Dateien (*.pdf *.PDF)"),
    tr("Bilder") + " (" + " ".join(f"*{e}" for e in sorted(images.IMAGE_EXT)) + ")",
    tr("Office-Dokumente") + " (" + " ".join(f"*{e}" for e in sorted(_convert.OFFICE_EXT)) + ")",
])


def merge_files(parent, ctl, paths: list[str]):
    """Beliebige Dateien in Reihenfolge zu einem PDF-Dokument. Liefert (doc, hinweise) oder (None, [])."""
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
                box = QMessageBox(QMessageBox.Icon.Warning, tr("Umwandeln fehlgeschlagen"),
                                  tr("„{0}“ konnte nicht umgewandelt werden.\n\nDiese Datei überspringen und mit den anderen weitermachen?").format(os.path.basename(p)),
                                  QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, parent)
                box.setDetailedText("\n".join(lines))
                box.button(QMessageBox.StandardButton.Yes).setText(tr("Überspringen"))
                box.button(QMessageBox.StandardButton.No).setText(tr("Abbrechen"))
                r = box.exec()
                if r != QMessageBox.StandardButton.Yes:
                    out.close()
                    return None, []
                notes.append(tr("übersprungen: {0}").format(os.path.basename(p)))
                continue
            if part is None:          # Passwortabfrage abgebrochen
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
    """HDR-Fotos mit Zusatzbild (Helligkeitskarte) melden und die Reparatur wählen lassen.
        -> Optionen für images_to_document (None = keine solchen Bilder)."""
    from .hdrdialog import hdr_options
    found = [(p, images.hdr_aux_info(p)) for p in paths]
    found = [(p, i) for p, i in found if i is not None]
    if not found:
        return None
    names = ", ".join(f"„{os.path.basename(p)}“" for p, _i in found[:3]) + (" …" if len(found) > 3 else "")
    opts = hdr_options(parent, [i for _p, i in found], names, default_dpi, tr("Unverändert öffnen (2 Seiten)"))
    return {"keep": True} if opts is None else opts


def load_any(parent, ctl, path, workdir=None, notes=None):
    """PDF (mit Passwortabfrage), Bild oder Office-Datei -> pypdfium2-Dokument (None = abgebrochen)."""
    import tempfile
    if images.is_image(path):
        return images.images_to_document([path], ctl.image_dpi, ask_hdr(parent, [path], ctl.image_dpi))
    if _convert.is_office(path):
        from PySide6.QtWidgets import QApplication
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            pdf, used = _convert.office_to_pdf(path, workdir or tempfile.mkdtemp(prefix="passermark-conv-"),
                                               ctl.cfg.get("office_converter", "auto"))
        finally:
            QApplication.restoreOverrideCursor()
        if notes is not None:
            notes.append(tr("{0}: umgewandelt mit {1}").format(os.path.basename(path), used))
        # load into memory so the working folder may be deleted
        with open(pdf, "rb") as f:
            return pdfium.PdfDocument(f.read())
    return load_pdf(parent, path)

from ..papersizes import UI_FORMATS as PAPER_NAMES     # mm, Hochformat – gemeinsame Formattabelle


def page_size_text(w_pt: float, h_pt: float) -> str:
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
                password, ok = QInputDialog.getText(parent, tr("Passwort"), tr("Passwort für {0}:").format(os.path.basename(path)),
                                                    QLineEdit.EchoMode.Password)
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
    """Sauberes Verkleinern des Seitenbilds in einem Hintergrund-Thread. Beim Zoomen wird sofort grob skaliert
        (Sekundenbruchteile), das saubere Bild kommt kurz danach – ein großes Seitenbild blockiert so nie das
        Fenster (QImage.scaled gibt den Python-Lock frei). Je Seite zählt nur der neueste Auftrag."""
    done = Signal(object, object, object)          # Seite, Schlüssel, QImage

    _inst = None

    @classmethod
    def get(cls):
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
                out = img.scaled(tw, th, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
            except Exception:
                continue
            self.done.emit(widget, key, out)

    @staticmethod
    def _deliver(widget, key, img):
        try:
            widget.smooth_ready(key, img)
        except RuntimeError:                       # Seite inzwischen weg
            pass


class PageWidget(QWidget):
    def __init__(self, index: int, view=None):
        super().__init__()
        self.index = index
        # Seitenbild: einmal je Seite gerendert (etwa doppelte Ansichtsgröße), Zoomstufen und Miniatur
        # werden daraus nur skaliert – Fotos werden nicht bei jedem Zoomschritt neu entpackt
        self.master = None        # QImage (Gerätepixel), ganze Seite, mit Ansichtsdrehung
        self.mkey = None          # (Maßstab, Drehung) des Seitenbilds
        self.mstale = False       # Seite wurde bearbeitet: altes Bild zeigen, bis das neue da ist
        # starkes Zoomen über das Seitenbild hinaus: nur der sichtbare Ausschnitt, scharf
        self.tile = None          # QImage
        self.tile_rect = None     # QRectF in Widget-Koordinaten
        self.tkey = None          # (Maßstab, Drehung)
        self._scaled = None       # Seitenbild auf Widgetgröße skaliert (einmal je Größe)
        self._skey = None
        self.view = view
        self.setMouseTracking(True)

    def drop(self, tile_only: bool = False):
        self.tile, self.tile_rect, self.tkey = None, None, None
        if not tile_only:
            self.master, self.mkey, self.mstale = None, None, False
            self._scaled, self._skey = None, None

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect().adjusted(3, 3, 3, 3), QColor(0, 0, 0, 60))   # Schatten
        if self.master is not None:
            dpr = self.devicePixelRatioF()
            tw, th = max(1, round(self.width() * dpr)), max(1, round(self.height() * dpr))
            key = (tw, th, self.master.cacheKey())
            if self._skey != key:
                img = self.master
                if (img.width(), img.height()) != (tw, th):
                    if img.width() * img.height() <= 2_000_000:
                        img = img.scaled(tw, th, Qt.AspectRatioMode.IgnoreAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation)
                    else:                        # groß: sofort grob, sauber kommt aus dem Hintergrund
                        _Smoother.get().request(self, key, img, tw, th)
                        img = img.scaled(tw, th, Qt.AspectRatioMode.IgnoreAspectRatio,
                                         Qt.TransformationMode.FastTransformation)
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
        """Sauber verkleinertes Seitenbild aus dem Hintergrund – nur übernehmen, wenn es noch passt."""
        if key != self._skey or self.master is None:
            return
        pm = QPixmap.fromImage(img)
        pm.setDevicePixelRatio(self.devicePixelRatioF())
        self._scaled = pm
        self.update()

    # Maus -> Ansicht (Textauswahl bzw. Bearbeiten-Modus)
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
        self.cursor_px = None            # mouse position (screen, global) for the selection stroke
        if horizontal:
            self.setFixedHeight(self.SIZE)
        else:
            self.setFixedWidth(self.SIZE)

    def paintEvent(self, _):
        from PySide6.QtCore import QPoint
        from .. import measure as ms
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.PANEL))
        geo = self.view.ruler_geometry()
        if geo is None:
            return
        origin_vp, ppm = geo                          # Seitenecke (Viewport-Pixel), Pixel je mm
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
    viewMoved = Signal()                 # Scrollen/Zoom/Seite -> Lineale neu zeichnen
    masterReady = Signal(int)            # Seitenbild fertig -> Miniatur daraus ableiten
    infoReady = Signal()                 # Seitendaten (Rahmen, Drehung) vom Render-Prozess da

    MASTER_FACTOR = 2.0        # Seitenbild = doppelte Ganze-Seite-Größe: Zoomen bis dahin ohne neu zu rendern
    MASTER_PIXELS = 16_000_000
    KEEP_MASTERS = 2           # Seitenbilder ± so viele Seiten um die sichtbaren behalten

    JUMP_THRESHOLD = 120       # eine Mausrad-Raste; Touchpad-Bruchteile werden gesammelt
    JUMP_COOLDOWN = 0.30       # s – prevents kinetic scrolling from skipping several pages

    def __init__(self, single: bool = True):
        super().__init__()
        self.setWidgetResizable(False)
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.setStyleSheet(f"QScrollArea {{ background: {theme.VIEW}; }} #pages {{ background: {theme.VIEW}; }}")
        self.doc = None
        self.sizes = []
        self.base = "page"        # width | page | actual – Bezug je Seite
        self.factor = 1.0         # Zoom relativ zum Bezug (Strg+Mausrad, +/-)
        self.zoom = 1.0           # actual scale of the current page (display only)
        self.rotation = 0
        self.current = 0
        self.single = single
        self._acc = 0.0
        self._block_until = 0.0
        self.pages: list[PageWidget] = []
        self.sel = None           # Textauswahl: (Seite, Start-, Endzeichen)
        self._drag = None
        self._tp = {}             # Seite -> (PdfPage, PdfTextPage)
        self.imode = "text"       # Maus: text = Textauswahl; edit = Bearbeiten-Modus (Klicks an edit_click)
        self.edit_click = None    # callback (page, x, y in page coordinates, shift)
        self.meas = None          # Messung: {"page", "a": (x, y) pt, "b": (x, y) pt | None, "done": bool}
        self.on_measure = None    # callback (text for the status bar)
        self.on_cursor = None     # callback (page widget, mouse position) for the rulers
        self.editor = None        # Bearbeiten-Seitenleiste: press/drag/release/cursor (Seitenkoordinaten)
        self._edrag = False
        self.overlay = {}         # Seite -> [(x0, y0, x1, y1, Farbe)] in Seitenkoordinaten
        self._snap = {}           # Seite -> ([X-Kanten], [Y-Kanten]) – Einrasten beim Messen
        self._snap_prev = None    # Strg-Vorschau: (Seite, x, y, gerastet?) – Fadenkreuz vor dem 1. Klick
        self._snap_stuck = None   # Hysterese: {"x": Kante, "y": Kante} – wo das Fadenkreuz gerade klebt
        self.container = QWidget()
        self.container.setObjectName("pages")
        self.setWidget(self.container)
        self._timer = QTimer(self, singleShot=True, interval=30, timeout=self._render_visible)
        self._gen = 0             # Dokument-Stand: Ergebnisse älterer Stände werden verworfen
        self.proof = None         # Softproof der Ansicht (proof.proofed_render) oder None
        self._pkey = ()           # dazu: Schlüssel – Bilder mit anderem Softproof werden verworfen
        self._rkey = None         # Dokument im Render-Prozess
        self._src_path = None
        self._tmp = None          # eigene Zwischendatei für den Render-Prozess
        self._local = False       # im Programm rendern (Render-Prozess nicht verfügbar / Dokument dort nicht ladbar)
        self._rfail = set()       # Seiten, die im Render-Prozess scheiterten
        self._pinfo = None        # je Seite Rahmen/Drehung (renderproc.page_info) – ohne Seite zu laden
        self._lazy_boxes = {}     # Rückfall: Rahmen per pdfium, erst bei Bedarf
        self._chars = {}          # Seite -> Zeichenkästen (numpy) für den Text-Cursor, "pending" = angefragt
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.verticalScrollBar().valueChanged.connect(lambda _v: self.viewMoved.emit())
        self.horizontalScrollBar().valueChanged.connect(lambda _v: self.viewMoved.emit())

    # --------------------------------------------------------------- #
    def set_document(self, doc, keep_page: int | None = None, src=None, changed_pages=None):
        """src: Pfad oder Bytes des Dokuments für den Render-Prozess (None = aus doc speichern).
            changed_pages: Bearbeiten (gleiche Seitenzahl) – die bisherigen Bilder bleiben als Platzhalter stehen,
            bis die neuen da sind; die bearbeiteten Seiten kommen zuerst dran."""
        old = self.pages
        keep = changed_pages is not None and len(old) == len(doc)
        for w in self.pages:          # Seiten des vorherigen Dokuments entsorgen
            w.deleteLater()
        self._close_textpages()
        self.sel, self._drag = None, None
        self.meas = None
        self._snap = {}
        self._snap_prev = None
        self._snap_stuck = None
        self.doc = doc
        self.sizes = [doc.get_page_size(i) for i in range(len(doc))]
        # Endformat/Anschnitt und Seitenlage kommen vom Render-Prozess (ohne Seiten im Programm zu laden)
        self._pinfo, self._lazy_boxes, self._chars = None, {}, {}
        self.pages = [PageWidget(i, self) for i in range(len(doc))]
        for w in self.pages:
            w.setParent(self.container)
        if keep:
            # alte Bilder als Platzhalter weiter zeigen (kein weißes Aufblitzen), aber alle neu rendern:
            # ein auf mehreren Seiten verwendetes Element kann sich überall geändert haben
            for w, o in zip(self.pages, old):
                w.master, w.mkey, w.mstale = o.master, o.mkey, o.master is not None
        self._gen += 1
        self._rfail = set()
        self._open_render(src)
        self.current = min(keep_page or 0, max(0, len(self.pages) - 1))
        self.relayout()
        self.goto(self.current, force=True)

    # ---------------- Rendern (eigener Prozess, siehe renderclient.py) ---------------- #
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
                    self._tmp = src                      # Zwischendatei der Prüfung übernehmen (wird später gelöscht)
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
        if err:                                  # z. B. Passwort: diese Ansicht rendert im Programm
            self._local = True
            self._timer.start()
        elif isinstance(info, list) and len(info) == len(self.pages):
            self._pinfo = info
            self._snap = {}
            for w in self.pages:
                w.update()
            self.infoReady.emit()

    def release_render(self):
        """Fenster/Reiter zu: Dokument im Render-Prozess schließen, Zwischendatei löschen."""
        from .renderclient import RenderService
        svc = RenderService.get()
        svc.unregister(self)
        if self._rkey is not None:
            svc.close_doc(self._rkey, on_done=lambda _e, t=self._tmp: _remove_quiet(t))
        elif self._tmp:
            _remove_quiet(self._tmp)
        self._rkey, self._tmp = None, None

    # Schnittstelle für RenderService
    def render_priority(self) -> int:
        try:
            return 0 if self.isVisible() and self.window().isActiveWindow() else 2
        except RuntimeError:
            return 9

    def render_reset(self):
        """Render-Prozess neu gestartet: Dokument dort neu öffnen."""
        from .renderclient import RenderService
        if self._rkey is not None and self._src_path and os.path.isfile(self._src_path):
            RenderService.get().open_doc(self._rkey, self._src_path,
                                         on_done=lambda err, info=None, k=self._rkey: self._render_opened(k, err, info))

    def render_fallback(self):
        self._local = True
        self._timer.start()

    def _dev_scale(self, i: int) -> float:
        """Gerätepixel je pt für Seite i bei der aktuellen Ansicht."""
        return self.page_zoom(i) * self._dpi_scale() * self.devicePixelRatioF()

    def _master_scale(self, i: int) -> float:
        pw, ph = self._rot_size(i)
        s = self._dpi_scale()
        vw = max(50, self.viewport().width() - 2 * PAGE_GAP - 4)
        vh = max(50, self.viewport().height() - 2 * PAGE_GAP)
        fit = min(vw / (pw * s), vh / (ph * s)) * s * self.devicePixelRatioF()
        cap = min(MAX_RENDER_EDGE / max(1.0, pw), MAX_RENDER_EDGE / max(1.0, ph),
                  (self.MASTER_PIXELS / max(1.0, pw * ph)) ** 0.5)
        # stark rausgezoomt (viele Seiten): kleiner; ab Ganze-Seite-Größe: doppelt so groß, darüber Ausschnitte
        S = self._dev_scale(i)
        want = self.MASTER_FACTOR * max(fit * 0.5, min(S, fit))
        return max(0.02, min(want, cap))

    def set_proof(self, spec):
        """Softproof an (spec) oder aus (None): alle Seitenbilder neu, die alten bleiben bis dahin stehen."""
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
        return (round(self._dev_scale(w.index), 4), self.rotation)

    def _visible_rect(self, w) -> QRect:
        vp = self.viewport().rect()
        top_left = w.mapFrom(self.viewport(), vp.topLeft())
        return QRect(top_left, vp.size()).intersected(w.rect())

    def _wanted_pages(self) -> list:
        """Sichtbare Seiten (aktuelle zuerst)."""
        vis = [w for w in self.pages if w.isVisibleTo(self.container) and not self._visible_rect(w).isEmpty()]
        vis.sort(key=lambda w: (w.index != self.current, abs(w.index - self.current)))
        return vis

    def next_render(self):
        """Was als Nächstes gerendert werden soll – oder None. (Auch für das Rendern im Programm.)"""
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
        for w in vis:                                   # starkes Zoomen: scharfer Ausschnitt
            i = w.index
            if i in self._rfail or w.mkey is None:
                continue
            S = self._dev_scale(i)
            if S <= w.mkey[0] * 1.02:
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
            return dict(base, page=i, scale=S, kind="tile", crop=crop, tkey=need,
                        rect=(r.x(), r.y(), r.width(), r.height()))
        if self.single and not self._local:             # Nachbarseiten vorbereiten (nur im Hintergrund sinnvoll)
            for i in (self.current + 1, self.current - 1):
                if 0 <= i < len(self.pages) and i not in self._rfail:
                    w = self.pages[i]
                    if w.master is None or w.mstale or w.mkey[1] != rot:
                        return dict(base, page=i, scale=self._master_scale(i), kind="master")
        return None

    def render_done(self, req, img, err):
        if req.get("gen") != self._gen or (req.get("doc") is not None and req.get("doc") != self._rkey):
            return
        if req.get("pkey", ()) != self._pkey:
            return                                      # mit einem anderen Softproof gerendert
        i = req["page"]
        if not (0 <= i < len(self.pages)):
            return
        w = self.pages[i]
        if err or img is None:
            if err == "render process ended":
                return                                  # wird nach dem Neustart erneut angefragt
            self._rfail.add(i)
            self._render_one_local(w, req)              # diese Seite im Programm rendern
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
        """Im Programm rendern (Rückfall) – gleiche Anfrage wie an den Render-Prozess."""
        page = self.doc[req["page"]]
        try:
            crop = tuple(req["crop"]) if req.get("crop") else (0, 0, 0, 0)
            if req.get("proof"):
                from .. import proof
                im = proof.proofed_render(page, req["scale"], req["rotation"], crop, req["proof"], self._src_path,
                                          req["page"])
                return QImage(im.tobytes("raw", "RGB"), im.width, im.height, im.width * 3,
                              QImage.Format.Format_RGB888).copy()
            bmp = page.render(scale=req["scale"], rotation=req["rotation"] % 360, crop=crop, prefer_bgrx=True,
                              may_draw_forms=True, draw_annots=True)
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
        """Speicher: Seitenbilder nur um die sichtbaren Seiten behalten, Ausschnitte nur sichtbar."""
        vis = {w.index for w in self._wanted_pages()} or {self.current}
        lo, hi = min(vis) - self.KEEP_MASTERS, max(vis) + self.KEEP_MASTERS
        for w in self.pages:
            if w.index not in vis and w.tile is not None:
                w.drop(tile_only=True)
            if not (lo <= w.index <= hi) and w.master is not None:
                w.drop()

    def set_single(self, single: bool):
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
        return self.page_zoom(self.current) if self.sizes else self.zoom

    def relayout(self):
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
        """Ansicht gedreht: vorhandenes Seitenbild sofort mitdrehen (scharf kommt danach)."""
        if w.master is None or w.mkey is None or w.mkey[1] == self.rotation:
            return
        from PySide6.QtGui import QTransform
        w.master = w.master.transformed(QTransform().rotate((self.rotation - w.mkey[1]) % 360))
        w.mkey = (w.mkey[0], self.rotation)
        w.mstale = True                    # neu rendern (Seitenverhältnis/Kanten exakt)
        w._skey = None
        w.drop(tile_only=True)

    def _render_visible(self):
        """Nach Scrollen/Zoomen/Layout: Bedarf an den Render-Prozess melden (oder im Programm rendern)."""
        if self.doc is None or getattr(self.doc, "raw", None) is None:
            return                         # Dokument schon geschlossen (Fenster/Reiter zu, Zeitgeber kam danach)
        self._evict()
        for w in self._wanted_pages():
            w.update()                     # Ausschnitt einer anderen Zoomstufe nicht mehr zeigen
        if not self._local:
            from .renderclient import RenderService
            RenderService.get().kick()
            return
        for _ in range(12):                # Rückfall: im Programm, gleiche Bedarfsermittlung
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
        """Prüfung: zur Fundstelle springen und sie markieren (Rahmen um den Bereich, sonst um die Seite)."""
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
                if r.height() < vh:                    # Fundstelle ins obere Drittel holen
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
        self.goto(self.current + 1)

    def prev_page(self, at_end: bool = False):
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
        c = self.viewport().rect().center()
        self.zoom_at(factor, c)

    def zoom_at(self, factor: float, pos):
        """Zoomt um `factor`, der Punkt unter `pos` (Viewport-Koordinaten) bleibt stehen."""
        if not self.doc:
            return
        new_factor = max(0.02, min(self.factor * factor, 64.0))
        if abs(new_factor - self.factor) < 1e-5:
            return
        hb, vb = self.horizontalScrollBar(), self.verticalScrollBar()
        cx, cy = hb.value() + pos.x(), vb.value() + pos.y()
        page = next((w for w in self.pages if w.isVisibleTo(self.container)
                     and w.y() <= cy <= w.y() + w.height() + PAGE_GAP), None)
        if page is not None:
            fx = (cx - page.x()) / max(1, page.width())
            fy = (cy - page.y()) / max(1, page.height())
        self.factor = new_factor            # reference stays -> pages keep the same size relative to each other
        self.relayout()
        if page is not None:
            hb.setValue(int(page.x() + fx * page.width() - pos.x()))
            vb.setValue(int(page.y() + fy * page.height() - pos.y()))

    def _edge_jump(self, delta: float) -> bool:
        """delta < 0 = nach unten. True, wenn auf eine andere Seite gesprungen wurde."""
        import time
        vb = self.verticalScrollBar()
        now = time.monotonic()
        if now < self._block_until:
            return True                      # Nachlauf nach einem Sprung schlucken
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
        # Touchpads (v. a. Windows Precision/macOS-artige) liefern oft nur pixelDelta, angleDelta = 0
        ady = e.angleDelta().y() or e.pixelDelta().y() * 3
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            steps = ady / 120.0                     # 1 Raste = 120; Touchpads liefern Bruchteile
            if steps:
                self.zoom_at(1.15 ** steps, e.position().toPoint())
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
    # Textauswahl
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

    # ---------------- Seitendaten ohne Seite zu laden ---------------- #
    def page_info(self, i):
        return self._pinfo[i] if self._pinfo is not None and 0 <= i < len(self._pinfo) else None

    def page_boxes(self, i):
        """(TrimBox, BleedBox) für die Anzeige – None, solange unbekannt (Render-Prozess) bzw. nicht definiert."""
        info = self.page_info(i)
        if info is not None:
            return info["trim"], info["bleed"]
        if not (self._local or (self._rkey is None and self.doc is not None)):
            return None, None                        # kommt gleich vom Render-Prozess
        if i not in self._lazy_boxes:                # Rückfall: pdfium, nur diese Seite
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
        """Wie layout.trim_info, aus den Seitendaten (None = unbekannt/kein Anschnitt)."""
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
        """Seite -> Widget wie pdfium, aus den Seitendaten (siehe pagegeom.py). None = Seitendaten fehlen."""
        info = self.page_info(w.index)
        if info is None:
            return None
        from ..pagegeom import display_matrix
        return display_matrix(info, w.width(), w.height(), self.rotation)

    def to_page(self, w, pos):
        """Widget-Pixel -> Seitenkoordinaten (pt, PDF-System) – Drehung/CropBox wie pdfium."""
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
        r.FPDF_DeviceToPage(pg.raw, 0, 0, w.width(), w.height(), (self.rotation // 90) % 4,
                            int(pos.x()), int(pos.y()), ctypes.byref(px), ctypes.byref(py))
        return px.value, py.value

    def to_widget(self, w, x, y):
        m = self._display_matrix(w)
        if m is not None:
            from ..pagegeom import to_device
            dx, dy = to_device(m, x, y)
            return round(dx), round(dy)
        import ctypes
        import pypdfium2.raw as r
        pg, _tp = self._textpage(w.index)
        dx, dy = ctypes.c_int(), ctypes.c_int()
        r.FPDF_PageToDevice(pg.raw, 0, 0, w.width(), w.height(), (self.rotation // 90) % 4,
                            x, y, ctypes.byref(dx), ctypes.byref(dy))
        return dx.value, dy.value

    def _rect_widget(self, w, x0, y0, x1, y1):
        from PySide6.QtCore import QRectF
        a = self.to_widget(w, x0, y0)
        b = self.to_widget(w, x1, y1)
        return QRectF(min(a[0], b[0]), min(a[1], b[1]), abs(a[0] - b[0]), abs(a[1] - b[1]))

    def _hover_text(self, w, pos, tol=4.0) -> bool:
        """Liegt Text unter der Maus? Für den Cursor – lädt die Seite NICHT im Programm (Zeichenkästen kommen
            vom Render-Prozess); ist die Textseite schon geladen, wird sie genommen."""
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
        return bool(((ch[:, 0] - tol <= x) & (x <= ch[:, 2] + tol) & (ch[:, 1] - tol <= y) & (y <= ch[:, 3] + tol)).any())

    def _char_at(self, w, pos, tol=4.0):
        _pg, tp = self._textpage(w.index)
        x, y = self.to_page(w, pos)
        i = tp.get_index(x, y, tol, tol)
        return i if i is not None and i >= 0 else -1

    # --------------------------------------------------------------- #
    # Lineal und Messen
    # --------------------------------------------------------------- #
    def ruler_geometry(self):
        """(linke obere Seitenecke in Viewport-Pixeln, Pixel je mm) der aktuellen Seite – oder None."""
        from PySide6.QtCore import QPoint
        if not self.doc or not (0 <= self.current < len(self.pages)):
            return None
        w = self.pages[self.current]
        pw, _ph = self._rot_size(self.current)
        if pw <= 0 or w.width() <= 0:
            return None
        return w.mapTo(self.viewport(), QPoint(0, 0)), w.width() / pw * 72.0 / 25.4

    def page_matrix(self, w):
        """Lineare Abbildung Seite -> Bildschirm (a, b, c, d) inkl. Zoom und Drehung, aus pdfium abgeleitet."""
        x0, y0 = self.to_page(w, QPointF(w.width() / 2, w.height() / 2))
        far = 1000.0
        p0 = self.to_widget(w, x0, y0)
        px = self.to_widget(w, x0 + far, y0)
        py = self.to_widget(w, x0, y0 + far)
        return ((px[0] - p0[0]) / far, (px[1] - p0[1]) / far, (py[0] - p0[0]) / far, (py[1] - p0[1]) / far)

    def _snap_candidates(self, w):
        """Einrast-Kandidaten der Seite (pt), getrennt nach Priorität:
        1) Schnitt-/Innenlinien (Seitenrand, TrimBox, BleedBox) – Vorrang,
        2) Bildkanten und Vektorlinien-Punkte.
        Text/Buchstaben werden bewusst NICHT einrastbar. Je Seite gecacht."""
        if w.index in self._snap:
            return self._snap[w.index]
        bx, by, ox, oy = set(), set(), set(), set()
        try:
            pg, _tp = self._textpage(w.index)              # Messen: Objekte der Seite werden gebraucht
            crop = pg.get_cropbox()
            bx |= {crop[0], crop[2]}
            by |= {crop[1], crop[3]}
            if True:
                for b in self.page_boxes(w.index):
                    if b is not None:
                        bx |= {b[0], b[2]}
                        by |= {b[1], b[3]}
            try:                          # Objekte: Bilder und Vektorpfade – kein Text
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
                            # einzelne Pfadsegmente: Linienenden, Kurven-Stützpunkte –
                            # präzises Einrasten an echten Vektorlinien
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
        # Diagnose (einmal je Seite im Terminal): zeigt, ob Kandidaten gefunden wurden
        print(f"[Passermark] Einrasten Seite {w.index + 1}: {len(out[0])} Schnitt-/Innen-X, "
              f"{len(out[1])} -Y, {len(out[2])} Bild-/Vektor-X, {len(out[3])} -Y", flush=True)
        return out

    def _snap_point(self, w, x, y, ctrl):
        """Fadenkreuz einrasten – nur mit Steuerung (Strg) gedrückt. Priorität:
        1) Schnitt-/Innenlinien (Seitenrand/TrimBox/BleedBox) fixieren zuerst,
        2) sonst Bildkanten/Vektorlinien-Punkte.
        Magnetisch mit Hysterese: einrasten ab ~8 Bildschirmpixeln Nähe, aber
        erst wieder loslassen, wenn die Maus ~24 px weit weg ist – so „klebt“ das
        Fadenkreuz während eines leichten Mausschwungs an der Kante und rollt
        erst bei richtigem Schwung weiter."""
        if not ctrl:
            self._snap_stuck = None
            return x, y
        bxs, bys, oxs, oys = self._snap_candidates(w)
        pw, ph = self._rot_size(w.index)
        sx = 10.0 * pw / max(1, w.width())
        sy = 10.0 * ph / max(1, w.height())

        def near(vals_pri, vals_obj, v, tol, key):
            release = tol * 8.0                    # Loslass-Schwelle: 8× Einrast-Toleranz
                                                       # (~80 px) – das Kreuz soll wirklich
                                                       # auf der Kante stehenbleiben
            stuck = self._snap_stuck or {}
            old = stuck.get(key)
            if old is not None and abs(old - v) <= release:
                return old                         # hängt an der Kante fest
            best, bd = None, tol
            for c in vals_pri:                     # zuerst Schnitt-/Innenlinien
                d = abs(c - v)
                if d <= bd:
                    best, bd = c, d
            if best is None:                        # sonst Bild-/Vektorkanten
                for c in vals_obj:
                    d = abs(c - v)
                    if d <= bd:
                        best, bd = c, d
            stuck[key] = best                       # None = nicht gerastet (auch merken)
            self._snap_stuck = stuck
            return best if best is not None else v

        return near(bxs, oxs, x, sx, "x"), near(bys, oys, y, sy, "y")

    def _measure_point(self, w, pos, shift, ctrl):
        """Mausposition -> Seitenpunkt; mit Umschalt waagrecht/senkrecht/45° zum Startpunkt eingerastet."""
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
        return self._snap_point(w, x, y, ctrl)   # Strg = Einrasten an Schnitt-/Bild-/Vektorlinien

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
            a = self._measure_point(w, e.position(), False, ctrl)   # 1. Klick: Anfang
            self.meas = {"page": w.index, "a": a, "b": None, "done": False}
        else:
            m["b"] = self._measure_point(w, e.position(), shift,
                                          bool(e.modifiers() & Qt.KeyboardModifier.ControlModifier))  # 2. Klick: Ende
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
            m["b"] = self._measure_point(w, e.position(), shift,
                                         bool(e.modifiers() & Qt.KeyboardModifier.ControlModifier))  # Gummiband
            self._measure_report(w)
            w.update()
        elif self.on_measure is not None and (m is None or m["done"]):
            geo = self.ruler_geometry()
            if geo is not None and w.index == self.current:
                ppm = geo[1]
                if m is None:
                    self.on_measure(ms.describe_pos(e.position().x() / ppm, e.position().y() / ppm, l10n.current()))
            # Strg gehalten: Vorschau-Fadenkreuz, das auf der nächsten Kante einrastet
            # (schon vor dem 1. Klick sichtbar – danach rastet das Gummiband-Ende)
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
        self.setFocus()
        if self.imode == "measure":
            self._measure_press(w, e)
            return
        if self.imode == "edit":
            x, y = self.to_page(w, e.position())
            if self.editor is not None:
                self._edrag = True
                self.editor.press(w.index, x, y, self._tol_pt(w),
                                   bool(e.modifiers() & Qt.KeyboardModifier.ControlModifier))
            elif self.edit_click is not None:
                self.edit_click(w.index, x, y, bool(e.modifiers() & (Qt.KeyboardModifier.ShiftModifier
                                                                     | Qt.KeyboardModifier.ControlModifier)))
            return
        i = self._char_at(w, e.position(), 12.0)
        self._drag = (w.index, i) if i >= 0 else None
        old = self.sel
        self.sel = None
        if old is not None and 0 <= old[0] < len(self.pages):
            self.pages[old[0]].update()

    def mouse_move(self, w, e):
        if self.imode == "measure":
            w.setCursor(Qt.CursorShape.CrossCursor)
            self._measure_move(w, e)
            return
        if self.on_cursor is not None:
            self.on_cursor(w, e.position())
        if self.imode == "edit":
            x, y = self.to_page(w, e.position())
            if self.editor is not None and self._edrag:
                self.editor.drag(w.index, x, y)
                return
            kind = self.editor.cursor(w.index, x, y, self._tol_pt(w)) if self.editor is not None else None
            w.setCursor({"move": Qt.CursorShape.SizeAllCursor, "scale": Qt.CursorShape.SizeFDiagCursor}.get(
                kind, Qt.CursorShape.PointingHandCursor))
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
        if self.imode in ("edit", "measure"):
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
        if self.sel is None:
            return ""
        page, a, b = self.sel
        _pg, tp = self._textpage(page)
        return tp.get_text_range(a, b - a + 1).replace("\r\n", "\n").replace("\r", "\n")

    def select_page_text(self):
        if not self.doc:
            return
        _pg, tp = self._textpage(self.current)
        n = tp.count_chars()
        if n:
            self.sel = (self.current, 0, n - 1)
            self.pages[self.current].update()

    def paint_overlay(self, w, p):
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
                for (x, y) in ((ax, ay), (bx, by)):
                    p.drawEllipse(QPointF(x, y), 3.5, 3.5)
            elif m is not None and m["page"] == w.index:
                ax, ay = self.to_widget(w, *m["a"])
                p.setPen(QPen(QColor(theme.ACCENT), 2))
                p.drawLine(ax - 6, ay, ax + 6, ay)
                p.drawLine(ax, ay - 6, ax, ay + 6)
            sp = self._snap_prev
            if sp is not None and sp[0] == w.index:
                # Strg-Vorschau-Fadenkreuz; fett + Kreis, wenn auf einer Kante eingerastet
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
                # Endformat = grüne innere Grenze, Anschnitt = dezente rote Umrandung
                # (keine rote Vollfläche mehr); BleedBox rot gestrichelt (wird nicht mitgedruckt)
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
                # Ring zwischen Seitenrand und Endformat: nur ein feiner roter Rahmen
                ring_pen = QPen(red, 1.0)
                ring_pen.setStyle(Qt.PenStyle.DotLine)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(ring_pen)
                p.drawRect(outer)
                # innere Grenze (Endformat) kräftig grün – wie in der VDP-Vorschau
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
                if style == "dash" and items and w.master is not None and w.width() > 0:
                    # Ziehen: das Objekt als Bild mitschieben (aus dem Seitenbild, ohne neu zu rendern)
                    sx0, sy0, sx1, sy1 = items[0][:4]
                    src = self._rect_widget(w, sx0, sy1, sx1, sy0)
                    f = w.master.width() / w.width()
                    p.setOpacity(0.6)
                    p.drawImage(self._rect_widget(w, x0, y1, x1, y0), w.master,
                                QRectF(src.x() * f, src.y() * f, src.width() * f, src.height() * f))
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
            if mk and mk[0] == w.index:                # Fundstelle aus der Prüfung
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
        cur = self.current
        self.rotation = (self.rotation + delta) % 360
        self.relayout()
        self.goto(cur, force=True)


THUMB_PIX = int(Qt.ItemDataRole.UserRole) + 1
THUMB_ASPECT = int(Qt.ItemDataRole.UserRole) + 2
THUMB_W = int(Qt.ItemDataRole.UserRole) + 3


class ThumbList(QListWidget):
    """Seitenübersicht. Zwei Anordnungen: eine Spalte (Vorschau füllt die Breite) oder Raster
        (feste Kachelgröße, so viele nebeneinander wie Platz haben). Strg + Mausrad skaliert."""
    resized = Signal()
    zoomed = Signal(int)                 # Strg + Mausrad: +1 größer, -1 kleiner
    pagesMoved = Signal(list, int)       # gewählte Seiten (Zeilen), Einfügestelle (vor dieser Zeile; count = ans Ende)
    TILE_MIN, TILE_MAX = 60, 600

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.grid_mode = False
        self.tile = 140
        self._press = None               # (Position, Zeile, Auswahl-Änderung aufgeschoben)
        self._drop_ins = None            # Einfügestelle beim Ziehen (gelber Balken)
        self._scroll_timer = QTimer(self, interval=40, timeout=self._auto_scroll)
        self._scroll_dir = 0

    # ---------------- Seiten ziehen (Umordnen mit gelbem Balken) ---------------- #
    def mousePressEvent(self, e):
        self._drop_ins = None
        if e.button() == Qt.MouseButton.LeftButton:
            it = self.itemAt(e.position().toPoint())
            plain = not (e.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))
            if it is not None and it.isSelected() and plain and len(self.selectedItems()) > 1:
                # Klick auf eine schon gewählte Seite: Mehrfachauswahl erst beim Loslassen auflösen (sonst wäre sie
                # weg, bevor man ziehen kann)
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
                super().mouseMoveEvent(e)                  # Gummiband/Auswahl wie gewohnt
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
        if press is not None and press[2]:                # aufgeschobener Klick: jetzt nur diese Seite wählen
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
            # senkrechter Balken zwischen zwei Seiten; am Zeilenanfang hinter die letzte Seite der vorigen Zeile
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
        vw = max(80, self.viewport().width() - 2)
        return vw if not self.grid_mode else max(self.TILE_MIN, min(self.tile, vw))

    def set_grid(self, on: bool):
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
        bw = rect.width() - 2 * self.PAD
        return QRect(rect.x() + self.PAD, rect.y() + self.PAD, bw, int(bw * self.BOX_ASPECT))

    def image_rect(self, rect, aspect):
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
        p.drawText(QRect(r.x(), box.bottom() + 2, r.width(), self.LABEL),
                   int(Qt.AlignmentFlag.AlignCenter), str(index.data(Qt.ItemDataRole.DisplayRole)))
        p.restore()


class _ThumbSource:
    """Miniaturen für RenderService: rendert nur, was nicht schon aus einem Seitenbild abgeleitet werden kann."""

    def __init__(self, win):
        self.win = win
        self.failed = set()

    def usable(self) -> bool:
        from .renderclient import RenderService
        v = self.win.view
        return RenderService.get().ok and not v._local and v._rkey is not None

    def kick(self):
        from .renderclient import RenderService
        svc = RenderService.get()
        svc.register(self)
        svc.kick()

    def release(self):
        from .renderclient import RenderService
        RenderService.get().unregister(self)

    def render_priority(self) -> int:
        try:
            return 1 if self.win.isActiveWindow() else 3
        except RuntimeError:
            return 9

    def next_render(self):
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
            win._thumb_from_master(i)                    # Seitenbild schon da?
            if it.data(THUMB_W) == iw:
                q.pop(0)
                continue
            return {"doc": win.view._rkey, "gen": win.view._gen, "page": i, "scale": sc,
                    "rotation": win._view_rot(), "kind": "thumb", "iw": iw}
        return None

    def render_done(self, req, img, err):
        win = self.win
        if req.get("gen") != win.view._gen or win.doc is None:
            return
        i = req["page"]
        if err or img is None:
            if err != "render process ended":
                self.failed.add((req["gen"], i))       # bleibt leer statt endlos neu anzufragen
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
        pass

    def render_fallback(self):
        self.win._thumb_timer.start()


class _MergeList(QListWidget):
    """Liste im Zusammenführen-Dialog: intern umsortieren und Dateien/Ordner aus dem Dateimanager hineinziehen."""
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
    """Merge several PDFs/images in the desired order into one document. Für große Mengen (z. B. 110 Pläne):
        Ordner hinzufügen, Dateien hineinziehen, nach Name sortieren; nachkommende Dateien (Explorer) landen hier."""

    def __init__(self, parent, start: list[str] | None = None):
        super().__init__(parent)
        self.setWindowTitle(tr("Dokumente zusammenführen"))
        self.resize(620, 520)
        self._manual = False                     # selbst umsortiert: neue Dateien nur noch anhängen
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
        for text, fn in [(tr("Hinzufügen…"), self._add), (tr("Ordner hinzufügen …"), self._add_folder),
                         (tr("Entfernen"), self._remove), ("▲ " + tr("Nach oben"), lambda: self._move(-1)),
                         ("▼ " + tr("Nach unten"), lambda: self._move(1)), (tr("Nach Name sortieren"), self._sort)]:
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
        """Dateien (oder Ordner) dazu – ohne Doppelte; solange nicht selbst umsortiert, nach Name sortiert."""
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
        """Nach Dateiname (natürlich: Plan 2 vor Plan 10)."""
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
        for r in (rows if d < 0 else reversed(rows)):
            it = self.lst.takeItem(r)
            self.lst.insertItem(r + d, it)
            it.setSelected(True)

    def paths(self):
        return [self.lst.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.lst.count())]


class PageEdit(QLineEdit):
    """Seitenanzeige „aktuell / gesamt“ in EINEM Feld. QLineEdit statt QSpinBox:
    wird vom Theme überall zuverlässig dargestellt (der QSpinBox wurde z. T. leer
    gerendert). Einfach die Seitenzahl eintippen und Enter – oder woanders hinklicken."""
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
            "QLineEdit:focus { border-color: #8a9099; }")

    # ---- Anzeige nachführen ----
    def set_count(self, n: int):
        self._n = max(0, n)
        self._refresh()

    def set_current(self, i: int):
        self._cur = i
        self._refresh()

    def _refresh(self):
        if not self.hasFocus():
            self.setText(f"{self._cur + 1} / {self._n}" if self._n else "")
        fm = self.fontMetrics()
        self.setFixedWidth(max(56, fm.horizontalAdvance(f"{self._n} / {self._n}") + 24))

    # ---- Eingabe: führende Zahl, Enter/Verlassen springt zur Seite ----
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
        super().focusInEvent(e)
        self.setText(str(self._cur + 1))            # beim Reinschreiben nur die nackte Zahl
        self.selectAll()


class MainWindow(QMainWindow):
    def __init__(self, ctl):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.ctl = ctl
        self.resize(1280, 860)
        self.setAcceptDrops(True)
        self.doc = None
        self.path = None           # Datei auf der Platte (None = noch nie gespeichert)
        self.display_name = ""
        self.modified = False

        self.view = PageView(single=getattr(ctl, "view_single", True))
        self._jobs = []                      # running jobs (separate processes)
        # Lineale oben/links an der Kante der Ansicht (bleiben beim Scrollen stehen)
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
        self.thumbs.setStyleSheet(f"QListWidget {{ background: {theme.BG}; border: none; }}"
                                  "QListWidget::item, QListWidget::item:selected { background: transparent; }")
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
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable
                         | QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self.resizeDocks([dock], [165], Qt.Orientation.Horizontal)
        self._thumb_queue = []
        self._thumb_timer = QTimer(self, interval=0, timeout=self._render_thumbs)
        self._thumb_src = _ThumbSource(self)             # Miniaturen über den Render-Prozess
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
        self.statusBar().addPermanentWidget(self.lbl_measure)     # bottom far right, does not get in the way
        self.view.on_measure = self.lbl_measure.setText
        self.lbl_proof = QLabel()
        self.lbl_proof.setContentsMargins(8, 0, 8, 0)
        self.lbl_proof.setStyleSheet(f"color: {theme.ACCENT};")
        self.lbl_proof.hide()
        self.statusBar().addPermanentWidget(self.lbl_proof)
        self._update_title()

    # ---------------- Arbeitsbereiche ---------------- #
    WORKSPACES = ("view", "prep", "edit", "vdp", "auto")

    def _build_workspaces(self, pages_dock):
        """Second bar: choose the work area; the tools of that area to its right."""
        from PySide6.QtGui import QActionGroup
        self._pages_dock = pages_dock
        self.a_presets = self._act(tr("Preset-Ordner öffnen"), self._open_presets_dir, None, "folder_gear")
        self.a_cli = self._act(tr("Kommandozeile – Anleitung (PDF)"), self._open_cli_howto, None, "terminal")
        self.a_vdp_howto = self._act(tr("Variable Daten – Anleitung (PDF)"), self._open_vdp_howto, None, "book")
        self.a_examples = self._act(tr("Beispiele für Variable Daten holen …"), self._get_examples, None, "qr")
        tools = {"view": [(self.a_copy, tr("Text kopieren"))],
                 "prep": [(self.a_preflight, tr("Prüfen")), (self.a_colorcheck, tr("Farbe")),
                          (self.a_press, tr("Für Druckerei")), (self.a_manip_cmyk, tr("CMYK")),
                          (self.a_manip_crop, tr("Beschneiden")), (self.a_cut, tr("CutContour")),
                          (self.a_separate, tr("Objekte trennen")), (self.a_repair, tr("Reparieren"))],
                 "edit": [(self.a_edit, tr("Text/Ebenen")), (self.a_ins_after, tr("Einfügen")),
                          (self.a_delete, tr("Löschen")), (self.a_rot_l, tr("Links drehen")),
                          (self.a_rot_r, tr("Rechts drehen")), (self.a_up, tr("Nach vorne")),
                          (self.a_down, tr("Nach hinten")), (self.a_split, tr("Teilen")),
                          (self.a_merge, tr("Zusammenführen")),
                          (self.a_export, tr("Exportieren"))],
                 "vdp": [(self.a_vdp, tr("Variable Daten")), (self.a_data, tr("Daten erfassen")),
                         (self.a_examples, tr("Beispiele")),
                         (self.a_vdp_howto, tr("Anleitung"))],
                 "auto": [(self.a_presets, tr("Presets")), (self.a_cli, tr("Anleitung"))]}
        self.addToolBarBreak()
        tb = self.ws_bar = self.addToolBar(tr("Arbeitsbereich"))
        tb.setObjectName("workspaces")
        tb.setMovable(False)
        tb.setIconSize(QSize(18, 18))
        grp = QActionGroup(self)
        grp.setExclusive(True)
        self.ws_actions = {}
        names = {"view": tr("Anzeigen & Drucken"), "prep": tr("Druckaufbereitung"), "edit": tr("Bearbeiten"),
                 "vdp": tr("Variable Daten"), "auto": tr("Automatisierung")}
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
        tb.setStyleSheet(f"QToolButton#workspace {{ padding: 3px 10px; border-bottom: 2px solid transparent; }}"
                         f"QToolButton#workspace:checked {{ color: {theme.ACCENT}; border-bottom: 2px solid {theme.ACCENT};"
                         f" background: transparent; }}")
        tb.addSeparator()
        self.ws_tools = {}
        for key, acts in tools.items():
            holders = []
            for a, text in acts:
                a.setIconText(text)                    # short text for bars; menus keep showing the full text
                b = QToolButton()
                b.setDefaultAction(a)
                b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                holders.append(tb.addWidget(b))
            self.ws_tools[key] = holders
        grp.triggered.connect(lambda a: self.set_workspace(a.data()))
        from .. import l10n
        key = l10n.load_settings().get("workspace", "view")
        self.set_workspace(key if key in self.ws_actions else "view", remember=False)

    def set_workspace(self, key: str, remember: bool = True):
        self.workspace = key
        self.ws_actions[key].setChecked(True)
        for k, holders in self.ws_tools.items():
            for h in holders:
                h.setVisible(k == key)
        if key != "edit" and self.a_edit.isChecked():
            self.a_edit.setChecked(False)                  # edit mode belongs to the Edit area
        if key == "prep":
            self.pf_dock.show()
            self.pf_dock.raise_()
        elif key == "edit":
            self._pages_dock.show()
            if not self.a_edit.isChecked():
                self.a_edit.setChecked(True)       # Bearbeiten-Modus starten: Dock + Listen füllen
            self.edit_dock.raise_()                # Dock vor die Seitenübersicht holen
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
        """Ordner „licenses“ neben dem Programm (Installer/AppImage); aus dem Quellcode: LICENSE."""
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

    # ---------------- Bearbeiten-Modus (Text und Ebenen) ---------------- #
    def _build_edit(self, pages_dock):
        from .editpanel import EditPanel
        self.edit_panel = EditPanel(self)
        class _Dock(QDockWidget):
            def closeEvent(dock_self, e):          # the close button ends edit mode
                self.a_edit.setChecked(False)
                e.accept()
        self.edit_dock = _Dock(tr("Bearbeiten"), self)
        self.edit_dock.setWidget(self._dock_scroll(self.edit_panel))
        self.edit_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable
                                   | QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.edit_dock)
        self.tabifyDockWidget(pages_dock, self.edit_dock)
        self.edit_dock.hide()
        pages_dock.raise_()
        self.edit_dock.visibilityChanged.connect(lambda vis: vis and self.edit_panel.refresh())
        self.view.edit_click = self.edit_panel.page_click
        self.view.editor = self.edit_panel
        self.view.pageChanged.connect(lambda _p: self.a_edit.isChecked() and self.edit_panel.refresh())

    # ---------------- Lineale und Messen ---------------- #
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
            return                                         # nur rechnen, wenn die Lineale zu sehen sind
        gpos = w.mapToGlobal(pos.toPoint())
        self.ruler_h.cursor_px = gpos
        self.ruler_v.cursor_px = gpos
        self._rulers_update()

    # ---------------- Softproof ---------------- #
    def _toggle_proof(self, on: bool):
        from .softproofdialog import build_spec, load_saved
        spec = build_spec(self.session.cfg, load_saved()) if on else None
        if on and spec is None:
            self.softproof_dialog()                     # noch nichts gewählt (oder Profil weg): einrichten
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
        from .softproofdialog import SoftproofDialog, build_spec, load_saved
        dlg = getattr(self, "_proof_dlg", None)
        if dlg is None:
            dlg = SoftproofDialog(self, self.session.cfg)
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
        """Farbprüfung → Softproof: diese Druckbedingung im Softproof zeigen."""
        from .softproofdialog import build_spec, load_saved, save
        saved = dict(load_saved(), key=choice["key"])
        save(saved)
        self._proof_dlg = None                      # Auswahl neu einlesen
        spec = build_spec(self.session.cfg, saved)
        if spec:
            self._apply_proof(spec)

    # ---------------- Farbe ---------------- #
    def _build_color(self, pages_dock):
        from .colorpanel import ColorPanel
        self.color_panel = ColorPanel(self)
        self.color_panel.data_fn = lambda: self._doc_bytes() if self.doc is not None else None
        self.color_panel.cfg_fn = lambda: self.session.cfg
        self.color_panel.goto_spot.connect(lambda p, box: self.view.show_spot(p - 1, box))
        self.color_panel.action_requested.connect(self._color_action)
        self.color_panel.proof_requested.connect(self._proof_for_choice)
        self.color_dock = QDockWidget(tr("Farbe"), self)
        self.color_dock.setWidget(self._dock_scroll(self.color_panel))
        self.color_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable
                                    | QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.color_dock)
        self.tabifyDockWidget(pages_dock, self.color_dock)
        self.color_dock.hide()

    def color_check(self):
        if self.doc is None:
            return
        self.color_panel.reload_choices()
        self.color_dock.show()
        self.color_dock.raise_()
        self.color_panel.start()

    def _color_refresh(self):
        """Papiere/Profile geändert: Auswahl in Farbprüfung und Softproof neu einlesen."""
        from .. import colorlab
        colorlab._WHITE_CACHE.clear()
        self._proof_dlg = None
        if hasattr(self, "color_panel"):
            self.color_panel.reload_choices()
            if self.color_dock.isVisible() and self.color_panel.facts is not None:
                self.color_panel.start()

    def materials_dialog(self, select: str = "", measure: bool = False):
        from .materialsdialog import MaterialsDialog
        dlg = MaterialsDialog(self, self.session.cfg, select, measure)
        dlg.changed.connect(self._color_refresh)
        dlg.exec()

    def standard_profiles(self, surface: str = ""):
        from .materialsdialog import StandardProfilesDialog
        dlg = StandardProfilesDialog(self, surface)
        dlg.exec()
        if dlg.fetched:
            self._color_refresh()

    def _color_help(self):
        from .materialsdialog import show_help
        show_help(self)

    def press_dialog(self):
        if self.doc is None:
            return
        from .colorpanel import load_choice
        from .pressdialog import PressDialog
        ch = load_choice()
        base = os.path.splitext(self.display_name or tr("Dokument"))[0]
        folder = os.path.dirname(self.path) if self.path else (getattr(self, "_suggest_dir", "") or os.path.expanduser("~"))
        dlg = PressDialog(self, self._doc_bytes, self.session.cfg, os.path.join(folder, base + tr("_Druck") + ".pdf"),
                          ch.get("key", ""), ch.get("intent", ""), int(ch.get("tac", 0) or 0))
        dlg.open_result.connect(lambda path: self.ctl.open_paths([path], tab_of=self))
        dlg.exec()

    def _ask_rgb(self, target_name: str) -> str:
        """RGB immer fragen: "convert" | "keep" | "" (abgebrochen)."""
        box = QMessageBox(QMessageBox.Icon.Question, tr("RGB im Dokument"), tr(
            "Die Datei enthält RGB. Nach „{0}“ umwandeln oder RGB mit Profil weitergeben (die Druckerei rechnet "
            "um)?").format(target_name), parent=self)
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
            s = pressexport.PressSettings(target=p["target"], intent=p.get("intent") or "relative",
                                          cmyk_mode=p.get("cmyk_mode") or "rgb_only" if kind == "convert" else "none",
                                          source=p.get("source") or "", rgb=rgb,
                                          tac_limit=int(p.get("tac_limit") or 0), material=p.get("material") or "")
            self.start_job("press", core.settings_to_dict(s), suffix=tr("_Druck"), title=tr("Farbe"))
        elif kind == "preflight":
            self.pf_dock.show()
            self.pf_dock.raise_()
            self._pf_start(force=True)
        elif kind == "measure":
            mid = p.get("material") or ""
            m = colorlab.material_by_id(self.session.cfg, mid) if mid else None
            if m is not None and m.get("scope") == "admin":
                if QMessageBox.question(self, tr("Papier messen"), tr(
                        "„{0}“ ist ein Papier der Verwaltung (für alle). Als eigenes Papier übernehmen und messen? "
                        "Ändern für alle geht unter Verwaltung → Standardeinstellungen → Materialien.").format(
                            m.get("name") or mid)) != QMessageBox.StandardButton.Yes:
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

    def _measure_mode(self, on: bool):
        if on:
            if self.a_edit.isChecked():
                self.a_edit.setChecked(False)              # Edit and Measure are mutually exclusive
            self.view.imode = "measure"
            self.view.sel = None
            if not self.a_rulers.isChecked():
                self.a_rulers.setChecked(True)
            self.statusBar().showMessage(tr("Messen: 1. Klick Anfang, 2. Klick Ende · Umschalt = waagrecht/senkrecht/45° "
                                            "· Esc = abbrechen"), 8000)
        else:
            if self.view.imode == "measure":
                self.view.imode = "text"
            self.view.measure_clear()

    def _edit_mode(self, on: bool):
        if on and self.a_measure.isChecked():
            self.a_measure.setChecked(False)
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
        self.pf_panel.data_fn = self._doc_bytes
        self.pf_panel.file_fn = self._file_bytes
        self.pf_panel.result_ready.connect(self._pf_result)
        self.pf_panel.job_requested.connect(
            lambda kind, s, suffix, title: self.start_job(
                kind, s, suffix=suffix, title=title,
                src_data=self.pf_panel.take_job_data() if kind == "shrink" else None))
        self.pf_panel.goto_page.connect(lambda p: self.view.goto(p - 1))
        self.pf_panel.goto_spot.connect(lambda p, box: self.view.show_spot(p - 1, box))
        self.pf_panel.recheck.connect(lambda: self._pf_start(force=True))
        self.pf_dock = QDockWidget(tr("Prüfung"), self)
        self.pf_dock.setWidget(self._dock_scroll(self.pf_panel))
        self.pf_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable
                                 | QDockWidget.DockWidgetFeature.DockWidgetMovable)
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
        """Die Datei wie auf der Platte (unverändert geöffnet, unverschlüsselt) – sonst der aktuelle Stand.
            Für Größe/Verkleinern: pdfium speichert neu und verwischt sonst, was wirklich in der Datei steckt."""
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
        # eigener Prozess: kein Ausbremsen der Oberfläche (Python-Threads teilen sich eine Sperre), kein pdfium
        # im Programm; geprüft wird die Datei (unverändert) bzw. der Stand, den auch die Vorschau zeigt
        from .renderclient import RenderService
        svc = RenderService.get("analysis")
        path = None
        if svc.ok:
            if not self.modified and self.path and self.path.lower().endswith(".pdf") and os.path.isfile(self.path) \
                    and not self.view._local:
                path = self.path
            elif self.view._src_path and os.path.isfile(self.view._src_path) and not self.view._local:
                path = self.view._src_path
        if path is None:
            self._pf_start_thread(gen)
            return

        def got(err, rep, gen=gen):
            if gen != self._pf_gen or self.doc is None:
                return                                  # veraltet (Dokument inzwischen geändert)
            if err or rep is None:
                self._pf_start_thread(gen)              # Rückfall: wie bisher im Programm
            else:
                self._pf_show(rep)
        svc.call("preflight", {"path": path, "deep_layers": True}, got)

    def _pf_show(self, rep):
        self.pf_panel.set_report(rep)
        c = rep.counts()
        if c["error"] or c["warning"]:
            self.btn_pf.setText("⚠ " + tr("{0} Fehler · {1} Warnung(en)").format(c["error"], c["warning"]))
            self.btn_pf.setStyleSheet(f"color: {theme.ERROR if c['error'] else theme.ACCENT};")
        else:
            self.btn_pf.setText("✓ " + tr("Prüfung OK"))
            self.btn_pf.setStyleSheet(f"color: {theme.MUTED};")

    def _pf_start_thread(self, gen):
        """Rückfall ohne Analyse-Prozess: pikepdf-Teil im Hintergrund-Thread, pdfium-Teil im Hauptfenster."""
        from .preflightpanel import _Worker
        from .. import preflight
        try:
            # unverändert: die Datei selbst prüfen (kein Neuspeichern im Hauptfenster, Größe wie auf der Platte)
            data = self._doc_bytes() if self.modified else self._file_bytes()
        except Exception as e:
            self.pf_panel.set_error(str(e))
            return
        w = _Worker(lambda d: preflight.analyze(d, True, pdfium_parts=False), data)

        def done(rep, err, gen=gen, w=w):
            if gen != self._pf_gen:
                return                                  # outdated (document has changed in the meantime)
            if err:
                self.pf_panel.set_error(err)
                self.btn_pf.setText("⚠ " + tr("Prüfung fehlgeschlagen"))
                return
            try:
                preflight.finish(rep, data)          # pdfium-Teile im Hauptthread
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
        self.a_manip = A(tr("CMYK und Beschneiden in einem Schritt …"), lambda: self.manip_dialog("all"), "Ctrl+Shift+M", "cmyk")
        self.a_manip_cmyk = A(tr("CMYK-Umwandlung …"), lambda: self.manip_dialog("cmyk"), None, "cmyk")
        self.a_manip_crop = A(tr("Auf Format beschneiden …"), lambda: self.manip_dialog("crop"), None, "crop")
        self.a_separate = A(tr("Objekte trennen (Einzelseiten ohne Weißraum) …"), self.separate_dialog, None, "separate")
        self.a_cut = A(tr("CutContour erzeugen (Schneideplotter) …"), self.cut_dialog, None, "cut")
        self.a_vdp = A(tr("Variable Daten (Nummern, QR-/Barcodes, CSV) …"), self.vdp_dialog, "Ctrl+Shift+D", "vdp")
        self.a_data = A(tr("Daten erfassen (Tabelle für Visitenkarten, WLAN, Codes …) …"), self.data_dialog, None, "table")
        self.a_edit = A(tr("Text und Ebenen bearbeiten"), lambda: None, "Ctrl+T", "edit")
        self.a_edit.setCheckable(True)
        self.a_edit.toggled.connect(self._edit_mode)

        self.a_ins_before = A(tr("Seiten einfügen – vor Auswahl…"), lambda: self.insert_dialog("before"))
        self.a_ins_after = A(tr("Seiten einfügen – nach Auswahl…"), lambda: self.insert_dialog("after"), "Ctrl+I", "insert")
        self.a_ins_end = A(tr("Seiten anhängen (am Ende)…"), lambda: self.insert_dialog("end"), "Ctrl+Shift+I")
        self.a_blank_before = A(tr("Leerseite einfügen – vor Auswahl"), lambda: self.insert_blank("before"))
        self.a_blank_after = A(tr("Leerseite einfügen – nach Auswahl"), lambda: self.insert_blank("after"),
                               "Ctrl+Alt+I")
        self.a_export = A(tr("Auswahl als ein PDF exportieren…"), self.export_selection, "Ctrl+E", "export")
        self.a_export_each = A(tr("Auswahl als einzelne PDFs exportieren…"), self.export_each, "Ctrl+Shift+E")
        self.a_delete = A(tr("Seiten löschen"), self.delete_pages, QKeySequence.StandardKey.Delete, "delete")
        self.a_split = A(tr("Seiten teilen (halbieren, Raster) …"), self.split_dialog, None, "split")
        self.a_split_spreads = A(tr("Doppelseiten teilen (falsch exportierte Broschüre)"), self.split_spreads, None,
                                 "split")
        self.a_rot_l = A(tr("Seiten links drehen (dauerhaft)"), lambda: self.rotate_pages(-90), None, "rot_l")
        self.a_rot_r = A(tr("Seiten rechts drehen (dauerhaft)"), lambda: self.rotate_pages(90), None, "rot_r")
        self.a_up = A(tr("Seiten nach vorne verschieben"), lambda: self.move_pages(-1), "Alt+Up", "move_up")
        self.a_down = A(tr("Seiten nach hinten verschieben"), lambda: self.move_pages(1), "Alt+Down", "move_down")
        self.a_selall = A(tr("Alle Seiten auswählen"), lambda: self.thumbs.selectAll(), "Ctrl+Shift+A")

        mb = self.menuBar()
        m = mb.addMenu(tr("&Datei"))
        for a in (self.a_open, self.a_newwin, self.a_newtab, self.a_detach, None, self.a_save, self.a_saveas, None,
                  self.a_props, None, self.a_print, None, self.a_settings, None, self.a_close):
            m.addSeparator() if a is None else m.addAction(a)
        m = mb.addMenu(tr("&Seiten"))
        for a in (self.a_ins_before, self.a_ins_after, self.a_ins_end, self.a_blank_before, self.a_blank_after,
                  None, self.a_export,
                  self.a_export_each, None, self.a_rot_l, self.a_rot_r, self.a_up, self.a_down, None,
                  self.a_split, self.a_split_spreads, None,
                  self.a_delete, None, self.a_selall, None, self.a_copy, self.a_seltext):
            m.addSeparator() if a is None else m.addAction(a)
        self.page_menu = m
        m = mb.addMenu(tr("D&okument"))
        m.addAction(self.a_merge)
        m.addAction(self.a_repair)
        m.addAction(self.a_shrink)
        m.addSeparator()
        self.a_preflight = A(tr("Dokumentprüfung (Preflight) …"),
                             lambda: (self.pf_dock.show(), self.pf_dock.raise_(), self._pf_start(force=True)),
                             "Ctrl+Shift+P", "check")
        m.addAction(self.a_preflight)
        m = mb.addMenu(tr("Dokument-&Manipulation"))
        for a in (self.a_edit, None, self.a_manip_cmyk, self.a_manip_crop, None, self.a_manip, None, self.a_separate,
                  self.a_cut, None, self.a_vdp, self.a_data):
            m.addSeparator() if a is None else m.addAction(a)
        m = mb.addMenu(tr("&Farbe"))
        self.a_proof = A(tr("Softproof (Druckfarben anzeigen)"), lambda: None, "Ctrl+Y", "proof")
        self.a_proof.setCheckable(True)
        self.a_proof.toggled.connect(self._toggle_proof)
        self.a_colorcheck = A(tr("Farbprüfung …"), self.color_check, "Ctrl+Shift+F", "check")
        self.a_colorcheck.setToolTip(tr("Dokument gegen eine Druckbedingung prüfen – mit Empfehlungen"))
        self.a_press = A(tr("Für Druckerei ausgeben …"), lambda: self.press_dialog(), None, "export")
        self.a_press.setToolTip(tr("Umwandeln, Output Intent einbetten, prüfen, speichern – optional als Paket"))
        for a in (self.a_colorcheck, self.a_proof):
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
            if isinstance(btn, QToolButton):      # die drei Hauptaktionen mit Text
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
        # Lineale/Maßband/Endformat immer verfügbar – nicht nur im Arbeitsbereich „Anzeigen“
        tb.addAction(self.a_rulers)
        tb.addAction(self.a_measure)
        tb.addAction(self.a_boxes)
        tb.addAction(self.a_proof)
        tb.addSeparator()
        tb.addAction(A(tr("Verkleinern"), lambda: self.view.step_zoom(1 / 1.2), QKeySequence.StandardKey.ZoomOut, "zoom_out"))
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
        tb.addAction(A(tr("Vergrößern"), lambda: self.view.step_zoom(1.2), [QKeySequence.StandardKey.ZoomIn, "Ctrl+="], "zoom_in"))
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
        self.ctl.view_single = single           # applies to new windows of this session
        self.view.set_single(single)
        self.view.setFocus()

    def _update_actions(self):
        has = self.doc is not None
        for a in (self.a_save, self.a_saveas, self.a_print, self.a_ins_before, self.a_ins_after,
                  self.a_ins_end, self.a_blank_before, self.a_blank_after, self.a_export, self.a_export_each, self.a_delete, self.a_rot_l,
                  self.a_rot_r, self.a_up, self.a_down, self.a_selall, self.a_manip, self.a_manip_cmyk,
                  self.a_manip_crop, self.a_repair, self.a_separate, self.a_cut, self.a_edit, self.a_vdp,
                  self.a_split, self.a_split_spreads):
            a.setEnabled(has)
        # Speichern nur, wenn es etwas zu speichern gibt (sonst „nichts passiert“)
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
        paths, _ = QFileDialog.getOpenFileNames(self, tr("Öffnen"), os.path.dirname(self.path or ""), OPEN_FILTER)
        if paths:
            self.open_paths_here(paths)

    def open_paths_here(self, paths):
        """Erstes Dokument in dieses (leere) Fenster, den Rest in neue Fenster.
        Mehrere Bilder auf einmal werden zu einem Dokument."""
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
        """src: Bytes des Dokuments, falls schon vorhanden (spart dem Render-Prozess das Zwischenspeichern).
            changed_pages: Seiten, die bearbeitet wurden – alte Vorschau/Miniaturen bleiben als Platzhalter stehen,
            bis die neuen da sind (diese Seiten zuerst)."""
        if self.doc is not None and self.doc is not doc:
            self.doc.close()
        same_count = self.doc is not None and changed_pages is not None and self.thumbs.count() == len(doc)
        self.doc, self.path, self.display_name, self.modified = doc, path, display, modified
        if src is None and not modified and path and path.lower().endswith(".pdf") and os.path.isfile(path):
            src = path                                   # unverändert: Render-Prozess liest die Datei selbst
        self.view.set_document(doc, keep_page, src=src, changed_pages=changed_pages if same_count else None)
        n = len(doc)
        self.page_edit.set_count(n)
        if same_count:
            for i in range(self.thumbs.count()):        # alte Miniaturen bleiben stehen, bis die neuen da sind
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
            self._pf_timer.start()                       # document check in the background

    def open(self, path: str):
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
        if self.doc is None:
            return
        from .propsdialog import PropertiesDialog
        PropertiesDialog(self).exec()

    def merge_dialog(self):
        dlg = MergeDialog(self, [self.path] if self.path and not self.modified else None)
        if not dlg.exec() or not dlg.paths():
            return
        self.ctl.merge_into_window(dlg.paths(), self if self.doc is None else None)

    def _load_any(self, path):
        return load_any(self, self.ctl, path)

    # ================================================================ #
    # Speichern / Exportieren
    # ================================================================ #
    def _write(self, doc, path):
        """Save safely – even over the file that is just open."""
        tmp = path + ".pdfdruck-tmp"
        doc.save(tmp)
        return tmp

    def save(self):
        if self.doc is None:
            return False
        if not self.path:
            return self.save_as()
        return self._save_to(self.path)

    def save_as(self):
        if self.doc is None:
            return False
        start = self.path or os.path.join(getattr(self, "_suggest_dir", os.path.expanduser("~")),
                                          self.display_name or "Dokument.pdf")
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
            self.doc.close()                 # Datei freigeben, falls es dieselbe ist
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
        rows = sorted(self.thumbs.row(i) for i in self.thumbs.selectedItems())
        return rows or ([self.view.current] if self.doc is not None else [])

    def export_selection(self):
        pages = self.selected_pages()
        if not pages:
            return
        base = os.path.splitext(self.display_name or "Dokument")[0]
        rng = f"S{pages[0] + 1}" if len(pages) == 1 else f"S{pages[0] + 1}-{pages[-1] + 1}"
        start = os.path.join(os.path.dirname(self.path) if self.path else getattr(self, "_suggest_dir", ""),
                             f"{base}_{rng}.pdf")
        path, _ = QFileDialog.getSaveFileName(self, tr("{0} Seite(n) exportieren").format(len(pages)), start, tr("PDF-Dateien (*.pdf)"))
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
        QMessageBox.information(self, tr("Exportiert"), tr("{0} Seite(n) gespeichert als:\n{1}").format(len(pages), path))

    def export_each(self):
        pages = self.selected_pages()
        if not pages:
            return
        folder = QFileDialog.getExistingDirectory(
            self, tr("Zielordner für Einzelseiten"),
            os.path.dirname(self.path) if self.path else getattr(self, "_suggest_dir", ""))
        if not folder:
            return
        base = os.path.splitext(self.display_name or "Dokument")[0]
        digits = max(3, len(str(len(self.doc))))
        names = [f"{base}_S{p + 1:0{digits}d}.pdf" for p in pages]
        exist = [n for n in names if os.path.exists(os.path.join(folder, n))]
        if exist and QMessageBox.question(
                self, tr("Überschreiben?"), tr("{0} Datei(en) existieren bereits (z. B. {1}). Überschreiben?").format(len(exist), exist[0])
        ) != QMessageBox.StandardButton.Yes:
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
            QMessageBox.critical(self, tr("Exportieren"), tr("{0} gespeichert, {1} Fehler:\n").format(done, len(errors)) + "\n".join(errors[:8]))
        else:
            QMessageBox.information(self, tr("Exportiert"),
                                    tr("{0} Einzelseite(n) gespeichert in:\n{1}\n\n{2}").format(done, folder, names[0]) + (f" … {names[-1]}" if len(names) > 1 else ""))

    # ================================================================ #
    # Seitenoperationen
    # ================================================================ #
    def _changed_doc(self, keep_page=None, select=None):
        self.modified = True
        self._set_doc(self.doc, self.path, self.display_name, True,
                      self.view.current if keep_page is None else keep_page)
        if select:
            self.thumbs.clearSelection()
            for i in select:
                if 0 <= i < self.thumbs.count():
                    self.thumbs.item(i).setSelected(True)

    def insert_dialog(self, where: str):
        paths, _ = QFileDialog.getOpenFileNames(self, tr("Seiten einfügen aus …"), os.path.dirname(self.path or ""),
                                                OPEN_FILTER)
        if not paths:
            return
        sel = self.selected_pages()
        pos = {"before": sel[0] if sel else 0, "after": (sel[-1] + 1) if sel else len(self.doc),
               "end": len(self.doc)}[where]
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
        """Leerseite(n) vor/nach der Auswahl – im Format der Nachbarseite (Rahmen und Drehung inklusive)."""
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
        except Exception as e:                   # noqa: BLE001
            QMessageBox.critical(self, tr("Leerseite einfügen"), str(e))
            return
        self._changed_doc(pos, list(range(pos, pos + k)))
        self.statusBar().showMessage(tr("{0} Leerseite(n) eingefügt.").format(k), 6000)

    def delete_pages(self):
        pages = self.selected_pages()
        if not pages:
            return
        if len(pages) >= len(self.doc):
            QMessageBox.warning(self, tr("Löschen"), tr("Es muss mindestens eine Seite übrig bleiben."))
            return
        if QMessageBox.question(self, tr("Seiten löschen"),
                                tr("{0} Seite(n) aus dem Dokument entfernen?\n(Die Datei ändert sich erst beim Speichern.)").format(len(pages))) != QMessageBox.StandardButton.Yes:
            return
        for i in reversed(pages):
            self.doc.del_page(i)
        self._changed_doc(min(pages[0], len(self.doc) - 1))

    def rotate_pages(self, delta: int):
        pages = self.selected_pages()
        for i in pages:
            pg = self.doc[i]
            pg.set_rotation((pg.get_rotation() + delta) % 360)
            pg.close()
        self._changed_doc(select=pages)

    def move_pages(self, d: int):
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
        """Seitenleiste: gewählte Seiten an die Einfügestelle ziehen (ins = vor dieser Seite, len = ans Ende)."""
        if self.doc is None or not pages:
            return
        pages = sorted(set(p for p in pages if 0 <= p < len(self.doc)))
        dest = ins - sum(1 for p in pages if p < ins)     # Index der ersten Seite nach dem Verschieben
        dest = max(0, min(dest, len(self.doc) - len(pages)))
        if pages == list(range(dest, dest + len(pages))):
            return                                         # liegt schon dort
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
        for a in (self.a_ins_before, self.a_ins_after, self.a_blank_before, self.a_blank_after, None,
                  self.a_export, self.a_export_each, None, self.a_rot_l, self.a_rot_r, self.a_up, self.a_down, None):
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
    # Miniaturen / Anzeige
    # ================================================================ #
    def rotate_view(self, delta: int):
        """Rotate the view – the thumbnails in the sidebar rotate along (the document stays unchanged)."""
        self.view.rotate(delta)
        if self.doc is not None:
            self._rebuild_thumbs()

    def _view_rot(self) -> int:
        r = getattr(self.view, "rotation", 0)
        return r % 360 if isinstance(r, int) else 0

    # ---------------- Seitenleiste: Breite, Anordnung, Vorschaugröße ---------------- #
    @staticmethod
    def _dock_scroll(w):
        """Panel in einen Scrollbereich: die Reiter links teilen sich eine Breite – ohne das
                erzwingt das breiteste Panel (Prüfung/Bearbeiten) die Mindestbreite auch für „Seiten“."""
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.Shape.NoFrame)
        sc.setWidget(w)
        return sc

    def _dock_vis(self, d, vis):
        """Jeder Reiter links merkt sich seine eigene Breite (Seiten schmal, Prüfung breiter …)."""
        shown = self.__dict__.setdefault("_dock_shown", set())
        if not vis:
            if d in shown:                     # nur echte, sichtbare Breiten merken
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
        """Raster: Kachelgröße ändern. Eine Spalte: die Seitenleiste selbst breiter/schmäler."""
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
        # sichtbare zuerst, dann der Rest
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
        """(Bildbreite in der Liste, Maßstab in Gerätepixeln) für Miniatur i."""
        dlg = self.thumbs.itemDelegate()
        it = self.thumbs.item(i)
        iw = dlg.image_rect(QRect(0, 0, self.thumbs.tile_width(), 10000), it.data(THUMB_ASPECT)).width()
        w, h = self.doc.get_page_size(i)
        rot = self._view_rot()
        return iw, iw / (h if rot % 180 else w) * self.devicePixelRatioF()

    def _thumb_from_master(self, i):
        """Seitenbild der Vorschau fertig -> Miniatur daraus skalieren (kein zweites Rendern)."""
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
            ti = self.view.trim_info(i)                    # ohne die Seite im Programm zu laden
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
        if self.doc is None:
            return
        from .objectsdialog import SeparateDialog
        dlg = SeparateDialog(self, self.doc, self.view.current)
        if dlg.exec() and getattr(dlg, "job", None):
            self.start_job(*dlg.job, suffix=tr("_einzeln"), title=tr("Objekte trennen"),
                           notes=lambda info: [tr("{0} Objekt(e) als Einzelseiten.").format(info.get("objects", 0))])

    def split_selected(self, mode: str):
        """Right-click → Split: immediately halve the selected pages (no dialog, no comparison page)."""
        if self.doc is None:
            return
        from .. import core, split
        pages = self.selected_pages()
        if not pages:
            return
        self.start_job("split", core.settings_to_dict(split.SplitSettings(mode=mode)), pages,
                       suffix=tr("_geteilt"), title=tr("Seiten teilen"))

    def split_dialog(self, selection: bool = False):
        if self.doc is None:
            return
        from .splitdialog import SplitDialog
        dlg = SplitDialog(self, self.doc, self.view.current, self.selected_pages(),
                          which="selected" if selection else "all")
        if dlg.exec() and getattr(dlg, "job", None):
            self.start_job(*dlg.job, suffix=tr("_geteilt"), title=tr("Seiten teilen"))

    def split_spreads(self):
        """One click: halve all double pages vertically (e.g. a booklet exported as press sheets)."""
        if self.doc is None:
            return
        from .. import core, split
        sizes = [self.doc.get_page_size(i) for i in range(len(self.doc))]
        if not split.spreads(sizes, 2, 1):
            QMessageBox.information(self, tr("Doppelseiten teilen"), tr(
                "Keine Doppelseiten gefunden – keine Seite ist doppelt so breit wie die übrigen. Für andere Fälle: "
                "Seiten → Seiten teilen …"))
            return
        self.start_job("split", core.settings_to_dict(split.SplitSettings(only_spreads=True)), None,
                       suffix=tr("_geteilt"), title=tr("Doppelseiten teilen"))

    def cut_dialog(self):
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
            self.start_job(*dlg.job, suffix=tr("_CutContour"), title=tr("CutContour"),
                           notes=lambda info: [tr("{0} Schnittkontur(en) erzeugt.").format(info.get("cuts", 0))])

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
            self.start_job(*dlg.job, suffix=tr("_Daten"), title=tr("Variable Daten"),
                           notes=lambda info: [tr("{0} Datensätze, {1} Seiten erzeugt.").format(
                               info.get("records", 0), info.get("pages", 0))])

    def data_dialog(self):
        """Create a data table; "Use for variable data" opens Variable Data with this table."""
        from .datadialog import DataDialog
        dlg = DataDialog(self)
        if not (dlg.exec() and dlg.use and dlg.path):
            return
        if self.doc is None:
            QMessageBox.information(self, tr("Daten erfassen"), tr(
                "Die Tabelle ist gespeichert:\n{0}\n\nJetzt die Vorlage (PDF) öffnen und unter Variable Daten → "
                "„CSV öffnen …“ diese Datei wählen.").format(dlg.path))
            return
        self.vdp_dialog((dlg.path, dlg.kind))

    # ---------------- Background jobs (separate process) ---------------- #
    def start_job(self, kind, settings, pages=None, suffix="", title="", notes=None, src_data=None):
        """Dokument in den Zwischenspeicher, Kommandozeile als eigenen Prozess starten, Fortschritt unten anzeigen."""
        from .. import jobproc, l10n
        from .jobs import JobReader, JobWidget
        base = os.path.splitext(self.display_name or "Dokument")[0]
        src = self.ctl.cache_file(base + "_eingabe.pdf")
        dst = self.ctl.cache_file(base + suffix + ".pdf")
        try:
            if src_data is not None:                             # z. B. die Datei wie auf der Platte
                with open(src, "wb") as f:
                    f.write(src_data)
            else:
                self.doc.save(src)                               # current state (including unsaved changes)
            open(dst, "wb").close()                              # reserve names (several jobs at once)
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
        crashlog.record(f"Auftrag {entry['job'].kind} fehlgeschlagen (Code {res.get('returncode')}): "
                        f"{res.get('message')}", res.get("details") or "")
        box = QMessageBox(QMessageBox.Icon.Critical, tr("Fehler"), res.get("message") or tr("Unbekannter Fehler"),
                          parent=self)
        if res.get("details"):
            box.setDetailedText(res["details"])
        box.exec()

    def _stop_jobs(self):
        """Window is closing: cancel running jobs."""
        cp = self.__dict__.get("color_panel")
        if cp is not None:                              # Farbprüfung im Hintergrund: abbrechen und warten
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
        """Sprachversion einer Anleitung (z. B. …-anleitung.en.pdf), sonst die deutsche."""
        from .. import l10n
        lang = l10n.current()
        for code in (lang, "en"):                # UI-Sprache, dann Englisch statt Deutsch
            if code and code != "de":
                root, ext = os.path.splitext(path)
                p = f"{root}.{code}{ext}"
                if os.path.isfile(p):
                    return p
        return path

    @staticmethod
    def cli_howto_path() -> str:
        """Anleitung zur Kommandozeile im Programmpaket (Linux-Installation, AppImage, Windows-Setup)."""
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
        QMessageBox.information(self, tr("Beispiele"), tr(
            "Die Beispiele liegen in:\n{0}\n\nDie Vorlage ist geöffnet. Unter Variable Daten (Strg+Umschalt+D) "
            "in der Preset-Leiste „Beispiel 1“ bis „Beispiel 4“ wählen – die CSV ist schon eingetragen.\n\n"
            "Im Ordner „ergebnis“ liegen die fertigen PDFs zum Vergleich, die Anleitung liegt daneben.").format(d))

    def _win_print_test(self):
        """Print one test page per method – shows what the driver can really do (blank sheets?)."""
        from PySide6.QtWidgets import QInputDialog
        from .. import printers, printers_win
        try:
            names = [p.name for p in printers.list_printers()]
        except Exception as e:                          # noqa: BLE001
            QMessageBox.critical(self, tr("Windows-Druck testen"), str(e))
            return
        if not names:
            QMessageBox.information(self, tr("Windows-Druck testen"), tr("Kein Drucker gefunden."))
            return
        name, ok = QInputDialog.getItem(self, tr("Windows-Druck testen"),
                                        tr("Je Verfahren wird eine A4-Testseite gedruckt (4 Blätter).\nDrucker:"),
                                        names, 0, False)
        if not ok:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            res = printers_win.test_print(name)
        finally:
            QApplication.restoreOverrideCursor()
        lines = "\n".join(f"• {label}: {r}" for label, r in res)
        QMessageBox.information(self, tr("Windows-Druck testen"),
                                tr("Gesendet an {0}:").format(name) + "\n" + lines + "\n\n"
                                + tr("Auf jedem Blatt steht das Verfahren. Wählen Sie unter Datei → Einstellungen → Drucken "
                                     "unter Windows das Verfahren, dessen Blatt richtig ankommt."))

    def copy_text(self):
        t = self.view.selected_text()
        if t:
            QApplication.clipboard().setText(t)
            self.statusBar().showMessage(tr("{0} Zeichen kopiert.").format(len(t)), 3000)

    def settings_dialog(self):
        from .settingsdialog import SettingsDialog
        SettingsDialog(self).exec()

    def shrink_dialog(self):
        """Dateigröße aufschlüsseln und verkleinern – auch für Dateien, die nicht als zu groß gelten."""
        if self.doc is None:
            return
        from .shrinkdialog import ShrinkDialog
        data = self._file_bytes()
        dlg = ShrinkDialog(self, None, data)
        if dlg.exec():
            self.start_job("shrink", dlg.options(), suffix=tr("_klein"), title=tr("Datei verkleinern"), src_data=data)

    def repair_dialog(self):
        import tempfile
        from .. import repair
        from .repairdialog import RepairDialog
        names, out_dir = {}, None
        if self.doc is None:
            files, _ = QFileDialog.getOpenFileNames(self, tr("PDFs reparieren / optimieren"), "", tr("PDF-Dateien (*.pdf *.PDF)"))
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
            out_dir = os.path.dirname(self.path) if self.path else getattr(self, "_suggest_dir", os.path.expanduser("~"))
        RepairDialog(self, files, names, out_dir, open_cb=lambda p: self.ctl.open_paths([p], tab_of=self)).exec()

    def print_dialog(self):
        if self.doc is None:
            return
        from .printdialog import PrintDialog
        PrintDialog(self, self.doc, self.display_name, self.view.current, self.session,
                    src_path=getattr(self.view, "_src_path", None), pinfo=getattr(self.view, "_pinfo", None)).exec()

    def admin_dialog(self):
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
                self, tr("Ungespeicherte Änderungen"), tr("Änderungen an „{0}“ speichern?").format(self.display_name),
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel)
            if r == QMessageBox.StandardButton.Cancel or (r == QMessageBox.StandardButton.Save and not self.save()):
                e.ignore()
                return
        # Druckeinstellungen der Sitzung bleiben bis zum letzten Fenster – dann verfallen sie.
        try:
            self.view._timer.stop()
            self.view.release_render()     # Dokument im Render-Prozess schließen
            self._thumb_src.release()
            self.view.doc = None           # Ansicht darf das gleich geschlossene Dokument nicht mehr anfassen
        except Exception:
            pass
        if self.doc is not None:
            self.doc.close()
            self.doc = None
        super().closeEvent(e)
        host = getattr(self, "_host", None)
        if host is not None:
            host.tab_closed()
