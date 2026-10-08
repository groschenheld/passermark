# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Preflight: Analyse (Schriften, Ebenen, Transparenz) und Ebenen-Reparaturen."""
import io, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("PASSERMARK_LANG", "de")
import numpy as np
import pikepdf
import pypdfium2 as pdfium
from pdfdruck import preflight


def problem_pdf() -> bytes:
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(595, 842))
    page = pdf.pages[0]
    o1 = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.OCG, Name=pikepdf.String("Bemaßung")))
    o2 = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.OCG, Name=pikepdf.String("Hilfslinien"),
                                              Usage=pikepdf.Dictionary(Print=pikepdf.Dictionary(PrintState=pikepdf.Name.OFF))))
    o3 = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.OCG, Name=pikepdf.String("Verrutscht")))
    pdf.Root.OCProperties = pikepdf.Dictionary(OCGs=pikepdf.Array([o1, o2, o3]), D=pikepdf.Dictionary(
        ON=pikepdf.Array([o2, o3]), OFF=pikepdf.Array([o1]), Order=pikepdf.Array([o1, o2, o3])))
    arial = pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.TrueType, BaseFont=pikepdf.Name("/ArialMT"),
                               FirstChar=32, LastChar=126, Widths=pikepdf.Array([556] * 95),
                               Encoding=pikepdf.Name.WinAnsiEncoding,
                               FontDescriptor=pdf.make_indirect(pikepdf.Dictionary(
                                   Type=pikepdf.Name.FontDescriptor, FontName=pikepdf.Name("/ArialMT"), Flags=32,
                                   FontBBox=pikepdf.Array([-665, -325, 2000, 1040]), ItalicAngle=0, Ascent=905,
                                   Descent=-212, CapHeight=716, StemV=80)))
    helv = pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica)
    page.obj.Resources = pikepdf.Dictionary(
        Font=pikepdf.Dictionary(F1=pdf.make_indirect(arial), F2=pdf.make_indirect(helv)),
        Properties=pikepdf.Dictionary(L1=o1, L2=o2, L3=o3),
        ExtGState=pikepdf.Dictionary(GS1=pikepdf.Dictionary(Type=pikepdf.Name.ExtGState, ca=0.5)))
    content = b"""q 0 0 0 rg 50 700 200 50 re f Q
/OC /L1 BDC 1 0 0 rg 50 600 200 50 re f EMC
/OC /L2 BDC 0 0 1 rg 50 500 200 50 re f EMC
/OC /L3 BDC 0 1 0 rg 700 300 200 200 re f EMC
BT /F1 24 Tf 50 400 Td (Hallo Arial) Tj ET
BT /F2 12 Tf 50 380 Td (Helvetica) Tj ET
q /GS1 gs 0 0 1 rg 300 100 100 100 re f Q
"""
    page.obj.Contents = pikepdf.Stream(pdf, content)
    buf = io.BytesIO(); pdf.save(buf)
    return buf.getvalue()


def px(data, x, y, scale=1.0):
    img = pdfium.PdfDocument(data)[0].render(scale=scale).to_pil()
    return img.getpixel((int(x * scale), int((842 - y) * scale)))


def test_analyze():
    rep = preflight.analyze(problem_pdf())
    names = {f.name: f for f in rep.fonts}
    assert names["ArialMT"].status == "missing" and names["Helvetica"].status == "std14"
    L = {l.name: l for l in rep.layers}
    assert not L["Bemaßung"].view_on and L["Hilfslinien"].view_on and L["Hilfslinien"].print_on is False
    assert L["Verrutscht"].outside_pct is not None and L["Verrutscht"].outside_pct > 50
    assert all(l.pages == {1} for l in rep.layers)
    assert "alpha" in rep.transparency[1]
    sev = [(i.severity, i.category) for i in rep.issues]
    assert ("error", "font") in sev and sev.count(("warning", "layer")) >= 3
    assert "ArialMT" in preflight.report_text(rep)


def test_flatten_layers_print_state():
    data = problem_pdf()
    assert px(data, 100, 625)[:3] == (255, 255, 255)          # Bemaßung (aus) ist ausgeblendet
    out = preflight.flatten_layers(data)
    pk = pikepdf.open(io.BytesIO(out))
    assert "/OCProperties" not in pk.Root
    content = pk.pages[0].Contents.read_bytes()
    assert b"/OC" not in content and b"BDC" not in content
    assert b"1 0 0 rg" not in content                         # Bemaßung entfernt
    assert b"0 0 1 rg 50 500" not in content                  # Hilfslinien: Druck aus -> entfernt
    assert b"0 1 0 rg" in content                             # Verrutscht: sichtbar -> bleibt (ohne Marker)
    assert px(out, 100, 725)[:3] == (0, 0, 0)                 # Grundinhalt bleibt


def test_remove_layer_keeps_others():
    data = problem_pdf()
    key = next(l.key for l in preflight.analyze(data, deep_layers=False).layers if l.name == "Verrutscht")
    out = preflight.remove_layers(data, {key})
    rep = preflight.analyze(out, deep_layers=False)
    assert sorted(l.name for l in rep.layers) == ["Bemaßung", "Hilfslinien"]
    pk = pikepdf.open(io.BytesIO(out)); content = pk.pages[0].Contents.read_bytes()
    assert b"0 1 0 rg" not in content and b"/OC /L1 BDC" in content


def test_set_layer_states():
    data = problem_pdf()
    rep = preflight.analyze(data, deep_layers=False)
    st = {l.key: (True, True) for l in rep.layers}
    out = preflight.set_layer_states(data, st)
    r = px(out, 100, 625)[:3]
    assert r[0] > 200 and r[1] < 60                           # Bemaßung jetzt sichtbar (rot)
    rep2 = preflight.analyze(out, deep_layers=False)
    assert all(l.view_on and l.print_on for l in rep2.layers)


def test_font_name_normalize():
    assert preflight._norm("ABCDEF+Arial-BoldMT") == ("arial", True, False)
    assert preflight._norm("TimesNewRomanPS-ItalicMT") == ("timesnewroman", False, True)
    assert preflight._norm("Calibri,Bold") == ("calibri", True, False)


def test_download_alias_and_suggestions(tmp_dir="/tmp/_pm_fonts"):
    """fontsource.org nachgebaut: Arial -> Arimo; unbekannter Name -> Vorschläge statt nur 404."""
    import json, shutil, urllib.error, urllib.request
    shutil.rmtree(tmp_dir, ignore_errors=True)
    assert preflight.free_alternative("ArialMT") == "Arimo"
    assert preflight.free_alternative("Calibri-Bold") == "Carlito"
    assert preflight.free_alternative("TimesNewRomanPSMT") == "Tinos"
    assert preflight.free_alternative("Roboto") == ""
    calls = []

    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def fake_urlopen(req, timeout=0, **kw):
        url = req.full_url if hasattr(req, "full_url") else req
        calls.append(url)
        if url.endswith("/fonts/arimo"):
            v = {"latin": {"url": {"ttf": "https://cdn.test/arimo-400.ttf"}}}
            return Resp(json.dumps({"family": "Arimo", "variants": {"400": {"normal": v}}}).encode())
        if url.endswith("/fonts"):
            return Resp(json.dumps([{"family": "Roboto"}, {"family": "Roboto Slab"}, {"family": "Arimo"}]).encode())
        if url.startswith("https://cdn.test/"):
            return Resp(b"\x00\x01\x00\x00fake-ttf")
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    orig, orig_dir = urllib.request.urlopen, preflight.user_font_dir
    urllib.request.urlopen = fake_urlopen
    preflight.user_font_dir = lambda: tmp_dir
    try:
        paths, used = preflight.download_font("arial")
        assert used == "Arimo" and len(paths) == 1 and os.path.exists(paths[0])
        assert calls[0].endswith("/fonts/arimo")
        try:
            preflight.download_font("Robotto")
            assert False
        except preflight.FontNotFound as e:
            assert "Roboto" in e.suggestions and "Roboto" in str(e)
    finally:
        urllib.request.urlopen, preflight.user_font_dir = orig, orig_dir


def test_testfile_findings():
    """Das ausgelieferte Test-PDF: alle Schriftfälle richtig eingeordnet."""
    path = "/mnt/user-data/outputs/passermark-test-fehlerhaft.pdf"
    if not os.path.exists(path):
        return
    rep = preflight.analyze(open(path, "rb").read())
    f = {x.name: x for x in rep.fonts}
    assert f["WeirdSymbolFont"].encoding == "private" and not f["WeirdSymbolFont"].suggestion
    assert f["MS-Gothic"].cid and not f["MS-Gothic"].suggestion
    assert "Ausweichschrift" in f["ISOCPEUR"].suggestion_name or "osifont" in f["ISOCPEUR"].suggestion_name
    assert f["Calibri-Bold"].suggestion_name.startswith("Carlito")


def test_download_cdn_fallback(tmp_dir="/tmp/_pm_fonts2"):
    """API nicht erreichbar -> Dateien direkt vom fontsource-CDN."""
    import shutil, urllib.error, urllib.request
    shutil.rmtree(tmp_dir, ignore_errors=True)

    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def fake(req, timeout=0, **kw):
        url = req.full_url if hasattr(req, "full_url") else req
        if "api.fontsource.org" in url:
            raise urllib.error.URLError("API down")
        if url.endswith("latin-400-normal.ttf") or url.endswith("latin-700-normal.ttf"):
            return Resp(b"ttf")
        raise urllib.error.HTTPError(url, 404, "nf", {}, None)
    orig, od = urllib.request.urlopen, preflight.user_font_dir
    urllib.request.urlopen, preflight.user_font_dir = fake, (lambda: tmp_dir)
    try:
        paths, used = preflight.download_font("Calibri")
        assert used == "Carlito" and len(paths) == 2 and all("carlito" in p for p in paths)
    finally:
        urllib.request.urlopen, preflight.user_font_dir = orig, od


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("ok", k)
