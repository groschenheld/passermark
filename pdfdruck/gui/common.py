# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, Version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Shared GUI helpers and the session state (kept in memory only)."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QLabel,
    QPlainTextEdit,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..l10n import tr
from ..layout import LayoutSettings  # noqa: F401  (used to be needed here)
from ..session import Session  # noqa: F401  (the session lives without Qt in pdfdruck.session)
from . import theme


class CollapsibleSection(QWidget):
    """Collapsible group: the title row always stays visible, the content only when needed.
    Uniform section style (bold, accent colour) – print dialog and VDP dialog.
    """

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
        self.btn.setStyleSheet(f"QToolButton {{ font-weight: bold; border: none; color: {theme.ACCENT_TEXT}; }}")
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


# Render limit: huge/faulty pages no longer block the view.
# Render at most 8192 px per edge or 40 megapixels, then scale up smoothly.
MAX_RENDER_EDGE = 8192
MAX_RENDER_PIXELS = 40_000_000


def render_pixmap(page, scale: float, rotation: int = 0, dpr: float = 1.0) -> QPixmap:
    """Render a pdfium page as a QPixmap (BGRX -> QImage.Format.Format_RGB32).

    Size limit: pages that would become gigapixel-sized when zoomed (or have broken
    measures) are rendered at most 8192 px per edge or 40 megapixels and
    then scaled up smoothly to the target size – zooming stays fluid.
    """
    rot = rotation % 360
    w, h = page.get_size()
    if rot % 180:
        w, h = h, w
    sc = scale * dpr
    lim = min(
        1.0,
        MAX_RENDER_EDGE / max(1.0, w * sc),
        MAX_RENDER_EDGE / max(1.0, h * sc),
        (MAX_RENDER_PIXELS / max(1.0, w * sc * h * sc)) ** 0.5,
    )
    bmp = page.render(scale=sc * lim, rotation=rot, prefer_bgrx=True, may_draw_forms=True, draw_annots=True)
    fmt = QImage.Format.Format_RGB32 if bmp.n_channels == 4 else QImage.Format.Format_BGR888
    img = QImage(bytes(bmp.buffer), bmp.width, bmp.height, bmp.stride, fmt).copy()
    bmp.close()
    if lim < 1.0:  # render limit reached: scale up smoothly
        img = img.scaled(
            max(1, round(w * sc)),
            max(1, round(h * sc)),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
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
        # (otherwise intermediate values such as "1 mm" appear briefly while typing -> tens of thousands of copies)
        sp.setKeyboardTracking(False)
    for sa in root.findChildren(QAbstractScrollArea):
        if sa.metaObject().className() == "QScrollArea":
            # cut nothing off: if the window gets narrower than the content there is a horizontal scroll bar
            sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)


def guard_wheel(root):
    """Mouse-wheel protection runs globally (theme.WheelGuard) – deliberately nothing to do here."""
    return None


def window_modal_dialogs():
    """QDialog.exec() otherwise blocks the whole program (all windows). With a parent window only that window –
    work can continue in other Passermark windows (leave the print dialog open, look at another document).
    """
    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtWidgets import QDialog

    if getattr(QDialog, "_pm_window_modal", False):
        return
    orig = QDialog.exec

    def exec_(self, *a, **k):
        try:
            if self.parentWidget() is not None and self.windowModality() != _Qt.WindowModality.WindowModal:
                self.setWindowModality(_Qt.WindowModality.WindowModal)
        except Exception:  # noqa: BLE001 – window placement is cosmetic
            pass
        try:  # own windows: wrap rows of buttons, wrap forms
            if type(self).__module__.startswith("pdfdruck") and not getattr(self, "_pm_responsive", False):
                self._pm_responsive = True
                responsive(self)
                scr = (self.parentWidget() or self).screen().availableGeometry()
                if self.minimumSizeHint().height() > scr.height() - 60:
                    scroll_body(self)  # taller than the screen: the content scrolls, the buttons stay
        except Exception:  # noqa: BLE001 – window placement is cosmetic
            pass
        try:  # never larger than the screen (small notebooks)
            scr = (self.parentWidget() or self).screen().availableGeometry()
            w, h = min(self.width(), scr.width() - 40), min(self.height(), scr.height() - 60)
            if (w, h) != (self.width(), self.height()):
                self.resize(max(320, w), max(240, h))
        except Exception:  # noqa: BLE001 – window placement is cosmetic
            pass
        return orig(self, *a, **k)

    QDialog.exec = exec_
    QDialog._pm_window_modal = True


def split_panels(root, left, right, right_width: int = 420):
    """Preview on the left, settings on the right – with a movable splitter; scrollable on the right (vertically
    and horizontally) so that nothing is cut off in a small window. left/right: layout or widget.
    """
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


# --------------------------------------------------------------------------- #
# responsive: rows of buttons wrap instead of widening the window/panel
# --------------------------------------------------------------------------- #
from PySide6.QtCore import QPoint, QRect, QSize  # noqa: E402
from PySide6.QtWidgets import QLayout  # noqa: E402


class FlowLayout(QLayout):
    """Row that wraps to the next line when space is short (like text). Knows heightForWidth so that
    scroll areas and docks get the right height.
    """

    def __init__(self, parent=None, hspacing: int = 6, vspacing: int = 6):
        super().__init__(parent)
        self._items = []
        self._h, self._v = hspacing, vspacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do(rect, False)

    def sizeHint(self):
        w = h = 0
        for it in self._items:
            if it.isEmpty():
                continue
            sh = it.sizeHint()
            w += sh.width() + (self._h if w else 0)
            h = max(h, sh.height())
        m = self.contentsMargins()
        return QSize(w + m.left() + m.right(), h + m.top() + m.bottom())

    def minimumSize(self):
        size = QSize()
        for it in self._items:
            if not it.isEmpty():
                size = size.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do(self, rect, test: bool) -> int:
        m = self.contentsMargins()
        r = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, line_h = r.x(), r.y(), 0
        row = []

        def place(items, y0, h):
            for it, xx in items:
                sh = it.sizeHint()
                it.setGeometry(QRect(QPoint(xx, y0 + (h - sh.height()) // 2), sh))

        for it in self._items:
            if it.isEmpty():
                continue
            sh = it.sizeHint()
            nx = x + sh.width() + self._h
            if nx - self._h > r.right() + 1 and line_h > 0:
                if not test:
                    place(row, y, line_h)
                row, x, y = [], r.x(), y + line_h + self._v
                nx, line_h = x + sh.width() + self._h, 0
            row.append((it, x))
            x, line_h = nx, max(line_h, sh.height())
        if not test:
            place(row, y, line_h)
        return y + line_h - rect.y() + m.bottom()


def flow_buttons(root, minimum: int = 3):
    """Convert horizontal rows that consist only of buttons (from `minimum`) into FlowLayouts."""
    from PySide6.QtWidgets import QAbstractButton, QBoxLayout, QHBoxLayout

    for lay in list(root.findChildren(QHBoxLayout)):
        parent = lay.parent()
        if not isinstance(parent, QBoxLayout):
            continue
        widgets, ok = [], True
        for i in range(lay.count()):
            it = lay.itemAt(i)
            if it.widget() is not None:
                if not isinstance(it.widget(), QAbstractButton):
                    ok = False
                    break
                widgets.append(it.widget())
            elif it.layout() is not None:
                ok = False
                break
        if not ok or len(widgets) < minimum:
            continue
        idx = next((i for i in range(parent.count()) if parent.itemAt(i).layout() is lay), -1)
        if idx < 0:
            continue
        stretch = parent.stretch(idx)
        parent.takeAt(idx)
        flow = FlowLayout()
        for w_ in widgets:
            lay.removeWidget(w_)
            flow.addWidget(w_)
        parent.insertLayout(idx, flow, stretch)
        lay.setParent(None)
        lay.deleteLater()


def responsive(root):
    """Everything that lets a window or panel become narrow: wrap forms, combo boxes and long texts
    may get narrower, rows of buttons wrap.
    """
    from PySide6.QtWidgets import QLabel, QSizePolicy

    fit_width(root)
    for lb in root.findChildren(QLabel):
        if lb.wordWrap():
            lb.setMinimumWidth(0)
            lb.setSizePolicy(QSizePolicy.Policy.Ignored, lb.sizePolicy().verticalPolicy())
    flow_buttons(root)


def scroll_body(dlg) -> bool:
    """Put the content of a window into a scroll area; the button bar at the bottom (OK/Cancel) stays.
    For windows that are taller than the available space on small screens. -> rebuilt?
    """
    from PySide6.QtWidgets import QBoxLayout, QDialogButtonBox, QFrame, QScrollArea, QVBoxLayout, QWidget

    top = dlg.layout()
    if not isinstance(top, QBoxLayout) or top.count() == 0:
        return False
    if any(isinstance(top.itemAt(i).widget(), QScrollArea) for i in range(top.count())):
        return False  # already has one
    last = top.itemAt(top.count() - 1).widget()
    n = top.count() - (1 if isinstance(last, QDialogButtonBox) else 0)
    inner = QWidget()
    il = QVBoxLayout(inner)
    il.setContentsMargins(0, 0, 0, 0)
    for _ in range(n):
        st = top.stretch(0)
        it = top.takeAt(0)
        if it.widget() is not None:
            il.addWidget(it.widget(), st)
        elif it.layout() is not None:
            lay = it.layout()
            lay.setParent(None)
            il.addLayout(lay, st)
        else:
            il.addItem(it)
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.Shape.NoFrame)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    sa.setWidget(inner)
    top.insertWidget(0, sa, 1)
    return True


class MsgBox(QPlainTextEdit):
    """Message to read, select and copy: grows up to ``lines`` rows, then scrolls – moves nothing."""

    def __init__(self, lines: int = 3, color: str = "", parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("QPlainTextEdit { background: transparent; %s }" % (f"color: {color};" if color else ""))
        self._lines = max(1, lines)
        self.document().contentsChanged.connect(self._fit)
        self._fit()

    def setText(self, text: str):
        """Set the message; an empty text hides the box."""
        self.setPlainText(text or "")
        self.setVisible(bool(text))
        QTimer.singleShot(0, self._fit)  # the number of rows is only known after wrapping

    def text(self) -> str:
        """The current message."""
        return self.toPlainText()

    def _fit(self):
        fm = self.fontMetrics()
        rows = max(1, min(self._lines, int(self.document().size().height()) or 1))
        m = self.contentsMargins()
        self.setFixedHeight(rows * fm.lineSpacing() + 2 * int(self.document().documentMargin()) + m.top() + m.bottom())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()


def make_responsive(w: QWidget):
    """Long entries (rolls, materials, messages) must not widen the window or push the
    settings into each other: shorten combo boxes, wrap forms.
    """
    for c in w.findChildren(QComboBox):
        c.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        c.setMinimumContentsLength(8)
        c.view().setTextElideMode(Qt.TextElideMode.ElideNone)
        c.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    for f in w.findChildren(QFormLayout):
        f.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        f.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    for lb in w.findChildren(QLabel):
        if lb.wordWrap():
            lb.setMinimumWidth(0)
            lb.setSizePolicy(QSizePolicy.Policy.Ignored, lb.sizePolicy().verticalPolicy())
