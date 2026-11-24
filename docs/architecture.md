# Passermark – architecture

This document is the map of the code: what lives where, how the parts talk to each other and where to start
reading. For an introduction to the features and walkthroughs through the code read [guide.md](guide.md) first.
User documentation is in the READMEs; the command line and workflow interface is specified in
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
│   mainwindow.py · pageview.py · printdialog.py · plandialog.py · …           │
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
   print `Session` (`session.py`) and opens the main window (`gui/mainwindow.py`) or the requested dialog.
4. Plan and poster printing are separate top-level windows (`gui/plandialog.py`); the program ends when the last
   window of any kind is closed.

## Jobs, settings, presets, workflows

- A **job** is registered in `core.JOBS` under a name (`impose`, `vdp`, `cutcontour`, `manip`, `repair`,
  `preflight_fix`, `separate`, `split`, `shrink`, `press`) together with its settings dataclass. Workflows add
  the steps `print` and `plan` (`workflow.py`), which print and leave the PDF unchanged.
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
are English. Anyone can translate without touching code (`langpack.py`, see [translating.md](translating.md)):
the texts are exported as a table, a filled-in table is checked and installed per user (`lang/<code>.json` next
to the settings – it completes a shipped language or adds a new one), and `passermark-cli lang import` turns it
into a catalog of the program.

## Look of the main window (1.19.0)

The design follows Hias' sheet: one black title row with gear, menu and the word mark (`gui/titlebar.py`, the
window is then frameless and resized at its edges; File → Settings switches back to the system frame), one
toolbar in groups (file, navigation, tools on the page, rotate/layout, zoom), the thumbnails at the left, a small tool box over the page, tabs at the right edge (Werkzeuge opens the tools panel, Plan and Poster their windows –
`gui/sidepanels.py`), and the status bar with the check result, the page and the update state.

With the own title bar the tabs stand outside the page area (since 1.19.1): the window frame (`gui/tabhost.py`)
is transparent at the right, places the tabs of the current document there and sets a window mask (page area +
tabs), so clicks into the empty margin reach what lies behind. The edge grips sit at the page area. With the
system frame the tabs stay inside the window (`MainWindow.edges_inside`). The tool box (merge, split, edit) lies
over the page, right of the sidebar, and folds away with an arrow (`sidepanels.ToolboxOverlay`, since 1.19.3).
The grip symbol marks the separators between sidebar, page and tools panel and (turned) the size grip in the
window corner; the scroll symbol sits on the handles of the two large scroll bars (`QScrollBar#bigScroll`). QSS
needs image files for both, so `theme.py` writes them, coloured in the accent, next to the check mark.

Panels in the sidebars get narrow without cutting anything off (`common.responsive_panel`, since 1.19.5): button
texts break into lines, tabs wrap into rows, lists and tables wrap their text. The tools panel keeps text next to
the symbols while there is room and shows only the symbols below that. Switching the page arrangement keeps the
page and the place in it (`PageView.set_view_mode`).

Fonts ship with the program (since 1.19.4): Inter for the interface (with digits of equal width) and JetBrains
Mono for measurements and sizes, in `gui/fonts/` with their licence texts (SIL Open Font License);
`theme.load_fonts()` registers them at start, so the look does not depend on the fonts of the system.

Colours come only from `gui/theme.py` (Hias' palette), icons only from `gui/svgicons/` (Hias' set, drawn with
`currentColor`, coloured per state by `gui/icons.py`; a name used in the program maps to its file in `_FILES`).

## Image export and SVG (1.19.8)

`rasterexport.py` renders pages with pdfium (RGB, grey, transparent PNG) or Ghostscript `tiff32nc` (CMYK with
a profile) and saves them with Pillow; every file is written to `*.part` first and renamed at the end, so a
cancelled export leaves no half files. The GUI starts it as a `JobProcess` (`jobproc.EXPORT`) like any other
job; the CLI command `export` and the workflow step `export` use the same `ExportSettings`. Presets are not
offered for the export.

`images.py` converts SVG with rsvg-convert (PATH first, then `rsvg/` next to the frozen executable), then
Inkscape, then Qt, and keeps a short report per file (`svg_report`) so the GUI can say which path was used and
warn about rasterised parts.

## Updates

`pdfdruck/updates.py` asks the GitHub releases of the repository (at most once a day at start, from Help, or by a
click on the symbol in the status bar) and compares versions. The stable channel only takes plain tags
(`v1.19.1`); a tag with a suffix or a release marked as pre-release only reaches the test channel. A version
remembered as available is asked for again at the next start, in case it was withdrawn. How an update is applied depends on the installation: the AppImage swaps itself, the Windows
setup runs silently and starts Passermark again (`/AUTOUPDATE`, `windows/passermark.iss`), an install.sh
installation downloads the source package and lets root install it (`passermark-admin update`, which fetches the
checksum itself instead of trusting the caller). Every download is checked against the `<file>.sha256` that the
release workflows publish with it; without it nothing is installed. Pushing a tag `v*` starts both build workflows
by themselves; each attaches its files in a `release` job (one concurrency group, so the two never create the
release twice), marks a tag with a suffix as pre-release and takes the release text from the changelogs
(`tools/release_notes.py`, German and English – the update dialog shows it). If a file is still missing, the
dialog says which one instead of only pointing to the release page (`updates.why_not`). Without the workflows
(e.g. no Actions minutes left) the same release is made locally: `tools/release_local.sh <tag>` (source package,
AppImage, checksums, text) and `windows/release_upload.ps1 <tag>` on the Windows machine (Setup.exe). The administrator can switch the check off or
allow test versions (admin configuration `updates`). The window side is `gui/updatestatus.py`.

## Error handling

A device, driver or broken PDF must never take the interface down, so errors are caught at many places. The
rule is that no error disappears without a trace: every `except Exception` does one of three things, and
`ruff check` (rule BLE001) enforces it.

- **Show it.** At the boundary to the user (dialogs, menu actions) the error ends up in a message box, a status
  text or an error list. The handler says so: `# noqa: BLE001 – shown to the user`.
- **Log it.** Where the program works around an error it did not expect (a check that could not run, a page
  that could not be rendered, a fallback taken), it writes a warning with the traceback:
  `log.warning("Prüfung: Haarlinien nicht geprüft", exc_info=True)`, with `log = logging.getLogger(__name__)`.
  The message is German like the rest of the log.
- **Say why it is expected.** Broken objects in a PDF, an optional module that is not installed, a driver that
  does not answer a query, cleanup of something that may already be gone. The reason goes next to the handler:
  `# noqa: BLE001 – malformed PDF object: skipped or default value`.

Where the warnings go: in the GUI `crashlog.install` writes them to the error log as "Hinweis" entries – the file
is kept so it can be sent along, but it is not reported as a crash at the next start, and the same note is
written at most three times per run. The render process writes them to its stderr; if the process ends
unexpectedly, the GUI copies the end of that output into the error log. Without a log (CLI, tests) they stay
silent (`NullHandler` in `pdfdruck/__init__.py`).

`try/except/pass` is preferred over `contextlib.suppress` (ruff SIM105 is off): the except line is where the
reason is written.

## Tests

`tests/test_<module>.py`, each runnable on its own (`python3 tests/test_layout.py`). GUI tests run against a
Qt stand-in (`tests/_qtstub`) so they work without a display; they check wiring, not appearance. Printing is
tested against fake printers. See CONTRIBUTING.md for the style rules (`ruff format`, `ruff check`).

## Known rough edges

Listed so that a reader does not mistake them for intent. They are tracked for clean-up.

- **Windows built from mixins**: the main window (`gui/mainwindow.py`), the print dialog (`gui/printdialog.py`)
  and the plan window (`gui/plandialog.py`) are each one class whose methods are spread over several modules by
  topic (`main*.py`, `print*.py`, `plan*.py`). The parts still share the window's attributes freely; separating
  them further (own objects instead of mixins) is left for where the redesign changes them anyway. The document
  view (`gui/pageview.py`) is split the same way, except for the arrangement of the pages, which is a
  separate object (`gui/viewlayout.py`: single page, continuous, facing pages, grid) so that a new view mode is
  one more class.
- **Imports against the layer rule**: `preflight.py` uses three helpers from `planprint.py`; `workflow.py`
  imports `cli.py` (and the reverse); `printers.py` and `printers_win.py` import each other. These are done inside functions to avoid import cycles.
- **Imports inside functions** are common. Some are deliberate (fast start, optional dependencies such as
  pywin32 or pycups), many are not.
- **Broad `except Exception`** is still used widely so that a device or driver quirk never crashes the
  interface. Each one now shows, logs or explains the error (see Error handling), but many could catch a
  narrower exception type.
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
| `pdfdruck/bleedgen.py` | Create bleed for customer files without it |
| `pdfdruck/cfgvalidate.py` | Validation of the admin configuration – shared by the Linux helper (pkexec) and the Windows helper (UAC). |
| `pdfdruck/cli.py` | Command line: run jobs without a GUI. |
| `pdfdruck/cmyk.py` | CMYK conversion of PDFs and color-accurate preview. |
| `pdfdruck/colorcheck.py` | Colour check of a document against a printing condition – facts, findings, recommendations. No Qt. |
| `pdfdruck/colorconv.py` | Color conversion of the finished print PDF to an output profile. |
| `pdfdruck/colorlab.py` | Colour measurement and materials (papers) – no Qt. |
| `pdfdruck/colorrules.py` | Colour rules for the whole document (like "global changes" in PitStop) – also as a job in workflows. |
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
| `pdfdruck/fontlib.py` | Fonts |
| `pdfdruck/i18n.py` | German names for typical (English) driver options and values. |
| `pdfdruck/iccfetch.py` | Obtaining ICC profiles: download via link, unpacking (ZIP, driver packages via 7z), validation. |
| `pdfdruck/imagecheck.py` | Check images and colours: colour space (RGB/CMYK/grey/spot) with the ICC profile name, the effective resolution of every placed image (also inside forms, also when used several times) and the resulting maximum print size. |
| `pdfdruck/images.py` | Opening images as PDFs – at their actual size (from the image's DPI value). |
| `pdfdruck/ipp.py` | Minimal IPP client (RFC 8010/8011): asks the printer directly what lies in which tray. |
| `pdfdruck/jobproc.py` | Jobs as a separate process: the GUI starts the command line in the background. |
| `pdfdruck/l10n.py` | Interface language |
| `pdfdruck/langpack.py` | Translations by anyone: export the texts as a table, check a filled-in table, install it for the user or turn it into a catalog of the program (pdfdruck/lang/<code>.py). |
| `pdfdruck/layout.py` | Page selection, scaling and N-up imposition. |
| `pdfdruck/measure.py` | Ruler and measuring – pure computation logic (no GUI, therefore precisely testable). |
| `pdfdruck/objects.py` | Object detection on PDF pages (vector and raster) and splitting into individual pages. |
| `pdfdruck/overprint.py` | Overprint: find risky overprint settings in the content streams and correct them. |
| `pdfdruck/pageboxes.py` | Set the trim format: trim box (where it is cut) and bleed box (colour beyond the cut) on the pages. |
| `pdfdruck/pagegeom.py` | Page <-> screen without loading the page: a re-implementation of pdfium's CPDF_Page::GetDisplayMatrix. |
| `pdfdruck/pageops.py` | Page operations on the open document (pdfium), no user interface. |
| `pdfdruck/papersizes.py` | Paper sizes in ONE place (mm, portrait) – no Qt. |
| `pdfdruck/pdffunc.py` | PDF functions (ISO 32000 7.10): evaluate them in Python – for the tint transforms of spot colours. |
| `pdfdruck/pdflayers.py` | Layers (optional content) of a PDF |
| `pdfdruck/pdfmanip.py` | Document manipulation: cropping to a target size and CMYK conversion. |
| `pdfdruck/pdfutil.py` | Small helpers for pikepdf objects that several checks share |
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
| `pdfdruck/rasterexport.py` | Export pages as images: PNG, JPG or TIFF. |
| `pdfdruck/renderproc.py` | Render server for the page view: its own process with its own pdfium (pdfium is not thread-safe). |
| `pdfdruck/repair.py` | Repair PDFs and optimize them for sharing. |
| `pdfdruck/roland.py` | Roland cutting plotters (CAMM-1 GS/GS2/GR/GX …) over the network (raw port 9100): loaded material width and direct cut jobs in CAMM-GL III (HP-GL dialect). |
| `pdfdruck/rolls.py` | Rolls of large-format printers and plotters: what is loaded (width, grammage, media, remaining length). |
| `pdfdruck/selftest.py` | Self-test of the finished program file (EXE/AppImage): checks that all bundled dependencies load. |
| `pdfdruck/separations.py` | Output preview: the printing plates of a page (CMYK + spot colours) and the total ink coverage. |
| `pdfdruck/session.py` | Print session (printers, options, colour profile, layout) – no Qt, for the program and the command line. |
| `pdfdruck/shared.py` | Shared print folder for Passermark and all add-on programs (Passermark-GUI, Passerlink, PassCount …). |
| `pdfdruck/shrink.py` | File size: show what takes up the space and reduce it selectively – every measure can be switched separately. |
| `pdfdruck/snmp.py` | Minimal SNMP v2c client (read only) – fallback when a printer does not report its rolls over IPP. |
| `pdfdruck/softmask.py` | Convert transparent gradients (soft masks) into opaque images where needed – without Ghostscript. |
| `pdfdruck/split.py` | Splitting pages: halve a page vertically/horizontally or cut it into a grid – every piece becomes its own page. |
| `pdfdruck/trays.py` | Automatic tray selection: size (+ grammage) -> first matching, non-empty tray. |
| `pdfdruck/updates.py` | Updates from the GitHub releases of Passermark (no Qt – the window shows the state, see gui/updatestatus.py). |
| `pdfdruck/usercolor.py` | Own materials and ICC profiles of the user – no admin rights, no Qt. |
| `pdfdruck/vdp.py` | Variable data |
| `pdfdruck/watch.py` | Drop folders (passermark-cli serve): files dropped into a folder run through a workflow. No Qt. |
| `pdfdruck/winadmin.py` | Admin changes on Windows: counterpart to polkit/pkexec. |
| `pdfdruck/workflow.py` | Workflows: several jobs in a row, described as JSON – the public interface for other programs. |

### User interface (PySide6)

| Module | Purpose |
|---|---|
| `pdfdruck/gui/admindialog.py` | Management of the defaults – saved via pkexec + helper (a single password prompt). |
| `pdfdruck/gui/bleeddialog.py` | Dialog "Anschnitt erzeugen": bleed for customer files without it – mirror or stretch the edges (bleedgen.py). |
| `pdfdruck/gui/colorpanel.py` | Farbe → Farbprüfung: side panel next to the soft proof. |
| `pdfdruck/gui/colorrulesdialog.py` | Dialog "Farbregeln": black text and thin lines -> 100 % K, spot colours (rename, merge, into process colours), cut contours under one name (colorrules.py). |
| `pdfdruck/gui/common.py` | Shared GUI helpers and the session state (kept in memory only). |
| `pdfdruck/gui/comparedialog.py` | Dialog "Compare before/after": the saved file next to the current state, differences marked in red. |
| `pdfdruck/gui/crashui.py` | Error log in the interface: message on unexpected errors, notice after a crash. |
| `pdfdruck/gui/customsizes.py` | Manage custom sizes: name, width, height – stored permanently, for all printers and "Save as PDF". |
| `pdfdruck/gui/datadialog.py` | Dialog "Enter data": create a data table for variable data right inside Passermark. |
| `pdfdruck/gui/docscroll.py` | Scroll bar for the whole document in the single-page view. |
| `pdfdruck/gui/editpanel.py` | Sidebar "Edit": text rows (text, font, size) and layers (on/off, remove, replace, scale/move). |
| `pdfdruck/gui/exportdialog.py` | File → Export as image: format, resolution, pages, colour – the export itself runs as a job in the background (passermark-cli export, rasterexport.py). |
| `pdfdruck/gui/fileopen.py` | Opening files |
| `pdfdruck/gui/findreplacedialog.py` | Dialog "Search and replace text": find rows with a text and replace it (original font). |
| `pdfdruck/gui/hdrdialog.py` | Question for HDR photos (photo + grey gain map): when opening and in the document check. |
| `pdfdruck/gui/iccimport.py` | Admin: obtain color profiles for a printer – sources, link download, file/ZIP/driver package. |
| `pdfdruck/gui/icons.py` | Line icons of the interface. |
| `pdfdruck/gui/jobs.py` | Jobs in the interface: shown in the status bar with progress and cancel. |
| `pdfdruck/gui/lastdir.py` | Last used folder: file dialogs (open, save, export …) start where the user worked last – also after a restart. |
| `pdfdruck/gui/mainactions.py` | Main window: the actions, the menus and the main toolbar. |
| `pdfdruck/gui/maincheck.py` | Main window: the document check in the background, the edit mode, rulers and measuring. |
| `pdfdruck/gui/maincolour.py` | Main window |
| `pdfdruck/gui/maindialogs.py` | Main window |
| `pdfdruck/gui/mainfile.py` | Main window: opening, saving and exporting, and the operations on pages (insert, delete, rotate, move, split). |
| `pdfdruck/gui/mainwindow.py` | Acrobat-like main window: thumbnails on the left, continuous view, toolbar, page operations. |
| `pdfdruck/gui/manipdialog.py` | Document manipulation: control panel (tab in the print dialog + its own dialog) and colour preview. |
| `pdfdruck/gui/mapdialog.py` | Dialog "Map columns": which column of your CSV provides which piece of a QR code with a kind (business card, WLAN …). |
| `pdfdruck/gui/materialsdialog.py` | Farbe → Papiere und Messungen |
| `pdfdruck/gui/materialtab.py` | Materials (papers) |
| `pdfdruck/gui/measuredialog.py` | Determine the paper white of a material: with the measuring device (ArgyllCMS spotread – X-Rite i1Pro, ColorMunki, i1Studio …), from a measurement file (CGATS from i1Profiler/ArgyllCMS, spotread log) or by hand. |
| `pdfdruck/gui/mergedialog.py` | Dialog "Zusammenführen": put files (PDF, images, Office) in order and combine them into one PDF. |
| `pdfdruck/gui/objectsdialog.py` | Dialogs "Separate objects" (individual pages without white space) and "Create CutContour" (cutting plotters). |
| `pdfdruck/gui/outputpanel.py` | Farbe → Ausgabevorschau: side panel for the printing plates of the page and the total ink coverage. |
| `pdfdruck/gui/pageboxdialog.py` | Dialog "Set trim format": final format and bleed – trim and bleed box follow, excess sheet is cut off. |
| `pdfdruck/gui/pagegeometry.py` | Geometry of the document view |
| `pdfdruck/gui/pageinteraction.py` | Mouse in the document view: selecting text, measuring with snapping to edges, edit mode and pipette clicks. |
| `pdfdruck/gui/pageoverlay.py` | What the document view draws on top of the page image |
| `pdfdruck/gui/pagerender.py` | Rendering of the document view |
| `pdfdruck/gui/pageview.py` | The document view: a scroll area with one widget per page. |
| `pdfdruck/gui/pagewidgets.py` | Small widgets of the document view: one page, the rulers, smooth scrolling and the page number field. |
| `pdfdruck/gui/pipettedialog.py` | Colour pipette: small tool window next to the page. |
| `pdfdruck/gui/planbuild.py` | Plan and poster window |
| `pdfdruck/gui/plandialog.py` | Plan & Poster → Plandruck … and Rollen … |
| `pdfdruck/gui/plansetup.py` | Setup dialogs of plan and poster printing |
| `pdfdruck/gui/plantexts.py` | Display texts and small helpers shared by the plan and poster window modules (plandialog, planbuild, plansetup). |
| `pdfdruck/gui/preflightpanel.py` | Sidebar "Check": findings, fonts, layers, transparency – with repairs (result in a new window). |
| `pdfdruck/gui/presetbar.py` | Preset bar for dialogs: pick saved settings, save, delete, share as a file. |
| `pdfdruck/gui/pressdialog.py` | Farbe → Für Druckerei ausgeben … – assistant in four steps |
| `pdfdruck/gui/printbuild.py` | Print dialog |
| `pdfdruck/gui/printdevice.py` | Print dialog |
| `pdfdruck/gui/printdialog.py` | Own print dialog (Acrobat layout): settings on the left, live preview on the right. |
| `pdfdruck/gui/printpreview.py` | Print dialog |
| `pdfdruck/gui/printwidgets.py` | Widgets of the print dialog |
| `pdfdruck/gui/propsdialog.py` | Datei → Eigenschaften: location, file, document, pages, fonts, check. |
| `pdfdruck/gui/renderclient.py` | Page rendering in the background: one render process for the whole program (see renderproc.py). |
| `pdfdruck/gui/repairdialog.py` | Dialog: repair PDFs, optimize for sharing, set/remove password protection. |
| `pdfdruck/gui/settingsdialog.py` | File → Settings: the user's personal settings (currently: language). |
| `pdfdruck/gui/shrinkdialog.py` | Reduce file size: breakdown of the file size and every measure on/off separately. |
| `pdfdruck/gui/sidebarwin.py` | The sidebar as its own window (1.20.1). |
| `pdfdruck/gui/sidepanels.py` | Parts of the 1.19.0 main window at its edges |
| `pdfdruck/gui/softproofdialog.py` | Set up the soft proof of the page view: printing condition (material or profile), intent, paper white, black, warnings. |
| `pdfdruck/gui/splitdialog.py` | Dialog "Split pages": halve or grid, which pages, order – with a preview of the cut lines. |
| `pdfdruck/gui/stallwatch.py` | Stall log: notices when the interface hangs and records what the main window is doing at that moment. |
| `pdfdruck/gui/tabhost.py` | Window frame with tabs: every document is a full Passermark window (menus, bars, sidebars) – here as a tab. |
| `pdfdruck/gui/theme.py` | Dark theme in Hias' colours (1.19.0: blue accent #007DAF, black/#272727 surfaces) + global mouse wheel guard. |
| `pdfdruck/gui/thumbs.py` | Thumbnails of the pages in the side bar: list, drawing of an entry, loading in the background. |
| `pdfdruck/gui/titlebar.py` | Own title bar (1.19.0 design) |
| `pdfdruck/gui/updatestatus.py` | Update state in the status bar of every window, the update dialog and applying an update (pdfdruck/updates.py). |
| `pdfdruck/gui/vdpdialog.py` | Dialog "Variable data": create fields and place them with the mouse, CSV data source, numbering, preview of any record. |
| `pdfdruck/gui/viewlayout.py` | View modes of the document view: how the pages are arranged in the scroll area. |
<!-- modules:end -->
