# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
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
    """Einstellungen der Dokument-Manipulation. Signal `changed` bei jeder Änderung."""
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
        self.chk_crop = QCheckBox(tr("Seiten auf ein Zielformat beschneiden (Überstand beidseitig gleich)"))
        self.chk_crop.setChecked(settings.crop)
        f.addRow(self.chk_crop)
        self.cmb_size = QComboBox()
        fill_combo(self.cmb_size, [(k, f"{k}  ({w:g} × {h:g} mm)") for k, (w, h) in pdfmanip.FORMATS.items()]
                   + [("custom", tr("Benutzerdefiniert"))], settings.crop_size)
        f.addRow(tr("Zielformat:"), self.cmb_size)
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
        f.addRow(tr("Breite × Höhe:"), row)
        self.chk_follow = QCheckBox(tr("Hoch-/Querformat der jeweiligen Seite folgen"))
        self.chk_follow.setChecked(settings.crop_follow)
        f.addRow(self.chk_follow)
        self.lbl_crop = QLabel()
        self.lbl_crop.setWordWrap(True)
        self.lbl_crop.setStyleSheet(f"color: {theme.ACCENT};")
        f.addRow(self.lbl_crop)
        v.addWidget(g)
        v.addStretch()

        self._fill_profiles()
        for w in (self.chk_cmyk, self.chk_bpc, self.chk_k, self.chk_oi, self.chk_crop, self.chk_follow):
            w.toggled.connect(self._changed)
        for w in (self.cmb_mode, self.cmb_target, self.cmb_source, self.cmb_intent, self.cmb_size):
            w.currentIndexChanged.connect(self._changed)
        for w in (self.spn_w, self.spn_h):
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
        custom = self.cmb_size.currentData() == "custom"
        for w in (self.cmb_size, self.chk_follow):
            w.setEnabled(crop)
        self.spn_w.setEnabled(crop and custom)
        self.spn_h.setEnabled(crop and custom)
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
        return s

    def open_preview(self):
        if self.doc is None:
            return
        s = self.settings()
        if s.cmyk_mode != "gray" and not s.target:
            QMessageBox.warning(self, tr("Farbvorschau"), tr("Bitte zuerst ein CMYK-Zielprofil wählen."))
            return
        ColorPreviewDialog(self, self.doc, s, self.current).exec()


# --------------------------------------------------------------------------- #
class _PreviewWorker(QThread):
    done = Signal(object, str)

    def __init__(self, path, page, s, dpi, paper):
        super().__init__()
        self.args = (path, page, s, dpi, paper)

    def run(self):
        try:
            path, page, s, dpi, paper = self.args
            self.done.emit(cmyk.render_preview(path, page, s, dpi, paper), "")
        except Exception as e:
            self.done.emit(None, str(e))


class ColorPreviewDialog(QDialog):
    """Vorher/Nachher, Einzelauszüge und Farbauftrag – aus den echten CMYK-Werten berechnet."""

    VIEWS = [("both", "Vorher | Nachher"), ("after", "Nur Nachher"), ("c", "Auszug Cyan"), ("m", "Auszug Magenta"),
             ("y", "Auszug Gelb"), ("k", "Auszug Schwarz"), ("tac", "Farbauftrag (TAC) – Warnung")]

    def __init__(self, parent, doc, s: cmyk.ManipSettings, page: int = 0):
        super().__init__(parent)
        self.setWindowTitle(tr("Farbvorschau – Passermark"))
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
        self.chk_paper = QCheckBox(tr("Papierweiß simulieren"))
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
                                     self.cmb_dpi.currentData(), self.chk_paper.isChecked())
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
    """Aus dem Menü Dokument-Manipulation: auf das ganze Dokument anwenden -> Ergebnis im neuen Fenster.

    mode: "cmyk" (nur Umwandlung), "crop" (nur Beschneiden) oder "all" (beides).
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
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.panel = ManipPanel(self, session.manip, session.cfg, doc, current)
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

    def _apply(self):
        s = self.panel.settings()
        if self.mode == "cmyk":
            s.crop = False
        elif self.mode == "crop":
            s.cmyk = False
        if not s.active:
            QMessageBox.information(self, tr("Nichts zu tun"), tr("Bitte CMYK-Umwandlung und/oder Beschneiden aktivieren."))
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            from ..layout import flattened
            flat = flattened(self.doc)
            self.new_doc, self.notes = pdfmanip.apply(flat, s)
            if flat is not self.doc and flat is not self.new_doc:
                flat.close()
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, tr("Fehler"), str(e))
            return
        QApplication.restoreOverrideCursor()
        self.accept()
