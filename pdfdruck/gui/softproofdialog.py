# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Softproof der Seitenansicht einrichten: Druckbedingung (Material oder Profil), Intent, Papierweiß, Schwarz,
    Warnungen. Änderungen wirken sofort; die Einstellung wird für das nächste Mal gemerkt."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                               QLabel, QRadioButton, QSpinBox, QVBoxLayout)

from .. import colorlab, config, proof
from .. import platform as _platform
from ..l10n import tr
from . import theme
from .common import fill_combo


def load_saved() -> dict:
    from .. import l10n
    st = l10n.load_settings().get("softproof")
    return st if isinstance(st, dict) else {}


def save(d: dict):
    from .. import l10n
    st = l10n.load_settings()
    if st.get("softproof") != d:
        st["softproof"] = d
        try:
            l10n.save_settings(st)
        except OSError:
            pass


def build_spec(cfg: dict, saved: dict):
    """Gespeicherte Auswahl -> spec für proof.proofed_render (None, wenn die Druckbedingung fehlt)."""
    ch = next((c for c in colorlab.proof_choices(cfg) if c["key"] == saved.get("key")), None)
    if ch is None:
        return None
    return {"icc": ch["icc"], "space": ch["space"], "name": ch["name"],
            "intent": saved.get("intent") or ch.get("intent") or "relative", "bpc": bool(saved.get("bpc", True)),
            "paper": bool(saved.get("paper", False)), "black": bool(saved.get("black", False)),
            "white": ch["white"] if saved.get("measured", True) else None,
            "warn": saved.get("warn", "none"), "tac": int(saved.get("tac", 300))}


class SoftproofDialog(QDialog):
    changed = Signal(object)            # spec oder None

    def __init__(self, parent, cfg: dict):
        super().__init__(parent)
        self.setWindowTitle(tr("Softproof einrichten"))
        self.cfg = cfg
        self.choices = colorlab.proof_choices(cfg)
        saved = load_saved()
        v = QVBoxLayout(self)
        f = QFormLayout()
        v.addLayout(f)
        self.cmb = QComboBox()
        fill_combo(self.cmb, [(c["key"], c["label"]) for c in self.choices] or [("", tr("Keine Profile vorhanden"))],
                   saved.get("key") or (self.choices[0]["key"] if self.choices else ""))
        f.addRow(tr("Druckbedingung:"), self.cmb)
        self.cmb_intent = QComboBox()
        fill_combo(self.cmb_intent, [("", tr("wie beim Material / Relativ farbmetrisch"))] +
                   list(config.INTENTS.items()), saved.get("intent", ""))
        f.addRow(tr("Render-Intent:"), self.cmb_intent)
        self.chk_bpc = QCheckBox(tr("Tiefenkompensierung (BPC)"))
        self.chk_bpc.setToolTip(tr("Hält dunkle Bildstellen durchgezeichnet – meist an lassen"))
        self.chk_bpc.setChecked(bool(saved.get("bpc", True)))
        f.addRow("", self.chk_bpc)
        self.chk_paper = QCheckBox(tr("Papierfarbe simulieren"))
        self.chk_paper.setToolTip(tr("Zeigt Weiß als Papierweiß (gelblich, grau …) – so wirkt der Druck neben dem Papier"))
        self.chk_paper.setChecked(bool(saved.get("paper", False)))
        self.chk_black = QCheckBox(tr("Schwarze Druckfarbe simulieren"))
        self.chk_black.setToolTip(tr("Zeigt das tiefste Schwarz, das der Druck schafft – meist ein dunkles Grau"))
        self.chk_black.setChecked(bool(saved.get("black", False)))
        self.chk_measured = QCheckBox(tr("Gemessenes Papierweiß des Materials verwenden"))
        self.chk_measured.setToolTip(tr("Statt des Papierweiß aus dem Profil das gemessene des Materials (Farbe → Papiere "
                                        "und Messungen)"))
        self.chk_measured.setChecked(bool(saved.get("measured", True)))
        f.addRow(tr("Anzeigen:"), self.chk_paper)
        f.addRow("", self.chk_black)
        f.addRow("", self.chk_measured)
        h = QHBoxLayout()
        self.grp = QButtonGroup(self)
        self.rb = {}
        tips = {"none": "", "gamut": tr("Markiert Farben, die auf diesem Papier nicht druckbar sind (werden flauer)"),
                "tac": tr("Markiert Stellen mit mehr Farbe als erlaubt (C+M+Y+K)")}
        for k, t in (("none", tr("keine")), ("gamut", tr("Farbumfang")), ("tac", tr("Farbauftrag über"))):
            rb = QRadioButton(t)
            rb.setToolTip(tips[k])
            self.grp.addButton(rb)
            self.rb[k] = rb
            h.addWidget(rb)
        self.spn_tac = QSpinBox()
        self.spn_tac.setRange(100, 400)
        self.spn_tac.setSuffix(" %")
        self.spn_tac.setValue(int(saved.get("tac", 300)))
        h.addWidget(self.spn_tac)
        h.addStretch()
        self.rb.get(saved.get("warn", "none"), self.rb["none"]).setChecked(True)
        f.addRow(tr("Warnung:"), h)
        self.lbl = QLabel()
        self.lbl.setWordWrap(True)
        self.lbl.setStyleSheet(f"color: {theme.MUTED};")
        v.addWidget(self.lbl)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        if hasattr(parent, "color_check"):
            b = bb.addButton(tr("Farbprüfung mit Empfehlungen …"), QDialogButtonBox.ButtonRole.ActionRole)
            b.setToolTip(tr("Was ist am Dokument für diese Druckbedingung zu tun? (Farbe → Farbprüfung)"))
            b.clicked.connect(parent.color_check)
        bb.rejected.connect(self.reject)
        bb.accepted.connect(self.accept)
        v.addWidget(bb)
        for w in (self.cmb, self.cmb_intent):
            w.currentIndexChanged.connect(self._emit)
        for w in (self.chk_bpc, self.chk_paper, self.chk_black, self.chk_measured):
            w.toggled.connect(self._emit)
        self.grp.buttonToggled.connect(lambda *_: self._emit())
        self.spn_tac.valueChanged.connect(self._emit)
        self.resize(560, 10)
        self._update()

    def current(self) -> dict:
        warn = next(k for k, rb in self.rb.items() if rb.isChecked())
        return {"key": self.cmb.currentData() or "", "intent": self.cmb_intent.currentData() or "",
                "bpc": self.chk_bpc.isChecked(), "paper": self.chk_paper.isChecked(),
                "black": self.chk_black.isChecked(), "measured": self.chk_measured.isChecked(),
                "warn": warn, "tac": self.spn_tac.value()}

    def _choice(self):
        return next((c for c in self.choices if c["key"] == self.cmb.currentData()), None)

    def _update(self):
        ch = self._choice()
        self.chk_black.setEnabled(not self.chk_paper.isChecked())
        self.chk_measured.setEnabled(bool(ch and ch["white"]) and self.chk_paper.isChecked())
        self.spn_tac.setEnabled(self.rb["tac"].isChecked())
        self.rb["tac"].setEnabled(bool(ch and ch["space"] == "CMYK"))
        notes = []
        if ch:
            pw = colorlab.profile_white(ch["icc"])
            notes.append(tr("Papierweiß des Profils: {0}").format(colorlab.fmt_lab(pw)))
            if ch["white"]:
                de = colorlab.delta_e(ch["white"], pw) if pw else None
                notes.append(tr("gemessen: {0}").format(colorlab.fmt_lab(ch["white"]))
                             + (tr(" (ΔE {0:.1f})").format(de) if de is not None else ""))
            if ch["space"] == "CMYK":
                notes.append(tr("Echte Separation mit Ghostscript – vorhandenes CMYK bleibt, RGB/Grau wird umgerechnet.")
                             if _platform.ghostscript() else
                             tr("Ohne Ghostscript angenähert: CMYK-Inhalte werden über das Bildschirmbild umgerechnet."))
            else:
                notes.append(tr("{0}-Druckerprofil: die Seite wird so umgerechnet, wie der Druck sie umrechnet.")
                             .format(ch["space"]))
        self.lbl.setText("\n".join(notes))

    def _emit(self, *_):
        self._update()
        cur = self.current()
        save(cur)
        self.changed.emit(build_spec(self.cfg, cur))


def describe(spec) -> str:
    return proof.describe_spec(spec)
