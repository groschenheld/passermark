# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("PASSERMARK_LANG", "de")
import pypdfium2 as pdfium
from pdfdruck import cmyk, pdfmanip

MM = 72 / 25.4
FOGRA = "/usr/share/texlive/texmf-dist/tex/generic/colorprofiles/FOGRA39L_coated.icc"


def _pdf(sizes_mm, path="/tmp/_crop.pdf", rotate=None):
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(path)
    for w, h in sizes_mm:
        c.setPageSize((w * MM, h * MM)); c.rect(0, 0, w * MM, h * MM); c.drawString(20, 20, "x"); c.showPage()
    c.save()
    if rotate:
        import pypdf
        r = pypdf.PdfReader(path); wtr = pypdf.PdfWriter()
        for i, p in enumerate(r.pages):
            if i in rotate: p.rotate(90)
            wtr.add_page(p)
        wtr.write(path)
    return pdfium.PdfDocument(path)


def test_crop_symmetric():
    d = _pdf([(216, 303), (303, 216), (200, 310), (210, 297)])
    s = cmyk.ManipSettings(crop=True, crop_size="A4", crop_scale=False)
    out, small = pdfmanip.crop_doc(d, s)
    sz = [tuple(round(v / MM, 1) for v in out.get_page_size(i)) for i in range(4)]
    assert sz[0] == (210.0, 297.0)                    # 3 mm je Seite weg
    assert sz[1] == (297.0, 210.0)                    # Querformat folgt dem Ziel quer
    assert sz[2] == (200.0, 297.0) and small == [3]   # zu schmal -> Breite bleibt, Hinweis
    assert sz[3] == (210.0, 297.0)
    l, b, r, t = out[0].get_cropbox()
    assert abs(l / MM - 3) < 0.05 and abs(b / MM - 3) < 0.05   # zentriert: links 3, unten 3


def test_crop_rotated_page():
    d = _pdf([(216, 303)], "/tmp/_crop_rot.pdf", rotate={0})       # /Rotate 90 -> sichtbar quer
    out, _ = pdfmanip.crop_doc(d, cmyk.ManipSettings(crop=True, crop_size="A4", crop_scale=False))
    w, h = (round(v / MM, 1) for v in out.get_page_size(0))
    assert (w, h) == (297.0, 210.0)


def test_describe():
    d = _pdf([(216, 303)])
    txt = pdfmanip.describe_crop(d, cmyk.ManipSettings(crop=True, crop_size="A4", crop_scale=False), 0)
    assert "216.0 × 303.0 mm → 210.0 × 297.0 mm" in txt and "3.0 mm" in txt


def test_fill_scale_and_crop():
    """Standard: skalieren bis das Ziel gefüllt ist, Überstand der anderen Kante beidseitig weg (A4 → A6 = 50 %)."""
    from reportlab.pdfgen import canvas
    c = canvas.Canvas("/tmp/_fill.pdf")
    c.setPageSize((210 * MM, 297 * MM)); c.setFillColorRGB(1, 0, 0)
    c.rect(0, 277 * MM, 20 * MM, 20 * MM, fill=1, stroke=0); c.showPage()          # rotes Quadrat oben links
    c.setPageSize((200 * MM, 600 * MM)); c.setFillColorRGB(0, 0, 1); c.rect(0, 0, 200 * MM, 100 * MM, fill=1, stroke=0)
    c.setFillColorRGB(0, 1, 0); c.rect(0, 250 * MM, 200 * MM, 100 * MM, fill=1, stroke=0); c.showPage()   # schmal
    c.save()
    d = pdfium.PdfDocument("/tmp/_fill.pdf")
    s = cmyk.ManipSettings(crop=True, crop_size="A6")
    assert "50.0 %" in pdfmanip.describe_crop(d, s, 0)
    assert "83.5 mm oben/unten" in pdfmanip.describe_crop(d, s, 1)
    out, small = pdfmanip.crop_doc(d, s)
    assert small == [] and [tuple(round(v / MM) for v in out.get_page_size(i)) for i in range(2)] == [(105, 148)] * 2
    a = out[0].render(scale=1).to_pil().convert("RGB")
    assert a.getpixel((5, 5))[0] > 200 and a.getpixel((5, 5))[1] < 60          # Quadrat oben links mitskaliert
    assert a.getpixel((40, 40)) == (255, 255, 255)                              # 10 mm * 50 % ≈ 14 px -> dahinter weiß
    b = out[1].render(scale=1).to_pil().convert("RGB")
    assert b.getpixel((b.width // 2, b.height // 2))[1] > 200                   # grüne Mitte des Plakats
    assert b.getpixel((b.width // 2, b.height - 3)) == (255, 255, 255)          # blauer Fuß ist abgeschnitten
    big, _ = pdfmanip.crop_doc(_pdf([(105, 148)], "/tmp/_small.pdf"), cmyk.ManipSettings(crop=True, crop_size="A4"))
    assert tuple(round(v / MM) for v in big.get_page_size(0)) == (210, 297)    # kleiner -> hochskaliert


def test_fill_with_inset():
    """Weißer Rand der Vorlage wird vorher abgeschnitten: 10 mm weiß um A4 -> danach erst auf A6 skaliert."""
    from reportlab.pdfgen import canvas
    c = canvas.Canvas("/tmp/_inset.pdf", pagesize=(210 * MM, 297 * MM))
    c.setFillColorRGB(0, 0, 1); c.rect(10 * MM, 10 * MM, 190 * MM, 277 * MM, fill=1, stroke=0); c.showPage(); c.save()
    d = pdfium.PdfDocument("/tmp/_inset.pdf")
    s = cmyk.ManipSettings(crop=True, crop_size="A6", crop_inset_mm=10)
    assert "190.0 × 277.0 mm" in pdfmanip.describe_crop(d, s, 0)
    out, _ = pdfmanip.crop_doc(d, s)
    im = out[0].render(scale=1).to_pil().convert("RGB")
    for xy in ((1, 1), (im.width - 2, im.height - 2), (1, im.height // 2), (im.width // 2, 1)):
        assert im.getpixel(xy)[2] > 200 and im.getpixel(xy)[0] < 60, (xy, im.getpixel(xy))   # bis zum Rand blau
    s2 = cmyk.ManipSettings(crop=True, crop_size="A4", crop_scale=False, crop_inset_mm=10)
    o2, _ = pdfmanip.crop_doc(d, s2)
    assert tuple(round(v / MM) for v in o2.get_page_size(0)) == (190, 277)                     # nur abschneiden


def test_color_args():
    s = cmyk.ManipSettings(cmyk=True, target="/p/psov3.icc", cmyk_mode="rgb_only", intent="perceptual")
    a = cmyk.color_args(s)
    assert "-sOutputICCProfile=/p/psov3.icc" in a and "-sDefaultCMYKProfile=/p/psov3.icc" in a and "-dRenderIntent=0" in a
    s.cmyk_mode, s.source = "all", "/p/fogra39.icc"
    assert "-sDefaultCMYKProfile=/p/fogra39.icc" in cmyk.color_args(s)
    assert "-sColorConversionStrategy=Gray" in cmyk.color_args(cmyk.ManipSettings(cmyk=True, cmyk_mode="gray"))


def test_softproof_and_tac():
    if not os.path.exists(FOGRA):
        print("  (kein FOGRA-Profil – übersprungen)"); return
    from PIL import Image
    img = Image.new("CMYK", (4, 1)); img.putdata([(0, 0, 0, 0), (255, 255, 255, 255), (255, 0, 0, 0), (200, 200, 200, 255)])
    rgb = cmyk.cmyk_to_screen(img, FOGRA)
    white, black, cyan, rich = rgb.getpixel((0, 0)), rgb.getpixel((1, 0)), rgb.getpixel((2, 0)), rgb.getpixel((3, 0))
    assert min(white) > 245                             # Papierweiß (relativ) = Weiß
    assert max(black) < 60                              # 400 % ≈ tiefes Schwarz
    assert cyan[2] > cyan[0] + 100                      # Cyan wirkt blau-grün
    paper = cmyk.cmyk_to_screen(img, FOGRA, paper_white=True).getpixel((0, 0))
    assert paper != (255, 255, 255)                     # absolut: Papierton sichtbar
    mx, pct, warn = cmyk.tac(img, 300)
    assert round(mx) == 400 and abs(pct - 50) < 0.1     # 2 von 4 Pixeln über 300 %
    assert warn.getpixel((1, 0)) == (255, 0, 64)
    assert cmyk.separation(img, 0).getpixel((2, 0))[0] == 0   # volles Cyan = schwarz im Auszug


def test_find_profiles():
    found = cmyk.find_profiles({})
    if os.path.exists(FOGRA):
        assert any("FOGRA39" in p.name or "FOGRA39" in p.path for p in found)


def test_crop_file_then_print_end_to_end():
    """Ablauf wie in der Oberfläche: beschneiden -> Datei im Zwischenspeicher -> öffnen -> normal drucken."""
    from reportlab.pdfgen import canvas
    from pdfdruck import config, layout, printers, printjob
    c = canvas.Canvas("/tmp/_rand.pdf", pagesize=(216 * MM, 303 * MM))
    c.setFillColorRGB(1, 0, 0); c.rect(0, 0, 216 * MM, 303 * MM, fill=1, stroke=0)
    c.setFillColorRGB(0.8, 0.9, 1); c.rect(3 * MM, 3 * MM, 210 * MM, 297 * MM, fill=1, stroke=0); c.showPage(); c.save()
    new, _ = pdfmanip.apply(pdfium.PdfDocument("/tmp/_rand.pdf"), cmyk.ManipSettings(crop=True, crop_size="A4", crop_scale=False))
    new.save("/tmp/_rand_cache.pdf"); new.close()
    doc = pdfium.PdfDocument("/tmp/_rand_cache.pdf")

    class S:
        cfg = config.BUILTIN; _c = {}
        def caps_for(s, n): return s._c.setdefault(n, printers.pdf_caps())
        def values_for(s, n): return s.caps_for(n).defaults()
        def color_for(s, n): return ("", "relative")
    printjob.submit_document(doc, "x", S(), printers.PDF_TARGET, [0], layout.LayoutSettings(mode="actual"),
                             values={"PageSize": "A4", "__out__": "/tmp/_rand_print.pdf"})
    im = pdfium.PdfDocument("/tmp/_rand_print.pdf")[0].render(scale=1).to_pil()
    for xy in ((2, 2), (im.width // 2, 2), (2, im.height // 2), (im.width - 3, im.height - 3)):
        r, g, b = im.getpixel(xy)[:3]
        assert not (r > 200 and g < 80 and b < 80), f"roter Rand bei {xy}: {(r, g, b)}"


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("ok", k)
