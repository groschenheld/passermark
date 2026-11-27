# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Print dialog: the printer and its options – paper, trays, borderless, finishing, driver settings, presets, colour profiles and materials."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import config, printers, trays
from ..l10n import tr
from . import theme
from .common import fill_combo, fit_width

ROLE_LABELS = [
    ("pagesize", "Papierformat"),
    ("source", "Papierzufuhr / Fach"),
    ("mediatype", "Medientyp"),
    ("duplex", "Beidseitig"),
    ("color", "Farbmodus"),
    ("quality", "Qualität"),
    ("outputbin", "Ausgabefach"),
]


FINISH_LABELS = [
    ("saddle", "Sattelheftung / Broschüre"),
    ("staple", "Heften"),
    ("punch", "Lochen"),
    ("fold", "Falzen"),
    ("trim", "Beschnitt"),
    ("stacker", "Stapler / Versatz"),
]


class PrintDeviceMixin:
    """Printer-dependent part of PrintDialog."""

    def _show_admin_info(self, name):
        if name == printers.PDF_TARGET:
            self.lbl_admin.setText(
                tr(
                    "PDF-Ausgabe – alle Layout-Funktionen (N-Up, Broschüre, Poster, Nutzen, "
                    "Marken, Anschnitt) wirken, Farben bleiben unverändert."
                )
            )
            return
        pc = self.cfg.get("printers", {}).get(name, {})
        opts = pc.get("options", {})
        parts = []
        for k, v in opts.items():
            o = self.caps.options.get(k) if self.caps else None
            if o:
                parts.append(f"{o.text} = {next((c.text for c in o.choices if c.value == v), v)}")
        dp = self.cfg.get("default_printer", "")
        txt = (
            (tr("Admin: ") + "; ".join(parts))
            if parts
            else tr("Keine eigenen Admin-Werte – es gelten die Standards der CUPS-Queue.")
        )
        if dp and dp != name:
            txt += tr("\n⚠ Admin-Standarddrucker ist „{0}“, gewählt ist „{1}“.").format(dp, name)
        self.lbl_admin.setText(txt)

    def _reset_to_admin(self):
        if not self.caps:
            return
        name = self.caps.name
        self.s.values.pop(name, None)
        self.s.color.pop(name, None)
        self.s.material.pop(name, None)
        self.values = self.s.values_for(name)
        self._build_paper()
        self._build_driver_tab()
        self._build_profiles()
        self._fill_sr2_formats()
        fit_width(self)
        self._changed()

    # ================================================================== #
    # printer
    # ================================================================== #
    def _load_printers(self):
        try:
            plist = printers.list_printers()
        except Exception as e:  # noqa: BLE001 – shown to the user
            QMessageBox.critical(self, tr("CUPS"), tr("Drucker können nicht abgefragt werden:\n{0}").format(e))
            plist = []
        plist = list(plist) + [printers.pdf_target_info()]  # always available: Save as PDF
        self.cmb_printer.blockSignals(True)
        for p in plist:
            label = f"{p.info}  ({p.name})" if p.info != p.name else p.name
            if p.model:
                label += f"  –  {p.model}"
            self.cmb_printer.addItem(label, p)
        want = self.s.printer or next((p.name for p in plist if p.is_default), None)
        idx = next((i for i, p in enumerate(plist) if p.name == want), 0)
        self.cmb_printer.setCurrentIndex(idx)
        self.cmb_printer.blockSignals(False)
        if plist:
            self._printer_changed(idx)
        else:
            self.btn_print.setEnabled(False)

    def _printer_changed(self, _idx):
        p: printers.PrinterInfo = self.cmb_printer.currentData()
        if p is None:
            return
        if p.name == printers.PDF_TARGET:
            self.lbl_pstate.setText(
                tr(
                    "Speichert das Ergebnis als PDF-Datei – vektoriell, Farben und Farbräume "
                    "unverändert, kein Farbprofil, keine Druckerränder."
                )
            )
        else:
            self.lbl_pstate.setText(
                f"{tr(p.state_text)} – {p.model}" + (f"\n{p.state_message}" if p.state_message else "")
            )
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.caps = self.s.caps_for(p.name)
        except Exception as e:  # noqa: BLE001 – shown to the user
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, tr("Drucker"), tr("Treiberoptionen nicht lesbar:\n{0}").format(e))
            self.caps = None
            self.btn_print.setEnabled(False)
            return
        QApplication.restoreOverrideCursor()
        self.btn_print.setEnabled(True)
        self.btn_print.setText(tr("Speichern …") if p.name == printers.PDF_TARGET else tr("Drucken"))
        self._pw_form.setRowVisible(self.pw_box, p.name == printers.PDF_TARGET)
        self.spn_copies.setEnabled(p.name != printers.PDF_TARGET)
        self.chk_collate.setEnabled(p.name != printers.PDF_TARGET)
        if hasattr(self, "btn_reset"):
            self.btn_reset.setEnabled(p.name != printers.PDF_TARGET)
        self.s.printer = p.name
        self._show_admin_info(p.name)
        self.values = self.s.values_for(p.name)
        self._build_paper()
        self._build_driver_tab()
        self._build_profiles()
        self._fill_sr2_formats()
        fit_width(self)
        self._changed()

    def _option_combo(self, key):
        opt = self.caps.options[key]
        cb = QComboBox()
        fill_combo(cb, [(c.value, c.text) for c in opt.choices], self.values.get(key, opt.default))
        cb.setProperty("key", key)
        cb.currentIndexChanged.connect(lambda _i, cb=cb: self._option_changed(cb))
        return cb

    def _build_paper(self):
        while self.paper_form.rowCount():
            self.paper_form.removeRow(0)
        self.role_combos = {}
        for role, label in ROLE_LABELS:
            key = self.caps.roles.get(role)
            if key and key in self.caps.options:
                cb = self._option_combo(key)
                self.role_combos[key] = cb
                drv = self.caps.options[key].text
                label = tr(label)
                text = label if drv.lower() in (label.lower(), key.lower()) else f"{label}\n({drv})"
                if role == "pagesize":
                    if self.caps.backend == "pdf":  # layout only for the PDF target
                        row = QHBoxLayout()
                        row.addWidget(cb, 1)
                        b = QPushButton(tr("Sonderformate …"))
                        b.setToolTip(
                            tr(
                                "Eigene Papierformate anlegen – bleiben gespeichert und stehen "
                                "bei „Als PDF speichern“ zur Wahl (mit ★)"
                            )
                        )
                        b.clicked.connect(self._custom_sizes)
                        row.addWidget(b)
                        self.paper_form.addRow(text + ":", row)
                    else:  # device: plain, without a button
                        self.paper_form.addRow(text + ":", cb)
                    continue
                self.paper_form.addRow(text + ":", cb)
        if not self.role_combos:
            self.paper_form.addRow(QLabel(tr("Keine Basisoptionen erkannt – siehe unten „Treiber (alle Optionen)“.")))
        self._build_borderless()
        self._build_tray_auto()
        self._build_finishing()

    def _custom_sizes(self):
        from .customsizes import CustomSizesDialog

        dlg = CustomSizesDialog(self)
        if not dlg.exec():
            return
        self.s.refresh_custom_sizes()
        key = self.caps.roles.get("pagesize") if self.caps else None
        if key and dlg.chosen and self.caps.backend == "pdf":  # PDF target only
            self.values[key] = dlg.chosen
        self._build_paper()
        self._changed()

    def _pc(self):
        return self.cfg.get("printers", {}).get(self.caps.name, {}) if self.caps else {}

    def _build_tray_auto(self):
        self.tray_list = trays.trays_of(self._pc())
        self.cmb_weight = None
        if not self.tray_list or not self.caps.roles.get("source"):
            return
        weights = trays.weights_of(self._pc())
        self.s.__dict__.setdefault("weights", {})
        cur = self.s.weights.get(self.caps.name, 0)
        if weights:
            self.cmb_weight = QComboBox()
            fill_combo(self.cmb_weight, [(0, tr("beliebig"))] + [(w, tr("{0} g/m²").format(w)) for w in weights], cur)
            self.cmb_weight.currentIndexChanged.connect(self._weight_changed)
            self.paper_form.addRow(tr("Grammatur:"), self.cmb_weight)
        self.chk_autotray = QCheckBox(tr("Fach automatisch nach Format/Grammatur wählen"))
        self.chk_autotray.setChecked(bool(self._pc().get("tray_auto", True)))
        self.chk_autotray.toggled.connect(lambda _b: self._auto_tray())
        self.paper_form.addRow("", self.chk_autotray)
        self.lbl_tray = QLabel()
        self.lbl_tray.setWordWrap(True)
        self.paper_form.addRow("", self.lbl_tray)
        self._live = None
        host = self._pc().get("tray_host", "")
        if self._pc().get("tray_live") and host:
            self._start_live(host)
        self._auto_tray()

    def _start_live(self, host):
        from PySide6.QtCore import QThread, Signal

        class _Live(QThread):
            got = Signal(object)

            def run(self_t):
                self_t.got.emit(trays.live_status(host, force=True))

        self._live_thread = _Live(self)
        self._live_thread.got.connect(self._live_arrived)
        self._live_thread.start()

    def _live_arrived(self, st):
        self._live = st
        if st is None and hasattr(self, "lbl_tray"):
            self.lbl_tray.setToolTip(tr("Gerät nicht erreichbar – es gilt die hinterlegte Reihenfolge."))
        self._auto_tray()

    def _weight_changed(self, *_):
        self.s.weights[self.caps.name] = self.cmb_weight.currentData() or 0
        self._auto_tray()

    def _auto_tray(self):
        if not getattr(self, "tray_list", None) or not hasattr(self, "chk_autotray"):
            return
        if not self.chk_autotray.isChecked():
            self.lbl_tray.setText("")
            self._auto_slot = None
            return
        skey, pkey, mkey = (self.caps.roles.get(r) for r in ("source", "pagesize", "mediatype"))
        weight = self.cmb_weight.currentData() if self.cmb_weight else 0
        labels = {c.value: c.text for c in self.caps.options[skey].choices}
        p = trays.pick(self.tray_list, self.values.get(pkey, ""), weight or 0, self._live, labels)
        if p.tray:
            self.values[skey] = p.tray.slot
            self._set_combo(skey, p.tray.slot)
            if p.tray.media and mkey:
                self.values[mkey] = p.tray.media
                self._set_combo(mkey, p.tray.media)
            self._auto_slot = p.tray.slot
            txt = f"→ {labels.get(p.tray.slot, p.tray.slot)}" + (f"   ({p.note})" if p.note else "")
        else:
            self._auto_slot = None
            txt = "⚠ " + p.note
        if self._live is not None:
            txt += tr("   · Füllstand vom Gerät")
        self.lbl_tray.setText(txt)
        self.lbl_tray.setStyleSheet(f"color: {theme.ERROR if p.warn else theme.ACCENT};")
        self._preview_timer.start()

    def _set_combo(self, key, value):
        for cb in (self.role_combos.get(key), getattr(self, "driver_combos", {}).get(key)):
            if cb is not None:
                cb.blockSignals(True)
                i = cb.findData(value)
                if i >= 0:
                    cb.setCurrentIndex(i)
                cb.blockSignals(False)

    # borderless
    def _build_borderless(self):
        self.chk_borderless = None
        self._bl_want = False
        if not self.caps or self.caps.backend == "pdf" or not self.caps.can_borderless():
            return
        row = QHBoxLayout()
        self.chk_borderless = QCheckBox(tr("Randlos drucken"))
        self.chk_borderless.setToolTip(
            tr(
                "Bis an den Blattrand drucken. Passermark wählt dafür die randlose Variante "
                "des Papierformats bzw. schaltet die Randlos-Option des Treibers ein. "
                "Hat das Dokument ein Endformat mit Anschnitt, liegt das Endformat genau "
                "auf dem Blatt und der Anschnitt läuft über den Rand."
            )
        )
        self._bl_want = self.caps.is_borderless(self.values)
        self.chk_borderless.toggled.connect(self._borderless_toggled)
        row.addWidget(self.chk_borderless)
        k = self.caps.borderless_expand_key()
        if k and k not in self.role_combos:
            cb = self._option_combo(k)
            self.role_combos[k] = cb
            cb.setToolTip(
                tr(
                    "Erweiterung: wie weit der Treiber das Bild über den Blattrand zieht. Mit Anschnitt im "
                    "Dokument reicht die kleinste Stufe."
                )
            )
            row.addWidget(QLabel(self.caps.options[k].text + ":"))
            row.addWidget(cb, 1)
        row.addStretch()
        self.paper_form.addRow(tr("Rand:"), row)
        self.lbl_borderless = QLabel()
        self.lbl_borderless.setWordWrap(True)
        self.lbl_borderless.setStyleSheet(f"color: {theme.ACCENT_TEXT};")
        self.paper_form.addRow("", self.lbl_borderless)
        self._borderless_sync()

    def _borderless_toggled(self, on: bool):
        self._bl_want = bool(on)
        vals, ok = self.caps.set_borderless(self.values, bool(on))
        if ok:
            self.values = vals
            for k in {self.caps.roles.get("pagesize"), (self.caps.borderless_option() or (None,))[0]} - {None}:
                if k in self.values:
                    self._set_combo(k, self.values[k])
        self._borderless_sync()
        self._changed()

    def _borderless_sync(self):
        """Tick and note according to what is currently set (also if borderless paper was chosen directly)."""
        cb = getattr(self, "chk_borderless", None)
        if cb is None:
            return
        on = self.caps.is_borderless(self.values)
        possible = on or bool(self.caps.borderless_how(self.values))
        cb.blockSignals(True)
        cb.setChecked(on)
        cb.setEnabled(possible)
        cb.blockSignals(False)
        k = self.caps.borderless_expand_key()
        if k in self.role_combos:
            self.role_combos[k].setEnabled(on)
        if not possible:
            txt = tr("Für dieses Papierformat bietet der Treiber kein randloses Drucken an – anderes Format wählen.")
        elif not on:
            txt = ""
        elif any(getattr(self, "trims", None) or []):
            txt = tr(
                "Randlos: das Endformat des Dokuments liegt genau auf dem Blatt, der Anschnitt läuft über den "
                "Rand – Erweiterung im Treiber so klein wie möglich."
            )
        else:
            txt = tr(
                "Randlos: die Seite füllt das ganze Blatt. Der Drucker zieht das Bild etwas über den Rand "
                "(Erweiterung) – wichtige Inhalte nicht direkt an die Kante legen."
            )
        self.lbl_borderless.setText(txt)
        self.lbl_borderless.setVisible(bool(txt))

    def _presets(self):
        return self.cfg.get("printers", {}).get(self.caps.name, {}).get("presets", []) if self.caps else []

    def _build_finishing(self):
        while self.finish_form.rowCount():
            self.finish_form.removeRow(0)
        presets = self._presets()
        self.cmb_preset = QComboBox()
        fill_combo(
            self.cmb_preset,
            [("", tr("(keine Vorlage)"))] + [(str(i), p["name"]) for i, p in enumerate(presets)],
            getattr(self, "_preset_sel", {}).get(self.caps.name, ""),
        )
        self.cmb_preset.setEnabled(bool(presets))
        self.cmb_preset.setToolTip(tr("Vom Admin angelegte Finisher-Vorlagen, z. B. „Broschüre heften + falzen“"))
        self.cmb_preset.currentIndexChanged.connect(self._preset_chosen)
        self.finish_form.addRow(tr("Vorlage:"), self.cmb_preset)
        n = 0
        for role, label in FINISH_LABELS:
            key = self.caps.roles.get(role)
            if key and key in self.caps.options and key not in self.role_combos:
                cb = self._option_combo(key)
                self.role_combos[key] = cb
                self.finish_form.addRow(f"{tr(label)}\n({self.caps.options[key].text}):", cb)
                n += 1
        if self.caps.backend == "win":
            btn = QPushButton(tr("Herstellereinstellungen (Finisher, Heften, Falzen …)"))
            btn.clicked.connect(self._win_driver_dialog)
            self.finish_form.addRow(btn)
            self.lbl_devmode = QLabel()
            self.lbl_devmode.setStyleSheet(f"color: {theme.MUTED};")
            self.finish_form.addRow(self.lbl_devmode)
            self._update_devmode_label()
        elif not n:
            lbl = QLabel(
                tr(
                    "Keine Finisher-Optionen erkannt – alle Treiberoptionen unten bei „Treiber (alle Optionen)“. "
                    "Fehlen Finisher ganz: im Admin unter „Installierte Hardware“ einschalten."
                )
            )
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color: {theme.MUTED};")
            self.finish_form.addRow(lbl)

    def _update_devmode_label(self):
        if hasattr(self, "lbl_devmode"):
            has = bool(self.values.get("__devmode__"))
            self.lbl_devmode.setText(
                tr("Herstellereinstellungen aktiv (Admin-Standard, Vorlage oder von dir gesetzt).")
                if has
                else tr("Es gelten die Windows-Standards des Druckers.")
            )

    def _win_driver_dialog(self):
        from ..printers_win import DEVMODE_KEY, driver_dialog
        from .stallwatch import paused

        try:
            with paused():  # Windows dialog with its own loop: not a stall
                res = driver_dialog(int(self.winId()), self.caps.name, self.values.get(DEVMODE_KEY))
        except Exception as e:  # noqa: BLE001 – shown to the user
            QMessageBox.critical(self, tr("Treiberdialog"), str(e))
            return
        if res:
            self.values[DEVMODE_KEY] = res
            self._update_devmode_label()
            self._changed()

    def _preset_chosen(self, *_):
        idx = self.cmb_preset.currentData()
        self.__dict__.setdefault("_preset_sel", {})[self.caps.name] = idx or ""
        if not idx:
            return
        pr = self._presets()[int(idx)]
        for k, v in pr.get("options", {}).items():
            if k in self.caps.options:
                self.values[k] = v
        if pr.get("devmode"):
            self.values["__devmode__"] = pr["devmode"]
        if pr.get("booklet") and self._handling() != "booklet":
            self.handling_btns["booklet"].setChecked(True)
            self.stack.setCurrentIndex(self.handling_btns["booklet"].property("page"))
        # rebuild the fields so that they show the preset
        self._build_paper()
        skey = self.caps.roles.get("source")
        if skey and skey in pr.get("options", {}) and hasattr(self, "chk_autotray"):
            # the preset decides the tray itself (e.g. cover board from the multi-purpose tray)
            self.chk_autotray.blockSignals(True)
            self.chk_autotray.setChecked(False)
            self.chk_autotray.blockSignals(False)
            self.values[skey] = pr["options"][skey]
            self._set_combo(skey, self.values[skey])
            self.lbl_tray.setText(tr("Fach durch Vorlage festgelegt"))
        self._build_driver_tab()
        fit_width(self)
        self._changed()

    def _build_driver_tab(self):
        old = self.driver_box.layout()
        if old is not None:
            QWidget().setLayout(old)  # dispose of the old layout
        v = QVBoxLayout(self.driver_box)
        self.lbl_conflict = QLabel()
        self.lbl_conflict.setWordWrap(True)
        self.lbl_conflict.setStyleSheet(f"color: {theme.ERROR};")
        v.addWidget(self.lbl_conflict)
        backend = {"ppd": "PPD (Herstellertreiber)", "ipp": "IPP (driverless)", "win": "Windows-Druckertreiber"}.get(
            self.caps.backend, self.caps.backend
        )
        info = QLabel(
            tr("Backend: {0} – alle Optionen bleiben wählbar; Konflikte werden nur gemeldet.").format(backend)
            if self.caps.backend != "win"
            else tr(
                "Backend: {0}. Alle herstellerspezifischen Funktionen (Finisher, Heften, Lochen, Falzen, Beschnitt, Fiery-Optionen …) stellst du im Original-Dialog des Herstellers ein. Papierformat, Fach, Duplex und Farbe von oben haben Vorrang."
            ).format(backend)
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color: {theme.MUTED};")
        v.addWidget(info)
        if self.caps.backend == "win":
            btn = QPushButton(tr("Herstellereinstellungen öffnen …"))
            btn.clicked.connect(self._win_driver_dialog)
            v.addWidget(btn)
        self.driver_combos = {}
        installable = []
        for gname, gtext, keys in self.caps.groups:
            keys = [k for k in keys if k not in self.role_combos]
            if not keys:
                continue
            if gname == printers.INSTALLABLE_GROUP:
                installable = keys
                continue
            box = QGroupBox(gtext)
            f = QFormLayout(box)
            for k in keys:
                cb = self._option_combo(k)
                self.driver_combos[k] = cb
                f.addRow(self.caps.options[k].text + ":", cb)
            v.addWidget(box)
        if installable:
            box = QGroupBox(tr("Installierte Hardware (nur Admin änderbar)"))
            f = QFormLayout(box)
            for k in installable:
                o = self.caps.options[k]
                txt = next((c.text for c in o.choices if c.value == o.default), o.default)
                f.addRow(o.text + ":", QLabel(txt))
            v.addWidget(box)
        v.addStretch()

    def _option_changed(self, cb):
        key = cb.property("key")
        self.values[key] = cb.currentData()
        if self.caps and key == self.caps.roles.get("pagesize"):
            if getattr(self, "_bl_want", False) and not self.caps.is_borderless(self.values):
                vals, ok = self.caps.set_borderless(self.values, True)  # other size: borderless stays on
                if ok and vals.get(key) != self.values.get(key):
                    self.values = vals
                    self._set_combo(key, vals[key])
            self._auto_tray()  # format changed -> select a matching tray
        if getattr(self, "chk_borderless", None) is not None:
            self._borderless_sync()
        self._changed()

    def _build_profiles(self):
        name = self.caps.name
        profs = config.profiles_for(self.cfg, name)
        pid, intent = self.s.color_for(name)
        self.cmb_profile.blockSignals(True)
        self.cmb_intent.blockSignals(True)
        fill_combo(
            self.cmb_profile,
            [("", tr("Keins – Farbmanagement des Treibers"))] + [(p["id"], p.get("name") or p["id"]) for p in profs],
            pid,
        )
        self._fill_intents(intent)
        user = bool(self.cfg.get("allow_user_profile_choice", True))
        if self._is_pdf_target():  # PDF output: colors stay unchanged
            fill_combo(self.cmb_profile, [("", tr("Keins – Farben bleiben unverändert"))], "")
            user = False
        self.cmb_profile.setEnabled(user and bool(profs))
        self.cmb_intent.setEnabled(user and bool(self.cmb_profile.currentData()))
        self.cmb_profile.blockSignals(False)
        self.cmb_intent.blockSignals(False)
        self._build_materials(name, user and bool(profs))
        if getattr(self, "chk_drvcolor", None) is not None:
            from .. import printers

            can = not self._is_pdf_target() and printers.color_off_option(self.caps) is not None
            self.chk_drvcolor.setEnabled(can)
            if not can:
                self.chk_drvcolor.setChecked(False)
            if not self._is_pdf_target() and not can:
                self.chk_drvcolor.setToolTip(tr("Der Treiber bietet keine Option, seine Farbanpassung abzuschalten."))
        self._profile_note()

    def _build_materials(self, printer: str, enabled: bool):
        """Materials with a profile for this printer (own assignment or "all printers")."""
        from .. import colorlab

        allowed = {p["id"] for p in config.profiles_for(self.cfg, printer)}
        mats = [
            m
            for m in colorlab.materials_for(self.cfg, printer)
            if colorlab.profile_for(self.cfg, m, printer) in allowed
        ]
        cur = getattr(self.s, "material", {}).get(printer, "")
        self.cmb_material.blockSignals(True)
        fill_combo(
            self.cmb_material,
            [("", tr("– keins –"))]
            + [
                (m["id"], (m.get("name") or m["id"]) + (f"  ({m['weight']} g/m²)" if m.get("weight") else ""))
                for m in mats
            ],
            cur if cur in [m["id"] for m in mats] else "",
        )
        self.cmb_material.blockSignals(False)
        self.cmb_material.setEnabled(enabled and bool(mats))
        self.color_form.setRowVisible(self.row_material, bool(mats))

    def _material_changed(self, *_):
        from .. import colorlab

        printer = self.caps.name
        mid = self.cmb_material.currentData() or ""
        if not hasattr(self.s, "material"):
            self.s.material = {}
        self.s.material[printer] = mid
        m = colorlab.material_by_id(self.cfg, mid)
        if m is None:
            self._profile_note()
            return
        pid = colorlab.profile_for(self.cfg, m, printer)
        i = self.cmb_profile.findData(pid)
        if i >= 0:
            self.cmb_profile.setCurrentIndex(i)
        if m.get("intent"):
            j = self.cmb_intent.findData(m["intent"])
            if j >= 0:
                self.cmb_intent.setCurrentIndex(j)
        self._profile_note()

    def _fill_intents(self, current):
        p = config.profile_by_id(self.cfg, self.cmb_profile.currentData() or "")
        allowed = (p or {}).get("intents") or list(config.INTENTS)
        fill_combo(self.cmb_intent, [(i, config.INTENTS[i]) for i in allowed if i in config.INTENTS], current)

    def _profile_changed(self, *_):
        cur_intent = self.cmb_intent.currentData() or "relative"
        if self.sender() is self.cmb_profile:
            self.cmb_intent.blockSignals(True)
            self._fill_intents(cur_intent)
            self.cmb_intent.blockSignals(False)
        self.cmb_intent.setEnabled(self.cmb_profile.isEnabled() and bool(self.cmb_profile.currentData()))
        self.s.color[self.caps.name] = (
            self.cmb_profile.currentData() or "",
            self.cmb_intent.currentData() or "relative",
        )
        self._profile_note()
        self._preview_timer.start()

    def _profile_note(self):
        p = config.profile_by_id(self.cfg, self.cmb_profile.currentData() or "")
        from .. import colorlab

        m = colorlab.material_by_id(self.cfg, self.cmb_material.currentData() or "")
        if m is not None and colorlab.profile_for(self.cfg, m, self.caps.name) != (
            self.cmb_profile.currentData() or ""
        ):
            self.cmb_material.blockSignals(True)  # profile changed by hand: no material any more
            self.cmb_material.setCurrentIndex(0)
            self.cmb_material.blockSignals(False)
            getattr(self.s, "material", {}).pop(self.caps.name, None)
            m = None
        if not p:
            chk = getattr(self, "chk_drvcolor", None)
            off = chk is not None and chk.isEnabled() and chk.isChecked()
            self.lbl_profile_note.setText(
                tr(
                    "Ohne Profil und ohne Farbanpassung gehen die Farbwerte unverändert an den Drucker (z. B. für Testcharts)."
                )
                if off
                else ""
            )
            return
        dopts = p.get("driver_options") or {}
        txt = tr("Das PDF wird vor dem Senden mit diesem Profil in Gerätefarben umgerechnet.")
        if m is not None and m.get("white"):
            pw = colorlab.profile_white(p.get("file", ""))
            if pw:
                de = colorlab.delta_e(m["white"], pw)
                txt += " " + tr("Papierweiß {0} zum Profil: ΔE {1:.1f} – {2}.").format(
                    m.get("name") or m["id"], de, colorlab.verdict(de)
                )
        if dopts:
            txt += tr(" Profil setzt Treiberoptionen: ") + ", ".join(f"{k}={v}" for k, v in dopts.items())
        chk = getattr(self, "chk_drvcolor", None)
        if chk is not None and chk.isEnabled() and not chk.isChecked() and not dopts:
            txt += " " + tr(
                "Passt der Treiber die Farben zusätzlich an, werden sie doppelt verändert – dann unten "
                "„Farbanpassung des Treibers aus“."
            )
        self.lbl_profile_note.setText(txt)
