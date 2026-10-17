# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Drop-Ordner (passermark-cli serve): Einstellung prüfen, Dateien verarbeiten, Ergebnis/Original/Fehler ablegen,
    nur Druckende Abläufe, unterbrochene Dateien zurücklegen, halb geschriebene Dateien abwarten."""
import io, json, os, shutil, subprocess, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
os.environ.setdefault("PASSERMARK_LANG", "de")
from pdfdruck import watch, workflow

TMP = tempfile.mkdtemp(prefix="pm-watch-")
ENV = dict(os.environ, PYTHONPATH=ROOT + os.pathsep + os.environ.get("PYTHONPATH", ""), PASSERMARK_LANG="de",
           XDG_CONFIG_HOME=os.path.join(TMP, "cfg"), PDFDRUCK_CONFIG_DIR=os.path.join(TMP, "etc"))


def pdf(path, n=2, size=(85, 55)):
    from reportlab.pdfgen import canvas
    MM = 72 / 25.4
    c = canvas.Canvas(path, pagesize=(size[0] * MM, size[1] * MM))
    for i in range(n):
        c.drawString(10, 10, f"Karte {i + 1}")
        c.showPage()
    c.save()
    return path


def setup(name):
    base = os.path.join(TMP, name)
    os.makedirs(os.path.join(base, "in"))
    json.dump({"passermark": "workflow", "version": 1, "name": "Nutzen",
               "output": "${dir}/${stem}-nutzen.pdf",          # würde im Eingang landen – der Watcher legt nach out
               "steps": [{"job": "impose", "settings": {"sheet": "A4", "step_repeat": True}}]},
              open(os.path.join(base, "nutzen.json"), "w"))
    json.dump({"passermark": "workflow", "version": 1,
               "steps": [{"job": "print", "settings": {"paper": "auto", "layout": {"handling": "size"}}}]},
              open(os.path.join(base, "druck.json"), "w"))
    return base


def test_config_problems():
    base = setup("cfg")
    p = os.path.join(base, "watch.json")
    json.dump({"passermark": "watch", "version": 9, "intervall": 3, "settle": -1,
               "folders": [{"in": "in", "workflow": "nutzen.json", "out": ".", "patterns": [], "x": 1},
                           {"in": "in", "workflow": ""}]}, open(p, "w"))
    try:
        watch.load_config(p)
        assert False
    except watch.WatchError as e:
        where = {w for w, _ in e.problems}
        assert {"version", "intervall", "settle", "folders[0].out", "folders[0].patterns", "folders[0].x",
                "folders[1].in", "folders[1].workflow"} <= where, where
    json.dump({"passermark": "watch", "version": 1, "folders": [{"in": "gibtsnicht", "workflow": "nutzen.json"},
                                                                  {"in": "in", "workflow": "fehlt"}]}, open(p, "w"))
    cfg = watch.load_config(p)
    f0 = cfg["folders"][0]
    assert f0["out"] == os.path.join(base, "gibtsnicht", "output") and f0["workflow"] == os.path.join(base, "nutzen.json")
    probs = watch.check(cfg)
    where = {w for w, _ in probs}
    assert "folders[0].in" in where and "folders[1].workflow" in where, probs


def test_process_files():
    base = setup("run")
    ind = os.path.join(base, "in")
    p = os.path.join(base, "watch.json")
    json.dump({"passermark": "watch", "version": 1, "settle": 0,
               "folders": [{"in": "in", "workflow": "nutzen.json"}]}, open(p, "w"))
    pdf(os.path.join(ind, "karte.pdf"))
    open(os.path.join(ind, "kaputt.pdf"), "w").write("kein pdf")
    open(os.path.join(ind, "notiz.txt"), "w").write("passt nicht zum Muster")
    open(os.path.join(ind, "halb.pdf.part"), "w").write("wird noch kopiert")
    evs = []
    counts = watch.Watcher(watch.load_config(p), evs.append).run(once=True)
    assert counts == {"done": 1, "failed": 1}, (counts, evs)
    assert os.path.isfile(os.path.join(ind, "output", "karte.pdf"))                  # Ergebnis
    assert os.path.isfile(os.path.join(ind, "processed", "karte.pdf"))               # Original
    assert os.path.isfile(os.path.join(ind, "failed", "kaputt.pdf"))
    assert os.path.isfile(os.path.join(ind, "failed", "kaputt.pdf.log"))
    assert sorted(os.listdir(ind)) == sorted(["output", "processed", "failed", ".passermark", "notiz.txt",
                                              "halb.pdf.part"]), os.listdir(ind)
    assert not os.listdir(os.path.join(ind, ".passermark"))
    kinds = [e["event"] for e in evs]
    assert kinds[0] == "watch_start" and "file_done" in kinds and "file_failed" in kinds and "step" in kinds
    # gleicher Name nochmal: nichts wird überschrieben
    pdf(os.path.join(ind, "karte.pdf"))
    watch.Watcher(watch.load_config(p)).run(once=True)
    assert os.path.isfile(os.path.join(ind, "output", "karte-1.pdf"))
    assert os.path.isfile(os.path.join(ind, "processed", "karte-1.pdf"))


def test_print_only_and_recover():
    import test_printcli as T
    base = setup("druck")
    ind = os.path.join(base, "in")
    p = os.path.join(base, "watch.json")
    json.dump({"passermark": "watch", "version": 1, "settle": 0,
               "folders": [{"in": "in", "workflow": "druck.json", "done": ""}]}, open(p, "w"))
    pdf(os.path.join(ind, "a3.pdf"), 2, (297, 420))
    # Rest eines Absturzes: liegt noch im Arbeitsordner -> kommt zurück und wird verarbeitet
    os.makedirs(os.path.join(ind, ".passermark"))
    pdf(os.path.join(ind, ".passermark", "liegengeblieben.pdf"), 1, (210, 297))
    evs = []
    with T.FakePrinter() as fp:
        counts = watch.Watcher(watch.load_config(p), evs.append).run(once=True)
    assert counts == {"done": 2, "failed": 0}, evs
    assert sorted(s["opts"]["PageSize"] for s in fp.sent) == ["A3", "A4"]
    assert evs[0]["recovered"] == 1
    done = [e for e in evs if e["event"] == "file_done"]
    assert all(e["output"] is None and e["moved_to"] is None and e["prints"][0]["job_id"] == 4711 for e in done)
    assert sorted(os.listdir(ind)) == [".passermark"]                       # nur gedruckt: kein Ergebnis, Original weg


def test_settle_waits_for_complete_file():
    base = setup("settle")
    ind = os.path.join(base, "in")
    p = os.path.join(base, "watch.json")
    json.dump({"passermark": "watch", "version": 1, "settle": 1.0,
               "folders": [{"in": "in", "workflow": "nutzen.json"}]}, open(p, "w"))
    w = watch.Watcher(watch.load_config(p))
    f = os.path.join(ind, "gross.pdf")
    pdf(f)
    assert w.scan_once() == 0                       # gerade erst gesehen
    time.sleep(0.4)
    with open(f, "ab") as fh:                       # wächst noch -> wieder warten
        fh.write(b"\n%")
    assert w.scan_once() == 0
    time.sleep(0.4)
    assert w.scan_once() == 0
    time.sleep(0.8)
    assert w.scan_once() == 1


def test_cli_serve():
    base = setup("cli")
    ind = os.path.join(base, "in")
    p = os.path.join(base, "watch.json")
    json.dump({"passermark": "watch", "version": 1, "settle": 0,
               "folders": [{"in": "in", "workflow": "nutzen.json", "name": "Karten"}]}, open(p, "w"))

    def cli(*args):
        return subprocess.run([sys.executable, "-m", "pdfdruck.cli", "serve", *args], capture_output=True, text=True,
                              env=ENV, cwd=base, timeout=600)
    r = cli("--config", p, "--check")
    assert r.returncode == 0 and "1 Ordner" in r.stdout, r.stdout + r.stderr
    pdf(os.path.join(ind, "k.pdf"))
    r = cli("--config", p, "--once", "--json")
    ev = [json.loads(x) for x in r.stdout.splitlines() if x.strip()]
    assert r.returncode == 0, r.stdout + r.stderr
    assert ev[0]["event"] == "watch_start" and ev[-1] == {"event": "stopped", "done": 1, "failed": 0}, ev
    assert any(e["event"] == "file_done" and e["output"].endswith(os.path.join("output", "k.pdf")) for e in ev)
    pdf(os.path.join(ind, "k2.pdf"))
    log = os.path.join(base, "watch.log")
    r = cli("--config", p, "--once", "--quiet", "--log", log)
    assert r.returncode == 0 and not r.stdout, r.stdout
    txt = open(log, encoding="utf-8").read()
    assert "Karten: k2.pdf → nutzen.json" in txt and "Beendet: 1 verarbeitet" in txt, txt
    # ohne --config: eigene Einstellung unter ~/.config/passermark/watch.json
    own = os.path.join(TMP, "cfg", "passermark")
    os.makedirs(own, exist_ok=True)
    shutil.copy(p, os.path.join(own, "watch.json"))
    r = cli("--check")
    assert r.returncode == 2 and "folders[0].in" in r.stderr, r.stdout + r.stderr   # „in“ relativ zur eigenen Datei
    r = subprocess.run([sys.executable, "-m", "pdfdruck.cli", "serve", "--config", "fehlt.json", "--json"],
                       capture_output=True, text=True, env=ENV, cwd=base, timeout=600)
    assert r.returncode == 2 and json.loads(r.stdout)["code"] == "not_found"


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
