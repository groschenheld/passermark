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
                             "crop": [left, bottom, right, top] | null}
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


CALLS = {"preflight": _call_preflight, "verify": _call_verify, "edit": _call_edit}


def serve(inp, out) -> int:
    import pypdfium2 as pdfium
    docs: dict = {}
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
