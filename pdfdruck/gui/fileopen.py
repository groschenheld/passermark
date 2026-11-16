# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Opening files: the file filter, loading PDFs, images and Office documents, and combining several files into one PDF."""

from __future__ import annotations

import os

import pypdfium2 as pdfium
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QInputDialog,
    QLineEdit,
    QMessageBox,
)

from .. import convert as _convert
from .. import images
from ..l10n import tr

_ALL_EXT = sorted({".pdf"} | images.IMAGE_EXT | _convert.OFFICE_EXT)


OPEN_FILTER = ";;".join(
    [
        tr("Alle unterstützten") + " (" + " ".join(f"*{e} *{e.upper()}" for e in _ALL_EXT) + ")",
        tr("PDF-Dateien (*.pdf *.PDF)"),
        tr("Bilder") + " (" + " ".join(f"*{e}" for e in sorted(images.IMAGE_EXT)) + ")",
        tr("Office-Dokumente") + " (" + " ".join(f"*{e}" for e in sorted(_convert.OFFICE_EXT)) + ")",
    ]
)


def merge_files(parent, ctl, paths: list[str]):
    """Any files in order into one PDF document. Returns (doc, notes) or (None, [])."""
    import shutil
    import tempfile

    from PySide6.QtWidgets import QApplication, QProgressDialog

    work = tempfile.mkdtemp(prefix="passermark-merge-")
    out = pdfium.PdfDocument.new()
    notes = []
    dlg = QProgressDialog(tr("Füge zusammen …"), tr("Abbrechen"), 0, len(paths), parent)
    dlg.setWindowModality(Qt.WindowModality.WindowModal)
    dlg.setMinimumDuration(300)
    try:
        for i, p in enumerate(paths):
            dlg.setValue(i)
            dlg.setLabelText((tr("Wandle um: ") if _convert.is_office(p) else tr("Füge hinzu: ")) + os.path.basename(p))
            QApplication.processEvents()
            if dlg.wasCanceled():
                out.close()
                return None, []
            try:
                part = load_any(parent, ctl, p, work, notes)
            except Exception as e:  # noqa: BLE001 – shown to the user
                lines = str(e).splitlines()
                box = QMessageBox(
                    QMessageBox.Icon.Warning,
                    tr("Umwandeln fehlgeschlagen"),
                    tr(
                        "„{0}“ konnte nicht umgewandelt werden.\n\nDiese Datei überspringen und mit den anderen weitermachen?"
                    ).format(os.path.basename(p)),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    parent,
                )
                box.setDetailedText("\n".join(lines))
                box.button(QMessageBox.StandardButton.Yes).setText(tr("Überspringen"))
                box.button(QMessageBox.StandardButton.No).setText(tr("Abbrechen"))
                r = box.exec()
                if r != QMessageBox.StandardButton.Yes:
                    out.close()
                    return None, []
                notes.append(tr("übersprungen: {0}").format(os.path.basename(p)))
                continue
            if part is None:  # password prompt cancelled
                notes.append(tr("übersprungen: {0} (Passwort)").format(os.path.basename(p)))
                continue
            out.import_pages(part)
            part.close()
        dlg.setValue(len(paths))
        return out, notes
    finally:
        dlg.close()
        shutil.rmtree(work, ignore_errors=True)


def ask_hdr(parent, paths: list[str], default_dpi: float = 96.0):
    """Report HDR photos with an extra image (gain map) and let the user choose the repair.
    -> options for images_to_document (None = no such images).
    """
    from .hdrdialog import hdr_options

    found = [(p, images.hdr_aux_info(p)) for p in paths]
    found = [(p, i) for p, i in found if i is not None]
    if not found:
        return None
    names = ", ".join(f"„{os.path.basename(p)}“" for p, _i in found[:3]) + (" …" if len(found) > 3 else "")
    opts = hdr_options(parent, [i for _p, i in found], names, default_dpi, tr("Unverändert öffnen (2 Seiten)"))
    return {"keep": True} if opts is None else opts


def load_any(parent, ctl, path, workdir=None, notes=None):
    """PDF (with password prompt), image or Office file -> pypdfium2 document (None = cancelled)."""
    import tempfile

    if images.is_image(path):
        doc = images.images_to_document([path], ctl.image_dpi, ask_hdr(parent, [path], ctl.image_dpi))
        rep = images.svg_report(path)  # SVG: which way and what got rasterised
        if rep is not None and notes is not None:
            if rep["method"] != "qt":
                notes.append(tr("{0}: als Vektoren geöffnet mit {1}").format(os.path.basename(path), rep["method"]))
            notes.extend(rep["notes"])
        return doc
    if _convert.is_office(path):
        from PySide6.QtWidgets import QApplication

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            pdf, used = _convert.office_to_pdf(
                path, workdir or tempfile.mkdtemp(prefix="passermark-conv-"), ctl.cfg.get("office_converter", "auto")
            )
        finally:
            QApplication.restoreOverrideCursor()
        if notes is not None:
            notes.append(tr("{0}: umgewandelt mit {1}").format(os.path.basename(path), used))
        # load into memory so the working folder may be deleted
        with open(pdf, "rb") as f:
            return pdfium.PdfDocument(f.read())
    return load_pdf(parent, path)


def load_pdf(parent, path: str):
    """Open a PDF, asking for a password if needed. None on cancel/error."""
    password = None
    while True:
        try:
            return pdfium.PdfDocument(path, password=password)
        except pdfium.PdfiumError as e:
            if "password" in str(e).lower():
                password, ok = QInputDialog.getText(
                    parent,
                    tr("Passwort"),
                    tr("Passwort für {0}:").format(os.path.basename(path)),
                    QLineEdit.EchoMode.Password,
                )
                if not ok:
                    return None
            else:
                QMessageBox.critical(parent, tr("Fehler"), tr("Kann {0} nicht öffnen:\n{1}").format(path, e))
                return None
