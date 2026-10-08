# SPDX-License-Identifier: GPL-3.0-or-later
"""Presets (speichern/laden/löschen, zuletzt verwendet, Kommandozeile mit Preset-Namen), PDF mit Passwort,
Arbeitsbereiche im Fenster (Qt-Ersatz) und eindeutige Tastenkürzel."""
import json, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
SAMPLE = os.path.join(HERE, "sample.pdf")

TMP = tempfile.mkdtemp(prefix="pm-presets-")
os.environ["XDG_CONFIG_HOME"] = TMP              # eigene Ablage, nichts vom Benutzer anfassen
os.environ["APPDATA"] = TMP

from pdfdruck import core, cutcontour, presets  # noqa: E402
from pdfdruck.layout import LayoutSettings      # noqa: E402


def test_roundtrip_and_list():
    s = cutcontour.CutSettings(shape="rounded", corner_mm=4.5, bleed_mm=3.0)
    s.detect.tolerance = 55
    p = presets.save("cutcontour", "Sticker rund", s)
    assert os.path.isfile(p) and os.path.dirname(p).endswith(os.path.join("presets", "cutcontour"))
    assert presets.list_presets("cutcontour") == ["Sticker rund"]
    t = presets.load("cutcontour", "Sticker rund")
    assert t.shape == "rounded" and t.corner_mm == 4.5 and t.bleed_mm == 3.0 and t.detect.tolerance == 55
    with open(p, encoding="utf-8") as f:
        assert json.load(f)["job"] == "cutcontour"      # gleiches Format wie `passermark-cli settings`
    presets.delete("cutcontour", "Sticker rund")
    assert presets.list_presets("cutcontour") == []


def test_names_and_last():
    for bad in ("", "  ", "../..", "..."):
        try:
            presets.clean_name(bad)
            raise AssertionError(bad)
        except ValueError:
            pass
    assert presets.clean_name('a/b:c*?"<>|d') == "abcd"
    assert presets.load_last("manip") is None
    from pdfdruck.cmyk import ManipSettings
    presets.save_last("manip", ManipSettings(crop=True, crop_size="A5"))
    last = presets.load_last("manip")
    assert last.crop and last.crop_size == "A5"
    assert presets.list_presets("manip") == []          # „zuletzt“ steht nicht in der Liste


def test_print_layout_kind():
    L = LayoutSettings(handling="booklet", booklet_gutter_mm=4.0, step_repeat=True, sr_cols=3)
    presets.save(presets.PRINT, "Heft A5", L)
    M = presets.load(presets.PRINT, "Heft A5")
    assert M.handling == "booklet" and M.booklet_gutter_mm == 4.0 and M.step_repeat and M.sr_cols == 3
    try:
        presets.load("cutcontour", "Heft A5")
        raise AssertionError("falscher Auftrag")
    except FileNotFoundError:
        pass


def test_wrong_kind_rejected():
    p = presets.save("manip", "x", core.settings_class("manip")())
    os.makedirs(presets.job_dir("cutcontour"), exist_ok=True)
    os.replace(p, presets.path_for("cutcontour", "x"))
    try:
        presets.load("cutcontour", "x")
        raise AssertionError("muss abgelehnt werden")
    except ValueError:
        pass
    presets.delete("cutcontour", "x")


def _cli(*args):
    env = dict(os.environ, PYTHONPATH=ROOT, PASSERMARK_LANG="de", PASSERMARK_WORKERS="1")
    return subprocess.run([sys.executable, "-m", "pdfdruck.cli", *args], capture_output=True, text=True,
                          env=env, cwd=ROOT, timeout=300)


def test_cli_preset_by_name():
    from pdfdruck.cmyk import ManipSettings
    presets.save("manip", "A5 zuschneiden", ManipSettings(crop=True, crop_size="A5"))
    r = _cli("presets", "manip")
    assert r.returncode == 0 and r.stdout.strip() == "A5 zuschneiden", (r.stdout, r.stderr)
    out = os.path.join(TMP, "a5.pdf")
    r = _cli("manip", SAMPLE, out, "--preset", "A5 zuschneiden", "--quiet")
    assert r.returncode == 0, r.stderr
    import pypdfium2 as pdfium
    d = pdfium.PdfDocument(out)
    w, h = d.get_page_size(0)
    d.close()
    assert abs(min(w, h) - 148 / 25.4 * 72) < 1.5, (w, h)
    r = _cli("manip", SAMPLE, out, "--preset", "gibtsnicht")
    assert r.returncode == 2 and "A5 zuschneiden" in r.stderr, r.stderr


def test_pdf_with_password():
    import pikepdf
    import pypdfium2 as pdfium
    from pdfdruck import printers, printjob
    caps = printers.pdf_caps()
    sess = type("S", (), {"caps_for": lambda self, n: caps})()
    out = os.path.join(TMP, "geschützt.pdf")
    doc = pdfium.PdfDocument(SAMPLE)
    printjob.submit_document(doc, "x.pdf", sess, printers.PDF_TARGET, [0], LayoutSettings(),
                             1, True, False, values=dict(caps.defaults(), __out__=out, __password__="geheim"))
    doc.close()
    try:
        pikepdf.open(out).close()
        raise AssertionError("ohne Passwort lesbar")
    except pikepdf.PasswordError:
        pass
    with pikepdf.open(out, password="geheim") as p:
        assert len(p.pages) == 1 and p.is_encrypted
    assert not os.path.exists(out + ".part")


GUI = r'''
import sys, types
from pdfdruck.gui import viewer
viewer.PageView._dpi_scale = lambda self: 1.0
viewer.PageView.page_zoom = lambda self, i: 1.0
from pdfdruck import config, l10n
from pdfdruck.gui.common import Session
import pypdfium2 as pdfium
w = viewer.MainWindow(types.SimpleNamespace(view_single=True, session=Session(config.BUILTIN), windows=[]))
w._set_doc(pdfium.PdfDocument(sys.argv[1]), sys.argv[1], "x.pdf", False)
assert w.workspace == "view"
for k in ("prep", "edit", "auto", "view", "prep"):
    w.set_workspace(k)
    assert w.workspace == k
assert l10n.load_settings()["workspace"] == "prep"
w2 = viewer.MainWindow(types.SimpleNamespace(view_single=True, session=Session(config.BUILTIN), windows=[]))
assert w2.workspace == "prep"                       # neues Fenster startet im zuletzt gewählten Bereich
# Bearbeiten einschalten wechselt in den Bereich Bearbeiten
w._edit_mode(True)
assert w.workspace == "edit"
w._open_presets_dir()
# Dialoge mit Preset-Leiste lassen sich bauen und Presets übernehmen
from pdfdruck.gui import objectsdialog as od, manipdialog as md
from pdfdruck import cutcontour, cmyk, presets
od._CutWorker.start = lambda self: None
od._CutWorker.isRunning = lambda self: False
presets.save_last("cutcontour", cutcontour.CutSettings(shape="heart", bleed_color="#ff0000"))
dlg = od.CutContourDialog(None, pdfium.PdfDocument(sys.argv[1]), 0)
dlg._load_settings(cutcontour.CutSettings(shape="rect"))
assert dlg._bcol == "#ff0000"                       # zuletzt verwendete Überfüller-Farbe übernommen
dlg.presetbar.refresh()
s = Session(config.BUILTIN)
md_dlg = md.ManipDialog(None, pdfium.PdfDocument(sys.argv[1]), s, 0, "all")
md_dlg.panel.load_settings(cmyk.ManipSettings(crop=True, crop_size="A5"))
from pdfdruck.gui import printdialog as pd
from pdfdruck.layout import LayoutSettings
pdlg = pd.PrintDialog(None, pdfium.PdfDocument(sys.argv[1]), sys.argv[1], 0, s)
pdlg._load_layout(LayoutSettings(handling="booklet", cols=2, rows=3))
print("ok")
'''


def test_gui_workspaces_and_presetbars():
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.join(HERE, "_qtstub"), ROOT, HERE]),
               QT_QPA_PLATFORM="offscreen")
    r = subprocess.run([sys.executable, "-c", GUI, SAMPLE], capture_output=True, text=True, env=env, timeout=300)
    assert r.returncode == 0 and r.stdout.strip().endswith("ok"), r.stdout[-2000:] + r.stderr[-4000:]


def test_shortcuts_unique():
    """Jedes Tastenkürzel im Hauptfenster nur einmal (sonst löst Qt keines von beiden aus)."""
    src = open(os.path.join(ROOT, "pdfdruck", "gui", "viewer.py"), encoding="utf-8").read()
    keys = re.findall(r'\bA\(tr\("[^"]*"\),\s*[^\n]*?,\s*"((?:Ctrl|Alt|Shift|F\d|Home|End)[^"]*)"', src)
    seen = {}
    for k in keys:
        seen[k] = seen.get(k, 0) + 1
    dup = sorted(k for k, n in seen.items() if n > 1)
    assert len(keys) > 15, keys
    assert not dup, dup


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
