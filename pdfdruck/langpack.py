# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Translations by anyone: export the texts as a table, check a filled-in table, install it for the user or turn
it into a catalog of the program (pdfdruck/lang/<code>.py). Standard library only, no Qt.

Formats:
- CSV (semicolon, UTF-8 with BOM – opens in Excel and LibreOffice): columns source_de, english, translation, note
- JSON: {"format": "passermark-translation", "language": "it", "name": "Italiano", "program": "1.19.6",
  "messages": {"<German source text>": "<translation>"}}

Installed translations live next to the user settings in lang/<code>.json (l10n.user_lang_dir()). For a language
that ships with the program they complete or correct it; a new code becomes a new language in File → Settings.
"""

from __future__ import annotations

import csv
import importlib
import io
import json
import os
import re
from dataclasses import dataclass, field

from . import __version__, l10n

FORMAT = "passermark-translation"
COLUMNS = ("source_de", "english", "translation", "note")
_PLACEHOLDER = re.compile(r"\{\w*(?:[!:][^{}]*)?\}")  # str.format fields: {} {0} {name} {0:.1f}


def placeholders(text: str) -> list[str]:
    """The str.format fields of a text; doubled braces ({{Spalte}} – shown literally) do not count."""
    return _PLACEHOLDER.findall(text.replace("{{", "").replace("}}", ""))


_CODE = re.compile(r"^[a-z]{2,3}(_[A-Z]{2})?$")


# --------------------------------------------------------------------------- #
# the texts of the program
# --------------------------------------------------------------------------- #
def _bundled(code: str) -> dict:
    """The catalog shipped with the program for ``code`` ({} if there is none)."""
    if code == "de" or code not in l10n.LANGS:
        return {}
    try:
        return dict(importlib.import_module(f"{__package__}.lang.{code}").MESSAGES)
    except ImportError:
        return {}


def source_texts() -> list[str]:
    """All German source texts of the interface. The English catalog is complete (tests/test_l10n.py), so its
    keys are the list."""
    return list(_bundled("en"))


def existing(code: str) -> dict:
    """What is already translated for ``code``: shipped catalog, completed by an installed translation."""
    out = _bundled(code)
    out.update(l10n.user_messages(code))
    return out


def note_for(text: str) -> str:
    """Hint for the translator: placeholders, shortcut letter, line breaks."""
    notes = []
    ph = placeholders(text)
    if ph:
        notes.append("keep " + ", ".join(dict.fromkeys(ph)))
    if re.search(r"&[^&\s]", text.replace("&&", "")):
        notes.append("& marks the shortcut letter")
    if "&&" in text:
        notes.append("&& shows one &")
    if "\n" in text:
        notes.append("contains line breaks")
    return "; ".join(notes)


def rows(code: str | None = None) -> list[dict]:
    """One row per text: German source, English as a help, the existing translation of ``code`` (if any)."""
    en = _bundled("en")
    have = existing(code) if code else {}
    return [
        {"source_de": t, "english": en.get(t, ""), "translation": have.get(t, ""), "note": note_for(t)}
        for t in source_texts()
    ]


# --------------------------------------------------------------------------- #
# writing and reading files
# --------------------------------------------------------------------------- #
def export(path: str, code: str | None = None, name: str = "") -> int:
    """Write the template (CSV or JSON by the file extension); returns the number of texts."""
    data = rows(code)
    if path.lower().endswith(".json"):
        doc = {
            "format": FORMAT,
            "language": code or "",
            "name": name or l10n.languages().get(code or "", ""),
            "program": __version__,
            "messages": {r["source_de"]: r["translation"] for r in data},
            "english": {r["source_de"]: r["english"] for r in data},
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
    else:
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS, delimiter=";", quoting=csv.QUOTE_ALL)
            w.writeheader()
            w.writerows(data)
    return len(data)


def read(path: str) -> tuple[dict, dict]:
    """Read a filled-in table. -> (meta {"language", "name"} – may be empty, messages {source: translation}).
    Empty translations are left out. Raises ValueError for a file that is not a translation."""
    with open(path, "rb") as f:
        raw = f.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:  # Excel's plain "CSV" saves in the Windows code page
        text = raw.decode("cp1252", errors="replace")
    if path.lower().endswith(".json") or text.lstrip().startswith("{"):
        doc = json.loads(text)
        if not isinstance(doc, dict):
            raise ValueError("JSON: expected an object")
        msgs = doc.get("messages", doc) if doc.get("format") == FORMAT or "messages" in doc else doc
        meta = {"language": str(doc.get("language") or ""), "name": str(doc.get("name") or "")}
        if not isinstance(msgs, dict):
            raise ValueError("JSON: 'messages' must be an object")
        return meta, {str(k): str(v) for k, v in msgs.items() if isinstance(v, str) and v.strip()}
    return {"language": "", "name": ""}, _read_csv(text)


def _read_csv(text: str) -> dict:
    first = text.split("\n", 1)[0]
    sep = max(";,\t", key=first.count)  # the separator of the header line (Excel in German uses ";")

    class dialect(csv.excel):
        delimiter = sep

    reader = csv.reader(io.StringIO(text), dialect)
    head = [h.strip().lower() for h in next(reader, [])]

    def col(*names):
        for n in names:
            if n in head:
                return head.index(n)
        return -1

    src = col("source_de", "deutsch", "german", "source", "quelle")
    dst = col("translation", "übersetzung", "uebersetzung")
    if src < 0 or dst < 0:
        raise ValueError("CSV: columns 'source_de' and 'translation' not found")
    out = {}
    for row in reader:
        if len(row) > max(src, dst) and row[src] and row[dst].strip():
            out[row[src]] = row[dst]
    return out


# --------------------------------------------------------------------------- #
# checking
# --------------------------------------------------------------------------- #
@dataclass
class Report:
    """Result of check(): how much is translated, what is missing, what is broken."""

    total: int = 0
    translated: int = 0
    missing: list = field(default_factory=list)
    unknown: list = field(default_factory=list)  # texts the program no longer has
    problems: list = field(default_factory=list)  # (source, what is wrong)

    @property
    def percent(self) -> int:
        """Share of translated texts in whole percent."""
        return round(100 * self.translated / self.total) if self.total else 0

    @property
    def ok(self) -> bool:
        """Usable: no broken placeholders (missing texts simply stay in English/German)."""
        return not self.problems

    def summary(self) -> str:
        """The result as a few lines of text (command line)."""
        lines = [f"{self.translated} of {self.total} texts translated ({self.percent} %)"]
        if self.missing:
            lines.append(f"missing: {len(self.missing)}")
        if self.unknown:
            lines.append(f"no longer used by the program (ignored): {len(self.unknown)}")
        for src, what in self.problems[:20]:
            lines.append(f'problem in "{src[:60]}": {what}')
        if len(self.problems) > 20:
            lines.append(f"… {len(self.problems) - 20} more problems")
        return "\n".join(lines)


def check(messages: dict) -> Report:
    """Compare a translation with the texts of the program: coverage, unknown texts, placeholders."""
    src = source_texts()
    known = set(src)
    rep = Report(total=len(src))
    for t in src:
        tr_ = messages.get(t, "")
        if not tr_.strip():
            rep.missing.append(t)
            continue
        rep.translated += 1
        a, b = sorted(placeholders(t)), sorted(placeholders(tr_))
        if a != b:
            rep.problems.append((t, f"placeholders {', '.join(a) or '–'} became {', '.join(b) or '–'}"))
    rep.unknown = [t for t in messages if t not in known]
    return rep


# --------------------------------------------------------------------------- #
# installing for the user, or as a catalog of the program
# --------------------------------------------------------------------------- #
def valid_code(code: str) -> bool:
    """Language code like "it", "pt_BR"; German is the source language and cannot be translated into."""
    return bool(_CODE.match(code or "")) and code != "de"


def install(messages: dict, code: str, name: str = "") -> str:
    """Install a translation for the user (only texts the program knows); returns the file path."""
    if not valid_code(code):
        raise ValueError(f"invalid language code: {code!r}")
    known = set(source_texts())
    doc = {
        "format": FORMAT,
        "language": code,
        "name": name or l10n.LANGS.get(code) or code,
        "program": __version__,
        "messages": {k: v for k, v in messages.items() if k in known and v.strip()},
    }
    d = l10n.user_lang_dir()
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, code + ".json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
    l10n.forget_user_languages()
    return path


def remove(code: str) -> bool:
    """Remove an installed translation; True if there was one."""
    path = os.path.join(l10n.user_lang_dir(), code + ".json")
    try:
        os.remove(path)
    except FileNotFoundError:
        return False
    l10n.forget_user_languages()
    return True


def catalog_source(messages: dict, code: str, name: str) -> str:
    """Python source of pdfdruck/lang/<code>.py (same layout as the shipped catalogs), in the program's order."""
    lines = [
        "# SPDX-License-Identifier: GPL-3.0-or-later",
        "# Passermark – Copyright (C) 2026 Hias",
        "# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public",
        "# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.",
        "# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.",
        f'"""Übersetzung: {name}. Schlüssel = deutscher Ausgangstext. Fehlende Einträge bleiben deutsch."""',
        "",
        "MESSAGES = {",
    ]
    for k in source_texts():  # only texts the program knows, in its order
        v = messages.get(k, "")
        if v.strip():
            # a JSON string literal is a valid Python string literal
            lines.append(f"    {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)},")
    lines.append("}")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# command line: passermark-cli lang …
# --------------------------------------------------------------------------- #
_HELP = """passermark-cli lang – translations

  lang list                                  languages (shipped and installed)
  lang export FILE.csv|FILE.json [--code CODE] template; with --code the existing translation is filled in
  lang check FILE                            coverage, missing texts, broken placeholders
  lang install FILE --code CODE [--name N]   install for this user (File → Settings → language)
  lang remove CODE                           remove an installed translation
  lang import FILE --code CODE --name N [--out PATH]
                                             make pdfdruck/lang/<code>.py for the repository
"""


def cli_main(argv: list[str]) -> int:
    """``passermark-cli lang …``; returns the exit code (0 ok, 1 error, 2 wrong usage)."""
    import argparse

    p = argparse.ArgumentParser(prog="passermark-cli lang", add_help=False)
    p.add_argument("cmd", nargs="?")
    p.add_argument("arg", nargs="?")
    p.add_argument("--code", default="")
    p.add_argument("--name", default="")
    p.add_argument("--out", default="")
    p.add_argument("-h", "--help", action="store_true")
    try:
        a = p.parse_args(argv)
    except SystemExit:
        print(_HELP)
        return 2
    if a.help or not a.cmd:
        print(_HELP)
        return 0 if a.help else 2
    try:
        return _run(a)
    except (OSError, ValueError) as e:
        print(f"error: {e}")
        return 1


def _run(a) -> int:
    if a.cmd == "list":
        user = l10n.user_languages()
        for code, name in l10n.languages().items():
            mark = " (installed)" if code in user else ""
            print(f"{code:6} {name}{mark}")
        return 0
    if a.cmd == "remove":
        if not a.arg:
            print(_HELP)
            return 2
        print("removed" if remove(a.arg) else "not installed")
        return 0
    if not a.arg:
        print(_HELP)
        return 2
    if a.cmd == "export":
        n = export(a.arg, a.code or None, a.name)
        print(f"{n} texts written to {a.arg}")
        return 0
    meta, msgs = read(a.arg)
    code = a.code or meta.get("language", "")
    name = a.name or meta.get("name", "")
    rep = check(msgs)
    print(rep.summary())
    if a.cmd == "check":
        return 0 if rep.ok else 1
    if not valid_code(code):
        print("error: --code is needed (e.g. it, pt_BR)")
        return 2
    if not rep.ok:
        print("error: fix the placeholders first")
        return 1
    if a.cmd == "install":
        print("installed: " + install(msgs, code, name))
        return 0
    if a.cmd == "import":
        if not name:
            print("error: --name is needed (the language in its own language, e.g. Italiano)")
            return 2
        out = a.out or os.path.join(os.path.dirname(os.path.abspath(__file__)), "lang", code + ".py")
        with open(out, "w", encoding="utf-8") as f:
            f.write(catalog_source(msgs, code, name))
        print(f"written: {out}")
        if code not in l10n.LANGS:
            print(
                "new language – also add it to: l10n.LANGS, cfgvalidate (language), tests/test_l10n.py (LANGS) "
                "and LANGS in linux/passermark.spec and windows/passermark.spec"
            )
        return 0
    print(_HELP)
    return 2
