# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Minimaler IPP-Client (RFC 8010/8011): fragt beim Drucker direkt ab, was in welcher Lade liegt.

Unabhängig von CUPS – funktioniert unter Linux und Windows und auch dann, wenn die Druckerwarteschlange
einen Herstellertreiber (UFR II, PS) verwendet. Ausgewertet werden:
  * media-col-ready     – geladene Medien je Lade: Quelle, Format, Grammatur, Papiertyp
  * printer-input-tray  – Laden mit Füllstand (PWG 5100.13): leer / nicht leer
"""
from __future__ import annotations

from .l10n import tr

import re
import socket
import ssl
import struct
import urllib.request
from dataclasses import dataclass, field

# Tags
T_OPERATION, T_PRINTER, T_END = 0x01, 0x04, 0x03
T_INTEGER, T_BOOLEAN, T_ENUM = 0x21, 0x22, 0x23
T_OCTET, T_DATETIME, T_RESOLUTION, T_RANGE = 0x30, 0x31, 0x32, 0x33
T_BEGCOL, T_TEXTLANG, T_NAMELANG, T_ENDCOL = 0x34, 0x35, 0x36, 0x37
T_TEXT, T_NAME, T_KEYWORD, T_URI, T_CHARSET, T_LANG, T_MIME, T_MEMBER = \
    0x41, 0x42, 0x44, 0x45, 0x47, 0x48, 0x49, 0x4A

WANTED = ["media-col-ready", "media-ready", "printer-input-tray", "media-source-supported",
          "printer-make-and-model", "printer-state"]


@dataclass
class TrayState:
    source: str                 # z. B. tray-1, tray-2, by-pass-tray, main
    size_mm: tuple | None = None    # (Breite, Höhe) in mm
    size_name: str = ""         # PWG-Name, falls gemeldet (iso_a4_210x297mm)
    weight: int | None = None   # g/m²
    media_type: str = ""        # stationery, cardstock …
    level: int | None = None    # Füllstand in %; 0 = leer; None = unbekannt
    name: str = ""              # Anzeigename des Geräts (z. B. „Kassette 1“)

    @property
    def empty(self) -> bool:
        return self.level == 0


@dataclass
class DeviceStatus:
    trays: dict = field(default_factory=dict)   # source -> TrayState
    model: str = ""
    error: str = ""


# --------------------------------------------------------------------------- #
# Kodieren
# --------------------------------------------------------------------------- #
def _attr(tag: int, name: str, value: bytes) -> bytes:
    n = name.encode()
    return struct.pack(">BH", tag, len(n)) + n + struct.pack(">H", len(value)) + value


def build_request(uri: str, attrs=WANTED, request_id: int = 1) -> bytes:
    out = struct.pack(">BBHI", 2, 0, 0x000B, request_id)        # IPP 2.0, Get-Printer-Attributes
    out += bytes([T_OPERATION])
    out += _attr(T_CHARSET, "attributes-charset", b"utf-8")
    out += _attr(T_LANG, "attributes-natural-language", b"de")
    out += _attr(T_URI, "printer-uri", uri.encode())
    for i, a in enumerate(attrs):
        out += _attr(T_KEYWORD, "requested-attributes" if i == 0 else "", a.encode())
    return out + bytes([T_END])


# --------------------------------------------------------------------------- #
# Dekodieren (inkl. Collections)
# --------------------------------------------------------------------------- #
def _value(tag: int, raw: bytes):
    if tag in (T_INTEGER, T_ENUM) and len(raw) == 4:
        return struct.unpack(">i", raw)[0]
    if tag == T_BOOLEAN and len(raw) == 1:
        return bool(raw[0])
    if tag == T_RANGE and len(raw) == 8:
        return struct.unpack(">ii", raw)
    if tag == T_RESOLUTION and len(raw) == 9:
        return struct.unpack(">iib", raw)
    if tag in (T_TEXTLANG, T_NAMELANG) and len(raw) >= 4:
        ll = struct.unpack(">H", raw[:2])[0]
        tl = struct.unpack(">H", raw[2 + ll:4 + ll])[0]
        return raw[4 + ll:4 + ll + tl].decode("utf-8", "replace")
    if tag == T_OCTET:
        return raw
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw


def parse_response(data: bytes) -> tuple[int, dict]:
    """(Statuscode, {Attributname: [Werte]}) – Collections als dict."""
    if len(data) < 8:
        raise ValueError(tr("IPP-Antwort zu kurz"))
    status = struct.unpack(">H", data[2:4])[0]
    pos, attrs = 8, {}
    stack = []                 # offene Collections: (dict, aktueller Membername)
    last_name = None

    def store(name, val):
        if stack:
            col, _ = stack[-1]
            col.setdefault(name, []).append(val)
        else:
            attrs.setdefault(name, []).append(val)

    while pos < len(data):
        tag = data[pos]
        pos += 1
        if tag == T_END:
            break
        if tag < 0x10:          # Gruppenbeginn
            continue
        nlen = struct.unpack(">H", data[pos:pos + 2])[0]
        name = data[pos + 2:pos + 2 + nlen].decode("utf-8", "replace")
        pos += 2 + nlen
        vlen = struct.unpack(">H", data[pos:pos + 2])[0]
        raw = data[pos + 2:pos + 2 + vlen]
        pos += 2 + vlen
        if tag == T_BEGCOL:
            col = {}
            if stack and not name:            # Member in Collection
                parent, member = stack[-1]
                parent.setdefault(member, []).append(col)
            else:
                if not name:
                    name = last_name
                if stack:
                    stack[-1][0].setdefault(name, []).append(col)
                else:
                    attrs.setdefault(name, []).append(col)
                last_name = name
            stack.append((col, None))
            continue
        if tag == T_ENDCOL:
            if stack:
                stack.pop()
            continue
        if tag == T_MEMBER:
            if stack:
                stack[-1] = (stack[-1][0], raw.decode("utf-8", "replace"))
            continue
        val = _value(tag, raw)
        if stack:
            col, member = stack[-1]
            if member:
                col.setdefault(member, []).append(val)
            continue
        if not name:
            name = last_name
        last_name = name
        store(name, val)
    return status, attrs


def _first(d: dict, key, default=None):
    v = d.get(key)
    return v[0] if v else default


def interpret(attrs: dict) -> DeviceStatus:
    st = DeviceStatus(model=str(_first(attrs, "printer-make-and-model", "")))
    for col in attrs.get("media-col-ready", []):
        if not isinstance(col, dict):
            continue
        src = str(_first(col, "media-source", "") or "")
        if not src:
            continue
        t = st.trays.setdefault(src, TrayState(src))
        size = _first(col, "media-size")
        if isinstance(size, dict):
            x, y = _first(size, "x-dimension"), _first(size, "y-dimension")
            if isinstance(x, int) and isinstance(y, int):
                t.size_mm = (x / 100.0, y / 100.0)
        w = _first(col, "media-weight-metric")
        if isinstance(w, int) and w > 0:
            t.weight = w
        t.media_type = str(_first(col, "media-type", "") or "")
        t.size_name = str(_first(col, "media-size-name", "") or "")
    # printer-input-tray: "type=sheetFeedAutoRemovableTray;mediafeed=…;level=40;status=0;name=Tray 1;"
    srcs = [str(s) for s in attrs.get("media-source-supported", [])]
    for i, raw in enumerate(attrs.get("printer-input-tray", [])):
        txt = raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
        kv = dict(re.findall(r"(\w+)=([^;]*)", txt))
        name = kv.get("name", "")
        src = _match_source(name, srcs) or (srcs[i] if i < len(srcs) else name)
        t = st.trays.setdefault(src, TrayState(src))
        t.name = name
        try:
            lvl = int(kv.get("level", "-3"))
            mx = int(kv.get("maxcapacity", "-2"))
        except ValueError:
            lvl, mx = -3, -2
        if lvl == 0:
            t.level = 0
        elif lvl > 0:
            t.level = round(lvl * 100 / mx) if mx > 0 else lvl
    return st


def _match_source(name: str, sources: list[str]) -> str | None:
    n = re.sub(r"[^a-z0-9]", "", name.lower())
    for s in sources:
        if re.sub(r"[^a-z0-9]", "", s.lower()) == n:
            return s
    m = re.search(r"(\d+)", name)
    if m:
        for s in sources:
            if re.search(rf"\D{m.group(1)}$", s):
                return s
    return None


# --------------------------------------------------------------------------- #
# Abfragen
# --------------------------------------------------------------------------- #
def host_from_device_uri(uri: str) -> str:
    """lpd://192.168.1.20/print, ipp://drucker.local:631/…, socket://…, dnssd://Name._ipp._tcp.local/… -> Host."""
    m = re.match(r"^[a-z]+://([^/:?]+)", uri or "", re.I)
    if not m:
        return ""
    host = urllib.request.unquote(m.group(1))
    if "._ipp" in host or "._pdl-datastream" in host or "._printer" in host:
        return ""                       # DNS-SD-Dienstname – Host muss der Admin eintragen
    return host


def query(host: str, timeout: float = 4.0) -> DeviceStatus:
    """Fragt zuerst ipps://host/ipp/print, dann ipp://host:631/ipp/print ab."""
    if not host:
        return DeviceStatus(error=tr("Keine Geräteadresse"))
    errors = []
    for scheme, port in (("https", 443), ("https", 631), ("http", 631)):
        uri = f"{'ipps' if scheme == 'https' else 'ipp'}://{host}:{port}/ipp/print"
        url = f"{scheme}://{host}:{port}/ipp/print"
        try:
            req = urllib.request.Request(url, data=build_request(uri), method="POST",
                                         headers={"Content-Type": "application/ipp"})
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE          # Drucker im LAN haben selbstsignierte Zertifikate
            with urllib.request.urlopen(req, timeout=timeout, context=ctx if scheme == "https" else None) as r:
                status, attrs = parse_response(r.read())
            if status >= 0x0400:
                errors.append(tr("{0}: IPP-Status 0x{1:04x}").format(url, status))
                continue
            return interpret(attrs)
        except (OSError, ValueError, socket.timeout) as e:
            errors.append(f"{url}: {e}")
    return DeviceStatus(error="; ".join(errors[-2:]))
