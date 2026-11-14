# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Variable data: place fields (text, number, QR code, Code 128, EAN-13, image) on the pages – one copy per record.

Records come from a CSV file (row = copy) or from plain numbering (count). Contents are
templates with placeholders: {{column name}}, {{nr}} (number incl. format/check digit), {{i}} (running number from 1).
Everything is drawn as vectors (type, bars, QR modules) and laid on the page as an overlay –
the template itself stays unchanged. Coordinates in mm from the top left corner of the visible page.
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
FITS = ("contain", "cover", "stretch")  # image: fit | fill (crop) | stretch
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp", ".pdf")
IMAGE_MIN_PPI = 150  # below this the data check warns (effective resolution in the field)
STD_FONTS = ("Helvetica", "Helvetica-Bold", "Times-Roman", "Times-Bold", "Courier", "Courier-Bold")
CHECKS = ("none", "luhn", "mod11", "ean")
PH = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
MAX_RECORDS = 100000


@dataclass
class VdpField:
    """One variable field on the page: kind (text, QR, Code 128, EAN-13, image), content template, position, look."""

    kind: str = "text"  # text | qr | code128 | ean13 | image
    content: str = "{{nr}}"  # template with placeholders
    x_mm: float = 10.0  # top left corner of the field, from the top left of the page
    y_mm: float = 10.0
    w_mm: float = 40.0
    h_mm: float = 10.0
    font: str = "Helvetica"  # standard font or path to a TTF file
    size_pt: float = 12.0
    color: str = "#000000"
    align: str = "left"  # left | center | right
    rotate: int = 0  # 0 | 90 | 180 | 270 (counterclockwise)
    pages: str = ""  # only on these pages of the template, e.g. "1", "1,3-4", "ungerade", "gerade",
    # "ungerade 1-50" (empty = all)
    qr_type: str = "text"  # QR: text = content as entered; vcard, wifi, email, url, phone, sms, event, geo =
    # content composed from the columns of the data table (see datakinds)
    quiet: bool = True  # QR/Code 128: keep a white quiet zone inside the field (for reliable scanning)
    qr_map: dict = field(default_factory=dict)  # QR with a kind: field of the kind -> CSV column ("-" = leave empty);
    # fields not named are mapped automatically
    fit: str = "contain"  # image: contain = fit | cover = fill (overhang cut off) | stretch = distort
    fallback: str = (
        ""  # image: fallback image if the column is empty or the file is missing (empty = leave the field empty)
    )


@dataclass
class Numbering:
    """Settings of the running number: start, step, padding, prefix/suffix, check digit."""

    start: int = 1
    step: int = 1
    digits: int = 0  # pad with zeros (0 = no padding)
    prefix: str = ""
    suffix: str = ""
    check: str = "none"  # none | luhn | mod11 | ean  – append a check digit
    continue_key: str = ""  # name of the counter: the next job continues counting there


@dataclass
class VdpWindow:
    """A group of fields that applies to a set of pages ("all", "odd", "1,3-5" …)."""

    pages: str = ""  # page group of the window: "" = all | "ungerade" | "gerade" | "1,3-5" | "ungerade 1-50" …
    fields: list = field(default_factory=list)  # fields of this window (VdpField or dicts)


@dataclass
class VdpSettings:
    """Settings of the job ``vdp``: fields, data source (CSV), numbering and how records map to pages."""

    fields: list = field(default_factory=list)  # list of VdpField or dicts
    csv_path: str = ""  # data source; empty = numbering only
    delimiter: str = ""  # empty = automatic (; , tab)
    encoding: str = ""  # empty = automatic (UTF-8, otherwise Windows-1252)
    records: str = ""  # only these records, e.g. "1-50" (empty = all)
    count: int = 1  # without CSV: this many copies
    numbering: Numbering = field(default_factory=Numbering)
    pages_per_record: int = 1  # only for order "each": this many template pages belong to one record
    # (2 = front and back: pages 1+2 -> record 1, 3+4 -> record 2 …)
    order: str = "each"  # each = every page the next record (template pages in turn) |
    # record = one copy of all pages per record | page = like record, page by page
    reverse: bool = False  # backwards (tear-off pad: the top sheet has the highest number)
    log_path: str = ""  # code log as CSV (empty = none)
    doc_name: str = ""  # name of the template for {{datei}} (empty = file name of the input)
    placeholders: bool = False  # take over {{…}} in the PDF as field positions
    windows: list = field(default_factory=list)  # Windows (page groups) – in the interface they replace
    # "only on these pages", "distribution" and "pages per record".
    # Empty = old format: field pages/order/pages_per_record apply unchanged.


# --------------------------------------------------------------------------- #
# check digits
# --------------------------------------------------------------------------- #
def check_digit(digits: str, method: str) -> str:
    """Check digit for ``digits`` by ``method`` (luhn, mod11, ean); empty string for method "none"."""
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
    if method == "ean":  # GS1: weights 3,1 from the right
        s = sum(v * (3 if i % 2 == 0 else 1) for i, v in enumerate(reversed(d)))
        return str((10 - s % 10) % 10)
    if method == "mod11":  # weights 2..7 from the right; 10 -> X
        s = sum(v * (2 + i % 6) for i, v in enumerate(reversed(d)))
        r = (11 - s % 11) % 11
        return "X" if r == 10 else str(r)
    raise ValueError(tr("Unbekannte Prüfziffer: {0}").format(method))


def format_number(n: int, nb: Numbering) -> str:
    """Format the running number ``n``: zero padding, prefix, check digit and suffix."""
    core = str(abs(n)).zfill(nb.digits) if nb.digits > 0 else str(abs(n))
    if n < 0:
        core = "-" + core
    return f"{nb.prefix}{core}{check_digit(core, nb.check)}{nb.suffix}"


# --------------------------------------------------------------------------- #
# data source
# --------------------------------------------------------------------------- #
def read_csv(path: str, delimiter: str = "", encoding: str = "") -> tuple[list[str], list[dict]]:
    """Read a CSV file and return ``(column names, rows as dicts)``; delimiter and encoding are detected if empty."""
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
    """The stored counters (last used numbers) from the user settings."""
    from . import l10n

    return dict(l10n.load_settings().get("vdp_counters", {}) or {})


def _save_counter(key: str, next_value: int):
    from . import l10n

    st = l10n.load_settings()
    st.setdefault("vdp_counters", {})[key] = int(next_value)
    l10n.save_settings(st)


def records(s: VdpSettings) -> tuple[list[str], list[dict]]:
    """All records (in output order) with {{i}}, {{nr}} and the CSV columns."""
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
        rec["_row"] = i + 2 if s.csv_path else None  # row in the CSV (1 = header row) – for messages
        out.append(rec)
    if s.reverse:
        out.reverse()
    return cols, out


# --------------------------------------------------------------------------- #
# variables besides the CSV columns: {{datum}}, {{seite}}, {{zufall:6}} …
# --------------------------------------------------------------------------- #
WEEKDAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")


def _weekday(i: int) -> str:
    return (
        tr("Montag"),
        tr("Dienstag"),
        tr("Mittwoch"),
        tr("Donnerstag"),
        tr("Freitag"),
        tr("Samstag"),
        tr("Sonntag"),
    )[i]


def system_vars(s, n_records: int = 0, now=None) -> dict:
    """Fixed variables of a job (time = start of the job, the same for all pages)."""
    import datetime as _dt

    now = now or _dt.datetime.now()
    return {
        "datum": now.strftime("%d.%m.%Y"),
        "zeit": now.strftime("%H:%M"),
        "jahr": now.strftime("%Y"),
        "monat": now.strftime("%m"),
        "tag": now.strftime("%d"),
        "wochentag": _weekday(now.weekday()),
        "kw": str(now.isocalendar()[1]),
        "datum_iso": now.strftime("%Y-%m-%d"),
        "datei": os.path.splitext(os.path.basename(getattr(s, "doc_name", "") or ""))[0],
        "datensaetze": str(n_records),
        "_now": now,
    }


def variables_help() -> list:
    """(placeholder, explanation) for the "?" window and the manual."""
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
        (
            "{{datum:%d.%m.%y %H:%M}}",
            tr(
                "Datum/Zeit mit eigenem Format (%d Tag, %m Monat, %Y Jahr, %y zweistellig, "
                "%H Stunde, %M Minute, %A Wochentag englisch)"
            ),
        ),
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
    """Variables with a function: datum:FORMAT, zufall:N, code:N, uuid. None = unknown."""
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


def field_value(f: VdpField, rec: dict) -> str:
    """Content of a field for one record: template with placeholders or – for QR with a "kind" – from the columns."""
    t = getattr(f, "qr_type", "text") or "text"
    if f.kind == "qr" and t != "text":
        from . import datakinds

        return datakinds.build(t, rec, getattr(f, "qr_map", None) or None)
    return fill(f.content, rec)


def fill(template: str, rec: dict) -> str:
    """Replace placeholders: CSV columns, nr, i, then job variables (datum, seite …) and functions
    (datum:FORMAT, zufall:N …). Unknown placeholders are left as they are.
    """
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
# drawing (reportlab, vector)
# --------------------------------------------------------------------------- #
_TTF = {}


def _system_ttf() -> str | None:
    cands = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arial.ttf"),
    ]
    return next((p for p in cands if os.path.isfile(p)), None)


def _font_for(font: str, text: str) -> str:
    """Font name for reportlab. The standard fonts only cover Western European – otherwise a system font (TTF)."""
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


# --- image fields -------------------------------------------------------------------------------------------------


def image_base(s) -> str:
    """Base folder for relative image paths: the folder of the CSV file (without CSV: current folder)."""
    p = getattr(s, "csv_path", "") or ""
    return os.path.dirname(os.path.abspath(p)) if p else ""


def find_image(value: str, base: str = "") -> str | None:
    """Resolve an image path from the CSV: absolute or relative to the base folder; \\ like /, case-insensitive
    (lists created on Windows), without an extension the usual image extensions are tried. -> path or None.
    """
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
    """Images for image fields: read once, draw often.
    Raster images (PNG, JPG, TIFF …) go into the PDF via reportlab; JPEG without rotation unchanged.
    PDF images (first page): vector=True puts them on the page as a vector form – the content stream only holds
    the name, build() attaches the object when assembling (attach). vector=False converts them to a raster image.
    """

    def __init__(self, vector: bool = False):
        from collections import OrderedDict

        self.vector = vector
        self._info = {}  # path -> {"size": (w, h) natural, "px": (w, h) | None, "pdf": bool}
        self._readers = OrderedDict()  # path -> reportlab ImageReader (only the last few)
        self._forms = {}  # path -> (name, pikepdf.Pdf, form XObject, box x0, y0, x1, y1)
        self.page = 0
        self.used = {}  # output page -> {name: path}

    # reading
    def info(self, path: str) -> dict:
        """Size/kind of an image; raises ValueError if it cannot be read."""
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
                    if (im.getexif() or {}).get(0x0112, 1) in (5, 6, 7, 8):  # phone photo in portrait
                        w, h = h, w
                got = {"size": (float(w), float(h)), "px": (w, h), "pdf": False}
            if got["size"][0] <= 0 or got["size"][1] <= 0:
                raise ValueError(tr("leeres Bild"))
        except Exception as e:  # noqa: BLE001 – jede Ursache als „nicht lesbar“
            why = (
                tr("kein bekanntes Bildformat")
                if type(e).__name__ == "UnidentifiedImageError"
                else str(e).replace(path, os.path.basename(path)) or type(e).__name__
            )
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
            pts = [
                (x * m[0] + y * m[2] + m[4], x * m[1] + y * m[3] + m[5]) for x in (bx[0], bx[2]) for y in (bx[1], bx[3])
            ]
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
                scale = min(300 / 72, 4000 / max(w, h, 1))  # 300 dpi, at most 4000 pixels long
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
                r = ImageReader(path)  # pass JPEG through unchanged
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

    # drawing
    @staticmethod
    def placement(size: tuple, w: float, h: float, fit: str, align: str) -> tuple:
        """Place an image of natural size ``size`` into a box w×h -> (x, y, width, height) inside the box."""
        iw, ih = size
        if fit == "stretch":
            return 0.0, 0.0, w, h
        sc = (max if fit == "cover" else min)(w / iw, h / ih)
        dw, dh = iw * sc, ih * sc
        dx = 0.0 if align == "left" else (w - dw if align == "right" else (w - dw) / 2)
        return dx, (h - dh) / 2, dw, dh

    def draw(self, cv, path: str, w: float, h: float, fit: str = "contain", align: str = "center"):
        """Draw the image or PDF at ``path`` into a box of ``w`` × ``h`` points (contain, cover or stretch)."""
        inf = self.info(path)
        dx, dy, dw, dh = self.placement(inf["size"], w, h, fit, align)
        cv.saveState()
        if fit == "cover":  # cut off the overhang
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
        """Enter vector PDF images into the page resources of the overlay PDF (pikepdf)."""
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
        """Effective resolution in the field (pixels per inch); None for PDF images."""
        inf = self.info(path)
        if not inf["px"]:
            return None
        _dx, _dy, dw, dh = self.placement(inf["size"], w, h, fit, "center")
        return min(inf["px"][0] / (dw / 72.0), inf["px"][1] / (dh / 72.0))

    def close(self):
        """Close the PDF files that were opened for image fields."""
        for _n, pdf, _f, _b in self._forms.values():
            try:
                pdf.close()
            except Exception:  # noqa: BLE001
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
    """Which image goes into the field? -> (path | None, kind | None, severity, message).
    kind: None = all fine, empty = nothing given (field stays empty), fallback = fallback image used,
    missing/unreadable = error (without a fallback image).
    """

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


def draw_field(cv, f: VdpField, value: str, page_h: float, images: Images | None = None):
    """Draw one field on the reportlab canvas (pt, origin bottom left). Image field: value = path of the image file
    (already resolved, see pick_image; empty = draw nothing).
    """
    from reportlab.graphics import renderPDF
    from reportlab.graphics.barcode import createBarcodeDrawing

    x, w, h = f.x_mm * MM, f.w_mm * MM, f.h_mm * MM
    y = page_h - f.y_mm * MM - h
    cv.saveState()
    # field = box on the page; the content is rotated inside the box (90/270: content sideways, width = box height)
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
        base = max(0.0, (h - f.size_pt * 0.72) / 2)  # text vertically centred in the field
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
            kw = {"barBorder": 4 if getattr(f, "quiet", True) else 0}  # standard: quiet zone of 4 modules all round
            side = min(w, h)
            d = createBarcodeDrawing("QR", value=value, width=side, height=side, barFillColor=col, **kw)
            renderPDF.draw(d, cv, (w - side) / 2, (h - side) / 2)
        else:
            if f.kind == "ean13":
                digits = re.sub(r"\D", "", value)
                if len(digits) not in (12, 13):
                    raise ValueError(tr("EAN-13 braucht 12 oder 13 Ziffern: „{0}“").format(value))
                if len(digits) == 13 and check_digit(digits[:12], "ean") != digits[12]:
                    raise ValueError(
                        tr("EAN-13 „{0}“: Prüfziffer falsch – richtig wäre {1}").format(
                            value, digits[:12] + check_digit(digits[:12], "ean")
                        )
                    )
                value = digits[:12]  # reportlab calculates the check digit itself
                kw = {"humanReadable": True}
            else:
                # set the plain text line ourselves: reportlab would distort it together with the bars to the box size
                th = f.size_pt * 1.25 if f.size_pt > 0 else 0.0
                d = createBarcodeDrawing(
                    kind,
                    value=value,
                    width=w,
                    height=max(1.0, h - th),
                    barFillColor=col,
                    humanReadable=False,
                    quiet=bool(getattr(f, "quiet", True)),
                )
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
    """Pages of the template (0-based): "1,3-4", "ungerade" (odd), "gerade" (even), "ungerade 1-50" (= odd within
    1–50); several entries separated by commas = all of them together.
    """
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
    """List of fields (VdpField) from mixed entries (VdpField or dict); unknown keys are dropped."""
    out = []
    for f in items or []:
        if isinstance(f, VdpField):
            out.append(f)
        elif isinstance(f, dict):
            out.append(VdpField(**{k: v for k, v in f.items() if k in VdpField.__dataclass_fields__}))
    return out


def _windows(s: VdpSettings) -> list:
    """Windows of the job; the old format (fields with pages, without windows) is migrated to windows:
    fields with the same pages entry go into one window together, in the order they were created.
    """
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


def window_mode(s: VdpSettings) -> bool:
    """True if windows (new format) are given – they then replace the old distribution.
    Presets without windows (old files, command line) keep running unchanged in the old format.
    """
    return bool(getattr(s, "windows", None) or [])


def windows_resolved(s: VdpSettings, npages: int) -> list:
    """[(set of pages (0-based), fields)] – windows in their order. "All pages" is the
    base layer: its fields apply everywhere and compete with no window (several such
    windows show their fields together). Odd/even rank equally (they do not
    overlap); a fixed page range (e.g. "5-8") wins for its pages over odd/even –
    at equal rank the first window wins. Only windows with fields are listed.
    """
    wins = []
    for w in _windows(s):
        p = (w.pages or "").strip()
        if p:
            pgs = _page_set(p, npages)
            prec = 1 if p in ("ungerade", "gerade") else 2
        else:
            pgs = set(range(npages))
            prec = 0  # base layer: applies everywhere, no competition for precedence
        flds = _fields_of_list(w.fields)
        if flds:
            wins.append([pgs, prec, flds])
    out = []
    for i, (pgs, prec, flds) in enumerate(wins):
        if prec == 0:
            mine = pgs
        else:
            mine = {
                p for p in pgs if not any(j != i and p in wins[j][0] and wins[j][1] > prec for j in range(len(wins)))
            }
        out.append((mine, flds))
    return [(p, f) for p, f in out if f]


def window_pages_used(s: VdpSettings, npages: int) -> set:
    """Template pages covered by windows (for the result line and the warning)."""
    used = set()
    for pgs, _f in windows_resolved(s, npages):
        used |= pgs
    return used


def output_info(s: VdpSettings, npages: int, n_records: int, tpl_len: int) -> dict:
    """Result line and warning condition. Default: every record one complete round over the
    template pages (pages are duplicated). warn = True if template pages are covered by no window
    and empty duplicates would result with more than one record.
    order == "each" (window mode, no duplicates): output = npages pages, one record per pages_per_record
    template pages; "unused" = records without pages of their own.
    """
    out_pages = n_records * tpl_len
    unused = 0
    if window_mode(s):
        used = window_pages_used(s, npages)
        uncovered = sorted(set(range(npages)) - used)
        if getattr(s, "order", "") == "each":
            g = max(1, int(getattr(s, "pages_per_record", 1) or 1))
            out_pages = npages
            unused = max(0, n_records - -(-npages // g))  # ceil(npages / g)
    else:
        uncovered = []
    return {
        "records": n_records,
        "pages": out_pages,
        "uncovered": uncovered,
        "warn": bool(uncovered) and n_records > 1,
        "unused": unused,
    }


def sequence(order: str, n_records: int, tpl: list, per_record: int = 1) -> list:
    """Output pages as a list of (record, template page)."""
    if order == "each":  # page 1 -> record 1 … (in turn); with per_record > 1 that many pages belong together
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
# data check before generating
# --------------------------------------------------------------------------- #
CHECK_MAX = 300  # at most this many individual messages (plus the count per kind)


def all_fields(s: VdpSettings) -> list:
    """All fields of the job – including those in windows."""
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
    """Number with one decimal place in the notation of the interface language."""
    try:
        from . import l10n, measure

        return measure.fmt(float(v), l10n.current(), 1)
    except Exception:  # noqa: BLE001
        return f"{v:.1f}"


def _field_label(f: VdpField, k: int) -> str:
    c = (f.content or "").strip().replace("\n", " ")
    return tr("Feld {0} ({1}: {2})").format(k + 1, f.kind, c[:30] + ("…" if len(c) > 30 else ""))


class _DataCheck:
    """State of one check(): the problems found, how often each kind occurred, and what was already reported."""

    def __init__(self, s: VdpSettings, cols: list):
        self.colmap = {c.lower(): c for c in cols}
        self.probs: list = []
        self.counts: dict = {}
        self.unknown_done: set = set()  # (field, placeholder) – reported only once per field
        self.lowres_done: set = set()  # (field, image path) – measured only once
        self.base, self.images = image_base(s), Images()

    def add(self, kind, sev, rec, k, f, msg):
        """Count a problem and, up to CHECK_MAX, keep it for the report."""
        self.counts[kind] = self.counts.get(kind, 0) + 1
        if len(self.probs) < CHECK_MAX:
            self.probs.append(
                {
                    "row": rec.get("_row") if rec else None,
                    "record": int(rec["i"]) if rec else None,
                    "field": _field_label(f, k),
                    "severity": sev,
                    "kind": kind,
                    "message": msg,
                }
            )

    def field(self, rec, k, f):
        """Check field number k for one record."""
        if f.kind == "qr" and (getattr(f, "qr_type", "text") or "text") != "text":
            try:
                value = field_value(f, rec)
            except Exception as e:  # noqa: BLE001 – report every cause
                self.add("invalid", "error", rec, k, f, str(e))
                return
        else:
            value = self._filled(rec, k, f)
        if f.kind == "image":
            self._image(rec, k, f, value)
        elif f.kind == "text":
            self._text(rec, k, f, value)
        elif not value.strip():
            self.add("empty", "error", rec, k, f, tr("Code ohne Inhalt – wird nicht gedruckt"))
        elif f.kind == "ean13":
            self._ean13(rec, k, f, value)

    def _filled(self, rec, k, f) -> str:
        """The content with the placeholders filled in; reports empty columns and unknown placeholders."""
        for key in PH.findall(f.content or ""):
            col = self.colmap.get(key.lower())
            if f.kind != "image" and col is not None and not str(rec.get(col, "") or "").strip():
                self.add("empty", "warning", rec, k, f, tr("Spalte „{0}“ ist leer").format(col))
        value = fill(f.content, rec)
        for key in PH.findall(value):
            if (k, key) not in self.unknown_done:  # only once per field
                self.unknown_done.add((k, key))
                self.add(
                    "unknown",
                    "warning",
                    rec,
                    k,
                    f,
                    tr("Platzhalter {{{{{0}}}}} gibt es weder als Spalte noch als Variable").format(key),
                )
        return value

    def _image(self, rec, k, f, value):
        """Image field: file missing or unreadable, fallback used, resolution too low for the field."""
        path, kind, sev, msg = pick_image(f, value, self.base, self.images)
        if kind:
            self.add(kind, sev, rec, k, f, msg)
        if path and (k, path) not in self.lowres_done:
            self.lowres_done.add((k, path))
            w, h = _field_size_pt(f)
            ppi = self.images.ppi(path, w, h, getattr(f, "fit", "contain") or "contain")
            if ppi is not None and ppi < IMAGE_MIN_PPI:
                self.add(
                    "lowres",
                    "warning",
                    rec,
                    k,
                    f,
                    tr("{0}: nur {1} ppi in diesem Feld (empfohlen ab {2})").format(
                        os.path.basename(path), int(ppi), IMAGE_MIN_PPI
                    ),
                )

    def _text(self, rec, k, f, value):
        """Text field: too wide or too tall for its field."""
        from reportlab.pdfbase import pdfmetrics

        if not value:
            return
        w, h = _field_size_pt(f)
        try:
            fn = _font_for(f.font, value)
            lines = value.split("\n")
            widest = max(pdfmetrics.stringWidth(ln, fn, f.size_pt) for ln in lines)
        except Exception:  # noqa: BLE001
            return
        if widest > w + 0.5:
            self.add(
                "overflow",
                "error",
                rec,
                k,
                f,
                tr("Text zu lang: {0} mm breit, Feld {1} mm – „{2}“").format(
                    _n1(widest / MM), _n1(w / MM), value[:40] + ("…" if len(value) > 40 else "")
                ),
            )
        tall = (len(lines) - 1) * f.size_pt * 1.15 + f.size_pt * 0.9
        if tall > h + 0.5:
            self.add(
                "overflow",
                "error",
                rec,
                k,
                f,
                tr("Text zu hoch: {0} Zeile(n) passen nicht in {1} mm").format(len(lines), _n1(h / MM)),
            )

    def _ean13(self, rec, k, f, value):
        """EAN-13: number of digits and check digit."""
        digits = re.sub(r"\D", "", value)
        if len(digits) not in (12, 13):
            self.add("invalid", "error", rec, k, f, tr("EAN-13 braucht 12 oder 13 Ziffern: „{0}“").format(value))
        elif len(digits) == 13 and check_digit(digits[:12], "ean") != digits[12]:
            self.add(
                "invalid",
                "error",
                rec,
                k,
                f,
                tr("EAN-13 „{0}“: Prüfziffer falsch – richtig wäre {1}").format(
                    value, digits[:12] + check_digit(digits[:12], "ean")
                ),
            )


def _field_size_pt(f: VdpField) -> tuple[float, float]:
    """Width and height of a field in points as the content sees them (swapped when rotated by 90°/270°)."""
    rot = int(f.rotate) % 360
    w = (f.h_mm if rot in (90, 270) else f.w_mm) * MM
    h = (f.w_mm if rot in (90, 270) else f.h_mm) * MM
    return w, h


def check(s: VdpSettings) -> dict:
    """Check the data against the fields before anything is generated: text too long for its field (width/height),
    empty columns, unknown placeholders, invalid EAN-13, empty codes, missing/unreadable images, images with too
    low a resolution.
    -> {"problems": [{"row", "record", "field", "severity", "message"}], "counts": {kind: count}, "records": n}.
    row = row in the CSV (header row = 1), record = record in the output.
    """
    fields = all_fields(s)
    cols, recs = records(s)
    c = _DataCheck(s, cols)
    for rec0 in recs:
        rec = dict(rec0)  # page variables only exist when generating: assume wide
        rec["_sys"] = dict(rec0.get("_sys") or {}, seite="999", seiten="999", vorlagenseite="9")
        for k, f in enumerate(fields):
            c.field(rec, k, f)
    c.images.close()
    return {"problems": c.probs, "counts": c.counts, "records": len(recs)}


BLOCKING = ("invalid", "missing", "unreadable")  # these errors abort generating


def check_blocking(res: dict) -> bool:
    """Whether a data check result contains findings that should stop the job."""
    c = res.get("counts") or {}
    return any(c.get(k) for k in BLOCKING)


def check_text(res: dict, limit: int = 20) -> str:
    """Short report of the data check (several lines)."""
    names = {
        "overflow": tr("zu lang/zu hoch"),
        "empty": tr("leer"),
        "unknown": tr("unbekannter Platzhalter"),
        "invalid": tr("ungültig"),
        "missing": tr("Bild fehlt"),
        "unreadable": tr("Bild nicht lesbar"),
        "fallback": tr("Ersatzbild"),
        "lowres": tr("geringe Auflösung"),
    }
    c = res.get("counts") or {}
    if not c:
        return tr("{0} Datensätze geprüft – alles in Ordnung.").format(res.get("records", 0))
    head = tr("{0} Datensätze geprüft: ").format(res.get("records", 0)) + ", ".join(
        f"{n}× {names.get(k, k)}" for k, n in c.items()
    )
    lines = [head]
    for p in (res.get("problems") or [])[:limit]:
        where = tr("Zeile {0}").format(p["row"]) if p.get("row") else tr("Datensatz {0}").format(p["record"])
        lines.append(f"{where} · {p['field']}: {p['message']}")
    rest = sum(c.values()) - min(limit, len(res.get("problems") or []))
    if rest > 0:
        lines.append(tr("… und {0} weitere").format(rest))
    return "\n".join(lines)


def find_placeholders(doc) -> list[tuple[int, str, tuple]]:
    """{{name}} in the text of the template: (page, content, box in mm from top left: x, y, w, h)."""
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
    """Turn {{…}} in the PDF into text fields (same place, font size from the height)."""
    out = []
    for page, content, (x, y, w, h) in find_placeholders(doc):
        out.append(
            VdpField(
                kind="text",
                content=content,
                x_mm=round(x, 2),
                y_mm=round(y, 2),
                w_mm=round(max(w * 3, 20), 2),
                h_mm=round(h, 2),
                size_pt=round(h * MM / 0.75, 1),
                pages=str(page + 1),
            )
        )
    return out


def _strip_ph(pdf, ops):
    """Content operators without the BT…ET blocks whose text is only a {{…}} placeholder. -> (ops, removed)"""
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
    """Remove text objects that consist only of {{…}} from the template – also in form XObjects. Returns the count."""
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


def _read_template(src: str, s: VdpSettings):
    """Read the template once: page sizes, trim and bleed, the fields from {{placeholders}}, and the pages
    themselves unrotated from (0, 0) – field coordinates then refer to the visible page.
    -> (sizes, pdf bytes, trims, bleeds, placeholder fields)"""
    import pypdfium2 as pdfium
    from .objects import normalized
    from .layout import page_trims, page_doc_bleeds

    src_doc = pdfium.PdfDocument(src)
    try:
        trims, bleeds = page_trims(src_doc), page_doc_bleeds(src_doc)  # take trim size/bleed along
        norm = normalized(src_doc)  # unrotated, from (0,0): field coordinates = visible page
    finally:
        src_doc.close()
    try:
        ph_extra = []
        if s.placeholders:
            ph_extra = placeholder_fields(norm)
        sizes = [norm.get_page_size(i) for i in range(len(norm))]
        buf = io.BytesIO()
        norm.save(buf)
    finally:
        norm.close()
    return sizes, buf.getvalue(), trims, bleeds, ph_extra


def _fields_with_pages(s: VdpSettings, fields: list, ph_extra: list, npages: int):
    """The fields to draw and, for each, the set of template pages it appears on. -> (fields, pages_of)"""
    if window_mode(s):
        # window mode: the set of pages comes from the window, not from the individual field
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
    return fields, pages_of


def _output_sequence(s: VdpSettings, recs: list, tpl: list) -> list:
    """Order of the output pages: [(record index, template page), …]."""
    if window_mode(s):
        # window mode: every record one complete round over the template pages;
        # "page by page" remains available as a sort order via order == "page".
        # order == "each": no duplicates – per record the next pages_per_record pages of the template.
        if getattr(s, "order", "") == "each":
            g = max(1, int(getattr(s, "pages_per_record", 1) or 1))
            seq = [(min(p // g, len(recs) - 1), p) for p in tpl]
        else:
            seq = sequence("page" if s.order == "page" else "record", len(recs), tpl)
    else:
        seq = sequence(s.order, len(recs), tpl, s.pages_per_record)
    return seq


def _draw_overlays(s: VdpSettings, fields, pages_of, recs, seq, sizes, progress=None, cancel=None):
    """All overlays in one PDF, one page per output page. -> (pdf bytes, Images, log rows)"""
    from reportlab.pdfgen import canvas

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
                    where = (
                        tr("Zeile {0}").format(rec["_row"]) if rec.get("_row") else tr("Datensatz {0}").format(r + 1)
                    )
                    raise ValueError(f"{where} · {_field_label(f, fi)}: {msg}")
                v = v or ""
            vals[fi] = v
            images.page = k
            draw_field(cv, f, v, H, images)
        cv.showPage()
        if vals:
            log.append((k + 1, r, p, vals))
    cv.save()
    return ov.getvalue(), images, log


def _assemble(template: bytes, overlays: bytes, images, seq, sizes, trims, bleeds, strip: bool):
    """Copy the template per output page and put its overlay on top. strip = remove the {{placeholder}} text.
    -> (pdf bytes, number of placeholders removed)"""
    import pikepdf

    base = pikepdf.open(io.BytesIO(template))
    removed = _remove_placeholder_text(base) if strip else 0
    over = pikepdf.open(io.BytesIO(overlays))
    images.attach(over)  # attach vector PDF images to their pages
    out = pikepdf.new()
    # template once per page as a form XObject; every output page = template + its own overlay (small, separate)
    base_x = [out.copy_foreign(base.pages[p].as_form_xobject()) for p in range(len(sizes))]
    for k, (r, p) in enumerate(seq):
        W, H = sizes[p]
        ox = out.copy_foreign(over.pages[k].as_form_xobject())
        res = pikepdf.Dictionary(XObject=pikepdf.Dictionary(B=base_x[p], O=ox))
        pg = pikepdf.Dictionary(
            Type=pikepdf.Name.Page,
            MediaBox=[0, 0, W, H],
            Resources=res,
            Contents=out.make_stream(b"q /B Do Q q /O Do Q"),
        )
        t = trims[p] if p < len(trims) else None
        if t:
            pg.TrimBox = [t[0], t[1], W - t[2], H - t[3]]
            b = bleeds[p] if p < len(bleeds) else 0.0
            pg.BleedBox = [t[0] - b, t[1] - b, W - t[2] + b, H - t[3] + b] if b > 0 else [0, 0, W, H]
        out.pages.append(pikepdf.Page(out.make_indirect(pg)))
    data = io.BytesIO()
    out.save(data, object_stream_mode=pikepdf.ObjectStreamMode.generate)
    for d in (out, over, base):
        d.close()
    images.close()
    return data.getvalue(), removed


def _write_log(s: VdpSettings, fields: list, log: list):
    """CSV log: which record and which values went onto which output page."""
    with open(s.log_path, "w", newline="", encoding="utf-8-sig") as fh:
        wr = csv.writer(fh, delimiter=";")
        wr.writerow(
            [tr("Ausgabeseite"), tr("Datensatz"), tr("Vorlagenseite")]
            + [f"{i + 1}:{f.kind}" for i, f in enumerate(fields)]
        )
        for page_no, r, p, vals in log:
            wr.writerow([page_no, r + 1, p + 1] + [vals.get(i, "") for i in range(len(fields))])


def _advance_counter(s: VdpSettings, recs: list):
    """Continuous numbering: remember where the next run goes on."""
    nb = s.numbering if isinstance(s.numbering, Numbering) else Numbering(**(s.numbering or {}))
    if nb.continue_key and recs:
        last = max(rec["_n"] for rec in recs) if nb.step >= 0 else min(rec["_n"] for rec in recs)
        _save_counter(nb.continue_key, last + nb.step)


def build(src: str, s: VdpSettings, progress=None, cancel=None, pages=None, strip=False) -> tuple[bytes, dict]:
    """Output PDF (bytes) + info. pages = only these template pages (0-based, None = all).
    progress(done, total, text); cancel() -> True aborts.
    """
    fields = _fields(s)
    if not getattr(s, "doc_name", ""):
        import dataclasses

        s = dataclasses.replace(s, doc_name=os.path.basename(src))
    sizes, template, trims, bleeds, ph_extra = _read_template(src, s)
    if s.placeholders and not window_mode(s):
        fields = fields + ph_extra
    if not fields and not window_mode(s):
        raise ValueError(tr("Keine Felder angelegt."))
    cols, recs = records(s)
    if not recs:
        raise ValueError(tr("Keine Datensätze (CSV leer oder Anzahl 0)."))
    npages = len(sizes)
    fields, pages_of = _fields_with_pages(s, fields, ph_extra, npages)
    tpl = [p for p in (pages if pages else range(npages)) if 0 <= p < npages]
    if not tpl:
        raise ValueError(tr("Keine Seiten ausgewählt."))
    seq = _output_sequence(s, recs, tpl)
    overlays, images, log = _draw_overlays(s, fields, pages_of, recs, seq, sizes, progress, cancel)
    if progress is not None:
        progress(len(seq), len(seq), tr("Schreibe PDF …"))
    data, removed = _assemble(template, overlays, images, seq, sizes, trims, bleeds, bool(s.placeholders or strip))
    if s.log_path:
        _write_log(s, fields, log)
    _advance_counter(s, recs)
    info = {"records": len(recs), "pages": len(seq), "placeholders_removed": removed, "columns": cols}
    return data, info


def _preview_value(f: VdpField, rec: dict, base: str, images: Images) -> str:
    """Content for the preview; image fields get the resolved path (image missing: empty)."""
    v = field_value(f, rec)
    if f.kind == "image":
        v = pick_image(f, v, base, images)[0] or ""
    return v


def page_for_record(s: VdpSettings, record: int, npages: int) -> int:
    """First template page of record ``record`` (only defined for order == "each")."""
    g = max(1, int(getattr(s, "pages_per_record", 1) or 1))
    return (record * g) % max(1, npages) if s.order == "each" else -1


def preview(src_doc, page: int, s: VdpSettings, record: int = 0):
    """One page with the fields of the chosen record – as a pypdfium2 document (for the preview)."""
    import pypdfium2 as pdfium
    import tempfile

    s2 = VdpSettings(**{k: v for k, v in asdict(s).items()})
    s2.numbering = s.numbering if isinstance(s.numbering, Numbering) else Numbering(**(s.numbering or {}))
    s2.log_path = ""
    nb = s2.numbering
    s2.numbering = Numbering(**{**asdict(nb), "continue_key": ""})
    if nb.continue_key:  # the preview does not count on but shows the state
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
    # insert a fixed record: number/columns as template constants
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
    s2.windows = []  # The fields are already filtered by window/page and pre-filled –
    # otherwise build() would resolve the windows against the 1-page intermediate PDF
    # again (odd = page 1, even = nothing) and falsify the output.
    s2.placeholders = False
    if not fl:
        return pdfium.PdfDocument(one), len(recs)
    data, _info = build(one, s2, strip=s.placeholders)
    return pdfium.PdfDocument(data), len(recs)
