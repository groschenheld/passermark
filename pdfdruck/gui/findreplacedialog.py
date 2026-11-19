# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Dialog "Search and replace text": find rows with a text and replace it (original font)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
)

from .. import editing
from ..l10n import tr


class FindReplaceDialog(QDialog):
    """Works on ``doc`` (pypdfium2) – ``Ersetzen`` changes it directly; ``changed`` tells the caller afterwards."""

    def __init__(self, parent, doc, current: int):
        super().__init__(parent)
        self.setWindowTitle(tr("Text suchen und ersetzen"))
        self.doc, self.current = doc, current
        self.changed = 0
        self.notes: list[str] = []
        v = QVBoxLayout(self)
        f = QFormLayout()
        self.ed_find = QLineEdit()
        self.ed_repl = QLineEdit()
        f.addRow(tr("Suchen:"), self.ed_find)
        f.addRow(tr("Ersetzen durch:"), self.ed_repl)
        self.chk_case = QCheckBox(tr("Groß-/Kleinschreibung beachten"))
        f.addRow("", self.chk_case)
        self.cmb_pages = QComboBox()
        self.cmb_pages.addItem(tr("alle Seiten"), "all")
        self.cmb_pages.addItem(tr("aktuelle Seite ({0})").format(current + 1), "current")
        f.addRow(tr("Seiten:"), self.cmb_pages)
        v.addLayout(f)
        self.btn_find = QPushButton(tr("Suchen"))
        self.btn_find.clicked.connect(self._find)
        v.addWidget(self.btn_find)
        self.lst = QListWidget()
        v.addWidget(self.lst, 1)
        self.lbl = QLabel(
            tr(
                "Ersetzt wird in der Originalschrift. Ist sie nur als Teilmenge eingebettet, können neue Zeichen "
                "fehlen – Passermark weist darauf hin. Text, den pdfium nicht lesen kann, wird nicht gefunden."
            )
        )
        self.lbl.setWordWrap(True)
        v.addWidget(self.lbl)
        bb = QDialogButtonBox()
        self.btn_repl = bb.addButton(tr("Alle ersetzen"), QDialogButtonBox.ButtonRole.AcceptRole)
        bb.addButton(tr("Schließen"), QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(self._replace)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.ed_find.returnPressed.connect(self._find)

    def pages(self) -> list[int]:
        """Pages to search (0-based)."""
        return [self.current] if self.cmb_pages.currentData() == "current" else list(range(len(self.doc)))

    def _find(self):
        self.lst.clear()
        hits = editing.find_text(self.doc, self.pages(), self.ed_find.text(), self.chk_case.isChecked() is True)
        for p, text in hits:
            self.lst.addItem(tr("Seite {0}: {1}").format(p + 1, text))
        if not hits:
            self.lst.addItem(tr("Nichts gefunden."))
        return hits

    def _replace(self):
        if not self.ed_find.text():
            return
        n, notes = editing.replace_text(
            self.doc, self.pages(), self.ed_find.text(), self.ed_repl.text(), self.chk_case.isChecked() is True
        )
        self.changed += n
        self.notes += [h for h in notes if h not in self.notes]
        self.lst.clear()
        self.lst.addItem(tr("{0} Stelle(n) ersetzt.").format(n))
        for h in notes:
            self.lst.addItem(h)
