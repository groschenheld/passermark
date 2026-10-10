# Changelog – Passermark

**English** · [Deutsch](CHANGELOG.de.md) · [Magyar](CHANGELOG.hu.md) · [Français](CHANGELOG.fr.md) · [Español](CHANGELOG.es.md)

## 1.10.8

- Internationalised the source-code documentation: translated all comments and
  docstrings across the entire codebase (GUI, language packs, pdfdruck data
  package, tests, platform scripts) from German to English; the GPL license
  headers as well.
- Added the missing "pdfdruck" data package (fixes the broken build).
- No functional changes: strings, logic and behaviour are unchanged
  (verified against the previous release via AST comparison).

## 1.10.7

- **CutContour: basic shapes without computation.** New placement "On the trim size (without computation)":
  rectangle, rounded rectangle, circle … are placed directly onto the trim size (TrimBox, otherwise the page) –
  no rendering, no motif detection, no worker processes, in a fraction of a second. Spacing, size, offset and
  dragging with the mouse work as before. Computation only happens for "Contour" or when the shape is placed
  around the motif or per object. Command line: `--set fit=trim`
- **CutContour default:** rectangle on the trim size (unless custom recently used settings are saved)

## 1.10.6

- Windows fix: CutContour got stuck at 0 % (since 1.10.5). The switch of the command-line output to UTF-8 has
  been reverted; the fix for "Split pages" remains (progress messages as plain ASCII)
- CutContour: no more error when closing the window while a preview computation is still finishing
  ("expected LP_struct_fpdf_document_t … NoneType")

## 1.10.5

- Windows fix: "Split pages" (and any job whose message contains characters such as "→") aborted with
  UnicodeEncodeError … cp1252. The command line now switches its own output to UTF-8; the progress messages
  sent to the UI are plain ASCII
- SECURITY.md, CONTRIBUTING.md and GitHub templates for bug reports and suggestions included in the package

## 1.10.4

- README bilingual: README.md (English) and README.de.md (German), brought up to date (split pages, variable
  data, data capture, all command-line jobs) and with a note on the project status
- Example configuration data/defaults.example.json with neutral printer names

## 1.10.3

- Split pages via right-click: select pages in the page sidebar → right-click → Split → "Halve vertically" /
  "Halve horizontally" – immediate, only the selected pages, no comparison page needed. "Grid / more options …"
  opens the dialog with the selection preset

## 1.10.2

- Variable data – front and back: new "Pages per record" (under 2.): 2 = page 1+2 → record 1, 3+4 → record 2 …
  – regardless of whether the template has 2 pages or already all cards (e.g. 200 pages for 100 business cards).
  The "Only on these pages" fields now know odd and even, also combined with ranges ("odd 1-50").
  Example 7: business card with name on the front and QR business card on the back
- More variables: {{datum}}, {{zeit}}, {{jahr}}, {{monat}}, {{tag}}, {{wochentag}}, {{kw}}, {{datum_iso}},
  {{datum:FORMAT}}, {{seite}}, {{seiten}}, {{vorlagenseite}}, {{datensatz}}, {{datensaetze}}, {{datei}},
  {{zufall}}, {{zufall:N}}, {{code:N}}, {{uuid}}. The ? button next to the content shows all of them with a
  sample value; double-click inserts one. CSV columns of the same name take precedence
- Double-clicking a column replaces an unchanged {{nr}} instead of leaving it in place
- Split pages (Pages → Split pages …, Edit workspace): halve vertically/horizontally or a grid, all/selected
  pages or a range, facing pages only, order right→left; with a preview of the cut lines. Split facing pages
  with one click for incorrectly exported brochures. Lossless (content is not copied or rasterised), rotated
  pages as you see them; with a trim size, the cut happens inside it and the bleed stays outside.
  Command line: job split
- Page sidebar: the thumbnails rotate along with "Rotate view left/right"
- Fixed: opening from outside landed in a locked window (Windows, double-click/right-click, while a tool is
  open in another window) – now a separate window. Cause: opening in the empty start window left behind an
  invisible empty tab; the empty window is now used itself. Results from a locked window also open in a
  separate window

## 1.10.1

- Use your own CSV with different column names directly: Variable data → Open CSV recognises what the table
  fits ("The table fits: QR – business card"); Create matching field creates the QR code with that type.
  Columns are assigned automatically – including English, Hungarian, Spanish, French names and the headers of
  the contact exports from Outlook, Google and Thunderbird. The CSV remains unchanged
- Assign columns … in the QR field with a type: choose the column per item, "leave empty" or automatic; with a
  preview of the finished content. Below the type it says what comes from where and what is missing. The
  assignment is saved in the preset (qr_map) and also applies on the command line
- Data capture: a CSV with foreign column names no longer gets duplicate columns; the header shows the
  assignment ("First Name → Vorname"). datencheck also recognises foreign column names
- Example folder: kontakte-outlook.csv (this is what an Outlook export looks like); guide extended with
  "Your own CSV with different column names"

## 1.10.0

- Data capture (Variable data workspace, Document manipulation menu, or in the Variable data dialog under 2.):
  create the data table directly in Passermark. The matching columns per type – QR business card (vCard),
  WLAN access, e-mail, web address, call, SMS, appointment, location, free QR text, Code 128, EAN-13, text
  with your own columns. Every row is validated immediately (required fields, EAN check digit, umlauts in
  Code 128, date …); on the right, the finished code of the selected row. Paste from Excel with Ctrl+V,
  duplicate rows, fill a column with a number series (also creates the rows), custom columns. Save as CSV
  (UTF-8 with BOM, semicolon – Excel reads umlauts correctly)
- "Use in variable data" takes the table as the data source and creates the matching field
- QR field "Type of QR code": content as entered or composed from the table columns (vCard, WLAN, mailto, tel,
  SMS, appointment, geo). The CSV stays readable; Passermark builds the code content on generation
- Quiet zone: QR code and Code 128 now have a white margin in the field (can be disabled). Without it, codes
  close to other content were hard to read. Existing presets: the QR code becomes slightly smaller in the field
- EAN-13 with 13 digits and a wrong check digit is now an error (with the correct number in the message) –
  previously the last digit was silently replaced
- Command line: datenarten, datenvorlage <type> [file.csv], datencheck <file.csv> [type] (returns 1 on
  problems); in the preset qr_type per QR field
- Examples 5 (business card from a contact list) and 6 (WLAN access); "Variable data" guide with the new
  section "Data capture", CLI guide extended
- Tests now actually read back the generated codes: QR and EAN-13 with OpenCV (if installed), Code 128 with
  its own reader including checksum
- Fixed: without a distribution selection, variable data used "the whole document per record" instead of
  "each page the next record"

## 1.9.5

- Variable data examples in the program: template, CSV, 4 presets (QR with number, QR from CSV, Code 128,
  EAN-13) and finished result PDFs are included in the program package. Help → Get variable data examples …
  (also in the Variable data workspace) copies them to ~/Passermark-Beispiele/vdp, registers the presets
  "Beispiel 1" to "Beispiel 4" with the full CSV path and opens the template
- New guide "Variable data" (PDF) for the UI and the command line, with all four examples step by step:
  Help → Variable data – guide (PDF)
- Command line: passermark-cli beispiele [folder]; a relative csv_path in a preset is also searched next to
  the preset file
- CLI guide: VDP texts brought up to date (each page the next record, workspace)
- Windows/Linux build: the whole pdfdruck/docs folder is included

## 1.9.4

- Fixed: Code 128 – plain-text line distorted. The readable line under the barcode was stretched with the
  bars to the field size; now it sits below in the configured font size
- Example package "passermark-vdp-beispiele": template, CSV, presets and finished PDFs for QR code, Code 128
  and EAN-13

## 1.9.3

- Fixed: variable data put the same values on every page (number 1, same name, {{i}} = 1) – one record always
  applied to a copy of the whole document. New and default: each page gets the next record (page 1 → record 1,
  page 2 → 2 …; for a one-page template, one page per record). The previous distribution remains available as
  "One copy of the whole document per record" (e.g. front and back of a card). The choice is now the first
  question under "2. Where do the data come from?"
- Without a CSV, the count at the start is the document's page count; page and record in the preview are
  linked (page 3 shows record 3)

## 1.9.2

- Variable data made easier to understand: every setting with a heading and a short explanation above it,
  groups in the order of work (1. fields, 2. data, 3. numbering, 4. output), quick guide at the top;
  position/size, counting with labelled individual fields (left, top, width, height – first number, step,
  digits); indicator showing where a counter currently stands for continued counting; CSV "Remove"
- Reset everything (button at the top): one text field with the number, no CSV, numbering from 1
- Variable data now remember the last settings only until the program ends – after a restart the dialog starts
  fresh. To keep them permanently: save as a preset
- A new EAN-13 field starts with a valid sample number instead of {{nr}}

## 1.9.1

- Windows with many options are no longer cut off: Variable data, CutContour, Separate objects and the print
  dialog have a movable divider between preview and settings; the settings area scrolls vertically and – if
  narrower than its content – also horizontally. The same in CMYK/Crop and in the admin dialog. Dialogs are
  never opened larger than the screen
- Variable data: button "Open CSV …" (was cut off in narrow windows – only the code log's save button
  remained visible, now "Save as …"); Enter in an input field no longer accidentally starts "Generate"

## 1.9.0

- Variable data (Document manipulation → Variable data …, Ctrl+Shift+D; its own workspace): place fields on the
  template and position them with the mouse – text, QR code, Code 128, EAN-13, all as vector. Content as a
  template: {{column}} from a CSV file, {{nr}} (number), {{i}} (running index). Font, size, colour, alignment,
  rotation, only on specific pages. Preview with the real result for every record. Result as a new tab
- Numbering: start, step, digits (with zeros), prefix/suffix, check digit (Luhn, GS1/EAN, Mod 11), backwards
  for tear-off pads, continued counting across jobs (counter name)
- CSV: delimiter and character set (UTF-8/Windows) are detected; insert columns with a double-click; record
  range; order all pages per record or all records per page
- Placeholders {{…}} in the PDF (e.g. from InDesign) are taken over as field positions, the placeholder text
  removed
- Code log as CSV (output page, record, all values)
- Use with an individual record per instance: print dialog → Instances → "The next page per instance", order
  sheet by sheet or cut and stack (each stack continuous)
- Command line: job vdp (fields most conveniently as a preset from the program), impose with sr_sequence and
  sr_stack; guide with worked examples
- The template's trim size/bleed is preserved for variable data (for imposition afterwards)
- New dependency: reportlab (text, QR and barcodes as vector) – included in the setup and AppImage

## 1.8.5

- Custom sizes in the print dialog: next to "Paper size" the button Custom sizes … – create or delete a name,
  width × height in mm. The sizes stay saved and are available for all printers and for "Save as PDF" (marked
  with ★). They are spooled as a custom size: CUPS PageSize/media = Custom.BxHmm, Windows custom paper
  (DMPAPER_USER with width/length). Whether a device accepts the size is up to its driver; the print margins
  are taken from the printer's default format
- Print presets with a custom size remember the dimensions (for passermark-cli impose: sheet=custom)

## 1.8.4

- Fixed: crash message after closing a window/tab ("expected LP_struct_fpdf_document …" in the page view) –
  the view no longer accesses the closed document
- CutContour circle: side handles scale uniformly (previously briefly an oval, then it snapped back; the
  fields stayed e.g. at 60 × 120). For the circle there is now only one diameter (height follows width)
- CutContour: the ↺ button next to "Size" resets size and position (automatic from the motif, centred)
- Crop to format: new "Trim white margin first" (mm, command line crop_inset_mm) – the template is first
  shrunk on all sides by this value, then scaled and cropped as configured

## 1.8.3

- Fixed: the instance layout "filler against filler" left gaps between objects – for individual objects from
  CutContour or "Separate objects", the whole page including the white margin was placed. These pages now
  carry their trim size: CutContour = cut line (bleed = filler), Separate objects = object (bleed = margin).
  In imposition, the fillers lie against each other
- Instance layout "filler against filler" with 0 bleed: the bleed from the document (BleedBox) is taken over
  – a configured value takes precedence. "With spacing" 0 places the trim sizes (cut lines) directly against
  each other

## 1.8.2

- Dialogs now lock only their own window: print dialog, CutContour, CMYK … open – in the other Passermark
  windows you can keep browsing, zooming, working. (Tabs in the same window belong to the window and stay
  locked meanwhile; "Open in own window" detaches a tab.)
- Booklet: "Sheets per section" is always adjustable; changing the number automatically enables "Grouped
  sections" (with saddle stitching the number otherwise had no effect). Added a test for 24 pages with
  3 sheets per section

## 1.8.1

- Tabs: whatever is created or opened in the program becomes a tab in the same window – the open button with
  a document open, drag-and-drop, results (CutContour, CMYK/Crop, Separate objects …), "Open in Passermark
  now" after "Save as PDF", help guides. Starting the program without a file and double-click/"Open with" in
  the file manager still open a standalone window. Every tab is a complete window with its own menus, bars
  and sidebars; with only one document the tab bar is hidden
- Tabs: move by dragging, close with ×, right-click → "Open in own window" / "Close others"; File → New tab
  (Ctrl+Shift+N), detach tab into own window, New window (Ctrl+N). When closing a window with several tabs,
  each unsaved document is asked about
- Can be disabled: File → Settings → Window → "Open what the program creates as tabs in the same window"

## 1.8.0

- Binding schemes (print dialog → Booklet): binding type saddle stitching (all sheets nested), grouped
  sections (e.g. 4 sheets = 16 pages per section, sections in sequence) or single sheets stacked (perfect
  binding). The preview labels "Section x · Sheet y – front/back"
- Blank pages: padded to a multiple of 4 – at the end or before the last page (the back of the cover stays at
  the back); optionally with a notice text
- Shingling (mm per sheet, ≈ paper thickness): inner sheets are shifted towards the fold
- Marks: fold marks, register marks, fan-out marks at the spine (staircase when gathering); space is kept
  free at the sheet edge for this
- Sheet overview …: all sheets as thumbnails, double-click jumps to the preview
- Command line impose: imposition like in the print dialog as PDF (booklet/sections, instances, multiple,
  poster), sheet size with sheet (e.g. SRA3). Print presets from the program apply directly and remember the
  paper size (--preset "Name"); existing print presets from 1.7 are taken over. Guide extended with worked
  examples
- The bleed from the document is detected (TrimBox/BleedBox, e.g. from InDesign/Affinity/Scribus with "use
  bleed"): the view shows the trim size as a red line, the bleed area tinted red, the BleedBox dashed (not
  printed; View → Show trim size and bleed, Ctrl+Shift+B); the status bar names trim size and bleed. During
  imposition (instances, booklet, cut marks, bleed) the trim size is placed and scaled – cut marks sit on the
  trim size, the bleed genuinely comes from the document; only if more bleed is configured than present, the
  rest is mirrored at the page edge. Normal printing ("Size") still prints the whole page
- Fixed: starting Passermark a second time (start menu, icon) did nothing while a window was open – the
  running instance now opens a new, empty window. New: File → New window (Ctrl+N)
- Print dialog: the preset line sits above the tabs (applies to General and More options)
- Test: folding simulation (fold, nest, stack sections) checks for all binding types, binding left/right and
  blank-page sections that the pages come out as 1…N

## 1.7.1

- Crop to format now scales (default): the fitting edge is scaled exactly onto the target format, the
  overhang of the other edge cut off equally on both sides – A4 → A6 = 50 %, a narrow poster fills the width
  and loses equally top and bottom. Smaller pages are scaled up. Content stays vector. Previously it only
  cropped; that remains available as an option (untick "Scale until the format is completely filled" or
  --set crop_scale=false) for files that already come at final size with bleed.
- Command line/chains: preflight_fix --set fix=flatten_layers no longer aborts on files without layers but
  passes the file through unchanged (note "No layers")

## 1.7.0

- Workspaces: a second bar below the toolbar – View & Print, Print preparation, Edit, Automation. To the
  right, the tools of the chosen workspace appear (e.g. Check, CMYK, Crop, CutContour, Separate objects,
  Repair). Print preparation opens the check, Edit the page sidebar; leaving the workspace ends the edit mode.
  The last chosen workspace applies at the next start. The menus remain complete.
- Presets: in the CutContour, CMYK/Crop windows and in the print dialog the preset line at the top – select,
  Save …, delete, export/load as a file, default values. Print presets cover page handling, Multiple,
  Booklet, Poster, Instances and more options (without printer and tray). Storage: Linux
  ~/.config/passermark/presets/, Windows %APPDATA%\Passermark\presets\
- CutContour remembers the most recently used settings (without the shape offset)
- Command line: --preset NAME finds a preset saved in the program; passermark-cli presets [job] lists them.
  Guide extended.
- Save as PDF with a password (print dialog, destination "Save as PDF"): tick Protect PDF with password
  (AES-256, enter the password twice)
- Windows setup: optionally make passermark-cli available in every command prompt (search path PATH; removed
  again on uninstall)
- Keyboard shortcuts without double assignments: Measure now Ctrl+Shift+L (Ctrl+Shift+M = CMYK and Crop),
  Edit text and layers Ctrl+T (Ctrl+E = Export selection), select the page's text Ctrl+Alt+A
  (Ctrl+Shift+A = select all pages); a test checks this from now on
- Own icons for CutContour, CMYK, Crop, Separate objects, Edit, Check, Repair, Measure and others (previously
  partly duplicate icon assignments)

## 1.6.7

- Time-budget tests in the GitHub build (tests/test_performance.py): CutContour (contour + filler,
  rectangle), object detection, PDF assembly and booklet are measured – relative to a calibration task on
  the same machine, so that build runners of different speeds do not trigger false alarms. From 1.6× slower
  than before, a yellow warning on the build; from 3× the build fails. Reference values in
  tests/perf_baseline.json (re-measure: python3 tests/test_performance.py --messen)

## 1.6.6

- Fixed: blank sheets when printing under Windows (various devices). "Automatic" now always rasterises
  without JPEG (300 dpi) – the most compatible way. Some drivers report PostScript and JPEG pass-through as
  supported and then produce blank sheets; both are now available only on request (File → Settings)
- New: Help → Test Windows printing – one labelled test page per method (raster, raster + JPEG, PostScript,
  vector); shows what the driver really supports
- Windows printing: the device context is passed as a 64-bit pointer (previously ctypes default int),
  halftone mode when rasterising; every job is recorded in druck-windows.log in the log folder (method,
  resolution, driver capabilities)
- Fixed: reddish rectangle over the object (CutContour) when a program or printer driver does not evaluate
  the transparency of the filler/edge images (including the Windows PostScript path): invisible areas are now
  paper-white or show the original motif instead of the first spot colour

## 1.6.5

- Error log: every error ends up in a file to send along (with versions and system details) – Linux
  ~/.local/state/passermark/logs, Windows %LOCALAPPDATA%\Passermark\logs; Help → Open error logs
- Unexpected error: message with the path to the log, Passermark keeps running
- Hard crash (e.g. in a library): a one-time message with the log at the next start
- Errors in background jobs with details; errors in threads
- Without errors the log is deleted on exit; at most 10 are kept
- Parallel computing: memory budget based on the machine's actual RAM (40 %, at least 1 GB)

## 1.6.4

- CutContour with several pages: whole pages in parallel – each worker process computes one complete page
  (including rendering and detection); no more stalling between pages. One page: still objects in parallel
- Memory protection: number of simultaneous pages based on the estimated memory requirement (e.g. A4: up to
  8, A0: 1 – then objects in parallel)
- Progress with several pages: "3 of 12 pages done"; result bit-identical to serial computation

## 1.6.3

- Parallel computing: CutContour distributes a page's objects across several CPU cores (all but one, at most
  8); result bit-identical to serial computation. Worker processes are started once per job and used for all
  pages; small tasks stay serial (not worth it there). Limit with the environment variable
  PASSERMARK_WORKERS (1 = not parallel)
- Progress per object ("Page 1/1 · object 12/40")
- Cancel also terminates the worker processes
- Internal: object computation as its own function; program executables call
  multiprocessing.freeze_support()

## 1.6.2

- No more freezing: CutContour, Separate objects and CMYK/Crop compute as a separate process in the
  background. The window stays usable; progress and a cancel button (✕) at the bottom of the status bar;
  several jobs at once possible; the result opens as usual in a new window
- A crash during computation no longer takes the program down – you get an error message with details
- When a window is closed, running jobs are cancelled and cleaned up
- Guide: example "PDF/A with password" corrected (PDF/A forbids encryption) – split into "PDF/A" and
  "Protect with a password"; the example test now creates an input for each example (build error under
  Linux)

## 1.6.1

- Guide to the command line (PDF, 6 pages) with worked examples for all jobs, presets and whole folders
  (Linux and Windows); in the program under Help → Command line – guide
- The guide's worked examples are tested automatically (tests/test_cli_howto.py) – the guide cannot silently
  go stale; generated with python3 docs/make_cli_howto.py

## 1.6.0

- Command line passermark-cli: CutContour, Separate objects, CMYK/Crop, Repair and preflight fixes without
  the UI; settings via --preset file.json and --set key=value (also nested), --pages, progress bar, Ctrl+C
  cancels cleanly, --json-progress for programs. Linux: passermark-cli (install.sh), AppImage: … --cli,
  Windows: passermark-cli.exe
- Internal: core interface core.py (input PDF + settings → output PDF, progress, cancel, atomic writing) –
  the basis for jobs in their own process, presets and the watcher

## 1.5.3

- CutContour generates faster (approx. 17–20 %), result bit-identical to 1.5.2: motif detection computes with
  integers, the spot-colour search only in the edge strip, unnecessary distance calculations removed (among
  others one per object during smoothing, one for cut-outs below 0.08 mm)

## 1.5.2

- CutContour basic shapes: handles on the shape in the preview – corner handles scale uniformly from the
  centre, side handles only width or height, the move handle above the shape moves it
- Size now only in mm ("Size (W × H)", "auto" = from the motif plus spacing); percent removed. An entered
  size applies exactly as the cut line; dragging the handles writes the mm values into the fields
- New: offset (X / Y) in mm, with a reset button
- Fixed: after scaling with the mouse, entered sizes no longer had any effect (hidden percentage factor)
- Display at the bottom: current shape size in mm, live while dragging

## 1.5.1

- CutContour with a basic shape (rectangle, circle, heart …): one shape around the whole motif instead of
  one per detected part; sits centred, size changes from the centre. Option "One shape per object" for
  sticker sheets
- CutContour: resize the shape in the preview with the mouse (live display in %, applied on release)
- The circle encloses the motif (the larger side as diameter) instead of cutting through wide motifs

## 1.5.0

- Rulers and measuring (View → Show rulers, Ctrl+R; View → Measure, Ctrl+Shift+M, also in the toolbar):
  rulers in mm at the top and left at the edge of the view, stay in place while scrolling, origin = top-left
  page corner, mouse position marked; measuring: 1st click start, 2nd click end, Shift snaps to
  horizontal/vertical/45°, Esc cancels; result (length, ΔX, ΔY, angle) bottom right in the status bar;
  measured in real page dimensions, independent of zoom and rotation

## 1.4.7

- CutContour: the preview refreshes automatically with every setting – previously it kept showing the old
  contour after a shape change (rectangle, circle, heart …) until you pressed "Refresh preview"
- CutContour: the preview computes in the background, the window stays usable ("Computing preview …");
  several quick changes in a row trigger only one computation
- New test (tests/test_cut_dialog.py): a shape change changes the preview

## 1.4.6

- Fixed: the program did not start under Python 3.10/3.11 (e.g. Ubuntu 22.04) – syntax in convert.py that is
  only allowed from Python 3.12; the AppImage build now checks this as a first step
- AppImage: an installed Ghostscript takes precedence, the bundled one serves as a fallback; if it fails to
  start at build time it is removed with a warning (the build does not fail)
- Finished programs via GitHub: Windows setup.exe and Linux AppImage are built on every push and published as
  a release for tags v*; dependencies (Python, Qt, all packages, Ghostscript) are included
- Self-test of the finished executable in the build (--selftest); --version
- Ghostscript is found next to the program's own executable (installer/AppImage include it)
- AppImage: saving admin defaults via pkexec with the same hardened helper
- Fixed: admin window not scrollable on small screens (tabs scroll, the window adapts)
- Fixed: touchpad scrolling (page change/zoom) under Windows
- uninstall.sh, .gitignore; installer script UTF-8 with BOM; build.ps1 plain ASCII; README in English

## 1.4.5

- Windows printing redone (as in pdfToolkit 1.4.3): PostScript directly for PS drivers, otherwise own
  rasterising in strips with JPEG – fixes long spooling and aborted jobs (especially with multiple instances);
  settings under File → Settings → "Printing under Windows". Linux printing unchanged
- Fixed: possible crashes – the document check used pdfium in a background thread simultaneously with the
  view (pdfium is not thread-safe); those parts now run in the main thread

## 1.4.4

- Root cause found (on a Chrome PDF): pdfium cannot rewrite pages with Type3 fonts – previously all text
  disappeared. Editing now manages entirely without regenerating the page:
  - Move/scale: the line is lifted out of its text block (the line matrix is carried along), even when many
    lines share one block
  - Change text/font: first directly; if the page loses content, the old line is removed and the new one placed
    on top at the same position and in the same colour
  - Delete: only the line's text commands are removed
- The coordinate system is carried along (Chrome: scale 0.24 + mirrored; CAD: 0.12) – when moving text and
  layers, when replacing layers and for the CutContour line (the original content is wrapped in q/Q)
- Lines are recognised better (also with a font change within the line and individually placed letters)
- The re-check is more sensitive (also on pages with little text)
- New tests: a Chrome-like Type3 file, a CAD layer in a scaled coordinate system

## 1.4.3

- Fixed: after moving/scaling with the mouse, text changes or font changes, all the page's texts could
  disappear
- Moving/scaling text now changes only the affected text blocks in the PDF (q/cm/Q); the rest of the page
  stays byte-identical; pdfium's regeneration of the page only as a fallback
- Every text edit runs on a copy and is re-checked afterwards (characters and pixels outside the edited
  line); if anything is missing, nothing is applied and a message with details appears
- The view releases its open pages before the edit
- The start test considerably stricter (missing own methods surface immediately) and now also checks change
  text, change font and delete – all other lines being preserved

## 1.4.2

- Fixed: "don't know how to encode value np.float64" when scaling layers (reference "centre of the layer")
- Fixed: mouse selection in edit mode found nothing if the lists had not been loaded when it was switched on
- Move and scale with the mouse: grab and drag the object (text line/layer); scale at the four corner handles
  (the opposite corner stays fixed); dashed preview, matching cursors, undo
- Moving/scaling text lines preserves font, colour and layer
- Finer layer detection; the start test now also checks the mouse interaction

## 1.4.1

- Fixed: the program did not start (name conflict in the page view caused by the new text selection)
- Fixed: Ctrl+C (copy text) would have raised an error (missing import)
- New start test (tests/test_gui_smoke.py): program start, window, text selection, edit mode – without a
  screen

## 1.4.0

- Edit mode (Document manipulation → Edit text and layers, Ctrl+E): "Edit" page sidebar
  - Text: list the page's lines or click them on the page; change text, font (original, standard fonts, your
    own file) and size, delete a line
  - Layers: list or click on the page (repeated clicking cycles through stacked ones); show/hide, remove,
    scale/move (including "Bring back onto the page"), replace with a page of another PDF; undo
  - Select text in the page view (drag, double-click = word, Ctrl+C copies)
- Font download: own buttons under the table, visible error messages, fallback to the fontsource CDN
- Translations: missing texts added (print dialog, admin, merge, file filters, messages), "&" spelled out in
  translations, German driver terms (from German-installed PPDs) are translated

## 1.3.2

- Fixed: the "Download free font" dialog did not open
- Flatten layers / recommended repairs: if view and print differ, Passermark asks which state should apply
  ("As when printing" / "As on screen") – instead of silently taking the print state
- Embedding: warning when no replacement is chosen for a missing font (otherwise Ghostscript uses its own)
- CAD standard fonts (ISOCPEUR & co.) without osifont: narrow fallback font (DejaVu Sans Condensed)
- Fonts with custom glyph names (without embedding) are recognised as not repairable

## 1.3.1

- Font download: commercial fonts are redirected to their free, metrically identical twin (Arial → Arimo,
  Times New Roman → Tinos, Courier New → Cousine, Calibri → Carlito, Cambria → Caladea, Georgia → Gelasio);
  the dialog suggests it and explains why
- Unknown name: suggestions of similar free fonts ("Did you mean …") instead of just "404"

## 1.3.0

- New name: Passermark (previously pdfToolbox – name clash with a commercial preflight product); own paths
  (/etc/passermark, /usr/local/lib/passermark), runs alongside pdfToolkit/pdfToolbox
- Document check (preflight) on opening: fonts (embedding, type, Unicode, odd characters), layers
  (view/print, misaligned), transparencies; status button, "Check" sidebar, report
- Repairs: adopt the layer state, bake the visible state, remove layers, embed fonts with a
  metrically compatible replacement / your own file / download (fontsource.org), text to paths, reduce
  transparencies
- install.sh: free replacement fonts (Liberation, Carlito, Caladea, URW, DejaVu)

## 1.2.5

- CutContour: filler can be disabled ("generate" or 0 mm) – the motif stays unchanged (no filler, no
  cut-out), only the cut line; with a positive "spacing to the motif" you get white margins

## 1.2.4

- CutContour colours: unmixing instead of RGB distance – edge pixels are interpreted as a mixture of
  spot colour + background or spot colour + spot colour (light pink = red, not green); fixes wrongly coloured
  wedges in the filler
- The filler colour comes from this assignment; inside the cut shape always fully opaque
- Cut-outs: tiny holes closed (no white dots), tighter tolerance (no light seam)
- New: the filler colour can be fixed (uniform edge) for motifs where the automatic does not fit
- New (optional): clean up mixed edges in the motif (narrow fringes up to ~1 mm between spot colours)

## 1.2.3

- CutContour filler in spot colours: colour = the object's computationally nearest spot colour (the exact
  original tone), no more pale mixed tones from anti-aliasing/scaled screening
- Light fringe removed: for motifs with a background, the mixed fringe at the edge is cut out (flat motifs:
  adaptively up to 1.5 mm, photos: 0.25 mm) – the spot-colour filler lies there
- Inner cut with filler: cut-out holes are cut out of the original, the filler runs over the inner cut line;
  small inner areas (white lettering) remain

## 1.2.2

- Fixed: error "don't know how to encode value np.float64" with "Each object as its own page" + filler (page
  dimensions are now passed to pikepdf as plain numbers)
- Fixed: filler invisible on motifs with a background (white page, raster image) – the original is clipped to
  the object shape (background punched out), inner areas like white lettering remain; the preview likewise

## 1.2.1

- Separate objects: the margin applies immediately (also negative, also on self-drawn frames) – previously
  only after "re-detect"; dashed preview of the margin; the other sliders re-detect automatically
- CutContour: the filler fills the whole area inside the cut line (space between object and line,
  indentations) plus filler beyond the line – edge colours (also multi-coloured) pulled outwards, lies behind
  the object; colours from the core (no mixed colours from anti-aliasing)
- Error messages in the object dialogs with "Details" (the sequence to copy)

## 1.2.0

- CutContour: sticker shapes rectangle, rounded rectangle, circle, oval, hexagon, octagon, heart, star,
  crest, goal arch – at object size, scalable (%) or fixed size (mm); spacing also negative
- CutContour: the filler starts from the object (no frames in empty areas); a cut through the motif always
  lies inside the filler
- CutContour: output optionally each object as its own page with a margin (default 6 mm), neighbours hidden
- Detection: a motif filling the whole page is recognised as one object (the contour used to hang on the
  page edge); auto mode recognises the background also on partially transparent pages
- Separate objects: margin also negative (inwards)

## 1.1.0

- Separate objects: detect objects (business cards, photos on scans …) and open them as individual pages
  without white space; vector exactly via transparency, raster via background colour; editable frame
- CutContour for cutting plotters (Roland VersaWorks): special colour "CutContour", spacing, smoothing for
  weeding, automatically generated filler (the cut always lies inside it), inner contours, preview
- Open SVG/SVGZ (vector, true size; rsvg-convert > Inkscape > Qt), also via right-click and merge
- Transparency in WebP/GIF/HEIC is preserved (instead of being flattened onto white)
- New dependencies: scipy, contourpy, librsvg2-bin

## 1.0.1

- Document manipulation now as its own menu next to "Document" (CMYK conversion, cropping, both); no longer
  in the print dialog
- The result opens in a new window, stored only temporarily in the cache (deleted on exit)
- Fixed: cropping did not apply when printing – the cropped file itself is now printed (end-to-end test:
  crop → cache → print, the margin disappears)
- "Document" menu: merge and repair/optimise

## 1.0.0 (October 2026)

First version of Passermark, built on pdfToolkit 1.4.0 (all features taken over).

- Document manipulation (tab in the print dialog and Document menu):
  - CMYK conversion: RGB→CMYK with unchanged CMYK, complete re-separation (source → destination profile),
    greyscale; intent, BPC, grey/black with K only, output intent
  - Colour preview before/after from real CMYK values, individual separations, total area coverage (TAC),
    paper white
  - Crop to target format with an equal overhang on both sides, portrait/landscape follows the page
- Installable independently alongside pdfToolkit (own paths, admin helper, polkit rule, single instance)
- Own icon; all texts in German, English, Hungarian, Spanish, French
