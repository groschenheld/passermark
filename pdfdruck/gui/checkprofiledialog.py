# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Dokument → Prüfprofile bearbeiten (1.20.2): what the check reports how strictly ("Melden") and with which
limits ("Grenzwerte"). Built-in profiles are templates – changes are saved as an own profile (checkprofile.save)."""

from __future__ import annotations

import json
import os

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import checkprofile, l10n
from ..l10n import tr
from . import theme

SEV_LABEL = {"error": "Fehler", "warning": "Warnung", "info": "Hinweis", "off": "aus"}


class CheckProfileDialog(QDialog):
    """Edit check profiles; ``saved`` names the profile saved last (None: nothing saved)."""

    def __init__(self, parent=None, start: str | None = None):
        super().__init__(parent)
        from .preflightpanel import CAT_TEXT

        self.setWindowTitle(tr("Prüfprofile"))
        self.saved: str | None = None
        self.cur: checkprofile.Profile | None = None
        v = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel(tr("Profil:")))
        self.cmb = QComboBox()
        top.addWidget(self.cmb, 1)
        v.addLayout(top)
        form = QFormLayout()
        self.ed_name = QLineEdit()
        form.addRow(tr("Name:"), self.ed_name)
        self.ed_desc = QLineEdit()
        form.addRow(tr("Beschreibung:"), self.ed_desc)
        v.addLayout(form)
        self.lbl_hint = QLabel("")
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setStyleSheet(f"color: {theme.MUTED};")
        v.addWidget(self.lbl_hint)

        tabs = QTabWidget()
        # "Melden": every check with its severity, grouped by kind
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([tr("Prüfung"), tr("Melden als")])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.sev_boxes: dict = {}
        groups: dict = {}
        for key, (cat, default, label) in checkprofile.CHECKS.items():
            g = groups.get(cat)
            if g is None:
                g = groups[cat] = QTreeWidgetItem([tr(CAT_TEXT.get(cat, cat)), ""])
                f = g.font(0)
                f.setBold(True)
                g.setFont(0, f)
                self.tree.addTopLevelItem(g)
            it = QTreeWidgetItem([tr(label), ""])
            lim = checkprofile.LIMIT_OF.get(key)
            tip = tr("Vorgabe: {0}").format(tr(SEV_LABEL[default]))
            if lim:
                tip += " · " + tr("läuft nur, wenn der Grenzwert „{0}“ nicht aus ist").format(
                    tr(checkprofile.LIMITS[lim][2])
                )
            it.setToolTip(0, f"{key} – {tip}")
            g.addChild(it)
            cb = QComboBox()
            for sev in checkprofile.SEVERITIES:
                cb.addItem(tr(SEV_LABEL[sev]), sev)
            cb.setToolTip(tip)
            cb.currentIndexChanged.connect(lambda _i, k=key: self._mark(k))
            self.tree.setItemWidget(it, 1, cb)
            self.sev_boxes[key] = (it, cb)
        self.tree.expandAll()
        tabs.addTab(self.tree, tr("Melden"))
        # "Grenzwerte"
        w = QWidget()
        lf = QFormLayout(w)
        self.lim_boxes: dict = {}
        for key, (default, unit, label, lo, hi, off) in checkprofile.LIMITS.items():
            sp = QDoubleSpinBox()
            sp.setRange(lo, hi)
            sp.setDecimals(2 if unit == "mm" else 1 if unit == "pt" else 0)
            sp.setSingleStep(0.05 if unit == "mm" else 0.5 if unit == "pt" else 1)
            if unit:
                sp.setSuffix(" " + unit)
            zero = tr("automatisch") if key in checkprofile.AUTO_ZERO else tr("aus")
            if off == lo:
                sp.setSpecialValueText(zero)
            sp.setToolTip(tr("Vorgabe: {0}").format(zero if default == off else f"{default:g} {unit}".strip()))
            lf.addRow(tr(label) + ":", sp)
            self.lim_boxes[key] = sp
        tabs.addTab(w, tr("Grenzwerte"))
        v.addWidget(tabs, 1)

        row = QHBoxLayout()
        self.btn_save = QPushButton(tr("Speichern"))
        self.btn_save.clicked.connect(self._save)
        self.btn_save_as = QPushButton(tr("Speichern unter …"))
        self.btn_save_as.clicked.connect(lambda: self._save(ask=True))
        self.btn_delete = QPushButton(tr("Löschen"))
        self.btn_delete.clicked.connect(self._delete)
        btn_imp = QPushButton(tr("Importieren …"))
        btn_imp.clicked.connect(self._import)
        btn_exp = QPushButton(tr("Exportieren …"))
        btn_exp.clicked.connect(self._export)
        btn_close = QPushButton(tr("Schließen"))
        btn_close.clicked.connect(self.accept)
        for b in (self.btn_save, self.btn_save_as, self.btn_delete, btn_imp, btn_exp):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(btn_close)
        v.addLayout(row)

        self._fill(start or checkprofile.chosen())
        self.cmb.currentIndexChanged.connect(lambda _i: self._load(self._picked()))
        self.resize(640, 640)

    # ------------------------------------------------------------------ #
    def _fill(self, select: str):
        self.cmb.blockSignals(True)
        self.cmb.clear()
        for p in checkprofile.all_profiles():
            self.cmb.addItem(p.title() + ("" if p.builtin else "  ·  " + tr("eigenes")), p.name)
        i = self.cmb.findData(select)
        self.cmb.setCurrentIndex(i if i >= 0 else 0)
        self.cmb.blockSignals(False)
        self._load(self._picked())

    def _picked(self) -> checkprofile.Profile:
        try:
            return checkprofile.resolve(self.cmb.currentData() or checkprofile.DEFAULT)
        except (ValueError, OSError):
            return checkprofile.BUILTIN[checkprofile.DEFAULT]

    def _load(self, p: checkprofile.Profile):
        """Show profile ``p`` in the fields."""
        self.cur = p
        self.ed_name.setText(p.title())
        self.ed_desc.setText(checkprofile.describe(p)["description"])
        for key, (_it, cb) in self.sev_boxes.items():
            cb.blockSignals(True)
            cb.setCurrentIndex(max(0, cb.findData(p.report.get(key) or checkprofile.CHECKS[key][1])))
            cb.blockSignals(False)
            self._mark(key)
        for key, sp in self.lim_boxes.items():
            sp.setValue(p.limit(key))
        self.btn_delete.setEnabled(not p.builtin and bool(p.path))
        self.lbl_hint.setText(
            tr("Eingebautes Profil – Änderungen werden als eigenes Profil gespeichert.")
            if p.builtin
            else tr("Eigenes Profil: {0}").format(p.path)
        )

    def _mark(self, key: str):
        """Checks that differ from the default are shown in bold."""
        it, cb = self.sev_boxes[key]
        f = it.font(0)
        f.setBold(cb.currentData() != checkprofile.CHECKS[key][1])
        it.setFont(0, f)

    def profile(self) -> checkprofile.Profile:
        """The profile as set in the fields (only the deviations from the defaults)."""
        report = {
            k: cb.currentData()
            for k, (_it, cb) in self.sev_boxes.items()
            if cb.currentData() != checkprofile.CHECKS[k][1]
        }
        limits = {}
        for k, sp in self.lim_boxes.items():
            val = round(sp.value(), 3)
            if abs(val - checkprofile.LIMITS[k][0]) > 1e-9:
                limits[k] = val
        data = {"name": self.ed_name.text().strip(), "description": self.ed_desc.text().strip()}
        data.update(report=report, limits=limits)
        return checkprofile.from_dict(data, self.cur.name if self.cur else "")

    # ------------------------------------------------------------------ #
    def _save(self, ask: bool = False):
        p = self.profile()
        cur = self.cur
        if ask or cur is None or cur.builtin:
            label = tr("{0} (eigen)").format(cur.title()) if cur is not None and cur.builtin else p.label
            name, ok = QInputDialog.getText(
                self, tr("Prüfprofil speichern"), tr("Name des eigenen Profils:"), text=label
            )
            if not ok or not name.strip():
                return
            p.label = name.strip()
            p.name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in p.label).strip()
            if p.name.lower() in checkprofile.BUILTIN:
                QMessageBox.warning(
                    self,
                    tr("Prüfprofile"),
                    tr("„{0}“ ist ein eingebautes Profil – bitte unter einem anderen Namen speichern.").format(p.name),
                )
                return
            exists = any(x.name.lower() == p.name.lower() for x in checkprofile.own_profiles())
            if (
                exists
                and QMessageBox.question(
                    self, tr("Prüfprofile"), tr("„{0}“ gibt es schon. Überschreiben?").format(p.label)
                )
                != QMessageBox.StandardButton.Yes
            ):
                return
            folder = None
        else:
            folder = os.path.dirname(cur.path) if cur.path else None
        try:
            checkprofile.save(p, folder)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, tr("Prüfprofile"), tr("Fehler: {0}").format(e))
            return
        self._choose(p.name)
        self._fill(p.name)

    def _choose(self, name: str):
        """The saved profile becomes the chosen one (the check uses it right away)."""
        s = l10n.load_settings()
        s[checkprofile.SETTING] = name
        l10n.save_settings(s)
        self.saved = name

    def _delete(self):
        p = self.cur
        if p is None or p.builtin or not p.path:
            return
        if (
            QMessageBox.question(self, tr("Prüfprofile"), tr("Eigenes Profil „{0}“ löschen?").format(p.title()))
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            os.remove(p.path)
        except OSError as e:
            QMessageBox.warning(self, tr("Prüfprofile"), tr("Fehler: {0}").format(e))
            return
        if checkprofile.chosen() == p.name:
            self._choose(checkprofile.DEFAULT)
        self.saved = self.saved or checkprofile.DEFAULT
        self._fill(checkprofile.DEFAULT)

    def _import(self):
        path, _f = QFileDialog.getOpenFileName(self, tr("Prüfprofil importieren"), "", tr("Prüfprofile (*.json)"))
        if not path:
            return
        try:
            p = checkprofile.load_file(path)
            if p.name.lower() in checkprofile.BUILTIN:
                p.name += "-import"
            checkprofile.save(p)
        except (OSError, ValueError) as e:  # json errors are ValueErrors too
            QMessageBox.warning(self, tr("Prüfprofile"), tr("Fehler: {0}").format(e))
            return
        self._choose(p.name)
        self._fill(p.name)

    def _export(self):
        p = self.profile()
        path, _f = QFileDialog.getSaveFileName(
            self, tr("Prüfprofil exportieren"), (p.name or "profil") + ".json", tr("Prüfprofile (*.json)")
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(p.to_dict(), f, ensure_ascii=False, indent=2)
                f.write("\n")
        except OSError as e:
            QMessageBox.warning(self, tr("Prüfprofile"), tr("Fehler: {0}").format(e))


def edit_profiles(parent=None) -> str | None:
    """Open the editor; returns the name of a profile that was saved/chosen (None: nothing changed)."""
    dlg = CheckProfileDialog(parent)
    dlg.exec()
    return dlg.saved
