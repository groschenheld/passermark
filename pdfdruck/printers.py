# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Druckeranbindung über CUPS (pycups).

Strategie:
  * Queue mit PPD (Herstellertreiber wie escpr2 / Canon UFR II): ALLE PPD-Optionen
    generisch auslesen -> komplette Treiberfunktionalität ohne Einzelimplementierung.
  * Queue ohne PPD (reines IPP / CUPS 3): *-supported-Attribute als Optionen.

Die Queue-Defaults in CUPS werden von diesem Modul NIE verändert. Optionen werden
pro Job vollständig mitgeschickt.
"""
from __future__ import annotations

from .l10n import tr

import os
import re
import sys
from dataclasses import dataclass, field

from . import i18n

try:
    import cups  # python3-cups / pycups
except ImportError:  # erlaubt Import ohne CUPS (Tests, Doku)
    cups = None

INSTALLABLE_GROUP = "InstallableOptions"

# Optionen, die das Programm selbst regelt bzw. die nie mitgeschickt werden dürfen
SKIP_KEYS = {"PageRegion", "number-up", "fit-to-page", "print-scaling",
             "copies", "collate", "page-ranges", "orientation-requested"}

# Kandidaten für die "Basis"-Felder (Hersteller benennen unterschiedlich)
ROLE_KEYS = {
    "pagesize": ["PageSize", "media"],
    "source": ["InputSlot", "MediaSource", "media-source", "CNInputSlot", "EPIJ_FdSo"],
    "mediatype": ["MediaType", "media-type", "CNMediaType", "EPIJ_MdTy"],
    "duplex": ["Duplex", "CNDuplex", "sides", "EPIJ_Dupl", "JCLDuplex"],
    "color": ["ColorModel", "CNColorMode", "print-color-mode", "ColorMode", "Ink", "EPIJ_Colo"],
    "quality": ["cupsPrintQuality", "print-quality", "Resolution", "EPIJ_Qual", "CNQuality"],
    "outputbin": ["OutputBin", "output-bin", "CNOutputPartition"],
}
ROLE_TEXT = {
    "source": re.compile(r"(papier(zufuhr|quelle|fach)|zufuhr|source|tray|kassette|cassette)", re.I),
    "mediatype": re.compile(r"(medien|papier)(typ|art)|media\s*type|paper\s*type", re.I),
    "duplex": re.compile(r"duplex|beidseitig|2-sided|two-sided", re.I),
    "color": re.compile(r"farb(modus|e)|colou?r\s*mode|grayscale|graustufen|\bink\b", re.I),
}

# Rückfall-Tabelle (mm, Hochformat) für Papiernamen, falls der Treiber keine Maße liefert.
# Präfix "T" bzw. ".Borderless"/"FULL" = randlos (gleiches Maß, kein Rand).
STD_SIZES_MM = {
    "A0": (841, 1189), "A1": (594, 841), "A2": (420, 594), "A3": (297, 420), "A4": (210, 297),
    "A5": (148, 210), "A6": (105, 148), "A3+": (329, 483), "SRA3": (320, 450), "B4": (257, 364),
    "B5": (182, 257), "B6": (128, 182), "LETTER": (215.9, 279.4), "LEGAL": (215.9, 355.6),
    "TABLOID": (279.4, 431.8), "LEDGER": (279.4, 431.8), "EXECUTIVE": (184.2, 266.7),
    "4X6": (101.6, 152.4), "4X6FULL": (101.6, 152.4), "4X7": (101.6, 177.8), "5X7": (127, 177.8),
    "8X10": (203.2, 254), "2L": (127, 178), "L": (89, 127), "INDEX5": (127, 203.2),
    "POSTCARD": (100, 148), "ENV10": (104.8, 241.3), "ENVDL": (110, 220), "DL": (110, 220),
    "ENVC4": (229, 324), "ENVC4P": (229, 324), "C4": (229, 324), "ENVC5": (162, 229), "C5": (162, 229),
    "ENVC6": (114, 162), "C6": (114, 162), "8K": (270, 390), "16K": (195, 270),
}


def std_size(name: str):
    """(w, h, randlos) in pt für einen Papiernamen wie 'A3', 'TA4', 'A4.Borderless' – oder None."""
    n = name.upper().replace(" ", "")
    borderless = False
    for suf in (".BORDERLESS", ".FULLBLEED", ".FB", "_BORDERLESS"):
        if n.endswith(suf):
            n, borderless = n[: -len(suf)], True
    n = n.split(".")[0]
    if n not in STD_SIZES_MM and n.startswith("T") and n[1:] in STD_SIZES_MM:
        n, borderless = n[1:], True
    if n.endswith("FULL"):
        borderless = True
    mm = STD_SIZES_MM.get(n)
    if mm is None:
        m = re.fullmatch(r"(?:CUSTOM\.)?(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)(MM|IN|CM)?", n)
        if not m:
            return None
        f = {"MM": 72 / 25.4, "CM": 72 / 2.54, "IN": 72.0, None: 1.0}[m.group(3)]
        return float(m.group(1)) * f, float(m.group(2)) * f, borderless
    return mm[0] * 72 / 25.4, mm[1] * 72 / 25.4, borderless


_PPD_DIM = re.compile(r'^\*(PaperDimension|ImageableArea)\s+([^/:\s]+)(?:/[^:]*)?:\s*"([^"]*)"')


def parse_ppd_dimensions(path: str):
    """Liest *PaperDimension / *ImageableArea direkt aus der PPD-Datei (zuverlässiger als pycups)."""
    dims, areas = {}, {}
    try:
        with open(path, "rb") as f:
            for raw in f:
                if not raw.startswith((b"*PaperDimension", b"*ImageableArea")):
                    continue
                m = _PPD_DIM.match(raw.decode("latin-1").strip())
                if not m:
                    continue
                try:
                    nums = [float(v) for v in m.group(3).split()]
                except ValueError:
                    continue
                if m.group(1) == "PaperDimension" and len(nums) >= 2:
                    dims[m.group(2)] = (nums[0], nums[1])
                elif m.group(1) == "ImageableArea" and len(nums) >= 4:
                    areas[m.group(2)] = tuple(nums[:4])
    except OSError:
        pass
    return dims, areas


IPP_QUALITY = {"3": "Entwurf", "4": "Normal", "5": "Hoch"}
IPP_FINISHINGS = {"3": "Keine", "4": "Heften", "5": "Lochen", "6": "Abdeckung", "7": "Binden",
                  "8": "Sattelheftung", "9": "Kantenheftung", "20": "Heften oben links",
                  "21": "Heften unten links", "22": "Heften oben rechts", "23": "Heften unten rechts",
                  "28": "Doppelheftung links", "29": "Doppelheftung oben", "74": "Lochung (2) links",
                  "75": "Lochung (2) oben", "80": "Lochung (4) links"}


@dataclass
class Choice:
    value: str
    text: str


@dataclass
class Option:
    keyword: str
    text: str
    group: str
    choices: list[Choice]
    default: str
    installable: bool = False


@dataclass
class PrinterInfo:
    name: str
    info: str
    location: str
    model: str
    state: int
    state_message: str
    is_default: bool
    uri: str = ""                 # Geräteadresse (Linux: device-uri, Windows: Anschluss)

    @property
    def state_text(self) -> str:
        return tr({3: "Bereit", 4: "Druckt", 5: "Angehalten"}.get(self.state, "Unbekannt"))


@dataclass
class PrinterCaps:
    name: str
    backend: str                                   # "ppd" | "ipp"
    options: dict[str, Option] = field(default_factory=dict)
    groups: list[tuple[str, str, list[str]]] = field(default_factory=list)
    page_sizes: dict[str, tuple[float, float]] = field(default_factory=dict)
    imageable: dict[str, tuple[float, float, float, float]] = field(default_factory=dict)
    roles: dict[str, str] = field(default_factory=dict)  # role -> keyword
    _ppd: object = None

    # ------------------------------------------------------------------ #
    def defaults(self) -> dict[str, str]:
        return {k: o.default for k, o in self.options.items() if not o.installable}

    def sheet_for(self, values: dict[str, str]):
        """(breite, höhe, imageable) für die aktuell gewählte Papiergröße."""
        w, h, ia, _exact = self.sheet_info(values)
        return w, h, ia

    def sheet_info(self, values: dict[str, str]):
        """Wie sheet_for, plus ob das Maß wirklich bekannt ist (False = Notlösung A4)."""
        key = self.roles.get("pagesize")
        val = values.get(key) if key else None
        if self.backend == "win" and val is not None:
            cache = self.__dict__.setdefault("_win_ia", {})
            if val not in cache:
                try:
                    from .printers_win import imageable_for
                    cache[val] = imageable_for(self.name, values)
                except Exception:
                    cache[val] = None
            if cache[val]:
                ia, (w, h) = cache[val]
                return w, h, ia, True
        if val is not None and val in self.page_sizes:
            w, h = self.page_sizes[val]
            return w, h, self.imageable.get(val), True
        if val is not None:
            std = std_size(val)
            if std is None and key in self.options:      # über den Anzeigetext versuchen ("DIN A3")
                txt = next((c.text for c in self.options[key].choices if c.value == val), "")
                std = std_size(txt.replace("DIN", "").strip())
            if std:
                w, h, borderless = std
                return w, h, (None if borderless else (12.0, 12.0, w - 12.0, h - 12.0)), True
        return 595.28, 841.89, None, False

    def conflicts(self, values: dict[str, str]) -> list[str]:
        """Liste der Optionen, die laut UIConstraints kollidieren (nur PPD)."""
        if self.backend != "ppd" or self._ppd is None:
            return []
        ppd = self._ppd
        ppd.markDefaults()
        for k, v in values.items():
            if k in self.options:
                ppd.markOption(k, v)
        if ppd.conflicts() == 0:
            return []
        bad = []
        for k in self.options:
            opt = ppd.findOption(k)
            if opt is not None and getattr(opt, "conflicted", False):
                bad.append(k)
        return bad

    def job_options(self, values: dict[str, str]) -> dict[str, str]:
        """Vollständiger, deterministischer Optionssatz für den Job.

        Es werden ALLE Treiberoptionen mitgeschickt (nicht nur geänderte), damit
        weder ~/.cups/lpoptions noch spätere Queue-Änderungen hineinpfuschen.
        """
        out = {}
        for k, opt in self.options.items():
            if opt.installable or k in SKIP_KEYS:
                continue
            v = values.get(k, opt.default)
            if v is not None and v != "":
                out[k] = str(v)
        return out


# --------------------------------------------------------------------------- #
PDF_TARGET = "__pdf__"
PDF_SIZES = ["A0", "A1", "A2", "A3", "A4", "A5", "A6", "A3+", "SRA3", "LETTER", "LEGAL", "TABLOID"]


def pdf_target_info() -> "PrinterInfo":
    return PrinterInfo(name=PDF_TARGET, info=tr("Als PDF speichern (Farben unverändert)"), location="",
                       model="Passermark", state=3, state_message="", is_default=False)


def pdf_caps() -> "PrinterCaps":
    """Virtueller Drucker: ausgeschossenes Ergebnis als PDF-Datei – ohne Farbkonvertierung, vektoriell."""
    caps = PrinterCaps(name=PDF_TARGET, backend="pdf")
    choices = [Choice("DOC", tr("Wie Dokument (erste gewählte Seite)"))]
    for n in PDF_SIZES:
        w, h, _b = std_size(n)
        label = {"LETTER": "Letter", "LEGAL": "Legal", "TABLOID": "Tabloid"}.get(n, n)
        choices.append(Choice(n, f"{label} ({w / 72 * 25.4:.0f} × {h / 72 * 25.4:.0f} mm)"))
        caps.page_sizes[n] = (w, h)
        caps.imageable[n] = (0.0, 0.0, w, h)          # kein Druckerrand
    caps.options["PageSize"] = Option("PageSize", tr("Papierformat"), tr("Allgemein"), choices, "DOC")
    caps.groups.append(("pdf", tr("Allgemein"), ["PageSize"]))
    caps.roles["pagesize"] = "PageSize"
    return caps


def _conn():
    if cups is None:
        raise RuntimeError(tr("pycups ist nicht installiert (Paket python3-cups)."))
    return cups.Connection()


def list_printers() -> list[PrinterInfo]:
    c = _conn()
    default = c.getDefault()
    out = []
    for name, a in sorted(c.getPrinters().items()):
        out.append(PrinterInfo(
            name=name,
            info=a.get("printer-info", "") or name,
            location=a.get("printer-location", ""),
            model=a.get("printer-make-and-model", ""),
            state=int(a.get("printer-state", 0)),
            state_message=a.get("printer-state-message", ""),
            is_default=(name == default),
            uri=a.get("device-uri", ""),
        ))
    return out


def load_caps(name: str) -> PrinterCaps:
    c = _conn()
    try:
        ppd_file = c.getPPD(name)
    except Exception:
        ppd_file = None
    if ppd_file:
        try:
            return _caps_from_ppd(name, ppd_file)
        finally:
            try:
                os.unlink(ppd_file)
            except OSError:
                pass
    return _caps_from_ipp(name, c)


# --------------------------------------------------------------------------- #
# PPD
# --------------------------------------------------------------------------- #
def _walk_groups(groups, prefix=""):
    for g in groups:
        yield g, prefix
        yield from _walk_groups(getattr(g, "subgroups", []) or [], prefix + g.text + " / ")


def _caps_from_ppd(name: str, ppd_file: str) -> PrinterCaps:
    ppd = cups.PPD(ppd_file)
    try:
        ppd.localize()
    except Exception:
        pass
    caps = PrinterCaps(name=name, backend="ppd", _ppd=ppd)
    for g, prefix in _walk_groups(ppd.optionGroups):
        keys = []
        installable = g.name == INSTALLABLE_GROUP
        for o in g.options:
            if o.keyword in SKIP_KEYS:
                continue
            choices = [Choice(ch["choice"], i18n.choice_text(o.keyword, ch["choice"], ch.get("text") or "", o.text or ""))
                       for ch in o.choices]
            if not choices:
                continue
            default = o.defchoice or choices[0].value
            caps.options[o.keyword] = Option(o.keyword, i18n.option_text(o.keyword, o.text or o.keyword),
                                             prefix + (i18n.option_text(g.name, g.text) if g.text else g.name),
                                             choices, default, installable)
            keys.append(o.keyword)
        if keys:
            caps.groups.append((g.name, prefix + (g.text or g.name), keys))

    dims, areas = parse_ppd_dimensions(ppd_file)
    ps = caps.options.get("PageSize")
    if ps:
        for ch in ps.choices:
            if ch.value in dims:
                caps.page_sizes[ch.value] = dims[ch.value]
                if ch.value in areas:
                    caps.imageable[ch.value] = areas[ch.value]
                continue
            try:
                dim = ppd.findAttr("PaperDimension", ch.value)
            except Exception:
                dim = None
            if dim is None:
                continue
            try:
                w, h = (float(v) for v in dim.value.split()[:2])
            except ValueError:
                continue
            caps.page_sizes[ch.value] = (w, h)
            try:
                ia = ppd.findAttr("ImageableArea", ch.value)
            except Exception:
                ia = None
            if ia is not None:
                try:
                    l, b, r, t = (float(v) for v in ia.value.split()[:4])
                    caps.imageable[ch.value] = (l, b, r, t)
                except ValueError:
                    pass
    _assign_roles(caps)
    return caps


# --------------------------------------------------------------------------- #
# IPP (ohne PPD)
# --------------------------------------------------------------------------- #
_MEDIA_RE = re.compile(r"_(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)(mm|in)$")


def _media_size(name: str):
    m = _MEDIA_RE.search(name)
    if not m:
        return None
    w, h, unit = float(m.group(1)), float(m.group(2)), m.group(3)
    f = 72.0 if unit == "in" else 72.0 / 25.4
    return w * f, h * f


def _as_list(v):
    if v is None:
        return []
    return list(v) if isinstance(v, (list, tuple)) else [v]


def _caps_from_ipp(name: str, c) -> PrinterCaps:
    want = ["media-supported", "media-default", "media-source-supported", "media-source-default",
            "media-type-supported", "media-type-default", "sides-supported", "sides-default",
            "print-color-mode-supported", "print-color-mode-default", "print-quality-supported",
            "print-quality-default", "output-bin-supported", "output-bin-default",
            "finishings-supported", "finishings-default",
            "media-bottom-margin-supported", "media-left-margin-supported",
            "media-right-margin-supported", "media-top-margin-supported"]
    a = c.getPrinterAttributes(name, requested_attributes=want)
    caps = PrinterCaps(name=name, backend="ipp")

    def add(key, text, labels=None):
        sup = [str(v) for v in _as_list(a.get(f"{key}-supported"))]
        if not sup:
            return
        dflt = _as_list(a.get(f"{key}-default"))
        dflt = str(dflt[0]) if dflt else sup[0]
        choices = [Choice(v, (labels or {}).get(v, v)) for v in sup]
        caps.options[key] = Option(key, text, tr("Allgemein"), choices, dflt)

    add("media", tr("Papierformat"))
    add("media-source", tr("Papierzufuhr"))
    add("media-type", tr("Medientyp"))
    add("sides", tr("Beidseitig"), {"one-sided": tr("Einseitig"), "two-sided-long-edge": tr("Beidseitig, lange Kante"),
                                       "two-sided-short-edge": tr("Beidseitig, kurze Kante")})
    add("print-color-mode", tr("Farbmodus"), {"color": tr("Farbe"), "monochrome": tr("Graustufen"),
                                              "auto": tr("Automatisch")})
    add("print-quality", tr("Qualität"), {k: tr(v) for k, v in IPP_QUALITY.items()})
    add("output-bin", tr("Ausgabefach"))
    add("finishings", tr("Endverarbeitung"), {k: tr(v) for k, v in IPP_FINISHINGS.items()})
    caps.groups.append(("ipp", tr("Allgemein"), list(caps.options)))

    def margin(k):
        vals = [int(v) for v in _as_list(a.get(f"media-{k}-margin-supported"))]
        return min(vals) * 72.0 / 2540.0 if vals else 0.0
    mb, ml, mr, mt = margin("bottom"), margin("left"), margin("right"), margin("top")
    for ch in caps.options.get("media", Option("", "", "", [], "")).choices:
        sz = _media_size(ch.value)
        if sz:
            w, h = sz
            caps.page_sizes[ch.value] = (w, h)
            caps.imageable[ch.value] = (ml, mb, w - mr, h - mt)
    _assign_roles(caps)
    return caps


# --------------------------------------------------------------------------- #
# Endverarbeitung: (Rolle, Muster) – Reihenfolge wichtig (Sattelheftung vor Heftung)
FINISH_ROLES = [
    ("saddle", re.compile(r"saddle|sattel|booklet|broschür", re.I)),
    ("staple", re.compile(r"stapl|heft", re.I)),
    ("punch", re.compile(r"punch|loch", re.I)),
    ("fold", re.compile(r"fold|falz", re.I)),
    ("trim", re.compile(r"trim|beschnitt|schneid", re.I)),
    ("stacker", re.compile(r"stacker|stapler|offset|versatz", re.I)),
]


def _assign_roles(caps: PrinterCaps):
    for role, cands in ROLE_KEYS.items():
        for k in cands:
            if k in caps.options and not caps.options[k].installable:
                caps.roles[role] = k
                break
        else:
            rx = ROLE_TEXT.get(role)
            if rx:
                for k, o in caps.options.items():
                    if not o.installable and k not in caps.roles.values() and rx.search(o.text):
                        caps.roles[role] = k
                        break
    for role, rx in FINISH_ROLES:
        for k, o in caps.options.items():
            if o.installable or k in caps.roles.values() or len(o.choices) < 2:
                continue
            if rx.search(k) or rx.search(o.text):
                caps.roles[role] = k
                break


def submit(printer: str, path: str, title: str, options: dict[str, str]) -> int:
    """Schickt den Job ab. Die Datei ist danach von CUPS gespoolt und kann weg."""
    return _conn().printFile(printer, path, title, options)


# --------------------------------------------------------------------------- #
# Windows: gleiche Schnittstelle, andere Anbindung (siehe printers_win.py)
# --------------------------------------------------------------------------- #
if sys.platform == "win32":
    from . import printers_win as _win   # noqa: E402

    list_printers = _win.list_printers   # type: ignore[assignment]  # noqa: F811
    load_caps = _win.load_caps           # type: ignore[assignment]  # noqa: F811
