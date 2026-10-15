# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Sidebar "Edit": text rows (text, font, size) and layers (on/off, remove, replace,
scale/move). Selection via the list or by clicking on the page.
"""
from __future__ import annotations

import io
import os
import traceback

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMessageBox, QPushButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from .. import editing, preflight
from ..l10n import tr
from . import theme

MM = 72.0 / 25.4
SEL_TEXT = "#ff8a00"
SEL_LAYER = "#00a8ff"


def _err(parent, e):
    box = QMessageBox(QMessageBox.Icon.Critical, tr("Fehler"), str(e) or type(e).__name__, parent=parent)
    box.setDetailedText(traceback.format_exc())
    box.exec()


class EditPanel(QWidget):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.lines: list[editing.TextLine] = []
        self.objects: list = []
        self.lmap: editing.LayerMap | None = None
        self.lmap_key = None
        self.layers = []
        self.undo: list[bytes] = []
        self._cycle = []
        self._dstate = None
        self.sel_box = None          # Auswahlrahmen (Seitenkoordinaten)
        self._loaded = None          # (page, tab) for which the lists are filled
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)
        hint = QLabel(tr("Bearbeiten-Modus: auf der Seite klicken wählt eine Textzeile bzw. Ebene aus."))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {theme.MUTED};")
        v.addWidget(hint)
        self.tabs = QTabWidget()
        v.addWidget(self.tabs, 1)
        self.tabs.currentChanged.connect(lambda _i: self.refresh())

        # ---- Text ----
        w = QWidget()
        lv = QVBoxLayout(w)
        self.lst_text = QListWidget()
        self.lst_text.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.lst_text.itemSelectionChanged.connect(self._text_selection)
        lv.addWidget(self.lst_text, 1)
        f = QFormLayout()
        self.ed_text = QLineEdit()
        f.addRow(tr("Text:"), self.ed_text)
        row = QHBoxLayout()
        self.cmb_font = QComboBox()
        self.cmb_font.addItem(tr("Originalschrift"), None)
        for n in editing.STANDARD_FONTS:
            self.cmb_font.addItem(n, ("std", n))
        self.cmb_font.addItem(tr("Schriftdatei …"), "__file__")
        self.cmb_font.activated.connect(self._font_activated)
        row.addWidget(self.cmb_font, 1)
        self.spn_size = QDoubleSpinBox()
        self.spn_size.setRange(1, 500)
        self.spn_size.setDecimals(1)
        self.spn_size.setSuffix(" pt")
        row.addWidget(self.spn_size)
        f.addRow(tr("Schrift:"), row)
        lv.addLayout(f)
        row = QHBoxLayout()
        b = QPushButton(tr("Übernehmen"))
        b.clicked.connect(self._text_apply)
        row.addWidget(b)
        b = QPushButton(tr("Zeile löschen"))
        b.clicked.connect(self._text_delete)
        row.addWidget(b)
        b = QPushButton(tr("Farbe …"))
        b.setToolTip(tr("Farbe der gewählten Zeilen ändern (CMYK oder RGB)"))
        b.clicked.connect(self._text_color)
        row.addWidget(b)
        lv.addLayout(row)
        row = QHBoxLayout()
        for text, tip, fn in ((tr("Eins nach vorn"), tr("In der Zeichenreihenfolge eine Position nach vorn"), self._text_z_up),
                              (tr("Eins nach hinten"), tr("In der Zeichenreihenfolge eine Position nach hinten"), self._text_z_down),
                              (tr("Ganz nach vorn"), tr("Vor alle anderen Objekte legen"), self._text_z_front),
                              (tr("Ganz nach hinten"), tr("Hinter alle anderen Objekte legen"), self._text_z_back)):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            row.addWidget(b)
        lv.addLayout(row)
        self.tabs.addTab(w, tr("Text"))

        # ---- Objekte ----
        w = QWidget()
        lv = QVBoxLayout(w)
        self.cmb_objkind = QComboBox()
        self.cmb_objkind.setToolTip(tr("Liste nach Art filtern – Klicks auf die Seite wählen nur diese Art"))
        self.cmb_objkind.currentIndexChanged.connect(self._object_filter)
        lv.addWidget(self.cmb_objkind)
        self.lst_objects = QListWidget()
        self.lst_objects.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.lst_objects.itemSelectionChanged.connect(self._object_selection)
        lv.addWidget(self.lst_objects, 1)
        self.lbl_object = QLabel()
        self.lbl_object.setWordWrap(True)
        self.lbl_object.setStyleSheet(f"color: {theme.MUTED};")
        lv.addWidget(self.lbl_object)
        grid = QHBoxLayout()
        for text, fn in ((tr("Skalieren / Verschieben …"), self._object_transform),
                         (tr("Objekt löschen"), self._object_delete),
                         (tr("Farbe …"), self._object_color)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            grid.addWidget(b)
        lv.addLayout(grid)
        grid = QHBoxLayout()
        for text, tip, fn in ((tr("Eins nach vorn"), tr("In der Zeichenreihenfolge eine Position nach vorn"), self._object_z_up),
                              (tr("Eins nach hinten"), tr("In der Zeichenreihenfolge eine Position nach hinten"), self._object_z_down),
                              (tr("Ganz nach vorn"), tr("Vor alle anderen Objekte legen"), self._object_z_front),
                              (tr("Ganz nach hinten"), tr("Hinter alle anderen Objekte legen"), self._object_z_back)):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            grid.addWidget(b)
        lv.addLayout(grid)
        self.tabs.addTab(w, tr("Objekte"))

        # ---- Ebenen ----
        w = QWidget()
        lv = QVBoxLayout(w)
        self.lst_layers = QListWidget()
        self.lst_layers.currentRowChanged.connect(self._layer_selected)
        lv.addWidget(self.lst_layers, 1)
        self.lbl_layer = QLabel()
        self.lbl_layer.setWordWrap(True)
        self.lbl_layer.setStyleSheet(f"color: {theme.MUTED};")
        lv.addWidget(self.lbl_layer)
        grid = QHBoxLayout()
        for text, fn in ((tr("Ein-/Ausblenden"), self._layer_toggle), (tr("Entfernen"), self._layer_remove)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            grid.addWidget(b)
        lv.addLayout(grid)
        grid = QHBoxLayout()
        for text, fn in ((tr("Skalieren / Verschieben …"), self._layer_transform), (tr("Ersetzen …"), self._layer_replace)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            grid.addWidget(b)
        lv.addLayout(grid)
        grid = QHBoxLayout()
        for text, tip, fn in ((tr("Eins nach vorn"), tr("In der Zeichenreihenfolge eine Position nach vorn"), self._layer_z_up),
                              (tr("Eins nach hinten"), tr("In der Zeichenreihenfolge eine Position nach hinten"), self._layer_z_down),
                              (tr("Ganz nach vorn"), tr("Vor alle anderen Objekte legen"), self._layer_z_front),
                              (tr("Ganz nach hinten"), tr("Hinter alle anderen Objekte legen"), self._layer_z_back)):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            grid.addWidget(b)
        lv.addLayout(grid)
        self.tabs.addTab(w, tr("Ebenen"))

        self._tab_names = [tr("Text"), tr("Objekte"), tr("Ebenen")]
        self._last_color = ("cmyk", (0.0, 0.0, 0.0, 1.0))
        self.btn_undo = QPushButton(tr("Rückgängig"))
        self.btn_undo.clicked.connect(self._undo)
        self.btn_undo.setEnabled(False)
        v.addWidget(self.btn_undo)

    # ------------------------------------------------------------------ #
    @property
    def page(self) -> int:
        return self.win.view.current

    def refresh(self):
        """Rebuild the lists for the current page."""
        if self.win.doc is None or not self.win.a_edit.isChecked():
            return
        if self._loaded is None or self._loaded[0] != self.page:     # andere Seite: alte Anzahlen weg
            for i, n in enumerate(self._tab_names):
                self.tabs.setTabText(i, n)
        try:
            if self.tabs.currentIndex() == 0:
                self._fill_text()
            elif self.tabs.currentIndex() == 1:
                self._fill_objects()
            else:
                self._fill_layers()
            self._loaded = (self.page, self.tabs.currentIndex())
        except Exception as e:
            _err(self, e)
        self.sel_box = None
        self._overlay()

    def _snapshot(self):
        self.undo.append(self.win._doc_bytes())
        del self.undo[:-20]
        self.btn_undo.setEnabled(True)

    def _replace_doc(self, data: bytes):
        import pypdfium2 as pdfium
        page = self.page
        self.win._set_doc(pdfium.PdfDocument(data), self.win.path, self.win.display_name, True, keep_page=page)
        self.lmap_key = None
        self.refresh()

    def _undo(self):
        if self.undo:
            self._replace_doc(self.undo.pop())
            self.btn_undo.setEnabled(bool(self.undo))

    def _overlay(self, rects=None, preview=None):
        """Auswahlrahmen mit Eckgriffen; optional gestrichelte Vorschau (beim Ziehen)."""
        view = self.win.view
        items = list(rects or [])
        if items:
            x0, y0, x1, y1, c = items[0][:5]
            self.sel_box = (x0, y0, x1, y1)
            h = self._handle_pt()
            for cx, cy in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
                items.append((cx - h, cy - h, cx + h, cy + h, c, "handle"))
        else:
            self.sel_box = None
        if preview is not None:
            items.append((*preview, items[0][4] if items else SEL_LAYER, "dash"))
        view.overlay = {self.page: items} if items else {}
        if 0 <= self.page < len(view.pages):
            view.pages[self.page].update()

    def _handle_pt(self) -> float:
        w = self.win.view.pages[self.page] if 0 <= self.page < len(self.win.view.pages) else None
        return self.win.view._tol_pt(w) * 0.55 if w is not None else 3.0

    # ---------------- Mouse: select, move, scale ---------------- #
    def _ensure_loaded(self, page):
        if self._loaded != (page, self.tabs.currentIndex()):
            self.refresh()

    @staticmethod
    def _corner_hit(box, x, y, tol):
        x0, y0, x1, y1 = box
        for cx, cy, ax, ay in ((x0, y0, x1, y1), (x1, y0, x0, y1), (x0, y1, x1, y0), (x1, y1, x0, y0)):
            if abs(x - cx) <= tol and abs(y - cy) <= tol:
                return (cx, cy), (ax, ay)
        return None

    @staticmethod
    def _inside(box, x, y, tol):
        return box[0] - tol <= x <= box[2] + tol and box[1] - tol <= y <= box[3] + tol

    def cursor(self, page, x, y, tol):
        if page != self.page or self.sel_box is None:
            return None
        if self._corner_hit(self.sel_box, x, y, tol):
            return "scale"
        if self._inside(self.sel_box, x, y, tol):
            return "move"
        return None

    def press(self, page, x, y, tol, ctrl=False):
        if page != self.page:
            return
        self._ensure_loaded(page)
        self._dstate = None
        box = self.sel_box
        if box is not None:
            hit = self._corner_hit(box, x, y, tol)
            if hit:
                self._dstate = {"kind": "scale", "box": box, "corner": hit[0], "anchor": hit[1], "start": (x, y)}
                return
            if self._inside(box, x, y, tol) and ctrl:
                cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
                self._dstate = {"kind": "scale_radial", "box": box, "anchor": (cx, cy), "start": (x, y)}
                return
            if self._inside(box, x, y, tol):
                self._dstate = {"kind": "move", "box": box, "start": (x, y)}
                return
        self.page_click(page, x, y, ctrl)          # reselect (Strg = zur Auswahl hinzufügen) …
        box = self.sel_box
        if box is not None and self._inside(box, x, y, tol):
            self._dstate = {"kind": "move", "box": box, "start": (x, y)}   # … und gleich greifen

    def _preview(self, x, y, d=None):
        import math
        d = d or self._dstate
        x0, y0, x1, y1 = d["box"]
        if d["kind"] == "scale_radial":
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            r0 = math.hypot(d["start"][0] - cx, d["start"][1] - cy)
            r1 = math.hypot(x - cx, y - cy)
            s = max(0.05, r1 / r0) if r0 > 1e-3 else 1.0
            w, h = (x1 - x0) / 2 * s, (y1 - y0) / 2 * s
            return s, 0.0, 0.0, (cx - w, cy - h, cx + w, cy + h)
        if d["kind"] == "move":
            dx, dy = x - d["start"][0], y - d["start"][1]
            return 1.0, dx, dy, (x0 + dx, y0 + dy, x1 + dx, y1 + dy)
        ax, ay = d["anchor"]
        cx, cy = d["corner"]
        vx, vy = cx - ax, cy - ay
        s = max(0.05, ((x - ax) * vx + (y - ay) * vy) / max(1e-6, vx * vx + vy * vy))
        nb = (ax + (x0 - ax) * s, ay + (y0 - ay) * s, ax + (x1 - ax) * s, ay + (y1 - ay) * s)
        return s, 0.0, 0.0, (min(nb[0], nb[2]), min(nb[1], nb[3]), max(nb[0], nb[2]), max(nb[1], nb[3]))

    def drag(self, page, x, y):
        """Mouse moved with the button held: dashed preview of the new position."""
        if self._dstate is None or page != self.page or self.sel_box is None:
            return
        s, _dx, _dy, nb = self._preview(x, y)
        col = SEL_TEXT if self.tabs.currentIndex() == 0 else SEL_LAYER
        self._overlay([(*self._dstate["box"], col)], preview=nb)
        if self._dstate["kind"] in ("scale", "scale_radial"):
            if self.tabs.currentIndex() == 0 and self.lines:
                L = self.lines[self.lst_text.currentRow()] if 0 <= self.lst_text.currentRow() < len(self.lines) else None
                if L is not None:
                    self.win.statusBar().showMessage(tr("Neue Größe: {0:.1f} pt").format(L.size * s), 2000)
            elif self.tabs.currentIndex() == 1 and self.objects:
                O = self.objects[self.lst_objects.currentRow()] if 0 <= self.lst_objects.currentRow() < len(self.objects) else None
                if O is not None:
                    self.win.statusBar().showMessage(tr("Neue Größe: {0:.1f} × {1:.1f} mm").format(
                        (O.bbox[2] - O.bbox[0]) / MM * s, (O.bbox[3] - O.bbox[1]) / MM * s), 2000)

    def release(self, page, x, y):
        """Release: apply move/scale (layer or text row), with undo."""
        d, self._dstate = self._dstate, None
        if d is None or page != self.page:
            return
        s, dx, dy, nb = self._preview(x, y, d)
        if abs(s - 1) < 0.005 and abs(dx) < 0.5 and abs(dy) < 0.5:
            self._overlay([(*d["box"], SEL_TEXT if self.tabs.currentIndex() == 0 else SEL_LAYER)])
            return                                   # nur geklickt, nicht gezogen
        origin = d.get("anchor", (0.0, 0.0))
        try:
            if self.tabs.currentIndex() == 0:
                lines = self._selected_lines()
                if not lines:
                    return

                def run(data):
                    # preferred: enclose only the text blocks (otherwise the page stays unchanged)
                    new, pending = data, []
                    for L in lines:
                        b = editing.transform_line_blocks(new, self.page, L, s, dx, dy, origin)
                        if b is not None:
                            new = b
                        else:
                            pending.append(L)
                    if pending:                    # pdfium-Rest Durchlauf (einmal speichern)
                        new = self._pdfium_edit(new, self.page,
                                                lambda d: editing.transform_lines_bulk(d, self.page, pending, s, dx, dy, origin))[0]
                    return new
                if self._text_edit(run, [L.bbox for L in lines] + [nb]):
                    self._reselect_text(nb)
            elif self.tabs.currentIndex() == 1:
                objs = self._selected_objects()
                if not objs:
                    return

                def run_obj(data):
                    return self._pdfium_edit(data, self.page,
                                             lambda d: editing.transform_objects_bulk(d, self.page, objs, s, dx, dy, origin))[0]
                if self._text_edit(run_obj, [O.bbox for O in objs] + [nb]):
                    self._reselect_object(nb)
            else:
                L = self._layer_key()
                if L is None:
                    return
                data = self.win._doc_bytes()
                new = editing.transform_layer(data, L.key, s, dx, dy, origin, [self.page])
                self.undo.append(data)
                del self.undo[:-20]
                self.btn_undo.setEnabled(True)
                self._replace_doc(new)
                self._reselect_layer(L.key)
        except Exception as e:
            _err(self, e)

    def _reselect_text(self, box):
        """After reloading, select the moved row again (the one nearest the new position)."""
        if not self.lines:
            return
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        best = min(self.lines, key=lambda L: abs((L.bbox[0] + L.bbox[2]) / 2 - cx) + abs((L.bbox[1] + L.bbox[3]) / 2 - cy))
        if self.lst_text.currentRow() == best.index:
            self._text_selected(best.index)          # gleiche Zeile: kein Signal -> direkt anwählen
        else:
            self.lst_text.setCurrentRow(best.index)

    def _reselect_object(self, box):
        """After reloading, select the moved object again (nearest to the new position)."""
        if not self.objects:
            return
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        best = min(self.objects, key=lambda O: abs((O.bbox[0] + O.bbox[2]) / 2 - cx)
                   + abs((O.bbox[1] + O.bbox[3]) / 2 - cy))
        if self.lst_objects.currentRow() == best.index:
            self._object_selected(best.index)        # gleiche Zeile: kein Signal -> direkt anwählen
        else:
            self.lst_objects.setCurrentRow(best.index)

    def _reselect_layer(self, key):
        for i, L in enumerate(self.layers):
            if L.key == key:
                self.lst_layers.setCurrentRow(i)
                self._layer_selected(i)
                break

    # ---------------- Auswahl (Mehrfach, Bild + Liste synchron) ---------------- #
    def _selected_lines(self) -> list:
        return [self.lines[i.row()] for i in self.lst_text.selectedIndexes()
                if 0 <= i.row() < len(self.lines)]

    def _selected_objects(self) -> list:
        return [self.objects[i.row()] for i in self.lst_objects.selectedIndexes()
                if 0 <= i.row() < len(self.objects)]

    @staticmethod
    def _union(boxes) -> tuple:
        return (min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes))

    def _text_selection(self):
        """Mehrfachauswahl Text: Rahmen um alle gewählten Zeilen (Union = Griffrahmen)."""
        sel = self._selected_lines()
        if not sel:
            self.sel_box = None
            self._overlay()
            return
        boxes = [(L.bbox[0] - 1, L.bbox[1] - 1, L.bbox[2] + 1, L.bbox[3] + 1, SEL_TEXT) for L in sel]
        u = self._union([b[:4] for b in boxes])
        self._overlay([(u[0], u[1], u[2], u[3], SEL_TEXT)] + boxes)
        row = self.lst_text.currentRow()
        if 0 <= row < len(sel) and sel[0].index == row or any(L.index == row for L in sel):
            L = next(L for L in sel if L.index == row)
            self.ed_text.setText(L.text)
            self.spn_size.setValue(L.size)
        multi = len(sel) > 1
        self.ed_text.setEnabled(not multi)
        self.ed_text.setToolTip(tr("Bei mehreren gewählten Zeilen werden nur Schrift und Größe übernommen.")
                                if multi else "")

    def _object_selection(self):
        """Mehrfachauswahl Objekte: Rahmen um alle gewählten Objekte (Union = Griffrahmen)."""
        sel = self._selected_objects()
        if not sel:
            self.sel_box = None
            self._overlay()
            if not self.objects:
                self.lbl_object.setText(tr("Keine Vektor- oder Bildobjekte auf dieser Seite."))
            return
        boxes = [(O.bbox[0] - 1, O.bbox[1] - 1, O.bbox[2] + 1, O.bbox[3] + 1, SEL_TEXT) for O in sel]
        u = self._union([b[:4] for b in boxes])
        self._overlay([(u[0], u[1], u[2], u[3], SEL_TEXT)] + boxes)
        row = self.lst_objects.currentRow()
        if any(O.index == row for O in sel):
            O = next(O for O in sel if O.index == row)
            self.lbl_object.setText(tr("Ausdehnung: {0:.1f} × {1:.1f} mm").format(
                (O.bbox[2] - O.bbox[0]) / MM, (O.bbox[3] - O.bbox[1]) / MM))

    # ---------------- Z-Ordnung ---------------- #
    def _zorder(self, items, where, layer_key=None) -> None:
        """Zeichenreihenfolge ändern (Objekte/Zeilen oder Ebene) – ohne Neuaufbau (pikepdf)."""
        data = self.win._doc_bytes()
        try:
            if layer_key is not None:
                new = editing.reorder_layer_blocks(data, self.page, layer_key, where)
            else:
                new = editing.reorder_objects(data, self.page, items, where)
        except Exception as e:
            _err(self, e)
            return
        if new is None:
            QMessageBox.information(self, tr("Bearbeiten"),
                                    tr("Für diese Auswahl lässt sich die Zeichenreihenfolge nicht sicher "
                                       "umordnen (Struktur der Seite nicht erkannt)."))
            return
        if new == data:
            return                                    # schon an der Position
        self.undo.append(data)
        del self.undo[:-20]
        self.btn_undo.setEnabled(True)
        self._replace_doc(new)

    def _text_z_up(self):
        sel = self._selected_lines()
        if sel:
            self._zorder(sel, "up")

    def _text_z_down(self):
        sel = self._selected_lines()
        if sel:
            self._zorder(sel, "down")

    def _text_z_front(self):
        sel = self._selected_lines()
        if sel:
            self._zorder(sel, "front")

    def _text_z_back(self):
        sel = self._selected_lines()
        if sel:
            self._zorder(sel, "back")

    def _object_z_up(self):
        sel = self._selected_objects()
        if sel:
            self._zorder(sel, "up")

    def _object_z_down(self):
        sel = self._selected_objects()
        if sel:
            self._zorder(sel, "down")

    def _object_z_front(self):
        sel = self._selected_objects()
        if sel:
            self._zorder(sel, "front")

    def _object_z_back(self):
        sel = self._selected_objects()
        if sel:
            self._zorder(sel, "back")

    def _layer_z_up(self):
        L = self._layer_key()
        if L is not None:
            self._zorder(None, "up", layer_key=L.key)

    def _layer_z_down(self):
        L = self._layer_key()
        if L is not None:
            self._zorder(None, "down", layer_key=L.key)

    def _layer_z_front(self):
        L = self._layer_key()
        if L is not None:
            self._zorder(None, "front", layer_key=L.key)

    def _layer_z_back(self):
        L = self._layer_key()
        if L is not None:
            self._zorder(None, "back", layer_key=L.key)

    # ---------------- Text ---------------- #
    def _fill_text(self):
        cur = self.lst_text.currentRow()
        self.lines = editing.text_lines(self.win.doc, self.page, include_undecodable=True)
        self.lst_text.blockSignals(True)
        self.lst_text.clear()
        for L in self.lines:
            shown = L.text[:60] if L.text.strip() and not L.no_text else "(" + tr("ohne Textinhalt") + ")"
            it = QListWidgetItem(f"{shown}\n{L.font.split('+')[-1]} · {L.size:.1f} pt" +
                                 (" · " + tr("Ebene") if L.in_layer else "") +
                                 (" · " + tr("Pfadtext") if L.path_center else ""))
            self.lst_text.addItem(it)
        self.lst_text.blockSignals(False)
        self.tabs.setTabText(0, tr("Text ({0})").format(len(self.lines)))
        if 0 <= cur < len(self.lines):
            self.lst_text.setCurrentRow(cur)

    def _text_selected(self, row):
        if not (0 <= row < len(self.lines)):
            return
        L = self.lines[row]
        self.ed_text.setText(L.text)
        self.spn_size.setValue(L.size)
        self.cmb_font.setCurrentIndex(0)
        x0, y0, x1, y1 = L.bbox
        self._overlay([(x0 - 1, y0 - 1, x1 + 1, y1 + 1, SEL_TEXT)])

    def _font_activated(self, idx):
        if self.cmb_font.itemData(idx) == "__file__":
            p, _ = QFileDialog.getOpenFileName(self, tr("Schriftdatei wählen"), preflight.user_font_dir(),
                                               tr("Schriften (*.ttf *.otf *.TTF *.OTF)"))
            if p:
                self.cmb_font.insertItem(idx, os.path.basename(p), ("file", p))
                self.cmb_font.setCurrentIndex(idx)
            else:
                self.cmb_font.setCurrentIndex(0)

    def _sel_or_current_lines(self) -> list:
        sel = self._selected_lines()
        if not sel and 0 <= self.lst_text.currentRow() < len(self.lines):
            sel = [self.lines[self.lst_text.currentRow()]]
        return sorted(sel, key=lambda L: L.index)

    def _sel_or_current_objects(self) -> list:
        sel = self._selected_objects()
        if not sel and 0 <= self.lst_objects.currentRow() < len(self.objects):
            sel = [self.objects[self.lst_objects.currentRow()]]
        return sorted(sel, key=lambda O: O.index)

    def _text_apply(self):
        sel = self._sel_or_current_lines()
        if not sel:
            return
        font = self.cmb_font.currentData()
        size = self.spn_size.value()
        holder = {"notes": []}
        if len(sel) == 1:
            L = sel[0]
            size_arg = size if (abs(size - L.size) > 0.01 or font is not None) else None
            text = self.ed_text.text()

            def run(data):
                new, notes = editing.edit_line_bytes(data, self.page, L, text, font, size_arg)
                holder["notes"] = notes
                return new
        else:
            # mehrere Zeilen: Schrift/Größe für alle; nach jeder Änderung die nächste Zeile neu suchen
            # (Objektnummern können sich durch die Änderung verschieben)
            def run(data):
                import pypdfium2 as pdfium
                cur = data
                for L0 in sel:
                    d = pdfium.PdfDocument(cur)
                    try:
                        lines = editing.text_lines(d, self.page, include_undecodable=True)
                    finally:
                        d.close()
                    L = _match_line(L0, lines)
                    if L is None:
                        raise ValueError(tr("Zeile „{0}“ nach der Änderung nicht mehr gefunden – "
                                            "Änderung abgebrochen.").format(L0.text[:40]))
                    size_arg = size if (abs(size - L.size) > 0.01 or font is not None) else None
                    cur, notes = editing.edit_line_bytes(cur, self.page, L, L.text, font, size_arg)
                    for n in notes:
                        if n not in holder["notes"]:
                            holder["notes"].append(n)
                return cur
        try:
            if self._text_edit(run, [self._wide_box(L) for L in sel]):
                if holder.get("notes"):
                    QMessageBox.information(self, tr("Hinweis"), "\n\n".join(holder["notes"]))
        except Exception as e:
            _err(self, e)

    def _text_delete(self):
        sel = self._sel_or_current_lines()
        if not sel:
            return
        try:
            if self._text_edit(lambda data: editing.remove_lines_ops(data, self.page, sel), [L.bbox for L in sel]):
                self._overlay(None)
        except Exception as e:
            _err(self, e)

    def _text_color(self):
        sel = self._sel_or_current_lines()
        if not sel:
            QMessageBox.information(self, tr("Text"), tr("Bitte zuerst eine Zeile wählen (Liste oder Klick auf die Seite)."))
            return
        self._recolor(sel, [], tr("{0} Zeile(n)").format(len(sel)), with_parts=False)

    def _object_color(self):
        sel = self._sel_or_current_objects()
        if not sel:
            QMessageBox.information(self, tr("Objekte"), tr("Bitte zuerst ein Objekt wählen (Liste oder Klick auf die Seite)."))
            return
        paths = [O for O in sel if O.kind == "path"]
        if not paths:
            QMessageBox.information(self, tr("Objekte"), tr("Bilder lassen sich nicht umfärben – bitte Vektorobjekte wählen."))
            return
        self._recolor([], paths, tr("{0} Vektorobjekt(e)").format(len(paths)), with_parts=True,
                      skipped=len(sel) - len(paths))

    def _recolor(self, lines, objs, what, with_parts, skipped=0):
        dlg = _ColorDialog(self, what, self._last_color, with_parts)
        if not dlg.exec():
            return
        color, fill, stroke = dlg.values()
        if not (fill or stroke):
            return
        self._last_color = color
        boxes = [L.bbox for L in lines] + [O.bbox for O in objs]
        holder = {}

        def run(data):
            new = editing.recolor(data, self.page, color, lines=lines, objs=objs, fill=fill, stroke=stroke)
            holder["unsafe"] = new is None
            return new
        try:
            self._text_edit(run, [(b[0] - 2, b[1] - 2, b[2] + 2, b[3] + 2) for b in boxes])
            if holder.get("unsafe"):
                QMessageBox.information(self, tr("Farbe"), tr("Auf dieser Seite lässt sich die Farbe nicht sicher "
                                                              "zuordnen – das Dokument bleibt unverändert."))
            elif skipped:
                QMessageBox.information(self, tr("Farbe"), tr("{0} Bild(er) in der Auswahl wurden nicht umgefärbt.").format(skipped))
        except Exception as e:
            _err(self, e)

    def _text_edit(self, fn, ignore_boxes, notes=None) -> bool:
        """fn(data) -> new data. Runs on a copy, is verified, then adopted."""
        self.win.view._close_textpages()                 # no open pages of the view during the change
        data = self.win._doc_bytes()
        new = fn(data)
        if new is None or new == data:
            return False                                 # nichts geändert: kein Rückgängig-Schritt, nicht „geändert“
        err = editing.verify_edit(data, new, self.page, ignore_boxes)
        if err:
            from pypdfium2 import version as _v
            box = QMessageBox(QMessageBox.Icon.Warning, tr("Änderung nicht übernommen"),
                              err + "\n\n" + tr("Das Dokument bleibt unverändert. Bitte die Datei an den Entwickler "
                                                "schicken, damit der Fall gelöst werden kann."), parent=self)
            box.setDetailedText(f"pypdfium2 {getattr(_v, 'PYPDFIUM_INFO', '?')} · pdfium {getattr(_v, 'PDFIUM_INFO', '?')}\n"
                                f"Seite {self.page + 1}\n{err}")
            box.exec()
            return False
        self.undo.append(data)
        del self.undo[:-20]
        self.btn_undo.setEnabled(True)
        self._replace_doc(new)
        if notes:
            QMessageBox.information(self, tr("Hinweis"), "\n\n".join(notes))
        return True

    @staticmethod
    def _pdfium_edit(data, page, fn):
        """Apply a pdfium change to a freshly loaded copy -> (new data, hints)."""
        import pypdfium2 as pdfium
        d = pdfium.PdfDocument(data)
        try:
            notes = fn(d) or []
            buf = io.BytesIO()
            d.save(buf)
            return buf.getvalue(), notes
        finally:
            d.close()

    def _wide_box(self, L):
        """Area in which a changed row may vary (row height, full page width)."""
        pw = self.win.doc.get_page_size(self.page)[0]
        h = L.bbox[3] - L.bbox[1]
        size = self.spn_size.value() if hasattr(self, "spn_size") else L.size
        grow = max(0.0, (float(size) / max(L.size, 0.1) - 1.0)) * h     # a larger font may grow upward
        return (0, L.bbox[1] - 0.3 * h, pw, L.bbox[3] + 0.3 * h + grow)

    def _after_edit(self, notes):
        # reload the document (refresh the display), mark as changed
        self._replace_doc(self.win._doc_bytes())
        if notes:
            QMessageBox.information(self, tr("Hinweis"), "\n\n".join(notes))

    # ---------------- Objekte ---------------- #
    def _fill_objects(self):
        cur = self.lst_objects.currentRow()
        self.objects = editing.page_objects(self.win.doc, self.page)
        self.lst_objects.blockSignals(True)
        self.lst_objects.clear()
        for O in self.objects:
            w_mm = (O.bbox[2] - O.bbox[0]) / MM
            h_mm = (O.bbox[3] - O.bbox[1]) / MM
            self.lst_objects.addItem(QListWidgetItem(
                f"{O.text}\n{w_mm:.1f} × {h_mm:.1f} mm" + (" · " + tr("Ebene") if O.in_layer else "")))
        self.lst_objects.blockSignals(False)
        n_path = sum(1 for O in self.objects if O.kind == "path")
        n_img = len(self.objects) - n_path
        kind = self.cmb_objkind.currentData() or "all"
        self.cmb_objkind.blockSignals(True)
        self.cmb_objkind.clear()
        self.cmb_objkind.addItem(tr("Alle ({0})").format(len(self.objects)), "all")
        self.cmb_objkind.addItem(tr("Vektoren ({0})").format(n_path), "path")
        self.cmb_objkind.addItem(tr("Bilder ({0})").format(n_img), "image")
        self.cmb_objkind.setCurrentIndex(max(0, self.cmb_objkind.findData(kind)))
        self.cmb_objkind.blockSignals(False)
        self.tabs.setTabText(1, tr("Objekte ({0})").format(len(self.objects)))
        self._object_filter()
        if not self.objects:
            self.lbl_object.setText(tr("Keine Vektor- oder Bildobjekte auf dieser Seite."))
        if 0 <= cur < len(self.objects) and not self.lst_objects.isRowHidden(cur):
            self.lst_objects.setCurrentRow(cur)

    def _object_filter(self, *_):
        """Nur Vektoren / nur Bilder zeigen (Zeilen bleiben, werden ausgeblendet – Indizes stimmen weiter)."""
        kind = self.cmb_objkind.currentData() or "all"
        for O in self.objects:
            hide = kind != "all" and O.kind != kind
            self.lst_objects.setRowHidden(O.index, hide)
            if hide and self.lst_objects.item(O.index).isSelected():
                self.lst_objects.item(O.index).setSelected(False)

    def _object_selected(self, row):
        if not (0 <= row < len(self.objects)):
            return
        O = self.objects[row]
        self._overlay([(O.bbox[0] - 1, O.bbox[1] - 1, O.bbox[2] + 1, O.bbox[3] + 1, SEL_TEXT)])
        self.lbl_object.setText(tr("Ausdehnung: {0:.1f} × {1:.1f} mm").format(
            (O.bbox[2] - O.bbox[0]) / MM, (O.bbox[3] - O.bbox[1]) / MM))

    def _object_transform(self):
        sel = self._sel_or_current_objects()
        if not sel:
            QMessageBox.information(self, tr("Objekte"), tr("Bitte zuerst ein Objekt wählen (Liste oder Klick auf die Seite)."))
            return
        box = self._union([O.bbox for O in sel])
        name = sel[0].text if len(sel) == 1 else tr("{0} Objekte").format(len(sel))
        dlg = _TransformDialog(self, name, box, what=tr("Objekt"), with_pages=False)
        if not dlg.exec():
            return
        pb = self.win.doc.get_page_size(self.page)
        pb = (0.0, 0.0, pb[0], pb[1])
        scale, dx, dy, origin, _all = dlg.values(box, pb)
        moved = (box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy)
        try:
            if self._text_edit(lambda data: self._pdfium_edit(
                    data, self.page, lambda d: editing.transform_objects_bulk(d, self.page, sel, scale, dx, dy, origin))[0],
                    [O.bbox for O in sel] + [self._grow_box(box, scale), self._grow_box(moved, scale)]):
                self._reselect_object(self._grow_box(moved, scale) if len(sel) == 1 else moved)
        except Exception as e:
            _err(self, e)

    def _object_delete(self):
        sel = self._sel_or_current_objects()
        if not sel:
            QMessageBox.information(self, tr("Objekte"), tr("Bitte zuerst ein Objekt wählen (Liste oder Klick auf die Seite)."))
            return
        try:
            if self._text_edit(lambda data: self._pdfium_edit(
                    data, self.page, lambda d: editing.delete_objects(d, self.page, sel))[0], [O.bbox for O in sel]):
                self._overlay(None)
        except Exception as e:
            _err(self, e)

    @staticmethod
    def _grow_box(bbox, scale):
        s = max(1.0, float(scale))
        cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
        w, h = (bbox[2] - bbox[0]) * s, (bbox[3] - bbox[1]) * s
        return (cx - w, cy - h, cx + w, cy + h)

    # ---------------- Ebenen ---------------- #
    def _fill_layers(self):
        data = self.win._doc_bytes()
        rep = preflight.analyze(data, deep_layers=False)
        self.layers = rep.layers
        key = (len(data), hash(data[:4096]), hash(data[-4096:]), self.page)
        if key != self.lmap_key:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                self.lmap = editing.layer_map(data, self.page)
            finally:
                QApplication.restoreOverrideCursor()
            self.lmap_key = key
        cur = self.lst_layers.currentRow()
        self.lst_layers.blockSignals(True)
        self.lst_layers.clear()
        for L in self.layers:
            on = tr("sichtbar") if L.view_on else tr("ausgeblendet")
            here = tr("auf dieser Seite") if L.key in self.lmap.boxes else tr("nicht auf dieser Seite")
            self.lst_layers.addItem(QListWidgetItem(f"{'●' if L.view_on else '○'}  {L.name}\n{on} · {here}"))
        self.lst_layers.blockSignals(False)
        if not self.layers:
            self.lbl_layer.setText(tr("Das Dokument hat keine Ebenen."))
        if 0 <= cur < len(self.layers):
            self.lst_layers.setCurrentRow(cur)

    def _layer_selected(self, row):
        if not (0 <= row < len(self.layers)) or self.lmap is None:
            return
        L = self.layers[row]
        b = self.lmap.boxes.get(L.key)
        if b:
            pb = self.lmap.page_box
            out = 100 * (1 - _overlap(b, pb))
            self.lbl_layer.setText(tr("Ausdehnung: {0:.0f} × {1:.0f} mm").format((b[2] - b[0]) / MM, (b[3] - b[1]) / MM)
                                   + (tr(" · {0:.0f} % außerhalb der Seite").format(out) if out > 1 else ""))
            self._overlay([(b[0], b[1], b[2], b[3], SEL_LAYER)])
        else:
            self.lbl_layer.setText(tr("Kein Inhalt auf dieser Seite."))
            self._overlay(None)

    def _layer_key(self):
        row = self.lst_layers.currentRow()
        if not (0 <= row < len(self.layers)):
            QMessageBox.information(self, tr("Ebenen"), tr("Bitte zuerst eine Ebene wählen (Liste oder Klick auf die Seite)."))
            return None
        return self.layers[row]

    def _run_layer(self, fn):
        L = self._layer_key()
        if L is None:
            return
        try:
            data = self.win._doc_bytes()
            new = fn(data, L)
            if new is None:
                return
            self.undo.append(data)
            del self.undo[:-20]
            self.btn_undo.setEnabled(True)
            self._replace_doc(new)
        except Exception as e:
            _err(self, e)

    def _layer_toggle(self):
        self._run_layer(lambda d, L: editing.set_visible(d, L.key, not L.view_on))

    def _layer_remove(self):
        def fn(d, L):
            if QMessageBox.question(self, tr("Ebene entfernen"), tr("Ebene „{0}“ samt Inhalt entfernen?").format(L.name)) \
                    != QMessageBox.StandardButton.Yes:
                return None
            return preflight.remove_layers(d, {L.key})
        self._run_layer(fn)

    def _layer_transform(self):
        def fn(d, L):
            b = self.lmap.boxes.get(L.key) if self.lmap else None
            dlg = _TransformDialog(self, L.name, b)
            if not dlg.exec():
                return None
            scale, dx, dy, origin, all_pages = dlg.values(b, self.lmap.page_box if self.lmap else (0, 0, 0, 0))
            return editing.transform_layer(d, L.key, scale, dx, dy, origin, None if all_pages else [self.page])
        self._run_layer(fn)

    def _layer_replace(self):
        def fn(d, L):
            p, _ = QFileDialog.getOpenFileName(self, tr("Ersatz für Ebene „{0}“ wählen").format(L.name), "",
                                               tr("PDF-Dateien (*.pdf *.PDF)"))
            if not p:
                return None
            src = open(p, "rb").read()
            import pypdfium2 as pdfium
            n = len(pdfium.PdfDocument(src))
            sp = 0
            if n > 1:
                from PySide6.QtWidgets import QInputDialog
                sp, ok = QInputDialog.getInt(self, tr("Seite wählen"), tr("Welche Seite der Datei ({0} Seiten)?").format(n),
                                             1, 1, n)
                if not ok:
                    return None
                sp -= 1
            box = self.lmap.boxes.get(L.key) if self.lmap else None
            return editing.replace_layer(d, L.key, self.page, src, sp, box)
        self._run_layer(fn)

    # ---------------- Mausauswahl ---------------- #
    def page_click(self, page, x, y, additive):
        if page != self.page:
            return
        if self.tabs.currentIndex() == 0:
            L = editing.line_at(self.lines, x, y)
            if L is not None:
                if additive:
                    it = self.lst_text.item(L.index)
                    it.setSelected(not it.isSelected())
                    if it.isSelected():
                        self.lst_text.setCurrentRow(L.index)
                else:
                    self.lst_text.setCurrentRow(L.index)
        elif self.tabs.currentIndex() == 1:
            kind = self.cmb_objkind.currentData() or "all"
            hits = [O for O in self.objects if O.bbox[0] <= x <= O.bbox[2] and O.bbox[1] <= y <= O.bbox[3]
                    and (kind == "all" or O.kind == kind)]
            if hits:
                O = min(hits, key=lambda o: (o.bbox[2] - o.bbox[0]) * (o.bbox[3] - o.bbox[1]))
                if additive:
                    it = self.lst_objects.item(O.index)
                    it.setSelected(not it.isSelected())
                    if it.isSelected():
                        self.lst_objects.setCurrentRow(O.index)
                elif self.lst_objects.currentRow() == O.index:
                    self._object_selected(O.index)
                else:
                    self.lst_objects.setCurrentRow(O.index)
        elif self.lmap is not None:
            hits = editing.layers_at(self.lmap, x, y)
            if not hits:
                return
            # a repeated click at the same spot cycles through overlapping layers
            if self._cycle and self._cycle[0] == hits:
                self._cycle[1] = (self._cycle[1] + 1) % len(hits)
            else:
                self._cycle = [hits, 0]
            key = hits[self._cycle[1]]
            for i, L in enumerate(self.layers):
                if L.key == key:
                    self.lst_layers.setCurrentRow(i)
                    break


def _match_line(L0, lines):
    """Dieselbe Zeile nach einer Änderung wiederfinden: gleicher Text, nächstgelegene Mitte."""
    cx, cy = (L0.bbox[0] + L0.bbox[2]) / 2, (L0.bbox[1] + L0.bbox[3]) / 2
    same = [L for L in lines if L.text == L0.text] or lines
    if not same:
        return None
    best = min(same, key=lambda L: abs((L.bbox[0] + L.bbox[2]) / 2 - cx) + abs((L.bbox[1] + L.bbox[3]) / 2 - cy))
    h = max(1.0, L0.bbox[3] - L0.bbox[1])
    d = abs((best.bbox[0] + best.bbox[2]) / 2 - cx) + abs((best.bbox[1] + best.bbox[3]) / 2 - cy)
    return best if d <= max(20.0, 4 * h) else None


def _overlap(b, pb) -> float:
    w = max(0.0, min(b[2], pb[2]) - max(b[0], pb[0]))
    h = max(0.0, min(b[3], pb[3]) - max(b[1], pb[1]))
    area = max(1e-6, (b[2] - b[0]) * (b[3] - b[1]))
    return w * h / area


class _TransformDialog(QDialog):
    def __init__(self, parent, name, box, what=None, with_pages=True):
        super().__init__(parent)
        self._with_pages = with_pages
        self.setWindowTitle(tr("{0} „{1}“ skalieren / verschieben").format(what or tr("Ebene"), name))
        f = QFormLayout(self)
        self.spn_scale = QDoubleSpinBox()
        self.spn_scale.setRange(1, 1000)
        self.spn_scale.setDecimals(1)
        self.spn_scale.setSuffix(" %")
        self.spn_scale.setValue(100)
        f.addRow(tr("Größe:"), self.spn_scale)
        self.spn_dx, self.spn_dy = QDoubleSpinBox(), QDoubleSpinBox()
        for sp in (self.spn_dx, self.spn_dy):
            sp.setRange(-5000, 5000)
            sp.setDecimals(1)
            sp.setSuffix(" mm")
        f.addRow(tr("Verschieben waagrecht (+ rechts):"), self.spn_dx)
        f.addRow(tr("Verschieben senkrecht (+ oben):"), self.spn_dy)
        self.cmb_origin = QComboBox()
        self.cmb_origin.addItem(tr("Mitte der Ebene"), "center")
        self.cmb_origin.addItem(tr("Mitte der Seite"), "page")
        self.cmb_origin.addItem(tr("Seitenursprung (unten links)"), "origin")
        f.addRow(tr("Bezugspunkt fürs Skalieren:"), self.cmb_origin)
        self.cmb_pages = QComboBox()
        if self._with_pages:
            self.cmb_pages.addItem(tr("Nur diese Seite"), False)
            self.cmb_pages.addItem(tr("Alle Seiten"), True)
            f.addRow(tr("Seiten:"), self.cmb_pages)
        b = QPushButton(tr("Auf die Seite zurückholen"))
        b.setToolTip(tr("Verschiebung so setzen, dass die Ebene mittig auf der Seite liegt"))
        b.setEnabled(box is not None)
        b.clicked.connect(lambda: self._center(box))
        f.addRow(b)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)
        self._page_box = None

    def _center(self, box):
        pb = getattr(self.parent().lmap, "page_box", None)
        if box is None or pb is None:
            return
        self.spn_dx.setValue(((pb[0] + pb[2]) / 2 - (box[0] + box[2]) / 2) / MM)
        self.spn_dy.setValue(((pb[1] + pb[3]) / 2 - (box[1] + box[3]) / 2) / MM)

    def values(self, box, page_box):
        o = self.cmb_origin.currentData()
        if o == "center" and box:
            origin = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
        elif o == "page":
            origin = ((page_box[0] + page_box[2]) / 2, (page_box[1] + page_box[3]) / 2)
        else:
            origin = (0.0, 0.0)
        return (self.spn_scale.value() / 100.0, self.spn_dx.value() * MM, self.spn_dy.value() * MM, origin,
                bool(self.cmb_pages.currentData()) if self._with_pages else False)


class _ColorDialog(QDialog):
    """Farbe wählen: CMYK (Druck, Standard) oder RGB; bei Vektoren Fläche und/oder Kontur."""

    def __init__(self, parent, what, last, with_parts=True):
        from PySide6.QtWidgets import QCheckBox, QFrame
        super().__init__(parent)
        self.setWindowTitle(tr("Farbe ändern – {0}").format(what))
        f = QFormLayout(self)
        self.cmb_model = QComboBox()
        self.cmb_model.addItem(tr("CMYK (für den Druck)"), "cmyk")
        self.cmb_model.addItem(tr("RGB"), "rgb")
        f.addRow(tr("Farbmodell:"), self.cmb_model)
        self.spins = {}
        for key, label in (("c", tr("Cyan:")), ("m", tr("Magenta:")), ("y", tr("Gelb:")), ("k", tr("Schwarz:")),
                           ("r", tr("Rot:")), ("g", tr("Grün:")), ("b", tr("Blau:"))):
            sp = QSpinBox()
            sp.setRange(0, 100 if key in "cmyk" else 255)
            sp.setSuffix(" %" if key in "cmyk" else "")
            sp.valueChanged.connect(self._preview)
            self.spins[key] = sp
            f.addRow(label, sp)
        self.btn_pick = QPushButton(tr("Farbe auswählen …"))
        self.btn_pick.clicked.connect(self._pick)
        f.addRow("", self.btn_pick)
        self.swatch = QFrame()
        self.swatch.setMinimumHeight(28)
        self.swatch.setFrameShape(QFrame.Shape.Box)
        f.addRow(tr("Vorschau:"), self.swatch)
        self.chk_fill = QCheckBox(tr("Fläche"))
        self.chk_stroke = QCheckBox(tr("Kontur"))
        self.chk_fill.setChecked(True)
        self.chk_stroke.setChecked(True)
        if with_parts:
            row = QHBoxLayout()
            row.addWidget(self.chk_fill)
            row.addWidget(self.chk_stroke)
            row.addStretch(1)
            f.addRow(tr("Ändern:"), row)
        else:
            self.chk_fill.hide()
            self.chk_stroke.hide()
        hint = QLabel(tr("Schwarzer Text: CMYK 0/0/0/100 bleibt reines Schwarz (kein Vierfarbschwarz)."))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {theme.MUTED};")
        f.addRow(hint)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)
        self._form = f
        kind, vals = last
        if kind == "rgb":
            self.cmb_model.setCurrentIndex(1)
            for k, v in zip("rgb", vals):
                self.spins[k].setValue(round(v * 255))
        else:
            for k, v in zip("cmyk", vals):
                self.spins[k].setValue(round(v * 100))
        self.cmb_model.currentIndexChanged.connect(self._model_changed)
        self._model_changed()

    def _model_changed(self, *_):
        cmyk = self.cmb_model.currentData() == "cmyk"
        for k, sp in self.spins.items():
            self._form.setRowVisible(sp, (k in "cmyk") == cmyk)
        self._form.setRowVisible(self.btn_pick, not cmyk)
        self._preview()

    def _rgb(self):
        if self.cmb_model.currentData() == "cmyk":
            c, m, y, k = (self.spins[x].value() / 100 for x in "cmyk")
            return tuple(round(255 * (1 - v) * (1 - k)) for v in (c, m, y))       # nur Bildschirm-Näherung
        return tuple(self.spins[x].value() for x in "rgb")

    def _preview(self, *_):
        r, g, b = self._rgb()
        self.swatch.setStyleSheet(f"background: rgb({r},{g},{b});")

    def _pick(self):
        from PySide6.QtGui import QColor
        from PySide6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(QColor(*self._rgb()), self, tr("Farbe auswählen"))
        if c.isValid():
            for k, v in zip("rgb", (c.red(), c.green(), c.blue())):
                self.spins[k].setValue(v)

    def values(self):
        if self.cmb_model.currentData() == "cmyk":
            color = ("cmyk", tuple(self.spins[x].value() / 100 for x in "cmyk"))
        else:
            color = ("rgb", tuple(self.spins[x].value() / 255 for x in "rgb"))
        fill = self.chk_fill.isChecked() or self.chk_fill.isHidden()
        stroke = self.chk_stroke.isChecked() or self.chk_stroke.isHidden()
        return color, fill, stroke
