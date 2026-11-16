# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Pages as images (rasterexport.py): formats, file names, multi-page TIFF, command line, workflow step, job."""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, ROOT)

from PIL import Image  # noqa: E402

from pdfdruck import cmyk, jobproc, rasterexport as R  # noqa: E402

SAMPLE = os.path.join(HERE, "sample.pdf")  # 7 pages, different sizes


def _tmp():
    return tempfile.mkdtemp(prefix="pm-img-")


def _white_page() -> str:
    """One A6 page, white with a black square in the middle."""
    from reportlab.pdfgen import canvas

    path = os.path.join(_tmp(), "w.pdf")
    c = canvas.Canvas(path, pagesize=(298, 420))
    c.rect(119, 180, 60, 60, fill=1, stroke=0)
    c.showPage()
    c.save()
    return path


def test_names():
    s = R.ExportSettings()
    assert R.target_files("/x/a.png", [4], s) == ["/x/a.png"]  # one page: the name as given
    assert R.target_files("/x/a", [0, 9], R.ExportSettings(format="jpg")) == ["/x/a-001.jpg", "/x/a-010.jpg"]
    assert R.target_files("/x/a.png", list(range(1200)), s)[-1] == "/x/a-1200.png"
    assert R.target_files("/x/a.tif", [0, 1], R.ExportSettings(format="tiff", multipage=True)) == ["/x/a.tif"]
    assert R.target_files("/x/a.pdf", [0], R.ExportSettings(format="tiff")) == ["/x/a.pdf.tif"]
    assert R.format_for("b.JPEG") == "jpg" and R.format_for("c.tiff") == "tiff" and R.format_for("d.x") == "png"


def test_check():
    assert R.check(R.ExportSettings()) == []
    assert R.check(R.ExportSettings(color="cmyk"))  # PNG has no CMYK
    assert R.check(R.ExportSettings(format="gif")) and R.check(R.ExportSettings(dpi=5))
    assert R.check(R.ExportSettings(format="jpg", quality=0)) and R.check(R.ExportSettings(compression="x"))
    assert R.check(R.ExportSettings(format="tiff", color="cmyk")) == []


def test_png_jpg_tiff():
    d = _tmp()
    info = R.export(SAMPLE, os.path.join(d, "p.png"), R.ExportSettings(dpi=36), pages=[0, 2])
    assert [os.path.basename(f) for f in info["files"]] == ["p-001.png", "p-003.png"]
    with Image.open(info["files"][0]) as im:
        assert im.mode == "RGB" and im.info.get("icc_profile") and round(im.info["dpi"][0]) == 36
    w = _white_page()
    o = R.export(w, os.path.join(d, "o.png"), R.ExportSettings(dpi=72))
    with Image.open(o["files"][0]) as im:
        assert im.size == (298, 420) and im.getpixel((5, 5)) == (255, 255, 255) and im.getpixel((149, 210)) == (0, 0, 0)
    t = R.export(w, os.path.join(d, "t.png"), R.ExportSettings(dpi=72, transparent=True))
    with Image.open(t["files"][0]) as im:
        assert im.mode == "RGBA" and im.getpixel((5, 5))[3] == 0 and im.getpixel((149, 210))[3] == 255
    j = R.export(SAMPLE, os.path.join(d, "j.jpg"), R.ExportSettings(format="jpg", dpi=20, quality=60), pages=[1])
    with Image.open(j["files"][0]) as im:
        assert im.format == "JPEG" and im.mode == "RGB"
    g = R.export(SAMPLE, os.path.join(d, "g.tif"), R.ExportSettings(format="tiff", dpi=20, color="gray"), pages=[1])
    with Image.open(g["files"][0]) as im:
        assert im.format == "TIFF" and im.mode == "L" and im.info.get("compression") == "tiff_lzw"


def test_multipage_tiff_and_nothing_half_written():
    d = _tmp()
    out = os.path.join(d, "alle.tif")
    s = R.ExportSettings(format="tiff", dpi=15, multipage=True, compression="zip")
    info = R.export(SAMPLE, out, s)
    with Image.open(out) as im:
        assert info["files"] == [out] and im.n_frames == 7 and im.info.get("compression") == "tiff_adobe_deflate"
    calls = []

    def cancel():
        calls.append(1)
        return len(calls) > 2

    try:
        R.export(SAMPLE, os.path.join(d, "x.png"), R.ExportSettings(dpi=15), cancel=cancel)
        raise AssertionError("not cancelled")
    except Exception as e:  # noqa: BLE001 – core.Cancelled
        assert type(e).__name__ == "Cancelled"
    assert not [f for f in os.listdir(d) if f.endswith(".part")]


def test_cmyk_needs_ghostscript_and_profile():
    d = _tmp()
    if not cmyk.ghostscript():
        try:
            R.export(SAMPLE, os.path.join(d, "c.tif"), R.ExportSettings(format="tiff", color="cmyk", dpi=20), [0])
        except (RuntimeError, ValueError):
            print("   (CMYK übersprungen: kein Ghostscript)")
            return
        raise AssertionError("CMYK without Ghostscript")
    from test_softproof import cmyk_profile

    s = R.ExportSettings(format="tiff", color="cmyk", dpi=20, profile=cmyk_profile())
    info = R.export(SAMPLE, os.path.join(d, "c.tif"), s, [0])
    with Image.open(info["files"][0]) as im:
        assert im.mode == "CMYK" and im.info.get("icc_profile")


def _cli(*args):
    env = dict(os.environ, PASSERMARK_LANG="de", PYTHONPATH=ROOT)
    return subprocess.run([sys.executable, "-m", "pdfdruck.cli", *args], capture_output=True, text=True, env=env)


def test_cli_and_workflow():
    d = _tmp()
    r = _cli("export", SAMPLE, os.path.join(d, "c.jpg"), "--pages", "2-3", "--dpi", "20", "--json")
    last = json.loads(r.stdout.strip().splitlines()[-1])
    assert r.returncode == 0 and last["event"] == "done" and len(last["files"]) == 2, r.stdout + r.stderr
    r = _cli("export", SAMPLE, os.path.join(d, "c.png"), "--set", "color=cmyk")
    assert r.returncode == 2 and "CMYK" in r.stderr
    wf = os.path.join(d, "wf.json")
    with open(wf, "w", encoding="utf-8") as f:
        json.dump(
            {
                "passermark": "workflow",
                "version": 1,
                "steps": [{"job": "export", "pages": "1", "settings": {"out": "bilder/s.png", "dpi": 15}}],
            },
            f,
        )
    r = _cli("run", wf, os.path.join(d, "out.pdf"), "--in", SAMPLE)
    assert r.returncode == 0 and os.path.isfile(os.path.join(d, "bilder", "s.png")), r.stdout + r.stderr
    assert os.path.isfile(os.path.join(d, "out.pdf"))  # the PDF goes on unchanged
    with open(wf, "w", encoding="utf-8") as f:
        json.dump({"passermark": "workflow", "version": 1, "steps": [{"job": "export", "settings": {}}]}, f)
    r = _cli("check", wf, "--in", SAMPLE, "--out", os.path.join(d, "o.pdf"))
    assert r.returncode == 2 and "Zieldatei fehlt" in r.stdout + r.stderr


def test_job_process():
    d = _tmp()
    job = jobproc.JobProcess(jobproc.EXPORT, SAMPLE, os.path.join(d, "j.png"), {"dpi": 15}, [0, 6], lang="de")
    res = job.run()
    assert res["event"] == "done" and [os.path.basename(f) for f in res["files"]] == ["j-001.png", "j-007.png"], res


if __name__ == "__main__":
    for k, fn in list(globals().items()):
        if k.startswith("test_"):
            fn()
            print("ok", k)
