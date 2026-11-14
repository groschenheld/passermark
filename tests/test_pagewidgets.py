# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Page widget painting: smaller than the page image -> scaled copy (cached, large ones smoothed in the
background); larger -> drawn directly, without an enlarged copy of the whole page (memory, crash when zooming in).
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "_qtstub"), os.path.join(HERE, "..")]

from pdfdruck.gui import pagewidgets as PW  # noqa: E402

CALLS = []
REQUESTS = []


class Img:
    def __init__(self, w, h):
        self.w, self.h = w, h

    def width(self):
        return self.w

    def height(self):
        return self.h

    def cacheKey(self):
        return 7

    def scaled(self, w, h, *a):
        CALLS.append(("scaled", w, h))
        return Img(w, h)


class Painter:
    class RenderHint:
        SmoothPixmapTransform = 1

    def __init__(self, *a):
        pass

    def __getattr__(self, name):
        return lambda *a, **k: CALLS.append((name,) + tuple(a))


class Pixmap:
    @staticmethod
    def fromImage(img):
        CALLS.append(("pixmap", img.w, img.h))
        return Pixmap()

    def setDevicePixelRatio(self, d):
        pass


class Smoother:
    def request(self, *a):
        REQUESTS.append(a[-2:])


def _paint(width, height, master=(2420, 1512), dpr=1.0):
    CALLS.clear()
    REQUESTS.clear()
    w = PW.PageWidget(0)
    w.view = None
    w.devicePixelRatioF = lambda: dpr
    w.width, w.height = (lambda: width), (lambda: height)
    w.rect = lambda: type("R", (), {"adjusted": lambda s, *a: s})()
    w.master = Img(*master)
    w.paintEvent(None)
    return [c[0] for c in CALLS if c[0] in ("scaled", "pixmap", "drawImage", "drawPixmap")]


def test_smaller_than_page_image_uses_cached_copy():
    old = PW.QPainter, PW.QPixmap, PW._Smoother.get
    PW.QPainter, PW.QPixmap, PW._Smoother.get = Painter, Pixmap, classmethod(lambda c: Smoother())
    try:
        assert _paint(800, 500) == ["scaled", "pixmap", "drawPixmap"]
        assert REQUESTS == [(800, 500)]  # large page image: the clean version comes from the background
    finally:
        PW.QPainter, PW.QPixmap, PW._Smoother.get = old


def test_larger_than_page_image_drawn_directly():
    old = PW.QPainter, PW.QPixmap, PW._Smoother.get
    PW.QPainter, PW.QPixmap, PW._Smoother.get = Painter, Pixmap, classmethod(lambda c: Smoother())
    try:
        assert _paint(9600, 6000) == ["drawImage"]  # no 9600 x 6000 copy, no background job
        assert REQUESTS == []
        assert _paint(4800, 3000, dpr=2.0) == ["drawImage"]  # device pixels count (HiDPI)
    finally:
        PW.QPainter, PW.QPixmap, PW._Smoother.get = old


if __name__ == "__main__":
    for k, fn in list(globals().items()):
        if k.startswith("test_"):
            fn()
            print("ok", k)
