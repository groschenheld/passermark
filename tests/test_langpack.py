# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Translations by anyone (langpack.py): export, read back, check, install, turn into a catalog."""

import csv
import importlib
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

TMP = tempfile.mkdtemp()
os.environ["XDG_CONFIG_HOME"] = TMP  # installed translations go to a temporary folder
os.environ["APPDATA"] = TMP
os.environ.pop("PASSERMARK_LANG", None)

from pdfdruck import l10n, langpack  # noqa: E402

HU = importlib.import_module("pdfdruck.lang.hu").MESSAGES


def test_round_trip_csv_and_json():
    for ext in ("csv", "json"):
        path = os.path.join(TMP, "hu." + ext)
        n = langpack.export(path, "hu")
        assert n == len(langpack.source_texts())
        _meta, msgs = langpack.read(path)
        assert msgs == HU, ext  # every text survives, also quotes, braces and line breaks
        assert langpack.check(msgs).ok


def test_excel_variants():
    """Comma instead of semicolon, Windows code page instead of UTF-8."""
    path = os.path.join(TMP, "x.csv")
    with open(path, "w", encoding="cp1252", newline="") as f:
        w = csv.writer(f)
        w.writerow(["source_de", "english", "translation", "note"])
        w.writerow(["Übersetzung", "Translation", "Traduzione", ""])
    assert langpack.read(path)[1] == {"Übersetzung": "Traduzione"}


def test_check_placeholders():
    src = next(t for t in langpack.source_texts() if "{0}" in t and "{{" not in t)
    assert langpack.check({src: src}).ok
    rep = langpack.check({src: src.replace("{0}", "")})
    assert not rep.ok and rep.problems[0][0] == src
    assert langpack.placeholders("Doppelklick fügt {{Spalte}} ein, Seite {0} von {n:.1f}") == ["{0}", "{n:.1f}"]
    assert langpack.check({"gibt es nicht": "x"}).unknown == ["gibt es nicht"]


def test_install_new_language_and_remove():
    src = langpack.source_texts()
    one = src[0]
    path = langpack.install({one: "uno", "unbekannt": "x"}, "it", "Italiano")
    assert os.path.dirname(path) == l10n.user_lang_dir()
    assert l10n.languages()["it"] == "Italiano" and "it" in l10n.user_languages()
    l10n.set_language("it")
    assert l10n.tr(one) == "uno"
    en = importlib.import_module("pdfdruck.lang.en").MESSAGES
    assert l10n.tr(src[1]) == en[src[1]]  # what the new language lacks comes from English
    assert langpack.remove("it") and "it" not in l10n.languages()
    l10n.set_language("de")


def test_correction_of_a_shipped_language():
    one = langpack.source_texts()[0]
    langpack.install({one: "javítva"}, "hu")
    l10n.set_language("hu")
    assert l10n.tr(one) == "javítva"
    other = langpack.source_texts()[1]
    assert l10n.tr(other) == HU[other]  # the rest stays the shipped translation
    langpack.remove("hu")
    l10n.set_language("de")


def test_invalid_codes():
    for bad in ("de", "", "Italiano", "i", "it-IT"):
        assert not langpack.valid_code(bad), bad
    assert langpack.valid_code("pt_BR")


def test_catalog_source_matches_shipped():
    ns = {}
    exec(langpack.catalog_source(HU, "hu", "Magyar"), ns)  # noqa: S102 – our own generated source
    assert ns["MESSAGES"] == {k: v for k, v in HU.items() if k in set(langpack.source_texts())}


def test_template_in_docs_is_current():
    path = os.path.join(HERE, "..", "docs", "translations", "passermark-texts.csv")
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    want = langpack.rows()
    assert [(r["source_de"], r["english"]) for r in rows] == [(r["source_de"], r["english"]) for r in want], (
        "run: passermark-cli lang export docs/translations/passermark-texts.csv"
    )


if __name__ == "__main__":
    for k, fn in list(globals().items()):
        if k.startswith("test_"):
            fn()
            print("ok", k)
