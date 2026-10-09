# SPDX-License-Identifier: GPL-3.0-or-later
"""Daten erfassen (1.10): Datenarten, Inhalt der Codes, Prüfung, CSV, QR-Feld mit „Art“, Ruhezone – und die
erzeugten Codes werden wirklich gelesen (QR/EAN mit OpenCV, falls installiert; Code 128 mit eigenem Leser)."""
import os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
TMP = tempfile.mkdtemp(prefix="pm-dk-")
os.environ["XDG_CONFIG_HOME"] = TMP
os.environ["APPDATA"] = TMP
os.environ.setdefault("PASSERMARK_LANG", "de")
import pypdfium2 as pdfium
from pdfdruck import datakinds as D, vdp
import _codes as C

SAMPLE = os.path.join(HERE, "sample.pdf")


def _a6():
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    p = os.path.join(TMP, "a6.pdf")
    if not os.path.exists(p):
        c = canvas.Canvas(p, pagesize=(148 * mm, 105 * mm))
        c.showPage()
        c.save()
    return p


def test_kinds_complete():
    ks = D.kinds()
    assert tuple(ks) == D.IDS
    for kid, k in ks.items():
        assert k.cols and k.field_kind in vdp.KINDS, kid
        D.build(kid, D.example_row(kid))           # Beispielzeile ist gültig
        assert D.validate(kid, D.columns(kid), [D.example_row(kid)]) == [], kid
    for t in D.QR_TYPES[1:]:
        assert D.get(t).field_kind == "qr"


def test_build_contents():
    assert D.build("url", {"Adresse": "huber.at/x"}) == "https://huber.at/x"
    assert D.build("url", {"adresse": "mailto:a@b.at"}) == "mailto:a@b.at"        # Groß/klein egal
    assert D.build("phone", {"Telefon": "0043 316 / 12 34-56"}) == "tel:+4331612345" + "6"
    assert D.build("email", {"E-Mail": "a@b.at", "Betreff": "A & B"}) == "mailto:a@b.at?subject=A%20%26%20B"
    assert D.build("wifi", {"Netzname": "N;1", "Passwort": 'p:"x'}) == 'WIFI:T:WPA;S:N\\;1;P:p\\:\\"x;;'
    assert D.build("wifi", {"Netzname": "Offen", "Passwort": ""}) == "WIFI:T:nopass;S:Offen;;"
    assert D.build("wifi", {"Netzname": "W", "Passwort": "x", "Verschlüsselung": "WEP", "Versteckt": "ja"}) == \
        "WIFI:T:WEP;S:W;P:x;H:true;;"
    v = D.build("vcard", {"Vorname": "Zoë", "Nachname": "Kovács", "Notiz": "a;b,c"})
    assert "N:Kovács;Zoë;;;" in v and "FN:Zoë Kovács" in v and "NOTE:a\\;b\\,c" in v and v.startswith("BEGIN:VCARD")
    e = D.build("event", {"Titel": "Fest", "Beginn": "24.10.2026 18:00"})
    assert "DTSTART:20261024T180000" in e and "DTEND:20261024T190000" in e
    e = D.build("event", {"Titel": "Messe", "Beginn": "2026-11-02", "Ende": "2026-11-04"})
    assert "DTSTART;VALUE=DATE:20261102" in e
    assert D.build("geo", {"Breite": "47,0707", "Länge": "15.4395"}) == "geo:47.0707,15.4395"
    for kid, rec in (("wifi", {"Netzname": ""}), ("vcard", {}), ("event", {"Titel": "x", "Beginn": "morgen"}),
                     ("geo", {"Breite": "100", "Länge": "1"}), ("wifi", {"Netzname": "x", "Verschlüsselung": "ROT13"})):
        try:
            D.build(kid, rec)
            raise AssertionError(kid)
        except ValueError:
            pass


def test_validate_and_guess():
    p = D.validate("ean13", ["EAN"], [{"EAN": "4006381333932"}, {"EAN": "400638133393"}, {"EAN": "ART1"}, {"EAN": ""}])
    assert [(r, c) for r, c, _m in p] == [(0, "EAN"), (2, "EAN")], p
    assert "4006381333931" in p[0][2]
    assert D.validate("wifi", ["Passwort"], [])[0][:2] == (-1, "Netzname")
    assert D.validate("code128", ["Code"], [{"Code": "Größe"}])[0][1] == "Code"
    assert D.guess_kind(["Vorname", "Nachname", "E-Mail"]) == "vcard"
    assert D.guess_kind(["telefon"]) == "phone"
    assert D.guess_kind(["Netzname", "Passwort"]) == "wifi"
    assert D.guess_kind(["Name", "Tisch"]) == "text"
    assert D.series(3, 8, 2, 4, "T", "/26") == ["T0008/26", "T0010/26", "T0012/26"]


def test_csv_roundtrip_excel_safe():
    p = os.path.join(TMP, "k.csv")
    rows = [{"Vorname": "Zoë", "Nachname": "Müller; Söhne", "Notiz": "zwei\nZeilen"}, {"Vorname": "", "Nachname": ""}]
    D.write_csv(p, D.columns("vcard"), rows)
    assert open(p, "rb").read(3) == b"\xef\xbb\xbf"                 # BOM: Excel erkennt UTF-8
    cols, back = vdp.read_csv(p)
    assert cols == D.columns("vcard") and len(back) == 1             # leere Zeile fällt weg
    assert back[0]["Nachname"] == "Müller; Söhne" and back[0]["Notiz"] == "zwei\nZeilen"


def test_ean_wrong_check_digit_is_an_error():
    s = vdp.VdpSettings(count=1, fields=[vdp.VdpField("ean13", "4006381333932", 10, 10, 40, 28)])
    try:
        vdp.build(_a6(), s)
        raise AssertionError("falsche Prüfziffer ging durch")
    except ValueError as e:
        assert "4006381333931" in str(e)


def test_qr_types_scan_back():
    """Jede QR-Art aus einer CSV erzeugen und wieder lesen – Inhalt muss genau stimmen."""
    if not C.HAVE_CV2:
        print("  (OpenCV fehlt – Lesen übersprungen)")
        return
    extra = {"vcard": {"Vorname": "Zoë", "Nachname": "Müller-Szabó", "Notiz": "a; b, c"},
             "wifi": {"Netzname": "Gäste;Netz", "Passwort": 'a:b"c'},
             "email": {"Betreff": "Anfrage & Angebot", "Text": "Grüße\naus Graz"}}
    for kid in D.QR_TYPES[1:]:
        rec = D.example_row(kid)
        rec.update(extra.get(kid, {}))
        p = os.path.join(TMP, kid + ".csv")
        D.write_csv(p, D.columns(kid), [rec, rec])
        s = vdp.VdpSettings(csv_path=p, fields=[vdp.VdpField("qr", "", 40, 10, 60, 60, qr_type=kid)])
        data, info = vdp.build(_a6(), s)
        assert info["pages"] == 2
        d = pdfium.PdfDocument(data)
        got = C.read_qr(C.page_gray(d[0]))
        d.close()
        exp = D.build(kid, rec).replace("\r\n", "\n")
        assert got and got[0].replace("\r\n", "\n") == exp, (kid, got, exp)


def test_quiet_zone_makes_qr_readable_alone():
    """Mit Ruhezone ist der QR-Code auch als enger Ausschnitt lesbar (vorher nicht)."""
    if not C.HAVE_CV2:
        return
    res = {}
    for quiet in (True, False):
        s = vdp.VdpSettings(count=1, fields=[vdp.VdpField("qr", "https://huber.at/t/{{nr}}", 40, 10, 40, 40,
                                                          quiet=quiet)])
        d = pdfium.PdfDocument(vdp.build(_a6(), s)[0])
        img = C.page_gray(d[0], 6)
        d.close()
        res[quiet] = C.read_qr(C.crop_mm(img, 6, 40, 10, 40, 40, pad_px=0))
    assert res[True] == ["https://huber.at/t/1"], res


def test_code128_and_ean_scan_back():
    vals = ["T0001", "ART-1001", "Hallo Welt 123", "12345678901234"]
    p = os.path.join(TMP, "c.csv")
    D.write_csv(p, ["Code", "EAN"], [{"Code": v, "EAN": e} for v, e in
                                     zip(vals, ["4006381333931", "978316148410", "5901234123457", "201234500001"])])
    s = vdp.VdpSettings(csv_path=p, fields=[vdp.VdpField("code128", "{{Code}}", 10, 10, 70, 20, size_pt=9),
                                            vdp.VdpField("ean13", "{{EAN}}", 10, 50, 40, 28)])
    d = pdfium.PdfDocument(vdp.build(_a6(), s)[0])
    eans = []
    for i, v in enumerate(vals):
        img = C.page_gray(d[i], 6)
        assert C.read_code128(C.crop_mm(img, 6, 10, 10, 70, 15)) == v, (i, v)
        if C.HAVE_CV2:
            eans += C.read_ean(C.page_gray(d[i], 4))
    d.close()
    if C.HAVE_CV2:
        assert eans == ["4006381333931", "9783161484100", "5901234123457", "2012345000018"], eans


def test_old_presets_still_load():
    """Presets ohne qr_type/quiet (bis 1.9) laden weiter – Standard: Inhalt wie eingegeben, mit Ruhezone."""
    s = vdp.VdpSettings(count=1, fields=[{"kind": "qr", "content": "x", "x_mm": 1, "y_mm": 1, "w_mm": 20,
                                          "h_mm": 20}])
    f = vdp._fields(s)[0]
    assert f.qr_type == "text" and f.quiet is True
    try:
        vdp._fields(vdp.VdpSettings(fields=[{"kind": "qr", "qr_type": "fax"}]))
        raise AssertionError
    except ValueError:
        pass


GUI = r'''
import sys, os, types
from pdfdruck.gui.datadialog import DataDialog, field_for
from pdfdruck import datakinds as D, vdp
tmp = sys.argv[2]
dlg = DataDialog(None, "", "wifi")
assert dlg.kind == "wifi" and dlg.cols == D.columns("wifi") and len(dlg.rows) == 5
dlg.paste_text("Gaeste\tsommer\tWPA\nBuero\tgeheim\t\t\nCafe\t\tkeine\n", 0, 0)
assert [r["Netzname"] for r in dlg.data_rows()] == ["Gaeste", "Buero", "Cafe"]
assert dlg.problems() == [], dlg.problems()
dlg.duplicate(0); assert dlg.rows[1]["Netzname"] == "Gaeste"
dlg.delete([1]); assert dlg.rows[1]["Netzname"] == "Buero"
assert dlg.add_column("Tisch") and not dlg.add_column("tisch") and not dlg.add_column("{x}")
dlg.fill_column("Tisch", 1, 1, 2, "T")
assert dlg.rows[0]["Tisch"] == "T01" and dlg.rows[2]["Tisch"] == "T03"
p = os.path.join(tmp, "wlan.csv"); dlg.save(p)
assert not dlg.dirty and dlg.path == p
d2 = DataDialog(None, p)
assert d2.kind == "wifi" and len(d2.data_rows()) == 5 and "Tisch" in d2.cols   # Füllen nimmt alle 5 Zeilen
d5 = DataDialog(None, "", "code128"); d5.fill_column("Code", 1, 1, 4, "T", count=100)
assert len(d5.data_rows()) == 100 and d5.rows[99]["Code"] == "T0100" and d5.problems() == []
d2.set_kind("vcard")                                     # Art wechseln: Spalten dazu, Daten bleiben
assert "Vorname" in d2.cols and d2.rows[0]["Netzname"] == "Gaeste"
d3 = DataDialog(None, "", "ean13"); d3.paste_text("4006381333932\nabc", 0, 0)
assert len(d3.problems()) == 2
d3._show_row(0); d3._check()
d4 = DataDialog(None, "", "vcard"); d4.add_row(D.example_row("vcard")); d4._show_row(len(d4.rows) - 1)
f = field_for("vcard", 148, 105); assert f.kind == "qr" and f.qr_type == "vcard"
f = field_for("qrtext", 148, 105); assert f.kind == "qr" and f.qr_type == "text" and f.content == "{{Inhalt}}"
f = field_for("ean13", 30, 20); assert f.content == "{{EAN}}" and f.x_mm >= 0
import pypdfium2 as pdfium
from pdfdruck.gui.vdpdialog import VdpDialog
vd = VdpDialog(None, pdfium.PdfDocument(sys.argv[1]), 0)
vd.use_data(p, "wifi")
assert [x.kind for x in vd.fields] == ["qr"] and vd.fields[0].qr_type == "wifi", vd.fields
vd.use_data(p, "wifi")                                   # zweimal: kein zweites Feld
assert len(vd.fields) == 1
vd._qr_widgets(vd.fields[0]); vd._refresh()
s = vd._settings()
assert s.fields[0]["qr_type"] == "wifi" and s.csv_path == p and s.order == "each", s
# Hauptfenster: Daten erfassen (ohne und mit Dokument), Variable Daten mit übergebener Tabelle
from pdfdruck.gui import viewer
from pdfdruck import config
from pdfdruck.gui.common import Session
viewer.PageView._dpi_scale = lambda self: 1.0
viewer.PageView.page_zoom = lambda self, i: 1.0
w = viewer.MainWindow(types.SimpleNamespace(view_single=True, session=Session(config.BUILTIN), windows=[]))
w.data_dialog()
w._set_doc(pdfium.PdfDocument(sys.argv[1]), sys.argv[1], "x.pdf", False)
w.data_dialog()
w.vdp_dialog((p, "wifi"))
w.set_workspace("vdp")
print("ok")
'''


def test_gui_data_dialog():
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.join(HERE, "_qtstub"), ROOT, HERE]),
               QT_QPA_PLATFORM="offscreen")
    r = subprocess.run([sys.executable, "-c", GUI, SAMPLE, TMP], capture_output=True, text=True, env=env, timeout=300)
    assert r.returncode == 0 and r.stdout.strip().endswith("ok"), r.stdout[-2000:] + r.stderr[-4000:]


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
