# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Als PDF speichern + Formularwerte beim Druck (Flatten)."""
import os, sys
import os as _os
_os.environ.setdefault("PASSERMARK_LANG", "de")   # Tests prüfen deutsche Texte
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pypdfium2 as pdfium
from pdfdruck import config, layout, printers, printjob

HERE = os.path.dirname(__file__)


class S:
    def __init__(self):
        self.cfg = config.BUILTIN
        self._c = {}
    def caps_for(self, n): return self._c.setdefault(n, printers.pdf_caps())
    def values_for(self, n): return self.caps_for(n).defaults()
    def color_for(self, n): return ("", "relative")


def _form_pdf():
    from reportlab.pdfgen import canvas
    p = "/tmp/_form.pdf"
    c = canvas.Canvas(p); c.drawString(72, 760, "Formular")
    c.acroForm.textfield(name="n", value="Formularwert Hias", x=72, y=700, width=250, height=24)
    c.showPage(); c.save()
    return p


def test_flatten_keeps_form_values():
    d = pdfium.PdfDocument(_form_pdf())
    f = layout.flattened(d)
    assert f is not d and "Formularwert" in f[0].get_textpage().get_text_range()
    plain = pdfium.PdfDocument(os.path.join(HERE, "sample.pdf"))
    assert layout.flattened(plain) is plain                  # ohne Anmerkungen: Original


def test_save_as_pdf_doc_size_and_nup():
    d = pdfium.PdfDocument(os.path.join(HERE, "sample.pdf"))
    out = "/tmp/_pdfout.pdf"
    printjob.submit_document(d, "x", S(), printers.PDF_TARGET, list(range(len(d))), layout.LayoutSettings(mode="actual"),
                             values={"PageSize": "DOC", "__out__": out})
    o = pdfium.PdfDocument(out)
    assert len(o) == len(d) and abs(o.get_page_size(0)[0] - d.get_page_size(0)[0]) < 0.5
    printjob.submit_document(d, "x", S(), printers.PDF_TARGET, list(range(len(d))),
                             layout.LayoutSettings(handling="multiple", nup=4), values={"PageSize": "A3", "__out__": out})
    o = pdfium.PdfDocument(out)
    assert len(o) == 2 and round(o.get_page_size(0)[1]) == 1191     # A3


def test_form_values_in_print_output():
    d = pdfium.PdfDocument(_form_pdf())
    out = "/tmp/_pdfout_form.pdf"
    printjob.submit_document(d, "x", S(), printers.PDF_TARGET, [0], layout.LayoutSettings(handling="multiple", nup=2),
                             values={"PageSize": "A4", "__out__": out})
    assert "Formularwert" in pdfium.PdfDocument(out)[0].get_textpage().get_text_range()


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("ok", k)
