# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Gerät prüfen: was ein Drucker/Plotter über das Netz verrät – roh, zum Weitergeben und Auswerten. No Qt.

    Adresse (aus Anschluss/Einstellung), offene Ports (IPP 631, HTTPS 443, HTTP 80, RAW 9100, LPD 515, FTP 21),
    IPP (alle Attribute inkl. media-col-database, finishings-col-database), SNMP v2c/v1 (sysDescr, sysObjectID,
    prtInputTable, prtMediaPathTable, Herstellerzweig begrenzt), und was Passermark daraus an Rollen macht.
    Stufe: blind (nichts) · status (Rollen/Füllstand) · catalog (Medienkatalog vom Gerät).
    Nur lesend – nichts wird an das Gerät geschickt, das druckt oder etwas ändert (kein RAW-Text an 9100).
"""
from __future__ import annotations

import datetime
import json
import socket
import time

from .l10n import tr

PORTS = {631: "IPP", 443: "HTTPS", 80: "HTTP", 9100: "RAW", 515: "LPD", 21: "FTP"}
SYS_OBJECT = "1.3.6.1.2.1.1.2.0"
SYS_NAME = "1.3.6.1.2.1.1.5.0"
PRT_INPUT = "1.3.6.1.2.1.43.8.2"
PRT_MEDIA_PATH = "1.3.6.1.2.1.43.13.4"
HR_DEVICE_DESCR = "1.3.6.1.2.1.25.3.2.1.3"
VENDOR_LIMIT = 1500


def _jsonable(v):
    if isinstance(v, (bytes, bytearray)):
        try:
            t = bytes(v).decode("utf-8")
            if all(c.isprintable() or c in "\r\n\t" for c in t):
                return t
        except UnicodeDecodeError:
            pass
        return "hex:" + bytes(v).hex()
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    return v


def _port(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _ipp_all(host: str, timeout: float) -> dict:
    import ssl
    import urllib.request
    from . import ipp
    errors = []
    for scheme, port in (("https", 443), ("https", 631), ("http", 631)):
        uri = f"{'ipps' if scheme == 'https' else 'ipp'}://{host}:{port}/ipp/print"
        url = f"{scheme}://{host}:{port}/ipp/print"
        try:
            req = urllib.request.Request(url, data=ipp.build_request(uri, ["all", "media-col-database",
                                                                             "media-col-ready", "printer-input-tray"]),
                                         method="POST", headers={"Content-Type": "application/ipp"})
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(req, timeout=timeout, context=ctx if scheme == "https" else None) as r:
                status, attrs = ipp.parse_response(r.read())
            return {"url": url, "status": f"0x{status:04x}", "attributes": _jsonable(attrs)}
        except Exception as e:                                  # noqa: BLE001 – jede Ursache melden
            errors.append(f"{url}: {e}")
    return {"error": errors}


def run(host: str, printer: str = "", community: str = "", timeout: float = 2.0, progress=None) -> dict:
    """Bericht als dict (JSON-fähig)."""
    from . import rolls, snmp
    rep = {"passermark": "probe", "time": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
           "printer": printer, "host": host, "ports": {}, "ipp": None, "snmp": None, "rolls": None, "level": "blind",
           "notes": []}
    if not host:
        rep["notes"].append(tr("Keine Geräteadresse"))
        return rep
    try:
        rep["address"] = socket.gethostbyname(host)
    except OSError as e:
        rep["notes"].append(tr("Gerät „{0}“ nicht gefunden – Adresse prüfen (unter „Rollen …“ eintragbar)")
                            .format(host) + f" ({e})")
        return rep
    step = lambda t: progress(t) if progress else None              # noqa: E731
    step(tr("Ports …"))
    for port, name in PORTS.items():
        rep["ports"][f"{port}/{name}"] = _port(host, port, timeout)
    if rep["ports"].get("631/IPP") or rep["ports"].get("443/HTTPS"):
        step("IPP …")
        rep["ipp"] = _ipp_all(host, timeout + 2)
    else:
        rep["ipp"] = {"error": [tr("IPP-Port nicht offen")]}
    step("SNMP …")
    com = community or rolls.community_for(host)
    sn = {"community": com}
    try:
        c = snmp.client(host, com, timeout)
        sn["version"] = "v2c" if c.version == 1 else "v1"
        for key, oid in (("sysDescr", snmp.SYS_DESCR), ("sysObjectID", SYS_OBJECT), ("sysName", SYS_NAME)):
            try:
                sn[key] = _jsonable(c.get(oid))
            except snmp.SnmpError as e:
                sn[key] = f"error: {e}"
        for key, oid, lim in (("prtInputTable", PRT_INPUT, 600), ("prtMediaPathTable", PRT_MEDIA_PATH, 300),
                              ("hrDeviceDescr", HR_DEVICE_DESCR, 50)):
            step(f"SNMP {key} …")
            try:
                sn[key] = [[o, _jsonable(v)] for o, v in c.walk(oid, lim)]
            except snmp.SnmpError as e:
                sn[key] = f"error: {e}"
        vendor = str(sn.get("sysObjectID") or "")
        parts = vendor.split(".")
        if vendor.startswith("1.3.6.1.4.1.") and len(parts) > 6:
            base = ".".join(parts[:7])                      # 1.3.6.1.4.1.<Hersteller>
            step(f"SNMP {base} …")
            try:
                sn["vendor_tree"] = {"base": base,
                                     "values": [[o, _jsonable(v)] for o, v in c.walk(base, VENDOR_LIMIT)]}
            except snmp.SnmpError as e:
                sn["vendor_tree"] = {"base": base, "error": str(e)}
        raw = []
        try:
            rows = snmp.input_table(host, com, timeout, raw)
            sn["inputs"] = [_jsonable(r) for r in rows]
            sn["inputs_raw"] = [_jsonable(r) for r in raw]
        except snmp.SnmpError as e:
            sn["inputs"] = f"error: {e}"
    except (OSError, snmp.SnmpError) as e:
        sn["error"] = str(e)
    rep["snmp"] = sn
    step(tr("Rollen …"))
    st = rolls.query(host, force=True, community=com)
    rep["rolls"] = {"origin": st.origin, "error": st.error, "rolls": [dict(r.to_dict(), label=r.label())
                                                                       for r in st.rolls]}
    ipp_attrs = (rep["ipp"] or {}).get("attributes") or {}
    if ipp_attrs.get("media-col-database"):
        rep["level"] = "catalog"
    elif st.rolls:
        rep["level"] = "status"
    if not st.rolls:
        if isinstance(sn.get("prtInputTable"), list) and sn["prtInputTable"]:
            rep["notes"].append(tr("Das Gerät meldet Zufuhren über SNMP, aber keine als Rolle erkennbar – bitte den "
                                   "Bericht schicken."))
        elif sn.get("error"):
            rep["notes"].append(tr("SNMP antwortet nicht (Community „{0}“?).").format(com))
    return rep


def text(rep: dict) -> str:
    """Kurzfassung für die Anzeige; der volle Bericht ist das JSON."""
    L = [tr("Passermark – Gerät prüfen"), f"{rep.get('printer') or ''} {rep.get('host')} "
         f"({rep.get('address', '?')}) · {rep.get('time')}", ""]
    if rep.get("ports"):
        L.append(tr("Ports: ") + ", ".join(f"{k} {tr('offen') if v else '–'}" for k, v in rep["ports"].items()))
    ipp = rep.get("ipp") or {}
    if ipp.get("attributes"):
        a = ipp["attributes"]
        L.append("IPP: " + ipp.get("url", "") + f" – {len(a)} " + tr("Attribute"))
        for k in ("printer-make-and-model", "media-ready", "media-source-supported"):
            if a.get(k):
                L.append(f"  {k}: {', '.join(str(x) for x in a[k][:12])}")
        L.append("  media-col-database: " + (str(len(a.get("media-col-database") or [])) + " " + tr("Einträge")))
    elif ipp:
        L.append("IPP: " + "; ".join(ipp.get("error") or [])[:300])
    sn = rep.get("snmp") or {}
    if sn.get("error"):
        L.append("SNMP: " + sn["error"])
    elif sn:
        L.append(f"SNMP {sn.get('version', '')}: {sn.get('sysDescr', '')}  ({sn.get('sysObjectID', '')})")
        pit = sn.get("prtInputTable")
        L.append("  prtInputTable: " + (f"{len(pit)} " + tr("Werte") if isinstance(pit, list) else str(pit)))
        for r in sn.get("inputs") or [] if isinstance(sn.get("inputs"), list) else []:
            L.append("   · " + ", ".join(f"{k}={v}" for k, v in r.items() if v not in (None, "")))
        vt = sn.get("vendor_tree")
        if vt:
            L.append(f"  {tr('Herstellerzweig')} {vt.get('base')}: "
                     + (f"{len(vt['values'])} " + tr("Werte") if "values" in vt else vt.get("error", "")))
    r = rep.get("rolls") or {}
    L.append("")
    L.append(tr("Rollen: ") + (", ".join(x["label"] for x in r.get("rolls") or []) or "–")
             + (f"  ({r.get('error')})" if r.get("error") else ""))
    L.append(tr("Stufe: ") + {"blind": tr("blind (nur drucken)"), "status": tr("Status (Rollen vom Gerät)"),
                              "catalog": tr("Katalog (Medienliste vom Gerät)")}.get(rep.get("level"), "?"))
    for n in rep.get("notes") or []:
        L.append(tr("Hinweis: {0}").format(n))
    return "\n".join(L) + "\n"


def save(rep: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)


def default_name(rep: dict) -> str:
    import re
    stem = re.sub(r"[^\w.\-]+", "_", rep.get("printer") or rep.get("host") or "geraet")[:40]
    return f"passermark-probe_{stem}_{time.strftime('%Y%m%d-%H%M%S')}.json"
