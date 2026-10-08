# SPDX-License-Identifier: GPL-3.0-or-later
# pdfToolkit – Copyright (C) 2026 Hias
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
        return os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "pdfToolkit")
    return "/etc/pdfdruck"


def user_log_dir() -> str:
    """Fehlerprotokolle: Windows %LOCALAPPDATA%\\pdfToolkit\\logs, Linux ~/.local/state/pdftoolkit/logs."""
    if IS_WIN:
        base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
        return os.path.join(base, "pdfToolkit", "logs")
    base = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(base, "pdftoolkit", "logs")


def total_memory() -> int | None:
    """Arbeitsspeicher des Rechners in Bytes (None, wenn nicht ermittelbar)."""
    try:
        if IS_WIN:
            import ctypes

            class _MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            ms = _MS()
            ms.dwLength = ctypes.sizeof(_MS)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms)):
                return int(ms.ullTotalPhys)
            return None
        return int(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"))
    except (ValueError, OSError, AttributeError):
        return None


def user_cache_dir() -> str:
    if IS_WIN:
        base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
        return os.path.join(base, "pdfToolkit", "cache")
    return os.path.join(os.path.expanduser("~"), ".cache", "pdftoolkit")


def app_dirs() -> list[str]:
    """Ordner der eigenen Programmdatei (Installer/AppImage bringen dort z. B. Ghostscript mit)."""
    import sys
    if getattr(sys, "frozen", False):
        return [os.path.dirname(os.path.abspath(sys.executable))]
    return []


def find_program(names: list[str], win_globs: list[str] = ()) -> str | None:
    """Programm im PATH oder (Windows) unter den üblichen Installationsorten finden."""
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    if IS_WIN:
        roots = app_dirs() + [os.environ.get(v) for v in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432",
                                                          "LOCALAPPDATA")]
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
            tray = getattr(app, "_pdftoolkit_tray", None)
            if tray is None:
                tray = QSystemTrayIcon(app.windowIcon(), app)
                app._pdftoolkit_tray = tray
            tray.show()
            tray.showMessage(title, body, QSystemTrayIcon.MessageIcon.Critical if error
                             else QSystemTrayIcon.MessageIcon.Information, 6000)
        except Exception:
            pass
        return
    if shutil.which("notify-send"):
        subprocess.Popen(["notify-send", "-a", "pdfToolkit", "-i", "dialog-error" if error else "pdftoolkit",
                          title, body], start_new_session=True)


def hidden_subprocess_kwargs() -> dict:
    """Unter Windows kein Konsolenfenster für Hilfsprogramme aufblitzen lassen."""
    if IS_WIN:
        return {"creationflags": 0x08000000}        # CREATE_NO_WINDOW
    return {}
