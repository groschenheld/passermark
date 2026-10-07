# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Prüfung der Admin-Konfiguration – gemeinsam für den Linux-Helfer (pkexec) und den
Windows-Helfer (UAC). Wirft ValueError bei allem, was nicht exakt erwartet wird.

Absichtlich ohne Abhängigkeiten außer der Standardbibliothek.
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


def check_devmode(s, where):
    """Windows-Treibereinstellungen (DEVMODE) als Base64 – nur Größe und Kodierung prüfen."""
    if s in (None, ""):
        return
    if not isinstance(s, str) or len(s) > MAX_DEVMODE * 4 // 3 + 8:
        raise ValueError(f"{where}: Treiberdaten zu groß")
    try:
        base64.b64decode(s, validate=True)
    except Exception:
        raise ValueError(f"{where}: Treiberdaten ungültig")


def validate(cfg, icc_dir: str, windows: bool = False):
    if not isinstance(cfg, dict):
        raise ValueError("Konfiguration muss ein Objekt sein")
    allowed = {"version", "default_printer", "layout", "printers", "color_profiles",
               "allow_user_profile_choice", "image_default_dpi", "office_converter", "language"}
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
