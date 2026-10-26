# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Shared print folder for Passermark and all add-on programs (Passermark-GUI, Passerlink, PassCount …).

    Linux:   /srv/passermark/{hotfolder,ausgabe,archiv}, group passermark, root:passermark 2775 (setgid) plus
             default ACL g:passermark:rwX – services run with UMask=0007 and are members of the group.
    Windows: %ProgramData%\\Passermark\\{hotfolder,ausgabe,archiv}, users may modify ONLY these three subfolders –
             %ProgramData%\\Passermark itself stays read-only for users (admin defaults, profiles, workflows).

Setting up needs root (Linux: root helper passermark-admin shared-folder, via pkexec) or the installer (Windows).
This module only reads (status, paths, warnings) and starts the helper. No Qt.
"""
from __future__ import annotations

import os
import subprocess
import sys

from .platform import IS_WIN

SUBDIRS = ("hotfolder", "ausgabe", "archiv")
GROUP = "passermark"


def root() -> str:
    if IS_WIN:
        return os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "Passermark")
    return "/srv/passermark"


def path(sub: str = "hotfolder") -> str:
    return os.path.join(root(), sub)


def hotfolder_dir() -> str:
    """Vorschlag für neue Hotfolder/Drop-Ordner: im gemeinsamen Ordner, sonst (noch nicht eingerichtet) das Home."""
    d = path("hotfolder")
    return d if os.path.isdir(d) else os.path.expanduser("~")


def in_home(p: str) -> bool:
    """Ordner in einem Home-Verzeichnis – für Dienste (eigene Benutzer) meist gesperrt."""
    if not p:
        return False
    a = os.path.normcase(os.path.abspath(os.path.expanduser(p)))
    if IS_WIN:
        users = os.path.normcase(os.path.join(os.environ.get("SystemDrive", "C:") + os.sep, "Users"))
        return a == users or a.startswith(users + os.sep)
    return a == "/home" or a.startswith("/home/") or a == "/root" or a.startswith("/root/")


def home_hint() -> str:
    from .l10n import tr
    return tr("Ordner liegt in einem Home-Verzeichnis – Dienste anderer Benutzer (Watcher, Passerlink …) dürfen dort "
              "meist nicht schreiben. Besser unter {0}.").format(path("hotfolder"))


def status() -> dict:
    """{root, exists, dirs: {name: {exists, writable}}, group (Linux: gibt's die Gruppe), member (aktiver Benutzer in
        der Gruppe – None unter Windows), member_pending (in /etc/group, aber noch nicht angemeldet), ok}."""
    r = root()
    dirs = {}
    for s in SUBDIRS:
        p = os.path.join(r, s)
        dirs[s] = {"path": p, "exists": os.path.isdir(p), "writable": os.path.isdir(p) and os.access(p, os.W_OK)}
    out = {"root": r, "exists": os.path.isdir(r), "dirs": dirs, "group": None, "member": None,
           "member_pending": False}
    if not IS_WIN:
        try:
            import grp
            import pwd
            g = grp.getgrnam(GROUP)
            out["group"] = True
            me = pwd.getpwuid(os.getuid()).pw_name
            active = g.gr_gid in os.getgroups() or g.gr_gid == os.getgid()
            listed = me in g.gr_mem or pwd.getpwnam(me).pw_gid == g.gr_gid
            out["member"] = active
            out["member_pending"] = listed and not active
        except (ImportError, KeyError):
            out["group"] = False
            out["member"] = False
    out["ok"] = bool(out["exists"] and all(d["writable"] for d in dirs.values()))
    return out


def status_text(st: dict | None = None) -> str:
    from .l10n import tr
    st = st or status()
    if st["ok"]:
        return tr("Gemeinsamer Druckordner {0}: eingerichtet, beschreibbar.").format(st["root"])
    if not st["exists"] or not all(d["exists"] for d in st["dirs"].values()):
        return tr("Gemeinsamer Druckordner {0}: noch nicht eingerichtet.").format(st["root"])
    if st.get("member_pending"):
        return tr("Gemeinsamer Druckordner {0}: du bist in der Gruppe {1} – neu anmelden, dann ist er "
                  "beschreibbar.").format(st["root"], GROUP)
    if st.get("member") is False:
        return tr("Gemeinsamer Druckordner {0}: vorhanden, aber du bist nicht in der Gruppe {1}.").format(st["root"], GROUP)
    return tr("Gemeinsamer Druckordner {0}: vorhanden, aber nicht beschreibbar.").format(st["root"])


def helper_cmd() -> list:
    """Root-Helfer aufrufen: als root direkt, sonst über pkexec. Installiert: /usr/libexec/passermark-admin;
        AppImage: das AppImage selbst (--admin-helper); aus dem Quellordner: admin/passermark-admin."""
    from . import config
    appimage = os.environ.get("APPIMAGE")
    if os.path.exists(config.HELPER):
        cmd = [config.HELPER]
    elif appimage:
        cmd = ["env", "APPIMAGE_EXTRACT_AND_RUN=1", appimage, "--admin-helper"]
    else:
        src = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "admin", "passermark-admin"))
        cmd = [sys.executable, "-I", src]
    return cmd if os.geteuid() == 0 else ["pkexec"] + cmd


def setup(users: list | None = None) -> tuple[int, str]:
    """Linux: einrichten über den Root-Helfer (ein Passwort). users leer = der aufrufende Benutzer.
        -> (Rückgabecode, Ausgabe). 126/127 = abgebrochen bzw. pkexec fehlt."""
    if IS_WIN:
        from .l10n import tr
        return 1, tr("Unter Windows richtet das Setup den Ordner ein (Passermark neu installieren bzw. reparieren).")
    users = list(users or [])
    if not users and os.geteuid() != 0:
        try:
            import pwd
            users = [pwd.getpwuid(os.getuid()).pw_name]
        except (ImportError, KeyError):
            users = []
    try:
        r = subprocess.run(helper_cmd() + ["shared-folder"] + users, capture_output=True, text=True)
    except FileNotFoundError:
        from .l10n import tr
        return 127, tr("pkexec wurde nicht gefunden (Paket polkit).")
    return r.returncode, (r.stdout + ("\n" + r.stderr if r.stderr else "")).strip()
