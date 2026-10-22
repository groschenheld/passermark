# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Colour check of a document against a printing condition – facts, findings, recommendations. No Qt.

facts()     what is in the PDF: RGB/CMYK/grey/Lab per page, RGB images (with/without ICC), spot colours,
            output intent, transparency, missing fonts, maximum ink coverage (Ghostscript: exact for the target,
            otherwise estimated from the CMYK content)
check()     findings with plain text and – where something can be done – an action:
              convert      CMYK conversion (method rgb_only/all, source profile) -> job "press"
              embed_oi     embed the target profile as output intent -> job "press" (cmyk_mode "none")
              preflight    fonts etc. -> document check
              measure      measure the paper white of the material
              get_profiles fetch standard profiles
              choose_target choose another printing condition
Everything here only reads – the GUI (gui/colorpanel.py), the assistant (gui/pressdialog.py) and the job
"press" (pressexport.py) act on it.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from .l10n import tr

SEV_ORDER = {"error": 0, "warning": 1, "info": 2, "ok": 3}


@dataclass
class Target:
    """Printing condition to check against (from colorlab.proof_choices or a profile file)."""
    icc: str = ""
    name: str = ""
    space: str = ""              # CMYK | RGB | Gray
    intent: str = "relative"
    material: str = ""           # Name des Materials ("" = nur Profil)
    material_id: str = ""
    white: list | None = None    # gemessenes Papierweiß des Materials (Lab D50)
    surface: str = ""            # Oberfläche des Materials
    tac_limit: int = 0           # 0 = Richtwert aus dem Profil

    @property
    def limit(self) -> int:
        if self.tac_limit:
            return int(self.tac_limit)
        from . import usercolor
        return usercolor.tac_limit_for(self.icc)


def target_from_choice(choice: dict | None, cfg: dict | None = None, intent: str = "") -> Target:
    if not choice:
        return Target()
    from . import colorlab
    m = colorlab.material_by_id(cfg or {}, choice.get("material") or "") if choice.get("material") else None
    return Target(icc=choice["icc"], name=choice.get("name") or colorlab.profile_desc(choice["icc"]),
                  space=choice.get("space") or colorlab.profile_space(choice["icc"]),
                  intent=intent or choice.get("intent") or "relative",
                  material=(m.get("name") or m["id"]) if m else "", material_id=m["id"] if m else "",
                  white=list(m["white"]) if m and m.get("white") else None,
                  surface=(m.get("surface") or "") if m else "")


def target_from_file(icc: str, intent: str = "relative") -> Target:
    from . import colorlab
    return Target(icc=icc, name=colorlab.profile_desc(icc), space=colorlab.profile_space(icc), intent=intent)


@dataclass
class Facts:
    pages: int = 0
    page_colors: dict = field(default_factory=dict)      # Seite (1-basiert) -> {"RGB", "CMYK", …}
    rgb_pages: list = field(default_factory=list)
    cmyk_pages: list = field(default_factory=list)
    gray_pages: list = field(default_factory=list)
    lab_pages: list = field(default_factory=list)
    rgb_images: list = field(default_factory=list)       # [imagecheck.ImageUse]
    rgb_tagged: int = 0                                  # davon mit eingebettetem ICC-Profil
    spots: dict = field(default_factory=dict)            # Sonderfarbe -> [Seiten]
    output_intents: list = field(default_factory=list)   # Bezeichnungen der Output Intents
    transparency: list = field(default_factory=list)     # Seiten
    fonts_missing: list = field(default_factory=list)    # [(Name, [Seiten])]
    tac: dict | None = None                              # {"max", "page", "over_pct", "limit", "method", "pages"}
    truncated: bool = False

    @property
    def has_cmyk(self) -> bool:
        return bool(self.cmyk_pages)

    @property
    def has_rgb(self) -> bool:
        return bool(self.rgb_pages)


@dataclass
class Finding:
    key: str
    severity: str                # error | warning | info | ok
    title: str
    text: str = ""
    spots: list = field(default_factory=list)            # [preflight.Spot]
    action: str = ""
    params: dict = field(default_factory=dict)
    action_label: str = ""


def _pages_str(pages) -> str:
    from .preflight import _pages_str as ps
    return ps(sorted(set(pages)))


# --------------------------------------------------------------------------- #
# Fakten
# --------------------------------------------------------------------------- #
def facts(data: bytes, target: Target | None = None, tac: bool = True, tac_pages: int = 12, cancel=None) -> Facts:
    """Was im Dokument steckt (pikepdf, darf im Hintergrund laufen; Ghostscript nur für den Farbauftrag)."""
    from . import colorlab, preflight
    rep = preflight.analyze(data, deep_layers=False, pdfium_parts=False)
    f = Facts(pages=rep.pages)
    cr = rep.colors
    if cr is not None:
        f.page_colors = {p: set(s) for p, s in cr.page_colors.items()}
        f.truncated = cr.truncated
        for p, s in sorted(cr.page_colors.items()):
            kinds = {_base(x) for x in s}
            if "RGB" in kinds:
                f.rgb_pages.append(p)
            if "CMYK" in kinds:
                f.cmyk_pages.append(p)
            if "Grau" in kinds:
                f.gray_pages.append(p)
            if "Lab" in kinds:
                f.lab_pages.append(p)
        for u in cr.images:
            if not u.mask and _base(u.space) == "RGB":
                f.rgb_images.append(u)
                if u.profile:
                    f.rgb_tagged += 1
        for p, names in cr.spots.items():
            for n in names:
                f.spots.setdefault(n, []).append(p)
    f.output_intents, _ = colorlab.doc_color_facts(data)
    if not f.output_intents and cr is not None and cr.output_intent:
        f.output_intents = [cr.output_intent]
    f.transparency = sorted(p for p, k in rep.transparency.items() if k - {"overprint"})
    for font in rep.fonts:
        if font.status in ("missing",):
            f.fonts_missing.append((font.name, sorted(font.pages)))
    if tac and target is not None and target.space == "CMYK" and target.icc and (f.has_cmyk or f.has_rgb
                                                                                  or f.gray_pages):
        try:
            f.tac = measure_tac(data, target, max_pages=tac_pages, cancel=cancel)
        except Exception:
            f.tac = None
    return f


def _base(space: str) -> str:
    """„Indiziert (RGB)“ -> RGB, „RGB“ -> RGB …"""
    s = space or ""
    if "(" in s and s.endswith(")") and not s.startswith(("DeviceN", "Sonderfarbe")):
        s = s[s.index("(") + 1:-1]
    return s if s in ("RGB", "CMYK", "Grau", "Lab") else ""


def measure_tac(data: bytes, target: Target, dpi: int = 30, max_pages: int = 12, cancel=None) -> dict | None:
    """Maximaler Farbauftrag in %, wie er gedruckt würde: mit Ghostscript die Seiten in CMYK des Ziels rechnen
        (RGB/Grau nach dem Zielprofil, vorhandenes CMYK bleibt) – ohne Ghostscript eine Schätzung aus dem
        vorhandenen CMYK (Farbwerte und CMYK-Bilder)."""
    from . import cmyk
    limit = target.limit
    gs = cmyk.ghostscript()
    if gs:
        import tempfile
        import numpy as np
        from PIL import Image
        tmp = tempfile.mkdtemp(prefix="passermark-tac-")
        try:
            src = os.path.join(tmp, "in.pdf")
            with open(src, "wb") as fh:
                fh.write(data)
            s = cmyk.ManipSettings(cmyk=True, cmyk_mode="rgb_only", target=target.icc, intent=target.intent)
            import pikepdf
            with pikepdf.open(src) as pdf:
                n = len(pdf.pages)
            best, per = (0.0, 0, 0.0), {}
            for i in range(min(n, max_pages)):
                if cancel is not None and cancel():
                    break
                out = os.path.join(tmp, f"p{i}.tif")
                cmyk._render(gs, src, i, dpi, "tiff32nc", [*cmyk._permit(s), *cmyk.color_args(s)], out)
                im = Image.open(out)
                im.load()
                a = np.asarray(im.convert("CMYK") if im.mode != "CMYK" else im, dtype=np.uint16)
                tot = a.sum(axis=2) * (100.0 / 255.0)
                mx = float(tot.max()) if tot.size else 0.0
                over = float((tot > limit + 0.5).mean() * 100.0) if tot.size else 0.0
                per[i + 1] = round(mx)
                if mx > best[0]:
                    best = (mx, i + 1, over)
            return {"max": round(best[0]), "page": best[1], "over_pct": round(best[2], 2), "limit": limit,
                    "method": "gs", "pages": per, "checked": min(n, max_pages), "total": n}
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
    return estimate_tac(data, limit, cancel=cancel)


def estimate_tac(data: bytes, limit: int = 300, max_pages: int = 50, cancel=None) -> dict | None:
    """Farbauftrag ohne Ghostscript: höchste Summe der CMYK-Farbwerte (k/K, scn bei DeviceCMYK) und der CMYK-Bilder
        (verkleinert ausgewertet). RGB wird nicht berücksichtigt (das rechnet erst die Umwandlung)."""
    import io
    import pikepdf
    best, per = (0.0, 0), {}
    with pikepdf.open(io.BytesIO(data)) as pdf:
        n = len(pdf.pages)
        for i, page in enumerate(pdf.pages):
            if i >= max_pages or (cancel is not None and cancel()):
                break
            mx = 0.0
            try:
                for ins in pikepdf.parse_content_stream(page):
                    if str(ins.operator) in ("k", "K") and len(ins.operands) == 4:
                        mx = max(mx, sum(float(v) for v in ins.operands) * 100.0)
            except Exception:
                pass
            res = page.obj.get("/Resources") or {}
            for _n, x in (res.get("/XObject") or {}).items():
                mx = max(mx, _image_tac(x))
            if mx:
                per[i + 1] = round(mx)
            if mx > best[0]:
                best = (mx, i + 1)
    if not per:
        return None
    return {"max": round(best[0]), "page": best[1], "over_pct": None, "limit": limit, "method": "estimate",
            "pages": per, "checked": min(n, max_pages), "total": n}


def _image_tac(x) -> float:
    import pikepdf
    try:
        if not isinstance(x, pikepdf.Stream) or x.get("/Subtype") != pikepdf.Name.Image:
            return 0.0
        img = pikepdf.PdfImage(x)
        if img.mode != "CMYK" and "CMYK" not in str(img.colorspace or ""):
            return 0.0
        if img.width * img.height > 40_000_000:
            return 0.0
        pil = img.as_pil_image()
        if pil.mode != "CMYK":
            return 0.0
        pil.thumbnail((400, 400))
        import numpy as np
        a = np.asarray(pil, dtype=np.uint16)
        return float(a.sum(axis=2).max()) * 100.0 / 255.0
    except Exception:
        return 0.0


# --------------------------------------------------------------------------- #
# Vergleich Druckbedingungen
# --------------------------------------------------------------------------- #
_COND = re.compile(r"(fogra\s*\d+|crpc\s*\d+|gracol|swop|pso\s*coated|pso\s*uncoated|isocoated|isouncoated)", re.I)


def condition_keys(text: str) -> set:
    """Kennungen einer Druckbedingung aus Namen/Dateinamen: {"fogra39", "isocoated"} …"""
    t = (text or "").lower()
    keys = {re.sub(r"\s+", "", m.group(1).lower()) for m in _COND.finditer(t)}
    if re.search(r"pso\s*coated\s*v3|psocoated_?v3", t):
        keys.add("fogra51")
    if re.search(r"pso\s*uncoated\s*v3|psouncoated_?v3", t):
        keys.add("fogra52")
    if re.search(r"iso\s*coated\s*v2|isocoated_?v2", t):
        keys.add("fogra39")
    return keys


def same_condition(oi: str, icc: str) -> bool:
    """Ist der Output Intent (Bezeichnung) dieselbe Druckbedingung wie das Profil?"""
    from . import colorlab
    a = condition_keys(oi)
    names = f"{colorlab.profile_desc(icc)} {os.path.basename(icc)}" if icc else ""
    b = condition_keys(names)
    fa = {k for k in a if k.startswith(("fogra", "crpc"))}
    fb = {k for k in b if k.startswith(("fogra", "crpc"))}
    if fa and fb:
        return bool(fa & fb)
    na = re.sub(r"[^a-z0-9]", "", (oi or "").lower())
    nb = re.sub(r"[^a-z0-9]", "", colorlab.profile_desc(icc).lower()) if icc else ""
    return bool(na and nb and (na in nb or nb in na))


def source_profile_for(oi: str, cfg: dict | None = None) -> str:
    """Installiertes Profil zur Ausgabebedingung oi (für „alles neu separieren“) – "" = keins gefunden."""
    from . import colorlab
    for c in colorlab.candidates(cfg or {}):
        if c["space"] == "CMYK" and same_condition(oi, c["file"]):
            return c["file"]
    return ""


# --------------------------------------------------------------------------- #
# Befunde
# --------------------------------------------------------------------------- #
def check(f: Facts, t: Target, cfg: dict | None = None) -> list:
    """Befunde mit Empfehlung – schlimmste zuerst."""
    from . import colorlab
    from .preflight import Spot
    out: list[Finding] = []
    pagespots = lambda pages: [Spot(p) for p in sorted(set(pages))]          # noqa: E731

    if not t.icc:
        out.append(Finding("no_target", "info", tr("Keine Druckbedingung gewählt"),
                           tr("Oben das Material oder Profil wählen, auf dem gedruckt wird – erst dann lässt sich "
                              "sagen, was zu tun ist."), action="choose_target",
                           action_label=tr("Druckbedingung wählen …")))
    cmyk_target = t.space == "CMYK"
    if t.icc and not cmyk_target:
        out.append(Finding("rgb_target", "info", tr("Druckerprofil ({0}) gewählt").format(t.space),
                           tr("Für den eigenen Drucker rechnet Passermark beim Drucken selbst um – vorher umwandeln ist "
                              "nicht nötig. Für eine Druckerei eine CMYK-Druckbedingung wählen (z. B. PSO Coated v3).")))

    ois = [o for o in f.output_intents if o]
    oi = ois[0] if ois else ""
    oi_other = bool(cmyk_target and oi and not same_condition(oi, t.icc))
    convert_all = None
    if oi_other and f.has_cmyk:
        src = source_profile_for(oi, cfg)
        convert_all = {"cmyk_mode": "all", "source": src}
        txt = tr("Die Datei ist für „{0}“ separiert, gedruckt wird auf „{1}“. Die CMYK-Werte passen nicht zum Papier – "
                 "Farben werden zu dunkel/zu bunt oder zu flau.").format(oi, t.name)
        txt += " " + (tr("Empfehlung: alles neu separieren ({0} → {1}).").format(oi, t.name) if src else
                      tr("Empfehlung: alles neu separieren. Das Profil „{0}“ ist nicht installiert – „Standardprofile "
                         "holen …“, sonst rechnet Ghostscript mit seinem Standard-CMYK.").format(oi))
        out.append(Finding("oi_other", "warning", tr("Datei für eine andere Druckbedingung angelegt"), txt,
                           pagespots(f.cmyk_pages), "convert", dict(convert_all, target=t.icc),
                           tr("Neu separieren …")))

    if cmyk_target and f.has_rgb:
        n, tagged = len(f.rgb_images), f.rgb_tagged
        parts = []
        if n:
            parts.append(tr("{0} RGB-Bild(er), davon {1} mit eingebettetem Profil").format(n, tagged))
        vec = sorted(set(f.rgb_pages) - {u.page for u in f.rgb_images})
        if vec:
            parts.append(tr("RGB-Flächen/Text auf Seite {0}").format(_pages_str(vec)))
        txt = "; ".join(parts) + ". " + tr(
            "Ohne Umwandlung rechnet erst die Druckerei (RIP) mit ihren Einstellungen um – Farben können abweichen, "
            "kräftiges RGB-Grün/-Blau wird im Druck flauer.")
        if convert_all is None:
            txt += " " + tr("Empfehlung: nach „{0}“ umwandeln – vorhandenes CMYK bleibt unverändert. Alternativ RGB mit "
                            "Profil weitergeben (PDF/X-4 erlaubt das), dann rechnet die Druckerei.").format(t.name)
        spots = [Spot(u.page, u.bbox, f"{u.px[0]} × {u.px[1]} px" + (f", {u.profile}" if u.profile else ""))
                 for u in f.rgb_images[:200]] + [Spot(p) for p in vec]
        out.append(Finding("rgb", "warning", tr("RGB-Inhalte auf Seite {0}").format(_pages_str(f.rgb_pages)), txt,
                           spots, "convert",
                           dict(convert_all or {"cmyk_mode": "rgb_only", "source": ""}, target=t.icc, rgb_ask=True),
                           tr("Umwandeln …")))

    if f.lab_pages:
        out.append(Finding("lab", "info", tr("Lab-Farben auf Seite {0}").format(_pages_str(f.lab_pages)),
                           tr("Geräteunabhängige Farben – werden bei der Umwandlung mit dem Zielprofil gerechnet."),
                           pagespots(f.lab_pages)))

    if cmyk_target:
        if not oi:
            if f.has_cmyk and convert_all is None:
                out.append(Finding("cmyk_unknown", "info", tr("CMYK ohne Angabe der Druckbedingung"),
                                   tr("Die Datei sagt nicht, für welches Papier das CMYK gedacht ist. Passermark nimmt "
                                      "„{0}“ an – stimmt das nicht, über „Neu separieren“ das richtige Quellprofil "
                                      "wählen.").format(t.name), pagespots(f.cmyk_pages)))
            out.append(Finding("oi_missing", "warning", tr("Kein Output Intent"),
                               tr("Die Druckerei sieht nicht, für welche Druckbedingung die Datei gemacht ist. Das "
                                  "Zielprofil als Output Intent einbetten – bei „Für Druckerei ausgeben“ passiert das "
                                  "immer."), [], "embed_oi", {"target": t.icc}, tr("Einbetten")))
        elif not oi_other:
            out.append(Finding("oi_ok", "ok", tr("Output Intent „{0}“ passt zum Ziel").format(oi)))
        elif not f.has_cmyk:
            out.append(Finding("oi_replace", "info", tr("Output Intent „{0}“ wird ersetzt").format(oi),
                               tr("Die Datei enthält kein CMYK – bei der Umwandlung wird „{0}“ als Output Intent "
                                  "eingetragen.").format(t.name), [], "embed_oi", {"target": t.icc},
                               tr("Einbetten")))

    if cmyk_target and f.tac:
        tc = f.tac
        lim = tc["limit"]
        est = tc["method"] != "gs"
        how = tr(" (geschätzt, ohne Ghostscript nur das vorhandene CMYK)") if est else ""
        part = "" if tc.get("checked", 0) >= tc.get("total", 0) else tr(" – geprüft: die ersten {0} Seiten").format(
            tc.get("checked"))
        if tc["max"] > lim + 0.5:
            sev = "error" if tc["max"] > lim + 30 else "warning"
            over = [p for p, v in (tc.get("pages") or {}).items() if v > lim + 0.5]
            area = "" if tc.get("over_pct") is None else tr(", {0:.1f} % der Fläche darüber").format(tc["over_pct"])
            txt = tr("Höchster Farbauftrag {0} % auf Seite {1}{2} – Richtwert für „{3}“: {4} %. Zu viel Farbe trocknet "
                     "schlecht, schlägt durch oder klebt.").format(tc["max"], tc["page"], area, t.name, lim) + how + part
            txt += " " + tr("Empfehlung: mit dem Zielprofil neu separieren – das Profil begrenzt den Farbauftrag.")
            params = dict(convert_all or {"cmyk_mode": "all", "source": source_profile_for(oi, cfg) if oi else ""},
                          target=t.icc)
            if not params.get("source") and not oi_other:
                params["source"] = t.icc                     # CMYK ist schon für das Ziel – nur begrenzen
            out.append(Finding("tac", sev, tr("Farbauftrag zu hoch ({0} % > {1} %)").format(tc["max"], lim), txt,
                               pagespots(over or [tc["page"]]), "convert", params, tr("Neu separieren …")))
        else:
            out.append(Finding("tac_ok", "ok", tr("Farbauftrag höchstens {0} % (Richtwert {1} %)").format(
                tc["max"], lim), how.strip() + part))

    if f.spots:
        names = sorted(f.spots)
        pages = sorted({p for v in f.spots.values() for p in v})
        out.append(Finding("spots", "info", tr("Sonderfarben: {0}").format(", ".join(names[:6]) + (" …" if len(names) > 6
                                                                                                else "")),
                           tr("Mit der Druckerei klären, ob sie als eigene Farbe gedruckt werden. Sonst werden sie in "
                              "CMYK nachgebildet – bei Schmuckfarben (Pantone, HKS) oft sichtbar anders. Schnitt-/"
                              "Stanzlinien (CutContour, Stanze) bleiben, wie sie sind."), pagespots(pages)))

    if t.icc and t.material:
        pw = colorlab.profile_white(t.icc)
        if t.white and pw:
            de = colorlab.delta_e(t.white, pw)
            if de > 4:
                out.append(Finding("paper", "warning", tr("Papierweiß passt nicht zum Profil (ΔE {0:.1f})").format(de),
                                   tr("Gemessen {0}, Profil {1}: {2}. Ein Profil mit ähnlichem Papierweiß wählen oder "
                                      "für dieses Papier ein eigenes Profil erstellen.").format(
                                       colorlab.fmt_lab(t.white), colorlab.fmt_lab(pw), colorlab.verdict(de)),
                                   [], "get_profiles", {"surface": t.surface}, tr("Passende Profile …")))
            else:
                out.append(Finding("paper_ok", "ok", tr("Papierweiß passt zum Profil (ΔE {0:.1f})").format(de)))
        elif not t.white:
            out.append(Finding("paper_unmeasured", "info", tr("Papierweiß von „{0}“ nicht gemessen").format(t.material),
                               tr("Mit Messgerät, Messdatei oder von Hand eintragen – dann zeigt der Softproof das "
                                  "echte Papier und die Vorschläge werden genauer."), [], "measure",
                               {"material": t.material_id}, tr("Papier messen …")))
        ps = colorlab.guess_surface(f"{t.name} {os.path.basename(t.icc)}")
        if t.surface and ps and colorlab._surface_group(ps) != colorlab._surface_group(t.surface):
            out.append(Finding("surface", "warning", tr("Profil für {0}, Papier ist {1}").format(
                colorlab.surface_label(ps), colorlab.surface_label(t.surface)),
                tr("Gestrichenes und ungestrichenes Papier brauchen verschiedene Profile – ungestrichenes saugt mehr "
                   "Farbe, Bilder werden sonst dunkel und matschig."), [], "get_profiles", {"surface": t.surface},
                tr("Passende Profile …")))

    if f.transparency:
        out.append(Finding("transparency", "info", tr("Transparenz auf Seite {0}").format(_pages_str(f.transparency)),
                           tr("PDF/X-4 erlaubt Transparenz, die meisten Druckereien verarbeiten sie direkt. Verlangt die "
                              "Druckerei PDF/X-1a oder X-3: in der Dokumentprüfung reduzieren."),
                           pagespots(f.transparency), "preflight", {}, tr("Dokumentprüfung …")))

    if f.fonts_missing:
        names = [n for n, _ in f.fonts_missing]
        pages = sorted({p for _, ps in f.fonts_missing for p in ps})
        out.append(Finding("fonts", "error", tr("Nicht eingebettete Schriften: {0}").format(
            ", ".join(names[:4]) + (" …" if len(names) > 4 else "")),
            tr("Die Druckerei hat diese Schriften nicht – Text kann anders aussehen oder fehlen. In der Dokumentprüfung "
               "einbetten oder in Pfade wandeln."), pagespots(pages), "preflight", {}, tr("Dokumentprüfung …")))

    if t.icc and not any(x.severity in ("error", "warning") for x in out):
        out.append(Finding("ready", "ok", tr("Bereit für „{0}“").format(t.name),
                           tr("Nichts Kritisches gefunden. Mit „Für Druckerei ausgeben“ wird der Output Intent "
                              "sicher eingetragen und auf Wunsch ein Paket mit Profil und Bericht erstellt.")))
    out.sort(key=lambda x: SEV_ORDER.get(x.severity, 9))
    return out


def summary(f: Facts) -> list:
    """Kurzfassung der Fakten für die Anzeige: [(Bezeichnung, Wert)]."""
    rows = [(tr("Seiten"), str(f.pages))]
    kinds = []
    for label, pages in ((tr("RGB"), f.rgb_pages), (tr("CMYK"), f.cmyk_pages), (tr("Grau"), f.gray_pages),
                         (tr("Lab"), f.lab_pages)):
        if pages:
            kinds.append(f"{label} ({tr('S.')} {_pages_str(pages)})")
    rows.append((tr("Farbräume"), ", ".join(kinds) or tr("keine erkannt")))
    if f.rgb_images:
        rows.append((tr("RGB-Bilder"), tr("{0}, davon {1} mit Profil").format(len(f.rgb_images), f.rgb_tagged)))
    if f.spots:
        rows.append((tr("Sonderfarben"), ", ".join(sorted(f.spots))))
    rows.append((tr("Output Intent"), ", ".join(f.output_intents) or tr("keiner")))
    if f.tac:
        rows.append((tr("Farbauftrag max."), f"{f.tac['max']} %" + (tr(" (geschätzt)") if f.tac["method"] != "gs"
                                                                       else "")))
    if f.transparency:
        rows.append((tr("Transparenz"), tr("S.") + " " + _pages_str(f.transparency)))
    if f.fonts_missing:
        rows.append((tr("Schriften fehlen"), ", ".join(n for n, _ in f.fonts_missing)))
    return rows
