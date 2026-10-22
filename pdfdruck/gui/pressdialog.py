# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Farbe → Für Druckerei ausgeben … – assistant in four steps:
    1 printing condition   2 check and plan (RGB: always asked)   3 save (optionally as package)   4 result + report
    The work is done by pressexport.run (same as the job "press" on the command line)."""
from __future__ import annotations

import os
import tempfile

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QBrush, QColor, QDesktopServices
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QRadioButton, QSpinBox,
                               QStackedWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import colorcheck, colorlab, config, pressexport
from ..l10n import tr
from . import theme
from .common import fill_combo

SEV_TEXT = {"error": "Fehler", "warning": "Warnung", "info": "Hinweis", "ok": "OK"}
SEV_COL = {"error": theme.ERROR, "warning": theme.ACCENT, "info": theme.MUTED, "ok": "#3fa34d"}


class _Run(QThread):
    done = Signal(object, str)
    step = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        import traceback
        try:
            self.done.emit(self.fn(self), "")
        except Exception as e:                                 # noqa: BLE001
            self.done.emit(None, f"{e}\n\n{traceback.format_exc()}")


def _findings_tree(tree: QTreeWidget, findings):
    tree.clear()
    for x in findings:
        it = QTreeWidgetItem([tr(SEV_TEXT[x.severity]), x.title])
        it.setForeground(0, QBrush(QColor(SEV_COL[x.severity])))
        it.setToolTip(1, x.text or x.title)
        tree.addTopLevelItem(it)
    tree.resizeColumnToContents(0)


class PressDialog(QDialog):
    open_result = Signal(str)

    def __init__(self, parent, data_fn, cfg: dict, default_out: str, choice_key: str = "", intent: str = "",
                 tac: int = 0):
        super().__init__(parent)
        self.setWindowTitle(tr("Für Druckerei ausgeben – Passermark"))
        self.data_fn, self.cfg = data_fn, cfg
        self.tmp = tempfile.mkdtemp(prefix="passermark-press-")
        self.src = os.path.join(self.tmp, "eingabe.pdf")
        self.facts = None
        self.result = None
        self._run = None
        self._threads = set()
        v = QVBoxLayout(self)
        self.lbl_step = QLabel()
        self.lbl_step.setStyleSheet(f"color: {theme.ACCENT}; font-weight: 600;")
        v.addWidget(self.lbl_step)
        self.stack = QStackedWidget()
        v.addWidget(self.stack, 1)

        # 1 Druckbedingung
        w = QWidget()
        f = QFormLayout(w)
        t = QLabel(tr("Auf welcher Druckbedingung druckt die Druckerei? Steht meist im Datenblatt („Output Intent“, "
                      "„Druckbedingung“, FOGRA-Nummer). Ohne Angabe: gestrichenes Papier PSO Coated v3, "
                      "ungestrichenes PSO Uncoated v3."))
        t.setWordWrap(True)
        f.addRow(t)
        self.cmb = QComboBox()
        f.addRow(tr("Druckbedingung:"), self.cmb)
        b = QPushButton(tr("Standardprofile holen …"))
        b.setToolTip(tr("PSO Coated v3, PSO Uncoated v3, FOGRA39 … kostenlos aus der ICC Profile Registry"))
        b.clicked.connect(self._standards)
        f.addRow("", b)
        self.cmb_intent = QComboBox()
        fill_combo(self.cmb_intent, list(config.INTENTS.items()), intent or "relative")
        self.cmb_intent.setToolTip(tr("Relativ farbmetrisch passt fast immer; Wahrnehmungsorientiert für sehr bunte Fotos"))
        f.addRow(tr("Render-Intent:"), self.cmb_intent)
        self.chk_bpc = QCheckBox(tr("Tiefenkompensierung (BPC)"))
        self.chk_bpc.setChecked(True)
        self.chk_bpc.setToolTip(tr("Hält dunkle Bildstellen durchgezeichnet – an lassen, außer die Druckerei will es anders"))
        f.addRow("", self.chk_bpc)
        self.spn_tac = QSpinBox()
        self.spn_tac.setRange(0, 400)
        self.spn_tac.setSuffix(" %")
        self.spn_tac.setSpecialValueText(tr("Richtwert der Druckbedingung"))
        self.spn_tac.setValue(int(tac or 0))
        f.addRow(tr("Max. Farbauftrag:"), self.spn_tac)
        self.stack.addWidget(w)

        # 2 Prüfen und Plan
        w = QWidget()
        lv = QVBoxLayout(w)
        self.lbl_check = QLabel()
        self.lbl_check.setWordWrap(True)
        lv.addWidget(self.lbl_check)
        self.tree_before = QTreeWidget()
        self.tree_before.setHeaderLabels([tr("Art"), tr("Befund")])
        self.tree_before.setRootIsDecorated(False)
        lv.addWidget(self.tree_before, 1)
        self.box_rgb = QWidget()
        rv = QVBoxLayout(self.box_rgb)
        rv.setContentsMargins(0, 0, 0, 0)
        q = QLabel(tr("<b>Die Datei enthält RGB.</b> Wie soll es weitergehen?"))
        rv.addWidget(q)
        self.grp_rgb = QButtonGroup(self)
        self.rb_convert = QRadioButton()
        self.rb_keep = QRadioButton(tr("RGB mit Profil weitergeben – die Druckerei rechnet um (PDF/X-4 erlaubt das; "
                                       "RGB ohne Profil wird als sRGB gekennzeichnet)"))
        for rb in (self.rb_convert, self.rb_keep):
            self.grp_rgb.addButton(rb)
            rv.addWidget(rb)
        lv.addWidget(self.box_rgb)
        h = QHBoxLayout()
        h.addWidget(QLabel(tr("Methode:")))
        self.cmb_mode = QComboBox()
        fill_combo(self.cmb_mode, [("auto", tr("Automatisch (Empfehlung der Prüfung)")),
                                   ("rgb_only", tr("Nur RGB/Grau umwandeln, CMYK bleibt")),
                                   ("all", tr("Alles neu separieren")),
                                   ("none", tr("Keine Umwandlung, nur Output Intent"))], "auto")
        h.addWidget(self.cmb_mode, 1)
        lv.addLayout(h)
        self.lbl_plan = QLabel()
        self.lbl_plan.setWordWrap(True)
        self.lbl_plan.setStyleSheet(f"color: {theme.ACCENT};")
        lv.addWidget(self.lbl_plan)
        self.grp_rgb.buttonToggled.connect(lambda *_: self._update_plan())
        self.cmb_mode.currentIndexChanged.connect(lambda *_: self._update_plan())
        self.stack.addWidget(w)

        # 3 Speichern
        w = QWidget()
        f = QFormLayout(w)
        h = QHBoxLayout()
        self.ed_out = QLineEdit(default_out)
        h.addWidget(self.ed_out, 1)
        b = QPushButton(tr("…"))
        b.clicked.connect(self._pick_out)
        h.addWidget(b)
        f.addRow(tr("Speichern als:"), h)
        self.chk_pkg = QCheckBox(tr("Paket für die Druckerei (Zip: PDF, verwendete Profile, kurzer Bericht)"))
        self.chk_pkg.setToolTip(tr("Hilft bei Rückfragen: die Druckerei sieht, mit welchem Profil und Intent "
                                   "umgewandelt wurde"))
        f.addRow("", self.chk_pkg)
        t = QLabel(tr("Das Profil wird immer als Output Intent eingebettet – die Druckerei sieht die Druckbedingung."))
        t.setWordWrap(True)
        t.setStyleSheet(f"color: {theme.MUTED};")
        f.addRow(t)
        self.lbl_run = QLabel()
        self.lbl_run.setWordWrap(True)
        f.addRow(self.lbl_run)
        self.stack.addWidget(w)

        # 4 Ergebnis
        w = QWidget()
        lv = QVBoxLayout(w)
        self.lbl_done = QLabel()
        self.lbl_done.setWordWrap(True)
        self.lbl_done.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lv.addWidget(self.lbl_done)
        self.tree_after = QTreeWidget()
        self.tree_after.setHeaderLabels([tr("Art"), tr("Befund")])
        self.tree_after.setRootIsDecorated(False)
        lv.addWidget(self.tree_after, 1)
        self.txt_report = QPlainTextEdit()
        self.txt_report.setReadOnly(True)
        self.txt_report.setFont(theme.mono_font(9))
        lv.addWidget(self.txt_report, 1)
        h = QHBoxLayout()
        b = QPushButton(tr("In Passermark öffnen"))
        b.clicked.connect(lambda: self.result and self.open_result.emit(self.out_path))
        h.addWidget(b)
        b = QPushButton(tr("Ordner öffnen"))
        b.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(self.out_path))))
        h.addWidget(b)
        h.addStretch()
        lv.addLayout(h)
        self.stack.addWidget(w)

        nav = QHBoxLayout()
        nav.addStretch()
        self.btn_back = QPushButton(tr("< Zurück"))
        self.btn_back.clicked.connect(lambda: self._go(self.stack.currentIndex() - 1))
        self.btn_next = QPushButton(tr("Weiter >"))
        self.btn_next.setDefault(True)
        self.btn_next.clicked.connect(self._next)
        self.btn_close = QPushButton(tr("Schließen"))
        self.btn_close.clicked.connect(self.reject)
        for b in (self.btn_back, self.btn_next, self.btn_close):
            nav.addWidget(b)
        v.addLayout(nav)

        self._fill_choices(choice_key)
        self.resize(720, 560)
        self._go(0)

    # ---------------------------------------------------------------- #
    def _fill_choices(self, key=""):
        self.choices = [c for c in colorlab.proof_choices(self.cfg) if c["space"] == "CMYK"]
        cur = self.cmb.currentData() or key
        fill_combo(self.cmb, [(c["key"], c["label"]) for c in self.choices] or [("", tr("Kein CMYK-Profil – bitte "
                                                                                      "Standardprofile holen"))], cur)

    def _standards(self):
        from .materialsdialog import StandardProfilesDialog
        dlg = StandardProfilesDialog(self)
        dlg.exec()
        if dlg.fetched:
            self._fill_choices(self.cmb.currentData() or "")
            if not self.cmb.currentData():
                i = self.cmb.findData("f:" + dlg.fetched[0])
                if i >= 0:
                    self.cmb.setCurrentIndex(i)

    def _choice(self):
        return next((c for c in self.choices if c["key"] == self.cmb.currentData()), None)

    def _target(self) -> colorcheck.Target:
        t = colorcheck.target_from_choice(self._choice(), self.cfg, self.cmb_intent.currentData() or "relative")
        t.tac_limit = self.spn_tac.value()
        return t

    def _settings(self) -> pressexport.PressSettings:
        t = self._target()
        rgb = "convert" if self.rb_convert.isChecked() else "keep" if self.rb_keep.isChecked() else "ask"
        return pressexport.PressSettings(target=t.icc, intent=t.intent, bpc=self.chk_bpc.isChecked(),
                                         cmyk_mode=self.cmb_mode.currentData() or "auto", rgb=rgb,
                                         tac_limit=self.spn_tac.value(), material=t.material_id,
                                         package=self.chk_pkg.isChecked())

    def _go(self, i: int):
        i = max(0, min(3, i))
        self.stack.setCurrentIndex(i)
        self.lbl_step.setText([tr("1 / 4 · Druckbedingung"), tr("2 / 4 · Prüfen und Vorgehen"),
                               tr("3 / 4 · Speichern"), tr("4 / 4 · Ergebnis")][i])
        self.btn_back.setEnabled(0 < i < 3 and self._run is None)
        self.btn_next.setVisible(i < 3)
        self.btn_next.setText(tr("Ausgeben") if i == 2 else tr("Weiter >"))
        self.btn_close.setText(tr("Fertig") if i == 3 else tr("Schließen"))
        if i == 1:
            self._update_plan()

    def _next(self):
        i = self.stack.currentIndex()
        if i == 0:
            if self._choice() is None:
                QMessageBox.information(self, tr("Druckbedingung"), tr("Bitte eine CMYK-Druckbedingung wählen."))
                return
            self._check()
        elif i == 1:
            if self.facts is None:
                return
            if self.facts.has_rgb and not (self.rb_convert.isChecked() or self.rb_keep.isChecked()):
                QMessageBox.information(self, tr("RGB"), tr("Bitte entscheiden, was mit dem RGB passieren soll."))
                return
            self._go(2)
        elif i == 2:
            self._output()

    # ---------------- 2: prüfen ---------------- #
    def _check(self):
        try:
            data = self.data_fn()
            with open(self.src, "wb") as fh:
                fh.write(data)
        except Exception as e:                                  # noqa: BLE001
            QMessageBox.critical(self, tr("Fehler"), str(e))
            return
        t = self._target()
        self.facts = None
        self._go(1)
        self.lbl_check.setText("… " + tr("Prüfe"))
        self.btn_next.setEnabled(False)
        self.rb_convert.setText(tr("RGB nach „{0}“ umwandeln (empfohlen, wenn die Druckerei nichts anderes "
                                   "sagt)").format(t.name))
        for rb in (self.rb_convert, self.rb_keep):          # immer fragen: keine Vorauswahl
            self.grp_rgb.setExclusive(False)
            rb.setChecked(False)
            self.grp_rgb.setExclusive(True)

        def work(_th, data=data, t=t, cfg=self.cfg):
            f = colorcheck.facts(data, t)
            return f, colorcheck.check(f, t, cfg)

        self._start(work, lambda res, t=t: self._checked(t, *res))

    def _checked(self, t, f, findings):
        self.facts, self.t = f, t
        self.btn_next.setEnabled(True)
        bad = sum(1 for x in findings if x.severity in ("error", "warning"))
        self.lbl_check.setText(tr("Prüfung gegen „{0}“: {1} Punkt(e) zu klären.").format(t.name, bad) if bad
                               else tr("Prüfung gegen „{0}“: nichts Kritisches.").format(t.name))
        _findings_tree(self.tree_before, findings)
        self.box_rgb.setVisible(f.has_rgb)
        self._update_plan()

    def _update_plan(self):
        if self.facts is None or self.stack.currentIndex() != 1:
            self.lbl_plan.setText("")
            return
        s = self._settings()
        if self.facts.has_rgb and s.rgb == "ask":
            s.rgb = "convert"                                   # nur für die Vorschau des Plans
            pending = True
        else:
            pending = False
        try:
            p = pressexport.plan(self.facts, self.t, s, self.cfg)
        except ValueError as e:
            self.lbl_plan.setText(str(e))
            return
        what = {"rgb_only": tr("RGB/Grau wird nach „{0}“ umgewandelt, vorhandenes CMYK bleibt."),
                "all": tr("Alles wird neu separiert (→ „{0}“)."),
                "none": tr("Keine Farbumwandlung.")}[p["mode"]].format(self.t.name)
        lines = [what, tr("Output Intent „{0}“ wird eingebettet.").format(self.t.name)]
        if p["mode"] == "all":
            lines.append(tr("Quellprofil für vorhandenes CMYK: {0}").format(
                os.path.basename(p["source"]) if p["source"] else tr("Ghostscript-Standard")))
        if p["tag_rgb"]:
            lines.append(tr("RGB bleibt, RGB ohne Profil wird als sRGB gekennzeichnet."))
        lines += p["notes"] + ([p["tac_note"]] if p.get("tac_note") else [])
        if pending:
            lines.insert(0, tr("(Vorschau unter der Annahme „umwandeln“ – bitte oben entscheiden.)"))
        from .. import cmyk
        if p["mode"] in ("rgb_only", "all") and not cmyk.ghostscript():
            lines.append(tr("Achtung: Für die Umwandlung wird Ghostscript gebraucht – nicht gefunden."))
        self.lbl_plan.setText("\n".join(lines))

    # ---------------- 3: ausgeben ---------------- #
    def _pick_out(self):
        p, _ = QFileDialog.getSaveFileName(self, tr("Speichern als"), self.ed_out.text(), tr("PDF (*.pdf)"))
        if p:
            self.ed_out.setText(p if p.lower().endswith(".pdf") else p + ".pdf")

    def _output(self):
        out = self.ed_out.text().strip()
        if not out:
            self._pick_out()
            out = self.ed_out.text().strip()
            if not out:
                return
        if os.path.abspath(out) == os.path.abspath(self.src):
            return
        if os.path.exists(out) and QMessageBox.question(
                self, tr("Speichern"), tr("„{0}“ gibt es schon – ersetzen?").format(os.path.basename(out))) \
                != QMessageBox.StandardButton.Yes:
            return
        self.out_path = out
        s = self._settings()
        self.btn_next.setEnabled(False)
        self.btn_back.setEnabled(False)

        def work(th, s=s, out=out, cfg=self.cfg):
            return pressexport.run(self.src, out, s, cfg, progress=lambda d, t, x: th.step.emit(x))

        self._start(work, self._finished, step=lambda x: self.lbl_run.setText(x))

    def _finished(self, res):
        self.result = res
        self.btn_next.setEnabled(True)
        self._go(3)
        lines = [tr("Gespeichert: {0}").format(self.out_path)]
        if res.get("package"):
            lines.append(tr("Paket: {0}").format(res["package"]))
        self.lbl_done.setText("\n".join(lines))
        _findings_tree(self.tree_after, res["findings"])
        self.txt_report.setPlainText(res["report"])

    # ---------------------------------------------------------------- #
    def _start(self, fn, ok, step=None):
        th = _Run(fn)
        self._run = th
        if step is not None:
            th.step.connect(step)

        def done(res, err):
            self._run = None
            self.btn_next.setEnabled(True)
            self.btn_back.setEnabled(0 < self.stack.currentIndex() < 3)
            if err:
                self.lbl_run.setText("")
                box = QMessageBox(QMessageBox.Icon.Critical, tr("Fehler"), err.splitlines()[0], parent=self)
                box.setDetailedText(err)
                box.exec()
                if self.stack.currentIndex() == 1 and self.facts is None:
                    self._go(0)
                return
            ok(res)

        th.done.connect(done)
        self._threads.add(th)                      # Verweis halten, bis der Thread wirklich fertig ist
        th.finished.connect(lambda th=th: self._threads.discard(th))
        th.start()

    def done(self, r):
        for th in list(self._threads):
            th.wait(30000)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().done(r)
