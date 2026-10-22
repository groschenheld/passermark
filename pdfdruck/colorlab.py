# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Colour measurement and materials (papers) – no Qt.

* Lab / XYZ (D50) maths, ΔE 2000
* media white of an ICC profile (what LittleCMS gives for "no ink", absolute colorimetric)
* measurements: CGATS files (i1Profiler, ArgyllCMS, ColorPort …), ArgyllCMS spotread output
* materials: registered papers with measured paper white, surface, weight and their profile per printer
* suggestions: which installed profile fits a paper (ΔE of the paper white, surface, printer) and which
  conversion fits a document (output intent of the file -> profile of the paper)

Materials live in the admin defaults ("materials"), like the colour profiles – only the administrator
registers them; measuring needs the instrument and stays in the program (not in the CLI).
"""
from __future__ import annotations

import glob
import math
import os
import re
import shutil

from .l10n import tr

D50 = (96.422, 100.0, 82.521)
SURFACES = ("", "coated", "uncoated", "matte", "glossy", "silk", "recycled", "special")


def surface_label(s: str) -> str:
    return {"": tr("unbekannt"), "coated": tr("gestrichen"), "uncoated": tr("ungestrichen"),
            "matte": tr("matt gestrichen"), "glossy": tr("glänzend (Fotopapier)"), "silk": tr("seidenmatt"),
            "recycled": tr("Recycling/Natur"), "special": tr("Spezial (Folie, Karton, farbig …)")}.get(s, s)


# --------------------------------------------------------------------------- #
# Farbrechnung
# --------------------------------------------------------------------------- #
def _f(t):
    return t ** (1 / 3) if t > (6 / 29) ** 3 else t / (3 * (6 / 29) ** 2) + 4 / 29


def _fi(t):
    return t ** 3 if t > 6 / 29 else 3 * (6 / 29) ** 2 * (t - 4 / 29)


def xyz_to_lab(xyz, white=D50):
    fx, fy, fz = (_f(xyz[i] / white[i]) for i in range(3))
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def lab_to_xyz(lab, white=D50):
    L, a, b = lab
    fy = (L + 16) / 116
    fx, fz = fy + a / 500, fy - b / 200
    return (white[0] * _fi(fx), white[1] * _fi(fy), white[2] * _fi(fz))


def delta_e(lab1, lab2) -> float:
    """CIEDE2000."""
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    C1, C2 = math.hypot(a1, b1), math.hypot(a2, b2)
    Cm = (C1 + C2) / 2
    G = 0.5 * (1 - math.sqrt(Cm ** 7 / (Cm ** 7 + 25 ** 7))) if Cm else 0.0
    a1p, a2p = a1 * (1 + G), a2 * (1 + G)
    C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360 if C1p else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360 if C2p else 0.0
    dLp, dCp = L2 - L1, C2p - C1p
    if C1p * C2p == 0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    else:
        dhp = h2p - h1p - 360 if h2p > h1p else h2p - h1p + 360
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp / 2))
    Lm, Cmp = (L1 + L2) / 2, (C1p + C2p) / 2
    if C1p * C2p == 0:
        hm = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hm = (h1p + h2p) / 2
    else:
        hm = (h1p + h2p + 360) / 2 if h1p + h2p < 360 else (h1p + h2p - 360) / 2
    T = (1 - 0.17 * math.cos(math.radians(hm - 30)) + 0.24 * math.cos(math.radians(2 * hm))
         + 0.32 * math.cos(math.radians(3 * hm + 6)) - 0.20 * math.cos(math.radians(4 * hm - 63)))
    dth = 30 * math.exp(-(((hm - 275) / 25) ** 2))
    Rc = 2 * math.sqrt(Cmp ** 7 / (Cmp ** 7 + 25 ** 7)) if Cmp else 0.0
    Sl = 1 + 0.015 * (Lm - 50) ** 2 / math.sqrt(20 + (Lm - 50) ** 2)
    Sc, Sh = 1 + 0.045 * Cmp, 1 + 0.015 * Cmp * T
    Rt = -math.sin(math.radians(2 * dth)) * Rc
    return math.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2 + Rt * (dCp / Sc) * (dHp / Sh))


def fmt_lab(lab) -> str:
    return "L {0:.1f}  a {1:+.1f}  b {2:+.1f}".format(*lab) if lab else "–"


def mean_lab(labs):
    labs = [tuple(x) for x in labs if x]
    if not labs:
        return None
    return tuple(round(sum(x[i] for x in labs) / len(labs), 2) for i in range(3))


# --------------------------------------------------------------------------- #
# ICC-Profile
# --------------------------------------------------------------------------- #
_WHITE_CACHE: dict = {}


def profile_space(path: str) -> str:
    from .colorconv import icc_colorspace
    return icc_colorspace(path)


def profile_desc(path: str) -> str:
    try:
        from PIL import ImageCms
        d = (ImageCms.getProfileDescription(ImageCms.getOpenProfile(path)) or "").strip()
        if d:
            return d
    except Exception:
        pass
    return os.path.splitext(os.path.basename(path))[0]


def profile_white(path: str):
    """Papierweiß, wie das Profil es beschreibt (Gerätewert „keine Farbe“, absolut farbmetrisch) – Lab D50 oder None."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = (os.path.realpath(path), st.st_mtime_ns, st.st_size)
    if key in _WHITE_CACHE:
        return _WHITE_CACHE[key]
    lab = None
    try:
        from PIL import Image, ImageCms
        space = profile_space(path)
        mode, val = {"CMYK": ("CMYK", (0, 0, 0, 0)), "RGB": ("RGB", (255, 255, 255)), "Gray": ("L", 255)}[space]
        tf = ImageCms.buildTransform(ImageCms.getOpenProfile(path), ImageCms.createProfile("LAB", 5000), mode, "LAB",
                                     renderingIntent=ImageCms.Intent.ABSOLUTE_COLORIMETRIC)
        px = ImageCms.applyTransform(Image.new(mode, (4, 4), val), tf).getpixel((0, 0))
        lab = (round(px[0] * 100 / 255, 1), float(px[1] - 128), float(px[2] - 128))
    except Exception:
        lab = None
    _WHITE_CACHE[key] = lab
    return lab


_SURF_RX = [
    ("uncoated", re.compile(r"uncoat|ungestr|fogra\s*(29|47|52)|\bpt4\b|\bps5\b|naturpap|\boffset\b|bond|plain", re.I)),
    ("matte", re.compile(r"\bmatt|matte|velvet", re.I)),
    ("glossy", re.compile(r"gloss|glanz|glänz|photo|foto|lustre|luster|semigloss|premium.?glossy", re.I)),
    ("silk", re.compile(r"\bsilk|seiden|satin", re.I)),
    ("recycled", re.compile(r"recycl|umwelt", re.I)),
    ("special", re.compile(r"\blwc\b|\bsc-?b?\b|newspaper|zeitung|fogra\s*(45|54)|label|folie|film|vinyl", re.I)),
    ("coated", re.compile(r"(?<!un)coated|gestrichen|fogra\s*(27|39|51)|\bpt[12]\b|isocoated|pso\s*coated|gracol", re.I)),
]


def guess_surface(text: str) -> str:
    """Oberfläche aus Profilname/Datei raten (FOGRA-Nummern, coated/uncoated …) – "" = unbekannt."""
    for name, rx in _SURF_RX:
        if rx.search(text or ""):
            return name
    return ""


def _surface_group(s: str) -> str:
    return {"matte": "coated", "silk": "coated", "glossy": "coated", "recycled": "uncoated"}.get(s, s)


# --------------------------------------------------------------------------- #
# Messdaten einlesen
# --------------------------------------------------------------------------- #
RX_LAB = re.compile(r"Lab:\s*(-?\d+(?:\.\d+)?)[ ,]+(-?\d+(?:\.\d+)?)[ ,]+(-?\d+(?:\.\d+)?)")
RX_XYZ = re.compile(r"XYZ:\s*(-?\d+(?:\.\d+)?)[ ,]+(-?\d+(?:\.\d+)?)[ ,]+(-?\d+(?:\.\d+)?)")


def parse_lab_text(text: str):
    """Freie Eingabe oder Messprotokoll: „95.1 0.4 -2.9“, „L=95,1 a=0,4 b=-2,9“ oder Zeilen mit „Lab: …“ ->
        Lab oder None (Komma als Dezimalzeichen erlaubt)."""
    m = RX_LAB.search(text or "")
    if m:
        return tuple(float(x) for x in m.groups())
    nums = re.findall(r"-?\d+(?:[.,]\d+)?", (text or "").replace(";", " "))
    if len(nums) >= 3:
        try:
            lab = tuple(float(n.replace(",", ".")) for n in nums[:3])
        except ValueError:
            return None
        if 0 <= lab[0] <= 100 and all(-128 <= v <= 128 for v in lab[1:]):
            return lab
    return None


def parse_measurements(text: str) -> list:
    """Alle Messwerte eines spotread-Protokolls (oder einer Liste) -> [Lab, …]."""
    out = [tuple(float(x) for x in m.groups()) for m in RX_LAB.finditer(text or "")]
    if out:
        return out
    if "Lab" not in (text or "") and "XYZ:" in (text or ""):
        return [xyz_to_lab(tuple(float(x) for x in m.groups())) for m in RX_XYZ.finditer(text)]
    return []


def _cgats_rows(text: str):
    fields, rows, mode = [], [], ""
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        u = line.upper()
        if u.startswith("BEGIN_DATA_FORMAT"):
            mode, fields = "fmt", []
            continue
        if u.startswith("END_DATA_FORMAT"):
            mode = ""
            continue
        if u.startswith("BEGIN_DATA"):
            mode = "data"
            continue
        if u.startswith("END_DATA"):
            if rows and fields:
                yield fields, rows
            mode, rows = "", []
            continue
        parts = re.findall(r'"[^"]*"|\S+', line)
        if mode == "fmt":
            fields += [p.strip('"').upper() for p in parts]
        elif mode == "data" and fields:
            rows.append([p.strip('"') for p in parts])


def _num(v):
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        return None


def parse_cgats(text: str) -> list:
    """CGATS-Messdatei (i1Profiler, ArgyllCMS .ti3, ColorPort …) -> [{"name", "lab", "device": {…}}]."""
    out = []
    for fields, rows in _cgats_rows(text):
        idx = {f: i for i, f in enumerate(fields)}
        has_lab = all(k in idx for k in ("LAB_L", "LAB_A", "LAB_B"))
        has_xyz = all(k in idx for k in ("XYZ_X", "XYZ_Y", "XYZ_Z"))
        if not (has_lab or has_xyz):
            continue
        for r in rows:
            if len(r) < len(fields):
                continue
            if has_lab:
                lab = tuple(_num(r[idx[k]]) for k in ("LAB_L", "LAB_A", "LAB_B"))
            else:
                xyz = tuple(_num(r[idx[k]]) for k in ("XYZ_X", "XYZ_Y", "XYZ_Z"))
                lab = xyz_to_lab(xyz) if None not in xyz else (None,)
            if None in lab:
                continue
            dev = {f: _num(r[i]) for f, i in idx.items()
                   if f.startswith(("CMYK_", "RGB_", "GRAY_")) and _num(r[i]) is not None}
            name = next((r[idx[k]] for k in ("SAMPLE_NAME", "SAMPLE_ID", "SAMPLE_LOC") if k in idx), "")
            out.append({"name": name, "lab": tuple(round(v, 2) for v in lab), "device": dev})
    return out


def paper_white_from(patches: list):
    """Papierweiß aus Messfeldern: das Feld ohne Farbe (CMYK 0 / RGB max), sonst ein Feld namens
        „Papier/Paper/White“, sonst das hellste. -> (Lab, Erklärung) oder (None, "")."""
    if not patches:
        return None, ""
    blank = []
    for p in patches:
        d = p["device"]
        cmyk = [v for k, v in d.items() if k.startswith("CMYK_")]
        rgb = [v for k, v in d.items() if k.startswith("RGB_")]
        if (cmyk and all(abs(v) < 1e-6 for v in cmyk)) or (rgb and min(rgb) >= max(100.0, max(rgb)) - 1e-6):
            blank.append(p)
    if blank:
        return mean_lab([p["lab"] for p in blank]), tr("{0} Feld(er) ohne Farbe gemittelt").format(len(blank))
    named = [p for p in patches if re.search(r"paper|papier|white|weiß|weiss|substrat", p["name"] or "", re.I)]
    if named:
        return mean_lab([p["lab"] for p in named]), tr("Feld „{0}“").format(named[0]["name"])
    best = max(patches, key=lambda p: p["lab"][0])
    return best["lab"], tr("hellstes Feld ({0})").format(best["name"] or "?")


def read_measurement_file(path: str):
    """Datei mit Messwerten (CGATS oder spotread-Protokoll) -> (Lab Papierweiß, Erklärung, Anzahl Felder)."""
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read(20_000_000)
    patches = parse_cgats(text)
    if patches:
        lab, why = paper_white_from(patches)
        return lab, why, len(patches)
    vals = parse_measurements(text)
    if vals:
        return mean_lab(vals), tr("{0} Messung(en) gemittelt").format(len(vals)), len(vals)
    lab = parse_lab_text(text)
    return lab, (tr("Lab-Wert aus der Datei") if lab else ""), 1 if lab else 0


# --------------------------------------------------------------------------- #
# Messgerät (ArgyllCMS spotread)
# --------------------------------------------------------------------------- #
def spotread() -> str | None:
    """spotread von ArgyllCMS (X-Rite i1Pro/i1Pro 2/3, ColorMunki, i1Studio, Spyder … – reflektiv)."""
    env = os.environ.get("PASSERMARK_SPOTREAD")
    if env:
        return env
    from . import platform as _platform
    p = _platform.find_program(["spotread"], [r"Argyll*\bin\spotread.exe", r"ArgyllCMS\bin\spotread.exe"])
    if p:
        return p
    if _platform.IS_WIN:
        for root in ("C:\\", os.path.expanduser("~")):
            hits = sorted(glob.glob(os.path.join(root, "Argyll*", "bin", "spotread.exe")), reverse=True)
            if hits:
                return hits[0]
    return shutil.which("spotread")


def spotread_args(port: int = 1, skip_cal: bool = False) -> list:
    """Einmal kalibrieren (falls nötig) und messen, dann beenden; Lab D50 wie die Profile."""
    a = ["-O", "-c", str(max(1, int(port)))]
    if skip_cal:
        a.append("-N")
    return a


RX_PROMPT = re.compile(r"(hit|press)\s+(any\s+)?(key|return)|key to (continue|start)|to (start|take) (a )?reading",
                       re.I)
RX_ABORT = re.compile(r"(abort|give up)\s*:?\s*$", re.I)
RX_CAL = re.compile(r"calibrat|white (reference|tile)|kalibr", re.I)
RX_FAIL = re.compile(r"no (instrument|device)s? found|failed to|error|not supported|can't|cannot|unable", re.I)


def spotread_state(text: str) -> str:
    """Zustand aus der bisherigen Ausgabe: "result" | "calibrate" | "measure" | "error" | "busy"."""
    tail = (text or "")[-600:]
    if RX_LAB.search(tail):
        return "result"
    lines = [ln.strip() for ln in tail.replace("\r", "\n").splitlines() if ln.strip()]
    if not lines:
        return "busy"
    last, window = lines[-1], " ".join(lines[-3:])
    if RX_PROMPT.search(last) or RX_ABORT.search(last) or (RX_PROMPT.search(window) and last.endswith(":")):
        if re.search(r"reading", last, re.I):
            return "measure"
        return "calibrate" if RX_CAL.search(window) else "measure"
    if RX_FAIL.search(last):
        return "error"
    return "busy"


# --------------------------------------------------------------------------- #
# Materialien
# --------------------------------------------------------------------------- #
def new_material(mid: str, name: str) -> dict:
    return {"id": mid, "name": name, "weight": 0, "surface": "", "white": None, "white_source": "",
            "profiles": {}, "intent": "", "notes": ""}


def material_by_id(cfg: dict, mid: str):
    return next((m for m in (cfg or {}).get("materials", []) if m.get("id") == mid), None)


def materials_for(cfg: dict, printer: str = "") -> list:
    """Materialien, die für diesen Drucker ein Profil haben (oder ein allgemeines) – zuerst die passenden."""
    ms = list((cfg or {}).get("materials", []))
    if not printer:
        return ms
    return sorted(ms, key=lambda m: 0 if printer in (m.get("profiles") or {}) else 1)


def profile_for(cfg: dict, material: dict, printer: str = ""):
    """Profil-ID des Materials für den Drucker (eigene Zuordnung, sonst die allgemeine "*")."""
    prof = (material or {}).get("profiles") or {}
    return prof.get(printer) or prof.get("*") or ""


def candidates(cfg: dict, extra_cmyk: bool = True) -> list:
    """Profile, die für Vorschläge in Frage kommen: die der Verwaltung, dazu (optional) die CMYK-Profile im
        System. -> [{"id", "name", "file", "printers", "space", "white", "surface", "admin"}]"""
    out, seen = [], set()
    for p in (cfg or {}).get("color_profiles", []):
        f = p.get("file") or ""
        if not os.path.isfile(f):
            continue
        seen.add(os.path.realpath(f))
        try:
            space = profile_space(f)
        except (OSError, ValueError):
            continue
        name = p.get("name") or p["id"]
        out.append({"id": p["id"], "name": name, "file": f, "printers": list(p.get("printers") or []),
                    "space": space, "white": profile_white(f), "admin": True,
                    "surface": guess_surface(f"{name} {profile_desc(f)} {os.path.basename(f)}")})
    if extra_cmyk:
        from . import cmyk
        for cp in cmyk.find_profiles(None):
            if os.path.realpath(cp.path) in seen:
                continue
            seen.add(os.path.realpath(cp.path))
            out.append({"id": "", "name": cp.name, "file": cp.path, "printers": [], "space": "CMYK",
                        "white": profile_white(cp.path), "admin": False,
                        "surface": guess_surface(f"{cp.name} {os.path.basename(cp.path)}")})
    return out


def verdict(de) -> str:
    if de is None:
        return tr("Papierweiß unbekannt")
    if de <= 2:
        return tr("passt sehr gut")
    if de <= 4:
        return tr("passt – Papierweiß im Softproof angleichen")
    if de <= 8:
        return tr("nur bedingt – eigenes Profil wäre besser")
    return tr("passt nicht – eigenes Profil messen")


STANDARD_TIPS = {
    "coated": "PSO Coated v3 (FOGRA51)",
    "uncoated": "PSO Uncoated v3 (FOGRA52)",
    "special": "PSO LWC Improved (FOGRA45) / PSO SC-B Paper v3 (FOGRA54)",
}


def suggest(material: dict, cands: list, printer: str = "", limit: int = 6) -> list:
    """Profile für ein Material, beste zuerst. Kriterien: Abstand des Papierweiß (ΔE 2000), gleiche Oberfläche,
        dem Drucker zugeordnet. -> [{… Kandidat …, "de", "score", "why"}]"""
    white = tuple(material["white"]) if material.get("white") else None
    surf = _surface_group(material.get("surface") or "")
    res = []
    for c in cands:
        if printer and c["printers"] and printer not in c["printers"]:
            continue                                   # einem anderen Drucker zugeordnet
        de = round(delta_e(white, c["white"]), 1) if white and c["white"] else None
        score = de if de is not None else 8.0
        why = [tr("ΔE Papierweiß {0:.1f}").format(de) if de is not None else tr("Papierweiß nicht vergleichbar")]
        cs = _surface_group(c["surface"])
        if surf and cs:
            if cs == surf:
                score -= 1.0
                why.append(tr("gleiche Oberfläche"))
            else:
                score += 6.0
                why.append(tr("andere Oberfläche ({0})").format(surface_label(c["surface"])))
        if printer and printer in c["printers"]:
            score -= 3.0
            why.append(tr("für {0} eingerichtet").format(printer))
        elif printer and c["space"] == "CMYK" and not c["admin"]:
            score += 1.0                               # Standardprofil (Offset) – für den Drucker nur Ersatz
        res.append(dict(c, de=de, score=round(score, 2), why=", ".join(why), verdict=verdict(de)))
    res.sort(key=lambda r: (r["score"], r["name"].casefold()))
    return res[:limit]


def standard_tip(material: dict, best) -> str:
    """Hinweis, wenn kein installiertes Profil gut passt: welches Standardprofil (eci.org) sich lohnt."""
    if best and best.get("de") is not None and best["de"] <= 4:
        return ""
    tip = STANDARD_TIPS.get(_surface_group(material.get("surface") or ""))
    if not tip:
        return tr("Kein gut passendes Profil – für dieses Papier ein eigenes Profil messen (Testchart).")
    return tr("Kein gut passendes Profil installiert – für diese Oberfläche üblich: {0} (eci.org), "
              "sonst ein eigenes Profil messen.").format(tip)


def recommend_conversion(output_intents: list, has_cmyk: bool, target_file: str, cands: list) -> dict:
    """CMYK-Umwandlung für ein Dokument auf dieses Papier: Ausgabebedingung der Datei -> Profil des Papiers.
        -> {"mode", "source", "text"} (source = Datei des Quellprofils oder "")."""
    tname = profile_desc(target_file) if target_file else ""
    if not has_cmyk:
        return {"mode": "rgb_only", "source": "",
                "text": tr("Keine CMYK-Inhalte: RGB/Grau werden nach „{0}“ umgerechnet.").format(tname)}
    oi = next((o for o in output_intents or [] if o), "")
    if not oi:
        return {"mode": "rgb_only", "source": "",
                "text": tr("CMYK ohne Ausgabebedingung: vorhandenes CMYK bleibt, nur RGB/Grau nach „{0}“.").format(tname)}
    norm = re.sub(r"[^a-z0-9]", "", oi.lower())
    tnorm = re.sub(r"[^a-z0-9]", "", tname.lower())
    if norm and (norm in tnorm or tnorm in norm):
        return {"mode": "rgb_only", "source": "",
                "text": tr("Die Datei ist schon für „{0}“ angelegt – CMYK bleibt, nur RGB/Grau wird umgerechnet.").format(oi)}
    src = ""
    fog = re.search(r"fogra\s*(\d+)", oi, re.I)
    for c in cands:
        if c["space"] != "CMYK":
            continue
        cn = re.sub(r"[^a-z0-9]", "", f"{c['name']} {os.path.basename(c['file'])}".lower())
        if (norm and norm in cn) or (fog and f"fogra{fog.group(1)}" in cn):
            src = c["file"]
            break
    if src:
        return {"mode": "all", "source": src,
                "text": tr("Datei angelegt für „{0}“, Papier braucht „{1}“: alles neu separieren ({0} → {1}).").format(oi, tname)}
    return {"mode": "all", "source": "",
            "text": tr("Datei angelegt für „{0}“, Papier braucht „{1}“: alles neu separieren – Quellprofil „{0}“ "
                       "ist nicht installiert (bitte importieren), sonst wird das Standard-CMYK angenommen.").format(oi, tname)}


def proof_choices(cfg: dict) -> list:
    """Druckbedingungen für den Softproof: erst die Materialien (je zugeordnetem Drucker), dann die Profile der
        Verwaltung, dann die CMYK-Profile im System.
        -> [{"key", "label", "icc", "space", "name", "white", "material", "printer"}]"""
    out = []
    by_id = {p["id"]: p for p in (cfg or {}).get("color_profiles", []) if p.get("file")}
    for m in (cfg or {}).get("materials", []):
        for printer, pid in sorted((m.get("profiles") or {}).items(), key=lambda kv: (kv[0] != "*", kv[0])):
            p = by_id.get(pid)
            if not p or not os.path.isfile(p["file"]):
                continue
            try:
                space = profile_space(p["file"])
            except (OSError, ValueError):
                continue
            where = tr("alle Drucker") if printer == "*" else printer
            out.append({"key": f"m:{m['id']}:{printer}", "icc": p["file"], "space": space,
                        "label": tr("Material: {0} – {1} ({2})").format(m.get("name") or m["id"], p.get("name") or pid, where),
                        "name": f"{m.get('name') or m['id']} / {p.get('name') or pid}",
                        "white": list(m["white"]) if m.get("white") else None, "material": m["id"],
                        "printer": "" if printer == "*" else printer, "intent": m.get("intent") or ""})
    for c in candidates(cfg):
        out.append({"key": ("p:" + c["id"]) if c["admin"] else ("f:" + c["file"]), "icc": c["file"],
                    "space": c["space"], "name": c["name"], "white": None, "material": "", "printer": "",
                    "intent": "",
                    "label": (tr("Profil: {0}") if c["admin"] else tr("System: {0}")).format(c["name"])})
    return out


def doc_color_facts(path, max_pages: int = 50) -> tuple:
    """(Ausgabebedingungen, CMYK-Inhalte?) eines PDFs – schnell: Output Intents, Operatoren k/K, CMYK-Farbräume
        von Bildern und Ressourcen (die ersten max_pages Seiten). path = Datei oder PDF-Bytes."""
    import io
    import pikepdf
    ois, cmyk = [], False
    try:
        with pikepdf.open(io.BytesIO(path) if isinstance(path, (bytes, bytearray)) else path) as pdf:
            for o in pdf.Root.get("/OutputIntents") or []:
                ois.append(str(o.get("/OutputConditionIdentifier") or o.get("/Info") or ""))
            for n, page in enumerate(pdf.pages):
                if n >= max_pages or cmyk:
                    break
                try:
                    for ins in pikepdf.parse_content_stream(page):
                        if str(getattr(ins, "operator", "")) in ("k", "K"):
                            cmyk = True
                            break
                except Exception:
                    pass
                if cmyk:
                    break
                res = page.obj.get("/Resources") or {}
                for kind in ("/XObject", "/ColorSpace"):
                    for _, obj in (res.get(kind) or {}).items():
                        cs = obj.get("/ColorSpace") if kind == "/XObject" and isinstance(obj, pikepdf.Stream) else obj
                        if cs == pikepdf.Name.DeviceCMYK:
                            cmyk = True
                        elif isinstance(cs, pikepdf.Array) and len(cs) > 1 and cs[0] == pikepdf.Name.ICCBased:
                            try:
                                cmyk = cmyk or int(cs[1].get("/N", 0)) == 4
                            except Exception:
                                pass
    except Exception:
        pass
    return [o for o in ois if o], cmyk


def cmyk_profile_of(cfg: dict, material: dict) -> str:
    """Datei des CMYK-Profils eines Materials (für die CMYK-Umwandlung): die allgemeine Zuordnung, sonst die
        erste CMYK-Zuordnung eines Druckers. "" = keins."""
    by_id = {p["id"]: p for p in (cfg or {}).get("color_profiles", [])}
    prof = (material or {}).get("profiles") or {}
    for q in ["*"] + sorted(k for k in prof if k != "*"):
        p = by_id.get(prof.get(q, ""))
        if p and os.path.isfile(p.get("file", "")):
            try:
                if profile_space(p["file"]) == "CMYK":
                    return p["file"]
            except (OSError, ValueError):
                continue
    return ""
