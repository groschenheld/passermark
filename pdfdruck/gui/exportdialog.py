# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""File → Export as image: format, resolution, pages, colour – the export itself runs as a job in the background
(passermark-cli export, rasterexport.py). The last choices are remembered (user setting "image_export")."""

from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import l10n, rasterexport
from ..l10n import tr
from . import theme

SETTING = "image_export"
DPIS = (72, 150, 300, 600)


class ExportImageDialog(QDialog):
    """Settings of the image export; ``result_settings()`` and ``result_pages()`` after OK."""

    def __init__(self, parent, page_count: int, current: int, selection: list[int]):
        super().__init__(parent)
        self.setWindowTitle(tr("Als Bild exportieren"))
        self.page_count, self.current, self.selection = page_count, current, selection
        last = l10n.load_settings().get(SETTING) or {}
        v = QVBoxLayout(self)
        f = QFormLayout()
        v.addLayout(f)

        self.cmb_format = QComboBox()
        for key, label in (("png", "PNG"), ("jpg", "JPG"), ("tiff", "TIFF")):
            self.cmb_format.addItem(label, key)
        self.cmb_format.setCurrentIndex(max(0, self.cmb_format.findData(last.get("format", "png"))))
        f.addRow(tr("Format:"), self.cmb_format)

        self.cmb_dpi = QComboBox()
        self.cmb_dpi.setEditable(True)
        for d in DPIS:
            self.cmb_dpi.addItem(f"{d}", d)
        self.cmb_dpi.setCurrentText(str(int(last.get("dpi", 150))))
        self.cmb_dpi.setToolTip(tr("72 = Bildschirm, 150 = Vorschau und Web, 300 = Druck, 600 = feine Linien"))
        f.addRow(tr("Auflösung (dpi):"), self.cmb_dpi)

        # pages
        pages = QWidget()
        ph = QHBoxLayout(pages)
        ph.setContentsMargins(0, 0, 0, 0)
        self.grp_pages = QButtonGroup(self)
        for i, text in enumerate(
            (
                tr("Alle ({0})").format(page_count),
                tr("Aktuelle Seite ({0})").format(current + 1),
                tr("Auswahl ({0})").format(len(selection)),
            )
        ):
            rb = QRadioButton(text)
            self.grp_pages.addButton(rb, i)
            ph.addWidget(rb)
        self.grp_pages.button(2).setEnabled(len(selection) > 1)
        self.grp_pages.button(2 if len(selection) > 1 else 0).setChecked(True)
        f.addRow(tr("Seiten:"), pages)

        self.cmb_color = QComboBox()
        self.cmb_color.addItem(tr("RGB"), "rgb")
        self.cmb_color.addItem(tr("Graustufen"), "gray")
        self.cmb_color.addItem(tr("CMYK (mit Druckprofil)"), "cmyk")
        self.cmb_color.setCurrentIndex(max(0, self.cmb_color.findData(last.get("color", "rgb"))))
        f.addRow(tr("Farbe:"), self.cmb_color)

        self.cmb_profile = QComboBox()
        self.cmb_profile.setToolTip(
            tr("CMYK wird mit Ghostscript und diesem Profil separiert; vorhandenes CMYK bleibt, RGB wird umgerechnet.")
        )
        from .. import cmyk, config

        for p in cmyk.find_profiles(config.load()):
            self.cmb_profile.addItem(p.name, p.path)
        i = self.cmb_profile.findData(last.get("profile", ""))
        self.cmb_profile.setCurrentIndex(max(0, i))
        self.lbl_profile = QLabel(tr("Profil:"))
        f.addRow(self.lbl_profile, self.cmb_profile)

        self.chk_transparent = QCheckBox(tr("Hintergrund durchsichtig statt weiß"))
        self.chk_transparent.setChecked(bool(last.get("transparent", False)))
        f.addRow("", self.chk_transparent)

        self.spn_quality = QSpinBox()
        self.spn_quality.setRange(1, 100)
        self.spn_quality.setValue(int(last.get("quality", 90)))
        self.spn_quality.setSuffix(" %")
        self.lbl_quality = QLabel(tr("JPG-Qualität:"))
        f.addRow(self.lbl_quality, self.spn_quality)

        self.cmb_comp = QComboBox()
        self.cmb_comp.addItem(tr("LZW (verlustfrei)"), "lzw")
        self.cmb_comp.addItem(tr("ZIP (verlustfrei, meist kleiner)"), "zip")
        self.cmb_comp.addItem(tr("keine"), "none")
        self.cmb_comp.setCurrentIndex(max(0, self.cmb_comp.findData(last.get("compression", "lzw"))))
        self.lbl_comp = QLabel(tr("Komprimierung:"))
        f.addRow(self.lbl_comp, self.cmb_comp)

        self.chk_multi = QCheckBox(tr("Alle Seiten in eine TIFF-Datei"))
        self.chk_multi.setChecked(bool(last.get("multipage", False)))
        f.addRow("", self.chk_multi)

        self.lbl_names = QLabel()
        self.lbl_names.setWordWrap(True)
        self.lbl_names.setStyleSheet(f"color: {theme.MUTED};")
        v.addWidget(self.lbl_names)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Exportieren …"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

        for w in (self.cmb_format, self.cmb_color):
            w.currentIndexChanged.connect(self._sync)
        self.grp_pages.idClicked.connect(lambda _i: self._sync())
        self.chk_multi.toggled.connect(lambda _on: self._sync())
        self._sync()

    def _sync(self):
        """Show only what fits the format; PNG has no CMYK."""
        fmt = self.cmb_format.currentData()
        cmyk_item = self.cmb_color.model().item(2)
        if cmyk_item is not None:
            cmyk_item.setEnabled(fmt != "png")
        if fmt == "png" and self.cmb_color.currentData() == "cmyk":
            self.cmb_color.setCurrentIndex(0)
        cmyk = self.cmb_color.currentData() == "cmyk"
        for w in (self.lbl_profile, self.cmb_profile):
            w.setVisible(cmyk)
        self.chk_transparent.setVisible(fmt == "png" and self.cmb_color.currentData() != "gray")
        for w in (self.lbl_quality, self.spn_quality):
            w.setVisible(fmt == "jpg")
        for w in (self.lbl_comp, self.cmb_comp):
            w.setVisible(fmt == "tiff")
        n = len(self.result_pages())
        self.chk_multi.setVisible(fmt == "tiff" and n > 1)
        if n > 1 and not (fmt == "tiff" and self.chk_multi.isChecked()):
            self.lbl_names.setText(
                tr("{0} Seiten – je Seite eine Datei: name-001, name-002 … (Seitennummer)").format(n)
            )
        else:
            self.lbl_names.setText("")
        self.adjustSize()

    def result_pages(self) -> list[int]:
        """0-based page numbers to export."""
        which = self.grp_pages.checkedId()
        if which == 1:
            return [self.current]
        if which == 2:
            return sorted(self.selection)
        return list(range(self.page_count))

    def result_settings(self) -> rasterexport.ExportSettings:
        """The chosen settings (also remembered for next time)."""
        try:
            dpi = float(self.cmb_dpi.currentText().replace(",", "."))
        except ValueError:
            dpi = 150.0
        if dpi <= 0:
            dpi = 150.0
        color = str(self.cmb_color.currentData() or "rgb")
        fmt = str(self.cmb_format.currentData() or "png")
        # decided by format and colour, not by isVisible(): after exec() the dialog is hidden
        s = rasterexport.ExportSettings(
            format=fmt,
            dpi=dpi,
            color=color,
            profile=str(self.cmb_profile.currentData() or "") if color == "cmyk" else "",
            transparent=bool(self.chk_transparent.isChecked() is True and fmt == "png" and color != "gray"),
            quality=int(self.spn_quality.value()),
            compression=str(self.cmb_comp.currentData() or "lzw"),
            multipage=bool(self.chk_multi.isChecked() is True and fmt == "tiff"),
        )
        st = l10n.load_settings()
        st[SETTING] = {k: v for k, v in vars(s).items() if k != "out"}
        try:
            l10n.save_settings(st)
        except OSError:
            pass  # remembering is a convenience
        return s


def default_name(display_name: str, fmt: str, folder: str = "") -> str:
    """Suggested target file: document name with the extension of the format."""
    base = os.path.splitext(display_name or tr("Dokument"))[0]
    return os.path.join(folder, base + rasterexport.FORMATS[fmt])
