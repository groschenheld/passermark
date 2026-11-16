# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Setup dialogs of plan and poster printing: rolls loaded in the printer (also read from the device), the printer's materials, and the folders for saved jobs."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .. import planprint as pp
from .. import rolls as rl
from ..l10n import tr
from . import lastdir
from . import theme
from .common import MsgBox, make_responsive
from .icons import icon
from .plantexts import (
    CAT_TEXT,
    COLOR_MODE_TEXT,
    ORIGIN_TEXT,
    SOURCE_TEXT,
)

_RUNNING: set = set()  # running device queries (survive closing the window)


def start_query(host: str, receiver, tag: str = "", fn=None):
    """Query the device in the background. receiver = bound method of a window (it is then called in the main
    thread and disconnected automatically if the window is already closed): receiver(RollState, tag).
    """
    for old in [t for t in _RUNNING if t.isFinished()]:
        _RUNNING.discard(old)
    q = _RollQuery(host, tag, fn)
    _RUNNING.add(q)
    q.done.connect(receiver)
    q.start()
    return q


class _RollQuery(QThread):
    """Query the device (network only – no pdfium) without stopping the interface."""

    done = Signal(object, str)

    def __init__(self, host: str, tag: str = "", fn=None):
        super().__init__()
        self.host, self.tag, self.fn = host, tag, fn or (lambda h: rl.query(h, force=True))

    def run(self):
        try:
            st = self.fn(self.host)
        except Exception as e:  # noqa: BLE001
            st = rl.RollState([], "none", str(e), self.host)
        self.done.emit(st, self.tag)


# --------------------------------------------------------------------------- #
# rolls entered by hand
# --------------------------------------------------------------------------- #
class RollsDialog(QDialog):
    """Rolls of the printer: what the device reports and those entered by hand (per user, no admin rights)."""

    def __init__(self, parent, session, printer: str):
        super().__init__(parent)
        self.setWindowTitle(tr("Rollen – {0}").format(printer))
        self.session, self.printer = session, printer
        self.caps = None
        try:
            self.caps = session.caps_for(printer)
        except Exception:  # noqa: BLE001 – printer not reachable: no driver values
            self.caps = None
        self._q = None
        v = QVBoxLayout(self)
        t = QLabel(
            tr(
                "Passermark liest die geladenen Rollen direkt vom Gerät (IPP, sonst SNMP). Meldet das Gerät "
                "nichts, gelten die hier eingetragenen Rollen. Die Zufuhr ist der Wert im Treiber."
            )
        )
        t.setWordWrap(True)
        v.addWidget(t)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Geräteadresse:")))
        self.ed_host = QLineEdit(rl.host_for(session, printer))
        self.ed_host.setPlaceholderText(tr("IP-Adresse oder Name, z. B. 10.30.4.73"))
        self.ed_host.setToolTip(
            tr(
                "Wird aus dem Anschluss ermittelt; geht das nicht (WSD, Druckserver), hier "
                "eintragen – gilt nur für dich"
            )
        )
        row.addWidget(self.ed_host, 1)
        self.btn_query = QPushButton(tr("Vom Gerät lesen"))
        self.btn_query.clicked.connect(self._query)
        row.addWidget(self.btn_query)
        self.btn_probe = QPushButton(icon("check"), tr("Gerät prüfen …"))
        self.btn_probe.setToolTip(
            tr("Alles abfragen, was das Gerät über IPP/SNMP meldet – Bericht zum Speichern und Weitergeben")
        )
        self.btn_probe.clicked.connect(self._probe)
        row.addWidget(self.btn_probe)
        v.addLayout(row)
        self.lbl_dev = MsgBox(5)
        v.addWidget(self.lbl_dev)
        self.tbl = QTableWidget(0, 5)
        self.tbl.setHorizontalHeaderLabels(
            [tr("Breite (mm)"), tr("Zufuhr im Treiber"), tr("g/m²"), tr("Name"), tr("Material")]
        )
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
            rl.set_user_host(self.printer, "" if host == auto else host)  # remember only what differs
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
        self._q = start_query(host, self._queried, "", fn)

    def _probe(self):
        host = self._save_host()
        if not host:
            self.lbl_dev.setText(tr("Keine Geräteadresse – oben die IP-Adresse des Geräts eintragen."))
            return
        from .. import probe

        self.btn_probe.setEnabled(False)
        self.lbl_dev.setText(tr("Prüfe {0} … (bis zu einer Minute)").format(host))
        printer = self.printer
        self._q = start_query(host, self._probed, "", lambda h: probe.run(h, printer))

    def _probed(self, rep, _tag=""):
        from .. import probe

        self.btn_probe.setEnabled(True)
        if not isinstance(rep, dict):  # error in the thread: RollState with a message
            self.lbl_dev.setText(getattr(rep, "error", "") or tr("Prüfung fehlgeschlagen"))
            return
        ProbeDialog(self, rep).exec()
        r = rep.get("rolls") or {}
        if r.get("rolls"):
            self._queried(
                rl.RollState([rl.Roll.from_dict(x) for x in r["rolls"]], r.get("origin", ""), "", rep.get("host", ""))
            )
        else:
            self.lbl_dev.setText(probe.text(rep).splitlines()[-1])

    def _queried(self, st, _tag=""):
        self.btn_query.setEnabled(True)
        self.live = list(st.rolls)
        for i, r in enumerate(self.live):
            r.slot = r.slot or (rl.slot_for(self.caps, r.device or r.name, i) if self.caps else "")
        if st.rolls:
            self.lbl_dev.setText(
                tr("Gerät {0} meldet {1}:").format(st.host, tr(ORIGIN_TEXT.get(st.origin, st.origin)))
                + "<br>"
                + "<br>".join(r.label() for r in st.rolls)
            )
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
# plan printing
# --------------------------------------------------------------------------- #
class ProbeDialog(QDialog):
    """Result of the device check: short version, the full report can be saved (JSON)."""

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

        out, _ = lastdir.getSaveFileName(
            self,
            tr("Bericht speichern"),
            os.path.join(os.path.expanduser("~"), probe.default_name(self.rep)),
            "JSON (*.json)",
        )
        if out:
            try:
                probe.save(self.rep, out)
            except OSError as e:
                QMessageBox.critical(self, tr("Bericht speichern"), str(e))


class MaterialsDialog(QDialog):
    """Print materials: main category (plan printing/quality printing), then the settings per material."""

    COLS = (
        "Name",
        "Kategorie",
        "g/m²",
        "Medientyp",
        "Qualität",
        "Tintenmenge",
        "Profil",
        "Farbe",
        "max. Farbauftrag",
        "nur für diesen Drucker",
        "Quelle",
        "geprüft",
    )
    C_COLOR, C_TAC, C_PRN, C_SRC, C_OK = 7, 8, 9, 10, 11

    def __init__(self, parent, session, printer: str, caps, device: list | None = None):
        super().__init__(parent)
        from .. import printmat

        self.setWindowTitle(tr("Materialien – {0}").format(printer or tr("alle Drucker")))
        self.session, self.printer, self.caps = session, printer, caps
        self.others = [m for m in printmat.load() if m["printer"] and m["printer"] != printer]
        v = QVBoxLayout(self)
        t = QLabel(
            tr(
                "Zuerst die Kategorie (Plandruck = Produktionsdruck, Qualitätsdruck = Poster, Foto, PVC …), "
                "dann je Material: Grammatur (wählt die Rolle), Medientyp und Qualität im Treiber, Tintenmenge "
                "(falls der Treiber sie anbietet) und das Farbprofil – sein Farbauftrag ist die echte Grenze. "
                "„max. Farbauftrag“ ist der Richtwert, gegen den Passermark warnt."
            )
        )
        t.setWordWrap(True)
        v.addWidget(t)
        self.tbl = QTableWidget(0, len(self.COLS))
        self.tbl.setHorizontalHeaderLabels([tr(c) for c in self.COLS])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        v.addWidget(self.tbl, 1)
        self.ids = []
        self.orig = []  # per row the stored material (fields without a column of their own)
        self.device = list(device or [])
        row = QHBoxLayout()
        b = QPushButton(icon("insert"), tr("Material hinzufügen"))
        b.clicked.connect(lambda: self._add({"name": tr("Neues Material"), "category": "quality"}))
        row.addWidget(b)
        b = QPushButton(icon("delete"), tr("Entfernen"))
        b.clicked.connect(self._remove)
        row.addWidget(b)
        b = QPushButton(tr("Vom Gerät übernehmen"))
        b.setToolTip(
            tr(
                "Die Medien, die das Gerät meldet (geladen und im Katalog), als Materialien anlegen – "
                "ungeprüft, bis du sie abhakst"
            )
        )
        b.setEnabled(bool(self.device))
        b.clicked.connect(self._from_device)
        row.addWidget(b)
        b = QPushButton(icon("open"), tr("Importieren …"))
        b.setToolTip(
            tr(
                "Materialliste aus CSV oder JSON (z. B. Export aus dem RIP): Spalten wie Name/Material, "
                "Grammatur/gsm, Medientyp, Qualität, Profil werden erkannt"
            )
        )
        b.clicked.connect(self._import)
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
        from .. import printmat

        n = self.tbl.rowCount()
        self.tbl.insertRow(n)
        self.ids.append(m.get("id", ""))
        self.orig.append(dict(m))
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
        if pc.findData(m.get("profile", "")) < 0 and m.get("profile"):
            pc.addItem(tr("{0} (nicht vorhanden)").format(m["profile"]), m["profile"])
            pc.setCurrentIndex(pc.count() - 1)
        self.tbl.setCellWidget(n, 6, pc)
        cc = QComboBox()
        for k, txt in COLOR_MODE_TEXT.items():
            cc.addItem(tr(txt), k)
        cc.setToolTip(
            tr(
                "Umwandeln: Passermark rechnet ins Profil um, das Gerät soll nicht mehr umrechnen (am "
                "sichersten).\nNur einbetten: das Profil geht als Output Intent mit, das Gerät/der RIP wendet "
                "es an.\nNichts: unverändert senden, die Farbe macht ganz das Gerät."
            )
        )
        cc.setCurrentIndex(max(0, cc.findData(m.get("color_mode", "convert"))))
        self.tbl.setCellWidget(n, self.C_COLOR, cc)
        t = QSpinBox()
        t.setRange(0, 400)
        t.setSuffix(" %")
        t.setSpecialValueText("–")
        t.setValue(int(m.get("tac") or 0))
        self.tbl.setCellWidget(n, self.C_TAC, t)
        ck = QCheckBox()
        ck.setChecked(bool(m.get("printer")) or not m.get("id"))
        self.tbl.setCellWidget(n, self.C_PRN, ck)
        src = m.get("source", "hand")
        it = QTableWidgetItem(tr(SOURCE_TEXT.get(src, src)) + (f" · {m['updated']}" if m.get("updated") else ""))
        it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.tbl.setItem(n, self.C_SRC, it)
        ok = QCheckBox()
        ok.setChecked(bool(m.get("checked", src == "hand")))
        ok.setToolTip(tr("Abhaken, wenn die Einstellungen geprüft sind (vom Gerät bzw. importiert: anfangs ungeprüft)"))
        self.tbl.setCellWidget(n, self.C_OK, ok)

    def _remove(self):
        for i in sorted({ix.row() for ix in self.tbl.selectedIndexes()}, reverse=True):
            self.tbl.removeRow(i)
            self.ids.pop(i)
            self.orig.pop(i)
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
            o = self.orig[i]
            out.append(
                {
                    **{k: o[k] for k in ("options", "intent", "notes", "cut_force", "cut_speed", "updated") if k in o},
                    "source": o.get("source", "hand"),
                    "checked": self.tbl.cellWidget(i, self.C_OK).isChecked(),
                    "color_mode": self.tbl.cellWidget(i, self.C_COLOR).currentData() or "convert",
                    "id": mid,
                    "name": name,
                    "category": self.tbl.cellWidget(i, 1).currentData(),
                    "weight": self.tbl.cellWidget(i, 2).value(),
                    "media": self.tbl.cellWidget(i, 3).currentData(),
                    "quality": self.tbl.cellWidget(i, 4).currentData(),
                    "density_key": (dc.property("density_key") or "") if dc.currentData() else "",
                    "density": dc.currentData() or "",
                    "profile": self.tbl.cellWidget(i, 6).currentData(),
                    "tac": self.tbl.cellWidget(i, self.C_TAC).value(),
                    "printer": self.printer if self.tbl.cellWidget(i, self.C_PRN).isChecked() else "",
                }
            )
        return out

    def _names(self) -> set:
        return {
            (self.tbl.item(i, 0).text() if self.tbl.item(i, 0) else "").strip().lower()
            for i in range(self.tbl.rowCount())
        }

    def _add_new(self, mats: list) -> int:
        have, n = self._names(), 0
        for m in mats:
            if m["name"].strip().lower() in have:
                continue
            have.add(m["name"].strip().lower())
            self._add(m)
            n += 1
        self._fill_defaults()
        return n

    def _from_device(self):
        from .. import printmat

        n = self._add_new(printmat.from_device(self.device, self.printer))
        QMessageBox.information(
            self,
            tr("Materialien"),
            tr("{0} Material(ien) vom Gerät übernommen – ungeprüft. Einstellungen ansehen, abhaken, speichern.").format(
                n
            )
            if n
            else tr("Alle gemeldeten Medien sind schon angelegt."),
        )

    def _import(self):
        from .. import printmat

        path, _ = lastdir.getOpenFileName(
            self,
            tr("Materialliste importieren"),
            os.path.expanduser("~"),
            tr("Materiallisten (*.csv *.txt *.json);;Alle Dateien (*)"),
        )
        if not path:
            return
        try:
            mats = printmat.parse_import(path, self.printer)
        except Exception as e:  # noqa: BLE001 – jede Ursache melden
            QMessageBox.warning(self, tr("Materialien"), tr("Import nicht möglich: {0}").format(e))
            return
        n = self._add_new(mats)
        QMessageBox.information(
            self,
            tr("Materialien"),
            tr(
                "{0} von {1} Material(ien) übernommen (gleiche Namen "
                "übersprungen) – ungeprüft. Ansehen, abhaken, speichern."
            ).format(n, len(mats)),
        )

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
    """Output folders (hot folders): print pages end up there as PDF – e.g. VersaWorks for Roland printers."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(tr("Ausgabe-Ordner"))
        v = QVBoxLayout(self)
        t = QLabel(
            tr(
                "Für Geräte ohne Druckertreiber (Roland über VersaWorks, andere RIPs): jede Druckseite wird als "
                "PDF in den Ordner gelegt – mit CutContour, falls eingeschaltet. Der Ordner erscheint dann wie "
                "ein Drucker; Rollen dafür unter „Rollen …“ eintragen."
            )
        )
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
        b.clicked.connect(
            lambda: [
                self.tbl.removeRow(i) for i in sorted({ix.row() for ix in self.tbl.selectedIndexes()}, reverse=True)
            ]
        )
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

        bad = [
            self.tbl.item(i, 1).text()
            for i in range(self.tbl.rowCount())
            if self.tbl.item(i, 1) and shared.in_home(self.tbl.item(i, 1).text())
        ]
        self.lbl_home.setText(shared.home_hint() if bad else "")

    def _row(self, name, d):
        n = self.tbl.rowCount()
        self.tbl.insertRow(n)
        self.tbl.setItem(n, 0, QTableWidgetItem(name))
        self.tbl.setItem(n, 1, QTableWidgetItem(d))

    def _add_dir(self):
        from .. import shared

        d = lastdir.getExistingDirectory(self, tr("Ausgabe-Ordner wählen"), shared.hotfolder_dir())
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
