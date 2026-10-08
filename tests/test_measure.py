# SPDX-License-Identifier: GPL-3.0-or-later
"""Lineal und Messen: Einrasten, Längen, Bildschirmachsen bei Zoom/Drehung, Linealteilung."""
import math, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pdfdruck import measure as m

MM = 72 / 25.4


def test_snap():
    assert m.snap(100, 3) == (100.0, 0.0) or abs(m.snap(100, 3)[1]) < 1e-9          # fast waagrecht -> waagrecht
    x, y = m.snap(4, -90)
    assert abs(x) < 1e-9 and y < 0                                                   # fast senkrecht -> senkrecht
    x, y = m.snap(50, 47)
    assert abs(x - y) < 1e-9                                                        # fast diagonal -> 45°
    x, y = m.snap(100, 40)                                                          # 21,8° -> noch waagrecht
    assert abs(y) < 1e-9
    x, y = m.snap(100, 43)                                                          # 23,3° -> schon 45°
    assert abs(x - y) < 1e-9
    assert m.snap(10, 7, enabled=False) == (10, 7)


def test_measure_lengths_and_axes():
    zoom = 2.0
    M0 = (zoom, 0.0, 0.0, -zoom)                       # keine Drehung: Seiten-y nach oben = Bildschirm-y nach unten
    r = m.measure((0, 0), (100 * MM, 0), M0)
    assert abs(r.length_mm - 100) < 1e-6 and abs(r.dx_mm - 100) < 1e-6 and abs(r.dy_mm) < 1e-6 and abs(r.angle_deg) < 1e-6
    r = m.measure((0, 0), (30 * MM, 40 * MM), M0)
    assert abs(r.length_mm - 50) < 1e-6 and abs(r.dy_mm - 40) < 1e-6 and abs(r.angle_deg - math.degrees(math.atan2(40, 30))) < 1e-6
    M90 = (0.0, zoom, zoom, 0.0)                       # Ansicht 90° gedreht: Seiten-x zeigt nach unten
    r = m.measure((0, 0), (100 * MM, 0), M90)
    assert abs(r.length_mm - 100) < 1e-6 and abs(r.dx_mm) < 1e-6 and abs(r.dy_mm + 100) < 1e-6   # am Bildschirm senkrecht


def test_ruler_steps():
    for ppm in (0.3, 1, 3.78, 10, 40):
        minor, major = m.ruler_steps(ppm)
        assert minor * ppm >= 6 or minor == m.STEPS_MM[-1]
        assert major * ppm >= 50 or major == m.STEPS_MM[-1]
        assert abs(major / minor - round(major / minor)) < 1e-9


def test_format():
    assert m.fmt(12.345, "de") == "12,3" and m.fmt(12.345, "en") == "12.3"
    assert m.fmt(-0.01, "de") == "0,0"
    assert "mm" in m.describe(m.Measurement(10, 6, 8, 53.1), "de")


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("ok", k)
