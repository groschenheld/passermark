# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Create bleed (bleedgen.py: mirror/stretch the edges, boxes) and the safety distance check (preflight.py)."""

import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "_qtstub"))
sys.path.insert(0, os.path.join(HERE, ".."))

import pikepdf  # noqa: E402

from pdfdruck import bleedgen, l10n, preflight  # noqa: E402

l10n.set_language("de")
MM = 72 / 25.4

# left half blue, right half red, green square in the lower left corner (200 × 100 pt)
CONTENT = b"0 0 1 rg 0 0 100 100 re f 1 0 0 rg 100 0 100 100 re f 0 1 0 rg 0 0 20 20 re f"


def _pdf(content=CONTENT, media=(0, 0, 200, 100), trim=None, rotate=0, pages=1) -> bytes:
    pdf = pikepdf.new()
    for _ in range(pages):
        d = pikepdf.Dictionary(Type=pikepdf.Name.Page, MediaBox=list(media), Contents=pdf.make_stream(content))
        d.Resources = pikepdf.Dictionary()
        if trim:
            d.TrimBox = list(trim)
        if rotate:
            d.Rotate = rotate
        pdf.pages.append(pikepdf.Page(d))
    b = io.BytesIO()
    pdf.save(b)
    return b.getvalue()


def _render(data: bytes, page: int = 0, scale: float = 2.0):
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(data)
    try:
        return doc[page].render(scale=scale).to_pil().convert("RGB")
    finally:
        doc.close()


def _boxes(data: bytes, page: int = 0) -> dict:
    with pikepdf.open(io.BytesIO(data)) as p:
        o = p.pages[page].obj
        return {
            k: [round(float(v), 2) for v in o[k]] for k in ("/MediaBox", "/TrimBox", "/BleedBox", "/CropBox") if k in o
        }


def _near(c, want, tol=40):
    return all(abs(a - b) <= tol for a, b in zip(c, want, strict=True))


def test_matrices():
    trim, b = [0, 0, 200, 100], 10
    strips = bleedgen.strip_matrices(trim, b, "mirror")
    assert len(strips) == 8
    (rx, ry, rw, rh), m = next(s for s in strips if s[0][0] < 0 and s[0][1] == 0)  # left strip
    assert (rx, ry, rw, rh) == (-10, 0, 10, 100)
    x = 3.0  # 3 pt inside the edge -> 3 pt outside
    assert abs(m[0] * x + m[4] - (-3.0)) < 1e-9 and m[3] == 1 and m[5] == 0
    (_r, m) = next(s for s in bleedgen.strip_matrices(trim, b, "stretch") if s[0][0] < 0 and s[0][1] == 0)
    band = bleedgen.STRETCH_BAND_MM * MM
    assert abs(m[0] * 0 + m[4] - (-10)) < 1e-9  # the page edge lands on the outer edge of the bleed
    assert abs(m[0] * band + m[4] - band) < 1e-9  # the inner end of the strip stays put
    assert m[0] > 1  # not mirrored: order kept


def test_mirror_render_and_boxes():
    out, notes = bleedgen.add_bleed(_pdf(), None, 10, "mirror")
    assert "Anschnitt 10 mm (gespiegelt) erzeugt: Seite 1." in notes
    b = round(10 * MM, 2)
    bx = _boxes(out)
    assert bx["/TrimBox"] == [0, 0, 200, 100] and bx["/MediaBox"] == [-b, -b, 200 + b, 100 + b]
    assert bx["/BleedBox"] == bx["/MediaBox"] == bx["/CropBox"]
    im = _render(out)
    s = 2.0
    # left bleed beside the green corner square: mirrored green; top left above the blue: blue
    assert _near(im.getpixel((int(10 * s), int((100 + 2 * b - 10) * s))), (0, 255, 0))
    assert _near(im.getpixel((int(5 * s), int(5 * s))), (0, 0, 255))
    assert _near(im.getpixel((int((200 + 2 * b - 5) * s), int(60 * s))), (255, 0, 0))  # right bleed: red
    again, n2 = bleedgen.add_bleed(out, None, 10, "mirror")
    assert again == out and "schon genug" in n2[0]


def test_partial_bleed_and_trim():
    """TrimBox 5 pt inside: real content beyond the final format stays, only the rest is filled."""
    content = b"0 0 1 rg -5 -5 210 110 re f 1 1 0 rg -5 40 5 20 re f"  # yellow only in the existing bleed
    d = _pdf(content, media=(-5, -5, 205, 105), trim=(0, 0, 200, 100))
    with pikepdf.open(io.BytesIO(d)) as pdf:
        assert abs(bleedgen.existing_bleed(pdf.pages[0]) - 5) < 1e-6
    out, notes = bleedgen.add_bleed(d, None, 3, "mirror")
    b = 3 * MM
    im = _render(out)
    s = 2.0
    # 2 pt left of the trim (inside the existing 5 pt bleed), at y = 50: the real yellow, not a mirror image
    x = (b - 2) * s
    y = (100 + b - 50) * s
    assert _near(im.getpixel((int(x), int(y))), (255, 255, 0))
    assert _boxes(out)["/TrimBox"] == [0, 0, 200, 100]


def test_pages_rotation_stretch():
    d = _pdf(pages=3, rotate=90)
    out, notes = bleedgen.add_bleed(d, [1], 3, "stretch")
    assert "gestreckt" in notes[0] and "Seite 2" in notes[0]
    assert _boxes(out, 0)["/MediaBox"] == [0, 0, 200, 100]  # untouched
    assert _boxes(out, 1)["/TrimBox"] == [0, 0, 200, 100]
    with pikepdf.open(io.BytesIO(out)) as p:
        assert int(p.pages[1].obj.Rotate) == 90
    im = _render(out, 1)
    assert im.size[0] < im.size[1]  # still shown rotated
    try:
        bleedgen.add_bleed(d, None, 3, "blur")
        raise AssertionError("unknown mode accepted")
    except ValueError:
        pass
    assert bleedgen.add_bleed(d, None, 0)[0] == d


def test_job():
    from pdfdruck import core, workflow

    tmp = tempfile.mkdtemp()
    src, dst = os.path.join(tmp, "a.pdf"), os.path.join(tmp, "b.pdf")
    with open(src, "wb") as f:
        f.write(_pdf(pages=2))
    res = core.run_job("bleed", src, dst, {"bleed_mm": 2}, {"pages": [0]})
    assert res.info["changed"] and "Seite 1." in res.notes[0]
    with open(dst, "rb") as f:
        data = f.read()
    assert _boxes(data, 0)["/TrimBox"] == [0, 0, 200, 100] and "/TrimBox" not in _boxes(data, 1)
    assert workflow.schema()["$defs"]["settings.bleed"]["properties"]["mode"]["default"] == "mirror"


def _text_pdf(content: bytes, media=(0, 0, 400, 400), trim=None) -> bytes:
    pdf = pikepdf.new()
    font = pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica)
    img = pdf.make_stream(bytes([200] * 4))
    img.Type, img.Subtype, img.Width, img.Height = pikepdf.Name.XObject, pikepdf.Name.Image, 2, 2
    img.BitsPerComponent, img.ColorSpace = 8, pikepdf.Name.DeviceGray
    res = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font), XObject=pikepdf.Dictionary(Im=img))
    d = pikepdf.Dictionary(
        Type=pikepdf.Name.Page, MediaBox=list(media), Resources=res, Contents=pdf.make_stream(content)
    )
    if trim:
        d.TrimBox = list(trim)
    pdf.pages.append(pikepdf.Page(d))
    b = io.BytesIO()
    pdf.save(b)
    return b.getvalue()


def test_safety_distance():
    content = b"""BT /F1 10 Tf 4 200 Td (N) Tj ET
BT /F1 10 Tf 200 200 Td (innen) Tj ET
q 20 0 0 20 200 6 cm /Im Do Q
q 20 0 0 20 380 300 cm /Im Do Q
q 420 0 0 300 -10 -10 cm /Im Do Q
q 30 0 0 30 150 150 cm /Im Do Q"""
    rep = preflight.analyze(_text_pdf(content))
    boxes = rep.near_edge.get(1) or []
    xs = sorted(round(b[0]) for b in boxes)
    assert xs == [5, 200], boxes  # the "N" at the left edge and the small image 6 pt above the bottom edge
    iss = [i for i in rep.issues if "Sicherheits" in i.message or "näher als 3 mm" in i.message]
    assert len(iss) == 1 and iss[0].pages == [1] and iss[0].severity == "warning" and len(iss[0].spots) == 2
    # with a TrimBox the distance counts from the final format: text in the bleed area is not reported
    rep = preflight.analyze(_text_pdf(b"BT /F1 10 Tf 2 200 Td (B) Tj ET", (0, 0, 420, 420), (10, 10, 410, 410)))
    assert not rep.near_edge
    # text crossing the final format is reported
    rep = preflight.analyze(_text_pdf(b"BT /F1 10 Tf 6 200 Td (BB) Tj ET", (0, 0, 420, 420), (10, 10, 410, 410)))
    assert 1 in rep.near_edge
    # tiny formats (labels) are not checked
    assert not preflight.analyze(_text_pdf(b"BT /F1 4 Tf 1 5 Td (x) Tj ET", (0, 0, 50, 30))).near_edge


def test_dialog():
    from pdfdruck.gui import bleeddialog as D

    d = _pdf(media=(-5, -5, 205, 105), trim=(0, 0, 200, 100))
    size, have = D.page_state(d, 0)
    assert abs(size[0] - 200 / MM) < 1e-6 and abs(have - 5 / MM) < 1e-6
    assert "bleibt unverändert" in D.state_text(size, have, 1.0)
    t = D.state_text(size, have, 3.0)
    assert "1,8 mm → neu 3,0 mm" in t and "70,6 × 35,3 mm" in t
    dlg = D.BleedDialog(None, d, 0, 1)
    assert dlg.size == size


def _print_render(bleed_mode: str, doc_bleed=True, bleed_mm=6.0, data=None, marks=False, fill=True):
    """Single sheet in the print path (layout.plan + impose) -> (image, placement)."""
    import pypdfium2 as pdfium

    from pdfdruck.layout import LayoutSettings, Sheet, impose, page_doc_bleeds, page_trims, plan

    data = data or _pdf(b"0 0 1 rg 0 0 200 100 re f 1 0 0 rg 5 0 3 100 re f")  # blue, red stripe 5..8 pt
    doc = pdfium.PdfDocument(data)
    s = LayoutSettings(
        mode="actual",
        autorotate=False,
        bleed_mm=bleed_mm,
        bleed_mode=bleed_mode,
        doc_bleed=doc_bleed,
        bleed_fill=fill,
        crop_marks=marks,
        use_margins=False,
        orientation="portrait",
    )
    sheet = Sheet(300, 400, None)
    plans = plan([(doc[0].get_width(), doc[0].get_height())], [0], sheet, s, page_trims(doc), page_doc_bleeds(doc))
    out = impose(doc, sheet, plans)
    im = out[0].render(scale=2).to_pil().convert("RGB")
    pl = plans[0].placements[0]
    out.close()
    doc.close()
    return im, pl


def test_print_mirror_or_stretch():
    """Missing bleed in the print path: mirrored (the red stripe appears outside) or stretched (edge colour)."""
    for mode, want in (("mirror", (255, 0, 0)), ("stretch", (0, 0, 255))):
        im, pl = _print_render(mode)
        x = (pl.x - 6.5) * 2  # 6.5 pt left of the page edge
        y = (400 - (pl.y + 50)) * 2
        assert _near(im.getpixel((int(x), int(y))), want), (mode, im.getpixel((int(x), int(y))))
        assert _near(im.getpixel((int((pl.x + 6.5) * 2), int(y))), (255, 0, 0))  # the page itself unchanged


def test_print_no_fill():
    """Without "create missing bleed" nothing is mirrored: only the file's own bleed (5 pt) is printed."""
    im, pl = _print_render("mirror", fill=False)  # file without bleed
    y = int((400 - (pl.y + 50)) * 2)
    assert _near(im.getpixel((int((pl.x - 3) * 2), y)), (255, 255, 255))
    assert _near(im.getpixel((int((pl.x + 3) * 2), y)), (0, 0, 255))
    data = _pdf(b"0 0 1 rg 0 0 210 110 re f", media=(0, 0, 210, 110), trim=(5, 5, 205, 105))
    for fill, far in ((False, (255, 255, 255)), (True, (0, 0, 255))):
        im, pl = _print_render("mirror", data=data, fill=fill)
        y = int((400 - (pl.y + 50)) * 2)
        assert round(pl.w) == 200
        assert _near(im.getpixel((int((pl.x - 3) * 2), y)), (0, 0, 255)), fill  # the file's bleed
        assert _near(im.getpixel((int((pl.x - 9) * 2), y)), far), (fill, im.getpixel((int((pl.x - 9) * 2), y)))


def test_print_doc_bleed():
    """The document has 5 pt bleed (TrimBox): with "use the document's bleed" the page is printed whole,
    without it bleed 0 prints exactly the final format."""
    from pdfdruck.layout import LayoutSettings, Sheet, plan

    sizes, trims = [(210, 110)], [(5, 5, 5, 5)]
    keep = plan(sizes, [0], Sheet(400, 300, None), LayoutSettings(mode="actual", autorotate=False), trims, [5])
    assert round(keep[0].placements[0].w) == 210 and keep[0].placements[0].trim is None
    cut = plan(
        sizes, [0], Sheet(400, 300, None), LayoutSettings(mode="actual", autorotate=False, doc_bleed=False), trims, [5]
    )
    assert round(cut[0].placements[0].w) == 200 and cut[0].placements[0].trim == (5, 5, 5, 5)


def test_print_bleed_texts():
    from pdfdruck.gui.printdialog import _mm, bleed_texts
    from pdfdruck.l10n import tr
    from pdfdruck.layout import available_bleeds

    av = available_bleeds([None, (8.5, 8.5, 8.5, 8.5), (8.5, 8.5, 8.5, 8.5)], [0, 8.5039, 0], 3)
    assert av[0] is None and abs(av[1] - 3.0) < 0.01 and abs(av[2] - 8.5 / MM) < 0.01
    t = bleed_texts(av, 3.0, "gespiegelt")
    assert t["doc"] == tr("Die Datei hat schon Anschnitt: Seite {0} ({1} mm).").format("2–3", _mm(3.0)) + " " + tr(
        "Ohne Anschnitt: Seite {0}."
    ).format(1)
    assert (
        t["add"] == tr("Wird beim Druck ergänzt ({0}): Seite {1}.").format("gespiegelt", 1)
        and abs(t["doc_mm"] - 3.0) < 0.01
    )
    assert bleed_texts(av[1:], 3.0, "x")["add"] == tr("Anschnitt vollständig in der Datei – nichts wird ergänzt.")
    assert bleed_texts(av, 0.0, "x")["add"] == tr("Anschnitt 0 mm: gedruckt wird genau das Endformat.")
    assert bleed_texts([None, None], 3.0, "x")["doc"] == ""
    assert bleed_texts(av, 3.0, "x", fill=False)["add"] == tr(
        "Gedruckt wird der Anschnitt aus der Datei – nichts wird ergänzt."
    )
    no = tr("Kein Anschnitt: gedruckt wird genau das Endformat.")
    assert bleed_texts(av, 3.0, "x", fill=False, use_doc=False)["add"] == no
    assert bleed_texts([None], 3.0, "x", fill=False)["add"] == no
    assert abs(t["doc_max"] - 8.5 / MM) < 0.01


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
