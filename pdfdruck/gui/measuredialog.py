# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Papierweiß eines Materials bestimmen: mit dem Messgerät (ArgyllCMS spotread – X-Rite i1Pro, ColorMunki,
    i1Studio …), aus einer Messdatei (CGATS aus i1Profiler/ArgyllCMS, spotread-Protokoll) oder per Hand.
    Mehrere Messungen werden gemittelt (Papier an verschiedenen Stellen messen)."""
from __future__ import annotations

from PySide6.QtCore import QProcess, Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton,
                               QSpinBox, QVBoxLayout)

from .. import colorlab
from .. import platform as _platform
from ..l10n import tr
from . import theme


def install_help() -> str:
    """Hinweis, wenn ArgyllCMS fehlt (Rich Text mit Link)."""
    link = '<a style="color:{0}" href="https://www.argyllcms.com/">argyllcms.com</a>'.format(theme.ACCENT)
    if _platform.IS_WIN:
        how = tr("Windows: ArgyllCMS von {0} laden, entpacken (z. B. nach C:\\Argyll) und den Gerätetreiber laut "
                 "Anleitung installieren. Passermark findet spotread dort von selbst.").format(link)
    else:
        how = tr("Linux: Paket installieren – Debian/Ubuntu <tt>sudo apt install argyll</tt>, Fedora "
                 "<tt>sudo dnf install argyllcms</tt>, Arch <tt>sudo pacman -S argyllcms</tt>. Danach das Messgerät "
                 "neu anstecken. Mehr auf {0}.").format(link)
    return (tr("<b>ArgyllCMS (spotread) nicht gefunden.</b> Damit spricht Passermark das Messgerät an (X-Rite i1Pro, "
               "i1Studio, ColorMunki …).") + "<br>" + how + "<br>" +
            tr("Bis dahin: Messdatei laden oder Werte eingeben."))


class MeasureDialog(QDialog):
    def __init__(self, parent, material_name: str = "", start=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Papierweiß bestimmen – {0}").format(material_name) if material_name
                            else tr("Papierweiß bestimmen"))
        self.values: list = []           # [(Lab, Herkunft)]
        self.source = ""
        self.proc = None
        self.buf = ""
        v = QVBoxLayout(self)

        intro = QLabel(tr("Papierweiß = die Farbe des unbedruckten Papiers (Lab-Wert). Daran erkennt Passermark, welches "
                          "Profil zum Papier passt, und der Softproof zeigt das echte Papier. Mehrere Messungen an "
                          "verschiedenen Stellen werden gemittelt."))
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {theme.MUTED};")
        v.addWidget(intro)

        # Messgerät
        box = QGroupBox(tr("Messgerät (ArgyllCMS spotread)"))
        bv = QVBoxLayout(box)
        self.exe = colorlab.spotread()
        self.lbl_dev = QLabel(tr("Gefunden: {0}").format(self.exe) if self.exe else install_help())
        self.lbl_dev.setWordWrap(True)
        self.lbl_dev.setOpenExternalLinks(True)
        self.lbl_dev.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        bv.addWidget(self.lbl_dev)
        h = QHBoxLayout()
        self.btn_find = QPushButton(tr("Gerät suchen"))
        self.btn_find.setToolTip(tr("Fragt ArgyllCMS, welche Messgeräte angeschlossen sind, und wählt das erste"))
        self.btn_find.clicked.connect(self._find)
        h.addWidget(self.btn_find)
        h.addWidget(QLabel(tr("Anschluss:")))
        self.spn_port = QSpinBox()
        self.spn_port.setRange(1, 9)
        self.spn_port.setToolTip(tr("Nummer des Geräts in der Liste von spotread (meist 1)"))
        h.addWidget(self.spn_port)
        self.chk_nocal = QCheckBox(tr("Kalibrierung überspringen"))
        self.chk_nocal.setToolTip(tr("Nur wenn das Gerät gerade erst kalibriert wurde"))
        h.addWidget(self.chk_nocal)
        h.addStretch()
        self.btn_measure = QPushButton(tr("Messen"))
        self.btn_measure.setToolTip(tr("Startet spotread: zuerst kalibrieren (Gerät auf die Kalibrierstellung), dann "
                                       "aufs Papier setzen – das Programm sagt jeweils, was zu tun ist"))
        self.btn_measure.clicked.connect(self._start)
        self.btn_next = QPushButton(tr("Weiter"))
        self.btn_next.setToolTip(tr("Gerät liegt richtig – Kalibrierung bzw. Messung auslösen (wie die Taste am Gerät)"))
        self.btn_next.setEnabled(False)
        self.btn_next.clicked.connect(self._key)
        self.btn_stop = QPushButton(tr("Abbrechen"))
        self.btn_stop.setToolTip(tr("spotread beenden"))
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop)
        for b in (self.btn_measure, self.btn_next, self.btn_stop):
            h.addWidget(b)
        bv.addLayout(h)
        self.lbl_state = QLabel(tr("Gerät anschließen, dann „Messen“. Das Papier auf eine weiße Unterlage oder "
                                   "mehrere Blätter desselben Papiers legen."))
        self.lbl_state.setWordWrap(True)
        self.lbl_state.setStyleSheet(f"color: {theme.ACCENT};")
        bv.addWidget(self.lbl_state)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(110)
        self.log.setFont(theme.mono_font(9))
        bv.addWidget(self.log)
        for w in (self.spn_port, self.chk_nocal, self.btn_measure, self.btn_find):
            w.setEnabled(bool(self.exe))
        v.addWidget(box)

        # Datei / Hand
        box = QGroupBox(tr("Ohne Gerät"))
        bh = QHBoxLayout(box)
        b = QPushButton(tr("Messdatei laden …"))
        b.setToolTip(tr("CGATS (i1Profiler, ArgyllCMS .ti3, ColorPort …) oder spotread-Protokoll – das Feld ohne "
                        "Farbe wird als Papierweiß genommen"))
        b.clicked.connect(self._load_file)
        bh.addWidget(b)
        self.ed_lab = QLineEdit()
        self.ed_lab.setPlaceholderText(tr("L a b, z. B. 93,5 0,8 4,2"))
        self.ed_lab.returnPressed.connect(self._add_manual)
        bh.addWidget(self.ed_lab, 1)
        b = QPushButton(tr("Hinzufügen"))
        b.clicked.connect(self._add_manual)
        bh.addWidget(b)
        v.addWidget(box)

        # Messwerte
        self.lst = QListWidget()
        self.lst.setMaximumHeight(130)
        v.addWidget(self.lst)
        h = QHBoxLayout()
        self.lbl_mean = QLabel()
        h.addWidget(self.lbl_mean, 1)
        b = QPushButton(tr("Entfernen"))
        b.clicked.connect(self._remove)
        h.addWidget(b)
        v.addLayout(h)
        self.bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.bb.accepted.connect(self.accept)
        self.bb.rejected.connect(self.reject)
        v.addWidget(self.bb)
        if start:
            self._add(tuple(start), tr("bisheriger Wert"))
        self._refresh()
        self.resize(640, 10)

    # ---------------------------------------------------------------- #
    def result_lab(self):
        return colorlab.mean_lab([lab for lab, _ in self.values])

    def result_source(self) -> str:
        srcs = sorted({s for _, s in self.values})
        return "; ".join(srcs)[:200]

    def _add(self, lab, src):
        lab = tuple(round(float(x), 2) for x in lab)
        self.values.append((lab, src))
        it = QListWidgetItem(f"{colorlab.fmt_lab(lab)}   ·  {src}")
        self.lst.addItem(it)
        self._refresh()

    def _remove(self):
        r = self.lst.currentRow()
        if 0 <= r < len(self.values):
            self.values.pop(r)
            self.lst.takeItem(r)
            self._refresh()

    def _refresh(self):
        m = self.result_lab()
        if m is None:
            self.lbl_mean.setText(tr("Noch kein Messwert."))
        else:
            spread = max((colorlab.delta_e(lab, m) for lab, _ in self.values), default=0.0)
            txt = tr("Papierweiß: {0}  ({1} Wert(e))").format(colorlab.fmt_lab(m), len(self.values))
            if len(self.values) > 1:
                txt += tr(" – Streuung ΔE {0:.1f}").format(spread)
                if spread > 1.5:
                    txt += tr(" (uneinheitlich – nochmal messen?)")
            self.lbl_mean.setText(txt)
        self.bb.button(QDialogButtonBox.StandardButton.Ok).setEnabled(m is not None)

    def _add_manual(self):
        lab = colorlab.parse_lab_text(self.ed_lab.text())
        if lab is None:
            QMessageBox.warning(self, tr("Papierweiß"), tr("Bitte drei Werte L a b eingeben (L 0–100, a/b ±128)."))
            return
        self._add(lab, tr("eingegeben"))
        self.ed_lab.clear()

    def _load_file(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Messdatei"), "", tr(
            "Messdaten (*.txt *.ti3 *.cgats *.it8 *.csv *.log);;Alle Dateien (*)"))
        if not path:
            return
        try:
            lab, why, n = colorlab.read_measurement_file(path)
        except OSError as e:
            QMessageBox.warning(self, tr("Messdatei"), str(e))
            return
        if lab is None:
            QMessageBox.warning(self, tr("Messdatei"), tr("Keine Lab- oder XYZ-Messwerte in der Datei gefunden."))
            return
        import os
        self._add(lab, f"{os.path.basename(path)}: {why}")

    # ---------------- spotread ---------------- #
    def _find(self):
        """spotread -? listet die Anschlüsse – angeschlossene Messgeräte stehen mit Namen darin."""
        if self.proc is not None or not self.exe:
            return
        p = QProcess(self)
        p.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        p.start(self.exe, ["-?"])
        p.waitForFinished(8000)
        text = bytes(p.readAllStandardOutput()).decode("utf-8", "replace")
        if p.state() != QProcess.ProcessState.NotRunning:
            p.kill()
            p.waitForFinished(1000)
        ports = colorlab.spotread_ports(text)
        inst = [(n, d) for n, d in ports if colorlab.is_instrument(d)]
        if inst:
            self.spn_port.setValue(inst[0][0])
            self.lbl_state.setText(tr("Messgerät gefunden: {0} (Anschluss {1}). Jetzt „Messen“.").format(
                inst[0][1], inst[0][0]))
        else:
            self.lbl_state.setText(tr("Kein Messgerät erkannt. Angesteckt? Unter Windows braucht ArgyllCMS einen eigenen "
                                      "Treiber (siehe argyllcms.com → Installation), unter Linux die udev-Regel aus dem "
                                      "Paket argyll."))
        self.log.appendPlainText("$ spotread -?\n" + "\n".join(f"{n} = {d}" for n, d in ports))

    def _start(self):
        if self.proc is not None:
            return
        self.buf = ""
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.finished.connect(self._finished)
        self.proc.errorOccurred.connect(lambda _e: self._finished())
        args = colorlab.spotread_args(self.spn_port.value(), self.chk_nocal.isChecked())
        self.log.appendPlainText("$ spotread " + " ".join(args))
        self.lbl_state.setText(tr("Gerät wird gesucht …"))
        self.btn_measure.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.proc.start(self.exe, args)

    def _read(self):
        if self.proc is None:
            return
        chunk = bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        self.buf += chunk
        self.log.moveCursor(self.log.textCursor().MoveOperation.End)
        self.log.insertPlainText(chunk)
        self.log.ensureCursorVisible()
        st = colorlab.spotread_state(self.buf)
        if st == "result":
            vals = colorlab.parse_measurements(self.buf)
            if vals:
                self._add(vals[-1], tr("gemessen"))
                self.buf = ""
                self.lbl_state.setText(tr("Gemessen. Für einen Mittelwert an einer anderen Stelle nochmal „Messen“."))
            self.btn_next.setEnabled(False)
        elif st == "calibrate":
            self.lbl_state.setText(tr("Kalibrieren: Gerät auf die Kalibrierstellung/weiße Kachel setzen, dann „Weiter“."))
            self.btn_next.setEnabled(True)
        elif st == "measure":
            self.lbl_state.setText(tr("Messen: Gerät flach aufs Papier setzen, dann „Weiter“."))
            self.btn_next.setEnabled(True)
        elif st == "error":
            self.lbl_state.setText(tr("Das Gerät meldet einen Fehler – siehe Protokoll."))

    def _key(self):
        if self.proc is not None:
            self.proc.write(b" ")
            self.btn_next.setEnabled(False)
            self.lbl_state.setText(tr("Messung läuft …"))

    def _stop(self):
        if self.proc is not None:
            self.proc.write(b"q")
            if not self.proc.waitForFinished(1500):
                self.proc.kill()

    def _finished(self, *_):
        p, self.proc = self.proc, None
        if p is not None:
            p.deleteLater()
        self.btn_measure.setEnabled(bool(self.exe))
        self.btn_next.setEnabled(False)
        self.btn_stop.setEnabled(False)
        if self.lbl_state.text() == tr("Gerät wird gesucht …") or "…" in self.lbl_state.text():
            self.lbl_state.setText(tr("spotread beendet – siehe Protokoll."))

    def done(self, r):
        if self.proc is not None:
            self.proc.kill()
            self.proc.waitForFinished(1000)
        super().done(r)
