# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Dialog "Compare before/after": the saved file next to the current state, differences marked in red."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from ..l10n import tr


def render(data: bytes, page: int, px: int):
    """Page ``page`` of ``data`` as a PIL image, the longer side ``px`` pixels (None if the page is missing)."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(data)
    try:
        if page >= len(doc):
            return None
        pg = doc[page]
        w, h = pg.get_size()
        img = pg.render(scale=px / max(w, h, 1)).to_pil().convert("RGB")
        pg.close()
        return img
    finally:
        doc.close()


def marked(before, after, tol: int = 24):
    """``after`` with the pixels that differ from ``before`` tinted red -> (image, share of changed pixels)."""
    from PIL import Image, ImageChops

    if before is None or after is None:
        return after, 0.0
    if before.size != after.size:
        before = before.resize(after.size)
    diff = ImageChops.difference(before, after).convert("L").point(lambda v: 255 if v > tol else 0)
    share = (diff.histogram()[255] / (diff.width * diff.height)) if diff.width and diff.height else 0.0
    red = Image.new("RGB", after.size, (230, 40, 40))
    return Image.composite(Image.blend(after, red, 0.6), after, diff), share


def _pixmap(img) -> QPixmap:
    if img is None:
        return QPixmap()
    data = img.tobytes("raw", "RGB")
    q = QImage(data, img.width, img.height, img.width * 3, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(q.copy())


class CompareDialog(QDialog):
    """``before``/``after``: PDF bytes (saved file / current state)."""

    PX = 700

    def __init__(self, parent, before: bytes, after: bytes, page: int, pages: int):
        super().__init__(parent)
        self.setWindowTitle(tr("Vorher/Nachher vergleichen"))
        self.before, self.after = before, after
        v = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel(tr("Seite:")))
        self.sp = QSpinBox()
        self.sp.setRange(1, max(1, pages))
        self.sp.setValue(page + 1)
        self.sp.valueChanged.connect(self._show)
        top.addWidget(self.sp)
        self.chk = QCheckBox(tr("Unterschiede rot markieren"))
        self.chk.setChecked(True)
        self.chk.toggled.connect(self._show)
        top.addWidget(self.chk)
        top.addStretch(1)
        v.addLayout(top)
        row = QHBoxLayout()
        self.lbl_a, self.lbl_b = QLabel(), QLabel()
        for title, lb in ((tr("Vorher (gespeicherte Datei)"), self.lbl_a), (tr("Nachher (jetzt)"), self.lbl_b)):
            col = QVBoxLayout()
            col.addWidget(QLabel(f"<b>{title}</b>"))
            lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lb.setMinimumSize(200, 200)
            col.addWidget(lb, 1)
            row.addLayout(col, 1)
        v.addLayout(row, 1)
        self.lbl_info = QLabel()
        self.lbl_info.setWordWrap(True)
        v.addWidget(self.lbl_info)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self._show()

    def _show(self, *_):
        page = self.sp.value() - 1
        a = render(self.before, page, self.PX)
        b = render(self.after, page, self.PX)
        shown, share = marked(a, b) if self.chk.isChecked() is True else (b, None)
        self.lbl_a.setPixmap(_pixmap(a))
        self.lbl_b.setPixmap(_pixmap(shown))
        if a is None:
            self.lbl_info.setText(tr("Diese Seite gibt es in der gespeicherten Datei nicht."))
        elif b is None:
            self.lbl_info.setText(tr("Diese Seite gibt es jetzt nicht mehr."))
        elif share is None:
            self.lbl_info.setText("")
        elif share == 0:
            self.lbl_info.setText(tr("Keine sichtbaren Unterschiede auf dieser Seite."))
        else:
            self.lbl_info.setText(tr("{0:.1f} % der Seite haben sich sichtbar verändert.").format(share * 100))
