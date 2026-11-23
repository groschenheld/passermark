# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Farbe → Ausgabevorschau: side panel for the printing plates of the page and the total ink coverage.

Aus | Auszüge | Farbauftrag. Auszüge: every ink of the page (CMYK + spot colours) with a check box and a swatch,
the values under the mouse next to it; one ink alone optionally in black. Farbauftrag: limit, everything above in
red over the page. Überdrucken simulieren as in the soft proof. Based on the printing condition of the soft proof.
(Idea for the layout: FormDesign/FormPDF, nodemode-dev, Apache-2.0 – only the idea, no code.)

Signals to the main window (it does the work):
  changed(options | None)   {"mode": "sep"|"tac", "hide": [...], "gray": bool, "tac": int, "overprint": bool}
  setup_requested()         open the soft proof set-up (printing condition)
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import l10n
from ..l10n import tr

MODES = ("off", "sep", "tac")


def _num1(v: float) -> str:
    """One decimal place, with a decimal comma except in English."""
    t = f"{v:.1f}"
    return t if l10n.current() == "en" else t.replace(".", ",")


def tac_text(info: dict | None) -> str:
    """Result line for the ink coverage: highest value and the share of the page above the limit."""
    if not info:
        return ""
    mx, over, lim = info.get("max_tac", 0.0), info.get("over", 0.0), info.get("limit", 300)
    if over <= 0.0:
        return tr("Höchster Farbauftrag {0:.0f} % – nichts über {1:.0f} %.").format(mx, lim)
    return tr("Höchster Farbauftrag {0:.0f} % – {1} % der Seite liegt über {2:.0f} % (rot umrandet).").format(
        mx, _num1(over), lim
    )


def count_text(shown: int, total: int) -> str:
    """ "3 von 5 Farben sichtbar" / "Alle 5 Farben sichtbar"."""
    if total and shown == total:
        return tr("Alle {0} Farben sichtbar.").format(total)
    return tr("{0} von {1} Farben sichtbar.").format(shown, total)


def values_text(vals: dict | None) -> str:
    """Total under the mouse for the label below the list."""
    if not vals:
        return tr("Maus über die Seite bewegen: Werte je Farbe.")
    return tr("Unter der Maus: gesamt {0:.0f} %").format(vals.get("", 0.0))


class _InfoWorker(QThread):
    """separations.page_info in the background (Ghostscript, no pdfium)."""

    done = Signal(object, str)

    def __init__(self, path: str, index: int, spec: dict):
        super().__init__()
        self.path, self.index, self.spec = path, index, spec

    def run(self):
        from .. import separations

        try:
            self.done.emit(separations.page_info(self.path, self.index, self.spec), "")
        except Exception as e:  # noqa: BLE001 – shown in the panel
            self.done.emit(None, str(e))


class OutputPanel(QWidget):
    """Side panel "Ausgabevorschau"."""

    changed = Signal(object)
    setup_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode = "off"
        self.hide: set = set()
        self.info = None
        self.page = -1
        self._gen = 0
        self._threads = set()
        self._quiet = False
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)

        intro = QLabel(
            tr(
                "Zeigt, was auf den einzelnen Druckplatten landet und wo zu viel Farbe aufgetragen wird – "
                "für die Druckbedingung des Softproofs."
            )
        )
        intro.setWordWrap(True)
        v.addWidget(intro)
        row = QHBoxLayout()
        self.lbl_cond = QLabel()
        self.lbl_cond.setWordWrap(True)
        row.addWidget(self.lbl_cond, 1)
        self.btn_setup = QPushButton(tr("Einrichten …"))
        self.btn_setup.setToolTip(tr("Druckbedingung (CMYK-Profil) im Softproof wählen"))
        self.btn_setup.clicked.connect(self.setup_requested.emit)
        row.addWidget(self.btn_setup)
        v.addLayout(row)

        segw = QWidget()  # in its own widget: the three stay in one row (no button flow of the panel)
        seg = QHBoxLayout(segw)
        seg.setContentsMargins(0, 0, 0, 0)
        seg.setSpacing(0)
        self.grp = QButtonGroup(self)
        self.grp.setExclusive(True)
        self.btn_mode = {}
        for key, text, tip in (
            ("off", tr("Aus"), tr("Normale Ansicht")),
            ("sep", tr("Auszüge"), tr("Einzelne Druckfarben ein- und ausblenden")),
            ("tac", tr("Farbauftrag"), tr("Stellen über dem Grenzwert rot umranden")),
        ):
            b = QPushButton(text)
            b.setCheckable(True)
            b.setToolTip(tip)
            b.setMinimumWidth(40)
            self.grp.addButton(b)
            seg.addWidget(b, 1)
            self.btn_mode[key] = b
            b.clicked.connect(lambda _c=False, k=key: self.set_mode(k))
        self.btn_mode["off"].setChecked(True)
        v.addWidget(segw)

        self.lbl_hint = QLabel()
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.hide()
        v.addWidget(self.lbl_hint)

        self.box_sep = QGroupBox(tr("Druckfarben dieser Seite"))
        sv = QVBoxLayout(self.box_sep)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels([tr("Farbe"), tr("Maus"), tr("Fläche")])
        self.tree.setRootIsDecorated(False)
        self.tree.setToolTip(
            tr(
                "Häkchen weg = Seite ohne diese Farbe. „Maus“: Wert unter dem Mauszeiger, "
                "„Fläche“: Anteil der Seite, auf den diese Farbe druckt."
            )
        )
        hdr = self.tree.header()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.itemChanged.connect(self._item_changed)
        sv.addWidget(self.tree)
        self.lbl_count = QLabel()
        sv.addWidget(self.lbl_count)
        r2 = QHBoxLayout()
        self.btn_all = QPushButton(tr("Alle zeigen"))
        self.btn_all.clicked.connect(self.show_all)
        r2.addWidget(self.btn_all)
        self.chk_gray = QCheckBox(tr("Einzelne Farbe schwarz"))
        self.chk_gray.setToolTip(
            tr("Ist nur eine Farbe sichtbar, wird sie schwarz gezeigt – wie ein Film, kleine Stellen sieht man besser")
        )
        self.chk_gray.toggled.connect(lambda _on: self._emit())
        r2.addWidget(self.chk_gray)
        r2.addStretch(1)
        sv.addLayout(r2)
        v.addWidget(self.box_sep)

        self.box_tac = QGroupBox(tr("Gesamtfarbauftrag"))
        tv = QVBoxLayout(self.box_tac)
        r3 = QHBoxLayout()
        self.spn_tac = QSpinBox()
        self.spn_tac.setRange(100, 400)
        self.spn_tac.setSingleStep(5)
        self.spn_tac.setPrefix(tr("Grenzwert") + " ")  # in the field: a wrapping label next to it would vanish
        self.spn_tac.setSuffix(" %")
        self.spn_tac.setValue(300)
        self.spn_tac.setToolTip(
            tr("Summe aller Farben (C+M+Y+K und Sonderfarben). Offset gestrichen meist 300–330 %, Zeitung 240 %")
        )
        self.spn_tac.valueChanged.connect(lambda _v: self._tac_changed())
        r3.addWidget(self.spn_tac)
        r3.addStretch(1)
        tv.addLayout(r3)
        self.lbl_tac = QLabel()
        self.lbl_tac.setWordWrap(True)
        tv.addWidget(self.lbl_tac)
        v.addWidget(self.box_tac)

        self.lbl_values = QLabel(values_text(None))
        self.lbl_values.setWordWrap(True)
        v.addWidget(self.lbl_values)
        self.chk_overprint = QCheckBox(tr("Überdrucken simulieren"))
        self.chk_overprint.setChecked(True)
        self.chk_overprint.setToolTip(
            tr("Überdruckende Objekte so zeigen, wie sie gedruckt werden (weiß überdruckt verschwindet)")
        )
        self.chk_overprint.toggled.connect(lambda _on: self._emit(refresh=True))
        v.addWidget(self.chk_overprint)
        self.lbl_busy = QLabel()
        v.addWidget(self.lbl_busy)
        v.addStretch(1)
        self._sync()

    # ------------------------------------------------------------------ #
    def options(self) -> dict | None:
        """Current settings for the soft proof spec, None when switched off."""
        if self.mode == "off":
            return None
        return {
            "mode": self.mode,
            "hide": sorted(self.hide),
            "gray": self.chk_gray.isChecked(),
            "tac": self.spn_tac.value(),
            "overprint": self.chk_overprint.isChecked(),
        }

    def set_mode(self, mode: str, emit: bool = True):
        """Aus | Auszüge | Farbauftrag."""
        if mode not in MODES:
            return
        self.mode = mode
        b = self.btn_mode[mode]
        if not b.isChecked():
            b.setChecked(True)
        self._sync()
        if emit:
            self._emit(refresh=True)

    def reset(self):
        """Switched off from outside (soft proof off): back to "Aus" without signal."""
        self.set_mode("off", emit=False)
        self.show_values(None)

    def set_defaults(self, spec: dict | None):
        """Limit and overprint from the soft proof spec (when the preview starts)."""
        if not spec:
            return
        self._quiet = True
        try:
            self.spn_tac.setValue(int(spec.get("tac", 300) or 300))
            self.chk_overprint.setChecked(bool(spec.get("overprint", True)))
        finally:
            self._quiet = False

    def set_condition(self, name: str, problem: str = ""):
        """Name of the printing condition; problem = why the preview is not possible (then the modes are off)."""
        self.lbl_cond.setText(tr("Druckbedingung: {0}").format(name or "–"))
        self.lbl_hint.setText(problem)
        self.lbl_hint.setVisible(bool(problem))
        for k in ("sep", "tac"):
            self.btn_mode[k].setEnabled(not problem)
        if problem and self.mode != "off":
            self.reset()

    def show_all(self):
        """All inks visible again."""
        self.hide.clear()
        self._fill()
        self._emit()

    def show_values(self, vals: dict | None):
        """Values under the mouse (separations.values_at) in the list and the total below."""
        self.lbl_values.setText(values_text(vals))
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            name = it.data(0, Qt.ItemDataRole.UserRole)
            it.setText(1, f"{vals.get(name, 0.0):.0f} %" if vals else "")

    # ------------------------------------------------------------------ #
    def load(self, path: str, index: int, spec: dict):
        """Read the inks of page ``index`` in the background."""
        self._gen += 1
        gen = self._gen
        self.page = index
        self.lbl_busy.setText("… " + tr("Lese die Druckfarben"))
        w = _InfoWorker(path, index, dict(spec))
        w.done.connect(lambda info, err, gen=gen: self._loaded(gen, info, err))
        self._threads.add(w)
        w.finished.connect(lambda w=w: self._threads.discard(w))
        w.start()

    def stop(self, wait_ms: int = 15000):
        """Wait for running background jobs (before the window closes)."""
        self._gen += 1
        for w in list(self._threads):
            if w.isRunning():
                w.wait(wait_ms)

    def _loaded(self, gen, info, err):
        if gen != self._gen:
            return
        self.lbl_busy.setText(tr("Fehler: {0}").format(err.splitlines()[0]) if err else "")
        self.lbl_busy.setToolTip(err)
        self.info = info
        self._fill()
        self.lbl_tac.setText(tac_text(info))

    def _fill(self):
        self._quiet = True
        try:
            self.tree.clear()
            inks = (self.info or {}).get("inks") or []
            for ink in inks:
                it = QTreeWidgetItem([ink["label"] + (" " + tr("(Sonderfarbe)") if ink["spot"] else ""), "", ""])
                it.setData(0, Qt.ItemDataRole.UserRole, ink["name"])
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                it.setCheckState(0, Qt.CheckState.Unchecked if ink["name"] in self.hide else Qt.CheckState.Checked)
                pm = QPixmap(14, 14)
                pm.fill(QColor(*ink["rgb"]))
                it.setIcon(0, QIcon(pm))
                it.setText(2, f"{ink['coverage']:.0f} %")
                self.tree.addTopLevelItem(it)
            names = [i["name"] for i in inks]
            shown = len([n for n in names if n not in self.hide])
            self.lbl_count.setText(count_text(shown, len(names)) if names else "")
        finally:
            self._quiet = False

    def _item_changed(self, it, col):
        if self._quiet or col != 0:
            return
        name = it.data(0, Qt.ItemDataRole.UserRole)
        if it.checkState(0) == Qt.CheckState.Checked:
            self.hide.discard(name)
        else:
            self.hide.add(name)
        names = [i["name"] for i in (self.info or {}).get("inks") or []]
        self.lbl_count.setText(count_text(len([n for n in names if n not in self.hide]), len(names)))
        self._emit()

    def _tac_changed(self):
        if self.info:
            self.info = dict(self.info)
            self.info["limit"] = self.spn_tac.value()
            # the share above the limit needs the plates: estimate it again from the overview
            from .. import separations

            self.info["over"] = separations.share_over(self.info, self.spn_tac.value())
            self.lbl_tac.setText(tac_text(self.info))
        self._emit()

    def _sync(self):
        self.box_sep.setVisible(self.mode == "sep")
        self.box_tac.setVisible(self.mode == "tac")
        self.lbl_values.setVisible(self.mode != "off")
        self.chk_overprint.setVisible(self.mode != "off")

    def _emit(self, refresh: bool = False):
        if self._quiet:
            return
        opts = self.options()
        if opts is not None:
            opts["refresh"] = refresh
        self.changed.emit(opts)
