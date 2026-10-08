# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Erzeugt windows/passermark.ico aus dem SVG-Icon (beim Bauen)."""
import io
import os
import sys

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

here = os.path.dirname(os.path.abspath(__file__))
svg = os.path.join(here, "..", "data", "passermark.svg")
app = QGuiApplication(sys.argv[:1])
r = QSvgRenderer(svg)
frames = []
for size in (16, 24, 32, 48, 64, 128, 256):
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r.render(p)
    p.end()
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    frames.append(Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA"))
frames[-1].save(os.path.join(here, "passermark.ico"), sizes=[f.size for f in frames])
print("passermark.ico erzeugt")
