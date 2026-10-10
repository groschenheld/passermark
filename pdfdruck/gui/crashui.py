# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Error log in the interface: message on unexpected errors, notice after a crash."""
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
    """Unexpected Python error: the program keeps running, message with the path to the log."""
    if _showing["on"]:                                   # do not stack several messages on top of each other
        return
    _showing["on"] = True
    try:
        box = QMessageBox(QMessageBox.Icon.Warning, tr("Unerwarteter Fehler"),
                          tr("Es ist ein Fehler aufgetreten – Passermark läuft weiter.") + "\n\n" + summary + "\n\n"
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
    """At startup: report earlier hard crashes (once)."""
    paths = crashlog.pending_crashes()
    if not paths:
        return
    crashlog.mark_seen(paths)
    box = QMessageBox(QMessageBox.Icon.Information, tr("Passermark wurde unerwartet beendet"),
                      tr("Passermark wurde beim letzten Mal unerwartet beendet. Das Protokoll hilft beim Beheben – "
                         "bitte mitschicken:") + "\n\n" + paths[-1], parent=QApplication.activeWindow())
    btn = box.addButton(tr("Protokollordner öffnen"), QMessageBox.ButtonRole.ActionRole)
    box.addButton(QMessageBox.StandardButton.Ok)
    box.exec()
    if box.clickedButton() is btn:
        open_log_dir()
