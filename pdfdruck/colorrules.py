# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Colour rules for the whole document (like "global changes" in PitStop) – also as a job in workflows.

  black       small text and thin lines in RGB black, grey black or 4-colour black -> 100 % K (DeviceCMYK)
              – no registration problems; large areas stay as they are (rich black is wanted there)
  spots       rename spot colours, merge duplicates ("HKS 43 K" / "HKS43K"), convert into their alternate
              colour (usually CMYK): text/graphics, images and smooth shades
  cut         cut contours under one name ("Cut", "Kiss-Cut", "Stanze" … -> "CutContour"), set to overprint

survey() lists what the document contains (for the dialog), apply() changes it -> (bytes, notes).
Only pikepdf (no pdfium, no Ghostscript) – safe in background threads.
"""

from __future__ import annotations

import io
import logging
import math
import re
from dataclasses import dataclass, field

from .l10n import tr

log = logging.getLogger(__name__)

CUT_ALIASES = (
    "CutContour",
    "Cut Contour",
    "Cut",
    "Cutline",
    "Cut Line",
    "Cutting",
    "Contour",
    "Kontur",
    "Konturschnitt",
    "Schneidkontur",
    "Schneidekontur",
    "Schnittkontur",
    "Schnitt",
    "Stanze",
    "Stanzkontur",
    "Stanzlinie",
    "Die",
    "Dieline",
    "Die Line",
    "Diecut",
    "Die Cut",
)
SPECIAL = {"All", "None"}  # registration colour and "nothing": never renamed or converted
MAX_DEPTH = 8


@dataclass
class ColorRulesSettings:
    """Settings of the job ``colorrules``."""

    black_text: bool = True  # small text in RGB/grey/4-colour black -> 100 % K
    black_text_max_pt: float = 12.0
    black_lines: bool = True  # thin lines likewise
    black_line_max_pt: float = 1.0  # line width
    rename: dict = field(default_factory=dict)  # spot colour -> new name
    merge_duplicates: bool = True  # "HKS 43 K" and "HKS43K" -> one name
    to_process: list = field(default_factory=list)  # spot colours -> alternate colour; "*" = all but cut contours
    cut_name: str = ""  # "" = leave cut contours alone; e.g. "CutContour"
    cut_aliases: list = field(default_factory=lambda: list(CUT_ALIASES))
    cut_overprint: bool = True  # cut contour always overprints (otherwise it knocks out the print)


def spot_key(name: str) -> str:
    """Name for comparing: without spaces, dashes, dots, underscores, case ignored ("HKS 43 K" = "hks43k")."""
    return re.sub(r"[\s_\-.]+", "", name or "").lower()


# --------------------------------------------------------------------------- #
# colour spaces in the document
# --------------------------------------------------------------------------- #
def _walk(obj, visit, seen: set):
    """All dictionaries and arrays below obj (indirect objects once), visit(array) for each array."""
    import pikepdf

    if isinstance(obj, (pikepdf.Dictionary, pikepdf.Stream, pikepdf.Array)):
        if obj.is_indirect:
            key = obj.objgen
            if key in seen:
                return
            seen.add(key)
        if isinstance(obj, pikepdf.Array):
            visit(obj)
            items = list(obj)
        else:
            items = [v for k, v in obj.items() if k not in ("/Parent", "/P")]
        for v in items:
            _walk(v, visit, seen)


def _colour_spaces(pdf) -> list:
    """Every /Separation and /DeviceN array of the document."""
    import pikepdf

    out = []

    def visit(a):
        try:
            if len(a) >= 4 and isinstance(a[0], pikepdf.Name) and str(a[0]) in ("/Separation", "/DeviceN"):
                out.append(a)
        except Exception:  # noqa: BLE001 – odd arrays: skip
            pass

    seen: set = set()
    for obj in pdf.objects:
        _walk(obj, visit, seen)
    return out


def _names_of(cs) -> list:
    if str(cs[0]) == "/Separation":
        return [str(cs[1])[1:]]
    return [str(n)[1:] for n in cs[1]]


def _page_spots(pdf) -> dict:
    """Spot colour -> set of pages (1-based) where a resource uses it (also in forms and patterns)."""
    import pikepdf

    found: dict = {}

    def scan_res(res, pno, depth, seen):
        if res is None or depth > MAX_DEPTH:
            return
        for key in ("/ColorSpace", "/XObject", "/Pattern", "/Shading"):
            d = res.get(key)
            if not isinstance(d, pikepdf.Dictionary):
                continue
            for _, v in d.items():
                if v.is_indirect and v.objgen in seen:
                    continue
                if v.is_indirect:
                    seen.add(v.objgen)

                def visit(a):
                    try:
                        if len(a) >= 4 and str(a[0]) in ("/Separation", "/DeviceN"):
                            for n in _names_of(a):
                                found.setdefault(n, set()).add(pno)
                    except Exception:  # noqa: BLE001
                        pass

                _walk(v, visit, set())
                if isinstance(v, (pikepdf.Stream, pikepdf.Dictionary)) and v.get("/Resources") is not None:
                    scan_res(v.get("/Resources"), pno, depth + 1, seen)

    from .pdfutil import page_resources

    for i, page in enumerate(pdf.pages, start=1):
        scan_res(page_resources(page), i, 0, set())
    return found


@dataclass
class Survey:
    """What the document contains: spot colours with pages, groups of duplicates, cut contour candidates."""

    spots: dict = field(default_factory=dict)  # name -> [pages]
    duplicates: list = field(default_factory=list)  # [[name, name …]] – same name except spaces/case
    cut: list = field(default_factory=list)  # names that look like a cut contour


def survey(data: bytes, aliases=CUT_ALIASES) -> Survey:
    """List spot colours, duplicates and cut contours of a PDF (for the dialog)."""
    import pikepdf

    with pikepdf.open(io.BytesIO(data)) as pdf:
        pages = _page_spots(pdf)
        names = set(pages)
        for cs in _colour_spaces(pdf):
            names.update(_names_of(cs))
    names -= SPECIAL
    s = Survey(spots={n: sorted(pages.get(n, ())) for n in sorted(names, key=str.lower)})
    groups: dict = {}
    for n in s.spots:
        groups.setdefault(spot_key(n), []).append(n)
    s.duplicates = [g for g in groups.values() if len(g) > 1]
    keys = {spot_key(a) for a in aliases}
    s.cut = [n for n in s.spots if spot_key(n) in keys]
    return s


def rename_plan(sv: Survey, s: ColorRulesSettings) -> dict:
    """Old name -> new name from the settings: own renames, duplicates merged, cut contours unified."""
    plan = {k: v for k, v in (s.rename or {}).items() if k and v and k != v and k not in SPECIAL}
    if s.merge_duplicates:
        for g in sv.duplicates:
            target = max(g, key=lambda n: (len(sv.spots.get(n, ())), " " in n, -g.index(n)))
            for n in g:
                if n != target and n not in plan:
                    plan[n] = plan.get(target, target)
    if s.cut_name:
        keys = {spot_key(a) for a in s.cut_aliases or ()}
        for n in sv.spots:
            if spot_key(n) in keys and n != s.cut_name:
                plan[n] = s.cut_name
    return plan


def _rename(pdf, plan: dict) -> int:
    """Rename spot colours in every Separation/DeviceN colour space -> number of changed colour spaces."""
    import pikepdf

    count = 0
    for cs in _colour_spaces(pdf):
        if str(cs[0]) == "/Separation":
            old = str(cs[1])[1:]
            if old in plan:
                cs[1] = pikepdf.Name("/" + plan[old])
                count += 1
            continue
        names = cs[1]
        changed = False
        for i in range(len(names)):
            old = str(names[i])[1:]
            if old in plan:
                names[i] = pikepdf.Name("/" + plan[old])
                changed = True
        attrs = cs[4] if len(cs) > 4 and isinstance(cs[4], pikepdf.Dictionary) else None
        col = attrs.get("/Colorants") if attrs is not None else None
        if isinstance(col, pikepdf.Dictionary):
            for k in list(col.keys()):
                if k[1:] in plan:
                    col["/" + plan[k[1:]]] = col[k]
                    del col[k]
                    changed = True
        count += changed
    return count


# --------------------------------------------------------------------------- #
# spot colour -> alternate colour
# --------------------------------------------------------------------------- #
class _Alt:
    """A Separation colour space that is converted: alternate space + tint transform."""

    def __init__(self, cs):
        from .pdffunc import compile_function

        self.name = str(cs[1])[1:]
        self.alt = cs[2]
        self.fn = compile_function(cs[3])
        self.n = _components(self.alt)
        self.range = _alt_range(self.alt, self.n)

    def values(self, tint: float) -> list:
        """Alternate colour for a tint (0..1)."""
        v = self.fn([tint])[: self.n]
        return v + [0.0] * (self.n - len(v))


def _components(cs) -> int:
    import pikepdf

    if isinstance(cs, pikepdf.Name):
        return {"/DeviceGray": 1, "/DeviceRGB": 3, "/DeviceCMYK": 4, "/CalGray": 1, "/CalRGB": 3}.get(str(cs), 0)
    fam = str(cs[0])
    if fam == "/ICCBased":
        return int(cs[1].get("/N", 3))
    if fam in ("/Lab", "/CalRGB"):
        return 3
    if fam == "/CalGray":
        return 1
    return 0


def _alt_range(cs, n: int) -> list:
    import pikepdf

    if not isinstance(cs, pikepdf.Name) and str(cs[0]) == "/Lab":
        r = [float(v) for v in (cs[1].get("/Range") or [-100, 100, -100, 100])]
        return [(0.0, 100.0), (r[0], r[1]), (r[2], r[3])]
    return [(0.0, 1.0)] * n


def _convertible(cs) -> bool:
    try:
        return str(cs[0]) == "/Separation" and _components(cs[2]) > 0
    except Exception:  # noqa: BLE001
        return False


def _sampled(pdf, fn, domain: tuple, rng: list, n_in_samples: int = 256):
    """Type 0 function (1 input) from a Python function – for shadings."""
    d0, d1 = domain
    out = bytearray()
    for i in range(n_in_samples):
        t = d0 + (d1 - d0) * i / (n_in_samples - 1)
        for v, (lo, hi) in zip(fn(t), rng, strict=False):
            q = 0.0 if hi == lo else (v - lo) / (hi - lo)
            q = min(1.0, max(0.0, q))
            u = int(round(q * 65535))
            out += bytes((u >> 8, u & 255))
    st = pdf.make_stream(bytes(out))
    st.FunctionType = 0
    st.Domain = [d0, d1]
    st.Range = [x for pair in rng for x in pair]
    st.Size = [n_in_samples]
    st.BitsPerSample = 16
    return st


def _convert_objects(pdf, targets: set, notes: list) -> tuple:
    """Images and smooth shades in a spot colour that is converted -> (images, shadings) converted."""
    import pikepdf

    imgs = shades = 0
    skipped: set = set()
    seen: set = set()
    todo = []

    def visit_dict(d):
        todo.append(d)

    def walk(obj, depth=0):
        if depth > 40 or not isinstance(obj, (pikepdf.Dictionary, pikepdf.Stream, pikepdf.Array)):
            return
        if obj.is_indirect:
            if obj.objgen in seen:
                return
            seen.add(obj.objgen)
        if isinstance(obj, (pikepdf.Dictionary, pikepdf.Stream)):
            visit_dict(obj)
            items = [v for k, v in obj.items() if k not in ("/Parent", "/P")]
        else:
            items = list(obj)
        for v in items:
            walk(v, depth + 1)

    for obj in pdf.objects:
        walk(obj)
    for d in todo:
        cs = d.get("/ColorSpace")
        if cs is None or not isinstance(cs, pikepdf.Array) or not _convertible(cs):
            continue
        name = str(cs[1])[1:]
        if name not in targets:
            continue
        try:
            alt = _Alt(cs)
        except Exception:  # noqa: BLE001 – unknown tint transform
            skipped.add(name)
            continue
        if isinstance(d, pikepdf.Stream) and d.get("/Subtype") == pikepdf.Name.Image:
            if _convert_image(d, alt):
                imgs += 1
            else:
                skipped.add(name)
        elif d.get("/ShadingType") is not None:
            if _convert_shading(pdf, d, alt):
                shades += 1
            else:
                skipped.add(name)
    for n in sorted(skipped):
        notes.append(tr("„{0}“: einige Bilder/Verläufe konnten nicht umgewandelt werden.").format(n))
    return imgs, shades


def _drop_resources(pdf, names: set) -> None:
    """Colour space resources of converted spot colours are no longer used: remove them, so the check does not
    report the spot colour any more."""
    import pikepdf

    def visit_dict(d):
        res_cs = d.get("/ColorSpace")
        if not isinstance(res_cs, pikepdf.Dictionary) or "/Type" in res_cs:
            return
        for k in list(res_cs.keys()):
            v = res_cs[k]
            if isinstance(v, pikepdf.Array) and _convertible(v) and str(v[1])[1:] in names:
                del res_cs[k]

    seen: set = set()

    def walk(obj, depth=0):
        if depth > 40 or not isinstance(obj, (pikepdf.Dictionary, pikepdf.Stream, pikepdf.Array)):
            return
        if obj.is_indirect:
            if obj.objgen in seen:
                return
            seen.add(obj.objgen)
        if isinstance(obj, (pikepdf.Dictionary, pikepdf.Stream)):
            if "/Resources" in obj or "/Font" in obj or "/XObject" in obj or "/ColorSpace" in obj:
                visit_dict(obj)
            items = [v for k, v in obj.items() if k not in ("/Parent", "/P")]
        else:
            items = list(obj)
        for v in items:
            walk(v, depth + 1)

    for obj in pdf.objects:
        walk(obj)


def _convert_image(img, alt: _Alt) -> bool:
    """Image in a spot colour (8 bit) -> image in the alternate colour."""
    import pikepdf

    if int(img.get("/BitsPerComponent", 8)) != 8:
        return False
    try:
        raw = img.read_bytes()  # decodes Flate/LZW …; JPEG stays specialised
    except Exception:  # noqa: BLE001
        return False
    flt = img.get("/Filter")
    flts = [str(f) for f in flt] if isinstance(flt, pikepdf.Array) else ([str(flt)] if flt is not None else [])
    if any(f in ("/DCTDecode", "/JPXDecode", "/JBIG2Decode", "/CCITTFaxDecode") for f in flts):
        return False
    w, h = int(img.Width), int(img.Height)
    if len(raw) < w * h:
        return False
    dec = [float(v) for v in img.get("/Decode", [0, 1])]
    lut = []
    for i in range(256):
        t = dec[0] + i / 255.0 * (dec[1] - dec[0])
        vals = alt.values(t)
        row = bytearray()
        for v, (lo, hi) in zip(vals, alt.range, strict=False):
            q = 0.0 if hi == lo else (v - lo) / (hi - lo)
            row.append(int(round(min(1.0, max(0.0, q)) * 255)))
        lut.append(bytes(row))
    out = b"".join(lut[b] for b in raw[: w * h])
    img.write(out)
    img.ColorSpace = alt.alt
    img.BitsPerComponent = 8
    if "/Decode" in img:
        del img["/Decode"]
    if alt.range[0] != (0.0, 1.0):  # Lab: map the 0..255 back onto the ranges
        img.Decode = [x for pair in alt.range for x in pair]
    return True


def _convert_shading(pdf, sh, alt: _Alt) -> bool:
    """Axial/radial shade (types 2 and 3, also 1 with one input) in a spot colour -> alternate colour."""
    t = int(sh.get("/ShadingType", 0))
    fn = sh.get("/Function")
    if t not in (2, 3) or fn is None:
        return False
    from .pdffunc import compile_function

    try:
        f = compile_function(fn)
    except Exception:  # noqa: BLE001
        return False
    dom = [float(v) for v in sh.get("/Domain", [0, 1])]
    sh.Function = _sampled(pdf, lambda x: alt.values(f([x])[0]), (dom[0], dom[1]), alt.range)
    sh.ColorSpace = alt.alt
    return True


# --------------------------------------------------------------------------- #
# content streams: black -> K, spot colour operators -> alternate colour, cut contour overprints
# --------------------------------------------------------------------------- #
PATH_CONSTR = {"m", "l", "c", "v", "y", "h", "re"}
PATH_PAINT = {"S", "s", "f", "F", "f*", "B", "B*", "b", "b*"}
FILL_PAINT = {"f", "F", "f*", "B", "B*", "b", "b*"}
STROKE_PAINT = {"S", "s", "B", "B*", "b", "b*"}
SHOW = {"Tj", "TJ", "'", '"'}


def is_black(kind: str, vals: list) -> bool:
    """RGB black, grey black or 4-colour black (K ≥ 90 % with some C/M/Y) – not pure K, which needs nothing."""
    if not vals:
        return False
    if kind == "Gray":
        return vals[0] <= 0.02
    if kind == "RGB":
        return len(vals) >= 3 and max(vals[:3]) <= 0.05
    if kind == "CMYK":
        return len(vals) >= 4 and vals[3] >= 0.9 and sum(vals[:3]) > 0.02
    return False


class _St:
    __slots__ = ("ctm", "fill", "stroke", "lw", "OP", "op", "font_size", "mode")

    def __init__(self):
        self.ctm = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
        # colour: (kind, values, resource name or None, spot name or "")
        self.fill = ("Gray", [0.0], None, "")
        self.stroke = ("Gray", [0.0], None, "")
        self.lw = 1.0
        self.OP = self.op = False
        self.font_size = 0.0
        self.mode = 0

    def copy(self):
        """Independent copy (for q and forms)."""
        s = _St()
        for k in self.__slots__:
            setattr(s, k, getattr(self, k))
        return s


def _mul(a, b):
    return (
        a[0] * b[0] + a[1] * b[2],
        a[0] * b[1] + a[1] * b[3],
        a[2] * b[0] + a[3] * b[2],
        a[2] * b[1] + a[3] * b[3],
        a[4] * b[0] + a[5] * b[2] + b[4],
        a[4] * b[1] + a[5] * b[3] + b[5],
    )


def _scale(m) -> float:
    return math.sqrt(abs(m[0] * m[3] - m[1] * m[2])) or 1.0


class _Rewriter:
    """One pass over the content streams of all pages (forms and tiling patterns once)."""

    def __init__(self, pdf, s: ColorRulesSettings, alts: dict):
        self.pdf, self.s, self.alts = pdf, s, alts  # alts: spot name -> _Alt (converted)
        self.done: set = set()
        self.count = {"black_text": 0, "black_lines": 0, "spot_ops": 0, "cut_op": 0}
        self.res_cache: dict = {}

    def page(self, page):
        """Rewrite the content of one page (and its forms/patterns)."""
        import pikepdf

        from .pdfutil import page_resources

        res = page_resources(page)
        try:
            ins = list(pikepdf.parse_content_stream(page))
        except Exception:  # noqa: BLE001 – damaged content: leave it
            return
        new = self._run(ins, res, _St(), 0)
        if new is not None:
            page.obj.Contents = self.pdf.make_stream(pikepdf.unparse_content_stream(new))

    def _stream(self, st, res, state, depth):
        """Form XObject or tiling pattern: rewrite its stream once."""
        import pikepdf

        key = st.objgen if st.is_indirect else id(st)
        if key in self.done or depth > MAX_DEPTH:
            return
        self.done.add(key)
        own = st.get("/Resources")
        r = own if own is not None else res
        try:
            ins = list(pikepdf.parse_content_stream(st))
        except Exception:  # noqa: BLE001
            return
        new = self._run(ins, r, state, depth + 1)
        if new is not None:
            st.write(pikepdf.unparse_content_stream(new))

    # ------------------------------------------------------------------ #
    def _space(self, operand, res):
        """cs operand -> (kind, n, resource name or None, spot name, colour space object)."""
        import pikepdf

        from .pipette import _space

        sp = _space(operand, res)
        name = str(operand) if isinstance(operand, pikepdf.Name) else None
        obj = None
        if name and name not in ("/DeviceGray", "/DeviceRGB", "/DeviceCMYK", "/Pattern"):
            try:
                obj = res.ColorSpace[name]
            except (AttributeError, KeyError, TypeError):
                obj = None
        spot = sp.get("spot", "") if sp["space"] == "Separation" else ""
        return sp["space"], sp["n"], name, spot, obj

    def _restore_ops(self, colour, stroke: bool) -> list:
        """Instructions that set ``colour`` again (after a temporary 100 % K)."""
        import pikepdf

        kind, vals, name, _spot = colour
        Ins = pikepdf.ContentStreamInstruction  # noqa: N806
        Op = pikepdf.Operator  # noqa: N806
        if name is None:
            op = {"Gray": "g", "RGB": "rg", "CMYK": "k"}[kind]
            return [Ins([*vals], Op(op.upper() if stroke else op))]
        return [Ins([pikepdf.Name(name)], Op("CS" if stroke else "cs")), Ins([*vals], Op("SCN" if stroke else "scn"))]

    def _k_ops(self, stroke: bool) -> list:
        import pikepdf

        return [pikepdf.ContentStreamInstruction([0, 0, 0, 1], pikepdf.Operator("K" if stroke else "k"))]

    def _gs_op(self, res, OP: bool, op: bool) -> list:  # noqa: N803
        import pikepdf

        name = f"/PMcr{int(OP)}{int(op)}"
        if res.get("/ExtGState") is None:
            res.ExtGState = pikepdf.Dictionary()
        if name not in res.ExtGState:
            res.ExtGState[name] = pikepdf.Dictionary(Type=pikepdf.Name.ExtGState, OP=OP, op=op, OPM=1)
        return [pikepdf.ContentStreamInstruction([pikepdf.Name(name)], pikepdf.Operator("gs"))]

    def _alt_cs(self, res, alt: _Alt):
        """Operand for cs: the alternate colour space (device name, or a name added to the resources)."""
        import pikepdf

        if isinstance(alt.alt, pikepdf.Name):
            return alt.alt
        if res.get("/ColorSpace") is None:
            res.ColorSpace = pikepdf.Dictionary()
        name = "/PMalt" + (re.sub(r"[^A-Za-z0-9]", "", alt.name)[:24] or "Spot")
        res.ColorSpace[name] = alt.alt
        return pikepdf.Name(name)

    # ------------------------------------------------------------------ #
    def _run(self, ins, res, st: _St, depth: int):
        """Walk the instructions; returns the new list or None when nothing changed."""
        import pikepdf

        from .pipette import _nums

        Ins = pikepdf.ContentStreamInstruction  # noqa: N806
        Op = pikepdf.Operator  # noqa: N806
        before: dict = {}
        after: dict = {}
        replace: dict = {}
        stack = []
        tm = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
        tlm = tm
        leading = 0.0
        path_start = None
        for idx, item in enumerate(ins):
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
                elif op == "w" and ops:
                    st.lw = abs(float(ops[0]))
                elif op == "gs" and ops:
                    g = res.ExtGState[ops[0]] if res.get("/ExtGState") is not None else None
                    if g is not None:
                        if "/OP" in g:
                            st.OP = bool(g.OP)
                            if "/op" not in g:
                                st.op = st.OP
                        if "/op" in g:
                            st.op = bool(g.op)
                elif op in ("g", "G"):
                    c = ("Gray", _nums(ops), None, "")
                    st.fill, st.stroke = (c, st.stroke) if op == "g" else (st.fill, c)
                elif op in ("rg", "RG"):
                    c = ("RGB", _nums(ops), None, "")
                    st.fill, st.stroke = (c, st.stroke) if op == "rg" else (st.fill, c)
                elif op in ("k", "K"):
                    c = ("CMYK", _nums(ops), None, "")
                    st.fill, st.stroke = (c, st.stroke) if op == "k" else (st.fill, c)
                elif op in ("cs", "CS") and ops:
                    kind, n, name, spot, obj = self._space(ops[0], res)
                    init = [1.0] * max(1, n) if kind in ("Separation", "DeviceN") else [0.0] * max(1, n)
                    if kind == "CMYK":
                        init = [0.0, 0.0, 0.0, 1.0]
                    c = (kind, init, name, spot)
                    if spot in self.alts:  # spot colour converted: alternate space + its colour for 100 %
                        alt = self.alts[spot]
                        stroke = op == "CS"
                        replace[idx] = [
                            Ins([self._alt_cs(res, alt)], Op(op)),
                            Ins(alt.values(1.0), Op("SCN" if stroke else "scn")),
                        ]
                        self.count["spot_ops"] += 1
                    st.fill, st.stroke = (c, st.stroke) if op == "cs" else (st.fill, c)
                elif op in ("sc", "scn", "SC", "SCN"):
                    fill = op in ("sc", "scn")
                    cur = st.fill if fill else st.stroke
                    vals = _nums(ops)
                    c = (cur[0], vals or cur[1], cur[2], cur[3])
                    if cur[3] in self.alts and vals:
                        replace[idx] = [Ins(self.alts[cur[3]].values(vals[0]), Op(op))]
                    if fill:
                        st.fill = c
                    else:
                        st.stroke = c
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
                    if op == "TD":
                        leading = -float(ops[1])
                    tm = tlm = _mul((1, 0, 0, 1, float(ops[0]), float(ops[1])), tlm)
                elif op in ("T*", "'", '"'):
                    tm = tlm = _mul((1, 0, 0, 1, 0, -leading), tlm)
            except (TypeError, ValueError, IndexError, KeyError, AttributeError):
                pass
            if op in PATH_CONSTR:
                if path_start is None:
                    path_start = idx
            elif op in PATH_PAINT and path_start is not None:
                self._paint(st, op, res, before, after, path_start, idx)
                path_start = None
            elif op == "n":
                path_start = None
            elif op in SHOW:
                self._show(st, tm, res, before, after, idx)
            elif op == "Do" and ops:
                self._do(st, res, ops[0], depth)
            elif op == "scn" or op == "SCN":
                self._pattern(st, res, ops, depth)
        if not (before or after or replace):
            return None
        out = []
        for idx, item in enumerate(ins):
            out += before.get(idx, [])
            out += replace.get(idx, [item])
            out += after.get(idx, [])
        return out

    def _cut(self, colour) -> bool:
        return bool(self.s.cut_name) and self.s.cut_overprint and colour[3] == self.s.cut_name

    def _paint(self, st, op, res, before, after, start, end):
        s = self.s
        pre, post = [], []
        fills, strokes = op in FILL_PAINT, op in STROKE_PAINT
        if (
            s.black_lines
            and strokes
            and st.lw * _scale(st.ctm) <= s.black_line_max_pt + 1e-6
            and is_black(st.stroke[0], st.stroke[1])
        ):
            pre += self._k_ops(True)
            post += self._restore_ops(st.stroke, True)
            self.count["black_lines"] += 1
        cut_fill = fills and self._cut(st.fill) and not st.op
        cut_stroke = strokes and self._cut(st.stroke) and not st.OP
        if cut_fill or cut_stroke:
            pre += self._gs_op(res, st.OP or cut_stroke, st.op or cut_fill)
            post = self._gs_op(res, st.OP, st.op) + post
            self.count["cut_op"] += 1
        if pre:
            before[start] = before.get(start, []) + pre
            after[end] = post + after.get(end, [])

    def _show(self, st, tm, res, before, after, idx):
        s = self.s
        size = st.font_size * _scale(_mul(tm, st.ctm))
        pre, post = [], []
        if s.black_text and 0 < size <= s.black_text_max_pt + 1e-6:
            if st.mode in (0, 2, 4, 6) and is_black(st.fill[0], st.fill[1]):
                pre += self._k_ops(False)
                post += self._restore_ops(st.fill, False)
            if st.mode in (1, 2, 5, 6) and is_black(st.stroke[0], st.stroke[1]):
                pre += self._k_ops(True)
                post += self._restore_ops(st.stroke, True)
            if pre:
                self.count["black_text"] += 1
        if self._cut(st.fill) and not st.op and st.mode in (0, 2, 4, 6):
            pre += self._gs_op(res, st.OP, True)
            post = self._gs_op(res, st.OP, st.op) + post
            self.count["cut_op"] += 1
        if pre:
            before[idx] = before.get(idx, []) + pre
            after[idx] = post + after.get(idx, [])

    def _do(self, st, res, name, depth):
        import pikepdf

        try:
            xo = res.XObject[name]
        except (AttributeError, KeyError, TypeError):
            return
        if isinstance(xo, pikepdf.Stream) and xo.get("/Subtype") == pikepdf.Name.Form:
            sub = st.copy()
            m = xo.get("/Matrix")
            if m is not None and len(m) == 6:
                try:
                    sub.ctm = _mul(tuple(float(v) for v in m), sub.ctm)
                except (TypeError, ValueError):
                    pass
            self._stream(xo, res, sub, depth)

    def _pattern(self, st, res, ops, depth):
        """scn /P0: a tiling pattern has its own content stream."""
        import pikepdf

        if not ops or not isinstance(ops[-1], pikepdf.Name):
            return
        try:
            pat = res.Pattern[ops[-1]]
        except (AttributeError, KeyError, TypeError):
            return
        if isinstance(pat, pikepdf.Stream) and int(pat.get("/PatternType", 0)) == 1:
            self._stream(pat, res, _St(), depth)


# --------------------------------------------------------------------------- #
# public interface
# --------------------------------------------------------------------------- #
def apply(data: bytes, s: ColorRulesSettings | None = None) -> tuple:
    """Apply the colour rules -> (bytes, notes). Unchanged bytes when there is nothing to do."""
    import pikepdf

    s = s or ColorRulesSettings()
    notes: list = []
    sv = survey(data, s.cut_aliases or CUT_ALIASES)
    plan = rename_plan(sv, s)
    pdf = pikepdf.open(io.BytesIO(data))
    try:
        changed = False
        if plan:
            n = _rename(pdf, plan)
            if n:
                changed = True
                for old, new in sorted(plan.items()):
                    notes.append(tr("Sonderfarbe „{0}“ → „{1}“.").format(old, new))
        # spot colours into their alternate colour (names after renaming)
        names_now = {plan.get(n, n) for n in sv.spots}
        cut_keys = {spot_key(a) for a in (s.cut_aliases or ())} | ({spot_key(s.cut_name)} if s.cut_name else set())
        want = set()
        for n in s.to_process or ():
            if n == "*":
                want |= {x for x in names_now if spot_key(x) not in cut_keys}
            else:
                want.add(plan.get(n, n))
        want &= names_now
        alts: dict = {}
        for cs in _colour_spaces(pdf):
            if _convertible(cs):
                name = str(cs[1])[1:]
                if name in want and name not in alts:
                    try:
                        alts[name] = _Alt(cs)
                    except Exception:  # noqa: BLE001 – function not understood
                        notes.append(tr("„{0}“: Umrechnung unbekannt, bleibt Sonderfarbe.").format(name))
        rw = _Rewriter(pdf, s, alts)
        for page in pdf.pages:
            rw.page(page)
        imgs, shades = _convert_objects(pdf, set(alts), notes) if alts else (0, 0)
        if alts:
            _drop_resources(pdf, set(alts))
        c = rw.count
        if c["black_text"]:
            notes.append(tr("{0} kleine Textstelle(n) in Schwarz auf 100 % K gesetzt.").format(c["black_text"]))
        if c["black_lines"]:
            notes.append(tr("{0} dünne Linie(n) in Schwarz auf 100 % K gesetzt.").format(c["black_lines"]))
        if alts:
            notes.append(
                tr("In Prozessfarben umgewandelt: {0} ({1} Stelle(n), {2} Bild(er), {3} Verläufe).").format(
                    ", ".join(sorted(alts)), c["spot_ops"], imgs, shades
                )
            )
        for n in sorted(want - set(alts)):
            if not any(n in x for x in notes):
                notes.append(tr("„{0}“ ist keine einfache Sonderfarbe (DeviceN) – bleibt.").format(n))
        if c["cut_op"]:
            notes.append(
                tr("Schneidkontur „{0}“ an {1} Stelle(n) auf Überdrucken gestellt.").format(s.cut_name, c["cut_op"])
            )
        changed = changed or any(c.values()) or imgs or shades
        if not changed:
            return data, [tr("Farbregeln: nichts zu ändern – Datei unverändert.")]
        out = io.BytesIO()
        pdf.save(out)
        return out.getvalue(), notes
    finally:
        pdf.close()
