# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Interface for other programs: workflow file (schema, check, run), inspect, version – as a real process,
    JSON events with stable error codes, nothing half-written on errors."""
import io, json, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ.setdefault("PASSERMARK_LANG", "de")
from pdfdruck import core, workflow

TMP = tempfile.mkdtemp(prefix="pm-wf-")
ENV = dict(os.environ, PYTHONPATH=ROOT, PASSERMARK_LANG="de")
MM = 72 / 25.4


def run(*args):
    return subprocess.run([sys.executable, "-m", "pdfdruck.cli", *args], capture_output=True, text=True,
                          env=ENV, timeout=600)


def events(r):
    return [json.loads(x) for x in r.stdout.splitlines() if x.strip()]


def cards():
    p = os.path.join(TMP, "karten.pdf")
    if not os.path.exists(p):
        import pikepdf
        from reportlab.pdfgen import canvas
        b = io.BytesIO()
        c = canvas.Canvas(b)
        for i in range(4):
            c.setPageSize((91 * MM, 61 * MM))
            c.setFillColorRGB(0.2 * i, 0.5, 0.8)
            c.rect(0, 0, 91 * MM, 61 * MM, fill=1)
            c.showPage()
        c.save()
        pk = pikepdf.open(io.BytesIO(b.getvalue()))
        for pg in pk.pages:
            pg.TrimBox = [3 * MM, 3 * MM, 88 * MM, 58 * MM]
            pg.BleedBox = [0, 0, 91 * MM, 61 * MM]
        pk.pages[3].Rotate = 90
        pk.save(p)
    return p


def write_wf(name, data):
    p = os.path.join(TMP, name)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return p


GOOD = {"passermark": "workflow", "version": 1, "name": "Karten", "input": "karten.pdf",
        "output": "out/${stem}-${kunde}.pdf",
        "steps": [{"job": "impose", "name": "Nutzen", "pages": "1-2",
                   "settings": {"sheet": "SRA3", "step_repeat": True, "crop_marks": True, "bleed_mm": 3}},
                  {"job": "shrink"}]}


def test_schema_and_settings_check():
    try:
        import jsonschema
    except ImportError:
        jsonschema = None
    sch = workflow.schema()
    assert set(sch["$defs"]) == {f"settings.{j}" for j in list(core.JOBS) + ["print", "plan"]} | {"step", "condition"}
    bad = {"passermark": "workflow", "version": 1, "steps": [{"job": "impose", "settings": {"sheett": "A4"}}]}
    if jsonschema is not None:
        jsonschema.Draft202012Validator.check_schema(sch)
        v = jsonschema.Draft202012Validator(sch)
        assert not list(v.iter_errors(GOOD))
        assert list(v.iter_errors(bad))
        for job in workflow.step_jobs():               # Standardwerte passen zum eigenen Schema
            cls = workflow.step_settings_class(job)
            d = core.settings_to_dict(cls())
            assert not list(jsonschema.Draft202012Validator(workflow.settings_schema(cls))
                            .iter_errors(json.loads(json.dumps(d)))), job
    cls = core.settings_class("impose")
    assert workflow.check_settings(cls, {"sheet": "A3", "bleed_mm": 3, "nup": 4}) == []
    probs = dict(workflow.check_settings(cls, {"sheett": "A3", "bleed_mm": "3", "nup": 2.5, "crop_marks": 1}))
    assert set(probs) == {"settings.sheett", "settings.bleed_mm", "settings.nup", "settings.crop_marks"}, probs
    cut = core.settings_class("cutcontour")
    assert dict(workflow.check_settings(cut, {"detect": {"tolerancee": 4}})) == {
        "settings.detect.tolerancee": "unbekannte Einstellung"}


def test_version_and_schema_cli():
    r = run("version", "--json")
    d = json.loads(r.stdout)
    assert r.returncode == 0 and d["api"] == workflow.API and d["workflow_version"] == workflow.VERSION
    assert "impose" in d["jobs"]
    r = run("schema", "--json")
    assert r.returncode == 0 and json.loads(r.stdout)["$id"] == f"urn:passermark:workflow:{workflow.VERSION}"
    r = run("schema", "impose")
    assert r.returncode == 0 and json.loads(r.stdout)["properties"]["sheet"]["default"] == "A4"
    r = run("schema", "gibtsnicht", "--json")
    assert r.returncode == 2 and events(r)[0]["code"] == "usage"


def test_check_reports_all_problems():
    cards()
    p = write_wf("kaputt.json", {"passermark": "workflow", "version": 1, "input": "fehlt.pdf", "foo": 1,
                                 "steps": [{"job": "impose", "settings": {"sheett": "A4", "bleed_mm": "3"}},
                                           {"job": "xx"}, {"job": "split", "pages": "3-1"}]})
    r = run("check", p, "--json")
    ev = events(r)[0]
    assert r.returncode == 2 and ev["event"] == "error" and ev["code"] == "invalid"
    where = {x["where"] for x in ev["problems"]}
    assert {"foo", "input", "output", "steps[0].settings.sheett", "steps[0].settings.bleed_mm", "steps[1].job",
            "steps[2].pages"} <= where, where
    p = write_wf("gut.json", GOOD)
    r = run("check", p, "--json")
    assert r.returncode == 2 and "kunde" in r.stdout                  # Variable fehlt
    r = run("check", p, "--var", "kunde=Muster", "--json")
    d = json.loads(r.stdout)
    assert r.returncode == 0 and d["ok"] and d["output"].endswith(os.path.join("out", "karten-Muster.pdf"))
    assert d["steps"][0]["pages"] == [1, 2] and d["steps"][0]["settings"]["sheet"] == "SRA3"
    r = run("check", os.path.join(TMP, "nichtda.json"), "--json")
    assert r.returncode == 2 and events(r)[0]["code"] == "not_found"


def test_run_events_and_result():
    import pypdfium2 as pdfium
    cards()
    p = write_wf("gut.json", GOOD)
    r = run("run", p, "--var", "kunde=Muster", "--json")
    ev = events(r)
    assert r.returncode == 0, r.stdout + r.stderr
    assert ev[0]["event"] == "start" and ev[0]["api"] == workflow.API and ev[0]["steps"] == 2
    kinds = [e["event"] for e in ev]
    assert kinds.count("step") == 2 and kinds.count("step_done") == 2 and kinds[-1] == "done"
    done = ev[-1]
    assert os.path.isfile(done["output"]) and done["pages"] == 2
    assert [s["job"] for s in done["steps"]] == ["impose", "shrink"] and done["steps"][0]["info"]["sheets"] == 2
    d = pdfium.PdfDocument(done["output"])
    w, h = d.get_page_size(0)
    assert abs(w / MM - 320) < 1 and abs(h / MM - 450) < 1           # SRA3
    d.close()
    # --in und Ausgabe relativ zum aktuellen Ordner (nicht zum Ordner des Ablaufs)
    sub = os.path.join(TMP, "anderswo")
    os.makedirs(sub, exist_ok=True)
    import shutil
    shutil.copy(cards(), os.path.join(sub, "hier.pdf"))
    r = subprocess.run([sys.executable, "-m", "pdfdruck.cli", "run", p, "rel.pdf", "--in", "hier.pdf",
                        "--var", "kunde=X", "--json"], capture_output=True, text=True, env=ENV, cwd=sub, timeout=600)
    assert r.returncode == 0, r.stdout + r.stderr
    assert os.path.isfile(os.path.join(sub, "rel.pdf"))
    r = run(p.replace(".json", "") + ".json", "x.pdf")                # Ablauf als Auftrag angegeben -> Hinweis
    assert r.returncode == 2 and "passermark-cli run" in r.stderr
    # Ausgabe als Argument, Eingabe überschrieben, Text-Ausgabe
    out = os.path.join(TMP, "anders.pdf")
    r = run("run", p, out, "--in", cards(), "--var", "kunde=X")
    assert r.returncode == 0 and os.path.isfile(out) and out in r.stdout


def test_run_failure_leaves_nothing():
    cards()
    out = os.path.join(TMP, "nie.pdf")
    p = write_wf("fehler.json", {"passermark": "workflow", "version": 1, "input": "karten.pdf", "output": out,
                                 "steps": [{"job": "shrink"},
                                           {"job": "preflight_fix", "settings": {"fix": "gibtsnicht"}}]})
    r = run("run", p, "--json")
    ev = events(r)
    assert r.returncode == 1 and ev[-1]["event"] == "error" and ev[-1]["code"] == "failed"
    assert ev[-1]["step"] == 2 and ev[-1]["job"] == "preflight_fix"
    assert not os.path.exists(out) and not os.path.exists(out + ".part")


def test_run_merges_inputs_without_steps():
    import pypdfium2 as pdfium
    from PIL import Image
    img = os.path.join(TMP, "bild.png")
    Image.new("RGB", (300, 200), (200, 30, 30)).save(img, dpi=(150, 150))
    out = os.path.join(TMP, "zusammen.pdf")
    p = write_wf("merge.json", {"passermark": "workflow", "version": 1, "output": out, "steps": []})
    r = run("run", p, "--in", cards(), "--in", img, "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    assert events(r)[-1]["pages"] == 5
    d = pdfium.PdfDocument(out)
    assert len(d) == 5
    d.close()


def test_newer_format_rejected():
    p = write_wf("neu.json", {"passermark": "workflow", "version": workflow.VERSION + 1, "input": "karten.pdf",
                              "output": "x.pdf", "steps": []})
    r = run("check", p, "--json")
    assert r.returncode == 2 and any(x["where"] == "version" for x in events(r)[0]["problems"])


def test_inspect():
    r = run("inspect", cards(), "--json", "--check")
    d = json.loads(r.stdout)
    assert r.returncode == 0 and d["pages"] == 4
    p1, p4 = d["page_list"][0], d["page_list"][3]
    assert p1["width_mm"] == 91.0 and p1["height_mm"] == 61.0 and p1["trim_mm"] == [85.0, 55.0]
    assert p1["bleed_mm"] == 3.0 and p1["orientation"] == "landscape"
    assert p4["rotate"] == 90 and p4["width_mm"] == 61.0 and p4["trim_mm"] == [55.0, 85.0]
    assert {"counts", "issues", "fonts", "layers"} <= set(d["check"])
    assert all(i["severity"] in ("error", "warning", "info") for i in d["check"]["issues"])
    r = run("inspect", cards())
    assert r.returncode == 0 and "Endformat 85 × 55 mm" in r.stdout
    r = run("inspect", os.path.join(TMP, "nix.pdf"), "--json")
    assert r.returncode == 1 and events(r)[0]["code"] == "not_found"


def test_inspect_password():
    import pikepdf
    p = os.path.join(TMP, "geheim.pdf")
    with pikepdf.open(cards()) as pk:
        pk.save(p, encryption=pikepdf.Encryption(owner="o", user="geheim"))
    r = run("inspect", p, "--json")
    assert r.returncode == 1 and events(r)[0]["code"] == "failed" and "Passwort" in events(r)[0]["message"]
    r = run("inspect", p, "--json", "--password", "geheim")
    d = json.loads(r.stdout)
    assert r.returncode == 0 and d["pages"] == 4 and d["encrypted"]


def test_workflow_folders_by_name():
    """Abläufe in den Ablauf-Ordnern beim Namen aufrufen; eigene vor gemeinsamen (Admin) vor denen für alle;
        alte Ordner „ablaeufe“ (bis 1.14) werden zu „workflows“ umbenannt."""
    import shutil
    home, sysd = os.path.join(TMP, "cfg"), os.path.join(TMP, "etc")
    env = dict(ENV, XDG_CONFIG_HOME=home, PDFDRUCK_CONFIG_DIR=sysd)
    old_user, old_sys = os.path.join(home, "passermark", "ablaeufe"), os.path.join(sysd, "ablaeufe")
    user_dir, sys_dir = os.path.join(home, "passermark", "workflows"), os.path.join(sysd, "workflows")
    shared = os.path.join(TMP, "freigabe", "workflows")
    for d in (old_user, old_sys, shared):
        os.makedirs(d, exist_ok=True)
    json.dump({"workflow_dirs": [shared]}, open(os.path.join(sysd, "defaults.json"), "w"))
    wf = {"passermark": "workflow", "version": 1, "description": "Nutzen auf SRA3",
          "steps": [{"job": "impose", "settings": {"sheet": "SRA3", "step_repeat": True}}]}
    json.dump(dict(wf, description="für alle"), open(os.path.join(old_sys, "Karten.json"), "w"))
    json.dump(dict(wf, description="meins"), open(os.path.join(old_user, "karten.json"), "w"))
    json.dump(dict(wf, description="gemeinsam"), open(os.path.join(shared, "Karten.json"), "w"))
    json.dump(dict(wf, description="Team"), open(os.path.join(shared, "Team.json"), "w"))
    json.dump(dict(wf, description="Broschüre", steps=[{"job": "impose", "settings": {"handling": "booklet"}}]),
              open(os.path.join(old_sys, "Broschuere A4.json"), "w"))
    open(os.path.join(old_sys, "kaputt.json"), "w").write("{nix")

    def cli(*args, cwd=TMP):
        return subprocess.run([sys.executable, "-m", "pdfdruck.cli", *args], capture_output=True, text=True,
                              env=env, cwd=cwd, timeout=600)
    r = cli("workflows", "--json")
    d = {w["name"].lower(): w for w in json.loads(r.stdout)}
    assert r.returncode == 0 and set(d) == {"karten", "team", "broschuere a4", "kaputt"}, r.stdout + r.stderr
    assert d["karten"]["source"] == "user" and d["karten"]["description"] == "meins"   # eigener schlägt alle anderen
    assert d["team"]["source"] == "shared"
    assert os.path.isdir(user_dir) and not os.path.exists(old_user) and not os.path.exists(old_sys)  # umbenannt
    assert d["broschuere a4"]["jobs"] == ["impose"] and d["kaputt"]["error"]
    shutil.copy(cards(), os.path.join(TMP, "k.pdf"))
    r = cli("run", "Karten", "aus.pdf", "--in", "k.pdf", "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    assert os.path.isfile(os.path.join(TMP, "aus.pdf"))
    r = cli("run", "Broschuere A4", "b.pdf", "--in", "k.pdf")
    assert r.returncode == 0, r.stdout + r.stderr
    r = cli("run", "gibtsnicht", "--in", "k.pdf", "--json")
    ev = events(r)[0]
    assert r.returncode == 2 and ev["code"] == "not_found" and "karten" in ev["message"].lower()
    r = cli("workflows", "--dirs", "--json")
    d = json.loads(r.stdout)
    assert [x["folder"] for x in d] == [user_dir, shared, sys_dir] and [x["source"] for x in d] == \
        ["user", "shared", "system"]
    r = cli("run", "Team", "t.pdf", "--in", "k.pdf")
    assert r.returncode == 0 and os.path.isfile(os.path.join(TMP, "t.pdf")), r.stdout + r.stderr


def test_old_and_new_folder_both_read():
    """„workflows“ schon von Hand angelegt UND noch ein alter „ablaeufe“: beide werden gelesen, der neue zuerst."""
    home, sysd = os.path.join(TMP, "cfg2"), os.path.join(TMP, "etc2")
    env = dict(ENV, XDG_CONFIG_HOME=home, PDFDRUCK_CONFIG_DIR=sysd)
    new, old = os.path.join(home, "passermark", "workflows"), os.path.join(home, "passermark", "ablaeufe")
    for d in (new, old, sysd):
        os.makedirs(d, exist_ok=True)
    wf = {"passermark": "workflow", "version": 1, "steps": [{"job": "impose", "settings": {"sheet": "A3"}}]}
    json.dump(dict(wf, description="neu"), open(os.path.join(new, "Gleich.json"), "w"))
    json.dump(dict(wf, description="alt"), open(os.path.join(old, "Gleich.json"), "w"))
    json.dump(dict(wf, description="nur alt"), open(os.path.join(old, "Alt.json"), "w"))
    r = subprocess.run([sys.executable, "-m", "pdfdruck.cli", "workflows", "--json"], capture_output=True, text=True,
                       env=env, cwd=TMP, timeout=300)
    d = {w["name"]: w for w in json.loads(r.stdout)}
    assert d["Gleich"]["description"] == "neu" and d["Alt"]["description"] == "nur alt", d
    assert os.path.isdir(old)                       # nichts umbenannt oder überschrieben


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
