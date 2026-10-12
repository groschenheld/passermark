# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Entry point for passermark-cli.exe (console, PyInstaller)."""
import sys

from pdfdruck.cli import main

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()   # worker processes for parallel computing (bundled executable)
    sys.exit(main())
