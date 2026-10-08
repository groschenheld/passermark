# SPDX-License-Identifier: GPL-3.0-or-later
# pdfToolkit – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Bilder als PDF öffnen – in tatsächlicher Größe (aus der DPI-Angabe des Bildes).

JPEG/PNG/TIFF werden von img2pdf verlustfrei eingebettet (keine Neukomprimierung),
EXIF-Drehung wird berücksichtigt. HEIC/HEIF über pillow-heif (optional).
Ohne DPI-Angabe im Bild gilt der Admin-Standard (image_default_dpi).
"""
from __future__ import annotations

from .l10n import tr

import io
import logging
import os

IMAGE_EXT = {".jpg", ".jpeg", ".jpe", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp",
             ".heic", ".heif"}
HEIF_EXT = {".heic", ".heif"}

logging.getLogger("img2pdf").setLevel(logging.ERROR)


def is_image(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in IMAGE_EXT


def heif_available() -> bool:
    try:
        import pillow_heif  # noqa: F401
        return True
    except ImportError:
        return False


def _dpi_of(img) -> float | None:
    dpi = img.info.get("dpi")
    if not dpi:
        return None
    try:
        x = float(dpi[0])
    except (TypeError, ValueError, IndexError):
        return None
    return x if x > 1.5 else None      # (1,1) = nur Seitenverhältnis, keine echte Angabe


def image_to_pdf_bytes(path: str, default_dpi: float = 96.0) -> bytes:
    import img2pdf
    from PIL import Image, ImageOps

    ext = os.path.splitext(path)[1].lower()
    if ext in HEIF_EXT:
        try:
            import pillow_heif
        except ImportError:
            raise RuntimeError(tr("HEIC/HEIF wird nicht unterstützt – pillow-heif fehlt (install.sh erneut ausführen)."))
        pillow_heif.register_heif_opener()

    with Image.open(path) as img:
        dpi = _dpi_of(img)
        needs_reencode = ext in HEIF_EXT or ext in (".webp", ".bmp") or \
            (ext == ".gif" and getattr(img, "n_frames", 1) == 1)
        if needs_reencode:
            im = ImageOps.exif_transpose(img)
            if im.mode in ("RGBA", "LA", "P"):
                bg = Image.new("RGB", im.size, "white")
                bg.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[-1])
                im = bg
            elif im.mode not in ("RGB", "L", "CMYK"):
                im = im.convert("RGB")
            buf = io.BytesIO()
            if ext in HEIF_EXT:
                im.save(buf, "JPEG", quality=95, subsampling=0, dpi=(dpi or default_dpi,) * 2)
            else:
                im.save(buf, "PNG", dpi=(dpi or default_dpi,) * 2)
            data = buf.getvalue()
            dpi = dpi or default_dpi
        else:
            with open(path, "rb") as f:
                data = f.read()

    kw = {"rotation": img2pdf.Rotation.ifvalid}
    if dpi is None:
        kw["layout_fun"] = img2pdf.get_fixed_dpi_layout_fun((default_dpi, default_dpi))
    return img2pdf.convert(data, **kw)


def images_to_document(paths: list[str], default_dpi: float = 96.0):
    """Mehrere Bilder -> ein pypdfium2-Dokument (eine Seite pro Bild/Frame)."""
    import pypdfium2 as pdfium

    out = pdfium.PdfDocument.new()
    for p in paths:
        part = pdfium.PdfDocument(image_to_pdf_bytes(p, default_dpi))
        out.import_pages(part)
        part.close()
    return out
