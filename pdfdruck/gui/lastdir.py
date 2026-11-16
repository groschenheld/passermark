# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Last used folder: file dialogs (open, save, export …) start where the user worked last – also after a restart.

The dialogs call ``lastdir.getOpenFileName`` … instead of the static QFileDialog functions. A suggested folder of the program itself (fonts, ICC profiles, hot folders,
configuration, system folders) is kept; an empty suggestion, a bare file name, the home folder or a document
folder is replaced by the last used folder – the suggested file name stays.
"""

from __future__ import annotations

import os
import sys

from .. import l10n

SETTING = "last_dir"


def _special_roots() -> list[str]:
    home = os.path.expanduser("~")
    roots = [os.path.join(home, ".config"), os.path.join(home, ".local"), os.path.join(home, ".color")]
    if sys.platform == "win32":
        roots += [os.environ.get(k, "") for k in ("APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "WINDIR", "PROGRAMFILES")]
    else:
        roots += ["/usr", "/etc", "/srv", "/opt", "/var"]
    if os.environ.get("XDG_CONFIG_HOME"):
        roots.append(os.environ["XDG_CONFIG_HOME"])
    return [os.path.normcase(os.path.abspath(r)) for r in roots if r]


def _is_special(folder: str) -> bool:
    """Folder that belongs to the program or the system (kept as the dialog's start folder, not remembered)."""
    f = os.path.normcase(os.path.abspath(folder))
    return any(f == r or f.startswith(r + os.sep) for r in _special_roots())


def last() -> str:
    """The last used folder, if it still exists – otherwise ""."""
    d = l10n.load_settings().get(SETTING)
    return d if isinstance(d, str) and os.path.isdir(d) else ""


def remember(path: str):
    """Remember the folder of ``path`` (a file or a folder) as the last used one."""
    if not isinstance(path, str) or not path:
        return
    folder = path if os.path.isdir(path) else os.path.dirname(path)
    if not folder or not os.path.isdir(folder) or _is_special(folder):
        return
    st = l10n.load_settings()
    if st.get(SETTING) == folder:
        return
    st[SETTING] = folder
    try:
        l10n.save_settings(st)
    except (OSError, TypeError, ValueError):
        pass  # remembering is a convenience


def start(given: str) -> str:
    """Start path for a file dialog: ``given`` with its folder replaced by the last used one (see module text)."""
    d = last()
    given = given if isinstance(given, str) else ""
    if not d:
        return given
    if not given:
        return d
    if os.path.isdir(given):
        return given if _is_special(given) else d
    folder = os.path.dirname(given)
    if folder and _is_special(folder):
        return given
    return os.path.join(d, os.path.basename(given))


def _first_path(res):
    """Chosen path from the result of a static QFileDialog function (str, (str, filter), ([str], filter))."""
    if isinstance(res, tuple) and res:
        res = res[0]
    if isinstance(res, list):
        res = res[0] if res else ""
    return res if isinstance(res, str) else ""


def _call(name: str, args: tuple, kw: dict):
    """Static QFileDialog function ``name`` with the start folder from ``start`` – remembers the choice."""
    from PySide6.QtWidgets import QFileDialog

    a = list(args)
    if "dir" in kw:
        kw["dir"] = start(kw["dir"])
    elif len(a) >= 3:
        a[2] = start(a[2])
    elif len(a) == 2:
        a.append(start(""))
    res = getattr(QFileDialog, name)(*a, **kw)
    remember(_first_path(res))
    return res


def getOpenFileName(*args, **kw):  # noqa: N802 – same name as in Qt
    """QFileDialog.getOpenFileName, starting in the last used folder."""
    return _call("getOpenFileName", args, kw)


def getOpenFileNames(*args, **kw):  # noqa: N802 – same name as in Qt
    """QFileDialog.getOpenFileNames, starting in the last used folder."""
    return _call("getOpenFileNames", args, kw)


def getSaveFileName(*args, **kw):  # noqa: N802 – same name as in Qt
    """QFileDialog.getSaveFileName, starting in the last used folder."""
    return _call("getSaveFileName", args, kw)


def getExistingDirectory(*args, **kw):  # noqa: N802 – same name as in Qt
    """QFileDialog.getExistingDirectory, starting in the last used folder."""
    return _call("getExistingDirectory", args, kw)
