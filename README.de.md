# Passermark 1.18.8

PDF-Betrachter, Druckwerkzeug und Druckvorstufen-Werkzeugkasten für **Linux und Windows**. Freie Software
(GPL-3.0-or-later).

**English:** [README.md](README.md) · **Deutsch** · [Magyar](README.hu.md) · [Français](README.fr.md) · [Español](README.es.md)

> **Status:** ein privates Projekt, entwickelt neben der täglichen Arbeit in der Druckvorstufe. Rückmeldungen
> sind willkommen – Antworten und neue Funktionen ohne Garantie. Getestet mit CUPS- und Windows-Treibern
> (Tintenstrahl, Büro- und Produktionsdrucker mit Finisher über einen Druckserver); seltenere Treiber und
> Finisher-Optionen brauchen eventuell Anpassungen.
>
> **Testumgebung:** zum Testen läuft ein virtueller Maschinenpark – neun simulierte Drucker (Canon, Xerox, Epson,
> Roland, GBC), inklusive Finisher-Funktionen und mit PDF- und Log-Ausgabe je Druck:
> [Virtual-Printer-Machine-Fleet](https://github.com/groschenheld/Virtual-Printer-Machine-Fleet).
> Er wurde von Claude gebaut und hat für meine Testzwecke bislang ausgereicht – Verbesserungsvorschläge sind willkommen.

## Bilder

| | |
|---|---|
| ![Dokumentprüfung mit Warnungen und Hinweisen](docs/screenshots/preflight_example.jpg) | ![CMYK-Umwandlung mit Farbvorschau](docs/screenshots/cmyk_adjustment_example.png) |
| ![Nutzen (Step & Repeat)](docs/screenshots/step_and_repeat_example.png) | ![CutContour für Schneideplotter](docs/screenshots/cut_contour_example.png) |
| ![Beschneiden](docs/screenshots/trim_example.png) | ![Variable Daten](docs/screenshots/variable_data_example.png) |

## Funktionen

- **Anzeigen und Drucken** von PDFs, Bildern (auch HEIC, SVG) und Office-Dateien (über LibreOffice). Verwendet
  die vorhandenen Druckertreiber (CUPS unter Linux, Windows-Treiber) mit allen ihren Optionen.
- **Ausschießen:** einpassen/skalieren, mehrere Seiten pro Blatt, Poster, Nutzen; Broschüren als
  Sammelheftung, gruppierte Lagen oder gestapelte Einzelbögen (Klebebindung), mit Bundzug, Leerseiten, Falz-,
  Passer- und Flattermarken und Bogenübersicht. Auch auf der Kommandozeile (`passermark-cli impose`). Nutzen lassen sich ein zweites Mal auf ein frei wählbares Zielformat montieren (Schritt 2) – jetzt auch beim direkten Drucken aus dem Druckdialog.
- **Plan & Poster:** Plandruck und Posterdruck auf Rollengeräten – Rollen vom Gerät lesen (IPP, sonst SNMP), „Gerät prüfen“ nur lesend mit JSON-Bericht; Rollenwahl automatisch (schmälste passende, nach Grammatur/Material) oder fest, Lage mittig oder am Rand; Laufmeter live mit Warnung vor leerer Rolle; Plan-Werkzeuge (Skalierung, Drehung, Überfüller, Schnittmarken, Haarlinien anheben, Faltmarken nach DIN 824), Poster-Werkzeuge (Saum, Ösenmarken, CutContour, Passermarken für Print & Cut mit der Roland), Breiteres als die Rolle wird in Bahnen geteilt; Materialien je Benutzer – die Medien der geladenen Rollen stehen automatisch in der Liste (mit „(Gerät)“) und wählen genau die Rolle; über IPP wird auch der Medienkatalog gelesen, angelegte, aber nicht geladene Medien stehen als „(Gerät, nicht geladen)“ in der Liste und gehen mit ihrem Medientyp an den Treiber Einstellungen je Plan: Sind einzelne Pläne oder Poster ausgewählt, gelten Material, Rolle, Lage auf der Rolle, Drehung, Druckbereich, Rand, Skalierung (in Prozent oder „Kurze/Lange Kante auf … mm“) und Überfüller nur für die Auswahl – Abweichungen zeigt die Liste mit ✎ an. Beim Versand ist „Ein Auftrag, je Exemplar ein Blatt“ Standard wahlweise je Exemplar ein eigener Auftrag oder eine Kopienzahl; unter der Liste wird jedes Druckblatt klein vorgerendert, mit Größe, Rolle und Schnittanzahl. Auch auf der Kommandozeile (`passermark-cli plan`/`poster`, `--dry-run` rechnet nur Laufmeter, `--copies-mode sheets|jobs|count`, `overrides` je Seitennummer), als Schritt im Ablauf und als Hotfolder-Ausgabe z. B. für VersaWorks; das Druckprotokoll speichert die Abweichungen, beim Nachdrucken stimmen sie.
- **Dokument-Manipulation:** CMYK-Umwandlung mit Farbvorschau, auf Format beschneiden, Objekte trennen,
  **CutContour** für Schneideplotter (Kontur, Formen, Überfüller, Innenschnitte; Formen mit Griffen skalieren
  und verschieben). Beschneiden zusätzlich mit „Kanten abschneiden“ (mm je Seite, ohne Zielformat) und
  „Weißraum entfernen“ (Inhalt erkennen, neuer Seitenrahmen ± Rand, Inhalt bleibt 1:1).
- **Seiten teilen:** Hälften oder Raster als Einzelseiten – z. B. eine als Doppelseiten exportierte Broschüre;
  Seiten markieren, Rechtsklick → Teilen. Verlustfrei (nichts wird gerastert), Endformat und Anschnitt werden
  berücksichtigt.
- **Preflight:** prüft beim Öffnen Schriften, Ebenen, Transparenzen, Seitenrahmen (Crop-/Trim-/Bleed-Box), Beschnitt am Inhalt, Schutz, PDF/X und Output Intent, Formularfelder und leere Seiten; Reparaturen: Schriften einbetten oder
  ersetzen (freie, metrisch kompatible Schriften oder Download von fontsource.org), Text in Pfade, Ebenen
  festschreiben/entfernen, Transparenzen reduzieren. Jeder Fund nennt seine Stelle (z. B. „Seite 2 – unten rechts, 40 × 20 mm“); ein Klick springt hin und rahmt sie rot ein, mit ◀ ▶ gehst du durch die Stellen.
- **Bearbeiten:** Textzeilen und Ebenen mit der Maus wählen; Text, Schrift und Größe ändern; Ebenen
  verschieben, skalieren, ausblenden, entfernen oder ersetzen; Rückgängig.
- Lineale und Messen: Lineale in mm am Rand der Ansicht; Start und Ende anklicken zum Messen (Umschalt rastet
  waagrecht/senkrecht/45° ein), Ergebnis in der Statusleiste. Mit gedrückter Strg rastet das Fadenkreuz magnetisch an Schnitt- und Innenlinien (Seitenrand,
  Endformat, Anschnitt), Bildkanten und Vektorlinien ein – nie an Text; es bleibt an der Kante kleben,
  bis die Maus deutlich weiterzieht. Das Endformat-Overlay zeigt das Endformat grün und den Anschnitt als Punktlinie.
- **Variable Daten:** Nummerierung (Start, Schrittweite, Stellen, Prüfziffern, rückwärts, Weiterzählen), Text
  aus CSV, QR-Codes, Code 128 und EAN-13 als Vektor (mit Ruhezone); Platzhalter `{{…}}` im PDF; Datum, Seite,
  Zufallszahl und weitere Variablen; mehrere Seiten je Datensatz (Vorder-/Rückseite) und Felder auf
  ungeraden/geraden Seiten; Code-Protokoll; Nutzen mit eigenem Datensatz je Nutzen (Bogen für Bogen oder
  Schneiden und Stapeln); **Fenster (Seitengruppen)** für Vorlagen mit mehreren Seiten – z. B. Vorderseiten mit dem Namen, Rückseiten mit QR-Code – mit Seitenauswahl je Fenster (alle/ungerade/gerade Seiten oder Bereiche) und Datensatz-Verteilung Bogen für Bogen oder Seite für Seite. Auch auf der Kommandozeile (`passermark-cli vdp`).
- **Daten erfassen:** die Datentabelle direkt in Passermark anlegen – QR-Visitenkarte (vCard), WLAN-Zugang,
  E-Mail, Webadresse, Anruf, SMS, Termin, Standort, Code 128, EAN-13 – mit passenden Spalten, sofortiger
  Prüfung und Einfügen aus Excel; gespeichert als CSV und direkt in Variable Daten verwendbar. Eigene CSV-Dateien
  mit anderen Spaltennamen (z. B. Kontakt-Exporte aus Outlook, Google, Thunderbird) werden automatisch
  zugeordnet. Sieben fertige Beispiele (Hilfe → Beispiele holen).
- **Arbeitsbereiche** (Anzeigen & Drucken, Plan & Poster, Druckaufbereitung, Bearbeiten, Variable Daten, Automatisierung) mit
  eigener Werkzeugleiste.
- **Presets** für CutContour, CMYK/Beschneiden, Druck-Layout und Variable Daten – gemeinsam mit der
  Kommandozeile.
- **Druckprotokoll:** pro Benutzer in den Einstellungen oder vom Admin erzwungen – eine JSON je Auftrag mit den exakten Einstellungen und den gesendeten Seiten je Exemplar (`out_pages`), dazu eine `printlog.csv`; mit `passermark-cli reprint <log.json>` druckst du einen Auftrag jederzeit neu (mit Warnung, wenn sich das Original geändert hat).
- **Automatisierung:** Schritt-für-Schritt-Abläufe mit Bedingungen („if“ an jedem Schritt, „choose“/„else“-Verzweigungen, „fail“/„stop“ mit Meldung); `passermark-cli serve` überwacht Ordner und schickt jede Datei durch den zugeordneten Ablauf – `serve --init` legt eine Vorlage mit Beispiel an.
- **Gemeinsamer Druckordner:** ein Hotfolder für alle – eingerichtet über einen Knopf in der Verwaltung („Gemeinsamen Druckordner einrichten …“), über install.sh oder `passermark-cli shared-folder`; ein einziger Root-Helfer legt Gruppe und Ordner an (root:passermark, 2775, Standard-ACL, die Benutzer kommen in die Gruppe, symbolische Links werden abgelehnt); unter Windows bekommen `hotfolder`, `ausgabe` und `archiv` Ändern-Recht für die Benutzer – der Rest von ProgramData bleibt den Administratoren vorbehalten.
- **Softproof:** das Druckergebnis in der Seitenansicht simulieren (Strg+Y) – als Druckbedingung ein Material, ein Profil aus der Verwaltung oder ein System-CMYK-Profil, mit Intent und BPC; Papierfarbe und schwarze Druckfarbe simulieren, Warnungen für Farben außerhalb des Farbumfangs und für Farbauftrag über einer Grenze in %.
- **Materialien:** Papiere registrieren (Grammatur, Oberfläche, Render-Intent, Profil je Drucker); Papierweiß mit ArgyllCMS (spotread) messen, aus einer CGATS-Messdatei oder per Hand; Profilvorschläge nach ΔE2000. Materialien setzen Profil und Intent im Druckdialog und in der CMYK-Umwandlung, die Farbvorschau nimmt das gemessene Papierweiß.
- **Farbprüfung:** im neuen Menü Farbe (Strg+Umschalt+F) – eine Seitenleiste wie der Preflight: Druckbedingung wählen, Passermark zeigt, was im Dokument steckt (RGB, Farbauftrag, Sonderfarben, Output Intent), und Befunde in Klartext, jeder mit Knopf zum Beheben; Fundstellen anklickbar.
- **Für Druckerei ausgeben:** Assistent in vier Schritten – Druckbedingung wählen, nach Empfehlung umwandeln, prüfen, speichern; ICC immer als Output Intent, bei RGB immer Rückfrage; optional Paket aus PDF, Profilen und Bericht. Auch auf der Kommandozeile (`passermark-cli press`).
- **Papiere und Messungen:** eigene Materialien ohne Adminrechte (`~/.config/passermark/materials.json`, sofort gespeichert); „Papier messen …“ legt das Papier an und startet die Messung, „Gerät suchen“ findet das X-Rite-Gerät über ArgyllCMS; die leere Materialliste im Admin-Dialog erklärt jetzt die ersten Schritte.
- **Standardprofile:** PSO Coated/Uncoated v3, FOGRA39/47, SC-B, GRACoL und SWOP mit „Standardprofile holen“ von registry.color.org in den eigenen ICC-Ordner laden (mitgeliefert werden sie aus Lizenzgründen nicht); Vorschläge zeigen auch noch nicht installierte.
- PDFs reparieren/optimieren, PDF/A, Passwortschutz (auch beim „Als PDF speichern“ im Druckdialog), Dateien
  zusammenführen, Text markieren und kopieren.
- Sprachen: Deutsch, Englisch, Ungarisch, Spanisch, Französisch.

## Installation

**Windows:** `Passermark-<version>-Setup.exe` unter [Releases](../../releases) herunterladen und ausführen. Alles
ist enthalten (Python, Qt, Ghostscript).

**Linux (jede Distribution):** `Passermark-<version>-x86_64.AppImage` unter [Releases](../../releases)
herunterladen, dann
```sh
chmod +x Passermark-*-x86_64.AppImage
./Passermark-*-x86_64.AppImage
```

**Linux (Debian/Ubuntu, Systeminstallation mit Dateimanager-Einbindung):**
```sh
sudo ./install.sh        # installiert Abhängigkeiten über apt, Startmenü-Eintrag, Nautilus-Menü
sudo ./uninstall.sh      # wieder entfernen (--dry-run zeigt vorher an, --purge entfernt auch /etc/passermark)
```

Optional: LibreOffice (Office-Dateien), 7-Zip (ICC-Profile aus Archiven importieren), ArgyllCMS (Papierweiß der Materialien messen – Linux-Paket `argyll`).

## Kommandozeile

Alle schweren Funktionen laufen auch ohne Oberfläche – für Skripte, ganze Ordner und Automatisierung:

```sh
passermark-cli list                                   # verfügbare Aufträge
passermark-cli settings cutcontour > sticker.json     # Standardeinstellungen = Preset-Vorlage
passermark-cli cutcontour ein.pdf aus.pdf --set shape=rect --set bleed_mm=2
passermark-cli cutcontour ein.pdf aus.pdf --preset sticker.json --pages 1,3-5
passermark-cli cutcontour ein.pdf aus.pdf --preset "Sticker rund"   # im Programm gespeichertes Preset
passermark-cli presets                                # im Programm gespeicherte Presets
```

Aufträge: `cutcontour`, `separate`, `manip` (CMYK/Beschneiden), `repair`, `preflight_fix`, `impose`, `vdp`,
`split`, `press` (Druckerei-Export), `plan`/`poster` (Plan- und Posterdruck auf Rollen); dazu `beispiele`, `datenarten`, `datenvorlage`, `datencheck` (Datentabellen). Verschachtelte
Einstellungen mit Punkt (`--set detect.tolerance=40`). Strg+C bricht sauber ab (keine halbe Datei).
Rückgabewerte: 0 fertig, 1 Fehler, 2 falsche Angabe, 130 abgebrochen. `--json-progress` gibt Fortschritt und
Ergebnis als JSON-Zeilen aus. Große Aufträge nutzen mehrere Rechenkerne; begrenzen mit der Umgebungsvariable
`PASSERMARK_WORKERS` (1 = nicht parallel).

`passermark-cli serve` überwacht Drop-Ordner (`--init` legt eine Vorlage mit Beispiel an); `passermark-cli shared-folder` richtet den gemeinsamen Druckordner ein (`--user NAME`, `--status`); `passermark-cli reprint <log.json>` druckt aus dem Druckprotokoll neu nach.

Wo: Linux `install.sh` → `passermark-cli`; AppImage → `Passermark-*.AppImage --cli …`;
Windows → `passermark-cli.exe` im Installationsordner (Setup-Option: in den Suchpfad aufnehmen).
Anleitungen mit Fallbeispielen (PDF) gibt es im Programm unter **Hilfe → Kommandozeile – Anleitung** und
**Hilfe → Variable Daten – Anleitung**.
Schnittstelle für Zusatzprogramme (feste JSON-Ereignisse, Fehlercodes): [docs/cli-api.md](docs/cli-api.md).

## Fehlerprotokolle

Geht etwas schief, schreibt Passermark eine Protokolldatei zum Mitschicken (Hilfe → Fehlerprotokolle öffnen):
Linux `~/.local/state/passermark/logs`, Windows `%LOCALAPPDATA%\Passermark\logs`. Nach einem Absturz weist der
nächste Start auf das Protokoll hin. Protokolle ohne Fehler werden beim Beenden gelöscht.

## Bauen

Lokal: `powershell -ExecutionPolicy Bypass -File windows\build.ps1` (Windows, braucht Python 3.12 und
Inno Setup 6) oder `./linux/build-appimage.sh` (Linux, benötigte Pakete im Kopf des Skripts).

Tests: `python3 tests/test_<name>.py` (kein Test-Framework nötig).

## Lizenz

GPL-3.0-or-later, siehe `LICENSE`. Windows-Installer und AppImage enthalten
[Ghostscript](https://ghostscript.com) (AGPL-3.0, Artifex Software).

Lizenzen von Drittanbietern: Installer und AppImage enthalten neben dem Programm einen Ordner
`licenses` (Hilfe → Lizenzen …) mit `THIRD_PARTY_NOTICES.txt`, den Lizenzdateien aller mitgelieferten
Python-Pakete, dem LGPL-Hinweis zu Qt/PySide6 (Austausch der Qt-Bibliotheken) und dem
Ghostscript-Hinweis mit den Quellcode-Links der mitgelieferten Version. Auf Anfrage wird der
zugehörige Quellcode der mitgelieferten Komponenten auch direkt bereitgestellt – bitte ein Issue auf
[GitHub](https://github.com/groschenheld/passermark/issues) anlegen.


