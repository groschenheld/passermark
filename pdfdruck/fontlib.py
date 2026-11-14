# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Fonts: where installed fonts are, finding a file for a font name, free alternatives, downloading free fonts; and the Ghostscript repairs (embed fonts, text to outlines, flatten transparency)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile

from . import platform as _platform
from .l10n import tr

# metrically compatible free substitute fonts (same character widths -> text does not shift)
METRIC = [
    (r"arial|helvetica|arimo", "Liberation Sans"),
    (r"timesnewroman|times|tinos", "Liberation Serif"),
    (r"couriernew|courier|cousine", "Liberation Mono"),
    (r"calibri", "Carlito"),
    (r"cambria", "Caladea"),
    (r"isocp|isoct|isocpeur|isocteur", "osifont"),
    (r"^symbol$|symbolmt", "Standard Symbols PS"),
    (r"zapfdingbats", "D050000L"),
    (r"verdana", "DejaVu Sans"),
    (r"tahoma|segoeui", "DejaVu Sans"),
    (r"georgia", "Gelasio"),
]


# commercial fonts -> free, metrically identical twin on fontsource.org (same character widths)
DOWNLOAD_ALIAS = [
    (r"arial|helvetica|arimo", "Arimo"),
    (r"timesnewroman|times|tinos", "Tinos"),
    (r"couriernew|courier|cousine", "Cousine"),
    (r"calibri|carlito", "Carlito"),
    (r"cambria|caladea", "Caladea"),
    (r"georgia|gelasio", "Gelasio"),
    (r"segoeui|tahoma|verdana", "Open Sans"),
]


FONTSOURCE = "https://api.fontsource.org/v1/fonts"


# --------------------------------------------------------------------------- #
# fonts
# --------------------------------------------------------------------------- #
def parse_font_name(name: str) -> tuple[str, bool, bool]:
    """BaseFont -> (normalised family, bold, italic)."""
    n = name.split("+", 1)[-1]
    low = n.lower()
    bold = bool(re.search(r"bold|black|heavy|semibold|demi", low))
    italic = bool(re.search(r"italic|oblique|kursiv", low))
    fam = re.split(r"[,-]", n)[0]
    fam = re.sub(r"(PSMT|MT|PS)$", "", fam)
    fam = re.sub(r"(Bold|Italic|Oblique|Regular)+$", "", fam, flags=re.I)
    return re.sub(r"[^a-z0-9]", "", fam.lower()), bold, italic


def font_dirs() -> list[str]:
    """Folders that are searched for font files on this system."""
    home = os.path.expanduser("~")
    if _platform.IS_WIN:
        win = os.environ.get("WINDIR", r"C:\Windows")
        return [
            os.path.join(win, "Fonts"),
            os.path.join(os.environ.get("LOCALAPPDATA", home), "Microsoft", "Windows", "Fonts"),
            user_font_dir(),
        ]
    return [
        "/usr/share/fonts",
        "/usr/local/share/fonts",
        os.path.join(home, ".local", "share", "fonts"),
        os.path.join(home, ".fonts"),
        user_font_dir(),
    ]


def user_font_dir() -> str:
    """Folder for fonts downloaded by Passermark for the current user."""
    if _platform.IS_WIN:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "Passermark", "fonts")
    return os.path.join(os.path.expanduser("~"), ".local", "share", "fonts", "passermark")


def _fc_match(family: str, bold: bool, italic: bool) -> str:
    fc = shutil.which("fc-match")
    if not fc:
        return ""
    style = ("Bold " if bold else "") + ("Italic" if italic else "")
    pat = family + (f":style={style.strip()}" if style.strip() else "")
    try:
        r = subprocess.run([fc, "-f", "%{family}|%{file}", pat], capture_output=True, text=True, timeout=10)
        fam, _, path = r.stdout.partition("|")
        if path and family.split()[0].lower() in fam.lower().replace(" ", ""):
            return path
        if path and family.lower() in fam.lower():
            return path
    except (OSError, subprocess.SubprocessError):
        pass
    return ""


def _scan_files(family: str, bold: bool, italic: bool) -> str:
    want = re.sub(r"[^a-z0-9]", "", family.lower())
    best, score_best = "", -1
    for d in font_dirs():
        if not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for fn in files:
                if not fn.lower().endswith((".ttf", ".otf")):
                    continue
                base = re.sub(r"[^a-z0-9]", "", fn.lower().rsplit(".", 1)[0])
                if not base.startswith(want):
                    continue
                rest = base[len(want) :]
                b, i = "bold" in rest, ("italic" in rest or "oblique" in rest)
                score = (b == bold) * 2 + (i == italic) * 2 - len(rest) / 100
                if score > score_best:
                    best, score_best = os.path.join(root, fn), score
    return best


def find_font_file(family: str, bold=False, italic=False) -> str:
    """Path of an installed font file for ``family`` in the given style, or an empty string."""
    return _fc_match(family, bold, italic) or _scan_files(family, bold, italic)


def suggest_font(name: str) -> tuple[str, str]:
    """(path, display name) of a suitable substitute font – preferably metrically compatible."""
    fam, bold, italic = parse_font_name(name)
    for pat, repl in METRIC:
        if re.search(pat, fam):
            p = find_font_file(repl, bold, italic)
            if p:
                return p, repl + (" Bold" if bold else "") + (" Italic" if italic else "")
    # a font of the same name in the system?
    p = _scan_files(fam, bold, italic)
    if p:
        return p, os.path.basename(p)
    # CAD standard fonts without osifont: narrow sans-serif fallback (widths stay from the PDF)
    if re.search(r"isocp|isoct|romans|simplex|txt|cad|norm", fam):
        for fb in ("DejaVu Sans Condensed", "Liberation Sans Narrow", "DejaVu Sans"):
            p = find_font_file(fb, bold, italic)
            if p:
                return p, fb + tr(" (Ausweichschrift)")
    return "", ""


def free_alternative(name: str) -> str:
    """Free (mostly metrically compatible) twin of a commercial font – or ""."""
    fam = parse_font_name(name)[0]
    for pat, alt in DOWNLOAD_ALIAS:
        if re.search(pat, fam):
            return alt
    return ""


def _get_json(url):
    import urllib.request  # only when needed: loads SSL – cost noticeable time for the first window

    req = urllib.request.Request(url, headers={"User-Agent": "Passermark"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def similar_fonts(family: str, n: int = 6) -> list[str]:
    """Similarly named free fonts on fontsource.org (for "Did you mean …?")."""
    import difflib

    try:
        lst = _get_json(FONTSOURCE)
    except Exception:
        return []
    fams = [f.get("family", "") for f in lst if isinstance(f, dict)]
    low = {f.lower(): f for f in fams}
    q = family.lower().strip()
    hits = [low[k] for k in difflib.get_close_matches(q, list(low), n=n, cutoff=0.6)]
    hits += [f for f in fams if q and q in f.lower() and f not in hits]
    return hits[:n]


class FontNotFound(RuntimeError):
    """Raised when a font cannot be downloaded; carries similar family names as suggestions."""

    def __init__(self, family, suggestions):
        self.family, self.suggestions = family, suggestions
        msg = tr("Schrift „{0}“ gibt es auf fontsource.org nicht (dort liegen nur freie Schriften).").format(family)
        if suggestions:
            msg += "\n" + tr("Ähnliche freie Schriften: {0}").format(", ".join(suggestions))
        super().__init__(msg)


def download_font(family: str, progress=None) -> tuple[list[str], str]:
    """Fetch a free font (OFL/Apache) from fontsource.org -> (file paths, family actually loaded).
    Commercial names (Arial, Calibri …) are redirected to their free twin.
    """
    import urllib.error
    import urllib.request

    used = free_alternative(family) or family.strip()
    fid = re.sub(r"[^a-z0-9]+", "-", used.lower()).strip("-")
    cdn = "https://cdn.jsdelivr.net/fontsource/fonts/{0}@latest/latin-{1}-{2}.ttf"
    try:
        meta = _get_json(f"{FONTSOURCE}/{fid}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise FontNotFound(used, similar_fonts(used)) from e
        meta = None
        api_err = e
    except Exception as e:
        meta = None
        api_err = e
    if meta is None:
        # API not reachable: directly from the fontsource CDN (same files)
        meta = {
            "family": used,
            "variants": {
                w: {st: {"latin": {"url": {"ttf": cdn.format(fid, w, st)}}} for st in ("normal", "italic")}
                for w in ("400", "700")
            },
        }
    variants = meta.get("variants") or {}
    out_dir = user_font_dir()
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for weight in ("400", "700"):
        for style in ("normal", "italic"):
            v = (variants.get(weight) or {}).get(style) or {}
            sub = v.get("latin") or (next(iter(v.values())) if v else None)
            if not sub:
                continue
            u = (sub.get("url") or {}).get("ttf")
            if not u:
                continue
            fn = f"{fid}-{weight}-{style}.ttf"
            dst = os.path.join(out_dir, fn)
            try:
                with urllib.request.urlopen(
                    urllib.request.Request(u, headers={"User-Agent": "Passermark"}), timeout=30
                ) as r:
                    data = r.read()
            except Exception:
                continue  # style not available (e.g. no italic)
            with open(dst, "wb") as f:
                f.write(data)
            paths.append(dst)
            if progress:
                progress(fn)
    if not paths:
        if "api_err" in locals():
            raise RuntimeError(tr("Kein Zugriff auf fontsource.org ({0}).").format(api_err))
        raise RuntimeError(tr("Für „{0}“ gibt es keine TTF-Dateien zum Herunterladen.").format(used))
    if shutil.which("fc-cache"):
        subprocess.run(["fc-cache", "-f", out_dir], capture_output=True, timeout=60)
    return paths, meta.get("family", used)


def _gs(args: list, src: bytes) -> bytes:
    gs = _platform.ghostscript()
    if not gs:
        raise RuntimeError(tr("Für diese Reparatur wird Ghostscript benötigt."))
    tmp = tempfile.mkdtemp(prefix="passermark-pf-")
    try:
        i, o = os.path.join(tmp, "in.pdf"), os.path.join(tmp, "out.pdf")
        with open(i, "wb") as f:
            f.write(src)
        cmd = [
            gs,
            "-q",
            "-dNOPAUSE",
            "-dBATCH",
            "-dSAFER",
            "-sDEVICE=pdfwrite",
            "-dAutoRotatePages=/None",
            "-dDownsampleColorImages=false",
            "-dDownsampleGrayImages=false",
            "-dDownsampleMonoImages=false",
            *[a.replace("{TMP}", tmp) for a in args],
            "-o",
            o,
            i,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, **_platform.hidden_subprocess_kwargs())
        if r.returncode != 0 or not os.path.exists(o):
            raise RuntimeError(tr("Ghostscript-Fehler:\n") + (r.stderr or r.stdout or "")[-1500:])
        with open(o, "rb") as f:
            return f.read()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _ps_str(s: str) -> str:
    return "(" + s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ")"


def embed_fonts(data: bytes, mapping: dict) -> bytes:
    """Embed all fonts; replace missing ones via the mapping {font name: path} (Ghostscript fontmap)."""
    tmp = tempfile.mkdtemp(prefix="passermark-fm-")
    try:
        fm = os.path.join(tmp, "Fontmap")
        dirs = set()
        with open(fm, "w", encoding="utf-8") as f:
            for name, path in mapping.items():
                if path and os.path.exists(path):
                    f.write(f"/{name} {_ps_str(path)} ;\n")
                    dirs.add(os.path.dirname(path))
        permits = [f"--permit-file-read={d.rstrip(os.sep)}{os.sep}" for d in dirs | {tmp}]
        args = ["-dCompatibilityLevel=1.7", "-dEmbedAllFonts=true", "-dSubsetFonts=true", f"-sFONTMAP={fm}", *permits]
        if dirs:
            args.append("-sFONTPATH=" + os.pathsep.join(sorted(dirs)))
        return _gs(args, data)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def outline_text(data: bytes) -> bytes:
    """Convert text to paths (looks the same everywhere, but is no longer searchable)."""
    return _gs(["-dCompatibilityLevel=1.7", "-dNoOutputFonts"], data)


def flatten_transparency(data: bytes, dpi: int = 300) -> bytes:
    """Reduce transparency (PDF 1.3) – for older printers/RIPs. Transparent areas are rasterized."""
    return _gs(["-dCompatibilityLevel=1.3", f"-r{dpi}"], data)
