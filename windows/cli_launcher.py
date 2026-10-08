# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Einstiegspunkt für passermark-cli.exe (Konsole, PyInstaller)."""
import sys

from pdfdruck.cli import main

if __name__ == "__main__":
    sys.exit(main())
