# SPDX-License-Identifier: GPL-3.0-or-later
"""Windows-Druckweg ohne Windows: win32gui/win32print/gdi32 nachgebaut (tests/_winstub), der „Treiber“ zeichnet
alle Streifen auf eine Leinwand. Prüft Raster (lückenlos, pixelgenau), JPEG, PostScript-Wahl und Fehlerfall."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "_winstub"))
import numpy as np
import pypdfium2 as pdfium
import pypdfium2.raw as r
import fakewin
from pdfdruck import printers  # noqa: F401  zuerst laden: unter Windows bindet printers.py printers_win ein
from pdfdruck import printers_win as pw

SAMPLE = os.path.join(HERE, "sample.pdf")
_ORIG_DEVMODE = pw._devmode_for_job


def _setup(**kw):
    g = fakewin.FakeGDI(**kw)
    pw._gdi32 = lambda: g
    pw._devmode_for_job = lambda *a: None
    w, h = pdfium.PdfDocument(SAMPLE).get_page_size(0)
    fakewin.install(g, (int(round(w * g.dpi / 72)), int(round(h * g.dpi / 72))))
    return g


def test_raster_bands_exact_and_jpeg_smaller():
    ref = pdfium.PdfDocument(SAMPLE)[0].render(scale=150 / 72, fill_color=(255, 255, 255, 255)).to_pil().convert("RGB")
    sizes = {}
    for jpeg in (False, True):
        g = _setup(dpi=300, jpeg=jpeg)
        pw.print_settings = lambda jpeg=jpeg: ("raster_jpeg" if jpeg else "auto", 300)
        pw.BAND_BYTES = 2 * 1024 * 1024
        assert pw.print_pdf("T", SAMPLE, "t", {}, 1, True) == 42
        bands = [c for c in g.calls if c[0] == "band"]
        assert len(bands) > len(g.pages)                                  # wirklich in Streifen
        for a, b in zip(bands, bands[1:]):
            assert b[1] in (a[1] + a[2], 0)                               # lückenlos
        diff = np.abs(np.asarray(g.pages[0].resize(ref.size), int) - np.asarray(ref, int)).mean()
        assert diff < 6, diff
        assert all(c[3] == (4 if jpeg else 0) for c in bands)
        sizes[jpeg] = g.bytes_sent
    assert sizes[True] < sizes[False] / 3


def test_postscript_driver_uses_pdfium_ps_and_resets():
    g = _setup(dpi=600, ps=True)
    log = []
    had = (hasattr(r, "FPDF_SetPrintMode"), hasattr(r, "FPDF_RenderPage"))
    r.FPDF_SetPrintMode = lambda m: log.append(("mode", m))
    r.FPDF_RenderPage = lambda *a: log.append(("render",))
    try:
        pw.print_settings = lambda: ("postscript", 0)
        pw.print_pdf("PS", SAMPLE, "t", {}, 1, True)
        assert [x for x in log if x[0] == "mode"] == [("mode", 3), ("mode", 0)]
        assert not any(c[0] == "band" for c in g.calls)
    finally:
        if not had[0]: del r.FPDF_SetPrintMode
        if not had[1]: del r.FPDF_RenderPage


def test_error_aborts_job():
    g = _setup(dpi=300)
    g.StretchDIBits = lambda *a: 0
    pw.print_settings = lambda: ("raster", 0)
    try:
        pw.print_pdf("X", SAMPLE, "t", {}, 1, True)
        assert False
    except RuntimeError:
        pass
    assert ("abort",) in g.calls


def test_auto_is_plain_raster_even_if_driver_claims_more():
    """Automatisch: nie PostScript/JPEG – die führten bei manchen Treibern zu leeren Blättern."""
    g = _setup(dpi=300, ps=True, jpeg=True)
    pw.print_settings = lambda: ("auto", 0)
    pw.BAND_BYTES = 24 * 1024 * 1024
    pw.print_pdf("Canon", SAMPLE, "t", {}, 1, True)
    bands = [c for c in g.calls if c[0] == "band"]
    assert bands and all(c[3] == 0 for c in bands)
    assert pw.LAST_INFO["mode"] == "raster" and pw.LAST_INFO["ps"] and pw.LAST_INFO["jpeg"]
    assert pw.LAST_INFO["raster_dpi"] == 300 and pw.LAST_INFO["pages"] == len(pdfium.PdfDocument(SAMPLE))


def test_job_log_written():
    import tempfile
    from pdfdruck import platform as pl
    d = tempfile.mkdtemp()
    old = pl.user_log_dir
    pl.user_log_dir = lambda: d
    try:
        _setup(dpi=300)
        pw.print_settings = lambda: ("auto", 0)
        pw.print_pdf("Büro-Drucker", SAMPLE, "t", {}, 1, True)
        g = _setup(dpi=300); g.StretchDIBits = lambda *a: 0
        try:
            pw.print_pdf("Büro-Drucker", SAMPLE, "t", {}, 1, True)
        except RuntimeError:
            pass
    finally:
        pl.user_log_dir = old
    lines = open(os.path.join(d, "druck-windows.log"), encoding="utf-8").read().splitlines()
    assert len(lines) == 2 and '"mode": "raster"' in lines[0] and "Büro-Drucker" in lines[0] and "error" in lines[1]


def test_test_print_all_modes():
    g = _setup(dpi=300, ps=False, jpeg=True)
    pw.print_settings = lambda: ("auto", 0)
    had = hasattr(r, "FPDF_RenderPage")
    r.FPDF_RenderPage = lambda *a: g.calls.append(("vector",))
    try:
        res = dict(pw.test_print("T"))
    finally:
        if not had: del r.FPDF_RenderPage
    assert list(res) == [lab for _m, lab in pw.TEST_MODES]
    assert res["Raster"] == "ok" and res["Raster + JPEG"] == "ok" and res["Vektor (GDI)"] == "ok"
    assert "PostScript" in res["PostScript"] and res["PostScript"] != "ok"    # Treiber kann es nicht -> gemeldet
    assert len(g.pages) == 4 and ("vector",) in g.calls


def test_custom_paper_size_devmode():
    """Sonderformat: DMPAPER_USER mit Breite/Länge in 0,1 mm; normale Formate wie bisher."""
    class DM:
        Fields = 0
    pw.devmode_from_str = lambda printer, s: DM()
    dm = _ORIG_DEVMODE("T", {"PageSize": printers.custom_value(330, 1000)}, 1, True)
    assert dm.PaperSize == 256 and dm.PaperWidth == 3300 and dm.PaperLength == 10000
    assert dm.Fields & pw.DM_PAPERWIDTH and dm.Fields & pw.DM_PAPERLENGTH and dm.Fields & pw.DM_PAPERSIZE
    dm = _ORIG_DEVMODE("T", {"PageSize": "9"}, 1, True)
    assert dm.PaperSize == 9 and not hasattr(dm, "PaperWidth")


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("ok", k)
