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
    msg = (json.dumps({"cmd": cmd, "files": files}) + "\n").encode("utf-8")
    try:
        if os.name == "nt":
            return _send_pipe(msg, timeout)
        return _send_unix(msg, timeout)
    except Exception:
        return False


def _send_unix(msg: bytes, timeout: float) -> bool:
    import socket
    path = os.path.join(os.environ.get("TMPDIR") or "/tmp", server_name())
    if not os.path.exists(path):
        return False
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(path)
        s.sendall(msg)
        return s.recv(16).startswith(b"ok")
    except OSError:
        return False
    finally:
        s.close()


def _send_pipe(msg: bytes, timeout: float) -> bool:
    path = "\\\\.\\pipe\\" + server_name()
    f = None
    end = time.monotonic() + 1.0
    while f is None:
        try:
            f = open(path, "r+b", buffering=0)
        except FileNotFoundError:
            return False                         # keine Instanz
        except OSError:                          # Pipe gerade belegt (viele gleichzeitig): kurz warten
            if time.monotonic() > end:
                return False
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
    return bytes(res.get("reply") or b"").startswith(b"ok")
