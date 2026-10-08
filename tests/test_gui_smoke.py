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
    w.edit_panel.isVisible = lambda: True
    w._edit_mode(True); w.edit_panel._fill_text(); w.edit_panel._fill_layers(); w._edit_mode(False)
print("SMOKE-OK")
'''


def test_start_and_basic_actions():
    env = dict(os.environ, PYTHONPATH=os.path.join(HERE, "_qtstub") + os.pathsep + ROOT,
               HOME="/tmp/_smoke_home", PASSERMARK_LANG="en", PDFTOOLKIT_LANG="en", PDFTOOLBOX_LANG="en")
    os.makedirs("/tmp/_smoke_home", exist_ok=True)
    r = subprocess.run([sys.executable, "-c", SCRIPT, SAMPLE], capture_output=True, text=True, env=env, timeout=300)
    assert "SMOKE-OK" in r.stdout, r.stdout[-2000:] + r.stderr[-3000:]


if __name__ == "__main__":
    test_start_and_basic_actions(); print("ok test_start_and_basic_actions")
