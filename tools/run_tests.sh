#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Run all tests (tests/test_*.py, each a script of its own) and list what failed.
#
#   tools/run_tests.sh               all tests
#   tools/run_tests.sh preflight vdp only tests whose name contains one of the words
#
# Python: $PYTHON if set, else the first of: venv of an install.sh installation, build venv of the repository
# (.venv), python3 – the first one that has all packages of the program (an old .venv from an earlier AppImage
# build may lack some). Details of a failure: <python> tests/test_<name>.py
cd "$(dirname "$0")/.." || exit 2
NEED="import pypdfium2, pikepdf, PIL, numpy, scipy, contourpy, img2pdf, reportlab"
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for c in /usr/local/lib/passermark/venv/bin/python .venv/bin/python python3; do
    command -v "$c" >/dev/null 2>&1 || continue
    if "$c" -c "$NEED" 2>/dev/null; then PY="$c"; break; fi
    echo "skipped $c: $("$c" -c "$NEED" 2>&1 | tail -1)"
  done
fi
[ -n "$PY" ] || { echo "no Python with the packages of the program – set PYTHON=…"; exit 2; }
"$PY" -c "$NEED" 2>/dev/null || {
  echo "$PY lacks packages of the program: $("$PY" -c "$NEED" 2>&1 | tail -1)"; exit 2; }
echo "Python: $PY"
ok=0; bad=""
for f in tests/test_*.py; do
  name=$(basename "$f" .py)
  if [ $# -gt 0 ]; then
    hit=0; for w in "$@"; do case "$name" in *"$w"*) hit=1;; esac; done
    [ $hit = 1 ] || continue
  fi
  if "$PY" "$f" > "/tmp/passermark-$name.log" 2>&1; then
    ok=$((ok + 1))
  else
    bad="$bad $name"; echo "FAILED $name  (log: /tmp/passermark-$name.log)"
  fi
done
if [ -z "$bad" ]; then echo "$ok ok"; exit 0; fi
echo "$ok ok, failed:$bad"
exit 1
