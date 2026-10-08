# Änderungen – Passermark

## 1.5.1
- CutContour mit Grundform (Rechteck, Kreis, Herz …): **eine Form um das ganze Motiv** statt einer je erkanntem Teil;
  sitzt mittig, Größe ändert sich ab der Mitte. Option „Eine Form je Objekt“ für Aufkleberbögen
- CutContour: Form in der Vorschau **mit der Maus größer/kleiner ziehen** (Live-Anzeige in %, übernommen beim Loslassen)
- Kreis umschließt das Motiv (größere Seite als Durchmesser), statt bei breiten Motiven hindurchzuschneiden

## 1.5.0
- **Lineale und Messen** (Ansicht → Lineale anzeigen, Strg+R; Ansicht → Messen, Strg+Umschalt+M, auch in der
  Werkzeugleiste): Lineale in mm oben und links an der Kante der Ansicht, bleiben beim Scrollen stehen, Nullpunkt =
  linke obere Seitenecke, Mausposition markiert; Messen: 1. Klick Anfang, 2. Klick Ende, Umschalt rastet
  waagrecht/senkrecht/45° ein, Esc bricht ab; Ergebnis (Länge, ΔX, ΔY, Winkel) rechts unten in der Statusleiste;
  gemessen in echten Seitenmaßen, unabhängig von Zoom und Drehung

## 1.4.7
- CutContour: Vorschau aktualisiert sich automatisch bei jeder Einstellung – vorher zeigte sie nach einem
  Formwechsel (Rechteck, Kreis, Herz …) weiter die alte Kontur, bis man „Vorschau aktualisieren“ drückte
- CutContour: Vorschau rechnet im Hintergrund, das Fenster bleibt bedienbar („Berechne Vorschau …“); schnelle
  Änderungen hintereinander lösen nur eine Berechnung aus
- Neuer Test (tests/test_cut_dialog.py): Formwechsel ändert die Vorschau

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
- `uninstall.sh`, `.gitignore`; Installer-Skript UTF-8 mit BOM; `build.ps1` reines ASCII; README auf Englisch

## 1.4.5
- **Windows-Druck neu** (wie pdfToolkit 1.4.3): PostScript direkt für PS-Treiber, sonst eigenes Rastern in Streifen
  mit JPEG – behebt langes Spoolen und Abbrüche (besonders bei Mehrfachnutzen); Einstellungen unter
  Datei → Einstellungen → „Drucken unter Windows“. Linux-Druck unverändert
- Behoben: mögliche Abstürze – die Dokumentprüfung nutzte pdfium in einem Hintergrund-Thread gleichzeitig mit der
  Anzeige (pdfium ist nicht thread-sicher); diese Teile laufen jetzt im Hauptthread

## 1.4.4
- **Ursache gefunden** (an einer Chrome-PDF): pdfium kann Seiten mit **Type3-Schriften** nicht neu schreiben –
  bisher verschwand dabei aller Text. Bearbeiten kommt jetzt ganz ohne Neuerzeugung der Seite aus:
  - Verschieben/Skalieren: Zeile wird aus ihrem Textblock herausgelöst (Zeilenmatrix wird mitgerechnet), auch wenn
    sich viele Zeilen einen Block teilen
  - Text/Schrift ändern: zuerst direkt; verliert die Seite dabei Inhalt, wird die alte Zeile entfernt und die neue
    an gleicher Stelle und in gleicher Farbe darübergelegt
  - Löschen: nur die Textbefehle der Zeile werden entfernt
- Koordinatensystem wird mitgerechnet (Chrome: Maßstab 0,24 + gespiegelt; CAD: 0,12) – beim Verschieben von Text
  und Ebenen, beim Ersetzen von Ebenen und bei der CutContour-Linie (Originalinhalt wird in q/Q eingeschlossen)
- Zeilen werden besser erkannt (auch bei Schriftwechsel in der Zeile und einzeln gesetzten Buchstaben)
- Nachprüfung empfindlicher (auch bei Seiten mit wenig Text)
- Neue Tests: Chrome-artige Type3-Datei, CAD-Ebene in skaliertem Koordinatensystem

## 1.4.3
- Behoben: Nach Verschieben/Skalieren per Maus, Textänderung oder Schriftwechsel konnten alle Texte der Seite
  verschwinden
  - Verschieben/Skalieren von Text ändert jetzt nur noch die betroffenen Textblöcke im PDF (q/cm/Q), die übrige
    Seite bleibt byte-gleich; pdfiums Neuerzeugung der Seite nur noch als Rückfall
  - jede Textbearbeitung läuft auf einer Kopie und wird **nachgeprüft** (Zeichen und Bildpunkte außerhalb der
    bearbeiteten Zeile); fehlt etwas, wird nichts übernommen und eine Meldung mit Details erscheint
  - die Ansicht gibt vor der Bearbeitung ihre offenen Seiten frei
- Start-Test deutlich strenger (fehlende eigene Methoden fallen sofort auf) und prüft jetzt auch Text ändern,
  Schrift wechseln und Löschen – dabei bleiben alle anderen Zeilen erhalten

## 1.4.2
- Behoben: „don't know how to encode value np.float64“ beim Skalieren von Ebenen (Bezug „Mitte der Ebene“)
- Behoben: Mausauswahl im Bearbeiten-Modus fand nichts, wenn die Listen beim Einschalten nicht geladen waren
- **Mit der Maus verschieben und skalieren:** Objekt (Textzeile/Ebene) greifen und ziehen; an den vier Eckgriffen
  skalieren (gegenüberliegende Ecke bleibt fix); gestrichelte Vorschau, passende Mauszeiger, Rückgängig
- Textzeilen verschieben/skalieren behält Schrift, Farbe und Ebene
- Feinere Ebenen-Erkennung; Start-Test prüft jetzt auch die Mausbedienung

## 1.4.1
- Behoben: Programm startete nicht (Namenskonflikt in der Seitenansicht durch die neue Textauswahl)
- Behoben: Strg+C (Text kopieren) hätte einen Fehler ausgelöst (fehlender Import)
- Neuer Start-Test (tests/test_gui_smoke.py): Programmstart, Fenster, Textauswahl, Bearbeiten-Modus – ohne Bildschirm

## 1.4.0
- **Bearbeiten-Modus** (Dokument-Manipulation → Text und Ebenen bearbeiten, Strg+E): Seitenleiste „Bearbeiten“
  - **Text:** Zeilen der Seite auflisten oder auf der Seite anklicken; Text, Schrift (Original, Standardschriften,
    eigene Datei) und Größe ändern, Zeile löschen
  - **Ebenen:** auflisten oder auf der Seite anklicken (wiederholter Klick wechselt durch übereinanderliegende);
    ein-/ausblenden, entfernen, skalieren/verschieben (inkl. „Auf die Seite zurückholen“), durch eine Seite einer
    anderen PDF ersetzen; Rückgängig
- **Text markieren** in der Seitenansicht (ziehen, Doppelklick = Wort, Strg+C kopiert)
- Schrift-Download: eigene Knöpfe unter der Tabelle, sichtbare Fehlermeldungen, Rückfall auf das fontsource-CDN
- Übersetzungen: fehlende Texte ergänzt (Druckdialog, Admin, Zusammenführen, Dateifilter, Meldungen),
  „&“ in Übersetzungen ausgeschrieben, deutsche Treiberbegriffe (deutsch installierte PPDs) werden übersetzt

## 1.3.2
- Behoben: Dialog „Freie Schrift herunterladen“ öffnete sich nicht
- Ebenen festschreiben / Empfohlene Reparaturen: unterscheiden sich Ansicht und Druck, fragt Passermark, welcher
  Zustand gelten soll („Wie beim Druck“ / „Wie am Bildschirm“) – statt still den Druck-Zustand zu nehmen
- Einbetten: Warnung, wenn für eine fehlende Schrift kein Ersatz gewählt ist (Ghostscript nähme sonst eine eigene)
- CAD-Normschriften (ISOCPEUR & Co.) ohne osifont: schmale Ausweichschrift (DejaVu Sans Condensed)
- Schriften mit eigenen Zeichennamen (ohne Einbettung) werden als nicht reparierbar erkannt

## 1.3.1
- Schrift-Download: kommerzielle Schriften werden auf ihren freien, metrisch gleichen Zwilling umgeleitet
  (Arial → Arimo, Times New Roman → Tinos, Courier New → Cousine, Calibri → Carlito, Cambria → Caladea,
  Georgia → Gelasio); der Dialog schlägt ihn vor und erklärt warum
- Unbekannter Name: Vorschläge ähnlicher freier Schriften („Meintest du …“) statt nur „404“

## 1.3.0
- **Neuer Name: Passermark** (vorher pdfToolbox – Namensgleichheit mit einem kommerziellen Preflight-Produkt);
  eigene Pfade (/etc/passermark, /usr/local/lib/passermark), läuft neben pdfToolkit/pdfToolbox
- **Dokumentprüfung (Preflight)** beim Öffnen: Schriften (Einbettung, Typ, Unicode, seltsame Zeichen), Ebenen
  (Ansicht/Druck, verrutscht), Transparenzen; Statusknopf, Seitenleiste „Prüfung“, Bericht
- Reparaturen: Ebenen-Zustand übernehmen, sichtbaren Zustand festschreiben, Ebenen entfernen, Schriften einbetten
  mit metrisch kompatiblem Ersatz / eigener Datei / Download (fontsource.org), Text in Pfade, Transparenzen reduzieren
- install.sh: freie Ersatzschriften (Liberation, Carlito, Caladea, URW, DejaVu)

## 1.2.5
- CutContour: **Überfüller abschaltbar** („erzeugen“ bzw. 0 mm) – Motiv bleibt unverändert (kein Überfüller, kein
  Ausstanzen), nur die Schnittlinie; mit positivem „Abstand zum Motiv“ entstehen weiße Ränder

## 1.2.4
- CutContour-Farben: **Entmischen** statt RGB-Abstand – Kantenpixel werden als Mischung Vollfarbe+Hintergrund
  bzw. Vollfarbe+Vollfarbe gedeutet (helles Rosa = Rot, nicht Grün); behebt falschfarbige Keile im Überfüller
- Überfüller-Farbe kommt aus dieser Zuordnung; innerhalb der Schnittform immer voll deckend
- Aussparung: winzige Löcher geschlossen (keine weißen Pünktchen), engere Toleranz (kein heller Strich)
- Neu: **Überfüller-Farbe fest wählbar** (gleichmäßiger Rand) für Motive, bei denen die Automatik nicht passt
- Neu (optional): **Mischkanten im Motiv bereinigen** (schmale Säume bis ~1 mm zwischen Vollfarben)

## 1.2.3
- CutContour-Überfüller in **Vollfarben**: Farbe = rechnerisch nächste Vollfarbe des Objekts (exakter
  Originalton), keine blassen Mischtöne mehr von Kantenglättung/skaliertem Raster
- **Heller Saum entfernt:** Bei Motiven mit Hintergrund wird der Mischsaum am Rand ausgespart (flächige Motive:
  adaptiv bis 1,5 mm, Fotos: 0,25 mm) – dort liegt der vollfarbige Überfüller
- **Innenschnitt mit Überfüller:** ausgeschnittene Löcher werden im Original ausgespart, der Überfüller läuft
  über die innere Schnittlinie; kleine Innenflächen (weiße Schrift) bleiben

## 1.2.2
- Behoben: Fehler „don't know how to encode value np.float64“ bei „Jedes Objekt als eigene Seite“ + Überfüller
  (Seitenmaße werden jetzt als normale Zahlen an pikepdf übergeben)
- Behoben: Überfüller unsichtbar bei Motiven mit Hintergrund (weiße Seite, Rasterbild) – das Original wird auf
  die Objektform begrenzt (Hintergrund ausgestanzt), Innenflächen wie weiße Schrift bleiben; Vorschau ebenso

## 1.2.1
- Objekte trennen: **Rand wirkt sofort** (auch negativ, auch auf selbst gezogene Rahmen) – vorher nur nach
  „neu erkennen“; gestrichelte Vorschau des Randes; übrige Regler erkennen automatisch neu
- CutContour: **Überfüller füllt die ganze Fläche innerhalb der Schnittlinie** (Raum zwischen Objekt und
  Linie, Einbuchtungen) plus Überfüller über die Linie – Randfarben (auch mehrfarbig) nach außen gezogen,
  liegt hinter dem Objekt; Farben aus dem Kern (keine Mischfarben von der Kantenglättung)
- Fehlermeldungen in den Objekt-Dialogen mit „Details“ (Ablauf zum Kopieren)

## 1.2.0
- CutContour: **Stickerformen** Rechteck, abgerundetes Rechteck, Kreis, Oval, Sechseck, Achteck, Herz, Stern,
  Wappen, Torbogen – in Objektgröße, skalierbar (%) oder feste Größe (mm); Abstand auch negativ
- CutContour: **Überfüller geht vom Objekt aus** (keine Rahmen in leeren Flächen); Schnitt am Motiv liegt
  immer im Überfüller
- CutContour: Ausgabe wahlweise **jedes Objekt als eigene Seite** mit Rand (Standard 6 mm), Nachbarn ausgeblendet
- Erkennung: Motiv, das die ganze Seite füllt, wird als ein Objekt erkannt (Kontur hing vorher am Seitenrand);
  Auto-Modus erkennt Hintergrund auch bei teilweise transparenten Seiten
- Objekte trennen: Rand auch **negativ** (nach innen)

## 1.1.0
- **Objekte trennen:** Objekte (Visitenkarten, Fotos auf Scans …) erkennen und als Einzelseiten ohne Weißraum
  öffnen; Vektor exakt über Transparenz, Raster über Hintergrundfarbe; Rahmen bearbeitbar
- **CutContour** für Schneideplotter (Roland VersaWorks): Sonderfarbe „CutContour“, Abstand, Glättung zum
  Entgittern, automatisch erzeugter Überfüller (Schnitt liegt immer darin), Innenkonturen, Vorschau
- **SVG/SVGZ öffnen** (vektoriell, echte Größe; rsvg-convert > Inkscape > Qt), auch per Rechtsklick und Zusammenführen
- Transparenz bei WebP/GIF/HEIC bleibt erhalten (statt auf Weiß geplättet)
- Neue Abhängigkeiten: scipy, contourpy, librsvg2-bin

## 1.0.1
- Dokument-Manipulation jetzt als eigenes Menü neben „Dokument“ (CMYK-Umwandlung, Beschneiden, beides);
  nicht mehr im Druckdialog
- Ergebnis öffnet sich in einem neuen Fenster, abgelegt nur temporär im Zwischenspeicher (beim Beenden gelöscht)
- Behoben: Beschneiden wirkte beim Druck nicht – gedruckt wird jetzt die beschnittene Datei selbst
  (durchgehender Test: Beschneiden -> Zwischenspeicher -> Druck, Rand verschwindet)
- Menü „Dokument“: Zusammenführen und Reparieren/Optimieren

## 1.0.0 (Oktober 2026)
Erste Version von Passermark, aufgebaut auf pdfToolkit 1.4.0 (alle Funktionen übernommen).

- **Dokument-Manipulation** (Reiter im Druckdialog und Menü Dokument):
  - CMYK-Umwandlung: RGB→CMYK mit unverändertem CMYK, komplette Neuseparation (Quell- → Zielprofil),
    Graustufen; Intent, BPC, Grau/Schwarz nur mit K, Output Intent
  - Farbvorschau vorher/nachher aus echten CMYK-Werten, Einzelauszüge, Farbauftrag (TAC), Papierweiß
  - Beschneiden auf Zielformat mit beidseitig gleichem Überstand, Hoch-/Querformat folgt der Seite
- Eigenständig installierbar neben pdfToolkit (eigene Pfade, Admin-Helfer, Polkit-Regel, Einzelinstanz)
- Eigenes Icon; alle Texte in Deutsch, Englisch, Ungarisch, Spanisch, Französisch
