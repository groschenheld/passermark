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
shapes = {}
for shape in ("contour", "rect", "heart"):
    # echte Standard-Einstellungen (der Qt-Ersatz liefert für Zahlenfelder nur Platzhalter)
    dlg._settings = lambda preview=False, shape=shape: cutcontour.CutSettings(shape=shape, dpi=100)
    dlg._preview()
    shapes[shape] = [tuple(round(v, 1) for pt in p for v in pt)[:12] for p in dlg.canvas.paths]
assert len(ran) == 4 and ran[1:] == ["contour", "rect", "heart"], ran      # 1x beim Öffnen + 3 Formen
assert shapes["contour"] != shapes["rect"] != shapes["heart"], "Vorschau ändert sich nicht mit der Form"
assert all(len(v) == 3 for v in shapes.values()), {k: len(v) for k, v in shapes.items()}
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
