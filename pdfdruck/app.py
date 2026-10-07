# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""Programmweiter Zustand + Einzelinstanz.

Läuft pdfdruck bereits, schicken weitere Aufrufe (Rechtsklick „Drucken“ / „Als PDF öffnen“)
ihren Auftrag per QLocalSocket an die laufende Instanz. Dadurch gelten für den
Rechtsklick-Druck die im Druckdialog gesetzten Sitzungseinstellungen – bis das letzte
Fenster geschlossen wird. Läuft nichts, wird mit den Admin-Standards gedruckt.
"""
from __future__ import annotations

from .l10n import tr

import json
import os
import shutil
import subprocess

from PySide6.QtCore import QObject, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from . import config, images, printjob
from . import platform as _platform
from .gui.common import Session


def server_name() -> str:
    return f"passermark-{_platform.user_id()}"


def notify(title: str, body: str, error: bool = False):
    _platform.notify(title, body, error)


def send_to_running(cmd: str, files: list[str], timeout_ms: int = 400) -> bool:
    """True, wenn eine laufende Instanz den Auftrag übernommen hat."""
    sock = QLocalSocket()
    sock.connectToServer(server_name())
    if not sock.waitForConnected(timeout_ms):
        return False
    sock.write((json.dumps({"cmd": cmd, "files": files}) + "\n").encode("utf-8"))
    sock.flush()
    sock.waitForBytesWritten(2000)
    sock.waitForReadyRead(3000)
    sock.disconnectFromServer()
    return True


class Controller(QObject):
    def __init__(self):
        super().__init__()
        self.cfg = config.load()
        self.session = Session(self.cfg)
        self.windows = []
        self.server: QLocalServer | None = None
        self.view_single = True       # Einzelseite mit Springen als Standard (Ansicht umschaltbar)

    # ---------------------------------------------------------------- #
    # ---------------------------------------------------------------- #
    # Zwischenspeicher für Manipulations-Ergebnisse (wird beim Beenden geleert)
    # ---------------------------------------------------------------- #
    def cache_dir(self) -> str:
        if not hasattr(self, "_cache"):
            import time
            self._cache = os.path.join(_platform.user_cache_dir(), "dokumente")
            os.makedirs(self._cache, exist_ok=True)
            self._cache_files = []
            for f in os.listdir(self._cache):          # Reste früherer Sitzungen (älter als 2 Tage)
                p = os.path.join(self._cache, f)
                try:
                    if time.time() - os.path.getmtime(p) > 2 * 86400:
                        os.remove(p)
                except OSError:
                    pass
            QApplication.instance().aboutToQuit.connect(self._clear_cache)
        return self._cache

    def cache_file(self, name: str) -> str:
        import re
        d = self.cache_dir()
        base, ext = os.path.splitext(re.sub(r'[\\/:*?"<>|]+', "_", name) or "Dokument.pdf")
        path, i = os.path.join(d, base + ext), 2
        while os.path.exists(path):
            path, i = os.path.join(d, f"{base}_{i}{ext}"), i + 1
        self._cache_files.append(path)
        return path

    def _clear_cache(self):
        for w in list(self.windows):
            if getattr(w, "doc", None) is not None:
                try:
                    w.doc.close()
                except Exception:
                    pass
        for p in getattr(self, "_cache_files", []):
            try:
                os.remove(p)
            except OSError:
                pass

    def reload_config(self):
        """Nach Admin-Änderung: neue Standards sofort für alle Fenster."""
        self.cfg = config.load()
        self.session = Session(self.cfg)

    @property
    def image_dpi(self) -> float:
        return float(self.cfg.get("image_default_dpi", 96))

    # ---------------------------------------------------------------- #
    def start_server(self) -> bool:
        """Als Einzelinstanz-Server lauschen. False, wenn gerade eine andere Instanz Server wurde."""
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self._on_connection)
        if self.server.listen(server_name()):
            return True
        # Belegt: läuft wirklich jemand? Sonst verwaiste Socketdatei nach Absturz entfernen.
        probe = QLocalSocket()
        probe.connectToServer(server_name())
        if probe.waitForConnected(200):
            probe.disconnectFromServer()
            return False
        QLocalServer.removeServer(server_name())
        return self.server.listen(server_name())

    def _on_connection(self):
        while self.server.hasPendingConnections():
            sock = self.server.nextPendingConnection()
            sock.readyRead.connect(lambda s=sock: self._on_ready(s))

    def _on_ready(self, sock):
        if not sock.canReadLine():
            return
        try:
            msg = json.loads(bytes(sock.readLine()).decode("utf-8"))
            cmd, files = msg.get("cmd"), [str(f) for f in msg.get("files", [])]
        except (ValueError, AttributeError):
            sock.write(b"error\n")
            return
        sock.write(b"ok\n")
        sock.flush()
        sock.disconnected.connect(sock.deleteLater)
        self.queue_request(cmd, files)

    # ---------------------------------------------------------------- #
    # Aufträge kurz sammeln: Explorer/Nautilus starten bei Mehrfachauswahl teils einen Prozess je Datei
    # ---------------------------------------------------------------- #
    BATCH_MS = 700

    def queue_request(self, cmd: str, files: list[str]):
        cmd = cmd if cmd in ("print", "merge", "repair", "open") else "open"
        if not hasattr(self, "_pending"):
            self._pending = {}
            self._batch = QTimer(self, singleShot=True, interval=self.BATCH_MS, timeout=self._flush)
        lst = self._pending.setdefault(cmd, [])
        for f in files:
            if f not in lst:
                lst.append(f)
        self._batch.start()                     # jede neue Datei verlängert das Sammelfenster

    def _flush(self):
        pending, self._pending = self._pending, {}
        for cmd in ("merge", "open", "repair", "print"):
            files = pending.get(cmd)
            if not files:
                continue
            if cmd == "merge":
                self.merge_paths(files)
            elif cmd == "repair":
                self.repair_paths(files)
            elif cmd == "print":
                self.print_paths(files)
            else:
                self.open_paths(files)
        if not self.windows:
            QApplication.instance().quit()     # nichts mehr offen (reiner Druck/Reparatur/abgebrochen): fertig

    # ---------------------------------------------------------------- #
    def new_window(self):
        from .gui.viewer import MainWindow
        w = MainWindow(self)
        self.windows.append(w)
        w.destroyed.connect(lambda *_: self.windows.remove(w) if w in self.windows else None)
        w.show()
        return w

    def _target_window(self):
        for w in self.windows:
            if w.doc is None:
                return w
        return self.new_window()

    def open_paths(self, paths: list[str]):
        paths = [os.path.abspath(p) for p in paths if os.path.isfile(p)]
        imgs = [p for p in paths if images.is_image(p)]
        rest = [p for p in paths if not images.is_image(p)]
        if imgs:   # mehrere Bilder auf einmal -> ein Dokument
            self._target_window().open_images(imgs)
        for p in rest:   # PDF direkt, Office wird umgewandelt
            self._target_window().open_any(p)
        if not self.windows:
            self.new_window()
        w = self.windows[-1]
        w.raise_()
        w.activateWindow()

    def merge_paths(self, paths: list[str]):
        """Rechtsklick „Als ein PDF zusammenführen“: Reihenfolge prüfen, dann zusammenführen."""
        from . import convert
        from .gui.viewer import MergeDialog
        paths = [os.path.abspath(p) for p in paths if os.path.isfile(p) and convert.is_supported(p)]
        if not paths:
            return
        dlg = MergeDialog(self.windows[-1] if self.windows else None, sorted(paths, key=lambda p: os.path.basename(p).lower()))
        if dlg.exec() and dlg.paths():
            self.merge_into_window(dlg.paths())

    def merge_into_window(self, paths: list[str], window=None):
        from .gui.viewer import merge_files
        w = window or self._target_window()
        doc, notes = merge_files(w, self, paths)
        if doc is None:
            if w.doc is None and len(self.windows) > 1:
                w.close()
            return
        base = os.path.splitext(os.path.basename(paths[0]))[0]
        w._set_doc(doc, None, tr("{0} (zusammengeführt).pdf").format(base), True)
        w._suggest_dir = os.path.dirname(paths[0])
        w.show()
        w.raise_()
        conv = [n for n in notes if "umgewandelt" in n]
        skip = [n for n in notes if tr("übersprungen") in n]
        msg = tr("{0} Datei(en), {1} Seiten zusammengeführt – noch nicht gespeichert.").format(len(paths) - len(skip), len(doc))
        if skip:
            msg += "  " + "; ".join(skip)
        w.statusBar().showMessage(msg, 15000)
        if conv:
            w.statusBar().setToolTip("\n".join(conv))

    def repair_paths(self, paths: list[str]):
        from .gui.repairdialog import RepairDialog
        paths = [os.path.abspath(p) for p in paths if os.path.isfile(p)]
        if not paths:
            return
        parent = self.windows[-1] if self.windows else None
        dlg = RepairDialog(parent, paths, open_cb=lambda p: self.open_paths([p]))
        dlg.exec()

    def print_paths(self, paths: list[str]) -> bool:
        ok, errors = [], []
        for p in paths:
            password = None
            while True:
                try:
                    printer, jid = printjob.print_file(p, self.session, password)
                    ok.append(tr("{0} → {1} (Auftrag {2})").format(os.path.basename(p), printer, jid))
                    break
                except Exception as e:
                    if "password" in str(e).lower():
                        from PySide6.QtWidgets import QInputDialog, QLineEdit
                        password, accepted = QInputDialog.getText(
                            self.windows[-1] if self.windows else None, tr("Passwortgeschützt"),
                            tr("{0}Passwort für „{1}“:").format(tr('Falsches Passwort. ') if password else '', os.path.basename(p)),
                            QLineEdit.EchoMode.Password)
                        if accepted:
                            continue
                        errors.append(tr("{0}: passwortgeschützt – übersprungen").format(os.path.basename(p)))
                    else:
                        errors.append(f"{os.path.basename(p)}: {e}")
                    break
        if ok:
            notify(tr("{0} Datei(en) gedruckt").format(len(ok)), "\n".join(ok[:6]) + (" …" if len(ok) > 6 else ""))
            for w in self.windows:
                w.statusBar().showMessage(tr("{0} Datei(en) gedruckt.").format(len(ok)), 8000)
        if errors:
            notify(tr("Druckfehler"), "\n".join(errors[:6]), error=True)
            QMessageBox.critical(self.windows[-1] if self.windows else None, tr("Druckfehler"), "\n".join(errors))
        return not errors
