; SPDX-License-Identifier: GPL-3.0-or-later
; Passermark – Windows-Installer (Inno Setup 6). Aufruf: iscc windows\passermark.iss
#define AppVersion GetEnv("PASSERMARK_VERSION")
#if AppVersion == ""
  #define AppVersion "1.7.0"
#endif

[Setup]
AppId={{8C2E5A17-4B9D-4F36-A1E2-7D90C3B5F468}
AppName=Passermark
AppVersion={#AppVersion}
AppPublisher=Hias
DefaultDirName={autopf}\Passermark
DefaultGroupName=Passermark
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=Passermark-{#AppVersion}-Setup
SetupIconFile=passermark.ico
UninstallDisplayIcon={app}\passermark.exe
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ChangesAssociations=yes
ChangesEnvironment=yes

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "hu"; MessagesFile: "compiler:Languages\Hungarian.isl"
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[CustomMessages]
de.AddPath=Kommandozeile „passermark-cli“ in jeder Eingabeaufforderung verfügbar machen (Suchpfad PATH)
en.AddPath=Make the command line “passermark-cli” available in every command prompt (PATH)
hu.AddPath=A „passermark-cli” parancssor elérhetővé tétele minden parancssorban (PATH)
es.AddPath=Hacer disponible la línea de comandos «passermark-cli» en cualquier consola (PATH)
fr.AddPath=Rendre la ligne de commande « passermark-cli » disponible dans toutes les invites (PATH)
de.Print=Drucken (Passermark)
en.Print=Print (Passermark)
hu.Print=Nyomtatás (Passermark)
es.Print=Imprimir (Passermark)
fr.Print=Imprimer (Passermark)
de.Merge=Als ein PDF zusammenführen (Passermark)
en.Merge=Merge into one PDF (Passermark)
hu.Merge=Egyesítés egy PDF-be (Passermark)
es.Merge=Combinar en un PDF (Passermark)
fr.Merge=Fusionner en un PDF (Passermark)
de.Repair=Reparieren / optimieren (Passermark)
en.Repair=Repair / optimize (Passermark)
hu.Repair=Javítás / optimalizálás (Passermark)
es.Repair=Reparar / optimizar (Passermark)
fr.Repair=Réparer / optimiser (Passermark)
de.OpenWith=Mit Passermark öffnen
en.OpenWith=Open with Passermark
hu.OpenWith=Megnyitás a Passermarktel
es.OpenWith=Abrir con Passermark
fr.OpenWith=Ouvrir avec Passermark
de.OpenAsPdf=Als PDF öffnen (Passermark)
en.OpenAsPdf=Open as PDF (Passermark)
hu.OpenAsPdf=Megnyitás PDF-ként (Passermark)
es.OpenAsPdf=Abrir como PDF (Passermark)
fr.OpenAsPdf=Ouvrir en PDF (Passermark)
de.Desktop=Desktop-Verknüpfung anlegen
en.Desktop=Create desktop shortcut
hu.Desktop=Asztali parancsikon létrehozása
es.Desktop=Crear acceso directo en el escritorio
fr.Desktop=Créer un raccourci sur le bureau
de.Launch=Passermark starten
en.Launch=Start Passermark
hu.Launch=A Passermark indítása
es.Launch=Iniciar Passermark
fr.Launch=Lancer Passermark

[Files]
Source: "..\dist\passermark\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Dirs]
Name: "{commonappdata}\Passermark"
Name: "{commonappdata}\Passermark\icc"

[Icons]
Name: "{group}\Passermark"; Filename: "{app}\passermark.exe"
Name: "{autodesktop}\Passermark"; Filename: "{app}\passermark.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:Desktop}"; Flags: unchecked
Name: "addtopath"; Description: "{cm:AddPath}"; Flags: unchecked

[Run]
; Admin-Standards: nur Administratoren und SYSTEM dürfen schreiben, Benutzer nur lesen (SIDs = sprachunabhängig)
Filename: "{sys}\icacls.exe"; Parameters: """{commonappdata}\Passermark"" /inheritance:r /grant:r *S-1-5-32-544:(OI)(CI)F *S-1-5-18:(OI)(CI)F *S-1-5-32-545:(OI)(CI)RX"; Flags: runhidden waituntilterminated
Filename: "{app}\passermark.exe"; Description: "{cm:Launch}"; Flags: postinstall nowait skipifsilent unchecked

[Registry]
; Kommandozeile: Programmordner zum System-Suchpfad (optional, beim Deinstallieren wieder entfernt – siehe [Code])
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Tasks: addtopath; Check: NeedsAddPath(ExpandConstant('{app}'))
; Explorer-Kontextmenü in der Installationssprache (Windows 11: unter „Weitere Optionen anzeigen“)
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\passermark.print"; ValueType: string; ValueName: ""; ValueData: "{cm:Print}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\passermark.print"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\passermark.print"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\passermark.print\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --print ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\passermark.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\passermark.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\passermark.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\passermark.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\passermark.repair"; ValueType: string; ValueName: ""; ValueData: "{cm:Repair}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\passermark.repair"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\passermark.repair"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\passermark.repair\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --repair ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\passermark.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenWith}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\passermark.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\passermark.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\passermark.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\passermark.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\passermark.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\passermark.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\passermark.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\passermark.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\passermark.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\passermark.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\passermark.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\passermark.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\passermark.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\passermark.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\passermark.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\passermark.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\passermark.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\passermark.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\passermark.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\passermark.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\passermark.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\passermark.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\passermark.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\passermark.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\passermark.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\passermark.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\passermark.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.tif\shell\passermark.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.tif\shell\passermark.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.tif\shell\passermark.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.tif\shell\passermark.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.tif\shell\passermark.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.tif\shell\passermark.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.tif\shell\passermark.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.tif\shell\passermark.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.tiff\shell\passermark.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.tiff\shell\passermark.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.tiff\shell\passermark.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.tiff\shell\passermark.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.tiff\shell\passermark.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.tiff\shell\passermark.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.tiff\shell\passermark.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.tiff\shell\passermark.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\passermark.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\passermark.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\passermark.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\passermark.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\passermark.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\passermark.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\passermark.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\passermark.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\passermark.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\passermark.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\passermark.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\passermark.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\passermark.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\passermark.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\passermark.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\passermark.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\passermark.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\passermark.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\passermark.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\passermark.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\passermark.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\passermark.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\passermark.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\passermark.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.heic\shell\passermark.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.heic\shell\passermark.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.heic\shell\passermark.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.heic\shell\passermark.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.heic\shell\passermark.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.heic\shell\passermark.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.heic\shell\passermark.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.heic\shell\passermark.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.heif\shell\passermark.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.heif\shell\passermark.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.heif\shell\passermark.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.heif\shell\passermark.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.heif\shell\passermark.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.heif\shell\passermark.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.heif\shell\passermark.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.heif\shell\passermark.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.doc\shell\passermark.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.doc\shell\passermark.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.doc\shell\passermark.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.doc\shell\passermark.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.doc\shell\passermark.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.doc\shell\passermark.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.doc\shell\passermark.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.doc\shell\passermark.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.docx\shell\passermark.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.docx\shell\passermark.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.docx\shell\passermark.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.docx\shell\passermark.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.docx\shell\passermark.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.docx\shell\passermark.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.docx\shell\passermark.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.docx\shell\passermark.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.odt\shell\passermark.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.odt\shell\passermark.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.odt\shell\passermark.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.odt\shell\passermark.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.odt\shell\passermark.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.odt\shell\passermark.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.odt\shell\passermark.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.odt\shell\passermark.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.rtf\shell\passermark.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.rtf\shell\passermark.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.rtf\shell\passermark.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.rtf\shell\passermark.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.rtf\shell\passermark.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.rtf\shell\passermark.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.rtf\shell\passermark.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.rtf\shell\passermark.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.txt\shell\passermark.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.txt\shell\passermark.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.txt\shell\passermark.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.txt\shell\passermark.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.txt\shell\passermark.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.txt\shell\passermark.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.txt\shell\passermark.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.txt\shell\passermark.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.xls\shell\passermark.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.xls\shell\passermark.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.xls\shell\passermark.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.xls\shell\passermark.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.xls\shell\passermark.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.xls\shell\passermark.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.xls\shell\passermark.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.xls\shell\passermark.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.xlsx\shell\passermark.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.xlsx\shell\passermark.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.xlsx\shell\passermark.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.xlsx\shell\passermark.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.xlsx\shell\passermark.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.xlsx\shell\passermark.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.xlsx\shell\passermark.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.xlsx\shell\passermark.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.ods\shell\passermark.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.ods\shell\passermark.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.ods\shell\passermark.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.ods\shell\passermark.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.ods\shell\passermark.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.ods\shell\passermark.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.ods\shell\passermark.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.ods\shell\passermark.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.csv\shell\passermark.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.csv\shell\passermark.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.csv\shell\passermark.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.csv\shell\passermark.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.csv\shell\passermark.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.csv\shell\passermark.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.csv\shell\passermark.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.csv\shell\passermark.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.ppt\shell\passermark.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.ppt\shell\passermark.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.ppt\shell\passermark.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.ppt\shell\passermark.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.ppt\shell\passermark.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.ppt\shell\passermark.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.ppt\shell\passermark.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.ppt\shell\passermark.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pptx\shell\passermark.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pptx\shell\passermark.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pptx\shell\passermark.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pptx\shell\passermark.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pptx\shell\passermark.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pptx\shell\passermark.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pptx\shell\passermark.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.pptx\shell\passermark.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.odp\shell\passermark.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.odp\shell\passermark.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.odp\shell\passermark.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.odp\shell\passermark.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.odp\shell\passermark.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.odp\shell\passermark.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.odp\shell\passermark.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.odp\shell\passermark.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.svg\shell\passermark.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.svg\shell\passermark.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.svg\shell\passermark.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.svg\shell\passermark.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.svg\shell\passermark.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.svg\shell\passermark.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.svg\shell\passermark.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.svg\shell\passermark.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --merge ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.svgz\shell\passermark.open"; ValueType: string; ValueName: ""; ValueData: "{cm:OpenAsPdf}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.svgz\shell\passermark.open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.svgz\shell\passermark.open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.svgz\shell\passermark.open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --open ""%1"""
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.svgz\shell\passermark.merge"; ValueType: string; ValueName: ""; ValueData: "{cm:Merge}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.svgz\shell\passermark.merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\passermark.exe"",0"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.svgz\shell\passermark.merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKLM; Subkey: "Software\Classes\SystemFileAssociations\.svgz\shell\passermark.merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\passermark.exe"" --merge ""%1"""

[Code]
const
  EnvKey = 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment';

function NeedsAddPath(Dir: string): Boolean;
var
  Paths: string;
begin
  if not RegQueryStringValue(HKEY_LOCAL_MACHINE, EnvKey, 'Path', Paths) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Uppercase(Dir) + ';', ';' + Uppercase(Paths) + ';') = 0;
end;

procedure RemovePath(Dir: string);
var
  Paths: string;
  P: Integer;
begin
  if not RegQueryStringValue(HKEY_LOCAL_MACHINE, EnvKey, 'Path', Paths) then
    exit;
  Paths := ';' + Paths + ';';
  P := Pos(';' + Uppercase(Dir) + ';', Uppercase(Paths));
  if P = 0 then
    exit;
  Delete(Paths, P, Length(Dir) + 1);
  Paths := Copy(Paths, 2, Length(Paths) - 2);
  RegWriteExpandStringValue(HKEY_LOCAL_MACHINE, EnvKey, 'Path', Paths);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RemovePath(ExpandConstant('{app}'));
end;
