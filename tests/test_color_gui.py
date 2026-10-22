# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Farbe in der Oberfläche (1.17): Menü Farbe, Farbprüfung mit Aktionen, eigene Papiere (ohne Admin), Assistent
„Für Druckerei ausgeben“.
  test_color_gui_stub  – Qt-Attrappe (läuft überall): Aufbau, Handler, Speichern der eigenen Papiere
  test_color_gui_qt    – echtes Qt ohne Bildschirm: Prüfung im Hintergrund, Assistent bis zur fertigen Datei"""
import os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

STUB = r'''
import os, sys, types
from pdfdruck.gui import viewer
viewer.PageView._dpi_scale = lambda self: 1.0
viewer.PageView.page_zoom = lambda self, i: 1.0
import test_colorcheck as T
from pdfdruck import colorcheck, colorlab, config, pressexport, usercolor
from pdfdruck.gui.common import Session
import pypdfium2 as pdfium
F = T.cmyk_profile()
w = viewer.MainWindow(types.SimpleNamespace(view_single=True, session=Session(config.BUILTIN), windows=[]))
path = T.write(T.sample_pdf())
w._set_doc(pdfium.PdfDocument(path), path, "x.pdf", False)

# ---- Farbprüfung ----
w.color_check()
cp = w.color_panel
ch = next(c for c in cp.choices if c["icc"] == F)
cp.cmb.currentData = lambda: ch["key"]
cp.cmb_intent.currentData = lambda: ""
cp.spn_tac.value = lambda: 0
t = cp.target()
assert t.icc == F and t.space == "CMYK", t
f = colorcheck.facts(w._doc_bytes(), t)
res = colorcheck.check(f, t, {})
cp._gen = 7
cp._done(7, t, f, res, "")
assert cp.facts is f and cp.findings is res

jobs = []
w.start_job = lambda *a, **k: jobs.append((a, k))
asked = []
w._ask_rgb = lambda name: (asked.append(name), "convert")[1]
x = next(x for x in res if x.key == "rgb")
w._color_action("convert", dict(x.params, intent="relative", material="", tac_limit=0, has_rgb=True))
kind, s = jobs[-1][0][0], jobs[-1][0][1]
assert kind == "press" and s["rgb"] == "convert" and s["cmyk_mode"] == "rgb_only" and s["target"] == F and asked
w._ask_rgb = lambda name: ""                     # abgebrochen -> kein Auftrag
w._color_action("convert", dict(x.params, has_rgb=True))
assert len(jobs) == 1
w._color_action("embed_oi", {"target": F, "has_rgb": False})
assert jobs[-1][0][1]["cmyk_mode"] == "none"
w._color_action("preflight", {})
w._color_action("get_profiles", {"surface": "coated"})
w._color_action("press", {})
w._color_action("choose_target", {})
w._proof_for_choice(ch)

# ---- eigene Papiere (ohne Admin) ----
from pdfdruck.gui import materialtab, measuredialog
materialtab.QInputDialog.getText = staticmethod(lambda *a, **k: ("Munken Pure 120 g", True))
host = materialtab.UserHost(w, w.session.cfg)
tab = materialtab.MaterialTab(host=host)
cur = {"i": -1}
tab.lst.currentRow = lambda: cur["i"]
tab.lst.setCurrentRow = lambda i: cur.__setitem__("i", i)
tab._new()
assert [m["weight"] for m in usercolor.load_materials()] == [120]
cur["i"] = 0
class MD:
    def __init__(s, *a): pass
    def exec(s): return True
    def result_lab(s): return (93.4, 0.6, 3.9)
    def result_source(s): return "gemessen"
measuredialog.MeasureDialog = MD
tab._measure()
assert usercolor.load_materials()[0]["white"] == [93.4, 0.6, 3.9]
tab.cmb_for.currentData = lambda: "*"
tab.tree.currentItem = lambda: types.SimpleNamespace(data=lambda c, r: {"id": "", "file": F, "name": "F39",
                                                                          "space": "CMYK"})
tab._take()
m = usercolor.load_materials()[0]
assert m["profiles"] == {"*": F} and m["intent"] == "relative", m
assert any(c["material"] == m["id"] for c in colorlab.proof_choices(w.session.cfg))
assert any(p[0] == F for p in host.profile_items())
w.materials_dialog(m["id"], measure=True)
w._color_action("measure", {"material": m["id"]})

# ---- Assistent ----
from pdfdruck.gui.pressdialog import PressDialog
d = PressDialog(w, w._doc_bytes, w.session.cfg, path[:-4] + "_Druck.pdf", ch["key"])
d.cmb.currentData = lambda: ch["key"]
d.cmb_intent.currentData = lambda: "relative"
d.cmb_mode.currentData = lambda: "none"
d.chk_bpc.isChecked = lambda: True
d.chk_pkg.isChecked = lambda: True
d.spn_tac.value = lambda: 0
d.rb_convert.isChecked = lambda: False
d.rb_keep.isChecked = lambda: True
d.stack.currentIndex = lambda: 1
d._checked(t, f, res)
d._update_plan()
s = d._settings()
assert s.rgb == "keep" and s.package and s.target == F
out = path[:-4] + "_Druck.pdf"
r = pressexport.run(path, out, s, {})
d.out_path = out
d._finished(r)
assert os.path.isfile(r["package"])
print("COLOR-GUI-OK")
'''

QT = r'''
import os, sys, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.environ["PM_TESTS"])
from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog
app = QApplication(sys.argv)
for n in ("critical", "warning", "information"):
    setattr(QMessageBox, n, staticmethod(lambda *a, **k: None))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
QInputDialog.getText = staticmethod(lambda *a, **k: ("Natur ungestrichen 120 g", True))
import pikepdf
import test_colorcheck as T
from pdfdruck import cmyk, usercolor
F = T.cmyk_profile()
cmyk.system_profile_dirs = lambda: [os.path.dirname(F), usercolor.icc_dir()]


def pump(cond, n=1500):
    for _ in range(n):
        app.processEvents()
        time.sleep(0.01)
        if cond():
            return True
    return False


from pdfdruck.app import Controller
ctl = Controller()
path = T.write(T.sample_pdf())
ctl.open_paths([path]); w = ctl.windows[-1]
assert any(a.text().replace("&", "") == "Farbe" for a in w.menuBar().actions())
# ---- Farbprüfung im Hintergrund ----
w.color_check()
cp = w.color_panel
i = next(k for k in range(cp.cmb.count()) if cp.cmb.itemData(k) and cp.cmb.itemData(k).endswith(F))
cp.cmb.setCurrentIndex(i)
cp.start()
assert pump(lambda: cp.facts is not None and cp._worker is None), cp.lbl_sum.text()
titles = [cp.tree.topLevelItem(k).text(1) for k in range(cp.tree.topLevelItemCount())]
assert any("RGB" in t for t in titles), titles
cp.tree.setCurrentItem(cp.tree.topLevelItem(0))
assert cp.lbl_detail.text()

# ---- eigene Papiere ----
from pdfdruck.gui.materialsdialog import MaterialsDialog
md = MaterialsDialog(w, w.session.cfg)
md.tab._new()
assert usercolor.load_materials()[0]["surface"] == "uncoated"
md.reject()

# ---- Assistent bis zur Datei ----
from pdfdruck.gui.pressdialog import PressDialog
out = path[:-4] + "_Druck.pdf"
d = PressDialog(w, w._doc_bytes, w.session.cfg, out, cp.cmb.currentData())
d._next()
assert pump(lambda: d.facts is not None), d.lbl_check.text()
assert d.box_rgb.isVisibleTo(d) and not d.rb_convert.isChecked() and not d.rb_keep.isChecked()   # immer fragen
d._next()
assert d.stack.currentIndex() == 1                   # ohne Entscheidung geht es nicht weiter
d.rb_keep.setChecked(True)
d.cmb_mode.setCurrentIndex(d.cmb_mode.findData("none"))
assert "sRGB" in d.lbl_plan.text(), d.lbl_plan.text()
d._next()
assert d.stack.currentIndex() == 2
d.chk_pkg.setChecked(True)
d._next()
assert pump(lambda: d.result is not None), d.lbl_run.text()
assert d.stack.currentIndex() == 3 and "Output Intent" in d.txt_report.toPlainText(), d.txt_report.toPlainText()
with pikepdf.open(out) as pdf:
    assert "/OutputIntents" in pdf.Root
assert os.path.isfile(d.result["package"])
d.accept()
print("OK")
'''


def _env(d, stub):
    env = dict(os.environ, PASSERMARK_LANG="de", PDFTOOLKIT_LANG="de", PASSERMARK_RENDER="local", HOME=d,
               XDG_CONFIG_HOME=os.path.join(d, "cfg"), XDG_DATA_HOME=os.path.join(d, "data"), PM_TESTS=HERE,
               PASSERMARK_USER_DIR=os.path.join(d, "user"), PDFDRUCK_CONFIG_DIR=os.path.join(d, "etc"))
    env["PYTHONPATH"] = os.pathsep.join(([os.path.join(HERE, "_qtstub")] if stub else []) + [ROOT, HERE])
    return env


def test_color_gui_stub():
    d = tempfile.mkdtemp(prefix="pm-colgui-")
    r = subprocess.run([sys.executable, "-c", STUB], capture_output=True, text=True, env=_env(d, True), timeout=600)
    assert "COLOR-GUI-OK" in r.stdout, r.stdout[-2000:] + r.stderr[-3000:]


def test_color_gui_qt():
    try:
        import PySide6.QtWidgets  # noqa: F401
    except Exception:
        print("   (übersprungen: kein Qt)")
        return
    d = tempfile.mkdtemp(prefix="pm-colqt-")
    r = subprocess.run([sys.executable, "-c", QT], capture_output=True, text=True, env=_env(d, False), timeout=900)
    assert r.returncode == 0 and "OK" in r.stdout, r.stdout[-2000:] + r.stderr[-3000:]


if __name__ == "__main__":
    test_color_gui_stub(); print("ok test_color_gui_stub")
    test_color_gui_qt(); print("ok test_color_gui_qt")
