# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Export pages as images: PNG, JPG or TIFF. Saving stays PDF; this is an extra way out (File → Export as image,
``passermark-cli export``, workflow step ``"job": "export"``).

- RGB and greyscale are rendered with pdfium (what the view shows), with the sRGB profile embedded.
- CMYK (JPG, TIFF) is separated by Ghostscript with the chosen print profile, the same way as the CMYK
  conversion: CMYK already in the PDF passes through, RGB is converted. The profile is embedded.
- Several pages give one file per page (``name-001.png`` – the number is the page number); TIFF can also hold
  all pages in one file.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass

from .l10n import tr

FORMATS = {"png": ".png", "jpg": ".jpg", "tiff": ".tif"}
_EXT_FORMAT = {".png": "png", ".jpg": "jpg", ".jpeg": "jpg", ".tif": "tiff", ".tiff": "tiff"}
COLORS = ("rgb", "gray", "cmyk")
COMPRESSIONS = {"lzw": "tiff_lzw", "zip": "tiff_adobe_deflate", "none": None}


@dataclass
class ExportSettings:
    """How pages become images."""

    format: str = "png"  # png | jpg | tiff
    dpi: float = 150
    color: str = "rgb"  # rgb | gray | cmyk (cmyk: JPG and TIFF only)
    profile: str = ""  # CMYK: print profile (ICC file); empty = the first CMYK profile of the admin settings
    transparent: bool = False  # PNG: page background transparent instead of white
    quality: int = 90  # JPG: 1–100
    compression: str = "lzw"  # TIFF: lzw | zip | none
    multipage: bool = False  # TIFF: all pages in one file
    out: str = ""  # workflow step: target file (name.png -> name-001.png … for several pages)


def format_for(path: str, fallback: str = "png") -> str:
    """Format from a file name (.png, .jpg/.jpeg, .tif/.tiff), else ``fallback``."""
    return _EXT_FORMAT.get(os.path.splitext(path)[1].lower(), fallback)


def check(s: ExportSettings) -> list[str]:
    """Problems of the settings (empty list = fine)."""
    probs = []
    if s.format not in FORMATS:
        probs.append(tr("Unbekanntes Bildformat: {0} (png, jpg, tiff)").format(s.format))
    if not 10 <= float(s.dpi) <= 2400:
        probs.append(tr("Auflösung muss zwischen 10 und 2400 dpi liegen."))
    if s.color not in COLORS:
        probs.append(tr("Unbekannte Farbe: {0} (rgb, gray, cmyk)").format(s.color))
    if s.color == "cmyk" and s.format == "png":
        probs.append(tr("PNG kann kein CMYK – JPG oder TIFF wählen."))
    if not 1 <= int(s.quality) <= 100:
        probs.append(tr("JPG-Qualität muss zwischen 1 und 100 liegen."))
    if s.compression not in COMPRESSIONS:
        probs.append(tr("Unbekannte TIFF-Komprimierung: {0} (lzw, zip, none)").format(s.compression))
    return probs


def target_files(out: str, pages: list[int], s: ExportSettings) -> list[str]:
    """The files the export writes: one per page ("name-005.png" for page 5), or ``out`` itself for one page or
    a multi-page TIFF. The extension of the format is added if ``out`` has none of it."""
    base, ext = os.path.splitext(out)
    if format_for(out, "") != s.format:
        base, ext = out, FORMATS[s.format]
    if len(pages) == 1 or (s.format == "tiff" and s.multipage):
        return [base + ext]
    width = max(3, len(str(max(pages) + 1)))
    return [f"{base}-{p + 1:0{width}d}{ext}" for p in pages]


def _srgb_bytes() -> bytes:
    from PIL import ImageCms

    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def _profile(s: ExportSettings) -> str:
    """The CMYK print profile to separate with."""
    if s.profile:
        if not os.path.isfile(s.profile):
            raise ValueError(tr("Profil nicht gefunden: {0}").format(s.profile))
        return s.profile
    from . import cmyk, config

    found = cmyk.find_profiles(config.load())
    if not found:
        raise ValueError(tr("Kein CMYK-Profil vorhanden – eines unter Farbe → Standardprofile holen."))
    return found[0].path


def _render_rgb(pdf, index: int, s: ExportSettings):
    """One page with pdfium: RGB, RGBA (transparent PNG) or L."""
    page = pdf[index]
    try:
        transparent = s.format == "png" and s.transparent and s.color != "gray"
        bm = page.render(
            scale=float(s.dpi) / 72.0,
            may_draw_forms=True,
            fill_color=(255, 255, 255, 0 if transparent else 255),
        )
        img = bm.to_pil()
    finally:
        page.close()
    if s.color == "gray":
        return img.convert("L")
    return img.convert("RGBA" if transparent else "RGB")


def _render_cmyk(path: str, index: int, s: ExportSettings, icc: str, password: str | None):
    """One page separated by Ghostscript with the print profile -> PIL CMYK."""
    from PIL import Image

    from . import cmyk

    gs = cmyk.ghostscript()
    if not gs:
        raise RuntimeError(tr("CMYK-Export braucht Ghostscript."))
    ms = cmyk.ManipSettings(cmyk_mode="rgb_only", target=icc, intent="relative", bpc=True)
    extra = [*cmyk._permit(ms), *cmyk.color_args(ms)]
    if password:
        extra.append(f"-sPDFPassword={password}")
    fd, tmp = tempfile.mkstemp(prefix="passermark-cmyk-", suffix=".tif")
    os.close(fd)
    try:
        cmyk._render(gs, path, index, float(s.dpi), "tiff32nc", extra, tmp)
        with Image.open(tmp) as im:
            return im.convert("CMYK").copy()
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def _save_options(s: ExportSettings, icc_bytes: bytes | None) -> dict:
    opts = {"dpi": (float(s.dpi), float(s.dpi))}
    if icc_bytes:
        opts["icc_profile"] = icc_bytes
    if s.format == "jpg":
        opts.update(quality=int(s.quality), optimize=True)
    elif s.format == "tiff":
        comp = COMPRESSIONS[s.compression]
        if comp:
            opts["compression"] = comp
    elif s.format == "png":
        opts["optimize"] = False  # optimize costs a lot of time for big pages, gains little
    return opts


def _pil_format(s: ExportSettings) -> str:
    return {"png": "PNG", "jpg": "JPEG", "tiff": "TIFF"}[s.format]


def export(
    src: str,
    out: str,
    s: ExportSettings,
    pages: list[int] | None = None,
    password: str | None = None,
    progress=None,
    cancel=None,
) -> dict:
    """Export the pages ``pages`` (0-based; None = all) of the PDF ``src`` as images to ``out``.
    -> {"files": [...], "pages": n, "format", "dpi", "color"}. Raises ValueError for wrong settings."""
    import pypdfium2 as pdfium

    probs = check(s)
    if probs:
        raise ValueError("\n".join(probs))
    pdf = pdfium.PdfDocument(src, password=password)
    try:
        n = len(pdf)
        pages = list(range(n)) if pages is None else [p for p in pages if 0 <= p < n]
        if not pages:
            raise ValueError(tr("Keine Seite zum Exportieren."))
        files = target_files(out, pages, s)
        icc = _profile(s) if s.color == "cmyk" else ""
        if icc:
            with open(icc, "rb") as f:
                icc_bytes = f.read()
        else:
            icc_bytes = None if s.color == "gray" else _srgb_bytes()
        opts = _save_options(s, icc_bytes)
        one_tiff = s.format == "tiff" and s.multipage and len(pages) > 1
        written, parts = [], []

        def page_image(k: int, idx: int):
            if cancel is not None and cancel():
                from .core import Cancelled

                raise Cancelled(tr("Abgebrochen."))
            if progress:
                progress(k, len(pages), tr("Seite {0}").format(idx + 1))
            img = _render_cmyk(src, idx, s, icc, password) if icc else _render_rgb(pdf, idx, s)
            return img.convert("RGB") if s.format == "jpg" and img.mode == "RGBA" else img

        try:
            if one_tiff:  # all pages into one file, page by page (not all images in memory at once)
                part = files[0] + ".part"
                parts.append(part)
                first = page_image(0, pages[0])
                rest = (page_image(k, idx) for k, idx in enumerate(pages[1:], 1))  # rendered one by one
                first.save(part, format="TIFF", save_all=True, append_images=rest, **opts)
                os.replace(part, files[0])
                parts.remove(part)
                written.append(files[0])
            else:
                for k, idx in enumerate(pages):
                    img = page_image(k, idx)
                    part = files[k] + ".part"
                    parts.append(part)
                    img.save(part, format=_pil_format(s), **opts)
                    os.replace(part, files[k])
                    parts.remove(part)
                    written.append(files[k])
        finally:
            for p in parts:  # nothing half-written stays behind
                try:
                    os.remove(p)
                except OSError:
                    pass
        if progress:
            progress(len(pages), len(pages), "")
        return {"files": written, "pages": len(pages), "format": s.format, "dpi": float(s.dpi), "color": s.color}
    finally:
        pdf.close()
