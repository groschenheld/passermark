# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Plan printing on roll printers (production print, usually 75/80 g paper). No Qt.

Per plan (= PDF page):
  * Frame: plans usually come with two outer lines. The outer one is the cut line – printing is limited to it, so
    it disappears and an exact margin stays around the inner frame. Without two outer lines: content + 5 mm.
  * Roll: the one with the shortest run length (rotating is allowed: an A1 goes across the 841 roll instead of
    upright on the 594 – one manual cut more, but less paper). Same length -> the narrower roll.
  * Run length: only the plan sizes (no gaps, no lead-in) – per roll for one set and for all copies.
Printing: one job per plan, page = exact plan size, paper = custom size (roll width × length), feed = the roll.
Order: unsorted by default (plan 1 ×3, plan 2 ×3 …), optionally sorted and/or grouped by roll width.
"""
from __future__ import annotations

import dataclasses
import os
import re
import tempfile
from dataclasses import dataclass, field

from . import layout
from .l10n import tr

MM = layout.MM
PLAN_WEIGHTS = (75, 80)
FRAME_MODES = ("auto", "frame", "margin", "none")
ROTATE_MODES = ("auto", "keep", "short", "long")
BLEED_MODES = ("mirror", "blank", "color")
ORDERS = ("list", "roll")
ALIGNS = ("center", "left", "right")    # Lage quer auf der Rolle
TOL_MM = 0.5                  # Toleranz Rollenbreite


@dataclass
class PlanSettings:
    printer: str = ""                 # leer = Standarddrucker
    color: str = ""                   # color | gray | "" (wie im Treiber)
    media: str = ""                   # Medientyp im Treiber ("" = wie eingestellt)
    frame: str = "auto"               # auto | frame (zwei Außenlinien) | margin (Inhalt + Rand) | none (Seite)
    margin_mm: float = 5.0            # Rand ohne zwei Außenlinien
    rotate: str = "auto"              # auto (kürzeste Länge) | keep (wie angeliefert) | short (kurze Seite quer) | long
    scale_pct: float = 100.0          # Standard: tatsächliche Größe
    bleed_mm: float = 0.0             # Überfüller rundum
    bleed_mode: str = "mirror"        # mirror (gespiegelt) | blank (Leerraum) | color (Einzelfarbe)
    bleed_color: str = "#ffffff"
    crop_marks: bool = False          # Schnittmarken
    copies: int = 1                   # Exemplare (Sätze)
    collate: bool = False             # sortiert: Satz für Satz – Standard: jeder Plan n-mal hintereinander
    order: str = "list"               # list (Reihenfolge der Liste) | roll (nach Rollenbreite, schmal zuerst)
    weights: list = field(default_factory=lambda: list(PLAN_WEIGHTS))   # Planpapier g/m² (Rollenauswahl)
    rolls: list = field(default_factory=list)   # Rollen von Hand [594, 841, …] oder [{"width_mm": …, "slot": …}]
    live_rolls: bool = True           # Rollen vom Gerät lesen
    fix_hairlines: bool = False       # Haarlinien anheben
    hairline_mm: float = 0.1
    options: dict = field(default_factory=dict)     # Treiberoptionen roh
    profile: str = "admin"            # Farbprofil wie beim Druck: admin | none | Profil-ID
    intent: str = ""
    title: str = ""
    dry_run: bool = False
    # 1.18 Teil 2 – Poster/Qualitätsdruck, Banner, Print & Cut, Material
    kind: str = "plan"                # plan (Produktionsdruck) | poster (Qualitätsdruck)
    material: str = ""                # Druckmaterial (printmat) – Name oder ID; "" = keins
    nest: bool = False                # mehrere Stücke nebeneinander auf die Rolle (Poster: Standard an)
    gap_mm: float = 5.0               # Abstand zwischen Stücken beim Nebeneinander
    max_page_m: float = 10.0          # nicht mehr verwendet (seit 1.18.5 ist jede Reihe eine eigene Seite)
    overwidth: str = "none"           # breiter als jede Rolle: none (auslassen) | crop (abschneiden) | tile (Bahnen)
    overlap_mm: float = 20.0          # Überlappung der Bahnen
    fold_marks: bool = False          # Faltmarken nach DIN 824 (vereinfacht)
    hem_mm: float = 0.0               # Saum-/Tunnelzugabe
    hem_sides: str = "lrtb"           # Seiten mit Saum: l r t b (wie die Seite steht)
    grommet_spacing_mm: float = 0.0   # Ösen: Abstand höchstens (0 = keine Ösenmarken)
    grommet_inset_mm: float = 20.0    # Ösen: Mitte ab Endformat-Kante
    grommet_d_mm: float = 10.0        # Ösen: Durchmesser der Marke
    grommet_sides: str = "lrtb"
    cut_contour: bool = False         # CutContour (Sonderfarbe) am Bildrand – für Print & Cut (VersaWorks, CutStudio)
    printcut_marks: bool = False      # zusätzlich Passermarken (Winkel) an den Ecken
    # 1.18.2
    roll_pick: str = ""               # feste Rolle (roll_key) – "" = automatisch
    align: str = "left"               # center | left | right: Lage quer auf der Rolle (Seite = Rollenbreite)
    split_copies: bool = True         # alt (bis 1.18.6): False = Kopienzahl – heute copies_mode
    copies_mode: str = "sheets"       # sheets: ein Auftrag, je Exemplar ein Blatt | jobs: je Exemplar ein Auftrag |
                                      # count: ein Blatt mit Kopienzahl (Gerät entscheidet übers Schneiden)
    scale_mode: str = "pct"           # pct (scale_pct) | short (kurze Kante auf scale_mm) | long (lange Kante)
    scale_mm: float = 0.0
    overrides: dict = field(default_factory=dict)   # je Seite (1-basiert, "3") Abweichungen: {"scale_pct": 200, …}
    cut_sheets: bool = True           # Schneid-Option des Druckers auf „nach jeder Seite“ (IPP trim, CutMedia …)


KINDS = ("plan", "poster")
COPIES_MODES = ("sheets", "jobs", "count")
SCALE_MODES = ("pct", "short", "long")
# Einstellungen, die je Plan/Poster abweichen dürfen (Dialog: Auswahl; CLI/Ablauf: "overrides")
OV_KEYS = ("scale_mode", "scale_pct", "scale_mm", "rotate", "frame", "margin_mm", "bleed_mm", "bleed_mode",
           "bleed_color", "roll_pick", "align", "material")


def copies_mode(s) -> str:
    """Wie Exemplare verschickt werden – split_copies=False (bis 1.18.6) heißt Kopienzahl."""
    if not getattr(s, "split_copies", True):
        return "count"
    m = getattr(s, "copies_mode", "sheets")
    return m if m in COPIES_MODES else "sheets"


def clean_ov(d) -> dict:
    """Nur erlaubte Abweichungen (unbekannte Schlüssel fallen weg)."""
    return {k: v for k, v in (d or {}).items() if k in OV_KEYS} if isinstance(d, dict) else {}


def eff(s, it):
    """Einstellungen für diesen Plan: die des Auftrags plus seine Abweichungen."""
    ov = dict(getattr(it, "ov", None) or {})
    if getattr(it, "frame", "") and "frame" not in ov:
        ov["frame"] = it.frame
    return dataclasses.replace(s, **ov) if ov else s


def factor(area, s) -> float:
    """Skalierungsfaktor: Prozent oder kurze/lange Kante auf ein Maß (mm, ohne Überfüller)."""
    mode = getattr(s, "scale_mode", "pct")
    if mode in ("short", "long") and s.scale_mm > 0 and area is not None:
        edge = min(area.w_mm, area.h_mm) if mode == "short" else max(area.w_mm, area.h_mm)
        if edge > 0.1:
            return max(0.01, s.scale_mm / edge)
    return max(1.0, s.scale_pct) / 100.0


def scale_text(s) -> str:
    mode = getattr(s, "scale_mode", "pct")
    if mode == "short" and s.scale_mm > 0:
        return tr("kurze Kante {0} mm").format(mm_text(s.scale_mm))
    if mode == "long" and s.scale_mm > 0:
        return tr("lange Kante {0} mm").format(mm_text(s.scale_mm))
    return f"{mm_text(s.scale_pct)} %"
OVERWIDTH = ("none", "crop", "tile")


def defaults_for(kind: str) -> dict:
    """Standardwerte je Art: Poster = Qualitätsdruck, nebeneinander, Überbreite abschneiden, keine Planpapier-Wahl."""
    if kind == "poster":
        return {"kind": "poster", "nest": False, "overwidth": "crop", "weights": [], "frame": "none",
                "align": "center"}
    return {"kind": "plan"}


# --------------------------------------------------------------------------- #
# Rahmen / Druckbereich
# --------------------------------------------------------------------------- #
@dataclass
class Area:
    rect: tuple                       # (x0, y0, x1, y1) in pt, Koordinaten der angezeigten Seite (darf darüber hinaus)
    kind: str                         # frame | margin | page | empty
    note: str = ""

    @property
    def w_mm(self) -> float:
        return (self.rect[2] - self.rect[0]) / MM

    @property
    def h_mm(self) -> float:
        return (self.rect[3] - self.rect[1]) / MM

    def to_dict(self) -> dict:
        return {"rect_pt": [round(v, 2) for v in self.rect], "kind": self.kind, "w_mm": round(self.w_mm, 1),
                "h_mm": round(self.h_mm, 1), "note": self.note}


def num(v: float, digits: int = 2) -> str:
    """Zahl in der Schreibweise der Oberflächensprache (Komma bzw. Punkt)."""
    from . import l10n, measure
    return measure.fmt(float(v), l10n.current(), digits)


def mm_text(v: float) -> str:
    """594 -> „594“, 599.6 -> „599,6“, 0.1 -> „0,1“."""
    for d in (0, 1, 2):
        if abs(v - round(v, d)) < 0.5 * 10 ** -(d + 1):
            return num(v, d)
    return num(v, 2)


KIND_TEXT = {"frame": "Zwei Außenlinien – auf die äußere beschnitten", "margin": "Inhalt + Rand",
             "page": "Seite unverändert", "empty": "Leere Seite"}


def _render_gray(page, scale: float, crop=(0, 0, 0, 0)):
    import numpy as np
    bm = page.render(scale=scale, grayscale=True, no_smoothpath=True, may_draw_forms=True, crop=crop)
    a = bm.to_numpy()
    if a.ndim == 3:
        a = a[..., :3].min(axis=2) if a.shape[2] >= 3 else a[..., 0]
    return np.asarray(a)


def _runs(flags) -> list:
    """[(start, end)] zusammenhängender True-Bereiche (end inklusive)."""
    out, start = [], None
    for i, f in enumerate(flags):
        if f and start is None:
            start = i
        elif not f and start is not None:
            out.append((start, i - 1))
            start = None
    if start is not None:
        out.append((start, len(flags) - 1))
    return out


INK = 230
LONG = 0.6                    # Linie: mindestens 60 % der Breite/Höhe
MAX_GAP_MM = 60.0             # Abstand äußere -> innere Rahmenlinie höchstens


def _frames(ink, px_mm: float):
    """Grob: äußerer und innerer Rahmen in Pixeln {"outer": (t, b, l, r) Linien, "inner": …} oder None-Teile."""
    import numpy as np
    H, W = ink.shape
    ys, xs = np.nonzero(ink)
    if len(ys) == 0:
        return None, None, None
    y0, y1, x0, x1 = int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max())
    bbox = (y0, y1, x0, x1)
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    rows = _runs((ink[:, x0:x1 + 1].sum(axis=1) / bw) >= LONG)
    cols = _runs((ink[y0:y1 + 1, :].sum(axis=0) / bh) >= LONG)
    if len(rows) < 2 or len(cols) < 2:
        return bbox, None, None
    top, bot, lef, rig = rows[0], rows[-1], cols[0], cols[-1]

    def spans(r0, r1, c0, c1, horizontal, frac=0.9):
        seg = ink[r0:r1 + 1, c0:c1 + 1]
        cov = seg.any(axis=0).mean() if horizontal else seg.any(axis=1).mean()
        return cov >= frac
    # äußerer Rahmen: alle vier Linien durchgehend zwischen den anderen
    if not (spans(top[0], top[1], lef[0], rig[1], True) and spans(bot[0], bot[1], lef[0], rig[1], True)
            and spans(top[0], bot[1], lef[0], lef[1], False) and spans(top[0], bot[1], rig[0], rig[1], False)):
        return bbox, None, None
    outer = (top, bot, lef, rig)
    gap = MAX_GAP_MM / px_mm
    it = [r for r in rows[1:-1] if top[1] < r[0] <= top[1] + gap]
    ib = [r for r in rows[1:-1] if bot[0] - gap <= r[1] < bot[0]]
    il = [c for c in cols[1:-1] if lef[1] < c[0] <= lef[1] + gap]
    ir = [c for c in cols[1:-1] if rig[0] - gap <= c[1] < rig[0]]
    if not (it and ib and il and ir):
        return bbox, outer, None
    t2, b2, l2, r2 = it[0], ib[-1], il[0], ir[-1]
    if not (spans(t2[0], t2[1], l2[0], r2[1], True, 0.85) and spans(b2[0], b2[1], l2[0], r2[1], True, 0.85)
            and spans(t2[0], b2[1], l2[0], l2[1], False, 0.85) and spans(t2[0], b2[1], r2[0], r2[1], False, 0.85)):
        return bbox, outer, None
    return bbox, outer, (t2, b2, l2, r2)


def _refine(page, W: float, H: float, side: str, approx: float, lo: float, hi: float) -> float | None:
    """Innenkante der äußeren Linie fein (300 dpi) – side t/b/l/r, approx = grobe Lage in pt (Seitenkoordinaten),
        lo..hi = Bereich entlang der Linie in pt. -> Koordinate in pt oder None."""
    import numpy as np
    band = 3.0 * MM
    scale = 300 / 72
    if side in ("t", "b"):
        y0, y1 = max(0.0, approx - band), min(H, approx + band)
        crop = (lo, y0, W - hi, H - y1)          # links, unten, rechts, oben abschneiden
    else:
        x0, x1 = max(0.0, approx - band), min(W, approx + band)
        crop = (x0, lo, W - x1, H - hi)
    if min(crop) < 0 or crop[0] + crop[2] >= W or crop[1] + crop[3] >= H:
        return None
    a = _render_gray(page, scale, crop)
    ink = a < INK
    if side in ("t", "b"):
        runs = _runs(ink.mean(axis=1) >= 0.5)
        if not runs:
            return None
        # Zeile 0 = oben (y1)
        if side == "t":
            r = runs[0]                                       # oberste Linie im Band -> Innenkante unten
            return y1 - (r[1] + 1) / scale
        r = runs[-1]
        return y1 - r[0] / scale                              # unterste Linie -> Innenkante oben
    runs = _runs(ink.mean(axis=0) >= 0.5)
    if not runs:
        return None
    if side == "l":
        r = runs[0]
        return x0 + (r[1] + 1) / scale
    r = runs[-1]
    return x0 + r[0] / scale


def detect(doc, i: int, mode: str = "auto", margin_mm: float = 5.0) -> Area:
    """Druckbereich einer Planseite."""
    W, H = doc.get_page_size(i)
    if mode == "none":
        return Area((0.0, 0.0, W, H), "page")
    page = doc[i]
    try:
        longest_in = max(W, H) / 72
        dpi = max(20.0, min(50.0, 3200 / longest_in))
        scale = dpi / 72
        a = _render_gray(page, scale)
        ink = a < INK
        px_mm = 25.4 / dpi
        bbox, outer, inner = _frames(ink, px_mm)
        if bbox is None:
            return Area((0.0, 0.0, W, H), "empty", tr("Leere Seite"))
        h_px, w_px = ink.shape

        def ypt(row):                                   # Pixelzeile (Oberkante) -> pt
            return H - row * H / h_px

        def xpt(col):
            return col * W / w_px
        note = ""
        if mode in ("auto", "frame") and inner is not None:
            (t, b, l, r) = outer
            x0, x1 = xpt(l[1] + 1), xpt(r[0])
            y1, y0 = ypt(t[1] + 1), ypt(b[0])
            span_x = (x0 + (x1 - x0) * 0.3, x1 - (x1 - x0) * 0.3)
            span_y = (y0 + (y1 - y0) * 0.3, y1 - (y1 - y0) * 0.3)
            ft = _refine(page, W, H, "t", (ypt(t[0]) + ypt(t[1] + 1)) / 2, span_x[0], span_x[1])
            fb = _refine(page, W, H, "b", (ypt(b[0]) + ypt(b[1] + 1)) / 2, span_x[0], span_x[1])
            fl = _refine(page, W, H, "l", (xpt(l[0]) + xpt(l[1] + 1)) / 2, span_y[0], span_y[1])
            fr = _refine(page, W, H, "r", (xpt(r[0]) + xpt(r[1] + 1)) / 2, span_y[0], span_y[1])
            # minimal nach innen, damit von der Linie nichts stehen bleibt
            e = 0.15 * MM
            rect = ((fl if fl is not None else x0) + e, (fb if fb is not None else y0) + e,
                    (fr if fr is not None else x1) - e, (ft if ft is not None else y1) - e)
            return Area(rect, "frame")
        if mode == "frame":
            note = tr("Keine zwei Außenlinien gefunden – Inhalt + Rand")
        y0p, y1p, x0p, x1p = bbox
        m = margin_mm * MM
        rect = (xpt(x0p) - m, ypt(y1p + 1) - m, xpt(x1p + 1) + m, ypt(y0p) + m)
        return Area(rect, "margin", note)
    finally:
        page.close()


# --------------------------------------------------------------------------- #
# Rollen und Laufmeter
# --------------------------------------------------------------------------- #
@dataclass
class Fit:
    roll: int                 # Index in der Rollenliste
    width_mm: float           # Rollenbreite
    across: float             # quer zur Rolle (mm)
    along: float              # Länge auf der Rolle (mm)
    rotated: bool             # gegenüber der Seite um 90° gedreht


MARKS_MM = (layout.MARK_OFFSET + layout.MARK_LEN) / MM + 1.0


def margins_mm(s: PlanSettings) -> tuple:
    """Zusatz je Seite (links, unten, rechts, oben) in mm, wie die Seite steht: Saum ersetzt dort den
        Überfüller; dazu Platz für Schnitt-/Passermarken."""
    marks = MARKS_MM if (s.crop_marks or s.printcut_marks) else 0.0
    out = []
    for side in "lbrt":
        e = max(0.0, s.hem_mm) if (s.hem_mm > 0 and side in s.hem_sides) else max(0.0, s.bleed_mm)
        out.append(e + marks)
    return tuple(out)


def extra_mm(s: PlanSettings) -> float:
    """Größter Zusatz je Seite (Überfüller/Saum + Marken)."""
    return max(margins_mm(s))


def finished_size(area: Area, s: PlanSettings) -> tuple:
    f = factor(area, s)
    l, b, r, t = margins_mm(s)
    return area.w_mm * f + l + r, area.h_mm * f + b + t


def choose(w: float, h: float, rolls: list, rotate: str = "auto") -> Fit | None:
    """Rolle und Lage für einen Plan w × h (mm, wie die Seite steht)."""
    best = None
    for i, r in enumerate(rolls):
        if getattr(r, "empty", False):
            continue
        for rot in (False, True):
            across, along = (h, w) if rot else (w, h)
            if rotate == "keep" and rot:
                continue
            if rotate == "short" and across > along + 1e-6:
                continue
            if rotate == "long" and across < along - 1e-6:
                continue
            if across > r.width_mm + TOL_MM:
                continue
            key = (round(along, 1), r.width_mm, rot)
            if best is None or key < best[0]:
                best = (key, Fit(i, r.width_mm, across, along, rot))
    if best is None and rotate in ("short", "long"):
        return choose(w, h, rolls, "auto")             # passt nur andersherum
    return best[1] if best else None


def eligible(rolls: list, weights) -> tuple:
    """Rollen mit Planpapier (Grammatur passt oder unbekannt). -> (Rollen, Hinweis)."""
    ws = {int(w) for w in (weights or []) if w}
    if not ws or not rolls:
        return list(rolls), ""
    ok = [r for r in rolls if not r.weight or r.weight in ws]
    if ok:
        return ok, ""
    return list(rolls), tr("Keine Rolle mit {0} g/m² geladen – alle Rollen werden verwendet.").format(
        " / ".join(str(w) for w in sorted(ws)))


@dataclass
class Item:
    page: int                 # Seite im Dokument
    qty: int = 1              # Menge je Satz
    area: Area | None = None
    fit: Fit | None = None
    size: tuple = (0.0, 0.0)  # fertige Größe (mm) wie die Seite steht
    hairlines: int = 0
    source: str = ""          # Datei
    doc: object = None        # pdfium-Dokument (nicht im Protokoll)
    frame: str = ""           # Rahmen je Plan ("" = wie eingestellt)
    ov: dict = field(default_factory=dict)   # Abweichungen von den Auftrags-Einstellungen (OV_KEYS)

    @property
    def label(self) -> str:
        return f"{os.path.basename(self.source) or tr('Dokument')} · " + tr("S. {0}").format(self.page + 1)


def place(items: list, rolls: list, s: PlanSettings) -> None:
    """Fertige Größe und Rolle für jeden Plan (area muss gesetzt sein)."""
    for it in items:
        if it.area is None:
            it.fit = None
            continue
        es = eff(s, it)
        it.size = finished_size(it.area, es)
        it.fit = choose(it.size[0], it.size[1], rolls, es.rotate)


def run_lengths(items: list, rolls: list, copies: int) -> list:
    """Laufmeter je Rolle: [{"roll", "width_mm", "label", "plans", "single_m", "total_m"}] (nur Plangrößen)."""
    out = {}
    for it in items:
        if it.fit is None:
            continue
        d = out.setdefault(it.fit.roll, {"roll": it.fit.roll, "width_mm": it.fit.width_mm,
                                         "label": rolls[it.fit.roll].label(), "plans": 0, "single_m": 0.0})
        d["plans"] += max(0, it.qty)
        d["single_m"] += it.fit.along * max(0, it.qty) / 1000.0
    res = []
    for k in sorted(out, key=lambda k: (out[k]["width_mm"], k)):
        d = out[k]
        d["single_m"] = round(d["single_m"], 3)
        d["total_m"] = round(d["single_m"] * max(1, copies), 3)
        rem = rolls[k].remaining_m
        d["short"] = rem is not None and d["total_m"] > rem
        res.append(d)
    return res


def job_order(items: list, copies: int, collate: bool, order: str, rolls: list | None = None) -> list:
    """[(Item, Anzahl)] in Druckreihenfolge. Unsortiert: jeder Plan alle Exemplare hintereinander."""
    seq = [it for it in items if it.fit is not None and it.qty > 0]
    if order == "roll":
        seq.sort(key=lambda it: (it.fit.width_mm, it.fit.roll))   # stabil: innerhalb der Rolle wie in der Liste
    copies = max(1, int(copies))
    if not collate:
        return [(it, it.qty * copies) for it in seq]
    return [(it, it.qty) for _c in range(copies) for it in seq]


# --------------------------------------------------------------------------- #
# Haarlinien
# --------------------------------------------------------------------------- #
def _walk_paths(container, count_fn, get_fn, matrix, out: list, depth: int = 0):
    import ctypes
    import pypdfium2.raw as r
    n = count_fn(container)
    for k in range(n):
        obj = get_fn(container, k)
        m = r.FS_MATRIX()
        if r.FPDFPageObj_GetMatrix(obj, ctypes.byref(m)):
            own = (m.a, m.b, m.c, m.d, m.e, m.f)
        else:
            own = (1, 0, 0, 1, 0, 0)
        t = r.FPDFPageObj_GetType(obj)
        if t == r.FPDF_PAGEOBJ_FORM and depth < 8:
            _walk_paths(obj, r.FPDFFormObj_CountObjects, r.FPDFFormObj_GetObject, layout._mul(own, matrix), out,
                        depth + 1)
        elif t == r.FPDF_PAGEOBJ_PATH:
            fm, st = ctypes.c_int(0), ctypes.c_int(0)
            if not r.FPDFPath_GetDrawMode(obj, ctypes.byref(fm), ctypes.byref(st)) or not st.value:
                continue
            w = ctypes.c_float(0)
            if not r.FPDFPageObj_GetStrokeWidth(obj, ctypes.byref(w)):
                continue
            # die Matrix des Pfads (CTM) wirkt auch auf die Strichstärke, dazu die umgebenden Formulare
            a, b, c, d = layout._mul(own, matrix)[:4]
            f = abs(a * d - b * c) ** 0.5 or 1.0
            out.append((obj, w.value, f, matrix if depth else None))


def hairlines(doc, i: int, min_mm: float = 0.1, scale_pct: float = 100.0) -> int:
    """Anzahl gezeichneter Linien dünner als min_mm (Strichstärke 0 = dünnste Gerätelinie zählt mit)."""
    import pypdfium2.raw as r
    page = doc[i]
    try:
        found = []
        _walk_paths(page.raw, r.FPDFPage_CountObjects, r.FPDFPage_GetObject, (1, 0, 0, 1, 0, 0), found)
        lim = min_mm * MM
        f2 = max(1.0, scale_pct) / 100.0
        return sum(1 for _o, w, f, _m in found if w * f * f2 < lim - 1e-6)
    finally:
        page.close()


def hairline_boxes(doc, i: int, min_mm: float = 0.1, max_objs: int = 200000) -> tuple:
    """(Anzahl, [Bereich (x0, y0, x1, y1) pt]) der Linien dünner als min_mm – für den Preflight."""
    import ctypes
    import pypdfium2.raw as r
    page = doc[i]
    try:
        if r.FPDFPage_CountObjects(page.raw) > max_objs:
            return 0, []
        found = []
        _walk_paths(page.raw, r.FPDFPage_CountObjects, r.FPDFPage_GetObject, (1, 0, 0, 1, 0, 0), found)
        lim = min_mm * MM
        n, boxes = 0, []
        for obj, w, f, parent in found:
            if w * f >= lim - 1e-6:
                continue
            n += 1
            l, b, rr, t = (ctypes.c_float() for _ in range(4))
            if not r.FPDFPageObj_GetBounds(obj, ctypes.byref(l), ctypes.byref(b), ctypes.byref(rr), ctypes.byref(t)):
                continue
            box = (l.value, b.value, rr.value, t.value)
            if parent is not None:
                pts = [(x * parent[0] + y * parent[2] + parent[4], x * parent[1] + y * parent[3] + parent[5])
                       for x in (box[0], box[2]) for y in (box[1], box[3])]
                box = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
            boxes.append(box)
        return n, boxes
    finally:
        page.close()


def fix_hairlines(doc, pages, min_mm: float = 0.1, scale_pct: float = 100.0):
    """Kopie des Dokuments, in der Linien dünner als min_mm auf min_mm angehoben sind. -> (Kopie, Anzahl)."""
    import io
    import pypdfium2 as pdfium
    import pypdfium2.raw as r
    buf = io.BytesIO()
    doc.save(buf)
    cp = pdfium.PdfDocument(buf.getvalue())
    n = 0
    lim = min_mm * MM / (max(1.0, scale_pct) / 100.0)
    for i in pages:
        page = cp[i]
        found = []
        _walk_paths(page.raw, r.FPDFPage_CountObjects, r.FPDFPage_GetObject, (1, 0, 0, 1, 0, 0), found)
        changed = False
        for obj, w, f, _m in found:
            if w * f < lim - 1e-6:
                r.FPDFPageObj_SetStrokeWidth(obj, lim / f)
                n += 1
                changed = True
        if changed:
            r.FPDFPage_GenerateContent(page.raw)
        page.close()
    return cp, n


# --------------------------------------------------------------------------- #
# Stücke und Druckseiten
# --------------------------------------------------------------------------- #
@dataclass
class Piece:
    """Ein Stück auf der Rolle: ein Plan/Poster oder eine Bahn davon (Überbreite)."""
    item: Item
    rect: tuple               # Ausschnitt der Seite (pt) – der Druckbereich oder eine Bahn davon
    across: float             # mm quer zur Rolle (inkl. Überfüller/Saum/Marken)
    along: float              # mm Länge auf der Rolle
    rotated: bool
    roll: int
    width_mm: float
    tile: int = 0
    tiles: int = 1
    clipped: bool = False     # breiter als die Rolle – abgeschnitten

    @property
    def label(self) -> str:
        t = self.item.label
        if self.tiles > 1:
            t += " · " + tr("Bahn {0}/{1}").format(self.tile + 1, self.tiles)
        return t


@dataclass
class Run:
    """Eine Druckseite = ein Auftrag: ein Stück oder mehrere nebeneinander."""
    roll: int
    width_mm: float
    across: float             # Papierbreite (mm)
    along: float              # Papierlänge (mm)
    pieces: list              # [(Piece, x_mm, y_mm)] – Lage auf der Seite (links unten)
    copies: int = 1

    @property
    def label(self) -> str:
        if not self.pieces:
            return ""
        first = self.pieces[0][0].label
        n = len(self.pieces)
        return first if n == 1 else first + " " + tr("+ {0} weitere").format(n - 1)


def roll_key(r) -> str:
    """Kennung einer Rolle für die feste Auswahl: Zufuhr im Treiber, sonst Name am Gerät, sonst Breite."""
    return r.slot or r.device or r.name or f"{round(r.width_mm, 1)}"


def find_roll(rolls: list, key: str):
    """Index der Rolle mit dieser Kennung (oder None)."""
    if not key:
        return None
    live = [(k, r) for k, r in enumerate(rolls) if not getattr(r, "empty", False)]
    for k, r in live:
        if roll_key(r) == key:
            return k
    low = str(key).strip().lower()
    for k, r in live:                                    # Zufuhr, Name am Gerät, Anzeigename
        if low in {x.lower() for x in (r.slot, r.device, r.name) if x}:
            return k
    try:
        w = float(str(key).replace(",", ".").lower().removesuffix("mm").strip())
    except ValueError:
        return None
    for k, r in live:                                    # Breite
        if abs(r.width_mm - w) <= TOL_MM:
            return k
    return None


def _words(t: str) -> set:
    return {w for w in re.findall(r"[a-zäöüß]{3,}", (t or "").lower())}


def match_material(rolls: list, mat: dict) -> list:
    """Rollen, die zum Material passen: Grammatur gleich, sonst Medienname/Material-Name ähnlich. [] = keine."""
    if mat.get("device"):                              # vom Gerät: genau die Rolle(n) mit diesem Medium
        hit = [r for r in rolls if not getattr(r, "empty", False) and (r.media or r.name) == mat["device_media"]
               and (not mat["weight"] or r.weight == mat["weight"])]
        if hit:
            return hit
    w = int(mat.get("weight") or 0)
    by_w = [r for r in rolls if w and r.weight == w and not getattr(r, "empty", False)]
    if by_w:
        return by_w
    names = _words(mat.get("name", "")) | _words(mat.get("media", ""))
    if not names:
        return []
    return [r for r in rolls if not getattr(r, "empty", False) and names & _words(f"{r.media} {r.name}")]


def eligible_for(rolls: list, s: PlanSettings) -> tuple:
    """Rollen für diesen Auftrag. Feste Rolle geht vor; dann Material (Grammatur oder Name); Plan:
        Planpapier-Grammatur. -> (Rollen, Hinweis)."""
    if s.roll_pick:
        k = find_roll(rolls, s.roll_pick)
        if k is not None:
            return [rolls[k]], ""
        note = tr("Gewählte Rolle ist nicht geladen – Rolle wird automatisch gewählt.")
    else:
        note = ""
    mat = material_of(s)
    if mat is not None:
        hit = match_material(rolls, mat)
        if hit:
            return hit, note
        if mat.get("weight"):
            use, n2 = eligible(rolls, [int(mat["weight"])])
            return use, " ".join(x for x in (note, n2) if x)
    if s.kind == "plan":
        use, n2 = eligible(rolls, s.weights)
        return use, " ".join(x for x in (note, n2) if x)
    return list(rolls), note


DEV_PREFIX = "dev:"                     # Material, wie es der Drucker meldet: "dev:<g/m²>:<Medienname>"


def device_material_id(roll) -> str:
    return f"{DEV_PREFIX}{int(roll.weight or 0)}:{roll.media or roll.name}"


def device_materials(rolls: list) -> list:
    """Materialien laut Gerät (die Medien der geladenen Rollen), ohne Doppelte: [{"id", "name", "weight", …}]."""
    out, seen = [], set()
    for r in rolls:
        if getattr(r, "empty", False) or not (r.media or r.weight):
            continue
        mid = device_material_id(r)
        if mid in seen:
            continue
        seen.add(mid)
        out.append(_dev_mat(mid))
    return out


def _dev_mat(mid: str) -> dict:
    w, _sep, name = mid[len(DEV_PREFIX):].partition(":")
    return {"id": mid, "name": name or tr("Gerät"), "weight": int(w) if w.isdigit() else 0, "media": "",
            "category": "", "printer": "", "device": True, "device_media": name}


def material_of(s: PlanSettings):
    if not s.material:
        return None
    if s.material.startswith(DEV_PREFIX):
        return _dev_mat(s.material)
    try:
        from . import printmat
        return printmat.find(s.material, s.printer)
    except Exception:
        return None


def _narrowest(rolls: list, across: float, idx: list):
    best = None
    for k, r in zip(idx, rolls):
        if getattr(r, "empty", False) or across > r.width_mm + TOL_MM:
            continue
        if best is None or r.width_mm < best[1]:
            best = (k, r.width_mm)
    return best


def nest_fit(w: float, h: float, rolls: list, use: list, count: int, gap: float):
    """Nebeneinander: Rolle und Lage mit dem wenigsten Papier (Rollenbreite × Länge) für count Stücke."""
    best = None
    for r in use:
        k = rolls.index(r)
        for rot in (False, True):
            across, along = (h, w) if rot else (w, h)
            if across > r.width_mm + TOL_MM:
                continue
            per_row = max(1, int((r.width_mm + gap + TOL_MM) // (across + gap)))
            rows = -(-count // per_row)
            length = rows * along + (rows - 1) * gap
            key = (round(r.width_mm * length / 1e6, 4), round(length, 1), rot)
            if best is None or key < best[0]:
                best = (key, Fit(k, r.width_mm, across, along, rot))
    return best[1] if best else None


def pieces_for(it: Item, rolls: list, s: PlanSettings, use: list | None = None, count: int = 1) -> list:
    """Stücke eines Plans/Posters. Passt er auf eine Rolle: eins. Sonst je nach Überbreite: abschneiden oder in
        Bahnen mit Überlappung teilen (nur auf den passenden Rollen)."""
    if it.area is None:
        return []
    s = eff(s, it)
    if it.ov.get("roll_pick") or it.ov.get("material"):     # eigene Rolle/eigenes Material: eigene Auswahl
        use = eligible_for(rolls, s)[0]
    use = [r for r in (use if use is not None else rolls) if not getattr(r, "empty", False)]
    if it.fit is not None and s.nest and s.rotate == "auto" and count > 1:
        nf = nest_fit(it.size[0], it.size[1], rolls, use, count, max(0.0, s.gap_mm))
        if nf is not None:
            return [Piece(it, it.area.rect, nf.across, nf.along, nf.rotated, nf.roll, nf.width_mm)]
    if it.fit is not None:
        return [Piece(it, it.area.rect, it.fit.across, it.fit.along, it.fit.rotated, it.fit.roll, it.fit.width_mm)]
    if s.overwidth not in ("crop", "tile") or not use:
        return []
    idx = [rolls.index(r) for r in use]
    widest = max(r.width_mm for r in use)
    f = factor(it.area, s)
    l, b, r_, t = margins_mm(s)
    x0, y0, x1, y1 = it.area.rect
    cw, ch = it.area.w_mm * f, it.area.h_mm * f
    best = None
    for rot in (False, True):
        if rot and s.rotate == "keep":
            continue
        # quer zur Rolle: ungedreht die Breite der Seite, gedreht die Höhe
        c_across, m_across = (ch, b + t) if rot else (cw, l + r_)
        c_along, m_along = (cw, l + r_) if rot else (ch, b + t)
        avail = widest - m_across
        if avail <= 10:
            continue
        if s.overwidth == "crop":
            key = (c_across - avail, c_along)              # wenig abschneiden, dann kurz
        else:
            n = max(1, -(-(c_across - s.overlap_mm) // max(1.0, avail - s.overlap_mm)))
            key = (n, c_along)
        if best is None or key < best[0]:
            best = (key, rot, c_across, m_across, c_along, m_along, avail)
    if best is None:
        return []
    _k, rot, c_across, m_across, c_along, m_along, avail = best
    along = c_along + m_along

    def sub(a0, a1):
        """Bereich a0..a1 (mm, quer zur Rolle, ab Anfang) als Ausschnitt der Seite (pt)."""
        if rot:                                        # quer = Höhe der Seite (gedreht: oben beginnt)
            return (x0, y1 - a1 * MM / f, x1, y1 - a0 * MM / f)
        return (x0 + a0 * MM / f, y0, x0 + a1 * MM / f, y1)
    if s.overwidth == "crop":
        w = min(c_across, avail)
        k = _narrowest(use, w + m_across, idx)
        return [Piece(it, sub(0, w), w + m_across, along, rot, k[0], k[1], clipped=c_across > avail + TOL_MM)]
    ov = max(0.0, s.overlap_mm)
    n = int(max(1, -(-(c_across - ov) // max(1.0, avail - ov))))
    sw = (c_across + (n - 1) * ov) / n
    out = []
    for j in range(n):
        a0 = j * (sw - ov)
        k = _narrowest(use, sw + m_across, idx)
        out.append(Piece(it, sub(a0, a0 + sw), sw + m_across, along, rot, k[0], k[1], tile=j, tiles=n))
    return out


def _shelf(pieces: list, width: float, gap: float, max_len: float, roll: int) -> list:
    """Stücke nebeneinander (Regal-Verfahren, höchste zuerst) -> Druckseiten (Run) auf einer Rolle.
        Jede Reihe ist eine eigene Druckseite: Der Drucker schneidet nach jeder Reihe ab (nie mehrere Reihen bzw.
        Exemplare untereinander auf einem Blatt). Gleiche Reihen werden zu einer Seite mit Kopienzahl zusammengefasst
        – „Einzeln abschneiden“ macht daraus wieder je Exemplar einen Auftrag. max_len: nicht mehr verwendet."""
    pcs = sorted(pieces, key=lambda p: (-p.along, -p.across))
    rows = []                                        # [Höhe, belegte Breite, [(Stück, x)]]
    for p in pcs:
        for row in rows:
            if row[1] + gap + p.across <= width + TOL_MM and p.along <= row[0] + TOL_MM:
                row[2].append((p, row[1] + gap))
                row[1] += gap + p.across
                break
        else:
            rows.append([p.along, p.across, [(p, 0.0)]])
    runs, keys = [], []
    for h, w, items in rows:
        key = tuple((id(p.item), p.item.page, p.tile, round(x, 1), round(p.along, 1)) for p, x in items)
        if runs and keys[-1] == key:                 # gleiche Reihe wie davor: nur Kopienzahl erhöhen
            runs[-1].copies += 1
            continue
        placed = [(p, x, h - p.along) for p, x in items]
        runs.append(Run(roll, pieces[0].width_mm, w, h, placed))
        keys.append(key)
    return runs


def build_runs(items: list, rolls: list, s: PlanSettings, copies: int | None = None) -> list:
    """Druckseiten in Druckreihenfolge. Ohne Nebeneinander: ein Stück je Seite (unsortiert: alle Exemplare
        eines Stücks hintereinander, sortiert: Satz für Satz, optional nach Rollenbreite). Mit Nebeneinander:
        alle Exemplare zusammen auf die Rollen verteilt, je Reihe eine Seite (abgeschnitten)."""
    return [_aligned(r, s) for r in _build_runs(items, rolls, s, copies)]


def _aligned(run: Run, s: PlanSettings) -> Run:
    """Seite auf die volle Rollenbreite, Inhalt an den Rand (links/rechts) oder in die Mitte. So setzt der
        Drucker nichts selbst: am Rand bleibt nur ein Längsschnitt, mittig blendet er nichts aus."""
    if len(run.pieces) == 1:                          # ein Stück: Lage wie für diesen Plan eingestellt
        s = eff(s, run.pieces[0][0].item)
    if s.align not in ALIGNS or run.width_mm <= 0 or run.across >= run.width_mm - 0.05:
        return run
    free = run.width_mm - run.across
    dx = {"left": 0.0, "right": free, "center": free / 2.0}[s.align]
    return Run(run.roll, run.width_mm, run.width_mm, run.along, [(p, x + dx, y) for p, x, y in run.pieces],
               run.copies)


def _build_runs(items: list, rolls: list, s: PlanSettings, copies: int | None = None) -> list:
    copies = max(1, int(s.copies if copies is None else copies))
    use, _n = eligible_for(rolls, s)
    seq = []
    for it in items:
        if it.qty > 0:
            seq += [(p, it.qty) for p in pieces_for(it, rolls, s, use, it.qty * copies)]
    if not s.nest:
        if s.order == "roll":
            seq.sort(key=lambda x: (x[0].width_mm, x[0].roll))
        one = [(p, q) for p, q in seq]
        if not s.collate:
            return [Run(p.roll, p.width_mm, p.across, p.along, [(p, 0.0, 0.0)], q * copies) for p, q in one]
        return [Run(p.roll, p.width_mm, p.across, p.along, [(p, 0.0, 0.0)], q) for _c in range(copies) for p, q in one]
    by_roll = {}
    for p, q in seq:
        by_roll.setdefault(p.roll, []).extend([p] * (q * copies))
    runs = []
    for k in sorted(by_roll, key=lambda k: (rolls[k].width_mm, k)):
        runs += _shelf(by_roll[k], rolls[k].width_mm, max(0.0, s.gap_mm), max(0.5, s.max_page_m), k)
    return runs


def lengths(items: list, rolls: list, s: PlanSettings) -> list:
    """Laufmeter je Rolle für einen Satz und für alle Exemplare (Nebeneinander: jeweils neu verteilt)."""
    def per_roll(runs):
        d = {}
        for run in runs:
            e = d.setdefault(run.roll, [0.0, 0])
            e[0] += run.along * run.copies / 1000.0
            e[1] += len(run.pieces) * run.copies
        return d
    one = per_roll(build_runs(items, rolls, s, 1))
    allc = per_roll(build_runs(items, rolls, s)) if max(1, int(s.copies)) > 1 else one
    res = []
    for k in sorted(set(one) | set(allc), key=lambda k: (rolls[k].width_mm, k)):
        single, plans = one.get(k, (0.0, 0))
        total = allc.get(k, (0.0, 0))[0]
        rem = rolls[k].remaining_m
        res.append({"roll": k, "width_mm": rolls[k].width_mm, "label": rolls[k].label(), "plans": plans,
                    "single_m": round(single, 3), "total_m": round(total, 3),
                    "short": rem is not None and total > rem})
    return res


# --------------------------------------------------------------------------- #
# Zeichnen
# --------------------------------------------------------------------------- #
def _hex_rgb(c: str) -> tuple:
    c = str(c or "#ffffff").lstrip("#")
    try:
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    except (ValueError, IndexError):
        return 255, 255, 255


def _rect(page, x, y, w, h, rgb, m):
    import pypdfium2.raw as r
    ro = r.FPDFPageObj_CreateNewRect(x, y, w, h)
    r.FPDFPageObj_SetFillColor(ro, rgb[0], rgb[1], rgb[2], 255)
    r.FPDFPath_SetDrawMode(ro, r.FPDF_FILLMODE_WINDING, False)
    r.FPDFPageObj_Transform(ro, *m)
    r.FPDFPage_InsertObject(page.raw, ro)


def _line(page, x0, y0, x1, y1, m, width=0.25, gray=0, dash=None):
    import ctypes
    import pypdfium2.raw as r
    o = r.FPDFPageObj_CreateNewPath(x0, y0)
    r.FPDFPath_LineTo(o, x1, y1)
    r.FPDFPageObj_SetStrokeColor(o, gray, gray, gray, 255)
    r.FPDFPageObj_SetStrokeWidth(o, width)
    if dash:
        arr = (ctypes.c_float * len(dash))(*dash)
        r.FPDFPageObj_SetDashArray(o, arr, len(dash), 0.0)
    r.FPDFPath_SetDrawMode(o, r.FPDF_FILLMODE_NONE, True)
    r.FPDFPageObj_Transform(o, *m)
    r.FPDFPage_InsertObject(page.raw, o)


def _circle_obj(page, cx, cy, rad, m, width=0.4, gray=90):
    import pypdfium2.raw as r
    _kind, (sx, sy), segs = layout._circle(cx, cy, rad)
    o = r.FPDFPageObj_CreateNewPath(sx, sy)
    for c1, c2, pt in segs:
        r.FPDFPath_BezierTo(o, c1[0], c1[1], c2[0], c2[1], pt[0], pt[1])
    r.FPDFPath_Close(o)
    r.FPDFPageObj_SetStrokeColor(o, gray, gray, gray, 255)
    r.FPDFPageObj_SetStrokeWidth(o, width)
    r.FPDFPath_SetDrawMode(o, r.FPDF_FILLMODE_NONE, True)
    r.FPDFPageObj_Transform(o, *m)
    r.FPDFPage_InsertObject(page.raw, o)


def grommet_points(w: float, h: float, inset: float, spacing: float, sides: str = "lrtb") -> list:
    """Ösen auf einem Endformat w × h (beliebige Einheit): Ecken immer, dazwischen gleichmäßig, Abstand höchstens
        spacing. -> [(x, y)] ab links unten."""
    if spacing <= 0 or w <= 2 * inset or h <= 2 * inset:
        return []
    pts = set()

    def edge(p0, p1):
        (ax, ay), (bx, by) = p0, p1
        L = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
        n = max(1, int(-(-L // spacing)))
        for k in range(n + 1):
            pts.add((round(ax + (bx - ax) * k / n, 3), round(ay + (by - ay) * k / n, 3)))
    a, b_, c, d = (inset, inset), (w - inset, inset), (w - inset, h - inset), (inset, h - inset)
    if "b" in sides:
        edge(a, b_)
    if "r" in sides:
        edge(b_, c)
    if "t" in sides:
        edge(d, c)
    if "l" in sides:
        edge(a, d)
    return sorted(pts)


def fold_positions(w: float, h: float) -> tuple:
    """Faltung nach DIN 824 (vereinfacht, Form A): senkrecht von rechts in 190-mm-Feldern, bis links 210 mm
        (inkl. 20 mm Heftrand) bleiben; waagrecht in 297-mm-Feldern von unten. -> ([x mm], [y mm])."""
    xs, x = [], w
    while x - 190.0 >= 210.0 - 1e-6:
        x -= 190.0
        xs.append(round(x, 2))
    if w > 210.0 + 1e-6 and (not xs or xs[-1] > 210.0 + 1e-6):
        xs.append(210.0)
    ys, y = [], 297.0
    while y < h - 1e-6:
        ys.append(round(y, 2))
        y += 297.0
    return sorted(set(v for v in xs if 0 < v < w)), ys


def _draw_piece(out, page, tiles, src, p: Piece, s: PlanSettings, ox: float, oy: float, cuts: list):
    """Ein Stück an (ox, oy) pt auf die Seite: Inhalt, Überfüller, Saum, Marken, Ösen, Faltmarken."""
    import pypdfium2 as pdfium
    M = pdfium.PdfMatrix
    s = eff(s, p.item)
    f = factor(p.item.area, s)
    x0, y0, x1, y1 = p.rect
    cw, ch = (x1 - x0) * f, (y1 - y0) * f
    marks = MARKS_MM * MM if (s.crop_marks or s.printcut_marks) else 0.0
    l, b, r_, t = (v * MM for v in margins_mm(s))
    hem = {k: (max(0.0, s.hem_mm) * MM if (s.hem_mm > 0 and k in s.hem_sides) else 0.0) for k in "lbrt"}
    bl, bb, br, bt = ((0.0 if hem[k] else max(0.0, s.bleed_mm) * MM) for k in "lbrt")
    PW, PH = cw + l + r_, ch + b + t
    rot = layout._rot90ccw(PH) if p.rotated else (1, 0, 0, 1, 0, 0)
    m = layout._mul(rot, layout._translate(ox, oy))
    # 1 Inhalt auf den Ausschnitt beschnitten
    t1 = tiles.new_page(cw, ch)
    o = src.page_as_xobject(p.item.page, tiles).as_pageobject()
    o.transform(M(*layout._mul(layout._translate(-x0, -y0), layout._scale(f))))
    t1.insert_obj(o)
    t1.gen_content()
    t1.close()
    k1 = len(tiles) - 1
    content, cx, cy = k1, l, b
    if s.bleed_mode == "mirror" and (bl or bb or br or bt):
        t2 = tiles.new_page(cw + bl + br, ch + bb + bt)
        for dx in ([-1] if bl else []) + [0] + ([1] if br else []):
            for dy in ([-1] if bb else []) + [0] + ([1] if bt else []):
                mm_ = (1, 0, 0, 1, 0, 0)
                if dx == -1:
                    mm_ = layout._mul(mm_, (-1, 0, 0, 1, 0, 0))
                elif dx == 1:
                    mm_ = layout._mul(mm_, (-1, 0, 0, 1, 2 * cw, 0))
                if dy == -1:
                    mm_ = layout._mul(mm_, (1, 0, 0, -1, 0, 0))
                elif dy == 1:
                    mm_ = layout._mul(mm_, (1, 0, 0, -1, 0, 2 * ch))
                xo = tiles.page_as_xobject(k1, tiles).as_pageobject()
                xo.transform(M(*layout._mul(mm_, layout._translate(bl, bb))))
                t2.insert_obj(xo)
        t2.gen_content()
        t2.close()
        content, cx, cy = len(tiles) - 1, l - bl, b - bb
    if s.bleed_mode == "color" and (bl or bb or br or bt):
        rgb = _hex_rgb(s.bleed_color)
        for (rx, ry, rw, rh) in ((l - bl, b - bb, cw + bl + br, bb), (l - bl, b + ch, cw + bl + br, bt),
                                 (l - bl, b, bl, ch), (l + cw, b, br, ch)):
            if rw > 0 and rh > 0:
                _rect(page, rx, ry, rw, rh, rgb, m)
    xo = tiles.page_as_xobject(content, out).as_pageobject()
    xo.transform(M(*layout._mul(layout._translate(cx, cy), m)))
    page.insert_obj(xo)
    # Schnittkante = Endformat + Saum
    CX0, CY0, CX1, CY1 = l - hem["l"], b - hem["b"], l + cw + hem["r"], b + ch + hem["t"]
    if s.crop_marks:
        o_ = max(bl, bb, br, bt) + layout.MARK_OFFSET
        L = layout.MARK_LEN
        for (xa, ya, xb, yb) in ((CX0, CY1 + o_, CX0, CY1 + o_ + L), (CX1, CY1 + o_, CX1, CY1 + o_ + L),
                                 (CX0, CY0 - o_, CX0, CY0 - o_ - L), (CX1, CY0 - o_, CX1, CY0 - o_ - L),
                                 (CX0 - o_, CY0, CX0 - o_ - L, CY0), (CX0 - o_, CY1, CX0 - o_ - L, CY1),
                                 (CX1 + o_, CY0, CX1 + o_ + L, CY0), (CX1 + o_, CY1, CX1 + o_ + L, CY1)):
            _line(page, xa, ya, xb, yb, m)
    if s.printcut_marks:                             # Winkel an den Ecken (Sensor-Passermarken)
        o_, L, w_ = max(bl, bb, br, bt) + 2.0 * MM, 5.0 * MM, 1.0 * MM
        for (cx_, cy_, sx, sy) in ((CX0, CY0, -1, -1), (CX1, CY0, 1, -1), (CX0, CY1, -1, 1), (CX1, CY1, 1, 1)):
            ax, ay = cx_ + sx * o_, cy_ + sy * o_
            _rect(page, min(ax, ax + sx * L), min(ay, ay + sy * w_), L, w_, (0, 0, 0), m)
            _rect(page, min(ax, ax + sx * w_), min(ay, ay + sy * L), w_, L, (0, 0, 0), m)
    for k, (xa, ya, xb, yb) in (("l", (l, b, l, b + ch)), ("r", (l + cw, b, l + cw, b + ch)),
                                ("b", (l, b, l + cw, b)), ("t", (l, b + ch, l + cw, b + ch))):
        if hem[k]:                                   # Falzlinie des Saums: gestrichelt im Saum
            dx, dy = {"l": (-1, 0), "r": (1, 0), "b": (0, -1), "t": (0, 1)}[k]
            e = 1.0 * MM
            _line(page, xa + dx * e, ya + dy * e, xb + dx * e, yb + dy * e, m, 0.3, 120, (3.0, 3.0))
    if s.grommet_spacing_mm > 0:
        rad = max(1.0, s.grommet_d_mm / 2) * MM
        for gx, gy in grommet_points(cw / MM, ch / MM, s.grommet_inset_mm, s.grommet_spacing_mm, s.grommet_sides):
            X, Y = l + gx * MM, b + gy * MM
            _circle_obj(page, X, Y, rad, m)
            _line(page, X - 1.5 * MM, Y, X + 1.5 * MM, Y, m, 0.3, 90)
            _line(page, X, Y - 1.5 * MM, X, Y + 1.5 * MM, m, 0.3, 90)
    if s.fold_marks:
        xs, ys = fold_positions(cw / MM, ch / MM)
        T = 5.0 * MM
        for x in xs:
            X = l + x * MM
            _line(page, X, b, X, b + T, m, 0.3, 0)
            _line(page, X, b + ch - T, X, b + ch, m, 0.3, 0)
        for y in ys:
            Y = b + y * MM
            _line(page, l, Y, l + T, Y, m, 0.3, 0)
            _line(page, l + cw - T, Y, l + cw, Y, m, 0.3, 0)
    if s.cut_contour:
        pts = [(X * m[0] + Y * m[2] + m[4], X * m[1] + Y * m[3] + m[5]) for X in (CX0, CX1) for Y in (CY0, CY1)]
        cuts.append((min(q[0] for q in pts), min(q[1] for q in pts), max(q[0] for q in pts), max(q[1] for q in pts)))


def make_run(run: Run, s: PlanSettings, out=None) -> tuple:
    """Druckseite eines Auftrags (Breite = quer zur Rolle). -> (pdfium-Dokument, [CutContour-Rechtecke (pt)])."""
    import pypdfium2 as pdfium
    out = out if out is not None else pdfium.PdfDocument.new()
    tiles = pdfium.PdfDocument.new()
    fixed = {}
    cuts = []
    try:
        page = out.new_page(run.across * MM, run.along * MM)
        for p, x, y in run.pieces:
            src = p.item.doc
            if s.fix_hairlines and p.item.hairlines:
                key = (id(src), p.item.page)
                if key not in fixed:
                    fixed[key], _n = fix_hairlines(src, [p.item.page], s.hairline_mm,
                                                   factor(p.item.area, eff(s, p.item)) * 100.0)
                src = fixed[key]
            _draw_piece(out, page, tiles, src, p, s, x * MM, y * MM, cuts)
        page.gen_content()
        page.close()
    finally:
        tiles.close()
        for d in fixed.values():
            d.close()
    return out, cuts


def make_page(src, i: int, area: Area, fit: Fit, s: PlanSettings, out=None):
    """Ein Plan als Druckseite (ohne CutContour) – wie früher. -> pdfium-Dokument."""
    it = Item(i, 1, area, fit, doc=src)
    p = Piece(it, area.rect, fit.across, fit.along, fit.rotated, fit.roll, fit.width_mm)
    doc, _c = make_run(Run(fit.roll, fit.width_mm, fit.across, fit.along, [(p, 0.0, 0.0)]), s, out)
    return doc


def add_cut_contour(path: str, cuts_by_page: dict, spot: str = "CutContour", width_pt: float = 0.25) -> None:
    """Rechtecke als Schneidlinie in der Sonderfarbe (Separation, 100 % Magenta, Überdrucken) einzeichnen –
        das erkennen VersaWorks, CutStudio, Summa, Graphtec … als Konturschnitt."""
    if not any(cuts_by_page.values()):
        return
    import pikepdf
    pdf = pikepdf.open(path, allow_overwriting_input=True)
    try:
        fn = pikepdf.Dictionary(FunctionType=2, Domain=[0, 1], C0=[0, 0, 0, 0], C1=[0, 1, 0, 0], N=1)
        cs = pikepdf.Array([pikepdf.Name.Separation, pikepdf.Name("/" + spot), pikepdf.Name.DeviceCMYK, fn])
        gs = pikepdf.Dictionary(Type=pikepdf.Name.ExtGState, OP=True, op=True, OPM=1)
        for i, page in enumerate(pdf.pages):
            rects = cuts_by_page.get(i) or []
            if not rects:
                continue
            res = page.obj.get("/Resources")
            if res is None:
                page.obj.Resources = res = pikepdf.Dictionary()
            for key, val in (("/ColorSpace", ("/PMCut", cs)), ("/ExtGState", ("/PMCutGS", gs))):
                if key not in res:
                    res[key] = pikepdf.Dictionary()
                res[key][val[0]] = val[1]
            ops = ["q /PMCutGS gs /PMCut CS 1 SCN", f"{width_pt:.3f} w"]
            for (a, b_, c, d) in rects:
                ops.append(f"{a:.3f} {b_:.3f} {c - a:.3f} {d - b_:.3f} re S")
            ops.append("Q")
            page.contents_add(pikepdf.Stream(pdf, ("\n" + "\n".join(ops) + "\n").encode()), prepend=False)
        pdf.save(path)
    finally:
        pdf.close()


def page_value(caps, across: float, along: float) -> str:
    """Papierwert für den Treiber: genau die Größe der Druckseite als eigenes Format (Breite quer × Länge)."""
    from . import printers
    return printers.custom_value(round(across, 1), round(along, 1))


IPP_TRIM = ("61", "60", "63", "62", "64")      # trim-after-pages, trim, -after-copies, -after-documents, -after-job
_CUT_KEY = re.compile(r"cut|trim|schneid|abschnitt|schnitt", re.I)
_CUT_SKIP = re.compile(r"contour|kontur|cutcontour|plotter.?cut", re.I)
_CUT_NO = re.compile(r"(^|\b)(none|never|off|no|not|false|aus|kein\w*|nicht|manual|manuell|disabled?)(\b|$)|^0$", re.I)
_CUT_RANK = ((re.compile(r"page|seite|sheet|blatt|each|jede", re.I), 5), (re.compile(r"auto", re.I), 4),
             (re.compile(r"(^|\b)(on|yes|true|ein|an|enabled?|1)(\b|$)", re.I), 3),
             (re.compile(r"copy|kopie|set|satz|document|dokument", re.I), 2), (re.compile(r"job|auftrag", re.I), 1))


def cut_values(caps) -> dict:
    """Treiberwerte, damit der Rollendrucker nach jeder Seite schneidet: IPP finishings trim (61 …), CUPS/PPD
        CutMedia/cupsFinishings, Herstelleroptionen mit Schneid-/Cut-Namen. {} = Drucker bietet keine Option an."""
    if caps is None:
        return {}
    out = {}
    for k, o in caps.options.items():
        if o.installable or _CUT_SKIP.search(f"{k} {o.text}"):
            continue
        vals = {c.value: c.text for c in o.choices}
        if k == "finishings" or k.lower().startswith("cupsfinishing"):
            for v in IPP_TRIM:
                if v in vals:
                    out[k] = v
                    break
            else:
                hit = [v for v, t in vals.items() if re.search(r"trim|cut|schneid", f"{v} {t}", re.I)]
                if hit:
                    out[k] = hit[0]
            continue
        if not _CUT_KEY.search(f"{k} {o.text}"):
            continue
        best, score = None, 0
        for v, t in vals.items():
            txt = f"{v} {t}"
            if _CUT_NO.search(v) or _CUT_NO.search(t):
                continue
            sc = max((r for rx, r in _CUT_RANK if rx.search(txt)), default=0)
            if sc > score:
                best, score = v, sc
        if best is not None:
            out[k] = best
    return out


def media_for_roll(caps, roll) -> str:
    """Medientyp im Treiber passend zur Rolle (Medienname bzw. Grammatur laut Gerät). "" = nichts Passendes."""
    key = caps.roles.get("mediatype") if caps is not None else None
    if not key or key not in caps.options or roll is None:
        return ""
    want = _words(roll.media)
    best, score = "", 0
    for ch in caps.options[key].choices:
        t = f"{ch.value} {ch.text}"
        sc = len(want & _words(t)) * 2
        if roll.weight and re.search(rf"(?<!\d){roll.weight}\s*g", t, re.I):
            sc += 3
        if sc > score:
            best, score = ch.value, sc
    return best


def write_run(run: Run, s: PlanSettings, path: str, copies: int = 1) -> None:
    """Druckseite als PDF (copies > 1: die Seite so oft – für Ordner/Hotfolder ohne Kopienzahl)."""
    doc, cuts = make_run(run, s)
    try:
        for _k in range(max(1, copies) - 1):
            doc.import_pages(doc, [0])
        doc.save(path)
    finally:
        doc.close()
    if s.cut_contour:
        add_cut_contour(path, {k: cuts for k in range(max(1, copies))})


# --------------------------------------------------------------------------- #
# Zusammenstellen und drucken
# --------------------------------------------------------------------------- #
FOLDER_PREFIX = "folder:"             # Ausgabe in einen (Hot-)Ordner, z. B. für VersaWorks
FOLDERS_KEY = "plan_hotfolders"       # Benutzereinstellung: [{"name", "dir"}]


def hotfolders() -> list:
    from . import l10n
    out = []
    for e in l10n.load_settings().get(FOLDERS_KEY) or []:
        if isinstance(e, dict) and e.get("name") and e.get("dir"):
            out.append({"name": str(e["name"]), "dir": str(e["dir"])})
    return out


def save_hotfolders(lst: list) -> None:
    from . import l10n
    st = l10n.load_settings()
    st[FOLDERS_KEY] = [{"name": str(e["name"]), "dir": str(e["dir"])} for e in lst if e.get("name") and e.get("dir")]
    l10n.save_settings(st)


def is_folder(printer: str) -> bool:
    return str(printer or "").startswith(FOLDER_PREFIX)


def folder_dir(printer: str) -> str:
    name = printer[len(FOLDER_PREFIX):]
    for e in hotfolders():
        if e["name"] == name:
            return e["dir"]
    raise ValueError(tr("Ausgabe-Ordner nicht eingerichtet: {0}").format(name))


def rolls_for(session, printer: str, s: PlanSettings) -> tuple:
    """(Rollen, Herkunft, Hinweise). Rollen aus den Einstellungen gehen vor."""
    from . import rolls as rl
    if s.rolls:
        out = []
        for k, e in enumerate(s.rolls):
            r = rl.Roll.from_dict(e) if isinstance(e, dict) else rl.Roll(float(e))
            if not r.name:
                r.name = tr("Rolle {0}").format(k + 1)
            out.append(r)
        caps = session.caps_for(printer) if (session is not None and printer and not is_folder(printer)) else None
        if caps is not None:
            for k, r in enumerate(out):
                if not r.slot:
                    r.slot = rl.slot_for(caps, r.device or r.name, k)
        return out, "settings", []
    if is_folder(printer):
        st = rl.RollState(rl.manual(printer), "manual")
    else:
        st = rl.for_printer(session, printer, live=s.live_rolls)
    notes = []
    if not st.rolls:
        notes.append(tr("Keine Rollen bekannt – vom Gerät nichts gemeldet ({0}). Rollen von Hand eintragen.")
                     .format(st.error or tr("keine Adresse")))
    return st.rolls, st.origin, notes


def analyze(doc, pages: list, s: PlanSettings, rolls: list, source: str = "", qty: int = 1) -> list:
    items = []
    for p in pages:
        it = Item(p, qty, None, source=source, doc=doc, ov=clean_ov((s.overrides or {}).get(str(p + 1))))
        es = eff(s, it)
        it.area = detect(doc, p, es.frame, es.margin_mm)
        it.hairlines = hairlines(doc, p, s.hairline_mm, factor(it.area, es) * 100.0)
        items.append(it)
    place_all(items, rolls, s)
    return items


def place_all(items: list, rolls: list, s: PlanSettings) -> str:
    """Rolle je Plan auf den passenden Rollen (Planpapier/Material). -> Hinweis zur Rollenauswahl."""
    use, note = eligible_for(rolls, s)
    plain = [it for it in items if not (it.ov.get("roll_pick") or it.ov.get("material"))]
    _place_on(plain, rolls, use, s)
    notes = [note] if note else []
    for it in items:                                  # eigene Rolle/eigenes Material je Plan
        if it in plain:
            continue
        u, n = eligible_for(rolls, eff(s, it))
        _place_on([it], rolls, u, s)
        if n and n not in notes:
            notes.append(n)
    return " ".join(notes)


def _place_on(items: list, rolls: list, use: list, s: PlanSettings):
    """Nur auf den passenden Rollen platzieren, Index aber auf die volle Liste beziehen."""
    idx = [rolls.index(r) for r in use]
    place(items, use, s)
    for it in items:
        if it.fit is not None:
            it.fit.roll = idx[it.fit.roll]


def values_for(session, printer: str, caps, s: PlanSettings) -> dict:
    from .printcli import PrintSettings, resolve
    mat = material_of(s) or {}
    opts = dict(mat.get("options") or {})
    if mat.get("density_key") and mat.get("density"):
        opts[mat["density_key"]] = mat["density"]
    opts.update(s.options or {})
    ps = PrintSettings(color=s.color, media=s.media or mat.get("media", ""), quality=mat.get("quality", ""),
                       options=opts)
    vals, probs = resolve(caps, session.values_for(printer), ps)
    if probs:
        raise ValueError("; ".join(f"{w}: {m}" for w, m in probs))
    if mat.get("profile"):
        pid, intent = session.color_for(printer)
        session.color[printer] = (mat["profile"], mat.get("intent") or intent)
    return vals


def submit_run(session, printer: str, caps, base_vals: dict, run: Run, rolls: list, s: PlanSettings,
               log: bool = True) -> int | None:
    """Eine Druckseite run.copies-mal drucken (ein Auftrag). Mit Druckprotokoll inkl. Laufmeter."""
    from . import printjob, printlog
    roll = rolls[run.roll] if 0 <= run.roll < len(rolls) else None
    n = max(1, run.copies)
    vals = dict(base_vals)
    rs = eff(s, run.pieces[0][0].item) if run.pieces else s     # Material/Medium dieses Plans
    if rs.material != s.material and caps is not None and not is_folder(printer):
        try:
            vals = dict(values_for(session, printer, caps, rs))
        except ValueError:
            pass
    title = s.title or run.label
    jid, err = None, None
    tmp = tempfile.mkdtemp(prefix="passermark-plan-")
    try:
        if is_folder(printer):
            d = folder_dir(printer)
            os.makedirs(d, exist_ok=True)
            import re
            import time
            it0 = run.pieces[0][0].item
            stem = re.sub(r"[^\w.\-]+", "_", os.path.splitext(os.path.basename(it0.source or "plan"))[0])[:50]
            stem += f"_p{it0.page + 1}" + (f"+{len(run.pieces) - 1}" if len(run.pieces) > 1 else "")
            path = os.path.join(d, f"{time.strftime('%Y%m%d-%H%M%S')}_{stem}_{n}x.pdf")
            k = 1
            while os.path.exists(path):
                path = path[:-4] + f"-{k}.pdf"
                k += 1
            part = path + ".part"
            write_run(run, s, part, n)
            os.replace(part, path)
            jid = os.path.basename(path)
            return jid
        pkey, skey = caps.roles.get("pagesize"), caps.roles.get("source")
        if pkey:
            vals[pkey] = page_value(caps, run.across, run.along)
        if skey and roll is not None and roll.slot:
            vals[skey] = roll.slot
        if s.cut_sheets:                          # Abschnitt nach jeder Seite – außer von Hand anders gesetzt
            for k, v in cut_values(caps).items():
                if k not in (s.options or {}):
                    vals[k] = v
        mkey = caps.roles.get("mediatype")
        if mkey and roll is not None and not s.media and not (material_of(rs) or {}).get("media"):
            mv = media_for_roll(caps, roll)       # Medientyp nicht vorgegeben: der der Rolle (Gerät wählt danach)
            if mv:
                vals[mkey] = mv
        job = os.path.join(tmp, "plan.pdf")
        mode = copies_mode(s)
        try:
            if mode == "sheets":
                # ein Auftrag, je Exemplar eine Seite: der Drucker schneidet nach jeder Seite
                write_run(run, s, job, n)
                jid = printjob.send_prepared(session, printer, caps, job,
                                             title + (f" ×{n}" if n > 1 else ""), vals, 1, True, {})
            elif mode == "jobs" and n > 1:
                write_run(run, s, job)
                ids = []
                for k in range(n):
                    ids.append(printjob.send_prepared(session, printer, caps, job, f"{title} ({k + 1}/{n})",
                                                      vals, 1, True, {}))
                jid = ", ".join(str(x) for x in ids if x is not None) or None
            else:
                write_run(run, s, job)
                jid = printjob.send_prepared(session, printer, caps, job, title, vals, n, True, {})
        except Exception as e:
            err = str(e)
            raise
        return jid
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
        if log and printlog.enabled(session.cfg):
            printlog.write(log_record(caps, printer, run, roll, s, vals, session, jid, err), session.cfg)


def log_record(caps, printer, run: Run, roll, s: PlanSettings, vals: dict, session, jid, err) -> dict:
    from . import printlog
    first = run.pieces[0][0].item
    n = max(1, run.copies)
    pages = sorted({p.item.page for p, _x, _y in run.pieces})
    rec = printlog.build(caps if not is_folder(printer) else None, printer, first.source or None,
                         s.title or run.label, pages, s, vals, n, False, False,
                         session.color_for(printer) if not is_folder(printer) else ("", ""), jid, error=err,
                         sheet_mm=[round(run.across, 1), round(run.along, 1)])
    e = rec["job"]
    e["kind"] = s.kind
    e["roll_mm"] = round(run.width_mm, 1)
    e["roll"] = roll.label() if roll is not None else None
    e["length_mm"] = round(run.along * n, 1)
    e["run_m"] = round(run.along * n / 1000.0, 3)
    e["pieces"] = [{"plan": p.label, "page": p.item.page + 1, "x_mm": round(x, 1), "y_mm": round(y, 1),
                    "size_mm": [round(p.across, 1), round(p.along, 1)], "rotated": p.rotated,
                    "clipped": p.clipped} for p, x, y in run.pieces]
    e["area"] = first.area.to_dict() if first.area else None
    if len({id(p.item.doc) for p, _x, _y in run.pieces}) == 1 and len(run.pieces) == 1:
        st = compact(dataclasses.replace(s, printer=printer, copies=n, collate=False, order="list", nest=False,
                                         title=s.title, dry_run=False))
        st["rolls"] = [{"width_mm": round(run.width_mm, 1), "slot": roll.slot if roll is not None else ""}]
        if first.ov or first.frame:                     # Abweichungen dieses Plans mit protokollieren
            st["overrides"] = {str(first.page + 1): clean_ov(dict(first.ov, **({"frame": first.frame}
                                                                                if first.frame else {})))}
        step = {"job": "plan", "settings": st, "pages": str(first.page + 1)}
        rec["workflow"]["steps"] = list(rec["workflow"]["steps"][:-1]) + [step]
    else:                                   # mehrere Stücke auf einer Seite: Nachdruck aller Seiten dieser Datei
        st = compact(dataclasses.replace(s, printer=printer, copies=1, title=s.title, dry_run=False))
        st["rolls"] = [{"width_mm": round(run.width_mm, 1), "slot": roll.slot if roll is not None else ""}]
        ovs = {str(p.item.page + 1): clean_ov(p.item.ov) for p, _x, _y in run.pieces if p.item.ov}
        if ovs:
            st["overrides"] = ovs
        step = {"job": "plan", "settings": st, "pages": ",".join(str(p + 1) for p in pages)}
        rec["workflow"]["steps"] = list(rec["workflow"]["steps"][:-1]) + [step]
    return rec


def compact(s: PlanSettings) -> dict:
    d = dataclasses.asdict(s)
    base = dataclasses.asdict(PlanSettings())
    return {k: v for k, v in d.items() if v != base.get(k) or k == "printer"}


def _job_info(run: Run, rolls: list, s: PlanSettings | None = None) -> dict:
    mode = copies_mode(s) if s is not None else "sheets"
    n = max(1, run.copies)
    return {"plan": run.label, "pages": [p.item.page + 1 for p, _x, _y in run.pieces], "copies": run.copies,
            "copies_mode": mode, "jobs_sent": n if mode == "jobs" else 1, "sheets_per_job": n if mode == "sheets" else 1,
            "cuts": n,
            "roll_mm": run.width_mm, "size_mm": [round(run.across, 1), round(run.along, 1)],
            "rotated": run.pieces[0][0].rotated if len(run.pieces) == 1 else None,
            "pieces": len(run.pieces), "slot": rolls[run.roll].slot if 0 <= run.roll < len(rolls) else ""}


def print_items(session, printer: str, items: list, rolls: list, s: PlanSettings, progress=None, cancel=None) -> dict:
    """Pläne/Poster drucken (Reihenfolge laut Einstellung). -> Info inkl. Laufmeter und Auftragsnummern."""
    caps = None if is_folder(printer) else session.caps_for(printer)
    if is_folder(printer):
        base = {}
    else:
        base = values_for(session, printer, caps, s) if not s.dry_run else _try_values(session, printer, caps, s)
    runs = build_runs(items, rolls, s)
    info = summary(printer, items, rolls, s)
    info["cut_options"] = cut_values(caps) if (s.cut_sheets and caps is not None) else {}
    info["jobs"] = []
    for k, run in enumerate(runs):
        if cancel is not None and cancel():
            break
        if progress:
            progress(k, len(runs), run.label)
        rec = _job_info(run, rolls, s)
        if not s.dry_run:
            rec["job_id"] = submit_run(session, printer, caps, base, run, rolls, s)
        info["jobs"].append(rec)
    if progress:
        progress(len(runs), len(runs), "")
    return info


def _try_values(session, printer, caps, s):
    try:
        return values_for(session, printer, caps, s)
    except ValueError:
        return dict(session.values_for(printer))


def summary(printer: str, items: list, rolls: list, s: PlanSettings) -> dict:
    lens = lengths(items, rolls, s)
    use, _n = eligible_for(rolls, s)
    clipped, tiled = [], []
    for it in items:
        ps = pieces_for(it, rolls, s, use)
        if any(p.clipped for p in ps):
            clipped.append(it.label)
        if len(ps) > 1:
            tiled.append(it.label)
    return {"printer": printer, "kind": s.kind, "dry_run": s.dry_run, "copies": max(1, int(s.copies)),
            "collate": s.collate, "nest": s.nest,
            "rolls": [dict(r.to_dict(), label=r.label()) for r in rolls],
            "lengths": lens,
            "single_m": round(sum(d["single_m"] for d in lens), 3),
            "total_m": round(sum(d["total_m"] for d in lens), 3),
            "plans": [{"plan": it.label, "page": it.page + 1, "qty": it.qty,
                       "area": it.area.to_dict() if it.area else None,
                       "size_mm": [round(it.size[0], 1), round(it.size[1], 1)],
                       "roll_mm": it.fit.width_mm if it.fit else None,
                       "rotated": it.fit.rotated if it.fit else None,
                       "length_mm": round(it.fit.along, 1) if it.fit else None,
                       "hairlines": it.hairlines} for it in items],
            "unfit": [it.label for it in items if it.area is not None and not pieces_for(it, rolls, s, use)],
            "clipped": clipped, "tiled": tiled,
            "notes": []}


def cut_file(items: list, rolls: list, s: PlanSettings, path: str, force: int = 0, speed: int = 0) -> int:
    """Schneidauftrag (HP-GL/CAMM-GL) für einen Satz: die Schnittkanten aller Stücke, Seite für Seite
        hintereinander auf der Rolle (für Schneideplotter ohne Druck, z. B. Folie). -> Anzahl Schnitte."""
    from . import roland
    runs = build_runs(items, rolls, dataclasses.replace(s, collate=False, cut_contour=True), 1)
    rects, base = [], 0.0
    for run in runs:
        _d, cuts = make_run(run, dataclasses.replace(s, cut_contour=True))
        _d.close()
        for (a, b_, c, d) in cuts:
            rects.append((a / MM, base + b_ / MM, c / MM, base + d / MM))
        base += run.along + max(0.0, s.gap_mm)
    with open(path, "wb") as f:
        f.write(roland.hpgl(roland.rect_paths(rects), force, speed))
    return len(rects)


def save_pdf(items: list, rolls: list, s: PlanSettings, path: str) -> int:
    """Alle Druckseiten (je ein Exemplar) in eine PDF – zum Prüfen oder Weitergeben. -> Seitenzahl."""
    import pypdfium2 as pdfium
    runs = build_runs(items, rolls, dataclasses.replace(s, collate=False), 1)
    out = pdfium.PdfDocument.new()
    cuts = {}
    try:
        for k, run in enumerate(runs):
            _d, c = make_run(run, s, out)
            cuts[k] = c
        out.save(path)
    finally:
        out.close()
    if s.cut_contour:
        add_cut_contour(path, cuts)
    return len(runs)


def print_pdf(path: str, s: PlanSettings, pages: list | None = None, session=None, progress=None) -> dict:
    """Ablauf-Schritt „plan“: alle (gewählten) Seiten der PDF als Pläne/Poster."""
    return plan_files([path], s, pages, session, progress)


def _open(path: str):
    import pypdfium2 as pdfium
    from . import images
    if images.is_image(path):
        return images.images_to_document([path], 96.0)
    return pdfium.PdfDocument(path)


def plan_files(paths: list, s: PlanSettings, pages: list | None = None, session=None, progress=None,
               plt: str = "") -> dict:
    """passermark-cli plan / Ablauf: Pläne aus einer oder mehreren Dateien – Laufmeter, Rollen, drucken.
        pages gilt nur bei einer Datei. dry_run: nur rechnen (auch ohne Drucker, dann mit den Rollen aus s.rolls)."""
    from . import config, printers, printjob
    from .session import Session
    if session is None:
        session = Session(config.load())
    printer = s.printer or ("" if (s.dry_run and s.rolls) else printjob.default_printer(session)) or ""
    if not printer and not s.dry_run:
        raise RuntimeError(tr("Kein Drucker eingerichtet."))
    if printer == printers.PDF_TARGET:
        raise ValueError(tr("Plandruck geht nur auf einen Drucker – zum Prüfen im Programm „Als PDF speichern“."))
    if is_folder(printer):
        folder_dir(printer)                           # gibt es den Ordner in den Einstellungen?
    elif printer and not s.dry_run:
        try:
            names = [p.name for p in printers.list_printers()]
        except Exception:
            names = None
        if names is not None and printer not in names:
            raise ValueError(tr("Drucker nicht gefunden: {0} (vorhanden: {1})").format(printer, ", ".join(names) or "–"))
    if printer and not is_folder(printer) and (s.profile != "admin" or s.intent):
        pid, intent = session.color_for(printer)
        session.color[printer] = ("" if s.profile == "none" else (pid if s.profile == "admin" else s.profile),
                                  s.intent or intent)
    if s.material and material_of(s) is None:
        raise ValueError(tr("Material nicht gefunden: {0}").format(s.material))
    rolls, origin, notes = rolls_for(session, printer, s)
    if not rolls:
        raise ValueError(notes[0] if notes else tr("Keine Rollen bekannt."))
    docs, items = [], []
    try:
        for path in paths:
            doc = _open(path)
            docs.append(doc)
            sel = list(range(len(doc)))
            if pages and len(paths) == 1:
                sel = [p for p in pages if 0 <= p < len(doc)]
            items += analyze(doc, sel, s, rolls, path)
        _use, wnote = eligible_for(rolls, s)
        if s.dry_run or not printer:
            info = summary(printer, items, rolls, s)
            info["jobs"] = [_job_info(run, rolls, s) for run in build_runs(items, rolls, s)]
            if s.cut_sheets and printer and not is_folder(printer) and session is not None:
                info["cut_options"] = {}
                try:
                    info["cut_options"] = cut_values(session.caps_for(printer))
                except Exception:                       # noqa: BLE001 – Probelauf auch ohne erreichbaren Drucker
                    pass
        else:
            from . import printlog
            with printlog.source(printlog.current() if printlog.current() != "dialog" else "cli"):
                info = print_items(session, printer, items, rolls, s, progress)
        info["roll_origin"] = origin
        info["notes"] = notes + ([wnote] if wnote else []) + [
            tr("Passt auf keine Rolle: {0}").format(u) for u in info["unfit"]] + [
            tr("Breiter als die Rolle – abgeschnitten: {0}").format(u) for u in info["clipped"]] + [
            tr("In Bahnen geteilt: {0}").format(u) for u in info["tiled"]]
        hl = sum(it.hairlines for it in items)
        if hl and not s.fix_hairlines:
            info["notes"].append(tr("{0} Linie(n) dünner als {1} mm – fix_hairlines hebt sie an.")
                                 .format(hl, mm_text(s.hairline_mm)))
        from . import printmat
        info["notes"] += printmat.notes(material_of(s), session.cfg)
        info["pages"] = len(items)
        if plt:
            info["cut_file"] = {"path": os.path.abspath(plt), "cuts": cut_file(items, rolls, s, plt)}
        return info
    finally:
        for d in docs:
            d.close()
