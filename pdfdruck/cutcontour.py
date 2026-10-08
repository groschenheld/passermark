# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""CutContour für Schneideplotter (Roland VersaWorks u. a.) mit automatisch erzeugtem Überfüller.

Ablauf je Objekt (Seite normalisiert, siehe objects.py):
  1. Objekt aus dem Bogen herauslösen (Motivmaske, nahe Teile zusammengefasst)
  2. Schnittform festlegen:
       contour – folgt dem Motiv (Abstand + Glättung zum Entgittern; folgt dann bewusst nicht exakt)
       rect, rounded, circle, oval, hexagon, octagon, heart, star, shield, arch – klassische Stickerformen
       in Objektgröße (ohne Überfüller), skalierbar oder in fester Größe, zentriert über dem Objekt
  3. Überfüller: Die Randfarben des Objekts werden nach außen gezogen (nächster Motivpunkt) und füllen die
     ganze Fläche innerhalb der Schnittlinie (auch Einbuchtungen und den Raum zwischen Objekt und Linie) plus
     „Überfüller“ über die Linie hinaus. Er liegt HINTER dem Objekt; der Schnitt liegt immer darin.
  4. Ausgabe: Überfüller als Bild unter dem unveränderten (vektoriellen) Motiv, Schnitt als Pfad in der
     Sonderfarbe „CutContour“ (Separation, Ersatzfarbe 100 % Magenta), Überdrucken.
     Wahlweise auf dem Originalbogen oder jedes Objekt als eigene Seite mit Rand.
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
    offset_mm: float = 0.0         # Schnitt: + nach außen, − nach innen (vom Motiv bzw. von der Objektgröße)
    bleed: bool = True             # Überfüller erzeugen (aus = Motiv unverändert, z. B. für weiße Ränder)
    bleed_mm: float = 2.0          # Überfüller (ab Objekt, mindestens so weit über die Schnittlinie)
    smooth_mm: float = 1.5         # nur Kontur: Buchten < 2× werden überbrückt, Kanten gerundet
    inner: bool = False            # nur Kontur: Innenkonturen (Löcher) mitschneiden
    corner_mm: float = 3.0         # abgerundetes Rechteck: Eckenradius
    scale_pct: float = 100.0       # Formen: Größe relativ zum Objekt
    width_mm: float = 0.0          # Formen: Größe der Schnittlinie in mm (0 = aus dem Objekt + Abstand)
    height_mm: float = 0.0
    shift_x_mm: float = 0.0        # Formen: Versatz der Form gegenüber der Motivmitte (+ rechts)
    shift_y_mm: float = 0.0        # (+ oben)
    min_size_mm: float = 3.0
    bleed_color: str = ""          # "" = automatisch aus dem Motiv, sonst feste Farbe "#rrggbb" (gleichmäßiger Rand)
    clean_seams: bool = False      # schmale Mischkanten im Motiv durch Vollfarben ersetzen (nur flächige Motive)
    single_shape: bool = True      # Grundformen: EINE Form um das ganze Motiv (False = eine Form je Objekt)
    per_object: bool = False       # jedes Objekt als eigene Seite
    margin_mm: float = 6.0         # Rand der Einzelseiten um Überfüller/Schnitt
    spot: str = "CutContour"
    stroke_pt: float = 0.25
    detect: DetectSettings = field(default_factory=lambda: DetectSettings(gap_mm=1.0))


@dataclass
class CutObject:
    paths: list                    # [(Punkte [(x, y)…] in pt, glatt: bool)]
    bleed_rgba: object = None      # numpy (h, w, 4)
    bleed_box: tuple | None = None # (x0, y0, x1, y1) pt
    motif_box: tuple = (0, 0, 0, 0)
    box: tuple = (0, 0, 0, 0)      # Ausdehnung von Schnitt + Überfüller
    clip: list = field(default_factory=list)   # Umriss des Objekts (nur bei Motiven mit Hintergrund)
    overlay_rgba: object = None    # bereinigte Mischkanten (über dem Motiv)
    overlay_box: tuple | None = None


@dataclass
class CutResult:
    objects: list                  # [CutObject]
    page_size: tuple = (0, 0)
    knockout: object = None       # bool-Maske (Seite, dpi) – sichtbarer Teil des Originals (Hintergrund ausgestanzt)
    dpi: int = 0

    @property
    def paths(self):               # alle Schnittpfade (für Vorschau/Zählung)
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
            w = h = max(w, h)                  # um das ganze Motiv herum (größere Seite), nicht hindurch
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
        # Wappen: oben gerade, Seiten senkrecht, unten in zwei Bögen zur Spitze
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
    """Geschlossene Punktfolge gleichmäßig nach Bogenlänge neu verteilen (verhindert Überschwinger)."""
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
    """Formgröße: angegebene Größe gilt EXAKT als Schnittlinie; ohne Angabe Objektgröße + Abstand.
    Nur eine Angabe (Breite oder Höhe): das Seitenverhältnis des Objekts bleibt."""
    k = s.scale_pct / 100.0                      # nur noch für Aufrufer der Programmschnittstelle (Oberfläche: 100)
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
    """Vollfarben eines Objekts (häufige Farben im Kern) und Anteil der Kernpixel, die einer davon entsprechen."""
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
    n = max(1, len(raw) // 3)                          # bei wenigen Farben liefert Pillow eine kürzere Palette
    pal = np.asarray(raw[:n * 3], dtype=np.int16).reshape(n, 3)
    counts = np.bincount(np.asarray(q).ravel(), minlength=n)[:n]
    keep = counts >= max(1, 0.01 * len(pix))
    if bg is not None:
        keep &= np.abs(pal - bg).max(axis=1) > tol * 2
    pal = pal[keep]
    if len(pal) == 0:
        return None, 0.0
    # exakte Farbtöne: Median der echten Pixel je Farbgruppe (bei Flächenfarben = Originalwert)
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
    """Jedem Pixel die Vollfarbe zuordnen, aus der es durch Mischung entstanden ist.

    Ein Kantenpixel liegt (physikalisch) auf der Linie Vollfarbe–Hintergrund bzw. Vollfarbe–Vollfarbe. Gewählt
    wird die Linie mit dem kleinsten Abstand; bei zwei Vollfarben die nähere Seite. So wird helles Rosa eindeutig
    Rot – auch wenn es im einfachen RGB-Abstand näher an Grün läge."""
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
    rest = np.where(d0.min(axis=1) > solid_tol ** 2)[0]          # nur Misch-/Kantenpixel genauer prüfen
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
    top = np.argsort(-np.bincount(lab, minlength=K))[:8]           # Vollfarbe–Vollfarbe (häufigste)
    for i in range(len(top)):
        for j in range(i + 1, len(top)):
            line(C[top[i]], C[top[j]], int(top[i]), int(top[j]))
    lab[rest] = bl
    return lab


def _snap_to_solid(fill, core_px, bg, tol):
    """Jede Überfüller-Farbe auf die nächste Vollfarbe des Objekts setzen (siehe _solid_palette).
    Bei Fotos (viele Töne) bleiben die Farben ähnlich – sie liegen hinter dem Objekt bzw. außerhalb des Schnitts."""
    import numpy as np
    pal, _share = _solid_palette(core_px, bg, tol)
    if pal is None:
        return fill
    flat = fill.reshape(-1, 3).astype(np.int16)
    return pal[_nearest_idx(flat, pal)].reshape(fill.shape).astype(np.uint8)


def compute(page, s: CutSettings, rgba=None, size=None) -> CutResult:
    """Schnitt + Überfüller für alle Objekte einer normalisierten Seite.
    rgba/size: schon gerenderte Seite (bei s.dpi) und Seitengröße in pt – dann wird pdfium hier nicht benutzt,
    und die Berechnung darf in einem Hintergrund-Thread laufen (pdfium ist nicht thread-sicher)."""
    import numpy as np
    from contourpy import LineType, contour_generator
    from PIL import Image, ImageDraw
    from scipy import ndimage as ndi

    W, H = size if size is not None else page.get_size()
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
        # feste Größe / Skalierung kann die Form über das Objekt hinaus vergrößern
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
    # Hintergrund nur ausstanzen, wenn ein Überfüller darunter liegt – ohne Überfüller bleibt das Motiv unverändert
    knock = np.zeros_like(mask) if (mode == "color" and use_bleed) else None
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
        # Arbeitsfenster um das Objekt (Platz für Abstand, Glättung, Überfüller, Formgröße)
        g = pad
        wy0, wy1 = max(0, oy0 - g), min(mask.shape[0], oy1 + g)
        wx0, wx1 = max(0, ox0 - g), min(mask.shape[1], ox1 + g)
        obj = (lab[wy0:wy1, wx0:wx1] == k) & mask[wy0:wy1, wx0:wx1]
        rgbw = rgb[wy0:wy1, wx0:wx1]

        # 2. Schnittbereich
        paths = []
        if s.shape == "contour":
            if off >= 0:
                d_out = ndi.distance_transform_edt(~obj)
                region = d_out <= off if off > 0 else obj.copy()
                # Glättung (Schließen um sm): Abstand zur Region = Abstand zum Objekt − Abstand -> ein Feld weniger
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
            continue

        # 3. Überfüller: die GANZE Fläche innerhalb der Schnittlinie (auch Einbuchtungen, Freiräume zwischen
        #    Objekt und Linie) plus „Überfüller“ über die Linie hinaus – gefüllt mit den nach außen gezogenen
        #    Randfarben des Objekts. Liegt HINTER dem Objekt, Verzerrungen sind dadurch unsichtbar bzw. werden
        #    abgeschnitten. Der Schnitt liegt so immer im Überfüller.
        bleed = (cut | (ndi.distance_transform_edt(~cut) <= bl)) if use_bleed else np.zeros_like(cut)
        # Überfüller-Farbe
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
            # feste Farbe: gleichmäßiger Rand (für Motive, bei denen die automatische Farbe nicht passt)
            c = s.bleed_color.lstrip("#")
            fill = np.empty(obj.shape + (3,), np.uint8)
            fill[:] = (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))
        elif flat:
            # jedes Objektpixel seiner Vollfarbe zuordnen (Entmischen), dann vom nächsten Objektpixel übernehmen
            labels = np.full(obj.shape, -1, np.int32)
            labels[obj] = _unmix_labels(rgbw[obj], pal, bg_vec, s.detect.tolerance * 2)
            _d, (iy, ix) = ndi.distance_transform_edt(~obj, return_indices=True)
            fill = pal[labels[iy, ix]].astype(np.uint8)
        else:
            # Foto (keine Vollfarben): Farbe vom nächsten Kernpixel (~0,5 mm innen, ohne Mischsaum)
            _d, (iy, ix) = ndi.distance_transform_edt(~core, return_indices=True)
            fill = rgbw[iy, ix]
        alpha = np.clip(ndi.gaussian_filter(bleed.astype(np.float32), 0.7), 0, 1)
        alpha[cut] = 1.0                                   # innerhalb der Schnittform immer deckend (keine Löcher)
        alpha = (alpha * 255).astype(np.uint8)
        img = bbox = None
        if bleed.any():
            yy, xx = np.where(alpha > 0)
            by0, by1, bx0, bx1 = yy.min(), yy.max() + 1, xx.min(), xx.max() + 1
            img = np.dstack([fill[by0:by1, bx0:bx1], alpha[by0:by1, bx0:bx1]])
            p0 = to_pt(bx0 + wx0, by0 + wy0)
            p1 = to_pt(bx1 + wx0, by1 + wy0)
            bbox = (p0[0], p1[1], p1[0], p0[1])
        # Motiv mit Hintergrund (weiße Seite, Rasterbild): Original auf die Objektform begrenzen, sonst deckt
        # der Hintergrund den Überfüller zu. Innenflächen (weiße Schrift, Löcher) bleiben erhalten.
        clip = []
        if knock is not None:
            vis = ndi.binary_fill_holes(obj)
            if s.shape == "contour" and s.inner:
                # Löcher, die ausgeschnitten werden, aus dem Original aussparen -> Überfüller läuft ins Loch;
                # kleine Innenflächen (weiße Schrift u. ä.) bleiben sichtbar
                holes, nh = ndi.label(vis & ~obj)
                if nh:
                    sizes = ndi.sum(np.ones_like(holes), holes, range(1, nh + 1))
                    big = np.isin(holes, np.where(sizes >= (s.min_size_mm * MM * px) ** 2 * 0.25)[0] + 1)
                    vis &= ~big
            # Mischsaum an der Kante (Kantenglättung, weichgezeichnetes Raster) nicht zeigen – dort liegt der
            # vollfarbige Überfüller. Flächige Motive: alles am Rand aussparen, was keiner Vollfarbe entspricht
            # (max. 1,5 mm tief); Fotos (keine Vollfarben): fester kleiner Abstand.
            d_in = ndi.distance_transform_edt(vis)
            if flat:
                # am Rand nur echte Vollfarb-Pixel zeigen (enge Toleranz -> kein heller Strich an der Linie)
                tol2 = max(12, s.detect.tolerance * 0.6) ** 2
                # nur der Randstreifen (bis 1,5 mm) wird gebraucht -> nur dort die nächste Vollfarbe suchen
                cand = vis & (d_in <= 1.5 * MM * px)
                nonsolid = np.zeros_like(vis)
                if cand.any():
                    nonsolid[cand] = _nearest_dist(rgbw[cand].astype(np.int16), pal) > tol2
                vis &= ~nonsolid
                vis = ndi.binary_opening(vis, iterations=1)
                # winzige Löcher (vereinzelte Mischpixel) schließen – sonst weiße Pünktchen
                close = max(1, int(round(0.15 * MM * px)))
                vis = ndi.binary_closing(vis, iterations=close) & (d_in > 0)
                thr = 0.08 * MM * px
                if thr >= 1.0:                       # darunter ist die Bedingung für jeden Motivpunkt erfüllt
                    vis = ndi.distance_transform_edt(vis) > thr
            else:
                vis = d_in > 0.25 * MM * px
            knock[wy0:wy1, wx0:wx1] |= vis
            fld = ndi.gaussian_filter(vis.astype(np.float32), 0.6)
            for line in contour_generator(z=fld, line_type=LineType.Separate).lines(0.5):
                if len(line) >= 4:
                    clip.append([[float((c + wx0 - pad) / px), float(H - (r_ + wy0 - pad) / px)] for c, r_ in line])
        ov_img = ov_box = None
        if s.clean_seams and flat:
            # schmale Mischsäume IM Motiv (z. B. Rot/Grün-Kante) durch die zugeordnete Vollfarbe ersetzen
            if labels is None:
                labels = np.full(obj.shape, -1, np.int32)
                labels[obj] = _unmix_labels(rgbw[obj], pal, bg_vec, s.detect.tolerance * 2)
            tol2 = (s.detect.tolerance * 2) ** 2
            nonsolid = np.zeros_like(obj)
            if obj.any():
                nonsolid[obj] = _nearest_dist(rgbw[obj].astype(np.int16), pal) > tol2
            # Säume bis ~1 mm Breite gelten als Mischkante; breitere Bereiche = gewollter Verlauf/Foto -> bleiben
            thick = ndi.binary_opening(nonsolid, iterations=max(1, int(round(0.5 * MM * px))))
            seam = nonsolid & ~thick
            if knock is not None:
                seam &= knock[wy0:wy1, wx0:wx1]
            if seam.any():
                yy, xx = np.where(seam)
                sy0, sy1, sx0, sx1 = yy.min(), yy.max() + 1, xx.min(), xx.max() + 1
                col = pal[np.clip(labels[sy0:sy1, sx0:sx1], 0, None)].astype(np.uint8)
                al = (seam[sy0:sy1, sx0:sx1] * 255).astype(np.uint8)
                ov_img = np.dstack([col, al])
                q0 = to_pt(sx0 + wx0, sy0 + wy0)
                q1 = to_pt(sx1 + wx0, sy1 + wy0)
                ov_box = (q0[0], q1[1], q1[0], q0[1])
        mx0, my1 = to_pt(ox0, oy0)
        mx1, my0 = to_pt(ox1, oy1)
        xs_ = [x for p, _ in paths for x, _y in p] + ([bbox[0], bbox[2]] if bbox else [])
        ys_ = [y for p, _ in paths for _x, y in p] + ([bbox[1], bbox[3]] if bbox else [])
        out_objects.append(CutObject(paths, img, bbox, (mx0, my0, mx1, my1),
                                     (float(min(xs_)), float(min(ys_)), float(max(xs_)), float(max(ys_))), clip,
                                     ov_img, ov_box))
    from .objects import Box, reading_order
    boxes = [Box(*o.motif_box) for o in out_objects]
    order = reading_order(list(boxes))
    out_objects = [out_objects[boxes.index(b)] for b in order]
    km = knock[pad:-pad, pad:-pad] if knock is not None else None
    return CutResult(out_objects, (W, H), km, s.dpi)


# --------------------------------------------------------------------------- #
def build_pdf(norm_doc, results: dict, s: CutSettings) -> bytes:
    """Normalisiertes Dokument + Ergebnisse -> PDF mit Überfüller (unter dem Motiv) und CutContour-Pfaden.

    results: {Seitenindex: CutResult}. Bei per_object wird jedes Objekt eine eigene Seite."""
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
        pre = "\n".join(under) + "\nq\n"        # Original einschließen: es kann das Koordinatensystem verstellen
        nq = 1
        if single:
            # nur dieses Objekt zeigen (Nachbarn auf dem Bogen ausblenden): Inhalt auf Überfüller/Objekt begrenzen
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


def make(doc, s: CutSettings, pages: list[int] | None = None, progress=None, cancel=None):
    """Komplett: normalisieren, Schnitte berechnen, PDF bauen. Liefert (pypdfium2-Dokument, Anzahl Schnitte).
    progress(erledigt, gesamt, text) je Seite; cancel() -> True bricht ab (core.Cancelled)."""
    import pypdfium2 as pdfium
    from .objects import normalized
    norm = normalized(doc)
    results, total = {}, 0
    todo = list(pages) if pages is not None else list(range(len(norm)))
    for k, i in enumerate(todo):
        if cancel is not None and cancel():
            norm.close()
            from .core import Cancelled
            raise Cancelled(tr("Abgebrochen."))
        if progress is not None:
            progress(k, len(todo), tr("Seite {0}/{1}").format(k + 1, len(todo)))
        pg = norm[i]
        try:
            results[i] = compute(pg, s)
        finally:
            pg.close()
        total += len(results[i].paths)
    if progress is not None:
        progress(len(todo), len(todo), tr("Schreibe PDF …"))
    if not total:
        norm.close()
        raise ValueError(tr("Kein Motiv gefunden – Hintergrund/Toleranz prüfen."))
    if pages is not None and s.per_object:
        # nur gewählte Seiten -> nur deren Objekte ausgeben
        keep = sorted(results)
        tmp = pdfium.PdfDocument.new()
        tmp.import_pages(norm, keep)
        results = {k: results[i] for k, i in enumerate(keep)}
        norm.close()
        norm = tmp
    data = build_pdf(norm, results, s)
    norm.close()
    return pdfium.PdfDocument(data), total
