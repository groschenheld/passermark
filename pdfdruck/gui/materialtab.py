# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Materials (papers): name, weight, surface, measured paper white, the fitting profile per printer – with
suggestions (ΔE of the paper white, surface, printer).

Two homes, same tab:
* AdminHost – Verwaltung → Standardeinstellungen → Materialien (for everybody, saved with admin rights)
* UserHost  – Farbe → Papiere und Messungen (own materials, no admin rights, saved right away)"""

from __future__ import annotations

import os
import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import colorlab, config
from ..l10n import tr
from . import theme
from .common import fill_combo

NONE = ""


class AdminHost:
    """Materials of the administration (AdminDialog: cfg, plist, new_icc, import_profile_file)."""

    user_mode = False

    def __init__(self, admin):
        self.a = admin
        self.cfg = admin.cfg
        self.cfg.setdefault("materials", [])

    @property
    def mats(self) -> list:
        """The materials in the admin configuration."""
        return self.cfg["materials"]

    def printers(self) -> list:
        """Names of the printers."""
        return [q.name for q in self.a.plist]

    def profile_items(self) -> list:
        """Colour profiles as ``(id, name)`` for combo boxes."""
        return [(p["id"], p.get("name") or p["id"]) for p in self.cfg.get("color_profiles", [])]

    def candidates(self) -> list:
        """Profiles that can be suggested for a material."""
        view = dict(self.cfg)  # newly imported profiles are still at their source
        view["color_profiles"] = [
            dict(p, file=self.a.new_icc.get(p["id"], p.get("file", ""))) for p in self.cfg.get("color_profiles", [])
        ]
        return colorlab.candidates(view)

    def take(self, cand: dict) -> str:
        """Assign a candidate -> profile id ("" = cancelled). System profiles are taken into the administration."""
        return cand["id"] or self.a.import_profile_file(cand["file"], cand["name"])

    def new_id(self, name: str) -> str:
        """Derive an unused material id from the name."""
        base = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")[:48] or "material"
        ids = {m["id"] for m in self.mats}
        mid, i = base, 2
        while mid in ids:
            mid, i = f"{base}_{i}", i + 1
        return mid

    def changed(self):
        """Called after a change; nothing to do here because the admin dialog saves."""
        pass  # saved with "Speichern" of the admin dialog


class UserHost:
    """The user's own materials (usercolor.py) – profiles: those of the administration (id) or an ICC file (path)."""

    user_mode = True

    def __init__(self, parent, cfg: dict):
        from .. import usercolor

        self.parent = parent
        self.cfg = dict(cfg or {}, _no_user_materials=True)
        self._mats = usercolor.load_materials()
        self.error = ""

    @property
    def mats(self) -> list:
        """The user's own materials."""
        return self._mats

    def printers(self) -> list:
        """Names of the printers."""
        try:
            from .. import printers

            return [p.name for p in printers.list_printers()]
        except Exception:
            return []

    def profile_items(self) -> list:
        """Administration (id) + installed profiles (path) + files already assigned."""
        items = [
            (p["id"], tr("Verwaltung: {0}").format(p.get("name") or p["id"]))
            for p in self.cfg.get("color_profiles", [])
            if p.get("file") and os.path.isfile(p["file"])
        ]
        seen = set()
        for c in colorlab.candidates(self.cfg):
            if not c["admin"]:
                seen.add(c["file"])
                items.append((c["file"], tr("System: {0}").format(c["name"])))
        for m in self._mats:
            for ref in (m.get("profiles") or {}).values():
                if os.path.isabs(ref) and ref not in seen and os.path.isfile(ref):
                    seen.add(ref)
                    items.append((ref, tr("Datei: {0}").format(colorlab.profile_desc(ref))))
        return items

    def candidates(self) -> list:
        """Profiles that can be suggested for a material."""
        return colorlab.candidates(self.cfg)

    def take(self, cand: dict) -> str:
        """Reference to store for a suggested profile: its id, otherwise its file."""
        return cand["id"] or cand["file"]

    def new_id(self, name: str) -> str:
        """Derive an unused material id from the name."""
        from .. import usercolor

        return usercolor.new_id(name, {m["id"] for m in self._mats})

    def changed(self):
        """Called after a change: save the user's materials right away."""
        from .. import usercolor

        try:
            usercolor.save_materials(self._mats)
            self.error = ""
        except (OSError, ValueError) as e:
            self.error = str(e)


class MaterialTab(QWidget):
    """List of materials with their details (paper white, surface, profiles); used by admin and user."""

    def __init__(self, admin=None, host=None):
        super().__init__()
        self.host = host or AdminHost(admin)
        self.a = admin
        self.cfg = self.host.cfg
        self._loading = False
        outer = QVBoxLayout(self)
        if not self.host.user_mode:
            note = QLabel(
                tr(
                    "Diese Papiere gelten für alle Benutzer. Eigene Papiere messen geht ohne Adminrechte "
                    "unter Farbe → Papiere und Messungen."
                )
            )
            note.setWordWrap(True)
            note.setStyleSheet(f"color: {theme.MUTED};")
            outer.addWidget(note)
        h = QHBoxLayout()
        outer.addLayout(h, 1)
        self._build_list_column(h)
        right = QVBoxLayout()
        self._build_material_box(right)
        self._build_suggestions_box(right)
        h.addLayout(right, 2)

        self.lst.currentRowChanged.connect(self._show)
        self.ed_name.editingFinished.connect(self._store)
        self.spn_weight.valueChanged.connect(self._store)
        self.cmb_surface.currentIndexChanged.connect(self._store)
        self.cmb_intent.currentIndexChanged.connect(self._store)
        self.ed_notes.textChanged.connect(self._store)
        self.cmb_for.currentIndexChanged.connect(lambda *_: self._suggest())
        self._cands = None
        self._refresh()

    def _build_list_column(self, h):
        """Left column: the list of materials with the buttons to measure, add and remove."""
        left = QVBoxLayout()
        self.btn_measure_new = QPushButton(tr("Papier messen …"))
        self.btn_measure_new.setToolTip(
            tr(
                "Neues Papier anlegen und gleich das Papierweiß bestimmen – mit Messgerät "
                "(X-Rite, über ArgyllCMS), aus einer Messdatei oder von Hand"
            )
        )
        self.btn_measure_new.clicked.connect(self._new_and_measure)
        left.addWidget(self.btn_measure_new)
        self.lst = QListWidget()
        self.lst.setToolTip(tr("Registrierte Papiere – L = gemessene Helligkeit des Papierweiß"))
        left.addWidget(self.lst, 1)
        self.lbl_empty = QLabel(
            tr(
                "Noch kein Papier angelegt.\n\n1. „Neu …“ (oder „Papier messen …“) und einen Namen "
                "vergeben, z. B. „Munken Pure 120 g“.\n2. Oberfläche wählen.\n3. Papierweiß messen "
                "oder eingeben.\n4. Unter „Vorschläge“ das passende Profil übernehmen."
            )
        )
        self.lbl_empty.setWordWrap(True)
        self.lbl_empty.setStyleSheet(f"color: {theme.ACCENT};")
        left.addWidget(self.lbl_empty)
        row = QHBoxLayout()
        for text, fn, tip in (
            (tr("Neu …"), self._new, tr("Neues Papier anlegen")),
            (tr("Kopie"), self._copy, tr("Gewähltes Papier kopieren (z. B. andere Grammatur)")),
            (tr("Entfernen"), self._delete, tr("Gewähltes Papier entfernen")),
        ):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            row.addWidget(b)
        left.addLayout(row)
        h.addLayout(left, 1)

    def _build_material_box(self, right):
        """Group "Material": name, weight, surface, paper white, rendering intent, notes and the profile per printer."""
        self.box = QGroupBox(tr("Material"))
        f = QFormLayout(self.box)
        self.ed_name = QLineEdit()
        self.ed_name.setMaxLength(64)
        f.addRow(tr("Name:"), self.ed_name)
        self.spn_weight = QSpinBox()
        self.spn_weight.setRange(0, 2000)
        self.spn_weight.setSuffix(" g/m²")
        self.spn_weight.setSpecialValueText(tr("–"))
        f.addRow(tr("Grammatur:"), self.spn_weight)
        self.cmb_surface = QComboBox()
        self.cmb_surface.setToolTip(
            tr(
                "Gestrichen (glatt, Bilderdruck) oder ungestrichen (Offset-/Naturpapier) – "
                "entscheidet, welche Profile in Frage kommen"
            )
        )
        fill_combo(self.cmb_surface, [(s, colorlab.surface_label(s)) for s in colorlab.SURFACES], "")
        f.addRow(tr("Oberfläche:"), self.cmb_surface)
        wr = QHBoxLayout()
        self.lbl_white = QLabel()
        self.lbl_white.setFont(theme.mono_font(9.5))
        wr.addWidget(self.lbl_white, 1)
        self.btn_measure = QPushButton(tr("Messen / eingeben …"))
        self.btn_measure.setToolTip(tr("Mit dem Messgerät (ArgyllCMS), aus einer Messdatei oder per Hand"))
        self.btn_measure.clicked.connect(self._measure)
        wr.addWidget(self.btn_measure)
        b = QPushButton(tr("Löschen"))
        b.setToolTip(tr("Gemessenes Papierweiß verwerfen"))
        b.clicked.connect(self._clear_white)
        wr.addWidget(b)
        f.addRow(tr("Papierweiß:"), wr)
        self.lbl_src = QLabel()
        self.lbl_src.setWordWrap(True)
        self.lbl_src.setStyleSheet(f"color: {theme.MUTED};")
        f.addRow("", self.lbl_src)
        self.cmb_intent = QComboBox()
        self.cmb_intent.setToolTip(
            tr(
                "Wie Farben außerhalb des Druckbaren behandelt werden – „Relativ farbmetrisch“ "
                "passt fast immer, „Wahrnehmungsorientiert“ für Fotos mit sehr bunten Farben"
            )
        )
        fill_combo(self.cmb_intent, [("", tr("wie beim Profil"))] + list(config.INTENTS.items()), "")
        f.addRow(tr("Render-Intent:"), self.cmb_intent)
        self.ed_notes = QPlainTextEdit()
        self.ed_notes.setMaximumHeight(60)
        self.ed_notes.setPlaceholderText(tr("z. B. Hersteller, Sorte, Lieferant, Fach"))
        f.addRow(tr("Notizen:"), self.ed_notes)

        self.tbl = QTableWidget(0, 2)
        self.tbl.setHorizontalHeaderLabels([tr("Drucker"), tr("Profil")])
        self.tbl.setToolTip(
            tr(
                "Welches Profil gilt, wenn dieses Papier auf dem Drucker liegt. „Alle Drucker“ ist die "
                "Druckbedingung für Softproof, CMYK-Umwandlung und die Druckerei."
            )
        )
        self.tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setMinimumHeight(120)
        f.addRow(tr("Profil je Drucker:"), self.tbl)
        right.addWidget(self.box)

    def _build_suggestions_box(self, right):
        """Group "Vorschläge": profiles that suit the chosen material."""
        sbox = QGroupBox(tr("Vorschläge"))
        sbox.setToolTip(
            tr(
                "Profile nach Ähnlichkeit des Papierweiß (ΔE: unter 2 kaum, über 4 deutlich sichtbar), "
                "gleicher Oberfläche und Drucker – beste zuerst"
            )
        )
        sv = QVBoxLayout(sbox)
        r = QHBoxLayout()
        r.addWidget(QLabel(tr("für:")))
        self.cmb_for = QComboBox()
        r.addWidget(self.cmb_for, 1)
        b = QPushButton(tr("Übernehmen"))
        b.setToolTip(tr("Gewähltes Profil diesem Drucker zuordnen (Standardprofile werden dabei geholt)"))
        b.clicked.connect(self._take)
        r.addWidget(b)
        sv.addLayout(r)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([tr("Profil"), tr("ΔE"), tr("Bewertung"), tr("Begründung")])
        self.tree.setRootIsDecorated(False)
        self.tree.setMinimumHeight(130)
        self.tree.itemDoubleClicked.connect(lambda *_: self._take())
        sv.addWidget(self.tree)
        self.lbl_tip = QLabel()
        self.lbl_tip.setWordWrap(True)
        self.lbl_tip.setStyleSheet(f"color: {theme.ACCENT};")
        sv.addWidget(self.lbl_tip)
        right.addWidget(sbox, 1)

    # ---------------------------------------------------------------- #
    @property
    def mats(self) -> list:
        """The materials shown."""
        return self.host.mats

    def cur(self):
        """The selected material, or None."""
        r = self.lst.currentRow()
        return self.mats[r] if 0 <= r < len(self.mats) else None

    def _printers(self) -> list:
        return self.host.printers()

    def _refresh(self, select=None):
        self.lst.blockSignals(True)
        self.lst.clear()
        for m in self.mats:
            it = QListWidgetItem(m.get("name") or m["id"])
            it.setData(Qt.ItemDataRole.UserRole, m["id"])
            self.lst.addItem(it)
            self.lst.setCurrentItem(it)
            self._item_text(m)
        self.lst.blockSignals(False)
        row = 0
        if select:
            row = next((i for i, m in enumerate(self.mats) if m["id"] == select), 0)
        self.lst.setCurrentRow(row if self.mats else -1)
        self.lbl_empty.setVisible(not self.mats)
        self.lst.setVisible(bool(self.mats))
        self._show(self.lst.currentRow())

    def _profiles(self) -> list:
        return self.host.profile_items()

    def _show(self, _row=None):
        m = self.cur()
        self.box.setEnabled(m is not None)
        self.box.setToolTip("" if m is not None else tr("Zuerst links ein Papier anlegen („Neu …“) oder wählen."))
        self._loading = True
        try:
            self.tbl.setRowCount(0)
            if m is None:
                self.ed_name.clear()
                self.lbl_white.setText("")
                self.lbl_src.setText("")
                self.tree.clear()
                self.lbl_tip.setText("")
                return
            self.ed_name.setText(m.get("name", ""))
            self.spn_weight.setValue(int(m.get("weight") or 0))
            fill_combo(
                self.cmb_surface, [(s, colorlab.surface_label(s)) for s in colorlab.SURFACES], m.get("surface", "")
            )
            fill_combo(
                self.cmb_intent, [("", tr("wie beim Profil"))] + list(config.INTENTS.items()), m.get("intent", "")
            )
            self.ed_notes.setPlainText(m.get("notes", ""))
            self._show_white(m)
            rows = [("*", tr("Alle Drucker"))] + [(q, q) for q in self._printers()]
            rows += [
                (q, q + tr(" (nicht installiert)"))
                for q in (m.get("profiles") or {})
                if q != "*" and q not in self._printers()
            ]
            profs = [(NONE, "–")] + self._profiles()
            self.tbl.setRowCount(len(rows))
            for i, (q, label) in enumerate(rows):
                lab = QLabel(label)
                lab.setContentsMargins(6, 0, 6, 0)
                self.tbl.setCellWidget(i, 0, lab)
                cb = QComboBox()
                cur = (m.get("profiles") or {}).get(q, NONE)
                items = profs if cur in [p[0] for p in profs] else profs + [(cur, tr("fehlt: {0}").format(cur))]
                fill_combo(cb, items, cur)
                cb.setProperty("printer", q)
                cb.currentIndexChanged.connect(self._store_profiles)
                self.tbl.setCellWidget(i, 1, cb)
            cur_for = self.cmb_for.currentData()
            self.cmb_for.blockSignals(True)
            fill_combo(self.cmb_for, rows, cur_for if cur_for in [r[0] for r in rows] else "*")
            self.cmb_for.blockSignals(False)
        finally:
            self._loading = False
        self._suggest()

    def _show_white(self, m):
        w = m.get("white")
        self.lbl_white.setText(colorlab.fmt_lab(w) if w else tr("nicht gemessen"))
        self.lbl_src.setText(
            m.get("white_source", "")
            if w
            else tr("Ohne gemessenes Papierweiß gibt es nur Vorschläge nach Oberfläche und Drucker.")
        )

    def _store(self, *_):
        if self._loading:
            return
        m = self.cur()
        if m is None:
            return
        m["name"] = self.ed_name.text().strip()[:64] or m["id"]
        m["weight"] = int(self.spn_weight.value())
        m["surface"] = self.cmb_surface.currentData() or ""
        m["intent"] = self.cmb_intent.currentData() or ""
        m["notes"] = self.ed_notes.toPlainText()[:2000]
        self._item_text(m)
        self.host.changed()
        if self.sender() is self.cmb_surface:
            self._suggest()

    def _item_text(self, m):
        it = self.lst.currentItem()
        if it is None:
            return
        extra = []
        if m.get("weight"):
            extra.append(f"{m['weight']} g/m²")
        if m.get("white"):
            extra.append("L {:.0f}".format(m["white"][0]))
        it.setText((m.get("name") or m["id"]) + (f"  ({', '.join(extra)})" if extra else ""))

    def _store_profiles(self, *_):
        if self._loading:
            return
        m = self.cur()
        if m is None:
            return
        prof = {}
        for i in range(self.tbl.rowCount()):
            cb = self.tbl.cellWidget(i, 1)
            if cb is not None and cb.currentData():
                prof[cb.property("printer")] = cb.currentData()
        m["profiles"] = prof
        self.host.changed()

    # ---------------------------------------------------------------- #
    def _new_id(self, name: str) -> str:
        return self.host.new_id(name)

    def _new(self) -> dict | None:
        name, ok = QInputDialog.getText(self, tr("Neues Material"), tr("Name (z. B. „Munken Pure 120 g“):"))
        if not ok or not name.strip():
            return None
        m = colorlab.new_material(self._new_id(name.strip()), name.strip()[:64])
        m["surface"] = colorlab.guess_surface(name)
        w = re.search(r"(\d{2,4})\s*g", name)
        if w:
            m["weight"] = min(2000, int(w.group(1)))
        self.mats.append(m)
        self.host.changed()
        self._refresh(m["id"])
        return m

    def _new_and_measure(self):
        m = self.cur()
        if m is None or m.get("white"):
            m = self._new()
        if m is not None:
            self._measure()

    def _copy(self):
        m = self.cur()
        if m is None:
            return
        import copy

        n = copy.deepcopy(m)
        n["name"] = (m.get("name") or m["id"])[:56] + tr(" (Kopie)")
        n["id"] = self._new_id(n["name"])
        self.mats.append(n)
        self.host.changed()
        self._refresh(n["id"])

    def _delete(self):
        m = self.cur()
        if m is None:
            return
        if (
            QMessageBox.question(
                self, tr("Material entfernen"), tr("„{0}“ entfernen?").format(m.get("name") or m["id"])
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.mats.remove(m)
        self.host.changed()
        self._refresh()

    def _measure(self):
        from .measuredialog import MeasureDialog

        m = self.cur()
        if m is None:
            return
        dlg = MeasureDialog(self, m.get("name", ""), m.get("white"))
        if not dlg.exec():
            return
        lab = dlg.result_lab()
        if lab is None:
            return
        m["white"] = [round(float(x), 2) for x in lab]
        m["white_source"] = dlg.result_source()
        self.host.changed()
        self._show_white(m)
        self._refresh(m["id"])

    def _clear_white(self):
        m = self.cur()
        if m is None:
            return
        m["white"], m["white_source"] = None, ""
        self.host.changed()
        self._refresh(m["id"])

    # ---------------- suggestions ---------------- #
    def candidates(self) -> list:
        """Profiles that can be suggested, including standard profiles not installed yet (cached)."""
        if self._cands is None:
            cands = self.host.candidates()
            self._cands = cands + colorlab.standard_candidates([c["file"] for c in cands])
        return self._cands

    def invalidate(self):
        """Profiles changed (import/remove/standard profile downloaded)."""
        self._cands = None
        if self.isVisible():
            self._show()

    def _suggest(self):
        self.tree.clear()
        m = self.cur()
        if m is None:
            self.lbl_tip.setText("")
            return
        q = self.cmb_for.currentData() or "*"
        res = colorlab.suggest(m, self.candidates(), "" if q == "*" else q, limit=8)
        for r in res:
            prefix = "" if r["admin"] else (tr("Standard: ") if r.get("std") else tr("System: "))
            it = QTreeWidgetItem(
                [prefix + r["name"], "–" if r["de"] is None else f"{r['de']:.1f}", r["verdict"], r["why"]]
            )
            it.setData(0, Qt.ItemDataRole.UserRole, r)
            it.setToolTip(0, r["file"] or tr("Wird beim Übernehmen von registry.color.org geholt"))
            it.setToolTip(3, r["why"])
            if r.get("std"):
                it.setForeground(0, self.palette().placeholderText())
            self.tree.addTopLevelItem(it)
        for c in range(3):
            self.tree.resizeColumnToContents(c)
        if res:
            self.tree.setCurrentItem(self.tree.topLevelItem(0))
        best = next((r for r in res if not r.get("std")), None)
        self.lbl_tip.setText(colorlab.standard_tip(m, best))

    def _fetch_standard(self, key: str) -> str:
        from .. import usercolor

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            return usercolor.download_standard(key)
        except Exception as e:  # noqa: BLE001 – Netz, Proxy, Antwort
            QMessageBox.warning(
                self,
                tr("Standardprofil"),
                tr(
                    "Konnte das Profil nicht holen: {0}\n\nOhne Internet: die Datei {1}.icc von registry.color.org auf "
                    "einem anderen Rechner laden und unter „Profil je Drucker“ bzw. im Admin unter Farbprofile "
                    "einbinden."
                ).format(e, key),
            )
            return ""
        finally:
            QApplication.restoreOverrideCursor()

    def _take(self):
        m = self.cur()
        it = self.tree.currentItem()
        if m is None or it is None:
            return
        r = dict(it.data(0, Qt.ItemDataRole.UserRole))
        if r.get("std"):
            path = self._fetch_standard(r["std"])
            if not path:
                return
            r["file"] = path
            from .. import colorlab as _cl

            r["name"] = _cl.profile_desc(path)
        ref = self.host.take(r)
        if not ref:
            return
        self._cands = None
        q = self.cmb_for.currentData() or "*"
        m.setdefault("profiles", {})[q] = ref
        if not m.get("intent") and r["space"] == "CMYK":
            m["intent"] = "relative"
        self.host.changed()
        self._show()
