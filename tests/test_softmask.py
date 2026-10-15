# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Transparente Verläufe (Soft-Maske im Muster, wie Chrome/Canva sie exportieren):
    Erkennung in der Prüfung, Reparatur in deckende Bilder, Nachweis per RIP-Simulation."""
import io
import os
import sys
os.environ.setdefault("PASSERMARK_LANG", "de")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pdfdruck import preflight, softmask


def _chrome_like_pdf(in_form: bool = False) -> bytes:
    """Rotes Bild, darüber ein schwarzer Verlauf, der über eine Soft-Maske von durchsichtig (links)
        nach deckend (rechts) läuft, darüber Text. Ohne Soft-Maske: alles schwarz."""
    import pikepdf
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(300, 300))
    page = pdf.pages[0]
    img = pikepdf.Stream(pdf, bytes([220, 30, 30]) * 4, Type=pikepdf.Name.XObject, Subtype=pikepdf.Name.Image,
                         Width=2, Height=2, ColorSpace=pikepdf.Name.DeviceRGB, BitsPerComponent=8)
    alpha = pikepdf.Dictionary(ShadingType=2, ColorSpace=pikepdf.Name.DeviceGray, Coords=[0, 0, 300, 0],
                               Function=pikepdf.Dictionary(FunctionType=2, Domain=[0, 1], C0=[0], C1=[1], N=1),
                               Extend=[True, True])
    mask_form = pikepdf.Stream(pdf, b"/A sh", Type=pikepdf.Name.XObject, Subtype=pikepdf.Name.Form,
                               BBox=[0, 0, 300, 300],
                               Group=pikepdf.Dictionary(S=pikepdf.Name.Transparency, CS=pikepdf.Name.DeviceGray),
                               Resources=pikepdf.Dictionary(Shading=pikepdf.Dictionary(A=alpha)))
    gs = pikepdf.Dictionary(Type=pikepdf.Name.ExtGState,
                            SMask=pikepdf.Dictionary(Type=pikepdf.Name.Mask, S=pikepdf.Name.Luminosity, G=mask_form))
    pat = pikepdf.Stream(pdf, b"/G1 gs 0 0 0 rg 0 0 300 300 re f", Type=pikepdf.Name.Pattern, PatternType=1,
                         PaintType=1, TilingType=1, BBox=[0, 0, 300, 300], XStep=300, YStep=300,
                         Resources=pikepdf.Dictionary(ExtGState=pikepdf.Dictionary(G1=gs)))
    font = pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica)
    body = (b"q 200 0 0 200 50 50 cm /Im1 Do Q\n/Pattern cs /P1 scn 0 0 300 300 re f\n"
            b"0 0 1 rg BT /F1 20 Tf 60 20 Td (Oben drauf) Tj ET")
    res = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im1=img), Pattern=pikepdf.Dictionary(P1=pat),
                             Font=pikepdf.Dictionary(F1=font))
    if in_form:                                   # wie Chrome: alles in einem Formular mit Transparenzgruppe
        form = pikepdf.Stream(pdf, body, Type=pikepdf.Name.XObject, Subtype=pikepdf.Name.Form, BBox=[0, 0, 300, 300],
                              Group=pikepdf.Dictionary(S=pikepdf.Name.Transparency), Resources=res)
        page.obj.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Fm=form))
        page.obj.Contents = pikepdf.Stream(pdf, b"q 1 0 0 1 0 0 cm /Fm Do Q")
    else:
        page.obj.Resources = res
        page.obj.Contents = pikepdf.Stream(pdf, body)
    buf = io.BytesIO()
    pdf.save(buf)
    return buf.getvalue()


def _render(data, scale=0.5):
    import numpy as np
    import pypdfium2 as pdfium
    d = pdfium.PdfDocument(data)
    a = np.asarray(d[0].render(scale=scale).to_pil().convert("RGB")).astype(int)
    d.close()
    return a


def _px(a, x, y, scale=0.5):
    return tuple(a[int((300 - y) * scale), int(x * scale)])


def test_detect_warning():
    for in_form in (False, True):
        rep = preflight.analyze(_chrome_like_pdf(in_form), deep_layers=False, pdfium_parts=False)
        warn = [i for i in rep.issues if i.category == "transparency" and i.severity == "warning"]
        assert warn and warn[0].pages == [1], (in_form, rep.issues)
        assert softmask.count_softmask_paints(_chrome_like_pdf(in_form)) == {1: 1}


def test_rip_simulation_shows_the_problem():
    data = _chrome_like_pdf()
    a, b = _render(data), _render(softmask.rip_simulation(data))
    assert _px(a, 70, 150)[0] > 150, "links: Bild rot durch (Verlauf durchsichtig)"
    assert max(_px(b, 70, 150)) < 40, "RIP ohne Soft-Maske: schwarz über dem Bild"


def test_flatten_fixes_and_keeps_look():
    import numpy as np
    for in_form in (False, True):
        data = _chrome_like_pdf(in_form)
        new, notes = softmask.flatten_softmask_paints(data, dpi=150)
        assert notes and new != data
        a, f, fs = _render(data), _render(new), _render(softmask.rip_simulation(new))
        assert (np.abs(f - fs).max(2) > 24).sum() == 0, "nach der Reparatur egal, ob der RIP Soft-Masken kann"
        assert np.abs(a - f).max(2).mean() < 3, "Aussehen bleibt"
        assert _px(f, 70, 150)[0] > 150, "Bild links weiter sichtbar"
        assert softmask.count_softmask_paints(new) == {}
        rep = preflight.analyze(new, deep_layers=False, pdfium_parts=False)
        assert not [i for i in rep.issues if i.severity == "warning" and i.category == "transparency"]
        import pypdfium2 as pdfium
        from pdfdruck import editing
        d = pdfium.PdfDocument(new)
        if not in_form:
            assert [L.text for L in editing.text_lines(d, 0)] == ["Oben drauf"], "Text darüber bleibt Text"
        d.close()


def test_untouched_without_gradients():
    import pikepdf
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(100, 100))
    pdf.pages[0].obj.Contents = pikepdf.Stream(pdf, b"1 0 0 rg 10 10 50 50 re f")
    buf = io.BytesIO()
    pdf.save(buf)
    data = buf.getvalue()
    out, notes = softmask.flatten_softmask_paints(data)
    assert out == data and notes == []


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
