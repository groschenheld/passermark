# Passermark – architecture

This document is the map of the code: what lives where, how the parts talk to each other and where to start
reading. User documentation is in the READMEs; the command line and workflow interface is specified in
[cli-api.md](cli-api.md).

## In one paragraph

Passermark is a PDF viewer with prepress and print functions (PySide6). All heavy work is written as
**jobs**: functions of the form *input PDF + settings → output PDF* that know nothing about the user interface.
The interface, the command line (`passermark-cli`), workflows and drop folders all call the same jobs with the
same settings, so anything the dialogs do can be automated. Other programs (Passermark-GUI, Passerlink,
PassCount) only use the command line.

## Layers

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ pdfdruck/gui/      windows, dialogs, panels (PySide6)                        │
│   viewer.py (main window) · printdialog.py · plandialog.py · …               │
├──────────────────────────────────────────────────────────────────────────────┤
│ pdfdruck/app.py    Controller: one per process – configuration, print        │
│                    session, open windows, single instance                    │
├───────────────────────────┬──────────────────────────────────────────────────┤
│ cli.py · workflow.py      │ jobproc.py     GUI runs a job as a CLI process   │
│ watch.py (drop folders)   │ renderproc.py  page rendering in its own process │
├───────────────────────────┴──────────────────────────────────────────────────┤
│ core.py            job registry: JOBS, run_job(), settings <-> dict/JSON     │
├──────────────────────────────────────────────────────────────────────────────┤
│ job modules        layout · vdp · cutcontour · preflight · cmyk · repair ·   │
│ (no Qt)            shrink · split · pressexport · planprint · …              │
├──────────────────────────────────────────────────────────────────────────────┤
│ devices            printers (CUPS) · printers_win · ipp · snmp · rolls ·     │
│                    trays · roland · printjob · printlog                      │
├──────────────────────────────────────────────────────────────────────────────┤
│ base               platform (OS differences) · config (admin defaults) ·     │
│                    l10n (language, user settings) · papersizes · crashlog    │
└──────────────────────────────────────────────────────────────────────────────┘
```

Rule of thumb: **a module imports only from its own layer or the layers below it.** Everything outside
`pdfdruck/gui/` and `app.py` runs without Qt, which is what makes the command line and the tests possible.

## Processes

| Process | Started by | Why |
|---|---|---|
| main program (`passermark`) | user | windows and dialogs |
| render server (`renderproc.py`) | `gui/renderclient.py` | pdfium is not thread-safe; rendering must not block the interface |
| job process (`passermark-cli …`) | `jobproc.py` | no frozen interface, clean cancelling, a crash does not take the program down |
| root helper (`admin/passermark-admin`, Windows: `winadmin.py`) | management dialog via pkexec/UAC | writing the admin defaults; input is validated by `cfgvalidate.py` |

Only one main program runs per user. A second start hands its files to the running instance (`fastipc.py`,
before Qt is loaded) and exits; `Controller.queue_request` receives them.

## Program start

1. `pdfdruck/__main__.py` parses the arguments (`--print`, `--merge`, `--repair`, `--plan`, `--poster`, files).
2. If an instance is running, the request is passed on and the process ends.
3. Otherwise a `Controller` (`app.py`) is created. It loads the admin configuration (`config.py`), creates the
   print `Session` (`session.py`) and opens the main window (`gui/viewer.py`) or the requested dialog.
4. Plan and poster printing are separate top-level windows (`gui/plandialog.py`); the program ends when the last
   window of any kind is closed.

## Jobs, settings, presets, workflows

- A **job** is registered in `core.JOBS` under a name (`impose`, `vdp`, `cutcontour`, `manip`, `repair`,
  `preflight_fix`, `separate`, `split`, `shrink`, `press`, `print`, `plan`) together with its settings dataclass.
- `core.run_job(kind, src, dst, settings)` runs one job. Settings are plain dataclasses;
  `core.settings_from_dict` / `settings_to_dict` convert them to and from JSON. Unknown keys are ignored and
  missing ones keep their default, so files from other versions still load.
- A **preset** (`presets.py`) is one job's settings saved under a name. Dialogs, command line and workflows read
  the same files.
- A **workflow** (`workflow.py`) is a JSON file with several steps, conditions (`conditions.py`) and variables.
  `watch.py` runs workflows on files dropped into folders (`passermark-cli serve`).
- The interface never calls a job directly for long work: `gui/jobs.py` and `jobproc.py` start
  `passermark-cli` in the background and show progress in the status bar.

## Printing

```
print dialog / plan dialog / workflow step "print"
        │  settings (LayoutSettings, PlanSettings, PrintSettings)
        ▼
layout.py / planprint.py   plan the sheets or roll runs, impose into a temporary PDF
        ▼
printjob.py                colour conversion (colorconv), tray selection (trays), build the driver options
        ▼
printers.py (CUPS) / printers_win.py (Windows GDI)       →  device
        ▼
printlog.py                one JSON record per job (used by `reprint` and PassCount)
```

`printers.PrinterCaps` describes one printer: every driver option with its choices and a table of **roles**
(`pagesize`, `source`, `media`, `duplex`, `color`, `quality` …) that maps Passermark's own terms to whatever the
driver calls them. Code above this layer works with roles, never with driver keywords.

Large-format printers add `rolls.py` (what is loaded – from IPP, SNMP or entered by hand), `printmat.py`
(materials) and `planprint.py` (print area, roll choice, run length).

## Files on disk

| What | Where | Module |
|---|---|---|
| admin defaults (printers, profiles, trays) | `/etc/passermark/defaults.json`, Windows: ProgramData | `config.py` |
| user settings (language, last used values, custom sizes, rolls) | `~/.config/passermark/settings.json`, Windows: `%APPDATA%\Passermark` | `l10n.py` |
| presets | `presets/<job>/<name>.json` next to the user settings | `presets.py` |
| user materials (`materials.json`) and ICC profiles | `usercolor.user_dir()` | `usercolor.py` |
| print log, error logs, plan history | see `platform.user_log_dir()` and the modules | `printlog.py`, `crashlog.py`, `planhistory.py` |
| shared print folder for the add-on programs | `/srv/passermark` | `shared.py` |

Most paths come from `platform.py`. Exception: `l10n.py` computes the location of `settings.json` itself.

## User-visible text

Source strings are German and wrapped in `tr("…")`. Translations live in `pdfdruck/lang/<code>.py`
(en, hu, es, fr). `tests/test_l10n.py` fails if a string in the code has no translation. Comments and docstrings
are English.

## Tests

`tests/test_<module>.py`, each runnable on its own (`python3 tests/test_layout.py`). GUI tests run against a
Qt stand-in (`tests/_qtstub`) so they work without a display; they check wiring, not appearance. Printing is
tested against fake printers. See CONTRIBUTING.md for the style rules (`ruff format`, `ruff check`).

## Known rough edges

Listed so that a reader does not mistake them for intent. They are tracked for clean-up.

- **Very large interface modules**: `gui/viewer.py`, `gui/printdialog.py` and `gui/plandialog.py` build their
  whole window in one class. The long functions are split up (1.18.24–1.18.32); `gui/viewer.py` is being split
  into modules (thumbnails, merge dialog, small widgets and opening files are out since 1.18.34).
  The plan is in the project notes ("Stufe 5").
- **Imports against the layer rule**: `preflight.py` uses three helpers from `planprint.py`; `workflow.py`
  imports `cli.py` (and the reverse); `printers.py` and `printers_win.py` import each other. These are done inside functions to avoid import cycles.
- **Imports inside functions** are common. Some are deliberate (fast start, optional dependencies such as
  pywin32 or pycups), many are not.
- **Broad `except Exception`** is used widely so that a device or driver quirk never crashes the interface;
  in a number of places the error is dropped without a log entry.
- `LayoutSettings` / `ManipSettings` have hand-written `from_dict`/`to_dict`; newer settings use
  `core.settings_from_dict`.

## Module reference

Generated from the module docstrings: `python3 tools/module_overview.py`.

<!-- modules:begin -->
### Core (no user interface)

| Module | Purpose |
|---|---|
| `pdfdruck/__main__.py` | passermark [--print] [--open] [FILES …] |
| `pdfdruck/app.py` | Program-wide state + single instance. |
| `pdfdruck/cfgvalidate.py` | Validation of the admin configuration – shared by the Linux helper (pkexec) and the Windows helper (UAC). |
| `pdfdruck/cli.py` | Command line: run jobs without a GUI. |
| `pdfdruck/cmyk.py` | CMYK conversion of PDFs and color-accurate preview. |
| `pdfdruck/colorcheck.py` | Colour check of a document against a printing condition – facts, findings, recommendations. No Qt. |
| `pdfdruck/colorconv.py` | Color conversion of the finished print PDF to an output profile. |
| `pdfdruck/colorlab.py` | Colour measurement and materials (papers) – no Qt. |
| `pdfdruck/conditions.py` | Conditions in workflows ("if", "choose") – checked against the CURRENT PDF of the workflow. No Qt. |
| `pdfdruck/config.py` | Admin defaults from /etc/passermark/defaults.json. |
| `pdfdruck/convert.py` | Any files -> PDF: PDFs directly, images via img2pdf, Office via LibreOffice, OnlyOffice or Euro-Office. |
| `pdfdruck/core.py` | Core interface: every heavy function as "input PDF + settings → output PDF". |
| `pdfdruck/crashlog.py` | Error log: every kind of error ends up in a file you can send along. |
| `pdfdruck/cutcontour.py` | CutContour for cutting plotters (Roland VersaWorks and others) with automatically generated bleed. |
| `pdfdruck/datakinds.py` | Data kinds for variable data: which columns a table needs and how the content of a code is built from them. |
| `pdfdruck/docinfo.py` | Document information for other programs (passermark-cli inspect): pages, formats, trim and bleed and, optionally, the check results – as a plain dict (JSON). |
| `pdfdruck/editing.py` | Edit mode: change text rows (text, font, size) and edit layers. |
| `pdfdruck/editops.py` | Edit mode: the changes as named operations (no user interface). |
| `pdfdruck/examples.py` | Bundled examples (variable data) and manuals. |
| `pdfdruck/fastipc.py` | Hand a request to the running instance – without Qt, at the very start of the program. |
| `pdfdruck/i18n.py` | German names for typical (English) driver options and values. |
| `pdfdruck/iccfetch.py` | Obtaining ICC profiles: download via link, unpacking (ZIP, driver packages via 7z), validation. |
| `pdfdruck/imagecheck.py` | Check images and colours: colour space (RGB/CMYK/grey/spot) with the ICC profile name, the effective resolution of every placed image (also inside forms, also when used several times) and the resulting maximum print size. |
| `pdfdruck/images.py` | Opening images as PDFs – at their actual size (from the image's DPI value). |
| `pdfdruck/ipp.py` | Minimal IPP client (RFC 8010/8011): asks the printer directly what lies in which tray. |
| `pdfdruck/jobproc.py` | Jobs as a separate process: the GUI starts the command line in the background. |
| `pdfdruck/l10n.py` | Interface language: German (source language), English, Hungarian, Spanish, French. |
| `pdfdruck/layout.py` | Page selection, scaling and N-up imposition. |
| `pdfdruck/measure.py` | Ruler and measuring – pure computation logic (no GUI, therefore precisely testable). |
| `pdfdruck/objects.py` | Object detection on PDF pages (vector and raster) and splitting into individual pages. |
| `pdfdruck/pagegeom.py` | Page <-> screen without loading the page: a re-implementation of pdfium's CPDF_Page::GetDisplayMatrix. |
| `pdfdruck/pageops.py` | Page operations on the open document (pdfium), no user interface. |
| `pdfdruck/papersizes.py` | Paper sizes in ONE place (mm, portrait) – no Qt. |
| `pdfdruck/pdfmanip.py` | Document manipulation: cropping to a target size and CMYK conversion. |
| `pdfdruck/pipette.py` | Colour pipette: what is at a given point of the page? |
| `pdfdruck/planhistory.py` | History of plan and poster printing |
| `pdfdruck/planprint.py` | Plan printing on roll printers (production print, usually 75/80 g paper). No Qt. |
| `pdfdruck/platform.py` | Operating system differences in one place: paths, user id, notifications, programs. |
| `pdfdruck/preflight.py` | Preflight: check a document (fonts, layers, transparency, characters) and repair it in a targeted way. |
| `pdfdruck/presets.py` | Presets: named settings per job – the same files for the GUI, the command line and (later) the watcher. |
| `pdfdruck/pressexport.py` | Output for the print shop (job "press"): convert as recommended, always embed the printing condition as output intent, check before/after, optionally a package with PDF, ICC profiles and a short report. |
| `pdfdruck/printcli.py` | Printing without a user interface (workflow step "print", passermark-cli printers / caps). |
| `pdfdruck/printers.py` | Printer integration via CUPS (pycups). |
| `pdfdruck/printers_win.py` | Printer integration on Windows (pywin32). |
| `pdfdruck/printjob.py` | Build and send a print job â shared by the print dialog and right-click printing. |
| `pdfdruck/printlog.py` | Print log: every print job with its exact settings – one JSON file per job plus printlog.csv. No Qt. |
| `pdfdruck/printmat.py` | Print materials for roll printers (plan & poster): main category, then the settings per material. |
| `pdfdruck/probe.py` | Device check: what a printer/plotter reveals over the network – raw, to pass on and evaluate. No Qt. |
| `pdfdruck/proof.py` | Preview the way it comes out of the printer (as far as predictable). |
| `pdfdruck/renderproc.py` | Render server for the page view: its own process with its own pdfium (pdfium is not thread-safe). |
| `pdfdruck/repair.py` | Repair PDFs and optimize them for sharing. |
| `pdfdruck/roland.py` | Roland cutting plotters (CAMM-1 GS/GS2/GR/GX …) over the network (raw port 9100): loaded material width and direct cut jobs in CAMM-GL III (HP-GL dialect). |
| `pdfdruck/rolls.py` | Rolls of large-format printers and plotters: what is loaded (width, grammage, media, remaining length). |
| `pdfdruck/selftest.py` | Self-test of the finished program file (EXE/AppImage): checks that all bundled dependencies load. |
| `pdfdruck/session.py` | Print session (printers, options, colour profile, layout) – no Qt, for the program and the command line. |
| `pdfdruck/shared.py` | Shared print folder for Passermark and all add-on programs (Passermark-GUI, Passerlink, PassCount …). |
| `pdfdruck/shrink.py` | File size: show what takes up the space and reduce it selectively – every measure can be switched separately. |
| `pdfdruck/snmp.py` | Minimal SNMP v2c client (read only) – fallback when a printer does not report its rolls over IPP. |
| `pdfdruck/softmask.py` | Convert transparent gradients (soft masks) into opaque images where needed – without Ghostscript. |
| `pdfdruck/split.py` | Splitting pages: halve a page vertically/horizontally or cut it into a grid – every piece becomes its own page. |
| `pdfdruck/trays.py` | Automatic tray selection: size (+ grammage) -> first matching, non-empty tray. |
| `pdfdruck/usercolor.py` | Own materials and ICC profiles of the user – no admin rights, no Qt. |
| `pdfdruck/vdp.py` | Variable data |
| `pdfdruck/watch.py` | Drop folders (passermark-cli serve): files dropped into a folder run through a workflow. No Qt. |
| `pdfdruck/winadmin.py` | Admin changes on Windows: counterpart to polkit/pkexec. |
| `pdfdruck/workflow.py` | Workflows: several jobs in a row, described as JSON – the public interface for other programs. |

### User interface (PySide6)

| Module | Purpose |
|---|---|
| `pdfdruck/gui/admindialog.py` | Management of the defaults – saved via pkexec + helper (a single password prompt). |
| `pdfdruck/gui/colorpanel.py` | Farbe → Farbprüfung: side panel next to the soft proof. |
| `pdfdruck/gui/common.py` | Shared GUI helpers and the session state (kept in memory only). |
| `pdfdruck/gui/crashui.py` | Error log in the interface: message on unexpected errors, notice after a crash. |
| `pdfdruck/gui/customsizes.py` | Manage custom sizes: name, width, height – stored permanently, for all printers and "Save as PDF". |
| `pdfdruck/gui/datadialog.py` | Dialog "Enter data": create a data table for variable data right inside Passermark. |
| `pdfdruck/gui/docscroll.py` | Scroll bar for the whole document in the single-page view. |
| `pdfdruck/gui/editpanel.py` | Sidebar "Edit": text rows (text, font, size) and layers (on/off, remove, replace, scale/move). |
| `pdfdruck/gui/fileopen.py` | Opening files |
| `pdfdruck/gui/hdrdialog.py` | Question for HDR photos (photo + grey gain map): when opening and in the document check. |
| `pdfdruck/gui/iccimport.py` | Admin: obtain color profiles for a printer – sources, link download, file/ZIP/driver package. |
| `pdfdruck/gui/icons.py` | Own single-colour line icons (24×24, drawn as SVG) – plain, matching the dark theme. |
| `pdfdruck/gui/jobs.py` | Jobs in the interface: shown in the status bar with progress and cancel. |
| `pdfdruck/gui/manipdialog.py` | Document manipulation: control panel (tab in the print dialog + its own dialog) and colour preview. |
| `pdfdruck/gui/mapdialog.py` | Dialog "Map columns": which column of your CSV provides which piece of a QR code with a kind (business card, WLAN …). |
| `pdfdruck/gui/materialsdialog.py` | Farbe → Papiere und Messungen |
| `pdfdruck/gui/materialtab.py` | Materials (papers) |
| `pdfdruck/gui/measuredialog.py` | Determine the paper white of a material: with the measuring device (ArgyllCMS spotread – X-Rite i1Pro, ColorMunki, i1Studio …), from a measurement file (CGATS from i1Profiler/ArgyllCMS, spotread log) or by hand. |
| `pdfdruck/gui/mergedialog.py` | Dialog "Zusammenführen": put files (PDF, images, Office) in order and combine them into one PDF. |
| `pdfdruck/gui/objectsdialog.py` | Dialogs "Separate objects" (individual pages without white space) and "Create CutContour" (cutting plotters). |
| `pdfdruck/gui/pagewidgets.py` | Small widgets of the document view: one page, the rulers, smooth scrolling and the page number field. |
| `pdfdruck/gui/pipettedialog.py` | Colour pipette: small tool window next to the page. |
| `pdfdruck/gui/plandialog.py` | Plan & Poster → Plandruck … and Rollen … |
| `pdfdruck/gui/preflightpanel.py` | Sidebar "Check": findings, fonts, layers, transparency – with repairs (result in a new window). |
| `pdfdruck/gui/presetbar.py` | Preset bar for dialogs: pick saved settings, save, delete, share as a file. |
| `pdfdruck/gui/pressdialog.py` | Farbe → Für Druckerei ausgeben … – assistant in four steps |
| `pdfdruck/gui/printdialog.py` | Own print dialog (Acrobat layout): settings on the left, live preview on the right. |
| `pdfdruck/gui/propsdialog.py` | Datei → Eigenschaften: location, file, document, pages, fonts, check. |
| `pdfdruck/gui/renderclient.py` | Page rendering in the background: one render process for the whole program (see renderproc.py). |
| `pdfdruck/gui/repairdialog.py` | Dialog: repair PDFs, optimize for sharing, set/remove password protection. |
| `pdfdruck/gui/settingsdialog.py` | File → Settings: the user's personal settings (currently: language). |
| `pdfdruck/gui/shrinkdialog.py` | Reduce file size: breakdown of the file size and every measure on/off separately. |
| `pdfdruck/gui/softproofdialog.py` | Set up the soft proof of the page view: printing condition (material or profile), intent, paper white, black, warnings. |
| `pdfdruck/gui/splitdialog.py` | Dialog "Split pages": halve or grid, which pages, order – with a preview of the cut lines. |
| `pdfdruck/gui/stallwatch.py` | Stall log: notices when the interface hangs and records what the main window is doing at that moment. |
| `pdfdruck/gui/tabhost.py` | Window frame with tabs: every document is a full Passermark window (menus, bars, sidebars) – here as a tab. |
| `pdfdruck/gui/theme.py` | Dark theme with a yellow accent + global mouse wheel guard. |
| `pdfdruck/gui/thumbs.py` | Thumbnails of the pages in the side bar: list, drawing of an entry, loading in the background. |
| `pdfdruck/gui/vdpdialog.py` | Dialog "Variable data": create fields and place them with the mouse, CSV data source, numbering, preview of any record. |
| `pdfdruck/gui/viewer.py` | Acrobat-like main window: thumbnails on the left, continuous view, toolbar, page operations. |
<!-- modules:end -->
