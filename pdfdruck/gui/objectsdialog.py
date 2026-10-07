# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Dialoge „Objekte trennen“ (Einzelseiten ohne Weißraum) und „CutContour erzeugen“ (Schneideplotter)."""
from __future__ import annotations

import dataclasses
import traceback

from PySide6.QtCore import QPointF, QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QSpinBox, QVBoxLayout, QWidget)

from .. import cutcontour, objects
from ..l10n import tr
from . import theme
from .common import fill_combo, fit_width

MODES = [("auto", "Automatisch"), ("transparent", "Vektor/Transparenz (exakt)"),
         ("color", "Hintergrundfarbe (Scans)")]
SHAPES = [("contour", "Kontur (folgt dem Motiv)"), ("rect", "Rechteck"), ("rounded", "Abgerundetes Rechteck"),
          ("circle", "Kreis"), ("oval", "Oval"), ("hexagon", "Sechseck"), ("octagon", "Achteck"), ("heart", "Herz"),
          ("star", "Stern"), ("shield", "Wappen"), ("arch", "Torbogen")]


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
            p.setPen(QPen(QColor(236, 0, 140), 1.6))
            for poly in self.paths:
                path = QPainterPath(self.to_widget(*poly[0]))
                for x, y in poly[1:]:
                    path.lineTo(self.to_widget(x, y))
                path.closeSubpath()
                p.drawPath(path)
        if self._drag:
            p.setPen(QPen(QColor(theme.ACCENT), 1, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(self._drag[0], self._drag[1]).normalized())

    # Maus/Tastatur ------------------------------------------------------- #
    def mousePressEvent(self, e):
        if not self.editable:
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
        if self._drag:
            self._drag[1] = e.position()
            self.update()

    def mouseReleaseEvent(self, e):
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
        root.addLayout(left, 1)

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
        wrap.setFixedWidth(360)
        root.addWidget(wrap)
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
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.result = objects.separate(self.norm, self.boxes, self.w["margin"].value())
        except Exception as e:
            QApplication.restoreOverrideCursor()
            show_error(self, tr("Fehler"), e)
            return
        QApplication.restoreOverrideCursor()
        self.accept()

    def done(self, r):
        self.norm.close()
        super().done(r)


# --------------------------------------------------------------------------- #
class _CutWorker(QThread):
    """Konturberechnung im Hintergrund (nur numpy/scipy – die Seite wurde vorher im Hauptthread gerendert)."""
    done = Signal(int, object, str)

    def __init__(self, gen, s, rgba, size):
        super().__init__()
        self.gen, self.s, self.rgba, self.size = gen, s, rgba, size

    def run(self):
        try:
            self.done.emit(self.gen, cutcontour.compute(None, self.s, self.rgba, self.size), "")
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
        self.s = cutcontour.CutSettings()
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
        root.addLayout(left, 1)

        right = QVBoxLayout()
        g = QGroupBox(tr("Schnittlinie"))
        f = QFormLayout(g)
        self.cmb_shape = QComboBox()
        fill_combo(self.cmb_shape, SHAPES, self.s.shape)
        f.addRow(tr("Form:"), self.cmb_shape)

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
        self.spn_scale = QDoubleSpinBox()
        self.spn_scale.setRange(5, 500)
        self.spn_scale.setDecimals(1)
        self.spn_scale.setSuffix(" %")
        self.spn_scale.setValue(self.s.scale_pct)
        self.spn_scale.setToolTip(tr("Größe der Form relativ zum Objekt (ohne Überfüller)"))
        f.addRow(tr("Größe:"), self.spn_scale)
        row = QHBoxLayout()
        self.spn_fw, self.spn_fh = dspin(0, 0, 2000), dspin(0, 0, 2000)
        for sp in (self.spn_fw, self.spn_fh):
            sp.setSpecialValueText(tr("auto"))
            sp.setToolTip(tr("Feste Größe der Form; „auto“ = aus dem Objekt (nur eine Angabe: Seitenverhältnis bleibt)"))
        row.addWidget(self.spn_fw)
        row.addWidget(QLabel("×"))
        row.addWidget(self.spn_fh)
        f.addRow(tr("Feste Größe:"), row)
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
        for sig in (self.cmb_shape.currentIndexChanged, self.cmb_bcol.currentIndexChanged, self.chk_bleed.toggled,
                    self.cmb_out.currentIndexChanged, self.chk_seams.toggled, self.chk_inner.toggled):
            sig.connect(self._pv_timer.start)
        for sp in (self.spn_corner, self.spn_scale, self.spn_fw, self.spn_fh, self.spn_off, self.spn_smooth,
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
        wrap.setFixedWidth(380)
        root.addWidget(wrap)
        fit_width(wrap)
        self._sync()
        self._preview()

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
        for w in (self.spn_scale, self.spn_fw, self.spn_fh):
            w.setEnabled(not contour)
        self.spn_margin.setEnabled(bool(self.cmb_out.currentData()))

    def _settings(self, preview=False):
        s = self.s
        s.shape = self.cmb_shape.currentData()
        s.corner_mm = self.spn_corner.value()
        s.scale_pct = self.spn_scale.value()
        s.width_mm, s.height_mm = self.spn_fw.value(), self.spn_fh.value()
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

    def _preview(self):
        """Seite im Hauptthread rendern (pdfium, wenige ms), Kontur im Hintergrund rechnen – Fenster bleibt bedienbar."""
        import copy
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
        self._pv_worker = _CutWorker(self._pv_gen, s, rgba.copy(), size)
        self._pv_worker.done.connect(self._preview_done)
        self._pv_worker.start()

    def _preview_done(self, gen, r, err):
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
        self.canvas.set_page(x1 - x0, y1 - y0, shift)
        self.lbl_info.setText(tr("{0} Kontur(en) auf dieser Seite").format(len(r.paths)))

    def _apply(self):
        s = self._settings()
        pages = None if self.chk_all.isChecked() else [self.page]
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.result, self.count = cutcontour.make(self.doc, s, pages)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            show_error(self, tr("Fehler"), e)
            return
        QApplication.restoreOverrideCursor()
        self.accept()

    def done(self, r):
        if getattr(self, "_pv_timer", None) is not None:
            self._pv_timer.stop()
        w = getattr(self, "_pv_worker", None)
        if w is not None and w.isRunning():
            w.wait(30000)                        # Thread nicht mitten in der Berechnung zerstören
        self.norm.close()
        super().done(r)
