# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Dialog „Variable Daten“: Felder anlegen und mit der Maus platzieren, CSV-Datenquelle, Nummerierung, Vorschau
eines beliebigen Datensatzes. Erzeugt wird im Hintergrund (Auftrag „vdp“), das Ergebnis öffnet sich als Reiter."""
from __future__ import annotations

import copy
import os
from dataclasses import asdict

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QMessageBox, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from .. import vdp
from ..l10n import tr
from . import theme
from .common import fill_combo, fit_width, no_enter_default, split_panels

def kind_text(k: str) -> str:
    return {"text": tr("Text"), "qr": tr("QR-Code"), "code128": "Code 128", "ean13": "EAN-13"}.get(k, k)


class VdpCanvas(QWidget):
    """Seitenvorschau mit Feldkästen; Klick wählt ein Feld, Ziehen verschiebt es."""
    picked = Signal(int)
    moved = Signal(int, float, float)          # Feld, x_mm, y_mm

    def __init__(self):
        super().__init__()
        self.setMinimumSize(420, 520)
        self.pix = None
        self.page_mm = (210.0, 297.0)
        self.fields = []
        self.sel = -1
        self._drag = None

    def _geom(self):
        W, H = self.page_mm
        s = min((self.width() - 20) / W, (self.height() - 20) / H)
        return s, (self.width() - W * s) / 2, (self.height() - H * s) / 2

    def _rect(self, f):
        s, ox, oy = self._geom()
        return QRectF(ox + f.x_mm * s, oy + f.y_mm * s, f.w_mm * s, f.h_mm * s)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.BG))
        s, ox, oy = self._geom()
        W, H = self.page_mm
        if self.pix is not None:
            p.drawPixmap(QRectF(ox, oy, W * s, H * s), self.pix, QRectF(self.pix.rect()))
        else:
            p.fillRect(QRectF(ox, oy, W * s, H * s), QColor("#ffffff"))
        for i, f in enumerate(self.fields):
            col = QColor(theme.ACCENT if i == self.sel else "#ec008c")
            pen = QPen(col, 2 if i == self.sel else 1)
            pen.setStyle(Qt.PenStyle.SolidLine if i == self.sel else Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            r = self._rect(f)
            p.drawRect(r)
            p.drawText(r.topLeft() + QPointF(2, -3), f"{i + 1} {kind_text(f.kind)}")
        p.end()

    def mousePressEvent(self, e):
        pos = e.position()
        hit = next((i for i in reversed(range(len(self.fields))) if self._rect(self.fields[i]).contains(pos)), -1)
        if hit >= 0:
            self.sel = hit
            self.picked.emit(hit)
            f = self.fields[hit]
            self._drag = (hit, pos, f.x_mm, f.y_mm)
        self.update()

    def mouseMoveEvent(self, e):
        if not self._drag:
            return
        i, p0, x0, y0 = self._drag
        s, _ox, _oy = self._geom()
        f = self.fields[i]
        f.x_mm = round(x0 + (e.position().x() - p0.x()) / s, 1)
        f.y_mm = round(y0 + (e.position().y() - p0.y()) / s, 1)
        self.update()

    def mouseReleaseEvent(self, _e):
        if self._drag:
            i = self._drag[0]
            self._drag = None
            f = self.fields[i]
            self.moved.emit(i, f.x_mm, f.y_mm)


class VdpDialog(QDialog):
    def __init__(self, parent, doc, current: int = 0):
        super().__init__(parent)
        self.setWindowTitle(tr("Variable Daten – Passermark"))
        self.resize(1250, 860)
        self.doc = doc
        self.page = min(current, len(doc) - 1)
        self.s = vdp.VdpSettings(fields=[], numbering=vdp.Numbering())
        self.fields: list[vdp.VdpField] = []
        self.cols: list[str] = []
        self.job = None
        self._loading = False

        root = QHBoxLayout(self)
        left = QVBoxLayout()
        self.canvas = VdpCanvas()
        self.canvas.picked.connect(self._select)
        self.canvas.moved.connect(self._moved)
        left.addWidget(self.canvas, 1)
        nav = QHBoxLayout()
        nav.addWidget(QLabel(tr("Seite:")))
        self.spn_page = QSpinBox()
        self.spn_page.setRange(1, len(doc))
        self.spn_page.setValue(self.page + 1)
        self.spn_page.valueChanged.connect(self._page_changed)
        nav.addWidget(self.spn_page)
        nav.addWidget(QLabel(tr("Datensatz:")))
        self.spn_rec = QSpinBox()
        self.spn_rec.setRange(1, 1)
        self.spn_rec.valueChanged.connect(self._refresh)
        nav.addWidget(self.spn_rec)
        self.lbl_rec = QLabel()
        nav.addWidget(self.lbl_rec)
        nav.addStretch()
        left.addLayout(nav)
        self.lbl_info = QLabel()
        self.lbl_info.setWordWrap(True)
        self.lbl_info.setStyleSheet(f"color: {theme.ACCENT};")
        left.addWidget(self.lbl_info)
        # links: Vorschau – kommt unten mit den Einstellungen in einen verschiebbaren Teiler

        right = QVBoxLayout()
        from .presetbar import PresetBar
        self.presetbar = PresetBar(self, "vdp", self._settings, self._load_settings)
        right.addWidget(self.presetbar)
        btn_reset = QPushButton(tr("Alles zurücksetzen"))
        btn_reset.setToolTip(tr("Felder, Datenquelle und Nummerierung auf den Anfang: ein Textfeld mit der Nummer"))
        btn_reset.clicked.connect(self._reset)
        right.addWidget(btn_reset)
        intro = QLabel(tr("So geht’s: 1. Felder anlegen und in der Vorschau an ihren Platz ziehen. 2. Festlegen, was "
                          "drinsteht – eine Nummer, eine Spalte aus einer CSV-Datei oder fester Text. 3. Mit "
                          "„Datensatz“ unter der Vorschau durchblättern. 4. Erzeugen: für jeden Datensatz eine Kopie "
                          "der Seite(n)."))
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {theme.MUTED};")
        right.addWidget(intro)

        # ---------------- 1. Felder ----------------
        g = QGroupBox(tr("1. Felder auf der Seite"))
        v = QVBoxLayout(g)
        self._help(v, tr("Jedes Feld ist ein Kasten auf der Seite. In der Vorschau anklicken zum Auswählen, ziehen "
                         "zum Verschieben."))
        self.lst = QListWidget()
        self.lst.setMaximumHeight(110)
        self.lst.currentRowChanged.connect(self._select)
        v.addWidget(self.lst)
        row = QHBoxLayout()
        for kind in vdp.KINDS:
            b = QPushButton("+ " + kind_text(kind))
            b.setToolTip({"text": tr("Text oder Nummer"), "qr": tr("QR-Code (z. B. Webadresse, Ticketnummer)"),
                          "code128": tr("Strichcode für Buchstaben und Ziffern"),
                          "ean13": tr("Artikelnummer-Strichcode, genau 12 oder 13 Ziffern")}[kind])
            b.clicked.connect(lambda _c=False, k=kind: self._add(k))
            row.addWidget(b)
        b = QPushButton(tr("Feld löschen"))
        b.clicked.connect(self._delete)
        row.addWidget(b)
        v.addLayout(row)

        self.ed_content = QLineEdit()
        self.ed_content.setPlaceholderText("{{nr}}")
        self._field(v, tr("Inhalt des gewählten Feldes"),
                    tr("Fester Text und Platzhalter gemischt, z. B. „Ticket {{nr}}“. {{nr}} = Nummer (siehe 3.), "
                       "{{i}} = 1, 2, 3 …, {{Spaltenname}} = Wert aus der CSV (Doppelklick in der Spaltenliste fügt "
                       "ihn ein)."), self.ed_content)
        row = QHBoxLayout()
        self.spn_x, self.spn_y, self.spn_w, self.spn_h = (QDoubleSpinBox() for _ in range(4))
        for sp, lab in ((self.spn_x, tr("links")), (self.spn_y, tr("oben")), (self.spn_w, tr("Breite")),
                        (self.spn_h, tr("Höhe"))):
            sp.setRange(-2000, 5000)
            sp.setDecimals(1)
            sp.setSuffix(" mm")
            col = QVBoxLayout()
            l_ = QLabel(lab)
            l_.setStyleSheet(f"color: {theme.MUTED};")
            col.addWidget(l_)
            col.addWidget(sp)
            row.addLayout(col)
        self.spn_w.setMinimum(1)
        self.spn_h.setMinimum(1)
        self._field(v, tr("Lage und Größe"), tr("Abstand von der linken oberen Seitenecke, dazu Breite und Höhe des "
                                                "Kastens. Codes werden in den Kasten eingepasst."), row)
        row = QHBoxLayout()
        self.cmb_font = QComboBox()
        for fn in vdp.STD_FONTS:
            self.cmb_font.addItem(fn, fn)
        self.cmb_font.addItem(tr("Schriftdatei …"), "__file__")
        self.cmb_font.activated.connect(self._font_chosen)
        self.spn_size = QDoubleSpinBox()
        self.spn_size.setRange(0, 400)
        self.spn_size.setSuffix(" pt")
        self.btn_color = QPushButton()
        self.btn_color.setFixedWidth(40)
        self.btn_color.setToolTip(tr("Farbe"))
        self.btn_color.clicked.connect(self._pick_color)
        self._color = "#000000"
        row.addWidget(self.cmb_font, 1)
        row.addWidget(self.spn_size)
        row.addWidget(self.btn_color)
        self._field(v, tr("Schrift, Größe, Farbe"), tr("Nur für Textfelder; bei Strichcodes steuert die Größe die "
                                                       "Klarschrift darunter (0 = keine)."), row)
        row = QHBoxLayout()
        self.cmb_align = QComboBox()
        fill_combo(self.cmb_align, [("left", tr("links")), ("center", tr("mittig")), ("right", tr("rechts"))], "left")
        self.cmb_rot = QComboBox()
        fill_combo(self.cmb_rot, [(0, "0°"), (90, "90°"), (180, "180°"), (270, "270°")], 0)
        row.addWidget(self.cmb_align)
        row.addWidget(self.cmb_rot)
        self._field(v, tr("Ausrichtung und Drehung"), tr("Text links/mittig/rechts im Kasten; Drehung des Inhalts "
                                                         "im Kasten (90° = von unten nach oben lesbar)."), row)
        self.ed_pages = QLineEdit()
        self.ed_pages.setPlaceholderText(tr("alle Seiten"))
        self._field(v, tr("Nur auf diesen Seiten der Vorlage"), tr("Leer = auf jeder Seite. Z. B. „1“ oder „1,3-4“ – "
                                                                    "praktisch bei Vorder- und Rückseite."), self.ed_pages)
        self.chk_ph = QCheckBox(tr("Platzhalter {{…}} aus dem PDF als Textfelder übernehmen"))
        self._field(v, "", tr("Steht in der Vorlage z. B. {{Name}}, wird dort der Wert eingesetzt und der "
                              "Platzhaltertext entfernt – dann braucht es dafür kein eigenes Feld."), self.chk_ph)
        right.addWidget(g)

        # ---------------- 2. Daten ----------------
        g = QGroupBox(tr("2. Woher kommen die Daten?"))
        v = QVBoxLayout(g)
        row = QHBoxLayout()
        self.ed_csv = QLineEdit()
        self.ed_csv.setPlaceholderText(tr("keine – nur Nummerierung"))
        self.ed_csv.editingFinished.connect(self._csv_changed)
        b = QPushButton(tr("CSV öffnen …"))
        b.clicked.connect(self._pick_csv)
        b2 = QPushButton(tr("Entfernen"))
        b2.clicked.connect(lambda: (self.ed_csv.clear(), self._csv_changed()))
        row.addWidget(self.ed_csv, 1)
        row.addWidget(b)
        row.addWidget(b2)
        self._field(v, tr("CSV-Datei (Tabelle)"), tr("Eine Zeile = eine Kopie. Die erste Zeile enthält die "
                                                     "Spaltennamen. Aus Excel/LibreOffice: „Speichern unter → CSV“. "
                                                     "Ohne CSV werden nur Nummern erzeugt."), row)
        self.cmb_order = QComboBox()
        fill_combo(self.cmb_order, [
            ("each", tr("Jede Seite bekommt den nächsten Datensatz")),
            ("record", tr("Je Datensatz eine Kopie des ganzen Dokuments")),
            ("page", tr("Je Datensatz eine Kopie – sortiert Seite für Seite"))], "each")
        self._field(v, tr("Wie werden die Datensätze verteilt?"),
                    tr("„Jede Seite …“: Seite 1 bekommt Datensatz 1, Seite 2 Datensatz 2 usw. – bei einer einseitigen "
                       "Vorlage entsteht je Datensatz eine Seite. „Kopie des ganzen Dokuments“: alle Seiten mit "
                       "demselben Datensatz, dann alle Seiten mit dem nächsten (z. B. Vorder- und Rückseite einer "
                       "Karte)."), self.cmb_order)
        self.lst_cols = QListWidget()
        self.lst_cols.setMaximumHeight(80)
        self.lst_cols.itemDoubleClicked.connect(lambda it: self._insert("{{" + it.text() + "}}"))
        self._field(v, tr("Platzhalter zum Einfügen"), tr("Doppelklick fügt ihn in den Inhalt des gewählten Feldes "
                                                          "ein."), self.lst_cols)
        self.spn_count = QSpinBox()
        self.spn_count.setRange(1, vdp.MAX_RECORDS)
        self.spn_count.setValue(len(doc) if len(doc) > 1 else 10)
        self._field(v, tr("Anzahl Datensätze (nur ohne CSV)"),
                    tr("Wie viele Nummern erzeugt werden – z. B. 500 für 500 nummerierte Tickets. Am Anfang steht hier "
                       "die Seitenzahl des Dokuments."), self.spn_count)
        self.ed_records = QLineEdit()
        self.ed_records.setPlaceholderText(tr("alle"))
        self._field(v, tr("Nur diese Datensätze"), tr("Leer = alle. Z. B. „1-50“ für einen Probedruck oder "
                                                      "„51-“ für den Rest."), self.ed_records)
        right.addWidget(g)

        # ---------------- 3. Nummerierung ----------------
        g = QGroupBox(tr("3. Nummerierung – was {{nr}} ergibt"))
        v = QVBoxLayout(g)
        row = QHBoxLayout()
        self.spn_start, self.spn_step, self.spn_digits = QSpinBox(), QSpinBox(), QSpinBox()
        self.spn_start.setRange(-10 ** 9, 10 ** 9)
        self.spn_start.setValue(1)
        self.spn_step.setRange(-1000, 1000)
        self.spn_step.setValue(1)
        self.spn_digits.setRange(0, 20)
        for w_, lab in ((self.spn_start, tr("erste Nummer")), (self.spn_step, tr("Schrittweite")),
                        (self.spn_digits, tr("Stellen (mit Nullen)"))):
            col = QVBoxLayout()
            l_ = QLabel(lab)
            l_.setStyleSheet(f"color: {theme.MUTED};")
            col.addWidget(l_)
            col.addWidget(w_)
            row.addLayout(col)
        self._field(v, tr("Zählen"), tr("Beispiel: erste Nummer 1, Schrittweite 1, Stellen 4 → 0001, 0002, 0003 …"),
                    row)
        row = QHBoxLayout()
        self.ed_prefix, self.ed_suffix = QLineEdit(), QLineEdit()
        self.ed_prefix.setPlaceholderText(tr("davor, z. B. A-"))
        self.ed_suffix.setPlaceholderText(tr("danach, z. B. /26"))
        row.addWidget(self.ed_prefix)
        row.addWidget(self.ed_suffix)
        self._field(v, tr("Text vor und nach der Nummer"), tr("Ergibt z. B. A-0001/26."), row)
        self.cmb_check = QComboBox()
        fill_combo(self.cmb_check, [("none", tr("keine Prüfziffer")), ("luhn", tr("Prüfziffer Luhn (Mod 10)")),
                                    ("ean", tr("Prüfziffer GS1/EAN")), ("mod11", tr("Prüfziffer Mod 11"))], "none")
        self._field(v, tr("Prüfziffer"), tr("Hängt eine berechnete Ziffer an, mit der sich Tippfehler erkennen "
                                            "lassen. Für EAN-13 nicht nötig – die rechnet der Strichcode selbst."),
                    self.cmb_check)
        self.chk_rev = QCheckBox(tr("Rückwärts ausgeben"))
        self._field(v, "", tr("Für Abreißblöcke: das oberste Blatt bekommt die höchste Nummer."), self.chk_rev)
        self.ed_cont = QLineEdit()
        self.ed_cont.setPlaceholderText(tr("leer = jedes Mal ab der ersten Nummer"))
        self.lbl_cont = QLabel()
        self.lbl_cont.setStyleSheet(f"color: {theme.ACCENT};")
        self._field(v, tr("Beim nächsten Auftrag weiterzählen"),
                    tr("Einen Namen eingeben (z. B. „Tickets“): Passermark merkt sich, wo dieser Auftrag aufhört, und "
                       "der nächste Auftrag mit demselben Namen zählt dort weiter."), self.ed_cont)
        v.addWidget(self.lbl_cont)
        right.addWidget(g)

        # ---------------- 4. Ausgabe ----------------
        g = QGroupBox(tr("4. Ausgabe"))
        v = QVBoxLayout(g)
        row = QHBoxLayout()
        self.chk_log = QCheckBox(tr("Protokoll schreiben:"))
        self.ed_log = QLineEdit()
        b = QPushButton(tr("Speichern unter…"))
        b.clicked.connect(self._pick_log)
        row.addWidget(self.chk_log)
        row.addWidget(self.ed_log, 1)
        row.addWidget(b)
        self._field(v, tr("Code-Protokoll (CSV)"), tr("Liste aller erzeugten Nummern und Codes je Seite – zum "
                                                      "Nachweis oder Abgleich."), row)
        self._help(v, tr("Mehrere verschiedene Karten auf einem Bogen: das Ergebnis drucken → Weitere Optionen → "
                         "Nutzen → „Je Nutzen die nächste Seite“."))
        right.addWidget(g)
        right.addStretch()
        bb = QDialogButtonBox()
        ok = bb.addButton(tr("Erzeugen (neuer Reiter)"), QDialogButtonBox.ButtonRole.AcceptRole)
        ok.setDefault(True)
        bb.addButton(tr("Abbrechen"), QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(self._apply)
        bb.rejected.connect(self.reject)
        right.addWidget(bb)
        wrap = QWidget()
        wrap.setLayout(right)
        split_panels(root, left, wrap, 560)
        fit_width(wrap)
        no_enter_default(self)

        # Änderungen -> Vorschau (verzögert)
        self._timer = QTimer(self, singleShot=True, interval=350, timeout=self._refresh)
        for w_ in (self.ed_content, self.ed_records, self.ed_prefix, self.ed_suffix, self.ed_pages, self.ed_cont):
            w_.textChanged.connect(self._field_changed)
        for w_ in (self.spn_x, self.spn_y, self.spn_w, self.spn_h, self.spn_size, self.spn_start, self.spn_step,
                   self.spn_digits, self.spn_count):
            w_.valueChanged.connect(self._field_changed)
        for w_ in (self.cmb_align, self.cmb_rot, self.cmb_check, self.cmb_order):
            w_.currentIndexChanged.connect(self._field_changed)
        for w_ in (self.chk_rev, self.chk_ph):
            w_.toggled.connect(self._field_changed)

        sess = getattr(getattr(parent, "ctl", None), "session", None)
        last = getattr(sess, "vdp_last", None) if sess is not None else None
        if last is not None and _fields_of(last):
            self._load_settings(last)
        else:
            self._add("text")
        self._paint_color()

    # -------------------------------------------------------------- #
    def _help(self, layout, text):
        lab = QLabel(text)
        lab.setWordWrap(True)
        lab.setStyleSheet(f"color: {theme.MUTED};")
        layout.addWidget(lab)
        return lab

    def _field(self, layout, title, text, widget):
        """Überschrift, kurze Erklärung, darunter das Eingabeelement."""
        box = QVBoxLayout()
        box.setSpacing(2)
        if title:
            t = QLabel(f"<b>{title}</b>")
            box.addWidget(t)
        if text:
            self._help(box, text)
        if isinstance(widget, QWidget):
            box.addWidget(widget)
        else:
            box.addLayout(widget)
        layout.addSpacing(6)
        layout.addLayout(box)

    def _reset(self):
        self._load_settings(vdp.VdpSettings(fields=[asdict(vdp.VdpField())], numbering=vdp.Numbering()))
        self.spn_count.setValue(len(self.doc) if len(self.doc) > 1 else 10)
        self._remember(None)

    def _remember(self, s):
        """Letzte Einstellungen nur für diese Programmsitzung merken (nach einem Neustart frisch)."""
        sess = getattr(getattr(self.parent(), "ctl", None), "session", None)
        if sess is not None:
            sess.vdp_last = copy.deepcopy(s) if s is not None else None

    def _sel(self) -> int:
        return self.lst.currentRow()

    def _fill_list(self):
        self.lst.blockSignals(True)
        cur = self.lst.currentRow()
        self.lst.clear()
        for i, f in enumerate(self.fields):
            self.lst.addItem(f"{i + 1}. {kind_text(f.kind)}: {f.content}")
        self.lst.setCurrentRow(min(max(cur, 0), len(self.fields) - 1))
        self.lst.blockSignals(False)
        self.canvas.fields = self.fields
        self.canvas.sel = self.lst.currentRow()

    def _add(self, kind):
        W, H = self._page_mm()
        defaults = {"text": ("{{nr}}", 60, 10), "qr": ("{{nr}}", 25, 25), "code128": ("{{nr}}", 50, 15),
                    "ean13": ("4006381333931", 38, 22)}
        content, w, h = defaults[kind]
        n = len(self.fields)
        self.fields.append(vdp.VdpField(kind=kind, content=content, x_mm=min(10 + 5 * n, W - w), y_mm=min(10 + 5 * n, H - h),
                                        w_mm=w, h_mm=h))
        self._fill_list()
        self.lst.setCurrentRow(len(self.fields) - 1)
        self._select(len(self.fields) - 1)
        self._timer.start()

    def _delete(self):
        i = self._sel()
        if 0 <= i < len(self.fields):
            del self.fields[i]
            self._fill_list()
            self._select(self.lst.currentRow())
            self._timer.start()

    def _select(self, i):
        if not (0 <= i < len(self.fields)):
            return
        if self.lst.currentRow() != i:
            self.lst.blockSignals(True)
            self.lst.setCurrentRow(i)
            self.lst.blockSignals(False)
        f = self.fields[i]
        self._loading = True
        try:
            self.ed_content.setText(f.content)
            for sp, v in ((self.spn_x, f.x_mm), (self.spn_y, f.y_mm), (self.spn_w, f.w_mm), (self.spn_h, f.h_mm),
                          (self.spn_size, f.size_pt)):
                sp.setValue(v)
            k = self.cmb_font.findData(f.font)
            if k < 0:
                self.cmb_font.insertItem(self.cmb_font.count() - 1, os.path.basename(f.font), f.font)
                k = self.cmb_font.findData(f.font)
            self.cmb_font.setCurrentIndex(max(0, k))
            self._color = f.color
            self._paint_color()
            self.cmb_align.setCurrentIndex(max(0, self.cmb_align.findData(f.align)))
            self.cmb_rot.setCurrentIndex(max(0, self.cmb_rot.findData(int(f.rotate))))
            self.ed_pages.setText(f.pages)
            text = f.kind == "text"
            for w_ in (self.cmb_font, self.cmb_align):
                w_.setEnabled(text)
        finally:
            self._loading = False
        self.canvas.sel = i
        self.canvas.update()

    def _page_changed(self, v):
        self.page = v - 1
        if (self.cmb_order.currentData() or "each") == "each":      # Seite n zeigt Datensatz n
            self.spn_rec.blockSignals(True)
            self.spn_rec.setMaximum(max(self.spn_rec.maximum(), v))
            self.spn_rec.setValue(v)
            self.spn_rec.blockSignals(False)
        self._refresh()

    def _moved(self, i, x, y):
        if i == self._sel():
            self._loading = True
            self.spn_x.setValue(x)
            self.spn_y.setValue(y)
            self._loading = False
        self._timer.start()

    def _field_changed(self, *_):
        if self._loading:
            return
        i = self._sel()
        if 0 <= i < len(self.fields):
            f = self.fields[i]
            f.content = self.ed_content.text()
            f.x_mm, f.y_mm, f.w_mm, f.h_mm = self.spn_x.value(), self.spn_y.value(), self.spn_w.value(), self.spn_h.value()
            f.font = self.cmb_font.currentData() if self.cmb_font.currentData() != "__file__" else f.font
            f.size_pt = self.spn_size.value()
            f.color = self._color
            f.align = self.cmb_align.currentData() or "left"
            f.rotate = int(self.cmb_rot.currentData() or 0)
            f.pages = self.ed_pages.text().strip()
            item = self.lst.item(i)
            if item is not None:
                item.setText(f"{i + 1}. {kind_text(f.kind)}: {f.content}")
        self.canvas.update()
        self._timer.start()

    def _insert(self, text):
        self.ed_content.insert(text)
        self.ed_content.setFocus()

    def _font_chosen(self, _i):
        if self.cmb_font.currentData() != "__file__":
            self._field_changed()
            return
        p, _ = QFileDialog.getOpenFileName(self, tr("Schriftdatei wählen"), "", tr("Schriften (*.ttf *.TTF)"))
        i = self._sel()
        if p and 0 <= i < len(self.fields):
            self.fields[i].font = p
            self._select(i)
            self._timer.start()
        elif 0 <= i < len(self.fields):
            self._select(i)

    def _paint_color(self):
        self.btn_color.setStyleSheet(f"background: {self._color}; border: 1px solid {theme.MUTED};")

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self._color), self, tr("Farbe"))
        if c.isValid():
            self._color = c.name()
            self._paint_color()
            self._field_changed()

    def _pick_csv(self):
        p, _ = QFileDialog.getOpenFileName(self, tr("CSV-Datei wählen"), "", tr("CSV/Text (*.csv *.txt *.tsv);;Alle (*)"))
        if p:
            self.ed_csv.setText(p)
            self._csv_changed()

    def _pick_log(self):
        p, _ = QFileDialog.getSaveFileName(self, tr("Code-Protokoll speichern"), "codes.csv", tr("CSV (*.csv)"))
        if p:
            self.ed_log.setText(p)
            self.chk_log.setChecked(True)

    def _csv_changed(self):
        p = self.ed_csv.text()
        p = p.strip() if isinstance(p, str) else ""
        self.cols = []
        if p and not os.path.isfile(p):
            QMessageBox.warning(self, tr("CSV"), tr("Datei nicht gefunden: {0}").format(p))
            p = ""
        if p:
            try:
                self.cols, _recs = vdp.read_csv(p)
            except Exception as e:
                QMessageBox.warning(self, tr("CSV"), str(e))
        self.lst_cols.clear()
        self.lst_cols.addItems(["nr", "i"] + self.cols)
        self.spn_count.setEnabled(not p)
        self._timer.start()

    def _page_mm(self):
        w, h = self.doc.get_page_size(self.page)
        return w / vdp.MM, h / vdp.MM

    # -------------------------------------------------------------- #
    def _settings(self) -> vdp.VdpSettings:
        nb = vdp.Numbering(start=self.spn_start.value(), step=self.spn_step.value(), digits=self.spn_digits.value(),
                           prefix=self.ed_prefix.text(), suffix=self.ed_suffix.text(),
                           check=self.cmb_check.currentData() or "none", continue_key=self.ed_cont.text().strip())
        csvp = self.ed_csv.text().strip()
        return vdp.VdpSettings(fields=[asdict(f) for f in self.fields], csv_path=os.path.abspath(csvp) if csvp else "",
                               records=self.ed_records.text().strip(), count=self.spn_count.value(), numbering=nb,
                               order=self.cmb_order.currentData() or "record", reverse=self.chk_rev.isChecked(),
                               log_path=(os.path.abspath(self.ed_log.text().strip())
                                         if self.chk_log.isChecked() and self.ed_log.text().strip() else ""),
                               placeholders=self.chk_ph.isChecked())

    def _load_settings(self, s):
        self._loading = True
        try:
            self.fields = _fields_of(s)
            nb = s.numbering if isinstance(s.numbering, vdp.Numbering) else vdp.Numbering(**(s.numbering or {}))
            self.spn_start.setValue(nb.start)
            self.spn_step.setValue(nb.step)
            self.spn_digits.setValue(nb.digits)
            self.ed_prefix.setText(nb.prefix)
            self.ed_suffix.setText(nb.suffix)
            self.cmb_check.setCurrentIndex(max(0, self.cmb_check.findData(nb.check)))
            self.ed_cont.setText(nb.continue_key)
            self.ed_csv.setText(s.csv_path if s.csv_path and os.path.isfile(s.csv_path) else "")
            self.ed_records.setText(s.records)
            self.spn_count.setValue(max(1, int(s.count)))
            self.cmb_order.setCurrentIndex(max(0, self.cmb_order.findData(s.order)))
            self.chk_rev.setChecked(bool(s.reverse))
            self.chk_ph.setChecked(bool(s.placeholders))
            self.ed_log.setText(s.log_path)
            self.chk_log.setChecked(bool(s.log_path))
        finally:
            self._loading = False
        self._csv_changed()
        self._fill_list()
        if self.fields:
            self.lst.setCurrentRow(0)
            self._select(0)
        self._timer.start()

    def _refresh(self, *_):
        """Vorschau: aktuelle Seite mit dem gewählten Datensatz, echt erzeugt (wie beim Druck)."""
        key = self.ed_cont.text().strip()
        if key:
            nxt = vdp.counter_state().get(key)
            self.lbl_cont.setText(tr("Zähler „{0}“ steht bei {1}.").format(key, nxt) if nxt is not None
                                  else tr("Zähler „{0}“ ist neu – beginnt bei der ersten Nummer.").format(key))
        else:
            self.lbl_cont.setText("")
        if (self.cmb_order.currentData() or "each") == "each":
            # jede Seite ein Datensatz: der Datensatz bestimmt, welche Seite gezeigt wird
            pg = (self.spn_rec.value() - 1) % len(self.doc)
            if pg != self.page:
                self.page = pg
                self.spn_page.blockSignals(True)
                self.spn_page.setValue(pg + 1)
                self.spn_page.blockSignals(False)
        W, H = self._page_mm()
        self.canvas.page_mm = (W, H)
        self.canvas.fields = self.fields
        try:
            s = self._settings()
            s.log_path = ""
            doc, n = vdp.preview(self.doc, self.page, s, self.spn_rec.value() - 1)
            self.spn_rec.blockSignals(True)
            self.spn_rec.setMaximum(max(1, n))
            self.spn_rec.blockSignals(False)
            self.lbl_rec.setText(tr("von {0}").format(n))
            try:
                pg = doc[0]
                scale = 900 / max(pg.get_size())
                img = pg.render(scale=scale, fill_color=(255, 255, 255, 255)).to_pil().convert("RGB")
                pg.close()
            finally:
                doc.close()
            data = img.tobytes("raw", "RGB")
            qi = QImage(data, img.width, img.height, 3 * img.width, QImage.Format.Format_RGB888).copy()
            self.canvas.pix = QPixmap.fromImage(qi)
            self.lbl_info.setText("")
        except Exception as e:
            self.lbl_info.setText("⚠ " + str(e))
        self.canvas.update()

    def _apply(self):
        s = self._settings()
        if not s.fields and not s.placeholders:
            QMessageBox.information(self, tr("Variable Daten"), tr("Bitte mindestens ein Feld anlegen."))
            return
        try:
            _cols, recs = vdp.records(copy.deepcopy(s))
        except Exception as e:
            QMessageBox.warning(self, tr("Variable Daten"), str(e))
            return
        if not recs:
            QMessageBox.warning(self, tr("Variable Daten"), tr("Keine Datensätze (CSV leer oder Anzahl 0)."))
            return
        from .. import core
        self._remember(s)
        self.job = ("vdp", core.settings_to_dict(s), None)
        self.accept()


def _fields_of(s) -> list:
    out = []
    for f in (s.fields or []):
        if isinstance(f, vdp.VdpField):
            out.append(copy.deepcopy(f))
        elif isinstance(f, dict):
            out.append(vdp.VdpField(**{k: v for k, v in f.items() if k in vdp.VdpField.__dataclass_fields__}))
    return out
