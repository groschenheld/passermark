# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Program-wide state + single instance.

If pdfdruck is already running, further calls (right-click "Print" / "Open as PDF")
send their job via QLocalSocket to the running instance. That way, right-click
printing uses the session settings made in the print dialog – until the last
window is closed. If nothing is running, printing uses the admin defaults.
"""

from __future__ import annotations

import json
import logging
import os
import sys

from PySide6.QtCore import QObject, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from . import config, images, printjob
from . import platform as _platform
from .gui.common import Session
from .l10n import tr

log = logging.getLogger(__name__)


def server_name() -> str:
    """Name of the local socket of the running instance (one per user)."""
    return f"passermark-{_platform.user_id()}"


def notify(title: str, body: str, error: bool = False):
    """Show a desktop notification (used when printing without a window)."""
    _platform.notify(title, body, error)


def send_to_running(cmd: str, files: list[str], timeout_ms: int = 400) -> bool:
    """True if a running instance accepted the job."""
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
    """Program-wide state: admin configuration, print session, all open windows and the single-instance server.

    There is exactly one controller per process. Windows and dialogs reach shared state through it.
    """

    def __init__(self):
        super().__init__()
        self.cfg = config.load()
        self.session = Session(self.cfg)
        self.windows = []
        self.hosts = []  # window frames (each with one or more tabs)
        self.server: QLocalServer | None = None
        self.view_single = True  # single page with jumping as the default (the view can be switched)
        self._start_stallwatch()
        self._ensure_sendto()

    @staticmethod
    def _ensure_sendto():
        """Windows: "Send to → Passermark – zusammenführen" for the logged-in user (once).
        Hands all selected files to ONE process at once – for large numbers (110 plans) much
        faster than the context menu, where Explorer starts one process per file.
        """
        if os.name != "nt" or not getattr(sys, "frozen", False):
            return
        try:
            from . import l10n

            st = l10n.load_settings()
            if st.get("sendto_created"):
                return  # already created (or deliberately deleted) – not again
            folder = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "SendTo")
            if not os.path.isdir(folder):
                return
            import win32com.client

            lnk = os.path.join(folder, tr("Passermark – zusammenführen") + ".lnk")
            sc = win32com.client.Dispatch("WScript.Shell").CreateShortCut(lnk)
            sc.TargetPath = sys.executable
            sc.Arguments = "--merge"
            sc.IconLocation = sys.executable + ",0"
            sc.Description = tr("Markierte Dateien als ein PDF zusammenführen")
            sc.save()
            st["sendto_created"] = True
            l10n.save_settings(st)
        except Exception:
            log.warning("Kontextmenü-Verknüpfung „Senden an“ nicht angelegt", exc_info=True)

    def _start_stallwatch(self):
        """Stall log (ruckler.txt in the folder of the error logs): hangs of the interface with their cause."""
        try:
            from . import crashlog

            if not crashlog.enabled():  # error logs switched off: no stall reports either
                self._stallwatch = None
                return
            from .gui.renderclient import RenderService
            from .gui.stallwatch import StallWatch

            def ctx():
                # runs in the watchdog thread: only look at the service, never create it here (otherwise its timer
                # belongs to this thread and the render process never gets requests – pages would stay white)
                svc = RenderService._instances.get("render")
                return "Vorschau im Programm" if svc is not None and not svc.ok else ""

            self._stallwatch = StallWatch(os.path.join(crashlog.log_dir(), "ruckler.txt"), ctx).start(self)
        except Exception:
            log.warning("Ruckler-Protokoll nicht gestartet", exc_info=True)
            self._stallwatch = None

    # ---------------------------------------------------------------- #
    # ---------------------------------------------------------------- #
    # cache for manipulation results (emptied on exit)
    # ---------------------------------------------------------------- #
    def cache_dir(self) -> str:
        """Return the folder for temporary documents (created on first use; leftovers older than two days are
        removed).
        """
        if not hasattr(self, "_cache"):
            import time

            self._cache = os.path.join(_platform.user_cache_dir(), "dokumente")
            os.makedirs(self._cache, exist_ok=True)
            self._cache_files = []
            for f in os.listdir(self._cache):  # leftovers from earlier sessions (older than 2 days)
                p = os.path.join(self._cache, f)
                try:
                    if time.time() - os.path.getmtime(p) > 2 * 86400:
                        os.remove(p)
                except OSError:
                    pass
            QApplication.instance().aboutToQuit.connect(self._clear_cache)
        return self._cache

    def cache_file(self, name: str) -> str:
        """Return a new, unused path in the cache folder for ``name``; the file is removed when the program ends."""
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
                except Exception:  # noqa: BLE001 – closing on exit, the document may already be gone
                    pass
        for p in getattr(self, "_cache_files", []):
            try:
                os.remove(p)
            except OSError:
                pass

    def reload_config(self):
        """After an admin change: new defaults immediately for all windows."""
        self.cfg = config.load()
        self.session = Session(self.cfg)

    @property
    def image_dpi(self) -> float:
        """Resolution assumed for images that carry no DPI value (admin setting)."""
        return float(self.cfg.get("image_default_dpi", 96))

    # ---------------------------------------------------------------- #
    def start_server(self) -> bool:
        """Listen as the single-instance server. False if another instance has just become the server."""
        if os.name == "nt":
            # Windows: listen() also succeeds when an instance is already listening on the name (named pipe without
            # "first instance") – there would then be two servers and the files of a multiple selection would be split.
            probe = QLocalSocket()
            probe.connectToServer(server_name())
            if probe.waitForConnected(200):
                probe.disconnectFromServer()
                return False
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self._on_connection)
        if self.server.listen(server_name()):
            return True
        # In use: is someone really running? Otherwise remove an orphaned socket file left by a crash.
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
        if cmd in (None, "open") and not files:
            # program started again (start menu, icon) -> a new, empty window instead of nothing
            self.new_window()
            return
        self.queue_request(cmd, files)

    # ---------------------------------------------------------------- #
    # collect jobs briefly: Explorer/Nautilus sometimes start one process per file on multi-selection
    # ---------------------------------------------------------------- #
    BATCH_MS = 700

    def queue_request(self, cmd: str, files: list[str]):
        """Handle a request from the command line or from a second program start.

        ``cmd`` is one of open, print, merge, repair, plan, poster. Requests arriving in quick succession (several
        files selected in the file manager) are collected and handled together.
        """
        cmd = cmd if cmd in ("print", "merge", "repair", "open", "plan", "poster") else "open"
        if cmd in ("plan", "poster"):
            self.plan_window(cmd, files=files)  # own window; already open: add the files there
            return
        dlg = getattr(self, "_merge_dlg", None)
        if cmd == "merge" and dlg is not None:
            dlg.add_paths(files)  # the merge dialog is already open: add there (no second one)
            return
        if not hasattr(self, "_pending"):
            self._pending = {}
            self._batch = QTimer(self, singleShot=True, interval=self.BATCH_MS, timeout=self._flush)
        lst = self._pending.setdefault(cmd, [])
        for f in files:
            if f not in lst:
                lst.append(f)
        self._batch.start()  # each new file extends the collection window

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
        if not self.windows and not self.plan_windows():
            QApplication.instance().quit()  # nothing open any more (print only/repair/cancelled): done

    # ---------------------------------------------------------------- #
    def plan_window(self, kind: str = "plan", entry: dict | None = None, files=None):
        """Plan/poster printing as its own window – stays open when the document windows are closed."""
        from .gui.plandialog import open_window

        return open_window(self.session, self, kind, entry, [os.path.abspath(f) for f in files or []])

    @staticmethod
    def plan_windows() -> list:
        """Return the open plan and poster windows."""
        from .gui.plandialog import open_windows

        return open_windows()

    # ---------------------------------------------------------------- #
    @staticmethod
    def tabs_enabled() -> bool:
        """Whether documents open as tabs (user setting) instead of separate windows."""
        from . import l10n

        return bool(l10n.load_settings().get("open_in_tabs", True))

    def new_host(self):
        """Create a new top-level window frame that holds document tabs."""
        from .gui.tabhost import TabHost

        h = TabHost(self)
        self.hosts.append(h)
        return h

    def new_window(self, tab_of=None):
        """New document window. tab_of = window it originates from: then as a tab next to it
        (setting "Open inside the program as a tab"). Otherwise a standalone window.
        """
        from .gui.mainwindow import MainWindow

        w = MainWindow(self)
        self.windows.append(w)
        w.destroyed.connect(lambda *_: self.windows.remove(w) if w in self.windows else None)
        host = getattr(tab_of, "_host", None) if tab_of is not None and self.tabs_enabled() else None
        if host is None:
            host = self.new_host()
            if tab_of is not None:
                try:
                    host.move(tab_of.window().pos().x() + 40, tab_of.window().pos().y() + 40)
                except Exception:  # noqa: BLE001 – window placement is cosmetic
                    pass
        host.add(w)
        host.show_tab(w)
        return w

    def show_window(self, w):
        """Bring a document window to the front (selects its tab if it lives in a tab host)."""
        host = getattr(w, "_host", None)
        if host is not None:
            host.show_tab(w)
        else:
            w.show()
            w.raise_()
            w.activateWindow()

    @staticmethod
    def blocked(w) -> bool:
        """Is the window (or its frame with all tabs) currently blocked by an open dialog?"""
        from PySide6.QtWidgets import QDialog

        top = getattr(w, "_host", None) or w
        try:
            return any(d.isVisible() and d.isModal() for d in top.findChildren(QDialog))
        except Exception:  # noqa: BLE001 – if in doubt: not locked
            return False

    def _target_window(self, tab_of=None):
        if tab_of is None:  # from outside (double-click, "Open with"): use an empty window –
            for w in self.windows:  # but not in a frame in which a tool is currently open
                if w.doc is None and not self.blocked(w):
                    return w
            return self.new_window()
        if self.blocked(tab_of):  # result/open from a locked window: its own window
            return self.new_window()
        if getattr(tab_of, "doc", 1) is None and tab_of in self.windows:
            return tab_of  # use the empty window itself (no invisible empty tab)
        return self.new_window(tab_of)

    def open_paths(self, paths: list[str], tab_of=None):
        """Open files. tab_of = window inside the program (Open button, drag & drop, result) -> as a tab;
        otherwise (program start, double-click in the file manager) standalone windows.
        """
        paths = [os.path.abspath(p) for p in paths if os.path.isfile(p)]
        imgs = [p for p in paths if images.is_image(p)]
        rest = [p for p in paths if not images.is_image(p)]
        last = None
        if imgs:  # several images at once -> one document
            last = self._target_window(tab_of)
            last.open_images(imgs)
        for p in rest:  # PDF directly, Office files are converted
            last = self._target_window(tab_of)
            last.open_any(p)
        if not self.windows:
            last = self.new_window()
        self.show_window(last or self.windows[-1])

    def merge_paths(self, paths: list[str]):
        """Right-click "Merge into one PDF": check the order, then merge. Files that still arrive
        (Explorer starts one process per file) end up in the same dialog that is already open.
        """
        from . import convert
        from .gui.mergedialog import MergeDialog

        paths = [os.path.abspath(p) for p in paths if os.path.isfile(p) and convert.is_supported(p)]
        if not paths:
            return
        dlg = MergeDialog(self.windows[-1] if self.windows else None)
        dlg.add_paths(paths)
        self._merge_dlg = dlg
        try:
            ok = dlg.exec()
        finally:
            self._merge_dlg = None
        if ok and dlg.paths():
            self.merge_into_window(dlg.paths())

    def merge_into_window(self, paths: list[str], window=None):
        """Merge ``paths`` into one document and show it in ``window`` (default: the current target window)."""
        from .gui.fileopen import merge_files

        w = window or self._target_window()
        doc, notes = merge_files(w, self, paths)
        if doc is None:
            if w.doc is None and len(self.windows) > 1:
                w.close()
            return
        base = os.path.splitext(os.path.basename(paths[0]))[0]
        w._sources = list(paths)
        w._set_doc(doc, None, tr("{0} (zusammengeführt).pdf").format(base), True)
        w._suggest_dir = os.path.dirname(paths[0])
        self.show_window(w)
        conv = [n for n in notes if "umgewandelt" in n]
        skip = [n for n in notes if tr("übersprungen") in n]
        msg = tr("{0} Datei(en), {1} Seiten zusammengeführt – noch nicht gespeichert.").format(
            len(paths) - len(skip), len(doc)
        )
        if skip:
            msg += "  " + "; ".join(skip)
        w.statusBar().showMessage(msg, 15000)
        if conv:
            w.statusBar().setToolTip("\n".join(conv))

    def repair_paths(self, paths: list[str]):
        """Open the repair dialog for the given files."""
        from .gui.repairdialog import RepairDialog

        paths = [os.path.abspath(p) for p in paths if os.path.isfile(p)]
        if not paths:
            return
        parent = self.windows[-1] if self.windows else None
        dlg = RepairDialog(parent, paths, open_cb=lambda p: self.open_paths([p]))
        dlg.exec()

    def print_paths(self, paths: list[str]) -> bool:
        """Print files with the default settings and no dialog; asks for a password where needed.

        Returns True if at least one file was sent.
        """
        ok, errors = [], []
        for p in paths:
            password = None
            while True:
                try:
                    printer, jid = printjob.print_file(p, self.session, password)
                    ok.append(tr("{0} → {1} (Auftrag {2})").format(os.path.basename(p), printer, jid))
                    break
                except Exception as e:  # noqa: BLE001 – shown to the user (password prompt or error list)
                    if "password" in str(e).lower():
                        from PySide6.QtWidgets import QInputDialog, QLineEdit

                        password, accepted = QInputDialog.getText(
                            self.windows[-1] if self.windows else None,
                            tr("Passwortgeschützt"),
                            tr("{0}Passwort für „{1}“:").format(
                                tr("Falsches Passwort. ") if password else "", os.path.basename(p)
                            ),
                            QLineEdit.EchoMode.Password,
                        )
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
