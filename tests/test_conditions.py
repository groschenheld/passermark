# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Bedingungen in Abläufen (1.16): "if" an Schritten, "choose" mit "else", "fail" und "stop" – geprüft am
    aktuellen PDF; check meldet Tippfehler; JSON-Ereignisse; der Watcher legt abgelehnte Dateien nach failed/."""
import contextlib, io, json, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
os.environ.setdefault("PASSERMARK_LANG", "de")
import test_printcli as T
from pdfdruck import cli, conditions, watch, workflow

TMP = tempfile.mkdtemp(prefix="pm-cond-")
ENV = dict(os.environ, PYTHONPATH=ROOT, PASSERMARK_LANG="de", XDG_CONFIG_HOME=os.path.join(TMP, "cfg"))
MM = 72 / 25.4

WF = {"passermark": "workflow", "version": 1, "output": "${dir}/out/${stem}.pdf", "steps": [
    {"job": "shrink", "if": {"size_mb": {">": 500}}},                       # nie: Dateien sind klein
    {"choose": [
        {"if": {"format": "A5", "pages": {">=": 8}},
         "steps": [{"job": "impose", "settings": {"sheet": "A4", "handling": "booklet"}}]},
        {"if": {"any": [{"format": "A4"}, {"filename": {"matches": "*_a4*.pdf"}}]},
         "steps": [{"job": "stop", "message": "A4 – passt schon (${pages} Seite(n))"}]},
        {"else": [{"job": "fail", "message": "Format ${format} (${width_mm} × ${height_mm} mm) nicht vorgesehen"}]},
    ]},
    {"job": "impose", "if": {"var.kunde": "Huber"}, "settings": {"sheet": "A3", "handling": "multiple", "nup": 2}},
]}


def prep(inp, **v):
    return workflow.prepare(json.loads(json.dumps(WF)), TMP, [inp], None, v)


def test_branches():
    a5 = T.doc(8, (148, 210))
    r = workflow.run(prep(a5), variables={})
    assert [s["job"] for s in r["steps"]] == ["impose"] and r["pages"] == 4, r       # Broschüre: 4 A4-Bogenseiten
    assert r["decisions"][0]["result"] is False and "size_mb" in r["decisions"][0]["why"]
    # A4: stop – Ergebnis = unverändert, Meldung mit Prüfwert
    a4 = T.doc(3, (210, 297))
    r = workflow.run(prep(a4), variables={})
    assert r["steps"] == [] and r["stopped"] == "A4 – passt schon (3 Seite(n))" and r["pages"] == 3, r
    # anderes Format: fail mit Meldung
    a6 = T.doc(1, (105, 148))
    try:
        workflow.run(prep(a6), variables={})
        assert False
    except workflow.Rejected as e:
        assert str(e) == "Format A6 (105 × 148 mm) nicht vorgesehen", e
    # Dateiname per Muster, Variable
    named = os.path.join(TMP, "flyer_a4_final.pdf")
    import shutil
    shutil.copy(a6, named)
    r = workflow.run(prep(named), variables={})
    assert r["stopped"]
    r = workflow.run(prep(a5, kunde="Huber"), variables={"kunde": "Huber"})
    assert [s["job"] for s in r["steps"]] == ["impose", "impose"], r                    # Bedingung mit Variable


def test_facts_and_check_facts():
    a5 = T.doc(2, (148, 210))
    f = conditions.Facts(a5)
    assert f.get("format") == "A5" and f.get("orientation") == "portrait" and f.get("pages") == 2
    assert f._check is None                                     # Prüfung erst bei Bedarf
    assert f.get("fonts_missing") is False and f.get("errors") == 0          # Helvetica: Standardschrift
    import test_preflight as tp
    p = os.path.join(TMP, "problem.pdf")
    open(p, "wb").write(tp.problem_pdf())
    g = conditions.Facts(p)
    assert g.get("fonts_missing") is True and g.get("errors") >= 1 and g.get("rgb") is True and g.get("layers") >= 2
    ok, why = conditions.evaluate({"not": {"pages": {"<": 2}}, "format": {"in": ["a4", "a5"]}}, f)
    assert ok, why


def test_check_reports_mistakes():
    bad = {"passermark": "workflow", "version": 1, "output": "x.pdf", "steps": [
        {"job": "shrink", "if": {"seiten": 3}},
        {"job": "shrink", "if": {"pages": {"ab": 3}}},
        {"job": "shrink", "if": {"format": {">": 3}}},
        {"choose": [{"else": []}, {"if": {"pages": 1}, "steps": []}]},
        {"choose": [{"steps": []}]},
        {"job": "fail", "settings": {}},
        {"job": "nix"}]}
    try:
        workflow.prepare(bad, TMP, [T.doc(1)])
        assert False
    except workflow.WorkflowError as e:
        where = {w for w, _ in e.problems}
        want = {"steps[0].if.seiten", "steps[1].if.pages.ab", "steps[2].if.format.>", "steps[3].choose[0]",
                "steps[4].choose[0]", "steps[5].settings", "steps[6].job"}
        assert want <= where, where - want if not want <= where else where


def test_cli_events_and_rejected():
    p = os.path.join(TMP, "wf.json")
    json.dump(WF, open(p, "w"))
    a6 = T.doc(1, (105, 148))
    r = subprocess.run([sys.executable, "-m", "pdfdruck.cli", "run", p, "--in", a6, "--json"], capture_output=True,
                       text=True, env=ENV, cwd=TMP, timeout=300)
    ev = [json.loads(x) for x in r.stdout.splitlines() if x.strip()]
    assert r.returncode == 1 and ev[-1]["event"] == "error" and ev[-1]["code"] == "rejected", ev
    assert any(e["event"] == "condition" and e["result"] is False for e in ev)
    assert any(e["event"] == "branch" and e["branch"] == "else" for e in ev)
    r = subprocess.run([sys.executable, "-m", "pdfdruck.cli", "check", p, "--in", a6], capture_output=True,
                       text=True, env=ENV, cwd=TMP, timeout=300)
    assert r.returncode == 0 and "Verzweigung" in r.stdout and "sonst" in r.stdout and "fail" in r.stdout, r.stdout
    r = subprocess.run([sys.executable, "-m", "pdfdruck.cli", "version", "--json"], capture_output=True, text=True,
                       env=ENV, cwd=TMP, timeout=300)
    d = json.loads(r.stdout)
    assert "format" in d["conditions"]["facts"] and "matches" in d["conditions"]["operators"]


def test_watcher_rejects_into_failed():
    base = os.path.join(TMP, "w")
    os.makedirs(os.path.join(base, "in"))
    json.dump(dict(WF, output=None) if False else {k: v for k, v in WF.items() if k != "output"},
              open(os.path.join(base, "wf.json"), "w"))
    json.dump({"passermark": "watch", "version": 1, "settle": 0, "folders": [{"in": "in", "workflow": "wf.json"}]},
              open(os.path.join(base, "watch.json"), "w"))
    import shutil
    shutil.copy(T.doc(1, (105, 148)), os.path.join(base, "in", "a6.pdf"))
    shutil.copy(T.doc(8, (148, 210)), os.path.join(base, "in", "heft.pdf"))
    counts = watch.Watcher(watch.load_config(os.path.join(base, "watch.json"))).run(once=True)
    assert counts == {"done": 1, "failed": 1}, counts
    log = open(os.path.join(base, "in", "failed", "a6.pdf.log"), encoding="utf-8").read()
    assert "Format A6" in log, log
    assert os.path.isfile(os.path.join(base, "in", "output", "heft.pdf"))


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
