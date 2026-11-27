# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Check report as PDF (1.20.2): summary pages followed by the pages with findings, every location framed in
the colour of its severity and numbered like the finding in the summary.

The summary is set with reportlab, the marked pages are the original pages (copied with pikepdf) with an overlay
drawn in page coordinates – the frames sit exactly where the document check found something, also on rotated
pages. No Qt.
"""

from __future__ import annotations

import datetime
import io
from xml.sax.saxutils import escape

from .l10n import tr

# printable colours per severity (the yellow of the interface is not readable on white paper)
SEV_RGB = {"error": (0.85, 0.12, 0.12), "warning": (0.88, 0.50, 0.0), "info": (0.40, 0.42, 0.48)}
OK_RGB = (0.18, 0.62, 0.31)
MAX_MARKED_PAGES = 200  # marked pages at most (large documents: the first ones)
MAX_SPOTS_LISTED = 8  # locations per finding in the summary
MAX_MARKS = 40  # frames per finding and page


def _sev_text(sev: str) -> str:
    return {"error": tr("Fehler"), "warning": tr("Warnung"), "info": tr("Hinweis")}.get(sev, sev)


def marks(rep) -> dict:
    """Locations with an area per page: {page: [(number of the finding, severity, box)]} (numbers from 1)."""
    out: dict = {}
    for nr, iss in enumerate(rep.issues, start=1):
        per: dict = {}
        for sp in iss.spots:
            if sp.box is None:
                continue
            lst = per.setdefault(sp.page, [])
            if len(lst) < MAX_MARKS:
                lst.append((nr, iss.severity, tuple(float(v) for v in sp.box)))
        for p, lst in per.items():
            out.setdefault(p, []).extend(lst)
    return out


def write_pdf(rep, data: bytes, path: str, title: str = "", password: str | None = None) -> dict:
    """Write the report for ``rep`` (preflight.Report of ``data``) to ``path``.
    -> {"pages": pages of the report, "marked": marked document pages}"""
    import pikepdf

    mk = marks(rep)
    marked = sorted(mk)[:MAX_MARKED_PAGES]
    first = {}  # document page -> page of the report
    summary = _summary(rep, title, marked)
    with pikepdf.open(io.BytesIO(summary)) as out:
        n_sum = len(out.pages)
        if marked:
            with pikepdf.open(io.BytesIO(data), password=password or "") as src:
                for p in marked:
                    if not (1 <= p <= len(src.pages)):
                        continue
                    out.pages.append(src.pages[p - 1])
                    _overlay(out, out.pages[-1], mk[p])
                    first[p] = len(out.pages)
                _outline(out, n_sum, first, rep)
        out.docinfo["/Title"] = tr("Prüfbericht") + (f": {title}" if title else "")
        out.docinfo["/Creator"] = "Passermark"
        out.save(path)
        return {"pages": len(out.pages), "marked": len(first)}


# --------------------------------------------------------------------------- #
# marked pages
# --------------------------------------------------------------------------- #
def _num(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _overlay(pdf, page, items):
    """Frames and number labels on top of the page content (the content itself wrapped in q/Q)."""
    import math

    import pikepdf

    from .preflight import _box, _inh

    mb = _box(_inh(page.obj, "/MediaBox")) or (0.0, 0.0, 612.0, 792.0)
    rot = int(_inh(page.obj, "/Rotate") or 0) % 360
    short = min(mb[2] - mb[0], mb[3] - mb[1])
    lw = max(0.8, short / 350.0)
    fs = max(7.0, short / 60.0)
    font = pikepdf.Dictionary(
        Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name("/Helvetica-Bold")
    )
    fname = page.add_resource(pdf.make_indirect(font), pikepdf.Name.Font, prefix="PMR")
    a = math.radians(rot)  # text counter-rotated so it stands upright in the rotated view
    c, s = round(math.cos(a), 6), round(math.sin(a), 6)
    ops = []
    labelled = set()
    taken: dict = {}  # label anchor -> width already used there (labels of several findings side by side)
    order = {"info": 0, "warning": 1, "error": 2}  # errors drawn last, on top
    for nr, sev, (x0, y0, x1, y1) in sorted(items, key=lambda it: (order.get(it[1], 0), it[0])):
        r, g, b = SEV_RGB.get(sev, SEV_RGB["info"])
        pad = 1.5 * lw
        x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
        ops.append(f"{_num(r)} {_num(g)} {_num(b)} RG {_num(lw)} w [] 0 d")
        ops.append(f"{_num(x0)} {_num(y0)} {_num(x1 - x0)} {_num(y1 - y0)} re S")
        key = (nr, round(x0 / 20), round(y1 / 20))
        if key in labelled:
            continue
        labelled.add(key)
        txt = str(nr)
        w = 0.62 * fs * len(txt) + fs * 0.5
        h = fs * 1.25
        # label above the upper left corner of the frame as seen in the (rotated) view, drawn upright there
        tx, ty = {0: (x0, y1), 90: (x0, y0), 180: (x1, y0), 270: (x1, y1)}[rot]
        anchor = (round(tx / fs), round(ty / fs))
        shift = taken.get(anchor, 0.0)
        taken[anchor] = shift + w + lw
        tx, ty = tx + c * shift, ty + s * shift
        ops.append(f"q {_num(c)} {_num(s)} {_num(-s)} {_num(c)} {_num(tx)} {_num(ty)} cm")
        ops.append(f"{_num(r)} {_num(g)} {_num(b)} rg 0 0 {_num(w)} {_num(h)} re f")
        ops.append(f"1 1 1 rg BT {fname} {_num(fs)} Tf {_num(fs * 0.25)} {_num(fs * 0.28)} Td ({txt}) Tj ET Q")
    page.contents_add(pikepdf.Stream(pdf, b"q\n"), prepend=True)
    page.contents_add(pikepdf.Stream(pdf, ("\nQ\nq\n" + "\n".join(ops) + "\nQ\n").encode("ascii")))


def _outline(pdf, n_sum: int, first: dict, rep):
    """Bookmarks: summary and every marked page with its findings."""
    import pikepdf

    with pdf.open_outline() as ol:
        ol.root.append(pikepdf.OutlineItem(tr("Zusammenfassung"), 0))
        for p, at in first.items():
            nrs = sorted({nr for nr, iss in enumerate(rep.issues, 1) for sp in iss.spots if sp.page == p and sp.box})
            label = tr("Seite {0}").format(p) + "  (" + ", ".join(f"#{n}" for n in nrs) + ")"
            ol.root.append(pikepdf.OutlineItem(label, at - 1))


# --------------------------------------------------------------------------- #
# summary
# --------------------------------------------------------------------------- #
def _hex(rgb) -> str:
    return "#" + "".join(f"{round(v * 255):02x}" for v in rgb)


def _summary(rep, title: str, marked: list) -> bytes:
    """Summary pages (A4) with reportlab."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from . import __version__, checkprofile, preflight
    from .vdp import _font_for

    texts = [title, *(i.message for i in rep.issues), *(f.name for f in rep.fonts)]
    font = _font_for("Helvetica", " ".join(texts) + tr("Prüfbericht"))
    bold = "Helvetica-Bold" if font == "Helvetica" else font
    base = ParagraphStyle("pm", fontName=font, fontSize=9, leading=11.5)
    small = ParagraphStyle("pms", parent=base, fontSize=8, leading=10, textColor=colors.HexColor("#555555"))
    head = ParagraphStyle("pmh", parent=base, fontName=bold, fontSize=16, leading=20, spaceAfter=4)
    h2 = ParagraphStyle("pmh2", parent=base, fontName=bold, fontSize=11, leading=14, spaceBefore=10, spaceAfter=4)

    c = rep.counts()
    story = [Paragraph(escape(tr("Passermark – Prüfbericht")), head)]
    meta = [
        escape(title) if title else "",
        escape(
            tr("{0} Seiten · Prüfprofil: {1} · {2} · Passermark {3}").format(
                rep.pages,
                rep.profile.title() if rep.profile is not None else checkprofile.DEFAULT,
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                __version__,
            )
        ),
    ]
    story += [Paragraph(m, small) for m in meta if m]
    story.append(Spacer(1, 4 * mm))
    if not c["error"] and not c["warning"]:
        status, rgb = tr("Druckbereit – keine Fehler und Warnungen."), OK_RGB
    else:
        parts = []
        if c["error"]:
            parts.append(tr("{0} Fehler").format(c["error"]))
        if c["warning"]:
            parts.append(tr("{0} Warnung(en)").format(c["warning"]))
        if c["info"]:
            parts.append(tr("{0} Hinweis(e)").format(c["info"]))
        status, rgb = " · ".join(parts), SEV_RGB["error" if c["error"] else "warning"]
    st = ParagraphStyle("pmst", parent=base, fontName=bold, fontSize=12, leading=15, textColor=colors.white)
    box = Table([[Paragraph(escape(status), st)]], colWidths=[A4[0] - 36 * mm])
    box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(_hex(rgb))),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(box)
    hint_at = None
    if marked:
        story.append(Spacer(1, 2 * mm))
        hint_at = len(story)
        story.append(None)  # hint with the first marked page – known only after the layout
    if rep.issues:
        story.append(Paragraph(escape(tr("Befunde")), h2))
        rows = []
        styles = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]
        for nr, iss in enumerate(rep.issues, start=1):
            sev_style = ParagraphStyle(
                f"pmsev{nr}", parent=base, fontName=bold, textColor=colors.HexColor(_hex(SEV_RGB[iss.severity]))
            )
            body = escape(iss.message)
            if iss.pages:
                body += "<br/>" + escape(tr("Seiten {0}").format(preflight._pages_str(iss.pages)))
            located = [sp for sp in iss.spots if sp.box is not None or sp.label]
            lines = [escape(preflight.where_text(rep, sp)) for sp in located[:MAX_SPOTS_LISTED]]
            if len(located) > MAX_SPOTS_LISTED:
                lines.append(escape(tr("… und {0} weitere").format(len(located) - MAX_SPOTS_LISTED)))
            cell = [Paragraph(body, base)] + ([Paragraph("<br/>".join(lines), small)] if lines else [])
            rows.append([Paragraph(f"#{nr}", sev_style), Paragraph(escape(_sev_text(iss.severity)), sev_style), cell])
            styles.append(("LINEBEFORE", (0, nr - 1), (0, nr - 1), 3, colors.HexColor(_hex(SEV_RGB[iss.severity]))))
        t = Table(rows, colWidths=[12 * mm, 20 * mm, A4[0] - 36 * mm - 32 * mm], repeatRows=0)
        t.setStyle(TableStyle(styles))
        story.append(t)
    if rep.passed:
        story.append(Paragraph(escape(tr("Ohne Befund")), h2))
        labels = [tr(checkprofile.CHECKS[k][2]) for k in rep.passed if k in checkprofile.CHECKS]
        story.append(Paragraph(escape(" · ".join(labels)), small))
    if rep.fonts:
        story.append(Paragraph(escape(tr("Schriften")), h2))
        st_txt = {
            "ok": tr("eingebettet"),
            "std14": tr("Standard, nicht eingebettet"),
            "missing": tr("NICHT eingebettet"),
            "type3": "Type3",
        }
        frows = [
            [
                Paragraph(escape(f.name), small),
                Paragraph(escape(f.subtype), small),
                Paragraph(escape(st_txt.get(f.status, f.status) + (tr("  ·  Teilmenge") if f.subset else "")), small),
            ]
            for f in rep.fonts[:80]
        ]
        ft = Table(frows, colWidths=[70 * mm, 30 * mm, A4[0] - 36 * mm - 100 * mm])
        ft.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 2)]))
        story.append(ft)

    def hint(at: int):
        return Paragraph(
            escape(
                tr("Ab Seite {0} folgen die {1} Seite(n) mit markierten Stellen (Nummern wie in der Liste).").format(
                    at, len(marked)
                )
            ),
            small,
        )

    def build(first_marked: int) -> tuple[bytes, int]:
        if hint_at is not None:
            story[hint_at] = hint(first_marked)
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=16 * mm,
            bottomMargin=16 * mm,
            title=tr("Prüfbericht"),
            author="Passermark",
        )
        doc.build(list(story))
        return buf.getvalue(), doc.page

    pdf, n = build(2)
    if hint_at is not None and n != 1:
        pdf, _n = build(n + 1)
    return pdf
