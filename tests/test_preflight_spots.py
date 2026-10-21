# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Prüfung (1.16): jeder Befund sagt, wo er ist (Seite, Bereich, was genau) – Klick springt hin und markiert.
    Teil 1 ohne Oberfläche (Fundstellen), Teil 2 mit echtem Qt (Klick in der Liste, ◀ ▶, Markierung)."""
import io, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
os.environ.setdefault("PASSERMARK_LANG", "de")


def sample_pdf() -> bytes:
    """3 Seiten: S. 1 Text in nicht eingebetteter Arial (oben links), S. 2 ein 40 × 20 mm-Bild mit 50 dpi unten rechts
        in RGB, S. 3 dasselbe Bild nochmal oben in der Mitte."""
    from PIL import Image
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    import test_preflight as tp
    MM = 72 / 25.4
    img = Image.new("RGB", (79, 39), (200, 30, 30))
    b = io.BytesIO()
    c = canvas.Canvas(b, pagesize=(210 * MM, 297 * MM))
    c.drawString(20 * MM, 270 * MM, "Seite 1")
    c.showPage()
    c.drawImage(ImageReader(img), 150 * MM, 20 * MM, 40 * MM, 20 * MM)
    c.showPage()
    c.drawImage(ImageReader(img), 85 * MM, 250 * MM, 40 * MM, 20 * MM)
    c.showPage()
    c.save()
    import pikepdf
    pdf = pikepdf.open(io.BytesIO(b.getvalue()))
    for pg in pdf.pages[:1]:                      # Helvetica -> nicht eingebettete Arial (wie test_preflight)
        for _n, f in (pg.Resources.get("/Font") or {}).items():
            f.BaseFont = pikepdf.Name("/ArialMT")
    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()


def test_spots_without_gui():
    from pdfdruck import preflight
    rep = preflight.analyze(sample_pdf(), True, True)
    font = next(i for i in rep.issues if "ArialMT" in i.message)
    sp = font.spots[0]
    assert sp.page == 1 and sp.box is not None and "oben links" in preflight.where_text(rep, sp), \
        preflight.where_text(rep, sp)
    imgs = [i for i in rep.issues if i.category == "image" and "dpi" in i.message]
    where = [preflight.where_text(rep, s) for i in imgs for s in i.spots]
    assert any(w.startswith("Seite 2 – unten rechts, 40 × 20 mm") for w in where), where
    assert any(w.startswith("Seite 3 – oben, 40 × 20 mm") for w in where), where
    assert all("50 dpi" in w for w in where), where
    # jeder Befund hat mindestens eine Fundstelle
    assert all(i.spots for i in rep.issues if i.pages)
    # auch im Bericht und in inspect --json
    txt = preflight.report_text(rep)
    assert "· Seite 2 – unten rechts" in txt
    from pdfdruck import docinfo
    d = docinfo._check(sample_pdf())
    spots = [s for i in d["issues"] for s in i["spots"]]
    assert any(s["box_pt"] and s["where"].startswith("Seite 2") for s in spots)


GUI = r'''
import os, sys, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, sys.argv[2])
from PySide6.QtWidgets import QApplication, QMessageBox
app = QApplication(sys.argv)
for n in ("critical", "warning", "information"):
    setattr(QMessageBox, n, staticmethod(lambda *a, **k: None))
import test_preflight_spots as T
from pdfdruck import preflight
p = os.path.join(sys.argv[1], "probe.pdf")
open(p, "wb").write(T.sample_pdf())
from pdfdruck.app import Controller
ctl = Controller()
ctl.open_paths([p]); w = ctl.windows[-1]
for _ in range(100):
    app.processEvents(); time.sleep(0.02)
rep = preflight.analyze(T.sample_pdf(), True, True)
w._pf_show(rep)
panel, view, tree = w.pf_panel, w.view, w.pf_panel.tree
rgb = next(tree.topLevelItem(k) for k in range(tree.topLevelItemCount()) if "RGB" in tree.topLevelItem(k).text(1))
assert rgb.childCount() == 2, rgb.childCount()                # Bild auf S. 2 und S. 3
tree.setCurrentItem(rgb); panel._issue_clicked(rgb, 1)
assert view.current == 1 and view.pf_mark and view.pf_mark[0] == 1 and view.pf_mark[1] is not None, view.pf_mark
assert "1/2" in panel.lbl_nav.text(), panel.lbl_nav.text()
panel._step_spot(+1)
assert view.current == 2 and view.pf_mark[0] == 2 and "2/2" in panel.lbl_nav.text()
ch = rgb.child(0); tree.setCurrentItem(ch); panel._issue_clicked(ch, 1)
assert view.current == 1
panel._go(preflight.Spot(3))                                   # ohne Bereich: ganze Seite markiert
assert view.current == 2 and view.pf_mark == (2, None)
w.repaint(); app.processEvents()                               # Zeichnen der Markierung wirft nichts
view._clear_spot()
assert view.pf_mark is None
print("OK")
'''


def test_click_jumps_and_marks():
    try:
        import PySide6.QtWidgets  # noqa: F401
    except Exception:
        print("   (übersprungen: kein Qt)")
        return
    d = tempfile.mkdtemp(prefix="pm-pfspots-")
    env = dict(os.environ, PYTHONPATH=ROOT + os.pathsep + os.environ.get("PYTHONPATH", ""), PASSERMARK_LANG="de",
               PASSERMARK_RENDER="local", HOME=d, XDG_CONFIG_HOME=os.path.join(d, "cfg"))
    r = subprocess.run([sys.executable, "-c", GUI, d, HERE], capture_output=True, text=True, env=env, timeout=300)
    assert r.returncode == 0 and "OK" in r.stdout, r.stdout[-2000:] + r.stderr[-3000:]


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
