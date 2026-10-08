# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
import io, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("PASSERMARK_LANG", "de")
import pypdfium2 as pdfium
from pdfdruck import objects

MM = 72 / 25.4


def card_sheet(path="/tmp/_cards.pdf", rotate=False):
    """A4 mit 2×5 Visitenkarten 85×55 (5 mm Abstand), mit weißer Fläche und Text in jeder Karte."""
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(path, pagesize=(210 * MM, 297 * MM))
    for r in range(5):
        for col in range(2):
            x, y = (15 + col * 95) * MM, (10 + r * 57) * MM
            c.setFillColorRGB(0.1, 0.3, 0.6); c.rect(x, y, 85 * MM, 55 * MM, fill=1, stroke=0)
            c.setFillColorRGB(1, 1, 1); c.rect(x + 50 * MM, y + 5 * MM, 30 * MM, 20 * MM, fill=1, stroke=0)
            c.setFillColorRGB(1, 1, 1); c.drawString(x + 5 * MM, y + 40 * MM, f"Karte {r}/{col}")
    c.showPage(); c.save()
    if rotate:
        import pypdf
        rd = pypdf.PdfReader(path); w = pypdf.PdfWriter(); p = rd.pages[0]; p.rotate(90); w.add_page(p); w.write(path)
    return pdfium.PdfDocument(path)


def test_detect_cards_vector():
    n = objects.normalized(card_sheet())
    boxes = objects.detect(n[0], objects.DetectSettings())
    assert len(boxes) == 10, len(boxes)
    for b in boxes:
        assert abs(b.w / MM - 85) < 0.6 and abs(b.h / MM - 55) < 0.6, (b.w / MM, b.h / MM)
    # Lesereihenfolge: erste Karte oben links
    assert boxes[0].x0 < boxes[1].x0 and boxes[0].y1 > boxes[2].y1


def test_separate_pages():
    n = objects.normalized(card_sheet())
    boxes = objects.detect(n[0], objects.DetectSettings())
    out = objects.separate(n, {0: boxes})
    assert len(out) == 10
    w, h = out.get_page_size(3)
    assert abs(w / MM - 85) < 0.6 and abs(h / MM - 55) < 0.6
    img = out[0].render(scale=1).to_pil()
    assert img.getpixel((2, 2))[2] > 100            # Rand der Seite = Kartenblau, kein Weiß


def test_rotated_page():
    n = objects.normalized(card_sheet("/tmp/_cards_rot.pdf", rotate=True))
    assert round(n.get_page_size(0)[0] / MM) == 297    # Drehung eingerechnet
    boxes = objects.detect(n[0], objects.DetectSettings())
    assert len(boxes) == 10 and abs(boxes[0].w / MM - 55) < 0.6


def test_gap_merges_parts():
    from reportlab.pdfgen import canvas
    c = canvas.Canvas("/tmp/_parts.pdf", pagesize=(210 * MM, 297 * MM))
    c.rect(20 * MM, 200 * MM, 30 * MM, 30 * MM, fill=1); c.rect(51 * MM, 200 * MM, 30 * MM, 30 * MM, fill=1)  # 1 mm Lücke
    c.rect(20 * MM, 50 * MM, 30 * MM, 30 * MM, fill=1); c.showPage(); c.save()
    n = objects.normalized(pdfium.PdfDocument("/tmp/_parts.pdf"))
    assert len(objects.detect(n[0], objects.DetectSettings(gap_mm=2))) == 2
    assert len(objects.detect(n[0], objects.DetectSettings(gap_mm=0))) == 3


def test_raster_scan():
    """Scan: graues Papier mit Rauschen, zwei Fotos -> Farbmodus."""
    import numpy as np, img2pdf
    from PIL import Image
    rng = np.random.default_rng(1)
    a = (235 + rng.integers(-6, 6, (1169, 827, 3))).astype(np.uint8)       # A4 @100 dpi, Papiergrau + Rauschen
    a[100:400, 80:500] = (180, 40, 30); a[600:1000, 300:700] = (20, 120, 60)
    Image.fromarray(a).save("/tmp/_scan.png", dpi=(100, 100))
    open("/tmp/_scan.pdf", "wb").write(img2pdf.convert("/tmp/_scan.png"))
    n = objects.normalized(pdfium.PdfDocument("/tmp/_scan.pdf"))
    boxes = objects.detect(n[0], objects.DetectSettings())
    assert len(boxes) == 2
    assert abs(boxes[0].w / MM - 420 * 25.4 / 100) < 1.0


def test_negative_margin():
    n = objects.normalized(card_sheet())
    boxes = objects.detect(n[0], objects.DetectSettings(margin_mm=-2))
    assert len(boxes) == 10 and abs(boxes[0].w / MM - 81) < 0.6 and abs(boxes[0].h / MM - 51) < 0.6


def test_full_page_motif_is_one_object():
    from reportlab.pdfgen import canvas
    c = canvas.Canvas("/tmp/_vk1.pdf", pagesize=(85 * MM, 55 * MM))
    c.setFillColorRGB(0.1, 0.3, 0.6); c.rect(0, 0, 85 * MM, 55 * MM, fill=1, stroke=0)
    c.setFillColorRGB(0.9, 0.8, 0.1); c.rect(0, 0, 30 * MM, 55 * MM, fill=1, stroke=0); c.showPage(); c.save()
    n = objects.normalized(pdfium.PdfDocument("/tmp/_vk1.pdf"))
    b = objects.detect(n[0], objects.DetectSettings())
    assert len(b) == 1 and abs(b[0].w / MM - 85) < 0.5


def test_margin_applied_at_output():
    """Rand wird beim Ausgeben angewendet (auch nachträglich geändert, auch für eigene Rahmen)."""
    n = objects.normalized(card_sheet())
    boxes = objects.detect(n[0], objects.DetectSettings())            # ohne Rand erkannt
    out = objects.separate(n, {0: boxes[:2] + [objects.Box(10 * MM, 10 * MM, 50 * MM, 40 * MM)]}, margin_mm=-3)
    w, h = (v / MM for v in out.get_page_size(0))
    assert abs(w - 79) < 0.6 and abs(h - 49) < 0.6, (w, h)          # 85×55 -> 79×49
    w, h = (v / MM for v in out.get_page_size(2))
    assert abs(w - 34) < 0.1 and abs(h - 24) < 0.1                   # eigener Rahmen 40×30 -> 34×24


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("ok", k)
