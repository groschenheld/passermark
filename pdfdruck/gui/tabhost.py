# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Window frame with tabs: every document is a full Passermark window (menus, bars,
sidebars) – here as a tab. With only one tab, the tab bar is hidden; it then looks
like a single window.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QMainWindow, QMenu, QTabWidget

from ..l10n import tr


class TabHost(QMainWindow):
    def __init__(self, ctl):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.ctl = ctl
        self.resize(1280, 860)
        self.setWindowTitle("Passermark")
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setTabBarAutoHide(True)              # ein Dokument = sieht aus wie ein normales Fenster
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._current_changed)
        bar = self.tabs.tabBar()
        bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        bar.customContextMenuRequested.connect(self._tab_menu)
        bar.setElideMode(Qt.TextElideMode.ElideMiddle)
        self.setCentralWidget(self.tabs)

    # -------------------------------------------------------------- #
    def add(self, w, activate: bool = True):
        w._host = self
        w.setWindowFlags(Qt.WindowType.Widget)
        try:
            w.menuBar().setNativeMenuBar(False)       # menu in the tab, not in a global menu bar
        except Exception:
            pass
        self.tabs.addTab(w, w.windowTitle() or "Passermark")
        if activate:
            self.tabs.setCurrentWidget(w)
        self.update_tab(w)

    def windows(self) -> list:
        return [self.tabs.widget(i) for i in range(self.tabs.count())]

    def show_tab(self, w):
        if self.tabs.indexOf(w) >= 0:
            self.tabs.setCurrentWidget(w)
        self.show()
        self.raise_()
        self.activateWindow()

    def update_tab(self, w):
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

    # -------------------------------------------------------------- #
    def close_tab(self, i):
        w = self.tabs.widget(i)
        if w is not None:
            w.close()                    # asks about unsaved changes; afterwards the tab is removed

    def tab_closed(self):
        """Called by the document window after closing: last tab gone -> close the frame."""
        QTimer.singleShot(60, self._check_empty)

    def _check_empty(self):
        try:
            if self.tabs.count() == 0:
                self.close()
        except RuntimeError:             # already deleted
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
            if not w.close():            # cancelled at "Save changes?"
                e.ignore()
                return
        hosts = getattr(self.ctl, "hosts", None)
        if hosts is not None and self in hosts:
            hosts.remove(self)
        super().closeEvent(e)
