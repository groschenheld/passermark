# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Conditions in workflows ("if", "choose") – checked against the CURRENT PDF of the workflow. No Qt.

    {"pages": {">=": 8}, "format": "A5"}                    several entries = all must hold
    {"any": [{"format": "A4"}, {"format": "A5"}]}            any / all / not
    {"filename": {"matches": "*_sw.pdf"}}                    matches = pattern (* ?), case-insensitive
    {"var.kunde": {"in": ["Muster", "Huber"]}}              variables from --var / the watcher's "vars"

    Operators: a plain value means "equal"; otherwise {"==" | "!=" | ">" | ">=" | "<" | "<=" | "in" | "matches": …}.
    Texts are compared case-insensitively. Values are only computed when a condition needs them – the check facts
    (errors, rgb, fonts_missing …) run the document check once per file.
"""
from __future__ import annotations

import fnmatch
import os

from .l10n import tr

# Name -> (Typ, Beschreibung). Typen: int, float, bool, str, list
FACTS = {
    "pages": ("int", "number of pages"),
    "width_mm": ("float", "width of the first page in mm (reading direction)"),
    "height_mm": ("float", "height of the first page in mm (reading direction)"),
    "format": ("str", "standard size of the first page – its trim size if it has one (A4, SRA3, Letter …; '' = none)"),
    "page_format": ("str", "standard size of the first page itself, bleed included"),
    "orientation": ("str", "portrait | landscape | square (first page)"),
    "mixed_sizes": ("bool", "pages of different sizes"),
    "trim": ("bool", "first page has a trim size (TrimBox)"),
    "bleed_mm": ("float", "bleed of the first page in mm (0 = none)"),
    "size_mb": ("float", "file size in MB"),
    "filename": ("str", "file name of the (first) input file"),
    "errors": ("int", "errors found by the document check"),
    "warnings": ("int", "warnings found by the document check"),
    "infos": ("int", "notes found by the document check"),
    "rgb": ("bool", "RGB content (images or colours)"),
    "spot_colors": ("bool", "spot colours present"),
    "spot_names": ("list", "names of the spot colours"),
    "fonts_missing": ("bool", "fonts that are not embedded (standard fonts excluded)"),
    "transparency": ("bool", "transparency present"),
    "output_intent": ("str", "output intent (e.g. 'Coated FOGRA39'; '' = none)"),
    "layers": ("int", "number of layers"),
}
CHECK_FACTS = {"errors", "warnings", "infos", "rgb", "spot_colors", "spot_names", "fonts_missing", "transparency"}
OPS = ("==", "!=", ">", ">=", "<", "<=", "in", "matches")
LOGIC = ("all", "any", "not")
VAR_PREFIX = "var."


def validate(cond, where: str = "if") -> list:
    """Problems [(where, message)] of a condition – unknown values, operators or types."""
    probs = []
    if not isinstance(cond, dict) or not cond:
        return [(where, tr("Bedingung als Objekt erwartet, z. B. {\"pages\": {\">=\": 8}}"))]
    for k, v in cond.items():
        w = f"{where}.{k}"
        if k in ("all", "any"):
            if not isinstance(v, list) or not v:
                probs.append((w, tr("Liste von Bedingungen erwartet")))
                continue
            for i, c in enumerate(v):
                probs += validate(c, f"{w}[{i}]")
            continue
        if k == "not":
            probs += validate(v, w)
            continue
        if not (k in FACTS or (k.startswith(VAR_PREFIX) and len(k) > len(VAR_PREFIX))):
            probs.append((w, tr("unbekannter Prüfwert – möglich: {0}").format(", ".join(list(FACTS) + ["var.NAME"]))))
            continue
        typ = FACTS[k][0] if k in FACTS else "str"
        if isinstance(v, dict):
            if not v:
                probs.append((w, tr("Vergleich fehlt")))
            for op, val in v.items():
                if op not in OPS:
                    probs.append((f"{w}.{op}", tr("unbekannter Vergleich – möglich: {0}").format(", ".join(OPS))))
                elif op == "in" and not isinstance(val, list):
                    probs.append((f"{w}.in", tr("Liste erwartet")))
                elif op in (">", ">=", "<", "<=") and (typ not in ("int", "float") or not _is_num(val)):
                    probs.append((f"{w}.{op}", tr("Zahl erwartet") if typ in ("int", "float")
                                  else tr("„{0}“ geht nur bei Zahlen").format(op)))
                elif op == "matches" and not isinstance(val, str):
                    probs.append((f"{w}.matches", tr("Muster als Text erwartet, z. B. \"*_sw.pdf\"")))
        elif typ in ("int", "float") and not _is_num(v):
            probs.append((w, tr("Zahl erwartet")))
        elif typ == "bool" and not isinstance(v, bool):
            probs.append((w, tr("true oder false erwartet")))
    return probs


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _norm(v):
    return v.casefold() if isinstance(v, str) else v


def _cmp(actual, op: str, want) -> bool:
    if op == "in":
        return _norm(actual) in [_norm(x) for x in want] or (
            isinstance(actual, list) and any(_norm(a) in [_norm(x) for x in want] for a in actual))
    if op == "matches":
        items = actual if isinstance(actual, list) else [actual]
        return any(fnmatch.fnmatchcase(str(a).casefold(), str(want).casefold()) for a in items)
    if op in ("==", "!="):
        eq = (_norm(want) in [_norm(a) for a in actual]) if isinstance(actual, list) and not isinstance(want, list) \
            else _norm(actual) == _norm(want)
        if _is_num(actual) and _is_num(want):
            eq = abs(float(actual) - float(want)) < 1e-6
        return eq if op == "==" else not eq
    try:
        a, b = float(actual), float(want)
    except (TypeError, ValueError):
        return False
    return {">": a > b, ">=": a >= b, "<": a < b, "<=": a <= b}[op]


def evaluate(cond, facts) -> tuple[bool, str]:
    """(erfüllt?, Begründung für Protokoll/JSON, z. B. "pages 12 >= 8, format A5 == A5")."""
    parts, ok = [], True
    for k, v in cond.items():
        if k == "all":
            res = [evaluate(c, facts) for c in v]
            r, why = all(x[0] for x in res), "all(" + "; ".join(x[1] for x in res) + ")"
        elif k == "any":
            res = [evaluate(c, facts) for c in v]
            r, why = any(x[0] for x in res), "any(" + "; ".join(x[1] for x in res) + ")"
        elif k == "not":
            r0, why0 = evaluate(v, facts)
            r, why = not r0, f"not({why0})"
        else:
            actual = facts.get(k)
            ops = v.items() if isinstance(v, dict) else [("==", v)]
            r, sub = True, []
            for op, want in ops:
                hit = _cmp(actual, op, want)
                r = r and hit
                sub.append(f"{k} {_show(actual)} {op} {_show(want)}" + ("" if hit else " ✗"))
            why = ", ".join(sub)
        ok = ok and r
        parts.append(why)
    return ok, ", ".join(parts)


def _show(v) -> str:
    if isinstance(v, float):
        return f"{v:g}"
    if isinstance(v, str):
        return v or "''"
    return str(v)


class Facts:
    """Prüfwerte eines PDFs – erst berechnet, wenn eine Bedingung sie braucht; einmal je Datei."""

    def __init__(self, path: str, filename: str = "", variables: dict | None = None):
        self.path, self.filename, self.vars = path, filename or os.path.basename(path), dict(variables or {})
        self._basic = None
        self._check = None

    def get(self, key: str):
        if key.startswith(VAR_PREFIX):
            return self.vars.get(key[len(VAR_PREFIX):], "")
        if key == "filename":
            return self.filename
        if key in CHECK_FACTS:
            return self.check().get(key)
        return self.basic().get(key)

    def as_dict(self, keys=None) -> dict:
        return {k: self.get(k) for k in (keys or FACTS)}

    def basic(self) -> dict:
        if self._basic is None:
            from . import docinfo
            d = docinfo.inspect(self.path)
            pl = d["page_list"]
            p0 = pl[0] if pl else {}
            w, h = p0.get("width_mm") or 0.0, p0.get("height_mm") or 0.0
            trim = p0.get("trim_mm")
            self._basic = {
                "pages": d["pages"], "width_mm": w, "height_mm": h,
                "format": _format_name(*(trim or (w, h))), "page_format": _format_name(w, h),
                "orientation": p0.get("orientation", ""),
                "mixed_sizes": len(d["formats_mm"]) > 1,
                "trim": bool(trim), "bleed_mm": float(p0.get("bleed_mm") or 0.0),
                "size_mb": round(d["size_bytes"] / 1048576, 3),
                "output_intent": ", ".join(d["details"].get("output_intents") or []),
                "layers": int(d["details"].get("layers") or 0),
            }
        return self._basic

    def check(self) -> dict:
        if self._check is None:
            from . import preflight
            with open(self.path, "rb") as f:
                rep = preflight.analyze(f.read(), deep_layers=False, pdfium_parts=True)
            c = rep.counts()
            cr = rep.colors
            spots = sorted({n for ns in (cr.spots.values() if cr else []) for n in ns})
            self._check = {
                "errors": c["error"], "warnings": c["warning"], "infos": c["info"],
                "rgb": bool(cr and any("RGB" in v for v in cr.page_colors.values())),
                "spot_colors": bool(spots), "spot_names": spots,
                "fonts_missing": any(f.status == "missing" for f in rep.fonts),
                "transparency": bool(rep.transparency),
            }
        return self._check


def _format_name(w_mm: float, h_mm: float, tol: float = 2.0) -> str:
    from .papersizes import UI_FORMATS
    lo, hi = sorted((w_mm, h_mm))
    for name, (a, b) in UI_FORMATS.items():
        if abs(lo - a) <= tol and abs(hi - b) <= tol:
            return name
    return ""
