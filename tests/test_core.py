# SPDX-License-Identifier: GPL-3.0-or-later
"""Kern-Schnittstelle: Aufträge Datei -> Datei, Einstellungen als JSON, Fortschritt, Abbrechen, atomares Schreiben."""
import json, os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("PASSERMARK_LANG", "de")
import pikepdf
import pypdfium2 as pdfium
from pdfdruck import core, cutcontour, objects, preflight
import test_cutcontour as tc

TMP = tempfile.mkdtemp(prefix="pm-core-")


def stickers_file():
    p = os.path.join(TMP, "stickers.pdf")
    if not os.path.exists(p):
        tc.stickers().save(p)
    return p


def test_settings_json_roundtrip():
    s = cutcontour.CutSettings(shape="heart", bleed_mm=3, single_shape=False,
                               detect=objects.DetectSettings(tolerance=40, gap_mm=2.5))
    d = json.loads(json.dumps(core.settings_to_dict(s)))
    s2 = core.settings_from_dict(cutcontour.CutSettings, d)
    assert s2 == s and isinstance(s2.detect, objects.DetectSettings) and s2.detect.tolerance == 40
    # unbekannte Schlüssel werden ignoriert, fehlende bekommen den Standard, int -> float
    s3 = core.settings_from_dict(cutcontour.CutSettings, {"shape": "rect", "bleed_mm": 2, "gibts_nicht": 1})
    assert s3.shape == "rect" and s3.bleed_mm == 2.0 and isinstance(s3.bleed_mm, float) and s3.offset_mm == 0.0
    p = os.path.join(TMP, "preset.json")
    core.save_settings(p, "cutcontour", s)
    kind, d = core.load_settings(p)
    assert kind == "cutcontour" and core.settings_from_dict(cutcontour.CutSettings, d) == s
    for kind in core.JOBS:                           # jede Auftragsart: Standard-Einstellungen sind JSON-fähig
        cls = core.settings_class(kind)
        assert core.settings_from_dict(cls, json.loads(json.dumps(core.settings_to_dict(cls())))) == cls()


def test_cutcontour_job_with_progress():
    src, dst = stickers_file(), os.path.join(TMP, "cut.pdf")
    seen = []
    r = core.run_job("cutcontour", src, dst, {"shape": "contour", "bleed_mm": 2},
                     progress=lambda d, t, txt: seen.append((d, t)))
    assert os.path.exists(dst) and r.info["cuts"] >= 3 and r.info["pages"] == 1
    assert seen[0] == (0, 1) and seen[-1] == (1, 1)
    pk = pikepdf.open(dst)
    assert "/CutContour" in str(pk.pages[0].Resources.get("/ColorSpace", {}))
    pk.close()


def test_cancel_leaves_no_file():
    src, dst = stickers_file(), os.path.join(TMP, "abbruch.pdf")
    try:
        core.run_job("cutcontour", src, dst, {}, cancel=lambda: True)
        assert False, "kein Abbruch"
    except core.Cancelled:
        pass
    assert not os.path.exists(dst) and not os.path.exists(dst + ".part")
    calls = []
    def cancel_later():                               # Abbruch erst während der Arbeit
        calls.append(1)
        return len(calls) > 2
    try:
        core.run_job("cutcontour", src, dst, {}, cancel=cancel_later)
    except core.Cancelled:
        pass
    assert not os.path.exists(dst) and not os.path.exists(dst + ".part")


def test_error_leaves_no_file():
    src, dst = stickers_file(), os.path.join(TMP, "fehler.pdf")
    try:
        core.run_job("separate", src, dst, {"detect": {"min_size_mm": 5000}})     # findet nichts
        assert False
    except ValueError:
        pass
    assert not os.path.exists(dst) and not os.path.exists(dst + ".part")
    try:
        core.run_job("cutcontour", src, src, {})
        assert False
    except ValueError:
        pass
    try:
        core.run_job("gibts_nicht", src, dst, {})
        assert False
    except ValueError:
        pass


def test_separate_job():
    src, dst = stickers_file(), os.path.join(TMP, "getrennt.pdf")
    r = core.run_job("separate", src, dst, {"margin_mm": 2})
    assert r.info["objects"] >= 3 and len(pdfium.PdfDocument(dst)) == r.info["objects"]
    r = core.run_job("separate", src, dst, {"boxes": {"0": [[0, 0, 100, 100], [200, 200, 300, 400]]}})
    d = pdfium.PdfDocument(dst)
    assert len(d) == 2 and [round(v) for v in d.get_page_size(1)] == [100, 200]


def test_manip_crop_job():
    import test_preflight as tp
    src = os.path.join(TMP, "a4.pdf")
    open(src, "wb").write(tp.problem_pdf())
    dst = os.path.join(TMP, "crop.pdf")
    r = core.run_job("manip", src, dst, {"crop": True, "crop_size": "A5"})
    w, h = pdfium.PdfDocument(dst).get_page_size(0)
    assert abs(w - 419.5) < 1.5 and abs(h - 595.3) < 1.5, (w, h)
    try:
        core.run_job("manip", src, dst, {})          # nichts aktiviert
        assert False
    except ValueError:
        pass


def test_preflight_fix_job():
    import test_preflight as tp
    src = os.path.join(TMP, "ebenen.pdf")
    open(src, "wb").write(tp.problem_pdf())
    dst = os.path.join(TMP, "festgeschrieben.pdf")
    core.run_job("preflight_fix", src, dst, {"fix": "flatten_layers"})
    pk = pikepdf.open(dst)
    assert "/OCProperties" not in pk.Root
    pk.close()


def test_repair_job():
    from pdfdruck import platform as pl
    if not pl.ghostscript():
        print("   (übersprungen: kein Ghostscript – läuft im GitHub-Build)")
        return
    src, dst = stickers_file(), os.path.join(TMP, "repariert.pdf")
    r = core.run_job("repair", src, dst, {"mode": "print"})
    assert os.path.exists(dst) and r.info["pages"] == 1


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("ok", k)
