# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""File → Settings: the user's personal settings (currently: language)."""
from __future__ import annotations

import sys

from PySide6.QtCore import QProcess, Qt
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
        from .. import printlog
        g5 = QGroupBox(tr("Druckprotokoll"))
        f5 = QFormLayout(g5)
        self.chk_plog = QCheckBox(tr("Jeden Druckauftrag mit allen Einstellungen protokollieren"))
        forced = bool(printlog.admin_cfg().get("force"))
        self.chk_plog.setChecked(forced or bool(self.settings.get("print_log", False)))
        self.chk_plog.setEnabled(not forced)
        if forced:
            self.chk_plog.setToolTip(tr("Vom Administrator für alle eingeschaltet"))
        f5.addRow(self.chk_plog)
        lbl = QLabel(tr("Ordner: {0}").format(printlog.folder()) + "\n" +
                     tr("Je Auftrag eine JSON-Datei plus printlog.csv – nochmal genauso drucken: "
                        "passermark-cli reprint <datei.json>"))
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(lbl.textInteractionFlags() | Qt.TextInteractionFlag.TextSelectableByMouse)
        lbl.setStyleSheet(f"color: {theme.MUTED};")
        f5.addRow(lbl)
        v.addWidget(g5)
        g4 = QGroupBox(tr("Fenster"))
        f4 = QFormLayout(g4)
        self.chk_tabs = QCheckBox(tr("Im Programm Geöffnetes als Reiter im selben Fenster"))
        self.chk_tabs.setChecked(bool(self.settings.get("open_in_tabs", True)))
        self.chk_tabs.setToolTip(tr("Öffnen-Knopf, Hineinziehen und Ergebnisse (CutContour, CMYK …) kommen als Reiter. "
                                    "Programmstart und Doppelklick im Dateimanager öffnen immer ein eigenes Fenster."))
        f4.addRow(self.chk_tabs)
        v.addWidget(g4)
        from .. import platform as _platform
        self.cmb_wmode = self.cmb_wdpi = None
        if _platform.IS_WIN:
            g3 = QGroupBox(tr("Drucken unter Windows"))
            f3 = QFormLayout(g3)
            self.cmb_wmode = QComboBox()
            for val, txt in (("auto", tr("Automatisch (Raster – der verträglichste Weg)")),
                             ("raster_jpeg", tr("Raster + JPEG (kleinere Aufträge, nicht jeder Treiber)")),
                             ("postscript", tr("PostScript (Canon PS3, Fiery …)")),
                             ("vector", tr("Vektor über GDI (früheres Verfahren)"))):
                self.cmb_wmode.addItem(txt, val)
            self.cmb_wmode.setCurrentIndex(max(0, self.cmb_wmode.findData(self.settings.get("win_print_mode", "auto"))))
            f3.addRow(tr("Verfahren:"), self.cmb_wmode)
            self.cmb_wdpi = QComboBox()
            for val, txt in ((0, tr("Automatisch (600 dpi mit JPEG, sonst 300 dpi)")), (300, "300 dpi"), (400, "400 dpi"),
                             (600, "600 dpi"), (1200, "1200 dpi")):
                self.cmb_wdpi.addItem(txt, val)
            self.cmb_wdpi.setCurrentIndex(max(0, self.cmb_wdpi.findData(int(self.settings.get("win_raster_dpi", 0) or 0))))
            f3.addRow(tr("Raster-Auflösung:"), self.cmb_wdpi)
            hint = QLabel(tr("Leere Blätter oder Fehler? Hilfe → Windows-Druck testen schickt je Verfahren eine "
                             "Testseite – dann das Verfahren wählen, dessen Seite richtig ankommt."))
            hint.setWordWrap(True)
            hint.setStyleSheet(f"color: {theme.MUTED};")
            f3.addRow(hint)
            v.addWidget(g3)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _ok(self):
        new = self.cmb.currentData()
        old = self.settings.get("language", "auto")
        self.settings["language"] = new
        if self.cmb_wmode is not None:
            self.settings["win_print_mode"] = self.cmb_wmode.currentData()
            self.settings["win_raster_dpi"] = int(self.cmb_wdpi.currentData() or 0)
        self.settings["preflight_on_open"] = self.chk_pf.isChecked()
        self.settings["open_in_tabs"] = self.chk_tabs.isChecked()
        if self.chk_plog.isEnabled():
            self.settings["print_log"] = self.chk_plog.isChecked()
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
    """Close all windows (with a save prompt), release the single instance, restart."""
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
