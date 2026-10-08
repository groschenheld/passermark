# SPDX-License-Identifier: GPL-3.0-or-later
# pdfToolkit – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Admin-Standards aus /etc/pdfdruck/defaults.json.

Das Programm liest diese Datei nur. Geschrieben wird sie ausschließlich über
den Polkit-Helper /usr/libexec/pdfdruck-admin (läuft als root).
Benutzeränderungen leben nur im Speicher der laufenden Sitzung -> nach dem
Beenden gelten automatisch wieder die Admin-Standards.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

from . import platform as _platform

CONFIG_DIR = Path(_platform.config_dir())
DEFAULTS_FILE = CONFIG_DIR / "defaults.json"
ICC_DIR = CONFIG_DIR / "icc"
HELPER = os.environ.get("PDFDRUCK_HELPER", "/usr/libexec/pdfdruck-admin")

INTENTS = {
    "perceptual": "Wahrnehmungsorientiert",
    "relative": "Relativ farbmetrisch",
    "saturation": "Sättigung",
    "absolute": "Absolut farbmetrisch",
}

BUILTIN = {
    "version": 1,
    "default_printer": "",
    "layout": {
        "mode": "fit", "custom_percent": 100.0, "custom_by": "percent", "custom_mm": 210.0, "nup": 1, "cols": 0, "rows": 0,
        "order": "horizontal", "tile_mode": "fit", "tile_percent": 100.0, "gap_mm": 0.0,
        "borders": False, "orientation": "auto", "autorotate": True, "center": True,
        "use_margins": True, "handling": "size",
        "booklet_sides": "both", "booklet_binding": "left", "booklet_sheets": "", "booklet_gutter_mm": 0.0,
        "poster_mode": "scale", "poster_percent": 200.0, "poster_cols": 2, "poster_rows": 2,
        "poster_target": "A2", "poster_target_w_mm": 420.0, "poster_target_h_mm": 594.0,
        "poster_overlap_mm": 10.0, "poster_marks": True, "poster_labels": True, "poster_large_only": False,
        "mirror_h": False, "mirror_v": False, "step_repeat": False, "sr_mode": "auto", "sr_cols": 2,
        "sr_rows": 5, "sr_gap_mm": 0.0, "sr_percent": 100.0, "sr_by": "percent", "sr_mm": 85.0,
        "sr_orientation": "auto", "sr_rotate": "auto", "sr_join": "bleed", "crop_marks": False, "bleed_mm": 0.0,
    },
    # "printers": {"<queue>": {"options": {"InputSlot": "Cas1"}, "color_profile": "", "intent": "relative"}}
    "printers": {},
    # [{"id", "name", "file", "printers": [...], "intents": [...], "bpc": true,
    #   "driver_options": {"<PPD-Key>": "<Wert>"}}]
    "color_profiles": [],
    "allow_user_profile_choice": True,
    "image_default_dpi": 96,        # Bilder ohne DPI-Angabe: so groß wird 1 Pixel
    "office_converter": "auto",     # auto | libreoffice | onlyoffice | eurooffice
    "language": "",                 # Standardsprache für alle Benutzer ("" = Systemsprache)
}


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load() -> dict:
    try:
        with open(DEFAULTS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError
    except (OSError, ValueError):
        data = {}
    return _merge(BUILTIN, data)


def profiles_for(cfg: dict, printer: str) -> list[dict]:
    return [p for p in cfg.get("color_profiles", [])
            if not p.get("printers") or printer in p.get("printers", [])]


def profile_by_id(cfg: dict, pid: str) -> dict | None:
    return next((p for p in cfg.get("color_profiles", []) if p.get("id") == pid), None)
