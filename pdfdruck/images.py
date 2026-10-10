# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Opening images as PDFs – at their actual size (from the image's DPI value).

JPEG/PNG/TIFF are embedded losslessly by img2pdf (no recompression),
EXIF rotation is honored. HEIC/HEIF via pillow-heif (optional).
Without a DPI value in the image, the admin default applies (image_default_dpi).
"""
from __future__ import annotations

from .l10n import tr

import io
import logging
import os

IMAGE_EXT = {".jpg", ".jpeg", ".jpe", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp",
             ".heic", ".heif", ".svg", ".svgz"}
HEIF_EXT = {".heic", ".heif"}
SVG_EXT = {".svg", ".svgz"}

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
    return x if x > 1.5 else None      # (1,1) = aspect ratio only, no real value


def _svg_size_mm(path: str):
    """Width/height from width/height (mm, cm, in, pt, pc, px = 1/96 in) or the viewBox. None = unknown."""
    import gzip
    import re
    opener = gzip.open if path.lower().endswith(".svgz") else open
    try:
        with opener(path, "rb") as f:
            head = f.read(65536).decode("utf-8", "replace")
    except OSError:
        return None
    m = re.search(r"<svg\b[^>]*>", head, re.S)
    if not m:
        return None
    tag = m.group(0)
    unit = {"mm": 1.0, "cm": 10.0, "in": 25.4, "pt": 25.4 / 72, "pc": 25.4 / 6, "px": 25.4 / 96, "": 25.4 / 96}

    def length(name):
        a = re.search(rf'\s{name}\s*=\s*["\']\s*([0-9.]+)\s*([a-z%]*)', tag)
        if not a or a.group(2) == "%":
            return None
        return float(a.group(1)) * unit.get(a.group(2), 25.4 / 96)
    w, h = length("width"), length("height")
    vb = re.search(r'viewBox\s*=\s*["\']\s*([-0-9.eE]+)[ ,]+([-0-9.eE]+)[ ,]+([0-9.eE]+)[ ,]+([0-9.eE]+)', tag)
    if vb:
        vw, vh = float(vb.group(3)), float(vb.group(4))
        if w and not h and vw:
            h = w * vh / vw
        elif h and not w and vh:
            w = h * vw / vh
        elif not w and not h:
            w, h = vw * 25.4 / 96, vh * 25.4 / 96
    return (w, h) if w and h else None


def svg_to_pdf_bytes(path: str) -> bytes:
    """SVG -> PDF, vektoriell. rsvg-convert (librsvg) > Inkscape > Qt (SVG Tiny, immer vorhanden)."""
    import shutil
    import subprocess
    import tempfile
    from . import platform as _platform
    errors = []
    for tool in ("rsvg-convert", "inkscape"):
        exe = shutil.which(tool)
        if not exe:
            continue
        tmp = tempfile.mkdtemp(prefix="passermark-svg-")
        out = os.path.join(tmp, "out.pdf")
        cmd = [exe, "-f", "pdf", "-o", out, path] if tool == "rsvg-convert" else \
            [exe, path, "--export-type=pdf", f"--export-filename={out}"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                               **_platform.hidden_subprocess_kwargs())
            if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 0:
                with open(out, "rb") as f:
                    return f.read()
            errors.append(f"{tool}: {(r.stderr or '').strip()[-300:]}")
        except (OSError, subprocess.SubprocessError) as e:
            errors.append(f"{tool}: {e}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    # fallback: Qt (needs a running Qt application – always the case inside the program)
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMarginsF, QRectF, QSizeF
    from PySide6.QtGui import QPageLayout, QPageSize, QPainter, QPdfWriter
    from PySide6.QtSvg import QSvgRenderer
    ren = QSvgRenderer(path)
    if not ren.isValid():
        raise RuntimeError(tr("SVG konnte nicht gelesen werden.") + ("\n" + "\n".join(errors) if errors else ""))
    size = _svg_size_mm(path)
    if not size:
        d = ren.defaultSize()
        size = (d.width() * 25.4 / 96, d.height() * 25.4 / 96)
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    wr = QPdfWriter(buf)
    wr.setResolution(1200)
    wr.setPageLayout(QPageLayout(QPageSize(QSizeF(*size), QPageSize.Unit.Millimeter),
                                 QPageLayout.Orientation.Portrait, QMarginsF(0, 0, 0, 0)))
    painter = QPainter(wr)
    ren.render(painter, QRectF(0, 0, wr.width(), wr.height()))
    painter.end()
    buf.close()
    return bytes(data)


def image_to_pdf_bytes(path: str, default_dpi: float = 96.0) -> bytes:
    import img2pdf
    from PIL import Image, ImageOps

    ext = os.path.splitext(path)[1].lower()
    if ext in SVG_EXT:
        return svg_to_pdf_bytes(path)
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
            alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
            if alpha:
                im = im.convert("RGBA")         # Transparenz bleibt (img2pdf legt eine Soft-Mask an)
            elif im.mode not in ("RGB", "L", "CMYK"):
                im = im.convert("RGB")
            buf = io.BytesIO()
            if ext in HEIF_EXT and not alpha:
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
