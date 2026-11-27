# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Plan and poster window: building the window – top row, list of drawings, settings (job, material and roll, placement, finishing, banner), bottom row and the signal connections."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)

from .. import planprint as pp
from ..l10n import tr
from . import theme
from .common import MsgBox
from .icons import icon
from .plantexts import (
    ALIGN_TEXT,
    BLEED_TEXT,
    COLOR_TEXT,
    COPIES_TEXT,
    FRAME_TEXT,
    ORDER_TEXT,
    OVER_TEXT,
    PREVIEW_PX,
    QMODE_TEXT,
    ROTATE_TEXT,
    SCALE_TEXT,
    fill_combo,
)


class PlanBuildMixin:
    """Construction of PlanDialog."""

    def _build_top_row(self, v):
        """Top row: printer, reading the rolls, rolls by hand, output folders; below it the roll message."""
        # printer + rolls
        top = QHBoxLayout()
        top.addWidget(QLabel(tr("Drucker:")))
        self.cmb_printer = QComboBox()
        self.cmb_printer.setMinimumWidth(160)
        top.addWidget(self.cmb_printer)
        top.addStretch(1)
        self.lbl_rolls = MsgBox(3, theme.MUTED)
        self.btn_reload = QPushButton(tr("Rollen neu lesen"))
        self.btn_reload.clicked.connect(lambda: self._load_rolls(force=True))
        top.addWidget(self.btn_reload)
        self.btn_manual = QPushButton(icon("roll"), tr("Rollen …"))
        self.btn_manual.setToolTip(tr("Rollen von Hand eintragen (wenn das Gerät nichts meldet)"))
        self.btn_manual.clicked.connect(self._edit_rolls)
        top.addWidget(self.btn_manual)
        b = QPushButton(icon("open"), tr("Ordner …"))
        b.setToolTip(tr("Ausgabe in Ordner (z. B. Hotfolder von VersaWorks) einrichten"))
        b.clicked.connect(self._edit_folders)
        top.addWidget(b)
        v.addLayout(top)
        v.addWidget(self.lbl_rolls)

    def _build_plan_list(self):
        """Left side: buttons, the list of plans or posters and the hint below it. Returns the widget."""
        # ---- left: plans ----
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        b = QPushButton(icon("insert"), tr("Pläne hinzufügen …") if self.kind == "plan" else tr("Poster hinzufügen …"))
        b.setToolTip(tr("PDF, Bilder oder Office-Dateien – oder einfach ins Fenster ziehen"))
        b.clicked.connect(self._add_files)
        bar.addWidget(b)
        self.btn_remove = QPushButton(icon("delete"), "")
        self.btn_remove.setToolTip(tr("Ausgewählte Pläne entfernen"))
        self.btn_remove.clicked.connect(self._remove)
        bar.addWidget(self.btn_remove)
        b = QPushButton(icon("move_up"), "")
        b.setToolTip(tr("Nach oben"))
        b.clicked.connect(lambda: self._move(-1))
        bar.addWidget(b)
        b = QPushButton(icon("move_down"), "")
        b.setToolTip(tr("Nach unten"))
        b.clicked.connect(lambda: self._move(1))
        bar.addWidget(b)
        bar.addStretch(1)
        lv.addLayout(bar)
        # document check of the listed files (plandialog._run_check): profile for this window only
        crow = QHBoxLayout()
        crow.addWidget(QLabel(tr("Prüfung:")))
        self.cmb_check = QComboBox()
        self.cmb_check.setToolTip(
            tr("Prüfprofil für die Dateien in der Liste – gilt nur in diesem Fenster (Vorgabe: Plan- und Großformat)")
        )
        crow.addWidget(self.cmb_check)
        self.lbl_check = QLabel()
        self.lbl_check.setWordWrap(True)
        crow.addWidget(self.lbl_check, 1)
        lv.addLayout(crow)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([tr(c) for c in self.COLS])
        self.tree.setRootIsDecorated(False)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        self.tree.itemChanged.connect(self._qty_changed)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)  # only the quantity
        self.tree.itemDoubleClicked.connect(lambda row, col: self.tree.editItem(row, 4) if col == 4 else None)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        vsplit = QSplitter(Qt.Orientation.Vertical)
        vsplit.addWidget(self.tree)
        pg = QGroupBox(tr("Druckseiten (Vorschau)"))
        pgl = QVBoxLayout(pg)
        pgl.setContentsMargins(4, 4, 4, 4)
        self.lst_prev = QListWidget()
        self.lst_prev.setViewMode(QListView.ViewMode.IconMode)
        self.lst_prev.setFlow(QListView.Flow.LeftToRight)
        self.lst_prev.setWrapping(True)
        self.lst_prev.setResizeMode(QListView.ResizeMode.Adjust)
        self.lst_prev.setMovement(QListView.Movement.Static)
        self.lst_prev.setIconSize(QSize(PREVIEW_PX, PREVIEW_PX))
        self.lst_prev.setSpacing(6)
        self.lst_prev.setWordWrap(True)
        self.lst_prev.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        pgl.addWidget(self.lst_prev)
        self.lbl_prev = QLabel()
        self.lbl_prev.setStyleSheet(f"color: {theme.MUTED};")
        self.lbl_prev.setWordWrap(True)
        pgl.addWidget(self.lbl_prev)
        vsplit.addWidget(pg)
        vsplit.setStretchFactor(0, 3)
        vsplit.setStretchFactor(1, 2)
        vsplit.setChildrenCollapsible(False)
        lv.addWidget(vsplit, 1)
        self._prev_timer = QTimer(self)
        self._prev_timer.setSingleShot(True)
        self._prev_timer.setInterval(350)
        self._prev_timer.timeout.connect(self._preview)
        self.lbl_hint = QLabel(
            tr(
                "Pläne mit + hinzufügen oder ins Fenster ziehen. Jede Seite ist ein Plan. "
                "Menge: Doppelklick. Rechtsklick: Druckbereich je Plan."
            )
        )
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setStyleSheet(f"color: {theme.MUTED};")
        lv.addWidget(self.lbl_hint)
        return left

    def _build_settings_pane(self):
        """Right side: run length, settings, banner and cutting – in a scroll area. Returns the scroll area."""
        # ---- right: run length + settings ----
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        self._build_length_group(rv)
        self._build_settings_group(rv)
        self._build_banner_group(rv)
        rv.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(right)
        right.setMinimumWidth(320)
        return scroll

    def _build_length_group(self, rv):
        """Group "Laufmeter je Rolle": run length per roll and warnings."""
        g = QGroupBox(tr("Laufmeter je Rolle"))
        gv = QVBoxLayout(g)
        self.lbl_len = QLabel()
        self.lbl_len.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_len.setWordWrap(True)
        gv.addWidget(self.lbl_len)
        self.lbl_warn = MsgBox(4, theme.ACCENT)
        gv.addWidget(self.lbl_warn)
        rv.addWidget(g)

    def _build_settings_group(self, rv):
        """Group "Einstellungen": copies, order, colour, quality, material, roll, placement, scaling, bleed, marks."""
        g = QGroupBox(tr("Einstellungen"))
        f = QFormLayout(g)
        self._build_job_rows(f)
        self._build_media_rows(f)
        self._build_placement_rows(f)
        self._build_finishing_rows(f)
        rv.addWidget(g)

    def _build_job_rows(self, f):
        """Copies, how they are sent, order, colour and quality."""
        s0 = self.s0
        row = QHBoxLayout()
        self.spn_copies = QSpinBox()
        self.spn_copies.setRange(1, 999)
        self.spn_copies.setValue(max(1, s0.copies))
        row.addWidget(self.spn_copies)
        self.chk_collate = QCheckBox(tr("Sortiert"))
        self.chk_collate.setToolTip(
            tr("Aus: jeder Plan alle Exemplare hintereinander (Plan 1 ×3, Plan 2 ×3 …).\nAn: Satz für Satz.")
        )
        self.chk_collate.setChecked(s0.collate)
        row.addWidget(self.chk_collate)
        row.addStretch(1)
        f.addRow(tr("Exemplare:"), row)
        self.cmb_copies = QComboBox()
        fill_combo(self.cmb_copies, [(k, tr(t)) for k, t in COPIES_TEXT.items()], pp.copies_mode(s0))
        self.cmb_copies.setToolTip(
            tr(
                "Ein Auftrag, je Exemplar ein Blatt: so erwartet es z. B. die ColorWave – sie "
                "schneidet nach jedem Blatt.\nJe Exemplar ein Auftrag: (1/3), (2/3) …\n"
                "Kopienzahl: ein Blatt, das Gerät druckt es mehrfach."
            )
        )
        f.addRow(tr("Versand:"), self.cmb_copies)
        self.lbl_scope = QLabel()
        self.lbl_scope.setWordWrap(True)
        self.lbl_scope.setStyleSheet(f"color: {theme.ACCENT_TEXT};")
        f.addRow(self.lbl_scope)
        self.cmb_order = QComboBox()
        fill_combo(self.cmb_order, [(k, tr(t)) for k, t in ORDER_TEXT.items()], s0.order)
        f.addRow(tr("Reihenfolge:"), self.cmb_order)
        self.cmb_color = QComboBox()
        fill_combo(self.cmb_color, [(k, tr(t)) for k, t in COLOR_TEXT.items()], s0.color)
        f.addRow(tr("Farbe:"), self.cmb_color)
        self.cmb_qmode = QComboBox()
        fill_combo(self.cmb_qmode, [(k, tr(t)) for k, t in QMODE_TEXT.items()], pp.quality_mode_of(s0))
        self.cmb_qmode.setToolTip(
            tr(
                "Stellt die Druckqualität im Treiber auf die niedrigste (Produktionsdruck) bzw. "
                "höchste Stufe (Qualitätsdruck). Vorrang hat eine Qualität, die beim Material "
                "derselben Kategorie eingetragen ist."
            )
        )
        f.addRow(tr("Qualität:"), self.cmb_qmode)
        # colour for tests: this print only, never remembered (filled per printer: plandialog._fill_color_test)
        row = QHBoxLayout()
        self.cmb_cprof = QComboBox()
        self.cmb_cprof.setToolTip(
            tr(
                "Nur für diesen Druck (zum Testen) – wird nicht gespeichert, beim nächsten Mal gilt wieder die Einstellung."
            )
        )
        row.addWidget(self.cmb_cprof, 2)
        self.cmb_cintent = QComboBox()
        self.cmb_cintent.setToolTip(self.cmb_cprof.toolTip())
        row.addWidget(self.cmb_cintent, 1)
        f.addRow(tr("Farbprofil:"), row)
        self.chk_drvcolor = QCheckBox(tr("Farbanpassung des Treibers aus (nur dieser Druck)"))
        self.chk_drvcolor.setToolTip(
            tr(
                "Für Tests und wenn Passermark mit einem Profil umrechnet: der Treiber verändert die Farben dann "
                "nicht noch einmal. Unter Windows wird die ICM-Farbanpassung abgeschaltet – einen eigenen Farbmodus "
                "des Herstellers (z. B. „EPSON Vivid“) stellst du in den Treibereinstellungen auf „Aus“."
            )
        )
        f.addRow("", self.chk_drvcolor)

    def _build_media_rows(self, f):
        """Material, roll and where on the roll the drawing sits."""
        s0 = self.s0
        row = QHBoxLayout()
        self.cmb_mat = QComboBox()
        self.cmb_mat.setToolTip(
            tr(
                "Passermark-Material: Grammatur (wählt die Rolle), Medientyp, Qualität, "
                "Tintenmenge und Profil – unter „Materialien …“ je Drucker"
            )
        )
        row.addWidget(self.cmb_mat, 1)
        b = QPushButton(icon("material"), "")
        b.setToolTip(tr("Materialien …"))
        b.clicked.connect(self._edit_materials)
        row.addWidget(b)
        f.addRow(tr("Material:"), row)
        self.cmb_roll = QComboBox()
        self.cmb_roll.setToolTip(
            tr("Auf diese Rolle drucken – „Automatisch“ wählt nach Material bzw. Grammatur die schmälste passende")
        )
        f.addRow(tr("Rolle:"), self.cmb_roll)
        self.cmb_align = QComboBox()
        fill_combo(self.cmb_align, [(k, tr(t)) for k, t in ALIGN_TEXT.items()], s0.align)
        self.cmb_align.setToolTip(
            tr(
                "Am Rand: die Seite ist so breit wie die Rolle, der Plan liegt an der "
                "Rollenkante – Rand bzw. äußere Linie bleiben, es bleibt ein Längsschnitt.\n"
                "Mittig: rundum gleich viel Abstand, das Gerät blendet nichts aus."
            )
        )
        f.addRow(tr("Auf der Rolle:"), self.cmb_align)

    def _build_placement_rows(self, f):
        """Print area, margin, orientation and scaling."""
        s0 = self.s0
        self.cmb_media = QComboBox()  # no longer shown – the media type follows the roll
        self.ed_weights = QLineEdit(", ".join(str(w) for w in (s0.weights or [])))
        self.ed_weights.setToolTip(tr("Rollen mit dieser Grammatur werden für Pläne verwendet (leer = alle Rollen)"))
        if self.kind == "plan":
            f.addRow(tr("Planpapier g/m²:"), self.ed_weights)
        self.cmb_frame = QComboBox()
        fill_combo(self.cmb_frame, [(k, tr(t)) for k, t in FRAME_TEXT.items()], s0.frame)
        self.cmb_frame.setToolTip(
            tr(
                "Zwei Außenlinien: gedruckt wird bis zur äußeren – sie verschwindet, um den "
                "Plan bleibt ein exakter Rand. Sonst: Inhalt + Rand."
            )
        )
        f.addRow(tr("Druckbereich:"), self.cmb_frame)
        self.spn_margin = QDoubleSpinBox()
        self.spn_margin.setRange(0, 100)
        self.spn_margin.setDecimals(1)
        self.spn_margin.setSuffix(" mm")
        self.spn_margin.setValue(s0.margin_mm)
        f.addRow(tr("Rand ohne Außenlinien:"), self.spn_margin)
        self.cmb_rotate = QComboBox()
        fill_combo(self.cmb_rotate, [(k, tr(t)) for k, t in ROTATE_TEXT.items()], s0.rotate)
        f.addRow(tr("Lage:"), self.cmb_rotate)
        row = QHBoxLayout()
        self.cmb_scale = QComboBox()
        fill_combo(self.cmb_scale, [(k, tr(t)) for k, t in SCALE_TEXT.items()], s0.scale_mode)
        row.addWidget(self.cmb_scale)
        self.spn_scale = QDoubleSpinBox()
        self.spn_scale.setRange(1, 1000)
        self.spn_scale.setDecimals(1)
        self.spn_scale.setSuffix(" %")
        self.spn_scale.setValue(s0.scale_pct)
        self.spn_scale.setToolTip(tr("100 % = tatsächliche Größe (Maßstab bleibt)"))
        row.addWidget(self.spn_scale)
        self.spn_scale_mm = QDoubleSpinBox()
        self.spn_scale_mm.setRange(0, 100000)
        self.spn_scale_mm.setDecimals(1)
        self.spn_scale_mm.setSuffix(" mm")
        self.spn_scale_mm.setValue(s0.scale_mm or 0)
        self.spn_scale_mm.setToolTip(tr("Endmaß der Kante ohne Überfüller – die andere Kante folgt im Verhältnis"))
        row.addWidget(self.spn_scale_mm)
        f.addRow(tr("Skalierung:"), row)

    def _build_finishing_rows(self, f):
        """Bleed, crop marks, hairlines, fold marks, nesting on the roll, and drawings wider than the roll."""
        s0 = self.s0
        row = QHBoxLayout()
        self.spn_bleed = QDoubleSpinBox()
        self.spn_bleed.setRange(0, 50)
        self.spn_bleed.setDecimals(1)
        self.spn_bleed.setSuffix(" mm")
        self.spn_bleed.setValue(s0.bleed_mm)
        row.addWidget(self.spn_bleed)
        self.cmb_bleed = QComboBox()
        fill_combo(self.cmb_bleed, [(k, tr(t)) for k, t in BLEED_TEXT.items()], s0.bleed_mode)
        row.addWidget(self.cmb_bleed)
        self.btn_bcolor = QPushButton()
        self.btn_bcolor.setToolTip(tr("Farbe des Überfüllers"))
        self.btn_bcolor.setFixedWidth(36)
        self.btn_bcolor.clicked.connect(self._pick_color)
        row.addWidget(self.btn_bcolor)
        f.addRow(tr("Überfüller:"), row)
        self.chk_marks = QCheckBox(tr("Schnittmarken"))
        self.chk_marks.setChecked(s0.crop_marks)
        f.addRow("", self.chk_marks)
        self.chk_hair = QCheckBox(tr("Haarlinien auf {0} mm anheben").format(pp.mm_text(s0.hairline_mm)))
        self.chk_hair.setToolTip(tr("Linien, die dünner sind, druckt der Plotter kaum oder gar nicht"))
        self.chk_hair.setChecked(s0.fix_hairlines)
        f.addRow("", self.chk_hair)
        self.chk_fold = QCheckBox(tr("Faltmarken nach DIN 824"))
        self.chk_fold.setToolTip(tr("Kurze Marken an den Falzstellen (Form A, vereinfacht) – für Falten von Hand"))
        self.chk_fold.setChecked(s0.fold_marks)
        if self.kind == "plan":
            f.addRow("", self.chk_fold)
        row = QHBoxLayout()
        self.chk_nest = QCheckBox(tr("Nebeneinander auf die Rolle"))
        self.chk_nest.setToolTip(
            tr("Mehrere Stücke nebeneinander – spart Laufmeter (die Reihenfolge ergibt sich dann aus der Verteilung)")
        )
        self.chk_nest.setChecked(s0.nest)
        row.addWidget(self.chk_nest)
        self.spn_gap = QDoubleSpinBox()
        self.spn_gap.setRange(0, 100)
        self.spn_gap.setDecimals(1)
        self.spn_gap.setSuffix(" mm")
        self.spn_gap.setPrefix(tr("Abstand "))
        self.spn_gap.setValue(s0.gap_mm)
        row.addWidget(self.spn_gap)
        f.addRow("", row)
        row = QHBoxLayout()
        self.cmb_over = QComboBox()
        fill_combo(self.cmb_over, [(k, tr(t)) for k, t in OVER_TEXT.items()], s0.overwidth)
        self.cmb_over.setToolTip(tr("Was passiert, wenn ein Stück auf keine Rolle passt"))
        row.addWidget(self.cmb_over, 1)
        self.spn_overlap = QDoubleSpinBox()
        self.spn_overlap.setRange(0, 200)
        self.spn_overlap.setDecimals(0)
        self.spn_overlap.setSuffix(" mm")
        self.spn_overlap.setPrefix(tr("Überlappung "))
        self.spn_overlap.setValue(s0.overlap_mm)
        row.addWidget(self.spn_overlap)
        f.addRow(tr("Breiter als die Rolle:"), row)

    def _build_banner_group(self, rv):
        """Group "Banner und Schneiden": hem, eyelets, CutContour and register marks."""
        s0 = self.s0
        g = QGroupBox(tr("Banner und Schneiden"))
        g.setCheckable(False)
        fb = QFormLayout(g)
        row = QHBoxLayout()
        self.spn_hem = QDoubleSpinBox()
        self.spn_hem.setRange(0, 200)
        self.spn_hem.setDecimals(0)
        self.spn_hem.setSuffix(" mm")
        self.spn_hem.setSpecialValueText(tr("kein"))
        self.spn_hem.setValue(s0.hem_mm)
        self.spn_hem.setToolTip(tr("Saum (umschlagen) oder Tunnel (für Stangen) – Zugabe außerhalb des Endformats"))
        row.addWidget(self.spn_hem)
        self.chk_hem = {}
        for k, t in (("l", "links"), ("r", "rechts"), ("t", "oben"), ("b", "unten")):
            c = QCheckBox(tr(t))
            c.setChecked(k in s0.hem_sides)
            self.chk_hem[k] = c
            row.addWidget(c)
        fb.addRow(tr("Saum/Tunnel:"), row)
        row = QHBoxLayout()
        self.spn_grom = QDoubleSpinBox()
        self.spn_grom.setRange(0, 3000)
        self.spn_grom.setDecimals(0)
        self.spn_grom.setSuffix(" mm")
        self.spn_grom.setSpecialValueText(tr("keine"))
        self.spn_grom.setValue(s0.grommet_spacing_mm)
        self.spn_grom.setToolTip(tr("Ösenmarken: an den Ecken und dazwischen mit höchstens diesem Abstand"))
        row.addWidget(self.spn_grom)
        self.spn_grom_in = QDoubleSpinBox()
        self.spn_grom_in.setRange(3, 200)
        self.spn_grom_in.setDecimals(0)
        self.spn_grom_in.setSuffix(" mm")
        self.spn_grom_in.setPrefix(tr("vom Rand "))
        self.spn_grom_in.setValue(s0.grommet_inset_mm)
        row.addWidget(self.spn_grom_in)
        fb.addRow(tr("Ösen alle:"), row)
        self.chk_cut = QCheckBox(tr("CutContour am Bildrand (Print & Cut)"))
        self.chk_cut.setToolTip(
            tr(
                "Schneidlinie in der Sonderfarbe CutContour um das Endformat (inkl. Saum) – "
                "VersaWorks, CutStudio und andere schneiden danach. Freie Konturen: "
                "Druckaufbereitung → CutContour."
            )
        )
        self.chk_cut.setChecked(s0.cut_contour)
        fb.addRow("", self.chk_cut)
        self.chk_pcm = QCheckBox(tr("Passermarken (Winkel) an den Ecken"))
        self.chk_pcm.setToolTip(tr("Nur wenn das Schneideprogramm keine eigenen setzt (VersaWorks setzt sie selbst)"))
        self.chk_pcm.setChecked(s0.printcut_marks)
        fb.addRow("", self.chk_pcm)
        rv.addWidget(g)

    def _build_bottom_row(self, v):
        """Bottom row: status text, history, defaults, saving as PDF, print and close."""
        # ---- bottom ----
        bot = QHBoxLayout()
        self.lbl_state = QLabel()
        self.lbl_state.setWordWrap(True)
        self.lbl_state.setStyleSheet(f"color: {theme.MUTED};")
        bot.addWidget(self.lbl_state, 1)
        self.btn_hist = QPushButton(icon("history"), tr("Verlauf"))
        self.btn_hist.setToolTip(
            tr(
                "Frühere Drucke mit denselben Dateien, Mengen und Einstellungen wieder öffnen; "
                "„Verlauf aufräumen“ verwirft sie"
            )
        )
        self.btn_hist.clicked.connect(self._history_menu)
        bot.addWidget(self.btn_hist)
        b = QPushButton(tr("Als Standard speichern"))
        b.setToolTip(
            tr(
                "Die jetzigen Einstellungen (ohne Abweichungen einzelner Pläne) als Standard merken. Nach "
                "dem Drucken geht das Fenster immer auf den Standard zurück."
            )
        )
        b.clicked.connect(self._save_standard)
        bot.addWidget(b)
        b = QPushButton(tr("Standard"))
        b.setToolTip(tr("Alle Einstellungen auf den Standard zurücksetzen"))
        b.clicked.connect(self._load_standard)
        bot.addWidget(b)
        self.btn_pdf = QPushButton(icon("save"), tr("Als PDF speichern …"))
        self.btn_pdf.setToolTip(tr("Alle Druckseiten (je Plan eine) zum Prüfen oder Weitergeben"))
        self.btn_pdf.clicked.connect(self._save_pdf)
        bot.addWidget(self.btn_pdf)
        self.btn_print = QPushButton(icon("print"), tr("Drucken"))
        self.btn_print.setDefault(True)
        self.btn_print.clicked.connect(self._print)
        bot.addWidget(self.btn_print)
        b = QPushButton(tr("Schließen"))
        b.clicked.connect(self.reject)
        bot.addWidget(b)
        v.addLayout(bot)

    def _connect_settings(self):
        """Connect the settings: changes place or detect anew; per-plan settings apply to the selection."""
        s0 = self.s0
        # changes: only place anew or detect anew
        for w in (self.spn_copies, self.spn_gap, self.spn_overlap, self.spn_hem, self.spn_grom, self.spn_grom_in):
            w.valueChanged.connect(self._changed)
        for w in (
            self.chk_collate,
            self.chk_marks,
            self.chk_hair,
            self.chk_fold,
            self.chk_nest,
            self.chk_cut,
            self.chk_pcm,
            *self.chk_hem.values(),
        ):
            w.toggled.connect(self._changed)
        for w in (self.cmb_order, self.cmb_color, self.cmb_over, self.cmb_copies, self.cmb_qmode):
            w.currentIndexChanged.connect(self._changed)
        self.ed_weights.editingFinished.connect(self._changed)
        # settings per plan: apply to the selection (nothing or everything selected: to all)
        self.g = {k: getattr(s0, k) for k in pp.OV_KEYS}
        self.g["roll_pick"] = s0.roll_pick
        for w, key, get in (
            (self.cmb_mat, "material", lambda: self.cmb_mat.currentData() or ""),
            (self.cmb_roll, "roll_pick", lambda: self.cmb_roll.currentData() or ""),
            (self.cmb_align, "align", lambda: self.cmb_align.currentData() or "center"),
            (self.cmb_rotate, "rotate", lambda: self.cmb_rotate.currentData() or "auto"),
            (self.cmb_bleed, "bleed_mode", lambda: self.cmb_bleed.currentData() or "mirror"),
            (self.cmb_frame, "frame", lambda: self.cmb_frame.currentData() or "auto"),
        ):
            w.currentIndexChanged.connect(lambda _i, key=key, get=get: self._set_field({key: get()}))
        self.spn_bleed.valueChanged.connect(lambda v: self._set_field({"bleed_mm": v}))
        self.spn_margin.valueChanged.connect(lambda v: self._set_field({"margin_mm": v}))
        self.cmb_scale.currentIndexChanged.connect(self._scale_changed)
        self.spn_scale.valueChanged.connect(self._scale_changed)
        self.spn_scale_mm.valueChanged.connect(self._scale_changed)
        self.tree.itemSelectionChanged.connect(self._load_fields)
        self._scale_widgets()
