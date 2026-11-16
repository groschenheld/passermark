# Passermark – features and code guide

State: version 1.19.7 (November 2026). Written for a reader who wants to understand the program as a whole –
what it does for the user and how the code is built – before reviewing or changing it.

How this fits with the other documents:

| Document | Content |
|---|---|
| this guide | features, walkthroughs through the code, conventions, where to start reading |
| [architecture.md](architecture.md) | the map: layers, processes, files on disk, error handling, generated module reference |
| [cli-api.md](cli-api.md) | the command line and workflow interface (stable JSON, error codes) |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | how to report bugs, code style, pull requests, translations |
| [translating.md](translating.md) | translating the interface with a spreadsheet |
| READMEs | user-facing feature list and installation |

The interface is German (the source language of all user-visible text); English, Hungarian, Spanish and French
translations exist. Menu names below are given in German as they appear in the program, with the meaning in
English where it is not obvious. A short glossary of prepress terms is at the end.

---

## Part 1 – What the program does

### 1.1 In short

Passermark is a PDF viewer, print tool and prepress toolbox for Linux and Windows, written in Python with
PySide6 (Qt 6). It grew out of daily work in a print shop: open whatever a customer sends, check it, fix it,
impose it and print it on office, production and large-format devices – with the drivers that are already
installed. Every heavy function also runs without the interface (`passermark-cli`), so it can be automated
through workflows and drop folders. Licence: GPL-3.0-or-later.

Three add-on programs (Passermark-GUI, Passerlink, PassCount; separate repositories, not free software) talk
to Passermark only through the command line and the shared print folder.

### 1.2 The main window

Since 1.19 the window follows a design sheet by the author:

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ ⚙ Datei Seiten Dokument Ansicht Verwaltung Hilfe     PasserMark     – □ ×          │  title row
├─────────────────────────────────────────────────────────────────────────────────────┤
│ Drucken Öffnen Speichern │ ◀ [3/19] ▶ ≋ │ ▭ ✚ ⌖ ┃ ◐ │ ↺ ↻ ▯ ▯▯ │ − [100 %] + ↔ ⤢      │  toolbar
├────────────┬──┬──────────────────────────────────────────────────────┬──────┐       │
│ Seiten     │  │                                                      │ Werk-│ ┌───┐ │
│ (thumbnails│▐ │                    page view                         │ zeuge│ │ W │ │  tabs in the
│  or check, │  │                                                      │ panel│ │ P │ │  transparent
│  colour,   │  │ ┌────┐                                               │      │ │ P │ │  margin
│  edit)     │  │ │box │ merge / split / edit (folds away)             │      │ └───┘ │
├────────────┴──┴─┴────┴───────────────────────────────────────────────┴──────┘       │
│ ✓ Prüfung OK   Seite 3/19   210 × 297 mm                       ⟳ Alles aktuell      │  status bar
└─────────────────────────────────────────────────────────────────────────────────────┘
```

- **Title row** – gear (settings), the menu bar, the document name, the word mark and the window buttons. The
  window is frameless and resized at the edges of the page area or with the grip in the bottom right corner.
  File → Settings → Fenster switches back to the system frame.
- **Toolbar** in groups separated by space: print/open/save; page navigation with a page number field and the
  switch *Sanft scrollen* (smooth/continuous scrolling vs. page by page); tools on the page (trim and bleed
  boxes, colour pipette, measuring, rulers, soft proof); rotate the view and one page / several pages (the arrow
  beside it offers facing pages and grids of 2–4 columns); zoom.
- **Left sidebar** with tabs: *Seiten* (thumbnails with the page context menu), *Prüfung* (preflight findings),
  *Farbe* (colour check), *Bearbeiten* (edit mode). The strip between sidebar and page has the button that
  collapses the whole sidebar. Narrow panels wrap their texts and tabs instead of cutting them off.
- **Page view** – single page, continuous, facing pages (with the cover alone) or grid. Rulers in mm, measuring
  with snapping, trim/bleed overlay, soft proof.
- **Tool box** over the bottom left of the page: merge, split, edit; an arrow folds it to a strip.
- **Tabs at the right edge**: *Werkzeuge* opens the tools panel (colour and materials, cutting/separating/
  contours, variable data, document and check – every tool as a button, with a short explanation per group),
  *Plan* and *Poster* open their windows. With the own title bar the tabs stand outside the page area in a
  transparent margin of the window.
- **Status bar**: result of the automatic document check (green/yellow/red, click opens it), page, page size,
  progress of background jobs, update state (click on the symbol checks again).
- **Tabs for documents**: optionally every opened document becomes a tab in the same window; a tab can be
  detached into its own window.

### 1.3 Menus

| Menu | Content (shortcuts in brackets) |
|---|---|
| **Datei** (file) | Öffnen (Ctrl+O), new window, new tab, detach tab · Speichern (Ctrl+S), Speichern unter (Ctrl+Shift+S) · Eigenschaften (Ctrl+D: location, file, document, pages, fonts, check) · Drucken (Ctrl+P) · Einstellungen (Ctrl+,) · Schließen |
| **Seiten** (pages; also the context menu of the thumbnails) | insert pages before/after the selection or at the end, insert blank pages · export the selection as one PDF (Ctrl+E) or as single PDFs · rotate pages permanently, move them forward/back (Alt+↑/↓) · split pages (halves, grid), split spreads · delete (Del) · select all · copy marked text, select the page text |
| **Dokument** (document) | merge documents (Ctrl+M) · repair, optimise, password (Ctrl+Shift+R) · reduce file size · document check (Ctrl+Shift+P) · submenus below |
| ↳ **Dokument-Manipulation** | edit text and layers (Ctrl+T) · CMYK conversion · crop to format · CMYK and crop in one step (Ctrl+Shift+M) · separate objects (single pages without white space) · CutContour for cutting plotters · variable data (Ctrl+Shift+D) · enter data (tables for business cards, Wi-Fi, codes) |
| ↳ **Farbe** (colour) | colour check (Ctrl+Shift+F) · colour pipette (Ctrl+Shift+C) · soft proof on/off (Ctrl+Y) and set up (Ctrl+Shift+Y) · output for the print shop · CMYK conversion · papers and measurements · get standard profiles · colour management explained |
| ↳ **Plan & Poster** | plan printing (Ctrl+Alt+P) · poster printing · last prints (history) · rolls of the printers |
| **Ansicht** (view) | page arrangement · rulers (Ctrl+R) · measure (Ctrl+Shift+L) · trim and bleed (Ctrl+Shift+B) · soft proof · sidebar · whole page (Ctrl+1), page width (Ctrl+2), actual size (Ctrl+0) · rotate view |
| **Verwaltung** (administration) | admin defaults (password prompt) · open the preset folder |
| **Hilfe** (help) | command line guide and variable data guide (PDF) · get examples · Windows print test (Windows only) · open error logs · check for updates · licences |

Home/End jump to the first/last page; Ctrl+4…7 switch the page arrangement.

### 1.4 Feature areas

**Opening and viewing.** PDFs, images (also HEIC and SVG) at their real size, Office files via LibreOffice,
OnlyOffice or Euro-Office (`convert.py`, `images.py`). Pages are rendered in a separate process; zooming
re-renders sharply, large pages are smoothed in the background. A document is checked automatically after
opening (can be switched off).

**Page operations** (`pageops.py`, `gui/mainfile.py`): insert, blank pages, export, rotate, move, delete,
split into halves or a grid (`split.py`, lossless – content is not rasterised).

**Printing** – own print dialog with a live preview (`gui/printdialog.py` and the `print*.py` parts):
printer and tray chosen automatically from size and grammage, material, duplex, colour, the driver's own
options (finisher, stapling, folding – with German names for common English driver options, `i18n.py`),
borderless, mirroring, page order, presets and admin defaults. Page handling: scaling, N-up, booklets (saddle
stitch, signatures, perfect binding, creep), poster tiling with overlap and glue lines, step & repeat with marks
and a second step onto a target sheet. Output profile and rendering intent; save as a new PDF instead of
printing. Every print can be logged with its exact settings and reprinted from the log.

**Plan & Poster** (large-format roll printers, own windows `gui/plandialog.py` and parts): print area from the
outer lines of a plan, roll choice (narrowest fitting roll, by grammage/material, or fixed), running metres
per roll with a warning before a roll runs short, scaling, rotation, fold marks to DIN 824, hairline lifting;
posters side by side, wider than the roll in panels, hem, eyelets, registration marks and CutContour for print
& cut on Roland plotters. Rolls are read from the device (IPP, otherwise SNMP) or entered by hand; materials
per user with a colour path. History of the last 50 prints.

**Prepress check** (`preflight.py`, sidebar *Prüfung*): fonts (embedded, subset, Type 3 …), layers,
transparency, page boxes and bleed, protection, PDF/X and output intent, form fields, empty pages, page size
against the default printer, images (resolution, colour space – `imagecheck.py`). Every finding names its
position and can be jumped to; targeted repairs: embed or substitute fonts (also download free fonts), outline
text, fix/remove layers, flatten transparency.

**Colour** (`colorcheck.py`, `cmyk.py`, `colorconv.py`, `proof.py`, `pipette.py`, `colorlab.py`): colour check
against a printing condition with findings and fixes; soft proof in the view (paper white, black ink, gamut and
ink coverage warnings); colour pipette (what is in the PDF at a point and what the printer will put down per
channel); output for the print shop in four steps with the profile always embedded as output intent; own
materials with paper white measured by an X-Rite device through ArgyllCMS, from a measurement file or by hand;
download of standard profiles.

**Document manipulation**: CMYK conversion with preview, crop to format (also "trim edges" and "remove white
space"), separate objects onto pages of their own (`objects.py`), CutContour with generated bleed for cutting
plotters (`cutcontour.py`), reduce file size measure by measure (`shrink.py`), repair/optimise/password
(`repair.py`), merge files of any kind.

**Edit mode** (sidebar *Bearbeiten*, `editing.py`, `editops.py`): change text lines (text, font, size), move,
scale, hide, remove or replace layers and objects with snapping, grid and arrow keys; undo.

**Variable data** (`vdp.py`, `datakinds.py`, dialogs `vdpdialog.py`, `datadialog.py`, `mapdialog.py`):
numbering, text from CSV, QR codes, Code 128, EAN-13 as vectors, image fields, placeholders `{{…}}` in the
PDF, several pages per record, page groups for multi-page templates, step & repeat with a different record per
copy, a data check before generating. "Daten erfassen" builds the table inside the program for typical kinds
(vCard, Wi-Fi, e-mail, event …).

**Automation**: presets (named settings per job), workflows (several jobs in a row with conditions and
variables, JSON), drop folders (`passermark-cli serve`), the shared print folder `/srv/passermark` for all
add-on programs, the print log. See [cli-api.md](cli-api.md).

**Settings and administration.** Personal settings (`gui/settingsdialog.py`): language, check on opening,
print log, error logs, documents as tabs, own title bar, Windows print path. Admin defaults
(`gui/admindialog.py`, written by a root helper after one password prompt): general (incl. updates), printer
defaults, finisher templates, colour management, tray assignment, colour profiles per printer, materials.

**Updates** (`updates.py`, `gui/updatestatus.py`): check against the GitHub releases (stable or test channel),
download with checksum, apply per installation type (AppImage swaps itself, Windows setup runs silently, an
install.sh installation is reinstalled by the root helper from the source package).

**Error logs** (`crashlog.py`, `gui/crashui.py`, `gui/stallwatch.py`): every error and every hang of the
interface ends up in a log file that can be sent along; after a crash the next start points to it.

### 1.5 Starting it

```
passermark [FILES …]            open (several files: one window, or tabs)
passermark --plan / --poster    plan or poster window, optionally with files
passermark --merge FILES        merge dialog
passermark --repair FILES       repair dialog
passermark --print FILES        print without a dialog
passermark --selftest           check that all bundled dependencies load (built program)
passermark-cli …                command line, see cli-api.md
```

Only one instance runs per user; a second start hands its files to it.

---

## Part 2 – How the code works

### 2.1 Repository layout

| Path | Content |
|---|---|
| `pdfdruck/` | the program (package name from the early days). About 70 modules without Qt, ~34 000 lines |
| `pdfdruck/gui/` | the interface (PySide6), about 60 modules, ~28 000 lines, plus `svgicons/` and `fonts/` |
| `pdfdruck/lang/` | translations, one dict per language (`en.py`, `hu.py`, `es.py`, `fr.py`) |
| `admin/` | `passermark-admin`: the Linux root helper (called through pkexec) |
| `data/` | desktop file, program symbol, polkit policy, Nautilus extension, example admin configuration |
| `linux/`, `windows/` | AppImage build, PyInstaller specs, Inno Setup script, Windows build script, drop-folder service/task |
| `docs/` | this guide, architecture, CLI interface, generators for the PDF guides, screenshots |
| `tests/` | ~70 test files, each runnable on its own; `_qtstub/` is a stand-in for Qt |
| `tools/` | module overview generator, third-party licence collector |
| `.github/workflows/` | Linux (tests, ruff, AppImage, release) and Windows (tests, installer, release) |
| `install.sh`, `uninstall.sh` | system installation on Debian/Ubuntu |

Main dependencies: PySide6 ≥ 6.5, pypdfium2 (rendering, page operations), pikepdf (reading and writing PDF
structure), Pillow (+ pillow-heif), numpy, scipy, contourpy (contours), img2pdf, reportlab (vector text and
codes for variable data), pycups (Linux) or pywin32 (Windows). External programs: Ghostscript (separation,
colour conversion, soft proof; bundled in the installer and AppImage), optionally LibreOffice, 7-Zip, ArgyllCMS,
rsvg-convert/Inkscape.

### 2.2 The big picture

Read [architecture.md](architecture.md) for the layer diagram. The three ideas that explain most of the code:

1. **Jobs.** Every heavy function is a *job*: input PDF + a settings dataclass → output PDF, without Qt.
   `core.JOBS` registers ten of them (`impose`, `vdp`, `cutcontour`, `manip`, `repair`, `preflight_fix`,
   `separate`, `split`, `shrink`, `press`); workflows add the steps `print` and `plan`, which print and leave
   the PDF unchanged. The same job runs from a dialog, the command line, a workflow or a drop folder – with the
   same settings, which serialise to JSON (`core.settings_from_dict` / `settings_to_dict`).
2. **Layers.** A module imports only from its own layer or below. Everything outside `pdfdruck/gui/` and
   `app.py` runs without Qt, which is what makes the command line and most tests possible.
3. **Processes.** pdfium is not thread-safe and heavy work must not freeze the interface, so page rendering
   runs in one render process for the whole program, and long jobs run as `passermark-cli` child processes.
   Admin changes go through a root helper with validated input.

### 2.3 Walkthroughs

**Opening a file and seeing a page**

```
__main__.py            parse arguments; hand over to a running instance (fastipc.py) or start
app.Controller         admin config (config.py), print Session (session.py), single instance server
gui/tabhost.TabHost    the top-level window (frame, tabs, transparent margin)
gui/mainwindow         one MainWindow per document – built from mixins (see 2.4)
gui/fileopen.py        PDF / image / Office → PDF bytes (convert.py, images.py)
gui/pageview.PageView  one widget per page; viewlayout.ViewMode arranges them
gui/renderclient.py    request "page i at scale s" → renderproc.py (own process, own pdfium)
gui/pagewidgets.py     paints the image; smoothing of large pages in a worker thread
gui/maincheck.py       starts the document check in the background → status bar chip
```

**Running a job from a dialog** (e.g. CutContour)

```
gui/objectsdialog.py   builds CutContourSettings from the controls (presets via gui/presetbar.py)
gui/maindialogs.py     start_job(): hands kind + settings to a background job
jobproc.py             writes the settings to a temporary preset and starts
                       `passermark-cli cutcontour in.pdf out.pdf --preset tmp.json --json-progress`
cli.py → core.run_job  the job module (cutcontour.py) does the work, reports progress as JSON lines
gui/jobs.py            progress and cancel in the status bar
gui/maindialogs.py     _open_result_path(): the result opens in a new window or tab
```

**Printing**

```
gui/printdialog.py     PrintSettings + LayoutSettings from the dialog, live preview (gui/printpreview.py)
layout.py              page selection, scaling, N-up, booklet, step & repeat → temporary PDF
printjob.py            colour conversion (colorconv.py), tray choice (trays.py), driver options via roles
printers.py / printers_win.py   CUPS / Windows GDI
printlog.py            one JSON record per job (reprint, PassCount)
```

`printers.PrinterCaps` maps Passermark's own terms (*roles*: `pagesize`, `source`, `media`, `duplex`, `color`,
`quality` …) to whatever a driver calls them; code above that layer never uses driver keywords.

**An update**

```
gui/updatestatus.UpdateController   at start (at most once a day), from Help, or a click on the symbol
updates.check / newest              GitHub releases API, version compare, channel (stable/test)
updates.download                    asset for this installation type + its .sha256, verified
apply                               AppImage: replace file · Windows: Setup.exe /VERYSILENT /AUTOUPDATE ·
                                    install.sh: pkexec passermark-admin update (fetches the checksum itself)
```

### 2.4 The interface code

- **Big windows are classes assembled from mixins.** `MainWindow` combines `mainactions` (actions, menus,
  toolbar), `mainfile` (open/save/page operations), `maincheck` (check, edit mode, rulers, measuring),
  `maincolour` (soft proof, colour panel, pipette) and `maindialogs` (opening the dialogs). The print dialog
  (`print*.py`) and the plan window (`plan*.py`) are built the same way. The parts share the window's
  attributes – a known rough edge (see 2.8).
- **The page view** is split by topic: `pageview` (scroll area, pages, zoom, navigation), `pagegeometry`
  (page ↔ screen), `pageinteraction` (mouse), `pageoverlay` (what is drawn on top), `pagerender`
  (requests to the render process), `pagewidgets` (page widget, rulers, smoother), `viewlayout` (the page
  arrangement as its own object: `SinglePage`, `Continuous`, `Facing`, `Grid` – a new mode is one class),
  `docscroll` (the document scroll bar of the single-page view).
- **Window frame and edges**: `tabhost` (frameless, translucent window with a mask; places the tabs of the
  current document in the right margin), `titlebar` (title row, edge grips), `sidepanels` (tabs, tools panel,
  tool box), `updatestatus`.
- **Look**: all colours in `theme.py` (palette, the Qt style sheet, image files the style sheet needs);
  icons from `svgicons/` through `icons.py` (drawn with `currentColor`, coloured per state); fonts from
  `fonts/` (Inter, JetBrains Mono) loaded at start.
- **Narrow panels**: `common.responsive` turns rows of buttons into wrapping rows;
  `common.responsive_panel` (side panels) also breaks button texts into lines, wraps tab bars into rows and
  wraps text in lists and tables.
- **Text**: every user-visible string is German inside `tr("…")`; `tests/test_l10n.py` fails if a
  translation is missing. Translations by others come in as a filled-in table (`langpack.py`,
  [translating.md](translating.md)).

### 2.5 Configuration and files

Two kinds of settings: **admin defaults** (`config.py`, `/etc/passermark/defaults.json` or ProgramData;
validated by `cfgvalidate.py`, written only by the root helper) and **user settings** (`l10n.py`,
`~/.config/passermark/settings.json` or `%APPDATA%\Passermark`). Presets, materials, ICC profiles, logs and the
shared folder are listed in architecture.md → *Files on disk*.

### 2.6 Errors

A broken PDF or a driver quirk must never take the interface down, so errors are caught widely – but none
disappears silently: each `except Exception` shows the error, logs it (`log.warning(..., exc_info=True)` into
the error log) or states in a comment why it is expected. ruff rule BLE001 enforces this. Details in
architecture.md → *Error handling*.

### 2.7 Tests, style, build

- **Tests**: `python3 tests/test_<name>.py`, no test framework. To run all:
  `for f in tests/test_*.py; do python3 "$f" > /dev/null || echo "FAIL $f"; done`.
  GUI tests use the Qt stand-in in `tests/_qtstub`: they check wiring and logic, not what appears on screen;
  every real-Qt change is checked by hand with screenshots.
- **Style**: `ruff format` (120 columns) and `ruff check` (rules E, W, F, B, UP, SIM, BLE), both enforced in
  CI. Comments and docstrings English, user text German, log messages German.
- **Build**: PyInstaller for the AppImage (`linux/build-appimage.sh`) and Windows (`windows/build.ps1`,
  Inno Setup). Pushing a tag `vX.Y.Z` makes the workflows publish AppImage, Setup.exe and a source package, each
  with a `.sha256` – the update function relies on them.
- **Delivery**: changes are developed outside the repository and committed by the author himself; the version
  is in `pdfdruck/__init__.py`.

### 2.8 Known gaps and rough edges

From architecture.md and the test notes, so they are not mistaken for intent:

- Mixins share window state freely; separating them into own objects is planned where the redesign touches
  them anyway.
- A few imports go against the layer rule (done inside functions to avoid cycles); many imports inside
  functions are historical rather than deliberate.
- Many `except Exception` could catch narrower types.
- `LayoutSettings` / `ManipSettings` still have hand-written `from_dict` / `to_dict`.
- The CI runs a hand-picked list of test files, not all of them; newer ones (e.g. `test_updates.py`,
  `test_viewlayout.py`, `test_panels.py`) only run locally.
- No real-Qt tests (offscreen); Ghostscript-based checks are tested with stand-ins outside CI; printing is
  tested against fake printers.

### 2.9 Where to start reading

For a review, this order gives the most understanding per hour:

1. `core.py` and one small job end to end: `split.py` (short) or `cutcontour.py` (typical).
2. `cli.py` and `workflow.py` – the public interface.
3. `layout.py` → `printjob.py` → `printers.py` – the print path and the role idea.
4. `app.py`, `gui/mainwindow.py` and `gui/mainactions.py` – how the interface is put together.
5. `gui/pageview.py` with `gui/viewlayout.py` and `gui/renderclient.py` / `renderproc.py` – the view.
6. `preflight.py` – the largest piece of domain logic.

---

## Glossary

| German (in the program) | Meaning |
|---|---|
| Anschnitt | bleed – image area beyond the trim that is cut off |
| Endformat | trim size, final format after cutting |
| Passermarken | registration marks |
| Schnittmarken / Falzmarken | crop marks / fold marks |
| Nutzen, Step & Repeat | copies of one item on a sheet |
| Ausschießen | imposition |
| Broschüre, Rückendrahtheftung, Klebebindung, Bundzuwachs | booklet, saddle stitch, perfect binding, creep |
| Druckbedingung, Ausgabeprofil, Output Intent | printing condition, output (ICC) profile, embedded target profile |
| Farbauftrag | total ink coverage |
| Papierweiß | paper white (measured colour of the paper) |
| Softproof | on-screen simulation of the print |
| Dokumentprüfung (Preflight) | checking a file for print readiness |
| Rolle, Laufmeter | roll, running metres used on a roll |
| Plandruck / Posterdruck | printing building plans / posters on roll printers |
| CutContour | named spot colour that a cutting plotter follows |
| Fach, Fachwahl | tray, tray selection |
| Druckprotokoll | print log |
| Ablauf, Hotfolder / Überwachungsordner | workflow, drop folder |
| Verwaltung | administration (admin defaults) |
