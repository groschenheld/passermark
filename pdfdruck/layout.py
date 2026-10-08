# SPDX-License-Identifier: GPL-3.0-or-later
# pdfToolkit – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Seitenauswahl, Skalierung und N-Up-Ausschießen.

Reine Geometrie (plan_*) ist von pdfium entkoppelt und testbar.
impose() erzeugt daraus ein vektorielles PDF mit pypdfium2 (Form-XObjects),
das 1:1 auf das gewählte Papier passt und mit print-scaling=none gedruckt wird.

Koordinaten: PDF-Punkte (1/72 Zoll), Ursprung unten links.
"Physisch" = Blatt im Hochformat wie vom Treiber gemeldet (PaperDimension).
"Logisch"  = Blatt in gewählter Ausrichtung (bei Querformat 90° gedreht).
"""
from __future__ import annotations

from .l10n import tr

import re
from dataclasses import dataclass, field

MM = 72.0 / 25.4

POSTER_FORMATS = {  # Breite x Höhe in mm (Hochformat)
    "A0": (841, 1189), "A1": (594, 841), "A2": (420, 594), "A3": (297, 420), "A4": (210, 297),
    "B1": (707, 1000), "B2": (500, 707), "B3": (353, 500),
}
LABEL_H = 9.0       # Höhe der Beschriftungszeile (pt)

# Standardraster (Spalten, Zeilen) für Querformat; Hochformat = vertauscht
NUP_GRIDS = {2: (2, 1), 4: (2, 2), 6: (3, 2), 8: (4, 2), 9: (3, 3), 16: (4, 4)}

ORDERS = {
    "horizontal": "Horizontal (Z)",
    "horizontal_rev": "Horizontal umgekehrt",
    "vertical": "Vertikal (N)",
    "vertical_rev": "Vertikal umgekehrt",
}


# --------------------------------------------------------------------------- #
# Datenklassen
# --------------------------------------------------------------------------- #
@dataclass
class Sheet:
    width: float                      # physisch, Punkte
    height: float
    imageable: tuple[float, float, float, float] | None = None  # llx,lly,urx,ury

    def __post_init__(self):
        if self.width > self.height:  # immer Hochformat als Referenz
            self.width, self.height = self.height, self.width
            if self.imageable:
                l, b, r, t = self.imageable
                # Querformat-Angabe in Hochformat drehen (selten, defensiv)
                self.imageable = (b, self.height - r, t, self.height - l)


@dataclass
class LayoutSettings:
    mode: str = "fit"             # fit | actual | shrink | custom
    custom_percent: float = 100.0
    custom_by: str = "percent"    # percent | short | long  (benutzerdefiniert: Prozent oder Kantenmaß)
    custom_mm: float = 210.0      # Zielmaß der kurzen bzw. langen Kante in mm
    nup: int = 1                  # 1 = aus, sonst Seiten pro Blatt
    cols: int = 0                 # >0 und rows>0 => benutzerdefiniertes Raster
    rows: int = 0
    order: str = "horizontal"
    tile_mode: str = "fit"        # fit | actual | custom
    tile_percent: float = 100.0
    gap_mm: float = 0.0
    borders: bool = False
    orientation: str = "auto"     # auto | portrait | landscape
    autorotate: bool = True
    center: bool = True
    use_margins: bool = True      # nicht bedruckbaren Rand des Druckers berücksichtigen
    handling: str = "size"        # size | multiple | booklet | poster
    # Broschüre
    booklet_sides: str = "both"   # both | front | back
    booklet_binding: str = "left" # left | right
    booklet_sheets: str = ""      # Blattbereich, z. B. "1-3" (leer = alle)
    booklet_gutter_mm: float = 0.0
    # Poster / Überformat
    poster_mode: str = "scale"    # scale | sheets | target
    poster_percent: float = 200.0
    poster_cols: int = 2
    poster_rows: int = 2
    poster_target: str = "A2"     # Schlüssel aus POSTER_FORMATS oder "custom"
    poster_target_w_mm: float = 420.0
    poster_target_h_mm: float = 594.0
    poster_overlap_mm: float = 10.0
    poster_marks: bool = True     # Schnitt-/Klebelinien
    poster_labels: bool = True    # Beschriftung je Kachel
    poster_large_only: bool = False
    # Weitere Optionen
    mirror_h: bool = False        # horizontal spiegeln (Transferdruck)
    mirror_v: bool = False
    step_repeat: bool = False     # eine Seite mehrfach je Blatt (Nutzen)
    sr_mode: str = "auto"         # auto (so viele wie passen) | grid
    sr_cols: int = 2
    sr_rows: int = 5
    sr_gap_mm: float = 0.0
    sr_percent: float = 100.0
    sr_by: str = "percent"        # percent | short | long  (Nutzengröße: Prozent oder Kantenmaß)
    sr_mm: float = 85.0           # Zielmaß der kurzen bzw. langen Kante je Nutzen in mm
    sr_orientation: str = "auto"  # Blatt: auto | portrait | landscape
    sr_rotate: str = "auto"       # Nutzen: auto | 0 | 90
    sr_join: str = "bleed"        # edge = Kante an Kante | bleed = Überfüller an Überfüller | gap = Abstand
    crop_marks: bool = False      # Schnittmarken
    bleed_mm: float = 0.0         # Anschnitt/Überfüller durch Spiegeln der Ränder

    @classmethod
    def from_dict(cls, d: dict | None) -> "LayoutSettings":
        s = cls()
        d = d or {}
        for k, v in d.items():
            if hasattr(s, k):
                setattr(s, k, type(getattr(s, k))(v))
        if "handling" not in d and (s.nup > 1 or s.cols * s.rows > 1):
            s.handling = "multiple"          # alte Konfigurationen
        return s

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @property
    def is_nup(self) -> bool:
        return self.handling == "multiple" and (
            self.nup > 1 or (self.cols > 0 and self.rows > 0 and self.cols * self.rows > 1))


@dataclass
class Placement:
    src: int                      # Quellseiten-Index (0-basiert)
    rot: int                      # 0 oder 90 (zusätzlich, gegen den Uhrzeigersinn)
    scale: float
    x: float                      # logisch, linke untere Ecke der platzierten Seite
    y: float
    w: float                      # platzierte Größe
    h: float
    clip: tuple[float, float, float, float] | None  # logische Zelle (x,y,w,h) bei N-Up
    bleed: float = 0.0            # gespiegelter Anschnitt in pt (um die platzierte Seite)
    bleed_sides: tuple = (True, True, True, True)   # links, unten, rechts, oben
    mirror_h: bool = False
    mirror_v: bool = False


@dataclass
class SheetPlan:
    landscape: bool
    placements: list[Placement] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Zusatzgrafik in logischen Koordinaten:
    #   ("line", x0, y0, x1, y1, gestrichelt)  |  ("text", x, y, größe, text)
    marks: list[tuple] = field(default_factory=list)
    label: str = ""               # Beschreibung für die Vorschau
    duplex_short: bool = False    # Broschüre: Wenden an der kurzen Kante nötig


# --------------------------------------------------------------------------- #
# Seitenauswahl
# --------------------------------------------------------------------------- #
def parse_ranges(text: str, count: int) -> list[int]:
    """'1-3, 5, 8-' -> 0-basierte Indizes. Wirft ValueError bei Unsinn."""
    text = (text or "").strip()
    if not text:
        return list(range(count))
    out: list[int] = []
    for part in re.split(r"[,;]\s*", text):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"(\d*)\s*-\s*(\d*)", part)
        if m:
            a = int(m.group(1)) if m.group(1) else 1
            b = int(m.group(2)) if m.group(2) else count
        elif part.isdigit():
            a = b = int(part)
        else:
            raise ValueError(tr("Ungültiger Bereich: {0!r}").format(part))
        if a < 1 or b > count or a > b:
            raise ValueError(tr("Bereich außerhalb 1–{0}: {1!r}").format(count, part))
        out.extend(range(a - 1, b))
    return out


def select_pages(count: int, ranges: str = "", subset: str = "all",
                 reverse: bool = False, current: int | None = None) -> list[int]:
    pages = [current] if current is not None else parse_ranges(ranges, count)
    if subset == "odd":
        pages = [p for p in pages if (p + 1) % 2 == 1]
    elif subset == "even":
        pages = [p for p in pages if (p + 1) % 2 == 0]
    if reverse:
        pages = pages[::-1]
    return pages


# --------------------------------------------------------------------------- #
# Geometrie
# --------------------------------------------------------------------------- #
def _logical(sheet: Sheet, landscape: bool):
    """Logische Blattgröße und bedruckbarer Bereich (x,y,w,h)."""
    W, H = sheet.width, sheet.height
    l, b, r, t = sheet.imageable or (0.0, 0.0, W, H)
    if not landscape:
        return W, H, (l, b, r - l, t - b)
    # physisch (X,Y) -> logisch (x,y) = (Y, W - X)
    return H, W, (b, W - r, t - b, r - l)


def _area(sheet: Sheet, landscape: bool, use_margins: bool):
    LW, LH, printable = _logical(sheet, landscape)
    return LW, LH, (printable if use_margins else (0.0, 0.0, LW, LH)), printable


def _fits(rect, area, tol=0.5) -> bool:
    x, y, w, h = rect
    ax, ay, aw, ah = area
    return x >= ax - tol and y >= ay - tol and x + w <= ax + aw + tol and y + h <= ay + ah + tol


def _cell_order(n_cells: int, cols: int, rows: int, order: str) -> list[tuple[int, int]]:
    """Liefert (spalte, zeile) je Kachel-Index; Zeile 0 = oben."""
    cells = []
    for i in range(n_cells):
        if order.startswith("vertical"):
            c, r = divmod(i, rows)
        else:
            r, c = divmod(i, cols)
        if order.endswith("_rev"):
            c = cols - 1 - c
        cells.append((c, r))
    return cells


def _pick_grid(first_size, sheet: Sheet, s: LayoutSettings):
    """Wählt Ausrichtung + Raster mit dem größten Fit-Maßstab (wie Acrobat 'Auto')."""
    if s.cols > 0 and s.rows > 0:
        grids = [(s.cols, s.rows)]
        if s.orientation == "auto":
            grids.append((s.rows, s.cols))  # Raster darf mitdrehen
    else:
        base = NUP_GRIDS.get(s.nup)
        if base is None:  # z. B. 3, 5 … -> 1 Spalte n Zeilen bzw. umgekehrt
            base = (s.nup, 1)
        grids = [base, (base[1], base[0])]
    orients = [False, True] if s.orientation == "auto" else [s.orientation == "landscape"]
    gap = s.gap_mm * MM
    pw, ph = first_size
    best = None
    for land in orients:
        _, _, area, _ = _area(sheet, land, s.use_margins)
        for cols, rows in grids:
            cw = (area[2] - gap * (cols - 1)) / cols
            ch = (area[3] - gap * (rows - 1)) / rows
            if cw <= 0 or ch <= 0:
                continue
            w, h = pw, ph
            rotated = s.autorotate and (w > h) != (cw > ch) and abs(w - h) > 1
            if rotated:
                w, h = h, w
            sc = min(cw / w, ch / h)
            # größter Maßstab gewinnt; bei Gleichstand: ohne Drehung bevorzugen
            score = (round(sc, 3), not rotated)
            if best is None or score > best[0]:
                best = (score, land, cols, rows)
    if best is None:
        raise ValueError(tr("Raster passt nicht auf das Blatt (Abstand zu groß?)"))
    return best[1], best[2], best[3]


MAX_PER_SHEET = 400        # Schutz: mehr Nutzen/Kacheln pro Blatt sind praktisch nie gewollt
MAX_SHEETS = 2000          # Schutz: mehr Ausgabeblätter pro Auftrag (Poster) ebenso
MARK_OFFSET = 2.0 * MM     # Abstand Schnittmarke zum Anschnitt
MARK_LEN = 5.0 * MM


def _reserve(s: LayoutSettings) -> float:
    """Platz rund um die Endformat-Kante für Anschnitt + Schnittmarken."""
    if s.handling in ("booklet", "poster") and not s.step_repeat:
        return 0.0
    r = s.bleed_mm * MM
    if s.crop_marks:
        r += MARK_OFFSET + MARK_LEN
    return r


def _inset(area, r):
    x, y, w, h = area
    return (x + r, y + r, max(1.0, w - 2 * r), max(1.0, h - 2 * r))


def edge_scale(pw: float, ph: float, by: str, mm: float, percent: float) -> float:
    """Maßstab aus Prozent oder aus „kurze/lange Kante auf mm“ (die andere Kante ergibt sich)."""
    if by == "short":
        return max(0.001, mm * MM / min(pw, ph))
    if by == "long":
        return max(0.001, mm * MM / max(pw, ph))
    return percent / 100.0


def custom_scale(pw: float, ph: float, s: LayoutSettings) -> float:
    """Benutzerdefinierter Maßstab (Bereich „Größe“)."""
    return edge_scale(pw, ph, s.custom_by, s.custom_mm, s.custom_percent)


def plan_single(sizes, pages, sheet: Sheet, s: LayoutSettings) -> list[SheetPlan]:
    plans = []
    for p in pages:
        pw, ph = sizes[p]
        if s.orientation == "auto":
            land = pw > ph
        else:
            land = s.orientation == "landscape"
        LW, LH, area, printable = _area(sheet, land, s.use_margins)
        rot = 0
        if s.orientation != "auto" and s.autorotate and (pw > ph) != (LW > LH) and abs(pw - ph) > 1:
            rot = 90
            pw, ph = ph, pw
        area = _inset(area, _reserve(s))
        fit = min(area[2] / pw, area[3] / ph)
        if s.mode == "fit":
            sc, ref = fit, area
        elif s.mode == "shrink":
            sc, ref = min(1.0, fit), area
        elif s.mode == "custom":
            sc, ref = custom_scale(pw, ph, s), (0.0, 0.0, LW, LH)
        else:  # actual
            sc, ref = 1.0, (0.0, 0.0, LW, LH)
        w, h = pw * sc, ph * sc
        if s.center:
            x = ref[0] + (ref[2] - w) / 2
            y = ref[1] + (ref[3] - h) / 2
        else:  # oben links im Bezugsbereich
            x, y = ref[0], ref[1] + ref[3] - h
        plan = SheetPlan(land, [Placement(p, rot, sc, x, y, w, h, None)])
        if not _fits((x, y, w, h), printable):
            plan.warnings.append(tr("Seite {0} ragt über den bedruckbaren Bereich – wird beschnitten.").format(p + 1))
        plans.append(plan)
    return plans


def plan_nup(sizes, pages, sheet: Sheet, s: LayoutSettings) -> list[SheetPlan]:
    if not pages:
        return []
    land, cols, rows = _pick_grid(sizes[pages[0]], sheet, s)
    LW, LH, area, printable = _area(sheet, land, s.use_margins)
    area = _inset(area, _reserve(s))
    gap = max(s.gap_mm * MM, 2 * s.bleed_mm * MM)
    cw = (area[2] - gap * (cols - 1)) / cols
    ch = (area[3] - gap * (rows - 1)) / rows
    per = cols * rows
    order = _cell_order(per, cols, rows, s.order)
    plans = []
    for start in range(0, len(pages), per):
        plan = SheetPlan(land)
        for i, p in enumerate(pages[start:start + per]):
            c, r = order[i]
            cx = area[0] + c * (cw + gap)
            cy = area[1] + area[3] - (r + 1) * ch - r * gap
            pw, ph = sizes[p]
            rot = 0
            if s.autorotate and (pw > ph) != (cw > ch) and abs(pw - ph) > 1:
                rot = 90
                pw, ph = ph, pw
            fit = min(cw / pw, ch / ph)
            if s.tile_mode == "actual":
                sc = 1.0
            elif s.tile_mode == "custom":
                sc = s.tile_percent / 100.0
            else:
                sc = fit
            w, h = pw * sc, ph * sc
            x = cx + (cw - w) / 2
            y = cy + (ch - h) / 2
            if sc > fit + 1e-6:
                plan.warnings.append(tr("Seite {0} größer als Kachel – wird beschnitten.").format(p + 1))
            plan.placements.append(Placement(p, rot, sc, x, y, w, h, (cx, cy, cw, ch)))
        plans.append(plan)
    return plans


def booklet_order(n: int, binding: str = "left") -> list[tuple[list, list]]:
    """Seitenreihenfolge für Rückendrahtheftung (Sattelheftung).

    Liefert je Bogen (vorne, hinten) als [links, rechts]; Indizes >= n sind Leerseiten.
    Beispiel 8 Seiten, Bindung links: Bogen1 vorne [8,1] hinten [2,7], Bogen2 vorne [6,3] hinten [4,5].
    """
    N = max(4, -(-n // 4) * 4)
    out = []
    for i in range(N // 4):
        front = [N - 1 - 2 * i, 2 * i]
        back = [2 * i + 1, N - 2 - 2 * i]
        if binding == "right":
            front.reverse()
            back.reverse()
        out.append((front, back))
    return out


def plan_booklet(sizes, pages, sheet: Sheet, s: LayoutSettings) -> list[SheetPlan]:
    if not pages:
        return []
    pw0, ph0 = sizes[pages[0]]
    land = ph0 >= pw0            # Hochformatseiten -> Querbogen, Falz senkrecht
    LW, LH, area, printable = _area(sheet, land, s.use_margins)
    g = s.booklet_gutter_mm * MM / 2
    ax, ay, aw, ah = area
    if land:   # links | rechts, Falz bei LW/2
        cells = [(ax, ay, LW / 2 - g - ax, ah), (LW / 2 + g, ay, ax + aw - LW / 2 - g, ah)]
        inner = ["right", "left"]          # Kante Richtung Falz
    else:      # oben | unten (Querformatseiten), Falz bei LH/2
        cells = [(ax, LH / 2 + g, aw, ay + ah - LH / 2 - g), (ax, ay, aw, LH / 2 - g - ay)]
        inner = ["bottom", "top"]
    if min(c[2] for c in cells) <= 0 or min(c[3] for c in cells) <= 0:
        raise ValueError(tr("Bundsteg zu groß für das Papier"))

    order = booklet_order(len(pages), s.booklet_binding)
    n_bogen = len(order)
    chosen = parse_ranges(s.booklet_sheets, n_bogen) if s.booklet_sheets.strip() else range(n_bogen)
    sides = {"both": (0, 1), "front": (0,), "back": (1,)}.get(s.booklet_sides, (0, 1))
    blanks = n_bogen * 4 - len(pages)

    plans = []
    for b in chosen:
        for side in sides:
            sp = SheetPlan(land, label=tr("Bogen {0}/{1} – {2}").format(b + 1, n_bogen, tr('Vorderseite') if side == 0 else tr('Rückseite')),
                           duplex_short=(s.booklet_sides == "both"))
            for slot, idx in enumerate(order[b][side]):
                if idx >= len(pages):
                    continue                 # Leerseite
                p = pages[idx]
                cx, cy, cw, ch = cells[slot]
                pw, ph = sizes[p]
                rot = 0
                if s.autorotate and (pw > ph) != (cw > ch) and abs(pw - ph) > 1:
                    rot, pw, ph = 90, ph, pw
                sc = min(cw / pw, ch / ph)
                w, h = pw * sc, ph * sc
                x, y = cx + (cw - w) / 2, cy + (ch - h) / 2
                # an den Falz rücken
                if inner[slot] == "right":
                    x = cx + cw - w
                elif inner[slot] == "left":
                    x = cx
                elif inner[slot] == "bottom":
                    y = cy
                else:
                    y = cy + ch - h
                sp.placements.append(Placement(p, rot, sc, x, y, w, h, (cx, cy, cw, ch)))
            plans.append(sp)
    if blanks and plans:
        plans[0].warnings.append(tr("{0} Leerseite(n) am Ende ergänzt (Seitenzahl auf Vielfaches von 4).").format(blanks))
    return plans


def _poster_geometry(pw, ph, sheet: Sheet, s: LayoutSettings, land: bool):
    LW, LH, area, _ = _area(sheet, land, s.use_margins)
    ax, ay, aw, ah = area
    if s.poster_labels:
        ay, ah = ay + LABEL_H, ah - LABEL_H
    ov = s.poster_overlap_mm * MM
    sw, sh = aw - ov, ah - ov
    if sw <= 0 or sh <= 0:
        raise ValueError(tr("Überlappung größer als der bedruckbare Bereich"))
    if s.poster_mode == "sheets":
        sc = min((s.poster_cols * sw + ov) / pw, (s.poster_rows * sh + ov) / ph)
    elif s.poster_mode == "target":
        tw, th = POSTER_FORMATS.get(s.poster_target, (s.poster_target_w_mm, s.poster_target_h_mm))
        tw, th = tw * MM, th * MM
        if (pw > ph) != (tw > th):
            tw, th = th, tw
        sc = min(tw / pw, th / ph)
    else:
        sc = s.poster_percent / 100.0
    W, H = pw * sc, ph * sc
    cols = max(1, -(-(W - ov - 0.01) // sw)) if W > aw else 1
    rows = max(1, -(-(H - ov - 0.01) // sh)) if H > ah else 1
    cols, rows = int(cols), int(rows)
    return dict(area=(ax, ay, aw, ah), ov=ov, sw=sw, sh=sh, sc=sc, W=W, H=H, cols=cols, rows=rows)


def plan_poster(sizes, pages, sheet: Sheet, s: LayoutSettings) -> list[SheetPlan]:
    plans = []
    for p in pages:
        pw, ph = sizes[p]
        if s.poster_large_only:
            land = pw > ph
            _, _, area, _ = _area(sheet, land, s.use_margins)
            if pw <= area[2] + 0.5 and ph <= area[3] + 0.5:
                single = LayoutSettings(mode="actual", center=True, orientation="landscape" if land else "portrait",
                                        use_margins=s.use_margins)
                plans.extend(plan_single(sizes, [p], sheet, single))
                continue
        orients = [False, True] if s.orientation == "auto" else [s.orientation == "landscape"]
        best = None
        for land in orients:
            geo = _poster_geometry(pw, ph, sheet, s, land)
            # weniger Blätter gewinnt; bei "Anzahl Blätter" der größere Maßstab
            key = (-geo["sc"], geo["cols"] * geo["rows"]) if s.poster_mode == "sheets" \
                else (geo["cols"] * geo["rows"], -geo["sc"])
            if best is None or key < best[0]:
                best = (key, land, geo)
        _, land, geo = best
        ax, ay, aw, ah = geo["area"]
        ov, sw, sh, sc = geo["ov"], geo["sw"], geo["sh"], geo["sc"]
        cols, rows = geo["cols"], geo["rows"]
        if len(plans) + cols * rows > MAX_SHEETS:
            raise ValueError(tr("Das Poster ergäbe {0} Blätter pro Seite – Maßstab bzw. Zielformat prüfen (Grenze {1} Blätter).").format(cols * rows, MAX_SHEETS))
        TW, TH = cols * sw + ov, rows * sh + ov
        px, py = (TW - geo["W"]) / 2, (TH - geo["H"]) / 2
        rot_w, rot_h = geo["W"], geo["H"]
        for r in range(rows):
            for c in range(cols):
                x = ax + px - c * sw
                y = ay + py - (TH - r * sh - ah)
                sp = SheetPlan(land, label=tr("Seite {0} – Kachel Zeile {1}/{2}, Spalte {3}/{4}").format(p + 1, r + 1, rows, c + 1, cols))
                sp.placements.append(Placement(p, 0, sc, x, y, rot_w, rot_h, (ax, ay, aw, ah)))
                if s.poster_marks and ov > 0:
                    if c > 0:   # hier abschneiden und auf den Überlappungsstreifen links kleben
                        sp.marks.append(("line", ax + ov, ay, ax + ov, ay + ah, True))
                    if r > 0:
                        sp.marks.append(("line", ax, ay + ah - ov, ax + aw, ay + ah - ov, True))
                if s.poster_labels:
                    sp.marks.append(("text", ax, ay - LABEL_H + 2, 7.0,
                                     f"Seite {p + 1}  ·  Zeile {r + 1}/{rows}  ·  Spalte {c + 1}/{cols}  ·  "
                                     f"{sc * 100:.0f} %  ·  {geo['W'] / MM:.0f} × {geo['H'] / MM:.0f} mm"))
                plans.append(sp)
    return plans


def _sr_gap(s: LayoutSettings) -> float:
    bleed = s.bleed_mm * MM
    if s.sr_join == "edge":
        return 0.0                         # Kante an Kante: ein gemeinsamer Schnitt
    if s.sr_join == "bleed":
        return 2 * bleed                   # Überfüller an Überfüller
    return max(s.sr_gap_mm * MM, 2 * bleed)


def plan_step_repeat(sizes, pages, sheet: Sheet, s: LayoutSettings) -> list[SheetPlan]:
    """Nutzen: jede Seite so oft wie möglich (oder im Raster) auf ein eigenes Blatt."""
    plans = []
    gap = _sr_gap(s)
    orients = {"portrait": [False], "landscape": [True]}.get(s.sr_orientation, [False, True])
    rots = {"0": [0], "90": [90]}.get(s.sr_rotate, [0, 90])
    for p in pages:
        pw0, ph0 = sizes[p]
        sc = edge_scale(pw0, ph0, s.sr_by, s.sr_mm, s.sr_percent)   # je Seite (Kantenmaß gilt pro Nutzen)
        best = None
        for land in orients:
            _, _, area, printable = _area(sheet, land, s.use_margins)
            # außen Platz für Anschnitt + Schnittmarken lassen -> Bereich für die Endformate
            ax, ay, aw, ah = _inset(area, _reserve(s))
            for rot in rots:
                w, h = (ph0 * sc, pw0 * sc) if rot else (pw0 * sc, ph0 * sc)
                if s.sr_mode == "grid":
                    cols, rows = s.sr_cols, s.sr_rows
                else:
                    cols = int((aw + gap + 0.01) // (w + gap))
                    rows = int((ah + gap + 0.01) // (h + gap))
                if cols < 1 or rows < 1:
                    continue
                bw, bh = cols * w + (cols - 1) * gap, rows * h + (rows - 1) * gap
                over = max(bw - aw, bh - ah, 0.0)
                # passt > mehr Nutzen > weniger Überstand > ungedreht > Hochformat
                key = (over <= 0.5, cols * rows, -over, rot == 0, not land)
                if best is None or key > best[0]:
                    best = (key, land, rot, cols, rows, (ax, ay, aw, ah), w, h, bw, bh)
        if best is None:      # passt nicht einmal einmal -> 1 Stück, beschnitten
            land = pw0 > ph0
            _, _, area, _ = _area(sheet, land, s.use_margins)
            best = (None, land, 0, 1, 1, area, pw0 * sc, ph0 * sc, pw0 * sc, ph0 * sc)
        _, land, rot, cols, rows, (ax, ay, aw, ah), w, h, bw, bh = best
        n = cols * rows
        if n > MAX_PER_SHEET:
            raise ValueError(tr("{0} Nutzen pro Blatt ({1:.1f} × {2:.1f} mm) – das ist sicher nicht gewollt (Grenze {3}). Nutzengröße bzw. Maßstab größer wählen.").format(n, w / MM, h / MM, MAX_PER_SHEET))
        x0, y0 = ax + (aw - bw) / 2, ay + (ah - bh) / 2
        sp = SheetPlan(land, label=tr("Seite {0} – {1} Nutzen ({2} × {3}), Blatt {4}{5}").format(p + 1, n, cols, rows, tr('quer') if land else tr('hoch'), tr(', Nutzen gedreht') if rot else ''))
        for r in range(rows):
            for c in range(cols):
                x = x0 + c * (w + gap)
                y = y0 + bh - (r + 1) * h - r * gap
                pl = Placement(p, rot, sc, x, y, w, h, None)
                if s.sr_join == "edge":   # Anschnitt nur an den Außenkanten des Blocks
                    pl.bleed_sides = (c == 0, r == rows - 1, c == cols - 1, r == 0)
                sp.placements.append(pl)
        if bw > aw + 0.5 or bh > ah + 0.5:
            sp.warnings.append(tr("Seite {0}: {1} × {2} passt nicht aufs Blatt – wird beschnitten. Blatt drehen, Nutzen drehen oder Maßstab verkleinern.").format(p + 1, cols, rows))
        plans.append(sp)
    return plans


def _crop_marks(sp: SheetPlan, bleed: float):
    """Schnittmarken außen um den Block aller Nutzen, verlängert an jeder Schnittkante."""
    if not sp.placements:
        return
    xs = sorted({round(v, 2) for pl in sp.placements for v in (pl.x, pl.x + pl.w)})
    ys = sorted({round(v, 2) for pl in sp.placements for v in (pl.y, pl.y + pl.h)})
    X0, X1, Y0, Y1 = xs[0], xs[-1], ys[0], ys[-1]
    o = bleed + MARK_OFFSET
    for x in xs:
        sp.marks.append(("line", x, Y1 + o, x, Y1 + o + MARK_LEN, False))
        sp.marks.append(("line", x, Y0 - o, x, Y0 - o - MARK_LEN, False))
    for y in ys:
        sp.marks.append(("line", X0 - o, y, X0 - o - MARK_LEN, y, False))
        sp.marks.append(("line", X1 + o, y, X1 + o + MARK_LEN, y, False))


def _apply_extras(plans, s: LayoutSettings):
    special = s.handling in ("booklet", "poster") and not s.step_repeat
    bleed = 0.0 if special else s.bleed_mm * MM
    for sp in plans:
        for pl in sp.placements:
            pl.bleed = bleed
            pl.mirror_h, pl.mirror_v = s.mirror_h, s.mirror_v
        if s.crop_marks and not special:
            _crop_marks(sp, bleed)
    return plans


def plan(sizes, pages, sheet: Sheet, s: LayoutSettings) -> list[SheetPlan]:
    if s.step_repeat:
        return _apply_extras(plan_step_repeat(sizes, pages, sheet, s), s)
    if s.handling == "booklet":
        return _apply_extras(plan_booklet(sizes, pages, sheet, s), s)
    if s.handling == "poster":
        return _apply_extras(plan_poster(sizes, pages, sheet, s), s)
    return _apply_extras(plan_nup(sizes, pages, sheet, s) if s.is_nup else plan_single(sizes, pages, sheet, s), s)


# --------------------------------------------------------------------------- #
# Affine Matrizen (a b c d e f) – x' = a x + c y + e ; y' = b x + d y + f
# --------------------------------------------------------------------------- #
def _mul(m1, m2):
    """Zuerst m1, dann m2 anwenden."""
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (a1 * a2 + b1 * c2, a1 * b2 + b1 * d2,
            c1 * a2 + d1 * c2, c1 * b2 + d1 * d2,
            e1 * a2 + f1 * c2 + e2, e1 * b2 + f1 * d2 + f2)


def _translate(x, y):
    return (1, 0, 0, 1, x, y)


def _scale(s):
    return (s, 0, 0, s, 0, 0)


def _rot90ccw(h0):
    """Dreht Box [0,w0]x[0,h0] um 90° gegen den Uhrzeiger zurück in den 1. Quadranten."""
    return (0, 1, -1, 0, h0, 0)


def _log2phys(sheet: Sheet, landscape: bool):
    # logisch (x,y) -> physisch (W - y, x)
    return (0, 1, -1, 0, sheet.width, 0) if landscape else (1, 0, 0, 1, 0, 0)


def placement_matrix(pl: Placement, src_size) -> tuple:
    w0, h0 = src_size
    m = (1, 0, 0, 1, 0, 0)
    if pl.rot == 90:
        m = _mul(m, _rot90ccw(h0))
    m = _mul(m, _scale(pl.scale))
    return _mul(m, _translate(pl.x, pl.y))


# --------------------------------------------------------------------------- #
# PDF erzeugen
# --------------------------------------------------------------------------- #
def impose(src, sheet: Sheet, plans: list[SheetPlan], only: list[int] | None = None,
           borders: bool = False):
    """Erzeugt ein neues pypdfium2-Dokument. `src` ist ein pdfium.PdfDocument."""
    import pypdfium2 as pdfium

    out = pdfium.PdfDocument.new()
    tiles = pdfium.PdfDocument.new()   # Zwischenseiten zum Clippen der Kacheln
    sizes = {}

    def size(i):
        if i not in sizes:
            sizes[i] = src.get_page_size(i)
        return sizes[i]

    xobjs = {}

    def xobj(i, dest):
        key = (i, id(dest))
        if key not in xobjs:
            xobjs[key] = src.page_as_xobject(i, dest)
        return xobjs[key]

    for idx, sp in enumerate(plans):
        if only is not None and idx not in only:
            continue
        page = out.new_page(sheet.width, sheet.height)
        to_phys = _log2phys(sheet, sp.landscape)
        for pl in sp.placements:
            m = placement_matrix(pl, size(pl.src))
            b = pl.bleed
            if pl.clip is None and b <= 0 and not (pl.mirror_h or pl.mirror_v):
                obj = xobj(pl.src, out).as_pageobject()
                obj.transform(pdfium.PdfMatrix(*_mul(m, to_phys)))
                page.insert_obj(obj)
                continue
            # Kachel: Bereich, der sichtbar sein soll (Seite + Anschnitt, ggf. auf Zelle begrenzt)
            sl, sb, sr_, st = pl.bleed_sides if b > 0 else (False,) * 4
            bx, by = pl.x - (b if sl else 0), pl.y - (b if sb else 0)
            bw, bh = pl.w + b * (sl + sr_), pl.h + b * (sb + st)
            if pl.clip is not None:
                cx, cy, cw, ch = pl.clip
                nx, ny = max(bx, cx), max(by, cy)
                bw, bh = min(bx + bw, cx + cw) - nx, min(by + bh, cy + ch) - ny
                bx, by = nx, ny
            if bw <= 0 or bh <= 0:
                continue
            tpage = tiles.new_page(bw, bh)
            local = _mul(m, _translate(-bx, -by))
            X0, Y0 = pl.x - bx, pl.y - by
            X1, Y1 = X0 + pl.w, Y0 + pl.h
            xs_ = [0] + ([-1] if sl else []) + ([1] if sr_ else [])
            ys_ = [0] + ([-1] if sb else []) + ([1] if st else [])
            offsets = [(dx, dy) for dx in xs_ for dy in ys_]
            for dx, dy in offsets:
                mm = local
                if dx:   # an linker/rechter Kante spiegeln
                    c = X0 if dx < 0 else X1
                    mm = _mul(mm, (-1, 0, 0, 1, 2 * c, 0))
                if dy:
                    c = Y0 if dy < 0 else Y1
                    mm = _mul(mm, (1, 0, 0, -1, 0, 2 * c))
                tobj = xobj(pl.src, tiles).as_pageobject()
                tobj.transform(pdfium.PdfMatrix(*mm))
                tpage.insert_obj(tobj)
            if borders:
                _add_border(tpage, X0, Y0, pl.w, pl.h, bw, bh)
            tpage.gen_content()
            tindex = len(tiles) - 1
            tpage.close()
            cx_obj = tiles.page_as_xobject(tindex, out)
            cell = cx_obj.as_pageobject()
            place = (1, 0, 0, 1, 0, 0)
            if pl.mirror_h:
                place = _mul(place, (-1, 0, 0, 1, bw, 0))
            if pl.mirror_v:
                place = _mul(place, (1, 0, 0, -1, 0, bh))
            cell.transform(pdfium.PdfMatrix(*_mul(_mul(place, _translate(bx, by)), to_phys)))
            page.insert_obj(cell)
            cx_obj.close()
        for m in sp.marks:
            _add_mark(out, page, m, to_phys)
        page.gen_content()
        page.close()
    for x in xobjs.values():
        x.close()
    tiles.close()
    return out


def impose_with(src, sheet: Sheet, plans, settings: LayoutSettings, only=None):
    return impose(src, sheet, plans, only, borders=settings.borders and settings.is_nup)


def _add_border(tpage, x, y, w, h, cw, ch):
    import pypdfium2.raw as r
    lw = 0.5
    x0, y0 = max(x, 0) + lw / 2, max(y, 0) + lw / 2
    x1, y1 = min(x + w, cw) - lw / 2, min(y + h, ch) - lw / 2
    if x1 <= x0 or y1 <= y0:
        return
    path = r.FPDFPageObj_CreateNewRect(x0, y0, x1 - x0, y1 - y0)
    r.FPDFPageObj_SetStrokeColor(path, 0, 0, 0, 255)
    r.FPDFPageObj_SetStrokeWidth(path, lw)
    r.FPDFPath_SetDrawMode(path, r.FPDF_FILLMODE_NONE, True)
    r.FPDFPage_InsertObject(tpage.raw, path)


def _add_mark(doc, page, m, to_phys):
    import ctypes
    import pypdfium2.raw as r
    if m[0] == "line":
        _, x0, y0, x1, y1, dashed = m
        obj = r.FPDFPageObj_CreateNewPath(x0, y0)
        r.FPDFPath_LineTo(obj, x1, y1)
        if dashed:
            r.FPDFPageObj_SetStrokeColor(obj, 90, 90, 90, 255)
            r.FPDFPageObj_SetStrokeWidth(obj, 0.4)
        else:   # Schnittmarke: Passerschwarz-ähnlich, dünn
            r.FPDFPageObj_SetStrokeColor(obj, 0, 0, 0, 255)
            r.FPDFPageObj_SetStrokeWidth(obj, 0.25)
        if dashed:
            arr = (ctypes.c_float * 2)(3.0, 2.0)
            r.FPDFPageObj_SetDashArray(obj, arr, 2, 0.0)
        r.FPDFPath_SetDrawMode(obj, r.FPDF_FILLMODE_NONE, True)
    elif m[0] == "text":
        _, x, y, size, text = m
        obj = r.FPDFPageObj_NewTextObj(doc.raw, b"Helvetica", float(size))
        buf = ctypes.create_string_buffer((text + "\0").encode("utf-16-le"))
        r.FPDFText_SetText(obj, ctypes.cast(buf, r.FPDF_WIDESTRING))
        r.FPDFPageObj_SetFillColor(obj, 60, 60, 60, 255)
        r.FPDFPageObj_Transform(obj, 1, 0, 0, 1, x, y)
    else:
        return
    r.FPDFPageObj_Transform(obj, *to_phys)
    r.FPDFPage_InsertObject(page.raw, obj)


def flattened(doc):
    """Kopie, in der Formularwerte, Kommentare und Stempel eingebrannt sind (wie beim Druck aus Acrobat).

    Beim Ausschießen wird nur der Seiteninhalt übernommen – Anmerkungen (ausgefüllte Formularfelder,
    Kommentare, Stempel) lägen sonst nicht mit auf dem Blatt. Nur Anmerkungen, die laut PDF gedruckt werden
    sollen, kommen mit (FLAT_PRINT). Ohne Anmerkungen wird das Original unverändert zurückgegeben.
    """
    import io
    import pypdfium2 as pdfium
    import pypdfium2.raw as r
    has = False
    for i in range(len(doc)):
        pg = doc[i]
        n = r.FPDFPage_GetAnnotCount(pg.raw)
        pg.close()
        if n:
            has = True
            break
    if not has:
        return doc
    buf = io.BytesIO()
    doc.save(buf)
    cp = pdfium.PdfDocument(buf.getvalue())
    try:
        cp.init_forms()                 # erzeugt fehlende Feld-Darstellungen
    except Exception:
        pass
    for i in range(len(cp)):
        pg = cp[i]
        if r.FPDFPage_GetAnnotCount(pg.raw):
            r.FPDFPage_Flatten(pg.raw, r.FLAT_PRINT)
        pg.close()
    out = io.BytesIO()
    cp.save(out)
    cp.close()
    return pdfium.PdfDocument(out.getvalue())


def build_pdf(src, sheet: Sheet, pages: list[int], settings: LayoutSettings, path: str):
    sizes = [src.get_page_size(i) for i in range(len(src))]
    plans = plan(sizes, pages, sheet, settings)
    doc = impose_with(src, sheet, plans, settings)
    doc.save(path)
    doc.close()
    return plans
