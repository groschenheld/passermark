# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Dialog "Zusammenführen": put files (PDF, images, Office) in order and combine them into one PDF."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from ..l10n import tr
from . import lastdir
from .fileopen import OPEN_FILTER


class _MergeList(QListWidget):
    """List in the merge dialog: reorder internally and drag files/folders in from the file manager."""

    dropped = Signal(list)
    reordered = Signal()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e):
        if e.mimeData().hasUrls():
            self.dropped.emit([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])
            e.acceptProposedAction()
            return
        super().dropEvent(e)
        self.reordered.emit()


class MergeDialog(QDialog):
    """Merge several PDFs/images in the desired order into one document. For large numbers (e.g. 110 plans):
    add a folder, drag files in, sort by name; files arriving later (Explorer) end up here.
    """

    def __init__(self, parent, start: list[str] | None = None):
        super().__init__(parent)
        self.setWindowTitle(tr("Dokumente zusammenführen"))
        self.resize(620, 520)
        self._manual = False  # reordered by hand: new files are only appended
        v = QVBoxLayout(self)
        v.addWidget(QLabel(tr("Reihenfolge = Reihenfolge im neuen Dokument (Bilder in tatsächlicher Größe):")))
        h = QHBoxLayout()
        self.lst = _MergeList()
        self.lst.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.lst.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.lst.setAcceptDrops(True)
        self.lst.dropped.connect(self.add_paths)
        self.lst.reordered.connect(self._set_manual)
        h.addWidget(self.lst, 1)
        b = QVBoxLayout()
        for text, fn in [
            (tr("Hinzufügen…"), self._add),
            (tr("Ordner hinzufügen …"), self._add_folder),
            (tr("Entfernen"), self._remove),
            ("▲ " + tr("Nach oben"), lambda: self._move(-1)),
            ("▼ " + tr("Nach unten"), lambda: self._move(1)),
            (tr("Nach Name sortieren"), self._sort),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(fn)
            b.addWidget(btn)
        b.addStretch()
        h.addLayout(b)
        v.addLayout(h, 1)
        self.lbl_count = QLabel()
        v.addWidget(self.lbl_count)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Zusammenführen"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        for p in start or []:
            self._append(p)
        self._count()

    def _count(self):
        n = self.lst.count()
        self.lbl_count.setText(tr("{0} Datei(en)").format(n))

    def _set_manual(self):
        self._manual = True

    def _append(self, p):
        it = QListWidgetItem(os.path.basename(p))
        it.setToolTip(p)
        it.setData(Qt.ItemDataRole.UserRole, p)
        self.lst.addItem(it)

    def add_paths(self, paths):
        """Add files (or folders) – no duplicates; sorted by name as long as the user has not reordered."""
        from .. import convert

        have = set(self.paths())
        new = []
        for p in paths:
            p = os.path.abspath(p)
            cand = [os.path.join(p, f) for f in sorted(os.listdir(p))] if os.path.isdir(p) else [p]
            for c in cand:
                if os.path.isfile(c) and convert.is_supported(c) and c not in have:
                    have.add(c)
                    new.append(c)
        if not new:
            return
        self.lst.setUpdatesEnabled(False)
        for p in new:
            self._append(p)
        if not self._manual:
            self._sort(manual=False)
        self.lst.setUpdatesEnabled(True)
        self._count()
        self.raise_()
        self.activateWindow()

    def _add(self):
        paths, _ = lastdir.getOpenFileNames(self, tr("Dateien hinzufügen"), "", OPEN_FILTER)
        self.add_paths(paths)

    def _add_folder(self):
        d = lastdir.getExistingDirectory(self, tr("Ordner hinzufügen …"))
        if d:
            self.add_paths([d])

    def _sort(self, manual=True):
        """By file name (natural: Plan 2 before Plan 10)."""
        import re

        def key(p):
            return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", os.path.basename(p))]

        paths = sorted(self.paths(), key=key)
        self.lst.clear()
        for p in paths:
            self._append(p)
        if manual:
            self._manual = False

    def _remove(self):
        for it in self.lst.selectedItems():
            self.lst.takeItem(self.lst.row(it))
        self._count()

    def _move(self, d):
        rows = sorted(self.lst.row(i) for i in self.lst.selectedItems())
        if not rows or (d < 0 and rows[0] == 0) or (d > 0 and rows[-1] == self.lst.count() - 1):
            return
        self._manual = True
        for r in rows if d < 0 else reversed(rows):
            it = self.lst.takeItem(r)
            self.lst.insertItem(r + d, it)
            it.setSelected(True)

    def paths(self):
        """The files in the order shown in the list."""
        return [self.lst.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.lst.count())]
