# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Auftrag an die laufende Instanz weiterreichen – ohne Qt, ganz am Anfang des Programmstarts.

Explorer startet bei einer Mehrfachauswahl („Als ein PDF zusammenführen“ auf 110 Pläne) pro Datei einen eigenen
Prozess. Bisher lud jeder davon erst die ganze Oberfläche, bevor er seine Datei weitergab – die Dateien kamen
über Sekunden verteilt an. So ist jeder Prozess nach Sekundenbruchteilen wieder weg.

Spricht dasselbe Protokoll wie app.Controller (QLocalServer): eine JSON-Zeile hin, „ok“ zurück.
QLocalServer: Windows = Named Pipe \\\\.\\pipe\\<Name>, sonst Unix-Socket <TMPDIR oder /tmp>/<Name>.
"""
from __future__ import annotations

import json
import os
import threading
import time


def server_name() -> str:
    from .platform import user_id
    return f"passermark-{user_id()}"


def send(cmd: str, files: list, timeout: float = 3.0) -> bool:
    """True = laufende Instanz hat den Auftrag angenommen. False = keine da (oder nicht erreichbar)."""
    return send_ex(cmd, files, timeout) == "ok"


def send_ex(cmd: str, files: list, timeout: float = 3.0) -> str:
    """„ok“ = angenommen, „none“ = keine Instanz da, „busy“ = Instanz da, hat aber (noch) nicht geantwortet."""
    msg = (json.dumps({"cmd": cmd, "files": files}) + "\n").encode("utf-8")
    try:
        if os.name == "nt":
            return _send_pipe(msg, timeout)
        return _send_unix(msg, timeout)
    except Exception:
        return "busy"


def _send_unix(msg: bytes, timeout: float) -> str:
    import socket
    path = os.path.join(os.environ.get("TMPDIR") or "/tmp", server_name())
    if not os.path.exists(path):
        return "none"
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(path)
    except (ConnectionRefusedError, FileNotFoundError):
        s.close()
        return "none"                            # verwaiste Socket-Datei nach Absturz
    except OSError:
        s.close()
        return "busy"
    try:
        s.sendall(msg)
        return "ok" if s.recv(16).startswith(b"ok") else "busy"
    except OSError:
        return "busy"
    finally:
        s.close()


def _send_pipe(msg: bytes, timeout: float) -> str:
    path = "\\\\.\\pipe\\" + server_name()
    f = None
    end = time.monotonic() + max(1.0, timeout)
    while f is None:
        try:
            f = open(path, "r+b", buffering=0)
        except FileNotFoundError:
            return "none"                        # keine Instanz
        except OSError:                          # Pipe gerade belegt (viele gleichzeitig): kurz warten
            if time.monotonic() > end:
                return "busy"
            time.sleep(0.05)
    res = {}

    def talk():
        try:
            f.write(msg)
            res["reply"] = f.read(3)
        except OSError:
            pass
    t = threading.Thread(target=talk, daemon=True)
    t.start()
    t.join(timeout)
    try:
        f.close()
    except OSError:
        pass
    return "ok" if bytes(res.get("reply") or b"").startswith(b"ok") else "busy"


class StartLock:
    """Startsperre über alle Prozesse des Benutzers: Nur wer sie hält, darf Server (Hauptinstanz) werden.

        Explorer startet bei Mehrfachauswahl je Datei einen Prozess – alle gleichzeitig, keiner findet eine Instanz.
        Ohne Sperre wurden mehrere davon Server (QLocalServer.listen klappt unter Windows auch, wenn auf dem Namen
        schon einer lauscht) – jeder bekam nur einen Teil der Dateien: „nur Einzeldateien zusammengeführt“.
        Mit Sperre: einer wird Server, die anderen warten (ohne Qt zu laden) und reichen danach weiter.
        Das Betriebssystem gibt die Sperre frei, wenn der Prozess endet (auch bei Absturz)."""

    def __init__(self):
        self._h = None
        self._f = None

    def acquire(self, timeout: float = 20.0) -> bool:
        try:
            if os.name == "nt":
                return self._acquire_win(timeout)
            return self._acquire_posix(timeout)
        except Exception:
            return False                         # im Zweifel ohne Sperre weiter (wie bisher)

    def _acquire_win(self, timeout: float) -> bool:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateMutexW.restype = wintypes.HANDLE
        k32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        k32.WaitForSingleObject.restype = wintypes.DWORD
        k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        h = k32.CreateMutexW(None, False, "Local\\" + server_name() + "-start")
        if not h:
            return False
        r = k32.WaitForSingleObject(h, int(timeout * 1000))
        if r in (0x0, 0x80):                     # WAIT_OBJECT_0 / WAIT_ABANDONED (Vorgänger abgestürzt)
            self._h, self._k32 = h, k32
            return True
        k32.CloseHandle(h)
        return False

    def _acquire_posix(self, timeout: float) -> bool:
        import fcntl
        path = os.path.join(os.environ.get("TMPDIR") or "/tmp", server_name() + ".startlock")
        f = open(path, "a+")
        end = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._f = f
                return True
            except OSError:
                if time.monotonic() > end:
                    f.close()
                    return False
                time.sleep(0.05)

    def release(self):
        try:
            if self._h is not None:
                self._k32.ReleaseMutex(self._h)
                self._k32.CloseHandle(self._h)
            if self._f is not None:
                import fcntl
                fcntl.flock(self._f.fileno(), fcntl.LOCK_UN)
                self._f.close()
        except Exception:
            pass
        self._h = self._f = None


def hand_over_or_lock(cmd: str, files: list, wait: float = 20.0):
    """Auftrag an die laufende Instanz geben – oder die Startsperre holen, um selbst Hauptinstanz zu werden.
        Rückgabe: None = weitergereicht (Prozess kann enden), sonst die gehaltene StartLock (ggf. ohne Sperre)."""
    if send_ex(cmd, files) == "ok":
        return None
    lock = StartLock()
    lock.acquire(wait)
    end = time.monotonic() + 10.0
    while True:                                  # inzwischen ist vielleicht ein anderer Prozess Server geworden
        st = send_ex(cmd, files, timeout=5.0)
        if st == "ok":
            lock.release()
            return None
        if st == "none" or time.monotonic() > end:
            return lock                          # keiner da (oder hängt): selbst übernehmen
        time.sleep(0.2)
