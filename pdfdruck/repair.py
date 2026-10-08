# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""PDF reparieren und für die Weitergabe optimieren.

Modi:
  repair  – nur Struktur reparieren (qpdf/pikepdf): Querverweise, Objektströme, Metadaten.
            Inhalt bleibt Byte-für-Byte gleich – das Mittel bei „Datei ist beschädigt“.
  print   – mit Ghostscript neu schreiben: alle Schriften eingebettet, PDF 1.7, Bilder in Druckqualität.
            Behebt die meisten „öffnet im Browser, aber nicht in Acrobat / druckt nicht“-Fälle.
  screen  – wie print, Bilder auf 150 dpi – kleine Dateien für Mail und Bildschirm.
  pdfa    – PDF/A-2b (Archiv, Behörden, E-Rechnungs-Anhänge): Schriften eingebettet, sRGB-OutputIntent.

Passwort: Eingabe-Passwort zum Öffnen geschützter Dateien; optional neues Passwort (AES-256) für die
Ausgabe. Ohne neues Passwort wird die Ausgabe ungeschützt gespeichert.
"""
from __future__ import annotations

from .l10n import tr

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

MODES = {
    "repair": "Nur reparieren (Inhalt unverändert)",
    "print": "Für Weitergabe und Druck optimieren (Schriften einbetten)",
    "screen": "Für Mail/Bildschirm verkleinern (150 dpi)",
    "pdfa": "PDF/A-2b – Archiv, Behörden",
}
SUFFIX = {"repair": "_repariert", "print": "_optimiert", "screen": "_klein", "pdfa": "_PDFA"}


class PasswordRequired(Exception):
    """Datei ist verschlüsselt und das (richtige) Passwort fehlt."""


@dataclass
class Result:
    src: str
    dst: str
    pages_in: int
    pages_out: int
    size_in: int
    size_out: int
    notes: list

    @property
    def ok(self) -> bool:
        return self.pages_out == self.pages_in and self.pages_out > 0


def default_output(src: str, mode: str) -> str:
    base, _ = os.path.splitext(src)
    return base + SUFFIX.get(mode, "_neu") + ".pdf"


def needs_password(path: str) -> bool:
    import pikepdf
    try:
        pikepdf.open(path).close()
        return False
    except pikepdf.PasswordError:
        return True
    except Exception:
        return False


def _open(path: str, password: str | None):
    import pikepdf
    try:
        return pikepdf.open(path, password=password or "", attempt_recovery=True)
    except pikepdf.PasswordError:
        raise PasswordRequired(os.path.basename(path))


def _pages(path: str, password: str | None = None) -> int:
    try:
        pdf = _open(path, password)
    except PasswordRequired:
        raise
    except Exception:
        return 0
    try:
        return len(pdf.pages)
    finally:
        pdf.close()


def _gs():
    from . import platform as _platform
    gs = _platform.ghostscript()
    if not gs:
        raise RuntimeError(tr("Ghostscript (gs) ist nicht installiert."))
    return gs


def _srgb_icc(tmp: str) -> str:
    from PIL import ImageCms
    p = os.path.join(tmp, "sRGB.icc")
    with open(p, "wb") as f:
        f.write(ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes())
    return p


def _pdfa_def(tmp: str, icc: str) -> str:
    """OutputIntent-Definition für Ghostscript (entspricht Ghostscripts PDFA_def.ps)."""
    p = os.path.join(tmp, "PDFA_def.ps")
    esc = icc.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    with open(p, "w") as f:
        f.write(f"""%!
/ICCProfile ({esc}) def
[/_objdef {{icc_PDFA}} /type /stream /OBJ pdfmark
[{{icc_PDFA}} << /N 3 >> /PUT pdfmark
[{{icc_PDFA}} ICCProfile (r) file /PUT pdfmark
[/_objdef {{OutputIntent_PDFA}} /type /dict /OBJ pdfmark
[{{OutputIntent_PDFA}} <<
  /Type /OutputIntent /S /GTS_PDFA1 /DestOutputProfile {{icc_PDFA}}
  /OutputConditionIdentifier (sRGB IEC61966-2.1) /Info (sRGB IEC61966-2.1)
>> /PUT pdfmark
[{{Catalog}} << /OutputIntents [ {{OutputIntent_PDFA}} ] >> /PUT pdfmark
""")
    return p


def _ghostscript(src: str, dst: str, mode: str, password: str | None, tmp: str):
    cmd = [_gs(), "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=pdfwrite",
           "-dEmbedAllFonts=true", "-dSubsetFonts=true", "-dAutoRotatePages=/None",
           "-dDetectDuplicateImages=true", "-dCompressFonts=true"]
    if password:
        cmd.append(f"-sPDFPassword={password}")
    if mode == "screen":
        cmd += ["-dPDFSETTINGS=/ebook", "-dCompatibilityLevel=1.7"]
    elif mode == "pdfa":
        icc = _srgb_icc(tmp)
        cmd += ["-dPDFA=2", "-dPDFACompatibilityPolicy=1", "-dCompatibilityLevel=1.7",
                "-sColorConversionStrategy=RGB", "-sProcessColorModel=DeviceRGB",
                f"--permit-file-read={tmp}/", f"-sOutputICCProfile={icc}",
                "-dPDFSETTINGS=/prepress"]
        cmd += ["-o", dst, _pdfa_def(tmp, icc), src]
        return _run(cmd)
    else:
        cmd += ["-dPDFSETTINGS=/prepress", "-dCompatibilityLevel=1.7"]
    cmd += ["-o", dst, src]
    _run(cmd)


def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if r.returncode != 0 or not os.path.exists(cmd[cmd.index("-o") + 1]):
        raise RuntimeError((r.stderr or r.stdout or "Ghostscript-Fehler")[-1500:])


def _pike_save(src: str, dst: str, password: str | None, new_password: str | None,
               allow_print: bool = True, pdfa: bool = False):
    import pikepdf
    pdf = _open(src, password)
    try:
        enc = None
        if new_password and not pdfa:            # PDF/A verbietet Verschlüsselung
            perms = pikepdf.Permissions(print_lowres=allow_print, print_highres=allow_print,
                                        extract=True, modify_annotation=True, modify_form=True,
                                        modify_other=True, modify_assembly=True, accessibility=True)
            enc = pikepdf.Encryption(owner=new_password, user=new_password, R=6, allow=perms)
        pdf.remove_unreferenced_resources()
        pdf.save(dst, encryption=enc if enc else False, object_stream_mode=pikepdf.ObjectStreamMode.generate,
                 fix_metadata_version=True, linearize=not enc)
    finally:
        pdf.close()


def encrypt_file(src: str, dst: str, password: str, allow_print: bool = True) -> None:
    """Fertige PDF mit Passwort (AES-256) schützen – zum Öffnen und Bearbeiten dasselbe Passwort."""
    if not password:
        raise ValueError(tr("Bitte ein Passwort eingeben."))
    _pike_save(src, dst, None, password, allow_print=allow_print)


def process(src: str, dst: str, mode: str = "print", password: str | None = None,
            new_password: str | None = None, allow_print: bool = True) -> Result:
    """Verarbeitet eine Datei. Wirft PasswordRequired, wenn ein Passwort nötig/falsch ist."""
    if os.path.abspath(src) == os.path.abspath(dst):
        raise ValueError(tr("Ziel darf nicht die Quelldatei sein."))
    notes = []
    pages_in = _pages(src, password)          # wirft PasswordRequired
    tmp = tempfile.mkdtemp(prefix="passermark-rep-")
    try:
        # 1) immer zuerst die Struktur reparieren und entschlüsseln -> sauberer Zwischenstand
        clean = os.path.join(tmp, "clean.pdf")
        try:
            _pike_save(src, clean, password, None)
        except PasswordRequired:
            raise
        except Exception as e:                # extrem kaputt: Ghostscript direkt versuchen
            notes.append(tr("Strukturreparatur nicht möglich ({0}) – Neuaufbau direkt.").format(e.__class__.__name__))
            clean = src
        if mode == "repair":
            stage = clean
        else:
            stage = os.path.join(tmp, "gs.pdf")
            _ghostscript(clean, stage, mode, password if clean == src else None, tmp)
        # 2) abschließend speichern (ggf. verschlüsseln, linearisieren für schnelles Öffnen im Web)
        _pike_save(stage, dst, None, new_password, allow_print, pdfa=(mode == "pdfa"))
        if new_password and mode == "pdfa":
            notes.append(tr("PDF/A erlaubt keine Verschlüsselung – Passwort wurde nicht gesetzt."))
        pages_out = _pages(dst, new_password if mode != "pdfa" else None)
        if pages_in == 0:
            notes.append(tr("Seitenzahl der Quelle nicht ermittelbar (Datei stark beschädigt)."))
            pages_in = pages_out
        if pages_out != pages_in:
            notes.append(tr("Achtung: {0} Seiten in der Quelle, {1} im Ergebnis.").format(pages_in, pages_out))
        return Result(src, dst, pages_in, pages_out, os.path.getsize(src), os.path.getsize(dst), notes)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
