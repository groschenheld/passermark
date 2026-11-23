# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Overprint: find risky overprint settings in the content streams and correct them.

Findings (per page, with the area in page coordinates):
  white       a white object (CMYK 0/0/0/0, grey 100 %, RGB white) is set to overprint – on the press or a RIP
              with overprint it disappears
  black_text  small text in pure black (CMYK 0/0/0/K, K ≥ 95 %) knocks out – the slightest misregistration
              shows white edges ("Blitzer")
Correction: around exactly those objects an ExtGState switches overprint off (white) or on with overprint
mode 1 (black text) and restores the previous state afterwards. Everything else stays as it is.
Only pikepdf – no pdfium, no Ghostscript (safe in background threads).
"""

from __future__ import annotations

import io
import logging
import math

from .l10n import tr
from .pdfutil import obj_key, page_resources

log = logging.getLogger(__name__)

EPS = 0.002  # tolerance for "0 %" / "100 %"
BLACK_MIN_K = 0.95
TEXT_MAX_PT = 12.0
MAX_DEPTH = 8
MAX_OPS = 400_000  # per page (incl. forms) – beyond that: stop, result marked as truncated

PATH_CONSTR = {"m", "l", "c", "v", "y", "h", "re"}
PATH_PAINT = {"S", "s", "f", "F", "f*", "B", "B*", "b", "b*"}
FILL_PAINT = {"f", "F", "f*", "B", "B*", "b", "b*"}
STROKE_PAINT = {"S", "s", "B", "B*", "b", "b*"}
SHOW = {"Tj", "TJ", "'", '"'}
TEXT_FILL_MODES = {0, 2, 4, 6}
TEXT_STROKE_MODES = {1, 2, 5, 6}

_CMYK = {"space": "CMYK", "n": 4}
_GRAY = {"space": "Gray", "n": 1}
_RGB = {"space": "RGB", "n": 3}


def _mul(a, b):
    """PDF matrix product a × b (a applied first)."""
    return (
        a[0] * b[0] + a[1] * b[2],
        a[0] * b[1] + a[1] * b[3],
        a[2] * b[0] + a[3] * b[2],
        a[2] * b[1] + a[3] * b[3],
        a[4] * b[0] + a[5] * b[2] + b[4],
        a[4] * b[1] + a[5] * b[3] + b[5],
    )


def _pt(m, x, y):
    return (m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5])


def _nums(ops) -> list:
    out = []
    for v in ops:
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            pass
    return out


def is_white(color) -> bool:
    """(space dict, values) is paper white (no ink)?"""
    sp, vals = color
    s = sp.get("space")
    if not vals:
        return False
    if s == "CMYK":
        return len(vals) >= 4 and all(v <= EPS for v in vals[:4])
    if s == "Gray":
        return vals[0] >= 1 - EPS
    if s == "RGB":
        return len(vals) >= 3 and all(v >= 1 - EPS for v in vals[:3])
    return False


def is_pure_black(color) -> bool:
    """Pure black in CMYK (C = M = Y = 0, K ≥ BLACK_MIN_K)?"""
    sp, vals = color
    return sp.get("space") == "CMYK" and len(vals) >= 4 and all(v <= EPS for v in vals[:3]) and vals[3] >= BLACK_MIN_K


class _State:
    __slots__ = ("ctm", "fill", "stroke", "OP", "op", "OPM", "mode", "font_size")

    def __init__(self):
        self.ctm = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
        self.fill = (_GRAY, [0.0])
        self.stroke = (_GRAY, [0.0])
        self.OP = False
        self.op = False
        self.OPM = 0
        self.mode = 0
        self.font_size = 0.0

    def copy(self):
        """Independent copy (for q and forms)."""
        s = _State()
        for k in self.__slots__:
            setattr(s, k, getattr(self, k))
        return s


class _Edit:
    """Planned insertions in one content stream: index -> [(before|after, (OP, op, OPM))]."""

    def __init__(self, owner, res, ins, is_page):
        self.owner, self.res, self.ins, self.is_page = owner, res, ins, is_page
        self.before: dict = {}
        self.after: dict = {}


class _Scan:
    def __init__(self, pdf, text_max_pt: float, plan: bool, want: set):
        self.pdf = pdf
        self.text_max_pt = text_max_pt
        self.plan = plan  # collect insertions for the correction
        self.want = want  # {"white", "black_text"}
        self.found: dict = {"white": {}, "black_text": {}}
        self.counts: dict = {"white": 0, "black_text": 0}
        self.edits: list = []
        self.done_forms: set = set()
        self.truncated = False
        self.ops = 0

    # ------------------------------------------------------------------ #
    def page(self, page, pno: int):
        """Scan one page (1-based pno) with its forms."""
        import pikepdf

        self.ops = 0
        res = page_resources(page)
        if self.plan and not _has_resources(page):
            page.obj.Resources = pikepdf.Dictionary()
            res = page.obj.Resources
        try:
            ins = list(pikepdf.parse_content_stream(page))
        except Exception:  # noqa: BLE001 – damaged content: skip the page
            log.warning("Überdrucken: Seite %s nicht lesbar", pno, exc_info=True)
            return
        edit = _Edit(page, res, ins, True) if self.plan else None
        self._run(ins, res, _State(), pno, 0, edit)
        if edit is not None and (edit.before or edit.after):
            self.edits.append(edit)

    def _hit(self, kind, pno, box, edit, index_before, index_after, new_state, old_state):
        self.found[kind].setdefault(pno, []).append(box)
        self.counts[kind] += 1
        if edit is not None and kind in self.want:
            prev = edit.before.get(index_before)
            if prev is not None:  # e.g. fill and stroke of the same path: combine
                new_state = _merge(prev, new_state, old_state)
            edit.before[index_before] = new_state
            edit.after[index_after] = old_state

    def _run(self, ins, res, st: _State, pno: int, depth: int, edit):
        stack = []
        path_start, pts = None, []
        tm = tlm = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
        leading = 0.0
        for idx, item in enumerate(ins):
            self.ops += 1
            if self.ops > MAX_OPS:
                self.truncated = True
                return
            op = str(getattr(item, "operator", ""))
            ops = list(getattr(item, "operands", []) or [])
            try:
                if op == "q":
                    stack.append(st.copy())
                elif op == "Q":
                    if stack:
                        st = stack.pop()
                elif op == "cm" and len(ops) == 6:
                    st.ctm = _mul(tuple(float(v) for v in ops), st.ctm)
                elif op == "gs" and ops:
                    self._gs(st, res, ops[0])
                elif op in ("g", "G", "rg", "RG", "k", "K", "cs", "CS", "sc", "scn", "SC", "SCN"):
                    self._color(st, res, op, ops)
                elif op == "Tr" and ops:
                    st.mode = int(ops[0])
                elif op == "Tf" and len(ops) >= 2:
                    st.font_size = abs(float(ops[1]))
                elif op == "TL" and ops:
                    leading = float(ops[0])
                elif op == "BT":
                    tm = tlm = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
                elif op == "Tm" and len(ops) == 6:
                    tm = tlm = tuple(float(v) for v in ops)
                elif op in ("Td", "TD") and len(ops) == 2:
                    tx, ty = float(ops[0]), float(ops[1])
                    if op == "TD":
                        leading = -ty
                    tm = tlm = _mul((1, 0, 0, 1, tx, ty), tlm)
                elif op in ("T*", "'", '"'):
                    tm = tlm = _mul((1, 0, 0, 1, 0, -leading), tlm)
            except (TypeError, ValueError, IndexError, KeyError):
                pass
            if op in PATH_CONSTR:
                if path_start is None:
                    path_start, pts = idx, []
                self._path_points(st, op, ops, pts)
            elif op in PATH_PAINT:
                if path_start is not None:
                    self._paint(st, op, pts, pno, edit, path_start, idx)
                path_start, pts = None, []
            elif op == "n":
                path_start, pts = None, []
            elif op in SHOW:
                self._show(st, item, tm, pno, edit, idx)
            elif op == "Do" and ops and depth < MAX_DEPTH:
                self._form(st, res, ops[0], pno, depth)

    # ------------------------------------------------------------------ #
    def _gs(self, st, res, name):
        try:
            g = res.ExtGState[name]
        except (AttributeError, KeyError, TypeError):
            return
        if "/OP" in g:
            st.OP = bool(g.OP)
            if "/op" not in g:
                st.op = st.OP
        if "/op" in g:
            st.op = bool(g.op)
        if "/OPM" in g:
            try:
                st.OPM = int(g.OPM)
            except (TypeError, ValueError):
                pass

    def _color(self, st, res, op, ops):
        from .pipette import _initial, _space

        if op in ("g", "G"):
            c = (_GRAY, [float(ops[0])])
        elif op in ("rg", "RG"):
            c = (_RGB, [float(v) for v in ops[:3]])
        elif op in ("k", "K"):
            c = (_CMYK, [float(v) for v in ops[:4]])
        elif op in ("cs", "CS"):
            sp = _space(ops[0], res)
            c = (sp, _initial(sp))
        else:
            cur = st.fill if op in ("sc", "scn") else st.stroke
            c = (cur[0], _nums(ops) or cur[1])
        if op in ("g", "rg", "k", "cs", "sc", "scn"):
            st.fill = c
        else:
            st.stroke = c

    def _path_points(self, st, op, ops, pts):
        try:
            n = [float(v) for v in ops]
        except (TypeError, ValueError):
            return
        if op == "re" and len(n) == 4:
            x, y, w, h = n
            for px, py in ((x, y), (x + w, y), (x, y + h), (x + w, y + h)):
                pts.append(_pt(st.ctm, px, py))
        else:
            for i in range(0, len(n) - 1, 2):
                pts.append(_pt(st.ctm, n[i], n[i + 1]))

    def _paint(self, st, op, pts, pno, edit, start, end):
        if not pts:
            return
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        box = (min(xs), min(ys), max(xs), max(ys))
        old = (st.OP, st.op, st.OPM)
        off_fill = op in FILL_PAINT and st.op and is_white(st.fill)
        off_stroke = op in STROKE_PAINT and st.OP and is_white(st.stroke)
        if off_fill or off_stroke:
            new = (False if off_stroke else st.OP, False if off_fill else st.op, st.OPM)
            self._hit("white", pno, box, edit, start, end, new, old)

    def _show(self, st, item, tm, pno, edit, idx):
        import pikepdf

        if not _nonempty(item):
            return
        trm = _mul(tm, st.ctm)
        scale = math.sqrt(abs(trm[0] * trm[3] - trm[1] * trm[2])) or 1.0
        size = st.font_size * scale
        nbytes = 0
        for v in getattr(item, "operands", []) or []:
            if isinstance(v, pikepdf.String):
                nbytes += len(bytes(v))
            elif isinstance(v, pikepdf.Array):
                nbytes += sum(len(bytes(e)) for e in v if isinstance(e, pikepdf.String))
        w = max(1, nbytes) * 0.5 * st.font_size
        h = st.font_size
        corners = [_pt(trm, x, y) for x, y in ((0, -0.2 * h), (w, -0.2 * h), (0, 0.8 * h), (w, 0.8 * h))]
        box = (
            min(c[0] for c in corners),
            min(c[1] for c in corners),
            max(c[0] for c in corners),
            max(c[1] for c in corners),
        )
        old = (st.OP, st.op, st.OPM)
        fills = st.mode in TEXT_FILL_MODES
        strokes = st.mode in TEXT_STROKE_MODES
        off_fill = fills and st.op and is_white(st.fill)
        off_stroke = strokes and st.OP and is_white(st.stroke)
        if off_fill or off_stroke:
            new = (False if off_stroke else st.OP, False if off_fill else st.op, st.OPM)
            self._hit("white", pno, box, edit, idx, idx, new, old)
            return
        if fills and is_pure_black(st.fill) and 0 < size <= self.text_max_pt + 1e-6 and not (st.op and st.OPM == 1):
            self._hit("black_text", pno, box, edit, idx, idx, (st.OP, True, 1), old)

    def _form(self, st, res, name, pno, depth):
        import pikepdf

        try:
            xo = res.XObject[name]
        except (AttributeError, KeyError, TypeError):
            return
        if not isinstance(xo, pikepdf.Stream) or xo.get("/Subtype") != pikepdf.Name.Form:
            return
        key = obj_key(xo)
        fres = xo.get("/Resources")
        fres = fres if fres is not None else res
        sub = st.copy()
        m = xo.get("/Matrix")
        if m is not None and len(m) == 6:
            try:
                sub.ctm = _mul(tuple(float(v) for v in m), sub.ctm)
            except (TypeError, ValueError):
                pass
        try:
            ins = list(pikepdf.parse_content_stream(xo))
        except Exception:  # noqa: BLE001 – damaged form: skip
            return
        edit = None
        if self.plan and key not in self.done_forms:  # a form is corrected once (first use decides)
            self.done_forms.add(key)
            edit = _Edit(xo, fres, ins, False)
        self._run(ins, fres, sub, pno, depth + 1, edit)
        if edit is not None and (edit.before or edit.after):
            self.edits.append(edit)


def _has_resources(page) -> bool:
    node = page.obj
    while node is not None:
        if "/Resources" in node:
            return True
        node = node.get("/Parent")
    return False


def _merge(a, b, old):
    """Two planned states for the same position: take every deviation from the old state."""
    return tuple(bv if bv != ov else av for av, bv, ov in zip(a, b, old, strict=True))


def _nonempty(item) -> bool:
    import pikepdf

    for v in getattr(item, "operands", []) or []:
        if isinstance(v, pikepdf.String) and len(bytes(v)):
            return True
        if isinstance(v, pikepdf.Array) and any(isinstance(e, pikepdf.String) and len(bytes(e)) for e in v):
            return True
    return False


# --------------------------------------------------------------------------- #
# public interface
# --------------------------------------------------------------------------- #
def scan(pdf, max_pages: int = 300, text_max_pt: float = TEXT_MAX_PT) -> dict:
    """Findings of an open pikepdf document:
    {"white": {page: [box]}, "black_text": {page: [box]}, "counts": {kind: n}, "truncated": bool}.
    Pages are 1-based, boxes (x0, y0, x1, y1) in pt in page coordinates.
    """
    sc = _Scan(pdf, text_max_pt, plan=False, want={"white", "black_text"})
    for i, page in enumerate(pdf.pages, start=1):
        if i > max_pages:
            sc.truncated = True
            break
        sc.page(page, i)
    return {
        "white": sc.found["white"],
        "black_text": sc.found["black_text"],
        "counts": dict(sc.counts),
        "truncated": sc.truncated or len(pdf.pages) > max_pages,
    }


def scan_bytes(data: bytes, max_pages: int = 300, text_max_pt: float = TEXT_MAX_PT) -> dict:
    """Like scan(), for PDF bytes."""
    import pikepdf

    with pikepdf.open(io.BytesIO(data)) as pdf:
        return scan(pdf, max_pages, text_max_pt)


def _gs_name(res, state, cache) -> str:
    import pikepdf

    OP, op, OPM = state
    name = f"/PMop{int(OP)}{int(op)}{int(OPM)}"
    key = (id(res), name)
    if key in cache:
        return name
    if "/ExtGState" not in res:
        res.ExtGState = pikepdf.Dictionary()
    egs = res.ExtGState
    if name not in egs:
        egs[name] = pikepdf.Dictionary(Type=pikepdf.Name.ExtGState, OP=bool(OP), op=bool(op), OPM=int(OPM))
    cache.add(key)
    return name


def _gs_op(res, state, cache):
    import pikepdf

    return pikepdf.ContentStreamInstruction([pikepdf.Name(_gs_name(res, state, cache))], pikepdf.Operator("gs"))


def fix(data: bytes, white: bool = True, black_text: bool = True, text_max_pt: float = TEXT_MAX_PT) -> tuple:
    """Correct overprint -> (bytes, notes). white: switch overprint off for white objects; black_text: small
    black text overprints (overprint mode 1). Without a finding the bytes are returned unchanged.
    """
    import pikepdf

    want = ({"white"} if white else set()) | ({"black_text"} if black_text else set())
    notes: list = []
    if not want:
        return data, notes
    pdf = pikepdf.open(io.BytesIO(data))
    try:
        sc = _Scan(pdf, text_max_pt, plan=True, want=want)
        for i, page in enumerate(pdf.pages, start=1):
            sc.page(page, i)
        if not sc.edits:
            notes.append(tr("Überdrucken: nichts zu korrigieren – Datei unverändert."))
            return data, notes
        cache: set = set()
        for e in sc.edits:
            new = []
            for idx, item in enumerate(e.ins):
                st = e.before.get(idx)
                if st is not None:
                    new.append(_gs_op(e.res, st, cache))
                new.append(item)
                st = e.after.get(idx)
                if st is not None:
                    new.append(_gs_op(e.res, st, cache))
            raw = pikepdf.unparse_content_stream(new)
            if e.is_page:
                e.owner.obj.Contents = pdf.make_stream(raw)
            else:
                e.owner.write(raw)
        if "white" in want and sc.counts["white"]:
            notes.append(tr("Überdrucken bei {0} weißen Objekt(en) ausgeschaltet.").format(sc.counts["white"]))
        if "black_text" in want and sc.counts["black_text"]:
            notes.append(tr("{0} schwarze Textstelle(n) auf Überdrucken gestellt.").format(sc.counts["black_text"]))
        if sc.truncated:
            notes.append(tr("Überdrucken: sehr umfangreiche Seiten nur teilweise bearbeitet."))
        out = io.BytesIO()
        pdf.save(out)
        return out.getvalue(), notes
    finally:
        pdf.close()


def ghostscript_args(simulate: bool) -> list:
    """Ghostscript argument for rendering: simulate overprint (also spot colours, also on RGB devices) or not."""
    return ["-dOverprint=/simulate"] if simulate else ["-dOverprint=/disable"]
