# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Paper sizes in ONE place (mm, portrait) – no Qt.

    PAPER_MM   names as printer drivers use them (PPD keywords, upper case). Only the fallback when the driver
               does not state the size itself – the printer's own figures always come first (printers.py).
               "B4"/"B5"/"B6" are JIS sizes here (PPD convention), ISO B is "ISOB4" …
    UI_FORMATS the formats offered in dialogs (crop target, page size display) – ISO meaning, display names.
    size_from_text  sizes written in a name or display text: "100 x 148 mm", "4 x 6 in", "Custom.225x320mm".
"""
from __future__ import annotations

import re

PT = 72.0 / 25.4                  # pt per mm

_A = [(841, 1189), (594, 841), (420, 594), (297, 420), (210, 297), (148, 210), (105, 148), (74, 105), (52, 74),
      (37, 52), (26, 37)]
_B = [(1000, 1414), (707, 1000), (500, 707), (353, 500), (250, 353), (176, 250), (125, 176), (88, 125), (62, 88),
      (44, 62), (31, 44)]
_C = [(917, 1297), (648, 917), (458, 648), (324, 458), (229, 324), (162, 229), (114, 162), (81, 114), (57, 81),
      (40, 57), (28, 40)]
_JISB = [(1030, 1456), (728, 1030), (515, 728), (364, 515), (257, 364), (182, 257), (128, 182), (91, 128),
         (64, 91), (45, 64), (32, 45)]
_SRA = [(900, 1280), (640, 900), (450, 640), (320, 450), (225, 320)]
_RA = [(860, 1220), (610, 860), (430, 610), (305, 430), (215, 305)]

PAPER_MM: dict[str, tuple[float, float]] = {}
for _i in range(11):
    PAPER_MM[f"A{_i}"] = _A[_i]
    PAPER_MM[f"ISOB{_i}"] = _B[_i]
    PAPER_MM[f"B{_i}"] = _JISB[_i]                 # PPD: B4 = JIS B4
    PAPER_MM[f"JISB{_i}"] = _JISB[_i]
    PAPER_MM[f"C{_i}"] = _C[_i]
    PAPER_MM[f"ENVC{_i}"] = _C[_i]
for _i in range(5):
    PAPER_MM[f"SRA{_i}"] = _SRA[_i]
    PAPER_MM[f"RA{_i}"] = _RA[_i]
PAPER_MM.update({
    "A3+": (329, 483), "A3PLUS": (329, 483), "SUPERB": (329, 483), "SUPERA3": (329, 483),
    "LETTER": (215.9, 279.4), "LEGAL": (215.9, 355.6), "TABLOID": (279.4, 431.8), "LEDGER": (279.4, 431.8),
    "EXECUTIVE": (184.2, 266.7), "STATEMENT": (139.7, 215.9), "FOLIO": (215.9, 330.2),
    "4X6": (101.6, 152.4), "4X6FULL": (101.6, 152.4), "4X7": (101.6, 177.8), "5X7": (127, 177.8),
    "8X10": (203.2, 254), "2L": (127, 178), "L": (89, 127), "INDEX5": (127, 203.2), "INDEX4X6": (101.6, 152.4),
    "POSTCARD": (100, 148), "ENV10": (104.8, 241.3), "ENVDL": (110, 220), "DL": (110, 220),
    "ENVC4P": (229, 324), "ENVMONARCH": (98.4, 190.5), "8K": (270, 390), "16K": (195, 270),
})

# Dialogs (ISO meaning: B4 = ISO B4, DL = DIN lang flyer 99 × 210) – order as shown
UI_FORMATS: dict[str, tuple[float, float]] = {
    "A0": _A[0], "A1": _A[1], "A2": _A[2], "A3": _A[3], "A4": _A[4], "A5": _A[5], "A6": _A[6], "A7": _A[7],
    "B4": _B[4], "B5": _B[5], "C4": _C[4], "C5": _C[5], "C6": _C[6], "DL": (99, 210),
    "SRA4": _SRA[4], "SRA3": _SRA[3], "SRA2": _SRA[2], "A3+": (329, 483),
    "Letter": (215.9, 279.4), "Legal": (215.9, 355.6), "Tabloid": (279.4, 431.8),
}

_UNIT = {"mm": 1.0, "cm": 10.0, "in": 25.4, '"': 25.4, "inch": 25.4, "zoll": 25.4}
_TEXT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*[x×*]\s*(\d+(?:[.,]\d+)?)\s*(mm|cm|inch|in|zoll|\")(?![a-z])", re.I)
_CUSTOM_RE = re.compile(r"(?:custom\.)?(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)(mm|cm|in)?$", re.I)


def _num(t: str) -> float:
    return float(t.replace(",", "."))


def size_from_text(text: str) -> tuple[float, float] | None:
    """(w, h) in pt from a size written in a name or display text – the first one counts:
        "10 x 15 cm (4 x 6 in)" -> 10 × 15 cm, "8K 270 x 390 mm", "5 x 8 in (127 x 203 mm)", "Custom.225x320mm"."""
    if not text:
        return None
    t = re.sub(r"<([0-9A-Fa-f]{2})>", lambda m: chr(int(m.group(1), 16)), str(text)).strip()   # PPD: <2E> = "."
    m = _CUSTOM_RE.fullmatch(t)
    if m and (m.group(3) or t.lower().startswith("custom.")):   # „4X7“ allein ist ein Name, keine Größe
        f = _UNIT.get((m.group(3) or "").lower())
        if f is None:                               # Custom.WxH ohne Einheit: pt (CUPS)
            return float(m.group(1)), float(m.group(2))
        return float(m.group(1)) * f * PT, float(m.group(2)) * f * PT
    m = _TEXT_RE.search(t)
    if not m:
        return None
    f = _UNIT[m.group(3).lower()]
    w, h = _num(m.group(1)) * f, _num(m.group(2)) * f
    if w <= 0 or h <= 0:
        return None
    return w * PT, h * PT


def lookup(name: str) -> tuple[float, float] | None:
    """Table size (mm) for a driver name – exact, or ignoring blanks/dashes/'DIN'/'ISO' ("DIN A4", "SRA-3")."""
    if not name:
        return None
    n = str(name).upper().replace("DIN", "").replace(" ", "").replace("-", "").replace("_", "")
    return PAPER_MM.get(n) or PAPER_MM.get(n.replace("ISO", "")) if n else None
