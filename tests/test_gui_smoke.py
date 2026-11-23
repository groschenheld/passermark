# SPDX-License-Identifier: GPL-3.0-or-later
"""Startup test without a screen: Qt is replaced by a stub (tests/_qtstub) that accepts all calls.
Finds Python errors at program start, window construction and in menu/mouse functions."""

import os
import subprocess
import tempfile
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SAMPLE = os.path.join(HERE, "sample.pdf")

SCRIPT = r"""
import sys, types
from pdfdruck.gui import mainwindow, pageview
pageview.PageView._dpi_scale = lambda self: 1.0
pageview.PageView.page_zoom = lambda self, i: 1.0
import pdfdruck.__main__ as m
sys.argv = ["prog", sys.argv[1]]
assert m.main() == 0
from pdfdruck import config
from pdfdruck.gui.common import Session
import pypdfium2 as pdfium
w = mainwindow.MainWindow(types.SimpleNamespace(view_single=True, session=Session(config.BUILTIN), windows=[]))
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
    def button(s): return mainwindow.Qt.MouseButton.LeftButton
    def modifiers(s): return 0
w.view.mouse_press(pw, E(100, 100)); w.view.mouse_move(pw, E(200, 110)); w.view.mouse_release(pw, E(200, 110))
w.view.mouse_double(pw, E(100, 100)); w.view.select_page_text(); w.copy_text()
from PySide6.QtGui import QPainter
w.view.paint_overlay(pw, QPainter())
if "edit_panel" in w.__dict__:
    # edit mode with the mouse: grab + drag text, grab + drag a layer, corner handle, undo
    from pdfdruck import editing, preflight
    import test_preflight as tp
    w._set_doc(pdfium.PdfDocument(tp.problem_pdf()), "/tmp/x.pdf", "x.pdf", False)
    w.a_edit.isChecked = lambda: True
    ep = w.edit_panel; tab = [0]; row = {"t": -1, "l": -1}
    ep.tabs.currentIndex = lambda: tab[0]
    ep.lst_text.currentRow = lambda: row["t"]
    ep.lst_text.setCurrentRow = lambda r: (row.__setitem__("t", r), ep._text_selected(r))
    # multiple selection: dragging/scaling acts on the chosen rows – as in real Qt
    # the current row counts as chosen
    ep.lst_text.selectedIndexes = lambda: [types.SimpleNamespace(row=lambda: row["t"])] if row["t"] >= 0 else []
    ep.lst_layers.currentRow = lambda: row["l"]
    ep.lst_layers.setCurrentRow = lambda r: (row.__setitem__("l", r), ep._layer_selected(r))
    w._edit_mode(True)
    def pg():
        p = w.view.pages[w.view.current]; p.width = lambda: 595; p.height = lambda: 842; return p
    w.view.mouse_press(pg(), E(100, 434)); w.view.mouse_move(pg(), E(200, 384)); w.view.mouse_release(pg(), E(200, 384))
    L = next(l for l in editing.text_lines(w.doc, 0) if l.text.startswith("Hallo"))
    assert abs(L.bbox[0] - 152) < 2 and abs(L.bbox[1] - 450) < 2, L.bbox
    # change text, switch font, delete – the other lines must be preserved
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
    tab[0] = 2; ep.refresh()                 # tabs: 0 text, 1 objects, 2 layers
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
    # move step by step (10 mm to the right), snapping to the page edge, colour pipette
    from pdfdruck.gui import editpanel as EPm
    class _NoMods:                              # no key pressed (the stand-in knows no flags)
        def __and__(self, other): return 0
    EPm.QApplication.keyboardModifiers = staticmethod(lambda: _NoMods())
    tab[0] = 0
    hrow = next(i for i, l in enumerate(ep.lines) if l.text.startswith("Hallo"))
    ep.lst_text.setCurrentRow(hrow)
    x_before = next(l for l in editing.text_lines(w.doc, 0) if l.text.startswith("Hallo")).bbox[0]
    ep.spn_step.value = lambda: 10.0
    ep.cmb_unit.currentData = lambda: "mm"
    ep._screen_dir = lambda sx, sy: (float(sx), float(-sy))
    ep.nudge(1, 0)
    x_after = next(l for l in editing.text_lines(w.doc, 0) if l.text.startswith("Hallo")).bbox[0]
    assert abs(x_after - x_before - 10 * 72 / 25.4) < 1.0, (x_before, x_after)
    ep.chk_snap.isChecked = lambda: True
    ep.spn_grid.value = lambda: 0.0
    dx, dy, guides = ep._snap_move((50.0, 500.0, 150.0, 520.0), -46.0, 0.0)     # left edge almost at the page edge
    assert abs(dx + 50.0) < 0.01 and guides, (dx, guides)
    ep.spn_grid.value = lambda: 10.0
    ep.chk_snap.isChecked = lambda: False
    dx, dy, guides = ep._snap_move((50.0, 500.0, 150.0, 520.0), 5.0, 0.0)       # Raster 10 mm: x = 56,7 pt
    assert abs(50.0 + dx - 10 * 72 / 25.4 * 2) < 0.01 or abs(50.0 + dx - 10 * 72 / 25.4) < 0.01, dx
    w.a_pipette.isChecked = lambda: True
    w._pipette_mode(True)
    assert w.view.imode == "pipette"
    from pdfdruck import pipette
    w.pipette_dlg._done(pipette.sample(w._doc_bytes(), 0, 160, 460), "")
    w.pipette_dlg._take("rgb")
    w._pipette_picked("rgb", w.pipette_dlg.sample.as_rgb())     # the stand-in delivers no signals
    assert ep._last_color[0] == "rgb" and len(ep._last_color[1]) == 3, ep._last_color
    w.a_pipette.isChecked = lambda: False
    w._pipette_mode(False)
    assert w.view.imode == "edit"
    w._edit_mode(False)
from pdfdruck import planhistory               # Plan & Poster → recent prints
w._fill_plan_history()
planhistory.add("poster", "Plotter", {"copies": 1}, [{"source": sys.argv[1], "page": 0, "qty": 1, "ov": {}, "own": True}], 1.0, 1)
w._fill_plan_history(); w._clear_plan_history()
planhistory.clear()
from pdfdruck.gui import plandialog            # plan/poster: own window, the open document is not taken over
w.plan_dialog("poster")
pw_ = plandialog.open_windows()
assert len(pw_) == 1 and pw_[0].kind == "poster" and pw_[0].items == [] and pw_[0].ctl is w.ctl, pw_
from pdfdruck import app as appmod              # passermark --plan a.pdf (or passed on from a second start)
appmod.Controller().queue_request("plan", [sys.argv[1]])
pw_ = {d.kind: d for d in plandialog.open_windows()}
assert set(pw_) == {"plan", "poster"} and pw_["plan"].items, pw_
plandialog._WINDOWS.clear()
print("SMOKE-OK")
"""


def test_rows_stack_with_hysteresis():
    sys.path[:0] = [os.path.join(HERE, "_qtstub"), ROOT]
    from pdfdruck.gui.common import needs_stack

    assert needs_stack(300, 250, False) and not needs_stack(300, 320, False)
    assert needs_stack(300, 305, True)  # stays stacked until there is clearly room
    assert not needs_stack(300, 320, True)
    assert needs_stack(300, 0, True) and not needs_stack(300, 0, False)  # no width known yet: unchanged


def test_snap_reads_object_bounds():
    """Measuring with Ctrl snaps to image edges: page objects give their bounds (pypdfium2 4 and 5)."""
    sys.path[:0] = [os.path.join(HERE, "_qtstub"), ROOT]
    import io

    import img2pdf
    import pypdfium2 as pdfium
    from PIL import Image

    from pdfdruck.gui.pageinteraction import _bounds

    b = io.BytesIO()
    Image.new("RGB", (100, 100), "red").save(b, "JPEG")
    doc = pdfium.PdfDocument(img2pdf.convert(b.getvalue(), layout_fun=img2pdf.get_layout_fun((200, 300))))
    obj = next(iter(doc[0].get_objects()))
    left, bottom, right, top = _bounds(obj)
    assert right - left > 100 and top - bottom > 100


def test_softproof_switches_on_without_setup():
    """Ctrl+Y works before anything was changed in the set-up dialog: the first printing condition counts."""
    import tempfile

    os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
    sys.path[:0] = [os.path.join(HERE, "_qtstub"), ROOT]
    from pdfdruck import colorlab
    from pdfdruck.gui import softproofdialog as SD

    choices = colorlab.proof_choices({})
    if not choices:
        print("skip (no CMYK/RGB profile in this system)")
        return
    eff = SD.effective({})
    assert eff["key"] == choices[0]["key"] and SD.load_saved()["key"] == eff["key"]
    assert SD.build_spec({}, eff) is not None
    SD.save({"key": "f:/gone.icc", "intent": "perceptual"})
    eff = SD.effective({})
    assert eff["key"] == choices[0]["key"] and eff["intent"] == "perceptual"  # other choices are kept


def test_start_and_basic_actions():
    env = dict(
        os.environ,
        PYTHONPATH=os.pathsep.join([os.path.join(HERE, "_qtstub"), ROOT, HERE]),
        HOME="/tmp/_smoke_home",
        PASSERMARK_LANG="en",
        PDFTOOLKIT_LANG="en",
        PDFTOOLBOX_LANG="en",
        PASSERMARK_RENDER="local",
        # own socket folder: otherwise a running Passermark of the user takes over the file (single instance)
        TMPDIR=tempfile.mkdtemp(prefix="passermark-smoke-"),
    )  # the Qt stand-in has no event loop: everything in the program
    os.makedirs("/tmp/_smoke_home", exist_ok=True)
    r = subprocess.run([sys.executable, "-c", SCRIPT, SAMPLE], capture_output=True, text=True, env=env, timeout=300)
    assert "SMOKE-OK" in r.stdout, r.stdout[-2000:] + r.stderr[-3000:]


def test_fit_height():
    """Dialogs grow with their wrapped content (squeezed settings/repair windows, 1.20.0)."""
    from pdfdruck.gui import common

    class Size:
        def __init__(self, w, h):
            self.w, self.h = w, h

        def width(self):
            return self.w

        def height(self):
            return self.h

    class Lay:
        def activate(self):
            pass

        def totalMinimumSize(self):
            return Size(300, 200)

        def hasHeightForWidth(self):
            return True

        def totalHeightForWidth(self, w):
            return 120000 // w  # narrower -> taller

    class Scr:
        def availableGeometry(self):
            return Size(1920, 1000)

    class Win:
        def __init__(self):
            self.minw, self.minh, self.w, self.h = 0, 0, 600, 150

        def minimumWidth(self):
            return self.minw

        def minimumHeight(self):
            return self.minh

        def setMinimumSize(self, w, h):
            self.minw, self.minh = w, h

        def width(self):
            return self.w

        def height(self):
            return self.h

        def resize(self, w, h):
            self.w, self.h = w, h

        def layout(self):
            return Lay()

        def screen(self):
            return Scr()

        def isWindow(self):
            return True

        def isVisible(self):
            return True

        def installEventFilter(self, f):
            pass

        def property(self, name):
            return 0

    win = Win()
    assert common._fit_need(win) == (300, 200)  # 120000 / 600 = 200
    common._fit_window(win)
    assert (win.minw, win.minh) == (300, 200) and win.h == 200  # was 150: squeezed -> grows
    win.w = 400
    common._fit_window(win)
    assert win.minh == 300 and win.h == 300  # narrower: texts wrap, taller
    win.w = 40
    assert common._fit_need(win)[1] == 940  # never taller than the screen
    # the filter keeps no Python attributes (a fresh PySide wrapper must work, log 1.20.0-vorab4)
    import inspect

    assert "self." not in inspect.getsource(common._FitHeight.eventFilter)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
