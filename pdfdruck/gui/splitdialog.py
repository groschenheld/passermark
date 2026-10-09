# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Dialog „Seiten teilen“: halbieren oder Raster, welche Seiten, Reihenfolge – mit Vorschau der Schnittlinien."""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QSpinBox, QVBoxLayout)

from .. import core, split
from ..l10n import tr
from . import theme
from .common import fill_combo, no_enter_default


class SplitDialog(QDialog):
    def __init__(self, parent, doc, current: int = 0, selected=None, preset: split.SplitSettings | None = None,
                 which: str = "all"):
        super().__init__(parent)
        self.setWindowTitle(tr("Seiten teilen – Passermark"))
        self.doc = doc
        self.page = max(0, min(current, len(doc) - 1))
        self.selected = list(selected or [])
        self.job = None
        s = preset or split.SplitSettings()
        root = QHBoxLayout(self)
        self.lbl_prev = QLabel()
        self.lbl_prev.setMinimumSize(320, 380)
        self.lbl_prev.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.lbl_prev, 1)
        right = QVBoxLayout()
        intro = QLabel(tr("Jedes Stück wird eine eigene Seite – verlustfrei, der Inhalt wird nicht verändert. Typisch: "
                          "eine Broschüre wurde als Doppelseiten exportiert → „Senkrecht halbieren“ + „nur "
                          "Doppelseiten“. Das Ergebnis öffnet sich als neuer Reiter."))
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {theme.MUTED};")
        right.addWidget(intro)
        f = QFormLayout()
        self.cmb_mode = QComboBox()
        fill_combo(self.cmb_mode, [("halves_v", tr("Senkrecht halbieren (links | rechts)")),
                                   ("halves_h", tr("Waagrecht halbieren (oben / unten)")),
                                   ("grid", tr("Raster (Spalten × Zeilen)"))], s.mode)
        f.addRow(tr("Teilen:"), self.cmb_mode)
        row = QHBoxLayout()
        self.spn_cols, self.spn_rows = QSpinBox(), QSpinBox()
        for sp, v in ((self.spn_cols, s.cols), (self.spn_rows, s.rows)):
            sp.setRange(1, 20)
            sp.setValue(int(v))
        row.addWidget(self.spn_cols)
        row.addWidget(QLabel("×"))
        row.addWidget(self.spn_rows)
        row.addStretch()
        f.addRow(tr("Spalten × Zeilen:"), row)
        self.cmb_which = QComboBox()
        items = [("all", tr("alle Seiten")), ("current", tr("nur diese Seite ({0})").format(self.page + 1))]
        if len(self.selected) > 1:
            items.append(("selected", tr("ausgewählte Seiten ({0})").format(len(self.selected))))
        items.append(("range", tr("Seitenbereich …")))
        if which == "selected" and len(self.selected) <= 1:
            which = "current"                      # eine Seite markiert = diese Seite
        fill_combo(self.cmb_which, items, which if which in [k for k, _ in items] else "all")
        f.addRow(tr("Welche Seiten:"), self.cmb_which)
        self.ed_range = QLineEdit()
        self.ed_range.setPlaceholderText(tr("z. B. 2-5, 8"))
        f.addRow("", self.ed_range)
        self.chk_spreads = QCheckBox(tr("nur Doppelseiten (doppelt so breit wie die übrigen Seiten)"))
        self.chk_spreads.setChecked(bool(s.only_spreads))
        f.addRow("", self.chk_spreads)
        self.chk_rtl = QCheckBox(tr("Reihenfolge von rechts nach links (Bindung rechts)"))
        self.chk_rtl.setChecked(bool(s.rtl))
        f.addRow("", self.chk_rtl)
        self.chk_trim = QCheckBox(tr("im Endformat teilen, Anschnitt außen behalten (wenn das PDF ein Endformat hat)"))
        self.chk_trim.setChecked(bool(s.use_trim))
        f.addRow("", self.chk_trim)
        right.addLayout(f)
        self.lbl_info = QLabel()
        self.lbl_info.setWordWrap(True)
        self.lbl_info.setStyleSheet(f"color: {theme.ACCENT};")
        right.addWidget(self.lbl_info)
        right.addStretch()
        bb = QDialogButtonBox()
        ok = bb.addButton(tr("Teilen (neuer Reiter)"), QDialogButtonBox.ButtonRole.AcceptRole)
        ok.setDefault(True)
        bb.addButton(tr("Abbrechen"), QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(self._apply)
        bb.rejected.connect(self.reject)
        right.addWidget(bb)
        root.addLayout(right, 1)
        no_enter_default(self)
        for w in (self.cmb_mode, self.cmb_which):
            w.currentIndexChanged.connect(self._update)
        for w in (self.spn_cols, self.spn_rows):
            w.valueChanged.connect(self._update)
        for w in (self.chk_spreads, self.chk_rtl, self.chk_trim):
            w.toggled.connect(self._update)
        self.ed_range.textChanged.connect(self._update)
        self._update()

    # -------------------------------------------------------------- #
    def settings(self) -> split.SplitSettings:
        mode = self.cmb_mode.currentData()
        return split.SplitSettings(mode=mode if mode in split.MODES else "halves_v", cols=int(self.spn_cols.value()),
                                   rows=int(self.spn_rows.value()), only_spreads=bool(self.chk_spreads.isChecked()),
                                   rtl=bool(self.chk_rtl.isChecked()), use_trim=bool(self.chk_trim.isChecked()))

    def pages(self):
        """0-basierte Seiten oder None (= alle)."""
        w = self.cmb_which.currentData()
        if w == "current":
            return [self.page]
        if w == "selected":
            return list(self.selected)
        if w == "range":
            from ..layout import parse_ranges
            t = self.ed_range.text()
            return parse_ranges(t if isinstance(t, str) else "", len(self.doc))
        return None

    def _update(self, *_):
        grid = self.cmb_mode.currentData() == "grid"
        self.spn_cols.setEnabled(grid)
        self.spn_rows.setEnabled(grid)
        self.ed_range.setEnabled(self.cmb_which.currentData() == "range")
        try:
            s = self.settings()
            cols, rows = split.grid_of(s)
            pages = self.pages()
            sizes = [self.doc.get_page_size(i) for i in range(len(self.doc))]
            n = len(self.doc) if pages is None else len(pages)
            if s.only_spreads:
                sp = split.spreads(sizes, cols, rows)
                n = len(sp if pages is None else sp & set(pages))
            self.lbl_info.setText(tr("{0} Seite(n) werden geteilt → je {1} Stück.").format(n, cols * rows)
                                  if n else tr("Keine passende Seite – bei „nur Doppelseiten“ müssen manche Seiten "
                                               "doppelt so breit sein wie die übrigen."))
            self._preview(cols, rows, s.rtl)
        except Exception as e:                            # noqa: BLE001
            self.lbl_info.setText("⚠ " + str(e))

    def _preview(self, cols, rows, rtl):
        pg = self.doc[self.page]
        try:
            w, h = pg.get_size()
            scale = 360 / max(w, h)
            img = pg.render(scale=scale, fill_color=(255, 255, 255, 255)).to_pil().convert("RGB")
        finally:
            pg.close()
        data = img.tobytes("raw", "RGB")
        pix = QPixmap.fromImage(QImage(data, img.width, img.height, 3 * img.width,
                                       QImage.Format.Format_RGB888).copy())
        p = QPainter(pix)
        p.setPen(QPen(QColor(theme.ERROR), 2, Qt.PenStyle.DashLine))
        W, H = img.width, img.height
        for c in range(1, cols):
            p.drawLine(QPointF(W * c / cols, 0), QPointF(W * c / cols, H))
        for r in range(1, rows):
            p.drawLine(QPointF(0, H * r / rows), QPointF(W, H * r / rows))
        p.setPen(QColor(theme.ERROR))
        k = 1
        for r in range(rows):
            for c in (range(cols - 1, -1, -1) if rtl else range(cols)):
                p.drawText(QPointF(W * c / cols + 6, H * r / rows + 18), str(k))
                k += 1
        p.end()
        self.lbl_prev.setPixmap(pix)

    def _apply(self):
        try:
            pages = self.pages()
        except ValueError as e:
            self.lbl_info.setText("⚠ " + str(e))
            return
        self.job = ("split", core.settings_to_dict(self.settings()), pages)
        self.accept()
