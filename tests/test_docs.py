# SPDX-License-Identifier: GPL-3.0-or-later
"""The code documentation stays in step with the code."""

import ast
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_module_overview_current():
    """docs/architecture.md lists every module with its current summary (tools/module_overview.py)."""
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "module_overview.py"), "--check"])
    assert r.returncode == 0, "run: python3 tools/module_overview.py"


def test_every_module_has_a_docstring():
    """Each module says at the top what it is for."""
    missing = []
    for folder in ("pdfdruck", os.path.join("pdfdruck", "gui")):
        for name in sorted(os.listdir(os.path.join(ROOT, folder))):
            if not name.endswith(".py") or name == "__init__.py":
                continue
            with open(os.path.join(ROOT, folder, name), encoding="utf-8") as f:
                if not ast.get_docstring(ast.parse(f.read())):
                    missing.append(os.path.join(folder, name))
    assert not missing, missing


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
