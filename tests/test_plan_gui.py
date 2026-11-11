# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Plandruck-Fenster ohne Bildschirm (Qt-Attrappe aus tests/_qtstub): Pläne erkennen, Rollen von Hand, Laufmeter,
    Druck an einen nachgebauten Plotter, Einstellungen merken, Rollen-Fenster."""
import os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

SCRIPT = r'''
import os, sys, tempfile
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pm-plangui-")
from PySide6 import QtWidgets as W
from pdfdruck.gui import plandialog as P


class Combo(W.QComboBox):
    def __init__(self, *a):
        self.items, self.i = [], -1
    def addItem(self, text, data=None):
        self.items.append((text, data))
        if self.i < 0:
            self.i = 0
    def clear(self):
        self.items, self.i = [], -1
    def count(self):
        return len(self.items)
    def findData(self, d):
        return next((k for k, (_t, x) in enumerate(self.items) if x == d), -1)
    def setCurrentIndex(self, i):
        self.i = i
    def currentData(self):
        return self.items[self.i][1] if 0 <= self.i < len(self.items) else None
    def blockSignals(self, b):
        return False


class Spin(W.QSpinBox):
    def __init__(self, *a):
        self.v = 0
    def setValue(self, v):
        self.v = v
    def value(self):
        return self.v


class Check(W.QCheckBox):
    def __init__(self, *a):
        self.c = False
    def setChecked(self, b):
        self.c = bool(b)
    def isChecked(self):
        return self.c


class Edit(W.QLineEdit):
    def __init__(self, t="", *a):
        self.t = t
    def text(self):
        return self.t
    def setText(self, t):
        self.t = t


P.QComboBox, P.QSpinBox, P.QDoubleSpinBox, P.QCheckBox, P.QLineEdit = Combo, Spin, Spin, Check, Edit
import pypdfium2 as pdfium
import test_planprint as T
from pdfdruck import config, rolls
from pdfdruck import planprint as pp
from pdfdruck.session import Session

rolls.save_manual("Plotter", [rolls.Roll(594, "Roll1", "Rolle 1", 80), rolls.Roll(841, "Roll2", "Rolle 2", 80),
                              rolls.Roll(914, "Roll3", "Rolle 3", 180)])
src = T.plan_pdf("gui.pdf", 620, 870, pages=2)
with T.FakePlotter() as fp:
    sess = Session(config.BUILTIN)
    doc = pdfium.PdfDocument(src)
    dlg = P.PlanDialog(None, sess, None, doc, src)
    assert dlg.printer == "Plotter", dlg.printer
    assert [r.width_mm for r in dlg.rolls] == [594, 841, 914] and dlg.rolls[1].slot == "Roll2"
    assert len(dlg.items) == 2 and len(dlg._queue) == 2
    while dlg._queue:
        dlg._analyze_next()
    s = dlg.settings()
    assert s.weights == [75, 80] and not s.collate and s.copies == 1
    # 914 hat 180 g -> nicht für Pläne: 600 × 850 auf 841 (Länge 850)
    assert all(it.area.kind == "frame" and it.fit.width_mm == 841 for it in dlg.items), [it.fit for it in dlg.items]
    dlg.spn_copies.setValue(2)
    dlg.items[1].qty = 3
    dlg._refresh()
    lens = T.pp.run_lengths(dlg.items, dlg.rolls, 2)
    assert len(lens) == 1 and abs(lens[0]["single_m"] - 4 * 0.8497) < 0.01 and abs(lens[0]["total_m"] - 8 * 0.8497) < 0.02
    # Rand statt Rahmen für einen Plan
    dlg._set_frame([0], "margin")
    while dlg._queue:
        dlg._analyze_next()
    assert dlg.items[0].area.kind == "margin" and dlg.items[1].area.kind == "frame"
    # Graustufen, nach Rolle, drucken
    dlg.cmb_color.setCurrentIndex(dlg.cmb_color.findData("gray"))
    assert dlg.settings().quality_mode == "production"          # Plan: Produktionsdruck, umschaltbar
    dlg.cmb_qmode.setCurrentIndex(dlg.cmb_qmode.findData("quality"))
    assert dlg.settings().quality_mode == "quality"
    dlg._print()
    # seit 1.18.7 Standard: ein Auftrag je Plan, je Exemplar ein Blatt (copies = 1, Anzahl im Titel)
    assert len(fp.sent) == 2 and all(x["opts"]["copies"] == "1" for x in fp.sent), fp.sent
    assert fp.sent[0]["title"].endswith("×2") and fp.sent[1]["title"].endswith("×6"), fp.sent
    assert all(x["opts"]["InputSlot"] == "Roll2" and x["opts"]["ColorModel"] == "Gray" for x in fp.sent)
    assert dlg.items == [] and dlg.settings().copies == 1 and dlg.settings().color != "gray"   # Fenster bleibt: leer, Standard
    assert dlg.settings().quality_mode == "production"
    assert P.PlanDialog(None, sess, None, None, "", "", "poster").settings().quality_mode == "quality"
    from pdfdruck import planhistory              # Verlauf: Druck gemerkt, mit Dateien und Mengen wieder öffnen
    ents = planhistory.entries("plan")
    assert ents and ents[0]["printer"] == "Plotter" and [i["qty"] for i in ents[0]["items"]] == [1, 3], ents[:1]
    assert ents[0]["settings"].get("color") == "gray" and planhistory.file_of(ents[0], ents[0]["items"][0])
    d2 = P.PlanDialog(None, sess, None, None, "", "", "plan")
    d2.load_history(ents[0])
    assert [it.qty for it in d2.items] == [1, 3] and d2.settings().copies == 2 and d2.settings().color == "gray", [it.qty for it in d2.items]
    assert d2.printer == "Plotter"
    d2._cleanup(1)                                # wie gedruckt/übernommen: merkt nichts
    st = P.load_settings()                       # nach dem Drucken: wieder der Standard
    assert st.color == pp.PlanSettings(**pp.defaults_for("plan")).color and st.copies == 1, st
    dlg.cmb_color.setCurrentIndex(dlg.cmb_color.findData("gray"))
    dlg._save_standard()                          # eigener Standard: Graustufen
    assert P.load_settings().color == "gray" and P.load_settings().copies == 1
    dlg.spn_copies.setValue(4)
    dlg._load_standard()
    # PDF speichern
    dlg.add_doc(doc, src, own=False)
    while dlg._queue:
        dlg._analyze_next()
    out = os.path.join(T.TMP, "gui_out.pdf")
    P.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (out, ""))
    dlg._save_pdf()
    d = pdfium.PdfDocument(out)
    assert len(d) == 2
    d.close()
    dlg._cleanup(0)
    # Rollen-Fenster
    rd = P.RollsDialog(None, sess, "Plotter")
    rd._remove()
    # Posterdruck: Standard einzeln (Nebeneinander zuschaltbar), Überbreite abschneiden; Banner-Einstellungen
    doc2 = pdfium.PdfDocument(T.plan_pdf("gui_poster.pdf", 420, 594, frames=0))
    pd = P.PlanDialog(None, sess, None, doc2, "gui_poster.pdf", kind="poster")
    while pd._queue:
        pd._analyze_next()
    ps = pd.settings()
    assert ps.kind == "poster" and not ps.nest and ps.overwidth == "crop" and ps.weights == []
    pd.spn_hem.setValue(30)
    pd.chk_cut.setChecked(True)
    pd._refresh()
    assert pd.settings().hem_mm == 30 and pd.settings().cut_contour
    out2 = os.path.join(T.TMP, "gui_poster_out.pdf")
    P.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (out2, ""))
    pd._save_pdf()
    assert os.path.isfile(out2)
    pd._cleanup(0)
    assert P.load_settings("poster").hem_mm == 30 and P.load_settings("plan").hem_mm == 0
    # eigenes Fenster je Art: kein Elternfenster, ein zweiter Aufruf holt dasselbe nach vorne, Dateien dazu
    w1 = P.open_window(sess, None, "plan")
    assert P.open_window(sess, None, "plan") is w1 and w1.items == [] and w1.kind == "plan"
    w2 = P.open_window(sess, None, "poster", files=[src])
    assert w2 is not w1 and len(w2.items) == 2 and len(P.open_windows()) == 2
    P._WINDOWS.clear()
    md = P.MaterialsDialog(None, sess, "Plotter", T.plotter_caps())
    md._add({"name": "PVC 510", "category": "quality"})
    fd = P.FoldersDialog(None)
    from pdfdruck import probe
    P.ProbeDialog(None, probe.run("", "CW"))._save
assert planhistory.clear() >= 1 and planhistory.entries() == []
print("PLAN-GUI-OK")
'''


def test_plan_dialog():
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.join(HERE, "_qtstub"), ROOT, HERE]),
               PASSERMARK_LANG="de")
    r = subprocess.run([sys.executable, "-c", SCRIPT], capture_output=True, text=True, env=env, timeout=600)
    assert "PLAN-GUI-OK" in r.stdout, r.stdout[-2000:] + r.stderr[-4000:]


if __name__ == "__main__":
    test_plan_dialog()
    print("ok test_plan_dialog")
