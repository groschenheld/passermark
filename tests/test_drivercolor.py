# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Driver colour adjustment off (this job only) and the colour profile for tests in Plan & Poster."""

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()

from pdfdruck import planprint, printers, printjob
from pdfdruck.printers import Choice, Option, PrinterCaps
from pdfdruck.session import Session


def _caps(backend="ppd", extra=()):
    c = PrinterCaps(name="P", backend=backend)
    c.options["ColorModel"] = Option(
        "ColorModel", "Farbe", "g", [Choice("Gray", "Grau"), Choice("None", "Keine")], "Gray"
    )
    for o in extra:
        c.options[o.keyword] = o
    return c


def test_color_off_option():
    stp = Option(
        "StpColorCorrection",
        "Color Correction",
        "g",
        [Choice("None", "Default"), Choice("Accurate", "Accurate"), Choice("Uncorrected", "Uncorrected")],
        "None",
    )
    # "None" of the Gutenprint option means "default", the off value is "Uncorrected" – first match wins
    off = printers.color_off_option(_caps(extra=[stp]))
    assert off == ("StpColorCorrection", "Uncorrected")
    de = Option("CNColorAdjust", "Farbanpassung", "g", [Choice("Auto", "Automatisch"), Choice("Off", "Aus")], "Auto")
    assert printers.color_off_option(_caps(extra=[de])) == ("CNColorAdjust", "Off")
    assert printers.color_off_option(_caps()) is None  # ColorModel (colour/grey) is no colour adjustment
    icm = Option("ColorMatching", "Color Matching", "g", [Choice("Driver", "Driver"), Choice("None", "None")], "Driver")
    assert printers.color_off_option(_caps(extra=[icm])) == ("ColorMatching", "None")
    assert printers.color_off_option(_caps("win")) == ("ICM", "none")
    assert printers.color_off_option(_caps("pdf")) is None
    assert printers.color_off_option(None) is None


def test_send_prepared_switches_off_only_on_request(monkeypatch=None):
    de = Option("CNColorAdjust", "Farbanpassung", "g", [Choice("Auto", "Automatisch"), Choice("Off", "Aus")], "Auto")
    caps = _caps(extra=[de])
    sent_opts = []
    orig = printers.submit
    printers.submit = lambda printer, path, title, options: sent_opts.append(dict(options)) or 7
    try:
        s = Session({})
        job = os.path.join(tempfile.mkdtemp(), "j.pdf")
        open(job, "wb").write(b"%PDF-1.4\n%%EOF\n")
        sent = {}
        printjob.send_prepared(s, "P", caps, job, "t", {}, 1, True, sent)
        assert sent_opts[-1]["CNColorAdjust"] == "Auto"
        printjob.send_prepared(s, "P", caps, job, "t", {printers.COLOR_OFF_KEY: "1"}, 1, True, sent)
        assert sent_opts[-1]["CNColorAdjust"] == "Off" and sent["CNColorAdjust"] == "Off"
        assert printers.COLOR_OFF_KEY not in sent_opts[-1]
    finally:
        printers.submit = orig


def test_plan_color_choice_for_one_print():
    s = Session({"printers": {"P": {"color_profile": "admin-prof", "intent": "relative"}}})
    st = planprint.PlanSettings()
    planprint._set_color(s, "P", st, {})
    assert s.color["P"] == ("admin-prof", "relative")
    planprint._set_color(s, "P", st, {"profile": "mat-prof", "intent": "perceptual"})
    assert s.color["P"] == ("mat-prof", "perceptual")
    s._plan_color_base = {"P": ("admin-prof", "relative")}
    test = planprint.PlanSettings(profile="none", intent="saturation")
    planprint._set_color(s, "P", test, {"profile": "mat-prof"})  # the test choice wins over the material
    assert s.color["P"] == ("", "saturation")
    planprint._set_color(s, "P", planprint.PlanSettings(profile="other"), {})
    assert s.color["P"] == ("other", "relative")


def test_print_items_restores_the_session_colour():
    s = Session({"printers": {"P": {"color_profile": "admin-prof"}}})
    s.color["P"] = ("chosen", "perceptual")
    orig = planprint._print_items

    def fake(session, printer, items, rolls, st, progress=None, cancel=None):
        planprint._set_color(session, printer, st, {})
        assert session.color["P"] == ("", "perceptual")
        raise RuntimeError("stop")

    planprint._print_items = fake
    try:
        try:
            planprint.print_items(s, "P", [], [], planprint.PlanSettings(profile="none"))
        except RuntimeError:
            pass
    finally:
        planprint._print_items = orig
    assert s.color["P"] == ("chosen", "perceptual") and not s._plan_color_base


def test_run_values_marks_driver_colour_off():
    caps = _caps()
    run = planprint.Run.__new__(planprint.Run)
    run.roll, run.pieces, run.across, run.along = -1, [], 100.0, 100.0
    vals, _m = planprint.run_values(None, "P", caps, {}, run, [], planprint.PlanSettings(driver_color_off=True))
    assert vals[printers.COLOR_OFF_KEY] == "1"
    vals, _m = planprint.run_values(None, "P", caps, {}, run, [], planprint.PlanSettings())
    assert printers.COLOR_OFF_KEY not in vals


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
