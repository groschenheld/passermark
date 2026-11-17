# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""SVG -> PDF (images.py): which converter was used and the hint when parts are rasterised."""

import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from pdfdruck import images, l10n  # noqa: E402

l10n.set_language("de")  # the asserts look for the German wording

FILTER_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="50mm" viewBox="0 0 100 50">'
    '<defs><filter id="f"><feGaussianBlur stdDeviation="2"/></filter></defs>'
    '<circle cx="80" cy="25" r="10" fill="green" filter="url(#f)"/></svg>'
)
PLAIN_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="10mm" height="10mm"><rect width="5" height="5"/></svg>'


def _pdf_with_image() -> bytes:
    import img2pdf
    from PIL import Image

    b = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(b, "PNG")
    return img2pdf.convert(b.getvalue())


def _write(text: str) -> str:
    fd, p = tempfile.mkstemp(suffix=".svg")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    return p


def test_notes():
    pdf = _pdf_with_image()
    assert "Filter" in images._svg_notes(_write(FILTER_SVG), "rsvg-convert", pdf)[0]
    assert "gerastert" in images._svg_notes(_write(PLAIN_SVG), "rsvg-convert", pdf)[0]
    assert "rsvg-convert installieren" in images._svg_notes(_write(PLAIN_SVG), "qt", pdf)[0]

    from reportlab.pdfgen import canvas

    b = io.BytesIO()
    c = canvas.Canvas(b)
    c.rect(10, 10, 50, 50)
    c.save()
    assert images._svg_notes(_write(PLAIN_SVG), "rsvg-convert", b.getvalue()) == []


def test_rsvg_used_and_reported():
    """A stand-in rsvg-convert on the PATH: it is used, the report says so."""
    if sys.platform == "win32":
        return
    d = tempfile.mkdtemp()
    src_pdf = os.path.join(d, "ready.pdf")
    with open(src_pdf, "wb") as f:
        f.write(_pdf_with_image())
    tool = os.path.join(d, "rsvg-convert")
    with open(tool, "w") as f:  # rsvg-convert -f pdf -o OUT IN
        f.write(f'#!/bin/sh\ncp "{src_pdf}" "$4"\n')
    os.chmod(tool, 0o755)
    old = os.environ["PATH"]
    os.environ["PATH"] = d + os.pathsep + old
    try:
        svg = _write(FILTER_SVG)
        data = images.svg_to_pdf_bytes(svg)
        assert data.startswith(b"%PDF")
        rep = images.svg_report(svg)
        assert rep["method"] == "rsvg-convert" and "Filter" in rep["notes"][0]
        assert images.svg_report(svg) is None  # taken once
    finally:
        os.environ["PATH"] = old


if __name__ == "__main__":
    for k, fn in list(globals().items()):
        if k.startswith("test_"):
            fn()
            print("ok", k)
