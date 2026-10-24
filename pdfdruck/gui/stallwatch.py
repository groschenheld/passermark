# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Ruckler-Protokoll: merkt, wenn die Oberfläche hängt, und schreibt mit, was das Hauptfenster gerade tut.

Ein Herzschlag im Hauptfenster (alle 100 ms) und ein Wächter-Thread. Bleibt der Herzschlag länger als
THRESHOLD aus, schaut der Wächter alle 50 ms nach, in welcher Funktion das Hauptfenster steckt. Nach dem
Hänger wird eine Zeile mit Dauer und der häufigsten Aufrufkette in  ruckler.txt  (Ordner der
Fehlerprotokolle) geschrieben – zum Mitschicken. Kostet praktisch nichts, solange nichts hängt.
"""
from __future__ import annotations

import collections
import os
import sys
import threading
import time
import traceback

THRESHOLD = 0.4              # s ohne Herzschlag = Hänger
MAX_BYTES = 512 * 1024       # Logdatei klein halten

_paused = 0


class paused:
    """Kein Ruckler, sondern gewollt: z. B. der Original-Treiberdialog von Windows (modal, eigene Nachrichten-
        schleife) – solange er offen ist, schlägt das Herz nicht. Mit  with stallwatch.paused(): …  nicht mitschreiben."""

    def __enter__(self):
        global _paused
        _paused += 1
        return self

    def __exit__(self, *exc):
        global _paused
        _paused = max(0, _paused - 1)
        return False


class StallWatch:
    def __init__(self, log_path: str, context=None):
        self.log_path = log_path
        self.context = context or (lambda: "")
        self.beat = time.monotonic()
        self.main_id = threading.main_thread().ident
        self._stop = threading.Event()
        self.last: dict | None = None          # letzter Hänger (für Tests)

    def start(self, parent):
        from PySide6.QtCore import QTimer
        self._timer = QTimer(parent, interval=100, timeout=self._heartbeat)
        self._timer.start()
        t = threading.Thread(target=self._run, name="passermark-stallwatch", daemon=True)
        t.start()
        return self

    def stop(self):
        self._stop.set()

    def _heartbeat(self):
        self.beat = time.monotonic()

    def _sample(self) -> tuple:
        frame = sys._current_frames().get(self.main_id)
        if frame is None:
            return ()
        stack = traceback.extract_stack(frame)
        # nur eigener Code (pdfdruck) + die innerste Stelle, kurz
        own = [f for f in stack if "pdfdruck" in f.filename.replace("\\", "/")]
        keep = own[-6:] + ([stack[-1]] if stack and (not own or stack[-1] is not own[-1]) else [])
        return tuple(f"{os.path.basename(f.filename)}:{f.lineno} {f.name}" for f in keep)

    def _run(self):
        while not self._stop.wait(0.05):
            lag = time.monotonic() - self.beat
            if lag < THRESHOLD or _paused:
                continue
            start = self.beat
            samples = collections.Counter()
            was_paused = False
            while not self._stop.is_set() and self.beat == start:
                if _paused:
                    was_paused = True
                    time.sleep(0.05)
                    continue
                s = self._sample()
                if s:
                    samples[s] += 1
                time.sleep(0.05)
            dur = time.monotonic() - start - 0.1
            if dur >= THRESHOLD and samples and not was_paused:
                self._write(dur, samples)

    def _write(self, dur, samples: collections.Counter):
        top, n = samples.most_common(1)[0]
        total = sum(samples.values())
        self.last = {"seconds": dur, "stack": top}
        try:
            ctx = self.context()
        except Exception:
            ctx = ""
        line = (time.strftime("%Y-%m-%d %H:%M:%S") + f"  {dur:.1f} s  ({100 * n // max(total, 1)} %)  "
                + " > ".join(top) + (f"  [{ctx}]" if ctx else "") + "\n")
        try:
            if os.path.exists(self.log_path) and os.path.getsize(self.log_path) > MAX_BYTES:
                os.replace(self.log_path, self.log_path + ".1")
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            pass
