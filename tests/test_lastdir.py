# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Last used folder for file dialogs (gui/lastdir.py)."""

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "_qtstub"))
sys.path.insert(0, os.path.join(HERE, ".."))
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()

from pdfdruck.gui import lastdir  # noqa: E402

WORK = tempfile.mkdtemp(dir=os.path.expanduser("~")) if os.access(os.path.expanduser("~"), os.W_OK) else None


def test_start_and_remember():
    if WORK is None:
        print("skip (home not writable)")
        return
    try:
        assert lastdir.start("bericht.txt") == "bericht.txt"  # nothing remembered yet
        lastdir.remember(os.path.join(WORK, "a.pdf"))
        assert lastdir.last() == WORK
        assert lastdir.start("") == WORK
        assert lastdir.start("bild.png") == os.path.join(WORK, "bild.png")
        assert lastdir.start(os.path.join(os.path.expanduser("~"), "x.pdf")) == os.path.join(WORK, "x.pdf")
        assert lastdir.start(os.path.expanduser("~")) == WORK
        # folders of the program/system stay
        assert lastdir.start("/usr/share/color/icc") == "/usr/share/color/icc"
        cfg = os.path.join(os.environ["XDG_CONFIG_HOME"], "passermark", "presets", "p.json")
        assert lastdir.start(cfg) == cfg
        lastdir.remember("/usr/share/color/icc/x.icc")  # not remembered
        assert lastdir.last() == WORK
    finally:
        os.rmdir(WORK)
    assert lastdir.last() == ""  # gone folder -> nothing


def test_dialog_gets_start_and_remembers():
    from PySide6.QtWidgets import QFileDialog

    calls = []
    out = tempfile.mkdtemp()

    def orig(parent, caption="", dir="", flt=""):  # noqa: A002 – Qt's keyword name
        calls.append(dir)
        return (os.path.join(out, "out.png"), flt)

    old = getattr(QFileDialog, "getSaveFileName", None)
    QFileDialog.getSaveFileName = staticmethod(orig)
    try:
        lastdir.getSaveFileName(None, "t", "name.png")
        assert lastdir.last() == out  # remembered
        lastdir.getSaveFileName(None, "t", "name.png")
        lastdir.getSaveFileName(None, "t", dir="")
        lastdir.getSaveFileName(None, "t")
        assert calls[1:] == [os.path.join(out, "name.png"), out, out], calls
    finally:
        if old is not None:
            QFileDialog.getSaveFileName = old
    assert lastdir._first_path((["/a/b.pdf"], "")) == "/a/b.pdf" and lastdir._first_path("/d") == "/d"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
