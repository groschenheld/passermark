# SPDX-License-Identifier: GPL-3.0-or-later
"""Farbpipette (1.18.14): kleines Werkzeugfenster neben der Seite.

Klick auf die Seite -> definierte Farbe (RGB/CMYK/Grau/Sonderfarbe/Bildpixel), Farbauftrag im Druck je Kanal und
gesamt (mit dem Profil der Druckbedingung), Bildschirmfarbe. Die Farbe lässt sich als CMYK oder RGB übernehmen –
sie steht dann in „Farbe …“ beim Bearbeiten bereit.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QFormLayout, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout)

from .. import colorcheck, colorlab, pipette
from ..l10n import tr
from . import theme
from .common import fill_combo


class _Worker(QThread):
    done = Signal(object, str)

    def __init__(self, data, page, x, y, target, password):
        super().__init__()
        self.args = (data, page, x, y, target, password)

    def run(self):
        data, page, x, y, target, password = self.args
        try:
            self.done.emit(pipette.sample(data, page, x, y, target, password), "")
        except Exception as e:                                 # noqa: BLE001
            self.done.emit(None, str(e))


class PipetteDialog(QDialog):
    picked = Signal(str, object)          # ("cmyk" | "rgb", Werte 0..1)
    closed = Signal()

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle(tr("Farbpipette"))
        self.setWindowFlag(Qt.WindowType.Tool, True)
        self.setModal(False)
        self._worker = None
        self._pending = None
        self.sample = None
        v = QVBoxLayout(self)
        f = QFormLayout()
        self.cmb = QComboBox()
        self.cmb.setToolTip(tr("Druckbedingung (Material oder CMYK-Profil): damit wird der Farbauftrag gerechnet – "
                               "wie bei Farbprüfung und Softproof"))
        f.addRow(tr("Druckbedingung:"), self.cmb)
        v.addLayout(f)
        top = QHBoxLayout()
        self.swatch = QFrame()
        self.swatch.setFixedSize(56, 56)
        self.swatch.setFrameShape(QFrame.Shape.Box)
        top.addWidget(self.swatch)
        self.lbl_where = QLabel(tr("Auf die Seite klicken, um eine Farbe zu messen. Esc = beenden."))
        self.lbl_where.setWordWrap(True)
        top.addWidget(self.lbl_where, 1)
        v.addLayout(top)
        g = QFormLayout()
        self.lbl_obj = QLabel("–")
        self.lbl_def = QLabel("–")
        self.lbl_ink = QLabel("–")
        self.lbl_total = QLabel("–")
        self.lbl_screen = QLabel("–")
        for lb in (self.lbl_obj, self.lbl_def, self.lbl_ink, self.lbl_total, self.lbl_screen):
            lb.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lb.setWordWrap(lb not in (self.lbl_ink, self.lbl_def))   # Werte nie umbrechen/abschneiden
        self.lbl_ink.setFont(theme.mono_font(10))
        self.lbl_def.setFont(theme.mono_font(10))
        g.addRow(tr("Objekt:"), self.lbl_obj)
        g.addRow(tr("Im PDF:"), self.lbl_def)
        g.addRow(tr("Im Druck:"), self.lbl_ink)
        g.addRow(tr("Farbauftrag:"), self.lbl_total)
        g.addRow(tr("Bildschirm:"), self.lbl_screen)
        v.addLayout(g)
        self.lbl_note = QLabel()
        self.lbl_note.setWordWrap(True)
        self.lbl_note.setStyleSheet(f"color: {theme.MUTED};")
        v.addWidget(self.lbl_note)
        row = QHBoxLayout()
        self.btn_cmyk = QPushButton(tr("Als CMYK übernehmen"))
        self.btn_cmyk.setToolTip(tr("CMYK-Werte merken – definiertes CMYK bzw. bei RGB der Farbauftrag im Druck. "
                                    "Steht danach bei Bearbeiten → „Farbe …“ bereit."))
        self.btn_cmyk.clicked.connect(lambda: self._take("cmyk"))
        self.btn_rgb = QPushButton(tr("Als RGB übernehmen"))
        self.btn_rgb.setToolTip(tr("RGB-Werte merken – definiertes RGB bzw. die angezeigte Farbe"))
        self.btn_rgb.clicked.connect(lambda: self._take("rgb"))
        self.btn_copy = QPushButton(tr("Kopieren"))
        self.btn_copy.setToolTip(tr("Alle Werte als Text in die Zwischenablage"))
        self.btn_copy.clicked.connect(self._copy)
        for b in (self.btn_cmyk, self.btn_rgb, self.btn_copy):
            b.setEnabled(False)
            row.addWidget(b)
        v.addLayout(row)
        self._load_choices()
        self.cmb.currentIndexChanged.connect(self._choice_changed)
        from .common import responsive
        responsive(self)
        self.resize(420, 0)

    # ------------------------------------------------------------------ #
    def _load_choices(self):
        from .colorpanel import load_choice
        cfg = self._cfg()
        try:
            self.choices = [c for c in colorlab.proof_choices(cfg) if c.get("space") == "CMYK"]
        except Exception:                                      # noqa: BLE001
            self.choices = []
        saved = load_choice()
        keys = [c["key"] for c in self.choices]
        cur = saved.get("key", "") if saved.get("key", "") in keys else (keys[0] if keys else "")
        fill_combo(self.cmb, [("", tr("– ohne (nur Werte im PDF) –"))] + [(c["key"], c["label"]) for c in self.choices],
                   cur)

    def _cfg(self) -> dict:
        sess = getattr(self.win, "session", None)
        return getattr(sess, "cfg", None) or {}

    def _target(self):
        from .colorpanel import load_choice
        ch = next((c for c in self.choices if c["key"] == self.cmb.currentData()), None)
        if ch is None:
            return None
        cfg = self._cfg()
        t = colorcheck.target_from_choice(ch, cfg, load_choice().get("intent", ""))
        t.tac_limit = int(load_choice().get("tac", 0) or 0)
        return t

    def _choice_changed(self, *_):
        if self.sample is not None:
            self.measure(self.sample.page, self.sample.x, self.sample.y)

    # ------------------------------------------------------------------ #
    def measure(self, page: int, x: float, y: float):
        """Stelle messen (im Hintergrund; ein neuer Klick während des Messens wird danach gemessen)."""
        if self._worker is not None and self._worker.isRunning():
            self._pending = (page, x, y)
            return
        try:
            data = self.win._doc_bytes()
        except Exception as e:                                 # noqa: BLE001
            self.lbl_note.setText(str(e))
            return
        pw = ""                                      # _doc_bytes ist schon entschlüsselt
        from .. import l10n, measure as ms
        self.lbl_where.setText(tr("Seite {0} · x {1} mm, y {2} mm – messe …").format(
            page + 1, ms.fmt(x / 72 * 25.4, l10n.current()), ms.fmt(y / 72 * 25.4, l10n.current())))
        self._worker = _Worker(data, page, x, y, self._target(), pw)
        self._worker.done.connect(self._done)
        self._worker.start()

    def _done(self, s, err):
        if self._pending is not None:
            p, self._pending = self._pending, None
            self.measure(*p)
            return
        if s is None:
            self.lbl_note.setText(tr("Messen ging nicht: {0}").format(err))
            return
        self.sample = s
        self._show(s)

    def _show(self, s):
        from .. import l10n, measure as ms
        lang = l10n.current()
        self.lbl_where.setText(tr("Seite {0} · x {1} mm, y {2} mm").format(
            s.page + 1, ms.fmt(s.x / 72 * 25.4, lang), ms.fmt(s.y / 72 * 25.4, lang)))
        if s.screen:
            self.swatch.setStyleSheet("background: #%02x%02x%02x;" % tuple(s.screen))
        kinds = {"text": tr("Text"), "path": tr("Vektorfläche"), "image": tr("Bild"), "shading": tr("Verlauf"),
                 "form": tr("Gruppe"), "": tr("nichts – Papier")}
        obj = kinds.get(s.kind, s.kind)
        if s.kind == "path" and s.paint == "stroke":
            obj = tr("Vektorlinie (Kontur)")
        if s.detail:
            obj += " · " + s.detail
        if not s.sure:
            obj += " · " + tr("Zuordnung ungefähr")
        self.lbl_obj.setText(obj)
        defined = pipette.format_values(s)
        if s.icc:
            defined += "  (ICC)"
        self.lbl_def.setText(defined)
        if s.ink is not None:
            self.lbl_ink.setText("   ".join(f"{k} {round(v)} %" for k, v in zip("CMYK", s.ink)))
            tot = s.ink_total
            txt = tr("{0} % gesamt").format(ms.fmt(tot, lang, 0))
            if s.limit and tot > s.limit + 0.5:
                txt += " – " + tr("über dem Richtwert {0} %").format(s.limit)
                self.lbl_total.setStyleSheet(f"color: {theme.ERROR};")
            else:
                if s.limit:
                    txt += " " + tr("(Richtwert {0} %)").format(s.limit)
                self.lbl_total.setStyleSheet("")
            self.lbl_total.setText(txt + " · " + s.profile)
        else:
            self.lbl_ink.setText("–")
            self.lbl_total.setText(tr("Druckbedingung wählen, dann wird der Farbauftrag gerechnet"))
            self.lbl_total.setStyleSheet("")
        if s.screen:
            self.lbl_screen.setText("RGB {0} / {1} / {2} · #{0:02X}{1:02X}{2:02X}".format(*s.screen))
        notes = list(s.notes)
        if s.ink is not None and s.space in ("RGB", "Gray", "Lab") and s.kind:
            notes.insert(0, tr("{0} im PDF – beim Druck mit dieser Druckbedingung wird daraus der Farbauftrag oben.")
                         .format({"RGB": "RGB", "Gray": tr("Grau"), "Lab": "Lab"}[s.space]))
        if s.ink is not None and s.space in ("Separation", "DeviceN"):
            notes.insert(0, tr("Sonderfarbe: „Im Druck“ zeigt den CMYK-Ersatz – auf einer Maschine mit dieser "
                               "Sonderfarbe wird sie als eigene Farbe gedruckt."))
        if s.space == "Gray" and s.ink and (s.ink[0] + s.ink[1] + s.ink[2]) > 3:
            notes.append(tr("Grau wird hier vierfarbig aufgebaut – für reines Schwarz CMYK 0/0/0/K verwenden."))
        self.lbl_note.setText("\n".join(notes))
        self.btn_cmyk.setEnabled(s.as_cmyk() is not None)
        self.btn_rgb.setEnabled(s.as_rgb() is not None)
        self.btn_copy.setEnabled(True)
        self.adjustSize()                          # Fenster wächst mit (Hinweise, lange Profilnamen)

    def _take(self, kind: str):
        s = self.sample
        if s is None:
            return
        vals = s.as_cmyk() if kind == "cmyk" else s.as_rgb()
        if vals is None:
            return
        self.picked.emit(kind, tuple(vals))
        if kind == "cmyk":
            txt = "CMYK " + " / ".join(str(round(v * 100)) for v in vals)
        else:
            txt = "RGB " + " / ".join(str(round(v * 255)) for v in vals)
        self.lbl_note.setText(tr("Übernommen: {0} – steht bei Bearbeiten → „Farbe …“ bereit.").format(txt))

    def _copy(self):
        s = self.sample
        if s is None:
            return
        lines = [tr("Seite {0}, x {1:.1f} mm, y {2:.1f} mm").format(s.page + 1, s.x / 72 * 25.4, s.y / 72 * 25.4),
                 self.lbl_obj.text(), tr("Im PDF: {0}").format(self.lbl_def.text())]
        if s.ink is not None:
            lines.append(tr("Im Druck ({0}): C {1:.0f} % M {2:.0f} % Y {3:.0f} % K {4:.0f} % = {5:.0f} %").format(
                s.profile, *s.ink, s.ink_total))
        lines.append(tr("Bildschirm: {0}").format(self.lbl_screen.text()))
        QApplication.clipboard().setText("\n".join(lines))

    def closeEvent(self, e):
        self.closed.emit()
        super().closeEvent(e)
