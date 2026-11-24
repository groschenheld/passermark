# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Output preview: plates of a page (separations.py), soft proof with plates/ink coverage (proof.py), panel texts.
Ghostscript is simulated: the fake writes the files the way tiffsep does (separations inverted, spot colour names
in brackets, %XX for characters a file name cannot hold, the CMYK look of spot colours on stderr)."""

import os
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "_qtstub"))
sys.path.insert(0, os.path.join(HERE, ".."))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from pdfdruck import cmyk, l10n, proof, separations  # noqa: E402
from test_softproof import cmyk_profile  # noqa: E402

l10n.set_language("de")

W, H = 40, 20


def _fake_inks():
    """C left half 100 %, K right quarter 100 %, spot colour 'PANTONE 185 C' in the middle 50 %, 'Lack/Gold' on top."""
    c = np.zeros((H, W), np.uint8)
    c[:, : W // 2] = 255
    k = np.zeros((H, W), np.uint8)
    k[:, 3 * W // 4 :] = 255
    spot = np.zeros((H, W), np.uint8)
    spot[:, 10:30] = 128
    gold = np.zeros((H, W), np.uint8)
    gold[:5, :] = 255
    return {
        "Cyan": c,
        "Magenta": np.zeros((H, W), np.uint8),
        "Yellow": np.zeros((H, W), np.uint8),
        "Black": k,
        "PANTONE 185 C": spot,
        "Lack/Gold": gold,
    }


def _fake_gs(stdout_eq=True):
    """Stand-in for cmyk._run: writes the tiffsep files of the command's -o into its folder."""

    def run(cmd, timeout=0):
        out = cmd[cmd.index("-o") + 1]
        d, base = os.path.dirname(out), os.path.splitext(os.path.basename(out))[0]
        inks = _fake_inks()
        comp = np.stack([inks[n] for n in separations.PROCESS], axis=-1).astype(np.float32)
        comp[..., 1] += inks["PANTONE 185 C"] * 0.9  # spot colour simulated in the composite
        comp[..., 2] += inks["PANTONE 185 C"] * 0.8
        Image.fromarray(np.clip(comp, 0, 255).astype(np.uint8), "CMYK").save(out)
        for n, a in inks.items():
            fn = n.replace("/", "%2F")
            Image.fromarray(255 - a, "L").save(os.path.join(d, f"{base}({fn}).tif"))  # like film: 0 = full ink
        err = ""
        if stdout_eq:
            err = '%%SeparationColor: "PANTONE 185 C" 100% ink = 0 30485 25876 0 CMYK\n'
            err += '%%SeparationColor: "Lack/Gold" 100% ink = 0 6552 26208 6552 CMYK\n'
        return types.SimpleNamespace(returncode=0, stdout="", stderr=err)

    return run


def _patched(stdout_eq=True):
    old = cmyk._run, cmyk.ghostscript
    cmyk._run, cmyk.ghostscript = _fake_gs(stdout_eq), (lambda: "/usr/bin/gs")
    return old


def _restore(old):
    cmyk._run, cmyk.ghostscript = old


def _sample_pdf() -> str:
    return os.path.join(HERE, "sample.pdf")


SPEC = {"icc": "", "space": "CMYK"}


def test_parse():
    eq = separations.parse_equivalents(
        'x\n%%SeparationColor: "PANTONE 185 C" 100% ink = 0 30485 25876 0 CMYK\n'
        '%%SeparationColor: "Weiß Deckend" 100% ink = 0 0 0 0 CMYK\n'
        "%%SeparationName: Old Spot CMYK = [ 0.1 0.2 0.3 0.4 ]\n"
    )
    assert list(eq) == ["PANTONE 185 C", "Weiß Deckend", "Old Spot"]
    assert abs(eq["PANTONE 185 C"][1] - 30485 / 32760) < 1e-6 and eq["Weiß Deckend"] == (0, 0, 0, 0)
    assert eq["Old Spot"] == (0.1, 0.2, 0.3, 0.4)
    assert separations._name_of("/t/p(Cyan).tif", "p.tif") == "Cyan"
    assert separations._name_of("/t/p(Lack%2FGold).tif", "p.tif") == "Lack/Gold"
    assert separations._name_of("/t/p(Wei%C3%9F).tif", "p.tif") == "Weiß"
    assert separations._name_of("/t/p.tif", "p.tif") is None
    assert separations._name_of("/t/p.s0.tif", "p.tif") == "#1"


def test_tiffsep_plates():
    old = _patched()
    try:
        p = separations.run_tiffsep(_sample_pdf(), 0, 72, dict(SPEC, icc=cmyk_profile()))
    finally:
        _restore(old)
    assert p.names == ["Cyan", "Magenta", "Yellow", "Black", "PANTONE 185 C", "Lack/Gold"]
    assert p.spots == ["PANTONE 185 C", "Lack/Gold"]
    assert p.ink["Cyan"][0, 0] == 255 and p.ink["Cyan"][0, W - 1] == 0  # turned round: 255 = full ink
    assert p.size == (W, H)
    assert abs(p.equiv["PANTONE 185 C"][1] - 0.9305) < 0.01
    # without the CMYK look on stderr: estimated from the composite
    old = _patched(stdout_eq=False)
    try:
        p2 = separations.run_tiffsep(_sample_pdf(), 0, 72, dict(SPEC, icc=cmyk_profile()))
    finally:
        _restore(old)
    c, m, y, k = p2.equiv["PANTONE 185 C"]
    assert c < 0.05 and abs(m - 0.9) < 0.05 and abs(y - 0.8) < 0.05


def _plates():
    old = _patched()
    try:
        return separations.run_tiffsep(_sample_pdf(), 0, 72, dict(SPEC, icc=cmyk_profile()))
    finally:
        _restore(old)


def test_compose_and_tac():
    p = _plates()
    allc = np.asarray(separations.compose(p))
    assert (allc == p.composite).all()  # everything: Ghostscript's own composite
    no_k = np.asarray(separations.compose(p, ["Black"]))
    assert no_k[10:, :, 3].max() == 0 and no_k[10, 0, 0] == 255  # rows from 5 on: no gold (gold has some K)
    only_spot = np.asarray(separations.compose(p, ["Cyan", "Magenta", "Yellow", "Black", "Lack/Gold"]))
    assert only_spot[10, 0].tolist() == [0, 0, 0, 0] and only_spot[10, 15, 1] > 100  # spot colour as its look
    gray = separations.compose(p, ["Magenta", "Yellow", "Black", "PANTONE 185 C", "Lack/Gold"], gray=True)
    assert gray.mode == "L" and gray.getpixel((0, 10)) == 0 and gray.getpixel((W - 1, 10)) == 255
    assert separations.visible(p, ["Black"]) == ["Cyan", "Magenta", "Yellow", "PANTONE 185 C", "Lack/Gold"]
    t = separations.tac_map(p)
    assert abs(t[10, 0] - 100) < 0.5 and abs(t[0, 15] - (100 + 50.2 + 100)) < 0.5  # C + spot + gold
    assert separations.swatch_rgb(p, "Cyan") == separations.PROCESS_RGB["Cyan"]
    r, g, b = separations.swatch_rgb(p, "PANTONE 185 C")
    assert r > 200 and g < 60


def test_page_info_and_values():
    old = _patched()
    try:
        info = separations.page_info(_sample_pdf(), 0, dict(SPEC, icc=cmyk_profile(), tac=200))
    finally:
        _restore(old)
    names = [i["name"] for i in info["inks"]]
    assert names[:4] == ["Cyan", "Magenta", "Yellow", "Black"] and info["inks"][4]["spot"]
    assert info["inks"][0]["label"] == "Cyan" and info["inks"][2]["label"] == "Gelb"
    assert abs(info["inks"][0]["coverage"] - 50) < 1 and info["inks"][1]["coverage"] == 0
    assert info["max_tac"] > 240 and info["over"] > 0
    # above 200 %: the gold strip over cyan + spot (columns 10..19, rows 0..4) -> 10 × 5 of 800 pixels
    assert abs(info["over"] - 50 / 800 * 100) < 0.01
    assert abs(separations.share_over(info, 300) - 0.0) < 1e-9
    x0, y0, x1, y1 = info["crop"]
    v = separations.values_at(info, x0 + 1, y1 - (y1 - y0) / 2)  # left edge, middle: cyan 100 %
    assert abs(v["Cyan"] - 100) < 0.5 and v["Black"] == 0 and abs(v[""] - 100) < 0.5
    assert separations.values_at(info, x1 + 50, y0) is None
    assert separations.values_at(None, 1, 1) is None


def test_proof_output_preview():
    icc = cmyk_profile()
    p = _plates()
    old = separations.plates_for
    separations.plates_for = lambda *a, **k: p
    try:
        spec = {"icc": icc, "space": "CMYK", "name": "Test", "mode": "tac", "tac": 200}
        img = proof._output_preview("x.pdf", 0, 72, 72, spec, None)
        # above 200 %: rows 0..4, columns 10..19 – outlined, not filled: the area keeps its colour
        assert (
            img.size == (W, H) and img.getpixel((15, 6)) == proof.TAC_COLOR and img.getpixel((8, 2)) == proof.TAC_COLOR
        )
        assert img.getpixel((15, 2)) != proof.TAC_COLOR and img.getpixel((0, 15)) != proof.TAC_COLOR
        spec = dict(spec, mode="sep", hide=["Magenta", "Yellow", "Black", "PANTONE 185 C", "Lack/Gold"], gray=True)
        img = proof._output_preview("x.pdf", 0, 72, 36, spec, None)  # supersampled: scaled down
        assert img.size == (W * 2, H * 2) and img.getpixel((0, 20)) == (0, 0, 0)
    finally:
        separations.plates_for = old
    base = {"icc": icc, "space": "CMYK", "name": "Test"}
    assert proof.spec_key(dict(base, mode="sep")) != proof.spec_key(dict(base, mode="sep", hide=["Black"]))
    assert proof.spec_key(dict(base, mode="sep", hide=["Black", "Cyan"])) == proof.spec_key(
        dict(base, mode="sep", hide=["Cyan", "Black"])
    )
    assert "Ausgabevorschau" in proof.describe_spec(dict(base, mode="sep", hide=["Black"]))
    assert "ohne Schwarz" in proof.describe_spec(dict(base, mode="sep", hide=["Black"]))
    assert "Farbauftrag > 280" in proof.describe_spec(dict(base, mode="tac", tac=280))
    assert separations.describe(dict(base, mode="sep")) == "Alle Auszüge"


def test_outline():
    m = np.zeros((20, 20), bool)
    m[5:15, 5:15] = True
    o = proof.outline(m, 2)
    assert not o[10, 10] and not o[5, 5] and o[3, 10] and o[10, 16] and not o[0, 10]
    assert o.sum() == 14 * 14 - 100  # 2 px around, corners round with 8 neighbours = full square
    assert proof.outline(np.zeros((3, 3), bool), 2).sum() == 0


def test_plates_cache():
    calls = []
    old = separations.run_tiffsep
    separations.run_tiffsep = lambda *a, **k: calls.append(a) or separations.Plates()
    try:
        separations._CACHE.clear()
        spec = {"icc": "a.icc"}
        separations.plates_for(_sample_pdf(), 0, 100, spec)
        separations.plates_for(_sample_pdf(), 0, 100, dict(spec, hide=["Black"], mode="sep"))  # same plates
        assert len(calls) == 1
        separations.plates_for(_sample_pdf(), 0, 100, dict(spec, overprint=False))
        separations.plates_for(_sample_pdf(), 1, 100, spec)
        assert len(calls) == 3 and len(separations._CACHE) == separations._CACHE_MAX
    finally:
        separations.run_tiffsep = old
        separations._CACHE.clear()


def test_cms_flag_old_pillow():
    """Pillow before 10.3 (e.g. Ubuntu 24.04: 10.2) has ImageCms.FLAGS instead of ImageCms.Flags."""
    from PIL import ImageCms

    new = int(ImageCms.Flags.BLACKPOINTCOMPENSATION)
    assert proof._cms_flag("BLACKPOINTCOMPENSATION") == new
    saved = ImageCms.Flags
    try:
        del ImageCms.Flags
        ImageCms.FLAGS = {"BLACKPOINTCOMPENSATION": new, "SOFTPROOFING": 16384}
        assert proof._cms_flag("BLACKPOINTCOMPENSATION") == new and proof._cms_flag("SOFTPROOFING") == 16384
    finally:
        ImageCms.Flags = saved
        del ImageCms.FLAGS


def test_panel_texts():
    from pdfdruck.gui import outputpanel as O

    assert O.count_text(5, 5) == "Alle 5 Farben sichtbar."
    assert O.count_text(3, 5) == "3 von 5 Farben sichtbar."
    assert "nichts über 300" in O.tac_text({"max_tac": 280.4, "over": 0.0, "limit": 300})
    t = O.tac_text({"max_tac": 342, "over": 1.25, "limit": 300})
    assert "342" in t and "1,2" in t
    assert O.tac_text(None) == ""
    assert "gesamt 160" in O.values_text({"": 160.2})
    assert O.values_text(None).startswith("Maus")
    panel = O.OutputPanel()
    assert panel.options() is None  # off
    panel.mode = "sep"
    panel.hide = {"Black"}
    assert panel.options()["mode"] == "sep" and panel.options()["hide"] == ["Black"]


def test_problem_texts():
    """Main window: why the output preview cannot start (no condition, RGB profile, no Ghostscript)."""
    from pdfdruck.gui.maincolour import MainColourMixin

    class M(MainColourMixin):
        pass

    m = M()
    assert "Keine Druckbedingung" in m._output_problem(None)
    assert "CMYK-Profil" in m._output_problem({"space": "RGB"})
    from pdfdruck import platform as _platform

    old = _platform.ghostscript
    try:
        _platform.ghostscript = lambda: None
        assert "Ghostscript" in m._output_problem({"space": "CMYK"})
        _platform.ghostscript = lambda: "/usr/bin/gs"
        assert m._output_problem({"space": "CMYK"}) == ""
    finally:
        _platform.ghostscript = old


if __name__ == "__main__":
    tempfile.tempdir = tempfile.mkdtemp()
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
