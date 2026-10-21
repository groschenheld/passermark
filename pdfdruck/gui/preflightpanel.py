# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Sidebar "Check": findings, fonts, layers, transparency – with repairs (result in a new window)."""
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
CAT_TEXT = {"font": "Schrift", "layer": "Ebene", "transparency": "Transparenz", "text": "Zeichen", "image": "Bild",
            "size": "Dateigröße"}
KIND_TEXT = {"smask": "weiche Maske", "blend": "Füllmethode", "alpha": "Deckkraft", "group": "Transparenzgruppe",
             "overprint": "Überdrucken", "image_alpha": "Bild mit Transparenz",
             "pattern_smask": "Verlauf mit Soft-Maske"}


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
    """Show the check result and repair. Signals: open result, jump to page, recheck."""
    result_ready = Signal(bytes, str, list)      # PDF-Bytes, Namenszusatz, Hinweise
    goto_page = Signal(int)
    goto_spot = Signal(int, object)               # Seite (1-basiert), Bereich (x0, y0, x1, y1) pt oder None
    job_requested = Signal(str, object, str, str)  # Art, Einstellungen, Namenszusatz, Titel (eigener Prozess)
    recheck = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rep: preflight.Report | None = None
        self.data_fn = None                       # liefert die aktuellen Dokument-Bytes
        self.file_fn = None                       # Datei wie auf der Platte (Größe/Verkleinern), sonst data_fn
        self._job_data = None
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
        self.tree.setRootIsDecorated(True)
        self.tree.itemClicked.connect(self._issue_clicked)
        self.tree.currentItemChanged.connect(lambda cur, _prev: self._update_nav())
        self.tree.setToolTip(tr("Klick: zur Fundstelle springen · ▸ aufklappen: alle Fundstellen"))
        lv.addWidget(self.tree, 1)
        nav = QHBoxLayout()
        self.btn_prev = QPushButton("◀")
        self.btn_next = QPushButton("▶")
        for b, d in ((self.btn_prev, -1), (self.btn_next, +1)):
            b.setFixedWidth(36)
            b.clicked.connect(lambda _c=False, d=d: self._step_spot(d))
        self.lbl_nav = QLabel("")
        self.lbl_nav.setStyleSheet(f"color: {theme.MUTED};")
        nav.addWidget(self.btn_prev)
        nav.addWidget(self.btn_next)
        nav.addWidget(self.lbl_nav, 1)
        lv.addLayout(nav)
        self._update_nav()
        self.btn_fix_all = QPushButton(tr("Empfohlene Reparaturen …"))
        self.btn_fix_all.setToolTip(tr("Ebenen festschreiben (falls ausgeblendete vorhanden) und fehlende Schriften "
                                       "mit Ersatz einbetten – Ergebnis im neuen Fenster"))
        self.btn_fix_all.clicked.connect(self._fix_all)
        lv.addWidget(self.btn_fix_all)
        self.btn_hdr = QPushButton(tr("HDR-Zusatzseiten entfernen …"))
        self.btn_hdr.setToolTip(tr("Graue Helligkeitskarten von Handy-HDR-Fotos entfernen – eine Seite je Foto, "
                                   "Größe wählbar"))
        self.btn_hdr.clicked.connect(self._fix_hdr)
        self.btn_hdr.hide()
        lv.addWidget(self.btn_hdr)
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
        b = QPushButton(tr("Transparente Verläufe in Bilder umwandeln (300 dpi)"))
        b.setToolTip(tr("Gegen schwarze Flächen am RIP/Plotter: nur Verläufe mit Soft-Maske werden samt Untergrund "
                        "als deckendes Bild gerendert – Text und Vektoren darüber bleiben erhalten. Ohne Ghostscript."))
        b.clicked.connect(self._flatten_softmask)
        lv.addWidget(b)
        self.tabs.addTab(w, tr("Transparenz"))
        # Bilder & Farben
        w = QWidget()
        lv = QVBoxLayout(w)
        self.lbl_colors = QLabel()
        self.lbl_colors.setWordWrap(True)
        self.lbl_colors.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lv.addWidget(self.lbl_colors)
        self.tbl_images = QTableWidget(0, 7)
        self.tbl_images.setHorizontalHeaderLabels([tr("Seite"), tr("Pixel"), tr("Platziert"), tr("Auflösung"),
                                                   tr("Farbraum / Profil"), tr("max. 300 dpi"), tr("max. 150 dpi")])
        self.tbl_images.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.tbl_images.verticalHeader().setVisible(False)
        self.tbl_images.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_images.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl_images.setSortingEnabled(True)
        self.tbl_images.setToolTip(tr("Auflösung = Pixel im Verhältnis zur platzierten Größe auf der Seite. "
                                      "Grün ab 300 dpi, gelb 150–299 dpi (Plakat/Großformat), rot darunter. "
                                      "Doppelklick springt zur Seite."))
        self.tbl_images.cellDoubleClicked.connect(
            lambda r, _c: self.goto_page.emit(int(self.tbl_images.item(r, 0).data(Qt.ItemDataRole.UserRole) or 1)))
        lv.addWidget(self.tbl_images, 1)
        self.tabs.addTab(w, tr("Bilder & Farben").replace("&", "&&"))      # & sonst Tastenkürzel
        # Dateigröße
        w = QWidget()
        lv = QVBoxLayout(w)
        self.lbl_size = QLabel()
        self.lbl_size.setWordWrap(True)
        self.lbl_size.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.lbl_size.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lv.addWidget(self.lbl_size, 1)
        b = QPushButton(tr("Datei verkleinern …"))
        b.setToolTip(tr("Verlustfrei verkleinern, optional Auflösung reduzieren – jede Maßnahme einzeln wählbar"))
        b.clicked.connect(self.shrink)
        lv.addWidget(b)
        self.tabs.addTab(w, tr("Dateigröße"))

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
            spots = list(getattr(i, "spots", None) or [preflight.Spot(p) for p in i.pages])
            it = QTreeWidgetItem([tr(SEV_TEXT[i.severity]) + " · " + tr(CAT_TEXT[i.category]), i.message,
                                  preflight._pages_str(i.pages)])
            it.setForeground(0, QBrush(QColor(col[i.severity])))
            it.setData(0, Qt.ItemDataRole.UserRole, spots)
            it.setData(1, Qt.ItemDataRole.UserRole, 0)            # aktuelle Fundstelle (für ◀ ▶)
            it.setToolTip(1, i.message)
            self.tree.addTopLevelItem(it)
            if len(spots) > 1 or (spots and (spots[0].box is not None or spots[0].label)):
                for k, sp in enumerate(spots[:500]):
                    ch = QTreeWidgetItem(["", preflight.where_text(rep, sp), str(sp.page)])
                    ch.setData(0, Qt.ItemDataRole.UserRole, [sp])
                    ch.setData(1, Qt.ItemDataRole.UserRole, k)
                    ch.setToolTip(1, preflight.where_text(rep, sp))
                    it.addChild(ch)
        self.tree.resizeColumnToContents(0)
        self.btn_hdr.setVisible(bool(getattr(rep, "hdr", None)))
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
        self._fill_colors(rep)
        if rep.size is not None:
            from .. import shrink
            self.lbl_size.setText("\n".join(shrink.summary_lines(rep.size, top=8)))
        else:
            self.lbl_size.setText("")

    def shrink(self):
        """Dialog mit Aufschlüsselung und Häkchen; läuft als eigener Prozess (große Dateien)."""
        from .shrinkdialog import ShrinkDialog
        fn = self.file_fn or self.data_fn
        if fn is None:
            return
        data = fn()
        rep = self.rep.size if self.rep is not None and self.rep.size is not None \
            and self.rep.size.size == len(data) else None
        dlg = ShrinkDialog(self, rep, data)
        if dlg.exec():
            self._job_data = data
            self.job_requested.emit("shrink", dlg.options(), tr("_klein"), tr("Datei verkleinern"))
            self._job_data = None

    def take_job_data(self):
        """Für den Auftrag: genau die Bytes, die der Dialog analysiert hat."""
        return self._job_data

    def _fill_colors(self, rep):
        """Reiter „Bilder & Farben“: Farbräume je Seite, Ausgabeprofil, Seitenlimits und Bildtabelle."""
        from .. import imagecheck as ic
        cr = getattr(rep, "colors", None)
        self.tbl_images.setSortingEnabled(False)
        self.tbl_images.setRowCount(0)
        if cr is None:
            self.lbl_colors.setText(tr("Keine Angaben."))
            return
        lines = preflight.colors_text(rep)
        lim = ic.page_limits(cr)
        for p in sorted(lim)[:30]:
            dpi, f300, f150 = lim[p]
            ps = cr.page_size_mm.get(p, (0, 0))
            if f300 < 0.995:
                lines.append(tr("Seite {0}: niedrigste Bildauflösung {1:.0f} dpi – höchstens {2:.0f} % ({3:.0f} × {4:.0f} mm) "
                                "bei 300 dpi, {5:.0f} % ({6:.0f} × {7:.0f} mm) bei 150 dpi").format(
                    p, dpi, f300 * 100, ps[0] * f300, ps[1] * f300, min(f150, 9.99) * 100,
                    ps[0] * min(f150, 9.99), ps[1] * min(f150, 9.99)))
            else:
                lines.append(tr("Seite {0}: niedrigste Bildauflösung {1:.0f} dpi – in Originalgröße gut; für "
                                "Plakat/Großformat (150 dpi) bis {2:.0f} % vergrößerbar").format(p, dpi, min(f150, 9.99) * 100))
        if not cr.images:
            lines.append(tr("Keine Bilder."))
        if cr.truncated:
            lines.append(tr("(Nur die ersten {0} Bildplatzierungen ausgewertet.)").format(len(cr.images)))
        self.lbl_colors.setText("\n".join(lines))
        col = {"good": QColor("#3fa34d"), "ok": QColor(theme.ACCENT), "low": QColor(theme.ERROR)}

        self.tbl_images.setRowCount(len(cr.images))
        for r, u in enumerate(cr.images):
            a, b = u.max_mm(u.good), u.max_mm(u.ok)
            pg = QTableWidgetItem()
            pg.setData(Qt.ItemDataRole.DisplayRole, u.page)
            pg.setData(Qt.ItemDataRole.UserRole, u.page)
            self.tbl_images.setItem(r, 0, pg)
            self.tbl_images.setItem(r, 1, QTableWidgetItem(f"{u.px[0]} × {u.px[1]}"))
            self.tbl_images.setItem(r, 2, QTableWidgetItem(f"{u.placed_mm[0]:.0f} × {u.placed_mm[1]:.0f} mm"))
            d = QTableWidgetItem()
            d.setData(Qt.ItemDataRole.DisplayRole, round(u.dpi))
            if u.rating in col:
                d.setForeground(QBrush(col[u.rating]))
            if u.bits == 1:
                d.setToolTip(tr("Strichbild (1 Bit): gut ab 600 dpi, ausreichend ab 300 dpi"))
            self.tbl_images.setItem(r, 3, d)
            sp = ic.space_label(u.space) + (f" – {u.profile}" if u.profile else "") + f"  ·  {u.codec}"
            it = QTableWidgetItem(sp)
            it.setToolTip(sp)
            self.tbl_images.setItem(r, 4, it)
            self.tbl_images.setItem(r, 5, QTableWidgetItem(f"{a[0]:.0f} × {a[1]:.0f} mm"))
            self.tbl_images.setItem(r, 6, QTableWidgetItem(f"{b[0]:.0f} × {b[1]:.0f} mm"))
        self.tbl_images.setSortingEnabled(True)
        self.tbl_images.resizeColumnsToContents()

    # ------------------------------------------------------------------ #
    def _issue_clicked(self, it, _col):
        """Befund: zur (aktuellen) Fundstelle springen; Fundstelle (Unterpunkt): genau dorthin."""
        spots = it.data(0, Qt.ItemDataRole.UserRole) or []
        if not spots:
            return
        parent = it.parent()
        if parent is not None:                         # Unterpunkt: als aktuelle Fundstelle des Befunds merken
            parent.setData(1, Qt.ItemDataRole.UserRole, int(it.data(1, Qt.ItemDataRole.UserRole) or 0))
            self._go(spots[0])
        else:
            k = int(it.data(1, Qt.ItemDataRole.UserRole) or 0)
            self._go(spots[min(k, len(spots) - 1)])
        self._update_nav()

    def _go(self, sp):
        self.goto_spot.emit(int(sp.page), sp.box)

    def _top(self):
        it = self.tree.currentItem()
        return it.parent() or it if it is not None else None

    def _step_spot(self, d: int):
        top = self._top()
        if top is None:
            return
        spots = top.data(0, Qt.ItemDataRole.UserRole) or []
        if not spots:
            return
        k = (int(top.data(1, Qt.ItemDataRole.UserRole) or 0) + d) % len(spots)
        top.setData(1, Qt.ItemDataRole.UserRole, k)
        if k < top.childCount():
            self.tree.blockSignals(True)
            self.tree.setCurrentItem(top.child(k))
            self.tree.blockSignals(False)
        self._go(spots[k])
        self._update_nav()

    def _update_nav(self):
        top = self._top()
        spots = (top.data(0, Qt.ItemDataRole.UserRole) or []) if top is not None else []
        many = len(spots) > 1
        self.btn_prev.setEnabled(many)
        self.btn_next.setEnabled(many)
        if not spots:
            self.lbl_nav.setText(tr("Befund anklicken – springt zur Stelle"))
        else:
            k = int(top.data(1, Qt.ItemDataRole.UserRole) or 0)
            self.lbl_nav.setText(tr("Fundstelle {0}/{1}").format(min(k, len(spots) - 1) + 1, len(spots)))

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
        """Buttons below the table: act on the highlighted row."""
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
        if getattr(self.rep, "hdr", None):
            steps.append(lambda d: preflight.remove_hdr_aux(d, "aux", False))
            notes.append(tr("{0} HDR-Zusatzseite(n) entfernt.").format(len(self.rep.hdr)))
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

    def _fix_hdr(self):
        if not self.rep or not self.rep.hdr:
            return
        from .hdrdialog import hdr_options
        pages = ", ".join(str(h["aux"] + 1) for h in self.rep.hdr[:6]) + (" …" if len(self.rep.hdr) > 6 else "")
        opts = hdr_options(self, self.rep.hdr, tr("Das Dokument (Seite {0})").format(pages))
        if opts is None:
            return
        n = len(self.rep.hdr)
        self._run(lambda d: preflight.remove_hdr_aux(d, opts["size"], opts["merge"]), tr("_ohneHDR"),
                  [tr("{0} HDR-Zusatzseite(n) entfernt.").format(n)])

    def _flatten_softmask(self):
        """Läuft als eigener Prozess (pdfium rendert – nicht im Hintergrund-Thread der Oberfläche)."""
        from ..core import PreflightFixSettings
        self.job_requested.emit("preflight_fix", PreflightFixSettings(fix="flatten_softmask", dpi=300),
                                tr("_Verlaeufe"), tr("Verläufe umwandeln"))

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
