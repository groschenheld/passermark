# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""PDF functions (ISO 32000 7.10): evaluate them in Python – for the tint transforms of spot colours.

    f = compile_function(obj)      # pikepdf Dictionary/Stream (or an array of 1-output functions)
    f([0.5]) -> [0.0, 0.46, 0.39, 0.0]

Types 0 (sampled, any number of inputs, linear interpolation), 2 (exponential), 3 (stitching) and
4 (PostScript calculator). Unknown or broken functions raise ValueError.
"""

from __future__ import annotations

import math
import re


def _floats(arr) -> list:
    return [float(v) for v in arr] if arr is not None else []


def _clip(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def _pairs(arr) -> list:
    a = _floats(arr)
    return [(a[i], a[i + 1]) for i in range(0, len(a) - 1, 2)]


def compile_function(obj):
    """Function object -> callable(list of inputs) -> list of outputs."""
    import pikepdf

    if isinstance(obj, pikepdf.Array):  # several functions with one output each (e.g. in shadings)
        fs = [compile_function(o) for o in obj]
        return lambda x: [f(x)[0] for f in fs]
    try:
        kind = int(obj.get("/FunctionType"))
    except (TypeError, ValueError, AttributeError) as e:
        raise ValueError("keine PDF-Funktion") from e
    domain = _pairs(obj.get("/Domain"))
    rng = _pairs(obj.get("/Range")) if obj.get("/Range") is not None else None
    if kind == 2:
        f = _type2(obj)
    elif kind == 0:
        f = _type0(obj, domain, rng)
    elif kind == 3:
        f = _type3(obj, domain)
    elif kind == 4:
        f = _type4(obj)
    else:
        raise ValueError(f"Funktionstyp {kind} unbekannt")

    def run(x):
        x = [_clip(float(v), lo, hi) for v, (lo, hi) in zip(x, domain, strict=False)] if domain else list(x)
        y = f(x)
        if rng:
            y = [_clip(v, lo, hi) for v, (lo, hi) in zip(y, rng, strict=False)]
        return y

    return run


def _type2(obj):
    c0 = _floats(obj.get("/C0")) or [0.0]
    c1 = _floats(obj.get("/C1")) or [1.0]
    n = float(obj.get("/N", 1))

    def f(x):
        t = x[0]
        p = t**n if t >= 0 or n == int(n) else 0.0
        return [a + p * (b - a) for a, b in zip(c0, c1, strict=False)]

    return f


def _type0(obj, domain, rng):
    size = [int(v) for v in obj.get("/Size")]
    bps = int(obj.get("/BitsPerSample"))
    m, n = len(size), len(rng or [])
    if not n:
        raise ValueError("Typ 0 ohne /Range")
    enc = _pairs(obj.get("/Encode")) or [(0.0, s - 1.0) for s in size]
    dec = _pairs(obj.get("/Decode")) or rng
    data = obj.read_bytes()
    total = n
    for s in size:
        total *= s
    samples = _unpack(data, bps, total)
    top = float((1 << bps) - 1)

    def sample(idx: list) -> list:
        pos, mul = 0, 1
        for i, s in zip(idx, size, strict=True):
            pos += i * mul
            mul *= s
        base = pos * n
        return [samples[base + j] for j in range(n)]

    def f(x):
        e = []
        for i in range(m):
            d0, d1 = domain[i]
            e0, e1 = enc[i]
            v = e0 + (x[i] - d0) * (e1 - e0) / ((d1 - d0) or 1.0)
            e.append(_clip(v, 0.0, size[i] - 1.0))
        out = [0.0] * n
        for corner in range(1 << m):  # multilinear interpolation over the 2^m neighbours
            w, idx = 1.0, []
            for i in range(m):
                lo = int(math.floor(e[i]))
                hi = min(lo + 1, size[i] - 1)
                fr = e[i] - lo
                if corner >> i & 1:
                    w *= fr
                    idx.append(hi)
                else:
                    w *= 1.0 - fr
                    idx.append(lo)
            if w == 0.0:
                continue
            s = sample(idx)
            for j in range(n):
                out[j] += w * s[j]
        return [dec[j][0] + out[j] * (dec[j][1] - dec[j][0]) / top for j in range(n)]

    return f


def _unpack(data: bytes, bps: int, count: int) -> list:
    if bps == 8:
        return list(data[:count])
    if bps == 16:
        return [data[2 * i] << 8 | data[2 * i + 1] for i in range(min(count, len(data) // 2))]
    out, acc, bits = [], 0, 0
    mask = (1 << bps) - 1
    for b in data:
        acc = acc << 8 | b
        bits += 8
        while bits >= bps and len(out) < count:
            bits -= bps
            out.append(acc >> bits & mask)
    return out


def _type3(obj, domain):
    fs = [compile_function(o) for o in obj.get("/Functions")]
    bounds = _floats(obj.get("/Bounds"))
    enc = _pairs(obj.get("/Encode"))
    d0, d1 = domain[0] if domain else (0.0, 1.0)

    def f(x):
        t = x[0]
        k = 0
        while k < len(bounds) and t >= bounds[k]:
            k += 1
        k = min(k, len(fs) - 1)
        lo = d0 if k == 0 else bounds[k - 1]
        hi = d1 if k >= len(bounds) else bounds[k]
        e0, e1 = enc[k] if k < len(enc) else (0.0, 1.0)
        u = e0 + (t - lo) * (e1 - e0) / ((hi - lo) or 1.0)
        return fs[k]([u])

    return f


_TOKEN = re.compile(rb"\{|\}|[^\s{}]+")


def _parse_ps(code: bytes):
    toks = _TOKEN.findall(code)
    pos = 0

    def block():
        nonlocal pos
        out = []
        while pos < len(toks):
            t = toks[pos]
            pos += 1
            if t == b"{":
                out.append(block())
            elif t == b"}":
                return out
            else:
                try:
                    out.append(float(t) if (b"." in t or b"e" in t.lower()) else int(t))
                except ValueError:
                    out.append(t.decode("latin-1"))
        return out

    prog = block()
    if len(prog) == 1 and isinstance(prog[0], list):
        return prog[0]
    return prog


def _type4(obj):
    prog = _parse_ps(obj.read_bytes())

    def f(x):
        st = list(x)
        _exec(prog, st)
        return [float(v) for v in st]

    return f


_OPS1 = {
    "abs": abs,
    "neg": lambda a: -a,
    "ceiling": lambda a: float(math.ceil(a)),
    "floor": lambda a: float(math.floor(a)),
    "round": lambda a: float(math.floor(a + 0.5)),
    "truncate": lambda a: float(math.trunc(a)),
    "sqrt": lambda a: math.sqrt(max(0.0, a)),
    "sin": lambda a: math.sin(math.radians(a)),
    "cos": lambda a: math.cos(math.radians(a)),
    "ln": lambda a: math.log(a) if a > 0 else -1e30,
    "log": lambda a: math.log10(a) if a > 0 else -1e30,
    "cvi": lambda a: int(a),
    "cvr": lambda a: float(a),
    "not": lambda a: (not a) if isinstance(a, bool) else ~int(a),
}
_OPS2 = {
    "add": lambda a, b: a + b,
    "sub": lambda a, b: a - b,
    "mul": lambda a, b: a * b,
    "div": lambda a, b: a / b if b else 0.0,
    "idiv": lambda a, b: int(a) // int(b) if int(b) else 0,
    "mod": lambda a, b: int(a) % int(b) if int(b) else 0,
    "exp": lambda a, b: a**b if a > 0 or float(b).is_integer() else 0.0,
    "atan": lambda a, b: math.degrees(math.atan2(a, b)) % 360.0,
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "gt": lambda a, b: a > b,
    "ge": lambda a, b: a >= b,
    "lt": lambda a, b: a < b,
    "le": lambda a, b: a <= b,
    "and": lambda a, b: (a and b) if isinstance(a, bool) else int(a) & int(b),
    "or": lambda a, b: (a or b) if isinstance(a, bool) else int(a) | int(b),
    "xor": lambda a, b: (a != b) if isinstance(a, bool) else int(a) ^ int(b),
    "bitshift": lambda a, b: int(a) << int(b) if b >= 0 else int(a) >> -int(b),
}


def _exec(prog, st: list, depth: int = 0):
    if depth > 50:
        raise ValueError("PostScript-Funktion zu tief verschachtelt")
    i = 0
    while i < len(prog):
        t = prog[i]
        i += 1
        if isinstance(t, (int, float)):
            st.append(t)
        elif isinstance(t, list):
            st.append(t)  # procedure for if/ifelse
        elif t == "true":
            st.append(True)
        elif t == "false":
            st.append(False)
        elif t in _OPS1:
            st.append(_OPS1[t](st.pop()))
        elif t in _OPS2:
            b, a = st.pop(), st.pop()
            st.append(_OPS2[t](a, b))
        elif t == "dup":
            st.append(st[-1])
        elif t == "pop":
            st.pop()
        elif t == "exch":
            st[-1], st[-2] = st[-2], st[-1]
        elif t == "copy":
            n = int(st.pop())
            if n:
                st.extend(st[-n:])
        elif t == "index":
            n = int(st.pop())
            st.append(st[-1 - n])
        elif t == "roll":
            j, n = int(st.pop()), int(st.pop())
            if n:
                part = st[-n:]
                j %= n
                st[-n:] = part[-j:] + part[:-j] if j else part
        elif t == "if":
            proc, cond = st.pop(), st.pop()
            if cond:
                _exec(proc, st, depth + 1)
        elif t == "ifelse":
            p2, p1, cond = st.pop(), st.pop(), st.pop()
            _exec(p1 if cond else p2, st, depth + 1)
        else:
            raise ValueError(f"PostScript-Operator {t!r} unbekannt")
