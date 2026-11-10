# SPDX-License-Identifier: GPL-3.0-or-later
"""Verlauf für Plan- und Posterdruck (1.18.17): jeder Druck mit Dateien, Mengen, Abweichungen je Plan,
Einstellungen und Drucker – zum Wiederöffnen mit genau diesen Einstellungen.

Die Dateien werden mitgesichert (Kundendateien liegen oft im Hotfolder und sind später weg; bearbeitete Dokumente
gibt es nur im Speicher). Ablage: <Statusordner>/plan_history/<id>/entry.json + Dateien. „Aufräumen“ löscht.
Höchstens MAX_ENTRIES Einträge – die ältesten fallen automatisch weg.
"""
from __future__ import annotations

import json
import os
import shutil
import time

MAX_ENTRIES = 50


def history_dir() -> str:
    from .platform import user_log_dir
    return os.path.join(os.path.dirname(user_log_dir()), "plan_history")


def _entry_path(eid: str) -> str:
    return os.path.join(history_dir(), eid, "entry.json")


def add(kind: str, printer: str, settings: dict, items: list, total_m: float = 0.0, jobs: int = 0) -> dict:
    """Druck merken. items: [{"doc": pdfium-Dokument | None, "source": Pfad, "page", "qty", "ov", "frame",
        "own": vom Fenster selbst aus der Datei geöffnet (dann Datei kopieren, sonst Dokument speichern)}]."""
    os.makedirs(history_dir(), exist_ok=True)
    eid = time.strftime("%Y%m%d-%H%M%S") + f"-{os.getpid() % 1000:03d}"
    d = os.path.join(history_dir(), eid)
    k = 1
    while os.path.exists(d):
        d = os.path.join(history_dir(), f"{eid}-{k}")
        k += 1
    os.makedirs(d)
    eid = os.path.basename(d)
    files, out = {}, []
    for it in items:
        key = id(it.get("doc")) if it.get("doc") is not None else it.get("source", "")
        if key not in files:
            name = f"f{len(files) + 1}.pdf"
            dst = os.path.join(d, name)
            src = it.get("source") or ""
            try:
                if it.get("own") and src and os.path.isfile(src) and src.lower().endswith(".pdf"):
                    try:
                        os.link(src, dst)                       # gleiche Platte: kein Platz extra
                    except OSError:
                        shutil.copy2(src, dst)
                elif it.get("doc") is not None:
                    it["doc"].save(dst)                       # auch bearbeitete/umgewandelte Dokumente
                elif src and os.path.isfile(src):
                    shutil.copy2(src, dst)
                else:
                    name = ""
            except Exception:                                   # noqa: BLE001 – Verlauf darf den Druck nie stören
                name = ""
            files[key] = name
        out.append({"file": files[key], "source": it.get("source") or "", "page": int(it.get("page", 0)),
                    "qty": int(it.get("qty", 1)), "ov": dict(it.get("ov") or {}), "frame": it.get("frame", "")})
    entry = {"id": eid, "time": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": kind, "printer": printer,
             "settings": settings, "items": out, "total_m": round(float(total_m or 0), 3), "jobs": int(jobs or 0)}
    with open(os.path.join(d, "entry.json"), "w", encoding="utf-8") as fh:
        json.dump(entry, fh, ensure_ascii=False, indent=1)
    _trim()
    return entry


def entries(kind: str | None = None) -> list:
    """Neueste zuerst; kind = "plan" | "poster" | None (alle)."""
    root = history_dir()
    out = []
    try:
        names = sorted(os.listdir(root), reverse=True)
    except OSError:
        return []
    for n in names:
        try:
            with open(os.path.join(root, n, "entry.json"), encoding="utf-8") as fh:
                e = json.load(fh)
        except (OSError, ValueError):
            continue
        if isinstance(e, dict) and (kind is None or e.get("kind") == kind):
            out.append(e)
    return out


def file_of(entry: dict, item: dict) -> str:
    """Pfad der gesicherten Datei – sonst die Originaldatei, wenn es sie noch gibt; "" = weg."""
    if item.get("file"):
        p = os.path.join(history_dir(), entry["id"], item["file"])
        if os.path.isfile(p):
            return p
    src = item.get("source") or ""
    return src if src and os.path.isfile(src) else ""


def label(entry: dict) -> str:
    """„09.11. 14:32 · 3 Pläne · ColorWave · 4,2 m“"""
    from .l10n import tr
    from .planprint import num
    t = entry.get("time", "")
    when = f"{t[8:10]}.{t[5:7]}. {t[11:16]}" if len(t) >= 16 else t
    n = sum(1 for _ in entry.get("items", []))
    names = sorted({os.path.basename(i.get("source") or "") for i in entry.get("items", []) if i.get("source")})
    what = (names[0] + (f" +{len(names) - 1}" if len(names) > 1 else "")) if names else \
        (tr("{0} Plan/Pläne") if entry.get("kind") != "poster" else tr("{0} Poster")).format(n)
    parts = [when, what, entry.get("printer", "")]
    if entry.get("total_m"):
        parts.append(f"{num(entry['total_m'])} m")
    return " · ".join(p for p in parts if p)


def remove(eid: str) -> None:
    shutil.rmtree(os.path.join(history_dir(), os.path.basename(eid)), ignore_errors=True)


def clear(kind: str | None = None) -> int:
    """Verlauf aufräumen (nur eine Art oder alles). -> Anzahl gelöschter Einträge."""
    n = 0
    for e in entries(kind):
        remove(e["id"])
        n += 1
    return n


def size_bytes(kind: str | None = None) -> int:
    total = 0
    for e in entries(kind):
        d = os.path.join(history_dir(), e["id"])
        for r, _ds, fs in os.walk(d):
            for f in fs:
                try:
                    total += os.path.getsize(os.path.join(r, f))
                except OSError:
                    pass
    return total


def _trim() -> None:
    for e in entries()[MAX_ENTRIES:]:
        remove(e["id"])
