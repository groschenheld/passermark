# SPDX-License-Identifier: GPL-3.0-or-later
"""Variable Daten: Prüfziffern, Nummerierung, CSV, Felder (Text/QR/Code 128/EAN-13) als Überlagerung, Reihenfolge,
Weiterzählen, Protokoll, {{…}}-Platzhalter, Kommandozeile, Nutzen mit je eigener Seite (inkl. Schneiden und Stapeln)."""
import csv, json, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="pm-vdp-")
os.environ["XDG_CONFIG_HOME"] = TMP
os.environ["APPDATA"] = TMP
os.environ.setdefault("PASSERMARK_LANG", "de")
import pypdfium2 as pdfium
from pdfdruck import layout, vdp
from pdfdruck.layout import LayoutSettings, Sheet, MM

SAMPLE = os.path.join(HERE, "sample.pdf")
CSV = os.path.join(TMP, "daten.csv")
with open(CSV, "w", encoding="utf-8") as f:
    f.write("Name;Ort;Code\nAnna Müller;Graz;4006381333931\nBéla Kovács;Győr;9002236311036\nZoë;Wien;5901234123457\n")


def _text(path, i):
    d = pdfium.PdfDocument(path)
    try:
        return d[i].get_textpage().get_text_range()
    finally:
        d.close()


def test_check_digits_and_numbers():
    assert vdp.check_digit("7992739871", "luhn") == "3"                  # Lehrbuchbeispiel Luhn
    assert vdp.check_digit("400638133393", "ean") == "1"                 # EAN 4006381333931
    assert vdp.check_digit("123456789", "mod11") in "0123456789X"
    nb = vdp.Numbering(start=7, digits=5, prefix="A", check="luhn", suffix="/26")
    assert vdp.format_number(7, nb) == "A000075/26"


def test_csv_autodetect():
    cols, recs = vdp.read_csv(CSV)
    assert cols == ["Name", "Ort", "Code"] and recs[1]["Ort"] == "Győr"
    p = os.path.join(TMP, "komma.csv")
    open(p, "wb").write("a,b\n1,ä\n".encode("cp1252"))
    cols, recs = vdp.read_csv(p)
    assert cols == ["a", "b"] and recs[0]["b"] == "ä"


def test_build_overlays_are_separate_per_copy():
    s = vdp.VdpSettings(csv_path=CSV, order="record", log_path=os.path.join(TMP, "log.csv"), fields=[
        dict(kind="text", content="{{Name}} – {{Ort}} #{{nr}}", x_mm=20, y_mm=20, w_mm=150, h_mm=12, pages="1"),
        dict(kind="qr", content="https://x.at/{{i}}", x_mm=20, y_mm=40, w_mm=30, h_mm=30),
        dict(kind="code128", content="T{{nr}}", x_mm=60, y_mm=40, w_mm=15, h_mm=60, rotate=90),
        dict(kind="ean13", content="{{Code}}", x_mm=60, y_mm=60, w_mm=40, h_mm=20)],
        numbering=vdp.Numbering(start=7, digits=5, prefix="A", check="luhn"))
    data, info = vdp.build(SAMPLE, s, pages=[0, 1])
    out = os.path.join(TMP, "out.pdf")
    open(out, "wb").write(data)
    assert info["records"] == 3 and info["pages"] == 6
    t0, t1, t2 = _text(out, 0), _text(out, 1), _text(out, 2)
    assert "Anna Müller – Graz #A000075" in t0 and "Béla" not in t0           # keine angehäuften Überlagerungen
    assert "Anna" not in t1 and "TA000075" in t1                             # Textfeld nur auf Seite 1
    assert "Béla Kovács – Győr #A000083" in t2
    rows = list(csv.reader(open(s.log_path, encoding="utf-8-sig"), delimiter=";"))
    assert len(rows) == 7 and rows[3][3].startswith("Béla")


def test_each_page_gets_next_record():
    """Gemeldet: auf jeder Seite stand 1 bzw. derselbe Name. Standard jetzt: Seite 1 -> Datensatz 1, Seite 2 -> 2 …"""
    out = os.path.join(TMP, "each.pdf")
    data, info = vdp.build(SAMPLE, vdp.VdpSettings(count=7, fields=[dict(content="Nr {{nr}} i{{i}}")]))
    open(out, "wb").write(data)
    assert info["pages"] == 7 and all(f"Nr {k + 1} i{k + 1}" in _text(out, k) for k in range(7))
    data, info = vdp.build(SAMPLE, vdp.VdpSettings(csv_path=CSV, fields=[dict(content="{{Name}}")]))
    open(out, "wb").write(data)
    assert info["pages"] == 3 and "Anna" in _text(out, 0) and "Béla" in _text(out, 1) and "Zoë" in _text(out, 2)
    # einseitige Vorlage: reihum dieselbe Seite -> 5 Seiten mit 1…5
    data, info = vdp.build(SAMPLE, vdp.VdpSettings(count=5, fields=[dict(content="T{{nr}}")]), pages=[0])
    open(out, "wb").write(data)
    assert info["pages"] == 5 and "T5" in _text(out, 4) and "1" in _text(out, 4)
    assert vdp.page_for_record(vdp.VdpSettings(), 9, 7) == 2


def test_order_reverse_count_and_continue():
    s = vdp.VdpSettings(count=4, fields=[dict(content="Nr {{nr}}")], reverse=True,
                        numbering=vdp.Numbering(start=10, step=5, continue_key="t"))
    data, _ = vdp.build(SAMPLE, s, pages=[0])
    out = os.path.join(TMP, "rev.pdf")
    open(out, "wb").write(data)
    assert "Nr 25" in _text(out, 0) and "Nr 10" in _text(out, 3)            # Abreißblock: höchste oben
    assert vdp.counter_state()["t"] == 30
    data, _ = vdp.build(SAMPLE, s, pages=[0])
    open(out, "wb").write(data)
    assert "Nr 45" in _text(out, 0)                                          # weitergezählt ab 30


def test_placeholders_from_pdf():
    from reportlab.pdfgen import canvas
    p = os.path.join(TMP, "ph.pdf")
    c = canvas.Canvas(p, pagesize=(210 * MM, 297 * MM))
    c.setFont("Helvetica", 14)
    c.drawString(30 * MM, 250 * MM, "{{Name}}")
    c.drawString(30 * MM, 200 * MM, "Fixer Text")
    c.showPage(); c.save()
    d = pdfium.PdfDocument(p)
    ph = vdp.find_placeholders(d)
    d.close()
    assert len(ph) == 1 and abs(ph[0][2][0] - 30) < 1.5 and abs(ph[0][2][1] - 47) < 6
    data, info = vdp.build(p, vdp.VdpSettings(csv_path=CSV, placeholders=True, fields=[]))
    out = os.path.join(TMP, "ph-out.pdf")
    open(out, "wb").write(data)
    t = _text(out, 1)
    assert info["placeholders_removed"] == 1 and "Béla Kovács" in t and "{{" not in t and "Fixer Text" in t


def test_preview_and_trim_kept():
    d = pdfium.PdfDocument(SAMPLE)
    doc, n = vdp.preview(d, 0, vdp.VdpSettings(csv_path=CSV, fields=[dict(content="{{Name}}")]), record=2)
    assert n == 3 and "Zoë" in doc[0].get_textpage().get_text_range()
    doc.close()
    d.close()


def test_cli_and_step_repeat_sequence():
    env = dict(os.environ, PYTHONPATH=ROOT)
    preset = os.path.join(TMP, "karten.json")
    json.dump({"job": "vdp", "settings": {"count": 10, "fields": [{"content": "Ticket {{nr}}"}],
                                          "numbering": {"start": 1, "digits": 3}}}, open(preset, "w"))
    out = os.path.join(TMP, "tickets.pdf")
    r = subprocess.run([sys.executable, "-m", "pdfdruck.cli", "vdp", SAMPLE, out, "--preset", preset, "--pages", "1",
                        "--quiet"], capture_output=True, text=True, env=env, timeout=300)
    assert r.returncode == 0, r.stderr
    d = pdfium.PdfDocument(out)
    assert len(d) == 10
    sizes = [d.get_page_size(i) for i in range(len(d))]
    d.close()
    for stack, first in (("row", [1, 2, 3, 4]), ("stack", [1, 4, 7, 10])):
        s = LayoutSettings(step_repeat=True, sr_sequence=True, sr_stack=stack, sr_mode="grid", sr_cols=2, sr_rows=2,
                           sr_by="long", sr_mm=140)
        plans = layout.plan(sizes, list(range(10)), Sheet(210 * MM, 297 * MM), s)
        assert len(plans) == 3 and [pl.src + 1 for pl in plans[0].placements] == first, stack


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
