# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Output for the print shop (job "press"): convert as recommended, always embed the printing condition as output
intent, check before/after, optionally a package with PDF, ICC profiles and a short report. No Qt.

    passermark-cli press flyer.pdf flyer-druck.pdf --set target=/pfad/PSOcoated_v3.icc --set rgb=convert

cmyk_mode   auto      what colorcheck recommends: RGB -> target (existing CMYK stays); file made for another
                      printing condition or ink coverage above the guide value -> separate everything again
            rgb_only  RGB/grey -> target, existing CMYK unchanged
            all       everything again (CMYK from source -> target)
            none      no conversion, only the output intent
rgb         convert | keep (pass RGB on with ICC profile – untagged RGB gets sRGB) | ask (default: a file with
            RGB content is refused – the program asks, the command line must say what it wants)
"""
from __future__ import annotations

import datetime
import hashlib
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass

from .l10n import tr

MODES = ("auto", "rgb_only", "all", "none")
RGB_CHOICES = ("ask", "convert", "keep")


@dataclass
class PressSettings:
    target: str = ""            # CMYK-Profil der Druckbedingung (.icc) – Pflicht
    intent: str = "relative"    # perceptual | relative | saturation | absolute
    bpc: bool = True            # Tiefenkompensierung
    cmyk_mode: str = "auto"     # auto | rgb_only | all | none
    source: str = ""            # Quellprofil für vorhandenes CMYK bei „all“ ("" = aus dem Output Intent der Datei)
    rgb: str = "ask"            # convert | keep | ask
    gray_to_k: bool = True      # Grau/Schwarz nur mit K
    tac_limit: int = 0          # Richtwert Farbauftrag in % (0 = aus dem Profil)
    material: str = ""          # Material-ID (Papierweiß/Name für den Bericht)
    package: bool = False       # zusätzlich <Ausgabe>_Druckerei.zip: PDF, ICC-Profile, Bericht


def _target(s: PressSettings, cfg: dict | None):
    from . import colorcheck, colorlab, colorconv
    if not s.target:
        raise ValueError(tr("Keine Druckbedingung: target = Pfad zum CMYK-Profil (.icc) angeben."))
    if not os.path.isfile(s.target):
        raise ValueError(tr("Profil nicht gefunden: {0}").format(s.target))
    if colorconv.icc_colorspace(s.target) != "CMYK":
        raise ValueError(tr("Für die Druckerei wird ein CMYK-Profil gebraucht: {0}").format(s.target))
    if s.cmyk_mode not in MODES:
        raise ValueError(tr("cmyk_mode: {0} erwartet").format(", ".join(MODES)))
    if s.rgb not in RGB_CHOICES:
        raise ValueError(tr("rgb: {0} erwartet").format(", ".join(RGB_CHOICES)))
    t = colorcheck.target_from_file(s.target, s.intent or "relative")
    t.tac_limit = int(s.tac_limit or 0)
    if s.material:
        m = colorlab.material_by_id(cfg or {}, s.material)
        if m is not None:
            t.material, t.material_id = m.get("name") or m["id"], m["id"]
            t.white = list(m["white"]) if m.get("white") else None
            t.surface = m.get("surface") or ""
    return t


def plan(f, t, s: PressSettings, cfg: dict | None = None) -> dict:
    """What will be done: {"mode", "source", "tag_rgb", "notes": [...]} – also shown by the assistant beforehand."""
    from . import colorcheck
    notes = []
    oi = next((o for o in f.output_intents if o), "")
    other = bool(oi and f.has_cmyk and not colorcheck.same_condition(oi, t.icc))
    over = bool(f.tac and f.tac["max"] > f.tac["limit"] + 0.5)
    mode, source = s.cmyk_mode, s.source
    if mode == "auto":
        if other or (over and f.has_cmyk):
            mode = "all"
        elif f.has_rgb:
            mode = "rgb_only"
        else:
            mode = "none"
    if mode == "all" and not source:
        source = colorcheck.source_profile_for(oi, cfg) if other else t.icc
        if other and not source:
            notes.append(tr("Quellprofil „{0}“ nicht installiert – vorhandenes CMYK wird als Ghostscript-Standard "
                            "angenommen.").format(oi))
    if f.has_rgb and s.rgb == "ask":
        raise ValueError(tr("Die Datei enthält RGB. Bitte entscheiden: rgb=convert (nach „{0}“ umwandeln) oder "
                            "rgb=keep (RGB mit Profil weitergeben, die Druckerei rechnet um).").format(t.name))
    tag_rgb = False
    if f.has_rgb and s.rgb == "keep":
        if mode == "rgb_only":
            mode = "none"
        if mode == "none":
            tag_rgb = True
        else:
            notes.append(tr("RGB wird mit umgewandelt – beim Neu-Separieren rechnet Ghostscript alle Farben."))
    if mode == "rgb_only" and over and not f.has_cmyk:
        pass                                                   # RGB -> Ziel: das Profil begrenzt den Farbauftrag
    elif mode in ("rgb_only", "none") and over:
        tac_note = (tr("Farbauftrag {0} % über dem Richtwert {1} % bleibt – mit cmyk_mode=all neu separieren.").format(
            f.tac["max"], f.tac["limit"]))
        return {"mode": mode, "source": source if mode == "all" else "", "tag_rgb": tag_rgb, "notes": notes,
                "tac_note": tac_note}
    return {"mode": mode, "source": source if mode == "all" else "", "tag_rgb": tag_rgb, "notes": notes,
            "tac_note": ""}


def tag_rgb_srgb(pdf) -> int:
    """RGB ohne Profil als sRGB kennzeichnen (Bilder: ICCBased statt DeviceRGB, Seiten/Formulare: DefaultRGB).
        -> Anzahl geänderter Stellen."""
    import pikepdf
    from PIL import ImageCms
    prof = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    st = pikepdf.Stream(pdf, prof)
    st["/N"] = 3
    st["/Alternate"] = pikepdf.Name.DeviceRGB
    cs = pikepdf.Array([pikepdf.Name.ICCBased, st])
    n = 0

    def default_rgb(res):
        nonlocal n
        if res is None:
            return
        csd = res.get("/ColorSpace")
        if csd is None:
            res["/ColorSpace"] = pikepdf.Dictionary()
            csd = res["/ColorSpace"]
        if "/DefaultRGB" not in csd:
            csd["/DefaultRGB"] = cs
            n += 1

    for obj in pdf.objects:
        if not isinstance(obj, pikepdf.Stream):
            continue
        sub = obj.get("/Subtype")
        if sub == pikepdf.Name.Image and obj.get("/ColorSpace") == pikepdf.Name.DeviceRGB:
            obj["/ColorSpace"] = cs
            n += 1
        elif sub == pikepdf.Name.Form and obj.get("/Resources") is not None:
            default_rgb(obj.Resources)
    for page in pdf.pages:
        if page.obj.get("/Resources") is None:
            page.obj["/Resources"] = pikepdf.Dictionary()
        default_rgb(page.obj.Resources)
    return n


def _md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def report_text(src_name: str, t, s: PressSettings, p: dict, before, after, findings_after) -> str:
    from . import __version__, colorlab, config
    lines = [tr("Passermark {0} – Bericht für die Druckerei").format(__version__),
             tr("Erstellt: {0}").format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M")),
             tr("Datei: {0}").format(src_name), ""]
    lines.append(tr("Druckbedingung (Output Intent): {0}").format(t.name))
    lines.append(tr("Profil: {0}  (MD5 {1})").format(os.path.basename(t.icc), _md5(t.icc)))
    lines.append(tr("Render-Intent: {0}, Tiefenkompensierung: {1}").format(
        tr(config.INTENTS.get(t.intent, t.intent)), tr("ja") if s.bpc else tr("nein")))
    mode_txt = {"rgb_only": tr("RGB/Grau → CMYK, vorhandenes CMYK unverändert"),
                "all": tr("alles neu separiert"), "none": tr("keine Farbumwandlung")}[p["mode"]]
    lines.append(tr("Umwandlung: {0}").format(mode_txt))
    if p["mode"] == "all":
        lines.append(tr("Quellprofil für vorhandenes CMYK: {0}").format(
            os.path.basename(p["source"]) if p["source"] else tr("Ghostscript-Standard")))
    if p["tag_rgb"]:
        lines.append(tr("RGB weitergegeben, RGB ohne Profil als sRGB gekennzeichnet"))
    if t.material:
        lines.append(tr("Material: {0}").format(t.material))
        pw = colorlab.profile_white(t.icc)
        if t.white:
            lines.append(tr("Papierweiß gemessen: {0}").format(colorlab.fmt_lab(t.white))
                         + (tr("  (Profil {0}, ΔE {1:.1f})").format(colorlab.fmt_lab(pw), colorlab.delta_e(t.white, pw))
                            if pw else ""))
    lines.append("")
    for label, f in ((tr("Vorher"), before), (tr("Nachher"), after)):
        tac = f"{f.tac['max']} %" if f.tac else "–"
        lines.append(tr("{0}: Farbräume {1}; Output Intent {2}; Farbauftrag max. {3}").format(
            label, ", ".join(k for k, pages in (("RGB", f.rgb_pages), ("CMYK", f.cmyk_pages), (tr("Grau"), f.gray_pages),
                                                ("Lab", f.lab_pages)) if pages) or "–",
            ", ".join(f.output_intents) or tr("keiner"), tac))
    if after.spots:
        lines.append(tr("Sonderfarben: {0}").format(", ".join(sorted(after.spots))))
    lines.append("")
    lines.append(tr("Prüfung nach der Ausgabe:"))
    for x in findings_after:
        mark = {"error": "!!", "warning": "! ", "info": "i ", "ok": "ok"}.get(x.severity, "  ")
        keep = tr(" – bewusst mit Profil weitergegeben") if x.key == "rgb" and p["tag_rgb"] else ""
        lines.append(f"  [{mark}] {x.title}{keep}")
    for n in p["notes"] + ([p["tac_note"]] if p.get("tac_note") else []):
        lines.append(f"  - {n}")
    return "\n".join(lines) + "\n"


def run(src: str, dst: str, s: PressSettings, cfg: dict | None = None, progress=None, cancel=None) -> dict:
    """-> {"info": {...}, "notes": [...], "report": text, "findings": [...], "package": path|""}"""
    from . import cmyk, colorcheck
    import pikepdf

    def step(i, text):
        if progress is not None:
            progress(i, 5, text)
        if cancel is not None and cancel():
            from .core import Cancelled
            raise Cancelled(tr("Abgebrochen."))

    if cfg is None:
        from . import config
        cfg = config.load()
    t = _target(s, cfg)
    with open(src, "rb") as fh:
        data = fh.read()
    step(0, tr("Prüfe …"))
    before = colorcheck.facts(data, t, cancel=cancel)
    p = plan(before, t, s, cfg)
    tmpdir = tempfile.mkdtemp(prefix="passermark-press-")
    try:
        work = os.path.join(tmpdir, "work.pdf")
        if p["mode"] in ("rgb_only", "all"):
            step(1, tr("Wandle Farben um …"))
            ms = cmyk.ManipSettings(cmyk=True, cmyk_mode=p["mode"], target=t.icc, source=p["source"],
                                    intent=t.intent or "relative", bpc=bool(s.bpc), gray_to_k=bool(s.gray_to_k),
                                    output_intent=False)
            cmyk.convert_pdf(src, work, ms)
        else:
            shutil.copyfile(src, work)
        step(2, tr("Bette Output Intent ein …"))
        if p["tag_rgb"]:
            pdf = pikepdf.open(work, allow_overwriting_input=True)
            try:
                tag_rgb_srgb(pdf)
                pdf.save(work)
            finally:
                pdf.close()
        cmyk.embed_output_intent(work, t.icc)
        step(3, tr("Prüfe das Ergebnis …"))
        with open(work, "rb") as fh:
            out = fh.read()
        after = colorcheck.facts(out, t, cancel=cancel)
        findings = colorcheck.check(after, t, cfg)
        report = report_text(os.path.basename(src), t, s, p, before, after, findings)
        from .core import _write_atomic
        _write_atomic(dst, out)
        pkg = ""
        if s.package:
            step(4, tr("Packe …"))
            pkg = os.path.splitext(dst)[0] + "_Druckerei.zip"
            tmpzip = pkg + ".part"
            with zipfile.ZipFile(tmpzip, "w", zipfile.ZIP_DEFLATED) as z:
                z.write(dst, os.path.basename(dst))
                z.write(t.icc, "ICC/" + os.path.basename(t.icc))
                if p["source"] and os.path.realpath(p["source"]) != os.path.realpath(t.icc):
                    z.write(p["source"], "ICC/" + os.path.basename(p["source"]))
                z.writestr(tr("Bericht.txt"), report.encode("utf-8"))
            os.replace(tmpzip, pkg)
        step(5, "")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    skip = {"rgb"} if p["tag_rgb"] else set()                  # RGB bewusst weitergegeben
    notes = list(p["notes"]) + [x.title for x in findings if x.severity in ("error", "warning") and x.key not in skip]
    if pkg:
        notes.append(tr("Paket: {0}").format(pkg))
    info = {"mode": p["mode"], "target": t.name, "output_intent": t.name,
            "tac_before": before.tac["max"] if before.tac else None,
            "tac_after": after.tac["max"] if after.tac else None, "package": pkg}
    return {"info": info, "notes": notes, "report": report, "findings": findings, "package": pkg, "plan": p}
