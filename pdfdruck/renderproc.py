# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Render server for the page view: its own process with its own pdfium (pdfium is not thread-safe).

The GUI never waits for a page to be rendered any more – a slow page (large photos as ZIP, CAD plans) only
delays its own picture. Started as  passermark-cli render-server  (Windows: console EXE, clean pipes).

Protocol (stdin/stdout, binary-safe):
  request   one JSON line:  {"op": "open", "id": 1, "doc": "w1", "path": "…pdf", "password": null}
                            {"op": "render", "id": 2, "doc": "w1", "page": 0, "scale": 2.0, "rotation": 0,
                             "crop": [left, bottom, right, top] | null, "proof": {…} | null}
                            (proof = Softproof der Ansicht, siehe proof.proofed_render)
                            {"op": "chars", "id": 4, "doc": "w1", "page": 0}      (Zeichenkästen, für den Cursor)
                            {"op": "call", "id": 5, "fn": "preflight", "args": {…}}  (siehe CALLS)
                            {"op": "close", "id": 3, "doc": "w1"}      {"op": "quit"}
  response  one JSON line:  {"id": 2, "ok": true, "w": …, "h": …, "stride": …, "fmt": "bgrx", "n": bytes}
            followed by exactly n bytes: pixel data (render), a pickle (fmt "pickle": open = page info,
            chars, call results) – n = 0 otherwise. Pickle only between our own two processes.

The same program runs twice: one process renders pages, a second one does the slow analysis (check,
verification after editing) – so neither blocks the other and the GUI never waits for either.
"""
from __future__ import annotations

import json
import os
import pickle
import sys
from collections import OrderedDict

KEEP_PAGES = 4          # offene Seiten je Dokument: pdfium behält dekodierte Bilder, solange die Seite offen ist


def page_info(data: bytes) -> list:
    """Je Seite die Rahmen wie pdfium sie sieht, ohne Seiten zu laden (pikepdf, nur Wörterbücher):
        {"crop": (x0, y0, x1, y1) = CropBox ∩ MediaBox, "rotate": 0..3, "trim": … | None, "bleed": … | None}.
        Werte werden wie bei pdfium über /Parent geerbt."""
    import io
    import pikepdf

    def attr(obj, key):
        seen = 0
        while obj is not None and seen < 64:
            if key in obj:
                return obj[key]
            obj = obj.get("/Parent")
            seen += 1
        return None

    def box(v):
        try:
            a = [float(x) for x in v]
            return (min(a[0], a[2]), min(a[1], a[3]), max(a[0], a[2]), max(a[1], a[3])) if len(a) == 4 else None
        except Exception:
            return None
    out = []
    with pikepdf.open(io.BytesIO(data)) as pdf:
        for pg in pdf.pages:
            o = pg.obj
            media = box(attr(o, "/MediaBox")) or (0.0, 0.0, 612.0, 792.0)
            crop = box(attr(o, "/CropBox"))
            if crop is None or crop[2] - crop[0] <= 0 or crop[3] - crop[1] <= 0:
                crop = media
            else:
                crop = (max(crop[0], media[0]), max(crop[1], media[1]), min(crop[2], media[2]), min(crop[3], media[3]))
                if crop[2] <= crop[0] or crop[3] <= crop[1]:
                    crop = media
            try:
                rot = int(attr(o, "/Rotate") or 0)
            except Exception:
                rot = 0
            trim, bleed = box(attr(o, "/TrimBox")), box(attr(o, "/BleedBox"))
            raw = {"trim_raw": trim, "art": box(attr(o, "/ArtBox"))}      # für die Statuszeile (wie page_trims)
            if trim is not None and all(abs(trim[k] - crop[k]) < 0.5 for k in range(4)):
                trim = None                              # Endformat = Seite: kein Anschnitt
            if trim is None:
                bleed = None
            out.append(dict(raw, crop=crop, rotate=(rot // 90) % 4, trim=trim, bleed=bleed))
    return out


def _call_preflight(path: str, deep_layers: bool = True):
    from . import preflight
    with open(path, "rb") as f:
        data = f.read()
    return preflight.analyze(data, deep_layers, pdfium_parts=True)


def _call_verify(before: str, after: str, page: int, boxes: list):
    from . import editing
    with open(before, "rb") as f:
        a = f.read()
    with open(after, "rb") as f:
        b = f.read()
    return editing.verify_edit(a, b, page, [tuple(x) for x in boxes])


def _call_edit(before: str, out: str, page: int, op: str, kwargs: dict, boxes: list):
    """Bearbeiten-Modus: Änderung + Sicherheitsprüfung; das Ergebnis landet in out (nur wenn übernommen)."""
    from . import editops
    with open(before, "rb") as f:
        data = f.read()
    res = editops.apply_and_verify(data, page, op, kwargs, boxes)
    new = res.pop("new", None)
    res["changed"] = new is not None
    if new is not None:
        with open(out, "wb") as f:
            f.write(new)
    return res


_SHEET_SRC: OrderedDict = OrderedDict()      # (Pfad, flach) -> (Stempel, Dokument) – Druckvorschau


def _sheet_source(path: str, flatten: bool):
    """Quelle der Druckvorschau, je Datei einmal geladen (und Formulare/Kommentare eingebrannt)."""
    import pypdfium2 as pdfium
    from . import layout
    st = os.stat(path)
    key, stamp = (path, bool(flatten)), (st.st_mtime_ns, st.st_size)
    hit = _SHEET_SRC.get(key)
    if hit is not None and hit[0] == stamp:
        _SHEET_SRC.move_to_end(key)
        return hit[1]
    if hit is not None:
        _close_quiet(*hit[1:])
    with open(path, "rb") as f:
        data = f.read()
    doc = pdfium.PdfDocument(data)
    flat = layout.flattened(doc) if flatten else doc
    _SHEET_SRC[key] = (stamp, flat, doc)
    while len(_SHEET_SRC) > 2:
        _, old = _SHEET_SRC.popitem(last=False)
        _close_quiet(*old[1:])
    return flat


def _close_quiet(*docs):
    seen = set()
    for d in docs:
        if d is not None and id(d) not in seen:
            seen.add(id(d))
            try:
                d.close()
            except Exception:
                pass


def _rgb(page, scale: float, rotation: int, proof_args=None):
    """Seite -> (Breite, Höhe, RGB-Bytes), optional mit Proof (Farbsimulation)."""
    bmp = page.render(scale=scale, rotation=rotation % 360, may_draw_forms=True, draw_annots=True)
    try:
        img = bmp.to_pil().convert("RGB")
    finally:
        bmp.close()
    if proof_args:
        from . import proof
        img = proof.apply(img, *proof_args).convert("RGB")
    return img.width, img.height, img.tobytes("raw", "RGB")


def _call_sheet(path: str, flatten: bool, mode: str, sheet, plans, settings, only=None, scale: float = 1.0,
                rotations=None, proof_args=None, plans1=None, plans2=None, sheet1=None, limit: int = 400):
    """Druckvorschau: Bogen montieren und rendern (wie die Ausgabe, nur im eigenen Prozess).
        mode "sheet": impose_with, only = Bogennummern (Vorder- und ggf. Rückseite)
        mode "step2": impose_step2 (Schritt 2), only = [Bogen]
        mode "overview": alle Bögen (bis limit) als kleine Bilder, scale gilt für alle.
        -> Liste von (Breite, Höhe, RGB-Bytes)."""
    from . import layout
    src = _sheet_source(path, flatten)
    sub = None
    if mode == "sheet" and plans:
        try:
            sub = _raster_source(src, plans, only if only is not None else range(min(len(plans), limit)), scale)
        except Exception:
            sub = None                                  # dann direkt (wie die Ausgabe)
        if sub is not None:
            src = sub
    if mode == "step2":
        out = layout.impose_step2(src, sheet1, plans1, settings, plans2=plans2, only=only)
    else:
        out = layout.impose_with(src, sheet, plans, settings, only=only)
    try:
        imgs = []
        n = min(len(out), limit)
        for k in range(n):
            pg = out[k]
            try:
                rot = rotations[k] if rotations and k < len(rotations) else 0
                imgs.append(_rgb(pg, scale, rot, proof_args))
            finally:
                pg.close()
        return imgs
    finally:
        out.close()
        if sub is not None:
            sub.close()


def _raster_source(src, plans, sheets, scale: float):
    """Nur für die Vorschau: kommt eine Seite mehrfach auf die Bögen (Nutzen, Step & Repeat), wird sie einmal
        in Vorschau-Auflösung gerendert und das Bild montiert – statt die Seite für jeden Nutzen neu zu
        zeichnen (große Fotos, CAD-Pläne: jeder Nutzen dekodierte alles neu). Die Montage selbst (Lage,
        Anschnitt, Spiegelung, Marken) bleibt genau dieselbe. None = nicht nötig (jede Seite nur einmal)."""
    import pypdfium2 as pdfium
    need: dict = {}
    count: dict = {}
    for idx in sheets:
        for pl in plans[idx].placements:
            need[pl.src] = max(need.get(pl.src, 0.0), float(pl.scale))
            count[pl.src] = count.get(pl.src, 0) + 1
    if not count or max(count.values()) < 2:
        return None
    sub = pdfium.PdfDocument.new()
    try:
        for i in range(len(src)):
            w, h = src.get_page_size(i)
            page = sub.new_page(w, h)
            try:
                if i in need:
                    k = min(scale * need[i] * 1.5, 4000 / max(w, h, 1.0))
                    sp = src[i]
                    try:
                        bmp = sp.render(scale=max(k, 0.05), may_draw_forms=False, draw_annots=False)
                    finally:
                        sp.close()
                    img = pdfium.PdfImage.new(sub)
                    img.set_bitmap(bmp)
                    img.set_matrix(pdfium.PdfMatrix(w, 0, 0, h, 0, 0))
                    page.insert_obj(img)
                    page.gen_content()
                    bmp.close()
            finally:
                page.close()
    except Exception:
        sub.close()
        raise
    return sub


def _call_sheet_release():
    """Druckdialog zu: geladene Vorschau-Quellen freigeben."""
    while _SHEET_SRC:
        _close_quiet(*_SHEET_SRC.popitem()[1][1:])


def _call_inspect(path: str, password: str | None = None):
    """Eigenschaften-Fenster: alle Dokumentangaben samt Prüfung (wie passermark-cli inspect --check)."""
    from . import docinfo
    return docinfo.inspect(path, password, check=True)


CALLS = {"inspect": _call_inspect, "preflight": _call_preflight, "verify": _call_verify, "edit": _call_edit,
         "sheet": _call_sheet, "sheet_release": _call_sheet_release}


def serve(inp, out) -> int:
    import pypdfium2 as pdfium
    docs: dict = {}
    paths: dict = {}                                        # Dokument -> (Pfad, Passwort) für den Softproof
    pages: OrderedDict = OrderedDict()

    def send(head: dict, payload: bytes = b""):
        head["n"] = len(payload)
        out.write(json.dumps(head).encode("utf-8") + b"\n")
        if payload:
            out.write(payload)
        out.flush()

    def close_doc(key):
        for k in [k for k in pages if k[0] == key]:
            try:
                pages.pop(k).close()
            except Exception:
                pass
        paths.pop(key, None)
        d = docs.pop(key, None)
        if d is not None:
            try:
                d.close()
            except Exception:
                pass

    def page_of(key, i):
        k = (key, i)
        if k in pages:
            pages.move_to_end(k)
            return pages[k]
        pg = docs[key][i]
        pages[k] = pg
        same = [x for x in pages if x[0] == key]
        while len(same) > KEEP_PAGES:
            old = same.pop(0)
            try:
                pages.pop(old).close()
            except Exception:
                pass
        return pg

    for line in inp:
        if not line.strip():
            continue
        try:
            req = json.loads(line)
        except ValueError:
            continue
        if req.get("n"):                                    # Argumente als Pickle hinter der Zeile
            raw = inp.read(int(req["n"]))
            try:
                req["args"] = pickle.loads(raw)
            except Exception:
                req["args"] = None
        op, rid, key = req.get("op"), req.get("id"), req.get("doc", "")
        if op == "quit":
            break
        try:
            if op == "open":
                close_doc(key)
                with open(req["path"], "rb") as f:         # in den Speicher: Datei bleibt frei (Windows:
                    data = f.read()                          # Speichern über die offene Datei, Zwischendatei löschen)
                docs[key] = pdfium.PdfDocument(data, password=req.get("password") or None)
                paths[key] = (req["path"], req.get("password") or None)
                try:
                    info = page_info(data)
                except Exception:
                    info = None                              # z. B. verschlüsselt: Ansicht nimmt pdfium
                send({"id": rid, "ok": True, "pages": len(docs[key]), "fmt": "pickle"}, pickle.dumps(info))
            elif op == "chars":
                pg = page_of(key, int(req["page"]))
                tp = pg.get_textpage()
                try:
                    n = tp.count_chars()
                    boxes = [tp.get_charbox(i) for i in range(n)] if n < 200000 else []
                finally:
                    tp.close()
                send({"id": rid, "ok": True, "fmt": "pickle"}, pickle.dumps(boxes))
            elif op == "lists":
                from . import editing
                page = int(req["page"])
                if req.get("kind") == "text":
                    res = editing.text_lines(docs[key], page, include_undecodable=True)
                else:
                    res = editing.limit_objects(editing.page_objects(docs[key], page))   # (Auswahl, Gesamtzahl)
                send({"id": rid, "ok": True, "fmt": "pickle"}, pickle.dumps(res))
            elif op == "call":
                result = CALLS[req["fn"]](**(req.get("args") or {}))
                send({"id": rid, "ok": True, "fmt": "pickle"}, pickle.dumps(result))
            elif op == "close":
                close_doc(key)
                send({"id": rid, "ok": True})
            elif op == "render":
                pg = page_of(key, int(req["page"]))
                crop = tuple(float(c) for c in req["crop"]) if req.get("crop") else (0, 0, 0, 0)
                if req.get("proof"):
                    from . import proof
                    path, pw = paths.get(key, (None, None))
                    img = proof.proofed_render(pg, float(req["scale"]), int(req.get("rotation", 0)), crop, req["proof"],
                                               path, int(req["page"]), pw)
                    send({"id": rid, "ok": True, "w": img.width, "h": img.height, "stride": img.width * 4,
                          "fmt": "bgrx"}, img.tobytes("raw", "BGRX"))
                    continue
                bmp = pg.render(scale=float(req["scale"]), rotation=int(req.get("rotation", 0)) % 360, crop=crop,
                                prefer_bgrx=True, may_draw_forms=True, draw_annots=True)
                try:
                    data = bytes(bmp.buffer)
                    send({"id": rid, "ok": True, "w": bmp.width, "h": bmp.height, "stride": bmp.stride,
                          "fmt": "bgrx" if bmp.n_channels == 4 else "bgr"}, data)
                finally:
                    bmp.close()
            else:
                send({"id": rid, "ok": False, "error": f"unknown op {op!r}"})
        except Exception as e:                       # Fehler zurückmelden, Server läuft weiter
            send({"id": rid, "ok": False, "error": f"{type(e).__name__}: {e}"})
    for key in list(docs):
        close_doc(key)
    return 0


def main() -> int:
    """Entry point (passermark-cli render-server). Stray prints must not end up in the binary stream:
        stdout is taken over for the protocol, everything else goes to stderr."""
    out = os.fdopen(os.dup(sys.stdout.fileno()), "wb")
    try:
        os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    except OSError:
        pass
    sys.stdout = sys.stderr
    try:
        return serve(sys.stdin.buffer, out)
    except (BrokenPipeError, KeyboardInterrupt):
        return 0
