# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
import os, sys
import os as _os
_os.environ.setdefault("PASSERMARK_LANG", "de")   # Tests prüfen deutsche Texte
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from PIL import Image, ImageCms
from pdfdruck import proof, printers as P


def caps():
    c = P.PrinterCaps("x", "ppd")
    rng = [P.Choice(str(i), str(i)) for i in range(-25, 26)]
    for k, t in [("Brightness", "Helligkeit"), ("Contrast", "Kontrast"), ("Saturation", "Sättigung")]:
        c.options[k] = P.Option(k, t, "g", rng, "0")
    c.options["Ink"] = P.Option("Ink", "Farbe / Graustufen", "g",
                                [P.Choice("COLOR", "Farbe"), P.Choice("MONO", "Graustufen")], "COLOR")
    P._assign_roles(c)
    return c


def test_detect():
    a = proof.adjustments(caps(), {"Brightness": "25", "Ink": "COLOR"})
    assert a["brightness"] == 1.0 and not a["gray"]
    assert proof.adjustments(caps(), {"Ink": "MONO"})["gray"]
    assert not proof.adjustments(caps(), {})["labels"]          # alles Standard -> nichts simulieren


def test_apply():
    img = Image.new("RGB", (10, 10), (200, 60, 40))
    g = proof.apply(img, {"gray": True})
    r, gg, b = g.getpixel((1, 1)); assert r == gg == b
    br = proof.apply(img, {"brightness": 1.0})
    assert sum(br.getpixel((1, 1))) > sum(img.getpixel((1, 1)))
    icc = "/tmp/_srgb.icc"
    open(icc, "wb").write(ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes())
    sp = proof.apply(img, {}, icc, "relative", True)
    assert max(abs(a - b) for a, b in zip(sp.getpixel((1, 1)), img.getpixel((1, 1)))) <= 3   # sRGB->sRGB ~ neutral


def test_paper_white_stays_white():
    img = Image.new("RGB", (4, 1)); img.putdata([(255, 255, 255), (0, 0, 0), (128, 128, 128), (200, 60, 40)])
    for a in ({"brightness": -1.0}, {"brightness": 1.0}, {"contrast": -1.0}, {"contrast": 1.0},
              {"saturation": 1.0, "contrast": -0.5, "brightness": -0.5}, {"gray": True, "brightness": -1}):
        out = proof.apply(img, a)
        assert out.getpixel((0, 0)) == (255, 255, 255), (a, out.getpixel((0, 0)))
        assert out.getpixel((1, 0)) == (0, 0, 0), a
    assert proof.apply(img, {"brightness": -1.0}).getpixel((2, 0))[0] < 128     # Mitteltöne dunkler
    assert proof.apply(img, {"contrast": -1.0}).getpixel((3, 0))[0] < 200       # weniger Kontrast


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("ok", k)
