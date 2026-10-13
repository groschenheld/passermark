# Passermark Schritt-2-Diagnose (14.10.2026)
# Ins Repo-Root legen (dort, wo der Ordner "pdfdruck" liegt), daneben muss
# visitenkarten2.pdf liegen. Dann:  python3 diagnose_schritt2.py
# Anschließend: die GESAMTE Textausgabe hier zurückkopieren UND die erzeugte
# Datei schritt2-test.pdf in Passermark öffnen und prüfen:
#   - Sitzt der A4-Block mittig auf dem 320x450-Ziel?
#   - Sind die Schnittmarken sichtbar?
import os
import tempfile

import pypdfium2 as pdfium

from pdfdruck import layout

MM = layout.MM
HERE = os.path.dirname(os.path.abspath(__file__))
PDF = os.path.join(HERE, "visitenkarten2.pdf")

doc = pdfium.PdfDocument(PDF)
sizes = [doc.get_page_size(i) for i in range(len(doc))]
trims = layout.page_trims(doc)
bleeds = layout.page_doc_bleeds(doc)
print("== Dokument")
print("Seiten:", len(sizes))
print("size[0] (pt):", sizes[0], "= %.1f x %.1f mm" % (sizes[0][0] / MM, sizes[0][1] / MM))
print("trim[0] (pt):", trims[0] if trims and trims[0] else "-",
      " doc_bleeds[0]:", bleeds[0] if bleeds else "-")

# === Schritt 1: wie im Druckdialog (A4, Raster 3x3, Überfüller an Überfüller, Marken an) ===
s = layout.LayoutSettings(step_repeat=True, sr_mode="grid", sr_cols=3, sr_rows=3,
                          sr_join="bleed", crop_marks=True, sr_pass2=True,
                          sr2_w_mm=320.0, sr2_h_mm=450.0)
sheet = layout.Sheet(595.28, 841.89, None)          # A4 ohne Rand
plans1 = layout.plan(sizes, list(range(len(sizes))), sheet, s, trims, bleeds)
sp = plans1[0]
print("\n== Schritt 1 (A4, geplant)")
print("Bögen:", len(plans1), "| Nutzen je Bogen:", len(sp.placements),
      "| Marken je Bogen:", len(sp.marks), "| landscape:", sp.landscape)
print("Warnungen:", sp.warnings)
print("Nutzen 0: x=%.1f y=%.1f w=%.1f h=%.1f bleed=%.1f trim=%s"
      % (sp.placements[0].x, sp.placements[0].y, sp.placements[0].w,
         sp.placements[0].h, sp.placements[0].bleed, sp.placements[0].trim))
xs = [v for pl in sp.placements for v in (pl.x, pl.x + pl.w)]
ys = [v for pl in sp.placements for v in (pl.y, pl.y + pl.h)]
print("Block X: %.1f .. %.1f (Blatt 595.3 breit?landscape=%s)" % (min(xs), max(xs), sp.landscape))
print("Block Y: %.1f .. %.1f" % (min(ys), max(ys)))

# === Schritt 1 montieren ===
mid = layout.impose(doc, sheet, plans1)
print("\n== Schritt 1 montiert")
print("Seiten:", len(mid), "| Größe (pt):", mid.get_page_size(0))


def count_objs(d, i):
    pg = d[i]
    n = 0
    for o in pg.get_objects():
        n += 1
    pg.close()
    return n


print("Objekte auf Seite 0:", count_objs(mid, 0))

# === Flat zwischenspeichern + neu laden (genau wie impose_step2) ===
fd, tmp = tempfile.mkstemp(prefix="passermark-diag-", suffix=".pdf")
os.close(fd)
mid.save(tmp)
mid.close()
flat = pdfium.PdfDocument(tmp)
print("\n== Flach neu geladen")
print("Seiten:", len(flat), "| Größe (pt):", flat.get_page_size(0),
      "| Objekte Seite 0:", count_objs(flat, 0))

# === Schritt 2 planen ===
plans2 = layout.plan_step2((sheet.width, sheet.height), len(plans1), s)
sp2 = plans2[0]
print("\n== Schritt 2 (Ziel 320x450, geplant)")
print("Zielbögen:", len(plans2), "| je Bogen:", len(sp2.placements),
      "| landscape:", sp2.landscape, "| Warnungen:", sp2.warnings)
for pl in sp2.placements:
    print("  src=%d rot=%d x=%.1f y=%.1f w=%.1f h=%.1f" % (pl.src, pl.rot, pl.x, pl.y, pl.w, pl.h))
tgt = layout.step2_sheet(s)
LW, LH, area = layout._logical(tgt, sp2.landscape)
bxs = [v for pl in sp2.placements for v in (pl.x, pl.x + pl.w)]
bys = [v for pl in sp2.placements for v in (pl.y, pl.y + pl.h)]
print("Ziel logisch: %.1f x %.1f pt | Rand links %.1f / rechts %.1f | unten %.1f / oben %.1f"
      % (LW, LH, min(bxs), LW - max(bxs), min(bys), LH - max(bys)))

# === Schritt 2 montieren ===
out = layout.impose(flat, tgt, plans2)
print("\n== Schritt 2 montiert")
print("Seiten:", len(out), "| Größe (pt):", out.get_page_size(0),
      "| Objekte Seite 0:", count_objs(out, 0))
dst = os.path.join(HERE, "schritt2-test.pdf")
out.save(dst)
out.close()
flat.close()
os.unlink(tmp)
print("\nFertig:", dst)
print("-> Bitte die komplette obige Ausgabe zurückkopieren + sagen, was in")
print("   schritt2-test.pdf zu sehen ist (mittig? Marken?).")
