# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Preview the way it comes out of the printer (as far as predictable).

* ICC output profile selected -> real soft proof with LittleCMS (Pillow.ImageCms):
                                sRGB -> printer profile -> screen, with intent and black point compensation.
* Driver sliders brightness / contrast / saturation / grayscale -> approximation. The manufacturers'
  exact math (e.g. Epson escpr2) is not documented.
"""
from __future__ import annotations

from .l10n import tr

import re

RX = {
    "brightness": re.compile(r"bright|hellig", re.I),
    "contrast": re.compile(r"contrast|kontrast", re.I),
    "saturation": re.compile(r"satur|sättig|saettig|chroma", re.I),
}
RX_GRAY = re.compile(r"mono|gr[ae]y|grau|schwarz|black|\bk\b|\bbw\b", re.I)
RX_COLOR = re.compile(r"colou?r|farb|rgb|cmyk", re.I)

# strength of the approximation at the end of a slider (t = ±1)
STRENGTH = {"brightness": 0.35, "contrast": 0.45, "saturation": 0.60}

INTENT_CMS = {"perceptual": 0, "relative": 1, "saturation": 2, "absolute": 3}


def _num(v):
    try:
        return float(str(v).replace(",", ".").rstrip("%"))
    except ValueError:
        return None


def adjustments(caps, values: dict) -> dict:
    """Ermittelt aus den Treiberoptionen, was die Vorschau simulieren soll."""
    adj = {"gray": False, "brightness": 0.0, "contrast": 0.0, "saturation": 0.0, "labels": []}
    if caps is None:
        return adj
    for key, opt in caps.options.items():
        if opt.installable:
            continue
        hay = f"{key} {opt.text}"
        for name, rx in RX.items():
            if not rx.search(hay):
                continue
            v = _num(values.get(key, opt.default))
            nums = [n for n in (_num(c.value) for c in opt.choices) if n is not None]
            if v is None or not nums:
                break
            lo, hi = min(nums), max(nums)
            mid = 100.0 if lo >= 0 and hi > 100 else 0.0      # 0..200 % Skalen
            span = max(abs(hi - mid), abs(lo - mid)) or 1.0
            t = max(-1.0, min(1.0, (v - mid) / span))
            if abs(t) > 1e-6:
                adj[name] = t
                adj["labels"].append(f"{opt.text} {v - mid:+g}")
            break
    ck = caps.roles.get("color")
    if ck and ck in caps.options:
        val = values.get(ck, caps.options[ck].default)
        txt = next((c.text for c in caps.options[ck].choices if c.value == val), "")
        if RX_GRAY.search(f"{val} {txt}") and not RX_COLOR.search(str(val)):
            adj["gray"] = True
            adj["labels"].append(tr("Graustufen"))
    return adj


_tf_cache = {}


def _proof_transform(icc_path: str, intent: str, bpc: bool):
    from PIL import ImageCms
    key = (icc_path, intent, bpc)
    if key not in _tf_cache:
        srgb = ImageCms.createProfile("sRGB")
        dev = ImageCms.getOpenProfile(icc_path)
        flags = ImageCms.Flags.SOFTPROOFING
        if bpc:
            flags |= ImageCms.Flags.BLACKPOINTCOMPENSATION
        it = INTENT_CMS.get(intent, 1)
        _tf_cache[key] = ImageCms.buildProofTransform(
            srgb, srgb, dev, "RGB", "RGB", renderingIntent=it,
            proofRenderingIntent=ImageCms.Intent.ABSOLUTE_COLORIMETRIC if intent == "absolute"
            else ImageCms.Intent.RELATIVE_COLORIMETRIC, flags=flags)
    return _tf_cache[key]


def apply(img, adj: dict, icc: str | None = None, intent: str = "relative", bpc: bool = True):
    """img: PIL-Bild (RGB). Reihenfolge wie im Druckweg: Profil, dann Treiberregler."""
    from PIL import ImageEnhance, ImageOps
    img = img.convert("RGB")
    if icc:
        try:
            img = ImageCms_apply(img, _proof_transform(icc, intent, bpc))
        except Exception:
            pass                      # defektes/inkompatibles Profil -> ohne Softproof
    if adj.get("gray"):
        img = ImageOps.grayscale(img).convert("RGB")
    t = adj.get("saturation", 0.0)
    if t and not adj.get("gray"):            # saturation does not change white/gray anyway
        img = ImageEnhance.Color(img).enhance(max(0.0, 1.0 + STRENGTH["saturation"] * t))
    lut = tone_curve(adj.get("brightness", 0.0), adj.get("contrast", 0.0))
    if lut is not None:
        img = img.point(lut * 3)
    return img


def tone_curve(brightness: float, contrast: float):
    """Gradation curve like in printer drivers: white (paper) and black stay fixed,
        the midtones change. Returns a 256-entry LUT or None.
    """
    if not brightness and not contrast:
        return None
    g = 1.0 / (1.0 + STRENGTH["brightness"] * 1.6 * brightness) if brightness > -0.6 else 2.5
    p = 1.0 / (1.0 + STRENGTH["contrast"] * 1.4 * contrast) if contrast > -0.7 else 2.7
    lut = []
    for i in range(256):
        x = (i / 255.0) ** g                         # Helligkeit: Gamma, Endpunkte fix
        u = 2.0 * x - 1.0                            # Kontrast: S-Kurve um Mittelgrau, Endpunkte fix
        x = 0.5 + 0.5 * (abs(u) ** p) * (1 if u >= 0 else -1)
        lut.append(max(0, min(255, round(x * 255))))
    lut[0], lut[255] = 0, 255
    return lut


def ImageCms_apply(img, tf):
    from PIL import ImageCms
    return ImageCms.applyTransform(img, tf)


def describe(adj: dict, profile_name: str | None) -> str:
    parts = list(adj.get("labels", []))
    if profile_name:
        parts.insert(0, tr("Softproof: {0}").format(profile_name))
    return (tr("Vorschau simuliert: ") + ", ".join(parts)) if parts else ""
