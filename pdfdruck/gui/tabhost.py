# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Fensterrahmen mit Reitern: jedes Dokument ist ein vollständiges Passermark-Fenster (Menüs, Leisten,
Seitenleisten) – hier als Reiter. Mit nur einem Reiter ist die Reiterleiste ausgeblendet; es sieht dann aus
wie ein einzelnes Fenster."""
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
            w.menuBar().setNativeMenuBar(False)       # Menü im Reiter, nicht in einer globalen Menüleiste
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
            w.close()                    # fragt bei ungespeicherten Änderungen; danach wird der Reiter entfernt

    def tab_closed(self):
        """Vom Dokumentfenster nach dem Schließen gerufen: letzter Reiter weg -> Rahmen schließen."""
        QTimer.singleShot(60, self._check_empty)

    def _check_empty(self):
        try:
            if self.tabs.count() == 0:
                self.close()
        except RuntimeError:             # schon gelöscht
            pass

    def detach(self, w):
        """Reiter in ein eigenes Fenster lösen."""
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
            if not w.close():            # Abbrechen bei „Änderungen speichern?“
                e.ignore()
                return
        hosts = getattr(self.ctl, "hosts", None)
        if hosts is not None and self in hosts:
            hosts.remove(self)
        super().closeEvent(e)
