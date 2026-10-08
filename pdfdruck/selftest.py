# SPDX-License-Identifier: GPL-3.0-or-later
# pdfToolkit – Copyright (C) 2026 Hias
"""Selbsttest der fertigen Programmdatei (EXE/AppImage): prüft, dass alle mitgelieferten Abhängigkeiten laden.
Aufruf: pdftoolkit --selftest   (Rückgabe 0 = OK; Protokoll in <Temp>/pdftoolkit-selftest.log)"""
import os
import re
import subprocess
import sys
import tempfile
import traceback


def run() -> int:
    log = os.path.join(tempfile.gettempdir(), "pdftoolkit-selftest.log")
    lines, ok = [], True

    def step(name, fn):
        nonlocal ok
        try:
            r = fn()
            lines.append(f"OK   {name}" + (f": {r}" if r else ""))
        except Exception:
            ok = False
            lines.append(f"FAIL {name}\n" + traceback.format_exc())

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    def qt():
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([sys.argv[0]])
        from PySide6.QtSvg import QSvgRenderer  # noqa: F401
        return app.platformName()

    def pdfium():
        import pypdfium2 as p
        d = p.PdfDocument.new()
        d.new_page(595, 842)
        img = d[0].render(scale=0.2).to_pil()
        return f"render {img.size}"

    def pikepdf_():
        import pikepdf
        return pikepdf.__version__

    def images():
        import img2pdf  # noqa: F401
        from PIL import Image
        return Image.__version__

    def ghostscript():
        from . import platform as pl
        gs = pl.ghostscript()
        if not gs:
            raise RuntimeError("Ghostscript not found")
        out = subprocess.run([gs, "--version"], capture_output=True, text=True, timeout=60,
                             **pl.hidden_subprocess_kwargs())
        if out.returncode != 0:
            raise RuntimeError(out.stderr)
        return f"{out.stdout.strip()} ({gs})"

    def printing():
        from . import platform as pl
        if pl.IS_WIN:
            import win32print  # noqa: F401
            return "win32print"
        import cups  # noqa: F401
        return "pycups"

    step("Qt", qt)
    step("pdfium", pdfium)
    step("pikepdf", pikepdf_)
    step("Pillow/img2pdf", images)
    step("printing", printing)
    step("Ghostscript", ghostscript)
    if os.path.exists(os.path.join(os.path.dirname(__file__), "cutcontour.py")):
        step("numpy/scipy/contourpy", lambda: __import__("contourpy").__version__ + " / "
             + __import__("scipy").__version__)
    text = "\n".join(lines) + ("\nSELFTEST OK\n" if ok else "\nSELFTEST FAILED\n")
    try:
        with open(log, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError:
        pass
    try:
        print(text)
    except Exception:
        pass
    return 0 if ok else 1


def admin_helper(args: list) -> int:
    """Linux-AppImage: den mitgelieferten Root-Helfer ausführen (aufgerufen über pkexec, siehe admindialog).
    Der Helfer prüft wie gewohnt: Prüfregeln nur aus einem root-eigenen Ordner (beim AppImage: entpackt durch root)."""
    base = getattr(sys, "_MEIPASS", None) or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    path = os.path.join(base, "admin", "pdfdruck-admin")
    with open(path, encoding="utf-8") as f:
        code = f.read()
    code = re.sub(r'^LIB = .*$', "LIB = " + repr(base), code, count=1, flags=re.M)
    sys.argv = [path] + list(args)
    g = {"__name__": "__main__", "__file__": path}
    try:
        exec(compile(code, path, "exec"), g)
    except SystemExit as e:
        return int(e.code or 0)
    return 0



