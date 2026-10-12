# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
import math, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("PASSERMARK_LANG", "de")
import numpy as np
import pypdfium2 as pdfium
from pdfdruck import cutcontour, objects

MM = 72 / 25.4


def stickers(path="/tmp/_stickers.pdf"):
    """Circle, "C" with a 1 mm slit, five-pointed star – without page background (vector)."""
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(path, pagesize=(210 * MM, 297 * MM))
    c.setFillColorRGB(0.9, 0.2, 0.1); c.circle(50 * MM, 240 * MM, 25 * MM, fill=1, stroke=0)
    c.setFillColorRGB(0.1, 0.5, 0.2)                         # C: Ring mit echtem 1 mm breitem Schlitz rechts
    cx, cy, ro, ri = 140 * MM, 240 * MM, 30 * MM, 18 * MM
    to, ti = (0.5 * MM) / ro, (0.5 * MM) / ri
    pts = [(cx + ro * math.cos(a), cy + ro * math.sin(a)) for a in np.linspace(to, 2 * math.pi - to, 180)]
    pts += [(cx + ri * math.cos(a), cy + ri * math.sin(a)) for a in np.linspace(2 * math.pi - ti, ti, 120)]
    p = c.beginPath(); p.moveTo(*pts[0])
    for q in pts[1:]: p.lineTo(*q)
    p.close(); c.drawPath(p, fill=1, stroke=0)
    c.setFillColorRGB(0.95, 0.75, 0.1)
    p = c.beginPath()
    for k in range(10):
        r = (35 if k % 2 == 0 else 14) * MM
        a = math.pi / 2 + k * math.pi / 5
        x, y = 100 * MM + r * math.cos(a), 100 * MM + r * math.sin(a)
        p.moveTo(x, y) if k == 0 else p.lineTo(x, y)
    p.close(); c.drawPath(p, fill=1, stroke=0)
    c.showPage(); c.save()
    return pdfium.PdfDocument(path)


def inside(poly, x, y):
    poly = np.asarray(poly); n = len(poly); c = False
    for i in range(n):
        x1, y1 = poly[i]; x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def pts(r):
    return [np.asarray(p) for p, _smooth in r.paths]


def near(paths, x, y):
    return min(paths, key=lambda p: math.hypot(p[:, 0].mean() - x, p[:, 1].mean() - y))


def test_contours_and_smoothing():
    norm = objects.normalized(stickers())
    r = cutcontour.compute(norm[0], cutcontour.CutSettings(smooth_mm=1.5, offset_mm=0.0))
    assert len(r.paths) == 3, len(r.paths)
    rad = np.hypot(*(near(pts(r), 50 * MM, 240 * MM) - [50 * MM, 240 * MM]).T) / MM
    assert abs(rad.mean() - 25) < 0.3, rad.mean()
    cpath = next(p for p in pts(r) if inside(p, 140 * MM, 264 * MM))
    assert inside(cpath, 165 * MM, 240 * MM), "Schlitz nicht überbrückt"
    r0 = cutcontour.compute(norm[0], cutcontour.CutSettings(smooth_mm=0.0))
    c0 = next(p for p in pts(r0) if inside(p, 140 * MM, 264 * MM))
    assert not inside(c0, 165 * MM, 240 * MM)


def _alpha_at(o, x, y):
    a = np.asarray(o.bleed_rgba); x0, y0, x1, y1 = o.bleed_box
    col = int((x - x0) / (x1 - x0) * a.shape[1]); row = int((y1 - y) / (y1 - y0) * a.shape[0])
    if not (0 <= row < a.shape[0] and 0 <= col < a.shape[1]):
        return 0
    return a[row, col, 3]


def test_cut_inside_bleed_and_bleed_from_object():
    norm = objects.normalized(stickers())
    r = cutcontour.compute(norm[0], cutcontour.CutSettings(bleed_mm=2.0, smooth_mm=1.5))
    for o in r.objects:
        for poly, _ in o.paths:
            for x, y in poly[:: max(1, len(poly) // 50)]:
                assert _alpha_at(o, x, y) > 200, "Schnittlinie nicht im Überfüller"
    # bleed extends from the object: covered 1.5 mm outside the circle motif (radius 26.5), not 4 mm outside
    circ = r.objects[0]
    assert _alpha_at(circ, 50 * MM + 26.5 * MM, 240 * MM) > 200
    assert _alpha_at(circ, 50 * MM + 29 * MM, 240 * MM) < 30
    # cut 4 mm outside: the gap between object and line AND 2 mm beyond the line filled, in the object colour (red)
    r = cutcontour.compute(norm[0], cutcontour.CutSettings(offset_mm=4, bleed_mm=2, smooth_mm=0.5))
    circ = r.objects[0]
    for d in (26, 27.5, 29, 30.5):
        assert _alpha_at(circ, 50 * MM + d * MM, 240 * MM) > 200, d
    a = np.asarray(circ.bleed_rgba); x0, y0, x1, y1 = circ.bleed_box
    col = int((50 * MM + 28 * MM - x0) / (x1 - x0) * a.shape[1]); row = int((y1 - 240 * MM) / (y1 - y0) * a.shape[0])
    rr, gg, bb = a[row, col, :3]
    assert rr > 180 and gg < 90, (rr, gg, bb)


def test_offset_outward_and_inward():
    norm = objects.normalized(stickers())
    for off, want in ((2.0, 27), (-3.0, 22)):
        r = cutcontour.compute(norm[0], cutcontour.CutSettings(offset_mm=off, smooth_mm=0.5))
        rad = np.hypot(*(near(pts(r), 50 * MM, 240 * MM) - [50 * MM, 240 * MM]).T) / MM
        assert abs(rad.mean() - want) < 0.3, (off, rad.mean())


def test_shapes_sized_to_object():
    """Option „eine Form je Objekt“ (Aufkleberbogen): jede Form passt zu ihrem Aufkleber."""
    norm = objects.normalized(stickers())
    for kind in cutcontour.SHAPES[1:]:
        r = cutcontour.compute(norm[0], cutcontour.CutSettings(shape=kind, corner_mm=5, single_shape=False))
        assert len(r.paths) == 3, kind
        p = near(pts(r), 50 * MM, 240 * MM)                      # Kreismotiv 50 × 50 mm
        w, h = (p[:, 0].max() - p[:, 0].min()) / MM, (p[:, 1].max() - p[:, 1].min()) / MM
        assert abs(w - 50) < 0.6 and abs(h - 50) < 0.6, (kind, w, h)
    # scaling and fixed size
    r = cutcontour.compute(norm[0], cutcontour.CutSettings(shape="rect", scale_pct=80, single_shape=False))
    p = near(pts(r), 50 * MM, 240 * MM)
    assert abs((p[:, 0].max() - p[:, 0].min()) / MM - 40) < 0.6
    r = cutcontour.compute(norm[0], cutcontour.CutSettings(shape="circle", width_mm=60, single_shape=False))
    p = near(pts(r), 50 * MM, 240 * MM)
    assert abs((p[:, 0].max() - p[:, 0].min()) / MM - 60) < 0.6
    # rectangle with -2 mm offset: 46 mm, sharp corners (polyline, not smoothed)
    r = cutcontour.compute(norm[0], cutcontour.CutSettings(shape="rect", offset_mm=-2, single_shape=False))
    p = near(pts(r), 50 * MM, 240 * MM)
    assert abs((p[:, 0].max() - p[:, 0].min()) / MM - 46) < 0.6 and r.paths[0][1] is False


def test_single_shape_around_whole_motif():
    """Default for basic shapes: ONE shape centred around all parts of the motif, scaled from the centre;
    the circle encloses the motif (larger side) instead of cutting through it."""
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    c = canvas.Canvas("/tmp/_logo.pdf", pagesize=(150 * mm, 100 * mm))
    c.setFillColorRGB(0.8, 0.1, 0.1)
    for x in (30, 60, 90):                                   # three separate parts, 8 mm gap
        c.rect(x * mm, 40 * mm, 22 * mm, 22 * mm, fill=1, stroke=0)
    c.showPage(); c.save()
    norm = objects.normalized(pdfium.PdfDocument("/tmp/_logo.pdf"))
    def box(r):
        p = np.array([pt for poly, _s in r.paths for pt in poly]); return [v / MM for v in (p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max())]
    r = cutcontour.compute(norm[0], cutcontour.CutSettings(shape="rect", offset_mm=0, bleed_mm=0))
    assert len(r.paths) == 1
    b = box(r)
    assert abs(b[0] - 30) < 0.6 and abs(b[2] - 112) < 0.6 and abs(b[1] - 40) < 0.6 and abs(b[3] - 62) < 0.6, b
    r2 = cutcontour.compute(norm[0], cutcontour.CutSettings(shape="rect", offset_mm=0, bleed_mm=0, scale_pct=150))
    b2 = box(r2)
    assert abs(((b2[0] + b2[2]) - (b[0] + b[2])) / 2) < 0.3 and abs((b2[2] - b2[0]) - 1.5 * (b[2] - b[0])) < 0.8, (b, b2)
    rc = cutcontour.compute(norm[0], cutcontour.CutSettings(shape="circle", offset_mm=0, bleed_mm=0))
    bc = box(rc)
    assert abs((bc[2] - bc[0]) - 82) < 0.8, bc                 # Durchmesser = Breite des ganzen Motivs
    assert len(cutcontour.compute(norm[0], cutcontour.CutSettings(shape="contour", bleed_mm=0)).paths) == 3


def test_pdf_output_on_sheet_and_per_object():
    import pikepdf
    doc, n = cutcontour.make(stickers(), cutcontour.CutSettings(single_shape=False))
    assert n == 3 and len(doc) == 1
    w, h = doc.get_page_size(0)
    assert abs(w / MM - 210) < 0.5 and abs(h / MM - 297) < 0.5        # Bogen bleibt erhalten
    doc.save("/tmp/_cut_out.pdf")
    pk = pikepdf.open("/tmp/_cut_out.pdf"); pg = pk.pages[0]
    cs = pg.Resources.ColorSpace.CSCut
    assert str(cs[0]) == "/Separation" and str(cs[1]) == "/CutContour"
    doc2, n2 = cutcontour.make(stickers(), cutcontour.CutSettings(per_object=True, margin_mm=6, shape="circle", single_shape=False))
    assert len(doc2) == 3
    w, h = doc2.get_page_size(0)                                           # circle 50 + 2×2 bleed + 2×6 margin
    assert abs(w / MM - 66) < 1.0 and abs(h / MM - 66) < 1.0, (w / MM, h / MM)
    doc2.save("/tmp/_cut_per_object.pdf")
    # neighbouring objects are hidden: the corner of the single page is white/empty
    im = pdfium.PdfDocument("/tmp/_cut_per_object.pdf")[1].render(scale=1).to_pil()
    assert min(im.getpixel((2, 2))[:3]) > 240


def test_full_page_motif():
    """Business card at trim size (motif fills the page) -> the whole page is the object, bleed outward."""
    from reportlab.pdfgen import canvas
    c = canvas.Canvas("/tmp/_vk.pdf", pagesize=(85 * MM, 55 * MM))
    c.setFillColorRGB(0.1, 0.3, 0.6); c.rect(0, 0, 85 * MM, 55 * MM, fill=1, stroke=0)
    c.setFillColorRGB(0.9, 0.8, 0.1); c.rect(0, 0, 30 * MM, 55 * MM, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1); c.drawString(40 * MM, 30 * MM, "Hias"); c.showPage(); c.save()
    norm = objects.normalized(pdfium.PdfDocument("/tmp/_vk.pdf"))
    r = cutcontour.compute(norm[0], cutcontour.CutSettings(shape="rounded", corner_mm=3, bleed_mm=2))
    assert len(r.objects) == 1
    p = pts(r)[0]
    assert abs((p[:, 0].max() - p[:, 0].min()) / MM - 85) < 0.6 and abs((p[:, 1].max() - p[:, 1].min()) / MM - 55) < 0.6
    o = r.objects[0]
    assert o.bleed_box[0] < -1.5 * MM and o.bleed_box[2] > 86.5 * MM      # bleed beyond the page edge


def test_bleed_visible_on_opaque_background():
    """Raster image with white background: bleed must not be covered by the background (sheet + single pages)."""
    from PIL import Image, ImageDraw
    from pdfdruck import images
    im = Image.new("RGB", (900, 900), "white")
    ImageDraw.Draw(im).ellipse((300, 300, 600, 600), fill=(205, 40, 40))        # Kreis Ø 300 px @150 dpi = 50,8 mm
    im.save("/tmp/_opaque.png", dpi=(150, 150))
    doc = pdfium.PdfDocument(images.image_to_pdf_bytes("/tmp/_opaque.png"))
    for per in (False, True):
        out, n = cutcontour.make(doc, cutcontour.CutSettings(bleed_mm=3, smooth_mm=1, per_object=per))
        out.save("/tmp/_opaque_out.pdf")
        d = pdfium.PdfDocument("/tmp/_opaque_out.pdf")
        x0, y0, x1, y1 = d[0].get_mediabox()
        scale = 4
        img = d[0].render(scale=scale).to_pil()
        cx, cy = 450 / 150 * 72, (900 - 450) / 150 * 72                      # Kreismitte in pt (Seitensystem)
        r = 150 / 150 * 72
        for dmm in (1.0, 2.0):                                              # 1 and 2 mm outside the circle
            x = (cx + r + dmm * MM - x0) * scale
            y = (y1 - cy) * scale
            px_ = img.getpixel((int(x), int(y)))
            assert px_[0] > 150 and px_[1] < 120, (per, dmm, px_)            # red, not white


def test_soft_raster_solid_bleed_and_inner_hole():
    """Blurred raster on white: bleed in full colour (no mixed tone), inner cut gets bleed."""
    from PIL import Image, ImageDraw, ImageFilter
    from pdfdruck import images
    im = Image.new("RGB", (900, 700), "white"); d = ImageDraw.Draw(im)
    d.rounded_rectangle((100, 100, 700, 560), radius=40, fill=(105, 140, 40))
    d.ellipse((300, 250, 450, 380), fill="white")                                   # Loch ~ 25 × 22 mm
    im = im.resize((450, 350), Image.BILINEAR).resize((900, 700), Image.BICUBIC).filter(ImageFilter.GaussianBlur(1.2))
    im.save("/tmp/_soft.png", dpi=(150, 150))
    doc = pdfium.PdfDocument(images.image_to_pdf_bytes("/tmp/_soft.png"))
    norm = objects.normalized(doc)
    r = cutcontour.compute(norm[0], cutcontour.CutSettings(bleed_mm=3, smooth_mm=1, inner=True))
    o = r.objects[0]
    a = np.asarray(o.bleed_rgba)
    solid = a[a[:, :, 3] > 250][:, :3].astype(int)
    dist = np.abs(solid - [105, 140, 40]).max(axis=1)
    assert (dist <= 6).mean() > 0.97, (dist <= 6).mean()                  # praktisch nur die Vollfarbe
    out, _ = cutcontour.make(doc, cutcontour.CutSettings(bleed_mm=3, smooth_mm=1, inner=True))
    out.save("/tmp/_soft_out.pdf")
    dd = pdfium.PdfDocument("/tmp/_soft_out.pdf"); x0, y0, x1, y1 = dd[0].get_mediabox()
    img = dd[0].render(scale=3).to_pil()
    # 1 mm inside the hole edge (hole: x 300..450 px @150 dpi) must have bleed (green)
    hx = (300 / 150 * 72 + 1 * MM - x0) * 3
    hy = (y1 - (700 - 315) / 150 * 72) * 3
    pxl = img.getpixel((int(hx), int(hy)))
    assert pxl[1] > 110 and pxl[0] < 140 and pxl[2] < 80, pxl


def test_unmix_pale_pink_is_red():
    """Bug from practice: light pink (red + white) was closer to green in RGB distance -> green wedges."""
    pal = np.array([[105, 140, 40], [205, 40, 40]], np.int16)
    pink = np.array([[240, 200, 200], [225, 150, 150], [250, 235, 235]], np.int16)
    d = ((pink[:, None, :] - pal[None]) ** 2).sum(axis=2)
    assert d.argmin(axis=1)[0] == 0                                   # old approach: wrong (green)
    lab = cutcontour._unmix_labels(pink, pal, np.array([255, 255, 255]), 40)
    assert list(lab) == [1, 1, 1]                                     # Entmischen: Rot
    seam = np.array([[160, 85, 40], [130, 115, 40]], np.int16)        # red/green mixture -> nearer side
    assert list(cutcontour._unmix_labels(seam, pal, np.array([255, 255, 255]), 20)) == [1, 0]


def test_fixed_bleed_color():
    norm = objects.normalized(stickers())
    r = cutcontour.compute(norm[0], cutcontour.CutSettings(bleed_color="#00a0e0", bleed_mm=2))
    a = np.asarray(r.objects[0].bleed_rgba)
    solid = a[a[:, :, 3] > 250][:, :3]
    assert (solid == [0, 160, 224]).all()


def test_bleed_off_white_border():
    """Bleed off: motif unchanged (no bleed, no punching), only the cut line – e.g. a white border."""
    import pikepdf
    from PIL import Image, ImageDraw
    from pdfdruck import images
    im = Image.new("RGB", (900, 900), "white")
    ImageDraw.Draw(im).ellipse((300, 300, 600, 600), fill=(205, 40, 40))
    im.save("/tmp/_wb.png", dpi=(150, 150))
    doc = pdfium.PdfDocument(images.image_to_pdf_bytes("/tmp/_wb.png"))
    for kw in (dict(bleed=False, bleed_mm=3), dict(bleed_mm=0)):
        norm = objects.normalized(doc)
        r = cutcontour.compute(norm[0], cutcontour.CutSettings(offset_mm=3, **kw))
        assert r.objects[0].bleed_rgba is None and not r.objects[0].clip and r.knockout is None
        rad = np.hypot(*(pts(r)[0] - [450 / 150 * 72, 450 / 150 * 72]).T).mean() / MM
        assert abs(rad - (150 / 150 * 25.4 + 3)) < 0.4, rad                  # line 3 mm outside
        out, _ = cutcontour.make(doc, cutcontour.CutSettings(offset_mm=3, **kw))
        out.save("/tmp/_wb_out.pdf")
        pk = pikepdf.open("/tmp/_wb_out.pdf")
        content = b"".join(c.read_bytes() for c in (pk.pages[0].Contents if isinstance(pk.pages[0].Contents, pikepdf.Array) else [pk.pages[0].Contents]))
        assert b"PTBleed" not in content and b"W* n" not in content and b"/CSCut CS" in content
        pk.close()
        img = pdfium.PdfDocument("/tmp/_wb_out.pdf")[0].render(scale=2).to_pil()
        x = int((450 / 150 * 72 + (25.4 + 1.5) * MM) * 2); y = int(450 / 150 * 72 * 2)
        assert min(img.getpixel((x, y))[:3]) > 240                              # between motif and line: white


def test_fast_shape_on_trim_without_rendering():
    """Grundform aufs Endformat: keine Seite rendern, kein Arbeitsprozess; Linie genau auf TrimBox (± Abstand)."""
    import io, re
    import pikepdf
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(91 * MM, 61 * MM))      # Visitenkarte 85 × 55 + 3 mm Anschnitt
    c.setFillColorRGB(0.1, 0.4, 0.8); c.rect(0, 0, 91 * MM, 61 * MM, fill=1, stroke=0)
    c.showPage(); c.save()
    pk = pikepdf.open(io.BytesIO(buf.getvalue()))
    pk.pages[0].TrimBox = [3 * MM, 3 * MM, 88 * MM, 58 * MM]
    out = io.BytesIO(); pk.save(out)
    doc = pdfium.PdfDocument(out.getvalue())
    old = cutcontour.render_rgba
    cutcontour.render_rgba = lambda *a, **k: (_ for _ in ()).throw(AssertionError("gerendert"))
    old_pool = cutcontour.WorkerPool.get
    cutcontour.WorkerPool.get = lambda self: (_ for _ in ()).throw(AssertionError("Arbeitsprozess"))
    try:
        for kw, box in (({"shape": "rect"}, (3, 3, 88, 58)),
                        ({"shape": "rect", "offset_mm": -1}, (4, 4, 87, 57)),
                        ({"shape": "circle"}, (18, 3, 73, 58))):
            res, n = cutcontour.make(doc, cutcontour.CutSettings(fit="trim", **kw), workers=4)
            b = io.BytesIO(); res.save(b)
            pkr = pikepdf.open(io.BytesIO(b.getvalue()))
            pg = pkr.pages[0]
            data = b"".join(x.read_bytes() for x in (pg.Contents if isinstance(pg.Contents, pikepdf.Array) else [pg.Contents]))
            tail = data.decode("latin1").split("/CSCut CS")[1]
            pts = [(float(a), float(b_)) for a, b_ in re.findall(r"(-?[\d.]+) (-?[\d.]+) [ml]\b", tail)]
            got = (min(x for x, _ in pts) / MM, min(y for _, y in pts) / MM, max(x for x, _ in pts) / MM, max(y for _, y in pts) / MM)
            assert n == 1 and all(abs(g - e) < 0.05 for g, e in zip(got, box)), (kw, got)
            assert b"PTBleed" not in data
    finally:
        cutcontour.render_rgba = old
        cutcontour.WorkerPool.get = old_pool
    # „je Objekt“ braucht Erkennung -> kein schneller Weg
    assert not cutcontour.is_fast(cutcontour.CutSettings(shape="rect", fit="trim", single_shape=False))
    assert not cutcontour.is_fast(cutcontour.CutSettings(shape="contour", fit="trim"))


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("ok", k)
