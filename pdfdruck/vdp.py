# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Variable Daten: Felder (Text, Nummer, QR-Code, Code 128, EAN-13, Bild) auf die Seiten legen – je Datensatz eine Kopie.

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
KINDS = ("text", "qr", "code128", "ean13", "image")
FITS = ("contain", "cover", "stretch")    # Bild: einpassen | füllen (anschneiden) | verzerren
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp", ".pdf")
IMAGE_MIN_PPI = 150           # darunter warnt die Datenprüfung (wirksame Auflösung im Feld)
STD_FONTS = ("Helvetica", "Helvetica-Bold", "Times-Roman", "Times-Bold", "Courier", "Courier-Bold")
CHECKS = ("none", "luhn", "mod11", "ean")
PH = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
MAX_RECORDS = 100000


@dataclass
class VdpField:
    kind: str = "text"            # text | qr | code128 | ean13 | image
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
    fit: str = "contain"          # Bild: contain = einpassen | cover = füllen (Überstand abgeschnitten) | stretch = verzerren
    fallback: str = ""            # Bild: Ersatzbild, wenn die Spalte leer ist oder die Datei fehlt (leer = Feld leer lassen)


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
class VdpWindow:
    pages: str = ""            # Seitengruppe des Fensters: "" = alle | "ungerade" | "gerade" | "1,3-5" | "ungerade 1-50" …
    fields: list = field(default_factory=list)   # Felder dieses Fensters (VdpField bzw. dicts)


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
    windows: list = field(default_factory=list)  # Fenster (Seitengruppen, 1.11) – ersetzen in der Oberfläche
                                 # "Nur auf diesen Seiten", "Verteilung" und "Seiten je Datensatz".
                                 # Leer = Altformat: Feld-pages/order/pages_per_record gelten unverändert.


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
        rec["_row"] = i + 2 if s.csv_path else None      # Zeile in der CSV (1 = Kopfzeile) – für Meldungen
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


# --- Bildfelder ---------------------------------------------------------------------------------------------------

def image_base(s) -> str:
    """Bezugsordner für relative Bildpfade: der Ordner der CSV-Datei (ohne CSV: aktueller Ordner)."""
    p = getattr(s, "csv_path", "") or ""
    return os.path.dirname(os.path.abspath(p)) if p else ""


def find_image(value: str, base: str = "") -> str | None:
    """Bildpfad aus der CSV auflösen: absolut oder relativ zum Bezugsordner; \\ wie /, Groß-/Kleinschreibung egal
    (unter Windows erstellte Listen), ohne Endung werden die üblichen Bildendungen probiert. -> Pfad oder None."""
    v = (value or "").strip().strip('"').strip()
    if not v:
        return None
    if v.lower().startswith("file://"):
        from urllib.parse import unquote, urlparse
        v = unquote(urlparse(v).path)
    cands = [v] + ([v.replace("\\", "/")] if "\\" in v else [])
    if not os.path.splitext(v)[1]:
        cands += [c + e for c in list(cands) for e in IMAGE_EXT]
    for c in cands:
        c = os.path.expanduser(c)
        p = c if os.path.isabs(c) else os.path.join(base or os.getcwd(), c)
        if os.path.isfile(p):
            return os.path.abspath(p)
        d, n = os.path.split(p)
        try:
            hit = [x for x in os.listdir(d) if x.lower() == n.lower()]
        except OSError:
            hit = []
        if len(hit) == 1 and os.path.isfile(os.path.join(d, hit[0])):
            return os.path.abspath(os.path.join(d, hit[0]))
    return None


class Images:
    """Bilder für Bildfelder: einmal lesen, oft zeichnen.
    Rasterbilder (PNG, JPG, TIFF …) gehen über reportlab ins PDF; JPEG ohne Drehung unverändert.
    PDF-Bilder (erste Seite): vector=True stellt sie als Vektor-Form auf die Seite – im Inhaltsstrom steht nur der
    Name, das Objekt hängt build() beim Zusammenbau an (attach). vector=False rechnet sie in ein Rasterbild um."""

    def __init__(self, vector: bool = False):
        from collections import OrderedDict
        self.vector = vector
        self._info = {}                     # Pfad -> {"size": (b, h) natürlich, "px": (b, h) | None, "pdf": bool}
        self._readers = OrderedDict()       # Pfad -> reportlab ImageReader (nur die letzten paar)
        self._forms = {}                    # Pfad -> (Name, pikepdf.Pdf, Form-XObject, Kasten x0, y0, x1, y1)
        self.page = 0
        self.used = {}                      # Ausgabeseite -> {Name: Pfad}

    # Lesen
    def info(self, path: str) -> dict:
        """Größe/Art eines Bildes; wirft ValueError, wenn es sich nicht lesen lässt."""
        got = self._info.get(path)
        if isinstance(got, Exception):
            raise got
        if got is not None:
            return got
        try:
            if path.lower().endswith(".pdf") or _is_pdf(path):
                x0, y0, x1, y1 = self._pdf_box(path)
                got = {"size": (x1 - x0, y1 - y0), "px": None, "pdf": True}
            else:
                from PIL import Image
                with Image.open(path) as im:
                    w, h = im.size
                    if (im.getexif() or {}).get(0x0112, 1) in (5, 6, 7, 8):     # Handyfoto hochkant
                        w, h = h, w
                got = {"size": (float(w), float(h)), "px": (w, h), "pdf": False}
            if got["size"][0] <= 0 or got["size"][1] <= 0:
                raise ValueError(tr("leeres Bild"))
        except Exception as e:                                # noqa: BLE001 – jede Ursache als „nicht lesbar“
            why = (tr("kein bekanntes Bildformat") if type(e).__name__ == "UnidentifiedImageError"
                   else str(e).replace(path, os.path.basename(path)) or type(e).__name__)
            err = ValueError(tr("Bild nicht lesbar: {0} ({1})").format(os.path.basename(path), why))
            self._info[path] = err
            raise err from None
        self._info[path] = got
        return got

    def _pdf_box(self, path: str) -> tuple:
        if path not in self._forms:
            import pikepdf
            pdf = pikepdf.open(path)
            if not len(pdf.pages):
                pdf.close()
                raise ValueError(tr("PDF ohne Seiten"))
            form = pdf.make_indirect(pdf.pages[0].as_form_xobject())
            bx = [float(v) for v in form.BBox]
            m = [float(v) for v in form.get("/Matrix", [1, 0, 0, 1, 0, 0])]
            pts = [(x * m[0] + y * m[2] + m[4], x * m[1] + y * m[3] + m[5]) for x in (bx[0], bx[2]) for y in (bx[1], bx[3])]
            box = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
            self._forms[path] = (f"PMImg{len(self._forms)}", pdf, form, box)
        return self._forms[path][3]

    def _reader(self, path: str):
        r = self._readers.get(path)
        if r is not None:
            self._readers.move_to_end(path)
            return r
        from reportlab.lib.utils import ImageReader
        if self.info(path)["pdf"]:
            import pypdfium2 as pdfium
            doc = pdfium.PdfDocument(path)
            try:
                pg = doc[0]
                w, h = pg.get_size()
                scale = min(300 / 72, 4000 / max(w, h, 1))      # 300 dpi, höchstens 4000 Pixel lang
                im = pg.render(scale=scale, may_draw_forms=True).to_pil()
            finally:
                doc.close()
            r = ImageReader(im)
        else:
            from PIL import Image, ImageOps
            im = Image.open(path)
            turned = (im.getexif() or {}).get(0x0112, 1) not in (None, 1)
            if im.format == "JPEG" and not turned and im.mode in ("RGB", "L", "CMYK"):
                im.close()
                r = ImageReader(path)                         # JPEG unverändert durchreichen
            else:
                im = ImageOps.exif_transpose(im)
                if im.mode in ("P", "LA", "PA"):
                    im = im.convert("RGBA")
                elif im.mode == "1":
                    im = im.convert("L")
                elif im.mode not in ("RGB", "RGBA", "L", "CMYK"):
                    im = im.convert("RGB")
                im.load()
                r = ImageReader(im)
        self._readers[path] = r
        while len(self._readers) > 12:
            self._readers.popitem(last=False)
        return r

    # Zeichnen
    @staticmethod
    def placement(size: tuple, w: float, h: float, fit: str, align: str) -> tuple:
        """Bild der natürlichen Größe size in einen Kasten w×h setzen -> (x, y, Breite, Höhe) im Kasten."""
        iw, ih = size
        if fit == "stretch":
            return 0.0, 0.0, w, h
        sc = (max if fit == "cover" else min)(w / iw, h / ih)
        dw, dh = iw * sc, ih * sc
        dx = 0.0 if align == "left" else (w - dw if align == "right" else (w - dw) / 2)
        return dx, (h - dh) / 2, dw, dh

    def draw(self, cv, path: str, w: float, h: float, fit: str = "contain", align: str = "center"):
        inf = self.info(path)
        dx, dy, dw, dh = self.placement(inf["size"], w, h, fit, align)
        cv.saveState()
        if fit == "cover":                                   # Überstand abschneiden
            p = cv.beginPath()
            p.rect(0, 0, w, h)
            cv.clipPath(p, stroke=0, fill=0)
        if inf["pdf"] and self.vector:
            name, _pdf, _form, (x0, y0, x1, y1) = self._forms[path]
            sx, sy = dw / (x1 - x0), dh / (y1 - y0)
            cv.transform(sx, 0, 0, sy, dx - x0 * sx, dy - y0 * sy)
            cv.addLiteral(f"/{name} Do")
            self.used.setdefault(self.page, {})[name] = path
        else:
            cv.drawImage(self._reader(path), dx, dy, dw, dh, mask="auto")
        cv.restoreState()

    def attach(self, over):
        """Vektor-PDF-Bilder in die Seiten-Ressourcen des Überlagerungs-PDFs (pikepdf) eintragen."""
        import pikepdf
        done = {}
        for k, names in self.used.items():
            pg = over.pages[k]
            res = pg.obj.get("/Resources")
            if res is None:
                res = pg.obj.Resources = pikepdf.Dictionary()
            if "/XObject" not in res:
                res.XObject = pikepdf.Dictionary()
            for name, path in names.items():
                if name not in done:
                    done[name] = over.copy_foreign(self._forms[path][2])
                res.XObject[pikepdf.Name("/" + name)] = done[name]

    def ppi(self, path: str, w: float, h: float, fit: str) -> float | None:
        """Wirksame Auflösung im Feld (Pixel je Zoll); None bei PDF-Bildern."""
        inf = self.info(path)
        if not inf["px"]:
            return None
        _dx, _dy, dw, dh = self.placement(inf["size"], w, h, fit, "center")
        return min(inf["px"][0] / (dw / 72.0), inf["px"][1] / (dh / 72.0))

    def close(self):
        for _n, pdf, _f, _b in self._forms.values():
            try:
                pdf.close()
            except Exception:                                 # noqa: BLE001
                pass
        self._forms.clear()
        self._readers.clear()


def _is_pdf(path: str) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(5) == b"%PDF-"
    except OSError:
        return False


def pick_image(f: VdpField, value: str, base: str, images: Images) -> tuple:
    """Welches Bild kommt ins Feld? -> (Pfad | None, Art | None, Schwere, Meldung).
    Art: None = alles gut, empty = nichts angegeben (Feld bleibt leer), fallback = Ersatzbild verwendet,
    missing/unreadable = Fehler (ohne Ersatzbild)."""
    def fb(why_kind, why):
        if not (f.fallback or "").strip():
            return None, why_kind, "error", why
        p = find_image(f.fallback, base)
        if not p:
            return None, "missing", "error", tr("Ersatzbild nicht gefunden: {0}").format(f.fallback)
        try:
            images.info(p)
        except ValueError as e:
            return None, "unreadable", "error", tr("Ersatzbild: {0}").format(e)
        return p, "fallback", "warning", why + " – " + tr("Ersatzbild wird verwendet")
    if not (value or "").strip():
        if not (f.fallback or "").strip():
            return None, "empty", "warning", tr("Kein Bild angegeben – Feld bleibt leer")
        return fb("empty", tr("Kein Bild angegeben"))
    p = find_image(value, base)
    if not p:
        return fb("missing", tr("Bild nicht gefunden: {0}").format(value.strip()))
    try:
        images.info(p)
    except ValueError as e:
        return fb("unreadable", str(e))
    return p, None, "", ""

def draw_field(cv, f: VdpField, value: str, page_h: float, images: "Images | None" = None):
    """Ein Feld auf die reportlab-Leinwand (pt, Ursprung unten links). Bildfeld: value = Pfad der Bilddatei
    (schon aufgelöst, siehe pick_image; leer = nichts zeichnen)."""
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
    if f.kind == "image":
        if value:
            (images or Images()).draw(cv, value, w, h, getattr(f, "fit", "contain") or "contain", f.align)
        cv.restoreState()
        return
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


def _fields_of_list(items: list) -> list:
    """Feldliste (VdpField) aus gemischten Einträgen (VdpField oder dict); unbekannte Schlüssel fallen weg."""
    out = []
    for f in items or []:
        if isinstance(f, VdpField):
            out.append(f)
        elif isinstance(f, dict):
            out.append(VdpField(**{k: v for k, v in f.items() if k in VdpField.__dataclass_fields__}))
    return out


def _windows(s: "VdpSettings") -> list:
    """Fenster des Auftrags; Altformat (Felder mit pages-Angabe, ohne windows) wird zu Fenstern migriert:
    Felder mit gleicher Seiten-Angabe kommen gemeinsam in ein Fenster, Reihenfolge wie angelegt."""
    out = []
    for w in getattr(s, "windows", None) or []:
        if isinstance(w, VdpWindow):
            out.append(VdpWindow(pages=(w.pages or "").strip(), fields=list(w.fields or [])))
        elif isinstance(w, dict):
            known = {k: v for k, v in w.items() if k in VdpWindow.__dataclass_fields__}
            out.append(VdpWindow(**known))
    if out:
        return out
    groups: dict = {}
    order: list = []
    for f in _fields(s):
        key = (f.pages or "").strip()
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(f)
    return [VdpWindow(pages=key, fields=groups[key]) for key in order]


def window_mode(s: "VdpSettings") -> bool:
    """True, wenn Fenster (neues Format) angegeben sind – dann ersetzen sie die alte Verteilung.
    Presets ohne windows (alte Dateien, Kommandozeile) laufen unverändert im Altformat weiter."""
    return bool(getattr(s, "windows", None) or [])


def windows_resolved(s: "VdpSettings", npages: int) -> list:
    """[(Seitenmenge (0-basiert), Felder)] – Fenster in ihrer Reihenfolge. „alle Seiten“ ist die
    Grundschicht: ihre Felder gelten überall und konkurrieren mit keinem Fenster (mehrere solche
    Fenster zeigen ihre Felder gemeinsam). Ungerade/gerade sind gleichrangig (sie überlappen sich
    nicht); ein fester Seitenbereich (z. B. "5-8") gewinnt für seine Seiten vor ungerade/gerade –
    bei gleichem Rang gewinnt das erste Fenster. Nur Fenster mit Feldern kommen in die Liste."""
    wins = []
    for w in _windows(s):
        p = (w.pages or "").strip()
        if p:
            pgs = _page_set(p, npages)
            prec = 1 if p in ("ungerade", "gerade") else 2
        else:
            pgs = set(range(npages))
            prec = 0                                   # Grundschicht: gilt überall, ohne Vorrang-Streit
        flds = _fields_of_list(w.fields)
        if flds:
            wins.append([pgs, prec, flds])
    out = []
    for i, (pgs, prec, flds) in enumerate(wins):
        if prec == 0:
            mine = pgs
        else:
            mine = {p for p in pgs
                    if not any(j != i and p in wins[j][0] and wins[j][1] > prec for j in range(len(wins)))}
        out.append((mine, flds))
    return [(p, f) for p, f in out if f]


def window_pages_used(s: "VdpSettings", npages: int) -> set:
    """Von Fenstern abgedeckte Vorlagenseiten (für Ergebniszeile und Warnung)."""
    used = set()
    for pgs, _f in windows_resolved(s, npages):
        used |= pgs
    return used


def output_info(s: "VdpSettings", npages: int, n_records: int, tpl_len: int) -> dict:
    """Ergebniszeile und Warnbedingung. Standard: jeder Datensatz eine komplette Runde über die
    Vorlagenseiten (Seiten werden dupliziert). warn = True, wenn Vorlagenseiten von keinem Fenster
    abgedeckt sind und dadurch bei mehr als einem Datensatz leere Duplikate entstünden.
    order == "each" (Fenster-Modus, ohne Duplikate): Ausgabe = npages Seiten, je pages_per_record
    Vorlagenseiten ein Datensatz; "unused" = Datensätze ohne eigene Seiten."""
    out_pages = n_records * tpl_len
    unused = 0
    if window_mode(s):
        used = window_pages_used(s, npages)
        uncovered = sorted(set(range(npages)) - used)
        if getattr(s, "order", "") == "each":
            g = max(1, int(getattr(s, "pages_per_record", 1) or 1))
            out_pages = npages
            unused = max(0, n_records - -(-npages // g))    # ceil(npages / g)
    else:
        uncovered = []
    return {"records": n_records, "pages": out_pages,
            "uncovered": uncovered, "warn": bool(uncovered) and n_records > 1, "unused": unused}


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


# --------------------------------------------------------------------------- #
# Datenprüfung vor dem Erzeugen (1.18.10)
# --------------------------------------------------------------------------- #
CHECK_MAX = 300                       # höchstens so viele Einzelmeldungen (dazu die Zählung je Art)


def all_fields(s: VdpSettings) -> list:
    """Alle Felder des Auftrags – auch die in Fenstern."""
    out = list(_fields(s)) if s.fields else []
    for w in getattr(s, "windows", None) or []:
        items = w.fields if isinstance(w, VdpWindow) else (w.get("fields") if isinstance(w, dict) else []) or []
        for f in items:
            if isinstance(f, VdpField):
                out.append(f)
            elif isinstance(f, dict):
                out.append(VdpField(**{k: v for k, v in f.items() if k in VdpField.__dataclass_fields__}))
    return out


def _n1(v: float) -> str:
    """Zahl mit einer Nachkommastelle in der Schreibweise der Oberflächensprache."""
    try:
        from . import l10n, measure
        return measure.fmt(float(v), l10n.current(), 1)
    except Exception:                                      # noqa: BLE001
        return f"{v:.1f}"


def _field_label(f: VdpField, k: int) -> str:
    c = (f.content or "").strip().replace("\n", " ")
    return tr("Feld {0} ({1}: {2})").format(k + 1, f.kind, c[:30] + ("…" if len(c) > 30 else ""))


def check(s: VdpSettings) -> dict:
    """Daten gegen die Felder prüfen, bevor etwas erzeugt wird: Text zu lang für sein Feld (Breite/Höhe), leere
        Spalten, unbekannte Platzhalter, ungültige EAN-13, leere Codes, fehlende/unlesbare Bilder, Bilder mit zu
        geringer Auflösung.
        -> {"problems": [{"row", "record", "field", "severity", "message"}], "counts": {Art: Anzahl}, "records": n}.
        row = Zeile in der CSV (Kopfzeile = 1), record = Datensatz in der Ausgabe."""
    from reportlab.pdfbase import pdfmetrics
    fields = all_fields(s)
    cols, recs = records(s)
    colmap = {c.lower(): c for c in cols}
    probs, counts, unknown_done, lowres_done = [], {}, set(), set()
    base, images = image_base(s), Images()

    def add(kind, sev, rec, k, f, msg):
        counts[kind] = counts.get(kind, 0) + 1
        if len(probs) < CHECK_MAX:
            probs.append({"row": rec.get("_row") if rec else None, "record": int(rec["i"]) if rec else None,
                          "field": _field_label(f, k), "severity": sev, "kind": kind, "message": msg})
    for rec0 in recs:
        rec = dict(rec0)                                  # Seitenvariablen gibt's erst beim Erzeugen: breit annehmen
        rec["_sys"] = dict(rec0.get("_sys") or {}, seite="999", seiten="999", vorlagenseite="9")
        for k, f in enumerate(fields):
            if f.kind == "qr" and (getattr(f, "qr_type", "text") or "text") != "text":
                try:
                    value = field_value(f, rec)
                except Exception as e:                    # noqa: BLE001 – jede Ursache melden
                    add("invalid", "error", rec, k, f, str(e))
                    continue
            else:
                for key in PH.findall(f.content or ""):
                    col = colmap.get(key.lower())
                    if f.kind != "image" and col is not None and not str(rec.get(col, "") or "").strip():
                        add("empty", "warning", rec, k, f, tr("Spalte „{0}“ ist leer").format(col))
                value = fill(f.content, rec)
                for key in PH.findall(value):
                    if (k, key) not in unknown_done:          # je Feld nur einmal
                        unknown_done.add((k, key))
                        add("unknown", "warning", rec, k, f,
                            tr("Platzhalter {{{{{0}}}}} gibt es weder als Spalte noch als Variable").format(key))
            if f.kind == "image":
                path, kind, sev, msg = pick_image(f, value, base, images)
                if kind:
                    add(kind, sev, rec, k, f, msg)
                if path and (k, path) not in lowres_done:
                    lowres_done.add((k, path))
                    rot = int(f.rotate) % 360
                    w = (f.h_mm if rot in (90, 270) else f.w_mm) * MM
                    h = (f.w_mm if rot in (90, 270) else f.h_mm) * MM
                    ppi = images.ppi(path, w, h, getattr(f, "fit", "contain") or "contain")
                    if ppi is not None and ppi < IMAGE_MIN_PPI:
                        add("lowres", "warning", rec, k, f, tr("{0}: nur {1} ppi in diesem Feld (empfohlen ab {2})").format(
                            os.path.basename(path), int(ppi), IMAGE_MIN_PPI))
                continue
            if f.kind == "text":
                if not value:
                    continue
                rot = int(f.rotate) % 360
                w = (f.h_mm if rot in (90, 270) else f.w_mm) * MM
                h = (f.w_mm if rot in (90, 270) else f.h_mm) * MM
                try:
                    fn = _font_for(f.font, value)
                    lines = value.split("\n")
                    widest = max(pdfmetrics.stringWidth(ln, fn, f.size_pt) for ln in lines)
                except Exception:                           # noqa: BLE001
                    continue
                if widest > w + 0.5:
                    add("overflow", "error", rec, k, f, tr("Text zu lang: {0} mm breit, Feld {1} mm – „{2}“").format(
                        _n1(widest / MM), _n1(w / MM),
                        value[:40] + ("…" if len(value) > 40 else "")))
                tall = (len(lines) - 1) * f.size_pt * 1.15 + f.size_pt * 0.9
                if tall > h + 0.5:
                    add("overflow", "error", rec, k, f, tr("Text zu hoch: {0} Zeile(n) passen nicht in {1} mm").format(
                        len(lines), _n1(h / MM)))
            elif not value.strip():
                add("empty", "error", rec, k, f, tr("Code ohne Inhalt – wird nicht gedruckt"))
            elif f.kind == "ean13":
                digits = re.sub(r"\D", "", value)
                if len(digits) not in (12, 13):
                    add("invalid", "error", rec, k, f, tr("EAN-13 braucht 12 oder 13 Ziffern: „{0}“").format(value))
                elif len(digits) == 13 and check_digit(digits[:12], "ean") != digits[12]:
                    add("invalid", "error", rec, k, f, tr("EAN-13 „{0}“: Prüfziffer falsch – richtig wäre {1}").format(
                        value, digits[:12] + check_digit(digits[:12], "ean")))
    images.close()
    return {"problems": probs, "counts": counts, "records": len(recs)}


BLOCKING = ("invalid", "missing", "unreadable")   # diese Fehler brechen das Erzeugen ab


def check_blocking(res: dict) -> bool:
    c = res.get("counts") or {}
    return any(c.get(k) for k in BLOCKING)


def check_text(res: dict, limit: int = 20) -> str:
    """Kurzbericht der Datenprüfung (mehrzeilig)."""
    names = {"overflow": tr("zu lang/zu hoch"), "empty": tr("leer"), "unknown": tr("unbekannter Platzhalter"),
             "invalid": tr("ungültig"), "missing": tr("Bild fehlt"), "unreadable": tr("Bild nicht lesbar"),
             "fallback": tr("Ersatzbild"), "lowres": tr("geringe Auflösung")}
    c = res.get("counts") or {}
    if not c:
        return tr("{0} Datensätze geprüft – alles in Ordnung.").format(res.get("records", 0))
    head = tr("{0} Datensätze geprüft: ").format(res.get("records", 0)) + ", ".join(
        f"{n}× {names.get(k, k)}" for k, n in c.items())
    lines = [head]
    for p in (res.get("problems") or [])[:limit]:
        where = (tr("Zeile {0}").format(p["row"]) if p.get("row") else tr("Datensatz {0}").format(p["record"]))
        lines.append(f"{where} · {p['field']}: {p['message']}")
    rest = sum(c.values()) - min(limit, len(res.get("problems") or []))
    if rest > 0:
        lines.append(tr("… und {0} weitere").format(rest))
    return "\n".join(lines)


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
        ph_extra = []
        if s.placeholders:
            ph_extra = placeholder_fields(norm)
            if not window_mode(s):
                fields = fields + ph_extra
        sizes = [norm.get_page_size(i) for i in range(len(norm))]
        buf = io.BytesIO()
        norm.save(buf)
    finally:
        norm.close()
    if not fields and not window_mode(s):
        raise ValueError(tr("Keine Felder angelegt."))
    cols, recs = records(s)
    if not recs:
        raise ValueError(tr("Keine Datensätze (CSV leer oder Anzahl 0)."))
    npages = len(sizes)
    if window_mode(s):
        # Fenster-Modus: die Seitenmenge kommt vom Fenster, nicht vom einzelnen Feld
        fields = []
        pages_of = []
        for _pgs, wf in windows_resolved(s, npages):
            for f in wf:
                fields.append(f)
                pages_of.append(_pgs)
        if ph_extra:
            fields = fields + ph_extra
            pages_of = pages_of + [_page_set(f.pages, npages) for f in ph_extra]
        if not fields and not window_mode(s):
            raise ValueError(tr("Keine Felder angelegt."))
    else:
        pages_of = [(_page_set(f.pages, npages) if f.pages.strip() else set(range(npages))) for f in fields]
    tpl = [p for p in (pages if pages else range(npages)) if 0 <= p < npages]
    if not tpl:
        raise ValueError(tr("Keine Seiten ausgewählt."))
    if window_mode(s):
        # Fenster-Modus: jeder Datensatz eine komplette Runde über die Vorlagenseiten;
        # "Seite für Seite" bleibt als Sortierung über order == "page" erreichbar.
        # order == "each": keine Duplikate – je Datensatz die nächsten pages_per_record Seiten der Vorlage.
        if getattr(s, "order", "") == "each":
            g = max(1, int(getattr(s, "pages_per_record", 1) or 1))
            seq = [(min(p // g, len(recs) - 1), p) for p in tpl]
        else:
            seq = sequence("page" if s.order == "page" else "record", len(recs), tpl)
    else:
        seq = sequence(s.order, len(recs), tpl, s.pages_per_record)
    # 1) alle Überlagerungen in einem PDF (eine Seite je Ausgabeseite)
    ov = io.BytesIO()
    cv = canvas.Canvas(ov, pageCompression=1)
    log = []
    img_base, images = image_base(s), Images(vector=True)
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
            if f.kind == "image":
                v, _kind, sev, msg = pick_image(f, v, img_base, images)
                if sev == "error":
                    images.close()
                    where = tr("Zeile {0}").format(rec["_row"]) if rec.get("_row") else tr("Datensatz {0}").format(r + 1)
                    raise ValueError(f"{where} · {_field_label(f, fi)}: {msg}")
                v = v or ""
            vals[fi] = v
            images.page = k
            draw_field(cv, f, v, H, images)
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
    images.attach(over)                             # Vektor-PDF-Bilder an ihre Seiten hängen
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
    images.close()
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


def _preview_value(f: VdpField, rec: dict, base: str, images: Images) -> str:
    """Inhalt für die Vorschau; Bildfelder bekommen den aufgelösten Pfad (fehlt das Bild: leer)."""
    v = field_value(f, rec)
    if f.kind == "image":
        v = pick_image(f, v, base, images)[0] or ""
    return v


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
    img_base, images = image_base(s), Images()
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
    g = max(1, int(getattr(s, "pages_per_record", 1) or 1))
    if window_mode(s) and getattr(s, "order", "") == "each":
        seq = [(min(p // g, len(recs) - 1), p) for p in range(len(src_doc))]
    elif window_mode(s):
        seq = sequence("page" if s.order == "page" else "record", len(recs), list(range(len(src_doc))))
    else:
        seq = sequence(s.order, len(recs), list(range(len(src_doc))), s.pages_per_record)
    k = next((i for i, (r, p) in enumerate(seq) if r == record and p == page), 0)
    rec["_sys"] = dict(rec.get("_sys") or {}, seite=str(k + 1), seiten=str(len(seq)), vorlagenseite=str(page + 1))
    fl = []
    if window_mode(s):
        for pgs, wf in windows_resolved(s, len(src_doc)):
            if page not in pgs:
                continue
            for f in wf:
                g = VdpField(**asdict(f))
                g.content = _preview_value(f, rec, img_base, images)
                g.fallback = ""
                g.qr_type = "text"
                g.pages = ""
                fl.append(g)
    else:
        for f in _fields(s):
            if f.pages.strip() and page not in _page_set(f.pages, len(src_doc)):
                continue
            g = VdpField(**asdict(f))
            g.content = _preview_value(f, rec, img_base, images)
            g.fallback = ""
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
    s2.windows = []          # Felder sind bereits nach Fenster/Seite gefiltert und vorausgefüllt –
                             # sonst würde build() die Fenster gegen das 1-Seiten-Zwischen-PDF erneut
                             # auflösen (ungerade = Seite 1, gerade = nichts) und die Ausgabe verfälschen.
    s2.placeholders = False
    if not fl:
        return pdfium.PdfDocument(one), len(recs)
    data, _info = build(one, s2, strip=s.placeholders)
    return pdfium.PdfDocument(data), len(recs)

