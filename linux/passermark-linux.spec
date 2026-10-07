# -*- mode: python ; coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# PyInstaller-Bauplan fuer Passermark (Linux, fuer AppImage). Aufruf: siehe linux/build-appimage.sh
import os
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

root = os.path.abspath(os.path.join(SPECPATH, ".."))
datas = [(os.path.join(root, "pdfdruck", "gui", "passermark.svg"), "pdfdruck/gui"),
         (os.path.join(root, "LICENSE"), "."), (os.path.join(root, "README.md"), ".")]
datas += collect_data_files("pypdfium2") + collect_data_files("pypdfium2_raw")
binaries = collect_dynamic_libs("pypdfium2_raw") + collect_dynamic_libs("pikepdf")

a = Analysis([os.path.join(root, "windows", "launcher.py")], pathex=[root], binaries=binaries, datas=datas,
             hiddenimports=["cups",
                            "PySide6.QtSvg", "PySide6.QtNetwork", "PySide6.QtDBus",
                            "pillow_heif", "img2pdf", "pikepdf",
                            "pdfdruck.lang.en", "pdfdruck.lang.hu", "pdfdruck.lang.es", "pdfdruck.lang.fr"],
             excludes=["win32print", "win32gui", "win32con", "win32event", "win32process",
                       "win32com", "pythoncom", "winreg", "tkinter"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="passermark", console=False,
          icon=None, version=None)
coll = COLLECT(exe, a.binaries, a.datas, name="passermark")
