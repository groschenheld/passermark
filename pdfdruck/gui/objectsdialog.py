# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Dialoge „Objekte trennen“ (Einzelseiten ohne Weißraum) und „CutContour erzeugen“ (Schneideplotter)."""
from __future__ import annotations

import dataclasses
import traceback

import math

from PySide6.QtCore import QPointF, QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QSpinBox, QVBoxLayout, QWidget)

from .. import cutcontour, objects
from ..l10n import tr
from . import theme
from .common import split_panels, fill_combo, fit_width

MODES = [("auto", "Automatisch"), ("transparent", "Vektor/Transparenz (exakt)"),
         ("color", "Hintergrundfarbe (Scans)")]
SHAPES = [("contour", "Kontur (folgt dem Motiv)"), ("rect", "Rechteck"), ("rounded", "Abgerundetes Rechteck"),
          ("circle", "Kreis"), ("oval", "Oval"), ("hexagon", "Sechseck"), ("octagon", "Achteck"), ("heart", "Herz"),
          ("star", "Stern"), ("shield", "Wappen"), ("arch", "Torbogen")]


def fmt_mm(v: float) -> str:
    from .. import l10n
    from ..measure import fmt
    return fmt(v, l10n.current())


def show_error(parent, title, exc):
    """Fehlermeldung mit Details (Ablauf zum Kopieren) – damit Fehler eindeutig gemeldet werden können."""
    box = QMessageBox(QMessageBox.Icon.Critical, title, str(exc) or type(exc).__name__, parent=parent)
    box.setDetailedText(traceback.format_exc())
    box.exec()


def rgba_to_pixmap(arr) -> QPixmap:
    import numpy as np
    a = np.ascontiguousarray(arr.astype(np.uint8))
    h, w = a.shape[:2]
    qi = QImage(a.data, w, h, 4 * w, QImage.Format.Format_RGBA8888).copy()
    return QPixmap.fromImage(qi)


class PageCanvas(QWidget):
    """Zeigt eine (normalisierte) Seite; Rahmen anzeigen/auswählen/aufziehen; optional Konturen."""
    changed = Signal()

    def __init__(self, editable=True):
        super().__init__()
        self.setMinimumSize(420, 520)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.editable = editable
        self.page_w = self.page_h = 1.0
        self.layers = []          # [(QPixmap, (x0, y0, x1, y1) pt)] – von unten nach oben
        self.boxes: list[objects.Box] = []
        self.selected: set[int] = set()
        self.paths = []           # Konturen in pt
        self.shape_box = None     # Grundform: Rahmen der Form (pt) -> Griffe zum Skalieren/Verschieben
        self.on_shape = None      # Rückruf (sx, sy, dx_pt, dy_pt) beim Loslassen
        self.keep_aspect = False  # Kreis: Seitengriffe skalieren gleichmäßig
        self.on_shaping = None    # Rückruf (sx, sy, dx_pt, dy_pt) während des Ziehens (Anzeige)
        self.live = (1.0, 1.0, 0.0, 0.0)
        self._sdrag = None
        self.margin_pt = 0.0      # Vorschau des Randes (gestrichelt)
        self._drag = None

    def set_page(self, w, h, layers):
        self.page_w, self.page_h, self.layers = w, h, layers
        self.update()

    # Koordinaten -------------------------------------------------------- #
    def _geom(self):
        m = 12
        s = min((self.width() - 2 * m) / self.page_w, (self.height() - 2 * m) / self.page_h)
        ox = (self.width() - self.page_w * s) / 2
        oy = (self.height() - self.page_h * s) / 2
        return s, ox, oy

    def to_widget(self, x, y):
        s, ox, oy = self._geom()
        return QPointF(ox + x * s, oy + (self.page_h - y) * s)

    def to_pt(self, p):
        s, ox, oy = self._geom()
        return (p.x() - ox) / s, self.page_h - (p.y() - oy) / s

    def _rect(self, b):
        a, c = self.to_widget(b.x0, b.y1), self.to_widget(b.x1, b.y0)
        return QRectF(a, c)

    # Zeichnen ------------------------------------------------------------ #
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor(theme.VIEW))
        page = QRectF(self.to_widget(0, self.page_h), self.to_widget(self.page_w, 0))
        p.fillRect(page, Qt.GlobalColor.white)
        for pm, (x0, y0, x1, y1) in self.layers:
            p.drawPixmap(QRectF(self.to_widget(x0, y1), self.to_widget(x1, y0)), pm, QRectF(pm.rect()))
        for i, b in enumerate(self.boxes):
            sel = i in self.selected
            p.setPen(QPen(QColor(theme.ACCENT) if sel else QColor(0, 160, 255), 2.5 if sel else 1.5))
            c = QColor(theme.ACCENT if sel else "#00a0ff")
            c.setAlpha(50)
            p.setBrush(c)
            r = self._rect(b)
            p.drawRect(r)
            if abs(self.margin_pt) > 0.01:
                mb = objects.with_margin(b, self.margin_pt / objects.MM, self.page_w, self.page_h)
                p.save()
                p.setPen(QPen(QColor(236, 0, 140), 1.5, Qt.PenStyle.DashLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(self._rect(mb))
                p.restore()
                p.setPen(QPen(QColor(theme.ACCENT) if sel else QColor(0, 160, 255), 2.5 if sel else 1.5))
            p.setPen(QColor("#000"))
            p.drawText(r.adjusted(4, 2, 0, 0), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop), str(i + 1))
        if self.paths:
            p.setBrush(Qt.BrushStyle.NoBrush)
            live = self.live != (1.0, 1.0, 0.0, 0.0)
            p.setPen(QPen(QColor(236, 0, 140), 1.6, Qt.PenStyle.DashLine if live else Qt.PenStyle.SolidLine))
            for poly in self.paths:
                tpoly = self._transformed(poly) if live else poly
                path = QPainterPath(self.to_widget(*tpoly[0]))
                for x, y in tpoly[1:]:
                    path.lineTo(self.to_widget(x, y))
                path.closeSubpath()
                p.drawPath(path)
            if self.shape_box is not None:
                self._paint_handles(p)
        if self._drag:
            p.setPen(QPen(QColor(theme.ACCENT), 1, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(self._drag[0], self._drag[1]).normalized())

    # Griffe der Grundform ------------------------------------------------ #
    HANDLE = 5          # halbe Griffgröße (px)
    GRIP_OFF = 18       # Verschiebe-Griff: Abstand über der Form (px)

    def _box_now(self):
        """Rahmen der Form inkl. laufender Änderung (pt)."""
        x0, y0, x1, y1 = self.shape_box
        sx, sy, dx, dy = self.live
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        hw, hh = (x1 - x0) / 2 * sx, (y1 - y0) / 2 * sy
        return cx - hw + dx, cy - hh + dy, cx + hw + dx, cy + hh + dy

    def _transformed(self, poly):
        """Punkte der Form mit laufender Änderung: jede Form um ihre eigene Mitte skaliert, dann verschoben."""
        sx, sy, dx, dy = self.live
        xs = [x for x, _y in poly]
        ys = [y for _x, y in poly]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        return [(cx + (x - cx) * sx + dx, cy + (y - cy) * sy + dy) for x, y in poly]

    def _handles(self):
        """{Name: Bildschirmpunkt} – Ecken (gleichmäßig), Seiten (nur Breite/Höhe), Verschiebe-Griff."""
        x0, y0, x1, y1 = self._box_now()
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        h = {"c00": (x0, y0), "c10": (x1, y0), "c01": (x0, y1), "c11": (x1, y1),
             "sx0": (x0, cy), "sx1": (x1, cy), "sy0": (cx, y0), "sy1": (cx, y1)}
        out = {k: self.to_widget(*v) for k, v in h.items()}
        top = self.to_widget(cx, y1)
        out["move"] = QPointF(top.x(), top.y() - self.GRIP_OFF)
        return out

    def _hit(self, pos):
        for name, c in self._handles().items():
            r = self.HANDLE + (3 if name == "move" else 2)
            if abs(pos.x() - c.x()) <= r + 2 and abs(pos.y() - c.y()) <= r + 2:
                return name
        return None

    def _paint_handles(self, p):
        hs = self._handles()
        top = self.to_widget((self._box_now()[0] + self._box_now()[2]) / 2, self._box_now()[3])
        p.setPen(QPen(QColor(236, 0, 140), 1))
        p.drawLine(top, hs["move"])
        p.setBrush(QColor("#ffffff"))
        for name, c in hs.items():
            if name == "move":
                continue
            p.drawRect(QRectF(c.x() - self.HANDLE, c.y() - self.HANDLE, 2 * self.HANDLE, 2 * self.HANDLE))
        m = hs["move"]
        p.setBrush(QColor(236, 0, 140))
        p.drawEllipse(m, self.HANDLE + 3, self.HANDLE + 3)
        p.setPen(QPen(QColor("#ffffff"), 1.4))
        a = self.HANDLE
        p.drawLine(QPointF(m.x() - a, m.y()), QPointF(m.x() + a, m.y()))     # Kreuz = verschieben
        p.drawLine(QPointF(m.x(), m.y() - a), QPointF(m.x(), m.y() + a))

    # Maus/Tastatur ------------------------------------------------------- #
    def mousePressEvent(self, e):
        if not self.editable:
            if self.shape_box is not None and self.paths and e.button() == Qt.MouseButton.LeftButton:
                name = self._hit(e.position())
                if name is not None:
                    x0, y0, x1, y1 = self.shape_box
                    c = self.to_widget((x0 + x1) / 2, (y0 + y1) / 2)
                    self._sdrag = (name, e.position(), c)
            return
        pos = e.position()
        hit = next((i for i in reversed(range(len(self.boxes))) if self._rect(self.boxes[i]).contains(pos)), None)
        ctrl = bool(e.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))
        if hit is not None:
            if ctrl:
                self.selected ^= {hit}
            else:
                self.selected = {hit}
            self.update()
            return
        if not ctrl:
            self.selected = set()
        self._drag = [pos, pos]
        self.update()

    def mouseMoveEvent(self, e):
        if self._sdrag:
            name, p0, c = self._sdrag
            pos = e.position()
            sx = sy = 1.0
            dx = dy = 0.0
            if name == "move":
                s_, _ox, _oy = self._geom()
                dx, dy = (pos.x() - p0.x()) / s_, -(pos.y() - p0.y()) / s_
            elif name.startswith("c"):
                d0 = math.hypot(p0.x() - c.x(), p0.y() - c.y()) or 1.0
                sx = sy = max(0.05, min(20.0, math.hypot(pos.x() - c.x(), pos.y() - c.y()) / d0))
            elif name.startswith("sx"):
                sx = max(0.05, min(20.0, abs(pos.x() - c.x()) / (abs(p0.x() - c.x()) or 1.0)))
                if self.keep_aspect:
                    sy = sx                              # Kreis: Seitengriff skaliert gleichmäßig
            else:
                sy = max(0.05, min(20.0, abs(pos.y() - c.y()) / (abs(p0.y() - c.y()) or 1.0)))
                if self.keep_aspect:
                    sx = sy
            self.live = (sx, sy, dx, dy)
            if self.on_shaping is not None:
                self.on_shaping(*self.live)
            self.update()
            return
        if not self.editable and self.shape_box is not None and self.paths:
            name = self._hit(e.position())
            cur = {"c00": Qt.CursorShape.SizeBDiagCursor, "c11": Qt.CursorShape.SizeBDiagCursor,
                   "c10": Qt.CursorShape.SizeFDiagCursor, "c01": Qt.CursorShape.SizeFDiagCursor,
                   "sx0": Qt.CursorShape.SizeHorCursor, "sx1": Qt.CursorShape.SizeHorCursor,
                   "sy0": Qt.CursorShape.SizeVerCursor, "sy1": Qt.CursorShape.SizeVerCursor,
                   "move": Qt.CursorShape.SizeAllCursor}.get(name, Qt.CursorShape.ArrowCursor)
            self.setCursor(cur)
        if self._drag:
            self._drag[1] = e.position()
            self.update()

    def mouseReleaseEvent(self, e):
        if self._sdrag:
            self._sdrag = None
            sx, sy, dx, dy = self.live
            changed = abs(sx - 1) > 0.002 or abs(sy - 1) > 0.002 or abs(dx) > 0.2 or abs(dy) > 0.2
            if self.on_shape is not None and changed:
                self.on_shape(sx, sy, dx, dy)            # Größe/Versatz in mm übernehmen -> neu rechnen
            else:
                self.live = (1.0, 1.0, 0.0, 0.0)
                self.update()
            return
        if not self._drag:
            return
        a, b = self.to_pt(self._drag[0]), self.to_pt(self._drag[1])
        self._drag = None
        x0, x1 = sorted((max(0, a[0]), min(self.page_w, b[0])))
        y0, y1 = sorted((max(0, a[1]), min(self.page_h, b[1])))
        if x1 - x0 > 3 * objects.MM and y1 - y0 > 3 * objects.MM:
            self.boxes.append(objects.Box(x0, y0, x1, y1))
            self.selected = {len(self.boxes) - 1}
            self.changed.emit()
        self.update()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.remove_selected()
        else:
            super().keyPressEvent(e)

    def remove_selected(self):
        self.boxes = [b for i, b in enumerate(self.boxes) if i not in self.selected]
        self.selected = set()
        self.changed.emit()
        self.update()

    def merge_selected(self):
        sel = [self.boxes[i] for i in sorted(self.selected)]
        if len(sel) < 2:
            return
        m = objects.Box(min(b.x0 for b in sel), min(b.y0 for b in sel), max(b.x1 for b in sel), max(b.y1 for b in sel))
        self.boxes = [b for i, b in enumerate(self.boxes) if i not in self.selected] + [m]
        self.boxes = objects.reading_order(self.boxes)
        self.selected = {self.boxes.index(m)}
        self.changed.emit()
        self.update()


def _detect_group(parent, ds: objects.DetectSettings, with_gap=True, with_margin=True):
    g = QGroupBox(tr("Erkennung"))
    f = QFormLayout(g)
    w = {}
    w["mode"] = QComboBox()
    fill_combo(w["mode"], MODES, ds.mode)
    f.addRow(tr("Hintergrund:"), w["mode"])
    w["tol"] = QSpinBox()
    w["tol"].setRange(2, 200)
    w["tol"].setValue(ds.tolerance)
    w["tol"].setToolTip(tr("Wie stark sich ein Pixel vom Hintergrund unterscheiden muss (Scans: Papiergrau, Rauschen)"))
    f.addRow(tr("Toleranz:"), w["tol"])
    w["min"] = QDoubleSpinBox()
    w["min"].setRange(0.5, 200)
    w["min"].setSuffix(" mm")
    w["min"].setValue(ds.min_size_mm)
    f.addRow(tr("Mindestgröße:"), w["min"])
    if with_gap:
        w["gap"] = QDoubleSpinBox()
        w["gap"].setRange(0, 50)
        w["gap"].setSuffix(" mm")
        w["gap"].setValue(ds.gap_mm)
        w["gap"].setToolTip(tr("Teile, die näher beisammen liegen, gelten als ein Objekt"))
        f.addRow(tr("Zusammenfassen bis:"), w["gap"])
    if with_margin:
        w["margin"] = QDoubleSpinBox()
        w["margin"].setRange(-50, 50)
        w["margin"].setToolTip(tr("Negativ = nach innen in das Objekt beschneiden"))
        w["margin"].setSuffix(" mm")
        w["margin"].setValue(ds.margin_mm)
        f.addRow(tr("Rand um jedes Objekt:"), w["margin"])
    return g, w


def _read_detect(w, ds: objects.DetectSettings):
    ds.mode = w["mode"].currentData()
    ds.tolerance = w["tol"].value()
    ds.min_size_mm = w["min"].value()
    if "gap" in w:
        ds.gap_mm = w["gap"].value()
    if "margin" in w:
        ds.margin_mm = w["margin"].value()
    return ds


# --------------------------------------------------------------------------- #
class SeparateDialog(QDialog):
    """Objekte (z. B. Visitenkarten auf einem Bogen) erkennen und als Einzelseiten ohne Weißraum ausgeben."""

    def __init__(self, parent, doc, current=0):
        super().__init__(parent)
        self.setWindowTitle(tr("Objekte trennen – Passermark"))
        self.resize(1100, 800)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.norm = objects.normalized(doc)
        finally:
            QApplication.restoreOverrideCursor()
        self.ds = objects.DetectSettings()
        self.boxes: dict[int, list] = {}
        self.page = min(current, len(self.norm) - 1)
        self.result = None

        root = QHBoxLayout(self)
        self.canvas = PageCanvas(editable=True)
        self.canvas.changed.connect(self._canvas_changed)
        left = QVBoxLayout()
        left.addWidget(self.canvas, 1)
        nav = QHBoxLayout()
        nav.addWidget(QLabel(tr("Seite:")))
        self.spn_page = QSpinBox()
        self.spn_page.setRange(1, len(self.norm))
        self.spn_page.setValue(self.page + 1)
        self.spn_page.valueChanged.connect(self._goto)
        nav.addWidget(self.spn_page)
        nav.addWidget(QLabel(f"/ {len(self.norm)}"))
        nav.addStretch()
        left.addLayout(nav)
        hint = QLabel(tr("Klicken = auswählen (Strg/Umschalt: mehrere) · auf freier Fläche ziehen = Rahmen hinzufügen · "
                         "Entf = entfernen"))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {theme.MUTED};")
        left.addWidget(hint)
        # links: Vorschau – kommt unten mit den Einstellungen in einen verschiebbaren Teiler

        right = QVBoxLayout()
        g, self.w = _detect_group(self, self.ds)
        right.addWidget(g)
        # Rand wirkt sofort (auch auf eigene Rahmen); die anderen Regler erkennen die Seite automatisch neu
        self.w["margin"].valueChanged.connect(self._margin_changed)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(450)
        self._timer.timeout.connect(lambda: self._detect([self.page]))
        self.w["mode"].currentIndexChanged.connect(self._timer.start)
        for k in ("tol", "min", "gap"):
            self.w[k].valueChanged.connect(self._timer.start)
        row = QHBoxLayout()
        b1 = QPushButton(tr("Diese Seite neu erkennen"))
        b1.clicked.connect(lambda: self._detect([self.page]))
        b2 = QPushButton(tr("Alle Seiten"))
        b2.clicked.connect(lambda: self._detect(range(len(self.norm))))
        row.addWidget(b1)
        row.addWidget(b2)
        right.addLayout(row)
        g2 = QGroupBox(tr("Rahmen"))
        v2 = QVBoxLayout(g2)
        row = QHBoxLayout()
        b3 = QPushButton(tr("Entfernen"))
        b3.clicked.connect(self.canvas.remove_selected)
        b4 = QPushButton(tr("Zusammenlegen"))
        b4.clicked.connect(self.canvas.merge_selected)
        row.addWidget(b3)
        row.addWidget(b4)
        v2.addLayout(row)
        self.lbl_count = QLabel()
        self.lbl_count.setStyleSheet(f"color: {theme.ACCENT};")
        v2.addWidget(self.lbl_count)
        right.addWidget(g2)
        right.addStretch()
        bb = QDialogButtonBox()
        ok = bb.addButton(tr("Als Einzelseiten öffnen"), QDialogButtonBox.ButtonRole.AcceptRole)
        ok.setDefault(True)
        bb.addButton(tr("Abbrechen"), QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(self._apply)
        bb.rejected.connect(self.reject)
        right.addWidget(bb)
        wrap = QWidget()
        wrap.setLayout(right)
        split_panels(root, left, wrap, 400)
        fit_width(wrap)
        self._detect([self.page])

    def _render(self):
        pg = self.norm[self.page]
        try:
            w, h = pg.get_size()
            pm = rgba_to_pixmap(objects.render_rgba(pg, 72))
        finally:
            pg.close()
        self.canvas.boxes = self.boxes.get(self.page, [])
        self.canvas.selected = set()
        self.canvas.set_page(w, h, [(pm, (0, 0, w, h))])
        self._count()

    def _margin_changed(self, v):
        self.ds.margin_mm = v
        self.canvas.margin_pt = v * objects.MM
        self.canvas.update()

    def _detect(self, pages):
        _read_detect(self.w, self.ds)
        raw = dataclasses.replace(self.ds, margin_mm=0.0)     # Rahmen = Objekt; Rand erst bei der Ausgabe
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            for i in pages:
                pg = self.norm[i]
                try:
                    self.boxes[i] = objects.detect(pg, raw)
                finally:
                    pg.close()
        finally:
            QApplication.restoreOverrideCursor()
        self.canvas.margin_pt = self.ds.margin_mm * objects.MM
        self._render()

    def _goto(self, v):
        self.boxes[self.page] = self.canvas.boxes
        self.page = v - 1
        if self.page not in self.boxes:
            self._detect([self.page])
        else:
            self._render()

    def _canvas_changed(self):
        self.boxes[self.page] = self.canvas.boxes
        self._count()

    def _count(self):
        total = sum(len(v) for v in self.boxes.values())
        self.lbl_count.setText(tr("{0} Objekt(e) auf dieser Seite · {1} insgesamt").format(
            len(self.canvas.boxes), total))

    def _apply(self):
        self.boxes[self.page] = self.canvas.boxes
        if not any(self.boxes.values()):
            QMessageBox.information(self, tr("Nichts zu tun"), tr("Keine Objekte gefunden."))
            return
        # nur den Auftrag beschreiben – gerechnet wird im Hintergrund (eigener Prozess)
        boxes = {str(i): [[b.x0, b.y0, b.x1, b.y1] for b in bs] for i, bs in self.boxes.items() if bs}
        self.job = ("separate", {"margin_mm": self.w["margin"].value(), "boxes": boxes},
                    sorted(int(i) for i in boxes))
        self.accept()

    def done(self, r):
        self.norm.close()
        super().done(r)


# --------------------------------------------------------------------------- #
class _CutWorker(QThread):
    """Konturberechnung im Hintergrund (nur numpy/scipy – die Seite wurde vorher im Hauptthread gerendert)."""
    done = Signal(int, object, str)

    def __init__(self, gen, s, rgba, size, trim=None):
        super().__init__()
        self.gen, self.s, self.rgba, self.size, self.trim = gen, s, rgba, size, trim

    def run(self):
        try:
            self.done.emit(self.gen, cutcontour.compute(None, self.s, self.rgba, self.size, trim=self.trim), "")
        except Exception as e:
            import traceback
            self.done.emit(self.gen, None, f"{e}\n\n{traceback.format_exc()}")


class CutContourDialog(QDialog):
    """Schnittkontur (Sonderfarbe CutContour) mit Überfüller für Schneideplotter, z. B. Roland VersaWorks."""

    def __init__(self, parent, doc, current=0):
        super().__init__(parent)
        self.setWindowTitle(tr("CutContour erzeugen – Passermark"))
        self.resize(1150, 820)
        self.doc = doc
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.norm = objects.normalized(doc)
        finally:
            QApplication.restoreOverrideCursor()
        self.page = min(current, len(self.norm) - 1)
        self.s = cutcontour.CutSettings(shape="rect", fit="trim")   # Standard: Rechteck aufs Endformat (sofort)
        self.result = None
        self.count = 0

        root = QHBoxLayout(self)
        left = QVBoxLayout()
        self.canvas = PageCanvas(editable=False)
        left.addWidget(self.canvas, 1)
        nav = QHBoxLayout()
        nav.addWidget(QLabel(tr("Seite:")))
        self.spn_page = QSpinBox()
        self.spn_page.setRange(1, len(self.norm))
        self.spn_page.setValue(self.page + 1)
        self.spn_page.valueChanged.connect(lambda v: (setattr(self, "page", v - 1), self._preview()))
        nav.addWidget(self.spn_page)
        nav.addWidget(QLabel(f"/ {len(self.norm)}"))
        nav.addStretch()
        self.lbl_info = QLabel()
        self.lbl_info.setStyleSheet(f"color: {theme.ACCENT};")
        nav.addWidget(self.lbl_info)
        left.addLayout(nav)
        # links: Vorschau – kommt unten mit den Einstellungen in einen verschiebbaren Teiler

        right = QVBoxLayout()
        from .presetbar import PresetBar
        self.presetbar = PresetBar(self, "cutcontour", self._settings, self._load_settings)
        right.addWidget(self.presetbar)
        g = QGroupBox(tr("Schnittlinie"))
        f = QFormLayout(g)
        self.cmb_shape = QComboBox()
        fill_combo(self.cmb_shape, SHAPES, self.s.shape)
        f.addRow(tr("Form:"), self.cmb_shape)
        self.cmb_single = QComboBox()
        fill_combo(self.cmb_single, [("trim", tr("Auf das Endformat (ohne Berechnung)")),
                                     ("motif", tr("Eine Form um das ganze Motiv")),
                                     ("each", tr("Eine Form je Objekt"))], self._placement(self.s))
        self.cmb_single.setToolTip(tr("Bei Grundformen: „Endformat“ legt die Form direkt aufs Endformat (TrimBox, "
                                      "sonst die Seite) – sofort, ohne Motiv-Erkennung; Überfüller bringt das PDF "
                                      "selbst mit (Anschnitt). Sonst eine Form mittig um alle Teile des Motivs oder je "
                                      "erkanntem Objekt eine eigene – z. B. für Aufkleberbögen. "
                                      "In der Vorschau lässt sich die Form mit der Maus größer/kleiner ziehen."))
        f.addRow("", self.cmb_single)

        def dspin(val, lo, hi, tip=""):
            sp = QDoubleSpinBox()
            sp.setRange(lo, hi)
            sp.setDecimals(1)
            sp.setSingleStep(0.5)
            sp.setSuffix(" mm")
            sp.setValue(val)
            if tip:
                sp.setToolTip(tip)
            return sp
        self.spn_off = dspin(self.s.offset_mm, -30, 30, tr("Abstand der Schnittlinie vom Motivrand: + nach außen (weißer Rand), − nach innen"))
        f.addRow(tr("Abstand zum Motiv:"), self.spn_off)
        self.spn_corner = dspin(self.s.corner_mm, 0, 200)
        f.addRow(tr("Eckenradius:"), self.spn_corner)
        row = QHBoxLayout()
        self.spn_fw, self.spn_fh = dspin(0, 0, 2000), dspin(0, 0, 2000)
        self.spn_fw.valueChanged.connect(
            lambda v: self.cmb_shape.currentData() == "circle" and self.spn_fh.setValue(v))
        for sp in (self.spn_fw, self.spn_fh):
            sp.setSpecialValueText(tr("auto"))
            sp.setToolTip(tr("Größe der Schnittlinie in mm; „auto“ = aus dem Motiv plus Abstand (nur eine Angabe: "
                             "Seitenverhältnis bleibt). Ändert sich auch beim Ziehen an den Griffen in der Vorschau."))
        row.addWidget(self.spn_fw)
        row.addWidget(QLabel("×"))
        row.addWidget(self.spn_fh)
        self.btn_size0 = QPushButton("↺")
        self.btn_size0.setFixedWidth(34)
        self.btn_size0.setToolTip(tr("Größe und Lage zurücksetzen (automatisch aus dem Motiv, mittig)"))
        self.btn_size0.clicked.connect(self._reset_shape)
        row.addWidget(self.btn_size0)
        f.addRow(tr("Größe (B × H):"), row)
        row = QHBoxLayout()
        self.spn_sx, self.spn_sy = dspin(self.s.shift_x_mm, -2000, 2000), dspin(self.s.shift_y_mm, -2000, 2000)
        for sp, tip in ((self.spn_sx, tr("Versatz waagrecht (+ rechts)")), (self.spn_sy, tr("Versatz senkrecht (+ oben)"))):
            sp.setToolTip(tip + " – " + tr("auch mit dem Verschiebe-Griff über der Form in der Vorschau"))
            row.addWidget(sp)
        self.btn_shift0 = QPushButton("↺")
        self.btn_shift0.setFixedWidth(34)
        self.btn_shift0.setToolTip(tr("Form wieder mittig aufs Motiv setzen"))
        self.btn_shift0.clicked.connect(lambda: (self.spn_sx.setValue(0), self.spn_sy.setValue(0)))
        row.addWidget(self.btn_shift0)
        f.addRow(tr("Versatz (X / Y):"), row)
        self.spn_smooth = dspin(self.s.smooth_mm, 0, 20, tr("Buchten und Lücken schmaler als das Doppelte werden überbrückt, Ecken gerundet – nötig zum Entgittern"))
        f.addRow(tr("Glättung:"), self.spn_smooth)
        self.spn_bleed = dspin(self.s.bleed_mm, 0, 10, tr("So weit wird das Motiv über die Schnittlinie hinaus verlängert"))
        row_b = QHBoxLayout()
        self.chk_bleed = QCheckBox(tr("erzeugen"))
        self.chk_bleed.setChecked(self.s.bleed)
        self.chk_bleed.setToolTip(tr("Aus: Motiv bleibt unverändert, nur die Schnittlinie – z. B. für weiße Ränder "
                                     "(„Abstand zum Motiv“ ins Plus)"))
        row_b.addWidget(self.chk_bleed)
        row_b.addWidget(self.spn_bleed, 1)
        f.addRow(tr("Überfüller:"), row_b)
        self.chk_inner = QCheckBox(tr("Innenkonturen mitschneiden (Löcher im Motiv)"))
        self.chk_inner.setChecked(self.s.inner)
        f.addRow(self.chk_inner)
        row = QHBoxLayout()
        self.cmb_bcol = QComboBox()
        fill_combo(self.cmb_bcol, [("auto", tr("Automatisch (Vollfarben aus dem Motiv)")),
                                   ("fixed", tr("Feste Farbe (gleichmäßiger Rand)"))], "auto")
        self.btn_bcol = QPushButton()
        self.btn_bcol.setFixedWidth(46)
        self.btn_bcol.setToolTip(tr("Farbe wählen"))
        self._bcol = "#ffffff"
        self._paint_bcol()
        self.btn_bcol.clicked.connect(self._pick_bcol)
        row.addWidget(self.cmb_bcol, 1)
        row.addWidget(self.btn_bcol)
        f.addRow(tr("Überfüller-Farbe:"), row)
        self.chk_seams = QCheckBox(tr("Mischkanten im Motiv bereinigen (bis ~1 mm, nur flächige Motive)"))
        self.chk_seams.setToolTip(tr("Ersetzt schmale Mischsäume zwischen Vollfarben (z. B. dunkle Linie zwischen "
                                     "Rot und Grün) durch die jeweilige Vollfarbe. Verändert das Motiv leicht."))
        f.addRow(self.chk_seams)
        right.addWidget(g)

        ds = self.s.detect
        g2, self.w = _detect_group(self, ds, with_gap=True, with_margin=False)
        right.addWidget(g2)

        g3 = QGroupBox(tr("Ausgabe"))
        f3 = QFormLayout(g3)
        self.cmb_out = QComboBox()
        fill_combo(self.cmb_out, [(False, tr("Auf dem Bogen lassen")), (True, tr("Jedes Objekt als eigene Seite"))], False)
        f3.addRow(tr("Objekte:"), self.cmb_out)
        self.ed_spot = QLineEdit(self.s.spot)
        self.ed_spot.setToolTip(tr("Name der Sonderfarbe – Roland VersaWorks erkennt „CutContour“"))
        f3.addRow(tr("Sonderfarbe:"), self.ed_spot)
        self.spn_stroke = QDoubleSpinBox()
        self.spn_stroke.setRange(0.05, 2)
        self.spn_stroke.setDecimals(2)
        self.spn_stroke.setSingleStep(0.05)
        self.spn_stroke.setSuffix(" pt")
        self.spn_stroke.setValue(self.s.stroke_pt)
        f3.addRow(tr("Linienstärke:"), self.spn_stroke)
        self.cmb_dpi = QComboBox()
        fill_combo(self.cmb_dpi, [(150, "150 dpi"), (200, "200 dpi"), (300, "300 dpi"), (400, "400 dpi")], self.s.dpi)
        self.cmb_dpi.setToolTip(tr("Rechenauflösung für Kontur und Überfüller (höher = genauer, langsamer)"))
        f3.addRow(tr("Genauigkeit:"), self.cmb_dpi)
        self.spn_margin = dspin(self.s.margin_mm, 0, 50, tr("Rand um Überfüller und Schnitt auf den Einzelseiten"))
        f3.addRow(tr("Seitenrand:"), self.spn_margin)
        self.cmb_shape.currentIndexChanged.connect(self._sync)
        self.cmb_bcol.currentIndexChanged.connect(self._sync)
        self.chk_bleed.toggled.connect(self._sync)
        self.cmb_out.currentIndexChanged.connect(self._sync)
        # Vorschau automatisch: jede Einstellung -> kurz warten -> im Hintergrund neu rechnen
        self._pv_gen, self._pv_worker, self._pv_pending = 0, None, False
        self._pv_timer = QTimer(self)
        self._pv_timer.setSingleShot(True)
        self._pv_timer.setInterval(350)
        self._pv_timer.timeout.connect(self._preview)
        for sig in (self.cmb_shape.currentIndexChanged, self.cmb_single.currentIndexChanged,
                    self.cmb_bcol.currentIndexChanged, self.chk_bleed.toggled,
                    self.cmb_out.currentIndexChanged, self.chk_seams.toggled, self.chk_inner.toggled):
            sig.connect(self._pv_timer.start)
        for sp in (self.spn_corner, self.spn_fw, self.spn_fh, self.spn_sx, self.spn_sy, self.spn_off, self.spn_smooth,
                   self.spn_bleed, self.spn_margin):
            sp.valueChanged.connect(self._pv_timer.start)
        for wdg in self.w.values():
            for name in ("valueChanged", "currentIndexChanged", "toggled"):
                sig = getattr(wdg, name, None)
                if sig is not None:
                    try:
                        sig.connect(self._pv_timer.start)
                    except Exception:
                        pass
        right.addWidget(g3)
        b = QPushButton(tr("Vorschau aktualisieren"))
        b.clicked.connect(self._preview)
        right.addWidget(b)
        note = QLabel(tr("Die Schnittlinie liegt immer innerhalb des Überfüllers. Mit Glättung folgt sie dem Motiv bewusst "
                         "nicht exakt, damit sich die Restfolie entgittern lässt."))
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {theme.MUTED};")
        right.addWidget(note)
        self.chk_all = QCheckBox(tr("Alle Seiten"))
        self.chk_all.setChecked(True)
        right.addWidget(self.chk_all)
        right.addStretch()
        bb = QDialogButtonBox()
        ok = bb.addButton(tr("Erzeugen (neues Fenster)"), QDialogButtonBox.ButtonRole.AcceptRole)
        ok.setDefault(True)
        bb.addButton(tr("Abbrechen"), QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(self._apply)
        bb.rejected.connect(self.reject)
        right.addWidget(bb)
        wrap = QWidget()
        wrap.setLayout(right)
        split_panels(root, left, wrap, 420)
        fit_width(wrap)
        from .. import presets
        last = presets.load_last("cutcontour")
        if last is not None:                     # zuletzt verwendete Einstellungen – Versatz gehört zum alten Motiv
            last.shift_x_mm = last.shift_y_mm = 0.0
            try:
                self._load_settings(last, preview=False)
            except Exception:
                pass
        self._sync()
        self._preview()

    def _load_settings(self, s, preview=True):
        """Felder aus Einstellungen setzen (Preset, zuletzt verwendet)."""
        def pick(cmb, val):
            i = cmb.findData(val)
            if i >= 0:
                cmb.setCurrentIndex(i)
        widgets = [self.cmb_shape, self.cmb_single, self.cmb_out, self.cmb_bcol, self.cmb_dpi, self.chk_seams,
                   self.chk_bleed, self.chk_inner, self.spn_corner, self.spn_fw, self.spn_fh, self.spn_sx, self.spn_sy,
                   self.spn_off, self.spn_smooth, self.spn_bleed, self.spn_stroke, self.spn_margin, self.ed_spot,
                   *self.w.values()]
        for wd in widgets:
            wd.blockSignals(True)
        try:
            pick(self.cmb_shape, s.shape)
            pick(self.cmb_single, self._placement(s))
            pick(self.cmb_out, bool(s.per_object))
            pick(self.cmb_dpi, int(s.dpi))
            self.spn_corner.setValue(s.corner_mm)
            self.spn_fw.setValue(s.width_mm)
            self.spn_fh.setValue(s.height_mm)
            self.spn_sx.setValue(s.shift_x_mm)
            self.spn_sy.setValue(s.shift_y_mm)
            self.spn_off.setValue(s.offset_mm)
            self.spn_smooth.setValue(s.smooth_mm)
            self.spn_bleed.setValue(s.bleed_mm)
            self.chk_bleed.setChecked(bool(s.bleed))
            self.chk_inner.setChecked(bool(s.inner))
            self.chk_seams.setChecked(bool(s.clean_seams))
            if s.bleed_color:
                self._bcol = s.bleed_color
                self._paint_bcol()
                pick(self.cmb_bcol, "fixed")
            else:
                pick(self.cmb_bcol, "auto")
            self.ed_spot.setText(s.spot or "CutContour")
            self.spn_stroke.setValue(s.stroke_pt)
            self.spn_margin.setValue(s.margin_mm)
            d = s.detect
            pick(self.w["mode"], d.mode)
            self.w["tol"].setValue(d.tolerance)
            self.w["min"].setValue(d.min_size_mm)
            if "gap" in self.w:
                self.w["gap"].setValue(d.gap_mm)
            if "margin" in self.w:
                self.w["margin"].setValue(d.margin_mm)
        finally:
            for wd in widgets:
                wd.blockSignals(False)
        self._sync()
        if preview:
            self._pv_timer.start()

    def _paint_bcol(self):
        self.btn_bcol.setStyleSheet(f"background: {self._bcol}; border: 1px solid {theme.MUTED};")

    def _pick_bcol(self):
        from PySide6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(QColor(self._bcol), self, tr("Überfüller-Farbe"))
        if c.isValid():
            self._bcol = c.name()
            self._paint_bcol()
            self.cmb_bcol.setCurrentIndex(max(0, self.cmb_bcol.findData("fixed")))

    def _sync(self, *_):
        on = self.chk_bleed.isChecked()
        self.spn_bleed.setEnabled(on)
        self.cmb_bcol.setEnabled(on)
        self.btn_bcol.setEnabled(on and self.cmb_bcol.currentData() == "fixed")
        shape = self.cmb_shape.currentData()
        contour = shape == "contour"
        self.spn_smooth.setEnabled(contour)
        self.chk_inner.setEnabled(contour)
        self.spn_corner.setEnabled(shape == "rounded")
        for w in (self.spn_fw, self.spn_fh, self.spn_sx, self.spn_sy, self.btn_shift0, self.btn_size0, self.cmb_single):
            w.setEnabled(not contour)
        circle = shape == "circle"
        self.spn_fh.setEnabled(not contour and not circle)     # Kreis: ein Durchmesser
        self.canvas.keep_aspect = circle
        if circle and abs(self.spn_fh.value() - self.spn_fw.value()) > 0.05:
            d = max(self.spn_fw.value(), self.spn_fh.value())
            for sp in (self.spn_fw, self.spn_fh):
                sp.blockSignals(True)
                sp.setValue(d)
                sp.blockSignals(False)
        self.spn_margin.setEnabled(bool(self.cmb_out.currentData()))

    def _settings(self, preview=False):
        s = self.s
        s.shape = self.cmb_shape.currentData()
        place = self.cmb_single.currentData()
        s.fit = "trim" if place == "trim" else "motif"
        s.single_shape = place != "each"
        s.corner_mm = self.spn_corner.value()
        s.scale_pct = 100.0                          # Größe nur noch in mm (Feld bzw. Griffe)
        s.width_mm, s.height_mm = self.spn_fw.value(), self.spn_fh.value()
        if s.shape == "circle" and s.width_mm > 0:
            s.height_mm = s.width_mm                         # Kreis bleibt Kreis
        s.shift_x_mm, s.shift_y_mm = self.spn_sx.value(), self.spn_sy.value()
        s.per_object = bool(self.cmb_out.currentData())
        s.bleed_color = self._bcol if self.cmb_bcol.currentData() == "fixed" else ""
        s.clean_seams = self.chk_seams.isChecked()
        s.offset_mm = self.spn_off.value()
        s.smooth_mm = self.spn_smooth.value()
        s.bleed_mm = self.spn_bleed.value()
        s.bleed = self.chk_bleed.isChecked()
        s.inner = self.chk_inner.isChecked()
        _read_detect(self.w, s.detect)
        s.spot = self.ed_spot.text().strip() or "CutContour"
        s.stroke_pt = self.spn_stroke.value()
        s.dpi = 100 if preview else self.cmb_dpi.currentData()
        s.margin_mm = self.spn_margin.value()
        return s

    @staticmethod
    def _placement(s) -> str:
        if s.shape != "contour" and getattr(s, "fit", "motif") == "trim":
            return "trim"
        return "motif" if s.single_shape else "each"

    def _trim(self):
        """Endformat der aktuellen Seite (Abstände links/unten/rechts/oben in pt) oder None."""
        try:
            from ..layout import page_trims_one
            return page_trims_one(self.doc, self.page)
        except Exception:
            return None

    def _preview(self):
        """Seite im Hauptthread rendern (pdfium, wenige ms), Kontur im Hintergrund rechnen – Fenster bleibt bedienbar."""
        import copy
        if getattr(self, "_closing", False):     # Fenster schließt bzw. Dokument schon zu: keine Vorschau mehr
            return
        if self._pv_worker is not None and self._pv_worker.isRunning():
            self._pv_pending = True              # nach der laufenden Berechnung mit dem neuesten Stand nochmal
            return
        s = copy.deepcopy(self._settings(preview=True))
        try:
            pg = self.norm[self.page]
            try:
                size = pg.get_size()
                rgba = objects.render_rgba(pg, s.dpi)
            finally:
                pg.close()
        except Exception as e:
            self.lbl_info.setText("⚠ " + str(e))
            show_error(self, tr("Vorschau"), e)
            return
        self._pv_gen += 1
        self._pv_rgba, self._pv_size = rgba, size
        self.lbl_info.setText(tr("Berechne Vorschau …"))
        self._pv_worker = _CutWorker(self._pv_gen, s, rgba.copy(), size, self._trim())
        self._pv_worker.done.connect(self._preview_done)
        self._pv_worker.start()

    def _preview_done(self, gen, r, err):
        if getattr(self, "_closing", False):
            return
        if self._pv_pending:                     # Einstellungen haben sich inzwischen geändert -> neu rechnen
            self._pv_pending = False
            QTimer.singleShot(0, self._preview)
            return
        if gen != self._pv_gen:
            return
        if err:
            self.lbl_info.setText("⚠ " + err.splitlines()[0])
            box = QMessageBox(QMessageBox.Icon.Critical, tr("Vorschau"), err.split("\n\n")[0], parent=self)
            box.setDetailedText(err)
            box.exec()
            return
        rgba = self._pv_rgba.copy()
        w, h = self._pv_size
        if r.knockout is not None and r.knockout.shape == rgba.shape[:2]:
            rgba[:, :, 3] = rgba[:, :, 3] * r.knockout      # Hintergrund wie in der Ausgabe ausblenden
        motif = rgba_to_pixmap(rgba)
        layers = [(rgba_to_pixmap(o.bleed_rgba), o.bleed_box) for o in r.objects if o.bleed_rgba is not None]
        layers.append((motif, (0, 0, w, h)))
        x0 = min([0.0] + [o.box[0] for o in r.objects])
        y0 = min([0.0] + [o.box[1] for o in r.objects])
        x1 = max([w] + [o.box[2] for o in r.objects])
        y1 = max([h] + [o.box[3] for o in r.objects])
        # Ansicht auf die neue Seitengröße (inkl. Überfüller) ausrichten
        self.canvas.page_w, self.canvas.page_h = x1 - x0, y1 - y0
        shift = [(pm, (a - x0, b - y0, c - x0, d - y0)) for pm, (a, b, c, d) in layers]
        self.canvas.paths = [[(x - x0, y - y0) for x, y in p] for p, _smooth in r.paths]
        self.canvas.live = (1.0, 1.0, 0.0, 0.0)
        info = tr("{0} Kontur(en) auf dieser Seite").format(len(r.paths))
        if self.cmb_shape.currentData() != "contour" and self.canvas.paths:
            boxes = [(min(x for x, _y in p), min(y for _x, y in p), max(x for x, _y in p), max(y for _x, y in p))
                     for p in self.canvas.paths]
            self.canvas.shape_box = max(boxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))   # größte Form
            self.canvas.on_shape = self._apply_drag
            self.canvas.on_shaping = self._show_drag
            bx = self.canvas.shape_box
            info = tr("Form: {0} × {1} mm").format(fmt_mm((bx[2] - bx[0]) / objects.MM), fmt_mm((bx[3] - bx[1]) / objects.MM))
        else:
            self.canvas.shape_box = None
        self.canvas.set_page(x1 - x0, y1 - y0, shift)
        self.lbl_info.setText(info)

    def _show_drag(self, sx, sy, dx, dy):
        bx = self.canvas.shape_box
        w, h = (bx[2] - bx[0]) * sx / objects.MM, (bx[3] - bx[1]) * sy / objects.MM
        txt = tr("Form: {0} × {1} mm").format(fmt_mm(w), fmt_mm(h))
        if abs(dx) > 0.2 or abs(dy) > 0.2:
            txt += "  ·  " + tr("Versatz: {0} / {1} mm").format(fmt_mm(self.spn_sx.value() + dx / objects.MM),
                                                             fmt_mm(self.spn_sy.value() + dy / objects.MM))
        self.lbl_info.setText(txt)

    def _reset_shape(self):
        for sp in (self.spn_fw, self.spn_fh, self.spn_sx, self.spn_sy):
            sp.blockSignals(True)
            sp.setValue(0)
            sp.blockSignals(False)
        self.canvas.live = (1.0, 1.0, 0.0, 0.0)
        self._pv_timer.start()

    def _apply_drag(self, sx, sy, dx, dy):
        """Griff losgelassen: Größe (B × H) und Versatz in mm in die Felder – Felder und Maus bleiben im Einklang."""
        bx = self.canvas.shape_box
        w, h = (bx[2] - bx[0]) * sx / objects.MM, (bx[3] - bx[1]) * sy / objects.MM
        if self.cmb_shape.currentData() == "circle":
            w = h = max(w, h)
        for sp, v in ((self.spn_fw, w), (self.spn_fh, h), (self.spn_sx, self.spn_sx.value() + dx / objects.MM),
                      (self.spn_sy, self.spn_sy.value() + dy / objects.MM)):
            sp.blockSignals(True)
            sp.setValue(round(max(sp.minimum(), min(sp.maximum(), v)), 1))
            sp.blockSignals(False)
        self._pv_timer.start()

    def _apply(self):
        """Nur den Auftrag beschreiben – gerechnet wird im Hintergrund (eigener Prozess), das Fenster friert nicht ein."""
        from .. import core
        s = self._settings()
        pages = None if self.chk_all.isChecked() else [self.page]
        self.job = ("cutcontour", core.settings_to_dict(s), pages)
        from .. import presets
        presets.save_last("cutcontour", s)
        self.accept()

    def done(self, r):
        self._closing = True                     # verspätete Vorschau-Signale ignorieren (Dokument wird gleich geschlossen)
        if getattr(self, "_pv_timer", None) is not None:
            self._pv_timer.stop()
        w = getattr(self, "_pv_worker", None)
        if w is not None and w.isRunning():
            w.wait(30000)                        # Thread nicht mitten in der Berechnung zerstören
        self.norm.close()
        super().done(r)
