# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Bearbeiten-Modus: Textzeilen und Ebenen."""
import io, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("PASSERMARK_LANG", "de")
try:
    import pypdfium2 as pdfium
    from pdfdruck import preflight
    import test_preflight as tp
except ModuleNotFoundError:                    # reine Logik-Tests laufen ohne PDF-Bibliotheken
    pdfium = None
from pdfdruck import editing

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
    assert K["Bemaßung"] in editing.layers_at(lm, 150, 625)       # red rectangle of the dimension layer
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
    # moving/scaling: the line is detached from the shared text block, into page coordinates
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
    # changing text: the direct route loses the Type3 text -> fallback overlays, the rest remains
    out, notes = editing.edit_line_bytes(data, 0, L, "NEU")
    t = pdfium.PdfDocument(out)[0].get_textpage().get_text_range()
    assert "NEU" in t and "CABA" in t.replace(" ", "") and "ABC" not in t.replace(" ", "")
    assert editing.verify_edit(data, out, 0, [(0, L.bbox[1] - 40, 595, L.bbox[3] + 40)]) == ""
    # deleting without regeneration
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
    b2 = editing.layer_map(out, 0, [key]).boxes[key]
    assert abs(b2[0] - (b[0] + 100)) < 4 and abs(b2[1] - (b[1] - 50)) < 4, (b, b2)



def _path_text_pdf() -> bytes:
    """Logo mit Pfadtext: drei Buchstaben einzeln gesetzt, je eigene Drehung auf einem Bogen,
    plus schwarzer Balken als Seiteninhalt, der unverändert bleiben muss."""
    import math
    import pikepdf
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(595, 842))
    page = pdf.pages[0]
    helv = pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1,
                              BaseFont=pikepdf.Name.Helvetica)
    page.obj.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=helv))
    cx, cy, rad = 297.5, 500.0, 80.0
    parts = [b"q 0 0 0 rg 50 50 495 200 re f Q"]
    for ch, deg in (("l", 105), ("d", 90), ("r", 75)):
        a = math.radians(deg)
        th = a - math.pi / 2                      # Buchstabe tangential, aufrecht zum Bogen
        x, y = cx + rad * math.cos(a), cy + rad * math.sin(a)
        parts.append(("BT /F1 24 Tf %f %f %f %f %f %f Tm (%s) Tj ET"
                      % (math.cos(th), math.sin(th), -math.sin(th), math.cos(th), x, y, ch)).encode("ascii"))
    page.obj.Contents = pikepdf.Stream(pdf, b"\n".join(parts))
    buf = io.BytesIO(); pdf.save(buf)
    return buf.getvalue()


def test_merge_arc_lines():
    """Bogen-Gruppierung (pure Logik, kein PDF nötig): 10 einzeln gesetzte, gedrehte
    Buchstaben auf einem Kreis um (297.5, 500), r=80 – wie Affinity-Pfadtext."""
    import math
    lines, rots = [], {}
    text = "PASSERMARK"
    for k, ch in enumerate(text):
        deg = 150 - k * (120.0 / (len(text) - 1))          # Bogen 150° → 30°
        a = math.radians(deg)
        th = a - math.pi / 2
        x, y = 297.5 + 80 * math.cos(a), 500 + 80 * math.sin(a)
        rot = math.degrees(math.atan2(math.sin(th), math.cos(th)))
        obj = 100 + k
        rots[obj] = (rot, x, y)
        bbox = (x - 10, y - 10, x + 10, y + 10)
        lines.append(editing.TextLine(k, [obj], ch, "ArialMT", 30.0, bbox, False, False, [k]))
    # gerade Zeile dazwischen darf nicht mit hineinfallen
    lines.append(editing.TextLine(10, [200], "Normal", "ArialMT", 30.0, (50, 400, 150, 430), False, False, [10]))
    editing._merge_arc_lines(lines, rots)
    texts = [L.text for L in lines]
    assert "PASSERMARK" in texts, texts
    assert "Normal" in texts and len(lines) == 2
    arc = next(L for L in lines if L.text == "PASSERMARK")
    assert arc.path_center is not None
    assert abs(arc.path_center[0] - 297.5) < 1.0 and abs(arc.path_center[1] - 500.0) < 1.0
    assert len(arc.objs) == 10 and arc.index in (0, 1)
    # gerade Zeile (alle Buchstaben ungedreht) wird NICHT gebogen zusammengefasst
    lines2, rots2 = [], {}
    for k, ch in enumerate("gerade"):
        obj = 300 + k
        rots2[obj] = (0.0, 50.0 + 20 * k, 400.0)
        lines2.append(editing.TextLine(k, [obj], ch, "ArialMT", 30.0, (50 + 20 * k, 390, 70 + 20 * k, 420),
                                       False, False, [k]))
    editing._merge_arc_lines(lines2, rots2)
    assert len(lines2) == 6 and all(L.path_center is None for L in lines2)


def test_page_objects():
    """Objektliste: Vektor- und Bildobjekte der Seite, Nadelobjekte raus."""
    data = _path_text_pdf()                      # enthaelt 1 Pfad (schwarzer Balken) + 3 Textobjekte
    d = pdfium.PdfDocument(data)
    objs = editing.page_objects(d, 0)
    d.close()
    assert [(o.kind, len(o.objs)) for o in objs] == [("path", 1)], objs
    b = objs[0].bbox
    assert abs(b[2] - b[0] - 495) < 1 and abs(b[3] - b[1] - 200) < 1   # Balken 495x200
    # verschieben + loeschen (pdfium-Pfad), verify_edit sichert den Rest
    d = pdfium.PdfDocument(data)
    editing.transform_object(d, 0, objs[0], 1.0, 10.0, 5.0)
    buf = io.BytesIO(); d.save(buf); new = buf.getvalue()
    d2 = pdfium.PdfDocument(new)
    objs2 = editing.page_objects(d2, 0)
    d2.close()
    assert abs(objs2[0].bbox[0] - (b[0] + 10)) < 0.1
    assert editing.verify_edit(data, new, 0, [(b[0] - 5, b[1] - 5, b[2] + 15, b[3] + 15)]) == ""
    d3 = pdfium.PdfDocument(new)
    editing.delete_object(d3, 0, objs2[0])
    buf = io.BytesIO(); d3.save(buf); after = buf.getvalue()
    d3.close()
    assert editing.verify_edit(new, after, 0, [objs2[0].bbox]) == ""
    assert not editing.page_objects(pdfium.PdfDocument(after), 0)


def test_path_text_font_size():
    data = _path_text_pdf()
    d = pdfium.PdfDocument(data)
    lines = editing.text_lines(d, 0)
    d.close()
    L = next(l for l in lines if l.text.replace(" ", "") == "ldr")
    assert len(L.objs) == 3, "Pfadtext-Buchstaben als eine Zeile erkannt"
    assert L.path_center is not None, "Bogenzentrum erkannt (path_center gesetzt)"
    # Größe ändern: skalieren um das Bogenzentrum, Seite bleibt sonst unangetastet
    new, notes = editing.edit_line_bytes(data, 0, L, L.text, None, 36)
    assert editing.verify_edit(data, new, 0, [(167.5, 370.0, 427.5, 630.0)]) == ""
    d2 = pdfium.PdfDocument(new)
    L2 = next(l for l in editing.text_lines(d2, 0) if l.text.replace(" ", "") == "ldr")
    d2.close()
    assert abs(L2.size - 36) < 2 and len(L2.objs) == 3
    # Text ändern geht bei Pfadtext nicht: klare Meldung statt halber Seite
    try:
        editing.edit_line_bytes(data, 0, L, "xyz", None, None)
        assert False, "ValueError erwartet"
    except ValueError as e:
        assert "Pfad" in str(e)

def test_z_runs_and_permute():
    """Z-Order-Kernlogik (rein, ohne PDF): Run-Zerlegung und Permutation."""
    names = ["q", "rg", "re", "f", "Q", "BT", "Tf", "Tm", "Tj", "ET"]
    runs = editing._z_runs(names, set())
    assert runs == [(0, 4, "path"), (5, 9, "text")], runs
    # Bild: Do mit cm davor -> Run umfasst cm
    runs = editing._z_runs(["cm", "Do"], {1})
    assert runs == [(0, 1, "image")], runs
    # Pfad mit Clip (W ... n) wird NICHT als verschiebbarer Run erkannt
    runs = editing._z_runs(["re", "W", "n"], set())
    assert runs == [], runs
    # Permutation
    assert editing._z_permute(4, {1}, "up") == [0, 2, 1, 3]
    assert editing._z_permute(4, {1}, "down") == [1, 0, 2, 3]
    assert editing._z_permute(4, {1}, "front") == [0, 2, 3, 1]
    assert editing._z_permute(4, {1}, "back") == [1, 0, 2, 3]
    assert editing._z_permute(3, {2}, "up") is None          # schon ganz vorn
    assert editing._z_permute(3, {0}, "down") is None        # schon ganz hinten
    # mehrere Ziele wandern als Block nach vorn
    assert editing._z_permute(5, {1, 3}, "front") == [0, 2, 4, 1, 3]


def test_reorder_objects_and_lines():
    """Z-Order: rotes Rechteck hinter blauem nach vorne holen (Pixel check),
        mehrere Zeilen gemeinschaftlich verschieben."""
    import pikepdf
    import numpy as np
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(300, 300))
    page = pdf.pages[0]
    page.obj.Resources = pikepdf.Dictionary(
        Font=pikepdf.Dictionary(F1=pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1,
                                                       BaseFont=pikepdf.Name.Helvetica)))
    content = b"""1 0 0 rg 100 100 50 50 re f
0 0 1 rg 120 120 50 50 re f
BT /F1 12 Tf 20 40 Td (Erste) Tj ET
BT /F1 12 Tf 20 20 Td (Zweite) Tj ET"""
    page.obj.Contents = pikepdf.Stream(pdf, content)
    buf = io.BytesIO(); pdf.save(buf)
    data = buf.getvalue()

    def pixel(doc, x, y):
        import pypdfium2 as pdfium
        d = pdfium.PdfDocument(doc)
        a = np.asarray(d[0].render(scale=1.0).to_pil().convert("RGB"))
        d.close()
        return tuple(a[int(300 - y), int(x)])

    assert abs(pixel(data, 145, 145)[2] - 255) < 10, "blaues Rechteck liegt oben"
    d = pdfium.PdfDocument(data)
    objs = editing.page_objects(d, 0)
    d.close()
    assert len(objs) == 2
    new = editing.reorder_objects(data, 0, [objs[0]], "front")       # rot nach vorne
    assert new is not None and new != data
    assert abs(pixel(new, 145, 145)[0] - 255) < 10, "rot liegt jetzt oben"
    # "up" gegen Grenze: ganz vorn geht nicht -> unverändert (data zurueck)
    d = pdfium.PdfDocument(new)
    objs = editing.page_objects(d, 0)
    d.close()
    same = editing.reorder_objects(new, 0, [objs[0]], "up")
    assert same == new, "schon ganz vorn: Datei unveraendert"
    # mehrere Textzeilen gemeinsam verschieben (Bulk, pdfium-Pfad)
    d = pdfium.PdfDocument(new)
    lines = editing.text_lines(d, 0)
    d.close()
    assert [L.text for L in lines] == ["Erste", "Zweite"]
    d = pdfium.PdfDocument(new)
    editing.transform_lines_bulk(d, 0, lines, 1.0, 0.0, 30.0)
    buf = io.BytesIO(); d.save(buf); moved = buf.getvalue()
    d.close()
    assert editing.verify_edit(new, moved, 0, [(20, 10, 90, 90)]) == ""
    d = pdfium.PdfDocument(moved)
    l2 = editing.text_lines(d, 0)
    d.close()
    assert abs(l2[0].bbox[1] - (lines[0].bbox[1] + 30)) < 0.5
    assert abs(l2[1].bbox[1] - (lines[1].bbox[1] + 30)) < 0.5


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if not k.startswith("test_"):
            continue
        if pdfium is None and k != "test_z_runs_and_permute":
            print("skip", k, "(pypdfium2/pikepdf fehlen)")
            continue
        f(); print("ok", k)
