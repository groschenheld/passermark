# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Attach the Setup.exe built on this machine (windows\build.ps1) with its .sha256 to the GitHub release – the
# update function of the program needs both. Creates the release if it does not exist yet (text from the
# changelogs; a tag with a suffix becomes a pre-release).
#
#   .\windows\release_upload.ps1 v1.19.8
#
# Needs: GitHub CLI (winget install GitHub.cli, once: gh auth login), Python; the tag must be pushed.
param([Parameter(Mandatory = $true)][string]$Tag)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$AppVer = (python -c "import pdfdruck; print(pdfdruck.__version__)").Trim()
$Ver = $Tag.TrimStart("v")
if ($Ver -ne $AppVer -and -not $Ver.StartsWith("$AppVer-")) { throw "Tag $Tag does not match the program version $AppVer" }
$Setup = "dist\Passermark-$AppVer-Setup.exe"
if (-not (Test-Path $Setup)) { throw "$Setup missing – run .\windows\build.ps1 first" }

# checksum in sha256sum format ("<hash>  <file>"), as the program expects it
$Name = Split-Path $Setup -Leaf
$Hash = (Get-FileHash $Setup -Algorithm SHA256).Hash.ToLower()
"$Hash  $Name" | Out-File -Encoding ascii -NoNewline "$Setup.sha256"

gh release view $Tag *> $null
if ($LASTEXITCODE -ne 0) {
  python tools\release_notes.py $Tag "dist\notes.md"
  $Pre = @()
  if ($Ver.Contains("-")) { $Pre = @("--prerelease") }
  gh release create $Tag --verify-tag --title $Tag --notes-file "dist\notes.md" @Pre
  if ($LASTEXITCODE -ne 0) { throw "gh release create failed" }
}
gh release upload $Tag --clobber $Setup "$Setup.sha256"
if ($LASTEXITCODE -ne 0) { throw "gh release upload failed" }
Write-Host "Done: $Name and $Name.sha256 attached to $Tag"
