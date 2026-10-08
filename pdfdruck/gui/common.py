# SPDX-License-Identifier: GPL-3.0-or-later
# pdfToolkit – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Gemeinsame GUI-Hilfen und der (nur im RAM gehaltene) Sitzungszustand."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QComboBox

from .. import printers
from ..l10n import tr
from ..layout import LayoutSettings


def render_pixmap(page, scale: float, rotation: int = 0, dpr: float = 1.0) -> QPixmap:
    """Rendert eine pdfium-Seite als QPixmap (BGRX -> QImage.Format.Format_RGB32)."""
    bmp = page.render(scale=scale * dpr, rotation=rotation % 360, prefer_bgrx=True,
                      may_draw_forms=True, draw_annots=True)
    fmt = QImage.Format.Format_RGB32 if bmp.n_channels == 4 else QImage.Format.Format_BGR888
    img = QImage(bytes(bmp.buffer), bmp.width, bmp.height, bmp.stride, fmt).copy()
    bmp.close()
    pm = QPixmap.fromImage(img)
    pm.setDevicePixelRatio(dpr)
    return pm


def fill_combo(combo: QComboBox, choices, current):
    """choices: Liste (wert, text). Alle Einträge bleiben IMMER wählbar."""
    combo.blockSignals(True)
    combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    combo.setMinimumContentsLength(8)
    combo.clear()
    for val, text in choices:
        text = tr(text)
        combo.addItem(text, val)
        if str(text) != str(val):
            combo.setItemData(combo.count() - 1, f"Treiberwert: {val}", Qt.ItemDataRole.ToolTipRole)
    i = combo.findData(current)
    combo.setCurrentIndex(i if i >= 0 else 0)
    combo.blockSignals(False)


def fit_width(root):
    """Keine horizontale Scrollleiste: Formulare brechen um (Beschriftung über das Feld),
    Auswahlfelder dürfen schmaler werden als ihr längster Eintrag."""
    from PySide6.QtWidgets import QAbstractScrollArea, QFormLayout, QSizePolicy
    for f in root.findChildren(QFormLayout):
        f.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        f.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    for cb in root.findChildren(QComboBox):
        cb.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        cb.setMinimumContentsLength(min(cb.minimumContentsLength() or 8, 8))
        cb.setSizePolicy(QSizePolicy.Policy.Expanding, cb.sizePolicy().verticalPolicy())
    from PySide6.QtWidgets import QAbstractSpinBox
    for sp in root.findChildren(QAbstractSpinBox):
        # Wert erst bei Enter/Feldwechsel/Pfeiltasten übernehmen – nicht nach jeder getippten Ziffer
        # (sonst entstehen beim Tippen kurz Zwischenwerte wie „1 mm“ -> zehntausende Nutzen)
        sp.setKeyboardTracking(False)
    for sa in root.findChildren(QAbstractScrollArea):
        if sa.metaObject().className() == "QScrollArea":
            sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)


def guard_wheel(root):
    """Mausrad-Schutz läuft global (theme.WheelGuard) – hier bewusst nichts mehr zu tun."""
    return None


class Session:
    """Benutzeränderungen dieser Programmsitzung. Wird NIE gespeichert.

    Beim nächsten Start werden wieder die Admin-Standards aus /etc geladen –
    das ist das "Zurückstellen beim Beenden", absturzsicher ohne Cleanup.
    """

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.printer: str | None = cfg.get("default_printer") or None
        self.layout = LayoutSettings.from_dict(cfg.get("layout"))
        self.values: dict[str, dict[str, str]] = {}       # drucker -> Optionen
        self.color: dict[str, tuple[str, str]] = {}       # drucker -> (profil-id, intent)
        self.caps: dict[str, printers.PrinterCaps] = {}
        self.copies = 1
        self.collate = True
        self.subset = "all"
        self.reverse = False

    def caps_for(self, name: str, reload: bool = False) -> printers.PrinterCaps:
        if reload or name not in self.caps:
            self.caps[name] = printers.pdf_caps() if name == printers.PDF_TARGET else printers.load_caps(name)
        return self.caps[name]

    def values_for(self, name: str) -> dict[str, str]:
        if name not in self.values:
            caps = self.caps_for(name)
            vals = caps.defaults()
            admin = self.cfg.get("printers", {}).get(name, {}).get("options", {})
            for k, v in admin.items():
                opt = caps.options.get(k)
                if opt and not opt.installable and any(c.value == v for c in opt.choices):
                    vals[k] = v
            pc = self.cfg.get("printers", {}).get(name, {})
            if caps.backend == "win" and pc.get("devmode"):
                vals["__devmode__"] = pc["devmode"]          # Herstellereinstellungen (Finisher …)
            self.values[name] = vals
        return self.values[name]

    def color_for(self, name: str) -> tuple[str, str]:
        if name not in self.color:
            pc = self.cfg.get("printers", {}).get(name, {})
            self.color[name] = (pc.get("color_profile", ""), pc.get("intent", "relative"))
        return self.color[name]
