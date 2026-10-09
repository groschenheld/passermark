# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Variable Daten: Felder (Text, Nummer, QR-Code, Code 128, EAN-13) auf die Seiten legen – je Datensatz eine Kopie.

Datensätze kommen aus einer CSV-Datei (Zeile = Kopie) oder aus einer reinen Nummerierung (Anzahl). Inhalte sind
Vorlagen mit Platzhaltern: {{Spaltenname}}, {{nr}} (Nummer samt Format/Prüfziffer), {{i}} (laufende Nummer ab 1).
Alles wird als Vektor gezeichnet (Schrift, Balken, QR-Module) und als Überlagerung auf die Seite gelegt –
die Vorlage selbst bleibt unverändert. Koordinaten in mm ab der linken oberen Ecke der sichtbaren Seite.
"""
from __future__ import annotations

import csv
import io
import os
import re
from dataclasses import asdict, dataclass, field

from .l10n import tr

MM = 72.0 / 25.4
KINDS = ("text", "qr", "code128", "ean13")
STD_FONTS = ("Helvetica", "Helvetica-Bold", "Times-Roman", "Times-Bold", "Courier", "Courier-Bold")
CHECKS = ("none", "luhn", "mod11", "ean")
PH = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
MAX_RECORDS = 100000


@dataclass
class VdpField:
    kind: str = "text"            # text | qr | code128 | ean13
    content: str = "{{nr}}"       # Vorlage mit Platzhaltern
    x_mm: float = 10.0            # linke obere Ecke des Feldes, ab links oben auf der Seite
    y_mm: float = 10.0
    w_mm: float = 40.0
    h_mm: float = 10.0
    font: str = "Helvetica"       # Standardschrift oder Pfad zu einer TTF-Datei
    size_pt: float = 12.0
    color: str = "#000000"
    align: str = "left"           # left | center | right
    rotate: int = 0               # 0 | 90 | 180 | 270 (gegen den Uhrzeigersinn)
    pages: str = ""               # nur auf diesen Seiten der Vorlage, z. B. "1", "1,3-4", "ungerade", "gerade",
                                  # "ungerade 1-50" (leer = alle)
    qr_type: str = "text"         # QR: text = Inhalt wie eingegeben; vcard, wifi, email, url, phone, sms, event, geo =
                                  # Inhalt aus den Spalten der Datentabelle zusammengesetzt (siehe datakinds)
    quiet: bool = True            # QR/Code 128: weiße Ruhezone im Feld freihalten (für sicheres Scannen)
    qr_map: dict = field(default_factory=dict)   # QR mit Art: Feld der Art -> CSV-Spalte ("-" = leer lassen);
                                                 # nicht genannte Felder werden automatisch zugeordnet


@dataclass
class Numbering:
    start: int = 1
    step: int = 1
    digits: int = 0               # mit Nullen auffüllen (0 = nicht)
    prefix: str = ""
    suffix: str = ""
    check: str = "none"           # none | luhn | mod11 | ean  – Prüfziffer anhängen
    continue_key: str = ""        # Name des Zählers: beim nächsten Auftrag dort weiterzählen


@dataclass
class VdpSettings:
    fields: list = field(default_factory=list)       # Liste von VdpField bzw. dicts
    csv_path: str = ""            # Datenquelle; leer = nur Nummerierung
    delimiter: str = ""           # leer = automatisch (; , Tab)
    encoding: str = ""            # leer = automatisch (UTF-8, sonst Windows-1252)
    records: str = ""             # nur diese Datensätze, z. B. "1-50" (leer = alle)
    count: int = 1                # ohne CSV: so viele Kopien
    numbering: Numbering = field(default_factory=Numbering)
    pages_per_record: int = 1     # nur bei order "each": so viele Vorlagenseiten gehören zu einem Datensatz
                                  # (2 = Vorder- und Rückseite: Seite 1+2 -> Datensatz 1, 3+4 -> Datensatz 2 …)
    order: str = "each"           # each = jede Seite der nächste Datensatz (Seiten der Vorlage reihum) |
                                  # record = je Datensatz eine Kopie aller Seiten | page = wie record, Seite für Seite
    reverse: bool = False         # rückwärts (Abreißstapel: oberstes Blatt hat die höchste Nummer)
    log_path: str = ""            # Code-Protokoll als CSV (leer = keins)
    doc_name: str = ""            # Name der Vorlage für {{datei}} (leer = Dateiname der Eingabe)
    placeholders: bool = False    # {{…}} im PDF als Feldposition übernehmen


# --------------------------------------------------------------------------- #
# Prüfziffern
# --------------------------------------------------------------------------- #
def check_digit(digits: str, method: str) -> str:
    d = [int(c) for c in digits if c.isdigit()]
    if method == "none" or not d:
        return ""
    if method == "luhn":
        s = 0
        for i, v in enumerate(reversed(d)):
            if i % 2 == 0:
                v *= 2
                if v > 9:
                    v -= 9
            s += v
        return str((10 - s % 10) % 10)
    if method == "ean":                               # GS1: Gewichte 3,1 von rechts
        s = sum(v * (3 if i % 2 == 0 else 1) for i, v in enumerate(reversed(d)))
        return str((10 - s % 10) % 10)
    if method == "mod11":                             # Gewichte 2..7 von rechts; 10 -> X
        s = sum(v * (2 + i % 6) for i, v in enumerate(reversed(d)))
        r = (11 - s % 11) % 11
        return "X" if r == 10 else str(r)
    raise ValueError(tr("Unbekannte Prüfziffer: {0}").format(method))


def format_number(n: int, nb: Numbering) -> str:
    core = str(abs(n)).zfill(nb.digits) if nb.digits > 0 else str(abs(n))
    if n < 0:
        core = "-" + core
    return f"{nb.prefix}{core}{check_digit(core, nb.check)}{nb.suffix}"


# --------------------------------------------------------------------------- #
# Datenquelle
# --------------------------------------------------------------------------- #
def read_csv(path: str, delimiter: str = "", encoding: str = "") -> tuple[list[str], list[dict]]:
    if not isinstance(path, str) or not os.path.isfile(path):
        raise FileNotFoundError(tr("Datei nicht gefunden: {0}").format(path))
    with open(path, "rb") as f:
        raw = f.read()
    if encoding:
        text = raw.decode(encoding)
    else:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp1252")
    if not delimiter:
        head = text.splitlines()[0] if text.strip() else ""
        delimiter = max((";", ",", "\t", "|"), key=head.count) if head else ";"
        if not head.count(delimiter):
            delimiter = ";"
    rd = csv.reader(io.StringIO(text), delimiter="\t" if delimiter in ("\\t", "tab") else delimiter)
    rows = [r for r in rd if any(c.strip() for c in r)]
    if not rows:
        return [], []
    cols = [c.strip() or f"Spalte{i + 1}" for i, c in enumerate(rows[0])]
    recs = [{cols[i]: (r[i] if i < len(r) else "") for i in range(len(cols))} for r in rows[1:]]
    return cols, recs


def _ranges(text: str, n: int) -> list[int]:
    from .layout import parse_ranges
    return parse_ranges(text, n) if text.strip() else list(range(n))


def counter_state() -> dict:
    from . import l10n
    return dict(l10n.load_settings().get("vdp_counters", {}) or {})


def _save_counter(key: str, next_value: int):
    from . import l10n
    st = l10n.load_settings()
    st.setdefault("vdp_counters", {})[key] = int(next_value)
    l10n.save_settings(st)


def records(s: VdpSettings) -> tuple[list[str], list[dict]]:
    """Alle Datensätze (in Ausgabereihenfolge) mit {{i}}, {{nr}} und den CSV-Spalten."""
    nb = s.numbering if isinstance(s.numbering, Numbering) else Numbering(**(s.numbering or {}))
    if s.csv_path:
        cols, rows = read_csv(s.csv_path, s.delimiter, s.encoding)
    else:
        cols, rows = [], [{} for _ in range(max(0, int(s.count)))]
    idx = _ranges(s.records, len(rows))
    if len(idx) > MAX_RECORDS:
        raise ValueError(tr("Zu viele Datensätze ({0}) – höchstens {1} je Auftrag.").format(len(idx), MAX_RECORDS))
    start = nb.start
    if nb.continue_key:
        start = int(counter_state().get(nb.continue_key, nb.start))
    sysv = system_vars(s, len(idx))
    out = []
    for k, i in enumerate(idx):
        rec = dict(rows[i])
        rec["_sys"] = dict(sysv, datensatz=str(k + 1))
        n = start + k * nb.step
        rec["i"] = str(k + 1)
        rec["nr"] = format_number(n, nb)
        rec["_n"] = n
        out.append(rec)
    if s.reverse:
        out.reverse()
    return cols, out


# --------------------------------------------------------------------------- #
# Variablen außer den CSV-Spalten: {{datum}}, {{seite}}, {{zufall:6}} …
# --------------------------------------------------------------------------- #
WEEKDAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")


def _weekday(i: int) -> str:
    return (tr("Montag"), tr("Dienstag"), tr("Mittwoch"), tr("Donnerstag"), tr("Freitag"), tr("Samstag"),
            tr("Sonntag"))[i]


def system_vars(s, n_records: int = 0, now=None) -> dict:
    """Feste Variablen eines Auftrags (Zeitpunkt = Start des Auftrags, für alle Seiten gleich)."""
    import datetime as _dt
    now = now or _dt.datetime.now()
    return {"datum": now.strftime("%d.%m.%Y"), "zeit": now.strftime("%H:%M"), "jahr": now.strftime("%Y"),
            "monat": now.strftime("%m"), "tag": now.strftime("%d"), "wochentag": _weekday(now.weekday()),
            "kw": str(now.isocalendar()[1]), "datum_iso": now.strftime("%Y-%m-%d"),
            "datei": os.path.splitext(os.path.basename(getattr(s, "doc_name", "") or ""))[0],
            "datensaetze": str(n_records), "_now": now}


def variables_help() -> list:
    """(Platzhalter, Erklärung) für das „?“-Fenster und die Anleitung."""
    return [
        ("{{nr}}", tr("Nummer aus „3. Nummerierung“ (mit Stellen, Vorsatz, Prüfziffer)")),
        ("{{i}}", tr("laufende Nummer des Datensatzes: 1, 2, 3 …")),
        ("{{Spaltenname}}", tr("Wert dieser Spalte der CSV")),
        ("{{datum}}", tr("heutiges Datum, z. B. 09.10.2026")),
        ("{{datum_iso}}", tr("Datum als 2026-10-09")),
        ("{{zeit}}", tr("Uhrzeit beim Erzeugen, z. B. 14:30")),
        ("{{jahr}}", tr("Jahr, z. B. 2026")),
        ("{{monat}}", tr("Monat zweistellig, z. B. 10")),
        ("{{tag}}", tr("Tag zweistellig, z. B. 09")),
        ("{{wochentag}}", tr("z. B. Freitag")),
        ("{{kw}}", tr("Kalenderwoche")),
        ("{{datum:%d.%m.%y %H:%M}}", tr("Datum/Zeit mit eigenem Format (%d Tag, %m Monat, %Y Jahr, %y zweistellig, "
                                        "%H Stunde, %M Minute, %A Wochentag englisch)")),
        ("{{seite}}", tr("Nummer der Seite im Ergebnis")),
        ("{{seiten}}", tr("Seitenzahl des Ergebnisses")),
        ("{{vorlagenseite}}", tr("Seite der Vorlage (bei Vorder-/Rückseite 1 oder 2)")),
        ("{{datensatz}}", tr("Nummer des Datensatzes (wie {{i}})")),
        ("{{datensaetze}}", tr("Anzahl aller Datensätze – z. B. „Karte {{i}} von {{datensaetze}}“")),
        ("{{datei}}", tr("Name der Vorlage ohne .pdf")),
        ("{{zufall}}", tr("zufällige 6-stellige Zahl, je Feld und Seite neu (im Code-Protokoll festgehalten)")),
        ("{{zufall:10}}", tr("zufällige Zahl mit 10 Stellen")),
        ("{{code:8}}", tr("zufälliger Code aus 8 Großbuchstaben und Ziffern (ohne 0/O, 1/I)")),
        ("{{uuid}}", tr("weltweit eindeutige Kennung")),
    ]


def _special(key: str, sysv: dict):
    """Variablen mit Funktion: datum:FORMAT, zufall:N, code:N, uuid. None = unbekannt."""
    import secrets
    name, _, arg = key.partition(":")
    name = name.strip().lower()
    arg = arg.strip()
    if name in ("datum", "date", "zeit", "time") and arg:
        now = sysv.get("_now")
        if now is None:
            import datetime as _dt
            now = _dt.datetime.now()
        try:
            return now.strftime(arg)
        except ValueError:
            return ""
    if name in ("zufall", "random"):
        n = int(arg) if arg.isdigit() else 6
        n = max(1, min(n, 40))
        return str(secrets.randbelow(9) + 1) + "".join(str(secrets.randbelow(10)) for _ in range(n - 1))
    if name == "code":
        n = int(arg) if arg.isdigit() else 8
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        return "".join(secrets.choice(alphabet) for _ in range(max(1, min(n, 64))))
    if name == "uuid" and not arg:
        import uuid
        return str(uuid.uuid4())
    return None


def field_value(f: "VdpField", rec: dict) -> str:
    """Inhalt eines Feldes für einen Datensatz: Vorlage mit Platzhaltern oder – bei QR mit „Art“ – aus den Spalten."""
    t = getattr(f, "qr_type", "text") or "text"
    if f.kind == "qr" and t != "text":
        from . import datakinds
        return datakinds.build(t, rec, getattr(f, "qr_map", None) or None)
    return fill(f.content, rec)


def fill(template: str, rec: dict) -> str:
    """Platzhalter ersetzen: CSV-Spalten, nr, i, dann Auftragsvariablen (datum, seite …) und Funktionen
    (datum:FORMAT, zufall:N …). Unbekannte Platzhalter bleiben stehen."""
    sysv = rec.get("_sys") or {}

    def rep(m):
        key = m.group(1)
        if key in rec and not key.startswith("_"):
            return str(rec[key])
        low = {k.lower(): v for k, v in rec.items() if isinstance(k, str) and not k.startswith("_")}
        if key.lower() in low:
            return str(low[key.lower()])
        sl = {k.lower(): v for k, v in sysv.items() if not k.startswith("_")}
        if key.lower() in sl:
            return str(sl[key.lower()])
        v = _special(key, sysv)
        return v if v is not None else m.group(0)
    return PH.sub(rep, template or "")


# --------------------------------------------------------------------------- #
# Zeichnen (reportlab, Vektor)
# --------------------------------------------------------------------------- #
_TTF = {}


def _system_ttf() -> str | None:
    cands = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf",
             "/usr/share/fonts/TTF/DejaVuSans.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
             os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arial.ttf")]
    return next((p for p in cands if os.path.isfile(p)), None)


def _font_for(font: str, text: str) -> str:
    """Schriftname für reportlab. Standardschriften können nur Westeuropäisch – sonst eine Systemschrift (TTF)."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    path = None
    if font and font not in STD_FONTS:
        if os.path.isfile(font):
            path = font
        else:
            font = "Helvetica"
    if path is None and font in STD_FONTS:
        try:
            text.encode("cp1252")
            return font
        except UnicodeEncodeError:
            path = _system_ttf()
            if path is None:
                return font
    name = _TTF.get(path)
    if name is None:
        name = f"PM{len(_TTF)}"
        pdfmetrics.registerFont(TTFont(name, path))
        _TTF[path] = name
    return name


def _color(c: str):
    from reportlab.lib.colors import HexColor, black
    try:
        return HexColor(c)
    except Exception:
        return black


def draw_field(cv, f: VdpField, value: str, page_h: float):
    """Ein Feld auf die reportlab-Leinwand (pt, Ursprung unten links)."""
    from reportlab.graphics import renderPDF
    from reportlab.graphics.barcode import createBarcodeDrawing
    x, w, h = f.x_mm * MM, f.w_mm * MM, f.h_mm * MM
    y = page_h - f.y_mm * MM - h
    cv.saveState()
    # Feld = Kasten auf der Seite; gedreht wird der Inhalt im Kasten (90/270: Inhalt quer, Breite = Kastenhöhe)
    rot = int(f.rotate) % 360
    cv.translate(x, y)
    if rot == 90:
        cv.translate(w, 0)
        cv.rotate(90)
        w, h = h, w
    elif rot == 180:
        cv.translate(w, h)
        cv.rotate(180)
    elif rot == 270:
        cv.translate(0, h)
        cv.rotate(270)
        w, h = h, w
    col = _color(f.color)
    if f.kind == "text":
        fn = _font_for(f.font, value)
        cv.setFillColor(col)
        cv.setFont(fn, f.size_pt)
        base = max(0.0, (h - f.size_pt * 0.72) / 2)        # Text vertikal mittig im Feld
        lines = value.split("\n") if value else [""]
        lead = f.size_pt * 1.15
        top = base + (len(lines) - 1) * lead / 2
        for k, line in enumerate(lines):
            yy = top - k * lead
            if f.align == "center":
                cv.drawCentredString(w / 2, yy, line)
            elif f.align == "right":
                cv.drawRightString(w, yy, line)
            else:
                cv.drawString(0, yy, line)
    elif value:
        kind = {"qr": "QR", "code128": "Code128", "ean13": "EAN13"}[f.kind]
        kw = {}
        if f.kind == "qr":
            kw = {"barBorder": 4 if getattr(f, "quiet", True) else 0}    # Norm: 4 Module Ruhezone rundum
            side = min(w, h)
            d = createBarcodeDrawing("QR", value=value, width=side, height=side, barFillColor=col, **kw)
            renderPDF.draw(d, cv, (w - side) / 2, (h - side) / 2)
        else:
            if f.kind == "ean13":
                digits = re.sub(r"\D", "", value)
                if len(digits) not in (12, 13):
                    raise ValueError(tr("EAN-13 braucht 12 oder 13 Ziffern: „{0}“").format(value))
                if len(digits) == 13 and check_digit(digits[:12], "ean") != digits[12]:
                    raise ValueError(tr("EAN-13 „{0}“: Prüfziffer falsch – richtig wäre {1}").format(
                        value, digits[:12] + check_digit(digits[:12], "ean")))
                value = digits[:12]                          # Prüfziffer rechnet reportlab selbst
                kw = {"humanReadable": True}
            else:
                # Klartextzeile selbst setzen: reportlab würde sie mit den Strichen auf die Kastengröße verzerren
                th = f.size_pt * 1.25 if f.size_pt > 0 else 0.0
                d = createBarcodeDrawing(kind, value=value, width=w, height=max(1.0, h - th), barFillColor=col,
                                         humanReadable=False, quiet=bool(getattr(f, "quiet", True)))
                renderPDF.draw(d, cv, 0, th)
                if th:
                    cv.setFillColor(col)
                    cv.setFont(_font_for(f.font, value), f.size_pt)
                    cv.drawCentredString(w / 2, f.size_pt * 0.2, value)
                cv.restoreState()
                return
            d = createBarcodeDrawing(kind, value=value, width=w, height=h, barFillColor=col, **kw)
            renderPDF.draw(d, cv, 0, 0)
    cv.restoreState()


ODD = ("ungerade", "odd", "páratlan", "impares", "impaires", "u")
EVEN = ("gerade", "even", "páros", "pares", "paires", "g")


def _page_set(text: str, n: int) -> set:
    """Seiten der Vorlage (0-basiert): „1,3-4“, „ungerade“, „gerade“, „ungerade 1-50“ (= ungerade in 1–50);
    mehrere Angaben mit Komma = alle zusammen."""
    from .layout import parse_ranges
    out = set()
    for part in re.split(r"[,;]", text or ""):
        words = part.strip().lower().split()
        if not words:
            continue
        par = None
        if words[0] in ODD or words[0] in EVEN:
            par = 1 if words[0] in ODD else 0
            words = words[1:]
        rng = parse_ranges(" ".join(words), n) if words else list(range(n))
        out |= {p for p in rng if par is None or (p + 1) % 2 == par}
    return out if (text or "").strip() else set(range(n))


def sequence(order: str, n_records: int, tpl: list, per_record: int = 1) -> list:
    """Ausgabeseiten als Liste (Datensatz, Vorlagenseite)."""
    if order == "each":       # Seite 1 -> Datensatz 1 … (reihum); mit per_record > 1 gehören so viele Seiten zusammen
        g = max(1, int(per_record or 1))
        return [(r, tpl[(r * g + j) % len(tpl)]) for r in range(n_records) for j in range(g)]
    if order == "page":
        return [(r, p) for p in tpl for r in range(n_records)]
    return [(r, p) for r in range(n_records) for p in tpl]


def _fields(s: VdpSettings) -> list[VdpField]:
    out = []
    for f in s.fields:
        if isinstance(f, VdpField):
            out.append(f)
        else:
            known = {k: v for k, v in dict(f).items() if k in VdpField.__dataclass_fields__}
            out.append(VdpField(**known))
    from .datakinds import QR_TYPES
    for f in out:
        if f.kind not in KINDS:
            raise ValueError(tr("Unbekannte Feldart: {0}").format(f.kind))
        if (f.qr_type or "text") not in QR_TYPES:
            raise ValueError(tr("Unbekannte QR-Art: {0}").format(f.qr_type))
    return out


def find_placeholders(doc) -> list[tuple[int, str, tuple]]:
    """{{name}} im Text der Vorlage: (Seite, Inhalt, Kasten in mm ab links oben: x, y, w, h)."""
    out = []
    for i in range(len(doc)):
        pg = doc[i]
        try:
            W, H = pg.get_size()
            tp = pg.get_textpage()
            try:
                text = tp.get_text_range()
                for m in PH.finditer(text):
                    n = tp.count_rects(m.start(), m.end() - m.start())
                    rects = [tp.get_rect(k) for k in range(n)]
                    if not rects:
                        continue
                    l = min(r[0] for r in rects)
                    b = min(r[1] for r in rects)
                    r_ = max(r[2] for r in rects)
                    t = max(r[3] for r in rects)
                    out.append((i, m.group(0), (l / MM, (H - t) / MM, (r_ - l) / MM, (t - b) / MM)))
            finally:
                tp.close()
        finally:
            pg.close()
    return out


def placeholder_fields(doc) -> list[VdpField]:
    """Aus {{…}} im PDF Textfelder machen (gleiche Stelle, Schriftgröße aus der Höhe)."""
    out = []
    for page, content, (x, y, w, h) in find_placeholders(doc):
        out.append(VdpField(kind="text", content=content, x_mm=round(x, 2), y_mm=round(y, 2),
                            w_mm=round(max(w * 3, 20), 2), h_mm=round(h, 2), size_pt=round(h * MM / 0.75, 1),
                            pages=str(page + 1)))
    return out


def _strip_ph(pdf, ops):
    """Content-Operatoren ohne BT…ET-Blöcke, deren Text nur ein {{…}}-Platzhalter ist. -> (ops, entfernt)"""
    import pikepdf
    out, block, removed = [], None, 0
    for operands, op in ops:
        name = str(op)
        if name == "BT":
            block = [(operands, op)]
            continue
        if block is not None:
            block.append((operands, op))
            if name == "ET":
                txt = ""
                for o, p in block:
                    if str(p) in ("Tj", "'", '"'):
                        txt += "".join(str(x) for x in o if isinstance(x, pikepdf.String))
                    elif str(p) == "TJ":
                        for arr in o:
                            if isinstance(arr, pikepdf.Array):
                                txt += "".join(str(x) for x in arr if isinstance(x, pikepdf.String))
                if txt.strip() and PH.fullmatch(txt.strip()):
                    removed += 1
                else:
                    out.extend(block)
                block = None
            continue
        out.append((operands, op))
    return out, removed


def _remove_placeholder_text(pdf) -> int:
    """Textobjekte, die nur aus {{…}} bestehen, aus der Vorlage entfernen – auch in Form-XObjects. Liefert Anzahl."""
    import pikepdf
    seen, removed = set(), 0

    def walk_res(res):
        nonlocal removed
        xo = res.get("/XObject") if res is not None else None
        if xo is None:
            return
        for _k, x in xo.items():
            try:
                if x.get("/Subtype") != "/Form":
                    continue
                key = x.objgen
            except Exception:
                continue
            if key in seen:
                continue
            seen.add(key)
            try:
                ops, n = _strip_ph(pdf, pikepdf.parse_content_stream(x))
            except Exception:
                continue
            if n:
                x.write(pikepdf.unparse_content_stream(ops))
                removed += n
            walk_res(x.get("/Resources"))

    for page in pdf.pages:
        try:
            ops, n = _strip_ph(pdf, pikepdf.parse_content_stream(page))
            if n:
                page.Contents = pdf.make_stream(pikepdf.unparse_content_stream(ops))
                removed += n
        except Exception:
            pass
        walk_res(page.obj.get("/Resources"))
    return removed


def build(src: str, s: VdpSettings, progress=None, cancel=None, pages=None, strip=False) -> tuple[bytes, dict]:
    """Ausgabe-PDF (bytes) + Infos. pages = nur diese Vorlagenseiten (0-basiert, None = alle).
    progress(erledigt, gesamt, text); cancel() -> True bricht ab."""
    import pikepdf
    import pypdfium2 as pdfium
    from reportlab.pdfgen import canvas
    from .objects import normalized
    fields = _fields(s)
    if not getattr(s, "doc_name", ""):
        import dataclasses
        s = dataclasses.replace(s, doc_name=os.path.basename(src))
    from .layout import page_trims, page_doc_bleeds
    src_doc = pdfium.PdfDocument(src)
    try:
        trims, bleeds = page_trims(src_doc), page_doc_bleeds(src_doc)   # Endformat/Anschnitt mitnehmen
        norm = normalized(src_doc)                     # ungedreht, ab (0,0): Feldkoordinaten = sichtbare Seite
    finally:
        src_doc.close()
    try:
        if s.placeholders:
            fields = fields + placeholder_fields(norm)
        sizes = [norm.get_page_size(i) for i in range(len(norm))]
        buf = io.BytesIO()
        norm.save(buf)
    finally:
        norm.close()
    if not fields:
        raise ValueError(tr("Keine Felder angelegt."))
    cols, recs = records(s)
    if not recs:
        raise ValueError(tr("Keine Datensätze (CSV leer oder Anzahl 0)."))
    npages = len(sizes)
    pages_of = [(_page_set(f.pages, npages) if f.pages.strip() else set(range(npages))) for f in fields]
    tpl = [p for p in (pages if pages else range(npages)) if 0 <= p < npages]
    if not tpl:
        raise ValueError(tr("Keine Seiten ausgewählt."))
    seq = sequence(s.order, len(recs), tpl, s.pages_per_record)
    # 1) alle Überlagerungen in einem PDF (eine Seite je Ausgabeseite)
    ov = io.BytesIO()
    cv = canvas.Canvas(ov, pageCompression=1)
    log = []
    total = len(seq)
    for k, (r, p) in enumerate(seq):
        if cancel is not None and cancel():
            from .core import Cancelled
            raise Cancelled(tr("Abgebrochen."))
        if progress is not None and k % 50 == 0:
            progress(k, total, tr("Seite {0}/{1}").format(k + 1, total))
        W, H = sizes[p]
        cv.setPageSize((W, H))
        vals = {}
        rec = dict(recs[r])
        rec["_sys"] = dict(rec.get("_sys") or {}, seite=str(k + 1), seiten=str(total), vorlagenseite=str(p + 1))
        for fi, f in enumerate(fields):
            if p not in pages_of[fi]:
                continue
            v = field_value(f, rec)
            vals[fi] = v
            draw_field(cv, f, v, H)
        cv.showPage()
        if vals:
            log.append((k + 1, r, p, vals))
    cv.save()
    if progress is not None:
        progress(total, total, tr("Schreibe PDF …"))
    # 2) Vorlage je Ausgabeseite kopieren und Überlagerung darauflegen
    base = pikepdf.open(io.BytesIO(buf.getvalue()))
    removed = _remove_placeholder_text(base) if (s.placeholders or strip) else 0
    over = pikepdf.open(io.BytesIO(ov.getvalue()))
    out = pikepdf.new()
    # Vorlage je Seite einmal als Form-XObject; jede Ausgabeseite = Vorlage + eigene Überlagerung (klein, getrennt)
    base_x = [out.copy_foreign(base.pages[p].as_form_xobject()) for p in range(npages)]
    for k, (r, p) in enumerate(seq):
        W, H = sizes[p]
        ox = out.copy_foreign(over.pages[k].as_form_xobject())
        res = pikepdf.Dictionary(XObject=pikepdf.Dictionary(B=base_x[p], O=ox))
        pg = pikepdf.Dictionary(Type=pikepdf.Name.Page, MediaBox=[0, 0, W, H], Resources=res,
                                Contents=out.make_stream(b"q /B Do Q q /O Do Q"))
        t = trims[p] if p < len(trims) else None
        if t:
            pg.TrimBox = [t[0], t[1], W - t[2], H - t[3]]
            b = bleeds[p] if p < len(bleeds) else 0.0
            pg.BleedBox = ([t[0] - b, t[1] - b, W - t[2] + b, H - t[3] + b] if b > 0 else [0, 0, W, H])
        out.pages.append(pikepdf.Page(out.make_indirect(pg)))
    data = io.BytesIO()
    out.save(data, object_stream_mode=pikepdf.ObjectStreamMode.generate)
    for d in (out, over, base):
        d.close()
    # Protokoll und Zähler
    if s.log_path:
        with open(s.log_path, "w", newline="", encoding="utf-8-sig") as fh:
            wr = csv.writer(fh, delimiter=";")
            wr.writerow([tr("Ausgabeseite"), tr("Datensatz"), tr("Vorlagenseite")]
                        + [f"{i + 1}:{f.kind}" for i, f in enumerate(fields)])
            for page_no, r, p, vals in log:
                wr.writerow([page_no, r + 1, p + 1] + [vals.get(i, "") for i in range(len(fields))])
    nb = s.numbering if isinstance(s.numbering, Numbering) else Numbering(**(s.numbering or {}))
    if nb.continue_key and recs:
        last = max(rec["_n"] for rec in recs) if nb.step >= 0 else min(rec["_n"] for rec in recs)
        _save_counter(nb.continue_key, last + nb.step)
    info = {"records": len(recs), "pages": len(seq), "placeholders_removed": removed, "columns": cols}
    return data.getvalue(), info


def page_for_record(s: VdpSettings, record: int, npages: int) -> int:
    """Erste Vorlagenseite von Datensatz record (nur bei order == "each" festgelegt)."""
    g = max(1, int(getattr(s, "pages_per_record", 1) or 1))
    return (record * g) % max(1, npages) if s.order == "each" else -1


def preview(src_doc, page: int, s: VdpSettings, record: int = 0):
    """Eine Seite mit den Feldern des gewählten Datensatzes – als pypdfium2-Dokument (für die Vorschau)."""
    import pypdfium2 as pdfium
    import tempfile
    s2 = VdpSettings(**{k: v for k, v in asdict(s).items()})
    s2.numbering = s.numbering if isinstance(s.numbering, Numbering) else Numbering(**(s.numbering or {}))
    s2.log_path = ""
    nb = s2.numbering
    s2.numbering = Numbering(**{**asdict(nb), "continue_key": ""})
    if nb.continue_key:                                   # Vorschau zählt nicht weiter, zeigt aber den Stand
        s2.numbering.start = int(counter_state().get(nb.continue_key, nb.start))
    _cols, recs = records(s2)
    if not recs:
        raise ValueError(tr("Keine Datensätze (CSV leer oder Anzahl 0)."))
    record = max(0, min(record, len(recs) - 1))
    tmp = tempfile.mkdtemp(prefix="passermark-vdp-")
    one = os.path.join(tmp, "in.pdf")
    single = pdfium.PdfDocument.new()
    single.import_pages(src_doc, [page])
    single.save(one)
    single.close()
    s2.records = ""
    s2.csv_path = ""
    s2.count = 1
    # festen Datensatz einsetzen: Nummer/Spalten als Vorlage-Konstanten
    rec = dict(recs[record])
    seq = sequence(s.order, len(recs), list(range(len(src_doc))), s.pages_per_record)
    k = next((i for i, (r, p) in enumerate(seq) if r == record and p == page), 0)
    rec["_sys"] = dict(rec.get("_sys") or {}, seite=str(k + 1), seiten=str(len(seq)), vorlagenseite=str(page + 1))
    fl = []
    for f in _fields(s):
        if f.pages.strip() and page not in _page_set(f.pages, len(src_doc)):
            continue
        g = VdpField(**asdict(f))
        g.content = field_value(f, rec)
        g.qr_type = "text"
        g.pages = ""
        fl.append(g)
    if s.placeholders:
        for g in placeholder_fields(src_doc):
            if g.pages == str(page + 1):
                g.content = fill(g.content, rec)
                g.pages = ""
                fl.append(g)
    s2.fields = fl
    s2.placeholders = False
    if not fl:
        return pdfium.PdfDocument(one), len(recs)
    data, _info = build(one, s2, strip=s.placeholders)
    return pdfium.PdfDocument(data), len(recs)
