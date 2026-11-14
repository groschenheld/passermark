# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Hand a request to the running instance – without Qt, at the very start of the program.

For a multiple selection ("merge into one PDF" on 110 plans) Explorer starts a separate process per file.
If each of them first loaded the whole interface before passing its file on, the files would arrive
spread over seconds. This way every process is gone again within a split second.

Speaks the same protocol as app.Controller (QLocalServer): one JSON line there, "ok" back.
QLocalServer: Windows = named pipe \\\\.\\pipe\\<name>, otherwise Unix socket <TMPDIR or /tmp>/<name>.
"""

from __future__ import annotations

import json
import os
import threading
import time


def server_name() -> str:
    """Name of the local socket of the running instance (one per user)."""
    from .platform import user_id

    return f"passermark-{user_id()}"


def send(cmd: str, files: list, timeout: float = 3.0) -> bool:
    """True = the running instance accepted the request. False = none there (or not reachable)."""
    return send_ex(cmd, files, timeout) == "ok"


def send_ex(cmd: str, files: list, timeout: float = 3.0) -> str:
    """ "ok" = accepted, "none" = no instance there, "busy" = instance there but it has not answered (yet)."""
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
        return "none"  # orphaned socket file after a crash
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
            f = open(path, "r+b", buffering=0)  # noqa: SIM115 – kept by the caller for the lifetime of the connection
        except FileNotFoundError:
            return "none"  # no instance
        except OSError:  # pipe busy right now (many at once): wait briefly
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
    """Start lock across all processes of the user: only the holder may become the server (main instance).

    For a multiple selection Explorer starts one process per file – all at once, none finds an instance.
    Without a lock several of them would become servers (QLocalServer.listen also succeeds on Windows when
    someone is already listening on the name) – each would get only part of the files.
    With the lock: one becomes the server, the others wait (without loading Qt) and then pass on.
    The operating system releases the lock when the process ends (also after a crash).
    """

    def __init__(self):
        self._h = None
        self._f = None

    def acquire(self, timeout: float = 20.0) -> bool:
        """Take the lock, waiting up to ``timeout`` seconds; False if it could not be taken."""
        try:
            if os.name == "nt":
                return self._acquire_win(timeout)
            return self._acquire_posix(timeout)
        except Exception:
            return False  # when in doubt continue without a lock

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
        if r in (0x0, 0x80):  # WAIT_OBJECT_0 / WAIT_ABANDONED (the predecessor crashed)
            self._h, self._k32 = h, k32
            return True
        k32.CloseHandle(h)
        return False

    def _acquire_posix(self, timeout: float) -> bool:
        import fcntl

        path = os.path.join(os.environ.get("TMPDIR") or "/tmp", server_name() + ".startlock")
        f = open(path, "a+")  # noqa: SIM115 – holds the start lock; released by the caller
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
        """Release the lock (safe to call when it is not held)."""
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
    """Give the request to the running instance – or take the start lock to become the main instance.
    Returns: None = passed on (the process can end), otherwise the StartLock held (possibly without a lock).
    """
    if send_ex(cmd, files) == "ok":
        return None
    lock = StartLock()
    lock.acquire(wait)
    end = time.monotonic() + 10.0
    while True:  # another process may have become the server in the meantime
        st = send_ex(cmd, files, timeout=5.0)
        if st == "ok":
            lock.release()
            return None
        if st == "none" or time.monotonic() > end:
            return lock  # nobody there (or hanging): take over ourselves
        time.sleep(0.2)
