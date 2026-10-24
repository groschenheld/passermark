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

import os
import re

from .l10n import tr

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


# --------------------------------------------------------------------------- #
# Softproof der Seitenansicht (allgemein, unabhängig vom Druckdialog)
# --------------------------------------------------------------------------- #
# spec = {"icc": Pfad, "space": "CMYK"|"RGB"|"Gray", "name": Anzeigename, "intent": "relative", "bpc": True,
#         "paper": Papierfarbe simulieren, "black": schwarze Druckfarbe simulieren, "white": [L, a, b] | None
#         (gemessenes Papierweiß des Materials statt des Profilweiß), "warn": "none"|"gamut"|"tac", "tac": 300}
#
# CMYK-Profil + Ghostscript: die Seite wird wie bei der CMYK-Umwandlung separiert (vorhandenes CMYK bleibt,
# RGB/Grau -> Profil) und diese CMYK-Werte werden angezeigt – genau die Farben, die gedruckt würden.
# Sonst (RGB-Druckerprofil, kein Ghostscript): Bild der Seite (sRGB) -> Profil -> Bildschirm.
PROOF_MAX_DPI = 300
GAMUT_COLOR = (255, 0, 255)
TAC_COLOR = (255, 0, 64)
_BRADFORD_D50_D65 = ((0.9555766, -0.0230393, 0.0631636),
                     (-0.0282895, 1.0099416, 0.0210077),
                     (0.0122982, -0.0204830, 1.3299098))
_XYZ_SRGB = ((3.2404542, -1.5371385, -0.4985314),
             (-0.9692660, 1.8760108, 0.0415560),
             (0.0556434, -0.2040259, 1.0572252))


def spec_key(spec) -> tuple:
    if not spec:
        return ()
    w = tuple(round(float(x), 2) for x in spec["white"]) if spec.get("white") else None
    return (spec.get("icc"), spec.get("intent", "relative"), bool(spec.get("bpc", True)), bool(spec.get("paper")),
            bool(spec.get("black")), w, spec.get("warn", "none"), float(spec.get("tac", 300)))


def describe_spec(spec) -> str:
    if not spec:
        return ""
    parts = [spec.get("name") or os.path.basename(spec.get("icc", ""))]
    if spec.get("paper"):
        parts.append(tr("Papierweiß (gemessen)") if spec.get("white") else tr("Papierweiß"))
    elif spec.get("black"):
        parts.append(tr("Schwarz"))
    if spec.get("warn") == "gamut":
        parts.append(tr("Farbumfang-Warnung"))
    elif spec.get("warn") == "tac":
        parts.append(tr("Farbauftrag > {0:g} %").format(float(spec.get("tac", 300))))
    return tr("Softproof: {0}").format(", ".join(p for p in parts if p))


def _mode(space: str) -> str:
    return {"CMYK": "CMYK", "RGB": "RGB", "Gray": "L"}.get(space, "RGB")


_sp_cache: dict = {}


def _tf(kind: str, icc: str, space: str, intent: str = "relative", bpc: bool = True):
    """Zwischengespeicherte LittleCMS-Transformationen:
        to_dev  sRGB -> Gerät (Intent, BPC)         dev_lab  Gerät -> Lab (relativ, ohne BPC: Papier = L 100)
        srgb_lab sRGB -> Lab (relativ)              dev_scr  Gerät -> Bildschirm (Variante in intent/bpc kodiert)"""
    from PIL import ImageCms
    key = (kind, icc, space, intent, bpc)
    if key in _sp_cache:
        return _sp_cache[key]
    srgb, lab = ImageCms.createProfile("sRGB"), ImageCms.createProfile("LAB")
    mode = _mode(space)
    R = ImageCms.Intent
    if kind == "to_dev":
        tf = ImageCms.buildTransform(srgb, ImageCms.getOpenProfile(icc), "RGB", mode,
                                     renderingIntent=INTENT_CMS.get(intent, 1),
                                     flags=ImageCms.Flags.BLACKPOINTCOMPENSATION if bpc else 0)
    elif kind == "dev_lab":
        tf = ImageCms.buildTransform(ImageCms.getOpenProfile(icc), lab, mode, "LAB",
                                     renderingIntent=R.RELATIVE_COLORIMETRIC)
    elif kind == "dev_lab_bpc":                    # für die Farbumfang-Warnung: Tiefen wie im Druck skaliert
        tf = ImageCms.buildTransform(ImageCms.getOpenProfile(icc), lab, mode, "LAB",
                                     renderingIntent=R.RELATIVE_COLORIMETRIC, flags=ImageCms.Flags.BLACKPOINTCOMPENSATION)
    elif kind == "srgb_lab":
        tf = ImageCms.buildTransform(srgb, lab, "RGB", "LAB", renderingIntent=R.RELATIVE_COLORIMETRIC)
    else:                                          # dev_scr: intent "absolute" = Papier, bpc False = Schwarz
        tf = ImageCms.buildTransform(ImageCms.getOpenProfile(icc), srgb, mode, "RGB",
                                     renderingIntent=R.ABSOLUTE_COLORIMETRIC if intent == "absolute"
                                     else R.RELATIVE_COLORIMETRIC,
                                     flags=ImageCms.Flags.BLACKPOINTCOMPENSATION if bpc else 0)
    if len(_sp_cache) > 48:
        _sp_cache.clear()
    _sp_cache[key] = tf
    return tf


def _lab_arrays(lab_img):
    import numpy as np
    a = np.asarray(lab_img, dtype=np.uint8)           # Pillow speichert a/b mit Vorzeichen (0 = neutral)
    ab = a[..., 1:].view(np.int8).astype(np.float32)
    return a[..., 0].astype(np.float32) * (100.0 / 255.0), ab[..., 0], ab[..., 1]


def lab_to_screen(lab_img, white=None):
    """Lab-Bild (relativ: Papier = L 100) -> sRGB-Bild. white = Papierweiß (Lab D50): das Papier erscheint
        in dieser Farbe, alle Farben im selben Verhältnis (wie absolut farbmetrisch, nur mit dem Messwert)."""
    import numpy as np
    from PIL import Image
    from .colorlab import D50, lab_to_xyz
    L, A, B = _lab_arrays(lab_img)
    fy = (L + 16.0) / 116.0
    fx, fz = fy + A / 500.0, fy - B / 200.0
    e = 6.0 / 29.0

    def finv(t):
        return np.where(t > e, t ** 3, 3 * e * e * (t - 4.0 / 29.0))
    X, Y, Z = finv(fx) * D50[0] / 100, finv(fy), finv(fz) * D50[2] / 100
    if white:
        wx, wy, wz = lab_to_xyz(white)
        X, Y, Z = X * (wx / D50[0]), Y * (wy / D50[1]), Z * (wz / D50[2])
    xyz = np.stack([X, Y, Z], axis=-1)
    m = np.asarray(_XYZ_SRGB, dtype=np.float32) @ np.asarray(_BRADFORD_D50_D65, dtype=np.float32)
    rgb = np.clip(xyz @ m.T, 0.0, 1.0)
    rgb = np.where(rgb <= 0.0031308, 12.92 * rgb, 1.055 * np.power(rgb, 1 / 2.4) - 0.055)
    return Image.fromarray(np.clip(rgb * 255.0 + 0.5, 0, 255).astype(np.uint8), "RGB")


def device_to_screen(dev, spec):
    """Gerätefarben (Bild im Modus des Profils) so zeigen, wie sie auf dem Papier aussehen."""
    from PIL import ImageCms
    icc, space = spec["icc"], spec.get("space") or "CMYK"
    if spec.get("paper") and spec.get("white"):
        return lab_to_screen(ImageCms.applyTransform(dev, _tf("dev_lab", icc, space)), spec["white"])
    if spec.get("paper"):
        return ImageCms.applyTransform(dev, _tf("dev_scr", icc, space, "absolute", False))
    return ImageCms.applyTransform(dev, _tf("dev_scr", icc, space, "relative", not spec.get("black")))


def gamut_mask(rgb, spec, limit: float = 5.0):
    """Wo das Profil die (sRGB-)Farbe nicht erreicht: Abstand Original <-> Hin-und-zurück über das Profil (ΔE 76)."""
    import numpy as np
    from PIL import ImageCms
    icc, space = spec["icc"], spec.get("space") or "CMYK"
    src = ImageCms.applyTransform(rgb, _tf("srgb_lab", icc, space))
    dev = ImageCms.applyTransform(rgb, _tf("to_dev", icc, space, "relative", True))
    back = ImageCms.applyTransform(dev, _tf("dev_lab_bpc", icc, space))
    a, b = _lab_arrays(src), _lab_arrays(back)
    d = np.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)
    return d > limit


def _mark(img, mask, color):
    import numpy as np
    from PIL import Image
    if mask is None or not mask.any():
        return img
    a = np.asarray(img.convert("RGB")).copy()
    a[mask] = color
    return Image.fromarray(a, "RGB")


def softproof_rgb(rgb, spec):
    """Seitenbild (sRGB, wie pdfium es liefert) -> Druckergebnis auf dem Bildschirm."""
    from PIL import ImageCms
    rgb = rgb.convert("RGB")
    dev = ImageCms.applyTransform(rgb, _tf("to_dev", spec["icc"], spec.get("space") or "CMYK",
                                           spec.get("intent", "relative"), bool(spec.get("bpc", True))))
    out = device_to_screen(dev, spec).convert("RGB")
    if spec.get("warn") == "gamut":
        out = _mark(out, gamut_mask(rgb, spec), GAMUT_COLOR)
    elif spec.get("warn") == "tac" and dev.mode == "CMYK":
        out = _mark(out, _tac_mask(dev, spec), TAC_COLOR)
    return out


def _tac_mask(cmyk_img, spec):
    import numpy as np
    a = np.asarray(cmyk_img, dtype=np.uint16)
    return a.sum(axis=2) * (100.0 / 255.0) > float(spec.get("tac", 300))


def softproof_cmyk(cmyk_img, spec, rgb_for_gamut=None):
    """Echte CMYK-Werte (Ghostscript-Separation) -> Bildschirm."""
    out = device_to_screen(cmyk_img, spec).convert("RGB")
    if spec.get("warn") == "tac":
        out = _mark(out, _tac_mask(cmyk_img, spec), TAC_COLOR)
    elif spec.get("warn") == "gamut" and rgb_for_gamut is not None:
        g = rgb_for_gamut.convert("RGB")
        if g.size != out.size:
            g = g.resize(out.size)
        out = _mark(out, gamut_mask(g, spec), GAMUT_COLOR)
    return out


def can_separate(spec) -> bool:
    """CMYK-Weg möglich (CMYK-Profil und Ghostscript da)?"""
    if not spec or (spec.get("space") or "") != "CMYK":
        return False
    from . import platform as _platform
    return bool(_platform.ghostscript())


_SEP_CACHE: dict = {}


def separated_page(path: str, index: int, dpi: float, spec, password: str | None = None):
    """Seite mit Ghostscript separieren (wie die CMYK-Umwandlung „nur RGB/Grau“) und für den Bildschirm
        aufbereiten -> PIL RGB der ganzen Seite (CropBox, /Rotate berücksichtigt). Zwischengespeichert."""
    import shutil
    import tempfile
    from PIL import Image
    from . import cmyk
    st = os.stat(path)
    dpi = round(max(18.0, min(float(dpi), PROOF_MAX_DPI)))
    key = (os.path.realpath(path), st.st_mtime_ns, st.st_size, index, round(dpi, 1), spec_key(spec))
    hit = _SEP_CACHE.get(key)
    if hit is not None:
        return hit
    gs = cmyk.ghostscript()
    s = cmyk.ManipSettings(cmyk=True, cmyk_mode="rgb_only", target=spec["icc"],
                           intent=spec.get("intent", "relative"), bpc=bool(spec.get("bpc", True)))
    extra = ["-dUseCropBox", *cmyk._permit(s), *cmyk.color_args(s)]
    if password:
        extra.append(f"-sPDFPassword={password}")
    tmp = tempfile.mkdtemp(prefix="passermark-proof-")
    try:
        out = os.path.join(tmp, "p.tif")
        cmyk._render(gs, path, index, dpi, "tiff32nc", extra, out)
        c = Image.open(out)
        c.load()
        c = c.convert("CMYK") if c.mode != "CMYK" else c
        rgb = None
        if spec.get("warn") == "gamut":
            r = os.path.join(tmp, "r.png")
            cmyk._render(gs, path, index, dpi, "png16m", ["-dUseCropBox"] +
                         ([f"-sPDFPassword={password}"] if password else []), r)
            rgb = Image.open(r).convert("RGB")
        img = softproof_cmyk(c, spec, rgb)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    while len(_SEP_CACHE) >= 4:
        _SEP_CACHE.pop(next(iter(_SEP_CACHE)))
    _SEP_CACHE[key] = img
    return img


def proofed_render(page, scale: float, rotation: int, crop, spec, path: str | None = None, index: int = 0,
                   password: str | None = None):
    """Wie page.render(...), aber als Softproof -> PIL RGB. Mit CMYK-Profil und Ghostscript über die echte
        Separation, sonst über das Seitenbild."""
    from PIL import Image
    crop = tuple(float(c) for c in (crop or (0, 0, 0, 0)))
    if path and can_separate(spec):
        try:
            dpi = round(max(18.0, min(scale * 72.0, PROOF_MAX_DPI)))
            full = separated_page(path, index, dpi, spec, password)
            rot = rotation % 360
            if rot:
                full = full.transpose({90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180,
                                       270: Image.Transpose.ROTATE_90}[rot])
            import math
            # Größe genau wie pdfium (page.render): ganze Seite aufgerundet, Ausschnitt in Pixeln aufgerundet
            sw, sh = math.ceil(page.get_width() * scale), math.ceil(page.get_height() * scale)
            if rot in (90, 270):
                sw, sh = sh, sw
            cl, cb, cr, ct = (math.ceil(c * scale) for c in crop)
            w, h = max(1, sw - cl - cr), max(1, sh - cb - ct)
            fx, fy = full.width / sw, full.height / sh
            part = full.crop((int(round(cl * fx)), int(round(ct * fy)), int(round((cl + w) * fx)),
                              int(round((ct + h) * fy)))) if any(crop) else full
            return part.resize((w, h), Image.Resampling.LANCZOS) if (w, h) != part.size else part
        except Exception:
            pass                                    # z. B. Ghostscript-Fehler -> über das Seitenbild
    bmp = page.render(scale=scale, rotation=rotation % 360, crop=crop, may_draw_forms=True, draw_annots=True)
    try:
        img = bmp.to_pil().convert("RGB")
    finally:
        bmp.close()
    try:
        return softproof_rgb(img, spec)
    except Exception:
        return img                                  # defektes Profil: ohne Softproof
