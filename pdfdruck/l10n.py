# SPDX-License-Identifier: GPL-3.0-or-later
# pdfToolkit – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Oberflächensprache: Deutsch (Ausgangssprache), Englisch, Ungarisch, Spanisch, Französisch.

tr("deutscher Text") liefert den Text in der eingestellten Sprache; fehlt eine Übersetzung, bleibt der
deutsche Text stehen. Platzhalter: tr("Seite {0} von {1}").format(a, b).

Sprache: Benutzereinstellung (Datei → Einstellungen) > Admin-Standard > Systemsprache > Englisch.
Nur Standardbibliothek – auch vom Admin-Helfer importierbar.
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
        return os.path.join(base, "pdfToolkit", "settings.json")
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "pdftoolkit", "settings.json")


def load_settings() -> dict:
    try:
        with open(_settings_file(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(d: dict):
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
        want = os.environ.get("PDFTOOLKIT_LANG") or load_settings().get("language") or "auto"
        if want == "auto":
            want = _admin_default() or "auto"
        _lang = want if want in LANGS else system_language()
    return _lang


def set_language(code: str):
    """Für Tests/Neustart: Sprache sofort umstellen (die Oberfläche wird beim Neustart neu aufgebaut)."""
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
    """Deutschen Text in die eingestellte Sprache übersetzen (fehlt er, bleibt er deutsch)."""
    if not isinstance(text, str) or current() == "de":
        return text
    return _cat().get(text, text)
