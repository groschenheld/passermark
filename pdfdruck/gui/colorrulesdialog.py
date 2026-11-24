# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Dialog "Farbregeln": black text and thin lines -> 100 % K, spot colours (rename, merge, into process colours),
cut contours under one name (colorrules.py). The last choices are remembered."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from .. import colorrules, l10n
from ..l10n import tr

KEY = "colorrules"


def _spin(val: float, lo: float, hi: float, step: float) -> QDoubleSpinBox:
    sp = QDoubleSpinBox()
    sp.setRange(lo, hi)
    sp.setDecimals(2 if step < 0.5 else 1)
    sp.setSingleStep(step)
    sp.setSuffix(" pt")
    sp.setValue(val)
    return sp


def pages_text(pages: list) -> str:
    """[1, 2, 3, 7] -> "1–3, 7" (empty: "–")."""
    if not pages:
        return "–"
    out, start, prev = [], pages[0], pages[0]
    for p in pages[1:] + [None]:
        if p is not None and p == prev + 1:
            prev = p
            continue
        out.append(str(start) if start == prev else f"{start}–{prev}")
        if p is not None:
            start = prev = p
    return ", ".join(out)


def load_saved() -> dict:
    """Last choices (black limits, cut contour name and aliases) from the settings."""
    try:
        d = l10n.load_settings().get(KEY) or {}
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def save(d: dict):
    """Remember the choices that make sense for the next document (not the spot colours of this one)."""
    try:
        st = l10n.load_settings()
        st[KEY] = d
        l10n.save_settings(st)
    except OSError:
        pass


class ColorRulesDialog(QDialog):
    """Shows what the document contains and collects the settings for colorrules.apply()."""

    def __init__(self, parent, data: bytes):
        super().__init__(parent)
        self.setWindowTitle(tr("Farbregeln"))
        saved = load_saved()
        d = colorrules.ColorRulesSettings()
        aliases = saved.get("cut_aliases") or d.cut_aliases
        self.survey = colorrules.survey(data, aliases)
        v = QVBoxLayout(self)
        intro = QLabel(
            tr(
                "Ändert Farben im ganzen Dokument – nur die gewählten Regeln. Das Ergebnis ist noch nicht "
                "gespeichert: ohne Speichern bleibt die Datei, wie sie war."
            )
        )
        intro.setWordWrap(True)
        v.addWidget(intro)

        # black
        g = QGroupBox(tr("Schwarz → 100 % K"))
        gv = QVBoxLayout(g)
        expl = QLabel(
            tr(
                "Kleiner Text und dünne Linien in RGB-Schwarz, Grau-Schwarz oder 4c-Schwarz werden reines Schwarz "
                "(nur K) – kein Passer-Problem, keine bunten Ränder. Große Flächen bleiben, wie sie sind."
            )
        )
        expl.setWordWrap(True)
        gv.addWidget(expl)
        r = QHBoxLayout()
        self.chk_text = QCheckBox(tr("Text bis"))
        self.chk_text.setChecked(bool(saved.get("black_text", d.black_text)))
        self.spn_text = _spin(float(saved.get("black_text_max_pt", d.black_text_max_pt)), 1, 72, 0.5)
        r.addWidget(self.chk_text)
        r.addWidget(self.spn_text)
        r.addStretch(1)
        gv.addLayout(r)
        r = QHBoxLayout()
        self.chk_lines = QCheckBox(tr("Linien bis"))
        self.chk_lines.setChecked(bool(saved.get("black_lines", d.black_lines)))
        self.spn_lines = _spin(float(saved.get("black_line_max_pt", d.black_line_max_pt)), 0, 10, 0.25)
        r.addWidget(self.chk_lines)
        r.addWidget(self.spn_lines)
        r.addStretch(1)
        gv.addLayout(r)
        v.addWidget(g)

        # spot colours
        g = QGroupBox(tr("Sonderfarben"))
        gv = QVBoxLayout(g)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels([tr("Sonderfarbe"), tr("Seiten"), tr("Neuer Name"), tr("In CMYK")])
        self.tree.setRootIsDecorated(False)
        self.tree.setToolTip(
            tr(
                "„Neuer Name“: Doppelklick zum Umbenennen. „In CMYK“: die Sonderfarbe wird zu ihrer Ersatzfarbe "
                "(meist CMYK) – Texte, Grafiken, Bilder und Verläufe."
            )
        )
        self.tree.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)  # only "Neuer Name" is edited
        self.tree.itemDoubleClicked.connect(lambda it, _col: self.tree.editItem(it, 2))
        hdr = self.tree.header()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in (1, 2, 3):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        for name, pages in self.survey.spots.items():
            it = QTreeWidgetItem([name, pages_text(pages), "", ""])
            it.setData(0, Qt.ItemDataRole.UserRole, name)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(3, Qt.CheckState.Unchecked)
            self.tree.addTopLevelItem(it)
        gv.addWidget(self.tree)
        self.lbl_none = QLabel(tr("Keine Sonderfarben im Dokument."))
        gv.addWidget(self.lbl_none)
        self.chk_merge = QCheckBox(tr("Gleiche Namen zusammenführen (z. B. „HKS 43 K“ und „HKS43K“)"))
        self.chk_merge.setChecked(True)
        gv.addWidget(self.chk_merge)
        dup = "; ".join(" = ".join(gr) for gr in self.survey.duplicates)
        self.lbl_dup = QLabel(tr("Gefunden: {0}").format(dup) if dup else "")
        self.lbl_dup.setWordWrap(True)
        gv.addWidget(self.lbl_dup)
        has = bool(self.survey.spots)
        self.tree.setVisible(has)
        self.lbl_none.setVisible(not has)
        self.chk_merge.setVisible(bool(self.survey.duplicates))
        self.lbl_dup.setVisible(bool(dup))
        v.addWidget(g)

        # cut contours
        g = QGroupBox(tr("Schneidkonturen"))
        gv = QVBoxLayout(g)
        r = QHBoxLayout()
        self.chk_cut = QCheckBox(tr("Vereinheitlichen als"))
        self.chk_cut.setChecked(bool(self.survey.cut) and bool(saved.get("cut_on", True)))
        self.ed_cut = QLineEdit(saved.get("cut_name") or "CutContour")
        self.ed_cut.setToolTip(tr("Der Name, den der Plotter bzw. RIP erwartet – z. B. CutContour (Roland)"))
        r.addWidget(self.chk_cut)
        r.addWidget(self.ed_cut, 1)
        gv.addLayout(r)
        found = ", ".join(self.survey.cut)
        self.lbl_cut = QLabel(tr("Im Dokument: {0}").format(found) if found else tr("Keine Schneidkontur erkannt."))
        self.lbl_cut.setWordWrap(True)
        gv.addWidget(self.lbl_cut)
        self.ed_alias = QLineEdit(", ".join(aliases))
        self.ed_alias.setToolTip(
            tr("Diese Sonderfarben-Namen gelten als Schneidkontur (Groß-/Kleinschreibung und Leerzeichen egal)")
        )
        gv.addWidget(QLabel(tr("Als Kontur erkannt werden:")))
        gv.addWidget(self.ed_alias)
        self.chk_cut_op = QCheckBox(tr("Kontur auf Überdrucken stellen (sonst spart sie den Druck aus)"))
        self.chk_cut_op.setChecked(bool(saved.get("cut_overprint", True)))
        gv.addWidget(self.chk_cut_op)
        v.addWidget(g)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Anwenden"))
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def aliases(self) -> list:
        """Cut contour names from the field (comma separated)."""
        return [a.strip() for a in self.ed_alias.text().split(",") if a.strip()]

    def result_settings(self) -> colorrules.ColorRulesSettings:
        """The chosen rules."""
        rename, to_process = {}, []
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            old = it.data(0, Qt.ItemDataRole.UserRole)
            new = it.text(2).strip()
            if new and new != old:
                rename[old] = new
            if it.checkState(3) == Qt.CheckState.Checked:
                to_process.append(old)
        cut = self.ed_cut.text().strip() if self.chk_cut.isChecked() else ""
        return colorrules.ColorRulesSettings(
            black_text=self.chk_text.isChecked(),
            black_text_max_pt=self.spn_text.value(),
            black_lines=self.chk_lines.isChecked(),
            black_line_max_pt=self.spn_lines.value(),
            rename=rename,
            merge_duplicates=self.chk_merge.isChecked(),
            to_process=to_process,
            cut_name=cut,
            cut_aliases=self.aliases() or list(colorrules.CUT_ALIASES),
            cut_overprint=self.chk_cut_op.isChecked(),
        )

    def _accept(self):
        s = self.result_settings()
        save(
            {
                "black_text": s.black_text,
                "black_text_max_pt": s.black_text_max_pt,
                "black_lines": s.black_lines,
                "black_line_max_pt": s.black_line_max_pt,
                "cut_on": self.chk_cut.isChecked(),
                "cut_name": self.ed_cut.text().strip() or "CutContour",
                "cut_aliases": s.cut_aliases,
                "cut_overprint": s.cut_overprint,
            }
        )
        self.accept()
