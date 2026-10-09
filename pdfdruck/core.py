# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Kern-Schnittstelle: jede schwere Funktion als „Eingabe-PDF + Einstellungen → Ausgabe-PDF“.

    run_job("cutcontour", "ein.pdf", "aus.pdf", {"shape": "rect", "bleed_mm": 2}, progress=…, cancel=…)

- gleich für alle Funktionen (CutContour, Objekte trennen, CMYK/Beschneiden, Reparieren, Preflight-Reparaturen)
- Einstellungen als dict/JSON (Grundlage für Presets, CLI, Aufträge in eigenem Prozess, Watcher)
- Fortschritt: progress(erledigt, gesamt, text); Abbrechen: cancel() -> True löst Cancelled aus
- die Ausgabe wird atomar geschrieben: erst fertig in eine temporäre Datei, dann umbenannt – nach Fehler oder
  Abbruch bleibt nie eine halbe Datei liegen
- ohne Oberfläche (kein Qt) – läuft auch in einem eigenen Prozess oder auf der Kommandozeile
"""
from __future__ import annotations

import dataclasses
import json
import os
import typing
from dataclasses import dataclass, field

from .l10n import tr
from .objects import DetectSettings


class Cancelled(Exception):
    """Auftrag wurde abgebrochen."""


@dataclass
class JobResult:
    output: str
    info: dict = field(default_factory=dict)       # z. B. {"pages": 3, "cuts": 12}
    notes: list = field(default_factory=list)      # Hinweise für den Benutzer


# --------------------------------------------------------------------------- #
# Einstellungen <-> dict/JSON (auch verschachtelt, unbekannte Schlüssel werden ignoriert)
# --------------------------------------------------------------------------- #
def settings_to_dict(obj) -> dict:
    return dataclasses.asdict(obj)


def settings_from_dict(cls, data: dict | None):
    if data is None:
        return cls()
    if dataclasses.is_dataclass(data) and isinstance(data, cls):
        return data
    hints = typing.get_type_hints(cls)
    kw = {}
    for f in dataclasses.fields(cls):
        if f.name not in data:
            continue
        v = data[f.name]
        t = hints.get(f.name)
        if dataclasses.is_dataclass(t) and isinstance(v, dict):
            v = settings_from_dict(t, v)
        elif t is float and isinstance(v, int) and not isinstance(v, bool):
            v = float(v)
        kw[f.name] = v
    return cls(**kw)


def save_settings(path: str, kind: str, settings) -> None:
    """Preset-Datei schreiben: {"job": kind, "settings": {…}}."""
    d = settings if isinstance(settings, dict) else settings_to_dict(settings)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"job": kind, "settings": d}, f, ensure_ascii=False, indent=2)


def load_settings(path: str) -> tuple[str, dict]:
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return d["job"], d.get("settings", {})


# --------------------------------------------------------------------------- #
# Auftrags-Einstellungen, die es bisher nur als Dialog-Felder gab
# --------------------------------------------------------------------------- #
@dataclass
class SeparateSettings:
    detect: DetectSettings = field(default_factory=DetectSettings)
    margin_mm: float = 0.0
    boxes: dict | None = None    # {Seite: [[x0, y0, x1, y1], …]} in pt; None = automatisch erkennen


@dataclass
class RepairSettings:
    mode: str = "print"          # siehe repair.MODES
    password: str = ""
    new_password: str = ""
    allow_print: bool = True


@dataclass
class PreflightFixSettings:
    fix: str = "flatten_layers"  # flatten_layers | embed_fonts | outline_text | flatten_transparency
    font_map: dict = field(default_factory=dict)        # embed_fonts: {Schriftname: Pfad}
    dpi: int = 300                                      # flatten_transparency
    visible: list | None = None                         # flatten_layers: sichtbare Ebenen (None = Druck-Zustand)


# --------------------------------------------------------------------------- #
# Hilfen
# --------------------------------------------------------------------------- #
def _check(cancel):
    if cancel is not None and cancel():
        raise Cancelled(tr("Abgebrochen."))


def _report(progress, done, total, text=""):
    if progress is not None:
        progress(done, total, text)


def _write_atomic(dst: str, data: bytes):
    tmp = dst + ".part"
    try:
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, dst)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _doc_bytes(doc) -> bytes:
    import io
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Aufträge
# --------------------------------------------------------------------------- #
def _job_cutcontour(src, dst, s, opts, progress, cancel):
    import pypdfium2 as pdfium
    from . import cutcontour
    doc = pdfium.PdfDocument(src)
    try:
        out, n = cutcontour.make(doc, s, opts.get("pages"), progress=progress, cancel=cancel,
                                 workers=opts.get("workers") or cutcontour.default_workers())
        try:
            _check(cancel)
            _write_atomic(dst, _doc_bytes(out))
            return JobResult(dst, {"pages": len(out), "cuts": n})
        finally:
            out.close()
    finally:
        doc.close()


def _job_separate(src, dst, s: SeparateSettings, opts, progress, cancel):
    import pypdfium2 as pdfium
    from . import objects
    doc = pdfium.PdfDocument(src)
    norm = objects.normalized(doc)
    try:
        boxes = {}
        pages = opts.get("pages") or list(range(len(norm)))
        for k, i in enumerate(pages):
            _check(cancel)
            _report(progress, k, len(pages), tr("Seite {0}/{1}").format(k + 1, len(pages)))
            given = (s.boxes or {}).get(str(i), (s.boxes or {}).get(i))
            if given is not None:
                boxes[i] = [objects.Box(*b) for b in given]
            else:
                pg = norm[i]
                try:
                    boxes[i] = objects.detect(pg, s.detect)
                finally:
                    pg.close()
        if not any(boxes.values()):
            raise ValueError(tr("Keine Objekte gefunden."))
        _report(progress, len(pages), len(pages), tr("Schreibe PDF …"))
        out = objects.separate(norm, boxes, s.margin_mm)
        try:
            _write_atomic(dst, _doc_bytes(out))
            return JobResult(dst, {"pages": len(out), "objects": sum(len(v) for v in boxes.values())})
        finally:
            out.close()
    finally:
        norm.close()
        doc.close()


def _job_manip(src, dst, s, opts, progress, cancel):
    import pypdfium2 as pdfium
    from . import pdfmanip
    from .layout import flattened
    if not s.active:
        raise ValueError(tr("Bitte CMYK-Umwandlung und/oder Beschneiden aktivieren."))
    doc = pdfium.PdfDocument(src)
    try:
        _report(progress, 0, 1, tr("Bearbeite …"))
        flat = flattened(doc)
        _check(cancel)
        out, notes = pdfmanip.apply(flat, s)
        try:
            _check(cancel)
            _write_atomic(dst, _doc_bytes(out))
            _report(progress, 1, 1, "")
            return JobResult(dst, {"pages": len(out)}, list(notes))
        finally:
            if out is not doc:
                out.close()
            if flat is not doc and flat is not out:
                flat.close()
    finally:
        doc.close()


def _job_repair(src, dst, s: RepairSettings, opts, progress, cancel):
    from . import repair
    _report(progress, 0, 1, tr("Bearbeite …"))
    tmp = dst + ".part.pdf"
    try:
        r = repair.process(src, tmp, s.mode, s.password or None, s.new_password or None, s.allow_print)
        _check(cancel)
        os.replace(tmp, dst)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    _report(progress, 1, 1, "")
    return JobResult(dst, {"pages": r.pages_out, "size_in": r.size_in, "size_out": r.size_out}, list(r.notes))


def _job_preflight_fix(src, dst, s: PreflightFixSettings, opts, progress, cancel):
    from . import preflight
    with open(src, "rb") as f:
        data = f.read()
    _report(progress, 0, 1, tr("Bearbeite …"))
    notes = []
    if s.fix == "flatten_layers":
        if preflight.has_layers(data):
            out = preflight.flatten_layers(data, set(s.visible) if s.visible is not None else None)
        else:                                    # nichts zu tun – in Ketten/Ordnern nicht abbrechen
            out = data
            notes.append(tr("Keine Ebenen – Datei unverändert übernommen."))
    elif s.fix == "embed_fonts":
        out = preflight.embed_fonts(data, s.font_map)
    elif s.fix == "outline_text":
        out = preflight.outline_text(data)
    elif s.fix == "flatten_transparency":
        out = preflight.flatten_transparency(data, s.dpi)
    else:
        raise ValueError(tr("Unbekannte Reparatur: {0}").format(s.fix))
    _check(cancel)
    _write_atomic(dst, out)
    _report(progress, 1, 1, "")
    return JobResult(dst, {}, notes)


def _job_impose(src, dst, s, opts, progress, cancel):
    """Ausschießen wie im Druckdialog (Größe, Mehrere, Broschüre/Lagen, Poster, Nutzen) – Ergebnis als PDF."""
    import pypdfium2 as pdfium
    from . import layout
    sheet = s.sheet_obj()
    doc = pdfium.PdfDocument(src)
    try:
        flat = layout.flattened(doc)
        try:
            _report(progress, 0, 1, tr("Bearbeite …"))
            sizes = [flat.get_page_size(i) for i in range(len(flat))]
            pages = opts.get("pages") or list(range(len(flat)))
            plans = layout.plan(sizes, pages, sheet, s, layout.page_trims(flat), layout.page_doc_bleeds(flat))
            if not plans:
                raise ValueError(tr("Nichts zu drucken (Seiten-/Bogenbereich leer?)"))
            _check(cancel)
            out = layout.impose_with(flat, sheet, plans, s)
            try:
                _write_atomic(dst, _doc_bytes(out))
            finally:
                out.close()
        finally:
            if flat is not doc:
                flat.close()
    finally:
        doc.close()
    notes = [w for sp in plans for w in sp.warnings]
    _report(progress, 1, 1, "")
    return JobResult(dst, {"sheets": len(plans)}, notes)


def _job_vdp(src, dst, s, opts, progress, cancel):
    """Variable Daten: Felder je Datensatz auf eine Kopie der Vorlage legen."""
    from . import vdp
    data, info = vdp.build(src, s, progress=progress, cancel=cancel, pages=opts.get("pages"))
    _check(cancel)
    _write_atomic(dst, data)
    notes = []
    if info.get("placeholders_removed"):
        notes.append(tr("{0} Platzhalter aus der Vorlage übernommen.").format(info["placeholders_removed"]))
    if s.log_path:
        notes.append(tr("Code-Protokoll: {0}").format(s.log_path))
    return JobResult(dst, {"records": info["records"], "pages": info["pages"]}, notes)


def _vdp_settings():
    from .vdp import VdpSettings
    return VdpSettings


def _impose_settings():
    from .layout import ImposeSettings
    return ImposeSettings


def _cut_settings():
    from .cutcontour import CutSettings
    return CutSettings


def _manip_settings():
    from .cmyk import ManipSettings
    return ManipSettings


# Name -> (Einstellungs-Klasse (bzw. Funktion, die sie liefert), Ausführung)
JOBS = {
    "cutcontour": (_cut_settings, _job_cutcontour),
    "separate": (lambda: SeparateSettings, _job_separate),
    "manip": (_manip_settings, _job_manip),
    "repair": (lambda: RepairSettings, _job_repair),
    "preflight_fix": (lambda: PreflightFixSettings, _job_preflight_fix),
    "impose": (_impose_settings, _job_impose),
    "vdp": (_vdp_settings, _job_vdp),
}


def settings_class(kind: str):
    if kind not in JOBS:
        raise ValueError(tr("Unbekannter Auftrag: {0}").format(kind))
    return JOBS[kind][0]()


def run_job(kind: str, src: str, dst: str, settings=None, options: dict | None = None,
            progress=None, cancel=None) -> JobResult:
    """Einen Auftrag ausführen. settings: dict (z. B. aus JSON) oder die passende Einstellungs-Klasse.
    options: {"pages": [0, 2, …]} (nur diese Seiten, wo sinnvoll)."""
    cls = settings_class(kind)
    s = settings_from_dict(cls, settings) if not isinstance(settings, cls) else settings
    if os.path.abspath(src) == os.path.abspath(dst):
        raise ValueError(tr("Eingabe und Ausgabe dürfen nicht dieselbe Datei sein."))
    _check(cancel)
    return JOBS[kind][1](src, dst, s, options or {}, progress, cancel)
