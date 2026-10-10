# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Ruler and measuring – pure computation logic (no GUI, therefore precisely testable).

Coordinates: "page" = PDF points (1/72 inch, y up); "screen" = pixels of the page view (y down).
The page -> screen conversion (including zoom and rotation) is passed as a linear map `M`:
M = (a, b, c, d) with  px_x = a*dx + c*dy,  px_y = b*dx + d*dy  for a page vector (dx, dy).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

MM_PER_PT = 25.4 / 72.0
STEPS_MM = [0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000]


def snap(dx: float, dy: float, enabled: bool = True) -> tuple[float, float]:
    """Snap the screen vector to horizontal / vertical / 45° (nearest direction; the boundary at 22.5° each).
        The length along the snapped direction is the projection of the mouse path.
    """
    if not enabled or (dx == 0 and dy == 0):
        return dx, dy
    step = math.pi / 4
    ang = round(math.atan2(dy, dx) / step) * step
    ux, uy = math.cos(ang), math.sin(ang)
    length = dx * ux + dy * uy
    return length * ux, length * uy


@dataclass
class Measurement:
    length_mm: float
    dx_mm: float          # waagrecht am Bildschirm (+ rechts)
    dy_mm: float          # senkrecht am Bildschirm (+ oben)
    angle_deg: float      # gegen den Uhrzeigersinn ab waagrecht rechts, -180 … 180


def measure(a: tuple, b: tuple, M: tuple) -> Measurement:
    """Messung zwischen zwei Seitenpunkten; ΔX/ΔY/Winkel so, wie man es am Bildschirm sieht (auch bei Drehung)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length_mm = math.hypot(dx, dy) * MM_PER_PT
    ma, mb, mc, md = M
    vx, vy = ma * dx + mc * dy, mb * dx + md * dy           # Bildschirmvektor (Pixel, y nach unten)
    s = math.sqrt(abs(ma * md - mb * mc)) or 1.0           # Pixel je Punkt (Zoom)
    sx, sy = vx / s * MM_PER_PT, -vy / s * MM_PER_PT       # Bildschirmachsen in mm (y nach oben)
    angle = math.degrees(math.atan2(sy, sx)) if length_mm > 0 else 0.0
    return Measurement(length_mm, sx, sy, angle)


def ruler_steps(px_per_mm: float) -> tuple[float, float]:
    """(kleiner Strich, beschrifteter Strich) in mm – so, dass Striche ≥ 6 px und Beschriftungen ≥ 50 px auseinander."""
    minor = next((s for s in STEPS_MM if s * px_per_mm >= 6), STEPS_MM[-1])
    major = next((s for s in STEPS_MM if s * px_per_mm >= 50 and s >= minor and
                  abs(s / minor - round(s / minor)) < 1e-9), STEPS_MM[-1])
    return minor, major


def fmt(v: float, lang: str = "de", digits: int = 1) -> str:
    """Zahl mit Komma (de, hu, es, fr) bzw. Punkt (en)."""
    if abs(v) < 0.5 * 10 ** (-digits):
        v = 0.0                                    # kein „-0,0“
    t = f"{v:.{digits}f}"
    return t if lang == "en" else t.replace(".", ",")


def describe(m: Measurement, lang: str = "de") -> str:
    """Short text for the status bar."""
    return (f"↔ {fmt(m.length_mm, lang)} mm   ΔX {fmt(m.dx_mm, lang)}   ΔY {fmt(m.dy_mm, lang)}   "
            f"{fmt(m.angle_deg, lang)}°")


def describe_pos(x_mm: float, y_mm: float, lang: str = "de") -> str:
    return f"X {fmt(x_mm, lang)}   Y {fmt(y_mm, lang)} mm"
