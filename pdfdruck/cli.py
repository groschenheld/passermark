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

Interface for other programs (see docs/cli-api.md; never import Passermark code, only call the command line):
    passermark-cli version --json                            (program version, interface version, jobs)
    passermark-cli schema [auftrag]                          (JSON Schema: workflow file or one job's settings)
    passermark-cli check ablauf.json [--in …] [--var k=v]   (check a workflow without running it)
    passermark-cli run ablauf.json [ausgabe.pdf] [--in datei …] [--var k=v] [--json]
    passermark-cli run <Name> --in datei.pdf                 (workflow from the workflow folders, by name)
    passermark-cli workflows [--dirs] [--json]               (list workflows in the workflow folders)
    passermark-cli inspect datei.pdf [--check] [--json]      (pages, formats, trim/bleed, check results)
    passermark-cli printers [--json]                         (printers with status)
    passermark-cli caps <drucker> [--json]                   (driver options, trays, paper sizes, finishers)
    passermark-cli serve [--config watch.json] [--once] [--check] [--json]   (drop folders -> workflows)
    passermark-cli serve --init [--system]                   (template watch.json, never overwrites)
    passermark-cli tidy datei.json [--full] [--out neu.json] [--print]   (preset/workflow: only what differs)
    passermark-cli reprint protokoll.json [--in datei.pdf] [--dry-run]   (print a logged job again, exactly)

Return value: 0 = ok, 1 = error, 2 = wrong invocation / invalid workflow, 130 = cancelled (Ctrl+C).
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
    p = argparse.ArgumentParser(prog="passermark-cli", description=tr("Passermark – Aufträge ohne Oberfläche"),
                                epilog=tr("Abläufe und Schnittstelle für andere Programme: version, schema, check, run, "
                                          "inspect – z. B. passermark-cli run --help")
                                + " · printers, caps, workflows")
    p.add_argument("job", help=tr("Auftrag (z. B. cutcontour) oder: list, settings, presets, beispiele, datenarten, datenvorlage, "
                           "datencheck"))
    p.add_argument("input", nargs="?", help=tr("Eingabe-PDF (bei 'settings': Auftrag)"))
    p.add_argument("output", nargs="?", help=tr("Ausgabe-PDF"))
    p.add_argument("--preset", help=tr("Einstellungen: JSON-Datei oder Name eines im Programm gespeicherten Presets"))
    p.add_argument("--set", action="append", default=[], metavar=tr("SCHLÜSSEL=WERT"),
                   help=tr("einzelne Einstellung, auch verschachtelt (detect.tolerance=40); mehrfach möglich"))
    p.add_argument("--pages", help=tr("nur diese Seiten, z. B. 1,3-5"))
    p.add_argument("--json-progress", "--json", dest="json_progress", action="store_true",
                   help=tr("Fortschritt und Ergebnis als JSON-Zeilen"))
    p.add_argument("--quiet", action="store_true", help=tr("keine Fortschrittsanzeige"))
    return p


def _safe_streams():
    """Windows-Konsole/Pipe mit Codepage 1252/850: Zeichen wie „→“ oder „ΔE“ ließen den ganzen Auftrag abstürzen
    (UnicodeEncodeError). Nicht darstellbare Zeichen werden jetzt ersetzt statt den Auftrag abzubrechen."""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError, OSError):
            pass


def main(argv: list[str] | None = None) -> int:
    import faulthandler
    faulthandler.enable()                   # hard crash -> output to stderr (ends up in the GUI log)
    if argv is None:
        argv = sys.argv[1:]
    if argv[:1] == ["render-server"]:       # intern: Render-Prozess der Seitenansicht (kein Auftrag)
        from .renderproc import main as render_main
        return render_main()
    _safe_streams()
    if argv[:1] and argv[0] in API_COMMANDS:
        return api_main(argv[0], argv[1:])
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
        if a.job.lower().endswith(".json"):
            return fail(tr("„{0}“ ist kein Auftrag. Ablauf ausführen mit: passermark-cli run {0} --in <datei.pdf>")
                        .format(a.job), EXIT_USAGE)
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


# --------------------------------------------------------------------------- #
# interface for other programs: version, schema, check, run, inspect
# --------------------------------------------------------------------------- #
API_COMMANDS = ("version", "schema", "check", "run", "inspect", "printers", "caps", "workflows", "serve", "tidy",
                "reprint", "plan", "rolls", "probe")


def _api_parser(cmd: str) -> argparse.ArgumentParser:
    from .l10n import tr
    p = argparse.ArgumentParser(prog=f"passermark-cli {cmd}")
    if cmd == "schema":
        p.add_argument("job", nargs="?", help=tr("nur die Einstellungen dieses Auftrags"))
    elif cmd in ("check", "run"):
        p.add_argument("workflow", help=tr("Ablauf: Name aus den Ablauf-Ordnern oder JSON-Datei"))
        if cmd == "run":
            p.add_argument("output", nargs="?", help=tr("Ausgabe-PDF (statt der im Ablauf)"))
        else:
            p.add_argument("--out", dest="output", help=tr("Ausgabe-PDF (statt der im Ablauf)"))
        p.add_argument("--in", dest="inputs", action="append", default=[], metavar=tr("DATEI"),
                       help=tr("Eingabedatei (statt der im Ablauf); mehrfach = zusammenführen"))
        p.add_argument("--var", action="append", default=[], metavar=tr("NAME=WERT"),
                       help=tr("Variable ${NAME} im Ablauf setzen; mehrfach möglich"))
        p.add_argument("--quiet", action="store_true", help=tr("keine Fortschrittsanzeige"))
    elif cmd == "workflows":
        p.add_argument("--dirs", action="store_true", help=tr("nur die Ablauf-Ordner anzeigen"))
    elif cmd == "reprint":
        p.add_argument("log", help=tr("Druckprotokoll (JSON aus dem Protokoll-Ordner)"))
        p.add_argument("--in", dest="inputs", action="append", default=[], metavar=tr("DATEI"),
                       help=tr("andere Eingabedatei statt der protokollierten"))
        p.add_argument("--dry-run", action="store_true", help=tr("nichts senden – nur anzeigen, was gedruckt würde"))
        p.add_argument("--quiet", action="store_true", help=tr("keine Fortschrittsanzeige"))
    elif cmd == "tidy":
        p.add_argument("file", help=tr("Preset- oder Ablauf-Datei (JSON)"))
        p.add_argument("--full", action="store_true", help=tr("Preset mit allen Einstellungen schreiben"))
        p.add_argument("--out", help=tr("in diese Datei schreiben (sonst wird die Datei selbst ersetzt)"))
        p.add_argument("--print", dest="show", action="store_true", help=tr("nur anzeigen, nichts schreiben"))
    elif cmd == "serve":
        p.add_argument("--config", help=tr("Watcher-Einstellung (watch.json); ohne: eigene, dann die für alle"))
        p.add_argument("--once", action="store_true", help=tr("vorhandene Dateien verarbeiten und beenden"))
        p.add_argument("--check", action="store_true", help=tr("nur prüfen (Ordner und Abläufe), nichts verarbeiten"))
        p.add_argument("--init", action="store_true", help=tr("Vorlage watch.json anlegen (überschreibt nie)"))
        p.add_argument("--system", action="store_true", help=tr("mit --init: die für alle Benutzer (Administrator)"))
        p.add_argument("--quiet", action="store_true", help=tr("nur Fehler ausgeben"))
        p.add_argument("--log", metavar=tr("DATEI"), help=tr("Meldungen zusätzlich an diese Datei anhängen "
                                                            "(z. B. als Windows-Aufgabe ohne Konsole)"))
    elif cmd == "caps":
        p.add_argument("printer", help=tr("Druckername (wie bei passermark-cli printers)"))
    elif cmd == "rolls":
        p.add_argument("printer", help=tr("Druckername (wie bei passermark-cli printers)"))
        p.add_argument("--host", help=tr("Geräteadresse (statt der eingestellten bzw. aus der Warteschlange)"))
    elif cmd == "probe":
        p.add_argument("target", help=tr("Druckername oder Geräteadresse (IP)"))
        p.add_argument("--host", help=tr("Geräteadresse (statt der eingestellten bzw. aus der Warteschlange)"))
        p.add_argument("--community", default="", help=tr("SNMP-Community (Standard: public)"))
        p.add_argument("--out", metavar=tr("DATEI"), help=tr("vollständigen Bericht als JSON speichern"))
    elif cmd == "plan":
        p.add_argument("files", nargs="+", metavar=tr("DATEI"), help=tr("Pläne (PDF, jede Seite ein Plan; oder Bilder)"))
        p.add_argument("--printer", default="", help=tr("Drucker (leer = Standarddrucker)"))
        p.add_argument("--kind", default="plan", choices=["plan", "poster"],
                       help=tr("plan = Produktionsdruck, poster = Qualitätsdruck (nebeneinander, Überbreite "
                               "abschneiden)"))
        p.add_argument("--material", default="", help=tr("Druckmaterial (Name oder ID aus dem Programm)"))
        p.add_argument("--plt", metavar=tr("DATEI"),
                       help=tr("zusätzlich Schneidedatei (HP-GL/CAMM-GL) mit den Schnittkanten eines Satzes"))
        p.add_argument("--rolls", default="", metavar="594,841,914",
                       help=tr("Rollenbreiten in mm (statt der vom Gerät gemeldeten)"))
        p.add_argument("--copies", type=int, default=1, help=tr("Exemplare"))
        p.add_argument("--collate", action="store_true", help=tr("sortiert (Satz für Satz) statt jeder Plan n-mal"))
        p.add_argument("--by-roll", action="store_true", help=tr("nach Rollenbreite drucken statt in Listenreihenfolge"))
        p.add_argument("--color", default="", help=tr("color | gray (leer = wie im Treiber)"))
        p.add_argument("--frame", default="auto", choices=["auto", "frame", "margin", "none"],
                       help=tr("Druckbereich: auto, frame (zwei Außenlinien), margin (Inhalt + Rand), none (Seite)"))
        p.add_argument("--margin", type=float, default=5.0, help=tr("Rand in mm ohne zwei Außenlinien"))
        p.add_argument("--rotate", default="auto", choices=["auto", "keep", "short", "long"],
                       help=tr("auto = kürzeste Länge auf der Rolle"))
        p.add_argument("--pages", default="", help=tr("Seiten, z. B. 1,3-5 (nur bei einer Datei)"))
        p.add_argument("--set", action="append", default=[], metavar=tr("SCHLÜSSEL=WERT"),
                       help=tr("weitere Plan-Einstellung (passermark-cli schema plan)"))
        p.add_argument("--dry-run", action="store_true", help=tr("nichts senden – nur Laufmeter und Rollen anzeigen"))
        p.add_argument("--quiet", action="store_true", help=tr("keine Fortschrittsanzeige"))
    elif cmd == "inspect":
        p.add_argument("file", help=tr("PDF (oder Bild/Office-Datei)"))
        p.add_argument("--check", action="store_true", help=tr("zusätzlich prüfen (Schriften, Ebenen, Bilder …)"))
        p.add_argument("--password", help=tr("Passwort"))
    p.add_argument("--json", action="store_true", help=tr("Ausgabe als JSON"))
    return p


def tidy_data(data: dict, full: bool = False) -> dict:
    """Preset ({"job", "settings"}) oder Ablauf ({"passermark": "workflow"}) auf das Nötige kürzen: nur, was vom
        Standard abweicht. Unverändert bleiben Schritte mit "preset" (dort kann ein Standardwert das Preset
        absichtlich überschreiben) und "layout" im Druckschritt (fehlende Werte kommen dort aus der
        Admin-Einstellung). full=True: Preset mit allen Einstellungen (nur für Presets)."""
    import copy
    from . import core, workflow
    from .l10n import tr
    data = copy.deepcopy(data)
    if isinstance(data.get("job"), str) and isinstance(data.get("settings", {}), dict):
        cls = core.settings_class(data["job"])
        s = data.get("settings") or {}
        data["settings"] = (core.settings_to_dict(core.settings_from_dict(cls, s)) if full
                            else core.compact_settings(cls, s))
        return data
    if data.get("passermark") != workflow.KIND:
        raise ValueError(tr("Weder Preset noch Ablauf."))
    if full:
        raise ValueError(tr("--full gibt es nur für Presets – im Ablauf steht immer nur, was abweicht."))
    def flat(steps):                                  # auch Schritte in Verzweigungen („choose“)
        for st in steps or []:
            if isinstance(st, dict) and isinstance(st.get(workflow.CHOOSE), list):
                for br in st[workflow.CHOOSE]:
                    if isinstance(br, dict):
                        yield from flat(br.get("steps") or br.get("else"))
            else:
                yield st
    for st in flat(data.get("steps")):
        if not isinstance(st, dict) or "preset" in st or not isinstance(st.get("settings"), dict) \
                or st.get("job") in workflow.FLOW:
            continue
        cls = workflow.step_settings_class(st.get("job", ""))
        sett = core.compact_settings(cls, st["settings"])
        if st.get("job") == workflow.PRINT and "layout" in st["settings"]:
            sett["layout"] = st["settings"]["layout"]    # Druck: fehlende Werte kommen aus der Admin-Einstellung,
            #                                              nicht vom Programmstandard – darum ganz lassen
        if sett:
            st["settings"] = sett
        else:
            st.pop("settings")
    return data


def _tidy(a, rep, fail) -> int:
    from . import workflow
    from .l10n import tr
    try:
        with open(a.file, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError(tr("Objekt erwartet"))
        new = tidy_data(data, a.full)
    except FileNotFoundError as e:
        return fail(workflow.E_NOT_FOUND, tr("Datei nicht gefunden: {0}").format(e.filename), EXIT_ERROR)
    except (OSError, ValueError) as e:
        return fail(workflow.E_INVALID, tr("Falsche Angabe: {0}").format(e), EXIT_USAGE)

    def count(d):
        return sum(count(v) if isinstance(v, dict) else 1 for v in d.values())
    before, after = count(data), count(new)
    text = json.dumps(new, ensure_ascii=False, indent=2) + "\n"
    if a.show:
        sys.stdout.write(text)
        return EXIT_OK
    dst = a.out or a.file
    tmp = dst + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, dst)
    if a.json:
        rep.emit(event="done", output=os.path.abspath(dst), entries_before=before, entries_after=after)
    else:
        print(tr("{0}: {1} → {2} Einträge").format(dst, before, after))
    return EXIT_OK


def _serve(a, rep, fail) -> int:
    """passermark-cli serve: Drop-Ordner überwachen (pdfdruck/watch.py)."""
    import time
    from . import core, watch, workflow
    from .l10n import tr
    if a.init:
        try:
            path, new, made = watch.init_config(a.system)
        except OSError as e:
            return fail(workflow.E_FAILED, tr("Anlegen nicht möglich: {0}").format(e), EXIT_ERROR)
        if a.json:
            rep.emit(event="init", config=path, created=new, files=made)
        elif new:
            print(tr("Vorlage angelegt: {0}").format(path))
            for m in made[1:]:
                print("  + " + m)
            print(tr("Anpassen, dann prüfen: passermark-cli serve --check"))
        else:
            print(tr("Gibt es schon – nichts geändert: {0}").format(path))
        return EXIT_OK
    try:
        path = watch.find_config(a.config)
        cfg = watch.load_config(path)
    except FileNotFoundError as e:
        return fail(workflow.E_NOT_FOUND, str(e), EXIT_USAGE)
    except watch.WatchError as e:
        return fail(workflow.E_INVALID, tr("Watcher-Einstellung ungültig ({0} Problem(e))").format(len(e.problems)),
                    EXIT_USAGE, problems=[{"where": w, "message": m} for w, m in e.problems])
    if a.check:
        probs = watch.check(cfg)
        if probs:
            return fail(workflow.E_INVALID, tr("Watcher-Einstellung ungültig ({0} Problem(e))").format(len(probs)),
                        EXIT_USAGE, problems=[{"where": w, "message": m} for w, m in probs])
        if a.json:
            rep.emit(event="ok", config=path, folders=[{"name": f["name"], "in": f["in"], "workflow": f["workflow"]}
                                                      for f in cfg["folders"]])
        else:
            print(tr("Watcher-Einstellung in Ordnung: {0} Ordner").format(len(cfg["folders"])))
            for f in cfg["folders"]:
                print(f"  {f['in']}  →  {f['workflow']}")
        return EXIT_OK
    stop = {"flag": False}

    def on_term(_sig, _frm):
        stop["flag"] = True
    try:
        signal.signal(signal.SIGTERM, on_term)
    except (ValueError, AttributeError, OSError):
        pass

    logf = None
    if a.log:
        try:
            logf = open(a.log, "a", encoding="utf-8")
        except OSError as e:
            return fail(workflow.E_USAGE, tr("Falsche Angabe: {0}").format(e), EXIT_USAGE)

    def to_log(line):
        if logf is not None:
            try:
                logf.write(line + "\n")
                logf.flush()
            except OSError:
                pass

    def say(text, err=False):
        line = time.strftime("%Y-%m-%d %H:%M:%S") + "  " + text
        to_log(line)
        if a.quiet and not err:
            return
        try:
            print(line, file=sys.stderr if err else sys.stdout, flush=True)
        except (OSError, ValueError, AttributeError):        # Windows-Aufgabe ohne Konsole
            pass

    def events(ev):
        if a.json:
            if ev["event"] != "progress":
                rep.emit(**ev)
                to_log(json.dumps(ev, ensure_ascii=False))
            return
        e = ev["event"]
        if e == "watch_start":
            say(tr("Watcher läuft: {0} Ordner ({1})").format(len(ev["folders"]), ev["config"]))
            for f in ev["folders"]:
                say(f"  {f['in']}  →  {f['workflow']}")
            if ev["recovered"]:
                say(tr("{0} unterbrochene Datei(en) zurück in den Eingang gelegt").format(ev["recovered"]))
        elif e == "file":
            say("{0}: {1} → {2}".format(ev["folder"], os.path.basename(ev["file"]),
                                            os.path.basename(ev["workflow"])))
        elif e == "file_done":
            parts = []
            for pr in ev["prints"]:
                parts.append(tr("Probelauf auf {0}").format(pr["printer"]) if pr["dry_run"] else
                             tr("gedruckt auf {0} (Auftrag {1})").format(pr["printer"], pr["job_id"]))
            if ev["output"]:
                parts.append(ev["output"])
            say("  " + tr("fertig in {0} s").format(ev["seconds"]) + (": " + ", ".join(parts) if parts else ""))
            for n in ev["notes"]:
                say("    " + tr("Hinweis: {0}").format(n))
        elif e == "file_failed":
            say("  " + tr("Fehler: {0}").format(ev["message"]) + "  → " + ev["moved_to"], err=True)
            for pr in ev["problems"]:
                say(f"    {pr['where'] or '–'}: {pr['message']}", err=True)
    w = watch.Watcher(cfg, events, cancel=lambda: stop["flag"])
    try:
        counts = w.run(once=a.once)
    except (core.Cancelled, KeyboardInterrupt):
        counts = w.counts
    if a.json:
        rep.emit(event="stopped", **counts)
    else:
        say(tr("Beendet: {0} verarbeitet, {1} mit Fehler").format(counts["done"], counts["failed"]))
    if logf is not None:
        logf.close()
    return EXIT_ERROR if a.once and counts["failed"] else EXIT_OK


def _vars(items) -> dict:
    out = {}
    for it in items or []:
        if "=" not in it:
            raise ValueError(it)
        k, v = it.split("=", 1)
        out[k.strip()] = v
    return out


def api_main(cmd: str, argv: list[str]) -> int:
    from . import __version__, core, workflow
    from .l10n import tr
    try:
        a = _api_parser(cmd).parse_args(argv)
    except SystemExit as e:
        return EXIT_USAGE if e.code else EXIT_OK
    rep = _Reporter(a.json, getattr(a, "quiet", False))

    def fail(code: str, msg: str, exit_code: int, **extra):
        rep.finish_line()
        if a.json:
            rep.emit(event="cancelled" if code == workflow.E_CANCELLED else "error", code=code, message=msg, **extra)
        else:
            print(msg, file=sys.stderr)
            for pr in extra.get("problems", []):
                print(f"  {pr['where'] or '–'}: {pr['message']}", file=sys.stderr)
        return exit_code

    if cmd == "version":
        from . import conditions
        d = {"passermark": __version__, "api": workflow.API, "workflow_version": workflow.VERSION,
             "jobs": workflow.step_jobs(), "flow": [workflow.CHOOSE, *workflow.FLOW],
             "conditions": {"facts": {k: {"type": t, "description": desc} for k, (t, desc) in
                                      conditions.FACTS.items()},
                            "operators": list(conditions.OPS), "logic": list(conditions.LOGIC),
                            "variables": conditions.VAR_PREFIX + "NAME"}}
        print(json.dumps(d, ensure_ascii=False) if a.json else
              f"Passermark {__version__} (API {workflow.API}, {tr('Ablauf-Format')} {workflow.VERSION})")
        return EXIT_OK

    if cmd == "schema":
        if a.job:
            try:
                d = workflow.settings_schema(workflow.step_settings_class(a.job))
            except ValueError as e:
                return fail(workflow.E_USAGE, str(e), EXIT_USAGE)
        else:
            d = workflow.schema()
        print(json.dumps(d, ensure_ascii=False, indent=None if a.json else 2))
        return EXIT_OK

    if cmd in ("printers", "caps"):
        from . import printcli
        try:
            d = printcli.printers_info() if cmd == "printers" else printcli.caps_info(a.printer)
        except Exception as e:                                  # noqa: BLE001 – z. B. CUPS nicht erreichbar
            return fail(workflow.E_FAILED, tr("Drucker nicht abfragbar: {0}").format(e), EXIT_ERROR)
        if a.json:
            print(json.dumps(d, ensure_ascii=False))
        elif cmd == "printers":
            for pr in d:
                print(("* " if pr["default"] else "  ") + f"{pr['name']}\t{pr['state_text']}\t{pr['model']}")
        else:
            print(f"{d['name']} ({d['backend']})")
            for role, key in d["roles"].items():
                o = next((x for x in d["options"] if x["keyword"] == key), None)
                if o:
                    print(f"  {role} = {key}: " + ", ".join(c["value"] for c in o["choices"][:12])
                          + (" …" if len(o["choices"]) > 12 else ""))
            fin = [o for o in d["options"] if o.get("finishing")]
            if fin:
                print("  " + tr("Endverarbeitung:"))
                for o in fin:
                    ch = [c["value"] + ("" if c.get("available", True) else " (" + tr("nicht installiert") + ")")
                          for c in o["choices"]]
                    print(f"    {o['keyword']} ({o['text']}): " + ", ".join(ch))
            if d["installed_hardware"]:
                print("  " + tr("Installierte Hardware:") + " " + ", ".join(
                    f"{k}={v}" for k, v in d["installed_hardware"].items()))
            if d["finisher_presets"]:
                print("  " + tr("Finisher-Vorlagen:") + " " + ", ".join(p["name"] for p in d["finisher_presets"]))
            if d["driver_dialog"]:
                print("  " + tr("Herstellerfunktionen (Windows): in der Verwaltung als Finisher-Vorlage über den "
                                "Herstellerdialog anlegen, im Ablauf mit finisher_preset wählen."))
            print("  " + tr("{0} Treiberoptionen insgesamt (--json zeigt alle)").format(len(d["options"])))
        return EXIT_OK

    if cmd == "rolls":
        from . import rolls as rl
        from .session import Session
        from . import config
        try:
            sess = Session(config.load())
            if a.host:
                q = rl.query(a.host, force=True)
                st = rl.RollState([rl.Roll.from_dict(r.to_dict()) for r in q.rolls], q.origin, q.error, q.host)
                caps = sess.caps_for(a.printer)
                for i, r in enumerate(st.rolls):
                    r.slot = r.slot or rl.slot_for(caps, r.device or r.name, i)
            else:
                st = rl.for_printer(sess, a.printer, live=True, force=True)
        except Exception as e:                                  # noqa: BLE001
            return fail(workflow.E_FAILED, tr("Drucker nicht abfragbar: {0}").format(e), EXIT_ERROR)
        d = {"printer": a.printer, "host": st.host, "origin": st.origin, "error": st.error,
             "rolls": [dict(r.to_dict(), label=r.label()) for r in st.rolls]}
        if a.json:
            print(json.dumps(d, ensure_ascii=False))
        else:
            print(f"{a.printer} ({st.host or '–'}, {st.origin})")
            for r in st.rolls:
                print("  " + r.label() + (f"  → {r.slot}" if r.slot else ""))
            if not st.rolls:
                print("  " + tr("Keine Rollen bekannt") + (f" – {st.error}" if st.error else ""))
        return EXIT_OK

    if cmd == "plan":
        return _plan_cmd(a, rep, fail)

    if cmd == "probe":
        import re as _re
        from . import probe, rolls as rl
        from .session import Session
        from . import config
        host, printer = a.host or "", ""
        if not host:
            if _re.fullmatch(r"[\w.\-]+", a.target) and ("." in a.target or ":" in a.target) \
                    and not _is_printer(a.target):
                host = a.target
            else:
                printer = a.target
                host = rl.host_for(Session(config.load()), printer)
        else:
            printer = a.target
        d = probe.run(host, printer, a.community, progress=None if a.json else (lambda t: None))
        if a.out:
            probe.save(d, a.out)
        if a.json:
            print(json.dumps(d, ensure_ascii=False))
        else:
            print(probe.text(d), end="")
            if a.out:
                print(tr("Bericht: {0}").format(os.path.abspath(a.out)))
        return EXIT_OK

    if cmd == "inspect":
        from . import docinfo
        try:
            d = docinfo.inspect(a.file, a.password, a.check)
        except FileNotFoundError as e:
            return fail(workflow.E_NOT_FOUND, str(e), EXIT_ERROR)
        except Exception as e:                                  # noqa: BLE001 – jede Ursache melden
            return fail(workflow.E_FAILED, str(e), EXIT_ERROR)
        print(json.dumps(d, ensure_ascii=False) if a.json else docinfo.text_summary(d))
        return EXIT_OK

    if cmd == "workflows":
        if a.dirs:
            d = [{"source": src, "folder": f, "exists": os.path.isdir(f)} for src, f in workflow.folders()]
            if a.json:
                print(json.dumps(d, ensure_ascii=False))
            else:
                for x in d:
                    print(f"{x['source']:<7} " + x["folder"]
                          + ("" if x["exists"] else "  (" + tr("noch nicht angelegt") + ")"))
            return EXIT_OK
        d = workflow.list_workflows()
        if a.json:
            print(json.dumps(d, ensure_ascii=False))
        else:
            if not d:
                print(tr("Keine Abläufe in den Ablauf-Ordnern (passermark-cli workflows --dirs)."))
            for w in d:
                print(f"{w['name']}\t" + (tr("Fehler: {0}").format(w["error"]) if w["error"] else
                                         " → ".join(j or "?" for j in w["jobs"]))
                      + (f"\t{w['description']}" if w["description"] else ""))
        return EXIT_OK

    if cmd == "serve":
        return _serve(a, rep, fail)
    if cmd == "tidy":
        return _tidy(a, rep, fail)

    # check / run / reprint
    notes0 = []
    try:
        if cmd == "reprint":                   # Druckprotokoll: der gespeicherte Ablauf, genau wie damals
            from . import printlog
            rec = printlog.load(a.log)
            data = rec["workflow"]
            a.workflow, a.output, a.var = os.path.abspath(a.log), None, []
            if a.dry_run:
                for st in data.get("steps") or []:
                    if st.get("job") in workflow.PRINTS:
                        st.setdefault("settings", {})["dry_run"] = True
            old = rec["job"].get("file")
            if not a.inputs and old and rec["job"].get("file_sha256") and not rec["job"].get("files"):
                if not os.path.isfile(old):
                    raise FileNotFoundError(tr("Protokollierte Datei nicht mehr da: {0} – mit --in angeben.")
                                            .format(old))
                if printlog._sha256(old) != rec["job"]["file_sha256"]:
                    notes0.append(tr("Die Datei wurde seit dem Druck verändert: {0}").format(old))
        else:
            a.workflow = workflow.find(a.workflow)
            data = workflow.load(a.workflow)
        # Angaben auf der Kommandozeile gelten ab dem aktuellen Ordner, Pfade in der Datei ab deren Ordner
        ins = [os.path.abspath(x) for x in a.inputs] or None
        out = os.path.abspath(a.output) if a.output else None
        plan = workflow.prepare(data, os.path.dirname(os.path.abspath(a.workflow)), ins, out, _vars(a.var))
    except FileNotFoundError as e:
        return fail(workflow.E_NOT_FOUND, str(e), EXIT_USAGE)
    except workflow.WorkflowError as e:
        return fail(workflow.E_INVALID, tr("Ablauf ungültig ({0} Problem(e))").format(len(e.problems)), EXIT_USAGE,
                    problems=[{"where": w, "message": m} for w, m in e.problems])
    except (OSError, ValueError) as e:
        return fail(workflow.E_USAGE, tr("Falsche Angabe: {0}").format(e), EXIT_USAGE)

    if cmd == "check":
        d = {"ok": True, "name": plan.name, "inputs": plan.inputs, "output": plan.output,
             "steps": [st.to_dict() for st in plan.steps]}
        if a.json:
            print(json.dumps(d, ensure_ascii=False))
        else:
            print(tr("Ablauf in Ordnung: {0} Schritt(e)").format(len(plan.steps)))

            def show(steps, indent, num):
                for i, st in enumerate(steps, 1):
                    n = f"{num}{i}."
                    if st.job == workflow.CHOOSE:
                        print(f"{indent}{n} {tr('Verzweigung')}")
                        for c, sub in st.branches or []:
                            print(f"{indent}   " + (tr("wenn {0}").format(json.dumps(c, ensure_ascii=False))
                                                    if c is not None else tr("sonst")))
                            show(sub, indent + "      ", n)
                        continue
                    extra = f" – {st.name}" if st.name != st.job else ""
                    if st.message:
                        extra += f" „{st.message}“"
                    if st.cond is not None:
                        extra += "  " + tr("(nur wenn {0})").format(json.dumps(st.cond, ensure_ascii=False))
                    print(f"{indent}{n} {st.job}{extra}")
            show(plan.steps, "  ", "")
            print("  " + ", ".join(plan.inputs) + " → " + (plan.output or tr("(nur drucken)")))
        return EXIT_OK

    stop = {"flag": False}

    def on_term(_sig, _frm):
        stop["flag"] = True
    try:
        signal.signal(signal.SIGTERM, on_term)
    except (ValueError, AttributeError, OSError):
        pass
    cur = {"step": 0, "n": len(plan.steps), "job": ""}

    def events(ev):
        if ev["event"] == "step":
            cur.update(step=ev["step"], job=ev["job"], n=ev.get("steps") or cur["n"])
        if a.json:
            rep.emit(**ev)
            return
        if ev["event"] == "step":
            rep.finish_line()
            rep.last = ""
        elif ev["event"] in ("step_skipped", "branch", "stopped") and not a.quiet:
            rep.finish_line()
            rep.last = ""
            if ev["event"] == "step_skipped":
                print("  " + tr("übersprungen: {0} ({1}) – Bedingung nicht erfüllt").format(ev["job"], ev["where"]))
            elif ev["event"] == "branch":
                print("  " + (tr("Verzweigung {0}: Zweig „sonst“").format(ev["where"]) if ev["branch"] == "else" else
                              tr("Verzweigung {0}: Zweig {1}").format(ev["where"], ev["taken"] + 1)
                              if ev["taken"] is not None else tr("Verzweigung {0}: kein Zweig passt").format(ev["where"])))
            else:
                print("  " + tr("Beendet: {0}").format(ev["message"]))
        elif ev["event"] == "progress":
            rep.progress(ev["done"], ev["total"], f"{cur['step']}/{cur['n']} {cur['job']}  {ev.get('text', '')}")
    if a.json:
        rep.emit(event="start", api=workflow.API, version=__version__, steps=len(plan.steps), output=plan.output)
    try:
        r = workflow.run(plan, events, cancel=lambda: stop["flag"], variables=_vars(a.var))
        r["notes"] = notes0 + list(r.get("notes") or [])
    except (core.Cancelled, KeyboardInterrupt):
        return fail(workflow.E_CANCELLED, tr("Abgebrochen."), EXIT_CANCELLED, step=cur["step"])
    except workflow.Rejected as e:                              # „fail“-Schritt
        return fail(workflow.E_REJECTED, str(e), EXIT_ERROR, step=cur["step"])
    except Exception as e:                                      # noqa: BLE001 – jede Ursache melden
        return fail(workflow.E_FAILED, str(e), EXIT_ERROR, step=cur["step"], job=cur["job"])
    rep.finish_line()
    if a.json:
        rep.emit(event="done", **r)
    elif not a.quiet:
        for s in r["steps"]:                                    # Druckschritte: wohin und welcher Auftrag
            if s["job"] == workflow.PLAN:
                print(plan_text(s["info"] or {}))
                continue
            if s["job"] != workflow.PRINT:
                continue
            i = s["info"] or {}
            if i.get("dry_run"):
                print(tr("Probelauf – nichts gesendet: {0}, {1} Seite(n), Bogen {2:g} × {3:g} mm").format(
                    i.get("printer"), i.get("pages"), *(i.get("sheet_mm") or [0, 0])))
            else:
                print(tr("Gedruckt auf {0}: {1} Seite(n), Auftrag {2}").format(
                    i.get("printer"), i.get("pages"), i.get("job_id") if i.get("job_id") is not None else "–"))
        if r["output"]:
            print(r["output"] + ("  (" + tr("{0} Seite(n)").format(r["pages"]) + ")" if r["pages"] is not None else ""))
        for n in r["notes"]:
            print("  " + tr("Hinweis: {0}").format(n))
    return EXIT_OK


def _is_printer(name: str) -> bool:
    try:
        from . import printers
        return any(p.name == name for p in printers.list_printers())
    except Exception:
        return False


def plan_text(i: dict) -> str:
    """Laufmeter je Rolle als Text: „594 mm: 5,20 m · ×2 = 10,40 m“."""
    from .l10n import tr
    from .planprint import mm_text, num
    lines = []
    head = (tr("Probelauf – nichts gesendet") if i.get("dry_run") else
            tr("Gedruckt auf {0}: {1} Auftrag/Aufträge").format(i.get("printer"), len(i.get("jobs") or [])))
    lines.append(head)
    cp = int(i.get("copies") or 1)
    for d in i.get("lengths") or []:
        t = "  " + tr("{0} mm: {1} m").format(mm_text(d["width_mm"]), num(d["single_m"]))
        if cp > 1:
            t += " · ×{0} = ".format(cp) + tr("{0} m").format(num(d["total_m"]))
        t += "  (" + tr("{0} Plan/Pläne").format(d["plans"]) + ")"
        if d.get("short"):
            t += "  " + tr("– reicht laut Gerät nicht!")
        lines.append(t)
    if len(i.get("lengths") or []) > 1:
        t = "  " + tr("Gesamt: {0} m").format(num(i.get("single_m", 0)))
        if cp > 1:
            t += " · ×{0} = ".format(cp) + tr("{0} m").format(num(i.get("total_m", 0)))
        lines.append(t)
    return "\n".join(lines)


def _plan_cmd(a, rep, fail) -> int:
    from . import core, planprint, rolls as rl, workflow
    from .planprint import mm_text
    from .l10n import tr
    try:
        sett = dict(planprint.defaults_for(a.kind))
        sett.update({"printer": a.printer, "copies": max(1, a.copies), "collate": a.collate,
                     "order": "roll" if a.by_roll else "list", "color": a.color, "margin_mm": a.margin,
                     "rotate": a.rotate, "dry_run": a.dry_run, "material": a.material})
        if a.frame != "auto" or a.kind == "plan":
            sett["frame"] = a.frame
        if a.rolls:
            sett["rolls"] = [r.width_mm for r in rl.parse_widths(a.rolls)]
        apply_sets(sett, a.set)
        s = core.settings_from_dict(planprint.PlanSettings, sett)
        pages = parse_pages(a.pages) if a.pages else None
        for f in a.files:
            if not os.path.isfile(f):
                raise FileNotFoundError(tr("Eingabe nicht gefunden: {0}").format(f))
    except FileNotFoundError as e:
        return fail(workflow.E_NOT_FOUND, str(e), EXIT_USAGE)
    except (OSError, ValueError, KeyError) as e:
        return fail(workflow.E_USAGE, tr("Falsche Angabe: {0}").format(e), EXIT_USAGE)
    try:
        info = planprint.plan_files([os.path.abspath(f) for f in a.files], s, pages, progress=rep.progress,
                                    plt=os.path.abspath(a.plt) if a.plt else "")
    except Exception as e:                                      # noqa: BLE001 – jede Ursache melden
        return fail(workflow.E_FAILED, str(e), EXIT_ERROR)
    rep.finish_line()
    if a.json:
        rep.emit(event="done", **info)
    elif not a.quiet:
        print(plan_text(info))
        for p in info.get("plans") or []:
            if p.get("length_mm") is None:
                continue
            print("    " + tr("{0}: {1} × {2} mm → Rolle {3} mm{4}").format(
                p["plan"], mm_text(p["size_mm"][0]), mm_text(p["size_mm"][1]), mm_text(p["roll_mm"]),
                tr(", gedreht") if p.get("rotated") else ""))
        if info.get("cut_file"):
            print("  " + tr("Schneidedatei: {0} ({1} Schnitt(e))").format(info["cut_file"]["path"],
                                                                         info["cut_file"]["cuts"]))
        for n in info.get("notes") or []:
            print("  " + tr("Hinweis: {0}").format(n))
    return EXIT_OK


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    sys.exit(main())
