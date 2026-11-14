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
import logging
import os
import pickle
import sys
from collections import OrderedDict

log = logging.getLogger(__name__)

KEEP_PAGES = 4  # open pages per document: pdfium keeps decoded images as long as the page is open


def page_info(data: bytes) -> list:
    """Per page the boxes as pdfium sees them, without loading pages (pikepdf, dictionaries only):
    {"crop": (x0, y0, x1, y1) = CropBox ∩ MediaBox, "rotate": 0..3, "trim": … | None, "bleed": … | None}.
    Values are inherited via /Parent as in pdfium.
    """
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
        except Exception:  # noqa: BLE001 – malformed PDF object: skipped or default value
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
            except Exception:  # noqa: BLE001 – malformed PDF object: skipped or default value
                rot = 0
            trim, bleed = box(attr(o, "/TrimBox")), box(attr(o, "/BleedBox"))
            raw = {"trim_raw": trim, "art": box(attr(o, "/ArtBox"))}  # for the status line (like page_trims)
            if trim is not None and all(abs(trim[k] - crop[k]) < 0.5 for k in range(4)):
                trim = None  # trim size = page: no bleed
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
    """Edit mode: change + safety check; the result ends up in out (only if accepted)."""
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


_SHEET_SRC: OrderedDict = OrderedDict()  # (path, flat) -> (stamp, document) – print preview


def _sheet_source(path: str, flatten: bool):
    """Source of the print preview, loaded once per file (with forms/comments flattened)."""
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
            except Exception:  # noqa: BLE001 – cleanup
                pass


def _rgb(page, scale: float, rotation: int, proof_args=None):
    """Page -> (width, height, RGB bytes), optionally with proof (colour simulation)."""
    bmp = page.render(scale=scale, rotation=rotation % 360, may_draw_forms=True, draw_annots=True)
    try:
        img = bmp.to_pil().convert("RGB")
    finally:
        bmp.close()
    if proof_args:
        from . import proof

        img = proof.apply(img, *proof_args).convert("RGB")
    return img.width, img.height, img.tobytes("raw", "RGB")


def _call_sheet(
    path: str,
    flatten: bool,
    mode: str,
    sheet,
    plans,
    settings,
    only=None,
    scale: float = 1.0,
    rotations=None,
    proof_args=None,
    plans1=None,
    plans2=None,
    sheet1=None,
    limit: int = 400,
):
    """Print preview: impose and render a sheet (like the output, only in its own process).
    mode "sheet": impose_with, only = sheet numbers (front and, if any, back)
    mode "step2": impose_step2 (step 2), only = [sheet]
    mode "overview": all sheets (up to limit) as small images, scale applies to all.
    -> list of (width, height, RGB bytes).
    """
    from . import layout

    src = _sheet_source(path, flatten)
    sub = None
    if mode == "sheet" and plans:
        try:
            sub = _raster_source(src, plans, only if only is not None else range(min(len(plans), limit)), scale)
        except Exception:  # noqa: BLE001 – fallback: render directly (like the output)
            sub = None  # then directly (like the output)
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
    """Preview only: if a page appears several times on the sheets (step and repeat), it is rendered once
    at preview resolution and the image is imposed – instead of drawing the page anew for every
    copy (large photos, CAD plans: every copy decoded everything again). The imposition itself (position,
    bleed, mirroring, marks) stays exactly the same. None = not needed (every page only once).
    """
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
    """Print dialog closed: release the loaded preview sources."""
    while _SHEET_SRC:
        _close_quiet(*_SHEET_SRC.popitem()[1][1:])


def _call_inspect(path: str, password: str | None = None):
    """Properties window: all document details incl. the check (like passermark-cli inspect --check)."""
    from . import docinfo

    return docinfo.inspect(path, password, check=True)


CALLS = {
    "inspect": _call_inspect,
    "preflight": _call_preflight,
    "verify": _call_verify,
    "edit": _call_edit,
    "sheet": _call_sheet,
    "sheet_release": _call_sheet_release,
}


class _Server:
    """State of the render process: the open documents, a few loaded pages per document, and the answer channel."""

    def __init__(self, out):
        self.out = out
        self.docs: dict = {}
        self.paths: dict = {}  # document -> (path, password) for the soft proof
        self.pages: OrderedDict = OrderedDict()
        self.ops = {
            "open": self.op_open,
            "chars": self.op_chars,
            "lists": self.op_lists,
            "call": self.op_call,
            "close": self.op_close,
            "render": self.op_render,
        }

    def send(self, head: dict, payload: bytes = b""):
        """Write one answer: a JSON line, then the payload of head["n"] bytes."""
        head["n"] = len(payload)
        self.out.write(json.dumps(head).encode("utf-8") + b"\n")
        if payload:
            self.out.write(payload)
        self.out.flush()

    def close_doc(self, key):
        """Close a document and its loaded pages."""
        for k in [k for k in self.pages if k[0] == key]:
            try:
                self.pages.pop(k).close()
            except Exception:  # noqa: BLE001 – cleanup
                pass
        self.paths.pop(key, None)
        d = self.docs.pop(key, None)
        if d is not None:
            try:
                d.close()
            except Exception:  # noqa: BLE001 – cleanup
                pass

    def close_all(self):
        """Close every document (end of the process)."""
        for key in list(self.docs):
            self.close_doc(key)

    def page_of(self, key, i):
        """Page i of a document; the last KEEP_PAGES pages per document stay loaded."""
        k = (key, i)
        if k in self.pages:
            self.pages.move_to_end(k)
            return self.pages[k]
        pg = self.docs[key][i]
        self.pages[k] = pg
        same = [x for x in self.pages if x[0] == key]
        while len(same) > KEEP_PAGES:
            old = same.pop(0)
            try:
                self.pages.pop(old).close()
            except Exception:  # noqa: BLE001 – cleanup
                pass
        return pg

    def handle(self, req: dict):
        """Answer one request; an error is reported to the caller, the server keeps running."""
        op, rid = req.get("op"), req.get("id")
        try:
            fn = self.ops.get(op)
            if fn is None:
                self.send({"id": rid, "ok": False, "error": f"unknown op {op!r}"})
            else:
                fn(req, rid, req.get("doc", ""))
        except Exception as e:  # noqa: BLE001 – report the error, the server keeps running
            self.send({"id": rid, "ok": False, "error": f"{type(e).__name__}: {e}"})

    def op_open(self, req, rid, key):
        """Open a document (replacing one with the same key) and answer with its page geometry."""
        import pypdfium2 as pdfium

        self.close_doc(key)
        with open(req["path"], "rb") as f:  # into memory: the file stays free (Windows:
            data = f.read()  # save via the open file, delete the intermediate file)
        self.docs[key] = pdfium.PdfDocument(data, password=req.get("password") or None)
        self.paths[key] = (req["path"], req.get("password") or None)
        try:
            info = page_info(data)
        except Exception:  # noqa: BLE001 – e.g. encrypted: the view uses pdfium
            info = None  # e.g. encrypted: the view uses pdfium
        self.send({"id": rid, "ok": True, "pages": len(self.docs[key]), "fmt": "pickle"}, pickle.dumps(info))

    def op_chars(self, req, rid, key):
        """Boxes of all characters of a page (for selecting text)."""
        pg = self.page_of(key, int(req["page"]))
        tp = pg.get_textpage()
        try:
            n = tp.count_chars()
            boxes = [tp.get_charbox(i) for i in range(n)] if n < 200000 else []
        finally:
            tp.close()
        self.send({"id": rid, "ok": True, "fmt": "pickle"}, pickle.dumps(boxes))

    def op_lists(self, req, rid, key):
        """Text lines or objects of a page for the edit panel."""
        from . import editing

        page = int(req["page"])
        if req.get("kind") == "text":
            res = editing.text_lines(self.docs[key], page, include_undecodable=True)
        else:
            res = editing.limit_objects(editing.page_objects(self.docs[key], page))  # (selection, total)
        self.send({"id": rid, "ok": True, "fmt": "pickle"}, pickle.dumps(res))

    def op_call(self, req, rid, key):
        """Run one of the functions in CALLS with the given arguments."""
        result = CALLS[req["fn"]](**(req.get("args") or {}))
        self.send({"id": rid, "ok": True, "fmt": "pickle"}, pickle.dumps(result))

    def op_close(self, req, rid, key):
        """Close a document."""
        self.close_doc(key)
        self.send({"id": rid, "ok": True})

    def op_render(self, req, rid, key):
        """Render a page (or a part of it) as raw pixels, on request as a soft proof."""
        pg = self.page_of(key, int(req["page"]))
        crop = tuple(float(c) for c in req["crop"]) if req.get("crop") else (0, 0, 0, 0)
        if req.get("proof"):
            from . import proof

            path, pw = self.paths.get(key, (None, None))
            img = proof.proofed_render(
                pg,
                float(req["scale"]),
                int(req.get("rotation", 0)),
                crop,
                req["proof"],
                path,
                int(req["page"]),
                pw,
            )
            self.send(
                {"id": rid, "ok": True, "w": img.width, "h": img.height, "stride": img.width * 4, "fmt": "bgrx"},
                img.convert("RGBA").tobytes("raw", "BGRA"),
            )
            return
        bmp = pg.render(
            scale=float(req["scale"]),
            rotation=int(req.get("rotation", 0)) % 360,
            crop=crop,
            prefer_bgrx=True,
            may_draw_forms=True,
            draw_annots=True,
        )
        try:
            data = bytes(bmp.buffer)
            self.send(
                {
                    "id": rid,
                    "ok": True,
                    "w": bmp.width,
                    "h": bmp.height,
                    "stride": bmp.stride,
                    "fmt": "bgrx" if bmp.n_channels == 4 else "bgr",
                },
                data,
            )
        finally:
            bmp.close()


def serve(inp, out) -> int:
    """Main loop of the render process: read requests from ``inp``, write answers to ``out``."""
    server = _Server(out)
    for line in inp:
        if not line.strip():
            continue
        try:
            req = json.loads(line)
        except ValueError:
            continue
        if req.get("n"):  # arguments as a pickle after the line
            raw = inp.read(int(req["n"]))
            try:
                req["args"] = pickle.loads(raw)
            except Exception:
                log.warning("Argumente nicht lesbar", exc_info=True)
                req["args"] = None
        if req.get("op") == "quit":
            break
        server.handle(req)
    server.close_all()
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
    handler = logging.StreamHandler(sys.stderr)  # the GUI reads stderr when this process ends unexpectedly
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)s: %(message)s"))
    logging.getLogger("pdfdruck").addHandler(handler)
    try:
        return serve(sys.stdin.buffer, out)
    except (BrokenPipeError, KeyboardInterrupt):
        return 0
