# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Release notes from the changelogs (tools/release_notes.py) – the text the update dialog shows."""

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))

import release_notes as RN  # noqa: E402

DE = """# Änderungen

## 1.19.7 – Neues

### Teil
- eins

## 1.19.6 – Alt
- alt
"""
EN = """# Changelog

## 1.19.7 – New
- one
"""


def test_notes_from_both_changelogs():
    d = tempfile.mkdtemp()
    for name, text in (("CHANGELOG.de.md", DE), ("CHANGELOG.md", EN)):
        with open(os.path.join(d, name), "w", encoding="utf-8") as f:
            f.write(text)
    n = RN.notes("v1.19.7", d)
    assert "## Deutsch" in n and "**Neues**" in n and "### Teil" in n and "- eins" in n
    assert "## English" in n and "- one" in n and "alt" not in n
    assert RN.notes("v1.19.7-test1", d) == n  # pre-release: the section of the version without suffix
    assert "see CHANGELOG" in RN.notes("v9.0.0", d)
    assert RN.section(DE, "1.19") == ""  # 1.19 is not 1.19.7


if __name__ == "__main__":
    test_notes_from_both_changelogs()
    print("ok test_notes_from_both_changelogs")
