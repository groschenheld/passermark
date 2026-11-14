# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Error log: every kind of error ends up in a file you can send along.

- one file per program start with system information; if everything runs smoothly, it is deleted on exit
- captures: Python errors (the GUI keeps running), errors in threads, hard crashes (faulthandler),
  errors from background jobs (record)
- after a hard crash, the next start reports the log (pending_crashes)
- recoverable errors the program works around (logger warnings, see docs/architecture.md, error handling)
  go in as "Hinweis": the file is kept so it can be sent along, but it is not reported as a crash
- at most MAX_LOGS logs containing errors are kept
"""

from __future__ import annotations

import atexit
import datetime
import faulthandler
import logging
import os
import platform as _pyplatform
import sys
import threading
import traceback

from . import platform as _platform

MAX_LOGS = 10
NOTE_REPEATS = 3  # the same note is written at most this often per run
SEEN_MARK = "== bereits gemeldet =="
CRASH_MARKERS = ("Fatal Python error", "Traceback (most recent call last)", "== Fehler")

_state = {"file": None, "path": None, "error": False, "notes": False, "on_error": None, "kind": ""}
_lock = threading.Lock()


def log_dir() -> str:
    """Folder for error logs."""
    return _platform.user_log_dir()


def system_info() -> str:
    """Version and system details as text for the head of a log."""
    from . import __version__

    lines = [
        f"Passermark {__version__}",
        f"System: {_pyplatform.platform()}",
        f"Python: {sys.version.split()[0]} ({'gebündelt' if getattr(sys, 'frozen', False) else 'Quelltext'})",
    ]
    for mod, label in (("pypdfium2", "pypdfium2"), ("pikepdf", "pikepdf"), ("numpy", "numpy"), ("scipy", "scipy")):
        try:
            m = __import__(mod)
            lines.append(f"{label}: {getattr(m, '__version__', getattr(m, 'V_PYPDFIUM2', '?'))}")
        except Exception:  # noqa: BLE001 – the details are only extras
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


SETTING = "error_logs"  # user setting: error logs and stall reports (on by default)


def enabled() -> bool:
    """Error logs switched on? (File → Settings; on by default)"""
    try:
        from . import l10n

        return bool(l10n.load_settings().get(SETTING, True))
    except Exception:  # noqa: BLE001 – im Zweifel an
        return True


def install(kind: str = "gui", on_error=None) -> str | None:
    """Set up the log for this program start. on_error(text, path): display (main thread only)."""
    if _state["file"] is not None:
        return _state["path"]
    d = log_dir()
    try:
        os.makedirs(d, exist_ok=True)
        _prune()
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        path = os.path.join(d, f"passermark-{kind}-{stamp}-{os.getpid()}.log")
        f = open(path, "w", encoding="utf-8", buffering=1)  # noqa: SIM115 – the log of this run, kept open until the program ends
    except OSError:
        return None  # no log possible – the program still runs
    f.write(f"== Passermark-Protokoll ({kind}) {datetime.datetime.now().isoformat(timespec='seconds')}\n")
    f.write(system_info() + "\n\n")
    f.flush()
    _state.update(file=f, path=path, error=False, notes=False, on_error=on_error, kind=kind)
    logging.getLogger("pdfdruck").addHandler(_NoteHandler())
    faulthandler.enable(file=f, all_threads=True)  # hard crashes (e.g. in pdfium) -> file
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
            except Exception:  # noqa: BLE001 – the display must never crash itself
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
    """Translate ``text``; return it unchanged if translating fails (used while handling an error)."""
    try:
        from .l10n import tr

        return tr(text)
    except Exception:  # noqa: BLE001
        return text


def record(title: str, details: str = "") -> None:
    """Write an error to the log (the file is then kept)."""
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


class _NoteHandler(logging.Handler):
    """Logger warnings (recoverable errors) -> "Hinweis" in the log, the same one at most NOTE_REPEATS times."""

    def __init__(self):
        super().__init__(logging.WARNING)
        self._seen: dict = {}

    def emit(self, rec: logging.LogRecord) -> None:
        """Write one warning as a note (called by the logging module)."""
        f = _state["file"]
        if f is None:
            return
        key = (rec.name, rec.msg)
        n = self._seen[key] = self._seen.get(key, 0) + 1
        if n > NOTE_REPEATS:
            return
        text = f"== Hinweis {datetime.datetime.now().isoformat(timespec='seconds')}: {rec.name}: {rec.getMessage()}\n"
        if rec.exc_info:
            # without the "Traceback (most recent call last)" header: a note is not a crash (CRASH_MARKERS)
            tb = "".join(traceback.format_exception(*rec.exc_info))
            text += tb.replace("Traceback (most recent call last):", "Verlauf:")
        if n == NOTE_REPEATS:
            text += "(weitere gleiche Hinweise werden nicht protokolliert)\n"
        with _lock:
            try:
                f.write(text + "\n")
                f.flush()
                _state["notes"] = True
            except (OSError, ValueError):
                pass


def current_path() -> str | None:
    """Path of the log file of this run, or None if nothing has been logged."""
    return _state["path"]


def _finish():
    """Normal program end: delete the log again if it contains no errors and no notes."""
    f, path = _state["file"], _state["path"]
    if f is None:
        return
    try:
        faulthandler.disable()
    except Exception:  # noqa: BLE001
        pass
    if _state["error"] or _state["notes"]:
        try:  # errors were already shown, notes are no crash -> do not report again
            f.write(f"{SEEN_MARK}\n")
        except (OSError, ValueError):
            pass
    try:
        f.close()
    except OSError:
        pass
    _state["file"] = None
    if not (_state["error"] or _state["notes"]) and path:
        try:
            os.remove(path)
        except OSError:
            pass


def pending_crashes() -> list[str]:
    """Logs of earlier starts with errors/crashes not yet reported (not the current one)."""
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
    """Mark log files as shown to the user so that they are not reported again."""
    for p in paths:
        try:
            with open(p, "a", encoding="utf-8") as fh:
                fh.write(f"\n{SEEN_MARK}\n")
        except OSError:
            pass
