# Änderungen – Passermark

## 1.8.5
- **Sonderformate im Druckdialog:** neben „Papierformat“ der Knopf *Sonderformate …* – Name, Breite × Höhe in mm
  anlegen oder löschen. Die Formate bleiben gespeichert und stehen bei allen Druckern und bei „Als PDF speichern“
  zur Wahl (mit ★). Gespoolt werden sie als Sondergröße: CUPS `PageSize`/`media` = `Custom.BxHmm`, Windows
  benutzerdefiniertes Papier (DMPAPER_USER mit Breite/Länge). Ob ein Gerät das Maß annimmt, entscheidet sein
  Treiber; die Druckränder werden vom Standardformat des Druckers übernommen
- Druck-Presets mit Sonderformat merken sich das Maß (für `passermark-cli impose`: `sheet=custom`)

## 1.8.4
- **Behoben: Absturz-Meldung nach dem Schließen** eines Fensters/Reiters („expected LP_struct_fpdf_document …“ in
  der Seitenanzeige) – die Ansicht greift auf das geschlossene Dokument nicht mehr zu
- **CutContour Kreis:** Seitengriffe skalieren gleichmäßig (vorher kurz ein Oval, dann zurückgesprungen; die Felder
  blieben z. B. auf 60 × 120). Beim Kreis gibt es nur noch einen Durchmesser (Höhe folgt der Breite)
- CutContour: Knopf ↺ neben „Größe“ setzt Größe und Lage zurück (automatisch aus dem Motiv, mittig)
- **Auf Format beschneiden:** neu „Weißen Rand vorher abschneiden“ (mm, Kommandozeile `crop_inset_mm`) – zuerst
  wird die Vorlage rundum um diesen Wert verkleinert, dann wie eingestellt skaliert und beschnitten

## 1.8.3
- **Behoben: Nutzen „Überfüller an Überfüller“ ließ Abstände zwischen Objekten** – bei Einzelobjekten aus
  CutContour bzw. „Objekte trennen“ wurde die ganze Seite samt weißem Rand gesetzt. Jetzt tragen diese Seiten ihr
  Endformat mit: CutContour = Schnittlinie (Anschnitt = Überfüller), Objekte trennen = Objekt (Anschnitt = Rand).
  Beim Ausschießen liegen die Überfüller aneinander
- Nutzen „Überfüller an Überfüller“ mit Anschnitt 0: der Anschnitt aus dem Dokument (BleedBox) wird übernommen –
  ein eingestellter Wert hat Vorrang. „Mit Abstand“ 0 setzt die Endformate (Schnittlinien) direkt aneinander

## 1.8.2
- **Dialoge sperren nur noch ihr eigenes Fenster:** Druckdialog, CutContour, CMYK … offen – in anderen
  Passermark-Fenstern kann man weiter blättern, zoomen, arbeiten. (Reiter im selben Fenster gehören zum Fenster
  und sind solange gesperrt; „In eigenem Fenster öffnen“ löst einen Reiter.)
- Broschüre: „Bögen je Lage“ ist immer einstellbar; wer die Zahl ändert, bekommt automatisch „Gruppierte Lagen“
  (bei Sammelheftung blieb die Zahl sonst ohne Wirkung). Test für 24 Seiten mit 3 Bögen je Lage ergänzt

## 1.8.1
- **Reiter (Tabs):** Was im Programm entsteht oder geöffnet wird, kommt als Reiter ins selbe Fenster – Öffnen-Knopf
  bei offenem Dokument, Hineinziehen, Ergebnisse (CutContour, CMYK/Beschneiden, Objekte trennen …), „Jetzt in
  Passermark öffnen“ nach „Als PDF speichern“, Hilfe-Anleitung. Programmstart ohne Datei und Doppelklick bzw.
  „Öffnen mit“ im Dateimanager öffnen weiter ein eigenständiges Fenster. Jeder Reiter ist ein vollständiges
  Fenster mit eigenen Menüs, Leisten und Seitenleisten; mit nur einem Dokument ist die Reiterleiste ausgeblendet
- Reiter: verschieben per Ziehen, schließen mit ×, Rechtsklick → „In eigenem Fenster öffnen“ / „Andere
  schließen“; Datei → Neuer Reiter (Strg+Umschalt+N), Reiter in eigenes Fenster lösen, Neues Fenster (Strg+N).
  Beim Schließen eines Fensters mit mehreren Reitern wird für jedes ungespeicherte Dokument nachgefragt
- Abschaltbar: Datei → Einstellungen → Fenster → „Im Programm Geöffnetes als Reiter im selben Fenster“

## 1.8.0
- **Bindungsschemata** (Druckdialog → Broschüre): *Bindeart* Sammelheftung (alle Bögen ineinander), gruppierte
  Lagen (z. B. 4 Bögen = 16 Seiten je Lage, Lagen hintereinander) oder Einzelbögen gestapelt (Klebebindung).
  Vorschau beschriftet „Lage x · Bogen y – Vorder-/Rückseite“
- **Leerseiten:** werden auf ein Vielfaches von 4 aufgefüllt – am Ende oder vor der letzten Seite (Rückseite des
  Umschlags bleibt hinten); optional mit Hinweistext
- **Bundzug** (mm je Bogen, ≈ Papierstärke): innere Bögen werden zum Falz verschoben
- **Marken:** Falzmarken, Passermarken, Flattermarken am Rücken (Treppe beim Zusammentragen); dafür wird am
  Bogenrand Platz freigehalten
- **Bogenübersicht …:** alle Bögen als Miniaturen, Doppelklick springt in die Vorschau
- **Kommandozeile `impose`:** Ausschießen wie im Druckdialog als PDF (Broschüre/Lagen, Nutzen, Mehrere, Poster),
  Bogenformat mit `sheet` (z. B. SRA3). Druck-Presets aus dem Programm gelten direkt und merken sich das Papierformat
  (`--preset "Name"`); vorhandene Druck-Presets aus 1.7 werden übernommen. Anleitung um Fallbeispiele ergänzt
- **Anschnitt aus dem Dokument wird erkannt** (TrimBox/BleedBox, z. B. aus InDesign/Affinity/Scribus mit
  „Anschnitt verwenden“): Ansicht zeigt das Endformat als rote Linie, den Anschnittbereich rot getönt, die BleedBox
  gestrichelt (wird nicht gedruckt; Ansicht → Endformat und Anschnitt anzeigen, Strg+Umschalt+B); Statusleiste
  nennt Endformat und Anschnitt. Beim Ausschießen (Nutzen, Broschüre, Schnittmarken, Anschnitt) wird das
  Endformat platziert und skaliert – Schnittmarken sitzen am Endformat, der Anschnitt kommt echt aus dem
  Dokument; nur wenn mehr Anschnitt eingestellt ist als vorhanden, wird der Rest an der Seitenkante gespiegelt.
  Normaler Druck („Größe“) druckt weiter die ganze Seite
- **Behoben: Passermark ein zweites Mal starten (Startmenü, Symbol) tat nichts**, solange schon ein Fenster offen
  war – die laufende Instanz öffnet jetzt ein neues, leeres Fenster. Neu: Datei → Neues Fenster (Strg+N)
- Druckdialog: Preset-Zeile steht über den Reitern (gilt für Allgemein und Weitere Optionen)
- Test: Falz-Simulation (falzen, ineinanderstecken, Lagen stapeln) prüft für alle Bindearten, Bindung links/rechts
  und Leerseiten-Lagen, dass die Seiten 1…N ergeben

## 1.7.1
- **Beschneiden auf Format skaliert jetzt** (Standard): die passende Kante wird genau aufs Zielformat skaliert,
  der Überstand der anderen Kante beidseitig gleich abgeschnitten – A4 → A6 = 50 %, ein schmales Plakat füllt die
  Breite und verliert oben/unten gleich viel. Kleinere Seiten werden hochskaliert. Inhalt bleibt vektoriell.
  Bisher wurde nur abgeschnitten; das gibt es weiter als Option (Häkchen „Skalieren, bis das Format ganz gefüllt
  ist“ aus bzw. `--set crop_scale=false`) für Dateien, die schon in Endgröße mit Anschnitt kommen.
- Kommandozeile/Ketten: `preflight_fix --set fix=flatten_layers` bricht bei Dateien ohne Ebenen nicht mehr ab,
  sondern reicht die Datei unverändert durch (Hinweis „Keine Ebenen“)

## 1.7.0
- **Arbeitsbereiche:** zweite Leiste unter der Werkzeugleiste – *Anzeigen & Drucken*, *Druckaufbereitung*,
  *Bearbeiten*, *Automatisierung*. Rechts daneben stehen die Werkzeuge des gewählten Bereichs (z. B. Prüfen, CMYK,
  Beschneiden, CutContour, Objekte trennen, Reparieren). Druckaufbereitung öffnet die Prüfung, Bearbeiten die
  Seitenleiste; wer den Bereich verlässt, beendet den Bearbeiten-Modus. Der zuletzt gewählte Bereich gilt beim
  nächsten Start. Die Menüs bleiben vollständig.
- **Presets:** in den Fenstern CutContour, CMYK/Beschneiden und im Druckdialog oben die Zeile *Preset* – wählen,
  *Speichern…*, löschen, als Datei exportieren/laden, Standardwerte. Druck-Presets umfassen Seitenhandhabung,
  Mehrere, Broschüre, Poster, Nutzen und weitere Optionen (ohne Drucker und Fach).
  Ablage: Linux `~/.config/passermark/presets/`, Windows `%APPDATA%\Passermark\presets\`
- CutContour merkt sich die zuletzt verwendeten Einstellungen (ohne Versatz der Form)
- **Kommandozeile:** `--preset NAME` findet ein im Programm gespeichertes Preset; `passermark-cli presets [auftrag]`
  listet sie. Anleitung ergänzt.
- **Als PDF speichern mit Passwort** (Druckdialog, Ziel „Als PDF speichern“): Häkchen *PDF mit Passwort schützen*
  (AES-256, Passwort zweimal eingeben)
- **Windows-Setup:** optional *passermark-cli in jeder Eingabeaufforderung verfügbar machen* (Suchpfad PATH;
  beim Deinstallieren wieder entfernt)
- Tastenkürzel ohne Doppelbelegung: Messen jetzt Strg+Umschalt+L (Strg+Umschalt+M = CMYK und Beschneiden),
  Text und Ebenen bearbeiten Strg+T (Strg+E = Auswahl exportieren), Text der Seite markieren Strg+Alt+A
  (Strg+Umschalt+A = alle Seiten auswählen); ein Test prüft das künftig
- Eigene Symbole für CutContour, CMYK, Beschneiden, Objekte trennen, Bearbeiten, Prüfen, Reparieren, Messen u. a.
  (vorher teils doppelt vergebene Symbole)

## 1.6.7
- **Zeitbudget-Tests im GitHub-Build** (tests/test_performance.py): CutContour (Kontur + Überfüller, Rechteck),
  Objekterkennung, PDF-Aufbau und Broschüre werden gemessen – relativ zu einer Eichaufgabe auf demselben Rechner,
  damit unterschiedlich schnelle Build-Rechner keinen Fehlalarm auslösen. Ab 1,6× langsamer als bisher gelbe
  Warnung am Build, ab 3× schlägt der Build fehl. Bezugswerte in tests/perf_baseline.json
  (neu messen: `python3 tests/test_performance.py --messen`)

## 1.6.6
- **Behoben: leere Blätter beim Drucken unter Windows** (verschiedene Geräte). „Automatisch“ rastert jetzt immer
  ohne JPEG (300 dpi) – der verträglichste Weg. PostScript und JPEG-Durchreichen melden manche Treiber
  als unterstützt und liefern dann leere Blätter; beide gibt es nur noch auf Wunsch (Datei → Einstellungen)
- Neu: **Hilfe → Windows-Druck testen** – je Verfahren (Raster, Raster + JPEG, PostScript, Vektor) eine
  beschriftete Testseite; zeigt, was der Treiber wirklich kann
- Windows-Druck: Gerätekontext wird als 64-bit-Zeiger übergeben (vorher ctypes-Standard int), Halbton-Modus beim
  Rastern; jeder Auftrag wird in `druck-windows.log` im Protokollordner festgehalten (Verfahren, Auflösung,
  Treiber-Fähigkeiten)
- **Behoben: rötliches Rechteck über dem Objekt (CutContour)**, wenn ein Programm oder Druckertreiber die
  Transparenz der Überfüller-/Kantenbilder nicht auswertet (u. a. Windows-PostScript-Weg): unsichtbare Bereiche
  sind jetzt papierweiß bzw. zeigen das Original-Motiv statt der ersten Vollfarbe

## 1.6.5
- **Fehlerprotokoll:** jeder Fehler landet in einer Datei zum Mitschicken (mit Versionen und Systemangaben) –
  Linux `~/.local/state/passermark/logs`, Windows `%LOCALAPPDATA%\Passermark\logs`; Hilfe → Fehlerprotokolle öffnen
  - unerwarteter Fehler: Meldung mit Pfad zum Protokoll, Passermark läuft weiter
  - harter Absturz (z. B. in einer Bibliothek): beim nächsten Start einmalige Meldung mit dem Protokoll
  - Fehler in Hintergrund-Aufträgen samt Details; Fehler in Threads
  - ohne Fehler wird das Protokoll beim Beenden gelöscht; höchstens 10 werden aufgehoben
- Paralleles Rechnen: Speicherbudget nach dem tatsächlichen Arbeitsspeicher des Rechners (40 %, mind. 1 GB)

## 1.6.4
- CutContour mit **mehreren Seiten: ganze Seiten parallel** – jeder Arbeitsprozess rechnet eine komplette Seite
  (auch Rendern und Erkennen); kein Stocken mehr zwischen den Seiten. Eine Seite: weiterhin Objekte parallel
- Speicherschutz: Anzahl gleichzeitiger Seiten nach geschätztem Speicherbedarf (z. B. A4: bis 8, A0: 1 – dann
  Objekte parallel)
- Fortschritt bei mehreren Seiten: „3 von 12 Seiten fertig“; Ergebnis bitgleich zum seriellen Rechnen

## 1.6.3
- **Paralleles Rechnen:** CutContour verteilt die Objekte einer Seite auf mehrere Rechenkerne (alle bis auf einen,
  höchstens 8); Ergebnis bitgleich zum seriellen Rechnen. Arbeitsprozesse werden einmal je Auftrag gestartet und für
  alle Seiten verwendet; kleine Aufgaben bleiben seriell (lohnt sich dort nicht). Begrenzen mit der Umgebungsvariable
  `PASSERMARK_WORKERS` (1 = nicht parallel)
- Fortschritt je Objekt („Seite 1/1 · Objekt 12/40“)
- Abbrechen beendet auch die Arbeitsprozesse
- Intern: Objektberechnung als eigene Funktion; Programmdateien rufen `multiprocessing.freeze_support()` auf

## 1.6.2
- **Kein Einfrieren mehr:** CutContour, Objekte trennen und CMYK/Beschneiden rechnen als eigener Prozess im
  Hintergrund. Das Fenster bleibt bedienbar; unten in der Statusleiste Fortschritt und Abbrechen-Knopf (✕);
  mehrere Aufträge gleichzeitig möglich; das Ergebnis öffnet sich wie gewohnt in einem neuen Fenster
- Ein Absturz in der Berechnung reißt das Programm nicht mehr mit – es kommt eine Fehlermeldung mit Details
- Beim Schließen eines Fensters werden laufende Aufträge abgebrochen und aufgeräumt
- Anleitung: Beispiel „PDF/A mit Passwort“ korrigiert (PDF/A verbietet Verschlüsselung) – getrennt in „PDF/A“ und
  „Mit Passwort schützen“; Test der Beispiele legt jetzt für jedes Beispiel eine Eingabe an (Build-Fehler unter Linux)

## 1.6.1
- **Anleitung zur Kommandozeile** (PDF, 6 Seiten) mit Fallbeispielen für alle Aufträge, Presets und ganze Ordner
  (Linux und Windows); im Programm unter **Hilfe → Kommandozeile – Anleitung**
- Die Fallbeispiele der Anleitung werden automatisch getestet (tests/test_cli_howto.py) – die Anleitung kann nicht
  unbemerkt veralten; Erzeugen mit `python3 docs/make_cli_howto.py`

## 1.6.0
- **Kommandozeile** `passermark-cli`: CutContour, Objekte trennen, CMYK/Beschneiden, Reparieren und
  Preflight-Reparaturen ohne Oberfläche; Einstellungen per `--preset datei.json` und `--set schlüssel=wert`
  (auch verschachtelt), `--pages`, Fortschrittsbalken, Strg+C bricht sauber ab, `--json-progress` für Programme.
  Linux: `passermark-cli` (install.sh), AppImage: `… --cli`, Windows: `passermark-cli.exe`
- Intern: Kern-Schnittstelle `core.py` (Eingabe-PDF + Einstellungen → Ausgabe-PDF, Fortschritt, Abbrechen,
  atomares Schreiben) – Grundlage für Aufträge im eigenen Prozess, Presets und Watcher

## 1.5.3
- CutContour erzeugt schneller (ca. 17–20 %), Ergebnis bitgleich zu 1.5.2: Motiv-Erkennung rechnet ganzzahlig,
  Vollfarb-Suche nur noch im Randstreifen, unnötige Abstandsberechnungen entfallen (u. a. eine pro Objekt bei der
  Glättung, eine beim Aussparen unter 0,08 mm)

## 1.5.2
- CutContour-Grundformen: **Griffe** an der Form in der Vorschau – Ecken skalieren gleichmäßig ab der Mitte,
  Seitengriffe nur Breite bzw. Höhe, **Verschiebe-Griff** über der Form verschiebt sie
- Größe nur noch in **mm** („Größe (B × H)“, „auto“ = aus dem Motiv plus Abstand); Prozent entfällt.
  Eine eingetragene Größe gilt exakt als Schnittlinie; Ziehen an den Griffen schreibt die mm-Werte in die Felder
- Neu: **Versatz (X / Y)** in mm, mit Knopf zum Zurücksetzen
- Behoben: Nach dem Skalieren mit der Maus wirkten eingegebene Größen nicht mehr (versteckter Prozentfaktor)
- Anzeige unten: aktuelle Formgröße in mm, beim Ziehen live

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
