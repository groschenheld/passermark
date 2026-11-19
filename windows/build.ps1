# SPDX-License-Identifier: GPL-3.0-or-later
# Build the Passermark Windows installer (ASCII ONLY in this file - non-ASCII breaks PowerShell on CI runners).
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
# program icon from data\passermark.svg – delete the old one first: if the generation fails, the build must
# stop instead of quietly using an earlier passermark.ico (old icon)
Remove-Item "windows\passermark.ico" -Force -ErrorAction SilentlyContinue
.\.venv-win\Scripts\python windows\make_icon.py
if ($LASTEXITCODE -ne 0 -or -not (Test-Path "windows\passermark.ico")) { throw "make_icon.py failed (passermark.ico)" }
.\.venv-win\Scripts\pyinstaller --noconfirm windows\passermark.spec --distpath dist --workpath build\pyi
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

# Ghostscript next to the program (pdfdruck/platform.py finds it there)
$GsDest = "dist\passermark\gs\gs$GsVersion"
New-Item -ItemType Directory -Force -Path $GsDest | Out-Null
Copy-Item -Recurse -Force "$GsStage\*" $GsDest

# rsvg-convert (librsvg, LGPL) from MSYS2, if installed: opens SVG as vectors instead of Qt's rasterising
# fallback. Optional – without it the program still runs. MSYS2: pacman -S mingw-w64-ucrt-x86_64-librsvg
$Msys = if ($env:MSYS2_ROOT) { $env:MSYS2_ROOT } else { "C:\msys64" }
$RsvgExe = Join-Path $Msys "ucrt64\bin\rsvg-convert.exe"
if (Test-Path $RsvgExe) {
    $RsvgDest = "dist\passermark\rsvg"
    New-Item -ItemType Directory -Force -Path $RsvgDest | Out-Null
    Copy-Item -Force $RsvgExe $RsvgDest
    # the DLLs it needs: MSYS2's ldd lists them as /ucrt64/bin/xyz.dll (Windows' own DLLs are left out)
    $Ldd = Join-Path $Msys "usr\bin\ldd.exe"
    & $Ldd $RsvgExe | ForEach-Object {
        if ($_ -match "=>\s+(/ucrt64/bin/\S+\.dll)") {
            Copy-Item -Force (Join-Path $Msys ($Matches[1].TrimStart("/") -replace "/", "\")) $RsvgDest
        }
    }
    $LicDir = Join-Path $Msys "ucrt64\share\licenses\librsvg"
    if (Test-Path $LicDir) {
        New-Item -ItemType Directory -Force -Path "dist\passermark\licenses\librsvg" | Out-Null
        Copy-Item -Force "$LicDir\*" "dist\passermark\licenses\librsvg"
    }
    New-Item -ItemType Directory -Force -Path "build" | Out-Null
    Set-Content -Encoding ascii build\t.svg '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="5" height="5"/></svg>'
    & "$RsvgDest\rsvg-convert.exe" -f pdf -o build\t.pdf build\t.svg
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path build\t.pdf)) {
        Write-Host "WARNING: bundled rsvg-convert does not run - removed (SVG then opens via Qt)"
        Remove-Item -Recurse -Force $RsvgDest
    } else { Write-Host "bundled rsvg-convert ok" }
} else {
    Write-Host "NOTE: rsvg-convert not found ($RsvgExe) - Setup without it, SVG opens via Qt"
}

# Licences of everything shipped (Python packages, Qt/PySide6 LGPL notice, Ghostscript AGPL notice)
# -> dist\passermark\licenses (installed next to the program, Help -> Licences)
$Agpl = "build\agpl-3.0.txt"
if (-not (Test-Path $Agpl)) {
    curl.exe -L --fail --retry 3 --retry-delay 5 -o $Agpl "https://www.gnu.org/licenses/agpl-3.0.txt"
}
$LicArgs = @("tools\third_party_licenses.py", "dist\passermark\licenses", "--requirements", "requirements-windows.txt",
             "--gs-version", $GsVersion)
if (Test-Path $Agpl) { $LicArgs += @("--agpl", $Agpl) } else { Write-Host "WARNING: AGPL-3.0 text download failed - notice links to gnu.org" }
.\.venv-win\Scripts\python @LicArgs
if ($LASTEXITCODE -ne 0) { throw "Licence collection failed" }
if (-not (Test-Path "dist\passermark\licenses\THIRD_PARTY_NOTICES.txt")) { throw "THIRD_PARTY_NOTICES.txt missing" }

# Self test of the finished program (all bundled dependencies incl. Ghostscript must load)
$p = Start-Process -FilePath "dist\passermark\passermark.exe" -ArgumentList "--selftest" -Wait -PassThru
$log = Join-Path $env:TEMP "passermark-selftest.log"
if (Test-Path $log) { Get-Content $log }
if ($p.ExitCode -ne 0) { throw "Self test failed (exit code $($p.ExitCode))" }

# Command line program must start (console EXE next to the GUI EXE)
& "dist\passermark\passermark-cli.exe" list
if ($LASTEXITCODE -ne 0) { throw "passermark-cli.exe does not start" }

# Installer
$Version = (.\.venv-win\Scripts\python -c "import pdfdruck; print(pdfdruck.__version__)").Trim()
$env:PASSERMARK_VERSION = $Version
$iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $iscc)) { throw "Inno Setup 6 not found: $iscc" }
& $iscc windows\passermark.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
Write-Host "Done: dist\Passermark-$Version-Setup.exe (Ghostscript included)"
