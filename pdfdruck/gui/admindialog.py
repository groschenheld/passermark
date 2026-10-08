# SPDX-License-Identifier: GPL-3.0-or-later
# pdfToolkit – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Verwaltung der Standards – speichert über pkexec + Helper (eine Passwortabfrage)."""
from __future__ import annotations

from ..l10n import tr

import copy
import json
import os
import re
import subprocess
import tempfile

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from .. import colorconv, config, i18n, layout, printers
from .. import platform as _platform
from . import theme
from .common import Session, fill_combo, fit_width, guard_wheel


def _helper_cmd() -> list:
    """Root-Helfer: installiert (install.sh) bzw. – im AppImage – das AppImage selbst als root (pkexec)."""
    appimage = os.environ.get("APPIMAGE")
    if not os.path.exists(config.HELPER) and appimage:
        return ["pkexec", "env", "APPIMAGE_EXTRACT_AND_RUN=1", appimage, "--admin-helper"]
    return ["pkexec", config.HELPER]


def _scroll(widget):
    """Reiter-Inhalt scrollbar machen (kleine Bildschirme, Windows-Skalierung)."""
    from PySide6.QtWidgets import QFrame, QScrollArea
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.Shape.NoFrame)
    sa.setWidget(widget)
    return sa


def _fit_screen(dlg, want_w: int, want_h: int):
    """Fenstergröße auf den verfügbaren Bildschirm begrenzen (Taskleiste/Skalierung berücksichtigt)."""
    from PySide6.QtGui import QGuiApplication
    scr = dlg.screen() if hasattr(dlg, "screen") and dlg.screen() else QGuiApplication.primaryScreen()
    if scr is None:
        dlg.resize(want_w, want_h)
        return
    av = scr.availableGeometry()
    w = min(want_w, int(av.width() * 0.96))
    h = min(want_h, int(av.height() * 0.90))
    dlg.resize(w, h)
    dlg.move(av.x() + (av.width() - w) // 2, av.y() + max(0, (av.height() - h) // 2))


class AdminDialog(QDialog):
    def __init__(self, parent, session: Session):
        super().__init__(parent)
        self.setWindowTitle(tr("Verwaltung – Standardeinstellungen (Admin)"))
        self.s = session
        self.cfg = copy.deepcopy(session.cfg)
        self.queue_changes: dict[tuple[str, str], str] = {}
        self.touched: set[str] = set()          # Drucker, deren Standards geändert wurden
        self.new_icc: dict[str, str] = {}       # id -> Quelldatei
        self.removed_icc: set[str] = set()
        try:
            self.plist = printers.list_printers()
        except Exception as e:
            QMessageBox.critical(self, tr("CUPS"), str(e))
            self.plist = []

        v = QVBoxLayout(self)
        note = QLabel(tr("Änderungen hier sind die Standards für alle Benutzer. Speichern erfordert "
                      "Administratorrechte (Polkit). Benutzer können im Druckdialog abweichen – "
                      "nach Programmende gelten wieder diese Standards."))
        note.setWordWrap(True)
        v.addWidget(note)
        tabs = QTabWidget()
        v.addWidget(tabs, 1)
        tabs.addTab(_scroll(self._tab_general()), tr("Allgemein"))
        tabs.addTab(_scroll(self._tab_printers()), tr("Druckerstandards"))
        tabs.addTab(_scroll(self._tab_profiles()), tr("Farbprofile"))
        fit_width(self)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        _fit_screen(self, 900, 700)        # nie größer als der Bildschirm; der Rest scrollt

    # ================================================================== #
    def _tab_general(self):
        w = QWidget()
        f = QFormLayout(w)
        self.cmb_default = QComboBox()
        fill_combo(self.cmb_default, [("", tr("(CUPS-Standarddrucker)"))] + [(p.name, p.name) for p in self.plist],
                   self.cfg.get("default_printer", ""))
        f.addRow(tr("Standarddrucker:"), self.cmb_default)
        self.chk_user_prof = QCheckBox(tr("Benutzer dürfen Farbprofil/Intent im Druckdialog wählen"))
        self.chk_user_prof.setChecked(bool(self.cfg.get("allow_user_profile_choice", True)))
        f.addRow("", self.chk_user_prof)
        self.spn_imgdpi = QSpinBox()
        self.spn_imgdpi.setRange(10, 2400)
        self.spn_imgdpi.setSuffix(tr(" dpi"))
        self.spn_imgdpi.setValue(int(self.cfg.get("image_default_dpi", 96)))
        self.spn_imgdpi.setToolTip(tr("Gilt nur für Bilder ohne eigene Auflösungsangabe"))
        f.addRow(tr("Bilder ohne DPI-Angabe:"), self.spn_imgdpi)
        from .. import convert
        self.cmb_conv = QComboBox()
        fill_combo(self.cmb_conv, list(convert.CONVERTERS.items()), self.cfg.get("office_converter", "auto"))
        f.addRow(tr("Office → PDF mit:"), self.cmb_conv)
        from .. import l10n
        self.cmb_lang = QComboBox()
        self.cmb_lang.addItem(tr("Systemsprache"), "")
        for code, name in l10n.LANGS.items():
            self.cmb_lang.addItem(name, code)
        self.cmb_lang.setCurrentIndex(max(0, self.cmb_lang.findData(self.cfg.get("language", ""))))
        self.cmb_lang.setToolTip(tr("Gilt für alle Benutzer, die unter Datei → Einstellungen „Automatisch“ gewählt haben"))
        f.addRow(tr("Standardsprache:"), self.cmb_lang)
        lbl = QLabel(convert.describe_available() + tr(". Fällt ein Konverter aus, wird automatisch der nächste "
                     "verwendet. OnlyOffice/Euro-Office werden über ihren internen Konverter angesprochen."))
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {theme.MUTED};")
        f.addRow("", lbl)

        L = self.cfg["layout"]
        self.l_handling = QComboBox()
        fill_combo(self.l_handling, [("size", tr("Größe")), ("multiple", tr("Mehrere Seiten pro Blatt")),
                                     ("booklet", tr("Broschüre")), ("poster", tr("Poster"))], L.get("handling", "size"))
        f.addRow(tr("Seitenhandhabung:"), self.l_handling)
        self.l_mode = QComboBox()
        fill_combo(self.l_mode, [("fit", tr("Anpassen")), ("actual", tr("Tatsächliche Größe")),
                                 ("shrink", tr("Übergroße Seiten verkleinern")), ("custom", tr("Benutzerdefiniert"))], L["mode"])
        f.addRow(tr("Skalierung:"), self.l_mode)
        self.l_custom = QDoubleSpinBox()
        self.l_custom.setRange(1, 1000)
        self.l_custom.setSuffix(" %")
        self.l_custom.setValue(L["custom_percent"])
        f.addRow(tr("Benutzerdef. Maßstab:"), self.l_custom)
        row = QHBoxLayout()
        self.l_nup = QComboBox()
        fill_combo(self.l_nup, [(1, tr("Aus (1)"))] + [(n, str(n)) for n in (2, 4, 6, 8, 9, 16)] +
                   [(0, tr("Benutzerdefiniert"))], 0 if (L["cols"] and L["rows"]) else L["nup"])
        self.l_cols = QSpinBox()
        self.l_cols.setRange(1, 16)
        self.l_cols.setValue(L["cols"] or 2)
        self.l_rows = QSpinBox()
        self.l_rows.setRange(1, 16)
        self.l_rows.setValue(L["rows"] or 2)
        row.addWidget(self.l_nup)
        row.addWidget(self.l_cols)
        row.addWidget(QLabel("×"))
        row.addWidget(self.l_rows)
        f.addRow(tr("Seiten pro Blatt:"), row)
        self.l_order = QComboBox()
        fill_combo(self.l_order, list(layout.ORDERS.items()), L["order"])
        f.addRow(tr("Reihenfolge:"), self.l_order)
        self.l_tile = QComboBox()
        fill_combo(self.l_tile, [("fit", tr("An Kachel anpassen")), ("actual", tr("Tatsächliche Größe")),
                                 ("custom", tr("Benutzerdefiniert"))], L["tile_mode"])
        f.addRow(tr("Kachel-Skalierung:"), self.l_tile)
        self.l_tilepct = QDoubleSpinBox()
        self.l_tilepct.setRange(1, 1000)
        self.l_tilepct.setSuffix(" %")
        self.l_tilepct.setValue(L["tile_percent"])
        f.addRow(tr("Kachel-Maßstab:"), self.l_tilepct)
        self.l_gap = QDoubleSpinBox()
        self.l_gap.setRange(0, 50)
        self.l_gap.setSuffix(tr(" mm"))
        self.l_gap.setValue(L["gap_mm"])
        f.addRow(tr("Abstand:"), self.l_gap)
        self.l_orient = QComboBox()
        fill_combo(self.l_orient, [("auto", tr("Automatisch")), ("portrait", tr("Hochformat")),
                                   ("landscape", tr("Querformat"))], L["orientation"])
        f.addRow(tr("Ausrichtung:"), self.l_orient)
        self.l_checks = {}
        for k, t in [("borders", tr("Seitenrand drucken (N-Up)")), ("autorotate", tr("Seiten automatisch drehen")),
                     ("center", tr("Zentrieren")), ("use_margins", tr("Druckerränder berücksichtigen"))]:
            c = QCheckBox(t)
            c.setChecked(bool(L[k]))
            self.l_checks[k] = c
            f.addRow("", c)
        self.l_binding = QComboBox()
        fill_combo(self.l_binding, [("left", tr("Links")), ("right", tr("Rechts"))], L.get("booklet_binding", "left"))
        f.addRow(tr("Broschüre – Bindung:"), self.l_binding)
        self.l_overlap = QDoubleSpinBox()
        self.l_overlap.setRange(0, 50)
        self.l_overlap.setSuffix(tr(" mm"))
        self.l_overlap.setValue(L.get("poster_overlap_mm", 10.0))
        f.addRow(tr("Poster – Überlappung:"), self.l_overlap)
        for k, t in [("poster_marks", tr("Poster – Schnitt-/Klebelinien")), ("poster_labels", tr("Poster – Beschriftung"))]:
            c = QCheckBox(t)
            c.setChecked(bool(L.get(k, True)))
            self.l_checks[k] = c
            f.addRow("", c)
        return w

    def _collect_general(self):
        self.cfg["default_printer"] = self.cmb_default.currentData() or ""
        self.cfg["allow_user_profile_choice"] = self.chk_user_prof.isChecked()
        self.cfg["image_default_dpi"] = self.spn_imgdpi.value()
        self.cfg["office_converter"] = self.cmb_conv.currentData()
        self.cfg["language"] = self.cmb_lang.currentData() or ""
        n = self.l_nup.currentData()
        L = dict(self.cfg["layout"])     # übrige Felder (Poster/Broschüre) erhalten
        L.update({
            "mode": self.l_mode.currentData(), "custom_percent": self.l_custom.value(),
            "nup": 1 if n == 0 else n,
            "cols": self.l_cols.value() if n == 0 else 0, "rows": self.l_rows.value() if n == 0 else 0,
            "order": self.l_order.currentData(), "tile_mode": self.l_tile.currentData(),
            "tile_percent": self.l_tilepct.value(), "gap_mm": self.l_gap.value(),
            "orientation": self.l_orient.currentData(),
            "handling": self.l_handling.currentData(),
            "booklet_binding": self.l_binding.currentData(),
            "poster_overlap_mm": self.l_overlap.value(),
        })
        L.update({k: c.isChecked() for k, c in self.l_checks.items()})
        self.cfg["layout"] = L

    # ================================================================== #
    def _tab_printers(self):
        w = QWidget()
        v = QVBoxLayout(w)
        row = QHBoxLayout()
        self.cmb_p = QComboBox()
        for p in self.plist:
            label = p.name + (f"  –  {p.model}" if p.model else "") + (tr("  (CUPS-Standard)") if p.is_default else "")
            self.cmb_p.addItem(label, p.name)
        row.addWidget(QLabel(tr("Drucker:")))
        row.addWidget(self.cmb_p, 1)
        btn_reset = QPushButton(tr("Auf Treiber-Standard zurücksetzen"))
        btn_reset.clicked.connect(self._reset_printer)
        row.addWidget(btn_reset)
        v.addLayout(row)
        self.chk_sync = QCheckBox(tr("Auch als Windows-Standard des Druckers setzen (gilt dann für alle Programme)")
                                  if _platform.IS_WIN else
                                  tr("Auch als System-Standard der CUPS-Queue setzen "
                                  "(gilt dann zusätzlich für alle anderen Programme)"))
        self.chk_sync.setChecked(True)
        v.addWidget(self.chk_sync)
        self.p_area = QScrollArea()
        self.p_area.setWidgetResizable(True)
        v.addWidget(self.p_area, 1)
        self.cmb_p.currentIndexChanged.connect(self._show_printer)
        if self.plist:
            self._show_printer()
        return w

    def _pcfg(self, name):
        return self.cfg.setdefault("printers", {}).setdefault(name, {"options": {}})

    def _show_printer(self, *_):
        name = self.cmb_p.currentData()
        if not name:
            return
        try:
            caps = self.s.caps_for(name, reload=True)
        except Exception as e:
            self.p_area.setWidget(QLabel(tr("Fehler: {0}").format(e)))
            return
        self.caps = caps
        pc = self._pcfg(name)
        inner = QWidget()
        v = QVBoxLayout(inner)
        for gname, gtext, keys in caps.groups:
            box = QGroupBox(gtext + (tr(" – Hardware, wird direkt in der CUPS-Queue gesetzt")
                                     if gname == printers.INSTALLABLE_GROUP else ""))
            f = QFormLayout(box)
            for k in keys:
                o = caps.options[k]
                cb = QComboBox()
                cur = self.queue_changes.get((name, k), o.default) if o.installable \
                    else pc["options"].get(k, o.default)
                fill_combo(cb, [(c.value, c.text) for c in o.choices], cur)
                lbl = o.text + (" *" if (not o.installable and k in pc["options"]) else "") + ":"
                cb.currentIndexChanged.connect(lambda _i, k=k, cb=cb, o=o: self._opt_set(name, o, cb))
                f.addRow(lbl, cb)
            v.addWidget(box)
        if caps.backend == "win":
            g = QGroupBox(tr("Herstellereinstellungen (Windows-Treiber)"))
            gl = QVBoxLayout(g)
            lbl = QLabel(tr("Finisher, Heften, Lochen, Falzen, Beschnitt, Fiery-Optionen usw. stellst du im Original-"
                         "Dialog des Herstellers ein. Die Auswahl wird als pdfToolkit-Standard gespeichert."))
            lbl.setWordWrap(True)
            gl.addWidget(lbl)
            row = QHBoxLayout()
            b1 = QPushButton(tr("Herstellerdialog öffnen …"))
            b2 = QPushButton(tr("Zurücksetzen"))
            self.lbl_dm = QLabel(tr("gesetzt") if pc.get("devmode") else tr("Windows-Standard"))
            b1.clicked.connect(lambda: self._win_devmode(name))
            b2.clicked.connect(lambda: (pc.pop("devmode", None), self.lbl_dm.setText(tr("Windows-Standard"))))
            row.addWidget(b1)
            row.addWidget(b2)
            row.addWidget(self.lbl_dm, 1)
            gl.addLayout(row)
            v.addWidget(g)
            hint = QLabel(tr("Installierte Hardware (Finisher, Decks, Locher) wird unter Windows in den "
                          "Druckereigenschaften → Geräteeinstellungen des Treibers konfiguriert."))
            hint.setWordWrap(True)
            hint.setStyleSheet(f"color: {theme.MUTED};")
            v.addWidget(hint)

        self._build_tray_table(v, name, caps, pc)

        g = QGroupBox(tr("Finisher-Vorlagen (im Druckdialog wählbar)"))
        gl = QVBoxLayout(g)
        self.lst_presets = QListWidget()
        self.lst_presets.setMaximumHeight(120)
        gl.addWidget(self.lst_presets)
        row = QHBoxLayout()
        b_new = QPushButton(tr("Neue Vorlage …"))
        b_del = QPushButton(tr("Löschen"))
        b_new.clicked.connect(lambda: self._new_preset(name))
        b_del.clicked.connect(lambda: self._del_preset(name))
        row.addWidget(b_new)
        row.addWidget(b_del)
        row.addStretch()
        gl.addLayout(row)
        v.addWidget(g)
        self._refresh_presets(name)

        g = QGroupBox(tr("Farbmanagement-Standard"))
        f = QFormLayout(g)
        self.p_prof = QComboBox()
        fill_combo(self.p_prof, [("", tr("Keins (Treiber)"))] +
                   [(p["id"], p.get("name") or p["id"]) for p in config.profiles_for(self.cfg, name)],
                   pc.get("color_profile", ""))
        self.p_intent = QComboBox()
        fill_combo(self.p_intent, list(config.INTENTS.items()), pc.get("intent", "relative"))
        self.p_prof.currentIndexChanged.connect(lambda _i: pc.__setitem__("color_profile", self.p_prof.currentData()))
        self.p_intent.currentIndexChanged.connect(lambda _i: pc.__setitem__("intent", self.p_intent.currentData()))
        f.addRow(tr("Profil:"), self.p_prof)
        f.addRow(tr("Intent:"), self.p_intent)
        v.addWidget(g)
        v.addWidget(QLabel(tr("* = vom Treiber-Standard abweichend")))
        v.addStretch()
        self.p_area.setWidget(inner)
        fit_width(inner)
        self.p_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    # ---------------- Fächerbelegung ---------------- #
    def _build_tray_table(self, v, name, caps, pc):
        from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget
        skey, pkey, mkey = (caps.roles.get(r) for r in ("source", "pagesize", "mediatype"))
        g = QGroupBox(tr("Fächerbelegung – automatische Fachwahl nach Format und Grammatur"))
        gl = QVBoxLayout(g)
        if not skey or not pkey:
            gl.addWidget(QLabel(tr("Der Treiber meldet keine Fächer/Formate – automatische Fachwahl nicht möglich.")))
            v.addWidget(g)
            return
        info = QLabel(tr("Reihenfolge = Vorrang: Bei mehreren passenden Laden nimmt pdfToolkit die oberste; "
                      "ist sie laut Gerät leer, die nächste. Am Gerät zusätzlich die automatische "
                      "Kassettenumschaltung einschalten – nur der Drucker kann mitten im Auftrag wechseln."))
        info.setWordWrap(True)
        info.setStyleSheet(f"color: {theme.MUTED};")
        gl.addWidget(info)
        self.chk_trayauto = QCheckBox(tr("Fach automatisch nach Format/Grammatur wählen"))
        self.chk_trayauto.setChecked(bool(pc.get("tray_auto", True)))
        self.chk_trayauto.toggled.connect(lambda b: (pc.__setitem__("tray_auto", b), self.touched.add(name)))
        gl.addWidget(self.chk_trayauto)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Geräteadresse (IP/Name):")))
        self.ed_host = QLineEdit(pc.get("tray_host", "") or self._guess_host(name))
        self.ed_host.setPlaceholderText(tr("z. B. 192.168.1.20"))
        self.ed_host.editingFinished.connect(lambda: pc.__setitem__("tray_host", self.ed_host.text().strip()))
        row.addWidget(self.ed_host, 1)
        b_read = QPushButton(tr("Vom Gerät lesen"))
        b_read.setToolTip(tr("Fragt per IPP ab, was in welcher Lade liegt, und befüllt die Tabelle"))
        b_read.clicked.connect(lambda: self._tray_from_device(name, caps, pc))
        row.addWidget(b_read)
        gl.addLayout(row)
        self.chk_traylive = QCheckBox(tr("Vor jedem Druck Füllstand am Gerät prüfen (leere Laden überspringen)"))
        self.chk_traylive.setChecked(bool(pc.get("tray_live", False)))
        self.chk_traylive.toggled.connect(lambda b: pc.__setitem__("tray_live", b))
        gl.addWidget(self.chk_traylive)

        self.tbl = QTableWidget(0, 5)
        self.tbl.setHorizontalHeaderLabels([tr("Lade"), tr("Format"), tr("Grammatur"), tr("Medientyp"), tr("Gerätename (IPP)")])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl.verticalHeader().setVisible(True)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setMinimumHeight(170)
        gl.addWidget(self.tbl)
        self._tray_ctx = (name, caps, pc, skey, pkey, mkey)
        for t in pc.get("trays", []):
            self._tray_add_row(t)
        row = QHBoxLayout()
        for text, fn in [("+ Lade", lambda: (self._tray_add_row({}), self._tray_store())),
                         ("Entfernen", self._tray_remove), ("▲", lambda: self._tray_move(-1)),
                         ("▼", lambda: self._tray_move(1))]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch()
        gl.addLayout(row)
        v.addWidget(g)

    def _guess_host(self, name):
        from .. import ipp
        p = next((p for p in self.plist if p.name == name), None)
        return ipp.host_from_device_uri(p.uri) if p and getattr(p, "uri", "") else ""

    def _tray_add_row(self, t: dict):
        from PySide6.QtWidgets import QSpinBox as _Spin
        name, caps, pc, skey, pkey, mkey = self._tray_ctx
        r = self.tbl.rowCount()
        self.tbl.insertRow(r)
        cb_slot = QComboBox()
        fill_combo(cb_slot, [(c.value, c.text) for c in caps.options[skey].choices
                             if not re_auto(c)], t.get("slot", ""))
        cb_size = QComboBox()
        fill_combo(cb_size, [(c.value, c.text) for c in caps.options[pkey].choices], t.get("size", "A4"))
        sp = _Spin()
        sp.setRange(0, 2000)
        sp.setSuffix(tr(" g/m²"))
        sp.setSpecialValueText("–")
        sp.setValue(int(t.get("weight", 0) or 0))
        cb_media = QComboBox()
        media = [("", tr("(nicht setzen)"))]
        if mkey:
            media += [(c.value, c.text) for c in caps.options[mkey].choices]
        fill_combo(cb_media, media, t.get("media", ""))
        ed_ipp = QLineEdit(t.get("ipp", ""))
        ed_ipp.setPlaceholderText(tr("tray-1 …"))
        for col, w in enumerate((cb_slot, cb_size, sp, cb_media, ed_ipp)):
            self.tbl.setCellWidget(r, col, w)
        for w in (cb_slot, cb_size, cb_media):
            w.currentIndexChanged.connect(lambda *_: self._tray_store())
        sp.valueChanged.connect(lambda *_: self._tray_store())
        ed_ipp.editingFinished.connect(self._tray_store)

    def _tray_rows(self):
        out = []
        for r in range(self.tbl.rowCount()):
            w = [self.tbl.cellWidget(r, c) for c in range(5)]
            out.append({"slot": w[0].currentData() or "", "size": w[1].currentData() or "",
                        "weight": int(w[2].value()), "media": w[3].currentData() or "",
                        "ipp": w[4].text().strip()})
        return out

    def _tray_store(self):
        name, _caps, pc, *_ = self._tray_ctx
        pc["trays"] = [t for t in self._tray_rows() if t["slot"] and t["size"]]
        self.touched.add(name)

    def _tray_remove(self):
        r = self.tbl.currentRow()
        if r >= 0:
            self.tbl.removeRow(r)
            self._tray_store()

    def _tray_move(self, d):
        r = self.tbl.currentRow()
        rows = self._tray_rows()
        if r < 0 or not 0 <= r + d < len(rows):
            return
        rows[r], rows[r + d] = rows[r + d], rows[r]
        self.tbl.setRowCount(0)
        for t in rows:
            self._tray_add_row(t)
        self.tbl.selectRow(r + d)
        self._tray_store()

    def _tray_from_device(self, name, caps, pc):
        from .. import ipp, trays
        host = self.ed_host.text().strip()
        pc["tray_host"] = host
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        st = ipp.query(host)
        QApplication.restoreOverrideCursor()
        if st.error or not st.trays:
            QMessageBox.warning(self, tr("Vom Gerät lesen"),
                                tr("Keine Fachinformationen erhalten.\n\n") + (st.error or
                                tr("Das Gerät meldet keine Ladenbelegung (media-col-ready).")) +
                                tr("\n\nDie Belegung kann auch von Hand eingetragen werden."))
            return
        rows, unmapped = [], []
        for src, t in st.trays.items():
            slot = trays.slot_for_source(caps, src)
            size = trays.size_for_mm(caps, t.size_mm) if t.size_mm else None
            if not slot or not size:
                unmapped.append(f"{t.name or src}: {('%.0f × %.0f mm' % t.size_mm) if t.size_mm else 'Format ?'}")
                continue
            rows.append({"slot": slot, "size": size, "weight": int(t.weight or 0), "media": "", "ipp": src})
        if not rows:
            QMessageBox.warning(self, tr("Vom Gerät lesen"), tr("Laden gefunden, aber keiner Treiberlade zuordenbar:\n")
                                + "\n".join(unmapped))
            return
        self.tbl.setRowCount(0)
        for t in rows:
            self._tray_add_row(t)
        self._tray_store()
        msg = tr("{0} Lade(n) übernommen. Bitte Reihenfolge und Grammaturen prüfen.").format(len(rows))
        if unmapped:
            msg += tr("\n\nNicht zuordenbar (bitte von Hand ergänzen):\n") + "\n".join(unmapped)
        QMessageBox.information(self, tr("Vom Gerät lesen"), msg)

    def _win_devmode(self, name):
        from ..printers_win import driver_dialog
        pc = self._pcfg(name)
        try:
            res = driver_dialog(int(self.winId()), name, pc.get("devmode"))
        except Exception as e:
            QMessageBox.critical(self, tr("Treiberdialog"), str(e))
            return
        if res:
            pc["devmode"] = res
            self.touched.add(name)
            self.lbl_dm.setText(tr("gesetzt – wird beim Speichern übernommen"))

    def _refresh_presets(self, name):
        self.lst_presets.clear()
        for pr in self._pcfg(name).get("presets", []):
            extra = []
            if pr.get("booklet"):
                extra.append(tr("Broschüre"))
            if pr.get("devmode"):
                extra.append(tr("Herstellereinstellungen"))
            n = len(pr.get("options", {}))
            if n:
                extra.append(tr("{0} Option(en)").format(n))
            self.lst_presets.addItem(pr["name"] + (f"   ({', '.join(extra)})" if extra else ""))

    def _new_preset(self, name):
        dlg = PresetDialog(self, self.caps, name)
        if dlg.exec() and dlg.preset:
            self._pcfg(name).setdefault("presets", []).append(dlg.preset)
            self._refresh_presets(name)

    def _del_preset(self, name):
        r = self.lst_presets.currentRow()
        pres = self._pcfg(name).get("presets", [])
        if 0 <= r < len(pres):
            del pres[r]
            self._refresh_presets(name)

    def _opt_set(self, name, o, cb):
        val = cb.currentData()
        self.touched.add(name)
        if o.installable:
            if val == o.default:
                self.queue_changes.pop((name, o.keyword), None)
            else:
                self.queue_changes[(name, o.keyword)] = val
            return
        opts = self._pcfg(name)["options"]
        if val == o.default:
            opts.pop(o.keyword, None)    # nur Abweichungen speichern
        else:
            opts[o.keyword] = val

    def _reset_printer(self):
        name = self.cmb_p.currentData()
        if name:
            self._pcfg(name)["options"] = {}
            self.touched.discard(name)
            self._show_printer()

    # ================================================================== #
    def _tab_profiles(self):
        w = QWidget()
        h = QHBoxLayout(w)
        left = QVBoxLayout()
        self.lst_prof = QListWidget()
        left.addWidget(self.lst_prof, 1)
        row = QHBoxLayout()
        b_dl = QPushButton(tr("Profile laden / importieren…"))
        b_dl.setToolTip(tr("Bezugsquellen je Drucker, Download per Link, Import aus ZIP oder Treiberpaket"))
        b_add = QPushButton(tr("ICC-Datei…"))
        b_del = QPushButton(tr("Entfernen"))
        b_dl.clicked.connect(self._download_profiles)
        b_add.clicked.connect(self._add_profile)
        b_del.clicked.connect(self._del_profile)
        row.addWidget(b_dl)
        row.addWidget(b_add)
        row.addWidget(b_del)
        left.addLayout(row)
        h.addLayout(left, 1)

        self.prof_box = QGroupBox(tr("Profil"))
        f = QFormLayout(self.prof_box)
        self.pf_name = QLabel()
        self.pf_rename = QPushButton(tr("Umbenennen…"))
        self.pf_rename.clicked.connect(self._rename_profile)
        r = QHBoxLayout()
        r.addWidget(self.pf_name, 1)
        r.addWidget(self.pf_rename)
        f.addRow(tr("Name:"), r)
        self.pf_space = QLabel()
        f.addRow(tr("Farbraum:"), self.pf_space)
        self.pf_printers = QListWidget()
        self.pf_printers.setMaximumHeight(130)
        f.addRow(tr("Zugeordnet zu\n(leer = alle):"), self.pf_printers)
        self.pf_intents = {}
        ir = QVBoxLayout()
        for k, t in config.INTENTS.items():
            c = QCheckBox(t)
            self.pf_intents[k] = c
            ir.addWidget(c)
        f.addRow(tr("Freigegebene Intents:"), ir)
        self.pf_bpc = QCheckBox(tr("Tiefenkompensierung (BPC)"))
        f.addRow("", self.pf_bpc)
        self.pf_opts = QPlainTextEdit()
        self.pf_opts.setPlaceholderText(tr("Treiberoptionen, die mit diesem Profil gesetzt werden,\n"
                                        "z. B. Farbabgleich des Treibers aus:\nKEY=WERT"))
        self.pf_opts.setMaximumHeight(110)
        f.addRow(tr("Treiberoptionen:"), self.pf_opts)
        h.addWidget(self.prof_box, 2)

        self.lst_prof.currentRowChanged.connect(self._show_profile)
        self.pf_printers.itemChanged.connect(lambda _i: self._store_profile())
        for c in self.pf_intents.values():
            c.toggled.connect(lambda _b: self._store_profile())
        self.pf_bpc.toggled.connect(lambda _b: self._store_profile())
        self.pf_opts.textChanged.connect(self._store_profile)
        self._refresh_profiles()
        return w

    def _refresh_profiles(self, select=None):
        self.lst_prof.blockSignals(True)
        self.lst_prof.clear()
        for p in self.cfg["color_profiles"]:
            it = QListWidgetItem(f"{p.get('name') or p['id']}  [{p['id']}]")
            it.setData(Qt.ItemDataRole.UserRole, p["id"])
            self.lst_prof.addItem(it)
        self.lst_prof.blockSignals(False)
        row = 0
        if select:
            row = next((i for i, p in enumerate(self.cfg["color_profiles"]) if p["id"] == select), 0)
        self.lst_prof.setCurrentRow(row if self.cfg["color_profiles"] else -1)
        self._show_profile(self.lst_prof.currentRow())

    def _cur_profile(self):
        r = self.lst_prof.currentRow()
        return self.cfg["color_profiles"][r] if 0 <= r < len(self.cfg["color_profiles"]) else None

    def _show_profile(self, _row):
        p = self._cur_profile()
        self.prof_box.setEnabled(p is not None)
        self._loading = True
        try:
            self.pf_printers.clear()
            if p is None:
                return
            self.pf_name.setText(p.get("name") or p["id"])
            src = self.new_icc.get(p["id"], p["file"])
            try:
                self.pf_space.setText(colorconv.icc_colorspace(src))
            except (OSError, ValueError) as e:
                self.pf_space.setText(f"? ({e})")
            for q in self.plist:
                it = QListWidgetItem(q.name)
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                it.setCheckState(Qt.CheckState.Checked if q.name in p.get("printers", []) else Qt.CheckState.Unchecked)
                self.pf_printers.addItem(it)
            allowed = p.get("intents") or list(config.INTENTS)
            for k, c in self.pf_intents.items():
                c.setChecked(k in allowed)
            self.pf_bpc.setChecked(bool(p.get("bpc", True)))
            self.pf_opts.setPlainText("\n".join(f"{k}={v}" for k, v in (p.get("driver_options") or {}).items()))
        finally:
            self._loading = False

    def _store_profile(self):
        if getattr(self, "_loading", False):
            return
        p = self._cur_profile()
        if p is None:
            return
        p["printers"] = [self.pf_printers.item(i).text() for i in range(self.pf_printers.count())
                         if self.pf_printers.item(i).checkState() == Qt.CheckState.Checked]
        p["intents"] = [k for k, c in self.pf_intents.items() if c.isChecked()] or ["relative"]
        p["bpc"] = self.pf_bpc.isChecked()
        opts = {}
        for line in self.pf_opts.toPlainText().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                if k.strip():
                    opts[k.strip()] = v.strip()
        p["driver_options"] = opts

    def _add_profile(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("ICC-Profil wählen"), "/usr/share/color/icc",
                                              tr("ICC-Profile (*.icc *.icm *.ICC *.ICM)"))
        if not path:
            return
        try:
            space = colorconv.icc_colorspace(path)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, tr("ICC"), str(e))
            return
        base = re.sub(r"[^A-Za-z0-9_-]+", "_", os.path.splitext(os.path.basename(path))[0])[:48] or "profil"
        pid, i = base, 2
        ids = {p["id"] for p in self.cfg["color_profiles"]}
        while pid in ids:
            pid, i = f"{base}_{i}", i + 1
        name, ok = QInputDialog.getText(self, tr("Profilname"), tr("Anzeigename:"), text=os.path.basename(path))
        if not ok:
            return
        self.new_icc[pid] = path
        self.removed_icc.discard(pid)
        self.cfg["color_profiles"].append({
            "id": pid, "name": name.strip()[:128] or pid, "file": str(config.ICC_DIR / f"{pid}.icc"),
            "printers": [], "intents": ["perceptual", "relative"], "bpc": True, "driver_options": {},
        })
        self._refresh_profiles(pid)
        self.pf_space.setText(space)

    def _download_profiles(self):
        import tempfile
        from .. import iccfetch
        from .iccimport import IccImportDialog
        if not hasattr(self, "_icc_work"):
            self._icc_work = tempfile.mkdtemp(prefix="pdftoolkit-icc-")
            self.finished.connect(lambda *_: __import__("shutil").rmtree(self._icc_work, ignore_errors=True))
        current = self.cmb_p.currentData() if hasattr(self, "cmb_p") else None
        dlg = IccImportDialog(self, self.plist, current, self._icc_work)
        if not dlg.exec():
            return
        ids = {p["id"] for p in self.cfg["color_profiles"]}
        last = None
        for info, printer in dlg.selected:
            pid = iccfetch.profile_id(info.desc, ids)
            ids.add(pid)
            self.new_icc[pid] = info.path
            self.removed_icc.discard(pid)
            self.cfg["color_profiles"].append({
                "id": pid, "name": info.desc[:128], "file": str(config.ICC_DIR / f"{pid}.icc"),
                "printers": [printer] if printer else [], "intents": ["perceptual", "relative"],
                "bpc": True, "driver_options": {},
            })
            last = pid
        self._refresh_profiles(last)
        QMessageBox.information(self, tr("Übernommen"),
                                tr("{0} Profil(e) hinzugefügt. Sie werden beim Speichern installiert.").format(len(dlg.selected)))

    def _rename_profile(self):
        p = self._cur_profile()
        if p is None:
            return
        name, ok = QInputDialog.getText(self, tr("Umbenennen"), tr("Anzeigename:"), text=p.get("name", ""))
        if ok and name.strip():
            p["name"] = name.strip()[:128]
            self._refresh_profiles(p["id"])

    def _del_profile(self):
        p = self._cur_profile()
        if p is None:
            return
        self.cfg["color_profiles"].remove(p)
        if p["id"] in self.new_icc:
            del self.new_icc[p["id"]]
        else:
            self.removed_icc.add(p["id"])
        for pc in self.cfg.get("printers", {}).values():
            if pc.get("color_profile") == p["id"]:
                pc["color_profile"] = ""
        self._refresh_profiles()

    # ================================================================== #
    def _save(self):
        self._collect_general()
        self._store_profile()
        # leere Druckereinträge entfernen
        self.cfg["printers"] = {k: v for k, v in self.cfg.get("printers", {}).items()
                                if v.get("options") or v.get("color_profile") or v.get("devmode") or v.get("presets")
                                or v.get("trays")}
        qopts = [[q, k, v] for (q, k), v in self.queue_changes.items()]
        n_sys = 0
        if self.chk_sync.isChecked():
            for q in sorted(self.touched):
                for k, v in self.cfg.get("printers", {}).get(q, {}).get("options", {}).items():
                    qopts.append([q, k, v])
                    n_sys += 1
        bundle = {
            "config": self.cfg,
            "import_icc": [{"src": os.path.abspath(src), "id": pid} for pid, src in self.new_icc.items()],
            "remove_icc": sorted(self.removed_icc),
            "queue_options": qopts,
        }
        if _platform.IS_WIN:
            bundle.pop("queue_options", None)
            if self.chk_sync.isChecked():
                bundle["printer_defaults"] = [[q, self.cfg["printers"][q]["devmode"]] for q in sorted(self.touched)
                                              if self.cfg.get("printers", {}).get(q, {}).get("devmode")]
                n_sys = len(bundle["printer_defaults"])
            from .. import winadmin
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                code, err, _res = winadmin.run_elevated(bundle)
            except Exception as e:
                code, err = 1, str(e)
            finally:
                QApplication.restoreOverrideCursor()
            if code == 126:
                QMessageBox.information(self, tr("Abgebrochen"), tr("Administratorfreigabe abgelehnt – nichts gespeichert."))
                return
            if code != 0:
                QMessageBox.critical(self, tr("Fehler beim Speichern"), err or f"Code {code}")
                return
            self._saved_message(n_sys)
            return
        fd, tmp = tempfile.mkstemp(prefix="pdfdruck-admin-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(bundle, f, ensure_ascii=False)
            os.chmod(tmp, 0o644)
            r = subprocess.run(_helper_cmd() + ["apply", tmp], capture_output=True, text=True)
        except FileNotFoundError:
            QMessageBox.critical(self, tr("Polkit"), tr("pkexec wurde nicht gefunden (Paket polkit)."))
            return
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        if r.returncode == 126:
            QMessageBox.information(self, tr("Abgebrochen"), tr("Authentifizierung abgebrochen – nichts gespeichert."))
            return
        if r.returncode != 0:
            QMessageBox.critical(self, tr("Fehler beim Speichern"), r.stderr.strip() or f"Code {r.returncode}")
            return
        self._saved_message(n_sys)

    def _saved_message(self, n_sys):
        lines = []
        for q, pc in self.cfg.get("printers", {}).items():
            caps = self.s.caps.get(q)
            for k, v in pc.get("options", {}).items():
                o = caps.options.get(k) if caps else None
                txt = next((c.text for c in o.choices if c.value == v), v) if o else v
                lines.append(f"• {q}: {o.text if o else k} = {txt}")
            if pc.get("devmode"):
                lines.append(tr("• {0}: Herstellereinstellungen gesetzt").format(q))
            if pc.get("presets"):
                lines.append(tr("• {0}: {1} Finisher-Vorlage(n)").format(q, len(pc['presets'])))
            if pc.get("trays"):
                lines.append(tr("• {0}: Fächerbelegung mit {1} Lade(n)").format(q, len(pc['trays']))
                             + (tr(", Füllstand live") if pc.get("tray_live") else ""))
        msg = tr("Standards gespeichert.\n\n") + ("\n".join(lines) if lines else tr("Keine druckerspezifischen Abweichungen."))
        if n_sys:
            msg += (tr("\n\n{0} Drucker zusätzlich als Windows-Standard gesetzt.").format(n_sys) if _platform.IS_WIN else
                    tr("\n\n{0} Option(en) zusätzlich als CUPS-Queue-Standard gesetzt.").format(n_sys))
        QMessageBox.information(self, tr("Gespeichert"), msg)
        self.accept()


def re_auto(choice) -> bool:
    """„Automatisch“-Einträge gehören nicht in die Belegungstabelle."""
    return bool(re.search(r"^auto|automat", f"{choice.value} {choice.text}", re.I))


class PresetDialog(QDialog):
    """Neue Finisher-Vorlage: Name, Finisher-Optionen (nur geänderte zählen), Broschüre, ggf. Herstellerdialog."""

    def __init__(self, parent, caps, printer):
        super().__init__(parent)
        self.setWindowTitle(tr("Neue Finisher-Vorlage – {0}").format(printer))
        self.resize(560, 600)
        self.caps, self.printer = caps, printer
        self.preset = None
        self.devmode = None
        v = QVBoxLayout(self)
        f = QFormLayout()
        self.ed_name = QLineEdit()
        self.ed_name.setPlaceholderText(tr("z. B. Broschüre heften + falzen + beschneiden"))
        f.addRow(tr("Name:"), self.ed_name)
        self.chk_booklet = QCheckBox(tr("Für Broschürendruck (wählt im Druckdialog automatisch „Broschüre“)"))
        f.addRow(self.chk_booklet)
        v.addLayout(f)
        self.chk_all = QCheckBox(tr("Alle Treiberoptionen anzeigen (nicht nur Endverarbeitung)"))
        self.chk_all.toggled.connect(self._fill)
        v.addWidget(self.chk_all)
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        v.addWidget(self.area, 1)
        if caps.backend == "win":
            row = QHBoxLayout()
            b = QPushButton(tr("Herstellerdialog für diese Vorlage …"))
            b.clicked.connect(self._dm)
            self.lbl_dm = QLabel(tr("nicht gesetzt"))
            row.addWidget(b)
            row.addWidget(self.lbl_dm, 1)
            v.addLayout(row)
        note = QLabel(tr("Nur Optionen, die du von „(unverändert)“ wegstellst, werden Teil der Vorlage."))
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {theme.MUTED};")
        v.addWidget(note)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Vorlage anlegen"))
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.combos = {}
        self._fill()

    def _fill(self, *_):
        inner = QWidget()
        f = QFormLayout(inner)
        self.combos = {}
        finish_keys = {self.caps.roles.get(r) for r in ("saddle", "staple", "punch", "fold", "trim", "stacker")}
        for k, o in self.caps.options.items():
            if o.installable:
                continue
            if not self.chk_all.isChecked() and k not in finish_keys and not i18n.is_finishing(k, o.text):
                continue
            cb = QComboBox()
            fill_combo(cb, [("", tr("(unverändert)"))] + [(c.value, c.text) for c in o.choices], "")
            self.combos[k] = cb
            f.addRow(o.text + ":", cb)
        if not self.combos:
            msg = (tr("Keine Finisher-Optionen im Treiber erkannt. ") +
                   (tr("Nutze den Herstellerdialog unten.") if self.caps.backend == "win" else
                    tr("„Alle Treiberoptionen anzeigen“ oder Finisher unter „Installierte Hardware“ einschalten.")))
            lbl = QLabel(msg)
            lbl.setWordWrap(True)
            f.addRow(lbl)
        self.area.setWidget(inner)
        fit_width(inner)

    def _dm(self):
        from ..printers_win import driver_dialog
        try:
            res = driver_dialog(int(self.winId()), self.printer, self.devmode)
        except Exception as e:
            QMessageBox.critical(self, tr("Treiberdialog"), str(e))
            return
        if res:
            self.devmode = res
            self.lbl_dm.setText(tr("gesetzt"))

    def _ok(self):
        name = self.ed_name.text().strip()[:64]
        if not name:
            QMessageBox.warning(self, tr("Name"), tr("Bitte einen Namen eingeben."))
            return
        opts = {k: cb.currentData() for k, cb in self.combos.items() if cb.currentData()}
        if not opts and not self.devmode:
            QMessageBox.warning(self, tr("Leer"), tr("Die Vorlage enthält keine Einstellungen."))
            return
        self.preset = {"name": name, "options": opts, "booklet": self.chk_booklet.isChecked()}
        if self.devmode:
            self.preset["devmode"] = self.devmode
        self.accept()
