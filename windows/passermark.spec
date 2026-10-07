# -*- mode: python ; coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# PyInstaller recipe for Passermark (Windows). Run via windows/build.ps1.
import os
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

root = os.path.abspath(os.path.join(SPECPATH, ".."))
datas = [(os.path.join(root, "pdfdruck", "gui", "passermark.svg"), "pdfdruck/gui"),
         (os.path.join(root, "LICENSE"), "."), (os.path.join(root, "README.md"), ".")]
datas += collect_data_files("pypdfium2") + collect_data_files("pypdfium2_raw")
binaries = collect_dynamic_libs("pypdfium2_raw") + collect_dynamic_libs("pikepdf")
LANGS = ["pdfdruck.lang.en", "pdfdruck.lang.hu", "pdfdruck.lang.es", "pdfdruck.lang.fr"]

a = Analysis([os.path.join(SPECPATH, "launcher.py")], pathex=[root], binaries=binaries, datas=datas,
             hiddenimports=["win32print", "win32gui", "win32con", "win32event", "win32process", "pywintypes",
                            "win32com", "win32com.client", "win32com.shell", "pythoncom", "winreg",
                            "PySide6.QtSvg", "PySide6.QtNetwork", "pillow_heif", "img2pdf", "pikepdf", "numpy", "scipy", "contourpy", *LANGS],
             excludes=["cups", "tkinter"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="passermark", console=False,
          icon=os.path.join(SPECPATH, "passermark.ico"), version=None)
coll = COLLECT(exe, a.binaries, a.datas, name="passermark")
