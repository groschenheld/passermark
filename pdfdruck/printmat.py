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
          "profile", "intent", "tac", "notes", "cut_force", "cut_speed")
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
    for k in ("media", "quality", "density_key", "density", "profile", "intent", "notes"):
        out[k] = str(out.get(k) or "")
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
    clean = [c for c in (_clean(m) for m in mats) if c is not None][:MAX]
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
    if mat.get("tac") and not mat.get("profile") and not mat.get("density"):
        out.append(tr("Material „{0}“: max. Farbauftrag {1} % ist nur ein Richtwert – begrenzt wird er über das "
                      "Farbprofil oder die Tintenmenge im Treiber.").format(mat["name"], mat["tac"]))
    return out
