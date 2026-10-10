# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Color conversion of the finished print PDF to an output profile.

Ghostscript (pdfwrite) converts to device colors with the admin profile; vectors
and text are preserved. To avoid double conversion, the admin can store driver
options per profile (e.g. the driver color matching OFF).
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
