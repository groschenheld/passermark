# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Jobs in the interface: shown in the status bar with progress and cancel.

The computation runs as a separate process (jobproc.JobProcess). A reader thread only forwards its text
messages as Qt signals – it never touches pdfium.
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
