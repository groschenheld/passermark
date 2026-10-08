# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Preset-Leiste für Dialoge: gespeicherte Einstellungen wählen, speichern, löschen, als Datei weitergeben."""
from __future__ import annotations

import os

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QMenu, QMessageBox,
                               QToolButton, QWidget)

from .. import core, presets
from ..l10n import tr


class PresetBar(QWidget):
    """get_settings() -> Datenklasse, set_settings(datenklasse) setzt die Felder des Dialogs."""

    def __init__(self, parent, kind: str, get_settings, set_settings):
        super().__init__(parent)
        self.kind, self.get_settings, self.set_settings = kind, get_settings, set_settings
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(QLabel(tr("Preset:")))
        self.cmb = QComboBox()
        self.cmb.setToolTip(tr("Gespeicherte Einstellungen – gelten auch für die Kommandozeile (--preset NAME)"))
        self.cmb.activated.connect(self._chosen)
        h.addWidget(self.cmb, 1)
        self.btn_save = QToolButton()
        self.btn_save.setText(tr("Speichern…"))
        self.btn_save.setToolTip(tr("Aktuelle Einstellungen als Preset speichern"))
        self.btn_save.clicked.connect(self._save)
        h.addWidget(self.btn_save)
        self.btn_more = QToolButton()
        self.btn_more.setText("…")
        self.btn_more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        m = QMenu(self)
        self.a_del = m.addAction(tr("Gewähltes Preset löschen"), self._delete)
        m.addSeparator()
        m.addAction(tr("Aus Datei laden…"), self._import)
        m.addAction(tr("Als Datei exportieren…"), self._export)
        m.addAction(tr("Preset-Ordner öffnen"), self._open_dir)
        m.addSeparator()
        m.addAction(tr("Standardwerte"), self._defaults)
        self.btn_more.setMenu(m)
        h.addWidget(self.btn_more)
        self.refresh()

    # -------------------------------------------------------------- #
    def refresh(self, select: str | None = None):
        self.cmb.blockSignals(True)
        self.cmb.clear()
        self.cmb.addItem(tr("– wählen –"), None)
        for n in presets.list_presets(self.kind):
            self.cmb.addItem(n, n)
        i = self.cmb.findData(select) if select else 0
        self.cmb.setCurrentIndex(max(0, i))
        self.cmb.blockSignals(False)
        self.a_del.setEnabled(self.cmb.count() > 1)

    def current(self) -> str | None:
        return self.cmb.currentData()

    def _apply(self, s, name=None):
        try:
            self.set_settings(s)
        except Exception as e:                   # z. B. Wert außerhalb des Bereichs – lieber melden als abstürzen
            QMessageBox.warning(self, tr("Preset"), tr("Preset konnte nicht vollständig übernommen werden:") + f"\n{e}")

    def _chosen(self, _i):
        name = self.current()
        if not name:
            return
        try:
            s = presets.load(self.kind, name)
        except Exception as e:
            QMessageBox.warning(self, tr("Preset"), str(e))
            self.refresh()
            return
        self._apply(s, name)

    def _save(self):
        name, ok = QInputDialog.getText(self, tr("Preset speichern"), tr("Name:"), text=self.current() or "")
        if not ok or not name.strip():
            return
        try:
            clean = presets.clean_name(name)
        except ValueError as e:
            QMessageBox.warning(self, tr("Preset"), str(e))
            return
        if clean in presets.list_presets(self.kind) and clean != self.current():
            if QMessageBox.question(self, tr("Preset"), tr("„{0}“ gibt es schon. Überschreiben?").format(clean)) \
                    != QMessageBox.StandardButton.Yes:
                return
        try:
            presets.save(self.kind, clean, self.get_settings())
        except OSError as e:
            QMessageBox.warning(self, tr("Preset"), str(e))
            return
        self.refresh(clean)

    def _delete(self):
        name = self.current()
        if not name:
            QMessageBox.information(self, tr("Preset"), tr("Bitte zuerst ein Preset wählen."))
            return
        if QMessageBox.question(self, tr("Preset"), tr("Preset „{0}“ löschen?").format(name)) \
                == QMessageBox.StandardButton.Yes:
            presets.delete(self.kind, name)
            self.refresh()

    def _import(self):
        p, _ = QFileDialog.getOpenFileName(self, tr("Preset laden"), "", tr("Presets (*.json)"))
        if not p:
            return
        try:
            kind, d = core.load_settings(p)
            if kind != self.kind:
                raise ValueError(tr("Preset ist für „{0}“, nicht für „{1}“").format(kind, self.kind))
            s = core.settings_from_dict(presets.settings_class(self.kind), d)
        except Exception as e:
            QMessageBox.warning(self, tr("Preset"), str(e))
            return
        self._apply(s)
        name = os.path.splitext(os.path.basename(p))[0]
        if QMessageBox.question(self, tr("Preset"), tr("Unter „{0}“ in die Preset-Liste aufnehmen?").format(name)) \
                == QMessageBox.StandardButton.Yes:
            try:
                presets.save(self.kind, name, s)
                self.refresh(presets.clean_name(name))
            except (OSError, ValueError) as e:
                QMessageBox.warning(self, tr("Preset"), str(e))

    def _export(self):
        p, _ = QFileDialog.getSaveFileName(self, tr("Preset exportieren"), (self.current() or self.kind) + ".json",
                                           tr("Presets (*.json)"))
        if not p:
            return
        if not p.lower().endswith(".json"):
            p += ".json"
        try:
            core.save_settings(p, self.kind, self.get_settings())
        except OSError as e:
            QMessageBox.warning(self, tr("Preset"), str(e))

    def _open_dir(self):
        d = presets.job_dir(self.kind)
        os.makedirs(d, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(d))

    def _defaults(self):
        self._apply(presets.settings_class(self.kind)())
        self.refresh()
