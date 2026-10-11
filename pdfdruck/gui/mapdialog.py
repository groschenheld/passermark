# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Dialog "Map columns": which column of your CSV provides which piece of a QR code with a kind
    (business card, WLAN …). Pre-filled with the automatic mapping; your choice ends up in the field (qr_map) and thus
    in the preset. The CSV itself stays unchanged.
"""
from __future__ import annotations

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QPlainTextEdit,
                               QPushButton, QVBoxLayout)

from .. import datakinds
from ..l10n import tr
from . import theme
from .common import fill_combo


class MapDialog(QDialog):
    def __init__(self, parent, kind: str, cols: list, mapping: dict | None = None, sample: dict | None = None):
        super().__init__(parent)
        self.kind = kind
        self.cols = list(cols or [])
        self.mapping = {k: v for k, v in (mapping or {}).items() if v}
        self.sample = dict(sample or {})
        k = datakinds.get(kind)
        self.setWindowTitle(tr("Spalten zuordnen – {0}").format(k.title))
        v = QVBoxLayout(self)
        intro = QLabel(tr("Links steht, was der Code braucht, rechts die Spalte deiner Tabelle, aus der es kommt. "
                          "„automatisch“ = von Passermark erkannt (auch englische Namen und Exporte aus Outlook, "
                          "Google, Thunderbird). Die Tabelle selbst wird nicht verändert."))
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {theme.MUTED};")
        v.addWidget(intro)
        form = QFormLayout()
        self.combos = {}
        auto = datakinds.auto_map(kind, self.cols)
        for c in k.cols:
            cb = QComboBox()
            found = auto.get(c.key) or ""
            items = [("", tr("automatisch: {0}").format(found) if found else tr("automatisch: – nicht gefunden –")),
                     (datakinds.NONE, tr("– leer lassen –"))] + [(col, col) for col in self.cols]
            fill_combo(cb, items, self.mapping.get(c.key, ""))
            cb.setToolTip(c.hint)
            cb.currentIndexChanged.connect(lambda _i, key=c.key, w=cb: self.set_choice(key, w.currentData()))
            self.combos[c.key] = cb
            lab = QLabel(c.key + (" *" if c.required else ""))
            lab.setToolTip(c.hint)
            form.addRow(lab, cb)
        v.addLayout(form)
        b = QPushButton(tr("Alles automatisch"))
        b.clicked.connect(self.reset)
        v.addWidget(b)
        v.addWidget(QLabel(f"<b>{tr('So sieht der Inhalt für den ersten Datensatz aus')}</b>"))
        self.txt = QPlainTextEdit()
        self.txt.setReadOnly(True)
        self.txt.setMaximumHeight(170)
        v.addWidget(self.txt)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self._preview()

    def set_choice(self, key: str, col):
        if not isinstance(col, str) or not col:
            self.mapping.pop(key, None)
        else:
            self.mapping[key] = col
        self._preview()

    def reset(self):
        self.mapping = {}
        for cb in self.combos.values():
            cb.blockSignals(True)
            cb.setCurrentIndex(0)
            cb.blockSignals(False)
        self._preview()

    def preview_text(self) -> str:
        if not self.sample:
            return tr("(keine Daten geladen)")
        try:
            return datakinds.build(self.kind, self.sample, self.mapping)
        except ValueError as e:
            return "⚠ " + str(e)

    def _preview(self):
        self.txt.setPlainText(self.preview_text())

    def result_mapping(self) -> dict:
        return dict(self.mapping)


def summary(kind: str, cols: list, mapping: dict | None) -> str:
    """Short text for the Variable Data dialog: what comes from where, what is missing."""
    k = datakinds.get(kind)
    if not cols:
        return tr("Inhalt kommt aus den Spalten: {0}").format(
            ", ".join(c.key + ("*" if c.required else "") for c in k.cols))
    m = datakinds.resolve_map(kind, cols, mapping)
    got = [f"{c.key} ← {m[c.key]}" if m[c.key] != c.key else c.key for c in k.cols if m.get(c.key)]
    miss = [c.key + "*" for c in k.cols if c.required and not m.get(c.key)]
    txt = tr("Aus der Tabelle: {0}").format(", ".join(got) if got else "–")
    if miss:
        txt += "  ·  " + tr("⚠ fehlt: {0} – „Spalten zuordnen …“").format(", ".join(miss))
    return txt
