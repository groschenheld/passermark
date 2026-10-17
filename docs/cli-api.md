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
| `inspect file.pdf [--check] [--password PW] [--json]` | pages, formats, trim and bleed; `--check`: check results |
| `<job> in.pdf out.pdf [--preset …] [--set k=v …] [--pages …] [--json]` | a single job (as before) |

Exit codes: `0` ok · `1` error while working / file not found · `2` wrong invocation or invalid workflow ·
`130` cancelled (Ctrl+C or SIGTERM – no half-written output is left behind).

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
  to `run` (or `--out` for `check`) replaces it. Missing folders are created.
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

- `print` as a job/step with all options of the print dialog, including trays/rolls and finishers.
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
passermark-cli inspect karten.pdf --check           # Seiten, Formate, Endformat/Anschnitt, Prüfung
```

Ablauf-Datei, JSON-Ausgabe und Fehlercodes wie oben beschrieben. Unbekannte Einträge und falsche Typen sind
Fehler; `check` meldet alle Probleme auf einmal. Die Ausgabe wird erst geschrieben, wenn alle Schritte geklappt
haben. Meldungstexte kommen in der Programmsprache – für Entscheidungen `event`, `code`, `severity`, `category`
verwenden.
