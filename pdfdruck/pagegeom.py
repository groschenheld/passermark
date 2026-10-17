# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Seite <-> Bildschirm ohne die Seite zu laden: pdfiums CPDF_Page::GetDisplayMatrix nachgebaut.

Für die Seitenansicht: Mauskoordinaten, Rahmen, Auswahl – bisher hat dafür jede Seite im Programm geladen
werden müssen (bei Vektor-lastigen Seiten bis über eine Sekunde). Gebraucht werden nur CropBox (∩ MediaBox)
und /Rotate der Seite (renderproc.page_info). Geprüft gegen FPDF_PageToDevice (tests/test_pagegeom.py).
"""
from __future__ import annotations


def display_matrix(info: dict, width: float, height: float, view_rotation: int = 0):
    """(a, b, c, d, e, f) mit x' = a x + c y + e, y' = b x + d y + f  (Seite pt -> Gerätepixel) oder None.
        info: {"crop": (x0, y0, x1, y1), "rotate": 0..3}; view_rotation in Grad (0/90/180/270)."""
    x0, y0, x1, y1 = info["crop"]
    pr = int(info.get("rotate", 0)) % 4
    if pr == 1:
        pm, pw, ph = (0, -1, 1, 0, -y0, x1), y1 - y0, x1 - x0
    elif pr == 2:
        pm, pw, ph = (-1, 0, 0, -1, x1, y1), x1 - x0, y1 - y0
    elif pr == 3:
        pm, pw, ph = (0, 1, -1, 0, y1, -x0), y1 - y0, x1 - x0
    else:
        pm, pw, ph = (1, 0, 0, 1, -x0, -y0), x1 - x0, y1 - y0
    if pw <= 0 or ph <= 0:
        return None
    L, T, R, B = 0, 0, width, height
    r = (int(view_rotation) // 90) % 4
    X0, Y0, X1, Y1, X2, Y2 = ((L, B, L, T, R, B), (L, T, R, T, L, B), (R, T, R, B, L, T), (R, B, L, B, R, T))[r]
    m = ((X2 - X0) / pw, (Y2 - Y0) / pw, (X1 - X0) / ph, (Y1 - Y0) / ph, X0, Y0)
    a, b, c, d, e, f = pm
    return (a * m[0] + b * m[2], a * m[1] + b * m[3], c * m[0] + d * m[2], c * m[1] + d * m[3],
            e * m[0] + f * m[2] + m[4], e * m[1] + f * m[3] + m[5])


def to_device(m, x: float, y: float):
    a, b, c, d, e, f = m
    return a * x + c * y + e, b * x + d * y + f


def to_page(m, dx: float, dy: float):
    a, b, c, d, e, f = m
    det = a * d - b * c
    if abs(det) < 1e-12:
        return None
    px, py = dx - e, dy - f
    return (d * px - c * py) / det, (-b * px + a * py) / det
