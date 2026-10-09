# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Dialog „Daten erfassen“: eine Datentabelle für variable Daten direkt in Passermark anlegen.

Je Datenart (Visitenkarte, WLAN, E-Mail, Code 128, EAN-13 …) bringt die Tabelle die passenden Spalten mit; jede
Zeile wird sofort geprüft, der fertige Code-Inhalt der gewählten Zeile ist rechts zu sehen. Gespeichert wird als CSV
(UTF-8, Semikolon) – in Excel lesbar und in Variable Daten wieder verwendbar. „In Variable Daten verwenden“ übergibt
die Tabelle samt passendem Feld.

Die Daten liegen in self.cols / self.rows (Liste von dicts); die Tabelle ist nur die Ansicht.
"""
from __future__ import annotations

import io
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QKeySequence, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QMessageBox,
                               QPlainTextEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from .. import datakinds, vdp
from ..l10n import tr
from . import theme
from .common import fill_combo, no_enter_default, split_panels


class DataDialog(QDialog):
    def __init__(self, parent, path: str = "", kind: str = ""):
        super().__init__(parent)
        self.setWindowTitle(tr("Daten erfassen – Passermark"))
        self.resize(1200, 760)
        self.kind = kind if kind in datakinds.IDS else "vcard"
        self.cols: list[str] = []
        self.rows: list[dict] = []
        self.path = ""
        self.dirty = False
        self.use = False                 # True: „In Variable Daten verwenden“ gewählt
        self._sync = False

        root = QHBoxLayout(self)
        left = QVBoxLayout()
        top = QHBoxLayout()
        self.cmb_kind = QComboBox()
        fill_combo(self.cmb_kind, [(k, datakinds.get(k).title) for k in datakinds.IDS], self.kind)
        self.cmb_kind.currentIndexChanged.connect(self._kind_changed)
        top.addWidget(QLabel(tr("Art:")))
        top.addWidget(self.cmb_kind, 1)
        for text, fn, tip in ((tr("Neu"), self._new, tr("Leere Tabelle mit den Spalten dieser Art")),
                              (tr("CSV öffnen …"), self._open, tr("Vorhandene Tabelle laden (CSV)")),
                              (tr("Speichern"), self._save, tr("Als CSV speichern")),
                              (tr("Speichern unter …"), self._save_as, "")):
            b = QPushButton(text)
            if tip:
                b.setToolTip(tip)
            b.clicked.connect(fn)
            top.addWidget(b)
        left.addLayout(top)
        self.lbl_help = QLabel()
        self.lbl_help.setWordWrap(True)
        self.lbl_help.setStyleSheet(f"color: {theme.MUTED};")
        left.addWidget(self.lbl_help)

        self.tbl = QTableWidget()
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.cellChanged.connect(self._cell_changed)
        self.tbl.currentCellChanged.connect(lambda r, _c, _pr, _pc: self._show_row(r))
        self.tbl.installEventFilter(self)
        left.addWidget(self.tbl, 1)

        row = QHBoxLayout()
        for text, fn, tip in (
                (tr("+ Zeile"), self.add_row, tr("Leere Zeile anhängen")),
                (tr("Zeile duplizieren"), self._dup, tr("Gewählte Zeile kopieren – praktisch, wenn sich nur wenig "
                                                         "ändert")),
                (tr("Zeilen löschen"), self._del, tr("Gewählte Zeilen löschen")),
                (tr("Beispielzeile"), self._example, tr("Eine ausgefüllte Zeile als Muster anhängen")),
                (tr("Spalte füllen …"), self._fill, tr("Eine Spalte mit einer Nummernreihe füllen, z. B. T0001, "
                                                         "T0002 …")),
                (tr("Spalte hinzufügen …"), self._add_col, tr("Eigene Spalte, z. B. für einen Text auf der Karte"))):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch()
        left.addLayout(row)
        tip = QLabel(tr("Tipp: Zellen aus Excel/LibreOffice kopieren und hier mit Strg+V einfügen – auch mehrere "
                        "Zeilen und Spalten auf einmal. Entf leert die gewählten Zellen."))
        tip.setWordWrap(True)
        tip.setStyleSheet(f"color: {theme.MUTED};")
        left.addWidget(tip)

        # rechts: gewählte Zeile, Prüfung
        right = QVBoxLayout()
        right.addWidget(QLabel(f"<b>{tr('Inhalt der gewählten Zeile')}</b>"))
        self.lbl_qr = QLabel()
        self.lbl_qr.setMinimumSize(220, 220)
        self.lbl_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_qr.setStyleSheet("background: #ffffff;")
        right.addWidget(self.lbl_qr)
        self.txt_value = QPlainTextEdit()
        self.txt_value.setReadOnly(True)
        self.txt_value.setMaximumHeight(150)
        right.addWidget(self.txt_value)
        right.addWidget(QLabel(f"<b>{tr('Prüfung')}</b>"))
        self.lst_prob = QListWidget()
        self.lst_prob.itemDoubleClicked.connect(self._goto_problem)
        right.addWidget(self.lst_prob, 1)
        self.lbl_count = QLabel()
        right.addWidget(self.lbl_count)
        bb = QDialogButtonBox()
        self.btn_use = bb.addButton(tr("In Variable Daten verwenden"), QDialogButtonBox.ButtonRole.AcceptRole)
        self.btn_use.setToolTip(tr("Speichert die Tabelle und übernimmt sie als Datenquelle – das passende Feld wird "
                                   "angelegt"))
        bb.addButton(tr("Schließen"), QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(self._use)
        bb.rejected.connect(self.reject)
        right.addWidget(bb)
        wrap = QWidget()
        wrap.setLayout(right)
        split_panels(root, left, wrap, 760)
        no_enter_default(self)

        if path and os.path.isfile(path):
            self.load(path)
        else:
            self.set_kind(self.kind, reset=True)

    # -------------------------------------------------------------- Modell
    def set_kind(self, kind: str, reset: bool = False):
        """Datenart wechseln: fehlende Spalten ergänzen (vorhandene Daten bleiben)."""
        self.kind = kind
        k = datakinds.get(kind)
        if reset:
            self.cols = datakinds.columns(kind)
            self.rows = [{c: "" for c in self.cols} for _ in range(5)]
        else:
            low = {c.lower() for c in self.cols}
            self.cols += [c for c in datakinds.columns(kind) if c.lower() not in low]
        self.lbl_help.setText(k.help + "  " + tr("Pflichtspalten sind mit * markiert; Erklärung beim Zeigen auf die "
                                                 "Spaltenüberschrift."))
        self._render()

    def add_row(self, values: dict | None = None):
        self.rows.append({c: (values or {}).get(c, "") for c in self.cols})
        self.dirty = True
        self._render()

    def duplicate(self, i: int):
        if 0 <= i < len(self.rows):
            self.rows.insert(i + 1, dict(self.rows[i]))
            self.dirty = True
            self._render()

    def delete(self, idx):
        for i in sorted(set(idx), reverse=True):
            if 0 <= i < len(self.rows):
                del self.rows[i]
        self.dirty = True
        self._render()

    def add_column(self, name: str) -> bool:
        name = (name or "").strip()
        if not name or name.lower() in {c.lower() for c in self.cols} or "{" in name or "}" in name:
            return False
        self.cols.append(name)
        for r in self.rows:
            r.setdefault(name, "")
        self.dirty = True
        self._render()
        return True

    def fill_column(self, col: str, start=1, step=1, digits=0, prefix="", suffix="", only_empty=False, count=0):
        """Spalte mit einer Nummernreihe füllen; count = so viele Zeilen sollen es mindestens werden."""
        while len(self.rows) < count:
            self.rows.append({c: "" for c in self.cols})
        vals = datakinds.series(len(self.rows), start, step, digits, prefix, suffix)
        for r, v in zip(self.rows, vals):
            if not only_empty or not str(r.get(col, "")).strip():
                r[col] = v
        self.dirty = True
        self._render()

    def paste_text(self, text: str, row: int, col: int):
        """Tabellentext (Tab-getrennt, z. B. aus Excel) ab Zeile/Spalte einfügen; Zeilen werden angehängt."""
        lines = [ln for ln in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
        while lines and lines[-1] == "":
            lines.pop()
        row, col = max(0, row), max(0, col)
        for k, ln in enumerate(lines):
            r = row + k
            while r >= len(self.rows):
                self.rows.append({c: "" for c in self.cols})
            for j, cell in enumerate(ln.split("\t")):
                if col + j < len(self.cols):
                    self.rows[r][self.cols[col + j]] = cell.strip()
        self.dirty = True
        self._render()

    def data_rows(self) -> list:
        return [r for r in self.rows if any(str(v or "").strip() for v in r.values())]

    def problems(self) -> list:
        return datakinds.validate(self.kind, self.cols, self.data_rows())

    def load(self, path: str):
        cols, rows = vdp.read_csv(path)
        self.cols = list(cols)
        self.rows = [{c: str(r.get(c, "") or "") for c in self.cols} for r in rows]
        self.path = os.path.abspath(path)
        self.kind = datakinds.guess_kind(self.cols)
        self.cmb_kind.blockSignals(True)
        self.cmb_kind.setCurrentIndex(max(0, self.cmb_kind.findData(self.kind)))
        self.cmb_kind.blockSignals(False)
        self.set_kind(self.kind)
        self.dirty = False
        self._title()

    def save(self, path: str):
        datakinds.write_csv(path, self.cols, self.rows)
        self.path = os.path.abspath(path)
        self.dirty = False
        self._title()

    # -------------------------------------------------------------- Ansicht
    def _title(self):
        self.setWindowTitle(tr("Daten erfassen – Passermark") + (f" – {os.path.basename(self.path)}" if self.path
                                                                 else ""))

    def _render(self):
        self._sync = True
        try:
            req = {c.key.lower(): c for c in datakinds.get(self.kind).cols}
            self.tbl.setColumnCount(len(self.cols))
            self.tbl.setRowCount(len(self.rows))
            for j, c in enumerate(self.cols):
                spec = req.get(c.lower())
                it = QTableWidgetItem(c + (" *" if spec is not None and spec.required else ""))
                if spec is not None and spec.hint:
                    it.setToolTip(spec.hint + (f"\n{tr('Beispiel')}: {spec.example}" if spec.example else ""))
                self.tbl.setHorizontalHeaderItem(j, it)
            for i, r in enumerate(self.rows):
                for j, c in enumerate(self.cols):
                    self.tbl.setItem(i, j, QTableWidgetItem(str(r.get(c, "") or "")))
        finally:
            self._sync = False
        self._check()

    def _cell_changed(self, i, j):
        if self._sync or not (0 <= i < len(self.rows) and 0 <= j < len(self.cols)):
            return
        it = self.tbl.item(i, j)
        self.rows[i][self.cols[j]] = it.text() if it is not None else ""
        self.dirty = True
        self._check()
        self._show_row(i)

    def _check(self):
        self.lst_prob.clear()
        probs = self.problems()
        rows = self.data_rows()
        idx = {id(r): k for k, r in enumerate(self.rows)}
        self._prob_rows = []
        for r, col, msg in probs:
            row = idx.get(id(rows[r]), -1) if 0 <= r < len(rows) else -1
            self._prob_rows.append(row)
            where = tr("Zeile {0}").format(row + 1) if row >= 0 else tr("Tabelle")
            self.lst_prob.addItem(f"{where}{' · ' + col if col else ''}: {msg}")
        if not probs:
            self.lst_prob.addItem(tr("✓ Alles in Ordnung"))
        self.lbl_count.setText(tr("{0} Datensätze").format(len(rows)))

    def _goto_problem(self, _item):
        k = self.lst_prob.currentRow()
        rows = getattr(self, "_prob_rows", [])
        if 0 <= k < len(rows) and rows[k] >= 0:
            self.tbl.setCurrentCell(rows[k], 0)

    def _show_row(self, i):
        self.txt_value.setPlainText("")
        self.lbl_qr.clear()
        if not (0 <= i < len(self.rows)) or not any(str(v).strip() for v in self.rows[i].values()):
            return
        rec = self.rows[i]
        try:
            value = self.content_of(rec)
        except ValueError as e:
            self.txt_value.setPlainText("⚠ " + str(e))
            return
        self.txt_value.setPlainText(value)
        try:
            self.lbl_qr.setPixmap(self._code_pixmap(value))
        except Exception as e:                            # noqa: BLE001 – Vorschau darf nie stören
            self.txt_value.setPlainText(value + "\n\n⚠ " + str(e))

    def content_of(self, rec: dict) -> str:
        return datakinds.build(self.kind, rec)

    def _code_pixmap(self, value: str):
        """Code der gewählten Zeile als Bild (wie er gedruckt wird)."""
        import pypdfium2 as pdfium
        from reportlab.pdfgen import canvas
        fk = datakinds.get(self.kind).field_kind
        if fk == "text":
            return QPixmap()
        w, h = {"qr": (50, 50), "code128": (60, 20), "ean13": (40, 28)}[fk]
        buf = io.BytesIO()
        cv = canvas.Canvas(buf, pagesize=(w * vdp.MM, h * vdp.MM))
        vdp.draw_field(cv, vdp.VdpField(fk, value, 0, 0, w, h, size_pt=8), value, h * vdp.MM)
        cv.showPage()
        cv.save()
        d = pdfium.PdfDocument(buf.getvalue())
        try:
            img = d[0].render(scale=200 / max(w, h) / vdp.MM, fill_color=(255, 255, 255, 255)).to_pil().convert("RGB")
        finally:
            d.close()
        data = img.tobytes("raw", "RGB")
        return QPixmap.fromImage(QImage(data, img.width, img.height, 3 * img.width, QImage.Format.Format_RGB888).copy())

    def eventFilter(self, obj, ev):
        """Strg+V / Strg+C / Entf in der Tabelle."""
        try:
            from PySide6.QtCore import QEvent
            if obj is self.tbl and ev.type() == QEvent.Type.KeyPress:
                if ev.matches(QKeySequence.StandardKey.Paste):
                    self.paste_text(QApplication.clipboard().text(), self.tbl.currentRow(), self.tbl.currentColumn())
                    return True
                if ev.matches(QKeySequence.StandardKey.Copy):
                    self._copy()
                    return True
                if ev.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and not self.tbl.state() == \
                        QAbstractItemView.State.EditingState:
                    for it in self.tbl.selectedItems():
                        it.setText("")
                    return True
        except Exception:                                 # noqa: BLE001
            pass
        return super().eventFilter(obj, ev)

    def _copy(self):
        rng = self.tbl.selectedRanges()
        if not rng:
            return
        r = rng[0]
        lines = []
        for i in range(r.topRow(), r.bottomRow() + 1):
            lines.append("\t".join(str(self.rows[i].get(self.cols[j], "")) for j in range(r.leftColumn(),
                                                                                       r.rightColumn() + 1)))
        QApplication.clipboard().setText("\n".join(lines))

    def _selected_rows(self) -> list:
        return sorted({ix.row() for ix in self.tbl.selectedIndexes()} or {self.tbl.currentRow()})

    # -------------------------------------------------------------- Knöpfe
    def _kind_changed(self, _i):
        k = self.cmb_kind.currentData()
        if k and k != self.kind:
            self.set_kind(k, reset=not self.data_rows())

    def _ask_discard(self) -> bool:
        if not self.dirty or not self.data_rows():
            return True
        r = QMessageBox.question(self, tr("Daten erfassen"), tr("Die Tabelle ist nicht gespeichert. Trotzdem "
                                                               "verwerfen?"))
        return r == QMessageBox.StandardButton.Yes

    def _new(self):
        if self._ask_discard():
            self.path = ""
            self.set_kind(self.cmb_kind.currentData() or self.kind, reset=True)
            self.dirty = False
            self._title()

    def _open(self):
        if not self._ask_discard():
            return
        p, _ = QFileDialog.getOpenFileName(self, tr("CSV-Datei wählen"), os.path.dirname(self.path),
                                           tr("CSV/Text (*.csv *.txt *.tsv);;Alle (*)"))
        if p:
            try:
                self.load(p)
            except Exception as e:                        # noqa: BLE001
                QMessageBox.warning(self, tr("CSV"), str(e))

    def _save(self) -> bool:
        if not self.path:
            return self._save_as()
        try:
            self.save(self.path)
            return True
        except OSError as e:
            QMessageBox.critical(self, tr("Speichern"), str(e))
            return False

    def _save_as(self) -> bool:
        name = self.path or os.path.join(os.path.expanduser("~"), {"vcard": "visitenkarten", "wifi": "wlan"}.get(
            self.kind, "daten") + ".csv")
        p, _ = QFileDialog.getSaveFileName(self, tr("Tabelle speichern"), name, tr("CSV (*.csv)"))
        if not p or not isinstance(p, str):
            return False
        if not p.lower().endswith(".csv"):
            p += ".csv"
        try:
            self.save(p)
            return True
        except OSError as e:
            QMessageBox.critical(self, tr("Speichern"), str(e))
            return False

    def _dup(self):
        self.duplicate(self.tbl.currentRow())

    def _del(self):
        self.delete(self._selected_rows())

    def _example(self):
        self.add_row(datakinds.example_row(self.kind))

    def _add_col(self):
        name, ok = QInputDialog.getText(self, tr("Spalte hinzufügen"), tr("Name der Spalte (wird zu {{Name}}):"))
        if ok and not self.add_column(str(name)):
            QMessageBox.information(self, tr("Spalte hinzufügen"), tr("Name leer, schon vorhanden oder mit { }."))

    def _fill(self):
        dlg = _FillDialog(self, self.cols, self.cols[self.tbl.currentColumn()] if 0 <= self.tbl.currentColumn()
                          < len(self.cols) else (self.cols[0] if self.cols else ""), len(self.rows))
        if dlg.exec():
            self.fill_column(*dlg.values())

    def _use(self):
        if not self.data_rows():
            QMessageBox.information(self, tr("Daten erfassen"), tr("Die Tabelle ist leer."))
            return
        probs = self.problems()
        if probs:
            r = QMessageBox.question(self, tr("Daten erfassen"), tr("{0} Problem(e) in der Tabelle – trotzdem "
                                                                   "verwenden? Betroffene Datensätze ergeben beim "
                                                                   "Erzeugen einen Fehler.").format(len(probs)))
            if r != QMessageBox.StandardButton.Yes:
                return
        if (self.dirty or not self.path) and not self._save():
            return
        self.use = True
        self.accept()

    def reject(self):
        if not self._ask_discard():
            return
        super().reject()


class _FillDialog(QDialog):
    """Spalte mit Nummernreihe füllen."""

    def __init__(self, parent, cols, current, rows=0):
        super().__init__(parent)
        self.setWindowTitle(tr("Spalte füllen"))
        f = QFormLayout(self)
        self.cmb = QComboBox()
        fill_combo(self.cmb, [(c, c) for c in cols], current)
        self.spn_start, self.spn_step, self.spn_digits = QSpinBox(), QSpinBox(), QSpinBox()
        self.spn_start.setRange(-10 ** 9, 10 ** 9)
        self.spn_start.setValue(1)
        self.spn_step.setRange(-1000, 1000)
        self.spn_step.setValue(1)
        self.spn_digits.setRange(0, 20)
        self.ed_pre, self.ed_suf = QLineEdit(), QLineEdit()
        self.ed_pre.setPlaceholderText(tr("davor, z. B. T"))
        self.cmb_mode = QComboBox()
        fill_combo(self.cmb_mode, [(False, tr("alle Zeilen")), (True, tr("nur leere Zellen"))], False)
        self.spn_count = QSpinBox()
        self.spn_count.setRange(0, vdp.MAX_RECORDS)
        self.spn_count.setValue(rows)
        for lab, w in ((tr("Spalte"), self.cmb), (tr("Anzahl Zeilen"), self.spn_count), (tr("erste Nummer"), self.spn_start),
                       (tr("Schrittweite"), self.spn_step), (tr("Stellen (mit Nullen)"), self.spn_digits),
                       (tr("Text davor"), self.ed_pre), (tr("Text danach"), self.ed_suf), (tr("Füllen"), self.cmb_mode)):
            f.addRow(lab + ":", w)
        hint = QLabel(tr("Beispiel: Text davor T, Stellen 4 → T0001, T0002 … Ist die Anzahl größer als die Tabelle, "
                         "werden Zeilen angehängt – z. B. 100 für 100 Tickets."))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {theme.MUTED};")
        f.addRow(hint)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def values(self):
        return (self.cmb.currentData(), self.spn_start.value(), self.spn_step.value(), self.spn_digits.value(),
                self.ed_pre.text(), self.ed_suf.text(), bool(self.cmb_mode.currentData()), self.spn_count.value())


def field_for(kind: str, page_w_mm: float, page_h_mm: float) -> vdp.VdpField:
    """Passendes Feld für eine Datenart (wird bei „In Variable Daten verwenden“ angelegt)."""
    k = datakinds.get(kind)
    fk = k.field_kind
    w, h = {"qr": (30, 30), "code128": (55, 18), "ean13": (38, 26), "text": (70, 10)}[fk]
    x, y = max(0.0, min(10.0, page_w_mm - w)), max(0.0, min(10.0, page_h_mm - h))
    if fk == "qr":
        if kind in datakinds.QR_TYPES:
            return vdp.VdpField("qr", "", x, y, w, h, qr_type=kind)
        return vdp.VdpField("qr", "{{" + k.cols[0].key + "}}", x, y, w, h)
    if fk == "code128":
        return vdp.VdpField("code128", "{{Code}}", x, y, w, h, size_pt=9)
    if fk == "ean13":
        return vdp.VdpField("ean13", "{{EAN}}", x, y, w, h)
    return vdp.VdpField("text", "{{" + k.cols[0].key + "}}", x, y, w, h)
