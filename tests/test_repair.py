# SPDX-License-Identifier: GPL-3.0-or-later
# pdfToolkit – Copyright (C) 2026 Hias
import os, sys, io, zipfile
import os as _os
_os.environ.setdefault("PDFTOOLKIT_LANG", "de")   # Tests prüfen deutsche Texte
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pikepdf
from pdfdruck import repair, iccfetch

HERE = os.path.dirname(__file__)
SRC = os.path.join(HERE, "sample.pdf")


def test_repair_broken():
    d = open(SRC, "rb").read()
    i = d.rfind(b"startxref")
    open("/tmp/_broken.pdf", "wb").write(d[:i] + b"startxref\n999999\n%%EOF\n")
    r = repair.process("/tmp/_broken.pdf", "/tmp/_broken_rep.pdf", "repair")
    assert r.ok and r.pages_out == 7


def test_password_roundtrip():
    p = pikepdf.open(SRC); p.save("/tmp/_enc.pdf", encryption=pikepdf.Encryption(owner="x", user="geheim", R=6)); p.close()
    assert repair.needs_password("/tmp/_enc.pdf")
    try:
        repair.process("/tmp/_enc.pdf", "/tmp/_dec.pdf", "repair"); assert False
    except repair.PasswordRequired:
        pass
    repair.process("/tmp/_enc.pdf", "/tmp/_dec.pdf", "repair", password="geheim")
    assert not repair.needs_password("/tmp/_dec.pdf")
    repair.process("/tmp/_dec.pdf", "/tmp/_enc2.pdf", "repair", new_password="neu")
    assert repair.needs_password("/tmp/_enc2.pdf")


def test_icc_extract():
    from PIL import ImageCms
    b = bytearray(ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()); b[12:16] = b"prtr"
    os.makedirs("/tmp/_icc", exist_ok=True)
    with zipfile.ZipFile("/tmp/_icc/p.zip", "w") as z:
        z.writestr("a/x.icc", bytes(b)); z.writestr("b/x.icc", bytes(b)); z.writestr("note.txt", "x")
    res = iccfetch.extract_icc("/tmp/_icc/p.zip", "/tmp/_icc")
    assert len(res) == 1 and res[0].ok_output and res[0].space == "RGB"


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("ok", k)
