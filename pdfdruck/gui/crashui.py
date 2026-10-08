# SPDX-License-Identifier: GPL-3.0-or-later
# pdfToolkit – Copyright (C) 2026 Hias
"""Fehlerprotokoll in der Oberfläche: Meldung bei unerwartetem Fehler, Hinweis nach einem Absturz."""
from __future__ import annotations

import os

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QMessageBox

from .. import crashlog
from ..l10n import tr

_showing = {"on": False}


def open_log_dir():
    d = crashlog.log_dir()
    os.makedirs(d, exist_ok=True)
    QDesktopServices.openUrl(QUrl.fromLocalFile(d))


def show_error(summary: str, details: str):
    """Unerwarteter Python-Fehler: Programm läuft weiter, Meldung mit Pfad zum Protokoll."""
    if _showing["on"]:                                   # nicht mehrere Meldungen übereinander
        return
    _showing["on"] = True
    try:
        box = QMessageBox(QMessageBox.Icon.Warning, tr("Unerwarteter Fehler"),
                          tr("Es ist ein Fehler aufgetreten – pdfToolkit läuft weiter.") + "\n\n" + summary + "\n\n"
                          + tr("Protokoll zum Mitschicken: {0}").format(crashlog.current_path() or "–"),
                          parent=QApplication.activeWindow())
        box.setDetailedText(details)
        btn = box.addButton(tr("Protokollordner öffnen"), QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Ok)
        box.exec()
        if box.clickedButton() is btn:
            open_log_dir()
    finally:
        _showing["on"] = False


def notify_previous_crashes():
    """Beim Start: frühere harte Abstürze melden (einmal)."""
    paths = crashlog.pending_crashes()
    if not paths:
        return
    crashlog.mark_seen(paths)
    box = QMessageBox(QMessageBox.Icon.Information, tr("pdfToolkit wurde unerwartet beendet"),
                      tr("pdfToolkit wurde beim letzten Mal unerwartet beendet. Das Protokoll hilft beim Beheben – "
                         "bitte mitschicken:") + "\n\n" + paths[-1], parent=QApplication.activeWindow())
    btn = box.addButton(tr("Protokollordner öffnen"), QMessageBox.ButtonRole.ActionRole)
    box.addButton(QMessageBox.StandardButton.Ok)
    box.exec()
    if box.clickedButton() is btn:
        open_log_dir()
