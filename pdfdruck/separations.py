# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Output preview: the printing plates of a page (CMYK + spot colours) and the total ink coverage.

Ghostscript (device tiffsep) separates the page into one greyscale image per ink plus a CMYK composite.
From that:
  compose()   page image with only the selected inks (single ink optionally in black) -> CMYK or L
  tac_map()   total ink coverage per pixel in percent (all inks, spot colours included)
  page_info() small overview for the panel: inks with swatch and coverage, highest ink coverage, share above
              the limit, plus the plates at low resolution for the values under the mouse (values_at)
Colour conversion as in the soft proof (RGB/grey -> CMYK of the printing condition, CMYK stays).
"""

from __future__ import annotations

import glob
import logging
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field

from .l10n import tr

log = logging.getLogger(__name__)

PROCESS = ("Cyan", "Magenta", "Yellow", "Black")
PROCESS_RGB = {"Cyan": (0, 160, 227), "Magenta": (229, 0, 126), "Yellow": (255, 237, 0), "Black": (30, 30, 30)}
INFO_DPI = 100
INFO_MAX_PIXELS = 2_000_000  # per plate for the overview
TAC_HIST_MAX = 1000  # histogram of the ink coverage in 1 % steps (spot colours can go above 400 %)
_CACHE: dict = {}
_CACHE_MAX = 2  # whole pages at view resolution: big


def ink_label(name: str) -> str:
    """Display name: process inks translated, spot colours as they are named in the PDF."""
    return {
        "Cyan": tr("Cyan"),
        "Magenta": tr("Magenta"),
        "Yellow": tr("Gelb"),
        "Black": tr("Schwarz"),
    }.get(name, name)


@dataclass
class Plates:
    """The inks of one page: name -> ink (numpy uint8, 255 = 100 %), composite (numpy H×W×4, 255 = 100 %),
    equivalents of the spot colours (name -> CMYK 0..1)."""

    names: list = field(default_factory=list)
    ink: dict = field(default_factory=dict)
    composite: object = None
    equiv: dict = field(default_factory=dict)

    @property
    def spots(self) -> list:
        """Names of the spot colours (in the order Ghostscript found them)."""
        return [n for n in self.names if n not in PROCESS]

    @property
    def size(self) -> tuple:
        """(width, height) in pixels."""
        h, w = self.composite.shape[:2]
        return w, h


# --------------------------------------------------------------------------- #
# Ghostscript
# --------------------------------------------------------------------------- #
# Ghostscript 9.5x/10.x with -dPrintSpotCMYK:  %%SeparationColor: "PANTONE 185 C" 100% ink = 0 30485 25876 0 CMYK
# (values as "frac", 32760 = 100 %); older versions:  %%SeparationName: PANTONE 185 C CMYK = [ 0 0.93 0.79 0 ]
_SEP_COLOR = re.compile(r'%%SeparationColor:\s*"(.*)"\s+100%\s+ink\s*=\s*([-\d\s]+?)\s*CMYK', re.M)
_SEP_LINE = re.compile(r"%%SeparationName:\s*(.+?)\s+CMYK\s*=\s*\[?\s*([-\d.,\s]+?)\s*\]?\s*$", re.M)
FRAC_1 = 32760.0  # Ghostscript's "frac" for 100 %


def _clamp4(vals) -> tuple:
    return tuple(min(1.0, max(0.0, float(v))) for v in vals[:4])


def parse_equivalents(text: str) -> dict:
    """Ghostscript output (-dPrintSpotCMYK) -> {spot colour: (c, m, y, k) 0..1}, in the order found."""
    out = {}
    for m in _SEP_COLOR.finditer(text or ""):
        try:
            vals = [float(v) for v in m.group(2).split()]
        except ValueError:
            continue
        if len(vals) >= 4:
            out[m.group(1)] = _clamp4([v / FRAC_1 for v in vals])
    for m in _SEP_LINE.finditer(text or ""):
        try:
            vals = [float(v) for v in re.split(r"[,\s]+", m.group(2).strip()) if v]
        except ValueError:
            continue
        if len(vals) < 4 or m.group(1).strip() in out:
            continue
        top = max(vals[:4])
        scale = 1.0 if top <= 1.0 else 255.0 if top <= 255 else FRAC_1 if top <= FRAC_1 else 65535.0
        out[m.group(1).strip()] = _clamp4([v / scale for v in vals])
    return out


def _unescape(name: str) -> str:
    """Ghostscript writes characters a file name cannot hold as %XX (bytes of UTF-8)."""
    if "%" not in name:
        return name
    raw = re.sub(rb"%([0-9A-Fa-f]{2})", lambda m: bytes([int(m.group(1), 16)]), name.encode("utf-8", "surrogateescape"))
    return raw.decode("utf-8", "replace")


def _name_of(path: str, base: str) -> str | None:
    """p(PANTONE 185 C).tif -> "PANTONE 185 C"; the composite p.tif -> None."""
    fn = os.path.basename(path)
    stem = os.path.splitext(base)[0]
    if not fn.startswith(stem) or fn == base:
        return None
    rest = fn[len(stem) : -len(".tif")]
    if rest.startswith("(") and rest.endswith(")"):
        return _unescape(rest[1:-1])
    m = re.fullmatch(r"\.s(\d+)", rest)  # without names: p.s0.tif
    return f"#{int(m.group(1)) + 1}" if m else None


def run_tiffsep(path: str, index: int, dpi: float, spec, password: str | None = None) -> Plates:
    """Separate one page with Ghostscript -> Plates (CropBox, /Rotate applied)."""
    import numpy as np
    from PIL import Image

    from . import cmyk, overprint

    gs = cmyk.ghostscript()
    if not gs:
        raise RuntimeError(tr("Für die Ausgabevorschau wird Ghostscript benötigt."))
    s = cmyk.ManipSettings(
        cmyk=True,
        cmyk_mode="rgb_only",
        target=spec["icc"],
        intent=spec.get("intent", "relative"),
        bpc=bool(spec.get("bpc", True)),
    )
    tmp = tempfile.mkdtemp(prefix="passermark-sep-")
    try:
        out = os.path.join(tmp, "p.tif")
        cmd = [
            gs,
            "-dNOPAUSE",
            "-dBATCH",
            "-dSAFER",
            "-sDEVICE=tiffsep",
            f"-r{round(dpi)}",
            f"-dFirstPage={index + 1}",
            f"-dLastPage={index + 1}",
            "-dUseCropBox",
            "-dPrintSpotCMYK",
            *overprint.ghostscript_args(bool(spec.get("overprint", True))),
            *cmyk._permit(s),
            *cmyk.color_args(s),
            *([f"-sPDFPassword={password}"] if password else []),
            "-o",
            out,
            path,
        ]
        r = cmyk._run(cmd, timeout=300)
        if r.returncode != 0 or not os.path.exists(out):
            raise RuntimeError(tr("Ghostscript-Fehler:\n") + (r.stderr or r.stdout or "")[-800:])
        comp = Image.open(out)
        comp.load()
        comp = np.asarray(comp.convert("CMYK") if comp.mode != "CMYK" else comp, dtype=np.uint8)
        files = {}
        for f in glob.glob(os.path.join(glob.escape(tmp), "*.tif")):
            name = _name_of(f, "p.tif")
            if name:
                files[name] = f
        text = (r.stdout or "") + "\n" + (r.stderr or "")
        equiv = parse_equivalents(text)
        order = list(equiv)
        plates = Plates(composite=comp, equiv=equiv)
        for name, f in files.items():
            im = Image.open(f)
            im.load()
            a = np.asarray(im.convert("L"), dtype=np.uint8)
            if a.shape != comp.shape[:2]:
                a = np.asarray(im.convert("L").resize((comp.shape[1], comp.shape[0])), dtype=np.uint8)
            plates.ink[name] = a
        _calibrate(plates)
        spots = sorted(
            (n for n in plates.ink if n not in PROCESS), key=lambda n: (order.index(n) if n in order else 99, n)
        )
        plates.names = [n for n in PROCESS if n in plates.ink] + spots
        for n in spots:
            if n not in plates.equiv:
                plates.equiv[n] = _estimate_equiv(plates, n)
        return plates
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _calibrate(plates: Plates) -> None:
    """Separation files are written like film (0 = full ink) or like ink (255 = full ink), depending on the
    Ghostscript version: compare the process plates with the composite and turn them all the same way."""
    import numpy as np

    votes = 0.0
    for i, n in enumerate(PROCESS):
        a = plates.ink.get(n)
        if a is None:
            continue
        c = plates.composite[..., i].astype(np.int16)
        same = np.abs(a.astype(np.int16) - c).mean()
        inv = np.abs((255 - a.astype(np.int16)) - c).mean()
        votes += inv - same
    if votes < 0:  # inverted is closer: film-like
        for n in list(plates.ink):
            plates.ink[n] = 255 - plates.ink[n]


def _estimate_equiv(plates: Plates, name: str) -> tuple:
    """CMYK look of a spot colour from the composite: where this ink is strong and no other spot colour."""
    import numpy as np

    a = plates.ink[name]
    sel = a > 100  # at least ~40 %: the composite divided by the coverage gives the 100 % look
    for n in plates.spots:
        if n != name:
            sel &= plates.ink[n] < 8
    if sel.sum() < 4:
        return (0.0, 0.5, 0.5, 0.2)  # unknown: neutral reddish brown, only for the look
    proc = np.stack([plates.ink.get(n, np.zeros_like(a)) for n in PROCESS], axis=-1).astype(np.float32)
    diff = plates.composite.astype(np.float32) - proc
    cov = a[sel].astype(np.float32)[:, None] / 255.0
    est = np.median(diff[sel] / np.maximum(cov, 1e-3), axis=0) / 255.0
    return tuple(float(min(1.0, max(0.0, v))) for v in est)


def plates_for(path: str, index: int, dpi: float, spec, password: str | None = None) -> Plates:
    """run_tiffsep with a small cache (file, page, resolution, colour settings)."""
    st = os.stat(path)
    key = (
        os.path.realpath(path),
        st.st_mtime_ns,
        st.st_size,
        index,
        round(dpi),
        spec.get("icc"),
        spec.get("intent", "relative"),
        bool(spec.get("bpc", True)),
        bool(spec.get("overprint", True)),
    )
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    p = run_tiffsep(path, index, dpi, spec, password)
    while len(_CACHE) >= _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = p
    return p


# --------------------------------------------------------------------------- #
# images
# --------------------------------------------------------------------------- #
def visible(plates: Plates, hide) -> list:
    """Names of the inks shown (in plate order)."""
    hide = set(hide or ())
    return [n for n in plates.names if n not in hide]


def compose(plates: Plates, hide=(), gray: bool = False):
    """Page with only the visible inks -> PIL CMYK (for the soft proof transform), or PIL L when exactly one ink
    is shown and gray is set (the plate in black, like a film)."""
    import numpy as np
    from PIL import Image

    show = visible(plates, hide)
    if gray and len(show) == 1:
        return Image.fromarray(255 - plates.ink[show[0]], "L")
    if len(show) == len(plates.names):
        return Image.fromarray(plates.composite, "CMYK")  # everything: Ghostscript's own mix
    h, w = plates.composite.shape[:2]
    out = np.zeros((h, w, 4), dtype=np.float32)
    for i, n in enumerate(PROCESS):
        if n in show and n in plates.ink:
            out[..., i] = plates.ink[n]
    for n in plates.spots:
        if n in show:
            cov = plates.ink[n].astype(np.float32) / 255.0
            eq = np.asarray(plates.equiv.get(n, (0, 0, 0, 0)), dtype=np.float32) * 255.0
            out += cov[..., None] * eq  # like Ghostscript's composite: spot colour as its CMYK look on top
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "CMYK")


def tac_map(plates: Plates):
    """Total ink coverage per pixel in percent (numpy float32), all inks."""
    import numpy as np

    total = np.zeros(plates.composite.shape[:2], dtype=np.float32)
    for n in plates.names:
        total += plates.ink[n]
    return total * (100.0 / 255.0)


def swatch_rgb(plates: Plates, name: str) -> tuple:
    """Colour of the swatch in the panel (sRGB, rough)."""
    if name in PROCESS_RGB:
        return PROCESS_RGB[name]
    c, m, y, k = plates.equiv.get(name, (0, 0, 0, 0))
    return tuple(round(255 * (1 - min(1.0, v + k))) for v in (c, m, y))


# --------------------------------------------------------------------------- #
# overview for the panel
# --------------------------------------------------------------------------- #
def _geometry(path: str, index: int, password: str | None) -> tuple:
    """CropBox and /Rotate of the page (pikepdf, no pdfium: safe in threads)."""
    import pikepdf

    with pikepdf.open(path, password=password or "") as pdf:
        pg = pdf.pages[index]
        b = [float(v) for v in pg.cropbox]
        rot, node = None, pg.obj
        while rot is None and node is not None:
            rot = node.get("/Rotate")
            node = node.get("/Parent")
        return (min(b[0], b[2]), min(b[1], b[3]), max(b[0], b[2]), max(b[1], b[3])), int(rot or 0) % 360


def page_info(path: str, index: int, spec, password: str | None = None, dpi: float = INFO_DPI) -> dict:
    """Overview of one page for the panel:
    {"inks": [{"name", "label", "spot", "rgb", "coverage"}], "max_tac", "over", "limit", "plates": {name: uint8},
     "size": (w, h), "crop", "rot"}. coverage = share of the page area this ink prints on (%), over = share above
    the limit (%).
    """
    import numpy as np

    crop, rot = _geometry(path, index, password)
    w_pt, h_pt = crop[2] - crop[0], crop[3] - crop[1]
    px = (w_pt * dpi / 72.0) * (h_pt * dpi / 72.0)
    if px > INFO_MAX_PIXELS:
        dpi *= (INFO_MAX_PIXELS / px) ** 0.5
    dpi = max(10.0, dpi)
    p = run_tiffsep(path, index, dpi, spec, password)
    total = tac_map(p)
    limit = float(spec.get("tac", 300))
    inks = []
    for n in p.names:
        a = p.ink[n]
        inks.append(
            {
                "name": n,
                "label": ink_label(n),
                "spot": n not in PROCESS,
                "rgb": swatch_rgb(p, n),
                "coverage": float((a > 3).mean() * 100.0),
            }
        )
    hist = np.bincount(np.clip(np.rint(total), 0, TAC_HIST_MAX).astype(np.int32).ravel(), minlength=TAC_HIST_MAX + 1)
    info = {
        "inks": inks,
        "tac_hist": hist,
        "max_tac": float(total.max()) if total.size else 0.0,
        "limit": limit,
        "plates": {n: np.ascontiguousarray(p.ink[n]) for n in p.names},
        "size": p.size,
        "crop": crop,
        "rot": rot,
    }
    info["over"] = share_over(info, limit)
    return info


def share_over(info: dict, limit: float) -> float:
    """Share of the page (%) above ``limit`` from the histogram of page_info."""
    hist = (info or {}).get("tac_hist")
    if hist is None or not len(hist) or not hist.sum():
        return 0.0
    lo = min(len(hist), int(limit + 0.5) + 1)
    return float(hist[lo:].sum() * 100.0 / hist.sum())


def values_at(info: dict, x: float, y: float) -> dict | None:
    """Ink values (%) at a page point (pt) from page_info -> {name: percent, "": total} or None outside."""
    from .pipette import _pixel

    if not info or not info.get("plates"):
        return None
    x0, y0, x1, y1 = info["crop"]
    if not (x0 <= x <= x1 and y0 <= y <= y1):
        return None
    col, row = _pixel(x, y, info["crop"], info["rot"], info["size"])
    out = {n: float(a[row, col]) * 100.0 / 255.0 for n, a in info["plates"].items()}
    out[""] = sum(out.values())
    return out


def describe(spec) -> str:
    """Short text for the status bar: what the output preview shows."""
    mode = (spec or {}).get("mode")
    if mode == "tac":
        return tr("Farbauftrag > {0:g} %").format(float(spec.get("tac", 300)))
    if mode == "sep":
        hide = list(spec.get("hide") or [])
        if not hide:
            return tr("Alle Auszüge")
        return tr("ohne {0}").format(", ".join(ink_label(n) for n in hide[:4]) + (" …" if len(hide) > 4 else ""))
    return ""
