# Passermark 1.15.1

PDF-Betrachter, Druckwerkzeug und Druckvorstufen-Werkzeugkasten fÃ¼r **Linux und Windows**. Freie Software
(GPL-3.0-or-later).

**English:** [README.md](README.md) Â· **Deutsch** Â· [Magyar](README.hu.md) Â· [FranÃ§ais](README.fr.md) Â· [EspaÃ±ol](README.es.md)

> **Status:** ein privates Projekt, entwickelt neben der tÃ¤glichen Arbeit in der Druckvorstufe. RÃ¼ckmeldungen
> sind willkommen â Antworten und neue Funktionen ohne Garantie. Getestet mit CUPS- und Windows-Treibern
> (Tintenstrahl, BÃ¼ro- und Produktionsdrucker mit Finisher Ã¼ber einen Druckserver); seltenere Treiber und
> Finisher-Optionen brauchen eventuell Anpassungen.

## Bilder

| | |
|---|---|
| ![DokumentprÃ¼fung mit Warnungen und Hinweisen](docs/screenshots/preflight_example.jpg) | ![CMYK-Umwandlung mit Farbvorschau](docs/screenshots/cmyk_adjustment_example.png) |
| ![Nutzen (Step & Repeat)](docs/screenshots/step_and_repeat_example.png) | ![CutContour fÃ¼r Schneideplotter](docs/screenshots/cut_contour_example.png) |
| ![Beschneiden](docs/screenshots/trim_example.png) | ![Variable Daten](docs/screenshots/variable_data_example.png) |

## Funktionen

- **Anzeigen und Drucken** von PDFs, Bildern (auch HEIC, SVG) und Office-Dateien (Ã¼ber LibreOffice). Verwendet
  die vorhandenen Druckertreiber (CUPS unter Linux, Windows-Treiber) mit allen ihren Optionen.
- **AusschieÃen:** einpassen/skalieren, mehrere Seiten pro Blatt, Poster, Nutzen; BroschÃ¼ren als
  Sammelheftung, gruppierte Lagen oder gestapelte EinzelbÃ¶gen (Klebebindung), mit Bundzug, Leerseiten, Falz-,
  Passer- und Flattermarken und BogenÃ¼bersicht. Auch auf der Kommandozeile (`passermark-cli impose`). Nutzen lassen sich ein zweites Mal auf ein frei wÃ¤hlbares Zielformat montieren (Schritt 2).
- **Dokument-Manipulation:** CMYK-Umwandlung mit Farbvorschau, auf Format beschneiden, Objekte trennen,
  **CutContour** fÃ¼r Schneideplotter (Kontur, Formen, ÃberfÃ¼ller, Innenschnitte; Formen mit Griffen skalieren
  und verschieben). Beschneiden zusÃ¤tzlich mit âKanten abschneidenâ (mm je Seite, ohne Zielformat) und
  âWeiÃraum entfernenâ (Inhalt erkennen, neuer Seitenrahmen Â± Rand, Inhalt bleibt 1:1).
- **Seiten teilen:** HÃ¤lften oder Raster als Einzelseiten â z. B. eine als Doppelseiten exportierte BroschÃ¼re;
  Seiten markieren, Rechtsklick â Teilen. Verlustfrei (nichts wird gerastert), Endformat und Anschnitt werden
  berÃ¼cksichtigt.
- **Preflight:** prÃ¼ft beim Ãffnen Schriften, Ebenen und Transparenzen; Reparaturen: Schriften einbetten oder
  ersetzen (freie, metrisch kompatible Schriften oder Download von fontsource.org), Text in Pfade, Ebenen
  festschreiben/entfernen, Transparenzen reduzieren.
- **Bearbeiten:** Textzeilen und Ebenen mit der Maus wÃ¤hlen; Text, Schrift und GrÃ¶Ãe Ã¤ndern; Ebenen
  verschieben, skalieren, ausblenden, entfernen oder ersetzen; RÃ¼ckgÃ¤ngig.
- Lineale und Messen: Lineale in mm am Rand der Ansicht; Start und Ende anklicken zum Messen (Umschalt rastet
  waagrecht/senkrecht/45Â° ein), Ergebnis in der Statusleiste. Mit gedrÃ¼ckter Strg rastet das Fadenkreuz magnetisch an Schnitt- und Innenlinien (Seitenrand,
  Endformat, Anschnitt), Bildkanten und Vektorlinien ein â nie an Text; es bleibt an der Kante kleben,
  bis die Maus deutlich weiterzieht. Das Endformat-Overlay zeigt das Endformat grÃ¼n und den Anschnitt als Punktlinie.
- **Variable Daten:** Nummerierung (Start, Schrittweite, Stellen, PrÃ¼fziffern, rÃ¼ckwÃ¤rts, WeiterzÃ¤hlen), Text
  aus CSV, QR-Codes, Code 128 und EAN-13 als Vektor (mit Ruhezone); Platzhalter `{{â¦}}` im PDF; Datum, Seite,
  Zufallszahl und weitere Variablen; mehrere Seiten je Datensatz (Vorder-/RÃ¼ckseite) und Felder auf
  ungeraden/geraden Seiten; Code-Protokoll; Nutzen mit eigenem Datensatz je Nutzen (Bogen fÃ¼r Bogen oder
  Schneiden und Stapeln); **Fenster (Seitengruppen)** fÃ¼r Vorlagen mit mehreren Seiten â z. B. Vorderseiten mit dem Namen, RÃ¼ckseiten mit QR-Code â mit Seitenauswahl je Fenster (alle/ungerade/gerade Seiten oder Bereiche) und Datensatz-Verteilung Bogen fÃ¼r Bogen oder Seite fÃ¼r Seite. Auch auf der Kommandozeile (`passermark-cli vdp`).
- **Daten erfassen:** die Datentabelle direkt in Passermark anlegen â QR-Visitenkarte (vCard), WLAN-Zugang,
  E-Mail, Webadresse, Anruf, SMS, Termin, Standort, Code 128, EAN-13 â mit passenden Spalten, sofortiger
  PrÃ¼fung und EinfÃ¼gen aus Excel; gespeichert als CSV und direkt in Variable Daten verwendbar. Eigene CSV-Dateien
  mit anderen Spaltennamen (z. B. Kontakt-Exporte aus Outlook, Google, Thunderbird) werden automatisch
  zugeordnet. Sieben fertige Beispiele (Hilfe â Beispiele holen).
- **Arbeitsbereiche** (Anzeigen & Drucken, Druckaufbereitung, Bearbeiten, Variable Daten, Automatisierung) mit
  eigener Werkzeugleiste.
- **Presets** fÃ¼r CutContour, CMYK/Beschneiden, Druck-Layout und Variable Daten â gemeinsam mit der
  Kommandozeile.
- PDFs reparieren/optimieren, PDF/A, Passwortschutz (auch beim âAls PDF speichernâ im Druckdialog), Dateien
  zusammenfÃ¼hren, Text markieren und kopieren.
- Sprachen: Deutsch, Englisch, Ungarisch, Spanisch, FranzÃ¶sisch.

## Installation

**Windows:** `Passermark-<version>-Setup.exe` unter [Releases](../../releases) herunterladen und ausfÃ¼hren. Alles
ist enthalten (Python, Qt, Ghostscript).

**Linux (jede Distribution):** `Passermark-<version>-x86_64.AppImage` unter [Releases](../../releases)
herunterladen, dann
```sh
chmod +x Passermark-*-x86_64.AppImage
./Passermark-*-x86_64.AppImage
```

**Linux (Debian/Ubuntu, Systeminstallation mit Dateimanager-Einbindung):**
```sh
sudo ./install.sh        # installiert AbhÃ¤ngigkeiten Ã¼ber apt, StartmenÃ¼-Eintrag, Nautilus-MenÃ¼
sudo ./uninstall.sh      # wieder entfernen (--dry-run zeigt vorher an, --purge entfernt auch /etc/passermark)
```

Optional: LibreOffice (Office-Dateien), 7-Zip (ICC-Profile aus Archiven importieren).

## Kommandozeile

Alle schweren Funktionen laufen auch ohne OberflÃ¤che â fÃ¼r Skripte, ganze Ordner und Automatisierung:

```sh
passermark-cli list                                   # verfÃ¼gbare AuftrÃ¤ge
passermark-cli settings cutcontour > sticker.json     # Standardeinstellungen = Preset-Vorlage
passermark-cli cutcontour ein.pdf aus.pdf --set shape=rect --set bleed_mm=2
passermark-cli cutcontour ein.pdf aus.pdf --preset sticker.json --pages 1,3-5
passermark-cli cutcontour ein.pdf aus.pdf --preset "Sticker rund"   # im Programm gespeichertes Preset
passermark-cli presets                                # im Programm gespeicherte Presets
```

AuftrÃ¤ge: `cutcontour`, `separate`, `manip` (CMYK/Beschneiden), `repair`, `preflight_fix`, `impose`, `vdp`,
`split`; dazu `beispiele`, `datenarten`, `datenvorlage`, `datencheck` (Datentabellen). Verschachtelte
Einstellungen mit Punkt (`--set detect.tolerance=40`). Strg+C bricht sauber ab (keine halbe Datei).
RÃ¼ckgabewerte: 0 fertig, 1 Fehler, 2 falsche Angabe, 130 abgebrochen. `--json-progress` gibt Fortschritt und
Ergebnis als JSON-Zeilen aus. GroÃe AuftrÃ¤ge nutzen mehrere Rechenkerne; begrenzen mit der Umgebungsvariable
`PASSERMARK_WORKERS` (1 = nicht parallel).

Wo: Linux `install.sh` â `passermark-cli`; AppImage â `Passermark-*.AppImage --cli â¦`;
Windows â `passermark-cli.exe` im Installationsordner (Setup-Option: in den Suchpfad aufnehmen).
Anleitungen mit Fallbeispielen (PDF) gibt es im Programm unter **Hilfe â Kommandozeile â Anleitung** und
**Hilfe â Variable Daten â Anleitung**.
Schnittstelle fÃ¼r Zusatzprogramme (feste JSON-Ereignisse, Fehlercodes): [docs/cli-api.md](docs/cli-api.md).

## Fehlerprotokolle

Geht etwas schief, schreibt Passermark eine Protokolldatei zum Mitschicken (Hilfe â Fehlerprotokolle Ã¶ffnen):
Linux `~/.local/state/passermark/logs`, Windows `%LOCALAPPDATA%\Passermark\logs`. Nach einem Absturz weist der
nÃ¤chste Start auf das Protokoll hin. Protokolle ohne Fehler werden beim Beenden gelÃ¶scht.

## Bauen

Lokal: `powershell -ExecutionPolicy Bypass -File windows\build.ps1` (Windows, braucht Python 3.12 und
Inno Setup 6) oder `./linux/build-appimage.sh` (Linux, benÃ¶tigte Pakete im Kopf des Skripts).

Tests: `python3 tests/test_<name>.py` (kein Test-Framework nÃ¶tig).

## Lizenz

GPL-3.0-or-later, siehe `LICENSE`. Windows-Installer und AppImage enthalten
[Ghostscript](https://ghostscript.com) (AGPL-3.0, Artifex Software).

Lizenzen von Drittanbietern: Installer und AppImage enthalten neben dem Programm einen Ordner
`licenses` (Hilfe â Lizenzen â¦) mit `THIRD_PARTY_NOTICES.txt`, den Lizenzdateien aller mitgelieferten
Python-Pakete, dem LGPL-Hinweis zu Qt/PySide6 (Austausch der Qt-Bibliotheken) und dem
Ghostscript-Hinweis mit den Quellcode-Links der mitgelieferten Version. Auf Anfrage wird der
zugehÃ¶rige Quellcode der mitgelieferten Komponenten auch direkt bereitgestellt â bitte ein Issue auf
[GitHub](https://github.com/groschenheld/passermark/issues) anlegen.

