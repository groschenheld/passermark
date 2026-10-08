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
# Form mit der Maus ziehen: doppelter Abstand zur Mitte = Faktor 2, live angezeigt, beim Loslassen übernommen
run("rect")
class P:
    def __init__(s, x, y): s._x, s._y = x, y
    def x(s): return s._x
    def y(s): return s._y
class E:
    def __init__(s, x, y): s.p = P(x, y)
    def position(s): return s.p
    def button(s): return od.Qt.MouseButton.LeftButton
cv = dlg.canvas
cv.to_widget = lambda x, y: P(x, y)
cx, cy = cv.scale_center
got, live = [], []
cv.on_scale, cv.on_scaling = got.append, live.append
cv.mousePressEvent(E(cx + 40, cy)); cv.mouseMoveEvent(E(cx + 80, cy)); cv.mouseReleaseEvent(E(cx + 80, cy))
assert live and abs(live[-1] - 2.0) < 1e-6 and got == [2.0], (live, got)
cv.mousePressEvent(E(cx + 40, cy)); cv.mouseMoveEvent(E(cx + 20, cy)); cv.mouseReleaseEvent(E(cx + 20, cy))
assert abs(got[-1] - 0.5) < 1e-6, got
run("contour")
assert dlg.canvas.scale_center is None                                     # Kontur: kein Ziehen
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
