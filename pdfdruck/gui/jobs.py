# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Aufträge in der Oberfläche: Anzeige in der Statusleiste mit Fortschritt und Abbrechen.

Die Berechnung läuft als eigener Prozess (jobproc.JobProcess). Ein Lese-Thread reicht nur dessen Textmeldungen
als Qt-Signale weiter – er fasst kein pdfium an.
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QToolButton, QWidget

from ..l10n import tr


class JobReader(QThread):
    progress = Signal(int, int, str)
    finished_job = Signal(dict)

    def __init__(self, job):
        super().__init__()
        self.job = job

    def run(self):
        try:
            for ev in self.job.events():
                if ev.get("event") == "progress":
                    self.progress.emit(int(ev.get("done", 0)), int(ev.get("total", 0)), str(ev.get("text", "")))
            res = self.job.wait()
        except Exception as e:                       # noqa: BLE001 – jede Ursache melden
            res = {"event": "error", "message": str(e)}
        self.finished_job.emit(res)


class JobWidget(QWidget):
    """Ein laufender Auftrag in der Statusleiste: Titel, Fortschritt, Abbrechen."""

    def __init__(self, title: str, on_cancel):
        super().__init__()
        h = QHBoxLayout(self)
        h.setContentsMargins(6, 0, 6, 0)
        h.setSpacing(6)
        self.lbl = QLabel(title)
        self.bar = QProgressBar()
        self.bar.setFixedWidth(140)
        self.bar.setRange(0, 0)                      # unbestimmt, bis die erste Meldung kommt
        self.bar.setTextVisible(True)
        self.btn = QToolButton()
        self.btn.setText("✕")
        self.btn.setToolTip(tr("Abbrechen"))
        self.btn.clicked.connect(on_cancel)
        h.addWidget(self.lbl)
        h.addWidget(self.bar)
        h.addWidget(self.btn)
        self.title = title

    def set_progress(self, done: int, total: int, text: str):
        if total > 0:
            self.bar.setRange(0, total)
            self.bar.setValue(done)
        self.lbl.setText(f"{self.title} – {text}" if text else self.title)

    def set_cancelling(self):
        self.btn.setEnabled(False)
        self.lbl.setText(f"{self.title} – {tr('wird abgebrochen …')}")
