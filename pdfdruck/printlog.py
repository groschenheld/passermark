# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Print log: every print job with its exact settings – one JSON file per job plus printlog.csv. No Qt.

    On: user setting (File → Settings) or forced by the administrator (admin settings "print_log").
    Folder: admin "print_log.dir", otherwise Linux ~/.local/state/passermark/printlog,
    Windows %LOCALAPPDATA%\\Passermark\\printlog – in it YYYY-MM/<time>_<file>.json and printlog.csv.

    Each log holds a ready workflow ("workflow") that prints the job again exactly like this:
    passermark-cli reprint <log.json> [--in other.pdf] [--dry-run]
"""
from __future__ import annotations

import contextlib
import csv
import dataclasses
import datetime
import getpass
import hashlib
import json
import os
import re
import socket
import time

KIND = "printlog"
VERSION = 1
FOLDER = "printlog"
CSV_NAME = "printlog.csv"
_CSV_HEAD = ["time", "user", "host", "source", "file", "pages", "printer", "paper", "tray", "copies", "job_id",
             "result", "log", "roll_mm", "run_m"]       # Rolle/Laufmeter: Plandruck (seit 1.18)

_ctx = {"source": "dialog",          # Quelle des laufenden Auftrags (dialog | cli | watch | rightclick)
        "inputs": None, "before": None}   # im Ablauf: Original-Eingaben und die Schritte vor dem Druck
_pruned = {"dir": None}


@contextlib.contextmanager
def source(name: str):
    """Mark the print jobs inside this block (e.g. the watcher): with printlog.source("watch"): …"""
    old = _ctx["source"]
    _ctx["source"] = name
    try:
        yield
    finally:
        _ctx["source"] = old


@contextlib.contextmanager
def in_workflow(inputs: list, before: list):
    """Druck mitten in einem Ablauf: geprotokolliert werden die Original-Eingaben und die Schritte davor – der
        Nachdruck rechnet sie wieder durch (die Zwischendatei gibt es danach nicht mehr)."""
    old = (_ctx["inputs"], _ctx["before"])
    _ctx["inputs"], _ctx["before"] = list(inputs), list(before)
    try:
        yield
    finally:
        _ctx["inputs"], _ctx["before"] = old


def current() -> str:
    return _ctx["source"]


def admin_cfg(cfg: dict | None = None) -> dict:
    if cfg is None:
        from . import config
        cfg = config.load()
    pl = cfg.get("print_log") or {}
    return pl if isinstance(pl, dict) else {}


def enabled(cfg: dict | None = None) -> bool:
    if admin_cfg(cfg).get("force"):
        return True
    try:
        from . import l10n
        return bool(l10n.load_settings().get("print_log", False))
    except Exception:
        return False


def folder(cfg: dict | None = None) -> str:
    d = str(admin_cfg(cfg).get("dir") or "").strip()
    if d:
        return os.path.expandvars(os.path.expanduser(d))
    from .platform import user_log_dir
    return os.path.join(os.path.dirname(user_log_dir()), FOLDER)


def _pages_text(pages) -> str:
    """[0, 1, 2, 4] -> "1-3,5"."""
    out, run = [], []
    for p in sorted({int(p) for p in pages or []}):
        if run and p == run[-1] + 1:
            run.append(p)
            continue
        if run:
            out.append(f"{run[0] + 1}-{run[-1] + 1}" if len(run) > 1 else f"{run[0] + 1}")
        run = [p]
    if run:
        out.append(f"{run[0] + 1}-{run[-1] + 1}" if len(run) > 1 else f"{run[0] + 1}")
    return ",".join(out)


def _sha256(path: str) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def build(caps, printer: str, file: str | None, title: str, pages, settings, values: dict, copies: int,
          collate: bool, reverse: bool, color: tuple, job_id, error: str | None = None, sheet_mm=None) -> dict:
    """The log entry (dict). values = driver values as sent (incl. tray, step-2 paper)."""
    opts = {k: str(v) for k, v in caps.job_options(values).items()} if caps is not None else {}
    lay = dataclasses.asdict(settings) if dataclasses.is_dataclass(settings) else dict(settings or {})
    pkey = caps.roles.get("pagesize") if caps is not None else None
    skey = caps.roles.get("source") if caps is not None else None
    pid, intent = color or ("", "")
    now = datetime.datetime.now().astimezone()
    try:
        user = getpass.getuser()
    except Exception:
        user = ""
    if _ctx["inputs"]:                       # im Ablauf: die Datei ist eine Zwischenstufe
        file = _ctx["inputs"][0]
    entry = {
        "time": now.isoformat(timespec="seconds"),
        "user": user,
        "host": socket.gethostname(),
        "source": _ctx["source"],
        "file": os.path.abspath(file) if file else None,
        "file_sha256": _sha256(file) if file else None,
        "title": title,
        "pages": _pages_text(pages),
        "printer": printer,
        "backend": getattr(caps, "backend", ""),
        "paper": values.get(pkey) if pkey else None,
        "tray": values.get(skey) if skey else None,
        "sheet_mm": sheet_mm,
        "copies": int(copies),
        "collate": bool(collate),
        "reverse": bool(reverse),
        "options": opts,
        "vendor_settings": bool(values.get("__devmode__")),
        "color_profile": pid or None,
        "intent": intent or None,
        "layout": lay,
        "job_id": job_id,
        "result": "error" if error else "sent",
        "error": error,
    }
    st = {"printer": printer, "options": opts, "copies": int(copies), "collate": bool(collate),
          "reverse": bool(reverse), "layout": lay, "profile": pid or "none", "intent": intent or "",
          "auto_tray": False, "title": title}
    step = {"job": "print", "settings": st}
    if entry["pages"]:
        step["pages"] = entry["pages"]
    wf = {"passermark": "workflow", "version": 1,
          "name": f"Reprint {os.path.basename(file or title)} {now:%Y-%m-%d %H:%M}",
          "steps": list(_ctx["before"] or []) + [step]}
    if _ctx["inputs"]:
        wf["input"] = [os.path.abspath(p) for p in _ctx["inputs"]]
        entry["files"] = wf["input"]
        entry["steps_before"] = [b.get("job") for b in _ctx["before"] or []]
    elif file:
        wf["input"] = os.path.abspath(file)
    return {"passermark": KIND, "version": VERSION, "job": entry, "workflow": wf}


def write(rec: dict, cfg: dict | None = None) -> str | None:
    """Write the log (JSON + a line in printlog.csv). Never raises – a print must not fail because of its log."""
    try:
        base = folder(cfg)
        e = rec["job"]
        t = datetime.datetime.fromisoformat(e["time"])
        d = os.path.join(base, f"{t:%Y-%m}")
        os.makedirs(d, exist_ok=True)
        stem = re.sub(r"[^\w.\-]+", "_", os.path.basename(e.get("file") or e.get("title") or "job"))[:60]
        path = os.path.join(d, f"{t:%Y-%m-%d_%H-%M-%S}_{stem}.json")
        n = 1
        while os.path.exists(path):
            path = os.path.join(d, f"{t:%Y-%m-%d_%H-%M-%S}_{stem}-{n}.json")
            n += 1
        tmp = path + ".part"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        csv_path = os.path.join(base, CSV_NAME)
        new = not os.path.exists(csv_path)
        if not new:
            _upgrade_csv(csv_path)
        with open(csv_path, "a", encoding="utf-8-sig" if new else "utf-8", newline="") as f:
            w = csv.writer(f, delimiter=";")
            if new:
                w.writerow(_CSV_HEAD)
            w.writerow([e["time"], e["user"], e["host"], e["source"], e.get("file") or e.get("title"), e["pages"],
                        e["printer"], e.get("paper") or "", e.get("tray") or "", e["copies"], e.get("job_id") or "",
                        e["result"] + (f": {e['error']}" if e.get("error") else ""), os.path.relpath(path, base),
                        _num(e.get("roll_mm")), _num(e.get("run_m"))])
        _prune(base, cfg)
        return path
    except Exception:
        return None


def _num(v) -> str:
    """Zahl für die CSV (leer, wenn nicht vorhanden)."""
    if v is None or v == "":
        return ""
    return f"{float(v):g}"


def _upgrade_csv(path: str) -> None:
    """Ältere printlog.csv (ohne Rolle/Laufmeter): Kopfzeile ergänzen, damit neue Spalten benannt sind."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            first = f.readline()
            if "run_m" in first or not first.startswith("time;"):
                return
            rest = f.read()
        tmp = path + ".part"
        with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
            f.write(first.rstrip("\r\n") + ";roll_mm;run_m\r\n" + rest)
        os.replace(tmp, path)
    except OSError:
        pass


def _prune(base: str, cfg: dict | None = None) -> None:
    """Delete logs older than print_log.keep_days (admin; 0 = never) – once per program run and folder."""
    if _pruned["dir"] == base:
        return
    _pruned["dir"] = base
    try:
        days = int(admin_cfg(cfg).get("keep_days") or 0)
    except (TypeError, ValueError):
        days = 0
    if days <= 0:
        return
    limit = time.time() - days * 86400
    for root, dirs, files in os.walk(base):
        for f in files:
            if f.endswith(".json"):
                p = os.path.join(root, f)
                try:
                    if os.path.getmtime(p) < limit:
                        os.remove(p)
                except OSError:
                    pass
        for d in dirs:
            try:
                os.rmdir(os.path.join(root, d))          # nur leere Monatsordner
            except OSError:
                pass


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        rec = json.load(f)
    if not isinstance(rec, dict) or rec.get("passermark") != KIND or not isinstance(rec.get("workflow"), dict):
        from .l10n import tr
        raise ValueError(tr("„{0}“ ist kein Druckprotokoll.").format(os.path.basename(path)))
    return rec
