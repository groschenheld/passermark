# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Admin defaults from /etc/passermark/defaults.json.

The program only reads this file. It is written exclusively via the polkit helper
/usr/libexec/passermark-admin (runs as root).
User changes live only in the memory of the running session -> after quitting,
the admin defaults automatically apply again.
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
HELPER = os.environ.get("PDFDRUCK_HELPER", "/usr/libexec/passermark-admin")

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
    "image_default_dpi": 96,        # images without a DPI value: this is how large 1 pixel becomes
    "office_converter": "auto",     # auto | libreoffice | onlyoffice | eurooffice
    "language": "",                 # default language for all users ("" = system language)
    "workflow_dirs": [],            # weitere Ablauf-Ordner für alle (z. B. Netzwerkfreigabe), nach den eigenen
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
