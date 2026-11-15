# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Updates from the GitHub releases of Passermark (no Qt – the window shows the state, see gui/updatestatus.py).

How an update is applied depends on how Passermark was installed (``install_kind``):

- ``appimage``: download the new AppImage next to the running one, check it, swap it, restart.
- ``windows``: download the setup, check it, run it silently (it closes Passermark and starts it again).
- ``source`` (install.sh): download the source package; root (pkexec passermark-admin update) checks it against
  the checksum it fetches itself and runs install.sh from it.
- ``other`` (e.g. a git checkout): only say that there is a new version and where to get it.

Every download is checked against the ``<file>.sha256`` published with the release; without a matching checksum
nothing is installed. Only the release list is asked for – nothing is sent about the computer or its use.
The administrator can switch the check off or choose the test channel (admin configuration, "updates").
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass, field

from . import __version__

REPO = "groschenheld/passermark"
API = f"https://api.github.com/repos/{REPO}/releases?per_page=20"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
CHECK_EVERY = 24 * 3600  # at most one automatic check a day
TIMEOUT = 10
SOURCE_LIB = "/usr/local/lib/passermark"  # where install.sh puts the program
CHANNELS = ("stable", "test")  # test: pre-releases too
_RX_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-.]?(.*))?$")


def parse_version(text: str) -> tuple | None:
    """ "v1.19.0" -> (1, 19, 0, 1, ""); a suffix ("1.19.0-test1") sorts before the plain version. None if no version."""
    m = _RX_VERSION.match((text or "").strip())
    if not m:
        return None
    major, minor, patch, suffix = int(m[1]), int(m[2]), int(m[3]), m[4] or ""
    return (major, minor, patch, 0 if suffix else 1, suffix)


def is_newer(candidate: str, current: str = __version__) -> bool:
    """Is version ``candidate`` newer than ``current``?"""
    a, b = parse_version(candidate), parse_version(current)
    return a is not None and b is not None and a > b


@dataclass
class Release:
    """One release from GitHub, reduced to what the update needs."""

    version: str
    tag: str
    page: str  # web page of the release
    notes: str = ""
    prerelease: bool = False
    assets: dict[str, str] = field(default_factory=dict)  # file name -> download URL


def _get(url: str, timeout: float = TIMEOUT) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": f"Passermark/{__version__}", "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # fixed https URLs of GitHub
        return r.read()


def releases_from_json(data) -> list[Release]:
    """The usable releases from the GitHub answer (no drafts, only tags that are versions), newest first."""
    out = []
    for r in data if isinstance(data, list) else []:
        if not isinstance(r, dict) or r.get("draft"):
            continue
        tag = str(r.get("tag_name", ""))
        if parse_version(tag) is None:
            continue
        assets = {
            str(a.get("name")): str(a.get("browser_download_url"))
            for a in r.get("assets", []) or []
            if isinstance(a, dict) and a.get("name") and a.get("browser_download_url")
        }
        out.append(
            Release(
                version=tag.lstrip("v"),
                tag=tag,
                page=str(r.get("html_url") or RELEASES_PAGE),
                notes=str(r.get("body") or ""),
                prerelease=bool(r.get("prerelease")),
                assets=assets,
            )
        )
    out.sort(key=lambda r: parse_version(r.tag), reverse=True)
    return out


def newest(releases: list[Release], channel: str = "stable", current: str = __version__) -> Release | None:
    """The newest release of the channel that is newer than ``current`` – or None.

    The stable channel only takes plain versions (``v1.19.1``): a release marked as pre-release on GitHub or a tag
    with a suffix (``v1.19.1-test1``, ``v1.19.1-fix``) only goes to the test channel."""
    for r in releases:
        if channel != "test" and (r.prerelease or (parse_version(r.version) or (0, 0, 0, 0, ""))[4]):
            continue
        return r if is_newer(r.version, current) else None
    return None


def check(channel: str = "stable", fetch=_get) -> Release | None:
    """Ask GitHub; the newer release or None. Raises OSError/ValueError if GitHub cannot be reached or answers
    nonsense (the caller shows "no connection")."""
    try:
        data = json.loads(fetch(API).decode("utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"GitHub answer not readable: {e}") from e
    return newest(releases_from_json(data), channel)


# ---- configuration (admin) and memory of the last check (user) ---- #
def settings(cfg: dict) -> dict:
    """The update settings of the admin configuration: {"enabled": bool, "channel": "stable"|"test"}."""
    u = cfg.get("updates") if isinstance(cfg.get("updates"), dict) else {}
    channel = u.get("channel", "stable")
    return {"enabled": u.get("enabled", True) is not False, "channel": channel if channel in CHANNELS else "stable"}


def due(last_check: float | None, now: float | None = None) -> bool:
    """Is an automatic check due (none in the last CHECK_EVERY seconds)?"""
    now = time.time() if now is None else now
    return not last_check or now - last_check >= CHECK_EVERY or now < last_check


# ---- how this Passermark was installed ---- #
def install_kind(environ=os.environ, frozen=None, platform=sys.platform, module_file=__file__) -> str:
    """ "appimage", "windows", "source" (install.sh) or "other" – see the module text."""
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if environ.get("APPIMAGE") and os.path.isfile(environ["APPIMAGE"]):
        return "appimage"
    if frozen and platform == "win32":
        return "windows"
    if os.path.realpath(module_file).startswith(SOURCE_LIB + os.sep):
        return "source"
    return "other"


def asset_name(release: Release, kind: str) -> str | None:
    """The file of the release that this installation needs – or None (then only point to the release page)."""
    names = list(release.assets)
    if kind == "appimage":
        cands = [n for n in names if n.endswith(".AppImage")]
    elif kind == "windows":
        cands = [n for n in names if n.endswith("-Setup.exe")]
    elif kind == "source":
        cands = [n for n in names if n == f"passermark-src-{release.version}.tar.gz"]
    else:
        cands = []
    return cands[0] if cands else None


def can_apply(release: Release, kind: str) -> bool:
    """Can this installation update itself to ``release`` (file and its checksum published)?"""
    name = asset_name(release, kind)
    return bool(name and name + ".sha256" in release.assets)


# ---- download and check ---- #
def expected_sha256(text: str, name: str) -> str | None:
    """The checksum for ``name`` from a "<hash>  <file>" text (sha256sum format; a lone hash counts too)."""
    for line in text.splitlines():
        parts = line.strip().split()
        if not parts or not re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            continue
        if len(parts) == 1 or parts[-1].lstrip("*") == name:
            return parts[0].lower()
    return None


def sha256_of(path: str) -> str:
    """SHA-256 of a file (hex)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


class UpdateError(Exception):
    """An update could not be downloaded, checked or applied – the text is shown to the user."""


def download(release: Release, kind: str, dest_dir: str | None = None, progress=None, opener=urllib.request.urlopen):
    """Download the file this installation needs and check it against its published checksum -> local path.
    ``progress(done_bytes, total_bytes)`` is called while downloading. Raises UpdateError."""
    name = asset_name(release, kind)
    if not name or name + ".sha256" not in release.assets:
        raise UpdateError("Zu dieser Version gibt es keine passende Datei mit Prüfsumme.")
    try:
        want = expected_sha256(_get(release.assets[name + ".sha256"]).decode("utf-8", "replace"), name)
    except OSError as e:
        raise UpdateError(f"Prüfsumme nicht ladbar: {e}") from e
    if not want:
        raise UpdateError("Die veröffentlichte Prüfsumme ist nicht lesbar.")
    dest_dir = dest_dir or tempfile.mkdtemp(prefix="passermark-update-")
    path = os.path.join(dest_dir, name)
    req = urllib.request.Request(release.assets[name], headers={"User-Agent": f"Passermark/{__version__}"})
    try:
        with opener(req, timeout=60) as r, open(path, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while True:
                block = r.read(1 << 16)
                if not block:
                    break
                f.write(block)
                done += len(block)
                if progress:
                    progress(done, total)
    except OSError as e:
        raise UpdateError(f"Download fehlgeschlagen: {e}") from e
    if sha256_of(path) != want:
        os.remove(path)
        raise UpdateError("Die Prüfsumme stimmt nicht – die Datei wurde verworfen.")
    return path


# ---- apply ---- #
def replace_appimage(new_file: str, target: str) -> str:
    """Swap the running AppImage for the new one (same folder, atomically) -> path of the new AppImage.
    Raises UpdateError if the folder is not writable."""
    folder = os.path.dirname(os.path.abspath(target))
    if not os.access(folder, os.W_OK):
        raise UpdateError(f"Keine Schreibrechte im Ordner {folder} – bitte die neue Datei selbst dorthin kopieren.")
    tmp = os.path.join(folder, f".{os.path.basename(target)}.update")
    try:
        with open(new_file, "rb") as src, open(tmp, "wb") as dst:
            for block in iter(lambda: src.read(1 << 20), b""):
                dst.write(block)
        os.chmod(tmp, 0o755)
        os.replace(tmp, target)
    except OSError as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise UpdateError(f"AppImage nicht ersetzt: {e}") from e
    return target


def windows_setup_command(setup: str) -> list[str]:
    """Silent setup; /AUTOUPDATE lets the installer start Passermark again afterwards (windows/passermark.iss)."""
    return [setup, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/AUTOUPDATE"]


def source_update_command(release: Release, tarball: str) -> list[str]:
    """Root installs the source package (pkexec asks for the password; the helper fetches the checksum itself)."""
    return ["pkexec", "/usr/libexec/passermark-admin", "update", release.version, tarball]
