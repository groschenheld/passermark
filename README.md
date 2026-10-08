# Passermark 1.5.3

PDF viewer, print tool and prepress toolbox for **Linux and Windows**. Free software (GPL-3.0-or-later).

## Features

- **View and print** PDFs, images (incl. HEIC, SVG) and Office files (via LibreOffice). Uses the printer
  drivers already installed on your system (CUPS on Linux, Windows drivers) with all their options.
- **Imposition:** fit/scale, N-up, booklet, poster tiling, step & repeat.
- **Document manipulation:** CMYK conversion with colour preview, crop to format, separate objects,
  **CutContour** for cutting plotters (contour, shapes, bleed, inner cuts; resize and move shapes with handles).
- **Preflight:** checks fonts, layers and transparency when a document is opened; fixes: embed or substitute
  fonts (free metric-compatible fonts or download from fontsource.org), outline text, fix/remove layers,
  flatten transparency.
- **Edit mode:** select text lines and layers with the mouse; change text, font and size; move, scale,
  hide, remove or replace layers; undo.
- Rulers and measuring: rulers in mm at the edge of the view; click start and end to measure (Shift snaps to
  horizontal/vertical/45°), result in the status bar.
- Repair/optimise PDFs, PDF/A, merge files, select and copy text.
- Languages: English, German, Hungarian, Spanish, French.

## Install

**Windows:** download `Passermark-<version>-Setup.exe` from
[Releases](../../releases) and run it. Everything is included (Python, Qt, Ghostscript).

**Linux (any distro):** download `Passermark-<version>-x86_64.AppImage` from [Releases](../../releases), then
```sh
chmod +x Passermark-*-x86_64.AppImage
./Passermark-*-x86_64.AppImage
```

**Linux (Debian/Ubuntu, system install with file-manager integration):**
```sh
sudo ./install.sh        # installs dependencies via apt, desktop entry, Nautilus menu
sudo ./uninstall.sh      # remove again (--dry-run to preview, --purge also removes /etc/passermark)
```

Optional: LibreOffice (Office files), 7-Zip (ICC profile import from archives).

## Build

Every push to `main` builds the Windows installer and the Linux AppImage on GitHub (**Actions**); both are
checked with `--selftest`. Pushing a tag `v*` (e.g. `git tag v1.5.3 && git push origin v1.5.3`) attaches them
to a GitHub Release.

Local builds: `powershell -ExecutionPolicy Bypass -File windows\build.ps1` (Windows, needs Python 3.12 and
Inno Setup 6) or `./linux/build-appimage.sh` (Linux, see the script header for packages).

Tests: `python3 tests/test_<name>.py` (no test framework needed).

## Licence

GPL-3.0-or-later, see `LICENSE`. The Windows installer and the AppImage include
[Ghostscript](https://ghostscript.com) (AGPL-3.0, Artifex Software).
