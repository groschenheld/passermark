# SPDX-License-Identifier: GPL-3.0-or-later
"""Fehlerprotokoll mit echten Prozessen: sauberer Lauf, Python-Fehler, harter Absturz, Thread, Aufräumen, Aufträge."""
import glob, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); sys.path.insert(0, HERE)


def _run(code, state):
    env = dict(os.environ, PYTHONPATH=ROOT, XDG_STATE_HOME=state, PDFTOOLKIT_LANG="de", LOCALAPPDATA=state)
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=120)


def _logs(state):
    return sorted(glob.glob(os.path.join(state, "**", "*.log"), recursive=True))


PRE = "from pdfdruck import crashlog\nseen=[]\ncrashlog.install('gui', on_error=lambda s, d: seen.append(s))\n"


def test_clean_run_leaves_nothing():
    st = tempfile.mkdtemp()
    r = _run(PRE + "print('ok')", st)
    assert r.returncode == 0 and _logs(st) == [], (r.stderr, _logs(st))


def test_python_error_logged_and_shown_once():
    st = tempfile.mkdtemp()
    r = _run(PRE + "import atexit\natexit.register(lambda: print('ANGEZEIGT', len(seen)))\nraise RuntimeError('Testfehler 42')", st)
    logs = _logs(st)
    assert len(logs) == 1 and "ANGEZEIGT 1" in r.stdout, (r.stdout, r.stderr)
    text = open(logs[0], encoding="utf-8").read()
    assert "Testfehler 42" in text and "Traceback" in text and "pdfToolkit " in text and "Kerne:" in text
    r = _run("from pdfdruck import crashlog\ncrashlog.install('gui')\nprint(len(crashlog.pending_crashes()))", st)
    assert r.stdout.strip() == "0", r.stdout                 # schon angezeigt -> beim Start nicht nochmal


def test_hard_crash_reported_once():
    st = tempfile.mkdtemp()
    r = _run(PRE + "import ctypes\nctypes.string_at(0)", st)        # echter Speicherzugriffsfehler
    assert r.returncode != 0
    logs = _logs(st)
    assert len(logs) == 1 and "Fatal Python error" in open(logs[0], encoding="utf-8").read(), logs
    code = "from pdfdruck import crashlog\ncrashlog.install('gui')\np=crashlog.pending_crashes()\nprint(len(p))\ncrashlog.mark_seen(p)"
    assert _run(code, st).stdout.strip() == "1"                   # nächster Start meldet ihn
    assert _run(code, st).stdout.strip() == "0"                   # und danach nicht mehr


def test_thread_error_logged():
    st = tempfile.mkdtemp()
    r = _run(PRE + "import threading\nt=threading.Thread(target=lambda: 1/0, name='Rechner')\nt.start(); t.join()", st)
    logs = _logs(st)
    assert len(logs) == 1 and "ZeroDivisionError" in open(logs[0], encoding="utf-8").read() and "Rechner" in \
        open(logs[0], encoding="utf-8").read(), (r.stderr, logs)


def test_prune_keeps_max():
    st = tempfile.mkdtemp()
    code = PRE + "crashlog.record('x')"
    for _ in range(13):
        _run(code, st)
    from pdfdruck import crashlog
    assert len(_logs(st)) <= crashlog.MAX_LOGS + 1, len(_logs(st))


def test_wired_into_program():
    """Programmstart richtet das Protokoll ein, Hilfe-Menü öffnet den Ordner."""
    main = open(os.path.join(ROOT, "pdfdruck", "__main__.py"), encoding="utf-8").read()
    assert 'crashlog.install("gui"' in main and "notify_previous_crashes" in main
    viewer = open(os.path.join(ROOT, "pdfdruck", "gui", "viewer.py"), encoding="utf-8").read()
    assert "open_log_dir" in viewer


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("ok", k)
