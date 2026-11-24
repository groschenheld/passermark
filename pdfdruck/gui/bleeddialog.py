# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Dialog "Anschnitt erzeugen": bleed for customer files without it – mirror or stretch the edges (bleedgen.py)."""

from __future__ import annotations

import io

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QRadioButton,
    QVBoxLayout,
)

from .. import bleedgen, l10n
from ..l10n import tr

MM = 72.0 / 25.4


def page_state(data: bytes, index: int) -> tuple:
    """(final format w × h in mm, existing bleed in mm) of a page."""
    import pikepdf

    with pikepdf.open(io.BytesIO(data)) as pdf:
        pg = pdf.pages[index]
        t = bleedgen.final_format(pg)
        return ((t[2] - t[0]) / MM, (t[3] - t[1]) / MM), bleedgen.existing_bleed(pg) / MM


def _n(v: float) -> str:
    t = f"{v:.1f}"
    return t if l10n.current() == "en" else t.replace(".", ",")


def state_text(size: tuple, have: float, want: float) -> str:
    """Line under the intro: final format of the current page and what happens to it."""
    fmt = f"{_n(size[0])} × {_n(size[1])} mm"
    if have >= want - 0.05:
        return tr("Aktuelle Seite: Endformat {0}, hat schon {1} mm Anschnitt – bleibt unverändert.").format(
            fmt, _n(have)
        )
    return tr("Aktuelle Seite: Endformat {0}, Anschnitt bisher {1} mm → neu {2} mm, die Seite wird größer.").format(
        fmt, _n(have), _n(want)
    )


class BleedDialog(QDialog):
    """Bleed in mm, mirror or stretch, which pages."""

    def __init__(self, parent, data: bytes, current: int, page_count: int, selection=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Anschnitt erzeugen"))
        self.current, self.page_count = current, page_count
        self.selection = sorted(selection or [])
        try:
            self.size, self.have = page_state(data, current)
        except Exception:  # noqa: BLE001 – damaged page: the dialog still works
            self.size, self.have = (0.0, 0.0), 0.0
        saved = l10n.load_settings().get("bleedgen") or {}
        v = QVBoxLayout(self)
        intro = QLabel(
            tr(
                "Für Kundendateien ohne Anschnitt: Die Seite wird ringsum um den Anschnitt größer, der Rand "
                "wird aus dem Inhalt am Rand gefüllt. Endformat ist die TrimBox – fehlt sie, die Seite, wie sie "
                "ist. Seiten mit genug Anschnitt bleiben unverändert."
            )
        )
        intro.setWordWrap(True)
        v.addWidget(intro)
        f = QFormLayout()
        self.sp_bleed = QDoubleSpinBox()
        self.sp_bleed.setRange(0.5, 20)
        self.sp_bleed.setDecimals(1)
        self.sp_bleed.setSingleStep(0.5)
        self.sp_bleed.setSuffix(" mm")
        self.sp_bleed.setValue(float(saved.get("bleed_mm", 3.0)))
        f.addRow(tr("Anschnitt:"), self.sp_bleed)
        self.rb_mirror = QRadioButton(tr("Spiegeln – nahtlos, für Bilder und Flächen (empfohlen)"))
        self.rb_stretch = QRadioButton(tr("Strecken – der schmale Rand wird nach außen gezogen"))
        self.rb_stretch.setToolTip(
            tr(
                "Wenn ein Spiegelbild auffallen würde (Schrift oder Linien nahe am Rand). Linien im Randstreifen "
                "werden dabei mit gestreckt."
            )
        )
        (self.rb_stretch if saved.get("mode") == "stretch" else self.rb_mirror).setChecked(True)
        f.addRow(tr("Verfahren:"), self.rb_mirror)
        f.addRow("", self.rb_stretch)
        self.cmb_pages = QComboBox()
        self.cmb_pages.addItem(tr("alle Seiten"), "all")
        self.cmb_pages.addItem(tr("aktuelle Seite ({0})").format(current + 1), "current")
        if len(self.selection) > 1:
            self.cmb_pages.addItem(tr("Auswahl ({0})").format(len(self.selection)), "selection")
        f.addRow(tr("Seiten:"), self.cmb_pages)
        v.addLayout(f)
        self.lbl_state = QLabel()
        self.lbl_state.setWordWrap(True)
        v.addWidget(self.lbl_state)
        self.sp_bleed.valueChanged.connect(self._update)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Erzeugen"))
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self._update()

    def _update(self, *_):
        if self.size[0] > 0:
            self.lbl_state.setText(state_text(self.size, self.have, self.sp_bleed.value()))

    def result_pages(self) -> list[int]:
        """Page indices (0-based)."""
        kind = self.cmb_pages.currentData()
        if kind == "current":
            return [self.current]
        if kind == "selection":
            return list(self.selection)
        return list(range(self.page_count))

    def result_params(self) -> tuple:
        """(bleed mm, "mirror" | "stretch")."""
        return float(self.sp_bleed.value()), ("stretch" if self.rb_stretch.isChecked() else "mirror")

    def _accept(self):
        b, mode = self.result_params()
        try:
            st = l10n.load_settings()
            st["bleedgen"] = {"bleed_mm": b, "mode": mode}
            l10n.save_settings(st)
        except OSError:
            pass
        self.accept()
