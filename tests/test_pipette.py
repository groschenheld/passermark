# SPDX-License-Identifier: GPL-3.0-or-later
"""Farbpipette: definierte Farbe (CMYK, RGB, Grau, Sonderfarbe mit Tonwert, Kontur, Bildpixel, Text), Papier,
gedrehte Seite. Der Farbauftrag kommt sonst von Ghostscript – hier ersetzt durch pdfium + LittleCMS mit demselben
Profil (die Ghostscript-Aufrufe sind dieselben wie beim Softproof und dort getestet)."""
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pdfdruck import cmyk, colorcheck, pipette  # noqa: E402

TMP = tempfile.mkdtemp(prefix="pm-pipette-")


def _fake_render(gs, src, page, dpi, device, extra, out):
    import pypdfium2 as pdfium
    from PIL import ImageCms
    icc = next(a.split("=", 1)[1] for a in extra if a.startswith("-sOutputICCProfile="))
    d = pdfium.PdfDocument(src)
    im = d[page].render(scale=dpi / 72).to_pil().convert("RGB")
    d.close()
    tf = ImageCms.buildTransform(ImageCms.createProfile("sRGB"), ImageCms.getOpenProfile(icc), "RGB", "CMYK")
    ImageCms.applyTransform(im, tf).save(out)


def _cmyk_profile():
    from PIL import ImageCms
    for p in ("/usr/share/texlive/texmf-dist/tex/generic/colorprofiles/FOGRA39L_coated.icc",
              "/usr/share/color/icc/ghostscript/default_cmyk.icc"):
        if os.path.isfile(p):
            return p
    return None


def _page():
    from PIL import Image
    from reportlab.lib.colors import CMYKColor, CMYKColorSep
    from reportlab.pdfgen import canvas
    cm, rgb = os.path.join(TMP, "cm.jpg"), os.path.join(TMP, "rgb.png")
    Image.new("CMYK", (300, 200), (0, 255, 128, 0)).save(cm)
    Image.new("RGB", (100, 100), (0, 128, 255)).save(rgb)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(595, 842))
    c.setFillColor(CMYKColor(0, .4, 1, 0)); c.rect(50, 700, 100, 50, fill=1, stroke=0)
    c.setFillColorRGB(1, 0, 0); c.rect(200, 700, 100, 50, fill=1, stroke=0)
    c.setFillColor(CMYKColorSep(0, .2, 1, 0, spotName="HKS 5 K", density=0.6)); c.rect(350, 700, 100, 50, fill=1, stroke=0)
    c.setFillGray(0.3); c.rect(50, 600, 100, 50, fill=1, stroke=0)
    c.setStrokeColor(CMYKColor(1, 0, 0, 0)); c.setLineWidth(6); c.rect(200, 600, 100, 50, fill=0, stroke=1)
    c.drawImage(cm, 50, 450, 100, 100); c.drawImage(rgb, 200, 450, 100, 100)
    c.setFillColor(CMYKColor(0, 0, 0, 1)); c.setFont("Helvetica-Bold", 40); c.drawString(50, 350, "SCHWARZ")
    c.save()
    return buf.getvalue()


def test_defined_colors():
    data = _page()
    want = {(100, 725): ("path", "CMYK", [0, .4, 1, 0]), (250, 725): ("path", "RGB", [1, 0, 0]),
            (400, 725): ("path", "Separation", [.6]), (100, 625): ("path", "Gray", [.3]),
            (201, 625): ("path", "CMYK", [1, 0, 0, 0]), (100, 500): ("image", "CMYK", [0, 1, 128 / 255, 0]),
            (250, 500): ("image", "RGB", [0, 128 / 255, 1]), (62, 365): ("text", "CMYK", [0, 0, 0, 1])}
    for (x, y), (kind, space, vals) in want.items():
        s = pipette.sample(data, 0, x, y)
        assert s.kind == kind and s.space == space, (x, y, s)
        assert all(abs(a - b) < 0.01 for a, b in zip(s.values, vals)), (x, y, s.values)
    s = pipette.sample(data, 0, 400, 725)
    assert s.spot == "HKS 5 K" and "60 %" in pipette.format_values(s)
    s = pipette.sample(data, 0, 201, 625)
    assert s.paint == "stroke"
    s = pipette.sample(data, 0, 250, 625)                       # innerhalb der Kontur: Papier
    assert s.kind == "" and s.screen == (255, 255, 255)
    s = pipette.sample(data, 0, 100, 500)
    assert "300 × 200 px" in s.detail and "216 ppi" in s.detail, s.detail
    assert pipette.sample(data, 0, 100, 725).as_cmyk() == [0, .4, 1, 0]
    assert pipette.sample(data, 0, 250, 725).as_rgb() == [1, 0, 0]


def test_ink_and_rotation():
    import pikepdf
    icc = _cmyk_profile()
    if not icc:
        print("übersprungen: kein CMYK-Profil")
        return
    old = cmyk._render, cmyk.ghostscript
    cmyk._render, cmyk.ghostscript = _fake_render, lambda: "gs"
    try:
        data = _page()
        t = colorcheck.target_from_file(icc)
        s = pipette.sample(data, 0, 250, 725, t)                 # RGB-Rot -> wieviel CMYK im Druck
        assert s.ink and s.ink[1] > 80 and s.ink[2] > 80 and s.ink[0] < 10 and s.ink_total > 150, s.ink
        assert s.as_cmyk() == [round(v) / 100 for v in s.ink]
        assert pipette.sample(data, 0, 500, 100, t).ink_total < 1  # Papier
        for rot in (90, 180, 270):
            p = pikepdf.open(io.BytesIO(data))
            p.pages[0].Rotate = rot
            o = io.BytesIO()
            p.save(o)
            r = pipette.sample(o.getvalue(), 0, 250, 725, t)
            assert r.space == "RGB" and r.screen == (255, 0, 0) and r.ink[1] > 80, (rot, r)
    finally:
        cmyk._render, cmyk.ghostscript = old


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
