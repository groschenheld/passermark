# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Datei → Eigenschaften (echtes Qt, ohne Bildschirm): Speicherort, Dokument, Seiten, Schriften, Prüfung –
    für eine gespeicherte Datei und für ein nur im Speicher vorhandenes Dokument (Zusammenführen)."""
import io, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

SCRIPT = r'''
import io, os, sys, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication, QLabel, QTableWidget, QMessageBox
app = QApplication(sys.argv)
for n in ("critical", "warning", "information"):
    setattr(QMessageBox, n, staticmethod(lambda *a, **k: None))
import pikepdf
from reportlab.pdfgen import canvas
MM = 72 / 25.4
d = sys.argv[1]
p = os.path.join(d, "karten.pdf")
b = io.BytesIO(); c = canvas.Canvas(b); c.setTitle("Visitenkarten Muster"); c.setAuthor("Hias")
for i in range(3):
    c.setPageSize((91 * MM, 61 * MM)); c.drawString(20, 20, f"Karte {i}"); c.showPage()
c.save()
pk = pikepdf.open(io.BytesIO(b.getvalue()))
for pg in pk.pages:
    pg.TrimBox = [3 * MM, 3 * MM, 88 * MM, 58 * MM]; pg.BleedBox = [0, 0, 91 * MM, 61 * MM]
pk.save(p)
from pdfdruck.app import Controller
from pdfdruck.gui.propsdialog import PropertiesDialog
ctl = Controller()
ctl.open_paths([p]); w = ctl.windows[-1]

def texts(widget):
    return " | ".join(l.text() for l in widget.findChildren(QLabel))

def wait(dlg):
    t = time.time()
    while dlg.info is None and time.time() - t < 60:
        app.processEvents(); time.sleep(0.02)

dlg = PropertiesDialog(w); dlg.show(); wait(dlg)
assert dlg.info is not None
f = texts(dlg.tabs.widget(0))
assert d in f and "gespeichert" in f and "Bytes" in f, f
doc = texts(dlg.doc_w)
assert "Visitenkarten Muster" in doc and "Hias" in doc, doc
tab = dlg.pages_w.findChildren(QTableWidget)[0]
assert tab.rowCount() == 3 and tab.item(0, 1).text() == "91 × 61" and tab.item(0, 4).text() == "85 × 55", \
    (tab.item(0, 1).text(), tab.item(0, 4).text())
assert tab.item(0, 5).text() == "3"
fonts = dlg.fonts_w.findChildren(QTableWidget)
assert fonts and fonts[0].item(0, 0).text() == "Helvetica"
assert "Fehler" in texts(dlg.check_w)
dlg.done(0)
# nur im Speicher: zusammengeführt
ctl.merge_into_window([p, p]); m = ctl.windows[-1]
dlg = PropertiesDialog(m); dlg.show(); wait(dlg)
f = texts(dlg.tabs.widget(0))
assert "Arbeitsspeicher" in f and p in f, f
assert dlg.info["pages"] == 6
dlg.done(0)
print("OK")
'''


def test_properties_dialog():
    try:
        import PySide6.QtWidgets  # noqa: F401
    except Exception:
        print("   (übersprungen: kein Qt)")
        return
    d = tempfile.mkdtemp(prefix="pm-props-")
    env = dict(os.environ, PYTHONPATH=ROOT + os.pathsep + os.environ.get("PYTHONPATH", ""), PASSERMARK_LANG="de",
               PASSERMARK_RENDER="local", HOME=d, XDG_CONFIG_HOME=os.path.join(d, "cfg"))
    r = subprocess.run([sys.executable, "-c", SCRIPT, d], capture_output=True, text=True, env=env, timeout=300)
    assert r.returncode == 0 and "OK" in r.stdout, r.stdout[-2000:] + r.stderr[-3000:]


if __name__ == "__main__":
    test_properties_dialog()
    print("ok test_properties_dialog")
