# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
import os, sys, shutil, subprocess, tempfile
import os as _os
_os.environ.setdefault("PASSERMARK_LANG", "de")   # Tests prüfen deutsche Texte
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pdfdruck import convert


def test_order():
    av = {"libreoffice": "lo", "eurooffice": "x", "onlyoffice": "y"}
    assert convert.conversion_order("a.docx", "auto", av)[0] == "eurooffice"
    assert convert.conversion_order("a.odt", "auto", av)[0] == "libreoffice"
    assert convert.conversion_order("a.odg", "auto", av) == ["libreoffice"]
    assert convert.conversion_order("a.docx", "onlyoffice", av)[0] == "onlyoffice"
    assert convert.conversion_order("a.docx", "auto", {}) == []


def test_libreoffice_real():
    if not shutil.which("soffice"):
        print("  (LibreOffice nicht installiert – übersprungen)"); return
    d = tempfile.mkdtemp()
    p = os.path.join(d, "test.txt"); open(p, "w").write("Hallo Passermark\\n")
    doc, used = convert.to_document(p, d, preference="libreoffice")
    assert used == "LibreOffice" and len(doc) == 1


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("ok", k)
