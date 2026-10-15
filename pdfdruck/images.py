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


# ---------------------------------------------------------------------------------------------- #
# HDR-Fotos (Apple HDR, Google Ultra HDR …): JPEG mit eingebettetem Zusatzbild (Helligkeitskarte /
# „Gain Map“) nach dem Multi-Picture-Format. Ohne Behandlung macht img2pdf daraus zwei Seiten – das
# Farbfoto und eine graue Karte, die wegen ihrer 72 dpi oft größer ist. Fürs Drucken zählt nur das
# Foto; die Karte hellt auf HDR-Bildschirmen die Lichter auf.
# ---------------------------------------------------------------------------------------------- #
HDR_DEFAULT = {"size": "aux", "merge": False}     # ohne Rückfrage: eine Seite, Größe wie die Zusatzseite
HDR_APPLE_STOPS = 2.0                             # Aufhellung, wenn die Datei keinen Wert mitbringt


def hdr_aux_info(path: str) -> dict | None:
    """JPEG mit Zusatzbild (Helligkeitskarte)? -> Angaben dazu, sonst None."""
    if os.path.splitext(path)[1].lower() not in (".jpg", ".jpeg", ".jpe"):
        return None
    from PIL import Image
    try:
        with Image.open(path) as img:
            if img.format != "MPO" or getattr(img, "n_frames", 1) < 2:
                return None
            main_px, main_dpi = img.size, _dpi_of(img)
            img.seek(1)
            aux_px, aux_dpi, aux_mode = img.size, _dpi_of(img), img.mode
    except Exception:                       # noqa: BLE001 – kaputte Datei: normaler Weg meldet es
        return None
    with open(path, "rb") as f:
        raw = f.read()
    kind = (tr("Apple-HDR") if b"apple:photo:2020:aux:hdrgainmap" in raw or b"ns.apple.com/HDRGainMap" in raw
            else tr("Ultra HDR") if b"ns.adobe.com/hdr-gain-map" in raw or b"hdrgm:" in raw
            else tr("Zusatzbild"))
    return {"kind": kind, "main_px": main_px, "main_dpi": main_dpi, "aux_px": aux_px,
            "aux_dpi": aux_dpi, "aux_mode": aux_mode}


def hdr_size_mm(info: dict, which: str, default_dpi: float = 96.0) -> tuple:
    """Seitengröße in mm: which = "aux" (wie die Zusatzseite) oder "main" (wie im Foto hinterlegt)."""
    px, dpi = (info["aux_px"], info["aux_dpi"]) if which == "aux" else (info["main_px"], info["main_dpi"])
    dpi = dpi or default_dpi
    return px[0] / dpi * 25.4, px[1] / dpi * 25.4


def _strip_mpf(jpeg: bytes) -> bytes:
    """MPF-Kopf (APP2 „MPF“) aus einem JPEG entfernen – danach ist es ein gewöhnliches Einzelbild."""
    if jpeg[:2] != b"\xff\xd8":
        return jpeg
    out, i = bytearray(b"\xff\xd8"), 2
    while i + 4 <= len(jpeg) and jpeg[i] == 0xFF:
        m = jpeg[i + 1]
        if m in (0xDA, 0xD9):                       # ab Bilddaten: Rest unverändert
            break
        n = int.from_bytes(jpeg[i + 2:i + 4], "big")
        seg = jpeg[i:i + 2 + n]
        if not (m == 0xE2 and seg[4:8] == b"MPF\x00"):
            out += seg
        i += 2 + n
    return bytes(out + jpeg[i:])


def _primary_jpeg(path: str) -> bytes:
    """Das Hauptbild eines MPO/HDR-JPEGs verlustfrei (ohne Zusatzbild, ohne MPF-Kopf)."""
    from PIL import Image
    with open(path, "rb") as f:
        raw = f.read()
    with Image.open(path) as img:
        offs = getattr(img, "_MpoImageFile__mpoffsets", None)
    end = offs[1] if offs and len(offs) > 1 else None
    if not end:                                      # Rückfall: Ende des ersten Bildes suchen
        end = raw.find(b"\xff\xd8\xff", 2)
        end = end if end > 0 else len(raw)
    return _strip_mpf(raw[:end])


def _hdr_params(raw: bytes) -> dict | None:
    """Ultra-HDR-Kennwerte (hdrgm:GainMapMin/Max/Gamma, log2) aus dem XMP; None = nicht vorhanden."""
    import re
    vals = {}
    for key in ("GainMapMin", "GainMapMax", "Gamma", "OffsetSDR", "OffsetHDR"):
        m = re.search(rb'hdrgm:' + key.encode() + rb'="([-0-9.eE]+)"', raw) or \
            re.search(rb'<hdrgm:' + key.encode() + rb'>([-0-9.eE]+)<', raw)
        if m:
            vals[key] = float(m.group(1))
    return vals or None


def hdr_merged_jpeg(path: str, stops: float | None = None) -> bytes:
    """Foto mit eingerechneter Helligkeitskarte (Lichter aufgehellt, für Papier zurückgerechnet)."""
    from PIL import Image
    with open(path, "rb") as f:
        raw = f.read()
    with Image.open(path) as img:
        img.seek(0)
        base = img.convert("RGB")
        icc = img.info.get("icc_profile")
        img.seek(1)
        gm = img.convert("L")
    return merge_gain_map(base, gm, icc, _hdr_params(raw), stops)


def merge_gain_map(base, gm, icc=None, params: dict | None = None, stops: float | None = None) -> bytes:
    """Helligkeitskarte gm (PIL „L“) auf das Foto base (PIL „RGB“) anwenden -> JPEG-Bytes.
        params: Ultra-HDR-Kennwerte (GainMapMin/Max/Gamma …) oder None = Apple-Formel."""
    import numpy as np
    from PIL import Image
    base = base.convert("RGB")
    gm = gm.convert("L").resize(base.size, Image.BICUBIC)

    def lin(v):
        return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)

    def enc(v):
        return np.where(v <= 0.0031308, v * 12.92, 1.055 * np.power(np.clip(v, 0, None), 1 / 2.4) - 0.055)

    sdr = lin(np.asarray(base, np.float32) / 255.0)
    g = np.asarray(gm, np.float32)[..., None] / 255.0
    p = params
    if p and "GainMapMax" in p:                      # Ultra HDR: logarithmisch codierte Karte
        lo, hi = p.get("GainMapMin", 0.0), p["GainMapMax"]
        rec = np.power(g, 1.0 / max(p.get("Gamma", 1.0), 1e-3))
        o_s, o_h = p.get("OffsetSDR", 1 / 64), p.get("OffsetHDR", 1 / 64)
        hdr = (sdr + o_s) * np.power(2.0, lo + (hi - lo) * rec) - o_h
        H = 2.0 ** hi
    else:                                            # Apple: hdr = sdr · (1 + (H − 1) · Karte)
        H = 2.0 ** (stops if stops is not None else HDR_APPLE_STOPS)
        hdr = sdr * (1.0 + (H - 1.0) * lin(g))
    # zurück auf Papier: bis zum Knie unverändert, darüber weich bis Weiß (Farbton bleibt)
    knee = 0.75
    m = hdr.max(axis=2, keepdims=True)
    t = np.clip((m - knee) / max(H - knee, 1e-3), 0, None)
    mo = np.where(m <= knee, m, knee + (1 - knee) * (1 - np.exp(-4 * t)) / (1 - np.exp(-4)))
    out = hdr * np.where(m > 1e-6, mo / np.maximum(m, 1e-6), 1.0)
    im = Image.fromarray((np.clip(enc(np.clip(out, 0, 1)), 0, 1) * 255 + 0.5).astype(np.uint8))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=95, subsampling=0, **({"icc_profile": icc} if icc else {}))
    return buf.getvalue()


def _hdr_to_pdf_bytes(path: str, info: dict, opts: dict, default_dpi: float) -> bytes:
    import img2pdf
    data = hdr_merged_jpeg(path) if opts.get("merge") and info.get("aux_mode") == "L" else _primary_jpeg(path)
    w_mm, _h = hdr_size_mm(info, opts.get("size", "aux"), default_dpi)
    dpi = info["main_px"][0] / (w_mm / 25.4)         # Foto und Karte sind gleich ausgerichtet
    return img2pdf.convert(data, rotation=img2pdf.Rotation.ifvalid,
                           layout_fun=img2pdf.get_fixed_dpi_layout_fun((dpi, dpi)))


def image_to_pdf_bytes(path: str, default_dpi: float = 96.0, hdr: dict | None = None) -> bytes:
    """hdr: Behandlung von HDR-Fotos mit Zusatzbild – {"size": "aux"|"main", "merge": bool};
        None = HDR_DEFAULT; {"keep": True} = unverändert (Zusatzbild als zweite Seite)."""
    import img2pdf
    from PIL import Image, ImageOps

    opts = HDR_DEFAULT if hdr is None else hdr
    if not opts.get("keep"):
        info = hdr_aux_info(path)
        if info is not None:
            return _hdr_to_pdf_bytes(path, info, opts, default_dpi)
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


def images_to_document(paths: list[str], default_dpi: float = 96.0, hdr: dict | None = None):
    """Mehrere Bilder -> ein pypdfium2-Dokument (eine Seite pro Bild/Frame).
        hdr: siehe image_to_pdf_bytes – je Pfad ({Pfad: Optionen}) oder für alle gleich."""
    import pypdfium2 as pdfium

    out = pdfium.PdfDocument.new()
    for p in paths:
        if isinstance(hdr, dict) and not ({"size", "merge", "keep"} & set(hdr)):
            o = hdr.get(p)                       # je Pfad
        else:
            o = hdr                              # für alle gleich (oder None = Standard)
        part = pdfium.PdfDocument(image_to_pdf_bytes(p, default_dpi, o))
        out.import_pages(part)
        part.close()
    return out
