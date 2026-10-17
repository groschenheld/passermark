# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Drucken ohne Oberfläche (Ablauf-Schritt "print", passermark-cli printers / caps).

Gedruckt wird über denselben Weg wie aus dem Druckdialog (printjob.submit_document): Nutzen/Broschüre/Poster,
Farbprofil des Druckers aus der Admin-Einstellung, automatische Fachwahl, Windows-Herstellereinstellungen.

Optionen werden über ihre Rolle angesprochen (paper, tray, media, duplex, color, quality, output_bin und die
Finisher staple, punch, fold, saddle, trim, stacker). Der Wert darf der Treiberwert oder der angezeigte Name sein
("A3", "Fach 2", "Heften links oben"); duplex zusätzlich none | long | short, color zusätzlich color | gray.
Was keiner Rolle zugeordnet ist, geht roh über options {"Treiber-Schlüsselwort": "Wert"}.

Alle installierten Finisher: unter Linux sind sie Treiberoptionen (PPD) – Werte, die laut Treiber mit der
eingetragenen Hardware nicht gehen, werden abgelehnt. Unter Windows stecken die Herstellerfunktionen im
Original-Treiberdialog; der wird in der Verwaltung als Finisher-Vorlage gespeichert und hier mit
finisher_preset gewählt (das gilt auch unter Linux, z. B. für Kombinationen aus mehreren Optionen).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import printers
from .l10n import tr

ROLE_FIELDS = {"paper": "pagesize", "tray": "source", "media": "mediatype", "duplex": "duplex", "color": "color",
               "quality": "quality", "output_bin": "outputbin"}
FINISH_ROLES = ("staple", "punch", "fold", "saddle", "trim", "stacker")

_SYNONYMS = {
    "duplex": {
        "none": re.compile(r"^(none|off|simplex|one-sided|aus)$|einseitig|1-sided|one.sided|^false$", re.I),
        "long": re.compile(r"notumble|long|lange|two-sided-long|duplexnotumble", re.I),
        "short": re.compile(r"(?<!no)tumble|short|kurz|two-sided-short", re.I),
    },
    "color": {
        "gray": re.compile(r"gray|grey|grau|mono|black|schwarz|^k$|kgray", re.I),
        "color": re.compile(r"colou?r|farb|rgb|cmyk", re.I),
    },
}


@dataclass
class PrintSettings:
    printer: str = ""                 # leer = Standarddrucker (Admin-Einstellung bzw. System)
    paper: str = ""                   # Papierformat (Treiberwert oder Name, z. B. "A3", "SRA3")
    tray: str = ""                    # Fach/Zufuhr
    media: str = ""                   # Medientyp
    duplex: str = ""                  # none | long | short – oder Treiberwert/Name
    color: str = ""                   # color | gray – oder Treiberwert/Name
    quality: str = ""
    output_bin: str = ""              # Ausgabefach
    finishing: dict = field(default_factory=dict)   # {"staple": …, "punch": …, "fold": …, "saddle": …, …}
    options: dict = field(default_factory=dict)     # Treiberoptionen roh: {"Schlüsselwort": "Wert"}
    finisher_preset: str = ""         # Finisher-Vorlage aus der Verwaltung (Optionen + Windows-Herstellerdialog)
    copies: int = 1
    collate: bool = True
    reverse: bool = False             # umgekehrte Reihenfolge
    subset: str = "all"               # all | odd | even
    layout: dict = field(default_factory=dict)      # Seitenhandhabung wie im Druckdialog (LayoutSettings)
    profile: str = "admin"            # admin = Farbprofil laut Admin-Einstellung · none = ohne · sonst Profil-ID
    intent: str = ""                  # leer = wie in der Admin-Einstellung
    auto_tray: bool = True            # automatische Fachwahl (falls für den Drucker eingerichtet)
    title: str = ""                   # Auftragsname in der Warteschlange (leer = Dateiname)
    dry_run: bool = False             # nichts senden – nur auflösen und melden, was gedruckt würde


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s)).strip().lower()


def match_choice(opt: printers.Option, wanted: str, role: str = "") -> str:
    """Treiberwert zu einer Angabe: genauer Wert, Anzeigename, Kurzform (duplex/color) oder eindeutiger Teil."""
    w = str(wanted).strip()
    vals = [c.value for c in opt.choices]
    if w in vals:
        return w
    nw = _norm(w)
    for c in opt.choices:
        if _norm(c.value) == nw or _norm(c.text) == nw:
            return c.value
    syn = _SYNONYMS.get(role, {}).get(nw)
    if syn is not None:
        hits = [c.value for c in opt.choices if syn.search(c.value) or syn.search(c.text)]
        if role == "duplex" and nw == "long":
            hits = [h for h in hits if not re.search(r"(?<!no)tumble|short|kurz", h, re.I)] or hits
        if hits:
            return hits[0]
    part = [c.value for c in opt.choices if nw and (nw in _norm(c.text) or nw in _norm(c.value))]
    if len(part) == 1:
        return part[0]
    choices = ", ".join(f"{c.value} ({c.text})" if c.text != c.value else c.value for c in opt.choices[:25])
    raise ValueError(tr("„{0}“ passt zu keiner Auswahl bei {1}: {2}").format(w, opt.text or opt.keyword, choices))


def finisher_presets(cfg: dict, printer: str) -> list:
    return list(cfg.get("printers", {}).get(printer, {}).get("presets", []) or [])


def unavailable(caps: printers.PrinterCaps, values: dict, key: str, value: str) -> bool:
    """True = laut Treiber (PPD-Einschränkungen) mit der eingetragenen Hardware nicht möglich."""
    if caps.backend != "ppd" or getattr(caps, "_ppd", None) is None:
        return False
    try:
        return key in caps.conflicts(dict(values, **{key: value}))
    except Exception:
        return False


def resolve(caps: printers.PrinterCaps, base: dict, s: PrintSettings, presets: list | None = None) -> tuple[dict, list]:
    """Treiberwerte aus den Einstellungen. -> (Werte, Probleme [(Feld, Meldung)]).
        Reihenfolge: Admin/Treiber-Standard < Finisher-Vorlage < einzelne Angaben."""
    vals, probs = dict(base), []
    if s.finisher_preset:
        pr = next((p for p in presets or [] if p.get("name") == s.finisher_preset), None)
        if pr is None:
            names = ", ".join(p.get("name", "") for p in presets or []) or "–"
            probs.append(("finisher_preset", tr("Finisher-Vorlage nicht gefunden: {0} (vorhanden: {1})")
                          .format(s.finisher_preset, names)))
        else:
            for k, v in (pr.get("options") or {}).items():
                if k in caps.options:
                    vals[k] = v
            if pr.get("devmode"):
                vals["__devmode__"] = pr["devmode"]
    explicit = []
    wanted = [(f, ROLE_FIELDS[f], getattr(s, f)) for f in ROLE_FIELDS if getattr(s, f)]
    wanted += [(f"finishing.{k}", k, v) for k, v in (s.finishing or {}).items()]
    for fld, role, v in wanted:
        if fld.startswith("finishing.") and role not in FINISH_ROLES:
            probs.append((fld, tr("unbekannter Finisher – möglich: {0}").format(", ".join(FINISH_ROLES))))
            continue
        key = caps.roles.get(role)
        if not key or key not in caps.options:
            probs.append((fld, tr("Der Drucker bietet dafür keine Option an.")))
            continue
        try:
            vals[key] = match_choice(caps.options[key], v, role)
            explicit.append((fld, key))
        except ValueError as e:
            probs.append((fld, str(e)))
    for k, v in (s.options or {}).items():
        opt = caps.options.get(k)
        if opt is None:
            probs.append((f"options.{k}", tr("unbekannte Treiberoption")))
            continue
        try:
            vals[k] = match_choice(opt, v) if opt.choices else str(v)
            explicit.append((f"options.{k}", k))
        except ValueError as e:
            probs.append((f"options.{k}", str(e)))
    for fld, key in explicit:                        # nicht installierte Finisher u. Ä. gleich melden
        if key != caps.roles.get("pagesize") and unavailable(caps, vals, key, vals[key]):
            probs.append((fld, tr("„{0}“ ist mit der eingetragenen Hardware laut Treiber nicht möglich "
                                  "(Installierte Optionen prüfen).").format(vals[key])))
    return vals, probs


def print_pdf(path: str, s: PrintSettings, pages: list | None = None, session=None, progress=None) -> dict:
    """PDF drucken wie aus dem Druckdialog. -> {"printer", "job_id", "sheets", "options", "dry_run"}."""
    import os
    import pypdfium2 as pdfium
    from . import config, layout, printjob
    from .session import Session
    if session is None:
        session = Session(config.load())
    printer = s.printer or printjob.default_printer(session)
    if not printer:
        raise RuntimeError(tr("Kein Drucker eingerichtet."))
    names = None
    try:
        names = [p.name for p in printers.list_printers()]
    except Exception:
        pass
    if names is not None and printer not in names:
        raise ValueError(tr("Drucker nicht gefunden: {0} (vorhanden: {1})").format(printer, ", ".join(names) or "–"))
    caps = session.caps_for(printer)
    presets = finisher_presets(session.cfg, printer)
    vals, probs = resolve(caps, session.values_for(printer), s, presets)
    if probs:
        raise ValueError("; ".join(f"{w}: {m}" for w, m in probs))
    lay_d = dict(s.layout or {})
    pr = next((p for p in presets if p.get("name") == s.finisher_preset), None) if s.finisher_preset else None
    if pr and pr.get("booklet") and "handling" not in lay_d:
        lay_d["handling"] = "booklet"                # Vorlage für Broschüren (wie im Druckdialog)
    lay = layout.LayoutSettings.from_dict(dict(session.layout.to_dict(), **lay_d))
    if s.profile != "admin" or s.intent:
        pid, intent = session.color_for(printer)
        session.color[printer] = ("" if s.profile == "none" else (pid if s.profile == "admin" else s.profile),
                                  s.intent or intent)
        if s.profile not in ("admin", "none") and not config.profile_by_id(session.cfg, s.profile):
            raise ValueError(tr("Farbprofil nicht gefunden: {0}").format(s.profile))
    preset_tray = bool(pr and caps.roles.get("source") in (pr.get("options") or {}))
    if s.auto_tray and not s.tray and not preset_tray:      # Vorlage bestimmt das Fach selbst
        vals, _note, _warn = printjob.resolve_tray(session, printer, vals)
    doc = pdfium.PdfDocument(path)
    try:
        sel = layout.select_pages(len(doc), "", s.subset, s.reverse and lay.handling != "booklet")
        if pages:
            sel = [p for p in sel if p in set(pages)]
        rev = s.reverse and lay.handling == "booklet"
        if progress:
            progress(0, 1, tr("Drucke …"))
        w, h, _ia = caps.sheet_for(vals)
        info = {"printer": printer, "dry_run": s.dry_run, "pages": len(sel),
                "sheet_mm": [round(w / layout.MM, 1), round(h / layout.MM, 1)],
                "options": {k: v for k, v in caps.job_options(vals).items()},
                "color_profile": session.color_for(printer)[0] or None,
                "finisher_preset": s.finisher_preset or None,
                "driver_settings": bool(vals.get("__devmode__"))}
        if s.dry_run:
            info["job_id"] = None
            if progress:
                progress(1, 1, "")
            return info
        info["job_id"] = printjob.submit_document(doc, s.title or os.path.basename(path), session, printer, sel, lay,
                                                  max(1, int(s.copies)), s.collate, rev, values=vals)
        if progress:
            progress(1, 1, "")
        return info
    finally:
        doc.close()


# --------------------------------------------------------------------------- #
# Abfragen für andere Programme
# --------------------------------------------------------------------------- #
def printers_info() -> list:
    out = []
    for p in printers.list_printers():
        out.append({"name": p.name, "info": p.info, "location": p.location, "model": p.model, "state": p.state,
                    "state_text": p.state_text, "message": p.state_message, "default": p.is_default})
    return out


def caps_info(name: str) -> dict:
    from . import layout
    from .session import Session
    from . import config
    sess = Session(config.load())
    caps = sess.caps_for(name)
    vals = sess.values_for(name)
    field_of = {v: k for k, v in ROLE_FIELDS.items()}
    roles = {}
    for role, key in caps.roles.items():
        roles[field_of.get(role, role)] = key
    from . import i18n
    finish_keys = {caps.roles.get(r) for r in FINISH_ROLES}

    def choices(k, o):
        out = []
        for c in o.choices:
            d = {"value": c.value, "text": c.text}
            if not o.installable and (k in finish_keys or i18n.is_finishing(k, o.text)):
                d["available"] = not unavailable(caps, vals, k, c.value)
            out.append(d)
        return out
    return {
        "name": name, "backend": caps.backend, "roles": roles,
        "options": [{"keyword": k, "text": o.text, "group": o.group, "default": vals.get(k, o.default),
                     "installable": o.installable,
                     "finishing": (not o.installable) and (k in finish_keys or i18n.is_finishing(k, o.text)),
                     "choices": choices(k, o)}
                    for k, o in caps.options.items()],
        "installed_hardware": {k: vals.get(k, o.default) for k, o in caps.options.items() if o.installable},
        "finisher_presets": [{"name": p.get("name", ""), "options": p.get("options") or {},
                              "booklet": bool(p.get("booklet")), "driver_settings": bool(p.get("devmode"))}
                             for p in finisher_presets(sess.cfg, name)],
        "driver_dialog": caps.backend == "win",
        "page_sizes_mm": {k: [round(w / layout.MM, 1), round(h / layout.MM, 1)] for k, (w, h) in caps.page_sizes.items()},
    }
