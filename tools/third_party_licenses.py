#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Collect the licence texts of everything Passermark ships (for the Windows installer and the AppImage).

Run with the Python of the BUILD environment (the one PyInstaller uses), after PyInstaller:

    python tools/third_party_licenses.py OUTDIR [--requirements FILE] [--gs-version 10.05.1]
                                               [--gs-source-note TEXT] [--agpl FILE]
                                               [--deb-packages PKG ...] [--scan-libs DIR ...]

Writes into OUTDIR:
    THIRD_PARTY_NOTICES.txt      overview: every bundled component, version, licence, homepage, files
    python-packages/<name>-<ver>/  licence files from each package's *.dist-info (LICENSE, COPYING, NOTICE …)
    texts/                       GPL-3.0, LGPL-3.0, MPL-2.0 (from the repository), AGPL-3.0 (--agpl), Python
    QT-LGPL-NOTICE.txt           Qt / PySide6: LGPL-3 notice, where the Qt libraries are, how to replace them
    GHOSTSCRIPT-NOTICE.txt       (with --gs-version) AGPL-3 notice and where to get the source of that version
    system/<package>.copyright   (with --scan-libs, Debian/Ubuntu) copyright files of bundled system libraries

Only the standard library is used. Missing pieces produce a warning, never a failed build.
"""
from __future__ import annotations

import argparse
import importlib.metadata as md
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# build tools that are NOT shipped
BUILD_ONLY = {"pyinstaller", "pyinstaller-hooks-contrib", "pip", "setuptools", "wheel", "altgraph", "macholib",
              "pefile", "pywin32-ctypes", "packaging"}
ALWAYS = ["PySide6", "PySide6-Essentials", "PySide6-Addons", "shiboken6"]
LICENSE_RE = re.compile(r"^(licen[cs]e|copying|notice|authors|copyright)", re.I)


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def warn(msg: str):
    print("::warning::" + msg if os.environ.get("GITHUB_ACTIONS") else "WARNING: " + msg, file=sys.stderr)


# ------------------------------------------------------------------ Python packages
def requirement_names(path: str) -> list[str]:
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.split("#", 1)[0].strip()
                m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)", line)
                if m:
                    out.append(m.group(1))
    except OSError:
        warn(f"requirements file not found: {path}")
    return out


def _marker_ok(req: str) -> bool:
    """Evaluate the environment marker of a Requires-Dist line; extras are never installed for us."""
    if ";" not in req:
        return True
    marker = req.split(";", 1)[1]
    if "extra" in marker:
        return False
    try:
        from packaging.markers import Marker
        return Marker(marker).evaluate()
    except Exception:
        return True


def closure(names: list[str]) -> dict:
    """Installed distributions for these names and all their (installed) dependencies."""
    found: dict = {}
    todo = list(names)
    while todo:
        n = norm(todo.pop())
        if n in found or n in BUILD_ONLY:
            continue
        try:
            dist = md.distribution(n)
        except md.PackageNotFoundError:
            continue
        found[n] = dist
        for req in dist.requires or []:
            if _marker_ok(req):
                m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)", req.strip())
                if m:
                    todo.append(m.group(1))
    return found


def license_of(dist) -> str:
    meta = dist.metadata
    expr = meta.get("License-Expression")
    if expr:
        return expr
    lic = (meta.get("License") or "").strip()
    if lic and len(lic) <= 80 and "\n" not in lic:
        return lic
    cls = [c.split("::")[-1].strip() for c in meta.get_all("Classifier") or [] if c.startswith("License ::")]
    if cls:
        return ", ".join(dict.fromkeys(cls))
    return "see licence files" if lic else "unknown"


def homepage_of(dist) -> str:
    meta = dist.metadata
    if meta.get("Home-page"):
        return meta["Home-page"]
    for u in meta.get_all("Project-URL") or []:
        label, _, url = u.partition(",")
        if label.strip().lower() in ("homepage", "home", "source", "source code", "repository"):
            return url.strip()
    urls = [u.partition(",")[2].strip() for u in meta.get_all("Project-URL") or []]
    urls = [u for u in urls if not re.search(r"changelog|issues|funding|donate|docs?\b", u, re.I)] or urls
    return urls[0] if urls else ""


def copy_license_files(dist, dest: str) -> list[str]:
    copied = []
    for f in dist.files or []:
        parts = str(f).replace("\\", "/").split("/")
        in_meta = parts[0].endswith((".dist-info", ".egg-info"))
        name = parts[-1]
        wanted = (in_meta and ("licenses" in parts[1:-1] or LICENSE_RE.match(name))) or \
                 (not in_meta and LICENSE_RE.match(name) and len(parts) <= 3)
        if not wanted or name.endswith((".py", ".pyc")):
            continue
        src = str(dist.locate_file(f))
        if not os.path.isfile(src):
            continue
        rel = "/".join(parts[1:]) if in_meta else "/".join(parts)
        if in_meta and parts[1:2] == ["licenses"]:
            rel = "/".join(parts[2:])
        out = os.path.join(dest, *rel.split("/"))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        shutil.copyfile(src, out)
        copied.append(rel)
    return sorted(set(copied))


# Packages whose wheels/system packages ship no licence file: licence text from this repository.
# (PySide6/shiboken6 wheels never contain one; Debian's python3-lxml/python3-cups keep it in /usr/share/doc.)
KNOWN = {
    "pyside6": ("LGPL-3.0", "licenses/LGPL-3.0.txt", "see QT-LGPL-NOTICE.txt"),
    "pyside6-essentials": ("LGPL-3.0", "licenses/LGPL-3.0.txt", "see QT-LGPL-NOTICE.txt"),
    "pyside6-addons": ("LGPL-3.0", "licenses/LGPL-3.0.txt", "see QT-LGPL-NOTICE.txt"),
    "pyside6-pdf": ("LGPL-3.0", "licenses/LGPL-3.0.txt", "see QT-LGPL-NOTICE.txt"),
    "pyside6-webengine": ("LGPL-3.0", "licenses/LGPL-3.0.txt", "see QT-LGPL-NOTICE.txt"),
    "shiboken6": ("LGPL-3.0", "licenses/LGPL-3.0.txt", "see QT-LGPL-NOTICE.txt"),
    "lxml": ("BSD-3-Clause", "licenses/lxml-BSD-3-Clause.txt", "Copyright (c) 2004 Infrae"),
    "pycups": ("GPL-2.0-or-later", "licenses/GPL-2.0.txt", "Copyright (C) Tim Waugh, Red Hat, Inc. and contributors"),
}


def debian_copyright(dist, dest: str) -> str:
    """Python package from a Debian/Ubuntu system package: copy /usr/share/doc/<pkg>/copyright."""
    if not shutil.which("dpkg"):
        return ""
    try:
        meta_dir = str(dist.locate_file(next(f for f in dist.files or [] if str(f).endswith("METADATA"))))
    except StopIteration:
        meta_dir = getattr(dist, "_path", "")
        meta_dir = str(meta_dir)
    if not meta_dir or not meta_dir.startswith("/usr/"):
        return ""
    try:
        r = subprocess.run(["dpkg", "-S", meta_dir], capture_output=True, text=True, timeout=60)
    except Exception:
        return ""
    for line in r.stdout.splitlines():
        pkg = line.split(":", 1)[0].split(",")[0].strip()
        src = f"/usr/share/doc/{pkg}/copyright"
        if pkg and os.path.isfile(src):
            os.makedirs(dest, exist_ok=True)
            shutil.copyfile(src, os.path.join(dest, "copyright"))
            return "copyright"
    return ""


def known_license(key: str, dest: str) -> str:
    k = KNOWN.get(key)
    if not k:
        return ""
    spdx, text, note = k
    src = os.path.join(ROOT, text)
    if not os.path.isfile(src):
        return ""
    os.makedirs(dest, exist_ok=True)
    name = "LICENSE-" + spdx + ".txt"
    shutil.copyfile(src, os.path.join(dest, name))
    with open(os.path.join(dest, "NOTE.txt"), "w", encoding="utf-8") as f:
        f.write(f"The package ships no licence file of its own.\nLicence: {spdx} ({name}). {note}.\n")
    return name


# ------------------------------------------------------------------ system libraries (Debian/Ubuntu)
def dpkg_packages(dirs: list[str]) -> dict:
    """Shared libraries in these folders -> Debian package that installed them (by file name)."""
    if not shutil.which("dpkg"):
        warn("dpkg not available – copyright files of system libraries not collected")
        return {}
    names = set()
    for d in dirs:
        for base, _sub, files in os.walk(d):
            for fn in files:
                if ".so" in fn:
                    names.add(fn)
    pkgs: dict = {}
    names = sorted(names)
    for i in range(0, len(names), 200):                  # wenige dpkg-Aufrufe statt einem je Datei
        chunk = names[i:i + 200]
        try:
            r = subprocess.run(["dpkg", "-S", *["*/" + n for n in chunk]], capture_output=True, text=True,
                               timeout=120)
        except Exception:
            continue
        for line in r.stdout.splitlines():
            if ": " not in line or line.startswith("diversion"):
                continue
            left, path = line.split(": ", 1)
            fn = os.path.basename(path.strip())
            if fn not in chunk:
                continue
            for pkg in left.split(","):
                pkg = pkg.strip().split(":")[0]           # Architektur-Zusatz (:amd64) weg
                if pkg:
                    pkgs.setdefault(pkg, set()).add(fn)
                    break
    return pkgs


def dpkg_version(pkg: str) -> str:
    try:
        r = subprocess.run(["dpkg-query", "-W", "-f=${Version}", pkg], capture_output=True, text=True, timeout=30)
        return r.stdout.strip()
    except Exception:
        return ""


# ------------------------------------------------------------------ notices
QT_NOTICE = """Qt for Python (PySide6, shiboken6) and the Qt libraries {ver}
==============================================================

Copyright (C) The Qt Company Ltd. and other contributors.
Licence: GNU Lesser General Public License version 3 (LGPL-3.0), see texts/LGPL-3.0.txt
(it refers to the GNU General Public License version 3, see texts/GPL-3.0.txt).

Passermark uses the Qt libraries unmodified and links them dynamically. They are shipped as
separate files, so you may replace them with your own (modified) compatible build:

  Windows (installed program):  <program folder>\\_internal\\PySide6\\  (Qt6*.dll, plugins\\)
  AppImage:  run  ./Passermark-*.AppImage --appimage-extract , then replace the files in
             squashfs-root/usr/lib/passermark/_internal/PySide6/Qt/lib/  and
             squashfs-root/usr/lib/passermark/_internal/libQt6*.so.6 , start squashfs-root/AppRun

Source code of this version:
  Qt for Python:  https://code.qt.io/cgit/pyside/pyside-setup.git/tag/?h=v{ver}
                  https://download.qt.io/official_releases/QtForPython/
  Qt:             https://download.qt.io/official_releases/qt/
On request the author of Passermark also provides the corresponding source code (see README).

Deutsch: Passermark verwendet Qt for Python und die Qt-Bibliotheken {ver} unverändert und dynamisch
gebunden unter der LGPL-3.0. Die Bibliotheken liegen als eigene Dateien bei und dürfen durch eigene,
kompatible Fassungen ersetzt werden (Pfade siehe oben). Quellcode: Links oben.
"""

GS_NOTICE = """Ghostscript {ver}
================

Copyright (C) Artifex Software, Inc.
Licence: GNU Affero General Public License version 3 (AGPL-3.0), see {agpl}

Passermark ships Ghostscript unmodified as a separate program (gswin64c.exe / gs) and runs it as an
independent process for repairs, CMYK conversion and font embedding.

Source code of exactly this version:
  https://github.com/ArtifexSoftware/ghostpdl/tree/ghostpdl-{ver}
  https://github.com/ArtifexSoftware/ghostpdl-downloads/releases/tag/gs{tag}
  https://ghostscript.com/releases/gpldnld.html
{extra}On request the author of Passermark also provides the corresponding source code (see README).

Deutsch: Ghostscript {ver} liegt unverändert als eigenständiges Programm bei (AGPL-3.0). Quellcode genau
dieser Version: Links oben.
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("outdir")
    ap.add_argument("--requirements", default=os.path.join(ROOT, "requirements.txt"))
    ap.add_argument("--gs-version", default="")
    ap.add_argument("--gs-source-note", default="", help="extra line(s) for the Ghostscript notice")
    ap.add_argument("--agpl", default="", help="file with the full AGPL-3.0 text (e.g. Debian's ghostscript copyright)")
    ap.add_argument("--deb-packages", nargs="*", default=[],
                    help="further Debian packages shipped as files (e.g. ghostscript resources, fonts-urw-base35)")
    ap.add_argument("--scan-libs", nargs="*", default=[], help="folders with bundled system libraries (dpkg lookup)")
    a = ap.parse_args(argv)

    out = os.path.abspath(a.outdir)
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(os.path.join(out, "texts"))
    lines = ["Passermark – third-party components / Komponenten von Drittanbietern", "=" * 68, "",
             "Passermark itself: GNU General Public License v3 or later (LICENSE, texts/GPL-3.0.txt).",
             "Below: everything that is shipped with the program, with its licence and where its licence",
             "files are in this folder. / Unten: alles, was mit dem Programm mitgeliefert wird.", ""]

    # licence texts from the repository
    for src, dst in (("LICENSE", "GPL-3.0.txt"), ("licenses/LGPL-3.0.txt", "LGPL-3.0.txt"),
                     ("licenses/MPL-2.0.txt", "MPL-2.0.txt"), ("licenses/GPL-2.0.txt", "GPL-2.0.txt")):
        p = os.path.join(ROOT, src)
        if os.path.isfile(p):
            shutil.copyfile(p, os.path.join(out, "texts", dst))
        else:
            warn(f"missing licence text: {src}")
    agpl_rel = "texts/AGPL-3.0.txt"
    if a.agpl and os.path.isfile(a.agpl):
        shutil.copyfile(a.agpl, os.path.join(out, "texts", "AGPL-3.0.txt"))
    elif a.gs_version:
        agpl_rel = "https://www.gnu.org/licenses/agpl-3.0.txt"
        warn("AGPL-3.0 text not supplied (--agpl) – the notice links to gnu.org instead")

    # Python runtime
    py_lic = None
    for cand in (os.path.join(sys.base_prefix, "LICENSE.txt"),
                 os.path.join(sys.base_prefix, "lib", f"python{sys.version_info[0]}.{sys.version_info[1]}", "LICENSE.txt"),
                 f"/usr/lib/python{sys.version_info[0]}.{sys.version_info[1]}/LICENSE.txt",
                 f"/usr/share/doc/python{sys.version_info[0]}.{sys.version_info[1]}/copyright"):
        if os.path.isfile(cand):
            py_lic = cand
            break
    lines += ["Python runtime", "-" * 14, ""]
    if py_lic:
        shutil.copyfile(py_lic, os.path.join(out, "texts", "Python-LICENSE.txt"))
        lines.append(f"  Python {sys.version.split()[0]}  ·  PSF-2.0  ·  https://www.python.org  ·  texts/Python-LICENSE.txt")
    else:
        lines.append(f"  Python {sys.version.split()[0]}  ·  PSF-2.0  ·  https://docs.python.org/3/license.html")
        warn("Python licence file not found")
    lines.append("")

    # Python packages
    names = requirement_names(a.requirements) + ALWAYS
    dists = closure(names)
    lines += ["Python packages", "-" * 15, ""]
    qt_ver = ""
    for key in sorted(dists):
        d = dists[key]
        nm, ver = d.metadata["Name"], d.version
        if norm(nm) in ("pyside6", "pyside6-essentials", "shiboken6"):
            qt_ver = qt_ver or ver
        dest = os.path.join(out, "python-packages", f"{norm(nm)}-{ver}")
        files = copy_license_files(d, dest)
        if not files:
            files = [f for f in (debian_copyright(d, dest), known_license(norm(nm), dest)) if f]
            if files and os.path.isfile(os.path.join(dest, "NOTE.txt")):
                files.append("NOTE.txt")
        lic = license_of(d)
        if lic in ("unknown", "see licence files") and norm(nm) in KNOWN:
            lic = KNOWN[norm(nm)][0]
        home = homepage_of(d)
        lines.append(f"  {nm} {ver}  ·  {lic}" + (f"  ·  {home}" if home else ""))
        if files:
            for f in files:
                lines.append(f"      python-packages/{norm(nm)}-{ver}/{f}")
        else:
            if os.path.isdir(dest) and not os.listdir(dest):
                os.rmdir(dest)
            lines.append("      (no licence file in the package – see the homepage)")
            warn(f"no licence file found for {nm} {ver}")
        if any(t in lic.upper() for t in ("LGPL", "LESSER")):
            lines.append("      LGPL: texts/LGPL-3.0.txt")
        if "MPL" in lic.upper():
            lines.append("      MPL: texts/MPL-2.0.txt")
    lines.append("")

    # Qt notice
    if qt_ver:
        with open(os.path.join(out, "QT-LGPL-NOTICE.txt"), "w", encoding="utf-8") as f:
            f.write(QT_NOTICE.format(ver=qt_ver))
        lines += ["Qt / PySide6", "-" * 12, "", f"  Qt for Python {qt_ver}  ·  LGPL-3.0  ·  QT-LGPL-NOTICE.txt", ""]
    else:
        warn("PySide6 not found in the build environment")

    # Ghostscript notice
    if a.gs_version:
        extra = (a.gs_source_note.strip() + "\n") if a.gs_source_note.strip() else ""
        with open(os.path.join(out, "GHOSTSCRIPT-NOTICE.txt"), "w", encoding="utf-8") as f:
            f.write(GS_NOTICE.format(ver=a.gs_version, tag=a.gs_version.replace(".", ""), agpl=agpl_rel,
                                     extra=extra))
        lines += ["Ghostscript", "-" * 11, "",
                  f"  Ghostscript {a.gs_version}  ·  AGPL-3.0  ·  GHOSTSCRIPT-NOTICE.txt, {agpl_rel}", ""]

    # system libraries (AppImage)
    if a.scan_libs or a.deb_packages:
        pkgs = dpkg_packages(a.scan_libs) if a.scan_libs else {}
        for p in a.deb_packages:
            if dpkg_version(p):
                pkgs.setdefault(p, set()).add("(resources / Ressourcen)")
        if pkgs:
            os.makedirs(os.path.join(out, "system"))
            lines += ["System libraries (from the build system's Debian/Ubuntu packages)", "-" * 66, ""]
            for pkg in sorted(pkgs):
                cp = f"/usr/share/doc/{pkg}/copyright"
                ver = dpkg_version(pkg)
                if os.path.isfile(cp):
                    shutil.copyfile(cp, os.path.join(out, "system", f"{pkg}.copyright"))
                    lines.append(f"  {pkg} {ver}  ·  system/{pkg}.copyright  ·  source: apt-get source {pkg}={ver}")
                else:
                    lines.append(f"  {pkg} {ver}  ·  source: apt-get source {pkg}={ver}")
                lines.append("      " + ", ".join(sorted(pkgs[pkg])[:6]) + (" …" if len(pkgs[pkg]) > 6 else ""))
            lines.append("")

    with open(os.path.join(out, "THIRD_PARTY_NOTICES.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"third-party licences: {len(dists)} Python packages -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
