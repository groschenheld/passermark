# SPDX-License-Identifier: GPL-3.0-or-later
"""Bindungsschemata: Falz-Simulation (falzen, ineinanderstecken, Lagen stapeln -> muss 1…N ergeben),
Leerseiten, Bundzug, Marken, Ausschießen per Kommandozeile."""
import os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ.setdefault("PASSERMARK_LANG", "de")
from pdfdruck import layout
from pdfdruck.layout import LayoutSettings, Sheet, MM

A3 = Sheet(297 * MM, 420 * MM)
A4 = (210 * MM, 297 * MM)


def fold_read(sheets, binding="left"):
    """Physikalisches Modell, unabhängig von der Ausschieß-Formel: Bögen einer Lage (0 = außen) liegen
    ineinander, Rückseite über die kurze Kante gewendet (hinten-links liegt hinter vorne-rechts).
    Gelesen wird außen vorne beginnend, Blatt für Blatt bis zur Mitte und auf der anderen Hälfte zurück."""
    a, b = (1, 0) if binding == "left" else (0, 1)        # erste sichtbare Hälfte der Vorderseite
    first, second = [], []
    for front, back in sheets:
        first += [front[a], back[b]]
    for front, back in reversed(sheets):
        second += [back[a], front[b]]
    return first + second


def lagen_from_plans(plans, n_sheets_per_sig):
    """Aus den fertigen Bogenplänen (Platzierungen) wieder Bögen [vorne(l,r), hinten(l,r)] machen."""
    out = []
    LW = A3.height                                        # Querbogen: logische Breite = lange Kante
    for i in range(0, len(plans), 2):
        faces = []
        for sp in plans[i:i + 2]:
            slot = [None, None]
            for pl in sp.placements:
                slot[0 if pl.x + pl.w / 2 < LW / 2 else 1] = pl.src
            faces.append(slot)
        out.append(tuple(faces))
    return out


def run_all(n, kind, per_sig=4, binding="left", blanks="end"):
    s = LayoutSettings(handling="booklet", booklet_kind=kind, booklet_per_sig=per_sig, booklet_binding=binding,
                       booklet_blanks=blanks)
    plans = layout.plan_booklet([A4] * n, list(range(n)), A3, s)
    seq = layout.booklet_sequence(n, blanks)
    sigs = layout.signatures(len(seq), kind, per_sig)
    sheets = lagen_from_plans(plans, None)
    read = []
    pos = 0
    for sig in sigs:
        k = len(sig) // 4
        read += fold_read(sheets[pos:pos + k], binding)
        pos += k
    return read, seq


def test_fold_simulation_all_kinds():
    for kind, per in (("saddle", 4), ("stack", 1), ("grouped", 2), ("grouped", 3), ("grouped", 4)):
        for n in (4, 5, 8, 12, 16, 22, 32, 37):
            for binding in ("left", "right"):
                for blanks in ("end", "before_back"):
                    read, seq = run_all(n, kind, per, binding, blanks)
                    want = [p for p in seq]                     # None = Leerseite
                    assert read == want, (kind, per, n, binding, blanks, read, want)
                    assert [p for p in read if p is not None] == list(range(n))


def test_known_orders():
    # Sammelheftung 8 Seiten: Bogen 1 vorne 8|1, hinten 2|7; Bogen 2 vorne 6|3, hinten 4|5
    lay, blanks, nsig = layout.booklet_layout(8, LayoutSettings())
    assert [f for (_l, _j, _k, f) in lay] == [([7, 0], [1, 6]), ([5, 2], [3, 4])] and nsig == 1
    # Stapel: jede Lage ein Bogen mit 4 aufeinanderfolgenden Seiten
    lay, _, nsig = layout.booklet_layout(8, LayoutSettings(booklet_kind="stack"))
    assert [f for (*_x, f) in lay] == [([3, 0], [1, 2]), ([7, 4], [5, 6])] and nsig == 2
    # gruppiert 2 Bögen/Lage, 16 Seiten: Lage 2 beginnt mit Seite 9
    lay, _, nsig = layout.booklet_layout(16, LayoutSettings(booklet_kind="grouped", booklet_per_sig=2))
    assert nsig == 2 and lay[2][3] == ([15, 8], [9, 14])
    # Leerseiten vor der Rückseite: 6 Seiten -> 1 2 3 4 5 _ _ 6
    assert layout.booklet_sequence(6, "before_back") == [0, 1, 2, 3, 4, None, None, 5]


def test_creep_shifts_inner_sheets_to_fold():
    s = LayoutSettings(handling="booklet", booklet_creep_mm=0.2, use_margins=False)
    plans = layout.plan_booklet([A4] * 16, list(range(16)), A3, s)
    LW = A3.height
    # Bogen 1 (außen) liegt am Falz, Bogen 4 (innen) 3 × 0,2 mm weiter hinein
    def right_x(sp):
        return min(pl.x for pl in sp.placements if pl.x + pl.w / 2 > LW / 2)
    assert abs(right_x(plans[0]) - LW / 2) < 0.01
    assert abs(right_x(plans[6]) - (LW / 2 - 0.6 * MM)) < 0.01


def test_marks_and_blank_text():
    s = LayoutSettings(handling="booklet", booklet_kind="grouped", booklet_per_sig=1, booklet_fold_marks=True,
                       booklet_reg_marks=True, booklet_collation_marks=True, booklet_blank_text="Leerseite")
    plans = layout.plan_booklet([A4] * 6, list(range(6)), A3, s)
    kinds = [m[0] for m in plans[0].marks]
    assert kinds.count("bezier") == 4 and "rect" in kinds and ("line", A3.height / 2, 0) == plans[0].marks[0][:3]
    rects = [m for sp in plans for m in sp.marks if m[0] == "rect"]
    assert len(rects) == 2 and rects[0][2] != rects[1][2] or rects[0][1:3] != rects[1][1:3]   # Treppe
    assert any(m[0] == "text" and m[4] == "Leerseite" for sp in plans for m in sp.marks)
    # Marken werden ins PDF geschrieben (Kreis = Bézier, Balken = Rechteck)
    import pypdfium2 as pdfium
    src = pdfium.PdfDocument(os.path.join(HERE, "sample.pdf"))
    doc = layout.impose_with(src, A3, layout.plan([src.get_page_size(i) for i in range(len(src))],
                                                  list(range(6)), A3, s), s)
    assert len(doc) == 4
    doc.close()


def test_cli_impose():
    import pypdfium2 as pdfium
    tmp = tempfile.mkdtemp(prefix="pm-impose-")
    env = dict(os.environ, PYTHONPATH=ROOT, PASSERMARK_LANG="de", XDG_CONFIG_HOME=tmp, APPDATA=tmp)
    src = os.path.join(HERE, "sample.pdf")          # 7 Seiten A4
    out = os.path.join(tmp, "heft.pdf")
    r = subprocess.run([sys.executable, "-m", "pdfdruck.cli", "impose", src, out, "--set", "handling=booklet",
                        "--set", "sheet=A3", "--quiet"], capture_output=True, text=True, env=env, timeout=300)
    assert r.returncode == 0, r.stderr
    d = pdfium.PdfDocument(out)
    assert len(d) == 4 and [round(v / MM) for v in d.get_page_size(0)] == [297, 420]
    d.close()
    # Nutzen: A4 auf lange Kante 148 mm, 8× auf SRA3, Überfüller an Überfüller
    out2 = os.path.join(tmp, "nutzen.pdf")
    r = subprocess.run([sys.executable, "-m", "pdfdruck.cli", "impose", src, out2, "--pages", "1",
                        "--set", "sheet=SRA3", "--set", "step_repeat=true", "--set", "sr_by=long",
                        "--set", "sr_mm=148", "--set", "bleed_mm=2", "--set", "crop_marks=true", "--quiet"],
                       capture_output=True, text=True, env=env, timeout=300)
    assert r.returncode == 0, r.stderr
    d = pdfium.PdfDocument(out2)
    assert len(d) == 1 and [round(v / MM) for v in d.get_page_size(0)] == [320, 450]
    d.close()
    # Druck-Preset aus dem Programm (Art "impose") per Name
    from pdfdruck import presets
    os.environ["XDG_CONFIG_HOME"] = tmp
    os.environ["APPDATA"] = tmp
    presets.save(presets.PRINT, "Heft A3", presets.settings_class(presets.PRINT)(handling="booklet", sheet="A3"))
    out3 = os.path.join(tmp, "heft2.pdf")
    r = subprocess.run([sys.executable, "-m", "pdfdruck.cli", "impose", src, out3, "--preset", "Heft A3", "--quiet"],
                       capture_output=True, text=True, env=env, timeout=300)
    assert r.returncode == 0, r.stderr
    assert len(pdfium.PdfDocument(out3)) == 4


def _trim_pdf(path):
    """216×303 mm: rote 3 mm Anschnittfläche, blaues Endformat 210×297, TrimBox/BleedBox gesetzt; Seite 2 gedreht."""
    import pikepdf
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(path, pagesize=(216 * MM, 303 * MM))
    c.setFillColorRGB(1, 0, 0); c.rect(0, 0, 216 * MM, 303 * MM, fill=1, stroke=0)
    c.setFillColorRGB(0, 0, 1); c.rect(3 * MM, 3 * MM, 210 * MM, 297 * MM, fill=1, stroke=0)
    c.showPage(); c.save()
    pdf = pikepdf.open(path, allow_overwriting_input=True)
    pdf.pages[0].TrimBox = [3 * MM, 3 * MM, 213 * MM, 300 * MM]
    pdf.pages[0].BleedBox = [0, 0, 216 * MM, 303 * MM]
    pdf.pages.append(pdf.pages[0])
    pdf.pages[1].Rotate = 90
    pdf.pages.append(pdf.pages[0])
    pdf.pages[2].TrimBox = [5 * MM, 3 * MM, 213 * MM, 300 * MM]
    pdf.pages[2].Rotate = 90
    pdf.save(path)


def test_trimbox_recognized():
    import pypdfium2 as pdfium
    path = os.path.join(tempfile.mkdtemp(), "anschnitt.pdf")
    _trim_pdf(path)
    d = pdfium.PdfDocument(path)
    t = [tuple(round(v / MM, 1) for v in x) for x in layout.page_trims(d)]
    assert t == [(3, 3, 3, 3), (3, 3, 3, 3), (3, 3, 3, 5)], t          # gedreht: links (5) wird oben
    w, h, b = layout.trim_info(d, 0)
    assert (round(w), round(h), round(b)) == (210, 297, 3)
    assert layout.page_boxes(d)[0][1] is not None
    # Nutzen: Endformat 210×297 wird platziert, Anschnitt kommt aus dem Dokument (rot), nicht gespiegelt (blau)
    sizes = [d.get_page_size(i) for i in range(len(d))]
    s = LayoutSettings(step_repeat=True, sr_mode="grid", sr_cols=1, sr_rows=1, bleed_mm=3, crop_marks=True)
    sh = Sheet(320 * MM, 450 * MM)
    plans = layout.plan(sizes, [0], sh, s, layout.page_trims(d))
    pl = plans[0].placements[0]
    assert abs(pl.w / pl.scale / MM - 210) < 0.2 and pl.trim
    out = layout.impose_with(d, sh, plans, s)
    k = 4.0                                                            # px je pt
    im = out[0].render(scale=k).to_pil().convert("RGB")
    H = im.height
    def px(x_pt, y_pt):
        return im.getpixel((int(x_pt * k), int(H - y_pt * k)))
    x0, y0 = pl.x, pl.y + pl.h / 2
    assert px(x0 + 1.5 * MM * pl.scale, y0)[2] > 200                   # innen: blau
    inside_bleed = px(x0 - 1.5 * MM * pl.scale, y0)
    assert inside_bleed[0] > 200 and inside_bleed[2] < 80, inside_bleed  # Anschnitt: rot aus dem Dokument
    out.close()
    # ohne Ausschießen (normaler Druck „Größe“) bleibt die ganze Seite
    plain = layout.plan(sizes, [0], sh, LayoutSettings(), layout.page_trims(d))
    assert plain[0].placements[0].trim is None


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
