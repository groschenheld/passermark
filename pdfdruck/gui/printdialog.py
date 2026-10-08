# SPDX-License-Identifier: GPL-3.0-or-later
# pdfToolkit – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Eigener Druckdialog (Acrobat-Layout): Einstellungen links, Live-Vorschau rechts."""
from __future__ import annotations

from ..l10n import tr

import os

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog,
                               QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGridLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QRadioButton, QScrollArea, QSpinBox, QStackedWidget,
                               QTabWidget, QVBoxLayout, QWidget)

from .. import config, layout, printers, printjob, proof, trays
from . import theme
from .common import Session, fill_combo, fit_width, guard_wheel, render_pixmap

ROLE_LABELS = [("pagesize", "Papierformat"), ("source", "Papierzufuhr / Fach"),
               ("mediatype", "Medientyp"), ("duplex", "Beidseitig"), ("color", "Farbmodus"),
               ("quality", "Qualität"), ("outputbin", "Ausgabefach")]
FINISH_LABELS = [("saddle", "Sattelheftung / Broschüre"), ("staple", "Heften"), ("punch", "Lochen"),
                 ("fold", "Falzen"), ("trim", "Beschnitt"), ("stacker", "Stapler / Versatz")]


class Preview(QWidget):
    """Zeigt ein ausgeschossenes Blatt in Leserichtung + bedruckbaren Bereich."""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(380, 460)
        self.pixmap = None
        self.sheet = None
        self.landscape = False

    def set_content(self, pixmap, sheet, landscape):
        self.pixmap, self.sheet, self.landscape = pixmap, sheet, landscape
        self.update()

    def paper_rect(self):
        if not self.sheet:
            return QRectF()
        w, h = self.sheet.width, self.sheet.height
        if self.landscape:
            w, h = h, w
        m = 16
        s = min((self.width() - 2 * m) / w, (self.height() - 2 * m) / h)
        pw, ph = w * s, h * s
        return QRectF((self.width() - pw) / 2, (self.height() - ph) / 2, pw, ph)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.VIEW))
        if not self.sheet:
            return
        r = self.paper_rect()
        p.fillRect(r.translated(3, 3), QColor(0, 0, 0, 120))
        p.fillRect(r, Qt.GlobalColor.white)
        if self.pixmap is not None:
            p.drawPixmap(r, self.pixmap, QRectF(self.pixmap.rect()))
        # bedruckbarer Bereich (gestrichelt)
        LW, LH, (x, y, w, h) = layout._logical(self.sheet, self.landscape)
        s = r.width() / LW
        pen = QPen(QColor(theme.ACCENT), 1, Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.drawRect(QRectF(r.left() + x * s, r.top() + (LH - y - h) * s, w * s, h * s))
        p.setPen(QColor(theme.BORDER))
        p.drawRect(r)


class PrintDialog(QDialog):
    def __init__(self, parent, doc, path: str, current: int, session: Session):
        super().__init__(parent)
        self.setWindowTitle(tr("Drucken"))
        self.resize(1180, 760)
        self.doc, self.path, self.current, self.s = doc, path, current, session
        self.cfg = session.cfg
        self.sizes = [doc.get_page_size(i) for i in range(len(doc))]
        self.caps: printers.PrinterCaps | None = None
        self.plans: list[layout.SheetPlan] = []
        self.sheet_index = 0
        self._preview_timer = QTimer(self, singleShot=True, interval=150, timeout=self._update_preview)

        root = QHBoxLayout(self)
        self.tabs = QTabWidget()
        self.tabs.setMinimumWidth(500)
        root.addWidget(self.tabs, 0)
        self.general = QWidget()
        self.tabs.addTab(self._scroll(self.general), tr("Allgemein"))
        self.extras = QWidget()
        self.tabs.addTab(self._scroll(self.extras), tr("Weitere Optionen"))
        self.driver_box = QWidget()
        self.tabs.addTab(self._scroll(self.driver_box), tr("Treiber (alle Optionen)"))

        right = QVBoxLayout()
        root.addLayout(right, 1)
        self.preview = Preview()
        right.addWidget(self.preview, 1)
        nav = QHBoxLayout()
        self.btn_prev = QPushButton("◀")
        self.btn_next = QPushButton("▶")
        self.lbl_sheet = QLabel()
        self.lbl_sheet.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_prev.clicked.connect(lambda: self._goto_sheet(self.sheet_index - 1))
        self.btn_next.clicked.connect(lambda: self._goto_sheet(self.sheet_index + 1))
        nav.addWidget(self.btn_prev)
        nav.addWidget(self.lbl_sheet, 1)
        nav.addWidget(self.btn_next)
        right.addLayout(nav)
        self.lbl_info = QLabel()
        self.lbl_info.setWordWrap(True)
        right.addWidget(self.lbl_info)
        prow = QHBoxLayout()
        self.chk_proof = QCheckBox(tr("Farbwirkung simulieren"))
        self.chk_proof.setChecked(True)
        self.chk_proof.setToolTip(tr("Softproof mit gewähltem Farbprofil (exakt, LittleCMS) und Annäherung an "
                                  "Helligkeit/Kontrast/Sättigung/Graustufen des Treibers. Zum Vergleichen abschalten."))
        self.chk_proof.toggled.connect(lambda _b: self._render_sheet())
        prow.addWidget(self.chk_proof)
        self.lbl_proof = QLabel()
        self.lbl_proof.setWordWrap(True)
        self.lbl_proof.setStyleSheet(f"color: {theme.ACCENT};")
        prow.addWidget(self.lbl_proof, 1)
        right.addLayout(prow)
        self.lbl_warn = QLabel()
        self.lbl_warn.setWordWrap(True)
        self.lbl_warn.setStyleSheet(f"color: {theme.ERROR};")
        right.addWidget(self.lbl_warn)
        bb = QDialogButtonBox()
        self.btn_print = bb.addButton(tr("Drucken"), QDialogButtonBox.ButtonRole.AcceptRole)
        self.btn_print.setDefault(True)
        bb.addButton(tr("Abbrechen"), QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(self._print)
        bb.rejected.connect(self.reject)
        right.addWidget(bb)

        self._build_general()
        self._build_extras()
        fit_width(self)
        self._load_printers()

    @staticmethod
    def _scroll(w):
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sa.setWidget(w)
        return sa

    # ================================================================== #
    # Aufbau "Allgemein"
    # ================================================================== #
    def _build_general(self):
        v = QVBoxLayout(self.general)

        # Drucker
        g = QGroupBox(tr("Drucker"))
        f = QFormLayout(g)
        self.cmb_printer = QComboBox()
        self.cmb_printer.currentIndexChanged.connect(self._printer_changed)
        f.addRow(tr("Name:"), self.cmb_printer)
        self.lbl_pstate = QLabel()
        self.lbl_pstate.setWordWrap(True)
        f.addRow(tr("Status:"), self.lbl_pstate)
        self.lbl_admin = QLabel()
        self.lbl_admin.setWordWrap(True)
        self.lbl_admin.setStyleSheet(f"color: {theme.MUTED};")
        f.addRow(tr("Standards:"), self.lbl_admin)
        self.btn_reset = QPushButton(tr("Auf Admin-Standards zurücksetzen"))
        self.btn_reset.clicked.connect(self._reset_to_admin)
        f.addRow("", self.btn_reset)
        row = QHBoxLayout()
        self.spn_copies = QSpinBox()
        self.spn_copies.setRange(1, 9999)
        self.spn_copies.setValue(self.s.copies)
        self.chk_collate = QCheckBox(tr("Sortieren"))
        self.chk_collate.setChecked(self.s.collate)
        row.addWidget(self.spn_copies)
        row.addWidget(self.chk_collate)
        row.addStretch()
        f.addRow(tr("Kopien:"), row)
        v.addWidget(g)

        # Seiten
        g = QGroupBox(tr("Zu druckende Seiten"))
        gl = QGridLayout(g)
        self.rb_all = QRadioButton(tr("Alle"))
        self.rb_cur = QRadioButton(tr("Aktuelle Seite ({0})").format(self.current + 1))
        self.rb_range = QRadioButton(tr("Seiten:"))
        self.rb_all.setChecked(True)
        self.ed_range = QLineEdit()
        self.ed_range.setPlaceholderText(tr("z. B. 1-3, 5, 8-{0}").format(len(self.doc)))
        self.ed_range.textEdited.connect(lambda _: self.rb_range.setChecked(True))
        self.cmb_subset = QComboBox()
        fill_combo(self.cmb_subset, [("all", tr("Alle Seiten im Bereich")), ("odd", tr("Nur ungerade Seiten")),
                                     ("even", tr("Nur gerade Seiten"))], self.s.subset)
        self.chk_reverse = QCheckBox(tr("Seiten in umgekehrter Reihenfolge"))
        self.chk_reverse.setChecked(self.s.reverse)
        gl.addWidget(self.rb_all, 0, 0)
        gl.addWidget(self.rb_cur, 1, 0)
        gl.addWidget(self.rb_range, 2, 0)
        gl.addWidget(self.ed_range, 2, 1)
        gl.addWidget(self.cmb_subset, 3, 0, 1, 2)
        gl.addWidget(self.chk_reverse, 4, 0, 1, 2)
        v.addWidget(g)

        # Seitengröße und -handhabung
        L = self.s.layout
        g = QGroupBox(tr("Seitengröße und -handhabung"))
        gv = QVBoxLayout(g)
        tog = QHBoxLayout()
        self.handling_btns = {}
        bg = QButtonGroup(self)
        for i, (key, text) in enumerate([("size", tr("Größe")), ("multiple", tr("Mehrere")),
                                         ("booklet", tr("Broschüre")), ("poster", tr("Poster"))]):
            b = QPushButton(text)
            b.setCheckable(True)
            b.setProperty("handling", key)
            b.setProperty("page", i)
            bg.addButton(b)
            tog.addWidget(b)
            self.handling_btns[key] = b
        tog.addStretch()
        gv.addLayout(tog)
        self.stack = QStackedWidget()
        gv.addWidget(self.stack)

        # -- Größe
        pg = QWidget()
        pl = QGridLayout(pg)
        self.rb_fit = QRadioButton(tr("Anpassen"))
        self.rb_actual = QRadioButton(tr("Tatsächliche Größe"))
        self.rb_shrink = QRadioButton(tr("Übergroße Seiten verkleinern"))
        self.rb_custom = QRadioButton(tr("Benutzerdefiniert:"))
        self.cmb_custom_by = QComboBox()
        fill_combo(self.cmb_custom_by, [("percent", tr("Maßstab in %")), ("short", tr("Kurze Kante auf …")),
                                        ("long", tr("Lange Kante auf …"))], L.custom_by)
        self.spn_custom = QDoubleSpinBox()
        self.spn_custom.setRange(1, 1000)
        self.spn_custom.setDecimals(1)
        self.spn_custom.setSuffix(" %")
        self.spn_custom.setValue(L.custom_percent)
        self.spn_custom_mm = QDoubleSpinBox()
        self.spn_custom_mm.setRange(1, 5000)
        self.spn_custom_mm.setDecimals(1)
        self.spn_custom_mm.setSuffix(tr(" mm"))
        self.spn_custom_mm.setValue(L.custom_mm)
        self.lbl_custom = QLabel()
        self.lbl_custom.setWordWrap(True)
        self.lbl_custom.setStyleSheet(f"color: {theme.ACCENT};")
        self.mode_group = QButtonGroup(self)
        for i, (rb, m) in enumerate([(self.rb_fit, "fit"), (self.rb_actual, "actual"),
                                     (self.rb_shrink, "shrink"), (self.rb_custom, "custom")]):
            self.mode_group.addButton(rb)
            rb.setProperty("mode", m)
            rb.setChecked(L.mode == m)
            pl.addWidget(rb, i, 0)
        crow = QHBoxLayout()
        crow.addWidget(self.cmb_custom_by, 1)
        crow.addWidget(self.spn_custom)
        crow.addWidget(self.spn_custom_mm)
        pl.addLayout(crow, 3, 1)
        pl.addWidget(self.lbl_custom, 4, 0, 1, 2)
        self.stack.addWidget(pg)

        # -- Mehrere
        mg = QWidget()
        ml = QFormLayout(mg)
        row = QHBoxLayout()
        self.cmb_nup = QComboBox()
        fill_combo(self.cmb_nup, [(n, str(n)) for n in (2, 4, 6, 8, 9, 16)] + [(0, tr("Benutzerdefiniert"))],
                   0 if (L.cols and L.rows) else (L.nup if L.nup > 1 else 2))
        self.spn_cols = QSpinBox()
        self.spn_cols.setRange(1, 16)
        self.spn_cols.setValue(L.cols or 2)
        self.spn_rows = QSpinBox()
        self.spn_rows.setRange(1, 16)
        self.spn_rows.setValue(L.rows or 2)
        row.addWidget(self.cmb_nup)
        row.addWidget(self.spn_cols)
        row.addWidget(QLabel("×"))
        row.addWidget(self.spn_rows)
        row.addStretch()
        ml.addRow(tr("Seiten pro Blatt:"), row)
        self.cmb_order = QComboBox()
        fill_combo(self.cmb_order, list(layout.ORDERS.items()), L.order)
        ml.addRow(tr("Seitenreihenfolge:"), self.cmb_order)
        row = QHBoxLayout()
        self.cmb_tile = QComboBox()
        fill_combo(self.cmb_tile, [("fit", tr("An Kachel anpassen")), ("actual", tr("Tatsächliche Größe")),
                                   ("custom", tr("Benutzerdefiniert"))], L.tile_mode)
        self.spn_tile = QDoubleSpinBox()
        self.spn_tile.setRange(1, 1000)
        self.spn_tile.setSuffix(" %")
        self.spn_tile.setValue(L.tile_percent)
        row.addWidget(self.cmb_tile)
        row.addWidget(self.spn_tile)
        ml.addRow(tr("Skalierung je Kachel:"), row)
        self.spn_gap = QDoubleSpinBox()
        self.spn_gap.setRange(0, 50)
        self.spn_gap.setSuffix(tr(" mm"))
        self.spn_gap.setValue(L.gap_mm)
        ml.addRow(tr("Abstand:"), self.spn_gap)
        self.chk_borders = QCheckBox(tr("Seitenrand drucken"))
        self.chk_borders.setChecked(L.borders)
        ml.addRow("", self.chk_borders)
        self.stack.addWidget(mg)

        # -- Broschüre
        bw = QWidget()
        bl = QFormLayout(bw)
        self.cmb_bsides = QComboBox()
        fill_combo(self.cmb_bsides, [("both", tr("Beidseitig")), ("front", tr("Nur Vorderseiten")),
                                     ("back", tr("Nur Rückseiten"))], L.booklet_sides)
        bl.addRow(tr("Broschürenseiten:"), self.cmb_bsides)
        self.cmb_binding = QComboBox()
        fill_combo(self.cmb_binding, [("left", tr("Links (normal)")), ("right", tr("Rechts (z. B. Hebräisch/Arabisch)"))],
                   L.booklet_binding)
        bl.addRow(tr("Bindung:"), self.cmb_binding)
        self.ed_bsheets = QLineEdit(L.booklet_sheets)
        self.ed_bsheets.setPlaceholderText(tr("alle – oder z. B. 1-3"))
        bl.addRow(tr("Bögen:"), self.ed_bsheets)
        self.spn_gutter = QDoubleSpinBox()
        self.spn_gutter.setRange(0, 50)
        self.spn_gutter.setSuffix(tr(" mm"))
        self.spn_gutter.setValue(L.booklet_gutter_mm)
        bl.addRow(tr("Bundsteg:"), self.spn_gutter)
        self.lbl_bhint = QLabel()
        self.lbl_bhint.setWordWrap(True)
        self.lbl_bhint.setStyleSheet(f"color: {theme.MUTED};")
        bl.addRow(self.lbl_bhint)
        self.stack.addWidget(bw)

        # -- Poster
        ow = QWidget()
        ol = QFormLayout(ow)
        self.cmb_pmode = QComboBox()
        fill_combo(self.cmb_pmode, [("scale", tr("Maßstab")), ("sheets", tr("Anzahl Blätter")),
                                    ("target", tr("Zielformat"))], L.poster_mode)
        ol.addRow(tr("Größe bestimmen über:"), self.cmb_pmode)
        self.spn_ppct = QDoubleSpinBox()
        self.spn_ppct.setRange(1, 5000)
        self.spn_ppct.setSuffix(" %")
        self.spn_ppct.setValue(L.poster_percent)
        ol.addRow(tr("Maßstab:"), self.spn_ppct)
        row = QHBoxLayout()
        self.spn_pcols = QSpinBox()
        self.spn_pcols.setRange(1, 20)
        self.spn_pcols.setValue(L.poster_cols)
        self.spn_prows = QSpinBox()
        self.spn_prows.setRange(1, 20)
        self.spn_prows.setValue(L.poster_rows)
        row.addWidget(self.spn_pcols)
        row.addWidget(QLabel(tr("breit ×")))
        row.addWidget(self.spn_prows)
        row.addWidget(QLabel(tr("hoch")))
        row.addStretch()
        ol.addRow(tr("Blätter:"), row)
        row = QHBoxLayout()
        self.cmb_ptarget = QComboBox()
        fill_combo(self.cmb_ptarget, [(k, tr("{0} ({1} × {2} mm)").format(k, w, h)) for k, (w, h) in layout.POSTER_FORMATS.items()]
                   + [("custom", tr("Benutzerdefiniert"))], L.poster_target)
        self.spn_ptw = QDoubleSpinBox()
        self.spn_ptw.setRange(10, 5000)
        self.spn_ptw.setSuffix(tr(" mm"))
        self.spn_ptw.setValue(L.poster_target_w_mm)
        self.spn_pth = QDoubleSpinBox()
        self.spn_pth.setRange(10, 5000)
        self.spn_pth.setSuffix(tr(" mm"))
        self.spn_pth.setValue(L.poster_target_h_mm)
        row.addWidget(self.cmb_ptarget)
        row.addWidget(self.spn_ptw)
        row.addWidget(QLabel("×"))
        row.addWidget(self.spn_pth)
        ol.addRow(tr("Zielformat:"), row)
        self.spn_overlap = QDoubleSpinBox()
        self.spn_overlap.setRange(0, 50)
        self.spn_overlap.setSuffix(tr(" mm"))
        self.spn_overlap.setValue(L.poster_overlap_mm)
        ol.addRow(tr("Überlappung:"), self.spn_overlap)
        self.chk_pmarks = QCheckBox(tr("Schnitt-/Klebelinien"))
        self.chk_pmarks.setChecked(L.poster_marks)
        self.chk_plabels = QCheckBox(tr("Beschriftung (Zeile/Spalte, Maßstab)"))
        self.chk_plabels.setChecked(L.poster_labels)
        self.chk_plarge = QCheckBox(tr("Nur große Seiten kacheln"))
        self.chk_plarge.setChecked(L.poster_large_only)
        for c in (self.chk_pmarks, self.chk_plabels, self.chk_plarge):
            ol.addRow("", c)
        self.stack.addWidget(ow)

        # -- gemeinsam
        cf = QFormLayout()
        self.cmb_orient = QComboBox()
        fill_combo(self.cmb_orient, [("auto", tr("Automatisch Hoch-/Querformat")), ("portrait", tr("Hochformat")),
                                     ("landscape", tr("Querformat"))], L.orientation)
        cf.addRow(tr("Ausrichtung:"), self.cmb_orient)
        self.chk_autorot = QCheckBox(tr("Seiten automatisch drehen"))
        self.chk_autorot.setChecked(L.autorotate)
        self.chk_center = QCheckBox(tr("Auf Blatt zentrieren"))
        self.chk_center.setChecked(L.center)
        self.chk_margins = QCheckBox(tr("Nicht bedruckbaren Rand des Druckers berücksichtigen"))
        self.chk_margins.setChecked(L.use_margins)
        for c in (self.chk_autorot, self.chk_center, self.chk_margins):
            cf.addRow("", c)
        gv.addLayout(cf)
        v.addWidget(g)

        hb = self.handling_btns.get(L.handling, self.handling_btns["size"])
        hb.setChecked(True)
        self.stack.setCurrentIndex(hb.property("page"))

        # Papier (wird je Drucker befüllt)
        self.paper_group = QGroupBox(tr("Papier und Ausgabe"))
        self.paper_form = QFormLayout(self.paper_group)
        v.addWidget(self.paper_group)

        # Endverarbeitung (Finisher) – Vorlagen + erkannte Felder; unter Windows Herstellerdialog
        self.finish_group = QGroupBox(tr("Endverarbeitung (Finisher)"))
        self.finish_form = QFormLayout(self.finish_group)
        v.addWidget(self.finish_group)

        # Farbe
        g = QGroupBox(tr("Farbmanagement"))
        f = QFormLayout(g)
        self.cmb_profile = QComboBox()
        self.cmb_intent = QComboBox()
        self.lbl_profile_note = QLabel()
        self.lbl_profile_note.setWordWrap(True)
        self.lbl_profile_note.setStyleSheet(f"color: {theme.MUTED};")
        f.addRow(tr("Ausgabeprofil:"), self.cmb_profile)
        f.addRow(tr("Render-Intent:"), self.cmb_intent)
        f.addRow("", self.lbl_profile_note)
        v.addWidget(g)
        v.addStretch()

        # Signale
        bg.buttonClicked.connect(self._handling_changed)
        for w in (self.rb_all, self.rb_cur, self.rb_range, self.chk_reverse, self.chk_borders,
                  self.chk_autorot, self.chk_center, self.chk_margins):
            w.toggled.connect(self._changed)
        self.mode_group.buttonClicked.connect(self._changed)
        self.ed_range.editingFinished.connect(self._changed)
        self.ed_bsheets.editingFinished.connect(self._changed)
        self.cmb_custom_by.currentIndexChanged.connect(self._changed)
        for w in (self.spn_custom, self.spn_custom_mm, self.spn_cols, self.spn_rows, self.spn_tile, self.spn_gap,
                  self.spn_gutter, self.spn_ppct, self.spn_pcols, self.spn_prows, self.spn_ptw,
                  self.spn_pth, self.spn_overlap):
            w.valueChanged.connect(self._changed)
        for w in (self.cmb_subset, self.cmb_nup, self.cmb_order, self.cmb_tile, self.cmb_orient,
                  self.cmb_bsides, self.cmb_binding, self.cmb_pmode, self.cmb_ptarget):
            w.currentIndexChanged.connect(self._changed)
        for w in (self.chk_pmarks, self.chk_plabels, self.chk_plarge):
            w.toggled.connect(self._changed)
        self.cmb_profile.currentIndexChanged.connect(self._profile_changed)
        self.cmb_intent.currentIndexChanged.connect(self._profile_changed)
        self._sync_enabled()

    def _build_extras(self):
        L = self.s.layout
        v = QVBoxLayout(self.extras)

        g = QGroupBox(tr("Spiegeln"))
        f = QVBoxLayout(g)
        self.chk_mirror_h = QCheckBox(tr("Horizontal spiegeln (z. B. Transferpapier, Bügelfolie, Folienrückseite)"))
        self.chk_mirror_h.setChecked(L.mirror_h)
        self.chk_mirror_v = QCheckBox(tr("Vertikal spiegeln"))
        self.chk_mirror_v.setChecked(L.mirror_v)
        for c in (self.chk_mirror_h, self.chk_mirror_v):
            c.toggled.connect(self._changed)
            f.addWidget(c)
        v.addWidget(g)

        g = QGroupBox(tr("Step && Repeat (Nutzen)"))
        f = QFormLayout(g)
        self.chk_sr = QCheckBox(tr("Jede Seite mehrfach auf ein Blatt montieren"))
        self.chk_sr.setChecked(L.step_repeat)
        f.addRow(self.chk_sr)
        self.cmb_srmode = QComboBox()
        fill_combo(self.cmb_srmode, [("auto", tr("So viele wie aufs Blatt passen")), ("grid", tr("Raster vorgeben"))], L.sr_mode)
        f.addRow(tr("Anzahl:"), self.cmb_srmode)
        row = QHBoxLayout()
        self.spn_srcols = QSpinBox()
        self.spn_srcols.setRange(1, 50)
        self.spn_srcols.setValue(L.sr_cols)
        self.spn_srrows = QSpinBox()
        self.spn_srrows.setRange(1, 50)
        self.spn_srrows.setValue(L.sr_rows)
        row.addWidget(self.spn_srcols)
        row.addWidget(QLabel("×"))
        row.addWidget(self.spn_srrows)
        row.addStretch()
        f.addRow(tr("Spalten × Zeilen:"), row)
        row = QHBoxLayout()
        self.cmb_srby = QComboBox()
        fill_combo(self.cmb_srby, [("percent", tr("Maßstab in %")), ("short", tr("Kurze Kante auf …")),
                                   ("long", tr("Lange Kante auf …"))], L.sr_by)
        self.spn_srpct = QDoubleSpinBox()
        self.spn_srpct.setRange(1, 1000)
        self.spn_srpct.setDecimals(1)
        self.spn_srpct.setSuffix(" %")
        self.spn_srpct.setValue(L.sr_percent)
        self.spn_srmm = QDoubleSpinBox()
        self.spn_srmm.setRange(1, 5000)
        self.spn_srmm.setDecimals(1)
        self.spn_srmm.setSuffix(tr(" mm"))
        self.spn_srmm.setValue(L.sr_mm)
        row.addWidget(self.cmb_srby, 1)
        row.addWidget(self.spn_srpct)
        row.addWidget(self.spn_srmm)
        f.addRow(tr("Nutzengröße:"), row)
        self.lbl_srsize = QLabel()
        self.lbl_srsize.setWordWrap(True)
        self.lbl_srsize.setStyleSheet(f"color: {theme.ACCENT};")
        f.addRow("", self.lbl_srsize)
        self.cmb_srorient = QComboBox()
        fill_combo(self.cmb_srorient, [("auto", tr("Automatisch (passend / meiste Nutzen)")),
                                       ("portrait", tr("Hochformat")), ("landscape", tr("Querformat"))], L.sr_orientation)
        f.addRow(tr("Blatt:"), self.cmb_srorient)
        self.cmb_srrot = QComboBox()
        fill_combo(self.cmb_srrot, [("auto", tr("Automatisch")), ("0", tr("Nicht drehen")), ("90", tr("Um 90° drehen"))],
                   L.sr_rotate)
        f.addRow(tr("Nutzen drehen:"), self.cmb_srrot)
        self.cmb_srjoin = QComboBox()
        fill_combo(self.cmb_srjoin, [("edge", tr("Kante an Kante (ein Schnitt, Anschnitt nur außen)")),
                                     ("bleed", tr("Überfüller an Überfüller")),
                                     ("gap", tr("Mit Abstand"))], L.sr_join)
        f.addRow(tr("Anordnung:"), self.cmb_srjoin)
        self.spn_srgap = QDoubleSpinBox()
        self.spn_srgap.setRange(0, 50)
        self.spn_srgap.setSuffix(tr(" mm"))
        self.spn_srgap.setValue(L.sr_gap_mm)
        f.addRow(tr("Abstand:"), self.spn_srgap)
        note = QLabel(tr("Ersetzt die Seitenhandhabung (Größe/Mehrere/…), solange aktiv. Bei „Automatisch“ wird "
                      "zuerst eine Lage gesucht, in der das Raster aufs Blatt passt, dann die mit den meisten "
                      "Nutzen. Kante an Kante: zwischen den Nutzen kein Weißraum, die Schnittmarken liegen "
                      "nur außen und verlängern die gemeinsamen Schnittkanten."))
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {theme.MUTED};")
        f.addRow(note)
        v.addWidget(g)

        g = QGroupBox(tr("Schnittmarken und Anschnitt"))
        f = QFormLayout(g)
        self.chk_marks = QCheckBox(tr("Schnittmarken drucken"))
        self.chk_marks.setChecked(L.crop_marks)
        f.addRow(self.chk_marks)
        self.spn_bleed = QDoubleSpinBox()
        self.spn_bleed.setRange(0, 20)
        self.spn_bleed.setDecimals(1)
        self.spn_bleed.setSingleStep(0.5)
        self.spn_bleed.setSuffix(tr(" mm"))
        self.spn_bleed.setValue(L.bleed_mm)
        f.addRow(tr("Überfüller / Anschnitt (gespiegelt):"), self.spn_bleed)
        note = QLabel(tr("Erzeugt den Anschnitt durch Spiegeln der Seitenränder nach außen – für Dateien ohne "
                      "Beschnittzugabe. Beim Anpassen wird automatisch Platz für Anschnitt und Marken gelassen; "
                      "Nutzen bekommen mindestens den doppelten Anschnitt als Abstand."))
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {theme.MUTED};")
        f.addRow(note)
        v.addWidget(g)
        v.addStretch()

        for w in (self.chk_sr, self.chk_marks):
            w.toggled.connect(self._changed)
        for w in (self.cmb_srmode, self.cmb_srorient, self.cmb_srrot, self.cmb_srjoin):
            w.currentIndexChanged.connect(self._changed)
        self.cmb_srby.currentIndexChanged.connect(self._changed)
        for w in (self.spn_srcols, self.spn_srrows, self.spn_srpct, self.spn_srmm, self.spn_srgap, self.spn_bleed):
            w.valueChanged.connect(self._changed)

    def _show_admin_info(self, name):
        if name == printers.PDF_TARGET:
            self.lbl_admin.setText(tr("PDF-Ausgabe – alle Layout-Funktionen (N-Up, Broschüre, Poster, Nutzen, "
                                   "Marken, Anschnitt) wirken, Farben bleiben unverändert."))
            return
        pc = self.cfg.get("printers", {}).get(name, {})
        opts = pc.get("options", {})
        parts = []
        for k, v in opts.items():
            o = self.caps.options.get(k) if self.caps else None
            if o:
                parts.append(f"{o.text} = {next((c.text for c in o.choices if c.value == v), v)}")
        dp = self.cfg.get("default_printer", "")
        txt = (tr("Admin: ") + "; ".join(parts)) if parts else tr("Keine eigenen Admin-Werte – es gelten die Standards der CUPS-Queue.")
        if dp and dp != name:
            txt += tr("\n⚠ Admin-Standarddrucker ist „{0}“, gewählt ist „{1}“.").format(dp, name)
        self.lbl_admin.setText(txt)

    def _reset_to_admin(self):
        if not self.caps:
            return
        name = self.caps.name
        self.s.values.pop(name, None)
        self.s.color.pop(name, None)
        self.values = self.s.values_for(name)
        self._build_paper()
        self._build_driver_tab()
        self._build_profiles()
        fit_width(self)
        self._changed()

    def _handling(self) -> str:
        return next((k for k, b in self.handling_btns.items() if b.isChecked()), "size")

    def _handling_changed(self, *_):
        self.stack.setCurrentIndex(self.handling_btns[self._handling()].property("page"))
        self._changed()

    def _sync_enabled(self):
        cust = self.rb_custom.isChecked()
        by = self.cmb_custom_by.currentData()
        self.cmb_custom_by.setEnabled(cust)
        self.spn_custom.setVisible(by == "percent")
        self.spn_custom_mm.setVisible(by != "percent")
        self.spn_custom.setEnabled(cust)
        self.spn_custom_mm.setEnabled(cust)
        self.lbl_custom.setVisible(cust)
        custom_grid = self.cmb_nup.currentData() == 0
        self.spn_cols.setEnabled(custom_grid)
        self.spn_rows.setEnabled(custom_grid)
        self.spn_tile.setEnabled(self.cmb_tile.currentData() == "custom")
        pm = self.cmb_pmode.currentData()
        self.spn_ppct.setEnabled(pm == "scale")
        self.spn_pcols.setEnabled(pm == "sheets")
        self.spn_prows.setEnabled(pm == "sheets")
        self.cmb_ptarget.setEnabled(pm == "target")
        custom_t = pm == "target" and self.cmb_ptarget.currentData() == "custom"
        self.spn_ptw.setEnabled(custom_t)
        self.spn_pth.setEnabled(custom_t)
        if hasattr(self, "chk_sr"):
            sr = self.chk_sr.isChecked()
            grid = self.cmb_srmode.currentData() == "grid"
            for w in (self.cmb_srmode, self.cmb_srby, self.spn_srpct, self.spn_srmm, self.cmb_srorient,
                      self.cmb_srrot, self.cmb_srjoin):
                w.setEnabled(sr)
            by = self.cmb_srby.currentData()
            self.spn_srpct.setVisible(by == "percent")
            self.spn_srmm.setVisible(by != "percent")
            self.lbl_srsize.setVisible(sr)
            self.spn_srgap.setEnabled(sr and self.cmb_srjoin.currentData() == "gap")
            self.spn_srcols.setEnabled(sr and grid)
            self.spn_srrows.setEnabled(sr and grid)
            for b in self.handling_btns.values():
                b.setEnabled(not sr)
        booklet = self._handling() == "booklet"
        self.chk_reverse.setText(tr("Bögen in umgekehrter Reihenfolge") if booklet
                                 else tr("Seiten in umgekehrter Reihenfolge"))
        if booklet and self.caps is not None:
            if self.cmb_bsides.currentData() != "both":
                self.lbl_bhint.setText(tr("Manuell beidseitig: zuerst „Nur Vorderseiten“ drucken, Stapel an der "
                                       "kurzen Kante wenden und wieder einlegen, dann „Nur Rückseiten“."))
            elif self._short_edge_choice():
                self.lbl_bhint.setText(tr("Duplex wird für den Druck automatisch auf „kurze Kante“ gestellt."))
            else:
                self.lbl_bhint.setText(tr("⚠ Kein automatischer Duplex erkannt – „Nur Vorderseiten“/"
                                       "„Nur Rückseiten“ verwenden."))

    # ================================================================== #
    # Drucker
    # ================================================================== #
    def _load_printers(self):
        try:
            plist = printers.list_printers()
        except Exception as e:
            QMessageBox.critical(self, tr("CUPS"), tr("Drucker können nicht abgefragt werden:\n{0}").format(e))
            plist = []
        plist = list(plist) + [printers.pdf_target_info()]      # immer verfügbar: Als PDF speichern
        self.cmb_printer.blockSignals(True)
        for p in plist:
            label = (f"{p.info}  ({p.name})" if p.info != p.name else p.name)
            if p.model:
                label += f"  –  {p.model}"
            self.cmb_printer.addItem(label, p)
        want = self.s.printer or next((p.name for p in plist if p.is_default), None)
        idx = next((i for i, p in enumerate(plist) if p.name == want), 0)
        self.cmb_printer.setCurrentIndex(idx)
        self.cmb_printer.blockSignals(False)
        if plist:
            self._printer_changed(idx)
        else:
            self.btn_print.setEnabled(False)

    def _printer_changed(self, _idx):
        p: printers.PrinterInfo = self.cmb_printer.currentData()
        if p is None:
            return
        if p.name == printers.PDF_TARGET:
            self.lbl_pstate.setText(tr("Speichert das Ergebnis als PDF-Datei – vektoriell, Farben und Farbräume "
                                    "unverändert, kein Farbprofil, keine Druckerränder."))
        else:
            self.lbl_pstate.setText(f"{tr(p.state_text)} – {p.model}" + (f"\n{p.state_message}" if p.state_message else ""))
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.caps = self.s.caps_for(p.name)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, tr("Drucker"), tr("Treiberoptionen nicht lesbar:\n{0}").format(e))
            self.caps = None
            self.btn_print.setEnabled(False)
            return
        QApplication.restoreOverrideCursor()
        self.btn_print.setEnabled(True)
        self.btn_print.setText(tr("Speichern …") if p.name == printers.PDF_TARGET else tr("Drucken"))
        self.spn_copies.setEnabled(p.name != printers.PDF_TARGET)
        self.chk_collate.setEnabled(p.name != printers.PDF_TARGET)
        if hasattr(self, "btn_reset"):
            self.btn_reset.setEnabled(p.name != printers.PDF_TARGET)
        self.s.printer = p.name
        self._show_admin_info(p.name)
        self.values = self.s.values_for(p.name)
        self._build_paper()
        self._build_driver_tab()
        self._build_profiles()
        fit_width(self)
        self._changed()

    def _option_combo(self, key):
        opt = self.caps.options[key]
        cb = QComboBox()
        fill_combo(cb, [(c.value, c.text) for c in opt.choices], self.values.get(key, opt.default))
        cb.setProperty("key", key)
        cb.currentIndexChanged.connect(lambda _i, cb=cb: self._option_changed(cb))
        return cb

    def _build_paper(self):
        while self.paper_form.rowCount():
            self.paper_form.removeRow(0)
        self.role_combos = {}
        for role, label in ROLE_LABELS:
            key = self.caps.roles.get(role)
            if key and key in self.caps.options:
                cb = self._option_combo(key)
                self.role_combos[key] = cb
                drv = self.caps.options[key].text
                label = tr(label)
                text = label if drv.lower() in (label.lower(), key.lower()) else f"{label}\n({drv})"
                self.paper_form.addRow(text + ":", cb)
        if not self.role_combos:
            self.paper_form.addRow(QLabel(tr("Keine Basisoptionen erkannt – siehe Reiter „Treiber“.")))
        self._build_tray_auto()
        self._build_finishing()

    # ---------------- automatische Fachwahl ---------------- #
    def _pc(self):
        return self.cfg.get("printers", {}).get(self.caps.name, {}) if self.caps else {}

    def _build_tray_auto(self):
        self.tray_list = trays.trays_of(self._pc())
        self.cmb_weight = None
        if not self.tray_list or not self.caps.roles.get("source"):
            return
        weights = trays.weights_of(self._pc())
        self.s.__dict__.setdefault("weights", {})
        cur = self.s.weights.get(self.caps.name, 0)
        if weights:
            self.cmb_weight = QComboBox()
            fill_combo(self.cmb_weight, [(0, tr("beliebig"))] + [(w, tr("{0} g/m²").format(w)) for w in weights], cur)
            self.cmb_weight.currentIndexChanged.connect(self._weight_changed)
            self.paper_form.addRow(tr("Grammatur:"), self.cmb_weight)
        self.chk_autotray = QCheckBox(tr("Fach automatisch nach Format/Grammatur wählen"))
        self.chk_autotray.setChecked(bool(self._pc().get("tray_auto", True)))
        self.chk_autotray.toggled.connect(lambda _b: self._auto_tray())
        self.paper_form.addRow("", self.chk_autotray)
        self.lbl_tray = QLabel()
        self.lbl_tray.setWordWrap(True)
        self.paper_form.addRow("", self.lbl_tray)
        self._live = None
        host = self._pc().get("tray_host", "")
        if self._pc().get("tray_live") and host:
            self._start_live(host)
        self._auto_tray()

    def _start_live(self, host):
        from PySide6.QtCore import QThread, Signal

        class _Live(QThread):
            got = Signal(object)

            def run(self_t):
                self_t.got.emit(trays.live_status(host, force=True))
        self._live_thread = _Live(self)
        self._live_thread.got.connect(self._live_arrived)
        self._live_thread.start()

    def _live_arrived(self, st):
        self._live = st
        if st is None and hasattr(self, "lbl_tray"):
            self.lbl_tray.setToolTip(tr("Gerät nicht erreichbar – es gilt die hinterlegte Reihenfolge."))
        self._auto_tray()

    def _weight_changed(self, *_):
        self.s.weights[self.caps.name] = self.cmb_weight.currentData() or 0
        self._auto_tray()

    def _auto_tray(self):
        if not getattr(self, "tray_list", None) or not hasattr(self, "chk_autotray"):
            return
        if not self.chk_autotray.isChecked():
            self.lbl_tray.setText("")
            self._auto_slot = None
            return
        skey, pkey, mkey = (self.caps.roles.get(r) for r in ("source", "pagesize", "mediatype"))
        weight = self.cmb_weight.currentData() if self.cmb_weight else 0
        labels = {c.value: c.text for c in self.caps.options[skey].choices}
        p = trays.pick(self.tray_list, self.values.get(pkey, ""), weight or 0, self._live, labels)
        if p.tray:
            self.values[skey] = p.tray.slot
            self._set_combo(skey, p.tray.slot)
            if p.tray.media and mkey:
                self.values[mkey] = p.tray.media
                self._set_combo(mkey, p.tray.media)
            self._auto_slot = p.tray.slot
            txt = f"→ {labels.get(p.tray.slot, p.tray.slot)}" + (f"   ({p.note})" if p.note else "")
        else:
            self._auto_slot = None
            txt = "⚠ " + p.note
        if self._live is not None:
            txt += tr("   · Füllstand vom Gerät")
        self.lbl_tray.setText(txt)
        self.lbl_tray.setStyleSheet(f"color: {theme.ERROR if p.warn else theme.ACCENT};")
        self._preview_timer.start()

    def _set_combo(self, key, value):
        cb = self.role_combos.get(key) or getattr(self, "driver_combos", {}).get(key)
        if cb is not None:
            cb.blockSignals(True)
            i = cb.findData(value)
            if i >= 0:
                cb.setCurrentIndex(i)
            cb.blockSignals(False)

    def _presets(self):
        return self.cfg.get("printers", {}).get(self.caps.name, {}).get("presets", []) if self.caps else []

    def _build_finishing(self):
        while self.finish_form.rowCount():
            self.finish_form.removeRow(0)
        presets = self._presets()
        self.cmb_preset = QComboBox()
        fill_combo(self.cmb_preset, [("", tr("(keine Vorlage)"))] + [(str(i), p["name"]) for i, p in enumerate(presets)],
                   getattr(self, "_preset_sel", {}).get(self.caps.name, ""))
        self.cmb_preset.setEnabled(bool(presets))
        self.cmb_preset.setToolTip(tr("Vom Admin angelegte Finisher-Vorlagen, z. B. „Broschüre heften + falzen“"))
        self.cmb_preset.currentIndexChanged.connect(self._preset_chosen)
        self.finish_form.addRow(tr("Vorlage:"), self.cmb_preset)
        n = 0
        for role, label in FINISH_LABELS:
            key = self.caps.roles.get(role)
            if key and key in self.caps.options and key not in self.role_combos:
                cb = self._option_combo(key)
                self.role_combos[key] = cb
                self.finish_form.addRow(f"{tr(label)}\n({self.caps.options[key].text}):", cb)
                n += 1
        if self.caps.backend == "win":
            btn = QPushButton(tr("Herstellereinstellungen (Finisher, Heften, Falzen …)"))
            btn.clicked.connect(self._win_driver_dialog)
            self.finish_form.addRow(btn)
            self.lbl_devmode = QLabel()
            self.lbl_devmode.setStyleSheet(f"color: {theme.MUTED};")
            self.finish_form.addRow(self.lbl_devmode)
            self._update_devmode_label()
        elif not n:
            lbl = QLabel(tr("Keine Finisher-Optionen erkannt – alle Treiberoptionen im Reiter „Treiber“. "
                         "Fehlen Finisher ganz: im Admin unter „Installierte Hardware“ einschalten."))
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color: {theme.MUTED};")
            self.finish_form.addRow(lbl)

    def _update_devmode_label(self):
        if hasattr(self, "lbl_devmode"):
            has = bool(self.values.get("__devmode__"))
            self.lbl_devmode.setText(tr("Herstellereinstellungen aktiv (Admin-Standard, Vorlage oder von dir gesetzt).")
                                     if has else tr("Es gelten die Windows-Standards des Druckers."))

    def _win_driver_dialog(self):
        from ..printers_win import DEVMODE_KEY, driver_dialog
        try:
            res = driver_dialog(int(self.winId()), self.caps.name, self.values.get(DEVMODE_KEY))
        except Exception as e:
            QMessageBox.critical(self, tr("Treiberdialog"), str(e))
            return
        if res:
            self.values[DEVMODE_KEY] = res
            self._update_devmode_label()
            self._changed()

    def _preset_chosen(self, *_):
        idx = self.cmb_preset.currentData()
        self.__dict__.setdefault("_preset_sel", {})[self.caps.name] = idx or ""
        if not idx:
            return
        pr = self._presets()[int(idx)]
        for k, v in pr.get("options", {}).items():
            if k in self.caps.options:
                self.values[k] = v
        if pr.get("devmode"):
            self.values["__devmode__"] = pr["devmode"]
        if pr.get("booklet") and self._handling() != "booklet":
            self.handling_btns["booklet"].setChecked(True)
            self.stack.setCurrentIndex(self.handling_btns["booklet"].property("page"))
        # Felder neu aufbauen, damit sie die Vorlage zeigen
        self._build_paper()
        skey = self.caps.roles.get("source")
        if skey and skey in pr.get("options", {}) and hasattr(self, "chk_autotray"):
            # Vorlage bestimmt das Fach selbst (z. B. Umschlagkarton aus dem Mehrzweckfach)
            self.chk_autotray.blockSignals(True)
            self.chk_autotray.setChecked(False)
            self.chk_autotray.blockSignals(False)
            self.values[skey] = pr["options"][skey]
            self._set_combo(skey, self.values[skey])
            self.lbl_tray.setText(tr("Fach durch Vorlage festgelegt"))
        self._build_driver_tab()
        fit_width(self)
        self._changed()

    def _build_driver_tab(self):
        old = self.driver_box.layout()
        if old is not None:
            QWidget().setLayout(old)   # altes Layout entsorgen
        v = QVBoxLayout(self.driver_box)
        self.lbl_conflict = QLabel()
        self.lbl_conflict.setWordWrap(True)
        self.lbl_conflict.setStyleSheet(f"color: {theme.ERROR};")
        v.addWidget(self.lbl_conflict)
        backend = {"ppd": "PPD (Herstellertreiber)", "ipp": "IPP (driverless)",
                   "win": "Windows-Druckertreiber"}.get(self.caps.backend, self.caps.backend)
        info = QLabel(tr("Backend: {0} – alle Optionen bleiben wählbar; Konflikte werden nur gemeldet.").format(backend)
                      if self.caps.backend != "win" else
                      tr("Backend: {0}. Alle herstellerspezifischen Funktionen (Finisher, Heften, Lochen, Falzen, Beschnitt, Fiery-Optionen …) stellst du im Original-Dialog des Herstellers ein. Papierformat, Fach, Duplex und Farbe aus dem Reiter „Allgemein“ haben Vorrang.").format(backend))
        info.setWordWrap(True)
        info.setStyleSheet(f"color: {theme.MUTED};")
        v.addWidget(info)
        if self.caps.backend == "win":
            btn = QPushButton(tr("Herstellereinstellungen öffnen …"))
            btn.clicked.connect(self._win_driver_dialog)
            v.addWidget(btn)
        self.driver_combos = {}
        installable = []
        for gname, gtext, keys in self.caps.groups:
            keys = [k for k in keys if k not in self.role_combos]
            if not keys:
                continue
            if gname == printers.INSTALLABLE_GROUP:
                installable = keys
                continue
            box = QGroupBox(gtext)
            f = QFormLayout(box)
            for k in keys:
                cb = self._option_combo(k)
                self.driver_combos[k] = cb
                f.addRow(self.caps.options[k].text + ":", cb)
            v.addWidget(box)
        if installable:
            box = QGroupBox(tr("Installierte Hardware (nur Admin änderbar)"))
            f = QFormLayout(box)
            for k in installable:
                o = self.caps.options[k]
                txt = next((c.text for c in o.choices if c.value == o.default), o.default)
                f.addRow(o.text + ":", QLabel(txt))
            v.addWidget(box)
        v.addStretch()

    def _option_changed(self, cb):
        key = cb.property("key")
        self.values[key] = cb.currentData()
        if self.caps and key == self.caps.roles.get("pagesize"):
            self._auto_tray()            # Format geändert -> passende Lade wählen
        self._changed()

    def _build_profiles(self):
        name = self.caps.name
        profs = config.profiles_for(self.cfg, name)
        pid, intent = self.s.color_for(name)
        self.cmb_profile.blockSignals(True)
        self.cmb_intent.blockSignals(True)
        fill_combo(self.cmb_profile, [("", tr("Keins – Farbmanagement des Treibers"))] +
                   [(p["id"], p.get("name") or p["id"]) for p in profs], pid)
        self._fill_intents(intent)
        user = bool(self.cfg.get("allow_user_profile_choice", True))
        if self._is_pdf_target():                   # PDF-Ausgabe: Farben bleiben unverändert
            fill_combo(self.cmb_profile, [("", tr("Keins – Farben bleiben unverändert"))], "")
            user = False
        self.cmb_profile.setEnabled(user and bool(profs))
        self.cmb_intent.setEnabled(user and bool(self.cmb_profile.currentData()))
        self.cmb_profile.blockSignals(False)
        self.cmb_intent.blockSignals(False)
        self._profile_note()

    def _fill_intents(self, current):
        p = config.profile_by_id(self.cfg, self.cmb_profile.currentData() or "")
        allowed = (p or {}).get("intents") or list(config.INTENTS)
        fill_combo(self.cmb_intent, [(i, config.INTENTS[i]) for i in allowed if i in config.INTENTS], current)

    def _profile_changed(self, *_):
        cur_intent = self.cmb_intent.currentData() or "relative"
        if self.sender() is self.cmb_profile:
            self.cmb_intent.blockSignals(True)
            self._fill_intents(cur_intent)
            self.cmb_intent.blockSignals(False)
        self.cmb_intent.setEnabled(self.cmb_profile.isEnabled() and bool(self.cmb_profile.currentData()))
        self.s.color[self.caps.name] = (self.cmb_profile.currentData() or "",
                                        self.cmb_intent.currentData() or "relative")
        self._profile_note()
        self._preview_timer.start()

    def _profile_note(self):
        p = config.profile_by_id(self.cfg, self.cmb_profile.currentData() or "")
        if not p:
            self.lbl_profile_note.setText("")
            return
        dopts = p.get("driver_options") or {}
        txt = tr("Das PDF wird vor dem Senden mit diesem Profil in Gerätefarben umgerechnet.")
        if dopts:
            txt += tr(" Profil setzt Treiberoptionen: ") + ", ".join(f"{k}={v}" for k, v in dopts.items())
        self.lbl_profile_note.setText(txt)

    # ================================================================== #
    # Zustand -> Layout
    # ================================================================== #
    def _settings(self) -> layout.LayoutSettings:
        L = layout.LayoutSettings()
        L.mode = self.mode_group.checkedButton().property("mode") if self.mode_group.checkedButton() else "fit"
        L.custom_percent = self.spn_custom.value()
        L.custom_by = self.cmb_custom_by.currentData()
        L.custom_mm = self.spn_custom_mm.value()
        L.handling = self._handling()
        n = self.cmb_nup.currentData()
        if n == 0:
            L.cols, L.rows, L.nup = self.spn_cols.value(), self.spn_rows.value(), 1
        else:
            L.nup = n
        L.booklet_sides = self.cmb_bsides.currentData()
        L.booklet_binding = self.cmb_binding.currentData()
        L.booklet_sheets = self.ed_bsheets.text().strip()
        L.booklet_gutter_mm = self.spn_gutter.value()
        L.poster_mode = self.cmb_pmode.currentData()
        L.poster_percent = self.spn_ppct.value()
        L.poster_cols, L.poster_rows = self.spn_pcols.value(), self.spn_prows.value()
        L.poster_target = self.cmb_ptarget.currentData()
        L.poster_target_w_mm, L.poster_target_h_mm = self.spn_ptw.value(), self.spn_pth.value()
        L.poster_overlap_mm = self.spn_overlap.value()
        L.poster_marks = self.chk_pmarks.isChecked()
        L.poster_labels = self.chk_plabels.isChecked()
        L.poster_large_only = self.chk_plarge.isChecked()
        L.mirror_h = self.chk_mirror_h.isChecked()
        L.mirror_v = self.chk_mirror_v.isChecked()
        L.step_repeat = self.chk_sr.isChecked()
        L.sr_mode = self.cmb_srmode.currentData()
        L.sr_cols, L.sr_rows = self.spn_srcols.value(), self.spn_srrows.value()
        L.sr_percent = self.spn_srpct.value()
        L.sr_by = self.cmb_srby.currentData()
        L.sr_mm = self.spn_srmm.value()
        L.sr_gap_mm = self.spn_srgap.value()
        L.sr_orientation = self.cmb_srorient.currentData()
        L.sr_rotate = self.cmb_srrot.currentData()
        L.sr_join = self.cmb_srjoin.currentData()
        L.crop_marks = self.chk_marks.isChecked()
        L.bleed_mm = self.spn_bleed.value()
        L.order = self.cmb_order.currentData()
        L.tile_mode = self.cmb_tile.currentData()
        L.tile_percent = self.spn_tile.value()
        L.gap_mm = self.spn_gap.value()
        L.borders = self.chk_borders.isChecked()
        L.orientation = self.cmb_orient.currentData()
        L.autorotate = self.chk_autorot.isChecked()
        L.center = self.chk_center.isChecked()
        L.use_margins = self.chk_margins.isChecked()
        return L

    def _pages(self) -> list[int]:
        n = len(self.doc)
        cur = self.current if self.rb_cur.isChecked() else None
        rng = self.ed_range.text() if self.rb_range.isChecked() else ""
        rev = self.chk_reverse.isChecked() and self._handling() != "booklet"
        return layout.select_pages(n, rng, self.cmb_subset.currentData(), rev, cur)

    def _make_plans(self, pages):
        return printjob.make_plans(self.sizes, pages, self._sheet(), self._settings(),
                                   self.chk_reverse.isChecked())

    def _short_edge_choice(self):
        return printjob.short_edge_choice(self.caps)

    def _sheet(self) -> layout.Sheet:
        w, h, ia = self.caps.sheet_for(self.values)
        if self.caps.backend == "pdf" and self.values.get("PageSize") == "DOC":
            try:
                pages = self._pages()
            except ValueError:
                pages = []
            w, h = self.sizes[pages[0] if pages else self.current]
            ia = None
        return layout.Sheet(w, h, ia)

    def _print_doc(self):
        """Druckfassung des Dokuments: Formularwerte/Kommentare eingebrannt (einmal je Dialog)."""
        if getattr(self, "_flat", None) is None:
            self._flat = layout.flattened(self.doc)
        return self._flat

    def done(self, r):
        flat = getattr(self, "_flat", None)
        if flat is not None and flat is not self.doc:
            flat.close()
        self._flat = None
        super().done(r)

    def _is_pdf_target(self):
        return bool(self.caps and self.caps.backend == "pdf")

    def _changed(self, *_):
        self._sync_enabled()
        if not self.caps:
            return
        # Sitzung merken (nur RAM)
        self.s.layout = self._settings()
        self.s.copies = self.spn_copies.value()
        self.s.collate = self.chk_collate.isChecked()
        self.s.subset = self.cmb_subset.currentData()
        self.s.reverse = self.chk_reverse.isChecked()
        bad = self.caps.conflicts(self.values)
        self.lbl_conflict.setText((tr("⚠ Treiber meldet Konflikt bei: ") + ", ".join(
            self.caps.options[k].text for k in bad)) if bad else "")
        self._preview_timer.start()

    def _update_preview(self):
        self.lbl_warn.clear()
        try:
            pages = self._pages()
            self.ed_range.setStyleSheet("")
        except ValueError as e:
            self.ed_range.setStyleSheet("background: #ffd6d6;")
            self.lbl_warn.setText(str(e))
            self.plans = []
            self.preview.set_content(None, None, False)
            return
        try:
            self.plans = self._make_plans(pages)
        except ValueError as e:
            self.lbl_warn.setText(str(e))
            self.plans = []
        self.sheet_index = min(self.sheet_index, max(0, len(self.plans) - 1))
        try:
            self._render_sheet()
        except Exception as e:          # Vorschau darf das Programm nie mitreißen
            self.lbl_warn.setText(tr("Vorschau nicht möglich: {0}").format(e))

    def _goto_sheet(self, i):
        if 0 <= i < len(self.plans):
            self.sheet_index = i
            self._render_sheet()

    def _render_sheet(self):
        n = len(self.plans)
        if n:
            lab = self.plans[self.sheet_index].label
            self.lbl_sheet.setText(tr("Blatt {0} von {1}").format(self.sheet_index + 1, n) + (f"\n{lab}" if lab else ""))
        else:
            self.lbl_sheet.setText(tr("Keine Seiten"))
        self.btn_prev.setEnabled(self.sheet_index > 0)
        self.btn_next.setEnabled(self.sheet_index < n - 1)
        if not n:
            self.preview.set_content(None, None, False)
            return
        sheet = self._sheet()
        sp = self.plans[self.sheet_index]
        out = layout.impose_with(self._print_doc(), sheet, self.plans, self._settings(), only=[self.sheet_index])
        page = out[0]
        target_h = max(200, self.preview.height() - 32)
        ph = sheet.width if sp.landscape else sheet.height
        scale = target_h / ph
        dpr = self.devicePixelRatioF()
        pm = self._proofed_pixmap(page, scale, 90 if sp.landscape else 0, dpr)
        page.close()
        out.close()
        self.preview.set_content(pm, sheet, sp.landscape)

        # Info
        key = self.caps.roles.get("pagesize")
        fmt = self.caps.options[key].choices if key else []
        fmt_txt = next((c.text for c in fmt if c.value == self.values.get(key)), "")
        src_key = self.caps.roles.get("source")
        src_txt = ""
        if src_key:
            src_txt = next((c.text for c in self.caps.options[src_key].choices
                            if c.value == self.values.get(src_key)), "")
        scales = sorted({round(p.scale * 100, 1) for p in sp.placements})
        size_txt = ""
        if sp.placements:
            pl = sp.placements[0]
            ow, oh = self.sizes[pl.src]
            # Darstellung in Leserichtung der Seite (nicht gedreht), auf 0,1 mm
            nw, nh = (pl.h, pl.w) if pl.rot == 90 else (pl.w, pl.h)
            size_txt = (tr("Seite {0}: {1:.1f} × {2:.1f} mm → {3:.1f} × {4:.1f} mm auf dem Blatt").format(pl.src + 1, ow / layout.MM, oh / layout.MM, nw / layout.MM, nh / layout.MM))
            if self.chk_sr.isChecked():
                n = len(sp.placements)
                self.lbl_srsize.setText(tr("je Nutzen {0:.1f} × {1:.1f} mm ({2:.1f} %) · {3} Nutzen pro Blatt – Seite {4}").format(nw / layout.MM, nh / layout.MM, pl.scale * 100, n, pl.src + 1))
            elif self.rb_custom.isChecked() and not self._settings().is_nup:
                self.lbl_custom.setText(tr("ergibt {0:.1f} × {1:.1f} mm ({2:.1f} %) – Seite {3}").format(nw / layout.MM, nh / layout.MM, pl.scale * 100, pl.src + 1))
        self.lbl_info.setText(
            tr("Papier: {0} ({1:.0f} × {2:.0f} mm)").format(fmt_txt, sheet.width / layout.MM, sheet.height / layout.MM)
            + (tr(" · Fach: {0}").format(src_txt) if src_txt else "")
            + f" · {'Querformat' if sp.landscape else 'Hochformat'}"
            + tr(" · Maßstab: {0}").format(', '.join(f'{s:g} %' for s in scales))
            + (f"\n{size_txt}" if size_txt else ""))
        warns = sorted({w for p in self.plans for w in p.warnings})
        if not self.caps.sheet_info(self.values)[3]:
            warns.insert(0, tr("⚠ Maße für Papierformat „{0}“ unbekannt – A4 angenommen. "
                               "Bitte Treiber/PPD prüfen.").format(fmt_txt))
        self.lbl_warn.setText("\n".join(warns[:4]) + (" …" if len(warns) > 4 else ""))

    def _proof_params(self):
        """(Anpassungen, ICC-Pfad, Intent, BPC, Profilname) für die aktuelle Auswahl."""
        adj = proof.adjustments(self.caps, self.values)
        pid = self.cmb_profile.currentData() or ""
        prof = config.profile_by_id(self.cfg, pid) if pid else None
        icc = prof.get("file") if prof else None
        intent = self.cmb_intent.currentData() or "relative"
        bpc = bool(prof.get("bpc", True)) if prof else True
        name = (prof.get("name") or pid) if prof else None
        return adj, icc, intent, bpc, name

    def _proofed_pixmap(self, page, scale, rotation, dpr):
        if not self.chk_proof.isChecked():
            self.lbl_proof.setText("")
            return render_pixmap(page, scale, rotation, dpr)
        adj, icc, intent, bpc, name = self._proof_params()
        if not icc and not adj["labels"]:
            self.lbl_proof.setText("")
            return render_pixmap(page, scale, rotation, dpr)
        from PySide6.QtGui import QImage, QPixmap
        bmp = page.render(scale=scale * dpr, rotation=rotation, may_draw_forms=True, draw_annots=True)
        img = proof.apply(bmp.to_pil(), adj, icc, intent, bpc)
        bmp.close()
        data = img.tobytes("raw", "RGB")
        qi = QImage(data, img.width, img.height, 3 * img.width, QImage.Format.Format_RGB888).copy()
        pm = QPixmap.fromImage(qi)
        pm.setDevicePixelRatio(dpr)
        self.lbl_proof.setText(proof.describe(adj, name) + ("" if icc else tr("  (Treiberregler: Annäherung)")))
        return pm

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._preview_timer.start()

    # ================================================================== #
    # Drucken
    # ================================================================== #
    def _print(self):
        if not self.caps:
            return
        try:
            pages = self._pages()
        except ValueError as e:
            QMessageBox.warning(self, tr("Seitenbereich"), str(e))
            return
        if not pages:
            QMessageBox.warning(self, tr("Drucken"), tr("Keine Seiten ausgewählt."))
            return
        name = self.caps.name
        values = self.values
        if self._is_pdf_target():
            base = os.path.splitext(os.path.basename(self.path or "Dokument"))[0]
            start_dir = getattr(self.parent(), "_suggest_dir", "") or (
                os.path.dirname(getattr(self.parent(), "path", "") or "") or os.path.expanduser("~"))
            out, _ = QFileDialog.getSaveFileName(self, tr("Als PDF speichern"),
                                                 os.path.join(start_dir, f"{base}_druck.pdf"), tr("PDF-Dateien (*.pdf)"))
            if not out:
                return
            if not out.lower().endswith(".pdf"):
                out += ".pdf"
            src = getattr(self.parent(), "path", None)
            if src and os.path.abspath(out) == os.path.abspath(src):
                QMessageBox.warning(self, tr("Speichern"), tr("Bitte nicht über das geöffnete Dokument speichern."))
                return
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                printjob.submit_document(self.doc, os.path.basename(self.path or "Dokument"), self.s, name,
                                         pages, self._settings(), 1, True, self.chk_reverse.isChecked(),
                                         values=dict(self.values, __out__=out))
            except Exception as e:
                QApplication.restoreOverrideCursor()
                QMessageBox.critical(self, tr("Speichern"), str(e))
                return
            QApplication.restoreOverrideCursor()
            r = QMessageBox.question(self, tr("Gespeichert"), tr("Gespeichert als:\n{0}\n\nJetzt in pdfToolkit öffnen?").format(out))
            if r == QMessageBox.StandardButton.Yes and hasattr(self.parent(), "ctl"):
                self.parent().ctl.open_paths([out])
            self.accept()
            return
        skey = self.caps.roles.get("source")
        if getattr(self, "_auto_slot", None) and skey and self.values.get(skey) == self._auto_slot:
            weight = self.cmb_weight.currentData() if getattr(self, "cmb_weight", None) else 0
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            values, note, warn = printjob.resolve_tray(self.s, name, self.values, weight or 0, live=True)
            QApplication.restoreOverrideCursor()
            if warn and values.get(skey) == self.values.get(skey) and "leer" in note:
                if QMessageBox.question(self, tr("Fach leer"), note + tr("\n\nTrotzdem drucken?")) \
                        != QMessageBox.StandardButton.Yes:
                    return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            jid = printjob.submit_document(
                self.doc, os.path.basename(self.path or "Dokument"), self.s, name, pages,
                self._settings(), self.spn_copies.value(), self.chk_collate.isChecked(),
                self.chk_reverse.isChecked(), values=values)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, tr("Druckfehler"), str(e))
            return
        QApplication.restoreOverrideCursor()
        self.parent().statusBar().showMessage(tr("Auftrag {0} an {1} gesendet.").format(jid, name), 8000)
        self.accept()
