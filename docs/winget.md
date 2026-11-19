# Passermark in winget (Windows package manager)

winget is built into Windows 10/11. With an entry there, Windows users install and update Passermark with

    winget install Groschenheld.Passermark
    winget upgrade Groschenheld.Passermark      (or: winget upgrade --all)

winget builds nothing itself: the public repository `microsoft/winget-pkgs` holds a small description
(manifest: name, version, publisher, licence, download link and SHA256 of the Setup.exe). winget downloads the
Setup.exe from our GitHub release and installs it silently (Inno Setup: `/VERYSILENT`).

## First entry (once, by hand)

1. Install the tool: `winget install Microsoft.WingetCreate`
2. With a finished release on GitHub (e.g. v1.19.9):

        wingetcreate new https://github.com/groschenheld/passermark/releases/download/v1.19.9/Passermark-1.19.9-Setup.exe

   It reads the installer and asks for the rest. Suggested values:
   - PackageIdentifier: `Groschenheld.Passermark` (Publisher.Name – stays fixed afterwards)
   - Publisher: `Hias` · PackageName: `Passermark` · License: `GPL-3.0-or-later`
   - ShortDescription: `PDF printing, prepress and preflight for print shops`
   - PackageUrl / PublisherUrl: the GitHub page
3. At the end choose "submit": wingetcreate opens a pull request in `microsoft/winget-pkgs` (needs a GitHub
   login). An automatic check installs the package in a test machine; after that a moderator merges it –
   usually within a few days. Then `winget install Groschenheld.Passermark` works for everyone.

## New versions (by hand, one command)

After every stable release, on a Windows computer with wingetcreate:

    wingetcreate update Groschenheld.Passermark --version 1.20.0 --urls https://github.com/groschenheld/passermark/releases/download/v1.20.0/Passermark-1.20.0-Setup.exe --submit

wingetcreate signs in to GitHub in the browser (the login stays on that computer) and opens the pull request in
`microsoft/winget-pkgs`. Test releases (`v1.20.0-rc1`) are not sent. There is deliberately no automatic job in
the workflows: it would need a GitHub token stored as a secret.

## Notes

- The Setup.exe must stay at its URL – winget checks the SHA256 on every installation. Never replace a file
  of an existing release; make a new version instead.
- Microsoft's check runs the installer in a sandbox and warns about missing signatures (SmartScreen); an
  unsigned installer is accepted.
- The self-update of Passermark and winget do not get in each other's way: both install the same Setup.exe.
