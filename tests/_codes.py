# SPDX-License-Identifier: GPL-3.0-or-later
"""Codes in erzeugten PDFs wirklich lesen – für Tests.

QR-Code und EAN-13 mit OpenCV (wenn installiert: pip install opencv-python-headless; sonst werden die Lese-Tests
übersprungen). Code 128 kann OpenCV nicht: dafür ein kleiner eigener Leser, der eine Bildzeile in Balkenbreiten
zerlegt und mit der Code-128-Tabelle vergleicht (inkl. Prüfsumme).
"""
import numpy as np

try:
    import cv2                                        # noqa: F401
    HAVE_CV2 = True
except ImportError:                                   # pragma: no cover
    HAVE_CV2 = False

MM = 72 / 25.4


def page_gray(page, scale=6.0):
    return np.array(page.render(scale=scale).to_pil().convert("L"))


def crop_mm(img, scale, x, y, w, h, pad_px=40):
    """Ausschnitt (mm ab links oben) mit weißem Rand."""
    import cv2
    x0, y0 = int(x * MM * scale), int(y * MM * scale)
    x1, y1 = int((x + w) * MM * scale), int((y + h) * MM * scale)
    c = img[max(0, y0):y1, max(0, x0):x1]
    return cv2.copyMakeBorder(c, pad_px, pad_px, pad_px, pad_px, cv2.BORDER_CONSTANT, value=255)


def read_qr(img) -> list:
    import cv2
    out = []
    for det in (cv2.QRCodeDetectorAruco(), cv2.QRCodeDetector()):
        ok, texts, _pts, _ = det.detectAndDecodeMulti(img)
        if ok:
            out += [t for t in texts if t]
        if out:
            break
    return out


def read_ean(img) -> list:
    import cv2
    r = cv2.barcode.BarcodeDetector().detectAndDecodeWithType(img)
    if not r[0]:
        return []
    return [t for t, ty in zip(r[1], r[2]) if t and ty.startswith("EAN")]


# --------------------------------------------------------------------------- Code 128
def _table():
    from reportlab.graphics.barcode.code128 import _patterns
    tab = {}
    for v, p in _patterns.items():
        widths = tuple("abcd".index(ch.lower()) + 1 for ch in p)
        tab[widths] = v
    return tab


def _runs(row):
    """Lauflängen ab dem ersten Balken: [(ist_balken, breite_px), …]."""
    dark = row < 128
    out = []
    i, n = 0, len(dark)
    while i < n and not dark[i]:
        i += 1
    while i < n:
        j = i
        while j < n and dark[j] == dark[i]:
            j += 1
        out.append((bool(dark[i]), j - i))
        i = j
    if out and not out[-1][0]:
        out.pop()                                     # weißer Rest rechts
    return out


def read_code128(img) -> str:
    """Code 128 aus der mittleren Zeile eines Ausschnitts lesen; '' wenn nicht lesbar."""
    tab = _table()
    h = img.shape[0]
    for frac in (0.5, 0.4, 0.6, 0.3):
        runs = [w for _b, w in _runs(img[int(h * frac)])]
        if len(runs) < 6 + 6 + 7:
            continue
        vals = []
        k = 0
        ok = True
        while k + 6 <= len(runs):
            grp = runs[k:k + 6]
            mod = sum(grp) / 11.0
            widths = tuple(max(1, min(4, int(round(w / mod)))) for w in grp)
            if k + 7 <= len(runs) and len(runs) - k == 7:    # Stopzeichen: 7 Läufe, 13 Module
                vals.append(106)
                break
            v = tab.get(widths)
            if v is None:
                ok = False
                break
            vals.append(v)
            k += 6
        if not ok or len(vals) < 3 or vals[0] not in (103, 104, 105) or vals[-1] != 106:
            continue
        data, chk = vals[1:-2], vals[-2]
        if (vals[0] + sum((i + 1) * v for i, v in enumerate(data))) % 103 != chk:
            continue
        return _decode(vals[0], data)
    return ""


def _decode(start, data) -> str:
    code = {103: "A", 104: "B", 105: "C"}[start]
    out = []
    for v in data:
        if code == "C":
            if v < 100:
                out.append(f"{v:02d}")
            elif v == 100:
                code = "B"
            elif v == 101:
                code = "A"
            continue
        if v == 99:
            code = "C"
        elif v == 100 and code == "A":
            code = "B"
        elif v == 101 and code == "B":
            code = "A"
        elif v < 96:
            if code == "B":
                out.append(chr(v + 32))
            else:
                out.append(chr(v + 32) if v < 64 else chr(v - 64))
    return "".join(out)
