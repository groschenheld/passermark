# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Plan & Poster → Plandruck … and Rollen …

Plan printing window in three parts: the plans (add with + or drag in), the run length per roll (one set and all
copies) and the settings (colour, material, print area, rotation, scale, bleed, marks, order). The work is done by
planprint (same as passermark-cli plan / the workflow step "plan"); the rolls come from rolls (device or by hand).
"""
from __future__ import annotations

import dataclasses
import os

from PySide6.QtCore import QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QIcon, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QColorDialog, QComboBox, QDialog,
                               QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QListView, QListWidget, QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit, QPushButton,
                               QScrollArea, QSizePolicy, QSpinBox, QSplitter,
                               QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import planprint as pp
from .. import printers
from .. import rolls as rl
from ..l10n import tr
from . import theme
from .icons import icon

SETTINGS_KEY = "plan"                 # Benutzereinstellung: zuletzt verwendete Plan-Einstellungen
PRINTER_KEY = "plan_printer"

FRAME_TEXT = {"auto": "Automatisch (zwei Außenlinien, sonst Inhalt + Rand)", "frame": "Auf die äußere Linie",
              "margin": "Inhalt + Rand", "none": "Ganze Seite"}
ROTATE_TEXT = {"auto": "Kürzeste Länge auf der Rolle (drehen erlaubt)", "keep": "Wie angeliefert",
               "short": "Kurze Seite quer zur Rolle", "long": "Lange Seite quer zur Rolle"}
ORDER_TEXT = {"list": "Reihenfolge der Liste", "roll": "Nach Rollenbreite (schmal zuerst)"}
COLOR_TEXT = {"": "Wie im Treiber", "color": "Farbe", "gray": "Graustufen"}
BLEED_TEXT = {"mirror": "Gespiegelt", "blank": "Leerraum", "color": "Einzelfarbe"}
ORIGIN_TEXT = {"ipp": "vom Gerät (IPP)", "snmp": "vom Gerät (SNMP)", "manual": "von Hand eingetragen",
               "settings": "aus den Einstellungen", "roland": "vom Gerät (Roland)"}
OVER_TEXT = {"none": "Auslassen (Warnung)", "crop": "Abschneiden (was nicht passt)",
             "tile": "In Bahnen teilen (mit Überlappung)"}
COPIES_TEXT = {"sheets": "Ein Auftrag, je Exemplar ein Blatt", "jobs": "Je Exemplar ein eigener Auftrag",
               "count": "Kopienzahl (Gerät entscheidet übers Schneiden)"}
SCALE_TEXT = {"pct": "Prozent", "short": "Kurze Kante auf", "long": "Lange Kante auf"}
ALIGN_TEXT = {"center": "Mittig", "left": "Am Rand (links)", "right": "Am Rand (rechts)"}
CAT_TEXT = {"plan": "Plandruck", "quality": "Qualitätsdruck"}
KIND_SHORT = {"frame": "Außenlinie", "margin": "Rand", "page": "Seite", "empty": "leer"}


PREVIEW_PX = 150                      # Vorschaubild: längere Kante in Pixel
PREVIEW_MAX = 24                      # höchstens so viele Druckseiten in der Vorschau
_RUNNING: set = set()                 # laufende Geräteabfragen (überleben das Schließen des Fensters)


def fill_combo(combo: QComboBox, choices, current):
    """(Wert, Text) – ohne Treiberwert-Tooltips (eigene Auswahl, keine Treiberoption)."""
    combo.blockSignals(True)
    combo.clear()
    for val, text in choices:
        combo.addItem(text, val)
    i = combo.findData(current)
    combo.setCurrentIndex(i if i >= 0 else 0)
    combo.blockSignals(False)


class MsgBox(QPlainTextEdit):
    """Meldung zum Lesen, Markieren und Kopieren: wächst bis lines Zeilen, dann scrollbar – verschiebt nichts."""

    def __init__(self, lines: int = 3, color: str = "", parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse
                                     | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("QPlainTextEdit { background: transparent; %s }" % (f"color: {color};" if color else ""))
        self._lines = max(1, lines)
        self.document().contentsChanged.connect(self._fit)
        self._fit()

    def setText(self, text: str):
        self.setPlainText(text or "")
        self.setVisible(bool(text))
        QTimer.singleShot(0, self._fit)              # Zeilenzahl steht erst nach dem Umbruch fest

    def text(self) -> str:
        return self.toPlainText()

    def _fit(self):
        fm = self.fontMetrics()
        rows = max(1, min(self._lines, int(self.document().size().height()) or 1))
        m = self.contentsMargins()
        self.setFixedHeight(rows * fm.lineSpacing() + 2 * int(self.document().documentMargin()) + m.top() + m.bottom())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()


def make_responsive(w: QWidget):
    """Lange Einträge (Rollen, Materialien, Meldungen) dürfen das Fenster nicht breiter machen bzw. die
        Einstellungen ineinanderschieben: Auswahllisten kürzen, Formulare umbrechen."""
    for c in w.findChildren(QComboBox):
        c.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        c.setMinimumContentsLength(8)
        c.view().setTextElideMode(Qt.TextElideMode.ElideNone)
        c.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    for f in w.findChildren(QFormLayout):
        f.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        f.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    for lb in w.findChildren(QLabel):
        if lb.wordWrap():
            lb.setMinimumWidth(0)
            lb.setSizePolicy(QSizePolicy.Policy.Ignored, lb.sizePolicy().verticalPolicy())


def _start_query(host: str, receiver, tag: str = "", fn=None):
    """Gerät im Hintergrund abfragen. receiver = gebundene Methode eines Fensters (wird dann im Haupt-Thread
        aufgerufen und automatisch getrennt, wenn das Fenster schon zu ist): receiver(RollState, tag)."""
    for old in [t for t in _RUNNING if t.isFinished()]:
        _RUNNING.discard(old)
    q = _RollQuery(host, tag, fn)
    _RUNNING.add(q)
    q.done.connect(receiver)
    q.start()
    return q


def _keys(kind: str) -> tuple:
    return (SETTINGS_KEY, PRINTER_KEY) if kind != "poster" else ("poster", "poster_printer")


def load_settings(kind: str = "plan") -> pp.PlanSettings:
    from .. import core, l10n
    d = l10n.load_settings().get(_keys(kind)[0]) or {}
    base = pp.defaults_for(kind)
    try:
        merged = dict(base, **(d if isinstance(d, dict) else {}))
        merged["kind"] = kind
        return core.settings_from_dict(pp.PlanSettings, merged)
    except (TypeError, ValueError):
        return pp.PlanSettings(**base)


def save_settings(s: pp.PlanSettings, printer: str) -> None:
    from .. import l10n
    st = l10n.load_settings()
    d = pp.compact(dataclasses.replace(s, printer="", rolls=[], dry_run=False, title="", options={}))
    d.pop("printer", None)
    skey, pkey = _keys(s.kind)
    st[skey] = d
    if printer:
        st[pkey] = printer
    try:
        l10n.save_settings(st)
    except OSError:
        pass


class _RollQuery(QThread):
    """Gerät abfragen (nur Netzwerk – kein pdfium) ohne die Oberfläche anzuhalten."""
    done = Signal(object, str)

    def __init__(self, host: str, tag: str = "", fn=None):
        super().__init__()
        self.host, self.tag, self.fn = host, tag, fn or (lambda h: rl.query(h, force=True))

    def run(self):
        try:
            st = self.fn(self.host)
        except Exception as e:                                  # noqa: BLE001
            st = rl.RollState([], "none", str(e), self.host)
        self.done.emit(st, self.tag)


# --------------------------------------------------------------------------- #
# Rollen von Hand
# --------------------------------------------------------------------------- #
class RollsDialog(QDialog):
    """Rollen des Druckers: was das Gerät meldet, und die von Hand eingetragenen (je Benutzer, ohne Adminrechte)."""

    def __init__(self, parent, session, printer: str):
        super().__init__(parent)
        self.setWindowTitle(tr("Rollen – {0}").format(printer))
        self.session, self.printer = session, printer
        self.caps = None
        try:
            self.caps = session.caps_for(printer)
        except Exception:
            self.caps = None
        self._q = None
        v = QVBoxLayout(self)
        t = QLabel(tr("Passermark liest die geladenen Rollen direkt vom Gerät (IPP, sonst SNMP). Meldet das Gerät "
                      "nichts, gelten die hier eingetragenen Rollen. Die Zufuhr ist der Wert im Treiber."))
        t.setWordWrap(True)
        v.addWidget(t)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Geräteadresse:")))
        self.ed_host = QLineEdit(rl.host_for(session, printer))
        self.ed_host.setPlaceholderText(tr("IP-Adresse oder Name, z. B. 10.30.4.73"))
        self.ed_host.setToolTip(tr("Wird aus dem Anschluss ermittelt; geht das nicht (WSD, Druckserver), hier "
                                   "eintragen – gilt nur für dich"))
        row.addWidget(self.ed_host, 1)
        self.btn_query = QPushButton(tr("Vom Gerät lesen"))
        self.btn_query.clicked.connect(self._query)
        row.addWidget(self.btn_query)
        self.btn_probe = QPushButton(icon("check"), tr("Gerät prüfen …"))
        self.btn_probe.setToolTip(tr("Alles abfragen, was das Gerät über IPP/SNMP meldet – Bericht zum Speichern "
                                     "und Weitergeben"))
        self.btn_probe.clicked.connect(self._probe)
        row.addWidget(self.btn_probe)
        v.addLayout(row)
        self.lbl_dev = MsgBox(5)
        v.addWidget(self.lbl_dev)
        self.tbl = QTableWidget(0, 5)
        self.tbl.setHorizontalHeaderLabels([tr("Breite (mm)"), tr("Zufuhr im Treiber"), tr("g/m²"), tr("Name"),
                                            tr("Material")])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        v.addWidget(self.tbl, 1)
        row = QHBoxLayout()
        b = QPushButton(icon("insert"), tr("Rolle hinzufügen"))
        b.clicked.connect(lambda: self._add(rl.Roll(594, name=tr("Rolle {0}").format(self.tbl.rowCount() + 1))))
        row.addWidget(b)
        b = QPushButton(icon("delete"), tr("Entfernen"))
        b.clicked.connect(self._remove)
        row.addWidget(b)
        self.btn_take = QPushButton(tr("Gemeldete übernehmen"))
        self.btn_take.setToolTip(tr("Die vom Gerät gemeldeten Rollen als eigene Einträge speichern"))
        self.btn_take.setEnabled(False)
        self.btn_take.clicked.connect(self._take)
        row.addWidget(self.btn_take)
        row.addStretch(1)
        v.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.live = []
        for r in rl.manual(printer):
            self._add(r)
        make_responsive(self)
        self.resize(720, 420)
        if not self.ed_host.text():
            self.lbl_dev.setText(tr("Adresse nicht ermittelbar – bitte die IP-Adresse des Geräts eintragen."))

    def _slot_combo(self, value: str) -> QComboBox:
        c = QComboBox()
        c.addItem(tr("Gerät wählt selbst"), "")
        key = self.caps.roles.get("source") if self.caps else None
        if key and key in self.caps.options:
            for ch in self.caps.options[key].choices:
                c.addItem(ch.text if ch.text == ch.value else f"{ch.text} ({ch.value})", ch.value)
        i = c.findData(value)
        if i < 0 and value:
            c.addItem(value, value)
            i = c.count() - 1
        c.setCurrentIndex(max(0, i))
        return c

    def _add(self, r: rl.Roll):
        n = self.tbl.rowCount()
        self.tbl.insertRow(n)
        sp = QDoubleSpinBox()
        sp.setRange(10, 5000)
        sp.setDecimals(1)
        sp.setSuffix(" mm")
        sp.setValue(r.width_mm)
        self.tbl.setCellWidget(n, 0, sp)
        self.tbl.setCellWidget(n, 1, self._slot_combo(r.slot))
        w = QSpinBox()
        w.setRange(0, 999)
        w.setSpecialValueText("–")
        w.setValue(int(r.weight or 0))
        self.tbl.setCellWidget(n, 2, w)
        self.tbl.setItem(n, 3, QTableWidgetItem(r.name))
        self.tbl.setItem(n, 4, QTableWidgetItem(r.media))

    def _remove(self):
        for i in sorted({ix.row() for ix in self.tbl.selectedIndexes()}, reverse=True):
            self.tbl.removeRow(i)

    def _rolls(self) -> list:
        out = []
        for i in range(self.tbl.rowCount()):
            w = self.tbl.cellWidget(i, 0).value()
            slot = self.tbl.cellWidget(i, 1).currentData() or ""
            g = self.tbl.cellWidget(i, 2).value()
            name = (self.tbl.item(i, 3).text() if self.tbl.item(i, 3) else "").strip()
            media = (self.tbl.item(i, 4).text() if self.tbl.item(i, 4) else "").strip()
            out.append(rl.Roll(float(w), slot, name, int(g), media))
        return out

    def _save_host(self):
        host = self.ed_host.text().strip()
        auto = ""
        try:
            rl.set_user_host(self.printer, "")
            auto = rl.host_for(self.session, self.printer)
        except OSError:
            pass
        try:
            rl.set_user_host(self.printer, "" if host == auto else host)   # nur merken, was abweicht
        except OSError:
            pass
        return host

    def _query(self):
        host = self._save_host()
        if not host:
            self.lbl_dev.setText(tr("Keine Geräteadresse – oben die IP-Adresse des Geräts eintragen."))
            return
        self.btn_query.setEnabled(False)
        self.lbl_dev.setText(tr("Frage {0} ab …").format(host))
        from .. import roland
        fn = rl.query_roland if roland.is_roland(self.printer, rl.model_of(self.printer)) else None
        self._q = _start_query(host, self._queried, "", fn)

    def _probe(self):
        host = self._save_host()
        if not host:
            self.lbl_dev.setText(tr("Keine Geräteadresse – oben die IP-Adresse des Geräts eintragen."))
            return
        from .. import probe
        self.btn_probe.setEnabled(False)
        self.lbl_dev.setText(tr("Prüfe {0} … (bis zu einer Minute)").format(host))
        printer = self.printer
        self._q = _start_query(host, self._probed, "", lambda h: probe.run(h, printer))

    def _probed(self, rep, _tag=""):
        from .. import probe
        self.btn_probe.setEnabled(True)
        if not isinstance(rep, dict):                      # Fehler im Thread: RollState mit Meldung
            self.lbl_dev.setText(getattr(rep, "error", "") or tr("Prüfung fehlgeschlagen"))
            return
        ProbeDialog(self, rep).exec()
        r = rep.get("rolls") or {}
        if r.get("rolls"):
            self._queried(rl.RollState([rl.Roll.from_dict(x) for x in r["rolls"]], r.get("origin", ""), "",
                                       rep.get("host", "")))
        else:
            self.lbl_dev.setText(probe.text(rep).splitlines()[-1])

    def _queried(self, st, _tag=""):
        self.btn_query.setEnabled(True)
        self.live = list(st.rolls)
        for i, r in enumerate(self.live):
            r.slot = r.slot or (rl.slot_for(self.caps, r.device or r.name, i) if self.caps else "")
        if st.rolls:
            self.lbl_dev.setText(tr("Gerät {0} meldet {1}:").format(st.host, tr(ORIGIN_TEXT.get(st.origin, st.origin)))
                                 + "<br>" + "<br>".join(r.label() for r in st.rolls))
        else:
            self.lbl_dev.setText(tr("Gerät {0}: keine Rollen gemeldet ({1})").format(st.host, st.error or "–"))
        self.btn_take.setEnabled(bool(self.live))

    def _take(self):
        self.tbl.setRowCount(0)
        for r in self.live:
            self._add(r)

    def _save(self):
        self._save_host()
        try:
            rl.save_manual(self.printer, self._rolls())
        except OSError as e:
            QMessageBox.critical(self, tr("Rollen"), str(e))
            return
        self.accept()


# --------------------------------------------------------------------------- #
# Plandruck
# --------------------------------------------------------------------------- #
class ProbeDialog(QDialog):
    """Ergebnis von „Gerät prüfen“: Kurzfassung, vollständiger Bericht speicherbar (JSON)."""

    def __init__(self, parent, rep: dict):
        super().__init__(parent)
        from PySide6.QtWidgets import QPlainTextEdit
        from .. import probe
        self.rep = rep
        self.setWindowTitle(tr("Gerät prüfen – {0}").format(rep.get("printer") or rep.get("host")))
        v = QVBoxLayout(self)
        t = QPlainTextEdit(probe.text(rep))
        t.setReadOnly(True)
        v.addWidget(t, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        b = QPushButton(icon("save"), tr("Bericht speichern …"))
        b.clicked.connect(self._save)
        row.addWidget(b)
        b = QPushButton(tr("Schließen"))
        b.clicked.connect(self.accept)
        row.addWidget(b)
        v.addLayout(row)
        self.resize(760, 520)

    def _save(self):
        from .. import probe
        out, _ = QFileDialog.getSaveFileName(self, tr("Bericht speichern"),
                                             os.path.join(os.path.expanduser("~"), probe.default_name(self.rep)),
                                             "JSON (*.json)")
        if out:
            try:
                probe.save(self.rep, out)
            except OSError as e:
                QMessageBox.critical(self, tr("Bericht speichern"), str(e))


class MaterialsDialog(QDialog):
    """Druckmaterialien: Hauptkategorie (Plandruck/Qualitätsdruck), dann die Einstellungen je Material."""
    COLS = ("Name", "Kategorie", "g/m²", "Medientyp", "Qualität", "Tintenmenge", "Profil", "max. Farbauftrag",
            "nur für diesen Drucker")

    def __init__(self, parent, session, printer: str, caps):
        super().__init__(parent)
        from .. import printmat
        self.setWindowTitle(tr("Materialien – {0}").format(printer or tr("alle Drucker")))
        self.session, self.printer, self.caps = session, printer, caps
        self.others = [m for m in printmat.load() if m["printer"] and m["printer"] != printer]
        v = QVBoxLayout(self)
        t = QLabel(tr("Zuerst die Kategorie (Plandruck = Produktionsdruck, Qualitätsdruck = Poster, Foto, PVC …), "
                      "dann je Material: Grammatur (wählt die Rolle), Medientyp und Qualität im Treiber, Tintenmenge "
                      "(falls der Treiber sie anbietet) und das Farbprofil – sein Farbauftrag ist die echte Grenze. "
                      "„max. Farbauftrag“ ist der Richtwert, gegen den Passermark warnt."))
        t.setWordWrap(True)
        v.addWidget(t)
        self.tbl = QTableWidget(0, len(self.COLS))
        self.tbl.setHorizontalHeaderLabels([tr(c) for c in self.COLS])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        v.addWidget(self.tbl, 1)
        self.ids = []
        row = QHBoxLayout()
        b = QPushButton(icon("insert"), tr("Material hinzufügen"))
        b.clicked.connect(lambda: self._add({"name": tr("Neues Material"), "category": "quality"}))
        row.addWidget(b)
        b = QPushButton(icon("delete"), tr("Entfernen"))
        b.clicked.connect(self._remove)
        row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        f = QFormLayout()
        self.cmb_def = {}
        for cat in printmat.CATEGORIES:
            c = QComboBox()
            self.cmb_def[cat] = c
            f.addRow(tr("Standard für {0}:").format(tr(CAT_TEXT[cat])), c)
        if printer:
            v.addLayout(f)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        for m in printmat.load():
            if not m["printer"] or m["printer"] == printer:
                self._add(m)
        self._fill_defaults()
        self.resize(1100, 460)

    def _choice_combo(self, role: str, value: str, key: str | None = None) -> QComboBox:
        c = QComboBox()
        c.addItem(tr("wie im Treiber"), "")
        k = key or (self.caps.roles.get(role) if self.caps else None)
        if k and self.caps and k in self.caps.options:
            for ch in self.caps.options[k].choices:
                c.addItem(ch.text, ch.value)
        i = c.findData(value)
        if i < 0 and value:
            c.addItem(value, value)
            i = c.count() - 1
        c.setCurrentIndex(max(0, i))
        return c

    def _add(self, m: dict):
        from .. import config, printmat
        n = self.tbl.rowCount()
        self.tbl.insertRow(n)
        self.ids.append(m.get("id", ""))
        self.tbl.setItem(n, 0, QTableWidgetItem(m.get("name", "")))
        c = QComboBox()
        for cat in printmat.CATEGORIES:
            c.addItem(tr(CAT_TEXT[cat]), cat)
        c.setCurrentIndex(max(0, c.findData(m.get("category", "quality"))))
        self.tbl.setCellWidget(n, 1, c)
        w = QSpinBox()
        w.setRange(0, 2000)
        w.setSpecialValueText("–")
        w.setValue(int(m.get("weight") or 0))
        self.tbl.setCellWidget(n, 2, w)
        self.tbl.setCellWidget(n, 3, self._choice_combo("mediatype", m.get("media", "")))
        self.tbl.setCellWidget(n, 4, self._choice_combo("quality", m.get("quality", "")))
        dens = printmat.density_options(self.caps)
        dkey = m.get("density_key") or (dens[0][0] if dens else "")
        dc = self._choice_combo("", m.get("density", ""), dkey) if dkey else QComboBox()
        if not dkey:
            dc.addItem(tr("Treiber hat keine"), "")
            dc.setEnabled(False)
        dc.setProperty("density_key", dkey)
        self.tbl.setCellWidget(n, 5, dc)
        pc = QComboBox()
        pc.addItem(tr("wie beim Drucker"), "")
        for pr in self.session.cfg.get("color_profiles", []) or []:
            pc.addItem(pr.get("name") or pr.get("id"), pr.get("id"))
        pc.setCurrentIndex(max(0, pc.findData(m.get("profile", ""))))
        self.tbl.setCellWidget(n, 6, pc)
        t = QSpinBox()
        t.setRange(0, 400)
        t.setSuffix(" %")
        t.setSpecialValueText("–")
        t.setValue(int(m.get("tac") or 0))
        self.tbl.setCellWidget(n, 7, t)
        ck = QCheckBox()
        ck.setChecked(bool(m.get("printer")) or not m.get("id"))
        self.tbl.setCellWidget(n, 8, ck)

    def _remove(self):
        for i in sorted({ix.row() for ix in self.tbl.selectedIndexes()}, reverse=True):
            self.tbl.removeRow(i)
            self.ids.pop(i)
        self._fill_defaults()

    def _rows(self) -> list:
        from .. import printmat
        out = []
        for i in range(self.tbl.rowCount()):
            name = (self.tbl.item(i, 0).text() if self.tbl.item(i, 0) else "").strip()
            if not name:
                continue
            dc = self.tbl.cellWidget(i, 5)
            mid = self.ids[i] or printmat.new_id(name, self.others + out)
            out.append({"id": mid, "name": name, "category": self.tbl.cellWidget(i, 1).currentData(),
                        "weight": self.tbl.cellWidget(i, 2).value(), "media": self.tbl.cellWidget(i, 3).currentData(),
                        "quality": self.tbl.cellWidget(i, 4).currentData(),
                        "density_key": (dc.property("density_key") or "") if dc.currentData() else "",
                        "density": dc.currentData() or "", "profile": self.tbl.cellWidget(i, 6).currentData(),
                        "tac": self.tbl.cellWidget(i, 7).value(),
                        "printer": self.printer if self.tbl.cellWidget(i, 8).isChecked() else ""})
        return out

    def _fill_defaults(self):
        from .. import printmat
        if not self.printer:
            return
        rows = []
        for i in range(self.tbl.rowCount()):
            it = self.tbl.item(i, 0)
            rows.append((self.ids[i], it.text() if it else "", self.tbl.cellWidget(i, 1).currentData()))
        for cat, c in self.cmb_def.items():
            cur = c.currentData() if c.count() else printmat.default_for(self.printer, cat)
            c.clear()
            c.addItem(tr("– keins –"), "")
            for mid, name, mcat in rows:
                if mid and mcat == cat:
                    c.addItem(name, mid)
            c.setCurrentIndex(max(0, c.findData(cur or "")))

    def _save(self):
        from .. import printmat
        rows = self._rows()
        try:
            printmat.save(self.others + rows)
            if self.printer:
                for cat, c in self.cmb_def.items():
                    printmat.set_default(self.printer, cat, c.currentData() or "")
        except OSError as e:
            QMessageBox.critical(self, tr("Materialien"), str(e))
            return
        self.accept()


class FoldersDialog(QDialog):
    """Ausgabe-Ordner (Hotfolder): Druckseiten landen als PDF dort – z. B. VersaWorks für Roland-Drucker."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(tr("Ausgabe-Ordner"))
        v = QVBoxLayout(self)
        t = QLabel(tr("Für Geräte ohne Druckertreiber (Roland über VersaWorks, andere RIPs): jede Druckseite wird als "
                      "PDF in den Ordner gelegt – mit CutContour, falls eingeschaltet. Der Ordner erscheint dann wie "
                      "ein Drucker; Rollen dafür unter „Rollen …“ eintragen."))
        t.setWordWrap(True)
        v.addWidget(t)
        self.tbl = QTableWidget(0, 2)
        self.tbl.setHorizontalHeaderLabels([tr("Name"), tr("Ordner")])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        v.addWidget(self.tbl, 1)
        self.lbl_home = MsgBox(3, theme.ACCENT)
        v.addWidget(self.lbl_home)
        self.tbl.itemChanged.connect(lambda *_: self._check_home())
        row = QHBoxLayout()
        b = QPushButton(icon("insert"), tr("Ordner hinzufügen …"))
        b.clicked.connect(self._add_dir)
        row.addWidget(b)
        b = QPushButton(icon("delete"), tr("Entfernen"))
        b.clicked.connect(lambda: [self.tbl.removeRow(i) for i in sorted(
            {ix.row() for ix in self.tbl.selectedIndexes()}, reverse=True)])
        row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        for e in pp.hotfolders():
            self._row(e["name"], e["dir"])
        self._check_home()
        self.resize(640, 320)

    def _check_home(self):
        from .. import shared
        bad = [self.tbl.item(i, 1).text() for i in range(self.tbl.rowCount())
               if self.tbl.item(i, 1) and shared.in_home(self.tbl.item(i, 1).text())]
        self.lbl_home.setText(shared.home_hint() if bad else "")

    def _row(self, name, d):
        n = self.tbl.rowCount()
        self.tbl.insertRow(n)
        self.tbl.setItem(n, 0, QTableWidgetItem(name))
        self.tbl.setItem(n, 1, QTableWidgetItem(d))

    def _add_dir(self):
        from .. import shared
        d = QFileDialog.getExistingDirectory(self, tr("Ausgabe-Ordner wählen"), shared.hotfolder_dir())
        if d:
            self._row(os.path.basename(d.rstrip("/\\")) or d, d)

    def _save(self):
        out = []
        for i in range(self.tbl.rowCount()):
            name = (self.tbl.item(i, 0).text() if self.tbl.item(i, 0) else "").strip()
            d = (self.tbl.item(i, 1).text() if self.tbl.item(i, 1) else "").strip()
            if name and d:
                out.append({"name": name, "dir": d})
        try:
            pp.save_hotfolders(out)
        except OSError as e:
            QMessageBox.critical(self, tr("Ausgabe-Ordner"), str(e))
            return
        self.accept()


class PlanDialog(QDialog):
    printed = Signal(str)

    COLS = ("Plan", "Druckbereich", "Rolle", "Länge", "Menge")

    def __init__(self, parent, session, ctl=None, doc=None, path: str = "", name: str = "", kind: str = "plan"):
        super().__init__(parent)
        self.kind = kind if kind in pp.KINDS else "plan"
        self.setWindowTitle(tr("Plandruck – Passermark") if self.kind == "plan" else tr("Posterdruck – Passermark"))
        self.setAcceptDrops(True)
        self.session, self.ctl = session, ctl
        self.items: list = []
        self.owned: list = []                 # selbst geöffnete Dokumente (beim Schließen freigeben)
        self.rolls: list = []
        self.roll_state = None
        self.caps = None
        self.printer = ""
        self._queue: list = []
        self._q = None
        self._building = False
        self.s0 = load_settings(self.kind)
        self._bleed_color = self.s0.bleed_color

        v = QVBoxLayout(self)
        # Drucker + Rollen
        top = QHBoxLayout()
        top.addWidget(QLabel(tr("Drucker:")))
        self.cmb_printer = QComboBox()
        self.cmb_printer.setMinimumWidth(160)
        top.addWidget(self.cmb_printer)
        top.addStretch(1)
        self.lbl_rolls = MsgBox(3, theme.MUTED)
        self.btn_reload = QPushButton(tr("Rollen neu lesen"))
        self.btn_reload.clicked.connect(lambda: self._load_rolls(force=True))
        top.addWidget(self.btn_reload)
        self.btn_manual = QPushButton(icon("roll"), tr("Rollen …"))
        self.btn_manual.setToolTip(tr("Rollen von Hand eintragen (wenn das Gerät nichts meldet)"))
        self.btn_manual.clicked.connect(self._edit_rolls)
        top.addWidget(self.btn_manual)
        b = QPushButton(icon("open"), tr("Ordner …"))
        b.setToolTip(tr("Ausgabe in Ordner (z. B. Hotfolder von VersaWorks) einrichten"))
        b.clicked.connect(self._edit_folders)
        top.addWidget(b)
        v.addLayout(top)
        v.addWidget(self.lbl_rolls)

        split = QSplitter(Qt.Orientation.Horizontal)
        v.addWidget(split, 1)

        # ---- links: Pläne ----
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        b = QPushButton(icon("insert"), tr("Pläne hinzufügen …") if self.kind == "plan" else tr("Poster hinzufügen …"))
        b.setToolTip(tr("PDF, Bilder oder Office-Dateien – oder einfach ins Fenster ziehen"))
        b.clicked.connect(self._add_files)
        bar.addWidget(b)
        self.btn_remove = QPushButton(icon("delete"), "")
        self.btn_remove.setToolTip(tr("Ausgewählte Pläne entfernen"))
        self.btn_remove.clicked.connect(self._remove)
        bar.addWidget(self.btn_remove)
        b = QPushButton(icon("move_up"), "")
        b.setToolTip(tr("Nach oben"))
        b.clicked.connect(lambda: self._move(-1))
        bar.addWidget(b)
        b = QPushButton(icon("move_down"), "")
        b.setToolTip(tr("Nach unten"))
        b.clicked.connect(lambda: self._move(1))
        bar.addWidget(b)
        bar.addStretch(1)
        lv.addLayout(bar)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([tr(c) for c in self.COLS])
        self.tree.setRootIsDecorated(False)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        self.tree.itemChanged.connect(self._qty_changed)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)      # nur die Menge
        self.tree.itemDoubleClicked.connect(lambda row, col: self.tree.editItem(row, 4) if col == 4 else None)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        vsplit = QSplitter(Qt.Orientation.Vertical)
        vsplit.addWidget(self.tree)
        pg = QGroupBox(tr("Druckseiten (Vorschau)"))
        pgl = QVBoxLayout(pg)
        pgl.setContentsMargins(4, 4, 4, 4)
        self.lst_prev = QListWidget()
        self.lst_prev.setViewMode(QListView.ViewMode.IconMode)
        self.lst_prev.setFlow(QListView.Flow.LeftToRight)
        self.lst_prev.setWrapping(True)
        self.lst_prev.setResizeMode(QListView.ResizeMode.Adjust)
        self.lst_prev.setMovement(QListView.Movement.Static)
        self.lst_prev.setIconSize(QSize(PREVIEW_PX, PREVIEW_PX))
        self.lst_prev.setSpacing(6)
        self.lst_prev.setWordWrap(True)
        self.lst_prev.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        pgl.addWidget(self.lst_prev)
        self.lbl_prev = QLabel()
        self.lbl_prev.setStyleSheet(f"color: {theme.MUTED};")
        self.lbl_prev.setWordWrap(True)
        pgl.addWidget(self.lbl_prev)
        vsplit.addWidget(pg)
        vsplit.setStretchFactor(0, 3)
        vsplit.setStretchFactor(1, 2)
        vsplit.setChildrenCollapsible(False)
        lv.addWidget(vsplit, 1)
        self._prev_timer = QTimer(self)
        self._prev_timer.setSingleShot(True)
        self._prev_timer.setInterval(350)
        self._prev_timer.timeout.connect(self._preview)
        self.lbl_hint = QLabel(tr("Pläne mit + hinzufügen oder ins Fenster ziehen. Jede Seite ist ein Plan. "
                                  "Menge: Doppelklick. Rechtsklick: Druckbereich je Plan."))
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setStyleSheet(f"color: {theme.MUTED};")
        lv.addWidget(self.lbl_hint)
        split.addWidget(left)

        # ---- rechts: Laufmeter + Einstellungen ----
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        g = QGroupBox(tr("Laufmeter je Rolle"))
        gv = QVBoxLayout(g)
        self.lbl_len = QLabel()
        self.lbl_len.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_len.setWordWrap(True)
        gv.addWidget(self.lbl_len)
        self.lbl_warn = MsgBox(4, theme.ACCENT)
        gv.addWidget(self.lbl_warn)
        rv.addWidget(g)

        g = QGroupBox(tr("Einstellungen"))
        f = QFormLayout(g)
        s0 = self.s0
        row = QHBoxLayout()
        self.spn_copies = QSpinBox()
        self.spn_copies.setRange(1, 999)
        self.spn_copies.setValue(max(1, s0.copies))
        row.addWidget(self.spn_copies)
        self.chk_collate = QCheckBox(tr("Sortiert"))
        self.chk_collate.setToolTip(tr("Aus: jeder Plan alle Exemplare hintereinander (Plan 1 ×3, Plan 2 ×3 …).\n"
                                       "An: Satz für Satz."))
        self.chk_collate.setChecked(s0.collate)
        row.addWidget(self.chk_collate)
        row.addStretch(1)
        f.addRow(tr("Exemplare:"), row)
        self.cmb_copies = QComboBox()
        fill_combo(self.cmb_copies, [(k, tr(t)) for k, t in COPIES_TEXT.items()], pp.copies_mode(s0))
        self.cmb_copies.setToolTip(tr("Ein Auftrag, je Exemplar ein Blatt: so erwartet es z. B. die ColorWave – sie "
                                      "schneidet nach jedem Blatt.\nJe Exemplar ein Auftrag: (1/3), (2/3) …\n"
                                      "Kopienzahl: ein Blatt, das Gerät druckt es mehrfach."))
        f.addRow(tr("Versand:"), self.cmb_copies)
        self.lbl_scope = QLabel()
        self.lbl_scope.setWordWrap(True)
        self.lbl_scope.setStyleSheet(f"color: {theme.ACCENT};")
        f.addRow(self.lbl_scope)
        self.cmb_order = QComboBox()
        fill_combo(self.cmb_order, [(k, tr(t)) for k, t in ORDER_TEXT.items()], s0.order)
        f.addRow(tr("Reihenfolge:"), self.cmb_order)
        self.cmb_color = QComboBox()
        fill_combo(self.cmb_color, [(k, tr(t)) for k, t in COLOR_TEXT.items()], s0.color)
        f.addRow(tr("Farbe:"), self.cmb_color)
        row = QHBoxLayout()
        self.cmb_mat = QComboBox()
        self.cmb_mat.setToolTip(tr("Passermark-Material: Grammatur (wählt die Rolle), Medientyp, Qualität, "
                                   "Tintenmenge und Profil – unter „Materialien …“ je Drucker"))
        row.addWidget(self.cmb_mat, 1)
        b = QPushButton(icon("material"), "")
        b.setToolTip(tr("Materialien …"))
        b.clicked.connect(self._edit_materials)
        row.addWidget(b)
        f.addRow(tr("Material:"), row)
        self.cmb_roll = QComboBox()
        self.cmb_roll.setToolTip(tr("Auf diese Rolle drucken – „Automatisch“ wählt nach Material bzw. Grammatur "
                                    "die schmälste passende"))
        f.addRow(tr("Rolle:"), self.cmb_roll)
        self.cmb_align = QComboBox()
        fill_combo(self.cmb_align, [(k, tr(t)) for k, t in ALIGN_TEXT.items()], s0.align)
        self.cmb_align.setToolTip(tr("Am Rand: die Seite ist so breit wie die Rolle, der Plan liegt an der "
                                     "Rollenkante – Rand bzw. äußere Linie bleiben, es bleibt ein Längsschnitt.\n"
                                     "Mittig: rundum gleich viel Abstand, das Gerät blendet nichts aus."))
        f.addRow(tr("Auf der Rolle:"), self.cmb_align)
        self.cmb_media = QComboBox()            # 1.18.7: nicht mehr angezeigt – der Medientyp folgt der Rolle
        self.ed_weights = QLineEdit(", ".join(str(w) for w in (s0.weights or [])))
        self.ed_weights.setToolTip(tr("Rollen mit dieser Grammatur werden für Pläne verwendet (leer = alle Rollen)"))
        if self.kind == "plan":
            f.addRow(tr("Planpapier g/m²:"), self.ed_weights)
        self.cmb_frame = QComboBox()
        fill_combo(self.cmb_frame, [(k, tr(t)) for k, t in FRAME_TEXT.items()], s0.frame)
        self.cmb_frame.setToolTip(tr("Zwei Außenlinien: gedruckt wird bis zur äußeren – sie verschwindet, um den "
                                     "Plan bleibt ein exakter Rand. Sonst: Inhalt + Rand."))
        f.addRow(tr("Druckbereich:"), self.cmb_frame)
        self.spn_margin = QDoubleSpinBox()
        self.spn_margin.setRange(0, 100)
        self.spn_margin.setDecimals(1)
        self.spn_margin.setSuffix(" mm")
        self.spn_margin.setValue(s0.margin_mm)
        f.addRow(tr("Rand ohne Außenlinien:"), self.spn_margin)
        self.cmb_rotate = QComboBox()
        fill_combo(self.cmb_rotate, [(k, tr(t)) for k, t in ROTATE_TEXT.items()], s0.rotate)
        f.addRow(tr("Lage:"), self.cmb_rotate)
        row = QHBoxLayout()
        self.cmb_scale = QComboBox()
        fill_combo(self.cmb_scale, [(k, tr(t)) for k, t in SCALE_TEXT.items()], s0.scale_mode)
        row.addWidget(self.cmb_scale)
        self.spn_scale = QDoubleSpinBox()
        self.spn_scale.setRange(1, 1000)
        self.spn_scale.setDecimals(1)
        self.spn_scale.setSuffix(" %")
        self.spn_scale.setValue(s0.scale_pct)
        self.spn_scale.setToolTip(tr("100 % = tatsächliche Größe (Maßstab bleibt)"))
        row.addWidget(self.spn_scale)
        self.spn_scale_mm = QDoubleSpinBox()
        self.spn_scale_mm.setRange(0, 100000)
        self.spn_scale_mm.setDecimals(1)
        self.spn_scale_mm.setSuffix(" mm")
        self.spn_scale_mm.setValue(s0.scale_mm or 0)
        self.spn_scale_mm.setToolTip(tr("Endmaß der Kante ohne Überfüller – die andere Kante folgt im Verhältnis"))
        row.addWidget(self.spn_scale_mm)
        f.addRow(tr("Skalierung:"), row)
        row = QHBoxLayout()
        self.spn_bleed = QDoubleSpinBox()
        self.spn_bleed.setRange(0, 50)
        self.spn_bleed.setDecimals(1)
        self.spn_bleed.setSuffix(" mm")
        self.spn_bleed.setValue(s0.bleed_mm)
        row.addWidget(self.spn_bleed)
        self.cmb_bleed = QComboBox()
        fill_combo(self.cmb_bleed, [(k, tr(t)) for k, t in BLEED_TEXT.items()], s0.bleed_mode)
        row.addWidget(self.cmb_bleed)
        self.btn_bcolor = QPushButton()
        self.btn_bcolor.setToolTip(tr("Farbe des Überfüllers"))
        self.btn_bcolor.setFixedWidth(36)
        self.btn_bcolor.clicked.connect(self._pick_color)
        row.addWidget(self.btn_bcolor)
        f.addRow(tr("Überfüller:"), row)
        self.chk_marks = QCheckBox(tr("Schnittmarken"))
        self.chk_marks.setChecked(s0.crop_marks)
        f.addRow("", self.chk_marks)
        self.chk_hair = QCheckBox(tr("Haarlinien auf {0} mm anheben").format(pp.mm_text(s0.hairline_mm)))
        self.chk_hair.setToolTip(tr("Linien, die dünner sind, druckt der Plotter kaum oder gar nicht"))
        self.chk_hair.setChecked(s0.fix_hairlines)
        f.addRow("", self.chk_hair)
        self.chk_fold = QCheckBox(tr("Faltmarken nach DIN 824"))
        self.chk_fold.setToolTip(tr("Kurze Marken an den Falzstellen (Form A, vereinfacht) – für Falten von Hand"))
        self.chk_fold.setChecked(s0.fold_marks)
        if self.kind == "plan":
            f.addRow("", self.chk_fold)
        row = QHBoxLayout()
        self.chk_nest = QCheckBox(tr("Nebeneinander auf die Rolle"))
        self.chk_nest.setToolTip(tr("Mehrere Stücke nebeneinander – spart Laufmeter (die Reihenfolge ergibt sich "
                                    "dann aus der Verteilung)"))
        self.chk_nest.setChecked(s0.nest)
        row.addWidget(self.chk_nest)
        self.spn_gap = QDoubleSpinBox()
        self.spn_gap.setRange(0, 100)
        self.spn_gap.setDecimals(1)
        self.spn_gap.setSuffix(" mm")
        self.spn_gap.setPrefix(tr("Abstand "))
        self.spn_gap.setValue(s0.gap_mm)
        row.addWidget(self.spn_gap)
        f.addRow("", row)
        row = QHBoxLayout()
        self.cmb_over = QComboBox()
        fill_combo(self.cmb_over, [(k, tr(t)) for k, t in OVER_TEXT.items()], s0.overwidth)
        self.cmb_over.setToolTip(tr("Was passiert, wenn ein Stück auf keine Rolle passt"))
        row.addWidget(self.cmb_over, 1)
        self.spn_overlap = QDoubleSpinBox()
        self.spn_overlap.setRange(0, 200)
        self.spn_overlap.setDecimals(0)
        self.spn_overlap.setSuffix(" mm")
        self.spn_overlap.setPrefix(tr("Überlappung "))
        self.spn_overlap.setValue(s0.overlap_mm)
        row.addWidget(self.spn_overlap)
        f.addRow(tr("Breiter als die Rolle:"), row)
        rv.addWidget(g)

        g = QGroupBox(tr("Banner und Schneiden"))
        g.setCheckable(False)
        fb = QFormLayout(g)
        row = QHBoxLayout()
        self.spn_hem = QDoubleSpinBox()
        self.spn_hem.setRange(0, 200)
        self.spn_hem.setDecimals(0)
        self.spn_hem.setSuffix(" mm")
        self.spn_hem.setSpecialValueText(tr("kein"))
        self.spn_hem.setValue(s0.hem_mm)
        self.spn_hem.setToolTip(tr("Saum (umschlagen) oder Tunnel (für Stangen) – Zugabe außerhalb des Endformats"))
        row.addWidget(self.spn_hem)
        self.chk_hem = {}
        for k, t in (("l", "links"), ("r", "rechts"), ("t", "oben"), ("b", "unten")):
            c = QCheckBox(tr(t))
            c.setChecked(k in s0.hem_sides)
            self.chk_hem[k] = c
            row.addWidget(c)
        fb.addRow(tr("Saum/Tunnel:"), row)
        row = QHBoxLayout()
        self.spn_grom = QDoubleSpinBox()
        self.spn_grom.setRange(0, 3000)
        self.spn_grom.setDecimals(0)
        self.spn_grom.setSuffix(" mm")
        self.spn_grom.setSpecialValueText(tr("keine"))
        self.spn_grom.setValue(s0.grommet_spacing_mm)
        self.spn_grom.setToolTip(tr("Ösenmarken: an den Ecken und dazwischen mit höchstens diesem Abstand"))
        row.addWidget(self.spn_grom)
        self.spn_grom_in = QDoubleSpinBox()
        self.spn_grom_in.setRange(3, 200)
        self.spn_grom_in.setDecimals(0)
        self.spn_grom_in.setSuffix(" mm")
        self.spn_grom_in.setPrefix(tr("vom Rand "))
        self.spn_grom_in.setValue(s0.grommet_inset_mm)
        row.addWidget(self.spn_grom_in)
        fb.addRow(tr("Ösen alle:"), row)
        self.chk_cut = QCheckBox(tr("CutContour am Bildrand (Print & Cut)"))
        self.chk_cut.setToolTip(tr("Schneidlinie in der Sonderfarbe CutContour um das Endformat (inkl. Saum) – "
                                   "VersaWorks, CutStudio und andere schneiden danach. Freie Konturen: "
                                   "Druckaufbereitung → CutContour."))
        self.chk_cut.setChecked(s0.cut_contour)
        fb.addRow("", self.chk_cut)
        self.chk_pcm = QCheckBox(tr("Passermarken (Winkel) an den Ecken"))
        self.chk_pcm.setToolTip(tr("Nur wenn das Schneideprogramm keine eigenen setzt (VersaWorks setzt sie selbst)"))
        self.chk_pcm.setChecked(s0.printcut_marks)
        fb.addRow("", self.chk_pcm)
        rv.addWidget(g)
        rv.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(right)
        right.setMinimumWidth(320)
        split.addWidget(scroll)
        split.setChildrenCollapsible(False)
        left.setMinimumWidth(280)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)

        # ---- unten ----
        bot = QHBoxLayout()
        self.lbl_state = QLabel()
        self.lbl_state.setWordWrap(True)
        self.lbl_state.setStyleSheet(f"color: {theme.MUTED};")
        bot.addWidget(self.lbl_state, 1)
        self.btn_pdf = QPushButton(icon("save"), tr("Als PDF speichern …"))
        self.btn_pdf.setToolTip(tr("Alle Druckseiten (je Plan eine) zum Prüfen oder Weitergeben"))
        self.btn_pdf.clicked.connect(self._save_pdf)
        bot.addWidget(self.btn_pdf)
        self.btn_print = QPushButton(icon("print"), tr("Drucken"))
        self.btn_print.setDefault(True)
        self.btn_print.clicked.connect(self._print)
        bot.addWidget(self.btn_print)
        b = QPushButton(tr("Schließen"))
        b.clicked.connect(self.reject)
        bot.addWidget(b)
        v.addLayout(bot)

        self.finished.connect(self._cleanup)
        self._timer = QTimer(self)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._analyze_next)
        self._color_button()

        # Änderungen: nur neu platzieren bzw. neu erkennen
        for w in (self.spn_copies, self.spn_gap, self.spn_overlap, self.spn_hem, self.spn_grom, self.spn_grom_in):
            w.valueChanged.connect(self._changed)
        for w in (self.chk_collate, self.chk_marks, self.chk_hair, self.chk_fold, self.chk_nest, self.chk_cut,
                  self.chk_pcm, *self.chk_hem.values()):
            w.toggled.connect(self._changed)
        for w in (self.cmb_order, self.cmb_color, self.cmb_over, self.cmb_copies):
            w.currentIndexChanged.connect(self._changed)
        self.ed_weights.editingFinished.connect(self._changed)
        # Einstellungen je Plan: wirken auf die Auswahl (nichts bzw. alles ausgewählt: auf alle)
        self.g = {k: getattr(s0, k) for k in pp.OV_KEYS}
        self.g["roll_pick"] = s0.roll_pick
        for w, key, get in ((self.cmb_mat, "material", lambda: self.cmb_mat.currentData() or ""),
                            (self.cmb_roll, "roll_pick", lambda: self.cmb_roll.currentData() or ""),
                            (self.cmb_align, "align", lambda: self.cmb_align.currentData() or "center"),
                            (self.cmb_rotate, "rotate", lambda: self.cmb_rotate.currentData() or "auto"),
                            (self.cmb_bleed, "bleed_mode", lambda: self.cmb_bleed.currentData() or "mirror"),
                            (self.cmb_frame, "frame", lambda: self.cmb_frame.currentData() or "auto")):
            w.currentIndexChanged.connect(lambda _i, key=key, get=get: self._set_field({key: get()}))
        self.spn_bleed.valueChanged.connect(lambda v: self._set_field({"bleed_mm": v}))
        self.spn_margin.valueChanged.connect(lambda v: self._set_field({"margin_mm": v}))
        self.cmb_scale.currentIndexChanged.connect(self._scale_changed)
        self.spn_scale.valueChanged.connect(self._scale_changed)
        self.spn_scale_mm.valueChanged.connect(self._scale_changed)
        self.tree.itemSelectionChanged.connect(self._load_fields)
        self._scale_widgets()

        make_responsive(self)
        self.setMinimumSize(640, 420)
        self._fill_printers()
        self.cmb_printer.currentIndexChanged.connect(self._printer_changed)
        self._printer_changed()
        if doc is not None:
            self.add_doc(doc, path or name, own=False)
        self.resize(1180, 720)
        self._refresh()

    # ------------------------------------------------------------------ #
    # Drucker und Rollen
    # ------------------------------------------------------------------ #
    def _fill_printers(self):
        from .. import l10n, printjob
        try:
            plist = [p for p in printers.list_printers() if p.name != printers.PDF_TARGET]
        except Exception:
            plist = []
        for p in plist:
            self.cmb_printer.addItem(p.name + (f" – {p.model}" if p.model else ""), p.name)
        for e in pp.hotfolders():
            self.cmb_printer.addItem(tr("Ordner: {0}").format(e["name"]), pp.FOLDER_PREFIX + e["name"])
        want = l10n.load_settings().get(_keys(self.kind)[1]) or printjob.default_printer(self.session) or ""
        i = self.cmb_printer.findData(want)
        self.cmb_printer.setCurrentIndex(max(0, i))

    def _printer_changed(self, *_a):
        self.printer = self.cmb_printer.currentData() or ""
        self.caps = None
        if self.printer and not pp.is_folder(self.printer):
            try:
                self.caps = self.session.caps_for(self.printer)
            except Exception as e:                              # noqa: BLE001
                self.lbl_rolls.setText(tr("Drucker nicht abfragbar: {0}").format(e))
        self._fill_media()
        self._fill_materials()
        self._load_rolls()

    def _fill_media(self):
        cur = self.cmb_media.currentData() if self.cmb_media.count() else self.s0.media
        self.cmb_media.blockSignals(True)
        self.cmb_media.clear()
        self.cmb_media.addItem(tr("Wie im Treiber / am Gerät"), "")
        key = self.caps.roles.get("mediatype") if self.caps else None
        if key and key in self.caps.options:
            for ch in self.caps.options[key].choices:
                self.cmb_media.addItem(ch.text, ch.value)
        i = self.cmb_media.findData(cur or "")
        self.cmb_media.setCurrentIndex(max(0, i))
        self.cmb_media.blockSignals(False)

    def _load_rolls(self, force: bool = False):
        """Zuerst die von Hand eingetragenen anzeigen, das Gerät im Hintergrund fragen."""
        self.rolls = rl.manual(self.printer) if self.printer else []
        self._assign_slots(self.rolls)
        self.roll_state = rl.RollState(self.rolls, "manual" if self.rolls else "none")
        self._roll_text()
        self._refresh()
        host = rl.host_for(self.session, self.printer) if (self.printer and not pp.is_folder(self.printer)) else ""
        if not host:
            if not self.rolls:
                self.lbl_rolls.setText(tr("Geräteadresse nicht ermittelbar – unter „Rollen …“ die IP-Adresse "
                                          "eintragen oder die Rollen von Hand"))
            return
        self.btn_reload.setEnabled(False)
        self.lbl_rolls.setText(self.lbl_rolls.text() + "  " + tr("(frage Gerät ab …)"))
        from .. import roland
        fn = rl.query_roland if roland.is_roland(self.printer, rl.model_of(self.printer)) else None
        self._q = _start_query(host, self._rolls_read, self.printer, fn)

    def _assign_slots(self, rolls: list):
        for i, r in enumerate(rolls):
            if not r.slot and self.caps is not None:
                r.slot = rl.slot_for(self.caps, r.device or r.name, i)

    def _rolls_read(self, st, printer: str):
        if getattr(self, "_closed", False):
            return
        self.btn_reload.setEnabled(True)
        if printer != self.printer:
            return
        if st.rolls:
            self.rolls = [rl.Roll.from_dict(r.to_dict()) for r in st.rolls]
            self._assign_slots(self.rolls)
            self.roll_state = rl.RollState(self.rolls, st.origin, "", st.host, list(getattr(st, "catalog", []) or []))
        else:
            self.roll_state = rl.RollState(self.rolls, "manual" if self.rolls else "none", st.error, st.host)
        self._roll_text()
        self._refresh()

    def _fill_rolls(self):
        g = getattr(self, "g", None)
        cur = g["roll_pick"] if g is not None else self.s0.roll_pick
        self.cmb_roll.blockSignals(True)
        self.cmb_roll.clear()
        self.cmb_roll.addItem(tr("Automatisch"), "")
        for r in self.rolls:
            if not getattr(r, "empty", False):
                self.cmb_roll.addItem(r.label(), pp.roll_key(r))
        i = self.cmb_roll.findData(cur or "")
        self.cmb_roll.setCurrentIndex(max(0, i))
        self.cmb_roll.blockSignals(False)

    def _roll_text(self):
        self._fill_rolls()
        self._fill_materials()
        if hasattr(self, "g"):
            self._load_fields()
        st = self.roll_state
        if st is None or not self.rolls:
            err = f" ({st.error})" if st is not None and st.error else ""
            self.lbl_rolls.setText(tr("Keine Rollen bekannt") + err + " – " + tr("„Rollen …“ zum Eintragen"))
            return
        self.lbl_rolls.setText(tr(ORIGIN_TEXT.get(st.origin, st.origin)) + ": "
                               + "  ·  ".join(r.label() for r in self.rolls))

    def _edit_rolls(self):
        if not self.printer:
            return
        if RollsDialog(self, self.session, self.printer).exec():
            self._load_rolls()

    # ------------------------------------------------------------------ #
    # Pläne
    # ------------------------------------------------------------------ #
    def add_doc(self, doc, source: str, own: bool = True, pages=None):
        if own:
            self.owned.append(doc)
        for p in (pages if pages is not None else range(len(doc))):
            it = pp.Item(p, 1, None, source=source, doc=doc)
            self.items.append(it)
            self._queue.append(it)
        self._rebuild()
        self._timer.start()

    def _add_files(self):
        from .. import convert
        paths, _ = QFileDialog.getOpenFileNames(self, tr("Pläne hinzufügen"), os.path.expanduser("~"),
                                                tr("Pläne (*.pdf *.png *.jpg *.jpeg *.tif *.tiff);;Alle Dateien (*)"))
        self.add_paths([p for p in paths if convert.is_supported(p) or p.lower().endswith(".pdf")])

    def add_paths(self, paths: list):
        for p in paths:
            doc = self._load(p)
            if doc is not None:
                self.add_doc(doc, p)

    def _load(self, path: str):
        try:
            if self.ctl is not None:
                from .viewer import load_any
                return load_any(self, self.ctl, path)
            import pypdfium2 as pdfium
            from .. import images
            if images.is_image(path):
                return images.images_to_document([path], 96.0)
            return pdfium.PdfDocument(path)
        except Exception as e:                                  # noqa: BLE001
            QMessageBox.warning(self, tr("Plandruck"), tr("{0} lässt sich nicht öffnen: {1}").format(
                os.path.basename(path), e))
            return None

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        from .. import convert
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        self.add_paths([p for p in paths if convert.is_supported(p) or p.lower().endswith(".pdf")])

    def _selected(self) -> list:
        rows = sorted({self.tree.indexOfTopLevelItem(x) for x in self.tree.selectedItems()})
        return [r for r in rows if r >= 0]

    def _remove(self):
        rows = self._selected()
        for r in reversed(rows):
            it = self.items.pop(r)
            if it in self._queue:
                self._queue.remove(it)
        self._rebuild()
        self._refresh()

    def _move(self, d: int):
        rows = self._selected()
        if not rows:
            return
        if (d < 0 and rows[0] == 0) or (d > 0 and rows[-1] == len(self.items) - 1):
            return
        for r in (rows if d < 0 else reversed(rows)):
            self.items[r], self.items[r + d] = self.items[r + d], self.items[r]
        self._rebuild()
        for r in rows:
            self.tree.topLevelItem(r + d).setSelected(True)
        self._refresh()

    def _menu(self, pos):
        rows = self._selected()
        if not rows:
            return
        m = QMenu(self)
        sub = m.addMenu(tr("Druckbereich"))
        for k in ("", ) + pp.FRAME_MODES:
            a = sub.addAction(tr("Wie eingestellt") if k == "" else tr(FRAME_TEXT[k]))
            a.setCheckable(True)
            a.setChecked(all(self.items[r].ov.get("frame", self.items[r].frame) == k for r in rows))
            a.triggered.connect(lambda _c=False, k=k: self._set_frame(rows, k))
        a = m.addAction(tr("Menge …"))
        a.triggered.connect(lambda: self.tree.editItem(self.tree.topLevelItem(rows[0]), 4))
        m.exec(self.tree.viewport().mapToGlobal(pos))

    def _set_frame(self, rows, k):
        for r in rows:
            it = self.items[r]
            it.frame = ""
            if k:
                it.ov["frame"] = k
            else:
                it.ov.pop("frame", None)
            it.area = None
            if it not in self._queue:
                self._queue.append(it)
        self._timer.start()
        self._refresh()

    def _qty_changed(self, row, col):
        if self._building or col != 4:
            return
        i = self.tree.indexOfTopLevelItem(row)
        if i < 0:
            return
        try:
            q = max(0, int(row.text(4).strip() or "0"))
        except ValueError:
            q = self.items[i].qty
        self.items[i].qty = q
        self._refresh()

    def _rebuild(self):
        self._building = True
        self.tree.clear()
        for it in self.items:
            row = QTreeWidgetItem([it.label, "", "", "", str(it.qty)])
            row.setFlags(row.flags() | Qt.ItemFlag.ItemIsEditable)
            row.setTextAlignment(4, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.setTextAlignment(3, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tree.addTopLevelItem(row)
        self._building = False

    # ------------------------------------------------------------------ #
    # Erkennen und Rechnen
    # ------------------------------------------------------------------ #
    def _redetect(self, *_a):
        for it in self.items:
            it.area = None
            if it not in self._queue:
                self._queue.append(it)
        self._timer.start()
        self._refresh()

    def _redetect_hairlines(self, *_a):
        s = self.settings()
        for it in self.items:
            if it.area is not None:
                try:
                    it.hairlines = pp.hairlines(it.doc, it.page, s.hairline_mm,
                                                pp.factor(it.area, pp.eff(s, it)) * 100.0)
                except Exception:
                    pass
        self._refresh()

    def _analyze_next(self):
        if not self._queue:
            self._timer.stop()
            self.lbl_state.setText("")
            self._refresh()
            return
        it = self._queue.pop(0)
        s = self.settings()
        self.lbl_state.setText(tr("Erkenne {0} … ({1} offen)").format(it.label, len(self._queue)))
        try:
            es = pp.eff(s, it)
            it.area = pp.detect(it.doc, it.page, es.frame, es.margin_mm)
            it.hairlines = pp.hairlines(it.doc, it.page, s.hairline_mm, pp.factor(it.area, es) * 100.0)
        except Exception as e:                                  # noqa: BLE001
            it.area = None
            self.lbl_state.setText(tr("{0}: {1}").format(it.label, e))
        self._refresh()

    def _changed(self, *_a):
        self._color_button()
        self._refresh()

    def _weights(self) -> list:
        out = []
        for t in self.ed_weights.text().replace(";", ",").split(","):
            t = t.strip().lower().replace("g", "")
            if t.isdigit():
                out.append(int(t))
        return out

    # ------------------------------------------------------------------ #
    # Einstellungen je Plan (Auswahl)
    # ------------------------------------------------------------------ #
    def _partial(self) -> list:
        """Ausgewählte Pläne – leer, wenn nichts oder alles ausgewählt ist (dann gilt es für alle)."""
        rows = self._selected()
        return [self.items[r] for r in rows] if 0 < len(rows) < len(self.items) else []

    def _set_field(self, vals: dict):
        if getattr(self, "_loading_fields", False):
            return
        sel = self._partial()
        redetect = bool({"frame", "margin_mm"} & set(vals))
        targets = sel or self.items
        if sel:
            for it in sel:
                for k, v in vals.items():
                    if v == self.g.get(k):
                        it.ov.pop(k, None)       # gleich wie für alle: keine Abweichung mehr
                    else:
                        it.ov[k] = v
                    if k == "frame":
                        it.frame = ""
        else:
            self.g.update(vals)
            for it in self.items:
                for k in vals:
                    it.ov.pop(k, None)
                    if k == "frame":
                        it.frame = ""
        self._color_button()
        if redetect:
            for it in targets:
                it.area = None
                if it not in self._queue:
                    self._queue.append(it)
            self._timer.start()
        elif {"scale_pct", "scale_mode", "scale_mm"} & set(vals):
            self._redetect_hairlines()
            return
        self._refresh()

    def _scale_widgets(self):
        pct = (self.cmb_scale.currentData() or "pct") == "pct"
        self.spn_scale.setVisible(pct)
        self.spn_scale_mm.setVisible(not pct)

    def _scale_changed(self, *_a):
        self._scale_widgets()
        mode = self.cmb_scale.currentData() or "pct"
        if mode != "pct" and self.spn_scale_mm.value() <= 0:
            return                               # erst ein Maß eingeben
        self._set_field({"scale_mode": mode, "scale_pct": self.spn_scale.value(), "scale_mm": self.spn_scale_mm.value()})

    def _load_fields(self):
        """Felder zeigen die Werte der Auswahl (erster ausgewählter Plan) bzw. die für alle."""
        sel = self._partial()
        base = self.settings()
        es = pp.eff(base, sel[0]) if sel else base
        self._loading_fields = True
        try:
            for w, v in ((self.cmb_mat, es.material), (self.cmb_roll, es.roll_pick), (self.cmb_align, es.align),
                         (self.cmb_rotate, es.rotate), (self.cmb_bleed, es.bleed_mode), (self.cmb_frame, es.frame),
                         (self.cmb_scale, es.scale_mode)):
                w.blockSignals(True)
                i = w.findData(v)
                w.setCurrentIndex(max(0, i))
                w.blockSignals(False)
            for w, v in ((self.spn_bleed, es.bleed_mm), (self.spn_margin, es.margin_mm), (self.spn_scale, es.scale_pct),
                         (self.spn_scale_mm, es.scale_mm or 0)):
                w.blockSignals(True)
                w.setValue(v)
                w.blockSignals(False)
            self._bleed_color = es.bleed_color
            self._color_button()
            self._scale_widgets()
        finally:
            self._loading_fields = False
        if sel:
            self.lbl_scope.setText(tr("Änderungen gelten nur für die Auswahl ({0} von {1}) – Material, Rolle, Lage, "
                                      "Druckbereich, Skalierung und Überfüller").format(len(sel), len(self.items)))
        else:
            self.lbl_scope.setText("")

    def _ov_text(self, it) -> str:
        """Kurz, was bei diesem Plan abweicht."""
        if not it.ov and not it.frame:
            return ""
        es = pp.eff(self.settings(), it)
        parts = []
        if {"scale_mode", "scale_pct", "scale_mm"} & set(it.ov):
            parts.append(pp.scale_text(es))
        if "rotate" in it.ov:
            parts.append("↻ " + tr(ROTATE_TEXT.get(es.rotate, es.rotate)))
        if "frame" in it.ov or it.frame:
            parts.append(tr(KIND_SHORT.get(es.frame, FRAME_TEXT.get(es.frame, es.frame))))
        if "margin_mm" in it.ov:
            parts.append(tr("Rand {0} mm").format(pp.mm_text(es.margin_mm)))
        if {"bleed_mm", "bleed_mode", "bleed_color"} & set(it.ov):
            parts.append(tr("Überfüller {0} mm").format(pp.mm_text(es.bleed_mm)))
        if "material" in it.ov:
            m = pp.material_of(es)
            parts.append(m["name"] if m else tr("Material"))
        if "roll_pick" in it.ov:
            parts.append(tr("Rolle {0}").format(es.roll_pick or tr("automatisch")))
        if "align" in it.ov:
            parts.append(tr(ALIGN_TEXT.get(es.align, es.align)))
        return " · ".join(parts)

    def settings(self) -> pp.PlanSettings:
        hem = "".join(k for k, c in self.chk_hem.items() if c.isChecked())
        return dataclasses.replace(
            self.s0, kind=self.kind, printer=self.printer, color=self.cmb_color.currentData() or "",
            media=self.s0.media, crop_marks=self.chk_marks.isChecked(),
            copies=self.spn_copies.value(),
            collate=self.chk_collate.isChecked(), order=self.cmb_order.currentData() or "list",
            weights=self._weights() if self.kind == "plan" else [], fix_hairlines=self.chk_hair.isChecked(),
            nest=self.chk_nest.isChecked(), gap_mm=self.spn_gap.value(),
            overwidth=self.cmb_over.currentData() or "none", overlap_mm=self.spn_overlap.value(),
            fold_marks=self.chk_fold.isChecked() and self.kind == "plan", hem_mm=self.spn_hem.value(),
            hem_sides=hem, grommet_spacing_mm=self.spn_grom.value(), grommet_inset_mm=self.spn_grom_in.value(),
            cut_contour=self.chk_cut.isChecked(), printcut_marks=self.chk_pcm.isChecked(), rolls=[], dry_run=False,
            split_copies=True, copies_mode=self.cmb_copies.currentData() or "sheets", overrides={},
            **{k: self.g[k] for k in pp.OV_KEYS})

    def _pieces(self, it, s, use):
        return pp.pieces_for(it, self.rolls, s, use, max(1, it.qty) * max(1, s.copies)) if self.rolls else []

    def _refresh(self):
        s = self.settings()
        done = [it for it in self.items if it.area is not None]
        use, wnote = pp.eligible_for(self.rolls, s)
        if self.rolls:
            pp.place_all(done, self.rolls, s)
        else:
            for it in done:
                it.size = pp.finished_size(it.area, s)
                it.fit = None
        self._building = True
        for i, it in enumerate(self.items):
            row = self.tree.topLevelItem(i)
            if row is None:
                continue
            if it.area is None:
                row.setText(1, tr("wird erkannt …"))
                row.setText(2, "")
                row.setText(3, "")
                continue
            kind = tr(KIND_SHORT.get(it.area.kind, it.area.kind))
            row.setText(1, tr("{0} × {1} mm").format(pp.mm_text(round(it.size[0])), pp.mm_text(round(it.size[1])))
                        + f"  ({kind})" + ("  ⚠" if it.hairlines else ""))
            tip = [tr(pp.KIND_TEXT.get(it.area.kind, it.area.kind))]
            if it.area.note:
                tip.append(it.area.note)
            ovt = self._ov_text(it)
            row.setText(0, it.label + (f"  ✎ {ovt}" if ovt else ""))
            row.setToolTip(0, tr("Abweichend von den Einstellungen für alle: {0}").format(ovt) if ovt else "")
            if it.hairlines:
                tip.append(tr("{0} Linie(n) dünner als {1} mm").format(it.hairlines, pp.mm_text(s.hairline_mm)))
            row.setToolTip(1, "\n".join(tip))
            pcs = self._pieces(it, s, use)
            if pcs:
                p0 = pcs[0]
                txt = tr("{0} mm").format(pp.mm_text(p0.width_mm)) + ("  ↻" if p0.rotated else "")
                if len(pcs) > 1:
                    txt += "  " + tr("{0} Bahnen").format(len(pcs))
                if p0.clipped:
                    txt += "  ✂"
                row.setText(2, txt)
                row.setToolTip(2, "\n".join(x for x in (
                    tr("gedreht – quer zur Rolle") if p0.rotated else "",
                    tr("breiter als die Rolle – wird abgeschnitten") if p0.clipped else "",
                    tr("in {0} Bahnen mit Überlappung").format(len(pcs)) if len(pcs) > 1 else "") if x))
                row.setText(3, tr("{0} m").format(pp.num(sum(p.along for p in pcs) / 1000.0)))
                for c in range(4):
                    row.setForeground(c, QBrush())
                if p0.clipped:
                    row.setForeground(2, QBrush(QColor(theme.ACCENT)))
            else:
                row.setText(2, tr("passt nicht") if self.rolls else "–")
                row.setText(3, "")
                if self.rolls:
                    row.setForeground(2, QBrush(QColor(theme.ERROR)))
        self._building = False
        self._lengths(s, done, wnote, use)
        if hasattr(self, "_prev_timer"):
            self._prev_timer.start()

    def _preview(self):
        """Druckseiten so, wie sie zum Drucker gehen: je Blatt ein Bild mit Rolle, Größe, Exemplaren und Schnitt."""
        if getattr(self, "_closed", False):
            return
        self.lst_prev.clear()
        done = [it for it in self.items if it.area is not None and it.qty > 0]
        if not done or not self.rolls:
            self.lbl_prev.setText(tr("Noch nichts zu zeigen.") if not done else tr("Keine Rollen bekannt."))
            return
        s = self.settings()
        try:
            runs = pp.build_runs(done, self.rolls, s)
        except Exception as e:                                  # noqa: BLE001
            self.lbl_prev.setText(str(e))
            return
        mode = pp.copies_mode(s)
        for k, run in enumerate(runs[:PREVIEW_MAX]):
            roll = self.rolls[run.roll] if 0 <= run.roll < len(self.rolls) else None
            n = max(1, run.copies)
            cap = tr("Blatt {0}: {1} × {2} mm").format(k + 1, pp.mm_text(round(run.across)), pp.mm_text(round(run.along)))
            cap += "\n" + (roll.name or roll.slot or tr("{0} mm").format(pp.mm_text(roll.width_mm)) if roll else "")
            if n > 1:
                cap += "  ×" + str(n) + ("" if mode == "count" else " ✂")
            it = QListWidgetItem(QIcon(self._sheet_pixmap(run, s)), cap)
            it.setToolTip("\n".join(p.label for p, _x, _y in run.pieces))
            self.lst_prev.addItem(it)
        total = sum(max(1, r.copies) for r in runs)
        txt = {"sheets": tr("{0} Druckseite(n) · {1} Blatt · ein Auftrag je Druckseite, Schnitt nach jedem Blatt"),
               "jobs": tr("{0} Druckseite(n) · {1} Blatt · je Exemplar ein Auftrag"),
               "count": tr("{0} Druckseite(n) · {1} Blatt · Kopienzahl, Schneiden wie am Gerät eingestellt")}[mode]
        extra = tr(" – Vorschau zeigt die ersten {0}").format(PREVIEW_MAX) if len(runs) > PREVIEW_MAX else ""
        self.lbl_prev.setText(txt.format(len(runs), total) + extra)

    def _sheet_pixmap(self, run, s) -> QPixmap:
        """Druckseite klein gerendert, Rollenbreite grau umrandet, Schnittkante rot."""
        W, H = run.across, run.along
        sc = PREVIEW_PX / max(W, H)
        w, h = max(8, int(W * sc)), max(8, int(H * sc))
        pm = QPixmap(w + 2, h + 2)
        pm.fill(QColor("#ffffff"))
        try:
            doc, _cuts = pp.make_run(run, s)
            try:
                page = doc[0]
                bm = page.render(scale=sc / pp.MM, may_draw_forms=True)
                arr = bm.to_numpy()
                page.close()
            finally:
                doc.close()
            import numpy as np
            if arr.ndim == 2:
                arr = np.stack([arr] * 3, axis=2)
            arr = np.ascontiguousarray(arr[..., :3][..., ::-1]) if arr.shape[2] >= 3 else arr
            img = QImage(arr.data, arr.shape[1], arr.shape[0], arr.strides[0], QImage.Format.Format_RGB888).copy()
            p = QPainter(pm)
            p.drawImage(1, 1, img.scaled(w, h))
        except Exception:                                       # noqa: BLE001 – Vorschau darf nie stören
            p = QPainter(pm)
        p.setPen(QPen(QColor("#999999"), 1))
        p.drawRect(0, 0, w + 1, h + 1)
        p.setPen(QPen(QColor(theme.ERROR), 2, Qt.PenStyle.DashLine))
        p.drawLine(0, h + 1, w + 1, h + 1)                       # Schnitt am Blattende
        p.end()
        return pm

    def _lengths(self, s, done, wnote, use=None):
        lens = pp.lengths(done, self.rolls, s) if self.rolls else []
        by = {d["roll"]: d for d in lens}
        cp = max(1, s.copies)
        rows = []
        for i, r in enumerate(self.rolls):
            d = by.get(i)
            head = f"<b>{pp.mm_text(r.width_mm)} mm</b>"
            sub = " · ".join(x for x in (r.name, f"{r.weight} g" if r.weight else "", r.media) if x)
            if d is None:
                val = "–"
            else:
                val = f"<b>{pp.num(d['single_m'])} m</b>"
                if cp > 1:
                    val += f" &nbsp; ×{cp} = <b>{pp.num(d['total_m'])} m</b>"
                val += " &nbsp; <span style='color:%s'>(%s)</span>" % (theme.MUTED, tr("{0} Plan/Pläne").format(d["plans"]))
                if d.get("short"):
                    val += " <span style='color:%s'>%s</span>" % (theme.ERROR, tr("reicht nicht!"))
            if r.remaining_m is not None:
                sub += (" · " if sub else "") + tr("~{0} m Rest").format(pp.mm_text(r.remaining_m))
            rows.append(f"<tr><td>{head}</td><td style='color:{theme.MUTED}'>&nbsp;{sub}&nbsp;</td>"
                        f"<td align='right'>{val}</td></tr>")
        if len(lens) > 1:
            tot = sum(d["single_m"] for d in lens)
            tot_all = sum(d["total_m"] for d in lens)
            val = f"<b>{pp.num(tot)} m</b>" + (f" &nbsp; ×{cp} = <b>{pp.num(tot_all)} m</b>" if cp > 1 else "")
            rows.append(f"<tr><td colspan='2'>{tr('Gesamt')}</td><td align='right'>{val}</td></tr>")
        self.lbl_len.setText("<table width='100%'>" + "".join(rows) + "</table>" if rows else
                             tr("Noch keine Rollen – „Rollen …“ oder Gerät abfragen."))
        warn = []
        if wnote:
            warn.append(wnote)
        if s.cut_sheets and self.caps is not None and not pp.is_folder(self.printer) and not pp.cut_values(self.caps):
            warn.append(tr("Der Drucker bietet keine Schneid-Option an – ob nach jedem Blatt geschnitten wird, "
                           "entscheidet die Einstellung am Gerät."))
        k = pp.find_roll(self.rolls, s.roll_pick)
        if k is not None and not pp.is_folder(self.printer):
            r = self.rolls[k]
            if not r.slot:
                mv = pp.media_for_roll(self.caps, r) if self.caps is not None else ""
                warn.append(tr("Der Treiber bietet keine Rollenwahl – das Gerät nimmt die Rolle nach Breite und "
                               "Medientyp.") + (" " + tr("Medientyp laut Rolle wird mitgeschickt.") if mv else
                                                 " " + tr("Medientyp passend zur Rolle einstellen.")))
            mat = pp.material_of(s)
            if mat and mat.get("weight") and r.weight and int(mat["weight"]) != r.weight:
                warn.append(tr("Material ({0} g) passt nicht zur gewählten Rolle ({1} g).")
                            .format(mat["weight"], r.weight))
        use = use if use is not None else self.rolls
        unfit = [it.label for it in done if self.rolls and not self._pieces(it, s, use)]
        if unfit:
            warn.append(tr("Passt auf keine Rolle: {0}").format(", ".join(unfit[:5]) + (" …" if len(unfit) > 5 else "")))
        hl = sum(it.hairlines for it in done)
        if hl and not s.fix_hairlines:
            warn.append(tr("{0} Linie(n) dünner als {1} mm – „Haarlinien anheben“ verstärkt sie.")
                        .format(hl, pp.mm_text(s.hairline_mm)))
        from .. import printmat
        warn += printmat.notes(pp.material_of(s), self.session.cfg)
        self.lbl_warn.setText("\n".join(warn))
        printable = any(self._pieces(it, s, use) and it.qty > 0 for it in done) if self.rolls else False
        ready = bool(self.printer and printable and not self._queue)
        self.btn_print.setEnabled(ready)
        self.btn_pdf.setEnabled(bool(printable and not self._queue))

    # ------------------------------------------------------------------ #
    # Material und Ordner
    # ------------------------------------------------------------------ #
    def _fill_materials(self):
        from .. import printmat
        cat = "plan" if self.kind == "plan" else "quality"
        g = getattr(self, "g", None)
        cur = g["material"] if g is not None else self.s0.material
        if not cur and self.printer:
            cur = printmat.default_for(self.printer, cat)
            if g is not None and cur:
                g["material"] = cur
        self.cmb_mat.blockSignals(True)
        self.cmb_mat.clear()
        self.cmb_mat.addItem(tr("– keins –"), "")
        # was der Drucker meldet (Medien der geladenen Rollen) – ohne es extra anlegen zu müssen
        rs = getattr(self, "roll_state", None)
        for m in pp.device_materials(getattr(self, "rolls", []) or [], getattr(rs, "catalog", None)):
            self.cmb_mat.addItem(m["name"] + (f" · {m['weight']} g" if m["weight"] and f"{m['weight']} g"
                                              not in m["name"] else "")
                                 + "  (" + (tr("Gerät") if m["loaded"] else tr("Gerät, nicht geladen")) + ")", m["id"])
        for m in printmat.for_printer(self.printer, cat) + [m for m in printmat.for_printer(self.printer)
                                                            if m["category"] != cat]:
            t = m["name"] + (f" · {m['weight']} g" if m["weight"] else "")
            if m["category"] != cat:
                t += "  (" + tr(CAT_TEXT[m["category"]]) + ")"
            self.cmb_mat.addItem(t, m["id"])
        if cur and self.cmb_mat.findData(cur) < 0 and cur.startswith(pp.DEV_PREFIX):
            self.cmb_mat.addItem(pp.material_of(dataclasses.replace(self.s0, material=cur))["name"]
                                 + "  (" + tr("nicht geladen") + ")", cur)
        i = self.cmb_mat.findData(cur or "")
        self.cmb_mat.setCurrentIndex(max(0, i))
        self.cmb_mat.blockSignals(False)

    def _edit_materials(self):
        if MaterialsDialog(self, self.session, self.printer, self.caps).exec():
            self._fill_materials()
            self._refresh()

    def _edit_folders(self):
        if FoldersDialog(self).exec():
            cur = self.printer
            self.cmb_printer.blockSignals(True)
            self.cmb_printer.clear()
            self._fill_printers()
            i = self.cmb_printer.findData(cur)
            if i >= 0:
                self.cmb_printer.setCurrentIndex(i)
            self.cmb_printer.blockSignals(False)
            self._printer_changed()

    # ------------------------------------------------------------------ #
    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self._bleed_color), self, tr("Farbe des Überfüllers"))
        if c.isValid():
            self._bleed_color = c.name()
            self._color_button()
            self._set_field({"bleed_color": c.name()})

    def _color_button(self):
        self.btn_bcolor.setStyleSheet(f"background: {self._bleed_color};")
        self.btn_bcolor.setEnabled(self.cmb_bleed.currentData() == "color")

    def _save_pdf(self):
        s = self.settings()
        out, _ = QFileDialog.getSaveFileName(self, tr("Als PDF speichern"),
                                             os.path.join(os.path.expanduser("~"), (tr("Plaene_Druck") if self.kind
                                                          == "plan" else tr("Poster_Druck")) + ".pdf"),
                                             tr("PDF-Dateien (*.pdf)"))
        if not out:
            return
        if not out.lower().endswith(".pdf"):
            out += ".pdf"
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            n = pp.save_pdf([it for it in self.items if it.area is not None], self.rolls, s, out)
        except Exception as e:                                  # noqa: BLE001
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, tr("Speichern"), str(e))
            return
        QApplication.restoreOverrideCursor()
        self.lbl_state.setText(tr("{0} Seite(n) gespeichert: {1}").format(n, out))

    def _print(self):
        s = self.settings()
        items = [it for it in self.items if it.area is not None]
        use, _n = pp.eligible_for(self.rolls, s)
        unfit = [it for it in items if it.qty > 0 and not self._pieces(it, s, use)]
        if unfit and QMessageBox.question(
                self, tr("Plandruck"), tr("{0} Plan/Pläne passen auf keine Rolle und werden ausgelassen. "
                                          "Trotzdem drucken?").format(len(unfit))) != QMessageBox.StandardButton.Yes:
            return
        short = [d for d in pp.lengths(items, self.rolls, s) if d.get("short")]
        if short and QMessageBox.question(
                self, tr("Plandruck"), tr("Laut Gerät reicht die Rolle {0} mm nicht. Trotzdem drucken?").format(
                    pp.mm_text(short[0]["width_mm"]))) != QMessageBox.StandardButton.Yes:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        def prog(done, total, text=""):
            self.lbl_state.setText(tr("Sende {0} von {1}: {2}").format(done + 1 if done < total else total, total,
                                                                        text))
            QApplication.processEvents()
        try:
            info = pp.print_items(self.session, self.printer, items, self.rolls, s, prog)
        except Exception as e:                                  # noqa: BLE001
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, tr("Druckfehler"), str(e))
            return
        QApplication.restoreOverrideCursor()
        save_settings(s, self.printer)
        msg = tr("{0} Plan-Auftrag/-Aufträge an {1} gesendet – {2} m").format(
            len(info["jobs"]), self.printer, pp.num(info["total_m"]))
        self.printed.emit(msg)
        self.accept()

    def _cleanup(self, r):
        """Nach dem Schließen: Einstellungen merken, selbst geöffnete Dokumente freigeben."""
        if r != QDialog.DialogCode.Accepted and r != 1:
            save_settings(self.settings(), self.printer)
        self._timer.stop()
        self._closed = True
        for d in self.owned:
            try:
                d.close()
            except Exception:
                pass
        self.owned = []
