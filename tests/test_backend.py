# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Logiktests ohne echtes CUPS (Attrappen für pycups)."""
import importlib.machinery, importlib.util, json, os, sys, types
import os as _os
_os.environ.setdefault("PASSERMARK_LANG", "de")   # Tests prüfen deutsche Texte
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---- Fake pycups --------------------------------------------------------
class Opt:
    def __init__(s, kw, text, choices, d): s.keyword, s.text, s.defchoice = kw, text, d; s.choices = [{"choice": c, "text": t} for c, t in choices]; s.conflicted = False
class Grp:
    def __init__(s, name, text, opts): s.name, s.text, s.options, s.subgroups = name, text, opts, []
class Attr:
    def __init__(s, v): s.value = v
class FakePPD:
    def __init__(s, f):
        s.optionGroups = [
            Grp("General", "Allgemein", [
                Opt("PageSize", "Seitenformat", [("A4", "A4"), ("A3", "A3")], "A4"),
                Opt("PageRegion", "x", [("A4", "A4")], "A4"),
                Opt("InputSlot", "Papierzufuhr", [("Auto", "Automatisch"), ("Cas1", "Kassette 1"), ("Cas3", "Kassette 3"), ("Manual", "Mehrzweckfach")], "Auto"),
                Opt("Duplex", "Duplex", [("None", "Aus"), ("DuplexNoTumble", "Lange Kante")], "None")]),
            Grp("Finishing", "Endverarbeitung", [Opt("CNStaple", "Heften", [("None", "Aus"), ("TopLeft", "Oben links")], "None")]),
            Grp("InstallableOptions", "Installierbar", [Opt("CNFinisher", "Finisher", [("None", "Keiner"), ("InnerL1", "Inner Finisher-L1")], "None")]),
        ]
        s.marked = {}
    def localize(s): pass
    def findAttr(s, name, spec=None):
        return {("PaperDimension", "A4"): Attr("595 842"), ("PaperDimension", "A3"): Attr("842 1191"),
                ("ImageableArea", "A4"): Attr("12 12 583 830")}.get((name, spec))
    def markDefaults(s): s.marked = {}
    def markOption(s, k, v): s.marked[k] = v
    def conflicts(s):
        bad = s.marked.get("CNStaple") == "TopLeft" and s.marked.get("InputSlot") == "Manual"
        for g in s.optionGroups:
            for o in g.options: o.conflicted = bad and o.keyword in ("CNStaple", "InputSlot")
        return 1 if bad else 0
    def findOption(s, k):
        return next((o for g in s.optionGroups for o in g.options if o.keyword == k), None)
class FakeConn:
    def getPPD(s, n):
        if n == "ipp": raise RuntimeError("no ppd")
        p = "/tmp/fake.ppd"; open(p, "w").close(); return p
    def getPrinterAttributes(s, n, requested_attributes=None):
        return {"media-supported": ["iso_a4_210x297mm", "na_letter_8.5x11in"], "media-default": "iso_a4_210x297mm",
                "media-source-supported": ["auto", "tray-1", "tray-2", "manual"], "media-source-default": "auto",
                "sides-supported": ["one-sided", "two-sided-long-edge"], "sides-default": "one-sided",
                "print-quality-supported": [3, 4, 5], "print-quality-default": 4,
                "media-left-margin-supported": [300, 0], "media-right-margin-supported": [300],
                "media-top-margin-supported": [300], "media-bottom-margin-supported": [300]}
cupsmod = types.SimpleNamespace(PPD=FakePPD, Connection=FakeConn)

from pdfdruck import printers
printers.cups = cupsmod

def test_ppd():
    c = printers.load_caps("canon")
    assert c.backend == "ppd" and "PageRegion" not in c.options
    assert c.roles["source"] == "InputSlot" and c.roles["duplex"] == "Duplex"
    assert [x.value for x in c.options["InputSlot"].choices] == ["Auto", "Cas1", "Cas3", "Manual"]
    assert c.options["CNFinisher"].installable
    v = c.defaults(); assert "CNFinisher" not in v
    v.update({"CNStaple": "TopLeft", "InputSlot": "Manual"})
    assert set(c.conflicts(v)) == {"CNStaple", "InputSlot"}
    jo = c.job_options(v)
    assert jo["InputSlot"] == "Manual" and "CNFinisher" not in jo and "PageRegion" not in jo
    w, h, ia = c.sheet_for({"PageSize": "A3"}); assert (w, h) == (842, 1191) and ia is None
    assert c.sheet_for(v)[2] == (12, 12, 583, 830)

def test_ipp():
    c = printers.load_caps("ipp")
    assert c.backend == "ipp" and c.roles["pagesize"] == "media" and c.roles["source"] == "media-source"
    w, h, ia = c.sheet_for({"media": "na_letter_8.5x11in"})
    assert abs(w - 612) < .1 and abs(h - 792) < .1 and ia[0] == 0.0
    assert c.options["print-quality"].default == "4"

# ---- Helper-Validierung -------------------------------------------------
def test_helper_validate():
    from pdfdruck import cfgvalidate
    cfg = json.load(open(os.path.join(os.path.dirname(__file__), "..", "data", "defaults.example.json")))
    cfgvalidate.validate(cfg, "/etc/passermark/icc")
    for bad in [{"evil": 1}, {"layout": {"mode": "x"}}, {"printers": {"a;rm": {}}},
                {"printers": {"P": {"options": {"K": "v;rm -rf"}}}},
                {"color_profiles": [{"id": "x", "file": "/tmp/x.icc"}]},
                {"printers": {"P": {"devmode": "nicht base64!"}}}]:
        try:
            cfgvalidate.validate(bad, "/etc/passermark/icc"); raise AssertionError(bad)
        except ValueError:
            pass


def test_ppd_dimensions_from_file():
    ppd = "/tmp/_dim.ppd"
    open(ppd, "w").write('''*PPD-Adobe: "4.3"
*PaperDimension A4/A4: "595 842"
*PaperDimension A3/DIN A3: "842 1191"
*PaperDimension TA3/A3 (randlos): "842 1191"
*ImageableArea A3/DIN A3: "8.5 8.5 833.5 1182.5"
*ImageableArea TA3/A3 (randlos): "0 0 842 1191"
''')
    dims, areas = printers.parse_ppd_dimensions(ppd)
    assert dims["A3"] == (842, 1191) and areas["TA3"] == (0, 0, 842, 1191) and areas["A3"][0] == 8.5


def test_std_size_fallback():
    w, h, b = printers.std_size("A3"); assert round(w) == 842 and round(h) == 1191 and not b
    assert printers.std_size("TA4")[2] and printers.std_size("A4.Borderless")[2]
    assert round(printers.std_size("A3+")[0]) == 933
    c = printers.PrinterCaps("x", "ppd")
    c.options["PageSize"] = printers.Option("PageSize", "Papierformat", "g",
                                            [printers.Choice("A4", "A4"), printers.Choice("A3", "DIN A3")], "A4")
    c.roles["pagesize"] = "PageSize"
    c.page_sizes["A4"] = (595, 842)
    w, h, ia, exact = c.sheet_info({"PageSize": "A3"})      # A3 fehlt in page_sizes -> Tabelle
    assert exact and round(w) == 842 and round(h) == 1191


def test_canon_finishing_roles():
    P = printers
    c = P.PrinterCaps("ipV1350", "ppd")
    def opt(k, text, choices, d):
        c.options[k] = P.Option(k, P.i18n.option_text(k, text), "Finishing",
                                [P.Choice(v, P.i18n.choice_text(k, v, t, text)) for v, t in choices], d)
    opt("CNSaddleStitch", "Saddle Stitch", [("False", "Off"), ("True", "On")], "False")
    opt("StapleLocation", "Staple", [("None", "None"), ("TopLeft", "Top Left"), ("DoubleLeft", "Double Left")], "None")
    opt("CNPunch", "Hole Punch", [("None", "None"), ("2Holes", "2 Holes"), ("4Holes", "4 Holes")], "None")
    opt("CNFolding", "Folding", [("None", "None"), ("ZFold", "Z-Fold"), ("CFold", "C-Fold")], "None")
    opt("CNTrimming", "Trimming", [("None", "None"), ("Front", "Front-Edge Trim")], "None")
    P._assign_roles(c)
    assert c.roles["saddle"] == "CNSaddleStitch" and c.roles["staple"] == "StapleLocation"
    assert c.roles["punch"] == "CNPunch" and c.roles["fold"] == "CNFolding" and c.roles["trim"] == "CNTrimming"
    assert c.options["CNFolding"].choices[2].text == "Wickelfalz"
    assert c.options["StapleLocation"].text == "Heften"


def test_presets_validate():
    from pdfdruck import cfgvalidate
    cfg = {"printers": {"Canon_V1350": {"options": {}, "presets": [
        {"name": "Broschüre heften + falzen", "options": {"CNSaddleStitch": "True"}, "booklet": True}]}}}
    cfgvalidate.validate(cfg, "/etc/passermark/icc")
    cfg["printers"]["Canon_V1350"]["presets"][0]["evil"] = 1
    try:
        cfgvalidate.validate(cfg, "/etc/passermark/icc"); assert False
    except ValueError:
        pass


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("ok", k)
