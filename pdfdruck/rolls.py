# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Rolls of large-format printers and plotters: what is loaded (width, grammage, media, remaining length).

Order: 1. IPP (media-col-ready / printer-input-tray – Canon ColorWave/PlotWave, Epson SureColor T/P, HP …),
       2. SNMP Printer MIB (prtInputTable) for devices without IPP media data,
       3. rolls entered by hand per printer (user setting – no admin rights needed).
The device address comes from the admin setting (tray_host) or from the printer's device URI.
No Qt.
"""

from __future__ import annotations

import re
import sys
import time
from dataclasses import asdict, dataclass, field

from .l10n import tr

CACHE_S = 20
SETTINGS_KEY = "plan_rolls"  # user setting: {printer: [roll, …]}


@dataclass
class Roll:
    """One roll loaded in a large-format printer: width, driver slot, name, grammage, media, remaining length."""

    width_mm: float
    slot: str = ""  # driver value of the source ("" = the device chooses)
    name: str = ""  # display ("Rolle 1")
    weight: int = 0  # g/m², 0 = unbekannt
    media: str = ""  # media name/type according to the device or the input
    remaining_m: float | None = None
    origin: str = "manual"  # ipp | snmp | manual
    device: str = ""  # name of the source on the device (IPP media-source / MIB)
    empty: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> Roll:
        """Create a roll from a dict (tolerates missing or empty values)."""
        rem = d.get("remaining_m")
        return cls(
            float(d.get("width_mm", 0) or 0),
            str(d.get("slot", "") or ""),
            str(d.get("name", "") or ""),
            int(d.get("weight", 0) or 0),
            str(d.get("media", "") or ""),
            None if rem in (None, "") else float(rem),
            str(d.get("origin", "manual") or "manual"),
            str(d.get("device", "") or ""),
            bool(d.get("empty", False)),
        )

    def to_dict(self) -> dict:
        """Plain dict of all fields."""
        return asdict(self)

    def label(self) -> str:
        """Display text: width plus grammage, media and remaining length where known."""
        parts = [tr("{0} mm").format(_mm(self.width_mm))]
        if self.weight:
            parts.append(f"{self.weight} g")
        if self.media:
            parts.append(self.media)
        if self.remaining_m is not None:
            parts.append(tr("~{0} m Rest").format(_mm(self.remaining_m)))
        head = self.name or self.device or self.slot
        return (head + ": " if head else "") + " · ".join(parts)


def _num(v: float, digits: int) -> str:
    from . import l10n, measure

    return measure.fmt(float(v), l10n.current(), digits)


def _mm(v: float) -> str:
    return _num(v, 0) if abs(v - round(v)) < 0.05 else _num(v, 1)


@dataclass
class RollState:
    """The rolls of a printer together with where the information came from (ipp, snmp, manual, none)."""

    rolls: list
    origin: str = "manual"  # ipp | snmp | manual | none
    error: str = ""
    host: str = ""
    catalog: list = field(default_factory=list)  # media defined on the device (also those not loaded), IPP only


# --------------------------------------------------------------------------- #
# query the device
# --------------------------------------------------------------------------- #
def from_ipp(status) -> list:
    """Convert the trays of an IPP status into rolls (only trays that are rolls with a known width)."""
    out = []
    for src, t in status.trays.items():
        if not t.roll or not t.width_mm:
            continue
        out.append(
            Roll(
                float(t.width_mm),
                "",
                t.name or _pretty(src),
                int(t.weight or 0),
                t.media_name or t.media_type,
                t.remaining_m,
                "ipp",
                src,
                t.empty,
            )
        )
    return out


def from_snmp(rows: list) -> list:
    """Convert rows of the SNMP input table into rolls (only rolls with a known width)."""
    out = []
    for r in rows:
        if not r.get("roll") or not r.get("width_mm"):
            continue
        out.append(
            Roll(
                float(r["width_mm"]),
                "",
                r.get("name") or r.get("description") or "",
                int(r.get("weight") or 0),
                r.get("media_name") or r.get("media_type") or "",
                r.get("remaining_m"),
                "snmp",
                r.get("name") or r.get("index", ""),
                bool(r.get("empty")),
            )
        )
    return out


def _pretty(src: str) -> str:
    m = re.search(r"(\d+)", src)
    if m:
        return tr("Rolle {0}").format(m.group(1))
    if re.search(r"main", src, re.I):
        return tr("Rolle 1")
    if re.search(r"alt", src, re.I):
        return tr("Rolle 2")
    return src


_cache: dict = {}


def community_for(host: str) -> str:
    """SNMP community: user setting "snmp_community" ({address: community}), otherwise "public"."""
    from . import l10n

    d = l10n.load_settings().get("snmp_community") or {}
    return str(d.get(host) or d.get("*") or "public") if isinstance(d, dict) else "public"


def query(host: str, force: bool = False, community: str = "") -> RollState:
    """Rolls directly from the device: IPP first, then SNMP."""
    if not host:
        return RollState([], "none", tr("Keine Geräteadresse"))
    hit = _cache.get(host)
    if hit and not force and time.time() - hit[0] < CACHE_S:
        return hit[1]
    from . import ipp

    errors = []
    st = ipp.query(host, timeout=3.0)
    if st.error:
        errors.append("IPP: " + st.error)
    else:
        rl = from_ipp(st)
        if rl:
            res = RollState(rl, "ipp", "", host, list(st.catalog))
            _cache[host] = (time.time(), res)
            return res
        errors.append(tr("IPP: keine Rollen gemeldet"))
    try:
        from . import snmp

        rl = from_snmp(snmp.input_table(host, community or community_for(host)))
        if rl:
            res = RollState(rl, "snmp", "", host)
            _cache[host] = (time.time(), res)
            return res
        errors.append(tr("SNMP: keine Rollen gemeldet"))
    except OSError as e:
        errors.append(f"SNMP: {e}")
    msg = "; ".join(errors)
    if re.search(r"getaddrinfo|Name or service not known|nodename nor servname|11001", msg):
        msg = tr("Gerät „{0}“ nicht gefunden – Adresse prüfen (unter „Rollen …“ eintragbar)").format(host)
    elif re.search(r"timed out|Zeitüberschreitung|refused|10060|10061", msg, re.I) and len(errors) >= 2:
        msg = tr("Gerät {0} antwortet nicht auf IPP/SNMP").format(host)
    res = RollState([], "none", msg, host)
    _cache[host] = (time.time(), res)
    return res


# --------------------------------------------------------------------------- #
# driver source for the roll
# --------------------------------------------------------------------------- #
_ROLLWORD = re.compile(r"roll|rolle", re.I)


def roll_choices(caps) -> list:
    """Choices of the driver's paper source option that denote a roll."""
    key = caps.roles.get("source") if caps else None
    if not key or key not in caps.options:
        return []
    return [c for c in caps.options[key].choices if _ROLLWORD.search(f"{c.value} {c.text}")]


def slot_for(caps, device: str, index: int = 0) -> str:
    """Source in the driver for the roll on the device (roll-1, main-roll, Rolle 2 …). "" = the device chooses."""
    cands = roll_choices(caps)
    if not cands:
        return ""
    real = [c for c in cands if not re.search(r"auto", f"{c.value} {c.text}", re.I)] or cands
    s = device or ""
    m = re.search(r"(\d+)", s)
    n = (
        m.group(1)
        if m
        else (
            "1"
            if re.search(r"main|haupt|upper|oben", s, re.I)
            else "2"
            if re.search(r"alt|lower|unten", s, re.I)
            else None
        )
    )
    if n:
        for c in real:
            if re.search(rf"(?<!\d){n}(?!\d)", f"{c.value} {c.text}"):
                return c.value
        if n == "1" and len(real) == 1:
            return real[0].value  # only "roll paper"
    if index < len(real):
        return real[index].value
    return ""


# --------------------------------------------------------------------------- #
# rolls entered by hand (user setting)
# --------------------------------------------------------------------------- #
def manual(printer: str) -> list:
    """Rolls the user entered by hand for ``printer``."""
    from . import l10n

    d = (l10n.load_settings().get(SETTINGS_KEY) or {}).get(printer) or []
    out = []
    for e in d:
        try:
            r = Roll.from_dict(e)
        except (TypeError, ValueError):
            continue
        if r.width_mm > 0:
            r.origin = "manual"
            out.append(r)
    return out


def save_manual(printer: str, rolls: list) -> None:
    """Store the rolls entered by hand for ``printer`` in the user settings."""
    from . import l10n

    st = l10n.load_settings()
    allr = dict(st.get(SETTINGS_KEY) or {})
    allr[printer] = [
        {"width_mm": r.width_mm, "slot": r.slot, "name": r.name, "weight": r.weight, "media": r.media}
        for r in rolls
        if r.width_mm > 0
    ]
    st[SETTINGS_KEY] = allr
    l10n.save_settings(st)


def parse_widths(text: str) -> list:
    """ "594, 841 914" -> [Roll(594), Roll(841), Roll(914)] (for the command line)."""
    out = []
    for t in re.split(r"[,;\s]+", str(text or "").strip()):
        if not t:
            continue
        w = float(t.replace("mm", "").replace(",", "."))
        if w <= 0:
            raise ValueError(tr("Rollenbreite muss größer als 0 sein: {0}").format(t))
        out.append(Roll(w, name=tr("Rolle {0}").format(len(out) + 1)))
    return out


# --------------------------------------------------------------------------- #
# Alles zusammen
# --------------------------------------------------------------------------- #
def model_of(printer: str) -> str:
    """Model and description of ``printer`` as one string (empty if unknown)."""
    try:
        from . import printers

        for p in printers.list_printers():
            if p.name == printer:
                return f"{p.model} {p.info}"
    except Exception:
        pass
    return ""


def query_roland(host: str) -> RollState:
    """Roland cutting plotters: loaded material width via "OH" (port 9100)."""
    from . import roland

    try:
        d = roland.query(host)
    except OSError as e:
        return RollState([], "none", str(e), host)
    if not d.get("width_mm"):
        return RollState([], "none", tr("Roland: keine Breite gemeldet"), host)
    return RollState(
        [Roll(float(d["width_mm"]), name=tr("Eingelegtes Material"), origin="roland", device="roland")],
        "roland",
        "",
        host,
    )


HOSTS_KEY = "plan_hosts"  # user setting: {printer: device address}


def user_host(printer: str) -> str:
    """Network address the user entered for ``printer`` (empty if none)."""
    from . import l10n

    return str((l10n.load_settings().get(HOSTS_KEY) or {}).get(printer) or "").strip()


def set_user_host(printer: str, host: str) -> None:
    """Store or clear the network address of ``printer``."""
    from . import l10n

    st = l10n.load_settings()
    d = dict(st.get(HOSTS_KEY) or {})
    if host.strip():
        d[printer] = host.strip()
    else:
        d.pop(printer, None)
    st[HOSTS_KEY] = d
    l10n.save_settings(st)


def host_for(session, printer: str) -> str:
    """Device address: own entry (rolls window) > administration (tray_host) > from the port/the queue.
    Windows: "10.30.4.73-HPGL2", standard TCP/IP port (registry), WSD port (WSD device list).
    """
    host = user_host(printer)
    if host:
        return host
    pc = (session.cfg.get("printers") or {}).get(printer, {}) if session is not None else {}
    host = str(pc.get("tray_host", "") or "").strip()
    if host:
        return host
    try:
        from . import ipp, printers

        for p in printers.list_printers():
            if p.name != printer:
                continue
            if sys.platform == "win32":
                from .printers_win import port_host

                return port_host(p.uri, p.name)
            return ipp.host_from_device_uri(p.uri)
    except Exception:
        pass
    return ""


def for_printer(session, printer: str, live: bool = True, force: bool = False) -> RollState:
    """Rolls for the printer: live from the device, otherwise those entered by hand. Mapped to the driver source."""
    caps = None
    try:
        caps = session.caps_for(printer) if session is not None else None
    except Exception:
        caps = None
    st = RollState([], "none")
    if live:
        from . import roland

        host = host_for(session, printer)
        if host and roland.is_roland(printer, model_of(printer)):
            q = query_roland(host)  # never send "OH" to a normal printer (it prints text)
        else:
            q = query(host, force=force)
        st = RollState(
            [Roll.from_dict(r.to_dict()) for r in q.rolls],
            q.origin,
            q.error,
            q.host,  # the cache stays
            list(getattr(q, "catalog", []) or []),
        )
    if not st.rolls:
        mr = manual(printer)
        if mr:
            st = RollState(mr, "manual", st.error, st.host, st.catalog)
    for i, r in enumerate(st.rolls):
        if not r.slot and caps is not None:
            r.slot = slot_for(caps, r.device or r.name, i)
    return st
