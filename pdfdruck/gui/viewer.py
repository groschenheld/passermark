# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Acrobat-ähnliches Hauptfenster: Miniaturen links, Endlos-Ansicht, Toolbar, Seitenoperationen."""
from __future__ import annotations

from ..l10n import tr

import ctypes
import os

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_r
from PySide6.QtCore import QPointF, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QDialog, QDialogButtonBox, QDockWidget,
                               QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPushButton,
                               QScrollArea, QSpinBox, QStyle, QStyledItemDelegate, QToolButton,
                               QVBoxLayout, QWidget)

from .. import images
from . import theme
from .common import render_pixmap
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


def load_any(parent, ctl, path, workdir=None, notes=None):
    """PDF (mit Passwortabfrage), Bild oder Office-Datei -> pypdfium2-Dokument (None = abgebrochen)."""
    import tempfile
    if images.is_image(path):
        return images.images_to_document([path], ctl.image_dpi)
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
        # in den Speicher laden, damit der Arbeitsordner gelöscht werden darf
        with open(pdf, "rb") as f:
            return pdfium.PdfDocument(f.read())
    return load_pdf(parent, path)

PAPER_NAMES = {  # mm, Hochformat
    "A0": (841, 1189), "A1": (594, 841), "A2": (420, 594), "A3": (297, 420), "A4": (210, 297),
    "A5": (148, 210), "A6": (105, 148), "B4": (250, 353), "B5": (176, 250), "C4": (229, 324),
    "C5": (162, 229), "DL": (110, 220), "Letter": (215.9, 279.4), "Legal": (215.9, 355.6),
    "Tabloid": (279.4, 431.8), "SRA3": (320, 450),
}


def page_size_text(w_pt: float, h_pt: float) -> str:
    w, h = w_pt * 25.4 / 72, h_pt * 25.4 / 72
    lo, hi = sorted((w, h))
    name = next((n for n, (a, b) in PAPER_NAMES.items() if abs(lo - a) <= 1.5 and abs(hi - b) <= 1.5), None)
    orient = tr("quer") if w > h + 0.5 else tr("hoch")
    txt = tr("{0:.0f} × {1:.0f} mm").format(w, h)
    return f"{txt}  ({name} {orient})" if name else txt


def load_pdf(parent, path: str):
    """PDF öffnen, bei Bedarf Passwort abfragen. None bei Abbruch/Fehler."""
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


class PageWidget(QWidget):
    def __init__(self, index: int, view=None):
        super().__init__()
        self.index = index
        self.pixmap = None
        self.key = None
        self.view = view
        self.setMouseTracking(True)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect().adjusted(3, 3, 3, 3), QColor(0, 0, 0, 60))   # Schatten
        if self.pixmap is not None:
            p.drawPixmap(0, 0, self.pixmap)
        else:
            p.fillRect(self.rect(), Qt.GlobalColor.white)
        if self.view is not None:
            self.view.paint_overlay(self, p)

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
    """Lineal in mm an der Kante der Seitenansicht; Nullpunkt = linke obere Ecke der aktuellen Seite.
    Bleibt beim Scrollen stehen, die Skala läuft mit (Zoom, Seite, Drehung)."""
    SIZE = 22

    def __init__(self, view, horizontal: bool):
        super().__init__()
        self.view, self.horizontal = view, horizontal
        self.cursor_px = None            # Mausposition (Bildschirm, global) für den Markierungsstrich
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
    """Seitenansicht.

    single=True  (Standard): immer genau eine Seite, zentriert. Innerhalb der Seite wird
                 gescrollt; am Seitenende springt das nächste Mausrad-/Bild-runter zur
                 nächsten Seite (Anfang), am Seitenanfang zur vorherigen (Ende).
    single=False: fortlaufend wie bisher.
    """
    pageChanged = Signal(int)
    zoomChanged = Signal(float)
    viewMoved = Signal()                 # Scrollen/Zoom/Seite -> Lineale neu zeichnen

    JUMP_THRESHOLD = 120       # eine Mausrad-Raste; Touchpad-Bruchteile werden gesammelt
    JUMP_COOLDOWN = 0.30       # s – verhindert, dass Schwung-Scrollen mehrere Seiten überspringt

    def __init__(self, single: bool = True):
        super().__init__()
        self.setWidgetResizable(False)
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.setStyleSheet(f"QScrollArea {{ background: {theme.VIEW}; }} #pages {{ background: {theme.VIEW}; }}")
        self.doc = None
        self.sizes = []
        self.base = "page"        # width | page | actual – Bezug je Seite
        self.factor = 1.0         # Zoom relativ zum Bezug (Strg+Mausrad, +/-)
        self.zoom = 1.0           # tatsächlicher Maßstab der aktuellen Seite (nur Anzeige)
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
        self.edit_click = None    # Rückruf (Seite, x, y in Seitenkoordinaten, Umschalt)
        self.meas = None          # Messung: {"page", "a": (x, y) pt, "b": (x, y) pt | None, "done": bool}
        self.on_measure = None    # Rückruf (Text für die Statusleiste)
        self.on_cursor = None     # Rückruf (Seiten-Widget, Mausposition) für die Lineale
        self.editor = None        # Bearbeiten-Seitenleiste: press/drag/release/cursor (Seitenkoordinaten)
        self._edrag = False
        self.overlay = {}         # Seite -> [(x0, y0, x1, y1, Farbe)] in Seitenkoordinaten
        self.container = QWidget()
        self.container.setObjectName("pages")
        self.setWidget(self.container)
        self._timer = QTimer(self, singleShot=True, interval=30, timeout=self._render_visible)
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.verticalScrollBar().valueChanged.connect(lambda _v: self.viewMoved.emit())
        self.horizontalScrollBar().valueChanged.connect(lambda _v: self.viewMoved.emit())

    # --------------------------------------------------------------- #
    def set_document(self, doc, keep_page: int | None = None):
        for w in self.pages:          # Seiten des vorherigen Dokuments entsorgen
            w.deleteLater()
        self._close_textpages()
        self.sel, self._drag = None, None
        self.meas = None
        self.doc = doc
        self.sizes = [doc.get_page_size(i) for i in range(len(doc))]
        try:
            from ..layout import page_boxes
            self.boxes = page_boxes(doc)                 # Endformat/Anschnitt (TrimBox/BleedBox)
        except Exception:
            self.boxes = []
        self.pages = [PageWidget(i, self) for i in range(len(doc))]
        for w in self.pages:
            w.setParent(self.container)
        self.current = min(keep_page or 0, max(0, len(self.pages) - 1))
        self.relayout()
        self.goto(self.current, force=True)

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
        """Für die Zoom-Anzeige: width/page nur ohne Zusatzfaktor, sonst fixed."""
        return self.base if self.base != "actual" and abs(self.factor - 1) < 1e-3 else "fixed"

    def page_zoom(self, i: int) -> float:
        """Maßstab (1.0 = tatsächliche Größe) für Seite i. Bei width/page wird JEDE Seite
        für sich eingepasst -> alle Seiten erscheinen gleich groß, egal wie groß sie wirklich sind."""
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
                    w.pixmap, w.key = None, None
            w = self.pages[self.current]
            s = self.page_zoom(self.current) * dpi
            pw, ph = self._rot_size(self.current)
            ww, hh = int(pw * s), int(ph * s)
            cw, ch = max(ww + 2 * PAGE_GAP, vw), max(hh + 2 * PAGE_GAP, vh)
            w.setGeometry((cw - ww) // 2, max(PAGE_GAP, (ch - hh) // 2), ww, hh)
            if w.key != (s, self.rotation):
                w.pixmap = None
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
                if w.key != (s, self.rotation):
                    w.pixmap = None
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

    def _render_visible(self):
        if self.doc is None or getattr(self.doc, "raw", None) is None:
            return                         # Dokument schon geschlossen (Fenster/Reiter zu, Zeitgeber kam danach)
        top = self.verticalScrollBar().value() - 200
        bottom = top + self.viewport().height() + 400
        dpr = self.devicePixelRatioF()
        for w in self.pages:
            s = self.page_zoom(w.index) * self._dpi_scale()
            visible = w.isVisibleTo(self.container) and w.y() + w.height() >= top and w.y() <= bottom
            if visible and w.key != (s, self.rotation):
                page = self.doc[w.index]
                w.pixmap = render_pixmap(page, s, self.rotation, dpr)
                page.close()
                w.key = (s, self.rotation)
                w.update()
            elif not visible and w.pixmap is not None:
                w.pixmap, w.key = None, None   # Speicher freigeben

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

    def next_page(self):
        self.goto(self.current + 1)

    def prev_page(self, at_end: bool = False):
        self.goto(self.current - 1, at_end=at_end)

    def set_zoom(self, mode: str, value: float | None = None):
        """mode: width | page  (Faktor 1)  oder  fixed + value (Maßstab, 1.0 = tatsächliche Größe)."""
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
        self.factor = new_factor            # Bezug bleibt -> Seiten bleiben untereinander gleich groß
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

    def to_page(self, w, pos):
        """Widget-Pixel -> Seitenkoordinaten (pt, PDF-System) – pdfium rechnet Drehung/CropBox ein."""
        import ctypes
        import pypdfium2.raw as r
        pg, _tp = self._textpage(w.index)
        px, py = ctypes.c_double(), ctypes.c_double()
        r.FPDF_DeviceToPage(pg.raw, 0, 0, w.width(), w.height(), (self.rotation // 90) % 4,
                            int(pos.x()), int(pos.y()), ctypes.byref(px), ctypes.byref(py))
        return px.value, py.value

    def to_widget(self, w, x, y):
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

    def _measure_point(self, w, pos, shift):
        """Mausposition -> Seitenpunkt; mit Umschalt waagrecht/senkrecht/45° zum Startpunkt eingerastet."""
        from .. import measure as ms
        if shift and self.meas and self.meas["a"] is not None and not self.meas["done"]:
            sx, sy = self.to_widget(w, *self.meas["a"])
            vx, vy = ms.snap(pos.x() - sx, pos.y() - sy, True)
            # eingerasteten Bildschirmvektor exakt in Seitenmaße umrechnen (nicht über ganze Pixel)
            a, b, c, d = self.page_matrix(w)
            det = a * d - b * c
            if abs(det) > 1e-12:
                px = (d * vx - c * vy) / det
                py = (-b * vx + a * vy) / det
                ax, ay = self.meas["a"]
                return ax + px, ay + py
        return self.to_page(w, pos)

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
            a = self.to_page(w, e.position())
            self.meas = {"page": w.index, "a": a, "b": None, "done": False}       # 1. Klick: Anfang
        else:
            m["b"] = self._measure_point(w, e.position(), shift)                    # 2. Klick: Ende
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
            m["b"] = self._measure_point(w, e.position(), shift)                   # Gummiband
            self._measure_report(w)
            w.update()
        elif self.on_measure is not None and (m is None or m["done"]):
            geo = self.ruler_geometry()
            if geo is not None and w.index == self.current:
                ppm = geo[1]
                if m is None:
                    self.on_measure(ms.describe_pos(e.position().x() / ppm, e.position().y() / ppm, l10n.current()))

    def mouse_press(self, w, e):
        self.setFocus()
        if self.imode == "measure":
            self._measure_press(w, e)
            return
        if self.imode == "edit":
            x, y = self.to_page(w, e.position())
            if self.editor is not None:
                self._edrag = True
                self.editor.press(w.index, x, y, self._tol_pt(w))
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
            w.setCursor(Qt.CursorShape.IBeamCursor if self._char_at(w, e.position()) >= 0 else Qt.CursorShape.ArrowCursor)
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
            bx = self.boxes[w.index] if getattr(self, "show_boxes", True) and w.index < len(self.boxes) else None
            if bx and bx[0] is not None:
                # Endformat rot durchgezogen, Anschnittbereich rot getönt, BleedBox rot gestrichelt (nicht gedruckt)
                trim, bleed = bx
                pg_, _tp = self._textpage(w.index)
                crop = pg_.get_cropbox()
                red = QColor("#e0301e")
                outer = self._rect_widget(w, crop[0], crop[1], crop[2], crop[3])
                inner = self._rect_widget(w, trim[0], trim[1], trim[2], trim[3])
                from PySide6.QtGui import QPainterPath
                path = QPainterPath()
                path.addRect(outer)
                path.addRect(inner)
                tint = QColor(red)
                tint.setAlpha(45)
                p.fillPath(path, tint)                   # Ring zwischen Seitenrand und Endformat
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(red, 1.5))
                p.drawRect(inner)
                if bleed is not None:
                    pen = QPen(red, 1.2)
                    pen.setStyle(Qt.PenStyle.DashLine)
                    p.setPen(pen)
                    p.drawRect(self._rect_widget(w, bleed[0], bleed[1], bleed[2], bleed[3]))
            for item in self.overlay.get(w.index, []):
                x0, y0, x1, y1, c = item[:5]
                style = item[5] if len(item) > 5 else ""
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
    resized = Signal()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.resized.emit()


class ThumbDelegate(QStyledItemDelegate):
    """Alle Miniaturen gleich groß: feste Kachel, Bild darin eingepasst.
    Rest der Kachel grau, ausgewählt gelb hinterlegt mit gelbem Rahmen."""
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
        w = max(80, self.view.viewport().width() - 2)
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


class MergeDialog(QDialog):
    """Mehrere PDFs/Bilder in gewünschter Reihenfolge zu einem Dokument zusammenführen."""

    def __init__(self, parent, start: list[str] | None = None):
        super().__init__(parent)
        self.setWindowTitle(tr("Dokumente zusammenführen"))
        self.resize(560, 420)
        v = QVBoxLayout(self)
        v.addWidget(QLabel(tr("Reihenfolge = Reihenfolge im neuen Dokument (Bilder in tatsächlicher Größe):")))
        h = QHBoxLayout()
        self.lst = QListWidget()
        self.lst.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.lst.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        h.addWidget(self.lst, 1)
        b = QVBoxLayout()
        for text, fn in [(tr("Hinzufügen…"), self._add), (tr("Entfernen"), self._remove),
                         ("▲ Nach oben", lambda: self._move(-1)), ("▼ Nach unten", lambda: self._move(1))]:
            btn = QPushButton(text)
            btn.clicked.connect(fn)
            b.addWidget(btn)
        b.addStretch()
        h.addLayout(b)
        v.addLayout(h, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Zusammenführen"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        for p in start or []:
            self._append(p)

    def _append(self, p):
        it = QListWidgetItem(os.path.basename(p))
        it.setToolTip(p)
        it.setData(Qt.ItemDataRole.UserRole, p)
        self.lst.addItem(it)

    def _add(self):
        paths, _ = QFileDialog.getOpenFileNames(self, tr("Dateien hinzufügen"), "", OPEN_FILTER)
        for p in paths:
            self._append(p)

    def _remove(self):
        for it in self.lst.selectedItems():
            self.lst.takeItem(self.lst.row(it))

    def _move(self, d):
        rows = sorted(self.lst.row(i) for i in self.lst.selectedItems())
        if not rows or (d < 0 and rows[0] == 0) or (d > 0 and rows[-1] == self.lst.count() - 1):
            return
        for r in (rows if d < 0 else reversed(rows)):
            it = self.lst.takeItem(r)
            self.lst.insertItem(r + d, it)
            it.setSelected(True)

    def paths(self):
        return [self.lst.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.lst.count())]


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
        self._jobs = []                      # laufende Aufträge (eigene Prozesse)
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
        self.view.zoomChanged.connect(self._zoom_changed)

        # Miniaturen (Mehrfachauswahl für Seitenoperationen)
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
        dock = QDockWidget(tr("Seiten"), self)
        dock.setWidget(self.thumbs)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable
                         | QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self.resizeDocks([dock], [165], Qt.Orientation.Horizontal)
        self._thumb_queue = []
        self._thumb_timer = QTimer(self, interval=0, timeout=self._render_thumbs)

        self._build_actions(dock)
        self.lbl_size = QLabel()
        self.lbl_size.setContentsMargins(8, 0, 8, 0)
        self.lbl_size.setFont(theme.mono_font(9.5))
        self.statusBar().addPermanentWidget(self.lbl_size)
        self._build_preflight(dock)
        self._build_edit(dock)
        self._build_workspaces(dock)
        self.lbl_measure = QLabel()
        self.lbl_measure.setContentsMargins(8, 0, 8, 0)
        self.lbl_measure.setFont(theme.mono_font(9.5))
        self.lbl_measure.setToolTip(tr("Messung: Länge, waagrechter und senkrechter Abstand, Winkel"))
        self.statusBar().addPermanentWidget(self.lbl_measure)     # ganz rechts unten, stört die Arbeit nicht
        self.view.on_measure = self.lbl_measure.setText
        self._update_title()

    # ---------------- Arbeitsbereiche ---------------- #
    WORKSPACES = ("view", "prep", "edit", "vdp", "auto")

    def _build_workspaces(self, pages_dock):
        """Zweite Leiste: Arbeitsbereich wählen; rechts daneben die Werkzeuge dieses Bereichs."""
        from PySide6.QtGui import QActionGroup
        self._pages_dock = pages_dock
        self.a_presets = self._act(tr("Preset-Ordner öffnen"), self._open_presets_dir, None, "folder_gear")
        self.a_cli = self._act(tr("Kommandozeile – Anleitung (PDF)"), self._open_cli_howto, None, "terminal")
        tools = {"view": [(self.a_rulers, tr("Lineale")), (self.a_measure, tr("Messen")),
                          (self.a_boxes, tr("Endformat")),
                          (self.a_copy, tr("Text kopieren"))],
                 "prep": [(self.a_preflight, tr("Prüfen")), (self.a_boxes, tr("Endformat")), (self.a_manip_cmyk, tr("CMYK")),
                          (self.a_manip_crop, tr("Beschneiden")), (self.a_cut, tr("CutContour")),
                          (self.a_separate, tr("Objekte trennen")), (self.a_repair, tr("Reparieren"))],
                 "edit": [(self.a_edit, tr("Text/Ebenen")), (self.a_ins_after, tr("Einfügen")),
                          (self.a_delete, tr("Löschen")), (self.a_rot_l, tr("Links drehen")),
                          (self.a_rot_r, tr("Rechts drehen")), (self.a_up, tr("Nach vorne")),
                          (self.a_down, tr("Nach hinten")), (self.a_merge, tr("Zusammenführen")),
                          (self.a_export, tr("Exportieren"))],
                 "vdp": [(self.a_vdp, tr("Variable Daten"))],
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
                a.setIconText(text)                    # Kurztext für Leisten; Menüs zeigen weiter den vollen Text
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
            self.a_edit.setChecked(False)                  # Bearbeiten-Modus gehört zum Bereich Bearbeiten
        if key == "prep":
            self.pf_dock.show()
            self.pf_dock.raise_()
        elif key == "edit":
            self._pages_dock.show()
            self._pages_dock.raise_()
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
            def closeEvent(dock_self, e):          # Schließen-Knopf beendet den Bearbeiten-Modus
                self.a_edit.setChecked(False)
                e.accept()
        self.edit_dock = _Dock(tr("Bearbeiten"), self)
        self.edit_dock.setWidget(self.edit_panel)
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
                self.a_edit.setChecked(False)              # Bearbeiten und Messen schließen sich aus
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

    # ---------------- Preflight (Dokumentprüfung) ---------------- #
    def _build_preflight(self, pages_dock):
        from .preflightpanel import PreflightPanel
        self.pf_panel = PreflightPanel(self)
        self.pf_panel.data_fn = self._doc_bytes
        self.pf_panel.result_ready.connect(self._pf_result)
        self.pf_panel.goto_page.connect(lambda p: self.view.goto(p - 1))
        self.pf_panel.recheck.connect(lambda: self._pf_start(force=True))
        self.pf_dock = QDockWidget(tr("Prüfung"), self)
        self.pf_dock.setWidget(self.pf_panel)
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

    def _pf_start(self, force=False):
        from .. import l10n
        if self.doc is None:
            return
        if not force and not l10n.load_settings().get("preflight_on_open", True):
            return
        from .preflightpanel import _Worker
        from .. import preflight
        self._pf_gen += 1
        gen = self._pf_gen
        self.pf_panel.set_busy()
        self.btn_pf.setText("… " + tr("Prüfe"))
        self.btn_pf.show()
        try:
            data = self._doc_bytes()
        except Exception as e:
            self.pf_panel.set_error(str(e))
            return
        # Hintergrund: nur pikepdf-Teile (pdfium ist nicht thread-sicher – sonst gelegentliche Abstürze)
        w = _Worker(lambda d: preflight.analyze(d, True, pdfium_parts=False), data)

        def done(rep, err, gen=gen, w=w):
            if gen != self._pf_gen:
                return                                  # veraltet (Dokument inzwischen geändert)
            if err:
                self.pf_panel.set_error(err)
                self.btn_pf.setText("⚠ " + tr("Prüfung fehlgeschlagen"))
                return
            try:
                preflight.finish(rep, data)          # pdfium-Teile im Hauptthread
            except Exception:
                pass
            self.pf_panel.set_report(rep)
            c = rep.counts()
            if c["error"] or c["warning"]:
                self.btn_pf.setText("⚠ " + tr("{0} Fehler · {1} Warnung(en)").format(c["error"], c["warning"]))
                self.btn_pf.setStyleSheet(f"color: {theme.ERROR if c['error'] else theme.ACCENT};")
            else:
                self.btn_pf.setText("✓ " + tr("Prüfung OK"))
                self.btn_pf.setStyleSheet(f"color: {theme.MUTED};")
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
    # Aktionen / Menüs / Toolbar
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
        self.a_close = A(tr("Schließen"), self.close, QKeySequence.StandardKey.Close)
        self.a_copy = A(tr("Markierten Text kopieren"), self.copy_text, QKeySequence.StandardKey.Copy, "copy")
        self.a_seltext = A(tr("Text der Seite markieren"), lambda: self.view.select_page_text(), "Ctrl+Alt+A", "select")
        self.a_settings = A(tr("Einstellungen …"), self.settings_dialog, "Ctrl+,", "settings")
        self.a_manip = A(tr("CMYK und Beschneiden in einem Schritt …"), lambda: self.manip_dialog("all"), "Ctrl+Shift+M", "cmyk")
        self.a_manip_cmyk = A(tr("CMYK-Umwandlung …"), lambda: self.manip_dialog("cmyk"), None, "cmyk")
        self.a_manip_crop = A(tr("Auf Format beschneiden …"), lambda: self.manip_dialog("crop"), None, "crop")
        self.a_separate = A(tr("Objekte trennen (Einzelseiten ohne Weißraum) …"), self.separate_dialog, None, "separate")
        self.a_cut = A(tr("CutContour erzeugen (Schneideplotter) …"), self.cut_dialog, None, "cut")
        self.a_vdp = A(tr("Variable Daten (Nummern, QR-/Barcodes, CSV) …"), self.vdp_dialog, "Ctrl+Shift+D", "vdp")
        self.a_edit = A(tr("Text und Ebenen bearbeiten"), lambda: None, "Ctrl+T", "edit")
        self.a_edit.setCheckable(True)
        self.a_edit.toggled.connect(self._edit_mode)

        self.a_ins_before = A(tr("Seiten einfügen – vor Auswahl…"), lambda: self.insert_dialog("before"))
        self.a_ins_after = A(tr("Seiten einfügen – nach Auswahl…"), lambda: self.insert_dialog("after"), "Ctrl+I", "insert")
        self.a_ins_end = A(tr("Seiten anhängen (am Ende)…"), lambda: self.insert_dialog("end"), "Ctrl+Shift+I")
        self.a_export = A(tr("Auswahl als ein PDF exportieren…"), self.export_selection, "Ctrl+E", "export")
        self.a_export_each = A(tr("Auswahl als einzelne PDFs exportieren…"), self.export_each, "Ctrl+Shift+E")
        self.a_delete = A(tr("Seiten löschen"), self.delete_pages, QKeySequence.StandardKey.Delete, "delete")
        self.a_rot_l = A(tr("Seiten links drehen (dauerhaft)"), lambda: self.rotate_pages(-90), None, "rot_l")
        self.a_rot_r = A(tr("Seiten rechts drehen (dauerhaft)"), lambda: self.rotate_pages(90), None, "rot_r")
        self.a_up = A(tr("Seiten nach vorne verschieben"), lambda: self.move_pages(-1), "Alt+Up", "move_up")
        self.a_down = A(tr("Seiten nach hinten verschieben"), lambda: self.move_pages(1), "Alt+Down", "move_down")
        self.a_selall = A(tr("Alle Seiten auswählen"), lambda: self.thumbs.selectAll(), "Ctrl+Shift+A")

        mb = self.menuBar()
        m = mb.addMenu(tr("&Datei"))
        for a in (self.a_open, self.a_newwin, self.a_newtab, self.a_detach, None, self.a_save, self.a_saveas, None, self.a_print,
                  None, self.a_settings, None, self.a_close):
            m.addSeparator() if a is None else m.addAction(a)
        m = mb.addMenu(tr("&Seiten"))
        for a in (self.a_ins_before, self.a_ins_after, self.a_ins_end, None, self.a_export,
                  self.a_export_each, None, self.a_rot_l, self.a_rot_r, self.a_up, self.a_down, None,
                  self.a_delete, None, self.a_selall, None, self.a_copy, self.a_seltext):
            m.addSeparator() if a is None else m.addAction(a)
        self.page_menu = m
        m = mb.addMenu(tr("D&okument"))
        m.addAction(self.a_merge)
        m.addAction(self.a_repair)
        m.addSeparator()
        self.a_preflight = A(tr("Dokumentprüfung (Preflight) …"),
                             lambda: (self.pf_dock.show(), self.pf_dock.raise_(), self._pf_start(force=True)),
                             "Ctrl+Shift+P", "check")
        m.addAction(self.a_preflight)
        m = mb.addMenu(tr("Dokument-&Manipulation"))
        for a in (self.a_edit, None, self.a_manip_cmyk, self.a_manip_crop, None, self.a_manip, None, self.a_separate,
                  self.a_cut, None, self.a_vdp):
            m.addSeparator() if a is None else m.addAction(a)
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
        m.addAction(dock.toggleViewAction())
        self.a_actual = A(tr("Tatsächliche Größe"), lambda: self.view.set_zoom("fixed", 1.0), "Ctrl+0", "actual")
        self.a_fitpage = A(tr("Ganze Seite"), lambda: self.view.set_zoom("page"), "Ctrl+1", "fit_page")
        self.a_fitwidth = A(tr("Seitenbreite"), lambda: self.view.set_zoom("width"), "Ctrl+2", "fit_width")
        for a in (self.a_fitpage, self.a_fitwidth, self.a_actual):
            m.addAction(a)
        m.addSeparator()
        self.a_vrot_l = A(tr("Ansicht links drehen"), lambda: self.view.rotate(-90), "Ctrl+Shift+-", "rot_l")
        self.a_vrot_r = A(tr("Ansicht rechts drehen"), lambda: self.view.rotate(90), "Ctrl+Shift++", "rot_r")
        m.addAction(self.a_vrot_l)
        m.addAction(self.a_vrot_r)
        m = mb.addMenu(tr("&Verwaltung"))
        m.addAction(A(tr("Standardeinstellungen (Admin)…"), self.admin_dialog, None, "settings"))
        m = mb.addMenu(tr("&Hilfe"))
        a = QAction(tr("Kommandozeile – Anleitung (PDF)"), self)
        a.triggered.connect(self._open_cli_howto)
        m.addAction(a)
        from .. import platform as _pl
        if _pl.IS_WIN:
            a = QAction(tr("Windows-Druck testen …"), self)
            a.triggered.connect(self._win_print_test)
            m.addAction(a)
        a = QAction(tr("Fehlerprotokolle öffnen"), self)
        a.triggered.connect(lambda: __import__("pdfdruck.gui.crashui", fromlist=["x"]).open_log_dir())
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
        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setKeyboardTracking(False)
        self.page_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.page_spin.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.page_spin.setFixedWidth(52)
        self.page_spin.setFont(theme.mono_font(10))
        self.page_spin.valueChanged.connect(lambda v: self.view.goto(v - 1))
        tb.addWidget(self.page_spin)
        self.page_total = QLabel(" / 0 ")
        self.page_total.setFont(theme.mono_font(10))
        tb.addWidget(self.page_total)
        tb.addAction(A(tr("Nächste Seite"), lambda: self.view.goto(self.view.current + 1), None, "next"))
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
        self.ctl.view_single = single           # gilt für neue Fenster dieser Sitzung
        self.view.set_single(single)
        self.view.setFocus()

    def _update_actions(self):
        has = self.doc is not None
        for a in (self.a_save, self.a_saveas, self.a_print, self.a_ins_before, self.a_ins_after,
                  self.a_ins_end, self.a_export, self.a_export_each, self.a_delete, self.a_rot_l,
                  self.a_rot_r, self.a_up, self.a_down, self.a_selall, self.a_manip, self.a_manip_cmyk,
                  self.a_manip_crop, self.a_repair, self.a_separate, self.a_cut, self.a_edit, self.a_vdp):
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
    # Öffnen
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

    def _set_doc(self, doc, path, display, modified, keep_page=None):
        if self.doc is not None and self.doc is not doc:
            self.doc.close()
        self.doc, self.path, self.display_name, self.modified = doc, path, display, modified
        self.view.set_document(doc, keep_page)
        n = len(doc)
        self.page_spin.blockSignals(True)
        self.page_spin.setMaximum(max(1, n))
        self.page_spin.blockSignals(False)
        self.page_total.setText(f" / {n} ")
        self._rebuild_thumbs()
        self._update_actions()
        self._update_title()
        self._page_changed(self.view.current)
        if hasattr(self, "_pf_timer"):
            self._pf_timer.start()                       # Dokumentprüfung im Hintergrund

    def open(self, path: str):
        doc = load_pdf(self, path)
        if doc is not None:
            self._set_doc(doc, path, os.path.basename(path), False)

    def open_any(self, path: str):
        """PDF direkt öffnen, Office-Datei umwandeln und als (ungespeichertes) PDF öffnen."""
        if not _convert.is_office(path):
            self.open(path)
            return
        try:
            doc = load_any(self, self.ctl, path)
        except Exception as e:
            QMessageBox.critical(self, tr("Umwandeln"), str(e))
            return
        self._set_doc(doc, None, os.path.splitext(os.path.basename(path))[0] + ".pdf", False)
        self._suggest_dir = os.path.dirname(path)

    def open_images(self, paths: list[str]):
        try:
            doc = images.images_to_document(paths, self.ctl.image_dpi)
        except Exception as e:
            QMessageBox.critical(self, tr("Bild öffnen"), str(e))
            return
        base = os.path.splitext(os.path.basename(paths[0]))[0]
        name = f"{base}.pdf" if len(paths) == 1 else f"{base} (+{len(paths) - 1} Bilder).pdf"
        self._set_doc(doc, None, name, False)
        self._suggest_dir = os.path.dirname(paths[0])

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
        """Sicher speichern – auch über die gerade geöffnete Datei."""
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
        for a in (self.a_ins_before, self.a_ins_after, None, self.a_export, self.a_export_each, None,
                  self.a_rot_l, self.a_rot_r, self.a_up, self.a_down, None, self.a_delete):
            m.addSeparator() if a is None else m.addAction(a)
        m.exec(self.thumbs.mapToGlobal(pos))

    # ================================================================ #
    # Miniaturen / Anzeige
    # ================================================================ #
    def _rebuild_thumbs(self):
        self.thumbs.clear()
        for i in range(len(self.doc)):
            it = QListWidgetItem(str(i + 1))
            w, h = self.doc.get_page_size(i)
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
        self._thumb_timer.start()

    def _render_thumbs(self):
        if not self._thumb_queue or self.doc is None:
            self._thumb_timer.stop()
            return
        dlg = self.thumbs.itemDelegate()
        vw = max(60, self.thumbs.viewport().width() - 4)
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
            w, _h = self.doc.get_page_size(i)
            page = self.doc[i]
            pm = render_pixmap(page, iw / w, 0, dpr)
            page.close()
            it.setData(THUMB_PIX, pm)
            it.setData(THUMB_W, iw)

    def _page_changed(self, i):
        if self.doc is None:
            self.lbl_size.setText("")
            return
        self.page_spin.blockSignals(True)
        self.page_spin.setValue(i + 1)
        self.page_spin.blockSignals(False)
        if len(self.thumbs.selectedItems()) <= 1 and 0 <= i < self.thumbs.count():
            self.thumbs.blockSignals(True)
            self.thumbs.setCurrentRow(i)
            self.thumbs.blockSignals(False)
            self.thumbs.scrollToItem(self.thumbs.item(i))
        w, h = self.doc.get_page_size(i)
        txt = tr("Seite {0}/{1}   ·   {2}").format(i + 1, len(self.doc), page_size_text(w, h))
        try:
            from ..layout import trim_info
            ti = trim_info(self.doc, i)
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

    def vdp_dialog(self):
        if self.doc is None:
            return
        from .vdpdialog import VdpDialog
        try:
            dlg = VdpDialog(self, self.doc, self.view.current)
        except Exception as e:
            from .objectsdialog import show_error
            show_error(self, tr("Fehler"), e)
            return
        if dlg.exec() and getattr(dlg, "job", None):
            self.start_job(*dlg.job, suffix=tr("_Daten"), title=tr("Variable Daten"),
                           notes=lambda info: [tr("{0} Datensätze, {1} Seiten erzeugt.").format(
                               info.get("records", 0), info.get("pages", 0))])

    # ---------------- Aufträge im Hintergrund (eigener Prozess) ---------------- #
    def start_job(self, kind, settings, pages=None, suffix="", title="", notes=None):
        """Dokument in den Zwischenspeicher, Kommandozeile als eigenen Prozess starten, Fortschritt unten anzeigen."""
        from .. import jobproc, l10n
        from .jobs import JobReader, JobWidget
        base = os.path.splitext(self.display_name or "Dokument")[0]
        src = self.ctl.cache_file(base + "_eingabe.pdf")
        dst = self.ctl.cache_file(base + suffix + ".pdf")
        try:
            self.doc.save(src)                                   # aktueller Stand (auch ungespeicherte Änderungen)
            open(dst, "wb").close()                              # Namen reservieren (mehrere Aufträge gleichzeitig)
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
        """Fenster wird geschlossen: laufende Aufträge abbrechen."""
        for entry in list(self._jobs):
            entry["job"].cancel()
        for entry in list(self._jobs):
            entry["reader"].wait(5000)

    def _open_result(self, new_doc, suffix: str, notes=()):
        """Ergebnis in den Zwischenspeicher schreiben und von dort in einem neuen Fenster öffnen."""
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
        """Fertige Datei aus dem Zwischenspeicher in einem neuen Fenster öffnen (temporär, „Speichern unter“)."""
        doc = load_pdf(self, path)
        if doc is None:
            return
        w = self.ctl.new_window(tab_of=self)
        # temporär: kein fester Speicherort -> „Speichern“ fragt nach, Schließen erinnert ans Speichern
        w._set_doc(doc, None, os.path.basename(path), True)
        w._temp_path = path
        w._suggest_dir = os.path.dirname(self.path) if self.path else getattr(self, "_suggest_dir", "")
        w.raise_()
        msg = tr("Temporär im Zwischenspeicher – zum Behalten „Speichern unter …“.")
        if notes:
            msg += "  " + "  ".join(notes)
        w.statusBar().showMessage(msg, 20000)

    @staticmethod
    def cli_howto_path() -> str:
        """Anleitung zur Kommandozeile im Programmpaket (Linux-Installation, AppImage, Windows-Setup)."""
        from .. import __file__ as pkg
        return os.path.join(os.path.dirname(pkg), "docs", "passermark-cli-anleitung.pdf")

    def _open_cli_howto(self):
        p = self.cli_howto_path()
        if not os.path.isfile(p):
            QMessageBox.warning(self, tr("Hilfe"), tr("Anleitung nicht gefunden: {0}").format(p))
            return
        self.ctl.open_paths([p], tab_of=self)

    def _win_print_test(self):
        """Je Verfahren eine Testseite drucken – zeigt, was der Treiber wirklich kann (leere Blätter?)."""
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
            # aktueller Stand (bearbeitet, aus Bildern oder entsperrt) -> unverschlüsselte Arbeitskopie
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
        PrintDialog(self, self.doc, self.display_name, self.view.current, self.session).exec()

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
            # Strg + Ablegen = an das aktuelle Dokument anhängen
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
