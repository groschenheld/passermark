# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Render-Prozess der Seitenansicht (passermark-cli render-server): Öffnen, ganze Seite, Ausschnitt (auch
    gedreht, pixelgleich zum Ausschnitt der ganzen Seite), Fehler ohne Absturz, Datei bleibt frei."""
import io
import json
import os
import subprocess
import sys
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pdfdruck.jobproc import cli_command


def _pdf(path):
    import numpy as np
    import pikepdf
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(300, 200))
    y, x = np.mgrid[0:200, 0:300]
    a = np.stack([x % 256, y % 256, (x + y) % 256], 2).astype("uint8")
    img = pikepdf.Stream(pdf, a.tobytes(), Type=pikepdf.Name.XObject, Subtype=pikepdf.Name.Image, Width=300,
                         Height=200, ColorSpace=pikepdf.Name.DeviceRGB, BitsPerComponent=8)
    pdf.pages[0].obj.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im=img))
    pdf.pages[0].obj.Contents = pikepdf.Stream(pdf, b"q 300 0 0 200 0 0 cm /Im Do Q 1 0 0 rg 20 20 40 40 re f")
    pdf.save(path)


class Server:
    def __init__(self):
        cmd, env = cli_command()
        self.p = subprocess.Popen(cmd + ["render-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  env=dict(os.environ, **env))

    def __call__(self, **req):
        self.p.stdin.write(json.dumps(req).encode() + b"\n")
        self.p.stdin.flush()
        head = json.loads(self.p.stdout.readline())
        data = self.p.stdout.read(head["n"]) if head["n"] else b""
        return head, data

    def close(self):
        self.p.stdin.write(b'{"op": "quit"}\n')
        self.p.stdin.flush()
        return self.p.wait(20)


def _arr(head, data):
    import numpy as np
    a = np.frombuffer(data, np.uint8).reshape(head["h"], head["stride"])
    return a[:, :head["w"] * 4].reshape(head["h"], head["w"], 4)[:, :, :3].astype(int)


def test_render_server():
    import numpy as np
    d = tempfile.mkdtemp()
    path = os.path.join(d, "a.pdf")
    _pdf(path)
    s = Server()
    try:
        h, _ = s(op="open", id=1, doc="x", path=path)
        assert h["ok"] and h["pages"] == 1
        os.replace(path, path + ".alt")                  # Datei ist frei (im Speicher) – Speichern darüber geht
        for rot in (0, 90):
            h, data = s(op="render", id=2, doc="x", page=0, scale=2.0, rotation=rot)
            assert h["ok"] and h["fmt"] == "bgrx", h
            full = _arr(h, data)
            H, W = full.shape[:2]
            x0, y0, x1, y1 = 30, 20, 130, 90
            h2, d2 = s(op="render", id=3, doc="x", page=0, scale=2.0, rotation=rot,
                       crop=[x0 / 2, (H - y1) / 2, (W - x1) / 2, y0 / 2])
            part = _arr(h2, d2)
            assert part.shape[:2] == (y1 - y0, x1 - x0), part.shape
            assert np.abs(part - full[y0:y1, x0:x1]).mean() < 1.0, rot
        h, _ = s(op="render", id=4, doc="x", page=5, scale=1.0)
        assert not h["ok"] and h["error"]                 # Fehler zurück, Server läuft weiter
        h, _ = s(op="render", id=5, doc="gibtsnicht", page=0, scale=1.0)
        assert not h["ok"]
        h, _ = s(op="close", id=6, doc="x")
        assert h["ok"]
    finally:
        assert s.close() == 0


if __name__ == "__main__":
    test_render_server()
    print("ok test_render_server")
