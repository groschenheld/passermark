# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# Public License, Version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
import os
import os as _os
import sys

_os.environ.setdefault("PASSERMARK_LANG", "de")  # tests check German texts
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pypdfium2 as pdfium

from pdfdruck.layout import (
    MM,
    LayoutSettings,
    Sheet,
    booklet_order,
    booklet_spreads,
    build_pdf,
    impose_with,
    page_doc_bleeds,
    page_trims,
    parse_ranges,
    plan,
    plan_step2,
    plan_step_repeat,
    select_pages,
)

A4 = Sheet(595.28, 841.89, (12, 12, 583.28, 829.89))  # ~4.2 mm margin
A3 = Sheet(841.89, 1190.55, (12, 12, 829.89, 1178.55))
src = pdfium.PdfDocument(os.path.join(os.path.dirname(__file__), "sample.pdf"))
sizes = [src.get_page_size(i) for i in range(len(src))]


def test_ranges():
    assert parse_ranges("1-3,5,7-", 8) == [0, 1, 2, 4, 6, 7]
    assert select_pages(7, "", "even") == [1, 3, 5]
    assert select_pages(7, "1-4", "odd", True) == [2, 0]
    try:
        parse_ranges("9", 7)
        assert False
    except ValueError:
        pass


def test_actual():
    p = plan(sizes, [0], A4, LayoutSettings(mode="actual"))[0]
    pl = p.placements[0]
    assert abs(pl.scale - 1) < 1e-9 and abs(pl.x) < 0.1 and p.warnings  # A4 on A4 with margin -> warning


def test_fit_auto_landscape():
    p = plan(sizes, [2], A4, LayoutSettings(mode="fit"))[0]
    assert p.landscape and p.placements[0].rot == 0 and not p.warnings


def test_nup_grids():
    for n, exp in [(2, (True, 2, 1)), (4, (False, 2, 2)), (6, (True, 3, 2)), (8, (True, 4, 2)), (16, (False, 4, 4))]:
        s = LayoutSettings(handling="multiple", nup=n)
        ps = plan(sizes, list(range(7)), A4, s)
        assert len(ps) == -(-7 // n), (n, len(ps))
        assert ps[0].landscape == exp[0], (n, ps[0].landscape)
        assert all(not w for p in ps for w in p.warnings)
    s = LayoutSettings(handling="multiple", cols=3, rows=1, orientation="landscape")
    ps = plan(sizes, list(range(7)), A3, s)
    assert len(ps) == 3 and ps[0].landscape


def test_render(tmp="/tmp/pdfdruck_test"):
    os.makedirs(tmp, exist_ok=True)
    cases = {
        "actual": (A4, LayoutSettings(mode="actual")),
        "fit": (A4, LayoutSettings(mode="fit")),
        "custom50": (A4, LayoutSettings(mode="custom", custom_percent=50)),
        "nup2": (A4, LayoutSettings(handling="multiple", nup=2, borders=True)),
        "nup6": (A4, LayoutSettings(handling="multiple", nup=6, borders=True, gap_mm=3, order="vertical")),
        "nup8": (A3, LayoutSettings(handling="multiple", nup=8, borders=True)),
        "grid3x1_tile40": (
            A4,
            LayoutSettings(handling="multiple", cols=3, rows=1, tile_mode="custom", tile_percent=40, borders=True),
        ),
    }
    for name, (sheet, s) in cases.items():
        out = os.path.join(tmp, name + ".pdf")
        build_pdf(src, sheet, list(range(len(src))), s, out)
        d = pdfium.PdfDocument(out)
        for i in range(len(d)):
            w, h = d.get_page_size(i)
            assert abs(w - sheet.width) < 0.1 and abs(h - sheet.height) < 0.1  # always physically portrait
        d[0].render(scale=0.3).to_pil().save(os.path.join(tmp, name + ".png"))


def test_booklet_order():
    o = booklet_order(8)
    assert o == [([7, 0], [1, 6]), ([5, 2], [3, 4])]
    assert booklet_order(8, "right")[0] == ([0, 7], [6, 1])
    assert len(booklet_order(5)) == 2  # 5 pages -> 8 (3 blank pages)


def test_booklet_plan():
    ps = plan(sizes, list(range(7)), A4, LayoutSettings(handling="booklet"))
    assert len(ps) == 4 and all(p.landscape for p in ps) and ps[0].duplex_short
    assert [pl.src for pl in ps[0].placements] == [0]  # sheet 1 front: [blank, 1]
    assert [pl.src for pl in ps[1].placements] == [1, 6]
    f = plan(sizes, list(range(7)), A4, LayoutSettings(handling="booklet", booklet_sides="front"))
    assert len(f) == 2 and not f[0].duplex_short


def test_poster():
    # A4 page upscaled to A2, printed on A4, 10 mm overlap
    s = LayoutSettings(handling="poster", poster_mode="target", poster_target="A2")
    ps = plan(sizes, [0], A4, s)
    assert len(ps) == 8, len(ps)  # 2x4 landscape: margin + 10 mm overlap cost space
    s = LayoutSettings(handling="poster", poster_mode="sheets", poster_cols=2, poster_rows=2)
    assert len(plan(sizes, [0], A4, s)) == 4
    s = LayoutSettings(handling="poster", poster_percent=100, poster_large_only=True)
    assert len(plan(sizes, [0, 2], A3, s)) == 2  # fits on A3 -> no tiling


def test_render_new(tmp="/tmp/pdfdruck_test"):
    os.makedirs(tmp, exist_ok=True)
    for name, sheet, s in [
        ("booklet", A4, LayoutSettings(handling="booklet", booklet_gutter_mm=6)),
        ("poster", A4, LayoutSettings(handling="poster", poster_mode="target", poster_target="A2")),
    ]:
        out = os.path.join(tmp, name + ".pdf")
        build_pdf(src, sheet, list(range(len(src))) if name == "booklet" else [0], s, out)
        d = pdfium.PdfDocument(out)
        for i in range(len(d)):
            d[i].render(
                scale=0.25, rotation=90 if d.get_page_size(i)[0] < d.get_page_size(i)[1] and name == "booklet" else 0
            ).to_pil().save(f"{tmp}/{name}_{i}.png")


def test_step_repeat_bleed_marks():
    from reportlab.lib.units import mm as _mm
    from reportlab.pdfgen import canvas

    c = canvas.Canvas("/tmp/_vk.pdf", pagesize=(85 * _mm, 55 * _mm))
    c.rect(0, 0, 10, 10)
    c.save()
    vk = pdfium.PdfDocument("/tmp/_vk.pdf")
    sz = [vk.get_page_size(0)]
    p0 = plan(sz, [0], A4, LayoutSettings(step_repeat=True))[0]
    assert len(p0.placements) == 10, len(p0.placements)  # classic 10 business cards on A4
    p1 = plan(sz, [0], A4, LayoutSettings(step_repeat=True, bleed_mm=3, crop_marks=True))[0]
    assert len(p1.placements) == 9 and p1.marks and p1.placements[0].bleed > 0
    out = impose_with(vk, A4, [p1], LayoutSettings())
    assert len(out) == 1


def test_step_repeat_orientation_join():
    s = LayoutSettings(step_repeat=True, sr_mode="grid", sr_cols=2, sr_rows=1)
    a3 = Sheet(841.89, 1190.55, None)  # borderless
    p = plan([(595.28, 841.89)], [0], a3, s)[0]
    assert p.landscape and not p.warnings  # 2 x A4 -> automatically landscape
    s.sr_orientation = "portrait"
    assert plan([(595.28, 841.89)], [0], a3, s)[0].warnings
    e = plan([(240.9, 155.9)], [0], A4, LayoutSettings(step_repeat=True, bleed_mm=3, sr_join="edge"))[0]
    pls = e.placements
    assert any(not all(pl.bleed_sides) for pl in pls)  # no bleed inside
    xs = sorted({round(pl.x, 1) for pl in pls})
    assert abs(xs[1] - xs[0] - pls[0].w) < 0.2  # edge to edge


def test_custom_edge():
    a4 = (595.28, 841.89)
    p = plan([a4], [0], A3, LayoutSettings(mode="custom", custom_by="short", custom_mm=148))[0].placements[0]
    assert abs(p.w / MM - 148) < 0.05 and abs(p.h / MM - 209.3) < 0.2  # A4 -> short edge 148 mm
    p = plan([a4], [0], A3, LayoutSettings(mode="custom", custom_by="long", custom_mm=420))[0].placements[0]
    assert abs(p.h / MM - 420) < 0.05 and abs(p.w / MM - 297) < 0.2  # long edge 420 -> A3
    q = plan([(841.89, 595.28)], [0], A3, LayoutSettings(mode="custom", custom_by="short", custom_mm=100))[0]
    pl = q.placements[0]
    assert abs(min(pl.w, pl.h) / MM - 100) < 0.05  # landscape: short edge = height
    p = plan([a4], [0], A3, LayoutSettings(mode="custom", custom_percent=50))[0].placements[0]
    assert abs(p.scale - 0.5) < 1e-9


def test_step_repeat_edge():
    a4 = (595.28, 841.89)
    sp = plan([a4], [0], A4, LayoutSettings(step_repeat=True, sr_by="short", sr_mm=70))[0]
    pl = sp.placements[0]
    assert abs(min(pl.w, pl.h) / MM - 70) < 0.05 and abs(max(pl.w, pl.h) / MM - 99.0) < 0.2
    assert len(sp.placements) >= 6  # A4 -> 70 × 99 mm fits several times on A4
    vk = (240.94, 155.91)  # 85 × 55 mm
    a = plan([vk], [0], A4, LayoutSettings(step_repeat=True, sr_by="long", sr_mm=85))[0]
    b = plan([vk], [0], A4, LayoutSettings(step_repeat=True))[0]
    assert len(a.placements) == len(b.placements) and abs(a.placements[0].scale - 1) < 0.001


def test_step_repeat_guard():
    a4 = (595.28, 841.89)
    try:
        plan([a4], [0], A4, LayoutSettings(step_repeat=True, sr_by="short", sr_mm=1))
        assert False
    except ValueError as e:
        assert "Nutzen pro Blatt" in str(e)
    assert len(plan([a4], [0], A4, LayoutSettings(step_repeat=True, sr_by="short", sr_mm=20))[0].placements) == 100
    try:
        plan([a4], [0], A4, LayoutSettings(handling="poster", poster_percent=5000))
        assert False
    except ValueError:
        pass


def test_step2_nutzen():
    from pdfdruck.layout import _logical, is_step2, plan_step2, step2_sheet

    A4s = Sheet(595.28, 841.89, None)  # step 1 sheet = chosen paper (A4)
    s = LayoutSettings(
        step_repeat=True,
        sr_mode="grid",
        sr_cols=3,
        sr_rows=3,
        sr_join="bleed",
        bleed_mm=2.0,
        crop_marks=True,
        sr_pass2=True,
        sr2_w_mm=320,
        sr2_h_mm=450,
        sr2_cols=0,
        sr2_rows=0,
    )
    assert is_step2(s)
    assert not is_step2(LayoutSettings(step_repeat=True))  # without the tick: off
    t = step2_sheet(s)
    assert abs(t.width - 320 * MM) < 0.01 and abs(t.height - 450 * MM) < 0.01
    # step 1: 9 business cards on A4 (as always, with bleed + marks)
    plans1 = plan([(240.94, 155.91)], [0], A4s, s)
    assert len(plans1[0].placements) == 9
    assert plans1[0].marks and any(pl.bleed > 0 for pl in plans1[0].placements)
    # step 2 automatic: the finished A4 sheet, unchanged, onto the target size
    plans2 = plan_step2((A4s.width, A4s.height), len(plans1), s)
    assert len(plans2) == len(plans1)  # one target sheet per step 1 sheet
    assert len(plans2[0].placements) >= 2  # automatic: several times on the sheet
    for sp in plans2:
        assert not sp.marks  # never additional marks/bleed
        for pl in sp.placements:
            assert abs(pl.scale - 1.0) < 1e-9 and pl.bleed <= 0 and pl.src < len(plans1)
            assert pl.trim is None  # the sheet stays complete (marks stay!)
    # the grid block is always centred (same margin left/right and top/bottom)
    sp = plans2[0]
    LW, LH, area = _logical(step2_sheet(s), sp.landscape)
    xs = [v for pl in sp.placements for v in (pl.x, pl.x + pl.w)]
    ys = [v for pl in sp.placements for v in (pl.y, pl.y + pl.h)]
    assert abs(min(xs) - (LW - max(xs))) < 1.0
    assert abs(min(ys) - (LH - max(ys))) < 1.0
    # fixed grid: 2 × 1 -> exactly 2
    s.sr2_cols, s.sr2_rows = 2, 1
    plans2 = plan_step2((A4s.width, A4s.height), len(plans1), s)
    assert len(plans2[0].placements) == 2
    # rotation from step 1 is taken over: sr_rotate=0 -> never rotated
    s.sr2_cols, s.sr2_rows = 0, 0
    s.sr_rotate = "0"
    plans2 = plan_step2((A4s.width, A4s.height), 1, s)
    assert all(pl.rot == 0 for sp in plans2 for pl in sp.placements)
    s.sr_rotate = "auto"
    # target size too small -> NO error: impose anyway, with a warning
    s.sr2_w_mm, s.sr2_h_mm = 100, 100
    plans2 = plan_step2((A4s.width, A4s.height), 1, s)
    assert len(plans2) == 1 and len(plans2[0].placements) == 1
    assert plans2[0].warnings and "beschnitten" in plans2[0].warnings[0]
    # grid too large for the target size -> also a warning instead of an error
    s.sr2_w_mm, s.sr2_h_mm, s.sr2_cols, s.sr2_rows = 320, 450, 3, 3
    plans2 = plan_step2((A4s.width, A4s.height), 1, s)
    assert len(plans2[0].placements) == 9 and plans2[0].warnings
    # ... and the block still centred (symmetric overhang)
    sp = plans2[0]
    LW, LH, area = _logical(step2_sheet(s), sp.landscape)
    xs = [v for pl in sp.placements for v in (pl.x, pl.x + pl.w)]
    assert abs(min(xs) - (LW - max(xs))) < 1.0
    s.sr2_cols, s.sr2_rows = 0, 0


def test_step_repeat_trim_show_edge():
    """Step and repeat + TrimBox: the outer sides of the block show the real document edge
    (existing crop marks are used, not cut off).
    """
    sizes = [(302.05, 216.91)]  # 106.5 x 76.5 mm
    trims = [(30.5039, 30.5039, 30.5040, 30.5040)]  # trim size 85 x 55 mm
    bleeds = [8.5039]  # document bleed 3 mm
    sheet = Sheet(595.28, 841.89, None)  # A4
    s = LayoutSettings(step_repeat=True, sr_mode="grid", sr_cols=3, sr_rows=3, sr_join="bleed")
    plans = plan(sizes, [0], sheet, s, trims, bleeds)
    assert len(plans[0].placements) == 9
    for pl in plans[0].placements:
        # trim_show_edge only on the outer sides of the block
        assert pl.trim_show_edge[0] == (pl.x == min(p.x for p in plans[0].placements))
        assert pl.trim_show_edge[2] == (pl.x + pl.w == max(p.x + p.w for p in plans[0].placements))
        assert pl.trim_show_edge[3] == (pl.y + pl.h == max(p.y + p.h for p in plans[0].placements))
        assert pl.trim_show_edge[1] == (pl.y == min(p.y for p in plans[0].placements))
    # tile extent: outside up to the real edge, inside only the configured bleed
    for pl in plans[0].placements:
        b = pl.bleed
        eL = pl.trim[0] * pl.scale
        bL = max(b if pl.bleed_sides[0] else 0.0, eL if pl.trim_show_edge[0] else 0.0)
        if pl.trim_show_edge[0]:
            assert bL >= eL - 0.01  # whole document edge visible (marks!)
        else:
            assert bL == (b if pl.bleed_sides[0] else 0.0)
    # without TrimBox: no change (trim_show_edge has no effect)
    plans2 = plan(sizes, [0], sheet, s, None, None)
    for pl in plans2[0].placements:
        assert pl.trim is None  # no trim size -> fast path


def test_step2_raster_exakt():
    """A defined grid is always imposed exactly (step 1 + 2) – if it does not
    fit, it is clipped symmetrically with a warning, but never reduced.
    Auto in step 2 places as many sheets as fit on the target size
    (2 × A4 on A3).
    """
    from pdfdruck.layout import _logical, plan_step2

    A4t = (595.28, 841.89)
    A3 = Sheet(297 * MM, 420 * MM, None)
    s = LayoutSettings(step_repeat=True, sr_pass2=True, sr2_w_mm=297, sr2_h_mm=420)
    # auto: 2 A4 fit on A3 (landscape, side by side)
    plans = plan_step2(A4t, 1, s, target=A3)
    assert len(plans[0].placements) == 2 and not plans[0].warnings
    # fixed 2 x 1: identical
    s.sr2_cols, s.sr2_rows = 2, 1
    plans = plan_step2(A4t, 1, s, target=A3)
    assert len(plans[0].placements) == 2 and not plans[0].warnings
    # fixed 3 x 3 on an A3 that is too small: 9 stay 9, warning, symmetric overhang
    s.sr2_cols, s.sr2_rows = 3, 3
    plans = plan_step2(A4t, 1, s, target=A3)
    sp = plans[0]
    assert len(sp.placements) == 9 and sp.warnings
    xs = [v for pl in sp.placements for v in (pl.x, pl.x + pl.w)]
    LW, LH, area = _logical(A3, sp.landscape)
    assert abs(min(xs) - (LW - max(xs))) < 1.0
    # rotation from step 1: sr_rotate=90 -> sheet rotated, 2 below each other on A3 portrait
    s.sr2_cols, s.sr2_rows = 0, 0
    s.sr_rotate = "90"
    plans = plan_step2(A4t, 1, s, target=A3)
    assert len(plans[0].placements) == 2 and all(pl.rot == 90 for pl in plans[0].placements)
    s.sr_rotate = "auto"
    # step 1: a fixed grid stays exact even if too small (warning only)
    small = Sheet(100 * MM, 150 * MM, None)
    s1 = LayoutSettings(step_repeat=True, sr_mode="grid", sr_cols=3, sr_rows=3, sr_join="bleed", bleed_mm=3.0)
    p1 = plan([(241, 156)], [0], small, s1, [(30.5, 30.5, 30.5, 30.5)], [8.5])
    assert len(p1[0].placements) == 9 and p1[0].warnings


def test_booklet_spreads():
    """Booklet -> spreads: trim size opened, order, bleed only outside,
    side by side/one above the other; afterwards step-and-repeat mode imposes them without a warning.
    """
    import io

    import pikepdf
    from reportlab.pdfgen import canvas

    MMx = 72 / 25.4
    cols = [(1, 0, 0), (0, 0.6, 0), (0, 0, 1), (1, 0.8, 0), (0.6, 0, 0.6), (0, 0.7, 0.7), (0.3, 0.3, 0.3), (1, 0.5, 0)]
    b = io.BytesIO()
    c = canvas.Canvas(b)
    for i in range(8):  # 210 × 210 mm + 3 mm bleed, own colour per page
        c.setPageSize((216 * MMx, 216 * MMx))
        c.setFillColorRGB(*cols[i])
        c.rect(0, 0, 216 * MMx, 216 * MMx, fill=1, stroke=0)
        c.showPage()
    c.save()
    pk = pikepdf.open(io.BytesIO(b.getvalue()))
    for pg in pk.pages:
        pg.TrimBox = [3 * MMx, 3 * MMx, 213 * MMx, 213 * MMx]
    o = io.BytesIO()
    pk.save(o)
    src = pdfium.PdfDocument(o.getvalue())
    px = lambda img, x, y: img.getpixel((int(x), int(y)))[:3]
    for mode, size in (("side", (426, 216)), ("top", (216, 426))):
        out, notes = booklet_spreads(src, list(range(8)), LayoutSettings(handling="booklet", booklet_spread=mode))
        w, h = out.get_page_size(0)
        assert len(out) == 4 and (round(w / MMx), round(h / MMx)) == size, (mode, w / MMx, h / MMx)
        img = out[0].render(scale=1).to_pil().convert("RGB")
        W, H = img.size
        # sheet 1 front: page 8 | page 1 (or 8 on top, 1 below); real bleed outside, cut at the fold
        if mode == "side":
            a, z, fa, fz = (1, H / 2), (W - 2, H / 2), (W / 2 - 2, H / 2), (W / 2 + 2, H / 2)
        else:
            a, z, fa, fz = (W / 2, 1), (W / 2, H - 2), (W / 2, H / 2 - 2), (W / 2, H / 2 + 2)
        assert px(img, *a) == px(img, *fa) == (255, 128, 0)  # page 8
        assert px(img, *z) == px(img, *fz) == (255, 0, 0)  # page 1
        t = page_trims(out)[0]
        assert t and all(abs(v - 3 * MMx) < 0.5 for v in t)  # TrimBox set, 3 mm bleed
        # step and repeat imposes the spreads without a warning
        sz = [out.get_page_size(i) for i in range(len(out))]
        ps = plan(
            sz,
            list(range(len(out))),
            Sheet(320 * MMx, 450 * MMx, None),
            LayoutSettings(step_repeat=True, sr_join="bleed", bleed_mm=3),
            page_trims(out),
            page_doc_bleeds(out),
        )
        assert ps and ps[0].placements and not ps[0].warnings


def test_step_repeat_rotates_when_nothing_fits():
    """Grid 2 × 4 A6 with bleed + crop marks on A3 never fits completely: portrait data are rotated and
    end up exactly like landscape data (instead of staying unrotated and overhanging by 20 cm).
    """
    import dataclasses

    a3 = Sheet(297 * MM, 420 * MM, None)
    s = LayoutSettings(
        step_repeat=True, sr_mode="grid", sr_cols=2, sr_rows=4, bleed_mm=3, crop_marks=True, use_margins=False
    )
    res = {}
    for name, (w, h) in (("hoch", (105, 148)), ("quer", (148, 105))):
        sp = plan_step_repeat([(w * MM, h * MM)], [0], a3, s)[0]
        xs = sorted({round(pl.x / MM) for pl in sp.placements})
        ys = sorted({round(pl.y / MM) for pl in sp.placements})
        res[name] = (sp.landscape, len(xs), len(ys), round(sp.placements[0].w / MM), round(sp.placements[0].h / MM))
        assert sp.warnings  # does not fit completely – the warning stays
        assert sp.placements[0].rot == (90 if name == "hoch" else 0), (name, sp.label)
    assert res["hoch"] == res["quer"] == (False, 2, 4, 148, 105), res
    # "Nutzen drehen: 0°" stays forced unrotated
    sp = plan_step_repeat([(105 * MM, 148 * MM)], [0], a3, dataclasses.replace(s, sr_rotate="0"))[0]
    assert sp.placements[0].rot == 0
    # if everything fits, the principle "unrotated" holds (even if rotated would leave more room)
    sp = plan_step_repeat([(105 * MM, 148 * MM)], [0], a3, dataclasses.replace(s, sr_cols=2, sr_rows=2))[0]
    assert sp.placements[0].rot == 0 and not sp.warnings
    # does not fit even once: orientation with the smallest overhang
    sp = plan_step_repeat([(440 * MM, 300 * MM)], [0], a3, LayoutSettings(step_repeat=True, use_margins=False))[0]
    assert len(sp.placements) == 1 and sp.landscape, sp.label


def test_step2_rotates_when_nothing_fits():
    """Step 2: sheet 200 × 300 in a 1 × 2 grid on 600 × 300 – unrotated far too tall, rotated it almost fits."""
    s = LayoutSettings(
        step_repeat=True, sr_pass2=True, sr2_w_mm=590, sr2_h_mm=300, sr2_cols=2, sr2_rows=1, sr_orientation="portrait"
    )
    plans = plan_step2((200 * MM, 300 * MM), 1, s)
    assert plans[0].placements[0].rot == 0  # 2 × 1 unrotated: 400 × 300 fits
    s.sr2_cols, s.sr2_rows = 1, 2
    plans = plan_step2((200 * MM, 300 * MM), 1, s)
    assert plans[0].placements[0].rot == 90, plans[0].label  # 1 × 2: rotated 300 × 400 instead of 200 × 600


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
