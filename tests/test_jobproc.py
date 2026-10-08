# SPDX-License-Identifier: GPL-3.0-or-later
"""Aufträge als eigener Prozess (echte Prozesse): Erfolg, Fehler, Abbrechen, Absturz, Aufräumen."""
import glob, os, sys, tempfile, time, threading
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
os.environ.setdefault("PASSERMARK_LANG", "de")
import pypdfium2 as pdfium
from pdfdruck import jobproc

TMP = tempfile.mkdtemp(prefix="pm-job-")


def stickers():
    p = os.path.join(TMP, "bogen.pdf")
    if not os.path.exists(p):
        import test_cutcontour as tc
        tc.stickers().save(p)
    return p


def presets_left():
    return glob.glob(os.path.join(tempfile.gettempdir(), "passermark-job-*.json"))


def test_done_with_progress():
    before = set(presets_left())
    dst = os.path.join(TMP, "ok.pdf")
    evs = []
    r = jobproc.JobProcess("cutcontour", stickers(), dst, {"shape": "rect", "single_shape": False}).run(evs.append)
    assert r["event"] == "done" and r["returncode"] == 0 and r["info"]["cuts"] == 3, r
    assert any(e["event"] == "progress" for e in evs) and os.path.exists(dst)
    assert set(presets_left()) == before                         # temporäre Einstellungen aufgeräumt


def test_error_reported():
    dst = os.path.join(TMP, "fehler.pdf")
    r = jobproc.JobProcess("separate", stickers(), dst, {"detect": {"min_size_mm": 5000}}).run()
    assert r["event"] == "error" and r["returncode"] == 1 and "Keine Objekte" in r["message"], r
    assert not os.path.exists(dst)
    r = jobproc.JobProcess("cutcontour", os.path.join(TMP, "gibts-nicht.pdf"), dst, {}).run()
    assert r["event"] == "error" and r["returncode"] == 1


def test_pages_option():
    import test_cli as tcl
    src = tcl._slow_input()                                      # 12 Seiten
    dst = os.path.join(TMP, "seiten.pdf")
    r = jobproc.JobProcess("separate", src, dst, {}, pages=[1]).run()
    assert r["event"] == "done" and r["info"]["objects"] == 80, r   # nur Seite 2: 8 × 10 Kreise


def test_cancel_midway():
    import test_cli as tcl
    dst = os.path.join(TMP, "abbruch.pdf")
    job = jobproc.JobProcess("cutcontour", tcl._slow_input(), dst, {})
    job.start()
    first = next(job.events())                                   # er rechnet wirklich
    assert first["event"] == "progress"
    time.sleep(0.3)
    job.cancel()
    r = job.wait(timeout=120)
    assert r["event"] == "cancelled", r
    assert not os.path.exists(dst) and not os.path.exists(dst + ".part")


def test_crash_without_message():
    """Prozess stirbt ohne Abschlussmeldung (z. B. Absturz in einer Bibliothek) -> Fehler mit Code, kein Hängen."""
    orig = jobproc.cli_command
    jobproc.cli_command = lambda: ([sys.executable, "-c",
                                    "import sys, os; sys.stderr.write('Speicherzugriffsfehler\\n'); os._exit(3)"], {})
    try:
        r = jobproc.JobProcess("cutcontour", stickers(), os.path.join(TMP, "crash.pdf"), {}).run()
    finally:
        jobproc.cli_command = orig
    assert r["event"] == "error" and r["returncode"] == 3 and "Code 3" in r["message"], r
    assert "Speicherzugriffsfehler" in r.get("details", "")


def test_noise_and_parallel_jobs():
    """Mehrere Aufträge gleichzeitig (eigene Prozesse), jeder mit eigenem Ergebnis."""
    res = {}
    def go(name, shape):
        res[name] = jobproc.JobProcess("cutcontour", stickers(), os.path.join(TMP, f"{name}.pdf"),
                                       {"shape": shape}).run()
    ts = [threading.Thread(target=go, args=(n, s)) for n, s in (("p1", "rect"), ("p2", "circle"), ("p3", "contour"))]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert all(r["event"] == "done" for r in res.values()), res
    assert all(len(pdfium.PdfDocument(os.path.join(TMP, f"{n}.pdf"))) == 1 for n in res)


def test_unknown_job():
    try:
        jobproc.JobProcess("gibts_nicht", "a", "b")
        assert False
    except ValueError:
        pass


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("ok", k)
