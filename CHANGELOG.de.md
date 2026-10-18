# Changelog â Passermark

**English:** [CHANGELOG.md](CHANGELOG.md) Â· **Deutsch** Â· [Magyar](CHANGELOG.hu.md) Â· [FranÃ§ais](CHANGELOG.fr.md) Â· [EspaÃ±ol](CHANGELOG.es.md)

## 1.15.1
### Nutzen (Step & Repeat): Drehung
- Passt das Raster in keiner Lage ganz aufs Blatt, gewinnt jetzt die Lage mit dem kleinsten Überhang. Erst danach zählt „lieber ungedreht“.
- Hochformat-Daten werden damit genauso platziert wie Querformat-Daten.
- Gleich geändert in Schritt 2 und für den Fall, dass ein Nutzen nicht einmal einzeln aufs Blatt passt.
- Passt alles, bleibt es bei „ungedreht“. „Nutzen drehen: 0°“ bzw. „90°“ erzwingt die Drehung weiterhin.

### Papierformate
- Die Maße kommen jetzt immer zuerst vom Drucker, in dieser Reihenfolge: `*PaperDimension`, sonst `<</PageSize[b h]>>` aus der PPD, sonst aus Name oder Anzeigetext (z. B. „8K 270 x 390 mm“) – erst dann die Tabelle.
- Eine Formattabelle (papersizes.py) statt drei. Neu dabei: SRA4, SRA2, SRA0–1, RA-Reihe, A7–A10, ISO-B, C0–C10. Die bisherigen Werte sind gleich geblieben.
- Komma statt Punkt in der PPD wird erkannt: Die Maße werden trotzdem übernommen, gemeldet wird es auch.
- Fehlt der bedruckbare Bereich, nimmt Passermark die Ränder, die der Drucker bei seinen anderen Formaten hat. Bei randlosen Formaten ist es das ganze Blatt.
- Die Warnung im Druckdialog nennt die Ursache und gibt die fertigen PPD-Zeilen mit richtigen pt-Werten aus.
- IPP- und Windows-Drucker greifen auf Name und Tabelle zurück, wenn der Treiber nichts oder 0 × 0 meldet.
- `caps --json` zeigt neu, woher jedes Format seine Maße hat, und eventuelle PPD-Fehler.

### Als PDF speichern
- Bei „Wie Dokument“ kommt keine falsche A4-Warnung mehr. SRA4 und SRA2 sind jetzt auch in der Liste.

### Lesbare JSONs
- Presets speichern nur noch, was vom Standard abweicht. Ein Broschüren-Preset ist dann z. B. nur `{"handling": "booklet", "sheet": "A3"}`.
- Im Menü der Preset-Zeile gibt es den Haken „Alle Einstellungen speichern“. Der gilt für alle Dialoge.
- `passermark-cli tidy datei.json` kürzt bestehende Presets und Abläufe. Mit `--print` zeigt es nur an, mit `--full` schreibt es ein Preset wieder komplett.
- Zwei Sachen kürzt tidy bewusst nicht: Ablauf-Schritte mit `preset` (ein Standardwert dort kann das Preset absichtlich überschreiben) und `layout` im Druckschritt (fehlende Werte dort kommen aus der Admin-Einstellung, nicht vom Programmstandard).

## 1.15.0
### Drop-Ordner: passermark-cli serve (Watcher)
- `passermark-cli serve` Ã¼berwacht Ordner und schickt jede Datei durch den zugeordneten Ablauf. Die Zuordnung steht in `watch.json` (genommen wird `--config`, sonst die eigene, sonst die fÃ¼r alle).
- Nach der Verarbeitung landet das Ergebnis in `output/`, das Original in `processed/`; bei Fehlern kommt das Original nach `failed/` mit einer `.log` daneben. Jede dieser Einstellungen geht auch auf `""` (kein Ergebnis behalten bzw. Original lÃ¶schen). Ein Ablauf, der nur druckt, behÃ¤lt standardmÃ¤Ãig kein Ergebnis.
- ZuverlÃ¤ssig: Eine Datei wird erst genommen, wenn sie `settle` Sekunden unverÃ¤ndert ist; halb kopierte Dateien (`.part`, `.tmp`) werden nie angefasst. Jede Datei wird zuerst nach `.passermark/` verschoben â zwei Watcher auf demselben Ordner verarbeiten nie dieselbe Datei doppelt, und nach einem Absturz kommen liegengebliebene Dateien beim nÃ¤chsten Start zurÃ¼ck. Ergebnisse landen nie zurÃ¼ck im Eingangsordner und werden nie Ã¼berschrieben (`-1`, `-2` â¦).
- Optionen: `--check`, `--once` (Fehlercode 1, wenn eine Datei fehlschlÃ¤gt), `--json`, `--quiet`, `--log`.
- Als Dienst: `linux/passermark-watch.service` mit einem eigenen Benutzer ohne Rechte (die Schritte stehen in der Datei); fÃ¼r Windows `windows/watch-task.ps1`, das eine Aufgabe beim Systemstart anlegt.

### Ablauf-Ordner: ablaeufe â workflows
- Der Ordner heiÃt jetzt `workflows`; ein alter `ablaeufe`-Ordner wird beim ersten Aufruf automatisch umbenannt. Fehlen dafÃ¼r die Rechte, liest Passermark den alten Ordner einfach weiter.
- **Gemeinsame Ablauf-Ordner:** Neu in der Verwaltung unter Allgemein â âWeitere Ablauf-Ordnerâ, z. B. eine Netzwerkfreigabe. Reihenfolge: eigene â gemeinsame â fÃ¼r alle; der erste Ablauf mit dem Namen gilt. Wer dort AblÃ¤ufe ablegen darf, regeln die Ordnerrechte (z. B. eine Gruppe mit Schreibrecht) â Admin-Rechte braucht dafÃ¼r niemand. `workflows --dirs` zeigt, aus welchem Ordner (user / shared / system) ein Ablauf kommt.

### Druckschritt
- **`"paper": "auto"`:** Bei Seitenhandhabung GrÃ¶Ãe nimmt der Druckschritt das Papier passend zur Seite, bei BroschÃ¼re fÃ¼r zwei Seiten nebeneinander (A5 â A4). Gibt es beim Drucker kein passendes Papier, kommt ein Fehler mit den vorhandenen Formaten; bei Nutzen oder Poster einen klaren Fehler â dort muss das Papier angegeben werden. Leeres `paper` funktioniert wie bisher (Standardpapier).

### Nebenbei behoben
- Seitenangaben auÃerhalb des Dokuments (z. B. `pages: "1-2"` bei einer einseitigen PDF) liefern jetzt âSeite 2 gibt es nicht â¦â statt âlist index out of rangeâ.

## 1.14.2
### Datei â Eigenschaften â¦ (Strg+D)
- FÃ¼nf Reiter:
  - **Datei:** Name, Ordner (âOrdner Ã¶ffnenâ, âPfad kopierenâ), GrÃ¶Ãe, geÃ¤ndert am, Status (gespeichert / geÃ¤ndert / nur im Arbeitsspeicher / Zwischenspeicher). Bei zusammengefÃ¼hrten, umgewandelten oder aus Bildern erzeugten Dokumenten steht âEntstanden aus:â mit den Quelldateien, bei Ergebnissen âErgebnis aus â¦â.
  - **Dokument:** PDF-Version, Titel, Autor, Thema, StichwÃ¶rter, Erstellt mit / PDF erzeugt mit, Erstellt am / GeÃ¤ndert am; VerschlÃ¼sselung mit Verfahren, erlaubten und gesperrten Rechten; Ausgabeprofil (Output Intent), Ebenen, Formularfelder, Kommentare und Stempel, Lesezeichen, AnhÃ¤nge, JavaScript, Schnelle Webanzeige.
  - **Seiten:** Tabelle je Seite mit Format, Ausrichtung, Drehung, Endformat und Anschnitt, darÃ¼ber eine Ãbersicht der Formate.
  - **Schriften:** Name, Art, eingebettet, Teilmenge, Seiten. Nicht eingebettete Schriften sind gelb hervorgehoben.
  - **PrÃ¼fung:** Fehler, Warnungen und Hinweise mit Seiten.
- Das Fenster ist sofort da; die Dokumentangaben werden im Analyse-Prozess gelesen und kommen kurz danach â auch bei groÃen Dateien hÃ¤ngt das Programm nicht. Bei geÃ¤nderten Dokumenten wird der aktuelle Stand gezeigt, nicht die Datei auf der Platte. Die Angaben sind dieselben wie bei `passermark-cli inspect`, das jetzt ebenfalls die zusÃ¤tzlichen Dokumentangaben liefert.

### Anleitung Kommandozeile (Hilfe, Deutsch und Englisch)
- Neue Abschnitte zu AblÃ¤ufen (mit Ablauf-Ordnern), zum Drucken (mit Finishern), zu `inspect` und zur Schnittstelle fÃ¼r andere Programme; ergÃ¤nzt sind auÃerdem die BefehlsÃ¼bersicht, neue Tipps und das Ausblick-Kapitel (Watcher, geplant fÃ¼r 1.15).
- Alle Beispiele laufen als Tests wirklich mit, inklusive der gezeigten Ablauf-JSONs; nur das Druck-Beispiel wird geprÃ¼ft und nicht ausgefÃ¼hrt, wenn kein Drucker eingerichtet ist.
- Die Anleitung gibt es derzeit auf Deutsch und Englisch; Ungarisch, Spanisch und FranzÃ¶sisch zeigen wie bisher die englische.

## 1.14.1
### Kommandozeile: Drucken
- **Schritt `print` im Ablauf:** Drucker, Papier, Fach, Medium, Duplex (`none` | `long` | `short`), Farbe (`color` | `gray`), Kopien, Sortierung und Seitenbereich â dazu alle Optionen des Druckdialogs (Nutzen, BroschÃ¼re, Poster usw.), das Admin-Farbprofil des Druckers und rohe Treiberoptionen direkt. `dry_run` schickt nichts und zeigt nur, was gesendet wÃ¼rde.
- Gedruckt wird auf demselben Weg wie aus dem Druckdialog: mit automatischer Fachwahl und den Windows-Herstellereinstellungen.
- Werte gehen als Treiberwert, als Anzeigename oder als eindeutiges StÃ¼ck davon; passt etwas nicht, nennt die Fehlermeldung alle mÃ¶glichen Werte.
- Das PDF bleibt nach dem Druck unverÃ¤ndert â danach weiterarbeiten, speichern oder mit anderen Einstellungen nochmal drucken. Ohne `output` wird nur gedruckt.
- **Neue Befehle:** `printers` (Drucker mit Status und Standarddrucker) und `caps <drucker>` (alle Treiberoptionen mit Auswahl, Papierformate und welche Option fÃ¼r Papier, Fach, Medium, Duplex, Farbe, Ausgabefach und die Finisher â Heften, Lochen, Falzen, Sattel, Schneiden, Versatz â zustÃ¤ndig ist).
- Intern: Die Drucksitzung liegt jetzt ohne Qt in `pdfdruck/session.py`, damit die CLI sie nutzen kann; das Programm bekommt sie wie bisher Ã¼ber `gui/common.py`.
- Testpaket: Die AblÃ¤ufe 30 und 31 sind ProbelÃ¤ufe (`dry_run`) und laufen bei âalle testenâ mit; im eigenen Ordner `ablaeufe-echt-drucken/` liegen zwei AblÃ¤ufe, die wirklich drucken (laufen nicht automatisch mit).

## 1.14.0
### Kommandozeile: AblÃ¤ufe
- **Mehrere AuftrÃ¤ge hintereinander als versionierte JSON-Datei** (âAblauf", Formatversion 1): Die Schritte laufen hintereinander, jeder arbeitet mit dem Ergebnis des vorigen. Die Ausgabe wird nur geschrieben, wenn alles geklappt hat.
- **Neue Befehle:** `run` (Ablauf ausfÃ¼hren, auch mit mehreren Eingaben â Bilder und Office-Dateien werden vorher umgewandelt und mit den PDFs zusammengefÃ¼hrt), `check` (prÃ¼fen ohne AusfÃ¼hren, alle Fehler auf einmal), `schema` (JSON-Schema der Ablauf-Datei oder eines Auftrags), `inspect` (Dokument-Informationen: Seiten, Formate, Endformat/Anschnitt, PrÃ¼fbefunde â mit `--check`), `version --json` (Version, API- und Formatversion, verfÃ¼gbare AuftrÃ¤ge).
- **Variablen** im Ausgabepfad: `${â¦}` von `--var`; eingebaut sind `${input}`, `${dir}`, `${stem}`, `${date}` und `${workflow_dir}`.
- **Tippfehler sind Fehler:** unbekannte Einstellungen und falsche Typen werden gemeldet, nichts fÃ¤llt still auf einen Standardwert zurÃ¼ck.
- **FÃ¼r Zusatzprogramme:** feste JSON-Ereignisse (`start` â `step` â `progress` â `step_done` â `done`) und feste Fehlercodes (`usage`, `not_found`, `invalid`, `failed`, `cancelled`) mit Schritt und Auftrag; API- und Formatversion stehen in der Ausgabe von `version --json`. Die Schnittstelle ist in [docs/cli-api.md](docs/cli-api.md) beschrieben (Englisch, mit deutscher Kurzfassung) â der verbindliche Vertrag fÃ¼r Zusatzprogramme, aus allen READMEs verlinkt.

## 1.13.2
### Druckdialog: Vorschau im Hintergrund
- **Vorschau ohne Warten:** Der Bogen wird jetzt im Render-Prozess montiert und gezeichnet â das Fenster wartet nicht mehr darauf. Mit einer groÃen Datei braucht die Vorschau im Hauptfenster 0,001 s statt vorher bis zu 6 s HÃ¤nger. Wird etwas geÃ¤ndert, wÃ¤hrend noch gerechnet wird, wird nur der neueste Stand fertig gezeichnet.
- Die Wartezeit bleibt: Fertig ist die Vorschau trotzdem erst nach 2â5 s, weil die Seite selbst so lange zum Zeichnen braucht. Das Fenster bleibt dabei aber bedienbar.
- **Mehrfach-Nutzen (z. B. Step & Repeat):** Die Seite wird nur einmal gerendert statt fÃ¼r jeden Nutzen neu â etwa doppelt so schnell. Das Bild weicht minimal ab, weil es ein Rasterbild ist; nur bei sehr feinen Mustern sieht man leichtes MoirÃ©. Gedruckt wird weiterhin aus dem Original.
- **Ohne Mehrfach-Nutzen** ist die Vorschau pixelgleich zu vorher (verglichen fÃ¼r Einzelseiten, 9 auf 1, BroschÃ¼re, DruckbÃ¶gen und Duplex).
- **Endformat/Anschnitt** kommt jetzt aus den Seitendaten, ohne die Seiten zu laden â die Werte sind gleich wie vorher.
- **BogenÃ¼bersicht** wird ebenfalls im Hintergrund gerechnet.
- **Noch im Hauptfenster:** âBroschÃ¼re als DruckbÃ¶genâ braucht beim Umstellen noch ca. 0,9 s; das Erzeugen der DruckbÃ¶gen ist nicht ausgelagert.
- **Seitenansicht:** GroÃe Seitenbilder werden beim Zoomen sofort grob skaliert, das saubere Bild kommt im Hintergrund nach. Die Obergrenze fÃ¼rs Seitenbild bleibt unverÃ¤ndert bei 16 Megapixeln.

### ZusammenfÃ¼hren unter Windows
- **Ein Fenster:** Kommen mehrere Dateien gleichzeitig an, landen alle im selben Fenster. Mit 12 gleichzeitig gestarteten Aufrufen getestet: 1 Fenster, 12 Dateien, nach Namen sortiert.
- **Neue KnÃ¶pfe:** âOrdner hinzufÃ¼gen â¦â, Nach oben/unten und âNach Name sortierenâ. Dateien lassen auch hineinziehen; angezeigt wird, wie viele drin sind.
- **FÃ¼r viele PlÃ¤ne:** Am besten âSenden an â Passermark â zusammenfÃ¼hrenâ â das Ã¼bergibt alle Dateien auf einmal und wird beim ersten Start einmalig angelegt. Alternativ im Fenster gleich den ganzen Ordner hinzufÃ¼gen.
- **Seitenleiste:** Markierte Seiten lassen sich verschieben. Der gelbe Balken zeigt, wo sie landen; am Rand scrollt die Leiste automatisch weiter.

## 1.13.1
### Geschwindigkeits-Fix
- Kleinere Geschwindigkeitsverbesserungen in der neuen Ansicht (Rendering).

## 1.13.0
### Schnellere Ansicht (Render-Ãberarbeitung)
- **Rendern im eigenen Prozess:** Seiten werden von einem Hintergrundprozess gerendert (`passermark-cli render-server`); die OberflÃ¤che wartet nie mehr darauf. Es ist immer nur eine Anfrage unterwegs â beim schnellen BlÃ¤ttern stauen sich keine veralteten. StÃ¼rzt der Prozess ab, startet er neu; geht er gar nicht (oder ist das PDF passwortgeschÃ¼tzt), rendert die Ansicht wie frÃ¼her im Programm selbst.
- **Ein Seitenbild je Seite:** jede Seite wird einmal in etwa doppelter AnsichtsgrÃ¶Ãe gerendert; Zoomstufen bis dahin und die Miniaturen werden daraus nur skaliert. Die Bilder einer Seite werden also nur einmal entpackt â statt je Zoomstufe und je Miniatur.
- **Starkes Zoomen rendert nur den sichtbaren Ausschnitt,** pixelgenau auch bei gedrehter Ansicht. Bei 400 % ist die Seite kurz unscharf, dann scharf (vorher hochgezogen und unscharf).
- **Ãber dieselbe Datei speichern geht jetzt auch unter Windows:** die Datei wird in den Speicher gelesen und bleibt frei.
- **Bearbeiten:** beim Ziehen lÃ¤uft das Objekt halbdurchsichtig mit; nach dem Ãbernehmen bleiben die alten Bilder als Platzhalter stehen und werden im Hintergrund erneuert, die bearbeitete Seite zuerst. Vorher wurde alles weiÃ und alle Miniaturen wurden im Hauptfenster neu gerendert.
- **Die automatische PrÃ¼fung liest unverÃ¤nderte Dateien direkt** â beim Ãffnen entfÃ¤llt das Neuspeichern im Hauptfenster.
- Fehler eingrenzen: mit `PASSERMARK_RENDER=local` lÃ¤uft alles wie vorher â damit lÃ¤sst sich schnell klÃ¤ren, ob es am neuen Render-Prozess liegt.
- Bekanntes Restproblem: das Loslassen beim Bearbeiten dauert bei schweren Seiten noch ca. 1 s (die SicherheitsprÃ¼fung vergleicht die Seite vorher und nachher). Ein Element, das auf mehreren Seiten verwendet wird, kann sich durch eine Ãnderung Ã¼berall Ã¤ndern â darum werden nach dem Bearbeiten alle Seiten im Hintergrund neu gerendert, die bearbeitete zuerst.

## 1.12.6
### VorabprÃ¼fung (Preflight)
- Kleine Anpassungen an âDateigrÃ¶Ãe reduzierenâ (`shrink`) und den Preflight-PrÃ¼fungen; Ãbersetzungen vervollstÃ¤ndigt; CLI-Handbuch (DE/EN) aktualisiert.

## 1.12.5
### Lizenzen
- Installer und AppImage enthalten jetzt alle Drittanbieter-Lizenzhinweise (Python-Pakete, Qt LGPL-3.0, Ghostscript AGPL-3.0 mit Quellcode-Verweis, mitgelieferte Systembibliotheken), einsehbar Ã¼ber den neuen MenÃ¼eintrag Hilfe â Lizenzen.
- READMEs: neuer Abschnitt zu Drittanbieter-Lizenzen, Quellcode auf Anfrage erhÃ¤ltlich.
### Dokumentation
- Das CLI-Handbuch (DE/EN) wurde um `shrink` und `flatten_softmask` ergÃ¤nzt.

## 1.12.4
### DateigrÃ¶Ãe reduzieren (neu)
- Erreichbar Ã¼ber den Reiter âDateigrÃ¶Ãeâ oder Dokument â âDateigrÃ¶Ãe reduzieren â¦â, auch bei Dateien, die nicht als zu groÃ markiert sind.
- Jede MaÃnahme ist einzeln ein- und ausschaltbar:
  - **Verlustfrei, standardmÃ¤Ãig aktiv:** Neuschreiben (entfernt alte gespeicherte Versionen), ungenutzte Ressourcen entfernen, Duplikate zusammenfÃ¼hren (Schriften, Bilder, ICC-Profile), Bearbeitungsdaten und Vorschaubilder entfernen, Bilder verlustfrei neu komprimieren (entfernt auch ZIP um JPEG, wenn kleiner).
  - **StandardmÃ¤Ãig deaktiviert:** 16 â 8 Bit, AnhÃ¤nge entfernen, Inhalt verborgener Ebenen entfernen.
  - **Optionales Herunterrechnen:** auf 300/240/150/100 dpi mit Schwellwert und JPEG-QualitÃ¤t, gemessen an der grÃ¶Ãten Platzierung. Soft Masks werden mitskaliert.
- Das Ergebnis Ã¶ffnet sich in einem neuen Fenster, das Original bleibt unverÃ¤ndert. Ist das Ergebnis nicht kleiner, bleibt die Datei, wie sie ist.
- CLI: `passermark-cli shrink in.pdf out.pdf [--set downsample=true --set target_dpi=150 â¦]`
- Beispiel: Eine 34-MB-Datei mit 90-mal eingebettetem, identischem CMYK-Profil schrumpfte auf 0,5 MB, pixelidentisch.

## 1.12.3
### VorabprÃ¼fung (Preflight)
- **Neuer Reiter âDateigrÃ¶Ãeâ:** zeigt, wohin die Bytes gehen: Bilder, Schriften, Farbprofile, Illustrator-/Photoshop-Bearbeitungsdaten, Vorschaubilder, AnhÃ¤nge, Seiteninhalt.
  - Listet auÃerdem alte gespeicherte Versionen, Duplikate und die grÃ¶Ãten Bilder mit ihrer effektiven dpi-Zahl auf.
  - Warnt vor sehr groÃen Dateien (mehr als 20 MB je A4-FlÃ¤che) und groÃen Duplikaten.

## 1.12.2
### VorabprÃ¼fung (Preflight)
- **Transparente FarbverlÃ¤ufe (Soft Mask im Muster):** werden erkannt und sind reparierbar. Manche RIPs/Plotter drucken sie als schwarze FlÃ¤che, die die darunterliegenden Bilder verdeckt. Die neue Reparatur âTransparente FarbverlÃ¤ufe als Bilder umwandeln (300 dpi)â rendert nur die betroffenen VerlÃ¤ufe, zusammen mit dem darunter Liegenden, als deckendes Bild. Text und Vektoren darÃ¼ber bleiben erhalten. Kein Ghostscript nÃ¶tig.
- **HDR-Fotos (Gain Map):** ein Handy-HDR-Foto, das mit beiden Bildern geÃ¶ffnet wurde, wird jetzt von der PrÃ¼fung erkannt. Reparatur: âHDR-Hilfsseiten entfernen â¦â, mit wÃ¤hlbarer GrÃ¶Ãe und optionaler Gain-Map-ZusammenfÃ¼hrung.
- **Neuer Reiter âBilder & Farbenâ:**
  - Farbraum je Bild und Seite (RGB, CMYK, Grau, Schmuckfarben), inklusive exaktem ICC-Profilnamen und Ausgabe-Farbraum (Output Intent).
  - Effektive AuflÃ¶sung je Platzierung, auch bei mehrfach verwendeten Bildern oder Bildern in Formularen (XObjects).
  - Empfohlene MaximalgrÃ¶Ãe bei 300 und 150 dpi, plus maximale Skalierung je Seite.
  - Warnungen bei niedriger AuflÃ¶sung, Hinweise zu RGB-Inhalten und Schmuckfarben.

## 1.12.1
- **Bearbeiten: mehrere Objekte und Zeilen auf einmal.** âSkalieren / Verschieben â¦â, âObjekt
  lÃ¶schenâ, âÃbernehmenâ (Schrift und GrÃ¶Ãe) und âZeile lÃ¶schenâ wirken jetzt auf alle gewÃ¤hlten
  Objekte bzw. Zeilen, nicht mehr nur auf eine. Bei mehreren gewÃ¤hlten Zeilen ist das Textfeld
  gesperrt â Text Ã¤ndern geht nur bei einer Zeile
- **Bearbeiten: Farbe Ã¤ndern.** Neuer Knopf âFarbe â¦â fÃ¼r Textzeilen und Vektorobjekte, wahlweise
  CMYK (Standard, fÃ¼r den Druck) oder RGB; bei Vektoren FlÃ¤che und Kontur getrennt wÃ¤hlbar.
  Schwarz 0/0/0/100 bleibt reines Schwarz. Die Farbe wird direkt im Seiteninhalt gesetzt â alles
  auÃerhalb der Auswahl bleibt unverÃ¤ndert, auch Objekte, die ihre Farbe nur Ã¼bernommen haben
- **Bearbeiten: Ãbersicht.** Die Reiter zeigen die Anzahl (âText (12)â, âObjekte (40)â); im Reiter
  âObjekteâ lÃ¤sst sich nach Vektoren oder Bildern filtern, mit Anzahl je Art. Bei aktivem Filter
  wÃ¤hlt ein Klick auf die Seite nur diese Art
- **HDR-Fotos vom Handy (iPhone, Android) werden erkannt.** Solche JPGs enthalten neben dem Foto
  eine graue Helligkeitskarte fÃ¼r HDR-Bildschirme. Bisher wurde daraus eine zweite Seite in anderer
  GrÃ¶Ãe â am Plotter mit falschen Farben. Jetzt erscheint beim Ãffnen ein Hinweis; âReparierenâ
  ergibt eine Seite mit dem unverÃ¤nderten Foto, GrÃ¶Ãe wÃ¤hlbar (wie das Zusatzbild oder wie im Foto
  hinterlegt). Die Helligkeitskarte lÃ¤sst sich optional einrechnen. Ohne RÃ¼ckfrage (Kommandozeile,
  Direktdruck) wird automatisch repariert
- **Behoben: Kreistext-SchriftgrÃ¶Ãe.** Nach dem Ãndern zeigte die Liste weiter die alte GrÃ¶Ãe, jede
  weitere Ãnderung vergrÃ¶Ãerte erneut (24 â 36 â 54 pt). Jetzt wird die tatsÃ¤chliche GrÃ¶Ãe angezeigt;
  kurze BÃ¶gen mit wenigen Buchstaben werden ebenfalls als Pfadtext erkannt. âÃbernehmenâ ohne
  Ãnderung lÃ¤sst die Seite unangetastet
- **Behoben: Z-Ordnung.** âEins nach vornâ beim obersten Objekt meldete fÃ¤lschlich âStruktur der Seite
  nicht erkanntâ â jetzt bleibt einfach alles, wie es ist
- **Behoben: Text mit der Maus ziehen** brach bei manchen PDFs (z. B. aus Chrome) mit einer
  Fehlermeldung ab
- Ãbersetzungen fÃ¼r die Nutzen-Anordnung im Druckdialog ergÃ¤nzt (Englisch, Ungarisch, Spanisch,
  FranzÃ¶sisch)

## 1.11.3
- **VDP-Dialog aufgehÃ¼bscht.** Variable Daten bekam das gleiche Gesicht wie der Druckdialog: vier
  nummerierte, einklappbare Abschnitte (Felder, Daten, Nummerierung, Ausgabe) plus oben eine
  zugeklappte âAnleitungâ. Feld-ErklÃ¤rungen stehen jetzt als Tooltip am Feld und erscheinen nur
  mit dem neuen Schalter âHilfetexte anzeigenâ unter dem Feld. Der veraltete Ausgabe-Hinweis
  zeigt jetzt auf den Druckdialog (Nutzen, Reihenfolge âJe Nutzen die nÃ¤chste Seiteâ). Das
  CollapsibleSection-Widget liegt zentral in common.py (beide Dialoge nutzen es).
- **Druckdialog ohne Reiter.** Die Moduswahl oben (âWas soll gedruckt werden?") fÃ¼hrt nun in
  einer einzigen, durchlaufenden Spalte durch den ganzen Dialog: Preset, Modus, Modus-Panel,
  Skalierung (âWie aufs Blatt?"), Schnittmarken, Papier/Ausgabe, Finisher, Farbmanagement. Die
  frÃ¼here Reiter-Navigation ist weg.
- **Nutzen (Step & Repeat) ist ein eigener Modus.** âNutzen" steht im Drehkreuz neben EinzelblÃ¤tter,
  Mehrere pro Blatt, BroschÃ¼re und Poster â mit ErklÃ¤rtext wie die anderen Modi. Das alte HÃ¤kchen
  ersetzt der Modus-Knopf; das Nutzen-Panel erscheint dort, wo auch die anderen Modus-Panels
  liegen.
- **âWie aufs Blatt?"** Skalierung und Ausrichtung sind jetzt eine Gruppe: Einpassen/OriginalgrÃ¶Ãe/
  Verkleinern/Eigene, Drehung, automatisches Drehen, Zentrieren, RÃ¤nder. Die Skalierungswahl
  (Anpassen/TatsÃ¤chlich/â¦) ist in jedem Druckmodus sichtbar und wirksam: Anpassen = Modus-Standard,
  OriginalgrÃ¶Ãe/Verkleinern/Benutzerdefiniert Ã¼berschreiben die Modus-Skalierung â die Modus-Felder
  (Kachel-Skalierung, Nutzen-MaÃstab, Poster) bleiben daneben erhalten.
- **Spiegeln und Treiber einklappbar.** Beide Abschnitte bleiben mit deutlich sichtbarem Titel
  erhalten und lassen sich erst bei Bedarf aufklappen â alle Optionen unverÃ¤ndert.
- **BroschÃ¼re: âStandard" zuerst.** Die klassische Sattelheftung (âalle BÃ¶gen ineinander, einmal
  falzen") fÃ¼hrt die Bindeart-Liste jetzt unter dem klaren Namen âStandard" â der Spinner
  âBÃ¶gen je Lage" erscheint nur noch bei âGruppierte Lagen" und kann keine scheinbar
  wirkungslose Einstellung mehr nahelegen.
- **Einheitliche einklappbare Abschnitte.** Jeder Block der neuen Spalte â Preset, Moduswahl
  (âWas soll gedruckt werden?"), âWie aufs Blatt?", Schnittmarken, Papier/Ausgabe, Finisher,
  Farbmanagement, Spiegeln, Treiber â hat dieselbe einklappbare Ãberschrift in gleicher GrÃ¶Ãe.
  Die Modi-KnÃ¶pfe liegen untereinander, alle Beschriftungen bleiben lesbar; das Modus-Panel
  schrumpft auf den sichtbaren Modus (kein Leerraum mehr). Aus dem Nutzen-Modus lÃ¤sst sich
  jederzeit in jeden anderen Modus wechseln.
- **Ãbersetzungen:** 26 neue/nachgepflegte Meldungen je Sprache (EN/DE/ES/FR/HU); fehlende
  1.11.1-Strings in den Meldungskatalogen ES/FR/HU/EN wurden nachgepflegt. Alte Presets bleiben
  voll kompatibel (handling âsize"/âmultiple"/âsr" laden weiterhin).

## 1.11.2
- **Schritt 2: Nutzen erneut montieren.** Der fertig montierte Nutzen-Bogen (Schritt 1) wird ein zweites
  Mal auf ein frei wÃ¤hlbares Zielformat gesetzt (GerÃ¤teformate oder eigene MaÃe in mm) â zeilenweise,
  immer mittig, inhaltlich unverÃ¤ndert; das Ergebnis lÃ¤sst sich per Button als neues Dokument ausgeben
  (neuer Reiter), die Vorschau zeigt es wie bei Schritt 1 und der Dialog schlieÃt danach. Drehung und
  Ausrichtung aus Schritt 1 gelten auch fÃ¼r Schritt 2. Raster: 0 Ã 0 = automatisch (so oft wie mÃ¶glich).
- **Vorhandene Schnittmarken verwenden.** Bei Dokumenten mit Endformat (TrimBox) zeigen die AuÃenseiten
  des Nutzenblocks den echten Dokumentrand â vorhandene Schnittmarken bleiben sichtbar; eigene Marken
  bleiben wie gehabt per HÃ¤kchen zuschaltbar.
- **Raster exakt montieren.** Ein definiertes Raster (z. B. 3 Ã 3) bleibt in Schritt 1 und Schritt 2 immer
  exakt â passt es nicht aufs Blatt, wird symmetrisch am Rand beschnitten und gewarnt, nie abgebrochen.
- **Zielformat randlos geplant:** z. B. passen zwei A4-BÃ¶gen aus Schritt 1 sauber auf ein A3.
- Schritt-1-Druckpfad und Ausrichtung unverÃ¤ndert.

## 1.11.1
- **Sonderformate: nur noch âAls PDF speichernâ.** Selbst angelegte Formate werden nicht mehr an Drucker
  gesendet â Windows-Treiber und Spooler nehmen SondergrÃ¶Ãen oft nicht an (leere BlÃ¤tter, AbbrÃ¼che);
  bei âAls PDF speichernâ (â) bleiben sie voll nutzbar
- **Beschneiden: zwei neue Modi.** âKanten abschneidenâ: die Seite ohne Zielformat an allen vier Seiten
  in mm beschneiden; âWeiÃraum entfernenâ: erkennt den sichtbaren Inhalt (inkl. JPEG-Rauschen), das neue
  Seitenformat ergibt sich aus dem Inhaltsrahmen Â± Rand (auch negativ), der Inhalt bleibt 1:1 (nur verschoben)

## 1.11.0
- **Variable Daten â Fenster (Seitengruppen).** Bei Vorlagen mit mehreren Seiten gehÃ¶rt jedes Feld zu einem
  Fenster (z. B. âVorderseiten (Name), RÃ¼ckseiten (QR-Code)â); Fenster lassen sich anlegen, umbenennen und
  entfernen â ihre Felder wandern dann ins erste Fenster. Seitenauswahl je Fenster: alle Seiten, ungerade
  (Vorderseiten), gerade (RÃ¼ckseiten) oder Bereiche (â1,3-5 oder ungerade 1-50â); ohne eigene Auswahl gilt
  die Grundschicht âalle Seitenâ. Datensatz-Verteilung âBogen fÃ¼r Bogenâ (erst alle Seiten mit Datensatz 1)
  oder âSeite fÃ¼r Seiteâ (erst Seite 1 mit allen DatensÃ¤tzen); Anzeige â{0} DatensÃ¤tze â {1} Seitenâ und
  Warnung ââ {0} Seiten ohne Fenster!â
- **VDP-Vorschau:** Endformat grÃ¼n, Anschnitt rot; einstellbarer Innenrahmen (Hilfslinie) zwischen Endformat und Anschnitt
- **Seitenanzeige âaktuell / gesamtâ** in der Werkzeugleiste; Seitenzahl eintippen und Enter springt direkt zur Seite
- **Lineale, Messen und Endformat-Anzeige dauerhaft in der Haupt-Werkzeugleiste** â in jedem Arbeitsbereich,
  nicht mehr nur unter âAnzeigen & Druckenâ
- **Endformat und Anschnitt in der Hauptansicht:** innere Grenze (Endformat) grÃ¼n statt rot, Anschnitt als
  dezente rote Punktlinie statt roter VollflÃ¤che
- **Messen mit Einrasten:** Steuerung (Strg) gedrÃ¼ckt halten und das Fadenkreuz rastet magnetisch an Schnitt-
  und Innenlinien (Seitenrand, Endformat, Anschnitt) sowie an Bildkanten und Vektorlinien ein â nie an Text.
  Das Vorschau-Fadenkreuz bleibt an der Kante kleben, bis die Maus deutlich weiterzieht; Umschalt sperrt
  weiterhin waagrecht/senkrecht/45Â°

## 1.10.7
- **CutContour: Grundformen ohne Berechnung.** Neue Lage âAuf das Endformat (ohne Berechnung)â: Rechteck,
  abgerundetes Rechteck, Kreis â¦ werden direkt aufs Endformat (TrimBox, sonst die Seite) gelegt â kein Rendern,
  keine Motiv-Erkennung, keine Arbeitsprozesse, in Sekundenbruchteilen. Abstand, GrÃ¶Ãe, Versatz und Ziehen mit der
  Maus gelten wie bisher. Gerechnet wird nur noch bei âKonturâ oder wenn die Form ums Motiv bzw. je Objekt gelegt
  wird. Kommandozeile: `--set fit=trim`
- **Standard in CutContour:** Rechteck auf das Endformat (solange keine eigenen zuletzt verwendeten Einstellungen
  gespeichert sind)

## 1.10.6
- **Fix Windows: CutContour blieb bei 0 % hÃ¤ngen** (seit 1.10.5). Die Umstellung der Kommandozeilen-Ausgabe auf
  UTF-8 ist wieder entfernt; der Fix fÃ¼r âSeiten teilenâ bleibt (Fortschrittsmeldungen als reines ASCII)
- CutContour: kein Fehler mehr, wenn beim SchlieÃen des Fensters noch eine Vorschau-Berechnung nachkommt
  (âexpected LP_struct_fpdf_document_t â¦ NoneTypeâ)

## 1.10.5
- **Fix Windows:** âSeiten teilenâ (und jeder Auftrag, dessen Meldung Zeichen wie âââ enthÃ¤lt) brach mit
  `UnicodeEncodeError â¦ cp1252` ab. Die Kommandozeile stellt ihre Ausgabe jetzt selbst auf UTF-8 um, die
  Fortschrittsmeldungen an die OberflÃ¤che sind reines ASCII
- `SECURITY.md`, `CONTRIBUTING.md` und GitHub-Vorlagen fÃ¼r Fehlermeldungen und VorschlÃ¤ge im Paket

## 1.10.4
- README zweisprachig: `README.md` (Englisch) und `README.de.md` (Deutsch), auf aktuellem Stand (Seiten teilen,
  Variable Daten, Daten erfassen, alle AuftrÃ¤ge der Kommandozeile) und mit einem Hinweis zum Projektstatus
- Beispiel-Konfiguration `data/defaults.example.json` mit neutralen Druckernamen

## 1.10.3
- **Seiten teilen per Rechtsklick:** Seiten in der Seitenleiste markieren â Rechtsklick â **Teilen** â
  âSenkrecht halbierenâ / âWaagrecht halbierenâ â sofort, nur die markierten Seiten, keine Vergleichsseite nÃ¶tig.
  âRaster / weitere Optionen â¦â Ã¶ffnet den Dialog mit der Auswahl voreingestellt

## 1.10.2
- **Variable Daten â Vorder- und RÃ¼ckseite:** neu âSeiten je Datensatzâ (unter 2.): 2 = Seite 1+2 â Datensatz 1,
  3+4 â Datensatz 2 â¦ â egal ob die Vorlage 2 Seiten hat oder schon alle Karten (z. B. 200 Seiten fÃ¼r 100
  Visitenkarten). Felder âNur auf diesen Seitenâ kennen jetzt **ungerade** und **gerade**, auch kombiniert mit
  Bereichen (âungerade 1-50â). Beispiel 7: Visitenkarte mit Name vorne und QR-Visitenkarte hinten
- **Weitere Variablen:** {{datum}}, {{zeit}}, {{jahr}}, {{monat}}, {{tag}}, {{wochentag}}, {{kw}}, {{datum_iso}},
  {{datum:FORMAT}}, {{seite}}, {{seiten}}, {{vorlagenseite}}, {{datensatz}}, {{datensaetze}}, {{datei}},
  {{zufall}}, {{zufall:N}}, {{code:N}}, {{uuid}}. Knopf **?** neben dem Inhalt zeigt alle mit Beispielwert,
  Doppelklick fÃ¼gt ein. CSV-Spalten gleichen Namens gehen vor
- Doppelklick auf eine Spalte **ersetzt** ein unverÃ¤ndertes {{nr}} statt es davor stehen zu lassen
- **Seiten teilen** (Seiten â Seiten teilen â¦, Arbeitsbereich Bearbeiten): senkrecht/waagrecht halbieren oder
  Raster, alle/diese/ausgewÃ¤hlte Seiten oder Bereich, nur Doppelseiten, Reihenfolge rechtsâlinks; mit Vorschau der
  Schnittlinien. **Doppelseiten teilen** mit einem Klick fÃ¼r falsch exportierte BroschÃ¼ren. Verlustfrei (Inhalt wird
  nicht kopiert oder gerastert), gedrehte Seiten so, wie man sie sieht; mit Endformat wird darin geteilt und der
  Anschnitt bleibt auÃen. Kommandozeile: Auftrag `split`
- **Seitenleiste:** die Miniaturen drehen mit âAnsicht links/rechts drehenâ mit
- **Behoben: Ãffnen von auÃen landete in einem gesperrten Fenster** (Windows, Rechtsklick/Doppelklick, wÃ¤hrend
  in einem Fenster ein Werkzeug offen ist) â jetzt eigenes Fenster. Ursache: Ãffnen im leeren Startfenster lieÃ
  einen unsichtbaren leeren Reiter zurÃ¼ck; das leere Fenster wird jetzt selbst verwendet. Ergebnisse aus einem
  gesperrten Fenster Ã¶ffnen sich ebenfalls in einem eigenen Fenster

## 1.10.1
- **Eigene CSV mit anderen Spaltennamen direkt verwenden:** Variable Daten â CSV Ã¶ffnen erkennt, wozu die Tabelle
  passt (âDie Tabelle passt zu: QR â Visitenkarteâ), **Passendes Feld anlegen** legt den QR-Code mit dieser Art an.
  Die Spalten werden automatisch zugeordnet â auch englische, ungarische, spanische, franzÃ¶sische Namen und die
  Kopfzeilen der Kontakt-Exporte von **Outlook, Google und Thunderbird**. Die CSV bleibt unverÃ¤ndert
- **Spalten zuordnen â¦** beim QR-Feld mit Art: je Angabe die Spalte wÃ¤hlen, âleer lassenâ oder automatisch; mit
  Vorschau des fertigen Inhalts. Unter der Art steht, was woher kommt und was fehlt. Die Zuordnung wird im Preset
  gespeichert (`qr_map`) und gilt auch auf der Kommandozeile
- Daten erfassen: eine fremd benannte CSV bekommt keine doppelten Spalten mehr; die Kopfzeile zeigt die Zuordnung
  (âFirst Name â Vornameâ). `datencheck` erkennt fremde Spaltennamen ebenso
- Beispielordner: `kontakte-outlook.csv` (so sieht ein Outlook-Export aus); Anleitung um âEigene CSV mit anderen
  Spaltennamenâ ergÃ¤nzt

## 1.10.0
- **Daten erfassen** (Arbeitsbereich Variable Daten, MenÃ¼ Dokument-Manipulation, oder im Dialog Variable Daten
  unter 2.): die Datentabelle direkt in Passermark anlegen. Je Art die passenden Spalten â **QR-Visitenkarte
  (vCard), WLAN-Zugang, E-Mail, Webadresse, Anruf, SMS, Termin, Standort**, freier QR-Text, **Code 128**,
  **EAN-13**, Text mit eigenen Spalten. Jede Zeile wird sofort geprÃ¼ft (Pflichtangaben, EAN-PrÃ¼fziffer, Umlaute im
  Code 128, Datum â¦), rechts der fertige Code der gewÃ¤hlten Zeile. EinfÃ¼gen aus Excel mit Strg+V, Zeilen
  duplizieren, Spalte mit Nummernreihe fÃ¼llen (legt auch die Zeilen an), eigene Spalten. Speichern als CSV
  (UTF-8 mit BOM, Semikolon â Excel liest Umlaute richtig)
- **âIn Variable Daten verwendenâ** Ã¼bernimmt die Tabelle als Datenquelle und legt das passende Feld an
- **QR-Feld âArt des QR-Codesâ:** Inhalt wie eingegeben oder aus den Tabellenspalten zusammengesetzt (vCard,
  WLAN, mailto, tel, SMS, Termin, geo). Die CSV bleibt lesbar; den Code-Inhalt baut Passermark beim Erzeugen
- **Ruhezone:** QR-Code und Code 128 haben jetzt einen weiÃen Rand im Feld (abschaltbar). Ohne ihn waren Codes
  nahe an anderem Inhalt schlecht lesbar. *Bestehende Presets: der QR-Code wird dadurch etwas kleiner im Feld*
- **EAN-13 mit 13 Ziffern und falscher PrÃ¼fziffer ist jetzt ein Fehler** (mit der richtigen Nummer in der
  Meldung) â vorher wurde die letzte Ziffer still ersetzt
- Kommandozeile: `datenarten`, `datenvorlage <art> [datei.csv]`, `datencheck <datei.csv> [art]` (RÃ¼ckgabe 1 bei
  Problemen); im Preset `qr_type` je QR-Feld
- Beispiele 5 (Visitenkarte aus Kontaktliste) und 6 (WLAN-Zugang); Anleitung âVariable Datenâ mit neuem
  Abschnitt âDaten erfassenâ, CLI-Anleitung ergÃ¤nzt
- Tests lesen die erzeugten Codes jetzt wirklich zurÃ¼ck: QR und EAN-13 mit OpenCV (wenn installiert), Code 128
  mit eigenem Leser samt PrÃ¼fsumme
- Behoben: Variable Daten nahm ohne Auswahl der Verteilung âje Datensatz das ganze Dokumentâ statt âjede Seite
  der nÃ¤chste Datensatzâ

## 1.9.5
- **Beispiele fÃ¼r Variable Daten im Programm:** Vorlage, CSV, 4 Presets (QR mit Nummer, QR aus CSV, Code 128,
  EAN-13) und fertige Ergebnis-PDFs liegen im Programmpaket. *Hilfe â Beispiele fÃ¼r Variable Daten holen â¦* (auch im
  Arbeitsbereich Variable Daten) kopiert sie nach `~/Passermark-Beispiele/vdp`, trÃ¤gt die Presets âBeispiel 1â bis
  âBeispiel 4â mit vollem CSV-Pfad ein und Ã¶ffnet die Vorlage
- **Neue Anleitung âVariable Datenâ (PDF)** fÃ¼r OberflÃ¤che und Kommandozeile, mit allen vier Beispielen Schritt fÃ¼r
  Schritt: *Hilfe â Variable Daten â Anleitung (PDF)*
- Kommandozeile: `passermark-cli beispiele [ordner]`; ein relativer `csv_path` im Preset wird auch neben der
  Preset-Datei gesucht
- Anleitung Kommandozeile: VDP-Texte auf den aktuellen Stand (jede Seite der nÃ¤chste Datensatz, Arbeitsbereich)
- Windows-/Linux-Build: der ganze Ordner `pdfdruck/docs` wird mitgeliefert

## 1.9.4
- **Behoben: Code 128 â Klartextzeile verzerrt.** Die lesbare Zeile unter dem Strichcode wurde mit den Strichen
  auf die FeldgrÃ¶Ãe gestreckt; jetzt steht sie in der eingestellten SchriftgrÃ¶Ãe darunter
- Beispielpaket âpassermark-vdp-beispieleâ: Vorlage, CSV, Presets und fertige PDFs fÃ¼r QR-Code, Code 128 und EAN-13

## 1.9.3
- **Behoben: Variable Daten setzten auf jede Seite dieselben Werte** (Nummer 1, gleicher Name, {{i}} = 1) â ein
  Datensatz galt immer fÃ¼r eine Kopie des *ganzen* Dokuments. Neu und Standard: **jede Seite bekommt den nÃ¤chsten
  Datensatz** (Seite 1 â Datensatz 1, Seite 2 â 2 â¦; bei einseitiger Vorlage je Datensatz eine Seite). Die
  bisherige Verteilung gibt es weiter als âJe Datensatz eine Kopie des ganzen Dokumentsâ (z. B. Vorder- und
  RÃ¼ckseite einer Karte). Die Wahl steht jetzt als erste Frage unter â2. Woher kommen die Daten?â
- Ohne CSV ist die Anzahl am Anfang die Seitenzahl des Dokuments; Seite und Datensatz in der Vorschau sind
  gekoppelt (Seite 3 zeigt Datensatz 3)

## 1.9.2
- **Variable Daten verstÃ¤ndlicher:** jede Einstellung mit Ãberschrift und kurzer ErklÃ¤rung darÃ¼ber, Gruppen in
  der Reihenfolge der Arbeit (1. Felder, 2. Daten, 3. Nummerierung, 4. Ausgabe), Kurzanleitung oben; Lage/GrÃ¶Ãe,
  ZÃ¤hlen mit beschrifteten Einzelfeldern (links, oben, Breite, HÃ¶he â erste Nummer, Schrittweite, Stellen);
  Anzeige, wo ein ZÃ¤hler zum WeiterzÃ¤hlen gerade steht; CSV âEntfernenâ
- **Alles zurÃ¼cksetzen** (Knopf oben): ein Textfeld mit der Nummer, keine CSV, Nummerierung ab 1
- Variable Daten merken sich die letzten Einstellungen nur noch bis zum Programmende â nach einem Neustart
  beginnt der Dialog frisch. Dauerhaft behalten: als Preset speichern
- Neues EAN-13-Feld startet mit einer gÃ¼ltigen Beispielnummer statt mit {{nr}}

## 1.9.1
- **Fenster mit vielen Optionen werden nicht mehr abgeschnitten:** Variable Daten, CutContour, Objekte trennen und
  der Druckdialog haben zwischen Vorschau und Einstellungen einen verschiebbaren Teiler; der Einstellungsbereich
  scrollt senkrecht und â wenn er schmaler als sein Inhalt ist â auch waagrecht. Dasselbe in CMYK/Beschneiden und
  im Admin-Dialog. Dialoge werden nie grÃ¶Ãer als der Bildschirm geÃ¶ffnet
- Variable Daten: Knopf âCSV Ã¶ffnen â¦â (war bei schmalem Fenster abgeschnitten â sichtbar blieb nur der
  Speichern-Knopf des Code-Protokolls, jetzt âSpeichern unterâ¦â); Enter in einem Eingabefeld startet nicht mehr
  versehentlich âErzeugenâ

## 1.9.0
- **Variable Daten** (Dokument-Manipulation â Variable Daten â¦, Strg+Umschalt+D; eigener Arbeitsbereich):
  Felder auf die Vorlage legen und mit der Maus platzieren â **Text**, **QR-Code**, **Code 128**, **EAN-13**,
  alles als Vektor. Inhalt als Vorlage: `{{Spalte}}` aus einer CSV-Datei, `{{nr}}` (Nummer), `{{i}}` (laufend).
  Schrift, GrÃ¶Ãe, Farbe, Ausrichtung, Drehung, nur auf bestimmten Seiten. Vorschau mit echtem Ergebnis fÃ¼r jeden
  Datensatz. Ergebnis als neuer Reiter
- **Nummerierung:** Start, Schrittweite, Stellen (mit Nullen), Vor-/Nachsatz, PrÃ¼fziffer (Luhn, GS1/EAN, Mod 11),
  rÃ¼ckwÃ¤rts fÃ¼r AbreiÃblÃ¶cke, **WeiterzÃ¤hlen** Ã¼ber AuftrÃ¤ge hinweg (ZÃ¤hlername)
- **CSV:** Trennzeichen und Zeichensatz (UTF-8/Windows) werden erkannt; Spalten per Doppelklick einfÃ¼gen;
  Datensatzbereich; Reihenfolge je Datensatz alle Seiten oder je Seite alle DatensÃ¤tze
- **Platzhalter `{{â¦}}` im PDF** (z. B. aus InDesign) werden als Feldposition Ã¼bernommen, der Platzhaltertext
  entfernt
- **Code-Protokoll** als CSV (Ausgabeseite, Datensatz, alle Werte)
- **Nutzen mit eigenem Datensatz je Nutzen:** Druckdialog â Nutzen â âJe Nutzen die nÃ¤chste Seiteâ, Reihenfolge
  Bogen fÃ¼r Bogen oder **Schneiden und Stapeln** (jeder Stapel fortlaufend)
- Kommandozeile: Auftrag `vdp` (Felder am bequemsten als Preset aus dem Programm), `impose` mit `sr_sequence`
  und `sr_stack`; Anleitung mit Fallbeispielen
- Endformat/Anschnitt der Vorlage bleibt bei variablen Daten erhalten (fÃ¼r das AusschieÃen danach)
- Neue AbhÃ¤ngigkeit: reportlab (Text, QR- und Barcodes als Vektor) â in Setup und AppImage enthalten

## 1.8.5
- **Sonderformate im Druckdialog:** neben âPapierformatâ der Knopf *Sonderformate â¦* â Name, Breite Ã HÃ¶he in mm
  anlegen oder lÃ¶schen. Die Formate bleiben gespeichert und stehen bei allen Druckern und bei âAls PDF speichernâ
  zur Wahl (mit â). Gespoolt werden sie als SondergrÃ¶Ãe: CUPS `PageSize`/`media` = `Custom.BxHmm`, Windows
  benutzerdefiniertes Papier (DMPAPER_USER mit Breite/LÃ¤nge). Ob ein GerÃ¤t das MaÃ annimmt, entscheidet sein
  Treiber; die DruckrÃ¤nder werden vom Standardformat des Druckers Ã¼bernommen
- Druck-Presets mit Sonderformat merken sich das MaÃ (fÃ¼r `passermark-cli impose`: `sheet=custom`)

## 1.8.4
- **Behoben: Absturz-Meldung nach dem SchlieÃen** eines Fensters/Reiters (âexpected LP_struct_fpdf_document â¦â in
  der Seitenanzeige) â die Ansicht greift auf das geschlossene Dokument nicht mehr zu
- **CutContour Kreis:** Seitengriffe skalieren gleichmÃ¤Ãig (vorher kurz ein Oval, dann zurÃ¼ckgesprungen; die Felder
  blieben z. B. auf 60 Ã 120). Beim Kreis gibt es nur noch einen Durchmesser (HÃ¶he folgt der Breite)
- CutContour: Knopf âº neben âGrÃ¶Ãeâ setzt GrÃ¶Ãe und Lage zurÃ¼ck (automatisch aus dem Motiv, mittig)
- **Auf Format beschneiden:** neu âWeiÃen Rand vorher abschneidenâ (mm, Kommandozeile `crop_inset_mm`) â zuerst
  wird die Vorlage rundum um diesen Wert verkleinert, dann wie eingestellt skaliert und beschnitten

## 1.8.3
- **Behoben: Nutzen âÃberfÃ¼ller an ÃberfÃ¼llerâ lieÃ AbstÃ¤nde zwischen Objekten** â bei Einzelobjekten aus
  CutContour bzw. âObjekte trennenâ wurde die ganze Seite samt weiÃem Rand gesetzt. Jetzt tragen diese Seiten ihr
  Endformat mit: CutContour = Schnittlinie (Anschnitt = ÃberfÃ¼ller), Objekte trennen = Objekt (Anschnitt = Rand).
  Beim AusschieÃen liegen die ÃberfÃ¼ller aneinander
- Nutzen âÃberfÃ¼ller an ÃberfÃ¼llerâ mit Anschnitt 0: der Anschnitt aus dem Dokument (BleedBox) wird Ã¼bernommen â
  ein eingestellter Wert hat Vorrang. âMit Abstandâ 0 setzt die Endformate (Schnittlinien) direkt aneinander

## 1.8.2
- **Dialoge sperren nur noch ihr eigenes Fenster:** Druckdialog, CutContour, CMYK â¦ offen â in anderen
  Passermark-Fenstern kann man weiter blÃ¤ttern, zoomen, arbeiten. (Reiter im selben Fenster gehÃ¶ren zum Fenster
  und sind solange gesperrt; âIn eigenem Fenster Ã¶ffnenâ lÃ¶st einen Reiter.)
- BroschÃ¼re: âBÃ¶gen je Lageâ ist immer einstellbar; wer die Zahl Ã¤ndert, bekommt automatisch âGruppierte Lagenâ
  (bei Sammelheftung blieb die Zahl sonst ohne Wirkung). Test fÃ¼r 24 Seiten mit 3 BÃ¶gen je Lage ergÃ¤nzt

## 1.8.1
- **Reiter (Tabs):** Was im Programm entsteht oder geÃ¶ffnet wird, kommt als Reiter ins selbe Fenster â Ãffnen-Knopf
  bei offenem Dokument, Hineinziehen, Ergebnisse (CutContour, CMYK/Beschneiden, Objekte trennen â¦), âJetzt in
  Passermark Ã¶ffnenâ nach âAls PDF speichernâ, Hilfe-Anleitung. Programmstart ohne Datei und Doppelklick bzw.
  âÃffnen mitâ im Dateimanager Ã¶ffnen weiter ein eigenstÃ¤ndiges Fenster. Jeder Reiter ist ein vollstÃ¤ndiges
  Fenster mit eigenen MenÃ¼s, Leisten und Seitenleisten; mit nur einem Dokument ist die Reiterleiste ausgeblendet
- Reiter: verschieben per Ziehen, schlieÃen mit Ã, Rechtsklick â âIn eigenem Fenster Ã¶ffnenâ / âAndere
  schlieÃenâ; Datei â Neuer Reiter (Strg+Umschalt+N), Reiter in eigenes Fenster lÃ¶sen, Neues Fenster (Strg+N).
  Beim SchlieÃen eines Fensters mit mehreren Reitern wird fÃ¼r jedes ungespeicherte Dokument nachgefragt
- Abschaltbar: Datei â Einstellungen â Fenster â âIm Programm GeÃ¶ffnetes als Reiter im selben Fensterâ

## 1.8.0
- **Bindungsschemata** (Druckdialog â BroschÃ¼re): *Bindeart* Sammelheftung (alle BÃ¶gen ineinander), gruppierte
  Lagen (z. B. 4 BÃ¶gen = 16 Seiten je Lage, Lagen hintereinander) oder EinzelbÃ¶gen gestapelt (Klebebindung).
  Vorschau beschriftet âLage x Â· Bogen y â Vorder-/RÃ¼ckseiteâ
- **Leerseiten:** werden auf ein Vielfaches von 4 aufgefÃ¼llt â am Ende oder vor der letzten Seite (RÃ¼ckseite des
  Umschlags bleibt hinten); optional mit Hinweistext
- **Bundzug** (mm je Bogen, â PapierstÃ¤rke): innere BÃ¶gen werden zum Falz verschoben
- **Marken:** Falzmarken, Passermarken, Flattermarken am RÃ¼cken (Treppe beim Zusammentragen); dafÃ¼r wird am
  Bogenrand Platz freigehalten
- **BogenÃ¼bersicht â¦:** alle BÃ¶gen als Miniaturen, Doppelklick springt in die Vorschau
- **Kommandozeile `impose`:** AusschieÃen wie im Druckdialog als PDF (BroschÃ¼re/Lagen, Nutzen, Mehrere, Poster),
  Bogenformat mit `sheet` (z. B. SRA3). Druck-Presets aus dem Programm gelten direkt und merken sich das Papierformat
  (`--preset "Name"`); vorhandene Druck-Presets aus 1.7 werden Ã¼bernommen. Anleitung um Fallbeispiele ergÃ¤nzt
- **Anschnitt aus dem Dokument wird erkannt** (TrimBox/BleedBox, z. B. aus InDesign/Affinity/Scribus mit
  âAnschnitt verwendenâ): Ansicht zeigt das Endformat als rote Linie, den Anschnittbereich rot getÃ¶nt, die BleedBox
  gestrichelt (wird nicht gedruckt; Ansicht â Endformat und Anschnitt anzeigen, Strg+Umschalt+B); Statusleiste
  nennt Endformat und Anschnitt. Beim AusschieÃen (Nutzen, BroschÃ¼re, Schnittmarken, Anschnitt) wird das
  Endformat platziert und skaliert â Schnittmarken sitzen am Endformat, der Anschnitt kommt echt aus dem
  Dokument; nur wenn mehr Anschnitt eingestellt ist als vorhanden, wird der Rest an der Seitenkante gespiegelt.
  Normaler Druck (âGrÃ¶Ãeâ) druckt weiter die ganze Seite
- **Behoben: Passermark ein zweites Mal starten (StartmenÃ¼, Symbol) tat nichts**, solange schon ein Fenster offen
  war â die laufende Instanz Ã¶ffnet jetzt ein neues, leeres Fenster. Neu: Datei â Neues Fenster (Strg+N)
- Druckdialog: Preset-Zeile steht Ã¼ber den Reitern (gilt fÃ¼r Allgemein und Weitere Optionen)
- Test: Falz-Simulation (falzen, ineinanderstecken, Lagen stapeln) prÃ¼ft fÃ¼r alle Bindearten, Bindung links/rechts
  und Leerseiten-Lagen, dass die Seiten 1â¦N ergeben

## 1.7.1
- **Beschneiden auf Format skaliert jetzt** (Standard): die passende Kante wird genau aufs Zielformat skaliert,
  der Ãberstand der anderen Kante beidseitig gleich abgeschnitten â A4 â A6 = 50 %, ein schmales Plakat fÃ¼llt die
  Breite und verliert oben/unten gleich viel. Kleinere Seiten werden hochskaliert. Inhalt bleibt vektoriell.
  Bisher wurde nur abgeschnitten; das gibt es weiter als Option (HÃ¤kchen âSkalieren, bis das Format ganz gefÃ¼llt
  istâ aus bzw. `--set crop_scale=false`) fÃ¼r Dateien, die schon in EndgrÃ¶Ãe mit Anschnitt kommen.
- Kommandozeile/Ketten: `preflight_fix --set fix=flatten_layers` bricht bei Dateien ohne Ebenen nicht mehr ab,
  sondern reicht die Datei unverÃ¤ndert durch (Hinweis âKeine Ebenenâ)

## 1.7.0
- **Arbeitsbereiche:** zweite Leiste unter der Werkzeugleiste â *Anzeigen & Drucken*, *Druckaufbereitung*,
  *Bearbeiten*, *Automatisierung*. Rechts daneben stehen die Werkzeuge des gewÃ¤hlten Bereichs (z. B. PrÃ¼fen, CMYK,
  Beschneiden, CutContour, Objekte trennen, Reparieren). Druckaufbereitung Ã¶ffnet die PrÃ¼fung, Bearbeiten die
  Seitenleiste; wer den Bereich verlÃ¤sst, beendet den Bearbeiten-Modus. Der zuletzt gewÃ¤hlte Bereich gilt beim
  nÃ¤chsten Start. Die MenÃ¼s bleiben vollstÃ¤ndig.
- **Presets:** in den Fenstern CutContour, CMYK/Beschneiden und im Druckdialog oben die Zeile *Preset* â wÃ¤hlen,
  *Speichernâ¦*, lÃ¶schen, als Datei exportieren/laden, Standardwerte. Druck-Presets umfassen Seitenhandhabung,
  Mehrere, BroschÃ¼re, Poster, Nutzen und weitere Optionen (ohne Drucker und Fach).
  Ablage: Linux `~/.config/passermark/presets/`, Windows `%APPDATA%\Passermark\presets\`
- CutContour merkt sich die zuletzt verwendeten Einstellungen (ohne Versatz der Form)
- **Kommandozeile:** `--preset NAME` findet ein im Programm gespeichertes Preset; `passermark-cli presets [auftrag]`
  listet sie. Anleitung ergÃ¤nzt.
- **Als PDF speichern mit Passwort** (Druckdialog, Ziel âAls PDF speichernâ): HÃ¤kchen *PDF mit Passwort schÃ¼tzen*
  (AES-256, Passwort zweimal eingeben)
- **Windows-Setup:** optional *passermark-cli in jeder Eingabeaufforderung verfÃ¼gbar machen* (Suchpfad PATH;
  beim Deinstallieren wieder entfernt)
- TastenkÃ¼rzel ohne Doppelbelegung: Messen jetzt Strg+Umschalt+L (Strg+Umschalt+M = CMYK und Beschneiden),
  Text und Ebenen bearbeiten Strg+T (Strg+E = Auswahl exportieren), Text der Seite markieren Strg+Alt+A
  (Strg+Umschalt+A = alle Seiten auswÃ¤hlen); ein Test prÃ¼ft das kÃ¼nftig
- Eigene Symbole fÃ¼r CutContour, CMYK, Beschneiden, Objekte trennen, Bearbeiten, PrÃ¼fen, Reparieren, Messen u. a.
  (vorher teils doppelt vergebene Symbole)

## 1.6.7
- **Zeitbudget-Tests im GitHub-Build** (tests/test_performance.py): CutContour (Kontur + ÃberfÃ¼ller, Rechteck),
  Objekterkennung, PDF-Aufbau und BroschÃ¼re werden gemessen â relativ zu einer Eichaufgabe auf demselben Rechner,
  damit unterschiedlich schnelle Build-Rechner keinen Fehlalarm auslÃ¶sen. Ab 1,6Ã langsamer als bisher gelbe
  Warnung am Build, ab 3Ã schlÃ¤gt der Build fehl. Bezugswerte in tests/perf_baseline.json
  (neu messen: `python3 tests/test_performance.py --messen`)

## 1.6.6
- **Behoben: leere BlÃ¤tter beim Drucken unter Windows** (verschiedene GerÃ¤te). âAutomatischâ rastert jetzt immer
  ohne JPEG (300 dpi) â der vertrÃ¤glichste Weg. PostScript und JPEG-Durchreichen melden manche Treiber
  als unterstÃ¼tzt und liefern dann leere BlÃ¤tter; beide gibt es nur noch auf Wunsch (Datei â Einstellungen)
- Neu: **Hilfe â Windows-Druck testen** â je Verfahren (Raster, Raster + JPEG, PostScript, Vektor) eine
  beschriftete Testseite; zeigt, was der Treiber wirklich kann
- Windows-Druck: GerÃ¤tekontext wird als 64-bit-Zeiger Ã¼bergeben (vorher ctypes-Standard int), Halbton-Modus beim
  Rastern; jeder Auftrag wird in `druck-windows.log` im Protokollordner festgehalten (Verfahren, AuflÃ¶sung,
  Treiber-FÃ¤higkeiten)
- **Behoben: rÃ¶tliches Rechteck Ã¼ber dem Objekt (CutContour)**, wenn ein Programm oder Druckertreiber die
  Transparenz der ÃberfÃ¼ller-/Kantenbilder nicht auswertet (u. a. Windows-PostScript-Weg): unsichtbare Bereiche
  sind jetzt papierweiÃ bzw. zeigen das Original-Motiv statt der ersten Vollfarbe

## 1.6.5
- **Fehlerprotokoll:** jeder Fehler landet in einer Datei zum Mitschicken (mit Versionen und Systemangaben) â
  Linux `~/.local/state/passermark/logs`, Windows `%LOCALAPPDATA%\Passermark\logs`; Hilfe â Fehlerprotokolle Ã¶ffnen
  - unerwarteter Fehler: Meldung mit Pfad zum Protokoll, Passermark lÃ¤uft weiter
  - harter Absturz (z. B. in einer Bibliothek): beim nÃ¤chsten Start einmalige Meldung mit dem Protokoll
  - Fehler in Hintergrund-AuftrÃ¤gen samt Details; Fehler in Threads
  - ohne Fehler wird das Protokoll beim Beenden gelÃ¶scht; hÃ¶chstens 10 werden aufgehoben
- Paralleles Rechnen: Speicherbudget nach dem tatsÃ¤chlichen Arbeitsspeicher des Rechners (40 %, mind. 1 GB)

## 1.6.4
- CutContour mit **mehreren Seiten: ganze Seiten parallel** â jeder Arbeitsprozess rechnet eine komplette Seite
  (auch Rendern und Erkennen); kein Stocken mehr zwischen den Seiten. Eine Seite: weiterhin Objekte parallel
- Speicherschutz: Anzahl gleichzeitiger Seiten nach geschÃ¤tztem Speicherbedarf (z. B. A4: bis 8, A0: 1 â dann
  Objekte parallel)
- Fortschritt bei mehreren Seiten: â3 von 12 Seiten fertigâ; Ergebnis bitgleich zum seriellen Rechnen

## 1.6.3
- **Paralleles Rechnen:** CutContour verteilt die Objekte einer Seite auf mehrere Rechenkerne (alle bis auf einen,
  hÃ¶chstens 8); Ergebnis bitgleich zum seriellen Rechnen. Arbeitsprozesse werden einmal je Auftrag gestartet und fÃ¼r
  alle Seiten verwendet; kleine Aufgaben bleiben seriell (lohnt sich dort nicht). Begrenzen mit der Umgebungsvariable
  `PASSERMARK_WORKERS` (1 = nicht parallel)
- Fortschritt je Objekt (âSeite 1/1 Â· Objekt 12/40â)
- Abbrechen beendet auch die Arbeitsprozesse
- Intern: Objektberechnung als eigene Funktion; Programmdateien rufen `multiprocessing.freeze_support()` auf

## 1.6.2
- **Kein Einfrieren mehr:** CutContour, Objekte trennen und CMYK/Beschneiden rechnen als eigener Prozess im
  Hintergrund. Das Fenster bleibt bedienbar; unten in der Statusleiste Fortschritt und Abbrechen-Knopf (â);
  mehrere AuftrÃ¤ge gleichzeitig mÃ¶glich; das Ergebnis Ã¶ffnet sich wie gewohnt in einem neuen Fenster
- Ein Absturz in der Berechnung reiÃt das Programm nicht mehr mit â es kommt eine Fehlermeldung mit Details
- Beim SchlieÃen eines Fensters werden laufende AuftrÃ¤ge abgebrochen und aufgerÃ¤umt
- Anleitung: Beispiel âPDF/A mit Passwortâ korrigiert (PDF/A verbietet VerschlÃ¼sselung) â getrennt in âPDF/Aâ und
  âMit Passwort schÃ¼tzenâ; Test der Beispiele legt jetzt fÃ¼r jedes Beispiel eine Eingabe an (Build-Fehler unter Linux)

## 1.6.1
- **Anleitung zur Kommandozeile** (PDF, 6 Seiten) mit Fallbeispielen fÃ¼r alle AuftrÃ¤ge, Presets und ganze Ordner
  (Linux und Windows); im Programm unter **Hilfe â Kommandozeile â Anleitung**
- Die Fallbeispiele der Anleitung werden automatisch getestet (tests/test_cli_howto.py) â die Anleitung kann nicht
  unbemerkt veralten; Erzeugen mit `python3 docs/make_cli_howto.py`

## 1.6.0
- **Kommandozeile** `passermark-cli`: CutContour, Objekte trennen, CMYK/Beschneiden, Reparieren und
  Preflight-Reparaturen ohne OberflÃ¤che; Einstellungen per `--preset datei.json` und `--set schlÃ¼ssel=wert`
  (auch verschachtelt), `--pages`, Fortschrittsbalken, Strg+C bricht sauber ab, `--json-progress` fÃ¼r Programme.
  Linux: `passermark-cli` (install.sh), AppImage: `â¦ --cli`, Windows: `passermark-cli.exe`
- Intern: Kern-Schnittstelle `core.py` (Eingabe-PDF + Einstellungen â Ausgabe-PDF, Fortschritt, Abbrechen,
  atomares Schreiben) â Grundlage fÃ¼r AuftrÃ¤ge im eigenen Prozess, Presets und Watcher

## 1.5.3
- CutContour erzeugt schneller (ca. 17â20 %), Ergebnis bitgleich zu 1.5.2: Motiv-Erkennung rechnet ganzzahlig,
  Vollfarb-Suche nur noch im Randstreifen, unnÃ¶tige Abstandsberechnungen entfallen (u. a. eine pro Objekt bei der
  GlÃ¤ttung, eine beim Aussparen unter 0,08 mm)

## 1.5.2
- CutContour-Grundformen: **Griffe** an der Form in der Vorschau â Ecken skalieren gleichmÃ¤Ãig ab der Mitte,
  Seitengriffe nur Breite bzw. HÃ¶he, **Verschiebe-Griff** Ã¼ber der Form verschiebt sie
- GrÃ¶Ãe nur noch in **mm** (âGrÃ¶Ãe (B Ã H)â, âautoâ = aus dem Motiv plus Abstand); Prozent entfÃ¤llt.
  Eine eingetragene GrÃ¶Ãe gilt exakt als Schnittlinie; Ziehen an den Griffen schreibt die mm-Werte in die Felder
- Neu: **Versatz (X / Y)** in mm, mit Knopf zum ZurÃ¼cksetzen
- Behoben: Nach dem Skalieren mit der Maus wirkten eingegebene GrÃ¶Ãen nicht mehr (versteckter Prozentfaktor)
- Anzeige unten: aktuelle FormgrÃ¶Ãe in mm, beim Ziehen live

## 1.5.1
- CutContour mit Grundform (Rechteck, Kreis, Herz â¦): **eine Form um das ganze Motiv** statt einer je erkanntem Teil;
  sitzt mittig, GrÃ¶Ãe Ã¤ndert sich ab der Mitte. Option âEine Form je Objektâ fÃ¼r AufkleberbÃ¶gen
- CutContour: Form in der Vorschau **mit der Maus grÃ¶Ãer/kleiner ziehen** (Live-Anzeige in %, Ã¼bernommen beim Loslassen)
- Kreis umschlieÃt das Motiv (grÃ¶Ãere Seite als Durchmesser), statt bei breiten Motiven hindurchzuschneiden

## 1.5.0
- **Lineale und Messen** (Ansicht â Lineale anzeigen, Strg+R; Ansicht â Messen, Strg+Umschalt+M, auch in der
  Werkzeugleiste): Lineale in mm oben und links an der Kante der Ansicht, bleiben beim Scrollen stehen, Nullpunkt =
  linke obere Seitenecke, Mausposition markiert; Messen: 1. Klick Anfang, 2. Klick Ende, Umschalt rastet
  waagrecht/senkrecht/45Â° ein, Esc bricht ab; Ergebnis (LÃ¤nge, ÎX, ÎY, Winkel) rechts unten in der Statusleiste;
  gemessen in echten SeitenmaÃen, unabhÃ¤ngig von Zoom und Drehung

## 1.4.7
- CutContour: Vorschau aktualisiert sich automatisch bei jeder Einstellung â vorher zeigte sie nach einem
  Formwechsel (Rechteck, Kreis, Herz â¦) weiter die alte Kontur, bis man âVorschau aktualisierenâ drÃ¼ckte
- CutContour: Vorschau rechnet im Hintergrund, das Fenster bleibt bedienbar (âBerechne Vorschau â¦â); schnelle
  Ãnderungen hintereinander lÃ¶sen nur eine Berechnung aus
- Neuer Test (tests/test_cut_dialog.py): Formwechsel Ã¤ndert die Vorschau

## 1.4.6
- Behoben: Programm startete unter Python 3.10/3.11 nicht (z. B. Ubuntu 22.04) â Syntax in convert.py, die erst ab
  Python 3.12 erlaubt ist; das AppImage-Build prÃ¼ft das jetzt als ersten Schritt
- AppImage: installiertes Ghostscript hat Vorrang, das mitgelieferte dient als Reserve; startet es beim Bauen
  nicht, wird es mit Warnung entfernt (Build bricht nicht ab)
- **Fertige Programme Ã¼ber GitHub:** Windows-Setup.exe und Linux-AppImage werden bei jedem Push gebaut, bei
  Tags `v*` als Release verÃ¶ffentlicht; AbhÃ¤ngigkeiten (Python, Qt, alle Pakete, Ghostscript) sind enthalten
- Selbsttest der fertigen Programmdatei im Build (`--selftest`); `--version`
- Ghostscript wird neben der eigenen Programmdatei gefunden (Installer/AppImage bringen es mit)
- AppImage: Admin-Standards speichern Ã¼ber pkexec mit demselben abgesicherten Helfer
- Behoben: Admin-Fenster auf kleinen Bildschirmen nicht scrollbar (Reiter scrollen, Fenster passt sich an)
- Behoben: Touchpad-Scrollen (Seitenwechsel/Zoom) unter Windows
- `uninstall.sh`, `.gitignore`; Installer-Skript UTF-8 mit BOM; `build.ps1` reines ASCII; README auf Englisch

## 1.4.5
- **Windows-Druck neu** (wie pdfToolkit 1.4.3): PostScript direkt fÃ¼r PS-Treiber, sonst eigenes Rastern in Streifen
  mit JPEG â behebt langes Spoolen und AbbrÃ¼che (besonders bei Mehrfachnutzen); Einstellungen unter
  Datei â Einstellungen â âDrucken unter Windowsâ. Linux-Druck unverÃ¤ndert
- Behoben: mÃ¶gliche AbstÃ¼rze â die DokumentprÃ¼fung nutzte pdfium in einem Hintergrund-Thread gleichzeitig mit der
  Anzeige (pdfium ist nicht thread-sicher); diese Teile laufen jetzt im Hauptthread

## 1.4.4
- **Ursache gefunden** (an einer Chrome-PDF): pdfium kann Seiten mit **Type3-Schriften** nicht neu schreiben â
  bisher verschwand dabei aller Text. Bearbeiten kommt jetzt ganz ohne Neuerzeugung der Seite aus:
  - Verschieben/Skalieren: Zeile wird aus ihrem Textblock herausgelÃ¶st (Zeilenmatrix wird mitgerechnet), auch wenn
    sich viele Zeilen einen Block teilen
  - Text/Schrift Ã¤ndern: zuerst direkt; verliert die Seite dabei Inhalt, wird die alte Zeile entfernt und die neue
    an gleicher Stelle und in gleicher Farbe darÃ¼bergelegt
  - LÃ¶schen: nur die Textbefehle der Zeile werden entfernt
- Koordinatensystem wird mitgerechnet (Chrome: MaÃstab 0,24 + gespiegelt; CAD: 0,12) â beim Verschieben von Text
  und Ebenen, beim Ersetzen von Ebenen und bei der CutContour-Linie (Originalinhalt wird in q/Q eingeschlossen)
- Zeilen werden besser erkannt (auch bei Schriftwechsel in der Zeile und einzeln gesetzten Buchstaben)
- NachprÃ¼fung empfindlicher (auch bei Seiten mit wenig Text)
- Neue Tests: Chrome-artige Type3-Datei, CAD-Ebene in skaliertem Koordinatensystem

## 1.4.3
- Behoben: Nach Verschieben/Skalieren per Maus, TextÃ¤nderung oder Schriftwechsel konnten alle Texte der Seite
  verschwinden
  - Verschieben/Skalieren von Text Ã¤ndert jetzt nur noch die betroffenen TextblÃ¶cke im PDF (q/cm/Q), die Ã¼brige
    Seite bleibt byte-gleich; pdfiums Neuerzeugung der Seite nur noch als RÃ¼ckfall
  - jede Textbearbeitung lÃ¤uft auf einer Kopie und wird **nachgeprÃ¼ft** (Zeichen und Bildpunkte auÃerhalb der
    bearbeiteten Zeile); fehlt etwas, wird nichts Ã¼bernommen und eine Meldung mit Details erscheint
  - die Ansicht gibt vor der Bearbeitung ihre offenen Seiten frei
- Start-Test deutlich strenger (fehlende eigene Methoden fallen sofort auf) und prÃ¼ft jetzt auch Text Ã¤ndern,
  Schrift wechseln und LÃ¶schen â dabei bleiben alle anderen Zeilen erhalten

## 1.4.2
- Behoben: âdon't know how to encode value np.float64â beim Skalieren von Ebenen (Bezug âMitte der Ebeneâ)
- Behoben: Mausauswahl im Bearbeiten-Modus fand nichts, wenn die Listen beim Einschalten nicht geladen waren
- **Mit der Maus verschieben und skalieren:** Objekt (Textzeile/Ebene) greifen und ziehen; an den vier Eckgriffen
  skalieren (gegenÃ¼berliegende Ecke bleibt fix); gestrichelte Vorschau, passende Mauszeiger, RÃ¼ckgÃ¤ngig
- Textzeilen verschieben/skalieren behÃ¤lt Schrift, Farbe und Ebene
- Feinere Ebenen-Erkennung; Start-Test prÃ¼ft jetzt auch die Mausbedienung

## 1.4.1
- Behoben: Programm startete nicht (Namenskonflikt in der Seitenansicht durch die neue Textauswahl)
- Behoben: Strg+C (Text kopieren) hÃ¤tte einen Fehler ausgelÃ¶st (fehlender Import)
- Neuer Start-Test (tests/test_gui_smoke.py): Programmstart, Fenster, Textauswahl, Bearbeiten-Modus â ohne Bildschirm

## 1.4.0
- **Bearbeiten-Modus** (Dokument-Manipulation â Text und Ebenen bearbeiten, Strg+E): Seitenleiste âBearbeitenâ
  - **Text:** Zeilen der Seite auflisten oder auf der Seite anklicken; Text, Schrift (Original, Standardschriften,
    eigene Datei) und GrÃ¶Ãe Ã¤ndern, Zeile lÃ¶schen
  - **Ebenen:** auflisten oder auf der Seite anklicken (wiederholter Klick wechselt durch Ã¼bereinanderliegende);
    ein-/ausblenden, entfernen, skalieren/verschieben (inkl. âAuf die Seite zurÃ¼ckholenâ), durch eine Seite einer
    anderen PDF ersetzen; RÃ¼ckgÃ¤ngig
- **Text markieren** in der Seitenansicht (ziehen, Doppelklick = Wort, Strg+C kopiert)
- Schrift-Download: eigene KnÃ¶pfe unter der Tabelle, sichtbare Fehlermeldungen, RÃ¼ckfall auf das fontsource-CDN
- Ãbersetzungen: fehlende Texte ergÃ¤nzt (Druckdialog, Admin, ZusammenfÃ¼hren, Dateifilter, Meldungen),
  â&â in Ãbersetzungen ausgeschrieben, deutsche Treiberbegriffe (deutsch installierte PPDs) werden Ã¼bersetzt

## 1.3.2
- Behoben: Dialog âFreie Schrift herunterladenâ Ã¶ffnete sich nicht
- Ebenen festschreiben / Empfohlene Reparaturen: unterscheiden sich Ansicht und Druck, fragt Passermark, welcher
  Zustand gelten soll (âWie beim Druckâ / âWie am Bildschirmâ) â statt still den Druck-Zustand zu nehmen
- Einbetten: Warnung, wenn fÃ¼r eine fehlende Schrift kein Ersatz gewÃ¤hlt ist (Ghostscript nÃ¤hme sonst eine eigene)
- CAD-Normschriften (ISOCPEUR & Co.) ohne osifont: schmale Ausweichschrift (DejaVu Sans Condensed)
- Schriften mit eigenen Zeichennamen (ohne Einbettung) werden als nicht reparierbar erkannt

## 1.3.1
- Schrift-Download: kommerzielle Schriften werden auf ihren freien, metrisch gleichen Zwilling umgeleitet
  (Arial â Arimo, Times New Roman â Tinos, Courier New â Cousine, Calibri â Carlito, Cambria â Caladea,
  Georgia â Gelasio); der Dialog schlÃ¤gt ihn vor und erklÃ¤rt warum
- Unbekannter Name: VorschlÃ¤ge Ã¤hnlicher freier Schriften (âMeintest du â¦â) statt nur â404â

## 1.3.0
- **Neuer Name: Passermark** (vorher pdfToolbox â Namensgleichheit mit einem kommerziellen Preflight-Produkt);
  eigene Pfade (/etc/passermark, /usr/local/lib/passermark), lÃ¤uft neben pdfToolkit/pdfToolbox
- **DokumentprÃ¼fung (Preflight)** beim Ãffnen: Schriften (Einbettung, Typ, Unicode, seltsame Zeichen), Ebenen
  (Ansicht/Druck, verrutscht), Transparenzen; Statusknopf, Seitenleiste âPrÃ¼fungâ, Bericht
- Reparaturen: Ebenen-Zustand Ã¼bernehmen, sichtbaren Zustand festschreiben, Ebenen entfernen, Schriften einbetten
  mit metrisch kompatiblem Ersatz / eigener Datei / Download (fontsource.org), Text in Pfade, Transparenzen reduzieren
- install.sh: freie Ersatzschriften (Liberation, Carlito, Caladea, URW, DejaVu)

## 1.2.5
- CutContour: **ÃberfÃ¼ller abschaltbar** (âerzeugenâ bzw. 0 mm) â Motiv bleibt unverÃ¤ndert (kein ÃberfÃ¼ller, kein
  Ausstanzen), nur die Schnittlinie; mit positivem âAbstand zum Motivâ entstehen weiÃe RÃ¤nder

## 1.2.4
- CutContour-Farben: **Entmischen** statt RGB-Abstand â Kantenpixel werden als Mischung Vollfarbe+Hintergrund
  bzw. Vollfarbe+Vollfarbe gedeutet (helles Rosa = Rot, nicht GrÃ¼n); behebt falschfarbige Keile im ÃberfÃ¼ller
- ÃberfÃ¼ller-Farbe kommt aus dieser Zuordnung; innerhalb der Schnittform immer voll deckend
- Aussparung: winzige LÃ¶cher geschlossen (keine weiÃen PÃ¼nktchen), engere Toleranz (kein heller Strich)
- Neu: **ÃberfÃ¼ller-Farbe fest wÃ¤hlbar** (gleichmÃ¤Ãiger Rand) fÃ¼r Motive, bei denen die Automatik nicht passt
- Neu (optional): **Mischkanten im Motiv bereinigen** (schmale SÃ¤ume bis ~1 mm zwischen Vollfarben)

## 1.2.3
- CutContour-ÃberfÃ¼ller in **Vollfarben**: Farbe = rechnerisch nÃ¤chste Vollfarbe des Objekts (exakter
  Originalton), keine blassen MischtÃ¶ne mehr von KantenglÃ¤ttung/skaliertem Raster
- **Heller Saum entfernt:** Bei Motiven mit Hintergrund wird der Mischsaum am Rand ausgespart (flÃ¤chige Motive:
  adaptiv bis 1,5 mm, Fotos: 0,25 mm) â dort liegt der vollfarbige ÃberfÃ¼ller
- **Innenschnitt mit ÃberfÃ¼ller:** ausgeschnittene LÃ¶cher werden im Original ausgespart, der ÃberfÃ¼ller lÃ¤uft
  Ã¼ber die innere Schnittlinie; kleine InnenflÃ¤chen (weiÃe Schrift) bleiben

## 1.2.2
- Behoben: Fehler âdon't know how to encode value np.float64â bei âJedes Objekt als eigene Seiteâ + ÃberfÃ¼ller
  (SeitenmaÃe werden jetzt als normale Zahlen an pikepdf Ã¼bergeben)
- Behoben: ÃberfÃ¼ller unsichtbar bei Motiven mit Hintergrund (weiÃe Seite, Rasterbild) â das Original wird auf
  die Objektform begrenzt (Hintergrund ausgestanzt), InnenflÃ¤chen wie weiÃe Schrift bleiben; Vorschau ebenso

## 1.2.1
- Objekte trennen: **Rand wirkt sofort** (auch negativ, auch auf selbst gezogene Rahmen) â vorher nur nach
  âneu erkennenâ; gestrichelte Vorschau des Randes; Ã¼brige Regler erkennen automatisch neu
- CutContour: **ÃberfÃ¼ller fÃ¼llt die ganze FlÃ¤che innerhalb der Schnittlinie** (Raum zwischen Objekt und
  Linie, Einbuchtungen) plus ÃberfÃ¼ller Ã¼ber die Linie â Randfarben (auch mehrfarbig) nach auÃen gezogen,
  liegt hinter dem Objekt; Farben aus dem Kern (keine Mischfarben von der KantenglÃ¤ttung)
- Fehlermeldungen in den Objekt-Dialogen mit âDetailsâ (Ablauf zum Kopieren)

## 1.2.0
- CutContour: **Stickerformen** Rechteck, abgerundetes Rechteck, Kreis, Oval, Sechseck, Achteck, Herz, Stern,
  Wappen, Torbogen â in ObjektgrÃ¶Ãe, skalierbar (%) oder feste GrÃ¶Ãe (mm); Abstand auch negativ
- CutContour: **ÃberfÃ¼ller geht vom Objekt aus** (keine Rahmen in leeren FlÃ¤chen); Schnitt am Motiv liegt
  immer im ÃberfÃ¼ller
- CutContour: Ausgabe wahlweise **jedes Objekt als eigene Seite** mit Rand (Standard 6 mm), Nachbarn ausgeblendet
- Erkennung: Motiv, das die ganze Seite fÃ¼llt, wird als ein Objekt erkannt (Kontur hing vorher am Seitenrand);
  Auto-Modus erkennt Hintergrund auch bei teilweise transparenten Seiten
- Objekte trennen: Rand auch **negativ** (nach innen)

## 1.1.0
- **Objekte trennen:** Objekte (Visitenkarten, Fotos auf Scans â¦) erkennen und als Einzelseiten ohne WeiÃraum
  Ã¶ffnen; Vektor exakt Ã¼ber Transparenz, Raster Ã¼ber Hintergrundfarbe; Rahmen bearbeitbar
- **CutContour** fÃ¼r Schneideplotter (Roland VersaWorks): Sonderfarbe âCutContourâ, Abstand, GlÃ¤ttung zum
  Entgittern, automatisch erzeugter ÃberfÃ¼ller (Schnitt liegt immer darin), Innenkonturen, Vorschau
- **SVG/SVGZ Ã¶ffnen** (vektoriell, echte GrÃ¶Ãe; rsvg-convert > Inkscape > Qt), auch per Rechtsklick und ZusammenfÃ¼hren
- Transparenz bei WebP/GIF/HEIC bleibt erhalten (statt auf WeiÃ geplÃ¤ttet)
- Neue AbhÃ¤ngigkeiten: scipy, contourpy, librsvg2-bin

## 1.0.1
- Dokument-Manipulation jetzt als eigenes MenÃ¼ neben âDokumentâ (CMYK-Umwandlung, Beschneiden, beides);
  nicht mehr im Druckdialog
- Ergebnis Ã¶ffnet sich in einem neuen Fenster, abgelegt nur temporÃ¤r im Zwischenspeicher (beim Beenden gelÃ¶scht)
- Behoben: Beschneiden wirkte beim Druck nicht â gedruckt wird jetzt die beschnittene Datei selbst
  (durchgehender Test: Beschneiden -> Zwischenspeicher -> Druck, Rand verschwindet)
- MenÃ¼ âDokumentâ: ZusammenfÃ¼hren und Reparieren/Optimieren

## 1.0.0 (Oktober 2026)
Erste Version von Passermark, aufgebaut auf pdfToolkit 1.4.0 (alle Funktionen Ã¼bernommen).

- **Dokument-Manipulation** (Reiter im Druckdialog und MenÃ¼ Dokument):
  - CMYK-Umwandlung: RGBâCMYK mit unverÃ¤ndertem CMYK, komplette Neuseparation (Quell- â Zielprofil),
    Graustufen; Intent, BPC, Grau/Schwarz nur mit K, Output Intent
  - Farbvorschau vorher/nachher aus echten CMYK-Werten, EinzelauszÃ¼ge, Farbauftrag (TAC), PapierweiÃ
  - Beschneiden auf Zielformat mit beidseitig gleichem Ãberstand, Hoch-/Querformat folgt der Seite
- EigenstÃ¤ndig installierbar neben pdfToolkit (eigene Pfade, Admin-Helfer, Polkit-Regel, Einzelinstanz)
- Eigenes Icon; alle Texte in Deutsch, Englisch, Ungarisch, Spanisch, FranzÃ¶sisch

