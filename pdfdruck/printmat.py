# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Print materials for roll printers (plan & poster): main category, then the settings per material.

    category  plan (production print, usually 75/80 g) | quality (posters, photo paper, PVC …)
    per material: grammage (selects the roll), the driver's media type and print quality, ink amount/density
    (driver option, if the driver has one), colour profile (its ink limit is the real limit), max. ink coverage
    as a guide value, extra driver options; for cutters force and speed.

Stored per user (no admin rights): print_materials.json next to the settings. Standard material per printer and
category: setting "print_material_default". No Qt.
"""
from __future__ import annotations

import copy
import json
import os
import re

from .l10n import tr

CATEGORIES = ("plan", "quality")
FIELDS = ("id", "name", "category", "printer", "weight", "media", "quality", "density_key", "density", "options",
          "profile", "intent", "tac", "notes", "cut_force", "cut_speed",
          "source", "updated", "checked", "color_mode")            # 1.18.11
SOURCES = ("hand", "device", "import")   # woher das Material kommt
COLOR_MODES = ("convert", "embed", "none")
# convert: Passermark wandelt ins Profil um, das Gerät soll nicht mehr umrechnen (sicherster Weg, Standard)
# embed:   Profil nur als Output Intent einbetten – das Gerät/der RIP wendet es an
# none:    unverändert senden – Farbe macht ganz das Gerät
DEFAULTS_KEY = "print_material_default"
MAX = 300
DENSITY = re.compile(r"densit|dichte|tintenmenge|farbmenge|ink\s*(amount|level|volume|densit)|inkdens|"
                     r"EPIJ_Dens|CNInk|ColorDensity|Saturation", re.I)


def materials_file() -> str:
    from .usercolor import user_dir
    return os.path.join(user_dir(), "print_materials.json")


def _clean(m: dict) -> dict | None:
    if not isinstance(m, dict) or not str(m.get("name") or "").strip():
        return None
    out = {k: copy.deepcopy(m[k]) for k in FIELDS if k in m}
    out["name"] = str(out["name"]).strip()[:80]
    out["id"] = str(out.get("id") or new_id(out["name"], []))[:80]
    out["category"] = out.get("category") if out.get("category") in CATEGORIES else "quality"
    out["printer"] = str(out.get("printer") or "")
    for k in ("weight", "tac", "cut_force", "cut_speed"):
        try:
            out[k] = max(0, min(5000, int(out.get(k) or 0)))
        except (TypeError, ValueError):
            out[k] = 0
    for k in ("media", "quality", "density_key", "density", "profile", "intent", "notes", "updated"):
        out[k] = str(out.get(k) or "")
    out["source"] = out.get("source") if out.get("source") in SOURCES else "hand"
    out["checked"] = bool(out["checked"]) if "checked" in out else out["source"] == "hand"
    out["color_mode"] = out.get("color_mode") if out.get("color_mode") in COLOR_MODES else "convert"
    o = out.get("options")
    out["options"] = {str(k): str(v) for k, v in o.items()} if isinstance(o, dict) else {}
    return out


def new_id(name: str, existing) -> str:
    base = "m_" + (re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:40] or "material")
    ids = {e.get("id") for e in existing or []}
    i, cand = 1, base
    while cand in ids:
        i += 1
        cand = f"{base}_{i}"
    return cand


def load() -> list:
    try:
        with open(materials_file(), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return []
    lst = d.get("materials") if isinstance(d, dict) else d
    out, seen = [], set()
    for m in lst if isinstance(lst, list) else []:
        c = _clean(m)
        if c is not None and c["id"] not in seen:
            seen.add(c["id"])
            out.append(c)
    return out[:MAX]


def save(mats: list) -> None:
    """Speichern; geänderte (und neue) Materialien bekommen das heutige Datum als Stand."""
    import datetime
    clean = [c for c in (_clean(m) for m in mats) if c is not None][:MAX]
    old = {m["id"]: m for m in load()}
    today = datetime.date.today().isoformat()
    for c in clean:
        o = old.get(c["id"])
        same = o is not None and {k: v for k, v in o.items() if k != "updated"} == \
            {k: v for k, v in c.items() if k != "updated"}
        if not same or not c.get("updated"):
            c["updated"] = c.get("updated") if (same and c.get("updated")) else today
    p = materials_file()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "materials": clean}, f, indent=2, ensure_ascii=False)
    os.replace(tmp, p)


def for_printer(printer: str, category: str | None = None) -> list:
    return [m for m in load() if (not m["printer"] or m["printer"] == printer)
            and (category is None or m["category"] == category)]


def find(ref: str, printer: str = "") -> dict | None:
    """Material nach ID oder Name (ohne Groß/klein), für diesen Drucker oder für alle."""
    if not ref:
        return None
    r = str(ref).strip().lower()
    cands = [m for m in load() if m["id"].lower() == r or m["name"].lower() == r]
    if printer:
        own = [m for m in cands if m["printer"] == printer]
        cands = own or [m for m in cands if not m["printer"]] or cands
    return cands[0] if cands else None


def default_for(printer: str, category: str) -> str:
    from . import l10n
    d = (l10n.load_settings().get(DEFAULTS_KEY) or {}).get(printer) or {}
    mid = d.get(category, "") if isinstance(d, dict) else ""
    return mid if find(mid, printer) else ""


def set_default(printer: str, category: str, mid: str) -> None:
    from . import l10n
    st = l10n.load_settings()
    allp = dict(st.get(DEFAULTS_KEY) or {})
    cur = dict(allp.get(printer) or {})
    if mid:
        cur[category] = mid
    else:
        cur.pop(category, None)
    allp[printer] = cur
    st[DEFAULTS_KEY] = allp
    l10n.save_settings(st)


# --------------------------------------------------------------------------- #
# Übernehmen: vom Gerät, aus Dateien (CSV/JSON)
# --------------------------------------------------------------------------- #
ALIASES = {
    "name": ("name", "material", "medium", "media name", "medienname", "medium name", "bezeichnung", "paper",
             "papier", "media_name", "mediumname"),
    "weight": ("weight", "gsm", "g/m2", "g/m²", "grammatur", "gewicht", "media-weight-metric", "basis weight"),
    "media": ("media", "media type", "mediatype", "medientyp", "type", "typ", "media-type", "paper type"),
    "quality": ("quality", "qualität", "qualitaet", "print quality", "druckqualität", "resolution", "auflösung"),
    "profile": ("profile", "profil", "icc", "icc profile", "icc-profil", "farbprofil"),
    "category": ("category", "kategorie"),
    "tac": ("tac", "ink limit", "farbauftrag", "max. farbauftrag", "total ink"),
    "notes": ("notes", "notiz", "bemerkung", "comment", "kommentar"),
}
PLAN_MAX_G = 90                       # bis zu dieser Grammatur gilt Übernommenes als Plandruck-Papier


def _num_g(v) -> int:
    m = re.search(r"\d+", str(v or ""))
    return int(m.group(0)) if m else 0


def _guess_category(name: str, weight: int) -> str:
    if re.search(r"bond|plan|plain|normal|recycl", name or "", re.I) or (0 < weight <= PLAN_MAX_G):
        return "plan"
    return "quality"


def _row_to_mat(d: dict, printer: str, source: str) -> dict | None:
    low = {str(k).strip().lower(): v for k, v in d.items() if k is not None}
    out = {}
    for field, names in ALIASES.items():
        for n in names:
            if n in low and str(low[n] or "").strip():
                out[field] = str(low[n]).strip()
                break
    if not out.get("name"):
        return None
    w = _num_g(out.get("weight"))
    cat = (out.get("category") or "").lower()
    cat = "plan" if cat.startswith(("plan", "prod")) else "quality" if cat else _guess_category(out["name"], w)
    return {"name": out["name"][:80], "category": cat, "printer": printer, "weight": w,
            "media": out.get("media", ""), "quality": out.get("quality", ""), "profile": out.get("profile", ""),
            "tac": _num_g(out.get("tac")), "notes": out.get("notes", ""), "source": source, "checked": False}


def parse_import(path: str, printer: str = "") -> list:
    """Materialliste aus CSV (Trennzeichen ; , Tab; Kopfzeile nötig) oder JSON (Liste bzw. {"materials": […]}).
        Spalten werden nach Namen zugeordnet (Name/Material, Grammatur/gsm, Medientyp, Qualität, Profil …).
        -> Materialien (noch nicht gespeichert), Quelle „import“, ungeprüft."""
    import csv
    with open(path, "rb") as f:
        raw = f.read(5 << 20)
    for enc in ("utf-8-sig", "cp1252"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    rows = []
    if path.lower().endswith(".json") or text.lstrip().startswith(("[", "{")):
        d = json.loads(text)
        lst = d.get("materials") or d.get("media") or d.get("items") if isinstance(d, dict) else d
        rows = [x for x in (lst or []) if isinstance(x, dict)]
    else:
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=";,\t")
        except csv.Error:
            dialect = csv.excel
            dialect.delimiter = ";"
        rows = list(csv.DictReader(text.splitlines(), dialect=dialect))
    out = [m for m in (_row_to_mat(r, printer, "import") for r in rows) if m]
    if rows and not out:
        raise ValueError(tr("Keine Spalte für den Namen gefunden (Name, Material, Medium …)."))
    return out[:MAX]


def from_device(dev: list, printer: str) -> list:
    """Medien, die das Gerät meldet (geladen oder im Katalog), als Materialien – Quelle „gerät“, ungeprüft."""
    out = []
    for d in dev or []:
        name = str(d.get("device_media") or d.get("name") or "").strip()
        if not name:
            continue
        w = int(d.get("weight") or 0)
        out.append({"name": name[:80], "category": _guess_category(name, w), "printer": printer, "weight": w,
                    "media": "", "source": "device", "checked": False})
    return out


def merge(existing: list, new: list) -> tuple[list, int]:
    """Neue Materialien dazunehmen – gleicher Name für denselben Drucker wird übersprungen. -> (Liste, neu)."""
    have = {(m.get("name", "").lower(), m.get("printer", "")) for m in existing}
    out, n = list(existing), 0
    for m in new:
        key = (m["name"].lower(), m.get("printer", ""))
        if key in have:
            continue
        have.add(key)
        m = dict(m, id=new_id(m["name"], out))
        out.append(m)
        n += 1
    return out, n


def density_options(caps) -> list:
    """Treiberoptionen für Tintenmenge/Farbdichte: [(Schlüsselwort, Text)]."""
    if caps is None:
        return []
    out = []
    for k, o in caps.options.items():
        if not o.installable and (DENSITY.search(k) or DENSITY.search(o.text or "")):
            out.append((k, o.text or k))
    return out


def notes(mat: dict | None, cfg: dict) -> list:
    """Hinweise zum Material, z. B. Profil erlaubt mehr Farbauftrag als das Material verträgt."""
    if not mat:
        return []
    out = []
    if mat.get("tac") and mat.get("profile"):
        from . import config, usercolor
        prof = config.profile_by_id(cfg, mat["profile"])
        if prof and prof.get("file"):
            lim = usercolor.tac_limit_for(prof["file"], 0)
            if lim and lim > mat["tac"]:
                out.append(tr("Material „{0}“: das Profil erlaubt ca. {1} % Farbauftrag, das Material nur {2} % – "
                              "ein Profil mit weniger Farbauftrag wählen oder die Tintenmenge im Treiber senken.")
                           .format(mat["name"], lim, mat["tac"]))
    if mat.get("color_mode") == "embed" and not mat.get("profile"):
        out.append(tr("Material „{0}“: „Profil nur einbetten“ nimmt das Profil des Druckers – ist dort keins "
                      "eingestellt, wird nichts eingebettet.").format(mat["name"]))
    if mat.get("source") in ("device", "import") and not mat.get("checked", True):
        out.append(tr("Material „{0}“ ist ungeprüft (vom Gerät bzw. importiert) – unter „Materialien …“ "
                      "prüfen und abhaken.").format(mat["name"]))
    if mat.get("tac") and not mat.get("profile") and not mat.get("density"):
        out.append(tr("Material „{0}“: max. Farbauftrag {1} % ist nur ein Richtwert – begrenzt wird er über das "
                      "Farbprofil oder die Tintenmenge im Treiber.").format(mat["name"], mat["tac"]))
    return out
