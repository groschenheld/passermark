# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Plan & Poster → Plandruck … and Rollen …

Plan printing window in three parts: the plans (add with + or drag in), the run length per roll (one set and all
copies) and the settings (colour, material, print area, rotation, scale, bleed, marks, order). The work is done by
planprint (same as passermark-cli plan / the workflow step "plan"); the rolls come from rolls (device or by hand).
"""

from __future__ import annotations

import dataclasses
import logging
import os

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QIcon, QImage, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QDialog,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QSplitter,
    QTreeWidgetItem,
    QVBoxLayout,
)

from .. import planprint as pp
from .. import printers
from .. import rolls as rl
from ..l10n import tr
from . import lastdir
from . import theme
from .common import make_responsive
from .planbuild import PlanBuildMixin
from .plansetup import FoldersDialog, MaterialsDialog, RollsDialog, start_query
from .plantexts import (
    ALIGN_TEXT,
    CAT_TEXT,
    FRAME_TEXT,
    KIND_SHORT,
    ORIGIN_TEXT,
    PREVIEW_MAX,
    PREVIEW_PX,
    ROTATE_TEXT,
)

log = logging.getLogger(__name__)

SETTINGS_KEY = "plan"  # user setting: last used plan settings
PRINTER_KEY = "plan_printer"


def _keys(kind: str) -> tuple:
    return (SETTINGS_KEY, PRINTER_KEY) if kind != "poster" else ("poster", "poster_printer")


def _std_key(kind: str) -> str:
    return "plan_standard" if kind != "poster" else "poster_standard"


# colour choices for tests: this print only – never remembered, every window starts with the setting
COLOR_TEST = {"profile": "admin", "intent": "", "driver_color_off": False}


def _clean(s: pp.PlanSettings) -> dict:
    """For remembering: without printer, rolls entered by hand, per-plan overrides, raw driver values and the colour
    choices for tests."""
    d = pp.compact(
        dataclasses.replace(s, printer="", rolls=[], dry_run=False, title="", options={}, overrides={}, **COLOR_TEST)
    )
    d.pop("printer", None)
    d.pop("overrides", None)
    return d


def load_settings(kind: str = "plan") -> pp.PlanSettings:
    """Default (the user's own, otherwise the built-in one) + what was last set but not printed."""
    from .. import core, l10n

    st = l10n.load_settings()
    d = st.get(_keys(kind)[0]) or {}
    std = st.get(_std_key(kind)) or {}
    base = dict(pp.defaults_for(kind), **(std if isinstance(std, dict) else {}))
    try:
        merged = dict(base, **(d if isinstance(d, dict) else {}))
        merged["kind"] = kind
        merged.update(COLOR_TEST)
        return core.settings_from_dict(pp.PlanSettings, merged)
    except (TypeError, ValueError):
        return pp.PlanSettings(**base)


def save_settings(s: pp.PlanSettings, printer: str, reset: bool = False) -> None:
    """Remember what is set. reset=True (after printing): next time the default again –
    only the printer stays.
    """
    from .. import l10n

    st = l10n.load_settings()
    skey, pkey = _keys(s.kind)
    if reset:
        st.pop(skey, None)
    else:
        st[skey] = _clean(s)
    if printer:
        st[pkey] = printer
    try:
        l10n.save_settings(st)
    except OSError:
        pass


_WINDOWS: dict = {}  # at most one open window per kind ("plan", "poster")


def open_windows() -> list:
    """The open plan and poster windows."""
    return list(_WINDOWS.values())


def open_window(session, ctl=None, kind: str = "plan", entry: dict | None = None, files=None):
    """Plan or poster printing as its own window (without a parent window): stays open when the document
    windows close. Already open: bring to the front; entry = open an earlier print, files = add files.
    """
    kind = kind if kind in pp.KINDS else "plan"
    dlg = _WINDOWS.get(kind)
    if dlg is None:
        dlg = PlanDialog(None, session, ctl, None, "", "", kind)
        dlg.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        dlg.setModal(False)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        _WINDOWS[kind] = dlg
        dlg.finished.connect(lambda _r, k=kind, d=dlg: _WINDOWS.pop(k, None) if _WINDOWS.get(k) is d else None)
        try:  # never larger than the screen (small notebooks)
            scr = dlg.screen().availableGeometry()
            w, h = min(dlg.width(), scr.width() - 40), min(dlg.height(), scr.height() - 60)
            if (w, h) != (dlg.width(), dlg.height()):
                dlg.resize(max(640, w), max(420, h))
        except Exception:  # noqa: BLE001
            pass
    if entry is not None:
        dlg.load_history(entry)
    if files:
        dlg.add_paths(files)
    dlg.show()
    if dlg.isMinimized():
        dlg.showNormal()
    dlg.raise_()
    dlg.activateWindow()
    return dlg


class PlanDialog(PlanBuildMixin, QDialog):
    """Window for plan and poster printing: list of plans, rolls, settings, preview and printing."""

    printed = Signal(str)

    COLS = ("Plan", "Druckbereich", "Rolle", "Länge", "Menge", "Prüfung")
    CHECK_DEFAULT = "plot"  # check profile of the window (plans and large format)

    def __init__(self, parent, session, ctl=None, doc=None, path: str = "", name: str = "", kind: str = "plan"):
        super().__init__(parent)
        self.kind = kind if kind in pp.KINDS else "plan"
        self.setWindowTitle(tr("Plandruck – Passermark") if self.kind == "plan" else tr("Posterdruck – Passermark"))
        self.setAcceptDrops(True)
        self.session, self.ctl = session, ctl
        self.items: list = []
        self.owned: list = []  # documents opened by the window itself (release when closing)
        self.rolls: list = []
        self.roll_state = None
        self.caps = None
        self.printer = ""
        self._queue: list = []
        self._q = None
        self._retired = []  # documents put aside after a print – release only when closing
        self._building = False
        self.s0 = load_settings(self.kind)
        self._bleed_color = self.s0.bleed_color
        self._checks: dict = {}  # source -> preflight.Report (None: could not be checked)

        v = QVBoxLayout(self)
        self._build_top_row(v)
        split = QSplitter(Qt.Orientation.Horizontal)
        v.addWidget(split, 1)
        left = self._build_plan_list()
        split.addWidget(left)
        pane = self._build_settings_pane()
        split.addWidget(pane)
        split.setChildrenCollapsible(False)
        left.setMinimumWidth(280)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        self._build_bottom_row(v)

        self._fill_checks()
        self.finished.connect(self._cleanup)
        self._timer = QTimer(self)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._analyze_next)
        self._color_button()
        self._connect_settings()

        make_responsive(self)
        self.setMinimumSize(640, 420)
        self._fill_printers()
        self.cmb_printer.currentIndexChanged.connect(self._printer_changed)
        self._printer_changed()
        if doc is not None:
            self.add_doc(doc, path or name, own=False)
        self.resize(1180, 720)
        self._refresh()

    # ------------------------------------------------------------------ #
    # printer and rolls
    # ------------------------------------------------------------------ #
    def _fill_printers(self):
        from .. import l10n, printjob

        try:
            plist = [p for p in printers.list_printers() if p.name != printers.PDF_TARGET]
        except Exception:  # noqa: BLE001 – printer/driver query: works without the value
            plist = []
        for p in plist:
            self.cmb_printer.addItem(p.name + (f" – {p.model}" if p.model else ""), p.name)
        for e in pp.hotfolders():
            self.cmb_printer.addItem(tr("Ordner: {0}").format(e["name"]), pp.FOLDER_PREFIX + e["name"])
        want = l10n.load_settings().get(_keys(self.kind)[1]) or printjob.default_printer(self.session) or ""
        i = self.cmb_printer.findData(want)
        self.cmb_printer.setCurrentIndex(max(0, i))

    def _printer_changed(self, *_a):
        self.printer = self.cmb_printer.currentData() or ""
        self.caps = None
        if self.printer and not pp.is_folder(self.printer):
            try:
                self.caps = self.session.caps_for(self.printer)
            except Exception as e:  # noqa: BLE001
                self.lbl_rolls.setText(tr("Drucker nicht abfragbar: {0}").format(e))
        self._fill_media()
        self._fill_materials()
        self._fill_color_test()
        self._load_rolls()

    def _fill_color_test(self):
        """Colour profile, intent and driver colour for tests (this print only): profiles of the printer."""
        from .. import config, printers

        if getattr(self, "cmb_cprof", None) is None:
            return
        on = bool(self.printer) and not pp.is_folder(self.printer)
        cur = self.cmb_cprof.currentData() if self.cmb_cprof.count() else "admin"
        self.cmb_cprof.blockSignals(True)
        self.cmb_cprof.clear()
        self.cmb_cprof.addItem(tr("Wie eingestellt (Material / Verwaltung)"), "admin")
        self.cmb_cprof.addItem(tr("Keins – Farbmanagement des Treibers"), "none")
        for p in config.profiles_for(self.session.cfg, self.printer) if on else []:
            self.cmb_cprof.addItem(p.get("name") or p["id"], p["id"])
        self.cmb_cprof.setCurrentIndex(max(0, self.cmb_cprof.findData(cur)))
        self.cmb_cprof.blockSignals(False)
        if not self.cmb_cintent.count():
            self.cmb_cintent.addItem(tr("Intent wie eingestellt"), "")
            for k, t in config.INTENTS.items():
                self.cmb_cintent.addItem(tr(t), k)
        can = on and printers.color_off_option(self.caps) is not None
        self.chk_drvcolor.setEnabled(can)
        if not can:
            self.chk_drvcolor.setChecked(False)
        for w in (self.cmb_cprof, self.cmb_cintent):
            w.setEnabled(on)

    def _reset_color_test(self):
        """Back to the setting (after printing and with the default)."""
        if getattr(self, "cmb_cprof", None) is None:
            return
        self.cmb_cprof.setCurrentIndex(max(0, self.cmb_cprof.findData("admin")))
        self.cmb_cintent.setCurrentIndex(0)
        self.chk_drvcolor.setChecked(False)

    def _fill_media(self):
        cur = self.cmb_media.currentData() if self.cmb_media.count() else self.s0.media
        self.cmb_media.blockSignals(True)
        self.cmb_media.clear()
        self.cmb_media.addItem(tr("Wie im Treiber / am Gerät"), "")
        key = self.caps.roles.get("mediatype") if self.caps else None
        if key and key in self.caps.options:
            for ch in self.caps.options[key].choices:
                self.cmb_media.addItem(ch.text, ch.value)
        i = self.cmb_media.findData(cur or "")
        self.cmb_media.setCurrentIndex(max(0, i))
        self.cmb_media.blockSignals(False)

    def _load_rolls(self, force: bool = False):
        """Show those entered by hand first, ask the device in the background."""
        self.rolls = rl.manual(self.printer) if self.printer else []
        self._assign_slots(self.rolls)
        self.roll_state = rl.RollState(self.rolls, "manual" if self.rolls else "none")
        self._roll_text()
        self._refresh()
        host = rl.host_for(self.session, self.printer) if (self.printer and not pp.is_folder(self.printer)) else ""
        if not host:
            if not self.rolls:
                self.lbl_rolls.setText(
                    tr(
                        "Geräteadresse nicht ermittelbar – unter „Rollen …“ die IP-Adresse "
                        "eintragen oder die Rollen von Hand"
                    )
                )
            return
        self.btn_reload.setEnabled(False)
        self.lbl_rolls.setText(self.lbl_rolls.text() + "  " + tr("(frage Gerät ab …)"))
        from .. import roland

        fn = rl.query_roland if roland.is_roland(self.printer, rl.model_of(self.printer)) else None
        self._q = start_query(host, self._rolls_read, self.printer, fn)

    def _assign_slots(self, rolls: list):
        for i, r in enumerate(rolls):
            if not r.slot and self.caps is not None:
                r.slot = rl.slot_for(self.caps, r.device or r.name, i)

    def _rolls_read(self, st, printer: str):
        if getattr(self, "_closed", False):
            return
        self.btn_reload.setEnabled(True)
        if printer != self.printer:
            return
        if st.rolls:
            self.rolls = [rl.Roll.from_dict(r.to_dict()) for r in st.rolls]
            self._assign_slots(self.rolls)
            self.roll_state = rl.RollState(self.rolls, st.origin, "", st.host, list(getattr(st, "catalog", []) or []))
        else:
            self.roll_state = rl.RollState(self.rolls, "manual" if self.rolls else "none", st.error, st.host)
        self._roll_text()
        self._refresh()

    def _fill_rolls(self):
        g = getattr(self, "g", None)
        cur = g["roll_pick"] if g is not None else self.s0.roll_pick
        self.cmb_roll.blockSignals(True)
        self.cmb_roll.clear()
        self.cmb_roll.addItem(tr("Automatisch"), "")
        for r in self.rolls:
            if not getattr(r, "empty", False):
                self.cmb_roll.addItem(r.label(), pp.roll_key(r))
        i = self.cmb_roll.findData(cur or "")
        self.cmb_roll.setCurrentIndex(max(0, i))
        self.cmb_roll.blockSignals(False)

    def _roll_text(self):
        self._fill_rolls()
        self._fill_materials()
        if hasattr(self, "g"):
            self._load_fields()
        st = self.roll_state
        if st is None or not self.rolls:
            err = f" ({st.error})" if st is not None and st.error else ""
            self.lbl_rolls.setText(tr("Keine Rollen bekannt") + err + " – " + tr("„Rollen …“ zum Eintragen"))
            return
        self.lbl_rolls.setText(
            tr(ORIGIN_TEXT.get(st.origin, st.origin)) + ": " + "  ·  ".join(r.label() for r in self.rolls)
        )

    def _edit_rolls(self):
        if not self.printer:
            return
        if RollsDialog(self, self.session, self.printer).exec():
            self._load_rolls()

    # ------------------------------------------------------------------ #
    # plans
    # ------------------------------------------------------------------ #
    def add_doc(self, doc, source: str, own: bool = True, pages=None):
        """Add pages of a document to the list (``own``: the window opened it and closes it later)."""
        if own:
            self.owned.append(doc)
        for p in pages if pages is not None else range(len(doc)):
            it = pp.Item(p, 1, None, source=source, doc=doc)
            self.items.append(it)
            self._queue.append(it)
        self._rebuild()
        self._timer.start()

    def _add_files(self):
        from .. import convert

        paths, _ = lastdir.getOpenFileNames(
            self,
            tr("Pläne hinzufügen"),
            os.path.expanduser("~"),
            tr("Pläne (*.pdf *.png *.jpg *.jpeg *.tif *.tiff);;Alle Dateien (*)"),
        )
        self.add_paths([p for p in paths if convert.is_supported(p) or p.lower().endswith(".pdf")])

    def add_paths(self, paths: list):
        """Open the files and add all their pages to the list."""
        for p in paths:
            doc = self._load(p)
            if doc is not None:
                self.add_doc(doc, p)

    def _load(self, path: str):
        try:
            if self.ctl is not None:
                from .fileopen import load_any

                return load_any(self, self.ctl, path)
            import pypdfium2 as pdfium

            from .. import images

            if images.is_image(path):
                return images.images_to_document([path], 96.0)
            return pdfium.PdfDocument(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(
                self, tr("Plandruck"), tr("{0} lässt sich nicht öffnen: {1}").format(os.path.basename(path), e)
            )
            return None

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        from .. import convert

        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        self.add_paths([p for p in paths if convert.is_supported(p) or p.lower().endswith(".pdf")])

    def _selected(self) -> list:
        rows = sorted({self.tree.indexOfTopLevelItem(x) for x in self.tree.selectedItems()})
        return [r for r in rows if r >= 0]

    def _remove(self):
        rows = self._selected()
        for r in reversed(rows):
            it = self.items.pop(r)
            if it in self._queue:
                self._queue.remove(it)
        self._rebuild()
        self._refresh()

    def _move(self, d: int):
        rows = self._selected()
        if not rows:
            return
        if (d < 0 and rows[0] == 0) or (d > 0 and rows[-1] == len(self.items) - 1):
            return
        for r in rows if d < 0 else reversed(rows):
            self.items[r], self.items[r + d] = self.items[r + d], self.items[r]
        self._rebuild()
        for r in rows:
            self.tree.topLevelItem(r + d).setSelected(True)
        self._refresh()

    def _menu(self, pos):
        rows = self._selected()
        if not rows:
            return
        m = QMenu(self)
        sub = m.addMenu(tr("Druckbereich"))
        for k in ("",) + pp.FRAME_MODES:
            a = sub.addAction(tr("Wie eingestellt") if k == "" else tr(FRAME_TEXT[k]))
            a.setCheckable(True)
            a.setChecked(all(self.items[r].ov.get("frame", self.items[r].frame) == k for r in rows))
            a.triggered.connect(lambda _c=False, k=k: self._set_frame(rows, k))
        a = m.addAction(tr("Menge …"))
        a.triggered.connect(lambda: self.tree.editItem(self.tree.topLevelItem(rows[0]), 4))
        m.exec(self.tree.viewport().mapToGlobal(pos))

    def _set_frame(self, rows, k):
        for r in rows:
            it = self.items[r]
            it.frame = ""
            if k:
                it.ov["frame"] = k
            else:
                it.ov.pop("frame", None)
            it.area = None
            self._requeue(it)
        self._timer.start()
        self._refresh()

    def _qty_changed(self, row, col):
        if self._building or col != 4:
            return
        i = self.tree.indexOfTopLevelItem(row)
        if i < 0:
            return
        try:
            q = max(0, int(row.text(4).strip() or "0"))
        except ValueError:
            q = self.items[i].qty
        self.items[i].qty = q
        self._refresh()

    def _rebuild(self):
        self._building = True
        self.tree.clear()
        for it in self.items:
            row = QTreeWidgetItem([it.label, "", "", "", str(it.qty), ""])
            row.setFlags(row.flags() | Qt.ItemFlag.ItemIsEditable)
            row.setTextAlignment(4, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.setTextAlignment(3, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tree.addTopLevelItem(row)
        self._building = False

    # ------------------------------------------------------------------ #
    # detect and compute
    # ------------------------------------------------------------------ #
    def _redetect(self, *_a):
        for it in self.items:
            it.area = None
            self._requeue(it)
        self._timer.start()
        self._refresh()

    def _redetect_hairlines(self, *_a):
        """Count the hairlines again (scale changed) – in the background, the print area stays."""
        for it in self.items:
            if it.area is not None:
                it._hair_only = True
                self._requeue(it)
        self._timer.start()
        self._refresh()

    def _requeue(self, it):
        """Detect a plan again: answers still under way for it are outdated."""
        it._sent = False
        it._local = False
        it._tok = getattr(it, "_tok", 0) + 1
        if it not in self._queue:
            self._queue.append(it)

    def _service(self):
        """Analysis process (as for the check of the main window) – None: everything in the window."""
        if os.environ.get("PASSERMARK_RENDER", "") == "local":
            return None
        from .renderclient import RenderService

        svc = RenderService.get("analysis")
        return svc if svc.ok else None

    @staticmethod
    def _item_path(it) -> str:
        """The file of a plan, if the analysis process can open it itself (a PDF as it lies on disk)."""
        src = it.source or ""
        return src if src.lower().endswith(".pdf") and os.path.isfile(src) else ""

    def _analyze_next(self):
        """Detection of the plans: files in the analysis process (the window does not wait – CAD plans take
        seconds), converted documents one per step in the window. Then the check."""
        if getattr(self, "_closed", False):
            self._timer.stop()
            return
        svc = self._service()
        s = self.settings()
        if svc is not None:
            for it in self._queue:
                path = self._item_path(it)
                if getattr(it, "_sent", False) or not path or getattr(it, "_local", False):
                    continue
                it._sent = True
                it._tok = getattr(it, "_tok", 0) + 1
                es = pp.eff(s, it)
                hair = bool(getattr(it, "_hair_only", False)) and it.area is not None
                args = {
                    "path": path,
                    "page": it.page,
                    "frame": es.frame,
                    "margin_mm": es.margin_mm,
                    "hairline_mm": s.hairline_mm,
                    "scale": {"scale_mode": es.scale_mode, "scale_pct": es.scale_pct, "scale_mm": es.scale_mm},
                    "area": [list(it.area.rect), it.area.kind, it.area.note] if hair else None,
                }
                svc.call("plan_item", args, lambda err, res, it=it, tok=it._tok: self._item_done(it, tok, err, res))
        local = next(
            (it for it in self._queue if not getattr(it, "_sent", False)),
            None,
        )
        if local is None:
            if self._queue:  # everything is in the analysis process: wait for the answers
                self.lbl_state.setText(tr("Erkenne … ({0} offen)").format(len(self._queue)))
                self._timer.stop()
                return
            src = self._next_unchecked()
            if src is not None:  # after the detection: check the files one by one (window stays usable)
                self._run_check(src)
                self._refresh()
                return
            self._timer.stop()
            self.lbl_state.setText("")
            self._refresh()
            return
        it = local
        self._queue.remove(it)
        self.lbl_state.setText(tr("Erkenne {0} … ({1} offen)").format(it.label, len(self._queue)))
        try:
            es = pp.eff(s, it)
            if not (getattr(it, "_hair_only", False) and it.area is not None):
                it.area = pp.detect(it.doc, it.page, es.frame, es.margin_mm)
            it.hairlines = pp.hairlines(it.doc, it.page, s.hairline_mm, pp.factor(it.area, es) * 100.0)
            if getattr(it, "_thumb", None) is None:
                self._local_thumb(it)
        except Exception as e:  # noqa: BLE001
            it.area = None
            self.lbl_state.setText(tr("{0}: {1}").format(it.label, e))
        it._hair_only = False
        self._refresh()

    def _item_done(self, it, tok, err, res):
        """Answer of the analysis process for one plan."""
        if getattr(self, "_closed", False) or it not in self.items or tok != getattr(it, "_tok", 0):
            return
        it._sent = False
        if err or not res:
            log.warning("Plandruck: Erkennung im Hintergrund fehlgeschlagen (%s) – im Fenster", err)
            it._local = True  # once more in the window
            self._timer.start()
            return
        it.area = pp.Area(tuple(res["rect"]), res["kind"], res.get("note", ""))
        it.hairlines = int(res.get("hairlines") or 0)
        w, h, data = res["thumb"]
        it._thumb = QImage(data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
        it._thumb_pt = tuple(res["page_pt"])
        it._hair_only = False
        if it in self._queue:
            self._queue.remove(it)
        self.lbl_state.setText(tr("Erkenne … ({0} offen)").format(len(self._queue)) if self._queue else "")
        self._refresh()
        if not self._queue:
            self._timer.start()  # then the check

    def _local_thumb(self, it):
        """Small picture of a page rendered in the window (converted images/office files – these are light)."""
        try:
            W, H = it.doc.get_page_size(it.page)
            k = pp.THUMB_PX / max(W, H)
            page = it.doc[it.page]
            try:
                arr = page.render(scale=k, may_draw_forms=True).to_numpy()
            finally:
                page.close()
            import numpy as np

            if arr.ndim == 2:
                arr = np.stack([arr] * 3, axis=2)
            arr = np.ascontiguousarray(arr[..., :3][..., ::-1])
            it._thumb = QImage(arr.data, arr.shape[1], arr.shape[0], arr.strides[0], QImage.Format.Format_RGB888).copy()
            it._thumb_pt = (W, H)
        except Exception:  # noqa: BLE001 – preview only
            it._thumb = None

    # ------------------------------------------------------------------ #
    # document check
    # ------------------------------------------------------------------ #
    def _fill_checks(self):
        """Check profiles in the combo; plot by default (this window only, not remembered)."""
        from .. import checkprofile

        self.cmb_check.blockSignals(True)
        self.cmb_check.clear()
        for p in checkprofile.all_profiles():
            self.cmb_check.addItem(p.title(), p.name)
        self.cmb_check.addItem(tr("Keine Prüfung"), "")
        self.cmb_check.setCurrentIndex(max(0, self.cmb_check.findData(self.CHECK_DEFAULT)))
        self.cmb_check.blockSignals(False)
        self.cmb_check.currentIndexChanged.connect(self._check_profile_changed)

    def _check_profile_changed(self, *_a):
        self._check_gen = getattr(self, "_check_gen", 0) + 1  # answers still under way are outdated
        self._checks.clear()
        self._timer.start()
        self._refresh()

    def _next_unchecked(self):
        if not self.cmb_check.currentData():
            return None
        return next((it.source for it in self.items if it.source not in self._checks and it.doc is not None), None)

    def _run_check(self, src: str):
        """Check one file of the list with the profile of the window – in the analysis process if possible."""
        from .. import preflight

        it = next(x for x in self.items if x.source == src)
        self.lbl_state.setText(tr("Prüfe {0} …").format(os.path.basename(src)))
        svc = self._service()
        if svc is not None and self._item_path(it):
            self._checks[src] = "pending"
            gen = self._check_gen = getattr(self, "_check_gen", 0) + 1

            def got(err, rep, src=src, gen=gen):
                if getattr(self, "_closed", False) or gen != getattr(self, "_check_gen", 0):
                    return
                self._checks[src] = None if err else rep
                self._refresh()
                self._timer.start()  # next file

            svc.call("preflight", {"path": src, "deep_layers": False, "profile": self.cmb_check.currentData()}, got)
            self._timer.stop()
            return
        QApplication.processEvents()
        try:
            if src.lower().endswith(".pdf") and os.path.isfile(src):
                with open(src, "rb") as f:
                    data = f.read()
            else:  # image or office file: the converted document
                import io

                buf = io.BytesIO()
                it.doc.save(buf)
                data = buf.getvalue()
            self._checks[src] = preflight.analyze(data, profile=self.cmb_check.currentData())
        except Exception:  # noqa: BLE001 – the plan stays printable, the check is a hint
            log.warning("Plandruck: Prüfung von %s fehlgeschlagen", src, exc_info=True)
            self._checks[src] = None

    def _findings(self, it) -> list | None:
        """Findings of the check that concern this plan (its page or the whole file); None: not checked yet."""
        rep = self._checks.get(it.source)
        if rep == "pending":
            return None
        if rep is None:
            return None if it.source not in self._checks else []
        return [i for i in rep.issues if i.severity in ("error", "warning") and (not i.pages or it.page + 1 in i.pages)]

    def _check_cell(self, row, it):
        """Column "Prüfung" of a plan: symbol, count and the findings as tool tip."""
        if not self.cmb_check.currentData():
            row.setText(5, "")
            row.setToolTip(5, "")
            return
        f = self._findings(it)
        if f is None:
            row.setText(5, "…")
            row.setToolTip(5, tr("wird geprüft …"))
            return
        err = sum(1 for i in f if i.severity == "error")
        warn = len(f) - err
        if err:
            row.setText(5, f"✖ {err}" + (f"  ⚠ {warn}" if warn else ""))
            row.setForeground(5, QBrush(QColor(theme.ERROR)))
        elif warn:
            row.setText(5, f"⚠ {warn}")
            row.setForeground(5, QBrush(QColor(theme.WARN)))
        else:
            row.setText(5, "✓")
            row.setForeground(5, QBrush(QColor(theme.OK)))
        lines = [("✖ " if i.severity == "error" else "⚠ ") + i.message for i in f[:10]]
        if len(f) > 10:
            lines.append(tr("… und {0} weitere").format(len(f) - 10))
        row.setToolTip(5, "\n".join(lines) or tr("Keine Fehler und Warnungen."))

    def _check_summary(self):
        """Line above the list: errors and warnings of the plans to print (each finding once)."""
        if not self.cmb_check.currentData():
            self.lbl_check.setText("")
            return
        seen, err, warn, pending = set(), 0, 0, False
        for it in self.items:
            if it.qty <= 0:
                continue
            f = self._findings(it)
            if f is None:
                pending = True
                continue
            for i in f:
                key = (it.source, id(i))
                if key in seen:
                    continue
                seen.add(key)
                err += i.severity == "error"
                warn += i.severity == "warning"
        if not self.items:
            txt, col = "", theme.MUTED
        elif err or warn:
            parts = [tr("{0} Fehler").format(err)] if err else []
            parts += [tr("{0} Warnung(en)").format(warn)] if warn else []
            txt, col = " · ".join(parts) + tr(" – Details: Spalte „Prüfung“"), theme.ERROR if err else theme.WARN
        elif pending:
            txt, col = tr("wird geprüft …"), theme.MUTED
        else:
            txt, col = tr("Keine Fehler und Warnungen."), theme.OK
        self.lbl_check.setText(txt)
        self.lbl_check.setStyleSheet(f"color: {col};")
        self._check_errors = err

    def _changed(self, *_a):
        self._color_button()
        self._refresh()

    def _weights(self) -> list:
        out = []
        for t in self.ed_weights.text().replace(";", ",").split(","):
            t = t.strip().lower().replace("g", "")
            if t.isdigit():
                out.append(int(t))
        return out

    # ------------------------------------------------------------------ #
    # settings per plan (selection)
    # ------------------------------------------------------------------ #
    def _partial(self) -> list:
        """Selected plans – empty if nothing or everything is selected (it then applies to all)."""
        rows = self._selected()
        return [self.items[r] for r in rows] if 0 < len(rows) < len(self.items) else []

    def _set_field(self, vals: dict):
        if getattr(self, "_loading_fields", False):
            return
        sel = self._partial()
        redetect = bool({"frame", "margin_mm"} & set(vals))
        targets = sel or self.items
        if sel:
            for it in sel:
                for k, v in vals.items():
                    if v == self.g.get(k):
                        it.ov.pop(k, None)  # same as for all: no override any more
                    else:
                        it.ov[k] = v
                    if k == "frame":
                        it.frame = ""
        else:
            self.g.update(vals)
            for it in self.items:
                for k in vals:
                    it.ov.pop(k, None)
                    if k == "frame":
                        it.frame = ""
        self._color_button()
        if redetect:
            for it in targets:
                it.area = None
                self._requeue(it)
            self._timer.start()
        elif {"scale_pct", "scale_mode", "scale_mm"} & set(vals):
            self._redetect_hairlines()
            return
        self._refresh()

    def _scale_widgets(self):
        pct = (self.cmb_scale.currentData() or "pct") == "pct"
        self.spn_scale.setVisible(pct)
        self.spn_scale_mm.setVisible(not pct)

    def _scale_changed(self, *_a):
        self._scale_widgets()
        mode = self.cmb_scale.currentData() or "pct"
        if mode != "pct" and self.spn_scale_mm.value() <= 0:
            return  # enter a measure first
        self._set_field(
            {"scale_mode": mode, "scale_pct": self.spn_scale.value(), "scale_mm": self.spn_scale_mm.value()}
        )

    def _load_fields(self):
        """The fields show the values of the selection (first selected plan) or those for all."""
        sel = self._partial()
        base = self.settings()
        es = pp.eff(base, sel[0]) if sel else base
        self._loading_fields = True
        try:
            for w, v in (
                (self.cmb_mat, es.material),
                (self.cmb_roll, es.roll_pick),
                (self.cmb_align, es.align),
                (self.cmb_rotate, es.rotate),
                (self.cmb_bleed, es.bleed_mode),
                (self.cmb_frame, es.frame),
                (self.cmb_scale, es.scale_mode),
            ):
                w.blockSignals(True)
                i = w.findData(v)
                w.setCurrentIndex(max(0, i))
                w.blockSignals(False)
            for w, v in (
                (self.spn_bleed, es.bleed_mm),
                (self.spn_margin, es.margin_mm),
                (self.spn_scale, es.scale_pct),
                (self.spn_scale_mm, es.scale_mm or 0),
            ):
                w.blockSignals(True)
                w.setValue(v)
                w.blockSignals(False)
            self._bleed_color = es.bleed_color
            self._color_button()
            self._scale_widgets()
        finally:
            self._loading_fields = False
        if sel:
            self.lbl_scope.setText(
                tr(
                    "Änderungen gelten nur für die Auswahl ({0} von {1}) – Material, Rolle, Lage, "
                    "Druckbereich, Skalierung und Überfüller"
                ).format(len(sel), len(self.items))
            )
        else:
            self.lbl_scope.setText("")

    def _ov_text(self, it) -> str:
        """Briefly what differs for this plan."""
        if not it.ov and not it.frame:
            return ""
        es = pp.eff(self.settings(), it)
        parts = []
        if {"scale_mode", "scale_pct", "scale_mm"} & set(it.ov):
            parts.append(pp.scale_text(es))
        if "rotate" in it.ov:
            parts.append("↻ " + tr(ROTATE_TEXT.get(es.rotate, es.rotate)))
        if "frame" in it.ov or it.frame:
            parts.append(tr(KIND_SHORT.get(es.frame, FRAME_TEXT.get(es.frame, es.frame))))
        if "margin_mm" in it.ov:
            parts.append(tr("Rand {0} mm").format(pp.mm_text(es.margin_mm)))
        if {"bleed_mm", "bleed_mode", "bleed_color"} & set(it.ov):
            parts.append(tr("Überfüller {0} mm").format(pp.mm_text(es.bleed_mm)))
        if "material" in it.ov:
            m = pp.material_of(es)
            parts.append(m["name"] if m else tr("Material"))
        if "roll_pick" in it.ov:
            parts.append(tr("Rolle {0}").format(es.roll_pick or tr("automatisch")))
        if "align" in it.ov:
            parts.append(tr(ALIGN_TEXT.get(es.align, es.align)))
        return " · ".join(parts)

    def settings(self) -> pp.PlanSettings:
        """The settings as entered in the window."""
        hem = "".join(k for k, c in self.chk_hem.items() if c.isChecked())
        return dataclasses.replace(
            self.s0,
            kind=self.kind,
            printer=self.printer,
            color=self.cmb_color.currentData() or "",
            quality_mode=self.cmb_qmode.currentData() or "",
            media=self.s0.media,
            crop_marks=self.chk_marks.isChecked(),
            copies=self.spn_copies.value(),
            collate=self.chk_collate.isChecked(),
            order=self.cmb_order.currentData() or "list",
            weights=self._weights() if self.kind == "plan" else [],
            fix_hairlines=self.chk_hair.isChecked(),
            nest=self.chk_nest.isChecked(),
            gap_mm=self.spn_gap.value(),
            overwidth=self.cmb_over.currentData() or "none",
            overlap_mm=self.spn_overlap.value(),
            fold_marks=self.chk_fold.isChecked() and self.kind == "plan",
            hem_mm=self.spn_hem.value(),
            hem_sides=hem,
            grommet_spacing_mm=self.spn_grom.value(),
            grommet_inset_mm=self.spn_grom_in.value(),
            cut_contour=self.chk_cut.isChecked(),
            printcut_marks=self.chk_pcm.isChecked(),
            rolls=[],
            dry_run=False,
            split_copies=True,
            copies_mode=self.cmb_copies.currentData() or "sheets",
            overrides={},
            profile=self.cmb_cprof.currentData() or "admin",
            intent=self.cmb_cintent.currentData() or "",
            driver_color_off=self.chk_drvcolor.isEnabled() and self.chk_drvcolor.isChecked(),
            **{k: self.g[k] for k in pp.OV_KEYS},
        )

    def _pieces(self, it, s, use):
        return pp.pieces_for(it, self.rolls, s, use, max(1, it.qty) * max(1, s.copies)) if self.rolls else []

    def _refresh(self):
        s = self.settings()
        done = [it for it in self.items if it.area is not None]
        use, wnote = pp.eligible_for(self.rolls, s)
        if self.rolls:
            pp.place_all(done, self.rolls, s)
        else:
            for it in done:
                it.size = pp.finished_size(it.area, s)
                it.fit = None
        self._building = True
        for i, it in enumerate(self.items):
            row = self.tree.topLevelItem(i)
            if row is None:
                continue
            self._check_cell(row, it)
            if it.area is None:
                row.setText(1, tr("wird erkannt …"))
                row.setText(2, "")
                row.setText(3, "")
                continue
            kind = tr(KIND_SHORT.get(it.area.kind, it.area.kind))
            row.setText(
                1,
                tr("{0} × {1} mm").format(pp.mm_text(round(it.size[0])), pp.mm_text(round(it.size[1])))
                + f"  ({kind})"
                + ("  ⚠" if it.hairlines else ""),
            )
            tip = [tr(pp.KIND_TEXT.get(it.area.kind, it.area.kind))]
            if it.area.note:
                tip.append(it.area.note)
            ovt = self._ov_text(it)
            row.setText(0, it.label + (f"  ✎ {ovt}" if ovt else ""))
            row.setToolTip(0, tr("Abweichend von den Einstellungen für alle: {0}").format(ovt) if ovt else "")
            if it.hairlines:
                tip.append(tr("{0} Linie(n) dünner als {1} mm").format(it.hairlines, pp.mm_text(s.hairline_mm)))
            row.setToolTip(1, "\n".join(tip))
            pcs = self._pieces(it, s, use)
            if pcs:
                p0 = pcs[0]
                txt = tr("{0} mm").format(pp.mm_text(p0.width_mm)) + ("  ↻" if p0.rotated else "")
                if len(pcs) > 1:
                    txt += "  " + tr("{0} Bahnen").format(len(pcs))
                if p0.clipped:
                    txt += "  ✂"
                elif p0.trimmed > 0:
                    txt += "  " + tr("−{0} mm").format(pp.mm_text(round(p0.trimmed, 1)))
                row.setText(2, txt)
                row.setToolTip(
                    2,
                    "\n".join(
                        x
                        for x in (
                            tr("gedreht – quer zur Rolle") if p0.rotated else "",
                            tr("breiter als die Rolle – wird abgeschnitten") if p0.clipped else "",
                            tr("{0} mm breiter als die Rolle – am Rand beschnitten (je Seite die Hälfte)").format(
                                pp.mm_text(round(p0.trimmed, 1))
                            )
                            if p0.trimmed > 0
                            else "",
                            tr("in {0} Bahnen mit Überlappung").format(len(pcs)) if len(pcs) > 1 else "",
                        )
                        if x
                    ),
                )
                row.setText(3, tr("{0} m").format(pp.num(sum(p.along for p in pcs) / 1000.0)))
                for c in range(4):
                    row.setForeground(c, QBrush())
                if p0.clipped:
                    row.setForeground(2, QBrush(QColor(theme.ACCENT)))
            else:
                row.setText(2, tr("passt nicht") if self.rolls else "–")
                row.setText(3, "")
                if self.rolls:
                    row.setForeground(2, QBrush(QColor(theme.ERROR)))
        self._building = False
        self._check_summary()
        self._lengths(s, done, wnote, use)
        if hasattr(self, "_prev_timer"):
            self._prev_timer.start()

    def _preview(self):
        """Print pages as they go to the printer: one image per sheet with roll, size, copies and cut."""
        if getattr(self, "_closed", False):
            return
        self.lst_prev.clear()
        done = [it for it in self.items if it.area is not None and it.qty > 0]
        if not done or not self.rolls:
            self.lbl_prev.setText(tr("Noch nichts zu zeigen.") if not done else tr("Keine Rollen bekannt."))
            return
        s = self.settings()
        try:
            runs = pp.build_runs(done, self.rolls, s)
        except Exception as e:  # noqa: BLE001
            self.lbl_prev.setText(str(e))
            return
        mode = pp.copies_mode(s)
        for k, run in enumerate(runs[:PREVIEW_MAX]):
            roll = self.rolls[run.roll] if 0 <= run.roll < len(self.rolls) else None
            n = max(1, run.copies)
            cap = tr("Blatt {0}: {1} × {2} mm").format(
                k + 1, pp.mm_text(round(run.across)), pp.mm_text(round(run.along))
            )
            cap += "\n" + (roll.name or roll.slot or tr("{0} mm").format(pp.mm_text(roll.width_mm)) if roll else "")
            if n > 1:
                cap += "  ×" + str(n) + ("" if mode == "count" else " ✂")
            it = QListWidgetItem(QIcon(self._sheet_pixmap(run, s)), cap)
            it.setToolTip("\n".join(p.label for p, _x, _y in run.pieces))
            self.lst_prev.addItem(it)
        total = sum(max(1, r.copies) for r in runs)
        txt = {
            "sheets": tr("{0} Druckseite(n) · {1} Blatt · ein Auftrag je Druckseite, Schnitt nach jedem Blatt"),
            "jobs": tr("{0} Druckseite(n) · {1} Blatt · je Exemplar ein Auftrag"),
            "count": tr("{0} Druckseite(n) · {1} Blatt · Kopienzahl, Schneiden wie am Gerät eingestellt"),
        }[mode]
        extra = tr(" – Vorschau zeigt die ersten {0}").format(PREVIEW_MAX) if len(runs) > PREVIEW_MAX else ""
        self.lbl_prev.setText(txt.format(len(runs), total) + extra)

    def _sheet_pixmap(self, run, s) -> QPixmap:
        """Print page drawn small from the page pictures of the plans (no rendering – CAD plans take seconds),
        roll width outlined in grey, cut edge red. A plan without a picture yet: grey area."""
        from .. import layout

        W, H = run.across, run.along
        sc = PREVIEW_PX / max(W, H)
        w, h = max(8, int(W * sc)), max(8, int(H * sc))
        pm = QPixmap(w + 2, h + 2)
        pm.fill(QColor("#ffffff"))
        p = QPainter(pm)
        try:
            k = sc / pp.MM  # px per pt
            to_px = (k, 0, 0, -k, 1.0, 1.0 + H * pp.MM * k)  # sheet pt (y up) -> picture px (y down)
            for piece, x, y in run.pieces:
                it = piece.item
                es = pp.eff(s, it)
                f = pp.factor(it.area, es)
                x0, y0, x1, y1 = piece.rect
                cw, ch = (x1 - x0) * f, (y1 - y0) * f
                left, b, _r, t = (v * pp.MM for v in pp.margins_mm(es))
                rot = layout._rot90ccw(ch + b + t) if piece.rotated else (1, 0, 0, 1, 0, 0)
                m = layout._mul(rot, layout._translate(x * pp.MM, y * pp.MM))
                box = layout._mul(layout._mul(layout._translate(left, b), m), to_px)  # content box -> px
                corners = [
                    (cx * box[0] + cy * box[2] + box[4], cx * box[1] + cy * box[3] + box[5])
                    for cx, cy in ((0, 0), (cw, 0), (cw, ch), (0, ch))
                ]
                xs, ys = [c[0] for c in corners], [c[1] for c in corners]
                clip = QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
                img = getattr(it, "_thumb", None)
                if img is None or img.isNull():
                    p.fillRect(clip, QColor(theme.PAPER_LINE))
                    continue
                PW, PH = getattr(it, "_thumb_pt", (img.width(), img.height()))
                img2pt = (PW / img.width(), 0, 0, -PH / img.height(), 0, PH)  # picture px -> page pt (y up)
                src2px = layout._mul(
                    layout._mul(layout._mul(img2pt, layout._translate(-x0, -y0)), layout._scale(f)),
                    layout._mul(layout._mul(layout._translate(left, b), m), to_px),
                )
                p.save()
                p.setClipRect(clip)
                p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                p.setTransform(QTransform(*src2px))
                p.drawImage(0, 0, img)
                p.restore()
        except Exception:  # noqa: BLE001 – the preview must never get in the way
            log.debug("Vorschau der Druckseite", exc_info=True)
        p.setPen(QPen(QColor(theme.PAPER_LINE), 1))
        p.drawRect(0, 0, w + 1, h + 1)
        p.setPen(QPen(QColor(theme.ERROR), 2, Qt.PenStyle.DashLine))
        p.drawLine(0, h + 1, w + 1, h + 1)  # cut at the end of the sheet
        p.end()
        return pm

    def _lengths(self, s, done, wnote, use=None):
        lens = pp.lengths(done, self.rolls, s) if self.rolls else []
        by = {d["roll"]: d for d in lens}
        cp = max(1, s.copies)
        rows = []
        for i, r in enumerate(self.rolls):
            d = by.get(i)
            head = f"<b>{pp.mm_text(r.width_mm)} mm</b>"
            sub = " · ".join(x for x in (r.name, f"{r.weight} g" if r.weight else "", r.media) if x)
            if d is None:
                val = "–"
            else:
                val = f"<b>{pp.num(d['single_m'])} m</b>"
                if cp > 1:
                    val += f" &nbsp; ×{cp} = <b>{pp.num(d['total_m'])} m</b>"
                val += " &nbsp; <span style='color:{}'>({})</span>".format(
                    theme.MUTED,
                    tr("{0} Plan/Pläne").format(d["plans"]),
                )
                if d.get("short"):
                    val += " <span style='color:{}'>{}</span>".format(theme.ERROR, tr("reicht nicht!"))
            if r.remaining_m is not None:
                sub += (" · " if sub else "") + tr("~{0} m Rest").format(pp.mm_text(r.remaining_m))
            rows.append(
                f"<tr><td>{head}</td><td style='color:{theme.MUTED}'>&nbsp;{sub}&nbsp;</td>"
                f"<td align='right'>{val}</td></tr>"
            )
        if len(lens) > 1:
            tot = sum(d["single_m"] for d in lens)
            tot_all = sum(d["total_m"] for d in lens)
            val = f"<b>{pp.num(tot)} m</b>" + (f" &nbsp; ×{cp} = <b>{pp.num(tot_all)} m</b>" if cp > 1 else "")
            rows.append(f"<tr><td colspan='2'>{tr('Gesamt')}</td><td align='right'>{val}</td></tr>")
        self.lbl_len.setText(
            "<table width='100%'>" + "".join(rows) + "</table>"
            if rows
            else tr("Noch keine Rollen – „Rollen …“ oder Gerät abfragen.")
        )
        warn = []
        if wnote:
            warn.append(wnote)
        if s.cut_sheets and self.caps is not None and not pp.is_folder(self.printer) and not pp.cut_values(self.caps):
            warn.append(
                tr(
                    "Der Drucker bietet keine Schneid-Option an – ob nach jedem Blatt geschnitten wird, "
                    "entscheidet die Einstellung am Gerät."
                )
            )
        k = pp.find_roll(self.rolls, s.roll_pick)
        if k is not None and not pp.is_folder(self.printer):
            r = self.rolls[k]
            if not r.slot:
                mv = pp.media_for_roll(self.caps, r) if self.caps is not None else ""
                warn.append(
                    tr("Der Treiber bietet keine Rollenwahl – das Gerät nimmt die Rolle nach Breite und Medientyp.")
                    + (
                        " " + tr("Medientyp laut Rolle wird mitgeschickt.")
                        if mv
                        else " " + tr("Medientyp passend zur Rolle einstellen.")
                    )
                )
            mat = pp.material_of(s)
            if mat and mat.get("weight") and r.weight and int(mat["weight"]) != r.weight:
                warn.append(
                    tr("Material ({0} g) passt nicht zur gewählten Rolle ({1} g).").format(mat["weight"], r.weight)
                )
        use = use if use is not None else self.rolls
        unfit = [it.label for it in done if self.rolls and not self._pieces(it, s, use)]
        if unfit:
            warn.append(
                tr("Passt auf keine Rolle: {0}").format(", ".join(unfit[:5]) + (" …" if len(unfit) > 5 else ""))
            )
        hl = sum(it.hairlines for it in done)
        if hl and not s.fix_hairlines:
            warn.append(
                tr("{0} Linie(n) dünner als {1} mm – „Haarlinien anheben“ verstärkt sie.").format(
                    hl, pp.mm_text(s.hairline_mm)
                )
            )
        from .. import printmat

        warn += printmat.notes(pp.material_of(s), self.session.cfg)
        self.lbl_warn.setText("\n".join(warn))
        printable = any(self._pieces(it, s, use) and it.qty > 0 for it in done) if self.rolls else False
        ready = bool(self.printer and printable and not self._queue)
        self.btn_print.setEnabled(ready)
        self.btn_pdf.setEnabled(bool(printable and not self._queue))

    # ------------------------------------------------------------------ #
    # material and folders
    # ------------------------------------------------------------------ #
    def _fill_materials(self):
        from .. import printmat

        cat = "plan" if self.kind == "plan" else "quality"
        g = getattr(self, "g", None)
        cur = g["material"] if g is not None else self.s0.material
        if not cur and self.printer:
            cur = printmat.default_for(self.printer, cat)
            if g is not None and cur:
                g["material"] = cur
        self.cmb_mat.blockSignals(True)
        self.cmb_mat.clear()
        self.cmb_mat.addItem(tr("– keins –"), "")
        # what the printer reports (media of the loaded rolls) – without having to create it separately
        rs = getattr(self, "roll_state", None)
        own = {m["name"].strip().lower() for m in printmat.for_printer(self.printer)}
        for m in pp.device_materials(getattr(self, "rolls", []) or [], getattr(rs, "catalog", None)):
            if m["name"].strip().lower() in own:
                continue  # already created as a material of its own
            self.cmb_mat.addItem(
                m["name"]
                + (f" · {m['weight']} g" if m["weight"] and f"{m['weight']} g" not in m["name"] else "")
                + "  ("
                + (tr("Gerät") if m["loaded"] else tr("Gerät, nicht geladen"))
                + ")",
                m["id"],
            )
        for m in printmat.for_printer(self.printer, cat) + [
            m for m in printmat.for_printer(self.printer) if m["category"] != cat
        ]:
            t = m["name"] + (f" · {m['weight']} g" if m["weight"] else "")
            if not m.get("checked", True):
                t += "  ⚠ " + tr("ungeprüft")
            if m["category"] != cat:
                t += "  (" + tr(CAT_TEXT[m["category"]]) + ")"
            self.cmb_mat.addItem(t, m["id"])
        if cur and self.cmb_mat.findData(cur) < 0 and cur.startswith(pp.DEV_PREFIX):
            self.cmb_mat.addItem(
                pp.material_of(dataclasses.replace(self.s0, material=cur))["name"] + "  (" + tr("nicht geladen") + ")",
                cur,
            )
        i = self.cmb_mat.findData(cur or "")
        self.cmb_mat.setCurrentIndex(max(0, i))
        self.cmb_mat.blockSignals(False)

    def _edit_materials(self):
        rs = getattr(self, "roll_state", None)
        dev = pp.device_materials(self.rolls or [], getattr(rs, "catalog", None))
        if MaterialsDialog(self, self.session, self.printer, self.caps, dev).exec():
            self._fill_materials()
            self._refresh()

    def _edit_folders(self):
        if FoldersDialog(self).exec():
            cur = self.printer
            self.cmb_printer.blockSignals(True)
            self.cmb_printer.clear()
            self._fill_printers()
            i = self.cmb_printer.findData(cur)
            if i >= 0:
                self.cmb_printer.setCurrentIndex(i)
            self.cmb_printer.blockSignals(False)
            self._printer_changed()

    # ------------------------------------------------------------------ #
    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self._bleed_color), self, tr("Farbe des Überfüllers"))
        if c.isValid():
            self._bleed_color = c.name()
            self._color_button()
            self._set_field({"bleed_color": c.name()})

    def _color_button(self):
        self.btn_bcolor.setStyleSheet(f"background: {self._bleed_color};")
        self.btn_bcolor.setEnabled(self.cmb_bleed.currentData() == "color")

    def _save_pdf(self):
        s = self.settings()
        out, _ = lastdir.getSaveFileName(
            self,
            tr("Als PDF speichern"),
            os.path.join(
                os.path.expanduser("~"), (tr("Plaene_Druck") if self.kind == "plan" else tr("Poster_Druck")) + ".pdf"
            ),
            tr("PDF-Dateien (*.pdf)"),
        )
        if not out:
            return
        if not out.lower().endswith(".pdf"):
            out += ".pdf"
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            n = pp.save_pdf([it for it in self.items if it.area is not None], self.rolls, s, out)
        except Exception as e:  # noqa: BLE001
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, tr("Speichern"), str(e))
            return
        QApplication.restoreOverrideCursor()
        self.lbl_state.setText(tr("{0} Seite(n) gespeichert: {1}").format(n, out))

    def _print(self):
        s = self.settings()
        items = [it for it in self.items if it.area is not None]
        if (
            getattr(self, "_check_errors", 0)
            and QMessageBox.question(
                self,
                tr("Prüfung"),
                tr("Die Prüfung meldet {0} Fehler (Spalte „Prüfung“). Trotzdem drucken?").format(self._check_errors),
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        use, _n = pp.eligible_for(self.rolls, s)
        unfit = [it for it in items if it.qty > 0 and not self._pieces(it, s, use)]
        if (
            unfit
            and QMessageBox.question(
                self,
                tr("Plandruck"),
                tr("{0} Plan/Pläne passen auf keine Rolle und werden ausgelassen. Trotzdem drucken?").format(
                    len(unfit)
                ),
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        short = [d for d in pp.lengths(items, self.rolls, s) if d.get("short")]
        if (
            short
            and QMessageBox.question(
                self,
                tr("Plandruck"),
                tr("Laut Gerät reicht die Rolle {0} mm nicht. Trotzdem drucken?").format(
                    pp.mm_text(short[0]["width_mm"])
                ),
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        def prog(done, total, text=""):
            self.lbl_state.setText(
                tr("Sende {0} von {1}: {2}").format(done + 1 if done < total else total, total, text)
            )
            QApplication.processEvents()

        try:
            info = pp.print_items(self.session, self.printer, items, self.rolls, s, prog)
        except Exception as e:  # noqa: BLE001
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, tr("Druckfehler"), str(e))
            return
        QApplication.restoreOverrideCursor()
        self._remember(s, info)  # history: reopen exactly like this
        save_settings(s, self.printer, reset=True)  # next time the default again
        msg = tr("{0} Plan-Auftrag/-Aufträge an {1} gesendet – {2} m").format(
            len(info["jobs"]), self.printer, pp.num(info["total_m"])
        )
        self.printed.emit(msg)
        self._reset_after_print(msg)

    def _reset_after_print(self, msg: str):
        """The window stays open: clear the list, fields back to the default (the print is in the history).
        Release documents opened by the window only when closing – nothing may point to a closed one.
        """
        try:
            self._timer.stop()
            self._prev_timer.stop()
            self._retired += self.owned
            self.owned, self.items, self._queue = [], [], []
            self.tree.blockSignals(True)
            try:
                self.tree.clearSelection()
                self._rebuild()
            finally:
                self.tree.blockSignals(False)
            self.s0 = load_settings(self.kind)
            self._fill_from(self.s0)
        except Exception:  # noqa: BLE001 – the window stays in any case
            import traceback

            from .. import crashlog

            crashlog.record("Plandruck: Zurücksetzen nach dem Druck", traceback.format_exc())
        self.lbl_state.setText(msg)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:  # own window: Esc does not close (the list would be gone)
            e.ignore()
            return
        super().keyPressEvent(e)

    # ------------------------------------------------------------------ #
    # history
    def _remember(self, s, info):
        from .. import planhistory

        try:
            items = [
                {
                    "doc": it.doc,
                    "source": it.source,
                    "page": it.page,
                    "qty": it.qty,
                    "ov": dict(it.ov),
                    "frame": it.frame,
                    "own": any(it.doc is d for d in self.owned),
                }
                for it in self.items
                if it.area is not None
            ]
            st = pp.compact(dataclasses.replace(s, printer="", rolls=[], dry_run=False, title="", overrides={}))
            st.pop("printer", None)
            planhistory.add(self.kind, self.printer, st, items, info.get("total_m", 0), len(info.get("jobs", [])))
        except Exception:  # noqa: BLE001 – Verlauf darf den Druck nie stören
            pass

    def _history_menu(self):
        from .. import planhistory

        m = QMenu(self)
        ents = planhistory.entries(self.kind)
        if not ents:
            a = m.addAction(tr("Noch keine Drucke im Verlauf"))
            a.setEnabled(False)
        for e in ents[:25]:
            m.addAction(planhistory.label(e), lambda e=e: self.load_history(e))
        m.addSeparator()
        a = m.addAction(tr("Verlauf aufräumen …"), self._clear_history)
        a.setEnabled(bool(ents))
        m.exec(self.btn_hist.mapToGlobal(self.btn_hist.rect().bottomLeft()))

    def _clear_history(self):
        from .. import planhistory

        n = len(planhistory.entries(self.kind))
        mb = planhistory.size_bytes(self.kind) / 1e6
        what = tr("Plandrucke") if self.kind == "plan" else tr("Posterdrucke")
        if (
            QMessageBox.question(
                self,
                tr("Verlauf aufräumen"),
                tr("{0} {1} im Verlauf verwerfen ({2} MB)?").format(n, what, pp.num(round(mb, 1))),
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        planhistory.clear(self.kind)
        self.lbl_state.setText(tr("Verlauf aufgeräumt."))

    def load_history(self, entry: dict):
        """Open an earlier print: files, pages, quantities, per-plan overrides, settings, printer."""
        from .. import core, planhistory

        if (
            self.items
            and QMessageBox.question(self, tr("Verlauf"), tr("Die Liste durch den früheren Druck ersetzen?"))
            != QMessageBox.StandardButton.Yes
        ):
            return
        for d in self.owned:
            try:
                d.close()
            except Exception:  # noqa: BLE001
                pass
        self.owned, self.items, self._queue = [], [], []
        try:
            base = dict(pp.defaults_for(self.kind), **(entry.get("settings") or {}))
            base["kind"] = self.kind
            s = core.settings_from_dict(pp.PlanSettings, base)
        except (TypeError, ValueError):
            s = load_settings(self.kind)
        i = self.cmb_printer.findData(entry.get("printer", ""))
        if i >= 0 and i != self.cmb_printer.currentIndex():
            self.cmb_printer.setCurrentIndex(i)
        self.s0 = s
        self._fill_from(s)
        docs, missing = {}, []
        for rec in entry.get("items", []):
            path = planhistory.file_of(entry, rec)
            if not path:
                missing.append(os.path.basename(rec.get("source") or "?"))
                continue
            if path not in docs:
                docs[path] = self._load(path)
                if docs[path] is not None:
                    self.owned.append(docs[path])
            doc = docs[path]
            if doc is None or rec.get("page", 0) >= len(doc):
                continue
            it = pp.Item(
                int(rec.get("page", 0)),
                int(rec.get("qty", 1)),
                None,
                source=rec.get("source") or path,
                doc=doc,
                frame=rec.get("frame", ""),
                ov=dict(rec.get("ov") or {}),
            )
            self.items.append(it)
            self._queue.append(it)
        self._rebuild()
        self._timer.start()
        msg = tr("Früherer Druck geöffnet: {0}").format(planhistory.label(entry))
        if missing:
            msg += " – " + tr("nicht mehr vorhanden: {0}").format(", ".join(sorted(set(missing))))
        self.lbl_state.setText(msg)

    def _save_standard(self):
        from .. import l10n

        st = l10n.load_settings()
        st[_std_key(self.kind)] = _clean(dataclasses.replace(self.settings(), copies=1))  # copies: always 1
        try:
            l10n.save_settings(st)
        except OSError as e:
            QMessageBox.warning(self, tr("Standard"), str(e))
            return
        self.lbl_state.setText(tr("Als Standard gespeichert – nach jedem Druck geht das Fenster hierher zurück."))

    def _load_standard(self):
        """Set the fields to the default (plans in the list and their overrides stay)."""
        from .. import l10n

        st = l10n.load_settings()
        st.pop(_keys(self.kind)[0], None)
        try:
            l10n.save_settings(st)
        except OSError:
            pass
        self.s0 = load_settings(self.kind)
        self._fill_from(self.s0)
        self.lbl_state.setText(tr("Einstellungen auf den Standard zurückgesetzt."))

    def _fill_from(self, s: pp.PlanSettings):
        """Counterpart of settings(): set all fields from s (per-plan overrides stay)."""

        def combo(cb, val):
            i = cb.findData(val)
            if i >= 0:
                cb.setCurrentIndex(i)

        ws = [
            self.spn_copies,
            self.chk_collate,
            self.cmb_copies,
            self.cmb_order,
            self.cmb_color,
            self.cmb_qmode,
            self.ed_weights,
            self.chk_hair,
            self.chk_marks,
            self.chk_fold,
            self.chk_nest,
            self.spn_gap,
            self.cmb_over,
            self.spn_overlap,
            self.spn_hem,
            self.spn_grom,
            self.spn_grom_in,
            self.chk_cut,
            self.chk_pcm,
            *self.chk_hem.values(),
        ]
        for w in ws:
            w.blockSignals(True)
        try:
            self.spn_copies.setValue(max(1, s.copies))
            self.chk_collate.setChecked(s.collate)
            combo(self.cmb_copies, pp.copies_mode(s))
            combo(self.cmb_order, s.order)
            combo(self.cmb_color, s.color)
            combo(self.cmb_qmode, pp.quality_mode_of(s))
            self.ed_weights.setText(", ".join(str(w) for w in (s.weights or [])))
            self.chk_hair.setChecked(s.fix_hairlines)
            self.chk_marks.setChecked(s.crop_marks)
            self.chk_fold.setChecked(s.fold_marks)
            self.chk_nest.setChecked(s.nest)
            self.spn_gap.setValue(s.gap_mm)
            combo(self.cmb_over, s.overwidth)
            self.spn_overlap.setValue(s.overlap_mm)
            self.spn_hem.setValue(s.hem_mm)
            for k, c in self.chk_hem.items():
                c.setChecked(k in (s.hem_sides or ""))
            self.spn_grom.setValue(s.grommet_spacing_mm)
            self.spn_grom_in.setValue(s.grommet_inset_mm)
            self.chk_cut.setChecked(s.cut_contour)
            self.chk_pcm.setChecked(s.printcut_marks)
        finally:
            for w in ws:
                w.blockSignals(False)
        self._reset_color_test()
        self._bleed_color = s.bleed_color
        self.g = {k: getattr(s, k) for k in pp.OV_KEYS}
        self.g["roll_pick"] = s.roll_pick
        self._load_fields()
        self._changed()

    def _cleanup(self, r):
        """After closing: remember the settings, release documents opened by the window."""
        if r != QDialog.DialogCode.Accepted and r != 1:
            save_settings(self.settings(), self.printer)
        self._timer.stop()
        self._closed = True
        for d in self.owned + self._retired:
            try:
                d.close()
            except Exception:  # noqa: BLE001 – cleanup
                pass
        self.owned, self._retired = [], []
