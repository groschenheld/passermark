# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Lizenzen von Drittanbietern: tools/third_party_licenses.py sammelt alles, was Installer und
    AppImage mitliefern (Python-Pakete, Qt-LGPL-Hinweis, Ghostscript-AGPL-Hinweis, Lizenztexte)."""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
TOOL = os.path.join(ROOT, "tools", "third_party_licenses.py")


def _run(*args) -> str:
    out = tempfile.mkdtemp(prefix="pm-lic-")
    r = subprocess.run([sys.executable, TOOL, os.path.join(out, "licenses"), *args],
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout + r.stderr
    return os.path.join(out, "licenses")


def test_repository_texts_present():
    for f in ("LICENSE", "licenses/LGPL-3.0.txt", "licenses/MPL-2.0.txt", "licenses/GPL-2.0.txt",
              "licenses/lxml-BSD-3-Clause.txt"):
        p = os.path.join(ROOT, f)
        assert os.path.isfile(p), f
    assert "LESSER GENERAL PUBLIC LICENSE" in open(os.path.join(ROOT, "licenses/LGPL-3.0.txt")).read()
    assert "Mozilla Public License Version 2.0" in open(os.path.join(ROOT, "licenses/MPL-2.0.txt")).read()


def test_collects_packages_and_notices():
    agpl = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
    agpl.write("GNU AFFERO GENERAL PUBLIC LICENSE\nVersion 3, 19 November 2007\n")
    agpl.close()
    try:
        d = _run("--requirements", os.path.join(ROOT, "requirements.txt"), "--gs-version", "10.05.1",
                 "--agpl", agpl.name)
    finally:
        os.unlink(agpl.name)
    notes = open(os.path.join(d, "THIRD_PARTY_NOTICES.txt"), encoding="utf-8").read()
    for pkg in ("pikepdf", "numpy", "img2pdf", "pypdfium2"):
        assert pkg in notes, pkg
    assert "Ghostscript 10.05.1" in notes and "AGPL-3.0" in notes
    for t in ("GPL-3.0.txt", "LGPL-3.0.txt", "MPL-2.0.txt", "AGPL-3.0.txt"):
        assert os.path.isfile(os.path.join(d, "texts", t)), t
    gs = open(os.path.join(d, "GHOSTSCRIPT-NOTICE.txt"), encoding="utf-8").read()
    assert "ghostpdl-10.05.1" in gs and "gs10051" in gs, gs
    pk = [p for p in os.listdir(os.path.join(d, "python-packages")) if p.startswith("pikepdf-")]
    assert pk and any(f.upper().startswith("LICENSE") for f in os.listdir(os.path.join(d, "python-packages", pk[0])))


def test_without_ghostscript_no_gs_notice():
    d = _run("--requirements", os.path.join(ROOT, "requirements.txt"))
    assert not os.path.exists(os.path.join(d, "GHOSTSCRIPT-NOTICE.txt"))
    assert os.path.isfile(os.path.join(d, "THIRD_PARTY_NOTICES.txt"))


def test_fallback_for_packages_without_licence_file():
    """PySide6/shiboken6-Wheels und Debians python3-lxml/python3-cups haben keine Lizenzdatei im dist-info."""
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import third_party_licenses as t
    for key, spdx in (("pyside6", "LGPL-3.0"), ("shiboken6", "LGPL-3.0"), ("lxml", "BSD-3-Clause"),
                      ("pycups", "GPL-2.0-or-later")):
        d = tempfile.mkdtemp()
        name = t.known_license(key, d)
        assert name == f"LICENSE-{spdx}.txt" and os.path.getsize(os.path.join(d, name)) > 1000, key
        assert spdx in open(os.path.join(d, "NOTE.txt"), encoding="utf-8").read()
    assert t.known_license("gibtsnicht", tempfile.mkdtemp()) == ""


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
