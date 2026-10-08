# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Erzeugt pdfdruck/docs/passermark-cli-anleitung.pdf (Kommandozeile mit Fallbeispielen).

    python3 docs/make_cli_howto.py

Bei jeder neuen Version neu erzeugen; die Fallbeispiele werden in tests/test_cli_howto.py ausgeführt.
Benötigt reportlab und die Schriften DejaVu Sans / DejaVu Sans Mono.
"""
import os
import sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from pdfdruck import __version__  # noqa: E402

OUT = os.path.join(ROOT, "pdfdruck", "docs", "passermark-cli-anleitung.pdf")
FONT_DIRS = ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "C:/Windows/Fonts"]


def _font(name, file):
    for d in FONT_DIRS:
        p = os.path.join(d, file)
        if os.path.exists(p):
            pdfmetrics.registerFont(TTFont(name, p))
            return
    raise SystemExit(f"Schrift {file} nicht gefunden")


_font("DV", "DejaVuSans.ttf")
_font("DV-B", "DejaVuSans-Bold.ttf")
_font("DVM", "DejaVuSansMono.ttf")
pdfmetrics.registerFontFamily("DV", normal="DV", bold="DV-B", italic="DV", boldItalic="DV-B")

ACCENT = colors.HexColor("#c2185b")
INK = colors.HexColor("#1d1d1f")
MUTED = colors.HexColor("#5f6368")
CODEBG = colors.HexColor("#f3f3f5")

H1 = ParagraphStyle("h1", fontName="DV-B", fontSize=20, leading=25, textColor=INK, spaceAfter=4)
SUB = ParagraphStyle("sub", fontName="DV", fontSize=10.5, leading=15, textColor=MUTED, spaceAfter=14)
H2 = ParagraphStyle("h2", fontName="DV-B", fontSize=14, leading=19, textColor=ACCENT, spaceBefore=14, spaceAfter=6)
H3 = ParagraphStyle("h3", fontName="DV-B", fontSize=11, leading=15, textColor=INK, spaceBefore=10, spaceAfter=3)
BODY = ParagraphStyle("body", fontName="DV", fontSize=9.5, leading=13.5, textColor=INK, alignment=TA_LEFT,
                      spaceAfter=5)
NOTE = ParagraphStyle("note", parent=BODY, textColor=MUTED, fontSize=8.8, leading=12.5)
CELL = ParagraphStyle("cell", fontName="DV", fontSize=8.5, leading=11.5, textColor=INK)
CELLB = ParagraphStyle("cellb", parent=CELL, fontName="DV-B")
CODE = ParagraphStyle("code", fontName="DVM", fontSize=8.3, leading=11.2, textColor=INK, backColor=CODEBG,
                      borderPadding=(5, 6, 5, 6), leftIndent=6, rightIndent=6, spaceBefore=3, spaceAfter=9)


def P(t, st=BODY):
    return Paragraph(t, st)


def code(t):
    return Preformatted(t.strip("\n"), CODE)


def c(t):
    return f'<font face="DVM">{t}</font>'


def table(rows, widths, head=True):
    data = [[Paragraph(str(x), CELLB if (head and i == 0) else CELL) for x in r] for i, r in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1 if head else 0)
    st = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#d9d9de")),
          ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
          ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    if head:
        st += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ececf0"))]
    t.setStyle(TableStyle(st))
    return t


def example(title, text, cmd):
    return KeepTogether([P(title, H3), P(text), code(cmd)])


W = A4[0] - 40 * mm


def build():
    s = []
    s += [P("Passermark – Kommandozeile", H1),
          P(f"Anleitung zu {c('passermark-cli')} mit Fallbeispielen · Passermark {__version__}", SUB)]
    s.append(P("Mit der Kommandozeile laufen die schweren Funktionen von Passermark ohne Oberfläche: in Skripten, "
               "für ganze Ordner auf einmal oder später automatisch im Hintergrund. Alles, was hier steht, macht "
               "dasselbe wie die entsprechenden Dialoge im Programm."))

    # ------------------------------------------------------------------ Grundlagen
    s.append(P("1 · Aufruf", H2))
    s.append(code("passermark-cli <auftrag> <eingabe.pdf> <ausgabe.pdf> [optionen]"))
    s.append(table([
        ["System", "So heißt der Befehl"],
        ["Linux (installiert mit install.sh)", c("passermark-cli …")],
        ["Linux (AppImage)", c("./Passermark-*-x86_64.AppImage --cli …")],
        ["Windows", c('"C:\\Program Files\\Passermark\\passermark-cli.exe" …')],
        ["Windows (Suchpfad bei der Installation angehakt)", c("passermark-cli …")],
    ], [55 * mm, W - 55 * mm]))
    s.append(P("Windows: Im Setup gibt es (ab 1.7) das Häkchen „Kommandozeile passermark-cli in jeder "
               "Eingabeaufforderung verfügbar machen“. Dann genügt " + c("passermark-cli") + " – in einem "
               "<b>neu geöffneten</b> Fenster von Eingabeaufforderung oder PowerShell. Ohne Häkchen immer den vollen "
               "Pfad in Anführungszeichen angeben.", NOTE))
    s.append(Spacer(1, 6))
    s.append(P("Die Eingabedatei wird nie verändert. Die Ausgabe entsteht erst, wenn alles fertig ist – nach einem "
               "Fehler oder Abbruch bleibt keine halbe Datei liegen. Eingabe und Ausgabe dürfen nicht dieselbe "
               "Datei sein."))

    s.append(P("Die fünf Aufträge", H3))
    s.append(table([
        ["Auftrag", "Was er macht"],
        [c("cutcontour"), "Schnittlinie für Schneideplotter (Sonderfarbe CutContour), optional mit Überfüller"],
        [c("separate"), "Motive erkennen, jedes Motiv als eigene Seite"],
        [c("manip"), "CMYK-Umwandlung mit ICC-Profil und/oder Beschneiden auf ein Format"],
        [c("repair"), "Reparieren, für Druck optimieren, verkleinern, PDF/A, Passwort"],
        [c("preflight_fix"), "Ebenen festschreiben, Schriften einbetten, Text in Pfade, Transparenzen reduzieren"],
    ], [32 * mm, W - 32 * mm]))

    s.append(P("Optionen", H3))
    s.append(table([
        ["Option", "Bedeutung"],
        [c("--set name=wert"), "eine Einstellung setzen; mehrfach möglich. Zahlen, " + c("true") + "/" + c("false")
         + " und Listen werden erkannt, alles andere ist Text. Verschachtelt mit Punkt: "
         + c("--set detect.tolerance=40")],
        [c("--preset datei.json"), "Einstellungen aus einer Datei laden (siehe Abschnitt 3). " + c("--set")
         + " überschreibt einzelne Werte daraus"],
        [c('--preset "Name"'), "ein im Programm gespeichertes Preset verwenden (siehe Abschnitt 3)"],
        [c("--pages 1,3-5"), "nur diese Seiten bearbeiten (wo sinnvoll)"],
        [c("--quiet"), "keine Fortschrittsanzeige"],
        [c("--json-progress"), "Fortschritt und Ergebnis als JSON-Zeilen – für andere Programme"],
        [c("list"), "alle Aufträge anzeigen: " + c("passermark-cli list")],
        [c("settings <auftrag>"), "alle Einstellungen eines Auftrags mit Standardwerten als JSON – die Vorlage "
         "für eigene Presets"],
        [c("presets [auftrag]"), "die im Programm gespeicherten Presets auflisten"],
    ], [42 * mm, W - 42 * mm]))

    s.append(P("Rückgabewerte und Abbrechen", H3))
    s.append(P(f"{c('0')} = fertig · {c('1')} = Fehler (z. B. Datei fehlt, kein Motiv gefunden) · {c('2')} = falscher "
               f"Aufruf · {c('130')} = abgebrochen. <b>Strg+C</b> bricht sauber ab, ohne Ausgabedatei. In Skripten "
               f"kann man so auf Fehler reagieren (Abschnitt 4)."))

    # ------------------------------------------------------------------ CutContour
    s.append(PageBreak())
    s.append(P("2 · Die Aufträge mit Fallbeispielen", H2))
    s.append(P("cutcontour – Schnittlinie für den Plotter", H3))
    s.append(table([
        ["Einstellung", "Standard", "Bedeutung"],
        [c("shape"), c("contour"), "Form: " + c("contour") + " (folgt dem Motiv), " + c("rect") + ", "
         + c("rounded") + ", " + c("circle") + ", " + c("oval") + ", " + c("hexagon") + ", " + c("octagon") + ", "
         + c("heart") + ", " + c("star") + ", " + c("shield") + ", " + c("arch")],
        [c("offset_mm"), "0", "Abstand der Linie vom Motiv: + nach außen (weißer Rand), − nach innen"],
        [c("smooth_mm"), "1,5", "Glättung der Kontur (folgt dem Motiv bewusst nicht exakt)"],
        [c("bleed"), c("true"), "Überfüller erzeugen (Farbe läuft über die Schnittlinie hinaus)"],
        [c("bleed_mm"), "2", "Breite des Überfüllers"],
        [c("inner"), c("false"), "Innenkonturen (Löcher im Motiv) mitschneiden"],
        [c("width_mm") + " / " + c("height_mm"), "0", "Grundform: Größe der Schnittlinie in mm (0 = aus dem Motiv)"],
        [c("shift_x_mm") + " / " + c("shift_y_mm"), "0", "Grundform: Versatz gegenüber der Motivmitte (+ rechts / + oben)"],
        [c("corner_mm"), "3", "Eckenradius bei " + c("rounded")],
        [c("single_shape"), c("true"), "Grundform: eine Form um das ganze Motiv; " + c("false")
         + " = eine je Objekt (Aufkleberbogen)"],
        [c("per_object"), c("false"), "jedes Objekt auf eine eigene Seite"],
        [c("margin_mm"), "6", "Seitenrand bei " + c("per_object")],
        [c("spot"), c("CutContour"), "Name der Sonderfarbe – je nach RIP-Software anders"],
        [c("stroke_pt"), "0,25", "Linienstärke"],
        [c("dpi"), "200", "Genauigkeit; 300 dauert gut doppelt so lang"],
        [c("detect.*"), "", "Motiverkennung, siehe " + c("separate")],
    ], [32 * mm, 22 * mm, W - 54 * mm]))
    s.append(Spacer(1, 4))
    s.append(example("Aufkleberbogen mit Kontur und 2 mm Überfüller",
                     "Jeder Aufkleber bekommt seine Kontur, die Farbe läuft 2 mm über die Linie – kein weißer "
                     "Blitzer beim Schneiden.",
                     "passermark-cli cutcontour bogen.pdf bogen-cut.pdf --set bleed_mm=2"))
    s.append(example("Logo mit Rechteck 80 × 50 mm, ohne Überfüller",
                     "Feste Größe der Schnittlinie, mittig auf dem ganzen Logo – auch wenn das Logo aus mehreren "
                     "Teilen besteht.",
                     "passermark-cli cutcontour logo.pdf logo-cut.pdf \\\n"
                     "    --set shape=rect --set width_mm=80 --set height_mm=50 --set bleed=false"))
    s.append(example("Runde Aufkleber Ø 60 mm auf einem Bogen",
                     "Jeder Aufkleber einzeln (" + c("single_shape=false") + "), jeder Kreis exakt 60 mm.",
                     "passermark-cli cutcontour bogen.pdf rund.pdf \\\n"
                     "    --set shape=circle --set width_mm=60 --set height_mm=60 --set single_shape=false"))
    s.append(example("3 mm weißer Rand um das Motiv",
                     "Die Kontur liegt 3 mm außerhalb, ohne Überfüller bleibt der Rand weiß.",
                     "passermark-cli cutcontour logo.pdf logo-rand.pdf --set offset_mm=3 --set bleed=false"))
    s.append(example("Jeder Aufkleber auf einer eigenen Seite",
                     "Praktisch für Einzelaufträge oder wenn der Plotter Seite für Seite schneidet.",
                     "passermark-cli cutcontour bogen.pdf einzeln.pdf --set per_object=true --set margin_mm=5"))
    s.append(example("Andere Sonderfarbe für die RIP-Software",
                     "Manche Programme erwarten einen anderen Namen als „CutContour“, z. B. „Thru-cut“.",
                     "passermark-cli cutcontour bogen.pdf bogen-cut.pdf --set spot=Thru-cut"))
    s.append(example("Nur bestimmte Seiten",
                     "Seiten 1 sowie 3 bis 5 bearbeiten.",
                     "passermark-cli cutcontour mappe.pdf mappe-cut.pdf --pages 1,3-5"))

    # ------------------------------------------------------------------ separate
    s.append(P("separate – Motive als einzelne Seiten", H3))
    s.append(table([
        ["Einstellung", "Standard", "Bedeutung"],
        [c("margin_mm"), "0", "Rand um jedes Motiv (negativ = nach innen)"],
        [c("detect.mode"), c("auto"), c("auto") + ", " + c("transparent") + " (freigestellt) oder " + c("color")
         + " (einfarbiger Hintergrund)"],
        [c("detect.tolerance"), "28", "wie stark sich das Motiv vom Hintergrund unterscheiden muss (0–255); höher = "
         "unempfindlicher gegen Flecken"],
        [c("detect.min_size_mm"), "5", "kleinere Teile gelten als Staub"],
        [c("detect.gap_mm"), "1", "Teile, die näher beisammen liegen, gehören zu einem Motiv"],
    ], [38 * mm, 22 * mm, W - 60 * mm]))
    s.append(Spacer(1, 4))
    s.append(example("Scan mit mehreren Motiven zerlegen",
                     "Jedes Motiv wird eine Seite, mit 3 mm Rand.",
                     "passermark-cli separate scan.pdf motive.pdf --set margin_mm=3"))
    s.append(example("Fleckiger Hintergrund (z. B. Altpapier)",
                     "Höhere Toleranz und größere Mindestgröße – Flecken werden nicht mehr als Motiv erkannt.",
                     "passermark-cli separate scan.pdf motive.pdf \\\n"
                     "    --set detect.tolerance=40 --set detect.min_size_mm=10"))

    # ------------------------------------------------------------------ manip
    s.append(P("manip – CMYK-Umwandlung und Beschneiden", H3))
    s.append(table([
        ["Einstellung", "Standard", "Bedeutung"],
        [c("crop"), c("false"), "auf ein Format beschneiden (Überstand beidseitig gleich)"],
        [c("crop_size"), c("A4"), "A0–A7, B4, B5, C4–C6, DL, SRA3, A3+, Letter, Legal, Tabloid, „Visitenkarte "
         "85×55“, „Visitenkarte 90×50“, „Quadrat 210“, „Quadrat 148“ oder " + c("custom")],
        [c("crop_w_mm") + " / " + c("crop_h_mm"), "210 / 297", "Maße bei " + c("custom")],
        [c("crop_follow"), c("true"), "Hoch-/Querformat der Seite folgen"],
        [c("cmyk"), c("false"), "nach CMYK umwandeln (braucht Ghostscript)"],
        [c("target"), "", "Pfad zum CMYK-Zielprofil (.icc), z. B. ISOcoated_v2_eci.icc"],
        [c("cmyk_mode"), c("rgb_only"), c("rgb_only") + " (vorhandenes CMYK bleibt), " + c("all") + " (auch CMYK "
         "umrechnen, Quellprofil in " + c("source") + "), " + c("gray")],
        [c("intent"), c("relative"), c("perceptual") + ", " + c("relative") + ", " + c("saturation") + ", "
         + c("absolute")],
        [c("gray_to_k"), c("true"), "Grau/Schwarz nur mit K drucken"],
    ], [32 * mm, 22 * mm, W - 54 * mm]))
    s.append(Spacer(1, 4))
    s.append(example("Alle Seiten auf A5 beschneiden",
                     "", "passermark-cli manip flyer.pdf flyer-a5.pdf --set crop=true --set crop_size=A5"))
    s.append(example("Eigenes Format 100 × 150 mm",
                     "", "passermark-cli manip foto.pdf foto-10x15.pdf \\\n"
                         "    --set crop=true --set crop_size=custom --set crop_w_mm=100 --set crop_h_mm=150"))
    s.append(example("Druckdaten nach CMYK (ISO Coated v2)",
                     "Das Profil gibt es kostenlos bei der ECI (eci.org). Pfad an deinen Speicherort anpassen.",
                     "passermark-cli manip druck.pdf druck-cmyk.pdf \\\n"
                     "    --set cmyk=true --set target=/pfad/ISOcoated_v2_eci.icc"))

    # ------------------------------------------------------------------ repair
    s.append(P("repair – Reparieren, optimieren, PDF/A, Passwort", H3))
    s.append(table([
        ["Einstellung", "Standard", "Bedeutung"],
        [c("mode"), c("print"), c("repair") + " (nur reparieren), " + c("print") + " (für Weitergabe und Druck, "
         "Schriften einbetten), " + c("screen") + " (für Mail verkleinern, 150 dpi), " + c("pdfa")
         + " (PDF/A-2b, Archiv/Behörden)"],
        [c("password"), "", "Passwort der Eingabedatei, falls geschützt"],
        [c("new_password"), "", "neues Passwort für die Ausgabe (leer = keins); nicht bei " + c("pdfa")
         + " – PDF/A verbietet Verschlüsselung, das Passwort wird dann weggelassen"],
        [c("allow_print"), c("true"), "mit Passwort: Drucken trotzdem erlauben"],
    ], [32 * mm, 22 * mm, W - 54 * mm]))
    s.append(Spacer(1, 4))
    s.append(example("Kaputtes PDF für den Druck aufbereiten", "",
                     "passermark-cli repair kaputt.pdf ok.pdf --set mode=print"))
    s.append(example("Für Mail verkleinern", "", "passermark-cli repair katalog.pdf katalog-klein.pdf --set mode=screen"))
    s.append(example("Archivieren als PDF/A", "Für Archiv, Behörden und E-Rechnungs-Anhänge.",
                     "passermark-cli repair vertrag.pdf vertrag-a.pdf --set mode=pdfa"))
    s.append(example("Mit Passwort schützen", "Öffnen nur mit Passwort, Drucken bleibt erlaubt.",
                     "passermark-cli repair angebot.pdf angebot-geschuetzt.pdf --set new_password=geheim"))

    # ------------------------------------------------------------------ preflight_fix
    s.append(P("preflight_fix – Problem-PDFs druckfest machen", H3))
    s.append(table([
        ["Einstellung", "Standard", "Bedeutung"],
        [c("fix"), c("flatten_layers"), c("flatten_layers") + " (Ebenen festschreiben – gedruckt wird genau das "
         "Sichtbare), " + c("embed_fonts") + ", " + c("outline_text") + " (Text in Pfade), "
         + c("flatten_transparency")],
        [c("font_map"), "{}", "bei " + c("embed_fonts") + ": Ersatzschriften {Schriftname: Pfad}"],
        [c("dpi"), "300", "bei " + c("flatten_transparency") + ": Auflösung der gerasterten Bereiche"],
    ], [30 * mm, 32 * mm, W - 62 * mm]))
    s.append(Spacer(1, 4))
    s.append(example("Plan mit Ebenen: nur das Sichtbare drucken", "",
                     "passermark-cli preflight_fix plan.pdf plan-fest.pdf --set fix=flatten_layers"))
    s.append(example("Alter RIP: Transparenzen reduzieren", "",
                     "passermark-cli preflight_fix plakat.pdf plakat-flach.pdf \\\n"
                     "    --set fix=flatten_transparency --set dpi=300"))
    s.append(P(f"{c('embed_fonts')}, {c('outline_text')}, {c('flatten_transparency')}, {c('repair')} und die "
               f"CMYK-Umwandlung brauchen Ghostscript. Windows-Setup und AppImage bringen es mit; bei der "
               f"Linux-Installation installiert es {c('install.sh')}.", NOTE))

    # ------------------------------------------------------------------ Presets
    s.append(PageBreak())
    s.append(P("3 · Presets: Einstellungen als Datei", H2))
    s.append(P("Wer dieselben Einstellungen immer wieder braucht, legt sie einmal in einer Datei ab. Die Vorlage mit "
               "allen Einstellungen und ihren Standardwerten liefert " + c("settings") + "."))
    s.append(code("passermark-cli settings cutcontour > sticker.json"))
    s.append(P("Dann die Datei in einem Texteditor anpassen – nur die Werte hinter dem Doppelpunkt ändern:"))
    s.append(code('''{
  "job": "cutcontour",
  "settings": {
    "shape": "rounded",
    "corner_mm": 4,
    "offset_mm": 2,
    "bleed_mm": 2,
    ...
  }
}'''))
    s.append(P("Verwenden – einzelne Werte lassen sich trotzdem noch mit " + c("--set") + " ändern:"))
    s.append(code("passermark-cli cutcontour bogen.pdf bogen-cut.pdf --preset sticker.json\n"
                  "passermark-cli cutcontour bogen.pdf bogen-cut.pdf --preset sticker.json --set bleed_mm=3"))
    s.append(P("Ein Preset gehört immer zu einem Auftrag – ein CutContour-Preset kann nicht für " + c("separate")
               + " verwendet werden. Werte mit Sonderzeichen (z. B. " + c("font_map") + " mit Windows-Pfaden) "
               "trägt man am einfachsten im Preset statt mit " + c("--set") + " ein.", NOTE))

    s.append(P("Presets aus dem Programm", H3))
    s.append(P("Einfacher geht es im Programm selbst: In den Fenstern für CutContour, CMYK/Beschneiden und im "
               "Druckdialog gibt es oben die Zeile <b>Preset</b>. Einstellungen wie gewünscht setzen, "
               "<b>Speichern…</b> und einen Namen vergeben. Die Kommandozeile findet das Preset dann über seinen "
               "Namen – ohne Pfad:"))
    s.append(code('passermark-cli presets cutcontour\n'
                  'passermark-cli cutcontour bogen.pdf bogen-cut.pdf --preset "Sticker rund"'))
    s.append(P("Abgelegt sind die Presets als JSON-Dateien je Auftrag – unter Linux in "
               + c("~/.config/passermark/presets/") + ", unter Windows in " + c("%APPDATA%\\Passermark\\presets\\")
               + ". Im Programm: Arbeitsbereich <b>Automatisierung</b> → <b>Presets</b> öffnet den Ordner. "
               "Druck-Presets (Broschüre, Poster, Nutzen) gelten nur im Druckdialog.", NOTE))

    # ------------------------------------------------------------------ Stapel
    s.append(P("4 · Ganze Ordner auf einmal", H2))
    s.append(P("Linux (Terminal): alle PDFs aus " + c("eingang") + " schneiden, Ergebnisse nach " + c("fertig")
               + ", Fehler werden gemeldet."))
    s.append(code('''mkdir -p fertig
for f in eingang/*.pdf; do
    passermark-cli cutcontour "$f" "fertig/$(basename "$f" .pdf)-cut.pdf" \\
        --preset sticker.json --quiet || echo "FEHLER: $f"
done'''))
    s.append(P("Windows (PowerShell):"))
    s.append(code('''$cli = "C:\\Program Files\\Passermark\\passermark-cli.exe"
New-Item -ItemType Directory -Force -Path fertig | Out-Null
Get-ChildItem eingang\\*.pdf | ForEach-Object {
    & $cli cutcontour $_.FullName "fertig\\$($_.BaseName)-cut.pdf" `
        --preset sticker.json --quiet
    if ($LASTEXITCODE -ne 0) { Write-Host "FEHLER: $($_.Name)" }
}'''))

    # ------------------------------------------------------------------ Tipps
    s.append(P("5 · Tipps und Fehler", H2))
    s.append(table([
        ["Meldung / Problem", "Lösung"],
        ["Kein Motiv gefunden", "Toleranz senken (" + c("--set detect.tolerance=15") + ") oder Modus festlegen ("
         + c("--set detect.mode=color") + ")"],
        ["Flecken werden als Motiv erkannt", "Toleranz erhöhen, " + c("detect.min_size_mm") + " vergrößern"],
        ["Teile eines Logos bekommen getrennte Konturen", c("detect.gap_mm") + " erhöhen, z. B. 3"],
        ["Dauert lange", c("dpi") + " auf 200 lassen; 300 dauert gut doppelt so lang. Große Seiten mit vielen "
         "Objekten rechnet Passermark automatisch auf mehreren Rechenkernen"],
        ["Rechner soll nebenbei frei bleiben", "Rechenkerne begrenzen: Linux " + c("PASSERMARK_WORKERS=2 passermark-cli …")
         + ", Windows (PowerShell) " + c("$env:PASSERMARK_WORKERS=2") + " davor; 1 = nicht parallel"],
        ["Preset ist für „…“", "Das Preset gehört zu einem anderen Auftrag"],
        ["Wert wird als Text statt Zahl gelesen", "Dezimalpunkt verwenden: " + c("bleed_mm=2.5") + " (nicht 2,5)"],
        ["Leerzeichen im Dateinamen", "Namen in Anführungszeichen setzen: " + c('"mein bogen.pdf"')],
    ], [60 * mm, W - 60 * mm]))

    s.append(P("6 · Ausblick", H2))
    s.append(P("Die Kommandozeile wächst mit Passermark. Mit den nächsten Versionen kommen dazu – jeweils mit "
               "Fallbeispielen in dieser Anleitung:"))
    s.append(table([
        ["Version", "Neu in der Kommandozeile"],
        ["1.8", "Broschüren und Bindungen: Sammelheftung, Stapelheftung, gruppierte Lagen; Ausschießen allgemein"],
        ["1.9", "Variable Daten: Nummerierung, QR- und Barcodes, Datenquelle CSV; Mehrfachnutzen mit eigenem Code "
                "je Nutzen"],
        ["1.10", "Projektordner (Watcher): Datei in einen Ordner werfen – fertiges, gedrucktes oder gespeichertes "
                 "Ergebnis kommt heraus, ein Preset je Ordner"],
    ], [20 * mm, W - 20 * mm]))
    return s


def on_page(canvas, doc):
    canvas.saveState()
    canvas.setFont("DV", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(20 * mm, 12 * mm, f"Passermark {__version__} · Kommandozeile")
    canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, str(doc.page))
    canvas.restoreState()


if __name__ == "__main__":
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm,
                            bottomMargin=20 * mm, title="Passermark – Kommandozeile", author="Passermark",
                            subject="Anleitung passermark-cli")
    doc.build(build(), onFirstPage=on_page, onLaterPages=on_page)
    print(OUT)
