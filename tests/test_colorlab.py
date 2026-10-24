# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Materialien und Messwerte (1.16): ΔE 2000, Papierweiß der Profile, CGATS/spotread einlesen, Zustände des
    Messgeräts, Profilvorschläge, Umwandlungs-Empfehlung, Prüfung der Admin-Einstellung."""
import copy
import os
import sys
import tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
os.environ.setdefault("PASSERMARK_LANG", "de")
from pdfdruck import cfgvalidate, colorlab
from test_softproof import cmyk_profile

TMP = tempfile.mkdtemp(prefix="pm-color-")

CGATS = """CGATS.17
ORIGINATOR "i1Profiler"
NUMBER_OF_FIELDS 9
BEGIN_DATA_FORMAT
SAMPLE_ID SAMPLE_NAME CMYK_C CMYK_M CMYK_Y CMYK_K LAB_L LAB_A LAB_B
END_DATA_FORMAT
NUMBER_OF_SETS 4
BEGIN_DATA
1 A1 0 0 0 0 93.10 0.90 4.10
2 A2 100 0 0 0 55.0 -37.0 -50.0
3 A3 0 0 0 0 93.30 0.70 3.90
4 A4 0 0 0 100 18.0 0.5 1.0
END_DATA
"""


def test_delta_e_reference_pairs():
    # Sharma, Wu, Dalal (2005) – Prüfpaare
    pairs = [((50, 2.6772, -79.7751), (50, 0, -82.7485), 2.0425), ((50, 3.1571, -77.2803), (50, 0, -82.7485), 2.8615),
             ((50, -1.3802, -84.2814), (50, 0, -82.7485), 1.0), ((50, 2.5, 0), (73, 25, -18), 27.1492),
             ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644)]
    for a, b, want in pairs:
        assert abs(colorlab.delta_e(a, b) - want) < 1e-4, (a, b, colorlab.delta_e(a, b))
    lab = (93.5, 0.8, 4.2)
    back = colorlab.xyz_to_lab(colorlab.lab_to_xyz(lab))
    assert all(abs(x - y) < 1e-9 for x, y in zip(lab, back))


def test_profile_white_and_surface():
    f = cmyk_profile()
    w = colorlab.profile_white(f)
    assert w and 93 < w[0] < 97 and abs(w[1]) < 2 and -4 < w[2] < 1, w           # FOGRA39: L95 a0 b-2
    assert colorlab.guess_surface("PSO Uncoated v3 (FOGRA52)") == "uncoated"
    assert colorlab.guess_surface("ISOcoated_v2_eci") == "coated"
    assert colorlab.guess_surface("Epson Premium Glossy Photo Paper") == "glossy"
    assert colorlab.guess_surface("Coated FOGRA39") == "coated" and colorlab.guess_surface("xyz") == ""


def test_read_measurements():
    p = os.path.join(TMP, "messung.txt")
    open(p, "w").write(CGATS)
    lab, why, n = colorlab.read_measurement_file(p)
    assert n == 4 and lab == (93.2, 0.8, 4.0) and "2" in why, (lab, why)          # beide Papierfelder gemittelt
    xyz = CGATS.replace("LAB_L LAB_A LAB_B", "XYZ_X XYZ_Y XYZ_Z").replace("93.10 0.90 4.10", "80.0 83.0 65.0")
    pts = colorlab.parse_cgats(xyz)
    assert len(pts) == 4 and abs(pts[0]["lab"][0] - colorlab.xyz_to_lab((80, 83, 65))[0]) < 0.01
    log = os.path.join(TMP, "spotread.log")
    open(log, "w").write(" Result is XYZ: 1 2 3, D50 Lab: 93.0 1.0 4.0\n Result is XYZ: 1 2 3, D50 Lab: 94.0 0.0 3.0\n")
    lab, why, n = colorlab.read_measurement_file(log)
    assert lab == (93.5, 0.5, 3.5) and n == 2
    assert colorlab.parse_lab_text("L=93,5 a=0,8 b=-4,2") == (93.5, 0.8, -4.2)
    assert colorlab.parse_lab_text("130 0 0") is None and colorlab.parse_lab_text("93 1") is None


def test_spotread_states():
    s = colorlab.spotread_state
    assert s("Place the instrument on its reflective white reference,\n and then hit any key to continue,\n"
             " or hit Esc or Q to abort:") == "calibrate"
    assert s("Calibration complete\nPlace instrument on spot to be read,\n'k' to do a calibration\n"
             "Hit ESC or 'q' to give up, any other key to take a reading:") == "measure"
    assert s(" Result is XYZ: 89.2 92.4 76.0, D50 Lab: 96.9 -0.18 -1.84\n") == "result"
    assert s("No instruments found\n") == "error" and s("Setting up the instrument\n") == "busy"
    assert colorlab.spotread_args(2, True) == ["-O", "-c", "2", "-N"]


def _cfg():
    f = cmyk_profile()
    return {"color_profiles": [
        {"id": "fogra39", "name": "Coated FOGRA39", "file": f, "printers": [], "intents": ["relative"]},
        {"id": "epson_matt", "name": "Epson Matte", "file": f, "printers": ["epson"], "intents": ["relative"]},
        {"id": "canon_only", "name": "Canon gestrichen", "file": f, "printers": ["canon"], "intents": ["relative"]}],
        "materials": [{"id": "natur", "name": "Natur 120", "weight": 120, "surface": "uncoated",
                       "white": [92.0, 0.5, 7.0], "profiles": {"*": "fogra39", "epson": "epson_matt"}}]}


def test_suggestions():
    cfg = _cfg()
    cands = colorlab.candidates(cfg, extra_cmyk=False)
    assert {c["id"] for c in cands} == {"fogra39", "epson_matt", "canon_only"}
    coated = {"id": "x", "white": list(colorlab.profile_white(cmyk_profile())), "surface": "coated"}
    res = colorlab.suggest(coated, cands, "epson")
    assert [r["id"] for r in res][0] == "epson_matt" and "canon_only" not in [r["id"] for r in res]
    assert res[0]["de"] < 1 and res[0]["verdict"] == colorlab.verdict(0.5)
    natur = cfg["materials"][0]
    res = colorlab.suggest(natur, cands, "")
    assert res[0]["de"] > 4 and "andere Oberfläche" in res[0]["why"]
    assert "FOGRA52" in colorlab.standard_tip(natur, res[0])
    assert colorlab.standard_tip(coated, colorlab.suggest(coated, cands)[0]) == ""
    assert colorlab.profile_for(cfg, natur, "epson") == "epson_matt" and colorlab.profile_for(cfg, natur, "x") == "fogra39"
    assert colorlab.cmyk_profile_of(cfg, natur) == cmyk_profile()
    ch = colorlab.proof_choices(cfg)
    keys = [c["key"] for c in ch]
    assert keys[:2] == ["m:natur:*", "m:natur:epson"] and ch[0]["white"] == [92.0, 0.5, 7.0], keys
    assert "p:fogra39" in keys


def test_conversion_recommendation():
    f = cmyk_profile()
    cands = colorlab.candidates(_cfg(), extra_cmyk=False)
    r = colorlab.recommend_conversion([], False, f, cands)
    assert r["mode"] == "rgb_only" and "Keine CMYK" in r["text"]
    r = colorlab.recommend_conversion(["FOGRA39L Coated"], True, f, cands)
    assert r["mode"] == "rgb_only" and "schon" in r["text"], r                 # gleiche Bedingung: CMYK bleibt
    r = colorlab.recommend_conversion(["Coated FOGRA39 (ISO 12647-2:2004)"], True, "/x/PSOuncoated_v3_FOGRA52.icc", cands)
    assert r["mode"] == "all" and r["source"] == f, r                         # Quellprofil installiert -> gefunden
    r = colorlab.recommend_conversion(["FOGRA27"], True, f, cands)
    assert r["mode"] == "all" and r["source"] == "" and "nicht installiert" in r["text"]


def test_doc_color_facts():
    import pikepdf
    p = os.path.join(TMP, "oi.pdf")
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(100, 100))
    pdf.pages[0].obj.Contents = pikepdf.Stream(pdf, b"1 0 0 rg 0 0 10 10 re f")
    pdf.save(p)
    assert colorlab.doc_color_facts(p) == ([], False)
    pdf = pikepdf.open(p, allow_overwriting_input=True)
    pdf.pages[0].obj.Contents = pikepdf.Stream(pdf, b"0 0 0 1 k 0 0 10 10 re f")
    pdf.Root.OutputIntents = pikepdf.Array([pikepdf.Dictionary(Type=pikepdf.Name.OutputIntent, S=pikepdf.Name.GTS_PDFX,
                                                               OutputConditionIdentifier=pikepdf.String("FOGRA51"))])
    pdf.save(p)
    assert colorlab.doc_color_facts(open(p, "rb").read()) == (["FOGRA51"], True)


def test_admin_validation():
    icc_dir = "/etc/passermark/icc"
    cfg = {"color_profiles": [{"id": "a", "file": os.path.join(icc_dir, "a.icc"), "name": "A"}],
           "materials": [{"id": "m1", "name": "Natur", "weight": 120, "surface": "uncoated", "white": [92, 0.5, 7],
                          "white_source": "gemessen", "profiles": {"*": "a", "epson": "a"}, "intent": "relative",
                          "notes": "Fach 2\nLieferant X"}]}
    cfgvalidate.validate(cfg, icc_dir)
    for bad in ({"white": [101, 0, 0]}, {"white": [90, 0]}, {"profiles": {"*": "zz"}}, {"surface": "x"},
                {"foo": 1}, {"weight": True}, {"intent": "x"}, {"profiles": {"bad name!": "a"}}, {"id": "a b"}):
        d = copy.deepcopy(cfg)
        d["materials"][0].update(bad)
        try:
            cfgvalidate.validate(d, icc_dir)
            assert False, bad
        except ValueError:
            pass
    d = copy.deepcopy(cfg)
    d["materials"].append(copy.deepcopy(d["materials"][0]))
    try:
        cfgvalidate.validate(d, icc_dir)
        assert False
    except ValueError as e:
        assert "doppelt" in str(e)


if __name__ == "__main__":
    for k, fn in list(globals().items()):
        if k.startswith("test_"):
            fn()
            print("ok", k)
