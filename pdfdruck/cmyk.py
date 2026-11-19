# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""CMYK conversion of PDFs and color-accurate preview.

Conversion: Ghostscript (pdfwrite) with the destination profile (e.g. PSO Coated v3 / FOGRA51), rendering
intent and black point compensation. Vectors and fonts are preserved.

Methods:
  rgb_only – RGB/grayscale -> CMYK; existing CMYK stays unchanged (source CMYK = destination profile,
             so Ghostscript passes CMYK through 1:1)
  all      – separate everything anew: CMYK data are interpreted with the source profile (e.g. FOGRA39)
             and converted to the destination profile (e.g. FOGRA52 uncoated)
  gray     – everything to grayscale (prints with black only)

Preview: Ghostscript renders the page with the VERY SAME settings as a CMYK raster (tiff32nc);
LittleCMS converts that CMYK with the destination profile to the screen (sRGB) – the way it will look
when printed. Additionally: total ink coverage (TAC) and the individual separations C/M/Y/K from exactly
these CMYK values.
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field, replace

from . import platform as _platform
from .l10n import tr

INTENT_NUM = {"perceptual": 0, "relative": 1, "saturation": 2, "absolute": 3}

# known standard printing conditions (see www.eci.org and idealliance.org) – for explanation/detection
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
    """An available CMYK ICC profile: display name, file path and where it comes from."""

    name: str
    path: str
    origin: str  # admin | system


@dataclass
class ManipSettings:
    """Settings of the job ``manip``: CMYK conversion and/or cropping to a target size."""

    cmyk: bool = False
    cmyk_mode: str = "rgb_only"  # rgb_only | all | gray
    target: str = ""  # path of the target profile (CMYK)
    source: str = ""  # source profile path for existing CMYK (mode "all")
    intent: str = "relative"
    bpc: bool = True
    gray_to_k: bool = True  # print grey/black with K only
    output_intent: bool = True  # embed the target profile as output intent
    crop: bool = False
    crop_size: str = "A4"  # key from FORMATS or "custom"
    crop_w_mm: float = 210.0
    crop_h_mm: float = 297.0
    crop_follow: bool = True  # follow the portrait/landscape orientation of the page
    crop_scale: bool = True  # first scale until the target is fully covered, then trim the overhang
    crop_inset_mm: float = 0.0  # trim this much all around beforehand (white margins of the original)
    crop_mode: str = "format"  # format | trim | whiteout
    trim_l_mm: float = 0.0  # trim: cut off left/top/right/bottom
    trim_t_mm: float = 0.0
    trim_r_mm: float = 0.0
    trim_b_mm: float = 0.0
    white_margin_mm: float = 0.0  # whiteout: margin around the detected content (negative = cut into it)

    @classmethod
    def from_dict(cls, d):
        """Create settings from a dict; unknown keys are ignored."""
        s = cls()
        for k, v in (d or {}).items():
            if hasattr(s, k):
                setattr(s, k, type(getattr(s, k))(v))
        return s

    def to_dict(self):
        """Plain dict of all fields."""
        return dict(self.__dict__)

    @property
    def active(self) -> bool:
        """Whether the settings would change the document at all."""
        return (self.cmyk and (bool(self.target) or self.cmyk_mode == "gray")) or self.crop


# --------------------------------------------------------------------------- #
# find profiles
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
    except Exception:  # noqa: BLE001 – optional part: works without it
        pass
    return os.path.splitext(os.path.basename(path))[0]


def system_profile_dirs() -> list[str]:
    """Folders with ICC profiles: system, plus the user's profile folder (usercolor.icc_dir – get standard profiles)."""
    from . import usercolor

    if _platform.IS_WIN:
        win = os.environ.get("WINDIR", r"C:\Windows")
        dirs = [os.path.join(win, "System32", "spool", "drivers", "color")]
    else:
        home = os.path.expanduser("~")
        dirs = [
            "/usr/share/color/icc",
            "/usr/local/share/color/icc",
            "/var/lib/color/icc",
            os.path.join(home, ".local", "share", "icc"),
            os.path.join(home, ".color", "icc"),
            "/usr/share/texlive/texmf-dist/tex/generic/colorprofiles",
            "/usr/share/ghostscript",
        ]
    own = usercolor.icc_dir()
    if own not in dirs:
        dirs.insert(0, own)
    return dirs


def _gs_internal(path: str, desc: str) -> bool:
    """Ghostscript's PostScript working profile (ps_cmyk, "Artifex PS CMYK Profile"): a naive CMYK conversion,
    no printing condition – not offered as a target, the preview with it shows garishly saturated colours.
    Ghostscript's SWOP profile (default_cmyk) stays: usable for quick tests."""
    return os.path.basename(path).lower() == "ps_cmyk.icc" or desc.startswith("Artifex PS ")


def find_profiles(cfg: dict | None = None) -> list[CmykProfile]:
    """CMYK print profiles: first those imported by the admin, then those present in the system."""
    out, seen = [], set()

    def add(path, origin, name=None):
        real = os.path.realpath(path)
        if real in seen:
            return
        h = _icc_head(path)
        if not h or h[16:20] != b"CMYK" or h[12:16] not in (b"prtr", b"spac"):
            return
        desc = name or _desc(path)
        if origin == "system" and _gs_internal(path, desc):
            return
        seen.add(real)
        out.append(CmykProfile(desc, path, origin))

    for p in (cfg or {}).get("color_profiles", []):
        if p.get("file") and os.path.exists(p["file"]):
            add(p["file"], "admin", p.get("name"))
    for d in system_profile_dirs():
        if not os.path.isdir(d):
            continue
        for path in glob.glob(os.path.join(d, "**", "*.ic[cm]"), recursive=True) + glob.glob(
            os.path.join(d, "**", "*.IC[CM]"), recursive=True
        ):
            add(path, "system")
    return out


def ghostscript() -> str | None:
    """Path of the Ghostscript program, or None if it is not installed."""
    return _platform.ghostscript()


# --------------------------------------------------------------------------- #
# Ghostscript arguments (shared by conversion and preview -> identical result)
# --------------------------------------------------------------------------- #
def color_args(s: ManipSettings) -> list[str]:
    """Ghostscript arguments for the colour conversion described by ``s``."""
    if s.cmyk_mode == "gray":
        return ["-sColorConversionStrategy=Gray", "-sProcessColorModel=DeviceGray"]
    if not s.target:
        raise ValueError(tr("Kein CMYK-Zielprofil gewählt."))
    args = [
        "-sColorConversionStrategy=CMYK",
        "-sProcessColorModel=DeviceCMYK",
        f"-sOutputICCProfile={s.target}",
        f"-dRenderIntent={INTENT_NUM.get(s.intent, 1)}",
        f"-dBlackPtComp={1 if s.bpc else 0}",
        f"-dDeviceGrayToK={'true' if s.gray_to_k else 'false'}",
    ]
    if s.cmyk_mode == "rgb_only":
        # source CMYK = target profile -> existing CMYK is passed through 1:1
        args.append(f"-sDefaultCMYKProfile={s.target}")
    elif s.source:
        args.append(f"-sDefaultCMYKProfile={s.source}")
    return args


def _profile_key(data: bytes) -> bytes:
    """Identity of an ICC profile: MD5 over the data with the header fields that may differ between copies
    (flags, rendering intent, profile ID) set to zero – the way the ICC specification computes the profile ID."""
    import hashlib

    b = bytearray(data)
    if len(b) >= 100:
        b[44:48] = b"\0" * 4
        b[64:68] = b"\0" * 4
        b[84:100] = b"\0" * 16
    return hashlib.md5(bytes(b)).digest()


def same_profile(data: bytes, path: str) -> bool:
    """Is the profile ``data`` the same as the ICC file ``path``?"""
    try:
        with open(path, "rb") as f:
            return _profile_key(data) == _profile_key(f.read())
    except OSError:
        return False


def document_cmyk_profile(path: str, password: str | None = None) -> bytes | None:
    """CMYK profile of the PDF's output intent – the printing condition the file was separated for – or None."""
    try:
        import pikepdf

        with pikepdf.open(path, password=password or "") as pdf:
            for oi in pdf.Root.get("/OutputIntents", None) or []:
                prof = oi.get("/DestOutputProfile")
                if prof is None:
                    continue
                data = prof.read_bytes()
                if len(data) >= 20 and data[16:20] == b"CMYK":
                    return data
    except Exception:  # noqa: BLE001 – no readable output intent: Ghostscript's default applies
        return None
    return None


def resolve_source(src_pdf: str, s: ManipSettings, tmpdir: str, password: str | None = None):
    """Existing CMYK in the file: which profile it is read with -> (settings, notes).

    The output intent of the file says what the CMYK was separated for. Is that already the target profile,
    the CMYK stays 1:1 (also in "separate everything anew"). In "separate everything anew" without a chosen
    source profile it is read with the output intent instead of Ghostscript's SWOP default.
    """
    if s.cmyk_mode not in ("all", "rgb_only") or not s.target or s.source:
        return s, []
    data = document_cmyk_profile(src_pdf, password)
    if not data:
        return s, []
    p = os.path.join(tmpdir, "source.icc")
    with open(p, "wb") as f:
        f.write(data)
    name = _desc(p)
    if same_profile(data, s.target):
        return replace(s, cmyk_mode="rgb_only"), [
            tr("Die Datei ist schon für {0} separiert – vorhandenes CMYK bleibt unverändert.").format(name)
        ]
    if s.cmyk_mode == "rgb_only":
        return s, []
    return replace(s, source=p), [tr("Vorhandenes CMYK wird mit dem Profil der Datei gelesen: {0}").format(name)]


def _permit(s: ManipSettings) -> list[str]:
    out = []
    for p in {s.target, s.source} - {""}:
        out.append(f"--permit-file-read={p}")
    return out


def _run(cmd, timeout=1800):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **_platform.hidden_subprocess_kwargs())
    return r


def convert_pdf(src: str, dst: str, s: ManipSettings) -> list[str]:
    """Convert the colours of ``src`` with Ghostscript and write the result to ``dst`` -> notes."""
    gs = ghostscript()
    if not gs:
        raise RuntimeError(tr("Für die CMYK-Umwandlung wird Ghostscript benötigt."))
    tmp = tempfile.mkdtemp(prefix="passermark-cmyk-")
    try:
        return _convert(gs, src, dst, s, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _convert(gs, src, dst, s, tmp) -> list[str]:
    target = s.target
    s, notes = resolve_source(src, s, tmp)
    cmd = [
        gs,
        "-q",
        "-dNOPAUSE",
        "-dBATCH",
        "-dSAFER",
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.7",
        "-dAutoRotatePages=/None",
        "-dEmbedAllFonts=true",
        "-dSubsetFonts=true",
        # no image downscaling – only the colors should change
        "-dDownsampleColorImages=false",
        "-dDownsampleGrayImages=false",
        "-dDownsampleMonoImages=false",
        *_permit(s),
        *color_args(s),
        "-o",
        dst,
        src,
    ]
    r = _run(cmd)
    if r.returncode != 0 or not os.path.exists(dst):
        raise RuntimeError(tr("Ghostscript-Fehler:\n") + (r.stderr or r.stdout or "")[-1500:])
    if s.output_intent and s.cmyk_mode != "gray" and target:
        embed_output_intent(dst, target)
    return notes


def embed_output_intent(path: str, icc: str):
    """Embed the target profile as output intent (GTS_PDFX) – the print shop sees the printing condition."""
    import pikepdf

    with open(icc, "rb") as f:
        data = f.read()
    pdf = pikepdf.open(path, allow_overwriting_input=True)
    try:
        _set_output_intent(pdf, data, _desc(icc))
        pdf.save(path)
    finally:
        pdf.close()


def _set_output_intent(pdf, data: bytes, name: str):
    import pikepdf

    stream = pikepdf.Stream(pdf, data)
    stream["/N"] = 4
    oi = pikepdf.Dictionary(
        Type=pikepdf.Name.OutputIntent,
        S=pikepdf.Name.GTS_PDFX,
        OutputConditionIdentifier=pikepdf.String(name),
        Info=pikepdf.String(name),
        DestOutputProfile=stream,
    )
    pdf.Root.OutputIntents = pikepdf.Array([oi])


def with_output_intent(pdf_bytes: bytes, icc: bytes) -> bytes:
    """``pdf_bytes`` with the CMYK profile ``icc`` as output intent (in memory) – unchanged if that fails."""
    import io
    import tempfile

    import pikepdf

    try:
        with tempfile.NamedTemporaryFile(suffix=".icc", delete=False) as f:
            f.write(icc)
            tmp = f.name
        try:
            name = _desc(tmp)
        finally:
            os.unlink(tmp)
        with pikepdf.open(io.BytesIO(pdf_bytes)) as pdf:
            _set_output_intent(pdf, icc, name)
            out = io.BytesIO()
            pdf.save(out)
            return out.getvalue()
    except Exception:  # noqa: BLE001 – the output intent is an addition, the document stays usable
        return pdf_bytes


# --------------------------------------------------------------------------- #
# preview
# --------------------------------------------------------------------------- #
def _render(gs, src, page, dpi, device, extra, out):
    cmd = [
        gs,
        "-q",
        "-dNOPAUSE",
        "-dBATCH",
        "-dSAFER",
        f"-sDEVICE={device}",
        f"-r{dpi}",
        f"-dFirstPage={page + 1}",
        f"-dLastPage={page + 1}",
        "-dTextAlphaBits=4",
        "-dGraphicsAlphaBits=4",
        *extra,
        "-o",
        out,
        src,
    ]
    r = _run(cmd, timeout=300)
    if r.returncode != 0 or not os.path.exists(out):
        raise RuntimeError(tr("Ghostscript-Fehler:\n") + (r.stderr or r.stdout or "")[-800:])


@dataclass
class Preview:
    """Before/after images of one page for the conversion preview, plus the real CMYK separation."""

    before: object  # PIL RGB
    after: object  # PIL RGB (Softproof)
    cmyk: object = None  # PIL CMYK (real separation values) or None for greyscale
    gray: object = None  # PIL L for greyscale
    notes: list = field(default_factory=list)


def _before_args(s: ManipSettings) -> list[str]:
    """Ghostscript arguments for the "before" image: existing CMYK is shown with the profile the conversion
    reads it with (and the same intent as "after"), so CMYK that stays unchanged looks the same on both sides
    instead of once as SWOP (Ghostscript's default) and once through the target profile."""
    if s.cmyk_mode == "gray" or not s.target:
        return []
    src = s.target if s.cmyk_mode == "rgb_only" else s.source
    if not src:
        return []
    return [*_permit(s), f"-sDefaultCMYKProfile={src}", "-dRenderIntent=1", "-dBlackPtComp=1"]


def render_preview(
    src_pdf: str, page: int, s: ManipSettings, dpi: int = 100, paper_white: bool = False, white_lab=None
) -> Preview:
    """Render one page before and after the conversion for the preview (soft proof of the result)."""
    from PIL import Image

    gs = ghostscript()
    if not gs:
        raise RuntimeError(tr("Für die Farbvorschau wird Ghostscript benötigt."))
    tmp = tempfile.mkdtemp(prefix="passermark-prev-")
    try:
        notes = []
        if s.cmyk_mode != "gray":
            s, notes = resolve_source(src_pdf, s, tmp)
        b = os.path.join(tmp, "before.png")
        _render(gs, src_pdf, page, dpi, "png16m", _before_args(s), b)
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
        after = cmyk_to_screen(cmyk, s.target, paper_white, white_lab)
        return Preview(before, after, cmyk, notes=notes)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def cmyk_to_screen(cmyk, profile: str, paper_white: bool = False, white_lab=None):
    """Show CMYK values as they look when printed with this profile (LittleCMS). white_lab = measured
    paper white of the material (instead of the profile white) for the paper simulation.
    """
    from PIL import ImageCms

    if paper_white and white_lab:
        from . import proof

        return proof.device_to_screen(cmyk, {"icc": profile, "space": "CMYK", "paper": True, "white": list(white_lab)})
    src = ImageCms.getOpenProfile(profile)
    dst = ImageCms.createProfile("sRGB")
    intent = ImageCms.Intent.ABSOLUTE_COLORIMETRIC if paper_white else ImageCms.Intent.RELATIVE_COLORIMETRIC
    flags = 0 if paper_white else ImageCms.Flags.BLACKPOINTCOMPENSATION
    tf = ImageCms.buildTransform(src, dst, "CMYK", "RGB", renderingIntent=intent, flags=flags)
    return ImageCms.applyTransform(cmyk, tf)


def separation(cmyk, channel: int):
    """Single separation (0=C, 1=M, 2=Y, 3=K) as a grey image: a lot of ink = dark (like a film)."""
    from PIL import ImageOps

    return ImageOps.invert(cmyk.split()[channel]).convert("RGB")


def tac(cmyk, limit_pct: float = 300.0):
    """Ink coverage: (maximum in %, area share above the limit in %, warning image RGB)."""
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
