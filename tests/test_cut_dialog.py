# SPDX-License-Identifier: GPL-3.0-or-later
"""CutContour-Dialog ohne Bildschirm (Qt-Ersatz): Formwechsel ändert die Vorschau; Berechnung läuft im Worker."""
import os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

SCRIPT = r'''
import sys
sys.path.insert(0, sys.argv[1])
from pdfdruck.gui import objectsdialog as od
import test_cutcontour as tc
ran = []
def sync_start(self):           # Worker im Test sofort ausführen (Qt-Ersatz startet keine Threads)
    ran.append(self.s.shape)
    self.run()
od._CutWorker.start = sync_start
od._CutWorker.isRunning = lambda self: False
od.QDialog.done = lambda self, r: None       # Qt-Ersatz: Basismethode bereitstellen
dlg = od.CutContourDialog(None, tc.stickers(), 0)
from pdfdruck import cutcontour
def run(shape, single=True):
    # echte Standard-Einstellungen (der Qt-Ersatz liefert für Zahlenfelder nur Platzhalter)
    dlg._settings = lambda preview=False: cutcontour.CutSettings(shape=shape, single_shape=single, dpi=100)
    dlg.cmb_shape.currentData = lambda: shape
    dlg._preview()
    return [tuple(round(v, 1) for pt in p for v in pt)[:12] for p in dlg.canvas.paths]
shapes = {sh: run(sh) for sh in ("contour", "rect", "heart")}
assert len(ran) == 4 and ran[1:] == ["contour", "rect", "heart"], ran      # 1x beim Öffnen + 3 Formen
assert shapes["contour"] != shapes["rect"] != shapes["heart"], "Vorschau ändert sich nicht mit der Form"
assert len(shapes["contour"]) == 3, len(shapes["contour"])                 # Kontur: je Aufkleber
assert len(shapes["rect"]) == 1 and len(shapes["heart"]) == 1, (len(shapes["rect"]), len(shapes["heart"]))
assert len(run("rect", single=False)) == 3                                 # Option: eine Form je Objekt
# Griffe: Ecke = gleichmäßig, Seite = nur Breite, Verschiebe-Griff = Versatz; Felder bekommen mm-Werte
run("rect")
class P:
    def __init__(s, x, y): s._x, s._y = x, y
    def x(s): return s._x
    def y(s): return s._y
class E:
    def __init__(s, x, y): s.p = P(x, y)
    def position(s): return s.p
    def button(s): return od.Qt.MouseButton.LeftButton
od.QPointF = lambda x, y: P(x, y)
od.QRectF = lambda *a: None
cv = dlg.canvas
cv._geom = lambda: (1.0, 0.0, 0.0)                 # 1 px = 1 pt
cv.page_h = 1000.0
x0, y0, x1, y1 = cv.shape_box
assert cv.shape_box is not None
got = []
cv.on_shape = lambda *v: got.append(v)
def drag(name, ddx, ddy):
    h = cv._handles()[name]
    cv.mousePressEvent(E(h.x(), h.y()))
    c = cv.to_widget((x0 + x1) / 2, (y0 + y1) / 2)
    if name.startswith("c") or name.startswith("s"):
        tx, ty = c.x() + (h.x() - c.x()) * ddx, c.y() + (h.y() - c.y()) * ddy
    else:
        tx, ty = h.x() + ddx, h.y() + ddy
    cv.mouseMoveEvent(E(tx, ty)); cv.mouseReleaseEvent(E(tx, ty))
    cv.live = (1.0, 1.0, 0.0, 0.0)
    return got[-1]
sx, sy, dx, dy = drag("c11", 2, 2)
assert abs(sx - 2) < 1e-6 and abs(sy - 2) < 1e-6 and dx == 0 and dy == 0, (sx, sy, dx, dy)
sx, sy, dx, dy = drag("sx1", 2, 1)
assert abs(sx - 2) < 1e-6 and sy == 1.0, (sx, sy)
sx, sy, dx, dy = drag("move", 30, -20)
assert sx == sy == 1.0 and abs(dx - 30) < 1e-6 and abs(dy - 20) < 1e-6, (dx, dy)   # Bildschirm-y nach unten = Seite nach oben
# Übernahme in die Felder (mm)
class Spin:
    def __init__(s, v=0.0): s.v = v
    def value(s): return s.v
    def setValue(s, v): s.v = v
    def minimum(s): return -2000.0
    def maximum(s): return 2000.0
    def blockSignals(s, b): pass
dlg.spn_fw, dlg.spn_fh, dlg.spn_sx, dlg.spn_sy = Spin(), Spin(), Spin(5.0), Spin()
MM = 72 / 25.4
bw, bh = (x1 - x0) / MM, (y1 - y0) / MM
dlg._apply_drag(1.5, 1.0, 10 * MM, -4 * MM)
assert abs(dlg.spn_fw.v - round(bw * 1.5, 1)) < 0.11 and abs(dlg.spn_fh.v - round(bh, 1)) < 0.11, (dlg.spn_fw.v, bw)
assert abs(dlg.spn_sx.v - 15.0) < 0.01 and abs(dlg.spn_sy.v + 4.0) < 0.01, (dlg.spn_sx.v, dlg.spn_sy.v)
# danach eingetippte Größe wirkt direkt (kein versteckter Prozentfaktor mehr)
dlg._settings = lambda preview=False: cutcontour.CutSettings(shape="rect", width_mm=100, height_mm=40, dpi=100)
dlg._preview()
bb = dlg.canvas.shape_box
assert abs((bb[2] - bb[0]) / MM - 100) < 0.6 and abs((bb[3] - bb[1]) / MM - 40) < 0.6, bb
run("contour")
assert dlg.canvas.shape_box is None                                        # Kontur: keine Griffe
dlg.done(0)
print("CUT-DIALOG-OK")
'''


def test_shape_changes_preview_in_worker():
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.join(HERE, "_qtstub"), ROOT, HERE]),
               HOME="/tmp/_smoke_home", PASSERMARK_LANG="de")
    os.makedirs("/tmp/_smoke_home", exist_ok=True)
    r = subprocess.run([sys.executable, "-c", SCRIPT, ROOT], capture_output=True, text=True, env=env, timeout=600)
    assert "CUT-DIALOG-OK" in r.stdout, r.stdout[-2000:] + r.stderr[-3000:]


if __name__ == "__main__":
    test_shape_changes_preview_in_worker(); print("ok test_shape_changes_preview_in_worker")
