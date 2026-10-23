# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Mehrfachauswahl im Dateimanager: viele gleichzeitig gestartete Prozesse einigen sich auf GENAU eine Hauptinstanz,
    alle Dateien landen dort (früher: mehrere Server, jeder bekam nur einen Teil -> „nur Einzeldateien zusammengeführt“).
    Dazu Leerseiten einfügen (Seitenleiste)."""
import io, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

PROC = r'''
import json, os, socket, sys, time
sys.path.insert(0, sys.argv[3])
os.environ["TMPDIR"] = sys.argv[2]
from pdfdruck import fastipc
f = sys.argv[1]
lock = fastipc.hand_over_or_lock("merge", [f])
if lock is None:
    sys.exit(0)
time.sleep(1.0)                                   # langsamer Start der Oberfläche
path = os.path.join(sys.argv[2], fastipc.server_name())
srv = socket.socket(socket.AF_UNIX); srv.bind(path); srv.listen(30)
lock.release()
got = [f]; srv.settimeout(3)
try:
    while True:
        c, _ = srv.accept(); got += json.loads(c.recv(4096).decode())["files"]; c.sendall(b"ok\n"); c.close()
except socket.timeout:
    pass
os.remove(path)
print("SERVER " + ",".join(sorted(got)))
'''


def test_one_server_for_parallel_starts():
    if os.name == "nt":
        return                                    # Named-Pipe-Variante: nur auf Windows prüfbar
    d = tempfile.mkdtemp()
    script = os.path.join(d, "proc.py")
    with open(script, "w") as fh:
        fh.write(PROC)
    procs = [subprocess.Popen([sys.executable, "-I", script, f"f{i:02d}", d, ROOT], stdout=subprocess.PIPE, text=True)
             for i in range(10)]
    out = [p.communicate(timeout=60)[0] for p in procs]
    servers = [o for o in out if o.startswith("SERVER")]
    assert len(servers) == 1, out
    assert servers[0].strip().split(" ", 1)[1].split(",") == [f"f{i:02d}" for i in range(10)], servers


def test_insert_blank_takes_neighbour_format():
    import pikepdf
    import pypdfium2 as pdfium
    from pdfdruck import pageops
    pk = pikepdf.new()
    for _ in range(3):
        pk.add_blank_page(page_size=(255, 170))
    pk.pages[1].TrimBox = [9, 9, 246, 161]
    pk.pages[1].Rotate = 90
    b = io.BytesIO()
    pk.save(b)
    doc = pdfium.PdfDocument(b.getvalue())
    assert pageops.insert_blank(doc, 2, ref=1, count=2) == 2
    pageops.insert_blank(doc, len(doc))                      # ohne Vorlage: A4
    out = io.BytesIO()
    doc.save(out)
    q = pikepdf.open(io.BytesIO(out.getvalue()))
    assert len(q.pages) == 6
    for i in (2, 3):
        assert [float(v) for v in q.pages[i].MediaBox] == [0, 0, 255, 170]
        assert [float(v) for v in q.pages[i].TrimBox] == [9, 9, 246, 161]
        assert int(q.pages[i].Rotate) == 90
    assert round(float(q.pages[5].MediaBox[3])) == 842


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("ok", k)
