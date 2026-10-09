# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Datenarten für variable Daten: welche Spalten eine Tabelle braucht und wie daraus der Inhalt eines Codes wird.

Eine Datentabelle (CSV) enthält lesbare Spalten – z. B. Vorname, Nachname, Telefon. Den eigentlichen QR-Inhalt
(vCard, WLAN-Zugang, mailto: …) setzt Passermark erst beim Erzeugen zusammen. So bleibt die CSV in Excel lesbar und
änderbar; mehrzeilige Inhalte mit Sonderzeichen landen nie in einer Tabellenzelle.

Spaltennamen werden ohne Rücksicht auf Groß-/Kleinschreibung gesucht.
"""
from __future__ import annotations

import csv
import datetime as _dt
import re
from dataclasses import dataclass, field
from urllib.parse import quote

from .l10n import tr


@dataclass
class Col:
    key: str                     # Spaltenname in der CSV (= Platzhalter {{key}})
    hint: str = ""               # kurze Erklärung (Kopfzeilen-Tooltip, Anleitung)
    required: bool = False
    example: str = ""


@dataclass
class Kind:
    id: str
    title: str
    field_kind: str              # passendes Feld in Variable Daten: qr | code128 | ean13 | text
    cols: list = field(default_factory=list)
    help: str = ""
    free_cols: bool = False      # eigene Spalten erwünscht (Text)


def _kinds() -> dict:
    """Alle Datenarten (Texte bei jedem Aufruf übersetzt)."""
    K = [
        Kind("vcard", tr("QR – Visitenkarte (vCard)"), "qr", [
            Col("Vorname", tr("Vorname"), example="Anna"),
            Col("Nachname", tr("Nachname – Vor- oder Nachname muss ausgefüllt sein"), example="Huber"),
            Col("Firma", tr("Firma oder Organisation"), example="Druckerei Huber"),
            Col("Position", tr("Funktion, z. B. Geschäftsführerin"), example="Geschäftsführerin"),
            Col("Telefon", tr("Festnetz, am besten international: +43 316 123456"), example="+43 316 123456"),
            Col("Mobil", tr("Handynummer"), example="+43 660 1234567"),
            Col("E-Mail", tr("E-Mail-Adresse"), example="anna@huber.at"),
            Col("Straße", tr("Straße und Hausnummer"), example="Hauptplatz 1"),
            Col("PLZ", tr("Postleitzahl"), example="8010"),
            Col("Ort", tr("Ort"), example="Graz"),
            Col("Land", tr("Land"), example="Österreich"),
            Col("Web", tr("Webadresse"), example="https://huber.at"),
            Col("Notiz", tr("freier Text"), example=""),
        ], tr("Das Handy bietet beim Scannen an, den Kontakt zu speichern.")),
        Kind("wifi", tr("QR – WLAN-Zugang"), "qr", [
            Col("Netzname", tr("Name des WLANs (SSID), genau wie am Router"), True, "Gaeste"),
            Col("Passwort", tr("WLAN-Passwort – leer bei offenem Netz"), example="sommer2026"),
            Col("Verschlüsselung", tr("WPA (Standard, auch WPA2/WPA3), WEP oder keine"), example="WPA"),
            Col("Versteckt", tr("ja, wenn das Netz seinen Namen nicht anzeigt – sonst leer"), example=""),
        ], tr("Das Handy verbindet sich nach dem Scannen mit dem WLAN.")),
        Kind("email", tr("QR – E-Mail"), "qr", [
            Col("E-Mail", tr("Empfänger"), True, "info@huber.at"),
            Col("Betreff", tr("Betreff (wird vorausgefüllt)"), example="Anfrage"),
            Col("Text", tr("Nachricht (wird vorausgefüllt)"), example=""),
        ], tr("Öffnet eine neue E-Mail mit Empfänger, Betreff und Text.")),
        Kind("url", tr("QR – Webadresse"), "qr", [
            Col("Adresse", tr("z. B. huber.at/aktion – https:// wird ergänzt"), True, "https://huber.at"),
        ], tr("Öffnet die Webseite.")),
        Kind("phone", tr("QR – Anruf"), "qr", [
            Col("Telefon", tr("Nummer, am besten international: +43 316 123456"), True, "+43 316 123456"),
        ], tr("Das Handy bietet an, die Nummer anzurufen.")),
        Kind("sms", tr("QR – SMS"), "qr", [
            Col("Telefon", tr("Empfänger"), True, "+43 660 1234567"),
            Col("Text", tr("Nachricht (wird vorausgefüllt)"), example="Gewinnspiel"),
        ], tr("Öffnet eine SMS mit Empfänger und Text.")),
        Kind("event", tr("QR – Termin"), "qr", [
            Col("Titel", tr("Name des Termins"), True, "Tag der offenen Tür"),
            Col("Beginn", tr("Datum und Uhrzeit: 24.10.2026 18:00 oder 2026-10-24 18:00 – nur Datum = ganztägig"),
                True, "24.10.2026 18:00"),
            Col("Ende", tr("wie Beginn – leer = eine Stunde nach Beginn"), example="24.10.2026 21:00"),
            Col("Ort", tr("Ort oder Adresse"), example="Hauptplatz 1, Graz"),
            Col("Beschreibung", tr("freier Text"), example=""),
        ], tr("Das Handy bietet an, den Termin in den Kalender zu übernehmen.")),
        Kind("geo", tr("QR – Standort"), "qr", [
            Col("Breite", tr("Breitengrad, z. B. 47.0707"), True, "47.0707"),
            Col("Länge", tr("Längengrad, z. B. 15.4395"), True, "15.4395"),
        ], tr("Öffnet den Ort in der Karten-App.")),
        Kind("qrtext", tr("QR – freier Text"), "qr", [
            Col("Inhalt", tr("beliebiger Text, Nummer oder Adresse"), True, "Ticket 0001"),
        ], tr("Der Text steht genau so im QR-Code.")),
        Kind("code128", tr("Strichcode – Code 128"), "code128", [
            Col("Code", tr("Buchstaben, Ziffern und übliche Zeichen, keine Umlaute"), True, "ART-1001"),
        ], tr("Für Artikel-, Lager- und Ticketnummern.")),
        Kind("ean13", tr("Strichcode – EAN-13"), "ean13", [
            Col("EAN", tr("12 Ziffern (Prüfziffer wird gerechnet) oder 13 Ziffern"), True, "4006381333931"),
        ], tr("Artikelnummer für den Handel (bei GS1 registriert) oder intern 20…–29…")),
        Kind("text", tr("Text – eigene Spalten"), "text", [
            Col("Text", tr("beliebiger Text"), example="Anna Huber"),
        ], tr("Eigene Spalten anlegen, z. B. Name, Tisch, Kategorie."), free_cols=True),
    ]
    return {k.id: k for k in K}


IDS = ("vcard", "wifi", "email", "url", "phone", "sms", "event", "geo", "qrtext", "code128", "ean13", "text")
# QR-Feld „Art“: was im QR-Code steht. "text" = Inhalt wie eingegeben (Vorlage mit Platzhaltern)
QR_TYPES = ("text", "vcard", "wifi", "email", "url", "phone", "sms", "event", "geo")


def kinds() -> dict:
    return _kinds()


def get(kind_id: str) -> Kind:
    k = _kinds().get(kind_id)
    if k is None:
        raise ValueError(tr("Unbekannte Datenart: {0}").format(kind_id))
    return k


def qr_type_text(t: str) -> str:
    if t in ("", "text"):
        return tr("Inhalt wie eingegeben")
    return get(t).title.replace(tr("QR – "), "")


# --------------------------------------------------------------------------- #
# Spalten lesen
# --------------------------------------------------------------------------- #
def _v(rec: dict, key: str) -> str:
    if key in rec:
        return str(rec[key] or "").strip()
    low = key.lower()
    for k, v in rec.items():
        if isinstance(k, str) and k.lower() == low:
            return str(v or "").strip()
    return ""


def guess_kind(cols: list) -> str:
    """Datenart aus den Spaltennamen einer CSV erraten (meiste Übereinstimmung, Pflichtspalten vorhanden)."""
    have = {c.lower() for c in cols}
    best, score = "text", 0
    for kid in IDS:
        k = get(kid)
        if k.free_cols:
            continue
        keys = [c.key.lower() for c in k.cols]
        if not all(c.key.lower() in have for c in k.cols if c.required):
            continue
        n = sum(1 for c in keys if c in have)
        # Anteil, damit „Telefon“ allein nicht zur Visitenkarte wird
        sc = n * 10 - (len(keys) - n) + (5 if n == len(keys) else 0)
        if n and sc > score:
            best, score = kid, sc
    return best


# --------------------------------------------------------------------------- #
# Inhalt zusammensetzen
# --------------------------------------------------------------------------- #
def _vesc(s: str) -> str:
    """vCard/iCal-Text maskieren."""
    return (s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def _wesc(s: str) -> str:
    """WLAN-Text maskieren (\\ ; , : ")."""
    return re.sub(r'([\\;,:"])', r"\\\1", s)


def _tel(s: str) -> str:
    s = s.strip()
    plus = s.startswith("+") or s.startswith("00")
    digits = re.sub(r"\D", "", s)
    if s.startswith("00"):
        digits = digits[2:]
    return ("+" if plus else "") + digits


def _yes(s: str) -> bool:
    return s.strip().lower() in ("ja", "j", "yes", "y", "true", "1", "x", "igen", "sí", "si", "oui")


_DT_FORMATS = ("%d.%m.%Y %H:%M", "%d.%m.%Y %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M",
               "%Y-%m-%dT%H:%M:%S", "%d.%m.%y %H:%M")
_D_FORMATS = ("%d.%m.%Y", "%Y-%m-%d", "%d.%m.%y")


def parse_when(s: str):
    """'24.10.2026 18:00' -> datetime; '24.10.2026' -> date; sonst ValueError."""
    s = (s or "").strip()
    for f in _DT_FORMATS:
        try:
            return _dt.datetime.strptime(s, f)
        except ValueError:
            pass
    for f in _D_FORMATS:
        try:
            return _dt.datetime.strptime(s, f).date()
        except ValueError:
            pass
    raise ValueError(tr("Datum nicht erkannt: „{0}“ (z. B. 24.10.2026 18:00)").format(s))


def _ical(d) -> str:
    if isinstance(d, _dt.datetime):
        return d.strftime("%Y%m%dT%H%M%S")
    return d.strftime("%Y%m%d")


def _num(s: str) -> float:
    return float(s.strip().replace(",", "."))


def build(kind_id: str, rec: dict) -> str:
    """Inhalt des Codes für einen Datensatz. Fehlende Pflichtangaben -> ValueError mit verständlicher Meldung."""
    k = get(kind_id)
    for c in k.cols:
        if c.required and not _v(rec, c.key):
            raise ValueError(tr("{0}: Spalte „{1}“ ist leer oder fehlt").format(k.title, c.key))
    g = lambda key: _v(rec, key)                       # noqa: E731
    if kind_id == "url":
        a = g("Adresse")
        return a if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", a) else "https://" + a
    if kind_id == "email":
        q = [(n, g(c)) for n, c in (("subject", "Betreff"), ("body", "Text")) if g(c)]
        tail = "&".join(f"{n}={quote(v, safe='')}" for n, v in q)
        return "mailto:" + g("E-Mail") + ("?" + tail if tail else "")
    if kind_id == "phone":
        return "tel:" + _tel(g("Telefon"))
    if kind_id == "sms":
        return f"SMSTO:{_tel(g('Telefon'))}:{g('Text')}"
    if kind_id == "wifi":
        enc = g("Verschlüsselung").upper().replace(" ", "")
        if enc in ("", "WPA", "WPA2", "WPA3", "WPA/WPA2", "WPA2/WPA3"):
            enc = "WPA"
        elif enc in ("KEINE", "KEIN", "OFFEN", "NONE", "NOPASS", "-"):
            enc = "nopass"
        elif enc != "WEP":
            raise ValueError(tr("WLAN: Verschlüsselung „{0}“ unbekannt – WPA, WEP oder keine").format(
                g("Verschlüsselung")))
        if enc != "nopass" and not g("Passwort"):
            enc = "nopass"
        parts = [f"T:{enc}", f"S:{_wesc(g('Netzname'))}"]
        if enc != "nopass":
            parts.append(f"P:{_wesc(g('Passwort'))}")
        if _yes(g("Versteckt")):
            parts.append("H:true")
        return "WIFI:" + ";".join(parts) + ";;"
    if kind_id == "vcard":
        vn, nn = g("Vorname"), g("Nachname")
        if not (vn or nn or g("Firma")):
            raise ValueError(tr("Visitenkarte: Vorname, Nachname oder Firma ausfüllen"))
        fn = " ".join(x for x in (vn, nn) if x) or g("Firma")
        L = ["BEGIN:VCARD", "VERSION:3.0", f"N:{_vesc(nn)};{_vesc(vn)};;;", f"FN:{_vesc(fn)}"]
        if g("Firma"):
            L.append(f"ORG:{_vesc(g('Firma'))}")
        if g("Position"):
            L.append(f"TITLE:{_vesc(g('Position'))}")
        if g("Telefon"):
            L.append(f"TEL;TYPE=WORK,VOICE:{_tel(g('Telefon'))}")
        if g("Mobil"):
            L.append(f"TEL;TYPE=CELL:{_tel(g('Mobil'))}")
        if g("E-Mail"):
            L.append(f"EMAIL;TYPE=INTERNET:{g('E-Mail')}")
        if any(g(c) for c in ("Straße", "PLZ", "Ort", "Land")):
            L.append("ADR;TYPE=WORK:;;{0};{1};;{2};{3}".format(*(_vesc(g(c)) for c in ("Straße", "Ort", "PLZ", "Land"))))
        if g("Web"):
            L.append(f"URL:{g('Web')}")
        if g("Notiz"):
            L.append(f"NOTE:{_vesc(g('Notiz'))}")
        L.append("END:VCARD")
        return "\r\n".join(L)
    if kind_id == "event":
        start = parse_when(g("Beginn"))
        if g("Ende"):
            end = parse_when(g("Ende"))
        elif isinstance(start, _dt.datetime):
            end = start + _dt.timedelta(hours=1)
        else:
            end = start + _dt.timedelta(days=1)
        if type(start) is not type(end):
            raise ValueError(tr("Termin: Beginn und Ende beide mit Uhrzeit oder beide ohne"))
        if end < start:
            raise ValueError(tr("Termin: Ende liegt vor dem Beginn"))
        val = "" if isinstance(start, _dt.datetime) else ";VALUE=DATE"
        L = ["BEGIN:VEVENT", f"SUMMARY:{_vesc(g('Titel'))}", f"DTSTART{val}:{_ical(start)}", f"DTEND{val}:{_ical(end)}"]
        if g("Ort"):
            L.append(f"LOCATION:{_vesc(g('Ort'))}")
        if g("Beschreibung"):
            L.append(f"DESCRIPTION:{_vesc(g('Beschreibung'))}")
        L.append("END:VEVENT")
        return "\r\n".join(L)
    if kind_id == "geo":
        try:
            la, lo = _num(g("Breite")), _num(g("Länge"))
        except ValueError:
            raise ValueError(tr("Standort: Breite und Länge als Zahl, z. B. 47.0707")) from None
        if not (-90 <= la <= 90 and -180 <= lo <= 180):
            raise ValueError(tr("Standort: Breite −90…90, Länge −180…180"))
        return f"geo:{la:g},{lo:g}"
    if kind_id == "qrtext":
        return g("Inhalt")
    if kind_id == "code128":
        return g("Code")
    if kind_id == "ean13":
        return re.sub(r"\D", "", g("EAN"))
    return g("Text")


# --------------------------------------------------------------------------- #
# Prüfen
# --------------------------------------------------------------------------- #
def ean_problem(value: str) -> str:
    """Leer = in Ordnung; sonst Meldung. 13 Ziffern mit falscher Prüfziffer werden gemeldet."""
    from .vdp import check_digit
    raw = (value or "").strip()
    d = re.sub(r"\D", "", raw)
    if re.search(r"[^\d\s-]", raw):
        return tr("nur Ziffern erlaubt")
    if len(d) not in (12, 13):
        return tr("{0} Ziffern – EAN-13 braucht 12 oder 13").format(len(d))
    if len(d) == 13 and check_digit(d[:12], "ean") != d[12]:
        return tr("Prüfziffer falsch: richtig wäre {0}").format(d[:12] + check_digit(d[:12], "ean"))
    return ""


def validate(kind_id: str, cols: list, rows: list) -> list:
    """Probleme als Liste (zeile0, spalte|"", meldung); leere Zeilen werden übersprungen."""
    k = get(kind_id)
    out = []
    have = {c.lower() for c in cols}
    for c in k.cols:
        if c.required and c.key.lower() not in have:
            out.append((-1, c.key, tr("Spalte „{0}“ fehlt").format(c.key)))
    if out:
        return out
    for i, rec in enumerate(rows):
        if not any(str(v or "").strip() for v in rec.values()):
            continue
        try:
            value = build(kind_id, rec)
        except ValueError as e:
            out.append((i, "", str(e)))
            continue
        if kind_id == "ean13":
            p = ean_problem(_v(rec, "EAN"))
            if p:
                out.append((i, "EAN", p))
        elif kind_id == "code128":
            bad = sorted({ch for ch in value if ord(ch) < 32 or ord(ch) > 126})
            if bad:
                out.append((i, "Code", tr("Zeichen nicht möglich: {0}").format(" ".join(bad))))
        elif kind_id == "email" and "@" not in _v(rec, "E-Mail"):
            out.append((i, "E-Mail", tr("keine gültige E-Mail-Adresse")))
        if k.field_kind == "qr" and len(value.encode("utf-8")) > 2000:
            out.append((i, "", tr("Inhalt sehr lang ({0} Zeichen) – QR-Code wird sehr fein").format(len(value))))
    return out


# --------------------------------------------------------------------------- #
# Tabellen
# --------------------------------------------------------------------------- #
def columns(kind_id: str) -> list:
    return [c.key for c in get(kind_id).cols]


def example_row(kind_id: str) -> dict:
    return {c.key: c.example for c in get(kind_id).cols}


def series(n: int, start: int = 1, step: int = 1, digits: int = 0, prefix: str = "", suffix: str = "",
           check: str = "none") -> list:
    """Nummernreihe für eine Spalte, z. B. T0001 … (gleiche Regeln wie die Nummerierung)."""
    from .vdp import Numbering, format_number
    nb = Numbering(start=start, step=step, digits=digits, prefix=prefix, suffix=suffix, check=check)
    return [format_number(start + i * step, nb) for i in range(n)]


def write_csv(path: str, cols: list, rows: list) -> None:
    """UTF-8 mit BOM (Excel erkennt Umlaute), Semikolon, Zeilen ohne Inhalt fallen weg."""
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        w.writerow(cols)
        for r in rows:
            vals = [str(r.get(c, "") or "") for c in cols]
            if any(v.strip() for v in vals):
                w.writerow(vals)
