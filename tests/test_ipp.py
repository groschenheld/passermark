# SPDX-License-Identifier: GPL-3.0-or-later
# pdfToolkit – Copyright (C) 2026 Hias
import os, struct, sys
import os as _os
_os.environ.setdefault("PDFTOOLKIT_LANG", "de")   # Tests prüfen deutsche Texte
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pdfdruck import ipp


def a(tag, name, val):
    if isinstance(val, int) and not isinstance(val, bool):
        val = struct.pack(">i", val)
    elif isinstance(val, str):
        val = val.encode()
    n = name.encode()
    return struct.pack(">BH", tag, len(n)) + n + struct.pack(">H", len(val)) + val


def media_col(first, src, w, h, weight, mtype):
    out = a(ipp.T_BEGCOL, "media-col-ready" if first else "", b"")
    out += a(ipp.T_MEMBER, "", "media-source") + a(ipp.T_KEYWORD, "", src)
    out += a(ipp.T_MEMBER, "", "media-size") + a(ipp.T_BEGCOL, "", b"")
    out += a(ipp.T_MEMBER, "", "x-dimension") + a(ipp.T_INTEGER, "", w)
    out += a(ipp.T_MEMBER, "", "y-dimension") + a(ipp.T_INTEGER, "", h)
    out += a(ipp.T_ENDCOL, "", b"")
    out += a(ipp.T_MEMBER, "", "media-weight-metric") + a(ipp.T_INTEGER, "", weight)
    out += a(ipp.T_MEMBER, "", "media-type") + a(ipp.T_KEYWORD, "", mtype)
    return out + a(ipp.T_ENDCOL, "", b"")


def fake_response():
    r = struct.pack(">BBHI", 2, 0, 0, 1) + bytes([ipp.T_OPERATION])
    r += a(ipp.T_CHARSET, "attributes-charset", "utf-8")
    r += bytes([ipp.T_PRINTER])
    r += a(ipp.T_TEXT, "printer-make-and-model", "Canon iR-ADV DX C3822")
    r += media_col(True, "tray-1", 21000, 29700, 80, "stationery")
    r += media_col(False, "tray-2", 21000, 29700, 80, "stationery")
    r += media_col(False, "tray-3", 29700, 42000, 120, "stationery-heavyweight")
    r += a(ipp.T_KEYWORD, "media-source-supported", "by-pass-tray") + a(ipp.T_KEYWORD, "", "tray-1") \
        + a(ipp.T_KEYWORD, "", "tray-2") + a(ipp.T_KEYWORD, "", "tray-3")
    r += a(ipp.T_OCTET, "printer-input-tray", "type=sheetFeedManual;level=-2;maxcapacity=100;name=Bypass;") \
        + a(ipp.T_OCTET, "", "type=sheetFeedAutoRemovableTray;level=0;maxcapacity=550;name=Tray 1;") \
        + a(ipp.T_OCTET, "", "type=sheetFeedAutoRemovableTray;level=275;maxcapacity=550;name=Tray 2;")
    return r + bytes([ipp.T_END])


def test_request_roundtrip():
    req = ipp.build_request("ipp://x/ipp/print")
    assert req[:4] == bytes([2, 0, 0, 0x0B]) and req.endswith(bytes([3]))


def test_parse_trays():
    status, attrs = ipp.parse_response(fake_response())
    st = ipp.interpret(attrs)
    assert status == 0 and st.model.startswith("Canon")
    t1, t2, t3 = st.trays["tray-1"], st.trays["tray-2"], st.trays["tray-3"]
    assert t1.size_mm == (210, 297) and t1.weight == 80 and t1.empty
    assert t2.level == 50 and not t2.empty
    assert t3.size_mm == (297, 420) and t3.weight == 120 and t3.level is None


def test_host():
    assert ipp.host_from_device_uri("lpd://192.168.1.20/print") == "192.168.1.20"
    assert ipp.host_from_device_uri("ipp://canon.local:631/ipp/print") == "canon.local"
    assert ipp.host_from_device_uri("dnssd://Canon._ipp._tcp.local/?uuid=1") == ""


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("ok", k)
