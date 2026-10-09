# SPDX-License-Identifier: GPL-3.0-or-later
"""Mitgelieferte Beispiele (Variable Daten) und Anleitungen: im Paket, holen, Presets, Kommandozeile."""
import json, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="pm-bsp-")
os.environ["XDG_CONFIG_HOME"] = TMP
os.environ["APPDATA"] = TMP
os.environ["HOME"] = TMP
os.environ.setdefault("PASSERMARK_LANG", "de")
import pypdfium2 as pdfium
from pdfdruck import examples, presets, vdp

ENV = dict(os.environ, PYTHONPATH=ROOT)


def _cli(*args, cwd=None):
    return subprocess.run([sys.executable, "-m", "pdfdruck.cli", *args], cwd=cwd or TMP, env=ENV,
                          capture_output=True, text=True)


def _pages(p):
    d = pdfium.PdfDocument(p)
    try:
        return len(d), d[0].get_textpage().get_text_range()
    finally:
        d.close()


def test_in_package():
    for p in (examples.CLI_HOWTO, examples.VDP_HOWTO, os.path.join(examples.VDP_DIR, "vorlage-a6.pdf"),
              os.path.join(examples.VDP_DIR, "daten.csv"), os.path.join(examples.VDP_DIR, "LIESMICH.txt")):
        assert os.path.isfile(p), p
    for stem, _ in examples.EXAMPLES:
        assert os.path.isfile(os.path.join(examples.VDP_DIR, "presets", stem + ".json")), stem
        assert os.path.isfile(os.path.join(examples.VDP_DIR, "ergebnis", stem + ".pdf")), stem
    n, text = _pages(examples.VDP_HOWTO)
    assert n >= 5
    full = "".join(pdfium.PdfDocument(examples.VDP_HOWTO)[i].get_textpage().get_text_range() for i in range(n))
    for s in ("passermark-cli beispiele", "EAN-13", "Code 128", "QR-Code", "{{nr}}", "Strg+Umschalt+D"):
        assert s in full, s
    for s in ("Visitenkarte (vCard)", "Spalten zuordnen", "kontakte-outlook.csv"):
        assert s in full, s
    for s in ("Business card", "phone offers", "Wi-Fi access"):          # Handbuch nie in der Systemsprache
        assert s not in full, s


def test_specs_ship_docs_folder():
    for spec in ("windows/passermark.spec", "linux/passermark.spec"):
        t = open(os.path.join(ROOT, spec), encoding="utf-8").read()
        assert '(os.path.join(root, "pdfdruck", "docs"), "pdfdruck/docs")' in t, spec


def test_install_copies_and_registers_presets():
    target = os.path.join(TMP, "ziel")
    d = examples.install(target)
    assert d == os.path.join(target, "vdp")
    assert os.path.isfile(os.path.join(target, "passermark-vdp-anleitung.pdf"))
    names = presets.list_presets("vdp")
    for _, name in examples.EXAMPLES:
        assert name in names, names
    s = presets.load("vdp", "Beispiel 4 – EAN-13")
    assert s.csv_path == os.path.join(d, "daten.csv") and os.path.isfile(s.csv_path)
    data, info = vdp.build(os.path.join(d, "vorlage-a6.pdf"), s)
    assert data[:5] == b"%PDF-"
    # zweimal holen ist kein Fehler
    examples.install(target)


def test_cli_beispiele_and_run_by_name():
    r = _cli("beispiele", os.path.join(TMP, "cli"))
    assert r.returncode == 0, r.stderr
    d = os.path.join(TMP, "cli", "vdp")
    assert d in r.stdout
    out = os.path.join(TMP, "ean.pdf")
    r = _cli("vdp", os.path.join(d, "vorlage-a6.pdf"), out, "--preset", "Beispiel 4 – EAN-13", "--quiet")
    assert r.returncode == 0, r.stderr
    n, text = _pages(out)
    assert n == 3 and "4006381333931" in text


def test_cli_relative_csv_next_to_preset():
    """Mitgelieferte Preset-Datei mit csv_path=daten.csv läuft auch aus einem anderen Ordner."""
    p = os.path.join(examples.VDP_DIR, "presets", "beispiel-2-qr-csv.json")
    assert json.load(open(p, encoding="utf-8"))["settings"]["csv_path"] == "daten.csv"
    out = os.path.join(TMP, "qr.pdf")
    r = _cli("vdp", os.path.join(examples.VDP_DIR, "vorlage-a6.pdf"), out, "--preset", p, "--quiet")
    assert r.returncode == 0, r.stderr
    n, text = _pages(out)
    assert n == 3 and "Anna Huber" in text


def test_examples_numbers():
    """Die in Anleitung und LIESMICH genannten Werte stimmen."""
    assert vdp.check_digit("978316148410", "ean") == "0"
    assert vdp.check_digit("201234500001", "ean") == "8"
    n, text = _pages(os.path.join(examples.VDP_DIR, "ergebnis", "beispiel-1-qr-nummer.pdf"))
    assert n == 5 and "Ticket 0001" in text


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
