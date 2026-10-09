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


def test_code128_klartext_in_schriftgroesse():
    """Klartext unter Code 128 wird in der eingestellten Größe gesetzt, nicht mit den Strichen verzerrt."""
    out = os.path.join(TMP, "c128.pdf")
    s = vdp.VdpSettings(count=1, fields=[vdp.VdpField("code128", "T{{nr}}", 10, 10, 120, 40, size_pt=9)])
    with open(out, "wb") as f:
        f.write(vdp.build(SAMPLE, s, pages=[0])[0])
    d = pdfium.PdfDocument(out)
    tp = d[0].get_textpage()
    assert "T1" in tp.get_text_range()
    i = tp.get_text_range().index("T1")
    l, b, r, t = tp.get_charbox(i)
    assert (t - b) < 12, (t - b)                 # 9 pt Schrift, nicht auf 40 mm Kastenhöhe gestreckt
    d.close()


def test_front_back_pages_per_record_and_parity():
    """100-Visitenkarten-Fall: Vorder-/Rückseite je Datensatz, Name nur ungerade, QR nur gerade (1.10.2)."""
    from reportlab.lib.units import mm as _mm
    from reportlab.pdfgen import canvas as _cv
    for npages in (2, 6):                                   # Vorlage 2 Seiten (reihum) oder schon 3 Karten × 2
        tpl = os.path.join(TMP, f"karte{npages}.pdf")
        c = _cv.Canvas(tpl, pagesize=(85 * _mm, 55 * _mm))
        for i in range(npages):
            c.drawString(5, 5, "VORNE" if i % 2 == 0 else "HINTEN")
            c.showPage()
        c.save()
        s = vdp.VdpSettings(csv_path=CSV, pages_per_record=2, fields=[
            vdp.VdpField("text", "{{Name}} S{{seite}}/{{seiten}} V{{vorlagenseite}} D{{datensatz}}/{{datensaetze}}",
                         2, 2, 80, 6, size_pt=6, pages="ungerade"),
            vdp.VdpField("text", "QR {{Name}}", 2, 20, 80, 6, size_pt=6, pages="gerade")])
        out = os.path.join(TMP, f"karten{npages}.pdf")
        data, info = vdp.build(tpl, s)
        open(out, "wb").write(data)
        assert info["pages"] == 6, info
        t = [_text(out, i) for i in range(6)]
        assert "Anna Müller S1/6 V1 D1/3" in t[0] and "VORNE" in t[0] and "QR" not in t[0], t[0]
        assert "QR Anna Müller" in t[1] and "HINTEN" in t[1] and "S2" not in t[1], t[1]
        assert "Béla Kovács S3/6" in t[2] and "QR Béla Kovács" in t[3]
        assert "QR Zoë" in t[5]


def test_page_set_parity_and_ranges():
    assert sorted(vdp._page_set("ungerade", 6)) == [0, 2, 4]
    assert sorted(vdp._page_set("gerade", 6)) == [1, 3, 5]
    assert sorted(vdp._page_set("ungerade 3-6, 2", 8)) == [1, 2, 4]
    assert sorted(vdp._page_set("odd", 4)) == [0, 2] and sorted(vdp._page_set("", 3)) == [0, 1, 2]
    assert vdp.sequence("each", 2, [0, 1, 2, 3], 2) == [(0, 0), (0, 1), (1, 2), (1, 3)]
    assert vdp.sequence("each", 3, [0, 1], 2) == [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0), (2, 1)]
    assert vdp.sequence("each", 3, [0, 1]) == [(0, 0), (1, 1), (2, 0)]


def test_more_variables():
    import datetime as dt
    now = dt.datetime(2026, 10, 9, 14, 5)
    rec = {"Name": "Anna", "datum": "aus CSV", "_sys": vdp.system_vars(vdp.VdpSettings(doc_name="flyer.pdf"), 7, now)}
    assert vdp.fill("{{datum}}", rec) == "aus CSV"                       # CSV-Spalte geht vor
    del rec["datum"]
    out = vdp.fill("{{datum}} {{zeit}} {{jahr}} {{kw}} {{wochentag}} {{datei}} {{datensaetze}} {{datum:%y%m%d}}", rec)
    assert out == "09.10.2026 14:05 2026 41 Freitag flyer 7 261009", out
    z = vdp.fill("{{zufall}}|{{zufall:10}}|{{code:8}}|{{uuid}}", rec).split("|")
    assert len(z[0]) == 6 and z[0].isdigit() and len(z[1]) == 10 and len(z[2]) == 8 and len(z[3]) == 36, z
    assert not set(z[2]) & set("0O1I")
    assert vdp.fill("{{gibtsnicht}} {{Name}}", rec) == "{{gibtsnicht}} Anna"
    names = [p for p, _ in vdp.variables_help()]
    assert "{{datum}}" in names and "{{seite}}" in names and "{{zufall:10}}" in names
    # Datenarten sehen die Variablen nicht als Spalten (z. B. Termin-Beginn ≠ {{datum}})
    from pdfdruck import datakinds
    assert datakinds.mapped("event", {"Titel": "x", "_sys": {"datum": "1.1.2026"}})["Beginn"] == ""


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
