# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Own materials and ICC profiles of the user – no admin rights, no Qt.

* materials (papers) of the user: ~/.config/passermark/materials.json (Windows %APPDATA%\\Passermark\\materials.json)
  same fields as the admin materials; ids start with "u_"; a profile is either an admin profile id or the path
  of an ICC file (own profile, system profile, downloaded standard profile)
* own ICC folder: Linux ~/.local/share/icc (also read by other colour tools), Windows %APPDATA%\\Passermark\\icc
* standard printing conditions (ECI, VIGC, Idealliance) from the ICC profile registry: catalogue and download –
  the profiles are not shipped with Passermark (their licences do not allow it everywhere), every user fetches
  them for himself from registry.color.org

The admin materials (/etc/passermark/defaults.json) stay as they are; colorlab.all_materials() shows both.
"""
from __future__ import annotations

import copy
import json
import os
import re
import shutil
import tempfile

from . import platform as _platform
from .l10n import tr

PREFIX = "u_"
MAX_MATERIALS = 200
FIELDS = ("id", "name", "weight", "surface", "white", "white_source", "profiles", "intent", "notes")


def user_dir() -> str:
    """Folder of the user settings (next to settings.json)."""
    env = os.environ.get("PASSERMARK_USER_DIR")
    if env:
        return env
    from . import l10n
    return os.path.dirname(l10n._settings_file())


def materials_file() -> str:
    return os.path.join(user_dir(), "materials.json")


def icc_dir() -> str:
    """Own ICC folder (created on demand)."""
    if os.environ.get("PASSERMARK_USER_DIR"):
        return os.path.join(os.environ["PASSERMARK_USER_DIR"], "icc")
    if _platform.IS_WIN:
        return os.path.join(user_dir(), "icc")
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "icc")


# --------------------------------------------------------------------------- #
# Materialien des Benutzers
# --------------------------------------------------------------------------- #
def _clean(m: dict) -> dict | None:
    """One material from the file – tolerant: unknown fields away, wrong values to defaults."""
    if not isinstance(m, dict) or not re.match(r"^u_[A-Za-z0-9_-]{1,60}$", str(m.get("id", ""))):
        return None
    out = {k: copy.deepcopy(m[k]) for k in FIELDS if k in m}
    out["name"] = str(out.get("name") or out["id"])[:64]
    try:
        out["weight"] = max(0, min(2000, int(out.get("weight") or 0)))
    except (TypeError, ValueError):
        out["weight"] = 0
    from .colorlab import SURFACES
    if out.get("surface", "") not in SURFACES:
        out["surface"] = ""
    w = out.get("white")
    try:
        w = [float(x) for x in w] if w is not None else None
        if w is not None and (len(w) != 3 or not 0 <= w[0] <= 100 or not all(-128 <= x <= 128 for x in w[1:])):
            w = None
    except (TypeError, ValueError):
        w = None
    out["white"] = w
    out["white_source"] = str(out.get("white_source") or "")[:200]
    out["notes"] = str(out.get("notes") or "")[:2000]
    from .config import INTENTS
    if out.get("intent", "") not in ("",) + tuple(INTENTS):
        out["intent"] = ""
    prof = out.get("profiles")
    out["profiles"] = {str(k): str(v) for k, v in prof.items() if v} if isinstance(prof, dict) else {}
    return out


def load_materials() -> list:
    try:
        with open(materials_file(), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return []
    mats = d.get("materials") if isinstance(d, dict) else d
    out, seen = [], set()
    for m in mats if isinstance(mats, list) else []:
        c = _clean(m)
        if c is not None and c["id"] not in seen:
            seen.add(c["id"])
            out.append(c)
    return out[:MAX_MATERIALS]


def save_materials(mats: list):
    """Store the list atomically (only the known fields)."""
    if len(mats) > MAX_MATERIALS:
        raise ValueError(tr("Höchstens {0} eigene Materialien.").format(MAX_MATERIALS))
    clean = [c for c in (_clean(m) for m in mats) if c is not None]
    p = materials_file()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "materials": clean}, f, indent=2, ensure_ascii=False)
    os.replace(tmp, p)


def new_id(name: str, existing) -> str:
    base = PREFIX + (re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")[:48] or "material")
    ids = set(existing)
    mid, i = base, 2
    while mid in ids:
        mid, i = f"{base}_{i}", i + 1
    return mid


# --------------------------------------------------------------------------- #
# Eigene ICC-Profile
# --------------------------------------------------------------------------- #
def import_icc(path: str) -> str:
    """Copy an ICC file into the own ICC folder -> new path (the same file is not copied twice)."""
    from .colorconv import icc_colorspace
    icc_colorspace(path)                                    # ValueError, wenn kein ICC
    d = icc_dir()
    os.makedirs(d, exist_ok=True)
    if os.path.realpath(os.path.dirname(path)) == os.path.realpath(d):
        return path
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", os.path.basename(path)) or "profil.icc"
    dst = os.path.join(d, name)
    if os.path.exists(dst):
        with open(path, "rb") as a, open(dst, "rb") as b:
            if a.read() == b.read():
                return dst
        stem, ext = os.path.splitext(name)
        i = 2
        while os.path.exists(dst):
            dst = os.path.join(d, f"{stem}_{i}{ext}")
            i += 1
    shutil.copyfile(path, dst)
    return dst


# --------------------------------------------------------------------------- #
# Standard-Druckbedingungen (ICC Profile Registry)
# --------------------------------------------------------------------------- #
REGISTRY = "https://registry.color.org/profile-registry/profiles/{0}.icc"
REGISTRY_PAGE = "https://registry.color.org/profile-registry/{0}"

# key, file (= registry name), shown name, characterisation, surface, typical max. ink coverage %, publisher
STANDARD_PROFILES = [
    {"key": "PSOcoated_v3", "name": "PSO Coated v3", "condition": "FOGRA51", "surface": "coated", "tac": 300,
     "by": "ECI", "use": "Offset, gestrichenes Papier (Bilderdruck) – heutiger Standard"},
    {"key": "PSOuncoated_v3_FOGRA52", "name": "PSO Uncoated v3", "condition": "FOGRA52", "surface": "uncoated",
     "tac": 300, "by": "ECI", "use": "Offset, ungestrichenes Papier (Naturpapier, Offsetpapier) – heutiger Standard"},
    {"key": "Coated_Fogra39L_VIGC_300", "name": "Coated FOGRA39 (300 %)", "condition": "FOGRA39",
     "surface": "coated", "tac": 300, "by": "VIGC",
     "use": "Offset, gestrichen – ältere Norm, verlangen viele Druckereien noch (wie ISO Coated v2)"},
    {"key": "Uncoated_Fogra47L_VIGC_300", "name": "Uncoated FOGRA47 (300 %)", "condition": "FOGRA47",
     "surface": "uncoated", "tac": 300, "by": "VIGC", "use": "Offset, ungestrichen – ältere Norm"},
    {"key": "PSOsc-b_paper_v3_FOGRA54", "name": "PSO SC-B Paper v3", "condition": "FOGRA54", "surface": "special",
     "tac": 270, "by": "ECI", "use": "Rollenoffset, SC-Papier (Magazine, Beilagen)"},
    {"key": "GRACoL2013_CRPC6", "name": "GRACoL 2013", "condition": "CRPC6", "surface": "coated", "tac": 320,
     "by": "Idealliance", "use": "USA, Bogenoffset gestrichen"},
    {"key": "SWOP2013C3_CRPC5", "name": "SWOP 2013 C3", "condition": "CRPC5", "surface": "coated", "tac": 300,
     "by": "Idealliance", "use": "USA, Rollenoffset Publikationspapier"},
]


def standard_by_key(key: str):
    return next((p for p in STANDARD_PROFILES if p["key"] == key), None)


def standard_installed(p: dict) -> str:
    """Path of an installed copy of the standard profile ("" = not installed)."""
    from . import cmyk
    want = p["key"].lower()
    for d in cmyk.system_profile_dirs():
        if not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for f in files:
                if os.path.splitext(f)[0].lower() == want and f.lower().endswith((".icc", ".icm")):
                    return os.path.join(root, f)
    return ""


def standards_for_surface(surface: str) -> list:
    """Standard profiles that fit this surface (coated/uncoated/…), Europe first."""
    from .colorlab import _surface_group
    g = _surface_group(surface or "")
    return [p for p in STANDARD_PROFILES if g and _surface_group(p["surface"]) == g]


def download_standard(key: str, timeout: float = 60.0, opener=None) -> str:
    """Fetch a standard profile from the ICC registry into the own ICC folder -> path.
        Only CMYK output profiles are accepted (header checked); at most 8 MB."""
    import urllib.request
    p = standard_by_key(key)
    if p is None:
        raise ValueError(tr("Unbekanntes Standardprofil: {0}").format(key))
    url = REGISTRY.format(p["key"])
    req = urllib.request.Request(url, headers={"User-Agent": "Passermark"})
    op = opener or urllib.request.urlopen
    with op(req, timeout=timeout) as r:
        data = r.read(8 * 1024 * 1024 + 1)
    if len(data) > 8 * 1024 * 1024:
        raise ValueError(tr("Die Datei ist zu groß – kein ICC-Profil?"))
    if len(data) < 132 or data[36:40] != b"acsp" or data[16:20] != b"CMYK":
        raise ValueError(tr("Die Antwort von {0} ist kein CMYK-Profil.").format(url))
    d = icc_dir()
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, p["key"] + ".icc")
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".part")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, dst)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return dst


def tac_limit_for(icc_path: str, default: int = 300) -> int:
    """Usual maximum ink coverage of a printing condition (from the profile name) – a guide value."""
    text = os.path.basename(icc_path or "").lower()
    try:
        from .colorlab import profile_desc
        text += " " + profile_desc(icc_path).lower()
    except Exception:
        pass
    text = re.sub(r"[^a-z0-9]", "", text)
    for p in STANDARD_PROFILES:                             # genau dieses Profil
        if re.sub(r"[^a-z0-9]", "", p["key"].lower()) in text:
            return p["tac"]
    m = re.search(r"(?:tac|gcr|ucr|vigc)(2[4-9]0|3[0-5]0)", text)
    if m:                                                    # Grenze im Namen („…_VIGC_260“, „TAC300“)
        return int(m.group(1))
    if "isocoatedv2" in text or "fogra39" in text or "fogra27" in text:
        return 330                                           # ISO Coated v2 / FOGRA39: 330 %
    for p in STANDARD_PROFILES:                              # gleiche Druckbedingung
        if p["condition"].lower() in text:
            return p["tac"]
    return default
