# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Rollen erkennen: IPP (media-col-ready, printer-input-tray), SNMP Printer-MIB (nachgestellter Agent auf
    localhost), Zuordnung zur Treiber-Zufuhr, von Hand eingetragene Rollen."""
import os, socket, struct, sys, tempfile, threading
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ.setdefault("PASSERMARK_LANG", "de")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pm-rolls-cfg-")
from pdfdruck import ipp, rolls, snmp
from pdfdruck.printers import Choice, Option, PrinterCaps
from test_ipp import a


def roll_col(first, src, w, weight, mtype, info=""):
    out = a(ipp.T_BEGCOL, "media-col-ready" if first else "", b"")
    out += a(ipp.T_MEMBER, "", "media-source") + a(ipp.T_KEYWORD, "", src)
    out += a(ipp.T_MEMBER, "", "media-size") + a(ipp.T_BEGCOL, "", b"")
    out += a(ipp.T_MEMBER, "", "x-dimension") + a(ipp.T_INTEGER, "", w)
    out += a(ipp.T_MEMBER, "", "y-dimension") + a(ipp.T_RANGE, "", struct.pack(">ii", 10000, 4500000))
    out += a(ipp.T_ENDCOL, "", b"")
    if weight:
        out += a(ipp.T_MEMBER, "", "media-weight-metric") + a(ipp.T_INTEGER, "", weight)
    out += a(ipp.T_MEMBER, "", "media-type") + a(ipp.T_KEYWORD, "", mtype)
    if info:
        out += a(ipp.T_MEMBER, "", "media-info") + a(ipp.T_TEXT, "", info)
    return out + a(ipp.T_ENDCOL, "", b"")


def plotter_response():
    r = struct.pack(">BBHI", 2, 0, 0, 1) + bytes([ipp.T_OPERATION])
    r += a(ipp.T_CHARSET, "attributes-charset", "utf-8") + bytes([ipp.T_PRINTER])
    r += a(ipp.T_TEXT, "printer-make-and-model", "Canon ColorWave 3800")
    r += roll_col(True, "roll-1", 59400, 80, "stationery", "Bond 80")
    r += roll_col(False, "roll-2", 84100, 75, "stationery")
    r += roll_col(False, "roll-3", 91400, 0, "photographic-glossy")
    r += a(ipp.T_KEYWORD, "media-source-supported", "roll-1") + a(ipp.T_KEYWORD, "", "roll-2") \
        + a(ipp.T_KEYWORD, "", "roll-3") + a(ipp.T_KEYWORD, "", "roll-4")
    r += a(ipp.T_OCTET, "printer-input-tray",
           "type=continuousRoll;dimunit=micrometers;mediafeed=0;mediaxfeed=594000;unit=meters;maxcapacity=150;"
           "level=45;status=0;name=Roll 1;") \
        + a(ipp.T_OCTET, "", "type=continuousRoll;dimunit=micrometers;mediaxfeed=841000;maxcapacity=-2;level=-2;"
                             "status=0;name=Roll 2;") \
        + a(ipp.T_OCTET, "", "type=continuousRoll;dimunit=micrometers;mediaxfeed=914000;level=-2;name=Roll 3;") \
        + a(ipp.T_OCTET, "", "type=continuousRoll;dimunit=micrometers;mediaxfeed=1067000;unit=meters;level=0;"
                             "maxcapacity=100;name=Roll 4;")
    return r + bytes([ipp.T_END])


def plotter_caps():
    caps = PrinterCaps("Plotter", "ppd")
    caps.options["InputSlot"] = Option("InputSlot", "Papierzufuhr", "", [
        Choice("Auto", "Automatisch"), Choice("Roll1", "Rolle 1"), Choice("Roll2", "Rolle 2"),
        Choice("Roll3", "Rolle 3"), Choice("Roll4", "Rolle 4")], "Auto")
    from pdfdruck import printers
    printers._assign_roles(caps)
    return caps


def test_ipp_rolls():
    _s, attrs = ipp.parse_response(plotter_response())
    st = ipp.interpret(attrs)
    r1 = st.trays["roll-1"]
    assert r1.roll and r1.width_mm == 594 and r1.size_mm is None and r1.weight == 80
    assert r1.remaining_m == 45 and r1.media_name == "Bond 80"
    assert st.trays["roll-4"].width_mm == 1067 and st.trays["roll-4"].empty       # nur aus printer-input-tray
    rl = rolls.from_ipp(st)
    assert [r.width_mm for r in rl] == [594, 841, 914, 1067]
    assert rl[0].weight == 80 and rl[1].weight == 75 and rl[2].weight == 0
    assert rl[0].name == "Roll 1" and "45 m" in rl[0].label() and "594 mm" in rl[0].label()


def test_slot_mapping():
    caps = plotter_caps()
    assert rolls.slot_for(caps, "roll-2") == "Roll2"
    assert rolls.slot_for(caps, "main-roll") == "Roll1"
    assert rolls.slot_for(caps, "alternate-roll") == "Roll2"
    assert rolls.slot_for(caps, "", 2) == "Roll3"
    one = PrinterCaps("E", "ppd")
    one.options["InputSlot"] = Option("InputSlot", "Papierzufuhr", "", [Choice("Sheet", "Einzelblatt"),
                                                                          Choice("RollPaper", "Rollenpapier")], "Sheet")
    from pdfdruck import printers
    printers._assign_roles(one)
    assert rolls.slot_for(one, "roll-1") == "RollPaper"
    assert rolls.slot_for(PrinterCaps("x", "ppd"), "roll-1") == ""


# ---------------- SNMP ----------------
def _agent(table: dict):
    """Mini-Agent: beantwortet GetNext aus table {oid: value} (int oder bytes)."""
    keys = sorted(table, key=lambda o: [int(x) for x in o.split(".")])
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    s.settimeout(5)

    def val(v):
        return snmp._int(v) if isinstance(v, int) else snmp._tlv(0x04, v)

    def serve():
        while True:
            try:
                data, addr = s.recvfrom(65535)
            except OSError:
                return
            # Anfrage zerlegen
            _t, msg, _ = snmp._read(data, 0)
            _, _v, p = snmp._read(msg, 0)
            _, com, p = snmp._read(msg, p)
            ptag, pdu, _ = snmp._read(msg, p)
            _, rid, q = snmp._read(pdu, 0)
            _, _e, q = snmp._read(pdu, q)
            _, _i, q = snmp._read(pdu, q)
            _, binds, _ = snmp._read(pdu, q)
            _, vb, _ = snmp._read(binds, 0)
            _, oid, _ = snmp._read(vb, 0)
            want = [int(x) for x in snmp._decode_oid(oid).split(".")]
            if ptag == 0xA0:                              # Get: genau dieses Objekt
                nxt = ".".join(map(str, want)) if ".".join(map(str, want)) in table else None
            else:
                nxt = next((k for k in keys if [int(x) for x in k.split(".")] > want), None)
            vbody = (snmp._oid(nxt) + val(table[nxt])) if nxt else (snmp._oid(".".join(map(str, want))) + b"\x82\x00")
            body = snmp._tlv(0x02, rid) + snmp._int(0) + snmp._int(0) + snmp._tlv(0x30, snmp._tlv(0x30, vbody))
            resp = snmp._tlv(0x30, snmp._int(1) + snmp._tlv(0x04, com) + snmp._tlv(0xA2, body))
            s.sendto(resp, addr)
    threading.Thread(target=serve, daemon=True).start()
    return s


def test_snmp_input_table():
    E = snmp.PRT_INPUT_ENTRY
    t = {}
    for idx, typ, w, unit, lvl, name, wt in (("1.1", 6, 914000, 17, 38, b"Roll 1", 90),
                                              ("1.2", 6, 594000, 17, -2, b"Roll 2", 0),
                                              ("1.3", 3, 210000, 8, 100, b"Cassette", 80)):
        t[f"{E}.2.{idx}"] = typ
        t[f"{E}.3.{idx}"] = 4                     # micrometers
        t[f"{E}.5.{idx}"] = w
        t[f"{E}.8.{idx}"] = unit
        t[f"{E}.10.{idx}"] = lvl
        t[f"{E}.13.{idx}"] = name
        t[f"{E}.12.{idx}"] = b"Plain Paper"
        t[f"{E}.20.{idx}"] = wt
    t["1.3.6.1.2.1.43.9.1.1.1"] = 1                 # danach: anderer Zweig
    s = _agent(t)
    port = s.getsockname()[1]
    old = snmp.Client.__init__.__defaults__
    snmp.Client.__init__.__defaults__ = ("public", port, 2.0, 1, 1)
    try:
        rows = snmp.input_table("127.0.0.1")
    finally:
        snmp.Client.__init__.__defaults__ = old
        s.close()
    rl = rolls.from_snmp(rows)
    assert [r.width_mm for r in rl] == [914, 594], rl
    assert rl[0].remaining_m == 38 and rl[0].weight == 90 and rl[0].media == "Plain Paper"
    assert rl[1].remaining_m is None and rl[1].weight == 0


def test_ber_roundtrip():
    pkt = snmp.request("public", ["1.3.6.1.2.1.43.8.2.1.2"], 77)
    _t, msg, _ = snmp._read(pkt, 0)
    assert snmp._decode_oid(snmp._oid("1.3.6.1.2.1.43.8.2.1.2.1.1")[2:]) == "1.3.6.1.2.1.43.8.2.1.2.1.1"
    assert snmp._decode_oid(snmp._oid("1.3.6.1.4.1.1602.1.300")[2:]) == "1.3.6.1.4.1.1602.1.300"


def test_manual_rolls_and_fallback():
    rolls.save_manual("Plotter", [rolls.Roll(594, "Roll1", "Rolle 1", 80), rolls.Roll(914, name="Rolle 2")])
    m = rolls.manual("Plotter")
    assert [r.width_mm for r in m] == [594, 914] and m[0].slot == "Roll1" and m[0].weight == 80

    class S:
        cfg = {}

        def caps_for(self, name):
            return plotter_caps()
    old = rolls.query
    rolls.query = lambda host, force=False: rolls.RollState([], "none", "keine Antwort", host)
    try:
        st = rolls.for_printer(S(), "Plotter")
    finally:
        rolls.query = old
    assert st.origin == "manual" and [r.slot for r in st.rolls] == ["Roll1", "Roll2"]
    assert [r.width_mm for r in rolls.parse_widths("594, 841;914")] == [594, 841, 914]


def test_snmp_other_type_plotter_and_probe():
    """Plotter meldet Typ „other“ ohne Rollen-Namen, Länge unbekannt (−2): trotzdem Rolle. Dazu „Gerät prüfen“."""
    from pdfdruck import probe
    E = snmp.PRT_INPUT_ENTRY
    t = {snmp.SYS_DESCR: b"Canon ColorWave 3600", "1.3.6.1.2.1.1.2.0": 7}
    for idx, w in (("1.1", 914000), ("1.2", 841000), ("1.3", 594000)):
        t[f"{E}.2.{idx}"] = 1                      # other
        t[f"{E}.3.{idx}"] = 4
        t[f"{E}.4.{idx}"] = -2                     # Länge unbekannt
        t[f"{E}.5.{idx}"] = w
        t[f"{E}.13.{idx}"] = b"Drawer " + idx[-1].encode()
    s_ = _agent(t)
    port = s_.getsockname()[1]
    old = snmp.Client.__init__.__defaults__
    snmp.Client.__init__.__defaults__ = ("public", port, 2.0, 1, 1)
    try:
        rl = rolls.from_snmp(snmp.input_table("127.0.0.1"))
        rep = probe.run("127.0.0.1", "CW", timeout=0.5)
    finally:
        snmp.Client.__init__.__defaults__ = old
        s_.close()
    assert [r.width_mm for r in rl] == [914, 841, 594], rl
    assert rep["snmp"]["sysDescr"] == "Canon ColorWave 3600" and len(rep["snmp"]["inputs"]) == 3
    assert rep["level"] == "status" and len(rep["rolls"]["rolls"]) == 3
    assert "prtInputTable" in probe.text(rep)
    path = os.path.join(tempfile.mkdtemp(), probe.default_name(rep))
    probe.save(rep, path)
    import json
    assert json.load(open(path, encoding="utf-8"))["passermark"] == "probe"


def test_windows_ports_and_own_address():
    from pdfdruck import ipp, printers_win
    assert ipp.host_from_device_uri("socket://10.30.4.73-HPGL2") == "10.30.4.73"
    assert ipp.host_from_device_uri("socket://IP_10.0.0.5") == "10.0.0.5"
    assert ipp.host_from_device_uri("socket://WSD-d186ce9a-263a") == ""
    assert printers_win.port_host("10.30.4.73-HPGL2") == "10.30.4.73"
    assert printers_win.port_host("socket://10.30.4.73_1") == "10.30.4.73"
    assert printers_win.port_host("WSD-d186ce9a") == ""          # ohne Windows-Registry: unbekannt

    class S:
        cfg = {"printers": {"CW": {"tray_host": "10.1.1.1"}}}
    assert rolls.host_for(S(), "CW") == "10.1.1.1"
    rolls.set_user_host("CW", "10.30.4.73")
    assert rolls.host_for(S(), "CW") == "10.30.4.73"            # eigene Angabe geht vor
    rolls.set_user_host("CW", "")
    assert rolls.host_for(S(), "CW") == "10.1.1.1"
    st = rolls.query("diesen-namen-gibt-es-nicht.invalid", force=True)
    assert not st.rolls and "nicht gefunden" in st.error, st.error


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
