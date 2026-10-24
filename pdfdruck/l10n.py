# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Interface language: German (source language), English, Hungarian, Spanish, French.

tr("German text") returns the text in the configured language; if a translation is missing,
the German text stays. Placeholders: tr("Page {0} of {1}").format(a, b).

Language: user setting (File → Settings) > admin default > system language > English.
Standard library only – also importable by the admin helper.
"""
from __future__ import annotations

import importlib
import json
import locale
import os
import sys

LANGS = {"de": "Deutsch", "en": "English", "hu": "Magyar", "es": "Español", "fr": "Français"}

_lang: str | None = None
_catalog: dict | None = None


def _settings_file() -> str:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "Passermark", "settings.json")
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "passermark", "settings.json")


_settings_cache: tuple | None = None      # (Pfad, Stand der Datei, Inhalt)


def load_settings() -> dict:
    """Benutzereinstellungen. Gelesen wird nur, wenn sich die Datei geändert hat – beim Aufbau eines Fensters wird
        das Dutzende Male abgefragt; auf Windows (Virenscanner, servergespeichertes Profil) kostete jedes Öffnen Zeit."""
    global _settings_cache
    p = _settings_file()
    try:
        st = os.stat(p)
        stamp = (st.st_mtime_ns, st.st_size)
    except OSError:
        return {}
    c = _settings_cache
    if c is not None and c[0] == p and c[1] == stamp:
        return json.loads(c[2])                  # frische Kopie: Aufrufer ändern das Ergebnis und speichern es
    try:
        with open(p, encoding="utf-8") as f:
            text = f.read()
        d = json.loads(text)
    except (OSError, ValueError):
        return {}
    if not isinstance(d, dict):
        return {}
    _settings_cache = (p, stamp, text)
    return d


def save_settings(d: dict):
    global _settings_cache
    _settings_cache = None
    p = _settings_file()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
    os.replace(tmp, p)


def _admin_default() -> str:
    try:
        from . import platform as _platform
        with open(os.path.join(_platform.config_dir(), "defaults.json"), encoding="utf-8") as f:
            return str(json.load(f).get("language", "") or "")
    except Exception:
        return ""


def system_language() -> str:
    cands = [os.environ.get(v, "") for v in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG")]
    if sys.platform == "win32":
        try:
            import ctypes
            cands.insert(0, locale.windows_locale.get(ctypes.windll.kernel32.GetUserDefaultUILanguage(), ""))
        except Exception:
            pass
    try:
        cands.append(locale.getlocale()[0] or "")
    except Exception:
        pass
    for c in cands:
        for part in c.split(":"):
            code = part[:2].lower()
            if code in LANGS:
                return code
    return "en"


def current() -> str:
    global _lang
    if _lang is None:
        want = os.environ.get("PASSERMARK_LANG") or load_settings().get("language") or "auto"
        if want == "auto":
            want = _admin_default() or "auto"
        _lang = want if want in LANGS else system_language()
    return _lang


def set_language(code: str):
    """For tests/restart: switch the language immediately (the GUI is rebuilt on restart)."""
    global _lang, _catalog
    _lang = code if code in LANGS else "en"
    _catalog = None


def _cat() -> dict:
    global _catalog
    if _catalog is None:
        lang = current()
        _catalog = {}
        if lang != "de":
            try:
                _catalog = importlib.import_module(f"{__package__}.lang.{lang}").MESSAGES
            except Exception:
                _catalog = {}
    return _catalog


def tr(text):
    """Translate a German text into the configured language (if missing, it stays German)."""
    if not isinstance(text, str) or current() == "de":
        return text
    return _cat().get(text, text)
