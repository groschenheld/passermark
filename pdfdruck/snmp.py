# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Minimal SNMP v2c client (read only) – fallback when a printer does not report its rolls over IPP.

Reads the input table of the Printer MIB (RFC 3805, prtInputTable): type (continuous roll), width across the
feed direction, capacity/level (remaining length when the device counts in metres or feet), media name,
grammage and media type. Supported by almost every network printer and plotter (Canon, Epson, HP, Océ …).
Standard library only; nothing is ever written to the device.
"""
from __future__ import annotations

import os
import socket
import struct

PRT_INPUT_ENTRY = "1.3.6.1.2.1.43.8.2.1"
SYS_DESCR = "1.3.6.1.2.1.1.1.0"
# Spalten der prtInputTable, die gebraucht werden
COLUMNS = {2: "type", 3: "dimunit", 4: "feed_declared", 5: "xfeed_declared", 6: "feed_chosen", 7: "xfeed_chosen",
           8: "capunit", 9: "maxcapacity",
           10: "level", 12: "media_name", 13: "name", 18: "description", 20: "weight", 21: "media_type"}
CONTINUOUS_ROLL = 6
DIM_MM = {3: 0.00254, 4: 0.001}                         # tenThousandthsOfInches, micrometers
CAP_M = {3: 2.54e-6, 4: 1e-6, 16: 0.3048, 17: 1.0}     # … feet, meters (8 = sheets: keine Länge)


class SnmpError(OSError):
    pass


# --------------------------------------------------------------------------- #
# BER
# --------------------------------------------------------------------------- #
def _len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(b)]) + b


def _tlv(tag: int, body: bytes) -> bytes:
    return bytes([tag]) + _len(len(body)) + body


def _int(v: int) -> bytes:
    n = max(1, (v.bit_length() + 8) // 8)
    return _tlv(0x02, v.to_bytes(n, "big", signed=True))


def _oid(oid: str) -> bytes:
    parts = [int(x) for x in oid.strip(".").split(".")]
    body = bytes([40 * parts[0] + parts[1]])
    for p in parts[2:]:
        chunk = [p & 0x7F]
        p >>= 7
        while p:
            chunk.append(0x80 | (p & 0x7F))
            p >>= 7
        body += bytes(reversed(chunk))
    return _tlv(0x06, body)


def _decode_oid(b: bytes) -> str:
    if not b:
        return ""
    out = [b[0] // 40, b[0] % 40]
    v = 0
    for x in b[1:]:
        v = (v << 7) | (x & 0x7F)
        if not x & 0x80:
            out.append(v)
            v = 0
    return ".".join(str(x) for x in out)


def _read(data: bytes, pos: int):
    tag = data[pos]
    n = data[pos + 1]
    pos += 2
    if n & 0x80:
        k = n & 0x7F
        n = int.from_bytes(data[pos:pos + k], "big")
        pos += k
    return tag, data[pos:pos + n], pos + n


def request(community: str, oids: list, req_id: int, pdu: int = 0xA1, version: int = 1) -> bytes:
    """GetRequest (0xA0) / GetNextRequest (0xA1). version: 1 = SNMP v2c, 0 = SNMP v1."""
    binds = b"".join(_tlv(0x30, _oid(o) + b"\x05\x00") for o in oids)
    body = _int(req_id) + _int(0) + _int(0) + _tlv(0x30, binds)
    return _tlv(0x30, _int(version) + _tlv(0x04, community.encode()) + _tlv(pdu, body))


def parse(data: bytes) -> tuple[int, int, list]:
    """(req_id, error_status, [(oid, value)]). value: int, bytes, str (OID) oder None (Ende/kein Objekt)."""
    tag, msg, _ = _read(data, 0)
    if tag != 0x30:
        raise SnmpError("no SNMP message")
    _, _ver, p = _read(msg, 0)
    _, _com, p = _read(msg, p)
    tag, pdu, _ = _read(msg, p)
    if tag != 0xA2:
        raise SnmpError("no SNMP response")
    _, rid, p = _read(pdu, 0)
    _, err, p = _read(pdu, p)
    _, _idx, p = _read(pdu, p)
    _, binds, _ = _read(pdu, p)
    out, q = [], 0
    while q < len(binds):
        _, vb, q = _read(binds, q)
        _, oid, r = _read(vb, 0)
        vtag, val, _ = _read(vb, r)
        if vtag in (0x02, 0x41, 0x42, 0x43, 0x46):
            v = int.from_bytes(val, "big", signed=(vtag == 0x02)) if val else 0
        elif vtag == 0x04:
            v = bytes(val)
        elif vtag == 0x06:
            v = _decode_oid(val)
        else:                                   # NULL, noSuchObject (0x80), noSuchInstance, endOfMibView (0x82)
            v = None
        out.append((_decode_oid(oid), v))
    return int.from_bytes(rid, "big", signed=True), int.from_bytes(err, "big"), out


# --------------------------------------------------------------------------- #
# Abfragen
# --------------------------------------------------------------------------- #
class Client:
    def __init__(self, host: str, community: str = "public", port: int = 161, timeout: float = 1.5, retries: int = 1,
                 version: int = 1):
        self.version = version
        self.addr = (host, port)
        self.community = community
        self.timeout, self.retries = timeout, retries
        self.req = int.from_bytes(os.urandom(3), "big")

    def _ask(self, oids: list, pdu: int) -> list:
        self.req = (self.req + 1) & 0x7FFFFFFF
        pkt = request(self.community, oids, self.req, pdu, self.version)
        last = None
        for _ in range(self.retries + 1):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.settimeout(self.timeout)
                    s.sendto(pkt, self.addr)
                    while True:
                        data, _a = s.recvfrom(65535)
                        rid, err, binds = parse(data)
                        if rid != self.req:
                            continue                  # alte Antwort
                        if err == 2 and pdu == 0xA1:
                            return [("", None)]       # SNMP v1: noSuchName = Ende der Tabelle
                        if err:
                            raise SnmpError(f"SNMP error {err}")
                        return binds
            except (socket.timeout, TimeoutError) as e:
                last = e
            except (IndexError, ValueError) as e:
                raise SnmpError(f"SNMP: {e}") from e
        raise SnmpError(f"SNMP: no answer from {self.addr[0]} ({last})")

    def get(self, oid: str):
        return self._ask([oid], 0xA0)[0][1]

    def walk(self, prefix: str, limit: int = 200) -> list:
        out, cur = [], prefix
        for _ in range(limit):
            oid, val = self._ask([cur], 0xA1)[0]
            if val is None or not oid.startswith(prefix + "."):
                break
            out.append((oid, val))
            cur = oid
        return out


def client(host: str, community: str = "public", timeout: float = 1.5) -> "Client":
    """Client, der antwortet: zuerst SNMP v2c, sonst v1 (ältere Geräte/Einstellung „nur v1“)."""
    last = None
    for ver in (1, 0):
        c = Client(host, community, timeout=timeout, version=ver)
        try:
            c.get(SYS_DESCR)
            return c
        except SnmpError as e:
            last = e
    raise last or SnmpError("SNMP: no answer")


def input_table(host: str, community: str = "public", timeout: float = 1.5, raw: list | None = None) -> list:
    """Zeilen der prtInputTable: [{"index": "1.1", "type": 6, "width_mm": 914.0, "remaining_m": 45.0, …}].
        raw: bekommt die Rohzeilen (für „Gerät prüfen“)."""
    c = client(host, community, timeout)
    rows: dict = {}
    for col, key in COLUMNS.items():
        try:
            vals = c.walk(f"{PRT_INPUT_ENTRY}.{col}", limit=64)
        except SnmpError:
            if col == 2:
                raise                                  # nicht einmal die Lade-Typen -> kein Printer-MIB
            continue
        for oid, v in vals:
            idx = oid[len(PRT_INPUT_ENTRY) + len(str(col)) + 2:]
            rows.setdefault(idx, {"index": idx})[key] = v
    if raw is not None:
        raw.extend(dict(r) for r in rows.values())
    return [interpret_row(r) for r in rows.values()]


def walk_all(host: str, prefix: str, community: str = "public", limit: int = 2000, timeout: float = 1.5) -> list:
    """Ganzen Teilbaum lesen (für „Gerät prüfen“): [(OID, Wert)]."""
    return client(host, community, timeout).walk(prefix, limit)


def _text(v) -> str:
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace").strip("\x00 ").strip()
    return "" if v is None else str(v)


def interpret_row(r: dict) -> dict:
    """Rohwerte einer Zeile -> Breite in mm, Restlänge in m, Texte."""
    out = {"index": r.get("index", ""), "roll": r.get("type") == CONTINUOUS_ROLL, "name": _text(r.get("name")),
           "media_name": _text(r.get("media_name")), "media_type": _text(r.get("media_type")),
           "description": _text(r.get("description")), "width_mm": None, "remaining_m": None, "weight": None,
           "empty": r.get("level") == 0}
    f = DIM_MM.get(r.get("dimunit"))
    x = r.get("xfeed_chosen")
    if not isinstance(x, int) or x <= 0:
        x = r.get("xfeed_declared")
    if f and isinstance(x, int) and x > 0:
        out["width_mm"] = round(x * f, 1)
    cf = CAP_M.get(r.get("capunit"))
    lvl = r.get("level")
    if cf and isinstance(lvl, int) and lvl >= 0:
        out["remaining_m"] = round(lvl * cf, 2)
    w = r.get("weight")
    if isinstance(w, int) and w > 0:
        out["weight"] = w
    if not out["roll"]:                                      # manche Geräte melden „other“ – am Namen erkennen
        from .ipp import is_roll_name
        out["roll"] = is_roll_name(out["name"]) or is_roll_name(out["description"]) or is_roll_name(out["media_name"])
    if not out["roll"] and out["width_mm"] and r.get("type") in (1, 2, None):
        # „other“/„unknown“ mit Breite, aber ohne Länge (−1/−2/0 = unbegrenzt/unbekannt): bei Plottern eine Rolle
        feed = r.get("feed_chosen") if isinstance(r.get("feed_chosen"), int) and r.get("feed_chosen") > 0 \
            else r.get("feed_declared")
        out["roll"] = not (isinstance(feed, int) and feed > 0)
    return out
