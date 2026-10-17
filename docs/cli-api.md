# Passermark command line – interface for other programs

**English** · [Deutsch](#deutsch)

Other programs (scripts, a watcher, shop or intranet connections, a graphical workflow editor) use Passermark
**only through the command line**: they start `passermark-cli`, hand over JSON and read JSON back. They never
import Passermark code. This keeps Passermark and such programs separate programs.

- Interface version: **API 1** (`passermark-cli version --json` → `"api": 1`)
- Workflow file format: **version 1** (`"workflow_version": 1`)

Compatible changes (new jobs, new settings, new fields in the output) do not change these numbers – ignore
fields you do not know. Incompatible changes raise the number.

Where the command is: Linux `install.sh` → `passermark-cli`; AppImage → `Passermark-*.AppImage --cli …`;
Windows → `passermark-cli.exe` in the installation folder.

## Commands

| Command | Purpose |
|---|---|
| `version --json` | program version, `api`, `workflow_version`, list of jobs |
| `schema [job] [--json]` | JSON Schema (draft 2020-12) of the workflow file, or of one job's settings |
| `check workflow.json [--in FILE …] [--out FILE] [--var NAME=VALUE …] [--json]` | check without running; shows the resolved steps |
| `run workflow.json [output.pdf] [--in FILE …] [--var NAME=VALUE …] [--json]` | run all steps |
| `run NAME …` | run a workflow from the workflow folders by its name (file name without `.json`) |
| `workflows [--dirs] [--json]` | list the workflows in the workflow folders (`--dirs`: the folders) |
| `inspect file.pdf [--check] [--password PW] [--json]` | pages, formats, trim and bleed; `--check`: check results |
| `printers [--json]` | printers with status (`default`, `state`, `model`) |
| `caps PRINTER [--json]` | the printer's driver options with all choices, which option serves which role, paper sizes |
| `<job> in.pdf out.pdf [--preset …] [--set k=v …] [--pages …] [--json]` | a single job (as before) |

Exit codes: `0` ok · `1` error while working / file not found · `2` wrong invocation or invalid workflow ·
`130` cancelled (Ctrl+C or SIGTERM – no half-written output is left behind).

## Workflow folders

Workflows can be called by name instead of by path: `passermark-cli run "Business cards" --in order.pdf`. Passermark
looks in two folders – the user's own first (a workflow there overrides one with the same name for everybody):

| | own | for all users (administrator) |
|---|---|---|
| Linux | `~/.config/passermark/ablaeufe/` | `/etc/passermark/ablaeufe/` |
| Windows | `%APPDATA%\Passermark\ablaeufe\` | `%ProgramData%\Passermark\ablaeufe\` |

`passermark-cli workflows` lists them, `--dirs` shows the folders. Relative paths inside a workflow (presets, CSV
files) are relative to its folder, so a workflow and its files can live there together. Paths given on the command
line (`--in`, output) are relative to the current folder.

## Workflow file

```json
{
  "passermark": "workflow",
  "version": 1,
  "name": "Business cards SRA3",
  "input": "${input}",
  "output": "${dir}/done/${stem}-sra3.pdf",
  "options": {"image_dpi": 96, "password": ""},
  "steps": [
    {"job": "preflight_fix", "settings": {"fix": "flatten_layers"}},
    {"job": "impose", "name": "Imposition", "preset": "Business cards",
     "settings": {"sheet": "SRA3", "step_repeat": true, "crop_marks": true, "bleed_mm": 3},
     "pages": "1-2"}
  ]
}
```

- `input`: one file or a list. Several files, images and Office documents are converted and merged into one PDF
  first (like *Merge* in the program). `--in` on the command line replaces it.
- `output`: the result. Written only when all steps succeeded (temporary file, then renamed). A second argument
  to `run` (or `--out` for `check`) replaces it. Missing folders are created. Optional when a step prints – then
  nothing is saved unless `output` is given.
- `steps`: run one after another; each step works on the result of the previous one. Without steps the input is
  only merged/converted.
  - `job`: see `passermark-cli version --json` → `jobs`.
  - `preset`: name of a preset saved in Passermark or a preset JSON file; `settings` are applied on top of it.
  - `settings`: only the keys you want to change – everything else keeps its default
    (`passermark-cli settings <job>` shows all defaults, `passermark-cli schema <job>` the types).
  - `pages`: only these pages, 1-based (`"1,3-5"`), where the job supports it.
- Variables `${name}`: from `--var name=value`, plus `${input}` (first input file), `${dir}` (its folder),
  `${stem}` (its name without extension), `${workflow_dir}`, `${date}` (YYYY-MM-DD). An unset variable is an
  error.
- Relative paths (input, output, preset files, `csv_path`) are relative to the workflow file.
- Unknown keys and wrong types are errors (a typo must not silently fall back to a default). `check` lists all
  problems at once.

## Printing (`"job": "print"`)

A `print` step sends the current PDF to a printer – the same way as the print dialog (imposition, the printer's
colour profile from the admin settings, automatic tray selection, Windows vendor settings). The PDF is not changed:
later steps continue with it, so a workflow can print and save, or print several times with different settings.

```json
{"job": "print", "pages": "1-8",
 "settings": {
   "printer": "Canon-C3822i",
   "paper": "A3", "tray": "Fach 2", "media": "Heavy 3", "duplex": "short", "color": "gray",
   "output_bin": "", "quality": "",
   "finishing": {"staple": "TopLeft", "punch": "4Holes"},
   "options": {"CNSaddleStitch": "True"},
   "finisher_preset": "Booklet stapled + folded",
   "copies": 3, "collate": true, "reverse": false, "subset": "all",
   "layout": {"handling": "booklet", "booklet_fold_marks": true},
   "profile": "admin", "intent": "", "auto_tray": true, "title": "Order 4711",
   "dry_run": false}}
```

- `printer`: as listed by `printers`; empty = default printer (admin setting, otherwise the system default).
- `paper`, `tray`, `media`, `duplex`, `color`, `quality`, `output_bin` and the finishers in `finishing`
  (`staple`, `punch`, `fold`, `saddle`, `trim`, `stacker`) address the driver option that serves this role
  (`caps` → `roles`). The value may be the driver value or its display text; a unique part of the text is enough
  ("links oben"). `duplex` also accepts `none | long | short`, `color` also `color | gray`. A value that matches
  nothing is an error that lists the available choices.
- `options`: driver options by keyword, for everything without a role.
- `finisher_preset`: a finisher template set up in Passermark's administration for this printer (driver
  options and, on Windows, the settings from the vendor's own driver dialog – every installed finisher the driver
  offers is reachable this way). A template marked "for booklets" switches to booklet handling unless `layout`
  says otherwise. Single settings above override the template.
- Installed hardware: values that the driver rejects for the installed hardware (PPD constraints, e.g. a punch
  unit that is not installed) are errors. `caps` marks them per choice with `"available": false`, lists the
  installed hardware (`installed_hardware`), all finishing options (`"finishing": true`) and the templates
  (`finisher_presets`).
- `layout`: page handling as in the print dialog (same keys as the `impose` job without `sheet`: `handling`
  size/multiple/booklet/poster, `nup`, `step_repeat`, `crop_marks`, `bleed_mm` …). The sheet is the selected paper.
- `profile`: `admin` (colour profile set up for this printer), `none`, or a profile id; `intent` overrides the
  rendering intent.
- `dry_run`: send nothing – the step only resolves everything and reports it (see below). Good for testing a
  workflow against a real printer.

Result (`step_done` → `info`): `{"printer": "…", "job_id": 4711, "pages": 8, "sheet_mm": [297.0, 420.0],
"options": {all driver options as sent}, "color_profile": "…", "dry_run": false}`.

On Windows the vendor-specific finishers live in the vendor's driver dialog, not in the option list: set them up
once as a finisher template (administration → printer → new finisher template → vendor dialog) and select it with
`finisher_preset`.

## JSON output (`--json`)

One JSON object per line on stdout (ASCII, non-ASCII characters escaped). Messages are in the program language
(`PASSERMARK_LANG=de|en|hu|es|fr`); for decisions use `event`, `code`, `severity`, `category` – they are stable.

`run`:

```
{"event": "start", "api": 1, "version": "1.14.0", "steps": 2, "output": "/…/out.pdf"}
{"event": "step", "step": 1, "steps": 2, "job": "impose", "name": "Imposition"}
{"event": "progress", "step": 1, "done": 0, "total": 1, "text": "…"}
{"event": "step_done", "step": 1, "job": "impose", "info": {"sheets": 2}, "notes": []}
…
{"event": "done", "output": "/…/out.pdf", "pages": 2,
 "steps": [{"step": 1, "job": "impose", "name": "Imposition", "info": {…}, "notes": […]}, …], "notes": […]}
```

Errors (all commands):

```
{"event": "error", "code": "invalid", "message": "…", "problems": [{"where": "steps[0].settings.sheett", "message": "…"}]}
{"event": "error", "code": "failed", "message": "…", "step": 2, "job": "preflight_fix"}
{"event": "cancelled", "code": "cancelled", "message": "…", "step": 1}
```

| `code` | meaning | exit code |
|---|---|---|
| `usage` | wrong invocation (unknown job, bad `--var`) | 2 |
| `not_found` | workflow or input file not found | 1 / 2 |
| `invalid` | workflow file invalid – details in `problems` | 2 |
| `failed` | a step failed – `step` and `job` say which | 1 |
| `cancelled` | cancelled | 130 |

`inspect --json`:

```
{"file": "/…/cards.pdf", "size_bytes": 2897, "encrypted": false, "pdf_version": "1.4", "metadata": {…},
 "pages": 4,
 "page_list": [{"page": 1, "width_mm": 91.0, "height_mm": 61.0, "orientation": "landscape", "rotate": 0,
                "trim_mm": [85.0, 55.0], "bleed_mm": 3.0,
                "boxes_pt": {"crop": […], "trim": […], "bleed": […], "art": null}}, …],
 "formats_mm": [{"size": "91 x 61", "pages": 4}],
 "check": {"counts": {"error": 0, "warning": 0, "info": 2},
           "issues": [{"severity": "info", "category": "font", "message": "…", "pages": [1, 2]}],
           "fonts": [{"name": "Helvetica", "subtype": "/Type1", "embedded": false, "subset": false, "pages": [1]}],
           "layers": [{"name": "…", "view": true, "print": null, "locked": false}]}}
```

Sizes in mm in reading direction (page rotation applied), boxes in pt as stored in the PDF, pages 1-based.
`trim_mm`/`bleed_mm` are `null` when the page defines no trim box (or it equals the page).

## Coming next

- `serve`: Passermark keeps running and accepts jobs as JSON lines (no start-up time per job).

---

## Deutsch

Andere Programme (Skripte, Watcher, Shop-/Intranet-Anbindung, eine grafische Ablauf-Oberfläche) nutzen Passermark
**nur über die Kommandozeile**: `passermark-cli` starten, JSON übergeben, JSON zurücklesen – nie Passermark-Code
importieren. So bleiben Passermark und diese Programme getrennte Programme.

Kurzfassung der Befehle:

```sh
passermark-cli version --json                       # Version, API-Version, Aufträge
passermark-cli schema                               # JSON-Schema der Ablauf-Datei
passermark-cli schema impose                        # Schema der Einstellungen eines Auftrags
passermark-cli check ablauf.json --var kunde=Muster # prüfen, ohne auszuführen (alle Probleme auf einmal)
passermark-cli run ablauf.json --in karten.pdf --json
passermark-cli run Visitenkarten --in karten.pdf     # Ablauf beim Namen aus den Ablauf-Ordnern
passermark-cli workflows                            # Abläufe in den Ordnern (--dirs: welche Ordner)
passermark-cli inspect karten.pdf --check           # Seiten, Formate, Endformat/Anschnitt, Prüfung
passermark-cli printers                             # Drucker
passermark-cli caps Canon-C3822i                    # Optionen, Fächer, Formate, Finisher eines Druckers
```

Drucken im Ablauf: Schritt `{"job": "print", "settings": {"printer": "…", "paper": "A3", "tray": "Fach 2",
"duplex": "short", "finishing": {"staple": "…"}, "layout": {"handling": "booklet"}, "dry_run": true}}` – gleicher
Weg wie der Druckdialog; `dry_run` schickt nichts, sondern meldet nur, was gedruckt würde.

Ablauf-Ordner: eigene unter `~/.config/passermark/ablaeufe/` bzw. `%APPDATA%\Passermark\ablaeufe\`, für alle
unter `/etc/passermark/ablaeufe/` bzw. `%ProgramData%\Passermark\ablaeufe\`. Ablauf-Datei, JSON-Ausgabe und
Fehlercodes wie oben beschrieben. Unbekannte Einträge und falsche Typen sind
Fehler; `check` meldet alle Probleme auf einmal. Die Ausgabe wird erst geschrieben, wenn alle Schritte geklappt
haben. Meldungstexte kommen in der Programmsprache – für Entscheidungen `event`, `code`, `severity`, `category`
verwenden.
