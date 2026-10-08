# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Presets: benannte Einstellungen je Auftrag – dieselben Dateien für Programm, Kommandozeile und (später) Watcher.

Ablage (je Benutzer):
  Linux    ~/.config/passermark/presets/<auftrag>/<name>.json
  Windows  %APPDATA%\\Passermark\\presets\\<auftrag>\\<name>.json
Format wie `passermark-cli settings <auftrag>`: {"job": "<auftrag>", "settings": {…}}.
Zusätzlich je Auftrag die zuletzt verwendeten Einstellungen (Datei „.zuletzt.json“, nicht in der Liste).
"""
from __future__ import annotations

import os
import re

from . import core
from .l10n import tr

LAST = ".zuletzt"
PRINT = "druck"                                  # Druck-Layout (Größe, Mehrere, Broschüre, Poster, Nutzen) – kein CLI-Auftrag
_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def root_dir() -> str:
    from .l10n import _settings_file
    return os.path.join(os.path.dirname(_settings_file()), "presets")


def settings_class(kind: str):
    if kind == PRINT:
        from .layout import LayoutSettings
        return LayoutSettings
    return core.settings_class(kind)             # unbekannter Auftrag -> ValueError


def job_dir(kind: str) -> str:
    settings_class(kind)
    return os.path.join(root_dir(), kind)


def clean_name(name: str) -> str:
    """Erlaubter Preset-Name (wird Dateiname): ohne Pfadzeichen, ohne Punkt am Anfang, höchstens 80 Zeichen."""
    n = _BAD.sub("", (name or "").strip()).strip(". ")
    if not n:
        raise ValueError(tr("Ungültiger Preset-Name."))
    return n[:80]


def path_for(kind: str, name: str) -> str:
    return os.path.join(job_dir(kind), (name if name == LAST else clean_name(name)) + ".json")


def list_presets(kind: str) -> list[str]:
    d = job_dir(kind)
    try:
        names = [f[:-5] for f in os.listdir(d) if f.endswith(".json") and not f.startswith(".")]
    except OSError:
        return []
    return sorted(names, key=str.lower)


def save(kind: str, name: str, settings) -> str:
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
    if k != kind:
        raise ValueError(tr("Preset ist für „{0}“, nicht für „{1}“").format(k, kind))
    return core.settings_from_dict(settings_class(kind), d)


def delete(kind: str, name: str) -> None:
    try:
        os.remove(path_for(kind, name))
    except FileNotFoundError:
        pass


def save_last(kind: str, settings) -> None:
    try:
        save(kind, LAST, settings)
    except OSError:
        pass                                     # „zuletzt verwendet“ ist nur Komfort


def load_last(kind: str):
    try:
        return load(kind, LAST)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def resolve(kind: str, ref: str) -> str:
    """Für die Kommandozeile: Pfad zu einer Datei oder Name eines gespeicherten Presets -> Dateipfad."""
    if os.path.isfile(ref):
        return ref
    try:
        p = path_for(kind, ref)
    except ValueError:
        p = ""
    if p and os.path.isfile(p):
        return p
    raise FileNotFoundError(tr("Preset nicht gefunden: {0} (gespeicherte: {1})").format(
        ref, ", ".join(list_presets(kind)) or "–"))
