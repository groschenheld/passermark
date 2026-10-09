# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Erzeugt die Beispiele für Variable Daten in pdfdruck/docs/beispiele/vdp (Vorlage, CSV, Presets, Ergebnisse).

    python3 docs/make_vdp_examples.py

Die Presets verweisen relativ auf daten.csv; „Beispiele holen“ (Programm bzw. passermark-cli beispiele) kopiert den
Ordner zum Benutzer und trägt die Presets mit vollem Pfad ein.
"""
import os
import shutil
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from reportlab.lib.units import mm  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

from pdfdruck import core, vdp  # noqa: E402
from pdfdruck.examples import EXAMPLES, VDP_DIR  # noqa: E402
from pdfdruck.vdp import Numbering, VdpField, VdpSettings  # noqa: E402

CSV = ("Name;Ort;Artikelnummer;EAN\n"
       "Anna Huber;Wien;ART-1001;4006381333931\n"
       "Bernd Gruber;Graz;ART-1002;978316148410\n"
       "Clara Wimmer;Linz;ART-1003;5901234123457\n")


def T(content, x, y, w=60, h=8, size=12):
    return VdpField("text", content, x, y, w, h, size_pt=size)


SETTINGS = {
    "beispiel-1-qr-nummer": VdpSettings(count=5, numbering=Numbering(digits=4), fields=[
        VdpField("qr", "https://deinefirma.at/ticket/{{nr}}", 100, 25, 35, 35),
        T("Ticket {{nr}}", 10, 30, size=16),
        T("QR-Inhalt: https://deinefirma.at/ticket/{{nr}}", 10, 85, 85, 6, 8)]),
    "beispiel-2-qr-csv": VdpSettings(csv_path="daten.csv", fields=[
        VdpField("qr", "{{Name}} – {{Ort}}", 100, 25, 35, 35),
        T("{{Name}}", 10, 30, size=16), T("{{Ort}}", 10, 42),
        T("QR-Inhalt: {{Name}} – {{Ort}}", 10, 85, 85, 6, 8)]),
    "beispiel-3-code128": VdpSettings(csv_path="daten.csv", numbering=Numbering(digits=4), fields=[
        VdpField("code128", "T{{nr}}", 10, 28, 60, 18, size_pt=9),
        T("oben: T{{nr}}  (Nummerierung, Stellen 4)", 10, 50, 120, 6, 8),
        VdpField("code128", "{{Artikelnummer}}", 10, 62, 60, 18, size_pt=9),
        T("unten: {{Artikelnummer}}  (aus der CSV)", 10, 84, 120, 6, 8)]),
    "beispiel-4-ean13": VdpSettings(csv_path="daten.csv", numbering=Numbering(prefix="2012345", digits=5), fields=[
        VdpField("ean13", "{{EAN}}", 10, 25, 45, 28),
        T("links: {{EAN}} aus der CSV", 10, 56, 60, 6, 8),
        VdpField("ean13", "{{nr}}", 80, 25, 45, 28),
        T("rechts: {{nr}}", 80, 56, 60, 6, 8),
        T("(Nummerierung: Vorsatz 2012345, Stellen 5)", 80, 61, 60, 6, 8)]),
}


def main():
    out = VDP_DIR
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(os.path.join(out, "presets"))
    os.makedirs(os.path.join(out, "ergebnis"))
    w, h = 148 * mm, 105 * mm
    c = canvas.Canvas(os.path.join(out, "vorlage-a6.pdf"), pagesize=(w, h))
    c.setTitle("Passermark – Beispiel-Vorlage")
    c.setStrokeColorRGB(.6, .6, .6)
    c.rect(5 * mm, 5 * mm, w - 10 * mm, h - 10 * mm)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(10 * mm, h - 15 * mm, "Beispiel-Vorlage (Passermark VDP)")
    c.showPage()
    c.save()
    with open(os.path.join(out, "daten.csv"), "w", encoding="utf-8", newline="\n") as f:
        f.write(CSV)
    assert sorted(SETTINGS) == sorted(k for k, _ in EXAMPLES)
    for name, s in SETTINGS.items():
        core.save_settings(os.path.join(out, "presets", name + ".json"), "vdp", s)
        run = vdp.VdpSettings(**{**s.__dict__, "csv_path": os.path.join(out, s.csv_path) if s.csv_path else ""})
        data, _ = vdp.build(os.path.join(out, "vorlage-a6.pdf"), run)
        with open(os.path.join(out, "ergebnis", name + ".pdf"), "wb") as f:
            f.write(data)
    shutil.copy(os.path.join(ROOT, "docs", "vdp-liesmich.txt"), os.path.join(out, "LIESMICH.txt"))
    print(out)


if __name__ == "__main__":
    main()
