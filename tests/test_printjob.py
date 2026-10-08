# SPDX-License-Identifier: GPL-3.0-or-later
# pdfToolkit – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
import os, sys
import os as _os
_os.environ.setdefault("PDFTOOLKIT_LANG", "de")   # Tests prüfen deutsche Texte
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import test_backend as tb                      # Fake-pycups
from pdfdruck import printers, printjob, layout, config

SENT = []
class Conn(tb.FakeConn):
    def printFile(self, printer, path, title, opts):
        import pypdfium2 as p
        d = p.PdfDocument(path); SENT.append((printer, title, dict(opts), len(d), d.get_page_size(0))); d.close()
        return 42
    def getPrinters(self): return {"canon": {"printer-info": "Canon", "printer-state": 3}}
    def getDefault(self): return "canon"
printers.cups.Connection = Conn

class FakeSession:
    def __init__(self, **lay):
        self.cfg = config.BUILTIN; self.printer = None; self.layout = layout.LayoutSettings(**lay)
        self.copies, self.collate, self.subset, self.reverse = 2, True, "all", False
        self._caps = {}
    def caps_for(self, n): return self._caps.setdefault(n, printers.load_caps(n))
    def values_for(self, n): return self.caps_for(n).defaults()
    def color_for(self, n): return ("", "relative")

HERE = os.path.dirname(__file__)

def test_print_pdf_defaults():
    SENT.clear()
    pr, jid = printjob.print_file(os.path.join(HERE, "sample.pdf"), FakeSession())
    printer, title, opts, n, size = SENT[0]
    assert pr == "canon" and jid == 42 and n == 7 and opts["copies"] == "2"
    assert opts["print-scaling"] == "none" and opts["InputSlot"] == "Auto"

def test_print_booklet_sets_tumble():
    SENT.clear()
    printjob.print_file(os.path.join(HERE, "sample.pdf"), FakeSession(handling="booklet"))
    opts = SENT[0][2]
    # Fake-PPD kennt nur DuplexNoTumble -> kein Tumble-Wert vorhanden, darf NICHT NoTumble setzen
    assert opts["Duplex"] == "None"

def test_print_image():
    from PIL import Image
    p = "/tmp/pdfdruck_test_img.jpg"; Image.new("RGB", (1000, 500), "red").save(p, dpi=(100, 100))
    SENT.clear()
    printjob.print_file(p, FakeSession(mode="actual"))
    assert SENT[0][3] == 1

def test_auto_tray_on_print():
    SENT.clear()
    sess = FakeSession()
    sess.cfg = dict(config.BUILTIN)
    sess.cfg["printers"] = {"canon": {"tray_auto": True, "trays": [
        {"slot": "Cas3", "size": "A3", "weight": 80}, {"slot": "Cas1", "size": "A4", "weight": 80},
        {"slot": "Manual", "size": "A4", "weight": 120}]}}
    printjob.print_file(os.path.join(HERE, "sample.pdf"), sess)
    assert SENT[0][2]["InputSlot"] == "Cas1"                # A4-Standard -> erste A4-Lade
    sess.weights = {"canon": 120}
    SENT.clear(); printjob.print_file(os.path.join(HERE, "sample.pdf"), sess)
    assert SENT[0][2]["InputSlot"] == "Manual"              # 120 g -> Mehrzweckfach


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("ok", k)
