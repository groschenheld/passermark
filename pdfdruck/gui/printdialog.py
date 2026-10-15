# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Eigener Druckdialog (Acrobat-Layout): Einstellungen links, Live-Vorschau rechts."""
from __future__ import annotations

from ..l10n import tr

import os
import re

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog,
                               QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGridLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QRadioButton, QScrollArea, QSpinBox, QStackedWidget,
                               QVBoxLayout, QWidget)

from .. import config, layout, printers, printjob, proof, trays
from . import theme
from .common import CollapsibleSection, Session, fill_combo, fit_width, guard_wheel, render_pixmap

ROLE_LABELS = [("pagesize", "Papierformat"), ("source", "Papierzufuhr / Fach"),
               ("mediatype", "Medientyp"), ("duplex", "Beidseitig"), ("color", "Farbmodus"),
               ("quality", "Qualität"), ("outputbin", "Ausgabefach")]
FINISH_LABELS = [("saddle", "Sattelheftung / Broschüre"), ("staple", "Heften"), ("punch", "Lochen"),
                 ("fold", "Falzen"), ("trim", "Beschnitt"), ("stacker", "Stapler / Versatz")]


class PageBox(QWidget):
    """Statt QStackedWidget: nur die sichtbare Seite ist im Layout — die Gruppe
    passt ihre Höhe in JEDEM Modus exakt an (kein Leerraum, keine Riesen-Reserve)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pages: list[QWidget] = []
        self._idx = -1
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._lay = lay

    def addWidget(self, w: QWidget):
        self._pages.append(w)
        self._lay.addWidget(w)
        w.hide()
        if self._idx < 0:
            self.setCurrentIndex(0)

    def count(self) -> int:
        return len(self._pages)

    def currentIndex(self) -> int:
        return self._idx

    def currentWidget(self):
        return self._pages[self._idx] if 0 <= self._idx < len(self._pages) else None

    def setCurrentIndex(self, i: int):
        if i == self._idx or not (0 <= i < len(self._pages)):
            return
        if 0 <= self._idx < len(self._pages):
            self._pages[self._idx].hide()
        self._idx = i
        self._pages[i].show()


class Preview(QWidget):
    """Zeigt ein ausgeschossenes Blatt in Leserichtung + bedruckbaren Bereich.
    Bei Duplex zusätzlich die Rückseite – links/rechts/darunter, je nach Wendekante."""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(380, 460)
        self.pixmap = None
        self.back = None                # Rückseite (Pixmap) oder None
        self.back_side = None           # "left" | "right" | "below" | "above"
        self.sheet = None
        self.landscape = False

    def set_content(self, pixmap, sheet, landscape, back=None, back_side=None):
        self.pixmap, self.sheet, self.landscape = pixmap, sheet, landscape
        self.back, self.back_side = back, back_side
        self.update()

    def _rects(self):
        """Rechtecke (vorne, hinten|None) in Vorschaukoordinaten, gemeinsam skaliert."""
        if not self.sheet:
            return None, None
        w, h = self.sheet.width, self.sheet.height
        if self.landscape:
            w, h = h, w
        m, gap, lab = 16, 10, 14
        pair = self.back is not None and self.back_side in ("left", "right", "below", "above")
        nx = 2 if pair and self.back_side in ("left", "right") else 1
        ny = 2 if pair and self.back_side in ("below", "above") else 1
        s = min((self.width() - 2 * m) / max(1.0, w * nx + gap * (nx - 1)),
                (self.height() - 2 * m - lab) / max(1.0, h * ny + gap * (ny - 1)))
        pw, ph = w * s, h * s
        x0 = (self.width() - (pw * nx + gap * (nx - 1))) / 2
        y0 = lab + (self.height() - lab - (ph * ny + gap * (ny - 1))) / 2
        front = QRectF(x0, y0, pw, ph)
        back = None
        if pair:
            bx = x0 + (pw + gap if self.back_side == "right" else -(pw + gap) if self.back_side == "left" else 0)
            by = y0 + (ph + gap if self.back_side == "below" else -(ph + gap) if self.back_side == "above" else 0)
            back = QRectF(bx, by, pw, ph)
        return front, back

    def _draw_sheet(self, p, r, pixmap, label):
        p.fillRect(r.translated(3, 3), QColor(0, 0, 0, 120))
        p.fillRect(r, Qt.GlobalColor.white)
        if pixmap is not None:
            p.drawPixmap(r, pixmap, QRectF(pixmap.rect()))
        # bedruckbarer Bereich (gestrichelt)
        LW, LH, (x, y, w, h) = layout._logical(self.sheet, self.landscape)
        s = r.width() / LW
        pen = QPen(QColor(theme.ACCENT), 1, Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.drawRect(QRectF(r.left() + x * s, r.top() + (LH - y - h) * s, w * s, h * s))
        p.setPen(QColor(theme.BORDER))
        p.drawRect(r)
        p.setPen(QColor(theme.MUTED))
        p.drawText(int(r.left()), int(r.top()) - 4, label)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.VIEW))
        if not self.sheet:
            return
        front, back = self._rects()
        self._draw_sheet(p, front, self.pixmap, tr("Vorderseite"))
        if back is not None:
            self._draw_sheet(p, back, self.back, tr("Rückseite"))


class SideTab(QPushButton):
    """Senkrechter Reiter am linken Dialogrand (gelb, Text von unten nach oben, Pfeil zum Öffnen).
        Öffnet/schließt ein zugehöriges Fenster; der Pfeil zeigt, ob es offen ist, der Punkt,
        ob die Funktion aktiv ist."""
    W = 30

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._text = text
        self.window_fn = lambda: None          # -> das zugehörige Fenster (für den Offen-Zustand)
        self.active_fn = lambda: False         # -> Funktion zugeschaltet?
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(self.W)
        fm = self.fontMetrics()
        self.setFixedHeight(fm.horizontalAdvance(text) + 2 * self.W + 24)
        self.setAccessibleName(text)

    def watch(self, w):
        w.installEventFilter(self)

    def eventFilter(self, obj, ev):
        from PySide6.QtCore import QEvent
        if ev.type() in (QEvent.Type.Show, QEvent.Type.Hide, QEvent.Type.WindowStateChange):
            self.update()
        return False

    def _open(self) -> bool:
        w = self.window_fn()
        return bool(w is not None and w.isVisible() and not w.isMinimized())

    def paintEvent(self, _e):
        from PySide6.QtGui import QPainterPath, QPolygonF
        from PySide6.QtCore import QPointF
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        bg = QColor(theme.ACCENT)
        if self.isDown() or self._open():
            bg = bg.darker(118)
        elif self.underMouse():
            bg = bg.lighter(110)
        # links abgerundet, rechts bündig am Dialog
        rad = 7.0
        path = QPainterPath()
        path.moveTo(r.right(), r.top())
        path.lineTo(r.left() + rad, r.top())
        path.quadTo(r.left(), r.top(), r.left(), r.top() + rad)
        path.lineTo(r.left(), r.bottom() - rad)
        path.quadTo(r.left(), r.bottom(), r.left() + rad, r.bottom())
        path.lineTo(r.right(), r.bottom())
        path.closeSubpath()
        p.fillPath(path, bg)
        ink = QColor("#1b1d20")
        # Pfeil oben: ◀ = öffnen (Fenster geht nach links auf), ▶ = schließen
        cx, cy, a = r.center().x(), r.top() + self.W / 2 + 2, 5.5
        pts = ([QPointF(cx + a * .6, cy - a), QPointF(cx - a * .6, cy), QPointF(cx + a * .6, cy + a)]
               if not self._open() else
               [QPointF(cx - a * .6, cy - a), QPointF(cx + a * .6, cy), QPointF(cx - a * .6, cy + a)])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(ink)
        p.drawPolygon(QPolygonF(pts))
        # Text von unten nach oben
        p.save()
        p.translate(r.center().x(), r.center().y() + self.W / 2 - 4)
        p.rotate(-90)
        f = p.font()
        f.setBold(True)
        p.setFont(f)
        p.setPen(ink)
        h = self.height() - self.W - 20
        p.drawText(QRectF(-h / 2, -self.W / 2, h, self.W), int(Qt.AlignmentFlag.AlignCenter), self._text)
        p.restore()
        # aktiv: Punkt unten
        if self.active_fn():
            p.setBrush(ink)
            p.drawEllipse(QPointF(cx, r.bottom() - 10), 3.5, 3.5)
        if self.hasFocus():
            p.setPen(QPen(ink, 1, Qt.PenStyle.DotLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(r.adjusted(3, 3, -3, -3))
        p.end()

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)


class PrintDialog(QDialog):
    def __init__(self, parent, doc, path: str, current: int, session: Session):
        super().__init__(parent)
        self.setWindowTitle(tr("Drucken"))
        self.resize(1180, 760)
        self.doc, self.path, self.current, self.s = doc, path, current, session
        self.cfg = session.cfg
        self.sizes = [doc.get_page_size(i) for i in range(len(doc))]
        self.caps: printers.PrinterCaps | None = None
        self.plans: list[layout.SheetPlan] = []
        self.plans1 = None            # Schritt 1: Pläne auf dem gewählten Papier (bei Schritt 2)
        self.plans2 = None            # Schritt 2: Pläne auf dem Zielformat (für Vorschau/Ausgabe)
        self.sheet_index = 0
        self._preview_timer = QTimer(self, singleShot=True, interval=150, timeout=self._update_preview)

        root = self._root = QHBoxLayout(self)
        left = QVBoxLayout()
        # Preset oben: gilt für die ganze linke Spalte (ohne Drucker/Fach)
        from .presetbar import PresetBar
        self.presetbar = PresetBar(self, "impose", self._preset_settings, self._load_layout)
        self.presetbar.setToolTip(tr("Seitenhandhabung, Broschüre, Poster, Nutzen und weitere Optionen – ohne Drucker"))
        left.addWidget(self.presetbar)
        # Eine durchlaufende Spalte statt Reiter: Führung von oben nach unten
        self.general = QWidget()
        self.general.setMinimumWidth(380)
        left.addWidget(self._scroll(self.general), 1)

        right = QVBoxLayout()
        # Einstellungen | Vorschau mit verschiebbarem Teiler (breiter ziehen statt abgeschnitten)
        from PySide6.QtWidgets import QSplitter
        lw, rw = QWidget(), QWidget()
        lw.setLayout(left)
        rw.setLayout(right)
        self.split = QSplitter(Qt.Orientation.Horizontal)
        self.split.addWidget(lw)
        self.split.addWidget(rw)
        self.split.setStretchFactor(0, 0)
        self.split.setStretchFactor(1, 1)
        self.split.setChildrenCollapsible(False)
        self.split.setSizes([560, 620])
        root.addWidget(self.split)
        self.preview = Preview()
        right.addWidget(self.preview, 1)
        nav = QHBoxLayout()
        self.btn_prev = QPushButton("◀")
        self.btn_next = QPushButton("▶")
        self.lbl_sheet = QLabel()
        self.lbl_sheet.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_prev.clicked.connect(lambda: self._step_sheet(-1))
        self.btn_next.clicked.connect(lambda: self._step_sheet(+1))
        nav.addWidget(self.btn_prev)
        nav.addWidget(self.lbl_sheet, 1)
        nav.addWidget(self.btn_next)
        right.addLayout(nav)
        self.lbl_info = QLabel()
        self.lbl_info.setWordWrap(True)
        right.addWidget(self.lbl_info)
        prow = QHBoxLayout()
        self.chk_proof = QCheckBox(tr("Farbwirkung simulieren"))
        self.chk_proof.setChecked(True)
        self.chk_proof.setToolTip(tr("Softproof mit gewähltem Farbprofil (exakt, LittleCMS) und Annäherung an "
                                  "Helligkeit/Kontrast/Sättigung/Graustufen des Treibers. Zum Vergleichen abschalten."))
        self.chk_proof.toggled.connect(lambda _b: self._render_sheet())
        prow.addWidget(self.chk_proof)
        self.lbl_proof = QLabel()
        self.lbl_proof.setWordWrap(True)
        self.lbl_proof.setStyleSheet(f"color: {theme.ACCENT};")
        prow.addWidget(self.lbl_proof, 1)
        right.addLayout(prow)
        self.lbl_warn = QLabel()
        self.lbl_warn.setWordWrap(True)
        self.lbl_warn.setStyleSheet(f"color: {theme.ERROR};")
        right.addWidget(self.lbl_warn)
        bb = QDialogButtonBox()
        self.btn_print = bb.addButton(tr("Drucken"), QDialogButtonBox.ButtonRole.AcceptRole)
        self.btn_print.setDefault(True)
        bb.addButton(tr("Abbrechen"), QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(self._print)
        bb.rejected.connect(self.reject)
        right.addWidget(bb)

        self._build_general()
        fit_width(self)
        self._load_printers()

    @staticmethod
    def _scroll(w):
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        sa.setWidget(w)
        return sa

    # ================================================================== #
    # Aufbau "Allgemein"
    # ================================================================== #
    def _section(self, title: str, expanded: bool = True):
        """Einheitlicher einklappbarer Abschnitt mit Formular im Haupt-Layout."""
        sec = CollapsibleSection(title, expanded=expanded)
        self._col.addWidget(sec)
        inner = QWidget()
        sec.body_layout.addWidget(inner)
        sec.form = QFormLayout(inner)
        return sec

    def _build_general(self):
        v = QVBoxLayout(self.general)
        self._col = v

        # Drucker
        sec = self._section(tr("Drucker"))
        f = sec.form
        self.cmb_printer = QComboBox()
        self.cmb_printer.currentIndexChanged.connect(self._printer_changed)
        f.addRow(tr("Name:"), self.cmb_printer)
        self.lbl_pstate = QLabel()
        self.lbl_pstate.setWordWrap(True)
        f.addRow(tr("Status:"), self.lbl_pstate)
        self.lbl_admin = QLabel()
        self.lbl_admin.setWordWrap(True)
        self.lbl_admin.setStyleSheet(f"color: {theme.MUTED};")
        f.addRow(tr("Standards:"), self.lbl_admin)
        self.btn_reset = QPushButton(tr("Auf Admin-Standards zurücksetzen"))
        self.btn_reset.clicked.connect(self._reset_to_admin)
        f.addRow("", self.btn_reset)
        # nur beim Speichern als PDF: Passwortschutz
        self.pw_box = QWidget()
        pv = QVBoxLayout(self.pw_box)
        pv.setContentsMargins(0, 0, 0, 0)
        self.chk_pw = QCheckBox(tr("PDF mit Passwort schützen (AES-256)"))
        pv.addWidget(self.chk_pw)
        prow = QHBoxLayout()
        self.ed_pw, self.ed_pw2 = QLineEdit(), QLineEdit()
        for ed, ph in ((self.ed_pw, tr("Passwort")), (self.ed_pw2, tr("wiederholen"))):
            ed.setEchoMode(QLineEdit.EchoMode.Password)
            ed.setPlaceholderText(ph)
            ed.setEnabled(False)
            prow.addWidget(ed)
        pv.addLayout(prow)
        self.chk_pw.toggled.connect(lambda on: (self.ed_pw.setEnabled(on), self.ed_pw2.setEnabled(on)))
        self.pw_box.setToolTip(tr("Zum Öffnen der gespeicherten Datei wird das Passwort verlangt. "
                                  "Es wird nirgends gespeichert – gut merken."))
        self.pw_box.hide()
        f.addRow(tr("Schutz:"), self.pw_box)
        self._pw_form = f
        row = QHBoxLayout()
        self.spn_copies = QSpinBox()
        self.spn_copies.setRange(1, 9999)
        self.spn_copies.setValue(self.s.copies)
        self.chk_collate = QCheckBox(tr("Sortieren"))
        self.chk_collate.setChecked(self.s.collate)
        row.addWidget(self.spn_copies)
        row.addWidget(self.chk_collate)
        row.addStretch()
        f.addRow(tr("Kopien:"), row)

        # Seiten
        sec = self._section(tr("Zu druckende Seiten"))
        gw = QWidget()
        sec.body_layout.addWidget(gw)
        gl = QGridLayout(gw)
        self.rb_all = QRadioButton(tr("Alle"))
        self.rb_cur = QRadioButton(tr("Aktuelle Seite ({0})").format(self.current + 1))
        self.rb_range = QRadioButton(tr("Seiten:"))
        self.rb_all.setChecked(True)
        self.ed_range = QLineEdit()
        self.ed_range.setPlaceholderText(tr("z. B. 1-3, 5, 8-{0}").format(len(self.doc)))
        self.ed_range.textEdited.connect(lambda _: self.rb_range.setChecked(True))
        self.cmb_subset = QComboBox()
        fill_combo(self.cmb_subset, [("all", tr("Alle Seiten im Bereich")), ("odd", tr("Nur ungerade Seiten")),
                                     ("even", tr("Nur gerade Seiten"))], self.s.subset)
        self.chk_reverse = QCheckBox(tr("Seiten in umgekehrter Reihenfolge"))
        self.chk_reverse.setChecked(self.s.reverse)
        gl.addWidget(self.rb_all, 0, 0)
        gl.addWidget(self.rb_cur, 1, 0)
        gl.addWidget(self.rb_range, 2, 0)
        gl.addWidget(self.ed_range, 2, 1)
        gl.addWidget(self.cmb_subset, 3, 0, 1, 2)
        gl.addWidget(self.chk_reverse, 4, 0, 1, 2)

        # page size and handling
        L = self.s.layout
        sec = CollapsibleSection(tr("Was soll gedruckt werden?"), expanded=True)
        self.handling_group = sec      # sofort verankert, einheitliche Überschrift
        v.addWidget(sec)
        gv = sec.body_layout
        tog = QVBoxLayout()            # Knöpfe untereinander: immer lesbar
        self.handling_btns = {}
        bg = QButtonGroup(self)
        for key, text, page in [("size", tr("Einzelblätter"), 0), ("multiple", tr("Mehrere pro Blatt"), 1),
                                ("booklet", tr("Broschüre"), 2), ("poster", tr("Poster"), 3)]:
            b = QPushButton(text)
            b.setCheckable(True)
            b.setProperty("handling", key)
            b.setProperty("page", page)
            bg.addButton(b)
            tog.addWidget(b)
            self.handling_btns[key] = b
        gv.addLayout(tog)
        # Step & Repeat: kein Modus, sondern ein eigenes Fenster, das auf den gewählten Modus wirkt
        # (Einzelblätter: die Seiten, Broschüre: die Druckbögen) – inkl. Schritt 2
        # als senkrechter gelber Reiter am linken Dialogrand (öffnet/schließt das Fenster)
        self.btn_srwin = SideTab(tr("Step && Repeat …").replace("&&", "&"))
        self.btn_srwin.setToolTip(tr("Öffnet das Step-&-Repeat-Fenster: Mehrfachnutzen zuschalten und einstellen, "
                                     "optional Schritt 2 auf ein Zielformat. Wirkt nur zusammen mit diesem Druckdialog."))
        self.btn_srwin.clicked.connect(self._toggle_sr_window)
        _tabcol = QVBoxLayout()
        _tabcol.setContentsMargins(0, 40, 0, 0)
        _tabcol.addWidget(self.btn_srwin)
        _tabcol.addStretch(1)
        _m = self._root.contentsMargins()
        self._root.setContentsMargins(0, _m.top(), _m.right(), _m.bottom())
        self._root.insertLayout(0, _tabcol)
        self.lbl_modehint = QLabel()
        self.lbl_modehint.setWordWrap(True)
        self.lbl_modehint.setStyleSheet(f"color: {theme.MUTED};")
        gv.addWidget(self.lbl_modehint)
        self.stack = PageBox()
        gv.addWidget(self.stack)
        self.stack.addWidget(QWidget())          # Seite 0: Einzelblätter – Optionen stehen bei „Wie aufs Blatt?“

        # -- Size-Optionen (Anpassen/Tatsächlich/…) stehen jetzt in der Gruppe
        #    „Wie aufs Blatt?“ weiter unten – nicht mehr als eigene Stack-Seite.

        # -- Mehrere
        mg = QWidget()
        self.stack.addWidget(mg)      # sofort verankern, dann füllen
        ml = QFormLayout(mg)
        row = QHBoxLayout()
        self.cmb_nup = QComboBox()
        fill_combo(self.cmb_nup, [(n, str(n)) for n in (2, 4, 6, 8, 9, 16)] + [(0, tr("Benutzerdefiniert"))],
                   0 if (L.cols and L.rows) else (L.nup if L.nup > 1 else 2))
        self.spn_cols = QSpinBox()
        self.spn_cols.setRange(1, 16)
        self.spn_cols.setValue(L.cols or 2)
        self.spn_rows = QSpinBox()
        self.spn_rows.setRange(1, 16)
        self.spn_rows.setValue(L.rows or 2)
        row.addWidget(self.cmb_nup)
        row.addWidget(self.spn_cols)
        row.addWidget(QLabel("×"))
        row.addWidget(self.spn_rows)
        row.addStretch()
        ml.addRow(tr("Seiten pro Blatt:"), row)
        self.cmb_order = QComboBox()
        fill_combo(self.cmb_order, list(layout.ORDERS.items()), L.order)
        ml.addRow(tr("Seitenreihenfolge:"), self.cmb_order)
        row = QHBoxLayout()
        self.cmb_tile = QComboBox()
        fill_combo(self.cmb_tile, [("fit", tr("An Kachel anpassen")), ("actual", tr("Tatsächliche Größe")),
                                   ("custom", tr("Benutzerdefiniert"))], L.tile_mode)
        self.spn_tile = QDoubleSpinBox()
        self.spn_tile.setRange(1, 1000)
        self.spn_tile.setSuffix(" %")
        self.spn_tile.setValue(L.tile_percent)
        row.addWidget(self.cmb_tile)
        row.addWidget(self.spn_tile)
        ml.addRow(tr("Skalierung je Kachel:"), row)
        self.spn_gap = QDoubleSpinBox()
        self.spn_gap.setRange(0, 50)
        self.spn_gap.setSuffix(tr(" mm"))
        self.spn_gap.setValue(L.gap_mm)
        self.spn_gap.setToolTip(tr("Abstand zwischen den Kacheln. Wird von der „Nutzen-Anordnung“ im Abschnitt "
                                   "„Schnittmarken und Anschnitt“ übersteuert, sobald dort eine Anordnung "
                                   "gewählt ist (Kante an Kante / Überfüller an Überfüller / Mit Abstand)."))
        ml.addRow(tr("Abstand:"), self.spn_gap)
        self.chk_borders = QCheckBox(tr("Seitenrand drucken"))
        self.chk_borders.setChecked(L.borders)
        ml.addRow("", self.chk_borders)

        # -- Booklet
        bw = QWidget()
        self.stack.addWidget(bw)      # sofort verankern, dann füllen
        bl = QFormLayout(bw)
        self.cmb_bkind = QComboBox()
        fill_combo(self.cmb_bkind, [("saddle", tr("Standard (alle Bögen ineinander, einmal falzen)")),
                                    ("grouped", tr("Gruppierte Lagen (je Lage mehrere Bögen)")),
                                    ("stack", tr("Einzelbögen gestapelt (Klebebindung)"))], L.booklet_kind)
        self.cmb_bkind.setToolTip(tr("Standard/Sammelheftung: ein Heft, Bögen ineinandergesteckt und in der Mitte geheftet. "
                                     "Gruppierte Lagen: z. B. je 4 Bögen = 16 Seiten pro Lage, Lagen hintereinander "
                                     "(Fadenheftung, dicke Hefte). Einzelbögen: jeder Bogen einzeln gefalzt, "
                                     "gestapelt (Klebebindung, Blockheftung)."))
        bl.addRow(tr("Bindeart:"), self.cmb_bkind)
        self.spn_persig = QSpinBox()
        self.spn_persig.setRange(1, 32)
        self.spn_persig.setValue(L.booklet_per_sig)
        self.spn_persig.setSuffix(tr(" Bögen je Lage"))
        self.spn_persig.setToolTip(tr("Nur bei „Gruppierte Lagen“: Anzahl Bögen je Lage. Beim Standard (Sammelheftung) "
                                       "liegen alle Bögen sowieso ineinander – die Zahl ist dort ohne Bedeutung."))
        bl.addRow("", self.spn_persig)
        self.spn_persig.setVisible(L.booklet_kind == "grouped")
        # changing "sheets per signature" = grouped signatures (otherwise the number would have no effect with saddle stitching)
        self.spn_persig.valueChanged.connect(
            lambda _v: self.cmb_bkind.currentData() == "saddle"
            and self.cmb_bkind.setCurrentIndex(max(0, self.cmb_bkind.findData("grouped"))))
        self.cmb_bsides = QComboBox()
        fill_combo(self.cmb_bsides, [("both", tr("Beidseitig")), ("front", tr("Nur Vorderseiten")),
                                     ("back", tr("Nur Rückseiten"))], L.booklet_sides)
        bl.addRow(tr("Broschürenseiten:"), self.cmb_bsides)
        self.cmb_binding = QComboBox()
        fill_combo(self.cmb_binding, [("left", tr("Links (normal)")), ("right", tr("Rechts (z. B. Hebräisch/Arabisch)"))],
                   L.booklet_binding)
        bl.addRow(tr("Bindung:"), self.cmb_binding)
        self.ed_bsheets = QLineEdit(L.booklet_sheets)
        self.ed_bsheets.setPlaceholderText(tr("alle – oder z. B. 1-3"))
        bl.addRow(tr("Bögen:"), self.ed_bsheets)
        self.spn_gutter = QDoubleSpinBox()
        self.spn_gutter.setRange(0, 50)
        self.spn_gutter.setSuffix(tr(" mm"))
        self.spn_gutter.setValue(L.booklet_gutter_mm)
        bl.addRow(tr("Bundsteg:"), self.spn_gutter)
        self.spn_creep = QDoubleSpinBox()
        self.spn_creep.setRange(0, 2)
        self.spn_creep.setDecimals(2)
        self.spn_creep.setSingleStep(0.05)
        self.spn_creep.setSuffix(tr(" mm je Bogen"))
        self.spn_creep.setValue(L.booklet_creep_mm)
        self.spn_creep.setToolTip(tr("Bundzug: innere Bögen stehen nach dem Falzen vorne über. Ihr Inhalt wird je Bogen "
                                     "um diesen Wert zum Falz verschoben (ungefähr die Papierstärke, z. B. 0,1 mm "
                                     "bei 80 g/m², 0,15 mm bei 150 g/m²)."))
        bl.addRow(tr("Bundzug:"), self.spn_creep)
        self.cmb_blanks = QComboBox()
        fill_combo(self.cmb_blanks, [("end", tr("am Ende")), ("before_back", tr("vor der letzten Seite (Rückseite bleibt hinten)"))],
                   L.booklet_blanks)
        bl.addRow(tr("Leerseiten:"), self.cmb_blanks)
        self.ed_blank = QLineEdit(L.booklet_blank_text)
        self.ed_blank.setPlaceholderText(tr("Hinweistext auf Leerseiten (optional), z. B. „Diese Seite bleibt leer“"))
        bl.addRow("", self.ed_blank)
        mrow = QHBoxLayout()
        self.chk_bfold = QCheckBox(tr("Falzmarken"))
        self.chk_bfold.setChecked(L.booklet_fold_marks)
        self.chk_breg = QCheckBox(tr("Passermarken"))
        self.chk_breg.setChecked(L.booklet_reg_marks)
        self.chk_bcoll = QCheckBox(tr("Flattermarken"))
        self.chk_bcoll.setChecked(L.booklet_collation_marks)
        self.chk_bcoll.setToolTip(tr("Balken am Rücken jeder Lage, je Lage versetzt – beim Zusammentragen ergibt sich "
                                     "eine Treppe; eine fehlende oder vertauschte Lage fällt sofort auf."))
        for c in (self.chk_bfold, self.chk_breg, self.chk_bcoll):
            mrow.addWidget(c)
        mrow.addStretch()
        bl.addRow(tr("Marken:"), mrow)
        # Falzbogen-Optionen gelten nur für den alten Weg (Bogen aufs Blatt eingepasst) – ausgeblendet
        for _w in (self.spn_gutter, self.spn_creep):
            bl.setRowVisible(_w, False)
        bl.setRowVisible(mrow, False)
        # Druckbögen für Nutzen: Broschüre -> eigenes Dokument (je Bogenseite ein aufgeklappter Bogen),
        # das danach im Modus „Nutzen“ mit Anordnung/Überfüller/Schnittmarken/Schritt 2 montiert wird
        self.cmb_bspread = QComboBox()
        fill_combo(self.cmb_bspread, [("side", tr("nebeneinander (seitlich gebunden)")),
                                      ("top", tr("übereinander (oben gebunden)"))], L.booklet_spread)
        self.cmb_bspread.setToolTip(tr("Wie die zwei Seiten eines aufgeklappten Bogens aneinandergesetzt werden – "
                                       "nur für „Druckbögen erzeugen“."))
        bl.addRow(tr("Seiten aneinander:"), self.cmb_bspread)
        self.chk_bnutzen = QCheckBox(tr("Als Druckbögen montieren (Überfüller, Schnittmarken, Nutzen)"))
        self.chk_bnutzen.setChecked(bool(getattr(L, "booklet_nutzen", False)))
        self.chk_bnutzen.setToolTip(tr("Statt Falzbogen auf dem Druckerblatt: je Bogenseite ein aufgeklappter Bogen im "
                                       "Endformat (z. B. 420 × 210 mm), so oft wie möglich aufs Blatt – mit "
                                       "„Schnittmarken und Anschnitt“: Nutzen-Anordnung (Kante an Kante / Überfüller "
                                       "an Überfüller / Abstand), Überfüller, Schnittmarken. Vorschau und Druck zeigen "
                                       "genau das."))
        self.chk_bnutzen.setChecked(True)          # seit 1.12: Broschüre IMMER als Druckbögen – VOR dem
        self.chk_bnutzen.setVisible(False)         # Verbinden setzen (Dialog ist hier noch im Aufbau)
        self.chk_bnutzen.toggled.connect(self._changed)
        self.cmb_bspread.currentIndexChanged.connect(self._changed)
        bl.addRow("", self.chk_bnutzen)

        self.btn_bspreads = QPushButton(tr("Druckbögen erzeugen (für Nutzen) …"))
        self.btn_bspreads.setToolTip(tr("Erzeugt ein neues Dokument: je Bogenseite ein aufgeklappter Bogen im Endformat "
                                        "(z. B. 420 × 210 mm), Anschnitt nur außen, in Ausschieß-Reihenfolge. "
                                        "Dieses Dokument dann mit „Nutzen“ drucken – dort Anordnung (Kante an Kante / "
                                        "Überfüller an Überfüller / Abstand), Überfüller, Schnittmarken und Schritt 2."))
        self.btn_bspreads.clicked.connect(self._booklet_spreads_output)
        bl.addRow("", self.btn_bspreads)
        self.btn_overview = QPushButton(tr("Bogenübersicht …"))
        self.btn_overview.setToolTip(tr("Alle Bögen als Miniaturen – Verteilung der Seiten prüfen"))
        self.btn_overview.clicked.connect(self._sheet_overview)
        bl.addRow("", self.btn_overview)
        self.lbl_bhint = QLabel()
        self.lbl_bhint.setWordWrap(True)
        self.lbl_bhint.setStyleSheet(f"color: {theme.MUTED};")
        bl.addRow(self.lbl_bhint)

        # -- Poster
        ow = QWidget()
        self.stack.addWidget(ow)      # sofort verankern, dann füllen
        ol = QFormLayout(ow)
        self.cmb_pmode = QComboBox()
        fill_combo(self.cmb_pmode, [("scale", tr("Maßstab")), ("sheets", tr("Anzahl Blätter")),
                                    ("target", tr("Zielformat"))], L.poster_mode)
        ol.addRow(tr("Größe bestimmen über:"), self.cmb_pmode)
        self.spn_ppct = QDoubleSpinBox()
        self.spn_ppct.setRange(1, 5000)
        self.spn_ppct.setSuffix(" %")
        self.spn_ppct.setValue(L.poster_percent)
        ol.addRow(tr("Maßstab:"), self.spn_ppct)
        row = QHBoxLayout()
        self.spn_pcols = QSpinBox()
        self.spn_pcols.setRange(1, 20)
        self.spn_pcols.setValue(L.poster_cols)
        self.spn_prows = QSpinBox()
        self.spn_prows.setRange(1, 20)
        self.spn_prows.setValue(L.poster_rows)
        row.addWidget(self.spn_pcols)
        row.addWidget(QLabel(tr("breit ×")))
        row.addWidget(self.spn_prows)
        row.addWidget(QLabel(tr("hoch")))
        row.addStretch()
        ol.addRow(tr("Blätter:"), row)
        row = QHBoxLayout()
        self.cmb_ptarget = QComboBox()
        fill_combo(self.cmb_ptarget, [(k, tr("{0} ({1} × {2} mm)").format(k, w, h)) for k, (w, h) in layout.POSTER_FORMATS.items()]
                   + [("custom", tr("Benutzerdefiniert"))], L.poster_target)
        self.spn_ptw = QDoubleSpinBox()
        self.spn_ptw.setRange(10, 5000)
        self.spn_ptw.setSuffix(tr(" mm"))
        self.spn_ptw.setValue(L.poster_target_w_mm)
        self.spn_pth = QDoubleSpinBox()
        self.spn_pth.setRange(10, 5000)
        self.spn_pth.setSuffix(tr(" mm"))
        self.spn_pth.setValue(L.poster_target_h_mm)
        row.addWidget(self.cmb_ptarget)
        row.addWidget(self.spn_ptw)
        row.addWidget(QLabel("×"))
        row.addWidget(self.spn_pth)
        ol.addRow(tr("Zielformat:"), row)
        self.spn_overlap = QDoubleSpinBox()
        self.spn_overlap.setRange(0, 50)
        self.spn_overlap.setSuffix(tr(" mm"))
        self.spn_overlap.setValue(L.poster_overlap_mm)
        ol.addRow(tr("Überlappung:"), self.spn_overlap)
        self.chk_pmarks = QCheckBox(tr("Schnitt-/Klebelinien"))
        self.chk_pmarks.setChecked(L.poster_marks)
        self.chk_plabels = QCheckBox(tr("Beschriftung (Zeile/Spalte, Maßstab)"))
        self.chk_plabels.setChecked(L.poster_labels)
        self.chk_plarge = QCheckBox(tr("Nur große Seiten kacheln"))
        self.chk_plarge.setChecked(L.poster_large_only)
        for c in (self.chk_pmarks, self.chk_plabels, self.chk_plarge):
            ol.addRow("", c)

        # -- Nutzen (Step & Repeat) – vormals Reiter „Weitere Optionen“
        # Eigenes, frei bewegliches Fenster (verschieben, minimieren, schließen) – Kind des Druckdialogs:
        # lebt und wirkt nur mit ihm; Schließen versteckt es, die Einstellungen bleiben.
        self.sr_win = QWidget(self, Qt.WindowType.Window | Qt.WindowType.WindowMinimizeButtonHint
                              | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.WindowTitleHint)
        self.sr_win.setWindowTitle(tr("Step & Repeat – Passermark"))
        self.sr_win.resize(520, 640)
        _wl = QVBoxLayout(self.sr_win)
        self.chk_sr = QCheckBox(tr("Step && Repeat aktiv (Mehrfachnutzen)"))
        self.chk_sr.setStyleSheet(f"font-weight: bold; color: {theme.ACCENT};")
        self.chk_sr.setChecked(bool(L.step_repeat or getattr(L, "sr_multi", False)))
        self.chk_sr.setToolTip(tr("Einzelblätter: jede Seite mehrfach aufs Blatt. Broschüre: jeder Druckbogen "
                                  "mehrfach aufs Blatt. Aus: alles wird einmal gesetzt."))
        _wl.addWidget(self.chk_sr)
        self.btn_srwin.window_fn = lambda: getattr(self, "sr_win", None)
        self.btn_srwin.active_fn = self.chk_sr.isChecked
        self.btn_srwin.watch(self.sr_win)
        self.chk_sr.toggled.connect(lambda *_: self.btn_srwin.update())
        _sc = QScrollArea(self.sr_win)
        _sc.setWidgetResizable(True)
        _wl.addWidget(_sc, 1)
        g = QWidget()
        _sc.setWidget(g)
        f = QFormLayout(g)
        self.cmb_srmode = QComboBox()
        fill_combo(self.cmb_srmode, [("auto", tr("So viele wie aufs Blatt passen")), ("grid", tr("Raster vorgeben"))], L.sr_mode)
        f.addRow(tr("Anzahl:"), self.cmb_srmode)
        row = QHBoxLayout()
        self.spn_srcols = QSpinBox()
        self.spn_srcols.setRange(1, 50)
        self.spn_srcols.setValue(L.sr_cols)
        self.spn_srrows = QSpinBox()
        self.spn_srrows.setRange(1, 50)
        self.spn_srrows.setValue(L.sr_rows)
        row.addWidget(self.spn_srcols)
        row.addWidget(QLabel("×"))
        row.addWidget(self.spn_srrows)
        row.addStretch()
        f.addRow(tr("Spalten × Zeilen:"), row)
        row = QHBoxLayout()
        self.cmb_srby = QComboBox()
        fill_combo(self.cmb_srby, [("percent", tr("Maßstab in %")), ("short", tr("Kurze Kante auf …")),
                                   ("long", tr("Lange Kante auf …"))], L.sr_by)
        self.spn_srpct = QDoubleSpinBox()
        self.spn_srpct.setRange(1, 1000)
        self.spn_srpct.setDecimals(1)
        self.spn_srpct.setSuffix(" %")
        self.spn_srpct.setValue(L.sr_percent)
        self.spn_srmm = QDoubleSpinBox()
        self.spn_srmm.setRange(1, 5000)
        self.spn_srmm.setDecimals(1)
        self.spn_srmm.setSuffix(tr(" mm"))
        self.spn_srmm.setValue(L.sr_mm)
        row.addWidget(self.cmb_srby, 1)
        row.addWidget(self.spn_srpct)
        row.addWidget(self.spn_srmm)
        f.addRow(tr("Nutzengröße:"), row)
        self.lbl_srsize = QLabel()
        self.lbl_srsize.setWordWrap(True)
        self.lbl_srsize.setStyleSheet(f"color: {theme.ACCENT};")
        f.addRow("", self.lbl_srsize)
        self.cmb_srorient = QComboBox()
        fill_combo(self.cmb_srorient, [("auto", tr("Automatisch (passend / meiste Nutzen)")),
                                       ("portrait", tr("Hochformat")), ("landscape", tr("Querformat"))], L.sr_orientation)
        f.addRow(tr("Blatt:"), self.cmb_srorient)
        self.cmb_srrot = QComboBox()
        fill_combo(self.cmb_srrot, [("auto", tr("Automatisch (Nutzen bleiben aufrecht, das Blatt dreht mit)")),
                                   ("0", tr("Nicht drehen")), ("90", tr("Um 90° drehen"))],
                   L.sr_rotate)
        f.addRow(tr("Nutzen drehen:"), self.cmb_srrot)
        # „Anordnung“ + „Abstand“ stehen seit 1.12 beim Schnittmarken-/Anschnitt-Abschnitt
        # (sie wirken auch dort: Nutzen-Abstand = Überfüller-/Zuschnitt-Frage)
        self.chk_srseq = QCheckBox(tr("Je Nutzen die nächste Seite (variable Daten, Nummerierung)"))
        self.chk_srseq.setChecked(L.sr_sequence)
        self.chk_srseq.setToolTip(tr("Statt eine Seite zu vervielfachen, kommt auf jeden Nutzen die nächste Seite – "
                                     "z. B. nach „Variable Daten“ jede Karte mit eigenem Namen oder Code."))
        f.addRow(self.chk_srseq)
        self.cmb_srstack = QComboBox()
        fill_combo(self.cmb_srstack, [("row", tr("Bogen für Bogen")),
                                      ("stack", tr("Schneiden und Stapeln (Stapel fortlaufend)"))], L.sr_stack)
        self.cmb_srstack.setToolTip(tr("Schneiden und Stapeln: Bögen übereinanderlegen, schneiden – jeder Stapel ist "
                                       "fortlaufend nummeriert (1, 2, 3 … im ersten Stapel, dann der zweite)."))
        f.addRow(tr("Reihenfolge:"), self.cmb_srstack)
        self.chk_sr2 = QCheckBox(tr("Schritt 2 (optional): den montierten Bogen erneut auf ein Zielformat setzen"))
        self.chk_sr2.setChecked(L.sr_pass2)
        self.chk_sr2.setToolTip(tr("Erst wird wie oben eingestellt auf das gewählte Papier montiert (Schritt 1), "
                                   "dann wird dieses Ergebnis nochmals aufs hier gewählte Zielformat gesetzt – "
                                   "aneinandergereiht und mittig, inhaltlich unverändert. Schritt 2 fügt nie "
                                   "Überfüller oder Schnittmarken hinzu: was der montierte Bogen schon hat, "
                                   "bleibt erhalten – Schnittmarken und Überfüller aus Schritt 1 also mit "
                                   "dabei. Der fertige Schritt-1-Bogen wird dabei so oft wie möglich (oder im "
                                   "eingestellten Raster) aufs Zielformat gesetzt, immer mittig. Passt er (auch "
                                   "gedreht) nicht, wird trotzdem montiert und gewarnt – beschnitten wird am Rand. "
                                   "Die Vorschau zeigt das Ergebnis wie bei Schritt 1. Der Button gibt es als "
                                   "neues Dokument aus (neuer Reiter) und schließt diesen Dialog."))
        # Schritt 2 als eigener Block: liegt im Nutzen-Panel – bei „Broschüre als Druckbögen“
        # wandert er ins Broschüren-Panel (_place_sr2), Werte und Logik bleiben dieselben
        self.sr2_box = QWidget(self)
        f2 = QFormLayout(self.sr2_box)
        f2.setContentsMargins(0, 0, 0, 0)
        self._sr2_home = QVBoxLayout()
        self._sr2_home.setContentsMargins(0, 0, 0, 0)
        f.addRow(self._sr2_home)
        self._sr2_home.addWidget(self.sr2_box)
        f2.addRow(self.chk_sr2)
        self.cmb_sr2fmt = QComboBox()
        f2.addRow(tr("Zielformat (Schritt 2):"), self.cmb_sr2fmt)
        row = QHBoxLayout()
        self.spn_sr2w = QDoubleSpinBox()
        self.spn_sr2w.setRange(10, 5000)
        self.spn_sr2w.setDecimals(1)
        self.spn_sr2w.setSuffix(tr(" mm"))
        self.spn_sr2w.setValue(L.sr2_w_mm)
        self.spn_sr2h = QDoubleSpinBox()
        self.spn_sr2h.setRange(10, 5000)
        self.spn_sr2h.setDecimals(1)
        self.spn_sr2h.setSuffix(tr(" mm"))
        self.spn_sr2h.setValue(L.sr2_h_mm)
        row.addWidget(self.spn_sr2w)
        row.addWidget(QLabel("×"))
        row.addWidget(self.spn_sr2h)
        row.addStretch()
        f2.addRow(tr("Eigene Maße:"), row)
        row = QHBoxLayout()
        self.spn_sr2cols = QSpinBox()
        self.spn_sr2cols.setRange(0, 10)
        self.spn_sr2cols.setSpecialValueText(tr("Automatisch"))
        self.spn_sr2cols.setValue(L.sr2_cols)
        self.spn_sr2rows = QSpinBox()
        self.spn_sr2rows.setRange(0, 10)
        self.spn_sr2rows.setSpecialValueText(tr("Automatisch"))
        self.spn_sr2rows.setValue(L.sr2_rows)
        row.addWidget(self.spn_sr2cols)
        row.addWidget(QLabel("×"))
        row.addWidget(self.spn_sr2rows)
        row.addStretch()
        f2.addRow(tr("Wie oft (0 × 0 = automatisch):"), row)
        self.btn_sr2 = QPushButton(tr("Als neues Dokument ausgeben (Schritt 1 + 2)"))
        self.btn_sr2.clicked.connect(self._sr2_output)
        f2.addRow("", self.btn_sr2)
        note = QLabel(tr("Wirkt auf den im Druckdialog gewählten Modus: Einzelblätter – jede Seite mehrfach, "
                      "Broschüre – jeder Druckbogen mehrfach. Anordnung, Abstand, Überfüller und Schnittmarken "
                      "stehen im Druckdialog unter „Schnittmarken und Anschnitt“. Bei „Automatisch“ wird zuerst "
                      "eine Lage gesucht, in der das Raster aufs Blatt passt, dann die mit den meisten Nutzen."))
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {theme.MUTED};")
        f.addRow(note)

        # die Modus-Gruppe ist bereits in v verankert (direkt nach Erstellung)

        # Wie kommt die Seite aufs Blatt? – passt zu jedem Druckmodus
        sec = self._section(tr("Wie aufs Blatt?"))
        wf = sec.form
        # Skalierungswahl (Anpassen/Tatsächlich/…) wirkt in JEDEM Modus:
        # fit = Modus-Standard, actual/shrink/custom überschreiben die
        # Modus-Skalierung (layout.global_scale).
        self.scale_box = QWidget()
        sec.body_layout.insertWidget(0, self.scale_box)
        sf = QFormLayout(self.scale_box)
        self.rb_fit = QRadioButton(tr("Anpassen"))
        self.rb_actual = QRadioButton(tr("Tatsächliche Größe"))
        self.rb_shrink = QRadioButton(tr("Übergroße Seiten verkleinern"))
        self.rb_custom = QRadioButton(tr("Benutzerdefiniert:"))
        self.cmb_custom_by = QComboBox()
        fill_combo(self.cmb_custom_by, [("percent", tr("Maßstab in %")), ("short", tr("Kurze Kante auf …")),
                                        ("long", tr("Lange Kante auf …"))], L.custom_by)
        self.spn_custom = QDoubleSpinBox()
        self.spn_custom.setRange(1, 1000)
        self.spn_custom.setDecimals(1)
        self.spn_custom.setSuffix(" %")
        self.spn_custom.setValue(L.custom_percent)
        self.spn_custom_mm = QDoubleSpinBox()
        self.spn_custom_mm.setRange(1, 5000)
        self.spn_custom_mm.setDecimals(1)
        self.spn_custom_mm.setSuffix(tr(" mm"))
        self.spn_custom_mm.setValue(L.custom_mm)
        self.lbl_custom = QLabel()
        self.lbl_custom.setWordWrap(True)
        self.lbl_custom.setStyleSheet(f"color: {theme.ACCENT};")
        self.mode_group = QButtonGroup(self)
        for rb, m in [(self.rb_fit, "fit"), (self.rb_actual, "actual"),
                      (self.rb_shrink, "shrink"), (self.rb_custom, "custom")]:
            self.mode_group.addButton(rb)
            rb.setProperty("mode", m)
            rb.setChecked(L.mode == m)
            sf.addRow(rb)
        crow = QHBoxLayout()
        crow.addWidget(self.cmb_custom_by, 1)
        crow.addWidget(self.spn_custom)
        crow.addWidget(self.spn_custom_mm)
        sf.addRow("", crow)
        sf.addRow("", self.lbl_custom)
        self.cmb_orient = QComboBox()
        fill_combo(self.cmb_orient, [("auto", tr("Automatisch Hoch-/Querformat")), ("portrait", tr("Hochformat")),
                                     ("landscape", tr("Querformat"))], L.orientation)
        wf.addRow(tr("Ausrichtung:"), self.cmb_orient)
        self.chk_autorot = QCheckBox(tr("Seiten automatisch drehen"))
        self.chk_autorot.setChecked(L.autorotate)
        self.chk_center = QCheckBox(tr("Auf Blatt zentrieren"))
        self.chk_center.setChecked(L.center)
        self.chk_margins = QCheckBox(tr("Nicht bedruckbaren Rand des Druckers berücksichtigen"))
        self.chk_margins.setChecked(L.use_margins)
        for c in (self.chk_autorot, self.chk_center, self.chk_margins):
            wf.addRow("", c)

        hb = self.handling_btns.get(L.handling, self.handling_btns["size"])
        hb.setChecked(True)
        self.stack.setCurrentIndex(hb.property("page"))

        sec = self._section(tr("Schnittmarken und Anschnitt"))
        f = sec.form
        self.chk_marks = QCheckBox(tr("Schnittmarken drucken"))
        self.chk_marks.setChecked(L.crop_marks)
        f.addRow(self.chk_marks)
        self.spn_bleed = QDoubleSpinBox()
        self.spn_bleed.setRange(0, 20)
        self.spn_bleed.setDecimals(1)
        self.spn_bleed.setSingleStep(0.5)
        self.spn_bleed.setSuffix(tr(" mm"))
        self.spn_bleed.setValue(L.bleed_mm)
        f.addRow(tr("Überfüller / Anschnitt (gespiegelt):"), self.spn_bleed)
        # Nutzen-Anordnung (hat seit 1.12 hier ihren Platz – bei den Schnitt-/Zuschnitt-Fragen)
        self.cmb_srjoin = QComboBox()
        fill_combo(self.cmb_srjoin, [("edge", tr("Kante an Kante (ein Schnitt, Anschnitt nur außen)")),
                                     ("bleed", tr("Überfüller an Überfüller")),
                                     ("gap", tr("Mit Abstand"))], L.sr_join)
        self.cmb_srjoin.setToolTip(tr("Wie die Kacheln auf dem Blatt liegen – gilt für „Nutzen (Step & Repeat)“ "
                                     "UND für „Mehrere pro Blatt“; überschreibt dort den Abstand des "
                                     "Mehrere-Abschnitts. "
                                     "Kante an Kante: 0 mm Abstand, der Anschnitt liegt nur außen – "
                                     "ein Schnitt teilt zwei Kacheln. Überfüller an Überfüller: "
                                     "2 × Anschnitt als Abstand, wird in der Mitte geschnitten. "
                                     "Mit Abstand: der Abstand unten in diesem Abschnitt "
                                     "(z. B. Mindestabstand für einen Multifinisher), nie unter 2 × Anschnitt."))
        f.addRow(tr("Nutzen-Anordnung:"), self.cmb_srjoin)
        self.spn_srgap = QDoubleSpinBox()
        self.spn_srgap.setRange(0, 50)
        self.spn_srgap.setSuffix(tr(" mm"))
        self.spn_srgap.setValue(L.sr_gap_mm)
        self.spn_srgap.setToolTip(tr("Abstand zwischen den Kacheln bei „Mit Abstand“ – gilt für Nutzen "
                                      "UND für „Mehrere pro Blatt“ (überschreibt dort den Abstand des "
                                      "Mehrere-Abschnitts; z. B. Mindestabstand für einen Multifinisher). "
                                      "Nie kleiner als 2 × Anschnitt, damit der Überfüller Platz hat."))
        f.addRow(tr("Abstand zwischen Nutzen:"), self.spn_srgap)
        note = QLabel(tr("Erzeugt den Anschnitt durch Spiegeln der Seitenränder nach außen – für Dateien ohne "
                      "Beschnittzugabe. Beim Anpassen wird automatisch Platz für Anschnitt und Marken gelassen; "
                      "Nutzen bekommen mindestens den doppelten Anschnitt als Abstand."))
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {theme.MUTED};")
        f.addRow(note)

        # paper (filled per printer)
        self.paper_group = self._section(tr("Papier und Ausgabe"))
        self.paper_form = self.paper_group.form

        # Endverarbeitung (Finisher) – Vorlagen + erkannte Felder; unter Windows Herstellerdialog
        self.finish_group = self._section(tr("Endverarbeitung (Finisher)"))
        self.finish_form = self.finish_group.form

        # Farbe
        sec = self._section(tr("Farbmanagement"))
        f = sec.form
        self.cmb_profile = QComboBox()
        self.cmb_intent = QComboBox()
        self.lbl_profile_note = QLabel()
        self.lbl_profile_note.setWordWrap(True)
        self.lbl_profile_note.setStyleSheet(f"color: {theme.MUTED};")
        f.addRow(tr("Ausgabeprofil:"), self.cmb_profile)
        f.addRow(tr("Render-Intent:"), self.cmb_intent)
        f.addRow("", self.lbl_profile_note)

        # Seltenes gut sichtbar, aber eingeklappt:
        sec = CollapsibleSection(tr("Spiegeln (z. B. Transferpapier, Folienrückseite)"))
        self.chk_mirror_h = QCheckBox(tr("Horizontal spiegeln (z. B. Transferpapier, Bügelfolie, Folienrückseite)"))
        self.chk_mirror_h.setChecked(L.mirror_h)
        self.chk_mirror_v = QCheckBox(tr("Vertikal spiegeln"))
        self.chk_mirror_v.setChecked(L.mirror_v)
        for c in (self.chk_mirror_h, self.chk_mirror_v):
            c.toggled.connect(self._changed)
            sec.body_layout.addWidget(c)
        v.addWidget(sec)

        sec = CollapsibleSection(tr("Treiber (alle Optionen)"))
        self.driver_box = QWidget()
        sec.body_layout.addWidget(self.driver_box)
        v.addWidget(sec)
        v.addStretch()

        # Signale
        bg.buttonClicked.connect(self._handling_changed)
        for w in (self.rb_all, self.rb_cur, self.rb_range, self.chk_reverse, self.chk_borders,
                  self.chk_autorot, self.chk_center, self.chk_margins):
            w.toggled.connect(self._changed)
        self.mode_group.buttonClicked.connect(self._changed)
        self.ed_range.editingFinished.connect(self._changed)
        self.ed_bsheets.editingFinished.connect(self._changed)
        self.ed_blank.editingFinished.connect(self._changed)
        for w in (self.chk_bfold, self.chk_breg, self.chk_bcoll):
            w.toggled.connect(self._changed)
        self.cmb_custom_by.currentIndexChanged.connect(self._changed)
        for w in (self.spn_custom, self.spn_custom_mm, self.spn_cols, self.spn_rows, self.spn_tile, self.spn_gap,
                  self.spn_gutter, self.spn_creep, self.spn_persig, self.spn_ppct, self.spn_pcols, self.spn_prows, self.spn_ptw,
                  self.spn_pth, self.spn_overlap):
            w.valueChanged.connect(self._changed)
        for w in (self.cmb_subset, self.cmb_nup, self.cmb_order, self.cmb_tile, self.cmb_orient,
                  self.cmb_bsides, self.cmb_binding, self.cmb_bkind, self.cmb_blanks, self.cmb_pmode, self.cmb_ptarget):
            w.currentIndexChanged.connect(self._changed)
        for w in (self.chk_pmarks, self.chk_plabels, self.chk_plarge):
            w.toggled.connect(self._changed)
        # Signale des ehemaligen Reiters „Weitere Optionen“ (Nutzen, Marken, Spiegeln)
        for w in (self.chk_sr, self.chk_sr2, self.chk_marks, self.chk_srseq):
            w.toggled.connect(self._changed)
        for w in (self.cmb_srmode, self.cmb_srorient, self.cmb_srrot, self.cmb_srjoin, self.cmb_srstack):
            w.currentIndexChanged.connect(self._changed)
        self.cmb_srby.currentIndexChanged.connect(self._changed)
        self.cmb_sr2fmt.currentIndexChanged.connect(self._sr2_format_changed)
        self.cmb_sr2fmt.currentIndexChanged.connect(self._changed)
        for w in (self.spn_srcols, self.spn_srrows, self.spn_srpct, self.spn_srmm, self.spn_srgap, self.spn_bleed,
                  self.spn_sr2w, self.spn_sr2h, self.spn_sr2cols, self.spn_sr2rows):
            w.valueChanged.connect(self._changed)
        self.cmb_profile.currentIndexChanged.connect(self._profile_changed)
        self.cmb_intent.currentIndexChanged.connect(self._profile_changed)
        self._sync_enabled()

    def _fill_sr2_formats(self):
        """Zielformat-Liste für Schritt 2: die Formate des gewählten Geräts + eigene Maße."""
        if not hasattr(self, "cmb_sr2fmt"):
            return
        cur = self.cmb_sr2fmt.currentData() or getattr(self.s.layout, "sr2_format", "") or "custom"
        self.cmb_sr2fmt.blockSignals(True)
        self.cmb_sr2fmt.clear()
        items = []
        if self.caps:
            key = self.caps.roles.get("pagesize")
            if key and key in self.caps.options:
                items = [(c.value, c.text) for c in self.caps.options[key].choices]
        items.append(("custom", tr("Eigene Maße (mm)")))
        for v, t in items:
            self.cmb_sr2fmt.addItem(t, v)
        idx = next((i for i in range(self.cmb_sr2fmt.count()) if self.cmb_sr2fmt.itemData(i) == cur), -1)
        self.cmb_sr2fmt.setCurrentIndex(idx if idx >= 0 else self.cmb_sr2fmt.count() - 1)
        self.cmb_sr2fmt.blockSignals(False)
        self._sr2_format_changed()

    def _sr2_format_changed(self, *_):
        """Zielformat gewählt: die mm-Felder aus dem Gerät übernehmen (bei „Eigene Maße“ frei)."""
        if not hasattr(self, "spn_sr2w"):
            return
        v = self.cmb_sr2fmt.currentData()
        if v and v != "custom" and self.caps:
            key = self.caps.roles.get("pagesize")
            if key:
                try:
                    w, h, _ia = self.caps.sheet_for({key: v})
                    self.spn_sr2w.setValue(w / layout.MM)
                    self.spn_sr2h.setValue(h / layout.MM)
                except Exception:
                    pass
        self._sync_enabled()

    def _sr2_output(self):
        """Schritt 1 + Schritt 2 im Speicher montieren und als neues Dokument öffnen."""
        if not self.caps:
            return
        try:
            pages = self._pages()
        except ValueError as e:
            QMessageBox.warning(self, tr("Seitenbereich"), str(e))
            return
        s = self._eff_settings()
        if not layout.is_step2(s):
            QMessageBox.warning(self, tr("Schritt 2"),
                                tr("Bitte „Jede Seite mehrfach …“ und „Schritt 2“ aktivieren "
                                   "und ein Zielformat wählen."))
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            if getattr(self, "trims", None) is None:
                self.trims, self.doc_bleeds = layout.page_trims(self.doc), layout.page_doc_bleeds(self.doc)
            sheet = self._sheet()
            self._make_plans(pages)          # derselbe Weg wie die Vorschau (auch Broschüre als Druckbögen)
            plans1 = self.plans1
            if not plans1:
                raise RuntimeError(tr("Nichts zu montieren (Seiten-/Bogenbereich leer?)"))
            plans2 = self.plans2
            out = layout.impose_step2(self._print_doc(), sheet, plans1, s, plans2=plans2)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, tr("Schritt 2"), str(e))
            return
        QApplication.restoreOverrideCursor()
        opener = getattr(self.parent(), "_open_result", None)
        if opener is None:
            out.close()
            QMessageBox.critical(self, tr("Schritt 2"),
                                tr("Kein Fenster zum Öffnen des Ergebnisses gefunden."))
            return
        notes = [w for p in plans1 for w in p.warnings] + [w for p in plans2 for w in p.warnings]
        opener(out, "_nutzen2", notes)
        self.accept()          # wie beim Drucken: Dialog schließen, Ergebnis liegt im neuen Reiter

    def _booklet_spreads_output(self):
        """Broschüre als Druckbögen-Dokument öffnen (Schritt 1); montiert wird danach mit „Nutzen“."""
        try:
            pages = self._pages()
        except ValueError as e:
            QMessageBox.warning(self, tr("Seitenbereich"), str(e))
            return
        s = self._settings()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            if getattr(self, "trims", None) is None:
                self.trims, self.doc_bleeds = layout.page_trims(self.doc), layout.page_doc_bleeds(self.doc)
            out, notes = layout.booklet_spreads(self._base_print_doc(), pages, s, self.trims)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, tr("Druckbögen"), str(e))
            return
        QApplication.restoreOverrideCursor()
        opener = getattr(self.parent(), "_open_result", None)
        if opener is None:
            out.close()
            QMessageBox.critical(self, tr("Druckbögen"), tr("Kein Fenster zum Öffnen des Ergebnisses gefunden."))
            return
        opener(out, "_druckboegen", notes)
        self.accept()          # wie Schritt 2: Dialog schließen, Druckbögen liegen im neuen Reiter

    def _show_admin_info(self, name):
        if name == printers.PDF_TARGET:
            self.lbl_admin.setText(tr("PDF-Ausgabe – alle Layout-Funktionen (N-Up, Broschüre, Poster, Nutzen, "
                                   "Marken, Anschnitt) wirken, Farben bleiben unverändert."))
            return
        pc = self.cfg.get("printers", {}).get(name, {})
        opts = pc.get("options", {})
        parts = []
        for k, v in opts.items():
            o = self.caps.options.get(k) if self.caps else None
            if o:
                parts.append(f"{o.text} = {next((c.text for c in o.choices if c.value == v), v)}")
        dp = self.cfg.get("default_printer", "")
        txt = (tr("Admin: ") + "; ".join(parts)) if parts else tr("Keine eigenen Admin-Werte – es gelten die Standards der CUPS-Queue.")
        if dp and dp != name:
            txt += tr("\n⚠ Admin-Standarddrucker ist „{0}“, gewählt ist „{1}“.").format(dp, name)
        self.lbl_admin.setText(txt)

    def _reset_to_admin(self):
        if not self.caps:
            return
        name = self.caps.name
        self.s.values.pop(name, None)
        self.s.color.pop(name, None)
        self.values = self.s.values_for(name)
        self._build_paper()
        self._build_driver_tab()
        self._build_profiles()
        self._fill_sr2_formats()
        fit_width(self)
        self._changed()

    def _handling(self) -> str:
        return next((k for k, b in self.handling_btns.items() if b.isChecked()), "size")

    def _toggle_sr_window(self):
        """Reiter: offen -> schließen (Einstellungen bleiben), sonst öffnen."""
        if self.sr_win.isVisible() and not self.sr_win.isMinimized():
            self.sr_win.hide()
        else:
            self._open_sr_window()

    def _open_sr_window(self):
        """Step-&-Repeat-Fenster zeigen (auch wenn es minimiert war) und nach vorne holen.
                Beim ersten Mal links neben den Druckdialog (dorthin zeigt der Pfeil), sonst wo es zuletzt war."""
        if not getattr(self, "_sr_placed", False) and not self.sr_win.isVisible():
            self._sr_placed = True
            try:
                g = self.frameGeometry()
                scr = (self.screen() or QApplication.primaryScreen()).availableGeometry()
                w, h = self.sr_win.width(), min(self.sr_win.height(), scr.height())
                x = g.left() - w - 6
                if x < scr.left():
                    x = scr.left()
                y = max(scr.top(), min(g.top(), scr.bottom() - h))
                self.sr_win.move(x, y)
            except Exception:                    # noqa: BLE001 – Platzierung ist nur Komfort
                pass
        self.sr_win.showNormal()
        self.sr_win.raise_()
        self.sr_win.activateWindow()

    def _handling_changed(self, *_):
        h = self._handling()
        self.stack.setCurrentIndex(self.handling_btns[h].property("page"))
        self._update_mode_hint()
        self._changed()

    def _update_mode_hint(self):
        h = self._handling()
        self.lbl_modehint.setText({
            "size": tr("Jede Seite einzeln aufs Blatt – Normaldruck. Skalierung und Ausrichtung unten bei „Wie aufs Blatt?“."),
            "multiple": tr("Mehrere verschiedene Seiten auf ein Blatt setzen (z. B. 2 × A5 auf A4)."),
            "booklet": tr("Seiten als Falzbögen für Broschüren montieren (Falzen und Heften)."),
            "poster": tr("Seite vergrößert über mehrere Blätter verteilen und zusammenfügen."),
        }.get(h, ""))

    def _sync_enabled(self):
        # Globale Skalierung („Wie aufs Blatt?“) wirkt in JEDEM Druckmodus:
        # fit = Modus-Standard, actual = Originalgröße, shrink = höchstens 100 %,
        # custom = Maßstab/Eigene Maße. Deshalb immer sichtbar und wählbar.
        cust = self.rb_custom.isChecked()
        by = self.cmb_custom_by.currentData()
        self.cmb_custom_by.setEnabled(cust)
        self.spn_custom.setVisible(by == "percent")
        self.spn_custom_mm.setVisible(by != "percent")
        self.spn_custom.setEnabled(cust)
        self.spn_custom_mm.setEnabled(cust)
        self.lbl_custom.setVisible(cust)
        custom_grid = self.cmb_nup.currentData() == 0
        self.spn_cols.setEnabled(custom_grid)
        self.spn_rows.setEnabled(custom_grid)
        self.spn_tile.setEnabled(self.cmb_tile.currentData() == "custom")
        pm = self.cmb_pmode.currentData()
        self.spn_ppct.setEnabled(pm == "scale")
        self.spn_pcols.setEnabled(pm == "sheets")
        self.spn_prows.setEnabled(pm == "sheets")
        self.cmb_ptarget.setEnabled(pm == "target")
        custom_t = pm == "target" and self.cmb_ptarget.currentData() == "custom"
        self.spn_ptw.setEnabled(custom_t)
        self.spn_pth.setEnabled(custom_t)
        if hasattr(self, "chk_sr"):
            sr = self.chk_sr.isChecked()
            grid = self.cmb_srmode.currentData() == "grid"
            nup = self._handling() == "multiple"          # Nutzen-Anordnung gilt auch bei „Mehrere pro Blatt“
            # … und bei Broschüre als Druckbögen (die Bögen werden mit der Nutzen-Logik montiert)
            nup = nup or (self._handling() == "booklet" and self.chk_bnutzen.isChecked())
            for w in (self.cmb_srmode, self.cmb_srby, self.spn_srpct, self.spn_srmm, self.cmb_srorient,
                      self.cmb_srrot):
                w.setEnabled(sr)
            self.cmb_srjoin.setEnabled(True)              # Anordnung: in jedem Modus einstellbar (wirkt, sobald Nutzen entstehen)
            by = self.cmb_srby.currentData()
            self.spn_srpct.setVisible(by == "percent")
            self.spn_srmm.setVisible(by != "percent")
            self.lbl_srsize.setVisible(sr)
            join = self.cmb_srjoin.currentData()
            self.spn_srgap.setEnabled(join == "gap")      # Abstand: immer einstellbar, sobald „Mit Abstand“ gewählt
            self.chk_srseq.setEnabled(sr)
            self.cmb_srstack.setEnabled(sr and self.chk_srseq.isChecked())
            # bei „Mehrere pro Blatt“ übersteuert die Nutzen-Anordnung den alten
            # Abstand (edge immer; bleed ab 1 mm Anschnitt; gap immer) – Feld dann
            # ausgrauen, damit klar ist, wo der wirksame Wert herkommt
            overridden = nup and (join != "bleed" or self.spn_bleed.value() > 0)
            self.spn_gap.setEnabled(not overridden)
            self.spn_srcols.setEnabled(sr and grid)
            self.spn_srrows.setEnabled(sr and grid)
            sr2 = sr and self.chk_sr2.isChecked()
            self.chk_sr2.setEnabled(sr)
            self.cmb_sr2fmt.setEnabled(sr2)
            custom2 = self.cmb_sr2fmt.currentData() == "custom"
            self.spn_sr2w.setEnabled(sr2 and custom2)
            self.spn_sr2h.setEnabled(sr2 and custom2)
            self.spn_sr2cols.setEnabled(sr2)
            self.spn_sr2rows.setEnabled(sr2)
            self.btn_sr2.setEnabled(sr2 and self.spn_sr2w.value() > 0 and self.spn_sr2h.value() > 0)
        booklet = self._handling() == "booklet"
        self.spn_persig.setVisible(self.cmb_bkind.currentData() == "grouped")
        self.spn_persig.setEnabled(self.cmb_bkind.currentData() == "grouped")
        self.spn_creep.setEnabled(booklet and self.cmb_bkind.currentData() != "stack")
        self.chk_bcoll.setEnabled(booklet and self.cmb_bkind.currentData() != "saddle")
        self.chk_reverse.setText(tr("Bögen in umgekehrter Reihenfolge") if booklet
                                 else tr("Seiten in umgekehrter Reihenfolge"))
        if booklet and self.caps is not None:
            # Druckbögen: gewendet wird an der Kante parallel zum Falz (hängt von Blattlage und
            # „Seiten aneinander“ ab – steht nach der Planung im ersten Bogen)
            plans = getattr(self, "plans", None) or []
            short = bool(plans and plans[0].landscape == (self.cmb_bspread.currentData() != "top"))
            edge = tr("kurzen Kante") if short else tr("langen Kante")
            if self.cmb_bsides.currentData() != "both":
                self.lbl_bhint.setText(tr("Manuell beidseitig: zuerst „Nur Vorderseiten“ drucken, Stapel an der "
                                          "{0} wenden und wieder einlegen, dann „Nur Rückseiten“.").format(edge))
            elif short and self._short_edge_choice():
                self.lbl_bhint.setText(tr("Duplex wird für den Druck automatisch auf „kurze Kante“ gestellt."))
            elif short:
                self.lbl_bhint.setText(tr("⚠ Wenden an der kurzen Kante nötig, am Drucker aber nicht erkannt – "
                                          "„Nur Vorderseiten“/„Nur Rückseiten“ verwenden."))
            else:
                self.lbl_bhint.setText(tr("Beidseitig an der langen Kante wenden (Standard-Duplex)."))

    # ================================================================== #
    # Drucker
    # ================================================================== #
    def _load_printers(self):
        try:
            plist = printers.list_printers()
        except Exception as e:
            QMessageBox.critical(self, tr("CUPS"), tr("Drucker können nicht abgefragt werden:\n{0}").format(e))
            plist = []
        plist = list(plist) + [printers.pdf_target_info()]      # always available: Save as PDF
        self.cmb_printer.blockSignals(True)
        for p in plist:
            label = (f"{p.info}  ({p.name})" if p.info != p.name else p.name)
            if p.model:
                label += f"  –  {p.model}"
            self.cmb_printer.addItem(label, p)
        want = self.s.printer or next((p.name for p in plist if p.is_default), None)
        idx = next((i for i, p in enumerate(plist) if p.name == want), 0)
        self.cmb_printer.setCurrentIndex(idx)
        self.cmb_printer.blockSignals(False)
        if plist:
            self._printer_changed(idx)
        else:
            self.btn_print.setEnabled(False)

    def _printer_changed(self, _idx):
        p: printers.PrinterInfo = self.cmb_printer.currentData()
        if p is None:
            return
        if p.name == printers.PDF_TARGET:
            self.lbl_pstate.setText(tr("Speichert das Ergebnis als PDF-Datei – vektoriell, Farben und Farbräume "
                                    "unverändert, kein Farbprofil, keine Druckerränder."))
        else:
            self.lbl_pstate.setText(f"{tr(p.state_text)} – {p.model}" + (f"\n{p.state_message}" if p.state_message else ""))
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.caps = self.s.caps_for(p.name)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, tr("Drucker"), tr("Treiberoptionen nicht lesbar:\n{0}").format(e))
            self.caps = None
            self.btn_print.setEnabled(False)
            return
        QApplication.restoreOverrideCursor()
        self.btn_print.setEnabled(True)
        self.btn_print.setText(tr("Speichern …") if p.name == printers.PDF_TARGET else tr("Drucken"))
        self._pw_form.setRowVisible(self.pw_box, p.name == printers.PDF_TARGET)
        self.spn_copies.setEnabled(p.name != printers.PDF_TARGET)
        self.chk_collate.setEnabled(p.name != printers.PDF_TARGET)
        if hasattr(self, "btn_reset"):
            self.btn_reset.setEnabled(p.name != printers.PDF_TARGET)
        self.s.printer = p.name
        self._show_admin_info(p.name)
        self.values = self.s.values_for(p.name)
        self._build_paper()
        self._build_driver_tab()
        self._build_profiles()
        self._fill_sr2_formats()
        fit_width(self)
        self._changed()

    def _option_combo(self, key):
        opt = self.caps.options[key]
        cb = QComboBox()
        fill_combo(cb, [(c.value, c.text) for c in opt.choices], self.values.get(key, opt.default))
        cb.setProperty("key", key)
        cb.currentIndexChanged.connect(lambda _i, cb=cb: self._option_changed(cb))
        return cb

    def _build_paper(self):
        while self.paper_form.rowCount():
            self.paper_form.removeRow(0)
        self.role_combos = {}
        for role, label in ROLE_LABELS:
            key = self.caps.roles.get(role)
            if key and key in self.caps.options:
                cb = self._option_combo(key)
                self.role_combos[key] = cb
                drv = self.caps.options[key].text
                label = tr(label)
                text = label if drv.lower() in (label.lower(), key.lower()) else f"{label}\n({drv})"
                if role == "pagesize":
                    if self.caps.backend == "pdf":          # NEU: Layout nur fürs PDF-Ziel
                        row = QHBoxLayout()
                        row.addWidget(cb, 1)
                        b = QPushButton(tr("Sonderformate …"))
                        b.setToolTip(tr("Eigene Papierformate anlegen – bleiben gespeichert und stehen "
                        "bei „Als PDF speichern“ zur Wahl (mit ★)"))
                        b.clicked.connect(self._custom_sizes)
                        row.addWidget(b)
                        self.paper_form.addRow(text + ":", row)
                    else:                                    # Gerät: schlicht ohne Button
                        self.paper_form.addRow(text + ":", cb)
                    continue
                self.paper_form.addRow(text + ":", cb)
        if not self.role_combos:
            self.paper_form.addRow(QLabel(tr("Keine Basisoptionen erkannt – siehe unten „Treiber (alle Optionen)“.")))
        self._build_tray_auto()
        self._build_finishing()

    def _custom_sizes(self):
        from .customsizes import CustomSizesDialog
        dlg = CustomSizesDialog(self)
        if not dlg.exec():
            return
        self.s.refresh_custom_sizes()
        key = self.caps.roles.get("pagesize") if self.caps else None
        if key and dlg.chosen and self.caps.backend == "pdf":   # NEU: nur PDF-Ziel
            self.values[key] = dlg.chosen
        self._build_paper()
        self._changed()

    # ---------------- automatische Fachwahl ---------------- #
    def _pc(self):
        return self.cfg.get("printers", {}).get(self.caps.name, {}) if self.caps else {}

    def _build_tray_auto(self):
        self.tray_list = trays.trays_of(self._pc())
        self.cmb_weight = None
        if not self.tray_list or not self.caps.roles.get("source"):
            return
        weights = trays.weights_of(self._pc())
        self.s.__dict__.setdefault("weights", {})
        cur = self.s.weights.get(self.caps.name, 0)
        if weights:
            self.cmb_weight = QComboBox()
            fill_combo(self.cmb_weight, [(0, tr("beliebig"))] + [(w, tr("{0} g/m²").format(w)) for w in weights], cur)
            self.cmb_weight.currentIndexChanged.connect(self._weight_changed)
            self.paper_form.addRow(tr("Grammatur:"), self.cmb_weight)
        self.chk_autotray = QCheckBox(tr("Fach automatisch nach Format/Grammatur wählen"))
        self.chk_autotray.setChecked(bool(self._pc().get("tray_auto", True)))
        self.chk_autotray.toggled.connect(lambda _b: self._auto_tray())
        self.paper_form.addRow("", self.chk_autotray)
        self.lbl_tray = QLabel()
        self.lbl_tray.setWordWrap(True)
        self.paper_form.addRow("", self.lbl_tray)
        self._live = None
        host = self._pc().get("tray_host", "")
        if self._pc().get("tray_live") and host:
            self._start_live(host)
        self._auto_tray()

    def _start_live(self, host):
        from PySide6.QtCore import QThread, Signal

        class _Live(QThread):
            got = Signal(object)

            def run(self_t):
                self_t.got.emit(trays.live_status(host, force=True))
        self._live_thread = _Live(self)
        self._live_thread.got.connect(self._live_arrived)
        self._live_thread.start()

    def _live_arrived(self, st):
        self._live = st
        if st is None and hasattr(self, "lbl_tray"):
            self.lbl_tray.setToolTip(tr("Gerät nicht erreichbar – es gilt die hinterlegte Reihenfolge."))
        self._auto_tray()

    def _weight_changed(self, *_):
        self.s.weights[self.caps.name] = self.cmb_weight.currentData() or 0
        self._auto_tray()

    def _auto_tray(self):
        if not getattr(self, "tray_list", None) or not hasattr(self, "chk_autotray"):
            return
        if not self.chk_autotray.isChecked():
            self.lbl_tray.setText("")
            self._auto_slot = None
            return
        skey, pkey, mkey = (self.caps.roles.get(r) for r in ("source", "pagesize", "mediatype"))
        weight = self.cmb_weight.currentData() if self.cmb_weight else 0
        labels = {c.value: c.text for c in self.caps.options[skey].choices}
        p = trays.pick(self.tray_list, self.values.get(pkey, ""), weight or 0, self._live, labels)
        if p.tray:
            self.values[skey] = p.tray.slot
            self._set_combo(skey, p.tray.slot)
            if p.tray.media and mkey:
                self.values[mkey] = p.tray.media
                self._set_combo(mkey, p.tray.media)
            self._auto_slot = p.tray.slot
            txt = f"→ {labels.get(p.tray.slot, p.tray.slot)}" + (f"   ({p.note})" if p.note else "")
        else:
            self._auto_slot = None
            txt = "⚠ " + p.note
        if self._live is not None:
            txt += tr("   · Füllstand vom Gerät")
        self.lbl_tray.setText(txt)
        self.lbl_tray.setStyleSheet(f"color: {theme.ERROR if p.warn else theme.ACCENT};")
        self._preview_timer.start()

    def _set_combo(self, key, value):
        cb = self.role_combos.get(key) or getattr(self, "driver_combos", {}).get(key)
        if cb is not None:
            cb.blockSignals(True)
            i = cb.findData(value)
            if i >= 0:
                cb.setCurrentIndex(i)
            cb.blockSignals(False)

    def _presets(self):
        return self.cfg.get("printers", {}).get(self.caps.name, {}).get("presets", []) if self.caps else []

    def _build_finishing(self):
        while self.finish_form.rowCount():
            self.finish_form.removeRow(0)
        presets = self._presets()
        self.cmb_preset = QComboBox()
        fill_combo(self.cmb_preset, [("", tr("(keine Vorlage)"))] + [(str(i), p["name"]) for i, p in enumerate(presets)],
                   getattr(self, "_preset_sel", {}).get(self.caps.name, ""))
        self.cmb_preset.setEnabled(bool(presets))
        self.cmb_preset.setToolTip(tr("Vom Admin angelegte Finisher-Vorlagen, z. B. „Broschüre heften + falzen“"))
        self.cmb_preset.currentIndexChanged.connect(self._preset_chosen)
        self.finish_form.addRow(tr("Vorlage:"), self.cmb_preset)
        n = 0
        for role, label in FINISH_LABELS:
            key = self.caps.roles.get(role)
            if key and key in self.caps.options and key not in self.role_combos:
                cb = self._option_combo(key)
                self.role_combos[key] = cb
                self.finish_form.addRow(f"{tr(label)}\n({self.caps.options[key].text}):", cb)
                n += 1
        if self.caps.backend == "win":
            btn = QPushButton(tr("Herstellereinstellungen (Finisher, Heften, Falzen …)"))
            btn.clicked.connect(self._win_driver_dialog)
            self.finish_form.addRow(btn)
            self.lbl_devmode = QLabel()
            self.lbl_devmode.setStyleSheet(f"color: {theme.MUTED};")
            self.finish_form.addRow(self.lbl_devmode)
            self._update_devmode_label()
        elif not n:
            lbl = QLabel(tr("Keine Finisher-Optionen erkannt – alle Treiberoptionen unten bei „Treiber (alle Optionen)“. "
                         "Fehlen Finisher ganz: im Admin unter „Installierte Hardware“ einschalten."))
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color: {theme.MUTED};")
            self.finish_form.addRow(lbl)

    def _update_devmode_label(self):
        if hasattr(self, "lbl_devmode"):
            has = bool(self.values.get("__devmode__"))
            self.lbl_devmode.setText(tr("Herstellereinstellungen aktiv (Admin-Standard, Vorlage oder von dir gesetzt).")
                                     if has else tr("Es gelten die Windows-Standards des Druckers."))

    def _win_driver_dialog(self):
        from ..printers_win import DEVMODE_KEY, driver_dialog
        try:
            res = driver_dialog(int(self.winId()), self.caps.name, self.values.get(DEVMODE_KEY))
        except Exception as e:
            QMessageBox.critical(self, tr("Treiberdialog"), str(e))
            return
        if res:
            self.values[DEVMODE_KEY] = res
            self._update_devmode_label()
            self._changed()

    def _preset_chosen(self, *_):
        idx = self.cmb_preset.currentData()
        self.__dict__.setdefault("_preset_sel", {})[self.caps.name] = idx or ""
        if not idx:
            return
        pr = self._presets()[int(idx)]
        for k, v in pr.get("options", {}).items():
            if k in self.caps.options:
                self.values[k] = v
        if pr.get("devmode"):
            self.values["__devmode__"] = pr["devmode"]
        if pr.get("booklet") and self._handling() != "booklet":
            self.handling_btns["booklet"].setChecked(True)
            self.stack.setCurrentIndex(self.handling_btns["booklet"].property("page"))
        # Felder neu aufbauen, damit sie die Vorlage zeigen
        self._build_paper()
        skey = self.caps.roles.get("source")
        if skey and skey in pr.get("options", {}) and hasattr(self, "chk_autotray"):
            # Vorlage bestimmt das Fach selbst (z. B. Umschlagkarton aus dem Mehrzweckfach)
            self.chk_autotray.blockSignals(True)
            self.chk_autotray.setChecked(False)
            self.chk_autotray.blockSignals(False)
            self.values[skey] = pr["options"][skey]
            self._set_combo(skey, self.values[skey])
            self.lbl_tray.setText(tr("Fach durch Vorlage festgelegt"))
        self._build_driver_tab()
        fit_width(self)
        self._changed()

    def _build_driver_tab(self):
        old = self.driver_box.layout()
        if old is not None:
            QWidget().setLayout(old)   # altes Layout entsorgen
        v = QVBoxLayout(self.driver_box)
        self.lbl_conflict = QLabel()
        self.lbl_conflict.setWordWrap(True)
        self.lbl_conflict.setStyleSheet(f"color: {theme.ERROR};")
        v.addWidget(self.lbl_conflict)
        backend = {"ppd": "PPD (Herstellertreiber)", "ipp": "IPP (driverless)",
                   "win": "Windows-Druckertreiber"}.get(self.caps.backend, self.caps.backend)
        info = QLabel(tr("Backend: {0} – alle Optionen bleiben wählbar; Konflikte werden nur gemeldet.").format(backend)
                      if self.caps.backend != "win" else
                      tr("Backend: {0}. Alle herstellerspezifischen Funktionen (Finisher, Heften, Lochen, Falzen, Beschnitt, Fiery-Optionen …) stellst du im Original-Dialog des Herstellers ein. Papierformat, Fach, Duplex und Farbe von oben haben Vorrang.").format(backend))
        info.setWordWrap(True)
        info.setStyleSheet(f"color: {theme.MUTED};")
        v.addWidget(info)
        if self.caps.backend == "win":
            btn = QPushButton(tr("Herstellereinstellungen öffnen …"))
            btn.clicked.connect(self._win_driver_dialog)
            v.addWidget(btn)
        self.driver_combos = {}
        installable = []
        for gname, gtext, keys in self.caps.groups:
            keys = [k for k in keys if k not in self.role_combos]
            if not keys:
                continue
            if gname == printers.INSTALLABLE_GROUP:
                installable = keys
                continue
            box = QGroupBox(gtext)
            f = QFormLayout(box)
            for k in keys:
                cb = self._option_combo(k)
                self.driver_combos[k] = cb
                f.addRow(self.caps.options[k].text + ":", cb)
            v.addWidget(box)
        if installable:
            box = QGroupBox(tr("Installierte Hardware (nur Admin änderbar)"))
            f = QFormLayout(box)
            for k in installable:
                o = self.caps.options[k]
                txt = next((c.text for c in o.choices if c.value == o.default), o.default)
                f.addRow(o.text + ":", QLabel(txt))
            v.addWidget(box)
        v.addStretch()

    def _option_changed(self, cb):
        key = cb.property("key")
        self.values[key] = cb.currentData()
        if self.caps and key == self.caps.roles.get("pagesize"):
            self._auto_tray()            # format changed -> select a matching tray
        self._changed()

    def _build_profiles(self):
        name = self.caps.name
        profs = config.profiles_for(self.cfg, name)
        pid, intent = self.s.color_for(name)
        self.cmb_profile.blockSignals(True)
        self.cmb_intent.blockSignals(True)
        fill_combo(self.cmb_profile, [("", tr("Keins – Farbmanagement des Treibers"))] +
                   [(p["id"], p.get("name") or p["id"]) for p in profs], pid)
        self._fill_intents(intent)
        user = bool(self.cfg.get("allow_user_profile_choice", True))
        if self._is_pdf_target():                   # PDF output: colors stay unchanged
            fill_combo(self.cmb_profile, [("", tr("Keins – Farben bleiben unverändert"))], "")
            user = False
        self.cmb_profile.setEnabled(user and bool(profs))
        self.cmb_intent.setEnabled(user and bool(self.cmb_profile.currentData()))
        self.cmb_profile.blockSignals(False)
        self.cmb_intent.blockSignals(False)
        self._profile_note()

    def _fill_intents(self, current):
        p = config.profile_by_id(self.cfg, self.cmb_profile.currentData() or "")
        allowed = (p or {}).get("intents") or list(config.INTENTS)
        fill_combo(self.cmb_intent, [(i, config.INTENTS[i]) for i in allowed if i in config.INTENTS], current)

    def _profile_changed(self, *_):
        cur_intent = self.cmb_intent.currentData() or "relative"
        if self.sender() is self.cmb_profile:
            self.cmb_intent.blockSignals(True)
            self._fill_intents(cur_intent)
            self.cmb_intent.blockSignals(False)
        self.cmb_intent.setEnabled(self.cmb_profile.isEnabled() and bool(self.cmb_profile.currentData()))
        self.s.color[self.caps.name] = (self.cmb_profile.currentData() or "",
                                        self.cmb_intent.currentData() or "relative")
        self._profile_note()
        self._preview_timer.start()

    def _profile_note(self):
        p = config.profile_by_id(self.cfg, self.cmb_profile.currentData() or "")
        if not p:
            self.lbl_profile_note.setText("")
            return
        dopts = p.get("driver_options") or {}
        txt = tr("Das PDF wird vor dem Senden mit diesem Profil in Gerätefarben umgerechnet.")
        if dopts:
            txt += tr(" Profil setzt Treiberoptionen: ") + ", ".join(f"{k}={v}" for k, v in dopts.items())
        self.lbl_profile_note.setText(txt)

    # ================================================================== #
    # Zustand -> Layout
    # ================================================================== #
    def _settings(self) -> layout.LayoutSettings:
        L = layout.LayoutSettings()
        L.mode = self.mode_group.checkedButton().property("mode") if self.mode_group.checkedButton() else "fit"
        L.custom_percent = self.spn_custom.value()
        L.custom_by = self.cmb_custom_by.currentData()
        L.custom_mm = self.spn_custom_mm.value()
        h = self._handling()
        L.handling = h
        n = self.cmb_nup.currentData()
        if n == 0:
            L.cols, L.rows, L.nup = self.spn_cols.value(), self.spn_rows.value(), 1
        else:
            L.nup = n
        L.booklet_sides = self.cmb_bsides.currentData()
        L.booklet_binding = self.cmb_binding.currentData()
        L.booklet_sheets = self.ed_bsheets.text().strip()
        L.booklet_gutter_mm = self.spn_gutter.value()
        L.booklet_kind = self.cmb_bkind.currentData() or "saddle"
        L.booklet_per_sig = self.spn_persig.value()
        L.booklet_creep_mm = self.spn_creep.value()
        L.booklet_spread = self.cmb_bspread.currentData() or "side"
        L.booklet_nutzen = self.chk_bnutzen.isChecked()
        L.booklet_blanks = self.cmb_blanks.currentData() or "end"
        L.booklet_blank_text = self.ed_blank.text()
        L.booklet_fold_marks = self.chk_bfold.isChecked()
        L.booklet_reg_marks = self.chk_breg.isChecked()
        L.booklet_collation_marks = self.chk_bcoll.isChecked()
        L.poster_mode = self.cmb_pmode.currentData()
        L.poster_percent = self.spn_ppct.value()
        L.poster_cols, L.poster_rows = self.spn_pcols.value(), self.spn_prows.value()
        L.poster_target = self.cmb_ptarget.currentData()
        L.poster_target_w_mm, L.poster_target_h_mm = self.spn_ptw.value(), self.spn_pth.value()
        L.poster_overlap_mm = self.spn_overlap.value()
        L.poster_marks = self.chk_pmarks.isChecked()
        L.poster_labels = self.chk_plabels.isChecked()
        L.poster_large_only = self.chk_plarge.isChecked()
        L.mirror_h = self.chk_mirror_h.isChecked()
        L.mirror_v = self.chk_mirror_v.isChecked()
        # Step & Repeat wirkt auf den gewählten Modus: Broschüre -> die Druckbögen (sr_multi),
        # sonst die Seiten (step_repeat, wie bisher)
        L.sr_multi = self.chk_sr.isChecked()
        L.step_repeat = self.chk_sr.isChecked() and h != "booklet"
        L.sr_mode = self.cmb_srmode.currentData()
        L.sr_cols, L.sr_rows = self.spn_srcols.value(), self.spn_srrows.value()
        L.sr_percent = self.spn_srpct.value()
        L.sr_by = self.cmb_srby.currentData()
        L.sr_mm = self.spn_srmm.value()
        L.sr_gap_mm = self.spn_srgap.value()
        L.sr_orientation = self.cmb_srorient.currentData()
        L.sr_rotate = self.cmb_srrot.currentData()
        L.sr_join = self.cmb_srjoin.currentData()
        L.sr_sequence = self.chk_srseq.isChecked()
        L.sr_stack = self.cmb_srstack.currentData() or "row"
        L.sr_pass2 = self.chk_sr2.isChecked()
        L.sr2_format = self.cmb_sr2fmt.currentData() or "custom"
        L.sr2_w_mm, L.sr2_h_mm = self.spn_sr2w.value(), self.spn_sr2h.value()
        L.sr2_cols, L.sr2_rows = self.spn_sr2cols.value(), self.spn_sr2rows.value()
        L.crop_marks = self.chk_marks.isChecked()
        L.bleed_mm = self.spn_bleed.value()
        L.order = self.cmb_order.currentData()
        L.tile_mode = self.cmb_tile.currentData()
        L.tile_percent = self.spn_tile.value()
        L.gap_mm = self.spn_gap.value()
        L.borders = self.chk_borders.isChecked()
        L.orientation = self.cmb_orient.currentData()
        L.autorotate = self.chk_autorot.isChecked()
        L.center = self.chk_center.isChecked()
        L.use_margins = self.chk_margins.isChecked()
        return L

    def _load_layout(self, L: layout.LayoutSettings):
        """Felder aus Layout-Einstellungen setzen (Preset)."""
        def pick(cmb, val):
            i = cmb.findData(val)
            if i >= 0:
                cmb.setCurrentIndex(i)
        for b in self.mode_group.buttons():
            if b.property("mode") == L.mode:
                b.setChecked(True)
        pick(self.cmb_custom_by, L.custom_by)
        self.spn_custom.setValue(L.custom_percent)
        self.spn_custom_mm.setValue(L.custom_mm)
        if L.cols and L.rows:
            pick(self.cmb_nup, 0)
            self.spn_cols.setValue(L.cols)
            self.spn_rows.setValue(L.rows)
        else:
            pick(self.cmb_nup, L.nup if L.nup > 1 else 2)
        pick(self.cmb_order, L.order)
        pick(self.cmb_tile, L.tile_mode)
        self.spn_tile.setValue(L.tile_percent)
        self.spn_gap.setValue(L.gap_mm)
        self.chk_borders.setChecked(L.borders)
        pick(self.cmb_bsides, L.booklet_sides)
        pick(self.cmb_binding, L.booklet_binding)
        self.ed_bsheets.setText(L.booklet_sheets)
        self.spn_gutter.setValue(L.booklet_gutter_mm)
        self.spn_persig.blockSignals(True)
        self.spn_persig.setValue(L.booklet_per_sig)
        self.spn_persig.blockSignals(False)
        pick(self.cmb_bkind, L.booklet_kind)
        self.spn_creep.setValue(L.booklet_creep_mm)
        pick(self.cmb_bspread, getattr(L, "booklet_spread", "side"))
        self.chk_bnutzen.blockSignals(True)
        self.chk_bnutzen.setChecked(True)          # alte Presets: Broschüre läuft immer über Druckbögen
        self.chk_bnutzen.blockSignals(False)
        pick(self.cmb_blanks, L.booklet_blanks)
        self.ed_blank.setText(L.booklet_blank_text)
        self.chk_bfold.setChecked(L.booklet_fold_marks)
        self.chk_breg.setChecked(L.booklet_reg_marks)
        self.chk_bcoll.setChecked(L.booklet_collation_marks)
        pick(self.cmb_pmode, L.poster_mode)
        self.spn_ppct.setValue(L.poster_percent)
        self.spn_pcols.setValue(L.poster_cols)
        self.spn_prows.setValue(L.poster_rows)
        pick(self.cmb_ptarget, L.poster_target)
        self.spn_ptw.setValue(L.poster_target_w_mm)
        self.spn_pth.setValue(L.poster_target_h_mm)
        self.spn_overlap.setValue(L.poster_overlap_mm)
        self.chk_pmarks.setChecked(L.poster_marks)
        self.chk_plabels.setChecked(L.poster_labels)
        self.chk_plarge.setChecked(L.poster_large_only)
        pick(self.cmb_orient, L.orientation)
        self.chk_autorot.setChecked(L.autorotate)
        self.chk_center.setChecked(L.center)
        self.chk_margins.setChecked(L.use_margins)
        self.chk_mirror_h.setChecked(L.mirror_h)
        self.chk_mirror_v.setChecked(L.mirror_v)
        self.chk_sr.setChecked(L.step_repeat)
        pick(self.cmb_srmode, L.sr_mode)
        self.spn_srcols.setValue(L.sr_cols)
        self.spn_srrows.setValue(L.sr_rows)
        self.spn_srpct.setValue(L.sr_percent)
        pick(self.cmb_srby, L.sr_by)
        self.spn_srmm.setValue(L.sr_mm)
        self.spn_srgap.setValue(L.sr_gap_mm)
        pick(self.cmb_srorient, L.sr_orientation)
        pick(self.cmb_srrot, str(L.sr_rotate))
        pick(self.cmb_srjoin, L.sr_join)
        self.chk_srseq.setChecked(L.sr_sequence)
        pick(self.cmb_srstack, L.sr_stack)
        self.chk_sr2.setChecked(bool(L.sr_pass2))
        if self.cmb_sr2fmt.count():
            i = self.cmb_sr2fmt.findData(L.sr2_format or "custom")
            self.cmb_sr2fmt.setCurrentIndex(i if i >= 0 else self.cmb_sr2fmt.count() - 1)
        self.spn_sr2w.setValue(L.sr2_w_mm)
        self.spn_sr2h.setValue(L.sr2_h_mm)
        self.spn_sr2cols.setValue(L.sr2_cols)
        self.spn_sr2rows.setValue(L.sr2_rows)
        self.chk_marks.setChecked(L.crop_marks)
        self.spn_bleed.setValue(L.bleed_mm)
        self.handling_btns.get(L.handling, self.handling_btns["size"]).setChecked(True)
        on = bool(L.step_repeat or getattr(L, "sr_multi", False))
        if bool(self.chk_sr.isChecked()) != on:
            self.chk_sr.setChecked(on)
        self._handling_changed()
        self._changed()

    def _pages(self) -> list[int]:
        n = len(self.doc)
        cur = self.current if self.rb_cur.isChecked() else None
        rng = self.ed_range.text() if self.rb_range.isChecked() else ""
        rev = self.chk_reverse.isChecked() and self._handling() != "booklet"
        return layout.select_pages(n, rng, self.cmb_subset.currentData(), rev, cur)

    def _make_plans(self, pages):
        if getattr(self, "trims", None) is None:
            try:
                self.trims, self.doc_bleeds = layout.page_trims(self.doc), layout.page_doc_bleeds(self.doc)
            except Exception:
                self.trims, self.doc_bleeds = [], []
        s = self._settings()
        sheet = self._sheet()
        self._spr_active = layout.is_booklet_spreads(s)
        if self._spr_active:
            # Broschüre als Druckbögen: aufgeklappte Bögen mit der Nutzen-Logik montieren –
            # Vorschau, Bogenübersicht und Schritt 2 sehen genau das, was gedruckt wird
            s = self._spreads(pages, s)
            plans = printjob.make_plans(self._spr_sizes, self._spr_pages, sheet, s, False,
                                        self._spr_trims, self._spr_bleeds)
            layout.mark_spread_duplex(plans, self._settings())
            if plans and self._spr_notes:
                plans[0].warnings.extend(n for n in self._spr_notes[1:] if n not in plans[0].warnings)
        else:
            plans = printjob.make_plans(self.sizes, pages, sheet, s,
                                        self.chk_reverse.isChecked(), self.trims, self.doc_bleeds)
        if layout.is_step2(s) and plans:
            # Vorschau zeigt Schritt 2: die fertigen Bögen aufs Zielformat montiert
            self.plans1 = plans
            self.plans2 = layout.plan_step2((sheet.width, sheet.height), len(plans), s)
            return self.plans2
        self.plans1 = self.plans2 = None
        return plans

    def _short_edge_choice(self):
        return printjob.short_edge_choice(self.caps)

    # ---------------- Duplex-Vorschau (Vorder-/Rückseite je Wendekante) ------------- #
    def _duplex_active(self) -> bool:
        """Duplex am Gerät gewählt (Vorder- UND Rückseite auf einem Blatt)?"""
        if self.caps is None:
            return False
        key = self.caps.roles.get("duplex")
        if not key:
            return False
        val = str(self.values.get(key, ""))
        txt = next((c.text for c in self.caps.options[key].choices if c.value == val), "")
        both = val + " " + txt
        return bool(re.search(r"two|duplex|doppel|beidseit", both, re.I)
                    and not re.search(r"one|none|off|simplex|einseit", both, re.I))

    def _duplex_short(self) -> bool:
        """Wendekante der aktuellen Duplex-Einstellung: kurze Kante (tumble)?"""
        dc = self._short_edge_choice()
        if not dc:
            return False
        return self.values.get(dc[0]) == dc[1]

    def _duplex_layout(self):
        """Wo die Rückseite in der Vorschau liegt: None = keine Rückseite zeigen.

        Querformat: kurze Kante -> Rückseite links, lange Kante -> darunter.
        Hochformat: kurze Kante -> darunter, lange Kante -> rechts davon.
        """
        if self.caps is None or not self.plans:
            return None
        s = self._settings()
        if s.handling == "poster":
            return None                 # Poster: der nächste Plan ist die nächste Kachel, keine Rückseite
        if s.handling == "booklet" and s.booklet_sides != "both":
            return None                 # nur Vorder-/Rückseiten: Rückseite ist nicht ausgeschossen
        if s.handling == "booklet":
            land = self.plans[self.sheet_index].landscape
            short = land == (s.booklet_spread != "top")   # Druckbögen: Wendekante parallel zum Falz
        elif self._duplex_active():
            short = self._duplex_short()
        else:
            return None
        land = self.plans[self.sheet_index].landscape
        if land:
            return "left" if short else "below"
        return "below" if short else "right"

    def _preset_settings(self) -> layout.ImposeSettings:
        """Layout + current paper size – so a print preset also fits `passermark-cli impose`."""
        import dataclasses
        imp = layout.ImposeSettings(**dataclasses.asdict(self._settings()))
        try:
            sh = self._sheet() if self.caps else None
        except Exception:
            sh = None
        if sh is not None:
            from ..printers import STD_SIZES_MM
            w, h = sh.width / layout.MM, sh.height / layout.MM
            name = next((k for k, (a, b) in STD_SIZES_MM.items() if abs(a - w) < 1 and abs(b - h) < 1), None)
            if name:
                imp.sheet = name
            else:
                imp.sheet, imp.sheet_w_mm, imp.sheet_h_mm = "custom", round(w, 1), round(h, 1)
        return imp

    def _sheet(self) -> layout.Sheet:
        w, h, ia = self.caps.sheet_for(self.values)
        if self.caps.backend == "pdf" and self.values.get("PageSize") == "DOC":
            try:
                pages = self._pages()
            except ValueError:
                pages = []
            w, h = self.sizes[pages[0] if pages else self.current]
            ia = None
        return layout.Sheet(w, h, ia)

    def _base_print_doc(self):
        """Druckfassung des Dokuments: Formularwerte/Kommentare eingebrannt (einmal je Dialog)."""
        if getattr(self, "_flat", None) is None:
            self._flat = layout.flattened(self.doc)
        return self._flat

    def _print_doc(self):
        """Quelle für Vorschau/Montage: das Dokument – bzw. bei „Als Druckbögen montieren“ die Druckbögen."""
        if getattr(self, "_spr_active", False) and getattr(self, "_spr_doc", None) is not None:
            return self._spr_doc
        return self._base_print_doc()

    def _eff_settings(self):
        """Einstellungen, nach denen montiert wird (Broschüre als Druckbögen -> Nutzen-Logik)."""
        s = self._settings()
        return layout.spread_settings(s) if layout.is_booklet_spreads(s) else s

    def _spreads(self, pages, s):
        """Druckbögen (zwischengespeichert, neu nur wenn sich Seiten oder Broschüren-Werte ändern)."""
        key = (tuple(pages), s.booklet_spread, s.booklet_kind, s.booklet_per_sig, s.booklet_binding,
               s.booklet_blanks, s.booklet_sheets, s.booklet_sides)
        if getattr(self, "_spr_key", None) != key:
            old = getattr(self, "_spr_doc", None)
            self._spr_doc = None
            if old is not None:
                old.close()
            doc, spages, ss, notes = layout.spread_source(self._base_print_doc(), pages, s, self.trims)
            self._spr_doc, self._spr_pages, self._spr_notes = doc, spages, notes
            self._spr_sizes = [doc.get_page_size(i) for i in range(len(doc))]
            self._spr_trims, self._spr_bleeds = layout.page_trims(doc), layout.page_doc_bleeds(doc)
            self._spr_key = key
        return layout.spread_settings(s)

    def done(self, r):
        if getattr(self, "sr_win", None) is not None:
            self.sr_win.hide()
        spr = getattr(self, "_spr_doc", None)
        if spr is not None:
            spr.close()
            self._spr_doc = None
        flat = getattr(self, "_flat", None)
        if flat is not None and flat is not self.doc:
            flat.close()
        self._flat = None
        super().done(r)

    def _is_pdf_target(self):
        return bool(self.caps and self.caps.backend == "pdf")

    def _changed(self, *_):
        self._sync_enabled()
        if not self.caps:
            return
        # Sitzung merken (nur RAM)
        self.s.layout = self._settings()
        self.s.copies = self.spn_copies.value()
        self.s.collate = self.chk_collate.isChecked()
        self.s.subset = self.cmb_subset.currentData()
        self.s.reverse = self.chk_reverse.isChecked()
        bad = self.caps.conflicts(self.values)
        self.lbl_conflict.setText((tr("⚠ Treiber meldet Konflikt bei: ") + ", ".join(
            self.caps.options[k].text for k in bad)) if bad else "")
        self._preview_timer.start()

    def _update_preview(self):
        self.lbl_warn.clear()
        try:
            pages = self._pages()
            self.ed_range.setStyleSheet("")
        except ValueError as e:
            self.ed_range.setStyleSheet("background: #ffd6d6;")
            self.lbl_warn.setText(str(e))
            self.plans = []
            self.preview.set_content(None, None, False)
            return
        try:
            self.plans = self._make_plans(pages)
        except ValueError as e:
            self.lbl_warn.setText(str(e))
            self.plans = []
        self.sheet_index = min(self.sheet_index, max(0, len(self.plans) - 1))
        try:
            self._render_sheet()
        except Exception as e:          # the preview must never take the program down with it
            self.lbl_warn.setText(tr("Vorschau nicht möglich: {0}").format(e))

    def _pair_step(self) -> int:
        """Duplex-Vorschau zeigt Vorder- UND Rückseite: dann bogenweise (2 Seiten) blättern."""
        try:
            return 2 if self._duplex_layout() else 1
        except Exception:
            return 1

    def _step_sheet(self, d: int):
        st = self._pair_step()
        i = self.sheet_index - (self.sheet_index % st) + d * st
        self._goto_sheet(max(0, min(i, len(self.plans) - 1)))

    def _goto_sheet(self, i):
        if 0 <= i < len(self.plans):
            self.sheet_index = i
            self._render_sheet()

    def _sheet_overview(self):
        """All sheets as thumbnails (reading order) – shows the distribution of the pages at a glance."""
        from PySide6.QtWidgets import QListView, QListWidget, QListWidgetItem
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QIcon
        from .manipdialog import pil_to_pixmap
        if not self.plans:
            QMessageBox.information(self, tr("Bogenübersicht"), tr("Keine Seiten"))
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            s = self._eff_settings()
            if layout.is_step2(s) and getattr(self, "plans2", None):
                out, sheet = layout.impose_step2(self._print_doc(), self._sheet(),
                                                  self.plans1, s, plans2=self.plans2), layout.step2_sheet(s)
            else:
                sheet = self._sheet()
                out = layout.impose_with(self._print_doc(), sheet, self.plans, s)
            thumbs = []
            for i, sp in enumerate(self.plans[:400]):
                pg = out[i]
                img = pg.render(scale=150 / max(sheet.width, sheet.height), rotation=90 if sp.landscape else 0).to_pil()
                pg.close()
                thumbs.append((pil_to_pixmap(img), sp.label or tr("Blatt {0}").format(i + 1)))
            out.close()
        finally:
            QApplication.restoreOverrideCursor()
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("Bogenübersicht – Passermark"))
        dlg.resize(980, 700)
        v = QVBoxLayout(dlg)
        lw = QListWidget()
        lw.setViewMode(QListView.ViewMode.IconMode)
        lw.setIconSize(QSize(160, 160))
        lw.setGridSize(QSize(200, 215))
        lw.setResizeMode(QListView.ResizeMode.Adjust)
        lw.setMovement(QListView.Movement.Static)
        lw.setWordWrap(True)
        for pm, text in thumbs:
            lw.addItem(QListWidgetItem(QIcon(pm), text))
        lw.itemDoubleClicked.connect(lambda it: (self._goto_sheet(lw.row(it)), dlg.accept()))
        v.addWidget(lw, 1)
        hint = QLabel(tr("Doppelklick springt zu diesem Bogen in der Vorschau."))
        hint.setStyleSheet(f"color: {theme.MUTED};")
        v.addWidget(hint)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        dlg.exec()

    def _render_sheet2(self, s):
        """Vorschau des Schritt-2-Bogens: fertig montierte Bögen aufs Zielformat, mittig."""
        n = len(self.plans)
        if n:
            lab = self.plans[self.sheet_index].label
            self.lbl_sheet.setText(tr("Zielformat (Schritt 2): Blatt {0} von {1}").format(self.sheet_index + 1, n)
                                  + (f"\n{lab}" if lab else ""))
        else:
            self.lbl_sheet.setText(tr("Keine Seiten"))
        self.btn_prev.setEnabled(self.sheet_index > 0)
        self.btn_next.setEnabled(self.sheet_index < n - 1)
        if not n:
            self.preview.set_content(None, None, False)
            return
        sheet = layout.step2_sheet(s)
        sp = self.plans[self.sheet_index]
        # derselbe Weg wie bei der Ausgabe: Schritt-1-Bogen flach zwischenspeichern,
        # dann montieren – Vorschau und Ergebnis sind identisch
        out = layout.impose_step2(self._print_doc(), self._sheet(), self.plans1, s,
                                  plans2=self.plans2, only=[self.sheet_index])
        page = out[0]
        target_h = max(200, self.preview.height() - 32)
        ph = sheet.width if sp.landscape else sheet.height
        scale = target_h / ph
        dpr = self.devicePixelRatioF()
        pm = self._proofed_pixmap(page, scale, 90 if sp.landscape else 0, dpr)
        page.close()
        out.close()
        self.preview.set_content(pm, sheet, sp.landscape)
        cols = len({round(pl.x, 1) for pl in sp.placements}) or 1
        rows = len({round(pl.y, 1) for pl in sp.placements}) or 1
        sw, sh = self._sheet().width / layout.MM, self._sheet().height / layout.MM
        self.lbl_info.setText(
            tr("Schritt 2 – Zielformat: {0:.0f} × {1:.0f} mm · {2} × {3} Bögen ({4:.0f} × {5:.0f} mm) je Blatt{6}").format(
                sheet.width / layout.MM, sheet.height / layout.MM, cols, rows, sw, sh,
                tr(" · quer") if sp.landscape else ""))
        warns = sorted({w for p in self.plans for w in p.warnings}
                       | {w for p in (self.plans1 or []) for w in p.warnings})
        self.lbl_warn.setText("\n".join(warns[:4]) + (" …" if len(warns) > 4 else ""))

    def _render_sheet(self):
        s = self._eff_settings()
        if layout.is_step2(s) and getattr(self, "plans2", None):
            return self._render_sheet2(s)
        n = len(self.plans)
        st = self._pair_step() if n else 1
        if st == 2:                                  # Duplex: immer bei der Vorderseite eines Bogens beginnen
            self.sheet_index -= self.sheet_index % 2
        if n:
            lab = self.plans[self.sheet_index].label
            if st == 2:
                self.lbl_sheet.setText(tr("Bogen {0} von {1} (Vorder- und Rückseite)").format(
                    self.sheet_index // 2 + 1, (n + 1) // 2) + (f"\n{lab}" if lab else ""))
            else:
                self.lbl_sheet.setText(tr("Blatt {0} von {1}").format(self.sheet_index + 1, n) + (f"\n{lab}" if lab else ""))
        else:
            self.lbl_sheet.setText(tr("Keine Seiten"))
        self.btn_prev.setEnabled(self.sheet_index > 0)
        self.btn_next.setEnabled(self.sheet_index + st < n)
        if not n:
            self.preview.set_content(None, None, False)
            return
        sheet = self._sheet()
        sp = self.plans[self.sheet_index]
        out = layout.impose_with(self._print_doc(), sheet, self.plans, self._settings(), only=[self.sheet_index])
        page = out[0]
        target_h = max(200, self.preview.height() - 32)
        ph = sheet.width if sp.landscape else sheet.height
        scale = target_h / ph
        dpr = self.devicePixelRatioF()
        pm = self._proofed_pixmap(page, scale, 90 if sp.landscape else 0, dpr)
        page.close()
        out.close()
        # Duplex: Rückseite des Bogens mit zeigen (Lage je nach Wendekante)
        back_pm = None
        back_side = self._duplex_layout()
        if back_side and self.sheet_index + 1 < len(self.plans):
            spb = self.plans[self.sheet_index + 1]
            outb = layout.impose_with(self._print_doc(), sheet, self.plans, self._settings(),
                                      only=[self.sheet_index + 1])
            pgb = outb[0]
            back_pm = self._proofed_pixmap(pgb, scale, 90 if spb.landscape else 0, dpr)
            pgb.close()
            outb.close()
        self.preview.set_content(pm, sheet, sp.landscape, back_pm, back_side if back_pm else None)

        # Info
        key = self.caps.roles.get("pagesize")
        fmt = self.caps.options[key].choices if key else []
        fmt_txt = next((c.text for c in fmt if c.value == self.values.get(key)), "")
        src_key = self.caps.roles.get("source")
        src_txt = ""
        if src_key:
            src_txt = next((c.text for c in self.caps.options[src_key].choices
                            if c.value == self.values.get(src_key)), "")
        scales = sorted({round(p.scale * 100, 1) for p in sp.placements})
        size_txt = ""
        if sp.placements:
            pl = sp.placements[0]
            _sz = self._spr_sizes if getattr(self, "_spr_active", False) else self.sizes
            ow, oh = _sz[pl.src]
            # Darstellung in Leserichtung der Seite (nicht gedreht), auf 0,1 mm
            nw, nh = (pl.h, pl.w) if pl.rot == 90 else (pl.w, pl.h)
            size_txt = (tr("Seite {0}: {1:.1f} × {2:.1f} mm → {3:.1f} × {4:.1f} mm auf dem Blatt").format(pl.src + 1, ow / layout.MM, oh / layout.MM, nw / layout.MM, nh / layout.MM))
            if self.chk_sr.isChecked():
                n = len(sp.placements)
                self.lbl_srsize.setText(tr("je Nutzen {0:.1f} × {1:.1f} mm ({2:.1f} %) · {3} Nutzen pro Blatt – Seite {4}").format(nw / layout.MM, nh / layout.MM, pl.scale * 100, n, pl.src + 1))
            elif self.rb_custom.isChecked() and not self._settings().is_nup:
                self.lbl_custom.setText(tr("ergibt {0:.1f} × {1:.1f} mm ({2:.1f} %) – Seite {3}").format(nw / layout.MM, nh / layout.MM, pl.scale * 100, pl.src + 1))
        # wirksame Nutzen-Anordnung + Abstände (bei Nutzen/Mehrere): Zellabstand
        # = Abstand der Schnittlinien; Weißabstand = sichtbar freier Raum zwischen
        # den Karten (der gespiegelte Anschnitt füllt den Rest)
        join_txt = ""
        if s.handling == "multiple" or s.step_repeat:
            names = {"edge": tr("Kante an Kante"), "bleed": tr("Überfüller an Überfüller"),
                     "gap": tr("Mit Abstand")}
            if s.step_repeat:
                cell_gap = layout._sr_gap(s)
            elif s.sr_join == "edge":
                cell_gap = 0.0
            elif s.sr_join == "gap":
                cell_gap = s.sr_gap_mm + 2 * s.bleed_mm
            else:
                cell_gap = max(s.gap_mm, 2 * s.bleed_mm)
            white = cell_gap - 2 * s.bleed_mm
            join_txt = (tr(" · Anordnung: {0} · Zellabstand: {1:.1f} mm")
                        .format(names.get(s.sr_join, s.sr_join), cell_gap))
            if s.bleed_mm > 0 and white > 0.05:
                join_txt += tr(" (davon {0:.1f} mm sichtbar weiß)").format(white)
        self.lbl_info.setText(
            tr("Papier: {0} ({1:.0f} × {2:.0f} mm)").format(fmt_txt, sheet.width / layout.MM, sheet.height / layout.MM)
            + (tr(" · Fach: {0}").format(src_txt) if src_txt else "")
            + f" · {'Querformat' if sp.landscape else 'Hochformat'}"
            + tr(" · Maßstab: {0}").format(', '.join(f'{s:g} %' for s in scales))
            + join_txt
            + (f"\n{size_txt}" if size_txt else ""))
        warns = sorted({w for p in self.plans for w in p.warnings})
        if not self.caps.sheet_info(self.values)[3]:
            warns.insert(0, tr("⚠ Maße für Papierformat „{0}“ unbekannt – A4 angenommen. "
                               "Bitte Treiber/PPD prüfen.").format(fmt_txt))
        self.lbl_warn.setText("\n".join(warns[:4]) + (" …" if len(warns) > 4 else ""))

    def _proof_params(self):
        """(adjustments, ICC path, intent, BPC, profile name) for the current selection."""
        adj = proof.adjustments(self.caps, self.values)
        pid = self.cmb_profile.currentData() or ""
        prof = config.profile_by_id(self.cfg, pid) if pid else None
        icc = prof.get("file") if prof else None
        intent = self.cmb_intent.currentData() or "relative"
        bpc = bool(prof.get("bpc", True)) if prof else True
        name = (prof.get("name") or pid) if prof else None
        return adj, icc, intent, bpc, name

    def _proofed_pixmap(self, page, scale, rotation, dpr):
        if not self.chk_proof.isChecked():
            self.lbl_proof.setText("")
            return render_pixmap(page, scale, rotation, dpr)
        adj, icc, intent, bpc, name = self._proof_params()
        if not icc and not adj["labels"]:
            self.lbl_proof.setText("")
            return render_pixmap(page, scale, rotation, dpr)
        from PySide6.QtGui import QImage, QPixmap
        bmp = page.render(scale=scale * dpr, rotation=rotation, may_draw_forms=True, draw_annots=True)
        img = proof.apply(bmp.to_pil(), adj, icc, intent, bpc)
        bmp.close()
        data = img.tobytes("raw", "RGB")
        qi = QImage(data, img.width, img.height, 3 * img.width, QImage.Format.Format_RGB888).copy()
        pm = QPixmap.fromImage(qi)
        pm.setDevicePixelRatio(dpr)
        self.lbl_proof.setText(proof.describe(adj, name) + ("" if icc else tr("  (Treiberregler: Annäherung)")))
        return pm

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._preview_timer.start()

    # ================================================================== #
    # Drucken
    # ================================================================== #
    def _print(self):
        if not self.caps:
            return
        try:
            pages = self._pages()
        except ValueError as e:
            QMessageBox.warning(self, tr("Seitenbereich"), str(e))
            return
        if not pages:
            QMessageBox.warning(self, tr("Drucken"), tr("Keine Seiten ausgewählt."))
            return
        name = self.caps.name
        values = self.values
        if self._is_pdf_target():
            pw = ""
            if self.chk_pw.isChecked():
                pw = self.ed_pw.text()
                if not pw:
                    QMessageBox.warning(self, tr("Passwort"), tr("Bitte ein Passwort eingeben."))
                    return
                if pw != self.ed_pw2.text():
                    QMessageBox.warning(self, tr("Passwort"), tr("Die Passwörter stimmen nicht überein."))
                    return
            base = os.path.splitext(os.path.basename(self.path or "Dokument"))[0]
            start_dir = getattr(self.parent(), "_suggest_dir", "") or (
                os.path.dirname(getattr(self.parent(), "path", "") or "") or os.path.expanduser("~"))
            out, _ = QFileDialog.getSaveFileName(self, tr("Als PDF speichern"),
                                                 os.path.join(start_dir, f"{base}_druck.pdf"), tr("PDF-Dateien (*.pdf)"))
            if not out:
                return
            if not out.lower().endswith(".pdf"):
                out += ".pdf"
            src = getattr(self.parent(), "path", None)
            if src and os.path.abspath(out) == os.path.abspath(src):
                QMessageBox.warning(self, tr("Speichern"), tr("Bitte nicht über das geöffnete Dokument speichern."))
                return
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                printjob.submit_document(self.doc, os.path.basename(self.path or "Dokument"), self.s, name,
                                         pages, self._settings(), 1, True, self.chk_reverse.isChecked(),
                                         values=dict(self.values, __out__=out, __password__=pw))
            except Exception as e:
                QApplication.restoreOverrideCursor()
                QMessageBox.critical(self, tr("Speichern"), str(e))
                return
            QApplication.restoreOverrideCursor()
            r = QMessageBox.question(self, tr("Gespeichert"), tr("Gespeichert als:\n{0}\n\nJetzt in Passermark öffnen?").format(out))
            if r == QMessageBox.StandardButton.Yes and hasattr(self.parent(), "ctl"):
                self.parent().ctl.open_paths([out], tab_of=self.parent())
            self.accept()
            return
        skey = self.caps.roles.get("source")
        if getattr(self, "_auto_slot", None) and skey and self.values.get(skey) == self._auto_slot:
            weight = self.cmb_weight.currentData() if getattr(self, "cmb_weight", None) else 0
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            values, note, warn = printjob.resolve_tray(self.s, name, self.values, weight or 0, live=True)
            QApplication.restoreOverrideCursor()
            if warn and values.get(skey) == self.values.get(skey) and "leer" in note:
                if QMessageBox.question(self, tr("Fach leer"), note + tr("\n\nTrotzdem drucken?")) \
                        != QMessageBox.StandardButton.Yes:
                    return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            jid = printjob.submit_document(
                self.doc, os.path.basename(self.path or "Dokument"), self.s, name, pages,
                self._settings(), self.spn_copies.value(), self.chk_collate.isChecked(),
                self.chk_reverse.isChecked(), values=values)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, tr("Druckfehler"), str(e))
            return
        QApplication.restoreOverrideCursor()
        self.parent().statusBar().showMessage(tr("Auftrag {0} an {1} gesendet.").format(jid, name), 8000)
        self.accept()

