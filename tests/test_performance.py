# SPDX-License-Identifier: GPL-3.0-or-later
"""Zeitbudgets: schlägt an, wenn eine Änderung etwas spürbar langsamer macht.

Die Rechner im GitHub-Build sind unterschiedlich schnell. Deshalb wird zuerst eine feste Eichaufgabe gemessen und jedes
Budget als Vielfaches davon angegeben („Eichfaktor“). Je Messung der beste von mehreren Läufen.
  über WARN × Bezug  -> Warnung (Build gelb, läuft weiter)
  über FAIL × Bezug  -> Fehler (Build rot)
Bezugswerte neu bestimmen: python3 tests/test_performance.py --messen
"""
import io, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
os.environ.setdefault("PASSERMARK_LANG", "de")
import numpy as np

WARN, FAIL = 1.6, 3.0
# Bezug = gemessene Zeit / Eichzeit, gespeichert in tests/perf_baseline.json
BASELINE = {}
BASELINE_FILE = os.path.join(HERE, "perf_baseline.json")
if os.path.exists(BASELINE_FILE):
    BASELINE.update(json.load(open(BASELINE_FILE, encoding="utf-8")))


def calibrate() -> float:
    from scipy import ndimage as ndi
    rng = np.random.default_rng(7)
    a = rng.random((1400, 1400)) > 0.6

    def once():
        t = time.perf_counter()
        for _ in range(3):
            ndi.distance_transform_edt(a)
            ndi.gaussian_filter(a.astype(np.float32), 2)
        return time.perf_counter() - t
    return min(once() for _ in range(3))


def best(fn, runs=3, min_time=0.3):
    """Beste Zeit je Aufruf; kurze Aufgaben so oft hintereinander, dass eine Messung ≥ min_time dauert."""
    t = time.perf_counter()
    fn()
    first = time.perf_counter() - t
    reps = max(1, int(min_time / max(first, 1e-4)) + 1) if first < min_time else 1
    out = []
    for _ in range(runs):
        t = time.perf_counter()
        for _ in range(reps):
            fn()
        out.append((time.perf_counter() - t) / reps)
    return min(out)


def judge(res: dict, cal: float, baseline: dict):
    """[(Name, Zeit, Faktor, Bezug, relativ, „ok“|„WARNUNG“|„FEHLER“|„neu“)]"""
    out = []
    for k, t in res.items():
        ratio = t / cal
        ref = baseline.get(k)
        if not ref:
            out.append((k, t, ratio, None, None, "neu"))
            continue
        rel = ratio / ref
        out.append((k, t, ratio, ref, rel, "FEHLER" if rel > FAIL else "WARNUNG" if rel > WARN else "ok"))
    return out


def _poster():
    """A4-Plakat wie im Alltag: fleckiger Papierhintergrund, mehrere Motive (fest, ohne Zufall von außen)."""
    from PIL import Image, ImageDraw, ImageFilter
    import pypdfium2 as pdfium
    import img2pdf
    W, H = 1240, 1754                                      # 150 dpi
    rng = np.random.default_rng(1)
    base = np.zeros((H, W, 3), np.float32); base[:] = (233, 208, 160)
    noise = np.array(Image.fromarray(rng.normal(0, 1, (H // 8, W // 8)).astype(np.float32)).resize((W, H)))
    base += noise[:, :, None] * 14
    img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8)); d = ImageDraw.Draw(img)
    for (x, y, w, h) in ((200, 450, 450, 500), (750, 750, 350, 400), (150, 1100, 600, 350), (850, 1300, 250, 350)):
        d.ellipse((x, y, x + w, y + h), fill=(20, 15, 12)); d.rectangle((x + w // 3, y + h // 3, x + w // 2, y + h // 2), fill=(200, 60, 50))
    for _ in range(25):
        x, y = int(rng.integers(50, W - 50)), int(rng.integers(50, H - 50))
        d.regular_polygon((x, y, 15), 5, fill=(90, 20, 20))
    b = io.BytesIO(); img.filter(ImageFilter.GaussianBlur(0.8)).save(b, "JPEG", quality=90, dpi=(150, 150))
    return pdfium.PdfDocument(img2pdf.convert(b.getvalue()))


def _booklet_src():
    import pypdfium2 as pdfium
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    b = io.BytesIO(); c = canvas.Canvas(b, pagesize=A4)
    for i in range(32):
        c.setFont("Helvetica", 40); c.drawString(100, 700, f"Seite {i + 1}")
        for j in range(60):
            c.line(50 + j * 8, 100, 300 + j * 3, 600)
        c.showPage()
    c.save()
    return pdfium.PdfDocument(b.getvalue())


def measure() -> dict:
    from pdfdruck import cutcontour, layout, objects
    poster = _poster()
    norm = objects.normalized(poster)
    pg = norm[0]
    s_kont = cutcontour.CutSettings(shape="contour", bleed=True, dpi=200)
    s_rect = cutcontour.CutSettings(shape="rect", bleed=True, dpi=200)
    res = {}
    res["cutcontour_kontur_ueberfueller"] = best(lambda: cutcontour.compute(pg, s_kont))
    res["cutcontour_rechteck"] = best(lambda: cutcontour.compute(pg, s_rect))
    res["objekte_erkennen"] = best(lambda: objects.detect(pg, objects.DetectSettings()))
    r = cutcontour.compute(pg, s_kont)
    res["pdf_bauen"] = best(lambda: cutcontour.build_pdf(norm, {0: r}, s_kont))
    src = _booklet_src()
    ls = layout.LayoutSettings(handling="booklet")
    a3 = layout.Sheet(841.89, 1190.55, (12, 12, 829.89, 1178.55))
    out = os.path.join(__import__("tempfile").mkdtemp(), "b.pdf")
    res["broschuere_ausschiessen"] = best(lambda: layout.build_pdf(src, a3, list(range(len(src))), ls, out))
    return res


def test_judge_logic():
    """Entscheidung mit erfundenen Zahlen: gleich schnell ok, 2× gelb, 4× rot, unbekannt neu."""
    base = {"a": 1.0, "b": 1.0, "c": 1.0}
    r = {x[0]: x[5] for x in judge({"a": 0.5, "b": 1.0, "c": 2.0, "d": 1.0}, 0.5, base)}
    assert r == {"a": "ok", "b": "WARNUNG", "c": "FEHLER", "d": "neu"}, r


def test_time_budgets():
    cal = calibrate()
    rows = judge(measure(), cal, BASELINE)
    print(f"Eichung {cal:.3f} s")
    for k, t, ratio, ref, rel, flag in rows:
        if ref is None:
            print(f"  {k:32s} {t:6.3f} s  Faktor {ratio:5.2f}  (kein Bezug)")
        else:
            print(f"  {k:32s} {t:6.3f} s  Faktor {ratio:5.2f}  Bezug {ref:5.2f}  -> {rel:4.2f}×  {flag}")
        if flag == "WARNUNG":
            # GitHub: gelbe Anmerkung am Lauf (Build bleibt grün)
            print(f"::warning title=Zeitbudget::{k} ist {rel:.1f}× langsamer als bisher")
    # gemessene Werte als fertige Zeile – zum Übernehmen in tests/perf_baseline.json, falls der Build-Rechner abweicht
    print("Messwerte (Faktor):", json.dumps({x[0]: round(x[2], 3) for x in rows}))
    fails = [x[0] for x in rows if x[5] == "FEHLER"]
    assert not fails, f"deutlich langsamer (> {FAIL}× Bezug): {fails}"


if __name__ == "__main__":
    if "--messen" in sys.argv:
        cal = calibrate()
        res = {k: round(v / cal, 3) for k, v in measure().items()}
        json.dump(res, open(BASELINE_FILE, "w", encoding="utf-8"), indent=2)
        print("Bezug gespeichert:", json.dumps(res))
    else:
        test_judge_logic(); print("ok test_judge_logic")
        test_time_budgets(); print("ok test_time_budgets")
