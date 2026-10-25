# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Roland cutting plotters (CAMM-1 GS/GS2/GR/GX …) over the network (raw port 9100): loaded material width and
direct cut jobs in CAMM-GL III (HP-GL dialect). Standard library only.

    width:  "IN;OH;" – the device answers with its cutting area "x1,y1,x2,y2" (1 unit = 0.025 mm). With a roll,
            one axis is the loaded width, the other the length set on the device (often very long).
    cut:    "IN;VS<speed>;FS<force>;PU…;PD…;" – rectangles/polygons in mm, X = feed direction, Y = across.

Only for devices recognised as Roland (name/model) – a normal printer on port 9100 would print the text.
Printer-cutters (TrueVIS, VersaSTUDIO …) print through VersaWorks: Passermark hands them a PDF with the spot
colour CutContour (hot folder), VersaWorks adds its own crop marks.
"""
from __future__ import annotations

import re
import socket

UNIT_MM = 0.025
PORT = 9100
NAME = re.compile(r"roland|camm|\bgs2?-?24\b|\bgr2?-?\d|\bgx-?\d|stika|versa|truevis|bn-?20", re.I)


def is_roland(*texts) -> bool:
    return any(t and NAME.search(str(t)) for t in texts)


def _ask(host: str, data: bytes, port: int = PORT, timeout: float = 3.0) -> bytes:
    with socket.create_connection((host, port), timeout=timeout) as s:
        s.settimeout(timeout)
        s.sendall(data)
        buf = b""
        while not buf.endswith(b"\r") and len(buf) < 256:
            try:
                chunk = s.recv(64)
            except socket.timeout:
                break
            if not chunk:
                break
            buf += chunk
        return buf


def parse_hardclip(raw: bytes) -> dict | None:
    nums = [int(x) for x in re.findall(rb"-?\d+", raw or b"")[:4]]
    if len(nums) < 4:
        return None
    x1, y1, x2, y2 = nums
    dx, dy = abs(x2 - x1) * UNIT_MM, abs(y2 - y1) * UNIT_MM
    return {"x_mm": round(dx, 1), "y_mm": round(dy, 1), "width_mm": round(dy, 1), "length_mm": round(dx, 1),
            "raw": raw.decode("latin-1", "replace").strip()}


def query(host: str, port: int = PORT, timeout: float = 3.0) -> dict:
    """Schneidbereich des Geräts: {"width_mm", "length_mm", "raw"} – Breite = quer zur Vorschubrichtung."""
    raw = _ask(host, b"IN;OH;", port, timeout)
    d = parse_hardclip(raw)
    if d is None:
        raise OSError(f"Roland: keine Antwort auf OH ({raw!r})")
    return d


def hpgl(paths_mm: list, force: int = 0, speed: int = 0) -> bytes:
    """Schneidauftrag: [[(x, y), …], …] in mm (x = quer, y = Vorschub) -> CAMM-GL III."""
    out = ["IN"]
    if speed:
        out.append(f"VS{int(speed)}")
    if force:
        out.append(f"FS{int(force)}")
    for poly in paths_mm:
        if len(poly) < 2:
            continue
        pts = [(round(y / UNIT_MM), round(x / UNIT_MM)) for x, y in poly]   # Gerät: X = Vorschub, Y = quer
        out.append("PU{0},{1}".format(*pts[0]))
        out.append("PD" + ",".join(f"{a},{b}" for a, b in pts[1:]))
    out.append("PU0,0")
    return (";".join(out) + ";").encode("ascii")


def rect_paths(rects_mm: list) -> list:
    """Rechtecke (x0, y0, x1, y1) mm -> geschlossene Pfade."""
    return [[(a, b), (c, b), (c, d), (a, d), (a, b)] for a, b, c, d in rects_mm]


def send(host: str, data: bytes, port: int = PORT, timeout: float = 10.0) -> None:
    with socket.create_connection((host, port), timeout=timeout) as s:
        s.sendall(data)
