# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Admin: Farbprofile für einen Drucker beschaffen – Bezugsquellen, Link-Download, Datei/ZIP/Treiberpaket."""
from __future__ import annotations

from ..l10n import tr

import html

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMessageBox, QProgressDialog, QPushButton, QVBoxLayout)

from .. import iccfetch
from . import theme
from .common import fill_combo, fit_width


class IccImportDialog(QDialog):
    """Ergebnis: self.selected = [(IccInfo, druckername)]"""

    def __init__(self, parent, printers, current: str | None, workdir: str):
        super().__init__(parent)
        self.setWindowTitle(tr("Farbprofile laden und zuordnen"))
        self.resize(760, 640)
        self.printers = printers
        self.workdir = workdir
        self.selected = []
        v = QVBoxLayout(self)

        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Für Drucker:")))
        self.cmb = QComboBox()
        fill_combo(self.cmb, [(p.name, f"{p.name}  –  {p.model}" if p.model else p.name) for p in printers],
                   current or (printers[0].name if printers else ""))
        self.cmb.currentIndexChanged.connect(self._show_sources)
        row.addWidget(self.cmb, 1)
        v.addLayout(row)

        g = QGroupBox(tr("1. Bezugsquellen"))
        gl = QVBoxLayout(g)
        self.lbl_src = QLabel()
        self.lbl_src.setWordWrap(True)
        self.lbl_src.setOpenExternalLinks(True)
        self.lbl_src.setTextFormat(Qt.TextFormat.RichText)
        gl.addWidget(self.lbl_src)
        v.addWidget(g)

        g = QGroupBox(tr("2. Profil laden"))
        gl = QVBoxLayout(g)
        r1 = QHBoxLayout()
        btn = QPushButton(tr("Datei / ZIP / Treiberpaket…"))
        btn.clicked.connect(self._from_file)
        r1.addWidget(btn)
        r1.addStretch()
        gl.addLayout(r1)
        r2 = QHBoxLayout()
        self.ed_url = QLineEdit()
        self.ed_url.setPlaceholderText(tr("oder direkter https-Link zu .icc / .icm / .zip / Treiber-.exe"))
        btn2 = QPushButton(tr("Laden"))
        btn2.clicked.connect(self._from_url)
        r2.addWidget(self.ed_url, 1)
        r2.addWidget(btn2)
        gl.addLayout(r2)
        v.addWidget(g)

        g = QGroupBox(tr("3. Gefundene Profile – zum Import anhaken"))
        gl = QVBoxLayout(g)
        self.lst = QListWidget()
        gl.addWidget(self.lst)
        hint = QLabel(tr("Nur Druckerprofile (Klasse „Drucker“) sind als Ausgabeprofil sinnvoll; andere "
                      "werden angezeigt, aber nicht vorausgewählt. Für den Epson unter Linux: RGB-Profile."))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {theme.MUTED};")
        gl.addWidget(hint)
        v.addWidget(g, 1)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Übernehmen"))
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self._show_sources()
        fit_width(self)

    def _model(self):
        name = self.cmb.currentData()
        return next((p.model for p in self.printers if p.name == name), "") or (name or "")

    def _show_sources(self, *_):
        parts = []
        for s in iccfetch.sources_for(self._model()):
            parts.append(f'<p><a style="color:{theme.ACCENT}" href="{html.escape(s["url"])}">'
                         f'{html.escape(tr(s["name"]))}</a><br><span style="color:{theme.MUTED}">'
                         f'{html.escape(tr(s["hint"]))}</span></p>')
        parts.append(f'<p style="color:{theme.MUTED}">' + tr("Profile gelten immer für Drucker + Papier + Tinte. Herstellerprofile sind für den Windows/Mac-Treiber gemacht – unter Linux eine gute Annäherung. Am genauesten: eigenes Profil über den Linux-Druckweg (ArgyllCMS).") + "</p>")
        self.lbl_src.setText("".join(parts))

    # ------------------------------------------------------------------ #
    def _add_results(self, infos):
        if not infos:
            QMessageBox.information(self, tr("Keine Profile"), tr("In dieser Datei wurden keine ICC-Profile gefunden."))
            return
        for i in infos:
            it = QListWidgetItem(f"{i.desc}   ·   {i.space}, {tr(i.klass_text)}   ·   {i.name.split('_', 1)[-1]}")
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if i.ok_output and len(infos) <= 3 else Qt.CheckState.Unchecked)
            it.setToolTip(i.path)
            it.setData(Qt.ItemDataRole.UserRole, i)
            if not i.ok_output:
                it.setForeground(Qt.GlobalColor.gray)
            self.lst.addItem(it)

    def _from_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Profil, ZIP oder Treiberpaket wählen"), "",
            tr("Profile und Pakete (*.icc *.icm *.ICC *.ICM *.zip *.exe *.cab *.7z *.dmg *.pkg *.msi);;Alle Dateien (*)"))
        if path:
            self._extract(path)

    def _extract(self, path):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            infos = iccfetch.extract_icc(path, self.workdir)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, tr("Entpacken"), str(e))
            return
        QApplication.restoreOverrideCursor()
        self._add_results(infos)

    def _from_url(self):
        url = self.ed_url.text().strip()
        if not url:
            return
        dlg = QProgressDialog(tr("Lade …"), tr("Abbrechen"), 0, 100, self)
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setMinimumDuration(0)

        def progress(n, total):
            if total:
                dlg.setValue(int(n * 100 / total))
            dlg.setLabelText(tr("Lade … {0:.1f} MB").format(n / 1048576))
            QApplication.processEvents()
            if dlg.wasCanceled():
                raise RuntimeError(tr("Abgebrochen."))
        try:
            path = iccfetch.download(url, self.workdir, progress)
        except Exception as e:
            dlg.close()
            QMessageBox.critical(self, tr("Download"), str(e))
            return
        dlg.close()
        self._extract(path)

    def _accept(self):
        printer = self.cmb.currentData()
        for i in range(self.lst.count()):
            it = self.lst.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                self.selected.append((it.data(Qt.ItemDataRole.UserRole), printer))
        if not self.selected:
            QMessageBox.information(self, tr("Nichts ausgewählt"), tr("Bitte mindestens ein Profil anhaken."))
            return
        self.accept()
