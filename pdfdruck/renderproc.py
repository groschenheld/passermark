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
                            {"op": "close", "id": 3, "doc": "w1"}      {"op": "quit"}
  response  one JSON line:  {"id": 2, "ok": true, "w": …, "h": …, "stride": …, "fmt": "bgrx", "n": bytes}
            followed by exactly n bytes of pixel data (render only; n = 0 otherwise)
"""
from __future__ import annotations

import json
import os
import sys
from collections import OrderedDict

KEEP_PAGES = 4          # offene Seiten je Dokument: pdfium behält dekodierte Bilder, solange die Seite offen ist


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
        op, rid, key = req.get("op"), req.get("id"), req.get("doc", "")
        if op == "quit":
            break
        try:
            if op == "open":
                close_doc(key)
                with open(req["path"], "rb") as f:         # in den Speicher: Datei bleibt frei (Windows:
                    data = f.read()                          # Speichern über die offene Datei, Zwischendatei löschen)
                docs[key] = pdfium.PdfDocument(data, password=req.get("password") or None)
                send({"id": rid, "ok": True, "pages": len(docs[key])})
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
