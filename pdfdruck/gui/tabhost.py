# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Window frame with tabs: every document is a full Passermark window (menus, bars,
sidebars) – here as a tab. With only one tab, the tab bar is hidden; it then looks
like a single window.

With the own title bar (titlebar.py) the frame is transparent at the right: the tabs of the current document stand
there, outside the page area (design sheet 1.19). A window mask lets clicks into the empty margin through to
whatever lies behind the window.
"""

from __future__ import annotations

import os

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer
from PySide6.QtGui import QRegion
from PySide6.QtWidgets import QApplication, QHBoxLayout, QMainWindow, QMenu, QTabWidget, QWidget

from ..l10n import tr


class TabHost(QMainWindow):
    """Top-level window frame that holds one or more document windows as tabs."""

    def __init__(self, ctl):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        # tool tips also when the window manager does not report the (frameless) window as active
        self.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips, True)
        self.ctl = ctl
        from .titlebar import make_frameless, wanted

        self.outside = wanted()  # tabs outside the page area (transparent margin)
        self._edge_l, self._edge_r = (self.EDGE_L, self.EDGE_R) if self.outside else (0, 0)
        self.resize(1280 + self._edge_l + self._edge_r, 860)
        self.setWindowTitle("Passermark")
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setTabBarAutoHide(True)  # one document = looks like a normal window
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._current_changed)
        bar = self.tabs.tabBar()
        bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        bar.customContextMenuRequested.connect(self._tab_menu)
        bar.setElideMode(Qt.TextElideMode.ElideMiddle)
        if self.outside:
            self.setObjectName("passermarkHost")
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.frame = QWidget()
            self.frame.setObjectName("hostFrame")
            lay = self._frame_lay = QHBoxLayout(self.frame)
            lay.setContentsMargins(self._edge_l, 0, self._edge_r, 0)
            lay.setSpacing(0)
            lay.addWidget(self.tabs)
            self.tabs.setAutoFillBackground(True)  # the page area itself stays opaque
            self.setCentralWidget(self.frame)
            self._edge_timer = QTimer(self)
            self._edge_timer.setSingleShot(True)
            self._edge_timer.setInterval(0)
            self._edge_timer.timeout.connect(self._place_edges)
            self.tabs.currentChanged.connect(lambda _i: self._edge_timer.start())
        else:
            self.setCentralWidget(self.tabs)
        # own title bar (in each document window) -> no system frame; the grips sit at the page area
        self._grips = make_frameless(self, insets=lambda: (self._edge_l, self._edge_r))

    EDGE_L = 0  # width of the transparent margins
    EDGE_R = 52

    # -------------------------------------------------------------- #
    def add(self, w, activate: bool = True):
        """Add a document window as a tab."""
        w._host = self
        w.setWindowFlags(Qt.WindowType.Widget)
        mb = getattr(w, "mbar", None)  # not menuBar(): with the own title bar that would replace it
        if mb is not None:
            mb.setNativeMenuBar(False)  # menu in the tab, not in a global menu bar
        if getattr(w, "edges_outside", False):
            if self.outside:
                w.edge_right.setParent(self.frame)  # at once: the old frame of a detached tab may close soon
                w.edge_right.hide()
                for obj in (w, w.centralWidget()):
                    obj.installEventFilter(self)
            else:  # frame from before the setting was changed: keep them inside
                w.edges_inside()
        self.tabs.addTab(w, w.windowTitle() or "Passermark")
        if activate:
            self.tabs.setCurrentWidget(w)
        self.update_tab(w)
        if self.outside:
            self._edge_timer.start()

    # ---------- tabs in the transparent margin ---------- #
    def eventFilter(self, obj, ev):
        if self.outside and ev.type() in (QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.Show):
            self._edge_timer.start()
        return False

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.outside:
            self._edge_timer.start()

    def _place_edges(self):
        """Put the tabs of the current document into the margin; the window mask = page area + tabs."""
        cur = self.tabs.currentWidget()
        for w in self.windows():
            if w is not cur and getattr(w, "edges_outside", False):
                w.edge_right.hide()
        fw = self.frame
        off = fw.pos()
        region = QRegion(off.x() + self._edge_l, off.y(), fw.width() - self._edge_l - self._edge_r, fw.height())
        if cur is not None and getattr(cur, "edges_outside", False):
            right = cur.edge_right
            top = cur.centralWidget().mapTo(fw, QPoint(0, 0)).y() + 10
            right.setGeometry(fw.width() - self._edge_r, top, right.width(), right.sizeHint().height())
            right.layout().activate()
            right.show()
            right.raise_()
            for t in right.tabs:
                region += QRegion(t.geometry().translated(right.pos() + off))
        self.setMask(region)
        if self._grips is not None:
            self._grips.place()

    def windows(self) -> list:
        """The document windows in this frame."""
        return [self.tabs.widget(i) for i in range(self.tabs.count())]

    def show_tab(self, w):
        """Select the tab of ``w`` and bring the frame to the front."""
        if self.tabs.indexOf(w) >= 0:
            self.tabs.setCurrentWidget(w)
        self.show()
        self.raise_()
        self.activateWindow()

    def update_tab(self, w):
        """Refresh title and tooltip of the tab of ``w``."""
        i = self.tabs.indexOf(w)
        if i < 0:
            return
        name = getattr(w, "display_name", "") or "Passermark"
        self.tabs.setTabText(i, ("● " if getattr(w, "modified", False) else "") + name)
        self.tabs.setTabToolTip(i, getattr(w, "path", None) or name)
        if self.tabs.currentWidget() is w:
            self.setWindowTitle(w.windowTitle())

    def _current_changed(self, i):
        w = self.tabs.widget(i)
        if w is not None:
            self.setWindowTitle(w.windowTitle())
        sb = getattr(self, "_pm_sidebar", None)
        if sb is not None and sb.active:  # sidebar in its own window: follows the document in front
            sb.take(w)

    # -------------------------------------------------------------- #
    def close_tab(self, i):
        """Close the document in tab ``i``."""
        w = self.tabs.widget(i)
        if w is not None:
            w.close()  # asks about unsaved changes; afterwards the tab is removed

    def tab_closed(self):
        """Called by the document window after closing: last tab gone -> close the frame."""
        QTimer.singleShot(60, self._check_empty)

    def _check_empty(self):
        try:
            if self.tabs.count() == 0:
                self.close()
        except RuntimeError:  # already deleted
            pass

    def detach(self, w):
        """Detach a tab into its own window."""
        i = self.tabs.indexOf(w)
        if i < 0 or self.tabs.count() < 2:
            return
        self.tabs.removeTab(i)
        host = self.ctl.new_host() if hasattr(self.ctl, "new_host") else TabHost(self.ctl)
        host.add(w)
        host.move(self.pos().x() + 40, self.pos().y() + 40)
        host.show_tab(w)

    def take_all_from(self, other):
        """Alle Reiter eines anderen Fensters hierher holen."""
        for w in other.windows():
            other.tabs.removeTab(other.tabs.indexOf(w))
            self.add(w)
        other.close()

    def _tab_menu(self, pos):
        bar = self.tabs.tabBar()
        i = bar.tabAt(pos)
        if i < 0:
            return
        w = self.tabs.widget(i)
        m = QMenu(self)
        a = m.addAction(tr("In eigenem Fenster öffnen"), lambda: self.detach(w))
        a.setEnabled(self.tabs.count() > 1)
        m.addAction(tr("Schließen"), lambda: self.close_tab(self.tabs.indexOf(w)))
        o = m.addAction(tr("Andere schließen"), lambda: self._close_others(w))
        o.setEnabled(self.tabs.count() > 1)
        m.addSeparator()
        pa = m.addAction(tr("Eigenschaften …"), lambda: (self.tabs.setCurrentWidget(w), w.properties_dialog()))
        pa.setEnabled(getattr(w, "doc", None) is not None)
        path = getattr(w, "path", None)
        if path and os.path.isfile(path):
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices

            m.addAction(
                tr("Ordner öffnen"), lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))
            )
            m.addAction(tr("Pfad kopieren"), lambda: QApplication.clipboard().setText(path))
        m.exec(bar.mapToGlobal(pos))

    def _close_others(self, keep):
        for w in self.windows():
            if w is not keep:
                self.tabs.setCurrentWidget(w)
                if not w.close():
                    break
        self.tabs.setCurrentWidget(keep)

    def closeEvent(self, e):
        for w in self.windows():
            self.tabs.setCurrentWidget(w)
            if not w.close():  # cancelled at "Save changes?"
                e.ignore()
                return
        hosts = getattr(self.ctl, "hosts", None)
        if hosts is not None and self in hosts:
            hosts.remove(self)
        sb = getattr(self, "_pm_sidebar", None)
        if sb is not None:  # the sidebar window closes with its frame
            sb.shutdown()
        super().closeEvent(e)
