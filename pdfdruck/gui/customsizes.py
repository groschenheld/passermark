# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Sonderformate verwalten: Name, Breite, Höhe – dauerhaft gespeichert, für alle Drucker und „Als PDF speichern“."""
from __future__ import annotations

from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QMessageBox, QPushButton, QVBoxLayout)

from .. import printers
from ..l10n import tr
from . import theme


class CustomSizesDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(tr("Sonderformate – Passermark"))
        self.resize(460, 420)
        self.sizes = printers.load_custom_sizes()
        self.chosen = None                       # Papierwert, der danach eingestellt werden soll
        v = QVBoxLayout(self)
        self.lst = QListWidget()
        v.addWidget(self.lst, 1)
        f = QFormLayout()
        self.ed_name = QLineEdit()
        self.ed_name.setPlaceholderText(tr("z. B. Visitenkarte, Banner 330 × 1000"))
        f.addRow(tr("Name:"), self.ed_name)
        row = QHBoxLayout()
        self.spn_w, self.spn_h = QDoubleSpinBox(), QDoubleSpinBox()
        for sp, val in ((self.spn_w, 210.0), (self.spn_h, 297.0)):
            sp.setRange(10, 5000)
            sp.setDecimals(1)
            sp.setSuffix(" mm")
            sp.setValue(val)
            row.addWidget(sp)
        row.insertWidget(1, QLabel("×"))
        f.addRow(tr("Breite × Höhe:"), row)
        v.addLayout(f)
        row = QHBoxLayout()
        b_add = QPushButton(tr("Hinzufügen"))
        b_add.clicked.connect(self._add)
        b_del = QPushButton(tr("Löschen"))
        b_del.clicked.connect(self._delete)
        row.addWidget(b_add)
        row.addWidget(b_del)
        row.addStretch()
        v.addLayout(row)
        note = QLabel(tr("Gedruckt wird das Format als Sondergröße (CUPS: Custom.B×Hmm, Windows: benutzerdefiniertes "
                         "Papier). Ob ein Drucker das Maß annimmt, entscheidet sein Treiber – bei „Als PDF "
                         "speichern“ geht jedes Maß."))
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {theme.MUTED};")
        v.addWidget(note)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self._fill()

    def _fill(self):
        self.lst.clear()
        for e in self.sizes:
            self.lst.addItem(f"{e['name']}  ({e['w']:g} × {e['h']:g} mm)")

    def _add(self):
        w, h = round(self.spn_w.value(), 1), round(self.spn_h.value(), 1)
        name = self.ed_name.text().strip() or f"{w:g} × {h:g} mm"
        if any(abs(e["w"] - w) < 0.05 and abs(e["h"] - h) < 0.05 for e in self.sizes):
            QMessageBox.information(self, tr("Sonderformate"), tr("Dieses Maß gibt es schon."))
            return
        self.sizes.append({"name": name, "w": w, "h": h})
        self.chosen = printers.custom_value(w, h)
        self._fill()
        self.lst.setCurrentRow(len(self.sizes) - 1)
        self.ed_name.clear()

    def _delete(self):
        r = self.lst.currentRow()
        if 0 <= r < len(self.sizes):
            if printers.custom_value(self.sizes[r]["w"], self.sizes[r]["h"]) == self.chosen:
                self.chosen = None
            del self.sizes[r]
            self._fill()

    def _ok(self):
        r = self.lst.currentRow()
        if self.chosen is None and 0 <= r < len(self.sizes):
            self.chosen = printers.custom_value(self.sizes[r]["w"], self.sizes[r]["h"])
        try:
            printers.save_custom_sizes(self.sizes)
        except OSError as e:
            QMessageBox.critical(self, tr("Sonderformate"), tr("Speichern nicht möglich:\n{0}").format(e))
            return
        self.accept()
