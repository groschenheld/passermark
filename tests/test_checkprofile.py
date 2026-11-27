# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Check profiles: built-in profiles, own profile files, severities and limits applied to the document check."""

import io
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
os.environ.setdefault("PASSERMARK_LANG", "de")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()  # no chosen profile of the developer
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]
import pikepdf

from pdfdruck import checkprofile, preflight


def _pdf(content: bytes, pages: int = 1, resources=None, size=(595, 842)) -> bytes:
    pdf = pikepdf.new()
    font = pdf.make_indirect(
        pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica)
    )
    for _ in range(pages):
        pdf.add_blank_page(page_size=size)
        pg = pdf.pages[-1]
        res = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font))
        for k, v in (resources or {}).items():
            res["/" + k] = v
        pg.obj.Resources = res
        pg.obj.Contents = pdf.make_stream(content)
    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()


def _image_pdf(px: int, inch: float = 1.0) -> bytes:
    """One RGB image of px × px pixels placed at inch × inch (-> px / inch dpi)."""
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(595, 842))
    img = pdf.make_stream(
        bytes([200, 100, 50]) * (px * px),
        Type=pikepdf.Name.XObject,
        Subtype=pikepdf.Name.Image,
        Width=px,
        Height=px,
        ColorSpace=pikepdf.Name.DeviceRGB,
        BitsPerComponent=8,
    )
    pg = pdf.pages[0]
    pg.obj.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im1=img))
    s = 72 * inch
    pg.obj.Contents = pdf.make_stream(f"q {s:g} 0 0 {s:g} 200 400 cm /Im1 Do Q".encode())
    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()


def _checks(rep) -> dict:
    return {i.check: i.severity for i in rep.issues}


def test_builtin_profiles_valid():
    assert checkprofile.DEFAULT in checkprofile.BUILTIN
    for p in checkprofile.BUILTIN.values():
        d = p.to_dict()
        q = checkprofile.from_dict(json.loads(json.dumps(d)), p.name)  # round trip through a file
        assert q.report == p.report and q.limits == p.limits, p.name
        assert all(v in checkprofile.SEVERITIES for v in p.report.values())
        assert set(p.report) <= set(checkprofile.CHECKS) and set(p.limits) <= set(checkprofile.LIMITS)
    std = checkprofile.BUILTIN["standard"]
    assert not std.report and not std.limits  # "standard" = the check as before
    assert std.severity("text_small") == "off"  # no limit -> off
    assert std.severity("pdfx_none") == "off"  # off by default
    assert checkprofile.BUILTIN["offset"].severity("text_small") == "warning"


def test_invalid_profiles_rejected():
    for bad, word in (
        ({"report": {"gibtsnicht": "error"}}, "unbekannte Prüfung"),
        ({"report": {"rgb": "rot"}}, "muss eines von"),
        ({"limits": {"safety_mm": "3"}}, "Zahl"),
        ({"limits": {"safety_mm": 500}}, "zwischen"),
        ({"limits": {"gibtsnicht": 1}}, "unbekannter Grenzwert"),
        ({"passermark": "workflow"}, "keine Prüfprofil-Datei"),
    ):
        try:
            checkprofile.from_dict(bad, "x")
        except ValueError as e:
            assert word in str(e), (bad, e)
        else:
            raise AssertionError(bad)


def test_own_profile_saved_found_and_chosen():
    p = checkprofile.from_dict({"name": "Druckerei Muster", "report": {"rgb": "error"}, "limits": {"safety_mm": 5}})
    p.name = "muster"
    path = checkprofile.save(p)
    assert os.path.isfile(path) and path.startswith(os.environ["XDG_CONFIG_HOME"])
    assert [x.name for x in checkprofile.own_profiles()] == ["muster"]
    q = checkprofile.resolve("MUSTER")  # names are not case-sensitive
    assert q.severity("rgb") == "error" and q.limit("safety_mm") == 5.0
    assert checkprofile.resolve(path).limit("safety_mm") == 5.0  # also as a file
    try:
        checkprofile.save(checkprofile.BUILTIN["offset"])
    except ValueError:
        pass
    else:
        raise AssertionError("built-in profile overwritten")
    from pdfdruck import l10n

    s = l10n.load_settings()
    s[checkprofile.SETTING] = "muster"
    l10n.save_settings(s)
    assert checkprofile.chosen() == "muster" and checkprofile.resolve(None).name == "muster"
    # the choice of the program does not reach library, command line and workflows: there "standard" applies
    assert preflight.analyze(_pdf(b""), deep_layers=False).profile.name == "standard"
    from pdfdruck import docinfo

    assert docinfo._check(_pdf(b""))["profile"] == "standard"
    s[checkprofile.SETTING] = "standard"
    l10n.save_settings(s)
    os.remove(path)


def test_profile_changes_severities():
    from test_preflight import problem_pdf

    data = problem_pdf()
    std = preflight.analyze(data, deep_layers=False, profile="standard")
    off = preflight.analyze(data, deep_layers=False, profile="offset")
    scr = preflight.analyze(data, deep_layers=False, profile="screen")
    a, b, c = _checks(std), _checks(off), _checks(scr)
    assert a["font_std14"] == "info" and b["font_std14"] == "error"
    assert a["rgb"] == "info" and b["rgb"] == "warning" and "rgb" not in c
    assert "pdfx_none" not in a and b["pdfx_none"] == "warning"
    assert a["font_missing"] == "error" and c["font_missing"] == "warning"
    assert std.profile.name == "standard" and off.profile.name == "offset"
    assert "overprint_white" in std.passed and "font_missing" not in std.passed
    assert "pdfx_none" not in std.passed  # off checks are not "passed"
    assert [SEV for SEV in (i.severity for i in off.issues)] == sorted(
        (i.severity for i in off.issues), key=preflight.SEV_ORDER.get
    )  # sorted again after the change


def test_small_text_only_with_limit():
    data = _pdf(b"BT /F1 4 Tf 100 700 Td (klein) Tj ET BT /F1 10 Tf 100 600 Td (normal) Tj ET")
    assert "text_small" not in _checks(preflight.analyze(data, deep_layers=False, profile="standard"))
    rep = preflight.analyze(data, deep_layers=False, profile={"limits": {"text_min_pt": 6}})
    i = next(i for i in rep.issues if i.check == "text_small")
    assert i.pages == [1] and "4,0 pt" in i.message.replace("4.0", "4,0") and len(i.spots) == 1
    # scaled with the text matrix: 10 pt font at 50 % -> 5 pt
    data = _pdf(b"BT /F1 10 Tf 0.5 0 0 0.5 100 700 Tm (halb) Tj ET")
    assert "text_small" in _checks(preflight.analyze(data, deep_layers=False, profile={"limits": {"text_min_pt": 6}}))


def test_page_multiple_and_spot_count():
    data = _pdf(b"", pages=3)
    rep = preflight.analyze(data, deep_layers=False, profile={"limits": {"page_multiple": 4}})
    i = next(i for i in rep.issues if i.check == "page_multiple")
    assert "3 Seiten" in i.message and "1 Seite" in i.message
    assert "page_multiple" not in _checks(preflight.analyze(_pdf(b"", pages=4), False, profile=rep.profile))
    sep = pikepdf.Array(
        [
            pikepdf.Name.Separation,
            pikepdf.Name("/HKS 43 K"),
            pikepdf.Name.DeviceCMYK,
            pikepdf.Dictionary(FunctionType=2, Domain=[0, 1], C0=[0, 0, 0, 0], C1=[1, 0.5, 0, 0], N=1),
        ]
    )
    data = _pdf(b"/CS1 cs 1 scn 100 100 200 200 re f", resources={"ColorSpace": pikepdf.Dictionary(CS1=sep)})
    assert "spot_count" not in _checks(preflight.analyze(data, deep_layers=False, profile="standard"))
    rep = preflight.analyze(data, deep_layers=False, profile={"limits": {"spot_max": 0}})
    assert _checks(rep).get("spot_count") == "warning", _checks(rep)
    assert "spot_count" not in _checks(preflight.analyze(data, False, profile={"limits": {"spot_max": 1}}))


def test_image_limits_from_profile():
    low = _image_pdf(100)  # 100 dpi
    assert _checks(preflight.analyze(low, deep_layers=False, profile="standard")).get("image_low") == "warning"
    plot = _checks(preflight.analyze(low, deep_layers=False, profile="plot"))  # from 100 dpi: fine
    assert "image_low" not in plot and "image_ok" not in plot
    big = _image_pdf(400)  # 400 dpi
    assert "image_high" not in _checks(preflight.analyze(big, deep_layers=False, profile="standard"))
    assert _checks(preflight.analyze(big, deep_layers=False, profile="screen")).get("image_high") == "warning"


def test_limits_reach_the_measuring_checks():
    """Safety distance and bleed are measured with the limits of the profile (pdfium part)."""
    data = _pdf(b"BT /F1 12 Tf 30 400 Td (Rand) Tj ET")  # 30 pt ~ 10.6 mm from the left edge
    near = {"limits": {"safety_mm": 15}}
    assert "safety" not in _checks(preflight.analyze(data, profile="standard"))
    assert "safety" in _checks(preflight.analyze(data, profile=near))
    assert "safety" not in _checks(preflight.analyze(data, profile={"limits": {"safety_mm": 0}}))


def test_gwg_profile():
    from types import SimpleNamespace

    g = checkprofile.BUILTIN["gwg"]
    assert g.limit("tac_max") == 320 and g.limit("pdfx_min") == 4 and g.severity("rgb") == "error"
    rep = preflight.Report(profile=g)
    assert preflight._ppi(rep, SimpleNamespace(bits=1)) == (799.0, 549.0)
    assert preflight._ppi(rep, SimpleNamespace(bits=8)) == (224.0, 149.0)
    std = preflight.Report(profile=checkprofile.BUILTIN["standard"])
    assert preflight._ppi(std, SimpleNamespace(bits=1)) == (600.0, 300.0)  # automatic: twice
    assert preflight._pdfx_number("PDF/X-1a:2001") == 1 and preflight._pdfx_number("PDF/X-4p") == 4
    # PDF/X-1a with Courier: too old for GWG and Courier is reported – not with "standard"
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(595, 842))
    font = pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Courier)
    pdf.pages[0].obj.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font))
    pdf.pages[0].obj.Contents = pdf.make_stream(b"BT /F1 10 Tf 72 700 Td (Hallo) Tj ET")
    with pdf.open_metadata(set_pikepdf_as_editor=False) as md:
        md["pdfxid:GTS_PDFXVersion"] = "PDF/X-1a:2001"
    buf = io.BytesIO()
    pdf.save(buf)
    keys = {i.check: i for i in preflight.analyze(buf.getvalue(), profile="gwg").issues}
    assert keys["pdfx_version"].severity == "error" and "PDF/X-4" in keys["pdfx_version"].message
    assert keys["font_courier"].severity == "warning"
    std_keys = {i.check for i in preflight.analyze(buf.getvalue(), profile="standard").issues}
    assert "pdfx_version" not in std_keys and "font_courier" not in std_keys


def test_workflow_option_and_cli():
    from pdfdruck import workflow

    st = tempfile.mkdtemp()
    src = os.path.join(st, "a.pdf")
    with open(src, "wb") as f:
        f.write(_pdf(b""))
    wf = {
        "passermark": "workflow",
        "version": 1,
        "options": {"check_profile": "gibtsnicht"},
        "steps": [{"job": "shrink"}],
    }
    try:
        workflow.prepare(wf, st, inputs=[src], output=os.path.join(st, "b.pdf"))
    except workflow.WorkflowError as e:
        assert "gibtsnicht" in str(e.problems)
    else:
        raise AssertionError("unknown profile accepted")
    wf["options"]["check_profile"] = "offset"
    plan = workflow.prepare(wf, st, inputs=[src], output=os.path.join(st, "b.pdf"))
    assert plan.check_profile == "offset"
    env = dict(os.environ, PYTHONPATH=ROOT)
    r = subprocess.run(
        [sys.executable, "-m", "pdfdruck.cli", "checkprofiles", "--show", "offset", "--json"],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    d = json.loads(r.stdout)
    assert d["name"] == "offset" and d["checks"]["font_std14"] == "error" and d["limits"]["bleed_min_mm"] == 3.0
    r = subprocess.run(
        [sys.executable, "-m", "pdfdruck.cli", "inspect", src, "--check", "--profile", "screen", "--json"],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    d = json.loads(r.stdout)
    assert d["check"]["profile"] == "screen" and isinstance(d["check"]["passed"], list)
    assert all("check" in i for i in d["check"]["issues"])


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
