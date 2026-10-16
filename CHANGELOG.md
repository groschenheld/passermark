# Changelog – Passermark

**English** · [Deutsch](CHANGELOG.de.md) · [Magyar](CHANGELOG.hu.md) · [Français](CHANGELOG.fr.md) · [Español](CHANGELOG.es.md)

## 1.13.2
### Print dialog: preview in the background
- **Preview without waiting:** the sheet is mounted and drawn in the render process now – the dialog no longer waits for it. With a large file the preview takes 0.001 s in the main window instead of freezes of up to 6 s before. If something is changed while a computation is still running, only the newest state is drawn to the end.
- The waiting time remains: the preview is still not finished for 2–5 s, because drawing the page itself takes that long. The dialog stays usable during that time.
- **Multiple copies (e.g. step & repeat):** the page is rendered only once instead of once per copy – roughly twice as fast. The image deviates minimally because it is a raster image; only with very fine patterns a slight moiré is visible. Printing still uses the original.
- **Without multiple copies** the preview is pixel-identical to before (compared for single pages, 9 on 1, booklet, press sheets and duplex).
- **Trim size/bleed** now comes from the page data without loading the pages – the values are the same as before.
- **Sheet overview** is computed in the background as well.
- **Still in the main window:** switching to "Booklet as press sheets" still takes about 0.9 s; generating the press sheets has not been moved out.
- **Page view:** large page images are scaled coarsely immediately when zooming; the clean image follows in the background. The upper limit for the page image is unchanged at 16 megapixels.

### Merging on Windows
- **One window:** if several files arrive at the same time, they all land in the same window. Tested with 12 simultaneously started calls: 1 window, 12 files, sorted by name.
- **New buttons:** "Add folder …", move up/down and "Sort by name". Files can also be dragged in; the window shows how many are in it.
- **For many plans:** best use "Send to → Passermark – merge" – it passes all files at once and is created once on the first start. Alternatively add the whole folder in the window.
- **Sidebar:** selected pages can be moved. The yellow bar shows where they will land; at the edge the sidebar scrolls on automatically.

## 1.13.1
### Speed fix
- Minor speed improvements in the new view (rendering).

## 1.13.0
### Faster view (render overhaul)
- **Rendering in a separate process:** pages are rendered by a background process (`passermark-cli render-server`); the user interface never waits for it. Only one request is in flight at a time, so fast page flipping no longer piles up outdated requests. If the process crashes it restarts; if it cannot start at all (or the PDF is password-protected), the view renders inside the program as before.
- **One page image per page:** each page is rendered once at roughly twice the viewing size; zoom levels up to that size and the thumbnails are only scaled from it. A page's images are unpacked once instead of once per zoom level and once per thumbnail.
- **Strong zoom renders only the visible part,** pixel-exact even in a rotated view. At 400 % the page is briefly blurry and then sharp (previously upscaled and blurry).
- **Saving over the same file works on Windows now:** the file is read into memory and released on disk.
- **Edit mode:** while dragging, the object moves along semi-transparently; after applying, the old images stay as placeholders and are renewed in the background, the edited page first. Previously everything turned white and all thumbnails were re-rendered in the main window.
- **Automatic check reads unchanged files directly** – no re-save in the main window needed when opening.
- Troubleshooting: with `PASSERMARK_RENDER=local` everything renders as before – a quick way to narrow down whether the new render process is the cause.
- Known limitation: releasing an object in edit mode still takes about 1 s on heavy pages (the safety check compares the page before and after). Elements used on several pages can change everywhere through an edit, so after editing all pages are re-rendered in the background, the edited one first.

## 1.12.6
### Preflight adjustments
- Small adjustments to the "Reduce file size" function (`shrink`) and the preflight checks; translations completed; CLI manual (DE/EN) updated.

## 1.12.5
### Licences
- Installer and AppImage now include all third-party licence notices (Python packages, Qt LGPL-3.0, Ghostscript AGPL-3.0 with source reference, bundled system libraries), viewable via the new menu entry Help → Licences.
- READMEs: new section on third-party licences, with source code available on request.
### Docs
- The CLI manual (DE/EN) is updated with `shrink` and `flatten_softmask`.

## 1.12.4
### Reduce file size (new)
- Available from the "File size" tab or Document → "Reduce file size …", also for files that are not flagged as too large.
- Every measure can be switched on and off individually:
  - **Lossless, on by default:** rewrite (drops old saved versions), remove unused resources, merge duplicates (fonts, images, ICC profiles), remove editing data and thumbnails, recompress images losslessly (also removes ZIP around JPEG when smaller).
  - **Off by default:** 16 → 8 bit, remove attachments, remove hidden layer content.
  - **Optional downsampling:** to 300/240/150/100 dpi with threshold and JPEG quality, measured at the largest placement. Soft masks are scaled along.
- The result opens in a new window and the original stays unchanged. If the result is not smaller, the file is kept as is.
- CLI: `passermark-cli shrink in.pdf out.pdf [--set downsample=true --set target_dpi=150 …]`
- Example: a 34 MB file with the same CMYK profile embedded 90 times went down to 0.5 MB, pixel-identical.

## 1.12.3
### Preflight
- **New tab "File size":** shows where the bytes go: images, fonts, colour profiles, Illustrator/Photoshop editing data, thumbnails, attachments, page content.
  - It also lists old saved versions, duplicates, and the largest images with their effective dpi.
  - Warns about very large files (more than 20 MB per A4 area) and large duplicates.

## 1.12.2
### Preflight
- **Transparent gradients (soft mask in pattern):** detected and repairable. Some RIPs/plotters print them as a black area that covers the images beneath. The new repair "Convert transparent gradients to images (300 dpi)" renders only the affected gradients, together with what lies beneath, as an opaque image. Text and vectors on top stay intact. No Ghostscript needed.
- **HDR photos (gain map):** a phone HDR photo opened with both images is now detected in the check. Repair: "Remove HDR auxiliary pages …", with the size selectable and an optional gain-map merge.
- **New tab "Images & Colours":**
  - Colour space per image and page (RGB, CMYK, grey, spot colours), including the exact ICC profile name and the output intent.
  - Effective resolution per placement, also for images used several times or inside forms.
  - Recommended maximum size at 300 and 150 dpi, plus the maximum scale per page.
  - Warnings for low resolution and info for RGB content and spot colours.

## 1.12.1
- **Edit mode: several objects and lines at once.** "Scale / move …", "Delete object", "Apply" (font
  and size) and "Delete line" now act on all selected objects or lines, no longer only on one. With
  several lines selected the text field is locked – changing text works with one line only
- **Edit mode: change colour.** New "Colour …" button for text lines and vector objects, either
  CMYK (default, for print) or RGB; for vectors fill and stroke separately selectable. Black
  0/0/0/100 stays pure black. The colour is set directly in the page content – everything outside
  the selection stays untouched, including objects that only inherited their colour
- **Edit mode: overview.** The tabs show the count ("Text (12)", "Objects (40)"); in the "Objects"
  tab a filter for vectors or images is available, with the count per kind. With an active filter a
  click on the page selects only that kind
- **HDR photos from phones (iPhone, Android) are recognised.** Such JPGs contain a grey
  luminance map for HDR screens next to the photo. Previously that became a second page in a
  different size – with wrong colours at the plotter. Now a hint appears on opening; "Repair"
  produces one page with the unchanged photo, size selectable (like the auxiliary image or as
  stored in the photo). The luminance map can optionally be computed in. Without a prompt (command
  line, direct printing) the file is repaired automatically
- **Fixed: font size of text on a path.** After changing it, the list kept showing the old size and
  every further change enlarged again (24 → 36 → 54 pt). The actual size is shown now; short arcs
  with few letters are recognised as path text as well. "Apply" without a change leaves the page
  untouched
- **Fixed: Z-order.** "One step forward" on the topmost object falsely reported "structure of the
  page not recognised" – now everything simply stays as it is
- **Fixed: dragging text with the mouse** aborted with an error message on some PDFs (e.g. from
  Chrome)
- Translations for the items arrangement in the print dialog added (English, Hungarian, Spanish,
  French)

## 1.11.3
- **VDP dialog facelift.** Variable data uses the same look as the print dialog: four numbered,
  collapsible sections (fields, data, numbering, output) plus a collapsed "Guide" section on top.
  Field explanations are tooltips now and only appear under the fields via the new "Show help
  texts" switch. The outdated output hint points to the print dialog's Step & Repeat order now.
  The CollapsibleSection widget lives in common.py, shared by both dialogs.
- **Print dialog without tabs.** The mode selector at the top ("What should be printed?") now leads
  through the whole dialog in a single, continuous column: preset, mode, mode panel, scaling
  ("How onto the sheet?"), crop marks, paper/output, finisher, colour management. Old tab
  navigation is gone.
- **Step & Repeat is a mode of its own.** "Nutzen" joins the mode selector next to single sheets,
  multiple per sheet, booklet and poster – with an explanation text like the other modes. The old
  checkbox is replaced by the mode button; the S&R panel appears exactly where the other mode
  panels are.
- **"How onto the sheet?"** scaling and orientation are now one group: fit/original size/shrink/
  custom, rotation, auto-rotate, centring, margins. The scaling choice (fit/actual/…) is
  visible and effective in every print mode: fit = the mode's default, original size/shrink/custom
  override the mode scaling – the mode fields (tile scaling, Nutzen scale, poster) remain alongside.
- **Mirror and driver options collapsible.** Both sections stay visible with a clear title and can
  be folded open only when needed – all options unchanged.
- **Booklet binding: "Standard" first.** The classic saddle stitch ("all sheets nested together,
  folded once") now leads the binding list under the clear name "Standard" – the "sheets per
  signature" spinner only appears for grouped signatures, so it can no longer suggest a wrong
  setting.
- **Uniform collapsible sections.** Every block of the new column – preset, mode selection
  ("What should be printed?"), "How onto the sheet?", crop marks, paper/output, finisher, colour
  management, mirror, driver – carries the same collapsible header in the same size. The mode
  buttons sit one below the other so every label stays readable, and the mode panel shrinks to the
  visible mode (no empty placeholder space any more). Switching away from "Nutzen" always works.
- **Localisation:** 26 new/reworked messages per language (EN/DE/ES/FR/HU); missing 1.11.1 strings
  in ES/FR/HU/EN message catalogues were backfilled. Old presets remain fully compatible
  (handling "size"/"multiple"/"sr" still load).

## 1.11.2
- **Step 2: mount the sheet again.** The finished step-1 sheet is mounted a second time onto a freely
  chosen target format (device formats or custom sizes in mm) – row by row, always centred, content
  unchanged; the result can be output as a new document via a button (new tab), the preview shows it
  like step 1 and the dialog closes afterwards. Rotation and orientation from step 1 also apply to
  step 2. Grid: 0 × 0 = automatic (as many as fit).
- **Use existing crop marks.** With documents that have a trim size (TrimBox), the outer sides of the
  item block show the real document edge – existing crop marks stay visible; own marks remain
  switchable via a checkbox as before.
- **Mount the grid exactly.** A defined grid (e.g. 3 × 3) always stays exact in step 1 and step 2 – if it
  does not fit the sheet, it is clipped symmetrically at the edge with a warning, never aborted.
- **Target format planned without margins:** e.g. two A4 sheets from step 1 fit neatly onto one A3.
- Step-1 print path and orientation unchanged.

## 1.11.1
- **Custom paper sizes: only "Save as PDF" any more.** Self-defined sizes are no longer sent to printers –
  Windows drivers and spoolers often reject custom sizes (blank sheets, aborts); with "Save as PDF" (★)
  they remain fully usable
- **Crop: two new modes.** "Trim edges": trim the page on all four sides in mm, without a target format;
  "Remove white space": detects the visible content (JPEG noise included), the new page size results from
  the content frame ± margin (negative allowed), the content stays 1:1 (only moved)

## 1.11.0
- **Variable data – windows (page groups).** For templates with several pages every field belongs to a
  window (e.g. "front sides (name), back sides (QR code)"); windows can be created, renamed and removed –
  their fields then move to the first window. Page selection per window: all pages, odd (front sides),
  even (back sides) or ranges ("1,3-5 or odd 1-50"); without its own selection the "all pages" base layer
  applies. Record distribution "sheet by sheet" (first all pages with record 1) or "page by page" (first
  page 1 with all records); display "{0} records → {1} pages" and warning "– {0} pages without a window!"
- **VDP preview:** trim size green, bleed red; adjustable inner frame (guide line) between trim and bleed
- **Page indicator "current / total"** in the toolbar; type a page number and press Enter to jump to it
- **Rulers, measuring and trim-size overlay permanently in the main toolbar** – in every workspace, not
  only under "View & Print"
- **Trim size and bleed in the main view:** inner boundary (trim size) green instead of red, bleed as a
  subtle red dotted line instead of a solid red area
- **Measuring with snapping:** hold Control and the crosshair snaps magnetically to trim and inner lines
  (page edge, trim size, bleed) as well as image edges and vector lines – never to text. The preview
  crosshair sticks to the edge until the mouse pulls clearly away; Shift still locks horizontal/vertical/45°

## 1.10.7
- **CutContour: basic shapes without computation.** New placement "On the trim size (without computation)":
  rectangle, rounded rectangle, circle … are placed directly onto the trim size (TrimBox, otherwise the page) –
  no rendering, no motif detection, no worker processes, within fractions of a second. Distance, size, offset
  and dragging with the mouse work as before. Computation only happens with "Contour" or when the shape is
  placed around the motif or per object. Command line: `--set fit=trim`
- **Default in CutContour:** rectangle on the trim size (as long as no own last-used settings are stored)

## 1.10.6
- **Fix Windows: CutContour got stuck at 0 %** (since 1.10.5). Switching the command-line output to UTF-8 is
  removed again; the fix for "Split pages" remains (progress messages as plain ASCII)
- CutContour: no more error when a preview computation catches up while the window is being closed
  ("expected LP_struct_fpdf_document_t … NoneType")

## 1.10.5
- **Fix Windows:** "Split pages" (and every job whose message contains characters like "→") aborted with
  `UnicodeEncodeError … cp1252`. The command line now switches its output to UTF-8 itself; the progress
  messages to the user interface are plain ASCII
- `SECURITY.md`, `CONTRIBUTING.md` and GitHub templates for bug reports and feature requests included in the
  package

## 1.10.4
- README bilingual: `README.md` (English) and `README.de.md` (German), up to date (split pages, variable data,
  enter data, all command-line jobs) and with a note about the project status
- Example configuration `data/defaults.example.json` with neutral printer names

## 1.10.3
- **Split pages via right-click:** select pages in the sidebar → right-click → **Split** →
  "Split vertically in half" / "Split horizontally in half" – immediately, only the selected pages, no
  comparison page needed. "Grid / more options …" opens the dialog with the selection preset

## 1.10.2
- **Variable data – front and back:** new "Pages per record" (under 2.): 2 = pages 1+2 → record 1, 3+4 →
  record 2 … – regardless of whether the template has 2 pages or already all cards (e.g. 200 pages for 100
  business cards). Fields "Only on these pages" now know **odd** and **even**, also combined with ranges
  ("odd 1-50"). Example 7: business card with name on the front and QR business card on the back
- **More variables:** {{datum}}, {{zeit}}, {{jahr}}, {{monat}}, {{tag}}, {{wochentag}}, {{kw}}, {{datum_iso}},
  {{datum:FORMAT}}, {{seite}}, {{seiten}}, {{vorlagenseite}}, {{datensatz}}, {{datensaetze}}, {{datei}},
  {{zufall}}, {{zufall:N}}, {{code:N}}, {{uuid}}. The **?** button next to the content shows all of them with
  an example value, double-click inserts one. CSV columns of the same name take precedence
- Double-clicking a column **replaces** an unchanged {{nr}} instead of leaving it in front
- **Split pages** (Pages → Split pages …, Edit workspace): split in half vertically/horizontally or a grid,
  all/current/selected pages or a range, only spreads, order right→left; with a preview of the cut lines.
  **Split spreads** with one click for wrongly exported booklets. Lossless (content is not copied or
  rasterised), rotated pages the way you see them; with a trim size the split happens inside it and the bleed
  stays outside. Command line: job `split`
- **Sidebar:** the thumbnails rotate along with "Rotate view left/right"
- **Fixed: opening from outside landed in a locked window** (Windows, right-click/double-click while a tool is
  open in a window) – now its own window. Cause: opening in the empty start window left behind an invisible
  empty tab; the empty window is now used itself. Results from a locked window also open in their own window

## 1.10.1
- **Use your own CSV with different column names directly:** Variable data → Open CSV recognises what the
  table fits ("The table fits: QR – business card"), **Create fitting field** creates the QR code with that
  type. The columns are mapped automatically – including English, Hungarian, Spanish, French names and the
  headers of contact exports from **Outlook, Google and Thunderbird**. The CSV stays unchanged
- **Map columns …** in the QR field with a type: choose the column per entry, "leave empty" or automatic;
  with a preview of the finished content. Below the type it says what comes from where and what is missing.
  The mapping is saved in the preset (`qr_map`) and also applies on the command line
- Enter data: a CSV with foreign column names no longer gets duplicate columns; the header shows the mapping
  ("First Name → First name"). `datencheck` recognises foreign column names as well
- Example folder: `kontakte-outlook.csv` (this is what an Outlook export looks like); guide extended with
  "Your own CSV with different column names"

## 1.10.0
- **Enter data** (Variable data workspace, Document manipulation menu, or in the Variable data dialog under
  2.): build the data table directly in Passermark. The fitting columns per type – **QR business card
  (vCard), Wi-Fi access, e-mail, web address, phone call, SMS, event, location**, free QR text, **Code 128**,
  **EAN-13**, text with own columns. Every row is checked immediately (required entries, EAN check digit,
  umlauts in Code 128, date …), on the right the finished code of the selected row. Paste from Excel with
  Ctrl+V, duplicate rows, fill a column with a number series (also creates the rows), own columns. Save as CSV
  (UTF-8 with BOM, semicolon – Excel reads umlauts correctly)
- **"Use in variable data"** adopts the table as data source and creates the fitting field
- **QR field "Type of QR code":** content as entered or composed from the table columns (vCard, Wi-Fi,
  mailto, tel, SMS, event, geo). The CSV stays readable; Passermark builds the code content when generating
- **Quiet zone:** QR code and Code 128 now have a white border in the field (can be switched off). Without
  it, codes close to other content were hard to read. *Existing presets: the QR code becomes slightly smaller
  in the field because of this*
- **EAN-13 with 13 digits and a wrong check digit is now an error** (with the correct number in the message) –
  previously the last digit was silently replaced
- Command line: `datenarten`, `datenvorlage <type> [file.csv]`, `datencheck <file.csv> [type]` (return code 1
  on problems); in the preset `qr_type` per QR field
- Examples 5 (business card from contact list) and 6 (Wi-Fi access); guide "Variable data" with a new section
  "Enter data", CLI guide extended
- Tests now really read back the generated codes: QR and EAN-13 with OpenCV (if installed), Code 128 with an
  own reader including checksum
- Fixed: variable data used "one copy of the whole document per record" without choosing the distribution
  instead of "the next record on every page"

## 1.9.5
- **Variable data examples in the program:** template, CSV, 4 presets (QR with number, QR from CSV, Code 128,
  EAN-13) and finished result PDFs are included in the program package. *Help → Get variable data examples …*
  (also in the Variable data workspace) copies them to `~/Passermark-Beispiele/vdp`, registers the presets
  "Beispiel 1" to "Beispiel 4" with the full CSV path and opens the template
- **New guide "Variable data" (PDF)** for the user interface and the command line, with all four examples step
  by step: *Help → Variable data – guide (PDF)*
- Command line: `passermark-cli beispiele [folder]`; a relative `csv_path` in the preset is also searched next
  to the preset file
- Command line guide: VDP texts brought up to date (next record on every page, workspace)
- Windows/Linux build: the whole folder `pdfdruck/docs` is included

## 1.9.4
- **Fixed: Code 128 – plaintext line distorted.** The readable line below the barcode was stretched together
  with the bars to the field size; now it sits below it in the set font size
- Example package "passermark-vdp-beispiele": template, CSV, presets and finished PDFs for QR code, Code 128
  and EAN-13

## 1.9.3
- **Fixed: variable data placed the same values on every page** (number 1, same name, {{i}} = 1) – one record
  always applied to one copy of the *whole* document. New and default: **every page gets the next record**
  (page 1 → record 1, page 2 → 2 …; with a one-page template one page per record). The previous distribution
  remains available as "One copy of the whole document per record" (e.g. front and back of a card). The choice
  is now the first question under "2. Where do the data come from?"
- Without a CSV the count at the start is the document's page number; page and record in the preview are
  linked (page 3 shows record 3)

## 1.9.2
- **Variable data easier to understand:** every setting with a heading and a short explanation above it,
  groups in the order of work (1. fields, 2. data, 3. numbering, 4. output), quick instructions at the top;
  position/size, counting with labelled individual fields (left, top, width, height – first number, step,
  digits); display of where a continue-counting counter currently stands; CSV "Remove"
- **Reset everything** (button at the top): one text field with the number, no CSV, numbering from 1
- Variable data only remember the last settings until the program ends – after a restart the dialog starts
  fresh. Keep permanently: save as a preset
- A new EAN-13 field starts with a valid example number instead of {{nr}}

## 1.9.1
- **Windows with many options are no longer cut off:** Variable data, CutContour, Separate objects and the
  print dialog have a movable divider between preview and settings; the settings area scrolls vertically and –
  if narrower than its content – horizontally as well. The same in CMYK/crop and in the admin dialog. Dialogs
  never open larger than the screen
- Variable data: button "Open CSV …" (was cut off in a narrow window – only the save button of the code log
  remained visible, now "Save as…"); Enter in an input field no longer accidentally starts "Generate"

## 1.9.0
- **Variable data** (Document manipulation → Variable data …, Ctrl+Shift+D; own workspace): place fields on
  the template and position them with the mouse – **text**, **QR code**, **Code 128**, **EAN-13**, all as
  vectors. Content as a template: `{{Spalte}}` from a CSV file, `{{nr}}` (number), `{{i}}` (running). Font,
  size, colour, alignment, rotation, only on certain pages. Preview with a real result for every record.
  Result as a new tab
- **Numbering:** start, step, digits (with zeros), prefix/suffix, check digit (Luhn, GS1/EAN, mod 11),
  backwards for tear-off pads, **continue counting** across jobs (counter name)
- **CSV:** delimiter and encoding (UTF-8/Windows) are detected; insert columns by double-click; record range;
  order per record all pages or per page all records
- **Placeholders `{{…}}` in the PDF** (e.g. from InDesign) are taken as the field position, the placeholder
  text removed
- **Code log** as CSV (output page, record, all values)
- **Step & repeat with its own record per copy:** print dialog → Step & repeat → "Next page per copy", order
  sheet by sheet or **cut and stack** (each stack in sequence)
- Command line: job `vdp` (fields most conveniently as a preset from the program), `impose` with
  `sr_sequence` and `sr_stack`; guide with case examples
- Trim size/bleed of the template is kept in variable data (for imposing afterwards)
- New dependency: reportlab (text, QR and barcodes as vectors) – included in setup and AppImage

## 1.8.5
- **Custom paper sizes in the print dialog:** next to "Paper size" the button *Custom sizes …* – create or
  delete name, width × height in mm. The sizes stay stored and are available for all printers and for "Save as
  PDF" (marked with ★). They are spooled as a custom size: CUPS `PageSize`/`media` = `Custom.WxHmm`, Windows
  custom paper (DMPAPER_USER with width/length). Whether a device accepts the size is up to its driver; the
  print margins are taken from the printer's standard size
- Print presets with a custom size remember the size (for `passermark-cli impose`: `sheet=custom`)

## 1.8.4
- **Fixed: crash message after closing** a window/tab ("expected LP_struct_fpdf_document …" in the page view) –
  the view no longer accesses the closed document
- **CutContour circle:** side handles scale evenly (previously briefly an oval, then it jumped back; the
  fields stayed e.g. at 60 × 120). For the circle there is now only one diameter (height follows width)
- CutContour: the ↺ button next to "Size" resets size and position (automatically from the motif, centred)
- **Crop to format:** new "Trim white margin first" (mm, command line `crop_inset_mm`) – first the template is
  shrunk all around by this value, then scaled and cropped as set

## 1.8.3
- **Fixed: step & repeat "bleed against bleed" left gaps between objects** – for single objects from CutContour
  or "Separate objects" the whole page including the white margin was placed. Now these pages carry their trim
  size: CutContour = cut line (bleed = overfill), Separate objects = object (bleed = margin). When imposing,
  the bleeds lie against each other
- Step & repeat "bleed against bleed" with bleed 0: the bleed from the document (BleedBox) is adopted – an
  explicitly set value takes precedence. "With margin" 0 places the trim sizes (cut lines) directly next to
  each other

## 1.8.2
- **Dialogs now lock only their own window:** print dialog, CutContour, CMYK … open – in the other Passermark
  windows you can keep paging, zooming, working. (Tabs in the same window belong to that window and stay
  locked; "Open in own window" detaches a tab)
- Booklet: "Sheets per section" is always adjustable; changing the number automatically enables "Grouped
  sections" (with saddle stitching the number otherwise had no effect). Added a test for 24 pages with 3
  sheets per section

## 1.8.1
- **Tabs:** whatever the program creates or opens becomes a tab in the same window – open button with a
  document open, drag & drop, results (CutContour, CMYK/crop, Separate objects …), "Open in Passermark now"
  after "Save as PDF", the guide. Starting the program without a file and double-click or "Open with" in the
  file manager still open a standalone window. Every tab is a full window with its own menus, bars and
  sidebars; with only one document the tab bar is hidden
- Tabs: move by dragging, close with ×, right-click → "Open in own window" / "Close others"; File → New tab
  (Ctrl+Shift+N), detach tab into own window, New window (Ctrl+N). Closing a window with several tabs asks
  for every unsaved document
- Can be switched off: File → Settings → Window → "Open things from within the program as tabs in the same
  window"

## 1.8.0
- **Binding schemes** (print dialog → booklet): *binding* saddle stitching (all sheets nested into each other),
  grouped sections (e.g. 4 sheets = 16 pages per section, sections one after another) or single sheets stacked
  (perfect binding). The preview labels "Section x · Sheet y – front/back"
- **Blank pages:** padded to a multiple of 4 – at the end or before the last page (the back of the cover stays
  at the rear); optionally with a note text
- **Shingling** (mm per sheet, ≈ paper thickness): inner sheets are shifted towards the fold
- **Marks:** fold marks, registration marks, collation marks at the spine (staircase when gathering); space is
  reserved for them at the sheet edge
- **Sheet overview …:** all sheets as miniatures, double-click jumps to the preview
- **Command line `impose`:** impose like in the print dialog as a PDF (booklet/sections, step & repeat,
  "Several", poster), sheet format with `sheet` (e.g. SRA3). Print presets from the program apply directly and
  remember the paper format (`--preset "Name"`); existing print presets from 1.7 are adopted. The guide gained
  case examples
- **Bleed from the document is detected** (TrimBox/BleedBox, e.g. from InDesign/Affinity/Scribus with "use
  bleed"): the view shows the trim size as a red line, the bleed area tinted red, the BleedBox dashed (not
  printed; View → Show trim size and bleed, Ctrl+Shift+B); the status bar names trim size and bleed. When
  imposing (step & repeat, booklet, cut marks, bleed) the trim size is placed and scaled – cut marks sit at
  the trim size, the bleed genuinely comes from the document; only if more bleed is set than present, the
  remainder is mirrored at the page edge. Normal printing ("Size") still prints the whole page
- **Fixed: launching Passermark a second time (start menu, icon) did nothing** while a window was already
  open – the running instance now opens a new, empty window. New: File → New window (Ctrl+N)
- Print dialog: the preset line sits above the tabs (applies to General and More options)
- Test: a folding simulation (fold, nest, stack sections) verifies for all binding types, binding left/right
  and blank-page sections that the pages come out as 1…N

## 1.7.1
- **Crop to format now scales** (default): the fitting edge is scaled exactly onto the target format, the
  overhang of the other edge cut off equally on both sides – A4 → A6 = 50 %, a narrow poster fills the width
  and loses equally much at top and bottom. Smaller pages are scaled up. Content stays vector. Previously
  only cutting took place; that remains available as an option (uncheck "Scale until the format is completely
  filled" or `--set crop_scale=false`) for files that already come in final size with bleed.
- Command line/chains: `preflight_fix --set fix=flatten_layers` no longer aborts on files without layers but
  passes the file through unchanged (note "No layers")

## 1.7.0
- **Workspaces:** second bar below the tool bar – *View & Print*, *Print preparation*, *Edit*, *Automation*.
  To its right the tools of the chosen area (e.g. check, CMYK, crop, CutContour, separate objects, repair).
  Print preparation opens the preflight, Edit the sidebar; leaving the area ends the edit mode. The last chosen
  area applies at the next start. The menus stay complete.
- **Presets:** in the CutContour, CMYK/crop windows and in the print dialog the line *Preset* at the top –
  select, *Save…*, delete, export/load as file, defaults. Print presets cover page handling, Several,
  booklet, poster, step & repeat and more options (without printer and tray).
  Storage: Linux `~/.config/passermark/presets/`, Windows `%APPDATA%\Passermark\presets\`
- CutContour remembers the last used settings (without the shape's offset)
- **Command line:** `--preset NAME` finds a preset stored in the program; `passermark-cli presets [job]`
  lists them. Guide extended.
- **Save as PDF with password** (print dialog, destination "Save as PDF"): check *Protect PDF with password*
  (AES-256, enter the password twice)
- **Windows setup:** optional *make passermark-cli available in every command prompt* (search path PATH;
  removed again on uninstall)
- Keyboard shortcuts without double assignments: Measure is now Ctrl+Shift+L (Ctrl+Shift+M = CMYK and crop),
  Edit text and layers Ctrl+T (Ctrl+E = export selection), select page text Ctrl+Alt+A (Ctrl+Shift+A = select
  all pages); a test checks this from now on
- Own icons for CutContour, CMYK, crop, Separate objects, Edit, Check, Repair, Measure and others (previously
  some icons were assigned twice)

## 1.6.7
- **Time-budget tests in the GitHub build** (tests/test_performance.py): CutContour (contour + overfill,
  rectangle), object detection, PDF build-up and booklet are measured – relative to a calibration task on
  the same machine, so differently fast build machines do not raise false alarms. From 1.6× slower than
  before a yellow build warning, from 3× the build fails. Reference values in tests/perf_baseline.json
  (re-measure: `python3 tests/test_performance.py --messen`)

## 1.6.6
- **Fixed: blank sheets when printing under Windows** (various devices). "Automatic" now always rasterises
  without JPEG (300 dpi) – the most compatible way. PostScript and JPEG pass-through are reported as
  supported by some drivers and then deliver blank sheets; both are only available on request
  (File → Settings)
- New: **Help → Test Windows printing** – a labelled test page per method (raster, raster + JPEG, PostScript,
  vector); shows what the driver really can do
- Windows printing: the device context is passed as a 64-bit pointer (previously ctypes default int),
  halftone mode when rasterising; every job is recorded in `druck-windows.log` in the log folder (method,
  resolution, driver capabilities)
- **Fixed: reddish rectangle over the object (CutContour)** when a program or printer driver does not evaluate
  the transparency of the overfill/edge images (among others the Windows PostScript path): invisible areas
  are now paper white or show the original motif instead of the first spot colour

## 1.6.5
- **Error log:** every error lands in a file ready to send along (with versions and system details) – Linux
  `~/.local/state/passermark/logs`, Windows `%LOCALAPPDATA%\Passermark\logs`; Help → Open error logs
  - unexpected error: message with the log path, Passermark keeps running
  - hard crash (e.g. in a library): one-time message with the log at the next start
  - errors in background jobs including details; errors in threads
  - without errors the log is deleted on exit; at most 10 are kept
- Parallel computing: memory budget according to the machine's actual RAM (40 %, at least 1 GB)

## 1.6.4
- CutContour with **several pages: whole pages in parallel** – each worker processes one complete page
  (rendering and detection included); no more stalling between pages. One page: objects still in parallel
- Memory protection: number of simultaneous pages according to estimated memory requirement (e.g. A4: up to
  8, A0: 1 – then objects in parallel)
- Progress with several pages: "3 of 12 pages done"; result bit-identical to serial processing

## 1.6.3
- **Parallel computing:** CutContour distributes a page's objects over several cores (all but one, at most
  8); result bit-identical to serial processing. Workers are started once per job and used for all pages;
  small tasks stay serial (not worth it there). Limit with the environment variable `PASSERMARK_WORKERS`
  (1 = not parallel)
- Progress per object ("Page 1/1 · object 12/40")
- Cancel also terminates the workers
- Internal: object computation as its own function; program entry points call
  `multiprocessing.freeze_support()`

## 1.6.2
- **No more freezing:** CutContour, Separate objects and CMYK/crop compute as a separate process in the
  background. The window stays usable; progress and a cancel button (✕) at the bottom of the status bar;
  several jobs at once possible; the result opens in a new window as usual
- A crash during computation no longer takes the program down – you get an error message with details
- Closing a window cancels running jobs and cleans up
- Guide: corrected the example "PDF/A with password" (PDF/A forbids encryption) – split into "PDF/A" and
  "Protect with password"; the example test now creates an input for every example (build failure under
  Linux)

## 1.6.1
- **Guide for the command line** (PDF, 6 pages) with case examples for all jobs, presets and whole folders
  (Linux and Windows); in the program under **Help → Command line – guide**
- The guide's case examples are tested automatically (tests/test_cli_howto.py) – the guide cannot silently
  go stale; generate with `python3 docs/make_cli_howto.py`

## 1.6.0
- **Command line** `passermark-cli`: CutContour, Separate objects, CMYK/crop, Repair and preflight fixes
  without the GUI; settings via `--preset file.json` and `--set key=value` (nested too), `--pages`, progress
  bar, Ctrl+C aborts cleanly, `--json-progress` for programs. Linux: `passermark-cli` (install.sh),
  AppImage: `… --cli`, Windows: `passermark-cli.exe`
- Internal: core interface `core.py` (input PDF + settings → output PDF, progress, cancel, atomic writing) –
  the foundation for jobs in their own process, presets and watchers

## 1.5.3
- CutContour computes faster (approx. 17–20 %), result bit-identical to 1.5.2: motif detection computes with
  integers, spot colour search only in the border strip, unnecessary distance calculations dropped (among
  others one per object during smoothing, one when exempting below 0.08 mm)

## 1.5.2
- CutContour basic shapes: **handles** on the shape in the preview – corner handles scale evenly from the
  centre, side handles only width or height, a **move handle** above the shape moves it
- Size only in **mm** ("Size (W × H)", "auto" = from the motif plus distance); percentage dropped. An entered
  size applies exactly as the cut line; dragging the handles writes the mm values into the fields
- New: **offset (X / Y)** in mm, with a reset button
- Fixed: after scaling with the mouse, entered sizes had no effect (hidden percentage factor)
- Display at the bottom: current shape size in mm, live while dragging

## 1.5.1
- CutContour with a basic shape (rectangle, circle, heart …): **one shape around the whole motif** instead of
  one per detected part; sits centred, size changes from the centre. Option "One shape per object" for
  sticker sheets
- CutContour: **drag the shape larger/smaller with the mouse** in the preview (live display in %, applied on
  release)
- The circle encloses the motif (larger side as diameter) instead of cutting through wide motifs

## 1.5.0
- **Rulers and measuring** (View → Show rulers, Ctrl+R; View → Measure, Ctrl+Shift+M, also in the tool bar):
  rulers in mm at the top and left edge of the view, stay put while scrolling, origin = top left page corner,
  mouse position marked; measure: 1st click start, 2nd click end, Shift snaps horizontally/vertically/45°,
  Esc cancels; result (length, ΔX, ΔY, angle) at the bottom right of the status bar; measured in real page
  dimensions, independent of zoom and rotation

## 1.4.7
- CutContour: the preview refreshes automatically with every setting – previously it kept showing the old
  contour after a shape change (rectangle, circle, heart …) until you pressed "Refresh preview"
- CutContour: the preview computes in the background, the window stays usable ("Computing preview …"); quick
  consecutive changes trigger only one computation
- New test (tests/test_cut_dialog.py): a shape change changes the preview

## 1.4.6
- Fixed: the program did not start under Python 3.10/3.11 (e.g. Ubuntu 22.04) – syntax in convert.py that is
  only allowed from Python 3.12; the AppImage build checks this as a first step now
- AppImage: an installed Ghostscript takes precedence, the bundled one serves as fallback; if it fails to
  start during the build it is removed with a warning (the build does not abort)
- **Ready-made programs via GitHub:** Windows Setup.exe and Linux AppImage are built on every push, published
  as releases for tags `v*`; dependencies (Python, Qt, all packages, Ghostscript) are included
- Self-test of the finished program file in the build (`--selftest`); `--version`
- Ghostscript is found alongside the program file (installer/AppImage bundle it)
- AppImage: saving admin defaults via pkexec with the same hardened helper
- Fixed: admin window not scrollable on small screens (tabs scroll, the window adapts)
- Fixed: touchpad scrolling (page change/zoom) under Windows
- `uninstall.sh`, `.gitignore`; installer script UTF-8 with BOM; `build.ps1` pure ASCII; README in English

## 1.4.5
- **Windows printing redone** (as pdfToolkit 1.4.3): PostScript directly for PS drivers, otherwise own
  strip-wise rasterising with JPEG – fixes long spooling and aborts (especially with step & repeat);
  settings under File → Settings → "Printing under Windows". Linux printing unchanged
- Fixed: possible crashes – document checking used pdfium in a background thread at the same time as the
  view (pdfium is not thread-safe); those parts now run in the main thread

## 1.4.4
- **Cause found** (on a Chrome PDF): pdfium cannot rewrite pages with **Type3 fonts** – previously all text
  disappeared. Editing now gets by without regenerating the page at all:
  - Move/scale: the line is lifted out of its text block (the line matrix is carried along), even when many
    lines share one block
  - Change text/font: first directly; if the page loses content, the old line is removed and the new one
    placed on top at the same spot and in the same colour
  - Delete: only the line's text operators are removed
- The coordinate system is carried along (Chrome: scale 0.24 + mirrored; CAD: 0.12) – when moving text and
  layers, when replacing layers and for the CutContour line (original content is wrapped in q/Q)
- Lines are detected better (also with a font change inside the line and individually placed letters)
- Post-check more sensitive (also on pages with little text)
- New tests: Chrome-like Type3 file, CAD layer in a scaled coordinate system

## 1.4.3
- Fixed: after moving/scaling with the mouse, changing text or switching fonts, all texts of the page could
  disappear
  - Moving/scaling text now changes only the affected text blocks in the PDF (q/cm/Q), the rest of the page
    stays byte-identical; pdfium's page regeneration only as a fallback
  - every text edit runs on a copy and is **post-checked** (characters and pixels outside the edited line);
    if anything is missing, nothing is applied and a message with details appears
  - the view releases its open pages before editing
- Start test much stricter (missing own methods show up immediately) and now also checks changing text,
  switching fonts and deleting – all other lines stay intact

## 1.4.2
- Fixed: "don't know how to encode value np.float64" when scaling layers (reference "centre of the layer")
- Fixed: mouse selection in edit mode found nothing when the lists had not been loaded on activation
- **Move and scale with the mouse:** grab an object (text line/layer) and drag; scale at the four corner
  handles (opposite corner stays fixed); dashed preview, matching cursors, undo
- Moving/scaling text lines keeps font, colour and layer
- Finer layer detection; the start test now also checks mouse operation

## 1.4.1
- Fixed: the program did not start (name conflict in the page view caused by the new text selection)
- Fixed: Ctrl+C (copy text) would have raised an error (missing import)
- New start test (tests/test_gui_smoke.py): program start, window, text selection, edit mode – without a
  screen

## 1.4.0
- **Edit mode** (Document manipulation → Edit text and layers, Ctrl+E): sidebar "Edit"
  - **Text:** list the page's lines or click them on the page; change text, font (original, standard fonts,
    own file) and size, delete a line
  - **Layers:** list or click on the page (repeated clicking cycles through overlapping ones); show/hide,
    remove, scale/move (including "bring back onto the page"), replace by a page of another PDF; undo
- **Select text** in the page view (drag, double-click = word, Ctrl+C copies)
- Font download: own buttons under the table, visible error messages, fallback to the fontsource CDN
- Translations: missing texts added (print dialog, admin, merge, file filters, messages), "&" spelled out in
  translations, German driver terms (German-installed PPDs) are translated

## 1.3.2
- Fixed: the "Download free font" dialog did not open
- Flatten layers / recommended fixes: if view and print differ, Passermark asks which state should apply
  ("as printed" / "as on screen") – instead of silently taking the print state
- Embedding: warning when no substitute has been chosen for a missing font (otherwise Ghostscript would pick
  its own)
- CAD standard fonts (ISOCPEUR & co.) without osifont: narrow fallback font (DejaVu Sans Condensed)
- Fonts with their own glyph names (without embedding) are recognised as not repairable

## 1.3.1
- Font download: commercial fonts are redirected to their free, metrically identical twin (Arial → Arimo,
  Times New Roman → Tinos, Courier New → Cousine, Calibri → Carlito, Cambria → Caladea, Georgia → Gelasio);
  the dialog suggests it and explains why
- Unknown name: suggestions of similar free fonts ("Did you mean …") instead of just "404"

## 1.3.0
- **New name: Passermark** (previously pdfToolbox – name clash with a commercial preflight product); own
  paths (/etc/passermark, /usr/local/lib/passermark), runs alongside pdfToolkit/pdfToolbox
- **Document check (preflight)** on opening: fonts (embedding, type, Unicode, strange characters), layers
  (view/print, misaligned), transparencies; status button, sidebar "Check", report
- Fixes: adopt layer state, flatten the visible state, remove layers, embed fonts with a metrically
  compatible substitute / own file / download (fontsource.org), text to paths, reduce transparencies
- install.sh: free substitute fonts (Liberation, Carlito, Caladea, URW, DejaVu)

## 1.2.5
- CutContour: **overfill can be switched off** ("generate" or 0 mm) – the motif stays unchanged (no overfill,
  no cut-out), only the cut line; with a positive "distance to motif" white margins appear

## 1.2.4
- CutContour colours: **unmixing** instead of RGB distance – edge pixels are interpreted as a mix of spot
  colour + background or spot colour + spot colour (light pink = red, not green); fixes wrongly coloured
  wedges in the overfill
- Overfill colour comes from this mapping; inside the cut shape always fully opaque
- Cut-out: tiny holes closed (no white dots), tighter tolerance (no light streak)
- New: **overfill colour can be fixed** (even margin) for motifs where the automatic does not fit
- New (optional): **clean mixed edges in the motif** (narrow seams up to ~1 mm between spot colours)

## 1.2.3
- CutContour overfill in **spot colours**: colour = computationally nearest spot colour of the object (exact
  original tone), no more pale mixed tones from anti-aliasing/scaled rasters
- **Light halo removed:** for motifs with a background the mixed fringe at the edge is exempted (flat motifs:
  adaptively up to 1.5 mm, photos: 0.25 mm) – the spot-coloured overfill sits there
- **Inner cut with overfill:** cut-out holes are exempted in the original, the overfill runs over the inner
  cut line; small inner areas (white lettering) remain

## 1.2.2
- Fixed: error "don't know how to encode value np.float64" with "every object as its own page" + overfill
  (page dimensions are now passed to pikepdf as plain numbers)
- Fixed: overfill invisible for motifs with a background (white page, raster image) – the original is
  clipped to the object shape (background punched out), inner areas like white lettering remain; the preview
  likewise

## 1.2.1
- Separate objects: the **margin takes effect immediately** (negative too, also on hand-drawn frames) –
  previously only after "re-detect"; dashed preview of the margin; the other sliders re-detect automatically
- CutContour: the **overfill fills the whole area inside the cut line** (space between object and line,
  indentations) plus overfill beyond the line – border colours (multi-coloured too) pulled outwards, sits
  behind the object; colours taken from the core (no mixed colours from anti-aliasing)
- Error messages in the object dialogs with "Details" (trace to copy)

## 1.2.0
- CutContour: **sticker shapes** rectangle, rounded rectangle, circle, oval, hexagon, octagon, heart, star,
  crest, arch – at object size, scalable (%) or fixed size (mm); distance negative too
- CutContour: the **overfill follows the object** (no frames in empty areas); a cut on the motif always lies
  inside the overfill
- CutContour: output optionally **every object as its own page** with a margin (default 6 mm), neighbours
  hidden
- Detection: a motif filling the whole page is detected as one object (the contour previously hung on the
  page edge); auto mode detects the background also on partially transparent pages
- Separate objects: margin **negative** too (inwards)

## 1.1.0
- **Separate objects:** detect objects (business cards, photos on scans …) and open them as single pages
  without white space; vector exactly via transparency, raster via background colour; editable frame
- **CutContour** for cutting plotters (Roland VersaWorks): spot colour "CutContour", distance, smoothing for
  weeding, automatically generated overfill (the cut always lies inside it), inner contours, preview
- **Open SVG/SVGZ** (vectorial, true size; rsvg-convert > Inkscape > Qt), also via right-click and merge
- Transparency in WebP/GIF/HEIC is preserved (instead of being flattened onto white)
- New dependencies: scipy, contourpy, librsvg2-bin

## 1.0.1
- Document manipulation now as its own menu next to "Document" (CMYK conversion, crop, both); no longer in
  the print dialog
- The result opens in a new window, stored only temporarily in the cache (deleted on exit)
- Fixed: cropping had no effect when printing – the cropped file itself is now printed (end-to-end test:
  crop -> cache -> print, margin disappears)
- Menu "Document": merge and repair/optimize

## 1.0.0 (October 2026)
First version of Passermark, built on pdfToolkit 1.4.0 (all features adopted).

- **Document manipulation** (tab in the print dialog and Document menu):
  - CMYK conversion: RGB→CMYK with unchanged CMYK, complete re-separation (source → destination profile),
    greyscale; intent, BPC, grey/black with K only, Output Intent
  - Colour preview before/after from real CMYK values, individual separations, total area coverage (TAC),
    paper white
  - Crop to target format with the overhang cut off equally on both sides, portrait/landscape follows the
    page
- Independently installable alongside pdfToolkit (own paths, admin helper, polkit rule, single instance)
- Own icon; all texts in German, English, Hungarian, Spanish, French
