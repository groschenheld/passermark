# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Main window: the document check in the background, the edit mode, rulers and measuring."""

from __future__ import annotations

import logging
import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDockWidget,
    QPushButton,
)

from ..l10n import tr
from . import theme
from .common import responsive

log = logging.getLogger(__name__)


class MainCheckMixin:
    """Document check, editing, rulers and measuring of MainWindow."""

    def _build_edit(self, pages_dock):
        from .editpanel import EditPanel

        self.edit_panel = EditPanel(self)

        class _Dock(QDockWidget):
            def closeEvent(dock_self, e):  # the close button ends edit mode
                self.a_edit.setChecked(False)
                e.accept()

        self.edit_dock = _Dock(tr("Bearbeiten"), self)
        self.edit_dock.setWidget(self._dock_scroll(self.edit_panel))
        self.edit_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable | QDockWidget.DockWidgetFeature.DockWidgetMovable
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.edit_dock)
        self.tabifyDockWidget(pages_dock, self.edit_dock)
        self.edit_dock.hide()
        pages_dock.raise_()
        self.edit_dock.visibilityChanged.connect(lambda vis: vis and self.edit_panel.refresh())
        self.view.edit_click = self.edit_panel.page_click
        self.view.editor = self.edit_panel
        self.view.pageChanged.connect(lambda _p: self.a_edit.isChecked() and self.edit_panel.refresh())

    def _show_rulers(self, on: bool):
        self._rulers_on = bool(on)
        for r in (self.ruler_corner, self.ruler_h, self.ruler_v):
            r.setVisible(on)
        if not on and self.a_measure.isChecked():
            self.a_measure.setChecked(False)
        self._rulers_update()

    def _rulers_update(self):
        if self._rulers_on:
            self.ruler_h.update()
            self.ruler_v.update()

    def _rulers_cursor(self, w, pos):
        if not self._rulers_on:
            return  # only compute when the rulers are visible
        gpos = w.mapToGlobal(pos.toPoint())
        self.ruler_h.cursor_px = gpos
        self.ruler_v.cursor_px = gpos
        self._rulers_update()

    def _show_boxes(self, on: bool):
        self.view.show_boxes = bool(on)
        for w in self.view.pages:
            w.update()
        from .. import l10n

        st = l10n.load_settings()
        if st.get("show_trim", True) != bool(on):
            st["show_trim"] = bool(on)
            try:
                l10n.save_settings(st)
            except OSError:
                pass

    def _measure_mode(self, on: bool):
        if on and self.a_pipette.isChecked():
            self.a_pipette.setChecked(False)
        if on:
            if self.a_edit.isChecked():
                self.a_edit.setChecked(False)  # Edit and Measure are mutually exclusive
            self.view.imode = "measure"
            self.view.sel = None
            if not self.a_rulers.isChecked():
                self.a_rulers.setChecked(True)
            self.statusBar().showMessage(
                tr("Messen: 1. Klick Anfang, 2. Klick Ende · Umschalt = waagrecht/senkrecht/45° · Esc = abbrechen"),
                8000,
            )
        else:
            if self.view.imode == "measure":
                self.view.imode = "text"
            self.view.measure_clear()

    def _edit_mode(self, on: bool):
        if on and self.a_measure.isChecked():
            self.a_measure.setChecked(False)
        if self.a_pipette.isChecked():
            self.a_pipette.setChecked(False)
        if on and self.edit_panel.rulers_wanted() and not self.a_rulers.isChecked():
            self.a_rulers.setChecked(True)  # rulers while editing (can be switched off in the Move section)
        if on:
            self._pages_dock.show()  # the edit panel sits next to the thumbnails
        self.view.imode = "edit" if on else "text"
        self.view.sel = None
        if on:
            self.edit_dock.show()
            self.edit_dock.raise_()
            self.edit_panel.refresh()
            self.statusBar().showMessage(tr("Bearbeiten-Modus: Textzeile bzw. Ebene auf der Seite anklicken."), 6000)
        else:
            self.view.overlay = {}
            self.edit_dock.hide()
            for w in self.view.pages:
                w.update()

    def _build_preflight(self, pages_dock):
        from .preflightpanel import PreflightPanel

        self.pf_panel = PreflightPanel(self)
        responsive(self.pf_panel)
        self.pf_panel.data_fn = self._doc_bytes
        self.pf_panel.file_fn = self._file_bytes
        self.pf_panel.result_ready.connect(self._pf_result)
        self.pf_panel.job_requested.connect(
            lambda kind, s, suffix, title: self.start_job(
                kind,
                s,
                suffix=suffix,
                title=title,
                src_data=self.pf_panel.take_job_data() if kind == "shrink" else None,
            )
        )
        self.pf_panel.goto_page.connect(lambda p: self.view.goto(p - 1))
        self.pf_panel.goto_spot.connect(lambda p, box: self.view.show_spot(p - 1, box))
        self.pf_panel.recheck.connect(lambda: self._pf_start(force=True))
        self.pf_dock = QDockWidget(tr("Prüfung"), self)
        self.pf_dock.setWidget(self._dock_scroll(self.pf_panel))
        self.pf_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable | QDockWidget.DockWidgetFeature.DockWidgetMovable
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.pf_dock)
        self.tabifyDockWidget(pages_dock, self.pf_dock)
        pages_dock.raise_()
        self.btn_pf = QPushButton("")
        self.btn_pf.setFlat(True)
        self.btn_pf.setToolTip(tr("Dokumentprüfung anzeigen"))
        self.btn_pf.clicked.connect(lambda: (self.pf_dock.show(), self.pf_dock.raise_()))
        self.btn_pf.setObjectName("pfChip")
        self.btn_pf.hide()
        self.statusBar().addWidget(self.btn_pf)  # far left (design: "Prüfung OK")
        self._pf_timer = QTimer(self, singleShot=True, interval=700, timeout=self._pf_start)
        self._pf_gen = 0
        self._pf_worker = None

    def _doc_bytes(self) -> bytes:
        import io

        buf = io.BytesIO()
        self.doc.save(buf)
        return buf.getvalue()

    def _file_bytes(self) -> bytes:
        """The file as on disk (opened unchanged, not encrypted) – otherwise the current state.
        For size/shrinking: pdfium re-saves and would otherwise blur what is really in the file.
        """
        p = self.path
        if p and not self.modified and p.lower().endswith(".pdf") and os.path.isfile(p):
            try:
                import pikepdf

                with pikepdf.open(p) as pdf:
                    enc = pdf.is_encrypted
                if not enc:
                    with open(p, "rb") as f:
                        return f.read()
            except Exception:  # noqa: BLE001 – optional module
                pass
        return self._doc_bytes()

    def _pf_start(self, force=False):
        from .. import l10n

        if self.doc is None:
            return
        if not force and not l10n.load_settings().get("preflight_on_open", True):
            return
        self._pf_gen += 1
        gen = self._pf_gen
        self.pf_panel.set_busy()
        self.btn_pf.setText("… " + tr("Prüfe"))
        self.btn_pf.show()
        # own process: does not slow the interface down (Python threads share one lock), no pdfium
        # in the program; the file (unchanged) is checked, or the state that the preview shows too
        from .renderclient import RenderService

        svc = RenderService.get("analysis")
        path = None
        if svc.ok:
            if (
                not self.modified
                and self.path
                and self.path.lower().endswith(".pdf")
                and os.path.isfile(self.path)
                and not self.view._local
            ):
                path = self.path
            elif self.view._src_path and os.path.isfile(self.view._src_path) and not self.view._local:
                path = self.view._src_path
        if path is None:
            self._pf_start_thread(gen)
            return

        def got(err, rep, gen=gen):
            if gen != self._pf_gen or self.doc is None:
                return  # outdated (the document has changed in the meantime)
            if err or rep is None:
                self._pf_start_thread(gen)  # fallback: in the program
            else:
                self._pf_show(rep)

        svc.call("preflight", {"path": path, "deep_layers": True}, got)

    def _pf_show(self, rep):
        try:  # size against the default printer (paper sizes)
            from .. import preflight, printjob

            prn = printjob.default_printer(self.session)
            if prn:
                preflight.add_device_issues(rep, self.session.caps_for(prn), prn)
        except Exception:  # noqa: BLE001 – the check must never fail because of this
            pass
        self.pf_panel.set_report(rep)
        c = rep.counts()
        if c["error"] or c["warning"]:
            self.btn_pf.setText("⚠ " + tr("{0} Fehler · {1} Warnung(en)").format(c["error"], c["warning"]))
            self.btn_pf.setStyleSheet(_chip(theme.ERROR if c["error"] else theme.WARN))
        else:
            self.btn_pf.setText("✓ " + tr("Prüfung OK"))
            self.btn_pf.setStyleSheet(_chip(theme.OK))

    def _pf_start_thread(self, gen):
        """Fallback without the analysis process: pikepdf part in a background thread, pdfium part in the window."""
        from .. import preflight
        from .preflightpanel import _Worker

        try:
            # unchanged: check the file itself (no re-saving in the main window, size as on disk)
            data = self._doc_bytes() if self.modified else self._file_bytes()
        except Exception as e:  # noqa: BLE001 – shown to the user
            self.pf_panel.set_error(str(e))
            return
        w = _Worker(lambda d: preflight.analyze(d, True, pdfium_parts=False), data)

        def done(rep, err, gen=gen, w=w):
            if gen != self._pf_gen:
                return  # outdated (document has changed in the meantime)
            if err:
                self.pf_panel.set_error(err)
                self.btn_pf.setText("⚠ " + tr("Prüfung fehlgeschlagen"))
                return
            try:
                preflight.finish(rep, data)  # pdfium parts in the main thread
            except Exception:
                log.warning("Prüfung: pdfium-Teil nicht abgeschlossen", exc_info=True)
            self._pf_show(rep)

        w.done.connect(done)
        self._pf_worker = w
        w.start()

    def _pf_result(self, data: bytes, suffix: str, notes: list):
        import pypdfium2 as pdfium

        self._open_result(pdfium.PdfDocument(data), suffix, notes)

    def _pf_stop(self):
        w = getattr(self, "_pf_worker", None)
        if w is not None and w.isRunning():
            w.wait(15000)


def _chip(color: str) -> str:
    """Style of the check result at the left of the status bar: coloured text on a dark rounded field."""
    return (
        f"QPushButton#pfChip {{ color: {color}; background: {theme.PANEL}; border: 1px solid {theme.BORDER_SUBTLE};"
        " border-radius: 6px; padding: 3px 12px; font-weight: 600; }"
        f"QPushButton#pfChip:hover {{ border-color: {color}; }}"
    )
