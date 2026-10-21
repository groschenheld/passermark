# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Printer integration via CUPS (pycups).

Strategy:
  * Queue with a PPD (vendor driver like escpr2 / Canon UFR II): read ALL PPD options
    generically -> full driver functionality without per-driver implementations.
  * Queue without a PPD (pure IPP / CUPS 3): *-supported attributes as options.

The queue defaults in CUPS are NEVER changed by this module. Options are sent
in full with every job.
"""
from __future__ import annotations

from . import papersizes
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

# options the program handles itself or that must never be sent along
SKIP_KEYS = {"PageRegion", "number-up", "fit-to-page", "print-scaling",
             "copies", "collate", "page-ranges", "orientation-requested"}

# candidates for the "basic" fields (manufacturers name them differently)
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

# fallback table (mm, portrait) for paper names if the driver provides no sizes – one table for the whole
# program (papersizes.py). prefix "T" or ".Borderless"/"FULL" = borderless (same size, no margin).
STD_SIZES_MM = papersizes.PAPER_MM


def std_size(name: str):
    """(w, h, borderless) in pt for a paper name like 'A3', 'TA4', 'A4.Borderless', 'DIN A4', 'Custom.85x55mm'
        or a display text with the size in it ("10 x 15 cm (4 x 6 in)") – or None."""
    raw = str(name or "")
    n = raw.upper().replace(" ", "")
    borderless = bool(re.search(r"borderless|randlos|full\s*bleed|sans\s*marges|sin\s*bordes", raw, re.I))
    for suf in (".BORDERLESS", ".FULLBLEED", ".FB", "_BORDERLESS"):
        if n.endswith(suf):
            n, borderless = n[: -len(suf)], True
    base = n.split(".")[0] if not n.startswith("CUSTOM.") else n
    if papersizes.lookup(base) is None and base.startswith("T") and papersizes.lookup(base[1:]) is not None:
        base, borderless = base[1:], True
    if base.endswith("FULL"):
        borderless = True
    mm = papersizes.lookup(base)
    if mm is None:
        mm = papersizes.lookup(re.sub(r"\(.*\)", "", raw).strip())       # "A4 (Borderless)", "JIS B4"
    if mm is not None:
        return mm[0] * 72 / 25.4, mm[1] * 72 / 25.4, borderless
    pt = papersizes.size_from_text(raw)
    if pt is None:
        return None
    return pt[0], pt[1], borderless


_PPD_ENTRY = re.compile(r'^\*(PaperDimension|ImageableArea|PageSize|PageRegion)\s+([^/:\s]+)(?:/([^:\n]*))?:\s*"([^"]*)"',
                        re.M)
_PS_PAGESIZE = re.compile(r"/PageSize\s*\[\s*([^\]]*?)\s*\]")


def _ppd_numbers(text: str, n: int, comma_ok: bool):
    """n numbers from a PPD value. Comma as decimal separator (\"636,75 905,6\") -> (numbers, True)."""
    toks = text.split()
    if len(toks) < n:
        return None, False
    comma = any("," in t for t in toks[:n])
    if comma and not comma_ok:
        return None, True
    try:
        return [float(t.replace(",", ".")) for t in toks[:n]], comma
    except ValueError:
        return None, comma


def parse_ppd_sizes(path: str) -> dict:
    """Paper sizes straight from the PPD file (more reliable than pycups), from every place a PPD states them:
        {"dims": {name: (w, h)} from *PaperDimension, "areas": {name: (l, b, r, t)} from *ImageableArea,
         "code": {name: (w, h)} from the PostScript code of *PageSize/*PageRegion (<</PageSize[w h]>>),
         "texts": {name: display text}, "problems": {name: [message, …]}} – sizes in pt."""
    out = {"dims": {}, "areas": {}, "code": {}, "texts": {}, "problems": {}}
    try:
        with open(path, "rb") as f:
            text = f.read().decode("latin-1")
    except OSError:
        return out

    def problem(name, msg):
        out["problems"].setdefault(name, [])
        if msg not in out["problems"][name]:
            out["problems"][name].append(msg)
    for m in _PPD_ENTRY.finditer(text):
        kind, name, label, val = m.group(1), m.group(2), (m.group(3) or "").strip(), m.group(4)
        if kind == "PaperDimension":
            nums, comma = _ppd_numbers(val, 2, True)
            if comma:
                problem(name, tr("*PaperDimension mit Komma statt Punkt"))
            if nums and nums[0] > 0 and nums[1] > 0:
                out["dims"][name] = (nums[0], nums[1])
        elif kind == "ImageableArea":
            nums, comma = _ppd_numbers(val, 4, True)
            if comma:
                problem(name, tr("*ImageableArea mit Komma statt Punkt"))
            if nums and nums[2] > nums[0] and nums[3] > nums[1]:
                out["areas"][name] = tuple(nums)
        else:
            if label and kind == "PageSize":
                out["texts"].setdefault(name, label)
            pm = _PS_PAGESIZE.search(val)
            if pm:
                nums, comma = _ppd_numbers(pm.group(1), 2, True)
                if comma:
                    problem(name, tr("*{0} mit Komma statt Punkt – PostScript braucht „{1}“").format(
                        kind, " ".join(f"{v:g}" for v in nums) if nums else "…"))
                if nums and nums[0] > 0 and nums[1] > 0:
                    out["code"].setdefault(name, (nums[0], nums[1]))
    return out


def parse_ppd_dimensions(path: str):
    """*PaperDimension / *ImageableArea from the PPD file -> (dims, areas)."""
    d = parse_ppd_sizes(path)
    return d["dims"], d["areas"]


def ppd_lines(name: str, w: float, h: float, area=None) -> str:
    """The PPD lines that make a paper size known (for the warning): pt with a decimal point."""
    l, b, r, t = area or (0.0, 0.0, w, h)
    f = lambda v: f"{v:.2f}".rstrip("0").rstrip(".")
    return (f'*PaperDimension {name}/{name}: "{f(w)} {f(h)}"\n'
            f'*ImageableArea {name}/{name}: "{f(l)} {f(b)} {f(r)} {f(t)}"')


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
    uri: str = ""                 # device address (Linux: device-uri, Windows: port)

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
    # woher die Maße je Papierformat stammen: "driver" (PaperDimension/Treiber), "code" (PostScript-Code der PPD),
    # "text" (im Namen/Anzeigetext), "table" (eingebaute Tabelle) – fehlt ein Format hier, sind die Maße unbekannt
    size_source: dict[str, str] = field(default_factory=dict)
    size_problems: dict[str, list] = field(default_factory=dict)  # PPD-Fehler je Format (Komma statt Punkt …)
    _ppd: object = None

    # ------------------------------------------------------------------ #
    def defaults(self) -> dict[str, str]:
        return {k: o.default for k, o in self.options.items() if not o.installable}

    def sheet_for(self, values: dict[str, str]):
        """(width, height, imageable) for the currently selected paper size."""
        w, h, ia, _exact = self.sheet_info(values)
        return w, h, ia

    def sheet_info(self, values: dict[str, str]):
        """Like sheet_for, plus whether the size is really known (False = fallback A4)."""
        key = self.roles.get("pagesize")
        val = values.get(key) if key else None
        if self.backend == "win" and val is not None and not str(val).startswith(CUSTOM_PREFIX):
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
            if std is None and key in self.options:      # try via the display text ("DIN A3")
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
        """Complete, deterministic set of options for the job.

                ALL driver options are sent (not only changed ones), so that
                neither ~/.cups/lpoptions nor later queue changes can interfere.
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
PDF_DOC_SIZE = "DOC"                # „Als PDF speichern“: Blatt = Größe der ersten gewählten Seite
PDF_SIZES = ["A0", "A1", "A2", "A3", "A4", "A5", "A6", "A3+", "SRA4", "SRA3", "SRA2", "LETTER", "LEGAL", "TABLOID"]


def pdf_target_info() -> "PrinterInfo":
    return PrinterInfo(name=PDF_TARGET, info=tr("Als PDF speichern (Farben unverändert)"), location="",
                       model="Passermark", state=3, state_message="", is_default=False)


def pdf_caps() -> "PrinterCaps":
    """Virtueller Drucker: ausgeschossenes Ergebnis als PDF-Datei – ohne Farbkonvertierung, vektoriell."""
    caps = PrinterCaps(name=PDF_TARGET, backend="pdf")
    choices = [Choice(PDF_DOC_SIZE, tr("Wie Dokument (erste gewählte Seite)"))]
    for n in PDF_SIZES:
        w, h, _b = std_size(n)
        label = {"LETTER": "Letter", "LEGAL": "Legal", "TABLOID": "Tabloid"}.get(n, n)
        choices.append(Choice(n, f"{label} ({w / 72 * 25.4:.0f} × {h / 72 * 25.4:.0f} mm)"))
        caps.page_sizes[n] = (w, h)
        caps.imageable[n] = (0.0, 0.0, w, h)          # kein Druckerrand
    caps.options["PageSize"] = Option("PageSize", tr("Papierformat"), tr("Allgemein"), choices, PDF_DOC_SIZE)
    caps.groups.append(("pdf", tr("Allgemein"), ["PageSize"]))
    caps.roles["pagesize"] = "PageSize"
    return caps


# --------------------------------------------------------------------------- #
# Sonderformate (vom Benutzer angelegt, dauerhaft gespeichert)
# --------------------------------------------------------------------------- #
CUSTOM_PREFIX = "Custom."
_MMPT = 72.0 / 25.4


def custom_value(w_mm: float, h_mm: float) -> str:
    """Paper value as in CUPS/PPD: Custom.85x55mm (width × height)."""
    return f"{CUSTOM_PREFIX}{w_mm:g}x{h_mm:g}mm"


def parse_custom(val) -> tuple[float, float] | None:
    m = re.fullmatch(r"Custom\.([0-9.]+)x([0-9.]+)mm", str(val or ""))
    if not m:
        return None
    try:
        w, h = float(m.group(1)), float(m.group(2))
    except ValueError:
        return None
    return (w, h) if w > 0 and h > 0 else None


def load_custom_sizes() -> list[dict]:
    """[{"name": …, "w": mm, "h": mm}] aus den Benutzereinstellungen."""
    from . import l10n
    out = []
    for e in l10n.load_settings().get("custom_sizes", []) or []:
        try:
            w, h = float(e["w"]), float(e["h"])
            if w > 0 and h > 0:
                out.append({"name": str(e.get("name") or "").strip() or f"{w:g} × {h:g} mm", "w": w, "h": h})
        except (KeyError, TypeError, ValueError):
            continue
    return out


def save_custom_sizes(sizes: list[dict]) -> None:
    from . import l10n
    st = l10n.load_settings()
    st["custom_sizes"] = [{"name": e["name"], "w": float(e["w"]), "h": float(e["h"])} for e in sizes]
    l10n.save_settings(st)


def apply_custom_sizes(caps: "PrinterCaps", sizes: list[dict] | None = None) -> None:
    """Hook custom sizes into "Save as PDF" (replacing previous ones).
        Custom paper sizes are for PDF export only – devices reject them
        (no fallback to a standard size on some printers, e.g. Canon).
    """
    if caps.backend != "pdf":
        return                              # NEU: Geräte bekommen keine ★-Formate mehr
    sizes = load_custom_sizes() if sizes is None else sizes
    key = caps.roles.get("pagesize")
    if not key or key not in caps.options:
        return
    opt = caps.options[key]
    opt.choices = [c for c in opt.choices if not str(c.value).startswith(CUSTOM_PREFIX)]
    for k in [k for k in caps.page_sizes if str(k).startswith(CUSTOM_PREFIX)]:
        caps.page_sizes.pop(k, None)
        caps.imageable.pop(k, None)
    # take the printer margins from the standard size (the driver often does not know custom sizes in advance)
    margins = None
    if caps.backend != "pdf":
        ref = opt.default if opt.default in caps.imageable else next(iter(caps.imageable), None)
        if ref is not None and ref in caps.page_sizes:
            W, H = caps.page_sizes[ref]
            l, b, r, t = caps.imageable[ref]
            margins = (l, b, W - r, H - t)
        else:
            margins = (12.0, 12.0, 12.0, 12.0)
    for e in sizes:
        v = custom_value(e["w"], e["h"])
        w, h = e["w"] * _MMPT, e["h"] * _MMPT
        opt.choices.append(Choice(v, f"★ {e['name']} ({e['w']:g} × {e['h']:g} mm)"))
        caps.page_sizes[v] = (w, h)
        if margins is None:
            caps.imageable[v] = (0.0, 0.0, w, h)
        else:
            ml, mb, mr, mt = margins
            caps.imageable[v] = (ml, mb, w - mr, h - mt)


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
def fill_page_sizes(caps: "PrinterCaps", opt: "Option", dims: dict, areas: dict, code: dict | None = None,
                    problems: dict | None = None) -> None:
    """Maße für jedes Papierformat des Treibers – immer zuerst vom Drucker selbst:
        1. Treiber (*PaperDimension bzw. das, was das Backend meldet)   -> "driver"
        2. PostScript-Code der PPD (<</PageSize[w h]>>)                 -> "code"
        3. im Namen oder Anzeigetext ("10 x 15 cm", "Custom.225x320mm") -> "text"
        4. eingebaute Tabelle (SRA4, DIN A4, JIS B4 …)                  -> "table"
        Bedruckbarer Bereich: vom Treiber; bei Maßen nicht vom Treiber: randlos = ganzes Blatt, sonst die Ränder,
        die der Drucker bei seinen anderen Formaten hat (Median), sonst 12 pt."""
    code, problems = code or {}, problems or {}
    margins = []
    for v, (l, b, r, t) in areas.items():
        if v in dims:
            w, h = dims[v]
            margins.append((l, b, w - r, h - t))
    med = None
    if margins:
        med = tuple(sorted(m[i] for m in margins)[len(margins) // 2] for i in range(4))
    for ch in opt.choices:
        v = ch.value
        if problems.get(v):
            caps.size_problems[v] = list(problems[v])
        size, src = dims.get(v), "driver"
        if size is None and v in code:
            size, src = code[v], "code"
        std = None
        if size is None:
            pt = papersizes.size_from_text(v) or papersizes.size_from_text(ch.text)
            if pt:
                size, src = pt, "text"
        if size is None:
            std = std_size(v) or std_size(ch.text)
            if std:
                size, src = (std[0], std[1]), "table"
        if size is None:
            continue
        w, h = size
        caps.page_sizes[v] = (w, h)
        caps.size_source[v] = src
        if v in areas:
            caps.imageable[v] = areas[v]
            continue
        if src == "driver":                          # Treiber nennt die Größe, aber keinen Bereich: wie bisher offen
            continue
        borderless = (std or std_size(v) or std_size(ch.text) or (0, 0, False))[2] or bool(
            re.search(r"borderless|randlos|full\s*bleed", ch.text, re.I))
        if borderless:
            caps.imageable[v] = (0.0, 0.0, w, h)
        else:
            l, b, r, t = med or (12.0, 12.0, 12.0, 12.0)
            if w - l - r > 36 and h - b - t > 36:
                caps.imageable[v] = (l, b, w - r, h - t)


def find_paper(caps: "PrinterCaps", w: float, h: float, tol: float = 2 * 72 / 25.4) -> str | None:
    """Papierformat des Treibers für w × h pt (beide Lagen, Toleranz 2 mm) – ohne Randlos-/Sondervarianten
        bevorzugt, sonst der kürzeste Name. None = keins."""
    key = caps.roles.get("pagesize")
    if not key or key not in caps.options:
        return None
    vals = {c.value for c in caps.options[key].choices}
    hits = [v for v, (pw, ph) in caps.page_sizes.items() if v in vals and
            ((abs(pw - w) <= tol and abs(ph - h) <= tol) or (abs(pw - h) <= tol and abs(ph - w) <= tol))]
    if not hits:
        return None
    plain = [v for v in hits if not re.search(r"borderless|fullbleed|full.bleed|randlos|\.", v, re.I)
             and not (v[:1] == "T" and v[1:] in hits)]
    return sorted(plain or hits, key=lambda v: (len(v), v))[0]


def size_note(caps: "PrinterCaps", values: dict, label: str = "") -> str:
    """Warnung für den Druckdialog, wenn die Maße des gewählten Papierformats fehlen, ungenau sind oder die PPD
        Fehler hat – mit den PPD-Zeilen, die es beheben (pt, Dezimalpunkt). "" = alles in Ordnung.
        „Als PDF speichern“ mit „Wie Dokument“ hat absichtlich keine feste Größe – keine Warnung."""
    key = caps.roles.get("pagesize")
    value = values.get(key) if key else None
    if value is None or (caps.backend == "pdf" and value == PDF_DOC_SIZE):
        return ""
    label = label or str(value)
    probs = caps.size_problems.get(value) or []
    src = caps.size_source.get(value)
    if not caps.sheet_info(values)[3]:
        msg = tr("⚠ Maße für Papierformat „{0}“ unbekannt – A4 angenommen. Bitte Treiber/PPD prüfen.").format(label)
        if caps.backend == "ppd":
            msg += "\n" + tr("In der PPD fehlt z. B.: {0}").format(
                f'*PaperDimension {value}/{value}: "<{tr("Breite")}> <{tr("Höhe")}>" (pt)')
        return msg
    if not probs and src not in ("text", "table"):
        return ""
    w, h, _ia, _ok = caps.sheet_info(values)
    parts = list(probs)
    if src in ("text", "table"):
        parts.append(tr("Maße für „{0}“ ({1:.1f} × {2:.1f} mm) nicht vom Treiber, sondern aus {3}").format(
            label, w / papersizes.PT, h / papersizes.PT,
            tr("dem Namen") if src == "text" else tr("der eingebauten Formattabelle")))
    msg = "⚠ " + "; ".join(parts) + "."
    if caps.backend == "ppd":
        msg += "\n" + tr("Für die PPD:") + "\n" + ppd_lines(value, w, h, caps.imageable.get(value))
    return msg


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

    info = parse_ppd_sizes(ppd_file)
    dims, areas = dict(info["dims"]), dict(info["areas"])
    ps = caps.options.get("PageSize")
    if ps:
        for ch in ps.choices:                       # pycups kennt manchmal mehr (eingebundene Dateien)
            if ch.value not in dims:
                try:
                    dim = ppd.findAttr("PaperDimension", ch.value)
                    w, h = (float(v) for v in dim.value.replace(",", ".").split()[:2])
                    dims[ch.value] = (w, h)
                except Exception:
                    pass
            if ch.value not in areas:
                try:
                    ia = ppd.findAttr("ImageableArea", ch.value)
                    areas[ch.value] = tuple(float(v) for v in ia.value.replace(",", ".").split()[:4])
                except Exception:
                    pass
        fill_page_sizes(caps, ps, dims, areas, info["code"], info["problems"])
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
        sz, src = _media_size(ch.value), "driver"          # PWG-Name: iso_a4_210x297mm
        if not sz:                                          # sonst: Name/Text („Custom.225x320mm“, „A4“ …)
            sz, src = papersizes.size_from_text(ch.value) or papersizes.size_from_text(ch.text), "text"
        if not sz:
            std = std_size(ch.value) or std_size(ch.text)
            sz, src = ((std[0], std[1]) if std else None), "table"
        if sz:
            w, h = sz
            caps.page_sizes[ch.value] = (w, h)
            caps.size_source[ch.value] = src
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
