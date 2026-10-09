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
    """Alle Befehle aus den Code-Kästen der Anleitung (Fortsetzungszeilen zusammengefügt)."""
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
    """Für jedes Beispiel eine Eingabedatei anlegen (Name wie in der Anleitung); Liste der ausführbaren Beispiele."""
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
    for cmd in examples:
        args = shlex.split(cmd)[1:]
        if args[0] in ("settings", "list", "presets") or ">" in args or "/pfad/" in cmd:   # Vorlage / Platzhalter-Pfad
            continue
        src = os.path.join(tmp, args[1])
        if not os.path.exists(src):                  # Motiv-Aufträge: Bogen, sonst Problem-PDF (Ebenen, Formular)
            data = (open(os.path.join(tmp, "bogen.pdf"), "rb").read() if args[0] in ("cutcontour", "separate")
                    else tp.problem_pdf())
            open(src, "wb").write(data)
        if "--pages" in args:                        # Seitenauswahl auf die vorhandene Seite beschränken
            args[args.index("--pages") + 1] = "1"
        runnable.append((cmd, args))
    return runnable


def test_every_example_has_input():
    """Unabhängig von Ghostscript: jedes ausführbare Beispiel hat seine Eingabedatei (Fehler aus dem Build 1.6.2)."""
    tmp = tempfile.mkdtemp(prefix="pm-howto-in-")
    runnable = _prepare_inputs(tmp, _examples())
    assert len(runnable) >= 15, len(runnable)
    for cmd, args in runnable:
        assert os.path.isfile(os.path.join(tmp, args[1])), cmd


def test_examples_run():
    """Jedes Beispiel echt ausführen; die mit Ghostscript nur, wenn es da ist (GitHub-Build)."""
    from pdfdruck import platform as pl
    tmp = tempfile.mkdtemp(prefix="pm-howto-")
    runnable = _prepare_inputs(tmp, _examples())
    gs = bool(pl.ghostscript())
    env = dict(os.environ, PYTHONPATH=ROOT, PASSERMARK_LANG="de", XDG_CONFIG_HOME=tmp, APPDATA=tmp)
    subprocess.run([sys.executable, "-c", "from pdfdruck import presets, cutcontour, vdp; "
                    "presets.save('cutcontour', 'Sticker rund', cutcontour.CutSettings(shape='rounded')); "
                    "presets.save('vdp', 'Tickets', vdp.VdpSettings(fields=[dict(content='Nr. {{nr}}')])); "
                    "presets.save('vdp', 'Namensschilder', vdp.VdpSettings(fields=[dict(content='{{Name}}'), "
                    "dict(kind='qr', content='{{Name}}', y_mm=30, w_mm=25, h_mm=25)]))"],
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
        r = subprocess.run([sys.executable, "-m", "pdfdruck.cli", *args, "--quiet"], cwd=tmp, env=env,
                           capture_output=True, text=True, timeout=600)
        assert r.returncode == 0, f"{cmd}\n{r.stderr}"
        ran += 1
    assert ran >= 12, ran


def test_bash_loop_verbatim():
    """Das Ordner-Beispiel (Linux) wörtlich aus der Anleitung in einer Bash ausführen."""
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
