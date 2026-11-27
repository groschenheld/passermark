# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Check report as PDF (checkreport.py) and the ink coverage check (TAC) of the check profiles."""

import io
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ.setdefault("PASSERMARK_LANG", "de")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()  # no chosen profile of the developer
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]
import pikepdf

from pdfdruck import checkprofile, checkreport, cmyk, preflight

# small text, a hairline and a 400 % CMYK area on page 1; small text on page 2, which is rotated by 90°
P1 = b"BT /F1 4 Tf 100 700 Td (tiny text) Tj ET 0.05 w 100 600 m 400 600 l S 1 1 1 1 k 300 200 100 80 re f"
P2 = b"BT /F1 4 Tf 400 100 Td (tiny rotated) Tj ET"


def _doc() -> bytes:
    pdf = pikepdf.new()
    font = pdf.make_indirect(
        pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica)
    )
    for content in (P1, P2):
        pdf.add_blank_page(page_size=(595, 842))
        pg = pdf.pages[-1]
        pg.obj.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font))
        pg.obj.Contents = pdf.make_stream(content)
    pdf.pages[1].obj.Rotate = 90
    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()


def test_tac_only_with_limit():
    data = _doc()
    std = preflight.analyze(data, profile="standard")
    assert not std.tac and "ink_tac" not in {i.check for i in std.issues}
    off = preflight.analyze(data, profile="offset")
    assert checkprofile.BUILTIN["offset"].limit("tac_max") == 300.0
    iss = [i for i in off.issues if i.check == "ink_tac"]
    assert len(iss) == 1 and iss[0].pages == [1] and iss[0].category == "ink"
    assert off.tac["max"] >= 399 and off.tac["page"] == 1
    assert "400 %" in iss[0].message
    # higher limit: nothing to report, the check counts as passed
    p = checkprofile.from_dict({"name": "t", "limits": {"tac_max": 400}})
    hi = preflight.analyze(data, profile=p)
    assert "ink_tac" not in {i.check for i in hi.issues} and "ink_tac" in hi.passed


def test_tac_areas_with_ghostscript():
    if not cmyk.ghostscript():
        print("skip: kein Ghostscript")
        return
    rep = preflight.analyze(_doc(), profile="offset")
    assert rep.tac["method"] == "gs"
    (box,) = rep.tac["areas"][1]
    # the 400 % area 300,200 – 400,280 (coarse raster: a few pt tolerance)
    assert abs(box[0] - 300) < 8 and abs(box[1] - 200) < 8 and abs(box[2] - 400) < 8 and abs(box[3] - 280) < 8


def test_tac_boxes_follow_rotation():
    import numpy as np

    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(200, 100))  # 200 × 100 pt, area at x 20–40, y 10–30 (lower left)
    page = pdf.pages[0].obj
    s = preflight.TAC_DPI / 72.0
    for rot in (0, 90, 180, 270):
        page.Rotate = rot
        w, h = (200, 100) if rot in (0, 180) else (100, 200)  # rendered (rotated) size in pt
        m = np.zeros((round(h * s), round(w * s)), bool)
        # where the area lands in the rotated view (u to the right, v downwards, pt)
        u0, u1, v0, v1 = {
            0: (20, 40, 70, 90),
            90: (10, 30, 20, 40),
            180: (160, 180, 10, 30),
            270: (70, 90, 160, 180),
        }[rot]
        m[round(v0 * s) : round(v1 * s), round(u0 * s) : round(u1 * s)] = True
        (b,) = preflight._tac_boxes(m, page)
        assert all(abs(a - e) < 4 for a, e in zip(b, (20, 10, 40, 30))), (rot, b)


def test_report_pdf_marks_the_locations():
    data = _doc()
    rep = preflight.analyze(data, profile="offset")
    out = os.path.join(tempfile.mkdtemp(), "bericht.pdf")
    r = checkreport.write_pdf(rep, data, out, "test.pdf")
    assert r["marked"] == 2 and os.path.isfile(out)
    with pikepdf.open(out) as pdf:
        assert len(pdf.pages) == r["pages"] >= 3
        n_sum = r["pages"] - 2
        p1, p2 = pdf.pages[n_sum], pdf.pages[n_sum + 1]
        assert int(p2.obj.get("/Rotate", 0)) == 90  # original page geometry kept
        ops = (
            b"".join(c.read_bytes() for c in p1.obj.Contents)
            if isinstance(p1.obj.Contents, pikepdf.Array)
            else p1.obj.Contents.read_bytes()
        )
        assert ops.startswith(b"q") and b"re S" in ops and b"Tj" in ops
        with pdf.open_outline() as ol:
            titles = [x.title for x in ol.root]
        assert titles[0] == "Zusammenfassung" and titles[1].startswith("Seite 1")
    # numbers of the marks follow the order of the findings
    mk = checkreport.marks(rep)
    small = next(n for n, i in enumerate(rep.issues, 1) if i.check == "text_small")
    assert any(nr == small for nr, _sev, _b in mk[2])


def test_report_pdf_without_findings_with_location():
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(595, 842))
    buf = io.BytesIO()
    pdf.save(buf)
    rep = preflight.analyze(buf.getvalue(), profile="screen")
    out = os.path.join(tempfile.mkdtemp(), "leer.pdf")
    r = checkreport.write_pdf(rep, buf.getvalue(), out)
    assert r["marked"] == 0 and r["pages"] >= 1


def test_cli_report():
    tmp = tempfile.mkdtemp()
    src, out = os.path.join(tmp, "in.pdf"), os.path.join(tmp, "bericht.pdf")
    with open(src, "wb") as f:
        f.write(_doc())
    env = dict(os.environ, PYTHONPATH=ROOT)
    r = subprocess.run(
        [sys.executable, "-m", "pdfdruck.cli", "inspect", src, "--report", out, "--profile", "offset", "--json"],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert d["check"]["report_pdf"]["marked"] == 2 and os.path.isfile(out)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
