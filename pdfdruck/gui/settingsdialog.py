# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""File → Settings: the user's personal settings (currently: language)."""

from __future__ import annotations

import sys

from PySide6.QtCore import QProcess, Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from .. import l10n
from ..l10n import tr
from . import lastdir
from . import theme


class SettingsDialog(QDialog):
    """Dialog "Einstellungen": the user's program settings (language, document check, print log …)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(tr("Einstellungen"))
        self.resize(460, 220)
        self.settings = l10n.load_settings()
        v = QVBoxLayout(self)
        self._build_language_group(v)
        self._build_check_group(v)
        self._build_print_log_group(v)
        self._build_error_log_group(v)
        self._build_window_group(v)
        from .. import platform as _platform

        self.cmb_wmode = self.cmb_wdpi = None
        if _platform.IS_WIN:
            g3 = QGroupBox(tr("Drucken unter Windows"))
            f3 = QFormLayout(g3)
            self.cmb_wmode = QComboBox()
            for val, txt in (
                ("auto", tr("Automatisch (Raster – der verträglichste Weg)")),
                ("raster_jpeg", tr("Raster + JPEG (kleinere Aufträge, nicht jeder Treiber)")),
                ("postscript", tr("PostScript (Canon PS3, Fiery …)")),
                ("vector", tr("Vektor über GDI (früheres Verfahren)")),
            ):
                self.cmb_wmode.addItem(txt, val)
            self.cmb_wmode.setCurrentIndex(max(0, self.cmb_wmode.findData(self.settings.get("win_print_mode", "auto"))))
            f3.addRow(tr("Verfahren:"), self.cmb_wmode)
            self.cmb_wdpi = QComboBox()
            for val, txt in (
                (0, tr("Automatisch (600 dpi mit JPEG, sonst 300 dpi)")),
                (300, "300 dpi"),
                (400, "400 dpi"),
                (600, "600 dpi"),
                (1200, "1200 dpi"),
            ):
                self.cmb_wdpi.addItem(txt, val)
            self.cmb_wdpi.setCurrentIndex(
                max(0, self.cmb_wdpi.findData(int(self.settings.get("win_raster_dpi", 0) or 0)))
            )
            f3.addRow(tr("Raster-Auflösung:"), self.cmb_wdpi)
            hint = QLabel(
                tr(
                    "Leere Blätter oder Fehler? Hilfe → Windows-Druck testen schickt je Verfahren eine "
                    "Testseite – dann das Verfahren wählen, dessen Seite richtig ankommt."
                )
            )
            hint.setWordWrap(True)
            hint.setStyleSheet(f"color: {theme.MUTED};")
            f3.addRow(hint)
            v.addWidget(g3)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _build_language_group(self, v):
        """Group "Sprache"."""
        g = QGroupBox(tr("Sprache"))
        f = QFormLayout(g)
        self.cmb = QComboBox()
        self.cmb.addItem(tr("Automatisch (Systemsprache)"), "auto")
        self._fill_languages(self.settings.get("language", "auto"))
        f.addRow(tr("Oberflächensprache:"), self.cmb)
        note = QLabel(tr("Die Sprache wird nach einem Neustart von Passermark wirksam."))
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {theme.MUTED};")
        f.addRow(note)
        # translations by anyone: export a table, fill it in, play it back in (langpack.py, docs/translating.md)
        row = QHBoxLayout()
        b_exp = QPushButton(tr("Übersetzungsvorlage exportieren …"))
        b_exp.setToolTip(
            tr(
                "Alle Texte als Tabelle (CSV für Excel/LibreOffice oder JSON) – mit Englisch als Hilfe und, bei einer gewählten Sprache, ihrer bisherigen Übersetzung"
            )
        )
        b_exp.clicked.connect(self._export_translation)
        b_imp = QPushButton(tr("Übersetzung einspielen …"))
        b_imp.setToolTip(tr("Ausgefüllte Tabelle prüfen und für diesen Benutzer installieren"))
        b_imp.clicked.connect(self._install_translation)
        self.b_rm = QPushButton(tr("Entfernen"))
        self.b_rm.setToolTip(tr("Eingespielte Übersetzung der gewählten Sprache entfernen"))
        self.b_rm.clicked.connect(self._remove_translation)
        for b in (b_exp, b_imp, self.b_rm):
            row.addWidget(b)
        f.addRow(row)
        self.cmb.currentIndexChanged.connect(lambda _i: self._sync_remove())
        self._sync_remove()
        v.addWidget(g)

    def _fill_languages(self, select: str):
        """Shipped and installed languages; names always in their own language."""
        self.cmb.blockSignals(True)
        while self.cmb.count() > 1:
            self.cmb.removeItem(1)
        user = l10n.user_languages()
        for code, name in l10n.languages().items():
            self.cmb.addItem(name + (" ✎" if code in user else ""), code)
        self.cmb.setCurrentIndex(max(0, self.cmb.findData(select)))
        self.cmb.blockSignals(False)

    def _sync_remove(self):
        self.b_rm.setEnabled(self.cmb.currentData() in l10n.user_languages())

    def _export_translation(self):
        from .. import langpack

        code = self.cmb.currentData()
        code = code if code not in ("auto", "de") else None
        name = f"passermark-{code or 'translation'}.csv"
        path, _f = lastdir.getSaveFileName(
            self, tr("Übersetzungsvorlage exportieren"), name, tr("Tabelle (*.csv);;JSON (*.json)")
        )
        if not path:
            return
        try:
            n = langpack.export(path, code)
        except OSError as e:
            QMessageBox.critical(self, tr("Übersetzung"), tr("Speichern nicht möglich:\n{0}").format(e))
            return
        QMessageBox.information(
            self,
            tr("Übersetzung"),
            tr(
                "{0} Texte geschrieben. Spalte „translation“ ausfüllen, dann mit „Übersetzung einspielen …“ laden."
            ).format(n),
        )

    def _install_translation(self):
        from .. import langpack

        path, _f = lastdir.getOpenFileName(self, tr("Übersetzung einspielen"), "", tr("Übersetzung (*.csv *.json)"))
        if not path:
            return
        try:
            meta, msgs = langpack.read(path)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, tr("Übersetzung"), tr("Datei nicht lesbar:\n{0}").format(e))
            return
        rep = langpack.check(msgs)
        if not rep.translated:
            QMessageBox.warning(
                self, tr("Übersetzung"), tr("In der Datei ist nichts übersetzt (Spalte „translation“).")
            )
            return
        if not rep.ok:
            bad = "\n".join(f"• {src[:60]}" for src, _w in rep.problems[:8])
            QMessageBox.warning(
                self,
                tr("Übersetzung"),
                tr("Platzhalter wie {{0}} fehlen oder sind verändert – bitte zuerst korrigieren:\n{0}").format(bad),
            )
            return
        code = meta.get("language") or ""
        if not langpack.valid_code(code):
            code, ok = QInputDialog.getText(
                self, tr("Übersetzung"), tr("Sprachkürzel (z. B. it, pl, pt_BR – für Ungarisch hu):")
            )
            code = code.strip()
            if not ok or not langpack.valid_code(code):
                return
        name = meta.get("name") or l10n.LANGS.get(code, "")
        if not name:
            name, ok = QInputDialog.getText(
                self, tr("Übersetzung"), tr("Name der Sprache in der Sprache selbst (z. B. Italiano):")
            )
            if not ok or not name.strip():
                return
        try:
            langpack.install(msgs, code, name.strip())
        except (OSError, ValueError) as e:
            QMessageBox.critical(self, tr("Übersetzung"), tr("Installieren nicht möglich:\n{0}").format(e))
            return
        self._fill_languages(code)
        self._sync_remove()
        QMessageBox.information(
            self,
            tr("Übersetzung"),
            tr("{0}: {1} von {2} Texten übersetzt ({3} %). Fehlende Texte erscheinen wie bisher.").format(
                name, rep.translated, rep.total, rep.percent
            )
            + "\n"
            + tr("Mit OK speichern – die Sprache wirkt nach einem Neustart."),
        )

    def _remove_translation(self):
        from .. import langpack

        code = self.cmb.currentData()
        if langpack.remove(code):
            self._fill_languages(code if code in l10n.languages() else "auto")
            self._sync_remove()

    def _build_check_group(self, v):
        """Group "Dokumentprüfung"."""
        g2 = QGroupBox(tr("Dokumentprüfung"))
        f2 = QFormLayout(g2)
        self.chk_pf = QCheckBox(tr("Dokumente beim Öffnen automatisch prüfen (Schriften, Ebenen, Transparenz)"))
        self.chk_pf.setChecked(bool(self.settings.get("preflight_on_open", True)))
        f2.addRow(self.chk_pf)
        v.addWidget(g2)

    def _build_print_log_group(self, v):
        """Group "Druckprotokoll": whether to log, where, and how long to keep."""
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
        lbl = QLabel(
            tr("Ordner: {0}").format(printlog.folder())
            + "\n"
            + tr(
                "Je Auftrag eine JSON-Datei plus printlog.csv – nochmal genauso drucken: "
                "passermark-cli reprint <datei.json>"
            )
        )
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(lbl.textInteractionFlags() | Qt.TextInteractionFlag.TextSelectableByMouse)
        lbl.setStyleSheet(f"color: {theme.MUTED};")
        f5.addRow(lbl)
        v.addWidget(g5)

    def _build_error_log_group(self, v):
        """Group "Fehlerprotokolle": logging of errors and stutters, and the way to the log folder."""
        from .. import crashlog

        g6 = QGroupBox(tr("Fehlerprotokolle"))
        f6 = QFormLayout(g6)
        self.chk_errlog = QCheckBox(tr("Fehler und Ruckler protokollieren und melden"))
        self.chk_errlog.setChecked(bool(self.settings.get(crashlog.SETTING, True)))
        self.chk_errlog.setToolTip(
            tr(
                "Aus: keine Fehlerprotokolle, kein Fenster bei unerwarteten Fehlern oder nach "
                "einem Absturz, keine Ruckler-Liste. Gilt ab dem nächsten Start."
            )
        )
        f6.addRow(self.chk_errlog)
        lbl = QLabel(tr("Ordner: {0}").format(crashlog.log_dir()))
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(lbl.textInteractionFlags() | Qt.TextInteractionFlag.TextSelectableByMouse)
        lbl.setStyleSheet(f"color: {theme.MUTED};")
        f6.addRow(lbl)
        v.addWidget(g6)

    def _build_window_group(self, v):
        """Group "Fenster"."""
        g4 = QGroupBox(tr("Fenster"))
        f4 = QFormLayout(g4)
        self.chk_tabs = QCheckBox(tr("Im Programm Geöffnetes als Reiter im selben Fenster"))
        self.chk_tabs.setChecked(bool(self.settings.get("open_in_tabs", True)))
        self.chk_tabs.setToolTip(
            tr(
                "Öffnen-Knopf, Hineinziehen und Ergebnisse (CutContour, CMYK …) kommen als Reiter. "
                "Programmstart und Doppelklick im Dateimanager öffnen immer ein eigenes Fenster."
            )
        )
        f4.addRow(self.chk_tabs)
        from . import titlebar

        self.chk_titlebar = QCheckBox(tr("Eigene Titelleiste (Menü und Fensterknöpfe in einer Zeile)"))
        self.chk_titlebar.setChecked(titlebar.wanted())
        self.chk_titlebar.setToolTip(
            tr(
                "Aus: normaler Fensterrahmen des Systems und eigene Menüzeile – falls das Fenster auf diesem "
                "Desktop nicht richtig zu verschieben oder zu vergrößern ist. Gilt für neue Fenster."
            )
        )
        f4.addRow(self.chk_titlebar)
        v.addWidget(g4)

    def _ok(self):
        new = self.cmb.currentData()
        old = self.settings.get("language", "auto")
        self.settings["language"] = new
        if self.cmb_wmode is not None:
            self.settings["win_print_mode"] = self.cmb_wmode.currentData()
            self.settings["win_raster_dpi"] = int(self.cmb_wdpi.currentData() or 0)
        self.settings["preflight_on_open"] = self.chk_pf.isChecked()
        self.settings["open_in_tabs"] = self.chk_tabs.isChecked()
        from . import titlebar

        self.settings[titlebar.SETTING] = self.chk_titlebar.isChecked()
        if self.chk_plog.isEnabled():
            self.settings["print_log"] = self.chk_plog.isChecked()
        from .. import crashlog

        self.settings[crashlog.SETTING] = self.chk_errlog.isChecked()
        try:
            l10n.save_settings(self.settings)
        except OSError as e:
            QMessageBox.critical(self, tr("Einstellungen"), tr("Speichern nicht möglich:\n{0}").format(e))
            return
        self.accept()
        if (
            new != old
            and QMessageBox.question(
                self.parent(), tr("Neustart"), tr("Passermark jetzt neu starten, damit die Sprache wirksam wird?")
            )
            == QMessageBox.StandardButton.Yes
        ):
            restart(self.parent())


def restart(window):
    """Close all windows (with a save prompt), release the single instance, restart."""
    ctl = getattr(window, "ctl", None)
    for w in list(getattr(ctl, "windows", [])):
        if not w.close():
            return  # the user cancelled while saving
    if ctl is not None and ctl.server is not None:
        ctl.server.close()
    if getattr(sys, "frozen", False):
        QProcess.startDetached(sys.executable, [])
    else:
        QProcess.startDetached(sys.executable, ["-m", "pdfdruck"])
    QApplication.instance().quit()
