# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Check profiles (1.20.2): which findings of the document check are reported how, and with which limits.

A profile has two parts:
- ``report``: check key -> "error" | "warning" | "info" | "off" (only the deviations from the default of the check)
- ``limits``: limit key -> number (only the deviations from LIMITS)

Built-in profiles (BUILTIN) cover the usual purposes; own profiles are JSON files in the profile folders (see
folders()). "standard" is exactly the check as it was before profiles existed. No Qt.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from .l10n import tr

SEVERITIES = ("error", "warning", "info", "off")
FOLDER = "checkprofiles"
FORMAT = "check-profile"

# key -> (category, default severity, label). "off" = only on in profiles that switch it on.
# The label is German like all source texts (translated with tr() where shown).
CHECKS: dict = {
    # fonts
    "font_missing": ("font", "error", "Schrift nicht eingebettet"),
    "font_std14": ("font", "info", "Standardschrift nicht eingebettet"),
    "font_type3": ("font", "info", "Type3-Schrift"),
    "font_unicode": ("font", "info", "Schrift ohne Unicode-Zuordnung"),
    "font_courier": ("font", "off", "Schrift Courier (oft Ersatzschrift)"),
    # text
    "text_garbled": ("text", "warning", "Zeichen ohne gültige Zuordnung"),
    "text_small": ("text", "warning", "Text kleiner als die Mindestschrift"),
    # images and colours
    "image_low": ("image", "warning", "Bilder unter der Mindestauflösung"),
    "image_ok": ("image", "info", "Bilder unter der empfohlenen Auflösung"),
    "image_high": ("image", "info", "Bilder über der Höchstauflösung"),
    "rgb": ("image", "info", "RGB-Inhalte"),
    "spot_colors": ("image", "info", "Sonderfarben (Liste)"),
    "spot_count": ("image", "warning", "Mehr Sonderfarben als erlaubt"),
    "hdr": ("image", "warning", "HDR-Zusatzseiten"),
    "ink_tac": ("ink", "warning", "Farbauftrag über der Grenze"),
    # lines, transparency, overprint
    "hairline": ("line", "warning", "Haarlinien"),
    "transparency_gradient": ("transparency", "warning", "Transparente Verläufe (Soft-Maske im Muster)"),
    "transparency": ("transparency", "info", "Transparenzen"),
    "overprint_used": ("transparency", "info", "Überdrucken verwendet"),
    "overprint_white": ("overprint", "error", "Weiß überdruckt"),
    "overprint_black_text": ("overprint", "warning", "Kleiner schwarzer Text spart aus"),
    # layers
    "layer_hidden": ("layer", "warning", "Ausgeblendete Ebenen"),
    "layer_print": ("layer", "warning", "Ebene: Ansicht und Druck verschieden"),
    "layer_outside": ("layer", "warning", "Ebene außerhalb der Seite"),
    # pages and page boxes
    "userunit": ("geometry", "error", "UserUnit (Seite skaliert)"),
    "cropbox": ("geometry", "warning", "Sichtbarer Bereich (CropBox) weicht ab"),
    "boxes": ("geometry", "warning", "Widersprüchliche Seitenrahmen"),
    "rotate": ("geometry", "info", "Seite gedreht"),
    "page_sizes": ("geometry", "info", "Unterschiedliche Seitenformate"),
    "bleed": ("geometry", "warning", "Zu wenig Anschnitt"),
    "safety": ("geometry", "warning", "Sicherheitsabstand zum Endformat"),
    "page_multiple": ("geometry", "warning", "Seitenzahl kein Vielfaches"),
    "blank_pages": ("page", "info", "Leere Seiten"),
    # document
    "print_forbidden": ("security", "error", "Drucken nicht erlaubt"),
    "print_lowres": ("security", "warning", "Nur niedrige Druckqualität erlaubt"),
    "encrypted": ("security", "info", "Verschlüsselt"),
    "pdfx_none": ("pdfx", "off", "Keine PDF/X-Angabe (Output-Intent)"),
    "pdfx_version": ("pdfx", "warning", "PDF/X-Version älter als verlangt"),
    "pdfx_intent": ("pdfx", "warning", "PDF/X ohne Output-Intent"),
    "pdfx_profile": ("pdfx", "warning", "Output-Intent ohne Profil"),
    "pdfx_trim": ("pdfx", "warning", "PDF/X ohne Endformat"),
    "forms": ("form", "info", "Formularfelder"),
    "file_size": ("size", "info", "Dateigröße"),
    "device": ("device", "warning", "Format passt nicht zum Drucker"),
}

# key -> (default, unit, label, minimum, maximum, "off" value). A limit at its "off" value switches the check off.
LIMITS: dict = {
    "image_ppi_min": (150.0, "ppi", "Mindestauflösung Bilder", 0.0, 2400.0, 0.0),
    "image_ppi_good": (300.0, "ppi", "Empfohlene Auflösung Bilder", 0.0, 2400.0, 0.0),
    "image_ppi_max": (0.0, "ppi", "Höchstauflösung Bilder", 0.0, 9600.0, 0.0),
    "lineart_ppi_min": (0.0, "ppi", "Mindestauflösung Strichbilder", 0.0, 4800.0, 0.0),
    "lineart_ppi_good": (0.0, "ppi", "Empfohlene Auflösung Strichbilder", 0.0, 4800.0, 0.0),
    "text_min_pt": (0.0, "pt", "Mindestschrift", 0.0, 24.0, 0.0),
    "black_text_pt": (12.0, "pt", "Schwarzer Text überdruckt bis", 0.0, 72.0, 0.0),
    "hairline_mm": (0.1, "mm", "Haarlinien dünner als", 0.0, 2.0, 0.0),
    "bleed_min_mm": (2.0, "mm", "Mindestanschnitt", 0.0, 20.0, 0.0),
    "safety_mm": (3.0, "mm", "Sicherheitsabstand", 0.0, 30.0, 0.0),
    "spot_max": (-1.0, "", "Höchstens Sonderfarben", -1.0, 50.0, -1.0),
    "page_multiple": (0.0, "", "Seitenzahl Vielfaches von", 0.0, 64.0, 0.0),
    "tac_max": (0.0, "%", "Höchster Farbauftrag", 0.0, 400.0, 0.0),
    "pdfx_min": (0.0, "", "PDF/X mindestens Version", 0.0, 4.0, 0.0),
}
# limits whose 0 means "automatic" instead of "off": line art (1 bit) then needs twice the image resolution
AUTO_ZERO = {"lineart_ppi_min", "lineart_ppi_good"}

# which limit switches which check off (limit at its "off" value -> check not run)
LIMIT_OF = {
    "image_low": "image_ppi_min",
    "image_ok": "image_ppi_good",
    "image_high": "image_ppi_max",
    "text_small": "text_min_pt",
    "overprint_black_text": "black_text_pt",
    "hairline": "hairline_mm",
    "bleed": "bleed_min_mm",
    "safety": "safety_mm",
    "spot_count": "spot_max",
    "page_multiple": "page_multiple",
    "ink_tac": "tac_max",
    "pdfx_version": "pdfx_min",
}


@dataclass
class Profile:
    """A check profile: name, label, description and the deviations from the defaults."""

    name: str
    label: str = ""
    description: str = ""
    report: dict = field(default_factory=dict)
    limits: dict = field(default_factory=dict)
    builtin: bool = False
    path: str = ""  # file of an own profile

    def severity(self, check: str) -> str:
        """Severity of ``check`` in this profile ("off" if it is not reported)."""
        sev = self.report.get(check) or CHECKS.get(check, ("", "warning", ""))[1]
        lim = LIMIT_OF.get(check)
        if lim and self.limit(lim) == LIMITS[lim][5]:
            return "off"
        return sev

    def limit(self, key: str) -> float:
        """Value of the limit ``key`` in this profile."""
        v = self.limits.get(key)
        return float(LIMITS[key][0] if v is None else v)

    def all_limits(self) -> dict:
        """All limits with their values in this profile."""
        return {k: self.limit(k) for k in LIMITS}

    def title(self) -> str:
        """Label for lists (translated for built-in profiles)."""
        return tr(self.label) if self.builtin and self.label else (self.label or self.name)

    def to_dict(self) -> dict:
        """As stored in a profile file (only the deviations)."""
        return {
            "passermark": FORMAT,
            "version": 1,
            "name": self.label or self.name,
            "description": self.description,
            "report": dict(sorted(self.report.items())),
            "limits": dict(sorted(self.limits.items())),
        }


def _p(name, label, description, report=None, limits=None) -> Profile:
    return Profile(name, label, description, dict(report or {}), dict(limits or {}), builtin=True)


BUILTIN: dict = {
    p.name: p
    for p in (
        _p(
            "standard",
            "Standard",
            "Die Prüfung wie bisher: alles Wichtige für Büro-, Digital- und Plandruck.",
        ),
        _p(
            "offset",
            "Offset (angelehnt an PDF/X-4)",
            "Für die Druckerei: Schriften eingebettet, CMYK, 300 ppi, mindestens 3 mm Anschnitt, Mindestschrift "
            "6 pt, Farbauftrag höchstens 300 %, PDF/X-Angabe erwartet. Angelehnt an PDF/X-4 – ersetzt keine "
            "zertifizierte Prüfung.",
            report={
                "font_std14": "error",
                "font_type3": "warning",
                "image_low": "error",
                "image_ok": "warning",
                "rgb": "warning",
                "pdfx_none": "warning",
                "layer_hidden": "error",
            },
            limits={
                "bleed_min_mm": 3.0,
                "text_min_pt": 6.0,
                "hairline_mm": 0.05,
                "image_ppi_max": 1200.0,
                "tac_max": 300.0,
            },
        ),
        _p(
            "gwg",
            "GWG Bogenoffset (angelehnt an GWG2015 SheetCmyk)",
            "Werte der Ghent Workgroup für Bogenoffset CMYK: PDF/X-4, keine RGB-Inhalte und Sonderfarben, Bilder "
            "ab 149 ppi (empfohlen 224), Strichbilder ab 549 ppi (empfohlen 799), Mindestschrift 8 pt, Linien ab "
            "0,25 pt, Farbauftrag höchstens 320 %, schwarzer Text bis 12 pt überdruckt, Weiß nie überdruckt. "
            "Ersetzt keine zertifizierte GWG-Prüfung.",
            report={
                "font_std14": "error",
                "font_type3": "warning",
                "font_courier": "warning",
                "image_low": "error",
                "image_ok": "warning",
                "rgb": "error",
                "spot_count": "error",
                "overprint_white": "error",
                "overprint_black_text": "warning",
                "page_sizes": "warning",
                "blank_pages": "warning",
                "layer_hidden": "error",
                "pdfx_none": "error",
                "pdfx_version": "error",
                "pdfx_intent": "error",
                "pdfx_profile": "error",
            },
            limits={
                "image_ppi_min": 149.0,
                "image_ppi_good": 224.0,
                "lineart_ppi_min": 549.0,
                "lineart_ppi_good": 799.0,
                "text_min_pt": 8.0,
                "hairline_mm": 0.088,
                "spot_max": 0.0,
                "tac_max": 320.0,
                "black_text_pt": 12.0,
                "pdfx_min": 4.0,
            },
        ),
        _p(
            "digital",
            "Digitaldruck / Büro",
            "Laser- und Digitaldruck: Bilder ab 150 ppi, RGB erlaubt, Mindestschrift 5 pt.",
            report={"image_ok": "off", "overprint_black_text": "info", "rgb": "off"},
            limits={"text_min_pt": 5.0},
        ),
        _p(
            "plot",
            "Plan- und Großformat",
            "Plotter und Großformat: Bilder ab 100 ppi, Haarlinien wichtig, Anschnitt und Überdrucken meist egal.",
            report={
                "image_ok": "off",
                "rgb": "off",
                "overprint_black_text": "off",
                "bleed": "off",
                "safety": "off",
                "hairline": "error",
            },
            limits={"image_ppi_min": 100.0, "image_ppi_good": 150.0},
        ),
        _p(
            "screen",
            "Bildschirm / E-Mail",
            "Nur zum Ansehen: kleine Datei, Bilder bis 200 ppi genügen; Druckthemen sind aus.",
            report={
                "font_missing": "warning",
                "image_low": "info",
                "image_ok": "off",
                "image_high": "warning",
                "rgb": "off",
                "spot_colors": "off",
                "hairline": "off",
                "bleed": "off",
                "safety": "off",
                "transparency_gradient": "off",
                "transparency": "off",
                "overprint_used": "off",
                "overprint_white": "info",
                "overprint_black_text": "off",
                "print_lowres": "info",
                "pdfx_intent": "off",
                "pdfx_profile": "off",
                "pdfx_trim": "off",
                "device": "off",
            },
            limits={"image_ppi_min": 72.0, "image_ppi_good": 96.0, "image_ppi_max": 220.0},
        ),
    )
}
DEFAULT = "standard"


# --------------------------------------------------------------------------- #
# reading and checking profiles
# --------------------------------------------------------------------------- #
def from_dict(data: dict, name: str = "", path: str = "") -> Profile:
    """Profile from a dict (file contents). Unknown keys and invalid values -> ValueError with the reason."""
    if not isinstance(data, dict):
        raise ValueError(tr("Prüfprofil: kein JSON-Objekt."))
    if data.get("passermark") not in (None, FORMAT):
        raise ValueError(tr("Prüfprofil: keine Prüfprofil-Datei („passermark“: „{0}“).").format(FORMAT))
    report = data.get("report") or {}
    limits = data.get("limits") or {}
    if not isinstance(report, dict) or not isinstance(limits, dict):
        raise ValueError(tr("Prüfprofil: „report“ und „limits“ müssen Objekte sein."))
    for k, v in report.items():
        if k not in CHECKS:
            raise ValueError(tr("Prüfprofil: unbekannte Prüfung „{0}“.").format(k))
        if v not in SEVERITIES:
            raise ValueError(tr("Prüfprofil: „{0}“ muss eines von {1} sein.").format(k, ", ".join(SEVERITIES)))
    clean = {}
    for k, v in limits.items():
        if k not in LIMITS:
            raise ValueError(tr("Prüfprofil: unbekannter Grenzwert „{0}“.").format(k))
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError(tr("Prüfprofil: Grenzwert „{0}“ muss eine Zahl sein.").format(k))
        lo, hi = LIMITS[k][3], LIMITS[k][4]
        if not lo <= float(v) <= hi:
            raise ValueError(tr("Prüfprofil: Grenzwert „{0}“ muss zwischen {1:g} und {2:g} liegen.").format(k, lo, hi))
        clean[k] = float(v)
    label = str(data.get("name") or name)
    return Profile(
        name or label, label, str(data.get("description") or ""), dict(report), clean, builtin=False, path=path
    )


def folders() -> list:
    """[(kind, folder)] – own profiles first, then the ones for everybody (the first with the name wins):
    user    Linux ~/.config/passermark/checkprofiles · Windows %APPDATA%\\Passermark\\checkprofiles
    system  Linux /etc/passermark/checkprofiles · Windows %ProgramData%\\Passermark\\checkprofiles
    """
    from . import presets
    from .platform import config_dir

    return [
        ("user", os.path.join(os.path.dirname(presets.root_dir()), FOLDER)),
        ("system", os.path.join(config_dir(), FOLDER)),
    ]


def load_file(path: str) -> Profile:
    """Read a profile file."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return from_dict(data, os.path.splitext(os.path.basename(path))[0], path)


def own_profiles() -> list:
    """Own profiles from the profile folders: [Profile] (files that cannot be read are skipped)."""
    seen, out = set(BUILTIN), []
    for _kind, d in folders():
        try:
            files = sorted(f for f in os.listdir(d) if f.lower().endswith(".json") and not f.startswith("."))
        except OSError:
            continue
        for f in files:
            name = f[:-5]
            if name.lower() in seen:
                continue
            try:
                p = load_file(os.path.join(d, f))
            except (OSError, ValueError):
                continue
            seen.add(name.lower())
            out.append(p)
    return out


def all_profiles() -> list:
    """Built-in profiles, then the own ones."""
    return list(BUILTIN.values()) + own_profiles()


def resolve(ref=None) -> Profile:
    """Profile from a name (built-in or own), a path to a .json file, a dict or a Profile; None/"" = the one chosen
    in the settings (otherwise "standard"). Unknown names -> ValueError."""
    if isinstance(ref, Profile):
        return ref
    if isinstance(ref, dict):
        return from_dict(ref, str(ref.get("name") or "profile"))
    if not ref:
        ref = chosen()
    ref = str(ref)
    if ref in BUILTIN:
        return BUILTIN[ref]
    if ref.lower().endswith(".json") and os.path.isfile(ref):
        return load_file(ref)
    for p in own_profiles():
        if p.name.lower() == ref.lower():
            return p
    raise ValueError(
        tr("Prüfprofil „{0}“ nicht gefunden – vorhanden: {1}.").format(ref, ", ".join(p.name for p in all_profiles()))
    )


SETTING = "check_profile"


def chosen() -> str:
    """Name of the profile chosen in the settings (the program and passermark-cli without --profile)."""
    try:
        from .l10n import load_settings

        name = str(load_settings().get(SETTING) or DEFAULT)
    except Exception:  # noqa: BLE001 – settings not readable: the default
        return DEFAULT
    return name


def save(p: Profile, folder: str | None = None) -> str:
    """Save an own profile (into the own profile folder); returns the path."""
    if p.name in BUILTIN:
        raise ValueError(
            tr("„{0}“ ist ein eingebautes Profil – bitte unter einem anderen Namen speichern.").format(p.name)
        )
    d = folder or folders()[0][1]
    os.makedirs(d, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in p.name).strip() or "profil"
    path = os.path.join(d, safe + ".json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(p.to_dict(), f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    p.path = path
    return path


def describe(p: Profile) -> dict:
    """Everything about a profile for lists and --json: every check with its severity, every limit."""
    return {
        "name": p.name,
        "label": p.title(),
        "description": tr(p.description) if p.builtin and p.description else p.description,
        "builtin": p.builtin,
        "file": p.path or None,
        "checks": {k: p.severity(k) for k in CHECKS},
        "limits": p.all_limits(),
    }


# --------------------------------------------------------------------------- #
# applying a profile to the findings
# --------------------------------------------------------------------------- #
def apply(issues: list, p: Profile) -> tuple:
    """Severities of the profile on the findings: (kept findings, keys of the checks without a finding).
    Findings without a check key are kept as they are."""
    out, hit = [], set()
    for i in issues:
        key = getattr(i, "check", "")
        if not key:
            out.append(i)
            continue
        sev = p.severity(key)
        if sev == "off":
            continue
        if key in p.report and sev != i.severity:
            i.severity = sev
        hit.add(key)
        out.append(i)
    passed = [k for k in CHECKS if k not in hit and p.severity(k) != "off" and k != "device"]
    return out, passed
