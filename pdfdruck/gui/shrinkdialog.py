# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Datei verkleinern: Aufschlüsselung der Dateigröße und jede Maßnahme einzeln an/aus."""
from __future__ import annotations

import traceback

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
                               QGroupBox, QLabel, QSpinBox, QVBoxLayout)

from .. import shrink
from ..l10n import tr
from . import theme

MB = shrink.MB


class _Analyze(QThread):
    done = Signal(object, str)

    def __init__(self, data: bytes):
        super().__init__()
        self.data = data

    def run(self):
        try:
            self.done.emit(shrink.analyze(self.data), "")
        except Exception as e:
            self.done.emit(None, f"{e}\n{traceback.format_exc()}")


def _mb(b: int) -> str:
    return f"{b / MB:.1f} MB"


class ShrinkDialog(QDialog):
    """rep: fertige Analyse (aus der Prüfung) oder None – dann wird sie hier im Hintergrund erstellt."""

    def __init__(self, parent, rep: shrink.SizeReport | None = None, data: bytes | None = None):
        super().__init__(parent)
        self.setWindowTitle(tr("Datei verkleinern"))
        self.rep = rep
        self._worker = None
        v = QVBoxLayout(self)
        self.lbl = QLabel(tr("Analysiere …"))
        self.lbl.setWordWrap(True)
        v.addWidget(self.lbl)

        g = QGroupBox(tr("Verlustfrei – das Druckbild bleibt gleich"))
        gl = QVBoxLayout(g)
        self.cb = {}

        def add(layout, key, text, tip, on):
            c = QCheckBox(text)
            c.setToolTip(tip)
            c.setChecked(on)
            layout.addWidget(c)
            self.cb[key] = c
            return c
        add(gl, "rewrite", tr("Neu schreiben (alte Speicherstände weg, Struktur kompakt, ZIP stärker)"),
            tr("Inkrementell angehängte Speicherstände fallen weg, Objekte werden in komprimierten Objekt-Streams "
               "abgelegt, ZIP-Daten neu gepackt."), True)
        add(gl, "unreferenced", tr("Nicht mehr verwendete Ressourcen entfernen"),
            tr("Schriften, Bilder usw., die keine Seite mehr verwendet."), True)
        add(gl, "dedupe", tr("Doppelt gespeicherte Bilder, Schriften, Profile zusammenlegen"),
            tr("Gleiche Daten werden nur einmal gespeichert und mehrfach verwendet."), True)
        add(gl, "private", tr("Illustrator-/Photoshop-Bearbeitungsdaten entfernen"),
            tr("PieceInfo: damit lässt sich die Datei in Illustrator wieder voll bearbeiten – für den Druck nicht "
               "nötig. Das Original behält sie."), True)
        add(gl, "thumbs", tr("Eingebettete Seitenvorschaubilder entfernen"),
            tr("Alte Vorschaubilder; Programme erzeugen sie ohnehin selbst."), True)
        add(gl, "pack", tr("Bilder verlustfrei packen (ZIP mit Prädiktor)"),
            tr("Unkomprimierte oder schwach gepackte Bilder werden verlustfrei neu gepackt – nur übernommen, wenn "
               "es kleiner wird. Bei ZIP um ein JPEG wird die ZIP-Schicht entfernt, wenn es kleiner wird."), True)
        v.addWidget(g)

        g = QGroupBox(tr("Ändert die Datei, im Druck nicht sichtbar"))
        gl = QVBoxLayout(g)
        add(gl, "bits16", tr("16-Bit-Bilder auf 8 Bit"),
            tr("Druckmaschinen und RIPs arbeiten mit 8 Bit je Kanal – halbiert die Bilddaten."), False)
        add(gl, "attachments", tr("Eingebettete Dateien (Anhänge) entfernen"),
            tr("Anhänge im PDF, z. B. Originaldateien – werden nicht gedruckt."), False)
        add(gl, "hidden", tr("Inhalte ausgeblendeter Ebenen entfernen"),
            tr("Wie „Sichtbaren Zustand festschreiben“: was ausgeblendet ist, fliegt raus."), False)
        v.addWidget(g)

        g = QGroupBox(tr("Verlustbehaftet (optional)"))
        gl = QVBoxLayout(g)
        add(gl, "photos_jpeg", tr("Fotos, die als ZIP gespeichert sind, als JPEG speichern"),
            tr("Nur echte Fotos (viele Farbtöne) – Logos, Grafiken, Text-Scans und Masken bleiben verlustfrei. "
               "Wird nur übernommen, wenn es deutlich kleiner wird."), False)
        self.lbl_ph = QLabel()
        self.lbl_ph.setWordWrap(True)
        self.lbl_ph.setStyleSheet(f"color: {theme.MUTED};")
        gl.addWidget(self.lbl_ph)
        add(gl, "downsample", tr("Bilder mit zu hoher Auflösung herunterrechnen"),
            tr("Gemessen an der größten Platzierung im Dokument. Fotos (JPEG) werden neu als JPEG gespeichert, "
               "alles andere verlustfrei mit ZIP."), False)
        form = QFormLayout()
        self.cmb_dpi = QComboBox()
        for d, t in ((300, tr("300 dpi – Offset, Nahbetrachtung")), (240, tr("240 dpi")),
                     (150, tr("150 dpi – Plakat, Großformat")), (100, tr("100 dpi – Fernwirkung, Banner"))):
            self.cmb_dpi.addItem(t, d)
        self.spin_thr = QDoubleSpinBox()
        self.spin_thr.setRange(1.0, 4.0)
        self.spin_thr.setSingleStep(0.1)
        self.spin_thr.setValue(1.5)
        self.spin_thr.setPrefix("× ")
        self.spin_thr.setToolTip(tr("Nur Bilder über Ziel × Schwelle werden angefasst (1,5 bei 300 dpi = ab 450 dpi)."))
        self.spin_q = QSpinBox()
        self.spin_q.setRange(60, 100)
        self.spin_q.setValue(92)
        self.spin_q.setToolTip(tr("Für neu gespeicherte JPEG-Bilder. 92 ist im Druck nicht vom Original zu "
                                  "unterscheiden."))
        form.addRow(tr("Ziel:"), self.cmb_dpi)
        form.addRow(tr("Schwelle:"), self.spin_thr)
        form.addRow(tr("JPEG-Qualität:"), self.spin_q)
        gl.addLayout(form)
        self.lbl_ds = QLabel()
        self.lbl_ds.setWordWrap(True)
        self.lbl_ds.setStyleSheet(f"color: {theme.MUTED};")
        gl.addWidget(self.lbl_ds)
        v.addWidget(g)
        self.cb["downsample"].toggled.connect(self._update)
        self.cb["photos_jpeg"].toggled.connect(self._update)
        self.cmb_dpi.currentIndexChanged.connect(self._update)
        self.spin_thr.valueChanged.connect(self._update)

        note = QLabel(tr("Ergebnis öffnet im neuen Fenster, das Original bleibt unverändert. Macht eine Maßnahme "
                         "Probleme, einfach abwählen und neu verkleinern."))
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {theme.MUTED};")
        v.addWidget(note)
        bb = QDialogButtonBox()
        self.b_ok = bb.addButton(tr("Jetzt verkleinern"), QDialogButtonBox.ButtonRole.AcceptRole)
        bb.addButton(tr("Abbrechen"), QDialogButtonBox.ButtonRole.RejectRole)
        self.b_ok.setDefault(True)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        if rep is not None:
            self._show(rep, "")
        elif data is not None:
            self._worker = _Analyze(data)
            self._worker.done.connect(self._show)
            self._worker.start()
        self._update()

    # ------------------------------------------------------------------ #
    def _show(self, rep, err):
        if err or rep is None:
            self.lbl.setText(tr("Analyse nicht möglich: {0}").format((err or "").splitlines()[0] if err else "?"))
            return
        self.rep = rep
        self.lbl.setText("\n".join(shrink.summary_lines(rep)))
        hints = {"private": rep.private_bytes, "thumbs": rep.thumb_bytes, "attachments": rep.attachment_bytes,
                 "dedupe": rep.duplicate_bytes}
        for k, b in hints.items():
            c = self.cb[k]
            base = c.text().split("  (")[0]
            c.setText(base + (f"  ({_mb(b)})" if b >= 64 * 1024 else ""))
        if rep.revisions:
            c = self.cb["rewrite"]
            c.setText(c.text().split("  (")[0] + "  (" + tr("{0} Speicherstände").format(rep.revisions) + ")")
        n16 = sum(1 for i in rep.images if i.bpc == 16)
        self.cb["bits16"].setEnabled(n16 > 0)
        self.cb["attachments"].setEnabled(rep.attachment_bytes > 0)
        self.cb["hidden"].setEnabled(rep.has_hidden_layers)
        self._update()

    def _update(self):
        on = self.cb["downsample"].isChecked()
        for w in (self.cmb_dpi, self.spin_thr):
            w.setEnabled(on)
        self.spin_q.setEnabled(on or self.cb["photos_jpeg"].isChecked())
        if self.rep is None:
            self.lbl_ds.setText("")
            self.lbl_ph.setText("")
            return
        zp = shrink.zip_photos(self.rep)
        self.lbl_ph.setText(tr("Vermutlich {0} Foto(s) als ZIP gespeichert, zusammen {1}.").format(
            len(zp), _mb(sum(i.raw for i in zp))) if zp else tr("Keine Fotos als ZIP gefunden."))
        c = shrink.candidates(self.rep, self.cmb_dpi.currentData(), self.spin_thr.value())
        if c:
            self.lbl_ds.setText(tr("Betrifft {0} Bild(er) mit zusammen {1} (höchste Auflösung {2:.0f} dpi).").format(
                len(c), _mb(sum(i.raw for i in c)), max(i.dpi for i in c)))
        else:
            self.lbl_ds.setText(tr("Kein Bild liegt über dieser Grenze."))

    def options(self) -> shrink.ShrinkOptions:
        o = shrink.ShrinkOptions(target_dpi=int(self.cmb_dpi.currentData()), threshold=float(self.spin_thr.value()),
                                 jpeg_quality=int(self.spin_q.value()))
        for k, c in self.cb.items():
            setattr(o, k, c.isChecked() and c.isEnabled())
        return o

    def done(self, r):
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(30000)
        super().done(r)
