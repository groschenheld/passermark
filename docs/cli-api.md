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
| `caps PRINTER [--json]` | the printer's driver options with all choices, which option serves which role, paper sizes (`page_size_source`: `driver` · `code` = from the PPD's PostScript · `text` = from the name · `table`; `page_size_problems`: PPD errors such as a decimal comma) |
| `serve [--config watch.json] [--once] [--check] [--json] [--quiet] [--log FILE]` | drop folders: files dropped into a folder run through its workflow (see below) |
| `tidy file.json [--full] [--out FILE] [--print] [--json]` | shorten a preset or workflow to the values that differ from the default (`--full`: preset with every value). Steps with `preset` and the `layout` of a print step stay as they are |
| `<job> in.pdf out.pdf [--preset …] [--set k=v …] [--pages …] [--json]` | a single job (as before) |

Exit codes: `0` ok · `1` error while working / file not found · `2` wrong invocation or invalid workflow ·
`130` cancelled (Ctrl+C or SIGTERM – no half-written output is left behind).

## Workflow folders

Workflows can be called by name instead of by path: `passermark-cli run "Business cards" --in order.pdf`. Passermark
looks in these folders, in this order – the first workflow with the name wins:

| | own | shared (administrator, optional) | for all users (administrator) |
|---|---|---|---|
| Linux | `~/.config/passermark/workflows/` | any folders, e.g. a network share | `/etc/passermark/workflows/` |
| Windows | `%APPDATA%\Passermark\workflows\` | e.g. `\\server\print\workflows` | `%ProgramData%\Passermark\workflows\` |

Shared folders are entered in the administration (General → *Additional workflow folders*, `workflow_dirs` in the
admin settings). Who may add workflows there is decided by the folder's permissions – e.g. a group with write
access – so nobody needs administrator rights for that. Up to 1.14 the folders were called `ablaeufe`; an old
folder is renamed to `workflows` the first time (or still read, if Passermark may not rename it).

`passermark-cli workflows` lists them (`"source": "user" | "shared" | "system"`), `--dirs` shows the folders. Relative paths inside a workflow (presets, CSV
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
- `paper: "auto"`: the paper that matches the PDF – with handling `size` the page, with `booklet` two pages side by
  side (A5 pages → A4). Measured is the first page printed (mixed sizes → a note); tolerance 2 mm, either
  orientation; no matching paper size at the printer is an error listing the available ones. Not possible for
  multiple/poster (give the paper). Empty `paper` = the printer's default paper (admin setting or driver).
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
"paper": "A3", "options": {all driver options as sent}, "color_profile": "…", "notes": [], "dry_run": false}`.

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

## Drop folders (`serve`)

`passermark-cli serve` watches folders: every file dropped into a folder runs through the workflow assigned to it.
The settings are a JSON file – `--config`, otherwise the own `~/.config/passermark/watch.json`
(`%APPDATA%\Passermark\watch.json`), otherwise the one for all users `/etc/passermark/watch.json`
(`%ProgramData%\Passermark\watch.json`):

```json
{
  "passermark": "watch", "version": 1,
  "interval": 5, "settle": 5,
  "folders": [
    {"in": "/srv/print/business-cards", "workflow": "Business cards"},
    {"in": "/srv/print/a4-booklet", "workflow": "booklet.json", "out": "", "done": "",
     "patterns": ["*.pdf", "*.jpg"], "vars": {"customer": "Muster"}, "name": "Booklets"}
  ]
}
```

- `interval`: seconds between two scans · `settle`: a file counts as complete once its size and time stayed
  unchanged that long (copies over the network, scanners) – files ending in `.part`, `.tmp`, `.crdownload` and
  hidden files are never picked up.
- per folder: `in` and `workflow` (name from the workflow folders or a JSON file) are required. `out` = results
  (default `output`, `""` = keep no result), `done` = originals afterwards (default `processed`, `""` = delete),
  `error` = failed originals with a `.log` next to them (default `failed`), `patterns` (default `["*.pdf"]`),
  `vars` (`${name}` in the workflow), `name` (for messages).
- Relative paths: `in`/`workflow` from the folder of watch.json, `out`/`done`/`error` from the `in` folder.
- The result is always written to `out` as `<name>.pdf` (never overwritten: `-1`, `-2` …), not where the workflow's
  own `output` points – next to the dropped file it would be picked up again. A workflow that only prints keeps no
  result unless `out` is given. `${dir}` and `${stem}` refer to the dropped file, `${out}` to the out folder.
- Each file is first moved into `<in>/.passermark/` (claimed): several watchers on one folder never process a file
  twice, a file still locked by the copy is simply tried again. Claimed files left over from a crash go back into
  the folder at the next start.
- Polling instead of file system notifications – works the same on network shares and on Windows.
- `--check`: check folders and workflows, process nothing · `--once`: process what is there and exit
  (exit code 1 if a file failed – handy for cron) · `--log FILE`: also append the messages to a file ·
  `SIGTERM`/Ctrl+C: stops after the current step; the file goes back into its folder.

`--json` events (one per line): `watch_start` (`folders`, `recovered`), `file` (`folder`, `file`, `workflow`), the
workflow's `step` / `step_done` with `file`, `file_done` (`output`, `moved_to`, `pages`, `prints` [{`printer`,
`job_id`, `dry_run`}], `notes`, `seconds`), `file_failed` (`moved_to`, `message`, `problems`), `stopped`
(`done`, `failed`).

As a service with its own user without special rights: Linux `linux/passermark-watch.service` (systemd, setup
steps in the file), Windows `windows/watch-task.ps1` (scheduled task at system start, log in
`%ProgramData%\Passermark Watcher\watch.log`). The user needs write access to the drop folders and – on Windows –
the printers installed for it.

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
passermark-cli serve --check                        # Drop-Ordner prüfen (watch.json)
passermark-cli serve                                # Drop-Ordner überwachen (--once: einmal durch)
passermark-cli tidy preset.json                    # Preset/Ablauf auf die Abweichungen vom Standard kürzen
```

Drucken im Ablauf: Schritt `{"job": "print", "settings": {"printer": "…", "paper": "A3", "tray": "Fach 2",
"duplex": "short", "finishing": {"staple": "…"}, "layout": {"handling": "booklet"}, "dry_run": true}}` – gleicher
Weg wie der Druckdialog; `dry_run` schickt nichts, sondern meldet nur, was gedruckt würde. `"paper": "auto"`
wählt das Papier nach der PDF (Größe: die Seite, Broschüre: zwei Seiten nebeneinander).

Ablauf-Ordner (der erste mit dem Namen gewinnt): eigene unter `~/.config/passermark/workflows/` bzw.
`%APPDATA%\Passermark\workflows\`, dann die vom Admin eingetragenen weiteren Ordner (z. B. Netzwerkfreigabe,
Schreibrecht über die Ordnerrechte), dann für alle unter `/etc/passermark/workflows/` bzw.
`%ProgramData%\Passermark\workflows\`. Alte Ordner `ablaeufe` (bis 1.14) werden umbenannt.

Drop-Ordner: `passermark-cli serve` mit `watch.json` (Aufbau oben) – Ergebnisse nach `output`, Originale nach
`processed`, Fehler mit `.log` nach `failed`. Als Dienst: `linux/passermark-watch.service`,
`windows/watch-task.ps1`. Ablauf-Datei, JSON-Ausgabe und
Fehlercodes wie oben beschrieben. Unbekannte Einträge und falsche Typen sind
Fehler; `check` meldet alle Probleme auf einmal. Die Ausgabe wird erst geschrieben, wenn alle Schritte geklappt
haben. Meldungstexte kommen in der Programmsprache – für Entscheidungen `event`, `code`, `severity`, `category`
verwenden.
