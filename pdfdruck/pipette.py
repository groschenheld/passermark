# SPDX-License-Identifier: GPL-3.0-or-later
"""Farbpipette (1.18.14): was liegt an einer Stelle der Seite?

- **Definiert**: Farbe des obersten Objekts an der Stelle, so wie sie im PDF steht – RGB, CMYK, Grau, Lab,
  Sonderfarbe (Separation/DeviceN mit Tonwert) oder der Pixelwert eines Bildes.
- **Im Druck**: Farbauftrag je Kanal (C, M, Y, K in %) und gesamt – Ghostscript separiert die Seite mit dem Profil der
  Druckbedingung wie die CMYK-Umwandlung „nur RGB/Grau“: vorhandenes CMYK bleibt 1:1, RGB/Grau/Lab/Sonderfarben
  werden umgerechnet. Überdrucken, Transparenz und Bilder sind dabei schon verrechnet.
- **Bildschirm**: die angezeigte Farbe (RGB).

Ohne Qt – die Oberfläche (gui/pipettedialog.py) ruft sample() in einem Hintergrund-Thread auf.
"""
from __future__ import annotations

import hashlib
import io
import os
import shutil
import tempfile
from dataclasses import dataclass, field

from .l10n import tr

MAX_PX = 3000                  # längste Seite der Separation in Pixeln (Plakate werden gröber gerastert)
DPI = 150
_INK_CACHE: dict = {}          # (Datei-Hash, Seite, Profil, Intent, dpi) -> (numpy CMYK, Breite, Höhe)
_SCREEN_CACHE: dict = {}
_FILES: dict = {}              # Datei-Hash -> temporäre PDF für Ghostscript


@dataclass
class Sample:
    page: int = 0
    x: float = 0.0
    y: float = 0.0
    kind: str = ""             # text | path | image | shading | form | "" (nichts gefunden = Papier)
    paint: str = "fill"        # fill | stroke (Pfad nur mit Kontur)
    space: str = ""            # RGB | CMYK | Gray | Lab | Separation | DeviceN | Indexed | Pattern
    values: list = field(default_factory=list)   # 0..1 je Kanal (Lab: L 0..100, a, b)
    spot: str = ""             # Name(n) der Sonderfarbe(n)
    icc: bool = False          # Farbraum über ICC-Profil festgelegt (ICCBased)
    detail: str = ""           # z. B. „Bild 1200 × 800 px, 300 ppi“
    sure: bool = True          # Objekt passt zur angezeigten Farbe (sonst: ungefähr)
    ink: list | None = None    # C, M, Y, K in % im Druck
    profile: str = ""
    limit: int = 0             # Richtwert Gesamtfarbauftrag
    screen: tuple = ()         # RGB 0..255 wie angezeigt
    notes: list = field(default_factory=list)

    @property
    def ink_total(self) -> float:
        return float(sum(self.ink)) if self.ink else 0.0

    def as_cmyk(self) -> list | None:
        """Zum Wiederverwenden: definiertes CMYK, sonst der Farbauftrag im Druck (0..1)."""
        if self.space == "CMYK" and len(self.values) == 4:
            return [float(v) for v in self.values]
        if self.ink:
            return [round(v) / 100.0 for v in self.ink]
        return None

    def as_rgb(self) -> list | None:
        """Zum Wiederverwenden: definiertes RGB, sonst die Bildschirmfarbe (0..1)."""
        if self.space == "RGB" and len(self.values) == 3:
            return [float(v) for v in self.values]
        if self.space == "Gray" and len(self.values) == 1:
            return [float(self.values[0])] * 3
        if self.screen:
            return [v / 255.0 for v in self.screen]
        return None

    def to_dict(self) -> dict:
        return {"page": self.page + 1, "x_mm": round(self.x / 72 * 25.4, 2), "y_mm": round(self.y / 72 * 25.4, 2),
                "object": self.kind, "paint": self.paint, "space": self.space, "values": self.values,
                "spot": self.spot, "icc": self.icc, "detail": self.detail, "sure": self.sure,
                "ink": self.ink, "ink_total": round(self.ink_total, 1) if self.ink else None,
                "profile": self.profile, "limit": self.limit, "screen": list(self.screen), "notes": self.notes}


# --------------------------------------------------------------------------- #
# Farbräume aus dem Inhaltsstrom
# --------------------------------------------------------------------------- #
_DEVICE = {"/DeviceGray": ("Gray", 1), "/DeviceRGB": ("RGB", 3), "/DeviceCMYK": ("CMYK", 4),
           "/G": ("Gray", 1), "/RGB": ("RGB", 3), "/CMYK": ("CMYK", 4), "/CalGray": ("Gray", 1), "/CalRGB": ("RGB", 3)}


def _space(obj, res) -> dict:
    """Farbraum (Name oder Array, ggf. aus /Resources/ColorSpace) -> {"space", "n", "spot", "icc", "base"}."""
    import pikepdf
    if isinstance(obj, pikepdf.Name):
        name = str(obj)
        if name in _DEVICE:
            sp, n = _DEVICE[name]
            return {"space": sp, "n": n, "spot": "", "icc": False}
        if name == "/Pattern":
            return {"space": "Pattern", "n": 0, "spot": "", "icc": False}
        try:
            obj = res.ColorSpace[name]
        except (AttributeError, KeyError, TypeError):
            return {"space": name.lstrip("/"), "n": 0, "spot": "", "icc": False}
        if isinstance(obj, pikepdf.Name):
            return _space(obj, res)
    try:
        fam = str(obj[0])
    except (TypeError, IndexError, KeyError):
        return {"space": "?", "n": 0, "spot": "", "icc": False}
    if fam == "/ICCBased":
        n = int(obj[1].get("/N", 3))
        return {"space": {1: "Gray", 3: "RGB", 4: "CMYK"}.get(n, "ICC"), "n": n, "spot": "", "icc": True}
    if fam in ("/CalRGB", "/CalGray"):
        return _space(pikepdf.Name(fam), res)
    if fam == "/Lab":
        return {"space": "Lab", "n": 3, "spot": "", "icc": False}
    if fam == "/Separation":
        return {"space": "Separation", "n": 1, "spot": str(obj[1]).lstrip("/"), "icc": False}
    if fam == "/DeviceN":
        names = [str(v).lstrip("/") for v in obj[1]]
        return {"space": "DeviceN", "n": len(names), "spot": " + ".join(names), "icc": False}
    if fam == "/Indexed":
        base = _space(obj[1], res)
        return {"space": "Indexed", "n": 1, "spot": "", "icc": base.get("icc", False), "base": base["space"]}
    if fam == "/Pattern":
        return {"space": "Pattern", "n": 0, "spot": "", "icc": False}
    return {"space": fam.lstrip("/"), "n": 0, "spot": "", "icc": False}


def _nums(ops) -> list:
    """Zahlen-Operanden (pikepdf liefert int/Decimal); Musternamen bleiben weg."""
    out = []
    for v in ops:
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            pass
    return out


def _initial(sp: dict) -> list:
    if sp["space"] == "CMYK":
        return [0.0, 0.0, 0.0, 1.0]
    if sp["space"] in ("Separation", "DeviceN"):
        return [1.0] * max(1, sp["n"])
    return [0.0] * max(1, sp["n"])


def page_colors(data: bytes, page_index: int) -> dict:
    """Farben je Objekt der Seite in pdfiums Reihenfolge:
        {("path", n): {"fill": (Raum, Werte), "stroke": (…), "paint": "fill"|"stroke"},
         ("text", n): {"fill": …, "stroke": …, "mode": Tr}, ("image", n): {"name": XObject-Name | None}}."""
    import pikepdf
    from .editing import PATH_PAINT_OPS, PATH_CONSTR_OPS, SHOW_OPS, _show_nonempty
    gray = ({"space": "Gray", "n": 1, "spot": "", "icc": False}, [0.0])
    out = {}
    pdf = pikepdf.open(io.BytesIO(data))
    try:
        pg = pdf.pages[page_index]
        res = pg.obj.get("/Resources")
        xobj = res.get("/XObject") if res is not None else None
        fill, stroke, tr_mode, stack = gray, gray, 0, []
        in_bt, has_path, pord, tord, iord = False, False, -1, -1, -1
        for ins in pikepdf.parse_content_stream(pg):
            op = str(getattr(ins, "operator", ""))
            ops = list(getattr(ins, "operands", []) or [])
            if op == "INLINE IMAGE":
                iord += 1
                out[("image", iord)] = {"name": None}
                continue
            try:
                if op == "q":
                    stack.append((fill, stroke, tr_mode))
                elif op == "Q" and stack:
                    fill, stroke, tr_mode = stack.pop()
                elif op == "g":
                    fill = ({"space": "Gray", "n": 1, "spot": "", "icc": False}, [float(ops[0])])
                elif op == "G":
                    stroke = ({"space": "Gray", "n": 1, "spot": "", "icc": False}, [float(ops[0])])
                elif op == "rg":
                    fill = ({"space": "RGB", "n": 3, "spot": "", "icc": False}, [float(v) for v in ops[:3]])
                elif op == "RG":
                    stroke = ({"space": "RGB", "n": 3, "spot": "", "icc": False}, [float(v) for v in ops[:3]])
                elif op == "k":
                    fill = ({"space": "CMYK", "n": 4, "spot": "", "icc": False}, [float(v) for v in ops[:4]])
                elif op == "K":
                    stroke = ({"space": "CMYK", "n": 4, "spot": "", "icc": False}, [float(v) for v in ops[:4]])
                elif op == "cs":
                    sp = _space(ops[0], res)
                    fill = (sp, _initial(sp))
                elif op == "CS":
                    sp = _space(ops[0], res)
                    stroke = (sp, _initial(sp))
                elif op in ("sc", "scn"):
                    nums = _nums(ops)
                    fill = (fill[0], nums or fill[1])
                elif op in ("SC", "SCN"):
                    nums = _nums(ops)
                    stroke = (stroke[0], nums or stroke[1])
                elif op == "Tr" and ops:
                    tr_mode = int(ops[0])
            except (TypeError, ValueError, IndexError):
                pass
            if op == "BT":
                in_bt = True
            elif op == "ET":
                in_bt = False
            elif op == "Do":
                xo = xobj.get(ops[0]) if xobj is not None and ops else None
                if xo is not None and str(xo.get("/Subtype", "")) == "/Image":
                    iord += 1
                    out[("image", iord)] = {"name": str(ops[0])}
            elif in_bt and op in SHOW_OPS and _show_nonempty(ins):
                tord += 1
                out[("text", tord)] = {"fill": fill, "stroke": stroke, "mode": tr_mode}
            elif not in_bt and op in PATH_CONSTR_OPS:
                has_path = True
            elif not in_bt and op in PATH_PAINT_OPS:
                if has_path:
                    pord += 1
                    out[("path", pord)] = {"fill": fill, "stroke": stroke,
                                           "paint": "stroke" if op in ("S", "s") else "fill"}
                has_path = False
            elif op == "n":
                has_path = False
    finally:
        pdf.close()
    return out


# --------------------------------------------------------------------------- #
# Seite rendern (Bildschirm) und separieren (Druck)
# --------------------------------------------------------------------------- #
def _hash(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def _pixel(x: float, y: float, crop: tuple, rot: int, size: tuple) -> tuple:
    """Seitenpunkt (pt) -> Pixel (Spalte, Zeile) im gerenderten Bild (CropBox, /Rotate im Uhrzeigersinn)."""
    W, H = size
    cx0, cy0, cx1, cy1 = crop
    u = (x - cx0) / max(1e-6, cx1 - cx0)
    v = (y - cy0) / max(1e-6, cy1 - cy0)
    rot %= 360
    if rot == 0:
        col, row = u * W, (1 - v) * H
    elif rot == 90:                     # im Uhrzeigersinn: links oben wandert nach rechts oben
        col, row = v * W, u * H
    elif rot == 180:
        col, row = (1 - u) * W, v * H
    else:
        col, row = (1 - v) * W, (1 - u) * H
    return min(W - 1, max(0, int(col))), min(H - 1, max(0, int(row)))


def _geometry(data: bytes, page_index: int) -> tuple:
    import pypdfium2 as pdfium
    d = pdfium.PdfDocument(data)
    try:
        pg = d[page_index]
        return tuple(pg.get_cropbox()), int(pg.get_rotation()), tuple(pg.get_size())
    finally:
        d.close()


def screen_color(data: bytes, page_index: int, x: float, y: float) -> tuple:
    """Angezeigte Farbe (RGB 0..255) – pdfium, 2 px je pt (bei großen Seiten weniger)."""
    import numpy as np
    import pypdfium2 as pdfium
    key = (_hash(data), page_index)
    hit = _SCREEN_CACHE.get(key)
    if hit is None:
        d = pdfium.PdfDocument(data)
        try:
            pg = d[page_index]
            w, h = pg.get_size()
            scale = min(2.0, MAX_PX / max(w, h, 1))
            img = pg.render(scale=scale, may_draw_forms=True).to_pil().convert("RGB")
        finally:
            d.close()
        hit = np.asarray(img)
        while len(_SCREEN_CACHE) >= 3:
            _SCREEN_CACHE.pop(next(iter(_SCREEN_CACHE)))
        _SCREEN_CACHE[key] = hit
    crop, rot, _size = _geometry(data, page_index)
    col, row = _pixel(x, y, crop, rot, (hit.shape[1], hit.shape[0]))
    return tuple(int(v) for v in hit[row, col][:3])


def _temp_pdf(data: bytes) -> str:
    key = _hash(data)
    p = _FILES.get(key)
    if p and os.path.isfile(p):
        return p
    d = tempfile.mkdtemp(prefix="passermark-pipette-")
    p = os.path.join(d, "seite.pdf")
    with open(p, "wb") as fh:
        fh.write(data)
    while len(_FILES) >= 3:
        old = _FILES.pop(next(iter(_FILES)))
        shutil.rmtree(os.path.dirname(old), ignore_errors=True)
    _FILES[key] = p
    return p


def ink_color(data: bytes, page_index: int, x: float, y: float, icc: str, intent: str = "relative",
              password: str = "") -> list:
    """Farbauftrag im Druck an der Stelle: [C, M, Y, K] in % (Ghostscript-Separation mit dem Profil)."""
    import numpy as np
    from PIL import Image
    from . import cmyk
    crop, rot, (pw, ph) = _geometry(data, page_index)
    dpi = round(min(DPI, MAX_PX * 72.0 / max(pw, ph, 1)), 1)
    key = (_hash(data), page_index, icc, intent, dpi)
    arr = _INK_CACHE.get(key)
    if arr is None:
        gs = cmyk.ghostscript()
        if not gs:
            raise RuntimeError(tr("Für den Farbauftrag wird Ghostscript benötigt."))
        s = cmyk.ManipSettings(cmyk=True, cmyk_mode="rgb_only", target=icc, intent=intent or "relative")
        extra = ["-dUseCropBox", *cmyk._permit(s), *cmyk.color_args(s)]
        if password:
            extra.append(f"-sPDFPassword={password}")
        tmp = tempfile.mkdtemp(prefix="passermark-ink-")
        try:
            out = os.path.join(tmp, "p.tif")
            cmyk._render(gs, _temp_pdf(data), page_index, dpi, "tiff32nc", extra, out)
            im = Image.open(out)
            im.load()
            arr = np.asarray(im.convert("CMYK") if im.mode != "CMYK" else im)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        while len(_INK_CACHE) >= 4:
            _INK_CACHE.pop(next(iter(_INK_CACHE)))
        _INK_CACHE[key] = arr
    col, row = _pixel(x, y, crop, rot, (arr.shape[1], arr.shape[0]))
    return [round(float(v) * 100.0 / 255.0, 1) for v in arr[row, col][:4]]


# --------------------------------------------------------------------------- #
# Objekt an der Stelle
# --------------------------------------------------------------------------- #
def _object_at(data: bytes, page_index: int, x: float, y: float, screen: tuple) -> tuple:
    """Oberstes Objekt, dessen Rahmen die Stelle enthält und dessen Farbe zur Anzeige passt
        -> (Art, Ordinalzahl je Art, pdfium-Index, sicher?, Matrix bei Bildern) oder ("", -1, -1, True, None)."""
    import ctypes
    import pypdfium2 as pdfium
    import pypdfium2.raw as r
    kinds = {r.FPDF_PAGEOBJ_TEXT: "text", r.FPDF_PAGEOBJ_PATH: "path", r.FPDF_PAGEOBJ_IMAGE: "image",
             r.FPDF_PAGEOBJ_SHADING: "shading", r.FPDF_PAGEOBJ_FORM: "form"}
    d = pdfium.PdfDocument(data)
    try:
        page = d[page_index]
        n = r.FPDFPage_CountObjects(page.raw)
        objs, counts = [], {}
        for i in range(n):
            o = r.FPDFPage_GetObject(page.raw, i)
            k = kinds.get(r.FPDFPageObj_GetType(o), "")
            ordn = counts.get(k, -1) + 1
            counts[k] = ordn
            objs.append((i, o, k, ordn))
        tol = 0.6
        first = None
        for i, o, k, ordn in reversed(objs):
            if not k:
                continue
            L, B, R, T = ctypes.c_float(), ctypes.c_float(), ctypes.c_float(), ctypes.c_float()
            if not r.FPDFPageObj_GetBounds(o, L, B, R, T):
                continue
            if not (L.value - tol <= x <= R.value + tol and B.value - tol <= y <= T.value + tol):
                continue
            mat = None
            if k == "image":
                m = r.FS_MATRIX()
                if r.FPDFPageObj_GetMatrix(o, m):
                    mat = (m.a, m.b, m.c, m.d, m.e, m.f)
                return k, ordn, i, True, mat               # Bilder sind rechteckig: Rahmen = Fläche
            if k in ("shading", "form"):
                if first is None:
                    first = (k, ordn, i, False, None)
                continue
            rr, gg, bb, aa = ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint()
            ok = False
            if k == "path":
                fm, st = ctypes.c_int(), ctypes.c_int()
                r.FPDFPath_GetDrawMode(o, fm, st)
                if fm.value:
                    ok = bool(r.FPDFPageObj_GetFillColor(o, rr, gg, bb, aa))
                elif st.value:
                    ok = bool(r.FPDFPageObj_GetStrokeColor(o, rr, gg, bb, aa))
            else:
                ok = bool(r.FPDFPageObj_GetFillColor(o, rr, gg, bb, aa))
            if first is None:
                first = (k, ordn, i, False, None)
            if ok and screen and max(abs(rr.value - screen[0]), abs(gg.value - screen[1]),
                                     abs(bb.value - screen[2])) <= 48:
                return k, ordn, i, True, None
        if first is not None and screen and min(screen) >= 248:
            return "", -1, -1, True, None           # nichts passt und es ist hell: Papier (z. B. in einer Kontur)
        return first or ("", -1, -1, True, None)
    finally:
        d.close()


def _image_pixel(data: bytes, page_index: int, info: dict, mat: tuple, x: float, y: float) -> tuple:
    """Pixelwert eines Bildes an der Stelle -> (Raum, Werte 0..1, ICC?, Detail)."""
    import pikepdf
    if not mat:
        return "", [], False, ""
    a, b, c, d_, e, f = mat
    det = a * d_ - b * c
    if abs(det) < 1e-9:
        return "", [], False, ""
    px, py = x - e, y - f
    u = (px * d_ - py * c) / det                       # Einheitsquadrat des Bildes
    v = (py * a - px * b) / det
    pdf = pikepdf.open(io.BytesIO(data))
    try:
        pg = pdf.pages[page_index]
        if not info.get("name"):
            return "", [], False, tr("kleines eingebettetes Bild – Werte aus der Separation")
        raw = pg.obj.Resources.XObject[info["name"]]
        img = pikepdf.PdfImage(raw)
        W, H = int(img.width), int(img.height)
        ppi = W / max(1e-6, (abs(a) + abs(c)) / 72.0)
        detail = tr("Bild {0} × {1} px, {2} ppi").format(W, H, int(round(ppi)))
        sp = _space(raw.get("/ColorSpace", pikepdf.Name("/DeviceGray")), pg.obj.get("/Resources")) \
            if "/ColorSpace" in raw else {"space": "", "icc": False, "spot": ""}
        try:
            pil = img.as_pil_image()
        except Exception:                                  # noqa: BLE001 – exotische Kodierung
            return sp["space"], [], sp.get("icc", False), detail
        col = min(W - 1, max(0, int(u * W)))
        row = min(H - 1, max(0, int((1 - v) * H)))
        mode = pil.mode
        if mode == "P":
            pil, mode = pil.convert("RGB"), "RGB"
        if mode in ("1", "I;16", "I", "F"):
            pil, mode = pil.convert("L"), "L"
        val = pil.getpixel((col, row))
        vals = list(val) if isinstance(val, (tuple, list)) else [val]
        space = {"L": "Gray", "RGB": "RGB", "RGBA": "RGB", "CMYK": "CMYK", "LA": "Gray"}.get(mode, sp["space"])
        vals = [v / 255.0 for v in vals][:{"Gray": 1, "RGB": 3, "CMYK": 4}.get(space, len(vals))]
        if sp["space"] == "Separation":
            space, vals = "Separation", [1.0 - vals[0]] if vals else vals   # Tonwert: 1 = volle Farbe
        return space, vals, bool(sp.get("icc")), detail
    finally:
        pdf.close()


# --------------------------------------------------------------------------- #
def sample(data: bytes, page_index: int, x: float, y: float, target=None, password: str = "") -> Sample:
    """Alles zur Stelle (x, y in pt, PDF-Koordinaten der Seite). target = colorcheck.Target (Druckbedingung) oder
        None (dann ohne Farbauftrag)."""
    s = Sample(page=page_index, x=x, y=y)
    try:
        s.screen = screen_color(data, page_index, x, y)
    except Exception as e:                                 # noqa: BLE001
        s.notes.append(str(e))
    kind, ordn, _idx, sure, mat = _object_at(data, page_index, x, y, s.screen)
    s.kind, s.sure = kind, sure
    if kind in ("text", "path"):
        info = page_colors(data, page_index).get((kind, ordn))
        if info:
            use = info["fill"]
            if kind == "path" and info.get("paint") == "stroke":
                use, s.paint = info["stroke"], "stroke"
            elif kind == "text" and info.get("mode") in (1, 5):
                use, s.paint = info["stroke"], "stroke"
            sp, vals = use
            s.space, s.values, s.spot, s.icc = sp["space"], [round(float(v), 4) for v in vals], sp.get("spot", ""), \
                bool(sp.get("icc"))
            if sp["space"] == "Indexed":
                s.detail = tr("indizierte Farbe ({0})").format(sp.get("base", ""))
        else:
            s.sure = False
            s.notes.append(tr("Farbe des Objekts nicht eindeutig zuordenbar – Werte aus Anzeige und Separation."))
    elif kind == "image":
        info = page_colors(data, page_index).get(("image", ordn)) or {}
        try:
            s.space, s.values, s.icc, s.detail = _image_pixel(data, page_index, info, mat, x, y)
            s.values = [round(float(v), 4) for v in s.values]
        except Exception as e:                             # noqa: BLE001
            s.notes.append(tr("Bildpixel nicht lesbar: {0}").format(e))
    elif kind in ("shading", "form"):
        s.detail = tr("Verlauf") if kind == "shading" else tr("Gruppe/Form – Werte aus der Separation")
    if target is not None and getattr(target, "icc", "") and getattr(target, "space", "CMYK") == "CMYK":
        s.profile = target.name
        s.limit = int(getattr(target, "limit", 0) or 0)
        s.ink = ink_color(data, page_index, x, y, target.icc, target.intent, password)
    return s


def format_values(s: Sample) -> str:
    """Definierte Farbe als kurzer Text: „CMYK 0 / 40 / 100 / 0 (140 %)“, „RGB 245 / 167 / 35 · #F5A723“ …"""
    v = s.values
    if not s.space:
        return tr("Papier (kein Objekt)") if not s.kind else "–"
    if s.space == "CMYK" and len(v) == 4:
        pct = [round(x * 100) for x in v]
        return "CMYK " + " / ".join(str(p) for p in pct) + f"  ({sum(pct)} %)"
    if s.space == "RGB" and len(v) == 3:
        rgb = [round(x * 255) for x in v]
        return "RGB " + " / ".join(str(p) for p in rgb) + "  · #" + "".join(f"{p:02X}" for p in rgb)
    if s.space == "Gray" and v:
        return tr("Grau {0} % Schwarz").format(round((1 - v[0]) * 100))
    if s.space == "Lab" and len(v) == 3:
        return "Lab " + " / ".join(f"{x:.0f}" for x in v)
    if s.space in ("Separation", "DeviceN"):
        tints = " / ".join(f"{round(x * 100)} %" for x in v)
        return tr("Sonderfarbe {0}: {1}").format(s.spot or "?", tints)
    return s.space + (" " + " / ".join(f"{x:.2f}" for x in v) if v else "")
