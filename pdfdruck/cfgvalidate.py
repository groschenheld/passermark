# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Validation of the admin configuration – shared by the Linux helper (pkexec) and the
Windows helper (UAC). Raises ValueError for anything that is not exactly as expected.

Deliberately without dependencies beyond the standard library.
"""
from __future__ import annotations

import base64
import os
import re

RX_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
RX_QUEUE_UNIX = re.compile(r"^[A-Za-z0-9_.@-]{1,127}$")
RX_QUEUE_WIN = re.compile(r'^[^\x00-\x1f"<>|*?]{1,220}$')       # Windows: Leerzeichen, \\server\drucker …
RX_KEY = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
RX_VAL = re.compile(r"^[A-Za-z0-9_.,:+/@ -]{0,128}$")
RX_NAME = re.compile(r"^[^\x00-\x1f]{1,64}$")
MAX_DEVMODE = 96 * 1024

LAYOUT = {"mode": ("fit", "actual", "shrink", "custom"),
          "order": ("horizontal", "horizontal_rev", "vertical", "vertical_rev"),
          "tile_mode": ("fit", "actual", "custom"),
          "orientation": ("auto", "portrait", "landscape"),
          "handling": ("size", "multiple", "booklet", "poster"),
          "booklet_sides": ("both", "front", "back"), "booklet_binding": ("left", "right"),
          "poster_mode": ("scale", "sheets", "target"),
          "poster_target": ("A0", "A1", "A2", "A3", "A4", "B1", "B2", "B3", "custom"),
          "sr_mode": ("auto", "grid"), "sr_orientation": ("auto", "portrait", "landscape"),
          "sr_rotate": ("auto", "0", "90"), "sr_join": ("edge", "bleed", "gap"),
          "custom_by": ("percent", "short", "long"), "sr_by": ("percent", "short", "long")}
NUMS = {"custom_percent": (1, 1000), "custom_mm": (1, 5000), "sr_mm": (1, 5000), "nup": (1, 64), "cols": (0, 16), "rows": (0, 16),
        "tile_percent": (1, 1000), "gap_mm": (0, 50), "booklet_gutter_mm": (0, 50),
        "poster_percent": (1, 5000), "poster_cols": (1, 20), "poster_rows": (1, 20),
        "poster_target_w_mm": (10, 5000), "poster_target_h_mm": (10, 5000), "poster_overlap_mm": (0, 50),
        "sr_cols": (1, 50), "sr_rows": (1, 50), "sr_gap_mm": (0, 50), "sr_percent": (1, 1000), "bleed_mm": (0, 20)}
BOOLS = ("borders", "autorotate", "center", "use_margins", "poster_marks", "poster_labels",
         "poster_large_only", "mirror_h", "mirror_v", "step_repeat", "crop_marks")
STRS = {"booklet_sheets": re.compile(r"^[0-9 ,;-]{0,64}$")}
INTENTS = ("perceptual", "relative", "saturation", "absolute")
CONVERTERS = ("auto", "libreoffice", "onlyoffice", "eurooffice", "msoffice")


def _queue_ok(name: str, windows: bool) -> bool:
    return bool((RX_QUEUE_WIN if windows else RX_QUEUE_UNIX).match(str(name)))


def check_opts(d, where):
    if not isinstance(d, dict):
        raise ValueError(f"{where}: Objekt erwartet")
    for k, v in d.items():
        if not RX_KEY.match(str(k)) or not RX_VAL.match(str(v)):
            raise ValueError(f"{where}: ungültige Option {k!r}={v!r}")


def check_dirs(dirs, windows: bool):
    """Weitere Ablauf-Ordner: absolute Pfade (Windows auch \\\\server\\freigabe), höchstens 20."""
    import ntpath
    import posixpath
    if not isinstance(dirs, list) or len(dirs) > 20:
        raise ValueError("workflow_dirs: Liste mit höchstens 20 Ordnern erwartet")
    for d in dirs:
        if not isinstance(d, str) or not 1 <= len(d) <= 1024 or re.search(r"[\x00-\x1f]", d):
            raise ValueError(f"workflow_dirs: ungültiger Ordner {d!r}")
        if not (ntpath if windows else posixpath).isabs(d):
            raise ValueError(f"workflow_dirs: Ordner muss absolut angegeben sein: {d!r}")


def check_devmode(s, where):
    """Windows driver settings (DEVMODE) as Base64 – only check size and encoding."""
    if s in (None, ""):
        return
    if not isinstance(s, str) or len(s) > MAX_DEVMODE * 4 // 3 + 8:
        raise ValueError(f"{where}: Treiberdaten zu groß")
    try:
        base64.b64decode(s, validate=True)
    except Exception:
        raise ValueError(f"{where}: Treiberdaten ungültig")


SURFACES = ("", "coated", "uncoated", "matte", "glossy", "silk", "recycled", "special")
RX_TEXT = re.compile(r"^[^\x00-\x08\x0b-\x1f]*$")


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def check_materials(mats, profile_ids: set, windows: bool):
    """Materialien (Papiere): höchstens 200, Lab-Werte im Bereich, Profile nur aus der Verwaltung."""
    if not isinstance(mats, list) or len(mats) > 200:
        raise ValueError("materials: Liste mit höchstens 200 Einträgen erwartet")
    seen = set()
    for m in mats:
        if not isinstance(m, dict) or not RX_ID.match(str(m.get("id", ""))):
            raise ValueError("Material: id ungültig")
        if m["id"] in seen:
            raise ValueError(f"Material {m['id']}: doppelt")
        seen.add(m["id"])
        extra = set(m) - {"id", "name", "weight", "surface", "white", "white_source", "profiles", "intent", "notes"}
        if extra:
            raise ValueError(f"Material {m['id']}: unbekannte Felder {sorted(extra)}")
        if not isinstance(m.get("name", ""), str) or not RX_NAME.match(m.get("name") or m["id"]):
            raise ValueError(f"Material {m['id']}: Name ungültig")
        w = m.get("weight", 0)
        if not isinstance(w, int) or isinstance(w, bool) or not 0 <= w <= 2000:
            raise ValueError(f"Material {m['id']}: Grammatur ungültig")
        if m.get("surface", "") not in SURFACES:
            raise ValueError(f"Material {m['id']}: Oberfläche ungültig")
        wh = m.get("white")
        if wh is not None:
            if (not isinstance(wh, list) or len(wh) != 3 or not all(_num(x) for x in wh)
                    or not 0 <= wh[0] <= 100 or not all(-128 <= x <= 128 for x in wh[1:])):
                raise ValueError(f"Material {m['id']}: Papierweiß (Lab) ungültig")
        for k, lim in (("white_source", 200), ("notes", 2000)):
            t = m.get(k, "")
            if not isinstance(t, str) or len(t) > lim or not RX_TEXT.match(t):
                raise ValueError(f"Material {m['id']}: {k} ungültig")
        if m.get("intent", "") not in ("",) + INTENTS:
            raise ValueError(f"Material {m['id']}: Intent ungültig")
        prof = m.get("profiles", {})
        if not isinstance(prof, dict) or len(prof) > 100:
            raise ValueError(f"Material {m['id']}: Profile ungültig")
        for q, pid in prof.items():
            if q != "*" and not _queue_ok(q, windows):
                raise ValueError(f"Material {m['id']}: Druckername ungültig")
            if pid not in profile_ids:
                raise ValueError(f"Material {m['id']}: unbekanntes Profil {pid!r}")


def validate(cfg, icc_dir: str, windows: bool = False):
    if not isinstance(cfg, dict):
        raise ValueError("Konfiguration muss ein Objekt sein")
    allowed = {"version", "default_printer", "layout", "printers", "color_profiles",
               "allow_user_profile_choice", "image_default_dpi", "office_converter", "language",
               "workflow_dirs", "print_log", "materials"}
    extra = set(cfg) - allowed
    if extra:
        raise ValueError(f"Unbekannte Schlüssel: {sorted(extra)}")
    dpi = cfg.get("image_default_dpi", 96)
    if not isinstance(dpi, (int, float)) or not 10 <= dpi <= 2400:
        raise ValueError("image_default_dpi außerhalb 10–2400")
    if cfg.get("language", "") not in ("", "de", "en", "hu", "es", "fr"):
        raise ValueError("language ungültig")
    if cfg.get("office_converter", "auto") not in CONVERTERS:
        raise ValueError("office_converter ungültig")
    check_dirs(cfg.get("workflow_dirs", []), windows)
    pl = cfg.get("print_log", {})
    if not isinstance(pl, dict) or set(pl) - {"force", "dir", "keep_days"}:
        raise ValueError("print_log ungültig")
    if not isinstance(pl.get("force", False), bool):
        raise ValueError("print_log.force muss bool sein")
    kd = pl.get("keep_days", 0)
    if not isinstance(kd, int) or isinstance(kd, bool) or not 0 <= kd <= 36500:
        raise ValueError("print_log.keep_days außerhalb 0–36500")
    if pl.get("dir"):
        check_dirs([pl["dir"]], windows)
    dp = cfg.get("default_printer", "")
    if dp and not _queue_ok(dp, windows):
        raise ValueError("default_printer ungültig")
    lay = cfg.get("layout", {})
    if not isinstance(lay, dict):
        raise ValueError("layout ungültig")
    for k, v in lay.items():
        if k in LAYOUT:
            if v not in LAYOUT[k]:
                raise ValueError(f"layout.{k} ungültig")
        elif k in NUMS:
            if not isinstance(v, (int, float)) or isinstance(v, bool) or not NUMS[k][0] <= v <= NUMS[k][1]:
                raise ValueError(f"layout.{k} außerhalb des Bereichs")
        elif k in BOOLS:
            if not isinstance(v, bool):
                raise ValueError(f"layout.{k} muss bool sein")
        elif k in STRS:
            if not isinstance(v, str) or not STRS[k].match(v):
                raise ValueError(f"layout.{k} ungültig")
        else:
            raise ValueError(f"layout.{k} unbekannt")
    ids = set()
    for p in cfg.get("color_profiles", []):
        if not isinstance(p, dict) or not RX_ID.match(str(p.get("id", ""))):
            raise ValueError("Farbprofil: id ungültig")
        ids.add(p["id"])
        if os.path.normcase(str(p.get("file", ""))) != os.path.normcase(os.path.join(icc_dir, p["id"] + ".icc")):
            raise ValueError(f"Farbprofil {p['id']}: Datei muss in {icc_dir} liegen")
        if not isinstance(p.get("name", ""), str) or len(p.get("name", "")) > 128:
            raise ValueError("Farbprofil: Name ungültig")
        for q in p.get("printers", []):
            if not _queue_ok(q, windows):
                raise ValueError("Farbprofil: Druckername ungültig")
        if any(i not in INTENTS for i in p.get("intents", [])):
            raise ValueError("Farbprofil: Intent ungültig")
        check_opts(p.get("driver_options", {}), f"Profil {p['id']}")
    check_materials(cfg.get("materials", []), ids, windows)
    printers = cfg.get("printers", {})
    if not isinstance(printers, dict):
        raise ValueError("printers ungültig")
    for q, pc in printers.items():
        if not _queue_ok(q, windows) or not isinstance(pc, dict):
            raise ValueError(f"Drucker {q!r} ungültig")
        unknown = set(pc) - {"options", "color_profile", "intent", "devmode", "presets",
                             "trays", "tray_auto", "tray_live", "tray_host"}
        if unknown:
            raise ValueError(f"Drucker {q}: unbekannte Schlüssel {sorted(unknown)}")
        check_opts(pc.get("options", {}), f"Drucker {q}")
        check_devmode(pc.get("devmode"), f"Drucker {q}")
        prof = pc.get("color_profile", "")
        if prof and prof not in ids:
            raise ValueError(f"Drucker {q}: unbekanntes Profil {prof}")
        if pc.get("intent", "relative") not in INTENTS:
            raise ValueError(f"Drucker {q}: Intent ungültig")
        trays = pc.get("trays", [])
        if not isinstance(trays, list) or len(trays) > 40:
            raise ValueError(f"Drucker {q}: Fächerbelegung ungültig")
        for t in trays:
            if not isinstance(t, dict) or set(t) - {"slot", "size", "weight", "media", "ipp"}:
                raise ValueError(f"Drucker {q}: Fachzeile ungültig")
            check_opts({"slot": t.get("slot", ""), "size": t.get("size", ""), "media": t.get("media", ""),
                        "ipp": t.get("ipp", "")}, f"Drucker {q}, Fach")
            w = t.get("weight", 0)
            if not isinstance(w, int) or isinstance(w, bool) or not 0 <= w <= 2000:
                raise ValueError(f"Drucker {q}: Grammatur ungültig")
        for k in ("tray_auto", "tray_live"):
            if not isinstance(pc.get(k, False), bool):
                raise ValueError(f"Drucker {q}: {k} muss bool sein")
        if not re.match(r"^[A-Za-z0-9.:_\[\]-]{0,253}$", str(pc.get("tray_host", ""))):
            raise ValueError(f"Drucker {q}: Geräteadresse ungültig")
        presets = pc.get("presets", [])
        if not isinstance(presets, list) or len(presets) > 50:
            raise ValueError(f"Drucker {q}: Vorlagen ungültig")
        for pr in presets:
            if not isinstance(pr, dict) or not RX_NAME.match(str(pr.get("name", ""))):
                raise ValueError(f"Drucker {q}: Vorlagenname ungültig")
            if set(pr) - {"name", "options", "devmode", "booklet"}:
                raise ValueError(f"Drucker {q}: Vorlage mit unbekannten Feldern")
            check_opts(pr.get("options", {}), f"Vorlage {pr['name']}")
            check_devmode(pr.get("devmode"), f"Vorlage {pr['name']}")
            if not isinstance(pr.get("booklet", False), bool):
                raise ValueError(f"Vorlage {pr['name']}: booklet muss bool sein")
