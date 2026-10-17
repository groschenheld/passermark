# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Drucken ohne Oberfläche: Optionen über Rollen/Namen auflösen, Ablauf-Schritt "print" mit einem
    nachgebauten Drucker (kein CUPS nötig) – was beim Drucker ankommt, wird geprüft."""
import io, json, os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ.setdefault("PASSERMARK_LANG", "de")
from pdfdruck import printcli, printers, workflow
from pdfdruck.printers import Choice, Option, PrinterCaps, PrinterInfo

TMP = tempfile.mkdtemp(prefix="pm-print-")
MM = 72 / 25.4


def fake_caps(name="Canon"):
    def opt(k, text, choices, default):
        return Option(k, text, "", [Choice(v, t) for v, t in choices], default)
    caps = PrinterCaps(name, "ppd")
    caps.options = {
        "PageSize": opt("PageSize", "Papierformat", [("A4", "A4"), ("A3", "A3"), ("SRA3", "SRA3 320x450mm")], "A4"),
        "InputSlot": opt("InputSlot", "Papierzufuhr", [("Auto", "Automatisch"), ("Cas1", "Fach 1"),
                                                       ("Cas2", "Fach 2"), ("Manual", "Stapelanlage")], "Auto"),
        "MediaType": opt("MediaType", "Medientyp", [("Plain", "Normalpapier"), ("Heavy3", "Schwer 3 (164-220 g)")],
                         "Plain"),
        "Duplex": opt("Duplex", "Beidseitig", [("None", "Aus"), ("DuplexNoTumble", "Lange Kante"),
                                               ("DuplexTumble", "Kurze Kante")], "None"),
        "ColorModel": opt("ColorModel", "Farbmodus", [("CMYK", "Farbe"), ("Gray", "Schwarzweiß")], "CMYK"),
        "StapleLocation": opt("StapleLocation", "Heften", [("None", "Aus"), ("TopLeft", "Heften links oben"),
                                                           ("DualLeft", "Doppelt links")], "None"),
        "CNPunch": opt("CNPunch", "Lochen", [("None", "Aus"), ("2Holes", "2-fach"), ("4Holes", "4-fach")], "None"),
    }
    caps.page_sizes = {"A4": (210 * MM, 297 * MM), "A3": (297 * MM, 420 * MM), "SRA3": (320 * MM, 450 * MM)}
    printers._assign_roles(caps)
    return caps


class FakePrinter:
    """printers.* ersetzen: ein Drucker "Canon", Aufträge werden nur mitgeschrieben."""
    def __enter__(self):
        self.sent = []
        self.saved = (printers.list_printers, printers.load_caps, printers.submit)
        printers.list_printers = lambda: [PrinterInfo("Canon", "Canon", "", "Canon C3822i", 3, "", True)]
        printers.load_caps = lambda name: fake_caps(name)

        def submit(printer, path, title, opts):
            import pypdfium2 as pdfium
            d = pdfium.PdfDocument(path)
            self.sent.append({"printer": printer, "title": title, "opts": dict(opts), "pages": len(d),
                              "size": d.get_page_size(0)})
            d.close()
            return 4711
        printers.submit = submit
        return self

    def __exit__(self, *a):
        printers.list_printers, printers.load_caps, printers.submit = self.saved


def doc(n=4, size=(210, 297)):
    from reportlab.pdfgen import canvas
    p = os.path.join(TMP, f"doc{n}.pdf")
    c = canvas.Canvas(p, pagesize=(size[0] * MM, size[1] * MM))
    for i in range(n):
        c.drawString(100, 100, f"Seite {i + 1}")
        c.showPage()
    c.save()
    return p


def test_match_choice():
    caps = fake_caps()
    assert caps.roles["staple"] == "StapleLocation" and caps.roles["punch"] == "CNPunch"
    m = printcli.match_choice
    assert m(caps.options["PageSize"], "A3") == "A3"
    assert m(caps.options["PageSize"], "sra3 320x450mm") == "SRA3"            # Anzeigename
    assert m(caps.options["InputSlot"], "Fach 2") == "Cas2"
    assert m(caps.options["Duplex"], "long", "duplex") == "DuplexNoTumble"
    assert m(caps.options["Duplex"], "short", "duplex") == "DuplexTumble"
    assert m(caps.options["Duplex"], "none", "duplex") == "None"
    assert m(caps.options["ColorModel"], "gray", "color") == "Gray"
    assert m(caps.options["StapleLocation"], "links oben") == "TopLeft"     # eindeutiger Teil
    try:
        m(caps.options["InputSlot"], "Fach 9")
        assert False
    except ValueError as e:
        assert "Cas1" in str(e)                                               # Auswahl wird genannt


def test_resolve_problems():
    caps = fake_caps()
    s = printcli.PrintSettings(paper="A3", tray="Fach 1", finishing={"staple": "links oben", "binden": "x"},
                               options={"CNPunch": "4-fach", "GibtsNicht": "1"})
    vals, probs = printcli.resolve(caps, caps.defaults(), s)
    assert vals["PageSize"] == "A3" and vals["InputSlot"] == "Cas1" and vals["StapleLocation"] == "TopLeft"
    assert vals["CNPunch"] == "4Holes"
    assert {w for w, _ in probs} == {"finishing.binden", "options.GibtsNicht"}


def test_print_and_dry_run():
    src = doc(4)
    with FakePrinter() as fp:
        s = printcli.PrintSettings(paper="A3", duplex="short", color="gray", copies=3, collate=False,
                                   finishing={"staple": "TopLeft"}, layout={"handling": "multiple", "nup": 2},
                                   dry_run=True)
        info = printcli.print_pdf(src, s)
        assert info["dry_run"] and info["job_id"] is None and not fp.sent
        assert info["printer"] == "Canon" and info["sheet_mm"] == [297.0, 420.0]
        assert info["options"]["PageSize"] == "A3" and info["options"]["StapleLocation"] == "TopLeft"
        s.dry_run = False
        info = printcli.print_pdf(src, s, pages=[0, 1, 2])
        assert info["job_id"] == 4711 and len(fp.sent) == 1
        job = fp.sent[0]
        o = job["opts"]
        assert o["PageSize"] == "A3" and o["Duplex"] == "DuplexTumble" and o["ColorModel"] == "Gray"
        assert o["copies"] == "3" and o["collate"] == "false" and o["StapleLocation"] == "TopLeft"
        assert job["pages"] == 2                                  # 3 Seiten, 2 pro Blatt
        w, h = job["size"]
        assert abs(w / MM - 297) < 1 and abs(h / MM - 420) < 1
        try:
            printcli.print_pdf(src, printcli.PrintSettings(printer="Gibtsnicht"))
            assert False
        except ValueError as e:
            assert "Canon" in str(e)


def test_workflow_print_step():
    src = doc(8, (148, 210))
    wf = {"passermark": "workflow", "version": 1, "input": src,
          "steps": [{"job": "print", "settings": {"paper": "A4", "tray": "Fach 2", "duplex": "short",
                                                  "layout": {"handling": "booklet"}, "finishing": {"staple": "TopLeft"}}}]}
    with FakePrinter() as fp:
        plan = workflow.prepare(wf, TMP)                          # keine Ausgabe nötig: es wird nur gedruckt
        assert plan.output == "" and plan.steps[0].job == "print"
        r = workflow.run(plan)
        assert r["output"] is None and r["steps"][0]["info"]["job_id"] == 4711
        o = fp.sent[0]["opts"]
        assert o["InputSlot"] == "Cas2" and o["Duplex"] == "DuplexTumble"
        assert fp.sent[0]["pages"] == 4                           # 8 Seiten A5 als Broschüre -> 4 Seiten A4
        # Drucken mitten im Ablauf: danach geht es mit demselben PDF weiter, Ergebnis wird gespeichert
        out = os.path.join(TMP, "danach.pdf")
        wf2 = dict(wf, output=out, steps=[{"job": "print", "settings": {"paper": "A4"}},
                                           {"job": "impose", "settings": {"sheet": "A4", "handling": "multiple", "nup": 2}}])
        r = workflow.run(workflow.prepare(wf2, TMP))
        assert os.path.isfile(out) and r["pages"] == 4 and len(fp.sent) == 2
    # Fehler im Ablauf werden schon beim Prüfen gemeldet
    bad = dict(wf, steps=[{"job": "print", "preset": "x", "settings": {"papier": "A4", "layout": {"nupp": 2}}}])
    try:
        workflow.prepare(bad, TMP)
        assert False
    except workflow.WorkflowError as e:
        where = {w for w, _ in e.problems}
        assert {"steps[0].preset", "steps[0].settings.papier", "steps[0].settings.layout.nupp"} <= where, where
    try:
        workflow.prepare(dict(wf, steps=[{"job": "shrink"}]), TMP)  # ohne Druck: Ausgabe Pflicht
        assert False
    except workflow.WorkflowError as e:
        assert any(w == "output" for w, _ in e.problems)


def test_finisher_presets_and_availability():
    caps = fake_caps()
    presets = [{"name": "Broschüre geheftet", "options": {"StapleLocation": "DualLeft", "InputSlot": "Manual"},
                "booklet": True, "devmode": "QUJD"}]
    s = printcli.PrintSettings(finisher_preset="Broschüre geheftet", duplex="short")
    vals, probs = printcli.resolve(caps, caps.defaults(), s, presets)
    assert not probs and vals["StapleLocation"] == "DualLeft" and vals["__devmode__"] == "QUJD"
    assert vals["Duplex"] == "DuplexTumble"                          # einzelne Angaben zusätzlich
    s2 = printcli.PrintSettings(finisher_preset="Broschüre geheftet", finishing={"staple": "TopLeft"})
    vals, _ = printcli.resolve(caps, caps.defaults(), s2, presets)
    assert vals["StapleLocation"] == "TopLeft"                      # einzelne Angabe schlägt Vorlage
    _, probs = printcli.resolve(caps, caps.defaults(), printcli.PrintSettings(finisher_preset="gibts"), presets)
    assert probs and "Broschüre geheftet" in probs[0][1]
    # nicht installierter Finisher laut Treiber (PPD-Einschränkung): wird abgelehnt
    caps._ppd = object()
    caps.conflicts = lambda values: ["CNPunch"] if values.get("CNPunch") == "4Holes" else []
    _, probs = printcli.resolve(caps, caps.defaults(), printcli.PrintSettings(finishing={"punch": "4-fach"}))
    assert probs and probs[0][0] == "finishing.punch"
    _, probs = printcli.resolve(caps, caps.defaults(), printcli.PrintSettings(finishing={"punch": "2-fach"}))
    assert not probs


def test_print_with_preset_and_caps_info():
    from pdfdruck import config
    src = doc(8, (148, 210))
    cfg = dict(config.load())
    cfg["printers"] = {"Canon": {"presets": [{"name": "Heft", "options": {"StapleLocation": "DualLeft",
                                                                          "InputSlot": "Cas2"}, "booklet": True}]}}
    saved = config.load
    config.load = lambda: cfg
    try:
        with FakePrinter() as fp:
            info = printcli.print_pdf(src, printcli.PrintSettings(finisher_preset="Heft", paper="A4"))
            o = fp.sent[0]["opts"]
            assert o["StapleLocation"] == "DualLeft" and o["InputSlot"] == "Cas2" and info["finisher_preset"] == "Heft"
            assert fp.sent[0]["pages"] == 4                          # Vorlage "booklet" -> Broschüre
            d = printcli.caps_info("Canon")
            assert d["finisher_presets"][0]["name"] == "Heft" and d["roles"]["staple"] == "StapleLocation"
            st = next(x for x in d["options"] if x["keyword"] == "StapleLocation")
            assert st["finishing"] and all(c["available"] for c in st["choices"])
            assert not next(x for x in d["options"] if x["keyword"] == "PageSize")["finishing"]
    finally:
        config.load = saved


def test_cli_run_print_only():
    """passermark-cli run mit nur einem Druckschritt (keine Ausgabedatei): Meldung statt Absturz (1.14.2)."""
    import contextlib
    from pdfdruck import cli
    src = doc(3)
    f = os.path.join(TMP, "nur-druck.json")
    for dry in (False, True):
        with open(f, "w", encoding="utf-8") as fh:
            json.dump({"passermark": "workflow", "version": 1,
                       "steps": [{"job": "print", "settings": {"paper": "A3", "dry_run": dry}}]}, fh)
        out = io.StringIO()
        with FakePrinter() as fp, contextlib.redirect_stdout(out):
            rc = cli.main(["run", f, "--in", src])
        txt = out.getvalue()
        assert rc == 0, txt
        if dry:
            assert "Probelauf" in txt and "297 × 420" in txt and not fp.sent, txt
        else:
            assert "Gedruckt auf Canon: 3 Seite(n), Auftrag 4711" in txt and len(fp.sent) == 1, txt


def test_schema_has_print():
    sch = workflow.schema()
    assert "settings.print" in sch["$defs"] and "finishing" in sch["$defs"]["settings.print"]["properties"]


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
