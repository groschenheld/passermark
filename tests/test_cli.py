# SPDX-License-Identifier: GPL-3.0-or-later
"""Kommandozeile als echter Prozess: list, settings, Aufträge, Presets, JSON-Fortschritt, Rückgabewerte, Abbruch."""
import json, os, signal, subprocess, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
os.environ.setdefault("PASSERMARK_LANG", "de")
from pdfdruck import cli

TMP = tempfile.mkdtemp(prefix="pm-cli-")
ENV = dict(os.environ, PYTHONPATH=ROOT, PASSERMARK_LANG="de")


def run(*args, **kw):
    return subprocess.run([sys.executable, "-m", "pdfdruck.cli", *args], capture_output=True, text=True,
                          env=ENV, timeout=600, **kw)


def stickers():
    p = os.path.join(TMP, "stickers.pdf")
    if not os.path.exists(p):
        import test_cutcontour as tc
        tc.stickers().save(p)
    return p


def test_helpers():
    assert cli.parse_pages("1,3-5") == [0, 2, 3, 4] and cli.parse_pages(None) is None
    d = cli.apply_sets({}, ["shape=rect", "bleed_mm=2.5", "detect.tolerance=40", "spot=CutContour", "bleed=false"])
    assert d == {"shape": "rect", "bleed_mm": 2.5, "detect": {"tolerance": 40}, "spot": "CutContour", "bleed": False}


def test_list_and_settings():
    r = run("list")
    assert r.returncode == 0 and "cutcontour" in r.stdout.split()
    r = run("settings", "cutcontour")
    d = json.loads(r.stdout)
    assert r.returncode == 0 and d["job"] == "cutcontour" and "detect" in d["settings"]
    assert run("settings", "gibts_nicht").returncode == 2


def test_job_with_set_and_preset():
    out = os.path.join(TMP, "a.pdf")
    r = run("cutcontour", stickers(), out, "--set", "shape=rect", "--set", "bleed_mm=1", "--quiet")
    assert r.returncode == 0 and os.path.exists(out), r.stderr
    preset = os.path.join(TMP, "p.json")
    d = json.loads(run("settings", "cutcontour").stdout)
    d["settings"]["shape"] = "circle"
    json.dump(d, open(preset, "w"))
    out2 = os.path.join(TMP, "b.pdf")
    r = run("cutcontour", stickers(), out2, "--preset", preset, "--set", "single_shape=false")
    assert r.returncode == 0 and os.path.exists(out2) and "cuts: 3" in r.stdout, r.stdout + r.stderr
    assert "%" in r.stderr                                    # Fortschrittsbalken
    r = run("separate", stickers(), out2, "--preset", preset)  # Preset passt nicht zum Auftrag
    assert r.returncode == 2


def test_json_progress():
    out = os.path.join(TMP, "j.pdf")
    r = run("cutcontour", stickers(), out, "--json-progress")
    evs = [json.loads(l) for l in r.stdout.splitlines() if l.strip()]
    assert r.returncode == 0 and evs[0]["event"] == "progress" and evs[-1]["event"] == "done"
    assert evs[-1]["output"] == out and evs[-1]["info"]["cuts"] >= 3
    r = run("cutcontour", os.path.join(TMP, "fehlt.pdf"), out, "--json-progress")
    assert r.returncode == 1 and json.loads(r.stdout.splitlines()[-1])["event"] == "error"


def test_exit_codes():
    assert run("cutcontour").returncode == 2                  # Eingabe/Ausgabe fehlen
    assert run("gibts_nicht", "a", "b").returncode == 2
    assert run("cutcontour", stickers(), os.path.join(TMP, "x.pdf"), "--pages", "0").returncode == 2
    assert run("--hilfe-gibts-nicht").returncode == 2


def _slow_input():
    """Mehrseitiges PDF mit vielen Objekten (dauert einige Sekunden) für den Abbruch-Test."""
    p = os.path.join(TMP, "slow.pdf")
    if not os.path.exists(p):
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        c = canvas.Canvas(p, pagesize=A4)
        for _page in range(12):
            for i in range(8):
                for j in range(10):
                    c.setFillColorRGB(0.8, 0.1 * i, 0.1 * j)
                    c.circle(40 + i * 70, 40 + j * 78, 25, fill=1, stroke=0)
            c.showPage()
        c.save()
    return p


def test_cancel_by_signal_leaves_no_file():
    for sig in (signal.SIGINT, signal.SIGTERM):
        out = os.path.join(TMP, f"abbruch-{int(sig)}.pdf")
        p = subprocess.Popen([sys.executable, "-m", "pdfdruck.cli", "cutcontour", _slow_input(), out, "--json-progress",
                              "--set", "dpi=200"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=ENV)
        first = p.stdout.readline()                              # warten, bis er wirklich rechnet
        assert json.loads(first)["event"] == "progress", first
        time.sleep(0.5)
        p.send_signal(sig)
        rest, _err = p.communicate(timeout=300)
        last = json.loads([l for l in rest.splitlines() if l.strip()][-1])
        assert p.returncode == 130 and last["event"] == "cancelled", (sig, p.returncode, last)
        assert not os.path.exists(out) and not os.path.exists(out + ".part")


def test_main_entry_cli_flag():
    r = subprocess.run([sys.executable, "-m", "pdfdruck", "--cli", "list"], capture_output=True, text=True, env=ENV,
                       timeout=120)
    assert r.returncode == 0 and "cutcontour" in r.stdout


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("ok", k)
