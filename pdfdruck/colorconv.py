# SPDX-License-Identifier: GPL-3.0-or-later
# pdfToolkit – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Farbkonvertierung des fertigen Druck-PDFs auf ein Ausgabeprofil.

Ghostscript (pdfwrite) rechnet mit dem Admin-Profil in Gerätefarben um; Vektoren
und Text bleiben erhalten. Damit nicht doppelt konvertiert wird, kann der Admin
pro Profil Treiberoptionen hinterlegen (z. B. Farbabgleich des Treibers AUS).
"""
from __future__ import annotations

from .l10n import tr

import shutil
import subprocess

INTENT_NUM = {"perceptual": 0, "relative": 1, "saturation": 2, "absolute": 3}


def icc_colorspace(path: str) -> str:
    """'RGB' | 'CMYK' | 'Gray' aus dem ICC-Header; ValueError wenn kein ICC."""
    with open(path, "rb") as f:
        head = f.read(40)
    if len(head) < 40 or head[36:40] != b"acsp":
        raise ValueError(tr("{0} ist kein ICC-Profil").format(path))
    cs = head[16:20]
    space = {b"RGB ": "RGB", b"CMYK": "CMYK", b"GRAY": "Gray"}.get(cs)
    if space is None:
        raise ValueError(tr("Farbraum {0!r} nicht unterstützt").format(cs))
    return space


def convert(src: str, dst: str, icc: str, intent: str = "relative", bpc: bool = True) -> None:
    from . import platform as _platform
    gs = _platform.ghostscript()
    if not gs:
        raise RuntimeError(tr("Ghostscript (gs) ist nicht installiert."))
    space = icc_colorspace(icc)
    cmd = [
        gs, "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", f"--permit-file-read={icc}",
        "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.7", "-dAutoRotatePages=/None",
        f"-sColorConversionStrategy={space}", f"-sOutputICCProfile={icc}",
        f"-dRenderIntent={INTENT_NUM.get(intent, 1)}",
        f"-dBlackPtComp={1 if bpc else 0}",
        "-o", dst, src,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(tr("Ghostscript-Fehler:\n") + (r.stderr or r.stdout)[-2000:])
