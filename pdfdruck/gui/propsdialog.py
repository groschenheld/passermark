# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Datei → Eigenschaften: Speicherort, Datei, Dokument, Seiten, Schriften, Prüfung.

Die Dokumentangaben kommen aus docinfo.inspect – dieselben wie bei passermark-cli inspect – und werden im
Analyse-Prozess gelesen; das Fenster ist sofort da (Speicherort, Größe), der Rest kommt kurz danach.
"""
from __future__ import annotations

import datetime
import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QHeaderView,
                               QLabel, QPushButton, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..l10n import tr
from . import theme


def _size(n) -> str:
    if n is None:
        return "–"
    if n >= 1024 * 1024:
        return tr("{0:.1f} MB ({1} Bytes)").format(n / 1024 / 1024, f"{n:,}".replace(",", "."))
    return tr("{0:.0f} KB ({1} Bytes)").format(n / 1024, f"{n:,}".replace(",", "."))


def _yes(v) -> str:
    return tr("ja") if v else tr("nein")


def _date(v: str) -> str:
    """ISO-Datum aus docinfo (2026-10-17 15:44:26 +02:00) wie im Programm üblich anzeigen."""
    try:
        d = datetime.datetime.strptime(v[:19], "%Y-%m-%d %H:%M:%S")
        return d.strftime("%d.%m.%Y %H:%M:%S") + v[19:]
    except (ValueError, TypeError):
        return v or "–"


def _mm(v) -> str:
    return f"{v:g}".replace(".", ",") if isinstance(v, (int, float)) else "–"


def _label(text, wrap=True, select=True) -> QLabel:
    lb = QLabel(text)
    lb.setWordWrap(wrap)
    if select:
        lb.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return lb


def _table(headers) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    t.horizontalHeader().setStretchLastSection(True)
    return t


def _fill(t: QTableWidget, rows):
    t.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            t.setItem(r, c, QTableWidgetItem("" if v is None else str(v)))


class PropertiesDialog(QDialog):
    """win: MainWindow (path, display_name, modified, _temp_path, _sources, view._src_path)."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle(tr("Eigenschaften – {0}").format(win.display_name or tr("Dokument")))
        self.resize(760, 620)
        v = QVBoxLayout(self)
        self.tabs = QTabWidget()
        v.addWidget(self.tabs, 1)
        self._file_tab()
        self.doc_w, self.pages_w, self.fonts_w, self.check_w = (QWidget(), QWidget(), QWidget(), QWidget())
        for w, name in ((self.doc_w, tr("Dokument")), (self.pages_w, tr("Seiten")), (self.fonts_w, tr("Schriften")),
                        (self.check_w, tr("Prüfung"))):
            lay = QVBoxLayout(w)
            lay.addWidget(_label(tr("Wird gelesen …")))
            lay.addStretch(1)
            self.tabs.addTab(w, name)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.info = None
        self._closed = False
        self._load()

    # ------------------------------------------------------------------ #
    def location(self) -> tuple[str | None, str]:
        """(Datei auf dem Datenträger oder None, Status-Text)."""
        w = self.win
        temp = getattr(w, "_temp_path", None)
        if w.path and os.path.isfile(w.path):
            return w.path, (tr("geändert – noch nicht gespeichert") if w.modified else tr("gespeichert"))
        if temp and os.path.isfile(temp):
            return temp, tr("Zwischenspeicher (temporär) – zum Behalten „Speichern unter …“")
        return None, tr("nur im Arbeitsspeicher – noch nicht gespeichert")

    def _file_tab(self):
        w = QWidget()
        f = QFormLayout(w)
        path, status = self.location()
        f.addRow(tr("Name:"), _label(self.win.display_name or "–"))
        if path:
            f.addRow(tr("Ordner:"), _label(os.path.dirname(path)))
            row = QHBoxLayout()
            b1 = QPushButton(tr("Ordner öffnen"))
            b1.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path))))
            b2 = QPushButton(tr("Pfad kopieren"))
            b2.clicked.connect(lambda: QApplication.clipboard().setText(path))
            row.addWidget(b1)
            row.addWidget(b2)
            row.addStretch(1)
            f.addRow("", row)
            st = os.stat(path)
            f.addRow(tr("Größe:"), _label(_size(st.st_size)))
            f.addRow(tr("Geändert am:"),
                     _label(datetime.datetime.fromtimestamp(st.st_mtime).strftime("%d.%m.%Y %H:%M:%S")))
        f.addRow(tr("Status:"), _label(status))
        src = getattr(self.win, "_sources", None) or []
        if src:
            f.addRow(tr("Entstanden aus:"), _label("\n".join(src)))
        sug = getattr(self.win, "_suggest_dir", "")
        if not path and sug:
            f.addRow(tr("Speichern schlägt vor:"), _label(sug))
        self.lbl_pages_quick = _label(tr("{0} Seite(n)").format(len(self.win.doc)) if self.win.doc is not None else "–")
        f.addRow(tr("Seiten:"), self.lbl_pages_quick)
        self.tabs.addTab(w, tr("Datei"))

    # ------------------------------------------------------------------ #
    def _source_for_analysis(self) -> str | None:
        """Datei mit genau dem aktuellen Inhalt (bei Änderungen die Zwischendatei der Ansicht)."""
        w = self.win
        if not w.modified and w.path and os.path.isfile(w.path) and w.path.lower().endswith(".pdf"):
            return w.path
        tmp = getattr(w.view, "_src_path", None)
        if tmp and os.path.isfile(tmp):
            return tmp
        return None

    def _load(self):
        src = self._source_for_analysis()
        if src is None:
            src = self._save_temp()
        if src is None:
            self._failed(tr("Dokument konnte nicht gelesen werden."))
            return
        from .renderclient import RenderService
        svc = RenderService.get("analysis")
        if svc.ok and os.environ.get("PASSERMARK_RENDER", "") != "local":
            svc.call("inspect", {"path": src}, self._done)
            return
        try:                                             # ohne Analyse-Prozess: hier lesen
            from .. import docinfo
            self._done(None, docinfo.inspect(src, check=True))
        except Exception as e:
            self._done(str(e), None)

    def _save_temp(self) -> str | None:
        import tempfile
        try:
            fd, path = tempfile.mkstemp(prefix="passermark-view-props-", suffix=".pdf")
            with os.fdopen(fd, "wb") as f:
                self.win.doc.save(f)
            self._tmp = path
            return path
        except Exception:
            return None

    def done(self, r):
        self._closed = True
        tmp = getattr(self, "_tmp", None)
        if tmp:
            try:
                os.remove(tmp)
            except OSError:
                pass
        super().done(r)

    def _failed(self, msg):
        for w in (self.doc_w, self.pages_w, self.fonts_w, self.check_w):
            lay = w.layout()
            item = lay.itemAt(0)
            if item and item.widget():
                item.widget().setText(tr("Nicht verfügbar: {0}").format(msg))

    def _done(self, err, info):
        if self._closed:
            return
        if err or not isinstance(info, dict):
            self._failed(err or "?")
            return
        self.info = info
        self._fill_doc(info)
        self._fill_pages(info)
        self._fill_fonts(info.get("check") or {})
        self._fill_check(info.get("check") or {})

    @staticmethod
    def _reset(w: QWidget):
        old = w.layout()
        while old.count():
            it = old.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        return old

    def _fill_doc(self, d):
        lay = self._reset(self.doc_w)
        box = QWidget()
        f = QFormLayout(box)
        m, det = d.get("metadata") or {}, d.get("details") or {}
        f.addRow(tr("PDF-Version:"), _label(d.get("pdf_version", "–")))
        f.addRow(tr("Seiten:"), _label(str(d.get("pages", "–"))))
        for key, text in (("title", tr("Titel:")), ("author", tr("Autor:")), ("subject", tr("Thema:")),
                          ("keywords", tr("Stichwörter:")), ("creator", tr("Erstellt mit:")),
                          ("producer", tr("PDF erzeugt mit:")), ("created", tr("Erstellt am:")),
                          ("modified", tr("Geändert am:"))):
            if m.get(key):
                f.addRow(text, _label(_date(m[key]) if key in ("created", "modified") else m[key]))
        enc = d.get("encrypted")
        f.addRow(tr("Verschlüsselt:"), _label(_yes(enc) + (f" ({det['encryption']})" if enc and det.get("encryption")
                                                            else "")))
        perm = det.get("permissions")
        if perm:
            allowed = [n for k, n in (("print", tr("Drucken")), ("print_highres", tr("Drucken in hoher Qualität")),
                                      ("modify", tr("Ändern")), ("copy", tr("Kopieren")),
                                      ("annotate", tr("Kommentieren")), ("forms", tr("Formulare ausfüllen")))
                       if perm.get(k)]
            denied = [n for k, n in (("print", tr("Drucken")), ("modify", tr("Ändern")), ("copy", tr("Kopieren")))
                      if not perm.get(k)]
            f.addRow(tr("Erlaubt:"), _label(", ".join(allowed) or "–"))
            if denied:
                f.addRow(tr("Gesperrt:"), _label(", ".join(denied)))
        f.addRow(tr("Ausgabeprofil (Output Intent):"), _label(", ".join(det.get("output_intents") or []) or tr("keines")))
        f.addRow(tr("Ebenen:"), _label(str(det.get("layers", 0))))
        f.addRow(tr("Formularfelder:"), _label(str(det.get("form_fields", 0))))
        f.addRow(tr("Kommentare/Stempel:"), _label(str(det.get("annotations", 0))))
        f.addRow(tr("Lesezeichen:"), _label(str(det.get("bookmarks", 0))))
        att = det.get("attachments") or []
        f.addRow(tr("Anhänge:"), _label(", ".join(att) if att else "0"))
        f.addRow(tr("JavaScript:"), _label(_yes(det.get("javascript"))))
        f.addRow(tr("Schnelle Webanzeige:"), _label(_yes(det.get("linearized"))))
        if d.get("converted"):
            f.addRow(tr("Umgewandelt mit:"), _label(d["converted"]))
        lay.addWidget(box)
        lay.addStretch(1)

    def _fill_pages(self, d):
        lay = self._reset(self.pages_w)
        fm = d.get("formats_mm") or []
        lay.addWidget(_label("  ·  ".join(tr("{0} mm: {1} Seite(n)").format(x["size"].replace(".", ","), x["pages"])
                                          for x in fm)))
        t = _table([tr("Seite"), tr("Format (mm)"), tr("Ausrichtung"), tr("Drehung"), tr("Endformat (mm)"),
                    tr("Anschnitt (mm)")])
        orient = {"portrait": tr("Hochformat"), "landscape": tr("Querformat"), "square": tr("Quadratisch")}
        rows = []
        for p in d.get("page_list") or []:
            tm = p.get("trim_mm")
            rows.append((p["page"], f"{_mm(p['width_mm'])} × {_mm(p['height_mm'])}", orient.get(p["orientation"], ""),
                         f"{p['rotate']}°" if p.get("rotate") else "–",
                         f"{_mm(tm[0])} × {_mm(tm[1])}" if tm else "–",
                         _mm(p["bleed_mm"]) if p.get("bleed_mm") is not None else "–"))
        _fill(t, rows)
        lay.addWidget(t, 1)

    def _fill_fonts(self, c):
        lay = self._reset(self.fonts_w)
        fonts = c.get("fonts") or []
        if not fonts:
            lay.addWidget(_label(tr("Keine Schriften.")))
            lay.addStretch(1)
            return
        t = _table([tr("Schrift"), tr("Art"), tr("Eingebettet"), tr("Teilmenge"), tr("Seiten")])
        rows = []
        for fo in fonts:
            pg = fo.get("pages") or []
            rows.append((fo["name"], str(fo.get("subtype", "")).lstrip("/"), _yes(fo.get("embedded")),
                         _yes(fo.get("subset")), ", ".join(map(str, pg[:15])) + (" …" if len(pg) > 15 else "")))
        _fill(t, rows)
        lay.addWidget(t, 1)
        missing = [fo["name"] for fo in fonts if not fo.get("embedded")]
        if missing:
            lb = _label(tr("Nicht eingebettet: {0}").format(", ".join(missing)))
            lb.setStyleSheet(f"color: {theme.ACCENT};")
            lay.addWidget(lb)

    def _fill_check(self, c):
        lay = self._reset(self.check_w)
        cnt = c.get("counts") or {}
        lay.addWidget(_label(tr("{0} Fehler, {1} Warnung(en), {2} Hinweis(e)").format(
            cnt.get("error", 0), cnt.get("warning", 0), cnt.get("info", 0))))
        names = {"error": tr("Fehler"), "warning": tr("Warnung"), "info": tr("Hinweis")}
        t = _table([tr("Art"), tr("Befund"), tr("Seiten")])
        rows = []
        for i in c.get("issues") or []:
            pg = i.get("pages") or []
            rows.append((names.get(i["severity"], i["severity"]), i["message"],
                         ", ".join(map(str, pg[:15])) + (" …" if len(pg) > 15 else "")))
        _fill(t, rows)
        hh = t.horizontalHeader()
        hh.setStretchLastSection(False)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)       # Befund umbrechen statt seitlich scrollen
        t.setWordWrap(True)
        t.resizeRowsToContents()
        hh.sectionResized.connect(lambda *_: t.resizeRowsToContents())
        lay.addWidget(t, 1)
        lay.addWidget(_label(tr("Ausführlich und mit Reparaturen: Druckaufbereitung → Prüfen.")))
