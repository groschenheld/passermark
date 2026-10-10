"""Nachgebaute Windows-Druckschnittstellen (win32gui/win32print/gdi32) – zeichnen auf eine Leinwand."""
import ctypes, io, sys, types
from PIL import Image

class FakeGDI:
    def __init__(self, dpi=600, ps=False, jpeg=False, page_px=None):
        self.dpi, self.ps, self.jpeg = dpi, ps, jpeg
        self.calls, self.bytes_sent, self.pages = [], 0, []
        self.canvas = None
    def ExtEscape(self, hdc, esc, n, inp, nout, out):
        if esc == 8:
            q = ctypes.cast(inp, ctypes.POINTER(ctypes.c_int)).contents.value
            return 1 if (q == 4115 and self.ps) or (q == 4119 and self.jpeg) else 0
        if esc == 4119:
            if out: ctypes.cast(out, ctypes.POINTER(ctypes.c_uint32)).contents.value = 1 if self.jpeg else 0
            return 1
        return 0
    def StretchDIBits(self, hdc, xd, yd, wd, hd, xs, ys, ws, hs, bits, bmi, usage, rop):
        bih = ctypes.cast(bmi, ctypes.POINTER(__import__("pdfdruck.printers_win", fromlist=["x"])._BITMAPINFOHEADER)).contents
        raw = ctypes.string_at(bits, bih.biSizeImage)
        self.bytes_sent += len(raw)
        if bih.biCompression == 4:
            img = Image.open(io.BytesIO(raw)).convert("RGB")
        else:
            stride = (bih.biWidth * 3 + 3) & ~3
            img = Image.frombytes("RGB", (bih.biWidth, abs(bih.biHeight)), raw, "raw", "BGR", stride, -1 if bih.biHeight > 0 else 1)
        self.calls.append(("band", yd, hd, bih.biCompression))
        if self.canvas is not None:
            self.canvas.paste(img.resize((wd, hd)), (xd, yd))
        return hd

def install(gdi, page_size_dev):
    w32g = types.ModuleType("win32gui"); w32p = types.ModuleType("win32print")
    w32g.CreateDC = lambda *a: 1234
    w32g.DeleteDC = lambda h: None
    w32p.GetDeviceCaps = lambda h, i: {88: gdi.dpi, 90: gdi.dpi, 112: 0, 113: 0}.get(i, 0)
    def start_page(h):
        gdi.canvas = Image.new("RGB", page_size_dev, (200, 200, 200))
    def end_page(h):
        gdi.pages.append(gdi.canvas)
    w32p.StartDoc = lambda h, info: 42; w32p.EndDoc = lambda h: None; w32p.AbortDoc = lambda h: gdi.calls.append(("abort",))
    w32p.StartPage = start_page; w32p.EndPage = end_page
    sys.modules["win32gui"] = w32g; sys.modules["win32print"] = w32p
