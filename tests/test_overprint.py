# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Overprint: white overprints, small black text knocks out – find, correct, report (overprint.py, preflight.py)."""

import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "_qtstub"))
sys.path.insert(0, os.path.join(HERE, ".."))

import pikepdf  # noqa: E402

from pdfdruck import l10n, overprint, preflight  # noqa: E402

l10n.set_language("de")


def _pdf(content: bytes, form: bytes | None = None, pages: int = 1) -> bytes:
    pdf = pikepdf.new()
    egs = pikepdf.Dictionary(
        OPon=pikepdf.Dictionary(Type=pikepdf.Name.ExtGState, OP=True, op=True, OPM=1),
        OPonly=pikepdf.Dictionary(OP=True),  # /op missing -> takes the value of /OP
        OPm0=pikepdf.Dictionary(OP=True, op=True, OPM=0),
    )
    font = pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica)
    res = pikepdf.Dictionary(ExtGState=egs, Font=pikepdf.Dictionary(F1=font))
    if form is not None:
        f = pdf.make_stream(form)
        f.Type = pikepdf.Name.XObject
        f.Subtype = pikepdf.Name.Form
        f.BBox = [0, 0, 100, 100]
        res.XObject = pikepdf.Dictionary(Fm=f)
    res = pdf.make_indirect(res)
    for _ in range(pages):
        page = pikepdf.Dictionary(
            Type=pikepdf.Name.Page, MediaBox=[0, 0, 200, 200], Resources=res, Contents=pdf.make_stream(content)
        )
        pdf.pages.append(pikepdf.Page(page))
    b = io.BytesIO()
    pdf.save(b)
    return b.getvalue()


WHITE_PATH = b"q /OPon gs 0 0 0 0 k 10 10 50 50 re f Q"
BLACK_SMALL = b"BT /F1 9 Tf 0 0 0 1 k 20 100 Td (Hallo) Tj ET"
BLACK_BIG = b"BT /F1 30 Tf 0 0 0 1 k 20 150 Td (Gross) Tj ET"


def test_colors():
    cmyk, gray, rgb = {"space": "CMYK"}, {"space": "Gray"}, {"space": "RGB"}
    assert overprint.is_white((cmyk, [0, 0, 0, 0]))
    assert overprint.is_white((gray, [1.0]))
    assert overprint.is_white((rgb, [1, 1, 1]))
    assert not overprint.is_white((cmyk, [0, 0, 0, 0.1]))
    assert not overprint.is_white(({"space": "Separation"}, [0.0]))
    assert overprint.is_pure_black((cmyk, [0, 0, 0, 1]))
    assert overprint.is_pure_black((cmyk, [0, 0, 0, 0.96]))
    assert not overprint.is_pure_black((cmyk, [0.4, 0.3, 0.3, 1]))  # rich black: not affected
    assert not overprint.is_pure_black((gray, [0.0]))


def test_scan():
    r = overprint.scan_bytes(_pdf(WHITE_PATH + b" " + BLACK_SMALL + b" " + BLACK_BIG))
    assert r["counts"] == {"white": 1, "black_text": 1}  # 30 pt text is not reported
    assert r["white"][1] == [(10.0, 10.0, 60.0, 60.0)]
    x0, y0, x1, y1 = r["black_text"][1][0]
    assert 19 < x0 < 21 and y0 < 100 < y1
    # nothing set to overprint, no black text
    assert overprint.scan_bytes(_pdf(b"0 0 0 0 k 10 10 50 50 re f"))["counts"] == {"white": 0, "black_text": 0}
    # black text that already overprints (op + OPM 1): fine; with OPM 0 it still knocks out
    ok = overprint.scan_bytes(_pdf(b"/OPon gs " + BLACK_SMALL))
    assert ok["counts"]["black_text"] == 0
    m0 = overprint.scan_bytes(_pdf(b"/OPm0 gs " + BLACK_SMALL))
    assert m0["counts"]["black_text"] == 1
    # q/Q restores the state: white after Q no longer overprints
    r = overprint.scan_bytes(_pdf(b"q /OPon gs Q 0 0 0 0 k 0 0 5 5 re f"))
    assert r["counts"]["white"] == 0
    # stroke only: white stroke with /OP (op follows /OP)
    r = overprint.scan_bytes(_pdf(b"/OPonly gs 1 G 0 0 m 50 50 l S"))
    assert r["counts"]["white"] == 1
    # white text set to overprint
    r = overprint.scan_bytes(_pdf(b"/OPon gs BT /F1 20 Tf 1 g 10 10 Td (Weiss) Tj ET"))
    assert r["counts"] == {"white": 1, "black_text": 0}
    # text scaled by cm: 20 pt × 0.5 = 10 pt -> reported
    r = overprint.scan_bytes(_pdf(b"0.5 0 0 0.5 0 0 cm BT /F1 20 Tf 0 0 0 1 k 10 10 Td (x) Tj ET"))
    assert r["counts"]["black_text"] == 1


def test_scan_form():
    d = _pdf(b"q 1 0 0 1 50 50 cm /Fm Do Q", form=b"/OPonly gs 1 g 0 0 10 10 re f")
    r = overprint.scan_bytes(d)
    assert r["white"] == {1: [(50.0, 50.0, 60.0, 60.0)]}


def test_fix():
    d = _pdf(WHITE_PATH + b" " + BLACK_SMALL + b" " + BLACK_BIG + b" 0.2 0.2 0.2 0.2 k 0 0 5 5 re f")
    out, notes = overprint.fix(d)
    assert any("1 weißen" in n for n in notes) and any("1 schwarze" in n for n in notes)
    r = overprint.scan_bytes(out)
    assert r["counts"] == {"white": 0, "black_text": 0}
    with pikepdf.open(io.BytesIO(out)) as p:
        page = p.pages[0]
        egs = page.obj.Resources.ExtGState
        assert bool(egs["/PMop101"].op) is False and int(egs["/PMop011"].OPM) == 1
        ops = [str(i.operator) for i in pikepdf.parse_content_stream(page)]
        # gs directly before the path construction, never between "re" and "f"
        i = ops.index("re")
        assert ops[i - 1] == "gs" and ops[i + 1] == "f" and ops[i + 2] == "gs"
        assert ops.count("BT") == 2 and ops.count("ET") == 2
    # second run: nothing left, bytes unchanged
    again, notes = overprint.fix(out)
    assert again == out and "nichts" in notes[0]
    # only white
    out, _ = overprint.fix(d, white=True, black_text=False)
    r = overprint.scan_bytes(out)
    assert r["counts"] == {"white": 0, "black_text": 1}


def test_fix_form_shared():
    """A form used on two pages is corrected once; the stream of the form is rewritten."""
    d = _pdf(b"/Fm Do", form=b"/OPonly gs 1 g 0 0 10 10 re f", pages=2)
    out, notes = overprint.fix(d)
    assert overprint.scan_bytes(out)["counts"]["white"] == 0
    with pikepdf.open(io.BytesIO(out)) as p:
        fm = p.pages[0].obj.Resources.XObject.Fm
        assert b"/PMop100 gs" in fm.read_bytes()


def test_preflight_issues():
    d = _pdf(WHITE_PATH + b" " + BLACK_SMALL)
    rep = preflight.analyze(d, pdfium_parts=False)
    cats = {(i.category, i.severity) for i in rep.issues}
    assert ("overprint", "error") in cats and ("overprint", "warning") in cats
    white = next(i for i in rep.issues if i.category == "overprint" and i.severity == "error")
    assert white.pages == [1] and white.spots[0].box == (10.0, 10.0, 60.0, 60.0)
    assert "Überdrucken korrigieren" in white.message
    from pdfdruck.core import PreflightFixSettings  # the repair as a job (workflows, CLI)

    assert PreflightFixSettings(fix="overprint").fix == "overprint"
    clean = preflight.analyze(overprint.fix(d)[0], pdfium_parts=False)
    assert not [i for i in clean.issues if i.category == "overprint"]


def test_gs_args():
    assert overprint.ghostscript_args(True) == ["-dOverprint=/simulate"]
    assert overprint.ghostscript_args(False) == ["-dOverprint=/disable"]


def test_panel_and_proof():
    from pdfdruck import proof
    from pdfdruck.gui import preflightpanel as P

    rep = preflight.Report(
        overprint={"white": {1: [(0, 0, 1, 1)], 3: [(0, 0, 1, 1)]}, "black_text": {2: [(0, 0, 1, 1)]}}
    )
    assert P.overprint_counts(rep) == 3
    lines = P.overprint_lines(rep)
    assert lines[0] == "" and "verschwindet" in lines[1] and "spart aus" in lines[2]
    assert P.overprint_lines(preflight.Report()) == []
    spec = {"icc": "x.icc", "space": "CMYK"}
    assert proof.spec_key(spec) != proof.spec_key(dict(spec, overprint=False))
    assert "ohne Überdrucken" in proof.describe_spec(dict(spec, overprint=False))
    assert "Überdrucken" not in proof.describe_spec(spec)


def test_job():
    import tempfile

    from pdfdruck import core

    d = _pdf(WHITE_PATH)
    tmp = tempfile.mkdtemp()
    src, dst = os.path.join(tmp, "a.pdf"), os.path.join(tmp, "b.pdf")
    with open(src, "wb") as f:
        f.write(d)
    res = core._job_preflight_fix(src, dst, core.PreflightFixSettings(fix="overprint"), {}, None, None)
    with open(dst, "rb") as f:
        assert overprint.scan_bytes(f.read())["counts"]["white"] == 0
    assert res.notes


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
