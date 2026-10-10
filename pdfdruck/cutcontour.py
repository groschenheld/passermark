# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""CutContour for cutting plotters (Roland VersaWorks and others) with automatically generated bleed.

Per-object sequence (page normalized, see objects.py):
  1. Extract the object from the sheet (artwork mask, nearby parts merged)
  2. Define the cut shape:
       contour – follows the artwork (distance + smoothing for weeding; deliberately not exact afterwards)
       rect, rounded, circle, oval, hexagon, octagon, heart, star, shield, arch – classic sticker shapes
       at object size (without bleed), scalable or at a fixed size, centered over the object
  3. Bleed: the object's edge colors are pulled outward (nearest artwork point) and fill the
     entire area inside the cut line (including bays and the space between object and line) plus
     "bleed" beyond the line. It lies BEHIND the object; the cut line always sits inside it.
  4. Output: bleed as an image under the unchanged (vector) artwork, cut as a path in the
     spot color "CutContour" (separation, alternate color 100 % magenta), overprint.
     Optionally on the original sheet, or each object as its own page with a margin.
"""
from __future__ import annotations

import io
import math
from dataclasses import dataclass, field

from .l10n import tr
from .objects import MM, DetectSettings, motif_mask, render_rgba

SHAPES = ["contour", "rect", "rounded", "circle", "oval", "hexagon", "octagon", "heart", "star", "shield", "arch"]


@dataclass
class CutSettings:
    dpi: int = 200
    shape: str = "contour"
    fit: str = "motif"             # Grundformen: "trim" = aufs Endformat (TrimBox, sonst Seite) – ohne Rendern/Erkennen;
                                   # "motif" = ums erkannte Motiv (gerechnet)
    offset_mm: float = 0.0         # cut: + outward, − inward (from the artwork or the object size)
    bleed: bool = True             # create bleed (off = artwork unchanged, e.g. for white margins)
    bleed_mm: float = 2.0          # bleed (from the object, at least this far beyond the cut line)
    smooth_mm: float = 1.5         # contour only: bays < 2× are bridged, edges rounded
    inner: bool = False            # contour only: also cut inner contours (holes)
    corner_mm: float = 3.0         # abgerundetes Rechteck: Eckenradius
    scale_pct: float = 100.0       # shapes: size relative to the object
    width_mm: float = 0.0          # shapes: cut line size in mm (0 = from the object + distance)
    height_mm: float = 0.0
    shift_x_mm: float = 0.0        # shapes: offset of the shape from the artwork center (+ is right)
    shift_y_mm: float = 0.0        # (+ oben)
    min_size_mm: float = 3.0
    bleed_color: str = ""          # "" = automatic from the artwork, otherwise a fixed color "#rrggbb" (uniform border)
    clean_seams: bool = False      # replace narrow blend edges inside the artwork with solid colors (flat artwork only)
    single_shape: bool = True      # Grundformen: EINE Form um das ganze Motiv (False = eine Form je Objekt)
    per_object: bool = False       # jedes Objekt als eigene Seite
    margin_mm: float = 6.0         # margin of the individual pages around bleed/cut
    spot: str = "CutContour"
    stroke_pt: float = 0.25
    detect: DetectSettings = field(default_factory=lambda: DetectSettings(gap_mm=1.0))


@dataclass
class CutObject:
    paths: list                    # [(Punkte [(x, y)…] in pt, glatt: bool)]
    bleed_rgba: object = None      # numpy (h, w, 4)
    bleed_box: tuple | None = None # (x0, y0, x1, y1) pt
    motif_box: tuple = (0, 0, 0, 0)
    box: tuple = (0, 0, 0, 0)      # extent of cut + bleed
    clip: list = field(default_factory=list)   # Umriss des Objekts (nur bei Motiven mit Hintergrund)
    overlay_rgba: object = None    # cleaned blend edges (above the artwork)
    overlay_box: tuple | None = None


@dataclass
class CutResult:
    objects: list                  # [CutObject]
    page_size: tuple = (0, 0)
    knockout: object = None       # bool-Maske (Seite, dpi) – sichtbarer Teil des Originals (Hintergrund ausgestanzt)
    dpi: int = 0

    @property
    def paths(self):               # all cut paths (for preview/counting)
        return [p for o in self.objects for p in o.paths]


# --------------------------------------------------------------------------- #
# Formen
# --------------------------------------------------------------------------- #
def _fit(pts, cx, cy, w, h):
    import numpy as np
    pts = np.asarray(pts, float)
    mn, mx = pts.min(axis=0), pts.max(axis=0)
    span = np.where(mx - mn > 1e-9, mx - mn, 1)
    unit = (pts - mn) / span - 0.5
    return np.column_stack([cx + unit[:, 0] * w, cy + unit[:, 1] * h])


def _arc(cx, cy, r, a0, a1, step):
    n = max(2, int(abs(a1 - a0) * r / step) + 1)
    return [(cx + r * math.cos(a0 + (a1 - a0) * i / (n - 1)), cy + r * math.sin(a0 + (a1 - a0) * i / (n - 1)))
            for i in range(n)]


def shape_polygon(kind: str, cx: float, cy: float, w: float, h: float, corner: float = 0.0):
    """Geschlossene Form (Punkte in pt), Ausdehnung w × h, Mitte (cx, cy). Kurven fein abgetastet."""
    import numpy as np
    step = 0.25 * MM
    if kind == "rect":
        return np.array([(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2), (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2)])
    if kind == "rounded":
        r = max(0.0, min(corner, w / 2, h / 2))
        if r < 0.05:
            return shape_polygon("rect", cx, cy, w, h)
        x0, x1, y0, y1 = cx - w / 2 + r, cx + w / 2 - r, cy - h / 2 + r, cy + h / 2 - r
        pts = (_arc(x1, y0, r, -math.pi / 2, 0, step) + _arc(x1, y1, r, 0, math.pi / 2, step)
               + _arc(x0, y1, r, math.pi / 2, math.pi, step) + _arc(x0, y0, r, math.pi, 1.5 * math.pi, step))
        return np.array(pts)
    if kind in ("circle", "oval"):
        if kind == "circle":
            w = h = max(w, h)                  # around the entire artwork (larger side), not through it
        n = max(48, int(math.pi * (w + h) / 2 / step))
        t = np.linspace(0, 2 * math.pi, n, endpoint=False)
        return np.column_stack([cx + w / 2 * np.cos(t), cy + h / 2 * np.sin(t)])
    if kind == "hexagon":
        t = np.radians(np.arange(0, 360, 60))
        return _fit(np.column_stack([np.cos(t), np.sin(t)]), cx, cy, w, h)
    if kind == "octagon":
        t = np.radians(np.arange(22.5, 360, 45))
        return _fit(np.column_stack([np.cos(t), np.sin(t)]), cx, cy, w, h)
    if kind == "star":
        t = math.pi / 2 + np.arange(10) * math.pi / 5
        r = np.where(np.arange(10) % 2 == 0, 1.0, 0.45)
        return _fit(np.column_stack([r * np.cos(t), r * np.sin(t)]), cx, cy, w, h)
    if kind == "heart":
        t = np.linspace(0, 2 * math.pi, 400, endpoint=False)
        x = 16 * np.sin(t) ** 3
        y = 13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t)
        return _fit(np.column_stack([x, y]), cx, cy, w, h)
    if kind == "shield":
        # crest: straight top, vertical sides, two bottom arcs meeting at the tip
        right = [(1 - tt, 0.15 - 1.15 * math.sin(tt * math.pi / 2)) for tt in np.linspace(0, 1, 60)]
        left = [(-x, y) for x, y in reversed(right)]
        return _fit([(-1, 1), (1, 1)] + right + left[1:], cx, cy, w, h)
    if kind == "arch":
        # unten rechteckig, oben Halbkreis
        right = [(1, -1), (1, 0)]
        top = [(math.cos(a), math.sin(a)) for a in np.linspace(0, math.pi, 120)]
        return _fit(right + top + [(-1, 0), (-1, -1)], cx, cy, w, h)
    raise ValueError(kind)


SMOOTH_KINDS = {"contour"}


# --------------------------------------------------------------------------- #
def _resample(pts, step):
    """Redistribute a closed point sequence evenly by arc length (prevents overshoot)."""
    import numpy as np
    closed = np.vstack([pts, pts[:1]])
    seg = np.hypot(*np.diff(closed, axis=0).T)
    t = np.concatenate([[0], np.cumsum(seg)])
    n = max(8, int(t[-1] / step))
    tt = np.linspace(0, t[-1], n, endpoint=False)
    return np.column_stack([np.interp(tt, t, closed[:, 0]), np.interp(tt, t, closed[:, 1])])


def bezier_ops(poly) -> str:
    """Geschlossenes Polygon -> glatter Pfad (Catmull-Rom als kubische Bézierkurven), PDF-Operatoren."""
    n = len(poly)
    if n < 3:
        return ""
    P = poly
    out = [f"{P[0][0]:.3f} {P[0][1]:.3f} m"]
    for i in range(n):
        p0, p1, p2, p3 = P[i - 1], P[i], P[(i + 1) % n], P[(i + 2) % n]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        out.append(f"{c1[0]:.3f} {c1[1]:.3f} {c2[0]:.3f} {c2[1]:.3f} {p2[0]:.3f} {p2[1]:.3f} c")
    out.append("h")
    return "\n".join(out)


def line_ops(poly) -> str:
    out = [f"{poly[0][0]:.3f} {poly[0][1]:.3f} m"] + [f"{x:.3f} {y:.3f} l" for x, y in poly[1:]] + ["h"]
    return "\n".join(out)


def _offset_shape(s: CutSettings, w, h):
    """Shape size: the given size applies EXACTLY as the cut line; without a value, object size + distance.
        With only one value (width or height): the object's aspect ratio is kept.
    """
    k = s.scale_pct / 100.0                      # only for API callers any more (GUI: 100)
    if s.width_mm > 0 and s.height_mm > 0:
        return max(1.0, s.width_mm * MM * k), max(1.0, s.height_mm * MM * k)
    off = 2 * s.offset_mm * MM
    if s.width_mm > 0:
        return max(1.0, s.width_mm * MM * k), max(1.0, (h + off) * s.width_mm * MM / (w + off) * k)
    if s.height_mm > 0:
        return max(1.0, (w + off) * s.height_mm * MM / (h + off) * k), max(1.0, s.height_mm * MM * k)
    return max(1.0, (w + off) * k), max(1.0, (h + off) * k)


# --------------------------------------------------------------------------- #
def _solid_palette(core_px, bg, tol):
    """Solid colors of an object (frequent colors in the core) and the share of core pixels matching one of them."""
    import numpy as np
    from PIL import Image
    pix = core_px.reshape(-1, 3)
    if len(pix) < 16:
        return None, 0.0
    if len(pix) > 200000:
        pix = pix[np.random.default_rng(0).choice(len(pix), 200000, replace=False)]
    q = Image.fromarray(pix.reshape(-1, 1, 3).astype(np.uint8), "RGB").quantize(
        colors=24, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    raw = q.getpalette() or []
    n = max(1, len(raw) // 3)                          # with few colors, Pillow returns a shorter palette
    pal = np.asarray(raw[:n * 3], dtype=np.int16).reshape(n, 3)
    counts = np.bincount(np.asarray(q).ravel(), minlength=n)[:n]
    keep = counts >= max(1, 0.01 * len(pix))
    if bg is not None:
        keep &= np.abs(pal - bg).max(axis=1) > tol * 2
    pal = pal[keep]
    if len(pal) == 0:
        return None, 0.0
    # exact hues: median of the real pixels per color group (for solid colors = original value)
    p16 = pix.astype(np.int16)
    lab = _nearest_idx(p16, pal)
    for i in range(len(pal)):
        sel = p16[lab == i]
        if len(sel):
            pal[i] = np.median(sel, axis=0).round()
    d = _nearest_dist(p16, pal)
    return pal, float((d <= (tol * 2) ** 2).mean())


def _nearest_idx(flat, pal):
    import numpy as np
    out = np.empty(len(flat), np.int32)
    for i in range(0, len(flat), 250000):
        part = flat[i:i + 250000]
        out[i:i + 250000] = ((part[:, None, :] - pal[None, :, :]) ** 2).sum(axis=2).argmin(axis=1)
    return out


def _nearest_dist(flat, pal):
    import numpy as np
    out = np.empty(len(flat), np.int32)
    for i in range(0, len(flat), 250000):
        part = flat[i:i + 250000]
        out[i:i + 250000] = ((part[:, None, :] - pal[None, :, :]) ** 2).sum(axis=2).min(axis=1)
    return out


def _unmix_labels(px, pal, bg, solid_tol):
    """Assign every pixel to the solid color it was mixed from.

        An edge pixel lies (physically) on the line solid color–background or solid color–solid color. The line
        with the smallest distance is chosen; between two solid colors, the nearer side. That way light pink is
        unambiguously red – even if by simple RGB distance it would be closer to green.
    """
    import numpy as np
    P = px.reshape(-1, 3).astype(np.float32)
    C = pal.astype(np.float32)
    B = np.asarray(bg, np.float32)
    K = len(C)
    lab = np.zeros(len(P), np.int32)
    if len(P) == 0:
        return lab
    d0 = ((P[:, None, :] - C[None, :, :]) ** 2).sum(axis=2)
    lab = d0.argmin(axis=1)
    rest = np.where(d0.min(axis=1) > solid_tol ** 2)[0]          # examine only blend/edge pixels closely
    if len(rest) == 0:
        return lab
    Q = P[rest]
    best = np.full(len(Q), np.inf, np.float32)
    bl = lab[rest].copy()

    def line(a, b, ia, ib):
        nonlocal best, bl
        d = b - a
        L2 = float((d * d).sum())
        if L2 < 1:
            return
        t = np.clip(((Q - a) @ d) / L2, 0, 1)
        res = ((Q - (a + t[:, None] * d)) ** 2).sum(axis=1)
        pick = np.where(t >= 0.5, ib, ia) if ia >= 0 else np.full(len(Q), ib)
        upd = res < best
        best = np.where(upd, res, best)
        bl = np.where(upd, pick, bl)
    for k in range(K):
        line(B, C[k], -1, k)                                       # Hintergrund–Vollfarbe
    top = np.argsort(-np.bincount(lab, minlength=K))[:8]           # solid–solid (most common)
    for i in range(len(top)):
        for j in range(i + 1, len(top)):
            line(C[top[i]], C[top[j]], int(top[i]), int(top[j]))
    lab[rest] = bl
    return lab


def _snap_to_solid(fill, core_px, bg, tol):
    """Set every bleed color to the object's nearest solid color (see _solid_palette).
        For photos (many tones) the colors stay similar – they lie behind the object or outside the cut.
    """
    import numpy as np
    pal, _share = _solid_palette(core_px, bg, tol)
    if pal is None:
        return fill
    flat = fill.reshape(-1, 3).astype(np.int16)
    return pal[_nearest_idx(flat, pal)].reshape(fill.shape).astype(np.uint8)


@dataclass
class _ObjCtx:
    """Page-wide values every object needs (small, passed to the worker processes)."""
    s: CutSettings
    pad: int
    px: float
    H: float
    off: float
    sm: float
    bl: float
    use_bleed: bool
    bg_rgb: object
    has_knock: bool


PARALLEL_MIN_OBJECTS = 4            # darunter lohnt sich der Start von Arbeitsprozessen nicht
PARALLEL_MIN_PIXELS = 1_500_000     # Summe der Arbeitsfenster (Bildpunkte)


def default_workers() -> int:
    """Worker processes for parallel computation: all cores but one (for the GUI), at most 8.
        Limit with the environment variable PASSERMARK_WORKERS (e.g. 2; 1 = not parallel).
    """
    import os
    env = os.environ.get("PASSERMARK_WORKERS", "").strip()
    if env.isdigit() and int(env) >= 1:
        return int(env)
    return max(1, min(8, (os.cpu_count() or 1) - 1))


class WorkerPool:
    """Start the worker processes once per job and use them for all pages (starting costs ~1 s per process)."""

    def __init__(self, workers: int):
        self.workers = workers
        self._ex = None

    def get(self):
        if self._ex is None:
            import multiprocessing as mp
            from concurrent.futures import ProcessPoolExecutor
            # "spawn": fresh processes (no inherited pdfium/threads), identical everywhere (Linux, Windows, AppImage)
            self._ex = ProcessPoolExecutor(max_workers=self.workers, mp_context=mp.get_context("spawn"))
        return self._ex

    def close(self):
        if self._ex is not None:
            self._ex.shutdown(wait=True, cancel_futures=True)
            self._ex = None


def _run_objects(ctx, jobs, workers, progress, cancel, pool=None):
    """Objekte berechnen – seriell oder auf mehrere Arbeitsprozesse verteilt; Reihenfolge bleibt erhalten."""
    n = len(jobs)
    pixels = sum(j[0].size for j in jobs)
    if pool is not None:
        workers = pool.workers
    parallel = workers > 1 and n >= PARALLEL_MIN_OBJECTS and pixels >= PARALLEL_MIN_PIXELS

    def check():
        if cancel is not None and cancel():
            from .core import Cancelled
            raise Cancelled(tr("Abgebrochen."))
    if not parallel:
        out = []
        for i, job in enumerate(jobs):
            check()
            if progress is not None:
                progress(i, n)
            out.append(_compute_object(ctx, job))
        return out
    from concurrent.futures import FIRST_COMPLETED, wait
    out = [None] * n
    own = pool is None
    if own:
        pool = WorkerPool(min(workers, n))
    ex = pool.get()
    try:
        pending = {ex.submit(_compute_object, ctx, job): i for i, job in enumerate(jobs)}
        done_count = 0
        while pending:
            check()
            finished, _ = wait(list(pending), timeout=0.2, return_when=FIRST_COMPLETED)
            for f in finished:
                out[pending.pop(f)] = f.result()
                done_count += 1
                if progress is not None:
                    progress(done_count, n)
    except BaseException:
        if not own:                      # Abbruch/Fehler: offene Aufgaben verwerfen, Prozesse beenden
            pool.close()
        raise
    finally:
        if own:
            pool.close()
    return out


def _compute_object(ctx, job):
    """Compute one object (cut, bleed, cutout). Independent of other objects -> can also run in its own
        worker process. Returns (CutObject | None, cutout in the window | None).
    """
    import numpy as np
    from contourpy import LineType, contour_generator
    from PIL import Image, ImageDraw
    from scipy import ndimage as ndi
    obj, rgbw, (wy0, wy1, wx0, wx1), (ox0, oy0, ox1, oy1) = job
    s, pad, px, H = ctx.s, ctx.pad, ctx.px, ctx.H
    off, sm, bl, use_bleed, bg_rgb = ctx.off, ctx.sm, ctx.bl, ctx.use_bleed, ctx.bg_rgb
    knock_patch = None

    def to_pt(col, row):
        return float((col - pad) / px), float(H - (row - pad) / px)

    def to_px(x, y):
        return x * px + pad, (H - y) * px + pad

    # 2. Schnittbereich
    paths = []
    if s.shape == "contour":
        if off >= 0:
            d_out = ndi.distance_transform_edt(~obj)
            region = d_out <= off if off > 0 else obj.copy()
            # smoothing (closing by sm): distance to region = distance to object − distance -> one field fewer
            dil = (d_out <= off + sm) if sm > 0 else None
        else:
            region = ndi.distance_transform_edt(obj) > -off
            dil = (ndi.distance_transform_edt(~region) <= sm) if sm > 0 else None
        if sm > 0:
            region = ndi.distance_transform_edt(dil) > sm
        if not s.inner:
            region = ndi.binary_fill_holes(region)
        field_ = ndi.gaussian_filter(region.astype(np.float32), sigma=max(1.0, sm / 2.5))
        cut = field_ >= 0.5
        step = max(0.25, min(0.5, s.smooth_mm / 3 if s.smooth_mm > 0 else 0.25)) * MM
        for line in contour_generator(z=field_, line_type=LineType.Separate).lines(0.5):
            if len(line) < 8:
                continue
            pts = np.column_stack([(line[:, 0] + wx0 - pad) / px, H - (line[:, 1] + wy0 - pad) / px])
            if np.allclose(pts[0], pts[-1]):
                pts = pts[:-1]
            if float(np.sum(np.hypot(*np.diff(pts, axis=0).T))) < s.min_size_mm * MM:
                continue
            paths.append((_resample(pts, step).tolist(), True))
    else:
        mx0, my1 = to_pt(ox0, oy0)
        mx1, my0 = to_pt(ox1, oy1)
        w, h = _offset_shape(s, mx1 - mx0, my1 - my0)
        poly = shape_polygon(s.shape, (mx0 + mx1) / 2 + s.shift_x_mm * MM, (my0 + my1) / 2 + s.shift_y_mm * MM, w, h,
                             s.corner_mm * MM + (s.offset_mm * MM if s.shape == "rounded" else 0))
        paths.append((poly.tolist(), False))
        im = Image.new("L", (wx1 - wx0, wy1 - wy0), 0)
        ImageDraw.Draw(im).polygon([(to_px(x, y)[0] - wx0, to_px(x, y)[1] - wy0) for x, y in poly], fill=255)
        cut = np.asarray(im) > 127
    if not paths:
        return None, None

    # 3. bleed: the ENTIRE area inside the cut line (including bays, gaps between
    #    object and line) plus "bleed" beyond the line – filled with the outward-extended
    #    Randfarben des Objekts. Liegt HINTER dem Objekt, Verzerrungen sind dadurch unsichtbar bzw. werden
    #    trimmed. The cut line thus always sits inside the bleed.
    bleed = (cut | (ndi.distance_transform_edt(~cut) <= bl)) if use_bleed else np.zeros_like(cut)
    # bleed color
    bg_vec = bg_rgb if bg_rgb is not None else np.array([255, 255, 255])
    core = obj
    for it in (max(2, int(round(0.5 * MM * px))), max(1, int(round(0.25 * MM * px))), 1):
        c2 = ndi.binary_erosion(obj, iterations=it)
        if c2.sum() > 0.15 * obj.sum():
            core = c2
            break
    pal, solid_share = _solid_palette(rgbw[core], bg_rgb, s.detect.tolerance)
    flat = pal is not None and solid_share > 0.85
    labels = None
    if s.bleed_color:
        # fixed color: uniform border (for artwork where the automatic color does not fit)
        c = s.bleed_color.lstrip("#")
        fill = np.empty(obj.shape + (3,), np.uint8)
        fill[:] = (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))
    elif flat:
        # assign every object pixel to its solid color (unmixing), then take over from the nearest object pixel
        labels = np.full(obj.shape, -1, np.int32)
        labels[obj] = _unmix_labels(rgbw[obj], pal, bg_vec, s.detect.tolerance * 2)
        _d, (iy, ix) = ndi.distance_transform_edt(~obj, return_indices=True)
        fill = pal[labels[iy, ix]].astype(np.uint8)
    else:
        # photo (no solid colors): color from the nearest core pixel (~0.5 mm inside, without blend fringe)
        _d, (iy, ix) = ndi.distance_transform_edt(~core, return_indices=True)
        fill = rgbw[iy, ix]
    alpha = np.clip(ndi.gaussian_filter(bleed.astype(np.float32), 0.7), 0, 1)
    alpha[cut] = 1.0                                   # always opaque inside the cut shape (no holes)
    alpha = (alpha * 255).astype(np.uint8)
    img = bbox = None
    if bleed.any():
        yy, xx = np.where(alpha > 0)
        by0, by1, bx0, bx1 = yy.min(), yy.max() + 1, xx.min(), xx.max() + 1
        rgb_b = fill[by0:by1, bx0:bx1].astype(np.uint8).copy()
        al_b = alpha[by0:by1, bx0:bx1]
        # invisible pixels white: if a program/driver cannot read the transparency (SMask), otherwise a
        # colored rectangle appears – this way it stays paper white
        rgb_b[al_b == 0] = 255
        img = np.dstack([rgb_b, al_b])
        p0 = to_pt(bx0 + wx0, by0 + wy0)
        p1 = to_pt(bx1 + wx0, by1 + wy0)
        bbox = (p0[0], p1[1], p1[0], p0[1])
    # artwork with a background (white page, raster image): clip the original to the object shape, otherwise
    # the background covers the bleed. Interior areas (white text, holes) are preserved.
    clip = []
    if ctx.has_knock:
        vis = ndi.binary_fill_holes(obj)
        if s.shape == "contour" and s.inner:
            # knock holes that will be cut out out of the original -> the bleed runs into the hole;
            # small interior areas (white text and the like) stay visible
            holes, nh = ndi.label(vis & ~obj)
            if nh:
                sizes = ndi.sum(np.ones_like(holes), holes, range(1, nh + 1))
                big = np.isin(holes, np.where(sizes >= (s.min_size_mm * MM * px) ** 2 * 0.25)[0] + 1)
                vis &= ~big
        # do not show the blend fringe at the edge (edge smoothing, blurred raster) – the
        # solid-color bleed lies there. Flat artwork: knock out everything at the edge that matches no solid color
        # (max. 1,5 mm tief); Fotos (keine Vollfarben): fester kleiner Abstand.
        d_in = ndi.distance_transform_edt(vis)
        if flat:
            # am Rand nur echte Vollfarb-Pixel zeigen (enge Toleranz -> kein heller Strich an der Linie)
            tol2 = max(12, s.detect.tolerance * 0.6) ** 2
            # only the border strip (up to 1.5 mm) is needed -> search for the nearest solid color only there
            cand = vis & (d_in <= 1.5 * MM * px)
            nonsolid = np.zeros_like(vis)
            if cand.any():
                nonsolid[cand] = _nearest_dist(rgbw[cand].astype(np.int16), pal) > tol2
            vis &= ~nonsolid
            vis = ndi.binary_opening(vis, iterations=1)
            # close tiny holes (scattered blend pixels) – otherwise white speckles
            close = max(1, int(round(0.15 * MM * px)))
            vis = ndi.binary_closing(vis, iterations=close) & (d_in > 0)
            thr = 0.08 * MM * px
            if thr >= 1.0:                       # beneath it, the condition is met for every artwork point
                vis = ndi.distance_transform_edt(vis) > thr
        else:
            vis = d_in > 0.25 * MM * px
        knock_patch = vis
        fld = ndi.gaussian_filter(vis.astype(np.float32), 0.6)
        for line in contour_generator(z=fld, line_type=LineType.Separate).lines(0.5):
            if len(line) >= 4:
                clip.append([[float((c + wx0 - pad) / px), float(H - (r_ + wy0 - pad) / px)] for c, r_ in line])
    ov_img = ov_box = None
    if s.clean_seams and flat:
        # replace narrow blend fringes INSIDE the artwork (e.g. a red/green edge) with the assigned solid color
        if labels is None:
            labels = np.full(obj.shape, -1, np.int32)
            labels[obj] = _unmix_labels(rgbw[obj], pal, bg_vec, s.detect.tolerance * 2)
        tol2 = (s.detect.tolerance * 2) ** 2
        nonsolid = np.zeros_like(obj)
        if obj.any():
            nonsolid[obj] = _nearest_dist(rgbw[obj].astype(np.int16), pal) > tol2
        # fringes up to ~1 mm wide count as blend edges; wider areas = intentional gradient/photo -> kept
        thick = ndi.binary_opening(nonsolid, iterations=max(1, int(round(0.5 * MM * px))))
        seam = nonsolid & ~thick
        if knock_patch is not None:
            seam &= knock_patch           # cutout of this object (objects do not overlap)
        if seam.any():
            yy, xx = np.where(seam)
            sy0, sy1, sx0, sx1 = yy.min(), yy.max() + 1, xx.min(), xx.max() + 1
            col = pal[np.clip(labels[sy0:sy1, sx0:sx1], 0, None)].astype(np.uint8)
            sm_ = seam[sy0:sy1, sx0:sx1]
            # outside the fringes the original artwork: if a program/driver ignores the transparency (SMask),
            # you only see the artwork instead of a colored rectangle above the object
            col[~sm_] = rgbw[sy0:sy1, sx0:sx1][~sm_].astype(np.uint8)
            al = (sm_ * 255).astype(np.uint8)
            ov_img = np.dstack([col, al])
            q0 = to_pt(sx0 + wx0, sy0 + wy0)
            q1 = to_pt(sx1 + wx0, sy1 + wy0)
            ov_box = (q0[0], q1[1], q1[0], q0[1])
    mx0, my1 = to_pt(ox0, oy0)
    mx1, my0 = to_pt(ox1, oy1)
    xs_ = [x for p, _ in paths for x, _y in p] + ([bbox[0], bbox[2]] if bbox else [])
    ys_ = [y for p, _ in paths for _x, y in p] + ([bbox[1], bbox[3]] if bbox else [])
    return CutObject(paths, img, bbox, (mx0, my0, mx1, my1),
                                 (float(min(xs_)), float(min(ys_)), float(max(xs_)), float(max(ys_))), clip,
                                 ov_img, ov_box), knock_patch



def is_fast(s: CutSettings) -> bool:
    """Base shape onto the trim size: pure geometry – nothing rendered, nothing detected, no bleed from the artwork."""
    return s.shape != "contour" and (s.fit or "motif") == "trim" and bool(s.single_shape)   # „je Objekt“ braucht Erkennung


def fast_result(size, trim, s: CutSettings) -> CutResult:
    """Cut line as a base shape onto the trim size. size = page (pt), trim = (left, bottom, right, top) distance
        of the trim size from the page edge in pt (layout.page_trims) or None = whole page. Size/distance/offset as elsewhere.
    """
    W, H = size
    l, b, r, t = trim or (0.0, 0.0, 0.0, 0.0)
    x0, y0, x1, y1 = l, b, W - r, H - t
    w, h = x1 - x0, y1 - y0
    if s.shape == "circle" and not (s.width_mm > 0):
        w = h = min(w, h)                         # Kreis ins Endformat
    sw, sh = _offset_shape(s, w, h)
    poly = shape_polygon(s.shape, (x0 + x1) / 2 + s.shift_x_mm * MM, (y0 + y1) / 2 + s.shift_y_mm * MM, sw, sh,
                         s.corner_mm * MM + (s.offset_mm * MM if s.shape == "rounded" else 0))
    pts = poly.tolist()
    px0, py0 = min(p[0] for p in pts), min(p[1] for p in pts)
    px1, py1 = max(p[0] for p in pts), max(p[1] for p in pts)
    obj = CutObject(paths=[(pts, False)], motif_box=(x0, y0, x1, y1),
                    box=(min(px0, x0), min(py0, y0), max(px1, x1), max(py1, y1)))
    return CutResult(objects=[obj], page_size=(W, H), dpi=s.dpi)


def compute(page, s: CutSettings, rgba=None, size=None, workers: int = 1, progress=None,
            cancel=None, pool=None, trim=None) -> CutResult:
    """Cut + bleed for all objects of a normalized page.
        rgba/size: already rendered page (at s.dpi) and page size in pt – then pdfium is not used here,
        and the computation may run in a background thread (pdfium is not thread-safe).
    """
    import numpy as np
    from contourpy import LineType, contour_generator
    from PIL import Image, ImageDraw
    from scipy import ndimage as ndi

    W, H = size if size is not None else page.get_size()
    if is_fast(s):
        return fast_result((W, H), trim, s)
    px = s.dpi / 72.0
    if rgba is None:
        rgba = render_rgba(page, s.dpi)
    mask, mode = motif_mask(rgba, s.detect)
    bg_rgb = None
    if mode == "color":
        _rgb = rgba[:, :, :3].astype(np.int16)
        bg_rgb = np.median(np.concatenate([_rgb[0], _rgb[-1], _rgb[:, 0], _rgb[:, -1]]), axis=0)
    off = s.offset_mm * MM * px
    sm = max(0.0, s.smooth_mm * MM * px) if s.shape == "contour" else 0.0
    use_bleed = s.bleed and s.bleed_mm > 0
    bl = max(0.0, s.bleed_mm * MM * px) if use_bleed else 0.0
    grow_shape = 0.0
    if s.shape != "contour":
        # fixed size / scaling can enlarge the shape beyond the object
        grow_shape = max(0.0, (s.scale_pct / 100.0 - 1) * max(mask.shape) / 2, (s.width_mm + s.height_mm) * MM * px)
        grow_shape += (abs(s.shift_x_mm) + abs(s.shift_y_mm)) * MM * px     # Versatz braucht Platz
    pad = int(math.ceil(max(off, 0) + sm + bl + grow_shape + 6))
    mask = np.pad(mask, pad)
    rgb = np.pad(rgba[:, :, :3], ((pad, pad), (pad, pad), (0, 0)), mode="edge")

    def to_pt(col, row):
        return float((col - pad) / px), float(H - (row - pad) / px)

    def to_px(x, y):
        return x * px + pad, (H - y) * px + pad

    # 1. Objekte: nahe Teile zusammenfassen, Staub entfernen
    gap = s.detect.gap_mm * MM * px / 2
    work = (ndi.distance_transform_edt(~mask) <= gap) if gap > 0 else mask
    lab, n = ndi.label(work)
    minpx = s.min_size_mm * MM * px
    if s.shape != "contour" and s.single_shape and n > 1:
        # Grundform: alle Teile des Motivs (ohne Staub) zu EINEM Objekt -> eine Form, mittig, Skalierung ab der Mitte
        keep = [k for k, sl in enumerate(ndi.find_objects(lab), start=1)
                if sl is not None and (sl[1].stop - sl[1].start) >= minpx and (sl[0].stop - sl[0].start) >= minpx]
        lab = np.isin(lab, keep).astype(np.int32) if keep else np.zeros_like(lab, dtype=np.int32)
        n = 1 if keep else 0
    out_objects = []
    # punch out the background only if bleed lies underneath – without bleed the artwork stays unchanged
    knock = np.zeros_like(mask) if (mode == "color" and use_bleed) else None
    jobs = []
    for k, sl in enumerate(ndi.find_objects(lab), start=1):
        if sl is None:
            continue
        ys, xs = sl
        obj_full = (lab[ys, xs] == k) & mask[ys, xs]
        if not obj_full.any():
            continue
        rows = np.where(obj_full.any(axis=1))[0]
        cols = np.where(obj_full.any(axis=0))[0]
        oy0, oy1 = ys.start + rows[0], ys.start + rows[-1] + 1
        ox0, ox1 = xs.start + cols[0], xs.start + cols[-1] + 1
        if (ox1 - ox0) < minpx or (oy1 - oy0) < minpx:
            continue
        # working window around the object (room for distance, smoothing, bleed, shape size)
        g = pad
        wy0, wy1 = max(0, oy0 - g), min(mask.shape[0], oy1 + g)
        wx0, wx1 = max(0, ox0 - g), min(mask.shape[1], ox1 + g)
        obj = (lab[wy0:wy1, wx0:wx1] == k) & mask[wy0:wy1, wx0:wx1]
        rgbw = rgb[wy0:wy1, wx0:wx1]

        jobs.append((obj, rgbw, (wy0, wy1, wx0, wx1), (ox0, oy0, ox1, oy1)))
    ctx = _ObjCtx(s, pad, px, H, off, sm, bl, use_bleed, bg_rgb, knock is not None)
    results = _run_objects(ctx, jobs, workers, progress, cancel, pool)
    for (cobj, patch), (_o, _r, (wy0, wy1, wx0, wx1), _b) in zip(results, jobs):
        if cobj is None:
            continue
        if patch is not None:
            knock[wy0:wy1, wx0:wx1] |= patch
        out_objects.append(cobj)
    from .objects import Box, reading_order
    boxes = [Box(*o.motif_box) for o in out_objects]
    order = reading_order(list(boxes))
    out_objects = [out_objects[boxes.index(b)] for b in order]
    km = knock[pad:-pad, pad:-pad] if knock is not None else None
    return CutResult(out_objects, (W, H), km, s.dpi)


# --------------------------------------------------------------------------- #
def build_pdf(norm_doc, results: dict, s: CutSettings) -> bytes:
    """Normalized document + results -> PDF with bleed (under the artwork) and CutContour paths.

        results: {page index: CutResult}. With per_object, every object becomes its own page.
    """
    import numpy as np
    import pikepdf
    import pypdfium2 as pdfium
    from PIL import Image

    # Seitenliste festlegen: (Quellseite, [Objekte], Einzelobjekt?)
    plan = []
    for i in range(len(norm_doc)):
        r = results.get(i)
        if r is None or not r.objects:
            plan.append((i, [], False))
        elif s.per_object:
            plan += [(i, [o], True) for o in r.objects]
        else:
            plan.append((i, r.objects, False))
    tmp = pdfium.PdfDocument.new()
    for i, _objs, _single in plan:
        tmp.import_pages(norm_doc, [i])
    buf = io.BytesIO()
    tmp.save(buf)
    tmp.close()
    pdf = pikepdf.open(io.BytesIO(buf.getvalue()))

    fn = pikepdf.Dictionary(FunctionType=2, Domain=[0, 1], C0=[0, 0, 0, 0], C1=[0, 1, 0, 0], N=1)
    cs = pikepdf.Array([pikepdf.Name.Separation, pikepdf.Name("/" + s.spot), pikepdf.Name.DeviceCMYK, fn])
    gs = pikepdf.Dictionary(Type=pikepdf.Name.ExtGState, OP=True, op=True, OPM=1)

    def sub(d, key):
        if key not in d:
            d[key] = pikepdf.Dictionary()
        return d[key]

    for page, (src, objs, single) in zip(pdf.pages, plan):
        if not objs:
            continue
        mb = [float(v) for v in page.MediaBox]
        if single:
            o = objs[0]
            m = s.margin_mm * MM
            box = [o.box[0] - m, o.box[1] - m, o.box[2] + m, o.box[3] + m]
        else:
            box = [min([mb[0]] + [o.box[0] for o in objs]), min([mb[1]] + [o.box[1] for o in objs]),
                   max([mb[2]] + [o.box[2] for o in objs]), max([mb[3]] + [o.box[3] for o in objs])]
        page.MediaBox = [float(v) for v in box]
        for k in ("/CropBox", "/TrimBox", "/BleedBox", "/ArtBox"):
            if k in page.obj:
                del page.obj[k]
        if single:
            # trim size = cut line, bleed area = bleed: when imposing (step & repeat "bleed against
            # bleed"), the bleeds then touch each other instead of the white page margins
            pts = [pt for poly, _sm in objs[0].paths for pt in poly]
            if pts:
                tx0, ty0 = max(box[0], min(p_[0] for p_ in pts)), max(box[1], min(p_[1] for p_ in pts))
                tx1, ty1 = min(box[2], max(p_[0] for p_ in pts)), min(box[3], max(p_[1] for p_ in pts))
                if tx1 - tx0 > 2 and ty1 - ty0 > 2:
                    page.TrimBox = [float(tx0), float(ty0), float(tx1), float(ty1)]
                    ob = objs[0].box
                    page.BleedBox = [float(max(box[0], min(ob[0], tx0))), float(max(box[1], min(ob[1], ty0))),
                                     float(min(box[2], max(ob[2], tx1))), float(min(box[3], max(ob[3], ty1)))]
        res = sub(page.obj, "/Resources")
        def image(arr, name, box):
            a = np.asarray(arr)
            rgb = Image.fromarray(a[:, :, :3].astype(np.uint8), "RGB")
            al = Image.fromarray(a[:, :, 3].astype(np.uint8), "L")
            smask = pikepdf.Stream(pdf, al.tobytes())
            smask.Type, smask.Subtype = pikepdf.Name.XObject, pikepdf.Name.Image
            smask.Width, smask.Height = al.width, al.height
            smask.ColorSpace, smask.BitsPerComponent = pikepdf.Name.DeviceGray, 8
            im = pikepdf.Stream(pdf, rgb.tobytes())
            im.Type, im.Subtype = pikepdf.Name.XObject, pikepdf.Name.Image
            im.Width, im.Height = rgb.width, rgb.height
            im.ColorSpace, im.BitsPerComponent = pikepdf.Name.DeviceRGB, 8
            im.SMask = smask
            sub(res, "/XObject")[name] = im
            bx0, by0, bx1, by1 = box
            return f"q {bx1 - bx0:.4f} 0 0 {by1 - by0:.4f} {bx0:.4f} {by0:.4f} cm {name} Do Q"

        under, over = [], []
        for j, o in enumerate(objs):
            if o.bleed_rgba is not None:
                under.append(image(o.bleed_rgba, f"/PTBleed{j}", o.bleed_box))
            if o.overlay_rgba is not None:
                over.append(image(o.overlay_rgba, f"/PTSeam{j}", o.overlay_box))
        pre = "\n".join(under) + "\nq\n"        # include the original: it may throw off the coordinate system
        nq = 1
        if single:
            # show only this object (hide neighbors on the sheet): clip the content to bleed/object
            o = objs[0]
            cb = o.bleed_box or o.motif_box
            x0, y0 = min(cb[0], o.motif_box[0]), min(cb[1], o.motif_box[1])
            x1, y1 = max(cb[2], o.motif_box[2]), max(cb[3], o.motif_box[3])
            pre += f"q {x0:.3f} {y0:.3f} {x1 - x0:.3f} {y1 - y0:.3f} re W n\n"
            nq += 1
        clips = [c for o in objs for c in o.clip]
        if clips:
            # Hintergrund ausstanzen: Original nur innerhalb der Objektumrisse zeigen
            pre += "q\n" + "\n".join(line_ops(c) for c in clips) + "\nW* n\n"
            nq += 1
        page.contents_add(pikepdf.Stream(pdf, pre.encode()), prepend=True)
        post = "Q\n" * nq
        sub(res, "/ColorSpace")["/CSCut"] = cs
        sub(res, "/ExtGState")["/GSCut"] = gs
        ops = [post + "\n".join(over) + f"\nq /GSCut gs /CSCut CS 1 SCN {s.stroke_pt:.3f} w 1 j 1 J"]
        for o in objs:
            for poly, smooth in o.paths:
                ops.append(bezier_ops(poly) if smooth else line_ops(poly))
        ops.append("S Q")
        page.contents_add(pikepdf.Stream(pdf, ("\n" + "\n".join(ops) + "\n").encode()), prepend=False)
    out = io.BytesIO()
    pdf.save(out)
    pdf.close()
    return out.getvalue()


def make(doc, s: CutSettings, pages: list[int] | None = None, progress=None, cancel=None, workers: int = 1):
    """Komplett: normalisieren, Schnitte berechnen, PDF bauen. Liefert (pypdfium2-Dokument, Anzahl Schnitte).
    progress(erledigt, gesamt, text) je Seite; cancel() -> True bricht ab (core.Cancelled)."""
    import pypdfium2 as pdfium
    from .objects import normalized
    norm = normalized(doc)
    results, total = {}, 0
    todo = list(pages) if pages is not None else list(range(len(norm)))
    if is_fast(s):                                        # Grundform aufs Endformat: keine Berechnung, kein Prozess
        from .layout import page_trims
        trims = page_trims(doc)
        for k, i in enumerate(todo):
            if progress is not None:
                progress(k, len(todo), tr("Seite {0}/{1}").format(k + 1, len(todo)))
            results[i] = fast_result(norm.get_page_size(i), trims[i], s)
            total += 1
        if progress is not None:
            progress(len(todo), len(todo), tr("Schreibe PDF …"))
        return _make_finish(norm, results, total, s, pages)
    pool = WorkerPool(workers) if workers > 1 else None
    try:
        at_once = _pages_at_once(norm, todo, s, workers) if (pool is not None and len(todo) >= 2) else 1
        if at_once >= 2:
            results, total = _make_pages_parallel(norm, s, todo, progress, cancel, pool, at_once)
        else:                                             # one page (or too large): objects in parallel
            results, total = _make_pages(norm, s, todo, progress, cancel, pool)
    except BaseException:
        norm.close()
        raise
    finally:
        if pool is not None:
            pool.close()
    if progress is not None:
        progress(len(todo), len(todo), tr("Schreibe PDF …"))
    return _make_finish(norm, results, total, s, pages)


PAGE_MEMORY_SHARE = 0.4             # share of RAM for pages computed simultaneously
PAGE_MEMORY_FALLBACK = 3_000_000_000  # wenn der Arbeitsspeicher nicht ermittelbar ist


def page_memory_budget() -> int:
    """Bytes for pages computed simultaneously (all worker processes together) – scaled by the machine, at least 1 GB."""
    from . import platform as _platform
    total = _platform.total_memory()
    return max(1_000_000_000, int(total * PAGE_MEMORY_SHARE)) if total else PAGE_MEMORY_FALLBACK
BYTES_PER_PIXEL = 40                 # grobe Spitze je Bildpunkt (Bild, Masken, Abstandsfelder)


def _page_worker(path: str, i: int, s: CutSettings):
    """Arbeitsprozess: eine ganze Seite rechnen (eigenes pdfium – in eigenen Prozessen sicher)."""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(path)
    try:
        pg = doc[i]
        try:
            return compute(pg, s)
        finally:
            pg.close()
    finally:
        doc.close()


def _pages_at_once(norm, todo, s, workers: int) -> int:
    """How many pages may be computed simultaneously (based on the estimated memory need of the largest page)."""
    px = s.dpi / 72.0
    biggest = 0
    for i in todo:
        w, h = norm.get_page_size(i)
        biggest = max(biggest, w * px * h * px)
    per_page = max(1.0, biggest * BYTES_PER_PIXEL)
    return max(1, min(workers, len(todo), int(page_memory_budget() // per_page)))


def _make_pages_parallel(norm, s, todo, progress, cancel, pool, at_once):
    """Mehrere Seiten gleichzeitig: jeder Arbeitsprozess rechnet eine ganze Seite (kein Warten zwischen Seiten)."""
    import os
    import tempfile
    from concurrent.futures import FIRST_COMPLETED, wait
    fd, path = tempfile.mkstemp(prefix="passermark-cut-", suffix=".pdf")
    os.close(fd)
    try:
        norm.save(path)                                   # normalized pages for the worker processes
        ex = pool.get()
        results, total, waiting = {}, 0, list(todo)
        running = {}
        done = 0
        if progress is not None:
            progress(0, len(todo), tr("Seite {0}/{1}").format(1, len(todo)))
        try:
            while waiting or running:
                if cancel is not None and cancel():
                    from .core import Cancelled
                    raise Cancelled(tr("Abgebrochen."))
                while waiting and len(running) < at_once:  # at most as many pages as fit into memory
                    i = waiting.pop(0)
                    running[ex.submit(_page_worker, path, i, s)] = i
                finished, _ = wait(list(running), timeout=0.2, return_when=FIRST_COMPLETED)
                for f in finished:
                    i = running.pop(f)
                    results[i] = f.result()
                    total += len(results[i].paths)
                    done += 1
                    if progress is not None:
                        progress(done, len(todo), tr("{0} von {1} Seiten fertig").format(done, len(todo)))
        except BaseException:
            pool.close()                                  # Abbruch/Fehler: offene Seiten verwerfen
            raise
        return results, total
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _make_pages(norm, s, todo, progress, cancel, pool):
    """Compute all selected pages; progress per page and per object."""
    results, total = {}, 0
    for k, i in enumerate(todo):
        if cancel is not None and cancel():
            from .core import Cancelled
            raise Cancelled(tr("Abgebrochen."))
        page_txt = tr("Seite {0}/{1}").format(k + 1, len(todo))
        if progress is not None:
            progress(k, len(todo), page_txt)

        def obj_progress(done, n, k=k, page_txt=page_txt):
            if progress is not None and n:
                progress(k, len(todo), page_txt + " · " + tr("Objekt {0}/{1}").format(min(done + 1, n), n))
        pg = norm[i]
        try:
            results[i] = compute(pg, s, progress=obj_progress, cancel=cancel, pool=pool)
        finally:
            pg.close()
        total += len(results[i].paths)
    return results, total


def _make_finish(norm, results, total, s, pages):
    """Assemble the results into the PDF (bleed under the artwork, CutContour paths)."""
    import pypdfium2 as pdfium
    if not total:
        norm.close()
        raise ValueError(tr("Kein Motiv gefunden – Hintergrund/Toleranz prüfen."))
    if pages is not None and s.per_object:
        # only selected pages -> output only their objects
        keep = sorted(results)
        tmp = pdfium.PdfDocument.new()
        tmp.import_pages(norm, keep)
        results = {k: results[i] for k, i in enumerate(keep)}
        norm.close()
        norm = tmp
    data = build_pdf(norm, results, s)
    norm.close()
    return pdfium.PdfDocument(data), total
