# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Dialog "Alles reparieren" (1.20.2): the planned repairs for the findings of the check profile – each can be
switched off –, the printing condition for RGB -> CMYK and PDF/X, and what stays to be done by hand.
The repair itself is the job ``autofix`` (autofix.py) in the render process."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
)

from .. import autofix, colorlab, config
from ..l10n import tr
from . import theme


class AutofixDialog(QDialog):
    """Choose the repairs; settings() -> autofix.AutofixSettings."""

    def __init__(self, parent, rep, cfg: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle(tr("Alles reparieren"))
        self.rep = rep
        self.cfg = cfg if cfg is not None else config.load()
        lv = QVBoxLayout(self)
        prof = rep.profile.title() if rep.profile is not None else ""
        head = QLabel(tr("Prüfprofil: {0}").format(prof))
        head.setStyleSheet("font-weight: 600;")
        lv.addWidget(head)
        self.has_oi = autofix._oi_cmyk(rep)
        self.steps = autofix.plan(rep, has_target=True)  # blocked is decided with the condition below
        self.checks: dict = {}
        if not self.steps:
            lv.addWidget(QLabel(tr("Keine automatischen Reparaturen nötig.")))
        for st in self.steps:
            cb = QCheckBox(st.label + f"  ({len(st.findings)})")
            cb.setChecked(True)
            cb.setToolTip("\n".join("• " + i.message for i in st.findings[:8]))
            self.checks[st.key] = cb
            lv.addWidget(cb)
        f = QFormLayout()
        self.cmb_target = QComboBox()
        if self.has_oi:
            self.cmb_target.addItem(tr("Wie im Dokument (Output-Intent)"), "")
        for c in colorlab.proof_choices(self.cfg):
            if c.get("space") == "CMYK":
                self.cmb_target.addItem(c["label"], c["icc"])
        if not self.cmb_target.count():
            self.cmb_target.addItem(tr("Kein CMYK-Profil – unter Farbe → Standardprofile holen"), None)
        self.cmb_intent = QComboBox()
        for k, t in config.INTENTS.items():
            self.cmb_intent.addItem(tr(t), k)
        self.cmb_intent.setCurrentIndex(max(0, self.cmb_intent.findData("relative")))
        if any(k in self.checks for k in autofix.NEEDS_TARGET):
            f.addRow(tr("Druckbedingung:"), self.cmb_target)
            f.addRow(tr("Render-Intent:"), self.cmb_intent)
        self.cmb_layers = QComboBox()
        self.cmb_layers.addItem(tr("wie beim Druck"), "print")
        self.cmb_layers.addItem(tr("wie am Bildschirm"), "view")
        if "layers" in self.checks:
            f.addRow(tr("Ebenen:"), self.cmb_layers)
        lv.addLayout(f)
        self.cmb_target.currentIndexChanged.connect(self._update)
        rest = autofix.remaining(rep)
        if rest:
            lbl = QLabel(
                tr("Bleibt – von Hand zu lösen ({0}):").format(len(rest))
                + "\n"
                + "\n".join("• " + i.message.split(" – ")[0] for i in rest[:8])
                + ("\n…" if len(rest) > 8 else "")
            )
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color: {theme.MUTED};")
            lv.addWidget(lbl)
        note = QLabel(tr("Das Ergebnis öffnet sich als bearbeitetes Dokument – das Original bleibt unverändert."))
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {theme.MUTED};")
        lv.addWidget(note)
        self.bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.bb.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Reparieren"))
        self.bb.accepted.connect(self.accept)
        self.bb.rejected.connect(self.reject)
        lv.addWidget(self.bb)
        self._update()

    def _update(self, *_a):
        """Steps that need a printing condition only with one (from the list or the document)."""
        ok = self.cmb_target.currentData() is not None and (bool(self.cmb_target.currentData()) or self.has_oi)
        for k in autofix.NEEDS_TARGET:
            cb = self.checks.get(k)
            if cb is not None:
                cb.setEnabled(ok)
                if not ok:
                    cb.setChecked(False)
                    cb.setToolTip(tr("Keine Druckbedingung (CMYK-Profil) gewählt und kein Output-Intent in der Datei."))
        self.bb.button(QDialogButtonBox.StandardButton.Ok).setEnabled(any(c.isChecked() for c in self.checks.values()))

    def chosen(self) -> list:
        """Keys of the chosen steps."""
        return [k for k, cb in self.checks.items() if cb.isEnabled() and cb.isChecked()]

    def settings(self, font_map: dict | None = None) -> autofix.AutofixSettings:
        """Settings of the job for the chosen steps."""
        return autofix.AutofixSettings(
            profile=self.rep.profile.name if self.rep.profile is not None else "",
            steps=self.chosen(),
            target=self.cmb_target.currentData() or "",
            intent=self.cmb_intent.currentData() or "relative",
            layers=self.cmb_layers.currentData() or "print",
            font_map=dict(font_map or {}),
        )
