# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, Version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Shared GUI helpers and the session state (kept in memory only)."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
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
        if cb.minimumWidth() == 0:  # an explicit minimum wins over the width of the longest entry
            cb.setMinimumWidth(80)
    from PySide6.QtWidgets import QAbstractSpinBox

    for sp in root.findChildren(QAbstractSpinBox):
        # apply the value only on Enter/field change/arrow keys – not after every typed digit
        # (otherwise intermediate values such as "1 mm" appear briefly while typing -> tens of thousands of copies)
        sp.setKeyboardTracking(False)
    for sa in root.findChildren(QAbstractScrollArea):
        if sa.metaObject().className() == "QScrollArea":
            # cut nothing off: if the window gets narrower than the content there is a horizontal scroll bar
            sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    stack_rows(root)  # rows and forms lie top-to-bottom when it gets narrow
    from PySide6.QtWidgets import QCheckBox, QRadioButton

    wrap_buttons(root, (QCheckBox, QRadioButton))  # long check box texts break into lines


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
                fit_height(self)  # wrapped texts: the window grows along instead of squeezing the content
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
    # the settings on the right behave like a side panel: wrap and stack instead of being cut off
    from PySide6.QtWidgets import QToolButton

    responsive_panel(rw)
    wrap_buttons(rw, (QToolButton,))  # section headings („3. Nummerierung – …“)
    lay = rw.layout()
    if lay is not None:  # distance to the window edge on the right
        m = lay.contentsMargins()
        lay.setContentsMargins(m.left(), m.top(), max(m.right(), 12), m.bottom())
    follow_minimum(rw, sa)
    return sp


def follow_minimum(content, area):
    """Keep scroll area ``area`` at least as wide as ``content`` needs (updated when the content changes)."""
    return _MinFollow(content, area)


class _MinFollow(QObject):
    """The scroll area of a settings side never gets narrower than what its content needs – the splitter stops
    there instead of cutting the content off."""

    def __init__(self, content, area):
        super().__init__(content)
        self.content, self.area = content, area
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(0)
        self.timer.timeout.connect(self.update)
        content.installEventFilter(self)
        self.timer.start()

    def update(self):
        """Set the area's minimum width to what the content needs now."""
        try:
            need = self.content.minimumSizeHint().width() + self.area.verticalScrollBar().sizeHint().width() + 2
            self.area.setMinimumWidth(max(260, need))
        except RuntimeError:
            pass  # already deleted

    def eventFilter(self, obj, ev):
        if ev.type() in (QEvent.Type.LayoutRequest, QEvent.Type.Show):
            self.timer.start()
        return False


def _fit_need(win) -> tuple:
    """(minimum width, height) the window's layout needs at its current width (capped at the screen)."""
    lay = win.layout()
    if lay is None:
        return 0, 0
    lay.activate()
    mn = lay.totalMinimumSize()
    h = mn.height()
    if lay.hasHeightForWidth():
        h = max(h, lay.totalHeightForWidth(win.width()))
    base = win.property("_pm_base_w")
    scr = win.screen().availableGeometry()
    return min(max(int(base or 0), mn.width()), scr.width() - 40), min(h, scr.height() - 60)


def _fit_window(win):
    """Raise the window's minimum size to what the content needs (Qt grows the window along)."""
    try:
        if win is None or not win.isWindow() or not win.isVisible():
            return
        w, h = _fit_need(win)
        if h <= 0:
            return
        if (win.minimumWidth(), win.minimumHeight()) != (w, h):
            win.setMinimumSize(w, h)
        if win.height() < h:
            win.resize(win.width(), h)
    except RuntimeError:
        pass  # window already closed


class _FitHeight(QObject):
    """A window is never lower than its content needs at its current width. Texts and buttons that wrap get
    taller when the window is narrow; Qt itself only looks at the minimum without line breaks – the content
    was squeezed into each other when a window opened (settings, repair).

    Keeps no Python attributes: PySide may hand the filter to Python as a fresh wrapper later (the original one
    collected with a dialog's local variable) – the watched window comes as ``obj``, its explicit minimum width
    is stored as a Qt property on the window."""

    def eventFilter(self, obj, ev):
        if ev.type() in (QEvent.Type.Show, QEvent.Type.LayoutRequest, QEvent.Type.Resize):
            QTimer.singleShot(0, lambda w=obj: _fit_window(w))
        return False


def fit_height(win):
    """Install _FitHeight once on a dialog or window."""
    if win is None or win.property("_pm_fit_height"):
        return
    win.setProperty("_pm_fit_height", True)
    win.setProperty("_pm_base_w", win.minimumWidth())  # an explicit minimum width of the window stays
    win.installEventFilter(_FitHeight(win))


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

    def __init__(self, parent=None, hspacing: int = 6, vspacing: int = 6, uniform: bool = False):
        super().__init__(parent)
        self._items = []
        self._h, self._v = hspacing, vspacing
        self.uniform = uniform  # all items equally wide, in as many columns as the widest one allows
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

    @staticmethod
    def _hint(it, width: int) -> QSize:
        """Size of an item, never wider than the row (a wrapping button then breaks its text, see wrap_buttons)."""
        sh = it.sizeHint()
        if width > 0 and sh.width() > width:
            sh = QSize(max(width, it.minimumSize().width()), sh.height())
        return sh

    def columns(self, width: int) -> int:
        """Uniform mode: how many equally wide columns fit (the widest item in one line decides)."""
        items = [it for it in self._items if not it.isEmpty()]
        if not items:
            return 1
        widest = max(it.sizeHint().width() for it in items)
        return max(1, min(len(items), (width + self._h) // max(1, widest + self._h)))

    def _do_uniform(self, rect, test: bool) -> int:
        m = self.contentsMargins()
        r = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        items = [it for it in self._items if not it.isEmpty()]
        if not items:
            return 0
        cols = self.columns(r.width())
        cw = max((r.width() - self._h * (cols - 1)) // cols, max(it.minimumSize().width() for it in items))
        y = r.y()
        for i in range(0, len(items), cols):
            row = items[i : i + cols]
            h = max(it.heightForWidth(cw) if it.hasHeightForWidth() else it.sizeHint().height() for it in row)
            if not test:
                for k, it in enumerate(row):
                    g = QRect(r.x() + k * (cw + self._h), y, cw, h)
                    w = it.widget()
                    # straight onto the widget: QWidgetItem would keep a tool button at its own width
                    (w.setGeometry if w is not None else it.setGeometry)(g)
            y += h + self._v
        return y - self._v - rect.y() + m.bottom()

    def _do(self, rect, test: bool) -> int:
        if self.uniform:
            return self._do_uniform(rect, test)
        m = self.contentsMargins()
        r = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, line_h = r.x(), r.y(), 0
        row = []

        def place(items, y0, h):
            for it, xx in items:
                sh = self._hint(it, r.width())
                it.setGeometry(QRect(QPoint(xx, y0 + (h - sh.height()) // 2), sh))

        for it in self._items:
            if it.isEmpty():
                continue
            sh = self._hint(it, r.width())
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
        flow = FlowLayout(uniform=True)  # equally wide buttons
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
    keep = form_labels(root)
    for lb in root.findChildren(QLabel):
        if lb.wordWrap():
            lb.setMinimumWidth(0)
            if any(lb is k for k in keep):
                continue  # a label beside its field: "Ignored" gave it 0 px width – it vanished (print dialog)
            lb.setSizePolicy(QSizePolicy.Policy.Ignored, lb.sizePolicy().verticalPolicy())
    flow_buttons(root)


def form_labels(root) -> list:
    """The labels in the label column of all form layouts below ``root``."""
    from PySide6.QtWidgets import QFormLayout

    out = []
    for f in root.findChildren(QFormLayout):
        for r in range(f.rowCount()):
            it = f.itemAt(r, QFormLayout.ItemRole.LabelRole)
            w = it.widget() if it is not None else None
            if w is not None:
                out.append(w)
    return out


def _wrap_words(text: str, fm, width: int) -> str:
    """``text`` with line breaks so that no line is wider than ``width`` (a single long word stays whole).
    A "…" stays with the word before it."""
    words = text.replace(" …", "\u00a0…").split(" ")
    lines, cur = [], ""
    for w in words:
        cand = f"{cur} {w}" if cur else w
        if cur and fm.horizontalAdvance(cand) > width:
            lines.append(cur)
            cur = w
        else:
            cur = cand
    lines.append(cur)
    return "\n".join(lines).replace("\u00a0", " ")


class _ButtonWrapper(QObject):
    """Breaks the text of push buttons into lines when they get narrow (see wrap_buttons)."""

    def eventFilter(self, b, ev):
        if ev.type() == QEvent.Type.Resize:
            self.rewrap(b)
        return False

    @staticmethod
    def _pad(b) -> int:
        from PySide6.QtWidgets import QStyle

        from PySide6.QtWidgets import QCheckBox, QRadioButton

        if isinstance(b, (QCheckBox, QRadioButton)):  # box/circle in front of the text instead of a frame
            st = b.style()
            return (
                st.pixelMetric(QStyle.PixelMetric.PM_IndicatorWidth, None, b)
                + st.pixelMetric(QStyle.PixelMetric.PM_CheckBoxLabelSpacing, None, b)
                + 8
            )
        pad = 2 * b.style().pixelMetric(QStyle.PixelMetric.PM_ButtonMargin, None, b) + 16
        if not b.icon().isNull():
            pad += b.iconSize().width() + 4
        return pad

    def rewrap(self, b):
        """Break the button's text for its current width (a text set by the program becomes the new source)."""
        shown = b.property("wrapShown")
        if shown is None or b.text() != shown:  # new text from the program: that is the source now
            b.setProperty("wrapSource", b.text().replace("\n", " "))
            self.set_minimum(b)
        src = b.property("wrapSource") or ""
        text = _wrap_words(src, b.fontMetrics(), b.width() - self._pad(b))
        b.setProperty("wrapShown", text)
        if text != b.text():
            b.setText(text)

    def set_minimum(self, b):
        """As narrow as the longest word allows (instead of the whole text in one line)."""
        src = b.property("wrapSource") or ""
        fm = b.fontMetrics()
        longest = max((fm.horizontalAdvance(w) for w in src.replace(" …", "\u00a0…").split(" ")), default=0)
        b.setMinimumWidth(longest + self._pad(b))


_wrapper = None


def wrap_buttons(root, kinds=None):
    """Push buttons (and with ``kinds`` other buttons such as check boxes) with text get narrow by breaking
    their text into lines instead of being cut off."""
    from PySide6.QtWidgets import QDialogButtonBox, QPushButton

    global _wrapper
    if _wrapper is None:
        _wrapper = _ButtonWrapper()
    found = []
    for k in kinds or (QPushButton,):
        kids = root.findChildren(k)
        found += kids if isinstance(kids, list) else list(kids or [])
    for b in found:
        t = b.text()
        if " " not in t.strip() or isinstance(b.parentWidget(), QDialogButtonBox) or b.property("wrapSource"):
            continue
        b.setProperty("wrapSource", t)
        _wrapper.set_minimum(b)
        b.installEventFilter(_wrapper)


def wrap_tabs(tw) -> bool:
    """Tabs of a panel in rows that wrap (instead of a tab bar with scroll arrows that hides tabs)."""
    from PySide6.QtWidgets import QBoxLayout, QButtonGroup, QToolButton

    host = tw.parentWidget()
    lay = host.layout() if host is not None else None
    if not isinstance(lay, QBoxLayout) or getattr(tw, "_flow_tabs", None) is not None:
        return False
    idx = lay.indexOf(tw)
    if idx < 0:
        return False
    bar = QWidget(host)
    bar.setObjectName("flowTabs")
    flow = FlowLayout(bar, 6, 6, uniform=True)  # equally wide tab buttons, same gaps as the button rows
    group = QButtonGroup(bar)
    group.setExclusive(True)
    tw._flow_tabs = bar

    def sync():
        btns = group.buttons()
        if len(btns) != tw.count():
            for b in btns:
                group.removeButton(b)
                flow.removeWidget(b)
                b.deleteLater()
            for i in range(tw.count()):
                b = QToolButton(bar)
                b.setObjectName("flowTab")
                b.setCheckable(True)
                b.setAutoRaise(True)
                group.addButton(b, i)
                flow.addWidget(b)
        for i in range(tw.count()):
            b = group.button(i)
            b.setText(tw.tabText(i))  # same text rules as the tab ("&&" = a literal &)
            b.setToolTip(tw.tabToolTip(i))
            b.setIcon(tw.tabIcon(i))
            b.setEnabled(tw.isTabEnabled(i))
            b.setVisible(tw.isTabVisible(i))
            b.setChecked(i == tw.currentIndex())

    group.idClicked.connect(tw.setCurrentIndex)
    tw.currentChanged.connect(lambda _i: sync())
    for name in ("setTabText", "setTabEnabled", "setTabVisible", "setTabToolTip", "setTabIcon"):
        orig = getattr(tw, name)
        setattr(tw, name, lambda *a, _o=orig: (_o(*a), sync())[0])
    for name in ("addTab", "insertTab", "removeTab"):
        orig = getattr(tw, name)
        setattr(tw, name, lambda *a, _o=orig: (lambda r: (sync(), r)[1])(_o(*a)))
    tw.tabBar().hide()
    lay.insertWidget(idx, bar)
    sync()
    return True


def wrap_views(root):
    """Lists and tables in a panel: text wraps and rows grow when a column gets narrow."""
    from PySide6.QtWidgets import QTableView, QTreeView

    for v in root.findChildren(QTreeView):
        if v.wordWrap():
            v.setTextElideMode(Qt.TextElideMode.ElideNone)
            t = QTimer(v)
            t.setSingleShot(True)
            t.setInterval(60)
            t.timeout.connect(v.doItemsLayout)
            v.header().sectionResized.connect(lambda *_a, t=t: t.start())
    for v in root.findChildren(QTableView):
        v.setWordWrap(True)
        v.setTextElideMode(Qt.TextElideMode.ElideNone)
        t = QTimer(v)
        t.setSingleShot(True)
        t.setInterval(60)
        t.timeout.connect(v.resizeRowsToContents)
        v.horizontalHeader().sectionResized.connect(lambda *_a, t=t: t.start())


def responsive_panel(root, labels_above: bool = True):
    """For the panels of the sidebars: like responsive(), and also: button texts and tabs wrap, lists and
    tables wrap their text – getting narrow breaks lines instead of cutting things off."""
    from PySide6.QtWidgets import QLabel, QTabWidget

    for lb in root.findChildren(QLabel):  # texts wrap instead of setting the panel's minimum width (also later ones)
        if not lb.wordWrap() and lb.pixmap().isNull():
            lb.setWordWrap(True)
    from PySide6.QtWidgets import QFormLayout, QPushButton

    for f in root.findChildren(QFormLayout) if labels_above else []:  # narrow panel: label above the field
        f.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
    for b in root.findChildren(QPushButton):  # arrows and symbols (◀ ▶ …): no 80 px minimum of the style
        if len(b.text().strip()) <= 2 and b.minimumWidth() == 0:
            b.setMinimumWidth(30)
    flow_buttons(root, 2)  # two buttons side by side already wrap
    responsive(root)
    wrap_buttons(root)
    for tw in root.findChildren(QTabWidget):
        wrap_tabs(tw)
    wrap_views(root)


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
    keep = form_labels(w)
    for lb in w.findChildren(QLabel):
        if lb.wordWrap():
            lb.setMinimumWidth(0)
            if not any(lb is k for k in keep):
                lb.setSizePolicy(QSizePolicy.Policy.Ignored, lb.sizePolicy().verticalPolicy())
    stack_rows(w)
    from PySide6.QtWidgets import QCheckBox, QRadioButton

    wrap_buttons(w, (QCheckBox, QRadioButton))  # long check box texts break into lines


# --------------------------------------------------------------------------- #
# rows that stack when it gets narrow


def needs_stack(needed: int, available: int, stacked: bool, slack: int = 12) -> bool:
    """Should a row lie top-to-bottom? With hysteresis, so it does not flip back and forth at the border."""
    if available <= 0:
        return stacked
    return needed > available if not stacked else needed + slack > available


def _scroll_viewport(w):
    """Viewport of the nearest scroll area above ``w`` (or None)."""
    from PySide6.QtWidgets import QAbstractScrollArea

    p = w.parentWidget() if w is not None else None
    while p is not None:
        if isinstance(p, QAbstractScrollArea):
            return p.viewport()
        p = p.parentWidget()
    return None


def _available(lay) -> int:
    """Width a layout really has: its own, but in a scroll area at most up to the visible right edge."""
    pw = lay.parentWidget()
    g = lay.geometry()
    avail = g.width() or (pw.width() if pw is not None else 0)
    vp = _scroll_viewport(pw)
    if vp is not None and pw is not None:
        x = pw.mapTo(vp.parentWidget(), g.topLeft()).x() - vp.geometry().x()
        avail = min(avail, vp.width() - max(0, x) - 4)
    return avail


def _row_needed(lay) -> int:
    """Minimum width of a horizontal row when all items stand side by side."""
    m = lay.contentsMargins()
    total, n = m.left() + m.right(), 0
    for i in range(lay.count()):
        it = lay.itemAt(i)
        w = it.widget()
        if w is not None and w.isHidden():
            continue
        if it.spacerItem() is not None:
            continue
        sz = it.minimumSize().width()
        if w is not None and not getattr(w, "wordWrap", lambda: True)():
            sz = max(sz, w.sizeHint().width())  # labels without wrapping: their text
        total += sz
        n += 1
    return total + max(0, n - 1) * max(0, lay.spacing())


def _form_needed(f) -> int:
    from PySide6.QtWidgets import QFormLayout

    lab = fld = 0
    for r in range(f.rowCount()):
        li = f.itemAt(r, QFormLayout.ItemRole.LabelRole)
        fi = f.itemAt(r, QFormLayout.ItemRole.FieldRole)
        if li is not None and (li.widget() is None or not li.widget().isHidden()):
            lab = max(lab, li.sizeHint().width())
        if fi is not None:
            fld = max(fld, fi.minimumSize().width())
    m = f.contentsMargins()
    return lab + fld + max(0, f.horizontalSpacing()) + m.left() + m.right()


def _visible_items(lay) -> int:
    return sum(
        1
        for i in range(lay.count())
        if lay.itemAt(i).widget() is not None
        and not lay.itemAt(i).widget().isHidden()
        or lay.itemAt(i).layout() is not None
    )


def restack(root):
    """Lay rows top-to-bottom where they do not fit side by side (and back when there is room again); forms put
    the label above the field. Picks up rows added later, too (results lists that are rebuilt)."""
    from PySide6.QtWidgets import QBoxLayout, QFormLayout, QHBoxLayout

    for lay in root.findChildren(QHBoxLayout):
        if _visible_items(lay) < 2 or lay.property("noStack"):
            continue
        stacked = lay.direction() == QBoxLayout.Direction.TopToBottom
        want = needs_stack(_row_needed(lay), _available(lay), stacked)
        if want != stacked:
            lay.setDirection(QBoxLayout.Direction.TopToBottom if want else QBoxLayout.Direction.LeftToRight)
    for f in root.findChildren(QFormLayout):
        stacked = f.rowWrapPolicy() == QFormLayout.RowWrapPolicy.WrapAllRows
        want = needs_stack(_form_needed(f), _available(f), stacked)
        if want != stacked:
            f.setRowWrapPolicy(
                QFormLayout.RowWrapPolicy.WrapAllRows if want else QFormLayout.RowWrapPolicy.WrapLongRows
            )


class _Stacker(QObject):
    """Calls restack() after the panel or its scroll area changed size (once per event loop pass)."""

    def __init__(self, root):
        super().__init__(root)
        self.root = root
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(0)
        self.timer.timeout.connect(self._run)

    def _run(self):
        try:
            restack(self.root)
        except RuntimeError:
            pass  # widget already deleted

    def eventFilter(self, obj, ev):
        if ev.type() in (QEvent.Type.Resize, QEvent.Type.Show, QEvent.Type.LayoutRequest):
            self.timer.start()
        return False


def stack_rows(root):
    """Make rows and forms below ``root`` stack when it gets narrow (see restack) – nothing is cut off."""
    if root.property("_stacker"):
        return
    st = _Stacker(root)
    root.setProperty("_stacker", True)
    root.installEventFilter(st)
    vp = _scroll_viewport(root)
    if vp is not None:
        vp.installEventFilter(st)
    from PySide6.QtWidgets import QAbstractScrollArea

    for sa in root.findChildren(QAbstractScrollArea):
        sa.viewport().installEventFilter(st)
