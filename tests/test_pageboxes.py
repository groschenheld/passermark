# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Page boxes by number, search and replace text, before/after comparison (pageboxes.py, editing.py,
gui/comparedialog.py)."""

import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "_qtstub"))
sys.path.insert(0, os.path.join(HERE, ".."))

from reportlab.pdfgen import canvas  # noqa: E402

from pdfdruck import editing, l10n, pageboxes  # noqa: E402

l10n.set_language("de")  # the asserts look for the German wording


def _pdf(pages=2) -> bytes:
    b = io.BytesIO()
    c = canvas.Canvas(b, pagesize=(595.276, 841.89))
    for i in range(pages):
        c.setFont("Helvetica", 12)
        c.drawString(72, 700, f"Hallo Welt, hallo Graz {i}")
        c.drawString(72, 680, "Zweite Zeile Welt")
        c.showPage()
    c.save()
    return b.getvalue()


def _sheet(w_mm, h_mm, rotate=0) -> bytes:
    b = io.BytesIO()
    c = canvas.Canvas(b, pagesize=(w_mm * pageboxes.MM, h_mm * pageboxes.MM))
    c.drawString(20, 20, "x")
    c.showPage()
    c.save()
    data = b.getvalue()
    if rotate:
        import pikepdf

        with pikepdf.open(io.BytesIO(data)) as pdf:
            pdf.pages[0].obj["/Rotate"] = rotate
            out = io.BytesIO()
            pdf.save(out)
            data = out.getvalue()
    return data


def test_guess_format():
    assert pageboxes.guess_format(216, 303)[:4] == ("A4", 210, 297, 3.0)
    assert pageboxes.guess_format(303, 216)[0] == "A4"  # landscape
    assert pageboxes.guess_format(210, 297)[3] == 0.0  # exact A4: no bleed
    assert pageboxes.guess_format(250, 250) is None


def test_trim_format_with_bleed_and_cut():
    data = _sheet(310, 220)  # A4 landscape with far too much margin
    new, notes = pageboxes.apply_format(data, [0], 297, 210, 3.0, cut_excess=True)
    info = pageboxes.read(new, 0)
    assert [round(v, 1) for v in info["trim"]] == [297.0, 210.0] and info["bleed"] == 3.0
    assert [round(v, 1) for v in info["sheet"]] == [303.0, 216.0] and notes == []
    keep, _ = pageboxes.apply_format(data, [0], 297, 210, 3.0, cut_excess=False)
    assert [round(v, 1) for v in pageboxes.read(keep, 0)["sheet"]] == [310.0, 220.0]


def test_trim_format_without_enough_bleed():
    data = _sheet(210, 297)  # plain A4, no bleed in the file
    new, notes = pageboxes.apply_format(data, [0], 210, 297, 3.0)
    info = pageboxes.read(new, 0)
    assert info["bleed"] == 0.0 and notes  # nothing invented, but said
    try:
        pageboxes.apply_format(data, [0], 297, 420, 3.0)  # A3 on an A4 page
        raise AssertionError("trim larger than the page accepted")
    except ValueError:
        pass


def test_trim_format_on_rotated_page():
    data = _sheet(216, 303, rotate=90)  # shown as landscape 303 × 216
    assert [round(v) for v in pageboxes.read(data, 0)["sheet"]] == [303, 216]
    new, _ = pageboxes.apply_format(data, [0], 297, 210, 3.0)
    assert [round(v, 1) for v in pageboxes.read(new, 0)["trim"]] == [297.0, 210.0]


def test_dialog_result_text():
    from pdfdruck.gui.pageboxdialog import result_text

    assert "303" in result_text(297, 210, 3, 310, 220, True)  # gets cut down
    assert "Achtung" in result_text(210, 297, 3, 210, 297, True)
    assert "kleiner" in result_text(297, 420, 3, 210, 297, True)


def test_search_and_replace_text():
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(_pdf())
    assert len(editing.find_text(doc, [0, 1], "welt")) == 4  # without case
    assert editing.find_text(doc, [0], "welt", case=True) == []
    n, _notes = editing.replace_text(doc, [0], "Welt", "Steiermark", case=True)
    assert n == 2
    b = io.BytesIO()
    doc.save(b)
    d2 = pdfium.PdfDocument(b.getvalue())
    assert [ln.text for ln in editing.text_lines(d2, 0)] == [
        "Hallo Steiermark, hallo Graz 0",
        "Zweite Zeile Steiermark",
    ]
    assert "Welt" in editing.text_lines(d2, 1)[0].text  # page 2 untouched
    assert editing.replace_text(d2, [1], "", "x") == (0, [])


def test_compare_marks_changes():
    from pdfdruck.gui import comparedialog as C

    a = _pdf()
    same, _ = pageboxes.apply_format(a, [0], 200, 280, 0.0, cut_excess=False)  # boxes only: looks the same
    before = C.render(a, 0, 300)
    _img, share = C.marked(before, C.render(same, 0, 300))
    assert share == 0.0
    import pypdfium2 as pdfium

    d = pdfium.PdfDocument(a)
    editing.replace_text(d, [0], "Welt", "WWWWWWWWWW")
    b = io.BytesIO()
    d.save(b)
    _img, share = C.marked(before, C.render(b.getvalue(), 0, 300))
    assert 0 < share < 0.2
    assert C.render(a, 5, 100) is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
