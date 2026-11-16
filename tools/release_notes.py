# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Release notes for a GitHub release, taken from the changelogs: the section of the version in German and
English. The update dialog of the program shows exactly this text.

    python3 tools/release_notes.py 1.19.7            -> Markdown on stdout
    python3 tools/release_notes.py v1.19.7-test1     -> a tag works too; a suffix falls back to 1.19.7
"""

from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHANGELOGS = (("Deutsch", "CHANGELOG.de.md"), ("English", "CHANGELOG.md"))


def section(text: str, version: str) -> str:
    """The body of "## <version> …" up to the next "## " heading ("" if the version is not there)."""
    lines = text.splitlines()
    head = re.compile(rf"^##\s+v?{re.escape(version)}(\s|$)")
    out, inside = [], False
    for line in lines:
        if line.startswith("## ") and not line.startswith("###"):
            if inside:
                break
            if head.match(line):
                inside = True
                title = line[3:].strip()
                rest = title[len(version) :].strip(" –-") if title.startswith(version) else ""
                if rest:
                    out.append(f"**{rest}**")
                continue
        elif inside:
            out.append(line)
    return "\n".join(out).strip()


def notes(tag: str, root: str = ROOT) -> str:
    """Markdown for the release of ``tag`` (v1.19.7, 1.19.7, v1.19.7-test1)."""
    version = tag[1:] if tag.startswith("v") else tag
    candidates = [version] + ([version.split("-", 1)[0]] if "-" in version else [])
    parts = []
    for label, name in CHANGELOGS:
        try:
            with open(os.path.join(root, name), encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        body = next((b for b in (section(text, v) for v in candidates) if b), "")
        if body:
            parts.append(f"## {label}\n\n{body}")
    if not parts:
        return f"Passermark {version} – see CHANGELOG.md / CHANGELOG.de.md."
    return "\n\n".join(parts) + "\n"


def main(argv: list[str]) -> int:
    """Print the notes for the tag given as the only argument."""
    if len(argv) != 1:
        print(__doc__)
        return 2
    sys.stdout.write(notes(argv[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
