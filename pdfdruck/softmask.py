# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Transparente Verläufe (Soft-Maske) gezielt in deckende Bilder umwandeln – ohne Ghostscript.

Hintergrund: Browser (Chrome/Skia, auch Canva-Exporte) legen CSS-Verläufe mit Transparenz als
Muster an, in dem ein Verlauf über eine Soft-Maske (Luminosity) halbtransparent wird. Die
Verlaufsfarbe fällt dort, wo er durchsichtig ist, auf Schwarz. Manche RIPs/Plotter ignorieren die
Soft-Maske – dann wird der Verlauf zur schwarzen Fläche und deckt darunterliegende Bilder ab.

Reparatur: Jeder betroffene Mal-Befehl wird samt allem, was darunter liegt, als deckendes Bild
gerendert (Kopie der Seite, die genau nach diesem Befehl endet) und ersetzt nur diesen Befehl.
Alles, was danach gezeichnet wird (Text, Logos, Linien), bleibt Vektor.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

from .l10n import tr

FILL_OPS = {"f", "F", "f*", "B", "B*", "b", "b*"}
PATH_OPS = {"m", "l", "c", "v", "y", "h", "re"}
I6 = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _mul(a, b):
    """a·b (PDF-Matrizen, Zeilenvektor-Konvention: erst a, dann b)."""
    return (a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3],
            a[2] * b[0] + a[3] * b[2], a[2] * b[1] + a[3] * b[3],
            a[4] * b[0] + a[5] * b[2] + b[4], a[4] * b[1] + a[5] * b[3] + b[5])


def _inv(m):
    a, b, c, d, e, f = m
    det = a * d - b * c
    if abs(det) < 1e-12:
        return None
    ia, ib, ic, id_ = d / det, -b / det, -c / det, a / det
    return (ia, ib, ic, id_, -(e * ia + f * ic), -(e * ib + f * id_))


def _pt(m, x, y):
    return (x * m[0] + y * m[2] + m[4], x * m[1] + y * m[3] + m[5])


def _nums(ins):
    out = []
    for o in ins.operands:
        try:
            out.append(float(o))
        except (TypeError, ValueError):
            return []
    return out


def _has_smask_gs(res, seen=None) -> bool:
    """Steckt in diesen Ressourcen (oder darin verschachtelten Mustern/Formularen) eine Soft-Maske?"""
    import pikepdf
    if res is None:
        return False
    seen = seen if seen is not None else set()
    try:
        k = res.objgen if res.objgen != (0, 0) else id(res)
    except Exception:
        k = id(res)
    if k in seen:
        return False
    seen.add(k)
    for _n, gs in (res.get("/ExtGState") or {}).items():
        sm = gs.get("/SMask")
        if sm is not None and str(sm) != "/None":
            return True
    for sub in ("/Pattern", "/XObject"):
        for _n, x in (res.get(sub) or {}).items():
            try:
                if sub == "/XObject" and x.get("/Subtype") != pikepdf.Name.Form:
                    continue
                if _has_smask_gs(x.get("/Resources"), seen):
                    return True
                eg = x.get("/ExtGState")              # Shading-Muster mit eigenem Grafikzustand
                if eg is not None and eg.get("/SMask") is not None and str(eg.get("/SMask")) != "/None":
                    return True
            except Exception:
                pass
    return False


def pattern_has_softmask(pat) -> bool:
    """Muster, das selbst mit Soft-Maske halbtransparent malt (Chrome-CSS-Verlauf o. Ä.)."""
    try:
        if int(pat.get("/PatternType", 0)) == 1:
            return _has_smask_gs(pat.get("/Resources"))
        eg = pat.get("/ExtGState")
        return eg is not None and eg.get("/SMask") is not None and str(eg.get("/SMask")) != "/None"
    except Exception:
        return False


@dataclass
class Target:
    page: int                         # Seitenindex (0-basiert)
    chain: list                       # [(Stromschlüssel, Index des Do)] von der Seite bis zum Formular
    stream: tuple                     # ("page", i) | ("obj", objgen)
    start: int                        # erster Pfad-Befehl
    end: int                          # Mal-Befehl (f / sh …)
    ctm: tuple                        # CTM beim Malen (Nutzer- -> Seitenraum)
    bbox: tuple                       # Seitenraum (x0, y0, x1, y1)
    kind: str = "pattern"             # pattern | shading


@dataclass
class Scan:
    targets: list = field(default_factory=list)
    skipped: int = 0                  # in mehrfach verwendeten Formularen (nicht sicher ersetzbar)
    form_uses: dict = field(default_factory=dict)


def _stream_ops(pdf, page, key):
    import pikepdf
    if key[0] == "page":
        return list(pikepdf.parse_content_stream(page))
    return list(pikepdf.parse_content_stream(pdf.get_object(key[1])))


def scan(pdf) -> Scan:
    """Alle Mal-Befehle, die einen Verlauf mit Soft-Maske zeichnen (pikepdf-Dokument)."""
    import pikepdf
    out = Scan()

    def walk(pi, page, key, ops, res, ctm, chain, depth):
        if depth > 12:
            return
        stack = []
        st = {"ctm": ctm, "fill_cs": None, "fill_pat": None, "smask": False}
        start, pts = None, []
        for idx, ins in enumerate(ops):
            op = str(getattr(ins, "operator", ""))
            if op == "q":
                stack.append(dict(st))
            elif op == "Q":
                if stack:
                    st = stack.pop()
            elif op == "cm":
                v = _nums(ins)
                if len(v) == 6:
                    st["ctm"] = _mul(tuple(v), st["ctm"])
            elif op == "gs" and ins.operands:
                g = (res.get("/ExtGState") or {}).get(str(ins.operands[0]))
                if g is not None and "/SMask" in g:
                    st["smask"] = str(g.get("/SMask")) != "/None"
            elif op == "cs" and ins.operands:
                st["fill_cs"] = str(ins.operands[0])
                st["fill_pat"] = None
            elif op == "scn" and ins.operands:
                last = ins.operands[-1]
                st["fill_pat"] = str(last) if isinstance(last, pikepdf.Name) else None
            elif op in ("g", "rg", "k", "sc"):
                st["fill_cs"], st["fill_pat"] = None, None
            elif op in PATH_OPS:
                if start is None:
                    start, pts = idx, []
                v = _nums(ins)
                if op == "re" and len(v) == 4:
                    x, y, w, h = v
                    pts += [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]
                else:
                    pts += [(v[i], v[i + 1]) for i in range(0, len(v) - 1, 2)]
            elif op in FILL_OPS and start is not None:
                pat = None
                if st["fill_pat"]:
                    pat = (res.get("/Pattern") or {}).get(st["fill_pat"])
                risky = False
                kind = "pattern"
                if pat is not None and pattern_has_softmask(pat):
                    risky = True
                elif pat is not None and st["smask"] and int(pat.get("/PatternType", 0)) == 2:
                    risky, kind = True, "shading"
                if risky and pts:
                    pp = [_pt(st["ctm"], x, y) for x, y in pts]
                    bbox = (min(p[0] for p in pp), min(p[1] for p in pp), max(p[0] for p in pp), max(p[1] for p in pp))
                    out.targets.append(Target(pi, list(chain), key, start, idx, st["ctm"], bbox, kind))
                start, pts = None, []
            elif op in ("n", "S", "s"):
                start, pts = None, []
            elif op == "sh" and st["smask"]:
                # Verlauf über die ganze Clipfläche: Größe unbekannt -> als Seitenfläche behandeln
                mb = [float(v) for v in page.mediabox]
                out.targets.append(Target(pi, list(chain), key, idx, idx, st["ctm"],
                                          (mb[0], mb[1], mb[2], mb[3]), "shading"))
            elif op == "Do" and ins.operands:
                x = (res.get("/XObject") or {}).get(str(ins.operands[0]))
                try:
                    if x is None or x.get("/Subtype") != pikepdf.Name.Form:
                        continue
                except Exception:
                    continue
                og = x.objgen
                out.form_uses[og] = out.form_uses.get(og, 0) + 1
                m = tuple(float(v) for v in x.get("/Matrix", [1, 0, 0, 1, 0, 0]))
                sub_res = x.get("/Resources") or res
                walk(pi, page, ("obj", og), list(pikepdf.parse_content_stream(x)), sub_res,
                     _mul(m, st["ctm"]), chain + [(key, idx)], depth + 1)

    for pi, page in enumerate(pdf.pages):
        res = page.obj.get("/Resources") or page.obj.get("/Parent", {}).get("/Resources") or pikepdf.Dictionary()
        walk(pi, page, ("page", pi), list(pikepdf.parse_content_stream(page)), res, I6, [], 0)
    keep = []
    for t in out.targets:
        if t.stream[0] == "obj" and out.form_uses.get(t.stream[1], 0) > 1:
            out.skipped += 1                    # gleiches Formular mehrfach -> Hintergrund je Verwendung anders
        else:
            keep.append(t)
    out.targets = keep
    return out


def count_softmask_paints(data: bytes) -> dict:
    """Seite (1-basiert) -> Anzahl betroffener Verläufe."""
    import pikepdf
    with pikepdf.open(io.BytesIO(data)) as pdf:
        sc = scan(pdf)
    res = {}
    for t in sc.targets:
        res[t.page + 1] = res.get(t.page + 1, 0) + 1
    return res


def _render_upto(data: bytes, t: Target, dpi: int):
    """Seite rendern, die genau nach dem Mal-Befehl t endet; Ausschnitt = t.bbox -> PIL-Bild."""
    import pikepdf
    import pypdfium2 as pdfium
    with pikepdf.open(io.BytesIO(data)) as pdf:
        page = pdf.pages[t.page]
        cuts = list(t.chain) + [(t.stream, t.end)]
        for key, idx in cuts:
            ops = _stream_ops(pdf, page, key)[:idx + 1]
            raw = pikepdf.unparse_content_stream(ops)
            if key[0] == "page":
                page.obj.Contents = pikepdf.Stream(pdf, raw)
            else:
                pdf.get_object(key[1]).write(raw)
        if "/Annots" in page.obj:
            del page.obj["/Annots"]
        if "/Rotate" in page.obj:
            del page.obj["/Rotate"]
        buf = io.BytesIO()
        pdf.save(buf)
    doc = pdfium.PdfDocument(buf.getvalue())
    try:
        pg = doc[t.page]
        cb = pg.get_cropbox()
        x0, y0 = max(t.bbox[0], cb[0]), max(t.bbox[1], cb[1])
        x1, y1 = min(t.bbox[2], cb[2]), min(t.bbox[3], cb[3])
        if x1 - x0 < 0.5 or y1 - y0 < 0.5:
            return None, None
        s = dpi / 72.0
        img = pg.render(scale=s, crop=(x0 - cb[0], y0 - cb[1], cb[2] - x1, cb[3] - y1),
                        draw_annots=False).to_pil().convert("RGB")
        pg.close()
        return img, (x0, y0, x1, y1)
    finally:
        doc.close()


def flatten_softmask_paints(data: bytes, dpi: int = 300, progress=None) -> tuple[bytes, list]:
    """Verläufe mit Soft-Maske in deckende Bilder umwandeln. -> (neue Daten, Hinweise)."""
    import pikepdf
    with pikepdf.open(io.BytesIO(data)) as pdf:
        sc = scan(pdf)
    notes = []
    if not sc.targets:
        if sc.skipped:
            notes.append(tr("{0} transparente(r) Verlauf/Verläufe in mehrfach verwendeten Elementen – nicht "
                            "umgewandelt, bitte „Transparenzen reduzieren“ verwenden.").format(sc.skipped))
        return data, notes
    rendered = []
    for n, t in enumerate(sc.targets):
        if progress:
            progress(n, len(sc.targets))
        img, box = _render_upto(data, t, dpi)
        if img is not None:
            rendered.append((t, img, box))
    pdf = pikepdf.open(io.BytesIO(data))
    try:
        by_stream: dict = {}
        for t, img, box in rendered:
            by_stream.setdefault((t.page, t.stream), []).append((t, img, box))
        counter = 0
        for (pi, key), items in by_stream.items():
            page = pdf.pages[pi]
            ops = _stream_ops(pdf, page, key)
            if key[0] == "page":
                if "/Resources" not in page.obj:
                    page.obj.Resources = pikepdf.Dictionary()
                res = page.obj.Resources
            else:
                form = pdf.get_object(key[1])
                if "/Resources" not in form:
                    form.Resources = pikepdf.Dictionary()
                res = form.Resources
            if "/XObject" not in res:
                res.XObject = pikepdf.Dictionary()
            if "/ExtGState" not in res:
                res.ExtGState = pikepdf.Dictionary()
            gname = pikepdf.Name("/PMOpaque")
            res.ExtGState[gname] = pikepdf.Dictionary(Type=pikepdf.Name.ExtGState, SMask=pikepdf.Name("/None"),
                                                      ca=1, CA=1, BM=pikepdf.Name.Normal)
            for t, img, box in sorted(items, key=lambda x: -x[0].start):
                counter += 1
                buf = io.BytesIO()
                img.save(buf, "JPEG", quality=92, subsampling=0)
                xo = pikepdf.Stream(pdf, buf.getvalue(), Type=pikepdf.Name.XObject, Subtype=pikepdf.Name.Image,
                                    Width=img.width, Height=img.height, ColorSpace=pikepdf.Name.DeviceRGB,
                                    BitsPerComponent=8, Filter=pikepdf.Name.DCTDecode)
                name = pikepdf.Name(f"/PMFlat{counter}")
                res.XObject[name] = xo
                inv = _inv(t.ctm)
                if inv is None:
                    continue
                mb = (box[2] - box[0], 0.0, 0.0, box[3] - box[1], box[0], box[1])
                m = _mul(mb, inv)
                new = [pikepdf.ContentStreamInstruction([], pikepdf.Operator("q")),
                       pikepdf.ContentStreamInstruction([gname], pikepdf.Operator("gs")),
                       pikepdf.ContentStreamInstruction([round(v, 6) for v in m], pikepdf.Operator("cm")),
                       pikepdf.ContentStreamInstruction([name], pikepdf.Operator("Do")),
                       pikepdf.ContentStreamInstruction([], pikepdf.Operator("Q"))]
                ops[t.start:t.end + 1] = new
            raw = pikepdf.unparse_content_stream(ops)
            if key[0] == "page":
                page.obj.Contents = pikepdf.Stream(pdf, raw)
            else:
                pdf.get_object(key[1]).write(raw)
            # nicht mehr verwendete Muster mit Soft-Maske aus den Ressourcen dieses Inhalts entfernen
            used = {str(o) for ins in ops for o in getattr(ins, "operands", [])
                    if isinstance(o, pikepdf.Name)}
            pats = res.get("/Pattern")
            if pats is not None:
                for n in [n for n, pat in pats.items() if n not in used and pattern_has_softmask(pat)]:
                    del pats[n]
        out = io.BytesIO()
        pdf.save(out)
        notes.append(tr("{0} transparente(r) Verlauf/Verläufe in Bilder umgewandelt ({1} dpi) – Text und Vektoren "
                        "darüber bleiben erhalten.").format(len(rendered), dpi))
        if sc.skipped:
            notes.append(tr("{0} weitere(r) in mehrfach verwendeten Elementen – nicht umgewandelt.").format(sc.skipped))
        return out.getvalue(), notes
    finally:
        pdf.close()


def rip_simulation(data: bytes) -> bytes:
    """Zum Prüfen: alle Soft-Masken in Grafikzuständen entfernen – so drucken RIPs, die sie ignorieren."""
    import pikepdf
    with pikepdf.open(io.BytesIO(data)) as pdf:
        for o in pdf.objects:
            try:
                if isinstance(o, (pikepdf.Dictionary, pikepdf.Stream)) and o.get("/Type") == pikepdf.Name.ExtGState \
                        and "/SMask" in o:
                    del o["/SMask"]
            except Exception:
                pass
        # auch direkte (nicht indirekte) ExtGState-Einträge
        def strip(res, seen):
            if res is None or id(res) in seen:
                return
            seen.add(id(res))
            for _n, g in (res.get("/ExtGState") or {}).items():
                if "/SMask" in g:
                    del g["/SMask"]
            for sub in ("/Pattern", "/XObject"):
                for _n, x in (res.get(sub) or {}).items():
                    try:
                        strip(x.get("/Resources"), seen)
                    except Exception:
                        pass
        seen = set()
        for p in pdf.pages:
            strip(p.obj.get("/Resources"), seen)
        buf = io.BytesIO()
        pdf.save(buf)
        return buf.getvalue()
