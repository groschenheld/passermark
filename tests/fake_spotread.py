# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Nachgestelltes ArgyllCMS spotread für die Tests: Kalibrier-Aufforderung, Mess-Aufforderung, Ergebnis.
    Liest je Aufforderung ein Zeichen von stdin (wie spotread); 'q' bricht ab."""
import os
import sys


def ask(text):
    sys.stdout.write(text)
    sys.stdout.flush()
    c = sys.stdin.read(1)
    if c in ("q", "Q", ""):
        sys.stdout.write("\nAborted\n")
        sys.exit(1)


if os.environ.get("FAKE_SPOTREAD_FAIL"):
    print("No instruments found")
    sys.exit(1)
if "-N" not in sys.argv:
    ask("Place the instrument on its reflective white reference,\n and then hit any key to continue,\n"
        " or hit Esc or Q to abort:")
    print("\nCalibration complete")
ask("Place instrument on spot to be read,\n'k' to do a calibration\n"
    "Hit ESC or 'q' to give up, any other key to take a reading:")
L = os.environ.get("FAKE_SPOTREAD_LAB", "93.512 0.812 4.215")
print(f"\n Result is XYZ: 80.1 83.9 64.2, D50 Lab: {L}\n")
