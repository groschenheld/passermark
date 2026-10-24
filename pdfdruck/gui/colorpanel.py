# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Farbe → Farbprüfung: side panel next to the soft proof. Printing condition (material or profile) on top,
    facts about the document, findings with plain text and an "Ausführen" button, clickable locations.

    Signals to the viewer (it does the work):
      goto_spot(page, box)         jump to a location (like the document check)
      action_requested(kind, dict) convert | embed_oi | preflight | measure | get_profiles | choose_target | press
      proof_requested(spec)        show the soft proof for the chosen printing condition"""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QPushButton,
                               QSpinBox, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import colorcheck, colorlab, config
from ..l10n import tr
from . import theme
from .common import fill_combo

SEV_TEXT = {"error": "Fehler", "warning": "Warnung", "info": "Hinweis", "ok": "OK"}


def load_choice() -> dict:
    from .. import l10n
    st = l10n.load_settings().get("colorcheck")
    if isinstance(st, dict):
        return st
    sp = l10n.load_settings().get("softproof")                 # sonst wie der Softproof
    return {"key": sp.get("key", ""), "intent": sp.get("intent", "")} if isinstance(sp, dict) else {}


def save_choice(d: dict):
    from .. import l10n
    st = l10n.load_settings()
    if st.get("colorcheck") != d:
        st["colorcheck"] = d
        try:
            l10n.save_settings(st)
        except OSError:
            pass


class _Worker(QThread):
    done = Signal(object, object, str)

    def __init__(self, data: bytes, target, cfg):
        super().__init__()
        self.data, self.target, self.cfg = data, target, cfg
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        import traceback
        try:
            f = colorcheck.facts(self.data, self.target, cancel=lambda: self._cancel)
            self.done.emit(f, colorcheck.check(f, self.target, self.cfg), "")
        except Exception as e:                                 # noqa: BLE001
            self.done.emit(None, None, f"{e}\n\n{traceback.format_exc()}")


class ColorPanel(QWidget):
    goto_spot = Signal(int, object)
    action_requested = Signal(str, object)
    proof_requested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data_fn = None                       # liefert die aktuellen Dokument-Bytes
        self.cfg_fn = lambda: {}
        self.facts = None
        self.findings = []
        self._worker = None
        self._threads = set()
        self._gen = 0
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)

        g = QGroupBox(tr("Gedruckt wird auf"))
        f = QFormLayout(g)
        self.cmb = QComboBox()
        self.cmb.setToolTip(tr("Material (Papier mit Profil) oder Profil der Druckbedingung – eigene Papiere unter "
                               "Farbe → Papiere und Messungen, Standards unter Farbe → Standardprofile holen"))
        f.addRow(tr("Druckbedingung:"), self.cmb)
        h = QHBoxLayout()
        self.cmb_intent = QComboBox()
        self.cmb_intent.setToolTip(tr("Relativ farbmetrisch passt fast immer; Wahrnehmungsorientiert für sehr bunte Fotos"))
        h.addWidget(self.cmb_intent, 1)
        self.spn_tac = QSpinBox()
        self.spn_tac.setRange(0, 400)
        self.spn_tac.setSuffix(" %")
        self.spn_tac.setSpecialValueText(tr("Richtwert"))
        self.spn_tac.setToolTip(tr("Höchster Farbauftrag (C+M+Y+K). „Richtwert“ = üblicher Wert der Druckbedingung, "
                                   "sonst das, was die Druckerei vorgibt"))
        h.addWidget(QLabel(tr("Farbauftrag:")))
        h.addWidget(self.spn_tac)
        f.addRow(tr("Render-Intent:"), h)
        v.addWidget(g)

        row = QHBoxLayout()
        self.btn_check = QPushButton(tr("Prüfen"))
        self.btn_check.setToolTip(tr("Dokument gegen die Druckbedingung prüfen"))
        self.btn_check.clicked.connect(self.start)
        row.addWidget(self.btn_check)
        self.btn_proof = QPushButton(tr("Softproof"))
        self.btn_proof.setToolTip(tr("Seiten so anzeigen, wie sie auf dieser Druckbedingung gedruckt aussehen (Strg+Y)"))
        self.btn_proof.clicked.connect(self._proof)
        row.addWidget(self.btn_proof)
        v.addLayout(row)

        self.lbl_sum = QLabel(tr("Noch nicht geprüft."))
        self.lbl_sum.setWordWrap(True)
        v.addWidget(self.lbl_sum)
        self.box_facts = QGroupBox(tr("Im Dokument"))
        self.form_facts = QFormLayout(self.box_facts)
        v.addWidget(self.box_facts)
        self.box_facts.hide()

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([tr("Art"), tr("Befund")])
        self.tree.setWordWrap(True)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tree.setToolTip(tr("Klick: Erklärung und Empfehlung unten · Fundstelle anklicken: dorthin springen"))
        self.tree.currentItemChanged.connect(self._selected)
        self.tree.itemClicked.connect(self._clicked)
        v.addWidget(self.tree, 1)
        self.lbl_detail = QLabel()
        self.lbl_detail.setWordWrap(True)
        self.lbl_detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        v.addWidget(self.lbl_detail)
        self.btn_action = QPushButton()
        self.btn_action.clicked.connect(self._run_action)
        self.btn_action.hide()
        v.addWidget(self.btn_action)

        row = QHBoxLayout()
        self.btn_press = QPushButton(tr("Für Druckerei ausgeben …"))
        self.btn_press.setToolTip(tr("Umwandeln wie empfohlen, Output Intent einbetten, prüfen, speichern – optional "
                                     "als Paket mit Profil und Bericht"))
        self.btn_press.clicked.connect(lambda: self.action_requested.emit("press", {}))
        row.addWidget(self.btn_press)
        b = QPushButton(tr("Papiere …"))
        b.setToolTip(tr("Farbe → Papiere und Messungen: eigene Papiere anlegen und messen"))
        b.clicked.connect(lambda: self.action_requested.emit("measure", {}))
        row.addWidget(b)
        v.addLayout(row)

        self.cmb.currentIndexChanged.connect(self._choice_changed)
        self.cmb_intent.currentIndexChanged.connect(self._choice_changed)
        self.spn_tac.valueChanged.connect(self._choice_changed)
        self._loading = False

    # ---------------------------------------------------------------- #
    def reload_choices(self):
        """Druckbedingungen neu einlesen (nach Papiere/Standardprofile)."""
        self._loading = True
        try:
            saved = load_choice()
            self.choices = colorlab.proof_choices(self.cfg_fn())
            cur = self.cmb.currentData() or saved.get("key", "")
            fill_combo(self.cmb, [("", tr("– bitte wählen –"))] + [(c["key"], c["label"]) for c in self.choices], cur)
            fill_combo(self.cmb_intent, [("", tr("wie beim Material / Relativ farbmetrisch"))]
                       + list(config.INTENTS.items()), self.cmb_intent.currentData() or saved.get("intent", ""))
            if not self.spn_tac.value():
                self.spn_tac.setValue(int(saved.get("tac", 0) or 0))
        finally:
            self._loading = False

    def choice(self):
        return next((c for c in getattr(self, "choices", []) if c["key"] == self.cmb.currentData()), None)

    def target(self) -> colorcheck.Target:
        t = colorcheck.target_from_choice(self.choice(), self.cfg_fn(), self.cmb_intent.currentData() or "")
        t.tac_limit = self.spn_tac.value()
        return t

    def _choice_changed(self, *_):
        if self._loading:
            return
        save_choice({"key": self.cmb.currentData() or "", "intent": self.cmb_intent.currentData() or "",
                     "tac": self.spn_tac.value()})
        if self.facts is not None:
            self.start()

    def focus_choice(self):
        self.cmb.setFocus()
        self.cmb.showPopup()

    # ---------------------------------------------------------------- #
    def start(self):
        if self.data_fn is None:
            return
        try:
            data = self.data_fn()
        except Exception as e:                                # noqa: BLE001
            self.lbl_sum.setText(tr("Fehler: {0}").format(e))
            return
        if data is None:
            return
        if self._worker is not None:
            self._worker.cancel()
        self._gen += 1
        gen = self._gen
        t = self.target()
        self.lbl_sum.setText("… " + tr("Prüfe"))
        self.btn_check.setEnabled(False)
        w = _Worker(data, t, self.cfg_fn())
        w.done.connect(lambda f, res, err, gen=gen, t=t: self._done(gen, t, f, res, err))
        self._threads.add(w)                       # Verweis halten, bis der Thread wirklich fertig ist
        w.finished.connect(lambda w=w: self._threads.discard(w))
        self._worker = w
        w.start()

    def _done(self, gen, t, f, res, err):
        if gen != self._gen:
            return
        self._worker = None
        self.btn_check.setEnabled(True)
        if err:
            self.lbl_sum.setText(tr("Fehler: {0}").format(err.splitlines()[0]))
            self.lbl_sum.setToolTip(err)
            return
        self.facts, self.findings, self.t = f, res, t
        self._show(t)

    def _show(self, t):
        f = self.facts
        for _ in range(self.form_facts.rowCount()):
            self.form_facts.removeRow(0)
        for k, val in colorcheck.summary(f):
            lab = QLabel(val)
            lab.setWordWrap(True)
            self.form_facts.addRow(k + ":", lab)
        if t.icc:
            pw = colorlab.profile_white(t.icc)
            self.form_facts.addRow(tr("Ziel:"), QLabel(t.name + (f" – {t.material}" if t.material else "")))
            if pw:
                self.form_facts.addRow(tr("Papierweiß Profil:"), QLabel(colorlab.fmt_lab(pw)))
            if t.white:
                de = colorlab.delta_e(t.white, pw) if pw else None
                self.form_facts.addRow(tr("Papierweiß gemessen:"), QLabel(
                    colorlab.fmt_lab(t.white) + (tr(" (ΔE {0:.1f})").format(de) if de is not None else "")))
        self.box_facts.show()
        n = {k: sum(1 for x in self.findings if x.severity == k) for k in ("error", "warning", "info")}
        if not n["error"] and not n["warning"]:
            self.lbl_sum.setText("✓ " + tr("Nichts Kritisches – {0} Hinweis(e).").format(n["info"]))
        else:
            self.lbl_sum.setText(tr("{0} Fehler, {1} Warnung(en), {2} Hinweis(e) – oben anfangen.").format(
                n["error"], n["warning"], n["info"]))
        col = {"error": theme.ERROR, "warning": theme.ACCENT, "info": theme.MUTED, "ok": "#3fa34d"}
        self.tree.clear()
        for x in self.findings:
            it = QTreeWidgetItem([tr(SEV_TEXT[x.severity]), x.title])
            it.setForeground(0, QBrush(QColor(col[x.severity])))
            it.setData(0, Qt.ItemDataRole.UserRole, x)
            it.setToolTip(1, x.text or x.title)
            self.tree.addTopLevelItem(it)
            for sp in x.spots[:300]:
                ch = QTreeWidgetItem(["", tr("Seite {0}").format(sp.page) + (f" – {sp.label}" if sp.label else "")])
                ch.setData(0, Qt.ItemDataRole.UserRole, sp)
                it.addChild(ch)
        self.tree.resizeColumnToContents(0)
        if self.findings:
            self.tree.setCurrentItem(self.tree.topLevelItem(0))

    def _item_finding(self, it):
        if it is None:
            return None
        top = it.parent() or it
        return top.data(0, Qt.ItemDataRole.UserRole)

    def _selected(self, cur, _prev):
        x = self._item_finding(cur)
        if x is None:
            self.lbl_detail.setText("")
            self.btn_action.hide()
            return
        self.lbl_detail.setText(x.text)
        self.btn_action.setVisible(bool(x.action))
        self.btn_action.setText(x.action_label or tr("Ausführen"))

    def _clicked(self, it, _col):
        sp = it.data(0, Qt.ItemDataRole.UserRole)
        if it.parent() is None:
            x = sp
            if x is not None and x.spots:
                s0 = x.spots[0]
                self.goto_spot.emit(int(s0.page), s0.box)
            return
        self.goto_spot.emit(int(sp.page), sp.box)

    def _run_action(self):
        x = self._item_finding(self.tree.currentItem())
        if x is None or not x.action:
            return
        if x.action == "choose_target":
            self.focus_choice()
            return
        p = dict(x.params)
        p.setdefault("intent", self.t.intent if getattr(self, "t", None) else "relative")
        p["material"] = getattr(self, "t", colorcheck.Target()).material_id
        p["tac_limit"] = self.spn_tac.value()
        p["has_rgb"] = bool(self.facts and self.facts.has_rgb)
        self.action_requested.emit(x.action, p)

    def _proof(self):
        ch = self.choice()
        if ch is None:
            self.focus_choice()
            return
        self.proof_requested.emit(ch)
