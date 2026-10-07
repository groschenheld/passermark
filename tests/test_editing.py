# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Bearbeiten-Modus: Textzeilen und Ebenen."""
import io, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("PASSERMARK_LANG", "de")
import pypdfium2 as pdfium
from pdfdruck import editing, preflight
import test_preflight as tp

MM = 72 / 25.4


def plan():
    """Plan mit Ebenen + Text (aus dem Preflight-Test, Seite A4)."""
    return tp.problem_pdf()


def test_text_lines_edit_and_font():
    d = pdfium.PdfDocument(plan())
    lines = editing.text_lines(d, 0)
    L = next(l for l in lines if l.text.startswith("Hallo"))
    assert L.font == "ArialMT" and abs(L.size - 24) < 0.1
    assert editing.line_at(lines, (L.bbox[0] + L.bbox[2]) / 2, (L.bbox[1] + L.bbox[3]) / 2) is L
    editing.edit_line(d, 0, L, "Hallo Passermark")
    buf = io.BytesIO(); d.save(buf); d2 = pdfium.PdfDocument(buf.getvalue())
    L2 = next(l for l in editing.text_lines(d2, 0) if l.text.startswith("Hallo"))
    assert L2.text == "Hallo Passermark" and L2.font == "ArialMT"
    editing.edit_line(d2, 0, L2, "Neue Schrift", font=("std", "Times-Bold"), size=30)
    buf = io.BytesIO(); d2.save(buf); d3 = pdfium.PdfDocument(buf.getvalue())
    L3 = next(l for l in editing.text_lines(d3, 0) if l.text == "Neue Schrift")
    assert "Times" in L3.font and abs(L3.size - 30) < 0.1
    assert abs(L3.bbox[0] - L.bbox[0]) < 2                       # gleiche Position
    editing.delete_line(d3, 0, L3)
    assert not any(l.text == "Neue Schrift" for l in editing.text_lines(d3, 0))


def test_layer_map_click_transform_replace():
    data = plan()
    K = {L.name: L.key for L in preflight.analyze(data, deep_layers=False).layers}
    lm = editing.layer_map(data, 0)
    b = lm.boxes[K["Verrutscht"]]
    assert b[0] > 595                                             # liegt rechts neben der Seite
    assert K["Bemaßung"] in editing.layers_at(lm, 150, 625)       # rotes Rechteck der Bemaßung
    out = editing.transform_layer(data, K["Verrutscht"], dx=-500)
    b2 = editing.layer_map(out, 0, [K["Verrutscht"]]).boxes[K["Verrutscht"]]
    assert abs(b2[0] - (b[0] - 500)) < 8
    out = editing.transform_layer(data, K["Bemaßung"], scale=0.5, origin=(150, 625))
    bb = editing.layer_map(out, 0, [K["Bemaßung"]]).boxes[K["Bemaßung"]]
    assert abs((bb[2] - bb[0]) - 100) < 8                         # 200 pt breit -> 100 pt
    from reportlab.pdfgen import canvas
    c = canvas.Canvas("/tmp/_ers.pdf", pagesize=(100, 100)); c.rect(0, 0, 100, 100, fill=1); c.showPage(); c.save()
    out = editing.replace_layer(data, K["Bemaßung"], 0, open("/tmp/_ers.pdf", "rb").read(), 0, box=(300, 300, 400, 400))
    bb = editing.layer_map(out, 0, [K["Bemaßung"]]).boxes[K["Bemaßung"]]
    assert abs(bb[0] - 300) < 8 and abs(bb[2] - 400) < 8
    hidden = editing.set_visible(out, K["Bemaßung"], False)
    assert not next(L for L in preflight.analyze(hidden, deep_layers=False).layers if L.key == K["Bemaßung"]).view_on


def chrome_like() -> bytes:
    """Wie ein Chrome-/Skia-PDF: Type3-Schrift, gespiegeltes Koordinatensystem ohne q/Q, mehrere Zeilen in
    einem Textblock, jeder Buchstabe einzeln positioniert. pdfium kann solche Seiten nicht neu schreiben."""
    import pikepdf
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(595, 842))
    procs = pikepdf.Dictionary()
    for ch in "ABC":
        procs[pikepdf.Name("/" + ch)] = pikepdf.Stream(pdf, b"600 0 0 0 500 700 d1 50 0 450 700 re f")
    t3 = pdf.make_indirect(pikepdf.Dictionary(
        Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type3, FontBBox=[0, 0, 500, 700], FontMatrix=[0.001, 0, 0, 0.001, 0, 0],
        CharProcs=procs, Encoding=pikepdf.Dictionary(Type=pikepdf.Name.Encoding, Differences=[65, pikepdf.Name.A, pikepdf.Name.B, pikepdf.Name.C]),
        FirstChar=65, LastChar=67, Widths=[600, 600, 600], Resources=pikepdf.Dictionary()))
    page = pdf.pages[0]
    page.obj.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(T3=t3))
    page.obj.Contents = pikepdf.Stream(pdf, b"""0.5 0 0 -0.5 0 842 cm
0 0 0 rg
BT /T3 40 Tf 1 0 0 -1 100 200 Tm (A) Tj 30 0 Td (B) Tj 30 0 Td (C) Tj
-60 -150 Td (C) Tj 30 0 Td (A) Tj 30 0 Td (B) Tj 30 0 Td (A) Tj ET
0 0 1 rg 100 600 400 20 re f
""")
    buf = io.BytesIO(); pdf.save(buf)
    return buf.getvalue()


def test_chrome_like_type3_edits():
    data = chrome_like()
    lines = editing.text_lines(pdfium.PdfDocument(data), 0)
    assert [l.text for l in lines] == ["ABC", "CABA"], [l.text for l in lines]
    L, other = lines
    # Verschieben/Skalieren: Zeile wird aus dem gemeinsamen Textblock herausgelöst, in Seitenkoordinaten
    new = editing.transform_line_blocks(data, 0, L, 1.0, 40, -30)
    assert new is not None
    after = editing.text_lines(pdfium.PdfDocument(new), 0)
    moved = next(l for l in after if l.text == "ABC")
    still = next(l for l in after if l.text == "CABA")
    assert abs(moved.bbox[0] - (L.bbox[0] + 40)) < 1 and abs(moved.bbox[1] - (L.bbox[1] - 30)) < 1
    assert abs(still.bbox[0] - other.bbox[0]) < 0.5 and abs(still.bbox[1] - other.bbox[1]) < 0.5   # Rest bleibt
    assert editing.verify_edit(data, new, 0, [L.bbox, moved.bbox]) == ""
    big = editing.transform_line_blocks(data, 0, L, 2.0, 0, 0, (L.bbox[0], L.bbox[1]))
    b2 = next(l for l in editing.text_lines(pdfium.PdfDocument(big), 0) if l.text == "ABC")
    assert abs((b2.bbox[2] - b2.bbox[0]) - 2 * (L.bbox[2] - L.bbox[0])) < 2
    # Text ändern: direkter Weg verliert den Type3-Text -> Rückfall überlagert, Rest bleibt
    out, notes = editing.edit_line_bytes(data, 0, L, "NEU")
    t = pdfium.PdfDocument(out)[0].get_textpage().get_text_range()
    assert "NEU" in t and "CABA" in t.replace(" ", "") and "ABC" not in t.replace(" ", "")
    assert editing.verify_edit(data, out, 0, [(0, L.bbox[1] - 40, 595, L.bbox[3] + 40)]) == ""
    # Löschen ohne Neuerzeugung
    gone = editing.remove_line_ops(data, 0, L)
    rest = [l.text for l in editing.text_lines(pdfium.PdfDocument(gone), 0)]
    assert rest == ["CABA"], rest
    st = next(l for l in editing.text_lines(pdfium.PdfDocument(gone), 0))
    assert abs(st.bbox[0] - other.bbox[0]) < 0.5 and abs(st.bbox[1] - other.bbox[1]) < 0.5


def test_layer_transform_in_scaled_coordinates():
    """CAD-typisch: Inhalt in einem skalierten Koordinatensystem (0.12) – Verschiebung trotzdem in Seiten-pt."""
    import pikepdf
    pdf = pikepdf.new(); pdf.add_blank_page(page_size=(595, 842)); pg = pdf.pages[0]
    g = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.OCG, Name=pikepdf.String("Möbel")))
    pdf.Root.OCProperties = pikepdf.Dictionary(OCGs=[g], D=pikepdf.Dictionary(ON=[g], Order=[g]))
    pg.obj.Resources = pikepdf.Dictionary(Properties=pikepdf.Dictionary(M=g))
    pg.obj.Contents = pikepdf.Stream(pdf, b"q 0.12 0 0 0.12 0 0 cm /OC /M BDC 0 0 0 rg 1000 1000 1000 500 re f EMC Q")
    buf = io.BytesIO(); pdf.save(buf); data = buf.getvalue()
    key = preflight.analyze(data, deep_layers=False).layers[0].key
    b = editing.layer_map(data, 0).boxes[key]
    out = editing.transform_layer(data, key, dx=100, dy=-50)
    b2 = editing.layer_map(out, 0).boxes[key]
    assert abs(b2[0] - (b[0] + 100)) < 4 and abs(b2[1] - (b[1] - 50)) < 4, (b, b2)


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("ok", k)
