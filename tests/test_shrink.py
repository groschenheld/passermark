# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Dateigröße: Aufschlüsselung, verlustfreie Maßnahmen (Druckbild pixelgleich), jede einzeln schaltbar,
    optionales Herunterrechnen, Befund in der Prüfung, Auftrag „shrink“."""
import io
import os
import sys
import tempfile
import zlib
os.environ.setdefault("PASSERMARK_LANG", "de")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pdfdruck import core, preflight, shrink

MM = 72 / 25.4


def _photo(w, h, c):
    import numpy as np
    y, x = np.mgrid[0:h, 0:w]
    ch = [np.sin(x / 37.0 + k) * 60 + np.cos(y / 23.0 * (k + 1)) * 60 + 128 + (x * y % 7) for k in range(c)]
    return np.clip(np.stack(ch, 2), 0, 255).astype(np.uint8)


def _pdf() -> bytes:
    """16-Bit-RGB unkomprimiert (~760 dpi), Graubild doppelt gespeichert, ZIP+JPEG-CMYK (~1000 dpi),
        RGB mit Soft-Maske, Illustrator-Bearbeitungsdaten, Vorschaubild."""
    import pikepdf
    from PIL import Image
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(595, 842))
    pg = pdf.pages[0]
    X, I = pikepdf.Name.XObject, pikepdf.Name.Image

    def img(data, w, h, cs, bpc=8, **kw):
        return pikepdf.Stream(pdf, data, Type=X, Subtype=I, Width=w, Height=h, ColorSpace=cs, BitsPerComponent=bpc, **kw)
    a = _photo(600, 600, 3).astype(">u2") * 257
    i16 = img(a.tobytes(), 600, 600, pikepdf.Name.DeviceRGB, 16)
    g = zlib.compress(_photo(400, 400, 1)[:, :, 0].tobytes())
    d1 = img(g, 400, 400, pikepdf.Name.DeviceGray, Filter=pikepdf.Name.FlateDecode)
    d2 = img(g, 400, 400, pikepdf.Name.DeviceGray, Filter=pikepdf.Name.FlateDecode)
    b = io.BytesIO()
    Image.fromarray(_photo(900, 900, 4), "CMYK").save(b, "JPEG", quality=95)
    fj = img(zlib.compress(b.getvalue()), 900, 900, pikepdf.Name.DeviceCMYK,
             Filter=pikepdf.Array([pikepdf.Name.FlateDecode, pikepdf.Name.DCTDecode]), Decode=[1, 0] * 4)
    m = (_photo(500, 500, 1)[:, :, 0] > 100).astype("uint8") * 255
    sm = img(zlib.compress(m.tobytes()), 500, 500, pikepdf.Name.DeviceGray, Filter=pikepdf.Name.FlateDecode)
    rs = img(zlib.compress(_photo(500, 500, 3).tobytes(), 1), 500, 500, pikepdf.Name.DeviceRGB,
             Filter=pikepdf.Name.FlateDecode, SMask=sm)
    pg.obj.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(A=i16, B=d1, C=d2, D=fj, E=rs))
    pg.obj.Contents = pikepdf.Stream(pdf, (
        f"q {20 * MM} 0 0 {20 * MM} 30 600 cm /A Do Q q 50 0 0 50 300 650 cm /B Do Q "
        f"q 50 0 0 50 420 650 cm /C Do Q q {23 * MM} 0 0 {23 * MM} 30 300 cm /D Do Q "
        f"q {17 * MM} 0 0 {17 * MM} 300 300 cm /E Do Q").encode())
    pg.obj.PieceInfo = pikepdf.Dictionary(Illustrator=pikepdf.Dictionary(Private=pikepdf.Dictionary(
        AIPrivateData1=pikepdf.Stream(pdf, os.urandom(400_000)))))
    pg.obj.Thumb = pikepdf.Stream(pdf, os.urandom(50_000), Width=10, Height=14,
                                  ColorSpace=pikepdf.Name.DeviceRGB, BitsPerComponent=8)
    out = io.BytesIO()
    pdf.save(out, compress_streams=False)
    return out.getvalue()


def _render(data):
    import numpy as np
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(data)
    try:
        return np.asarray(doc[0].render(scale=100 / 72).to_pil().convert("RGB")).astype(int)
    finally:
        doc.close()


def test_analyze_breakdown():
    rep = shrink.analyze(_pdf())
    assert rep.parts["images"] > rep.parts["private"] > 300_000
    assert rep.private_bytes >= 400_000 and rep.thumb_bytes >= 50_000
    assert rep.duplicates == 1
    a = [i for i in rep.images if i.bpc == 16]
    assert len(a) == 1 and abs(a[0].dpi - 762) < 2, rep.images
    assert [i for i in rep.images if i.is_smask], "Soft-Maske erkannt"
    assert all(not i.is_smask for i in shrink.candidates(rep))
    txt = "\n".join(shrink.summary_lines(rep))
    assert "Bilder" in txt and "Bearbeitungsdaten" in txt and "doppelt" in txt


def test_lossless_is_pixel_identical():
    import numpy as np
    data = _pdf()
    out, notes = shrink.shrink(data, shrink.ShrinkOptions())
    assert len(out) < len(data) * 0.8, (len(data), len(out))
    assert np.abs(_render(out) - _render(data)).max() == 0
    rep = shrink.analyze(out)
    assert rep.private_bytes == 0 and rep.thumb_bytes == 0 and rep.duplicates == 0
    assert any("verlustfrei" in n for n in notes) and any("Bearbeitungsdaten" in n for n in notes)


def test_each_measure_switchable():
    """Alles aus: nur neu geschrieben, Bearbeitungsdaten/Vorschau/Duplikate bleiben."""
    off = shrink.ShrinkOptions(rewrite=False, unreferenced=False, dedupe=False, private=False, thumbs=False,
                               pack=False)
    out, _ = shrink.shrink(_pdf(), off)
    rep = shrink.analyze(out)
    assert rep.private_bytes >= 400_000 and rep.thumb_bytes >= 50_000 and rep.duplicates == 1
    assert [i for i in rep.images if i.bpc == 16]
    only_thumbs = shrink.ShrinkOptions(**{**off.__dict__, "thumbs": True})
    rep = shrink.analyze(shrink.shrink(_pdf(), only_thumbs)[0])
    assert rep.thumb_bytes == 0 and rep.private_bytes >= 400_000


def test_bits16_and_downsample():
    import numpy as np
    data = _pdf()
    out, notes = shrink.shrink(data, shrink.ShrinkOptions(bits16=True))
    assert not [i for i in shrink.analyze(out).images if i.bpc == 16]
    assert np.abs(_render(out) - _render(data)).max() <= 1
    out, notes = shrink.shrink(data, shrink.ShrinkOptions(downsample=True, target_dpi=300))
    rep = shrink.analyze(out)
    for i in rep.images:
        if i.dpi and not i.is_smask:
            assert i.dpi < 300 * 1.5 + 1, i
    sm = [i for i in rep.images if i.is_smask]
    assert sm and sm[0].w < 500, "Soft-Maske mit heruntergerechnet"
    cmyk = [i for i in rep.images if i.comps == 4]
    assert cmyk and cmyk[0].codec == "JPEG" and cmyk[0].w < 900
    assert np.abs(_render(out) - _render(data)).mean() < 1.0, "Farben bleiben (CMYK-JPEG nicht invertiert)"
    assert any("300 dpi" in n for n in notes)


def test_preflight_finding_and_job():
    import pikepdf
    rep = preflight.analyze(_pdf(), deep_layers=False, pdfium_parts=False)
    assert rep.size is not None and rep.size.duplicates == 1
    assert any(i.category == "size" and "16 Bit" in i.message for i in rep.issues), rep.issues
    assert "Dateigröße:" in preflight.report_text(rep)
    d = tempfile.mkdtemp(prefix="pm-shrink-")
    src, dst = os.path.join(d, "a.pdf"), os.path.join(d, "b.pdf")
    with open(src, "wb") as f:
        f.write(_pdf())
    res = core.run_job("shrink", src, dst, {"downsample": True, "target_dpi": 150, "private": False})
    assert res.info["size_out"] < res.info["size_in"] / 3
    with pikepdf.open(dst) as pdf:
        assert "/PieceInfo" in pdf.pages[0].obj, "Häkchen aus -> Bearbeitungsdaten bleiben"


def test_same_profile_per_page_deduped():
    """Dasselbe ICC-Profil je Seite neu eingebettet, [/ICCBased …] direkt im Farbraum (Fall schritt2-test.pdf)."""
    import numpy as np
    import pikepdf
    from PIL import ImageCms
    prof = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes() + os.urandom(600_000)
    pdf = pikepdf.new()
    for k in range(6):
        pdf.add_blank_page(page_size=(200, 200))
        icc = pikepdf.Stream(pdf, prof, N=3)
        im = pikepdf.Stream(pdf, bytes([40 * k, 90, 160]) * 64 * 64, Type=pikepdf.Name.XObject,
                            Subtype=pikepdf.Name.Image, Width=64, Height=64, BitsPerComponent=8,
                            ColorSpace=pikepdf.Array([pikepdf.Name.ICCBased, icc]))
        pg = pdf.pages[k]
        pg.obj.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im=im))
        pg.obj.Contents = pikepdf.Stream(pdf, b"q 200 0 0 200 0 0 cm /Im Do Q")
    buf = io.BytesIO()
    pdf.save(buf)
    data = buf.getvalue()
    rep = shrink.analyze(data)
    assert rep.duplicates == 5 and rep.parts["icc"] > 3_000_000, rep
    assert any("doppelt" in m for _s, m in shrink.issues(rep))
    out, _ = shrink.shrink(data, shrink.ShrinkOptions())
    assert len(out) < len(data) / 3, (len(data), len(out))
    with pikepdf.open(io.BytesIO(out)) as p2:
        assert len({pg.Resources.XObject.Im.ColorSpace[1].objgen for pg in p2.pages}) == 1
    a, b = _render_all(data), _render_all(out)
    assert all(np.array_equal(x, y) for x, y in zip(a, b))


def _render_all(data):
    import numpy as np
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(data)
    try:
        return [np.asarray(doc[i].render(scale=0.5).to_pil()) for i in range(len(doc))]
    finally:
        doc.close()


def test_zip_photos_to_jpeg():
    """Fotos als ZIP (RGB, CMYK, Grau) -> JPEG mit treuen Farben; Grafik mit wenigen Farben bleibt ZIP;
        Häkchen aus -> nichts wird JPEG."""
    import numpy as np
    import pikepdf
    rng = np.random.default_rng(1)

    def photo(w, h, c):
        return np.clip(_photo(w, h, c).astype(int) + rng.normal(0, 6, (h, w, c)), 0, 255).astype(np.uint8)
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(595, 842))

    def img(a, cs):
        return pikepdf.Stream(pdf, zlib.compress(a.tobytes()), Type=pikepdf.Name.XObject, Subtype=pikepdf.Name.Image,
                              Width=a.shape[1], Height=a.shape[0], ColorSpace=cs, BitsPerComponent=8,
                              Filter=pikepdf.Name.FlateDecode)
    g = np.zeros((600, 600, 3), np.uint8)
    g[:300], g[300:] = [200, 30, 30], [20, 20, 200]
    pg = pdf.pages[0]
    pg.obj.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(
        A=img(photo(900, 700, 3), pikepdf.Name.DeviceRGB), B=img(photo(800, 800, 4), pikepdf.Name.DeviceCMYK),
        C=img(photo(600, 600, 1), pikepdf.Name.DeviceGray), D=img(g, pikepdf.Name.DeviceRGB)))
    pg.obj.Contents = pikepdf.Stream(pdf, b"q 250 0 0 200 20 600 cm /A Do Q q 250 0 0 250 300 550 cm /B Do Q "
                                          b"q 200 0 0 200 20 300 cm /C Do Q q 200 0 0 200 300 300 cm /D Do Q")
    buf = io.BytesIO()
    pdf.save(buf)
    data = buf.getvalue()
    assert len(shrink.zip_photos(shrink.analyze(data))) == 3
    out, notes = shrink.shrink(data, shrink.ShrinkOptions(photos_jpeg=True))
    assert len(out) < len(data) / 2 and any("JPEG" in n for n in notes), notes
    with pikepdf.open(io.BytesIO(out)) as p2:
        xo = p2.pages[0].Resources.XObject
        assert [str(xo[k].Filter) for k in ("/A", "/B", "/C")] == ["/DCTDecode"] * 3
        assert str(xo["/D"].Filter) == "/FlateDecode", "Grafik bleibt verlustfrei"
    assert np.abs(_render(out) - _render(data)).mean() < 1.0, "Farben (auch CMYK) bleiben"
    off, _ = shrink.shrink(data, shrink.ShrinkOptions())
    with pikepdf.open(io.BytesIO(off)) as p3:
        assert all(str(x.Filter) != "/DCTDecode" for _k, x in p3.pages[0].Resources.XObject.items())


def test_too_big_warning():
    rep = shrink.SizeReport(size=60 * shrink.MB, pages=1, area_m2=shrink.A4_M2, parts={"images": 55 * shrink.MB})
    iss = shrink.issues(rep)
    assert iss and iss[0][0] == "warning" and "60 MB" in iss[0][1] and "Bilder" in iss[0][1]
    rep.area_m2 = shrink.A4_M2 * 8                      # A0: 7,5 MB je A4 – unauffällig
    assert not [i for i in shrink.issues(rep) if i[0] == "warning"]


def test_ascii85_wrapped_jpeg():
    """JPEG hinter ASCII85 (ReportLab): wird erkannt, heruntergerechnet und ausgepackt."""
    import base64, io as _io
    import pikepdf
    from PIL import Image
    buf = _io.BytesIO()
    Image.new("RGB", (2000, 1500), (120, 60, 30)).save(buf, "JPEG", quality=90)
    jpg = buf.getvalue()
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(144, 108))            # 2 × 1,5 Zoll -> 1000 dpi
    img = pikepdf.Stream(pdf, base64.a85encode(jpg) + b"~>")
    img.Type, img.Subtype = pikepdf.Name.XObject, pikepdf.Name.Image
    img.Width, img.Height, img.BitsPerComponent = 2000, 1500, 8
    img.ColorSpace = pikepdf.Name.DeviceRGB
    img.Filter = pikepdf.Array([pikepdf.Name.ASCII85Decode, pikepdf.Name.DCTDecode])
    pg = pdf.pages[0]
    pg.obj.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im=img))
    pg.obj.Contents = pikepdf.Stream(pdf, b"q 144 0 0 108 0 0 cm /Im Do Q")
    out = _io.BytesIO()
    pdf.save(out)
    data = out.getvalue()
    assert shrink._undo_filters(base64.a85encode(b"abc") + b"~>", ["/ASCII85Decode"]) == b"abc"
    small, _ = shrink.shrink(data, shrink.ShrinkOptions(downsample=True, target_dpi=300))
    im = shrink.analyze(small).images[0]
    assert im.codec == "JPEG" and abs(im.w - 600) <= 1 and len(small) < len(data) / 3
    packed, notes = shrink.shrink(data, shrink.ShrinkOptions())
    assert shrink.analyze(packed).images[0].codec == "JPEG" and len(packed) < len(data)


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
