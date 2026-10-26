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
| `serve --init [--system]` | create a template watch.json plus an example workflow and drop folder – never overwrites |
| `reprint log.json [--in FILE] [--dry-run] [--json]` | print a logged job again, exactly as logged (see *Print log*) |
| `plan FILE … [--kind plan\|poster] [--material NAME] [--plt cut.plt] [--printer P] [--rolls 594,841,914] [--roll ROLL] [--align center\|left\|right] [--copies N] [--collate] [--no-split] [--by-roll] [--color gray] [--frame auto] [--margin 5] [--rotate auto] [--pages …] [--set k=v …] [--dry-run] [--json]` | plan printing on roll printers: print area, roll choice, run length per roll, print (see *Plan printing*) |
| `rolls PRINTER [--host ADDRESS] [--json]` | the rolls loaded in a large-format printer (IPP, SNMP or entered by hand) |
| `probe PRINTER\|ADDRESS [--host A] [--community C] [--out report.json] [--json]` | device check: open ports, all IPP attributes (incl. `media-col-database`), SNMP v2c/v1 (sysDescr, prtInputTable, prtMediaPathTable, vendor branch), resulting rolls and level `blind` · `status` · `catalog` – read only |
| `shared-folder [--user NAME …] [--status] [--json]` | shared print folder for Passermark and its add-on programs (see *Shared print folder*); sets up via the root helper (pkexec), `--status` only reads |
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

## Conditions (`if`, `choose`, `fail`, `stop`)

Conditions are checked against the **current** PDF of the workflow (after the steps before):

```json
"steps": [
  {"job": "shrink", "if": {"size_mb": {">": 20}}},
  {"choose": [
    {"if": {"format": "A5", "pages": {">=": 8}}, "steps": [{"job": "impose", "preset": "Booklet A4"}]},
    {"if": {"format": "A4"},                      "steps": [{"job": "print", "settings": {"paper": "A4"}}]},
    {"else": [{"job": "fail", "message": "Format ${format} (${width_mm} × ${height_mm} mm) is not handled here"}]}
  ]}
]
```

- `if` on any step: the step only runs when the condition holds. `choose`: the first branch whose `if` holds runs,
  otherwise `else` (optional, last). Branches may contain any steps, also further `choose`.
- `fail` ends the workflow with its `message` – error code `rejected`, exit code 1; the watcher puts the file into
  `failed/` with the message in the `.log`. `stop` ends early without an error: the result so far is written.
  In messages `${…}` takes variables and facts (`${format}`, `${pages}` …).
- Facts: `pages`, `width_mm`, `height_mm`, `format` (standard size – the trim size if the page has one: A4, SRA3,
  Letter …; `""` = none), `page_format`, `orientation`, `mixed_sizes`, `trim`, `bleed_mm`, `size_mb`,
  `filename`, `output_intent`, `layers`, and from the document check `errors`, `warnings`, `infos`, `rgb`,
  `spot_colors`, `spot_names`, `fonts_missing`, `transparency`, `blank_pages`, `print_allowed` (the check only runs
  when a condition needs it);
  `var.NAME` for variables. `passermark-cli version --json` lists them (`conditions`).
- A plain value means “equal”, otherwise `{"==" | "!=" | ">" | ">=" | "<" | "<=" | "in" | "matches": value}`
  (`matches`: pattern with `*` `?`). Several entries in one condition must all hold; `all`, `any`, `not` combine.
  Texts are compared case-insensitively.
- `check` reports unknown facts, operators and wrong types. `run --json` reports each decision:
  `{"event": "condition", "where": "steps[1].choose[0]", "result": true, "why": "format A5 == A5, pages 12 >= 8"}`,
  `{"event": "branch", …, "taken": 0 | null, "branch": 0 | "else"}`, `{"event": "step_skipped", …}`,
  `{"event": "stopped", "message": …}`; `done` contains `decisions` and `stopped`.

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
| `rejected` | a `fail` step was reached – `message` from the workflow | 1 |
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

## Print log

When the print log is on (File → Settings, or forced for everybody in the administration: `print_log` with
`force`, `dir` – e.g. a network share – and `keep_days`), every print job is written as JSON:
`printlog/YYYY-MM/<time>_<file>.json` plus a line in `printlog/printlog.csv`. Default folder: Linux
`~/.local/state/passermark/printlog`, Windows `%LOCALAPPDATA%\Passermark\printlog`.

Each log holds time, user, computer, source (`dialog`, `cli`, `watch`, `rightclick`), file with SHA-256, pages,
printer, paper, tray, every driver option, the exact options sent, page handling, colour profile, copies, job id and
the result – plus a ready workflow that prints the job again exactly like this: `passermark-cli reprint log.json`
(`--dry-run`, `--in other.pdf`). A print inside a workflow logs the original input and the steps before it; the
reprint runs them again. A changed file is reported.

With step & repeat **step 2** the job sent to the printer is the step-2 result on the target size (like saving),
and the paper is the target size.

## Document check

The check (program: *Check*; `inspect --check`; conditions) reports with severity `error` | `warning` | `info` and a
category: `font`, `text`, `layer`, `transparency`, `image`, `size`, and since 1.18.2:

- `geometry` – page boxes: `UserUnit` ≠ 1 (error: many printers/RIPs ignore it); CropBox smaller than or beyond the
  MediaBox (> 0.5 mm – plotters that print the MediaBox shift the content); TrimBox outside the visible area or
  larger than the BleedBox; `/Rotate` (info); different page sizes (info); content up to the trim edge with less
  than 2 mm bleed on that side (warning, checked on a low-resolution rendering, pages without /Rotate).
- `security` – encrypted: printing not allowed (error), only low resolution (warning), otherwise info.
- `pdfx` – file claims PDF/X (`GTS_PDFXVersion` in Info or XMP) without a PDF/X output intent, intent without an
  embedded profile, pages without TrimBox/ArtBox. No full PDF/X validation.
- `form` – form fields; how many are not printed (hidden, print flag off, no appearance); `NeedAppearances`.
- `page` – blank pages (pages with little content and no images, rendered at low resolution).

The text report (`report_text`) lists the page boxes and the bleed per side of the first page.

## Plan printing (`plan`)

Job `plan` (workflow step `{"job": "plan", "settings": {…}}`, or `passermark-cli plan`) prints every page as a plan
on a roll printer – the same as *Plan & Poster → Plan printing* in the program:

- **Print area** (`frame`): `auto` – two outer lines: printing is limited to the outer one (it disappears, an exact
  margin stays around the plan); otherwise the content plus `margin_mm` (5). `frame`, `margin`, `none` (page).
- **Roll** (`rotate`): `auto` = the roll with the shortest length, rotation allowed (an A1 goes across the 841 roll),
  equal length → the narrower roll; `keep`, `short`, `long`. Only rolls whose grammage is in `weights` (75, 80)
  or unknown are used for plans; with a `material` the rolls with its grammage, else those whose media name matches
  the material's name/media type (e.g. “Polyprop”).
- **Fixed roll** (`roll_pick`, `--roll`): print only on this roll – its driver feed value (`slot`), its name at the
  device or its width (`914`); it overrides `weights` and `material`. Not loaded → automatic with a note.
  Without a media type (`media` or the material's), the roll's media type is sent when the driver offers a
  matching one (devices without roll selection in the driver choose the roll by width and media type).
- **Position on the roll** (`align`, `--align`): `left` | `right` – the page is as wide as the roll and the plan
  lies at the roll edge (margin or outer line kept), so only one lengthwise cut remains; `center` – the same space
  on both sides, nothing is masked by the device. Default: plan `left`, poster `center`.
- **Rolls**: read from the device (IPP `media-col-ready`/`printer-input-tray`, otherwise SNMP Printer MIB), otherwise
  the ones entered by hand in the program; `rolls` (`[594, 841]` or `[{"width_mm": 594, "slot": "Roll1"}]`)
  overrides both.
- **Order**: default uncollated (each plan with all copies); `collate` set by set; `"order": "roll"` narrowest
  roll first.
- **Copies** (`split_copies`, default `true`; `--no-split` turns it off): every copy is its own job with one page
  (title `… (1/3)`, `(2/3)` …), so the printer cuts after each one. `false`: one job with a copy count.
- Paper = custom size (`Custom.WxHmm`, width across the roll – with `align` the roll width), feed = the roll's
  driver value.
- Further settings: `color`, `media`, `scale_pct`, `bleed_mm` + `bleed_mode` (`mirror` | `blank` | `color`,
  `bleed_color`), `crop_marks`, `fix_hairlines` (+ `hairline_mm`), `fold_marks` (DIN 824, simplified), `options`,
  `profile`, `intent`, `dry_run`.
- **Posters** (`"kind": "poster"`, `--kind poster` sets the poster defaults: `align` `center`, `overwidth` `crop`,
  no plan paper grammage, `frame` `none`): quality print; `nest` (side by side, off by default; roll and orientation
  with the least paper = roll width × length; `gap_mm`, `max_page_m`), `overwidth` (`none` | `crop` | `tile` with
  `overlap_mm`). In a workflow set `nest`/`overwidth`/`align` explicitly.
- **Banners**: `hem_mm` + `hem_sides` (`lrtb`) – hem/pocket allowance outside the trim, replaces the bleed there;
  grommet marks `grommet_spacing_mm` (0 = off), `grommet_inset_mm`, `grommet_d_mm`, `grommet_sides`.
- **Print & cut**: `cut_contour` – rectangle in the spot colour `CutContour` (100 % magenta, overprint) around trim
  + hem, as VersaWorks, CutStudio and others expect; `printcut_marks` – corner marks if the cutting software adds
  none. `--plt FILE` additionally writes an HP-GL/CAMM-GL cut file of one set.
- **Material** (`material`: name or ID): print materials per user, category `plan` | `quality`, grammage (selects
  the roll), the driver's media type, quality and ink amount, colour profile, max. ink coverage (guide value).
- **Output folders**: printer `"folder:NAME"` writes every print page as PDF into a hot folder set up in the program
  (e.g. VersaWorks for Roland); copies = the page repeated, file name `…_<n>x.pdf`.
- **Roland cutters**: for devices whose name/model says Roland, the loaded width is read with `IN;OH;` on port 9100
  (never sent to other printers).

Output (`--json`, event `done`; also the step's `info`): `lengths` [{`roll`, `width_mm`, `plans`, `single_m`,
`total_m`, `short`}], `single_m`, `total_m`, `plans` [{`plan`, `page`, `qty`, `area`, `size_mm`, `roll_mm`,
`rotated`, `length_mm`, `hairlines`}], `jobs`, `unfit`, `rolls`, `roll_origin`, `notes`. Run length counts the plan
sizes only (no gaps, no lead-in). The print log has `kind: "plan"`, `roll_mm`, `length_mm`, `run_m` per job and the
CSV the columns `roll_mm`, `run_m` – the counter for cost calculation.

## Shared print folder

One folder for Passermark and all add-on programs (Passermark-GUI, Passerlink, PassCount …), outside the home
directories – services run as their own users without special rights and may not write into `/home/…`.

- **Linux**: `/srv/passermark/{hotfolder,ausgabe,archiv}`, group `passermark`, owner `root:passermark`, mode `2775`
  (setgid) and the default ACL `g:passermark:rwX` (package `acl`). Services run with `UMask=0007`.
- **Windows**: `%ProgramData%\Passermark\{hotfolder,ausgabe,archiv}` – only these three subfolders are writable for
  users; `%ProgramData%\Passermark` itself stays read-only (admin defaults, profiles, workflows).
- Set up by `install.sh` (also adds the installing user and the watcher service user `passermark`), the Windows setup,
  *Management → General → Set up shared print folder* (AppImage too, one password prompt) or
  `passermark-cli shared-folder [--user NAME]` (root helper `passermark-admin shared-folder`). Idempotent: creates
  what is missing and sets group/mode of the four folders. After joining the group: log in again or restart the
  service.
- `serve --init --system` (and `--init` once the folder exists) puts the example drop folder under
  `…/hotfolder/beispiel`; `serve --check` and the output folders of plan printing mark folders in a home directory.

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

`passermark-cli serve --init` creates a template `watch.json` (with `--system` the one for all users) with an
example workflow and drop folder – it never overwrites an existing one. Keys starting with `_` are comments.

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
passermark-cli serve --init                         # Vorlage watch.json (überschreibt nie)
passermark-cli reprint protokoll.json               # Auftrag aus dem Druckprotokoll genauso nochmal
passermark-cli plan mappe.pdf --copies 3 --dry-run  # Plandruck: Rollen, Laufmeter (ohne --dry-run: drucken)
passermark-cli plan poster.pdf --kind poster --roll 914 --copies 3   # Poster auf die 914er, je Exemplar ein Abschnitt
passermark-cli plan mappe.pdf --align right --rolls 914 --dry-run   # Pläne an den rechten Rollenrand
passermark-cli rolls ColorWave                      # geladene Rollen eines Plotters
passermark-cli shared-folder                        # gemeinsamer Druckordner /srv/passermark (Passwort über pkexec)
passermark-cli probe ColorWave --out bericht.json    # Gerät prüfen: was meldet es über IPP/SNMP (nur lesend)
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

Bedingungen im Ablauf: `"if"` an einem Schritt, `{"choose": [{"if": …, "steps": […]}, {"else": […]}]}`,
Schritte `fail` (abbrechen mit Meldung, Fehlercode `rejected`) und `stop` (vorzeitig fertig). Prüfwerte und
Vergleiche wie oben unter *Conditions*.

Plandruck: Schritt `{"job": "plan", "settings": {…}}` bzw. `passermark-cli plan` – zwei Außenlinien: bis zur
äußeren drucken, sonst Inhalt + 5 mm; Rolle mit der kürzesten Länge (Drehen erlaubt), nur Rollen mit Planpapier
(`weights`, Standard 75/80 g) bzw. passend zum `material` (Grammatur, sonst Name); feste Rolle mit `roll_pick` /
`--roll` (Zufuhr, Name am Gerät oder Breite). Lage auf der Rolle `align` / `--align`: `left`/`right` = am Rand
(Seite = Rollenbreite, nur ein Längsschnitt; Standard beim Plan), `center` = mittig (Standard beim Poster).
Exemplare: unsortiert als Standard (`collate`, `"order": "roll"`), jedes Exemplar ein eigener Auftrag
(`split_copies`, Standard an; `--no-split` = Kopienzahl in einem Auftrag). Laufmeter nur aus den Plangrößen; im
Druckprotokoll je Auftrag `roll_mm`, `run_m`. Einstellungen wie oben unter *Plan printing*.
Poster (`--kind poster`): Qualitätsdruck, mittig, nebeneinander nur auf Wunsch (`nest`), Überbreite abschneiden
oder in Bahnen (`overwidth`), Banner mit Saum (`hem_mm`) und Ösenmarken, `cut_contour` für Print & Cut, `--plt` für
eine Schneidedatei, `material` aus den Druckmaterialien, Ausgabe in einen Hotfolder mit `"printer": "folder:NAME"`.

Gemeinsamer Druckordner für Passermark und die Zusatzprogramme: Linux `/srv/passermark/{hotfolder,ausgabe,archiv}`,
Gruppe `passermark`, `2775` + Standard-ACL; Windows `%ProgramData%\Passermark\{hotfolder,ausgabe,archiv}` (nur diese
drei für Benutzer beschreibbar). Einrichten: `install.sh`, Windows-Setup, Verwaltung → Allgemein oder
`passermark-cli shared-folder`. Hotfolder in Home-Ordnern bekommen einen Hinweis.

Prüfung (seit 1.18.2 zusätzlich): Seitenrahmen (UserUnit, CropBox ≠ MediaBox, TrimBox/BleedBox widersprüchlich,
/Rotate, gemischte Formate, Inhalt bis zum Endformat-Rand bei weniger als 2 mm Beschnitt), Schutz (Drucken
verboten/nur niedrige Auflösung), PDF/X-Angabe ohne Output-Intent bzw. ohne TrimBox, Formularfelder (nicht
gedruckte, NeedAppearances), leere Seiten. Neue Prüfwerte für Bedingungen: `blank_pages`, `print_allowed`.

Druckprotokoll (Datei → Einstellungen bzw. vom Admin erzwungen): je Auftrag eine JSON-Datei plus `printlog.csv`;
`passermark-cli reprint protokoll.json` druckt ihn genauso nochmal.

Drop-Ordner: `passermark-cli serve` mit `watch.json` (Aufbau oben) – Ergebnisse nach `output`, Originale nach
`processed`, Fehler mit `.log` nach `failed`. Als Dienst: `linux/passermark-watch.service`,
`windows/watch-task.ps1`. Ablauf-Datei, JSON-Ausgabe und
Fehlercodes wie oben beschrieben. Unbekannte Einträge und falsche Typen sind
Fehler; `check` meldet alle Probleme auf einmal. Die Ausgabe wird erst geschrieben, wenn alle Schritte geklappt
haben. Meldungstexte kommen in der Programmsprache – für Entscheidungen `event`, `code`, `severity`, `category`
verwenden.
