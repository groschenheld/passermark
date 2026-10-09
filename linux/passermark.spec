# -*- mode: python ; coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# PyInstaller recipe for Passermark (Linux / AppImage). Run via linux/build-appimage.sh.
import os
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

root = os.path.abspath(os.path.join(SPECPATH, ".."))
datas = [(os.path.join(root, "pdfdruck", "gui", "passermark.svg"), "pdfdruck/gui"),
         (os.path.join(root, "LICENSE"), "."), (os.path.join(root, "README.md"), "."),
         (os.path.join(root, "pdfdruck", "docs"), "pdfdruck/docs")]
datas += collect_data_files("pypdfium2") + collect_data_files("pypdfium2_raw") + collect_data_files("reportlab")
binaries = collect_dynamic_libs("pypdfium2_raw") + collect_dynamic_libs("pikepdf")
RL = collect_submodules("reportlab.graphics.barcode") + ["reportlab.graphics.renderPDF"]  # Barcodes (dynamisch geladen)
LANGS = ["pdfdruck.lang.en", "pdfdruck.lang.hu", "pdfdruck.lang.es", "pdfdruck.lang.fr"]

# root helper + validation rules as plain files (used by "--admin-helper" when running as AppImage)
datas += [(os.path.join(root, "admin", "passermark-admin"), "admin"),
          (os.path.join(root, "pdfdruck", "cfgvalidate.py"), "pdfdruck")]
a = Analysis([os.path.join(root, "windows", "launcher.py")], pathex=[root], binaries=binaries, datas=datas,
             hiddenimports=["cups", "PySide6.QtSvg", "PySide6.QtNetwork", "PySide6.QtDBus", "pillow_heif", "img2pdf",
                            "pikepdf", "numpy", "scipy", "contourpy", *RL, *LANGS],
             excludes=["tkinter", "win32print", "win32gui"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="passermark", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="passermark")
