# Passermark 1.14.0

PDF-Betrachter, Druckwerkzeug und Druckvorstufen-Werkzeugkasten für **Linux und Windows**. Freie Software
(GPL-3.0-or-later).

**English:** [README.md](README.md) · **Deutsch** · [Magyar](README.hu.md) · [Français](README.fr.md) · [Español](README.es.md)

> **Status:** ein privates Projekt, entwickelt neben der täglichen Arbeit in der Druckvorstufe. Rückmeldungen
> sind willkommen – Antworten und neue Funktionen ohne Garantie. Getestet mit CUPS- und Windows-Treibern
> (Tintenstrahl, Büro- und Produktionsdrucker mit Finisher über einen Druckserver); seltenere Treiber und
> Finisher-Optionen brauchen eventuell Anpassungen.

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
  Passer- und Flattermarken und Bogenübersicht. Auch auf der Kommandozeile (`passermark-cli impose`). Nutzen lassen sich ein zweites Mal auf ein frei wählbares Zielformat montieren (Schritt 2).
- **Dokument-Manipulation:** CMYK-Umwandlung mit Farbvorschau, auf Format beschneiden, Objekte trennen,
  **CutContour** für Schneideplotter (Kontur, Formen, Überfüller, Innenschnitte; Formen mit Griffen skalieren
  und verschieben). Beschneiden zusätzlich mit „Kanten abschneiden“ (mm je Seite, ohne Zielformat) und
  „Weißraum entfernen“ (Inhalt erkennen, neuer Seitenrahmen ± Rand, Inhalt bleibt 1:1).
- **Seiten teilen:** Hälften oder Raster als Einzelseiten – z. B. eine als Doppelseiten exportierte Broschüre;
  Seiten markieren, Rechtsklick → Teilen. Verlustfrei (nichts wird gerastert), Endformat und Anschnitt werden
  berücksichtigt.
- **Preflight:** prüft beim Öffnen Schriften, Ebenen und Transparenzen; Reparaturen: Schriften einbetten oder
  ersetzen (freie, metrisch kompatible Schriften oder Download von fontsource.org), Text in Pfade, Ebenen
  festschreiben/entfernen, Transparenzen reduzieren.
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
- **Arbeitsbereiche** (Anzeigen & Drucken, Druckaufbereitung, Bearbeiten, Variable Daten, Automatisierung) mit
  eigener Werkzeugleiste.
- **Presets** für CutContour, CMYK/Beschneiden, Druck-Layout und Variable Daten – gemeinsam mit der
  Kommandozeile.
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

Optional: LibreOffice (Office-Dateien), 7-Zip (ICC-Profile aus Archiven importieren).

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
`split`; dazu `beispiele`, `datenarten`, `datenvorlage`, `datencheck` (Datentabellen). Verschachtelte
Einstellungen mit Punkt (`--set detect.tolerance=40`). Strg+C bricht sauber ab (keine halbe Datei).
Rückgabewerte: 0 fertig, 1 Fehler, 2 falsche Angabe, 130 abgebrochen. `--json-progress` gibt Fortschritt und
Ergebnis als JSON-Zeilen aus. Große Aufträge nutzen mehrere Rechenkerne; begrenzen mit der Umgebungsvariable
`PASSERMARK_WORKERS` (1 = nicht parallel).

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
