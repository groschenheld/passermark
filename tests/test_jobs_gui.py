# SPDX-License-Identifier: GPL-3.0-or-later
"""Aufträge aus der Oberfläche (Qt-Ersatz, aber echte Hintergrundprozesse): Ergebnis, Abbrechen, Fehler."""
import os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

SCRIPT = r'''
import os, sys, tempfile, threading, time, types
from pdfdruck.gui import viewer, objectsdialog as od
viewer.PageView._dpi_scale = lambda self: 1.0      # Qt-Ersatz: kein Bildschirm -> feste Werte
viewer.PageView.page_zoom = lambda self, i: 1.0
from pdfdruck import config, core
from pdfdruck.gui.common import Session
import pypdfium2 as pdfium
import test_cutcontour as tc, test_cli as tcl
tmp = tempfile.mkdtemp(prefix="pm-guijob-")
class Ctl:
    def __init__(s):
        s.session, s.windows, s.view_single, s.made = Session(config.BUILTIN), [], True, []
    def cache_file(s, name):
        base, ext = os.path.splitext(name); p, i = os.path.join(tmp, name), 2
        while os.path.exists(p):
            p, i = os.path.join(tmp, f"{base}_{i}{ext}"), i + 1
        return p
    def new_window(s, tab_of=None):
        w = viewer.MainWindow(s); s.made.append(w); return w
ctl = Ctl()
tc.stickers().save(os.path.join(tmp, "bogen.pdf"))
w = viewer.MainWindow(ctl)
w._set_doc(pdfium.PdfDocument(os.path.join(tmp, "bogen.pdf")), os.path.join(tmp, "bogen.pdf"), "bogen.pdf", False)
msgs = []
w.statusBar = lambda: types.SimpleNamespace(addWidget=lambda x: None, removeWidget=lambda x: None,
                                             showMessage=lambda m, t=0: msgs.append(m))
boxes = []
viewer.QMessageBox = lambda *a, **k: types.SimpleNamespace(setDetailedText=lambda d: boxes.append(("details", d)),
                                                           exec=lambda: boxes.append(("box", a[2] if len(a) > 2 else "")))
viewer.QMessageBox.Icon = types.SimpleNamespace(Critical=0)

def run_sync(entry_index=-1):
    w._jobs[entry_index]["reader"].run()          # Qt-Ersatz startet keine Threads: Lese-Schleife direkt ausführen

# 1) Erfolg: Ergebnis in neuem Fenster, Eingabe-Kopie weg, Liste leer
w.start_job("cutcontour", {"shape": "rect", "single_shape": False}, None, suffix="_CutContour", title="CutContour",
            notes=lambda info: [f"{info.get('cuts')} Schnitte"])
src = w._jobs[-1]["src"]; dst = w._jobs[-1]["dst"]
run_sync()
assert not w._jobs and not os.path.exists(src), (w._jobs, src)
res_win = ctl.made[-1]
assert len(res_win.doc) == 1 and res_win._temp_path == dst and os.path.exists(dst)
print("Erfolg ok:", os.path.basename(dst))

# 2) Abbrechen mitten in der Rechnung
w2 = viewer.MainWindow(ctl); w2.statusBar = w.statusBar
slow = tcl._slow_input()
w2._set_doc(pdfium.PdfDocument(slow), slow, "slow.pdf", False)
w2.start_job("cutcontour", {}, None, suffix="_CutContour", title="CutContour")
entry = w2._jobs[-1]
t = threading.Thread(target=entry["reader"].run); t.start()
time.sleep(1.5)
w2._cancel_job(entry); t.join(120)
assert not w2._jobs and msgs and msgs[-1] == "Abgebrochen." and not os.path.exists(entry["dst"]), msgs[-1:]
assert not os.path.exists(entry["src"])
print("Abbrechen ok")

# 3) Fehler: Meldung, reservierte Ausgabe entfernt
w.start_job("separate", {"detect": {"min_size_mm": 5000}}, None, suffix="_einzeln", title="Objekte trennen")
entry = w._jobs[-1]; run_sync()
assert boxes and boxes[-1][0] == "box" and not os.path.exists(entry["dst"]), boxes
print("Fehler ok:", boxes[-1][1])

# 4) Dialoge beschreiben nur noch den Auftrag
od.QDialog.done = lambda self, r: None
dlg = od.CutContourDialog(None, pdfium.PdfDocument(os.path.join(tmp, "bogen.pdf")), 0)
dlg._settings = lambda preview=False: core.settings_from_dict(__import__("pdfdruck.cutcontour", fromlist=["x"]).CutSettings, {"shape": "heart"})
dlg.chk_all = types.SimpleNamespace(isChecked=lambda: False)
dlg.accept = lambda: None
dlg._apply()
assert dlg.job[0] == "cutcontour" and dlg.job[1]["shape"] == "heart" and dlg.job[2] == [0], dlg.job
from pdfdruck.objects import Box
sd = od.SeparateDialog.__new__(od.SeparateDialog)      # ohne Erkennung beim Öffnen (Qt-Ersatz hat keine Werte)
sd.page, sd.boxes = 0, {}
sd.canvas = types.SimpleNamespace(boxes=[Box(0, 0, 100, 100)])
sd.w = {"margin": types.SimpleNamespace(value=lambda: 2.0)}; sd.accept = lambda: None
sd._apply()
assert sd.job == ("separate", {"margin_mm": 2.0, "boxes": {"0": [[0, 0, 100, 100]]}}, [0]), sd.job
print("JOBS-GUI-OK")
'''


def test_jobs_from_gui():
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.join(HERE, "_qtstub"), ROOT, HERE]),
               HOME="/tmp/_smoke_home", PASSERMARK_LANG="de")
    os.makedirs("/tmp/_smoke_home", exist_ok=True)
    r = subprocess.run([sys.executable, "-c", SCRIPT], capture_output=True, text=True, env=env, timeout=900)
    print(r.stdout)
    assert "JOBS-GUI-OK" in r.stdout, r.stdout[-3000:] + r.stderr[-4000:]


if __name__ == "__main__":
    test_jobs_from_gui(); print("ok test_jobs_from_gui")
