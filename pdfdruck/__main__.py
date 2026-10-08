# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public
# License, Version 3 oder (nach Ihrer Wahl) jeder späteren Version, weitergeben und/oder ändern.
# Es wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Siehe die Datei LICENSE.
"""passermark [--print] [--open] [DATEIEN …]

  passermark a.pdf b.jpg      öffnen (Bilder werden als PDF in tatsächlicher Größe geöffnet)
  passermark --merge a.pdf b.docx c.jpg   alles zu einem PDF (Reihenfolge im Dialog änderbar)
  passermark --repair *.pdf   reparieren / für Weitergabe optimieren / Passwortschutz
  passermark --print *.pdf    ohne Dialog drucken – mit den Einstellungen einer laufenden
                            Instanz, sonst mit den Admin-Standards
"""
import argparse
import os
import sys


def main():
    import multiprocessing
    multiprocessing.freeze_support()       # gebündelte Programmdatei: Arbeitsprozess starten statt Programm
    # fertige Programmdatei prüfen (GitHub-Build) bzw. AppImage-Root-Helfer (über pkexec)
    if len(sys.argv) >= 2 and sys.argv[1] == "--selftest":
        from . import selftest
        return selftest.run()
    if len(sys.argv) >= 2 and sys.argv[1] == "--admin-helper":
        from . import selftest
        return selftest.admin_helper(sys.argv[2:])
    if len(sys.argv) >= 2 and sys.argv[1] == "--cli":
        from .cli import main as cli_main                      # Aufträge ohne Oberfläche (AppImage: … --cli)
        return cli_main(sys.argv[2:])
    if len(sys.argv) >= 2 and sys.argv[1] == "--version":
        from . import __version__
        print(__version__)
        return 0
    # Windows: erhöhter Admin-Helfer (über UAC gestartet) – ohne Oberfläche
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
        app.installTranslator(_tr)     # Qt-Standardtexte (Ja/Nein, Abbrechen, Dateidialog) in der Oberflächensprache
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

    # Einzelinstanz: an laufende Instanz übergeben – oder selbst Server werden. Mehrere gleichzeitig
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
    ctl.headless = cmd in ("print", "repair")
    if files or cmd != "open":
        ctl.queue_request(cmd, files)
    if not files and cmd == "open":
        ctl.new_window()
    from PySide6.QtCore import QTimer
    QTimer.singleShot(1200, crashui.notify_previous_crashes)  # Absturz beim letzten Mal? -> einmal melden
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
