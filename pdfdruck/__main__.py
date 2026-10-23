# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""passermark [--print] [--open] [FILES …]

  passermark a.pdf b.jpg      open (images are opened as PDFs at actual size)
  passermark --merge a.pdf b.docx c.jpg   everything into one PDF (order changeable in the dialog)
  passermark --repair *.pdf   repair / optimize for sharing / password protection
  passermark --print *.pdf    print without a dialog – with the settings of a running
                            instance, otherwise with the admin defaults
"""
import argparse
import os
import sys


def main():
    import multiprocessing
    multiprocessing.freeze_support()       # bundled program file: start the worker process instead of the program
    # check the finished program file (GitHub build) or AppImage root helper (via pkexec)
    if len(sys.argv) >= 2 and sys.argv[1] == "--selftest":
        from . import selftest
        return selftest.run()
    if len(sys.argv) >= 2 and sys.argv[1] == "--admin-helper":
        from . import selftest
        return selftest.admin_helper(sys.argv[2:])
    if len(sys.argv) >= 2 and sys.argv[1] == "--cli":
        from .cli import main as cli_main                      # jobs without a GUI (AppImage: … --cli)
        return cli_main(sys.argv[2:])
    if len(sys.argv) >= 2 and sys.argv[1] == "--version":
        from . import __version__
        print(__version__)
        return 0
    # Windows: elevated admin helper (started via UAC) – without a GUI
    if len(sys.argv) == 3 and sys.argv[1] == "--admin-apply":
        from . import winadmin
        return winadmin.apply(sys.argv[2])
    ap = argparse.ArgumentParser(prog="passermark")
    ap.add_argument("--print", dest="do_print", action="store_true", help="ohne Dialog drucken")
    ap.add_argument("--open", action="store_true", help="öffnen (Standard)")
    ap.add_argument("--repair", action="store_true", help="reparieren / optimieren / Passwort (Dialog)")
    ap.add_argument("--merge", action="store_true", help="Dateien (PDF, Bilder, Office) zu einem PDF zusammenführen")
    ap.add_argument("files", nargs="*")
    args, _qt = ap.parse_known_args()
    # läuft schon eine Instanz? Dann sofort weiterreichen – noch bevor Qt und die Oberfläche geladen werden
    # (Explorer-Mehrfachauswahl startet einen Prozess je Datei; so sind die nach Sekundenbruchteilen wieder weg)
    early_cmd = "print" if args.do_print else "repair" if args.repair else "merge" if args.merge else "open"
    # Mehrere gleichzeitig gestartete Prozesse (Explorer: je Datei einer) warten hier an einer Startsperre – genau
    # einer wird Hauptinstanz, die übrigen reichen danach ihre Datei an ihn weiter.
    from . import fastipc
    start_lock = fastipc.hand_over_or_lock(early_cmd, [os.path.abspath(f) for f in args.files])
    if start_lock is None:
        return 0

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Passermark")
    app.setApplicationDisplayName("Passermark")
    app.setDesktopFileName("passermark")   # Wayland app-id -> Icon/Desktop-Eintrag
    from PySide6.QtGui import QIcon
    _ic = os.path.join(os.path.dirname(__file__), "gui", "passermark.svg")
    app.setWindowIcon(QIcon.fromTheme("passermark", QIcon(_ic)))
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
    from . import l10n
    _lang = l10n.current()
    _tr = QTranslator(app)
    if _lang != "en" and _tr.load(QLocale(_lang), "qtbase", "_",
                                  QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(_tr)     # Qt standard texts (Yes/No, Cancel, file dialog) in the interface language
    from .gui import theme
    theme.apply(app)                 # dunkles Design, gelber Akzent, Mausrad-Schutz
    from .gui.common import window_modal_dialogs
    window_modal_dialogs()           # Dialoge sperren nur ihr eigenes Fenster, nicht alle Passermark-Fenster
    from . import crashlog
    from .gui import crashui
    crashlog.install("gui", on_error=crashui.show_error)     # Fehlerprotokoll (Datei zum Mitschicken)
    files = [os.path.abspath(f) for f in args.files]

    from . import app as appmod

    cmd = "print" if args.do_print else "repair" if args.repair else "merge" if args.merge else "open"

    # single instance: hand over to the running instance – or become the server yourself. Several at once
    # gestartete Prozesse (Explorer-Mehrfachauswahl) einigen sich so auf genau einen Server.
    import time
    ctl = None
    for _ in range(12):
        if appmod.send_to_running(cmd, files):
            return 0
        ctl = ctl or appmod.Controller()
        if ctl.start_server():
            break
        time.sleep(0.15)
    if ctl is None:
        ctl = appmod.Controller()
    start_lock.release()             # Server lauscht: wartende Prozesse dürfen jetzt weiterreichen
    ctl.headless = cmd in ("print", "repair")
    from PySide6.QtCore import QTimer
    if files or cmd != "open":
        # erst in der laufenden Ereignisschleife sammeln – sonst kann das Sammelfenster schon ablaufen, bevor die
        # gleichzeitig gestarteten Prozesse ihre Dateien überhaupt abgeben konnten
        QTimer.singleShot(0, lambda: ctl.queue_request(cmd, files))
    if not files and cmd == "open":
        ctl.new_window()
    QTimer.singleShot(1200, crashui.notify_previous_crashes)  # Absturz beim letzten Mal? -> einmal melden
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
