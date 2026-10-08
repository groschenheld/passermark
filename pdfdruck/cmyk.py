# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""CMYK-Umwandlung von PDFs und farbverbindliche Vorschau.

Umwandlung: Ghostscript (pdfwrite) mit Zielprofil (z. B. PSO Coated v3 / FOGRA51), Render-Intent und
Tiefenkompensierung. Vektoren und Schriften bleiben erhalten.

Methoden:
  rgb_only – RGB/Graustufen -> CMYK; vorhandenes CMYK bleibt unverändert (Quell-CMYK = Zielprofil,
             dadurch rechnet Ghostscript CMYK 1:1 durch)
  all      – alles neu separieren: CMYK-Daten werden als Quellprofil interpretiert (z. B. FOGRA39)
             und ins Zielprofil (z. B. FOGRA52 ungestrichen) umgerechnet
  gray     – alles in Graustufen (druckt nur mit Schwarz)

Vorschau: Ghostscript rendert die Seite mit DENSELBEN Einstellungen als CMYK-Raster (tiff32nc);
LittleCMS rechnet das CMYK mit dem Zielprofil auf den Bildschirm (sRGB) – so wie es gedruckt aussieht.
Zusätzlich: Farbauftrag (TAC) und Einzelauszüge C/M/Y/K aus genau diesen CMYK-Werten.
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field

from . import platform as _platform
from .l10n import tr

INTENT_NUM = {"perceptual": 0, "relative": 1, "saturation": 2, "absolute": 3}

# Bekannte Standard-Druckbedingungen (Bezug: www.eci.org bzw. idealliance.org) – zur Erklärung/Erkennung
KNOWN = [
    ("PSOcoated_v3", "PSO Coated v3 (FOGRA51) – Offset, gestrichen"),
    ("PSOuncoated_v3", "PSO Uncoated v3 (FOGRA52) – Offset, ungestrichen"),
    ("ISOcoated_v2", "ISO Coated v2 (FOGRA39) – Offset, gestrichen (älter)"),
    ("FOGRA39", "Coated FOGRA39 – Offset, gestrichen (älter)"),
    ("PSO_Uncoated_ISO12647", "PSO Uncoated ISO12647 (FOGRA47) – ungestrichen (älter)"),
    ("PSO_LWC_Improved", "PSO LWC Improved (FOGRA45) – Rollenoffset LWC"),
    ("PSOsc-b_paper_v3", "PSO SC-B Paper v3 (FOGRA54) – Zeitungs-/SC-Papier"),
    ("GRACoL2013", "GRACoL 2013 (CRPC6) – USA, gestrichen"),
    ("SWOP2013", "SWOP 2013 (CRPC5) – USA, Rollenoffset"),
]
ECI_URL = "https://www.eci.org/doku.php?id=en:downloads"


@dataclass
class CmykProfile:
    name: str
    path: str
    origin: str             # admin | system


@dataclass
class ManipSettings:
    cmyk: bool = False
    cmyk_mode: str = "rgb_only"        # rgb_only | all | gray
    target: str = ""                   # Pfad Zielprofil (CMYK)
    source: str = ""                   # Pfad Quellprofil für vorhandenes CMYK (Modus „all“)
    intent: str = "relative"
    bpc: bool = True
    gray_to_k: bool = True             # Grau/Schwarz nur mit K drucken
    output_intent: bool = True         # Zielprofil als Output Intent einbetten
    crop: bool = False
    crop_size: str = "A4"              # Schlüssel aus FORMATS oder "custom"
    crop_w_mm: float = 210.0
    crop_h_mm: float = 297.0
    crop_follow: bool = True           # Hoch-/Querformat der Seite folgen

    @classmethod
    def from_dict(cls, d):
        s = cls()
        for k, v in (d or {}).items():
            if hasattr(s, k):
                setattr(s, k, type(getattr(s, k))(v))
        return s

    def to_dict(self):
        return dict(self.__dict__)

    @property
    def active(self) -> bool:
        return (self.cmyk and (bool(self.target) or self.cmyk_mode == "gray")) or self.crop


# --------------------------------------------------------------------------- #
# Profile finden
# --------------------------------------------------------------------------- #
def _icc_head(path):
    try:
        with open(path, "rb") as f:
            h = f.read(40)
        return h if len(h) == 40 and h[36:40] == b"acsp" else None
    except OSError:
        return None


def _desc(path):
    try:
        from PIL import ImageCms
        d = (ImageCms.getProfileDescription(ImageCms.getOpenProfile(path)) or "").strip()
        if d:
            return d
    except Exception:
        pass
    return os.path.splitext(os.path.basename(path))[0]


def system_profile_dirs() -> list[str]:
    if _platform.IS_WIN:
        win = os.environ.get("WINDIR", r"C:\Windows")
        return [os.path.join(win, "System32", "spool", "drivers", "color")]
    home = os.path.expanduser("~")
    return ["/usr/share/color/icc", "/usr/local/share/color/icc", "/var/lib/color/icc",
            os.path.join(home, ".local", "share", "icc"), os.path.join(home, ".color", "icc"),
            "/usr/share/texlive/texmf-dist/tex/generic/colorprofiles", "/usr/share/ghostscript"]


def find_profiles(cfg: dict | None = None) -> list[CmykProfile]:
    """CMYK-Druckprofile: zuerst die vom Admin importierten, dann die im System vorhandenen."""
    out, seen = [], set()

    def add(path, origin, name=None):
        real = os.path.realpath(path)
        if real in seen:
            return
        h = _icc_head(path)
        if not h or h[16:20] != b"CMYK" or h[12:16] not in (b"prtr", b"spac"):
            return
        seen.add(real)
        out.append(CmykProfile(name or _desc(path), path, origin))

    for p in (cfg or {}).get("color_profiles", []):
        if p.get("file") and os.path.exists(p["file"]):
            add(p["file"], "admin", p.get("name"))
    for d in system_profile_dirs():
        if not os.path.isdir(d):
            continue
        for path in glob.glob(os.path.join(d, "**", "*.ic[cm]"), recursive=True) + \
                glob.glob(os.path.join(d, "**", "*.IC[CM]"), recursive=True):
            add(path, "system")
    return out


def ghostscript() -> str | None:
    return _platform.ghostscript()


# --------------------------------------------------------------------------- #
# Ghostscript-Argumente (gemeinsam für Umwandlung und Vorschau -> identisches Ergebnis)
# --------------------------------------------------------------------------- #
def color_args(s: ManipSettings) -> list[str]:
    if s.cmyk_mode == "gray":
        return ["-sColorConversionStrategy=Gray", "-sProcessColorModel=DeviceGray"]
    if not s.target:
        raise ValueError(tr("Kein CMYK-Zielprofil gewählt."))
    args = ["-sColorConversionStrategy=CMYK", "-sProcessColorModel=DeviceCMYK",
            f"-sOutputICCProfile={s.target}",
            f"-dRenderIntent={INTENT_NUM.get(s.intent, 1)}", f"-dBlackPtComp={1 if s.bpc else 0}",
            f"-dDeviceGrayToK={'true' if s.gray_to_k else 'false'}"]
    if s.cmyk_mode == "rgb_only":
        # Quell-CMYK = Zielprofil -> vorhandenes CMYK wird 1:1 durchgereicht
        args.append(f"-sDefaultCMYKProfile={s.target}")
    elif s.source:
        args.append(f"-sDefaultCMYKProfile={s.source}")
    return args


def _permit(s: ManipSettings) -> list[str]:
    out = []
    for p in {s.target, s.source} - {""}:
        out.append(f"--permit-file-read={p}")
    return out


def _run(cmd, timeout=1800):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **_platform.hidden_subprocess_kwargs())
    return r


def convert_pdf(src: str, dst: str, s: ManipSettings):
    gs = ghostscript()
    if not gs:
        raise RuntimeError(tr("Für die CMYK-Umwandlung wird Ghostscript benötigt."))
    cmd = [gs, "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.7",
           "-dAutoRotatePages=/None", "-dEmbedAllFonts=true", "-dSubsetFonts=true",
           # keine Bildverkleinerung – nur die Farben sollen sich ändern
           "-dDownsampleColorImages=false", "-dDownsampleGrayImages=false", "-dDownsampleMonoImages=false",
           *_permit(s), *color_args(s), "-o", dst, src]
    r = _run(cmd)
    if r.returncode != 0 or not os.path.exists(dst):
        raise RuntimeError(tr("Ghostscript-Fehler:\n") + (r.stderr or r.stdout or "")[-1500:])
    if s.output_intent and s.cmyk_mode != "gray" and s.target:
        embed_output_intent(dst, s.target)


def embed_output_intent(path: str, icc: str):
    """Zielprofil als Output Intent (GTS_PDFX) einbetten – die Druckerei sieht die Druckbedingung."""
    import pikepdf
    with open(icc, "rb") as f:
        data = f.read()
    pdf = pikepdf.open(path, allow_overwriting_input=True)
    try:
        stream = pikepdf.Stream(pdf, data)
        stream["/N"] = 4
        name = _desc(icc)
        oi = pikepdf.Dictionary(Type=pikepdf.Name.OutputIntent, S=pikepdf.Name.GTS_PDFX,
                                OutputConditionIdentifier=pikepdf.String(name), Info=pikepdf.String(name),
                                DestOutputProfile=stream)
        pdf.Root.OutputIntents = pikepdf.Array([oi])
        pdf.save(path)
    finally:
        pdf.close()


# --------------------------------------------------------------------------- #
# Vorschau
# --------------------------------------------------------------------------- #
def _render(gs, src, page, dpi, device, extra, out):
    cmd = [gs, "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", f"-sDEVICE={device}", f"-r{dpi}",
           f"-dFirstPage={page + 1}", f"-dLastPage={page + 1}", "-dTextAlphaBits=4", "-dGraphicsAlphaBits=4",
           *extra, "-o", out, src]
    r = _run(cmd, timeout=300)
    if r.returncode != 0 or not os.path.exists(out):
        raise RuntimeError(tr("Ghostscript-Fehler:\n") + (r.stderr or r.stdout or "")[-800:])


@dataclass
class Preview:
    before: object                     # PIL RGB
    after: object                      # PIL RGB (Softproof)
    cmyk: object = None                # PIL CMYK (echte Separationswerte) bzw. None bei Graustufen
    gray: object = None                # PIL L bei Graustufen
    notes: list = field(default_factory=list)


def render_preview(src_pdf: str, page: int, s: ManipSettings, dpi: int = 100, paper_white: bool = False) -> Preview:
    from PIL import Image
    gs = ghostscript()
    if not gs:
        raise RuntimeError(tr("Für die Farbvorschau wird Ghostscript benötigt."))
    tmp = tempfile.mkdtemp(prefix="passermark-prev-")
    try:
        b = os.path.join(tmp, "before.png")
        _render(gs, src_pdf, page, dpi, "png16m", [], b)
        before = Image.open(b).convert("RGB")
        if s.cmyk_mode == "gray":
            a = os.path.join(tmp, "after.png")
            _render(gs, src_pdf, page, dpi, "pnggray", [], a)
            g = Image.open(a).convert("L")
            return Preview(before, g.convert("RGB"), None, g)
        a = os.path.join(tmp, "after.tif")
        _render(gs, src_pdf, page, dpi, "tiff32nc", [*_permit(s), *color_args(s)], a)
        cmyk = Image.open(a)
        cmyk.load()
        cmyk = cmyk.convert("CMYK") if cmyk.mode != "CMYK" else cmyk
        after = cmyk_to_screen(cmyk, s.target, paper_white)
        return Preview(before, after, cmyk)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def cmyk_to_screen(cmyk, profile: str, paper_white: bool = False):
    """CMYK-Werte so anzeigen, wie sie mit diesem Profil gedruckt aussehen (LittleCMS)."""
    from PIL import ImageCms
    src = ImageCms.getOpenProfile(profile)
    dst = ImageCms.createProfile("sRGB")
    intent = ImageCms.Intent.ABSOLUTE_COLORIMETRIC if paper_white else ImageCms.Intent.RELATIVE_COLORIMETRIC
    flags = 0 if paper_white else ImageCms.Flags.BLACKPOINTCOMPENSATION
    tf = ImageCms.buildTransform(src, dst, "CMYK", "RGB", renderingIntent=intent, flags=flags)
    return ImageCms.applyTransform(cmyk, tf)


def separation(cmyk, channel: int):
    """Einzelauszug (0=C, 1=M, 2=Y, 3=K) als Graubild: viel Farbe = dunkel (wie ein Film)."""
    from PIL import ImageOps
    return ImageOps.invert(cmyk.split()[channel]).convert("RGB")


def tac(cmyk, limit_pct: float = 300.0):
    """Farbauftrag: (Maximum in %, Flächenanteil über Grenze in %, Warnbild RGB)."""
    import numpy as np
    from PIL import Image
    a = np.asarray(cmyk, dtype=np.uint16)
    total = a.sum(axis=2) * (100.0 / 255.0)
    mx = float(total.max()) if total.size else 0.0
    over = total > limit_pct
    pct = float(over.mean() * 100.0) if total.size else 0.0
    gray = np.asarray(cmyk.convert("RGB").convert("L"), dtype=np.uint8)
    rgb = np.stack([gray, gray, gray], axis=2).copy()
    rgb[over] = (255, 0, 64)
    return mx, pct, Image.fromarray(rgb, "RGB")
