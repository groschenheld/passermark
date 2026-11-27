# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Alles reparieren (autofix.py, job autofix): plan from the findings, steps, PDF/X-4 marking."""

import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
os.environ.setdefault("PASSERMARK_LANG", "de")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
import pikepdf

from pdfdruck import autofix, cmyk, core, preflight
from test_softproof import cmyk_profile


def _pdf(content: bytes, version: str = "", icc: str = "", spot: bool = False, fonts: bool = True) -> bytes:
    """A4 with 3 mm bleed boxes; optional PDF/X marker with output intent and a spot colour."""
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(612, 858))
    pg = pdf.pages[0].obj
    pg.TrimBox = pikepdf.Array([8.5, 8.5, 603.5, 849.5])
    pg.BleedBox = pikepdf.Array([0, 0, 612, 858])
    res = pikepdf.Dictionary()
    if spot:
        fn = pikepdf.Dictionary(FunctionType=2, Domain=[0, 1], C0=[0, 0, 0, 0], C1=[0, 0.9, 0.8, 0], N=1)
        res.ColorSpace = pikepdf.Dictionary(
            CS0=pikepdf.Array([pikepdf.Name.Separation, pikepdf.Name("/PANTONE 185 C"), pikepdf.Name.DeviceCMYK, fn])
        )
    res.ExtGState = pikepdf.Dictionary(GS0=pikepdf.Dictionary(Type=pikepdf.Name.ExtGState, op=True, OP=True, OPM=1))
    pg.Resources = res
    pg.Contents = pdf.make_stream(content)
    if version:
        with open(icc, "rb") as fh:
            cmyk._set_output_intent(pdf, fh.read(), "Test CMYK")
        with pdf.open_metadata(set_pikepdf_as_editor=False) as md:
            md["pdfxid:GTS_PDFXVersion"] = version
    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()


CMYK_BOX = b"0 0 0 1 k 100 100 200 100 re f"
SPOT_BOX = b"/CS0 cs 1 scn 100 300 100 50 re f"
WHITE_OP = b"/GS0 gs 0 0 0 0 k 100 500 100 50 re f"


def test_plan_follows_the_profile():
    data = _pdf(CMYK_BOX + b"\n" + SPOT_BOX + b"\n" + WHITE_OP, "PDF/X-1a:2001", cmyk_profile(), spot=True)
    gwg = preflight.analyze(data, profile="gwg")
    keys = [st.key for st in autofix.plan(gwg)]
    assert keys == ["spots", "overprint", "pdfx"], keys  # fixed order
    assert not any(st.blocked for st in autofix.plan(gwg))  # output intent in the file
    std = preflight.analyze(data, profile="standard")
    assert "pdfx" not in [st.key for st in autofix.plan(std)] and "spots" not in [st.key for st in autofix.plan(std)]
    no_oi = preflight.analyze(_pdf(CMYK_BOX), profile="gwg")
    (px,) = [st for st in autofix.plan(no_oi) if st.key == "pdfx"]
    assert px.blocked
    assert not [st for st in autofix.plan(no_oi, has_target=True) if st.blocked]


def test_run_repairs_and_marks_pdfx4():
    data = _pdf(CMYK_BOX + b"\n" + SPOT_BOX + b"\n" + WHITE_OP, "PDF/X-1a:2001", cmyk_profile(), spot=True)
    out, notes, after = autofix.run(data, autofix.AutofixSettings(profile="gwg"))
    assert all(n.startswith("✓") for n in notes[:3]), notes
    checks = {i.check for i in after.issues if i.severity in ("error", "warning")}
    assert not checks & {"spot_count", "overprint_white", "pdfx_version", "pdfx_none"}, checks
    with pikepdf.open(io.BytesIO(out)) as pdf:
        assert pdf.pdf_version >= "1.6" and len(pdf.Root.OutputIntents) == 1
        assert str(pdf.Root.OutputIntents[0].OutputConditionIdentifier) == "Test CMYK"  # kept
        with pdf.open_metadata() as md:
            assert md["pdfxid:GTS_PDFXVersion"] == "PDF/X-4" and md["xmpMM:VersionID"] == "1"
    # only chosen steps
    out2, notes2, after2 = autofix.run(data, autofix.AutofixSettings(profile="gwg", steps=["pdfx"]))
    assert len([n for n in notes2 if n.startswith("✓")]) == 1
    assert "spot_count" in {i.check for i in after2.issues}


def test_make_pdfx4():
    data = _pdf(CMYK_BOX)
    try:
        autofix.make_pdfx4(data)
        raise AssertionError("PDF/X ohne Output-Intent")
    except ValueError:
        pass
    out = autofix.make_pdfx4(data, cmyk_profile(), "Titel")
    with pikepdf.open(io.BytesIO(out)) as pdf:
        assert pdf.Root.OutputIntents[0].S == pikepdf.Name.GTS_PDFX
        assert "/TrimBox" in pdf.pages[0].obj and str(pdf.docinfo.Title) == "Titel"
    rep = preflight.analyze(out, profile="gwg")
    assert not {"pdfx_none", "pdfx_version", "pdfx_intent"} & {i.check for i in rep.issues}


def test_missing_trim_box_is_set():
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(200, 200))
    buf = io.BytesIO()
    pdf.save(buf)
    out = autofix.make_pdfx4(buf.getvalue(), cmyk_profile())
    with pikepdf.open(io.BytesIO(out)) as p:
        assert [float(v) for v in p.pages[0].obj.TrimBox] == [0, 0, 200, 200]


def test_job_and_failed_steps():
    """Job autofix in core (also CLI/workflows); a step without Ghostscript fails, the others run."""
    data = _pdf(b"BT /F1 12 Tf 72 700 Td (x) Tj ET\n" + WHITE_OP, "PDF/X-4", cmyk_profile())
    with pikepdf.open(io.BytesIO(data)) as pdf:  # Helvetica, not embedded -> fonts step
        pdf.pages[0].obj.Resources.Font = pikepdf.Dictionary(
            F1=pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica)
        )
        buf = io.BytesIO()
        pdf.save(buf)
    tmp = tempfile.mkdtemp()
    src, dst = os.path.join(tmp, "in.pdf"), os.path.join(tmp, "out.pdf")
    with open(src, "wb") as fh:
        fh.write(buf.getvalue())
    res = core.run_job("autofix", src, dst, {"profile": "gwg"})
    assert os.path.isfile(dst) and res.info["profile"] == "gwg"
    fonts = [n for n in res.notes if "Schriften einbetten" in n]
    assert fonts and (fonts[0].startswith("✓") or (fonts[0].startswith("✗") and not cmyk.ghostscript()))
    assert any(n.startswith("✓ Überdrucken") for n in res.notes), res.notes


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
