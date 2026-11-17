# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Soft proof of the page view: paper white/black, measured paper white, gamut and
ink coverage warning, CMYK path via the separation (section/rotation like pdfium), render process.
"""

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
os.environ.setdefault("PASSERMARK_LANG", "de")
import numpy as np
from PIL import Image

from pdfdruck import colorlab, proof

TMP = tempfile.mkdtemp(prefix="pm-proof-")


def is_fogra39(path: str) -> bool:
    """Is the test profile FOGRA39 (TeX Live, package texlive-base)? Without it Ghostscript's default CMYK profile is
    used, and checks that rely on FOGRA39's paper white or name are left out."""
    return "FOGRA39" in os.path.basename(path)


def cmyk_profile():
    """A CMYK print profile for testing: $PASSERMARK_TEST_CMYK if set, FOGRA39 from TeX Live, otherwise
    Ghostscript's default CMYK profile."""
    if os.environ.get("PASSERMARK_TEST_CMYK"):
        return os.environ["PASSERMARK_TEST_CMYK"]
    for p in (
        "/usr/share/texlive/texmf-dist/tex/generic/colorprofiles/FOGRA39L_coated.icc",
        "/usr/share/color/icc/ghostscript/default_cmyk.icc",
        "/usr/share/ghostscript/iccprofiles/default_cmyk.icc",
    ):
        if os.path.isfile(p):
            return p
    raise RuntimeError("kein CMYK-Profil zum Testen gefunden")


def img(*colors):
    im = Image.new("RGB", (len(colors), 1))
    for i, c in enumerate(colors):
        im.putpixel((i, 0), c)
    return im


def px(im):
    return [im.getpixel((i, 0)) for i in range(im.width)]


def test_variants():
    f = cmyk_profile()
    src = img((255, 255, 255), (0, 0, 0), (0, 255, 0), (128, 128, 128))
    base = px(proof.softproof_rgb(src, {"icc": f, "space": "CMYK"}))
    black = px(proof.softproof_rgb(src, {"icc": f, "space": "CMYK", "black": True}))
    paper = px(proof.softproof_rgb(src, {"icc": f, "space": "CMYK", "paper": True}))
    assert base[0] == (255, 255, 255) and sum(base[1]) < 30  # relative + BPC: paper white, black deep
    assert black[0] == (255, 255, 255) and sum(black[1]) > sum(base[1]) + 30  # black of the ink
    assert sum(paper[0]) < 3 * 252  # paper no longer pure white
    # measured white = profile white -> like absolute colorimetric (±2)
    pw = colorlab.profile_white(f)
    same = px(proof.softproof_rgb(src, {"icc": f, "space": "CMYK", "paper": True, "white": list(pw)}))
    assert all(abs(a - b) <= 3 for p, q in zip(same, paper) for a, b in zip(p, q)), (same, paper)
    # yellowish paper: white becomes yellowish (blue drops relative to red), all colours in the same ratio. Compare
    # ratios, not values: the measured white may be lighter than the profile's (Ghostscript's default profile)
    yel = px(proof.softproof_rgb(src, {"icc": f, "space": "CMYK", "paper": True, "white": [92, 1, 8]}))
    assert yel[0][2] < yel[0][0] - 10, yel
    assert yel[3][2] / max(yel[3][0], 1) < paper[3][2] / max(paper[3][0], 1), (yel, paper)


def test_warnings():
    f = cmyk_profile()
    src = img((0, 255, 0), (0, 0, 0), (128, 128, 128), (255, 255, 255))
    g = px(proof.softproof_rgb(src, {"icc": f, "space": "CMYK", "warn": "gamut"}))
    assert g[0] == proof.GAMUT_COLOR  # saturated RGB green: not printable
    assert g[1] != proof.GAMUT_COLOR and g[2] != proof.GAMUT_COLOR and g[3] == (255, 255, 255)
    t = px(proof.softproof_rgb(img((0, 0, 0), (255, 255, 255)), {"icc": f, "space": "CMYK", "warn": "tac", "tac": 250}))
    assert t[0] == proof.TAC_COLOR and t[1] == (255, 255, 255)  # deep black: ink coverage above 250 %


def test_spec_key_and_text():
    s = {"icc": "/x.icc", "space": "CMYK", "name": "Bilderdruck / FOGRA39", "paper": True, "white": [94.01, 0.5, -2]}
    assert proof.spec_key(s) != proof.spec_key(dict(s, white=[94, 0.5, -2.5]))
    t = proof.describe_spec(dict(s, warn="tac", tac=280))
    assert "Bilderdruck" in t and "gemessen" in t and "280" in t, t


def _page_pdf(path, w=200, h=100):
    import pikepdf

    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(w, h))
    pdf.pages[0].obj.Contents = pikepdf.Stream(pdf, b"0 0 1 rg 0 0 50 100 re f 1 0 0 rg 150 0 50 100 re f")
    pdf.save(path)
    return path


def test_separation_route(monkeypatch=None):
    """CMYK path (Ghostscript imitated): section and rotation match the whole page pixel for pixel."""
    import pypdfium2 as pdfium

    from pdfdruck import cmyk
    from pdfdruck import platform as _pl

    f = cmyk_profile()
    path = _page_pdf(os.path.join(TMP, "sep.pdf"))
    calls = []

    def fake_render(gs, src, page, dpi, device, extra, out):
        calls.append((device, dpi, extra))
        k = dpi / 72.0
        W, H = round(200 * k), round(100 * k)
        a = np.zeros((H, W, 4), np.uint8)
        a[:, : W // 4, 0] = 255  # cyan on the left
        a[:, -W // 4 :, 1] = 255  # magenta on the right
        if device == "tiff32nc":
            Image.fromarray(a, "CMYK").save(out, "TIFF")
        else:
            Image.new("RGB", (W, H), (255, 255, 255)).save(out)

    old = (cmyk._render, _pl.ghostscript)
    cmyk._render, _pl.ghostscript = fake_render, (lambda: "gs")
    proof._SEP_CACHE.clear()
    try:
        spec = {"icc": f, "space": "CMYK", "name": "t"}
        assert proof.can_separate(spec)
        doc = pdfium.PdfDocument(path)
        pg = doc[0]
        full = proof.proofed_render(pg, 2.0, 0, None, spec, path, 0)
        assert full.size == (400, 200), full.size
        assert full.getpixel((10, 100))[0] < 100 and full.getpixel((390, 100))[1] < 100  # Cyan / Magenta
        part = proof.proofed_render(pg, 2.0, 0, (20, 10, 100, 40), spec, path, 0)  # left, bottom, right, top
        assert part.size == (160, 100), part.size
        assert np.abs(np.asarray(part, int) - np.asarray(full, int)[80:180, 40:200]).mean() < 2
        rot = proof.proofed_render(pg, 2.0, 90, None, spec, path, 0)
        assert rot.size == (200, 400) and rot.getpixel((100, 10))[0] < 100  # rotated: cyan at the top
        assert "-dUseCropBox" in calls[0][2] and any(a.startswith("-sOutputICCProfile=") for a in calls[0][2])
        assert calls[0][1] == 288  # small page: separated twice as fine (smooth text), then scaled down
        n = len(calls)
        proof.proofed_render(pg, 2.0, 0, None, spec, path, 0)
        assert len(calls) == n  # cached
        big = proof.proofed_render(pg, 8.0, 0, (0, 0, 150, 50), spec, path, 0)
        assert calls[-1][1] == 2 * proof.PROOF_MAX_DPI and big.size == (400, 400), big.size  # at most 300 dpi (x2)
        pg.close()
        doc.close()
    finally:
        cmyk._render, _pl.ghostscript = old
        proof._SEP_CACHE.clear()


def test_supersample_factor():
    """Finer separation only while the page stays small enough (large plans stay fast)."""
    assert proof.supersample_factor(595, 842, 144) == 2.0  # A4 at 144 dpi: 8 Mpx at double resolution
    assert proof.supersample_factor(1800, 1125, 216) == 1.0  # large page: would be far too many pixels
    f = proof.supersample_factor(1800, 1125, 144)
    assert 1.3 <= f < 2.0, f
    k = f * 144 / 72
    assert 1800 * 1125 * k * k <= proof.PROOF_SUPERSAMPLE_PIXELS * 1.01


def test_render_server_proof():
    from test_renderproc import Server, _arr

    f = cmyk_profile()
    path = _page_pdf(os.path.join(TMP, "srv.pdf"))
    s = Server()
    try:
        h, _ = s(op="open", id=1, doc="x", path=path)
        assert h["ok"]
        h, d = s(op="render", id=2, doc="x", page=0, scale=1.0)
        plain = _arr(h, d)
        spec = {"icc": f, "space": "CMYK", "name": "t", "paper": True}
        h, d = s(op="render", id=3, doc="x", page=0, scale=1.0, proof=spec)
        assert h["ok"] and h["fmt"] == "bgrx", h
        assert min(d[3::4]) == 255  # 4th byte opaque: Qt reads it as alpha (Format_RGB32), 0 = page turns white
        pr = _arr(h, d)
        assert pr.shape == plain.shape
        assert pr[50, 100].sum() < plain[50, 100].sum() - 6  # paper white: the white centre gets darker
        h, d = s(op="render", id=4, doc="x", page=0, scale=1.0, proof=dict(spec, icc="/gibts/nicht.icc"))
        assert h["ok"]  # broken profile: without soft proof, no crash
    finally:
        s.close()


if __name__ == "__main__":
    for k, fn in list(globals().items()):
        if k.startswith("test_"):
            fn()
            print("ok", k)
