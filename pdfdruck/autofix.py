# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Repair everything that can be repaired automatically (1.20.2) – job ``autofix``.

The document is checked with a check profile; for every finding with an automatic repair one step is planned and
the steps run in a fixed order (layers, HDR pages, fonts, transparent gradients, spot colours, RGB -> CMYK,
overprint, bleed, PDF/X-4). Findings without an automatic repair (small images, small text, hairlines …) stay and are
reported afterwards. When the profile asks for PDF/X, the last step makes a PDF/X-4 file: output intent, version
marker in XMP, trim box, PDF 1.6, no encryption and no JavaScript.

Ghostscript is needed for fonts and the colour conversion; pdfium (render process) for transparent gradients.
"""

from __future__ import annotations

import datetime
import io
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field

from .l10n import tr

# step -> checks whose findings it repairs (order = order of execution)
STEPS = {
    "layers": ("layer_hidden", "layer_print"),
    "hdr": ("hdr",),
    "fonts": ("font_missing", "font_std14"),
    "softmask": ("transparency_gradient",),
    "spots": ("spot_count",),
    "cmyk": ("rgb",),
    "overprint": ("overprint_white", "overprint_black_text"),
    "bleed": ("bleed",),
    "pdfx": ("pdfx_none", "pdfx_version", "pdfx_intent", "pdfx_profile"),
}
LABELS = {
    "layers": "Ebenen festschreiben",
    "hdr": "HDR-Zusatzseiten entfernen",
    "fonts": "Schriften einbetten",
    "softmask": "Transparente Verläufe umwandeln",
    "spots": "Sonderfarben in CMYK umwandeln (Schneidkonturen bleiben)",
    "cmyk": "RGB in CMYK umwandeln",
    "overprint": "Überdrucken korrigieren",
    "bleed": "Anschnitt erzeugen",
    "pdfx": "Als PDF/X-4 ausweisen",
}
NEEDS_TARGET = {"cmyk", "pdfx"}  # need a CMYK printing condition (profile)


@dataclass
class AutofixSettings:
    """Settings of the job ``autofix``."""

    profile: str = ""  # check profile (name or .json); "" = standard
    steps: list = field(default_factory=list)  # only these steps (keys of STEPS); empty = all that are needed
    target: str = ""  # CMYK profile (.icc) for RGB -> CMYK and the output intent; "" = output intent of the file
    intent: str = "relative"
    bpc: bool = True
    layers: str = "print"  # print | view: which state the layers are flattened in
    font_map: dict = field(default_factory=dict)  # {font name: font file}
    bleed_mode: str = "mirror"  # mirror | stretch
    dpi: int = 300  # transparent gradients


@dataclass
class Step:
    """A planned repair: key, text, findings it answers, why it cannot run (empty: it can)."""

    key: str
    label: str
    findings: list
    blocked: str = ""


def plan(rep, s: AutofixSettings | None = None, has_target: bool | None = None) -> list[Step]:
    """Steps for the findings of ``rep`` (preflight.Report, already judged with the profile)."""
    s = s or AutofixSettings()
    by_check: dict = {}
    for i in rep.issues:
        by_check.setdefault(getattr(i, "check", ""), []).append(i)
    if has_target is None:
        has_target = bool(s.target) or bool(_oi_cmyk(rep))
    out = []
    for key, checks in STEPS.items():
        found = [i for c in checks for i in by_check.get(c, [])]
        if not found:
            continue
        st = Step(key, tr(LABELS[key]), found)
        if key in NEEDS_TARGET and not has_target:
            st.blocked = tr("Keine Druckbedingung (CMYK-Profil) gewählt und kein Output-Intent in der Datei.")
        out.append(st)
    return out


def _oi_cmyk(rep) -> bool:
    """The file has a PDF/X output intent with a profile (whether it is CMYK shows only run())."""
    p = rep.pdfx or {}
    return bool(p.get("intent")) and not p.get("no_profile")


def remaining(rep) -> list:
    """Findings (errors and warnings) without an automatic repair."""
    auto = {c for checks in STEPS.values() for c in checks}
    return [i for i in rep.issues if i.severity in ("error", "warning") and getattr(i, "check", "") not in auto]


def run(data: bytes, s: AutofixSettings, progress=None, cancel=None) -> tuple[bytes, list, object]:
    """Repair ``data`` -> (result, notes, report of the result with the same profile)."""
    from . import preflight

    rep = preflight.analyze(data, profile=s.profile or None)
    own = "" if s.target else _oi_file(data)  # temporary copy of the file's output intent
    target = s.target or own
    steps = [st for st in plan(rep, s, has_target=bool(target)) if not s.steps or st.key in s.steps]
    notes: list = []
    tmp = tempfile.mkdtemp(prefix="passermark-autofix-")
    try:
        for k, st in enumerate(steps):
            if cancel is not None and cancel():
                from .core import Cancelled

                raise Cancelled(tr("Abgebrochen."))
            if progress is not None:
                progress(k, len(steps), st.label + " …")
            if st.blocked:
                notes.append(tr("Übersprungen: {0} – {1}").format(st.label, st.blocked))
                continue
            try:
                data, more = _apply(st.key, data, rep, s, target, tmp)
            except Exception as e:  # noqa: BLE001 – one step fails (e.g. no Ghostscript): the others still run
                if type(e).__name__ == "Cancelled":
                    raise
                notes.append("✗ " + tr("{0} fehlgeschlagen: {1}").format(st.label, str(e).split("\n")[0]))
                continue
            notes.append("✓ " + st.label + ("" if not more else " – " + "; ".join(str(m) for m in more)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if own:
            try:
                os.remove(own)
            except OSError:
                pass
    after = preflight.analyze(data, profile=s.profile or None)
    rest = remaining(after)
    if rest:
        notes.append(tr("Bleibt (nicht automatisch reparierbar): {0}").format(len(rest)))
        notes += ["  • " + i.message for i in rest[:12]]
    if progress is not None:
        progress(len(steps), len(steps), "")
    return data, notes, after


def _oi_file(data: bytes) -> str:
    """CMYK output intent of the file as a temporary .icc (caller removes it) – "" if none."""
    import pikepdf

    try:
        with pikepdf.open(io.BytesIO(data)) as pdf:
            for oi in pdf.Root.get("/OutputIntents") or []:
                prof = oi.get("/DestOutputProfile")
                if prof is not None and int(prof.get("/N", 0)) == 4:
                    fd, path = tempfile.mkstemp(suffix=".icc", prefix="passermark-oi-")
                    with os.fdopen(fd, "wb") as fh:
                        fh.write(bytes(prof.read_bytes()))
                    return path
    except Exception:  # noqa: BLE001 – unreadable output intent: as if there was none
        pass
    return ""


def _apply(key: str, data: bytes, rep, s: AutofixSettings, target: str, tmp: str) -> tuple[bytes, list]:
    """One step -> (result, notes)."""
    from . import preflight

    if key == "layers":
        from . import pdflayers

        vis = {
            L.key for L in rep.layers if (L.print_on if s.layers == "print" and L.print_on is not None else L.view_on)
        }
        return pdflayers.flatten_layers(data, vis), [
            tr("wie beim Druck") if s.layers == "print" else tr("wie am Bildschirm")
        ]
    if key == "hdr":
        return preflight.remove_hdr_aux(data, "aux", False), []
    if key == "fonts":
        from . import fontlib

        return fontlib.embed_fonts(data, dict(s.font_map)), []
    if key == "softmask":
        from . import softmask

        out, more = softmask.flatten_softmask_paints(data, s.dpi, None)
        return out, list(more)
    if key == "spots":
        from . import colorrules

        out, more = colorrules.apply(
            data,
            colorrules.ColorRulesSettings(black_text=False, black_lines=False, to_process=["*"]),
        )
        return out, list(more)[:3]
    if key == "cmyk":
        from . import cmyk

        src, dst = os.path.join(tmp, "in.pdf"), os.path.join(tmp, "cmyk.pdf")
        with open(src, "wb") as fh:
            fh.write(data)
        cmyk.convert_pdf(
            src,
            dst,
            cmyk.ManipSettings(
                cmyk=True,
                cmyk_mode="rgb_only",
                target=target,
                intent=s.intent or "relative",
                bpc=bool(s.bpc),
                gray_to_k=True,
                output_intent=True,  # Ghostscript drops the output intent – the printing condition stays visible
            ),
        )
        with open(dst, "rb") as fh:
            return fh.read(), [os.path.basename(target) if target == s.target else tr("nach dem Output-Intent")]
    if key == "overprint":
        from . import overprint

        size = preflight.lim(rep, "black_text_pt") or overprint.TEXT_MAX_PT
        out, more = overprint.fix(data, black_text=bool(preflight.lim(rep, "black_text_pt")), text_max_pt=size)
        return out, list(more)[:2]
    if key == "bleed":
        from . import bleedgen

        pages = sorted({p - 1 for i in rep.issues if getattr(i, "check", "") == "bleed" for p in i.pages}) or None
        mm = preflight.lim(rep, "bleed_min_mm") or 3.0
        out, more = bleedgen.add_bleed(data, pages, mm, s.bleed_mode)
        return out, list(more)[:2]
    if key == "pdfx":
        return make_pdfx4(data, target, replace=bool(s.target)), []
    raise ValueError(key)


def make_pdfx4(data: bytes, icc: str = "", title: str = "", replace: bool = True) -> bytes:
    """Mark ``data`` as PDF/X-4: CMYK output intent (``icc`` – an existing one stays unless ``replace``), XMP with
    GTS_PDFXVersion, document and version id, trapped flag; trim box on every page (crop or media box) and the
    bleed box inside the media box; no JavaScript/open action scripts; PDF 1.6, unencrypted.
    Does not convert colours or embed fonts – that is done by the steps before."""
    import pikepdf

    from . import cmyk

    pdf = pikepdf.open(io.BytesIO(data))
    try:
        if icc and (replace or not pdf.Root.get("/OutputIntents")):
            with open(icc, "rb") as fh:
                cmyk._set_output_intent(pdf, fh.read(), cmyk._desc(icc))
        elif not pdf.Root.get("/OutputIntents"):
            raise ValueError(tr("PDF/X braucht einen Output-Intent – bitte eine Druckbedingung (CMYK-Profil) wählen."))
        for oi in pdf.Root.get("/OutputIntents") or []:
            oi.S = pikepdf.Name.GTS_PDFX
        for page in pdf.pages:
            o = page.obj
            mb = [float(v) for v in o.get("/MediaBox", [0, 0, 612, 792])]
            if "/TrimBox" not in o and "/ArtBox" not in o:
                o.TrimBox = o.get("/CropBox") or pikepdf.Array(mb)
            if "/BleedBox" in o:
                b = [float(v) for v in o.BleedBox]
                o.BleedBox = pikepdf.Array([max(b[0], mb[0]), max(b[1], mb[1]), min(b[2], mb[2]), min(b[3], mb[3])])
            if "/AA" in o:
                del o["/AA"]
        names = pdf.Root.get("/Names")
        if names is not None and "/JavaScript" in names:
            del names["/JavaScript"]
        oa = pdf.Root.get("/OpenAction")
        if isinstance(oa, pikepdf.Dictionary) and oa.get("/S") == "/JavaScript":
            del pdf.Root["/OpenAction"]
        if "/AA" in pdf.Root:
            del pdf.Root["/AA"]
        now = datetime.datetime.now(datetime.timezone.utc).astimezone()
        name = title or str(pdf.docinfo.get("/Title") or "") or tr("Dokument")
        with pdf.open_metadata(set_pikepdf_as_editor=False) as md:
            md["pdfxid:GTS_PDFXVersion"] = "PDF/X-4"
            md["pdf:Trapped"] = "False"
            md["dc:title"] = name
            md["xmp:CreatorTool"] = md.get("xmp:CreatorTool") or "Passermark"
            md["xmp:ModifyDate"] = now.isoformat()
            md["xmp:MetadataDate"] = now.isoformat()
            if not md.get("xmp:CreateDate"):
                md["xmp:CreateDate"] = now.isoformat()
            if not md.get("xmpMM:DocumentID"):
                md["xmpMM:DocumentID"] = f"uuid:{uuid.uuid4()}"
            md["xmpMM:InstanceID"] = f"uuid:{uuid.uuid4()}"
            md["xmpMM:VersionID"] = "1"
            md["xmpMM:RenditionClass"] = "default"
        pdf.docinfo["/Trapped"] = pikepdf.Name("/False")
        pdf.docinfo["/GTS_PDFXVersion"] = "PDF/X-4"
        if "/Title" not in pdf.docinfo:
            pdf.docinfo["/Title"] = name
        out = io.BytesIO()
        pdf.save(out, min_version="1.6", encryption=False, fix_metadata_version=False)
        return out.getvalue()
    finally:
        pdf.close()
