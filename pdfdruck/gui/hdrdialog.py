# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Rückfrage bei HDR-Fotos (Foto + graue Helligkeitskarte): beim Öffnen und in der Prüfung."""
from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QLabel, QRadioButton, QVBoxLayout

from .. import images
from ..l10n import tr
from . import theme


def hdr_options(parent, infos: list, names: str, default_dpi: float = 96.0, reject_text: str = "") -> dict | None:
    """Größe und „Karte einrechnen“ wählen. -> {"size", "merge"} oder None (abgelehnt/abgebrochen).
        infos: Angaben wie images.hdr_aux_info (die erste bestimmt die angezeigten Maße)."""
    info = infos[0]
    dlg = QDialog(parent)
    dlg.setWindowTitle(tr("HDR-Foto erkannt"))
    v = QVBoxLayout(dlg)
    lbl = QLabel(tr("{0} enthält neben dem Foto ein Zusatzbild ({1}: Helligkeitskarte für HDR-Bildschirme). "
                    "Ohne Reparatur wird es als zweite, graue Seite in anderer Größe geöffnet und gedruckt – "
                    "am Plotter kann das zu falschen Farben führen.").format(names, info["kind"]))
    lbl.setWordWrap(True)
    v.addWidget(lbl)
    aw, ah = images.hdr_size_mm(info, "aux", default_dpi)
    mw, mh = images.hdr_size_mm(info, "main", default_dpi)
    dpi_aux = info["main_px"][0] / (aw / 25.4)
    dpi_main = info["main_px"][0] / (mw / 25.4)
    rb_aux = QRadioButton(tr("Eine Seite, Größe wie das Zusatzbild: {0:.0f} × {1:.0f} mm ({2:.0f} dpi)").format(aw, ah, dpi_aux))
    rb_main = QRadioButton(tr("Eine Seite, Größe wie im Foto hinterlegt: {0:.0f} × {1:.0f} mm ({2:.0f} dpi)").format(mw, mh, dpi_main))
    rb_aux.setChecked(True)
    for rb in (rb_aux, rb_main):
        v.addWidget(rb)
    chk = QCheckBox(tr("Helligkeitskarte einrechnen (hellt die Lichter auf wie am HDR-Bildschirm)"))
    chk.setToolTip(tr("Aus: das Foto bleibt bit-genau unverändert. Ein: die Lichter werden aufgehellt und "
                      "für Papier zurückgerechnet (neu als JPEG gespeichert)."))
    v.addWidget(chk)
    if any(i.get("aux_mode") != "L" for i in infos):
        chk.hide()                           # farbiges Zusatzbild (z. B. 3D-Kamera): keine Helligkeitskarte
    note = QLabel(tr("Die Bildschärfe steckt im Foto – die Karte hat nur die halbe Auflösung und keine zusätzlichen Details."))
    note.setWordWrap(True)
    note.setStyleSheet(f"color: {theme.MUTED};")
    v.addWidget(note)
    bb = QDialogButtonBox()
    b_fix = bb.addButton(tr("Reparieren"), QDialogButtonBox.ButtonRole.AcceptRole)
    bb.addButton(reject_text or tr("Abbrechen"), QDialogButtonBox.ButtonRole.RejectRole)
    b_fix.setDefault(True)
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    v.addWidget(bb)
    if not dlg.exec():
        return None
    return {"size": "aux" if rb_aux.isChecked() else "main", "merge": chk.isChecked() and not chk.isHidden()}
