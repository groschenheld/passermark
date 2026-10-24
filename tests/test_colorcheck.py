# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Farbe (1.17): eigene Materialien, Standardprofile, Farbprüfung mit Empfehlungen, Ausgabe für die Druckerei
(Auftrag „press“) – ohne Qt. Ghostscript wird genutzt, wenn vorhanden; sonst die Wege ohne Umwandlung."""
import io, json, os, subprocess, sys, tempfile, zipfile
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
os.environ["PASSERMARK_LANG"] = "de"
USER = tempfile.mkdtemp(prefix="pm-user-")
os.environ["PASSERMARK_USER_DIR"] = USER

import pikepdf
from PIL import Image
from test_softproof import cmyk_profile
from pdfdruck import cmyk, colorcheck, colorlab, core, pressexport, usercolor, workflow


def sample_pdf(rgb=True, cmyk_ink=(0.9, 0.9, 0.8, 0.9), oi="", spot=False) -> bytes:
    pdf = pikepdf.new()
    pg = pdf.add_blank_page(page_size=(200, 200))
    res = pikepdf.Dictionary()
    ops = b""
    if cmyk_ink:
        ops += b"q %.2f %.2f %.2f %.2f k 0 0 100 100 re f Q " % cmyk_ink
    if rgb:
        im = Image.new("RGB", (20, 20), (0, 200, 0))
        b = io.BytesIO()
        im.save(b, "JPEG")
        x = pikepdf.Stream(pdf, b.getvalue())
        x.Type, x.Subtype = pikepdf.Name.XObject, pikepdf.Name.Image
        x.Width = x.Height = 20
        x.ColorSpace, x.BitsPerComponent, x.Filter = pikepdf.Name.DeviceRGB, 8, pikepdf.Name.DCTDecode
        res.XObject = pikepdf.Dictionary(Im0=x)
        ops += b"q 100 0 0 100 50 50 cm /Im0 Do Q 1 0 0 rg 10 150 30 30 re f "
    if spot:
        fn = pdf.make_indirect(pikepdf.Dictionary(FunctionType=2, Domain=[0, 1], C0=[0, 0, 0, 0], C1=[0, 1, 1, 0], N=1))
        res.ColorSpace = pikepdf.Dictionary(CS0=pikepdf.Array([pikepdf.Name.Separation, pikepdf.Name("/HKS 13"),
                                                               pikepdf.Name.DeviceCMYK, fn]))
        ops += b"/CS0 cs 1 scn 120 10 40 40 re f "
    pg.Resources = res
    pg.Contents = pikepdf.Stream(pdf, ops)
    if oi:
        oid = pikepdf.Dictionary(Type=pikepdf.Name.OutputIntent, S=pikepdf.Name.GTS_PDFX,
                                 OutputConditionIdentifier=pikepdf.String(oi))
        pdf.Root.OutputIntents = pikepdf.Array([oid])
    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()


def write(data: bytes) -> str:
    fd, p = tempfile.mkstemp(suffix=".pdf")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return p


def target():
    return colorcheck.target_from_file(cmyk_profile())


# --------------------------------------------------------------------------- #
def test_user_materials_roundtrip_and_merge():
    f = cmyk_profile()
    mats = [{"id": "u_natur", "name": "Natur 120 g", "weight": 120, "surface": "uncoated", "white": [93, 0.5, 4],
             "profiles": {"*": f}, "intent": "relative", "notes": "", "junk": 1},
            {"id": "kaputt"}, {"id": "u_x", "white": [200, 0, 0], "surface": "??", "intent": "x"}]
    os.makedirs(USER, exist_ok=True)
    with open(usercolor.materials_file(), "w") as fh:
        json.dump({"materials": mats}, fh)
    got = usercolor.load_materials()
    assert [m["id"] for m in got] == ["u_natur", "u_x"]
    assert "junk" not in got[0] and got[1]["white"] is None and got[1]["surface"] == "" and got[1]["intent"] == ""
    usercolor.save_materials(got)
    assert usercolor.load_materials() == got
    assert usercolor.new_id("Natur 120 g", {"u_Natur_120_g"}) == "u_Natur_120_g_2"
    cfg = {"materials": [{"id": "admin1", "name": "A", "profiles": {}}], "color_profiles": []}
    allm = colorlab.all_materials(cfg)
    assert [(m["id"], m["scope"]) for m in allm] == [("admin1", "admin"), ("u_natur", "user"), ("u_x", "user")]
    assert colorlab.material_by_id(cfg, "u_natur")["name"] == "Natur 120 g"
    # Profil als Pfad: Softproof-Auswahl, CMYK-Umwandlung
    assert colorlab.resolve_profile(cfg, f)["file"] == f and colorlab.resolve_profile(cfg, "/gibt/es/nicht") is None
    ch = [c for c in colorlab.proof_choices(cfg) if c["material"] == "u_natur"]
    assert ch and ch[0]["icc"] == f and ch[0]["white"] == [93, 0.5, 4] and "Eigenes Material" in ch[0]["label"]
    assert colorlab.cmyk_profile_of(cfg, got[0]) == f
    # Druckdialog: nur Profile der Verwaltung -> eigenes Material mit Pfad erscheint dort nicht
    assert colorlab.profile_for(cfg, got[0], "epson") == f
    assert colorlab.all_materials(dict(cfg, _no_user_materials=True)) == [dict(cfg["materials"][0], scope="admin")]
    usercolor.save_materials([])


def test_import_icc_and_profile_dirs():
    f = cmyk_profile()
    p = usercolor.import_icc(f)
    assert os.path.dirname(p) == usercolor.icc_dir() and usercolor.import_icc(f) == p     # nicht doppelt
    assert usercolor.icc_dir() in cmyk.system_profile_dirs()
    assert os.path.realpath(p) in {os.path.realpath(c.path) for c in cmyk.find_profiles(None)}
    try:
        usercolor.import_icc(__file__)
        raise AssertionError("kein ICC")
    except ValueError:
        pass
    os.remove(p)


def test_standard_profiles_catalogue_and_download():
    keys = {p["key"] for p in usercolor.STANDARD_PROFILES}
    assert {"PSOcoated_v3", "PSOuncoated_v3_FOGRA52"} <= keys
    assert [p["key"] for p in usercolor.standards_for_surface("matte")][0] == "PSOcoated_v3"
    data = open(cmyk_profile(), "rb").read()

    class R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    seen = []
    path = usercolor.download_standard("PSOcoated_v3", opener=lambda req, timeout: (seen.append(req.full_url), R(data))[1])
    assert seen == ["https://registry.color.org/profile-registry/profiles/PSOcoated_v3.icc"]
    assert os.path.basename(path) == "PSOcoated_v3.icc" and usercolor.standard_installed(
        usercolor.standard_by_key("PSOcoated_v3")) == path
    # nicht installierte Standards als Vorschlag (nach Oberfläche)
    cands = colorlab.standard_candidates()
    assert "PSOcoated_v3" not in {c["std"] for c in cands} and "PSOuncoated_v3_FOGRA52" in {c["std"] for c in cands}
    res = colorlab.suggest({"surface": "uncoated", "white": None}, cands, limit=3)
    assert res[0]["std"] in ("PSOuncoated_v3_FOGRA52", "Uncoated_Fogra47L_VIGC_300")
    for bad in (b"<html>nope</html>", data[:36] + b"xxxx" + data[40:]):
        try:
            usercolor.download_standard("PSOuncoated_v3_FOGRA52", opener=lambda req, timeout, b=bad: R(b))
            raise AssertionError("keine Prüfung")
        except ValueError:
            pass
    os.remove(path)


def test_tac_limits():
    assert usercolor.tac_limit_for("/x/PSOcoated_v3.icc") == 300
    assert usercolor.tac_limit_for("/x/ISOcoated_v2_eci.icc") == 330
    assert usercolor.tac_limit_for("/x/Coated_Fogra39L_VIGC_260.icc") == 260
    assert usercolor.tac_limit_for("/x/irgendwas.icc") == 300


def test_conditions():
    assert colorcheck.condition_keys("Coated FOGRA39 (ISO 12647-2:2004)") >= {"fogra39"}
    assert "fogra51" in colorcheck.condition_keys("PSO Coated v3")
    f = cmyk_profile()                                         # FOGRA39L_coated.icc
    assert colorcheck.same_condition("Coated FOGRA39 (ISO 12647-2:2004)", f)
    assert not colorcheck.same_condition("PSO Uncoated v3 (FOGRA52)", f)


def test_facts_and_findings():
    t = target()
    data = sample_pdf(spot=True)
    f = colorcheck.facts(data, t)
    assert f.rgb_pages == [1] and f.cmyk_pages == [1] and len(f.rgb_images) == 1 and f.rgb_tagged == 0
    assert "HKS 13" in f.spots and not f.output_intents
    assert f.tac and f.tac["max"] >= 300
    res = colorcheck.check(f, t, {})
    keys = [x.key for x in res]
    assert {"rgb", "oi_missing", "spots", "cmyk_unknown"} <= set(keys), keys
    rgb = next(x for x in res if x.key == "rgb")
    assert rgb.action == "convert" and rgb.params["cmyk_mode"] == "rgb_only" and rgb.params["rgb_ask"]
    assert rgb.spots[0].box == (50.0, 50.0, 150.0, 150.0)           # Fundstelle: das Bild
    assert next(x for x in res if x.key == "oi_missing").action == "embed_oi"
    if f.tac["max"] > t.limit:
        tac = next(x for x in res if x.key == "tac")
        assert tac.params["cmyk_mode"] == "all" and tac.params["source"] == t.icc
    assert colorcheck.SEV_ORDER[res[0].severity] <= colorcheck.SEV_ORDER[res[-1].severity]
    assert colorcheck.summary(f)[0][1] == "1"
    # Datei für FOGRA52 angelegt, Ziel FOGRA39 -> neu separieren
    f2 = colorcheck.facts(sample_pdf(rgb=False, cmyk_ink=(0.2, 0.2, 0.2, 0.2), oi="PSO Uncoated v3 (FOGRA52)"), t)
    res2 = colorcheck.check(f2, t, {})
    oo = next(x for x in res2 if x.key == "oi_other")
    assert oo.params["cmyk_mode"] == "all"
    # passt alles -> „Bereit“
    f3 = colorcheck.facts(sample_pdf(rgb=False, cmyk_ink=(0.2, 0.2, 0.2, 0.2), oi="Coated FOGRA39"), t)
    res3 = colorcheck.check(f3, t, {})
    assert {"oi_ok", "ready"} <= {x.key for x in res3} and not [x for x in res3 if x.severity in ("error", "warning")]
    # keine Druckbedingung
    assert colorcheck.check(f3, colorcheck.Target(), {})[0].key == "no_target"


def test_paper_findings():
    t = target()
    t.material, t.material_id, t.surface = "Natur", "u_n", "uncoated"
    f = colorcheck.facts(sample_pdf(rgb=False, cmyk_ink=(0.1, 0, 0, 0)), t)
    keys = {x.key for x in colorcheck.check(f, t, {})}
    assert {"paper_unmeasured", "surface"} <= keys
    t.white = [88.0, 2.0, 12.0]                                    # gelbliches Papier
    res = colorcheck.check(f, t, {})
    assert next(x for x in res if x.key == "paper").action == "get_profiles"


def test_plan_rgb_always_asked():
    t = target()
    f = colorcheck.facts(sample_pdf(), t)
    try:
        pressexport.plan(f, t, pressexport.PressSettings(target=t.icc))
        raise AssertionError("RGB muss entschieden werden")
    except ValueError as e:
        assert "rgb=convert" in str(e)
    p = pressexport.plan(f, t, pressexport.PressSettings(target=t.icc, rgb="convert"))
    assert p["mode"] in ("rgb_only", "all")
    p = pressexport.plan(f, t, pressexport.PressSettings(target=t.icc, rgb="keep", cmyk_mode="rgb_only"))
    assert p["mode"] == "none" and p["tag_rgb"]


def test_press_without_conversion_package():
    t = target()
    src = write(sample_pdf())
    dst = src[:-4] + "_druck.pdf"
    r = pressexport.run(src, dst, pressexport.PressSettings(target=t.icc, rgb="keep", cmyk_mode="none",
                                                             package=True), cfg={})
    with pikepdf.open(dst) as pdf:
        oi = pdf.Root.OutputIntents[0]
        assert str(oi.OutputConditionIdentifier) == t.name and oi.DestOutputProfile.N == 4
        im = pdf.pages[0].Resources.XObject.Im0
        assert im.ColorSpace[0] == pikepdf.Name.ICCBased            # RGB als sRGB gekennzeichnet
        assert "/DefaultRGB" in pdf.pages[0].Resources.ColorSpace
    with zipfile.ZipFile(r["package"]) as z:
        names = z.namelist()
        assert os.path.basename(dst) in names and "ICC/" + os.path.basename(t.icc) in names and "Bericht.txt" in names
        rep = z.read("Bericht.txt").decode()
        assert t.name in rep and "MD5" in rep and "sRGB" in rep
    assert r["info"]["mode"] == "none" and not any("RGB-Inhalte" in n for n in r["notes"])


def test_press_job_and_cli():
    assert "press" in core.JOBS and "press" in workflow.step_jobs()
    t = target()
    src = write(sample_pdf(rgb=False, cmyk_ink=(0.2, 0.2, 0.2, 0.2)))
    dst = src[:-4] + "_job.pdf"
    res = core.run_job("press", src, dst, {"target": t.icc, "cmyk_mode": "none"})
    with pikepdf.open(dst) as pdf:
        assert "/OutputIntents" in pdf.Root
    assert res.info["output_intent"] == t.name
    env = dict(os.environ, PASSERMARK_LANG="de")
    out = src[:-4] + "_cli.pdf"
    r = subprocess.run([sys.executable, "-m", "pdfdruck.cli", "press", write(sample_pdf()), out, "--set",
                        f"target={t.icc}"], capture_output=True, text=True, env=env, cwd=ROOT, timeout=300)
    assert r.returncode != 0 and "rgb=convert" in (r.stdout + r.stderr), r.stdout + r.stderr
    for bad in ({"target": ""}, {"target": t.icc, "cmyk_mode": "x"}, {"target": t.icc, "rgb": "x"}):
        try:
            core.run_job("press", src, dst, bad)
            raise AssertionError(bad)
        except ValueError:
            pass


def test_press_with_ghostscript():
    if not cmyk.ghostscript():
        print("   (übersprungen: kein Ghostscript)")
        return
    t = target()
    src = write(sample_pdf())
    dst = src[:-4] + "_gs.pdf"
    r = pressexport.run(src, dst, pressexport.PressSettings(target=t.icc, rgb="convert"), cfg={})
    f = colorcheck.facts(open(dst, "rb").read(), t)
    assert not f.rgb_pages and f.output_intents and r["info"]["tac_after"] <= t.limit + 2, r["info"]


def test_spotread_ports():
    text = " -c listno   Set communication port from the following list (default 1)\n" \
           "    1 = 'usb:/bus2/dev3/ (X-Rite i1 Pro 2)'\n    2 = '/dev/ttyS0'\n"
    ports = colorlab.spotread_ports(text)
    assert ports == [(1, "usb:/bus2/dev3/ (X-Rite i1 Pro 2)"), (2, "/dev/ttyS0")]
    assert [colorlab.is_instrument(d) for _, d in ports] == [True, False]


if __name__ == "__main__":
    for k, fn in list(globals().items()):
        if k.startswith("test_"):
            fn()
            print("ok", k)
