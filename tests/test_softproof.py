# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Softproof der Seitenansicht (1.16): Papierweiß/Schwarz, gemessenes Papierweiß, Farbumfang- und
    Farbauftrag-Warnung, CMYK-Weg über die Separation (Ausschnitt/Drehung wie pdfium), Render-Prozess."""
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


def cmyk_profile():
    """Ein CMYK-Druckprofil zum Testen: FOGRA39 aus TeX Live, sonst ein eigenes aus LittleCMS (Pillow)."""
    for p in ("/usr/share/texlive/texmf-dist/tex/generic/colorprofiles/FOGRA39L_coated.icc",
              "/usr/share/color/icc/ghostscript/default_cmyk.icc", "/usr/share/ghostscript/iccprofiles/default_cmyk.icc"):
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
    assert base[0] == (255, 255, 255) and sum(base[1]) < 30           # relativ + BPC: Papier weiß, Schwarz tief
    assert black[0] == (255, 255, 255) and sum(black[1]) > sum(base[1]) + 30   # Schwarz der Druckfarbe
    assert sum(paper[0]) < 3 * 252                                       # Papier nicht mehr reinweiß
    # gemessenes Weiß = Profilweiß -> wie absolut farbmetrisch (±2)
    pw = colorlab.profile_white(f)
    same = px(proof.softproof_rgb(src, {"icc": f, "space": "CMYK", "paper": True, "white": list(pw)}))
    assert all(abs(a - b) <= 3 for p, q in zip(same, paper) for a, b in zip(p, q)), (same, paper)
    # gelbliches Papier: Weiß wird gelblich (blau sinkt), alle Farben im selben Verhältnis
    yel = px(proof.softproof_rgb(src, {"icc": f, "space": "CMYK", "paper": True, "white": [92, 1, 8]}))
    assert yel[0][2] < yel[0][0] - 10 and yel[3][2] < paper[3][2], yel


def test_warnings():
    f = cmyk_profile()
    src = img((0, 255, 0), (0, 0, 0), (128, 128, 128), (255, 255, 255))
    g = px(proof.softproof_rgb(src, {"icc": f, "space": "CMYK", "warn": "gamut"}))
    assert g[0] == proof.GAMUT_COLOR                         # sattes RGB-Grün: nicht druckbar
    assert g[1] != proof.GAMUT_COLOR and g[2] != proof.GAMUT_COLOR and g[3] == (255, 255, 255)
    t = px(proof.softproof_rgb(img((0, 0, 0), (255, 255, 255)), {"icc": f, "space": "CMYK", "warn": "tac", "tac": 250}))
    assert t[0] == proof.TAC_COLOR and t[1] == (255, 255, 255)     # Tiefschwarz: Farbauftrag über 250 %


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
    """CMYK-Weg (Ghostscript nachgestellt): Ausschnitt und Drehung passen pixelgenau zur ganzen Seite."""
    import pypdfium2 as pdfium
    from pdfdruck import cmyk, platform as _pl
    f = cmyk_profile()
    path = _page_pdf(os.path.join(TMP, "sep.pdf"))
    calls = []

    def fake_render(gs, src, page, dpi, device, extra, out):
        calls.append((device, dpi, extra))
        k = dpi / 72.0
        W, H = round(200 * k), round(100 * k)
        a = np.zeros((H, W, 4), np.uint8)
        a[:, : W // 4, 0] = 255                                    # links Cyan
        a[:, -W // 4:, 1] = 255                                    # rechts Magenta
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
        assert full.getpixel((10, 100))[0] < 100 and full.getpixel((390, 100))[1] < 100      # Cyan / Magenta
        part = proof.proofed_render(pg, 2.0, 0, (20, 10, 100, 40), spec, path, 0)   # links, unten, rechts, oben
        assert part.size == (160, 100), part.size
        assert np.abs(np.asarray(part, int) - np.asarray(full, int)[80:180, 40:200]).mean() < 2
        rot = proof.proofed_render(pg, 2.0, 90, None, spec, path, 0)
        assert rot.size == (200, 400) and rot.getpixel((100, 10))[0] < 100      # gedreht: Cyan oben
        assert "-dUseCropBox" in calls[0][2] and any(a.startswith("-sOutputICCProfile=") for a in calls[0][2])
        n = len(calls)
        proof.proofed_render(pg, 2.0, 0, None, spec, path, 0)
        assert len(calls) == n                                   # zwischengespeichert
        big = proof.proofed_render(pg, 8.0, 0, (0, 0, 150, 50), spec, path, 0)
        assert calls[-1][1] == proof.PROOF_MAX_DPI and big.size == (400, 400), big.size   # höchstens 300 dpi
        pg.close()
        doc.close()
    finally:
        cmyk._render, _pl.ghostscript = old
        proof._SEP_CACHE.clear()


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
        pr = _arr(h, d)
        assert pr.shape == plain.shape
        assert pr[50, 100].sum() < plain[50, 100].sum() - 6       # Papierweiß: weiße Mitte wird dunkler
        h, d = s(op="render", id=4, doc="x", page=0, scale=1.0, proof=dict(spec, icc="/gibts/nicht.icc"))
        assert h["ok"]                                            # kaputtes Profil: ohne Softproof, kein Absturz
    finally:
        s.close()


if __name__ == "__main__":
    for k, fn in list(globals().items()):
        if k.startswith("test_"):
            fn()
            print("ok", k)
