# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Seite <-> Bildschirm ohne Seite zu laden (pagegeom) muss exakt wie pdfium rechnen – alle Kombinationen aus
    /Rotate, verschobener CropBox (∩ MediaBox), geerbten Werten und Ansichtsdrehung."""
import ctypes
import io
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pdfdruck import pagegeom, renderproc


def _pdf() -> bytes:
    import pikepdf
    pdf = pikepdf.new()
    cases = [(0, None), (90, [20, 30, 400, 600]), (180, [-50, 10, 500, 700]), (270, [100, 120, 300, 500]),
             (90, None), (0, [10, 20, 590, 820])]
    for rot, crop in cases:
        pdf.add_blank_page(page_size=(595, 842))
        p = pdf.pages[-1].obj
        if rot:
            p.Rotate = rot
        if crop:
            p.CropBox = crop
    pdf.pages[-1].obj.TrimBox = [30, 40, 570, 800]
    del pdf.pages[-1].obj["/MediaBox"]                     # geerbt über /Parent
    pdf.Root.Pages.MediaBox = [0, 0, 600, 850]
    buf = io.BytesIO()
    pdf.save(buf)
    return buf.getvalue()


def test_matches_pdfium():
    import pypdfium2 as pdfium
    import pypdfium2.raw as r
    data = _pdf()
    info = renderproc.page_info(data)
    doc = pdfium.PdfDocument(data)
    try:
        for i in range(len(doc)):
            pg = doc[i]
            assert info[i]["rotate"] * 90 == pg.get_rotation() % 360
            for vr in (0, 90, 180, 270):
                for W, H in ((800, 600), (333, 777)):
                    m = pagegeom.display_matrix(info[i], W, H, vr)
                    for x, y in ((50.0, 60.0), (300.0, 400.0), (590.0, 830.0)):
                        dx, dy = ctypes.c_int(), ctypes.c_int()
                        r.FPDF_PageToDevice(pg.raw, 0, 0, W, H, vr // 90, x, y, ctypes.byref(dx), ctypes.byref(dy))
                        mx, my = pagegeom.to_device(m, x, y)
                        assert abs(mx - dx.value) <= 1 and abs(my - dy.value) <= 1, (i, vr, W, H, x, y, mx, my, dx, dy)
                        px, py = pagegeom.to_page(m, mx, my)
                        assert abs(px - x) < 1e-6 and abs(py - y) < 1e-6
            pg.close()
    finally:
        doc.close()
    assert info[-1]["trim"] is not None and info[-1]["crop"] == (10.0, 20.0, 590.0, 820.0)


if __name__ == "__main__":
    test_matches_pdfium()
    print("ok test_matches_pdfium")
