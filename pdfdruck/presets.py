# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Presets: named settings per job – the same files for the GUI, the command line and (later) the watcher.

Storage (per user):
  Linux    ~/.config/passermark/presets/<job>/<name>.json
  Windows  %APPDATA%\\Passermark\\presets\\<job>\\<name>.json
Format like `passermark-cli settings <job>`: {"job": "<job>", "settings": {…}}.
Additionally, per job the most recently used settings (file ".zuletzt.json", not in the list).
"""

from __future__ import annotations

import os
import re

from . import core
from .l10n import tr

LAST = ".zuletzt"
PRINT = "impose"  # print layout (size, multiple, booklet, poster, step & repeat) = CLI job impose
_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def root_dir() -> str:
    """Folder that holds the user's presets (one subfolder per job)."""
    from .l10n import _settings_file

    return os.path.join(os.path.dirname(_settings_file()), "presets")


def settings_class(kind: str):
    """Return the settings dataclass of the job ``kind``."""
    return core.settings_class(kind)  # unbekannter Auftrag -> ValueError


def job_dir(kind: str) -> str:
    """Folder with the presets of job ``kind`` (migrates the folder name used before 1.7)."""
    settings_class(kind)
    d = os.path.join(root_dir(), kind)
    if kind == PRINT:  # 1.7: Druck-Presets lagen unter „druck“
        old = os.path.join(root_dir(), "druck")
        if os.path.isdir(old) and not os.path.exists(d):
            try:
                os.rename(old, d)
                for f in os.listdir(d):
                    if f.endswith(".json"):
                        k, data = core.load_settings(os.path.join(d, f))
                        if k == "druck":
                            core.save_settings(os.path.join(d, f), PRINT, data)
            except (OSError, ValueError, KeyError):
                pass
    return d


def clean_name(name: str) -> str:
    """Allowed preset name (becomes the file name): no path characters, no leading dot, at most 80 characters."""
    n = _BAD.sub("", (name or "").strip()).strip(". ")
    if not n:
        raise ValueError(tr("Ungültiger Preset-Name."))
    return n[:80]


def path_for(kind: str, name: str) -> str:
    """File path of the preset ``name`` of job ``kind``."""
    return os.path.join(job_dir(kind), (name if name == LAST else clean_name(name)) + ".json")


def list_presets(kind: str) -> list[str]:
    """Names of the saved presets of job ``kind``, sorted without regard to case."""
    d = job_dir(kind)
    try:
        names = [f[:-5] for f in os.listdir(d) if f.endswith(".json") and not f.startswith(".")]
    except OSError:
        return []
    return sorted(names, key=str.lower)


def save(kind: str, name: str, settings) -> str:
    """Save ``settings`` as preset ``name`` (written atomically) and return the file path."""
    p = path_for(kind, name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    core.save_settings(tmp, kind, settings)
    os.replace(tmp, p)
    return p


def load(kind: str, name: str):
    """Einstellungen (Datenklasse des Auftrags) aus einem Preset; FileNotFoundError, wenn es keines gibt."""
    p = path_for(kind, name)
    k, d = core.load_settings(p)
    if k == "druck" and kind == PRINT:
        k = PRINT
    if k != kind:
        raise ValueError(tr("Preset ist für „{0}“, nicht für „{1}“").format(k, kind))
    return core.settings_from_dict(settings_class(kind), d)


def delete(kind: str, name: str) -> None:
    """Delete a preset; a missing file is not an error."""
    try:
        os.remove(path_for(kind, name))
    except FileNotFoundError:
        pass


def save_last(kind: str, settings) -> None:
    """Remember ``settings`` as the last used ones of job ``kind`` (best effort)."""
    try:
        save(kind, LAST, settings)
    except OSError:
        pass  # „zuletzt verwendet“ ist nur Komfort


def load_last(kind: str):
    """Return the last used settings of job ``kind``, or None if there are none or they cannot be read."""
    try:
        return load(kind, LAST)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def resolve(kind: str, ref: str) -> str:
    """For the command line: path to a file or name of a saved preset -> file path."""
    if os.path.isfile(ref):
        return ref
    try:
        p = path_for(kind, ref)
    except ValueError:
        p = ""
    if p and os.path.isfile(p):
        return p
    raise FileNotFoundError(
        tr("Preset nicht gefunden: {0} (gespeicherte: {1})").format(ref, ", ".join(list_presets(kind)) or "–")
    )
