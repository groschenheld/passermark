# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Papierformate (1.15.1): Maße immer zuerst vom Drucker – PaperDimension, sonst der PostScript-Code der PPD,
    sonst Name/Anzeigetext, sonst die eine gemeinsame Tabelle. Fall aus der Praxis: Epson-PPD mit selbst
    eingetragenem SRA4 ohne *PaperDimension (früher: „Maße unbekannt – A4 angenommen“), Komma statt Punkt."""
import os, re, sys, tempfile, types
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ.setdefault("PASSERMARK_LANG", "de")
from pdfdruck import papersizes, printers

MM = 72 / 25.4
PPD = r'''*PPD-Adobe: "4.3"
*OpenUI *PageSize: PickOne
*OrderDependency: 10 AnySetup *PageSize
*DefaultPageSize: A4
*PageSize A4/A4: "<</PageSize[595.20 841.68]/ImagingBBox null>>setpagedevice"
*PageSize TA4/A4 (Borderless): "<</PageSize[595.20 841.68]/ImagingBBox null>>setpagedevice"
*PageSize A3/A3: "<</PageSize[841.68 1190.40]/ImagingBBox null>>setpagedevice"
*PageSize SRA4/SRA4: "<</PageSize[637.8 907.09]/ImagingBBox null>>setpagedevice"
*PageSize SRA3/SRA3: "<</PageSize[907.09 1275.6]/ImagingBBox null>>setpagedevice"
*PageSize KOMMA/Komma: "<</PageSize[636,75 905,6]/ImagingBBox null>>setpagedevice"
*PageSize 8K/8K 270 x 390 mm: "<</ImagingBBox null>>setpagedevice"
*PageSize 4X7/16<3A>9 wide (4 x 7<2E>11 in): "<</ImagingBBox null>>setpagedevice"
*PageSize ISOB4/B4 (ISO): "<</ImagingBBox null>>setpagedevice"
*PageSize RAETSEL/Irgendwas: "<</ImagingBBox null>>setpagedevice"
*CloseUI: *PageSize
*OpenUI *PageRegion: PickOne
*PageRegion SRA4/SRA4: "<</PageSize[637.8 907.09]/ImagingBBox null>>setpagedevice"
*CloseUI: *PageRegion
*DefaultImageableArea: A4
*ImageableArea A4/A4: "8.40 8.40 586.80 833.28"
*ImageableArea TA4/A4 (Borderless): "0 0 595.20 841.68"
*ImageableArea A3/A3: "8.40 8.40 833.28 1182.00"
*DefaultPaperDimension: A4
*PaperDimension A4/A4: "595.20 841.68"
*PaperDimension TA4/A4 (Borderless): "595.20 841.68"
*PaperDimension A3/A3: "841.68 1190.40"
'''


class _FakePPD:
    """So viel von pycups.PPD, wie _caps_from_ppd braucht – aus dem PPD-Text."""
    def __init__(self, path):
        text = open(path, encoding="latin-1").read()
        ch = [{"choice": m.group(1), "text": m.group(2)} for m in
              re.finditer(r'^\*PageSize ([^/:\s]+)/([^:]*):', text, re.M)]
        opt = types.SimpleNamespace(keyword="PageSize", text="Media Size", choices=ch, defchoice="A4")
        self.optionGroups = [types.SimpleNamespace(name="General", text="General", options=[opt], subgroups=[])]

    def localize(self):
        pass

    def findAttr(self, name, spec):
        return None


def caps_from(text):
    d = tempfile.mkdtemp(prefix="pm-ppd-")
    p = os.path.join(d, "test.ppd")
    open(p, "w", encoding="latin-1").write(text)
    old = printers.cups
    printers.cups = types.SimpleNamespace(PPD=_FakePPD)
    try:
        return printers._caps_from_ppd("Epson", p)
    finally:
        printers.cups = old


def mm(caps, v):
    w, h = caps.page_sizes[v]
    return round(w / MM, 1), round(h / MM, 1)


def test_sources_and_sizes():
    caps = caps_from(PPD)
    assert mm(caps, "A4") == (210.0, 296.9) and caps.size_source["A4"] == "driver"
    assert mm(caps, "SRA4") == (225.0, 320.0) and caps.size_source["SRA4"] == "code"      # der Praxisfall
    assert mm(caps, "SRA3") == (320.0, 450.0) and caps.size_source["SRA3"] == "code"
    assert mm(caps, "8K") == (270.0, 390.0) and caps.size_source["8K"] == "text"
    assert mm(caps, "4X7") == (101.6, 180.6) and caps.size_source["4X7"] == "text"           # <2E> = "."
    assert mm(caps, "ISOB4") == (250.0, 353.0) and caps.size_source["ISOB4"] == "table"
    assert "RAETSEL" not in caps.page_sizes
    # Komma statt Punkt: gemeint ist es trotzdem – Maße übernommen, Fehler gemeldet
    assert mm(caps, "KOMMA") == (224.6, 319.5) and caps.size_problems["KOMMA"]
    # bedruckbarer Bereich: vom Treiber, randlos = ganzes Blatt, sonst die Ränder der anderen Formate
    assert caps.imageable["A4"] == (8.4, 8.4, 586.8, 833.28)
    assert caps.imageable["TA4"] == (0.0, 0.0, 595.2, 841.68)
    l, b, r, t = caps.imageable["SRA4"]
    assert (round(l, 2), round(b, 2)) == (8.4, 8.4) and round(637.8 - r, 2) == 8.4 and round(907.09 - t, 2) == 8.4


def test_dialog_notes():
    caps = caps_from(PPD)
    ps = "PageSize"
    assert printers.size_note(caps, {ps: "A4"}) == ""
    assert printers.size_note(caps, {ps: "SRA4"}) == ""                 # exakt aus der PPD – kein Grund zur Warnung
    n = printers.size_note(caps, {ps: "KOMMA"}, "Komma")
    assert "Komma statt Punkt" in n and '*PaperDimension KOMMA/KOMMA: "636.75 905.6"' in n, n
    n = printers.size_note(caps, {ps: "ISOB4"}, "B4 (ISO)")
    assert "eingebauten Formattabelle" in n and '*PaperDimension ISOB4/ISOB4: "708.66 1000.63"' in n, n
    n = printers.size_note(caps, {ps: "RAETSEL"}, "Irgendwas")
    assert "unbekannt – A4 angenommen" in n and "*PaperDimension RAETSEL/RAETSEL" in n, n
    # „Als PDF speichern“ mit „Wie Dokument“: keine Warnung
    pdf = printers.pdf_caps()
    assert printers.size_note(pdf, {ps: printers.PDF_DOC_SIZE}) == ""
    assert printers.size_note(pdf, {ps: "SRA4"}) == ""                  # neu in der Liste


def test_one_table_and_names():
    for name, want in (("SRA4", (225, 320)), ("DIN A4", (210, 297)), ("sra-2", (450, 640)), ("A3+", (329, 483)),
                       ("B4", (257, 364)), ("ISOB4", (250, 353)), ("JIS B4", (257, 364))):
        assert papersizes.lookup(name) == want, name
    assert printers.STD_SIZES_MM is papersizes.PAPER_MM
    from pdfdruck import layout, pdfmanip
    assert pdfmanip.FORMATS["SRA4"] == (225, 320) and pdfmanip.FORMATS["B4"] == (250, 353)   # Dialog: ISO
    s = layout.ImposeSettings(sheet="SRA4").sheet_obj()
    assert round(s.width / MM) == 225 and round(s.height / MM) == 320
    w, h, bl = printers.std_size("A4 (Borderless)")
    assert bl and round(w / MM) == 210
    w, h, bl = printers.std_size("Custom.85x55mm")
    assert (round(w / MM), round(h / MM), bl) == (85, 55, False)
    assert printers.std_size("Custom.300x400")[:2] == (300.0, 400.0)       # CUPS ohne Einheit: pt
    assert papersizes.size_from_text("10 x 15 cm (4 x 6 in)") == (100 * MM, 150 * MM)


def test_parse_keeps_old_interface():
    d = tempfile.mkdtemp(prefix="pm-ppd-")
    p = os.path.join(d, "x.ppd")
    open(p, "w", encoding="latin-1").write(PPD)
    dims, areas = printers.parse_ppd_dimensions(p)
    assert set(dims) == {"A4", "TA4", "A3"} and "A4" in areas


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
