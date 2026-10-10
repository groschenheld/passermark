# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Bundled examples (variable data) and manuals.

The examples live in the program package (pdfdruck/docs/beispiele/vdp) – often read-only there. "Get examples"
copies them to a folder of the user and registers the presets with the full CSV path in the preset folder, so
they are available in the GUI preset bar and on the command line by name.
"""
from __future__ import annotations

import os
import shutil

DOCS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")
VDP_DIR = os.path.join(DOCS_DIR, "beispiele", "vdp")
CLI_HOWTO = os.path.join(DOCS_DIR, "passermark-cli-anleitung.pdf")
VDP_HOWTO = os.path.join(DOCS_DIR, "passermark-vdp-anleitung.pdf")

# Datei (ohne .json) -> Name in der Preset-Leiste
EXAMPLES = [
    ("beispiel-1-qr-nummer", "Beispiel 1 – QR mit Nummer"),
    ("beispiel-2-qr-csv", "Beispiel 2 – QR aus CSV"),
    ("beispiel-3-code128", "Beispiel 3 – Code 128"),
    ("beispiel-4-ean13", "Beispiel 4 – EAN-13"),
    ("beispiel-5-visitenkarte", "Beispiel 5 – Visitenkarte (vCard)"),
    ("beispiel-6-wlan", "Beispiel 6 – WLAN-Zugang"),
    ("beispiel-7-karte-vorne-hinten", "Beispiel 7 – Visitenkarte vorne und hinten"),
]


def default_target() -> str:
    return os.path.join(os.path.expanduser("~"), "Passermark-Beispiele")


def install(target: str | None = None, presets_too: bool = True) -> str:
    """Beispiele nach <target>/vdp kopieren (vorhandene Dateien werden ersetzt) und – wenn presets_too – als
    Presets „Beispiel 1 …“ eintragen. Liefert den Ordner mit den Beispielen."""
    from . import core, presets
    if not os.path.isdir(VDP_DIR):
        raise FileNotFoundError(VDP_DIR)
    dest = os.path.join(os.path.abspath(target or default_target()), "vdp")
    shutil.copytree(VDP_DIR, dest, dirs_exist_ok=True)
    for f in ("passermark-vdp-anleitung.pdf",):
        src = os.path.join(DOCS_DIR, f)
        if os.path.isfile(src):
            shutil.copy(src, os.path.join(os.path.dirname(dest), f))
    for stem, name in EXAMPLES:
        p = os.path.join(dest, "presets", stem + ".json")
        kind, data = core.load_settings(p)
        if data.get("csv_path") and not os.path.isabs(data["csv_path"]):
            data["csv_path"] = os.path.join(dest, data["csv_path"])     # full path: works from anywhere
        core.save_settings(p, kind, data)
        if presets_too:
            presets.save(kind, name, core.settings_from_dict(presets.settings_class(kind), data))
    return dest
