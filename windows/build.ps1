# SPDX-License-Identifier: GPL-3.0-or-later
# Build the pdfToolkit Windows installer (ASCII ONLY in this file - non-ASCII breaks PowerShell on CI runners).
# Needs: Python 3.12 x64, Inno Setup 6, 7-Zip, curl.exe (all preinstalled on GitHub windows runners).
# Local use:  powershell -ExecutionPolicy Bypass -File windows\build.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

# Ghostscript (bundled, so repair/CMYK/fonts work without extra installs)
$GsVersion = "10.05.1"
$GsTag     = "gs10051"
$GsUrl     = "https://github.com/ArtifexSoftware/ghostpdl-downloads/releases/download/$GsTag/$($GsTag)w64.exe"

$GsStage = Join-Path (Get-Location) "build\gs"
if (-not (Test-Path "$GsStage\bin\gswin64c.exe")) {
    New-Item -ItemType Directory -Force -Path "build" | Out-Null
    curl.exe -L --fail --retry 3 --retry-delay 5 -o "build\gs-setup.exe" $GsUrl
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path "build\gs-setup.exe")) { throw "Ghostscript download failed: $GsUrl" }
    # extract, do NOT run the installer (it waits for dialogs on CI)
    7z x "build\gs-setup.exe" -o"build\gs-extract" -y | Out-Null
    $binDir = Get-ChildItem "build\gs-extract" -Recurse -Directory -Filter "bin" |
        Where-Object { Test-Path (Join-Path $_.FullName "gswin64c.exe") } | Select-Object -First 1
    if (-not $binDir) { throw "gswin64c.exe not found after extraction" }
    New-Item -ItemType Directory -Force -Path $GsStage | Out-Null
    Copy-Item -Recurse -Force "$($binDir.Parent.FullName)\*" $GsStage
    Remove-Item "build\gs-setup.exe","build\gs-extract" -Recurse -Force
}

# Python environment + PyInstaller
python -m venv .venv-win
if ($LASTEXITCODE -ne 0) { throw "python -m venv failed" }
.\.venv-win\Scripts\python -m pip install --upgrade pip
.\.venv-win\Scripts\pip install -r requirements-windows.txt pyinstaller
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
.\.venv-win\Scripts\python windows\make_icon.py
.\.venv-win\Scripts\pyinstaller --noconfirm windows\pdftoolkit.spec --distpath dist --workpath build\pyi
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

# Ghostscript next to the program (pdfdruck/platform.py finds it there)
$GsDest = "dist\pdftoolkit\gs\gs$GsVersion"
New-Item -ItemType Directory -Force -Path $GsDest | Out-Null
Copy-Item -Recurse -Force "$GsStage\*" $GsDest

# Self test of the finished program (all bundled dependencies incl. Ghostscript must load)
$p = Start-Process -FilePath "dist\pdftoolkit\pdftoolkit.exe" -ArgumentList "--selftest" -Wait -PassThru
$log = Join-Path $env:TEMP "pdftoolkit-selftest.log"
if (Test-Path $log) { Get-Content $log }
if ($p.ExitCode -ne 0) { throw "Self test failed (exit code $($p.ExitCode))" }

# Installer
$Version = (.\.venv-win\Scripts\python -c "import pdfdruck; print(pdfdruck.__version__)").Trim()
$env:PDFTOOLKIT_VERSION = $Version
$iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $iscc)) { throw "Inno Setup 6 not found: $iscc" }
& $iscc windows\pdftoolkit.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
Write-Host "Done: dist\pdfToolkit-$Version-Setup.exe (Ghostscript included)"
