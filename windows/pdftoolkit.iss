; SPDX-License-Identifier: GPL-3.0-or-later
; pdfToolkit – Windows-Installer (Inno Setup 6). Aufruf: iscc windows\pdftoolkit.iss
#define AppVersion GetEnv("PDFTOOLKIT_VERSION")
#if AppVersion == ""
  #define AppVersion "1.4.8"
#endif

[Setup]
AppId={{6D3C7E0A-1F3B-4C51-9A57-2B8E1F0C9A11}
AppName=pdfToolkit
AppVersion={#AppVersion}
AppPublisher=Hias
DefaultDirName={autopf}\pdfToolkit
DefaultGroupName=pdfToolkit
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=pdfToolkit-{#AppVersion}-Setup
SetupIconFile=pdftoolkit.ico
UninstallDisplayIcon={app}\pdftoolkit.exe
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ChangesAssociations=yes

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "hu"; MessagesFile: "compiler:Languages\Hungarian.isl"
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[CustomMessages]
de.Print=Drucken (pdfToolkit)
en.Print=Print (pdfToolkit)
hu.Print=Nyomtatás (pdfToolkit)
es.Print=Imprimir (pdfToolkit)
fr.Print=Imprimer (pdfToolkit)
de.Merge=Als ein PDF zusammenführen (pdfToolkit)
en.Merge=Merge into one PDF (pdfToolkit)
hu.Merge=Egyesítés egy PDF-be (pdfToolkit)
es.Merge=Combinar en un PDF (pdfToolkit)
fr.Merge=Fusionner en un PDF (pdfToolkit)
de.Repair=Reparieren / optimieren (pdfToolkit)
en.Repair=Repair / optimize (pdfToolkit)
hu.Repair=Javítás / optimalizálás (pdfToolkit)
es.Repair=Reparar / optimizar (pdfToolkit)
fr.Repair=Réparer / optimiser (pdfToolkit)
de.OpenWith=Mit pdfToolkit öffnen
en.OpenWith=Open with pdfToolkit
hu.OpenWith=Megnyitás a pdfToolkittel
es.OpenWith=Abrir con pdfToolkit
fr.OpenWith=Ouvrir avec pdfToolkit
de.OpenAsPdf=Als PDF öffnen (pdfToolkit)
en.OpenAsPdf=Open as PDF (pdfToolkit)
hu.OpenAsPdf=Megnyitás PDF-ként (pdfToolkit)
es.OpenAsPdf=Abrir como PDF (pdfToolkit)
fr.OpenAsPdf=Ouvrir en PDF (pdfToolkit)
de.Desktop=Desktop-Verknüpfung anlegen
en.Desktop=Create desktop shortcut
hu.Desktop=Asztali parancsikon létrehozása
es.Desktop=Crear acceso directo en el escritorio
fr.Desktop=Créer un raccourci sur le bureau
de.Launch=pdfToolkit starten
en.Launch=Start pdfToolkit
hu.Launch=A pdfToolkit indítása
es.Launch=Iniciar pdfToolkit
fr.Launch=Lancer pdfToolkit

[Files]
Source: "..\dist\pdftoolkit\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Dirs]
Name: "{commonappdata}\pdfToolkit"
Name: "{commonappdata}\pdfToolkit\icc"

[Icons]
Name: "{group}\pdfToolkit"; Filename: "{app}\pdftoolkit.exe"
Name: "{autodesktop}\pdfToolkit"; Filename: "{app}\pdftoolkit.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:Desktop}"; Flags: unchecked

[Run]
; Admin-Standards: nur Administratoren und SYSTEM dürfen schreiben, Benutzer nur lesen (SIDs = sprachunabhängig)
Filename: "{sys}\icacls.exe"; Parameters: """{commonappdata}\pdfToolkit"" /inheritance:r /grant:r *S-1-5-32-544:(OI)(CI)F *S-1-5-18:(OI)(CI)F *S-1-5-32-545:(OI)(CI)RX"; Flags: runhidden waituntilterminated
Filename: "{app}\pdftoolkit.exe"; Description: "{cm:Launch}"; Flags: postinstall nowait skipifsilent unchecked

[Registry]
; Explorer-Kontextmenü in der Installationssprache (Windows 11: unter „Weitere Optionen anzeigen“)
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\pdftoolkit.print"; ValueType: string; ValueName: ""; ValueData: "{cm:Print}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\pdftoolkit.print"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\pdftoolkit.print"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\pdftoolkit.print\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --print ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\pdftoolkit.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\pdftoolkit.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\pdftoolkit.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\pdftoolkit.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\pdftoolkit.repair"; ValueType: string; ValueName: ""; ValueData: "{cm:Repair}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\pdftoolkit.repair"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\pdftoolkit.repair"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\pdftoolkit.repair\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --repair ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\pdftoolkit.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenWith}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\pdftoolkit.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\pdftoolkit.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\pdftoolkit.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\pdftoolkit.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\pdftoolkit.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\pdftoolkit.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\pdftoolkit.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\pdftoolkit.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\pdftoolkit.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\pdftoolkit.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\pdftoolkit.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\pdftoolkit.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\pdftoolkit.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\pdftoolkit.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\pdftoolkit.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\pdftoolkit.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\pdftoolkit.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\pdftoolkit.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\pdftoolkit.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\pdftoolkit.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\pdftoolkit.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\pdftoolkit.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\pdftoolkit.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\pdftoolkit.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\pdftoolkit.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\pdftoolkit.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\pdftoolkit.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.tif\shell\pdftoolkit.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.tif\shell\pdftoolkit.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.tif\shell\pdftoolkit.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.tif\shell\pdftoolkit.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.tif\shell\pdftoolkit.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.tif\shell\pdftoolkit.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.tif\shell\pdftoolkit.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.tif\shell\pdftoolkit.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.tiff\shell\pdftoolkit.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.tiff\shell\pdftoolkit.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.tiff\shell\pdftoolkit.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.tiff\shell\pdftoolkit.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.tiff\shell\pdftoolkit.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.tiff\shell\pdftoolkit.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.tiff\shell\pdftoolkit.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.tiff\shell\pdftoolkit.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\pdftoolkit.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\pdftoolkit.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\pdftoolkit.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\pdftoolkit.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\pdftoolkit.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\pdftoolkit.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\pdftoolkit.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\pdftoolkit.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\pdftoolkit.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\pdftoolkit.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\pdftoolkit.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\pdftoolkit.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\pdftoolkit.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\pdftoolkit.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\pdftoolkit.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\pdftoolkit.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\pdftoolkit.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\pdftoolkit.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\pdftoolkit.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\pdftoolkit.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\pdftoolkit.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\pdftoolkit.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\pdftoolkit.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\pdftoolkit.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.heic\shell\pdftoolkit.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.heic\shell\pdftoolkit.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.heic\shell\pdftoolkit.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.heic\shell\pdftoolkit.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.heic\shell\pdftoolkit.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.heic\shell\pdftoolkit.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.heic\shell\pdftoolkit.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.heic\shell\pdftoolkit.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.heif\shell\pdftoolkit.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.heif\shell\pdftoolkit.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.heif\shell\pdftoolkit.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.heif\shell\pdftoolkit.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.heif\shell\pdftoolkit.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.heif\shell\pdftoolkit.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.heif\shell\pdftoolkit.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.heif\shell\pdftoolkit.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.doc\shell\pdftoolkit.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.doc\shell\pdftoolkit.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.doc\shell\pdftoolkit.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.doc\shell\pdftoolkit.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.doc\shell\pdftoolkit.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.doc\shell\pdftoolkit.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.doc\shell\pdftoolkit.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.doc\shell\pdftoolkit.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.docx\shell\pdftoolkit.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.docx\shell\pdftoolkit.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.docx\shell\pdftoolkit.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.docx\shell\pdftoolkit.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.docx\shell\pdftoolkit.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.docx\shell\pdftoolkit.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.docx\shell\pdftoolkit.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.docx\shell\pdftoolkit.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.odt\shell\pdftoolkit.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.odt\shell\pdftoolkit.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.odt\shell\pdftoolkit.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.odt\shell\pdftoolkit.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.odt\shell\pdftoolkit.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.odt\shell\pdftoolkit.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.odt\shell\pdftoolkit.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.odt\shell\pdftoolkit.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.rtf\shell\pdftoolkit.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.rtf\shell\pdftoolkit.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.rtf\shell\pdftoolkit.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.rtf\shell\pdftoolkit.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.rtf\shell\pdftoolkit.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.rtf\shell\pdftoolkit.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.rtf\shell\pdftoolkit.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.rtf\shell\pdftoolkit.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.txt\shell\pdftoolkit.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.txt\shell\pdftoolkit.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.txt\shell\pdftoolkit.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.txt\shell\pdftoolkit.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.txt\shell\pdftoolkit.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.txt\shell\pdftoolkit.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.txt\shell\pdftoolkit.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.txt\shell\pdftoolkit.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.xls\shell\pdftoolkit.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.xls\shell\pdftoolkit.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.xls\shell\pdftoolkit.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.xls\shell\pdftoolkit.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.xls\shell\pdftoolkit.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.xls\shell\pdftoolkit.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.xls\shell\pdftoolkit.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.xls\shell\pdftoolkit.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.xlsx\shell\pdftoolkit.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.xlsx\shell\pdftoolkit.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.xlsx\shell\pdftoolkit.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.xlsx\shell\pdftoolkit.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.xlsx\shell\pdftoolkit.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.xlsx\shell\pdftoolkit.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.xlsx\shell\pdftoolkit.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.xlsx\shell\pdftoolkit.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.ods\shell\pdftoolkit.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.ods\shell\pdftoolkit.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.ods\shell\pdftoolkit.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.ods\shell\pdftoolkit.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.ods\shell\pdftoolkit.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.ods\shell\pdftoolkit.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.ods\shell\pdftoolkit.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.ods\shell\pdftoolkit.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.csv\shell\pdftoolkit.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.csv\shell\pdftoolkit.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.csv\shell\pdftoolkit.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.csv\shell\pdftoolkit.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.csv\shell\pdftoolkit.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.csv\shell\pdftoolkit.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.csv\shell\pdftoolkit.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.csv\shell\pdftoolkit.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.ppt\shell\pdftoolkit.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.ppt\shell\pdftoolkit.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.ppt\shell\pdftoolkit.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.ppt\shell\pdftoolkit.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.ppt\shell\pdftoolkit.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.ppt\shell\pdftoolkit.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.ppt\shell\pdftoolkit.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.ppt\shell\pdftoolkit.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pptx\shell\pdftoolkit.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pptx\shell\pdftoolkit.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pptx\shell\pdftoolkit.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pptx\shell\pdftoolkit.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pptx\shell\pdftoolkit.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pptx\shell\pdftoolkit.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pptx\shell\pdftoolkit.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pptx\shell\pdftoolkit.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.odp\shell\pdftoolkit.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.odp\shell\pdftoolkit.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.odp\shell\pdftoolkit.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.odp\shell\pdftoolkit.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.odp\shell\pdftoolkit.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.odp\shell\pdftoolkit.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\pdftoolkit.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.odp\shell\pdftoolkit.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.odp\shell\pdftoolkit.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdftoolkit.exe"" --merge ""%1"""
