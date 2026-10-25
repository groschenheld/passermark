# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Druckprotokoll (1.16): jeder Druckauftrag mit allen Einstellungen als JSON + printlog.csv, eingeschaltet
    vom Benutzer oder vom Admin erzwungen; passermark-cli reprint druckt ihn genauso nochmal – auch einen Druck
    mitten in einem Ablauf (die Schritte davor werden wieder durchgerechnet)."""
import contextlib, csv, io, json, os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
TMP = tempfile.mkdtemp(prefix="pm-plog-")
os.environ["XDG_CONFIG_HOME"] = os.path.join(TMP, "cfg")
os.environ["XDG_STATE_HOME"] = os.path.join(TMP, "state")
os.environ["PDFDRUCK_CONFIG_DIR"] = os.path.join(TMP, "etc")
os.makedirs(os.environ["PDFDRUCK_CONFIG_DIR"], exist_ok=True)
os.environ.setdefault("PASSERMARK_LANG", "de")
import test_printcli as T
from pdfdruck import cli, l10n, printcli, printlog, workflow

LOGDIR = os.path.join(TMP, "state", "passermark", "printlog")


def logs():
    out = []
    for root, _d, files in os.walk(LOGDIR):
        out += [os.path.join(root, f) for f in files if f.endswith(".json")]
    return sorted(out, key=lambda p: (os.path.getmtime(p), p))


def test_off_by_default_then_on():
    src = T.doc(2)
    with T.FakePrinter():
        printcli.print_pdf(src, printcli.PrintSettings(paper="A4"))
    assert not logs()                                    # aus: nichts geschrieben
    l10n.save_settings(dict(l10n.load_settings(), print_log=True))
    with T.FakePrinter():
        printcli.print_pdf(src, printcli.PrintSettings(paper="A3", duplex="short", copies=2,
                                                       finishing={"staple": "TopLeft"}))
    (p,) = logs()
    rec = json.load(open(p, encoding="utf-8"))
    j = rec["job"]
    assert rec["passermark"] == "printlog" and j["source"] == "cli" and j["printer"] == "Canon"
    assert j["paper"] == "A3" and j["copies"] == 2 and j["job_id"] == 4711 and j["result"] == "sent"
    assert j["options"]["StapleLocation"] == "TopLeft" and j["options"]["Duplex"] == "DuplexTumble"
    assert j["file"] == os.path.abspath(src) and len(j["file_sha256"]) == 64 and j["pages"] == "1-2"
    assert j["sent"]["copies"] == "2" and j["layout"]["handling"]
    assert j["out_pages"] == 2                           # 1.18.3: gesendete Seiten je Exemplar
    rows = list(csv.reader(open(os.path.join(LOGDIR, "printlog.csv"), encoding="utf-8-sig"), delimiter=";"))
    assert rows[0][0] == "time" and rows[1][6] == "Canon" and rows[1][11] == "sent"
    # Nachdruck: genau dieselben Treiberoptionen
    with T.FakePrinter() as fp, contextlib.redirect_stdout(io.StringIO()):
        assert cli.main(["reprint", p, "--quiet"]) == 0
    o = fp.sent[-1]["opts"]
    assert o["PageSize"] == "A3" and o["StapleLocation"] == "TopLeft" and o["copies"] == "2", o
    assert len(logs()) == 2                              # der Nachdruck wird selbst protokolliert
    # Datei inzwischen verändert -> Hinweis; --dry-run sendet nichts
    open(src, "ab").write(b"\n%")
    out = io.StringIO()
    with T.FakePrinter() as fp, contextlib.redirect_stdout(out):
        assert cli.main(["reprint", p, "--dry-run"]) == 0
    assert not fp.sent and "verändert" in out.getvalue(), out.getvalue()


def test_out_pages_bei_nutzen():
    """Mehrfachnutzen: Bogenzahl steht sonst nirgends im Protokoll (PassCount braucht sie)."""
    l10n.save_settings(dict(l10n.load_settings(), print_log=True))
    before = set(logs())
    with T.FakePrinter():
        printcli.print_pdf(T.doc(4), printcli.PrintSettings(paper="A4", layout={"handling": "multiple", "nup": 2}))
    (p,) = set(logs()) - before
    j = json.load(open(p, encoding="utf-8"))["job"]
    assert j["layout"]["handling"] == "multiple" and isinstance(j["out_pages"], int) and j["out_pages"] >= 1


def test_error_logged_and_workflow_reprint():
    src = T.doc(1, (85, 55))
    with T.FakePrinter():
        try:
            printcli.print_pdf(src, printcli.PrintSettings(paper="A4", layout={
                "step_repeat": True, "sr_pass2": True, "sr2_format": "custom", "sr2_w_mm": 999, "sr2_h_mm": 999}))
        except ValueError:
            pass
    # Fehler vor dem Senden (Zielformat fehlt) passieren in print_pdf – im Protokoll nur, was gesendet werden sollte
    n = len(logs())
    wf = {"passermark": "workflow", "version": 1, "input": src, "steps": [
        {"job": "impose", "settings": {"sheet": "A4", "step_repeat": True}},
        {"job": "print", "settings": {"paper": "A4"}}]}
    with T.FakePrinter() as fp:
        workflow.run(workflow.prepare(wf, TMP))
        first = fp.sent[-1]
    rec = json.load(open(logs()[-1], encoding="utf-8"))
    assert len(logs()) == n + 1
    assert rec["job"]["file"] == os.path.abspath(src) and rec["job"]["steps_before"] == ["impose"]
    assert [s["job"] for s in rec["workflow"]["steps"]] == ["impose", "print"]
    with T.FakePrinter() as fp, contextlib.redirect_stdout(io.StringIO()):
        assert cli.main(["reprint", logs()[-1], "--quiet"]) == 0
    assert fp.sent[-1]["size"] == first["size"] and fp.sent[-1]["opts"]["PageSize"] == first["opts"]["PageSize"]


def test_admin_force_and_shared_folder():
    l10n.save_settings(dict(l10n.load_settings(), print_log=False))
    shared = os.path.join(TMP, "gemeinsam")
    json.dump({"print_log": {"force": True, "dir": shared, "keep_days": 30}},
              open(os.path.join(os.environ["PDFDRUCK_CONFIG_DIR"], "defaults.json"), "w"))
    from pdfdruck import cfgvalidate, config
    assert printlog.enabled() and printlog.folder() == shared
    cfgvalidate.validate(config.load(), os.path.join(TMP, "icc"))
    with T.FakePrinter():
        printcli.print_pdf(T.doc(1), printcli.PrintSettings(paper="A4"))
    assert os.path.isfile(os.path.join(shared, "printlog.csv"))
    for bad in ({"force": "ja"}, {"keep_days": -1}, {"dir": "relativ"}, {"x": 1}):
        try:
            cfgvalidate.validate(dict(config.load(), print_log=bad), os.path.join(TMP, "icc"))
            assert False, bad
        except ValueError:
            pass


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
