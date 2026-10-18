# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Lesbare JSONs (1.15.1): Presets enthalten nur, was vom Standard abweicht (Programm-Einstellung „alle“
    möglich); passermark-cli tidy kürzt bestehende Presets und Abläufe, ohne dass sich etwas ändert."""
import json, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TMP = tempfile.mkdtemp(prefix="pm-tidy-")
os.environ["XDG_CONFIG_HOME"] = os.path.join(TMP, "cfg")
os.environ["APPDATA"] = os.path.join(TMP, "cfg")
os.environ.setdefault("PASSERMARK_LANG", "de")
sys.path.insert(0, ROOT)
from pdfdruck import core, cutcontour, l10n, layout, presets, vdp

ENV = dict(os.environ, PYTHONPATH=ROOT)


def cli(*args):
    return subprocess.run([sys.executable, "-m", "pdfdruck.cli", *args], capture_output=True, text=True, env=ENV,
                          cwd=TMP, timeout=300)


def test_presets_only_differences():
    s = layout.ImposeSettings(handling="booklet", sheet="A3", booklet_fold_marks=True)
    p = presets.save("impose", "Heft A3", s)
    d = json.load(open(p, encoding="utf-8"))
    assert d == {"job": "impose", "settings": {"handling": "booklet", "sheet": "A3", "booklet_fold_marks": True}}, d
    assert presets.load("impose", "Heft A3") == s                       # lädt wieder genau dasselbe
    c = cutcontour.CutSettings(shape="rect", bleed_mm=3.0)
    c.detect.tolerance = 40
    p = presets.save("cutcontour", "Rechteck", c)
    d = json.load(open(p, encoding="utf-8"))["settings"]
    assert d == {"shape": "rect", "bleed_mm": 3.0, "detect": {"tolerance": 40}}, d
    assert presets.load("cutcontour", "Rechteck") == c
    v = vdp.VdpSettings(fields=[dict(content="Nr. {{nr}}")], count=50)
    d = json.load(open(presets.save("vdp", "Tickets", v), encoding="utf-8"))["settings"]
    assert d["count"] == 50 and len(d["fields"]) == 1                  # Listen bleiben ganz
    # Einstellung „alle Einstellungen speichern“
    l10n.save_settings(dict(l10n.load_settings(), presets_full=True))
    try:
        d = json.load(open(presets.save("impose", "Heft A3", s), encoding="utf-8"))["settings"]
        assert len(d) > 40 and d["handling"] == "booklet"
    finally:
        l10n.save_settings(dict(l10n.load_settings(), presets_full=False))


def test_tidy_preset_and_workflow():
    full = os.path.join(TMP, "lang.json")
    core.save_settings(full, "impose", layout.ImposeSettings(handling="booklet", sheet="A3"), full=True)
    n_full = len(json.load(open(full))["settings"])
    r = cli("tidy", full)
    assert r.returncode == 0 and "→ 3 Einträge" in r.stdout, r.stdout + r.stderr
    assert json.load(open(full))["settings"] == {"handling": "booklet", "sheet": "A3"}
    r = cli("tidy", full, "--full", "--out", os.path.join(TMP, "wieder-lang.json"))
    assert r.returncode == 0 and len(json.load(open(os.path.join(TMP, "wieder-lang.json")))["settings"]) == n_full
    wf = {"passermark": "workflow", "version": 1, "steps": [
        {"job": "impose", "settings": core.settings_to_dict(layout.ImposeSettings(sheet="SRA3", step_repeat=True))},
        {"job": "impose", "preset": "Heft A3", "settings": {"sheet": "A4"}},       # A4 = Standard, überschreibt Preset
        {"job": "print", "settings": {"printer": "Canon", "paper": "A3", "copies": 1, "collate": True,
                                      "auto_tray": False, "layout": {"handling": "size", "mode": "fit"}}}]}
    p = os.path.join(TMP, "ablauf.json")
    json.dump(wf, open(p, "w"))
    r = cli("tidy", p, "--print")
    d = json.loads(r.stdout)
    assert d["steps"][0]["settings"] == {"sheet": "SRA3", "step_repeat": True}, d
    assert d["steps"][1]["settings"] == {"sheet": "A4"}                        # mit Preset: unverändert
    assert d["steps"][2]["settings"] == {"printer": "Canon", "paper": "A3", "auto_tray": False,
                                         "layout": {"handling": "size", "mode": "fit"}}, d   # layout bleibt ganz
    assert json.load(open(p)) == wf                                              # --print schreibt nichts
    r = cli("tidy", p, "--full")
    assert r.returncode == 2 and "nur für Presets" in r.stderr
    open(os.path.join(TMP, "x.json"), "w").write('{"foo": 1}')
    assert cli("tidy", "x.json").returncode == 2


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
