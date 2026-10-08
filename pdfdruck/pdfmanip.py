# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Dokument-Manipulation: Beschneiden auf Zielformat und CMYK-Umwandlung.

Beschneiden: Jede Seite wird auf das Zielformat gesetzt. Steht eine Kante über, wird der Überstand je zur
Hälfte auf BEIDEN Seiten weggenommen (zentriert). Ist eine Seite in einer Richtung kleiner als das Ziel,
bleibt sie in dieser Richtung unverändert (Hinweis). Media-, Crop-, Trim- und BleedBox werden gesetzt –
der Inhalt selbst bleibt unangetastet und vektoriell.
"""
from __future__ import annotations

import io
import os
import tempfile

from . import cmyk as _cmyk
from .l10n import tr

MM = 72.0 / 25.4

FORMATS = {  # Anzeige-Reihenfolge; mm, Hochformat
    "A0": (841, 1189), "A1": (594, 841), "A2": (420, 594), "A3": (297, 420), "A4": (210, 297), "A5": (148, 210),
    "A6": (105, 148), "A7": (74, 105), "B4": (250, 353), "B5": (176, 250), "C4": (229, 324), "C5": (162, 229),
    "C6": (114, 162), "DL": (99, 210), "SRA3": (320, 450), "A3+": (329, 483), "Letter": (215.9, 279.4),
    "Legal": (215.9, 355.6), "Tabloid": (279.4, 431.8), "Visitenkarte 85×55": (55, 85),
    "Visitenkarte 90×50": (50, 90), "Quadrat 210": (210, 210), "Quadrat 148": (148, 148),
}


def target_pt(s: _cmyk.ManipSettings) -> tuple[float, float]:
    if s.crop_size in FORMATS:
        w, h = FORMATS[s.crop_size]
    else:
        w, h = s.crop_w_mm, s.crop_h_mm
    return w * MM, h * MM


def crop_box_for(box, rotation: int, target, follow: bool):
    """Neue Box (l, b, r, t) im ungedrehten Seitensystem + Hinweise. box: (l, b, r, t) der sichtbaren Seite."""
    l, b, r, t = box
    W, H = r - l, t - b
    tw, th = target
    if rotation % 180:                     # Ziel ist in Leserichtung angegeben
        tw, th = th, tw
    if follow and abs(W - H) > 1 and (W > H) != (tw > th):
        tw, th = th, tw                    # Querformat-Seite -> Querformat-Ziel
    dx, dy = W - tw, H - th
    notes = []
    if dx > 0.05:
        l, r = l + dx / 2, r - dx / 2
    elif dx < -0.5:
        notes.append("w")
    if dy > 0.05:
        b, t = b + dy / 2, t - dy / 2
    elif dy < -0.5:
        notes.append("h")
    return (l, b, r, t), max(dx, 0) / 2, max(dy, 0) / 2, notes


def describe_crop(doc, s: _cmyk.ManipSettings, page: int) -> str:
    """Kurzinfo für die Oberfläche: was mit Seite x passiert."""
    pg = doc[page]
    try:
        box, rot = pg.get_cropbox(), pg.get_rotation()
    finally:
        pg.close()
    new, cx, cy, notes = crop_box_for(box, rot, target_pt(s), s.crop_follow)
    w0, h0 = (box[2] - box[0]) / MM, (box[3] - box[1]) / MM
    w1, h1 = (new[2] - new[0]) / MM, (new[3] - new[1]) / MM
    if rot % 180:
        w0, h0, w1, h1, cx, cy = h0, w0, h1, w1, cy, cx
    txt = tr("Seite {0}: {1:.1f} × {2:.1f} mm → {3:.1f} × {4:.1f} mm").format(page + 1, w0, h0, w1, h1)
    if cx > 0.05 or cy > 0.05:
        txt += tr(" (je {0:.1f} mm links/rechts, {1:.1f} mm oben/unten)").format(cx / MM, cy / MM)
    if notes:
        txt += " – " + tr("⚠ kleiner als das Zielformat, dort nicht beschnitten")
    return txt


def crop_doc(doc, s: _cmyk.ManipSettings):
    """Kopie mit beschnittenen Seiten + Liste der Seiten, die kleiner als das Ziel sind."""
    import pypdfium2 as pdfium
    buf = io.BytesIO()
    doc.save(buf)
    out = pdfium.PdfDocument(buf.getvalue())
    small = []
    tgt = target_pt(s)
    for i in range(len(out)):
        pg = out[i]
        new, _cx, _cy, notes = crop_box_for(pg.get_cropbox(), pg.get_rotation(), tgt, s.crop_follow)
        pg.set_mediabox(*new)
        pg.set_cropbox(*new)
        pg.set_trimbox(*new)
        pg.set_bleedbox(*new)
        pg.close()
        if notes:
            small.append(i + 1)
    b2 = io.BytesIO()
    out.save(b2)
    out.close()
    return pdfium.PdfDocument(b2.getvalue()), small


def apply(doc, s: _cmyk.ManipSettings):
    """Alle aktiven Manipulationen anwenden. Liefert (neues Dokument, Hinweise). Original bleibt unverändert."""
    import pypdfium2 as pdfium
    notes = []
    cur = doc
    if s.crop:
        cur, small = crop_doc(cur, s)
        if small:
            notes.append(tr("Seiten kleiner als das Zielformat (nicht beschnitten): {0}").format(
                ", ".join(map(str, small[:20])) + (" …" if len(small) > 20 else "")))
    if s.cmyk and (s.target or s.cmyk_mode == "gray"):
        tmp = tempfile.mkdtemp(prefix="passermark-manip-")
        try:
            src, dst = os.path.join(tmp, "in.pdf"), os.path.join(tmp, "out.pdf")
            cur.save(src)
            _cmyk.convert_pdf(src, dst, s)
            with open(dst, "rb") as f:
                data = f.read()
            if cur is not doc:
                cur.close()
            cur = pdfium.PdfDocument(data)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
    return cur, notes
