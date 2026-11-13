# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Dialog "Variable data": create fields and place them with the mouse, CSV data source, numbering, preview
of any record. The result is produced in the background (job "vdp") and opens as a tab."""

from __future__ import annotations

import copy
import os
from dataclasses import asdict

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import datakinds, vdp
from ..l10n import tr
from . import theme
from .common import CollapsibleSection, fill_combo, fit_width, no_enter_default, split_panels


def kind_text(k: str) -> str:
    """Display name of a field kind."""
    return {"text": tr("Text"), "qr": tr("QR-Code"), "code128": "Code 128", "ean13": "EAN-13", "image": tr("Bild")}.get(
        k, k
    )


IMAGE_FILTER = "*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.gif *.webp *.pdf"
IMAGE_COLS = ("bild", "foto", "photo", "image", "img", "logo", "datei", "pfad", "file", "path", "kép", "imagen")


class VdpCanvas(QWidget):
    """Page preview with field boxes; a click selects a field, dragging moves it."""

    picked = Signal(int)
    moved = Signal(int, float, float)  # field, x_mm, y_mm

    def __init__(self):
        super().__init__()
        self.setMinimumSize(420, 520)
        self.pix = None
        self.page_mm = (210.0, 297.0)
        self.fields = []
        self.sel = -1
        self.vis = None  # visible field indexes (window of the current page) or None = all
        self.trim = None  # inner frame/trim size (left, top, right, bottom) in mm – None = none
        self.bleed = 0.0  # bleed outside around the inner frame, in mm
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
        if self.trim is not None:
            l, t, r, b = self.trim
            p.setBrush(Qt.BrushStyle.NoBrush)
            pen = QPen(QColor("#2e9e4f"), 1)  # inner frame: trim size/inner distance
            p.setPen(pen)
            p.drawRect(QRectF(ox + l * s, oy + t * s, max(1.0, W - l - r) * s, max(1.0, H - t - b) * s))
            if self.bleed > 0:  # outside: bleed
                pen = QPen(QColor("#e04040"), 1)
                pen.setStyle(Qt.PenStyle.DashLine)
                p.setPen(pen)
                p.drawRect(
                    QRectF(
                        ox + (l - self.bleed) * s,
                        oy + (t - self.bleed) * s,
                        (W - l - r + 2 * self.bleed) * s,
                        (H - t - b + 2 * self.bleed) * s,
                    )
                )
        for i, f in enumerate(self.fields):
            if self.vis is not None and i not in self.vis:
                continue  # the field belongs to a window that does not cover this page
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
        hit = next(
            (
                i
                for i in reversed(range(len(self.fields)))
                if (self.vis is None or i in self.vis) and self._rect(self.fields[i]).contains(pos)
            ),
            -1,
        )
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
    """Dialog "Variable Daten": fields, data source, numbering, output and a live preview."""

    def __init__(self, parent, doc, current: int = 0):
        super().__init__(parent)
        self.setWindowTitle(tr("Variable Daten – Passermark"))
        self.resize(1250, 860)
        self.doc = doc
        self.page = min(current, len(doc) - 1)
        self.s = vdp.VdpSettings(fields=[], numbering=vdp.Numbering())
        self.fields: list[vdp.VdpField] = []
        self.cols: list[str] = []
        self._sample: dict = {}  # first record of the CSV (for mapping/preview)
        self._guess = "text"  # detected kind of the CSV (datakinds.guess_kind)
        self._csv = ""  # chosen CSV (full path) – source for the settings
        self._trims = None  # trim size per page (layout.page_trims), lazily
        self._doc_bleeds = []  # bleed per page (layout.page_doc_bleeds), lazily
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
        # left: preview – goes into a movable splitter with the settings further down

        right = QVBoxLayout()
        from .presetbar import PresetBar

        self.presetbar = PresetBar(self, "vdp", self._settings, self._load_settings)
        right.addWidget(self.presetbar)
        btn_reset = QPushButton(tr("Alles zurücksetzen"))
        btn_reset.setToolTip(tr("Felder, Datenquelle und Nummerierung auf den Anfang: ein Textfeld mit der Nummer"))
        btn_reset.clicked.connect(self._reset)
        right.addWidget(btn_reset)
        self.chk_help = QCheckBox(tr("Hilfetexte anzeigen"))
        self.chk_help.setToolTip(
            tr("Zeigt die Erklärungen unter den Feldern an – sonst stehen sie als Tooltip an jedem Feld.")
        )
        self._helps: list[QLabel] = []
        self.chk_help.toggled.connect(self._toggle_help)
        right.addWidget(self.chk_help)
        intro = CollapsibleSection(tr("Anleitung"), expanded=False)
        intro_lbl = QLabel(
            tr(
                "So geht’s: 1. Felder anlegen und in der Vorschau an ihren Platz ziehen. 2. Festlegen, was "
                "drinsteht – eine Nummer, eine Spalte aus einer CSV-Datei oder fester Text. 3. Mit "
                "„Datensatz“ unter der Vorschau durchblättern. 4. Erzeugen: für jeden Datensatz eine Kopie "
                "der Seite(n)."
            )
        )
        intro_lbl.setWordWrap(True)
        intro_lbl.setStyleSheet(f"color: {theme.MUTED};")
        intro.body_layout.addWidget(intro_lbl)
        right.addWidget(intro)

        # ---------------- 1. fields ----------------
        g = CollapsibleSection(tr("1. Felder auf der Seite"), expanded=True)
        right.addWidget(g)
        v = g.body_layout
        self._help(
            v,
            tr(
                "Jedes Feld liegt in einem Fenster, und jedes Fenster gilt für bestimmte Seiten der "
                "Vorlage – z. B. Namen auf den ungeraden (Vorderseiten), QR-Code auf den geraden "
                "(Rückseiten)."
            ),
            register=True,
        )
        self.windows: list[vdp.VdpWindow] = [vdp.VdpWindow()]
        self.win = 0  # active window
        self._win_pending = False  # "Seitenbereich …" chosen but nothing typed yet
        row_w = QHBoxLayout()
        self.cmb_win = QComboBox()
        self.cmb_win.currentIndexChanged.connect(self._win_changed)
        row_w.addWidget(self.cmb_win, 1)
        b = QPushButton("+ " + tr("Fenster"))
        b.setToolTip(tr("Weiteres Fenster anlegen – z. B. Vorderseiten (Name), Rückseiten (QR-Code)"))
        b.clicked.connect(self._win_add)
        row_w.addWidget(b)
        self.btn_win_del = QPushButton("−")
        self.btn_win_del.setToolTip(tr("Aktuelles Fenster entfernen – seine Felder wandern ins erste Fenster"))
        self.btn_win_del.clicked.connect(self._win_del)
        row_w.addWidget(self.btn_win_del)
        self._field(
            v,
            tr("Fenster (Seitengruppen)"),
            tr(
                "Jedes Fenster legt fest, auf welchen Seiten der Vorlage seine Felder stehen. „Alle "
                "Seiten“ ist die Grundschicht und gilt überall (z. B. der Name der Veranstaltung auf "
                "jeder Karte) – weitere Fenster kommen zu ihren Seiten hinzu: ungerade (Vorderseiten), "
                "gerade (Rückseiten) oder ein fester Seitenbereich, der für seine Seiten vor "
                "ungerade/gerade gewinnt."
            ),
            row_w,
        )
        row_p = QHBoxLayout()
        self.cmb_winpages = QComboBox()
        fill_combo(
            self.cmb_winpages,
            [
                ("", tr("alle Seiten")),
                ("ungerade", tr("ungerade Seiten (Vorderseiten)")),
                ("gerade", tr("gerade Seiten (Rückseiten)")),
                ("bereich", tr("Seitenbereich …")),
            ],
            "",
        )
        self.cmb_winpages.currentIndexChanged.connect(self._win_field_changed)
        self.ed_winpages = QLineEdit()
        self.ed_winpages.setPlaceholderText(tr("z. B. 1,3-5 oder ungerade 1-50"))
        self.ed_winpages.editingFinished.connect(self._win_field_changed)
        row_p.addWidget(self.cmb_winpages, 1)
        row_p.addWidget(self.ed_winpages, 1)
        self._field(v, tr("Seiten dieses Fensters"), "", row_p)
        self.lst = QListWidget()
        self.lst.setMaximumHeight(110)
        self.lst.currentRowChanged.connect(self._select)
        v.addWidget(self.lst)
        row = QHBoxLayout()
        for kind in vdp.KINDS:
            b = QPushButton("+ " + kind_text(kind))
            b.setToolTip(
                {
                    "text": tr("Text oder Nummer"),
                    "qr": tr("QR-Code (z. B. Webadresse, Ticketnummer)"),
                    "code128": tr("Strichcode für Buchstaben und Ziffern"),
                    "ean13": tr("Artikelnummer-Strichcode, genau 12 oder 13 Ziffern"),
                    "image": tr(
                        "Bild aus einer Datei (PNG, JPG, TIFF, PDF …) – der Pfad kommt meist aus einer "
                        "CSV-Spalte, z. B. {{Foto}}"
                    ),
                }[kind]
            )
            b.clicked.connect(lambda _c=False, k=kind: self._add(k))
            row.addWidget(b)
        b = QPushButton(tr("Feld löschen"))
        b.clicked.connect(self._delete)
        row.addWidget(b)
        v.addLayout(row)
        self.cmb_fieldwin = QComboBox()
        self.cmb_fieldwin.currentIndexChanged.connect(self._fieldwin_changed)
        self._field(
            v,
            tr("Fenster des gewählten Feldes"),
            tr(
                "Zeigt, zu welchem Fenster das gewählte Feld gehört – hier auswählen, um es in ein anderes "
                "Fenster umzuziehen. Neue Felder landen im Fenster, das oben gerade gewählt ist."
            ),
            self.cmb_fieldwin,
        )

        self.ed_content = QLineEdit()
        self.ed_content.setPlaceholderText("{{nr}}")
        row_c = QHBoxLayout()
        row_c.addWidget(self.ed_content, 1)
        b_vars = QPushButton("?")
        b_vars.setFixedWidth(32)
        b_vars.setToolTip(
            tr("Alle Variablen anzeigen: Datum, Uhrzeit, Seite, Zufallszahl, Spalten … – Doppelklick fügt ein")
        )
        b_vars.clicked.connect(self._show_vars)
        row_c.addWidget(b_vars)
        self._field(
            v,
            tr("Inhalt des gewählten Feldes"),
            tr(
                "Fester Text und Platzhalter gemischt, z. B. „Ticket {{nr}}“. {{nr}} = Nummer (siehe 3.), "
                "{{i}} = 1, 2, 3 …, {{Spaltenname}} = Wert aus der CSV (Doppelklick in der Spaltenliste fügt "
                "ihn ein). „?“ zeigt alle Variablen wie Datum, Seite oder Zufallszahl."
            ),
            row_c,
        )
        self.cmb_qrtype = QComboBox()
        fill_combo(self.cmb_qrtype, [(t, datakinds.qr_type_text(t)) for t in datakinds.QR_TYPES], "text")
        self.cmb_qrtype.currentIndexChanged.connect(self._qrtype_changed)
        self.lbl_qrcols = QLabel()
        self.lbl_qrcols.setWordWrap(True)
        self.lbl_qrcols.setStyleSheet(f"color: {theme.ACCENT};")
        box = QVBoxLayout()
        row_qt = QHBoxLayout()
        row_qt.addWidget(self.cmb_qrtype, 1)
        self.btn_map = QPushButton(tr("Spalten zuordnen …"))
        self.btn_map.setToolTip(
            tr(
                "Festlegen, welche Spalte deiner CSV welche Angabe liefert – nötig, wenn die "
                "Spalten anders heißen, z. B. bei einem Kontakt-Export"
            )
        )
        self.btn_map.clicked.connect(self._map_columns)
        row_qt.addWidget(self.btn_map)
        box.addLayout(row_qt)
        box.addWidget(self.lbl_qrcols)
        self._field(
            v,
            tr("Art des QR-Codes"),
            tr(
                "„Inhalt wie eingegeben“: der Text oben steht im Code. Visitenkarte, WLAN, E-Mail …: Passermark "
                "setzt den Inhalt aus den Spalten der Tabelle zusammen (Tabelle mit „Daten erfassen …“ unter 2. "
                "anlegen)."
            ),
            box,
        )
        self.chk_quiet = QCheckBox(tr("Weißen Rand (Ruhezone) im Feld freihalten – empfohlen"))
        self._field(
            v,
            "",
            tr(
                "Scanner brauchen rund um QR-Code und Code 128 einen hellen Rand. Nur abschalten, wenn "
                "der Rand schon in der Gestaltung vorhanden ist."
            ),
            self.chk_quiet,
        )
        box = QVBoxLayout()
        self.cmb_fit = QComboBox()
        fill_combo(
            self.cmb_fit,
            [
                ("contain", tr("Einpassen – ganzes Bild, Rand bleibt frei")),
                ("cover", tr("Füllen – Kasten voll, Überstand wird abgeschnitten")),
                ("stretch", tr("Verzerren – genau auf den Kasten ziehen")),
            ],
            "contain",
        )
        self.cmb_fit.currentIndexChanged.connect(self._field_changed)
        box.addWidget(self.cmb_fit)
        row_fb = QHBoxLayout()
        self.ed_fallback = QLineEdit()
        self.ed_fallback.setPlaceholderText(tr("kein Ersatzbild – Feld bleibt leer"))
        self.ed_fallback.textChanged.connect(self._field_changed)
        self.btn_fallback = QPushButton(tr("Ersatzbild …"))
        self.btn_fallback.clicked.connect(self._pick_fallback)
        row_fb.addWidget(self.ed_fallback, 1)
        row_fb.addWidget(self.btn_fallback)
        box.addLayout(row_fb)
        self._field(
            v,
            tr("Bild: einpassen und Ersatzbild"),
            tr(
                "Der Inhalt ist der Pfad der Bilddatei, meist aus einer Spalte ({{Foto}}) – absolut oder "
                "relativ zum Ordner der CSV, ohne Endung wird .png/.jpg/.pdf … gesucht. PDF-Bilder (erste "
                "Seite) bleiben Vektor. Das Ersatzbild kommt, wenn die Spalte leer ist oder die Datei fehlt; "
                "ohne Ersatzbild meldet „Daten prüfen“ jede fehlende Datei samt CSV-Zeile und das Erzeugen "
                "bricht ab. Ausrichtung links/mittig/rechts gilt auch für Bilder."
            ),
            box,
        )
        row = QHBoxLayout()
        self.spn_x, self.spn_y, self.spn_w, self.spn_h = (QDoubleSpinBox() for _ in range(4))
        for sp, lab in (
            (self.spn_x, tr("links")),
            (self.spn_y, tr("oben")),
            (self.spn_w, tr("Breite")),
            (self.spn_h, tr("Höhe")),
        ):
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
        self._field(
            v,
            tr("Lage und Größe"),
            tr(
                "Abstand von der linken oberen Seitenecke, dazu Breite und Höhe des "
                "Kastens. Codes werden in den Kasten eingepasst."
            ),
            row,
        )
        row_i = QHBoxLayout()
        self.spn_inner = QDoubleSpinBox()
        self.spn_inner.setRange(0, 100)
        self.spn_inner.setDecimals(1)
        self.spn_inner.setSuffix(" mm")
        self.spn_inner.valueChanged.connect(self._update_boxes)
        row_i.addWidget(self.spn_inner)
        row_i.addStretch()
        self._field(
            v,
            tr("Innenrahmen (Hilfslinie)"),
            tr(
                "Vorschau: grüner Rahmen = deklariertes Endformat (TrimBox), roter gestrichelter Rahmen "
                "außen = Anschnitt (Überfüller). Deklariert die Vorlage beides nicht, zeigt dieser "
                "Abstand einen grünen Hilfsrahmen – nur eine Platzierungshilfe, die nicht mitgedruckt "
                "wird."
            ),
            row_i,
        )
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
        self._field(
            v,
            tr("Schrift, Größe, Farbe"),
            tr("Nur für Textfelder; bei Strichcodes steuert die Größe die Klarschrift darunter (0 = keine)."),
            row,
        )
        row = QHBoxLayout()
        self.cmb_align = QComboBox()
        fill_combo(self.cmb_align, [("left", tr("links")), ("center", tr("mittig")), ("right", tr("rechts"))], "left")
        self.cmb_rot = QComboBox()
        fill_combo(self.cmb_rot, [(0, "0°"), (90, "90°"), (180, "180°"), (270, "270°")], 0)
        row.addWidget(self.cmb_align)
        row.addWidget(self.cmb_rot)
        self._field(
            v,
            tr("Ausrichtung und Drehung"),
            tr("Text links/mittig/rechts im Kasten; Drehung des Inhalts im Kasten (90° = von unten nach oben lesbar)."),
            row,
        )
        self.chk_ph = QCheckBox(tr("Platzhalter {{…}} aus dem PDF als Textfelder übernehmen"))
        self._field(
            v,
            "",
            tr(
                "Steht in der Vorlage z. B. {{Name}}, wird dort der Wert eingesetzt und der "
                "Platzhaltertext entfernt – dann braucht es dafür kein eigenes Feld."
            ),
            self.chk_ph,
        )
        # ---------------- 2. data ----------------
        g = CollapsibleSection(tr("2. Woher kommen die Daten?"), expanded=True)
        right.addWidget(g)
        v = g.body_layout
        row = QHBoxLayout()
        self.ed_csv = QLineEdit()
        self.ed_csv.setPlaceholderText(tr("keine – nur Nummerierung"))
        self.ed_csv.editingFinished.connect(lambda: self._csv_changed())
        b = QPushButton(tr("CSV öffnen …"))
        b.clicked.connect(self._pick_csv)
        b2 = QPushButton(tr("Entfernen"))
        b2.clicked.connect(lambda: (self.ed_csv.clear(), self._csv_changed("")))
        b3 = QPushButton(tr("Daten erfassen …"))
        b3.setToolTip(
            tr("Tabelle direkt in Passermark anlegen oder bearbeiten – Visitenkarten, WLAN, E-Mail, Code 128, EAN-13 …")
        )
        b3.clicked.connect(self._open_data)
        row.addWidget(self.ed_csv, 1)
        row.addWidget(b)
        row.addWidget(b3)
        row.addWidget(b2)
        row_g = QHBoxLayout()
        self.lbl_guess = QLabel()
        self.lbl_guess.setWordWrap(True)
        self.lbl_guess.setStyleSheet(f"color: {theme.ACCENT};")
        self.btn_guess = QPushButton(tr("Passendes Feld anlegen"))
        self.btn_guess.setToolTip(
            tr(
                "Legt das Feld für diese Art an, z. B. einen QR-Code mit Art Visitenkarte – die "
                "Spalten werden automatisch zugeordnet"
            )
        )
        self.btn_guess.setEnabled(False)
        self.btn_guess.clicked.connect(self._use_guess)
        row_g.addWidget(self.lbl_guess, 1)
        row_g.addWidget(self.btn_guess)
        self._field(
            v,
            tr("CSV-Datei (Tabelle)"),
            tr(
                "Eine Zeile = eine Kopie. Die erste Zeile enthält die "
                "Spaltennamen. Aus Excel/LibreOffice: „Speichern unter → CSV“. "
                "Ohne CSV werden nur Nummern erzeugt."
            ),
            row,
        )
        v.addLayout(row_g)
        self.lbl_result = QLabel()
        self.lbl_result.setStyleSheet(f"font-weight: bold; color: {theme.ACCENT};")
        self._field(
            v,
            tr("Ergebnis"),
            tr(
                "Jeder Datensatz bekommt eine eigene Runde über die Seiten der Vorlage – "
                "die Seiten werden entsprechend dupliziert (Vorder- und Rückseite "
                "gehören zum selben Datensatz)."
            ),
            self.lbl_result,
        )
        self.lst_cols = QListWidget()
        self.lst_cols.setMaximumHeight(80)
        self.lst_cols.itemDoubleClicked.connect(lambda it: self._insert("{{" + it.text() + "}}"))
        self._field(
            v,
            tr("Platzhalter zum Einfügen"),
            tr("Doppelklick fügt ihn in den Inhalt des gewählten Feldes ein."),
            self.lst_cols,
        )
        self.spn_count = QSpinBox()
        self.spn_count.setRange(1, vdp.MAX_RECORDS)
        self.spn_count.setValue(len(doc) if len(doc) > 1 else 10)
        self._field(
            v,
            tr("Anzahl Datensätze (nur ohne CSV)"),
            tr(
                "Wie viele Nummern erzeugt werden – z. B. 500 für 500 nummerierte Tickets. Am Anfang steht hier "
                "die Seitenzahl des Dokuments."
            ),
            self.spn_count,
        )
        self.ed_records = QLineEdit()
        self.ed_records.setPlaceholderText(tr("alle"))
        self._field(
            v,
            tr("Nur diese Datensätze"),
            tr("Leer = alle. Z. B. „1-50“ für einen Probedruck oder „51-“ für den Rest."),
            self.ed_records,
        )
        row_o = QHBoxLayout()
        self.cmb_order = QComboBox()
        fill_combo(
            self.cmb_order,
            [
                ("record", tr("Bogen für Bogen: erst alle Seiten mit Datensatz 1")),
                ("page", tr("Seite für Seite: erst Seite 1 mit allen Datensätzen")),
                ("each", tr("Ohne Duplikate: je Datensatz die nächste(n) Seite(n) der Vorlage")),
            ],
            "record",
        )
        self.spn_ppr = QSpinBox()
        self.spn_ppr.setRange(1, 1000)
        self.spn_ppr.setValue(2)
        self.spn_ppr.setEnabled(False)
        self.spn_ppr.valueChanged.connect(self._field_changed)
        self.cmb_order.currentIndexChanged.connect(self._order_changed)
        row_o.addWidget(self.cmb_order, 1)
        row_o.addWidget(QLabel(tr("Seiten je Datensatz:")))
        row_o.addWidget(self.spn_ppr)
        self._field(
            v,
            tr("Erweitert: Sortierung der Ausgabe"),
            tr(
                "„Ohne Duplikate“: die Vorlage wird nicht vervielfältigt – je Datensatz die nächsten "
                "„Seiten je Datensatz“ der Vorlage (2 = Vorder- und Rückseite). Z. B. 10 Kartenseiten, "
                "2 Seiten je Datensatz = 5 Datensätze, Ergebnis 10 Seiten. Die Reihenfolge der Seiten "
                "bleibt sonst unverändert."
            ),
            row_o,
        )
        # ---------------- 3. numbering ----------------
        g = CollapsibleSection(tr("3. Nummerierung – was {{nr}} ergibt"), expanded=True)
        right.addWidget(g)
        v = g.body_layout
        row = QHBoxLayout()
        self.spn_start, self.spn_step, self.spn_digits = QSpinBox(), QSpinBox(), QSpinBox()
        self.spn_start.setRange(-(10**9), 10**9)
        self.spn_start.setValue(1)
        self.spn_step.setRange(-1000, 1000)
        self.spn_step.setValue(1)
        self.spn_digits.setRange(0, 20)
        for w_, lab in (
            (self.spn_start, tr("erste Nummer")),
            (self.spn_step, tr("Schrittweite")),
            (self.spn_digits, tr("Stellen (mit Nullen)")),
        ):
            col = QVBoxLayout()
            l_ = QLabel(lab)
            l_.setStyleSheet(f"color: {theme.MUTED};")
            col.addWidget(l_)
            col.addWidget(w_)
            row.addLayout(col)
        self._field(
            v, tr("Zählen"), tr("Beispiel: erste Nummer 1, Schrittweite 1, Stellen 4 → 0001, 0002, 0003 …"), row
        )
        row = QHBoxLayout()
        self.ed_prefix, self.ed_suffix = QLineEdit(), QLineEdit()
        self.ed_prefix.setPlaceholderText(tr("davor, z. B. A-"))
        self.ed_suffix.setPlaceholderText(tr("danach, z. B. /26"))
        row.addWidget(self.ed_prefix)
        row.addWidget(self.ed_suffix)
        self._field(v, tr("Text vor und nach der Nummer"), tr("Ergibt z. B. A-0001/26."), row)
        self.cmb_check = QComboBox()
        fill_combo(
            self.cmb_check,
            [
                ("none", tr("keine Prüfziffer")),
                ("luhn", tr("Prüfziffer Luhn (Mod 10)")),
                ("ean", tr("Prüfziffer GS1/EAN")),
                ("mod11", tr("Prüfziffer Mod 11")),
            ],
            "none",
        )
        self._field(
            v,
            tr("Prüfziffer"),
            tr(
                "Hängt eine berechnete Ziffer an, mit der sich Tippfehler erkennen "
                "lassen. Für EAN-13 nicht nötig – die rechnet der Strichcode selbst."
            ),
            self.cmb_check,
        )
        self.chk_rev = QCheckBox(tr("Rückwärts ausgeben"))
        self._field(v, "", tr("Für Abreißblöcke: das oberste Blatt bekommt die höchste Nummer."), self.chk_rev)
        self.ed_cont = QLineEdit()
        self.ed_cont.setPlaceholderText(tr("leer = jedes Mal ab der ersten Nummer"))
        self.lbl_cont = QLabel()
        self.lbl_cont.setStyleSheet(f"color: {theme.ACCENT};")
        self._field(
            v,
            tr("Beim nächsten Auftrag weiterzählen"),
            tr(
                "Einen Namen eingeben (z. B. „Tickets“): Passermark merkt sich, wo dieser Auftrag aufhört, und "
                "der nächste Auftrag mit demselben Namen zählt dort weiter."
            ),
            self.ed_cont,
        )
        v.addWidget(self.lbl_cont)

        # ---------------- 4. output ----------------
        g = CollapsibleSection(tr("4. Ausgabe"), expanded=True)
        right.addWidget(g)
        v = g.body_layout
        row = QHBoxLayout()
        self.chk_log = QCheckBox(tr("Protokoll schreiben:"))
        self.ed_log = QLineEdit()
        b = QPushButton(tr("Speichern unter…"))
        b.clicked.connect(self._pick_log)
        row.addWidget(self.chk_log)
        row.addWidget(self.ed_log, 1)
        row.addWidget(b)
        self._field(
            v,
            tr("Code-Protokoll (CSV)"),
            tr("Liste aller erzeugten Nummern und Codes je Seite – zum Nachweis oder Abgleich."),
            row,
        )
        self._help(
            v,
            tr(
                "Mehrere verschiedene Karten auf einem Bogen: das Ergebnis drucken → Druckdialog → "
                "Nutzen (Step & Repeat) → Reihenfolge „Je Nutzen die nächste Seite“."
            ),
            register=True,
        )
        right.addStretch()
        bb = QDialogButtonBox()
        ok = bb.addButton(tr("Erzeugen (neuer Reiter)"), QDialogButtonBox.ButtonRole.AcceptRole)
        ok.setDefault(True)
        chk = bb.addButton(tr("Daten prüfen"), QDialogButtonBox.ButtonRole.ActionRole)
        chk.setToolTip(
            tr(
                "Jeden Datensatz gegen die Felder prüfen: Text zu lang, leere Spalten, unbekannte "
                "Platzhalter, ungültige Codes – mit Zeilennummer der CSV"
            )
        )
        chk.clicked.connect(lambda: self._check_data(ask=False))
        bb.addButton(tr("Abbrechen"), QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(self._apply)
        bb.rejected.connect(self.reject)
        right.addWidget(bb)
        wrap = QWidget()
        wrap.setLayout(right)
        split_panels(root, left, wrap, 560)
        fit_width(wrap)
        no_enter_default(self)

        # changes -> preview (delayed)
        self._timer = QTimer(self, singleShot=True, interval=350, timeout=self._refresh)
        for w_ in (self.ed_content, self.ed_records, self.ed_prefix, self.ed_suffix, self.ed_winpages, self.ed_cont):
            w_.textChanged.connect(self._field_changed)
        for w_ in (
            self.spn_x,
            self.spn_y,
            self.spn_w,
            self.spn_h,
            self.spn_size,
            self.spn_start,
            self.spn_step,
            self.spn_digits,
            self.spn_count,
        ):
            w_.valueChanged.connect(self._field_changed)
        for w_ in (self.cmb_align, self.cmb_rot, self.cmb_check, self.cmb_order):
            w_.currentIndexChanged.connect(self._field_changed)
        for w_ in (self.chk_rev, self.chk_ph, self.chk_quiet):
            w_.toggled.connect(self._field_changed)

        sess = getattr(getattr(parent, "ctl", None), "session", None)
        last = getattr(sess, "vdp_last", None) if sess is not None else None
        if last is not None and _fields_of(last):
            self._load_settings(last)
        else:
            self._add("text")
        self._paint_color()

    # -------------------------------------------------------------- #
    def _toggle_help(self, on: bool):
        """Checkbox "Hilfetexte anzeigen": show/hide all explanations."""
        for lab in self._helps:
            lab.setVisible(on)

    def _help(self, layout, text, register: bool = False):
        lab = QLabel(text)
        lab.setWordWrap(True)
        lab.setStyleSheet(f"color: {theme.MUTED};")
        layout.addWidget(lab)
        if register:  # only the field explanations depend on the switch
            lab.setVisible(self.chk_help.isChecked())
            self._helps.append(lab)
        return lab

    def _field(self, layout, title, text, widget):
        """Heading, explanation (always as a tooltip; visible only with "Hilfetexte anzeigen"),
        below it the input element.
        """
        box = QVBoxLayout()
        box.setSpacing(2)
        if title:
            t = QLabel(f"<b>{title}</b>")
            box.addWidget(t)
        w = widget if isinstance(widget, QWidget) else None
        if text:
            if w is None:  # layout -> wrap in a widget (a tooltip needs one)
                w = QWidget()
                w.setLayout(widget)
            tip = w.toolTip()
            tip = tip if isinstance(tip, str) else ""  # the Qt stand-in in the tests does not return a str
            w.setToolTip(text if not tip else tip + "\n\n" + text)
            self._help(box, text, register=True)
        if w is not None:
            box.addWidget(w)
        else:
            box.addLayout(widget)
        layout.addSpacing(6)
        layout.addLayout(box)

    def _reset(self):
        self._load_settings(vdp.VdpSettings(fields=[asdict(vdp.VdpField())], numbering=vdp.Numbering()))
        self.spn_count.setValue(len(self.doc) if len(self.doc) > 1 else 10)
        self._remember(None)

    def _remember(self, s):
        """Remember the last settings only for this program session (fresh after a restart)."""
        sess = getattr(getattr(self.parent(), "ctl", None), "session", None)
        if sess is not None:
            sess.vdp_last = copy.deepcopy(s) if s is not None else None

    def _sel(self) -> int:
        return self.lst.currentRow()

    def _update_vis(self):
        """Visible fields of the current preview page – same logic as when printing:
        "all pages" (base layer) shows everywhere; among the page entries the
        fixed range wins over odd/even, at equal rank the first window.
        """
        npages = max(1, len(self.doc))
        wins = []
        for w in self.windows:
            p = (w.pages or "").strip()
            pgs = vdp._page_set(p, npages) if p else set(range(npages))
            prec = 0 if not p else (1 if p in ("ungerade", "gerade") else 2)
            wins.append((pgs, prec, list(w.fields or [])))
        best = None
        for i, (pgs, prec, _f) in enumerate(wins):
            if self.page in pgs and prec >= 1 and (best is None or prec > wins[best][1]):
                best = i
        vis = set()
        for i, (pgs, prec, flds) in enumerate(wins):
            if (prec == 0 and pgs) or i == best:
                vis |= {gi for gi, g in enumerate(self.fields) if any(g is x for x in flds)}
        self.canvas.vis = vis or None
        vis = self.canvas.vis
        if vis is not None and self.canvas.sel not in vis and self.canvas.sel >= 0:
            vis_sorted = sorted(vis)
            if vis_sorted:
                self.canvas.sel = vis_sorted[0]

    def _fill_list(self):
        self.lst.blockSignals(True)
        cur = self.lst.currentRow()
        self.lst.clear()
        for i, f in enumerate(self.fields):
            self.lst.addItem(_item_text(i, f, self._field_of(i) if len(self.windows) > 1 else -1))
        self.lst.setCurrentRow(min(max(cur, 0), len(self.fields) - 1))
        self.lst.blockSignals(False)
        self.canvas.fields = self.fields
        self.canvas.sel = self.lst.currentRow()
        self._update_vis()

    def _add(self, kind):
        W, H = self._page_mm()
        defaults = {
            "text": ("{{nr}}", 60, 10),
            "qr": ("{{nr}}", 25, 25),
            "code128": ("{{nr}}", 50, 15),
            "ean13": ("4006381333931", 38, 22),
            "image": ("{{Bild}}", 40, 30),
        }
        content, w, h = defaults[kind]
        if kind == "image":  # guess the column with image paths (Foto, Bild, Logo …)
            col = next((c for c in self.cols if c.strip().lower() in IMAGE_COLS), None) or next(
                (c for c in self.cols if any(k in c.lower() for k in IMAGE_COLS)), None
            )
            if col:
                content = "{{" + col + "}}"
        n = len(self.fields)
        self.fields.append(
            vdp.VdpField(
                kind=kind,
                content=content,
                x_mm=min(10 + 5 * n, W - w),
                y_mm=min(10 + 5 * n, H - h),
                w_mm=w,
                h_mm=h,
                align="center" if kind == "image" else "left",
            )
        )
        self._assign_to_window(len(self.fields) - 1)
        self._fill_list()
        self.lst.setCurrentRow(len(self.fields) - 1)
        self._select(len(self.fields) - 1)
        self._timer.start()

    def _delete(self):
        i = self._sel()
        if 0 <= i < len(self.fields):
            f = self.fields[i]
            del self.fields[i]
            for w_ in self.windows:
                w_.fields = [x for x in (w_.fields or []) if x is not f]
            self._fill_list()
            self._select(self.lst.currentRow())
            self._timer.start()

    # ---------------- windows (page groups) ----------------
    def _order_changed(self, *_):
        """ "Seiten je Datensatz" is only needed with "Ohne Duplikate"."""
        self.spn_ppr.setEnabled((self.cmb_order.currentData() or "") == "each")
        self._field_changed()

    def _win_titles(self):
        out = []
        for i, w in enumerate(self.windows):
            if i == self.win and self._win_pending:
                out.append(tr("Fenster {0}: {1}").format(i + 1, tr("Seitenbereich …")))
                continue
            t = {"": tr("alle Seiten"), "ungerade": tr("ungerade Seiten"), "gerade": tr("gerade Seiten")}.get(
                (w.pages or "").strip()
            )
            if t is None:
                t = (w.pages or "").strip() or tr("alle Seiten")
            out.append(tr("Fenster {0}: {1}").format(i + 1, t))
        return out

    def _win_refresh(self):
        """Update the window row; the field list shows the window identifier as well."""
        self.cmb_win.blockSignals(True)
        self.cmb_win.clear()
        self.cmb_win.addItems(self._win_titles())
        self.cmb_win.setCurrentIndex(min(self.win, len(self.windows) - 1))
        self.cmb_win.blockSignals(False)
        self.btn_win_del.setEnabled(len(self.windows) > 1)
        w = self.windows[self.win]
        p = (w.pages or "").strip()
        if not self._win_pending:  # do not reset while the user is typing the range
            self.cmb_winpages.blockSignals(True)
            self.cmb_winpages.setCurrentIndex(
                max(0, self.cmb_winpages.findData("bereich" if p and p not in ("ungerade", "gerade") else p))
            )
            self.cmb_winpages.blockSignals(False)
            self.ed_winpages.setText("" if p in ("", "ungerade", "gerade") else p)
        self.ed_winpages.setEnabled(self.cmb_winpages.currentData() == "bereich")
        self._fill_list()
        i = self.lst.currentRow()
        self._fill_fieldwin(self._field_of(i) if 0 <= i < len(self.fields) else -1)

    def _win_changed(self, i):
        if 0 <= i < len(self.windows):
            self.win = i
            self._win_pending = False
            self._win_refresh()
            self._timer.start()

    def _win_add(self):
        self.windows.append(vdp.VdpWindow())
        self.win = len(self.windows) - 1
        self._win_pending = False
        self._win_refresh()

    def _win_del(self):
        if len(self.windows) <= 1:
            return
        gone = self.windows.pop(self.win)
        for f in gone.fields or []:
            if not any(f is x for x in (self.windows[0].fields or [])):
                self.windows[0].fields.append(f)
        self.win = 0
        self._win_refresh()
        self._timer.start()

    def _win_field_changed(self, *_):
        w = self.windows[self.win]
        mode = self.cmb_winpages.currentData() or ""
        txt = self.ed_winpages.text().strip()
        if mode == "bereich":
            self._win_pending = not txt  # nothing typed yet → the combo stays on "Seitenbereich …"
            w.pages = txt  # empty = open (counts as "all pages" for now)
        else:
            self._win_pending = False
            w.pages = mode
        self._win_refresh()
        self._timer.start()

    def _fill_fieldwin(self, cur: int = -1):
        """Update the combo "window of the chosen field"; cur = window index that should be selected."""
        self.cmb_fieldwin.blockSignals(True)
        self.cmb_fieldwin.clear()
        for wi, t in enumerate(self._win_titles()):
            self.cmb_fieldwin.addItem(t, wi)
        if 0 <= cur < self.cmb_fieldwin.count():
            self.cmb_fieldwin.setCurrentIndex(cur)
        self.cmb_fieldwin.setEnabled(bool(self.fields))
        self.cmb_fieldwin.blockSignals(False)

    def _fieldwin_changed(self, *_):
        """Move the chosen field to another window."""
        if self._loading:
            return
        i = self._sel()
        wi = self.cmb_fieldwin.currentData()
        if not (0 <= i < len(self.fields)) or not (0 <= wi < len(self.windows)):
            return
        f = self.fields[i]
        for w in self.windows:
            w.fields = [x for x in (w.fields or []) if x is not f]
        self.windows[wi].fields.append(f)
        self._fill_list()
        self._timer.start()

    def _field_of(self, i) -> int:
        # window index of field i – if the field is in no window (special case), it belongs to window 1
        for wi, w in enumerate(self.windows):
            if any(x is self.fields[i] for x in (w.fields or [])):
                return wi
        return 0

    def _assign_to_window(self, i: int):
        # put field i into the active window (out of all other windows)
        f = self.fields[i]
        for w in self.windows:
            w.fields = [x for x in (w.fields or []) if x is not f]
        self.windows[self.win].fields.append(f)

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
            for sp, v in (
                (self.spn_x, f.x_mm),
                (self.spn_y, f.y_mm),
                (self.spn_w, f.w_mm),
                (self.spn_h, f.h_mm),
                (self.spn_size, f.size_pt),
            ):
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
            text = f.kind == "text"
            img = f.kind == "image"
            self.cmb_font.setEnabled(text)
            self.cmb_align.setEnabled(text or img)
            for w_ in (self.spn_size, self.btn_color):
                w_.setEnabled(not img)
            for w_ in (self.cmb_fit, self.ed_fallback, self.btn_fallback):
                w_.setEnabled(img)
            self.cmb_fit.setCurrentIndex(max(0, self.cmb_fit.findData(getattr(f, "fit", "contain") or "contain")))
            self.ed_fallback.setText(getattr(f, "fallback", "") or "")
            self.cmb_qrtype.setCurrentIndex(max(0, self.cmb_qrtype.findData(f.qr_type or "text")))
            self.chk_quiet.setChecked(bool(getattr(f, "quiet", True)))
            self._fill_fieldwin(self._field_of(i))
            self._qr_widgets(f)
        finally:
            self._loading = False
        self.canvas.sel = i
        self.canvas.update()

    def _page_changed(self, v):
        self.page = v - 1
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
            f.x_mm, f.y_mm, f.w_mm, f.h_mm = (
                self.spn_x.value(),
                self.spn_y.value(),
                self.spn_w.value(),
                self.spn_h.value(),
            )
            f.font = self.cmb_font.currentData() if self.cmb_font.currentData() != "__file__" else f.font
            f.size_pt = self.spn_size.value()
            f.color = self._color
            f.align = self.cmb_align.currentData() or "left"
            f.rotate = int(self.cmb_rot.currentData() or 0)
            f.quiet = self.chk_quiet.isChecked()
            f.fit = self.cmb_fit.currentData() or "contain"
            f.fallback = self.ed_fallback.text().strip()
            item = self.lst.item(i)
            if item is not None:
                item.setText(_item_text(i, f, self._field_of(i) if len(self.windows) > 1 else -1))
        self.canvas.update()
        self._timer.start()

    def _qr_widgets(self, f):
        """QR kind only for QR fields; with a kind the content comes from the columns (content row locked)."""
        qr = f.kind == "qr"
        self.cmb_qrtype.setEnabled(qr)
        self.chk_quiet.setEnabled(f.kind in ("qr", "code128"))
        t = (f.qr_type or "text") if qr else "text"
        self.ed_content.setEnabled(t == "text")
        self.btn_map.setEnabled(t != "text")
        if t != "text":
            from .mapdialog import summary

            self.lbl_qrcols.setText(summary(t, self.cols, f.qr_map))
        else:
            self.lbl_qrcols.setText("")

    def _map_columns(self):
        """Map the columns of the CSV to the entries of the QR code (the user's choice goes into the field or preset)."""
        i = self._sel()
        if (
            not (0 <= i < len(self.fields))
            or self.fields[i].kind != "qr"
            or (self.fields[i].qr_type or "text") == "text"
        ):
            return
        f = self.fields[i]
        if not self.cols:
            QMessageBox.information(self, tr("Spalten zuordnen"), tr("Zuerst unter 2. eine CSV-Datei öffnen."))
            return
        from .mapdialog import MapDialog

        dlg = MapDialog(self, f.qr_type, self.cols, f.qr_map, self._sample)
        if dlg.exec():
            self.set_qr_map(i, dlg.result_mapping())

    def set_qr_map(self, i: int, mapping: dict):
        """Store the column mapping of QR field ``i``."""
        if 0 <= i < len(self.fields):
            self.fields[i].qr_map = dict(mapping or {})
            self._qr_widgets(self.fields[i])
            self._timer.start()

    def _qrtype_changed(self, _i):
        if self._loading:
            return
        i = self._sel()
        if 0 <= i < len(self.fields) and self.fields[i].kind == "qr":
            t = self.cmb_qrtype.currentData()
            self.fields[i].qr_type = t if t in datakinds.QR_TYPES else "text"
            self._qr_widgets(self.fields[i])
            item = self.lst.item(i)
            if item is not None:
                item.setText(_item_text(i, self.fields[i], self._field_of(i) if len(self.windows) > 1 else -1))
            self._timer.start()

    def _open_data(self):
        """Create/edit a data table; "verwenden" takes it over together with a matching field."""
        from .datadialog import DataDialog

        cur = self._csv
        kind = next((f.qr_type for f in self.fields if f.kind == "qr" and (f.qr_type or "text") != "text"), "")
        dlg = DataDialog(self, cur, kind)
        if dlg.exec() and dlg.use and dlg.path:
            self.use_data(dlg.path, dlg.kind)

    def use_data(self, path: str, kind: str):
        """Take the table over as the data source and – if there is none yet – create the matching field."""
        from .datadialog import field_for

        self.ed_csv.setText(path)
        self._csv_changed(path)
        W, H = self._page_mm()
        nf = field_for(kind, W, H)
        have = any(
            f.kind == nf.kind
            and (f.qr_type or "text") == (nf.qr_type or "text")
            and (nf.kind == "qr" and nf.qr_type != "text" or f.content == nf.content)
            for f in self.fields
        )
        if not have:
            # replace the untouched start field ({{nr}} text)
            if len(self.fields) == 1 and self.fields[0].kind == "text" and self.fields[0].content == "{{nr}}":
                self.fields = []
                for w_ in self.windows:
                    w_.fields = []
            self.fields.append(nf)
            self._assign_to_window(len(self.fields) - 1)
            self._fill_list()
            self.lst.setCurrentRow(len(self.fields) - 1)
            self._select(len(self.fields) - 1)
        self._timer.start()

    def _insert(self, text):
        """Insert a placeholder; if the field contains only the preset {{nr}}, it is replaced."""
        cur = self.ed_content.text()
        if isinstance(cur, str) and cur.strip() == "{{nr}}" and text != "{{nr}}":
            self.ed_content.setText(text)
        else:
            self.ed_content.insert(text)
        self.ed_content.setFocus()

    def _show_vars(self):
        dlg = VariablesDialog(self, self.cols)
        from .common import responsive

        responsive(dlg)
        dlg.chosen.connect(self._insert)
        dlg.show()

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

    def _pick_fallback(self):
        start = os.path.dirname(self.ed_fallback.text()) or os.path.dirname(self.ed_csv.text().strip())
        p, _ = QFileDialog.getOpenFileName(
            self, tr("Ersatzbild wählen"), start, tr("Bilder") + f" ({IMAGE_FILTER});;" + tr("Alle (*)")
        )
        if p:
            self.ed_fallback.setText(p)

    def _pick_csv(self):
        p, _ = QFileDialog.getOpenFileName(
            self, tr("CSV-Datei wählen"), "", tr("CSV/Text (*.csv *.txt *.tsv);;Alle (*)")
        )
        if p:
            self.ed_csv.setText(p)
            self._csv_changed(p)

    def _pick_log(self):
        p, _ = QFileDialog.getSaveFileName(self, tr("Code-Protokoll speichern"), "codes.csv", tr("CSV (*.csv)"))
        if p:
            self.ed_log.setText(p)
            self.chk_log.setChecked(True)

    def _csv_changed(self, path=None):
        p = self.ed_csv.text() if path is None else path
        p = p.strip() if isinstance(p, str) else ""
        self.cols = []
        self._sample = {}
        if p and not os.path.isfile(p):
            QMessageBox.warning(self, tr("CSV"), tr("Datei nicht gefunden: {0}").format(p))
            p = ""
        if p:
            try:
                self.cols, _recs = vdp.read_csv(p)
                self._sample = dict(_recs[0]) if _recs else {}
            except Exception as e:
                QMessageBox.warning(self, tr("CSV"), str(e))
        self._csv = os.path.abspath(p) if p else ""
        self.lst_cols.clear()
        self.lst_cols.addItems(["nr", "i"] + self.cols)
        self.spn_count.setEnabled(not p)
        self._guess = datakinds.guess_kind(self.cols) if self.cols else "text"
        if self.cols and self._guess != "text":
            self.lbl_guess.setText(tr("Die Tabelle passt zu: {0}").format(datakinds.get(self._guess).title))
            self.btn_guess.setEnabled(True)
        else:
            self.lbl_guess.setText(
                tr(
                    "Art der Tabelle nicht erkannt – Felder selbst anlegen oder beim QR-Feld die "
                    "Art wählen und „Spalten zuordnen …“."
                )
                if self.cols
                else ""
            )
            self.btn_guess.setEnabled(False)
        i = self._sel()
        if 0 <= i < len(self.fields):
            self._qr_widgets(self.fields[i])
        self._timer.start()

    def _use_guess(self):
        """Create a matching field for the detected kind (e.g. QR code with kind business card)."""
        if self._csv and self._guess != "text":
            self.use_data(self._csv, self._guess)

    def _page_mm(self):
        w, h = self.doc.get_page_size(self.page)
        return w / vdp.MM, h / vdp.MM

    def _update_boxes(self, *_):
        """Update the inner frame (green) and bleed (red) of the current page in the preview.
        If the template declares a trim size (TrimBox), it applies together with the bleed (BleedBox);
        otherwise the set distance shows a square helper frame.
        """
        if self._trims is None:
            try:
                from ..layout import page_trims, page_doc_bleeds

                self._trims = page_trims(self.doc) or []
                self._doc_bleeds = page_doc_bleeds(self.doc) or []
            except Exception:
                self._trims, self._doc_bleeds = [], []
        t = self._trims[self.page] if self.page < len(self._trims) else None
        b = self._doc_bleeds[self.page] if self.page < len(self._doc_bleeds) else 0.0
        if t:
            tm = (t[0] / vdp.MM, t[3] / vdp.MM, t[2] / vdp.MM, t[1] / vdp.MM)  # left, top, right, bottom
            self.spn_inner.setEnabled(False)
            self.canvas.bleed = b / vdp.MM
        else:
            m = self.spn_inner.value()
            tm = (m, m, m, m) if m > 0 else None
            self.spn_inner.setEnabled(True)
            self.canvas.bleed = 0.0
        self.canvas.trim = tm
        self.canvas.update()

    # -------------------------------------------------------------- #
    def _settings(self) -> vdp.VdpSettings:
        nb = vdp.Numbering(
            start=self.spn_start.value(),
            step=self.spn_step.value(),
            digits=self.spn_digits.value(),
            prefix=_text(self.ed_prefix),
            suffix=_text(self.ed_suffix),
            check=self.cmb_check.currentData() or "none",
            continue_key=_text(self.ed_cont).strip(),
        )
        log = _text(self.ed_log).strip()
        order = self.cmb_order.currentData()
        order = order if order in ("record", "page", "each") else "record"
        wins = [
            vdp.VdpWindow(pages=(w.pages or "").strip(), fields=[asdict(f) for f in (w.fields or [])])
            for w in self.windows
            if (w.fields or [])
        ] or [vdp.VdpWindow(pages="", fields=[asdict(f) for f in self.fields])]
        return vdp.VdpSettings(
            fields=[asdict(f) for f in self.fields],
            csv_path=self._csv,
            records=_text(self.ed_records).strip(),
            count=self.spn_count.value(),
            numbering=nb,
            order=order,
            pages_per_record=(max(1, self.spn_ppr.value()) if order == "each" else 1),
            windows=wins,
            doc_name=getattr(self.parent(), "display_name", "") or "",
            reverse=bool(self.chk_rev.isChecked()),
            log_path=os.path.abspath(log) if log and self.chk_log.isChecked() else "",
            placeholders=bool(self.chk_ph.isChecked()),
        )

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
            csvp = s.csv_path if s.csv_path and os.path.isfile(s.csv_path) else ""
            self.ed_csv.setText(csvp)
            self.ed_records.setText(s.records)
            self.spn_count.setValue(max(1, int(s.count)))
            self.cmb_order.setCurrentIndex(
                max(
                    0,
                    self.cmb_order.findData(
                        getattr(s, "order", "") if getattr(s, "order", "") in ("record", "page", "each") else "record"
                    ),
                )
            )
            self.spn_ppr.setValue(max(1, int(getattr(s, "pages_per_record", 2) or 2)))
            self.spn_ppr.setEnabled((getattr(s, "order", "") or "") == "each")
            self.chk_rev.setChecked(bool(s.reverse))
            self.chk_ph.setChecked(bool(s.placeholders))
            self.ed_log.setText(s.log_path)
            self.chk_log.setChecked(bool(s.log_path))
        finally:
            self._loading = False
        # take over the windows or migrate from the old format (field pages)
        wins = vdp._windows(s)
        if wins and any((w.fields or []) for w in wins):
            self.windows = []
            for w in wins:
                nw = vdp.VdpWindow(pages=(w.pages or "").strip())
                nw.fields = vdp._fields_of_list(w.fields)
                self.windows.append(nw)
            self.fields = [f for w in self.windows for f in (w.fields or [])]
        else:
            self.windows = [vdp.VdpWindow(pages="", fields=list(self.fields))]
        self.win = 0
        self._csv_changed(csvp)
        self._win_refresh()
        if self.fields:
            self.lst.setCurrentRow(0)
            self._select(0)
        self._timer.start()

    def _refresh(self, *_):
        """Preview: current page with the chosen record, really generated (as when printing)."""
        key = self.ed_cont.text().strip()
        if key:
            nxt = vdp.counter_state().get(key)
            self.lbl_cont.setText(
                tr("Zähler „{0}“ steht bei {1}.").format(key, nxt)
                if nxt is not None
                else tr("Zähler „{0}“ ist neu – beginnt bei der ersten Nummer.").format(key)
            )
        else:
            self.lbl_cont.setText("")
        W, H = self._page_mm()
        self.canvas.page_mm = (W, H)
        self.canvas.fields = self.fields
        self._update_boxes()
        self._update_vis()
        try:
            s = self._settings()
            s.log_path = ""
            doc, n = vdp.preview(self.doc, self.page, s, self.spn_rec.value() - 1)
            self.spn_rec.blockSignals(True)
            self.spn_rec.setMaximum(max(1, n))
            self.spn_rec.blockSignals(False)
            self.lbl_rec.setText(tr("von {0}").format(n))
            info = vdp.output_info(s, len(self.doc), n, len(self.doc))
            self.lbl_result.setText(
                tr("{0} Datensätze → {1} Seiten").format(info["records"], info["pages"])
                + (tr("  –  {0} Seiten ohne Fenster!").format(len(info["uncovered"])) if info["warn"] else "")
                + (
                    tr("  –  {0} Datensatz/Datensätze ohne eigene Seiten").format(info.get("unused", 0))
                    if info.get("unused")
                    else ""
                )
            )
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

    def _check_data(self, ask: bool = False, s=None) -> bool:
        """Show the data check. ask: before generating – True = continue."""
        s = s or self._settings()
        try:
            res = vdp.check(copy.deepcopy(s))
        except Exception as e:  # noqa: BLE001
            if not ask:
                QMessageBox.warning(self, tr("Daten prüfen"), str(e))
            return True
        text = vdp.check_text(res, limit=25)
        if not res["counts"]:
            if not ask:
                QMessageBox.information(self, tr("Daten prüfen"), text)
            return True
        box = QMessageBox(QMessageBox.Icon.Warning, tr("Daten prüfen"), text.split("\n")[0], parent=self)
        box.setDetailedText(text)
        box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        if ask:
            box.setInformativeText(tr("Trotzdem erzeugen?"))
            box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            box.setDefaultButton(QMessageBox.StandardButton.No)
            return box.exec() == QMessageBox.StandardButton.Yes
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()
        return True

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
        if not self._check_data(ask=True, s=s):
            return
        info = vdp.output_info(s, len(self.doc), len(recs), len(self.doc))
        if info["warn"]:
            q = QMessageBox.question(
                self,
                tr("Variable Daten"),
                tr(
                    "Die Vorlage hat {0} Seiten, aber nur {1} davon liegen in einem Fenster. Bei {2} "
                    "Datensätzen würden auch die {3} übrigen Seiten je Datensatz mitkopiert – insgesamt "
                    "{4} Seiten.\n\nTrotzdem erzeugen?"
                ).format(
                    len(self.doc),
                    len(self.doc) - len(info["uncovered"]),
                    info["records"],
                    len(info["uncovered"]),
                    info["pages"],
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if q != QMessageBox.StandardButton.Yes:
                return
        from .. import core

        self._remember(s)
        self.job = ("vdp", core.settings_to_dict(s), None)
        self.accept()


class VariablesDialog(QDialog):
    """All variables with explanation and example value; a double click inserts into the chosen field (stays open)."""

    chosen = Signal(str)

    def __init__(self, parent, cols=()):
        super().__init__(parent)
        self.setWindowTitle(tr("Variablen – Passermark"))
        self.resize(640, 560)
        v = QVBoxLayout(self)
        lab = QLabel(
            tr(
                "Doppelklick fügt die Variable in den Inhalt des gewählten Feldes ein. Fester Text und "
                "Variablen lassen sich mischen, z. B. „Gedruckt am {{datum}} – Karte {{i}} von {{datensaetze}}“."
            )
        )
        lab.setWordWrap(True)
        lab.setStyleSheet(f"color: {theme.MUTED};")
        v.addWidget(lab)
        self.lst = QListWidget()
        self.items = []
        sysv = vdp.system_vars(None, 0)
        for ph, txt in vdp.variables_help():
            if ph == "{{Spaltenname}}":
                for c in cols:
                    self._add("{{" + c + "}}", tr("Spalte der CSV"))
                if not cols:
                    self._add(ph, txt)
                continue
            ex = vdp.fill(ph, {"_sys": sysv}) if "{{" in ph and ph not in ("{{nr}}", "{{i}}") else ""
            ex = (
                ""
                if ex == ph
                or ph
                in ("{{seite}}", "{{seiten}}", "{{vorlagenseite}}", "{{datensatz}}", "{{datensaetze}}", "{{datei}}")
                else ex
            )
            self._add(ph, txt + (f"  →  {ex}" if ex else ""))
        self.lst.itemDoubleClicked.connect(lambda it: self.chosen.emit(self.items[self.lst.row(it)]))
        v.addWidget(self.lst, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.close)
        v.addWidget(bb)

    def _add(self, ph, txt):
        self.items.append(ph)
        self.lst.addItem(f"{ph}    {txt}")


def _text(w) -> str:
    t = w.text()
    return t if isinstance(t, str) else ""


def _item_text(i: int, f, win: int = -1) -> str:
    if f.kind == "qr" and (f.qr_type or "text") != "text":
        t = f"{i + 1}. {kind_text(f.kind)}: {datakinds.qr_type_text(f.qr_type)}"
    else:
        t = f"{i + 1}. {kind_text(f.kind)}: {f.content}"
    return t + (f"  ·  {tr('Fenster')} {win + 1}" if win >= 0 else "")


def _fields_of(s) -> list:
    out = []
    for f in s.fields or []:
        if isinstance(f, vdp.VdpField):
            out.append(copy.deepcopy(f))
        elif isinstance(f, dict):
            out.append(vdp.VdpField(**{k: v for k, v in f.items() if k in vdp.VdpField.__dataclass_fields__}))
    return out
