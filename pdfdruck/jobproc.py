# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Aufträge als eigener Prozess: die Oberfläche startet die Kommandozeile im Hintergrund.

- kein Einfrieren der Oberfläche, echte Parallelität (eigener Prozess, eigenes pdfium)
- ein Absturz in der Berechnung reißt das Programm nicht mit
- Fortschritt über --json-progress, Abbrechen sauber (SIGTERM; Windows: beenden + aufräumen)
- ohne Qt – die Oberfläche liest die Meldungen in einem Lese-Thread (nur Text, kein pdfium)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

from . import core, platform as _platform
from .l10n import tr


def cli_command() -> tuple[list[str], dict]:
    """Aufruf der Kommandozeile für diese Installation: (Befehl, zusätzliche Umgebung)."""
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        cli_exe = os.path.join(exe_dir, "passermark-cli.exe")
        if _platform.IS_WIN and os.path.isfile(cli_exe):
            return [cli_exe], {}                  # Windows: Konsolen-EXE (die Fenster-EXE hat keine Ausgabe)
        return [sys.executable, "--cli"], {}      # AppImage / gebündelt: Programmdatei mit --cli
    pkg_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pp = os.environ.get("PYTHONPATH", "")
    return [sys.executable, "-m", "pdfdruck.cli"], {"PYTHONPATH": pkg_parent + (os.pathsep + pp if pp else "")}


class JobProcess:
    """Einen Auftrag als eigenen Prozess ausführen.

        job = JobProcess("cutcontour", "ein.pdf", "aus.pdf", {"shape": "rect"})
        job.start()
        for ev in job.events():          # {"event": "progress", "done": 1, "total": 3, "text": …}
            …
        result = job.wait()              # {"event": "done" | "error" | "cancelled", …}
    """

    def __init__(self, kind: str, src: str, dst: str, settings: dict | None = None,
                 pages: list[int] | None = None, lang: str | None = None):
        core.settings_class(kind)                 # unbekannter Auftrag -> sofort ValueError
        self.kind, self.src, self.dst = kind, src, dst
        self.settings = settings or {}
        self.pages = pages
        self.lang = lang
        self.proc: subprocess.Popen | None = None
        self.last: dict | None = None
        self.cancelled = False
        self._preset = None
        self._stderr_file = None

    # ------------------------------------------------------------------ #
    def command(self) -> tuple[list[str], dict]:
        cmd, env_extra = cli_command()
        fd, self._preset = tempfile.mkstemp(prefix="passermark-job-", suffix=".json")
        os.close(fd)
        core.save_settings(self._preset, self.kind, self.settings)    # Datei statt --set: keine Quoting-Probleme
        args = [self.kind, self.src, self.dst, "--preset", self._preset, "--json-progress"]
        if self.pages:
            args += ["--pages", ",".join(str(p + 1) for p in self.pages)]
        return cmd + args, env_extra

    def start(self):
        cmd, env_extra = self.command()
        env = dict(os.environ, **env_extra)
        if self.lang:
            env["PASSERMARK_LANG"] = self.lang
        env["PYTHONIOENCODING"] = "utf-8"
        self._stderr_file = tempfile.TemporaryFile(mode="w+b")      # stderr nicht volllaufen lassen (kein Pipe-Stau)
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=self._stderr_file, stdin=subprocess.DEVNULL,
                                     env=env, **_platform.hidden_subprocess_kwargs())

    def events(self):
        """Meldungen des Prozesses, bis er endet (blockiert – in einem Lese-Thread aufrufen)."""
        assert self.proc is not None and self.proc.stdout is not None
        for raw in self.proc.stdout:
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                ev = {"event": "log", "text": line}
            if ev.get("event") in ("done", "error", "cancelled"):
                self.last = ev
            yield ev

    def cancel(self):
        """Abbrechen: Unix sauber per SIGTERM (die Kommandozeile räumt selbst auf), Windows beenden."""
        self.cancelled = True
        if self.proc is None or self.proc.poll() is not None:
            return
        try:
            self.proc.terminate()
        except OSError:
            pass

    def wait(self, timeout: float | None = None) -> dict:
        """Auf das Ende warten; liefert das Ergebnis (auch bei Absturz ohne eigene Meldung)."""
        assert self.proc is not None
        try:
            code = self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            code = self.proc.wait()
        if self.proc.stdout is not None:
            for _ in self.events():               # restliche Meldungen einsammeln
                pass
        err = self._stderr_tail()
        self._cleanup()
        if self.last is not None and not (self.cancelled and self.last.get("event") != "cancelled"):
            res = dict(self.last)
        elif self.cancelled:
            res = {"event": "cancelled", "message": tr("Abgebrochen.")}
        else:                                     # Absturz: keine Abschlussmeldung
            res = {"event": "error", "message": tr("Die Berechnung wurde unerwartet beendet (Code {0}).").format(code)}
        res["returncode"] = code
        if err:
            res["details"] = err
        if res["event"] != "done":
            for p in (self.dst, self.dst + ".part", self.dst + ".part.pdf"):
                if res["event"] == "cancelled" or p != self.dst:
                    try:
                        os.remove(p)
                    except OSError:
                        pass
        return res

    def run(self, on_event=None) -> dict:
        """Alles in einem (für Skripte/Tests): starten, Meldungen weiterreichen, Ergebnis liefern."""
        self.start()
        for ev in self.events():
            if on_event is not None:
                on_event(ev)
        return self.wait()

    # ------------------------------------------------------------------ #
    def _stderr_tail(self, limit: int = 4000) -> str:
        f = self._stderr_file
        if f is None:
            return ""
        try:
            f.seek(0)
            data = f.read().decode("utf-8", "replace").strip()
        except (OSError, ValueError):
            return ""
        return data[-limit:]

    def _cleanup(self):
        if self._preset and os.path.exists(self._preset):
            try:
                os.remove(self._preset)
            except OSError:
                pass
        self._preset = None
        if self._stderr_file is not None:
            try:
                self._stderr_file.close()
            except OSError:
                pass
            self._stderr_file = None
