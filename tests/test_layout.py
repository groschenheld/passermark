# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
import sys, os
import os as _os
_os.environ.setdefault("PASSERMARK_LANG", "de")   # Tests prüfen deutsche Texte
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pypdfium2 as pdfium
from pdfdruck.layout import *

A4 = Sheet(595.28, 841.89, (12, 12, 583.28, 829.89))   # ~4.2 mm Rand
A3 = Sheet(841.89, 1190.55, (12, 12, 829.89, 1178.55))
src = pdfium.PdfDocument(os.path.join(os.path.dirname(__file__), "sample.pdf"))
sizes = [src.get_page_size(i) for i in range(len(src))]

def test_ranges():
    assert parse_ranges("1-3,5,7-", 8) == [0,1,2,4,6,7]
    assert select_pages(7, "", "even") == [1,3,5]
    assert select_pages(7, "1-4", "odd", True) == [2,0]
    try: parse_ranges("9", 7); assert False
    except ValueError: pass

def test_actual():
    p = plan(sizes, [0], A4, LayoutSettings(mode="actual"))[0]
    pl = p.placements[0]
    assert abs(pl.scale-1) < 1e-9 and abs(pl.x) < .1 and p.warnings   # A4 auf A4 mit Rand -> Warnung

def test_fit_auto_landscape():
    p = plan(sizes, [2], A4, LayoutSettings(mode="fit"))[0]
    assert p.landscape and p.placements[0].rot == 0 and not p.warnings

def test_nup_grids():
    for n, exp in [(2,(True,2,1)),(4,(False,2,2)),(6,(True,3,2)),(8,(True,4,2)),(16,(False,4,4))]:
        s = LayoutSettings(handling="multiple", nup=n)
        ps = plan(sizes, list(range(7)), A4, s)
        assert len(ps) == -(-7//n), (n, len(ps))
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
        "grid3x1_tile40": (A4, LayoutSettings(handling="multiple", cols=3, rows=1, tile_mode="custom", tile_percent=40, borders=True)),
    }
    for name, (sheet, s) in cases.items():
        out = os.path.join(tmp, name + ".pdf")
        build_pdf(src, sheet, list(range(len(src))), s, out)
        d = pdfium.PdfDocument(out)
        for i in range(len(d)):
            w, h = d.get_page_size(i)
            assert abs(w - sheet.width) < .1 and abs(h - sheet.height) < .1  # immer physisch Hochformat
        d[0].render(scale=0.3).to_pil().save(os.path.join(tmp, name + ".png"))



def test_booklet_order():
    o = booklet_order(8)
    assert o == [([7, 0], [1, 6]), ([5, 2], [3, 4])]
    assert booklet_order(8, "right")[0] == ([0, 7], [6, 1])
    assert len(booklet_order(5)) == 2          # 5 Seiten -> 8 (3 Leerseiten)


def test_booklet_plan():
    ps = plan(sizes, list(range(7)), A4, LayoutSettings(handling="booklet"))
    assert len(ps) == 4 and all(p.landscape for p in ps) and ps[0].duplex_short
    assert [pl.src for pl in ps[0].placements] == [0]      # Bogen 1 vorne: [Leer, 1]
    assert [pl.src for pl in ps[1].placements] == [1, 6]
    f = plan(sizes, list(range(7)), A4, LayoutSettings(handling="booklet", booklet_sides="front"))
    assert len(f) == 2 and not f[0].duplex_short


def test_poster():
    # A4-Seite auf A2 hochskaliert, auf A4 gedruckt, 10 mm Überlappung
    s = LayoutSettings(handling="poster", poster_mode="target", poster_target="A2")
    ps = plan(sizes, [0], A4, s)
    assert len(ps) == 8, len(ps)            # 2x4 quer: Rand + 10 mm Überlappung kosten Platz
    s = LayoutSettings(handling="poster", poster_mode="sheets", poster_cols=2, poster_rows=2)
    assert len(plan(sizes, [0], A4, s)) == 4
    s = LayoutSettings(handling="poster", poster_percent=100, poster_large_only=True)
    assert len(plan(sizes, [0, 2], A3, s)) == 2      # passt auf A3 -> keine Kachelung


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
            d[i].render(scale=0.25, rotation=90 if d.get_page_size(i)[0] < d.get_page_size(i)[1] and name == "booklet" else 0).to_pil().save(f"{tmp}/{name}_{i}.png")


def test_step_repeat_bleed_marks():
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm as _mm
    c = canvas.Canvas("/tmp/_vk.pdf", pagesize=(85 * _mm, 55 * _mm)); c.rect(0, 0, 10, 10); c.save()
    vk = pdfium.PdfDocument("/tmp/_vk.pdf")
    sz = [vk.get_page_size(0)]
    p0 = plan(sz, [0], A4, LayoutSettings(step_repeat=True))[0]
    assert len(p0.placements) == 10, len(p0.placements)          # klassisch 10 Visitenkarten auf A4
    p1 = plan(sz, [0], A4, LayoutSettings(step_repeat=True, bleed_mm=3, crop_marks=True))[0]
    assert len(p1.placements) == 9 and p1.marks and p1.placements[0].bleed > 0
    out = impose_with(vk, A4, [p1], LayoutSettings())
    assert len(out) == 1


def test_step_repeat_orientation_join():
    s = LayoutSettings(step_repeat=True, sr_mode="grid", sr_cols=2, sr_rows=1)
    a3 = Sheet(841.89, 1190.55, None)                      # randlos
    p = plan([(595.28, 841.89)], [0], a3, s)[0]
    assert p.landscape and not p.warnings                  # 2 x A4 -> automatisch quer
    s.sr_orientation = "portrait"
    assert plan([(595.28, 841.89)], [0], a3, s)[0].warnings
    e = plan([(240.9, 155.9)], [0], A4, LayoutSettings(step_repeat=True, bleed_mm=3, sr_join="edge"))[0]
    pls = e.placements
    assert any(not all(pl.bleed_sides) for pl in pls)      # innen kein Anschnitt
    xs = sorted({round(pl.x, 1) for pl in pls})
    assert abs(xs[1] - xs[0] - pls[0].w) < 0.2              # Kante an Kante


def test_custom_edge():
    a4 = (595.28, 841.89)
    p = plan([a4], [0], A3, LayoutSettings(mode="custom", custom_by="short", custom_mm=148))[0].placements[0]
    assert abs(p.w / MM - 148) < 0.05 and abs(p.h / MM - 209.3) < 0.2       # A4 -> kurze Kante 148 mm
    p = plan([a4], [0], A3, LayoutSettings(mode="custom", custom_by="long", custom_mm=420))[0].placements[0]
    assert abs(p.h / MM - 420) < 0.05 and abs(p.w / MM - 297) < 0.2        # lange Kante 420 -> A3
    q = plan([(841.89, 595.28)], [0], A3, LayoutSettings(mode="custom", custom_by="short", custom_mm=100))[0]
    pl = q.placements[0]
    assert abs(min(pl.w, pl.h) / MM - 100) < 0.05                            # Querformat: kurze Kante = Höhe
    p = plan([a4], [0], A3, LayoutSettings(mode="custom", custom_percent=50))[0].placements[0]
    assert abs(p.scale - 0.5) < 1e-9


def test_step_repeat_edge():
    a4 = (595.28, 841.89)
    sp = plan([a4], [0], A4, LayoutSettings(step_repeat=True, sr_by="short", sr_mm=70))[0]
    pl = sp.placements[0]
    assert abs(min(pl.w, pl.h) / MM - 70) < 0.05 and abs(max(pl.w, pl.h) / MM - 99.0) < 0.2
    assert len(sp.placements) >= 6                       # A4 -> 70 × 99 mm passt mehrfach auf A4
    vk = (240.94, 155.91)                                # 85 × 55 mm
    a = plan([vk], [0], A4, LayoutSettings(step_repeat=True, sr_by="long", sr_mm=85))[0]
    b = plan([vk], [0], A4, LayoutSettings(step_repeat=True))[0]
    assert len(a.placements) == len(b.placements) and abs(a.placements[0].scale - 1) < 0.001


def test_step_repeat_guard():
    a4 = (595.28, 841.89)
    try:
        plan([a4], [0], A4, LayoutSettings(step_repeat=True, sr_by="short", sr_mm=1)); assert False
    except ValueError as e:
        assert "Nutzen pro Blatt" in str(e)
    assert len(plan([a4], [0], A4, LayoutSettings(step_repeat=True, sr_by="short", sr_mm=20))[0].placements) == 100
    try:
        plan([a4], [0], A4, LayoutSettings(handling="poster", poster_percent=5000)); assert False
    except ValueError:
        pass


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("ok", k)
