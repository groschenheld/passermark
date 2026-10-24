# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Workflows: several jobs in a row, described as JSON – the public interface for other programs.

    passermark-cli run ablauf.json [ausgabe.pdf] [--in datei.pdf …] [--var kunde=Muster] [--json]

Other programs (scripts, watcher, shop connection, a GUI for workflows) talk to Passermark only through the
command line and these JSON files – they never import Passermark code. The format is versioned (VERSION) and
described as JSON Schema (`passermark-cli schema`); see docs/cli-api.md.

    {
      "passermark": "workflow", "version": 1,
      "name": "Visitenkarten SRA3",
      "input": "${input}",                       (text or list – several files are merged first)
      "output": "${dir}/fertig/${stem}-sra3.pdf",
      "options": {"image_dpi": 96, "password": ""},
      "steps": [
        {"job": "preflight_fix", "settings": {"fix": "flatten_layers"}},
        {"job": "impose", "preset": "Visitenkarten", "settings": {"sheet": "SRA3"}, "pages": "1-2"}
      ]
    }

Variables ${name}: from --var name=value plus ${input} (first input file), ${dir} (folder of the first input),
${stem} (its name without extension), ${workflow_dir}, ${date} (YYYY-MM-DD). Relative paths are relative to
the workflow file.

No Qt here – runs in the CLI process and later in the watcher.
"""
from __future__ import annotations

import dataclasses
import json
import os
import re
import shutil
import tempfile
import types
import typing

from .l10n import tr

KIND = "workflow"
VERSION = 1                 # format of the workflow file
API = 1                     # command line interface for other programs (commands, events, error codes)

# error codes in JSON output ({"event": "error", "code": …}) – stable, for programs
E_USAGE, E_NOT_FOUND, E_INVALID, E_FAILED, E_CANCELLED = "usage", "not_found", "invalid", "failed", "cancelled"

_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_TOP_KEYS = {"passermark", "version", "name", "description", "input", "output", "options", "steps"}
_STEP_KEYS = {"job", "name", "settings", "preset", "pages", "if"}
_FLOW_KEYS = {"job", "name", "if", "message"}           # fail / stop
_CHOOSE_KEYS = {"choose", "name"}
_OPTION_KEYS = {"image_dpi": (int, float), "password": (str,)}


PRINT = "print"             # Schritt, der druckt (kein Auftrag in core.JOBS – das PDF bleibt unverändert)
FAIL, STOP, CHOOSE = "fail", "stop", "choose"   # Ablaufsteuerung: abbrechen mit Meldung, beenden, verzweigen
FLOW = (FAIL, STOP)
E_REJECTED = "rejected"     # „fail“-Schritt: Datei abgelehnt (Meldung aus dem Ablauf)


class Rejected(RuntimeError):
    """A fail step was reached – message from the workflow (the watcher puts the file into failed/)."""


def step_jobs() -> list:
    from . import core
    return list(core.JOBS) + [PRINT]


def step_settings_class(job: str):
    if job == PRINT:
        from .printcli import PrintSettings
        return PrintSettings
    from . import core
    return core.settings_class(job)


class WorkflowError(ValueError):
    """Workflow is not valid. problems: [(where, message)]."""

    def __init__(self, problems: list):
        self.problems = problems
        super().__init__("; ".join(f"{w}: {m}" if w else m for w, m in problems))


# --------------------------------------------------------------------------- #
# JSON Schema from the settings classes
# --------------------------------------------------------------------------- #
def _union_args(t):
    if isinstance(t, types.UnionType) or typing.get_origin(t) is typing.Union:
        return typing.get_args(t)
    return None


def _type_schema(t) -> dict:
    args = _union_args(t)
    if args is not None:
        opts = [_type_schema(a) for a in args if a is not type(None)]
        s = opts[0] if len(opts) == 1 else {"anyOf": opts}
        if type(None) in args:
            s = {"anyOf": [s, {"type": "null"}]}
        return s
    if dataclasses.is_dataclass(t):
        return settings_schema(t)
    origin = typing.get_origin(t) or t
    if t is bool:
        return {"type": "boolean"}
    if t is int:
        return {"type": "integer"}
    if t is float:
        return {"type": "number"}
    if t is str:
        return {"type": "string"}
    if origin in (list, tuple):
        return {"type": "array"}
    if origin is dict:
        return {"type": "object"}
    return {}


def settings_schema(cls) -> dict:
    """JSON Schema of a settings class (types and defaults; unknown keys not allowed)."""
    hints = typing.get_type_hints(cls)
    default = cls()
    props = {}
    for f in dataclasses.fields(cls):
        s = dict(_type_schema(hints.get(f.name)))
        v = getattr(default, f.name)
        if not dataclasses.is_dataclass(v):
            s["default"] = v if not isinstance(v, tuple) else list(v)
        props[f.name] = s
    return {"type": "object", "properties": props, "additionalProperties": False}


def schema() -> dict:
    """JSON Schema of the workflow file (all jobs with their settings)."""
    defs, variants = {}, []
    for job in step_jobs():
        defs[f"settings.{job}"] = settings_schema(step_settings_class(job))
        variants.append({
            "type": "object",
            "required": ["job"],
            "properties": {
                "job": {"const": job},
                "name": {"type": "string"},
                "preset": {"type": "string", "description": "preset name saved in Passermark or JSON file"},
                "settings": {"$ref": f"#/$defs/settings.{job}"},
                "pages": {"type": "string", "description": "e.g. 1,3-5 (1-based)"},
                "if": {"$ref": "#/$defs/condition"},
            },
            "additionalProperties": False,
        })
    for job in FLOW:
        variants.append({"type": "object", "required": ["job"], "additionalProperties": False, "properties": {
            "job": {"const": job}, "name": {"type": "string"}, "if": {"$ref": "#/$defs/condition"},
            "message": {"type": "string", "description": "${var} and ${fact} are replaced"}}})
    steps_ref = {"type": "array", "items": {"$ref": "#/$defs/step"}}
    variants.append({"type": "object", "required": [CHOOSE], "additionalProperties": False, "properties": {
        "name": {"type": "string"},
        CHOOSE: {"type": "array", "minItems": 1, "items": {"oneOf": [
            {"type": "object", "required": ["if", "steps"], "additionalProperties": False,
             "properties": {"if": {"$ref": "#/$defs/condition"}, "steps": steps_ref}},
            {"type": "object", "required": ["else"], "additionalProperties": False,
             "properties": {"else": steps_ref}}]}}}})
    from . import conditions
    defs["step"] = {"oneOf": variants}
    defs["condition"] = {
        "type": "object", "minProperties": 1,
        "description": "facts of the current PDF (" + ", ".join(conditions.FACTS) + ", var.NAME) with a value "
                       "(equal) or {operator: value} – operators " + ", ".join(conditions.OPS)
                       + "; all / any (lists of conditions), not",
        "properties": {"all": {"type": "array", "items": {"$ref": "#/$defs/condition"}},
                       "any": {"type": "array", "items": {"$ref": "#/$defs/condition"}},
                       "not": {"$ref": "#/$defs/condition"}}}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"urn:passermark:workflow:{VERSION}",
        "title": "Passermark workflow",
        "type": "object",
        "required": ["passermark", "version", "steps"],
        "properties": {
            "passermark": {"const": KIND},
            "version": {"const": VERSION},
            "name": {"type": "string"},
            "description": {"type": "string"},
            "input": {"anyOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}, "minItems": 1}]},
            "output": {"type": "string", "description": "result PDF – optional when a step prints"},
            "options": {"type": "object", "additionalProperties": False, "properties": {
                "image_dpi": {"type": "number", "default": 96},
                "password": {"type": "string", "default": ""}}},
            "steps": {"type": "array", "items": {"$ref": "#/$defs/step"}},
        },
        "additionalProperties": False,
        "$defs": defs,
    }


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #
def _check_type(value, t) -> bool:
    args = _union_args(t)
    if args is not None:
        return any(_check_type(value, a) for a in args)
    if t is type(None):
        return value is None
    if dataclasses.is_dataclass(t):
        return isinstance(value, dict)
    origin = typing.get_origin(t) or t
    if t is bool:
        return isinstance(value, bool)
    if t is int:
        return isinstance(value, int) and not isinstance(value, bool)
    if t is float:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t is str:
        return isinstance(value, str)
    if origin in (list, tuple):
        return isinstance(value, list)
    if origin is dict:
        return isinstance(value, dict)
    return True


def _type_name(t) -> str:
    s = _type_schema(t)
    if "type" in s:
        return s["type"]
    return " | ".join(x.get("type", "?") for x in s.get("anyOf", []) if isinstance(x, dict)) or "?"


def check_settings(cls, data, where: str = "settings") -> list:
    """Problems in a settings dict: unknown keys (typing errors), wrong types. [] = fine."""
    if not isinstance(data, dict):
        return [(where, tr("Objekt erwartet"))]
    hints = typing.get_type_hints(cls)
    names = {f.name for f in dataclasses.fields(cls)}
    out = []
    for k, v in data.items():
        if k not in names:
            out.append((f"{where}.{k}", tr("unbekannte Einstellung")))
            continue
        t = hints.get(k)
        if dataclasses.is_dataclass(t) and isinstance(v, dict):
            out += check_settings(t, v, f"{where}.{k}")
        elif not _check_type(v, t):
            out.append((f"{where}.{k}", tr("falscher Typ: {0} erwartet").format(_type_name(t))))
    return out


def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _subst(obj, vars_: dict, missing: set):
    if isinstance(obj, str):
        def rep(m):
            if m.group(1) in vars_:
                return str(vars_[m.group(1)])
            missing.add(m.group(1))
            return m.group(0)
        return _VAR.sub(rep, obj)
    if isinstance(obj, list):
        return [_subst(x, vars_, missing) for x in obj]
    if isinstance(obj, dict):
        return {k: _subst(v, vars_, missing) for k, v in obj.items()}
    return obj


@dataclasses.dataclass
class Step:
    job: str
    name: str
    settings: dict
    pages: list | None
    cond: dict | None = None          # "if": Schritt nur, wenn die Bedingung gilt
    message: str = ""                 # fail / stop
    branches: list | None = None      # choose: [(Bedingung oder None = sonst, [Step …])]
    where: str = ""                   # steps[2].choose[0].steps[1] – für Meldungen

    def to_dict(self) -> dict:
        """Für check --json und das Druckprotokoll."""
        if self.job == CHOOSE:
            return {"choose": [dict({"if": c} if c is not None else {}, **{"steps" if c is not None else "else":
                                                                          [x.to_dict() for x in st]})
                               for c, st in self.branches or []], "name": self.name}
        d = {"job": self.job, "name": self.name}
        if self.job in FLOW:
            d["message"] = self.message
        else:
            d["settings"] = self.settings
            d["pages"] = None if self.pages is None else [p + 1 for p in self.pages]
        if self.cond is not None:
            d["if"] = self.cond
        return d


def walk_steps(steps):
    """Alle Schritte, auch die in Verzweigungen."""
    for st in steps:
        yield st
        for _c, sub in st.branches or []:
            yield from walk_steps(sub)


@dataclasses.dataclass
class Plan:
    """Checked, ready-to-run workflow (variables replaced, presets loaded, paths absolute)."""
    name: str
    inputs: list
    output: str
    steps: list
    image_dpi: float = 96.0
    password: str = ""


def _has_print(raw) -> bool:
    """Druckt der Ablauf irgendwo (auch in einem Zweig)? Dann darf die Ausgabedatei fehlen."""
    if not isinstance(raw, list):
        return False
    for x in raw:
        if not isinstance(x, dict):
            continue
        if x.get("job") == PRINT:
            return True
        for br in x.get(CHOOSE) or [] if isinstance(x.get(CHOOSE), list) else []:
            if isinstance(br, dict) and (_has_print(br.get("steps")) or _has_print(br.get("else"))):
                return True
    return False


def load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except ValueError as e:
        raise WorkflowError([("", tr("kein gültiges JSON: {0}").format(e))])
    if not isinstance(data, dict):
        raise WorkflowError([("", tr("Objekt erwartet"))])
    return data


def prepare(data: dict, base_dir: str = ".", inputs: list | None = None, output: str | None = None,
            variables: dict | None = None, check_files: bool = True) -> Plan:
    """Check a workflow and make it runnable. inputs/output from the command line take precedence.
        Raises WorkflowError with all problems at once (not just the first)."""
    from . import cli, core, presets
    import datetime
    probs = []
    if data.get("passermark") != KIND:
        probs.append(("passermark", tr("muss \"{0}\" sein").format(KIND)))
    ver = data.get("version")
    if not isinstance(ver, int) or isinstance(ver, bool):
        probs.append(("version", tr("Zahl erwartet")))
    elif ver > VERSION:
        probs.append(("version", tr("Ablauf ist für eine neuere Passermark-Version (Format {0}, unterstützt: {1})")
                      .format(ver, VERSION)))
    for k in data:
        if k not in _TOP_KEYS:
            probs.append((k, tr("unbekannter Eintrag")))

    base_dir = os.path.abspath(base_dir or ".")

    def absp(p):
        return p if os.path.isabs(p) else os.path.normpath(os.path.join(base_dir, p))

    # inputs first: they define the built-in variables
    raw_in = inputs if inputs else data.get("input")
    if isinstance(raw_in, str):
        raw_in = [raw_in]
    if not raw_in or not isinstance(raw_in, list) or not all(isinstance(x, str) and x for x in raw_in):
        probs.append(("input", tr("Eingabedatei fehlt (im Ablauf oder mit --in)")))
        raw_in = []
    vars_ = {"workflow_dir": base_dir, "date": datetime.date.today().isoformat()}
    vars_.update(variables or {})
    missing: set = set()
    in_paths = [absp(_subst(p, vars_, missing)) for p in raw_in]
    if in_paths:
        vars_.setdefault("input", in_paths[0])
        vars_.setdefault("dir", os.path.dirname(in_paths[0]))
        vars_.setdefault("stem", os.path.splitext(os.path.basename(in_paths[0]))[0])
    if check_files:
        for i, p in enumerate(in_paths):
            if "${" not in p and not os.path.isfile(p):
                probs.append((f"input[{i}]" if len(in_paths) > 1 else "input",
                              tr("Datei nicht gefunden: {0}").format(p)))

    raw_out = output if output else data.get("output")
    prints = _has_print(data.get("steps"))
    if not raw_out and prints:
        out_path = ""                            # nur drucken, keine Datei
    elif not raw_out or not isinstance(raw_out, str):
        probs.append(("output", tr("Ausgabedatei fehlt (im Ablauf oder als zweites Argument)")))
        out_path = ""
    else:
        out_path = absp(_subst(raw_out, vars_, missing))
        if any(os.path.abspath(out_path) == os.path.abspath(p) for p in in_paths):
            probs.append(("output", tr("Eingabe und Ausgabe dürfen nicht dieselbe Datei sein.")))

    opts = data.get("options") or {}
    if not isinstance(opts, dict):
        probs.append(("options", tr("Objekt erwartet")))
        opts = {}
    for k, v in opts.items():
        if k not in _OPTION_KEYS:
            probs.append((f"options.{k}", tr("unbekannte Einstellung")))
        elif not isinstance(v, _OPTION_KEYS[k]) or isinstance(v, bool):
            probs.append((f"options.{k}", tr("falscher Typ")))

    from . import conditions

    def parse_steps(raw_list, prefix: str) -> list:
        out = []
        for i, st in enumerate(raw_list):
            where = f"{prefix}[{i}]"
            if not isinstance(st, dict):
                probs.append((where, tr("Objekt erwartet")))
                continue
            if CHOOSE in st:                                   # Verzweigung
                for k in st:
                    if k not in _CHOOSE_KEYS:
                        probs.append((f"{where}.{k}", tr("unbekannter Eintrag")))
                br_raw = st[CHOOSE]
                if not isinstance(br_raw, list) or not br_raw:
                    probs.append((f"{where}.choose", tr("Liste von Zweigen erwartet")))
                    continue
                branches = []
                for j, br in enumerate(br_raw):
                    bw = f"{where}.choose[{j}]"
                    if not isinstance(br, dict):
                        probs.append((bw, tr("Objekt erwartet")))
                        continue
                    if "else" in br:
                        if set(br) - {"else"}:
                            probs.append((bw, tr("„else“ steht allein: {\"else\": [Schritte]}")))
                        if j != len(br_raw) - 1:
                            probs.append((bw, tr("„else“ muss der letzte Zweig sein")))
                        sub = br["else"]
                        cond = None
                    else:
                        for k in br:
                            if k not in ("if", "steps"):
                                probs.append((f"{bw}.{k}", tr("unbekannter Eintrag")))
                        if "if" not in br:
                            probs.append((bw, tr("Bedingung „if“ fehlt (oder „else“ für den letzten Zweig)")))
                        cond = _subst(br.get("if"), vars_, missing)
                        probs.extend(conditions.validate(cond, f"{bw}.if"))
                        sub = br.get("steps")
                    if not isinstance(sub, list):
                        probs.append((f"{bw}.{'else' if cond is None else 'steps'}", tr("Liste von Schritten erwartet")))
                        sub = []
                    branches.append((cond, parse_steps(sub, f"{bw}.{'else' if cond is None else 'steps'}")))
                out.append(Step(CHOOSE, str(st.get("name") or CHOOSE), {}, None, branches=branches, where=where))
                continue
            job = st.get("job")
            cond = None
            if "if" in st:
                cond = _subst(st["if"], vars_, missing)
                probs.extend(conditions.validate(cond, f"{where}.if"))
            if job in FLOW:                                    # fail / stop
                for k in st:
                    if k not in _FLOW_KEYS:
                        probs.append((f"{where}.{k}", tr("unbekannter Eintrag")))
                msg = st.get("message", "")
                if not isinstance(msg, str):
                    probs.append((f"{where}.message", tr("Text erwartet")))
                    msg = ""
                out.append(Step(job, str(st.get("name") or job), {}, None, cond=cond, message=msg, where=where))
                continue
            for k in st:
                if k not in _STEP_KEYS:
                    probs.append((f"{where}.{k}", tr("unbekannter Eintrag")))
            if job not in step_jobs():
                probs.append((f"{where}.job", tr("Unbekannter Auftrag: {0}").format(job)
                              + " (" + ", ".join(step_jobs() + list(FLOW)) + tr(", oder „choose“") + ")"))
                continue
            st = _subst({k: v for k, v in st.items() if k != "if"}, vars_, missing)
            settings = {}
            if st.get("preset") and job == PRINT:
                probs.append((f"{where}.preset", tr("Druck-Presets gibt es im Ablauf nicht – Einstellungen direkt "
                                                    "angeben")))
            elif st.get("preset"):
                try:
                    ppath = presets.resolve(job, absp(st["preset"]) if os.path.isfile(absp(st["preset"]))
                                            else st["preset"])
                    kind, settings = core.load_settings(ppath)
                    if kind != job:
                        probs.append((f"{where}.preset", tr("Preset ist für „{0}“, nicht für „{1}“").format(kind, job)))
                    cli._rebase_paths(settings, os.path.dirname(os.path.abspath(ppath)))
                except (OSError, ValueError, KeyError) as e:
                    probs.append((f"{where}.preset", str(e)))
                    settings = {}
            own = st.get("settings") or {}
            if not isinstance(own, dict):
                probs.append((f"{where}.settings", tr("Objekt erwartet")))
                own = {}
            cli._rebase_paths(own, base_dir)
            settings = _deep_merge(settings, own)
            probs.extend(check_settings(step_settings_class(job), settings, f"{where}.settings"))
            if job == PRINT and isinstance(settings.get("layout"), dict):
                from .layout import LayoutSettings
                probs.extend(check_settings(LayoutSettings, settings["layout"], f"{where}.settings.layout"))
            pages = None
            if st.get("pages"):
                try:
                    pages = cli.parse_pages(str(st["pages"]))
                except ValueError:
                    probs.append((f"{where}.pages", tr("ungültiger Seitenbereich: {0}").format(st["pages"])))
            out.append(Step(job, st.get("name") or job, settings, pages, cond=cond, where=where))
        return out

    steps_raw = data.get("steps")
    if not isinstance(steps_raw, list):
        probs.append(("steps", tr("Liste erwartet")))
        steps_raw = []
    steps = parse_steps(steps_raw, "steps")
    for name in sorted(missing):
        probs.append(("", tr("Variable ${{{0}}} nicht gesetzt (--var {0}=…)").format(name)))
    if probs:
        raise WorkflowError(probs)
    return Plan(data.get("name") or "", in_paths, out_path, steps,
                float(opts.get("image_dpi", 96)), opts.get("password") or "")


# --------------------------------------------------------------------------- #
# execution
# --------------------------------------------------------------------------- #
def _gather_input(plan: Plan, work: str, notes: list) -> str:
    """Single PDF: used directly. Several files, images, Office: converted and merged into one PDF."""
    from . import convert
    if len(plan.inputs) == 1 and plan.inputs[0].lower().endswith(".pdf") and not plan.password:
        return plan.inputs[0]
    import pypdfium2 as pdfium
    out = pdfium.PdfDocument.new()
    try:
        for p in plan.inputs:
            doc, used = convert.to_document(p, work, plan.image_dpi, plan.password or None)
            try:
                out.import_pages(doc)
            finally:
                doc.close()
            if used:
                notes.append(tr("{0}: umgewandelt mit {1}").format(os.path.basename(p), used))
        path = os.path.join(work, "input.pdf")
        out.save(path)
    finally:
        out.close()
    return path


def run(plan: Plan, events=None, cancel=None, variables: dict | None = None) -> dict:
    """Run the steps one after another; only the finished result is written to plan.output.
        events(dict): {"event": "step"|"progress"|"step_done"|"condition"|"branch", …} – see docs/cli-api.md.
        Conditions are checked against the current PDF; "fail" raises Rejected, "stop" ends early (the result so
        far is written)."""
    from . import conditions, core

    def emit(**ev):
        if events is not None:
            events(ev)
    work = tempfile.mkdtemp(prefix="passermark-run-")
    notes, results, decisions = [], [], []
    total = sum(1 for st in walk_steps(plan.steps) if st.job != CHOOSE)
    state = {"cur": None, "n": 0, "facts": None, "done": [], "stopped": None}
    fname = os.path.basename(plan.inputs[0]) if plan.inputs else ""

    def facts():
        f = state["facts"]
        if f is None or f.path != state["cur"]:
            f = state["facts"] = conditions.Facts(state["cur"], fname, variables or {})
        return f

    def holds(cond, where, what) -> bool:
        ok, why = conditions.evaluate(cond, facts())
        decisions.append({"where": where, "result": ok, "why": why})
        emit(event="condition", where=where, what=what, result=ok, why=why)
        return ok

    def message(text: str) -> str:
        """${…} in fail/stop-Meldungen: Variablen und Prüfwerte (${format}, ${pages} …)."""
        def sub(m):
            k = m.group(1)
            if variables and k in variables:
                return str(variables[k])
            if k in conditions.FACTS:
                try:
                    return conditions._show(facts().get(k))
                except Exception:
                    return m.group(0)
            return m.group(0)
        return _VAR.sub(sub, text or "")

    def exec_steps(steps):
        for st in steps:
            core._check(cancel)
            if st.job == CHOOSE:
                taken = None
                for j, (cond, sub) in enumerate(st.branches or []):
                    if cond is None or holds(cond, f"{st.where}.choose[{j}]", "branch"):
                        taken = j
                        break
                emit(event="branch", where=st.where, taken=taken, branch="else" if (
                    taken is not None and st.branches[taken][0] is None) else taken)
                if taken is not None:
                    if exec_steps(st.branches[taken][1]):
                        return True
                continue
            if st.cond is not None and not holds(st.cond, f"{st.where}.if", st.job):
                emit(event="step_skipped", where=st.where, job=st.job, name=st.name)
                continue
            if st.job == FAIL:
                raise Rejected(message(st.message) or tr("Abgelehnt durch den Ablauf ({0}).").format(st.where))
            if st.job == STOP:
                state["stopped"] = message(st.message) or tr("Ablauf beendet ({0}).").format(st.where)
                emit(event="stopped", where=st.where, message=state["stopped"])
                return True
            state["n"] += 1
            k = state["n"]
            emit(event="step", step=k, steps=total, job=st.job, name=st.name, where=st.where)
            prog = (lambda d, t, x="", _k=k: emit(event="progress", step=_k, done=d, total=t, text=x))
            if st.job == PRINT:
                from .printcli import PrintSettings, print_pdf
                from . import printlog
                ps = core.settings_from_dict(PrintSettings, st.settings)
                before = [dict({"job": b.job, "settings": b.settings},
                               **({"pages": printlog._pages_text(b.pages)} if b.pages else {}))
                          for b in state["done"] if b.job != PRINT]
                with printlog.in_workflow(plan.inputs, before):
                    info = print_pdf(state["cur"], ps, st.pages, progress=prog)
                pn = list(info.get("notes") or [])
                results.append({"step": k, "job": st.job, "name": st.name, "where": st.where, "info": info,
                                "notes": pn})
                notes.extend(pn)
                emit(event="step_done", step=k, job=st.job, info=info, notes=pn)
                state["done"].append(st)
                continue                         # das PDF bleibt, wie es ist
            dst = os.path.join(work, f"step{k}.pdf")
            r = core.run_job(st.job, state["cur"], dst, st.settings, {"pages": st.pages} if st.pages else None,
                             progress=prog, cancel=cancel)
            results.append({"step": k, "job": st.job, "name": st.name, "where": st.where, "info": r.info,
                            "notes": r.notes})
            notes.extend(r.notes)
            emit(event="step_done", step=k, job=st.job, info=r.info, notes=r.notes)
            state["done"].append(st)
            state["cur"] = dst
        return False

    try:
        state["cur"] = _gather_input(plan, work, notes)
        exec_steps(plan.steps)
        core._check(cancel)
        if state["stopped"]:
            notes.append(state["stopped"])
        base = {"steps": results, "notes": notes, "decisions": decisions, "stopped": state["stopped"]}
        if not plan.output:                      # nur gedruckt
            return dict(base, output=None, pages=None)
        d = os.path.dirname(plan.output)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = plan.output + ".part"
        try:
            shutil.copyfile(state["cur"], tmp)
            os.replace(tmp, plan.output)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        pages = None
        try:
            import pypdfium2 as pdfium
            d_ = pdfium.PdfDocument(plan.output)
            pages = len(d_)
            d_.close()
        except Exception:
            pass
        return dict(base, output=plan.output, pages=pages)
    finally:
        shutil.rmtree(work, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Ablauf-Ordner: Abläufe beim Namen aufrufen (passermark-cli run Visitenkarten --in …)
# --------------------------------------------------------------------------- #
FOLDER = "workflows"
OLD_FOLDER = "ablaeufe"         # bis 1.14 – wird beim ersten Zugriff umbenannt bzw. weiter gelesen


def _with_legacy(d: str) -> list:
    """[Ordner …]: der neue Ordner; ein alter „ablaeufe“ (bis 1.14) wird umbenannt. Geht das nicht (keine Rechte)
        oder gibt es beide (z. B. „workflows“ schon von Hand angelegt), wird der alte zusätzlich gelesen –
        nach dem neuen, damit nichts verloren geht."""
    old = os.path.join(os.path.dirname(d), OLD_FOLDER)
    if not os.path.isdir(old):
        return [d]
    if not os.path.exists(d):
        try:
            os.rename(old, d)
            return [d]
        except OSError:
            return [old]
    return [d, old]


def folders(cfg: dict | None = None) -> list:
    """[(Art, Ordner)] in dieser Reihenfolge – der erste mit dem Namen gewinnt:
        user    eigene: Linux ~/.config/passermark/workflows · Windows %APPDATA%\\Passermark\\workflows
        shared  vom Admin eingetragene (workflow_dirs, z. B. eine Netzwerkfreigabe für alle)
        system  für alle: Linux /etc/passermark/workflows · Windows %ProgramData%\\Passermark\\workflows
        Ein alter Ordner „ablaeufe“ neben dem neuen wird jeweils direkt danach gelesen."""
    from . import presets
    from .platform import config_dir
    if cfg is None:
        from . import config
        cfg = config.load()
    out = [("user", d) for d in _with_legacy(os.path.join(os.path.dirname(presets.root_dir()), FOLDER))]
    for d in cfg.get("workflow_dirs") or []:
        if isinstance(d, str) and d.strip():
            out.append(("shared", os.path.expandvars(os.path.expanduser(d.strip()))))
    out += [("system", d) for d in _with_legacy(os.path.join(config_dir(), FOLDER))]
    return out


def list_workflows() -> list:
    """Alle Abläufe in den Ablauf-Ordnern: [{"name", "file", "source", "title", "description", "jobs", "error"}]."""
    seen, out = set(), []
    for src, d in folders():
        try:
            files = sorted(f for f in os.listdir(d) if f.lower().endswith(".json") and not f.startswith("."))
        except OSError:
            continue
        for f in files:
            name = f[:-5]
            if name.lower() in seen:
                continue
            seen.add(name.lower())
            path = os.path.join(d, f)
            item = {"name": name, "file": path, "source": src, "title": "", "description": "", "jobs": [],
                    "error": None}
            try:
                data = load(path)
                item["title"] = str(data.get("name") or "")
                item["description"] = str(data.get("description") or "")
                item["jobs"] = [st.get("job") for st in data.get("steps") or [] if isinstance(st, dict)]
                if data.get("passermark") != KIND:
                    item["error"] = tr("keine Ablauf-Datei")
            except (OSError, WorkflowError) as e:
                item["error"] = str(e)
            out.append(item)
    return out


def find(ref: str) -> str:
    """Datei oder Name eines Ablaufs aus den Ablauf-Ordnern -> Pfad. FileNotFoundError mit den vorhandenen Namen."""
    if os.path.isfile(ref):
        return ref
    stem = ref[:-5] if ref.lower().endswith(".json") else ref
    if os.sep not in stem and "/" not in stem:
        for _src, d in folders():
            try:
                for f in os.listdir(d):
                    if f.lower() == stem.lower() + ".json":
                        return os.path.join(d, f)
            except OSError:
                pass
    names = ", ".join(w["name"] for w in list_workflows()) or "–"
    raise FileNotFoundError(tr("Ablauf nicht gefunden: {0} (in den Ablauf-Ordnern: {1})").format(ref, names))
