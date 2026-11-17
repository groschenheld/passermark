# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Update state in the status bar of every window, the update dialog and applying an update (pdfdruck/updates.py).

One ``UpdateController`` for the whole program does the checking (in the background, at most once a day, unless
asked for in the Help menu); every main window shows its state with an ``UpdateStatus`` widget.
States: checking · available (with "Update now") · current · offline · off (switched off by the administrator).
"""

from __future__ import annotations

import os
import subprocess
import threading
import time

from PySide6.QtCore import QObject, QProcess, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, config, l10n, updates
from ..l10n import tr
from . import icons, theme

CHECKING, AVAILABLE, CURRENT, OFFLINE, OFF = "checking", "available", "current", "offline", "off"
MEMORY_KEY = "update_check"  # user settings: time and result of the last check


class UpdateController(QObject):
    """Checks for updates for the whole program and tells every window (``stateChanged``)."""

    stateChanged = Signal(str)
    _done = Signal(object, str)  # (release or None, error text) – from the worker thread

    _instance = None

    @classmethod
    def get(cls) -> UpdateController:
        """The one controller of the program."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        super().__init__()
        self.state = OFF
        self.release: updates.Release | None = None
        self._busy = False
        self._manual = False
        # queued: the result comes from the worker thread, the windows are updated in the main thread
        self._done.connect(self._finished, Qt.ConnectionType.QueuedConnection)
        self._restore()

    def _restore(self):
        """State of the last check (so that "everything up to date" shows without asking GitHub again)."""
        s = updates.settings(config.load())
        if not s["enabled"]:
            self.state = OFF
            return
        mem = l10n.load_settings().get(MEMORY_KEY) or {}
        if mem.get("version") and updates.is_newer(mem["version"]):
            self.release = updates.Release(mem["version"], "v" + mem["version"], mem.get("page", updates.RELEASES_PAGE))
            self.state = AVAILABLE
        elif mem.get("time"):
            self.state = CURRENT

    def start(self, manual: bool = False, force: bool = False):
        """Check now (``manual``: from the Help menu, answers with a message; ``force``: quietly, e.g. a click on
        the symbol in the status bar) or only if due (automatically at start, at most once a day)."""
        s = updates.settings(config.load())
        if not s["enabled"] and not manual:
            self._set(OFF)
            return
        mem = l10n.load_settings().get(MEMORY_KEY) or {}
        if self._busy or (not manual and not force and not updates.due(mem.get("time"))):
            return
        self._busy, self._manual = True, manual
        self._set(CHECKING)

        def work():
            try:
                rel = updates.check(s["channel"])
                self._done.emit(rel, "")
            except (OSError, ValueError) as e:
                self._done.emit(None, str(e) or type(e).__name__)

        threading.Thread(target=work, daemon=True, name="update-check").start()

    def _finished(self, rel, error: str):
        self._busy = False
        if error:
            self._set(OFFLINE)
            if self._manual:
                QTimer.singleShot(0, lambda: _info(tr("Keine Verbindung zu GitHub – bitte später noch einmal.")))
            return
        self.release = rel
        st = l10n.load_settings()
        st[MEMORY_KEY] = {"time": time.time(), "version": rel.version if rel else "", "page": rel.page if rel else ""}
        l10n.save_settings(st)
        self._set(AVAILABLE if rel else CURRENT)
        if self._manual:
            if rel:
                QTimer.singleShot(0, self.show_dialog)
            else:
                QTimer.singleShot(0, lambda: _info(tr("Passermark {0} ist aktuell.").format(__version__)))

    def _set(self, state: str):
        self.state = state
        self.stateChanged.emit(state)

    def show_dialog(self, parent=None):
        """The dialog about the new version (with "Update now"); ``parent`` is not used (see below)."""
        if self.release is not None:
            # without a parent: the main windows are closed before installing and would take the dialog along
            dlg = UpdateDialog(self.release)
            dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
            dlg.exec()


def _info(text: str):
    QMessageBox.information(QApplication.activeWindow(), tr("Aktualisierung"), text)


class UpdateStatus(QWidget):
    """Update state at the right of the status bar: symbol, short text, button when a version is available.
    The symbol turns while checking and carries a red "!" when a version is available; a click on it checks again."""

    ICON = 20

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(6)
        self.icon = QLabel()
        self.icon.setCursor(Qt.CursorShape.PointingHandCursor)
        self.icon.setToolTip(tr("Nochmal nach Aktualisierungen suchen"))
        self._angle = 0
        self._spin = QTimer(self)
        self._spin.setInterval(60)
        self._spin.timeout.connect(self._turn)
        self.text = QLabel()
        self.btn = QPushButton(tr("Jetzt aktualisieren"))
        self.btn.setObjectName("updateNow")
        self.btn.clicked.connect(lambda: UpdateController.get().show_dialog(self.window()))
        for w in (self.icon, self.text, self.btn):
            lay.addWidget(w)
        ctl = UpdateController.get()
        ctl.stateChanged.connect(self.show_state)
        self.show_state(ctl.state)

    def show_state(self, state: str):
        """Show one of the states (colours: accent while checking, warning yellow when available, green current)."""
        ctl = UpdateController.get()
        look = {
            CHECKING: ("update", theme.ACCENT_TEXT, tr("Suche nach Aktualisierung …")),
            AVAILABLE: (
                "update",
                theme.WARN,
                tr("Aktualisierung verfügbar: v{0}").format(ctl.release.version if ctl.release else ""),
            ),
            CURRENT: ("update", theme.OK, tr("Aktuell: v{0}").format(__version__)),  # shows which version runs
            OFFLINE: ("update", theme.MUTED, tr("Keine Verbindung")),
        }
        self.setVisible(state in look)
        if state not in look:
            self._spin.stop()
            return
        name, color, text = look[state]
        self._color = color
        self._angle = 0
        if state == CHECKING:
            self._spin.start()
        else:
            self._spin.stop()
        self.icon.setPixmap(self._symbol(state == AVAILABLE))
        self.text.setText(text)
        self.text.setStyleSheet(f"color: {color};")
        self.btn.setVisible(state == AVAILABLE)
        self.setToolTip(
            {
                CHECKING: tr("Passermark fragt bei GitHub nach einer neueren Version"),
                AVAILABLE: tr("Klicken für die Neuerungen und zum Installieren"),
                CURRENT: tr("Du hast die neueste Version ({0})").format(__version__),
                OFFLINE: tr("GitHub nicht erreichbar – ein Klick auf das Symbol versucht es erneut"),
            }[state]
        )

    def _symbol(self, mark: bool) -> QPixmap:
        """The update symbol, turned by ``self._angle``; with ``mark`` a red exclamation mark in the middle."""
        n, dpr = self.ICON, max(1.0, self.devicePixelRatioF())
        base = icons.pixmap("update", self._color, round(n * dpr))
        pm = QPixmap(base.size())
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        c = base.width() / 2
        p.translate(c, c)
        p.rotate(self._angle)
        p.translate(-c, -c)
        p.drawPixmap(0, 0, base)
        p.resetTransform()
        if mark:
            f = QFont(self.font())
            f.setBold(True)
            f.setPixelSize(round(base.height() * 0.62))
            p.setFont(f)
            p.setPen(QColor(theme.ERROR))
            p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "!")
        p.end()
        pm.setDevicePixelRatio(dpr)
        return pm

    def _turn(self):
        self._angle = (self._angle + 30) % 360
        self.icon.setPixmap(self._symbol(False))

    def mousePressEvent(self, e):
        """Click on the symbol: check again. Click on the text: available -> dialog, otherwise check again."""
        ctl = UpdateController.get()
        on_icon = self.icon.geometry().contains(e.position().toPoint())
        if ctl.state == AVAILABLE and not on_icon:
            ctl.show_dialog(self.window())
        elif ctl.state != CHECKING:
            ctl.start(force=True)
        super().mousePressEvent(e)


class UpdateDialog(QDialog):
    """What is new, and install it the way this Passermark was installed (updates.install_kind)."""

    _progress = Signal(int, int)
    _ready = Signal(str, str)  # (downloaded file, error text)
    _installed = Signal(str)  # error text of the source installation ("" = done)

    def __init__(self, release: updates.Release, parent=None):
        super().__init__(parent)
        self.release = release
        self.kind = updates.install_kind()
        self.setWindowTitle(tr("Aktualisierung auf v{0}").format(release.version))
        self.resize(560, 460)
        lay = QVBoxLayout(self)
        head = QLabel(
            tr("Passermark <b>v{0}</b> ist verfügbar (installiert: v{1}).").format(release.version, __version__)
        )
        lay.addWidget(head)
        notes = QTextBrowser()
        notes.setOpenExternalLinks(True)
        notes.setMarkdown(release.notes or tr("Keine Beschreibung."))
        lay.addWidget(notes, 1)
        self.lbl = QLabel(self._how_text())
        self.lbl.setWordWrap(True)
        lay.addWidget(self.lbl)
        self.bar = QProgressBar()
        self.bar.hide()
        lay.addWidget(self.bar)
        bb = QDialogButtonBox()
        self.btn_go = bb.addButton(tr("Jetzt aktualisieren"), QDialogButtonBox.ButtonRole.AcceptRole)
        btn_page = bb.addButton(tr("Seite öffnen"), QDialogButtonBox.ButtonRole.HelpRole)
        bb.addButton(tr("Später"), QDialogButtonBox.ButtonRole.RejectRole)
        self.btn_go.setEnabled(updates.can_apply(release, self.kind))
        self.btn_go.clicked.connect(self._go)
        btn_page.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(release.page)))
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._progress.connect(self._show_progress, Qt.ConnectionType.QueuedConnection)
        self._ready.connect(self._downloaded, Qt.ConnectionType.QueuedConnection)
        self._installed.connect(self._source_done, Qt.ConnectionType.QueuedConnection)

    def _how_text(self) -> str:
        why = updates.why_not(self.release, self.kind)
        if why == "checkout":
            return tr(
                "Passermark läuft hier nicht aus einer Installation (AppImage, Setup, install.sh), sondern z. B. "
                "aus einem Quellordner – dort bitte selbst aktualisieren (git pull)."
            )
        if why:
            # the release is incomplete: the build has not attached the file (or its checksum) yet
            return tr(
                "Zu dieser Version fehlt die Datei für diese Installation ({0}) noch – meist läuft der Build "
                "gerade. Später nochmal versuchen oder die Seite öffnen."
            ).format({"appimage": "AppImage", "windows": "Setup.exe", "source": tr("Quellpaket")}[self.kind])
        return {
            "appimage": tr("Die AppImage-Datei wird ersetzt, danach startet Passermark neu."),
            "windows": tr(
                "Das Setup läuft im Hintergrund (Windows fragt nach Administratorrechten), danach startet Passermark neu."
            ),
            "source": tr("Die Installation braucht Administratorrechte (Passwortabfrage) und dauert ein paar Minuten."),
        }.get(self.kind, "")

    def _go(self):
        if not _close_windows(exclude=self):
            return  # a document was not saved and the user cancelled
        self.btn_go.setEnabled(False)
        self.bar.show()
        self.bar.setRange(0, 0)
        self.lbl.setText(tr("Lade herunter …"))

        def work():
            try:
                path = updates.download(self.release, self.kind, progress=lambda d, t: self._progress.emit(d, t))
                self._ready.emit(path, "")
            except updates.UpdateError as e:
                self._ready.emit("", str(e))

        threading.Thread(target=work, daemon=True, name="update-download").start()

    def _show_progress(self, done: int, total: int):
        if total:
            self.bar.setRange(0, total)
            self.bar.setValue(done)

    def _downloaded(self, path: str, error: str):
        if error:
            self.lbl.setText(tr("Aktualisierung fehlgeschlagen: {0}").format(error))
            self.bar.hide()
            self.btn_go.setEnabled(True)
            return
        if self.kind == "source":  # minutes (apt, pip): in the background, the dialog stays responsive
            self.lbl.setText(tr("Installiere … (Passwortabfrage, kann ein paar Minuten dauern)"))
            self.bar.setRange(0, 0)

            def work():
                r = subprocess.run(updates.source_update_command(self.release, path), capture_output=True, text=True)
                err = "" if r.returncode == 0 else ((r.stderr or r.stdout or "").strip()[-400:] or tr("abgebrochen"))
                self._installed.emit(err)

            threading.Thread(target=work, daemon=True, name="update-install").start()
            return
        try:
            restart = _apply(self.kind, path)
        except updates.UpdateError as e:
            self.lbl.setText(tr("Aktualisierung fehlgeschlagen: {0}").format(e))
            self.bar.hide()
            return
        if restart:
            QProcess.startDetached(restart[0], restart[1:])
        QApplication.quit()

    def _source_done(self, error: str):
        if error:
            self.lbl.setText(tr("Aktualisierung fehlgeschlagen: {0}").format(error))
            self.bar.hide()
            self.btn_go.setEnabled(True)
            return
        QProcess.startDetached("/usr/local/bin/passermark", [])
        QApplication.quit()


def _close_windows(exclude=None) -> bool:
    """Close every window (each asks about unsaved changes) -> False if one stayed open."""
    for w in list(QApplication.topLevelWidgets()):
        if w is exclude or not w.isVisible() or w.parent() is not None:
            continue
        if isinstance(w, QDialog):
            continue
        if not w.close():
            return False
    return True


def _apply(kind: str, path: str) -> list[str] | None:
    """Install the checked AppImage or setup -> the command to start the new Passermark (None: the setup does it).
    The source installation runs in UpdateDialog (it takes minutes)."""
    if kind == "appimage":
        target = updates.replace_appimage(path, os.environ["APPIMAGE"])
        return [target]
    if kind == "windows":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen(updates.windows_setup_command(path), creationflags=flags, close_fds=True)
        return None  # the setup starts Passermark again (/AUTOUPDATE)
    raise updates.UpdateError(tr("Diese Installation kann sich nicht selbst aktualisieren."))


def start_background_check(delay_ms: int = 4000):
    """At program start: check a little later, so that opening the first document is not slowed down."""

    def go():
        ctl = UpdateController.get()
        # a version remembered as available is asked for again (it may have been withdrawn in the meantime)
        ctl.start(force=ctl.state == AVAILABLE)

    QTimer.singleShot(delay_ms, go)
