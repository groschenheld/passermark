# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""ICC-Profile beschaffen: Download per Link, Entpacken (ZIP, Treiberpakete via 7z), Prüfen.

Es gibt keinen zentralen Profil-Server – Hersteller und Papierfirmen bieten Profile auf
Download-Seiten (meist als ZIP) bzw. im Windows-/Mac-Treiberpaket an. Darum:
Bezugsquellen öffnen -> Datei laden -> hier importieren (Datei, ZIP, .exe/.dmg/.cab oder direkter Link).
"""
from __future__ import annotations

from .l10n import tr

import os
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass

MAX_DOWNLOAD = 400 << 20          # Treiberpakete können groß sein
ICC_EXT = (".icc", ".icm")

# Bezugsquellen (Stand 10/2026). "match": Teilstrings im Druckermodell (klein), leer = immer zeigen.
SOURCES = [
    {"name": "Epson-Treiberpaket (Windows/Mac) – enthält die Epson-Papierprofile",
     "url": "https://www.epson.eu/", "match": ["epson"],
     "hint": "Auf der Epson-Supportseite deines Modells den Windows-Treiber (.exe) laden und hier "
             "über „Datei / ZIP / Treiberpaket…“ importieren – die .icc/.icm werden herausgesucht."},
    {"name": "Red River Paper – Profile für Epson-EcoTank mit 502-Tinte (inkl. ET-15000)",
     "url": "https://www.redrivercatalog.com/profiles/inkjet-printer-color-icc-profiles-red-river-paper.html",
     "match": ["epson"], "hint": "Für Red-River-Papiere; als Annäherung auch für ähnliche Oberflächen."},
    {"name": "Marrutt – generische Profile (u. a. ET-4850/ET-15000)",
     "url": "https://marrutt.com/help-support/icc-profiles/icc-profiles-epson-et2850/",
     "match": ["epson"], "hint": "Kostenlos, für Marrutt-Papiere."},
    {"name": "Hahnemühle Download-Center (Fine-Art-Papiere, ZIP je Drucker/Papier)",
     "url": "https://www.hahnemuehle.com/de/digital-fineart/icc-profile/download-center.html",
     "match": [], "hint": "Drucker + Papier wählen, ZIP laden, hier importieren."},
    {"name": "farbenwerk – Profile für Fotopapiere (Deutschland)",
     "url": "https://www.farbenwerk.com/en/pages/icc-profile-downloads",
     "match": [], "hint": "ZIP-Pakete für verschiedene Druckermodelle."},
]


@dataclass
class IccInfo:
    path: str
    name: str            # Dateiname
    desc: str            # Beschreibung aus dem Profil
    space: str           # RGB | CMYK | Gray | …
    klass: str           # prtr (Drucker) | mntr | scnr | spac | …
    ok_output: bool      # als Druckerausgabeprofil verwendbar?

    @property
    def klass_text(self):
        return {"prtr": "Drucker", "mntr": "Monitor", "scnr": "Scanner/Kamera", "spac": "Farbraum",
                "link": "Geräteverknüpfung", "abst": "abstrakt", "nmcl": "Sonderfarben"}.get(self.klass, self.klass)


def sources_for(model: str) -> list[dict]:
    m = (model or "").lower()
    return [s for s in SOURCES if not s["match"] or any(k in m for k in s["match"])]


def icc_info(path: str) -> IccInfo | None:
    try:
        with open(path, "rb") as f:
            head = f.read(128)
    except OSError:
        return None
    if len(head) < 128 or head[36:40] != b"acsp":
        return None
    space = {b"RGB ": "RGB", b"CMYK": "CMYK", b"GRAY": "Gray"}.get(head[16:20], head[16:20].decode("latin-1").strip())
    klass = head[12:16].decode("latin-1").strip()
    desc = ""
    try:
        from PIL import ImageCms
        desc = (ImageCms.getProfileDescription(ImageCms.getOpenProfile(path)) or "").strip()
    except Exception:
        pass
    name = os.path.basename(path)
    return IccInfo(path, name, desc or os.path.splitext(name)[0], space, klass,
                   ok_output=(klass == "prtr" and space in ("RGB", "CMYK", "Gray")))


def download(url: str, dest_dir: str, progress=None) -> str:
    if not re.match(r"^https://", url, re.I):
        raise ValueError(tr("Nur https-Links werden geladen."))
    req = urllib.request.Request(url, headers={"User-Agent": "Passermark/0.9 (ICC-Import)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        ctype = r.headers.get("Content-Type", "")
        if "text/html" in ctype:
            raise ValueError(tr("Der Link führt zu einer Webseite, nicht zu einer Datei. Bitte die Seite im "
                             "Browser öffnen, dort die Datei laden und dann aus der Datei importieren."))
        name = os.path.basename(urllib.parse.urlparse(r.geturl()).path) or "download.bin"
        cd = r.headers.get("Content-Disposition", "")
        m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', cd)
        if m:
            name = os.path.basename(urllib.parse.unquote(m.group(1)))
        out = os.path.join(dest_dir, re.sub(r"[^\w.\-]+", "_", name) or "download.bin")
        total, n = int(r.headers.get("Content-Length") or 0), 0
        with open(out, "wb") as f:
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                n += len(chunk)
                if n > MAX_DOWNLOAD:
                    raise ValueError(tr("Download zu groß."))
                f.write(chunk)
                if progress:
                    progress(n, total)
    return out


def _safe_zip_extract(zf: zipfile.ZipFile, dest: str) -> list[str]:
    out = []
    for info in zf.infolist():
        nm = info.filename
        low = nm.lower()
        if info.is_dir():
            continue
        if low.endswith(ICC_EXT):
            import uuid
            target = os.path.join(dest, uuid.uuid4().hex[:8] + "_" + re.sub(r"[^\w.\-]+", "_", os.path.basename(nm)))
            with zf.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            out.append(target)
        elif low.endswith(".zip") and info.file_size < MAX_DOWNLOAD:     # ZIP im ZIP
            import io
            with zf.open(info) as src:
                try:
                    out += _safe_zip_extract(zipfile.ZipFile(io.BytesIO(src.read())), dest)
                except zipfile.BadZipFile:
                    pass
    return out


def _seven_zip(path: str, dest: str) -> list[str]:
    from . import platform as _platform
    sz = _platform.seven_zip()
    if not sz:
        raise RuntimeError(tr("Zum Entpacken von Treiberpaketen wird 7-Zip benötigt (Linux: p7zip-full, Windows: 7-zip.org)."))
    work = tempfile.mkdtemp(prefix="icc7z-", dir=dest)
    subprocess.run([sz, "x", "-y", f"-o{work}", path], capture_output=True, timeout=600)
    found = []
    for root, _dirs, files in os.walk(work):
        for f in files:
            p = os.path.join(root, f)
            low = f.lower()
            if low.endswith(ICC_EXT):
                found.append(p)
            elif low.endswith((".cab", ".zip", ".7z", ".exe", ".msi", ".pkg", ".dmg")) and root.count(os.sep) < work.count(os.sep) + 6:
                try:
                    found += _seven_zip(p, dest)        # verschachtelte Pakete (Treiber-Setups)
                except RuntimeError:
                    pass
    return found


def extract_icc(path: str, dest: str) -> list[IccInfo]:
    """Datei/Archiv -> Liste gültiger ICC-Profile (doppelte Profile werden zusammengefasst)."""
    low = path.lower()
    files: list[str] = []
    if low.endswith(ICC_EXT) or icc_info(path):
        files = [path]
    elif zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            files = _safe_zip_extract(zf, dest)
    else:
        files = _seven_zip(path, dest)
    seen, out = set(), []
    import hashlib
    for f in files:
        info = icc_info(f)
        if not info:
            continue
        h = hashlib.sha1(open(f, "rb").read()).hexdigest()
        if h in seen:
            continue
        seen.add(h)
        out.append(info)
    out.sort(key=lambda i: (not i.ok_output, i.desc.lower()))
    return out


def profile_id(desc: str, taken: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", desc).strip("_")[:48] or "profil"
    pid, i = base, 2
    while pid in taken:
        pid, i = f"{base}_{i}", i + 1
    return pid
