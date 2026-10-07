# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Beliebige Dateien -> PDF: PDF direkt, Bilder über img2pdf, Office über LibreOffice,
OnlyOffice oder Euro-Office.

* LibreOffice: offizielle Kopfmodus-Umwandlung (soffice --convert-to pdf), läuft mit EIGENEM Profil,
  damit es auch geht, wenn gerade ein LibreOffice-Fenster offen ist.
* OnlyOffice / Euro-Office (Fork von OnlyOffice): kein dokumentierter Kommandozeilenbefehl der
  Desktop-Editoren – verwendet wird deren mitgelieferter Konverter „x2t“. Meist originalgetreuer bei
  docx/xlsx/pptx, aber nicht offiziell als Schnittstelle zugesichert -> automatischer Rückfall.
"""
from __future__ import annotations

from .l10n import tr

import glob
import os
import shutil
import subprocess
import tempfile

from . import images
from . import platform as _platform

OFFICE_EXT = {
    ".doc", ".docx", ".docm", ".dot", ".dotx", ".odt", ".ott", ".rtf", ".txt", ".wpd",
    ".xls", ".xlsx", ".xlsm", ".ods", ".csv",
    ".ppt", ".pptx", ".pps", ".ppsx", ".odp",
    ".odg", ".vsd", ".vsdx", ".pub", ".html", ".htm", ".xps", ".epub", ".djvu",
}
OOXML_EXT = {".docx", ".docm", ".dotx", ".xlsx", ".xlsm", ".pptx", ".ppsx", ".doc", ".xls", ".ppt"}
X2T_EXT = {".doc", ".docx", ".docm", ".dotx", ".odt", ".rtf", ".txt", ".xls", ".xlsx", ".xlsm",
           ".ods", ".csv", ".ppt", ".pptx", ".ppsx", ".odp", ".html", ".htm", ".epub", ".xps", ".djvu"}
PDF_EXT = {".pdf"}

CONVERTERS = {
    "auto": "Automatisch (Word/Excel/PowerPoint: Microsoft Office bzw. Euro-Office/OnlyOffice, sonst LibreOffice)",
    "libreoffice": "LibreOffice",
    "onlyoffice": "OnlyOffice Desktop Editors",
    "eurooffice": "Euro-Office Desktop",
    "msoffice": "Microsoft Office (nur Windows)",
}
MSO_EXT = {".doc", ".docx", ".docm", ".dot", ".dotx", ".rtf", ".txt", ".odt", ".xls", ".xlsx", ".xlsm",
           ".ods", ".csv", ".ppt", ".pptx", ".pps", ".ppsx", ".odp", ".htm", ".html"}
X2T_PDF = 513        # AVS_OFFICESTUDIO_FILE_CROSSPLATFORM_PDF


def ext(path: str) -> str:
    return os.path.splitext(path)[1].lower()


def is_office(path: str) -> bool:
    return ext(path) in OFFICE_EXT


def is_supported(path: str) -> bool:
    return ext(path) in PDF_EXT or images.is_image(path) or is_office(path)


# ---------------------------------------------------------------------- #
# Erkennen, was installiert ist
# ---------------------------------------------------------------------- #
def _x2t_candidates():
    if _platform.IS_WIN:
        roots = filter(None, (os.environ.get(v) for v in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")))
        out = []
        for r in roots:
            for pat in (r"*\DesktopEditors\converter\x2t.exe", r"*\*\DesktopEditors\converter\x2t.exe",
                        r"*\converter\x2t.exe", r"*\*\converter\x2t.exe"):
                for hit in glob.glob(os.path.join(r, pat)):
                    if hit not in [h for h, _ in out]:
                        out.append((hit, hit))
        return out
    pats = ["/opt/*/desktopeditors/converter/x2t", "/opt/*/converter/x2t", "/opt/*/*/converter/x2t",
            "/usr/lib/*/desktopeditors/converter/x2t", "/usr/share/*/converter/x2t",
            "/snap/*/current/opt/*/desktopeditors/converter/x2t",
            "/var/lib/flatpak/app/*/current/active/files/*/desktopeditors/converter/x2t",
            "/var/lib/flatpak/app/*/current/active/files/*/*/converter/x2t",
            os.path.expanduser("~/.local/share/flatpak/app/*/current/active/files/*/*/converter/x2t")]
    seen, out = set(), []
    for p in pats:
        for hit in glob.glob(p):
            real = os.path.realpath(hit)
            if os.access(real, os.X_OK) and real not in seen:
                seen.add(real)
                out.append((hit, real))
    return out


def detect() -> dict[str, str]:
    """{"libreoffice": pfad, "onlyoffice": x2t, "eurooffice": x2t} – nur was gefunden wurde."""
    found = {}
    lo = _platform.find_program(["soffice", "libreoffice"], [r"LibreOffice\program\soffice.exe"])
    if _platform.IS_WIN and _msoffice_available():
        found["msoffice"] = "com"
    if lo:
        found["libreoffice"] = lo
    elif shutil.which("flatpak") and subprocess.run(["flatpak", "info", "org.libreoffice.LibreOffice"],
                                                    capture_output=True).returncode == 0:
        found["libreoffice"] = "flatpak:org.libreoffice.LibreOffice"
    for hit, real in _x2t_candidates():
        low = (hit + " " + real).lower().replace("-", "").replace("_", "")
        key = "eurooffice" if "eurooffice" in low else "onlyoffice" if "onlyoffice" in low else None
        if key and key not in found:
            found[key] = real
    return found


def _msoffice_available() -> bool:
    try:
        import winreg
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Word.Application"))
        return True
    except Exception:
        return False


def describe_available() -> str:
    d = detect()
    if not d:
        return tr("Kein Office-Konverter gefunden.")
    names = ("msoffice", "libreoffice", "eurooffice", "onlyoffice")
    return tr("Gefunden: ") + ", ".join(tr(CONVERTERS[k]).split(" (")[0] for k in names if k in d)


# ---------------------------------------------------------------------- #
# Umwandeln
# ---------------------------------------------------------------------- #
def _sandboxed(exe: str) -> bool:
    """Snap/Flatpak sehen unser /tmp nicht (eigenes, abgeschottetes /tmp)."""
    return exe.startswith("flatpak:") or "/snap/" in exe or "/snap/" in os.path.realpath(exe)


def _libreoffice(exe: str, path: str, outdir: str, timeout: int) -> str:
    from pathlib import Path
    profile = Path(tempfile.gettempdir(), f"passermark-lo-{_platform.user_id()}").as_uri()
    base = os.path.splitext(os.path.basename(path))[0]
    work, src = outdir, path
    if _sandboxed(exe):
        # sichtbarer Ordner im Home – den darf ein Snap/Flatpak lesen und beschreiben
        root = os.path.join(os.path.expanduser("~"), "Passermark-Umwandlung")
        os.makedirs(root, exist_ok=True)
        work = tempfile.mkdtemp(prefix="lo-", dir=root)
        src = os.path.join(work, "in" + ext(path))
        shutil.copy2(path, src)
        base = "in"
    launcher = ["flatpak", "run", exe.split(":", 1)[1]] if exe.startswith("flatpak:") else [exe]
    cmd = launcher + [f"-env:UserInstallation={profile}", "--headless", "--norestore",
                      "--nolockcheck", "--convert-to", "pdf", "--outdir", work, src]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **_platform.hidden_subprocess_kwargs())
        produced = os.path.join(work, base + ".pdf")
        if not os.path.exists(produced):
            hint = tr(" (LibreOffice als Snap/Flatpak? Dann darf es nicht in /tmp schreiben.)") \
                if "convert" in (r.stdout or "") else ""
            raise RuntimeError(((r.stderr or r.stdout or "keine Ausgabe").strip().splitlines() or ["?"])[-1] + hint)
        out = os.path.join(outdir, os.path.splitext(os.path.basename(path))[0] + ".pdf")
        if produced != out:
            shutil.move(produced, out)
        return out
    finally:
        if work != outdir:
            shutil.rmtree(work, ignore_errors=True)
            try:
                os.rmdir(os.path.dirname(work))      # leeren Sammelordner wieder entfernen
            except OSError:
                pass


def _fonts_ready(d: str) -> bool:
    return os.path.isfile(os.path.join(d, "AllFonts.js")) and os.path.isfile(os.path.join(d, "font_selection.bin"))


def _x2t_fonts(exe: str) -> str:
    """Ordner mit AllFonts.js + font_selection.bin für x2t (vorhanden, zwischengespeichert oder neu erzeugt)."""
    import hashlib
    home = os.path.expanduser("~")
    if _platform.IS_WIN:
        appdata = os.environ.get("LOCALAPPDATA", home)
        for hit in glob.glob(os.path.join(appdata, "*", "*", "data", "fonts", "AllFonts.js")) + \
                glob.glob(os.path.join(appdata, "*", "*", "*", "data", "fonts", "AllFonts.js")):
            if _fonts_ready(os.path.dirname(hit)):
                return os.path.dirname(hit)
    # 1) Schriftencache, den die Desktop-Editoren selbst angelegt haben
    pats = [home + "/.local/share/onlyoffice/**/AllFonts.js", home + "/.local/share/*euro*office*/**/AllFonts.js",
            home + "/.local/share/*Euro*Office*/**/AllFonts.js", home + "/snap/*/*/.local/share/*/**/AllFonts.js",
            home + "/.var/app/*/data/**/AllFonts.js"]
    for pat in pats:
        for hit in glob.glob(pat, recursive=True):
            if _fonts_ready(os.path.dirname(hit)):
                return os.path.dirname(hit)
    # 2) eigener Cache, einmalig mit allfontsgen erzeugt
    conv = os.path.dirname(exe)
    cache = os.path.join(_platform.user_cache_dir(), "x2t-fonts", hashlib.sha1(conv.encode()).hexdigest()[:10])
    if _fonts_ready(cache):
        return cache
    exe_ext = ".exe" if _platform.IS_WIN else ""
    gen = next((g for g in (os.path.join(conv, "allfontsgen" + exe_ext),
                            os.path.join(os.path.dirname(conv), "allfontsgen" + exe_ext),
                            os.path.join(os.path.dirname(conv), "tools", "allfontsgen" + exe_ext))
                if os.path.isfile(g) and os.access(g, os.X_OK)), None)
    if not gen:
        raise RuntimeError(tr("Schriftenverzeichnis fehlt und allfontsgen wurde nicht gefunden – "
                           "die Desktop-Editoren einmal starten, dann erneut versuchen."))
    os.makedirs(cache, exist_ok=True)
    sysfonts = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
                os.path.join(os.environ.get("LOCALAPPDATA", home), "Microsoft", "Windows", "Fonts")] \
        if _platform.IS_WIN else ["/usr/share/fonts", "/usr/local/share/fonts", home + "/.local/share/fonts", home + "/.fonts"]
    inputs = [d for d in sysfonts + [os.path.join(os.path.dirname(conv), "fonts")] if os.path.isdir(d)]
    cmd = [gen] + [f"--input={d}" for d in inputs] + [
        f"--allfonts={cache}/AllFonts.js", f"--selection={cache}/font_selection.bin",
        f"--allfonts-web={cache}/AllFonts-web.js", f"--output-web={cache}/web", "--use-system=true"]
    os.makedirs(os.path.join(cache, "web"), exist_ok=True)
    subprocess.run(cmd, capture_output=True, timeout=600, cwd=conv, env=_lib_env(conv),
                   **_platform.hidden_subprocess_kwargs())
    if not _fonts_ready(cache):
        raise RuntimeError(tr("Schriftenverzeichnis konnte nicht erzeugt werden (allfontsgen)."))
    return cache


def _lib_env(conv: str) -> dict:
    """Bibliothekspfad für die Konverter-Programme (Linux: LD_LIBRARY_PATH, Windows: PATH)."""
    var, sep = ("PATH", ";") if _platform.IS_WIN else ("LD_LIBRARY_PATH", ":")
    val = conv + sep + os.path.dirname(conv)
    if os.environ.get(var):
        val += sep + os.environ[var]
    return {**os.environ, var: val}


def _x2t(exe: str, path: str, outdir: str, timeout: int) -> str:
    from xml.sax.saxutils import escape
    out = os.path.join(outdir, os.path.splitext(os.path.basename(path))[0] + ".pdf")
    conv_dir = os.path.dirname(exe)
    fonts = _x2t_fonts(exe)
    params = os.path.join(outdir, "x2t-params.xml")
    with open(params, "w", encoding="utf-8") as f:
        f.write(f"""<?xml version="1.0" encoding="utf-8"?>
<TaskQueueDataConvert xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <m_sFileFrom>{escape(path)}</m_sFileFrom>
  <m_sFileTo>{escape(out)}</m_sFileTo>
  <m_nFormatTo>{X2T_PDF}</m_nFormatTo>
  <m_sFontDir>{escape(os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts") if _platform.IS_WIN else "/usr/share/fonts")}</m_sFontDir>
  <m_sAllFontsPath>{escape(os.path.join(fonts, "AllFonts.js"))}</m_sAllFontsPath>
  <m_sTempDir>{escape(outdir)}</m_sTempDir>
  <m_bIsNoBase64>true</m_bIsNoBase64>
</TaskQueueDataConvert>
""")
    r = subprocess.run([exe, params], capture_output=True, text=True, timeout=timeout, cwd=conv_dir,
                       env=_lib_env(conv_dir), **_platform.hidden_subprocess_kwargs())
    if not os.path.exists(out) or os.path.getsize(out) < 100:
        detail = (r.stderr or r.stdout or "").strip()
        first = next((l for l in detail.splitlines() if "error" in l.lower()), detail.splitlines()[0] if detail else "")
        raise RuntimeError(tr("Konverter-Code {0}").format(r.returncode) + (f" – {first[:160]}" if first else ""))
    return out


def _msoffice(path: str, outdir: str, timeout: int) -> str:
    """Word/Excel/PowerPoint per COM fernsteuern (nur Windows, unsichtbar, schreibgeschützt geöffnet)."""
    import pythoncom
    import win32com.client
    out = os.path.join(outdir, os.path.splitext(os.path.basename(path))[0] + ".pdf")
    src = os.path.abspath(path)
    e = ext(path)
    pythoncom.CoInitialize()
    try:
        if e in (".xls", ".xlsx", ".xlsm", ".ods", ".csv"):
            app = win32com.client.DispatchEx("Excel.Application")
            app.DisplayAlerts = False
            try:
                wb = app.Workbooks.Open(src, ReadOnly=True)
                wb.ExportAsFixedFormat(0, out)                 # 0 = xlTypePDF
                wb.Close(False)
            finally:
                app.Quit()
        elif e in (".ppt", ".pptx", ".pps", ".ppsx", ".odp"):
            app = win32com.client.DispatchEx("PowerPoint.Application")
            try:
                pres = app.Presentations.Open(src, ReadOnly=True, WithWindow=False)
                pres.SaveAs(out, 32)                           # 32 = ppSaveAsPDF
                pres.Close()
            finally:
                app.Quit()
        else:
            app = win32com.client.DispatchEx("Word.Application")
            app.Visible = False
            app.DisplayAlerts = 0
            try:
                doc = app.Documents.Open(src, ReadOnly=True, AddToRecentFiles=False, ConfirmConversions=False)
                doc.ExportAsFixedFormat(out, 17)               # 17 = wdExportFormatPDF
                doc.Close(False)
            finally:
                app.Quit()
    finally:
        pythoncom.CoUninitialize()
    if not os.path.exists(out):
        raise RuntimeError(tr("Microsoft Office hat keine PDF erzeugt."))
    return out


def conversion_order(path: str, preference: str, available: dict) -> list[str]:
    e = ext(path)
    if preference in ("libreoffice", "onlyoffice", "eurooffice", "msoffice"):
        order = [preference, "libreoffice", "eurooffice", "onlyoffice", "msoffice"]
    elif e in OOXML_EXT:                     # Microsoft-Formate: MS Office, dann OnlyOffice-Familie
        order = ["msoffice", "eurooffice", "onlyoffice", "libreoffice"]
    else:                                    # ODF & Rest: LibreOffice zuerst
        order = ["libreoffice", "eurooffice", "onlyoffice", "msoffice"]
    seen, out = set(), []
    for k in order:
        ok_ext = (k == "libreoffice") or (k == "msoffice" and e in MSO_EXT) or \
            (k in ("eurooffice", "onlyoffice") and e in X2T_EXT)
        if k in available and k not in seen and ok_ext:
            seen.add(k)
            out.append(k)
    return out


def office_to_pdf(path: str, outdir: str, preference: str = "auto", timeout: int = 300) -> tuple[str, str]:
    """Office-Datei -> PDF. Liefert (pdf_pfad, verwendeter_konverter). Fällt automatisch zurück."""
    available = detect()
    order = conversion_order(path, preference, available)
    if not order:
        raise RuntimeError(tr("Für Office-Dateien wird LibreOffice, OnlyOffice, Euro-Office")
                           + (tr(" oder Microsoft Office benötigt.") if _platform.IS_WIN else
                              tr(" benötigt, z. B.:\nsudo apt install libreoffice-writer libreoffice-calc libreoffice-impress")))
    errors = []
    for key in order:
        work = tempfile.mkdtemp(prefix=f"{key}-", dir=outdir)
        try:
            if key == "libreoffice":
                return _libreoffice(available[key], path, work, timeout), CONVERTERS[key]
            if key == "msoffice":
                return _msoffice(path, work, timeout), "Microsoft Office"
            return _x2t(available[key], path, work, timeout), CONVERTERS[key]
        except Exception as e:
            errors.append(f"{CONVERTERS[key]}: {e}")
    raise RuntimeError(tr("„{0}“ konnte nicht umgewandelt werden.\n").format(os.path.basename(path)) + "\n".join(errors))


def to_document(path: str, workdir: str, image_dpi: float = 96.0, password: str | None = None,
                preference: str = "auto"):
    """Beliebige unterstützte Datei -> (pypdfium2-Dokument, verwendeter Konverter oder "")."""
    import pypdfium2 as pdfium
    if images.is_image(path):
        return images.images_to_document([path], image_dpi), ""
    if is_office(path):
        pdf, used = office_to_pdf(path, workdir, preference)
        return pdfium.PdfDocument(pdf), used
    return pdfium.PdfDocument(path, password=password), ""
