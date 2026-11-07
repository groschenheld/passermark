# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# Public License, Version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
import os, sys
import os as _os
_os.environ.setdefault("PASSERMARK_LANG", "de")   # tests check German texts
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

def test_custom_size_pdf_and_cups():
    """Custom formats: stored permanently, selectable and spooled with "Save as PDF" and with CUPS printers."""
    import tempfile
    os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
    os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]
    printers.save_custom_sizes([{"name": "Banner", "w": 330, "h": 1000}])
    v = printers.custom_value(330, 1000)
    caps = printers.pdf_caps(); printers.apply_custom_sizes(caps)
    out = os.path.join(os.environ["XDG_CONFIG_HOME"], "banner.pdf")
    S = type("S", (), {"caps_for": lambda self, n: caps})()
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(os.path.join(HERE, "sample.pdf"))
    printjob.submit_document(doc, "x", S, printers.PDF_TARGET, [0], layout.LayoutSettings(),
                             values=dict(caps.defaults(), PageSize=v, __out__=out))
    w, h = pdfium.PdfDocument(out).get_page_size(0)
    assert round(w / 72 * 25.4) == 330 and round(h / 72 * 25.4) == 1000
    # CUPS-Drucker: seit 1.11.1 KEINE ★-Formate mehr (nur „Als PDF speichern") – Geräte schneiden sonst falsch
    sess = FakeSession()
    caps_c = sess.caps_for("canon")
    printers.apply_custom_sizes(caps_c)
    key = caps_c.roles["pagesize"]
    assert v not in [c.value for c in caps_c.options[key].choices]
    assert not any(str(k).startswith(printers.CUSTOM_PREFIX) for k in caps_c.page_sizes)


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


def test_booklet_spreads_print_pdf():
    """Broschüre als Druckbögen über den echten Druckweg („Als PDF speichern“): A5-Broschüre mit Anschnitt
    -> aufgeklappte Bögen 296 × 210 mm, mit der Nutzen-Logik aufs Blatt, Schnittmarken an."""
    import io
    import tempfile
    import pikepdf
    import pypdfium2 as pdfium
    from reportlab.pdfgen import canvas
    MMx = 72 / 25.4
    os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
    b = io.BytesIO(); c = canvas.Canvas(b)
    for i in range(8):
        c.setPageSize((154 * MMx, 216 * MMx)); c.setFillColorRGB(i / 8, 0.2, 0.5)
        c.rect(0, 0, 154 * MMx, 216 * MMx, fill=1, stroke=0); c.showPage()
    c.save()
    pk = pikepdf.open(io.BytesIO(b.getvalue()))
    for pg in pk.pages:
        pg.TrimBox = [3 * MMx, 3 * MMx, 151 * MMx, 213 * MMx]
    o = io.BytesIO(); pk.save(o)
    doc = pdfium.PdfDocument(o.getvalue())
    caps = printers.pdf_caps()
    S = type("S", (), {"caps_for": lambda self, n: caps})()
    out = os.path.join(os.environ["XDG_CONFIG_HOME"], "bk.pdf")
    s = layout.LayoutSettings(handling="booklet", booklet_nutzen=True, crop_marks=True, sr_join="edge", bleed_mm=3)
    printjob.submit_document(doc, "x", S, printers.PDF_TARGET, list(range(8)), s,
                             values=dict(caps.defaults(), __out__=out))
    r = pdfium.PdfDocument(out)
    assert len(r) == 4                                     # 8 Seiten -> 2 Bögen -> 4 Bogenseiten
    spreads, pages, ss, _n = layout.spread_source(doc, list(range(8)), s)
    w, h = spreads.get_page_size(0)
    assert (round(w / MMx), round(h / MMx)) == (302, 216) and ss.step_repeat   # 296 × 210 + 2 × 3 mm


def test_borderless():
    """Randlos: Papiervariante (PPD/Windows), eigene Option (Gutenprint, Canon), IPP media-col; Erweiterung erkannt;
    Laser ohne Randlos; mit Anschnitt im Dokument liegt das Endformat genau auf dem Blatt."""
    import io
    import pikepdf
    import pypdfium2 as pdfium
    from reportlab.pdfgen import canvas
    from pdfdruck.printers import PrinterCaps, Option, Choice
    mm = 72 / 25.4
    c = PrinterCaps("Epson", "ppd")
    sizes = {"A4": (595.3, 841.9), "A4.Borderless": (595.3, 841.9), "A3": (841.9, 1190.6),
             "4x6": (288, 432), "4x6.FB": (288, 432)}
    c.options["PageSize"] = Option("PageSize", "Papier", "Allg", [Choice(k, k) for k in sizes], "A4")
    c.options["Expansion"] = Option("Expansion", "Borderless Expansion", "Allg",
                                    [Choice("Min", "Min"), Choice("Max", "Max")], "Min")
    for k, (w, h) in sizes.items():
        c.page_sizes[k] = (w, h)
        c.imageable[k] = (0, 0, w, h) if "." in k else (8, 8, w - 8, h - 8)
    printers._assign_roles(c)
    assert c.borderless_sizes() == {"A4": "A4.Borderless", "4x6": "4x6.FB"} and c.borderless_expand_key() == "Expansion"
    v, ok = c.set_borderless({"PageSize": "A4"}, True)
    assert ok and v["PageSize"] == "A4.Borderless" and c.is_borderless(v) and c.sheet_for(v)[2] is None
    assert c.set_borderless(v, False)[0]["PageSize"] == "A4"
    assert c.set_borderless({"PageSize": "A3"}, True) == ({"PageSize": "A3"}, False)      # A3 gibt's nicht randlos
    g = PrinterCaps("Gutenprint", "ppd")
    g.options["PageSize"] = Option("PageSize", "Papier", "Allg", [Choice("A4", "A4")], "A4")
    g.page_sizes["A4"], g.imageable["A4"] = (595.3, 841.9), (9, 9, 586, 832)
    g.options["StpFullBleed"] = Option("StpFullBleed", "Borderless", "Allg", [Choice("False", "Off"), Choice("True", "On")],
                                       "False")
    printers._assign_roles(g)
    v, ok = g.set_borderless({"PageSize": "A4"}, True)
    assert ok and v["StpFullBleed"] == "True" and g.sheet_for(v)[2] is None
    k = PrinterCaps("Canon", "ppd")
    k.options["CNIJMarginType"] = Option("CNIJMarginType", "Randtyp", "Allg", [Choice("0", "Mit Rand"), Choice("1", "Randlos")],
                                         "0")
    k.options["CNIJExtension"] = Option("CNIJExtension", "Umfang der Erweiterung", "Allg",
                                        [Choice("0", "0"), Choice("3", "3")], "0")
    assert k.borderless_option() == ("CNIJMarginType", "1", "0") and k.borderless_expand_key() == "CNIJExtension"
    i = PrinterCaps("IPP", "ipp")
    i.options["media"] = Option("media", "Papier", "Allg", [Choice("iso_a4_210x297mm", "A4")], "iso_a4_210x297mm")
    i.page_sizes["iso_a4_210x297mm"], i.ipp_zero_margin = (595.28, 841.89), True
    printers._assign_roles(i)
    v, ok = i.set_borderless({"media": "iso_a4_210x297mm"}, True)
    col = i.job_options(v)["media-col"]
    assert ok and "x-dimension=21000 y-dimension=29700" in col and "media-left-margin=0" in col
    laser = PrinterCaps("Laser", "ppd")
    laser.options["PageSize"] = Option("PageSize", "Papier", "Allg", [Choice("A4", "A4")], "A4")
    printers._assign_roles(laser)
    assert not laser.can_borderless()
    try:
        printjob.apply_borderless(laser, {"PageSize": "A4"}, layout.LayoutSettings(borderless=True))
        raise AssertionError("Laser kann nicht randlos")
    except RuntimeError:
        pass
    _v, lay = printjob.apply_borderless(c, {"PageSize": "A4.Borderless"}, layout.LayoutSettings())
    assert lay.borderless                                     # randloses Papier gewählt -> Layout randlos
    # Dokument mit 3 mm Anschnitt: Endformat genau aufs Blatt, Anschnitt über den Rand
    buf = io.BytesIO()
    cv = canvas.Canvas(buf, pagesize=(216 * mm, 303 * mm))
    cv.setFillColorRGB(.8, .3, .1)
    cv.rect(0, 0, 216 * mm, 303 * mm, fill=1)
    cv.save()
    pdf = pikepdf.open(io.BytesIO(buf.getvalue()))
    pdf.pages[0].TrimBox = [3 * mm, 3 * mm, 213 * mm, 300 * mm]
    out = io.BytesIO()
    pdf.save(out)
    doc = pdfium.PdfDocument(out.getvalue())
    sheet = layout.Sheet(595.28, 841.89, (8, 8, 587, 833))
    s = layout.LayoutSettings(borderless=True)
    pl = layout.plan([doc.get_page_size(0)], [0], sheet, s, layout.page_trims(doc))[0].placements[0]
    assert abs(pl.scale - 1) < 0.001 and abs(pl.x) < 0.1 and abs(pl.w - 595.28) < 0.5 and all(pl.trim_show_edge)
    im = layout.impose_with(doc, sheet, layout.plan([doc.get_page_size(0)], [0], sheet, s, layout.page_trims(doc)),
                            s)[0].render(scale=0.5).to_pil().convert("RGB")
    assert im.getpixel((0, 0)) != (255, 255, 255)           # Farbe bis in die Ecke


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("ok", k)
