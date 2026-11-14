# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Print dialog: the sheet preview – rendering in the background, paging through sheets, overview, soft proof and the info lines."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QVBoxLayout,
)

from .. import config, layout, printers, proof
from ..l10n import tr
from . import theme
from .common import render_pixmap


class PrintPreviewMixin:
    """Sheet preview of PrintDialog."""

    def _update_preview(self):
        self.lbl_warn.clear()
        try:
            pages = self._pages()
            self.ed_range.setStyleSheet("")
        except ValueError as e:
            self.ed_range.setStyleSheet(f"background: {theme.INVALID_FIELD};")
            self.lbl_warn.setText(str(e))
            self.plans = []
            self.preview.set_content(None, None, False)
            return
        try:
            self.plans = self._make_plans(pages)
        except ValueError as e:
            self.lbl_warn.setText(str(e))
            self.plans = []
        self.sheet_index = min(self.sheet_index, max(0, len(self.plans) - 1))
        try:
            self._render_sheet()
        except Exception as e:  # the preview must never take the program down with it
            self.lbl_warn.setText(tr("Vorschau nicht möglich: {0}").format(e))

    def _pair_step(self) -> int:
        """The duplex preview shows front AND back: then page through sheet by sheet (2 pages)."""
        try:
            return 2 if self._duplex_layout() else 1
        except Exception:
            return 1

    def _step_sheet(self, d: int):
        st = self._pair_step()
        i = self.sheet_index - (self.sheet_index % st) + d * st
        self._goto_sheet(max(0, min(i, len(self.plans) - 1)))

    def _goto_sheet(self, i):
        if 0 <= i < len(self.plans):
            self.sheet_index = i
            self._render_sheet()

    def _sheet_overview(self):
        """All sheets as thumbnails (reading order) – shows the distribution of the pages at a glance.
        Rendered in the render process: the window stays usable, also with many sheets.
        """
        if not self.plans:
            QMessageBox.information(self, tr("Bogenübersicht"), tr("Keine Seiten"))
            return
        if getattr(self, "_ov_busy", False):
            return
        s = self._eff_settings()
        plans = self.plans[:400]
        rots = [90 if sp.landscape else 0 for sp in plans]
        labels = [sp.label or tr("Blatt {0}").format(i + 1) for i, sp in enumerate(plans)]
        if layout.is_step2(s) and getattr(self, "plans2", None):
            sheet = layout.step2_sheet(s)
            req = dict(
                mode="step2",
                sheet=None,
                plans=None,
                settings=s,
                only=None,
                sheet1=self._sheet(),
                plans1=self.plans1,
                plans2=self.plans2,
            )

            def make():
                return layout.impose_step2(self._print_doc(), self._sheet(), self.plans1, s, plans2=self.plans2)
        else:
            sheet = self._sheet()
            req = dict(mode="sheet", sheet=sheet, plans=self.plans, settings=s, only=None)

            def make():
                return layout.impose_with(self._print_doc(), sheet, self.plans, s)

        scale = 150 / max(sheet.width, sheet.height)
        req.update(scale=scale, rotations=rots, limit=400, proof=False)

        def local():
            out = make()
            try:
                return [
                    self._local_pixmap(out, k, scale, rots[k], 1.0, proof=False)
                    for k in range(min(len(out), len(plans)))
                ]
            finally:
                out.close()

        def show(pms):
            self._ov_busy = False
            QApplication.restoreOverrideCursor()
            self._show_overview(list(zip(pms, labels, strict=False)))

        def failed(msg):
            self._ov_busy = False
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, tr("Bogenübersicht"), msg)

        self._ov_busy = True
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self._pv_call(req, 1.0, show, local, failed)

    def _show_overview(self, thumbs):
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QListView, QListWidget, QListWidgetItem

        dlg = QDialog(self)
        dlg.setWindowTitle(tr("Bogenübersicht – Passermark"))
        dlg.resize(980, 700)
        v = QVBoxLayout(dlg)
        lw = QListWidget()
        lw.setViewMode(QListView.ViewMode.IconMode)
        lw.setIconSize(QSize(160, 160))
        lw.setGridSize(QSize(200, 215))
        lw.setResizeMode(QListView.ResizeMode.Adjust)
        lw.setMovement(QListView.Movement.Static)
        lw.setWordWrap(True)
        for pm, text in thumbs:
            lw.addItem(QListWidgetItem(QIcon(pm), text))
        lw.itemDoubleClicked.connect(lambda it: (self._goto_sheet(lw.row(it)), dlg.accept()))
        v.addWidget(lw, 1)
        hint = QLabel(tr("Doppelklick springt zu diesem Bogen in der Vorschau."))
        hint.setStyleSheet(f"color: {theme.MUTED};")
        v.addWidget(hint)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        dlg.exec()

    def _pv_service(self):
        if os.environ.get("PASSERMARK_RENDER", "") == "local":
            return None
        src = self._pv_source()
        if src is None:
            return None
        from .renderclient import RenderService

        svc = RenderService.get()
        return svc if svc.ok else None

    def _pv_source(self):
        """(file, flatten?) with exactly the content that is imposed – or None (then in the program)."""
        if getattr(self, "_spr_active", False) and getattr(self, "_spr_doc", None) is not None:
            if self._spr_file is None:
                import tempfile

                try:
                    fd, path = tempfile.mkstemp(prefix="passermark-view-print-", suffix=".pdf")
                    with os.fdopen(fd, "wb") as f:
                        self._spr_doc.save(f)
                    self._spr_file = path
                except Exception:
                    return None
            return self._spr_file, False
        if self.src_path and os.path.isfile(self.src_path):
            return self.src_path, True
        return None

    def _drop_spr_file(self):
        f, self._spr_file = self._spr_file, None
        if f:
            try:
                os.remove(f)
            except OSError:
                pass

    def _pv_proof(self):
        """Proof values for the render process (None = without) – also sets the proof line."""
        if not self.chk_proof.isChecked():
            self.lbl_proof.setText("")
            return None
        adj, icc, intent, bpc, name = self._proof_params()
        if not icc and not adj["labels"]:
            self.lbl_proof.setText("")
            return None
        self.lbl_proof.setText(proof.describe(adj, name) + ("" if icc else tr("  (Treiberregler: Annäherung)")))
        return (adj, icc, intent, bpc)

    def _local_pixmap(self, out, k, scale, rot, dpr, proof=True):
        pg = out[k]
        try:
            return self._proofed_pixmap(pg, scale, rot, dpr) if proof else render_pixmap(pg, scale, rot, dpr)
        finally:
            pg.close()

    def _pv_request(self, req, dpr, show, local):
        """Request a preview sheet. If one is already running, only the newest waits (others are dropped)."""
        self._pv_gen += 1
        gen = self._pv_gen

        def done(pms):
            if gen == self._pv_gen:
                show(pms)

        def failed(msg):
            if gen == self._pv_gen:
                self.lbl_warn.setText(tr("Vorschau nicht möglich: {0}").format(msg))

        self._pv_call(req, dpr, done, local, failed)

    def _pv_call(self, req, dpr, show, local, failed):
        job = (req, dpr, show, local, failed)
        if self._pv_busy:
            # per kind only the newest waits (preview replaces preview; the overview is kept)
            self._pv_next[req.get("proof", True)] = job
            return
        self._pv_send(job)

    def _pv_send(self, job):
        req, dpr, show, local, failed = job
        svc = self._pv_service()
        if svc is None:
            try:
                show(local())
            except Exception as e:  # the preview must never take the program down with it
                failed(str(e))
            return
        path, flat = self._pv_source()
        args = {k: v for k, v in req.items() if k != "proof"}
        args.update(path=path, flatten=flat, proof_args=self._pv_proof() if req.get("proof", True) else None)
        self._pv_busy = True
        self._pv_used = True

        def back(err, res):
            self._pv_busy = False
            if getattr(self, "_pv_closed", False):
                return
            nxt = self._pv_next.pop(True, None) or self._pv_next.pop(False, None)
            try:
                if err:
                    if "unavailable" in str(err) or "ended" in str(err):
                        show(local())  # process gone: in the program
                    else:
                        failed(str(err))
                else:
                    show([self._to_pixmap(w, h, data, dpr) for (w, h, data) in res])
            except Exception as e:
                failed(str(e))
            if nxt is not None:
                self._pv_send(nxt)

        try:
            svc.call("sheet", args, back)
        except Exception as e:
            self._pv_busy = False
            failed(str(e))

    @staticmethod
    def _to_pixmap(w, h, data, dpr):
        from PySide6.QtGui import QImage, QPixmap

        qi = QImage(data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
        pm = QPixmap.fromImage(qi)
        pm.setDevicePixelRatio(dpr)
        return pm

    def _render_sheet2(self, s):
        """Preview of the step 2 sheet: finished sheets imposed on the target size, centred."""
        n = len(self.plans)
        if n:
            lab = self.plans[self.sheet_index].label
            self.lbl_sheet.setText(
                tr("Zielformat (Schritt 2): Blatt {0} von {1}").format(self.sheet_index + 1, n)
                + (f"\n{lab}" if lab else "")
            )
        else:
            self.lbl_sheet.setText(tr("Keine Seiten"))
        self.btn_prev.setEnabled(self.sheet_index > 0)
        self.btn_next.setEnabled(self.sheet_index < n - 1)
        if not n:
            self.preview.set_content(None, None, False)
            return
        sheet = layout.step2_sheet(s)
        sp = self.plans[self.sheet_index]
        # The same path as for the output: save the step 1 sheet flat to a temporary file,
        # then impose – preview and result are identical
        target_h = max(200, self.preview.height() - 32)
        ph = sheet.width if sp.landscape else sheet.height
        scale = target_h / ph
        dpr = self.devicePixelRatioF()
        sheet1, plans1, plans2, only = self._sheet(), self.plans1, self.plans2, [self.sheet_index]
        rots = [90 if sp.landscape else 0]

        def show(pms, sheet=sheet, land=sp.landscape):
            self.preview.set_content(pms[0], sheet, land)

        def local():
            out = layout.impose_step2(self._print_doc(), sheet1, plans1, s, plans2=plans2, only=only)
            try:
                return [self._local_pixmap(out, 0, scale, rots[0], dpr)]
            finally:
                out.close()

        self._pv_request(
            dict(
                mode="step2",
                sheet=None,
                plans=None,
                settings=s,
                only=only,
                scale=scale * dpr,
                rotations=rots,
                sheet1=sheet1,
                plans1=plans1,
                plans2=plans2,
            ),
            dpr,
            show,
            local,
        )
        cols = len({round(pl.x, 1) for pl in sp.placements}) or 1
        rows = len({round(pl.y, 1) for pl in sp.placements}) or 1
        sw, sh = self._sheet().width / layout.MM, self._sheet().height / layout.MM
        self.lbl_info.setText(
            tr(
                "Schritt 2 – Zielformat: {0:.0f} × {1:.0f} mm · {2} × {3} Bögen ({4:.0f} × {5:.0f} mm) je Blatt{6}"
            ).format(
                sheet.width / layout.MM,
                sheet.height / layout.MM,
                cols,
                rows,
                sw,
                sh,
                tr(" · quer") if sp.landscape else "",
            )
        )
        warns = sorted(
            {w for p in self.plans for w in p.warnings} | {w for p in (self.plans1 or []) for w in p.warnings}
        )
        self.lbl_warn.setText("\n".join(warns[:4]) + (" …" if len(warns) > 4 else ""))

    def _render_sheet(self):
        """Show the current sheet in the preview and describe it below (paper, scale, arrangement, warnings)."""
        s = self._eff_settings()
        if layout.is_step2(s) and getattr(self, "plans2", None):
            return self._render_sheet2(s)
        n = len(self.plans)
        st = self._pair_step() if n else 1
        if st == 2:  # duplex: always start at the front side of a sheet
            self.sheet_index -= self.sheet_index % 2
        self._show_sheet_label(n, st)
        self.btn_prev.setEnabled(self.sheet_index > 0)
        self.btn_next.setEnabled(self.sheet_index + st < n)
        if not n:
            self.preview.set_content(None, None, False)
            return
        sheet = self._sheet()
        sp = self.plans[self.sheet_index]
        self._request_sheet_preview(sheet, sp)
        self._show_sheet_info(s, sheet, sp)

    def _show_sheet_label(self, n: int, st: int):
        """ "Sheet x of y" above the preview; st = 2 when front and back are shown together."""
        if n:
            lab = self.plans[self.sheet_index].label
            if st == 2:
                self.lbl_sheet.setText(
                    tr("Bogen {0} von {1} (Vorder- und Rückseite)").format(self.sheet_index // 2 + 1, (n + 1) // 2)
                    + (f"\n{lab}" if lab else "")
                )
            else:
                self.lbl_sheet.setText(
                    tr("Blatt {0} von {1}").format(self.sheet_index + 1, n) + (f"\n{lab}" if lab else "")
                )
        else:
            self.lbl_sheet.setText(tr("Keine Seiten"))

    def _request_sheet_preview(self, sheet, sp):
        """Have the sheet rendered (in the background, or here if that is not possible) and show it when ready."""
        target_h = max(200, self.preview.height() - 32)
        ph = sheet.width if sp.landscape else sheet.height
        scale = target_h / ph
        dpr = self.devicePixelRatioF()
        # duplex: show the back side of the sheet too (position depends on the flip edge)
        back_side = self._duplex_layout()
        only, rots = [self.sheet_index], [90 if sp.landscape else 0]
        if back_side and self.sheet_index + 1 < len(self.plans):
            only.append(self.sheet_index + 1)
            rots.append(90 if self.plans[self.sheet_index + 1].landscape else 0)
        settings, plans = self._settings(), self.plans

        def show(pms, sheet=sheet, land=sp.landscape, back_side=back_side):
            back = pms[1] if len(pms) > 1 else None
            self.preview.set_content(pms[0], sheet, land, back, back_side if back is not None else None)

        def local():
            out = layout.impose_with(self._print_doc(), sheet, plans, settings, only=only)
            try:
                return [self._local_pixmap(out, k, scale, rots[k], dpr) for k in range(len(only))]
            finally:
                out.close()

        self._pv_request(
            dict(
                mode="sheet", sheet=sheet, plans=plans, settings=settings, only=only, scale=scale * dpr, rotations=rots
            ),
            dpr,
            show,
            local,
        )

    def _size_text(self, sp) -> str:
        """Size of the first page on the sheet; also fills the hints below "step and repeat" and "custom scale"."""
        size_txt = ""
        if sp.placements:
            pl = sp.placements[0]
            _sz = self._spr_sizes if getattr(self, "_spr_active", False) else self.sizes
            ow, oh = _sz[pl.src]
            # display in the reading direction of the page (not rotated), to 0.1 mm
            nw, nh = (pl.h, pl.w) if pl.rot == 90 else (pl.w, pl.h)
            size_txt = tr("Seite {0}: {1:.1f} × {2:.1f} mm → {3:.1f} × {4:.1f} mm auf dem Blatt").format(
                pl.src + 1, ow / layout.MM, oh / layout.MM, nw / layout.MM, nh / layout.MM
            )
            if self.chk_sr.isChecked():
                n = len(sp.placements)
                self.lbl_srsize.setText(
                    tr("je Nutzen {0:.1f} × {1:.1f} mm ({2:.1f} %) · {3} Nutzen pro Blatt – Seite {4}").format(
                        nw / layout.MM, nh / layout.MM, pl.scale * 100, n, pl.src + 1
                    )
                )
            elif self.rb_custom.isChecked() and not self._settings().is_nup:
                self.lbl_custom.setText(
                    tr("ergibt {0:.1f} × {1:.1f} mm ({2:.1f} %) – Seite {3}").format(
                        nw / layout.MM, nh / layout.MM, pl.scale * 100, pl.src + 1
                    )
                )
        return size_txt

    def _join_text(self, s) -> str:
        """Arrangement and gaps for several pages per sheet / step and repeat."""
        # Effective step-and-repeat arrangement + gaps (step and repeat/several): cell gap
        # = distance of the cut lines; white gap = visibly free space between
        # the cards (the mirrored bleed fills the rest)
        join_txt = ""
        if s.handling == "multiple" or s.step_repeat:
            names = {"edge": tr("Kante an Kante"), "bleed": tr("Überfüller an Überfüller"), "gap": tr("Mit Abstand")}
            if s.step_repeat:
                cell_gap = layout._sr_gap(s)
            elif s.sr_join == "edge":
                cell_gap = 0.0
            elif s.sr_join == "gap":
                cell_gap = s.sr_gap_mm + 2 * s.bleed_mm
            else:
                cell_gap = max(s.gap_mm, 2 * s.bleed_mm)
            white = cell_gap - 2 * s.bleed_mm
            join_txt = tr(" · Anordnung: {0} · Zellabstand: {1:.1f} mm").format(
                names.get(s.sr_join, s.sr_join), cell_gap
            )
            if s.bleed_mm > 0 and white > 0.05:
                join_txt += tr(" (davon {0:.1f} mm sichtbar weiß)").format(white)
        return join_txt

    def _show_sheet_info(self, s, sheet, sp):
        """The lines below the preview: paper, tray, orientation, scale, arrangement, size – and the warnings."""
        key = self.caps.roles.get("pagesize")
        fmt = self.caps.options[key].choices if key else []
        fmt_txt = next((c.text for c in fmt if c.value == self.values.get(key)), "")
        src_key = self.caps.roles.get("source")
        src_txt = ""
        if src_key:
            src_txt = next(
                (c.text for c in self.caps.options[src_key].choices if c.value == self.values.get(src_key)), ""
            )
        scales = sorted({round(p.scale * 100, 1) for p in sp.placements})
        size_txt = self._size_text(sp)
        join_txt = self._join_text(s)
        self.lbl_info.setText(
            tr("Papier: {0} ({1:.0f} × {2:.0f} mm)").format(fmt_txt, sheet.width / layout.MM, sheet.height / layout.MM)
            + (tr(" · Fach: {0}").format(src_txt) if src_txt else "")
            + " · "
            + (tr("Querformat") if sp.landscape else tr("Hochformat"))
            + tr(" · Maßstab: {0}").format(", ".join(f"{s:g} %" for s in scales))
            + join_txt
            + (f"\n{size_txt}" if size_txt else "")
        )
        warns = sorted({w for p in self.plans for w in p.warnings})
        note = printers.size_note(self.caps, self.values, fmt_txt)  # "Wie Dokument" (PDF): no warning
        if note:
            warns.insert(0, note)
        self.lbl_warn.setText("\n".join(warns[:4]) + (" …" if len(warns) > 4 else ""))

    def _proof_params(self):
        """(adjustments, ICC path, intent, BPC, profile name) for the current selection."""
        adj = proof.adjustments(self.caps, self.values)
        pid = self.cmb_profile.currentData() or ""
        prof = config.profile_by_id(self.cfg, pid) if pid else None
        icc = prof.get("file") if prof else None
        intent = self.cmb_intent.currentData() or "relative"
        bpc = bool(prof.get("bpc", True)) if prof else True
        name = (prof.get("name") or pid) if prof else None
        return adj, icc, intent, bpc, name

    def _proofed_pixmap(self, page, scale, rotation, dpr):
        if not self.chk_proof.isChecked():
            self.lbl_proof.setText("")
            return render_pixmap(page, scale, rotation, dpr)
        adj, icc, intent, bpc, name = self._proof_params()
        if not icc and not adj["labels"]:
            self.lbl_proof.setText("")
            return render_pixmap(page, scale, rotation, dpr)
        from PySide6.QtGui import QImage, QPixmap

        bmp = page.render(scale=scale * dpr, rotation=rotation, may_draw_forms=True, draw_annots=True)
        img = proof.apply(bmp.to_pil(), adj, icc, intent, bpc)
        bmp.close()
        data = img.tobytes("raw", "RGB")
        qi = QImage(data, img.width, img.height, 3 * img.width, QImage.Format.Format_RGB888).copy()
        pm = QPixmap.fromImage(qi)
        pm.setDevicePixelRatio(dpr)
        self.lbl_proof.setText(proof.describe(adj, name) + ("" if icc else tr("  (Treiberregler: Annäherung)")))
        return pm
