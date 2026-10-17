# SPDX-License-Identifier: GPL-3.0-or-later
"""Anleitung zur Kommandozeile: liegt im Paket, Tabellen sind konsistent, Fallbeispiele laufen wirklich."""
import ast, os, shlex, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
os.environ.setdefault("PASSERMARK_LANG", "de")
GEN = os.path.join(ROOT, "docs", "make_cli_howto.py")
PDF = os.path.join(ROOT, "pdfdruck", "docs", "passermark-cli-anleitung.pdf")


def test_pdf_in_package():
    import pypdfium2 as pdfium
    import pdfdruck
    assert os.path.isfile(PDF)
    assert os.path.join(os.path.dirname(pdfdruck.__file__), "docs", "passermark-cli-anleitung.pdf") == PDF
    d = pdfium.PdfDocument(PDF)
    assert len(d) >= 5
    text = "".join(d[i].get_textpage().get_text_range() for i in range(len(d)))
    for job in ("cutcontour", "separate", "manip", "repair", "preflight_fix"):
        assert job in text, job


def test_tables_consistent():
    tree = ast.parse(open(GEN, encoding="utf-8").read())
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "table" and isinstance(n.args[0], ast.List):
            rows = n.args[0].elts
            k = len(rows[0].elts)
            assert all(len(r.elts) == k for r in rows), f"Tabelle in Zeile {n.lineno}: unterschiedlich viele Spalten"


def _examples():
    """All commands from the manual's code boxes (continuation lines joined)."""
    tree = ast.parse(open(GEN, encoding="utf-8").read())
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") in ("code", "example"):
            arg = n.args[-1]
            try:
                txt = ast.literal_eval(arg)
            except ValueError:
                continue
            txt = txt.replace("\\\n", " ")
            for line in txt.splitlines():
                line = line.strip()
                if line.startswith("passermark-cli ") and "<" not in line and "$" not in line:
                    out.append(line)
    return out


def _prepare_inputs(tmp, examples):
    """Create an input file for each example (name as in the manual); list of runnable examples."""
    import test_cutcontour as tc, test_preflight as tp
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    tc.stickers().save(os.path.join(tmp, "bogen.pdf"))
    c = canvas.Canvas(os.path.join(tmp, "logo.pdf"), pagesize=(150 * mm, 100 * mm))
    c.setFillColorRGB(0.8, 0.1, 0.1)
    for x in (30, 60, 90):
        c.rect(x * mm, 40 * mm, 22 * mm, 22 * mm, fill=1, stroke=0)
    c.showPage(); c.save()
    runnable = []
    wfs = _workflows()
    for name, text in wfs.items():                  # Ablauf-Beispiele aus dem Handbuch als Dateien
        open(os.path.join(tmp, name), "w", encoding="utf-8").write(text)
    user_dir = os.path.join(tmp, "passermark", "workflows")     # XDG_CONFIG_HOME=tmp -> eigener Ablauf-Ordner
    os.makedirs(user_dir, exist_ok=True)
    open(os.path.join(user_dir, "Visitenkarten.json"), "w", encoding="utf-8").write(wfs["visitenkarten.json"])
    for cmd in examples:
        args = shlex.split(cmd)[1:]
        if args[0] in ("settings", "list", "presets") or ">" in args or "/pfad/" in cmd:   # Vorlage / Platzhalter-Pfad
            continue
        if args[0] in ("printers", "caps", "serve"):  # echter Drucker / Watcher: eigene Tests
            continue
        if args[0] in API_NO_INPUT:
            runnable.append((cmd, args))
            continue
        if args[0] in ("run", "check"):
            wf = args[1] if args[1].endswith(".json") else "visitenkarten.json"
            if '"print"' in wfs.get(wf, ""):         # druckt – ohne Drucker nicht ausführbar
                continue
            src = os.path.join(tmp, args[args.index("--in") + 1])
            if not os.path.exists(src):
                open(src, "wb").write(tp.problem_pdf())
            runnable.append((cmd, args))
            continue
        src = os.path.join(tmp, args[1])
        if args[0] == "split" and not os.path.exists(src) and args[1] != "bogen.pdf":
            import test_split
            test_split._booklet(src)                 # booklet with double pages
        if not os.path.exists(src):                  # motif jobs: sheet, otherwise problem PDF (layers, form)
            data = (open(os.path.join(tmp, "bogen.pdf"), "rb").read() if args[0] in ("cutcontour", "separate")
                    else tp.problem_pdf())
            open(src, "wb").write(data)
        if "--pages" in args:                        # restrict page selection to the existing page
            args[args.index("--pages") + 1] = "1"
        runnable.append((cmd, args))
    return runnable


API_NO_INPUT = ("version", "schema", "workflows")
QUIET_OK = ("run", "check")                         # Schnittstellen-Befehle mit --quiet


def _workflows():
    """Die Ablauf-Beispiele (WORKFLOWS) aus dem Handbuch-Generator."""
    tree = ast.parse(open(GEN, encoding="utf-8").read())
    for n in tree.body:
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "WORKFLOWS":
            return ast.literal_eval(n.value)
    return {}


def test_workflow_examples_valid():
    """Die gezeigten Abläufe sind gültig (auch der Druck-Ablauf – geprüft wird ohne Drucker)."""
    import json
    from pdfdruck import workflow
    tmp = tempfile.mkdtemp(prefix="pm-howto-wf-")
    for name, text in _workflows().items():
        data = json.loads(text)
        open(os.path.join(tmp, "x.pdf"), "wb").write(b"%PDF-1.4")
        workflow.prepare(data, tmp, [os.path.join(tmp, "x.pdf")], None, {"kunde": "Muster"})


def _watch_example():
    tree = ast.parse(open(GEN, encoding="utf-8").read())
    for n in tree.body:
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "WATCH":
            return ast.literal_eval(n.value)
    raise AssertionError("WATCH fehlt")


def test_watch_example_runs():
    """Das Watcher-Beispiel ist gültig und verarbeitet eine Datei (der Druck-Ordner bleibt leer)."""
    import json
    tmp = tempfile.mkdtemp(prefix="pm-howto-watch-")
    open(os.path.join(tmp, "watch.json"), "w", encoding="utf-8").write(_watch_example())
    for name, text in _workflows().items():
        open(os.path.join(tmp, name), "w", encoding="utf-8").write(text)
    for d in ("visitenkarten", "drucken"):
        os.makedirs(os.path.join(tmp, "eingang", d))
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(os.path.join(tmp, "eingang", "visitenkarten", "karten.pdf"), pagesize=(91 * 72 / 25.4, 61 * 72 / 25.4))
    for _ in range(2):                                # Vorder- und Rückseite (Ablauf: pages 1-2)
        c.drawString(20, 20, "Karte"); c.showPage()
    c.save()
    env = dict(os.environ, PYTHONPATH=ROOT, PASSERMARK_LANG="de", XDG_CONFIG_HOME=tmp, APPDATA=tmp)
    cmds = [ln.strip() for ln in "\n".join(e for e in _examples_raw() if "serve" in e).splitlines()
            if ln.strip().startswith("passermark-cli serve")]
    assert len(cmds) == 3, cmds
    for cmd in cmds[:2]:                              # --check, --once (der dritte läuft dauerhaft)
        r = subprocess.run([sys.executable, "-m", "pdfdruck.cli", *shlex.split(cmd)[1:]], cwd=tmp, env=env,
                           capture_output=True, text=True, timeout=600)
        assert r.returncode == 0, cmd + "\n" + r.stdout + r.stderr
    assert os.listdir(os.path.join(tmp, "eingang", "visitenkarten", "output")) == ["karten.pdf"]
    assert os.listdir(os.path.join(tmp, "eingang", "visitenkarten", "processed")) == ["karten.pdf"]


def _examples_raw():
    tree = ast.parse(open(GEN, encoding="utf-8").read())
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") in ("code", "example"):
            try:
                out.append(ast.literal_eval(n.args[-1]))
            except ValueError:
                pass
    return out


def test_every_example_has_input():
    """Independent of Ghostscript: every runnable example has its input file (bug from build 1.6.2)."""
    tmp = tempfile.mkdtemp(prefix="pm-howto-in-")
    runnable = _prepare_inputs(tmp, _examples())
    assert len(runnable) >= 15, len(runnable)
    for cmd, args in runnable:
        if args[0] in API_NO_INPUT:
            continue
        f = args[args.index("--in") + 1] if args[0] in ("run", "check") else args[1]
        assert os.path.isfile(os.path.join(tmp, f)), cmd


def test_examples_run():
    """Really run every example; those needing Ghostscript only if it is present (GitHub build)."""
    from pdfdruck import platform as pl
    tmp = tempfile.mkdtemp(prefix="pm-howto-")
    runnable = _prepare_inputs(tmp, _examples())
    gs = bool(pl.ghostscript())
    env = dict(os.environ, PYTHONPATH=ROOT, PASSERMARK_LANG="de", XDG_CONFIG_HOME=tmp, APPDATA=tmp)
    subprocess.run([sys.executable, "-c", "from pdfdruck import presets, cutcontour, vdp; "
                    "presets.save('cutcontour', 'Sticker rund', cutcontour.CutSettings(shape='rounded')); "
                    "presets.save('vdp', 'Tickets', vdp.VdpSettings(fields=[dict(content='Nr. {{nr}}')])); "
                    "presets.save('vdp', 'Namensschilder', vdp.VdpSettings(fields=[dict(content='{{Name}}'), "
                    "dict(kind='qr', content='{{Name}}', y_mm=30, w_mm=25, h_mm=25)])); "
                    "presets.save('vdp', 'Visitenkarte', vdp.VdpSettings(fields=[dict(content='{{Vorname}}'), "
                    "dict(kind='qr', qr_type='vcard', y_mm=30, w_mm=35, h_mm=35)]))"],
                   cwd=tmp, env=env, check=True)
    open(os.path.join(tmp, "gaeste.csv"), "w", encoding="utf-8").write("Name;Firma\nAnna;A\nBéla;B\n")
    subprocess.run([sys.executable, "-m", "pdfdruck.cli", "settings", "cutcontour"], cwd=tmp, env=env, check=True,
                   stdout=open(os.path.join(tmp, "sticker.json"), "w"))
    ran = 0
    for cmd, args in runnable:
        needs_gs = args[0] == "repair" or "cmyk=true" in cmd or any(f in cmd for f in ("embed_fonts", "outline_text",
                                                                                     "flatten_transparency"))
        if needs_gs and not gs:
            continue
        quiet = ["--quiet"] if (args[0] not in API_NO_INPUT + ("inspect",) or args[0] in QUIET_OK) else []
        if args[0] in QUIET_OK and "--json" in args:
            quiet = []
        r = subprocess.run([sys.executable, "-m", "pdfdruck.cli", *args, *quiet], cwd=tmp, env=env,
                           capture_output=True, text=True, timeout=600)
        assert r.returncode == 0, f"{cmd}\n{r.stderr}"
        ran += 1
    assert ran >= 12, ran


def test_bash_loop_verbatim():
    """Run the folder example (Linux) literally from the manual in a bash shell."""
    import shutil
    if not shutil.which("bash"):
        return
    import test_cutcontour as tc
    src = open(GEN, encoding="utf-8").read()
    start = src.index("mkdir -p fertig\nfor f in eingang/*.pdf; do")
    Q = "'" * 3
    snippet = ast.literal_eval(src[src.rindex(Q, 0, start):src.index(Q, start) + 3])
    tmp = tempfile.mkdtemp(prefix="pm-loop-")
    os.makedirs(os.path.join(tmp, "eingang"))
    tc.stickers().save(os.path.join(tmp, "eingang", "a.pdf"))
    tc.stickers().save(os.path.join(tmp, "eingang", "b.pdf"))
    env = dict(os.environ, PYTHONPATH=ROOT, PASSERMARK_LANG="de", XDG_CONFIG_HOME=tmp, APPDATA=tmp)
    subprocess.run([sys.executable, "-c", "from pdfdruck import presets, cutcontour; "
                    "presets.save('cutcontour', 'Sticker rund', cutcontour.CutSettings(shape='rounded'))"],
                   cwd=tmp, env=env, check=True)
    subprocess.run([sys.executable, "-m", "pdfdruck.cli", "settings", "cutcontour"], cwd=tmp, env=env, check=True,
                   stdout=open(os.path.join(tmp, "sticker.json"), "w"))
    script = f'passermark-cli() {{ "{sys.executable}" -m pdfdruck.cli "$@"; }}\n' + snippet
    r = subprocess.run(["bash", "-c", script], cwd=tmp, env=env, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0 and "FEHLER" not in r.stdout, r.stdout + r.stderr
    assert sorted(os.listdir(os.path.join(tmp, "fertig"))) == ["a-cut.pdf", "b-cut.pdf"]


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("ok", k)
