# SPDX-License-Identifier: GPL-3.0-or-later
# pdfToolkit – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Deutsche Bezeichnungen für typische (englische) Treiberoptionen und -werte.

Viele Hersteller-PPDs (z. B. Epson escpr2) liefern nur Englisch bzw. interne Kürzel.
Unbekanntes bleibt unverändert – es geht nichts verloren, der Originalwert steht im Tooltip.
"""
import re

from .l10n import current, tr


def _norm(s: str) -> str:
    return re.sub(r"[\s_\-./]+", "", (s or "").lower())


OPTION_DE = {
    "papersource": "Papierzufuhr", "mediasource": "Papierzufuhr", "inputslot": "Papierzufuhr",
    "source": "Papierzufuhr", "mediasize": "Papierformat", "pagesize": "Papierformat",
    "papersize": "Papierformat", "printquality": "Druckqualität / Papiersorte", "mediatype": "Medientyp",
    "papertype": "Papiersorte", "duplex": "Beidseitig", "duplextumble": "Beidseitig",
    "2sidedprinting": "Beidseitig", "twosided": "Beidseitig", "grayscale": "Farbe / Graustufen",
    "colormode": "Farbmodus", "colormodel": "Farbmodus", "ink": "Farbe / Graustufen",
    "brightness": "Helligkeit", "contrast": "Kontrast", "saturation": "Sättigung",
    "resolution": "Auflösung", "outputbin": "Ausgabefach", "collate": "Sortieren",
    "staple": "Heften", "stapling": "Heften", "punch": "Lochen", "holepunch": "Lochen",
    "booklet": "Broschüre", "finisher": "Finisher", "quality": "Qualität",
    "tonersave": "Tonersparmodus", "inksave": "Tintensparmodus",
}

CHOICE_DE = {
    "auto": "Automatisch", "automatic": "Automatisch", "autoselect": "Automatisch",
    "rearpaperfeed": "Hintere Papierzufuhr", "rear": "Hintere Papierzufuhr",
    "rearfeed": "Hintere Papierzufuhr", "cassette": "Papierkassette", "papercassette": "Papierkassette",
    "manual": "Manuelle Zufuhr", "manualfeed": "Manuelle Zufuhr", "multipurpose": "Mehrzweckfach",
    "multipurposetray": "Mehrzweckfach", "mptray": "Mehrzweckfach", "bypass": "Mehrzweckfach",
    "none": "Aus", "off": "Aus", "on": "Ein", "true": "Ja", "false": "Nein",
    "duplexnotumble": "Beidseitig, lange Kante", "duplextumble": "Beidseitig, kurze Kante",
    "longedge": "Beidseitig, lange Kante", "shortedge": "Beidseitig, kurze Kante",
    "color": "Farbe", "colour": "Farbe", "rgb": "Farbe", "cmyk": "Farbe",
    "mono": "Graustufen", "monochrome": "Graustufen", "gray": "Graustufen", "grayscale": "Graustufen",
    "black": "Schwarzweiß", "draft": "Entwurf", "normal": "Normal", "high": "Hoch", "best": "Beste",
    "fine": "Fein", "standard": "Standard",
    "main": "Haupteinzug", "maintray": "Haupteinzug", "top": "Oberes Fach", "bottom": "Unteres Fach",
    "middle": "Mittleres Fach", "photo": "Fotofach", "envelope": "Umschlag",
    "faceup": "Schriftseite nach oben", "facedown": "Schriftseite nach unten",
    "stationery": "Normalpapier", "stationeryletterhead": "Briefpapier", "stationeryinkjet": "Inkjet-Papier",
    "stationerycoated": "Gestrichenes Papier", "photographic": "Fotopapier",
    "photographicglossy": "Fotopapier glänzend", "photographicmatte": "Fotopapier matt",
    "photographicsemigloss": "Fotopapier seidenmatt", "photographichighgloss": "Fotopapier hochglänzend",
    "cardstock": "Karton", "labels": "Etiketten", "transparency": "Folie", "envelopes": "Umschläge",
    "onesided": "Einseitig", "twosidedlongedge": "Beidseitig, lange Kante",
    "twosidedshortedge": "Beidseitig, kurze Kante",
}

# Epson-Medienkürzel (MediaType z. B. PLAIN_HIGH)
EPSON_MEDIA = {
    "PLAIN": "Normalpapier", "LETTERHEAD": "Briefkopfpapier", "SFINE": "Matt, Superfine",
    "PMMATT": "Premium Matt", "PLATINA": "Ultra Glossy (Platinum)", "PMPHOTO": "Premium Glossy",
    "PSGLOS": "Premium Semigloss", "LCPP": "Photo Quality Ink Jet", "ENV": "Umschlag",
    "PHOTO": "Fotopapier", "THICK": "Dickes Papier", "LABEL": "Etiketten",
}
EPSON_QUAL = {"HIGH": "hohe Qualität", "NORMAL": "Standard", "DRAFT": "Entwurf"}


# Endverarbeitung (Canon imagePRESS / imageRUNNER, Fiery, allgemein): Wort-/Phrasen-Übersetzung
FINISH_RX = re.compile(r"stapl|saddle|punch|hole|fold|trim|booklet|finish|stack|offset|insert|bind|"
                       r"cnsaddle|cnpunch|cnfold|cntrim|heft|loch|falz|beschnitt|broschüre", re.I)
# (Muster im englischen Treibertext, {Sprache: Ersatz}) – längere Phrasen zuerst
PHRASES = [
    (r"accordion\s*z[- ]?fold", {"de": "Leporellofalz", "fr": "Pli accordéon", "es": "Plegado en acordeón", "hu": "Harmonikahajtás"}),
    (r"double\s*parallel\s*fold", {"de": "Doppelparallelfalz", "fr": "Pli double parallèle", "es": "Plegado paralelo doble", "hu": "Dupla párhuzamos hajtás"}),
    (r"saddle\s*stitch(ing)?", {"de": "Sattelheftung", "fr": "Piqûre à cheval", "es": "Grapado por el lomo", "hu": "Gerinctűzés"}),
    (r"saddle\s*fold|half\s*fold", {"de": "Mittenfalz", "fr": "Pli central", "es": "Plegado por la mitad", "hu": "Középhajtás"}),
    (r"tri[- ]?fold|letter\s*fold|c[- ]?fold", {"de": "Wickelfalz", "fr": "Pli roulé", "es": "Plegado tríptico", "hu": "Levélhajtás"}),
    (r"z[- ]?fold", {"de": "Z-Falz", "fr": "Pli en Z", "es": "Plegado en Z", "hu": "Z-hajtás"}),
    (r"gate\s*fold", {"de": "Fensterfalz", "fr": "Pli fenêtre", "es": "Plegado de ventana", "hu": "Ablakhajtás"}),
    (r"perfect\s*bind(ing|er)?", {"de": "Klebebindung", "fr": "Reliure dos carré collé", "es": "Encuadernación encolada", "hu": "Ragasztókötés"}),
    (r"high[- ]capacity\s*stacker", {"de": "Großraumstapler", "fr": "Réceptacle grande capacité", "es": "Apilador de alta capacidad", "hu": "Nagy kapacitású gyűjtő"}),
    (r"two[- ]knife", {"de": "Zwei-Messer", "fr": "Deux lames", "es": "Dos cuchillas", "hu": "Kétkéses"}),
    (r"front[- ]edge\s*trim(ming)?", {"de": "Vorderkantenbeschnitt", "fr": "Massicotage avant", "es": "Recorte frontal", "hu": "Előélvágás"}),
    (r"3[- ]side\s*cut|three[- ]side\s*trim", {"de": "Dreiseitenbeschnitt", "fr": "Coupe trois côtés", "es": "Corte trilateral", "hu": "Háromoldalú vágás"}),
    (r"top\s*left", {"de": "oben links", "fr": "en haut à gauche", "es": "arriba a la izquierda", "hu": "bal felső"}),
    (r"top\s*right", {"de": "oben rechts", "fr": "en haut à droite", "es": "arriba a la derecha", "hu": "jobb felső"}),
    (r"bottom\s*left", {"de": "unten links", "fr": "en bas à gauche", "es": "abajo a la izquierda", "hu": "bal alsó"}),
    (r"bottom\s*right", {"de": "unten rechts", "fr": "en bas à droite", "es": "abajo a la derecha", "hu": "jobb alsó"}),
    (r"output\s*tray", {"de": "Ausgabefach", "fr": "Bac de sortie", "es": "Bandeja de salida", "hu": "Kimeneti tálca"}),
    (r"paper\s*deck|pod\s*deck", {"de": "Papiermagazin", "fr": "Magasin papier", "es": "Depósito de papel", "hu": "Papírtár"}),
    (r"hole\s*punch(ing)?", {"de": "Lochung", "fr": "Perforation", "es": "Perforación", "hu": "Lyukasztás"}),
    (r"(\d)\s*holes?", {"de": r"\1-fach", "fr": r"\1 trous", "es": r"\1 agujeros", "hu": r"\1 lyuk"}),
    (r"stapl(e|ing|er)", {"de": "Heftung", "fr": "Agrafage", "es": "Grapado", "hu": "Tűzés"}),
    (r"punch(ing|er)?", {"de": "Lochung", "fr": "Perforation", "es": "Perforación", "hu": "Lyukasztás"}),
    (r"booklet", {"de": "Broschüre", "fr": "Livret", "es": "Folleto", "hu": "Füzet"}),
    (r"fold(ing|er)?", {"de": "Falz", "fr": "Pliage", "es": "Plegado", "hu": "Hajtás"}),
    (r"trim(ming|mer)?", {"de": "Beschnitt", "fr": "Massicotage", "es": "Recorte", "hu": "Vágás"}),
    (r"stacker", {"de": "Stapler", "fr": "Réceptacle", "es": "Apilador", "hu": "Gyűjtő"}),
    (r"inserter|insertion", {"de": "Einschießen", "fr": "Insertion", "es": "Inserción", "hu": "Beillesztés"}),
    (r"offset", {"de": "Versatz", "fr": "Décalage", "es": "Desplazamiento", "hu": "Eltolás"}),
    (r"cover", {"de": "Umschlag", "fr": "Couverture", "es": "Cubierta", "hu": "Borító"}),
    (r"double", {"de": "doppelt", "fr": "double", "es": "doble", "hu": "dupla"}),
    (r"single", {"de": "einfach", "fr": "simple", "es": "simple", "hu": "egyszeres"}),
    (r"corner", {"de": "Ecke", "fr": "coin", "es": "esquina", "hu": "sarok"}),
    (r"center|centre", {"de": "Mitte", "fr": "centre", "es": "centro", "hu": "közép"}),
    (r"left", {"de": "links", "fr": "gauche", "es": "izquierda", "hu": "bal"}),
    (r"right", {"de": "rechts", "fr": "droite", "es": "derecha", "hu": "jobb"}),
    (r"top", {"de": "oben", "fr": "haut", "es": "arriba", "hu": "felül"}),
    (r"bottom", {"de": "unten", "fr": "bas", "es": "abajo", "hu": "alul"}),
    (r"\bon\b", {"de": "ein", "fr": "activé", "es": "activado", "hu": "be"}),
    (r"\boff\b", {"de": "aus", "fr": "désactivé", "es": "desactivado", "hu": "ki"}),
    (r"\bnone\b", {"de": "keine", "fr": "aucun", "es": "ninguno", "hu": "nincs"}),
    (r"\bauto(matic)?\b", {"de": "automatisch", "fr": "automatique", "es": "automático", "hu": "automatikus"}),
]


def _phrase_de(text: str) -> str:
    """Englischen Finisher-Text in die Oberflächensprache übertragen (Englisch: Original behalten)."""
    lang = current()
    out = text
    if lang != "en":
        for pat, reps in PHRASES:
            rep = reps.get(lang, reps["de"])
            out = re.sub(r"(?<![A-Za-zÄÖÜäöüß])" + pat + r"(?![A-Za-zÄÖÜäöüß])", rep, out, flags=re.I)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out[:1].upper() + out[1:] if out else text


# Deutsche Begriffe aus deutsch installierten Treibern (PPD) -> Oberflächensprache (längere zuerst)
DE_DRIVER = [
    ("Hintere Papierzufuhr", {"en": "Rear paper feed", "hu": "Hátsó papíradagoló", "es": "Alimentación trasera", "fr": "Alimentation arrière"}),
    ("Papierkassette", {"en": "Paper cassette", "hu": "Papírkazetta", "es": "Casete de papel", "fr": "Cassette papier"}),
    ("Papierformat", {"en": "Paper size", "hu": "Papírméret", "es": "Tamaño de papel", "fr": "Format du papier"}),
    ("Papierquelle", {"en": "Paper source", "hu": "Papírforrás", "es": "Origen del papel", "fr": "Source du papier"}),
    ("Papierzufuhr", {"en": "Paper feed", "hu": "Papíradagolás", "es": "Alimentación de papel", "fr": "Alimentation papier"}),
    ("Papiertyp", {"en": "Paper type", "hu": "Papírtípus", "es": "Tipo de papel", "fr": "Type de papier"}),
    ("Papiersorte", {"en": "Paper type", "hu": "Papírtípus", "es": "Tipo de papel", "fr": "Type de papier"}),
    ("Normalpapier", {"en": "Plain paper", "hu": "Normál papír", "es": "Papel normal", "fr": "Papier ordinaire"}),
    ("Fotopapier", {"en": "Photo paper", "hu": "Fotópapír", "es": "Papel fotográfico", "fr": "Papier photo"}),
    ("Druckqualität", {"en": "Print quality", "hu": "Nyomtatási minőség", "es": "Calidad de impresión", "fr": "Qualité d'impression"}),
    ("Qualität", {"en": "Quality", "hu": "Minőség", "es": "Calidad", "fr": "Qualité"}),
    ("Heftkante", {"en": "Binding edge", "hu": "Kötési él", "es": "Borde de encuadernación", "fr": "Bord de reliure"}),
    ("Lange Kante", {"en": "Long edge", "hu": "Hosszú él", "es": "Lado largo", "fr": "Grand côté"}),
    ("Kurze Kante", {"en": "Short edge", "hu": "Rövid él", "es": "Lado corto", "fr": "Petit côté"}),
    ("Beidseitig", {"en": "Two-sided", "hu": "Kétoldalas", "es": "Doble cara", "fr": "Recto verso"}),
    ("Einseitig", {"en": "One-sided", "hu": "Egyoldalas", "es": "Una cara", "fr": "Recto"}),
    ("Graustufen", {"en": "Grayscale", "hu": "Szürkeárnyalatos", "es": "Escala de grises", "fr": "Niveaux de gris"}),
    ("Schwarzweiß", {"en": "Black & white", "hu": "Fekete-fehér", "es": "Blanco y negro", "fr": "Noir et blanc"}),
    ("Farbmodus", {"en": "Color mode", "hu": "Színmód", "es": "Modo de color", "fr": "Mode couleur"}),
    ("Farbe", {"en": "Color", "hu": "Színes", "es": "Color", "fr": "Couleur"}),
    ("Automatisch", {"en": "Automatic", "hu": "Automatikus", "es": "Automático", "fr": "Automatique"}),
    ("Randlos", {"en": "Borderless", "hu": "Keret nélküli", "es": "Sin bordes", "fr": "Sans bordure"}),
    ("randlos", {"en": "borderless", "hu": "keret nélküli", "es": "sin bordes", "fr": "sans bordure"}),
    ("Umschlag", {"en": "Envelope", "hu": "Boríték", "es": "Sobre", "fr": "Enveloppe"}),
    ("US Lang", {"en": "US Legal", "hu": "US Legal", "es": "US Legal", "fr": "US Legal"}),
    ("Zoll", {"en": "in", "hu": "hüvelyk", "es": "pulg.", "fr": "po"}),
    ("breit", {"en": "wide", "hu": "széles", "es": "ancho", "fr": "large"}),
    ("Entwurf", {"en": "Draft", "hu": "Vázlat", "es": "Borrador", "fr": "Brouillon"}),
    ("Hoch", {"en": "High", "hu": "Magas", "es": "Alta", "fr": "Élevée"}),
    ("Fein", {"en": "Fine", "hu": "Finom", "es": "Fina", "fr": "Fine"}),
    ("Glänzend", {"en": "Glossy", "hu": "Fényes", "es": "Brillante", "fr": "Brillant"}),
    ("glänzend", {"en": "glossy", "hu": "fényes", "es": "brillante", "fr": "brillant"}),
    ("Matt", {"en": "Matte", "hu": "Matt", "es": "Mate", "fr": "Mat"}),
    ("Aus", {"en": "Off", "hu": "Ki", "es": "Desactivado", "fr": "Désactivé"}),
    ("Ein", {"en": "On", "hu": "Be", "es": "Activado", "fr": "Activé"}),
    ("Kassette", {"en": "Cassette", "hu": "Kazetta", "es": "Casete", "fr": "Cassette"}),
    ("Fach", {"en": "Tray", "hu": "Tálca", "es": "Bandeja", "fr": "Bac"}),
]
_DE_HINT = re.compile(r"[äöüÄÖÜß]|Randlos|randlos|Zoll|Umschlag|Papier|Kante|Fach|Kassette|seitig|Graustufen|Farbe|"
                      r"Automatisch|Qualität|Entwurf|\bAus\b|\bEin\b|\bDIN\b|US Lang|breit|Matt")


def localize_driver(text: str) -> str:
    """Deutsche Treibertexte in die Oberflächensprache übertragen (Deutsch: unverändert)."""
    lang = current()
    if lang == "de" or not text or not _DE_HINT.search(text):
        return text
    out = re.sub(r"\bDIN\s+(?=[A-C]\d)", "", text)
    for de, rep in DE_DRIVER:
        out = re.sub(r"(?<![A-Za-zÄÖÜäöüß])" + re.escape(de) + r"(?![A-Za-zÄÖÜäöüß])", rep.get(lang, rep["en"]), out)
    return out


def is_finishing(keyword: str, text: str) -> bool:
    return bool(FINISH_RX.search(f"{keyword} {text}"))


def option_text(keyword: str, text: str) -> str:
    de = OPTION_DE.get(_norm(text)) or OPTION_DE.get(_norm(keyword))
    if de:
        return localize_driver(text) if (current() == "en" and text) else tr(de)
    if is_finishing(keyword, text):
        return _phrase_de(text or keyword)
    return localize_driver(text)


def choice_text(keyword: str, value: str, text: str, option_label: str = "") -> str:
    if (is_finishing(keyword, option_label) or FINISH_RX.search(text or "")) and not CHOICE_DE.get(_norm(text or value)):
        return _phrase_de(text or value)
    for cand in (text, value):
        de = CHOICE_DE.get(_norm(cand))
        if de:
            return tr(de)
    m = re.fullmatch(r"(?:tray|fach)\s*_?(\d+)", value, re.I) or re.fullmatch(r"(?:tray|fach)\s*(\d+)", text or "", re.I)
    if m:
        return tr("Fach {0}").format(m.group(1))
    m = re.fullmatch(r"(?:cas|cassette|cst)\s*_?(\d+)", value, re.I) or \
        re.fullmatch(r"(?:paper\s*)?cassette\s*(\d+)", text or "", re.I)
    if m:
        return tr("Kassette {0}").format(m.group(1))
    m = re.fullmatch(r"([A-Z]+)_(HIGH|NORMAL|DRAFT)", value)
    if m and m.group(1) in EPSON_MEDIA:
        return f"{tr(EPSON_MEDIA[m.group(1)])} – {tr(EPSON_QUAL[m.group(2)])}"
    if (text or "") in ("", value):
        # Kürzel wie A3+, TA4 (T = randlos bei Epson)
        m = re.fullmatch(r"T(A\d\+?|Letter|4X6FULL|2L|L|8x10|4X7|Postcard)", value)
        if m:
            return f"{m.group(1)} {tr('randlos')}"
    return localize_driver(text or value)
