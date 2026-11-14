# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Page rendering in the background: one render process for the whole program (see renderproc.py).

Scheduling: exactly one request is under way at a time. When it is done, the sources (page views,
thumbnail lists) are asked what they need *now* – so nothing outdated piles up while scrolling or zooming
quickly. The page view comes before the thumbnails, the active window before the others.

If the process cannot be started or dies twice, `ok` becomes False and the sources render in-process as
before (PASSERMARK_RENDER=local forces that, e.g. for troubleshooting).
"""

from __future__ import annotations

import json
import logging
import os
import pickle
import subprocess
import tempfile

from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtGui import QImage

log = logging.getLogger(__name__)


def _clean_leftovers():
    """Intermediate files of the page view from earlier sessions (e.g. after a crash), older than 1 day."""
    import glob
    import time

    for f in glob.glob(os.path.join(tempfile.gettempdir(), "passermark-view-*.pdf")):
        try:
            if time.time() - os.path.getmtime(f) > 86400:
                os.remove(f)
        except OSError:
            pass


class _Reader(QThread):
    """Reads the answers of the render process in a thread."""

    got = Signal(dict, object)  # header, QImage | None
    dead = Signal()

    def __init__(self, stream):
        super().__init__()
        self.stream = stream

    def run(self):
        try:
            while True:
                line = self.stream.readline()
                if not line:
                    break
                head = json.loads(line)
                n = int(head.get("n", 0))
                data = self.stream.read(n) if n else b""
                if n and len(data) < n:
                    break
                img = None
                if n and head.get("ok"):
                    if head.get("fmt") == "pickle":
                        img = pickle.loads(data)  # only from our own process
                    else:
                        fmt = QImage.Format.Format_RGB32 if head.get("fmt") == "bgrx" else QImage.Format.Format_BGR888
                        img = QImage(data, head["w"], head["h"], head["stride"], fmt).copy()
                self.got.emit(head, img)
        except Exception:
            log.warning("Antworten des Render-Prozesses nicht lesbar", exc_info=True)
        self.dead.emit()


class RenderService(QObject):
    """Program-wide render process with a simple scheduler.
    get("render") draws pages; get("analysis") runs the slow checks (preflight, verification after
    editing) in a second process, so a check never holds up the picture and vice versa."""

    _instances: dict = {}

    @classmethod
    def get(cls, name: str = "render") -> RenderService:
        """The shared service with this name (created on first use)."""
        if name not in cls._instances:
            svc = RenderService()
            try:  # always create in the main thread (timers, signals)
                from PySide6.QtWidgets import QApplication

                app = QApplication.instance()
                if app is not None and svc.thread() is not app.thread():
                    svc.moveToThread(app.thread())
            except Exception:  # noqa: BLE001 – no QApplication (tests, CLI)
                pass
            cls._instances[name] = svc
        return cls._instances[name]

    def __init__(self):
        super().__init__()
        self.proc = None
        self.reader = None
        self.ok = os.environ.get("PASSERMARK_RENDER", "") != "local"
        self.restarts = 0
        self.sources: list = []  # objects with render_priority() and next_render() / render_done()
        self.ops: list = []  # open/close – before all image requests
        self.busy = None
        self._id = 0
        self._stderr = None
        self._kick = QTimer(self, singleShot=True, interval=0, timeout=self._pump)
        try:
            from PySide6.QtWidgets import QApplication

            QApplication.instance().aboutToQuit.connect(self.stop)
        except Exception:  # noqa: BLE001 – no QApplication (tests, CLI)
            pass

    # ------------------------------------------------------------------ #
    def start(self) -> bool:
        """Start the render process if it is not running; False if it is not available."""
        if not self.ok:
            return False
        if self.proc is not None and self.proc.poll() is None:
            return True
        _clean_leftovers()
        from .. import platform as _platform
        from ..jobproc import cli_command

        cmd, env_extra = cli_command()
        env = dict(os.environ, **env_extra)
        try:
            self._stderr = tempfile.TemporaryFile(mode="w+b")  # noqa: SIM115 – lives as long as the render process
            self.proc = subprocess.Popen(
                cmd + ["render-server"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self._stderr,
                env=env,
                **_platform.hidden_subprocess_kwargs(),
            )
        except Exception:
            log.warning("Render-Prozess nicht gestartet", exc_info=True)
            self.ok = False
            return False
        self.reader = _Reader(self.proc.stdout)
        self.reader.got.connect(self._on_result)
        self.reader.dead.connect(self._on_dead)
        self.reader.start()
        return True

    def stop(self):
        """End the render process."""
        p, self.proc = self.proc, None
        if p is not None and p.poll() is None:
            try:
                p.stdin.write(b'{"op": "quit"}\n')
                p.stdin.flush()
                p.wait(2)
            except Exception:  # noqa: BLE001 – cleanup
                try:
                    p.kill()
                except Exception:  # noqa: BLE001 – cleanup
                    pass
        if self.reader is not None:
            self.reader.wait(2000)
            self.reader = None

    def _send(self, req: dict, payload: bytes = b"") -> bool:
        try:
            self.proc.stdin.write(json.dumps(req).encode("utf-8") + b"\n" + payload)
            self.proc.stdin.flush()
            return True
        except Exception:  # noqa: BLE001 – process gone: handled by _on_dead
            return False

    # ------------------------------------------------------------------ #
    def register(self, source):
        """Register a source of render requests (a view)."""
        if source not in self.sources:
            self.sources.append(source)

    def unregister(self, source):
        """Remove a source and drop its waiting requests."""
        if source in self.sources:
            self.sources.remove(source)
        self.ops = [o for o in self.ops if o.get("source") is not source]

    def open_doc(self, key: str, path: str, on_done=None):
        """Open a document in the render process under ``key``."""
        self.ops.append({"op": "open", "doc": key, "path": path, "cb": on_done})
        self.kick()

    def close_doc(self, key: str, on_done=None):
        """Close the document ``key`` in the render process."""
        self.ops.append({"op": "close", "doc": key, "cb": on_done})
        self.kick()

    def call(self, fn: str, args: dict, on_done):
        """Run a function in the process (see renderproc.CALLS); on_done(err, result)."""
        self.ops.append({"op": "call", "fn": fn, "args": args, "cb2": on_done})
        self.kick()

    def lists(self, key: str, page: int, kind: str, on_done):
        """Edit mode: text rows ("text") or objects ("objects") of a page."""
        self.ops.append({"op": "lists", "doc": key, "page": page, "kind": kind, "cb2": on_done})
        self.kick()

    def chars(self, key: str, page: int, on_done):
        """Character boxes of a page (for the text cursor without loading the page in the program)."""
        self.ops.append({"op": "chars", "doc": key, "page": page, "cb2": on_done})
        self.kick()

    def kick(self):
        """Schedule sending the next request."""
        if self.ok:
            self._kick.start()

    def _pump(self):
        if self.busy is not None or not self.ok:
            return
        req = None
        if self.ops:
            req = self.ops.pop(0)
        else:
            for src in sorted(self.sources, key=lambda s: s.render_priority()):
                try:
                    r = src.next_render()
                except Exception:
                    log.warning("Render-Anfrage nicht ermittelt", exc_info=True)
                    r = None
                if r:
                    req = dict(r, op="render", source=src)
                    break
        if req is None:
            return
        if not self.start():
            self._fail_all()
            return
        self._id += 1
        req["id"] = self._id
        self.busy = req
        wire = {
            k: v
            for k, v in req.items()
            if k in ("op", "id", "doc", "path", "page", "scale", "rotation", "crop", "fn", "kind", "proof")
        }
        payload = b""
        if req.get("op") == "call":  # arguments can be objects (rows, objects)
            payload = pickle.dumps(req.get("args") or {})
            wire["n"] = len(payload)
        if not self._send(wire, payload):
            self.busy = None
            self._on_dead()

    def _on_result(self, head: dict, img):
        req, self.busy = self.busy, None
        if req is None or head.get("id") != req.get("id"):
            self.kick()
            return
        err = None if head.get("ok") else head.get("error", "?")
        cb = req.get("cb")
        if cb is not None:
            try:
                cb(err) if req.get("op") != "open" else cb(err, img)
            except Exception:
                log.warning("Rückmeldung des Render-Prozesses fehlgeschlagen", exc_info=True)
        cb2 = req.get("cb2")
        if cb2 is not None:
            try:
                cb2(err, img)
            except Exception:
                log.warning("Rückmeldung des Render-Prozesses fehlgeschlagen", exc_info=True)
        src = req.get("source")
        if src is not None and src in self.sources:
            try:
                src.render_done(req, img, err)
            except Exception:
                log.warning("Seitenbild nicht übernommen", exc_info=True)
        self.kick()

    def _on_dead(self):
        """Process gone: restart once (reopen the open documents), the second time render in the program."""
        req, self.busy = self.busy, None
        self._record_death(self.proc, req)
        self.proc = None
        self.restarts += 1
        if req is not None and req.get("cb2") is not None:
            try:
                req["cb2"]("render process ended", None)
            except Exception:
                log.warning("Rückmeldung nach Prozessende fehlgeschlagen", exc_info=True)
        if self.restarts > 2:
            self._fail_all()
            return
        for src in list(self.sources):
            try:
                src.render_reset()  # the source reopens its document
            except Exception:
                log.warning("Dokument nach Neustart nicht neu geöffnet", exc_info=True)
        if req is not None and req.get("source") is not None:
            try:
                req["source"].render_done(req, None, "render process ended")
            except Exception:
                log.warning("Rückmeldung nach Prozessende fehlgeschlagen", exc_info=True)
        self.kick()

    def _record_death(self, proc, req):
        """Unexpected end of the render process -> error log, with the end of its error output."""
        if proc is None:
            return  # stopped on purpose (stop())
        code = proc.poll()
        tail = ""
        if self._stderr is not None:
            try:
                self._stderr.seek(0, os.SEEK_END)
                size = self._stderr.tell()
                self._stderr.seek(max(0, size - 4000))
                tail = self._stderr.read().decode("utf-8", "replace")
            except (OSError, ValueError):
                tail = ""
        from .. import crashlog

        what = f"{req.get('op')} Seite {req.get('page')}" if req else "–"
        crashlog.record(f"Render-Prozess beendet (Code {code}, Anfrage: {what})", tail)

    def _fail_all(self):
        self.ok = False
        for op in self.ops:
            if op.get("cb2") is not None:
                try:
                    op["cb2"]("render process unavailable", None)
                except Exception:
                    log.warning("Rückmeldung (Render-Prozess nicht verfügbar) fehlgeschlagen", exc_info=True)
        self.ops = []
        for src in list(self.sources):
            try:
                src.render_fallback()
            except Exception:
                log.warning("Umschalten auf Rendern im Programm fehlgeschlagen", exc_info=True)
