# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Materialien und Softproof in der Oberfläche (echtes Qt, ohne Bildschirm): Papierweiß messen (nachgestelltes
    spotread: kalibrieren, messen), Datei/Hand, Verwaltung → Materialien mit Vorschlag und Übernahme,
    Material im Druckdialog und in der CMYK-Umwandlung, Softproof der Seitenansicht."""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

SCRIPT = r'''
import os, sys, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.environ["PM_TESTS"])
from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog
app = QApplication(sys.argv)
for n in ("critical", "warning", "information"):
    setattr(QMessageBox, n, staticmethod(lambda *a, **k: None))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
QInputDialog.getText = staticmethod(lambda *a, **k: ("Natur ungestrichen 120 g", True))
import pikepdf, pypdfium2 as pdfium
import test_printcli as T
from test_softproof import cmyk_profile
from pdfdruck import config, cfgvalidate, cmyk, colorlab, printers
F = cmyk_profile()
cmyk.system_profile_dirs = lambda: [os.path.dirname(F)]


def pump(cond, n=500):
    for _ in range(n):
        app.processEvents()
        time.sleep(0.01)
        if cond():
            return True
    return False


# ---- Papierweiß messen ----
from pdfdruck.gui.measuredialog import MeasureDialog
md = MeasureDialog(None, "Natur")
assert md.exe and md.btn_measure.isEnabled()
md._start()
assert pump(lambda: md.btn_next.isEnabled()), md.log.toPlainText()
assert "Kalibrieren" in md.lbl_state.text(), md.lbl_state.text()
md._key()
assert pump(lambda: md.btn_next.isEnabled() and "Messen" in md.lbl_state.text()), md.log.toPlainText()
md._key()
assert pump(lambda: md.values and md.proc is None), md.log.toPlainText()
assert md.values[0][0] == (93.51, 0.81, 4.21), md.values
md.ed_lab.setText("93,9 0,6 3,9")
md._add_manual()
assert md.result_lab() == (93.71, 0.71, 4.05) and "Streuung" in md.lbl_mean.text()
md._start()                                          # abbrechen mitten in der Kalibrierung
assert pump(lambda: md.btn_next.isEnabled())
md._stop()
assert pump(lambda: md.proc is None)
assert len(md.values) == 2
md.reject()

# ---- Verwaltung → Materialien ----
class Q:
    def __init__(s, n):
        s.name, s.model, s.is_default = n, "", False
printers.list_printers = lambda: [Q("epson"), Q("canon")]
from pdfdruck.session import Session
from pdfdruck.gui.admindialog import AdminDialog
d = AdminDialog(None, Session(config.load()))
t = d.mat_tab
t._new()
m = t.cur()
assert m["weight"] == 120 and m["surface"] == "uncoated" and m["name"] == "Natur ungestrichen 120 g", m
m["white"], m["white_source"] = [92.0, 0.5, 7.0], "gemessen"
t._show()
assert t.tree.topLevelItemCount() >= 1 and "FOGRA52" in t.lbl_tip.text(), t.lbl_tip.text()
t.cmb_for.setCurrentIndex(t.cmb_for.findData("epson"))
t.tree.setCurrentItem(t.tree.topLevelItem(0))
t._take()                                            # Systemprofil -> importiert und zugeordnet
pid = m["profiles"]["epson"]
assert pid in d.new_icc and d.new_icc[pid] == F, (pid, d.new_icc)
cfgvalidate.validate(d.cfg, str(config.ICC_DIR))
t._copy()
assert len(d.cfg["materials"]) == 2 and d.cfg["materials"][1]["id"] != m["id"]
t._delete()
assert len(d.cfg["materials"]) == 1
d.lst_prof.setCurrentRow(len(d.cfg["color_profiles"]) - 1)
d._del_profile()
assert m["profiles"] == {}                            # Profil weg -> Zuordnung weg
cfgvalidate.validate(d.cfg, str(config.ICC_DIR))
d.reject()

# ---- Druckdialog ----
with T.FakePrinter():
    cfg = config.load()
    cfg["default_printer"] = "Canon"
    cfg["color_profiles"] = [{"id": "fogra39", "name": "FOGRA39", "file": F, "printers": [], "intents": ["perceptual", "relative"]},
                             {"id": "other", "name": "Anderes", "file": F, "printers": [], "intents": ["relative"]}]
    cfg["materials"] = [{"id": "bd", "name": "Bilderdruck", "weight": 135, "surface": "coated", "white": [94, 0.5, -1.5],
                         "profiles": {"*": "fogra39"}, "intent": "perceptual"},
                        {"id": "x", "name": "Nur Epson", "profiles": {"epson": "other"}}]
    from pdfdruck.gui import printdialog as pd
    p = T.doc(1)
    s = Session(cfg)
    dlg = pd.PrintDialog(None, pdfium.PdfDocument(p), p, 0, s)
    assert dlg.cmb_material.count() == 2                 # „keins“ + Bilderdruck (Nur Epson passt nicht zu Canon)
    dlg.cmb_material.setCurrentIndex(1)
    assert dlg.cmb_profile.currentData() == "fogra39" and dlg.cmb_intent.currentData() == "perceptual"
    assert s.color["Canon"] == ("fogra39", "perceptual") and s.material == {"Canon": "bd"}
    assert "ΔE" in dlg.lbl_profile_note.text()
    dlg.cmb_profile.setCurrentIndex(dlg.cmb_profile.findData("other"))
    assert dlg.cmb_material.currentData() == "" and s.material == {}
    dlg.reject()

# ---- CMYK-Umwandlung ----
q = os.path.join(os.environ["PM_TMP"], "oi.pdf")
pdf = pikepdf.new(); pdf.add_blank_page(page_size=(200, 200))
pdf.pages[0].obj.Contents = pikepdf.Stream(pdf, b"0 0 0 1 k 0 0 100 100 re f")
pdf.Root.OutputIntents = pikepdf.Array([pikepdf.Dictionary(Type=pikepdf.Name.OutputIntent, S=pikepdf.Name.GTS_PDFX,
                                                           OutputConditionIdentifier=pikepdf.String("FOGRA27"))])
pdf.save(q)
from pdfdruck.gui.manipdialog import ManipPanel
s = Session(cfg)
pan = ManipPanel(None, s.manip, cfg, pdfium.PdfDocument(q), 0)
pan.cmb_material.setCurrentIndex(1)
assert pan.cmb_target.currentData() == F and pan.cmb_mode.currentData() == "all" and pan.chk_cmyk.isChecked()
assert "FOGRA27" in pan.lbl_rec.text() and pan.material_white == [94, 0.5, -1.5]
assert s.manip.target == F and s.manip.intent == "perceptual"

# ---- Softproof der Ansicht ----
from pdfdruck.app import Controller
from pdfdruck.gui import softproofdialog as SD
ctl = Controller()
ctl.open_paths([q]); w = ctl.windows[-1]
w.session.cfg.update(cfg)
pump(lambda: all(pw.master is not None for pw in w.view.pages), 300)
SD.save({"key": "m:bd:*", "paper": True, "measured": True, "warn": "tac", "tac": 280})
w.a_proof.setChecked(True)
assert w.view.proof and w.view.proof["white"] == [94, 0.5, -1.5] and w.view.proof["warn"] == "tac"
assert "Bilderdruck" in w.lbl_proof.text() and w.lbl_proof.isVisible()
assert pump(lambda: all(pw.master is not None and not pw.mstale for pw in w.view.pages), 600)
w.softproof_dialog()
dl = w._proof_dlg
dl.chk_paper.setChecked(False)
assert not w.view.proof["paper"] and SD.load_saved()["paper"] is False
w.a_proof.setChecked(False)
assert w.view.proof is None and not w.lbl_proof.isVisible()
print("OK")
'''


def test_materials_gui():
    try:
        import PySide6.QtWidgets  # noqa: F401
    except Exception:
        print("   (übersprungen: kein Qt)")
        return
    d = tempfile.mkdtemp(prefix="pm-mat-")
    wrap = os.path.join(d, "spotread")
    with open(wrap, "w") as f:
        f.write(f'#!/bin/sh\nexec "{sys.executable}" "{os.path.join(HERE, "fake_spotread.py")}" "$@"\n')
    os.chmod(wrap, 0o755)
    env = dict(os.environ, PYTHONPATH=ROOT + os.pathsep + os.environ.get("PYTHONPATH", ""), PASSERMARK_LANG="de",
               PASSERMARK_RENDER="local", HOME=d, XDG_CONFIG_HOME=os.path.join(d, "cfg"), PM_TESTS=HERE, PM_TMP=d,
               PASSERMARK_SPOTREAD=wrap, PDFDRUCK_CONFIG_DIR=os.path.join(d, "etc"))
    r = subprocess.run([sys.executable, "-c", SCRIPT, d], capture_output=True, text=True, env=env, timeout=600)
    assert r.returncode == 0 and "OK" in r.stdout, r.stdout[-2000:] + r.stderr[-3000:]


if __name__ == "__main__":
    test_materials_gui()
    print("ok test_materials_gui")
