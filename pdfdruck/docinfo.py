# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Document information for other programs (passermark-cli inspect): pages, formats, trim and bleed and,
    optionally, the check results – as a plain dict (JSON). No Qt.

    Sizes in mm in reading direction (page rotation applied), boxes in pt as stored in the PDF. Page numbers
    1-based (as in the check). Messages in the program language (PASSERMARK_LANG); severity/category are stable keys.
"""
from __future__ import annotations

import io
import os

from .l10n import tr

MM = 72 / 25.4


def _r(v, n=2):
    return None if v is None else round(float(v), n)


def _box(b):
    return None if b is None else [_r(x) for x in b]


def inspect(path: str, password: str | None = None, check: bool = False, image_dpi: float = 96.0) -> dict:
    """path: PDF (or image/Office file – converted first, like when opening)."""
    import pikepdf
    from . import convert, renderproc
    if not os.path.isfile(path):
        raise FileNotFoundError(tr("Datei nicht gefunden: {0}").format(path))
    out = {"file": os.path.abspath(path), "size_bytes": os.path.getsize(path)}
    if path.lower().endswith(".pdf"):
        with open(path, "rb") as f:
            data = f.read()
    else:
        import tempfile
        import shutil
        work = tempfile.mkdtemp(prefix="passermark-inspect-")
        try:
            doc, used = convert.to_document(path, work, image_dpi, password)
            buf = io.BytesIO()
            doc.save(buf)
            doc.close()
            data = buf.getvalue()
        finally:
            shutil.rmtree(work, ignore_errors=True)
        out["converted"] = used or "image"
    try:
        pdf = pikepdf.open(io.BytesIO(data), password=password or "")
    except pikepdf.PasswordError:
        raise PermissionError(tr("Passwortgeschützt – Passwort mit --password angeben."))
    with pdf:
        out["encrypted"] = bool(pdf.is_encrypted)
        out["pdf_version"] = str(pdf.pdf_version)
        meta = {}
        try:
            di = pdf.docinfo
            for k in ("Title", "Author", "Creator", "Producer"):
                v = di.get("/" + k)
                if v is not None:
                    meta[k.lower()] = str(v)
        except Exception:
            pass
        out["metadata"] = meta
        if pdf.is_encrypted:                         # page_info braucht eine lesbare Kopie
            buf = io.BytesIO()
            pdf.save(buf)
            data = buf.getvalue()
    info = renderproc.page_info(data)
    pages = []
    for i, pi in enumerate(info):
        x0, y0, x1, y1 = pi["crop"]
        w, h = (x1 - x0), (y1 - y0)
        if pi["rotate"] % 2:
            w, h = h, w
        trim = pi.get("trim")
        tw = th = bleed = None
        if trim is not None:
            tw, th = trim[2] - trim[0], trim[3] - trim[1]
            if pi["rotate"] % 2:
                tw, th = th, tw
            b = pi.get("bleed")
            if b is not None:
                bleed = max(0.0, min(trim[0] - b[0], trim[1] - b[1], b[2] - trim[2], b[3] - trim[3]))
        pages.append({
            "page": i + 1,
            "width_mm": _r(w / MM, 1), "height_mm": _r(h / MM, 1),
            "orientation": "landscape" if w > h + 0.5 else "portrait" if h > w + 0.5 else "square",
            "rotate": pi["rotate"] * 90,
            "trim_mm": None if trim is None else [_r(tw / MM, 1), _r(th / MM, 1)],
            "bleed_mm": None if bleed is None else _r(bleed / MM, 1),
            "boxes_pt": {"crop": _box(pi["crop"]), "trim": _box(pi.get("trim_raw")), "bleed": _box(pi.get("bleed")),
                         "art": _box(pi.get("art"))},
        })
    out["pages"] = len(pages)
    out["page_list"] = pages
    sizes = {}
    for p in pages:
        k = f"{p['width_mm']:g} x {p['height_mm']:g}"
        sizes[k] = sizes.get(k, 0) + 1
    out["formats_mm"] = [{"size": k, "pages": n} for k, n in sorted(sizes.items(), key=lambda kv: -kv[1])]
    if check:
        out["check"] = _check(data)
    return out


def _check(data: bytes) -> dict:
    from . import preflight
    rep = preflight.analyze(data, True, pdfium_parts=True)
    return {
        "counts": rep.counts(),
        "issues": [{"severity": i.severity, "category": i.category, "message": i.message,
                    "pages": sorted(i.pages)} for i in rep.issues],
        "fonts": [{"name": f.name, "subtype": f.subtype, "embedded": f.embedded, "subset": f.subset,
                   "pages": sorted(f.pages)} for f in rep.fonts],
        "layers": [{"name": L.name, "view": L.view_on, "print": L.print_on, "locked": L.locked}
                   for L in rep.layers],
    }


def text_summary(d: dict) -> str:
    """Kurzfassung für Menschen (ohne --json)."""
    lines = [f"{d['file']}  (" + tr("{0} Seite(n)").format(d["pages"]) + f", PDF {d.get('pdf_version', '?')})"]
    for f in d["formats_mm"]:
        lines.append("  " + tr("{0} mm: {1} Seite(n)").format(f["size"], f["pages"]))
    trims = [p for p in d["page_list"] if p["trim_mm"]]
    if trims:
        t = trims[0]
        lines.append("  " + tr("Endformat {0:g} × {1:g} mm, Anschnitt {2} mm ({3} Seite(n))").format(
            t["trim_mm"][0], t["trim_mm"][1], "–" if t["bleed_mm"] is None else f"{t['bleed_mm']:g}", len(trims)))
    c = d.get("check")
    if c:
        lines.append("  " + tr("Prüfung: {0} Fehler, {1} Warnung(en), {2} Hinweis(e)").format(
            c["counts"]["error"], c["counts"]["warning"], c["counts"]["info"]))
        for i in c["issues"]:
            pg = ",".join(str(p) for p in i["pages"][:10]) + (" …" if len(i["pages"]) > 10 else "")
            lines.append(f"    [{i['severity']}] {i['message']}" + ("  (" + tr("S. {0}").format(pg) + ")" if pg else ""))
    return "\n".join(lines)
