# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Main window: opening, saving and exporting, and the operations on pages (insert, delete, rotate, move, split)."""

from __future__ import annotations

import ctypes
import os

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_r
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMenu,
    QMessageBox,
)

from .. import convert as _convert
from .. import images
from ..l10n import tr
from .fileopen import OPEN_FILTER, ask_hdr, load_any, load_pdf
from . import lastdir
from .icons import icon as svg_icon
from .mergedialog import MergeDialog
from .thumbs import THUMB_W


class MainFileMixin:
    """Files and pages of MainWindow."""

    # ================================================================ #
    # Open
    # ================================================================ #
    def open_dialog(self):
        """Ask for files and open them."""
        paths, _ = lastdir.getOpenFileNames(self, tr("Öffnen"), os.path.dirname(self.path or ""), OPEN_FILTER)
        if paths:
            self.open_paths_here(paths)

    def open_paths_here(self, paths):
        """First document into this (empty) window, the rest into new windows.
        Several images at once become one document.
        """
        if self.doc is not None:
            self.ctl.open_paths(paths, tab_of=self)
            return
        imgs = [p for p in paths if images.is_image(p)]
        rest = [p for p in paths if not images.is_image(p)]
        if imgs:
            self.open_images(imgs)
        elif rest:
            self.open_any(rest.pop(0))
        if rest:
            self.ctl.open_paths(rest, tab_of=self)

    def _set_doc(self, doc, path, display, modified, keep_page=None, src=None, changed_pages=None):
        """src: bytes of the document if already available (saves the render process the intermediate save).
        changed_pages: pages that were edited – old preview/thumbnails stay as placeholders
        until the new ones are there (these pages first).
        """
        if self.doc is not None and self.doc is not doc:
            self.doc.close()
        same_count = self.doc is not None and changed_pages is not None and self.thumbs.count() == len(doc)
        new_file = bool(path) and path != getattr(self, "path", None)
        self.doc, self.path, self.display_name, self.modified = doc, path, display, modified
        if new_file:  # a document from another file was opened: dialogs start there next time (not on every edit)
            lastdir.remember(path)
        if src is None and not modified and path and path.lower().endswith(".pdf") and os.path.isfile(path):
            src = path  # unchanged: the render process reads the file itself
        self.view.set_document(doc, keep_page, src=src, changed_pages=changed_pages if same_count else None)
        n = len(doc)
        self.page_edit.set_count(n)
        if same_count:
            for i in range(self.thumbs.count()):  # old thumbnails stay until the new ones are there
                self.thumbs.item(i).setData(THUMB_W, None)
            self._requeue_thumbs()
            first = [i for i in changed_pages if i in self._thumb_queue]
            self._thumb_queue = first + [i for i in self._thumb_queue if i not in first]
        else:
            self._rebuild_thumbs()
        self._update_actions()
        self._update_title()
        self._page_changed(self.view.current)
        if hasattr(self, "_pf_timer"):
            self._pf_timer.start()  # document check in the background

    def open(self, path: str):
        """Open the file ``path`` in this window."""
        doc = load_pdf(self, path)
        if doc is not None:
            self._sources = []
            self._set_doc(doc, path, os.path.basename(path), False)

    def open_any(self, path: str):
        """Open PDFs directly, convert Office files and open them as (unsaved) PDFs."""
        if not _convert.is_office(path):
            self.open(path)
            return
        try:
            doc = load_any(self, self.ctl, path)
        except Exception as e:  # noqa: BLE001 – shown to the user
            QMessageBox.critical(self, tr("Umwandeln"), str(e))
            return
        self._sources = [tr("{0} (umgewandelt)").format(path)]
        self._set_doc(doc, None, os.path.splitext(os.path.basename(path))[0] + ".pdf", False)
        self._suggest_dir = os.path.dirname(path)
        lastdir.remember(path)

    def open_images(self, paths: list[str]):
        """Open several images as one document in this window."""
        try:
            doc = images.images_to_document(paths, self.ctl.image_dpi, ask_hdr(self, paths, self.ctl.image_dpi))
        except Exception as e:  # noqa: BLE001 – shown to the user
            QMessageBox.critical(self, tr("Bild öffnen"), str(e))
            return
        base = os.path.splitext(os.path.basename(paths[0]))[0]
        name = f"{base}.pdf" if len(paths) == 1 else f"{base} (+{len(paths) - 1} Bilder).pdf"
        self._sources = list(paths)
        self._set_doc(doc, None, name, False)
        self._suggest_dir = os.path.dirname(paths[0])
        lastdir.remember(paths[0])
        self._svg_hints(paths)

    def _svg_hints(self, paths: list[str]):
        """SVG: say how it was opened; if parts were rasterised, say so and why (not silently)."""
        warn, used = [], []
        for p in paths:
            rep = images.svg_report(p)
            if rep is None:
                continue
            used.append(rep["method"])
            warn += [f"{os.path.basename(p)}: {n}" for n in rep["notes"]]
        if warn:
            QMessageBox.information(self, tr("SVG geöffnet"), "\n\n".join(warn))
        elif used:
            self.statusBar().showMessage(
                tr("SVG als Vektoren geöffnet ({0})").format(", ".join(sorted(set(used)))), 8000
            )

    def properties_dialog(self):
        """Open the document properties."""
        if self.doc is None:
            return
        from .propsdialog import PropertiesDialog

        PropertiesDialog(self).exec()

    def merge_dialog(self):
        """Open the merge dialog and show the merged document."""
        dlg = MergeDialog(self, [self.path] if self.path and not self.modified else None)
        if not dlg.exec() or not dlg.paths():
            return
        self.ctl.merge_into_window(dlg.paths(), self if self.doc is None else None)

    def _load_any(self, path):
        return load_any(self, self.ctl, path)

    # ================================================================ #
    # save / export
    # ================================================================ #
    def _write(self, doc, path):
        """Save safely – even over the file that is just open."""
        tmp = path + ".pdfdruck-tmp"
        doc.save(tmp)
        return tmp

    def save(self):
        """Save to the current file (asks for a name if there is none). True if saved."""
        if self.doc is None:
            return False
        if not self.path:
            return self.save_as()
        return self._save_to(self.path)

    def save_as(self):
        """Ask for a file name and save. True if saved."""
        if self.doc is None:
            return False
        start = self.path or os.path.join(
            getattr(self, "_suggest_dir", os.path.expanduser("~")), self.display_name or "Dokument.pdf"
        )
        path, _ = lastdir.getSaveFileName(self, tr("Speichern unter"), start, tr("PDF-Dateien (*.pdf)"))
        if not path:
            return False
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        return self._save_to(path)

    def _save_to(self, path):
        cur = self.view.current
        try:
            tmp = self._write(self.doc, path)
            self.doc.close()  # release the file if it is the same one
            self.doc = None
            os.replace(tmp, path)
        except Exception as e:  # noqa: BLE001 – shown to the user
            QMessageBox.critical(self, tr("Speichern"), tr("Speichern fehlgeschlagen:\n{0}").format(e))
            if self.doc is None and self.path and os.path.exists(self.path):
                self.open(self.path)
            return False
        doc = load_pdf(self, path)
        if doc is None:
            return False
        self._set_doc(doc, path, os.path.basename(path), False, cur)
        self.statusBar().showMessage(tr("Gespeichert: {0}").format(path), 6000)
        return True

    def selected_pages(self) -> list[int]:
        """The pages selected in the sidebar; the current page if none is selected."""
        rows = sorted(self.thumbs.row(i) for i in self.thumbs.selectedItems())
        return rows or ([self.view.current] if self.doc is not None else [])

    def export_images(self):
        """File → Export as image: PNG/JPG/TIFF, one file per page – runs in the background (exportdialog.py)."""
        if self.doc is None:
            return
        from .exportdialog import ExportImageDialog, default_name

        sel = sorted(self.thumbs.row(i) for i in self.thumbs.selectedItems())
        dlg = ExportImageDialog(self, len(self.doc), self.view.current, sel)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        s, pages = dlg.result_settings(), dlg.result_pages()
        folder = os.path.dirname(self.path) if self.path else getattr(self, "_suggest_dir", "")
        ext = {"png": "*.png", "jpg": "*.jpg *.jpeg", "tiff": "*.tif *.tiff"}[s.format]
        path, _ = lastdir.getSaveFileName(
            self,
            tr("Als Bild exportieren"),
            default_name(self.display_name, s.format, folder),
            f"{s.format.upper()} ({ext})",
        )
        if not path:
            return
        from .. import rasterexport

        files = rasterexport.target_files(path, pages, s)
        taken = [f for f in files if os.path.exists(f)]
        if taken and (
            QMessageBox.question(
                self,
                tr("Als Bild exportieren"),
                tr("{0} Datei(en) gibt es schon, z. B. {1}. Überschreiben?").format(
                    len(taken), os.path.basename(taken[0])
                ),
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        settings = {k: v for k, v in vars(s).items() if k != "out"}
        self.start_export(path, settings, pages)

    def export_selection(self):
        """Export the selected pages as one PDF."""
        pages = self.selected_pages()
        if not pages:
            return
        base = os.path.splitext(self.display_name or "Dokument")[0]
        rng = f"S{pages[0] + 1}" if len(pages) == 1 else f"S{pages[0] + 1}-{pages[-1] + 1}"
        start = os.path.join(
            os.path.dirname(self.path) if self.path else getattr(self, "_suggest_dir", ""), f"{base}_{rng}.pdf"
        )
        path, _ = lastdir.getSaveFileName(
            self, tr("{0} Seite(n) exportieren").format(len(pages)), start, tr("PDF-Dateien (*.pdf)")
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        if self.path and os.path.abspath(path) == os.path.abspath(self.path):
            QMessageBox.warning(self, tr("Exportieren"), tr("Bitte nicht über das geöffnete Dokument exportieren."))
            return
        try:
            out = pdfium.PdfDocument.new()
            out.import_pages(self.doc, pages)
            out.save(path)
            out.close()
        except Exception as e:  # noqa: BLE001 – shown to the user
            QMessageBox.critical(self, tr("Exportieren"), tr("Export fehlgeschlagen:\n{0}").format(e))
            return
        QMessageBox.information(
            self, tr("Exportiert"), tr("{0} Seite(n) gespeichert als:\n{1}").format(len(pages), path)
        )

    def export_each(self):
        """Export every selected page as a PDF of its own."""
        pages = self.selected_pages()
        if not pages:
            return
        folder = lastdir.getExistingDirectory(
            self,
            tr("Zielordner für Einzelseiten"),
            os.path.dirname(self.path) if self.path else getattr(self, "_suggest_dir", ""),
        )
        if not folder:
            return
        base = os.path.splitext(self.display_name or "Dokument")[0]
        digits = max(3, len(str(len(self.doc))))
        names = [f"{base}_S{p + 1:0{digits}d}.pdf" for p in pages]
        exist = [n for n in names if os.path.exists(os.path.join(folder, n))]
        if (
            exist
            and QMessageBox.question(
                self,
                tr("Überschreiben?"),
                tr("{0} Datei(en) existieren bereits (z. B. {1}). Überschreiben?").format(len(exist), exist[0]),
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        done, errors = 0, []
        for p, name in zip(pages, names, strict=False):
            try:
                out = pdfium.PdfDocument.new()
                out.import_pages(self.doc, [p])
                out.save(os.path.join(folder, name))
                out.close()
                done += 1
            except Exception as e:  # noqa: BLE001 – shown to the user
                errors.append(f"{name}: {e}")
        if errors:
            QMessageBox.critical(
                self,
                tr("Exportieren"),
                tr("{0} gespeichert, {1} Fehler:\n").format(done, len(errors)) + "\n".join(errors[:8]),
            )
        else:
            QMessageBox.information(
                self,
                tr("Exportiert"),
                tr("{0} Einzelseite(n) gespeichert in:\n{1}\n\n{2}").format(done, folder, names[0])
                + (f" … {names[-1]}" if len(names) > 1 else ""),
            )

    # ================================================================ #
    # page operations
    # ================================================================ #
    def _changed_doc(self, keep_page=None, select=None):
        self.modified = True
        self._set_doc(
            self.doc, self.path, self.display_name, True, self.view.current if keep_page is None else keep_page
        )
        if select:
            self.thumbs.clearSelection()
            for i in select:
                if 0 <= i < self.thumbs.count():
                    self.thumbs.item(i).setSelected(True)

    def insert_dialog(self, where: str):
        """Ask for files and insert their pages (``where``: before, after or end)."""
        paths, _ = lastdir.getOpenFileNames(
            self, tr("Seiten einfügen aus …"), os.path.dirname(self.path or ""), OPEN_FILTER
        )
        if not paths:
            return
        sel = self.selected_pages()
        pos = {"before": sel[0] if sel else 0, "after": (sel[-1] + 1) if sel else len(self.doc), "end": len(self.doc)}[
            where
        ]
        start = pos
        try:
            for p in paths:
                part = self._load_any(p)
                if part is None:
                    return
                n = len(part)
                self.doc.import_pages(part, index=pos)
                part.close()
                pos += n
        except Exception as e:  # noqa: BLE001 – shown to the user
            QMessageBox.critical(self, tr("Einfügen"), str(e))
        self._changed_doc(start, list(range(start, pos)))
        self.statusBar().showMessage(tr("{0} Seite(n) eingefügt.").format(pos - start), 6000)

    def insert_blank(self, where: str, count: int = 1):
        """Blank page(s) before/after the selection – in the size of the neighbouring page (boxes and rotation
        included).
        """
        if self.doc is None:
            return
        from .. import pageops

        sel = self.selected_pages()
        n = len(self.doc)
        if where == "before":
            pos = sel[0] if sel else 0
            ref = pos if pos < n else n - 1
        else:
            pos = (sel[-1] + 1) if sel else n
            ref = pos - 1 if pos > 0 else 0
        try:
            k = pageops.insert_blank(self.doc, pos, ref if n else None, count)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, tr("Leerseite einfügen"), str(e))
            return
        self._changed_doc(pos, list(range(pos, pos + k)))
        self.statusBar().showMessage(tr("{0} Leerseite(n) eingefügt.").format(k), 6000)

    def delete_pages(self):
        """Delete the selected pages."""
        pages = self.selected_pages()
        if not pages:
            return
        if len(pages) >= len(self.doc):
            QMessageBox.warning(self, tr("Löschen"), tr("Es muss mindestens eine Seite übrig bleiben."))
            return
        if (
            QMessageBox.question(
                self,
                tr("Seiten löschen"),
                tr("{0} Seite(n) aus dem Dokument entfernen?\n(Die Datei ändert sich erst beim Speichern.)").format(
                    len(pages)
                ),
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        for i in reversed(pages):
            self.doc.del_page(i)
        self._changed_doc(min(pages[0], len(self.doc) - 1))

    def rotate_pages(self, delta: int):
        """Rotate the selected pages permanently by ``delta`` degrees."""
        pages = self.selected_pages()
        for i in pages:
            pg = self.doc[i]
            pg.set_rotation((pg.get_rotation() + delta) % 360)
            pg.close()
        self._changed_doc(select=pages)

    def move_pages(self, d: int):
        """Move the selected pages one position forwards or backwards."""
        pages = self.selected_pages()
        if not pages:
            return
        n = len(self.doc)
        dest = pages[0] + d
        if dest < 0 or dest + len(pages) > n:
            return
        arr = (ctypes.c_int * len(pages))(*pages)
        if not pdfium_r.FPDF_MovePages(self.doc.raw, arr, len(pages), dest):
            QMessageBox.warning(self, tr("Verschieben"), tr("Verschieben fehlgeschlagen."))
            return
        self._changed_doc(dest, list(range(dest, dest + len(pages))))

    def move_pages_to(self, pages: list, ins: int):
        """Sidebar: drag the selected pages to the insertion point (ins = before this page, len = at the end)."""
        if self.doc is None or not pages:
            return
        pages = sorted(set(p for p in pages if 0 <= p < len(self.doc)))
        dest = ins - sum(1 for p in pages if p < ins)  # index of the first page after moving
        dest = max(0, min(dest, len(self.doc) - len(pages)))
        if pages == list(range(dest, dest + len(pages))):
            return  # already there
        arr = (ctypes.c_int * len(pages))(*pages)
        if not pdfium_r.FPDF_MovePages(self.doc.raw, arr, len(pages), dest):
            QMessageBox.warning(self, tr("Verschieben"), tr("Verschieben fehlgeschlagen."))
            return
        self._changed_doc(dest, list(range(dest, dest + len(pages))))

    def _thumb_menu(self, pos):
        if self.doc is None:
            return
        it = self.thumbs.itemAt(pos)
        if it is not None and not it.isSelected():
            self.thumbs.clearSelection()
            it.setSelected(True)
        n = len(self.selected_pages())
        m = QMenu(self)
        m.addSection(tr("{0} Seite(n) ausgewählt").format(n))
        for a in (
            self.a_ins_before,
            self.a_ins_after,
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
        ):
            m.addSeparator() if a is None else m.addAction(a)
        sm = m.addMenu(svg_icon("split"), tr("Teilen"))
        sm.addAction(tr("Senkrecht halbieren (links | rechts)"), lambda: self.split_selected("halves_v"))
        sm.addAction(tr("Waagrecht halbieren (oben / unten)"), lambda: self.split_selected("halves_h"))
        sm.addSeparator()
        sm.addAction(tr("Raster / weitere Optionen …"), lambda: self.split_dialog(selection=True))
        m.addSeparator()
        m.addAction(self.a_delete)
        m.exec(self.thumbs.mapToGlobal(pos))

    def separate_dialog(self):
        """Open the dialog "Objekte trennen"."""
        if self.doc is None:
            return
        from .objectsdialog import SeparateDialog

        dlg = SeparateDialog(self, self.doc, self.view.current)
        if dlg.exec() and getattr(dlg, "job", None):
            self.start_job(
                *dlg.job,
                suffix=tr("_einzeln"),
                title=tr("Objekte trennen"),
                notes=lambda info: [tr("{0} Objekt(e) als Einzelseiten.").format(info.get("objects", 0))],
            )

    def split_selected(self, mode: str):
        """Right-click → Split: immediately halve the selected pages (no dialog, no comparison page)."""
        if self.doc is None:
            return
        from .. import core, split

        pages = self.selected_pages()
        if not pages:
            return
        self.start_job(
            "split",
            core.settings_to_dict(split.SplitSettings(mode=mode)),
            pages,
            suffix=tr("_geteilt"),
            title=tr("Seiten teilen"),
        )

    def split_dialog(self, selection: bool = False):
        """Open the dialog "Seiten teilen" (``selection``: only for the selected pages)."""
        if self.doc is None:
            return
        from .splitdialog import SplitDialog

        dlg = SplitDialog(
            self, self.doc, self.view.current, self.selected_pages(), which="selected" if selection else "all"
        )
        if dlg.exec() and getattr(dlg, "job", None):
            self.start_job(*dlg.job, suffix=tr("_geteilt"), title=tr("Seiten teilen"))

    def split_spreads(self):
        """One click: halve all double pages vertically (e.g. a booklet exported as press sheets)."""
        if self.doc is None:
            return
        from .. import core, split

        sizes = [self.doc.get_page_size(i) for i in range(len(self.doc))]
        if not split.spreads(sizes, 2, 1):
            QMessageBox.information(
                self,
                tr("Doppelseiten teilen"),
                tr(
                    "Keine Doppelseiten gefunden – keine Seite ist doppelt so breit wie die übrigen. Für andere Fälle: "
                    "Seiten → Seiten teilen …"
                ),
            )
            return
        self.start_job(
            "split",
            core.settings_to_dict(split.SplitSettings(only_spreads=True)),
            None,
            suffix=tr("_geteilt"),
            title=tr("Doppelseiten teilen"),
        )

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        paths = [p for p in paths if _convert.is_supported(p)]
        if not paths:
            return
        if self.doc is not None and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Ctrl + drop = append to the current document
            start = len(self.doc)
            for p in paths:
                part = self._load_any(p)
                if part is not None:
                    self.doc.import_pages(part)
                    part.close()
            self._changed_doc(start, list(range(start, len(self.doc))))
        else:
            self.open_paths_here(paths)

    # ------------------------------------------------------------------ #
    # page boxes, search and replace, before/after

    def _take_bytes(self, data: bytes, keep_page: int):
        """Show ``data`` as the new (unsaved) state of the document."""
        import pypdfium2 as pdfium

        self._set_doc(pdfium.PdfDocument(data), self.path, self.display_name, True, keep_page=keep_page, src=data)

    def page_boxes_dialog(self):
        """Set the trim format (final format and bleed) – trim and bleed box, excess sheet cut off."""
        if self.doc is None:
            return
        from .. import pageboxes
        from .pageboxdialog import PageBoxDialog

        data = self._doc_bytes()
        cur = self.view.current
        dlg = PageBoxDialog(self, data, cur, len(self.doc), self.selected_pages())
        if not dlg.exec():
            return
        w, h, bleed, cut = dlg.result_params()
        try:
            new, notes = pageboxes.apply_format(data, dlg.result_pages(), w, h, bleed, cut)
        except ValueError as e:
            QMessageBox.warning(self, tr("Endformat festlegen"), str(e))
            return
        self._take_bytes(new, cur)
        if notes:
            QMessageBox.information(self, tr("Endformat festlegen"), "\n\n".join(notes))
        self.statusBar().showMessage(tr("Endformat festgelegt – gespeichert wird beim Speichern."), 6000)

    def find_replace_dialog(self):
        """Search a text in the document and replace it (original font)."""
        if self.doc is None:
            return
        import pypdfium2 as pdfium

        from .findreplacedialog import FindReplaceDialog

        cur = self.view.current
        work = pdfium.PdfDocument(self._doc_bytes())  # on a copy: "Schließen" without replacing changes nothing
        dlg = FindReplaceDialog(self, work, cur)
        dlg.exec()
        if dlg.changed:
            import io

            buf = io.BytesIO()
            work.save(buf)
            self._take_bytes(buf.getvalue(), cur)
            self.statusBar().showMessage(tr("{0} Stelle(n) ersetzt.").format(dlg.changed), 6000)
        work.close()

    def compare_dialog(self):
        """The saved file next to the current state, differences marked."""
        if self.doc is None:
            return
        p = self.path
        if not (p and p.lower().endswith(".pdf") and os.path.isfile(p)):
            QMessageBox.information(
                self,
                tr("Vorher/Nachher vergleichen"),
                tr("Verglichen wird mit der gespeicherten PDF-Datei – dieses Dokument wurde noch nicht gespeichert."),
            )
            return
        with open(p, "rb") as f:
            before = f.read()
        from .comparedialog import CompareDialog

        dlg = CompareDialog(self, before, self._doc_bytes(), self.view.current, len(self.doc))
        dlg.resize(1100, 800)
        dlg.exec()
