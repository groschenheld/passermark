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
VERSION = 1  # format of the workflow file
API = 1  # command line interface for other programs (commands, events, error codes)

# error codes in JSON output ({"event": "error", "code": …}) – stable, for programs
E_USAGE, E_NOT_FOUND, E_INVALID, E_FAILED, E_CANCELLED = "usage", "not_found", "invalid", "failed", "cancelled"

_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_TOP_KEYS = {"passermark", "version", "name", "description", "input", "output", "options", "steps"}
_STEP_KEYS = {"job", "name", "settings", "preset", "pages", "if"}
_FLOW_KEYS = {"job", "name", "if", "message"}  # fail / stop
_CHOOSE_KEYS = {"choose", "name"}
_OPTION_KEYS = {"image_dpi": (int, float), "password": (str,)}


PRINT = "print"  # step that prints (not a job in core.JOBS – the PDF stays unchanged)
PLAN = "plan"  # plan printing on rolls (every page a plan) – also prints, the PDF stays unchanged
PRINTS = (PRINT, PLAN)
FAIL, STOP, CHOOSE = "fail", "stop", "choose"  # flow control: abort with a message, stop, branch
FLOW = (FAIL, STOP)
E_REJECTED = "rejected"  # "fail" step: file rejected (message from the workflow)


class Rejected(RuntimeError):
    """A fail step was reached – message from the workflow (the watcher puts the file into failed/)."""


def step_jobs() -> list:
    """Names of everything a workflow step can run: all jobs plus print and plan."""
    from . import core

    return list(core.JOBS) + [PRINT, PLAN]


def step_settings_class(job: str):
    """Settings dataclass for the step ``job``."""
    if job == PRINT:
        from .printcli import PrintSettings

        return PrintSettings
    if job == PLAN:
        from .planprint import PlanSettings

        return PlanSettings
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
        variants.append(
            {
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
            }
        )
    for job in FLOW:
        variants.append(
            {
                "type": "object",
                "required": ["job"],
                "additionalProperties": False,
                "properties": {
                    "job": {"const": job},
                    "name": {"type": "string"},
                    "if": {"$ref": "#/$defs/condition"},
                    "message": {"type": "string", "description": "${var} and ${fact} are replaced"},
                },
            }
        )
    steps_ref = {"type": "array", "items": {"$ref": "#/$defs/step"}}
    variants.append(
        {
            "type": "object",
            "required": [CHOOSE],
            "additionalProperties": False,
            "properties": {
                "name": {"type": "string"},
                CHOOSE: {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "oneOf": [
                            {
                                "type": "object",
                                "required": ["if", "steps"],
                                "additionalProperties": False,
                                "properties": {"if": {"$ref": "#/$defs/condition"}, "steps": steps_ref},
                            },
                            {
                                "type": "object",
                                "required": ["else"],
                                "additionalProperties": False,
                                "properties": {"else": steps_ref},
                            },
                        ]
                    },
                },
            },
        }
    )
    from . import conditions

    defs["step"] = {"oneOf": variants}
    defs["condition"] = {
        "type": "object",
        "minProperties": 1,
        "description": "facts of the current PDF (" + ", ".join(conditions.FACTS) + ", var.NAME) with a value "
        "(equal) or {operator: value} – operators "
        + ", ".join(conditions.OPS)
        + "; all / any (lists of conditions), not",
        "properties": {
            "all": {"type": "array", "items": {"$ref": "#/$defs/condition"}},
            "any": {"type": "array", "items": {"$ref": "#/$defs/condition"}},
            "not": {"$ref": "#/$defs/condition"},
        },
    }
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
            "options": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "image_dpi": {"type": "number", "default": 96},
                    "password": {"type": "string", "default": ""},
                },
            },
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
    """One step of a workflow: job, settings, optional condition and branches."""

    job: str
    name: str
    settings: dict
    pages: list | None
    cond: dict | None = None  # "if": step only if the condition holds
    message: str = ""  # fail / stop
    branches: list | None = None  # choose: [(condition or None = otherwise, [Step …])]
    where: str = ""  # steps[2].choose[0].steps[1] – for messages

    def to_dict(self) -> dict:
        """For check --json and the print log."""
        if self.job == CHOOSE:
            return {
                "choose": [
                    dict(
                        {"if": c} if c is not None else {},
                        **{"steps" if c is not None else "else": [x.to_dict() for x in st]},
                    )
                    for c, st in self.branches or []
                ],
                "name": self.name,
            }
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
    """All steps, including those in branches."""
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
    """Does the workflow print anywhere (also in a branch)? Then the output file may be missing."""
    if not isinstance(raw, list):
        return False
    for x in raw:
        if not isinstance(x, dict):
            continue
        if x.get("job") in PRINTS:
            return True
        for br in x.get(CHOOSE) or [] if isinstance(x.get(CHOOSE), list) else []:
            if isinstance(br, dict) and (_has_print(br.get("steps")) or _has_print(br.get("else"))):
                return True
    return False


def load(path: str) -> dict:
    """Read a workflow file; raises ValueError if it is not valid JSON or not a workflow."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except ValueError as e:
        raise WorkflowError([("", tr("kein gültiges JSON: {0}").format(e))]) from e
    if not isinstance(data, dict):
        raise WorkflowError([("", tr("Objekt erwartet"))])
    return data


class _Preparer:
    """State of one prepare() call: the problems found so far, the variables and the folder relative paths refer to."""

    def __init__(self, data: dict, base_dir: str, variables: dict | None):
        import datetime

        self.data = data
        self.probs: list = []
        self.base_dir = os.path.abspath(base_dir or ".")
        self.vars = {"workflow_dir": self.base_dir, "date": datetime.date.today().isoformat()}
        self.vars.update(variables or {})
        self.missing: set = set()

    def problem(self, where: str, text: str):
        """Note a problem; all of them are reported together at the end."""
        self.probs.append((where, text))

    def absp(self, p: str) -> str:
        """Path relative to the workflow file made absolute."""
        return p if os.path.isabs(p) else os.path.normpath(os.path.join(self.base_dir, p))

    def subst(self, obj):
        """Replace ${…} variables; unknown ones are collected in self.missing."""
        return _subst(obj, self.vars, self.missing)

    def unknown_keys(self, obj: dict, allowed, where: str):
        """Report every entry of obj that is not allowed there."""
        for k in obj:
            if k not in allowed:
                self.problem(f"{where}.{k}", tr("unbekannter Eintrag"))

    def check_header(self):
        """Kind, format version and unknown top-level entries."""
        data = self.data
        if data.get("passermark") != KIND:
            self.problem("passermark", tr('muss "{0}" sein').format(KIND))
        ver = data.get("version")
        if not isinstance(ver, int) or isinstance(ver, bool):
            self.problem("version", tr("Zahl erwartet"))
        elif ver > VERSION:
            self.problem(
                "version",
                tr("Ablauf ist für eine neuere Passermark-Version (Format {0}, unterstützt: {1})").format(ver, VERSION),
            )
        for k in data:
            if k not in _TOP_KEYS:
                self.problem(k, tr("unbekannter Eintrag"))

    def inputs(self, inputs: list | None, check_files: bool) -> list:
        """Input files as absolute paths. They come first: they define the built-in variables."""
        raw_in = inputs if inputs else self.data.get("input")
        if isinstance(raw_in, str):
            raw_in = [raw_in]
        if not raw_in or not isinstance(raw_in, list) or not all(isinstance(x, str) and x for x in raw_in):
            self.problem("input", tr("Eingabedatei fehlt (im Ablauf oder mit --in)"))
            raw_in = []
        in_paths = [self.absp(self.subst(p)) for p in raw_in]
        if in_paths:
            self.vars.setdefault("input", in_paths[0])
            self.vars.setdefault("dir", os.path.dirname(in_paths[0]))
            self.vars.setdefault("stem", os.path.splitext(os.path.basename(in_paths[0]))[0])
        if check_files:
            for i, p in enumerate(in_paths):
                if "${" not in p and not os.path.isfile(p):
                    self.problem(
                        f"input[{i}]" if len(in_paths) > 1 else "input", tr("Datei nicht gefunden: {0}").format(p)
                    )
        return in_paths

    def output(self, output: str | None, in_paths: list) -> str:
        """Output file as absolute path; "" for a workflow that only prints."""
        raw_out = output if output else self.data.get("output")
        prints = _has_print(self.data.get("steps"))
        if not raw_out and prints:
            return ""  # print only, no file
        if not raw_out or not isinstance(raw_out, str):
            self.problem("output", tr("Ausgabedatei fehlt (im Ablauf oder als zweites Argument)"))
            return ""
        out_path = self.absp(self.subst(raw_out))
        if any(os.path.abspath(out_path) == os.path.abspath(p) for p in in_paths):
            self.problem("output", tr("Eingabe und Ausgabe dürfen nicht dieselbe Datei sein."))
        return out_path

    def options(self) -> dict:
        """The "options" block, checked for unknown entries and types."""
        opts = self.data.get("options") or {}
        if not isinstance(opts, dict):
            self.problem("options", tr("Objekt erwartet"))
            opts = {}
        for k, v in opts.items():
            if k not in _OPTION_KEYS:
                self.problem(f"options.{k}", tr("unbekannte Einstellung"))
            elif not isinstance(v, _OPTION_KEYS[k]) or isinstance(v, bool):
                self.problem(f"options.{k}", tr("falscher Typ"))
        return opts

    def condition(self, raw, where: str):
        """An "if" condition with variables replaced, validated."""
        from . import conditions

        cond = self.subst(raw)
        self.probs.extend(conditions.validate(cond, where))
        return cond

    def steps(self, raw_list, prefix: str) -> list:
        """Turn a list of raw steps into Step objects (recursively for branches)."""
        out = []
        for i, st in enumerate(raw_list):
            where = f"{prefix}[{i}]"
            if not isinstance(st, dict):
                self.problem(where, tr("Objekt erwartet"))
                continue
            if CHOOSE in st:
                step = self._choose_step(st, where)
            else:
                cond = self.condition(st["if"], f"{where}.if") if "if" in st else None
                if st.get("job") in FLOW:
                    step = self._flow_step(st, where, cond)
                else:
                    step = self._job_step(st, where, cond)
            if step is not None:
                out.append(step)
        return out

    def _choose_step(self, st: dict, where: str):
        """A branch: {"choose": [{"if": …, "steps": […]}, …, {"else": […]}]}."""
        self.unknown_keys(st, _CHOOSE_KEYS, where)
        br_raw = st[CHOOSE]
        if not isinstance(br_raw, list) or not br_raw:
            self.problem(f"{where}.choose", tr("Liste von Zweigen erwartet"))
            return None
        branches = []
        for j, br in enumerate(br_raw):
            bw = f"{where}.choose[{j}]"
            if not isinstance(br, dict):
                self.problem(bw, tr("Objekt erwartet"))
                continue
            if "else" in br:
                if set(br) - {"else"}:
                    self.problem(bw, tr('„else“ steht allein: {"else": [Schritte]}'))
                if j != len(br_raw) - 1:
                    self.problem(bw, tr("„else“ muss der letzte Zweig sein"))
                sub = br["else"]
                cond = None
            else:
                self.unknown_keys(br, ("if", "steps"), bw)
                if "if" not in br:
                    self.problem(bw, tr("Bedingung „if“ fehlt (oder „else“ für den letzten Zweig)"))
                cond = self.condition(br.get("if"), f"{bw}.if")
                sub = br.get("steps")
            key = "else" if cond is None else "steps"
            if not isinstance(sub, list):
                self.problem(f"{bw}.{key}", tr("Liste von Schritten erwartet"))
                sub = []
            branches.append((cond, self.steps(sub, f"{bw}.{key}")))
        return Step(CHOOSE, str(st.get("name") or CHOOSE), {}, None, branches=branches, where=where)

    def _flow_step(self, st: dict, where: str, cond):
        """ "fail" or "stop" with an optional message."""
        job = st.get("job")
        self.unknown_keys(st, _FLOW_KEYS, where)
        msg = st.get("message", "")
        if not isinstance(msg, str):
            self.problem(f"{where}.message", tr("Text erwartet"))
            msg = ""
        return Step(job, str(st.get("name") or job), {}, None, cond=cond, message=msg, where=where)

    def _job_step(self, st: dict, where: str, cond):
        """An ordinary step: a job with settings (own ones on top of an optional preset) and pages."""
        from . import cli

        job = st.get("job")
        self.unknown_keys(st, _STEP_KEYS, where)
        if job not in step_jobs():
            self.problem(
                f"{where}.job",
                tr("Unbekannter Auftrag: {0}").format(job)
                + " ("
                + ", ".join(step_jobs() + list(FLOW))
                + tr(", oder „choose“")
                + ")",
            )
            return None
        st = self.subst({k: v for k, v in st.items() if k != "if"})
        settings = self._preset_settings(st, job, where)
        own = st.get("settings") or {}
        if not isinstance(own, dict):
            self.problem(f"{where}.settings", tr("Objekt erwartet"))
            own = {}
        cli._rebase_paths(own, self.base_dir)
        settings = _deep_merge(settings, own)
        self.probs.extend(check_settings(step_settings_class(job), settings, f"{where}.settings"))
        if job == PRINT and isinstance(settings.get("layout"), dict):
            from .layout import LayoutSettings

            self.probs.extend(check_settings(LayoutSettings, settings["layout"], f"{where}.settings.layout"))
        pages = None
        if st.get("pages"):
            try:
                pages = cli.parse_pages(str(st["pages"]))
            except ValueError:
                self.problem(f"{where}.pages", tr("ungültiger Seitenbereich: {0}").format(st["pages"]))
        return Step(job, st.get("name") or job, settings, pages, cond=cond, where=where)

    def _preset_settings(self, st: dict, job: str, where: str) -> dict:
        """Settings from the preset a step names; {} without a preset or if it cannot be loaded."""
        from . import cli, core, presets

        if not st.get("preset"):
            return {}
        if job in PRINTS:
            self.problem(f"{where}.preset", tr("Druck-Presets gibt es im Ablauf nicht – Einstellungen direkt angeben"))
            return {}
        try:
            own_file = self.absp(st["preset"])
            ppath = presets.resolve(job, own_file if os.path.isfile(own_file) else st["preset"])
            kind, settings = core.load_settings(ppath)
            if kind != job:
                self.problem(f"{where}.preset", tr("Preset ist für „{0}“, nicht für „{1}“").format(kind, job))
            cli._rebase_paths(settings, os.path.dirname(os.path.abspath(ppath)))
        except (OSError, ValueError, KeyError) as e:
            self.problem(f"{where}.preset", str(e))
            return {}
        return settings


def prepare(
    data: dict,
    base_dir: str = ".",
    inputs: list | None = None,
    output: str | None = None,
    variables: dict | None = None,
    check_files: bool = True,
) -> Plan:
    """Check a workflow and make it runnable. inputs/output from the command line take precedence.
    Raises WorkflowError with all problems at once (not just the first)."""
    p = _Preparer(data, base_dir, variables)
    p.check_header()
    in_paths = p.inputs(inputs, check_files)
    out_path = p.output(output, in_paths)
    opts = p.options()
    steps_raw = data.get("steps")
    if not isinstance(steps_raw, list):
        p.problem("steps", tr("Liste erwartet"))
        steps_raw = []
    steps = p.steps(steps_raw, "steps")
    for name in sorted(p.missing):
        p.problem("", tr("Variable ${{{0}}} nicht gesetzt (--var {0}=…)").format(name))
    if p.probs:
        raise WorkflowError(p.probs)
    return Plan(
        data.get("name") or "", in_paths, out_path, steps, float(opts.get("image_dpi", 96)), opts.get("password") or ""
    )


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


class _Run:
    """State of one run(): the current PDF, the step counter, and what has been done and decided so far."""

    def __init__(self, plan: Plan, events, cancel, variables: dict | None, work: str):
        self.plan = plan
        self.events = events
        self.cancel = cancel
        self.variables = variables
        self.work = work  # temporary folder for the intermediate PDFs
        self.notes: list = []
        self.results: list = []
        self.decisions: list = []
        self.total = sum(1 for st in walk_steps(plan.steps) if st.job != CHOOSE)
        self.cur = None  # path of the PDF the next step works on
        self.n = 0  # number of the step being executed
        self.done: list = []  # steps executed so far
        self.stopped = None  # message of the "stop" step that ended the run
        self._facts = None
        self._fname = os.path.basename(plan.inputs[0]) if plan.inputs else ""

    def emit(self, **ev):
        """Send an event to the caller, if anyone listens."""
        if self.events is not None:
            self.events(ev)

    def facts(self):
        """Check values of the current PDF – read anew whenever a step has produced a new file."""
        from . import conditions

        f = self._facts
        if f is None or f.path != self.cur:
            f = self._facts = conditions.Facts(self.cur, self._fname, self.variables or {})
        return f

    def holds(self, cond, where: str, what: str) -> bool:
        """Evaluate a condition against the current PDF and record the decision."""
        from . import conditions

        ok, why = conditions.evaluate(cond, self.facts())
        self.decisions.append({"where": where, "result": ok, "why": why})
        self.emit(event="condition", where=where, what=what, result=ok, why=why)
        return ok

    def message(self, text: str) -> str:
        """${…} in fail/stop messages: variables and check values (${format}, ${pages} …)."""
        from . import conditions

        def sub(m):
            k = m.group(1)
            if self.variables and k in self.variables:
                return str(self.variables[k])
            if k in conditions.FACTS:
                try:
                    return conditions._show(self.facts().get(k))
                except Exception:  # noqa: BLE001 – unknown placeholder stays as written
                    return m.group(0)
            return m.group(0)

        return _VAR.sub(sub, text or "")

    def exec_steps(self, steps) -> bool:
        """Execute steps in order. Returns True if a "stop" step ended the run."""
        from . import core

        for st in steps:
            core._check(self.cancel)
            if st.job == CHOOSE:
                if self._exec_choose(st):
                    return True
                continue
            if st.cond is not None and not self.holds(st.cond, f"{st.where}.if", st.job):
                self.emit(event="step_skipped", where=st.where, job=st.job, name=st.name)
                continue
            if st.job == FAIL:
                raise Rejected(self.message(st.message) or tr("Abgelehnt durch den Ablauf ({0}).").format(st.where))
            if st.job == STOP:
                self.stopped = self.message(st.message) or tr("Ablauf beendet ({0}).").format(st.where)
                self.emit(event="stopped", where=st.where, message=self.stopped)
                return True
            self.n += 1
            k = self.n
            self.emit(event="step", step=k, steps=self.total, job=st.job, name=st.name, where=st.where)
            prog = lambda d, t, x="", _k=k: self.emit(event="progress", step=_k, done=d, total=t, text=x)
            if st.job in (PLAN, PRINT):
                self._exec_print(st, k, prog)
            else:
                self._exec_job(st, k, prog)
        return False

    def _exec_choose(self, st) -> bool:
        """Take the first branch whose condition holds (or "else") and execute its steps."""
        taken = None
        for j, (cond, _sub) in enumerate(st.branches or []):
            if cond is None or self.holds(cond, f"{st.where}.choose[{j}]", "branch"):
                taken = j
                break
        self.emit(
            event="branch",
            where=st.where,
            taken=taken,
            branch="else" if (taken is not None and st.branches[taken][0] is None) else taken,
        )
        return taken is not None and self.exec_steps(st.branches[taken][1])

    def _exec_print(self, st, k: int, prog):
        """Print the current PDF (sheet or plan/poster printing); the PDF itself stays as it is."""
        from . import core, printlog

        if st.job == PLAN:
            from .planprint import PlanSettings as settings_class
            from .planprint import print_pdf
        else:
            from .printcli import PrintSettings as settings_class
            from .printcli import print_pdf

        ps = core.settings_from_dict(settings_class, st.settings)
        before = [
            dict(
                {"job": b.job, "settings": b.settings},
                **({"pages": printlog._pages_text(b.pages)} if b.pages else {}),
            )
            for b in self.done
            if b.job not in PRINTS
        ]
        with printlog.in_workflow(self.plan.inputs, before, self.variables):
            info = print_pdf(self.cur, ps, st.pages, progress=prog)
        self._step_done(st, k, info, list(info.get("notes") or []))

    def _exec_job(self, st, k: int, prog):
        """Run a job that produces a new PDF; the next step continues with that file."""
        from . import core

        dst = os.path.join(self.work, f"step{k}.pdf")
        r = core.run_job(
            st.job,
            self.cur,
            dst,
            st.settings,
            {"pages": st.pages} if st.pages else None,
            progress=prog,
            cancel=self.cancel,
        )
        self._step_done(st, k, r.info, r.notes)
        self.cur = dst

    def _step_done(self, st, k: int, info, step_notes):
        """Record the result of a step and tell the caller."""
        self.results.append(
            {"step": k, "job": st.job, "name": st.name, "where": st.where, "info": info, "notes": step_notes}
        )
        self.notes.extend(step_notes)
        self.emit(event="step_done", step=k, job=st.job, info=info, notes=step_notes)
        self.done.append(st)

    def write_output(self) -> dict:
        """Write the finished PDF to plan.output (via a .part file) and build the result."""
        plan = self.plan
        if self.stopped:
            self.notes.append(self.stopped)
        base = {"steps": self.results, "notes": self.notes, "decisions": self.decisions, "stopped": self.stopped}
        if not plan.output:  # printed only
            return dict(base, output=None, pages=None)
        d = os.path.dirname(plan.output)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = plan.output + ".part"
        try:
            shutil.copyfile(self.cur, tmp)
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
        except Exception:  # noqa: BLE001 – optional part: works without it
            pass
        return dict(base, output=plan.output, pages=pages)


def run(plan: Plan, events=None, cancel=None, variables: dict | None = None) -> dict:
    """Run the steps one after another; only the finished result is written to plan.output.
    events(dict): {"event": "step"|"progress"|"step_done"|"condition"|"branch", …} – see docs/cli-api.md.
    Conditions are checked against the current PDF; "fail" raises Rejected, "stop" ends early (the result so
    far is written)."""
    from . import core

    work = tempfile.mkdtemp(prefix="passermark-run-")
    r = _Run(plan, events, cancel, variables, work)
    try:
        r.cur = _gather_input(plan, work, r.notes)
        r.exec_steps(plan.steps)
        core._check(cancel)
        return r.write_output()
    finally:
        shutil.rmtree(work, ignore_errors=True)


# --------------------------------------------------------------------------- #
# workflow folders: call workflows by name (passermark-cli run Visitenkarten --in …)
# --------------------------------------------------------------------------- #
FOLDER = "workflows"
OLD_FOLDER = "ablaeufe"  # old folder name – renamed on first access or still read


def _with_legacy(d: str) -> list:
    """[folder …]: the new folder; an old "ablaeufe" is renamed. If that is not possible (no permission)
    or both exist (e.g. "workflows" already created by hand), the old one is read as well –
    after the new one, so that nothing gets lost.
    """
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
    """[(kind, folder)] in this order – the first with the name wins:
    user    own: Linux ~/.config/passermark/workflows · Windows %APPDATA%\\Passermark\\workflows
    shared  entered by the admin (workflow_dirs, e.g. a network share for everyone)
    system  for everyone: Linux /etc/passermark/workflows · Windows %ProgramData%\\Passermark\\workflows
    An old folder "ablaeufe" next to the new one is read directly after it.
    """
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
    """All workflows in the workflow folders: [{"name", "file", "source", "title", "description", "jobs", "error"}]."""
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
            item = {
                "name": name,
                "file": path,
                "source": src,
                "title": "",
                "description": "",
                "jobs": [],
                "error": None,
            }
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
    """File or name of a workflow from the workflow folders -> path. FileNotFoundError with the existing names."""
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
