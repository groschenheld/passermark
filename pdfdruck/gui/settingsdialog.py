# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Datei → Einstellungen: persönliche Einstellungen des Benutzers (derzeit: Sprache)."""
from __future__ import annotations

import sys

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox,
                               QLabel, QMessageBox, QVBoxLayout)

from .. import l10n
from ..l10n import tr
from . import theme


class SettingsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(tr("Einstellungen"))
        self.resize(460, 220)
        self.settings = l10n.load_settings()
        v = QVBoxLayout(self)
        g = QGroupBox(tr("Sprache"))
        f = QFormLayout(g)
        self.cmb = QComboBox()
        self.cmb.addItem(tr("Automatisch (Systemsprache)"), "auto")
        for code, name in l10n.LANGS.items():          # Sprachnamen immer in der eigenen Sprache
            self.cmb.addItem(name, code)
        i = self.cmb.findData(self.settings.get("language", "auto"))
        self.cmb.setCurrentIndex(max(0, i))
        f.addRow(tr("Oberflächensprache:"), self.cmb)
        note = QLabel(tr("Die Sprache wird nach einem Neustart von Passermark wirksam."))
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {theme.MUTED};")
        f.addRow(note)
        v.addWidget(g)
        g2 = QGroupBox(tr("Dokumentprüfung"))
        f2 = QFormLayout(g2)
        self.chk_pf = QCheckBox(tr("Dokumente beim Öffnen automatisch prüfen (Schriften, Ebenen, Transparenz)"))
        self.chk_pf.setChecked(bool(self.settings.get("preflight_on_open", True)))
        f2.addRow(self.chk_pf)
        v.addWidget(g2)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _ok(self):
        new = self.cmb.currentData()
        old = self.settings.get("language", "auto")
        self.settings["language"] = new
        self.settings["preflight_on_open"] = self.chk_pf.isChecked()
        try:
            l10n.save_settings(self.settings)
        except OSError as e:
            QMessageBox.critical(self, tr("Einstellungen"), tr("Speichern nicht möglich:\n{0}").format(e))
            return
        self.accept()
        if new != old and QMessageBox.question(
                self.parent(), tr("Neustart"), tr("Passermark jetzt neu starten, damit die Sprache wirksam wird?")
        ) == QMessageBox.StandardButton.Yes:
            restart(self.parent())


def restart(window):
    """Alle Fenster schließen (mit Speichern-Rückfrage), Einzelinstanz freigeben, neu starten."""
    ctl = getattr(window, "ctl", None)
    for w in list(getattr(ctl, "windows", [])):
        if not w.close():
            return                       # Benutzer hat beim Speichern abgebrochen
    if ctl is not None and ctl.server is not None:
        ctl.server.close()
    if getattr(sys, "frozen", False):
        QProcess.startDetached(sys.executable, [])
    else:
        QProcess.startDetached(sys.executable, ["-m", "pdfdruck"])
    QApplication.instance().quit()
