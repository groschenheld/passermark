# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Main window: the actions, the menus and the main toolbar."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QToolButton,
)

from ..l10n import tr
from .icons import icon as svg_icon
from .pagewidgets import PageEdit
from .viewlayout import ZOOM_STEPS


class MainActionsMixin:
    """Actions, menus and toolbar of MainWindow."""

    # ================================================================ #
    # actions / menus / toolbar
    # ================================================================ #
    def _act(self, text, slot, shortcut=None, icon=None):
        if isinstance(icon, str):
            a = QAction(svg_icon(icon), text, self)
        elif icon is not None:
            a = QAction(self.style().standardIcon(icon), text, self)
        else:
            a = QAction(text, self)
        a.triggered.connect(slot)
        if shortcut:
            seq = shortcut if isinstance(shortcut, list) else [shortcut]
            a.setShortcuts([QKeySequence(k) for k in seq])
        self.addAction(a)
        return a

    def _build_actions(self, dock):
        """Create all actions, then the menu bar and the main toolbar."""
        A = self._act
        self._create_actions()
        mb = self.menuBar()
        self._menu_file(mb)
        self._menu_pages(mb)
        self._menu_document(mb)
        self._menu_manipulation(mb)
        self._menu_colour(mb)
        self._menu_plan(mb)
        self._menu_view(mb, dock)
        self._menu_admin_and_help(mb)
        self._build_main_toolbar(dock)
        A(tr("Erste Seite"), lambda: self.view.goto(0), "Home")
        A(tr("Letzte Seite"), lambda: self.view.goto(len(self.view.pages) - 1), "End")
        self._update_actions()

    def _create_actions(self):
        """Create the actions that are used in more than one place (menus, toolbars, context menus)."""
        A = self._act
        self.a_open = A(tr("Öffnen…"), self.open_dialog, QKeySequence.StandardKey.Open, "open")
        self.a_newwin = A(tr("Neues Fenster"), lambda: self.ctl.new_window(), "Ctrl+N")
        self.a_newtab = A(tr("Neuer Reiter"), lambda: self._new_tab(), "Ctrl+Shift+N")
        self.a_detach = A(tr("Reiter in eigenes Fenster lösen"), self._detach, None)
        self.a_save = A(tr("Speichern"), self.save, QKeySequence.StandardKey.Save, "save")
        self.a_saveas = A(tr("Speichern unter…"), self.save_as, "Ctrl+Shift+S")
        self.a_merge = A(tr("Dokumente zusammenführen…"), self.merge_dialog, "Ctrl+M", "merge")
        self.a_print = A(tr("Drucken…"), self.print_dialog, QKeySequence.StandardKey.Print, "print")
        self.a_repair = A(tr("Reparieren, optimieren, Passwort…"), self.repair_dialog, "Ctrl+Shift+R", "repair")
        self.a_shrink = A(tr("Datei verkleinern …"), self.shrink_dialog, None, "repair")
        self.a_close = A(tr("Schließen"), self.close, QKeySequence.StandardKey.Close)
        self.a_props = A(tr("Eigenschaften …"), self.properties_dialog, "Ctrl+D", "info")
        self.a_copy = A(tr("Markierten Text kopieren"), self.copy_text, QKeySequence.StandardKey.Copy, "copy")
        self.a_seltext = A(tr("Text der Seite markieren"), lambda: self.view.select_page_text(), "Ctrl+Alt+A", "select")
        self.a_settings = A(tr("Einstellungen …"), self.settings_dialog, "Ctrl+,", "settings")
        self.a_manip = A(
            tr("CMYK und Beschneiden in einem Schritt …"), lambda: self.manip_dialog("all"), "Ctrl+Shift+M", "cmyk"
        )
        self.a_manip_cmyk = A(tr("CMYK-Umwandlung …"), lambda: self.manip_dialog("cmyk"), None, "cmyk")
        self.a_manip_crop = A(tr("Auf Format beschneiden …"), lambda: self.manip_dialog("crop"), None, "crop")
        self.a_separate = A(
            tr("Objekte trennen (Einzelseiten ohne Weißraum) …"), self.separate_dialog, None, "separate"
        )
        self.a_cut = A(tr("CutContour erzeugen (Schneideplotter) …"), self.cut_dialog, None, "cut")
        self.a_vdp = A(tr("Variable Daten (Nummern, QR-/Barcodes, CSV) …"), self.vdp_dialog, "Ctrl+Shift+D", "vdp")
        self.a_data = A(
            tr("Daten erfassen (Tabelle für Visitenkarten, WLAN, Codes …) …"), self.data_dialog, None, "table"
        )
        self.a_edit = A(tr("Text und Ebenen bearbeiten"), lambda: None, "Ctrl+T", "edit")
        self.a_edit.setCheckable(True)
        self.a_edit.toggled.connect(self._edit_mode)

        self.a_ins_before = A(tr("Seiten einfügen – vor Auswahl…"), lambda: self.insert_dialog("before"))
        self.a_ins_after = A(
            tr("Seiten einfügen – nach Auswahl…"), lambda: self.insert_dialog("after"), "Ctrl+I", "insert"
        )
        self.a_ins_end = A(tr("Seiten anhängen (am Ende)…"), lambda: self.insert_dialog("end"), "Ctrl+Shift+I")
        self.a_blank_before = A(tr("Leerseite einfügen – vor Auswahl"), lambda: self.insert_blank("before"))
        self.a_blank_after = A(
            tr("Leerseite einfügen – nach Auswahl"), lambda: self.insert_blank("after"), "Ctrl+Alt+I"
        )
        self.a_export = A(tr("Auswahl als ein PDF exportieren…"), self.export_selection, "Ctrl+E", "export")
        self.a_export_each = A(tr("Auswahl als einzelne PDFs exportieren…"), self.export_each, "Ctrl+Shift+E")
        self.a_delete = A(tr("Seiten löschen"), self.delete_pages, QKeySequence.StandardKey.Delete, "delete")
        self.a_split = A(tr("Seiten teilen (halbieren, Raster) …"), self.split_dialog, None, "split")
        self.a_split_spreads = A(
            tr("Doppelseiten teilen (falsch exportierte Broschüre)"), self.split_spreads, None, "split"
        )
        self.a_rot_l = A(tr("Seiten links drehen (dauerhaft)"), lambda: self.rotate_pages(-90), None, "rot_l")
        self.a_rot_r = A(tr("Seiten rechts drehen (dauerhaft)"), lambda: self.rotate_pages(90), None, "rot_r")
        self.a_up = A(tr("Seiten nach vorne verschieben"), lambda: self.move_pages(-1), "Alt+Up", "move_up")
        self.a_down = A(tr("Seiten nach hinten verschieben"), lambda: self.move_pages(1), "Alt+Down", "move_down")
        self.a_selall = A(tr("Alle Seiten auswählen"), lambda: self.thumbs.selectAll(), "Ctrl+Shift+A")

    def _menu_file(self, mb):
        """Menu "Datei"."""
        m = mb.addMenu(tr("&Datei"))
        for a in (
            self.a_open,
            self.a_newwin,
            self.a_newtab,
            self.a_detach,
            None,
            self.a_save,
            self.a_saveas,
            None,
            self.a_props,
            None,
            self.a_print,
            None,
            self.a_settings,
            None,
            self.a_close,
        ):
            m.addSeparator() if a is None else m.addAction(a)

    def _menu_pages(self, mb):
        """Menu "Seiten" (also used as the context menu of the page list)."""
        m = mb.addMenu(tr("&Seiten"))
        for a in (
            self.a_ins_before,
            self.a_ins_after,
            self.a_ins_end,
            self.a_blank_before,
            self.a_blank_after,
            None,
            self.a_export,
            self.a_export_each,
            None,
            self.a_rot_l,
            self.a_rot_r,
            self.a_up,
            self.a_down,
            None,
            self.a_split,
            self.a_split_spreads,
            None,
            self.a_delete,
            None,
            self.a_selall,
            None,
            self.a_copy,
            self.a_seltext,
        ):
            m.addSeparator() if a is None else m.addAction(a)
        self.page_menu = m

    def _menu_document(self, mb):
        """Menu "Dokument": merge, repair, shrink, document check."""
        A = self._act
        m = mb.addMenu(tr("D&okument"))
        m.addAction(self.a_merge)
        m.addAction(self.a_repair)
        m.addAction(self.a_shrink)
        m.addSeparator()
        self.a_preflight = A(
            tr("Dokumentprüfung (Preflight) …"),
            lambda: (self.pf_dock.show(), self.pf_dock.raise_(), self._pf_start(force=True)),
            "Ctrl+Shift+P",
            "check",
        )
        m.addAction(self.a_preflight)

    def _menu_manipulation(self, mb):
        """Menu "Dokument-Manipulation": editing, CMYK, cropping, objects, CutContour, variable data."""
        m = mb.addMenu(tr("Dokument-&Manipulation"))
        for a in (
            self.a_edit,
            None,
            self.a_manip_cmyk,
            self.a_manip_crop,
            None,
            self.a_manip,
            None,
            self.a_separate,
            self.a_cut,
            None,
            self.a_vdp,
            self.a_data,
        ):
            m.addSeparator() if a is None else m.addAction(a)

    def _menu_colour(self, mb):
        """Menu "Farbe": colour check, pipette, soft proof, output for the print shop, papers and profiles."""
        A = self._act
        m = mb.addMenu(tr("&Farbe"))
        self.a_proof = A(tr("Softproof (Druckfarben anzeigen)"), lambda: None, "Ctrl+Y", "proof")
        self.a_proof.setCheckable(True)
        self.a_proof.toggled.connect(self._toggle_proof)
        self.a_colorcheck = A(tr("Farbprüfung …"), self.color_check, "Ctrl+Shift+F", "check")
        self.a_colorcheck.setToolTip(tr("Dokument gegen eine Druckbedingung prüfen – mit Empfehlungen"))
        self.a_press = A(tr("Für Druckerei ausgeben …"), lambda: self.press_dialog(), None, "export")
        self.a_press.setToolTip(tr("Umwandeln, Output Intent einbetten, prüfen, speichern – optional als Paket"))
        self.a_pipette = A(tr("Farbpipette"), lambda: None, "Ctrl+Shift+C", "pipette")
        self.a_pipette.setCheckable(True)
        self.a_pipette.setToolTip(
            tr(
                "Farbe an einer Stelle messen: Werte im PDF, Farbauftrag im Druck je Kanal, "
                "Farbe übernehmen (Esc = beenden)"
            )
        )
        self.a_pipette.toggled.connect(self._pipette_mode)
        for a in (self.a_colorcheck, self.a_pipette, self.a_proof):
            m.addAction(a)
        m.addAction(A(tr("Softproof einrichten …"), self.softproof_dialog, "Ctrl+Shift+Y"))
        m.addSeparator()
        m.addAction(self.a_press)
        m.addAction(self.a_manip_cmyk)
        m.addSeparator()
        m.addAction(A(tr("Papiere und Messungen …"), lambda: self.materials_dialog(), None, "material"))
        m.addAction(A(tr("Standardprofile holen …"), lambda: self.standard_profiles(), None))
        m.addSeparator()
        m.addAction(A(tr("Farbmanagement kurz erklärt"), self._color_help, None, "info"))

    def _menu_plan(self, mb):
        """Menu "Plan & Poster": plan and poster printing, recent prints, rolls."""
        A = self._act
        m = mb.addMenu(tr("Pla&n && Poster"))
        self.a_plan = A(tr("Plandruck (Rollen, Laufmeter) …"), lambda: self.plan_dialog("plan"), "Ctrl+Alt+P", "plan")
        self.a_plan.setToolTip(tr("Pläne auf Rollendrucker: Außenlinien, Rollenwahl, Laufmeter, Reihenfolge"))
        self.a_rolls = A(tr("Rollen der Drucker …"), self.rolls_dialog, None, "roll")
        self.a_rolls.setToolTip(tr("Geladene Rollen vom Gerät lesen oder von Hand eintragen"))
        self.a_poster = A(
            tr("Posterdruck (Qualität, nebeneinander, Banner) …"), lambda: self.plan_dialog("poster"), None, "print"
        )
        self.a_poster.setToolTip(tr("Poster und Banner auf Rollen: nebeneinander, Überbreite, Saum, Ösen, Print & Cut"))
        m.addAction(self.a_plan)
        m.addAction(self.a_poster)
        self.m_plan_hist = m.addMenu(svg_icon("history"), tr("Letzte Drucke"))
        self.m_plan_hist.aboutToShow.connect(self._fill_plan_history)
        m.addSeparator()
        m.addAction(self.a_rolls)

    def _menu_view(self, mb, dock):
        """Menu "Ansicht": single page, rulers, measuring, trim size, soft proof, sidebar, zoom, rotation."""
        A = self._act
        m = mb.addMenu(tr("&Ansicht"))
        self.a_single = A(tr("Einzelseite (zur nächsten Seite springen)"), self._toggle_single, "Ctrl+4", "single")
        self.a_single.setCheckable(True)
        self.a_single.setChecked(self.view.single)
        m.addAction(self.a_single)
        m.addSeparator()
        self.a_rulers = A(tr("Lineale anzeigen"), lambda: None, "Ctrl+R", "ruler")
        self.a_rulers.setCheckable(True)
        self.a_rulers.toggled.connect(self._show_rulers)
        self.a_measure = A(tr("Messen"), lambda: None, "Ctrl+Shift+L", "measure")
        self.a_measure.setCheckable(True)
        self.a_measure.toggled.connect(self._measure_mode)
        self.a_boxes = A(tr("Endformat und Anschnitt anzeigen"), lambda: None, "Ctrl+Shift+B", "crop")
        self.a_boxes.setCheckable(True)
        from .. import l10n as _l10n

        self.a_boxes.setChecked(bool(_l10n.load_settings().get("show_trim", True)))
        self.view.show_boxes = self.a_boxes.isChecked()
        self.a_boxes.toggled.connect(self._show_boxes)
        m.addAction(self.a_rulers)
        m.addAction(self.a_measure)
        m.addAction(self.a_boxes)
        m.addSeparator()
        m.addAction(self.a_proof)
        m.addSeparator()
        m.addAction(dock.toggleViewAction())
        self.a_actual = A(tr("Tatsächliche Größe"), lambda: self.view.set_zoom("fixed", 1.0), "Ctrl+0", "actual")
        self.a_fitpage = A(tr("Ganze Seite"), lambda: self.view.set_zoom("page"), "Ctrl+1", "fit_page")
        self.a_fitwidth = A(tr("Seitenbreite"), lambda: self.view.set_zoom("width"), "Ctrl+2", "fit_width")
        for a in (self.a_fitpage, self.a_fitwidth, self.a_actual):
            m.addAction(a)
        m.addSeparator()
        self.a_vrot_l = A(tr("Ansicht links drehen"), lambda: self.rotate_view(-90), "Ctrl+Shift+-", "rot_l")
        self.a_vrot_r = A(tr("Ansicht rechts drehen"), lambda: self.rotate_view(90), "Ctrl+Shift++", "rot_r")
        m.addAction(self.a_vrot_l)
        m.addAction(self.a_vrot_r)

    def _menu_admin_and_help(self, mb):
        """Menus "Verwaltung" and "Hilfe"."""
        A = self._act
        m = mb.addMenu(tr("&Verwaltung"))
        m.addAction(A(tr("Standardeinstellungen (Admin)…"), self.admin_dialog, None, "settings"))
        m = mb.addMenu(tr("&Hilfe"))
        a = QAction(tr("Kommandozeile – Anleitung (PDF)"), self)
        a.triggered.connect(self._open_cli_howto)
        m.addAction(a)
        a = QAction(tr("Variable Daten – Anleitung (PDF)"), self)
        a.triggered.connect(self._open_vdp_howto)
        m.addAction(a)
        a = QAction(tr("Beispiele für Variable Daten holen …"), self)
        a.triggered.connect(self._get_examples)
        m.addAction(a)
        from .. import platform as _pl

        if _pl.IS_WIN:
            a = QAction(tr("Windows-Druck testen …"), self)
            a.triggered.connect(self._win_print_test)
            m.addAction(a)
        a = QAction(tr("Fehlerprotokolle öffnen"), self)
        a.triggered.connect(lambda: __import__("pdfdruck.gui.crashui", fromlist=["x"]).open_log_dir())
        m.addAction(a)
        a = QAction(tr("Lizenzen …"), self)
        a.setToolTip(tr("Lizenz von Passermark (GPL-3.0) und aller mitgelieferten Komponenten (Qt, Ghostscript, …)"))
        a.triggered.connect(self._open_licenses)
        m.addAction(a)

    def _build_main_toolbar(self, dock):
        """Main toolbar: open/save/print, sidebar, page navigation, view tools, zoom."""
        A = self._act
        dock_act = dock.toggleViewAction()
        dock_act.setIcon(svg_icon("sidebar"))
        dock_act.setText(tr("Seitenleiste"))
        tb = self.addToolBar(tr("Werkzeuge"))
        tb.setMovable(False)
        tb.setIconSize(QSize(20, 20))
        for a in (self.a_open, self.a_save, self.a_print):
            tb.addAction(a)
            btn = tb.widgetForAction(a)
            if isinstance(btn, QToolButton):  # the three main actions with text
                btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        tb.addSeparator()
        tb.addAction(dock_act)
        tb.addSeparator()
        tb.addAction(A(tr("Vorherige Seite"), lambda: self.view.goto(self.view.current - 1), None, "prev"))
        self.page_edit = PageEdit()
        self.page_edit.gotoRequested.connect(lambda p: self.view.goto(p))
        tb.addWidget(self.page_edit)
        tb.addAction(A(tr("Nächste Seite"), lambda: self.view.goto(self.view.current + 1), None, "next"))
        tb.addSeparator()
        # rulers/tape measure/trim size always available – not only in the workspace "Anzeigen"
        tb.addAction(self.a_rulers)
        tb.addAction(self.a_measure)
        tb.addAction(self.a_boxes)
        tb.addAction(self.a_proof)
        tb.addSeparator()
        tb.addAction(
            A(tr("Verkleinern"), lambda: self.view.step_zoom(1 / 1.2), QKeySequence.StandardKey.ZoomOut, "zoom_out")
        )
        self.zoom_combo = QComboBox()
        self.zoom_combo.setEditable(True)
        self.zoom_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.zoom_combo.setMinimumWidth(130)
        self.zoom_combo.addItem(tr("Seitenbreite"), "width")
        self.zoom_combo.addItem(tr("Ganze Seite"), "page")
        for z in ZOOM_STEPS:
            self.zoom_combo.addItem(f"{z * 100:.0f} %", z)
        self.zoom_combo.activated.connect(self._zoom_combo_activated)
        self.zoom_combo.lineEdit().returnPressed.connect(self._zoom_text_entered)
        tb.addWidget(self.zoom_combo)
        tb.addAction(
            A(
                tr("Vergrößern"),
                lambda: self.view.step_zoom(1.2),
                [QKeySequence.StandardKey.ZoomIn, "Ctrl+="],
                "zoom_in",
            )
        )
        tb.addSeparator()
        tb.addAction(self.a_fitpage)
        tb.addAction(self.a_fitwidth)
        tb.addAction(self.a_single)
        tb.addSeparator()
        tb.addAction(self.a_vrot_l)
        tb.addAction(self.a_vrot_r)

    def _toggle_single(self, checked=None):
        single = self.a_single.isChecked()
        self.ctl.view_single = single  # applies to new windows of this session
        self.view.set_single(single)
        self.view.setFocus()

    def _update_actions(self):
        has = self.doc is not None
        for a in (
            self.a_save,
            self.a_saveas,
            self.a_print,
            self.a_ins_before,
            self.a_ins_after,
            self.a_ins_end,
            self.a_blank_before,
            self.a_blank_after,
            self.a_export,
            self.a_export_each,
            self.a_delete,
            self.a_rot_l,
            self.a_rot_r,
            self.a_up,
            self.a_down,
            self.a_selall,
            self.a_manip,
            self.a_manip_cmyk,
            self.a_manip_crop,
            self.a_repair,
            self.a_separate,
            self.a_cut,
            self.a_edit,
            self.a_vdp,
            self.a_split,
            self.a_split_spreads,
        ):
            a.setEnabled(has)
        # save only when there is something to save (otherwise "nothing happens")
        self.a_save.setEnabled(has and (self.modified or not self.path))
        self.a_save.setToolTip(tr("Speichern") if self.a_save.isEnabled() else tr("Keine ungespeicherten Änderungen"))

    def _new_tab(self):
        if getattr(self, "_host", None) is None or not self.ctl.tabs_enabled():
            self.ctl.new_window()
            return
        self.ctl.new_window(tab_of=self)

    def _detach(self):
        host = getattr(self, "_host", None)
        if host is not None:
            host.detach(self)

    def _update_title(self):
        name = self.display_name or "Passermark"
        self.setWindowTitle(("● " if self.modified else "") + name + (tr(" – Passermark") if self.doc else ""))
        host = getattr(self, "_host", None)
        if host is not None:
            host.update_tab(self)
