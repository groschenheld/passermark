# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Dialog "Set trim format": final format and bleed – trim and bleed box follow, excess sheet is cut off."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

from .. import pageboxes
from ..l10n import tr
from ..papersizes import UI_FORMATS


def _spin(lo: float, hi: float, val: float) -> QDoubleSpinBox:
    sp = QDoubleSpinBox()
    sp.setRange(lo, hi)
    sp.setDecimals(1)
    sp.setSingleStep(1.0)
    sp.setSuffix(" mm")
    sp.setValue(val)
    return sp


class PageBoxDialog(QDialog):
    """Start values from the current page (existing trim box, otherwise a recognised format with bleed)."""

    def __init__(self, parent, data: bytes, current: int, page_count: int, selection: list[int] | None = None):
        super().__init__(parent)
        self.setWindowTitle(tr("Endformat festlegen"))
        self.page_count, self.current = page_count, current
        self.selection = sorted(selection or [])
        info = pageboxes.read(data, current)
        self.sheet = info["sheet"]
        v = QVBoxLayout(self)
        intro = QLabel(
            tr(
                "Legt fest, wo geschnitten wird (Endformat) und wie viel Anschnitt darum liegt. Das ändert kein "
                "Pixel: Passermark, Ausschießen, Schnittmarken, RIP und PDF/X lesen daraus den Schnitt. Fehlt "
                "der Anschnitt in der Datei, kann ihn kein Rahmen ersetzen."
            )
        )
        intro.setWordWrap(True)
        v.addWidget(intro)

        sw, sh = self.sheet
        guess = pageboxes.guess_format(sw, sh)
        if info["trim"]:
            tw, th = info["trim"]
            bleed = info["bleed"] if info["bleed"] is not None else 0.0
            found = tr("Seite {0}: Blatt {1:.1f} × {2:.1f} mm, Endformat schon gesetzt.").format(current + 1, sw, sh)
        elif guess:
            _name, tw, th, bleed = guess
            found = tr("Seite {0}: Blatt {1:.1f} × {2:.1f} mm – sieht aus wie {3} mit {4:g} mm Anschnitt.").format(
                current + 1, sw, sh, guess[0], guess[3]
            )
        else:
            tw, th, bleed = sw, sh, 0.0
            found = tr("Seite {0}: Blatt {1:.1f} × {2:.1f} mm.").format(current + 1, sw, sh)
        lb = QLabel(found)
        lb.setWordWrap(True)
        v.addWidget(lb)

        f = QFormLayout()
        self.cmb_fmt = QComboBox()
        self.cmb_fmt.addItem(tr("eigenes Maß"), None)
        for name, (w, h) in UI_FORMATS.items():
            self.cmb_fmt.addItem(f"{name} ({w:g} × {h:g} mm)", (w, h))
        self.cmb_fmt.currentIndexChanged.connect(self._format_chosen)
        self.cmb_fmt.setToolTip(tr("Bekanntes Format wählen – Hoch- oder Querformat richtet sich nach der Seite."))
        f.addRow(tr("Format:"), self.cmb_fmt)
        size = QHBoxLayout()
        self.sp_w, self.sp_h = _spin(1, 10000, round(tw, 1)), _spin(1, 10000, round(th, 1))
        size.addWidget(self.sp_w)
        size.addWidget(QLabel("×"))
        size.addWidget(self.sp_h)
        lab_trim = QLabel(tr("Endformat:"))
        tip_trim = tr(
            "Endformat (TrimBox): das fertige Format nach dem Schnitt. Es wird mittig auf die Seite gelegt. "
            "Schnittmarken, Ausschießen und die Prüfung „zu nah am Rand“ richten sich danach."
        )
        for wdg in (lab_trim, self.sp_w, self.sp_h):
            wdg.setToolTip(tip_trim)
        f.addRow(lab_trim, size)
        self.sp_bleed = _spin(0, 50, round(bleed, 1))
        lab_bleed = QLabel(tr("Anschnitt:"))
        tip_bleed = tr(
            "Anschnitt (BleedBox): wie weit die Farbe über den Schnitt hinausläuft, damit nach dem Schneiden kein "
            "weißer Blitzer bleibt – üblich 3 mm. Reicht der Inhalt der Seite nicht so weit, wird gesetzt, was da "
            "ist, und Passermark sagt es."
        )
        lab_bleed.setToolTip(tip_bleed)
        self.sp_bleed.setToolTip(tip_bleed)
        f.addRow(lab_bleed, self.sp_bleed)
        self.chk_cut = QCheckBox(tr("Überschüssigen Rand abschneiden"))
        self.chk_cut.setChecked(True)
        self.chk_cut.setToolTip(
            tr(
                "Ist das Blatt größer als Endformat + Anschnitt (z. B. 310 × 220 mm für A4 quer), wird es auf "
                "Endformat + Anschnitt verkleinert (MediaBox und CropBox, also Blatt und Anzeigebereich). Der "
                "Inhalt bleibt, nur der Rand außerhalb fällt weg."
            )
        )
        f.addRow("", self.chk_cut)
        self.cmb_pages = QComboBox()
        self.cmb_pages.addItem(tr("alle Seiten"), "all")
        self.cmb_pages.addItem(tr("aktuelle Seite ({0})").format(current + 1), "current")
        if len(self.selection) > 1:
            self.cmb_pages.addItem(tr("Auswahl ({0})").format(len(self.selection)), "selection")
        f.addRow(tr("Seiten:"), self.cmb_pages)
        v.addLayout(f)

        self.lbl_result = QLabel("")
        self.lbl_result.setWordWrap(True)
        v.addWidget(self.lbl_result)
        for sp in (self.sp_w, self.sp_h, self.sp_bleed):
            sp.valueChanged.connect(self._update)
        self.chk_cut.toggled.connect(self._update)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self._update()

    def _format_chosen(self, _i=None):
        wh = self.cmb_fmt.currentData()
        if not wh:
            return
        w, h = sorted(wh)
        if self.sheet[0] > self.sheet[1]:  # landscape page: landscape format
            w, h = h, w
        self.sp_w.setValue(w)
        self.sp_h.setValue(h)

    def _update(self, *_):
        w, h, b = self.sp_w.value(), self.sp_h.value(), self.sp_bleed.value()
        sw, sh = self.sheet
        text = result_text(w, h, b, sw, sh, self.chk_cut.isChecked() is True)
        self.lbl_result.setText(text)

    def result_pages(self) -> list[int]:
        """Page indices (0-based) the trim format is set on."""
        kind = self.cmb_pages.currentData()
        if kind == "current":
            return [self.current]
        if kind == "selection":
            return list(self.selection)
        return list(range(self.page_count))

    def result_params(self) -> tuple[float, float, float, bool]:
        """(trim width mm, trim height mm, bleed mm, cut excess sheet)."""
        return (
            float(self.sp_w.value()),
            float(self.sp_h.value()),
            float(self.sp_bleed.value()),
            self.chk_cut.isChecked() is True,
        )


def result_text(w: float, h: float, bleed: float, sw: float, sh: float, cut: bool) -> str:
    """What happens to a sheet ``sw`` × ``sh`` mm – shown live in the dialog."""
    if w > sw + 0.05 or h > sh + 0.05:
        return tr("Das Blatt ({0:.1f} × {1:.1f} mm) ist kleiner als das Endformat – so nicht möglich.").format(sw, sh)
    have = min((sw - w) / 2, (sh - h) / 2)
    if have + 0.05 < bleed:
        return tr(
            "Achtung: Die Seite hat rundum nur {0:.1f} mm über das Endformat hinaus – mehr Anschnitt gibt es nicht."
        ).format(max(0.0, have))
    if cut and have > bleed + 0.05:
        return tr(
            "Ergebnis: Endformat {0:g} × {1:g} mm, Anschnitt {2:g} mm, das Blatt wird von {3:.1f} × {4:.1f} auf {5:g} × {6:g} mm verkleinert."
        ).format(w, h, bleed, sw, sh, w + 2 * bleed, h + 2 * bleed)
    return tr("Ergebnis: Endformat {0:g} × {1:g} mm, Anschnitt {2:g} mm.").format(w, h, bleed)
