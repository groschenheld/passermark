# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Verwaltung → Materialien: Papiere registrieren (Name, Grammatur, Oberfläche, gemessenes Papierweiß),
    je Drucker das passende Profil zuordnen – mit Vorschlägen (ΔE des Papierweiß, Oberfläche, Drucker)."""
from __future__ import annotations

import os
import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton,
                               QSpinBox, QTableWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import colorlab, config
from ..l10n import tr
from . import theme
from .common import fill_combo

NONE = ""


class MaterialTab(QWidget):
    def __init__(self, admin):
        super().__init__()
        self.a = admin                       # AdminDialog: cfg, plist, new_icc, removed_icc
        self.cfg = admin.cfg
        self.cfg.setdefault("materials", [])
        self._loading = False
        h = QHBoxLayout(self)
        left = QVBoxLayout()
        self.lst = QListWidget()
        left.addWidget(self.lst, 1)
        row = QHBoxLayout()
        for text, fn in ((tr("Neu …"), self._new), (tr("Kopie"), self._copy), (tr("Entfernen"), self._delete)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        left.addLayout(row)
        h.addLayout(left, 1)

        right = QVBoxLayout()
        self.box = QGroupBox(tr("Material"))
        f = QFormLayout(self.box)
        self.ed_name = QLineEdit()
        self.ed_name.setMaxLength(64)
        f.addRow(tr("Name:"), self.ed_name)
        self.spn_weight = QSpinBox()
        self.spn_weight.setRange(0, 2000)
        self.spn_weight.setSuffix(" g/m²")
        self.spn_weight.setSpecialValueText(tr("–"))
        f.addRow(tr("Grammatur:"), self.spn_weight)
        self.cmb_surface = QComboBox()
        fill_combo(self.cmb_surface, [(s, colorlab.surface_label(s)) for s in colorlab.SURFACES], "")
        f.addRow(tr("Oberfläche:"), self.cmb_surface)
        wr = QHBoxLayout()
        self.lbl_white = QLabel()
        self.lbl_white.setFont(theme.mono_font(9.5))
        wr.addWidget(self.lbl_white, 1)
        b = QPushButton(tr("Messen / eingeben …"))
        b.setToolTip(tr("Mit dem Messgerät (ArgyllCMS), aus einer Messdatei oder per Hand"))
        b.clicked.connect(self._measure)
        wr.addWidget(b)
        b = QPushButton(tr("Löschen"))
        b.clicked.connect(self._clear_white)
        wr.addWidget(b)
        f.addRow(tr("Papierweiß:"), wr)
        self.lbl_src = QLabel()
        self.lbl_src.setWordWrap(True)
        self.lbl_src.setStyleSheet(f"color: {theme.MUTED};")
        f.addRow("", self.lbl_src)
        self.cmb_intent = QComboBox()
        fill_combo(self.cmb_intent, [("", tr("wie beim Profil"))] + list(config.INTENTS.items()), "")
        f.addRow(tr("Render-Intent:"), self.cmb_intent)
        self.ed_notes = QPlainTextEdit()
        self.ed_notes.setMaximumHeight(60)
        self.ed_notes.setPlaceholderText(tr("z. B. Hersteller, Sorte, Lieferant, Fach"))
        f.addRow(tr("Notizen:"), self.ed_notes)

        self.tbl = QTableWidget(0, 2)
        self.tbl.setHorizontalHeaderLabels([tr("Drucker"), tr("Profil")])
        self.tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setMinimumHeight(120)
        f.addRow(tr("Profil je Drucker:"), self.tbl)
        right.addWidget(self.box)

        sbox = QGroupBox(tr("Vorschläge"))
        sv = QVBoxLayout(sbox)
        r = QHBoxLayout()
        r.addWidget(QLabel(tr("für:")))
        self.cmb_for = QComboBox()
        r.addWidget(self.cmb_for, 1)
        b = QPushButton(tr("Übernehmen"))
        b.setToolTip(tr("Gewähltes Profil diesem Drucker zuordnen (Systemprofile werden dabei importiert)"))
        b.clicked.connect(self._take)
        r.addWidget(b)
        sv.addLayout(r)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([tr("Profil"), tr("ΔE"), tr("Bewertung"), tr("Begründung")])
        self.tree.setRootIsDecorated(False)
        self.tree.setMinimumHeight(130)
        self.tree.itemDoubleClicked.connect(lambda *_: self._take())
        sv.addWidget(self.tree)
        self.lbl_tip = QLabel()
        self.lbl_tip.setWordWrap(True)
        self.lbl_tip.setStyleSheet(f"color: {theme.ACCENT};")
        sv.addWidget(self.lbl_tip)
        right.addWidget(sbox, 1)
        h.addLayout(right, 2)

        self.lst.currentRowChanged.connect(self._show)
        self.ed_name.editingFinished.connect(self._store)
        self.spn_weight.valueChanged.connect(self._store)
        self.cmb_surface.currentIndexChanged.connect(self._store)
        self.cmb_intent.currentIndexChanged.connect(self._store)
        self.ed_notes.textChanged.connect(self._store)
        self.cmb_for.currentIndexChanged.connect(lambda *_: self._suggest())
        self._cands = None
        self._refresh()

    # ---------------------------------------------------------------- #
    @property
    def mats(self) -> list:
        return self.cfg["materials"]

    def cur(self):
        r = self.lst.currentRow()
        return self.mats[r] if 0 <= r < len(self.mats) else None

    def _printers(self) -> list:
        return [q.name for q in self.a.plist]

    def _refresh(self, select=None):
        self.lst.blockSignals(True)
        self.lst.clear()
        for m in self.mats:
            it = QListWidgetItem(m.get("name") or m["id"])
            it.setData(Qt.ItemDataRole.UserRole, m["id"])
            self.lst.addItem(it)
            self.lst.setCurrentItem(it)
            self._item_text(m)
        self.lst.blockSignals(False)
        row = 0
        if select:
            row = next((i for i, m in enumerate(self.mats) if m["id"] == select), 0)
        self.lst.setCurrentRow(row if self.mats else -1)
        self._show(self.lst.currentRow())

    def _profiles(self) -> list:
        return [(p["id"], p.get("name") or p["id"]) for p in self.cfg.get("color_profiles", [])]

    def _show(self, _row=None):
        m = self.cur()
        self.box.setEnabled(m is not None)
        self._loading = True
        try:
            self.tbl.setRowCount(0)
            if m is None:
                self.ed_name.clear()
                self.lbl_white.setText("")
                self.tree.clear()
                return
            self.ed_name.setText(m.get("name", ""))
            self.spn_weight.setValue(int(m.get("weight") or 0))
            fill_combo(self.cmb_surface, [(s, colorlab.surface_label(s)) for s in colorlab.SURFACES],
                       m.get("surface", ""))
            fill_combo(self.cmb_intent, [("", tr("wie beim Profil"))] + list(config.INTENTS.items()),
                       m.get("intent", ""))
            self.ed_notes.setPlainText(m.get("notes", ""))
            self._show_white(m)
            rows = [("*", tr("Alle Drucker"))] + [(q, q) for q in self._printers()]
            rows += [(q, q + tr(" (nicht installiert)")) for q in (m.get("profiles") or {})
                     if q != "*" and q not in self._printers()]
            profs = [(NONE, "–")] + self._profiles()
            self.tbl.setRowCount(len(rows))
            for i, (q, label) in enumerate(rows):
                lab = QLabel(label)
                lab.setContentsMargins(6, 0, 6, 0)
                self.tbl.setCellWidget(i, 0, lab)
                cb = QComboBox()
                fill_combo(cb, profs, (m.get("profiles") or {}).get(q, NONE))
                cb.setProperty("printer", q)
                cb.currentIndexChanged.connect(self._store_profiles)
                self.tbl.setCellWidget(i, 1, cb)
            cur_for = self.cmb_for.currentData()
            self.cmb_for.blockSignals(True)
            fill_combo(self.cmb_for, rows, cur_for if cur_for in [r[0] for r in rows] else "*")
            self.cmb_for.blockSignals(False)
        finally:
            self._loading = False
        self._suggest()

    def _show_white(self, m):
        w = m.get("white")
        self.lbl_white.setText(colorlab.fmt_lab(w) if w else tr("nicht gemessen"))
        self.lbl_src.setText(m.get("white_source", "") if w else tr(
            "Ohne gemessenes Papierweiß gibt es nur Vorschläge nach Oberfläche und Drucker."))

    def _store(self, *_):
        if self._loading:
            return
        m = self.cur()
        if m is None:
            return
        m["name"] = self.ed_name.text().strip()[:64] or m["id"]
        m["weight"] = int(self.spn_weight.value())
        m["surface"] = self.cmb_surface.currentData() or ""
        m["intent"] = self.cmb_intent.currentData() or ""
        m["notes"] = self.ed_notes.toPlainText()[:2000]
        self._item_text(m)
        if self.sender() is self.cmb_surface:
            self._suggest()

    def _item_text(self, m):
        it = self.lst.currentItem()
        if it is None:
            return
        extra = []
        if m.get("weight"):
            extra.append(f"{m['weight']} g/m²")
        if m.get("white"):
            extra.append("L {0:.0f}".format(m["white"][0]))
        it.setText((m.get("name") or m["id"]) + (f"  ({', '.join(extra)})" if extra else ""))

    def _store_profiles(self, *_):
        if self._loading:
            return
        m = self.cur()
        if m is None:
            return
        prof = {}
        for i in range(self.tbl.rowCount()):
            cb = self.tbl.cellWidget(i, 1)
            if cb is not None and cb.currentData():
                prof[cb.property("printer")] = cb.currentData()
        m["profiles"] = prof

    # ---------------------------------------------------------------- #
    def _new_id(self, name: str) -> str:
        base = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")[:48] or "material"
        ids = {m["id"] for m in self.mats}
        mid, i = base, 2
        while mid in ids:
            mid, i = f"{base}_{i}", i + 1
        return mid

    def _new(self):
        name, ok = QInputDialog.getText(self, tr("Neues Material"), tr("Name (z. B. „Munken Pure 120 g“):"))
        if not ok or not name.strip():
            return
        m = colorlab.new_material(self._new_id(name.strip()), name.strip()[:64])
        m["surface"] = colorlab.guess_surface(name)
        w = re.search(r"(\d{2,4})\s*g", name)
        if w:
            m["weight"] = min(2000, int(w.group(1)))
        self.mats.append(m)
        self._refresh(m["id"])

    def _copy(self):
        m = self.cur()
        if m is None:
            return
        import copy
        n = copy.deepcopy(m)
        n["name"] = (m.get("name") or m["id"])[:56] + tr(" (Kopie)")
        n["id"] = self._new_id(n["name"])
        self.mats.append(n)
        self._refresh(n["id"])

    def _delete(self):
        m = self.cur()
        if m is None:
            return
        if QMessageBox.question(self, tr("Material entfernen"), tr("„{0}“ entfernen?").format(m.get("name") or m["id"])) \
                != QMessageBox.StandardButton.Yes:
            return
        self.mats.remove(m)
        self._refresh()

    def _measure(self):
        from .measuredialog import MeasureDialog
        m = self.cur()
        if m is None:
            return
        dlg = MeasureDialog(self, m.get("name", ""), m.get("white"))
        if not dlg.exec():
            return
        lab = dlg.result_lab()
        if lab is None:
            return
        m["white"] = [round(float(x), 2) for x in lab]
        m["white_source"] = dlg.result_source()
        self._show_white(m)
        self._refresh(m["id"])

    def _clear_white(self):
        m = self.cur()
        if m is None:
            return
        m["white"], m["white_source"] = None, ""
        self._refresh(m["id"])

    # ---------------- Vorschläge ---------------- #
    def candidates(self) -> list:
        if self._cands is None:
            view = dict(self.cfg)                     # neu importierte Profile liegen noch bei der Quelle
            view["color_profiles"] = [dict(p, file=self.a.new_icc.get(p["id"], p.get("file", "")))
                                      for p in self.cfg.get("color_profiles", [])]
            self._cands = colorlab.candidates(view)
        return self._cands

    def invalidate(self):
        """Profile in der Verwaltung geändert (Import/Entfernen)."""
        self._cands = None
        if self.isVisible():
            self._show()

    def _suggest(self):
        self.tree.clear()
        m = self.cur()
        if m is None:
            self.lbl_tip.setText("")
            return
        q = self.cmb_for.currentData() or "*"
        res = colorlab.suggest(m, self.candidates(), "" if q == "*" else q, limit=8)
        for r in res:
            it = QTreeWidgetItem([("" if r["admin"] else tr("System: ")) + r["name"],
                                  "–" if r["de"] is None else f"{r['de']:.1f}", r["verdict"], r["why"]])
            it.setData(0, Qt.ItemDataRole.UserRole, r)
            it.setToolTip(0, r["file"])
            it.setToolTip(3, r["why"])
            self.tree.addTopLevelItem(it)
        for c in range(3):
            self.tree.resizeColumnToContents(c)
        if res:
            self.tree.setCurrentItem(self.tree.topLevelItem(0))
        self.lbl_tip.setText(colorlab.standard_tip(m, res[0] if res else None))

    def _take(self):
        m = self.cur()
        it = self.tree.currentItem()
        if m is None or it is None:
            return
        r = it.data(0, Qt.ItemDataRole.UserRole)
        pid = r["id"]
        if not pid:                                   # Systemprofil: in die Verwaltung übernehmen
            pid = self.a.import_profile_file(r["file"], r["name"])
            if not pid:
                return
            self._cands = None
        q = self.cmb_for.currentData() or "*"
        m.setdefault("profiles", {})[q] = pid
        if not m.get("intent") and r["space"] == "CMYK":
            m["intent"] = "relative"
        self._show()
