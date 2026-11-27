# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Own print dialog (Acrobat layout): settings on the left, live preview on the right."""

from __future__ import annotations

import logging
import os
import re

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import layout, printers, printjob
from ..l10n import tr
from . import lastdir
from . import theme
from .common import Session, fit_width, follow_minimum, responsive_panel
from .printbuild import PrintBuildMixin
from .printdevice import PrintDeviceMixin
from .printpreview import PrintPreviewMixin
from .printwidgets import PageBox, Preview, SideTab, _print_pump  # noqa: F401

log = logging.getLogger(__name__)


def _mm(v: float) -> str:
    from .. import l10n as _l

    t = f"{v:.1f}"
    return t if _l.current() == "en" else t.replace(".", ",")


def bleed_texts(avail: list, want_mm: float, mode_text: str, fill: bool = True, use_doc: bool = True) -> dict:
    """Texts for the bleed section from the bleed per page (mm, None = no final format in the file):
    {"doc": which pages have bleed, "doc_mm"/"doc_max": smallest/largest existing bleed, "add": where bleed is
    added}. fill False: nothing is created, only the file's bleed is printed (if use_doc)."""
    from ..preflight import _pages_str

    have = [i + 1 for i, a in enumerate(avail) if a is not None and a > 0.05]
    none = [i + 1 for i, a in enumerate(avail) if a is None or a <= 0.05]
    doc_mm = min((avail[p - 1] for p in have), default=0.0)
    doc_max = max((avail[p - 1] for p in have), default=0.0)
    doc = ""
    if have:
        doc = tr("Die Datei hat schon Anschnitt: Seite {0} ({1} mm).").format(_pages_str(have), _mm(doc_mm))
        if none:
            doc += " " + tr("Ohne Anschnitt: Seite {0}.").format(_pages_str(none))
    add_pages = [i + 1 for i, a in enumerate(avail) if want_mm > 0.05 and (a or 0.0) < want_mm - 0.05]
    if not fill:
        add = (
            tr("Gedruckt wird der Anschnitt aus der Datei – nichts wird ergänzt.")
            if have and use_doc
            else tr("Kein Anschnitt: gedruckt wird genau das Endformat.")
        )
    elif want_mm <= 0.05:
        add = tr("Anschnitt 0 mm: gedruckt wird genau das Endformat.") if have else ""
    elif add_pages:
        add = tr("Wird beim Druck ergänzt ({0}): Seite {1}.").format(mode_text, _pages_str(add_pages))
    else:
        add = tr("Anschnitt vollständig in der Datei – nichts wird ergänzt.")
    return {"doc": doc, "doc_mm": doc_mm, "doc_max": doc_max, "add": add}


class PrintDialog(PrintPreviewMixin, PrintDeviceMixin, PrintBuildMixin, QDialog):
    """The print dialog: printer and options on the left, live preview of the imposed sheets on the right."""

    def __init__(
        self,
        parent,
        doc,
        path: str,
        current: int,
        session: Session,
        src_path: str | None = None,
        pinfo: list | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(tr("Drucken"))
        self.resize(1180, 760)
        self.doc, self.path, self.current, self.s = doc, path, current, session
        # file with exactly the content of doc + page data (view): preview in the render process
        self.src_path, self.pinfo = src_path, pinfo
        self._pv_busy = False  # one preview request on its way
        self._pv_next = {}  # waiting requests: True = preview, False = overview (only the newest of each)
        self._pv_gen = 0
        self._pv_used = False  # the render process has loaded a preview source (release when closing)
        self._spr_file = None  # printer's spreads as a file for the render process
        self.cfg = session.cfg
        self.sizes = [doc.get_page_size(i) for i in range(len(doc))]
        self.caps: printers.PrinterCaps | None = None
        self.plans: list[layout.SheetPlan] = []
        self.plans1 = None  # step 1: plans on the chosen paper (with step 2)
        self.plans2 = None  # step 2: plans on the target size (for preview/output)
        self.sheet_index = 0
        self._preview_timer = QTimer(self, singleShot=True, interval=150, timeout=self._update_preview)

        root = self._root = QHBoxLayout(self)
        left = QVBoxLayout()
        # preset at the top: applies to the whole left column (without printer/tray)
        from .presetbar import PresetBar

        self.presetbar = PresetBar(self, "impose", self._preset_settings, self._load_layout)
        self.presetbar.setToolTip(tr("Seitenhandhabung, Broschüre, Poster, Nutzen und weitere Optionen – ohne Drucker"))
        left.addWidget(self.presetbar)
        # one continuous column instead of tabs: guidance from top to bottom
        self.general = QWidget()
        self._general_area = self._scroll(self.general)
        left.addWidget(self._general_area, 1)

        right = QVBoxLayout()
        # settings | preview with a movable splitter (drag wider instead of cut off)
        from PySide6.QtWidgets import QSplitter

        lw, rw = QWidget(), QWidget()
        lw.setLayout(left)
        rw.setLayout(right)
        self.split = QSplitter(Qt.Orientation.Horizontal)
        self.split.addWidget(lw)
        self.split.addWidget(rw)
        self.split.setStretchFactor(0, 0)
        self.split.setStretchFactor(1, 1)
        self.split.setChildrenCollapsible(False)
        self.split.setSizes([560, 620])
        root.addWidget(self.split)
        self.preview = Preview()
        right.addWidget(self.preview, 1)
        nav = QHBoxLayout()
        self.btn_prev = QPushButton("◀")
        self.btn_next = QPushButton("▶")
        self.lbl_sheet = QLabel()
        self.lbl_sheet.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_prev.clicked.connect(lambda: self._step_sheet(-1))
        self.btn_next.clicked.connect(lambda: self._step_sheet(+1))
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
        self.chk_proof.setToolTip(
            tr(
                "Softproof mit gewähltem Farbprofil (exakt, LittleCMS) und Annäherung an "
                "Helligkeit/Kontrast/Sättigung/Graustufen des Treibers. Zum Vergleichen abschalten."
            )
        )
        self.chk_proof.toggled.connect(lambda _b: self._render_sheet())
        prow.addWidget(self.chk_proof)
        self.lbl_proof = QLabel()
        self.lbl_proof.setWordWrap(True)
        self.lbl_proof.setStyleSheet(f"color: {theme.ACCENT_TEXT};")
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
        # the settings column behaves like a side panel: wrap and stack, the splitter stops before cutting off
        responsive_panel(self.general, labels_above=False)  # wide column: label beside, above only when narrow
        follow_minimum(self.general, self._general_area)
        fit_width(self)
        self._load_printers()

    def _fill_sr2_formats(self):
        """List of target sizes for step 2: the sizes of the chosen device + custom measures."""
        if not hasattr(self, "cmb_sr2fmt"):
            return
        cur = self.cmb_sr2fmt.currentData() or getattr(self.s.layout, "sr2_format", "") or "custom"
        self.cmb_sr2fmt.blockSignals(True)
        self.cmb_sr2fmt.clear()
        items = []
        if self.caps:
            key = self.caps.roles.get("pagesize")
            if key and key in self.caps.options:
                items = [(c.value, c.text) for c in self.caps.options[key].choices]
        items.append(("custom", tr("Eigene Maße (mm)")))
        for v, t in items:
            self.cmb_sr2fmt.addItem(t, v)
        idx = next((i for i in range(self.cmb_sr2fmt.count()) if self.cmb_sr2fmt.itemData(i) == cur), -1)
        self.cmb_sr2fmt.setCurrentIndex(idx if idx >= 0 else self.cmb_sr2fmt.count() - 1)
        self.cmb_sr2fmt.blockSignals(False)
        self._sr2_format_changed()

    def _sr2_format_changed(self, *_):
        """Target size chosen: take the mm fields from the device (free for "Eigene Maße")."""
        if not hasattr(self, "spn_sr2w"):
            return
        v = self.cmb_sr2fmt.currentData()
        if v and v != "custom" and self.caps:
            key = self.caps.roles.get("pagesize")
            if key:
                try:
                    w, h, _ia = self.caps.sheet_for({key: v})
                    self.spn_sr2w.setValue(w / layout.MM)
                    self.spn_sr2h.setValue(h / layout.MM)
                except Exception:  # noqa: BLE001 – driver cannot compute this sheet
                    pass
        self._sync_enabled()

    def _sr2_output(self):
        """Impose step 1 + step 2 in memory and open the result as a new document."""
        if not self.caps:
            return
        try:
            pages = self._pages()
        except ValueError as e:
            QMessageBox.warning(self, tr("Seitenbereich"), str(e))
            return
        s = self._eff_settings()
        if not layout.is_step2(s):
            QMessageBox.warning(
                self,
                tr("Schritt 2"),
                tr("Bitte „Jede Seite mehrfach …“ und „Schritt 2“ aktivieren und ein Zielformat wählen."),
            )
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self._ensure_trims()
            sheet = self._sheet()
            self._make_plans(pages)  # the same path as the preview (also booklet as spreads)
            plans1 = self.plans1
            if not plans1:
                raise RuntimeError(tr("Nichts zu montieren (Seiten-/Bogenbereich leer?)"))
            plans2 = self.plans2
            out = layout.impose_step2(self._print_doc(), sheet, plans1, s, plans2=plans2)
        except Exception as e:  # noqa: BLE001 – shown to the user
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, tr("Schritt 2"), str(e))
            return
        QApplication.restoreOverrideCursor()
        opener = getattr(self.parent(), "_open_result", None)
        if opener is None:
            out.close()
            QMessageBox.critical(self, tr("Schritt 2"), tr("Kein Fenster zum Öffnen des Ergebnisses gefunden."))
            return
        notes = [w for p in plans1 for w in p.warnings] + [w for p in plans2 for w in p.warnings]
        opener(out, "_nutzen2", notes)
        self.accept()  # as when printing: close the dialog, the result is in the new tab

    def _booklet_spreads_output(self):
        """Open the booklet as a document of spreads (step 1); imposing then happens with "Nutzen"."""
        try:
            pages = self._pages()
        except ValueError as e:
            QMessageBox.warning(self, tr("Seitenbereich"), str(e))
            return
        s = self._settings()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self._ensure_trims()
            out, notes = layout.booklet_spreads(self._base_print_doc(), pages, s, self.trims)
        except Exception as e:  # noqa: BLE001 – shown to the user
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, tr("Druckbögen"), str(e))
            return
        QApplication.restoreOverrideCursor()
        opener = getattr(self.parent(), "_open_result", None)
        if opener is None:
            out.close()
            QMessageBox.critical(self, tr("Druckbögen"), tr("Kein Fenster zum Öffnen des Ergebnisses gefunden."))
            return
        opener(out, "_druckboegen", notes)
        self.accept()  # like step 2: close the dialog, the spreads are in the new tab

    def _handling(self) -> str:
        return next((k for k, b in self.handling_btns.items() if b.isChecked()), "size")

    def _toggle_sr_window(self):
        """Tab: open -> close (settings stay), otherwise open."""
        if self.sr_win.isVisible() and not self.sr_win.isMinimized():
            self.sr_win.hide()
        else:
            self._open_sr_window()

    def _open_sr_window(self):
        """Show the step-and-repeat window (also if it was minimised) and bring it to the front.
        The first time to the left of the print dialog (where the arrow points), otherwise where it was last.
        """
        if not getattr(self, "_sr_placed", False) and not self.sr_win.isVisible():
            self._sr_placed = True
            try:
                g = self.frameGeometry()
                scr = (self.screen() or QApplication.primaryScreen()).availableGeometry()
                w, h = self.sr_win.width(), min(self.sr_win.height(), scr.height())
                x = g.left() - w - 6
                if x < scr.left():
                    x = scr.left()
                y = max(scr.top(), min(g.top(), scr.bottom() - h))
                self.sr_win.move(x, y)
            except Exception:  # noqa: BLE001 – the placement is only a convenience
                pass
        self.sr_win.showNormal()
        self.sr_win.raise_()
        self.sr_win.activateWindow()

    def _handling_changed(self, *_):
        h = self._handling()
        self.stack.setCurrentIndex(self.handling_btns[h].property("page"))
        self._update_mode_hint()
        self._changed()

    def _update_mode_hint(self):
        h = self._handling()
        self.lbl_modehint.setText(
            {
                "size": tr(
                    "Jede Seite einzeln aufs Blatt – Normaldruck. Skalierung und Ausrichtung unten bei „Wie aufs Blatt?“."
                ),
                "multiple": tr("Mehrere verschiedene Seiten auf ein Blatt setzen (z. B. 2 × A5 auf A4)."),
                "booklet": tr("Seiten als Falzbögen für Broschüren montieren (Falzen und Heften)."),
                "poster": tr("Seite vergrößert über mehrere Blätter verteilen und zusammenfügen."),
            }.get(h, "")
        )

    def _sync_enabled(self):
        # The global scaling ("Wie aufs Blatt?") acts in EVERY print mode:
        # fit = mode default, actual = original size, shrink = at most 100 %,
        # custom = scale/custom measures. Hence always visible and selectable.
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
            nup = self._handling() == "multiple"  # the step-and-repeat arrangement also applies to "several per sheet"
            # … and to booklets as spreads (the spreads are imposed with the step-and-repeat logic)
            nup = nup or (self._handling() == "booklet" and self.chk_bnutzen.isChecked())
            for w in (self.cmb_srmode, self.cmb_srby, self.spn_srpct, self.spn_srmm, self.cmb_srorient, self.cmb_srrot):
                w.setEnabled(sr)
            self.cmb_srjoin.setEnabled(True)  # arrangement: adjustable in every mode (acts as soon as copies result)
            by = self.cmb_srby.currentData()
            self.spn_srpct.setVisible(by == "percent")
            self.spn_srmm.setVisible(by != "percent")
            self.lbl_srsize.setVisible(sr)
            join = self.cmb_srjoin.currentData()
            self.spn_srgap.setEnabled(join == "gap")  # gap: always adjustable once "Mit Abstand" is chosen
            self.chk_srseq.setEnabled(sr)
            self.cmb_srstack.setEnabled(sr and self.chk_srseq.isChecked())
            # With "several per sheet" the step-and-repeat arrangement overrides the old
            # gap (edge always; bleed from 1 mm bleed; gap always) – the field is then
            # greyed out so that it is clear where the effective value comes from
            overridden = nup and (join != "bleed" or self._bleed_mm() > 0)
            self.spn_gap.setEnabled(not overridden)
            self.spn_srcols.setEnabled(sr and grid)
            self.spn_srrows.setEnabled(sr and grid)
            sr2 = sr and self.chk_sr2.isChecked()
            self.chk_sr2.setEnabled(sr)
            self.cmb_sr2fmt.setEnabled(sr2)
            custom2 = self.cmb_sr2fmt.currentData() == "custom"
            self.spn_sr2w.setEnabled(sr2 and custom2)
            self.spn_sr2h.setEnabled(sr2 and custom2)
            self.spn_sr2cols.setEnabled(sr2)
            self.spn_sr2rows.setEnabled(sr2)
            self.btn_sr2.setEnabled(sr2 and self.spn_sr2w.value() > 0 and self.spn_sr2h.value() > 0)
        booklet = self._handling() == "booklet"
        self.spn_persig.setVisible(self.cmb_bkind.currentData() == "grouped")
        self.spn_persig.setEnabled(self.cmb_bkind.currentData() == "grouped")
        self.spn_creep.setEnabled(booklet and self.cmb_bkind.currentData() != "stack")
        self.chk_bcoll.setEnabled(booklet and self.cmb_bkind.currentData() != "saddle")
        self.chk_reverse.setText(
            tr("Bögen in umgekehrter Reihenfolge") if booklet else tr("Seiten in umgekehrter Reihenfolge")
        )
        if booklet and self.caps is not None:
            # Spreads: the sheet is flipped at the edge parallel to the fold (depends on sheet orientation and
            # "Seiten aneinander" – found in the first sheet after planning)
            plans = getattr(self, "plans", None) or []
            short = bool(plans and plans[0].landscape == (self.cmb_bspread.currentData() != "top"))
            edge = tr("kurzen Kante") if short else tr("langen Kante")
            if self.cmb_bsides.currentData() != "both":
                self.lbl_bhint.setText(
                    tr(
                        "Manuell beidseitig: zuerst „Nur Vorderseiten“ drucken, Stapel an der "
                        "{0} wenden und wieder einlegen, dann „Nur Rückseiten“."
                    ).format(edge)
                )
            elif short and self._short_edge_choice():
                self.lbl_bhint.setText(tr("Duplex wird für den Druck automatisch auf „kurze Kante“ gestellt."))
            elif short:
                self.lbl_bhint.setText(
                    tr(
                        "⚠ Wenden an der kurzen Kante nötig, am Drucker aber nicht erkannt – "
                        "„Nur Vorderseiten“/„Nur Rückseiten“ verwenden."
                    )
                )
            else:
                self.lbl_bhint.setText(tr("Beidseitig an der langen Kante wenden (Standard-Duplex)."))

    # ---------------- automatic tray selection ---------------- #

    # ------------------------------------------------------------------ #

    # ================================================================== #
    # state -> layout
    # ================================================================== #
    def _settings(self) -> layout.LayoutSettings:
        L = layout.LayoutSettings()
        L.mode = self.mode_group.checkedButton().property("mode") if self.mode_group.checkedButton() else "fit"
        L.custom_percent = self.spn_custom.value()
        L.custom_by = self.cmb_custom_by.currentData()
        L.custom_mm = self.spn_custom_mm.value()
        h = self._handling()
        L.handling = h
        n = self.cmb_nup.currentData()
        if n == 0:
            L.cols, L.rows, L.nup = self.spn_cols.value(), self.spn_rows.value(), 1
        else:
            L.nup = n
        L.booklet_sides = self.cmb_bsides.currentData()
        L.booklet_binding = self.cmb_binding.currentData()
        L.booklet_sheets = self.ed_bsheets.text().strip()
        L.booklet_gutter_mm = self.spn_gutter.value()
        L.booklet_kind = self.cmb_bkind.currentData() or "saddle"
        L.booklet_per_sig = self.spn_persig.value()
        L.booklet_creep_mm = self.spn_creep.value()
        L.booklet_spread = self.cmb_bspread.currentData() or "side"
        L.booklet_nutzen = self.chk_bnutzen.isChecked()
        L.booklet_blanks = self.cmb_blanks.currentData() or "end"
        L.booklet_blank_text = self.ed_blank.text()
        L.booklet_fold_marks = self.chk_bfold.isChecked()
        L.booklet_reg_marks = self.chk_breg.isChecked()
        L.booklet_collation_marks = self.chk_bcoll.isChecked()
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
        # Step & repeat acts on the chosen mode: booklet -> the spreads (sr_multi),
        # otherwise the pages (step_repeat)
        L.sr_multi = self.chk_sr.isChecked()
        L.step_repeat = self.chk_sr.isChecked() and h != "booklet"
        L.sr_mode = self.cmb_srmode.currentData()
        L.sr_cols, L.sr_rows = self.spn_srcols.value(), self.spn_srrows.value()
        L.sr_percent = self.spn_srpct.value()
        L.sr_by = self.cmb_srby.currentData()
        L.sr_mm = self.spn_srmm.value()
        L.sr_gap_mm = self.spn_srgap.value()
        L.sr_orientation = self.cmb_srorient.currentData()
        L.sr_rotate = self.cmb_srrot.currentData()
        L.sr_join = self.cmb_srjoin.currentData()
        L.sr_sequence = self.chk_srseq.isChecked()
        L.sr_stack = self.cmb_srstack.currentData() or "row"
        L.sr_pass2 = self.chk_sr2.isChecked()
        L.sr2_format = self.cmb_sr2fmt.currentData() or "custom"
        L.sr2_w_mm, L.sr2_h_mm = self.spn_sr2w.value(), self.spn_sr2h.value()
        L.sr2_cols, L.sr2_rows = self.spn_sr2cols.value(), self.spn_sr2rows.value()
        L.crop_marks = self.chk_marks.isChecked()
        # (not isVisibleTo: the section may be collapsed)
        L.doc_bleed = self.chk_docbleed.isChecked() or not getattr(self, "_doc_has_bleed", False)
        L.bleed_fill = self.chk_fillbleed.isChecked()
        L.bleed_mm = self._bleed_mm()
        L.bleed_mode = self.cmb_bleedmode.currentData() or "mirror"
        L.order = self.cmb_order.currentData()
        L.tile_mode = self.cmb_tile.currentData()
        L.tile_percent = self.spn_tile.value()
        L.gap_mm = self.spn_gap.value()
        L.borders = self.chk_borders.isChecked()
        L.orientation = self.cmb_orient.currentData()
        L.autorotate = self.chk_autorot.isChecked()
        L.center = self.chk_center.isChecked()
        L.use_margins = self.chk_margins.isChecked()
        L.borderless = bool(
            self.caps and getattr(self, "chk_borderless", None) is not None and self.caps.is_borderless(self.values)
        )
        return L

    def _load_layout(self, L: layout.LayoutSettings):
        """Set the fields from layout settings (preset)."""

        def pick(cmb, val):
            i = cmb.findData(val)
            if i >= 0:
                cmb.setCurrentIndex(i)

        for b in self.mode_group.buttons():
            if b.property("mode") == L.mode:
                b.setChecked(True)
        pick(self.cmb_custom_by, L.custom_by)
        self.spn_custom.setValue(L.custom_percent)
        self.spn_custom_mm.setValue(L.custom_mm)
        if L.cols and L.rows:
            pick(self.cmb_nup, 0)
            self.spn_cols.setValue(L.cols)
            self.spn_rows.setValue(L.rows)
        else:
            pick(self.cmb_nup, L.nup if L.nup > 1 else 2)
        pick(self.cmb_order, L.order)
        pick(self.cmb_tile, L.tile_mode)
        self.spn_tile.setValue(L.tile_percent)
        self.spn_gap.setValue(L.gap_mm)
        self.chk_borders.setChecked(L.borders)
        pick(self.cmb_bsides, L.booklet_sides)
        pick(self.cmb_binding, L.booklet_binding)
        self.ed_bsheets.setText(L.booklet_sheets)
        self.spn_gutter.setValue(L.booklet_gutter_mm)
        self.spn_persig.blockSignals(True)
        self.spn_persig.setValue(L.booklet_per_sig)
        self.spn_persig.blockSignals(False)
        pick(self.cmb_bkind, L.booklet_kind)
        self.spn_creep.setValue(L.booklet_creep_mm)
        pick(self.cmb_bspread, getattr(L, "booklet_spread", "side"))
        self.chk_bnutzen.blockSignals(True)
        self.chk_bnutzen.setChecked(True)  # old presets: booklets always go through spreads
        self.chk_bnutzen.blockSignals(False)
        pick(self.cmb_blanks, L.booklet_blanks)
        self.ed_blank.setText(L.booklet_blank_text)
        self.chk_bfold.setChecked(L.booklet_fold_marks)
        self.chk_breg.setChecked(L.booklet_reg_marks)
        self.chk_bcoll.setChecked(L.booklet_collation_marks)
        pick(self.cmb_pmode, L.poster_mode)
        self.spn_ppct.setValue(L.poster_percent)
        self.spn_pcols.setValue(L.poster_cols)
        self.spn_prows.setValue(L.poster_rows)
        pick(self.cmb_ptarget, L.poster_target)
        self.spn_ptw.setValue(L.poster_target_w_mm)
        self.spn_pth.setValue(L.poster_target_h_mm)
        self.spn_overlap.setValue(L.poster_overlap_mm)
        self.chk_pmarks.setChecked(L.poster_marks)
        self.chk_plabels.setChecked(L.poster_labels)
        self.chk_plarge.setChecked(L.poster_large_only)
        pick(self.cmb_orient, L.orientation)
        self.chk_autorot.setChecked(L.autorotate)
        self.chk_center.setChecked(L.center)
        self.chk_margins.setChecked(L.use_margins)
        if (
            getattr(self, "chk_borderless", None) is not None
            and L.borderless != self.chk_borderless.isChecked()
            and self.chk_borderless.isEnabled()
        ):
            self.chk_borderless.setChecked(L.borderless)  # preset: take over borderless on/off
        self.chk_mirror_h.setChecked(L.mirror_h)
        self.chk_mirror_v.setChecked(L.mirror_v)
        self.chk_sr.setChecked(L.step_repeat)
        pick(self.cmb_srmode, L.sr_mode)
        self.spn_srcols.setValue(L.sr_cols)
        self.spn_srrows.setValue(L.sr_rows)
        self.spn_srpct.setValue(L.sr_percent)
        pick(self.cmb_srby, L.sr_by)
        self.spn_srmm.setValue(L.sr_mm)
        self.spn_srgap.setValue(L.sr_gap_mm)
        pick(self.cmb_srorient, L.sr_orientation)
        pick(self.cmb_srrot, str(L.sr_rotate))
        pick(self.cmb_srjoin, L.sr_join)
        self.chk_srseq.setChecked(L.sr_sequence)
        pick(self.cmb_srstack, L.sr_stack)
        self.chk_sr2.setChecked(bool(L.sr_pass2))
        if self.cmb_sr2fmt.count():
            i = self.cmb_sr2fmt.findData(L.sr2_format or "custom")
            self.cmb_sr2fmt.setCurrentIndex(i if i >= 0 else self.cmb_sr2fmt.count() - 1)
        self.spn_sr2w.setValue(L.sr2_w_mm)
        self.spn_sr2h.setValue(L.sr2_h_mm)
        self.spn_sr2cols.setValue(L.sr2_cols)
        self.spn_sr2rows.setValue(L.sr2_rows)
        self.chk_marks.setChecked(L.crop_marks)
        self.spn_bleed.setValue(L.bleed_mm)
        self.chk_docbleed.setChecked(bool(getattr(L, "doc_bleed", True)))
        self.chk_fillbleed.setChecked(bool(getattr(L, "bleed_fill", True)) and L.bleed_mm > 0.05)
        i = self.cmb_bleedmode.findData(getattr(L, "bleed_mode", "mirror"))
        self.cmb_bleedmode.setCurrentIndex(max(0, i))
        self.handling_btns.get(L.handling, self.handling_btns["size"]).setChecked(True)
        on = bool(L.step_repeat or getattr(L, "sr_multi", False))
        if bool(self.chk_sr.isChecked()) != on:
            self.chk_sr.setChecked(on)
        self._handling_changed()
        self._changed()

    def _pages(self) -> list[int]:
        n = len(self.doc)
        cur = self.current if self.rb_cur.isChecked() else None
        rng = self.ed_range.text() if self.rb_range.isChecked() else ""
        rev = self.chk_reverse.isChecked() and self._handling() != "booklet"
        return layout.select_pages(n, rng, self.cmb_subset.currentData(), rev, cur)

    def _ensure_trims(self):
        """Trim size/bleed per page – from the page data of the view (without loading a page),
        otherwise via pdfium.
        """
        if getattr(self, "trims", None) is not None:
            return
        info = self.pinfo
        try:
            if info is not None and len(info) == len(self.doc):
                self.trims, self.doc_bleeds = layout.trims_from_info(info), layout.doc_bleeds_from_info(info)
            else:
                self.trims, self.doc_bleeds = layout.page_trims(self.doc), layout.page_doc_bleeds(self.doc)
        except Exception:
            log.warning("Endformate nicht ermittelt", exc_info=True)
            self.trims, self.doc_bleeds = [], []

    def _make_plans(self, pages):
        self._ensure_trims()
        s = self._settings()
        sheet = self._sheet()
        self._spr_active = layout.is_booklet_spreads(s)
        if self._spr_active:
            # Booklet as spreads: impose the opened spreads with the step-and-repeat logic –
            # preview, sheet overview and step 2 see exactly what is printed
            s = self._spreads(pages, s)
            plans = printjob.make_plans(
                self._spr_sizes, self._spr_pages, sheet, s, False, self._spr_trims, self._spr_bleeds
            )
            layout.mark_spread_duplex(plans, self._settings())
            if plans and self._spr_notes:
                plans[0].warnings.extend(n for n in self._spr_notes[1:] if n not in plans[0].warnings)
        else:
            plans = printjob.make_plans(
                self.sizes, pages, sheet, s, self.chk_reverse.isChecked(), self.trims, self.doc_bleeds
            )
        if layout.is_step2(s) and plans:
            # the preview shows step 2: the finished sheets imposed on the target size
            self.plans1 = plans
            self.plans2 = layout.plan_step2((sheet.width, sheet.height), len(plans), s)
            return self.plans2
        self.plans1 = self.plans2 = None
        return plans

    def _short_edge_choice(self):
        return printjob.short_edge_choice(self.caps)

    # ---------------- duplex preview (front/back per flip edge) ------------- #
    def _duplex_active(self) -> bool:
        """Duplex chosen on the device (front AND back on one sheet)?"""
        if self.caps is None:
            return False
        key = self.caps.roles.get("duplex")
        if not key:
            return False
        val = str(self.values.get(key, ""))
        txt = next((c.text for c in self.caps.options[key].choices if c.value == val), "")
        both = val + " " + txt
        return bool(
            re.search(r"two|duplex|doppel|beidseit", both, re.I)
            and not re.search(r"one|none|off|simplex|einseit", both, re.I)
        )

    def _duplex_short(self) -> bool:
        """Flip edge of the current duplex setting: short edge (tumble)?"""
        dc = self._short_edge_choice()
        if not dc:
            return False
        return self.values.get(dc[0]) == dc[1]

    def _duplex_layout(self):
        """Where the back side lies in the preview: None = do not show a back side.

        Landscape: short edge -> back side on the left, long edge -> below.
        Portrait: short edge -> below, long edge -> to the right.
        """
        if self.caps is None or not self.plans:
            return None
        s = self._settings()
        if s.handling == "poster":
            return None  # poster: the next plan is the next tile, no back side
        if s.handling == "booklet" and s.booklet_sides != "both":
            return None  # front/back sides only: the back side is not imposed
        if s.handling == "booklet":
            land = self.plans[self.sheet_index].landscape
            short = land == (s.booklet_spread != "top")  # spreads: flip edge parallel to the fold
        elif self._duplex_active():
            short = self._duplex_short()
        else:
            return None
        land = self.plans[self.sheet_index].landscape
        if land:
            return "left" if short else "below"
        return "below" if short else "right"

    def _preset_settings(self) -> layout.ImposeSettings:
        """Layout + current paper size – so a print preset also fits `passermark-cli impose`."""
        import dataclasses

        imp = layout.ImposeSettings(**dataclasses.asdict(self._settings()))
        try:
            sh = self._sheet() if self.caps else None
        except Exception:
            log.warning("Bogen nicht berechnet", exc_info=True)
            sh = None
        if sh is not None:
            from ..printers import STD_SIZES_MM

            w, h = sh.width / layout.MM, sh.height / layout.MM
            name = next((k for k, (a, b) in STD_SIZES_MM.items() if abs(a - w) < 1 and abs(b - h) < 1), None)
            if name:
                imp.sheet = name
            else:
                imp.sheet, imp.sheet_w_mm, imp.sheet_h_mm = "custom", round(w, 1), round(h, 1)
        return imp

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

    def _base_print_doc(self):
        """Print version of the document: form values/comments flattened (once per dialog)."""
        if getattr(self, "_flat", None) is None:
            self._flat = layout.flattened(self.doc)
        return self._flat

    def _print_doc(self):
        """Source for preview/imposition: the document – or, with "impose as spreads", the spreads."""
        if getattr(self, "_spr_active", False) and getattr(self, "_spr_doc", None) is not None:
            return self._spr_doc
        return self._base_print_doc()

    def _eff_settings(self):
        """Settings used for imposing (booklet as spreads -> step-and-repeat logic)."""
        s = self._settings()
        return layout.spread_settings(s) if layout.is_booklet_spreads(s) else s

    def _spreads(self, pages, s):
        """Spreads (cached, rebuilt only when pages or booklet values change)."""
        key = (
            tuple(pages),
            s.booklet_spread,
            s.booklet_kind,
            s.booklet_per_sig,
            s.booklet_binding,
            s.booklet_blanks,
            s.booklet_sheets,
            s.booklet_sides,
        )
        if getattr(self, "_spr_key", None) != key:
            old = getattr(self, "_spr_doc", None)
            self._spr_doc = None
            if old is not None:
                old.close()
            self._drop_spr_file()
            doc, spages, ss, notes = layout.spread_source(self._base_print_doc(), pages, s, self.trims)
            self._spr_doc, self._spr_pages, self._spr_notes = doc, spages, notes
            self._spr_sizes = [doc.get_page_size(i) for i in range(len(doc))]
            self._spr_trims, self._spr_bleeds = layout.page_trims(doc), layout.page_doc_bleeds(doc)
            self._spr_key = key
        return layout.spread_settings(s)

    def done(self, r):
        self._pv_closed = True
        self._pv_next = {}
        if self._pv_used:
            try:
                from .renderclient import RenderService

                RenderService.get().call("sheet_release", {}, lambda *_a: None)
            except Exception:  # noqa: BLE001 – no render service: preview renders in the program
                pass
        if getattr(self, "_ov_busy", False):
            self._ov_busy = False
            QApplication.restoreOverrideCursor()
        self._drop_spr_file()
        if getattr(self, "sr_win", None) is not None:
            self.sr_win.hide()
        spr = getattr(self, "_spr_doc", None)
        if spr is not None:
            spr.close()
            self._spr_doc = None
        flat = getattr(self, "_flat", None)
        if flat is not None and flat is not self.doc:
            flat.close()
        self._flat = None
        super().done(r)

    def _is_pdf_target(self):
        return bool(self.caps and self.caps.backend == "pdf")

    def _bleed_mm(self) -> float:
        """Bleed to print: the field when missing bleed is created, otherwise the file's own (or none)."""
        if self.chk_fillbleed.isChecked():
            return self.spn_bleed.value()
        if not hasattr(self, "_doc_has_bleed") and self.doc is not None:
            self._bleed_info()  # the file's bleed not determined yet
        if getattr(self, "_doc_has_bleed", False) and self.chk_docbleed.isChecked():
            return round(getattr(self, "_doc_bleed_max", 0.0), 2)
        return 0.0

    def _docbleed_toggled(self, on: bool):
        """Use the document's bleed: the bleed field cannot go below it (otherwise it would be cut away)."""
        self._bleed_info(apply_minimum=True)
        self._changed()

    def _bleed_info(self, apply_minimum: bool = False):
        """Which pages already have bleed, which get it added – and the bleed field at least the document's
        bleed while "use the document's bleed" is ticked."""
        try:
            self._ensure_trims()
        except Exception:  # noqa: BLE001 – no info then
            return
        avail = layout.available_bleeds(
            getattr(self, "trims", None) or [], getattr(self, "doc_bleeds", None) or [], len(self.doc)
        )
        how = tr("gestreckt") if self.cmb_bleedmode.currentData() == "stretch" else tr("gespiegelt")
        fill = self.chk_fillbleed.isChecked()
        info = bleed_texts(avail, self.spn_bleed.value(), how)
        has = info["doc_mm"] > 0.05
        self._doc_bleed_max, self._doc_has_bleed = info["doc_max"], has
        self.spn_bleed.setEnabled(fill)
        self.cmb_bleedmode.setEnabled(fill)
        self.lbl_docbleed.setText(info["doc"])
        self.lbl_docbleed.setVisible(has)
        self.chk_docbleed.setVisible(has)
        if has:
            self.chk_docbleed.setText(
                tr("Vorhandenen Anschnitt aus dem Dokument verwenden ({0} mm)").format(_mm(info["doc_mm"]))
            )
        want_min = round(info["doc_mm"], 1) if has and self.chk_docbleed.isChecked() else 0.0
        if apply_minimum or self.spn_bleed.minimum() != want_min:
            self.spn_bleed.blockSignals(True)
            self.spn_bleed.setMinimum(want_min)
            if self.spn_bleed.value() < want_min:
                self.spn_bleed.setValue(want_min)
            self.spn_bleed.blockSignals(False)
        use_doc = has and self.chk_docbleed.isChecked()
        self.lbl_bleedadd.setText(bleed_texts(avail, self.spn_bleed.value(), how, fill, use_doc)["add"])

    def _changed(self, *_):
        self._sync_enabled()
        if self.doc is not None and hasattr(self, "chk_docbleed"):
            self._bleed_info()
        if not self.caps:
            return
        # remember the session (RAM only)
        self.s.layout = self._settings()
        self.s.copies = self.spn_copies.value()
        self.s.collate = self.chk_collate.isChecked()
        self.s.subset = self.cmb_subset.currentData()
        self.s.reverse = self.chk_reverse.isChecked()
        bad = self.caps.conflicts(self.values)
        self.lbl_conflict.setText(
            (tr("⚠ Treiber meldet Konflikt bei: ") + ", ".join(self.caps.options[k].text for k in bad)) if bad else ""
        )
        self._preview_timer.start()

    # ------------------------------------------------------------------ #
    # preview in the render process
    # ------------------------------------------------------------------ #

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._preview_timer.start()

    # ================================================================== #
    # printing
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
            pw = ""
            if self.chk_pw.isChecked():
                pw = self.ed_pw.text()
                if not pw:
                    QMessageBox.warning(self, tr("Passwort"), tr("Bitte ein Passwort eingeben."))
                    return
                if pw != self.ed_pw2.text():
                    QMessageBox.warning(self, tr("Passwort"), tr("Die Passwörter stimmen nicht überein."))
                    return
            base = os.path.splitext(os.path.basename(self.path or "Dokument"))[0]
            start_dir = getattr(self.parent(), "_suggest_dir", "") or (
                os.path.dirname(getattr(self.parent(), "path", "") or "") or os.path.expanduser("~")
            )
            out, _ = lastdir.getSaveFileName(
                self, tr("Als PDF speichern"), os.path.join(start_dir, f"{base}_druck.pdf"), tr("PDF-Dateien (*.pdf)")
            )
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
                printjob.submit_document(
                    self.doc,
                    os.path.basename(self.path or "Dokument"),
                    self.s,
                    name,
                    pages,
                    self._settings(),
                    1,
                    True,
                    self.chk_reverse.isChecked(),
                    values=dict(self.values, __out__=out, __password__=pw),
                )
            except Exception as e:  # noqa: BLE001 – shown to the user
                QApplication.restoreOverrideCursor()
                QMessageBox.critical(self, tr("Speichern"), str(e))
                return
            QApplication.restoreOverrideCursor()
            r = QMessageBox.question(
                self, tr("Gespeichert"), tr("Gespeichert als:\n{0}\n\nJetzt in Passermark öffnen?").format(out)
            )
            if r == QMessageBox.StandardButton.Yes and hasattr(self.parent(), "ctl"):
                self.parent().ctl.open_paths([out], tab_of=self.parent())
            self.accept()
            return
        try:  # step and repeat with step 2: paper = target size (as when saving)
            values = printjob.step2_values(self.caps, self.values, self._eff_settings())
        except ValueError as e:
            QMessageBox.warning(self, tr("Schritt 2"), str(e))
            return
        skey = self.caps.roles.get("source")
        if getattr(self, "_auto_slot", None) and skey and self.values.get(skey) == self._auto_slot:
            weight = self.cmb_weight.currentData() if getattr(self, "cmb_weight", None) else 0
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            values, note, warn = printjob.resolve_tray(self.s, name, values, weight or 0, live=True)
            QApplication.restoreOverrideCursor()
            if (
                warn
                and values.get(skey) == self.values.get(skey)
                and "leer" in note
                and (
                    QMessageBox.question(self, tr("Fach leer"), note + tr("\n\nTrotzdem drucken?"))
                    != QMessageBox.StandardButton.Yes
                )
            ):
                return
        pkey = self.caps.roles.get("pagesize")
        if pkey and pkey in self.values:  # sheet for step 1 as chosen – submit_document sets the target size
            values = dict(values, **{pkey: self.values[pkey]})
        chk = getattr(self, "chk_drvcolor", None)
        if chk is not None and chk.isEnabled() and chk.isChecked():  # this job only, never remembered
            from .. import printers as _printers

            values = dict(values, **{_printers.COLOR_OFF_KEY: "1"})
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        pump = _print_pump()
        try:
            jid = printjob.submit_document(
                self.doc,
                os.path.basename(self.path or "Dokument"),
                self.s,
                name,
                pages,
                self._settings(),
                self.spn_copies.value(),
                self.chk_collate.isChecked(),
                self.chk_reverse.isChecked(),
                values=values,
                file=self.path if self.path and os.path.isfile(self.path) else None,
            )
        except Exception as e:  # noqa: BLE001 – shown to the user
            pump.close()
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, tr("Druckfehler"), str(e))
            return
        pump.close()
        QApplication.restoreOverrideCursor()
        self.parent().statusBar().showMessage(tr("Auftrag {0} an {1} gesendet.").format(jid, name), 8000)
        self.accept()
