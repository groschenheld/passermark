# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Betriebssystem-Unterschiede an einer Stelle: Pfade, Benutzerkennung, Benachrichtigungen, Programme."""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
import tempfile

IS_WIN = sys.platform == "win32"


def user_id() -> str:
    """Kennung für benutzereigene Sockets/Profile (Linux: UID, Windows: Benutzername)."""
    if hasattr(os, "getuid"):
        return str(os.getuid())
    return "".join(c for c in (os.environ.get("USERNAME") or "user") if c.isalnum()) or "user"


def config_dir() -> str:
    env = os.environ.get("PDFDRUCK_CONFIG_DIR")
    if env:
        return env
    if IS_WIN:
        return os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "Passermark")
    return "/etc/passermark"


def user_cache_dir() -> str:
    if IS_WIN:
        base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
        return os.path.join(base, "Passermark", "cache")
    return os.path.join(os.path.expanduser("~"), ".cache", "passermark")


def find_program(names: list[str], win_globs: list[str] = ()) -> str | None:
    """Programm im PATH oder (Windows) unter den üblichen Installationsorten finden."""
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    if IS_WIN:
        # gebuendelte Programme neben der eigenen EXE zuerst (PyInstaller frozen)
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        for pat in win_globs:
            hits = sorted(glob.glob(os.path.join(exe_dir, pat)), reverse=True)
            if hits:
                return hits[0]
        roots = [os.environ.get(v) for v in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "LOCALAPPDATA")]
        for root in filter(None, roots):
            for pat in win_globs:
                hits = sorted(glob.glob(os.path.join(root, pat)), reverse=True)   # neueste Version zuerst
                if hits:
                    return hits[0]
    return None


def ghostscript() -> str | None:
    return find_program(["gs", "gswin64c", "gswin32c"], [r"gs\gs*\bin\gswin64c.exe", r"gs\gs*\bin\gswin32c.exe"])


def seven_zip() -> str | None:
    return find_program(["7z", "7zz", "7za"], [r"7-Zip\7z.exe"])


def notify(title: str, body: str, error: bool = False):
    """Desktop-Benachrichtigung (Linux: notify-send, Windows: Tray-Meldung)."""
    if IS_WIN:
        try:
            from PySide6.QtWidgets import QApplication, QSystemTrayIcon
            app = QApplication.instance()
            if app is None:
                return
            tray = getattr(app, "_passermark_tray", None)
            if tray is None:
                tray = QSystemTrayIcon(app.windowIcon(), app)
                app._passermark_tray = tray
            tray.show()
            tray.showMessage(title, body, QSystemTrayIcon.MessageIcon.Critical if error
                             else QSystemTrayIcon.MessageIcon.Information, 6000)
        except Exception:
            pass
        return
    if shutil.which("notify-send"):
        subprocess.Popen(["notify-send", "-a", "Passermark", "-i", "dialog-error" if error else "passermark",
                          title, body], start_new_session=True)


def hidden_subprocess_kwargs() -> dict:
    """Unter Windows kein Konsolenfenster für Hilfsprogramme aufblitzen lassen."""
    if IS_WIN:
        return {"creationflags": 0x08000000}        # CREATE_NO_WINDOW
    return {}
