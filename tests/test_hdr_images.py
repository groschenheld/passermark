# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""HDR-Fotos (JPEG mit Helligkeitskarte als Zusatzbild, Multi-Picture-Format):
    ohne Reparatur zwei Seiten, mit Reparatur eine Seite – Foto verlustfrei, Größe wählbar."""
import io
import os
import sys
import tempfile
os.environ.setdefault("PASSERMARK_LANG", "de")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pdfdruck import images

MM = 72 / 25.4


def _hdr_jpeg(aux_mode="L") -> str:
    """Foto 600×800 px mit 300 dpi + Zusatzbild 300×400 px mit 72 dpi (wie Apple-HDR)."""
    from PIL import Image
    photo = Image.new("RGB", (600, 800), (200, 60, 40))
    for x in range(0, 600, 40):                       # etwas Struktur, damit es kein Einfarb-JPEG ist
        photo.paste((20, 120, 200), (x, 0, x + 20, 800))
    aux = Image.new(aux_mode, (300, 400), 30 if aux_mode == "L" else (90, 90, 90))
    aux.paste(220 if aux_mode == "L" else (250, 250, 250), (100, 100, 200, 200))   # „Lichter“
    fd, p = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    photo.save(p, "MPO", save_all=True, append_images=[aux], dpi=(300, 300), quality=92)
    return p


def _sizes(doc):
    return [tuple(round(v / MM) for v in doc.get_page_size(i)) for i in range(len(doc))]


def test_detect_and_repair_sizes():
    p = _hdr_jpeg()
    try:
        info = images.hdr_aux_info(p)
        assert info and info["main_px"] == (600, 800) and info["aux_px"] == (300, 400) and info["aux_mode"] == "L"
        d = images.images_to_document([p], 96, {"keep": True})      # alt: zwei Seiten
        assert len(d) == 2
        d.close()
        d = images.images_to_document([p], 96)                       # Standard: eine Seite, Größe der Zusatzseite
        aw, ah = images.hdr_size_mm(info, "aux")
        assert len(d) == 1 and _sizes(d) == [(round(aw), round(ah))], _sizes(d)
        d.close()
        d = images.images_to_document([p], 96, {"size": "main", "merge": False})
        assert _sizes(d) == [(51, 68)], _sizes(d)                   # 600 px / 300 dpi = 50,8 mm
        d.close()
        d = images.images_to_document([p], 96, {"size": "aux", "merge": True})
        assert len(d) == 1 and _sizes(d) == [(round(aw), round(ah))]
        d.close()
    finally:
        os.unlink(p)


def test_primary_lossless():
    import numpy as np
    from PIL import Image
    p = _hdr_jpeg()
    try:
        with Image.open(p) as im:
            im.seek(0)
            a = np.asarray(im.convert("RGB"))
        prim = images._primary_jpeg(p)
        with Image.open(io.BytesIO(prim)) as im2:
            assert im2.format == "JPEG" and getattr(im2, "n_frames", 1) == 1
            assert np.array_equal(a, np.asarray(im2.convert("RGB")))
    finally:
        os.unlink(p)


def test_merge_brightens_only_highlights():
    import numpy as np
    from PIL import Image
    p = _hdr_jpeg()
    try:
        with Image.open(p) as im:
            im.seek(0)
            a = np.asarray(im.convert("L"), np.float32)
        b = np.asarray(Image.open(io.BytesIO(images.hdr_merged_jpeg(p))).convert("L"), np.float32)
        lit = (slice(250, 350), slice(250, 350))          # Karte hell -> Foto heller
        dark = (slice(600, 700), slice(450, 550))         # Karte dunkel -> fast unverändert
        assert b[lit].mean() > a[lit].mean() + 5
        assert abs(b[dark].mean() - a[dark].mean()) < 6
    finally:
        os.unlink(p)


def test_color_aux_never_merged():
    p = _hdr_jpeg("RGB")                                  # z. B. 3D-Kamera: zweites Farbbild
    try:
        info = images.hdr_aux_info(p)
        assert info and info["aux_mode"] == "RGB"
        d = images.images_to_document([p], 96, {"size": "aux", "merge": True})
        assert len(d) == 1
        d.close()
    finally:
        os.unlink(p)


def test_plain_jpeg_untouched():
    from PIL import Image
    fd, p = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    Image.new("RGB", (300, 300), "white").save(p, "JPEG", dpi=(300, 300))
    try:
        assert images.hdr_aux_info(p) is None
        d = images.images_to_document([p], 96)
        assert len(d) == 1 and _sizes(d) == [(25, 25)]
        d.close()
    finally:
        os.unlink(p)



def _doc_bytes(doc) -> bytes:
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def test_preflight_finds_and_repairs_two_page_hdr():
    """Unverändert geöffnet (2 Seiten) oder schon als PDF gespeichert: die Prüfung findet die
        graue Zusatzseite und repariert sie."""
    import pypdfium2 as pdfium
    from pdfdruck import preflight
    p = _hdr_jpeg()
    try:
        data = _doc_bytes(images.images_to_document([p], 96, {"keep": True}))
        info = images.hdr_aux_info(p)
    finally:
        os.unlink(p)
    rep = preflight.analyze(data, deep_layers=False, pdfium_parts=False)
    warn = [i for i in rep.issues if i.category == "image" and "HDR" in i.message]
    assert len(warn) == 1 and warn[0].severity == "warning" and warn[0].pages == [2], rep.issues
    assert rep.hdr and rep.hdr[0]["main"] == 0 and rep.hdr[0]["aux"] == 1
    aw, ah = images.hdr_size_mm(info, "aux")
    for kw, size in (({}, (round(aw), round(ah))), ({"size": "main"}, (51, 68)), ({"merge": True}, (round(aw), round(ah)))):
        out = preflight.remove_hdr_aux(data, **kw)
        d = pdfium.PdfDocument(out)
        assert len(d) == 1 and _sizes(d) == [size], (kw, _sizes(d))
        d.close()
        assert not [i for i in preflight.analyze(out, deep_layers=False, pdfium_parts=False).issues
                    if i.category == "image" and (i.severity == "warning" or "HDR" in i.message)]


def test_preflight_no_false_hdr():
    """Zwei Bildseiten, die nicht zusammengehören (anderes Seitenverhältnis bzw. beide farbig): kein Befund."""
    from PIL import Image
    from pdfdruck import preflight
    paths = []
    try:
        for size, mode in (((600, 800), "RGB"), ((400, 400), "L"), ((600, 800), "RGB"), ((300, 400), "RGB")):
            fd, q = tempfile.mkstemp(suffix=".jpg")
            os.close(fd)
            Image.new(mode, size, 128).save(q, "JPEG", dpi=(300, 300))
            paths.append(q)
        data = _doc_bytes(images.images_to_document(paths, 96))
        rep = preflight.analyze(data, deep_layers=False, pdfium_parts=False)
        assert rep.hdr == [] and not [i for i in rep.issues if i.category == "image" and "HDR" in i.message]
    finally:
        for q in paths:
            os.unlink(q)


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
