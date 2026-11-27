# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Print dialog: building the tab "General" – pages, page handling (multiple, booklet, poster, step and repeat), scaling, marks and the device sections."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import layout
from ..l10n import tr
from . import theme
from .common import CollapsibleSection, fill_combo
from .printwidgets import PageBox, SideTab


class PrintBuildMixin:
    """Construction of the "General" tab of PrintDialog."""

    @staticmethod
    def _scroll(w):
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        sa.setWidget(w)
        return sa

    # ================================================================== #
    # structure of "Allgemein"
    # ================================================================== #
    def _section(self, title: str, expanded: bool = True):
        """Uniform collapsible section with a form in the main layout."""
        sec = CollapsibleSection(title, expanded=expanded)
        self._col.addWidget(sec)
        inner = QWidget()
        sec.body_layout.addWidget(inner)
        sec.form = QFormLayout(inner)
        return sec

    def _build_general(self):
        """Build the settings column of the dialog, section by section from top to bottom."""
        self._col = QVBoxLayout(self.general)
        self._build_printer_section()
        self._build_pages_section()
        self._build_mode_group()
        self._build_multiple_page()
        self._build_booklet_page()
        self._build_poster_page()
        self._build_step_repeat_window()
        self._build_scale_section()
        self._build_device_sections()
        self._build_extra_sections()
        self._connect_general()

    def _build_printer_section(self):
        """Section "Drucker": printer, state, admin defaults, password protection (PDF target), copies."""
        # printer
        sec = self._section(tr("Drucker"))
        f = sec.form
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
        # only when saving as PDF: password protection
        self.pw_box = QWidget()
        pv = QVBoxLayout(self.pw_box)
        pv.setContentsMargins(0, 0, 0, 0)
        self.chk_pw = QCheckBox(tr("PDF mit Passwort schützen (AES-256)"))
        pv.addWidget(self.chk_pw)
        prow = QHBoxLayout()
        self.ed_pw, self.ed_pw2 = QLineEdit(), QLineEdit()
        for ed, ph in ((self.ed_pw, tr("Passwort")), (self.ed_pw2, tr("wiederholen"))):
            ed.setEchoMode(QLineEdit.EchoMode.Password)
            ed.setPlaceholderText(ph)
            ed.setEnabled(False)
            prow.addWidget(ed)
        pv.addLayout(prow)
        self.chk_pw.toggled.connect(lambda on: (self.ed_pw.setEnabled(on), self.ed_pw2.setEnabled(on)))
        self.pw_box.setToolTip(
            tr(
                "Zum Öffnen der gespeicherten Datei wird das Passwort verlangt. "
                "Es wird nirgends gespeichert – gut merken."
            )
        )
        self.pw_box.hide()
        f.addRow(tr("Schutz:"), self.pw_box)
        self._pw_form = f
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

    def _build_pages_section(self):
        """Section "Zu druckende Seiten": all, current page or a range; odd/even; reverse order."""
        # pages
        sec = self._section(tr("Zu druckende Seiten"))
        gw = QWidget()
        sec.body_layout.addWidget(gw)
        gl = QGridLayout(gw)
        self.rb_all = QRadioButton(tr("Alle"))
        self.rb_cur = QRadioButton(tr("Aktuelle Seite ({0})").format(self.current + 1))
        self.rb_range = QRadioButton(tr("Seiten:"))
        self.rb_all.setChecked(True)
        self.ed_range = QLineEdit()
        self.ed_range.setPlaceholderText(tr("z. B. 1-3, 5, 8-{0}").format(len(self.doc)))
        self.ed_range.textEdited.connect(lambda _: self.rb_range.setChecked(True))
        self.cmb_subset = QComboBox()
        fill_combo(
            self.cmb_subset,
            [
                ("all", tr("Alle Seiten im Bereich")),
                ("odd", tr("Nur ungerade Seiten")),
                ("even", tr("Nur gerade Seiten")),
            ],
            self.s.subset,
        )
        self.chk_reverse = QCheckBox(tr("Seiten in umgekehrter Reihenfolge"))
        self.chk_reverse.setChecked(self.s.reverse)
        gl.addWidget(self.rb_all, 0, 0)
        gl.addWidget(self.rb_cur, 1, 0)
        gl.addWidget(self.rb_range, 2, 0)
        gl.addWidget(self.ed_range, 2, 1)
        gl.addWidget(self.cmb_subset, 3, 0, 1, 2)
        gl.addWidget(self.chk_reverse, 4, 0, 1, 2)

    def _build_mode_group(self):
        """Group "Was soll gedruckt werden?": the mode buttons, the step-and-repeat tab and the stack of mode pages."""
        v = self._col
        # page size and handling
        sec = CollapsibleSection(tr("Was soll gedruckt werden?"), expanded=True)
        self.handling_group = sec  # anchored at once, uniform heading
        v.addWidget(sec)
        gv = sec.body_layout
        tog = QVBoxLayout()  # buttons below each other: always readable
        self.handling_btns = {}
        bg = QButtonGroup(self)
        for key, text, page in [
            ("size", tr("Einzelblätter"), 0),
            ("multiple", tr("Mehrere pro Blatt"), 1),
            ("booklet", tr("Broschüre"), 2),
            ("poster", tr("Poster"), 3),
        ]:
            b = QPushButton(text)
            b.setCheckable(True)
            b.setProperty("handling", key)
            b.setProperty("page", page)
            bg.addButton(b)
            tog.addWidget(b)
            self.handling_btns[key] = b
        gv.addLayout(tog)
        # Step & repeat: not a mode but a window of its own that acts on the chosen mode
        # (single sheets: the pages, booklet: the spreads) – incl. step 2
        # as a vertical yellow tab at the left edge of the dialog (opens/closes the window)
        self.btn_srwin = SideTab(tr("Step && Repeat …").replace("&&", "&"))
        self.btn_srwin.setToolTip(
            tr(
                "Öffnet das Step-&-Repeat-Fenster: Mehrfachnutzen zuschalten und einstellen, "
                "optional Schritt 2 auf ein Zielformat. Wirkt nur zusammen mit diesem Druckdialog."
            )
        )
        self.btn_srwin.clicked.connect(self._toggle_sr_window)
        _tabcol = QVBoxLayout()
        _tabcol.setContentsMargins(0, 40, 0, 0)
        _tabcol.addWidget(self.btn_srwin)
        _tabcol.addStretch(1)
        _m = self._root.contentsMargins()
        self._root.setContentsMargins(0, _m.top(), _m.right(), _m.bottom())
        self._root.insertLayout(0, _tabcol)
        self.lbl_modehint = QLabel()
        self.lbl_modehint.setWordWrap(True)
        self.lbl_modehint.setStyleSheet(f"color: {theme.MUTED};")
        gv.addWidget(self.lbl_modehint)
        self.stack = PageBox()
        gv.addWidget(self.stack)
        self.stack.addWidget(QWidget())  # page 0: single sheets – the options are under "Wie aufs Blatt?"

        # -- the size options (fit/actual/…) now live in the group
        #    "Wie aufs Blatt?" further down – no longer a stack page of their own.
        self._handling_buttons = bg

    def _build_multiple_page(self):
        """Mode page "Mehrere pro Blatt": pages per sheet, grid, order, gap, border."""
        L = self.s.layout
        # -- several per sheet
        mg = QWidget()
        self.stack.addWidget(mg)  # anchor at once, then fill
        ml = QFormLayout(mg)
        row = QHBoxLayout()
        self.cmb_nup = QComboBox()
        fill_combo(
            self.cmb_nup,
            [(n, str(n)) for n in (2, 4, 6, 8, 9, 16)] + [(0, tr("Benutzerdefiniert"))],
            0 if (L.cols and L.rows) else (L.nup if L.nup > 1 else 2),
        )
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
        fill_combo(
            self.cmb_tile,
            [
                ("fit", tr("An Kachel anpassen")),
                ("actual", tr("Tatsächliche Größe")),
                ("custom", tr("Benutzerdefiniert")),
            ],
            L.tile_mode,
        )
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
        self.spn_gap.setToolTip(
            tr(
                "Abstand zwischen den Kacheln. Wird von der „Nutzen-Anordnung“ im Abschnitt "
                "„Schnittmarken und Anschnitt“ übersteuert, sobald dort eine Anordnung "
                "gewählt ist (Kante an Kante / Überfüller an Überfüller / Mit Abstand)."
            )
        )
        ml.addRow(tr("Abstand:"), self.spn_gap)
        self.chk_borders = QCheckBox(tr("Seitenrand drucken"))
        self.chk_borders.setChecked(L.borders)
        ml.addRow("", self.chk_borders)

    def _build_booklet_page(self):
        """Mode page "Broschüre": binding, signatures, blank pages, spreads for step and repeat."""
        # -- Booklet
        bw = QWidget()
        self.stack.addWidget(bw)  # anchor at once, then fill
        bl = QFormLayout(bw)
        self._build_booklet_binding(bl)
        self._build_booklet_marks(bl)
        self._build_booklet_spreads(bl)

    def _build_booklet_binding(self, bl):
        """Kind of binding, signatures, which pages, binding side, gutter and creep, blank pages."""
        L = self.s.layout
        self.cmb_bkind = QComboBox()
        fill_combo(
            self.cmb_bkind,
            [
                ("saddle", tr("Standard (alle Bögen ineinander, einmal falzen)")),
                ("grouped", tr("Gruppierte Lagen (je Lage mehrere Bögen)")),
                ("stack", tr("Einzelbögen gestapelt (Klebebindung)")),
            ],
            L.booklet_kind,
        )
        self.cmb_bkind.setToolTip(
            tr(
                "Standard/Sammelheftung: ein Heft, Bögen ineinandergesteckt und in der Mitte geheftet. "
                "Gruppierte Lagen: z. B. je 4 Bögen = 16 Seiten pro Lage, Lagen hintereinander "
                "(Fadenheftung, dicke Hefte). Einzelbögen: jeder Bogen einzeln gefalzt, "
                "gestapelt (Klebebindung, Blockheftung)."
            )
        )
        bl.addRow(tr("Bindeart:"), self.cmb_bkind)
        self.spn_persig = QSpinBox()
        self.spn_persig.setRange(1, 32)
        self.spn_persig.setValue(L.booklet_per_sig)
        self.spn_persig.setSuffix(tr(" Bögen je Lage"))
        self.spn_persig.setToolTip(
            tr(
                "Nur bei „Gruppierte Lagen“: Anzahl Bögen je Lage. Beim Standard (Sammelheftung) "
                "liegen alle Bögen sowieso ineinander – die Zahl ist dort ohne Bedeutung."
            )
        )
        bl.addRow("", self.spn_persig)
        self.spn_persig.setVisible(L.booklet_kind == "grouped")
        # changing "sheets per signature" = grouped signatures (otherwise the number would have no effect with saddle stitching)
        self.spn_persig.valueChanged.connect(
            lambda _v: (
                self.cmb_bkind.currentData() == "saddle"
                and self.cmb_bkind.setCurrentIndex(max(0, self.cmb_bkind.findData("grouped")))
            )
        )
        self.cmb_bsides = QComboBox()
        fill_combo(
            self.cmb_bsides,
            [("both", tr("Beidseitig")), ("front", tr("Nur Vorderseiten")), ("back", tr("Nur Rückseiten"))],
            L.booklet_sides,
        )
        bl.addRow(tr("Broschürenseiten:"), self.cmb_bsides)
        self.cmb_binding = QComboBox()
        fill_combo(
            self.cmb_binding,
            [("left", tr("Links (normal)")), ("right", tr("Rechts (z. B. Hebräisch/Arabisch)"))],
            L.booklet_binding,
        )
        bl.addRow(tr("Bindung:"), self.cmb_binding)
        self.ed_bsheets = QLineEdit(L.booklet_sheets)
        self.ed_bsheets.setPlaceholderText(tr("alle – oder z. B. 1-3"))
        bl.addRow(tr("Bögen:"), self.ed_bsheets)
        self.spn_gutter = QDoubleSpinBox()
        self.spn_gutter.setRange(0, 50)
        self.spn_gutter.setSuffix(tr(" mm"))
        self.spn_gutter.setValue(L.booklet_gutter_mm)
        bl.addRow(tr("Bundsteg:"), self.spn_gutter)
        self.spn_creep = QDoubleSpinBox()
        self.spn_creep.setRange(0, 2)
        self.spn_creep.setDecimals(2)
        self.spn_creep.setSingleStep(0.05)
        self.spn_creep.setSuffix(tr(" mm je Bogen"))
        self.spn_creep.setValue(L.booklet_creep_mm)
        self.spn_creep.setToolTip(
            tr(
                "Bundzug: innere Bögen stehen nach dem Falzen vorne über. Ihr Inhalt wird je Bogen "
                "um diesen Wert zum Falz verschoben (ungefähr die Papierstärke, z. B. 0,1 mm "
                "bei 80 g/m², 0,15 mm bei 150 g/m²)."
            )
        )
        bl.addRow(tr("Bundzug:"), self.spn_creep)
        self.cmb_blanks = QComboBox()
        fill_combo(
            self.cmb_blanks,
            [("end", tr("am Ende")), ("before_back", tr("vor der letzten Seite (Rückseite bleibt hinten)"))],
            L.booklet_blanks,
        )
        bl.addRow(tr("Leerseiten:"), self.cmb_blanks)
        self.ed_blank = QLineEdit(L.booklet_blank_text)
        self.ed_blank.setPlaceholderText(tr("Hinweistext auf Leerseiten (optional), z. B. „Diese Seite bleibt leer“"))
        bl.addRow("", self.ed_blank)

    def _build_booklet_marks(self, bl):
        """Fold and stitch marks (only for the old path, hidden)."""
        L = self.s.layout
        mrow = QHBoxLayout()
        self.chk_bfold = QCheckBox(tr("Falzmarken"))
        self.chk_bfold.setChecked(L.booklet_fold_marks)
        self.chk_breg = QCheckBox(tr("Passermarken"))
        self.chk_breg.setChecked(L.booklet_reg_marks)
        self.chk_bcoll = QCheckBox(tr("Flattermarken"))
        self.chk_bcoll.setChecked(L.booklet_collation_marks)
        self.chk_bcoll.setToolTip(
            tr(
                "Balken am Rücken jeder Lage, je Lage versetzt – beim Zusammentragen ergibt sich "
                "eine Treppe; eine fehlende oder vertauschte Lage fällt sofort auf."
            )
        )
        for c in (self.chk_bfold, self.chk_breg, self.chk_bcoll):
            mrow.addWidget(c)
        mrow.addStretch()
        bl.addRow(tr("Marken:"), mrow)
        # the folded-sheet options only apply to the old path (sheet fitted onto the paper) – hidden
        for _w in (self.spn_gutter, self.spn_creep):
            bl.setRowVisible(_w, False)
        bl.setRowVisible(mrow, False)

    def _build_booklet_spreads(self, bl):
        """Spreads for step and repeat, the overview and the hint line."""
        L = self.s.layout
        # Spreads for step and repeat: booklet -> its own document (one opened spread per sheet side),
        # which is then imposed in "Nutzen" mode with arrangement/bleed/crop marks/step 2
        self.cmb_bspread = QComboBox()
        fill_combo(
            self.cmb_bspread,
            [("side", tr("nebeneinander (seitlich gebunden)")), ("top", tr("übereinander (oben gebunden)"))],
            L.booklet_spread,
        )
        self.cmb_bspread.setToolTip(
            tr(
                "Wie die zwei Seiten eines aufgeklappten Bogens aneinandergesetzt werden – "
                "nur für „Druckbögen erzeugen“."
            )
        )
        bl.addRow(tr("Seiten aneinander:"), self.cmb_bspread)
        self.chk_bnutzen = QCheckBox(tr("Als Druckbögen montieren (Überfüller, Schnittmarken, Nutzen)"))
        self.chk_bnutzen.setChecked(bool(getattr(L, "booklet_nutzen", False)))
        self.chk_bnutzen.setToolTip(
            tr(
                "Statt Falzbogen auf dem Druckerblatt: je Bogenseite ein aufgeklappter Bogen im "
                "Endformat (z. B. 420 × 210 mm), so oft wie möglich aufs Blatt – mit "
                "„Schnittmarken und Anschnitt“: Nutzen-Anordnung (Kante an Kante / Überfüller "
                "an Überfüller / Abstand), Überfüller, Schnittmarken. Vorschau und Druck zeigen "
                "genau das."
            )
        )
        self.chk_bnutzen.setChecked(True)  # booklet ALWAYS as spreads – set BEFORE
        self.chk_bnutzen.setVisible(False)  # connecting (the dialog is still being built here)
        self.chk_bnutzen.toggled.connect(self._changed)
        self.cmb_bspread.currentIndexChanged.connect(self._changed)
        bl.addRow("", self.chk_bnutzen)

        self.btn_bspreads = QPushButton(tr("Druckbögen erzeugen (für Nutzen) …"))
        self.btn_bspreads.setToolTip(
            tr(
                "Erzeugt ein neues Dokument: je Bogenseite ein aufgeklappter Bogen im Endformat "
                "(z. B. 420 × 210 mm), Anschnitt nur außen, in Ausschieß-Reihenfolge. "
                "Dieses Dokument dann mit „Nutzen“ drucken – dort Anordnung (Kante an Kante / "
                "Überfüller an Überfüller / Abstand), Überfüller, Schnittmarken und Schritt 2."
            )
        )
        self.btn_bspreads.clicked.connect(self._booklet_spreads_output)
        bl.addRow("", self.btn_bspreads)
        self.btn_overview = QPushButton(tr("Bogenübersicht …"))
        self.btn_overview.setToolTip(tr("Alle Bögen als Miniaturen – Verteilung der Seiten prüfen"))
        self.btn_overview.clicked.connect(self._sheet_overview)
        bl.addRow("", self.btn_overview)
        self.lbl_bhint = QLabel()
        self.lbl_bhint.setWordWrap(True)
        self.lbl_bhint.setStyleSheet(f"color: {theme.MUTED};")
        bl.addRow(self.lbl_bhint)

    def _build_poster_page(self):
        """Mode page "Poster": tiling over several sheets with overlap, marks and labels."""
        L = self.s.layout
        # -- Poster
        ow = QWidget()
        self.stack.addWidget(ow)  # anchor at once, then fill
        ol = QFormLayout(ow)
        self.cmb_pmode = QComboBox()
        fill_combo(
            self.cmb_pmode,
            [("scale", tr("Maßstab")), ("sheets", tr("Anzahl Blätter")), ("target", tr("Zielformat"))],
            L.poster_mode,
        )
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
        fill_combo(
            self.cmb_ptarget,
            [(k, tr("{0} ({1} × {2} mm)").format(k, w, h)) for k, (w, h) in layout.POSTER_FORMATS.items()]
            + [("custom", tr("Benutzerdefiniert"))],
            L.poster_target,
        )
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

    def _build_step_repeat_window(self):
        """The step-and-repeat window (a child window of the dialog) including the block for step 2."""
        L = self.s.layout
        # -- step and repeat – formerly the tab "Weitere Optionen"
        # A freely movable window of its own (move, minimise, close) – child of the print dialog:
        # it lives and acts only with it; closing hides it, the settings stay.
        self.sr_win = QWidget(
            self,
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowTitleHint,
        )
        self.sr_win.setWindowTitle(tr("Step & Repeat – Passermark"))
        self.sr_win.resize(520, 640)
        _wl = QVBoxLayout(self.sr_win)
        self.chk_sr = QCheckBox(tr("Step && Repeat aktiv (Mehrfachnutzen)"))
        self.chk_sr.setStyleSheet(f"font-weight: bold; color: {theme.ACCENT_TEXT};")
        self.chk_sr.setChecked(bool(L.step_repeat or getattr(L, "sr_multi", False)))
        self.chk_sr.setToolTip(
            tr(
                "Einzelblätter: jede Seite mehrfach aufs Blatt. Broschüre: jeder Druckbogen "
                "mehrfach aufs Blatt. Aus: alles wird einmal gesetzt."
            )
        )
        _wl.addWidget(self.chk_sr)
        self.btn_srwin.window_fn = lambda: getattr(self, "sr_win", None)
        self.btn_srwin.active_fn = self.chk_sr.isChecked
        self.btn_srwin.watch(self.sr_win)
        self.chk_sr.toggled.connect(lambda *_: self.btn_srwin.update())
        _sc = QScrollArea(self.sr_win)
        _sc.setWidgetResizable(True)
        _wl.addWidget(_sc, 1)
        g = QWidget()
        _sc.setWidget(g)
        f = QFormLayout(g)
        self._build_sr_step1(f)
        self._build_sr_step2(f)
        note = QLabel(
            tr(
                "Wirkt auf den im Druckdialog gewählten Modus: Einzelblätter – jede Seite mehrfach, "
                "Broschüre – jeder Druckbogen mehrfach. Anordnung, Abstand, Überfüller und Schnittmarken "
                "stehen im Druckdialog unter „Schnittmarken und Anschnitt“. Bei „Automatisch“ wird zuerst "
                "eine Lage gesucht, in der das Raster aufs Blatt passt, dann die mit den meisten Nutzen."
            )
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {theme.MUTED};")
        f.addRow(note)

    def _build_sr_step1(self, f):
        """Step 1: how many copies, their size, sheet orientation, rotation and order."""
        L = self.s.layout
        self.cmb_srmode = QComboBox()
        fill_combo(
            self.cmb_srmode,
            [("auto", tr("So viele wie aufs Blatt passen")), ("grid", tr("Raster vorgeben"))],
            L.sr_mode,
        )
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
        fill_combo(
            self.cmb_srby,
            [("percent", tr("Maßstab in %")), ("short", tr("Kurze Kante auf …")), ("long", tr("Lange Kante auf …"))],
            L.sr_by,
        )
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
        self.lbl_srsize.setStyleSheet(f"color: {theme.ACCENT_TEXT};")
        f.addRow("", self.lbl_srsize)
        self.cmb_srorient = QComboBox()
        fill_combo(
            self.cmb_srorient,
            [
                ("auto", tr("Automatisch (passend / meiste Nutzen)")),
                ("portrait", tr("Hochformat")),
                ("landscape", tr("Querformat")),
            ],
            L.sr_orientation,
        )
        f.addRow(tr("Blatt:"), self.cmb_srorient)
        self.cmb_srrot = QComboBox()
        fill_combo(
            self.cmb_srrot,
            [
                ("auto", tr("Automatisch (Nutzen bleiben aufrecht, das Blatt dreht mit)")),
                ("0", tr("Nicht drehen")),
                ("90", tr("Um 90° drehen")),
            ],
            L.sr_rotate,
        )
        f.addRow(tr("Nutzen drehen:"), self.cmb_srrot)
        # "Anordnung" + "Abstand" live in the crop marks/bleed section
        # (they act there too: step-and-repeat gap = a bleed/cutting question)
        self.chk_srseq = QCheckBox(tr("Je Nutzen die nächste Seite (variable Daten, Nummerierung)"))
        self.chk_srseq.setChecked(L.sr_sequence)
        self.chk_srseq.setToolTip(
            tr(
                "Statt eine Seite zu vervielfachen, kommt auf jeden Nutzen die nächste Seite – "
                "z. B. nach „Variable Daten“ jede Karte mit eigenem Namen oder Code."
            )
        )
        f.addRow(self.chk_srseq)
        self.cmb_srstack = QComboBox()
        fill_combo(
            self.cmb_srstack,
            [("row", tr("Bogen für Bogen")), ("stack", tr("Schneiden und Stapeln (Stapel fortlaufend)"))],
            L.sr_stack,
        )
        self.cmb_srstack.setToolTip(
            tr(
                "Schneiden und Stapeln: Bögen übereinanderlegen, schneiden – jeder Stapel ist "
                "fortlaufend nummeriert (1, 2, 3 … im ersten Stapel, dann der zweite)."
            )
        )
        f.addRow(tr("Reihenfolge:"), self.cmb_srstack)

    def _build_sr_step2(self, f):
        """Step 2 (optional): put the finished sheet onto a target format once more. A block of its own that can move into the booklet panel."""
        L = self.s.layout
        self.chk_sr2 = QCheckBox(tr("Schritt 2 (optional): den montierten Bogen erneut auf ein Zielformat setzen"))
        self.chk_sr2.setChecked(L.sr_pass2)
        self.chk_sr2.setToolTip(
            tr(
                "Erst wird wie oben eingestellt auf das gewählte Papier montiert (Schritt 1), "
                "dann wird dieses Ergebnis nochmals aufs hier gewählte Zielformat gesetzt – "
                "aneinandergereiht und mittig, inhaltlich unverändert. Schritt 2 fügt nie "
                "Überfüller oder Schnittmarken hinzu: was der montierte Bogen schon hat, "
                "bleibt erhalten – Schnittmarken und Überfüller aus Schritt 1 also mit "
                "dabei. Der fertige Schritt-1-Bogen wird dabei so oft wie möglich (oder im "
                "eingestellten Raster) aufs Zielformat gesetzt, immer mittig. Passt er (auch "
                "gedreht) nicht, wird trotzdem montiert und gewarnt – beschnitten wird am Rand. "
                "Die Vorschau zeigt das Ergebnis wie bei Schritt 1. Der Button gibt es als "
                "neues Dokument aus (neuer Reiter) und schließt diesen Dialog."
            )
        )
        # Step 2 as a block of its own: it lives in the step-and-repeat panel – with "booklet as spreads"
        # it moves into the booklet panel (_place_sr2), values and logic stay the same
        self.sr2_box = QWidget(self)
        f2 = QFormLayout(self.sr2_box)
        f2.setContentsMargins(0, 0, 0, 0)
        self._sr2_home = QVBoxLayout()
        self._sr2_home.setContentsMargins(0, 0, 0, 0)
        f.addRow(self._sr2_home)
        self._sr2_home.addWidget(self.sr2_box)
        f2.addRow(self.chk_sr2)
        self.cmb_sr2fmt = QComboBox()
        f2.addRow(tr("Zielformat (Schritt 2):"), self.cmb_sr2fmt)
        row = QHBoxLayout()
        self.spn_sr2w = QDoubleSpinBox()
        self.spn_sr2w.setRange(10, 5000)
        self.spn_sr2w.setDecimals(1)
        self.spn_sr2w.setSuffix(tr(" mm"))
        self.spn_sr2w.setValue(L.sr2_w_mm)
        self.spn_sr2h = QDoubleSpinBox()
        self.spn_sr2h.setRange(10, 5000)
        self.spn_sr2h.setDecimals(1)
        self.spn_sr2h.setSuffix(tr(" mm"))
        self.spn_sr2h.setValue(L.sr2_h_mm)
        row.addWidget(self.spn_sr2w)
        row.addWidget(QLabel("×"))
        row.addWidget(self.spn_sr2h)
        row.addStretch()
        f2.addRow(tr("Eigene Maße:"), row)
        row = QHBoxLayout()
        self.spn_sr2cols = QSpinBox()
        self.spn_sr2cols.setRange(0, 10)
        self.spn_sr2cols.setSpecialValueText(tr("Automatisch"))
        self.spn_sr2cols.setValue(L.sr2_cols)
        self.spn_sr2rows = QSpinBox()
        self.spn_sr2rows.setRange(0, 10)
        self.spn_sr2rows.setSpecialValueText(tr("Automatisch"))
        self.spn_sr2rows.setValue(L.sr2_rows)
        row.addWidget(self.spn_sr2cols)
        row.addWidget(QLabel("×"))
        row.addWidget(self.spn_sr2rows)
        row.addStretch()
        f2.addRow(tr("Wie oft (0 × 0 = automatisch):"), row)
        self.btn_sr2 = QPushButton(tr("Als neues Dokument ausgeben (Schritt 1 + 2)"))
        self.btn_sr2.clicked.connect(self._sr2_output)
        f2.addRow("", self.btn_sr2)

    def _build_scale_section(self):
        """Section "Wie aufs Blatt?": scaling, orientation, crop marks and bleed, step-and-repeat arrangement and gap."""
        # the mode group is already anchored in v (right after creation)

        # How does the page get onto the sheet? – fits every print mode
        sec = self._section(tr("Wie aufs Blatt?"))
        wf = sec.form
        # The scaling choice (fit/actual/…) acts in EVERY mode:
        # fit = mode default, actual/shrink/custom override the
        # Modus-Skalierung (layout.global_scale).
        self.scale_box = QWidget()
        sec.body_layout.insertWidget(0, self.scale_box)
        sf = QFormLayout(self.scale_box)
        self._build_scale_choice(sf)
        self._build_orientation_rows(wf)
        self._build_marks_section()

    def _build_scale_choice(self, sf):
        """Fit, actual size, shrink oversized pages, or a custom scale by percent or millimetres."""
        L = self.s.layout
        self.rb_fit = QRadioButton(tr("Anpassen"))
        self.rb_actual = QRadioButton(tr("Tatsächliche Größe"))
        self.rb_shrink = QRadioButton(tr("Übergroße Seiten verkleinern"))
        self.rb_custom = QRadioButton(tr("Benutzerdefiniert:"))
        self.cmb_custom_by = QComboBox()
        fill_combo(
            self.cmb_custom_by,
            [("percent", tr("Maßstab in %")), ("short", tr("Kurze Kante auf …")), ("long", tr("Lange Kante auf …"))],
            L.custom_by,
        )
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
        self.lbl_custom.setStyleSheet(f"color: {theme.ACCENT_TEXT};")
        self.mode_group = QButtonGroup(self)
        for rb, m in [
            (self.rb_fit, "fit"),
            (self.rb_actual, "actual"),
            (self.rb_shrink, "shrink"),
            (self.rb_custom, "custom"),
        ]:
            self.mode_group.addButton(rb)
            rb.setProperty("mode", m)
            rb.setChecked(L.mode == m)
            sf.addRow(rb)
        crow = QHBoxLayout()
        crow.addWidget(self.cmb_custom_by, 1)
        crow.addWidget(self.spn_custom)
        crow.addWidget(self.spn_custom_mm)
        sf.addRow("", crow)
        sf.addRow("", self.lbl_custom)

    def _build_orientation_rows(self, wf):
        """Orientation, automatic rotation, centring and printer margins."""
        L = self.s.layout
        self.cmb_orient = QComboBox()
        fill_combo(
            self.cmb_orient,
            [
                ("auto", tr("Automatisch Hoch-/Querformat")),
                ("portrait", tr("Hochformat")),
                ("landscape", tr("Querformat")),
            ],
            L.orientation,
        )
        wf.addRow(tr("Ausrichtung:"), self.cmb_orient)
        self.chk_autorot = QCheckBox(tr("Seiten automatisch drehen"))
        self.chk_autorot.setChecked(L.autorotate)
        self.chk_center = QCheckBox(tr("Auf Blatt zentrieren"))
        self.chk_center.setChecked(L.center)
        self.chk_margins = QCheckBox(tr("Nicht bedruckbaren Rand des Druckers berücksichtigen"))
        self.chk_margins.setChecked(L.use_margins)
        for c in (self.chk_autorot, self.chk_center, self.chk_margins):
            wf.addRow("", c)

        hb = self.handling_btns.get(L.handling, self.handling_btns["size"])
        hb.setChecked(True)
        self.stack.setCurrentIndex(hb.property("page"))

    def _build_marks_section(self):
        """Section "Schnittmarken und Anschnitt": crop marks, bleed, step-and-repeat arrangement and gap."""
        L = self.s.layout
        sec = self._section(tr("Schnittmarken und Anschnitt"))
        f = sec.form
        self.chk_marks = QCheckBox(tr("Schnittmarken drucken"))
        self.chk_marks.setChecked(L.crop_marks)
        f.addRow(self.chk_marks)
        self.spn_bleed = QDoubleSpinBox()
        self.spn_bleed.setRange(0, 20)
        self.spn_bleed.setDecimals(1)
        self.spn_bleed.setSingleStep(0.5)
        self.spn_bleed.setSuffix(tr(" mm"))
        self.spn_bleed.setValue(L.bleed_mm)
        self.spn_bleed.setToolTip(
            tr("Wie viel um das Endformat herum gedruckt wird. Fehlt Anschnitt in der Datei, wird er ergänzt.")
        )
        # bleed that the document already has (TrimBox/BleedBox) – filled in by _bleed_info once the pages are known
        self.lbl_docbleed = QLabel("")
        self.lbl_docbleed.setWordWrap(True)
        self.lbl_docbleed.hide()
        f.addRow(self.lbl_docbleed)
        self.chk_docbleed = QCheckBox(tr("Vorhandenen Anschnitt aus dem Dokument verwenden"))
        self.chk_docbleed.setChecked(bool(getattr(L, "doc_bleed", True)))
        self.chk_docbleed.setToolTip(
            tr(
                "An: der Anschnitt der Datei wird mitgedruckt. Aus: gedruckt wird nur das Endformat – plus "
                "ergänzter Anschnitt, wenn „Fehlenden Anschnitt beim Druck ergänzen“ an ist."
            )
        )
        self.chk_docbleed.hide()
        f.addRow(self.chk_docbleed)
        # creating bleed is opt-in: off = only what the file has is printed (old sessions/presets with a bleed
        # value keep it on)
        self.chk_fillbleed = QCheckBox(tr("Fehlenden Anschnitt beim Druck ergänzen"))
        self.chk_fillbleed.setChecked(bool(getattr(L, "bleed_fill", True)) and L.bleed_mm > 0.05)
        self.chk_fillbleed.setToolTip(
            tr(
                "Aus: gedruckt wird nur der Anschnitt, den die Datei hat – nichts wird erzeugt. An: bis zum Wert "
                "hier wird fehlender Anschnitt durch Spiegeln oder Strecken der Seitenränder ergänzt."
            )
        )
        f.addRow(self.chk_fillbleed)
        f.addRow(tr("Anschnitt:"), self.spn_bleed)
        self.cmb_bleedmode = QComboBox()
        fill_combo(
            self.cmb_bleedmode,
            [
                ("mirror", tr("spiegeln (nahtlos, empfohlen)")),
                ("stretch", tr("strecken (Randstreifen nach außen ziehen)")),
            ],
            getattr(L, "bleed_mode", "mirror"),
        )
        self.cmb_bleedmode.setToolTip(
            tr("Wie fehlender Anschnitt entsteht – Strecken, wenn ein Spiegelbild am Rand auffallen würde")
        )
        f.addRow(tr("Fehlender Anschnitt:"), self.cmb_bleedmode)
        self.lbl_bleedadd = QLabel("")
        self.lbl_bleedadd.setWordWrap(True)
        self.lbl_bleedadd.setStyleSheet(f"color: {theme.MUTED};")
        f.addRow(self.lbl_bleedadd)
        # step-and-repeat arrangement (lives here – with the cut/cutting questions)
        self.cmb_srjoin = QComboBox()
        fill_combo(
            self.cmb_srjoin,
            [
                ("edge", tr("Kante an Kante (ein Schnitt, Anschnitt nur außen)")),
                ("bleed", tr("Überfüller an Überfüller")),
                ("gap", tr("Mit Abstand")),
            ],
            L.sr_join,
        )
        self.cmb_srjoin.setToolTip(
            tr(
                "Wie die Kacheln auf dem Blatt liegen – gilt für „Nutzen (Step & Repeat)“ "
                "UND für „Mehrere pro Blatt“; überschreibt dort den Abstand des "
                "Mehrere-Abschnitts. "
                "Kante an Kante: 0 mm Abstand, der Anschnitt liegt nur außen – "
                "ein Schnitt teilt zwei Kacheln. Überfüller an Überfüller: "
                "2 × Anschnitt als Abstand, wird in der Mitte geschnitten. "
                "Mit Abstand: der Abstand unten in diesem Abschnitt "
                "(z. B. Mindestabstand für einen Multifinisher), nie unter 2 × Anschnitt."
            )
        )
        f.addRow(tr("Nutzen-Anordnung:"), self.cmb_srjoin)
        self.spn_srgap = QDoubleSpinBox()
        self.spn_srgap.setRange(0, 50)
        self.spn_srgap.setSuffix(tr(" mm"))
        self.spn_srgap.setValue(L.sr_gap_mm)
        self.spn_srgap.setToolTip(
            tr(
                "Abstand zwischen den Kacheln bei „Mit Abstand“ – gilt für Nutzen "
                "UND für „Mehrere pro Blatt“ (überschreibt dort den Abstand des "
                "Mehrere-Abschnitts; z. B. Mindestabstand für einen Multifinisher). "
                "Nie kleiner als 2 × Anschnitt, damit der Überfüller Platz hat."
            )
        )
        f.addRow(tr("Abstand zwischen Nutzen:"), self.spn_srgap)
        note = QLabel(
            tr(
                "Schnittmarken sitzen immer am Endformat. Fehlender Anschnitt wird beim Druck durch Spiegeln oder "
                "Strecken der Seitenränder ergänzt – dauerhaft in der Datei: Seiten → Anschnitt erzeugen. Beim "
                "Anpassen wird Platz für Anschnitt und Marken gelassen; Nutzen bekommen mindestens den doppelten "
                "Anschnitt als Abstand."
            )
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {theme.MUTED};")
        f.addRow(note)

    def _build_device_sections(self):
        """Sections filled per printer (paper and output, finishing) and the colour management section."""
        # paper (filled per printer)
        self.paper_group = self._section(tr("Papier und Ausgabe"))
        self.paper_form = self.paper_group.form

        # finishing – presets + detected fields; on Windows the vendor dialog
        self.finish_group = self._section(tr("Endverarbeitung (Finisher)"))
        self.finish_form = self.finish_group.form

        # colour
        sec = self._section(tr("Farbmanagement"))
        f = sec.form
        self.cmb_material = QComboBox()
        self.cmb_material.setToolTip(tr("Papier aus der Verwaltung – setzt das passende Profil und den Intent"))
        self.cmb_profile = QComboBox()
        self.cmb_intent = QComboBox()
        self.lbl_profile_note = QLabel()
        self.lbl_profile_note.setWordWrap(True)
        self.lbl_profile_note.setStyleSheet(f"color: {theme.MUTED};")
        self.row_material = f.rowCount()
        f.addRow(tr("Material:"), self.cmb_material)
        f.addRow(tr("Ausgabeprofil:"), self.cmb_profile)
        f.addRow(tr("Render-Intent:"), self.cmb_intent)
        self.chk_drvcolor = QCheckBox(tr("Farbanpassung des Treibers aus (nur dieser Druck)"))
        self.chk_drvcolor.setToolTip(
            tr(
                "Für Tests und wenn Passermark mit einem Profil umrechnet: der Treiber verändert die Farben dann "
                "nicht noch einmal. Unter Windows wird die ICM-Farbanpassung abgeschaltet – einen eigenen Farbmodus "
                "des Herstellers (z. B. „EPSON Vivid“) stellst du in den Treibereinstellungen auf „Aus“."
            )
        )
        f.addRow("", self.chk_drvcolor)
        f.addRow("", self.lbl_profile_note)
        self.color_form = f

    def _build_extra_sections(self):
        """Collapsed sections for rarely used things: mirroring and the list of all driver options."""
        L = self.s.layout
        v = self._col
        # rarely used things clearly visible but collapsed:
        sec = CollapsibleSection(tr("Spiegeln (z. B. Transferpapier, Folienrückseite)"))
        self.chk_mirror_h = QCheckBox(tr("Horizontal spiegeln (z. B. Transferpapier, Bügelfolie, Folienrückseite)"))
        self.chk_mirror_h.setChecked(L.mirror_h)
        self.chk_mirror_v = QCheckBox(tr("Vertikal spiegeln"))
        self.chk_mirror_v.setChecked(L.mirror_v)
        for c in (self.chk_mirror_h, self.chk_mirror_v):
            c.toggled.connect(self._changed)
            sec.body_layout.addWidget(c)
        v.addWidget(sec)

        sec = CollapsibleSection(tr("Treiber (alle Optionen)"))
        self.driver_box = QWidget()
        sec.body_layout.addWidget(self.driver_box)
        v.addWidget(sec)
        v.addStretch()

    def _connect_general(self):
        """Connect the signals of the settings column (after everything is built)."""
        bg = self._handling_buttons
        # signals
        bg.buttonClicked.connect(self._handling_changed)
        for w in (
            self.rb_all,
            self.rb_cur,
            self.rb_range,
            self.chk_reverse,
            self.chk_borders,
            self.chk_autorot,
            self.chk_center,
            self.chk_margins,
        ):
            w.toggled.connect(self._changed)
        self.mode_group.buttonClicked.connect(self._changed)
        self.ed_range.editingFinished.connect(self._changed)
        self.ed_bsheets.editingFinished.connect(self._changed)
        self.ed_blank.editingFinished.connect(self._changed)
        for w in (self.chk_bfold, self.chk_breg, self.chk_bcoll):
            w.toggled.connect(self._changed)
        self.cmb_custom_by.currentIndexChanged.connect(self._changed)
        for w in (
            self.spn_custom,
            self.spn_custom_mm,
            self.spn_cols,
            self.spn_rows,
            self.spn_tile,
            self.spn_gap,
            self.spn_gutter,
            self.spn_creep,
            self.spn_persig,
            self.spn_ppct,
            self.spn_pcols,
            self.spn_prows,
            self.spn_ptw,
            self.spn_pth,
            self.spn_overlap,
        ):
            w.valueChanged.connect(self._changed)
        for w in (
            self.cmb_subset,
            self.cmb_nup,
            self.cmb_order,
            self.cmb_tile,
            self.cmb_orient,
            self.cmb_bsides,
            self.cmb_binding,
            self.cmb_bkind,
            self.cmb_blanks,
            self.cmb_pmode,
            self.cmb_ptarget,
        ):
            w.currentIndexChanged.connect(self._changed)
        for w in (self.chk_pmarks, self.chk_plabels, self.chk_plarge):
            w.toggled.connect(self._changed)
        # signals of the former tab "Weitere Optionen" (step and repeat, marks, mirroring)
        for w in (self.chk_sr, self.chk_sr2, self.chk_marks, self.chk_srseq):
            w.toggled.connect(self._changed)
        self.chk_docbleed.toggled.connect(self._docbleed_toggled)
        self.chk_fillbleed.toggled.connect(self._docbleed_toggled)
        self.cmb_bleedmode.currentIndexChanged.connect(self._changed)
        for w in (self.cmb_srmode, self.cmb_srorient, self.cmb_srrot, self.cmb_srjoin, self.cmb_srstack):
            w.currentIndexChanged.connect(self._changed)
        self.cmb_srby.currentIndexChanged.connect(self._changed)
        self.cmb_sr2fmt.currentIndexChanged.connect(self._sr2_format_changed)
        self.cmb_sr2fmt.currentIndexChanged.connect(self._changed)
        for w in (
            self.spn_srcols,
            self.spn_srrows,
            self.spn_srpct,
            self.spn_srmm,
            self.spn_srgap,
            self.spn_bleed,
            self.spn_sr2w,
            self.spn_sr2h,
            self.spn_sr2cols,
            self.spn_sr2rows,
        ):
            w.valueChanged.connect(self._changed)
        self.cmb_profile.currentIndexChanged.connect(self._profile_changed)
        self.chk_drvcolor.toggled.connect(lambda _on: self._profile_note())
        self.cmb_intent.currentIndexChanged.connect(self._profile_changed)
        self.cmb_material.currentIndexChanged.connect(self._material_changed)
        self._sync_enabled()
