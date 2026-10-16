# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Command line: run jobs without a GUI.

    passermark-cli list
    passermark-cli settings cutcontour                       (default settings as JSON = preset template)
    passermark-cli cutcontour in.pdf out.pdf --set shape=rect --set bleed_mm=2
    passermark-cli cutcontour in.pdf out.pdf --preset sticker.json --pages 1,3-5
    passermark-cli cutcontour in.pdf out.pdf --preset Sticker               (preset saved in the program)
    passermark-cli presets [auftrag]                         (list saved presets)
    passermark-cli beispiele [zielordner]                   (fetch examples for variable data + presets)
    passermark-cli datenarten                                (data kinds for tables: vcard, wifi, email …)
    passermark-cli datenvorlage vcard karten.csv             (empty table with the matching columns)
    passermark-cli datencheck karten.csv [art]               (validate a table; return code 1 on problems)
    passermark-cli … --json-progress                         (progress as JSON lines, for the GUI)

Return value: 0 = ok, 1 = error, 2 = wrong invocation, 130 = cancelled (Ctrl+C).
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys

EXIT_OK, EXIT_ERROR, EXIT_USAGE, EXIT_CANCELLED = 0, 1, 2, 130


def parse_pages(text: str | None) -> list[int] | None:
    """'1,3-5' -> [0, 2, 3, 4] (Eingabe 1-basiert, Ergebnis 0-basiert)."""
    if not text:
        return None
    out = []
    for part in text.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            a, b = int(a), int(b)
            if a < 1 or b < a:
                raise ValueError(part)
            out.extend(range(a - 1, b))
        else:
            n = int(part)
            if n < 1:
                raise ValueError(part)
            out.append(n - 1)
    return sorted(set(out))


def _value(text: str):
    """Value from --set: JSON if possible (numbers, true/false, lists), otherwise text."""
    try:
        return json.loads(text)
    except ValueError:
        return text


def apply_sets(settings: dict, sets: list[str]) -> dict:
    """Apply --set a=1 --set detect.tolerance=40 to a (nested) dict."""
    for item in sets or []:
        if "=" not in item:
            raise ValueError(item)
        key, val = item.split("=", 1)
        cur = settings
        parts = key.strip().split(".")
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = _value(val.strip())
    return settings


class _Reporter:
    def __init__(self, json_mode: bool, quiet: bool):
        self.json, self.quiet = json_mode, quiet
        self.last = ""

    def emit(self, **ev):
        sys.stdout.write(json.dumps(ev, ensure_ascii=True) + "\n")    # reines ASCII: egal welche Konsolen-Codepage
        sys.stdout.flush()

    def progress(self, done, total, text=""):
        if self.json:
            self.emit(event="progress", done=done, total=total, text=text)
        elif not self.quiet:
            pct = int(100 * done / total) if total else 0
            bar = "#" * (pct // 5) + "-" * (20 - pct // 5)
            line = f"\r[{bar}] {pct:3d} %  {text}"
            sys.stderr.write(line + " " * max(0, len(self.last) - len(line)))
            sys.stderr.flush()
            self.last = line

    def finish_line(self):
        if not self.json and not self.quiet and self.last:
            sys.stderr.write("\n")
            sys.stderr.flush()


def _rebase_paths(settings: dict, base: str) -> None:
    """Relative file references in the preset (e.g. csv_path) are relative to the preset file if it does not
        exist in the current folder – so bundled presets work from anywhere.
    """
    for key in ("csv_path",):
        v = settings.get(key)
        if isinstance(v, str) and v and not os.path.isabs(v) and not os.path.exists(v):
            for cand in (os.path.join(base, v), os.path.join(os.path.dirname(base), v)):
                if os.path.exists(cand):
                    settings[key] = cand
                    break


def _data_cmd(a) -> int:
    """Data tables for variable data: show kinds, write an empty template, validate a table."""
    from . import datakinds, vdp
    from .l10n import tr
    if a.job == "datenarten":
        for kid in datakinds.IDS:
            k = datakinds.get(kid)
            print(f"{kid}\t{k.title}\t" + ";".join(c.key + ("*" if c.required else "") for c in k.cols))
        return EXIT_OK
    if a.job == "datenvorlage":
        if not a.input or a.input not in datakinds.IDS:
            print("passermark-cli datenvorlage <" + "|".join(datakinds.IDS) + "> [datei.csv]", file=sys.stderr)
            return EXIT_USAGE
        cols = datakinds.columns(a.input)
        if a.output:
            datakinds.write_csv(a.output, cols, [datakinds.example_row(a.input)])
            print(a.output)
        else:
            import csv as _csv
            w = _csv.writer(sys.stdout, delimiter=";", lineterminator="\n")
            w.writerow(cols)
            ex = datakinds.example_row(a.input)
            w.writerow([ex.get(c, "") for c in cols])
        return EXIT_OK
    # datencheck <datei.csv> [art]
    if not a.input or not os.path.isfile(a.input):
        print("passermark-cli datencheck <datei.csv> [art]", file=sys.stderr)
        return EXIT_USAGE
    try:
        cols, rows = vdp.read_csv(a.input)
        kind = a.output or datakinds.guess_kind(cols)
        probs = datakinds.validate(kind, cols, rows)
    except (OSError, ValueError, UnicodeDecodeError) as e:
        print(tr("Fehler: {0}").format(e), file=sys.stderr)
        return EXIT_ERROR
    print(tr("{0}: {1} Datensätze, Art {2}").format(a.input, len(rows), kind))
    for r, col, msg in probs:
        where = tr("Zeile {0}").format(r + 2) if r >= 0 else tr("Tabelle")      # +2: header line, counted from 1
        print(f"  {where}{' · ' + col if col else ''}: {msg}")
    if not probs:
        print("  " + tr("Alles in Ordnung"))
    return EXIT_ERROR if probs else EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    from .l10n import tr
    p = argparse.ArgumentParser(prog="passermark-cli", description=tr("Passermark – Aufträge ohne Oberfläche"))
    p.add_argument("job", help=tr("Auftrag (z. B. cutcontour) oder: list, settings, presets, beispiele, datenarten, datenvorlage, "
                           "datencheck"))
    p.add_argument("input", nargs="?", help=tr("Eingabe-PDF (bei 'settings': Auftrag)"))
    p.add_argument("output", nargs="?", help=tr("Ausgabe-PDF"))
    p.add_argument("--preset", help=tr("Einstellungen: JSON-Datei oder Name eines im Programm gespeicherten Presets"))
    p.add_argument("--set", action="append", default=[], metavar=tr("SCHLÜSSEL=WERT"),
                   help=tr("einzelne Einstellung, auch verschachtelt (detect.tolerance=40); mehrfach möglich"))
    p.add_argument("--pages", help=tr("nur diese Seiten, z. B. 1,3-5"))
    p.add_argument("--json-progress", action="store_true", help=tr("Fortschritt und Ergebnis als JSON-Zeilen"))
    p.add_argument("--quiet", action="store_true", help=tr("keine Fortschrittsanzeige"))
    return p


def main(argv: list[str] | None = None) -> int:
    import faulthandler
    faulthandler.enable()                   # hard crash -> output to stderr (ends up in the GUI log)
    if argv is None:
        argv = sys.argv[1:]
    if argv[:1] == ["render-server"]:       # intern: Render-Prozess der Seitenansicht (kein Auftrag)
        from .renderproc import main as render_main
        return render_main()
    from . import core
    from .l10n import tr
    parser = build_parser()
    try:
        a = parser.parse_args(argv)
    except SystemExit as e:
        return EXIT_USAGE if e.code else EXIT_OK

    if a.job == "list":
        for kind in core.JOBS:
            print(kind)
        return EXIT_OK
    if a.job == "settings":
        if not a.input:
            print("passermark-cli settings <auftrag>", file=sys.stderr)
            return EXIT_USAGE
        try:
            cls = core.settings_class(a.input)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return EXIT_USAGE
        print(json.dumps({"job": a.input, "settings": core.settings_to_dict(cls())}, ensure_ascii=False, indent=2))
        return EXIT_OK

    if a.job in ("datenarten", "datenvorlage", "datencheck"):
        return _data_cmd(a)

    if a.job == "beispiele":
        from . import examples
        try:
            d = examples.install(a.input)
        except OSError as e:
            print(tr("Fehler: {0}").format(e), file=sys.stderr)
            return EXIT_ERROR
        print(d)
        print("  " + tr("Presets: {0}").format(", ".join(n for _, n in examples.EXAMPLES)))
        print("  passermark-cli vdp \"{0}\" aus.pdf --preset \"{1}\"".format(
            os.path.join(d, "vorlage-a6.pdf"), examples.EXAMPLES[-1][1]))
        return EXIT_OK

    if a.job == "presets":
        from . import presets
        kinds = [a.input] if a.input else list(core.JOBS)
        for kind in kinds:
            try:
                names = presets.list_presets(kind)
            except ValueError as e:
                print(str(e), file=sys.stderr)
                return EXIT_USAGE
            for n in names:
                print(f"{kind}\t{n}" if not a.input else n)
        return EXIT_OK

    rep = _Reporter(a.json_progress, a.quiet)

    def fail(msg, code, raw=None):
        rep.finish_line()
        if a.json_progress:                     # for programs without an "Error:" prefix (the window is already titled that way)
            rep.emit(event="cancelled" if code == EXIT_CANCELLED else "error", message=raw or msg)
        else:
            print(msg, file=sys.stderr)
        return code

    if a.job not in core.JOBS:
        return fail(tr("Unbekannter Auftrag: {0}").format(a.job) + " (passermark-cli list)", EXIT_USAGE)
    if not a.input or not a.output:
        return fail(tr("Eingabe und Ausgabe angeben:") + " passermark-cli <job> <input.pdf> <output.pdf>", EXIT_USAGE)
    if not os.path.isfile(a.input):
        return fail(tr("Eingabe nicht gefunden: {0}").format(a.input), EXIT_ERROR)
    try:
        settings = {}
        if a.preset:
            from . import presets
            ppath = presets.resolve(a.job, a.preset)
            kind, settings = core.load_settings(ppath)
            if kind != a.job:
                return fail(tr("Preset ist für „{0}“, nicht für „{1}“").format(kind, a.job), EXIT_USAGE)
            _rebase_paths(settings, os.path.dirname(os.path.abspath(ppath)))
        apply_sets(settings, a.set)
        pages = parse_pages(a.pages)
    except (OSError, ValueError, KeyError) as e:
        return fail(tr("Falsche Angabe: {0}").format(e), EXIT_USAGE)

    # cancel: Ctrl+C (KeyboardInterrupt) or SIGTERM (GUI) -> clean, without a half-written file
    stop = {"flag": False}

    def on_term(_sig, _frm):
        stop["flag"] = True
    try:
        signal.signal(signal.SIGTERM, on_term)
    except (ValueError, AttributeError, OSError):
        pass
    try:
        r = core.run_job(a.job, a.input, a.output, settings, {"pages": pages} if pages else None,
                         progress=rep.progress, cancel=lambda: stop["flag"])
    except (core.Cancelled, KeyboardInterrupt):
        for p in (a.output + ".part", a.output + ".part.pdf"):
            if os.path.exists(p):
                os.remove(p)
        return fail(tr("Abgebrochen."), EXIT_CANCELLED)
    except Exception as e:                                  # noqa: BLE001 – jede Ursache melden
        return fail(tr("Fehler: {0}").format(e), EXIT_ERROR, raw=str(e))
    rep.finish_line()
    if a.json_progress:
        rep.emit(event="done", output=r.output, info=r.info, notes=r.notes)
    elif not a.quiet:
        info = ", ".join(f"{k}: {v}" for k, v in r.info.items())
        print(f"{r.output}" + (f"  ({info})" if info else ""))
        for n in r.notes:
            print("  " + tr("Hinweis: {0}").format(n))
    return EXIT_OK


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    sys.exit(main())
