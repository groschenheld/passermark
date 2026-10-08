# SPDX-License-Identifier: GPL-3.0-or-later
"""Paralleles Rechnen (CutContour): bitgleich zu seriell, Arbeitsprozesse einmal je Auftrag, Abbrechen ohne Reste."""
import json, multiprocessing, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
os.environ.setdefault("PASSERMARK_LANG", "de")
import numpy as np
import pypdfium2 as pdfium
from pdfdruck import cutcontour, objects


def _same(a, b):
    if len(a.paths) != len(b.paths) or len(a.objects) != len(b.objects):
        return False
    for (pa, sa), (pb, sb) in zip(a.paths, b.paths):
        if sa != sb or not np.array_equal(np.array(pa), np.array(pb)):
            return False
    for oa, ob in zip(a.objects, b.objects):
        for x, y in ((oa.bleed_rgba, ob.bleed_rgba), (oa.overlay_rgba, ob.overlay_rgba)):
            if (x is None) != (y is None) or (x is not None and not np.array_equal(x, y)):
                return False
    ka, kb = a.knockout, b.knockout
    return (ka is None) == (kb is None) and (ka is None or np.array_equal(ka, kb))


def test_parallel_equals_serial():
    import test_cutcontour as tc
    old = cutcontour.PARALLEL_MIN_OBJECTS, cutcontour.PARALLEL_MIN_PIXELS
    cutcontour.PARALLEL_MIN_OBJECTS, cutcontour.PARALLEL_MIN_PIXELS = 2, 0     # auch den kleinen Bogen parallel
    try:
        for kw in (dict(shape="contour", bleed_mm=2, inner=True, clean_seams=True),
                   dict(shape="rect", single_shape=False, bleed_mm=2), dict(shape="contour", bleed=False)):
            pg = objects.normalized(tc.stickers())[0]
            ser = cutcontour.compute(pg, cutcontour.CutSettings(**kw), workers=1)
            par = cutcontour.compute(pg, cutcontour.CutSettings(**kw), workers=2)
            assert _same(ser, par), kw
    finally:
        cutcontour.PARALLEL_MIN_OBJECTS, cutcontour.PARALLEL_MIN_PIXELS = old


def test_multipage_one_pool_same_result():
    import test_cli as tcl
    src = pdfium.PdfDocument(tcl._slow_input())
    two = pdfium.PdfDocument.new()
    two.import_pages(src, [0, 1])
    starts = []
    orig = cutcontour.WorkerPool.get
    def counting_get(self):
        if self._ex is None:
            starts.append(1)
        return orig(self)
    cutcontour.WorkerPool.get = counting_get
    try:
        par, n_par = cutcontour.make(two, cutcontour.CutSettings(), workers=2)
    finally:
        cutcontour.WorkerPool.get = orig
    ser, n_ser = cutcontour.make(two, cutcontour.CutSettings(), workers=1)
    assert len(starts) == 1, starts                         # einmal gestartet, für beide Seiten verwendet
    assert n_par == n_ser == 160 and len(par) == len(ser) == 2
    for i in range(2):
        a = np.asarray(par[i].render(scale=0.5).to_pil())
        b = np.asarray(ser[i].render(scale=0.5).to_pil())
        assert np.array_equal(a, b), i


def test_pages_parallel_equals_serial():
    """Mehrere Seiten gleichzeitig (jeder Arbeitsprozess eine ganze Seite) – bitgleich zu seriell, Seite für Seite."""
    import test_cli as tcl
    norm = objects.normalized(pdfium.PdfDocument(tcl._slow_input()))
    s = cutcontour.CutSettings(clean_seams=True)
    todo = [0, 3, 5]
    msgs = []
    pool = cutcontour.WorkerPool(2)
    try:
        par, tp = cutcontour._make_pages_parallel(norm, s, todo, lambda d, t, txt: msgs.append(txt), None, pool, 2)
    finally:
        pool.close()
    ser, ts = cutcontour._make_pages(norm, s, todo, None, None, None)
    assert tp == ts == 240 and sorted(par) == sorted(ser) == todo
    for i in todo:
        assert _same(par[i], ser[i]), i
    assert any("Seiten fertig" in m for m in msgs), msgs


def test_cancel_leaves_no_workers():
    import test_cli as tcl
    from pdfdruck import core
    calls = []
    def cancel():
        calls.append(1)
        return len(calls) > 3                                # mitten in der Berechnung abbrechen
    try:
        cutcontour.make(pdfium.PdfDocument(tcl._slow_input()), cutcontour.CutSettings(), pages=[0, 1, 2],
                        cancel=cancel, workers=2)
        assert False, "kein Abbruch"
    except core.Cancelled:
        pass
    assert not multiprocessing.active_children(), multiprocessing.active_children()
    # Seiten-Modus (mehrere Seiten gleichzeitig): Abbruch ebenfalls ohne übrige Arbeitsprozesse
    calls.clear()
    try:
        cutcontour.make(pdfium.PdfDocument(tcl._slow_input()), cutcontour.CutSettings(), pages=[0, 1, 2, 3],
                        cancel=cancel, workers=2)
        assert False, "kein Abbruch"
    except core.Cancelled:
        pass
    assert not multiprocessing.active_children(), multiprocessing.active_children()


def test_cli_parallel_with_object_progress():
    import test_cli as tcl
    out = os.path.join(tempfile.mkdtemp(), "p.pdf")
    env = dict(os.environ, PYTHONPATH=ROOT, PASSERMARK_LANG="de", PASSERMARK_WORKERS="2")
    r = subprocess.run([sys.executable, "-m", "pdfdruck.cli", "cutcontour", tcl._slow_input(), out, "--pages", "1",
                        "--json-progress"], capture_output=True, text=True, env=env, timeout=600)
    evs = [json.loads(l) for l in r.stdout.splitlines() if l.strip()]
    assert r.returncode == 0 and evs[-1]["event"] == "done" and evs[-1]["info"]["cuts"] == 80, r.stderr[-2000:]
    assert any("Objekt" in e.get("text", "") for e in evs), [e.get("text") for e in evs][:5]


def test_workers_setting():
    os.environ["PASSERMARK_WORKERS"] = "3"
    try:
        assert cutcontour.default_workers() == 3
    finally:
        del os.environ["PASSERMARK_WORKERS"]
    assert 1 <= cutcontour.default_workers() <= 8


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("ok", k)
