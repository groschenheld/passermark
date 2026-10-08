# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Seitenleiste „Bearbeiten“: Textzeilen (Text, Schrift, Größe) und Ebenen (ein/aus, entfernen, ersetzen,
skalieren/verschieben). Auswahl über die Liste oder per Mausklick auf der Seite."""
from __future__ import annotations

import io
import os
import traceback

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
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
        self.lmap: editing.LayerMap | None = None
        self.lmap_key = None
        self.layers = []
        self.undo: list[bytes] = []
        self._cycle = []
        self._dstate = None
        self.sel_box = None          # Auswahlrahmen (Seitenkoordinaten)
        self._loaded = None          # (Seite, Reiter), für die die Listen gefüllt sind
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
        self.lst_text.currentRowChanged.connect(self._text_selected)
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
        lv.addLayout(row)
        self.tabs.addTab(w, tr("Text"))

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
        self.tabs.addTab(w, tr("Ebenen"))

        self.btn_undo = QPushButton(tr("Rückgängig"))
        self.btn_undo.clicked.connect(self._undo)
        self.btn_undo.setEnabled(False)
        v.addWidget(self.btn_undo)

    # ------------------------------------------------------------------ #
    @property
    def page(self) -> int:
        return self.win.view.current

    def refresh(self):
        """Listen für die aktuelle Seite neu aufbauen."""
        if self.win.doc is None or not self.win.a_edit.isChecked():
            return
        try:
            if self.tabs.currentIndex() == 0:
                self._fill_text()
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

    # ---------------- Maus: auswählen, verschieben, skalieren ---------------- #
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

    def press(self, page, x, y, tol):
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
            if self._inside(box, x, y, tol):
                self._dstate = {"kind": "move", "box": box, "start": (x, y)}
                return
        self.page_click(page, x, y, False)          # neu auswählen …
        box = self.sel_box
        if box is not None and self._inside(box, x, y, tol):
            self._dstate = {"kind": "move", "box": box, "start": (x, y)}   # … und gleich greifen

    def _preview(self, x, y, d=None):
        d = d or self._dstate
        x0, y0, x1, y1 = d["box"]
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
        """Maus mit gedrückter Taste bewegt: gestrichelte Vorschau der neuen Lage."""
        if self._dstate is None or page != self.page or self.sel_box is None:
            return
        _s, _dx, _dy, nb = self._preview(x, y)
        col = SEL_TEXT if self.tabs.currentIndex() == 0 else SEL_LAYER
        self._overlay([(*self._dstate["box"], col)], preview=nb)

    def release(self, page, x, y):
        """Loslassen: Verschieben/Skalieren anwenden (Ebene bzw. Textzeile), mit Rückgängig."""
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
                row = self.lst_text.currentRow()
                if not (0 <= row < len(self.lines)):
                    return
                L = self.lines[row]

                def run(data):
                    # bevorzugt: nur die Textblöcke umschließen (Seite bleibt sonst unverändert)
                    new = editing.transform_line_blocks(data, self.page, L, s, dx, dy, origin)
                    if new is None:
                        new = self._pdfium_edit(data, self.page,
                                                lambda d: editing.transform_line(d, self.page, L, s, dx, dy, origin))[0]
                    return new
                if self._text_edit(run, [L.bbox, nb]):
                    self._reselect_text(nb)
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
        """Nach dem Neuladen die verschobene Zeile wieder auswählen (nächste zur neuen Lage)."""
        if not self.lines:
            return
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        best = min(self.lines, key=lambda L: abs((L.bbox[0] + L.bbox[2]) / 2 - cx) + abs((L.bbox[1] + L.bbox[3]) / 2 - cy))
        self.lst_text.setCurrentRow(best.index)

    def _reselect_layer(self, key):
        for i, L in enumerate(self.layers):
            if L.key == key:
                self.lst_layers.setCurrentRow(i)
                self._layer_selected(i)
                break

    # ---------------- Text ---------------- #
    def _fill_text(self):
        cur = self.lst_text.currentRow()
        self.lines = editing.text_lines(self.win.doc, self.page)
        self.lst_text.blockSignals(True)
        self.lst_text.clear()
        for L in self.lines:
            it = QListWidgetItem(f"{L.text[:60]}\n{L.font.split('+')[-1]} · {L.size:.1f} pt" +
                                 (" · " + tr("Ebene") if L.in_layer else ""))
            self.lst_text.addItem(it)
        self.lst_text.blockSignals(False)
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

    def _text_apply(self):
        row = self.lst_text.currentRow()
        if not (0 <= row < len(self.lines)):
            return
        L = self.lines[row]
        font = self.cmb_font.currentData()
        size = self.spn_size.value()
        size_arg = size if (abs(size - L.size) > 0.01 or font is not None) else None
        text = self.ed_text.text()
        holder = {}

        def run(data):
            new, notes = editing.edit_line_bytes(data, self.page, L, text, font, size_arg)
            holder["notes"] = notes
            return new
        try:
            if self._text_edit(run, [self._wide_box(L)]):
                if holder.get("notes"):
                    QMessageBox.information(self, tr("Hinweis"), "\n\n".join(holder["notes"]))
        except Exception as e:
            _err(self, e)

    def _text_delete(self):
        row = self.lst_text.currentRow()
        if not (0 <= row < len(self.lines)):
            return
        L = self.lines[row]
        try:
            self._text_edit(lambda data: editing.remove_line_ops(data, self.page, L), [L.bbox])
        except Exception as e:
            _err(self, e)

    def _text_edit(self, fn, ignore_boxes, notes=None) -> bool:
        """fn(daten) -> neue Daten. Läuft auf einer Kopie, wird nachgeprüft, erst dann übernommen."""
        self.win.view._close_textpages()                 # keine offenen Seiten der Ansicht während der Änderung
        data = self.win._doc_bytes()
        new = fn(data)
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
        """pdfium-Änderung an einer frisch geladenen Kopie ausführen -> (neue Daten, Hinweise)."""
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
        """Bereich, in dem sich eine geänderte Zeile verändern darf (Zeilenhöhe, ganze Seitenbreite)."""
        pw = self.win.doc.get_page_size(self.page)[0]
        h = L.bbox[3] - L.bbox[1]
        size = self.spn_size.value() if hasattr(self, "spn_size") else L.size
        grow = max(0.0, (float(size) / max(L.size, 0.1) - 1.0)) * h     # größere Schrift darf nach oben wachsen
        return (0, L.bbox[1] - 0.3 * h, pw, L.bbox[3] + 0.3 * h + grow)

    def _after_edit(self, notes):
        # Dokument neu laden (Darstellung aktualisieren), geändert markieren
        self._replace_doc(self.win._doc_bytes())
        if notes:
            QMessageBox.information(self, tr("Hinweis"), "\n\n".join(notes))

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
                self.lst_text.setCurrentRow(L.index)
        elif self.lmap is not None:
            hits = editing.layers_at(self.lmap, x, y)
            if not hits:
                return
            # wiederholter Klick an derselben Stelle wechselt durch übereinanderliegende Ebenen
            if self._cycle and self._cycle[0] == hits:
                self._cycle[1] = (self._cycle[1] + 1) % len(hits)
            else:
                self._cycle = [hits, 0]
            key = hits[self._cycle[1]]
            for i, L in enumerate(self.layers):
                if L.key == key:
                    self.lst_layers.setCurrentRow(i)
                    break


def _overlap(b, pb) -> float:
    w = max(0.0, min(b[2], pb[2]) - max(b[0], pb[0]))
    h = max(0.0, min(b[3], pb[3]) - max(b[1], pb[1]))
    area = max(1e-6, (b[2] - b[0]) * (b[3] - b[1]))
    return w * h / area


class _TransformDialog(QDialog):
    def __init__(self, parent, name, box):
        super().__init__(parent)
        self.setWindowTitle(tr("Ebene „{0}“ skalieren / verschieben").format(name))
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
                bool(self.cmb_pages.currentData()))
