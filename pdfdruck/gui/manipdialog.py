# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Dokument-Manipulation: Bedienfeld (Reiter im Druckdialog + eigener Dialog) und Farbvorschau."""
from __future__ import annotations

import os
import shutil
import tempfile

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QMessageBox,
                               QPushButton, QScrollArea, QSpinBox, QSplitter, QVBoxLayout, QWidget)

from .. import cmyk, config, pdfmanip
from ..l10n import tr
from . import theme
from .common import fill_combo, fit_width

MODES = [("rgb_only", "RGB/Graustufen → CMYK, vorhandenes CMYK unverändert"),
         ("all", "Alles neu separieren (CMYK von Quellprofil → Zielprofil)"),
         ("gray", "In Graustufen umwandeln (druckt nur mit Schwarz)")]


def pil_to_pixmap(img) -> QPixmap:
    img = img.convert("RGB")
    data = img.tobytes("raw", "RGB")
    qi = QImage(data, img.width, img.height, 3 * img.width, QImage.Format.Format_RGB888).copy()
    return QPixmap.fromImage(qi)


class ManipPanel(QWidget):
    """Document manipulation settings. `changed` signal on every change."""
    changed = Signal()

    def __init__(self, parent, settings: cmyk.ManipSettings, cfg: dict, doc=None, current: int = 0):
        super().__init__(parent)
        self.s, self.cfg, self.doc, self.current = settings, cfg, doc, current
        self.extra_profiles: list[cmyk.CmykProfile] = []
        v = QVBoxLayout(self)

        # ---------------- CMYK ----------------
        g = self.grp_cmyk = QGroupBox(tr("CMYK-Umwandlung"))
        f = QFormLayout(g)
        self.chk_cmyk = QCheckBox(tr("Dokument in CMYK umwandeln"))
        self.chk_cmyk.setChecked(settings.cmyk)
        f.addRow(self.chk_cmyk)
        from .. import colorlab
        self.material_white = None
        self._facts = None
        self.cmb_material = QComboBox()
        self.cmb_material.setToolTip(tr("Papier aus der Verwaltung – wählt Zielprofil, Intent und die passende Methode"))
        mats = [m for m in cfg.get("materials", []) if colorlab.cmyk_profile_of(cfg, m)]
        fill_combo(self.cmb_material, [("", tr("– keins –"))] + [(m["id"], m.get("name") or m["id"]) for m in mats], "")
        f.addRow(tr("Material:"), self.cmb_material)
        if not mats:
            f.setRowVisible(self.cmb_material, False)
        self.lbl_rec = QLabel()
        self.lbl_rec.setWordWrap(True)
        self.lbl_rec.setStyleSheet(f"color: {theme.ACCENT};")
        self.lbl_rec.hide()
        f.addRow(self.lbl_rec)
        self.cmb_mode = QComboBox()
        fill_combo(self.cmb_mode, MODES, settings.cmyk_mode)
        f.addRow(tr("Methode:"), self.cmb_mode)
        row = QHBoxLayout()
        self.cmb_target = QComboBox()
        b_file = QPushButton(tr("Datei…"))
        b_file.setToolTip(tr("ICC-Profil von der Festplatte wählen (gilt für diese Sitzung)"))
        b_file.clicked.connect(self._pick_file)
        row.addWidget(self.cmb_target, 1)
        row.addWidget(b_file)
        f.addRow(tr("Zielprofil (Druckbedingung):"), row)
        self.cmb_source = QComboBox()
        f.addRow(tr("Vorhandenes CMYK ist:"), self.cmb_source)
        self.cmb_intent = QComboBox()
        fill_combo(self.cmb_intent, list(config.INTENTS.items()), settings.intent)
        f.addRow(tr("Render-Intent:"), self.cmb_intent)
        self.chk_bpc = QCheckBox(tr("Tiefenkompensierung (BPC)"))
        self.chk_bpc.setChecked(settings.bpc)
        self.chk_k = QCheckBox(tr("Grau und Schwarz nur mit Schwarz (K) drucken"))
        self.chk_k.setChecked(settings.gray_to_k)
        self.chk_oi = QCheckBox(tr("Zielprofil als Output Intent einbetten (für die Druckerei)"))
        self.chk_oi.setChecked(settings.output_intent)
        for c in (self.chk_bpc, self.chk_k, self.chk_oi):
            f.addRow(c)
        self.lbl_cmyk = QLabel()
        self.lbl_cmyk.setWordWrap(True)
        self.lbl_cmyk.setOpenExternalLinks(True)
        self.lbl_cmyk.setStyleSheet(f"color: {theme.MUTED};")
        f.addRow(self.lbl_cmyk)
        self.btn_preview = QPushButton(tr("Farbvorschau (vorher / nachher) …"))
        self.btn_preview.clicked.connect(self.open_preview)
        f.addRow(self.btn_preview)
        v.addWidget(g)

        # ---------------- Beschneiden ----------------
        g = self.grp_crop = QGroupBox(tr("Auf Format beschneiden"))
        f = QFormLayout(g)
        self.chk_crop = QCheckBox(tr("Seiten auf ein Zielformat bringen (Überstand beidseitig gleich)"))
        self.chk_crop.setChecked(settings.crop)
        f.addRow(self.chk_crop)
        self.cmb_size = QComboBox()
        items = [(k, f"{k}  ({w:g} × {h:g} mm)") for k, (w, h) in pdfmanip.FORMATS.items()]
        items += [("custom", tr("Benutzerdefiniert")),
                  (pdfmanip.TRIM_MODE, tr("Kanten abschneiden (kein Zielformat)")),
                  (pdfmanip.WHITEOUT_MODE, tr("Weißraum entfernen"))]
        fill_combo(self.cmb_size, items, settings.crop_size)
        f.addRow(tr("Modus:"), self.cmb_size)
        row = QHBoxLayout()
        self.spn_w = QDoubleSpinBox()
        self.spn_h = QDoubleSpinBox()
        for sp, val in ((self.spn_w, settings.crop_w_mm), (self.spn_h, settings.crop_h_mm)):
            sp.setRange(5, 5000)
            sp.setDecimals(1)
            sp.setSuffix(" mm")
            sp.setValue(val)
        row.addWidget(self.spn_w)
        row.addWidget(QLabel("×"))
        row.addWidget(self.spn_h)
        row.addStretch()
        self.row_wh = QWidget()
        self.row_wh.setLayout(row)
        f.addRow(tr("Breite × Höhe:"), self.row_wh)
        self.chk_follow = QCheckBox(tr("Hoch-/Querformat der jeweiligen Seite folgen"))
        self.chk_follow.setChecked(settings.crop_follow)
        f.addRow(self.chk_follow)
        self.chk_scale = QCheckBox(tr("Skalieren, bis das Format ganz gefüllt ist"))
        self.chk_scale.setChecked(settings.crop_scale)
        self.chk_scale.setToolTip(tr("An: die passende Kante wird genau aufs Zielformat skaliert, an der anderen "
                                     "wird der Überstand oben/unten bzw. links/rechts gleichmäßig abgeschnitten "
                                     "(z. B. A4 → A6 = 50 %). Aus: nur abschneiden, ohne Skalieren – für Dateien, "
                                     "die schon in der richtigen Größe mit Anschnitt kommen."))
        f.addRow(self.chk_scale)
        self.spn_inset = QDoubleSpinBox()
        self.spn_inset.setRange(0, 100)
        self.spn_inset.setDecimals(1)
        self.spn_inset.setSuffix(" mm")
        self.spn_inset.setValue(settings.crop_inset_mm)
        self.spn_inset.setToolTip(tr("Vorher rundum so viel von der Vorlage abschneiden – z. B. weiße Ränder eines "
                                     "Scans oder einer Datei ohne Anschnitt. Danach wird wie eingestellt skaliert "
                                     "und beschnitten."))
        f.addRow(tr("Weißen Rand vorher abschneiden:"), self.spn_inset)
        self.lbl_trim = QLabel(tr("Kanten abschneiden:"))
        f.addRow(self.lbl_trim)
        row = QHBoxLayout()
        self.spn_tl = QDoubleSpinBox(); self.spn_tt = QDoubleSpinBox()
        self.spn_tr = QDoubleSpinBox(); self.spn_tb = QDoubleSpinBox()
        for sp, val, lbl in ((self.spn_tl, settings.trim_l_mm, tr("links")),
                             (self.spn_tt, settings.trim_t_mm, tr("oben")),
                             (self.spn_tr, settings.trim_r_mm, tr("rechts")),
                             (self.spn_tb, settings.trim_b_mm, tr("unten"))):
            sp.setRange(0, 500); sp.setDecimals(1); sp.setSuffix(" mm"); sp.setValue(val)
            cell = QWidget()
            col = QVBoxLayout(cell)
            col.setContentsMargins(0, 0, 0, 0)
            lab = QLabel(lbl)
            lab.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            col.addWidget(lab)
            col.addWidget(sp)
            row.addWidget(cell)
        row.addStretch()
        self.row_trim = QWidget()
        self.row_trim.setLayout(row)
        f.addRow(self.row_trim)
        self.lbl_wm = QLabel(tr("Rand um den erkannten Inhalt:"))
        f.addRow(self.lbl_wm)
        self.spn_wm = QDoubleSpinBox()
        self.spn_wm.setRange(-10, 50); self.spn_wm.setDecimals(1); self.spn_wm.setSuffix(" mm")
        self.spn_wm.setValue(settings.white_margin_mm)
        self.spn_wm.setToolTip(tr("Abstand rund um den erkannten Inhalt. Negativ = zusätzlich in den Inhalt hineinschneiden."))
        f.addRow(self.spn_wm)
        self.lbl_crop = QLabel()
        self.lbl_crop.setWordWrap(True)
        self.lbl_crop.setStyleSheet(f"color: {theme.ACCENT};")
        f.addRow(self.lbl_crop)
        v.addWidget(g)
        v.addStretch()

        self._fill_profiles()
        for w in (self.chk_cmyk, self.chk_bpc, self.chk_k, self.chk_oi, self.chk_crop, self.chk_follow, self.chk_scale):
            w.toggled.connect(self._changed)
        for w in (self.cmb_mode, self.cmb_target, self.cmb_source, self.cmb_intent, self.cmb_size):
            w.currentIndexChanged.connect(self._changed)
        self.cmb_material.currentIndexChanged.connect(self._material_changed)
        for w in (self.spn_w, self.spn_h, self.spn_inset,
                  self.spn_tl, self.spn_tt, self.spn_tr, self.spn_tb, self.spn_wm):
            w.valueChanged.connect(self._changed)
        self._sync()
        fit_width(self)

    # -------------------------------------------------------------- #
    def _fill_profiles(self):
        profs = cmyk.find_profiles(self.cfg) + self.extra_profiles
        items = [(p.path, p.name + ("" if p.origin == "admin" else f"  [{tr('System')}]")) for p in profs]
        cur_t = self.cmb_target.currentData() or self.s.target or (profs[0].path if profs else "")
        cur_s = self.cmb_source.currentData() or self.s.source
        fill_combo(self.cmb_target, items or [("", tr("(kein CMYK-Profil gefunden)"))], cur_t)
        fill_combo(self.cmb_source, [("", tr("Ghostscript-Standard (SWOP)"))] + items, cur_s)
        if not profs:
            self.lbl_cmyk.setText(tr("Kein CMYK-Druckprofil gefunden. Profile der Standard-Druckbedingungen (z. B. "
                                     "PSO Coated v3 / FOGRA51, PSO Uncoated v3 / FOGRA52) gibt es kostenlos bei der "
                                     "ECI: ") + f'<a style="color:{theme.ACCENT}" href="{cmyk.ECI_URL}">eci.org</a>. '
                                  + tr("Einbinden über „Datei…“ oder im Admin unter Farbprofile."))

    def _material_changed(self, *_):
        """Material gewählt: Zielprofil + Intent vom Material, Methode nach der Datei (Ausgabebedingung, CMYK)."""
        import io
        from .. import colorlab
        m = colorlab.material_by_id(self.cfg, self.cmb_material.currentData() or "")
        self.material_white = list(m["white"]) if m and m.get("white") else None
        if m is None:
            self.lbl_rec.hide()
            return
        target = colorlab.cmyk_profile_of(self.cfg, m)
        if self.cmb_target.findData(target) < 0 and target:
            self.extra_profiles.append(cmyk.CmykProfile(cmyk._desc(target), target, "file"))
            self._fill_profiles()
        if self._facts is None and self.doc is not None:
            buf = io.BytesIO()
            try:
                self.doc.save(buf)
                self._facts = colorlab.doc_color_facts(buf.getvalue())
            except Exception:
                self._facts = ([], True)
        ois, has_cmyk = self._facts or ([], True)
        rec = colorlab.recommend_conversion(ois, has_cmyk, target, colorlab.candidates(self.cfg))
        for cmb, val in ((self.cmb_target, target), (self.cmb_mode, rec["mode"]), (self.cmb_source, rec["source"]),
                         (self.cmb_intent, m.get("intent") or "")):
            if val or cmb is self.cmb_source:
                i = cmb.findData(val)
                if i < 0 and cmb is self.cmb_source and val:
                    self.extra_profiles.append(cmyk.CmykProfile(cmyk._desc(val), val, "file"))
                    self._fill_profiles()
                    i = cmb.findData(val)
                if i >= 0:
                    cmb.setCurrentIndex(i)
        if not self.chk_cmyk.isHidden():
            self.chk_cmyk.setChecked(True)
        txt = rec["text"]
        if m.get("white"):
            pw = colorlab.profile_white(target)
            if pw:
                de = colorlab.delta_e(m["white"], pw)
                txt += " " + tr("Papierweiß zum Profil: ΔE {0:.1f} – {1}.").format(de, colorlab.verdict(de))
        self.lbl_rec.setText(txt)
        self.lbl_rec.show()

    def _pick_file(self):
        p, _ = QFileDialog.getOpenFileName(self, tr("ICC-Profil wählen"), "", tr("ICC-Profile (*.icc *.icm *.ICC *.ICM)"))
        if not p:
            return
        head = cmyk._icc_head(p)
        if not head or head[16:20] != b"CMYK":
            QMessageBox.warning(self, tr("Profil"), tr("Das ist kein CMYK-Profil."))
            return
        self.extra_profiles.append(cmyk.CmykProfile(cmyk._desc(p), p, "file"))
        self.s.target = p
        self._fill_profiles()
        self.cmb_target.setCurrentIndex(max(0, self.cmb_target.findData(p)))

    def _sync(self):
        on = self.chk_cmyk.isChecked()
        mode = self.cmb_mode.currentData()
        for w in (self.cmb_mode, self.btn_preview):
            w.setEnabled(on)
        for w in (self.cmb_target, self.cmb_intent, self.chk_bpc, self.chk_k, self.chk_oi):
            w.setEnabled(on and mode != "gray")
        self.cmb_source.setEnabled(on and mode == "all")
        if on and not cmyk.ghostscript():
            self.lbl_cmyk.setText(tr("⚠ Ghostscript fehlt – ohne Ghostscript ist keine CMYK-Umwandlung möglich."))
        crop = self.chk_crop.isChecked()
        mode = self.cmb_size.currentData()
        custom = mode == "custom"
        trim = mode == pdfmanip.TRIM_MODE
        whiteout = mode == pdfmanip.WHITEOUT_MODE
        fmt = not (trim or whiteout)
        f = self.grp_crop.layout()

        def show(w, on):
            w.setVisible(on)
            w.setEnabled(on)
            lab = f.labelForField(w)
            if lab is not None:
                lab.setVisible(on)

        self.cmb_size.setVisible(crop)            # Modus-Auswahl bleibt immer erreichbar
        self.cmb_size.setEnabled(crop)
        show(self.row_wh, crop and custom and fmt)
        for w in (self.chk_follow, self.chk_scale):
            show(w, crop and fmt)
        show(self.spn_inset, crop and fmt)
        self.lbl_trim.setVisible(crop and trim)
        self.row_trim.setVisible(crop and trim)
        for w in (self.spn_tl, self.spn_tt, self.spn_tr, self.spn_tb):
            w.setEnabled(crop and trim)
        self.lbl_wm.setVisible(crop and whiteout)
        show(self.spn_wm, crop and whiteout)
        self.lbl_crop.setVisible(crop)
        if crop and self.doc is not None:
            try:
                self.lbl_crop.setText(pdfmanip.describe_crop(self.doc, self.settings(), self.current))
            except Exception as e:
                self.lbl_crop.setText(str(e))

    def _changed(self, *_):
        s = self.settings()
        self.s.__dict__.update(s.__dict__)       # Sitzung aktualisieren
        self._sync()
        self.changed.emit()

    def set_current(self, page: int):
        self.current = page
        self._sync()

    def settings(self) -> cmyk.ManipSettings:
        s = cmyk.ManipSettings()
        s.cmyk = self.chk_cmyk.isChecked()
        s.cmyk_mode = self.cmb_mode.currentData() or "rgb_only"
        s.target = self.cmb_target.currentData() or ""
        s.source = self.cmb_source.currentData() or ""
        s.intent = self.cmb_intent.currentData() or "relative"
        s.bpc = self.chk_bpc.isChecked()
        s.gray_to_k = self.chk_k.isChecked()
        s.output_intent = self.chk_oi.isChecked()
        s.crop = self.chk_crop.isChecked()
        s.crop_size = self.cmb_size.currentData() or "A4"
        s.crop_w_mm, s.crop_h_mm = self.spn_w.value(), self.spn_h.value()
        s.crop_follow = self.chk_follow.isChecked()
        s.crop_scale = self.chk_scale.isChecked()
        s.crop_inset_mm = self.spn_inset.value()
        s.trim_l_mm, s.trim_t_mm = self.spn_tl.value(), self.spn_tt.value()
        s.trim_r_mm, s.trim_b_mm = self.spn_tr.value(), self.spn_tb.value()
        s.white_margin_mm = self.spn_wm.value()
        return s

    def load_settings(self, s: cmyk.ManipSettings):
        """Felder aus Einstellungen setzen (Preset). Ein Zielprofil, das es hier nicht gibt, wird gemeldet."""
        import os

        def pick(cmb, val):
            i = cmb.findData(val)
            if i >= 0:
                cmb.setCurrentIndex(i)
            return i >= 0
        missing = []
        for p in (s.target, s.source):
            if p and self.cmb_target.findData(p) < 0 and os.path.isfile(p):
                self.extra_profiles.append(cmyk.CmykProfile(cmyk._desc(p), p, "file"))
        self._fill_profiles()
        ws = [self.chk_cmyk, self.cmb_mode, self.cmb_target, self.cmb_source, self.cmb_intent, self.chk_bpc, self.chk_k,
              self.chk_oi, self.chk_crop, self.cmb_size, self.spn_w, self.spn_h, self.chk_follow, self.chk_scale,
              self.spn_inset, self.spn_tl, self.spn_tt, self.spn_tr, self.spn_tb, self.spn_wm]
        for w in ws:
            w.blockSignals(True)
        try:
            if not self.chk_cmyk.isHidden():
                self.chk_cmyk.setChecked(bool(s.cmyk))
            pick(self.cmb_mode, s.cmyk_mode)
            if s.target and not pick(self.cmb_target, s.target):
                missing.append(s.target)
            if not pick(self.cmb_source, s.source or "") and s.source:
                missing.append(s.source)
            pick(self.cmb_intent, s.intent)
            self.chk_bpc.setChecked(bool(s.bpc))
            self.chk_k.setChecked(bool(s.gray_to_k))
            self.chk_oi.setChecked(bool(s.output_intent))
            if not self.chk_crop.isHidden():
                self.chk_crop.setChecked(bool(s.crop))
            pick(self.cmb_size, s.crop_size)
            self.spn_w.setValue(s.crop_w_mm)
            self.spn_h.setValue(s.crop_h_mm)
            self.chk_follow.setChecked(bool(s.crop_follow))
            self.chk_scale.setChecked(bool(s.crop_scale))
            self.spn_inset.setValue(s.crop_inset_mm)
            self.spn_tl.setValue(s.trim_l_mm); self.spn_tt.setValue(s.trim_t_mm)
            self.spn_tr.setValue(s.trim_r_mm); self.spn_tb.setValue(s.trim_b_mm)
            self.spn_wm.setValue(s.white_margin_mm)
        finally:
            for w in ws:
                w.blockSignals(False)
        self._changed()
        if missing:
            QMessageBox.warning(self, tr("Preset"), tr("Dieses Farbprofil gibt es auf diesem Rechner nicht – bitte ein "
                                                       "anderes wählen:") + "\n" + "\n".join(missing))

    def open_preview(self):
        if self.doc is None:
            return
        s = self.settings()
        if s.cmyk_mode != "gray" and not s.target:
            QMessageBox.warning(self, tr("Farbvorschau"), tr("Bitte zuerst ein CMYK-Zielprofil wählen."))
            return
        ColorPreviewDialog(self, self.doc, s, self.current, self.material_white).exec()


# --------------------------------------------------------------------------- #
class _PreviewWorker(QThread):
    done = Signal(object, str)

    def __init__(self, path, page, s, dpi, paper, white=None):
        super().__init__()
        self.args = (path, page, s, dpi, paper, white)

    def run(self):
        try:
            path, page, s, dpi, paper, white = self.args
            self.done.emit(cmyk.render_preview(path, page, s, dpi, paper, white), "")
        except Exception as e:
            self.done.emit(None, str(e))


class ColorPreviewDialog(QDialog):
    """Before/after, individual separations and total ink coverage – computed from the real CMYK values."""

    VIEWS = [("both", "Vorher | Nachher"), ("after", "Nur Nachher"), ("c", "Auszug Cyan"), ("m", "Auszug Magenta"),
             ("y", "Auszug Gelb"), ("k", "Auszug Schwarz"), ("tac", "Farbauftrag (TAC) – Warnung")]

    def __init__(self, parent, doc, s: cmyk.ManipSettings, page: int = 0, white=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Farbvorschau – Passermark"))
        self.white = white
        self.resize(1200, 820)
        self.s = s
        self.tmp = tempfile.mkdtemp(prefix="passermark-cprev-")
        self.path = os.path.join(self.tmp, "doc.pdf")
        src = doc
        if s.crop:
            src, _ = pdfmanip.crop_doc(doc, s)
        src.save(self.path)
        self.n = len(src)
        if src is not doc:
            src.close()
        self.result = None
        self.worker = None

        v = QVBoxLayout(self)
        bar = QHBoxLayout()
        bar.addWidget(QLabel(tr("Seite:")))
        self.spn_page = QSpinBox()
        self.spn_page.setRange(1, self.n)
        self.spn_page.setValue(min(page + 1, self.n))
        self.spn_page.setKeyboardTracking(False)
        bar.addWidget(self.spn_page)
        bar.addSpacing(12)
        bar.addWidget(QLabel(tr("Ansicht:")))
        self.cmb_view = QComboBox()
        views = self.VIEWS if s.cmyk_mode != "gray" else self.VIEWS[:2]
        fill_combo(self.cmb_view, views, "both")
        bar.addWidget(self.cmb_view)
        bar.addSpacing(12)
        bar.addWidget(QLabel(tr("Grenze:")))
        self.spn_tac = QSpinBox()
        self.spn_tac.setRange(100, 400)
        self.spn_tac.setSingleStep(10)
        self.spn_tac.setValue(300)
        self.spn_tac.setSuffix(" %")
        self.spn_tac.setToolTip(tr("Maximaler Farbauftrag der Druckbedingung (gestrichen meist 300–330 %, ungestrichen 280–300 %)"))
        bar.addWidget(self.spn_tac)
        self.chk_paper = QCheckBox(tr("Papierweiß simulieren") + (tr(" (gemessen)") if white else ""))
        bar.addWidget(self.chk_paper)
        bar.addWidget(QLabel(tr("Auflösung:")))
        self.cmb_dpi = QComboBox()
        fill_combo(self.cmb_dpi, [(72, "72 dpi"), (100, "100 dpi"), (150, "150 dpi"), (200, "200 dpi")], 100)
        bar.addWidget(self.cmb_dpi)
        bar.addStretch()
        v.addLayout(bar)

        self.split = QSplitter(Qt.Orientation.Horizontal)
        self.lbl_a, self.lbl_b = QLabel(), QLabel()
        for lb in (self.lbl_a, self.lbl_b):
            lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sa = QScrollArea()
            sa.setWidgetResizable(True)
            sa.setWidget(lb)
            sa.setStyleSheet(f"QScrollArea {{ background: {theme.VIEW}; }}")
            self.split.addWidget(sa)
        v.addWidget(self.split, 1)
        self.lbl_info = QLabel()
        self.lbl_info.setWordWrap(True)
        v.addWidget(self.lbl_info)
        note = QLabel(tr("„Nachher“ entsteht mit denselben Ghostscript-Einstellungen wie die Umwandlung und wird über "
                         "das Zielprofil (LittleCMS) auf den Bildschirm gerechnet. Auszüge und Farbauftrag stammen aus "
                         "den tatsächlichen CMYK-Werten. Genau so genau wie Profil und Monitorkalibrierung."))
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {theme.MUTED};")
        v.addWidget(note)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

        self.spn_page.valueChanged.connect(self._render)
        self.cmb_dpi.currentIndexChanged.connect(self._render)
        self.chk_paper.toggled.connect(self._render)
        self.cmb_view.currentIndexChanged.connect(self._show)
        self.spn_tac.valueChanged.connect(self._show)
        self._render()

    def _render(self, *_):
        if self.worker is not None and self.worker.isRunning():
            return
        self.lbl_info.setText(tr("Berechne Vorschau …"))
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.worker = _PreviewWorker(self.path, self.spn_page.value() - 1, self.s,
                                     self.cmb_dpi.currentData(), self.chk_paper.isChecked(), self.white)
        self.worker.done.connect(self._done)
        self.worker.start()

    def _done(self, res, err):
        QApplication.restoreOverrideCursor()
        if err:
            self.lbl_info.setText("⚠ " + err)
            return
        self.result = res
        self._show()

    def _show(self, *_):
        r = self.result
        if r is None:
            return
        view = self.cmb_view.currentData()
        info = []
        right = r.after
        if r.cmyk is not None:
            mx, pct, warn = cmyk.tac(r.cmyk, self.spn_tac.value())
            info.append(tr("Max. Farbauftrag: {0:.0f} %  ·  über {1} %: {2:.2f} % der Fläche").format(
                mx, self.spn_tac.value(), pct))
            if view in ("c", "m", "y", "k"):
                right = cmyk.separation(r.cmyk, "cmyk".index(view))
            elif view == "tac":
                right = warn
        left = r.before if view == "both" else None
        self.split.widget(0).setVisible(left is not None)
        if left is not None:
            self.lbl_a.setPixmap(pil_to_pixmap(left))
        self.lbl_b.setPixmap(pil_to_pixmap(right))
        self.lbl_info.setText("   ".join(info))

    def done(self, r):
        if self.worker is not None:
            self.worker.wait(30000)
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().done(r)


# --------------------------------------------------------------------------- #
class ManipDialog(QDialog):
    """From the Document manipulation menu: apply to the whole document -> result in a new window.

        mode: "cmyk" (conversion only), "crop" (cropping only) or "all" (both).
    """

    TITLES = {"cmyk": "CMYK-Umwandlung – Passermark", "crop": "Auf Format beschneiden – Passermark",
              "all": "Dokument-Manipulation – Passermark"}

    def __init__(self, parent, doc, session, current: int = 0, mode: str = "all"):
        super().__init__(parent)
        self.mode = mode
        self.setWindowTitle(tr(self.TITLES.get(mode, self.TITLES["all"])))
        self.resize(640, 720 if mode != "crop" else 420)
        self.doc, self.session = doc, session
        v = QVBoxLayout(self)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.panel = ManipPanel(self, session.manip, session.cfg, doc, current)
        from .presetbar import PresetBar
        self.presetbar = PresetBar(self, "manip", self.panel.settings, self.panel.load_settings)
        v.addWidget(self.presetbar)
        sa.setWidget(self.panel)
        v.addWidget(sa, 1)
        if mode == "cmyk":
            self.panel.grp_crop.hide()
            self.panel.chk_cmyk.setChecked(True)
            self.panel.chk_cmyk.hide()            # in diesem Dialog immer an
        elif mode == "crop":
            self.panel.grp_cmyk.hide()
            self.panel.chk_crop.setChecked(True)
            self.panel.chk_crop.hide()
        hint = QLabel(tr("Das Ergebnis öffnet sich in einem neuen Fenster und liegt vorerst nur im Zwischenspeicher. "
                         "Zum Behalten „Speichern unter …“ verwenden; gedruckt wird es wie jedes andere Dokument."))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {theme.MUTED};")
        v.addWidget(hint)
        bb = QDialogButtonBox()
        self.btn_apply = bb.addButton(tr("Anwenden (neues Fenster)"), QDialogButtonBox.ButtonRole.AcceptRole)
        self.btn_apply.setDefault(True)
        bb.addButton(tr("Schließen"), QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(self._apply)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.new_doc = None
        self.notes = []
        self.job = None

    def _apply(self):
        s = self.panel.settings()
        if self.mode == "cmyk":
            s.crop = False
        elif self.mode == "crop":
            s.cmyk = False
        if not s.active:
            QMessageBox.information(self, tr("Nichts zu tun"), tr("Bitte CMYK-Umwandlung und/oder Beschneiden aktivieren."))
            return
        # nur den Auftrag beschreiben – gerechnet wird im Hintergrund (eigener Prozess)
        from .. import core
        self.job = ("manip", core.settings_to_dict(s), None)
        self.accept()
