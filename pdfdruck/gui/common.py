# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
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
            # nichts abschneiden: wird das Fenster schmaler als der Inhalt, gibt es eine waagrechte Leiste
            sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)


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
        from ..cmyk import ManipSettings
        self.manip = ManipSettings()          # Dokument-Manipulation (nur diese Sitzung)
        self.copies = 1
        self.collate = True
        self.subset = "all"
        self.reverse = False

    def caps_for(self, name: str, reload: bool = False) -> printers.PrinterCaps:
        if reload or name not in self.caps:
            self.caps[name] = printers.pdf_caps() if name == printers.PDF_TARGET else printers.load_caps(name)
            try:
                printers.apply_custom_sizes(self.caps[name])      # Sonderformate des Benutzers
            except Exception:
                pass
        return self.caps[name]

    def refresh_custom_sizes(self):
        sizes = printers.load_custom_sizes()
        for c in self.caps.values():
            printers.apply_custom_sizes(c, sizes)

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
        try:                                     # nie größer als der Bildschirm (kleine Notebooks)
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
    """Enter in einem Eingabefeld löst nicht den Standardknopf aus (z. B. „Erzeugen“) – nur ein Klick."""
    from PySide6.QtWidgets import QPushButton
    for b in dialog.findChildren(QPushButton):
        b.setAutoDefault(False)
        b.setDefault(False)
