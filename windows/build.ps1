# SPDX-License-Identifier: GPL-3.0-or-later
# Build Passermark for Windows: Python 3.12 (x64) and Inno Setup 6 required.
# Bundles Ghostscript next to the program (repair/optimize/CMYK work out of the box).
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

# --- Ghostscript version (adjust on new releases) --------------------------
$GsVersion = "10.05.1"
$GsTag     = "gs10051"   # Artifex release tag
$GsUrl     = "https://github.com/ArtifexSoftware/ghostpdl-downloads/releases/download/$GsTag/$($GsTag)w64.exe"

# --- Download + EXTRACT Ghostscript (never run installers on CI - they hang)
$GsStage = Join-Path (Get-Location) "build\gs"
if (-not (Test-Path "$GsStage\bin\gswin64c.exe")) {
    New-Item -ItemType Directory -Force -Path "build" | Out-Null
    curl.exe -L --fail --retry 3 --retry-delay 5 -o "build\gs-setup.exe" $GsUrl
    if (-not (Test-Path "build\gs-setup.exe")) { throw "Ghostscript download failed: $GsUrl" }
    7z x "build\gs-setup.exe" -o"build\gs-extract" -y | Out-Null
    $appDir = Get-ChildItem "build\gs-extract" -Recurse -Directory -Filter "bin" |
        Where-Object { Test-Path (Join-Path $_.FullName "gswin64c.exe") } |
        Select-Object -First 1
    if (-not $appDir) { throw "gswin64c.exe not found after extraction" }
    New-Item -ItemType Directory -Force -Path $GsStage | Out-Null
    Copy-Item -Recurse -Force "$($appDir.Parent.FullName)\*" $GsStage
    Remove-Item "build\gs-setup.exe","build\gs-extract" -Recurse -Force
}

# --- Python environment + PyInstaller --------------------------------------
python -m venv .venv-win
.\.venv-win\Scripts\pip install --upgrade pip
.\.venv-win\Scripts\pip install -r requirements-windows.txt pyinstaller
.\.venv-win\Scripts\python windows\make_icon.py

# --- Build program folder ---------------------------------------------------
.\.venv-win\Scripts\pyinstaller --noconfirm windows\passermark.spec --distpath dist --workpath build

# --- Put Ghostscript next to the program (platform.py finds it there) ------
$GsDest = "dist\passermark\gs\gs$GsVersion"
New-Item -ItemType Directory -Force -Path $GsDest | Out-Null
Copy-Item -Recurse -Force "$GsStage\*" $GsDest

# --- Build the installer ----------------------------------------------------
$iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
& $iscc windows\passermark.iss
Write-Host "Done: dist\Passermark-*-Setup.exe (with bundled Ghostscript)"
