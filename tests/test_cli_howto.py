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


def test_examples_run():
    """Jedes Beispiel echt ausführen (ohne die, die Ghostscript oder fremde Dateien brauchen)."""
    import test_cutcontour as tc, test_preflight as tp
    from pdfdruck import platform as pl
    tmp = tempfile.mkdtemp(prefix="pm-howto-")
    tc.stickers().save(os.path.join(tmp, "bogen.pdf"))
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(os.path.join(tmp, "logo.pdf"), pagesize=(150 * mm, 100 * mm))
    c.setFillColorRGB(0.8, 0.1, 0.1)
    for x in (30, 60, 90):
        c.rect(x * mm, 40 * mm, 22 * mm, 22 * mm, fill=1, stroke=0)
    c.showPage(); c.save()
    for name in ("plan", "flyer", "foto", "mappe", "scan", "plakat"):
        src = tp.problem_pdf() if name in ("plan", "flyer", "foto") else open(os.path.join(tmp, "bogen.pdf"), "rb").read()
        open(os.path.join(tmp, f"{name}.pdf"), "wb").write(src)
    gs = bool(pl.ghostscript())
    env = dict(os.environ, PYTHONPATH=ROOT, PASSERMARK_LANG="de")
    ran = 0
    examples = _examples()
    assert len(examples) >= 15, len(examples)
    # Preset aus der Anleitung anlegen
    subprocess.run([sys.executable, "-m", "pdfdruck.cli", "settings", "cutcontour"], cwd=tmp, env=env, check=True,
                   stdout=open(os.path.join(tmp, "sticker.json"), "w"))
    for cmd in examples:
        args = shlex.split(cmd)[1:]
        needs_gs = args[0] == "repair" or "cmyk=true" in cmd or any(f in cmd for f in ("embed_fonts", "outline_text",
                                                                                     "flatten_transparency"))
        if (needs_gs and not gs) or args[0] in ("settings", "list") or ">" in args:
            continue
        if "mappe.pdf" in cmd:                         # Seiten 1,3-5 brauchen 5 Seiten
            args = [a if a != "1,3-5" else "1" for a in args]
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
    env = dict(os.environ, PYTHONPATH=ROOT, PASSERMARK_LANG="de")
    subprocess.run([sys.executable, "-m", "pdfdruck.cli", "settings", "cutcontour"], cwd=tmp, env=env, check=True,
                   stdout=open(os.path.join(tmp, "sticker.json"), "w"))
    script = f'passermark-cli() {{ "{sys.executable}" -m pdfdruck.cli "$@"; }}\n' + snippet
    r = subprocess.run(["bash", "-c", script], cwd=tmp, env=env, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0 and "FEHLER" not in r.stdout, r.stdout + r.stderr
    assert sorted(os.listdir(os.path.join(tmp, "fertig"))) == ["a-cut.pdf", "b-cut.pdf"]


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("ok", k)
