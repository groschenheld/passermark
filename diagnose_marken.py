# Passermark: Test „vorhandene dokumentseitige Marken verwenden“ (14.10.2026)
# Regel: Marken im Dokumentrand vorhanden -> am Blockrand verwenden (ohne eigenes
# Häkchen „Schnittmarken drucken“). Nur Überfüller vorhanden -> nichts zeichnen,
# aber per Häkchen zuschaltbar. Dieses Skript erzeugt beide Fälle als PDF.
# Ins Repo-Root legen (neben pdfdruck/ und visitenkarten2.pdf), dann:
#   python3 diagnose_marken.py
# Danach marken-vorhanden.pdf und marken-nur-ueberfueller.pdf in Passermark ansehen.
import os

import pypdfium2 as pdfium

from pdfdruck import layout

HERE = os.path.dirname(os.path.abspath(__file__))
PDF = os.path.join(HERE, "visitenkarten2.pdf")

doc = pdfium.PdfDocument(PDF)
sizes = [doc.get_page_size(i) for i in range(len(doc))]
trims = layout.page_trims(doc)
bleeds = layout.page_doc_bleeds(doc)
print("Dokument: trim[0] =", trims[0] if trims and trims[0] else "-",
      "| doc_bleeds[0] =", bleeds[0] if bleeds else "-")

sheet = layout.Sheet(595.28, 841.89, None)   # A4


def run(name, crop_marks, bleed_mm, join):
    s = layout.LayoutSettings(step_repeat=True, sr_mode="grid", sr_cols=3, sr_rows=3,
                              sr_join=join, crop_marks=crop_marks, bleed_mm=bleed_mm)
    plans = layout.plan(sizes, list(range(3)), sheet, s, trims, bleeds)
    sp = plans[0]
    outer = [bool(p.bleed_sides) for p in sp.placements]
    print("\n== %s (crop_marks=%s bleed=%.1fmm join=%s)" % (name, crop_marks, bleed_mm, join))
    print("Nutzen:", len(sp.placements), "| eigene Marken geplant:", len(sp.marks),
          "| Nutzen mit Außen-Überfüller:", sum(outer))
    out = layout.impose(doc, sheet, plans)
    pg = out[0]
    n = sum(1 for _ in pg.get_objects())
    pg.close()
    dst = os.path.join(HERE, "%s.pdf" % name.replace(" ", "_"))
    out.save(dst)
    out.close()
    print("-> %s  (Objekte Seite 0: %d)" % (dst, n))


# Fall A: dokumentseitige Marken vorhanden (im Rand) -> verwenden:
# Überfüller 11 mm reicht bis in den Rand, eigene Marken AUS.
run("marken-vorhanden", crop_marks=False, bleed_mm=11.0, join="bleed")

# Fall B: nur Überfüller -> eigene Marken zuschaltbar (hier: angeschaltet).
run("marken-zugeschaltet", crop_marks=True, bleed_mm=3.0, join="bleed")

print("\nBitte prüfen:")
print("1. marken-vorhanden.pdf  -> Sitzen die Marken aus dem Dokument am Außenrand des Blocks?")
print("2. marken-zugeschaltet.pdf -> Passermark-eigene Marken sichtbar (beim Häkchen)?")
print("Ausgabe hier zurückkopieren.")
