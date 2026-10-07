# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Automatische Fachwahl: Format (+ Grammatur) -> erste passende, nicht leere Lade.

Grundlage ist die vom Admin hinterlegte Belegung (Reihenfolge = Vorrang). Optional liefert der Drucker
per IPP live, welche Lade leer ist; leere Laden werden übersprungen. Ohne Live-Daten gilt die Reihenfolge.
"""
from __future__ import annotations

from .l10n import tr

import re
import time
from dataclasses import dataclass

LIVE_CACHE_S = 20


@dataclass
class Tray:
    slot: str            # Treiberwert der Lade (InputSlot / Windows-Fach-ID)
    size: str            # Treiberwert des Formats (PageSize / Windows-Papier-ID)
    weight: int = 0      # g/m², 0 = nicht angegeben
    media: str = ""      # Treiberwert Medientyp ("" = nicht setzen)
    ipp: str = ""        # Ladenname am Gerät (IPP media-source), für Füllstand

    @classmethod
    def from_dict(cls, d: dict) -> "Tray":
        return cls(str(d.get("slot", "")), str(d.get("size", "")), int(d.get("weight", 0) or 0),
                   str(d.get("media", "") or ""), str(d.get("ipp", "") or ""))

    def to_dict(self) -> dict:
        return {"slot": self.slot, "size": self.size, "weight": self.weight, "media": self.media, "ipp": self.ipp}


@dataclass
class Pick:
    tray: Tray | None
    note: str = ""
    warn: bool = False


def trays_of(pc: dict) -> list[Tray]:
    return [Tray.from_dict(d) for d in (pc or {}).get("trays", []) if d.get("slot") and d.get("size")]


def weights_of(pc: dict, size: str | None = None) -> list[int]:
    return sorted({t.weight for t in trays_of(pc) if t.weight and (size is None or t.size == size)})


def pick(trays: list[Tray], size: str, weight: int = 0, live=None, labels: dict | None = None) -> Pick:
    """Erste Lade mit passendem Format (und Grammatur), die laut Gerät nicht leer ist."""
    lab = (labels or {}).get
    same = [t for t in trays if t.size == size]
    if not same:
        return Pick(None, tr("Format ist in keiner Lade hinterlegt – Fach bitte manuell wählen."), warn=True)
    if weight:
        cands = [t for t in same if t.weight == weight] or [t for t in same if not t.weight]
        if not cands:
            have = ", ".join(f"{w} g" for w in sorted({t.weight for t in same if t.weight}))
            return Pick(None, tr("Keine Lade mit {0} g/m² in diesem Format (geladen: {1}).").format(weight, have), warn=True)
    else:
        cands = same
    skipped = []
    for t in cands:
        st = live.trays.get(t.ipp) if (live is not None and t.ipp) else None
        if st is not None and st.empty:
            skipped.append(lab(t.slot, t.slot))
            continue
        note = ""
        if skipped:
            note = tr("{0} leer – nehme {1}.").format(', '.join(skipped), lab(t.slot, t.slot))
        if st is not None and st.size_mm and st.weight and weight and st.weight != weight:
            note += tr(" Achtung: Gerät meldet {0} g in {1}.").format(st.weight, lab(t.slot, t.slot))
        return Pick(t, note.strip(), warn=bool(note and "Achtung" in note))
    first = cands[0]
    return Pick(first, tr("Alle passenden Laden laut Gerät leer – bitte {0} nachfüllen.").format(lab(first.slot, first.slot)),
                warn=True)


# --------------------------------------------------------------------------- #
# Live-Status mit kurzem Zwischenspeicher
# --------------------------------------------------------------------------- #
_cache: dict = {}


def live_status(host: str, force: bool = False):
    from . import ipp
    if not host:
        return None
    hit = _cache.get(host)
    if hit and not force and time.time() - hit[0] < LIVE_CACHE_S:
        return hit[1]
    st = ipp.query(host, timeout=3.0)
    st = None if st.error else st
    _cache[host] = (time.time(), st)
    return st


# --------------------------------------------------------------------------- #
# Hilfen für „Vom Gerät lesen“ (Admin)
# --------------------------------------------------------------------------- #
def size_for_mm(caps, mm: tuple) -> str | None:
    """Treiberwert des Papierformats mit diesen Maßen (±2 mm, randlose Varianten nachrangig)."""
    if not mm:
        return None
    w, h = sorted(mm)
    best = None
    for val, (pw, ph) in caps.page_sizes.items():
        a, b = sorted((pw * 25.4 / 72, ph * 25.4 / 72))
        if abs(a - w) <= 2 and abs(b - h) <= 2:
            borderless = bool(re.search(r"borderless|randlos|full|^T[A-Z0-9]", val, re.I))
            score = (borderless, len(val))
            if best is None or score < best[0]:
                best = (score, val)
    return best[1] if best else None


def slot_for_source(caps, source: str) -> str | None:
    """IPP-Ladenname (tray-1, by-pass-tray, main …) -> Treiberwert der Lade."""
    key = caps.roles.get("source")
    if not key or key not in caps.options:
        return None
    choices = caps.options[key].choices
    s = source.lower()
    m = re.search(r"(\d+)", s)
    if m:
        n = m.group(1)
        for c in choices:
            hay = f"{c.value} {c.text}".lower()
            if re.search(rf"(?<!\d){n}(?!\d)", hay) and not re.search(r"auto", hay):
                return c.value
    if re.search(r"by-?pass|manual|multi", s):
        for c in choices:
            if re.search(r"manual|bypass|mehrzweck|mp|multi", f"{c.value} {c.text}", re.I):
                return c.value
    if s in ("main", "top"):
        for c in choices:
            if re.search(r"main|haupt|cassette$|kassette$", f"{c.value} {c.text}", re.I):
                return c.value
    for c in choices:
        if c.value.lower() == s:
            return c.value
    return None
