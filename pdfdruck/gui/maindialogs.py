# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Main window: the dialogs it opens (print, plan, variable data, shrink, repair, settings, administration …) and the jobs that run in a separate process."""

from __future__ import annotations

import os

import pypdfium2.raw as pdfium_r
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QInputDialog,
    QMessageBox,
)

from ..l10n import tr
from . import lastdir
from .fileopen import load_pdf
from .icons import icon as svg_icon


class MainDialogsMixin:
    """Dialogs and background jobs of MainWindow."""

    # ================================================================ #
    def manip_dialog(self, mode: str = "all"):
        """Open the dialog for CMYK conversion and/or cropping."""
        if self.doc is None:
            return
        from .manipdialog import ManipDialog

        dlg = ManipDialog(self, self.doc, self.session, self.view.current, mode)
        if not dlg.exec() or not dlg.job:
            return
        suffix = {"cmyk": tr("_CMYK"), "crop": tr("_beschnitten")}.get(mode, tr("_bearbeitet"))
        title = {"cmyk": tr("CMYK"), "crop": tr("Beschneiden")}.get(mode, tr("Bearbeiten"))
        self.start_job(*dlg.job, suffix=suffix, title=title)

    def cut_dialog(self):
        """Open the dialog "CutContour erzeugen"."""
        if self.doc is None:
            return
        from .objectsdialog import CutContourDialog

        try:
            dlg = CutContourDialog(self, self.doc, self.view.current)
        except Exception as e:  # noqa: BLE001 – shown to the user
            from .objectsdialog import show_error

            show_error(self, tr("Fehler"), e)
            return
        if dlg.exec() and getattr(dlg, "job", None):
            self.start_job(
                *dlg.job,
                suffix=tr("_CutContour"),
                title=tr("CutContour"),
                notes=lambda info: [tr("{0} Schnittkontur(en) erzeugt.").format(info.get("cuts", 0))],
            )

    def vdp_dialog(self, data=None):
        """data = (csv_path, data kind) from "Enter data": adopt the table right away as the data source with a field."""
        if self.doc is None:
            return
        from .vdpdialog import VdpDialog

        try:
            dlg = VdpDialog(self, self.doc, self.view.current)
            if data:
                dlg.use_data(*data)
        except Exception as e:  # noqa: BLE001 – shown to the user
            from .objectsdialog import show_error

            show_error(self, tr("Fehler"), e)
            return
        if dlg.exec() and getattr(dlg, "job", None):
            self.start_job(
                *dlg.job,
                suffix=tr("_Daten"),
                title=tr("Variable Daten"),
                notes=lambda info: [
                    tr("{0} Datensätze, {1} Seiten erzeugt.").format(info.get("records", 0), info.get("pages", 0))
                ],
            )

    def data_dialog(self):
        """Create a data table; "Use for variable data" opens Variable Data with this table."""
        from .datadialog import DataDialog

        dlg = DataDialog(self)
        if not (dlg.exec() and dlg.use and dlg.path):
            return
        if self.doc is None:
            QMessageBox.information(
                self,
                tr("Daten erfassen"),
                tr(
                    "Die Tabelle ist gespeichert:\n{0}\n\nJetzt die Vorlage (PDF) öffnen und unter Variable Daten → "
                    "„CSV öffnen …“ diese Datei wählen."
                ).format(dlg.path),
            )
            return
        self.vdp_dialog((dlg.path, dlg.kind))

    def start_job(self, kind, settings, pages=None, suffix="", title="", notes=None, src_data=None):
        """Document into the cache, start the command line as its own process, show progress at the bottom."""
        from .. import jobproc, l10n
        from .jobs import JobReader, JobWidget

        base = os.path.splitext(self.display_name or "Dokument")[0]
        src = self.ctl.cache_file(base + "_eingabe.pdf")
        dst = self.ctl.cache_file(base + suffix + ".pdf")
        try:
            if src_data is not None:  # e.g. the file as on disk
                with open(src, "wb") as f:
                    f.write(src_data)
            else:
                self.doc.save(src)  # current state (including unsaved changes)
            open(dst, "wb").close()  # reserve names (several jobs at once)
            job = jobproc.JobProcess(kind, src, dst, settings, pages, lang=l10n.current())
            job.start()
        except Exception as e:  # noqa: BLE001 – shown to the user
            from .objectsdialog import show_error

            show_error(self, tr("Fehler"), e)
            return
        entry = {"job": job, "src": src, "dst": dst}
        widget = JobWidget(title or kind, lambda: self._cancel_job(entry))
        reader = JobReader(job)
        entry.update(widget=widget, reader=reader)
        reader.progress.connect(widget.set_progress)
        reader.finished_job.connect(lambda res: self._job_finished(entry, res, suffix, notes))
        self.statusBar().addWidget(widget)
        self._jobs.append(entry)
        reader.start()

    def start_export(self, out: str, settings: dict, pages: list[int]):
        """Export as images in the background (passermark-cli export); at the end a message with the files."""
        from .. import jobproc, l10n
        from .jobs import JobReader, JobWidget

        base = os.path.splitext(self.display_name or "Dokument")[0]
        src = self.ctl.cache_file(base + "_bild.pdf")
        try:
            self.doc.save(src)  # current state (including unsaved changes)
            job = jobproc.JobProcess(jobproc.EXPORT, src, out, settings, pages, lang=l10n.current())
            job.start()
        except Exception as e:  # noqa: BLE001 – shown to the user
            from .objectsdialog import show_error

            show_error(self, tr("Fehler"), e)
            return
        entry = {"job": job, "src": src, "dst": out}
        widget = JobWidget(tr("Als Bild exportieren"), lambda: self._cancel_job(entry))
        reader = JobReader(job)
        entry.update(widget=widget, reader=reader)
        reader.progress.connect(widget.set_progress)
        reader.finished_job.connect(lambda res: self._export_finished(entry, res))
        self.statusBar().addWidget(widget)
        self._jobs.append(entry)
        reader.start()

    def _export_finished(self, entry, res):
        if entry in self._jobs:
            self._jobs.remove(entry)
        self.statusBar().removeWidget(entry["widget"])
        entry["widget"].deleteLater()
        entry["reader"].wait(2000)
        try:
            os.remove(entry["src"])
        except OSError:
            pass
        ev = res.get("event")
        if ev == "cancelled":
            self.statusBar().showMessage(tr("Abgebrochen."), 6000)
            return
        if ev != "done":
            box = QMessageBox(
                QMessageBox.Icon.Critical, tr("Fehler"), res.get("message") or tr("Unbekannter Fehler"), parent=self
            )
            if res.get("details"):
                box.setDetailedText(res["details"])
            box.exec()
            return
        files = res.get("files") or []
        folder = os.path.dirname(files[0]) if files else os.path.dirname(entry["dst"])
        box = QMessageBox(
            QMessageBox.Icon.Information,
            tr("Als Bild exportieren"),
            tr("{0} Bild(er) gespeichert in:\n{1}").format(len(files), folder),
            parent=self,
        )
        if files:
            box.setDetailedText("\n".join(os.path.basename(f) for f in files))
        btn = box.addButton(tr("Ordner öffnen"), QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Ok)
        box.exec()
        if box.clickedButton() is btn:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices

            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _cancel_job(self, entry):
        entry["widget"].set_cancelling()
        entry["job"].cancel()

    def _job_finished(self, entry, res, suffix, notes):
        if entry in self._jobs:
            self._jobs.remove(entry)
        self.statusBar().removeWidget(entry["widget"])
        entry["widget"].deleteLater()
        entry["reader"].wait(2000)
        try:
            os.remove(entry["src"])
        except OSError:
            pass
        ev = res.get("event")
        if ev == "done":
            info = res.get("info") or {}
            extra = list(notes(info)) if notes else []
            self._open_result_path(entry["dst"], extra + list(res.get("notes") or []))
            return
        try:
            os.remove(entry["dst"])
        except OSError:
            pass
        if ev == "cancelled":
            self.statusBar().showMessage(tr("Abgebrochen."), 6000)
            return
        from .. import crashlog

        crashlog.record(
            f"Auftrag {entry['job'].kind} fehlgeschlagen (Code {res.get('returncode')}): {res.get('message')}",
            res.get("details") or "",
        )
        box = QMessageBox(
            QMessageBox.Icon.Critical, tr("Fehler"), res.get("message") or tr("Unbekannter Fehler"), parent=self
        )
        if res.get("details"):
            box.setDetailedText(res["details"])
        box.exec()

    def _stop_jobs(self):
        """Window is closing: cancel running jobs."""
        cp = self.__dict__.get("color_panel")
        if cp is not None:  # colour check in the background: cancel and wait
            if cp._worker is not None:
                cp._worker.cancel()
            for th in list(cp._threads):
                th.wait(10000)
        for entry in list(self._jobs):
            entry["job"].cancel()
        for entry in list(self._jobs):
            entry["reader"].wait(5000)

    def _open_result(self, new_doc, suffix: str, notes=()):
        """Write the result to the cache and open it from there in a new window."""
        base = os.path.splitext(self.display_name or "Dokument")[0]
        path = self.ctl.cache_file(base + suffix + ".pdf")
        try:
            new_doc.save(path)
        except Exception as e:  # noqa: BLE001 – shown to the user
            from .objectsdialog import show_error

            show_error(self, tr("Fehler"), e)
            return
        finally:
            new_doc.close()
        self._open_result_path(path, notes)

    def _open_result_path(self, path: str, notes=()):
        """Open the finished file from the cache in a new window (temporary, "Save as")."""
        doc = load_pdf(self, path)
        if doc is None:
            return
        w = self.ctl.new_window(tab_of=self)
        # temporary: no fixed location -> "Save" asks, closing reminds to save
        w._sources = [tr("Ergebnis aus {0}").format(self.path or self.display_name or "–")]
        w._set_doc(doc, None, os.path.basename(path), True)
        w._temp_path = path
        w._suggest_dir = os.path.dirname(self.path) if self.path else getattr(self, "_suggest_dir", "")
        w.raise_()
        msg = tr("Temporär im Zwischenspeicher – zum Behalten „Speichern unter …“.")
        if notes:
            msg += "  " + "  ".join(notes)
        w.statusBar().showMessage(msg, 20000)

    @staticmethod
    def _lang_pdf(path: str) -> str:
        """Language version of a manual (e.g. …-anleitung.en.pdf), otherwise the German one."""
        from .. import l10n

        lang = l10n.current()
        for code in (lang, "en"):  # interface language, then English instead of German
            if code and code != "de":
                root, ext = os.path.splitext(path)
                p = f"{root}.{code}{ext}"
                if os.path.isfile(p):
                    return p
        return path

    @staticmethod
    def cli_howto_path() -> str:
        """Manual for the command line in the program package (Linux installation, AppImage, Windows setup)."""
        from .. import __file__ as pkg

        return MainDialogsMixin._lang_pdf(os.path.join(os.path.dirname(pkg), "docs", "passermark-cli-anleitung.pdf"))

    def _open_cli_howto(self):
        p = self.cli_howto_path()
        if not os.path.isfile(p):
            QMessageBox.warning(self, tr("Hilfe"), tr("Anleitung nicht gefunden: {0}").format(p))
            return
        self.ctl.open_paths([p], tab_of=self)

    def _open_vdp_howto(self):
        from .. import examples

        p = MainDialogsMixin._lang_pdf(examples.VDP_HOWTO)
        if not os.path.isfile(p):
            QMessageBox.warning(self, tr("Hilfe"), tr("Anleitung nicht gefunden: {0}").format(p))
            return
        self.ctl.open_paths([p], tab_of=self)

    def _get_examples(self):
        """Copy the examples to the user folder, register the presets, open the template in a tab."""
        from .. import examples

        try:
            d = examples.install()
        except OSError as e:
            QMessageBox.critical(self, tr("Beispiele"), tr("Fehler: {0}").format(e))
            return
        self.ctl.open_paths([os.path.join(d, "vorlage-a6.pdf")], tab_of=self)
        QMessageBox.information(
            self,
            tr("Beispiele"),
            tr(
                "Die Beispiele liegen in:\n{0}\n\nDie Vorlage ist geöffnet. Unter Variable Daten (Strg+Umschalt+D) "
                "in der Preset-Leiste „Beispiel 1“ bis „Beispiel 4“ wählen – die CSV ist schon eingetragen.\n\n"
                "Im Ordner „ergebnis“ liegen die fertigen PDFs zum Vergleich, die Anleitung liegt daneben."
            ).format(d),
        )

    def _win_print_test(self):
        """Print one test page per method – shows what the driver can really do (blank sheets?)."""
        from PySide6.QtWidgets import QInputDialog

        from .. import printers, printers_win

        try:
            names = [p.name for p in printers.list_printers()]
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, tr("Windows-Druck testen"), str(e))
            return
        if not names:
            QMessageBox.information(self, tr("Windows-Druck testen"), tr("Kein Drucker gefunden."))
            return
        name, ok = QInputDialog.getItem(
            self,
            tr("Windows-Druck testen"),
            tr("Je Verfahren wird eine A4-Testseite gedruckt (4 Blätter).\nDrucker:"),
            names,
            0,
            False,
        )
        if not ok:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            res = printers_win.test_print(name)
        finally:
            QApplication.restoreOverrideCursor()
        lines = "\n".join(f"• {label}: {r}" for label, r in res)
        QMessageBox.information(
            self,
            tr("Windows-Druck testen"),
            tr("Gesendet an {0}:").format(name)
            + "\n"
            + lines
            + "\n\n"
            + tr(
                "Auf jedem Blatt steht das Verfahren. Wählen Sie unter Datei → Einstellungen → Drucken "
                "unter Windows das Verfahren, dessen Blatt richtig ankommt."
            ),
        )

    def copy_text(self):
        """Copy the selected text to the clipboard."""
        t = self.view.selected_text()
        if t:
            QApplication.clipboard().setText(t)
            self.statusBar().showMessage(tr("{0} Zeichen kopiert.").format(len(t)), 3000)

    def settings_dialog(self):
        """Open the program settings."""
        from .settingsdialog import SettingsDialog

        SettingsDialog(self).exec()

    def shrink_dialog(self):
        """Break down and reduce the file size – also for files that do not count as too large."""
        if self.doc is None:
            return
        from .shrinkdialog import ShrinkDialog

        data = self._file_bytes()
        dlg = ShrinkDialog(self, None, data)
        if dlg.exec():
            self.start_job("shrink", dlg.options(), suffix=tr("_klein"), title=tr("Datei verkleinern"), src_data=data)

    def repair_dialog(self):
        """Open the repair dialog for the current document."""
        import tempfile

        from .. import repair
        from .repairdialog import RepairDialog

        names, out_dir = {}, None
        if self.doc is None:
            files, _ = lastdir.getOpenFileNames(
                self, tr("PDFs reparieren / optimieren"), "", tr("PDF-Dateien (*.pdf *.PDF)")
            )
            if not files:
                return
        elif self.path and not self.modified and not repair.needs_password(self.path):
            files = [self.path]
        else:
            # current state (edited, from images, or unlocked) -> unencrypted working copy
            tmp = os.path.join(tempfile.mkdtemp(prefix="passermark-"), "dokument.pdf")
            self.doc.save(tmp, flags=pdfium_r.FPDF_REMOVE_SECURITY)
            files = [tmp]
            names = {tmp: self.display_name or "Dokument.pdf"}
            out_dir = (
                os.path.dirname(self.path) if self.path else getattr(self, "_suggest_dir", os.path.expanduser("~"))
            )
        RepairDialog(self, files, names, out_dir, open_cb=lambda p: self.ctl.open_paths([p], tab_of=self)).exec()

    def print_dialog(self):
        """Open the print dialog for the current document."""
        if self.doc is None:
            return
        from .printdialog import PrintDialog

        PrintDialog(
            self,
            self.doc,
            self.display_name,
            self.view.current,
            self.session,
            src_path=getattr(self.view, "_src_path", None),
            pinfo=getattr(self.view, "_pinfo", None),
        ).exec()

    def plan_dialog(self, kind: str = "plan", entry: dict | None = None):
        """Plan & Poster → plan/poster printing: own window, independent of this document (the open
        document is not taken over). entry: open an earlier print from the history.
        """
        from .plandialog import open_window

        open_window(self.session, self.ctl, entry.get("kind", kind) if entry else kind, entry)

    def send_to_plan(self, kind: str = "plan"):
        """Hand the open document over to plan or poster printing – as it is now: unchanged the file itself,
        edited (pages, crop, colour rules …) the current state as a copy in the cache (kept 14 days, so that the
        print history can reopen it)."""
        if self.doc is None:
            return
        from .plandialog import open_window

        path = self.path if self.path and not self.modified and self.path.lower().endswith(".pdf") else ""
        if not path or not os.path.isfile(path):
            try:
                path = handover_copy(self._doc_bytes(), self.display_name or "Dokument")
            except OSError as e:
                QMessageBox.warning(self, tr("Plan & Poster"), str(e))
                return
        open_window(self.session, self.ctl, kind, files=[path])

    def _fill_plan_history(self):
        """Plan & Poster → recent prints: plan and poster prints, newest first; clean-up at the bottom."""
        from .. import planhistory

        m = self.m_plan_hist
        m.clear()
        ents = planhistory.entries()
        if not ents:
            a = m.addAction(tr("Noch keine Drucke im Verlauf"))
            a.setEnabled(False)
            return
        for e in ents[:20]:
            pre = tr("Plan") if e.get("kind") != "poster" else tr("Poster")
            m.addAction(
                svg_icon("plan" if e.get("kind") != "poster" else "print"),
                f"{pre}: {planhistory.label(e)}",
                lambda e=e: self.plan_dialog(e.get("kind", "plan"), e),
            )
        m.addSeparator()
        m.addAction(tr("Verlauf aufräumen …"), self._clear_plan_history)

    def _clear_plan_history(self):
        from .. import planhistory
        from ..planprint import num as planhistory_num

        n = len(planhistory.entries())
        mb = round(planhistory.size_bytes() / 1e6, 1)
        if (
            QMessageBox.question(
                self,
                tr("Verlauf aufräumen"),
                tr("Alle {0} Plan- und Posterdrucke im Verlauf verwerfen ({1} MB)?").format(n, planhistory_num(mb)),
            )
            == QMessageBox.StandardButton.Yes
        ):
            planhistory.clear()
            self.statusBar().showMessage(tr("Verlauf aufgeräumt."), 5000)

    def rolls_dialog(self):
        """Open the dialog with the rolls of the printers."""
        from .. import printers as _pr
        from .. import printjob
        from .plansetup import RollsDialog

        try:
            names = [p.name for p in _pr.list_printers() if p.name != _pr.PDF_TARGET]
        except Exception:  # noqa: BLE001 – printer/driver query: works without the value
            names = []
        if not names:
            QMessageBox.information(self, tr("Rollen"), tr("Kein Drucker eingerichtet."))
            return
        cur = printjob.default_printer(self.session)
        if len(names) > 1:
            name, ok = QInputDialog.getItem(
                self, tr("Rollen"), tr("Drucker:"), names, names.index(cur) if cur in names else 0, False
            )
            if not ok:
                return
        else:
            name = names[0]
        RollsDialog(self, self.session, name).exec()

    def admin_dialog(self):
        """Open the management dialog and reload the configuration after saving."""
        from .admindialog import AdminDialog

        if AdminDialog(self, self.session).exec():
            self.ctl.reload_config()
            self.statusBar().showMessage(tr("Admin-Standards gespeichert und übernommen."), 6000)


HANDOVER_DAYS = 14


def handover_copy(data: bytes, name: str) -> str:
    """Write the current state of a document for plan/poster printing to the cache: <name>_bearbeitet.pdf
    (numbered if taken); copies older than HANDOVER_DAYS are removed."""
    import re
    import time

    from .. import platform as _platform

    d = os.path.join(_platform.user_cache_dir(), "plan-uebergabe")
    os.makedirs(d, exist_ok=True)
    now = time.time()
    for f in os.listdir(d):
        fp = os.path.join(d, f)
        try:
            if now - os.path.getmtime(fp) > HANDOVER_DAYS * 86400:
                os.remove(fp)
        except OSError:
            pass
    stem = re.sub(r"[^\w.\-]+", "_", os.path.splitext(os.path.basename(name))[0])[:60] or "Dokument"
    path = os.path.join(d, f"{stem}_{tr('bearbeitet')}.pdf")
    k = 2
    while os.path.exists(path):
        path = os.path.join(d, f"{stem}_{tr('bearbeitet')}-{k}.pdf")
        k += 1
    with open(path, "wb") as f:
        f.write(data)
    return path
