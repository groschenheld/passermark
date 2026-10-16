# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Dateigröße: zeigen, wofür der Platz draufgeht, und gezielt verkleinern – jede Maßnahme einzeln
schaltbar. Ohne Ghostscript (pikepdf + Pillow + numpy).

Verlustfrei (das Druckbild bleibt gleich):
  rewrite      neu schreiben: alte Speicherstände (inkrementelles Speichern) fallen weg, Objekte in
               komprimierten Objekt-Streams, ZIP-Streams stärker gepackt
  unreferenced nicht mehr verwendete Ressourcen entfernen
  dedupe       doppelt gespeicherte Bilder, Schriften, ICC-Profile zusammenlegen
  private      Illustrator-/Photoshop-Bearbeitungsdaten (PieceInfo) entfernen
  thumbs       eingebettete Seitenvorschaubilder entfernen
  pack         unkomprimierte / schwach gepackte Bilder verlustfrei packen (ZIP + PNG-Prädiktor)
Im Druck nicht sichtbar, aber eine Änderung (eigene Häkchen):
  bits16       16 Bit je Kanal -> 8 Bit
  attachments  eingebettete Dateien (Anhänge) entfernen
  hidden       Inhalte ausgeblendeter Ebenen entfernen (Sichtbares festschreiben)
Optional:
  downsample   Bilder, deren effektive Auflösung (am größten platzierten Ort) über Ziel × Schwelle
               liegt, auf die Ziel-dpi herunterrechnen; Fotos als JPEG (Qualität wählbar), sonst ZIP
"""
from __future__ import annotations

import hashlib
import io
import zlib
from dataclasses import dataclass, field

from .l10n import tr

MB = 1024 * 1024
A4_M2 = 0.210 * 0.297
WARN_MB_PER_A4 = 20.0                    # ab hier „sehr groß“ (je A4-Fläche)


# --------------------------------------------------------------------------- #
# Analyse
# --------------------------------------------------------------------------- #
@dataclass
class ImageInfo:
    key: tuple
    w: int
    h: int
    bpc: int
    comps: int
    codec: str
    raw: int                    # Bytes in der Datei
    dpi: float | None           # größte Verwendung = kleinste effektive Auflösung; None = nicht platziert gefunden
    smask: bool = False
    is_mask: bool = False
    is_smask: bool = False      # selbst Soft-Maske eines anderen Bilds

    @property
    def raw_mb(self) -> float:
        return self.raw / MB


@dataclass
class SizeReport:
    size: int = 0
    pages: int = 0
    area_m2: float = 0.0
    revisions: int = 0                      # angehängte Speicherstände (inkrementell)
    parts: dict = field(default_factory=dict)        # Kategorie -> Bytes
    images: list = field(default_factory=list)       # [ImageInfo]
    duplicates: int = 0                     # Anzahl doppelter Streams
    duplicate_bytes: int = 0
    private_bytes: int = 0
    thumb_bytes: int = 0
    attachment_bytes: int = 0
    has_hidden_layers: bool = False

    @property
    def mb_per_a4(self) -> float:
        return (self.size / MB) / max(self.area_m2 / A4_M2, 1e-6)

    @property
    def too_big(self) -> bool:
        return self.size > 10 * MB and self.mb_per_a4 > WARN_MB_PER_A4


PART_NAMES = {"images": "Bilder", "fonts": "Schriften", "content": "Seiteninhalt (Vektoren, Text)",
              "icc": "Farbprofile", "private": "Bearbeitungsdaten (Illustrator/Photoshop)",
              "thumbs": "Vorschaubilder", "attachments": "Anhänge", "metadata": "Metadaten",
              "other": "Struktur und Sonstiges"}


def _components(img) -> int:
    from .preflight import _components as comps
    n = comps(img)
    if n:
        return n
    import pikepdf
    cs = img.get("/ColorSpace")
    if isinstance(cs, pikepdf.Array) and len(cs) and str(cs[0]) in ("/Indexed", "/I", "/Separation"):
        return 1
    return 0


def _codec(img) -> str:
    from .imagecheck import _codec as c
    return c(img)


def _walk_streams(obj, out: set, depth=0):
    """Alle indirekten Streams unterhalb eines Objekts (für PieceInfo u. Ä.)."""
    import pikepdf
    if depth > 30:
        return
    try:
        if isinstance(obj, pikepdf.Stream):
            if obj.objgen != (0, 0):
                if obj.objgen in out:
                    return
                out.add(obj.objgen)
            items = obj.stream_dict.items()
        elif isinstance(obj, pikepdf.Dictionary):
            items = obj.items()
        elif isinstance(obj, pikepdf.Array):
            items = enumerate(obj)
        else:
            return
        for _k, v in items:
            if isinstance(v, (pikepdf.Stream, pikepdf.Dictionary, pikepdf.Array)):
                _walk_streams(v, out, depth + 1)
    except Exception:
        pass


def analyze(data: bytes, pdf=None, colors=None) -> SizeReport:
    """Wofür geht der Platz drauf? (pikepdf, darf im Hintergrund laufen).
        colors: schon vorhandenes imagecheck.ColorReport (spart den zweiten Durchlauf)."""
    import pikepdf
    from . import imagecheck
    rep = SizeReport(size=len(data))
    rep.revisions = max(0, data.count(b"%%EOF") - 1)
    own = pdf is None
    if own:
        pdf = pikepdf.open(io.BytesIO(data))
    try:
        rep.pages = len(pdf.pages)
        try:
            if pdf.is_linearized and rep.revisions:
                rep.revisions -= 1                 # linearisiert: zweites %%EOF gehört zur Schnellansicht
        except Exception:
            pass
        for p in pdf.pages:
            mb = [float(v) for v in p.mediabox]
            rep.area_m2 += abs(mb[2] - mb[0]) * abs(mb[3] - mb[1]) / (72 / 0.0254) ** 2
        fontfiles, iccs, private, thumbs, attach, content, smasks = set(), set(), set(), set(), set(), set(), set()
        for o in pdf.objects:
            try:
                if isinstance(o, pikepdf.Dictionary) and o.get("/Type") == pikepdf.Name.FontDescriptor:
                    for k in ("/FontFile", "/FontFile2", "/FontFile3"):
                        if k in o and o[k].objgen != (0, 0):
                            fontfiles.add(o[k].objgen)
                if isinstance(o, pikepdf.Array) and len(o) == 2 and o[0] == pikepdf.Name.ICCBased:
                    iccs.add(o[1].objgen)
                if isinstance(o, (pikepdf.Dictionary, pikepdf.Stream)):
                    d = o.stream_dict if isinstance(o, pikepdf.Stream) else o
                    if "/PieceInfo" in d:
                        _walk_streams(d["/PieceInfo"], private)
                    sm = d.get("/SMask")
                    if isinstance(sm, pikepdf.Stream):
                        smasks.add(sm.objgen)
                    if d.get("/Type") == pikepdf.Name.EmbeddedFile:
                        attach.add(o.objgen)
            except Exception:
                continue
        for p in pdf.pages:
            if "/Thumb" in p.obj:
                try:
                    thumbs.add(p.obj.Thumb.objgen)
                except Exception:
                    pass
            c = p.obj.get("/Contents")
            for s in (c if isinstance(c, pikepdf.Array) else [c] if c is not None else []):
                try:
                    content.add(s.objgen)
                except Exception:
                    pass
        try:
            from .preflight import current_visible, _layers
            layers = _layers(pdf)
            vis = current_visible(pdf)
            rep.has_hidden_layers = any(L.key not in vis for L in layers)
        except Exception:
            pass
        # effektive Auflösung je Bild-Objekt: kleinste dpi = größte Platzierung
        best: dict = {}
        try:
            for u in (colors or imagecheck.analyze(pdf, max_uses=20000)).images:
                if u.key is not None:
                    best[u.key] = min(best.get(u.key, 1e9), u.dpi)
        except Exception:
            pass
        parts = {k: 0 for k in PART_NAMES}
        hashes: dict = {}
        streams_total = 0
        for o in pdf.objects:
            if not isinstance(o, pikepdf.Stream):
                continue
            try:
                n = len(o.read_raw_bytes())
            except Exception:
                continue
            streams_total += n
            og = o.objgen
            sub = o.stream_dict.get("/Subtype")
            if og in private:
                cat = "private"
            elif og in thumbs:
                cat = "thumbs"
            elif og in attach:
                cat = "attachments"
            elif sub == pikepdf.Name.Image:
                cat = "images"
            elif og in fontfiles:
                cat = "fonts"
            elif og in iccs or _is_icc(o.stream_dict):
                cat = "icc"
            elif o.stream_dict.get("/Type") == pikepdf.Name.Metadata:
                cat = "metadata"
            elif og in content or sub == pikepdf.Name.Form:
                cat = "content"
            else:
                cat = "other"
            parts[cat] += n
            if cat in ("images", "fonts", "icc") and n > 256:
                h = hashlib.sha1(o.read_raw_bytes()).hexdigest() + str(sorted(
                    (k, str(v)) for k, v in o.stream_dict.items() if k not in ("/Length", "/SMask", "/Metadata")))
                if h in hashes:
                    rep.duplicates += 1
                    rep.duplicate_bytes += n
                else:
                    hashes[h] = og
            if sub == pikepdf.Name.Image:
                try:
                    bpc = int(o.stream_dict.get("/BitsPerComponent", 8) or 8)
                    is_mask = bool(o.stream_dict.get("/ImageMask", False))
                    rep.images.append(ImageInfo(og, int(o.stream_dict.get("/Width", 0)),
                                                int(o.stream_dict.get("/Height", 0)), 1 if is_mask else bpc,
                                                1 if is_mask else _components(o), _codec(o), n, best.get(og),
                                                "/SMask" in o.stream_dict, is_mask, og in smasks))
                except Exception:
                    pass
        parts["other"] += max(0, rep.size - streams_total)
        rep.parts = parts
        rep.private_bytes, rep.thumb_bytes, rep.attachment_bytes = parts["private"], parts["thumbs"], parts["attachments"]
        rep.images.sort(key=lambda i: -i.raw)
    finally:
        if own:
            pdf.close()
    return rep


def summary_lines(rep: SizeReport, top: int = 4) -> list:
    """Aufschlüsselung als Textzeilen (größter Anteil zuerst)."""
    out = [tr("Datei: {0:.1f} MB · {1} Seite(n) · {2:.1f} MB je A4-Fläche").format(rep.size / MB, rep.pages,
                                                                                   rep.mb_per_a4)]
    for k, v in sorted(rep.parts.items(), key=lambda kv: -kv[1]):
        if v >= max(64 * 1024, rep.size * 0.01):
            out.append(f"  {tr(PART_NAMES[k])}: {v / MB:.1f} MB ({100 * v / max(rep.size, 1):.0f} %)")
    if rep.revisions:
        out.append("  " + tr("{0} angehängte(r) Speicherstand/-stände (inkrementell gespeichert)").format(rep.revisions))
    if rep.duplicates:
        out.append("  " + tr("{0} doppelt gespeicherte(s) Objekt(e): {1:.1f} MB").format(rep.duplicates,
                                                                                         rep.duplicate_bytes / MB))
    for im in [i for i in rep.images if not i.is_smask][:top]:
        dpi = f"{im.dpi:.0f} dpi" if im.dpi else tr("nicht platziert")
        out.append("  " + tr("Bild {0} × {1} px, {2} Bit, {3}: {4:.1f} MB, {5}").format(
            im.w, im.h, im.bpc, im.codec, im.raw_mb, dpi))
    return out


def candidates(rep: SizeReport, target_dpi: int = 300, threshold: float = 1.5) -> list:
    """Bilder, die beim Herunterrechnen auf target_dpi angefasst würden."""
    return [i for i in rep.images if not i.is_smask and not i.is_mask and i.bpc != 1 and i.dpi
            and i.dpi > target_dpi * threshold]


def zip_photos(rep: SizeReport) -> list:
    """Vermutlich Fotos, die als ZIP bzw. unkomprimiert gespeichert sind: ZIP spart bei Fotos kaum etwas
        (> 50 % der Rohgröße) – als JPEG wären sie meist ein Zehntel so groß."""
    lossless = {"ZIP", "LZW", "RLE", tr("unkomprimiert")}
    out = []
    for i in rep.images:
        if i.is_mask or i.is_smask or i.bpc not in (8, 16) or i.comps not in (1, 3, 4) or i.w * i.h < 128 * 128:
            continue
        if i.codec in lossless and i.raw > 0.5 * i.w * i.h * i.comps * i.bpc / 8:
            out.append(i)
    return out


def issues(rep: SizeReport) -> list:
    """Befunde für die Prüfung: [(Schwere, Text)]."""
    out = []
    if rep.too_big:
        main = max(rep.parts.items(), key=lambda kv: kv[1]) if rep.parts else ("other", 0)
        out.append(("warning", tr("Datei sehr groß: {0:.0f} MB ({1:.0f} MB je A4-Fläche), größter Anteil: {2} "
                                  "({3:.0f} %). Reparatur: „Datei verkleinern …“ (Reiter Dateigröße).").format(
            rep.size / MB, rep.mb_per_a4, tr(PART_NAMES[main[0]]), 100 * main[1] / max(rep.size, 1))))
    zp = zip_photos(rep)
    zp_bytes = sum(i.raw for i in zp)
    if zp_bytes > max(5 * MB, rep.size * 0.3):
        out.append(("warning" if rep.too_big else "info",
                    tr("{0} Foto(s) als ZIP statt JPEG gespeichert ({1:.0f} MB) – als JPEG meist nur ein Zehntel so "
                       "groß. Reparatur: „Datei verkleinern …“ → „Fotos als JPEG speichern“.").format(
                        len(zp), zp_bytes / MB)))
    if rep.duplicate_bytes > max(2 * MB, rep.size * 0.1):
        out.append(("warning" if rep.duplicate_bytes > 10 * MB else "info",
                    tr("{0:.1f} MB doppelt gespeichert ({1} Objekte, z. B. dasselbe Farbprofil je Seite) – verlustfrei "
                       "entfernbar mit „Datei verkleinern …“.").format(rep.duplicate_bytes / MB, rep.duplicates)))
    if rep.private_bytes > max(2 * MB, rep.size * 0.1):
        out.append(("info", tr("{0:.1f} MB Illustrator-/Photoshop-Bearbeitungsdaten – für den Druck nicht nötig.")
                    .format(rep.private_bytes / MB)))
    if rep.revisions and rep.size > 5 * MB:
        out.append(("info", tr("Mehrfach gespeichert ({0} angehängte Speicherstände) – alte Stände belegen Platz.")
                    .format(rep.revisions)))
    b16 = [i for i in rep.images if i.bpc == 16]
    if b16:
        out.append(("info", tr("{0} Bild(er) mit 16 Bit je Kanal – doppelte Datenmenge, im Druck kein Unterschied.")
                    .format(len(b16))))
    big = candidates(rep, 300, 2.0)
    if rep.size > 10 * MB and big and sum(i.raw for i in big) > rep.size * 0.2:
        out.append(("info", tr("{0} Bild(er) mit mehr als 600 dpi – Herunterrechnen auf 300 dpi möglich.")
                    .format(len(big))))
    return out


# --------------------------------------------------------------------------- #
# Maßnahmen
# --------------------------------------------------------------------------- #
@dataclass
class ShrinkOptions:
    rewrite: bool = True
    unreferenced: bool = True
    dedupe: bool = True
    private: bool = True
    thumbs: bool = True
    pack: bool = True
    bits16: bool = False
    attachments: bool = False
    hidden: bool = False
    downsample: bool = False
    target_dpi: int = 300
    threshold: float = 1.5               # nur Bilder über Ziel × Schwelle
    jpeg_quality: int = 92
    photos_jpeg: bool = False            # Fotos, die als ZIP/unkomprimiert gespeichert sind, als JPEG


def _png_up(arr, bpp: int) -> bytes:
    """Zeilen mit PNG-Filter „Up“ (Typ 2) kodieren -> Bytes für FlateDecode /Predictor 12."""
    import numpy as np
    rows = arr.reshape(arr.shape[0], -1)
    diff = rows.copy()
    diff[1:] = (rows[1:].astype(np.int16) - rows[:-1].astype(np.int16)).astype(np.uint8)
    out = np.empty((rows.shape[0], rows.shape[1] + 1), np.uint8)
    out[:, 0] = 2
    out[:, 1:] = diff
    return out.tobytes()


def _write_flate(img, raw: bytes, w: int, h: int, comps: int, bpc: int):
    """Abtastwerte (dekodiert) verlustfrei als ZIP + PNG-Prädiktor ablegen."""
    import numpy as np
    import pikepdf
    row = (w * comps * bpc + 7) // 8
    arr = np.frombuffer(raw[:row * h], np.uint8).reshape(h, row)
    data = zlib.compress(_png_up(arr, max(1, comps * bpc // 8)), 9)
    img.write(data, filter=pikepdf.Name.FlateDecode,
              decode_parms=pikepdf.Dictionary(Predictor=12, Colors=comps, BitsPerComponent=bpc, Columns=w))
    return len(data)


def _replace_refs(container, dup: dict, depth: int = 0):
    """Verweise auf doppelte Objekte auf das behaltene umbiegen – auch in direkt eingebetteten
        Wörterbüchern/Arrays (z. B. [/ICCBased 13 0 R] direkt im Farbraum der Seite)."""
    import pikepdf
    if depth > 40:
        return
    try:
        items = list(container.items()) if isinstance(container, pikepdf.Dictionary) else list(enumerate(container))
    except Exception:
        return
    for k, v in items:
        try:
            if not isinstance(v, (pikepdf.Stream, pikepdf.Dictionary, pikepdf.Array)):
                continue
            if v.is_indirect:
                if v.objgen in dup:
                    container[k] = dup[v.objgen]
            else:
                _replace_refs(v, dup, depth + 1)
        except Exception:
            pass


def _is_icc(sd) -> bool:
    """ICC-Profil-Stream: /N (Kanäle), kein /Type/Subtype – auch wenn das [/ICCBased …] direkt im Farbraum steckt."""
    try:
        return "/N" in sd and "/Subtype" not in sd and "/Type" not in sd and int(sd.N) in (1, 3, 4)
    except Exception:
        return False


LOSSLESS = {"/FlateDecode", "/Fl", "/LZWDecode", "/LZW", "/RunLengthDecode", "/RL"}
DCT = {"/DCTDecode", "/DCT"}


def _filters(img) -> list:
    import pikepdf
    f = img.stream_dict.get("/Filter")
    return [str(x) for x in f] if isinstance(f, pikepdf.Array) else ([str(f)] if f is not None else [])


def _indexed(img) -> bool:
    import pikepdf
    cs = img.stream_dict.get("/ColorSpace")
    return isinstance(cs, pikepdf.Array) and len(cs) > 0 and str(cs[0]) in ("/Indexed", "/I")


def _set_dct(img, jpg: bytes):
    import pikepdf
    img.write(jpg, filter=pikepdf.Name.DCTDecode)
    if "/DecodeParms" in img.stream_dict:
        del img.stream_dict["/DecodeParms"]


def _image(img, im: ImageInfo, opts: ShrinkOptions, note, done: set):
    """Ein Bild-Objekt bearbeiten (alle Schritte prüfen ihr eigenes Häkchen)."""
    import numpy as np
    import pikepdf
    from PIL import Image
    before = len(img.read_raw_bytes())
    fl = _filters(img)
    w, h, comps, bpc = im.w, im.h, im.comps, im.bpc
    # ZIP um ein JPEG herum: inneres JPEG für Herunterrechnen; ohne ZIP-Schicht nur wenn's kleiner wird
    jpeg = None
    wrapped = len(fl) == 2 and fl[0] in ("/FlateDecode", "/Fl") and fl[1] in DCT
    if wrapped:
        jpeg = zlib.decompressobj().decompress(img.read_raw_bytes())
        if not jpeg.startswith(b"\xff\xd8"):
            jpeg, wrapped = None, False
    elif fl in (["/DCTDecode"], ["/DCT"]):
        jpeg = img.read_raw_bytes()
    is_jpeg = jpeg is not None
    lossless = all(x in LOSSLESS for x in fl)       # auch: unkomprimiert
    # optional: herunterrechnen (am größten platzierten Ort über Ziel × Schwelle)
    f = 1.0
    if opts.downsample and im.dpi and im.dpi > opts.target_dpi * opts.threshold and not _indexed(img):
        f = opts.target_dpi / im.dpi
    if f < 1.0 and comps in (1, 3, 4) and bpc in (8, 16) and (is_jpeg or lossless):
        nw, nh = max(1, round(w * f)), max(1, round(h * f))
        if is_jpeg:
            pil = Image.open(io.BytesIO(jpeg))
            pil.draft(pil.mode, (nw, nh))          # schneller bei großen JPEGs
            small = pil.convert(pil.mode).resize((nw, nh), Image.LANCZOS)
            buf = io.BytesIO()
            kw = {"icc_profile": pil.info["icc_profile"]} if pil.info.get("icc_profile") else {}
            small.save(buf, "JPEG", quality=opts.jpeg_quality, subsampling=0, **kw)
            _set_dct(img, buf.getvalue())
        else:
            if bpc == 16 and isinstance(img.stream_dict.get("/Mask"), pikepdf.Array):
                return                             # Farbschlüssel-Maske passt nach 8 Bit nicht mehr
            ok_jpeg = opts.photos_jpeg and _jpeg_ok(img, im)
            arr = _resized(img, w, h, comps, bpc, nw, nh)
            if ok_jpeg and _photo_like(arr):
                _write_jpeg(img, arr, opts.jpeg_quality)
            else:
                _write_flate(img, arr.tobytes(), nw, nh, comps, 8)
                img.BitsPerComponent = 8
        img.Width, img.Height = nw, nh
        sm = img.stream_dict.get("/SMask")
        if sm is not None and int(sm.get("/Width", 0)) == w and int(sm.get("/Height", 0)) == h \
                and int(sm.get("/BitsPerComponent", 8)) in (8, 16) and all(x in LOSSLESS for x in _filters(sm)):
            a2 = _resized(sm, w, h, 1, int(sm.get("/BitsPerComponent", 8)), nw, nh)
            _write_flate(sm, a2.tobytes(), nw, nh, 1, 8)
            sm.Width, sm.Height, sm.BitsPerComponent = nw, nh, 8
            done.add(sm.objgen)
        note("downsample", before - len(img.read_raw_bytes()))
        return
    if wrapped and opts.pack and len(jpeg) < before * 0.99:
        parms = img.stream_dict.get("/DecodeParms")
        _set_dct(img, jpeg)
        if isinstance(parms, pikepdf.Array) and len(parms) == 2 and isinstance(parms[1], pikepdf.Dictionary):
            img.DecodeParms = parms[1]
        note("unwrap", before - len(jpeg))
        return
    if not lossless or comps not in (1, 2, 3, 4) or bpc not in (8, 16):
        return
    if opts.photos_jpeg and _jpeg_ok(img, im):
        arr = _samples8(img, w, h, comps, bpc)
        if _photo_like(arr):
            old = img.read_raw_bytes(), img.stream_dict.get("/Filter"), img.stream_dict.get("/DecodeParms")
            n = _write_jpeg(img, arr, opts.jpeg_quality)
            if n < before * 0.9:
                note("photos", before - n)
                return
            img.write(old[0])                      # bringt nichts -> Original zurück
            for k, v in (("/Filter", old[1]), ("/DecodeParms", old[2])):
                if v is None:
                    if k in img.stream_dict:
                        del img.stream_dict[k]
                else:
                    img.stream_dict[k] = v
            img.BitsPerComponent = bpc
            if "/Decode" in img.stream_dict:
                del img.stream_dict["/Decode"]
    if opts.bits16 and bpc == 16 and not isinstance(img.stream_dict.get("/Mask"), pikepdf.Array):
        raw = img.read_bytes()
        a = (np.frombuffer(raw[:w * h * comps * 2], ">u2") >> 8).astype(np.uint8)
        _write_flate(img, a.tobytes(), w, h, comps, 8)
        img.BitsPerComponent = 8
        note("bits16", before - len(img.read_raw_bytes()))
        return
    if opts.pack:
        old_parms, old_filter, old_data = img.stream_dict.get("/DecodeParms"), img.stream_dict.get("/Filter"), \
            img.read_raw_bytes()
        newlen = _write_flate(img, img.read_bytes(), w, h, comps, bpc)
        if newlen >= before * 0.97:                # bringt nichts -> Original behalten
            img.write(old_data)
            for k, v in (("/Filter", old_filter), ("/DecodeParms", old_parms)):
                if v is None:
                    if k in img.stream_dict:
                        del img.stream_dict[k]
                else:
                    img.stream_dict[k] = v
        else:
            note("pack", before - newlen)


def _jpeg_ok(img, im: ImageInfo) -> bool:
    """Darf dieses Bild als JPEG gespeichert werden? (keine Masken, keine Decode-Umkehr, keine Farbschlüssel)"""
    import pikepdf
    sd = img.stream_dict
    return (not im.is_mask and not im.is_smask and im.comps in (1, 3, 4) and im.bpc in (8, 16)
            and not _indexed(img) and "/Decode" not in sd and not isinstance(sd.get("/Mask"), pikepdf.Array)
            and im.w * im.h >= 128 * 128)


def _samples8(img, w, h, comps, bpc):
    """Dekodierte Abtastwerte -> 8-Bit-Array (h, w, comps)."""
    import numpy as np
    raw = img.read_bytes()
    if bpc == 16:
        return (np.frombuffer(raw[:w * h * comps * 2], ">u2").reshape(h, w, comps) >> 8).astype(np.uint8)
    return np.frombuffer(raw[:w * h * comps], np.uint8).reshape(h, w, comps)


def _photo_like(arr) -> bool:
    """Foto (viele Farbtöne) statt Grafik/Logo/Text (wenige Farben, harte Kanten) – nur Fotos als JPEG."""
    import numpy as np
    step_y, step_x = max(1, arr.shape[0] // 64), max(1, arr.shape[1] // 64)
    sample = np.ascontiguousarray(arr[::step_y, ::step_x]).reshape(-1, arr.shape[2])
    if arr.shape[2] == 1:
        # Graustufen: viele Töne UND nicht überwiegend reines Schwarz/Weiß (Text-Scan, Strichzeichnung)
        v = sample[:, 0]
        extreme = np.mean((v < 16) | (v > 239))
        return len(np.unique(v)) > 128 and extreme < 0.5
    return len(np.unique(sample, axis=0)) > min(1000, sample.shape[0] // 3)


def _write_jpeg(img, arr, quality: int) -> int:
    """8-Bit-Array als JPEG ablegen. CMYK: Pillow schreibt Adobe-üblich invertiert -> /Decode [1 0 …]."""
    import pikepdf
    from PIL import Image
    comps = arr.shape[2]
    mode = {1: "L", 3: "RGB", 4: "CMYK"}[comps]
    pil = Image.fromarray(arr[:, :, 0] if comps == 1 else arr, mode)
    buf = io.BytesIO()
    pil.save(buf, "JPEG", quality=quality, subsampling=0)
    _set_dct(img, buf.getvalue())
    img.BitsPerComponent = 8
    if comps == 4:
        img.Decode = pikepdf.Array([1, 0, 1, 0, 1, 0, 1, 0])
    return len(buf.getvalue())


def _resized(img, w, h, comps, bpc, nw, nh):
    """Dekodierte Abtastwerte (ZIP/LZW/RLE/roh) -> 8-Bit-Array (nh, nw, comps), Lanczos."""
    import numpy as np
    from PIL import Image
    raw = img.read_bytes()
    if bpc == 16:
        a = (np.frombuffer(raw[:w * h * comps * 2], ">u2").reshape(h, w, comps) >> 8).astype(np.uint8)
    else:
        a = np.frombuffer(raw[:w * h * comps], np.uint8).reshape(h, w, comps)
    return np.stack([np.asarray(Image.fromarray(np.ascontiguousarray(a[:, :, c])).resize((nw, nh), Image.LANCZOS))
                     for c in range(comps)], axis=2)


def shrink(data: bytes, opts: ShrinkOptions, progress=None) -> tuple[bytes, list]:
    """Verkleinern nach opts. -> (neue Daten, Hinweise mit Einsparung je Maßnahme)."""
    import pikepdf
    saved: dict = {}
    counts: dict = {}

    def note(k, b, n=1):
        saved[k] = saved.get(k, 0) + b
        counts[k] = counts.get(k, 0) + n

    src = data
    if opts.hidden:
        try:
            from . import preflight
            if preflight.has_layers(src):
                before = len(src)
                src = preflight.flatten_layers(src)
                note("hidden", before - len(src))
        except Exception:
            pass
    rep = analyze(src)
    pdf = pikepdf.open(io.BytesIO(src))
    try:
        # 1) Bearbeitungsdaten, Vorschaubilder, Anhänge
        if opts.private:
            for o in list(pdf.objects) + [pdf.Root] + [p.obj for p in pdf.pages]:
                try:
                    d = o.stream_dict if isinstance(o, pikepdf.Stream) else o
                    if isinstance(d, pikepdf.Dictionary) and "/PieceInfo" in d:
                        del d["/PieceInfo"]
                        counts["private"] = counts.get("private", 0) + 1
                except Exception:
                    pass
            saved["private"] = rep.private_bytes
        if opts.thumbs:
            for p in pdf.pages:
                if "/Thumb" in p.obj:
                    del p.obj["/Thumb"]
                    counts["thumbs"] = counts.get("thumbs", 0) + 1
            saved["thumbs"] = rep.thumb_bytes
        if opts.attachments:
            names = pdf.Root.get("/Names")
            if names is not None and "/EmbeddedFiles" in names:
                del names["/EmbeddedFiles"]
                note("attachments", rep.attachment_bytes)
            if "/AF" in pdf.Root:
                del pdf.Root["/AF"]
        # 2) Bilder: herunterrechnen / 16 -> 8 Bit / verlustfrei packen / ZIP+JPEG entpacken
        info = {im.key: im for im in rep.images}
        imgs = [o for o in pdf.objects if isinstance(o, pikepdf.Stream)
                and o.stream_dict.get("/Subtype") == pikepdf.Name.Image]
        done = set()
        for n, img in enumerate(imgs):
            if progress:
                progress(n, len(imgs))
            im = info.get(img.objgen)
            if im is None or im.is_mask or im.bpc == 1 or img.objgen in done:
                continue
            try:
                _image(img, im, opts, note, done)
            except Exception:
                continue
        # 3) Duplikate zusammenlegen
        if opts.dedupe:
            canon, dup = {}, {}
            for o in pdf.objects:
                if not isinstance(o, pikepdf.Stream):
                    continue
                sd = o.stream_dict
                if sd.get("/Subtype") != pikepdf.Name.Image and "/Length1" not in sd and "/Length2" not in sd \
                        and sd.get("/Subtype") not in (pikepdf.Name("/Type1C"), pikepdf.Name("/CIDFontType0C"),
                                                       pikepdf.Name("/OpenType")) and not _is_icc(sd):
                    continue
                try:
                    raw = o.read_raw_bytes()
                except Exception:
                    continue
                if len(raw) < 256:
                    continue
                key = hashlib.sha1(raw).hexdigest() + str(sorted(
                    (k, str(v)) for k, v in sd.items() if k not in ("/Length",)))
                if key in canon:
                    dup[o.objgen] = canon[key]
                    note("dedupe", len(raw))
                else:
                    canon[key] = o
            if dup:
                for o in list(pdf.objects):
                    if isinstance(o, (pikepdf.Stream, pikepdf.Dictionary, pikepdf.Array)):
                        _replace_refs(o.stream_dict if isinstance(o, pikepdf.Stream) else o, dup)
                _replace_refs(pdf.trailer, dup)
        if opts.unreferenced:
            try:
                pdf.remove_unreferenced_resources()
            except Exception:
                pass
        buf = io.BytesIO()
        if opts.rewrite:
            pdf.save(buf, object_stream_mode=pikepdf.ObjectStreamMode.generate, compress_streams=True,
                     recompress_flate=True)
        else:
            pdf.save(buf)
        out = buf.getvalue()
    finally:
        pdf.close()
    labels = {"hidden": tr("Ausgeblendete Ebenen entfernt"), "private": tr("Bearbeitungsdaten entfernt"),
              "thumbs": tr("Vorschaubilder entfernt"), "attachments": tr("Anhänge entfernt"),
              "downsample": tr("Bilder auf {0} dpi heruntergerechnet").format(opts.target_dpi),
              "bits16": tr("16-Bit-Bilder auf 8 Bit"), "pack": tr("Bilder verlustfrei gepackt"),
              "dedupe": tr("Doppelte Objekte zusammengelegt"),
              "unwrap": tr("Doppelt gepackte JPEGs (ZIP + JPEG) entpackt"),
              "photos": tr("Fotos als JPEG gespeichert (Qualität {0})").format(opts.jpeg_quality)}
    notes = [tr("Vorher {0:.1f} MB → nachher {1:.1f} MB ({2:+.0f} %).").format(
        len(data) / MB, len(out) / MB, 100.0 * (len(out) - len(data)) / max(len(data), 1))]
    for k in ("downsample", "photos", "bits16", "pack", "unwrap", "dedupe", "private", "thumbs", "attachments",
              "hidden"):
        if counts.get(k) or saved.get(k):
            notes.append(f"{labels[k]}: {counts.get(k, 0)} · −{max(0, saved.get(k, 0)) / MB:.1f} MB")
    if opts.rewrite and rep.revisions:
        notes.append(tr("{0} alte(r) Speicherstand/-stände entfernt.").format(rep.revisions))
    return out, notes
