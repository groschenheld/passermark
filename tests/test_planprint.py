# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Plan printing: detect two outer lines (the outer one disappears), content + 5 mm, roll choice (shortest length,
rotation allowed), run length single/total, order (uncollated, collated, by roll), print page with
bleed/marks, hairlines, printing to an imitated plotter, log with run lengths,
command line and workflow step "plan".
"""

import csv
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ.setdefault("PASSERMARK_LANG", "de")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pm-plan-cfg-")
import pypdfium2 as pdfium

from pdfdruck import planprint as pp
from pdfdruck import printers, rolls
from pdfdruck.printers import Choice, Option, PrinterCaps, PrinterInfo

TMP = tempfile.mkdtemp(prefix="pm-plan-")
MM = 72 / 25.4
R = [rolls.Roll(594, name="Rolle 1"), rolls.Roll(841, name="Rolle 2"), rolls.Roll(914, name="Rolle 3")]


def plan_pdf(name, W, H, frames=2, outer=10, gaps=(20, 5, 5, 5), thin=False, pages=1):
    from reportlab.pdfgen import canvas

    p = os.path.join(TMP, name)
    c = canvas.Canvas(p, pagesize=(W * MM, H * MM))
    for _ in range(pages):
        if frames >= 1:
            c.setLineWidth(0.13 * MM)
            c.rect(outer * MM, outer * MM, (W - 2 * outer) * MM, (H - 2 * outer) * MM)
        left, b, r, t = gaps
        if frames >= 2:
            c.setLineWidth(0.5 * MM)
            c.rect((outer + left) * MM, (outer + b) * MM, (W - 2 * outer - left - r) * MM, (H - 2 * outer - b - t) * MM)
        c.setLineWidth((0.05 if thin else 0.3) * MM)
        for i in range(10):
            c.line((outer + 40) * MM, (outer + 40 + i * 8) * MM, (W / 2) * MM, (outer + 60 + i * 8) * MM)
        c.setLineWidth(0.35 * MM)
        c.rect((W - outer - 185) * MM, (outer + 5) * MM, 180 * MM, 60 * MM)
        c.showPage()
    c.save()
    return p


def near(a, b, tol=0.4):
    return abs(a - b) <= tol


def test_detect_frame_margin_page():
    d = pdfium.PdfDocument(plan_pdf("f2.pdf", 620, 870))
    a = pp.detect(d, 0)
    x0, y0, x1, y1 = (v / MM for v in a.rect)
    assert a.kind == "frame", a
    # the outer line (0.13 mm at 10 mm) lies outside: edge just inside the line
    assert 10.05 < x0 < 10.4 and 10.05 < y0 < 10.4 and 609.6 < x1 < 609.95 and 859.6 < y1 < 859.95, (x0, y0, x1, y1)
    d1 = pdfium.PdfDocument(plan_pdf("f1.pdf", 620, 870, frames=1))
    a1 = pp.detect(d1, 0)
    assert a1.kind == "margin" and near(a1.rect[0] / MM, 10 - 5, 0.8) and near(a1.w_mm, 600 + 10, 1.5)
    a1f = pp.detect(d1, 0, "frame")
    assert a1f.kind == "margin" and a1f.note  # explicitly a frame, but only one is there
    am = pp.detect(d, 0, "margin", 3)
    assert am.kind == "margin" and near(am.w_mm, 606, 1.5)
    an = pp.detect(d, 0, "none")
    assert an.kind == "page" and near(an.w_mm, 620, 0.01)
    from reportlab.pdfgen import canvas

    p = os.path.join(TMP, "leer.pdf")
    c = canvas.Canvas(p, pagesize=(200, 300))
    c.showPage()
    c.save()
    assert pp.detect(pdfium.PdfDocument(p), 0).kind == "empty"


def test_rotated_page():
    import pikepdf

    src = plan_pdf("rot.pdf", 420, 297)
    pdf = pikepdf.open(src)
    pdf.pages[0].Rotate = 90
    out = os.path.join(TMP, "rot90.pdf")
    pdf.save(out)
    d = pdfium.PdfDocument(out)
    a = pp.detect(d, 0)
    assert a.kind == "frame" and near(a.w_mm, 277 - 0.3, 0.5) and near(a.h_mm, 400 - 0.3, 0.5), a


def test_choose_roll():
    # A1 portrait 594 × 841: sideways on 841 (length 594) instead of upright on 594 (length 841)
    f = pp.choose(594, 841, R)
    assert f.width_mm == 841 and f.along == 594 and f.rotated
    # A1 supplied in landscape: without rotation on 841
    f = pp.choose(841, 594, R)
    assert f.width_mm == 841 and not f.rotated and f.along == 594
    # as supplied: no rotation
    f = pp.choose(594, 841, R, "keep")
    assert f.width_mm == 594 and f.along == 841 and not f.rotated
    # short side across
    f = pp.choose(841, 594, R, "short")
    assert f.width_mm == 594 and f.along == 841 and f.rotated
    # same length -> narrower roll (A2 landscape: 594 wide on 594 or 841)
    f = pp.choose(594, 420, R)
    assert f.width_mm == 594 and f.along == 420
    # fits nowhere
    assert pp.choose(1000, 1200, R) is None
    # an empty roll is skipped
    e = [rolls.Roll(594, empty=True), rolls.Roll(914)]
    assert pp.choose(594, 841, e).width_mm == 914
    # plan paper: only rolls with 75/80 g (unknown grammage counts too)
    w = [rolls.Roll(594, weight=80), rolls.Roll(841, weight=180), rolls.Roll(914)]
    ok, note = pp.eligible(w, [75, 80])
    assert [r.width_mm for r in ok] == [594, 914] and not note
    ok, note = pp.eligible([rolls.Roll(841, weight=180)], [75, 80])
    assert len(ok) == 1 and note


def test_least_paper_and_edge_tolerance():
    """1.20.2 Nachtrag (Plandruck am Epson): rolls 914 and 592.9 mm as reported by the device."""
    rr = [rolls.Roll(913.9, name="914"), rolls.Roll(592.9, name="594")]
    # A1 with frame lines 593.5 mm: 0.6 mm wider than the narrow roll – on it, edge trimmed (not 914 + 32 cm white)
    f = pp.choose(593.5, 593.5, rr, "auto", pp.EDGE_TOL_MM)
    assert f.width_mm == 592.9
    assert pp.choose(593.5, 593.5, rr, "auto", 0.0).width_mm == 913.9  # without tolerance as before
    # A2 landscape: least paper (594 × 420) instead of the shortest length on 914
    f = pp.choose(594.1, 420.2, rr, "auto", pp.EDGE_TOL_MM)
    assert f.width_mm == 592.9 and not f.rotated and abs(f.along - 420.2) < 0.1
    # trimmed piece: exactly the roll width, half of the excess cut off on each side
    doc = pdfium.PdfDocument(plan_pdf("a1", 593.5, 593.5, frames=0))
    s = pp.PlanSettings(frame="none")
    items = pp.analyze(doc, [0], s, rr)
    (pc,) = pp.pieces_for(items[0], rr, s)
    assert pc.width_mm == 592.9 and abs(pc.across - 592.9) < 0.01 and abs(pc.trimmed - 0.6) < 0.05
    cut = (items[0].area.rect[2] - items[0].area.rect[0]) - (pc.rect[2] - pc.rect[0])
    assert abs(cut / pp.MM - 0.6) < 0.05
    run = pp.build_runs(items, rr, s)[0]
    out, _ = pp.make_run(run, s)
    assert abs(out.get_page_size(0)[0] / pp.MM - 592.9) < 0.1


def test_media_vendor_words_do_not_match():
    """Roll "com.epson-usersetting" (IPP): no arbitrary EPSON media of the Windows driver (grey turned violet)."""
    caps = PrinterCaps(name="Epson", backend="win")
    caps.options["MediaType"] = Option(
        "MediaType",
        "Medientyp",
        "g",
        [Choice("1", "Plain Paper"), Choice("280", "EPSON Premium Glossy Photo Paper (250)")],
        "1",
    )
    caps.roles["mediatype"] = "MediaType"
    assert pp.media_for_roll(caps, rolls.Roll(913.9, media="com.epson-usersetting")) == ""
    assert pp.media_for_roll(caps, rolls.Roll(913.9, media="Premium Glossy")) == "280"


def test_margin_never_beyond_page():
    """Content + margin is limited to the page (verlegeplan: content up to the edge -> page, not +10 mm)."""
    path = plan_pdf("edge", 841, 594, frames=1, outer=0)
    doc = pdfium.PdfDocument(path)
    a = pp.detect(doc, 0, "margin", 5.0)
    W, H = doc.get_page_size(0)
    assert a.rect[0] >= 0 and a.rect[1] >= 0 and a.rect[2] <= W + 0.01 and a.rect[3] <= H + 0.01


def test_lengths_and_order():
    items = []
    for k, (w, h, q) in enumerate(((594, 841, 1), (420, 594, 2), (900, 1200, 1), (297, 420, 1))):
        it = pp.Item(k, q, pp.Area((0, 0, w * MM, h * MM), "frame"), source=f"plan{k + 1}.pdf")
        items.append(it)
    pp.place(items, R, pp.PlanSettings())
    assert [it.fit.width_mm for it in items] == [841, 594, 914, 594]
    lens = pp.run_lengths(items, R, 2)
    by = {d["width_mm"]: d for d in lens}
    assert near(by[594]["single_m"], (420 * 2 + 297) / 1000, 0.001) and by[594]["plans"] == 3
    assert near(by[594]["total_m"], 2 * (420 * 2 + 297) / 1000, 0.001)
    assert near(by[841]["single_m"], 0.594, 0.001) and near(by[914]["single_m"], 1.2, 0.001)
    # uncollated (default): every plan with all copies in a row
    order = pp.job_order(items, 3, False, "list")
    assert [(it.page, n) for it, n in order] == [(0, 3), (1, 6), (2, 3), (3, 3)]
    # collated: set by set
    order = pp.job_order(items, 2, True, "list")
    assert [(it.page, n) for it, n in order] == [(0, 1), (1, 2), (2, 1), (3, 1)] * 2
    # by roll width: 594 first (in list order), then 841, then 914
    order = pp.job_order(items, 1, False, "roll")
    assert [it.page for it, _n in order] == [1, 3, 0, 2]
    # the remaining length is not enough
    short = [rolls.Roll(594, remaining_m=0.5), rolls.Roll(841), rolls.Roll(914)]
    pp.place(items, short, pp.PlanSettings())
    assert pp.run_lengths(items, short, 2)[0]["short"]


def test_make_page_rotated_bleed_marks():
    d = pdfium.PdfDocument(plan_pdf("mk.pdf", 620, 870))
    a = pp.detect(d, 0)
    for mode in pp.BLEED_MODES:
        s = pp.PlanSettings(bleed_mm=3, bleed_mode=mode, bleed_color="#ff0000", crop_marks=True)
        w, h = pp.finished_size(a, s)
        f = pp.choose(w, h, R, s.rotate)
        assert f.rotated and f.width_mm == 914
        out = pp.make_page(d, 0, a, f, s)
        pw, ph = (v / MM for v in out.get_page_size(0))
        assert near(pw, f.across, 0.1) and near(ph, f.along, 0.1), (pw, ph, f)
        img = out[0].render(scale=0.2).to_pil().convert("RGB")
        px = img.getpixel((int(img.width / 2), int(pp.extra_mm(s) * MM * 0.2 - 3 * MM * 0.2 / 2)))
        if mode == "color":
            assert px[0] > 200 and px[1] < 80, px  # red bleed
        out.close()
    # without additions: exactly the print area, unrotated on 841 if landscape
    s = pp.PlanSettings(rotate="keep")
    f = pp.choose(a.w_mm, a.h_mm, R + [rolls.Roll(1067)], "keep")
    out = pp.make_page(d, 0, a, f, s)
    assert near(out.get_page_size(0)[0] / MM, a.w_mm, 0.05)
    # the outer line is gone: edge of the print page white, the inner frame stays black
    img = out[0].render(scale=2, grayscale=True).to_pil()
    W_, H_ = img.size
    assert min(img.getpixel((x, H_ // 2)) for x in range(0, 6)) > 240
    assert min(img.getpixel((x, H_ // 2)) for x in range(int(20 * MM * 2) - 6, int(20 * MM * 2) + 6)) < 80


def test_hairlines_count_and_fix():
    d = pdfium.PdfDocument(plan_pdf("thin.pdf", 420, 297, thin=True))
    n = pp.hairlines(d, 0)
    assert n == 10, n
    assert pp.hairlines(d, 0, scale_pct=250) == 0  # enlarged it is enough
    fixed, k = pp.fix_hairlines(d, [0])
    assert k == 10 and pp.hairlines(fixed, 0) == 0
    from pdfdruck import preflight

    rep = preflight.analyze(open(os.path.join(TMP, "thin.pdf"), "rb").read())
    hi = [i for i in rep.issues if i.category == "line"]
    assert hi and hi[0].severity == "warning" and any(sp.box for sp in hi[0].spots)


def plotter_caps(name="Plotter"):
    def opt(k, text, choices, default):
        return Option(k, text, "", [Choice(v, t) for v, t in choices], default)

    caps = PrinterCaps(name, "ppd")
    caps.options = {
        "PageSize": opt("PageSize", "Papierformat", [("A1", "A1"), ("A0", "A0")], "A1"),
        "InputSlot": opt(
            "InputSlot",
            "Papierzufuhr",
            [("Auto", "Automatisch"), ("Roll1", "Rolle 1"), ("Roll2", "Rolle 2"), ("Roll3", "Rolle 3")],
            "Auto",
        ),
        "MediaType": opt("MediaType", "Medientyp", [("Plain", "Normalpapier 80 g"), ("Photo", "Fotopapier")], "Plain"),
        "ColorModel": opt("ColorModel", "Farbmodus", [("CMYK", "Farbe"), ("Gray", "Graustufen")], "CMYK"),
    }
    caps.page_sizes = {"A1": (594 * MM, 841 * MM), "A0": (841 * MM, 1189 * MM)}
    printers._assign_roles(caps)
    return caps


class FakePlotter:
    def __enter__(self):
        self.sent = []
        self.saved = (printers.list_printers, printers.load_caps, printers.submit)
        printers.list_printers = lambda: [PrinterInfo("Plotter", "Plotter", "", "ColorWave", 3, "", True)]
        printers.load_caps = lambda name: plotter_caps(name)

        def submit(printer, path, title, opts):
            d = pdfium.PdfDocument(path)
            self.sent.append({"title": title, "opts": dict(opts), "size": tuple(v / MM for v in d.get_page_size(0))})
            d.close()
            return 100 + len(self.sent)

        printers.submit = submit
        return self

    def __exit__(self, *a):
        printers.list_printers, printers.load_caps, printers.submit = self.saved


def test_print_jobs_and_log():
    from pdfdruck import config, printlog
    from pdfdruck.session import Session

    logdir = os.path.join(TMP, "log")
    rolls.save_manual(
        "Plotter",
        [
            rolls.Roll(594, "Roll1", "Rolle 1", 80),
            rolls.Roll(841, "Roll2", "Rolle 2", 80),
            rolls.Roll(914, "Roll3", "Rolle 3", 80),
        ],
    )
    src = plan_pdf("job.pdf", 620, 870, pages=2)
    with FakePlotter() as fp:
        sess = Session(dict(config.BUILTIN, print_log={"force": True, "dir": logdir}))
        s = pp.PlanSettings(printer="Plotter", copies=3, color="gray", live_rolls=False, copies_mode="count")
        info = pp.plan_files([src], s, session=sess)
    assert len(fp.sent) == 2, fp.sent  # count to the device: one job per plan, 3 copies
    o = fp.sent[0]["opts"]
    assert o["copies"] == "3" and o["InputSlot"] == "Roll3" and o["ColorModel"] == "Gray"
    assert o["PageSize"].startswith("Custom.") and o["print-scaling"] == "none"
    w, h = fp.sent[0]["size"]
    assert near(w, 914, 0.5) and near(h, 599.7, 0.5)  # rotated, print page at roll width (cut per page)
    assert near(info["lengths"][0]["single_m"], 1.199, 0.003) and near(info["total_m"], 3.598, 0.01)
    # log: run length per job, CSV columns, reprint workflow with step "plan"
    with open(os.path.join(logdir, printlog.CSV_NAME), encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    assert len(rows) == 2 and rows[0]["roll_mm"] == "914" and abs(float(rows[0]["run_m"]) - 1.799) < 0.01
    logs = sorted(os.path.join(dp, x) for dp, _d, fs in os.walk(logdir) for x in fs if x.endswith(".json"))
    rec = json.load(open(logs[0], encoding="utf-8"))
    st = rec["workflow"]["steps"][-1]
    assert st["job"] == "plan" and st["settings"]["copies"] == 3 and st["settings"]["rolls"][0]["width_mm"] == 914
    # collated: set by set -> 6 jobs of 1 each
    with FakePlotter() as fp:
        sess = Session(config.BUILTIN)
        pp.plan_files([src], pp.PlanSettings(printer="Plotter", copies=3, collate=True, live_rolls=False), session=sess)
    assert len(fp.sent) == 6 and all(x["opts"]["copies"] == "1" for x in fp.sent)
    # default: one job per plan, one sheet per copy (copies = 1)
    with FakePlotter() as fp:
        pp.plan_files(
            [src], pp.PlanSettings(printer="Plotter", copies=3, live_rolls=False), session=Session(config.BUILTIN)
        )
    assert len(fp.sent) == 2 and all(x["opts"]["copies"] == "1" for x in fp.sent)


def test_csv_upgrade():
    from pdfdruck import printlog

    d = os.path.join(TMP, "oldlog")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, printlog.CSV_NAME)
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        f.write("time;user;host;source;file;pages;printer;paper;tray;copies;job_id;result;log\r\nx;y\r\n")
    printlog._upgrade_csv(p)
    head = open(p, encoding="utf-8-sig").readline()
    assert head.strip().endswith(";roll_mm;run_m;order;item"), head  # order reference


def _cli(*args):
    env = dict(os.environ, PYTHONPATH=ROOT)
    return subprocess.run(
        [sys.executable, "-m", "pdfdruck.cli", *args], capture_output=True, text=True, env=env, cwd=TMP
    )


def test_cli_plan_dry_run_and_workflow():
    src = plan_pdf("cli.pdf", 620, 870, pages=2)
    r = _cli("plan", src, "--rolls", "594,841,914", "--copies", "2", "--dry-run", "--json")
    assert r.returncode == 0, r.stderr
    ev = [json.loads(x) for x in r.stdout.splitlines() if x.strip()]
    done = ev[-1]
    assert done["event"] == "done" and done["dry_run"] and len(done["jobs"]) == 2
    assert done["lengths"][0]["width_mm"] == 914 and abs(done["total_m"] - 2.399) < 0.01
    r = _cli("plan", src, "--rolls", "594,841,914", "--dry-run")
    assert r.returncode == 0 and "914 mm:" in r.stdout and "gedreht" in r.stdout, r.stdout + r.stderr
    wf = {
        "passermark": "workflow",
        "version": 1,
        "input": src,
        "steps": [{"job": "plan", "settings": {"rolls": [594, 841, 914], "dry_run": True, "copies": 2}}],
    }
    p = os.path.join(TMP, "plan.json")
    json.dump(wf, open(p, "w"))
    r = _cli("check", p)
    assert r.returncode == 0, r.stderr
    r = _cli("run", p)
    assert r.returncode == 0 and "914 mm:" in r.stdout, r.stdout + r.stderr
    r = _cli("schema", "plan", "--json")
    assert r.returncode == 0 and "bleed_mode" in r.stdout


def test_media_of_loaded_roll():
    """The device reports the roll's media: exactly that is requested – even if the material (import, by hand)
    names another media type. Otherwise e.g. the ColorWave waits for a media that is not loaded.
    """
    from pdfdruck import config, printmat
    from pdfdruck.session import Session

    printmat.save(
        [
            {
                "id": "poster180",
                "name": "Poster 180",
                "category": "quality",
                "weight": 180,
                "media": "Photo",
                "printer": "Plotter",
            }
        ]
    )
    rolls.save_manual("Plotter", [rolls.Roll(914, "Roll3", "Rolle 3", 180, media="Normalpapier")])
    src = plan_pdf("media.pdf", 420, 594)
    with FakePlotter() as fp:
        pp.plan_files(
            [src],
            pp.PlanSettings(kind="poster", printer="Plotter", live_rolls=False, material="poster180"),
            session=Session(config.BUILTIN),
        )
    assert fp.sent and all(x["opts"]["MediaType"] == "Plain" for x in fp.sent), [x["opts"] for x in fp.sent]
    # the device reports a media that matches no media type of the driver: request nothing specific
    rolls.save_manual("Plotter", [rolls.Roll(914, "Roll3", "Rolle 3", 180, media="IJM 123 Matt Coated")])
    with FakePlotter() as fp:
        info = pp.plan_files(
            [src],
            pp.PlanSettings(kind="poster", printer="Plotter", live_rolls=False, material="poster180", dry_run=True),
            session=Session(config.BUILTIN),
        )
        pp.plan_files(
            [src],
            pp.PlanSettings(kind="poster", printer="Plotter", live_rolls=False, material="poster180"),
            session=Session(config.BUILTIN),
        )
    assert all(x["opts"]["MediaType"] == "Plain" for x in fp.sent), [
        x["opts"] for x in fp.sent
    ]  # default instead of Photo
    j = info["jobs"][0]  # the dry run shows what would go to the device
    assert j["options"]["MediaType"] == "Plain" and j["roll_media"] == "IJM 123 Matt Coated", j
    rolls.save_manual("Plotter", [rolls.Roll(914, "Roll3", "Rolle 3", 180)])  # media unknown: the material counts
    with FakePlotter() as fp:
        pp.plan_files(
            [src],
            pp.PlanSettings(kind="poster", printer="Plotter", live_rolls=False, material="poster180"),
            session=Session(config.BUILTIN),
        )
    assert all(x["opts"]["MediaType"] == "Photo" for x in fp.sent), [x["opts"] for x in fp.sent]
    printmat.save([])


def test_history():
    """History: the file is saved along (the original may be gone), newest first, at most MAX_ENTRIES, clean-up."""
    import shutil

    from pdfdruck import planhistory

    planhistory.clear()
    src = plan_pdf("hist.pdf", 420, 594)
    tmp = os.path.join(TMP, "hist_copy.pdf")
    shutil.copy(src, tmp)
    e = planhistory.add(
        "poster",
        "Plotter",
        {"copies": 3},
        [{"source": tmp, "page": 0, "qty": 2, "ov": {"align": "left"}, "own": True}],
        1.26,
        1,
    )
    os.remove(tmp)  # original gone: the saved copy counts
    p = planhistory.file_of(e, e["items"][0])
    assert p and os.path.isfile(p) and p.startswith(planhistory.history_dir())
    assert "hist_copy.pdf" in planhistory.label(e) and "Plotter" in planhistory.label(e)
    assert planhistory.entries("poster")[0]["id"] == e["id"] and planhistory.entries("plan") == []
    old = planhistory.MAX_ENTRIES
    planhistory.MAX_ENTRIES = 3
    try:
        for _ in range(4):
            planhistory.add("plan", "Plotter", {}, [], 0, 0)
        assert len(planhistory.entries()) == 3
    finally:
        planhistory.MAX_ENTRIES = old
    assert planhistory.clear() == 3 and planhistory.entries() == []


def test_quality_mode():
    """Plan = production print (lowest driver quality), poster = quality print (highest); switchable;
    a material of the same category with its own quality and options set by hand take precedence.
    """
    from pdfdruck import config, printmat
    from pdfdruck.session import Session

    q = lambda k, ch, d="": Option(k, "Druckqualität", "", [Choice(v, t) for v, t in ch], d)  # noqa: E731
    cq = q("cupsPrintQuality", [("Normal", "Normal"), ("Draft", "Entwurf"), ("High", "Hoch")], "Normal")
    assert printers.quality_choice(cq, "production") == "Draft" and printers.quality_choice(cq, "quality") == "High"
    ipp = q("print-quality", [("3", "Entwurf"), ("4", "Normal"), ("5", "Hoch")], "4")
    assert printers.quality_choice(ipp, "production") == "3" and printers.quality_choice(ipp, "quality") == "5"
    res = q("Resolution", [("600x600dpi", "600 dpi"), ("1200x1200dpi", "1200 dpi"), ("300x300dpi", "300 dpi")])
    assert printers.quality_choice(res, "production") == "300x300dpi"
    assert printers.quality_choice(res, "quality") == "1200x1200dpi"
    ep = q(
        "EPIJ_Qual",
        [("PLAIN_DRAFT", "Entwurf"), ("PLAIN_HIGH", "Fein"), ("PHOTO_HIGH", "Foto fein"), ("PHOTO_NORMAL", "Foto")],
        "PLAIN_DRAFT",
    )
    assert printers.quality_choice(ep, "quality", "PLAIN_DRAFT") == "PLAIN_HIGH"  # stay with the media
    assert printers.quality_choice(q("X", [("A", "Modus A"), ("B", "Modus B")]), "quality") == ""  # unclear: nothing
    caps = plotter_caps()
    caps.options["CNQualityMode"] = Option(
        "CNQualityMode",
        "Druckqualität",
        "",
        [Choice("Std", "Standard"), Choice("Fast", "Schnell"), Choice("Best", "Beste Qualität")],
        "Std",
    )
    printers._assign_roles(caps)  # recognised via the text "Druckqualität"
    assert caps.roles.get("quality") == "CNQualityMode"
    # 1.20.2: Passermark leaves the driver's quality alone unless asked
    assert pp.quality_mode_of(pp.PlanSettings()) == "driver"
    assert pp.quality_mode_of(pp.PlanSettings(kind="poster")) == "driver"
    assert pp.quality_mode_of(pp.PlanSettings(kind="poster", quality_mode="production")) == "production"
    assert pp.defaults_for("poster")["quality_mode"] == "driver" and pp.defaults_for("plan")["quality_mode"] == "driver"
    assert pp.apply_quality_mode(caps, {}, pp.PlanSettings()) == {}
    v = pp.apply_quality_mode(caps, {}, pp.PlanSettings(kind="poster", quality_mode="quality"))
    assert v == {"CNQualityMode": "Best"}
    assert pp.apply_quality_mode(caps, {}, pp.PlanSettings(kind="poster", options={"CNQualityMode": "Std"})) == {}
    prod = pp.PlanSettings(quality_mode="production")
    assert pp.apply_quality_mode(caps, {}, prod, {"category": "plan", "quality": "Std"}) == {}
    assert pp.apply_quality_mode(caps, {}, prod, {"category": "quality", "quality": "Best"}) == {
        "CNQualityMode": "Fast"
    }  # quality material in production print
    # end to end: what really goes to the printer
    printmat.save([])
    rolls.save_manual("Plotter", [rolls.Roll(914, "Roll3", "Rolle 3", 80)])
    src = plan_pdf("qmode.pdf", 420, 594)
    with FakePlotter() as fp:
        printers.load_caps = lambda name: caps
        for kind, mode, want in (
            ("plan", "", "Std"),  # as in the driver: its default stays
            ("poster", "", "Std"),
            ("plan", "production", "Fast"),
            ("poster", "quality", "Best"),
            ("poster", "production", "Fast"),
            ("plan", "quality", "Best"),
        ):
            fp.sent.clear()
            pp.plan_files(
                [src],
                pp.PlanSettings(kind=kind, quality_mode=mode, printer="Plotter", live_rolls=False),
                session=Session(config.BUILTIN),
            )
            assert fp.sent and all(x["opts"].get("CNQualityMode") == want for x in fp.sent), (kind, mode, fp.sent)


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
