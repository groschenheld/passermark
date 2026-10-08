# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Übersetzungen: vollständig, Platzhalter identisch, Rückfall auf Deutsch."""
import ast, glob, importlib, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["PASSERMARK_LANG"] = "de"
from pdfdruck import l10n

ROOT = os.path.join(os.path.dirname(__file__), "..", "pdfdruck")
LANGS = ("en", "hu", "es", "fr")


def code_strings():
    out = set()
    for p in glob.glob(os.path.join(ROOT, "**", "*.py"), recursive=True):
        if os.sep + "lang" + os.sep in p:
            continue
        for n in ast.walk(ast.parse(open(p, encoding="utf-8").read())):
            if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "tr" and n.args \
                    and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                out.add(n.args[0].value)
    return out


def ph(s):
    return sorted(re.findall(r"\{\d+[^}]*\}", s))


def test_catalogs_complete_and_consistent():
    need = code_strings()
    cats = {l: importlib.import_module(f"pdfdruck.lang.{l}").MESSAGES for l in LANGS}
    keys = set(cats["en"])
    for l, c in cats.items():
        assert set(c) == keys, f"{l}: Schlüssel weichen von en ab"
        missing = need - set(c)
        assert not missing, f"{l}: fehlende Übersetzungen: {sorted(missing)[:5]}"
        bad = [k for k, v in c.items() if ph(k) != ph(v)]
        assert not bad, f"{l}: Platzhalter abweichend: {bad[:3]}"


def test_switch_and_fallback():
    l10n.set_language("fr")
    assert l10n.tr("Drucken…") == "Imprimer…"
    assert l10n.tr("gibt es nicht") == "gibt es nicht"        # unbekannt -> unverändert
    l10n.set_language("de")
    assert l10n.tr("Drucken…") == "Drucken…"


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("ok", k)
