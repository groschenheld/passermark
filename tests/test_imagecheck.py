# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Bilder & Farben in der Prüfung: Farbraum mit ICC-Profilname, effektive Auflösung je Platzierung
    (auch im Formular, auch dasselbe Bild mehrfach), Empfehlung für die maximale Größe."""
import io
import os
import sys
os.environ.setdefault("PASSERMARK_LANG", "de")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pdfdruck import imagecheck, preflight

MM = 72 / 25.4


def _srgb_icc() -> bytes:
    from PIL import ImageCms
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def _pdf() -> bytes:
    """Seite 1: RGB-Bild (600×600 px, ICC) mit 50,8 mm = 300 dpi und dasselbe Bild über ein Formular
        auf 203,2 mm = 75 dpi; CMYK-Bild; Text in einer Sonderfarbe; RGB-Vektor."""
    import pikepdf
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(842, 842))
    page = pdf.pages[0]
    icc = pikepdf.Stream(pdf, _srgb_icc(), N=3)
    rgb = pikepdf.Stream(pdf, bytes([200, 100, 50]) * 600 * 600, Type=pikepdf.Name.XObject,
                         Subtype=pikepdf.Name.Image, Width=600, Height=600,
                         ColorSpace=pikepdf.Array([pikepdf.Name.ICCBased, icc]), BitsPerComponent=8)
    cmyk = pikepdf.Stream(pdf, bytes([0, 50, 100, 0]) * 100 * 100, Type=pikepdf.Name.XObject,
                          Subtype=pikepdf.Name.Image, Width=100, Height=100,
                          ColorSpace=pikepdf.Array([pikepdf.Name.DeviceCMYK]), BitsPerComponent=8)
    side = 600 / 300 * 72                              # 144 pt = 50,8 mm
    form = pikepdf.Stream(pdf, f"q {side} 0 0 {side} 0 0 cm /Im1 Do Q".encode(), Type=pikepdf.Name.XObject,
                          Subtype=pikepdf.Name.Form, BBox=[0, 0, side, side], Matrix=[4, 0, 0, 4, 200, 200],
                          Resources=pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im1=rgb)))
    sep = pikepdf.Array([pikepdf.Name.Separation, pikepdf.Name("/HKS 43 K"), pikepdf.Name.DeviceCMYK,
                         pikepdf.Dictionary(FunctionType=2, Domain=[0, 1], C0=[0, 0, 0, 0], C1=[1, 0.6, 0, 0], N=1)])
    page.obj.Resources = pikepdf.Dictionary(
        XObject=pikepdf.Dictionary(Im1=rgb, Im2=cmyk, Fm=form), ColorSpace=pikepdf.Dictionary(CS0=sep),
        Font=pikepdf.Dictionary(F1=pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1,
                                                       BaseFont=pikepdf.Name.Helvetica)))
    page.obj.Contents = pikepdf.Stream(pdf, (
        f"q {side} 0 0 {side} 20 20 cm /Im1 Do Q\n"
        "/Fm Do\n"
        "q 72 0 0 72 700 20 cm /Im2 Do Q\n"
        "/CS0 cs 1 scn BT /F1 12 Tf 20 800 Td (Sonderfarbe) Tj ET\n"
        "1 0 0 rg 700 700 50 50 re f").encode())
    buf = io.BytesIO()
    pdf.save(buf)
    return buf.getvalue()


def test_icc_name():
    assert imagecheck.icc_name(_srgb_icc())                      # nicht leer
    assert imagecheck.icc_name(b"kaputt") == ""


def test_uses_dpi_and_spaces():
    import pikepdf
    with pikepdf.open(io.BytesIO(_pdf())) as pdf:
        cr = imagecheck.analyze(pdf)
    rgb = sorted((u for u in cr.images if u.space == "RGB"), key=lambda u: -u.dpi)
    assert len(rgb) == 2, cr.images
    assert abs(rgb[0].dpi - 300) < 1 and abs(rgb[0].placed_mm[0] - 50.8) < 0.2
    assert abs(rgb[1].dpi - 75) < 1 and abs(rgb[1].placed_mm[0] - 203.2) < 0.5, "Formular-Matrix ×4"
    assert rgb[0].profile and rgb[0].rating == "good" and rgb[1].rating == "low"
    mx = rgb[1].max_mm(300)
    assert abs(mx[0] - 50.8) < 0.2, "max. bei 300 dpi = Pixel / 300 × 25,4"
    cm = [u for u in cr.images if u.space == "CMYK"]
    assert len(cm) == 1 and abs(cm[0].dpi - 100) < 1
    assert {"RGB", "CMYK"} <= cr.page_colors[1] and cr.spots[1] == {"HKS 43 K"}
    lim = imagecheck.page_limits(cr)[1]
    assert abs(lim[0] - 75) < 1 and abs(lim[1] - 0.25) < 0.01 and abs(lim[2] - 0.5) < 0.01


def test_issues_and_report():
    rep = preflight.analyze(_pdf(), deep_layers=False, pdfium_parts=False)
    img = [i for i in rep.issues if i.category == "image"]
    low = [i for i in img if i.severity == "warning"]
    assert len(low) == 1 and "75 dpi" in low[0].message and "Empfehlung" in low[0].message, img
    assert any("HKS 43 K" in i.message for i in img)
    assert any("RGB" in i.message and i.severity == "info" for i in img)
    txt = preflight.report_text(rep)
    assert "Bilder (" in txt and "75 dpi" in txt and "300 dpi" in txt


def test_good_file_quiet():
    """Ein Bild in CMYK mit 300 dpi und keine RGB-Inhalte: keine Bild-Befunde."""
    import pikepdf
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(144, 144))
    img = pikepdf.Stream(pdf, bytes([0, 0, 0, 255]) * 600 * 600, Type=pikepdf.Name.XObject,
                         Subtype=pikepdf.Name.Image, Width=600, Height=600, ColorSpace=pikepdf.Name.DeviceCMYK,
                         BitsPerComponent=8)
    pdf.pages[0].obj.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im=img))
    pdf.pages[0].obj.Contents = pikepdf.Stream(pdf, b"q 144 0 0 144 0 0 cm /Im Do Q")
    buf = io.BytesIO()
    pdf.save(buf)
    rep = preflight.analyze(buf.getvalue(), deep_layers=False, pdfium_parts=False)
    assert not [i for i in rep.issues if i.category == "image"], rep.issues


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
