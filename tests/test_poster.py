# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Posterdruck (Qualitätsdruck): nebeneinander mit dem wenigsten Papier, Überbreite abschneiden oder in Bahnen,
    Banner mit Saum und Ösenmarken, CutContour für Print & Cut, Faltmarken DIN 824, Ausgabe in einen Hotfolder,
    Druckmaterialien (Medientyp, Qualität, Tintenmenge, Profil), Roland (Breite über OH, Schneidedatei)."""
import json, os, socket, sys, tempfile, threading
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
os.environ.setdefault("PASSERMARK_LANG", "de")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pm-poster-cfg-")
import pikepdf
import pypdfium2 as pdfium
from pdfdruck import planprint as pp, printmat, roland, rolls
import test_planprint as T

MM = 72 / 25.4


def poster(**kw):
    return pp.PlanSettings(**dict(pp.defaults_for("poster"), **kw))


def test_nest_least_paper():
    R = [rolls.Roll(610), rolls.Roll(914)]
    d = pdfium.PdfDocument(T.plan_pdf("a3n.pdf", 297, 420, frames=1))
    s = poster()
    items = pp.analyze(d, [0], s, R, "a3n.pdf", qty=7)
    runs = pp.build_runs(items, R, s, 1)
    # 610: zwei hoch nebeneinander (297 + 5 + 297) braucht am wenigsten Papier
    assert len(runs) == 1 and len(runs[0].pieces) == 7 and runs[0].width_mm == 610
    # keine Überlappung, alles innerhalb der Seite
    boxes = [(x, y, x + p.across, y + p.along) for p, x, y in runs[0].pieces]
    for i, a in enumerate(boxes):
        assert a[0] >= -0.01 and a[1] >= -0.01 and a[2] <= runs[0].across + 0.01 and a[3] <= runs[0].along + 0.01
        for b in boxes[i + 1:]:
            assert a[2] <= b[0] + 0.01 or b[2] <= a[0] + 0.01 or a[3] <= b[1] + 0.01 or b[3] <= a[1] + 0.01
    assert T.near(runs[0].along, 4 * 420 + 3 * 5, 0.5)
    # A2 ×5: 610 gedreht (5 × 420) braucht weniger Papier als 914 mit zwei nebeneinander
    d2 = pdfium.PdfDocument(T.plan_pdf("a2n.pdf", 420, 594, frames=0))
    items = pp.analyze(d2, [0], s, R, "a2n.pdf", qty=5)
    runs = pp.build_runs(items, R, s, 1)
    assert runs[0].width_mm == 610 and len(runs[0].pieces) == 5
    lens = pp.lengths(items, R, poster(copies=2))
    assert lens[0]["width_mm"] == 610 and T.near(lens[0]["total_m"], (10 * 420 + 9 * 5) / 1000, 0.01)
    # ohne Nebeneinander (Plandruck): ein Stück je Seite
    runs = pp.build_runs(items, R, pp.PlanSettings(weights=[]), 1)
    assert len(runs) == 1 and runs[0].copies == 5


def test_overwidth_crop_and_tile():
    R = [rolls.Roll(914), rolls.Roll(1067)]
    d = pdfium.PdfDocument(T.plan_pdf("wide.pdf", 1500, 1200, frames=0))
    s = poster(rotate="keep")
    it = pp.analyze(d, [0], s, R, "wide.pdf")[0]
    assert it.fit is None
    ps = pp.pieces_for(it, R, s)
    assert len(ps) == 1 and ps[0].clipped and ps[0].width_mm == 1067 and T.near(ps[0].across, 1067, 0.01)
    st = poster(rotate="keep", overwidth="tile", overlap_mm=20)
    ps = pp.pieces_for(it, R, st)
    assert len(ps) == 2 and all(p.width_mm == 914 for p in ps)
    assert T.near(ps[0].across + ps[1].across - 20, 1500, 0.1)
    assert T.near((ps[1].rect[0] - ps[0].rect[0]) / MM, ps[0].across - 20, 0.1)
    assert pp.pieces_for(it, R, poster(rotate="keep", overwidth="none")) == []
    info = pp.summary("", [it], R, st)
    assert info["tiled"] == [it.label] and not info["unfit"]
    out = os.path.join(T.TMP, "tiles.pdf")
    assert pp.save_pdf([it], R, st, out) == 1                  # nebeneinander: beide Bahnen auf einer Seite
    import dataclasses
    assert pp.save_pdf([it], R, dataclasses.replace(st, nest=False), out) == 2


def test_banner_hem_grommets_cut():
    R = [rolls.Roll(1370)]
    d = pdfium.PdfDocument(T.plan_pdf("ban.pdf", 1000, 500, frames=0))
    s = poster(hem_mm=30, hem_sides="lr", grommet_spacing_mm=300, grommet_inset_mm=20, cut_contour=True,
               bleed_mm=5)
    it = pp.analyze(d, [0], s, R, "ban.pdf")[0]
    assert T.near(it.size[0], 1000 + 60, 0.5) and T.near(it.size[1], 500 + 10, 0.5)      # Saum statt Überfüller
    pts = pp.grommet_points(1000, 500, 20, 300, "lrtb")
    assert (20, 20) in pts and (980, 480) in pts and len([p for p in pts if p[1] == 20]) == 5
    out = os.path.join(T.TMP, "ban_out.pdf")
    pp.save_pdf([it], R, s, out)
    pdf = pikepdf.open(out)
    cs = pdf.pages[0].Resources.ColorSpace
    sep = next(iter(cs.values()))
    assert str(sep[1]) == "/CutContour"
    data = b"".join(c.read_bytes() for c in (pdf.pages[0].Contents if isinstance(pdf.pages[0].Contents, pikepdf.Array)
                                            else [pdf.pages[0].Contents]))
    assert b"re S" in data and b"/PMCut CS" in data
    # Schnittkante = Endformat + Saum: 1060 × 500 (ohne den Überfüller oben/unten)
    import re
    m = re.search(rb"([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+) re S", data)
    w, h = float(m.group(3)) / MM, float(m.group(4)) / MM
    assert T.near(max(w, h), 1060, 0.5) and T.near(min(w, h), 500, 0.5), (w, h)


def test_fold_marks_din824():
    xs, ys = pp.fold_positions(1189, 841)
    assert xs[-1] == 999 and 210 in xs and ys == [297, 594]
    xs, ys = pp.fold_positions(420, 297)
    assert xs == [210.0, 230.0] and ys == []                  # 190 von rechts, Rest auf 210
    d = pdfium.PdfDocument(T.plan_pdf("fold.pdf", 851, 604))
    R = [rolls.Roll(914)]
    s = pp.PlanSettings(fold_marks=True, rotate="keep", weights=[])
    it = pp.analyze(d, [0], s, R, "fold.pdf")
    assert pp.save_pdf(it, R, s, os.path.join(T.TMP, "fold_out.pdf")) == 1


def test_hotfolder_output_and_log():
    from pdfdruck import config, printlog
    from pdfdruck.session import Session
    hot = os.path.join(T.TMP, "versaworks")
    logdir = os.path.join(T.TMP, "hotlog")
    pp.save_hotfolders([{"name": "VersaWorks", "dir": hot}])
    rolls.save_manual("folder:VersaWorks", [rolls.Roll(1370, name="PVC")])
    src = T.plan_pdf("hot.pdf", 1000, 500, frames=0)
    sess = Session(dict(config.BUILTIN, print_log={"force": True, "dir": logdir}))
    info = pp.plan_files([src], poster(printer="folder:VersaWorks", copies=2, cut_contour=True, live_rolls=False,
                                       nest=False), session=sess)
    files = os.listdir(hot)
    assert len(files) == 1 and files[0].endswith("_hot_p1_2x.pdf"), files
    d = pdfium.PdfDocument(os.path.join(hot, files[0]))
    assert len(d) == 2                                     # Ordner kennt keine Kopienzahl: Seite zweimal
    assert info["jobs"][0]["job_id"] == files[0]
    rows = open(os.path.join(logdir, printlog.CSV_NAME), encoding="utf-8-sig").read()
    assert "folder:VersaWorks" in rows and ";1370;" in rows


def test_material_values():
    from pdfdruck import config
    from pdfdruck.session import Session
    from pdfdruck.printers import Choice, Option
    caps = T.plotter_caps()
    caps.options["EPIJ_Dens"] = Option("EPIJ_Dens", "Farbdichte", "", [Choice("0", "Standard"), Choice("-10", "-10 %")],
                                       "0")
    caps.options["cupsPrintQuality"] = Option("cupsPrintQuality", "Qualität", "", [Choice("Draft", "Entwurf"),
                                              Choice("High", "Hoch")], "Draft")
    from pdfdruck import printers
    printers._assign_roles(caps)
    assert printmat.density_options(caps) == [("EPIJ_Dens", "Farbdichte")]
    printmat.save([{"name": "Fotopapier 200", "category": "quality", "weight": 200, "media": "Photo",
                    "quality": "High", "density_key": "EPIJ_Dens", "density": "-10", "tac": 250,
                    "printer": "Plotter"},
                   {"name": "Bond 80", "category": "plan", "weight": 80, "media": "Plain"}])
    mats = printmat.for_printer("Plotter", "quality")
    assert [m["name"] for m in mats] == ["Fotopapier 200"]
    assert printmat.find("bond 80", "Plotter")["weight"] == 80
    printmat.set_default("Plotter", "quality", mats[0]["id"])
    assert printmat.default_for("Plotter", "quality") == mats[0]["id"]
    with T.FakePlotter():
        sess = Session(config.BUILTIN)
        s = poster(printer="Plotter", material="Fotopapier 200")
        vals = pp.values_for(sess, "Plotter", caps, s)
    assert vals["MediaType"] == "Photo" and vals["EPIJ_Dens"] == "-10" and vals["cupsPrintQuality"] == "High"
    # Material mit Grammatur wählt die Rolle
    R = [rolls.Roll(914, weight=80), rolls.Roll(1067, weight=200)]
    use, _n = pp.eligible_for(R, s)
    assert [r.width_mm for r in use] == [1067]
    assert printmat.notes({"name": "PVC", "tac": 250}, {}) and not printmat.notes(printmat.find("Fotopapier 200"), {})


def _fake_roland(answer: bytes):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    got = {}

    def run():
        c, _a = srv.accept()
        got["data"] = c.recv(64)
        c.sendall(answer)
        c.close()
        srv.close()
    threading.Thread(target=run, daemon=True).start()
    return srv.getsockname()[1], got


def test_roland():
    d = roland.parse_hardclip(b"0,0,2000000,24000\r")
    assert d["width_mm"] == 600 and d["length_mm"] == 50000
    port, got = _fake_roland(b"0,0,40000,23360\r")
    q = roland.query("127.0.0.1", port)
    assert got["data"] == b"IN;OH;" and q["width_mm"] == 584
    assert roland.is_roland("Roland GS-24") and roland.is_roland("", "CAMM-1 GR2-640") and not roland.is_roland("Canon")
    h = roland.hpgl(roland.rect_paths([(10, 0, 110, 50)]), force=80, speed=20).decode()
    assert h.startswith("IN;VS20;FS80;PU0,400;PD0,4400,2000,4400") and h.endswith("PU0,0;")
    # Rollenabfrage nimmt bei Roland-Geräten OH statt IPP/SNMP
    old = roland.PORT
    port, _got = _fake_roland(b"0,0,99999,52000\r")
    try:
        roland.query.__defaults__ = (port, 3.0)
        st = rolls.query_roland("127.0.0.1")
    finally:
        roland.query.__defaults__ = (old, 3.0)
    assert st.origin == "roland" and st.rolls[0].width_mm == 1300


def test_cli_poster_and_plt():
    src = T.plan_pdf("clip.pdf", 297, 420, frames=1)
    plt = os.path.join(T.TMP, "cut.plt")
    r = T._cli("plan", src, "--kind", "poster", "--rolls", "914", "--copies", "6", "--set", "cut_contour=true",
               "--plt", plt, "--dry-run", "--json")
    assert r.returncode == 0, r.stderr
    done = json.loads(r.stdout.strip().splitlines()[-1])
    assert done["nest"] and done["kind"] == "poster" and done["jobs"][0]["pieces"] == 6
    assert done["cut_file"]["cuts"] == 1 and open(plt).read().startswith("IN;")


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
