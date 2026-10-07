# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Preflight: Dokument prüfen (Schriften, Ebenen, Transparenzen, Zeichen) und gezielt reparieren.

Das Original wird nie verändert – alle Funktionen arbeiten auf Bytes und liefern neue Bytes.

Analyse:
  Schriften     eingebettet / Teilmenge / nicht eingebettet, Typ (TrueType, Type1, CID, Type3), ToUnicode,
                Standard-14, auf welchen Seiten; Ersatzvorschlag (metrisch kompatible freie Schriften)
  Zeichen       Seiten mit unlesbaren Zeichen (keine gültige Unicode-Zuordnung)
  Ebenen        Optional Content: Zustand für Ansicht und Druck, Seiten, Inhalt außerhalb der Seite
  Transparenz   weiche Masken, Füllmethoden, Deckkraft, Transparenzgruppen, Überdrucken
Reparaturen:
  Ebenen-Zustand setzen, Ebenen festschreiben (sichtbarer Zustand, Marker entfernt), Ebenen entfernen,
  Schriften einbetten (mit Ersatz), Text in Pfade, Transparenzen reduzieren (Ghostscript)
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from . import platform as _platform
from .l10n import tr

STANDARD14 = {"Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique", "Helvetica", "Helvetica-Bold",
              "Helvetica-Oblique", "Helvetica-BoldOblique", "Times-Roman", "Times-Bold", "Times-Italic",
              "Times-BoldItalic", "Symbol", "ZapfDingbats"}

# Metrisch kompatible freie Ersatzschriften (gleiche Zeichenbreiten -> Text verrutscht nicht)
METRIC = [
    (r"arial|helvetica|arimo", "Liberation Sans"),
    (r"timesnewroman|times|tinos", "Liberation Serif"),
    (r"couriernew|courier|cousine", "Liberation Mono"),
    (r"calibri", "Carlito"),
    (r"cambria", "Caladea"),
    (r"isocp|isoct|isocpeur|isocteur", "osifont"),
    (r"^symbol$|symbolmt", "Standard Symbols PS"),
    (r"zapfdingbats", "D050000L"),
    (r"verdana", "DejaVu Sans"),
    (r"tahoma|segoeui", "DejaVu Sans"),
    (r"georgia", "Gelasio"),
]

SEV_ORDER = {"error": 0, "warning": 1, "info": 2}


@dataclass
class Issue:
    severity: str              # error | warning | info
    category: str              # font | layer | transparency | text
    message: str
    pages: list = field(default_factory=list)


@dataclass
class FontInfo:
    key: str
    name: str                  # ohne Teilmengen-Präfix
    raw: str
    subtype: str
    embedded: bool
    subset: bool
    tounicode: bool
    encoding: str
    cid: bool
    standard14: bool
    pages: set = field(default_factory=set)
    suggestion: str = ""       # Pfad der Ersatzschrift
    suggestion_name: str = ""

    @property
    def status(self) -> str:
        if self.subtype == "Type3":
            return "type3"
        if self.embedded:
            return "ok"
        if self.standard14:
            return "std14"
        return "missing"


@dataclass
class LayerInfo:
    key: str
    name: str
    view_on: bool
    print_on: bool | None      # None = keine eigene Druck-Einstellung (folgt der Ansicht)
    locked: bool = False
    pages: set = field(default_factory=set)
    outside_pct: float | None = None


@dataclass
class Report:
    pages: int = 0
    fonts: list = field(default_factory=list)
    layers: list = field(default_factory=list)
    transparency: dict = field(default_factory=dict)   # Seite -> {Art}
    garbled: dict = field(default_factory=dict)        # Seite -> Anzahl
    issues: list = field(default_factory=list)

    def counts(self):
        c = {"error": 0, "warning": 0, "info": 0}
        for i in self.issues:
            c[i.severity] += 1
        return c


# --------------------------------------------------------------------------- #
# Hilfen
# --------------------------------------------------------------------------- #
def _key(obj) -> str:
    try:
        og = obj.objgen
        if og != (0, 0):
            return f"{og[0]} {og[1]}"
    except Exception:
        pass
    return f"id{id(obj)}"


def _resources(page):
    import pikepdf
    node = page.obj
    while node is not None:
        if "/Resources" in node:
            return node.Resources
        node = node.get("/Parent")
    return pikepdf.Dictionary()


def _pages_str(pages) -> str:
    ps = sorted(pages)
    if not ps:
        return ""
    out, start, prev = [], ps[0], ps[0]
    for p in ps[1:] + [None]:
        if p is not None and p == prev + 1:
            prev = p
            continue
        out.append(f"{start}" if start == prev else f"{start}–{prev}")
        if p is not None:
            start = prev = p
    return ", ".join(out[:8]) + (" …" if len(out) > 8 else "")


def _walk_resources(res, page_no, visit, seen):
    """Ressourcen inkl. Form-XObjects (verschachtelt) besuchen."""
    import pikepdf
    if res is None:
        return
    rk = _key(res)
    if rk in seen:
        return
    seen.add(rk)
    visit(res, page_no)
    xo = res.get("/XObject")
    if xo is not None:
        for _n, x in xo.items():
            try:
                if x.get("/Subtype") == pikepdf.Name.Form:
                    _walk_resources(x.get("/Resources"), page_no, visit, seen)
            except Exception:
                pass


# --------------------------------------------------------------------------- #
# Analyse
# --------------------------------------------------------------------------- #
def analyze(data: bytes, deep_layers: bool = True) -> Report:
    import pikepdf
    rep = Report()
    pdf = pikepdf.open(io.BytesIO(data))
    try:
        rep.pages = len(pdf.pages)
        fonts: dict[str, FontInfo] = {}
        trans: dict[int, set] = {}

        def visit(res, pno):
            for _n, f in (res.get("/Font") or {}).items():
                k = _key(f)
                if k not in fonts:
                    fonts[k] = _font_info(f, k)
                fonts[k].pages.add(pno)
            for _n, gs in (res.get("/ExtGState") or {}).items():
                sm = gs.get("/SMask")
                if sm is not None and str(sm) != "/None":
                    trans.setdefault(pno, set()).add("smask")
                bm = gs.get("/BM")
                if bm is not None:
                    names = [str(b) for b in (bm if isinstance(bm, pikepdf.Array) else [bm])]
                    if any(n not in ("/Normal", "/Compatible") for n in names):
                        trans.setdefault(pno, set()).add("blend")
                for k in ("/CA", "/ca"):
                    try:
                        if k in gs and float(gs[k]) < 0.999:
                            trans.setdefault(pno, set()).add("alpha")
                    except Exception:
                        pass
                if gs.get("/OP") is True or gs.get("/op") is True:
                    trans.setdefault(pno, set()).add("overprint")
            for _n, x in (res.get("/XObject") or {}).items():
                try:
                    if x.get("/Subtype") == pikepdf.Name.Image and "/SMask" in x:
                        trans.setdefault(pno, set()).add("image_alpha")
                    if x.get("/Subtype") == pikepdf.Name.Form and "/Group" in x:
                        if x.Group.get("/S") == pikepdf.Name.Transparency:
                            trans.setdefault(pno, set()).add("group")
                except Exception:
                    pass

        for i, page in enumerate(pdf.pages, start=1):
            seen = set()
            _walk_resources(_resources(page), i, visit, seen)
            for a in page.obj.get("/Annots") or []:
                try:
                    ap = a.get("/AP")
                    n = ap.get("/N") if ap is not None else None
                    if isinstance(n, pikepdf.Stream):
                        _walk_resources(n.get("/Resources"), i, visit, seen)
                except Exception:
                    pass
            g = page.obj.get("/Group")
            if g is not None and g.get("/S") == pikepdf.Name.Transparency:
                trans.setdefault(i, set()).add("group")
        rep.fonts = sorted(fonts.values(), key=lambda f: (f.status == "ok", f.name.lower()))
        for f in rep.fonts:
            if f.status in ("missing", "std14") and f.encoding != "private" and not (f.cid and f.encoding.startswith("Identity")):
                f.suggestion, f.suggestion_name = suggest_font(f.name)
        rep.transparency = trans
        rep.layers = _layers(pdf)
    finally:
        pdf.close()
    rep.garbled = _garbled(data)
    if deep_layers and rep.layers:
        try:
            _layers_outside(data, rep.layers)
        except Exception:
            pass
    rep.issues = _issues(rep)
    return rep


def _font_info(f, k) -> FontInfo:
    import pikepdf
    raw = str(f.get("/BaseFont", "/?"))[1:]
    subset = bool(re.match(r"^[A-Z]{6}\+", raw))
    name = raw.split("+", 1)[1] if subset else raw
    subtype = str(f.get("/Subtype", "/?"))[1:]
    cid = subtype == "Type0"
    desc = None
    if cid:
        try:
            d = f.DescendantFonts[0]
            desc = d.get("/FontDescriptor")
        except Exception:
            desc = None
    else:
        desc = f.get("/FontDescriptor")
    embedded = subtype == "Type3" or (desc is not None and any(k in desc for k in ("/FontFile", "/FontFile2", "/FontFile3")))
    enc = f.get("/Encoding")
    encoding = str(enc)[1:] if isinstance(enc, pikepdf.Name) else ("custom" if enc is not None else "")
    if isinstance(enc, pikepdf.Dictionary):
        # eigene Glyphennamen (g01, glyph12, cid45 …) -> Zeichenbedeutung nur in der Originalschrift
        names = [str(x) for x in (enc.get("/Differences") or []) if isinstance(x, pikepdf.Name)]
        if names and sum(bool(re.match(r"^/(g|glyph|cid|G|uni)?[0-9A-Fa-f]{1,5}$", n)) for n in names) > 0.5 * len(names):
            encoding = "private"
    return FontInfo(k, name, raw, subtype, embedded, subset, "/ToUnicode" in f, encoding, cid,
                    name in STANDARD14 and subtype == "Type1")


def _garbled(data: bytes) -> dict:
    """Seiten mit Zeichen ohne gültige Unicode-Zuordnung (Ersatzzeichen, Privatbereich, Steuerzeichen)."""
    import pypdfium2 as pdfium
    out = {}
    doc = pdfium.PdfDocument(data)
    try:
        for i in range(len(doc)):
            pg = doc[i]
            tp = pg.get_textpage()
            try:
                t = tp.get_text_range()
            finally:
                tp.close()
                pg.close()
            bad = sum(1 for ch in t if ch == "\ufffd" or "\ue000" <= ch <= "\uf8ff"
                      or (ord(ch) < 32 and ch not in "\r\n\t"))
            if bad >= 3 and bad > 0.02 * max(1, len(t)):
                out[i + 1] = bad
    finally:
        doc.close()
    return out


# --------------------------------------------------------------------------- #
# Ebenen
# --------------------------------------------------------------------------- #
def _ocp(pdf):
    return pdf.Root.get("/OCProperties")


def _layers(pdf) -> list[LayerInfo]:
    import pikepdf
    ocp = _ocp(pdf)
    if ocp is None:
        return []
    d = ocp.get("/D") or pikepdf.Dictionary()
    base_on = d.get("/BaseState", pikepdf.Name.ON) != pikepdf.Name.OFF
    on = {_key(o) for o in d.get("/ON") or []}
    off = {_key(o) for o in d.get("/OFF") or []}
    locked = {_key(o) for o in d.get("/Locked") or []}
    out = {}
    for g in ocp.get("/OCGs") or []:
        k = _key(g)
        view = (k in on) or (base_on and k not in off)
        pr = None
        try:
            ps = g.Usage.Print.PrintState
            pr = ps == pikepdf.Name.ON
        except Exception:
            pass
        out[k] = LayerInfo(k, str(g.get("/Name", "?")), view, pr, k in locked)
    # Seiten je Ebene (BDC /OC in Inhalten und XObjects mit /OC)
    for i, page in enumerate(pdf.pages, start=1):
        res = _resources(page)
        props = res.get("/Properties") or {}
        for kk in _oc_keys_in_stream(page, props, res, set()):
            if kk in out:
                out[kk].pages.add(i)
    return list(out.values())


def _ocgs_of(oc) -> list:
    import pikepdf
    if oc is None:
        return []
    if oc.get("/Type") == pikepdf.Name.OCMD:
        o = oc.get("/OCGs")
        if o is None:
            return []
        return list(o) if isinstance(o, pikepdf.Array) else [o]
    return [oc]


def _oc_keys_in_stream(obj, props, res, seen) -> set:
    import pikepdf
    keys = set()
    try:
        ops = pikepdf.parse_content_stream(obj)
    except Exception:
        return keys
    xo = res.get("/XObject") if res is not None else None
    for ins in ops:
        op = str(getattr(ins, "operator", ""))
        operands = getattr(ins, "operands", [])
        if op == "BDC" and len(operands) >= 2 and operands[0] == pikepdf.Name.OC:
            oc = props.get(operands[1]) if isinstance(operands[1], pikepdf.Name) else operands[1]
            for g in _ocgs_of(oc):
                keys.add(_key(g))
        elif op == "Do" and xo is not None and operands:
            x = xo.get(operands[0])
            if x is None:
                continue
            if "/OC" in x:
                for g in _ocgs_of(x.OC):
                    keys.add(_key(g))
            xk = _key(x)
            if x.get("/Subtype") == pikepdf.Name.Form and xk not in seen:
                seen.add(xk)
                xr = x.get("/Resources") or res
                keys |= _oc_keys_in_stream(x, xr.get("/Properties") or {}, xr, seen)
    return keys


def _layers_outside(data: bytes, layers: list[LayerInfo], max_layers=40, max_pages=6):
    """Je Ebene: wie viel ihres Inhalts liegt außerhalb der Seite? (Einzeln gerendert, Seite vergrößert)."""
    import numpy as np
    import pikepdf
    import pypdfium2 as pdfium
    for L in layers[:max_layers]:
        if not L.pages:
            continue
        pdf = pikepdf.open(io.BytesIO(data))
        try:
            ocp = _ocp(pdf)
            target = [g for g in ocp.OCGs if _key(g) == L.key]
            if not target:
                continue
            d = ocp.D
            d.BaseState = pikepdf.Name.OFF
            d.ON = pikepdf.Array(target)
            d.OFF = pikepdf.Array()
            if "/AS" in d:
                del d["/AS"]
            pages = sorted(L.pages)[:max_pages]
            boxes = {}
            for p in pages:
                pg = pdf.pages[p - 1]
                x0, y0, x1, y1 = [float(v) for v in (pg.obj.get("/CropBox") or pg.MediaBox)]
                w, h = x1 - x0, y1 - y0
                boxes[p] = (w, h)
                big = [x0 - w, y0 - h, x1 + w, y1 + h]
                pg.MediaBox = big
                pg.CropBox = big
            buf = io.BytesIO()
            pdf.save(buf)
        finally:
            pdf.close()
        doc = pdfium.PdfDocument(buf.getvalue())
        tot = outside = 0
        try:
            for p in pages:
                w, h = boxes[p]
                scale = 160.0 / max(w, h)
                bmp = doc[p - 1].render(scale=scale, fill_color=(255, 255, 255, 0))
                a = bmp.to_numpy()[:, :, 3] > 20
                H, W = a.shape
                ys, xs = slice(H // 3, H - H // 3), slice(W // 3, W - W // 3)
                inner = a[ys, xs].sum()
                total = a.sum()
                tot += total
                outside += total - inner
        finally:
            doc.close()
        L.outside_pct = (100.0 * outside / tot) if tot else None


def _visible(oc, visible: set) -> bool:
    import pikepdf
    if oc is None:
        return True
    if oc.get("/Type") == pikepdf.Name.OCMD:
        groups = [_key(g) for g in _ocgs_of(oc)]
        if not groups:
            return True
        states = [g in visible for g in groups]
        pol = str(oc.get("/P", "/AnyOn"))
        return {"/AllOn": all(states), "/AnyOff": not all(states), "/AllOff": not any(states)}.get(pol, any(states))
    return _key(oc) in visible


def _rewrite(pdf, obj, props, res, visible, strip, done):
    """Inhaltsstrom filtern: unsichtbare OC-Inhalte entfernen; bei strip auch die OC-Marker entfernen."""
    import pikepdf
    ok = _key(obj)
    if ok in done:
        return
    done.add(ok)
    try:
        ops = pikepdf.parse_content_stream(obj)
    except Exception:
        return
    xo = res.get("/XObject") if res is not None else None
    out, stack, skip = [], [], 0
    for ins in ops:
        op = str(getattr(ins, "operator", ""))
        operands = getattr(ins, "operands", [])
        if skip:
            if op in ("BDC", "BMC"):
                skip += 1
            elif op == "EMC":
                skip -= 1
            continue
        if op == "BDC" and len(operands) >= 2 and operands[0] == pikepdf.Name.OC:
            oc = props.get(operands[1]) if isinstance(operands[1], pikepdf.Name) else operands[1]
            if not _visible(oc, visible):
                skip = 1
                continue
            stack.append("drop" if strip else "keep")
            if not strip:
                out.append(ins)
            continue
        if op in ("BDC", "BMC"):
            stack.append("keep")
        elif op == "EMC":
            if (stack.pop() if stack else "keep") == "drop":
                continue
        elif op == "Do" and xo is not None and operands:
            x = xo.get(operands[0])
            if x is not None:
                if "/OC" in x and not _visible(x.OC, visible):
                    continue
                if x.get("/Subtype") == pikepdf.Name.Form:
                    xr = x.get("/Resources") or res
                    _rewrite(pdf, x, xr.get("/Properties") or {}, xr, visible, strip, done)
                    if strip and "/OC" in x:
                        del x["/OC"]
        out.append(ins)
    data = pikepdf.unparse_content_stream(out)
    if isinstance(obj, pikepdf.Page):
        obj.obj.Contents = pikepdf.Stream(pdf, data)
    else:
        obj.write(data)


def _apply_visibility(pdf, visible: set, strip: bool):
    import pikepdf
    done = set()
    for page in pdf.pages:
        res = _resources(page)
        props = res.get("/Properties") or {}
        _rewrite(pdf, page, props, res, visible, strip, done)
        annots = page.obj.get("/Annots")
        if annots is not None:
            keep = pikepdf.Array([a for a in annots if "/OC" not in a or _visible(a.OC, visible)])
            if strip:
                for a in keep:
                    if "/OC" in a:
                        del a["/OC"]
            page.obj.Annots = keep


def current_visible(pdf, use_print=True) -> set:
    """Sichtbare Ebenen: für den Druck (Druck-Einstellung, sonst Ansicht) bzw. für die Ansicht."""
    vis = set()
    for L in _layers(pdf):
        on = L.print_on if (use_print and L.print_on is not None) else L.view_on
        if on:
            vis.add(L.key)
    return vis


def flatten_layers(data: bytes, visible: set | None = None) -> bytes:
    """Sichtbaren Zustand festschreiben: versteckte Ebeneninhalte entfernen, Ebenen auflösen.
    Danach druckt jeder Drucker/Viewer genau das, was sichtbar ist."""
    import pikepdf
    pdf = pikepdf.open(io.BytesIO(data))
    try:
        if _ocp(pdf) is None:
            raise ValueError(tr("Das Dokument hat keine Ebenen."))
        vis = current_visible(pdf) if visible is None else visible
        _apply_visibility(pdf, vis, strip=True)
        del pdf.Root["/OCProperties"]
        out = io.BytesIO()
        pdf.save(out)
        return out.getvalue()
    finally:
        pdf.close()


def remove_layers(data: bytes, keys: set) -> bytes:
    """Ebenen samt Inhalt entfernen; die übrigen Ebenen bleiben erhalten."""
    import pikepdf
    pdf = pikepdf.open(io.BytesIO(data))
    try:
        ocp = _ocp(pdf)
        if ocp is None:
            raise ValueError(tr("Das Dokument hat keine Ebenen."))
        all_keys = {_key(g) for g in ocp.OCGs}
        _apply_visibility(pdf, all_keys - set(keys), strip=False)

        def clean(arr):
            out = pikepdf.Array()
            for it in arr:
                if isinstance(it, pikepdf.Array):
                    sub = clean(it)
                    if len(sub):
                        out.append(sub)
                elif isinstance(it, pikepdf.Dictionary) and _key(it) in keys:
                    continue
                else:
                    out.append(it)
            return out
        ocp.OCGs = clean(ocp.OCGs)
        d = ocp.get("/D")
        if d is not None:
            for k in ("/ON", "/OFF", "/Order", "/Locked", "/RBGroups"):
                if k in d:
                    d[k] = clean(d[k])
        if not len(ocp.OCGs):
            del pdf.Root["/OCProperties"]
        out = io.BytesIO()
        pdf.save(out)
        return out.getvalue()
    finally:
        pdf.close()


def set_layer_states(data: bytes, states: dict) -> bytes:
    """states: {Schlüssel: (Ansicht an, Druck an)} -> Standard-Zustand im Dokument setzen (Ebenen bleiben)."""
    import pikepdf
    pdf = pikepdf.open(io.BytesIO(data))
    try:
        ocp = _ocp(pdf)
        if ocp is None:
            raise ValueError(tr("Das Dokument hat keine Ebenen."))
        d = ocp.get("/D")
        if d is None:
            d = ocp.D = pikepdf.Dictionary()
        on, off = pikepdf.Array(), pikepdf.Array()
        printers = []
        for g in ocp.OCGs:
            view, prn = states.get(_key(g), (True, True))
            (on if view else off).append(g)
            usage = g.get("/Usage")
            if usage is None:
                usage = g.Usage = pikepdf.Dictionary()
            usage.Print = pikepdf.Dictionary(PrintState=pikepdf.Name.ON if prn else pikepdf.Name.OFF)
            usage.View = pikepdf.Dictionary(ViewState=pikepdf.Name.ON if view else pikepdf.Name.OFF)
            printers.append(g)
        d.BaseState = pikepdf.Name.ON
        d.ON, d.OFF = on, off
        # Druck-Zustand automatisch anwenden (Viewer, die Usage auswerten)
        d.AS = pikepdf.Array([pikepdf.Dictionary(Event=pikepdf.Name.Print, Category=pikepdf.Array([pikepdf.Name.Print]),
                                                 OCGs=pikepdf.Array(printers)),
                              pikepdf.Dictionary(Event=pikepdf.Name.View, Category=pikepdf.Array([pikepdf.Name.View]),
                                                 OCGs=pikepdf.Array(printers))])
        out = io.BytesIO()
        pdf.save(out)
        return out.getvalue()
    finally:
        pdf.close()


# --------------------------------------------------------------------------- #
# Schriften
# --------------------------------------------------------------------------- #
def _norm(name: str) -> tuple[str, bool, bool]:
    """BaseFont -> (Familie normalisiert, fett, kursiv)."""
    n = name.split("+", 1)[-1]
    low = n.lower()
    bold = bool(re.search(r"bold|black|heavy|semibold|demi", low))
    italic = bool(re.search(r"italic|oblique|kursiv", low))
    fam = re.split(r"[,-]", n)[0]
    fam = re.sub(r"(PSMT|MT|PS)$", "", fam)
    fam = re.sub(r"(Bold|Italic|Oblique|Regular)+$", "", fam, flags=re.I)
    return re.sub(r"[^a-z0-9]", "", fam.lower()), bold, italic


def font_dirs() -> list[str]:
    home = os.path.expanduser("~")
    if _platform.IS_WIN:
        win = os.environ.get("WINDIR", r"C:\Windows")
        return [os.path.join(win, "Fonts"), os.path.join(os.environ.get("LOCALAPPDATA", home), "Microsoft", "Windows", "Fonts"),
                user_font_dir()]
    return ["/usr/share/fonts", "/usr/local/share/fonts", os.path.join(home, ".local", "share", "fonts"),
            os.path.join(home, ".fonts"), user_font_dir()]


def user_font_dir() -> str:
    if _platform.IS_WIN:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "Passermark", "fonts")
    return os.path.join(os.path.expanduser("~"), ".local", "share", "fonts", "passermark")


def _fc_match(family: str, bold: bool, italic: bool) -> str:
    fc = shutil.which("fc-match")
    if not fc:
        return ""
    style = ("Bold " if bold else "") + ("Italic" if italic else "")
    pat = family + (f":style={style.strip()}" if style.strip() else "")
    try:
        r = subprocess.run([fc, "-f", "%{family}|%{file}", pat], capture_output=True, text=True, timeout=10)
        fam, _, path = r.stdout.partition("|")
        if path and family.split()[0].lower() in fam.lower().replace(" ", ""):
            return path
        if path and family.lower() in fam.lower():
            return path
    except (OSError, subprocess.SubprocessError):
        pass
    return ""


def _scan_files(family: str, bold: bool, italic: bool) -> str:
    want = re.sub(r"[^a-z0-9]", "", family.lower())
    best, score_best = "", -1
    for d in font_dirs():
        if not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for fn in files:
                if not fn.lower().endswith((".ttf", ".otf")):
                    continue
                base = re.sub(r"[^a-z0-9]", "", fn.lower().rsplit(".", 1)[0])
                if not base.startswith(want):
                    continue
                rest = base[len(want):]
                b, i = "bold" in rest, ("italic" in rest or "oblique" in rest)
                score = (b == bold) * 2 + (i == italic) * 2 - len(rest) / 100
                if score > score_best:
                    best, score_best = os.path.join(root, fn), score
    return best


def find_font_file(family: str, bold=False, italic=False) -> str:
    return _fc_match(family, bold, italic) or _scan_files(family, bold, italic)


def suggest_font(name: str) -> tuple[str, str]:
    """(Pfad, Anzeigename) einer passenden Ersatzschrift – bevorzugt metrisch kompatibel."""
    fam, bold, italic = _norm(name)
    for pat, repl in METRIC:
        if re.search(pat, fam):
            p = find_font_file(repl, bold, italic)
            if p:
                return p, repl + (" Bold" if bold else "") + (" Italic" if italic else "")
    # gleichnamige Schrift im System?
    p = _scan_files(fam, bold, italic)
    if p:
        return p, os.path.basename(p)
    # CAD-Normschriften ohne osifont: schmale serifenlose Ausweichschrift (Breiten bleiben aus dem PDF)
    if re.search(r"isocp|isoct|romans|simplex|txt|cad|norm", fam):
        for fb in ("DejaVu Sans Condensed", "Liberation Sans Narrow", "DejaVu Sans"):
            p = find_font_file(fb, bold, italic)
            if p:
                return p, fb + tr(" (Ausweichschrift)")
    return "", ""


# Kommerzielle Schriften -> freier, metrisch gleicher Zwilling auf fontsource.org (gleiche Zeichenbreiten)
DOWNLOAD_ALIAS = [
    (r"arial|helvetica|arimo", "Arimo"),
    (r"timesnewroman|times|tinos", "Tinos"),
    (r"couriernew|courier|cousine", "Cousine"),
    (r"calibri|carlito", "Carlito"),
    (r"cambria|caladea", "Caladea"),
    (r"georgia|gelasio", "Gelasio"),
    (r"segoeui|tahoma|verdana", "Open Sans"),
]
FONTSOURCE = "https://api.fontsource.org/v1/fonts"


def free_alternative(name: str) -> str:
    """Freier, (meist metrisch kompatibler) Zwilling einer kommerziellen Schrift – oder ""."""
    fam = _norm(name)[0]
    for pat, alt in DOWNLOAD_ALIAS:
        if re.search(pat, fam):
            return alt
    return ""


def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Passermark"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def similar_fonts(family: str, n: int = 6) -> list[str]:
    """Ähnlich benannte freie Schriften auf fontsource.org (für „Meintest du …?“)."""
    import difflib
    try:
        lst = _get_json(FONTSOURCE)
    except Exception:
        return []
    fams = [f.get("family", "") for f in lst if isinstance(f, dict)]
    low = {f.lower(): f for f in fams}
    q = family.lower().strip()
    hits = [low[k] for k in difflib.get_close_matches(q, list(low), n=n, cutoff=0.6)]
    hits += [f for f in fams if q and q in f.lower() and f not in hits]
    return hits[:n]


class FontNotFound(RuntimeError):
    def __init__(self, family, suggestions):
        self.family, self.suggestions = family, suggestions
        msg = tr("Schrift „{0}“ gibt es auf fontsource.org nicht (dort liegen nur freie Schriften).").format(family)
        if suggestions:
            msg += "\n" + tr("Ähnliche freie Schriften: {0}").format(", ".join(suggestions))
        super().__init__(msg)


def download_font(family: str, progress=None) -> tuple[list[str], str]:
    """Freie Schrift (OFL/Apache) über fontsource.org laden -> (Dateipfade, tatsächlich geladene Familie).
    Kommerzielle Namen (Arial, Calibri …) werden auf ihren freien Zwilling umgeleitet."""
    used = free_alternative(family) or family.strip()
    fid = re.sub(r"[^a-z0-9]+", "-", used.lower()).strip("-")
    cdn = "https://cdn.jsdelivr.net/fontsource/fonts/{0}@latest/latin-{1}-{2}.ttf"
    try:
        meta = _get_json(f"{FONTSOURCE}/{fid}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise FontNotFound(used, similar_fonts(used))
        meta = None
        api_err = e
    except Exception as e:
        meta = None
        api_err = e
    if meta is None:
        # API nicht erreichbar: direkt vom fontsource-CDN (gleiche Dateien)
        meta = {"family": used, "variants": {w: {st: {"latin": {"url": {"ttf": cdn.format(fid, w, st)}}}
                                                 for st in ("normal", "italic")} for w in ("400", "700")}}
    variants = meta.get("variants") or {}
    out_dir = user_font_dir()
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for weight in ("400", "700"):
        for style in ("normal", "italic"):
            v = (variants.get(weight) or {}).get(style) or {}
            sub = v.get("latin") or (next(iter(v.values())) if v else None)
            if not sub:
                continue
            u = (sub.get("url") or {}).get("ttf")
            if not u:
                continue
            fn = f"{fid}-{weight}-{style}.ttf"
            dst = os.path.join(out_dir, fn)
            try:
                with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Passermark"}),
                                            timeout=30) as r:
                    data = r.read()
            except Exception:
                continue                      # Schnitt nicht vorhanden (z. B. keine Kursive)
            with open(dst, "wb") as f:
                f.write(data)
            paths.append(dst)
            if progress:
                progress(fn)
    if not paths:
        if "api_err" in locals():
            raise RuntimeError(tr("Kein Zugriff auf fontsource.org ({0}).").format(api_err))
        raise RuntimeError(tr("Für „{0}“ gibt es keine TTF-Dateien zum Herunterladen.").format(used))
    if shutil.which("fc-cache"):
        subprocess.run(["fc-cache", "-f", out_dir], capture_output=True, timeout=60)
    return paths, meta.get("family", used)


def _gs(args: list, src: bytes) -> bytes:
    gs = _platform.ghostscript()
    if not gs:
        raise RuntimeError(tr("Für diese Reparatur wird Ghostscript benötigt."))
    tmp = tempfile.mkdtemp(prefix="passermark-pf-")
    try:
        i, o = os.path.join(tmp, "in.pdf"), os.path.join(tmp, "out.pdf")
        with open(i, "wb") as f:
            f.write(src)
        cmd = [gs, "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=pdfwrite", "-dAutoRotatePages=/None",
               "-dDownsampleColorImages=false", "-dDownsampleGrayImages=false", "-dDownsampleMonoImages=false",
               *[a.replace("{TMP}", tmp) for a in args], "-o", o, i]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, **_platform.hidden_subprocess_kwargs())
        if r.returncode != 0 or not os.path.exists(o):
            raise RuntimeError(tr("Ghostscript-Fehler:\n") + (r.stderr or r.stdout or "")[-1500:])
        with open(o, "rb") as f:
            return f.read()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _ps_str(s: str) -> str:
    return "(" + s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ")"


def embed_fonts(data: bytes, mapping: dict) -> bytes:
    """Alle Schriften einbetten; fehlende über mapping {Schriftname: Pfad} ersetzen (Ghostscript-Fontmap)."""
    tmp = tempfile.mkdtemp(prefix="passermark-fm-")
    try:
        fm = os.path.join(tmp, "Fontmap")
        dirs = set()
        with open(fm, "w", encoding="utf-8") as f:
            for name, path in mapping.items():
                if path and os.path.exists(path):
                    f.write(f"/{name} {_ps_str(path)} ;\n")
                    dirs.add(os.path.dirname(path))
        permits = [f"--permit-file-read={d.rstrip(os.sep)}{os.sep}" for d in dirs | {tmp}]
        args = ["-dCompatibilityLevel=1.7", "-dEmbedAllFonts=true", "-dSubsetFonts=true",
                f"-sFONTMAP={fm}", *permits]
        if dirs:
            args.append("-sFONTPATH=" + os.pathsep.join(sorted(dirs)))
        return _gs(args, data)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def outline_text(data: bytes) -> bytes:
    """Text in Pfade umwandeln (sieht überall gleich aus, ist aber nicht mehr durchsuchbar)."""
    return _gs(["-dCompatibilityLevel=1.7", "-dNoOutputFonts"], data)


def flatten_transparency(data: bytes, dpi: int = 300) -> bytes:
    """Transparenzen reduzieren (PDF 1.3) – für ältere Drucker/RIPs. Transparente Bereiche werden gerastert."""
    return _gs(["-dCompatibilityLevel=1.3", f"-r{dpi}"], data)


# --------------------------------------------------------------------------- #
# Befunde
# --------------------------------------------------------------------------- #
def _issues(rep: Report) -> list[Issue]:
    out = []
    for f in rep.fonts:
        pg = sorted(f.pages)
        if f.status == "missing":
            if f.encoding == "private":
                out.append(Issue("error", "font", tr("Schrift „{0}“ ist nicht eingebettet und verwendet eigene Zeichennamen – "
                                                     "ohne die Originalschrift nicht reparierbar (Text fehlt oder wird "
                                                     "zu Fremdzeichen).").format(f.name), pg))
            elif f.cid and f.encoding.startswith("Identity"):
                out.append(Issue("error", "font", tr("Schrift „{0}“ ist nicht eingebettet (CID, Identity) – ohne die "
                                                     "Originalschrift nicht reparierbar.").format(f.name), pg))
            else:
                hint = tr(" Ersatz: {0}.").format(f.suggestion_name) if f.suggestion_name else tr(" Kein Ersatz gefunden.")
                out.append(Issue("error", "font", tr("Schrift „{0}“ ist nicht eingebettet – Darstellung kann abweichen.")
                                 .format(f.name) + hint, pg))
        elif f.status == "std14":
            out.append(Issue("info", "font", tr("Standardschrift „{0}“ nicht eingebettet (wird meist korrekt ersetzt).")
                             .format(f.name), pg))
        elif f.status == "type3":
            out.append(Issue("info", "font", tr("Type3-Schrift „{0}“ (oft aus CAD) – Text ggf. nicht durchsuchbar.")
                             .format(f.name), pg))
        if not f.tounicode and f.status != "std14" and f.encoding not in ("WinAnsiEncoding", "MacRomanEncoding",
                                                                            "StandardEncoding"):
            out.append(Issue("info", "font", tr("Schrift „{0}“ ohne Unicode-Zuordnung – Kopieren/Suchen kann falsche "
                                                "Zeichen liefern.").format(f.name), pg))
    for p, n in sorted(rep.garbled.items()):
        out.append(Issue("warning", "text", tr("Seite {0}: {1} Zeichen ohne gültige Zuordnung (seltsame Zeichen).")
                         .format(p, n), [p]))
    hidden = [L for L in rep.layers if not L.view_on or L.print_on is False]
    if hidden:
        out.append(Issue("warning", "layer", tr("{0} ausgeblendete Ebene(n) – viele Drucker/RIPs ignorieren das und "
                                                "drucken sie trotzdem. Empfehlung: „Sichtbaren Zustand festschreiben“.")
                         .format(len(hidden)), sorted(set().union(*[L.pages for L in hidden]))))
    for L in rep.layers:
        if L.print_on is not None and L.print_on != L.view_on:
            out.append(Issue("warning", "layer", tr("Ebene „{0}“: Ansicht {1}, Druck {2}.").format(
                L.name, tr("an") if L.view_on else tr("aus"), tr("an") if L.print_on else tr("aus")), sorted(L.pages)))
        if L.outside_pct is not None and L.outside_pct > 25:
            out.append(Issue("warning", "layer", tr("Ebene „{0}“: {1:.0f} % des Inhalts liegen außerhalb der Seite "
                                                    "(verrutscht?).").format(L.name, L.outside_pct), sorted(L.pages)))
    risky = {p for p, k in rep.transparency.items() if k & {"smask", "blend", "group"}}
    if risky:
        out.append(Issue("info", "transparency", tr("Transparenzen auf {0} Seite(n) – auf älteren Druckern/RIPs ggf. "
                                                    "„Transparenzen reduzieren“.").format(len(risky)), sorted(risky)))
    op = {p for p, k in rep.transparency.items() if "overprint" in k}
    if op:
        out.append(Issue("info", "transparency", tr("Überdrucken auf {0} Seite(n).").format(len(op)), sorted(op)))
    out.sort(key=lambda i: (SEV_ORDER[i.severity], i.category))
    return out


def report_text(rep: Report, title: str = "") -> str:
    """Bericht als Text (zum Speichern/Weitergeben)."""
    lines = [tr("Passermark – Prüfbericht") + (f": {title}" if title else ""), ""]
    c = rep.counts()
    lines.append(tr("{0} Fehler, {1} Warnung(en), {2} Hinweis(e) · {3} Seiten").format(
        c["error"], c["warning"], c["info"], rep.pages))
    lines.append("")
    sev = {"error": tr("FEHLER"), "warning": tr("WARNUNG"), "info": tr("HINWEIS")}
    for i in rep.issues:
        lines.append(f"[{sev[i.severity]}] {i.message}" + (tr("  (Seiten {0})").format(_pages_str(i.pages)) if i.pages else ""))
    lines += ["", tr("Schriften:")]
    for f in rep.fonts:
        st = {"ok": tr("eingebettet"), "std14": tr("Standard, nicht eingebettet"), "missing": tr("NICHT eingebettet"),
              "type3": "Type3"}[f.status]
        lines.append(f"  {f.name}  ·  {f.subtype}  ·  {st}" + (tr("  ·  Teilmenge") if f.subset else "")
                     + (f"  ·  → {f.suggestion_name}" if f.suggestion_name else ""))
    if rep.layers:
        lines += ["", tr("Ebenen:")]
        for L in rep.layers:
            lines.append(f"  {L.name}  ·  " + tr("Ansicht {0}, Druck {1}").format(
                tr("an") if L.view_on else tr("aus"),
                tr("wie Ansicht") if L.print_on is None else (tr("an") if L.print_on else tr("aus"))))
    return "\n".join(lines) + "\n"
