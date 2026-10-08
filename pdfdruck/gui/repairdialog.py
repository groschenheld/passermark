# SPDX-License-Identifier: GPL-3.0-or-later
# pdfToolkit – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Dialog: PDFs reparieren, für die Weitergabe optimieren, Passwortschutz setzen/entfernen."""
from __future__ import annotations

from ..l10n import tr

import os

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QPushButton, QRadioButton, QVBoxLayout)

from .. import repair
from . import theme
from .common import fit_width

MODE_HELP = {
    "repair": "Behebt beschädigte Dateistrukturen („Datei ist beschädigt“, Acrobat öffnet nicht). "
              "Der Inhalt bleibt unverändert. Schnell, verlustfrei.",
    "print": "Erzeugt das PDF sauber neu: alle Schriften eingebettet, normgerechte Struktur. Hilft, wenn "
             "Acrobat nicht öffnet oder nicht druckt, der Browser aber schon. Empfohlen vor dem Versand.",
    "screen": "Wie oben, Bilder zusätzlich auf 150 dpi reduziert – deutlich kleinere Dateien für Mail.",
    "pdfa": "Langzeitarchiv-Format nach ISO 19005-2 (z. B. für Behörden, Gerichte, Archive). "
            "Kann nicht verschlüsselt werden.",
}


def _mb(n):
    return f"{n / 1048576:.1f} MB" if n >= 1048576 else f"{n / 1024:.0f} KB"


class _Worker(QThread):
    progress = Signal(str)
    done = Signal(list)

    def __init__(self, jobs):
        super().__init__()
        self.jobs = jobs          # [(src, dst, mode, pw_in, pw_new, allow_print)]

    def run(self):
        out = []
        for src, dst, mode, pw, npw, allow in self.jobs:
            self.progress.emit(f"Bearbeite {os.path.basename(src)} …")
            try:
                out.append(("ok", repair.process(src, dst, mode, pw, npw, allow)))
            except repair.PasswordRequired:
                out.append(("err", tr("{0}: falsches oder fehlendes Passwort").format(os.path.basename(src))))
            except Exception as e:
                out.append(("err", f"{os.path.basename(src)}: {e}"))
        self.done.emit(out)


class RepairDialog(QDialog):
    def __init__(self, parent, files: list[str], display_names: dict | None = None,
                 out_dir: str | None = None, open_cb=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Reparieren, optimieren, Passwortschutz – pdfToolkit"))
        self.resize(640, 640)
        self.files = files
        self.names = display_names or {}
        self.out_dir = out_dir
        self.open_cb = open_cb
        self.passwords: dict[str, str] = {}
        self.results = []
        v = QVBoxLayout(self)

        lbl = QLabel(tr("<b>Dateien:</b> ") + ", ".join(self.names.get(f, os.path.basename(f)) for f in files[:6])
                     + (f" … (+{len(files) - 6})" if len(files) > 6 else ""))
        lbl.setWordWrap(True)
        v.addWidget(lbl)

        g = QGroupBox(tr("Was soll gemacht werden?"))
        gl = QVBoxLayout(g)
        self.mode_group = QButtonGroup(self)
        for key, text in repair.MODES.items():
            rb = QRadioButton(tr(text))
            rb.setProperty("mode", key)
            rb.setToolTip(tr(MODE_HELP[key]))
            self.mode_group.addButton(rb)
            gl.addWidget(rb)
            if key == "print":
                rb.setChecked(True)
        self.lbl_help = QLabel()
        self.lbl_help.setWordWrap(True)
        self.lbl_help.setStyleSheet(f"color: {theme.MUTED};")
        gl.addWidget(self.lbl_help)
        v.addWidget(g)

        g = QGroupBox(tr("Passwortschutz der neuen Datei"))
        f = QFormLayout(g)
        self.chk_pw = QCheckBox(tr("Mit Passwort schützen (AES-256)"))
        f.addRow(self.chk_pw)
        self.ed_pw = QLineEdit()
        self.ed_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.ed_pw2 = QLineEdit()
        self.ed_pw2.setEchoMode(QLineEdit.EchoMode.Password)
        f.addRow(tr("Passwort:"), self.ed_pw)
        f.addRow(tr("Wiederholen:"), self.ed_pw2)
        self.chk_allowprint = QCheckBox(tr("Drucken erlauben"))
        self.chk_allowprint.setChecked(True)
        f.addRow(self.chk_allowprint)
        note = QLabel(tr("Ohne Haken wird die neue Datei <b>ohne</b> Passwort gespeichert – so entfernst du "
                      "auch einen bestehenden Schutz (das Passwort der Quelldatei wird beim Start abgefragt)."))
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {theme.MUTED};")
        f.addRow(note)
        v.addWidget(g)

        g = QGroupBox(tr("Speichern"))
        f = QFormLayout(g)
        if len(files) == 1:
            row = QHBoxLayout()
            self.ed_out = QLineEdit()
            btn = QPushButton(tr("Durchsuchen…"))
            btn.clicked.connect(self._browse)
            row.addWidget(self.ed_out, 1)
            row.addWidget(btn)
            f.addRow(tr("Ziel:"), row)
        else:
            self.ed_out = None
            f.addRow(QLabel(tr("Neben der jeweiligen Originaldatei, mit Namenszusatz (z. B. „_optimiert“).")))
        v.addWidget(g)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(130)
        v.addWidget(self.log)

        self.bb = QDialogButtonBox()
        self.btn_start = self.bb.addButton(tr("Starten"), QDialogButtonBox.ButtonRole.AcceptRole)
        self.btn_start.setDefault(True)
        self.btn_open = self.bb.addButton(tr("Ergebnis öffnen"), QDialogButtonBox.ButtonRole.ActionRole)
        self.btn_open.setVisible(False)
        self.bb.addButton(tr("Schließen"), QDialogButtonBox.ButtonRole.RejectRole)
        self.btn_start.clicked.connect(self._start)
        self.btn_open.clicked.connect(self._open_result)
        self.bb.rejected.connect(self.reject)
        v.addWidget(self.bb)

        self.mode_group.buttonClicked.connect(self._mode_changed)
        self.chk_pw.toggled.connect(self._sync)
        self._mode_changed()
        fit_width(self)

    # ------------------------------------------------------------------ #
    def _mode(self):
        b = self.mode_group.checkedButton()
        return b.property("mode") if b else "print"

    def _default_out(self, src):
        dst = repair.default_output(src, self._mode())
        if self.out_dir:
            name = self.names.get(src, os.path.basename(src))
            base = os.path.splitext(name)[0]
            dst = os.path.join(self.out_dir, base + repair.SUFFIX[self._mode()] + ".pdf")
        return dst

    def _mode_changed(self, *_):
        self.lbl_help.setText(tr(MODE_HELP[self._mode()]))
        if self.ed_out is not None:
            self.ed_out.setText(self._default_out(self.files[0]))
        self._sync()

    def _sync(self):
        pdfa = self._mode() == "pdfa"
        self.chk_pw.setEnabled(not pdfa)
        on = self.chk_pw.isChecked() and not pdfa
        for w in (self.ed_pw, self.ed_pw2, self.chk_allowprint):
            w.setEnabled(on)

    def _browse(self):
        p, _ = QFileDialog.getSaveFileName(self, tr("Speichern unter"), self.ed_out.text(), tr("PDF-Dateien (*.pdf)"))
        if p:
            self.ed_out.setText(p if p.lower().endswith(".pdf") else p + ".pdf")

    # ------------------------------------------------------------------ #
    def _start(self):
        npw = None
        if self.chk_pw.isChecked() and self._mode() != "pdfa":
            if not self.ed_pw.text():
                QMessageBox.warning(self, tr("Passwort"), tr("Bitte ein Passwort eingeben."))
                return
            if self.ed_pw.text() != self.ed_pw2.text():
                QMessageBox.warning(self, tr("Passwort"), tr("Die Passwörter stimmen nicht überein."))
                return
            npw = self.ed_pw.text()
        jobs = []
        for src in self.files:
            # Passwort der Quelle vorab abfragen (im Hauptthread)
            if src not in self.passwords and repair.needs_password(src):
                while True:
                    pw, ok = QInputDialog.getText(self, tr("Passwortgeschützt"),
                                                  tr("Passwort für „{0}“:").format(self.names.get(src, os.path.basename(src))),
                                                  QLineEdit.EchoMode.Password)
                    if not ok:
                        break
                    try:
                        repair._pages(src, pw)
                        self.passwords[src] = pw
                        break
                    except repair.PasswordRequired:
                        QMessageBox.warning(self, tr("Passwort"), tr("Falsches Passwort."))
                if src not in self.passwords:
                    self.log.appendPlainText(tr("⏭ {0}: übersprungen (kein Passwort)").format(os.path.basename(src)))
                    continue
            dst = self.ed_out.text().strip() if self.ed_out is not None else self._default_out(src)
            if os.path.abspath(dst) == os.path.abspath(src):
                QMessageBox.warning(self, tr("Ziel"), tr("Das Ziel darf nicht die Quelldatei sein."))
                return
            if os.path.exists(dst) and QMessageBox.question(
                    self, tr("Überschreiben?"), tr("{0} existiert bereits. Überschreiben?").format(os.path.basename(dst))
            ) != QMessageBox.StandardButton.Yes:
                continue
            jobs.append((src, dst, self._mode(), self.passwords.get(src), npw, self.chk_allowprint.isChecked()))
        if not jobs:
            return
        self.btn_start.setEnabled(False)
        self._worker = _Worker(jobs)
        self._worker.progress.connect(self.log.appendPlainText)
        self._worker.done.connect(self._finished)
        self._worker.start()

    def _finished(self, out):
        self.btn_start.setEnabled(True)
        self.results = [r for kind, r in out if kind == "ok"]
        for kind, r in out:
            if kind == "ok":
                mark = "✓" if r.ok else "⚠"
                self.log.appendPlainText(
                    tr("{0} {1} → {2}  ·  {3} Seiten  ·  {4} → {5}").format(mark, self.names.get(r.src, os.path.basename(r.src)), os.path.basename(r.dst), r.pages_out, _mb(r.size_in), _mb(r.size_out)))
                for n in r.notes:
                    self.log.appendPlainText("   " + n)
            else:
                self.log.appendPlainText("✗ " + r)
        self.btn_open.setVisible(len(self.results) == 1 and self.open_cb is not None)

    def _open_result(self):
        if self.results and self.open_cb:
            self.open_cb(self.results[0].dst)
            self.accept()
