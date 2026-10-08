# pdfToolkit 1.4.8 – PDF-Betrachter mit vollständigem Druckdialog (Linux/CUPS und Windows)

Acrobat-ähnliches Layout (Miniaturen links, Endlosansicht, Toolbar), Fokus ausschließlich auf
Anzeige und Druck. Stack: Python 3, PySide6, pypdfium2, pycups, Ghostscript, Polkit –
alles Open Source.

## Funktionen

- **Skalierung:** Anpassen · Tatsächliche Größe (1:1) · Übergroße verkleinern · Benutzerdefiniert – in %, oder **kurze bzw. lange Kante auf ein Maß in mm** (die andere Kante ergibt sich); das Ergebnis in mm steht direkt darunter und in der Vorschau
- **Mehrere Seiten pro Blatt:** 2/4/6/8/9/16 oder freies Raster (Spalten × Zeilen), Reihenfolge,
  Abstand, Seitenrand, **Skalierung je Kachel** (anpassen / 1:1 / %), automatische Drehung,
  automatische Wahl von Hoch-/Querformat
- **Broschüre:** Sattelheftung-Ausschießen (Leerseiten auf Vielfaches von 4), Bindung links/rechts,
  Bogenbereich, Bundsteg, beidseitig (Duplex kurze Kante automatisch) oder nur Vorder-/Rückseiten
- **Poster/Überformat:** Kacheln über Maßstab, Anzahl Blätter oder Zielformat (A0–A4, B1–B3, frei),
  Überlappung, Schnitt-/Klebelinien, Beschriftung, „nur große Seiten kacheln“
- **Weitere Optionen:** Spiegeln (horizontal/vertikal), Step & Repeat (Nutzen: automatisch so viele wie
  passen oder Raster; Nutzengröße in % oder kurze/lange Kante auf mm; Abstand), Schnittmarken, Überfüller/Anschnitt durch Spiegeln der Ränder (mm)
- **Reparieren / optimieren:** beschädigte PDFs reparieren (verlustfrei), für Weitergabe neu erzeugen
  (Schriften eingebettet), für Mail verkleinern, PDF/A-2b; Passwortschutz setzen (AES-256) oder entfernen.
  Auch per Nautilus-Rechtsklick und `pdftoolkit --repair`
- **Passwortgeschützte PDFs:** Passwortabfrage beim Öffnen, Einfügen, Zusammenführen und Rechtsklick-Druck
- **Farbprofile laden (Admin):** Bezugsquellen je Drucker, Download per Link, Import aus ICC, ZIP oder
  Treiberpaket (.exe/.cab/.dmg via 7-Zip), Prüfung auf Drucker-Ausgabeprofile, direkte Zuordnung
- **Endverarbeitung / Finisher:** eigener Bereich im Druckdialog (Sattelheftung, Heften, Lochen, Falzen,
  Beschnitt, Stapler – automatisch erkannt und übersetzt) plus **Finisher-Vorlagen**, die der Admin je Drucker
  anlegt (z. B. „Broschüre heften + falzen + beschneiden“); Vorlagen mit Broschüren-Kennzeichen schalten
  automatisch auf Broschüre
- **Windows:** gleiche Oberfläche; alle Herstellerfunktionen über den Original-Treiberdialog (Canon, Fiery …),
  Admin-Standards per UAC, Explorer-Kontextmenü, Office-Umwandlung zusätzlich über Microsoft Office
- **Als PDF speichern:** eigenes Ziel in der Druckerliste – das ausgeschossene Ergebnis (N-Up, Broschüre,
  Poster, Nutzen, Marken, Anschnitt, Spiegeln) als PDF-Datei; vektoriell, **Farben und Farbräume unverändert**
  (CMYK bleibt CMYK, kein Farbprofil), Format „wie Dokument“ oder A0–A6, A3+, SRA3, Letter …
- **Formulare und Kommentare** werden beim Drucken mitgedruckt (eingebrannt, wie in Acrobat)
- **Sprachen:** Deutsch, English, Magyar, Español, Français – umschaltbar unter *Datei → Einstellungen*
  (Admin kann eine Standardsprache vorgeben); auch Treiberbegriffe (Fächer, Finisher, Medien), Nautilus-Menü,
  Explorer-Menü und Windows-Installer sind übersetzt
- **Ansicht:** Strg + Mausrad zoomt um den Mauszeiger; unten rechts Seite und Seitenmaß (mm + Formatname)
- **Seiten (Miniaturen, Mehrfachauswahl, Rechtsklick):** einfügen vor/nach/am Ende (aus PDF oder Bild),
  als ein PDF oder als Einzelseiten exportieren, dauerhaft drehen, verschieben (Alt+↑/↓), löschen
- **Alles zu einem PDF:** mehrere Dateien – PDF, Bilder, Word/Excel/PowerPoint/ODF/RTF/TXT … – in wählbarer
  Reihenfolge zusammenführen (Nautilus-Rechtsklick, Datei-Menü, `pdftoolkit --merge`). Office-Dateien werden mit
  LibreOffice, OnlyOffice oder Euro-Office umgewandelt (Auto-Wahl: Microsoft-Formate über die OnlyOffice-Familie,
  ODF über LibreOffice; automatischer Rückfall). Einzelne Office-Dateien per Rechtsklick „Als PDF öffnen“
- **Zusammenführen:** Datei → Dokumente zusammenführen (Reihenfolge per Drag & Drop), oder Datei mit
  **Strg** auf das Fenster ziehen = anhängen
- **Bilder als PDF:** JPEG, PNG, TIFF (mehrseitig), BMP, GIF, WebP, HEIC/HEIF – in tatsächlicher Größe
  laut DPI-Angabe, sonst Admin-Standard (96 dpi); JPEG/PNG verlustfrei eingebettet, EXIF-Drehung beachtet
- **Nautilus-Rechtsklick:** bei Bildern „Als PDF öffnen“, bei PDFs „Drucken (pdfToolkit)“ ohne Dialog.
  Läuft pdfdruck, gelten die im Druckdialog gesetzten Einstellungen dieser Sitzung, sonst die Admin-Standards
- **Kommandozeile:** `pdftoolkit dateien…` öffnen, `pdftoolkit --print dateien…` ohne Dialog drucken
- **Seiten:** alle, aktuelle, Bereiche (`1-3, 5, 8-`), gerade/ungerade, umgekehrt; Kopien, Sortieren
- **Treiber:** *alle* Optionen der PPD bzw. IPP-Attribute werden generisch angezeigt; alle Fächer sind
  immer wählbar, Konflikte (UIConstraints) werden nur gemeldet, nie gesperrt
- **Vorschau:** echtes Ausschießergebnis inkl. bedruckbarem Bereich, Blattnavigation, Warnungen
- **Farbprofile:** vom Admin deklariert (ICC), Druckern zugeordnet, Intents freigegeben; Umrechnung per
  Ghostscript, optional mit Treiberoptionen (z. B. Treiber-Farbabgleich aus)
- **Rechte:** Standards in `/etc/pdfdruck/defaults.json` (root), Änderung nur über Polkit (`pkexec`)

## Warum es kein „Zurückstellen beim Beenden“ braucht

Das Programm verändert die Drucker-Standards des Systems nur, wenn der Admin das ausdrücklich will
(Haken „Auch als System-/Windows-Standard setzen“). Benutzeränderungen im Druckdialog leben nur im
Arbeitsspeicher; jeder Auftrag bekommt den **vollständigen** Optionssatz mit. Beim nächsten Start gelten
automatisch wieder die Admin-Standards – auch nach einem Absturz.

## Installation

### Linux (Ubuntu/Debian, getestet mit Ubuntu 24.04)

```sh
tar xzf pdftoolkit-<version>.tar.gz && cd pdftoolkit
sudo ./install.sh     # apt-Abhängigkeiten, eigenes venv in /usr/local/lib/pdfdruck, Polkit, Nautilus-Menü
nautilus -q           # Nautilus neu starten, damit das Rechtsklick-Menü erscheint
pdftoolkit datei.pdf
```

Ein Update ist dasselbe: neue Version entpacken, `sudo ./install.sh`. Admin-Standards bleiben erhalten
(`/etc/pdfdruck`).

### Windows 10/11

- **Installer bauen** – auf einem Windows-PC mit Python 3.12 (x64) und Inno Setup 6: `windows\build.ps1`
  → `dist\pdfToolkit-<version>-Setup.exe`.
  Ohne Windows-Rechner: Projekt auf GitHub hochladen, Workflow „Windows-Installer“ starten
  (`.github/workflows/windows.yml`), die Setup-Datei liegt dann unter „Artifacts“.
- **Installieren:** Setup als Administrator ausführen. Admin-Standards liegen danach in
  `%ProgramData%\pdfToolkit` (nur Administratoren dürfen schreiben – setzt der Installer).
- **Optional** (für einzelne Funktionen):
  [Ghostscript](https://ghostscript.com) (Optimieren, PDF/A, Farbprofile beim Druck),
  [7-Zip](https://7-zip.org) (ICC-Profile aus Treiberpaketen),
  LibreOffice, OnlyOffice, Euro-Office oder Microsoft Office (Office-Dateien als PDF).

## Drucker einrichten

### So funktioniert es

pdfToolkit programmiert keine Druckerfunktionen selbst nach – es liest sie aus dem **Herstellertreiber**.
Darum ist die Reihenfolge immer gleich:

1. **Herstellertreiber installieren** (nicht den automatisch angelegten „driverless“/„IPP-Klassentreiber“ –
   der kann nur Grundfunktionen).
2. **Druckerwarteschlange anlegen** (Linux: CUPS-Queue, Windows: Drucker in den Einstellungen).
3. **Installierte Hardware eintragen** – Finisher, Locher, Kassetten, Decks. Erst dann bietet der Treiber
   die passenden Funktionen an.
4. **Standards festlegen** in pdfToolkit → *Verwaltung → Druckerstandards* (Fach, Format, Duplex …).
5. **Finisher-Vorlagen anlegen** (nur bei Geräten mit Finisher), z. B. „Broschüre heften + falzen“.
6. *Optional:* **Farbprofile** zuordnen (*Verwaltung → Farbprofile → Profile laden / importieren*).
7. **Testen** mit den Testseiten (Lineal 1:1, Broschüre 12 Seiten, Poster A2).

### Allgemein unter Linux

```sh
lpinfo -m | grep -i "<Modell>"                       # passenden Herstellertreiber (PPD) finden
lpinfo -v | grep -i "<Modell>"                       # Geräteadresse finden (dnssd://… bevorzugt)
sudo lpadmin -p <Name> -E -v "<Adresse>" -m <PPD aus lpinfo -m>
sudo lpadmin -d <Name>                               # Systemstandard (sonst nimmt pdfToolkit den ersten)
lpoptions -p <Name> -l                               # alle Treiberoptionen anzeigen
```

- Die Meldung „Druckertreiber sind veraltet …“ beim Anlegen ist nur ein Hinweis von CUPS 2.4 – die Queue
  funktioniert normal.
- **Automatisch angelegte Doppel-Queues** (z. B. `EPSON_ET_15000_Series`, `…@….local`) entfernen, sonst
  druckt man versehentlich über die Grundfunktions-Variante:
  ```sh
  sudo lpadmin -x <automatische Queue>
  echo "CreateIPPPrinterQueues No" | sudo tee -a /etc/cups/cups-browsed.conf
  sudo systemctl restart cups-browsed cups
  ```
- **Installierte Hardware:** pdfToolkit → *Verwaltung → Druckerstandards → Installierte Hardware*.
  Wird direkt in der CUPS-Queue gespeichert und gilt damit für alle Programme.

### Allgemein unter Windows

- Herstellertreiber von der Supportseite des Herstellers installieren und den Drucker damit hinzufügen
  (*Einstellungen → Bluetooth und Geräte → Drucker und Scanner*). Einen von Windows automatisch angelegten
  Drucker mit „Microsoft IPP Class Driver“ entfernen bzw. nicht verwenden.
- **Installierte Hardware:** *Druckereigenschaften → Geräteeinstellungen* (bei Canon-Treibern meist
  „Geräteinformationen abrufen“, das liest Finisher und Kassetten automatisch aus).
- In pdfToolkit stellst du die Herstellerfunktionen im **Original-Treiberdialog** ein
  (*Druckdialog → Endverarbeitung → Herstellereinstellungen* bzw. *Verwaltung → Druckerstandards →
  Herstellerdialog öffnen*). pdfToolkit merkt sich diese Einstellungen als Standard, Vorlage oder für die Sitzung.
- Mit „Auch als Windows-Standard des Druckers setzen“ gelten die Admin-Standards zusätzlich in allen
  anderen Programmen.

---

### Epson EcoTank ET-15000

| | Linux | Windows |
|---|---|---|
| **Treiber** | `epson-inkjet-printer-escpr2` (Epson-Download) – **nicht** die driverless-Variante | Epson-Druckertreiber für ET-15000 (Epson-Supportseite) |
| **Anschluss** | `dnssd://EPSON%20ET-15000%20Series._ipp._tcp.local/?uuid=…` (aus `lpinfo -v`) oder `socket://<IP>:9100` | Netzwerk/USB über den Epson-Installer |
| **Hardware eintragen** | entfällt (keine Zusatzhardware) | entfällt |

Linux, Beispiel:
```sh
sudo lpadmin -p Epson_ET15000 -E \
  -v "dnssd://EPSON%20ET-15000%20Series._ipp._tcp.local/?uuid=<aus lpinfo -v>" \
  -m lsb/usr/epson-inkjet-printer-escpr2/Epson/Epson-ET-15000_Series-epson-inkjet-printer-escpr2.ppd.gz
sudo lpadmin -d Epson_ET15000
```

Hinweise:
- **Fächer:** *Automatisch*, *Hintere Papierzufuhr*, *Papierkassette*. **A3/A3+ nur über die hintere
  Papierzufuhr** – die Kassette kann bis A4.
- **Randlos:** Formate mit „randlos“ (Treiberwerte `TA4`, `TA3` …) – druckbarer Bereich = ganzes Blatt.
- **Medientyp** enthält beim Epson zugleich die Qualität („Normalpapier – hohe Qualität“ …).
- **2 × A4 auf A3 (Step & Repeat):** nur mit „A3 randlos“, ohne Druckerränder oder mit ca. 97 % Maßstab.
- **Farbprofile:** RGB-Profile für Papier + Epson-502-Tinte – aus dem Epson-Windows-/Mac-Treiberpaket
  (in pdfToolkit direkt aus der .exe importierbar), von Papierherstellern oder selbst gemessen (ArgyllCMS).
  **Keine FOGRA-Profile als Ausgabeprofil** – FOGRA beschreibt Offsetdruck, nicht den Epson.

### Canon imageRUNNER ADVANCE DX C3822i

| | Linux | Windows |
|---|---|---|
| **Treiber** | Canon „UFR II/UFRII LT Printer Driver for Linux“ (Paket `cnrdrvcups-lb`) | Canon Generic Plus UFR II (oder PS3/PCL6) |
| **Anschluss** | `lpd://<IP>/print` oder `ipp://<IP>/ipp/print` | über den Canon-Installer / „Drucker hinzufügen“ |
| **Hardware eintragen** | *Installierte Hardware*: Finisher, Kassetteneinheit, Locher | *Geräteeinstellungen → Geräteinformationen abrufen* |

Linux, Beispiel:
```sh
lpinfo -m | grep -i "C3822"
sudo lpadmin -p Canon_C3822i -E -v lpd://<IP>/print -m <UFR-II-PPD aus lpinfo>
```

Hinweise:
- Ohne eingetragene Hardware meldet der Treiber Konflikte bei Heften/Lochen bzw. Kassette 3/4 (rot im
  Druckdialog) – in pdfToolkit bleibt trotzdem alles wählbar.
- Typische Vorlagen: „Heften oben links“, „2-fach-Lochung für Ordner“, „Duplex + Heften“.

### Canon imagePRESS V1350

**Mögliche Ausstattung** (laut Canon-Datenblättern): Staple Finisher-AG1/AF1, Booklet Finisher-AG1/AF1
(Sattelheftung), Locher BT1 (2/4-fach) / BU1 (4-fach), Paper Folding Unit-K (C-, Z-, Mitten-,
Doppelparallel-, Leporellofalz), Document Insertion Unit, Booklet Trimmer-F1/G1 (Vorderkantenbeschnitt),
Two-Knife Booklet Trimmer-B1, High-Capacity Stacker-J1, Perfect Binder-F1, Plockmatic BLM35/BLM50,
POD Deck-E.

| | Linux | Windows |
|---|---|---|
| **Treiber** | Canon-Linux-Treiber laut Canon-Support (Linux 64-Bit); mit Fiery-Steuerung (imagePRESS Server E9500) die Fiery-PPD, sofern für Linux angeboten | Canon-Treiber bzw. Fiery-Treiber (imagePRESS Server E9500) |
| **Anschluss** | Adresse des Druckers bzw. des Fiery-Servers | über den Canon-/Fiery-Installer |
| **Hardware eintragen** | *Installierte Hardware*: alle verbauten Finisher, Locher, Falzeinheit, Trimmer, Stapler, Decks | *Geräteeinstellungen* (Canon: „Geräteinformationen abrufen“; Fiery: „Zwei-Wege-Kommunikation“) |

### Canon imagePRESS V700 / V800 / V900

Finisher aus derselben Familie; welche Optionen konkret vorhanden sind, meldet der Treiber.

| | Linux | Windows |
|---|---|---|
| **Treiber** | Canon „UFR II/UFRII LT Printer Driver for Linux“ (ab V6.40, unterstützt V700/V800/V900) | Canon Generic Plus PS3 oder UFR II; mit Fiery (imagePRESS Server N500/P400) der Fiery-Treiber |
| **Anschluss** | `lpd://<IP>/print` oder `ipp://<IP>/ipp/print` bzw. Fiery-Server | über den Canon-/Fiery-Installer |
| **Hardware eintragen** | *Installierte Hardware* | *Geräteeinstellungen* |

### Finisher-Vorlagen (imagePRESS, imageRUNNER)

*Verwaltung → Druckerstandards → Finisher-Vorlagen → Neue Vorlage*. Unter Linux die Optionen aus der Liste
wählen, unter Windows über „Herstellerdialog für diese Vorlage“. Bewährte Vorlagen:

| Vorlage | Inhalt | Broschüre-Kennzeichen |
|---|---|---|
| Broschüre: heften + falzen | Sattelheftung ein | ja |
| Broschüre: heften + falzen + beschneiden | Sattelheftung + Vorderkantenbeschnitt (Booklet Trimmer) | ja |
| Heften oben links | Heftung oben links | – |
| Doppelheftung links | Heftung links doppelt | – |
| Ordnerlochung | 2-fach-Lochung | – |
| Flyer Wickelfalz | Wickelfalz (C) | – |
| A3 → A4 Z-Falz | Z-Falz | – |

**Wichtig bei Broschüren:** pdfToolkit schießt die Seiten bereits aus. Im Treiber bzw. in der Vorlage darf
**kein eigener Broschürendruck/Booklet-Ausschießen** aktiv sein – nur Sattelheftung/Falzen (und ggf.
Beschnitt). Sonst wird doppelt ausgeschossen.

### Automatische Fachwahl (Fächerbelegung)

Wählt man im Druckdialog ein Format (und optional eine Grammatur), nimmt pdfToolkit automatisch die
**erste Lade, in der genau das liegt**. Liegt dasselbe Papier in mehreren Laden, gilt die Reihenfolge der
Tabelle; ist die erste laut Gerät **leer**, wird die nächste genommen.

Einrichten: *Verwaltung → Druckerstandards → Fächerbelegung*

1. **Geräteadresse** eintragen (wird aus der Queue vorgeschlagen; bei `dnssd://`-Adressen die IP eintragen).
2. **„Vom Gerät lesen“** – fragt per IPP ab, was in welcher Lade liegt, und befüllt die Tabelle
   (Lade, Format, Grammatur). Klappt das nicht, die Zeilen von Hand anlegen.
3. **Reihenfolge** mit ▲/▼ festlegen (oben = Vorrang), Grammatur und ggf. Medientyp prüfen.
   Der Medientyp wird beim Druck mitgesetzt (wichtig bei Karton: Fixiertemperatur).
4. Optional **„Vor jedem Druck Füllstand am Gerät prüfen“** – leere Laden werden übersprungen.

Im Druckdialog erscheinen dann **Grammatur** und **„Fach automatisch nach Format/Grammatur wählen“**;
darunter steht, welche Lade genommen wird (gelb) bzw. warum keine passt (rot). Wer das Fach von Hand ändert,
behält seine Wahl. Finisher-Vorlagen, die selbst ein Fach festlegen (z. B. Umschlagkarton aus dem
Mehrzweckfach), haben Vorrang. Auch der Rechtsklick-Druck ohne Dialog wählt das Fach automatisch.

**Am Gerät** (gilt für den DX C3822i genauso wie für die imagePRESS-Modelle):
- Format und **Papiertyp/Grammatur je Kassette** am Bedienfeld bzw. im Remote UI hinterlegen – das ist die
  Grundlage für „Vom Gerät lesen“.
- **IPP** im Netzwerk aktiv lassen (Remote UI → Netzwerkeinstellungen), sonst ist keine Live-Abfrage möglich.
- **Automatische Kassettenumschaltung** einschalten: Läuft eine Lade *während* eines Auftrags leer, kann
  nur der Drucker selbst auf die nächste Lade mit gleichem Papier wechseln.
- Bei zwei Queues für dasselbe Gerät (z. B. Farbe/Schwarzweiß) die Belegung **bei beiden** eintragen.

### Nach dem Einrichten prüfen

1. **Lineal-Testseite** mit „Tatsächliche Größe“ drucken – das Quadrat muss 100 × 100 mm messen.
2. **Druckdialog** öffnen: Unter „Standards“ müssen die Admin-Werte für *genau diese* Queue stehen; unter
   „Endverarbeitung“ die Finisher-Felder bzw. (Windows) die Herstellereinstellungen.
3. **Broschüre** (12 Seiten) beidseitig drucken, falzen, Reihenfolge und Pfeile prüfen.
4. Fehlt eine Option im Bereich „Endverarbeitung“: Sie ist trotzdem im Reiter „Treiber“ vorhanden.
   Unter Linux zeigt `lpoptions -p <Queue> -l` die echten Optionsnamen.

### Häufige Stolperfallen

| Problem | Ursache | Lösung |
|---|---|---|
| Admin-Standard wirkt nicht | Mehrere Queues für dasselbe Gerät, gedruckt wird über eine andere | Doppel-Queues entfernen, Systemstandard setzen, im Druckdialog Queue-Namen prüfen |
| Finisher-Optionen fehlen | Hardware nicht eingetragen | Linux: *Installierte Hardware*; Windows: *Geräteeinstellungen* |
| Nur Grundfunktionen | driverless-/IPP-Klassentreiber statt Herstellertreiber | Herstellertreiber installieren, Queue neu anlegen |
| Broschüre falsch sortiert | Treiber schießt zusätzlich aus | im Treiber nur Sattelheftung/Falzen, kein Booklet-Ausschießen |
| Farben doppelt korrigiert | Farbprofil in pdfToolkit **und** Farbmanagement im Treiber | im Profil die Treiberoption „Farbabgleich aus“ hinterlegen |
| Papierformat falsch (A4 statt A3) | Treiber liefert keine Maße | rote Warnung im Druckdialog beachten, Treiber/PPD prüfen |
| Falsche Lade bei A3/A4 | Fächerbelegung fehlt oder Reihenfolge falsch | *Fächerbelegung* anlegen („Vom Gerät lesen“), Reihenfolge prüfen |
| „Vom Gerät lesen“ liefert nichts | IPP am Gerät aus, falsche Adresse oder Gerät meldet keine Belegung | IP statt Namen eintragen, IPP im Remote UI aktivieren, sonst Belegung von Hand |

## Windows: Bedienung im Überblick

- Admin-Standards: `%ProgramData%\pdfToolkit`; Speichern im Admin-Dialog fragt per **UAC** nach Freigabe.
- Explorer-Kontextmenü: PDFs (Drucken, Zusammenführen, Reparieren, Öffnen), Bilder und Office-Dateien
  (Als PDF öffnen, Zusammenführen). Windows 11: unter „Weitere Optionen anzeigen“.
- Mehrfachauswahl: Der Explorer startet je Datei einen Prozess – pdfToolkit sammelt sie (0,7 s) und
  behandelt sie gemeinsam.
- Office-Umwandlung zusätzlich über Microsoft Office (falls installiert).

## Tests

```sh
python3 tests/test_layout.py    # Ausschießen, Skalierung, Broschüre, Poster, Step & Repeat
python3 tests/test_backend.py   # PPD/IPP-Parsing, Finisher-Erkennung, Prüfregeln (CUPS-Attrappe)
python3 tests/test_printjob.py  # Rechtsklick-Druckpfad (PDF, Bild, Broschüre) mit CUPS-Attrappe
python3 tests/test_proof.py     # Vorschau-Farbsimulation
python3 tests/test_repair.py    # Reparieren, Passwort, ICC-Import
python3 tests/test_convert.py   # Office-Umwandlung (LibreOffice, falls installiert)
python3 tests/test_pdfout.py    # Als PDF speichern, Formularwerte beim Druck
python3 tests/test_trays.py     # automatische Fachwahl
python3 tests/test_ipp.py       # IPP-Abfrage der Laden
python3 tests/test_l10n.py      # Übersetzungen vollständig und konsistent
```

## Sprache / Language

*Datei → Einstellungen → Oberflächensprache*: Automatisch (Systemsprache), Deutsch, English, Magyar, Español,
Français. Wirksam nach einem Neustart (pdfToolkit bietet ihn direkt an). Reihenfolge: eigene Einstellung →
Admin-Standard (*Verwaltung → Allgemein → Standardsprache*) → Systemsprache → Englisch.

Übersetzungen liegen in `pdfdruck/lang/<sprache>.py` (Schlüssel = deutscher Text). Neue Texte im Code mit
`tr("…")` markieren; `tests/test_l10n.py` meldet fehlende Übersetzungen und abweichende Platzhalter.

## Name

Programm, Menüeintrag und Befehl heißen **pdfToolkit** / `pdftoolkit`. Intern (Python-Paket,
`/etc/pdfdruck`, Polkit-Helfer) bleibt der alte Name, damit bestehende Admin-Einstellungen erhalten bleiben.
Der Befehl `pdfdruck` funktioniert weiter.

## Lizenz

pdfToolkit ist freie Software unter der **GNU General Public License, Version 3 oder später**
(GPL-3.0-or-later), siehe `LICENSE`. Copyright (C) 2026 Hias.

Verwendete Komponenten behalten ihre eigenen Lizenzen: PySide6/Qt (LGPL-3), pikepdf/qpdf (MPL-2.0/Apache-2.0), pypdfium2/PDFium
(Apache-2.0/BSD-3), pycups (GPL-2.0-or-later), CUPS (Apache-2.0), Ghostscript (AGPL-3, als eigenes
Programm aufgerufen), Pillow/LittleCMS (HPND/MIT), img2pdf (LGPL-3), pillow-heif/libheif (BSD-3/LGPL-3),
IBM Plex (SIL OFL 1.1). Die App-Icons und Oberflächen-Icons sind Teil von pdfToolkit.

## Build (GitHub)

Jeder Push auf `main` baut automatisch (Repo → **Actions**):
- **Windows installer** → `pdfToolkit-<Version>-Setup.exe` (Python, Qt und Ghostscript enthalten)
- **Linux AppImage** → `pdfToolkit-<Version>-x86_64.AppImage` (Python, Qt und Ghostscript enthalten)

Beide Builds prüfen das fertige Programm mit `--selftest`. Ein Tag `v*` (z. B. `git tag v1.4.7 && git push --tags`)
hängt EXE und AppImage zusätzlich dauerhaft an ein GitHub-Release.

Lokal: `powershell -ExecutionPolicy Bypass -File windows\build.ps1` bzw. `./linux/build-appimage.sh`.
Normale Linux-Installation weiterhin: `sudo ./install.sh` (Entfernen: `sudo ./uninstall.sh`).
