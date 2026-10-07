# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Druckeranbindung unter Windows (pywin32).

Windows kennt keine PPD. Die Fähigkeiten eines Treibers stecken in zwei Teilen:
  * öffentlich (DeviceCapabilities): Papierformate, Fächer, Duplex, Farbe, Medientypen
    -> daraus baut Passermark die Basisfelder (alle Fächer immer wählbar)
  * privat (DEVMODE-Treiberdaten): alles Herstellerspezifische – Finisher, Heften, Lochen, Falzen,
    Beschnitt, Booklet, Stacker, Fiery-Optionen …
    -> erreichbar über den ORIGINAL-Treiberdialog des Herstellers (DocumentProperties).
       Passermark speichert das Ergebnis (Admin-Standard, Vorlage oder Sitzung) und setzt beim Druck
       nur die Basisfelder darüber.

Gedruckt wird über GDI: PDFium zeichnet jede ausgeschossene Seite direkt in den Drucker-Gerätekontext
(vektoriell; Rückfall: Rastern in Druckerauflösung).
"""
from __future__ import annotations

import base64
import json

from .l10n import tr
from .printers import Choice, Option, PrinterCaps, PrinterInfo, _assign_roles

DEVMODE_KEY = "__devmode__"

# GDI-Konstanten
DC_BINS, DC_PAPERS, DC_PAPERSIZE, DC_DUPLEX = 6, 2, 3, 7
DC_BINNAMES, DC_PAPERNAMES, DC_COLORDEVICE = 12, 16, 32
DC_MEDIATYPENAMES, DC_MEDIATYPES = 34, 35
DM_ORIENTATION, DM_PAPERSIZE, DM_COPIES, DM_DEFAULTSOURCE = 0x1, 0x2, 0x100, 0x200
DM_COLOR, DM_DUPLEX, DM_COLLATE, DM_MEDIATYPE = 0x800, 0x1000, 0x8000, 0x2000000
DM_OUT_BUFFER, DM_IN_PROMPT, DM_IN_BUFFER = 2, 4, 8
LOGPIXELSX, LOGPIXELSY, HORZRES, VERTRES = 88, 90, 8, 10
PHYSICALWIDTH, PHYSICALHEIGHT, PHYSICALOFFSETX, PHYSICALOFFSETY = 110, 111, 112, 113

PUBLIC_FIELDS = ("Orientation", "PaperSize", "PaperLength", "PaperWidth", "Scale", "Copies",
                 "DefaultSource", "PrintQuality", "Color", "Duplex", "YResolution", "TTOption",
                 "Collate", "MediaType", "DitherType", "Fields")


# --------------------------------------------------------------------------- #
# DEVMODE <-> Text (für Konfiguration und Sitzung)
# --------------------------------------------------------------------------- #
def devmode_to_str(dm) -> str:
    d = {f: getattr(dm, f) for f in PUBLIC_FIELDS if hasattr(dm, f)}
    d["DriverName"] = getattr(dm, "DeviceName", "")
    d["DriverData"] = base64.b64encode(bytes(dm.DriverData or b"")).decode()
    return base64.b64encode(json.dumps(d).encode()).decode()


def devmode_from_str(printer: str, s: str | None):
    """Neuen DEVMODE des Druckers holen und gespeicherte Werte darüberlegen."""
    import win32print
    h = win32print.OpenPrinter(printer)
    try:
        dm = win32print.GetPrinter(h, 2)["pDevMode"]
        if not s:
            return dm
        try:
            d = json.loads(base64.b64decode(s))
        except Exception:
            return dm
        for f in PUBLIC_FIELDS:
            if f in d:
                try:
                    setattr(dm, f, d[f])
                except Exception:
                    pass
        data = base64.b64decode(d.get("DriverData", "") or b"")
        # private Treiberdaten nur übernehmen, wenn sie zum selben Treiber/Format passen
        if data and len(data) == len(bytes(dm.DriverData or b"")):
            try:
                dm.DriverData = data
            except Exception:
                pass
        return dm
    finally:
        win32print.ClosePrinter(h)


def driver_dialog(hwnd: int, printer: str, current: str | None) -> str | None:
    """Original-Treiberdialog des Herstellers öffnen. Liefert neue Einstellungen oder None (Abbruch)."""
    import win32print
    h = win32print.OpenPrinter(printer)
    try:
        dm_in = devmode_from_str(printer, current)
        dm_out = win32print.GetPrinter(h, 2)["pDevMode"]
        r = win32print.DocumentProperties(hwnd, h, printer, dm_out, dm_in,
                                          DM_IN_PROMPT | DM_IN_BUFFER | DM_OUT_BUFFER)
        return devmode_to_str(dm_out) if r == 1 else None          # 1 = IDOK
    finally:
        win32print.ClosePrinter(h)


# --------------------------------------------------------------------------- #
# Drucker und Fähigkeiten
# --------------------------------------------------------------------------- #
def list_printers() -> list[PrinterInfo]:
    import win32print
    default = win32print.GetDefaultPrinter()
    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    out = []
    for p in win32print.EnumPrinters(flags, None, 2):
        name = p["pPrinterName"]
        status = p.get("Status", 0)
        out.append(PrinterInfo(name=name, info=name, location=p.get("pLocation") or "",
                               model=p.get("pDriverName") or "", state=5 if status & 0x1 else 3,
                               state_message=p.get("pComment") or "", is_default=(name == default),
                               uri="socket://" + (p.get("pPortName") or "").replace("IP_", "")))
    return sorted(out, key=lambda x: x.name.lower())


def _caps(printer, port, cap):
    import win32print
    try:
        r = win32print.DeviceCapabilities(printer, port, cap)
        return list(r) if r else []
    except Exception:
        return []


def load_caps(name: str) -> PrinterCaps:
    import win32print
    h = win32print.OpenPrinter(name)
    try:
        info = win32print.GetPrinter(h, 2)
    finally:
        win32print.ClosePrinter(h)
    port = info.get("pPortName") or ""
    dm = info["pDevMode"]
    caps = PrinterCaps(name=name, backend="win")

    def add(key, text, values, names, default):
        ch = [Choice(str(v), str(n).strip() or str(v)) for v, n in zip(values, names)]
        if ch:
            d = str(default) if str(default) in [c.value for c in ch] else ch[0].value
            caps.options[key] = Option(key, text, tr("Allgemein"), ch, d)

    papers, pnames = _caps(name, port, DC_PAPERS), _caps(name, port, DC_PAPERNAMES)
    sizes = _caps(name, port, DC_PAPERSIZE)
    add("PageSize", tr("Papierformat"), papers, pnames, getattr(dm, "PaperSize", ""))
    for pid, sz in zip(papers, sizes):
        x, y = (sz["x"], sz["y"]) if isinstance(sz, dict) else sz         # Zehntel-mm
        caps.page_sizes[str(pid)] = (x / 254.0 * 72.0, y / 254.0 * 72.0)
    add("InputSlot", tr("Papierzufuhr"), _caps(name, port, DC_BINS), _caps(name, port, DC_BINNAMES),
        getattr(dm, "DefaultSource", ""))
    try:
        duplex = win32print.DeviceCapabilities(name, port, DC_DUPLEX)
    except Exception:
        duplex = 0
    if duplex == 1:
        add("Duplex", tr("Beidseitig"), [1, 2, 3], [tr("Einseitig"), tr("Beidseitig, lange Kante"), tr("Beidseitig, kurze Kante")],
            getattr(dm, "Duplex", 1))
    try:
        color = win32print.DeviceCapabilities(name, port, DC_COLORDEVICE)
    except Exception:
        color = 0
    if color:
        add("ColorModel", tr("Farbmodus"), [2, 1], [tr("Farbe"), tr("Graustufen")], getattr(dm, "Color", 2))
    add("MediaType", tr("Medientyp"), _caps(name, port, DC_MEDIATYPES), _caps(name, port, DC_MEDIATYPENAMES),
        getattr(dm, "MediaType", ""))
    caps.groups.append(("win", tr("Allgemein"), list(caps.options)))
    caps._ppd = None
    caps.win_port = port
    _assign_roles(caps)
    return caps


def imageable_for(printer: str, values: dict):
    """Bedruckbarer Bereich (pt) für das gewählte Papier – vom Treiber erfragt."""
    import win32gui
    import win32print
    dm = _devmode_for_job(printer, values, 1, True)
    hdc = win32gui.CreateDC("WINSPOOL", printer, dm)
    try:
        dx, dy = win32print.GetDeviceCaps(hdc, LOGPIXELSX), win32print.GetDeviceCaps(hdc, LOGPIXELSY)
        ox, oy = win32print.GetDeviceCaps(hdc, PHYSICALOFFSETX), win32print.GetDeviceCaps(hdc, PHYSICALOFFSETY)
        hr, vr = win32print.GetDeviceCaps(hdc, HORZRES), win32print.GetDeviceCaps(hdc, VERTRES)
        pw, ph = win32print.GetDeviceCaps(hdc, PHYSICALWIDTH), win32print.GetDeviceCaps(hdc, PHYSICALHEIGHT)
    finally:
        win32gui.DeleteDC(hdc)
    k = 72.0 / dx, 72.0 / dy
    l, t = ox * k[0], oy * k[1]
    r, b = (ox + hr) * k[0], (oy + vr) * k[1]
    H = ph * k[1]
    return (l, H - b, r, H - t), (pw * k[0], ph * k[1])


# --------------------------------------------------------------------------- #
# Drucken
# --------------------------------------------------------------------------- #
def _devmode_for_job(printer: str, values: dict, copies: int, collate: bool):
    dm = devmode_from_str(printer, values.get(DEVMODE_KEY))
    fields = dm.Fields

    def setf(attr, val, flag):
        nonlocal fields
        try:
            setattr(dm, attr, int(val))
            fields |= flag
        except (TypeError, ValueError):
            pass
    if values.get("PageSize"):
        setf("PaperSize", values["PageSize"], DM_PAPERSIZE)
    if values.get("InputSlot"):
        setf("DefaultSource", values["InputSlot"], DM_DEFAULTSOURCE)
    if values.get("Duplex"):
        setf("Duplex", values["Duplex"], DM_DUPLEX)
    if values.get("ColorModel"):
        setf("Color", values["ColorModel"], DM_COLOR)
    if values.get("MediaType"):
        setf("MediaType", values["MediaType"], DM_MEDIATYPE)
    setf("Orientation", 1, DM_ORIENTATION)               # Blätter sind bereits physisch hochkant
    setf("Copies", max(1, copies), DM_COPIES)
    setf("Collate", 1 if collate else 0, DM_COLLATE)
    dm.Fields = fields
    return dm


# --------------------------------------------------------------------------- #
# Drucken (nur Windows)
# --------------------------------------------------------------------------- #
QUERYESCSUPPORT = 8
POSTSCRIPT_PASSTHROUGH = 4115
CHECKJPEGFORMAT = 4119
DIB_RGB_COLORS = 0
SRCCOPY = 0x00CC0020
BI_RGB, BI_JPEG = 0, 4
FPDF_PRINTMODE_EMF, FPDF_PRINTMODE_POSTSCRIPT3 = 0, 3
BAND_BYTES = 24 * 1024 * 1024          # Speicher je Rasterstreifen (konstant, unabhängig von Seitengröße/Auflösung)


def _gdi32():
    import ctypes
    return ctypes.windll.gdi32


class _BITMAPINFOHEADER(__import__("ctypes").Structure):
    import ctypes as _c
    _fields_ = [("biSize", _c.c_uint32), ("biWidth", _c.c_int32), ("biHeight", _c.c_int32),
                ("biPlanes", _c.c_uint16), ("biBitCount", _c.c_uint16), ("biCompression", _c.c_uint32),
                ("biSizeImage", _c.c_uint32), ("biXPelsPerMeter", _c.c_int32), ("biYPelsPerMeter", _c.c_int32),
                ("biClrUsed", _c.c_uint32), ("biClrImportant", _c.c_uint32)]


def _escape_supported(gdi, hdc, esc) -> bool:
    import ctypes
    v = ctypes.c_int(esc)
    try:
        return gdi.ExtEscape(hdc, QUERYESCSUPPORT, ctypes.sizeof(v), ctypes.byref(v), 0, None) > 0
    except Exception:
        return False


def _jpeg_ok(gdi, hdc, data: bytes) -> bool:
    import ctypes
    res = ctypes.c_uint32(0)
    try:
        return gdi.ExtEscape(hdc, CHECKJPEGFORMAT, len(data), data, ctypes.sizeof(res), ctypes.byref(res)) > 0 \
            and res.value == 1
    except Exception:
        return False


def print_settings() -> tuple[str, int]:
    """(Verfahren, Raster-dpi) aus Datei → Einstellungen (nur Windows)."""
    try:
        from .l10n import load_settings
        st = load_settings()
    except Exception:
        st = {}
    mode = st.get("win_print_mode", "auto")
    dpi = int(st.get("win_raster_dpi", 0) or 0)
    return (mode if mode in ("auto", "postscript", "raster", "vector") else "auto"), dpi


def choose_mode(gdi, hdc, wanted: str) -> str:
    if wanted != "auto":
        return wanted
    # PostScript-Treiber: pdfium schreibt PostScript direkt (vektoriell, kompakt) – sonst selbst rastern
    return "postscript" if _escape_supported(gdi, hdc, POSTSCRIPT_PASSTHROUGH) else "raster"


def _raster_page(gdi, hdc, page, w_pt, h_pt, dev_dpi, ox, oy, raster_dpi, use_jpeg):
    """Seite in waagrechten Streifen rastern und an den Treiber geben (BGR-DIB bzw. JPEG, wenn möglich)."""
    import ctypes
    import io as _io
    dpx, dpy = dev_dpi
    scale = raster_dpi / 72.0
    width_px = max(1, int(round(w_pt * scale)))
    rows_per_band = max(16, BAND_BYTES // (width_px * 3))
    band_pt = rows_per_band / scale
    y_pt = 0.0
    while y_pt < h_pt - 1e-6:
        y2 = min(h_pt, y_pt + band_pt)
        # Streifen [y_pt, y2] von oben gemessen rendern (crop = links, unten, rechts, oben in pt)
        img = page.render(scale=scale, crop=(0, h_pt - y2, 0, y_pt), may_draw_forms=True, draw_annots=True,
                          fill_color=(255, 255, 255, 255)).to_pil().convert("RGB")
        dy0 = int(round(y_pt * dpy / 72.0))
        dy1 = int(round(y2 * dpy / 72.0))
        dw = int(round(w_pt * dpx / 72.0))
        bih = _BITMAPINFOHEADER()
        bih.biSize, bih.biWidth, bih.biPlanes, bih.biBitCount = ctypes.sizeof(_BITMAPINFOHEADER), img.width, 1, 24
        data = None
        if use_jpeg:
            b = _io.BytesIO()
            img.save(b, "JPEG", quality=92, subsampling=0)
            jp = b.getvalue()
            if _jpeg_ok(gdi, hdc, jp):
                bih.biHeight, bih.biCompression, bih.biSizeImage = img.height, BI_JPEG, len(jp)
                data = jp
        if data is None:
            stride = (img.width * 3 + 3) & ~3
            data = img.tobytes("raw", "BGR", stride, -1)          # unten-oben (positive Höhe)
            bih.biHeight, bih.biCompression, bih.biSizeImage = img.height, BI_RGB, len(data)
        buf = ctypes.create_string_buffer(data, len(data))
        r = gdi.StretchDIBits(hdc, -ox, -oy + dy0, dw, dy1 - dy0, 0, 0, img.width, img.height,
                              buf, ctypes.byref(bih), DIB_RGB_COLORS, SRCCOPY)
        if r == 0 or r == -1:
            raise RuntimeError("StretchDIBits")
        y_pt = y2


def print_pdf(printer: str, pdf_path: str, title: str, values: dict, copies: int = 1, collate: bool = True) -> int:
    """Das fertig ausgeschossene PDF Seite für Seite an den Windows-Treiber geben.

    Verfahren (Datei → Einstellungen → Drucken unter Windows):
      auto       PostScript-Treiber -> postscript, sonst raster
      postscript pdfium erzeugt PostScript für den Treiber (vektoriell, kompakt; Canon PS3, Fiery …)
      raster     Seite selbst in Streifen rastern (konstanter Speicher; JPEG, wenn der Treiber es kann)
      vector     früheres Verfahren: pdfium zeichnet per GDI (kann bei Transparenz/Mehrfachnutzen sehr groß werden)
    """
    import ctypes

    import pypdfium2 as pdfium
    import pypdfium2.raw as r
    import win32gui
    import win32print

    gdi = _gdi32()
    wanted, dpi_setting = print_settings()
    dm = _devmode_for_job(printer, values, copies, collate)
    hdc = win32gui.CreateDC("WINSPOOL", printer, dm)
    doc = pdfium.PdfDocument(pdf_path)
    job = 0
    mode = "raster"
    set_mode = getattr(r, "FPDF_SetPrintMode", None)
    try:
        dpx, dpy = win32print.GetDeviceCaps(hdc, LOGPIXELSX), win32print.GetDeviceCaps(hdc, LOGPIXELSY)
        ox, oy = win32print.GetDeviceCaps(hdc, PHYSICALOFFSETX), win32print.GetDeviceCaps(hdc, PHYSICALOFFSETY)
        mode = choose_mode(gdi, hdc, wanted)
        if mode in ("postscript", "vector") and not hasattr(r, "FPDF_RenderPage"):
            mode = "raster"
        if mode == "postscript":
            if set_mode is None:
                mode = "raster"
            else:
                set_mode(getattr(r, "FPDF_PRINTMODE_POSTSCRIPT3", FPDF_PRINTMODE_POSTSCRIPT3))
        use_jpeg = mode == "raster" and _escape_supported(gdi, hdc, CHECKJPEGFORMAT)
        raster_dpi = dpi_setting or (600 if use_jpeg else 400)
        raster_dpi = max(150, min(raster_dpi, max(dpx, dpy)))
        job = win32print.StartDoc(hdc, (title[:120], None, None, 0))
        for i in range(len(doc)):
            win32print.StartPage(hdc)
            w, h = doc.get_page_size(i)
            page = doc[i]
            try:
                if mode == "raster":
                    _raster_page(gdi, hdc, page, w, h, (dpx, dpy), ox, oy, raster_dpi, use_jpeg)
                else:
                    sx, sy = int(round(w * dpx / 72.0)), int(round(h * dpy / 72.0))
                    r.FPDF_RenderPage(ctypes.c_void_p(hdc), page.raw, -ox, -oy, sx, sy, 0,
                                      r.FPDF_PRINTING | r.FPDF_ANNOT)
            finally:
                page.close()
            win32print.EndPage(hdc)
        win32print.EndDoc(hdc)
    except Exception:
        try:
            win32print.AbortDoc(hdc)
        except Exception:
            pass
        raise
    finally:
        if mode == "postscript" and set_mode is not None:
            try:
                set_mode(getattr(r, "FPDF_PRINTMODE_EMF", FPDF_PRINTMODE_EMF))
            except Exception:
                pass
        doc.close()
        win32gui.DeleteDC(hdc)
    return int(job or 0)


def set_printer_default(printer: str, devmode_str: str):
    """Treibereinstellungen als Windows-Standard des Druckers setzen (braucht Adminrechte)."""
    import win32print
    h = win32print.OpenPrinter(printer, {"DesiredAccess": win32print.PRINTER_ALL_ACCESS})
    try:
        info = win32print.GetPrinter(h, 2)
        info["pDevMode"] = devmode_from_str(printer, devmode_str)
        win32print.SetPrinter(h, 2, info, 0)
    finally:
        win32print.ClosePrinter(h)
