# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Colour rules (colorrules.py, pdffunc.py): black -> 100 % K, spot colours renamed/merged/converted, cut contours."""

import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "_qtstub"))
sys.path.insert(0, os.path.join(HERE, ".."))

import pikepdf  # noqa: E402

from pdfdruck import colorrules as cr  # noqa: E402
from pdfdruck import l10n  # noqa: E402
from pdfdruck.pdffunc import compile_function  # noqa: E402

l10n.set_language("de")

FN = {"FunctionType": 2, "Domain": [0, 1], "C0": [0, 0, 0, 0], "C1": [0, 1, 0.8, 0], "N": 1}


def _pdf(content: bytes, extra_res=None) -> bytes:
    pdf = pikepdf.new()
    fn = pdf.make_indirect(pikepdf.Dictionary(**FN))

    def sep(n):
        return pikepdf.Array([pikepdf.Name.Separation, pikepdf.Name("/" + n), pikepdf.Name.DeviceCMYK, fn])

    font = pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica)
    img = pdf.make_stream(bytes([0, 128, 255, 64]))
    img.Type, img.Subtype = pikepdf.Name.XObject, pikepdf.Name.Image
    img.Width, img.Height, img.BitsPerComponent = 2, 2, 8
    img.ColorSpace = sep("HKS43K")
    sh = pikepdf.Dictionary(
        ShadingType=2,
        ColorSpace=sep("HKS 43 K"),
        Coords=[0, 0, 100, 0],
        Function=pikepdf.Dictionary(FunctionType=2, Domain=[0, 1], C0=[0], C1=[1], N=1),
    )
    form = pdf.make_stream(b"/CS2 CS 1 SCN 0.5 w 0 0 m 5 5 l S")
    form.Type, form.Subtype, form.BBox = pikepdf.Name.XObject, pikepdf.Name.Form, [0, 0, 10, 10]
    dn = pikepdf.Array(
        [pikepdf.Name.DeviceN, [pikepdf.Name("/Gold"), pikepdf.Name("/HKS43K")], pikepdf.Name.DeviceCMYK, fn]
    )
    res = pikepdf.Dictionary(
        Font=pikepdf.Dictionary(F1=font),
        ColorSpace=pikepdf.Dictionary(CS0=sep("HKS 43 K"), CS1=sep("HKS43K"), CS2=sep("Stanze"), CS3=dn),
        XObject=pikepdf.Dictionary(Im0=img, Fm0=form),
        Shading=pikepdf.Dictionary(Sh0=sh),
    )
    for k, v in (extra_res or {}).items():
        res[k] = v
    page = pikepdf.Dictionary(
        Type=pikepdf.Name.Page, MediaBox=[0, 0, 200, 200], Resources=res, Contents=pdf.make_stream(content)
    )
    pdf.pages.append(pikepdf.Page(page))
    b = io.BytesIO()
    pdf.save(b)
    return b.getvalue()


CONTENT = b"""0 0 0 rg BT /F1 9 Tf 10 10 Td (rgb black small) Tj ET
0.6 0.5 0.5 1 k BT /F1 9 Tf 10 30 Td (rich black) Tj 30 0 Td /F1 20 Tf (big) Tj ET
0 0 0 1 k BT /F1 9 Tf 10 50 Td (pure K) Tj ET
0.6 0.5 0.5 1 K 0.3 w 0 0 m 100 100 l S
0.6 0.5 0.5 1 K 3 w 0 0 m 100 100 l S
/CS0 cs 0.5 scn 10 10 50 50 re f
/CS1 cs 1 scn 10 70 50 50 re f
q 10 0 0 10 0 0 cm /Im0 Do Q /Sh0 sh /Fm0 Do"""


def _val(o):
    if isinstance(o, pikepdf.Name):
        return str(o)
    try:
        return float(o)
    except TypeError:
        return bytes(o) if isinstance(o, pikepdf.String) else "?"


def _ops(data: bytes, xobj: str | None = None) -> list:
    with pikepdf.open(io.BytesIO(data)) as p:
        pg = p.pages[0]
        src = pg.obj.Resources.XObject[xobj] if xobj else pg
        return [
            (str(i.operator), [_val(o) for o in i.operands])
            for i in pikepdf.parse_content_stream(src)
            if not isinstance(i, pikepdf.ContentStreamInlineImage)
        ]


def test_functions():
    pdf = pikepdf.new()
    assert compile_function(pikepdf.Dictionary(**FN))([0.5]) == [0.0, 0.5, 0.4, 0.0]
    f4 = pdf.make_stream(b"{ dup 0.5 gt { pop 1 } { 2 mul } ifelse 0 exch 0 0 }")
    f4.FunctionType, f4.Domain, f4.Range = 4, [0, 1], [0, 1] * 4
    assert compile_function(f4)([0.2]) == [0.0, 0.4, 0.0, 0.0] and compile_function(f4)([0.9])[1] == 1.0
    f0 = pdf.make_stream(bytes([0, 0, 0, 0, 0, 255, 128, 0]))
    f0.FunctionType, f0.Domain, f0.Range, f0.Size, f0.BitsPerSample = 0, [0, 1], [0, 1] * 4, [2], 8
    v = compile_function(f0)([0.5])
    assert abs(v[1] - 0.5) < 1e-9 and abs(v[2] - 128 / 255 / 2) < 1e-9
    f3 = pikepdf.Dictionary(
        FunctionType=3,
        Domain=[0, 1],
        Functions=[pikepdf.Dictionary(**FN), pikepdf.Dictionary(FunctionType=2, Domain=[0, 1], C0=[1], C1=[0], N=1)],
        Bounds=[0.5],
        Encode=[0, 1, 0, 1],
    )
    assert compile_function(f3)([0.25])[1] == 0.5 and compile_function(f3)([0.75]) == [0.5]
    try:
        compile_function(pikepdf.Dictionary(FunctionType=9))
        raise AssertionError("unknown type accepted")
    except ValueError:
        pass


def test_survey_and_plan():
    d = _pdf(CONTENT)
    sv = cr.survey(d)
    assert set(sv.spots) == {"HKS 43 K", "HKS43K", "Stanze", "Gold"} and sv.spots["Stanze"] == [1]
    assert sv.duplicates == [["HKS 43 K", "HKS43K"]] and sv.cut == ["Stanze"]
    plan = cr.rename_plan(sv, cr.ColorRulesSettings(cut_name="CutContour"))
    assert plan == {"HKS43K": "HKS 43 K", "Stanze": "CutContour"}
    plan = cr.rename_plan(sv, cr.ColorRulesSettings(merge_duplicates=False, rename={"Gold": "Gold 871"}))
    assert plan == {"Gold": "Gold 871"}
    assert cr.spot_key("HKS 43 K") == cr.spot_key("hks-43k") == "hks43k"


def test_black():
    d = _pdf(CONTENT)
    out, notes = cr.apply(d, cr.ColorRulesSettings(merge_duplicates=False))
    assert any("2 kleine Textstelle" in n for n in notes) and any("1 dünne Linie" in n for n in notes)
    ops = _ops(out)
    i = [k for k, (o, a) in enumerate(ops) if o == "Tj"]
    assert ops[i[0] - 1] == ("k", [0, 0, 0, 1]) and ops[i[0] + 1] == ("rg", [0, 0, 0])  # set and restored
    assert ops[i[1] - 1] == ("k", [0, 0, 0, 1]) and ops[i[1] + 1] == ("k", [0.6, 0.5, 0.5, 1])
    assert ops[i[2] - 1][0] != "k" or ops[i[2] - 1][1] != [0, 0, 0, 1]  # 20 pt: unchanged
    assert ops[i[3] - 1][0] == "Td"  # already pure K: nothing inserted
    s_ops = [k for k, (o, a) in enumerate(ops) if o == "S"]
    first_m = next(k for k, (o, a) in enumerate(ops) if o == "m")
    assert ops[first_m - 1] == ("K", [0, 0, 0, 1]) and ops[s_ops[0] + 1] == ("K", [0.6, 0.5, 0.5, 1])
    assert ops[s_ops[1] - 4][0] != "K" or ops[s_ops[1] - 4][1] != [0, 0, 0, 1]  # 3 pt line stays
    # nothing selected: unchanged
    same, n = cr.apply(d, cr.ColorRulesSettings(black_text=False, black_lines=False, merge_duplicates=False))
    assert same == d and "nichts" in n[0]


def test_spots_to_process():
    d = _pdf(CONTENT)
    out, notes = cr.apply(d, cr.ColorRulesSettings(black_text=False, black_lines=False, to_process=["*"]))
    assert any("HKS 43 K" in n and "1 Bild" in n and "1 Verläufe" in n for n in notes)
    ops = _ops(out)
    assert ("cs", ["/DeviceCMYK"]) in ops and ("scn", [0, 0.5, 0.4, 0]) in ops
    assert not any(o == "cs" and a == ["/CS1"] for o, a in ops)  # merged into HKS 43 K and converted
    with pikepdf.open(io.BytesIO(out)) as p:
        r = p.pages[0].obj.Resources
        im = r.XObject.Im0
        assert im.ColorSpace == pikepdf.Name.DeviceCMYK and im.read_bytes() == bytes.fromhex(
            "000000000080660000ffcc0000403300"
        )
        assert r.Shading.Sh0.ColorSpace == pikepdf.Name.DeviceCMYK and int(r.Shading.Sh0.Function.FunctionType) == 0
    sv = cr.survey(out)
    assert "HKS43K" not in sv.spots  # merged and converted; "HKS 43 K" remains only in the DeviceN (Gold + …)
    with pikepdf.open(io.BytesIO(out)) as p:
        assert set(p.pages[0].obj.Resources.ColorSpace.keys()) == {"/CS2", "/CS3"}  # unused resources removed
    assert "Stanze" in sv.spots  # cut contours are never converted by "*"
    # the converted page still renders
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(out)
    doc[0].render(scale=0.5).close()
    doc.close()


def test_cut_contour():
    d = _pdf(CONTENT)
    s = cr.ColorRulesSettings(black_text=False, black_lines=False, merge_duplicates=False, cut_name="CutContour")
    out, notes = cr.apply(d, s)
    assert any("„Stanze“ → „CutContour“" in n for n in notes) and any("Überdrucken" in n for n in notes)
    assert cr.survey(out).cut == ["CutContour"]
    fops = _ops(out, "/Fm0")
    i = fops.index(("S", []))
    assert fops[fops.index(("m", [0, 0])) - 1][0] == "gs" and fops[i + 1][0] == "gs"
    with pikepdf.open(io.BytesIO(out)) as p:
        egs = p.pages[0].obj.Resources.ExtGState
        assert bool(egs["/PMcr10"].OP) and int(egs["/PMcr10"].OPM) == 1
    again, n2 = cr.apply(out, s)
    assert again == out  # already right: nothing to do


def test_rename_devicen():
    d = _pdf(CONTENT)
    out, _ = cr.apply(d, cr.ColorRulesSettings(black_text=False, black_lines=False, rename={"Gold": "Gold 871"}))
    sv = cr.survey(out)
    assert "Gold 871" in sv.spots and "Gold" not in sv.spots and "HKS 43 K" in sv.spots


def test_job_and_workflow():
    from pdfdruck import core, workflow

    tmp = tempfile.mkdtemp()
    src, dst = os.path.join(tmp, "a.pdf"), os.path.join(tmp, "b.pdf")
    with open(src, "wb") as f:
        f.write(_pdf(CONTENT))
    res = core.run_job("colorrules", src, dst, {"cut_name": "CutContour", "to_process": ["*"]})
    assert res.info["changed"] and res.notes
    with open(dst, "rb") as f:
        assert cr.survey(f.read()).cut == ["CutContour"]
    sch = workflow.schema()
    assert "settings.colorrules" in sch["$defs"]
    props = sch["$defs"]["settings.colorrules"]["properties"]
    assert props["cut_name"]["default"] == "" and props["black_text_max_pt"]["default"] == 12.0


def test_dialog_helpers():
    from pdfdruck.gui import colorrulesdialog as D

    assert D.pages_text([1, 2, 3, 7, 9, 10]) == "1–3, 7, 9–10"
    assert D.pages_text([]) == "–" and D.pages_text([4]) == "4"
    dlg = D.ColorRulesDialog(None, _pdf(CONTENT))
    assert set(dlg.survey.spots) == {"HKS 43 K", "HKS43K", "Stanze", "Gold"}
    dlg.ed_alias = type("E", (), {"text": lambda self: "Cut,  Stanze ,"})()
    assert dlg.aliases() == ["Cut", "Stanze"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
