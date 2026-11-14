# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Layers (optional content) of a PDF: list them, find content outside the page, switch them on and off, flatten or remove them."""

from __future__ import annotations

import io
from dataclasses import dataclass, field

from .l10n import tr
from .pdfutil import obj_key, page_resources


@dataclass
class LayerInfo:
    """A layer (optional content group) with its visibility on screen and in print."""

    key: str
    name: str
    view_on: bool
    print_on: bool | None  # None = no print setting of its own (follows the view)
    locked: bool = False
    pages: set = field(default_factory=set)
    outside_pct: float | None = None


# --------------------------------------------------------------------------- #
# layers
# --------------------------------------------------------------------------- #
def _ocp(pdf):
    return pdf.Root.get("/OCProperties")


def list_layers(pdf) -> list[LayerInfo]:
    """All layers of the document with their state on screen and in print and the pages they occur on."""
    import pikepdf

    ocp = _ocp(pdf)
    if ocp is None:
        return []
    d = ocp.get("/D") or pikepdf.Dictionary()
    base_on = d.get("/BaseState", pikepdf.Name.ON) != pikepdf.Name.OFF
    on = {obj_key(o) for o in d.get("/ON") or []}
    off = {obj_key(o) for o in d.get("/OFF") or []}
    locked = {obj_key(o) for o in d.get("/Locked") or []}
    out = {}
    for g in ocp.get("/OCGs") or []:
        k = obj_key(g)
        view = (k in on) or (base_on and k not in off)
        pr = None
        try:
            ps = g.Usage.Print.PrintState
            pr = ps == pikepdf.Name.ON
        except Exception:
            pass
        out[k] = LayerInfo(k, str(g.get("/Name", "?")), view, pr, k in locked)
    # pages per layer (BDC /OC in contents and XObjects with /OC)
    for i, page in enumerate(pdf.pages, start=1):
        res = page_resources(page)
        props = res.get("/Properties") or {}
        for kk in _oc_keys_in_stream(page, props, res, set()):
            if kk in out:
                out[kk].pages.add(i)
    return list(out.values())


def ocgs_of(oc) -> list:
    """The layers (OCGs) an /OC entry refers to – directly or through a membership dictionary (OCMD)."""
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
            for g in ocgs_of(oc):
                keys.add(obj_key(g))
        elif op == "Do" and xo is not None and operands:
            x = xo.get(operands[0])
            if x is None:
                continue
            if "/OC" in x:
                for g in ocgs_of(x.OC):
                    keys.add(obj_key(g))
            xk = obj_key(x)
            if x.get("/Subtype") == pikepdf.Name.Form and xk not in seen:
                seen.add(xk)
                xr = x.get("/Resources") or res
                keys |= _oc_keys_in_stream(x, xr.get("/Properties") or {}, xr, seen)
    return keys


def layers_outside(data: bytes, layers: list[LayerInfo], max_layers=40, max_pages=6):
    """Per layer: how much of its content lies outside the page? (Rendered individually, page enlarged.)"""
    import pikepdf
    import pypdfium2 as pdfium

    for L in layers[:max_layers]:
        if not L.pages:
            continue
        pdf = pikepdf.open(io.BytesIO(data))
        try:
            ocp = _ocp(pdf)
            target = [g for g in ocp.OCGs if obj_key(g) == L.key]
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
        groups = [obj_key(g) for g in ocgs_of(oc)]
        if not groups:
            return True
        states = [g in visible for g in groups]
        pol = str(oc.get("/P", "/AnyOn"))
        return {"/AllOn": all(states), "/AnyOff": not all(states), "/AllOff": not any(states)}.get(pol, any(states))
    return obj_key(oc) in visible


def _rewrite(pdf, obj, props, res, visible, strip, done):
    """Filter a content stream: remove invisible OC content; with strip also remove the OC markers."""
    import pikepdf

    ok = obj_key(obj)
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
        res = page_resources(page)
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
    """Visible layers: for printing (print setting, otherwise view) or for the view."""
    vis = set()
    for L in list_layers(pdf):
        on = L.print_on if (use_print and L.print_on is not None) else L.view_on
        if on:
            vis.add(L.key)
    return vis


def has_layers(data: bytes) -> bool:
    """Whether the PDF defines layers (optional content)."""
    import pikepdf

    with pikepdf.open(io.BytesIO(data)) as pdf:
        return _ocp(pdf) is not None


def flatten_layers(data: bytes, visible: set | None = None) -> bytes:
    """Pin the visible state: remove hidden layer content, dissolve the layers.
    Afterwards every printer/viewer prints exactly what is visible.
    """
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
    """Remove layers including their content; the remaining layers are preserved."""
    import pikepdf

    pdf = pikepdf.open(io.BytesIO(data))
    try:
        ocp = _ocp(pdf)
        if ocp is None:
            raise ValueError(tr("Das Dokument hat keine Ebenen."))
        all_keys = {obj_key(g) for g in ocp.OCGs}
        _apply_visibility(pdf, all_keys - set(keys), strip=False)

        def clean(arr):
            out = pikepdf.Array()
            for it in arr:
                if isinstance(it, pikepdf.Array):
                    sub = clean(it)
                    if len(sub):
                        out.append(sub)
                elif isinstance(it, pikepdf.Dictionary) and obj_key(it) in keys:
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
    """states: {key: (view on, print on)} -> set the default state in the document (layers stay)."""
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
            view, prn = states.get(obj_key(g), (True, True))
            (on if view else off).append(g)
            usage = g.get("/Usage")
            if usage is None:
                usage = g.Usage = pikepdf.Dictionary()
            usage.Print = pikepdf.Dictionary(PrintState=pikepdf.Name.ON if prn else pikepdf.Name.OFF)
            usage.View = pikepdf.Dictionary(ViewState=pikepdf.Name.ON if view else pikepdf.Name.OFF)
            printers.append(g)
        d.BaseState = pikepdf.Name.ON
        d.ON, d.OFF = on, off
        # apply the print state automatically (viewers that evaluate Usage)
        d.AS = pikepdf.Array(
            [
                pikepdf.Dictionary(
                    Event=pikepdf.Name.Print, Category=pikepdf.Array([pikepdf.Name.Print]), OCGs=pikepdf.Array(printers)
                ),
                pikepdf.Dictionary(
                    Event=pikepdf.Name.View, Category=pikepdf.Array([pikepdf.Name.View]), OCGs=pikepdf.Array(printers)
                ),
            ]
        )
        out = io.BytesIO()
        pdf.save(out)
        return out.getvalue()
    finally:
        pdf.close()
