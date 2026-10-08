# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Seitenleiste „Prüfung“: Befunde, Schriften, Ebenen, Transparenz – mit Reparaturen (Ergebnis im neuen Fenster)."""
from __future__ import annotations

import os
import traceback

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QFileDialog, QHBoxLayout,
                               QHeaderView, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget,
                               QTableWidgetItem, QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import preflight
from ..l10n import tr
from . import theme

SEV_TEXT = {"error": "Fehler", "warning": "Warnung", "info": "Hinweis"}
CAT_TEXT = {"font": "Schrift", "layer": "Ebene", "transparency": "Transparenz", "text": "Zeichen"}
KIND_TEXT = {"smask": "weiche Maske", "blend": "Füllmethode", "alpha": "Deckkraft", "group": "Transparenzgruppe",
             "overprint": "Überdrucken", "image_alpha": "Bild mit Transparenz"}


class _Worker(QThread):
    done = Signal(object, str)

    def __init__(self, fn, *args):
        super().__init__()
        self.fn, self.args = fn, args

    def run(self):
        try:
            self.done.emit(self.fn(*self.args), "")
        except Exception as e:
            self.done.emit(None, f"{e}\n\n{traceback.format_exc()}")


class PreflightPanel(QWidget):
    """Prüfergebnis anzeigen und reparieren. Signale: Ergebnis öffnen, Seite anspringen, neu prüfen."""
    result_ready = Signal(bytes, str, list)      # PDF-Bytes, Namenszusatz, Hinweise
    goto_page = Signal(int)
    recheck = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rep: preflight.Report | None = None
        self.data_fn = None                       # liefert die aktuellen Dokument-Bytes
        self.font_map: dict[str, str] = {}
        self._worker = None
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)
        self.lbl_sum = QLabel(tr("Noch nicht geprüft."))
        self.lbl_sum.setWordWrap(True)
        v.addWidget(self.lbl_sum)
        row = QHBoxLayout()
        b = QPushButton(tr("Neu prüfen"))
        b.clicked.connect(self.recheck.emit)
        row.addWidget(b)
        self.btn_report = QPushButton(tr("Bericht …"))
        self.btn_report.clicked.connect(self._save_report)
        row.addWidget(self.btn_report)
        v.addLayout(row)

        self.tabs = QTabWidget()
        v.addWidget(self.tabs, 1)
        # Befunde
        w = QWidget()
        lv = QVBoxLayout(w)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([tr("Art"), tr("Befund"), tr("Seiten")])
        self.tree.setRootIsDecorated(False)
        self.tree.setWordWrap(True)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tree.itemDoubleClicked.connect(self._issue_clicked)
        lv.addWidget(self.tree, 1)
        self.btn_fix_all = QPushButton(tr("Empfohlene Reparaturen …"))
        self.btn_fix_all.setToolTip(tr("Ebenen festschreiben (falls ausgeblendete vorhanden) und fehlende Schriften "
                                       "mit Ersatz einbetten – Ergebnis im neuen Fenster"))
        self.btn_fix_all.clicked.connect(self._fix_all)
        lv.addWidget(self.btn_fix_all)
        self.tabs.addTab(w, tr("Befunde"))
        # Schriften
        w = QWidget()
        lv = QVBoxLayout(w)
        self.tbl_fonts = QTableWidget(0, 4)
        self.tbl_fonts.setHorizontalHeaderLabels([tr("Schrift"), tr("Typ"), tr("Status"), tr("Ersatz")])
        self.tbl_fonts.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl_fonts.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tbl_fonts.verticalHeader().setVisible(False)
        self.tbl_fonts.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        lv.addWidget(self.tbl_fonts, 1)
        row = QHBoxLayout()
        bf = QPushButton(tr("Schriftdatei wählen …"))
        bf.setToolTip(tr("Für die markierte Schrift eine eigene Schriftdatei als Ersatz wählen"))
        bf.clicked.connect(lambda: self._font_action("__file__"))
        bd = QPushButton(tr("Freie Schrift herunterladen …"))
        bd.setToolTip(tr("Für die markierte Schrift eine freie Schrift von fontsource.org laden"))
        bd.clicked.connect(lambda: self._font_action("__download__"))
        row.addWidget(bf)
        row.addWidget(bd)
        lv.addLayout(row)
        row = QHBoxLayout()
        b1 = QPushButton(tr("Schriften einbetten"))
        b1.setToolTip(tr("Alle Schriften einbetten, fehlende durch den gewählten Ersatz (Ghostscript)"))
        b1.clicked.connect(self._embed)
        b2 = QPushButton(tr("Text in Pfade"))
        b2.setToolTip(tr("Sieht überall gleich aus, Text ist danach aber nicht mehr durchsuchbar"))
        b2.clicked.connect(lambda: self._run(preflight.outline_text, tr("_Pfade"), [tr("Text in Pfade umgewandelt.")]))
        row.addWidget(b1)
        row.addWidget(b2)
        lv.addLayout(row)
        self.tabs.addTab(w, tr("Schriften"))
        # Ebenen
        w = QWidget()
        lv = QVBoxLayout(w)
        self.tbl_layers = QTableWidget(0, 4)
        self.tbl_layers.setHorizontalHeaderLabels([tr("Ebene"), tr("Ansicht"), tr("Druck"), tr("Hinweis")])
        self.tbl_layers.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl_layers.verticalHeader().setVisible(False)
        self.tbl_layers.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        lv.addWidget(self.tbl_layers, 1)
        b1 = QPushButton(tr("Zustand übernehmen"))
        b1.setToolTip(tr("Die gewählte Sichtbarkeit (Ansicht/Druck) ins Dokument schreiben – Ebenen bleiben erhalten"))
        b1.clicked.connect(self._layers_apply)
        b2 = QPushButton(tr("Sichtbaren Zustand festschreiben"))
        b2.setToolTip(tr("Ausgeblendete Inhalte entfernen und Ebenen auflösen – danach druckt jeder Drucker genau "
                         "das Sichtbare (Druck-Einstellung der Spalte „Druck“)"))
        b2.clicked.connect(self._layers_flatten)
        b3 = QPushButton(tr("Markierte entfernen"))
        b3.clicked.connect(self._layers_remove)
        for b in (b1, b2, b3):
            lv.addWidget(b)
        self.tabs.addTab(w, tr("Ebenen"))
        # Transparenz
        w = QWidget()
        lv = QVBoxLayout(w)
        self.lbl_trans = QLabel()
        self.lbl_trans.setWordWrap(True)
        self.lbl_trans.setAlignment(Qt.AlignmentFlag.AlignTop)
        lv.addWidget(self.lbl_trans, 1)
        b = QPushButton(tr("Transparenzen reduzieren (300 dpi)"))
        b.setToolTip(tr("Für ältere Drucker/RIPs: transparente Bereiche werden gerastert (PDF 1.3)"))
        b.clicked.connect(lambda: self._run(preflight.flatten_transparency, tr("_ohneTransparenz"),
                                            [tr("Transparenzen reduziert.")]))
        lv.addWidget(b)
        self.tabs.addTab(w, tr("Transparenz"))

    # ------------------------------------------------------------------ #
    def set_busy(self, text=None):
        self.lbl_sum.setText(text or tr("Prüfe …"))

    def set_error(self, msg):
        self.lbl_sum.setText("⚠ " + msg.splitlines()[0])

    def set_report(self, rep: preflight.Report):
        self.rep = rep
        c = rep.counts()
        if not rep.issues:
            self.lbl_sum.setText("✓ " + tr("Keine Probleme gefunden."))
        else:
            self.lbl_sum.setText(tr("{0} Fehler, {1} Warnung(en), {2} Hinweis(e)").format(c["error"], c["warning"], c["info"]))
        col = {"error": theme.ERROR, "warning": theme.ACCENT, "info": theme.MUTED}
        self.tree.clear()
        for i in rep.issues:
            it = QTreeWidgetItem([tr(SEV_TEXT[i.severity]) + " · " + tr(CAT_TEXT[i.category]), i.message,
                                  preflight._pages_str(i.pages)])
            it.setForeground(0, QBrush(QColor(col[i.severity])))
            it.setData(0, Qt.ItemDataRole.UserRole, i.pages[0] if i.pages else 0)
            it.setToolTip(1, i.message)
            self.tree.addTopLevelItem(it)
        self.tree.resizeColumnToContents(0)
        # Schriften
        st = {"ok": tr("eingebettet"), "std14": tr("Standard, nicht eingebettet"), "missing": tr("NICHT eingebettet"),
              "type3": "Type3"}
        self.tbl_fonts.setRowCount(0)
        self.font_map = {}
        for f in rep.fonts:
            r = self.tbl_fonts.rowCount()
            self.tbl_fonts.insertRow(r)
            self.tbl_fonts.setItem(r, 0, QTableWidgetItem(f.name + (tr(" (Teilmenge)") if f.subset else "")))
            self.tbl_fonts.setItem(r, 1, QTableWidgetItem(f.subtype))
            s_item = QTableWidgetItem(st[f.status])
            if f.status == "missing":
                s_item.setForeground(QBrush(QColor(theme.ERROR)))
            self.tbl_fonts.setItem(r, 2, s_item)
            if f.status in ("missing", "std14"):
                cb = QComboBox()
                cb.addItem(f.suggestion_name or tr("(kein Ersatz)"), f.suggestion)
                cb.addItem(tr("Schriftdatei wählen …"), "__file__")
                cb.addItem(tr("Freie Schrift herunterladen …"), "__download__")
                cb.setProperty("font", f.name)
                cb.activated.connect(lambda _i=0, c=cb: self._font_choice(c))
                self.tbl_fonts.setCellWidget(r, 3, cb)
                if f.suggestion:
                    self.font_map[f.name] = f.suggestion
            else:
                self.tbl_fonts.setItem(r, 3, QTableWidgetItem("–"))
        # Ebenen
        self.tbl_layers.setRowCount(0)
        for L in rep.layers:
            r = self.tbl_layers.rowCount()
            self.tbl_layers.insertRow(r)
            it = QTableWidgetItem(L.name)
            it.setData(Qt.ItemDataRole.UserRole, L.key)
            self.tbl_layers.setItem(r, 0, it)
            for col_i, on in ((1, L.view_on), (2, L.view_on if L.print_on is None else L.print_on)):
                c = QCheckBox()
                c.setChecked(bool(on))
                wrap = QWidget()
                hl = QHBoxLayout(wrap)
                hl.setContentsMargins(0, 0, 0, 0)
                hl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                hl.addWidget(c)
                self.tbl_layers.setCellWidget(r, col_i, wrap)
            note = []
            if L.outside_pct is not None and L.outside_pct > 25:
                note.append(tr("{0:.0f} % außerhalb").format(L.outside_pct))
            if not L.pages:
                note.append(tr("leer"))
            self.tbl_layers.setItem(r, 3, QTableWidgetItem(", ".join(note)))
        if not rep.layers:
            self.tbl_layers.setRowCount(0)
        # Transparenz
        if rep.transparency:
            lines = []
            for p, kinds in sorted(rep.transparency.items())[:60]:
                lines.append(tr("Seite {0}: {1}").format(p, ", ".join(tr(KIND_TEXT[k]) for k in sorted(kinds))))
            self.lbl_trans.setText("\n".join(lines))
        else:
            self.lbl_trans.setText(tr("Keine Transparenzen gefunden."))

    # ------------------------------------------------------------------ #
    def _issue_clicked(self, it, _col):
        p = it.data(0, Qt.ItemDataRole.UserRole)
        if p:
            self.goto_page.emit(int(p))

    def _layer_states(self):
        st = {}
        for r in range(self.tbl_layers.rowCount()):
            key = self.tbl_layers.item(r, 0).data(Qt.ItemDataRole.UserRole)
            view = self.tbl_layers.cellWidget(r, 1).findChild(QCheckBox).isChecked()
            prn = self.tbl_layers.cellWidget(r, 2).findChild(QCheckBox).isChecked()
            st[key] = (view, prn)
        return st

    def _layers_apply(self):
        if not self.rep or not self.rep.layers:
            return
        st = self._layer_states()
        self._run(lambda d: preflight.set_layer_states(d, st), tr("_Ebenen"), [tr("Ebenen-Zustand übernommen.")])

    def _ask_basis(self, states) -> str | None:
        """Unterscheiden sich Ansicht und Druck, fragen, welcher Zustand festgeschrieben wird."""
        diff = [self.tbl_layers.item(r, 0).text() for r in range(self.tbl_layers.rowCount())
                if states[self.tbl_layers.item(r, 0).data(Qt.ItemDataRole.UserRole)][0]
                != states[self.tbl_layers.item(r, 0).data(Qt.ItemDataRole.UserRole)][1]]
        if not diff:
            return "print"
        box = QMessageBox(QMessageBox.Icon.Question, tr("Ebenen festschreiben"),
                          tr("Bei diesen Ebenen unterscheiden sich Ansicht und Druck:\n{0}\n\n"
                             "Welcher Zustand soll festgeschrieben werden?").format("\n".join("• " + d for d in diff)),
                          parent=self)
        b_print = box.addButton(tr("Wie beim Druck"), QMessageBox.ButtonRole.AcceptRole)
        b_view = box.addButton(tr("Wie am Bildschirm"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(b_print)
        box.exec()
        if box.clickedButton() is b_print:
            return "print"
        if box.clickedButton() is b_view:
            return "view"
        return None

    def _layers_flatten(self):
        if not self.rep or not self.rep.layers:
            return
        st = self._layer_states()
        basis = self._ask_basis(st)
        if basis is None:
            return
        vis = {k for k, (v, p) in st.items() if (p if basis == "print" else v)}
        self._run(lambda d: preflight.flatten_layers(d, vis), tr("_festgeschrieben"),
                  [tr("Ebenen festgeschrieben – es wird genau das Sichtbare gedruckt.")])

    def _layers_remove(self):
        rows = {i.row() for i in self.tbl_layers.selectedIndexes()}
        if not rows:
            QMessageBox.information(self, tr("Ebenen"), tr("Bitte zuerst Ebenen in der Liste markieren."))
            return
        keys = {self.tbl_layers.item(r, 0).data(Qt.ItemDataRole.UserRole) for r in rows}
        self._run(lambda d: preflight.remove_layers(d, keys), tr("_Ebenen"),
                  [tr("{0} Ebene(n) entfernt.").format(len(keys))])

    def _font_action(self, what):
        """Knöpfe unter der Tabelle: wirken auf die markierte Zeile."""
        row = self.tbl_fonts.currentRow()
        cb = self.tbl_fonts.cellWidget(row, 3) if row >= 0 else None
        if not isinstance(cb, QComboBox):
            QMessageBox.information(self, tr("Schriften"), tr("Bitte zuerst eine nicht eingebettete Schrift in der "
                                                             "Liste markieren."))
            return
        i = cb.findData(what)
        if i >= 0:
            cb.setCurrentIndex(i)
        self._font_choice(cb)

    def _font_choice(self, cb):
        try:
            self._font_choice_inner(cb)
        except Exception as e:
            box = QMessageBox(QMessageBox.Icon.Critical, tr("Fehler"), str(e), parent=self)
            box.setDetailedText(traceback.format_exc())
            box.exec()

    def _font_choice_inner(self, cb):
        name = cb.property("font")
        what = cb.currentData()
        if what == "__file__":
            p, _ = QFileDialog.getOpenFileName(self, tr("Schriftdatei wählen"), "", tr("Schriften (*.ttf *.otf *.TTF *.OTF)"))
            cb.setCurrentIndex(0)
            if p:
                cb.setItemText(0, os.path.basename(p))
                cb.setItemData(0, p)
                self.font_map[name] = p
        elif what == "__download__":
            cb.setCurrentIndex(0)
            alt = preflight.free_alternative(name)
            text = tr("Name der Schrift (fontsource.org, freie Lizenzen), z. B. „Roboto“:")
            if alt:
                text = tr("„{0}“ ist eine kommerzielle Schrift und kann nicht frei heruntergeladen werden.\n"
                          "Freie Alternative mit gleichen Zeichenbreiten: {1}").format(name, alt) + "\n\n" + text
            fam, ok = QInputDialog.getText(self, tr("Freie Schrift herunterladen"), text,
                                           QLineEdit.EchoMode.Normal, alt)
            while ok and fam.strip():
                QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                try:
                    paths, used = preflight.download_font(fam.strip())
                except preflight.FontNotFound as e:
                    QApplication.restoreOverrideCursor()
                    if e.suggestions:
                        fam, ok = QInputDialog.getItem(self, tr("Freie Schrift herunterladen"), str(e) + "\n\n"
                                                       + tr("Stattdessen laden:"), e.suggestions, 0, False)
                        continue
                    QMessageBox.warning(self, tr("Herunterladen"), str(e))
                    return
                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    QMessageBox.warning(self, tr("Herunterladen"), str(e))
                    return
                QApplication.restoreOverrideCursor()
                _fam, bold, italic = preflight._norm(name)
                pick = next((p for p in paths if ("700" in p) == bold and ("italic" in p) == italic), paths[0])
                cb.setItemText(0, f"{used} ({os.path.basename(pick)})")
                cb.setItemData(0, pick)
                self.font_map[name] = pick
                return
        elif what:
            self.font_map[name] = what

    def _no_substitute_ok(self) -> bool:
        if not self.rep:
            return True
        names = [f.name for f in self.rep.fonts if f.status == "missing" and f.name not in self.font_map]
        if not names:
            return True
        return QMessageBox.question(
            self, tr("Schriften einbetten"),
            tr("Für diese Schriften ist kein Ersatz gewählt – Ghostscript nimmt dann eine eigene Standardschrift, "
               "das Schriftbild ändert sich:\n{0}\n\nTrotzdem einbetten?").format("\n".join("• " + n for n in names))
        ) == QMessageBox.StandardButton.Yes

    def _embed(self):
        if not self._no_substitute_ok():
            return
        mp = dict(self.font_map)
        self._run(lambda d: preflight.embed_fonts(d, mp), tr("_Schriften"),
                  [tr("Schriften eingebettet ({0} ersetzt).").format(len(mp))])

    def _fix_all(self):
        if not self.rep:
            return
        steps, notes = [], []
        hidden = [L for L in self.rep.layers if not L.view_on or L.print_on is False]
        if hidden:
            st = self._layer_states()
            basis = self._ask_basis(st)
            if basis is None:
                return
            vis = {k for k, (v, p) in st.items() if (p if basis == "print" else v)}
            steps.append(lambda d: preflight.flatten_layers(d, vis))
            notes.append(tr("Ebenen festgeschrieben ({0}).").format(
                tr("wie beim Druck") if basis == "print" else tr("wie am Bildschirm")))
        missing = [f for f in self.rep.fonts if f.status == "missing"]
        if missing and not self._no_substitute_ok():
            return
        if missing:
            mp = dict(self.font_map)
            steps.append(lambda d: preflight.embed_fonts(d, mp))
            notes.append(tr("Schriften eingebettet."))
        if not steps:
            QMessageBox.information(self, tr("Prüfung"), tr("Keine automatischen Reparaturen nötig."))
            return

        def chain(d):
            for s in steps:
                d = s(d)
            return d
        self._run(chain, tr("_repariert"), notes)

    def _run(self, fn, suffix, notes):
        if self.data_fn is None or (self._worker is not None and self._worker.isRunning()):
            return
        data = self.data_fn()
        self.set_busy(tr("Repariere …"))
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self._worker = _Worker(fn, data)

        def done(res, err):
            QApplication.restoreOverrideCursor()
            if err:
                box = QMessageBox(QMessageBox.Icon.Critical, tr("Fehler"), err.split("\n\n")[0], parent=self)
                box.setDetailedText(err)
                box.exec()
                if self.rep:
                    self.set_report(self.rep)
                return
            if self.rep:
                self.set_report(self.rep)
            self.result_ready.emit(res, suffix, notes)
        self._worker.done.connect(done)
        self._worker.start()

    def _save_report(self):
        if not self.rep:
            return
        p, _ = QFileDialog.getSaveFileName(self, tr("Prüfbericht speichern"), tr("Pruefbericht.txt"),
                                           tr("Textdateien (*.txt)"))
        if p:
            with open(p, "w", encoding="utf-8") as f:
                f.write(preflight.report_text(self.rep, getattr(self.window(), "display_name", "")))
