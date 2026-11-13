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


# Qt and container overrides whose meaning is defined by the base class
INHERITED = {
    "paintEvent", "resizeEvent", "closeEvent", "keyPressEvent", "mousePressEvent", "mouseMoveEvent",
    "mouseReleaseEvent", "wheelEvent", "showEvent", "eventFilter", "sizeHint", "minimumSizeHint", "dragEnterEvent",
    "dropEvent", "rowCount", "columnCount", "data", "headerData", "flags", "run", "accept", "reject", "done", "event",
    "leaveEvent", "enterEvent", "contextMenuEvent", "mouseDoubleClickEvent", "keyReleaseEvent", "changeEvent",
    "hideEvent", "focusOutEvent", "timerEvent", "dragMoveEvent", "heightForWidth", "hasHeightForWidth", "setGeometry",
    "addItem", "count", "itemAt", "takeAt", "expandingDirections", "minimumSize", "setData",
}  # fmt: skip


def test_public_api_is_documented():
    """Every public class, function and method has a docstring (nested helpers and Qt overrides excepted)."""
    missing = []

    def visit(node, path):
        for n in ast.iter_child_nodes(node):
            if isinstance(n, ast.ClassDef):
                if not n.name.startswith("_") and not ast.get_docstring(n):
                    missing.append(f"{path}:{n.lineno} class {n.name}")
                visit(n, path)
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if n.name.startswith("_") or n.name in INHERITED:
                    continue
                if not ast.get_docstring(n):
                    missing.append(f"{path}:{n.lineno} {n.name}")

    for folder in ("pdfdruck", os.path.join("pdfdruck", "gui")):
        for name in sorted(os.listdir(os.path.join(ROOT, folder))):
            if name.endswith(".py"):
                path = os.path.join(folder, name)
                with open(os.path.join(ROOT, path), encoding="utf-8") as f:
                    visit(ast.parse(f.read()), path)
    assert not missing, "\n".join(missing)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
