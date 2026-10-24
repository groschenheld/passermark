# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Drop folders (passermark-cli serve): files dropped into a folder run through a workflow. No Qt.

    Configuration (watch.json) – which folder runs which workflow:
    {
      "passermark": "watch", "version": 1,
      "interval": 5,                      seconds between two scans
      "settle": 5,                        a file counts as complete once size/time stay unchanged this long
      "folders": [
        {"in": "/srv/druck/visitenkarten", "workflow": "Visitenkarten"},
        {"in": "/srv/druck/a4-sw", "workflow": "drucken-a4.json", "patterns": ["*.pdf", "*.jpg"],
         "out": "", "vars": {"kunde": "Muster"}}
      ]
    }

    Per folder: in (required), workflow (name from the workflow folders or JSON file, required),
    out ("output" – results; "" = do not keep a result), done ("processed" – originals afterwards; "" = delete),
    error ("failed" – originals with a .log next to them), patterns (["*.pdf"]), vars ({}), name.
    Relative paths: in/workflow from the folder of watch.json, out/done/error from the "in" folder.
    A workflow that only prints keeps no result unless "out" is given.

    Each file is first claimed (moved to <in>/.passermark/) – several watchers on the same folder never process
    a file twice; after a crash, claimed files go back into the folder on the next start.
    Polling instead of file system notifications: works the same on network shares (SMB/NFS) and Windows.
"""
from __future__ import annotations

import datetime
import fnmatch
import json
import os
import time

from .l10n import tr

KIND = "watch"
VERSION = 1
FILE = "watch.json"
CLAIM = ".passermark"
DEFAULTS = {"out": "output", "done": "processed", "error": "failed"}
_TOP = {"passermark", "version", "interval", "settle", "folders"}
_FOLDER = {"in", "workflow", "out", "done", "error", "patterns", "vars", "name"}
_SKIP = (".part", ".tmp", ".crdownload", ".partial", ".download")


class WatchError(Exception):
    def __init__(self, problems: list):
        super().__init__("; ".join(f"{w}: {m}" if w else m for w, m in problems))
        self.problems = problems


def config_paths() -> list:
    """Where serve looks without --config: own folder first, then the one for all users."""
    from . import presets
    from .platform import config_dir
    return [os.path.join(os.path.dirname(presets.root_dir()), FILE), os.path.join(config_dir(), FILE)]


def find_config(path: str | None = None) -> str:
    if path:
        if not os.path.isfile(path):
            raise FileNotFoundError(tr("Datei nicht gefunden: {0}").format(path))
        return os.path.abspath(path)
    for p in config_paths():
        if os.path.isfile(p):
            return p
    raise FileNotFoundError(tr("Keine Watcher-Einstellung gefunden ({0}) – mit --config angeben.")
                            .format(" · ".join(config_paths())))


def load_config(path: str) -> dict:
    """Read and check watch.json -> {"interval", "settle", "folders": [{…, absolute paths}]}. WatchError lists all
        problems at once."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except ValueError as e:
        raise WatchError([("", tr("kein gültiges JSON: {0}").format(e))])
    base = os.path.dirname(os.path.abspath(path))
    probs = []
    if not isinstance(data, dict):
        raise WatchError([("", tr("Objekt erwartet"))])
    if data.get("passermark") != KIND:
        probs.append(("passermark", tr("muss \"{0}\" sein").format(KIND)))
    ver = data.get("version")
    if not isinstance(ver, int) or isinstance(ver, bool):
        probs.append(("version", tr("Zahl erwartet")))
    elif ver > VERSION:
        probs.append(("version", tr("Einstellung ist für eine neuere Passermark-Version (Format {0}, unterstützt: {1})")
                      .format(ver, VERSION)))
    for k in data:
        if k not in _TOP and not str(k).startswith("_"):       # "_hinweis" … = Kommentar
            probs.append((k, tr("unbekannter Eintrag")))
    out = {"file": os.path.abspath(path), "interval": 5.0, "settle": 5.0, "folders": []}
    for k in ("interval", "settle"):
        v = data.get(k, out[k])
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not 0 <= v <= 3600:
            probs.append((k, tr("Zahl zwischen 0 und 3600 erwartet")))
        else:
            out[k] = float(v)
    fl = data.get("folders")
    if not isinstance(fl, list) or not fl:
        probs.append(("folders", tr("Liste mit mindestens einem Ordner erwartet")))
        fl = []
    seen = set()
    for i, f in enumerate(fl):
        w = f"folders[{i}]"
        if not isinstance(f, dict):
            probs.append((w, tr("Objekt erwartet")))
            continue
        for k in f:
            if k not in _FOLDER and not str(k).startswith("_"):
                probs.append((f"{w}.{k}", tr("unbekannter Eintrag")))
        d = {}
        for k in ("in", "workflow"):
            v = f.get(k)
            if not isinstance(v, str) or not v.strip():
                probs.append((f"{w}.{k}", tr("fehlt")))
                v = ""
            d[k] = v.strip()
        d["in"] = os.path.normpath(os.path.join(base, os.path.expanduser(d["in"]))) if d["in"] else ""
        wfr = d["workflow"]
        if wfr and not os.path.isabs(wfr) and (wfr.lower().endswith(".json") or "/" in wfr or os.sep in wfr):
            cand = os.path.join(base, wfr)
            if os.path.isfile(cand):
                wfr = cand
        d["workflow"] = wfr
        for k, dflt in DEFAULTS.items():
            v = f.get(k, dflt)
            if v is None:
                v = ""
            if not isinstance(v, str):
                probs.append((f"{w}.{k}", tr("Text erwartet")))
                v = dflt
            d[k] = (os.path.normpath(os.path.join(d["in"], os.path.expanduser(v))) if v else "")
            if k == "error" and not v:
                probs.append((f"{w}.error", tr("Fehler-Ordner darf nicht leer sein")))
        d["out_given"] = "out" in f
        pats = f.get("patterns", ["*.pdf"])
        if isinstance(pats, str):
            pats = [pats]
        if not isinstance(pats, list) or not pats or not all(isinstance(p, str) and p for p in pats):
            probs.append((f"{w}.patterns", tr("Liste von Mustern erwartet, z. B. [\"*.pdf\"]")))
            pats = ["*.pdf"]
        d["patterns"] = pats
        vs = f.get("vars", {})
        if not isinstance(vs, dict) or not all(isinstance(v, (str, int, float)) for v in vs.values()):
            probs.append((f"{w}.vars", tr("Objekt mit Texten erwartet")))
            vs = {}
        d["vars"] = {str(k): str(v) for k, v in vs.items()}
        d["name"] = str(f.get("name") or os.path.basename(d["in"]) or w)
        if d["in"]:
            key = os.path.normcase(d["in"])
            if key in seen:
                probs.append((f"{w}.in", tr("Ordner ist doppelt eingetragen")))
            seen.add(key)
            for k in ("out", "done"):
                if d[k] and os.path.normcase(d[k]) == key:
                    probs.append((f"{w}.{k}", tr("darf nicht der Eingangsordner selbst sein")))
        out["folders"].append(d)
    if probs:
        raise WatchError(probs)
    return out


def init_config(system: bool = False) -> tuple[str, bool, list]:
    """Vorlage watch.json anlegen (eigene, mit system=True die für alle) – NIE überschreiben.
        -> (Pfad, neu angelegt?, angelegte Dateien/Ordner). Dazu ein harmloser Beispiel-Ablauf (verkleinern) und der
        Beispiel-Ordner – nur wenn es sie noch nicht gibt."""
    from .platform import IS_WIN
    path = config_paths()[1 if system else 0]
    if os.path.exists(path):
        return path, False, []
    base = os.path.dirname(path)
    if system:
        drop = "C:/Hotfolder/beispiel" if IS_WIN else "/srv/passermark/hotfolder/beispiel"
    else:
        drop = os.path.abspath(os.path.join(os.path.expanduser("~"), "hotfolder", "beispiel")).replace("\\", "/")
    made = []
    os.makedirs(base, exist_ok=True)
    wf = os.path.join(base, "beispiel-verkleinern.json")
    if not os.path.exists(wf):
        with open(wf, "w", encoding="utf-8") as f:
            json.dump({"passermark": "workflow", "version": 1, "name": "Beispiel: verkleinern",
                       "description": "Harmloser Test für den Watcher – das Ergebnis landet in output/",
                       "steps": [{"job": "shrink"}]}, f, ensure_ascii=False, indent=2)
        made.append(wf)
    data = {
        "_hinweis": "Vorlage – je Ordner: in (Drop-Ordner), workflow (Name aus den Ablauf-Ordnern oder JSON-Datei); "
                    "optional out/done/error (Standard output/processed/failed, \"\" = kein Ergebnis bzw. löschen), "
                    "patterns, vars, name. Prüfen: passermark-cli serve --check",
        "passermark": KIND, "version": VERSION,
        "interval": 5, "settle": 5,
        "folders": [{"in": drop, "workflow": "beispiel-verkleinern.json", "name": "Beispiel"}],
    }
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    if os.path.exists(path):                     # inzwischen von woanders angelegt: nichts überschreiben
        os.remove(tmp)
        return path, False, made
    os.replace(tmp, path)
    made.insert(0, path)
    try:
        os.makedirs(drop, exist_ok=True)
        made.append(drop)
    except OSError:
        pass
    return path, True, made


def check(cfg: dict) -> list:
    """Check every folder and its workflow without running anything. -> [(where, message)]."""
    from . import workflow
    probs = []
    for i, f in enumerate(cfg["folders"]):
        w = f"folders[{i}]"
        if not os.path.isdir(f["in"]):
            probs.append((f"{w}.in", tr("Ordner nicht gefunden: {0}").format(f["in"])))
        try:
            path = workflow.find(f["workflow"])
            data = workflow.load(path)
            dummy = os.path.join(f["in"], "datei.pdf")
            workflow.prepare(data, os.path.dirname(os.path.abspath(path)), [dummy],
                             _output_for(f, data, dummy), _vars(f, dummy), check_files=False)
        except FileNotFoundError as e:
            probs.append((f"{w}.workflow", str(e)))
        except workflow.WorkflowError as e:
            probs += [(f"{w}.workflow: {p}" if p else f"{w}.workflow", m) for p, m in e.problems]
    return probs


def _vars(f: dict, src: str) -> dict:
    """Built-in variables refer to the dropped file in its folder (not the claim folder)."""
    v = dict(f["vars"])
    v.update({"dir": f["in"], "stem": os.path.splitext(os.path.basename(src))[0], "folder": f["name"]})
    if f["out"]:
        v["out"] = f["out"]
    return v


def _prints_only(data: dict) -> bool:
    from .workflow import PRINT
    steps = data.get("steps") if isinstance(data.get("steps"), list) else []
    return bool(steps) and all(isinstance(s, dict) and s.get("job") == PRINT for s in steps)


def _output_for(f: dict, data: dict, src: str) -> str | None:
    """Result file in the out folder – never next to the dropped file (it would be picked up again)."""
    if not f["out"] or (_prints_only(data) and not f["out_given"]):
        return None
    return _unique(os.path.join(f["out"], os.path.splitext(os.path.basename(src))[0] + ".pdf"))


def _unique(path: str) -> str:
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    n = 1
    while os.path.exists(f"{stem}-{n}{ext}"):
        n += 1
    return f"{stem}-{n}{ext}"


def _move(src: str, folder: str, name: str) -> str:
    os.makedirs(folder, exist_ok=True)
    dst = _unique(os.path.join(folder, name))
    os.replace(src, dst)
    return dst


class Watcher:
    """events(dict): {"event": "watch_start" | "file" | "step" | "progress" | "step_done" | "file_done" |
        "file_failed" | "idle", …}. cancel(): True = stop (the current file goes back into its folder)."""

    def __init__(self, cfg: dict, events=None, cancel=None):
        self.cfg, self.events, self.cancel = cfg, events, cancel or (lambda: False)
        self.seen = {}                       # path -> (size, mtime, since)
        self.counts = {"done": 0, "failed": 0}

    def emit(self, **ev):
        if self.events is not None:
            self.events(ev)

    def recover(self) -> int:
        """Files still claimed from an earlier run (crash, power cut) go back into their folder."""
        n = 0
        for f in self.cfg["folders"]:
            cd = os.path.join(f["in"], CLAIM)
            try:
                names = os.listdir(cd)
            except OSError:
                continue
            for name in names:
                try:
                    _move(os.path.join(cd, name), f["in"], name)
                    n += 1
                except OSError:
                    pass
        return n

    def _ready(self, f: dict) -> list:
        """Complete files matching the patterns (size and time unchanged for `settle` seconds)."""
        now = time.monotonic()
        out = []
        try:
            entries = list(os.scandir(f["in"]))
        except OSError:
            return out
        present = {e.path for e in entries}
        for p in [p for p in self.seen if os.path.dirname(p) == f["in"] and p not in present]:
            del self.seen[p]                     # weg (umbenannt, gelöscht, von einem anderen Watcher geholt)
        for e in entries:
            name = e.name
            if name.startswith((".", "~")) or name.lower().endswith(_SKIP):
                continue
            if not any(fnmatch.fnmatch(name.lower(), p.lower()) for p in f["patterns"]):
                continue
            try:
                if not e.is_file():
                    continue
                st = e.stat()
            except OSError:
                continue
            sig = (st.st_size, st.st_mtime_ns)
            old = self.seen.get(e.path)
            if old is None or old[:2] != sig:
                self.seen[e.path] = (*sig, now)
                if self.cfg["settle"] > 0:
                    continue
            elif now - old[2] < self.cfg["settle"]:
                continue
            out.append(e.path)
        return sorted(out, key=lambda p: self.seen[p][2])

    def scan_once(self) -> int:
        """One pass over all folders. -> number of files processed."""
        n = 0
        for f in self.cfg["folders"]:
            for path in self._ready(f):
                if self.cancel():
                    return n
                self.seen.pop(path, None)
                if self.process(f, path):
                    n += 1
        return n

    def process(self, f: dict, path: str) -> bool:
        from . import core, workflow
        name = os.path.basename(path)
        try:
            os.makedirs(os.path.join(f["in"], CLAIM), exist_ok=True)
            work = os.path.join(f["in"], CLAIM, name)
            if os.path.exists(work):
                work = _unique(work)
            os.replace(path, work)                   # claim: still being written / someone else was faster -> skip
        except OSError:
            return False
        t0 = time.monotonic()
        self.emit(event="file", folder=f["name"], file=path, workflow=f["workflow"])
        try:
            wf = workflow.find(f["workflow"])
            data = workflow.load(wf)
            out = _output_for(f, data, path)
            plan = workflow.prepare(data, os.path.dirname(os.path.abspath(wf)), [work], out, _vars(f, path))
            if plan.output and os.path.normcase(os.path.dirname(plan.output)) == os.path.normcase(f["in"]):
                raise ValueError(tr("Das Ergebnis würde wieder im Eingangsordner landen – \"out\" angeben."))

            def ev(e):
                self.emit(**dict(e, file=path))
            from . import printlog
            with printlog.source("watch"):
                r = workflow.run(plan, ev, cancel=self.cancel, variables=_vars(f, path))
        except (core.Cancelled, KeyboardInterrupt):
            _move(work, f["in"], name)
            raise
        except Exception as e:                       # noqa: BLE001 – every cause ends up in the failed folder
            probs = getattr(e, "problems", None) or []
            msg = str(e) if not probs else tr("Ablauf ungültig ({0} Problem(e))").format(len(probs))
            try:
                moved = _move(work, f["error"], name)
                with open(moved + ".log", "w", encoding="utf-8") as fh:
                    fh.write(f"{datetime.datetime.now().isoformat(timespec='seconds')}  {f['workflow']}\n{msg}\n")
                    for w, m in probs:
                        fh.write(f"  {w or '–'}: {m}\n")
            except OSError as e2:
                moved = work
                msg += f" ({e2})"
            self.counts["failed"] += 1
            self.emit(event="file_failed", folder=f["name"], file=path, moved_to=moved, message=msg,
                      problems=[{"where": w, "message": m} for w, m in probs])
            return True
        if f["done"]:
            moved = _move(work, f["done"], name)
        else:
            os.remove(work)
            moved = None
        self.counts["done"] += 1
        self.emit(event="file_done", folder=f["name"], file=path, output=r["output"], moved_to=moved,
                  pages=r["pages"], notes=r["notes"], seconds=round(time.monotonic() - t0, 1),
                  prints=[{"printer": s["info"].get("printer"), "job_id": s["info"].get("job_id"),
                           "dry_run": s["info"].get("dry_run")} for s in r["steps"] if s["job"] == workflow.PRINT])
        return True

    def run(self, once: bool = False):
        """Scan until cancel() – once=True: process what is there (waiting for settle) and return."""
        n = self.recover()
        self.emit(event="watch_start", config=self.cfg["file"], recovered=n,
                  folders=[{"name": f["name"], "in": f["in"], "workflow": f["workflow"]} for f in self.cfg["folders"]])
        if once:
            deadline = None
            while not self.cancel():
                self.scan_once()
                pending = bool(self.seen)
                if not pending:
                    break
                if deadline is None:
                    deadline = time.monotonic() + self.cfg["settle"] + 60
                if time.monotonic() > deadline:
                    break
                time.sleep(min(0.5, max(0.05, self.cfg["settle"] / 4)))
            return self.counts
        while not self.cancel():
            self.scan_once()
            t = time.monotonic() + self.cfg["interval"]
            while time.monotonic() < t and not self.cancel():
                time.sleep(min(0.5, self.cfg["interval"] or 0.5))
        return self.counts
