# SPDX-License-Identifier: GPL-3.0-or-later
# pdfToolkit – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Fehlerprotokoll: jede Fehlerart landet in einer Datei, die man mitschicken kann.

- pro Programmstart eine Datei mit Systemangaben; läuft alles glatt, wird sie beim Beenden gelöscht
- erfasst: Python-Fehler (Oberfläche läuft weiter), Fehler in Threads, harte Abstürze (faulthandler),
  Fehler aus Hintergrund-Aufträgen (record)
- nach einem harten Absturz meldet der nächste Start das Protokoll (pending_crashes)
- es bleiben höchstens MAX_LOGS Protokolle mit Fehler erhalten
"""
from __future__ import annotations

import atexit
import datetime
import faulthandler
import os
import platform as _pyplatform
import sys
import threading
import traceback

from . import platform as _platform

MAX_LOGS = 10
SEEN_MARK = "== bereits gemeldet =="
CRASH_MARKERS = ("Fatal Python error", "Traceback (most recent call last)", "== Fehler")

_state = {"file": None, "path": None, "error": False, "on_error": None, "kind": ""}
_lock = threading.Lock()


def log_dir() -> str:
    return _platform.user_log_dir()


def system_info() -> str:
    from . import __version__
    lines = [f"pdfToolkit {__version__}",
             f"System: {_pyplatform.platform()}",
             f"Python: {sys.version.split()[0]} ({'gebündelt' if getattr(sys, 'frozen', False) else 'Quelltext'})"]
    for mod, label in (("pypdfium2", "pypdfium2"), ("pikepdf", "pikepdf"), ("numpy", "numpy"), ("scipy", "scipy")):
        try:
            m = __import__(mod)
            lines.append(f"{label}: {getattr(m, '__version__', getattr(m, 'V_PYPDFIUM2', '?'))}")
        except Exception:                                  # noqa: BLE001 – Angaben sind nur Beiwerk
            pass
    if "PySide6.QtCore" in sys.modules:
        lines.append(f"Qt: {sys.modules['PySide6.QtCore'].qVersion()}")
    mem = _platform.total_memory()
    lines.append(f"Kerne: {os.cpu_count()}  Arbeitsspeicher: {round(mem / 1e9, 1) if mem else '?'} GB")
    return "\n".join(lines)


def _prune():
    d = log_dir()
    try:
        logs = sorted((os.path.join(d, f) for f in os.listdir(d) if f.endswith(".log")), key=os.path.getmtime)
    except OSError:
        return
    for p in logs[:-MAX_LOGS]:
        try:
            os.remove(p)
        except OSError:
            pass


def install(kind: str = "gui", on_error=None) -> str | None:
    """Protokoll für diesen Programmstart einrichten. on_error(text, pfad): Anzeige (nur im Hauptthread)."""
    if _state["file"] is not None:
        return _state["path"]
    d = log_dir()
    try:
        os.makedirs(d, exist_ok=True)
        _prune()
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        path = os.path.join(d, f"pdftoolkit-{kind}-{stamp}-{os.getpid()}.log")
        f = open(path, "w", encoding="utf-8", buffering=1)
    except OSError:
        return None                                        # kein Protokoll möglich – Programm läuft trotzdem
    f.write(f"== pdfToolkit-Protokoll ({kind}) {datetime.datetime.now().isoformat(timespec='seconds')}\n")
    f.write(system_info() + "\n\n")
    f.flush()
    _state.update(file=f, path=path, error=False, on_error=on_error, kind=kind)
    faulthandler.enable(file=f, all_threads=True)          # harte Abstürze (z. B. in pdfium) -> Datei
    prev_hook = sys.excepthook

    def excepthook(et, ev, tb):
        if issubclass(et, KeyboardInterrupt):
            prev_hook(et, ev, tb)
            return
        text = "".join(traceback.format_exception(et, ev, tb))
        record(tr_safe("Unerwarteter Fehler"), text)
        cb = _state["on_error"]
        if cb is not None and threading.current_thread() is threading.main_thread():
            try:
                cb(f"{et.__name__}: {ev}", text)
            except Exception:                              # noqa: BLE001 – Anzeige darf nie selbst abstürzen
                pass
    sys.excepthook = excepthook

    def thread_hook(args):
        if args.exc_type is SystemExit:
            return
        text = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
        record(f"Fehler im Thread {getattr(args.thread, 'name', '?')}", text)
    threading.excepthook = thread_hook
    atexit.register(_finish)
    return path


def tr_safe(text: str) -> str:
    try:
        from .l10n import tr
        return tr(text)
    except Exception:                                      # noqa: BLE001
        return text


def record(title: str, details: str = "") -> None:
    """Einen Fehler ins Protokoll schreiben (Datei bleibt dann erhalten)."""
    f = _state["file"]
    if f is None:
        return
    with _lock:
        try:
            f.write(f"== Fehler {datetime.datetime.now().isoformat(timespec='seconds')}: {title}\n")
            if details:
                f.write(details.rstrip() + "\n")
            f.write("\n")
            f.flush()
            _state["error"] = True
        except (OSError, ValueError):
            pass


def current_path() -> str | None:
    return _state["path"]


def _finish():
    """Normales Programmende: Protokoll ohne Fehler wieder löschen."""
    f, path = _state["file"], _state["path"]
    if f is None:
        return
    try:
        faulthandler.disable()
    except Exception:                                      # noqa: BLE001
        pass
    if _state["error"]:
        try:                                               # Fehler wurden schon angezeigt -> nicht nochmal melden
            f.write(f"{SEEN_MARK}\n")
        except (OSError, ValueError):
            pass
    try:
        f.close()
    except OSError:
        pass
    _state["file"] = None
    if not _state["error"] and path:
        try:
            os.remove(path)
        except OSError:
            pass


def pending_crashes() -> list[str]:
    """Protokolle früherer Starts mit Fehler/Absturz, die noch nicht gemeldet wurden (ohne den laufenden)."""
    d = log_dir()
    out = []
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return out
    for n in names:
        p = os.path.join(d, n)
        if not n.endswith(".log") or p == _state["path"]:
            continue
        try:
            with open(p, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        if SEEN_MARK not in text and any(m in text for m in CRASH_MARKERS):
            out.append(p)
    return out


def mark_seen(paths: list[str]) -> None:
    for p in paths:
        try:
            with open(p, "a", encoding="utf-8") as fh:
                fh.write(f"\n{SEEN_MARK}\n")
        except OSError:
            pass
