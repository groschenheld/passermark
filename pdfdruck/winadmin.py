# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Admin-Änderungen unter Windows: Gegenstück zu Polkit/pkexec.

Ablauf: Die GUI schreibt ein Bündel (Konfiguration, ICC-Importe, Drucker-Standards) in eine
temporäre Datei und startet passermark.exe --admin-apply <datei> über UAC („Als Administrator“).
Der erhöhte Prozess prüft ALLES mit denselben Regeln wie unter Linux (cfgvalidate), schreibt
atomar nach %ProgramData%\\Passermark (nur Administratoren dürfen dort schreiben – setzt der
Installer) und legt das Ergebnis in <datei>.result ab.
"""
from __future__ import annotations

from .l10n import tr

import json
import os
import sys
import tempfile

from . import cfgvalidate
from . import platform as _platform

MAX_BUNDLE = 4 << 20
MAX_ICC = 20 << 20


def _cfg_dir():
    return _platform.config_dir()


def _atomic_write(path: str, data: bytes):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _import_icc(src: str, pid: str, icc_dir: str):
    if not cfgvalidate.RX_ID.match(pid):
        raise ValueError(tr("Profil-ID ungültig"))
    if os.path.getsize(src) > MAX_ICC:
        raise ValueError(tr("ICC-Datei zu groß"))
    with open(src, "rb") as f:
        data = f.read()
    if len(data) < 128 or data[36:40] != b"acsp" or data[16:20] not in (b"RGB ", b"CMYK", b"GRAY"):
        raise ValueError(tr("{0} ist kein gültiges RGB/CMYK/Grau-ICC-Profil").format(os.path.basename(src)))
    _atomic_write(os.path.join(icc_dir, pid + ".icc"), data)


def apply(bundle_path: str) -> int:
    """Läuft ERHÖHT. Rückgabe 0 = ok."""
    result = {"ok": False, "error": "", "printer_defaults": 0}
    try:
        if os.path.getsize(bundle_path) > MAX_BUNDLE:
            raise ValueError(tr("Bündel zu groß"))
        with open(bundle_path, encoding="utf-8") as f:
            b = json.load(f)
        if not isinstance(b, dict):
            raise ValueError(tr("Bündel ungültig"))
        icc_dir = os.path.join(_cfg_dir(), "icc")
        cfg = b.get("config")
        if cfg is not None:
            cfgvalidate.validate(cfg, icc_dir, windows=True)
        defaults = b.get("printer_defaults", [])
        if not isinstance(defaults, list):
            raise ValueError(tr("printer_defaults ungültig"))
        if defaults:
            from . import printers_win
            known = {p.name for p in printers_win.list_printers()}
            for q, dm in defaults:
                if q not in known:
                    raise ValueError(tr("Unbekannter Drucker: {0}").format(q))
                cfgvalidate.check_devmode(dm, f"Drucker {q}")
        # erst alles geprüft – jetzt schreiben
        for it in b.get("import_icc", []):
            _import_icc(str(it["src"]), str(it["id"]), icc_dir)
        for pid in b.get("remove_icc", []):
            if cfgvalidate.RX_ID.match(str(pid)):
                p = os.path.join(icc_dir, f"{pid}.icc")
                if os.path.exists(p):
                    os.unlink(p)
        if defaults:
            from . import printers_win
            for q, dm in defaults:
                printers_win.set_printer_default(q, dm)
                result["printer_defaults"] += 1
        if cfg is not None:
            _atomic_write(os.path.join(_cfg_dir(), "defaults.json"),
                          json.dumps(cfg, indent=2, ensure_ascii=False).encode("utf-8"))
        result["ok"] = True
        code = 0
    except Exception as e:
        result["error"] = str(e)
        code = 1
    try:
        with open(bundle_path + ".result", "w", encoding="utf-8") as f:
            json.dump(result, f)
    except OSError:
        pass
    return code


def run_elevated(bundle: dict) -> tuple[int, str, dict]:
    """Aus der GUI: Bündel schreiben, UAC-Abfrage, warten. (code, meldung, ergebnis); 126 = abgebrochen."""
    import pywintypes
    import win32con
    import win32event
    import win32process
    from win32com.shell import shell, shellcon

    fd, tmp = tempfile.mkstemp(prefix="passermark-admin-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False)
    if getattr(sys, "frozen", False):
        exe, params, cwd = sys.executable, f'--admin-apply "{tmp}"', None
    else:
        exe = sys.executable
        params = f'-m pdfdruck --admin-apply "{tmp}"'
        cwd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        try:
            info = shell.ShellExecuteEx(fMask=shellcon.SEE_MASK_NOCLOSEPROCESS, lpVerb="runas",
                                        lpFile=exe, lpParameters=params, lpDirectory=cwd,
                                        nShow=win32con.SW_HIDE)
        except pywintypes.error as e:
            if getattr(e, "winerror", 0) == 1223:          # Benutzer hat UAC abgelehnt
                return 126, "Abgebrochen", {}
            raise
        h = info["hProcess"]
        win32event.WaitForSingleObject(h, win32event.INFINITE)
        code = win32process.GetExitCodeProcess(h)
        res = {}
        try:
            with open(tmp + ".result", encoding="utf-8") as f:
                res = json.load(f)
        except (OSError, ValueError):
            pass
        return code, res.get("error", "") or ("" if code == 0 else f"Code {code}"), res
    finally:
        for p in (tmp, tmp + ".result"):
            try:
                os.unlink(p)
            except OSError:
                pass
