# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, Version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Gemeinsame GUI-Hilfen und der (nur im RAM gehaltene) Sitzungszustand."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QComboBox, QToolButton, QVBoxLayout, QWidget

from .. import printers
from ..l10n import tr
from ..layout import LayoutSettings  # noqa: F401  (früher hier gebraucht)
from ..session import Session  # noqa: F401  (Sitzung liegt ohne Qt in pdfdruck.session)
from . import theme


class CollapsibleSection(QWidget):
    """Einklappbare Gruppe: die Titelzeile bleibt immer sichtbar, der Inhalt nur bei Bedarf.
    Einheitlicher Abschnitts-Stil (fett, Akzentfarbe) – Druckdialog und VDP-Dialog."""

    def __init__(self, title: str, parent=None, expanded: bool = False):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.btn = QToolButton()
        self.btn.setText(title)
        self.btn.setCheckable(True)
        self.btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn.setArrowType(Qt.ArrowType.RightArrow)
        self.btn.setStyleSheet(f"QToolButton {{ font-weight: bold; border: none; color: {theme.ACCENT}; }}")
        self.btn.toggled.connect(self._toggle)
        v.addWidget(self.btn)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(2, 8, 2, 0)
        v.addWidget(self.body)
        self._toggle(expanded)

    def _toggle(self, on: bool):
        self.body.setVisible(on)
        self.btn.setArrowType(Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow)


# Render-Limit: Riesen-/fehlerhafte Seiten blockieren die Ansicht nicht mehr.
# Höchstens 8192 px je Kante bzw. 40 Megapixel rendern, dann weich hochskalieren.
MAX_RENDER_EDGE = 8192
MAX_RENDER_PIXELS = 40_000_000


def render_pixmap(page, scale: float, rotation: int = 0, dpr: float = 1.0) -> QPixmap:
    """Rendert eine pdfium-Seite als QPixmap (BGRX -> QImage.Format.Format_RGB32).

    Größenlimit: Seiten, die im Zoom gigapiselig würden (oder kaputte Massangaben
    haben), werden höchstens 8192 px je Kante bzw. 40 Megapixel gerendert und
    anschließend weich auf die Zielgröße hochskaliert – das Zoomen bleibt flüssig."""
    rot = rotation % 360
    w, h = page.get_size()
    if rot % 180:
        w, h = h, w
    sc = scale * dpr
    lim = min(1.0,
              MAX_RENDER_EDGE / max(1.0, w * sc),
              MAX_RENDER_EDGE / max(1.0, h * sc),
              (MAX_RENDER_PIXELS / max(1.0, w * sc * h * sc)) ** 0.5)
    bmp = page.render(scale=sc * lim, rotation=rot, prefer_bgrx=True,
                      may_draw_forms=True, draw_annots=True)
    fmt = QImage.Format.Format_RGB32 if bmp.n_channels == 4 else QImage.Format.Format_BGR888
    img = QImage(bytes(bmp.buffer), bmp.width, bmp.height, bmp.stride, fmt).copy()
    bmp.close()
    if lim < 1.0:                                   # Renderlimit erreicht: weich hochskalieren
        img = img.scaled(max(1, round(w * sc)), max(1, round(h * sc)),
                         Qt.AspectRatioMode.IgnoreAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    pm = QPixmap.fromImage(img)
    pm.setDevicePixelRatio(dpr)
    return pm


def fill_combo(combo: QComboBox, choices, current):
    """choices: list of (value, text). All entries remain selectable ALWAYS."""
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
    """No horizontal scrollbar: forms wrap (label above the field),
        selection fields may become narrower than their longest entry.
    """
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
        # apply the value only on Enter/field change/arrow keys – not after every typed digit
        # (sonst entstehen beim Tippen kurz Zwischenwerte wie „1 mm“ -> zehntausende Nutzen)
        sp.setKeyboardTracking(False)
    for sa in root.findChildren(QAbstractScrollArea):
        if sa.metaObject().className() == "QScrollArea":
            # nichts abschneiden: wird das Fenster schmaler als der Inhalt, gibt es eine waagrechte Leiste
            sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)


def guard_wheel(root):
    """Mouse-wheel protection runs globally (theme.WheelGuard) – deliberately nothing to do here."""
    return None


def window_modal_dialogs():
    """QDialog.exec() sperrt sonst das ganze Programm (alle Fenster). Mit Elternfenster nur noch dieses Fenster –
    in anderen Passermark-Fenstern kann man weiterarbeiten (Druckdialog offen lassen, anderes Dokument ansehen)."""
    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtWidgets import QDialog
    if getattr(QDialog, "_pm_window_modal", False):
        return
    orig = QDialog.exec

    def exec_(self, *a, **k):
        try:
            if self.parentWidget() is not None and self.windowModality() != _Qt.WindowModality.WindowModal:
                self.setWindowModality(_Qt.WindowModality.WindowModal)
        except Exception:
            pass
        try:                                     # never larger than the screen (small notebooks)
            scr = (self.parentWidget() or self).screen().availableGeometry()
            w, h = min(self.width(), scr.width() - 40), min(self.height(), scr.height() - 60)
            if (w, h) != (self.width(), self.height()):
                self.resize(max(320, w), max(240, h))
        except Exception:
            pass
        return orig(self, *a, **k)
    QDialog.exec = exec_
    QDialog._pm_window_modal = True


def split_panels(root, left, right, right_width: int = 420):
    """Vorschau links, Einstellungen rechts – mit verschiebbarem Teiler; rechts scrollbar (senkrecht und waagrecht),
    damit bei kleinem Fenster nichts abgeschnitten wird. left/right: Layout oder Widget."""
    from PySide6.QtWidgets import QFrame, QLayout, QScrollArea, QSplitter, QWidget

    def as_widget(x):
        if isinstance(x, QLayout):
            w = QWidget()
            w.setLayout(x)
            return w
        return x
    lw, rw = as_widget(left), as_widget(right)
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.Shape.NoFrame)
    sa.setWidget(rw)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    sa.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    sa.setMinimumWidth(260)
    sp = QSplitter(Qt.Orientation.Horizontal)
    sp.addWidget(lw)
    sp.addWidget(sa)
    sp.setStretchFactor(0, 1)
    sp.setStretchFactor(1, 0)
    sp.setChildrenCollapsible(False)
    sp.setSizes([900, right_width])
    root.addWidget(sp)
    return sp


def no_enter_default(dialog):
    """Enter in an input field does not trigger the default button (e.g. "Create") – only a click does."""
    from PySide6.QtWidgets import QPushButton
    for b in dialog.findChildren(QPushButton):
        b.setAutoDefault(False)
        b.setDefault(False)
