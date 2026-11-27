# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Sidebar "Check": findings, fonts, layers, transparency – with repairs (result in a new window)."""

from __future__ import annotations

import os
import traceback

from PySide6.QtCore import QRect, QSize, Qt, QThread, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolButton,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import fontlib, pdflayers, preflight
from ..l10n import tr
from . import lastdir
from . import theme

SEV_TEXT = {"error": "Fehler", "warning": "Warnung", "info": "Hinweis"}
CAT_TEXT = {
    "font": "Schrift",
    "layer": "Ebene",
    "transparency": "Transparenz",
    "overprint": "Überdrucken & Aussparen",
    "text": "Zeichen",
    "image": "Bild",
    "size": "Dateigröße",
    "geometry": "Seitenrahmen",
    "security": "Schutz",
    "pdfx": "PDF/X",
    "form": "Formular",
    "page": "Seite",
    "device": "Drucker",
    "line": "Linien",
    "ink": "Farbauftrag",
}
# icon per category in the findings list (gui/svgicons)
CAT_ICON = {
    "font": "copy",
    "text": "select",
    "image": "color",
    "line": "ruler",
    "transparency": "proof",
    "overprint": "cmyk",
    "layer": "multi",
    "geometry": "boxes",
    "page": "single",
    "security": "info",
    "pdfx": "info",
    "form": "table",
    "size": "shrink",
    "device": "print",
    "ink": "separate",
}
SEV_COLOR = {"error": theme.ERROR, "warning": theme.WARN, "info": theme.MUTED}
SEV_RANK = {"error": 0, "warning": 1, "info": 2}
ROLE_KIND = Qt.ItemDataRole.UserRole + 1  # "group" · "finding" · "spot" · "passed"
ROLE_DETAIL = Qt.ItemDataRole.UserRole + 2  # finding: the full message (grey line under the title)
ROLE_SEV = Qt.ItemDataRole.UserRole + 3  # finding: severity (colour of the stripe)


ROLE_PAGES = Qt.ItemDataRole.UserRole + 4  # finding: pages (right in the title line)
ROLE_ACTION = Qt.ItemDataRole.UserRole + 5  # finding: text of its repair (a link under the message)
ROLE_COUNT = Qt.ItemDataRole.UserRole + 6  # group: number of findings (badge on the right)
ROLE_FIX = Qt.ItemDataRole.UserRole + 7  # finding: its check key (which repair belongs to it)


def _depth(index) -> int:
    d, p = 0, index.parent()
    while p.isValid():
        d, p = d + 1, p.parent()
    return d


class _FindingDelegate(QStyledItemDelegate):
    """Rows of the findings list (1.20.2), one column so that a narrow sidebar is used fully:
    group rows with a count badge on the right; finding rows with a severity stripe, short title and pages in one
    line, the full message wrapped in grey below and – where there is one – the repair as a link below that."""

    PAD = 4
    STRIPE = 3

    def __init__(self, tree, on_action=None):
        super().__init__(tree)
        self.tree = tree
        self.on_action = on_action  # called with the index when the repair link is clicked

    def _width(self, index) -> int:
        return self.tree.viewport().width() - self.tree.indentation() * (_depth(index) + 1)

    def _geometry(self, font, rect: QRect, index) -> dict:
        """Where title, pages, message and repair link go in ``rect`` (also for the height)."""
        title = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        pages = str(index.data(ROLE_PAGES) or "")
        detail = str(index.data(ROLE_DETAIL) or "")
        action = str(index.data(ROLE_ACTION) or "")
        bold = QFont(font)
        bold.setBold(True)
        fm, fb = QFontMetrics(font), QFontMetrics(bold)
        flags = int(Qt.TextFlag.TextWordWrap)
        x = rect.left() + self.STRIPE + self.PAD
        w = max(30, rect.width() - self.STRIPE - 2 * self.PAD)
        pw = fm.horizontalAdvance(pages) + 6 if pages else 0
        if pw > w // 3:  # many pages: below the title instead of beside it
            pw = 0
        tw = max(20, w - pw)
        t = fb.boundingRect(QRect(0, 0, tw, 100000), flags, title)
        y = rect.top() + self.PAD
        out = {"bold": bold, "title": QRect(x, y, tw, t.height()), "pages": None, "detail": None, "action": None}
        if pages:
            if pw:
                out["pages"] = QRect(x + tw, y, pw, fm.height())
            else:
                y += t.height()
                out["pages"] = QRect(x, y, w, fm.boundingRect(QRect(0, 0, w, 100000), flags, pages).height())
                t = QRect(0, 0, 0, out["pages"].height())
        y += t.height()
        if detail:
            d = fm.boundingRect(QRect(0, 0, w, 100000), flags, detail)
            out["detail"] = QRect(x, y + 1, w, d.height())
            y += d.height() + 1
        if action:
            out["action"] = QRect(x, y + 2, min(w, fm.horizontalAdvance("→ " + action) + 4), fm.height())
            y += fm.height() + 2
        out["height"] = y - rect.top() + self.PAD
        return out

    def sizeHint(self, option, index):
        if index.data(ROLE_KIND) != "finding":
            return super().sizeHint(option, index)
        w = self._width(index)
        return QSize(w, self._geometry(option.font, QRect(0, 0, w, 0), index)["height"])

    def paint(self, painter, option, index):
        """Group and finding rows drawn by hand (badge; stripe, title, pages, grey message, link)."""
        kind = index.data(ROLE_KIND)
        if kind == "group":
            count = str(index.data(ROLE_COUNT) or "")
            fm = QFontMetrics(option.font)
            cw = fm.horizontalAdvance(count) + 12 if count else 0
            opt = QStyleOptionViewItem(option)
            opt.rect = QRect(
                option.rect.left(), option.rect.top(), max(10, option.rect.width() - cw), option.rect.height()
            )
            super().paint(painter, opt, index)
            if count:
                painter.save()
                painter.setPen(QColor(index.data(ROLE_SEV) or theme.MUTED))
                f = QFont(option.font)
                f.setBold(True)
                painter.setFont(f)
                r = QRect(option.rect.right() - cw, option.rect.top(), cw - 4, option.rect.height())
                painter.drawText(r, int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), count)
                painter.restore()
            return
        if kind != "finding":
            super().paint(painter, option, index)
            return
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        style = opt.widget.style() if opt.widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        r = option.rect
        g = self._geometry(option.font, r, index)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        flags = int(Qt.TextFlag.TextWordWrap)
        painter.save()
        painter.fillRect(
            QRect(r.left(), r.top() + 3, self.STRIPE, max(4, r.height() - 6)),
            QColor(SEV_COLOR.get(index.data(ROLE_SEV), theme.MUTED)),
        )
        painter.setFont(g["bold"])
        painter.setPen(
            option.palette.color(QPalette.ColorRole.HighlightedText if selected else QPalette.ColorRole.Text)
        )
        painter.drawText(g["title"], flags, str(index.data(Qt.ItemDataRole.DisplayRole) or ""))
        painter.setFont(option.font)
        painter.setPen(QColor(theme.TEXT if selected else theme.MUTED))
        if g["pages"] is not None:
            align = Qt.AlignmentFlag.AlignRight if g["pages"].left() > g["title"].left() else Qt.AlignmentFlag.AlignLeft
            painter.drawText(g["pages"], flags | int(align), str(index.data(ROLE_PAGES) or ""))
        if g["detail"] is not None:
            painter.drawText(g["detail"], flags, str(index.data(ROLE_DETAIL) or ""))
        if g["action"] is not None:
            f = QFont(option.font)
            f.setUnderline(True)
            painter.setFont(f)
            painter.setPen(QColor(theme.ACCENT_TEXT))
            painter.drawText(g["action"], 0, "→ " + str(index.data(ROLE_ACTION) or ""))
        painter.restore()

    def editorEvent(self, event, model, option, index):
        """A click on the repair link runs the repair (instead of only selecting the row)."""
        from PySide6.QtCore import QEvent

        if (
            event.type() == QEvent.Type.MouseButtonRelease
            and index.data(ROLE_KIND) == "finding"
            and index.data(ROLE_ACTION)
            and self.on_action is not None
        ):
            g = self._geometry(option.font, option.rect, index)
            if g["action"] is not None and g["action"].contains(event.position().toPoint()):
                self.on_action(index)
                return True
        return super().editorEvent(event, model, option, index)


KIND_TEXT = {
    "smask": "weiche Maske",
    "blend": "Füllmethode",
    "alpha": "Deckkraft",
    "group": "Transparenzgruppe",
    "overprint": "Überdrucken",
    "image_alpha": "Bild mit Transparenz",
    "pattern_smask": "Verlauf mit Soft-Maske",
}


def overprint_counts(rep) -> int:
    """Number of overprint findings (white overprints + black text that knocks out)."""
    op = getattr(rep, "overprint", None) or {}
    return sum(len(v) for k in ("white", "black_text") for v in (op.get(k) or {}).values())


def overprint_lines(rep) -> list:
    """Lines for the transparency tab: where white overprints and where small black text knocks out."""
    op = getattr(rep, "overprint", None) or {}
    out = []
    for key, text in (
        ("white", tr("Weiß überdruckt (verschwindet): Seite {0}")),
        ("black_text", tr("Schwarzer Text spart aus: Seite {0}")),
    ):
        pages = sorted(op.get(key) or {})
        if pages:
            out.append(text.format(preflight._pages_str(pages)))
    if out:
        out.insert(0, "")
    return out


class _Worker(QThread):
    """Runs a function in a background thread and reports result or error."""

    done = Signal(object, str)

    def __init__(self, fn, *args):
        super().__init__()
        self.fn, self.args = fn, args

    def run(self):
        try:
            self.done.emit(self.fn(*self.args), "")
        except Exception as e:  # noqa: BLE001 – shown to the user
            self.done.emit(None, f"{e}\n\n{traceback.format_exc()}")


class PreflightPanel(QWidget):
    """Show the check result and repair. Signals: open result, jump to page, recheck."""

    result_ready = Signal(bytes, str, list)  # PDF bytes, name suffix, notes
    goto_page = Signal(int)
    goto_spot = Signal(int, object)  # page (1-based), area (x0, y0, x1, y1) pt or None
    job_requested = Signal(str, object, str, str)  # kind, settings, name suffix, title (own process)
    recheck = Signal()
    tool_requested = Signal(str)  # "bleed" · "colorrules" – a dialog of the main window (repair in a finding row)
    profiles_requested = Signal()  # "Profile bearbeiten …"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._owner = parent  # document window (the panel may sit in the separate sidebar window)
        self.rep: preflight.Report | None = None
        self.data_fn = None  # returns the current document bytes
        self.file_fn = None  # file as on disk (size/shrink), otherwise data_fn
        self._job_data = None
        self.font_map: dict[str, str] = {}
        self._worker = None
        self._last_finding = None  # finding clicked last: clicking it again goes to its next location
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)
        # head (1.20.2): traffic light and summary, profile, check again, report
        head = QHBoxLayout()
        self.lbl_light = QLabel("●")
        self.lbl_light.setStyleSheet(f"color: {theme.MUTED}; font-size: 22px;")
        self.lbl_light.setToolTip(tr("Rot: Fehler · Gelb: Warnungen · Grün: druckbereit"))
        head.addWidget(self.lbl_light, 0, Qt.AlignmentFlag.AlignTop)
        self.lbl_sum = QLabel(tr("Noch nicht geprüft."))
        self.lbl_sum.setWordWrap(True)
        f = self.lbl_sum.font()
        f.setBold(True)
        self.lbl_sum.setFont(f)
        head.addWidget(self.lbl_sum, 1)
        from .icons import icon as svg_icon

        b = QToolButton()  # check again / report as symbols: one row less in the narrow sidebar
        b.setIcon(svg_icon("update"))
        b.setToolTip(tr("Neu prüfen"))
        b.setAutoRaise(True)
        b.clicked.connect(self.recheck.emit)
        head.addWidget(b, 0, Qt.AlignmentFlag.AlignTop)
        self.btn_report = QToolButton()
        self.btn_report.setIcon(svg_icon("export"))
        self.btn_report.setToolTip(tr("Bericht …"))
        self.btn_report.setAutoRaise(True)
        self.btn_report.clicked.connect(self._save_report)
        head.addWidget(self.btn_report, 0, Qt.AlignmentFlag.AlignTop)
        v.addLayout(head)
        prow = QHBoxLayout()
        self.cmb_profile = QComboBox()
        self.cmb_profile.setToolTip(tr("Prüfprofil: was wie streng gemeldet wird und mit welchen Grenzwerten"))
        self.fill_profiles()
        self.cmb_profile.currentIndexChanged.connect(self._profile_chosen)
        prow.addWidget(self.cmb_profile, 1)
        b = QToolButton()
        b.setText("…")
        b.setToolTip(tr("Prüfprofile bearbeiten …"))
        b.clicked.connect(self.profiles_requested.emit)
        prow.addWidget(b)
        v.addLayout(prow)
        # the parts as a choice instead of tabs (1.20.2): six tabs wrapped into six rows of buttons in the narrow
        # sidebar and took the place of the findings
        self.cmb_view = QComboBox()
        self.cmb_view.setToolTip(
            tr("Befunde oder die Einzelheiten: Schriften, Ebenen, Transparenz, Bilder, Dateigröße")
        )
        v.addWidget(self.cmb_view)
        self.tabs = QTabWidget()
        self.tabs._flow_tabs = self.cmb_view  # common.wrap_tabs: leave alone, the choice above switches
        self.tabs.tabBar().hide()
        self.tabs.setDocumentMode(True)
        v.addWidget(self.tabs, 1)
        self._build_findings_tab()
        self._build_fonts_tab()
        self._build_layers_tab()
        self._build_transparency_tab()
        self._build_images_tab()
        self._build_size_tab()
        for k in range(self.tabs.count()):
            self.cmb_view.addItem(self.tabs.tabText(k).replace("&&", "&"))
        self.cmb_view.currentIndexChanged.connect(self.tabs.setCurrentIndex)
        self.tabs.currentChanged.connect(self.cmb_view.setCurrentIndex)

    def _build_findings_tab(self):
        """Tab "Befunde": the list of findings, navigation between locations and the repair buttons."""
        # findings
        w = QWidget()
        lv = QVBoxLayout(w)
        # empty state: nothing to fix
        self.lbl_ready = QLabel("")
        self.lbl_ready.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_ready.setWordWrap(True)
        self.lbl_ready.hide()
        lv.addWidget(self.lbl_ready)
        # findings grouped by kind (1.20.2): group – finding – location
        self.tree = QTreeWidget()
        self.tree.setColumnCount(1)
        self.tree.setHeaderHidden(True)
        self.tree.setWordWrap(True)
        self.tree.setUniformRowHeights(False)
        self.tree.setRootIsDecorated(True)
        self.tree.setIndentation(12)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tree.header().setStretchLastSection(True)
        self.tree.header().sectionResized.connect(lambda *_a: self.tree.scheduleDelayedItemsLayout())
        self.tree.setItemDelegate(_FindingDelegate(self.tree, self._action_clicked))
        self.tree.itemClicked.connect(self._issue_clicked)
        self.tree.currentItemChanged.connect(lambda cur, _prev: self._update_nav())
        self.tree.setToolTip(
            tr("Klick: zur Fundstelle springen, nochmal: zur nächsten · ▸ aufklappen: alle Fundstellen")
        )
        lv.addWidget(self.tree, 1)
        nav = QHBoxLayout()
        self.btn_prev = QPushButton("◀")
        self.btn_next = QPushButton("▶")
        for b, d in ((self.btn_prev, -1), (self.btn_next, +1)):
            b.setFixedWidth(36)
            b.clicked.connect(lambda _c=False, d=d: self._step_spot(d))
        self.lbl_nav = QLabel("")
        self.lbl_nav.setStyleSheet(f"color: {theme.MUTED};")
        nav.addWidget(self.btn_prev)
        nav.addWidget(self.btn_next)
        nav.addWidget(self.lbl_nav, 1)
        lv.addLayout(nav)
        self._update_nav()
        self.btn_fix_all = QPushButton(tr("Alles reparieren …"))
        self.btn_fix_all.setToolTip(
            tr(
                "Alles automatisch Reparierbare für das Prüfprofil: Ebenen, Schriften, Verläufe, Sonderfarben, "
                "RGB → CMYK, Überdrucken, Anschnitt, PDF/X-4 – vorher auswählbar"
            )
        )
        self.btn_fix_all.clicked.connect(self._fix_all)
        lv.addWidget(self.btn_fix_all)
        self.btn_hdr = QPushButton(tr("HDR-Zusatzseiten entfernen …"))
        self.btn_hdr.setToolTip(
            tr("Graue Helligkeitskarten von Handy-HDR-Fotos entfernen – eine Seite je Foto, Größe wählbar")
        )
        self.btn_hdr.clicked.connect(self._fix_hdr)
        self.btn_hdr.hide()
        lv.addWidget(self.btn_hdr)
        self.tabs.addTab(w, tr("Befunde"))

    def _build_fonts_tab(self):
        """Tab "Schriften": fonts of the document with the actions to embed, replace or convert them."""
        # fonts
        w = QWidget()
        lv = QVBoxLayout(w)
        self.tbl_fonts = QTableWidget(0, 4)
        self.tbl_fonts.setHorizontalHeaderLabels([tr("Schrift"), tr("Typ"), tr("Status"), tr("Ersatz")])
        self.tbl_fonts.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl_fonts.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tbl_fonts.verticalHeader().setVisible(False)
        self.tbl_fonts.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        lv.addWidget(self.tbl_fonts, 1)
        row = QHBoxLayout()
        bf = QPushButton(tr("Schriftdatei wählen …"))
        bf.setToolTip(tr("Für die markierte Schrift eine eigene Schriftdatei als Ersatz wählen"))
        bf.clicked.connect(lambda: self._font_action("__file__"))
        bd = QPushButton(tr("Freie Schrift herunterladen …"))
        bd.setToolTip(tr("Für die markierte Schrift eine freie Schrift von fontsource.org laden"))
        bd.clicked.connect(lambda: self._font_action("__download__"))
        row.addWidget(bf)
        row.addWidget(bd)
        lv.addLayout(row)
        row = QHBoxLayout()
        b1 = QPushButton(tr("Schriften einbetten"))
        b1.setToolTip(tr("Alle Schriften einbetten, fehlende durch den gewählten Ersatz (Ghostscript)"))
        b1.clicked.connect(self._embed)
        b2 = QPushButton(tr("Text in Pfade"))
        b2.setToolTip(tr("Sieht überall gleich aus, Text ist danach aber nicht mehr durchsuchbar"))
        b2.clicked.connect(lambda: self._run(fontlib.outline_text, tr("_Pfade"), [tr("Text in Pfade umgewandelt.")]))
        row.addWidget(b1)
        row.addWidget(b2)
        lv.addLayout(row)
        self.tabs.addTab(w, tr("Schriften"))

    def _build_layers_tab(self):
        """Tab "Ebenen": layers with their visibility on screen and in print."""
        # layers
        w = QWidget()
        lv = QVBoxLayout(w)
        self.tbl_layers = QTableWidget(0, 4)
        self.tbl_layers.setHorizontalHeaderLabels([tr("Ebene"), tr("Ansicht"), tr("Druck"), tr("Hinweis")])
        self.tbl_layers.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl_layers.verticalHeader().setVisible(False)
        self.tbl_layers.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        lv.addWidget(self.tbl_layers, 1)
        b1 = QPushButton(tr("Zustand übernehmen"))
        b1.setToolTip(tr("Die gewählte Sichtbarkeit (Ansicht/Druck) ins Dokument schreiben – Ebenen bleiben erhalten"))
        b1.clicked.connect(self._layers_apply)
        b2 = QPushButton(tr("Sichtbaren Zustand festschreiben"))
        b2.setToolTip(
            tr(
                "Ausgeblendete Inhalte entfernen und Ebenen auflösen – danach druckt jeder Drucker genau "
                "das Sichtbare (Druck-Einstellung der Spalte „Druck“)"
            )
        )
        b2.clicked.connect(self._layers_flatten)
        b3 = QPushButton(tr("Markierte entfernen"))
        b3.clicked.connect(self._layers_remove)
        for b in (b1, b2, b3):
            lv.addWidget(b)
        self.tabs.addTab(w, tr("Ebenen"))

    def _build_transparency_tab(self):
        """Tab "Transparenz": where transparency occurs and how to flatten it."""
        # transparency
        w = QWidget()
        lv = QVBoxLayout(w)
        self.lbl_trans = QLabel()
        self.lbl_trans.setWordWrap(True)
        self.lbl_trans.setAlignment(Qt.AlignmentFlag.AlignTop)
        lv.addWidget(self.lbl_trans, 1)
        b = QPushButton(tr("Transparenzen reduzieren (300 dpi)"))
        b.setToolTip(tr("Für ältere Drucker/RIPs: transparente Bereiche werden gerastert (PDF 1.3)"))
        b.clicked.connect(
            lambda: self._run(fontlib.flatten_transparency, tr("_ohneTransparenz"), [tr("Transparenzen reduziert.")])
        )
        lv.addWidget(b)
        b = QPushButton(tr("Transparente Verläufe in Bilder umwandeln (300 dpi)"))
        b.setToolTip(
            tr(
                "Gegen schwarze Flächen am RIP/Plotter: nur Verläufe mit Soft-Maske werden samt Untergrund "
                "als deckendes Bild gerendert – Text und Vektoren darüber bleiben erhalten. Ohne Ghostscript."
            )
        )
        b.clicked.connect(self._flatten_softmask)
        lv.addWidget(b)
        self.btn_overprint = QPushButton(tr("Überdrucken korrigieren"))
        self.btn_overprint.setToolTip(
            tr(
                "Weiße Objekte, die überdrucken, werden auf Aussparen gestellt (sonst verschwinden sie im Druck); "
                "kleiner schwarzer Text (100 % K, bis 12 pt) wird auf Überdrucken gestellt (keine Blitzer). "
                "Nur genau diese Stellen werden geändert. Ohne Ghostscript."
            )
        )
        self.btn_overprint.setEnabled(False)
        self.btn_overprint.clicked.connect(self._fix_overprint)
        lv.addWidget(self.btn_overprint)
        self.tabs.addTab(w, tr("Transparenz"))

    def _build_images_tab(self):
        """Tab "Bilder & Farben": colour spaces and the images with their resolution."""
        # images & colours
        w = QWidget()
        lv = QVBoxLayout(w)
        self.lbl_colors = QLabel()
        self.lbl_colors.setWordWrap(True)
        self.lbl_colors.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lv.addWidget(self.lbl_colors)
        self.tbl_images = QTableWidget(0, 7)
        self.tbl_images.setHorizontalHeaderLabels(
            [
                tr("Seite"),
                tr("Pixel"),
                tr("Platziert"),
                tr("Auflösung"),
                tr("Farbraum / Profil"),
                tr("max. 300 dpi"),
                tr("max. 150 dpi"),
            ]
        )
        self.tbl_images.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.tbl_images.verticalHeader().setVisible(False)
        self.tbl_images.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_images.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl_images.setSortingEnabled(True)
        self.tbl_images.setToolTip(
            tr(
                "Auflösung = Pixel im Verhältnis zur platzierten Größe auf der Seite. "
                "Grün ab 300 dpi, gelb 150–299 dpi (Plakat/Großformat), rot darunter. "
                "Doppelklick springt zur Seite."
            )
        )
        self.tbl_images.cellDoubleClicked.connect(
            lambda r, _c: self.goto_page.emit(int(self.tbl_images.item(r, 0).data(Qt.ItemDataRole.UserRole) or 1))
        )
        lv.addWidget(self.tbl_images, 1)
        self.tabs.addTab(w, tr("Bilder & Farben").replace("&", "&&"))  # & would otherwise be a keyboard shortcut

    def _build_size_tab(self):
        """Tab "Dateigröße": what takes up the space, and the way to the shrink dialog."""
        # file size
        w = QWidget()
        lv = QVBoxLayout(w)
        self.lbl_size = QLabel()
        self.lbl_size.setWordWrap(True)
        self.lbl_size.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.lbl_size.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lv.addWidget(self.lbl_size, 1)
        b = QPushButton(tr("Datei verkleinern …"))
        b.setToolTip(tr("Verlustfrei verkleinern, optional Auflösung reduzieren – jede Maßnahme einzeln wählbar"))
        b.clicked.connect(self.shrink)
        lv.addWidget(b)
        self.tabs.addTab(w, tr("Dateigröße"))

    # ------------------------------------------------------------------ #
    def set_busy(self, text=None):
        """Show that the check is running – the old findings stay, marked as outdated."""
        self.lbl_sum.setText(text or tr("Prüfe …"))
        self.lbl_light.setStyleSheet(f"color: {theme.MUTED}; font-size: 22px;")
        if self.rep is not None:
            self.lbl_sum.setText((text or tr("Prüfe …")) + "  " + tr("(die Liste zeigt noch den alten Stand)"))

    def set_error(self, msg):
        """Show that the check failed."""
        self.lbl_sum.setText("⚠ " + msg.splitlines()[0])
        self.lbl_light.setStyleSheet(f"color: {theme.MUTED}; font-size: 22px;")

    def fill_profiles(self):
        """Fill the profile choice: built-in and own profiles, the one chosen in the settings selected."""
        from .. import checkprofile

        cur = checkprofile.chosen()
        self.cmb_profile.blockSignals(True)
        self.cmb_profile.clear()
        for p in checkprofile.all_profiles():
            self.cmb_profile.addItem(p.title(), p.name)
            info = checkprofile.describe(p)["description"]
            if info:
                self.cmb_profile.setItemData(self.cmb_profile.count() - 1, info, Qt.ItemDataRole.ToolTipRole)
        i = self.cmb_profile.findData(cur)
        self.cmb_profile.setCurrentIndex(i if i >= 0 else 0)
        self.cmb_profile.blockSignals(False)

    def _profile_chosen(self, _i):
        """Another profile: save it as the chosen one and check again."""
        from .. import checkprofile, l10n

        name = self.cmb_profile.currentData()
        if not name:
            return
        s = l10n.load_settings()
        if s.get(checkprofile.SETTING) != name:
            s[checkprofile.SETTING] = name
            l10n.save_settings(s)
        self.recheck.emit()

    def set_report(self, rep: preflight.Report):
        """Show the findings of a finished check."""
        self.rep = rep
        self._last_finding = None
        c = rep.counts()
        light = theme.ERROR if c["error"] else theme.WARN if c["warning"] else theme.OK
        self.lbl_light.setStyleSheet(f"color: {light}; font-size: 22px;")
        if not rep.issues:
            self.lbl_sum.setText("✓ " + tr("Keine Probleme gefunden."))
        elif not c["error"] and not c["warning"]:
            self.lbl_sum.setText(tr("Druckbereit – {0} Hinweis(e)").format(c["info"]))
        else:  # short, so that it fits the narrow sidebar: only what is there
            parts = [
                txt.format(n)
                for n, txt in (
                    (c["error"], tr("{0} Fehler")),
                    (c["warning"], tr("{0} Warnung(en)")),
                    (c["info"], tr("{0} Hinweis(e)")),
                )
                if n
            ]
            self.lbl_sum.setText(" · ".join(parts))
        prof = getattr(rep, "profile", None)
        if prof is not None:
            i = self.cmb_profile.findData(prof.name)
            if i < 0:  # e.g. chosen in another window meanwhile, or a new own profile
                self.fill_profiles()
                i = self.cmb_profile.findData(prof.name)
            if i >= 0 and i != self.cmb_profile.currentIndex():
                self.cmb_profile.blockSignals(True)
                self.cmb_profile.setCurrentIndex(i)
                self.cmb_profile.blockSignals(False)
            self.lbl_sum.setToolTip(
                tr("Prüfprofil: {0} · {1} Prüfung(en) ohne Befund").format(prof.title(), len(rep.passed or []))
            )
        self._fill_findings(rep)
        self.btn_hdr.setVisible(bool(getattr(rep, "hdr", None)))
        # fonts
        st = {
            "ok": tr("eingebettet"),
            "std14": tr("Standard, nicht eingebettet"),
            "missing": tr("NICHT eingebettet"),
            "type3": "Type3",
        }
        self.tbl_fonts.setRowCount(0)
        self.font_map = {}
        for f in rep.fonts:
            r = self.tbl_fonts.rowCount()
            self.tbl_fonts.insertRow(r)
            self.tbl_fonts.setItem(r, 0, QTableWidgetItem(f.name + (tr(" (Teilmenge)") if f.subset else "")))
            self.tbl_fonts.setItem(r, 1, QTableWidgetItem(f.subtype))
            s_item = QTableWidgetItem(st[f.status])
            if f.status == "missing":
                s_item.setForeground(QBrush(QColor(theme.ERROR)))
            self.tbl_fonts.setItem(r, 2, s_item)
            if f.status in ("missing", "std14"):
                cb = QComboBox()
                cb.addItem(f.suggestion_name or tr("(kein Ersatz)"), f.suggestion)
                cb.addItem(tr("Schriftdatei wählen …"), "__file__")
                cb.addItem(tr("Freie Schrift herunterladen …"), "__download__")
                cb.setProperty("font_name", f.name)  # not "font": that is a built-in property of every widget (QFont)
                cb.activated.connect(lambda _i=0, c=cb: self._font_choice(c))
                self.tbl_fonts.setCellWidget(r, 3, cb)
                if f.suggestion:
                    self.font_map[f.name] = f.suggestion
            else:
                self.tbl_fonts.setItem(r, 3, QTableWidgetItem("–"))
        # layers
        self.tbl_layers.setRowCount(0)
        for L in rep.layers:
            r = self.tbl_layers.rowCount()
            self.tbl_layers.insertRow(r)
            it = QTableWidgetItem(L.name)
            it.setData(Qt.ItemDataRole.UserRole, L.key)
            self.tbl_layers.setItem(r, 0, it)
            for col_i, on in ((1, L.view_on), (2, L.view_on if L.print_on is None else L.print_on)):
                c = QCheckBox()
                c.setChecked(bool(on))
                wrap = QWidget()
                hl = QHBoxLayout(wrap)
                hl.setContentsMargins(0, 0, 0, 0)
                hl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                hl.addWidget(c)
                self.tbl_layers.setCellWidget(r, col_i, wrap)
            note = []
            if L.outside_pct is not None and L.outside_pct > 25:
                note.append(tr("{0:.0f} % außerhalb").format(L.outside_pct))
            if not L.pages:
                note.append(tr("leer"))
            self.tbl_layers.setItem(r, 3, QTableWidgetItem(", ".join(note)))
        if not rep.layers:
            self.tbl_layers.setRowCount(0)
        # transparency
        if rep.transparency:
            lines = []
            for p, kinds in sorted(rep.transparency.items())[:60]:
                lines.append(tr("Seite {0}: {1}").format(p, ", ".join(tr(KIND_TEXT[k]) for k in sorted(kinds))))
        else:
            lines = [tr("Keine Transparenzen gefunden.")]
        lines += overprint_lines(rep)
        self.lbl_trans.setText("\n".join(lines))
        self.btn_overprint.setEnabled(bool(overprint_counts(rep)))
        self._fill_colors(rep)
        if rep.size is not None:
            from .. import shrink

            self.lbl_size.setText("\n".join(shrink.summary_lines(rep.size, top=8)))
        else:
            self.lbl_size.setText("")

    def _fix_for(self, check: str):
        """(button text, tooltip, action) of the repair that belongs to a finding – or None."""
        fixes = {
            "font_missing": (tr("Einbetten …"), tr("Fehlende Schriften mit Ersatz einbetten"), self._embed),
            "font_std14": (tr("Einbetten …"), tr("Fehlende Schriften mit Ersatz einbetten"), self._embed),
            "layer_hidden": (
                tr("Festschreiben …"),
                tr("Ebenen festschreiben (wie am Bildschirm oder beim Druck)"),
                self._layers_flatten,
            ),
            "layer_print": (
                tr("Festschreiben …"),
                tr("Ebenen festschreiben (wie am Bildschirm oder beim Druck)"),
                self._layers_flatten,
            ),
            "transparency_gradient": (
                tr("Umwandeln …"),
                tr("Transparente Verläufe in deckende Bilder umwandeln"),
                self._flatten_softmask,
            ),
            "overprint_white": (tr("Korrigieren"), tr("Überdrucken korrigieren"), self._fix_overprint),
            "overprint_black_text": (tr("Korrigieren"), tr("Überdrucken korrigieren"), self._fix_overprint),
            "hdr": (tr("Entfernen …"), tr("HDR-Zusatzseiten entfernen …"), self._fix_hdr),
            "file_size": (tr("Verkleinern …"), tr("Datei verkleinern …"), self.shrink),
            "image_high": (tr("Verkleinern …"), tr("Datei verkleinern …"), self.shrink),
            "bleed": (tr("Anschnitt …"), tr("Anschnitt erzeugen …"), lambda: self.tool_requested.emit("bleed")),
            "rgb": (tr("Farbregeln …"), tr("Farbregeln …"), lambda: self.tool_requested.emit("colorrules")),
            "spot_count": (tr("Farbregeln …"), tr("Farbregeln …"), lambda: self.tool_requested.emit("colorrules")),
        }
        return fixes.get(check)

    def _action_clicked(self, index):
        """Repair link of a finding row."""
        it = self.tree.itemFromIndex(index)
        fix = self._fix_for(it.data(0, ROLE_FIX) or "") if it is not None else None
        if fix is not None:
            fix[2]()

    def _fill_findings(self, rep):
        """Findings grouped by kind, groups with errors first – those open, the others closed, so that the list of
        groups is the overview also in the narrow sidebar; under a finding every location; at the end the checks of
        the profile without a finding. Nothing to fix: the empty state "Druckbereit"."""
        from .. import checkprofile
        from .icons import icon as svg_icon

        self.tree.clear()
        groups: dict = {}
        for i in rep.issues:
            groups.setdefault(i.category, []).append(i)
        order = sorted(groups, key=lambda k: (min(SEV_RANK[i.severity] for i in groups[k]), k))
        for cat in order:
            items = sorted(groups[cat], key=lambda i: SEV_RANK[i.severity])
            worst = items[0].severity
            g = QTreeWidgetItem([tr(CAT_TEXT.get(cat, cat))])
            g.setData(0, ROLE_KIND, "group")
            g.setData(0, ROLE_COUNT, len(items))
            g.setData(0, ROLE_SEV, SEV_COLOR[worst])
            if cat in CAT_ICON:
                g.setIcon(0, svg_icon(CAT_ICON[cat]))
            f = g.font(0)
            f.setBold(True)
            g.setFont(0, f)
            g.setToolTip(0, tr("{0} Befund(e)").format(len(items)))
            self.tree.addTopLevelItem(g)
            for i in items:
                spots = list(getattr(i, "spots", None) or [preflight.Spot(p) for p in i.pages])
                key = getattr(i, "check", "")
                spec = checkprofile.CHECKS.get(key)
                title = tr(SEV_TEXT[i.severity]) + " · " + (tr(spec[2]) if spec else tr(CAT_TEXT.get(cat, cat)))
                it = QTreeWidgetItem([title])
                it.setData(0, ROLE_KIND, "finding")
                it.setData(0, ROLE_DETAIL, i.message)
                it.setData(0, ROLE_SEV, i.severity)
                it.setData(0, ROLE_FIX, key)
                if i.pages:
                    it.setData(0, ROLE_PAGES, tr("S. {0}").format(preflight._pages_str(i.pages)))
                fix = self._fix_for(key)
                if fix is not None:
                    it.setData(0, ROLE_ACTION, fix[0])
                it.setData(0, Qt.ItemDataRole.UserRole, spots)
                it.setData(1, Qt.ItemDataRole.UserRole, 0)  # current location (for ◀ ▶)
                it.setToolTip(0, i.message + (("\n\n→ " + fix[1]) if fix is not None else ""))
                g.addChild(it)
                if len(spots) > 1 or (spots and (spots[0].box is not None or spots[0].label)):
                    for k, sp in enumerate(spots[:500]):
                        ch = QTreeWidgetItem([preflight.where_text(rep, sp)])
                        ch.setData(0, ROLE_KIND, "spot")
                        ch.setData(0, Qt.ItemDataRole.UserRole, [sp])
                        ch.setData(1, Qt.ItemDataRole.UserRole, k)
                        ch.setToolTip(0, preflight.where_text(rep, sp))
                        it.addChild(ch)
            g.setExpanded(worst == "error")
        passed = list(getattr(rep, "passed", None) or [])
        if passed:
            g = QTreeWidgetItem(["✓ " + tr("Ohne Befund")])
            g.setData(0, ROLE_KIND, "group")
            g.setData(0, ROLE_COUNT, len(passed))
            g.setData(0, ROLE_SEV, theme.OK)
            g.setForeground(0, QBrush(QColor(theme.OK)))
            g.setToolTip(0, tr("Prüfungen des Profils, die nichts gefunden haben"))
            self.tree.addTopLevelItem(g)
            for key in passed:
                spec = checkprofile.CHECKS.get(key)
                ch = QTreeWidgetItem(["✓ " + (tr(spec[2]) if spec else key)])
                ch.setData(0, ROLE_KIND, "passed")
                ch.setForeground(0, QBrush(QColor(theme.MUTED)))
                g.addChild(ch)
            g.setExpanded(False)
        c = rep.counts()
        ready = not c["error"] and not c["warning"]
        if ready:
            prof = getattr(rep, "profile", None)
            sub = tr("Profil: {0}").format(prof.title()) if prof is not None else ""
            self.lbl_ready.setText(
                f'<div style="font-size:40px; color:{theme.OK};">✓</div>'
                f'<div style="font-size:16px; font-weight:bold;">{tr("Druckbereit")}</div>'
                f'<div style="color:{theme.MUTED};">{sub}</div>'
            )
        self.lbl_ready.setVisible(ready)

    def shrink(self):
        """Dialog with breakdown and switches; runs as its own process (large files)."""
        from .shrinkdialog import ShrinkDialog

        fn = self.file_fn or self.data_fn
        if fn is None:
            return
        data = fn()
        rep = (
            self.rep.size
            if self.rep is not None and self.rep.size is not None and self.rep.size.size == len(data)
            else None
        )
        dlg = ShrinkDialog(self, rep, data)
        if dlg.exec():
            self._job_data = data
            self.job_requested.emit("shrink", dlg.options(), tr("_klein"), tr("Datei verkleinern"))
            self._job_data = None

    def take_job_data(self):
        """For the job: exactly the bytes that the dialog analysed."""
        return self._job_data

    def _fill_colors(self, rep):
        """Tab "Bilder & Farben": colour spaces per page, output profile, page limits and image table."""
        from .. import imagecheck as ic

        cr = getattr(rep, "colors", None)
        self.tbl_images.setSortingEnabled(False)
        self.tbl_images.setRowCount(0)
        if cr is None:
            self.lbl_colors.setText(tr("Keine Angaben."))
            return
        lines = preflight.colors_text(rep)
        lim = ic.page_limits(cr)
        for p in sorted(lim)[:30]:
            dpi, f300, f150 = lim[p]
            ps = cr.page_size_mm.get(p, (0, 0))
            if f300 < 0.995:
                lines.append(
                    tr(
                        "Seite {0}: niedrigste Bildauflösung {1:.0f} dpi – höchstens {2:.0f} % ({3:.0f} × {4:.0f} mm) "
                        "bei 300 dpi, {5:.0f} % ({6:.0f} × {7:.0f} mm) bei 150 dpi"
                    ).format(
                        p,
                        dpi,
                        f300 * 100,
                        ps[0] * f300,
                        ps[1] * f300,
                        min(f150, 9.99) * 100,
                        ps[0] * min(f150, 9.99),
                        ps[1] * min(f150, 9.99),
                    )
                )
            else:
                lines.append(
                    tr(
                        "Seite {0}: niedrigste Bildauflösung {1:.0f} dpi – in Originalgröße gut; für "
                        "Plakat/Großformat (150 dpi) bis {2:.0f} % vergrößerbar"
                    ).format(p, dpi, min(f150, 9.99) * 100)
                )
        if not cr.images:
            lines.append(tr("Keine Bilder."))
        if cr.truncated:
            lines.append(tr("(Nur die ersten {0} Bildplatzierungen ausgewertet.)").format(len(cr.images)))
        self.lbl_colors.setText("\n".join(lines))
        col = {"good": QColor(theme.OK), "ok": QColor(theme.ACCENT), "low": QColor(theme.ERROR)}

        self.tbl_images.setRowCount(len(cr.images))
        for r, u in enumerate(cr.images):
            a, b = u.max_mm(u.good), u.max_mm(u.ok)
            pg = QTableWidgetItem()
            pg.setData(Qt.ItemDataRole.DisplayRole, u.page)
            pg.setData(Qt.ItemDataRole.UserRole, u.page)
            self.tbl_images.setItem(r, 0, pg)
            self.tbl_images.setItem(r, 1, QTableWidgetItem(f"{u.px[0]} × {u.px[1]}"))
            self.tbl_images.setItem(r, 2, QTableWidgetItem(f"{u.placed_mm[0]:.0f} × {u.placed_mm[1]:.0f} mm"))
            d = QTableWidgetItem()
            d.setData(Qt.ItemDataRole.DisplayRole, round(u.dpi))
            rating = preflight._rate(rep, u)
            if rating in col:
                d.setForeground(QBrush(col[rating]))
            if u.bits == 1:
                d.setToolTip(tr("Strichbild (1 Bit): gut ab 600 dpi, ausreichend ab 300 dpi"))
            self.tbl_images.setItem(r, 3, d)
            sp = ic.space_label(u.space) + (f" – {u.profile}" if u.profile else "") + f"  ·  {u.codec}"
            it = QTableWidgetItem(sp)
            it.setToolTip(sp)
            self.tbl_images.setItem(r, 4, it)
            self.tbl_images.setItem(r, 5, QTableWidgetItem(f"{a[0]:.0f} × {a[1]:.0f} mm"))
            self.tbl_images.setItem(r, 6, QTableWidgetItem(f"{b[0]:.0f} × {b[1]:.0f} mm"))
        self.tbl_images.setSortingEnabled(True)
        self.tbl_images.resizeColumnsToContents()

    # ------------------------------------------------------------------ #
    def _issue_clicked(self, it, _col):
        """Finding: jump to the (current) location – clicked again: to the next one; location: exactly there;
        group: open/close."""
        kind = it.data(0, ROLE_KIND)
        if kind == "group":
            it.setExpanded(not it.isExpanded())
            return
        spots = it.data(0, Qt.ItemDataRole.UserRole) or []
        if not spots:
            return
        if kind == "spot":  # remember as the current location of the finding
            it.parent().setData(1, Qt.ItemDataRole.UserRole, int(it.data(1, Qt.ItemDataRole.UserRole) or 0))
            self._last_finding = it.parent()
            self._go(spots[0])
        elif it is self._last_finding and len(spots) > 1:
            self._step_spot(+1)
            return
        else:
            self._last_finding = it
            k = int(it.data(1, Qt.ItemDataRole.UserRole) or 0)
            self._go(spots[min(k, len(spots) - 1)])
        self._update_nav()

    def _go(self, sp):
        self.goto_spot.emit(int(sp.page), sp.box)

    def _top(self):
        """The finding of the current row (also from one of its locations)."""
        it = self.tree.currentItem()
        if it is None:
            return None
        kind = it.data(0, ROLE_KIND)
        if kind == "spot":
            return it.parent()
        return it if kind == "finding" else None

    def _step_spot(self, d: int):
        top = self._top()
        if top is None:
            return
        spots = top.data(0, Qt.ItemDataRole.UserRole) or []
        if not spots:
            return
        k = (int(top.data(1, Qt.ItemDataRole.UserRole) or 0) + d) % len(spots)
        top.setData(1, Qt.ItemDataRole.UserRole, k)
        if k < top.childCount():
            self.tree.blockSignals(True)
            self.tree.setCurrentItem(top.child(k))
            self.tree.blockSignals(False)
        self._go(spots[k])
        self._update_nav()

    def _update_nav(self):
        top = self._top()
        spots = (top.data(0, Qt.ItemDataRole.UserRole) or []) if top is not None else []
        many = len(spots) > 1
        self.btn_prev.setEnabled(many)
        self.btn_next.setEnabled(many)
        if not spots:
            self.lbl_nav.setText(tr("Befund anklicken – springt zur Stelle"))
        else:
            k = int(top.data(1, Qt.ItemDataRole.UserRole) or 0)
            self.lbl_nav.setText(tr("Fundstelle {0}/{1}").format(min(k, len(spots) - 1) + 1, len(spots)))

    def _layer_states(self):
        st = {}
        for r in range(self.tbl_layers.rowCount()):
            key = self.tbl_layers.item(r, 0).data(Qt.ItemDataRole.UserRole)
            view = self.tbl_layers.cellWidget(r, 1).findChild(QCheckBox).isChecked()
            prn = self.tbl_layers.cellWidget(r, 2).findChild(QCheckBox).isChecked()
            st[key] = (view, prn)
        return st

    def _layers_apply(self):
        if not self.rep or not self.rep.layers:
            return
        st = self._layer_states()
        self._run(lambda d: pdflayers.set_layer_states(d, st), tr("_Ebenen"), [tr("Ebenen-Zustand übernommen.")])

    def _ask_basis(self, states) -> str | None:
        """If view and print differ, ask which state is made permanent."""
        diff = [
            self.tbl_layers.item(r, 0).text()
            for r in range(self.tbl_layers.rowCount())
            if states[self.tbl_layers.item(r, 0).data(Qt.ItemDataRole.UserRole)][0]
            != states[self.tbl_layers.item(r, 0).data(Qt.ItemDataRole.UserRole)][1]
        ]
        if not diff:
            return "print"
        box = QMessageBox(
            QMessageBox.Icon.Question,
            tr("Ebenen festschreiben"),
            tr(
                "Bei diesen Ebenen unterscheiden sich Ansicht und Druck:\n{0}\n\n"
                "Welcher Zustand soll festgeschrieben werden?"
            ).format("\n".join("• " + d for d in diff)),
            parent=self,
        )
        b_print = box.addButton(tr("Wie beim Druck"), QMessageBox.ButtonRole.AcceptRole)
        b_view = box.addButton(tr("Wie am Bildschirm"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(b_print)
        box.exec()
        if box.clickedButton() is b_print:
            return "print"
        if box.clickedButton() is b_view:
            return "view"
        return None

    def _layers_flatten(self):
        if not self.rep or not self.rep.layers:
            return
        st = self._layer_states()
        basis = self._ask_basis(st)
        if basis is None:
            return
        vis = {k for k, (v, p) in st.items() if (p if basis == "print" else v)}
        self._run(
            lambda d: pdflayers.flatten_layers(d, vis),
            tr("_festgeschrieben"),
            [tr("Ebenen festgeschrieben – es wird genau das Sichtbare gedruckt.")],
        )

    def _layers_remove(self):
        rows = {i.row() for i in self.tbl_layers.selectedIndexes()}
        if not rows:
            QMessageBox.information(self, tr("Ebenen"), tr("Bitte zuerst Ebenen in der Liste markieren."))
            return
        keys = {self.tbl_layers.item(r, 0).data(Qt.ItemDataRole.UserRole) for r in rows}
        self._run(
            lambda d: pdflayers.remove_layers(d, keys), tr("_Ebenen"), [tr("{0} Ebene(n) entfernt.").format(len(keys))]
        )

    def _font_action(self, what):
        """Buttons below the table: act on the highlighted row."""
        row = self.tbl_fonts.currentRow()
        cb = self.tbl_fonts.cellWidget(row, 3) if row >= 0 else None
        if not isinstance(cb, QComboBox):
            QMessageBox.information(
                self, tr("Schriften"), tr("Bitte zuerst eine nicht eingebettete Schrift in der Liste markieren.")
            )
            return
        i = cb.findData(what)
        if i >= 0:
            cb.setCurrentIndex(i)
        self._font_choice(cb)

    def _font_choice(self, cb):
        try:
            self._font_choice_inner(cb)
        except Exception as e:  # noqa: BLE001 – shown to the user
            box = QMessageBox(QMessageBox.Icon.Critical, tr("Fehler"), str(e), parent=self)
            box.setDetailedText(traceback.format_exc())
            box.exec()

    def _font_choice_inner(self, cb):
        name = cb.property("font_name")
        what = cb.currentData()
        if what == "__file__":
            p, _ = lastdir.getOpenFileName(
                self, tr("Schriftdatei wählen"), "", tr("Schriften (*.ttf *.otf *.TTF *.OTF)")
            )
            cb.setCurrentIndex(0)
            if p:
                cb.setItemText(0, os.path.basename(p))
                cb.setItemData(0, p)
                self.font_map[name] = p
        elif what == "__download__":
            cb.setCurrentIndex(0)
            alt = fontlib.free_alternative(name)
            text = tr("Name der Schrift (fontsource.org, freie Lizenzen), z. B. „Roboto“:")
            if alt:
                text = (
                    tr(
                        "„{0}“ ist eine kommerzielle Schrift und kann nicht frei heruntergeladen werden.\n"
                        "Freie Alternative mit gleichen Zeichenbreiten: {1}"
                    ).format(name, alt)
                    + "\n\n"
                    + text
                )
            fam, ok = QInputDialog.getText(
                self, tr("Freie Schrift herunterladen"), text, QLineEdit.EchoMode.Normal, alt
            )
            while ok and fam.strip():
                QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                try:
                    paths, used = fontlib.download_font(fam.strip())
                except fontlib.FontNotFound as e:
                    QApplication.restoreOverrideCursor()
                    if e.suggestions:
                        fam, ok = QInputDialog.getItem(
                            self,
                            tr("Freie Schrift herunterladen"),
                            str(e) + "\n\n" + tr("Stattdessen laden:"),
                            e.suggestions,
                            0,
                            False,
                        )
                        continue
                    QMessageBox.warning(self, tr("Herunterladen"), str(e))
                    return
                except Exception as e:  # noqa: BLE001 – shown to the user
                    QApplication.restoreOverrideCursor()
                    QMessageBox.warning(self, tr("Herunterladen"), str(e))
                    return
                QApplication.restoreOverrideCursor()
                _fam, bold, italic = fontlib.parse_font_name(name)
                pick = next((p for p in paths if ("700" in p) == bold and ("italic" in p) == italic), paths[0])
                cb.setItemText(0, f"{used} ({os.path.basename(pick)})")
                cb.setItemData(0, pick)
                self.font_map[name] = pick
                return
        elif what:
            self.font_map[name] = what

    def _no_substitute_ok(self) -> bool:
        if not self.rep:
            return True
        names = [f.name for f in self.rep.fonts if f.status == "missing" and f.name not in self.font_map]
        if not names:
            return True
        return (
            QMessageBox.question(
                self,
                tr("Schriften einbetten"),
                tr(
                    "Für diese Schriften ist kein Ersatz gewählt – Ghostscript nimmt dann eine eigene Standardschrift, "
                    "das Schriftbild ändert sich:\n{0}\n\nTrotzdem einbetten?"
                ).format("\n".join("• " + n for n in names)),
            )
            == QMessageBox.StandardButton.Yes
        )

    def _embed(self):
        if not self._no_substitute_ok():
            return
        mp = dict(self.font_map)
        self._run(
            lambda d: fontlib.embed_fonts(d, mp),
            tr("_Schriften"),
            [tr("Schriften eingebettet ({0} ersetzt).").format(len(mp))],
        )

    def _fix_all(self):
        """Repair everything that can be repaired automatically for the profile (dialog, then job autofix)."""
        if not self.rep:
            return
        from .autofixdialog import AutofixDialog

        dlg = AutofixDialog(self, self.rep)
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.chosen():
            return
        if "fonts" in dlg.chosen() and not self._no_substitute_ok():
            return
        self.job_requested.emit("autofix", dlg.settings(self.font_map), tr("_repariert"), tr("Alles reparieren"))

    def _fix_hdr(self):
        if not self.rep or not self.rep.hdr:
            return
        from .hdrdialog import hdr_options

        pages = ", ".join(str(h["aux"] + 1) for h in self.rep.hdr[:6]) + (" …" if len(self.rep.hdr) > 6 else "")
        opts = hdr_options(self, self.rep.hdr, tr("Das Dokument (Seite {0})").format(pages))
        if opts is None:
            return
        n = len(self.rep.hdr)
        self._run(
            lambda d: preflight.remove_hdr_aux(d, opts["size"], opts["merge"]),
            tr("_ohneHDR"),
            [tr("{0} HDR-Zusatzseite(n) entfernt.").format(n)],
        )

    def _flatten_softmask(self):
        """Runs as its own process (pdfium renders – not in a background thread of the interface)."""
        from ..core import PreflightFixSettings

        self.job_requested.emit(
            "preflight_fix",
            PreflightFixSettings(fix="flatten_softmask", dpi=300),
            tr("_Verlaeufe"),
            tr("Verläufe umwandeln"),
        )

    def _fix_overprint(self):
        from .. import overprint

        n = overprint_counts(self.rep) if self.rep else 0
        size = (preflight.lim(self.rep, "black_text_pt") if self.rep else 0.0) or overprint.TEXT_MAX_PT
        black = bool(self.rep is None or preflight.lim(self.rep, "black_text_pt"))  # off in the profile: only white
        self._run(
            lambda d: overprint.fix(d, black_text=black, text_max_pt=size)[0],
            tr("_Ueberdrucken"),
            [tr("Überdrucken an {0} Stelle(n) korrigiert.").format(n)],
        )

    def stop(self, wait_ms: int = 15000):
        """Wait for a running repair before the window closes (see colorpanel.stop)."""
        w = self._worker
        if w is not None and w.isRunning():
            w.wait(wait_ms)

    def _run(self, fn, suffix, notes):
        if self.data_fn is None or (self._worker is not None and self._worker.isRunning()):
            return
        data = self.data_fn()
        self.set_busy(tr("Repariere …"))
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self._worker = _Worker(fn, data)

        def done(res, err):
            QApplication.restoreOverrideCursor()
            if err:
                box = QMessageBox(QMessageBox.Icon.Critical, tr("Fehler"), err.split("\n\n")[0], parent=self)
                box.setDetailedText(err)
                box.exec()
                if self.rep:
                    self.set_report(self.rep)
                return
            if self.rep:
                self.set_report(self.rep)
            self.result_ready.emit(res, suffix, notes)

        self._worker.done.connect(done)
        self._worker.start()

    def _save_report(self):
        if not self.rep:
            return
        name = getattr(self._owner or self.window(), "display_name", "") or ""
        stem = os.path.splitext(os.path.basename(name))[0] if name else ""
        p, flt = lastdir.getSaveFileName(
            self,
            tr("Prüfbericht speichern"),
            tr("Pruefbericht") + (f"-{stem}" if stem else "") + ".pdf",
            tr("PDF mit markierten Stellen (*.pdf)") + ";;" + tr("Textdateien (*.txt)"),
        )
        if not p:
            return
        try:
            if p.lower().endswith(".txt") or (flt and "*.txt" in flt and not p.lower().endswith(".pdf")):
                with open(p, "w", encoding="utf-8") as f:
                    f.write(preflight.report_text(self.rep, name))
                return
            from .. import checkreport

            if not p.lower().endswith(".pdf"):
                p += ".pdf"
            data = self.data_fn() if self.data_fn else None
            if data is None:
                raise RuntimeError(tr("Kein Dokument geladen."))
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                checkreport.write_pdf(self.rep, data, p, name)
            finally:
                QApplication.restoreOverrideCursor()
        except Exception as e:  # noqa: BLE001 – shown to the user
            QMessageBox.critical(self, tr("Prüfbericht speichern"), str(e))
