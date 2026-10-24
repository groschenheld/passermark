# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Farbe → Papiere und Messungen: own materials without admin rights (saved right away), standard profiles,
    short colour management help."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QLabel,
                               QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QTextBrowser, QVBoxLayout)

from .. import colorlab, usercolor
from ..l10n import tr
from . import theme


class MaterialsDialog(QDialog):
    changed = Signal()

    def __init__(self, parent, cfg: dict, select: str = "", measure: bool = False):
        super().__init__(parent)
        self.setWindowTitle(tr("Papiere und Messungen – Passermark"))
        self.cfg = cfg
        v = QVBoxLayout(self)
        n_admin = len((cfg or {}).get("materials", []))
        head = QLabel(tr("Eigene Papiere – nur für dich, ohne Adminrechte, sofort gespeichert. Sie erscheinen im "
                         "Softproof, in der Farbprüfung, bei der CMYK-Umwandlung und im Druckdialog.")
                      + ("  " + tr("Dazu {0} Papier(e) der Verwaltung (nur lesen).").format(n_admin) if n_admin else ""))
        head.setWordWrap(True)
        head.setStyleSheet(f"color: {theme.MUTED};")
        v.addWidget(head)
        row = QHBoxLayout()
        b = QPushButton(tr("Standardprofile holen …"))
        b.setToolTip(tr("Profile der Standard-Druckbedingungen (PSO Coated v3, PSO Uncoated v3, FOGRA39 …) "
                        "kostenlos aus der ICC Profile Registry laden"))
        b.clicked.connect(self._standards)
        row.addWidget(b)
        b = QPushButton(tr("Farbmanagement kurz erklärt"))
        b.clicked.connect(lambda: show_help(self))
        row.addWidget(b)
        row.addStretch()
        v.addLayout(row)
        from .materialtab import MaterialTab, UserHost
        self.host = UserHost(self, cfg)
        self.tab = MaterialTab(host=self.host)
        v.addWidget(self.tab, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.resize(980, 640)
        if select:
            self.tab._refresh(select)
        if measure:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self.tab._measure if self.tab.cur() is not None else self.tab._new_and_measure)

    def _standards(self):
        dlg = StandardProfilesDialog(self)
        dlg.exec()
        if dlg.fetched:
            self.tab.invalidate()
            self.tab._show()

    def done(self, r):
        self.host.changed()
        if self.host.error:
            QMessageBox.warning(self, tr("Papiere"), tr("Konnte die eigenen Papiere nicht speichern: {0}").format(
                self.host.error))
        self.changed.emit()
        super().done(r)


class StandardProfilesDialog(QDialog):
    """Standard-Druckbedingungen aus der ICC Profile Registry holen (in den eigenen Profilordner)."""

    def __init__(self, parent, surface: str = ""):
        super().__init__(parent)
        self.setWindowTitle(tr("Standardprofile holen"))
        self.fetched: list = []
        v = QVBoxLayout(self)
        t = QLabel(tr("Profile der üblichen Druckbedingungen. Welche die Druckerei will, steht meist in ihren "
                      "Datenblättern („Druckbedingung“, „Output Intent“, FOGRA-Nummer). Ohne Angabe: gestrichenes Papier "
                      "PSO Coated v3, ungestrichenes PSO Uncoated v3."))
        t.setWordWrap(True)
        v.addWidget(t)
        self.tbl = QTableWidget(len(usercolor.STANDARD_PROFILES), 5)
        self.tbl.setHorizontalHeaderLabels([tr("Profil"), tr("Kennung"), tr("Wofür"), tr("Herausgeber"), tr("Status")])
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        hh = self.tbl.horizontalHeader()
        for c in (0, 1, 3, 4):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        want = {p["key"] for p in usercolor.standards_for_surface(surface)} if surface else set()
        self.checks = []
        for i, p in enumerate(usercolor.STANDARD_PROFILES):
            chk = QCheckBox(p["name"])
            have = usercolor.standard_installed(p)
            chk.setChecked(not have and (p["key"] in want or (not want and p["condition"] in ("FOGRA51", "FOGRA52"))))
            chk.setProperty("key", p["key"])
            self.checks.append(chk)
            self.tbl.setCellWidget(i, 0, chk)
            self.tbl.setItem(i, 1, QTableWidgetItem(p["condition"]))
            self.tbl.setItem(i, 2, QTableWidgetItem(tr(p["use"])))
            self.tbl.setItem(i, 3, QTableWidgetItem(p["by"]))
            st = QTableWidgetItem(tr("installiert") if have else "–")
            if have:
                st.setToolTip(have)
            self.tbl.setItem(i, 4, st)
        v.addWidget(self.tbl, 1)
        lic = QLabel(tr("Die Profile kommen direkt von registry.color.org (International Color Consortium) und liegen "
                        "danach in {0}. Benutzen und in PDFs einbetten ist frei; die Profildateien selbst gibt "
                        "Passermark nicht weiter.").format(usercolor.icc_dir()))
        lic.setWordWrap(True)
        lic.setStyleSheet(f"color: {theme.MUTED};")
        lic.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        v.addWidget(lic)
        self.lbl = QLabel()
        self.lbl.setWordWrap(True)
        self.lbl.setStyleSheet(f"color: {theme.ACCENT};")
        v.addWidget(self.lbl)
        bb = QDialogButtonBox()
        self.btn = bb.addButton(tr("Holen"), QDialogButtonBox.ButtonRole.ActionRole)
        self.btn.clicked.connect(self._fetch)
        bb.addButton(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.resize(860, 420)

    def _fetch(self):
        keys = [c.property("key") for c in self.checks if c.isChecked()]
        if not keys:
            self.lbl.setText(tr("Bitte mindestens ein Profil anhaken."))
            return
        errors = []
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            for i, p in enumerate(usercolor.STANDARD_PROFILES):
                if p["key"] not in keys:
                    continue
                self.lbl.setText(tr("Hole {0} …").format(p["name"]))
                QApplication.processEvents()
                try:
                    path = usercolor.download_standard(p["key"])
                    self.fetched.append(path)
                    self.tbl.setItem(i, 4, QTableWidgetItem(tr("installiert")))
                    self.checks[i].setChecked(False)
                except Exception as e:                                # noqa: BLE001 – Netz, Proxy, Antwort
                    errors.append(f"{p['name']}: {e}")
        finally:
            QApplication.restoreOverrideCursor()
        colorlab._WHITE_CACHE.clear()
        if errors:
            self.lbl.setText(tr("Nicht geholt:") + "\n" + "\n".join(errors) + "\n" + tr(
                "Ohne Internet: die .icc-Datei von registry.color.org auf einem anderen Rechner laden und in den Ordner "
                "oben legen."))
        else:
            self.lbl.setText(tr("Fertig – {0} Profil(e) installiert.").format(len(self.fetched)))


HELP = [
    ("Druckbedingung (Profil)",
     "Beschreibt, wie ein Drucker auf einem Papier Farbe wiedergibt – als ICC-Profil. Für die Druckerei ist es eine "
     "Standard-Druckbedingung (z. B. PSO Coated v3 = FOGRA51 für gestrichenes Papier), für den eigenen Drucker das "
     "Profil des Druckers mit diesem Papier."),
    ("RGB und CMYK",
     "Bildschirm, Kamera und Office arbeiten in RGB, gedruckt wird mit Cyan, Magenta, Gelb und Schwarz (CMYK). Beim "
     "Umwandeln rechnet das Profil, welche CMYK-Werte auf diesem Papier am nächsten an die Bildschirmfarbe kommen. "
     "Leuchtende RGB-Farben (Grün, Blau, Orange) gibt es im Druck nicht – sie werden flauer."),
    ("Output Intent",
     "Ein Vermerk im PDF: „diese Datei ist für Druckbedingung X gemacht“ – mit dem Profil eingebettet. Die Druckerei "
     "sieht daran, wie sie die Daten verarbeiten soll. PDF/X verlangt ihn. „Für Druckerei ausgeben“ bettet ihn "
     "immer ein."),
    ("Papierweiß und ΔE",
     "Die Farbe des unbedruckten Papiers als Lab-Wert. ΔE (Delta E 2000) ist der Farbabstand: unter 2 kaum sichtbar, "
     "2–4 bei genauem Hinsehen, über 4 deutlich. Passt das gemessene Papierweiß nicht zum Profil, wählt man ein "
     "anderes Profil oder misst ein eigenes."),
    ("Render-Intent",
     "Was mit Farben passiert, die das Papier nicht drucken kann. „Relativ farbmetrisch“ lässt druckbare Farben "
     "genau und schneidet den Rest ab – passt fast immer. „Wahrnehmungsorientiert“ staucht alles etwas zusammen, "
     "gut für Fotos mit sehr bunten Farben. Tiefenkompensierung (BPC) hält dunkle Bildstellen durchgezeichnet."),
    ("Farbauftrag",
     "Summe aus C+M+Y+K an einer Stelle, z. B. 300 %. Zu viel Farbe trocknet schlecht und schlägt durch. Jede "
     "Druckbedingung hat einen Richtwert (PSO Coated v3: 300 %). Neu separieren mit dem Zielprofil begrenzt ihn."),
    ("Ablauf für die Druckerei",
     "1. Farbe → Farbprüfung: Druckbedingung wählen, Befunde lesen.  2. Softproof ansehen (Strg+Y).  3. Farbe → Für "
     "Druckerei ausgeben: umwandeln, Output Intent einbetten, auf Wunsch Paket mit Profil und Bericht."),
]


def show_help(parent):
    dlg = QDialog(parent)
    dlg.setWindowTitle(tr("Farbmanagement kurz erklärt"))
    v = QVBoxLayout(dlg)
    tb = QTextBrowser()
    tb.setOpenExternalLinks(True)
    tb.setHtml("".join(f"<h3>{tr(h)}</h3><p>{tr(t)}</p>" for h, t in HELP))
    v.addWidget(tb)
    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    bb.rejected.connect(dlg.reject)
    v.addWidget(bb)
    dlg.resize(620, 560)
    dlg.exec()
