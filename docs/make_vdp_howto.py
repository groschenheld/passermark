# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Erzeugt pdfdruck/docs/passermark-vdp-anleitung.pdf (Variable Daten: Oberfläche und Kommandozeile, mit Beispielen).

    python3 docs/make_vdp_examples.py     (zuerst: Beispiele und Ergebnis-PDFs)
    python3 docs/make_vdp_howto.py

Stil und Hilfsfunktionen kommen aus make_cli_howto.py.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_cli_howto as H  # noqa: E402  (registriert auch die Schriften)
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import Image, PageBreak, SimpleDocTemplate, Spacer  # noqa: E402

from pdfdruck import __version__  # noqa: E402
from pdfdruck.examples import EXAMPLES, VDP_DIR, VDP_HOWTO  # noqa: E402

P, c, code, table, W = H.P, H.c, H.code, H.table, H.W
H1, H2, H3, SUB, NOTE = H.H1, H.H2, H.H3, H.SUB, H.NOTE
NAMES = dict(EXAMPLES)
TMP = tempfile.mkdtemp(prefix="pm-howto-")


def result_image(stem, width=82 * mm):
    """Erste Seite des Ergebnis-PDFs als Bild (mit dünnem Rand)."""
    import pypdfium2 as pdfium
    d = pdfium.PdfDocument(os.path.join(VDP_DIR, "ergebnis", stem + ".pdf"))
    try:
        img = d[0].render(scale=3).to_pil()
    finally:
        d.close()
    p = os.path.join(TMP, stem + ".png")
    img.save(p)
    im = Image(p, width=width, height=width * img.height / img.width)
    return im


def steps(items):
    return [P(f"<b>{i}.</b> {t}") for i, t in enumerate(items, 1)]


def example_block(stem, title, intro, rows, gui, cli):
    s = [P(f"{title}", H3), P(intro)]
    s.append(table([["Feld", "Inhalt", "Lage (links, oben, B × H in mm)"]] + rows, [24 * mm, 80 * mm, W - 104 * mm]))
    s.append(Spacer(1, 4))
    s.append(result_image(stem))
    s.append(P("Ergebnis Seite 1 (ergebnis/" + stem + ".pdf)", NOTE))
    s.append(P("<b>In der Oberfläche selbst anlegen</b>"))
    s += steps(gui)
    s.append(P("<b>Fertiges Preset verwenden:</b> in der Preset-Leiste oben im Dialog „" + NAMES[stem] + "“ wählen.", NOTE))
    s.append(P("<b>Kommandozeile</b> (im Ordner der Beispiele)"))
    s.append(code(cli))
    return s


def build():
    s = []
    s += [P("Passermark – Variable Daten", H1),
          P(f"Nummern, Texte aus einer CSV, QR-Code, Code 128 und EAN-13 – in der Oberfläche und auf der "
            f"Kommandozeile · Passermark {__version__}", SUB)]
    s.append(P("Variable Daten legen Felder auf ein PDF und füllen sie für jede Seite neu: fortlaufende Nummern, "
               "Namen aus einer Tabelle, QR- und Strichcodes. Die Vorlage bleibt, wie sie ist; alles wird als "
               "Vektor darübergelegt."))

    # ------------------------------------------------------------------ 1 Prinzip
    s.append(P("1 · So funktioniert es", H2))
    s.append(P("Jedes Feld ist ein Kasten auf der Seite mit einem <b>Inhalt</b>. Der Inhalt ist fester Text, "
               "gemischt mit Platzhaltern in doppelten geschweiften Klammern. Das gilt gleich für Text, QR-Code, "
               "Code 128 und EAN-13."))
    s.append(table([
        ["Platzhalter", "wird zu", "kommt aus"],
        [c("{{nr}}"), "der Nummer, z. B. 0001", "Abschnitt 3 im Dialog (Nummerierung): erste Nummer, Stellen, "
         "Vorsatz, Prüfziffer"],
        [c("{{i}}"), "1, 2, 3 … (immer ohne Format)", "laufender Zähler der Datensätze"],
        [c("{{Spaltenname}}"), "dem Wert dieser Spalte", "der CSV-Datei; erste Zeile = Spaltennamen"],
    ], [32 * mm, 52 * mm, W - 84 * mm]))
    s.append(P("Ohne Klammern ist es einfacher Text: " + c("nr") + " druckt „nr“. Groß-/Kleinschreibung der "
               "Spaltennamen ist egal.", NOTE))
    s.append(P("Feldarten", H3))
    s.append(table([
        ["Art", "Was hinein darf", "Beispiel-Inhalt", "Darauf achten"],
        ["Text", "alles, auch Umlaute", c("Ticket {{nr}}"), "Schrift, Größe, Farbe, Ausrichtung im Dialog"],
        ["QR-Code", "alles: Text, Umlaute, Webadressen", c("https://…/{{nr}}"),
         "wird quadratisch in den Kasten eingepasst; für Webadressen ab etwa 20 × 20 mm"],
        ["Code 128", "Buchstaben, Ziffern, übliche Zeichen – keine Umlaute", c("T{{nr}}"),
         "wird auf die Kastenbreite gezogen – breit anlegen (50–60 mm für 8–10 Zeichen). Größe = Klartextzeile "
         "darunter, 0 = keine"],
        ["EAN-13", "genau 12 oder 13 Ziffern", c("{{EAN}}"),
         "bei 12 Ziffern wird die Prüfziffer dazugerechnet; bei 13 wird die letzte Stelle neu gerechnet"],
    ], [20 * mm, 40 * mm, 42 * mm, W - 102 * mm]))
    s.append(P("Wie die Datensätze auf die Seiten kommen", H3))
    s.append(table([
        ["Einstellung (Dialog / " + c("order") + ")", "Ergebnis"],
        ["Jede Seite bekommt den nächsten Datensatz / " + c("each"),
         "Standard. Einseitige Vorlage: je Datensatz eine Seite. Mehrseitige Vorlage: Seite 1 → Datensatz 1, "
         "Seite 2 → Datensatz 2 …"],
        ["Je Datensatz eine Kopie des ganzen Dokuments / " + c("record"),
         "alle Seiten mit demselben Datensatz, dann die nächste Kopie (Vorder- und Rückseite einer Karte)"],
        ["… sortiert Seite für Seite / " + c("page"), "wie oben, aber zuerst alle Vorderseiten, dann alle Rückseiten"],
    ], [70 * mm, W - 70 * mm]))

    # ------------------------------------------------------------------ 2 Beispiele holen
    s.append(P("2 · Die Beispiele holen", H2))
    s.append(P("Passermark bringt vier fertige Beispiele mit. „Holen“ kopiert sie in den Ordner "
               + c("Passermark-Beispiele/vdp") + " in deinem Benutzerordner und trägt sie als Presets "
               "„Beispiel 1“ bis „Beispiel 4“ ein (mit dem richtigen Pfad zur CSV)."))
    s.append(table([
        ["Wo", "So"],
        ["Oberfläche", "Menü <b>Hilfe → Beispiele für Variable Daten holen …</b> oder Arbeitsbereich "
         "<b>Variable Daten → Beispiele</b>. Die Vorlage öffnet sich gleich in einem neuen Reiter."],
        ["Kommandozeile", c("passermark-cli beispiele") + " – oder " + c("passermark-cli beispiele D:\\Kurs")
         + " für einen anderen Ordner"],
    ], [30 * mm, W - 30 * mm]))
    s.append(Spacer(1, 4))
    s.append(table([
        ["Datei", "Inhalt"],
        [c("vorlage-a6.pdf"), "leere Vorlage A6 quer – darauf kommen die Felder"],
        [c("daten.csv"), "3 Datensätze: Name;Ort;Artikelnummer;EAN"],
        [c("presets/beispiel-*.json"), "die Einstellungen der vier Beispiele"],
        [c("ergebnis/beispiel-*.pdf"), "so muss das Ergebnis aussehen"],
        [c("LIESMICH.txt"), "Kurzfassung dieser Anleitung"],
    ], [50 * mm, W - 50 * mm]))
    s.append(Spacer(1, 4))
    s.append(P("Inhalt von " + c("daten.csv") + ":", NOTE))
    s.append(code(open(os.path.join(VDP_DIR, "daten.csv"), encoding="utf-8").read()))

    # ------------------------------------------------------------------ 3 Oberfläche allgemein
    s.append(PageBreak())
    s.append(P("3 · In der Oberfläche – der Ablauf", H2))
    s += steps([
        "PDF öffnen, das die Vorlage ist (z. B. " + c("vorlage-a6.pdf") + ").",
        "Arbeitsbereich <b>Variable Daten</b> wählen und auf <b>Variable Daten</b> klicken – oder "
        + c("Strg+Umschalt+D") + ". Links ist die Vorschau, rechts die Einstellungen in vier Gruppen.",
        "<b>1. Felder auf der Seite:</b> mit <b>+ Text</b>, <b>+ QR-Code</b>, <b>+ Code 128</b> oder <b>+ EAN-13</b> "
        "ein Feld anlegen. In der Vorschau ziehen oder unter „Lage und Größe“ in mm eingeben (links/oben = Abstand "
        "von der linken oberen Ecke der Seite). Unter <b>Inhalt des gewählten Feldes</b> eintragen, was hinein soll.",
        "<b>2. Woher kommen die Daten?</b> Ohne Tabelle: „keine – nur Nummerierung“ lassen und die Anzahl einstellen. "
        "Mit Tabelle: <b>CSV öffnen …</b> – die Spalten erscheinen unter „Platzhalter zum Einfügen“; Doppelklick "
        "fügt sie in den Inhalt des gewählten Feldes ein.",
        "<b>3. Nummerierung</b> – nur nötig, wenn ein Inhalt " + c("{{nr}}") + " enthält: erste Nummer, "
        "Schrittweite, Stellen (mit Nullen), Text davor/danach, Prüfziffer.",
        "Oben über der Vorschau mit <b>Seite</b> / <b>Datensatz</b> durchblättern und prüfen. Fehler (z. B. falsche "
        "EAN-Länge) stehen dort statt des Codes.",
        "<b>Erzeugen (neuer Reiter)</b> – das Ergebnis öffnet sich als neues Dokument. Dann speichern oder drucken.",
    ])
    s.append(P("Einstellungen behalten: in der Preset-Leiste oben im Dialog speichern. Ohne Preset merkt sich "
               "der Dialog die Einstellungen nur bis zum Schließen von Passermark. <b>Alles zurücksetzen</b> "
               "fängt mit einem leeren Textfeld " + c("{{nr}}") + " neu an.", NOTE))

    # ------------------------------------------------------------------ 4 Beispiele
    s.append(PageBreak())
    s.append(P("4 · Die vier Beispiele", H2))
    s.append(P("Alle Beispiele verwenden " + c("vorlage-a6.pdf") + ". Lage in mm: links, oben, Breite × Höhe. "
               "Die kleinen Textzeilen in den Beispielen zeigen nur zur Kontrolle, was im Code steckt.", NOTE))
    blocks = [
        example_block(
            "beispiel-1-qr-nummer", "Beispiel 1 – QR-Code mit fortlaufender Nummer (ohne CSV)",
            "5 Tickets; jeder QR-Code enthält eine eigene Webadresse.",
            [["QR-Code", c("https://deinefirma.at/ticket/{{nr}}"), "100, 25, 35 × 35"],
             ["Text", c("Ticket {{nr}}") + ", 16 pt", "10, 30, 60 × 8"]],
            ["Vorlage öffnen, Variable Daten (" + c("Strg+Umschalt+D") + "), <b>Alles zurücksetzen</b>.",
             "Das vorhandene Textfeld wählen, Inhalt " + c("Ticket {{nr}}") + ", Größe 16.",
             "<b>+ QR-Code</b>, Inhalt " + c("https://deinefirma.at/ticket/{{nr}}") + ", Lage 100 / 25 / 35 / 35.",
             "2.: „keine – nur Nummerierung“, Anzahl Datensätze <b>5</b>.",
             "3.: erste Nummer 1, Schrittweite 1, <b>Stellen 4</b> → 0001 … 0005.",
             "Datensatz 1–5 durchblättern, <b>Erzeugen</b>."],
            'passermark-cli vdp vorlage-a6.pdf tickets.pdf --preset presets/beispiel-1-qr-nummer.json\n'
            '# 200 statt 5 Stück, ab Nummer 101:\n'
            'passermark-cli vdp vorlage-a6.pdf tickets.pdf --preset "Beispiel 1 – QR mit Nummer" \\\n'
            '    --set count=200 --set numbering.start=101'),
        example_block(
            "beispiel-2-qr-csv", "Beispiel 2 – QR-Code und Text aus der CSV",
            "Je Zeile der CSV eine Karte; der QR-Code enthält Name und Ort (Umlaute gehen).",
            [["QR-Code", c("{{Name}} – {{Ort}}"), "100, 25, 35 × 35"],
             ["Text", c("{{Name}}") + ", 16 pt", "10, 30, 60 × 8"],
             ["Text", c("{{Ort}}"), "10, 42, 60 × 8"]],
            ["Vorlage öffnen, Variable Daten, <b>Alles zurücksetzen</b>.",
             "2.: <b>CSV öffnen …</b> → " + c("daten.csv") + ". Unter „Platzhalter zum Einfügen“ stehen jetzt "
             "Name, Ort, Artikelnummer, EAN.",
             "Textfeld wählen, Inhalt leeren, <b>Name</b> doppelklicken → " + c("{{Name}}") + "; Größe 16.",
             "<b>+ Text</b> für " + c("{{Ort}}") + ", Lage 10 / 42.",
             "<b>+ QR-Code</b>, Inhalt " + c("{{Name}} – {{Ort}}") + " (Doppelklick, dazwischen „ – “ tippen).",
             "Datensatz 1–3 durchblättern, <b>Erzeugen</b>."],
            'passermark-cli vdp vorlage-a6.pdf karten.pdf --preset presets/beispiel-2-qr-csv.json\n'
            '# andere Tabelle, nur die ersten 50 Zeilen:\n'
            'passermark-cli vdp vorlage-a6.pdf karten.pdf --preset "Beispiel 2 – QR aus CSV" \\\n'
            '    --set csv_path=gaeste.csv --set records=1-50'),
        example_block(
            "beispiel-3-code128", "Beispiel 3 – Code 128 aus Nummer und aus der CSV",
            "Oben ein Code aus Buchstabe + Nummer, unten die Artikelnummer aus der Tabelle.",
            [["Code 128", c("T{{nr}}") + ", Größe 9", "10, 28, 60 × 18"],
             ["Code 128", c("{{Artikelnummer}}") + ", Größe 9", "10, 62, 60 × 18"]],
            ["Vorlage öffnen, Variable Daten, <b>Alles zurücksetzen</b>, Textfeld mit <b>Feld löschen</b> entfernen.",
             "2.: <b>CSV öffnen …</b> → " + c("daten.csv") + ".",
             "<b>+ Code 128</b>, Inhalt " + c("T{{nr}}") + ", Lage 10 / 28 / 60 / 18, Größe 9 "
             "(= Klartext darunter; 0 = ohne).",
             "3.: <b>Stellen 4</b> → T0001, T0002, T0003.",
             "<b>+ Code 128</b>, Inhalt " + c("{{Artikelnummer}}") + " (Doppelklick), Lage 10 / 62 / 60 / 18.",
             "<b>Erzeugen</b>."],
            'passermark-cli vdp vorlage-a6.pdf etiketten.pdf --preset presets/beispiel-3-code128.json'),
        example_block(
            "beispiel-4-ean13", "Beispiel 4 – EAN-13 aus der CSV und aus der Nummerierung",
            "Links fertige EAN aus der Tabelle (13 und 12 Ziffern gemischt), rechts eine selbst erzeugte "
            "interne Nummer.",
            [["EAN-13", c("{{EAN}}"), "10, 25, 45 × 28"],
             ["EAN-13", c("{{nr}}") + " (Vorsatz 2012345, Stellen 5)", "80, 25, 45 × 28"]],
            ["Vorlage öffnen, Variable Daten, <b>Alles zurücksetzen</b>, Textfeld löschen.",
             "2.: <b>CSV öffnen …</b> → " + c("daten.csv") + ".",
             "<b>+ EAN-13</b>, Inhalt " + c("{{EAN}}") + ". Datensatz 2 hat nur 12 Ziffern (978316148410) – "
             "die Prüfziffer 0 wird dazugerechnet.",
             "<b>+ EAN-13</b>, Inhalt " + c("{{nr}}") + ", Lage 80 / 25 / 45 / 28.",
             "3.: Text davor <b>2012345</b>, <b>Stellen 5</b>, Prüfziffer <b>keine</b> → 201234500001 "
             "(12 Ziffern) → Code 2012345000018.",
             "<b>Erzeugen</b>."],
            'passermark-cli vdp vorlage-a6.pdf ean.pdf --preset presets/beispiel-4-ean13.json'),
    ]
    for i, b in enumerate(blocks):
        if i:
            s.append(PageBreak())
        s += b
    s.append(P("EAN-13 für den Handel braucht eine bei GS1 registrierte Nummer. Für rein interne Codes "
               "(Lager, Inventar) sind die Nummernbereiche 20–29 vorgesehen.", NOTE))

    # ------------------------------------------------------------------ 5 Kommandozeile
    s.append(P("5 · Auf der Kommandozeile", H2))
    s.append(P("Die Felder legt man im Programm an und speichert ein Preset; die Kommandozeile verwendet es und ändert "
               "nur, was sich je Auftrag ändert. Ein Preset geht als Datei oder als Name aus der Preset-Leiste."))
    s.append(code('passermark-cli beispiele                               # Beispiele + Presets holen\n'
                  'passermark-cli presets vdp                             # gespeicherte Presets anzeigen\n'
                  'passermark-cli vdp <vorlage.pdf> <ergebnis.pdf> --preset "<Name oder Datei>" [--set …]'))
    s.append(table([
        ["Mit --set ändern", "Beispiel", "Bedeutung"],
        [c("csv_path"), c("--set csv_path=liste.csv"), "andere Tabelle"],
        [c("count"), c("--set count=500"), "ohne CSV: so viele Datensätze"],
        [c("records"), c("--set records=1-50"), "nur diese Zeilen der Tabelle"],
        [c("numbering.start"), c("--set numbering.start=101"), "erste Nummer"],
        [c("numbering.digits"), c("--set numbering.digits=6"), "Stellen mit Nullen"],
        [c("numbering.prefix"), c("--set numbering.prefix=A-"), "Text vor der Nummer"],
        [c("numbering.continue_key"), c("--set numbering.continue_key=Tickets"),
         "beim nächsten Auftrag dort weiterzählen"],
        [c("order"), c("--set order=record"), c("each") + " / " + c("record") + " / " + c("page") + " (Abschnitt 1)"],
        [c("reverse"), c("--set reverse=true"), "rückwärts (Abreißblock)"],
        [c("log_path"), c("--set log_path=codes.csv"), "Protokoll: welche Seite welchen Code hat"],
    ], [40 * mm, 62 * mm, W - 102 * mm]))
    s.append(Spacer(1, 4))
    s.append(P("Ein relativer " + c("csv_path") + " im Preset (wie " + c("daten.csv") + " in den Beispiel-Dateien) "
               "wird zuerst im aktuellen Ordner gesucht, dann neben der Preset-Datei.", NOTE))
    s.append(P("Windows: ohne das Setup-Häkchen für den Suchpfad den vollen Pfad schreiben, z. B. "
               + c('"C:\\Program Files\\Passermark\\passermark-cli.exe" vdp …') + ". AppImage: "
               + c("./Passermark-*.AppImage --cli vdp …") + ".", NOTE))
    s.append(P("Viele Karten auf einen Bogen", H3))
    s.append(P("Erst die Daten erzeugen, dann ausschießen – jeder Nutzen bekommt die nächste Seite, die Stapel "
               "bleiben nach dem Schneiden fortlaufend:"))
    s.append(code("passermark-cli vdp vorlage-a6.pdf tickets.pdf \\\n"
                  "    --preset \"Beispiel 1 – QR mit Nummer\" --set count=400\n"
                  "passermark-cli impose tickets.pdf tickets-sra3.pdf --set sheet=SRA3 \\\n"
                  "    --set step_repeat=true --set sr_sequence=true --set sr_stack=stack --set crop_marks=true"))
    s.append(P("In der Oberfläche dasselbe: Ergebnis drucken → Weitere Optionen → Nutzen → „Je Nutzen die nächste "
               "Seite“.", NOTE))

    # ------------------------------------------------------------------ 6 Fehler
    s.append(P("6 · Typische Fehler", H2))
    s.append(table([
        ["Was passiert", "Ursache / Lösung"],
        ["Überall steht „nr“ oder der Spaltenname", "Klammern fehlen: " + c("{{nr}}") + ", " + c("{{Name}}")],
        ["Jede Seite hat dieselbe Nummer", "Verteilung auf „Jede Seite bekommt den nächsten Datensatz“ stellen"],
        ["EAN-13: Fehler in der Vorschau", "Inhalt ergibt nicht 12 oder 13 Ziffern – z. B. Buchstaben im Vorsatz "
         "oder zu wenige Stellen. Vorsatz + Stellen = 12"],
        ["Code 128 lässt sich schlecht scannen", "Kasten breiter machen; nicht verkleinert drucken"],
        ["QR-Code zu fein", "Kasten größer oder Inhalt kürzer (kurze Webadresse)"],
        ["Spalte wird nicht gefunden", "Name in der ersten CSV-Zeile prüfen; Trennzeichen ; , oder Tab"],
        ["Umlaute aus der CSV falsch", "CSV als UTF-8 speichern (Excel: „CSV UTF-8“)"],
        ["Kommandozeile: Datei nicht gefunden (CSV)", c("--set csv_path=") + " mit vollem Pfad angeben"],
    ], [60 * mm, W - 60 * mm]))
    s.append(P("Ob ein Code wirklich gelesen wird, immer am Ausdruck mit einem Scanner oder Handy prüfen.", NOTE))
    return s


def on_page(canvas, doc):
    canvas.saveState()
    canvas.setFont("DV", 7.5)
    canvas.setFillColor(H.MUTED)
    canvas.drawString(20 * mm, 12 * mm, f"Passermark {__version__} · Variable Daten")
    canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, str(doc.page))
    canvas.restoreState()


if __name__ == "__main__":
    doc = SimpleDocTemplate(VDP_HOWTO, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm,
                            bottomMargin=20 * mm, title="Passermark – Variable Daten", author="Passermark",
                            subject="Anleitung Variable Daten: Oberfläche und Kommandozeile")
    doc.build(build(), onFirstPage=on_page, onLaterPages=on_page)
    print(VDP_HOWTO)
