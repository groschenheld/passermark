# SPDX-License-Identifier: GPL-3.0-or-later
# pdfToolkit – Copyright (C) 2026 Hias
import os, sys
import os as _os
_os.environ.setdefault("PDFTOOLKIT_LANG", "de")   # Tests prüfen deutsche Texte
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from pdfdruck import trays, ipp, printers as P

T = [trays.Tray("Cas1", "A4", 80, "", "tray-1"), trays.Tray("Cas2", "A4", 80, "", "tray-2"),
     trays.Tray("Cas3", "A4", 80, "", "tray-3"), trays.Tray("Cas4", "A3", 80, "", "tray-4"),
     trays.Tray("Cas5", "A4", 120, "HEAVY1", "")]
LAB = {"Cas1": "Kassette 1", "Cas2": "Kassette 2", "Cas3": "Kassette 3", "Cas4": "Kassette 4"}


def live(empty):
    st = ipp.DeviceStatus()
    for s in ("tray-1", "tray-2", "tray-3", "tray-4"):
        st.trays[s] = ipp.TrayState(s, level=0 if s in empty else 50)
    return st


def test_first_by_format():
    assert trays.pick(T, "A3").tray.slot == "Cas4"
    assert trays.pick(T, "A4").tray.slot == "Cas1"          # mehrere A4 -> erste


def test_weight():
    assert trays.pick(T, "A4", 120).tray.slot == "Cas5"
    assert trays.pick(T, "A4", 80).tray.slot == "Cas1"
    p = trays.pick(T, "A3", 120)
    assert p.tray is None and p.warn                       # A3 120 g gibt es nicht


def test_empty_skips():
    p = trays.pick(T, "A4", 80, live({"tray-1"}), LAB)
    assert p.tray.slot == "Cas2" and "Kassette 1 leer" in p.note
    p = trays.pick(T, "A4", 80, live({"tray-1", "tray-2"}), LAB)
    assert p.tray.slot == "Cas3"
    p = trays.pick(T, "A4", 80, live({"tray-1", "tray-2", "tray-3"}), LAB)
    assert p.tray.slot == "Cas1" and p.warn                 # alle leer -> erste + Warnung


def test_unknown_format():
    assert trays.pick(T, "A5").tray is None


def test_mapping():
    c = P.PrinterCaps("x", "ppd")
    c.options["InputSlot"] = P.Option("InputSlot", "Papierzufuhr", "g",
        [P.Choice("Auto", "Automatisch"), P.Choice("Manual", "Mehrzweckfach"),
         P.Choice("Cas1", "Kassette 1"), P.Choice("Cas2", "Kassette 2")], "Auto")
    c.roles["source"] = "InputSlot"
    c.page_sizes = {"A4": (595.28, 841.89), "A3": (841.89, 1190.55), "TA4": (595.28, 841.89)}
    assert trays.slot_for_source(c, "tray-2") == "Cas2"
    assert trays.slot_for_source(c, "by-pass-tray") == "Manual"
    assert trays.size_for_mm(c, (210, 297)) == "A4"         # nicht die randlose Variante
    assert trays.size_for_mm(c, (420, 297)) == "A3"


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("ok", k)
