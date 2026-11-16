# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Main window: soft proof, colour check, papers and profiles, output for the print shop, colour actions and the pipette."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDockWidget,
    QMessageBox,
)

from ..l10n import tr
from .common import responsive, responsive_panel


class MainColourMixin:
    """Colour functions of MainWindow."""

    def _toggle_proof(self, on: bool):
        from .softproofdialog import build_spec, load_saved

        spec = build_spec(self.session.cfg, load_saved()) if on else None
        if on and spec is None:
            self.softproof_dialog()  # nothing chosen yet (or the profile is gone): set up
            return
        self._apply_proof(spec)

    def _apply_proof(self, spec):
        from .. import proof

        self.view.set_proof(spec)
        self.lbl_proof.setText(proof.describe_spec(spec))
        self.lbl_proof.setVisible(bool(spec))
        if bool(spec) != self.a_proof.isChecked():
            self.a_proof.blockSignals(True)
            self.a_proof.setChecked(bool(spec))
            self.a_proof.blockSignals(False)

    def softproof_dialog(self):
        """Open the dialog for setting up the soft proof."""
        from .softproofdialog import SoftproofDialog, build_spec, load_saved

        dlg = getattr(self, "_proof_dlg", None)
        if dlg is None:
            dlg = SoftproofDialog(self, self.session.cfg)
            responsive(dlg)  # not modal (show instead of exec): adapt ourselves
            dlg.changed.connect(self._apply_proof)
            self._proof_dlg = dlg
        dlg.show()
        dlg.raise_()
        spec = build_spec(self.session.cfg, load_saved())
        if spec:
            self._apply_proof(spec)
        else:
            self._apply_proof(None)

    def _proof_for_choice(self, choice):
        """Colour check → soft proof: show this printing condition in the soft proof."""
        from .softproofdialog import build_spec, load_saved, save

        saved = dict(load_saved(), key=choice["key"])
        save(saved)
        self._proof_dlg = None  # read the selection anew
        spec = build_spec(self.session.cfg, saved)
        if spec:
            self._apply_proof(spec)

    def _build_color(self, pages_dock):
        from .colorpanel import ColorPanel

        self.color_panel = ColorPanel(self)
        responsive_panel(self.color_panel)
        self.color_panel.data_fn = lambda: self._doc_bytes() if self.doc is not None else None
        self.color_panel.cfg_fn = lambda: self.session.cfg
        self.color_panel.goto_spot.connect(lambda p, box: self.view.show_spot(p - 1, box))
        self.color_panel.action_requested.connect(self._color_action)
        self.color_panel.proof_requested.connect(self._proof_for_choice)
        self.color_dock = QDockWidget(tr("Farbe"), self)
        self.color_dock.setWidget(self._dock_scroll(self.color_panel))
        self.color_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable | QDockWidget.DockWidgetFeature.DockWidgetMovable
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.color_dock)
        self.tabifyDockWidget(pages_dock, self.color_dock)
        self.color_dock.hide()

    def color_check(self):
        """Show the colour panel and start the colour check."""
        if self.doc is None:
            return
        self.color_panel.reload_choices()
        self.color_dock.show()
        self.color_dock.raise_()
        self.color_panel.start()

    def _color_refresh(self):
        """Papers/profiles changed: read the selection in colour check and soft proof anew."""
        from .. import colorlab

        colorlab._WHITE_CACHE.clear()
        self._proof_dlg = None
        if hasattr(self, "color_panel"):
            self.color_panel.reload_choices()
            if self.color_dock.isVisible() and self.color_panel.facts is not None:
                self.color_panel.start()

    def materials_dialog(self, select: str = "", measure: bool = False):
        """Open "Papiere und Messungen"."""
        from .materialsdialog import MaterialsDialog

        dlg = MaterialsDialog(self, self.session.cfg, select, measure)
        dlg.changed.connect(self._color_refresh)
        dlg.exec()

    def standard_profiles(self, surface: str = ""):
        """Open the dialog for downloading standard profiles."""
        from .materialsdialog import StandardProfilesDialog

        dlg = StandardProfilesDialog(self, surface)
        dlg.exec()
        if dlg.fetched:
            self._color_refresh()

    def _color_help(self):
        from .materialsdialog import show_help

        show_help(self)

    def press_dialog(self):
        """Open the wizard "Für Druckerei ausgeben"."""
        if self.doc is None:
            return
        from .colorpanel import load_choice
        from .pressdialog import PressDialog

        ch = load_choice()
        base = os.path.splitext(self.display_name or tr("Dokument"))[0]
        folder = (
            os.path.dirname(self.path) if self.path else (getattr(self, "_suggest_dir", "") or os.path.expanduser("~"))
        )
        dlg = PressDialog(
            self,
            self._doc_bytes,
            self.session.cfg,
            os.path.join(folder, base + tr("_Druck") + ".pdf"),
            ch.get("key", ""),
            ch.get("intent", ""),
            int(ch.get("tac", 0) or 0),
        )
        dlg.open_result.connect(lambda path: self.ctl.open_paths([path], tab_of=self))
        dlg.exec()

    def _ask_rgb(self, target_name: str) -> str:
        """Always ask about RGB: "convert" | "keep" | "" (cancelled)."""
        box = QMessageBox(
            QMessageBox.Icon.Question,
            tr("RGB im Dokument"),
            tr(
                "Die Datei enthält RGB. Nach „{0}“ umwandeln oder RGB mit Profil weitergeben (die Druckerei rechnet "
                "um)?"
            ).format(target_name),
            parent=self,
        )
        b_conv = box.addButton(tr("Umwandeln"), QMessageBox.ButtonRole.AcceptRole)
        b_keep = box.addButton(tr("Mit Profil weitergeben"), QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        return "convert" if box.clickedButton() is b_conv else "keep" if box.clickedButton() is b_keep else ""

    def _color_action(self, kind: str, p: dict):
        from .. import colorlab, core, pressexport

        p = p or {}
        if kind == "press":
            self.press_dialog()
        elif kind in ("convert", "embed_oi"):
            if self.doc is None or not p.get("target"):
                return
            rgb = "convert"
            if p.get("has_rgb"):
                rgb = self._ask_rgb(colorlab.profile_desc(p["target"]))
                if not rgb:
                    return
            s = pressexport.PressSettings(
                target=p["target"],
                intent=p.get("intent") or "relative",
                cmyk_mode=p.get("cmyk_mode") or "rgb_only" if kind == "convert" else "none",
                source=p.get("source") or "",
                rgb=rgb,
                tac_limit=int(p.get("tac_limit") or 0),
                material=p.get("material") or "",
            )
            self.start_job("press", core.settings_to_dict(s), suffix=tr("_Druck"), title=tr("Farbe"))
        elif kind == "preflight":
            self.pf_dock.show()
            self.pf_dock.raise_()
            self._pf_start(force=True)
        elif kind == "measure":
            mid = p.get("material") or ""
            m = colorlab.material_by_id(self.session.cfg, mid) if mid else None
            if m is not None and m.get("scope") == "admin":
                if (
                    QMessageBox.question(
                        self,
                        tr("Papier messen"),
                        tr(
                            "„{0}“ ist ein Papier der Verwaltung (für alle). Als eigenes Papier übernehmen und messen? "
                            "Ändern für alle geht unter Verwaltung → Standardeinstellungen → Materialien."
                        ).format(m.get("name") or mid),
                    )
                    != QMessageBox.StandardButton.Yes
                ):
                    return
                from .. import usercolor

                mats = usercolor.load_materials()
                n = {k: v for k, v in m.items() if k in usercolor.FIELDS}
                n["id"] = usercolor.new_id(m.get("name") or mid, {x["id"] for x in mats})
                mats.append(n)
                try:
                    usercolor.save_materials(mats)
                except (OSError, ValueError) as e:
                    QMessageBox.warning(self, tr("Papiere"), str(e))
                    return
                mid = n["id"]
            self.materials_dialog(mid, measure=bool(mid))
        elif kind == "get_profiles":
            self.standard_profiles(p.get("surface") or "")
        elif kind == "choose_target":
            self.color_panel.focus_choice()

    def _pipette_mode(self, on: bool):
        if on:
            if self.a_measure.isChecked():
                self.a_measure.setChecked(False)
            if getattr(self, "pipette_dlg", None) is None:
                from .pipettedialog import PipetteDialog

                self.pipette_dlg = PipetteDialog(self)
                self.pipette_dlg.picked.connect(self._pipette_picked)
                self.pipette_dlg.closed.connect(lambda: self.a_pipette.setChecked(False))
            self.view.on_pipette = self.pipette_dlg.measure
            self.view.on_pipette_exit = lambda: self.a_pipette.setChecked(False)
            self.view.imode = "pipette"
            self.view.sel = None
            self.pipette_dlg.show()
            self.pipette_dlg.raise_()
            self.statusBar().showMessage(tr("Farbpipette: auf die Seite klicken · Esc = beenden"), 6000)
        else:
            if self.view.imode == "pipette":
                self.view.imode = "edit" if self.a_edit.isChecked() else "text"
            dlg = getattr(self, "pipette_dlg", None)
            if dlg is not None and dlg.isVisible():
                dlg.blockSignals(True)
                dlg.hide()
                dlg.blockSignals(False)

    def _pipette_picked(self, kind: str, vals):
        self.edit_panel._last_color = (kind, tuple(vals))
        self.statusBar().showMessage(tr("Farbe übernommen – Bearbeiten → „Farbe …“ verwendet sie."), 5000)
