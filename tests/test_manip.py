# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
import os
import sys

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
        c.setPageSize((w * MM, h * MM))
        c.rect(0, 0, w * MM, h * MM)
        c.drawString(20, 20, "x")
        c.showPage()
    c.save()
    if rotate:
        import pikepdf

        with pikepdf.open(path, allow_overwriting_input=True) as pdf:
            for i, p in enumerate(pdf.pages):
                if i in rotate:
                    p.Rotate = (int(p.get("/Rotate", 0)) + 90) % 360
            pdf.save(path)
    return pdfium.PdfDocument(path)


def test_crop_symmetric():
    d = _pdf([(216, 303), (303, 216), (200, 310), (210, 297)])
    s = cmyk.ManipSettings(crop=True, crop_size="A4", crop_scale=False)
    out, small = pdfmanip.crop_doc(d, s)
    sz = [tuple(round(v / MM, 1) for v in out.get_page_size(i)) for i in range(4)]
    assert sz[0] == (210.0, 297.0)  # 3 mm off per side
    assert sz[1] == (297.0, 210.0)  # landscape follows the target in landscape
    assert sz[2] == (200.0, 297.0) and small == [3]  # too narrow -> the width stays, note
    assert sz[3] == (210.0, 297.0)
    left, b, r, t = out[0].get_cropbox()
    assert abs(left / MM - 3) < 0.05 and abs(b / MM - 3) < 0.05  # centred: left 3, bottom 3


def test_crop_rotated_page():
    d = _pdf([(216, 303)], "/tmp/_crop_rot.pdf", rotate={0})  # /Rotate 90 -> visibly landscape
    out, _ = pdfmanip.crop_doc(d, cmyk.ManipSettings(crop=True, crop_size="A4", crop_scale=False))
    w, h = (round(v / MM, 1) for v in out.get_page_size(0))
    assert (w, h) == (297.0, 210.0)


def test_describe():
    d = _pdf([(216, 303)])
    txt = pdfmanip.describe_crop(d, cmyk.ManipSettings(crop=True, crop_size="A4", crop_scale=False), 0)
    assert "216.0 × 303.0 mm → 210.0 × 297.0 mm" in txt and "3.0 mm" in txt


def test_fill_scale_and_crop():
    """Default: scale until the target is filled, overhang of the other edge trimmed on both sides (A4 → A6 = 50 %)."""
    from reportlab.pdfgen import canvas

    c = canvas.Canvas("/tmp/_fill.pdf")
    c.setPageSize((210 * MM, 297 * MM))
    c.setFillColorRGB(1, 0, 0)
    c.rect(0, 277 * MM, 20 * MM, 20 * MM, fill=1, stroke=0)
    c.showPage()  # red square at the top left
    c.setPageSize((200 * MM, 600 * MM))
    c.setFillColorRGB(0, 0, 1)
    c.rect(0, 0, 200 * MM, 100 * MM, fill=1, stroke=0)
    c.setFillColorRGB(0, 1, 0)
    c.rect(0, 250 * MM, 200 * MM, 100 * MM, fill=1, stroke=0)
    c.showPage()  # narrow
    c.save()
    d = pdfium.PdfDocument("/tmp/_fill.pdf")
    s = cmyk.ManipSettings(crop=True, crop_size="A6")
    assert "50.0 %" in pdfmanip.describe_crop(d, s, 0)
    assert "83.5 mm oben/unten" in pdfmanip.describe_crop(d, s, 1)
    out, small = pdfmanip.crop_doc(d, s)
    assert small == [] and [tuple(round(v / MM) for v in out.get_page_size(i)) for i in range(2)] == [(105, 148)] * 2
    a = out[0].render(scale=1).to_pil().convert("RGB")
    assert a.getpixel((5, 5))[0] > 200 and a.getpixel((5, 5))[1] < 60  # square at the top left scaled along
    assert a.getpixel((40, 40)) == (255, 255, 255)  # 10 mm * 50 % ≈ 14 px -> white behind
    b = out[1].render(scale=1).to_pil().convert("RGB")
    assert b.getpixel((b.width // 2, b.height // 2))[1] > 200  # green centre of the poster
    assert b.getpixel((b.width // 2, b.height - 3)) == (255, 255, 255)  # blue foot is cut off
    big, _ = pdfmanip.crop_doc(_pdf([(105, 148)], "/tmp/_small.pdf"), cmyk.ManipSettings(crop=True, crop_size="A4"))
    assert tuple(round(v / MM) for v in big.get_page_size(0)) == (210, 297)  # smaller -> scaled up


def test_fill_with_inset():
    """The template's white border is trimmed first: 10 mm of white around A4 -> only then scaled to A6."""
    from reportlab.pdfgen import canvas

    c = canvas.Canvas("/tmp/_inset.pdf", pagesize=(210 * MM, 297 * MM))
    c.setFillColorRGB(0, 0, 1)
    c.rect(10 * MM, 10 * MM, 190 * MM, 277 * MM, fill=1, stroke=0)
    c.showPage()
    c.save()
    d = pdfium.PdfDocument("/tmp/_inset.pdf")
    s = cmyk.ManipSettings(crop=True, crop_size="A6", crop_inset_mm=10)
    assert "190.0 × 277.0 mm" in pdfmanip.describe_crop(d, s, 0)
    out, _ = pdfmanip.crop_doc(d, s)
    im = out[0].render(scale=1).to_pil().convert("RGB")
    for xy in ((1, 1), (im.width - 2, im.height - 2), (1, im.height // 2), (im.width // 2, 1)):
        assert im.getpixel(xy)[2] > 200 and im.getpixel(xy)[0] < 60, (xy, im.getpixel(xy))  # blue up to the edge
    s2 = cmyk.ManipSettings(crop=True, crop_size="A4", crop_scale=False, crop_inset_mm=10)
    o2, _ = pdfmanip.crop_doc(d, s2)
    assert tuple(round(v / MM) for v in o2.get_page_size(0)) == (190, 277)  # only cut off


def test_color_args():
    s = cmyk.ManipSettings(cmyk=True, target="/p/psov3.icc", cmyk_mode="rgb_only", intent="perceptual")
    a = cmyk.color_args(s)
    assert (
        "-sOutputICCProfile=/p/psov3.icc" in a and "-sDefaultCMYKProfile=/p/psov3.icc" in a and "-dRenderIntent=0" in a
    )
    s.cmyk_mode, s.source = "all", "/p/fogra39.icc"
    assert "-sDefaultCMYKProfile=/p/fogra39.icc" in cmyk.color_args(s)
    assert "-sColorConversionStrategy=Gray" in cmyk.color_args(cmyk.ManipSettings(cmyk=True, cmyk_mode="gray"))


def test_softproof_and_tac():
    if not os.path.exists(FOGRA):
        print("  (kein FOGRA-Profil – übersprungen)")
        return
    from PIL import Image

    img = Image.new("CMYK", (4, 1))
    img.putdata([(0, 0, 0, 0), (255, 255, 255, 255), (255, 0, 0, 0), (200, 200, 200, 255)])
    rgb = cmyk.cmyk_to_screen(img, FOGRA)
    white, black, cyan = rgb.getpixel((0, 0)), rgb.getpixel((1, 0)), rgb.getpixel((2, 0))
    assert min(white) > 245  # paper white (relative) = white
    assert max(black) < 60  # 400 % ≈ deep black
    assert cyan[2] > cyan[0] + 100  # cyan appears blue-green
    paper = cmyk.cmyk_to_screen(img, FOGRA, paper_white=True).getpixel((0, 0))
    assert paper != (255, 255, 255)  # absolute: paper tone visible
    mx, pct, warn = cmyk.tac(img, 300)
    assert round(mx) == 400 and abs(pct - 50) < 0.1  # 2 of 4 pixels above 300 %
    assert warn.getpixel((1, 0)) == (255, 0, 64)
    assert cmyk.separation(img, 0).getpixel((2, 0))[0] == 0  # full cyan = black in the separation


def test_find_profiles():
    found = cmyk.find_profiles({})
    if os.path.exists(FOGRA):
        assert any("FOGRA39" in p.name or "FOGRA39" in p.path for p in found)


def test_crop_file_then_print_end_to_end():
    """Flow as in the UI: crop -> file in the clipboard -> open -> print normally."""
    from reportlab.pdfgen import canvas

    from pdfdruck import config, layout, printers, printjob

    c = canvas.Canvas("/tmp/_rand.pdf", pagesize=(216 * MM, 303 * MM))
    c.setFillColorRGB(1, 0, 0)
    c.rect(0, 0, 216 * MM, 303 * MM, fill=1, stroke=0)
    c.setFillColorRGB(0.8, 0.9, 1)
    c.rect(3 * MM, 3 * MM, 210 * MM, 297 * MM, fill=1, stroke=0)
    c.showPage()
    c.save()
    new, _ = pdfmanip.apply(
        pdfium.PdfDocument("/tmp/_rand.pdf"), cmyk.ManipSettings(crop=True, crop_size="A4", crop_scale=False)
    )
    new.save("/tmp/_rand_cache.pdf")
    new.close()
    doc = pdfium.PdfDocument("/tmp/_rand_cache.pdf")

    class S:
        cfg = config.BUILTIN
        _c = {}

        def caps_for(s, n):
            return s._c.setdefault(n, printers.pdf_caps())

        def values_for(s, n):
            return s.caps_for(n).defaults()

        def color_for(s, n):
            return ("", "relative")

    printjob.submit_document(
        doc,
        "x",
        S(),
        printers.PDF_TARGET,
        [0],
        layout.LayoutSettings(mode="actual"),
        values={"PageSize": "A4", "__out__": "/tmp/_rand_print.pdf"},
    )
    im = pdfium.PdfDocument("/tmp/_rand_print.pdf")[0].render(scale=1).to_pil()
    for xy in ((2, 2), (im.width // 2, 2), (2, im.height // 2), (im.width - 3, im.height - 3)):
        r, g, b = im.getpixel(xy)[:3]
        assert not (r > 200 and g < 80 and b < 80), f"roter Rand bei {xy}: {(r, g, b)}"


def test_trim_edges_all_rotations_asymmetric():
    """Cut off edges: input in reading direction, in all 4 rotations with UNEQUAL values
    (equal values would hide a wrong mapping).
    """
    S = type("S", (), {"trim_l_mm": 1.0, "trim_t_mm": 2.0, "trim_r_mm": 3.0, "trim_b_mm": 4.0})()
    box = (0.0, 0.0, 210 * MM, 297 * MM)
    # displayed -> unrotated: which PDF edge lies left/top/right/bottom (display rotated clockwise)
    shown = {0: ("l", "t", "r", "b"), 90: ("b", "l", "t", "r"), 180: ("r", "b", "l", "t"), 270: ("t", "r", "b", "l")}
    for rot, edges in shown.items():
        (left, b, r, t), orig = pdfmanip.trim_box_for(box, rot, S)
        cut = {"l": left / MM, "b": b / MM, "r": (box[2] - r) / MM, "t": (box[3] - t) / MM}
        got = tuple(round(cut[e], 3) for e in edges)  # left, top, right, bottom as displayed
        assert got == (1.0, 2.0, 3.0, 4.0), (rot, got)
        assert orig == (1.0, 2.0, 3.0, 4.0)


def test_white_bbox_large_and_tinted_content():
    """White space: content larger than half the page or a tinted background is still detected
    (the background comes from the page edge, not from the median of the whole page).
    """
    import io

    from reportlab.pdfgen import canvas

    for frac, tint in ((0.3, None), (0.9, None), (0.9, (0.95, 0.93, 0.88))):
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(210 * MM, 297 * MM))
        if tint:
            c.setFillColorRGB(*tint)
            c.rect(0, 0, 210 * MM, 297 * MM, fill=1, stroke=0)
        w, h = 210 * MM * frac, 297 * MM * frac
        x, y = (210 * MM - w) / 2, (297 * MM - h) / 2
        c.setFillColorRGB(0.1, 0.3, 0.8)
        c.rect(x, y, w, h, fill=1, stroke=0)
        c.showPage()
        c.save()
        bb = pdfmanip._white_bbox(pdfium.PdfDocument(buf.getvalue())[0])
        assert bb and all(abs(g - e) < 2 * MM for g, e in zip(bb, (x, y, x + w, y + h))), (frac, tint, bb)


def test_preview_before_reads_cmyk_like_after():
    """Unchanged CMYK must look the same before and after: both sides read it with the same profile."""
    import tempfile

    from PIL import Image

    calls = []

    def fake_render(gs, src, page, dpi, device, extra, out):
        calls.append((device, list(extra)))
        mode = "CMYK" if device == "tiff32nc" else "RGB"
        Image.new(mode, (4, 4)).save(out)

    old = cmyk._render, cmyk.ghostscript
    cmyk._render, cmyk.ghostscript = fake_render, lambda: "gs"
    try:
        tmp = tempfile.mkdtemp()
        pdf = os.path.join(tmp, "x.pdf")
        doc = pdfium.PdfDocument.new()
        doc.new_page(100, 100)
        doc.save(pdf)
        prof = FOGRA if os.path.exists(FOGRA) else None
        if prof is None:
            print("skip (no FOGRA39 profile)")
            return
        cmyk.render_preview(pdf, 0, cmyk.ManipSettings(cmyk=True, cmyk_mode="rgb_only", target=prof))
        before = dict(calls)["png16m"]
        assert "-sDefaultCMYKProfile=" + prof in before and "-dRenderIntent=1" in before
        calls.clear()
        cmyk.render_preview(pdf, 0, cmyk.ManipSettings(cmyk=True, cmyk_mode="all", target=prof))
        assert dict(calls)["png16m"] == []  # no source profile known: Ghostscript's default on both sides
        calls.clear()
        cmyk.render_preview(pdf, 0, cmyk.ManipSettings(cmyk=True, cmyk_mode="gray"))
        assert dict(calls)["png16m"] == []
    finally:
        cmyk._render, cmyk.ghostscript = old


def test_ghostscript_working_profiles_hidden():
    assert cmyk._gs_internal("/usr/share/ghostscript/10.02.1/iccprofiles/ps_cmyk.icc", "x")
    assert cmyk._gs_internal("/opt/p/whatever.icc", "Artifex PS CMYK Profile")
    assert not cmyk._gs_internal("/usr/share/ghostscript/iccprofiles/default_cmyk.icc", "Artifex CMYK SWOP Profile")
    assert not cmyk._gs_internal("/usr/share/color/icc/ISOcoated_v2.icc", "ISO Coated v2 (ECI)")
    assert all(not p.name.startswith("Artifex PS ") for p in cmyk.find_profiles())


def test_existing_cmyk_read_with_output_intent():
    """A file already separated for the target stays 1:1; another output intent is the source profile."""
    import tempfile

    import pikepdf

    if not os.path.exists(FOGRA):
        print("skip (no FOGRA39 profile)")
        return
    tmp = tempfile.mkdtemp()
    with open(FOGRA, "rb") as f:
        data = f.read()
    flagged = bytearray(data)
    flagged[44:48] = b"\1\0\0\0"  # other flags / ID: still the same profile
    flagged[84:100] = b"x" * 16
    assert cmyk.same_profile(bytes(flagged), FOGRA)
    other = os.path.join(tmp, "other.icc")
    with open(other, "wb") as f:
        f.write(data[:-1] + bytes([data[-1] ^ 1]))
    assert not cmyk.same_profile(data, other)

    pdf_path = os.path.join(tmp, "sep.pdf")
    pdf = pikepdf.new()
    pdf.add_blank_page()
    pdf.save(pdf_path)
    s = cmyk.ManipSettings(cmyk=True, cmyk_mode="all", target=FOGRA)
    assert cmyk.resolve_source(pdf_path, s, tmp) == (s, [])  # no output intent: Ghostscript default
    cmyk.embed_output_intent(pdf_path, FOGRA)
    assert cmyk.document_cmyk_profile(pdf_path) == data
    s2, notes = cmyk.resolve_source(pdf_path, s, tmp)
    assert s2.cmyk_mode == "rgb_only" and len(notes) == 1  # same as the target: CMYK passes through
    assert "-sDefaultCMYKProfile=" + FOGRA in cmyk.color_args(s2)
    s3, notes = cmyk.resolve_source(pdf_path, cmyk.ManipSettings(cmyk=True, cmyk_mode="all", target=other), tmp)
    assert s3.cmyk_mode == "all" and s3.source.endswith("source.icc") and len(notes) == 1
    s4 = cmyk.ManipSettings(cmyk=True, cmyk_mode="all", target=other, source="/p/chosen.icc")
    assert cmyk.resolve_source(pdf_path, s4, tmp) == (s4, [])  # an explicitly chosen source profile wins
    s5 = cmyk.ManipSettings(cmyk=True, cmyk_mode="rgb_only", target=other)
    assert cmyk.resolve_source(pdf_path, s5, tmp) == (s5, [])


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
