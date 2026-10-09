# SPDX-License-Identifier: GPL-3.0-or-later
"""Seiten teilen (1.10.2): Doppelseiten einer falsch exportierten Broschüre, Hälften, Raster, gedrehte Seiten,
Endformat/Anschnitt, Reihenfolge rechts→links, verlustfrei (Inhalt geteilt, nicht kopiert), Kommandozeile."""
import os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="pm-split-")
os.environ.setdefault("PASSERMARK_LANG", "de")
import numpy as np
import pikepdf
import pypdfium2 as pdfium
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from pdfdruck import split

A4, A3Q = (210 * mm, 297 * mm), (420 * mm, 297 * mm)
COLORS = [(1, 0, 0), (0, 0.6, 0), (0, 0, 1), (1, 0.6, 0), (0.6, 0, 0.6), (0, 0.6, 0.6)]


def _booklet(path, bleed=0.0):
    """S. 1 A4 · S. 2+3 und 4+5 als Doppelseite A3 quer · S. 6 A4 – jede logische Seite vollflächig eigene Farbe."""
    c = canvas.Canvas(path)
    layout = [[0], [1, 2], [3, 4], [5]]
    for pages in layout:
        w, h = (A4 if len(pages) == 1 else A3Q)
        W, H = w + 2 * bleed, h + 2 * bleed
        c.setPageSize((W, H))
        for k, pg in enumerate(pages):
            c.setFillColorRGB(*COLORS[pg])
            x0 = 0 if k == 0 else bleed + w / 2
            x1 = W if k == len(pages) - 1 else bleed + w / 2
            c.rect(x0, 0, x1 - x0, H, fill=1, stroke=0)
        c.showPage()
    c.save()
    if bleed:
        with pikepdf.open(path, allow_overwriting_input=True) as pdf:
            for p in pdf.pages:
                W, H = float(p.MediaBox[2]), float(p.MediaBox[3])
                p.TrimBox = [bleed, bleed, W - bleed, H - bleed]
            pdf.save(path)
    return path


def _color(page):
    a = np.array(page.render(scale=0.2).to_pil().convert("RGB")).reshape(-1, 3).mean(axis=0) / 255
    return tuple(round(float(x), 1) for x in a)


def test_spreads_detected_and_split_in_order():
    src = _booklet(os.path.join(TMP, "b.pdf"))
    data, info = split.split(src, split.SplitSettings(only_spreads=True))
    assert info == {"pages_in": 4, "pages_out": 6, "split": 2}, info
    d = pdfium.PdfDocument(data)
    assert [round(d[i].get_size()[0] / mm) for i in range(6)] == [210] * 6
    got = [_color(d[i]) for i in range(6)]
    exp = [tuple(round(x, 1) for x in c) for c in COLORS]
    assert got == exp, (got, exp)
    d.close()
    # rechts → links: auf den Doppelseiten kommt die rechte Hälfte zuerst
    data, _ = split.split(src, split.SplitSettings(only_spreads=True, rtl=True))
    d = pdfium.PdfDocument(data)
    assert _color(d[1]) == exp[2] and _color(d[2]) == exp[1]
    d.close()


def test_lossless_shared_content():
    """Inhalt wird nicht kopiert: beide Hälften zeigen auf denselben Inhaltsstrom."""
    src = _booklet(os.path.join(TMP, "b2.pdf"))
    data, _ = split.split(src, split.SplitSettings(only_spreads=True))
    with pikepdf.open(__import__("io").BytesIO(data)) as pdf:
        a, b = pdf.pages[1].obj.Contents, pdf.pages[2].obj.Contents
        assert a.objgen == b.objgen
    assert len(data) < os.path.getsize(src) * 1.5


def test_trim_and_bleed_kept_outside():
    """Mit Endformat: Teilung in der Mitte des Endformats, Anschnitt nur außen, TrimBox je Hälfte A4."""
    b = 3 * mm
    src = _booklet(os.path.join(TMP, "b3.pdf"), bleed=b)
    data, _ = split.split(src, split.SplitSettings(only_spreads=True))
    with pikepdf.open(__import__("io").BytesIO(data)) as pdf:
        left, right = pdf.pages[1].obj, pdf.pages[2].obj
        lt, rt = [float(x) for x in left.TrimBox], [float(x) for x in right.TrimBox]
        assert abs((lt[2] - lt[0]) - A4[0]) < 0.5 and abs((rt[2] - rt[0]) - A4[0]) < 0.5, (lt, rt)
        lm, rm = [float(x) for x in left.MediaBox], [float(x) for x in right.MediaBox]
        assert abs(lt[0] - lm[0] - b) < 0.5 and abs(lm[2] - lt[2]) < 0.5      # links: Anschnitt außen, innen keiner
        assert abs(rt[0] - rm[0]) < 0.5 and abs(rm[2] - rt[2] - b) < 0.5


def test_grid_and_rotated_page():
    src = os.path.join(TMP, "r.pdf")
    c = canvas.Canvas(src, pagesize=A4)
    for i, col in enumerate(COLORS[:4]):                 # 2×2 Felder in sichtbarer Lage (nach Drehung)
        c.setFillColorRGB(*col)
        c.rect((i % 2) * A4[0] / 2, (1 - i // 2) * A4[1] / 2, A4[0] / 2, A4[1] / 2, fill=1, stroke=0)
    c.showPage()
    c.save()
    data, info = split.split(src, split.SplitSettings(mode="grid", cols=2, rows=2))
    d = pdfium.PdfDocument(data)
    assert info["pages_out"] == 4 and [_color(d[i]) for i in range(4)] == [tuple(round(x, 1) for x in c)
                                                                        for c in COLORS[:4]]
    d.close()
    with pikepdf.open(src, allow_overwriting_input=True) as pdf:
        pdf.pages[0].Rotate = 90
        pdf.save(src)
    data, info = split.split(src, split.SplitSettings(mode="halves_v"))
    d = pdfium.PdfDocument(data)
    w, h = d[0].get_size()
    assert abs(w - A4[1] / 2) < 1 and abs(h - A4[0]) < 1, (w / mm, h / mm)    # sichtbar quer, links|rechts geteilt
    d.close()


def test_nothing_to_split_is_an_error():
    src = os.path.join(TMP, "a4.pdf")
    c = canvas.Canvas(src, pagesize=A4)
    c.showPage()
    c.showPage()
    c.save()
    try:
        split.split(src, split.SplitSettings(only_spreads=True))
        raise AssertionError
    except ValueError as e:
        assert "Doppelseiten" in str(e)


def test_cli():
    src = _booklet(os.path.join(TMP, "b4.pdf"))
    out = os.path.join(TMP, "out.pdf")
    env = dict(os.environ, PYTHONPATH=ROOT)
    r = subprocess.run([sys.executable, "-m", "pdfdruck.cli", "split", src, out, "--set", "only_spreads=true",
                        "--quiet"], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    assert len(pdfium.PdfDocument(out)) == 6
    r = subprocess.run([sys.executable, "-m", "pdfdruck.cli", "split", src, out, "--set", "mode=grid",
                        "--set", "cols=3", "--set", "rows=1", "--pages", "1", "--quiet"], capture_output=True,
                       text=True, env=env)
    assert r.returncode == 0 and len(pdfium.PdfDocument(out)) == 6, r.stderr     # Seite 1 → 3, Rest bleibt


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
