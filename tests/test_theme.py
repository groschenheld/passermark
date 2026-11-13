# SPDX-License-Identifier: GPL-3.0-or-later
"""The colours of the interface live in pdfdruck/gui/theme.py only – so that a redesign changes one file."""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
GUI = os.path.join(ROOT, "pdfdruck", "gui")
HEX = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b")
# not interface colours: paper white and black as the default of a colour the user picks for the document
ALLOWED = {"#ffffff", "#000000", "#000"}


def test_no_colours_outside_theme():
    """No hex colour in gui/ outside theme.py (apart from paper white and document black)."""
    found = []
    for name in sorted(os.listdir(GUI)):
        if not name.endswith(".py") or name == "theme.py":
            continue
        with open(os.path.join(GUI, name), encoding="utf-8") as f:
            for no, line in enumerate(f, 1):
                for m in HEX.findall(line.split("  # ")[0]):
                    if m.lower() not in ALLOWED:
                        found.append(f"{name}:{no}: {m}")
    assert not found, "colours belong into gui/theme.py:\n" + "\n".join(found)


def test_theme_names_every_colour_once():
    """theme.py itself: hex values only in the constants at the top, none inside the style sheets."""
    with open(os.path.join(GUI, "theme.py"), encoding="utf-8") as f:
        src = f.read()
    body = src[src.index("ACCENT_SOFT = ") :]
    assert not HEX.search(body), HEX.findall(body)


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
