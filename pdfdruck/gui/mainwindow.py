# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Acrobat-like main window: thumbnails on the left, continuous view, toolbar, page operations."""

from __future__ import annotations

import os

from PySide6.QtCore import QRect, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..l10n import tr
from ..papersizes import UI_FORMATS as PAPER_NAMES  # mm, portrait – the shared table of formats
from . import theme
from .common import render_pixmap
from .icons import icon as svg_icon
from .mainactions import MainActionsMixin
from .maincheck import MainCheckMixin
from .maincolour import MainColourMixin
from .maindialogs import MainDialogsMixin
from .mainfile import MainFileMixin
from .pageview import PageView  # noqa: F401
from .pagewidgets import Ruler
from .thumbs import THUMB_ASPECT, THUMB_PIX, THUMB_W, ThumbDelegate, ThumbList, ThumbSource


def page_size_text(w_pt: float, h_pt: float) -> str:
    """Page size as text in mm, with the name of the paper size if it is a known one."""
    w, h = w_pt * 25.4 / 72, h_pt * 25.4 / 72
    lo, hi = sorted((w, h))
    name = next((n for n, (a, b) in PAPER_NAMES.items() if abs(lo - a) <= 1.5 and abs(hi - b) <= 1.5), None)
    orient = tr("quer") if w > h + 0.5 else tr("hoch")
    txt = tr("{0:.0f} × {1:.0f} mm").format(w, h)
    return f"{txt}  ({name} {orient})" if name else txt


class MainWindow(MainDialogsMixin, MainCheckMixin, MainColourMixin, MainFileMixin, MainActionsMixin, QMainWindow):
    """The document window: page view, sidebars, menus and toolbars for one open document."""

    def __init__(self, ctl):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.ctl = ctl
        self.resize(1280, 860)
        self.setAcceptDrops(True)
        self.doc = None
        self.path = None  # file on disk (None = never saved)
        self.display_name = ""
        self.modified = False

        self.view = PageView(single=getattr(ctl, "view_single", True))
        self._jobs = []  # running jobs (separate processes)
        # rulers at the top/left edge of the view (stay in place when scrolling)
        from PySide6.QtWidgets import QGridLayout

        central = QWidget()
        grid = QGridLayout(central)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)
        self.ruler_h = Ruler(self.view, True)
        self.ruler_v = Ruler(self.view, False)
        self.ruler_corner = QWidget()
        self.ruler_corner.setFixedSize(Ruler.SIZE, Ruler.SIZE)
        self.ruler_corner.setStyleSheet(f"background: {theme.PANEL};")
        grid.addWidget(self.ruler_corner, 0, 0)
        grid.addWidget(self.ruler_h, 0, 1)
        grid.addWidget(self.ruler_v, 1, 0)
        grid.addWidget(self.view, 1, 1)
        for r in (self.ruler_corner, self.ruler_h, self.ruler_v):
            r.hide()
        self._rulers_on = False
        self.setCentralWidget(central)
        self.view.viewMoved.connect(self._rulers_update)
        self.view.on_cursor = self._rulers_cursor
        self.view.pageChanged.connect(self._page_changed)
        self.view.infoReady.connect(lambda: self._page_changed(self.view.current))
        self.view.zoomChanged.connect(self._zoom_changed)

        # thumbnails (multi-selection for page operations)
        self.thumbs = ThumbList()
        self.thumbs.setViewMode(QListWidget.ViewMode.ListMode)
        self.thumbs.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.thumbs.setUniformItemSizes(False)
        self.thumbs.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.thumbs.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.thumbs.setItemDelegate(ThumbDelegate(self.thumbs))
        self.thumbs.setStyleSheet(
            f"QListWidget {{ background: {theme.BG}; border: none; }}"
            "QListWidget::item, QListWidget::item:selected { background: transparent; }"
        )
        self.thumbs.setMinimumWidth(110)
        self._thumb_resize = QTimer(self, singleShot=True, interval=200, timeout=self._requeue_thumbs)
        self.thumbs.resized.connect(self._thumb_resize.start)
        self.thumbs.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.thumbs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.thumbs.customContextMenuRequested.connect(self._thumb_menu)
        self.thumbs.itemClicked.connect(lambda it: self.view.goto(self.thumbs.row(it)))
        self.thumbs.pagesMoved.connect(self.move_pages_to)
        self.thumbs.zoomed.connect(self._thumb_zoom)
        dock = QDockWidget(tr("Seiten"), self)
        dock.setWidget(self._thumb_panel())
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable | QDockWidget.DockWidgetFeature.DockWidgetMovable
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self.resizeDocks([dock], [165], Qt.Orientation.Horizontal)
        self._thumb_queue = []
        self._thumb_timer = QTimer(self, interval=0, timeout=self._render_thumbs)
        self._thumb_src = ThumbSource(self)  # thumbnails via the render process
        self.view.masterReady.connect(self._thumb_from_master)

        self._build_actions(dock)
        self.lbl_size = QLabel()
        self.lbl_size.setContentsMargins(8, 0, 8, 0)
        self.lbl_size.setFont(theme.mono_font(9.5))
        self.statusBar().addPermanentWidget(self.lbl_size)
        self._build_preflight(dock)
        self._build_color(dock)
        self._build_edit(dock)
        self._dock_widths = {}
        for d in (dock, self.pf_dock, self.color_dock, self.edit_dock):
            d.visibilityChanged.connect(lambda vis, d=d: self._dock_vis(d, vis))
        self._build_workspaces(dock)
        self.lbl_measure = QLabel()
        self.lbl_measure.setContentsMargins(8, 0, 8, 0)
        self.lbl_measure.setFont(theme.mono_font(9.5))
        self.lbl_measure.setToolTip(tr("Messung: Länge, waagrechter und senkrechter Abstand, Winkel"))
        self.statusBar().addPermanentWidget(self.lbl_measure)  # bottom far right, does not get in the way
        self.view.on_measure = self.lbl_measure.setText
        self.lbl_proof = QLabel()
        self.lbl_proof.setContentsMargins(8, 0, 8, 0)
        self.lbl_proof.setStyleSheet(f"color: {theme.ACCENT};")
        self.lbl_proof.hide()
        self.statusBar().addPermanentWidget(self.lbl_proof)
        self._update_title()

    # ---------------- workspaces ---------------- #
    WORKSPACES = ("view", "prep", "edit", "vdp", "plot", "auto")

    def _build_workspaces(self, pages_dock):
        """Second bar: choose the work area; the tools of that area to its right."""
        from PySide6.QtGui import QActionGroup

        self._pages_dock = pages_dock
        self.a_presets = self._act(tr("Preset-Ordner öffnen"), self._open_presets_dir, None, "folder_gear")
        self.a_cli = self._act(tr("Kommandozeile – Anleitung (PDF)"), self._open_cli_howto, None, "terminal")
        self.a_vdp_howto = self._act(tr("Variable Daten – Anleitung (PDF)"), self._open_vdp_howto, None, "book")
        self.a_examples = self._act(tr("Beispiele für Variable Daten holen …"), self._get_examples, None, "qr")
        tools = {
            "view": [(self.a_copy, tr("Text kopieren"))],
            "prep": [
                (self.a_preflight, tr("Prüfen")),
                (self.a_colorcheck, tr("Farbe")),
                (self.a_pipette, tr("Pipette")),
                (self.a_press, tr("Für Druckerei")),
                (self.a_manip_cmyk, tr("CMYK")),
                (self.a_manip_crop, tr("Beschneiden")),
                (self.a_cut, tr("CutContour")),
                (self.a_separate, tr("Objekte trennen")),
                (self.a_repair, tr("Reparieren")),
            ],
            "edit": [
                (self.a_edit, tr("Text/Ebenen")),
                (self.a_pipette, tr("Pipette")),
                (self.a_ins_after, tr("Einfügen")),
                (self.a_delete, tr("Löschen")),
                (self.a_rot_l, tr("Links drehen")),
                (self.a_rot_r, tr("Rechts drehen")),
                (self.a_up, tr("Nach vorne")),
                (self.a_down, tr("Nach hinten")),
                (self.a_split, tr("Teilen")),
                (self.a_merge, tr("Zusammenführen")),
                (self.a_export, tr("Exportieren")),
            ],
            "vdp": [
                (self.a_vdp, tr("Variable Daten")),
                (self.a_data, tr("Daten erfassen")),
                (self.a_examples, tr("Beispiele")),
                (self.a_vdp_howto, tr("Anleitung")),
            ],
            "plot": [(self.a_plan, tr("Plandruck")), (self.a_poster, tr("Posterdruck")), (self.a_rolls, tr("Rollen"))],
            "auto": [(self.a_presets, tr("Presets")), (self.a_cli, tr("Anleitung"))],
        }
        self.addToolBarBreak()
        tb = self.ws_bar = self.addToolBar(tr("Arbeitsbereich"))
        tb.setObjectName("workspaces")
        tb.setMovable(False)
        tb.setIconSize(QSize(18, 18))
        grp = QActionGroup(self)
        grp.setExclusive(True)
        self.ws_actions = {}
        names = {
            "view": tr("Anzeigen & Drucken"),
            "prep": tr("Druckaufbereitung"),
            "edit": tr("Bearbeiten"),
            "vdp": tr("Variable Daten"),
            "plot": tr("Plan & Poster"),
            "auto": tr("Automatisierung"),
        }
        for key in self.WORKSPACES:
            a = QAction(names[key], self)
            a.setCheckable(True)
            a.setData(key)
            grp.addAction(a)
            tb.addAction(a)
            btn = tb.widgetForAction(a)
            if isinstance(btn, QToolButton):
                btn.setObjectName("workspace")
            self.ws_actions[key] = a
        tb.setStyleSheet(
            f"QToolButton#workspace {{ padding: 3px 10px; border-bottom: 2px solid transparent; }}"
            f"QToolButton#workspace:checked {{ color: {theme.ACCENT}; border-bottom: 2px solid {theme.ACCENT};"
            f" background: transparent; }}"
        )
        # The tools of the workspace live in their own bar: if the window gets narrow, it moves to the next
        # row (instead of disappearing behind the » arrow) – see _fit_toolbars
        tb = self.ws_tools_bar = self.addToolBar(tr("Werkzeuge des Arbeitsbereichs"))
        tb.setObjectName("workspace_tools")
        tb.setMovable(False)
        tb.setIconSize(QSize(18, 18))
        self.ws_tools = {}
        for key, acts in tools.items():
            holders = []
            for a, text in acts:
                a.setIconText(text)  # short text for bars; menus keep showing the full text
                b = QToolButton()
                b.setDefaultAction(a)
                b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                holders.append(tb.addWidget(b))
            self.ws_tools[key] = holders
        grp.triggered.connect(lambda a: self.set_workspace(a.data()))
        from .. import l10n

        key = l10n.load_settings().get("workspace", "view")
        self.set_workspace(key if key in self.ws_actions else "view", remember=False)

    def _fit_toolbars(self):
        """Toolbar of the workspace next to the workspaces if there is room – otherwise in its own row."""
        tb, tt = getattr(self, "ws_bar", None), getattr(self, "ws_tools_bar", None)
        if tb is None or tt is None:
            return
        want = tb.sizeHint().width() + tt.sizeHint().width() + 24 > self.width()
        if want != bool(self.toolBarBreak(tt)):
            if want:
                self.insertToolBarBreak(tt)
            else:
                self.removeToolBarBreak(tt)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit_toolbars()

    def set_workspace(self, key: str, remember: bool = True):
        """Switch to workspace ``key`` and show its tools (``remember``: store it as the user's choice)."""
        self.workspace = key
        self.ws_actions[key].setChecked(True)
        for k, holders in self.ws_tools.items():
            for h in holders:
                h.setVisible(k == key)
        self._fit_toolbars()
        if key != "edit" and self.a_edit.isChecked():
            self.a_edit.setChecked(False)  # edit mode belongs to the Edit area
        if key == "prep":
            self.pf_dock.show()
            self.pf_dock.raise_()
        elif key == "edit":
            self._pages_dock.show()
            if not self.a_edit.isChecked():
                self.a_edit.setChecked(True)  # start edit mode: fill the dock + lists
            self.edit_dock.raise_()  # bring the dock in front of the page overview
        elif self._pages_dock.isVisible():
            self._pages_dock.raise_()
        if remember:
            from .. import l10n

            st = l10n.load_settings()
            if st.get("workspace") != key:
                st["workspace"] = key
                try:
                    l10n.save_settings(st)
                except OSError:
                    pass

    @staticmethod
    def licenses_path() -> str:
        """Folder "licenses" next to the program (installer/AppImage); from the source code: LICENSE."""
        from .. import platform as _pl

        for d in _pl.app_dirs():
            p = os.path.join(d, "licenses")
            if os.path.isdir(p):
                return p
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        return os.path.join(root, "LICENSE")

    def _open_licenses(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        p = self.licenses_path()
        if not os.path.exists(p):
            QMessageBox.information(self, tr("Lizenzen"), tr("Passermark steht unter der GPL-3.0 (oder später)."))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(p))

    def _open_presets_dir(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        from .. import presets

        d = presets.root_dir()
        os.makedirs(d, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(d))

    # ---------------- edit mode (text and layers) ---------------- #

    # ---------------- rulers and measuring ---------------- #

    # ---------------- soft proof ---------------- #

    # ---------------- colour ---------------- #

    # ---------------- colour pipette ---------------- #

    # ---------------- Preflight (document check) ---------------- #

    @property
    def session(self):
        """The print session shared by all windows."""
        return self.ctl.session

    # ================================================================ #
    # thumbnails / display
    # ================================================================ #
    def rotate_view(self, delta: int):
        """Rotate the view – the thumbnails in the sidebar rotate along (the document stays unchanged)."""
        self.view.rotate(delta)
        if self.doc is not None:
            self._rebuild_thumbs()

    def _view_rot(self) -> int:
        r = getattr(self.view, "rotation", 0)
        return r % 360 if isinstance(r, int) else 0

    # ---------------- sidebar: width, arrangement, preview size ---------------- #
    @staticmethod
    def _dock_scroll(w):
        """Put a panel into a scroll area: the tabs on the left share one width – without this
        the widest panel (check/edit) forces its minimum width on "Seiten" too.
        """
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.Shape.NoFrame)
        sc.setWidget(w)
        # panels wrap (common.responsive) – scroll horizontally only when there is no other way
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        return sc

    def _dock_vis(self, d, vis):
        """Every tab on the left remembers its own width (pages narrow, check wider …)."""
        shown = self.__dict__.setdefault("_dock_shown", set())
        if not vis:
            if d in shown:  # remember only real, visible widths
                shown.discard(d)
                self._dock_widths[d] = d.width()
            return
        shown.add(d)
        want = self._dock_widths.get(d)
        if want is None and d is not self._pages_dock:
            inner = d.widget().widget() if isinstance(d.widget(), QScrollArea) else d.widget()
            want = max(d.width(), inner.minimumSizeHint().width() + 4)
        if want and want != d.width():
            QTimer.singleShot(0, lambda: self.resizeDocks([d], [want], Qt.Orientation.Horizontal))

    def _thumb_panel(self):
        from .. import l10n

        st = l10n.load_settings()
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        bar = QHBoxLayout()
        bar.setContentsMargins(6, 3, 6, 3)
        bar.setSpacing(2)
        self.btn_thumb_col = QToolButton()
        self.btn_thumb_col.setIcon(svg_icon("single"))
        self.btn_thumb_col.setToolTip(tr("Eine Spalte – Vorschau füllt die Breite"))
        self.btn_thumb_grid = QToolButton()
        self.btn_thumb_grid.setIcon(svg_icon("grid"))
        self.btn_thumb_grid.setToolTip(tr("Raster – mehrere Seiten nebeneinander"))
        self.btn_thumb_minus = QToolButton()
        self.btn_thumb_minus.setIcon(svg_icon("zoom_out"))
        self.btn_thumb_minus.setToolTip(tr("Vorschau verkleinern (Strg + Mausrad)"))
        self.btn_thumb_plus = QToolButton()
        self.btn_thumb_plus.setIcon(svg_icon("zoom_in"))
        self.btn_thumb_plus.setToolTip(tr("Vorschau vergrößern (Strg + Mausrad)"))
        for b in (self.btn_thumb_col, self.btn_thumb_grid):
            b.setCheckable(True)
            b.setAutoRaise(True)
            bar.addWidget(b)
        bar.addStretch(1)
        for b in (self.btn_thumb_minus, self.btn_thumb_plus):
            b.setAutoRaise(True)
            bar.addWidget(b)
        self.btn_thumb_col.clicked.connect(lambda: self._set_thumb_grid(False))
        self.btn_thumb_grid.clicked.connect(lambda: self._set_thumb_grid(True))
        self.btn_thumb_minus.clicked.connect(lambda: self._thumb_zoom(-1))
        self.btn_thumb_plus.clicked.connect(lambda: self._thumb_zoom(1))
        v.addLayout(bar)
        v.addWidget(self.thumbs, 1)
        try:
            self.thumbs.tile = int(st.get("thumb_tile", 140))
        except (TypeError, ValueError):
            pass
        self._set_thumb_grid(bool(st.get("thumb_grid", False)), remember=False)
        return box

    def _set_thumb_grid(self, on: bool, remember: bool = True):
        self.btn_thumb_col.setChecked(not on)
        self.btn_thumb_grid.setChecked(on)
        if on and self.thumbs.grid_mode != on:
            self.thumbs.tile = min(self.thumbs.tile, max(ThumbList.TILE_MIN, self.thumbs.viewport().width() // 2))
        self.thumbs.set_grid(on)
        self._requeue_thumbs()
        if remember:
            self._save_thumb_settings()

    def _thumb_zoom(self, step: int):
        """Grid: change the tile size. One column: make the sidebar itself wider/narrower."""
        f = 1.15 if step > 0 else 1 / 1.15
        if self.thumbs.grid_mode:
            t = int(round(self.thumbs.tile * f))
            if t == self.thumbs.tile:
                t += 1 if step > 0 else -1
            self.thumbs.tile = max(ThumbList.TILE_MIN, min(ThumbList.TILE_MAX, t))
            self.thumbs.doItemsLayout()
            self._thumb_resize.start()
            self._save_thumb_settings()
        else:
            d = self._pages_dock
            if not d.isFloating():
                w = max(110, min(int(d.width() * f), max(200, self.width() - 300)))
                self.resizeDocks([d], [w], Qt.Orientation.Horizontal)
            else:
                d.resize(max(110, int(d.width() * f)), d.height())

    def _save_thumb_settings(self):
        from .. import l10n

        st = l10n.load_settings()
        if st.get("thumb_grid") == self.thumbs.grid_mode and st.get("thumb_tile") == self.thumbs.tile:
            return
        st["thumb_grid"] = self.thumbs.grid_mode
        st["thumb_tile"] = self.thumbs.tile
        try:
            l10n.save_settings(st)
        except OSError:
            pass

    def _rebuild_thumbs(self):
        self.thumbs.clear()
        rot = self._view_rot()
        for i in range(len(self.doc)):
            it = QListWidgetItem(str(i + 1))
            w, h = self.doc.get_page_size(i)
            if rot % 180:
                w, h = h, w
            it.setData(THUMB_ASPECT, h / w if w else 1.414)
            it.setToolTip(tr("Seite {0}: {1}").format(i + 1, page_size_text(w, h)))
            self.thumbs.addItem(it)
        self._requeue_thumbs()

    def _requeue_thumbs(self):
        if self.doc is None:
            return
        self.thumbs.doItemsLayout()
        # visible ones first, then the rest
        first = self.thumbs.indexAt(self.thumbs.viewport().rect().topLeft()).row()
        first = max(0, first)
        n = self.thumbs.count()
        self._thumb_queue = list(range(first, n)) + list(range(0, first))
        if self._thumb_src.usable():
            self._thumb_timer.stop()
            self._thumb_src.kick()
        else:
            self._thumb_timer.start()

    def _thumb_target(self, i):
        """(image width in the list, scale in device pixels) for thumbnail i."""
        dlg = self.thumbs.itemDelegate()
        it = self.thumbs.item(i)
        iw = dlg.image_rect(QRect(0, 0, self.thumbs.tile_width(), 10000), it.data(THUMB_ASPECT)).width()
        w, h = self.doc.get_page_size(i)
        rot = self._view_rot()
        return iw, iw / (h if rot % 180 else w) * self.devicePixelRatioF()

    def _thumb_from_master(self, i):
        """Page image of the preview is ready -> scale the thumbnail from it (no second rendering)."""
        if self.doc is None or not (0 <= i < self.thumbs.count()) or not (0 <= i < len(self.view.pages)):
            return
        w = self.view.pages[i]
        if w.master is None or w.mstale or w.mkey is None or w.mkey[1] != self._view_rot():
            return
        it = self.thumbs.item(i)
        iw, _sc = self._thumb_target(i)
        dpr = self.devicePixelRatioF()
        tw = max(1, round(iw * dpr))
        img = w.master.scaledToWidth(tw, Qt.TransformationMode.SmoothTransformation)
        pm = QPixmap.fromImage(img)
        pm.setDevicePixelRatio(dpr)
        it.setData(THUMB_PIX, pm)
        it.setData(THUMB_W, iw)

    def _render_thumbs(self):
        if not self._thumb_queue or self.doc is None:
            self._thumb_timer.stop()
            return
        dlg = self.thumbs.itemDelegate()
        vw = self.thumbs.tile_width()
        dpr = self.devicePixelRatioF()
        for _ in range(3):
            if not self._thumb_queue:
                break
            i = self._thumb_queue.pop(0)
            if i >= len(self.doc) or i >= self.thumbs.count():
                continue
            it = self.thumbs.item(i)
            iw = dlg.image_rect(QRect(0, 0, vw, 10000), it.data(THUMB_ASPECT)).width()
            if it.data(THUMB_W) == iw and it.data(THUMB_PIX) is not None:
                continue
            w, h = self.doc.get_page_size(i)
            rot = self._view_rot()
            page = self.doc[i]
            pm = render_pixmap(page, iw / (h if rot % 180 else w), rot, dpr)
            page.close()
            it.setData(THUMB_PIX, pm)
            it.setData(THUMB_W, iw)

    def _page_changed(self, i):
        if self.doc is None:
            self.lbl_size.setText("")
            return
        self.page_edit.set_current(i)
        if len(self.thumbs.selectedItems()) <= 1 and 0 <= i < self.thumbs.count():
            self.thumbs.blockSignals(True)
            self.thumbs.setCurrentRow(i)
            self.thumbs.blockSignals(False)
            self.thumbs.scrollToItem(self.thumbs.item(i))
        w, h = self.doc.get_page_size(i)
        txt = tr("Seite {0}/{1}   ·   {2}").format(i + 1, len(self.doc), page_size_text(w, h))
        try:
            ti = self.view.trim_info(i)  # without loading the page in the program
        except Exception:
            ti = None
        if ti:
            txt += "   ·   " + tr("Endformat {0:.1f} × {1:.1f} mm, Anschnitt {2:.1f} mm").format(*ti)
        self.lbl_size.setText(txt)

    def _zoom_changed(self, z):
        if self.view.mode == "fixed":
            self.zoom_combo.setEditText(f"{z * 100:.0f} %")
        else:
            self.zoom_combo.setCurrentIndex(0 if self.view.mode == "width" else 1)

    def _zoom_combo_activated(self, idx):
        d = self.zoom_combo.itemData(idx)
        if d in ("width", "page"):
            self.view.set_zoom(d)
        elif d is not None:
            self.view.set_zoom("fixed", float(d))

    def _zoom_text_entered(self):
        t = self.zoom_combo.currentText().replace("%", "").replace(",", ".").strip()
        try:
            self.view.set_zoom("fixed", float(t) / 100.0)
        except ValueError:
            pass

    def _step_zoom(self, d):
        self.view.step_zoom(1.2 if d > 0 else 1 / 1.2)

    # ---------------- Background jobs (separate process) ---------------- #

    def closeEvent(self, e):
        self._stop_jobs()
        self._pf_stop()
        if self.doc is not None and self.modified:
            r = QMessageBox.question(
                self,
                tr("Ungespeicherte Änderungen"),
                tr("Änderungen an „{0}“ speichern?").format(self.display_name),
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
            )
            if r == QMessageBox.StandardButton.Cancel or (r == QMessageBox.StandardButton.Save and not self.save()):
                e.ignore()
                return
        # The print settings of the session stay until the last window – then they expire.
        try:
            self.view._timer.stop()
            self.view.release_render()  # close the document in the render process
            self._thumb_src.release()
            self.view.doc = None  # the view must no longer touch the document that is about to be closed
        except Exception:
            pass
        if self.doc is not None:
            self.doc.close()
            self.doc = None
        super().closeEvent(e)
        host = getattr(self, "_host", None)
        if host is not None:
            host.tab_closed()
