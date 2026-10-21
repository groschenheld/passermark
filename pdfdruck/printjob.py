# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark â Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Build and send a print job â shared by the print dialog and right-click printing."""
from __future__ import annotations

import os
import re
import shutil
import tempfile

from . import colorconv, config, layout, printers
from .l10n import tr


def make_plans(sizes, pages, sheet, settings: layout.LayoutSettings, reverse: bool = False, trims=None, bleeds=None):
    plans = layout.plan(sizes, pages, sheet, settings, trims, bleeds)
    if settings.handling == "booklet" and reverse:     # for booklets, reverse the sheets
        step = 2 if settings.booklet_sides == "both" else 1
        groups = [plans[i:i + step] for i in range(0, len(plans), step)]
        plans = [p for g in reversed(groups) for p in g]
    return plans


def short_edge_choice(caps: printers.PrinterCaps):
    """(option name, value) for duplex on the short edge â or None."""
    key = caps.roles.get("duplex") if caps else None
    if not key:
        return None
    rx = re.compile(r"tumble|short|kurz", re.I)
    for c in caps.options[key].choices:
        both = c.value + " " + c.text
        if rx.search(both) and not re.search(r"no\s*tumble", both, re.I):
            return key, c.value
    return None


def resolve_tray(session, printer: str, values: dict, weight: int = 0, live: bool = True):
    """Apply automatic tray selection (if stored and active for the printer).
        Returns (values, hint, warning). values is not modified but copied.
    """
    from . import trays
    pc = session.cfg.get("printers", {}).get(printer, {})
    tl = trays.trays_of(pc)
    if not tl or not pc.get("tray_auto", True):
        return values, "", False
    caps = session.caps_for(printer)
    skey, mkey, pkey = caps.roles.get("source"), caps.roles.get("mediatype"), caps.roles.get("pagesize")
    if not skey or not pkey:
        return values, "", False
    st = trays.live_status(pc.get("tray_host", ""), force=True) if (live and pc.get("tray_live")) else None
    labels = {c.value: c.text for c in caps.options[skey].choices}
    p = trays.pick(tl, values.get(pkey, ""), weight, st, labels)
    out = dict(values)
    if p.tray:
        out[skey] = p.tray.slot
        if p.tray.media and mkey:
            out[mkey] = p.tray.media
    return out, p.note, p.warn


def step2_values(caps: printers.PrinterCaps, values: dict, settings: layout.LayoutSettings) -> dict:
    """Mehrfachnutzen mit Schritt 2: Papier = Zielformat aus Schritt 2 (nicht das Montageblatt aus Schritt 1).
        Das Format aus der Geräteliste, sonst das Format des Treibers mit diesen Maßen. Ohne Schritt 2 unverändert.
        ValueError, wenn der Drucker das Zielformat nicht hat."""
    if not layout.is_step2(settings) or caps.backend == "pdf":
        return values
    key = caps.roles.get("pagesize")
    if not key or key not in caps.options:
        return values
    out = dict(values)
    fmt = getattr(settings, "sr2_format", "") or ""
    if fmt and fmt != "custom" and fmt in {c.value for c in caps.options[key].choices}:
        out[key] = fmt
        return out
    w, h = settings.sr2_w_mm * layout.MM, settings.sr2_h_mm * layout.MM
    v = printers.find_paper(caps, w, h)
    if v is None:
        raise ValueError(tr("Schritt 2: Zielformat {0:g} × {1:g} mm gibt es bei {2} nicht – bitte ein Format aus "
                            "der Liste des Druckers wählen.").format(settings.sr2_w_mm, settings.sr2_h_mm, caps.name))
    out[key] = v
    return out


def default_printer(session) -> str | None:
    if session.printer:
        return session.printer
    try:
        plist = printers.list_printers()
    except Exception:
        return None
    return next((p.name for p in plist if p.is_default), plist[0].name if plist else None)


def submit_document(doc, title: str, session, printer: str, pages: list[int],
                    settings: layout.LayoutSettings, copies: int = 1, collate: bool = True,
                    reverse: bool = False, values: dict | None = None, manip=None, file: str | None = None) -> int:
    """Impose, optional color conversion, assemble the options, send to CUPS.
        values: Papier = Montageblatt (Schritt 1). Mit Schritt 2 wird das Papier hier aufs Zielformat gesetzt.
        file: Quelldatei fürs Druckprotokoll (falls eingeschaltet)."""
    from . import printlog
    if printer == printers.PDF_TARGET or not printlog.enabled(session.cfg):
        return _submit(doc, title, session, printer, pages, settings, copies, collate, reverse, values, manip, {})
    caps = session.caps_for(printer)
    vals = dict(values if values is not None else session.values_for(printer))
    info = {}
    try:
        jid = _submit(doc, title, session, printer, pages, settings, copies, collate, reverse, values, manip, info)
    except Exception as e:
        printlog.write(printlog.build(caps, printer, file, title, pages, settings, info.get("values") or vals,
                                      copies, collate, reverse, session.color_for(printer), None, error=str(e),
                                      sheet_mm=info.get("sheet_mm")), session.cfg)
        raise
    rec = printlog.build(caps, printer, file, title, pages, settings, info.get("values") or vals, copies, collate,
                         reverse, session.color_for(printer), jid, sheet_mm=info.get("sheet_mm"))
    rec["job"]["sent"] = info.get("sent")
    printlog.write(rec, session.cfg)
    return jid


def _submit(doc, title, session, printer, pages, settings, copies, collate, reverse, values, manip, info: dict) -> int:
    caps = session.caps_for(printer)
    if values is None:
        values = session.values_for(printer)
    flat = layout.flattened(doc)          # Formularwerte/Kommentare mit auf das Blatt
    if manip is not None and manip.active:     # only on explicit request any more (e.g. scripts)  # document manipulation: crop, CMYK
        from . import pdfmanip
        changed, _notes = pdfmanip.apply(flat, manip)
        if flat is not doc:
            flat.close()
        flat = changed
    src_doc = doc
    doc = flat
    spread_from = None
    if layout.is_booklet_spreads(settings):
        spread_from = settings
        # Broschüre als Druckbögen: erst aufgeklappte Bögen bilden, dann mit der Nutzen-Logik montieren
        spreads, pages, settings, _notes = layout.spread_source(doc, pages, settings, layout.page_trims(doc))
        if doc is not src_doc:
            doc.close()
        doc = flat = spreads
        reverse = False
    w, h, ia = caps.sheet_for(values)
    if caps.backend == "pdf" and values.get("PageSize") == "DOC" and pages:
        w, h = doc.get_page_size(pages[0])
        ia = None
    sheet = layout.Sheet(w, h, ia)
    sizes = [doc.get_page_size(i) for i in range(len(doc))]
    plans = make_plans(sizes, pages, sheet, settings, reverse, layout.page_trims(doc), layout.page_doc_bleeds(doc))
    if spread_from is not None:
        layout.mark_spread_duplex(plans, spread_from)
    if not plans:
        raise RuntimeError(tr("Nichts zu drucken (Seiten-/Bogenbereich leer?)"))
    step2 = layout.is_step2(settings)
    if step2:                            # Mehrfachnutzen mit Schritt 2: wie beim Speichern beide Schritte,
        values = step2_values(caps, values, settings)          # Papier = Zielformat aus Schritt 2

    def imposed():
        if step2:
            t = layout.step2_sheet(settings)
            info["sheet_mm"] = [round(t.width / layout.MM, 1), round(t.height / layout.MM, 1)]
            return layout.impose_step2(doc, sheet, plans, settings)
        info["sheet_mm"] = [round(sheet.width / layout.MM, 1), round(sheet.height / layout.MM, 1)]
        return layout.impose_with(doc, sheet, plans, settings)

    if caps.backend == "pdf":            # Save as PDF: unchanged, without a color profile
        try:
            out = imposed()
            dst = values["__out__"]
            pw = values.get("__password__")
            if pw:                               # first unencrypted into the cache, then protected to the destination
                tmpd = tempfile.mkdtemp(prefix="pdfdruck-")
                try:
                    plain = os.path.join(tmpd, "plain.pdf")
                    out.save(plain)
                    out.close()
                    from .repair import encrypt_file
                    part = dst + ".part"
                    encrypt_file(plain, part, pw)
                    os.replace(part, dst)
                finally:
                    shutil.rmtree(tmpd, ignore_errors=True)
            else:
                out.save(dst)
                out.close()
        finally:
            if doc is not src_doc:
                doc.close()
        return 0
    opts = caps.job_options(values)
    pid, intent = session.color_for(printer)
    prof = config.profile_by_id(session.cfg, pid) if pid else None

    tmp = tempfile.mkdtemp(prefix="pdfdruck-", dir=os.environ.get("XDG_RUNTIME_DIR") or None)
    try:
        job = os.path.join(tmp, "job.pdf")
        out = imposed()
        out.save(job)
        out.close()
        job_values = dict(values)
        if any(p.duplex_short for p in plans):
            dc = short_edge_choice(caps)
            if dc:
                opts[dc[0]] = dc[1]
                job_values[dc[0]] = dc[1]
        info["values"] = job_values
        info["sent"] = opts
        if prof:
            conv = os.path.join(tmp, "job-icc.pdf")
            colorconv.convert(job, conv, prof["file"], intent, bool(prof.get("bpc", True)))
            job = conv
            opts.update({k: str(v) for k, v in (prof.get("driver_options") or {}).items()})
        if caps.backend == "win":              # Windows: via GDI to the vendor driver
            from .printers_win import print_pdf
            return print_pdf(printer, job, title, job_values, copies, collate)
        opts.update({
            "copies": str(copies),
            "collate": "true" if collate else "false",
            "multiple-document-handling": "separate-documents-collated-copies"
            if collate else "separate-documents-uncollated-copies",
            # Das PDF ist bereits exakt auf das Blatt ausgeschossen:
            "print-scaling": "none",
            "fit-to-page": "false",
            "number-up": "1",
        })
        return printers.submit(printer, job, title, opts)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if doc is not src_doc:
            doc.close()


def print_file(path: str, session, password: str | None = None) -> tuple[str, int]:
    """Rechtsklick-Druck: ganze Datei mit den aktuellen Sitzungs- bzw. Admin-Standards."""
    import pypdfium2 as pdfium
    from . import images

    printer = default_printer(session)
    if not printer:
        raise RuntimeError(tr("Kein Drucker eingerichtet."))
    if images.is_image(path):
        doc = images.images_to_document([path], float(session.cfg.get("image_default_dpi", 96)))
    else:
        doc = pdfium.PdfDocument(path, password=password)
    try:
        s = session.layout
        rev = session.reverse and s.handling != "booklet"
        pages = layout.select_pages(len(doc), "", session.subset, rev)
        vals, _note, _warn = resolve_tray(session, printer, session.values_for(printer),
                                          getattr(session, "weights", {}).get(printer, 0))
        from . import printlog
        with printlog.source("rightclick"):
            jid = submit_document(doc, os.path.basename(path), session, printer, pages, s,
                                  session.copies, session.collate, session.reverse, values=vals, file=path)
        return printer, jid
    finally:
        doc.close()

