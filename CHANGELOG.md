# Änderungen

## 1.4.8
- **Behoben: leere Blätter beim Drucken unter Windows** (verschiedene Geräte). „Automatisch“ rastert jetzt immer
  ohne JPEG (300 dpi) – der verträglichste Weg. PostScript und JPEG-Durchreichen melden manche Treiber als
  unterstützt und liefern dann leere Blätter; beide gibt es nur noch auf Wunsch (Datei → Einstellungen)
- Neu: **Hilfe → Windows-Druck testen** – je Verfahren (Raster, Raster + JPEG, PostScript, Vektor) eine
  beschriftete Testseite; zeigt, was der Treiber wirklich kann
- Windows-Druck: Gerätekontext als 64-bit-Zeiger, Halbton-Modus beim Rastern; jeder Auftrag wird in
  `druck-windows.log` im Protokollordner festgehalten (Verfahren, Auflösung, Treiber-Fähigkeiten)

## 1.4.7
- **Fehlerprotokoll:** jeder Fehler landet in einer Datei zum Mitschicken (mit Versionen und Systemangaben) –
  Linux `~/.local/state/pdftoolkit/logs`, Windows `%LOCALAPPDATA%\pdfToolkit\logs`; Hilfe → Fehlerprotokolle öffnen
  - unerwarteter Fehler: Meldung mit Pfad zum Protokoll, pdfToolkit läuft weiter
  - harter Absturz (z. B. in einer Bibliothek): beim nächsten Start einmalige Meldung mit dem Protokoll
  - Fehler in Threads werden ebenfalls erfasst
  - ohne Fehler wird das Protokoll beim Beenden gelöscht; höchstens 10 werden aufgehoben

## 1.4.6
- Behoben: Programm startete unter Python 3.10/3.11 nicht (z. B. Ubuntu 22.04) – Syntax in convert.py, die erst ab
  Python 3.12 erlaubt ist; das AppImage-Build prüft das jetzt als ersten Schritt
- AppImage: installiertes Ghostscript hat Vorrang, das mitgelieferte dient als Reserve; startet es beim Bauen
  nicht, wird es mit Warnung entfernt (Build bricht nicht ab)
- **Fertige Programme über GitHub:** Windows-Setup.exe und Linux-AppImage werden bei jedem Push gebaut, bei
  Tags `v*` als Release veröffentlicht; Abhängigkeiten (Python, Qt, alle Pakete, Ghostscript) sind enthalten
- Selbsttest der fertigen Programmdatei im Build (`--selftest`); `--version`
- Ghostscript wird neben der eigenen Programmdatei gefunden (Installer/AppImage bringen es mit)
- AppImage: Admin-Standards speichern über pkexec mit demselben abgesicherten Helfer
- Behoben: Admin-Fenster auf kleinen Bildschirmen nicht scrollbar (Reiter scrollen, Fenster passt sich an)
- Behoben: Touchpad-Scrollen (Seitenwechsel/Zoom) unter Windows
- `uninstall.sh` (Programm entfernen, Abhängigkeiten bleiben; `--dry-run`, `--purge`), `.gitignore`
- Installer-Skript als UTF-8 mit BOM (Umlaute im Setup korrekt); `build.ps1` reines ASCII; install.sh mit apt-get update
- Versionen 1.4.4/1.4.5 entfallen (zusammengefasst in 1.4.6)

## 1.4.3 (nur Windows betroffen, Linux unverändert)
- **Windows-Druck neu:** PostScript-Treiber (Canon PS3, Fiery …) bekommen PostScript direkt von pdfium (vektoriell,
  kompakt); alle anderen Treiber erhalten die Seite selbst gerastert in Streifen (konstanter Speicher, mit JPEG,
  wenn der Treiber es kann – bis über 90 % weniger Daten in der Warteschlange)
- Behoben: sehr langes Spoolen und Abbrüche (besonders bei Mehrfachnutzen/Step & Repeat) – der frühere GDI-Weg
  schickte Transparenzen, Beschneidungen und jede Nutzen-Platzierung unkomprimiert in voller Druckerauflösung
- Fehler mitten im Druck brechen den Auftrag jetzt sauber ab
- Datei → Einstellungen → „Drucken unter Windows“: Verfahren (Automatisch/PostScript/Raster/Vektor) und Raster-Auflösung
- Neuer Test (tests/test_win_print.py) mit nachgebauten Windows-Schnittstellen

## 1.4.2
- Behoben: Programm startete nicht (Namenskonflikt in der Seitenansicht durch die neue Textauswahl)
- Behoben: Strg+C (Text kopieren) hätte einen Fehler ausgelöst (fehlender Import)
- Neuer Start-Test (tests/test_gui_smoke.py): Programmstart, Fenster, Textauswahl – ohne Bildschirm

## 1.4.1
- **Text markieren** in der Seitenansicht (ziehen, Doppelklick = Wort, Strg+C kopiert, Seiten → Text der Seite markieren)
- Übersetzungen: fehlende Texte ergänzt (Druckdialog-Knöpfe Größe/Mehrere/Broschüre/Poster, Admin, Zusammenführen,
  Dateifilter, Meldungen), „&“ in Übersetzungen ausgeschrieben, deutsche Treiberbegriffe werden übersetzt

## 1.4.0
- **Mehrsprachig:** Deutsch, Englisch, Ungarisch, Spanisch, Französisch – *Datei → Einstellungen*,
  Admin-Standardsprache, Neustart auf Knopfdruck; Qt-Standardtexte in der jeweiligen Sprache
- Treiberbegriffe (Fächer, Finisher, Medien, Epson-Papiersorten) je Sprache; bei Englisch Originaltexte des Treibers
- Nautilus-Menü, Desktop-Eintrag, Explorer-Kontextmenü und Windows-Installer mehrsprachig
- Test `test_l10n.py` prüft Vollständigkeit und Platzhalter aller Kataloge

## 1.3.0
- **Als PDF speichern** als Ziel im Druckdialog: ausgeschossenes Ergebnis als PDF, vektoriell, Farben und
  Farbräume unverändert (geprüft: CMYK-/RGB-Werte bitgenau gleich), ohne Farbprofil und Druckerränder
- **Behoben:** ausgefüllte Formularfelder, Kommentare und Stempel fehlten beim Druck – sie werden jetzt wie
  in Acrobat eingebrannt (gilt für alle Drucker und die Vorschau)

## 1.2.3
- Behoben: Absturz bei Step & Repeat, wenn beim Eintippen eines Kantenmaßes kurz winzige Werte entstanden
  (z. B. 1 mm -> über 40.000 Nutzen). Zahlenfelder übernehmen Werte jetzt erst bei Enter/Feldwechsel;
  Schutzgrenzen (max. 400 Nutzen pro Blatt, 2000 Posterblätter) mit verständlicher Meldung

## 1.2.2
- Step & Repeat (Mehrfachnutzen): Nutzengröße wahlweise in % oder „kurze/lange Kante auf … mm“;
  Größe je Nutzen und Anzahl pro Blatt werden live angezeigt

## 1.2.1
- Benutzerdefinierte Skalierung: zusätzlich „Kurze Kante auf … mm“ bzw. „Lange Kante auf … mm“
  (proportional); resultierende Seitengröße in mm wird live angezeigt

## 1.2.0
- **Automatische Fachwahl**: Format (und Grammatur) wählen -> erste Lade mit genau diesem Papier;
  Reihenfolge = Vorrang; leere Laden werden per IPP-Live-Abfrage übersprungen
- Admin: **Fächerbelegung** je Drucker, „Vom Gerät lesen“ befüllt sie per IPP (Format, Grammatur, Lade)
- Druckdialog: Grammatur-Auswahl, Anzeige der gewählten Lade, Prüfung vor dem Senden; gilt auch für den
  Rechtsklick-Druck
- Eigener IPP-Client (ohne CUPS, auch unter Windows)

## 1.1.0
- **Windows-Version**: Druck über die Windows-Druck-API mit Original-Treiberdialog des Herstellers
  (alle Finisher-Funktionen), Admin-Standards per UAC in %ProgramData%, Explorer-Kontextmenü,
  Installer (Inno Setup) und automatischer Build (GitHub Actions)
- **Endverarbeitung**: eigener Bereich im Druckdialog, automatisch erkannte und übersetzte Finisher-Optionen
  (Sattelheftung, Heften, Lochen, Falzen, Beschnitt, Stapler), **Finisher-Vorlagen** je Drucker
- Canon imagePRESS V1350 und V700/V800/V900: Einrichtungsanleitung und Ausstattungsübersicht
- Office-Umwandlung unter Windows zusätzlich über Microsoft Office
- Mehrfachauswahl im Dateimanager wird gesammelt (ein Zusammenführen-Dialog für alle Dateien)
- Gemeinsame Prüfregeln für Admin-Änderungen (Linux und Windows)

## 1.0.1
- Office-Umwandlung: LibreOffice als Snap/Flatpak funktioniert jetzt (eigenes /tmp der Sandbox umgangen)
- OnlyOffice/Euro-Office: Schriftenverzeichnis für den Konverter wird gefunden bzw. einmalig erzeugt
- Kürzere Fehlermeldungen mit „Details“, Qt-Standardknöpfe auf Deutsch

## 1.0.0 (Oktober 2026)
Erste stabile Version.

- Acrobat-ähnlicher Betrachter: Einzelseite mit Springen oder fortlaufend, Seiten gleich groß, Seitenmaß unten rechts,
  Strg+Mausrad-Zoom, Miniaturen mit Mehrfachauswahl
- Eigener Druckdialog mit allen Treiberoptionen (PPD/IPP), alle Fächer immer wählbar, Admin-Standards per Polkit,
  Sitzungseinstellungen bis Programmende, Live-Vorschau mit Softproof
- Skalierung: tatsächliche Größe, Anpassen, Verkleinern, benutzerdefiniert; N-Up 2/4/6/8/9/16/frei mit Kachel-Skalierung
- Broschüre, Poster/Überformat, Step & Repeat (Kante an Kante / Überfüller an Überfüller / Abstand),
  Spiegeln, Schnittmarken, gespiegelter Anschnitt
- Seiten einfügen, exportieren, drehen, verschieben, löschen; Zusammenführen beliebiger Dateien
  (PDF, Bilder inkl. HEIC, Office über LibreOffice/OnlyOffice/Euro-Office)
- Reparieren, für Weitergabe optimieren, PDF/A-2b, Passwortschutz setzen/entfernen
- Farbprofile: Admin-Verwaltung, Import aus Datei/ZIP/Treiberpaket/Link, Ghostscript-Konvertierung
- Nautilus-Kontextmenü, Einzelinstanz, dunkles Design mit gelbem Akzent
- Lizenz: GPL-3.0-or-later
