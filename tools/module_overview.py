#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Regenerate the module reference in docs/architecture.md from the module docstrings.

Usage: python3 tools/module_overview.py [--check]

The table between the markers ``<!-- modules:begin -->`` and ``<!-- modules:end -->`` is replaced. With
``--check`` nothing is written; the exit code is 1 if the file is out of date (used by the tests).
"""

from __future__ import annotations

import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(ROOT, "docs", "architecture.md")
BEGIN, END = "<!-- modules:begin -->", "<!-- modules:end -->"
PACKAGES = (("pdfdruck", "Core (no user interface)"), ("pdfdruck/gui", "User interface (PySide6)"))


def summary(path: str) -> str:
    """First sentence of the module docstring, on one line."""
    with open(path, encoding="utf-8") as f:
        doc = ast.get_docstring(ast.parse(f.read())) or ""
    first = " ".join(doc.strip().split("\n\n")[0].split())
    for stop in (". ", ": "):
        if stop in first and len(first) > 110:
            first = first.split(stop)[0] + ("." if stop == ". " else "")
            break
    return first.replace("|", "\\|")


def table() -> str:
    """Build the markdown tables for all packages."""
    out = []
    for folder, title in PACKAGES:
        out += [f"### {title}", "", "| Module | Purpose |", "|---|---|"]
        for name in sorted(os.listdir(os.path.join(ROOT, folder))):
            path = os.path.join(ROOT, folder, name)
            if not name.endswith(".py") or name == "__init__.py":
                continue
            out.append(f"| `{folder}/{name}` | {summary(path)} |")
        out.append("")
    return "\n".join(out).rstrip("\n")


def main(argv: list[str]) -> int:
    with open(DOC, encoding="utf-8") as f:
        text = f.read()
    head, rest = text.split(BEGIN, 1)
    _old, tail = rest.split(END, 1)
    new = f"{head}{BEGIN}\n{table()}\n{END}{tail}"
    if "--check" in argv:
        return 0 if new == text else 1
    with open(DOC, "w", encoding="utf-8") as f:
        f.write(new)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
