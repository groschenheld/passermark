# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Nautilus-Kontextmenü für Passermark.

* Nur Bilder ausgewählt   -> „Als PDF öffnen“ (mehrere Bilder = ein Dokument)
* Nur PDFs ausgewählt     -> „Drucken“ ohne Dialog (Sitzungs- bzw. Admin-Standards)
Installiert nach /usr/share/nautilus-python/extensions/ (Paket python3-nautilus).
"""
import subprocess

import gi

try:
    gi.require_version("Nautilus", "4.0")
except ValueError:
    gi.require_version("Nautilus", "3.0")
from gi.repository import GObject, Nautilus  # noqa: E402

PDFDRUCK = "/usr/local/bin/passermark"
IMAGE_MIMES = {
    "image/jpeg", "image/png", "image/tiff", "image/bmp", "image/x-bmp", "image/x-ms-bmp",
    "image/gif", "image/webp", "image/heic", "image/heif", "image/heic-sequence", "image/heif-sequence",
}


IMAGE_EXT = {".jpg", ".jpeg", ".jpe", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp", ".heic", ".heif", ".svg", ".svgz"}
OFFICE_EXT = {".doc", ".docx", ".docm", ".dot", ".dotx", ".odt", ".ott", ".rtf", ".txt", ".wpd", ".xls", ".xlsx",
              ".xlsm", ".ods", ".csv", ".ppt", ".pptx", ".pps", ".ppsx", ".odp", ".odg", ".vsd", ".vsdx", ".pub",
              ".html", ".htm", ".xps", ".epub", ".djvu"}


LABELS = {
    "merge": {"de": "{n} Dateien als ein PDF zusammenführen (Passermark)", "en": "Merge {n} files into one PDF (Passermark)",
              "hu": "{n} fájl egyesítése egy PDF-be (Passermark)", "es": "Combinar {n} archivos en un PDF (Passermark)",
              "fr": "Fusionner {n} fichiers en un PDF (Passermark)"},
    "open1": {"de": "Als PDF öffnen", "en": "Open as PDF", "hu": "Megnyitás PDF-ként", "es": "Abrir como PDF",
              "fr": "Ouvrir en PDF"},
    "openN": {"de": "{n} Bilder als ein PDF öffnen", "en": "Open {n} images as one PDF", "hu": "{n} kép megnyitása egy PDF-ként",
              "es": "Abrir {n} imágenes como un PDF", "fr": "Ouvrir {n} images en un PDF"},
    "office": {"de": "Als PDF öffnen (Passermark)", "en": "Open as PDF (Passermark)", "hu": "Megnyitás PDF-ként (Passermark)",
               "es": "Abrir como PDF (Passermark)", "fr": "Ouvrir en PDF (Passermark)"},
    "print1": {"de": "Drucken (Passermark)", "en": "Print (Passermark)", "hu": "Nyomtatás (Passermark)",
               "es": "Imprimir (Passermark)", "fr": "Imprimer (Passermark)"},
    "printN": {"de": "{n} PDFs drucken (Passermark)", "en": "Print {n} PDFs (Passermark)", "hu": "{n} PDF nyomtatása (Passermark)",
               "es": "Imprimir {n} PDF (Passermark)", "fr": "Imprimer {n} PDF (Passermark)"},
    "repair": {"de": "Reparieren / optimieren (Passermark)", "en": "Repair / optimize (Passermark)",
               "hu": "Javítás / optimalizálás (Passermark)", "es": "Reparar / optimizar (Passermark)",
               "fr": "Réparer / optimiser (Passermark)"},
}


def _lang():
    """Sprache wie in Passermark: Datei → Einstellungen > Admin-Standard > Systemsprache > Englisch."""
    import json
    import os
    for path, key in ((os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
                                    "passermark", "settings.json"), "language"),
                      ("/etc/passermark/defaults.json", "language")):
        try:
            with open(path, encoding="utf-8") as f:
                v = json.load(f).get(key, "")
            if v and v != "auto":
                return v
        except Exception:
            pass
    for v in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        code = (os.environ.get(v) or "")[:2].lower()
        if code in ("de", "en", "hu", "es", "fr"):
            return code
    return "en"


def _t(key, n=0):
    lang = _lang()
    return LABELS[key].get(lang, LABELS[key]["en"]).format(n=n)


def _kind(f):
    import os
    e = os.path.splitext(f.get_name() or "")[1].lower()
    if e == ".pdf" or f.get_mime_type() == "application/pdf":
        return "pdf"
    if e in IMAGE_EXT or f.get_mime_type() in IMAGE_MIMES:
        return "image"
    if e in OFFICE_EXT:
        return "office"
    return None


class PassermarkMenu(GObject.GObject, Nautilus.MenuProvider):
    def get_file_items(self, *args):
        files = args[-1]                      # API 3.0: (window, files) – API 4.0: (files)
        if not files:
            return []
        if any(f.get_uri_scheme() != "file" or f.is_directory() for f in files):
            return []
        kinds = [_kind(f) for f in files]
        if None in kinds:
            return []
        n, ks = len(files), set(kinds)
        items = []

        def add(name, label, tip, flag):
            it = Nautilus.MenuItem(name=f"Passermark::{name}", label=label, tip=tip)
            it.connect("activate", self._run, files, flag)
            items.append(it)

        if n > 1:
            add("merge", _t("merge", n), "", "--merge")
        if ks == {"image"}:
            add("open_images", _t("open1") if n == 1 else _t("openN", n), "", "--open")
        elif ks == {"office"} and n == 1:
            add("open_office", _t("office"), "", "--open")
        elif ks == {"pdf"}:
            add("print", _t("print1") if n == 1 else _t("printN", n), "", "--print")
            add("repair", _t("repair"), "", "--repair")
        return items

    def _run(self, _item, files, flag):
        paths = sorted(f.get_location().get_path() for f in files)
        subprocess.Popen([PDFDRUCK, flag, *paths], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
