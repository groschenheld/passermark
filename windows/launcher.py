# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Einstiegspunkt für die Windows-Programmdatei (PyInstaller)."""
import sys

from pdfdruck.__main__ import main

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()   # Arbeitsprozesse fürs parallele Rechnen (gebündelte Programmdatei)
    sys.exit(main())
