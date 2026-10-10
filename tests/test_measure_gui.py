# SPDX-License-Identifier: GPL-3.0-or-later
"""Messen in der Seitenansicht ohne Bildschirm (Qt-Ersatz): Klick 1/2, Umschalt-Einrasten, Anzeige, Esc."""
import os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

SCRIPT = r'''
import sys, types
from pdfdruck.gui import viewer
viewer.PageView._dpi_scale = lambda self: 1.0
viewer.PageView.page_zoom = lambda self, i: 1.0
viewer.Qt.KeyboardModifier = types.SimpleNamespace(ShiftModifier=1, ControlModifier=2)
viewer.Qt.Key = types.SimpleNamespace(Key_Escape=27, Key_PageDown=-1, Key_Space=-2, Key_PageUp=-3, Key_Down=-4, Key_Up=-5)
from pdfdruck import config
from pdfdruck.gui.common import Session
import pypdfium2 as pdfium
from reportlab.pdfgen import canvas
c = canvas.Canvas("/tmp/_a4.pdf"); c.drawString(100, 700, "x"); c.showPage(); c.save()
w = viewer.MainWindow(types.SimpleNamespace(view_single=True, session=Session(config.BUILTIN), windows=[]))
w._set_doc(pdfium.PdfDocument("/tmp/_a4.pdf"), "/tmp/_a4.pdf", "a4.pdf", False)
out = []
w.view.on_measure = out.append
w._measure_mode(True)
assert w.view.imode == "measure"
pg = w.view.pages[0]; pg.width = lambda: 595; pg.height = lambda: 842
class P:
    def __init__(s, x, y): s._x, s._y = x, y
    def x(s): return s._x
    def y(s): return s._y
    def toPoint(s): return s
class E:
    def __init__(s, x, y, mod=0, key=None): s.p, s.m, s.k = P(x, y), mod, key
    def position(s): return s.p
    def button(s): return viewer.Qt.MouseButton.LeftButton
    def modifiers(s): return s.m
    def key(s): return s.k
viewer.QPointF = lambda x, y: P(x, y)            # Qt-Ersatz: echter Punkt statt Platzhalter
def strecke(a, b, shift=0):
    w.view.mouse_press(pg, E(*a)); w.view.mouse_move(pg, E(*b, mod=shift)); w.view.mouse_press(pg, E(*b, mod=shift))
    return w.view.meas, out[-1]
m, txt = strecke((100, 100), (400, 500))
print("3-4-5:", txt)
import re
def nums(t):
    return [float(x.replace(",", ".")) for x in re.findall(r"-?\d+,\d", t)]
L, dx, dy, ang = nums(txt)
assert abs(L - 176.4) <= 0.2 and abs(dx - 105.8) <= 0.2 and abs(dy + 141.1) <= 0.2 and abs(ang + 53.1) <= 0.2, txt   # Klickgenauigkeit 1 px
m, txt = strecke((100, 100), (400, 112), shift=1)
print("waagrecht:", txt)
assert abs(m["a"][1] - m["b"][1]) < 0.01 and abs(nums(txt)[2]) <= 0.05 and abs(nums(txt)[3]) <= 0.05, (m, txt)
m, txt = strecke((100, 100), (300, 290), shift=1)
print("45 Grad:", txt)
assert abs(abs(m["b"][0] - m["a"][0]) - abs(m["b"][1] - m["a"][1])) < 0.01 and abs(nums(txt)[3] + 45) <= 0.05, (m, txt)
m, txt = strecke((100, 100), (110, 400), shift=1)
print("senkrecht:", txt)
assert abs(m["a"][0] - m["b"][0]) < 0.01 and abs(nums(txt)[1]) <= 0.05, (m, txt)
w._show_rulers(True)
w._rulers_cursor(pg, P(50, 50))
w.ruler_h.paintEvent(None); w.ruler_v.paintEvent(None)      # Lineale zeichnen ohne Fehler
w.view.keyPressEvent(E(0, 0, key=27))
assert w.view.meas is None and out[-1] == ""
w._measure_mode(False)
assert w.view.imode == "text"
print("MEASURE-GUI-OK")
'''


def test_measure_in_view():
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.join(HERE, "_qtstub"), ROOT, HERE]),
               HOME="/tmp/_smoke_home", PASSERMARK_LANG="de", PDFTOOLKIT_LANG="de")
    os.makedirs("/tmp/_smoke_home", exist_ok=True)
    r = subprocess.run([sys.executable, "-c", SCRIPT], capture_output=True, text=True, env=env, timeout=300)
    print(r.stdout)
    assert "MEASURE-GUI-OK" in r.stdout, r.stdout[-2000:] + r.stderr[-3000:]


if __name__ == "__main__":
    test_measure_in_view(); print("ok test_measure_in_view")
