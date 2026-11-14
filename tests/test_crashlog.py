# SPDX-License-Identifier: GPL-3.0-or-later
"""Crash log with real processes: clean run, Python error, hard crash, thread, cleanup, jobs."""

import glob
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)


def _run(code, state):
    env = dict(os.environ, PYTHONPATH=ROOT, XDG_STATE_HOME=state, PASSERMARK_LANG="de", LOCALAPPDATA=state)
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
    r = _run(
        PRE
        + "import atexit\natexit.register(lambda: print('ANGEZEIGT', len(seen)))\nraise RuntimeError('Testfehler 42')",
        st,
    )
    logs = _logs(st)
    assert len(logs) == 1 and "ANGEZEIGT 1" in r.stdout, (r.stdout, r.stderr)
    text = open(logs[0], encoding="utf-8").read()
    assert "Testfehler 42" in text and "Traceback" in text and "Passermark " in text and "Kerne:" in text
    r = _run("from pdfdruck import crashlog\ncrashlog.install('gui')\nprint(len(crashlog.pending_crashes()))", st)
    assert r.stdout.strip() == "0", r.stdout  # already shown -> not again at start


def test_notes_kept_but_not_reported_as_crash():
    """Logger warnings (recoverable errors): file kept with the cause, same note at most NOTE_REPEATS times,
    nothing shown and no crash report at the next start."""
    st = tempfile.mkdtemp()
    code = (
        PRE
        + "import logging\nlog = logging.getLogger('pdfdruck.test')\n"
        + "for i in range(5):\n"
        + "    try:\n        raise ValueError('kaputt %d' % i)\n"
        + "    except ValueError:\n        log.warning('Testhinweis', exc_info=True)\n"
        + "log.info('nur Info')\nprint('GEZEIGT', len(seen))"
    )
    r = _run(code, st)
    logs = _logs(st)
    assert r.returncode == 0 and "GEZEIGT 0" in r.stdout and len(logs) == 1, (r.stdout, r.stderr, logs)
    text = open(logs[0], encoding="utf-8").read()
    assert text.count("== Hinweis") == 3 and "pdfdruck.test: Testhinweis" in text, text
    assert "kaputt 0" in text and "kaputt 4" not in text and "nur Info" not in text
    assert "Traceback (most recent call last)" not in text and "== Fehler" not in text
    r = _run("from pdfdruck import crashlog\ncrashlog.install('gui')\nprint(len(crashlog.pending_crashes()))", st)
    assert r.stdout.strip() == "0", r.stdout
    r = _run("import logging, pdfdruck\nlogging.getLogger('pdfdruck.x').warning('still')", st)
    assert r.returncode == 0 and "still" not in r.stderr, r.stderr  # without a log: silent (CLI, tests)


def test_hard_crash_reported_once():
    st = tempfile.mkdtemp()
    r = _run(PRE + "import ctypes\nctypes.string_at(0)", st)  # real memory access error
    assert r.returncode != 0
    logs = _logs(st)
    assert len(logs) == 1 and "Fatal Python error" in open(logs[0], encoding="utf-8").read(), logs
    code = "from pdfdruck import crashlog\ncrashlog.install('gui')\np=crashlog.pending_crashes()\nprint(len(p))\ncrashlog.mark_seen(p)"
    assert _run(code, st).stdout.strip() == "1"  # the next start reports it
    assert _run(code, st).stdout.strip() == "0"  # and not afterwards either


def test_thread_error_logged():
    st = tempfile.mkdtemp()
    r = _run(PRE + "import threading\nt=threading.Thread(target=lambda: 1/0, name='Rechner')\nt.start(); t.join()", st)
    logs = _logs(st)
    assert (
        len(logs) == 1
        and "ZeroDivisionError" in open(logs[0], encoding="utf-8").read()
        and "Rechner" in open(logs[0], encoding="utf-8").read()
    ), (r.stderr, logs)


def test_prune_keeps_max():
    st = tempfile.mkdtemp()
    code = PRE + "crashlog.record('x')"
    for _ in range(13):
        _run(code, st)
    from pdfdruck import crashlog

    assert len(_logs(st)) <= crashlog.MAX_LOGS + 1, len(_logs(st))


def test_job_crash_details_reach_gui():
    import test_cutcontour as tc

    from pdfdruck import jobproc

    tmp = tempfile.mkdtemp()
    src = os.path.join(tmp, "b.pdf")
    tc.stickers().save(src)
    orig = jobproc.cli_command
    jobproc.cli_command = lambda: (
        [sys.executable, "-c", "import faulthandler, ctypes; faulthandler.enable(); ctypes.string_at(0)"],
        {},
    )
    try:
        r = jobproc.JobProcess("cutcontour", src, os.path.join(tmp, "o.pdf"), {}).run()
    finally:
        jobproc.cli_command = orig
    assert r["event"] == "error" and "Fatal Python error" in r.get("details", ""), r


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
