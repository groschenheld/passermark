# SPDX-License-Identifier: GPL-3.0-or-later
"""Start-Test ohne Bildschirm: Qt wird durch einen Ersatz (tests/_qtstub) ersetzt, der alle Aufrufe annimmt.
Findet Python-Fehler beim Programmstart, Fensteraufbau und in Menü-/Mausfunktionen."""
import os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SAMPLE = os.path.join(HERE, "sample.pdf")

SCRIPT = r'''
import sys, types
from pdfdruck.gui import viewer
viewer.PageView._dpi_scale = lambda self: 1.0
viewer.PageView.page_zoom = lambda self, i: 1.0
import pdfdruck.__main__ as m
sys.argv = ["prog", sys.argv[1]]
assert m.main() == 0
from pdfdruck import config
from pdfdruck.gui.common import Session
import pypdfium2 as pdfium
w = viewer.MainWindow(types.SimpleNamespace(view_single=True, session=Session(config.BUILTIN), windows=[]))
w._set_doc(pdfium.PdfDocument(sys.argv[1]), sys.argv[1], "x.pdf", False)
pw = w.view.pages[0]
pw.width = lambda: 600; pw.height = lambda: 800
class P:
    def __init__(s, x, y): s._x, s._y = x, y
    def x(s): return s._x
    def y(s): return s._y
class E:
    def __init__(s, x, y): s.p = P(x, y)
    def position(s): return s.p
    def button(s): return viewer.Qt.MouseButton.LeftButton
    def modifiers(s): return 0
w.view.mouse_press(pw, E(100, 100)); w.view.mouse_move(pw, E(200, 110)); w.view.mouse_release(pw, E(200, 110))
w.view.mouse_double(pw, E(100, 100)); w.view.select_page_text(); w.copy_text()
w.view.paint_overlay(pw, viewer.QPainter())
if "edit_panel" in w.__dict__:
    # Bearbeiten-Modus mit Maus: Text greifen + ziehen, Ebene greifen + ziehen, Eckgriff, Rückgängig
    from pdfdruck import editing, preflight
    import test_preflight as tp
    w._set_doc(pdfium.PdfDocument(tp.problem_pdf()), "/tmp/x.pdf", "x.pdf", False)
    w.a_edit.isChecked = lambda: True
    ep = w.edit_panel; tab = [0]; row = {"t": -1, "l": -1}
    ep.tabs.currentIndex = lambda: tab[0]
    ep.lst_text.currentRow = lambda: row["t"]
    ep.lst_text.setCurrentRow = lambda r: (row.__setitem__("t", r), ep._text_selected(r))
    ep.lst_layers.currentRow = lambda: row["l"]
    ep.lst_layers.setCurrentRow = lambda r: (row.__setitem__("l", r), ep._layer_selected(r))
    w._edit_mode(True)
    def pg():
        p = w.view.pages[w.view.current]; p.width = lambda: 595; p.height = lambda: 842; return p
    w.view.mouse_press(pg(), E(100, 434)); w.view.mouse_move(pg(), E(200, 384)); w.view.mouse_release(pg(), E(200, 384))
    L = next(l for l in editing.text_lines(w.doc, 0) if l.text.startswith("Hallo"))
    assert abs(L.bbox[0] - 152) < 2 and abs(L.bbox[1] - 450) < 2, L.bbox
    # Text ändern, Schrift wechseln, löschen – die anderen Zeilen müssen erhalten bleiben
    def others(exclude):
        return sorted(l.text.strip() for l in editing.text_lines(w.doc, 0) if not l.text.startswith(exclude))
    keep = others("Hallo")
    i = next(k for k, l in enumerate(ep.lines) if l.text.startswith("Hallo"))
    ep.lst_text.setCurrentRow(i)
    ep.ed_text.text = lambda: "Hallo geändert"
    ep.cmb_font.currentData = lambda: None
    ep.spn_size.value = lambda: ep.lines[i].size
    ep._text_apply()
    assert any(l.text == "Hallo geändert" for l in editing.text_lines(w.doc, 0)) and others("Hallo") == keep
    i = next(k for k, l in enumerate(ep.lines) if l.text.startswith("Hallo"))
    ep.lst_text.setCurrentRow(i)
    ep.ed_text.text = lambda: "Hallo Times"
    ep.cmb_font.currentData = lambda: ("std", "Times-Bold")
    ep._text_apply()
    assert any(l.text == "Hallo Times" and "Times" in l.font for l in editing.text_lines(w.doc, 0)) and others("Hallo") == keep
    i = next(k for k, l in enumerate(ep.lines) if l.text.startswith("Hallo"))
    ep.lst_text.setCurrentRow(i)
    ep._text_delete()
    assert not any(l.text.startswith("Hallo") for l in editing.text_lines(w.doc, 0)) and others("Hallo") == keep
    for _k in range(3):
        ep._undo()
    tab[0] = 1; ep.refresh()
    K = {x.name: x.key for x in preflight.analyze(w._doc_bytes(), deep_layers=False).layers}
    w.view.mouse_press(pg(), E(150, 217)); w.view.mouse_move(pg(), E(150, 317)); w.view.mouse_release(pg(), E(150, 317))
    b = editing.layer_map(w._doc_bytes(), 0, [K["Bemaßung"]]).boxes[K["Bemaßung"]]
    assert abs(b[1] - 498) < 5, b
    x0, y0, x1, y1 = ep.sel_box
    assert ep.cursor(0, x1, y1, 4) == "scale" and ep.cursor(0, (x0 + x1) / 2, (y0 + y1) / 2, 4) == "move"
    w.view.mouse_press(pg(), E(x1, 842 - y1)); w.view.mouse_move(pg(), E(2 * x1 - x0, 842 - (2 * y1 - y0)))
    w.view.mouse_release(pg(), E(2 * x1 - x0, 842 - (2 * y1 - y0)))
    b2 = editing.layer_map(w._doc_bytes(), 0, [K["Bemaßung"]]).boxes[K["Bemaßung"]]
    assert 1.85 < (b2[2] - b2[0]) / (b[2] - b[0]) < 2.15, (b, b2)
    ep._undo(); ep._undo()
    b3 = editing.layer_map(w._doc_bytes(), 0, [K["Bemaßung"]]).boxes[K["Bemaßung"]]
    assert abs(b3[1] - 598) < 5, b3
    w._edit_mode(False)
print("SMOKE-OK")
'''


def test_start_and_basic_actions():
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.join(HERE, "_qtstub"), ROOT, HERE]),
               HOME="/tmp/_smoke_home", PASSERMARK_LANG="en", PDFTOOLKIT_LANG="en", PDFTOOLBOX_LANG="en")
    os.makedirs("/tmp/_smoke_home", exist_ok=True)
    r = subprocess.run([sys.executable, "-c", SCRIPT, SAMPLE], capture_output=True, text=True, env=env, timeout=300)
    assert "SMOKE-OK" in r.stdout, r.stdout[-2000:] + r.stderr[-3000:]


if __name__ == "__main__":
    test_start_and_basic_actions(); print("ok test_start_and_basic_actions")
