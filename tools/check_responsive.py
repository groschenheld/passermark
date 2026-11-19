# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Which widgets keep the side panels and windows from getting narrow? (real Qt, no screen needed)

Opens Passermark invisibly with tests/sample.pdf, builds the side panels (check, colour, edit, tools) and the
variable data window, and lists per panel its minimum width and the widgets that demand the most width –
those are the ones that get cut off when the panel is narrower.

    /usr/local/lib/passermark/venv/bin/python -u tools/check_responsive.py > responsive.txt
"""

import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtWidgets import (  # noqa: E402
    QAbstractButton,
    QApplication,
    QComboBox,
    QLabel,
    QMessageBox,
)

app = QApplication(sys.argv)
for _n in ("critical", "warning", "information"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: None))


def pump(sec=1.0):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def describe(w) -> str:
    text = ""
    if isinstance(w, (QLabel, QAbstractButton)):
        text = w.text()
    elif isinstance(w, QComboBox):
        text = w.currentText()
    text = " ".join(str(text).split())[:40]
    lay = w.parentWidget().layout() if w.parentWidget() is not None else None
    chain = []
    p = w.parentWidget()
    while p is not None and len(chain) < 3:
        chain.append(p.metaObject().className() + (f"#{p.objectName()}" if p.objectName() else ""))
        p = p.parentWidget()
    extra = ""
    if isinstance(w, QLabel):
        extra = f" wordWrap={w.wordWrap()}"
    return (
        f"{w.metaObject().className()}{'#' + w.objectName() if w.objectName() else ''} „{text}“{extra}"
        f"  layout={lay.metaObject().className() if lay is not None else '-'}  in {' < '.join(chain)}"
    )


def eff_min(w) -> int:
    """Minimum width a layout gives the widget (like Qt's qSmartMinSize)."""
    from PySide6.QtWidgets import QSizePolicy

    if w.minimumWidth() > 0:
        return w.minimumWidth()
    pol = w.sizePolicy().horizontalPolicy()
    if pol == QSizePolicy.Policy.Ignored:
        return 0
    if not (pol.value & QSizePolicy.PolicyFlag.ShrinkFlag.value):  # cannot shrink: Qt takes the size hint
        return w.sizeHint().width()
    return w.minimumSizeHint().width()


def item_min(it) -> int:
    if it.widget() is not None:
        return 0 if it.widget().isHidden() else eff_min(it.widget())
    if it.layout() is not None:
        return it.layout().minimumSize().width()
    return it.minimumSize().width()


def item_name(it) -> str:
    if it.widget() is not None:
        return describe(it.widget())
    if it.layout() is not None:
        return it.layout().metaObject().className()
    return "Abstand"


def trace(w, depth=0, seen=None):
    """Follow the widest minimum width downwards: at each level all parts of the layout with their minimum."""
    from PySide6.QtWidgets import QAbstractScrollArea, QStackedWidget, QTabWidget

    seen = seen if seen is not None else set()
    if w is None or id(w) in seen or depth > 14:
        return
    seen.add(id(w))
    ind = "  " * depth
    if isinstance(w, QTabWidget):
        w = w.findChild(QStackedWidget)
    if isinstance(w, QStackedWidget):
        pages = [w.widget(i) for i in range(w.count())]
        pages.sort(key=lambda p: -eff_min(p))
        for p in pages[:2]:
            print(f"{ind}[Seite des Stapels] {eff_min(p)}  {describe(p)}")
        trace(pages[0] if pages else None, depth + 1, seen)
        return
    from PySide6.QtWidgets import QSplitter

    if isinstance(w, QSplitter):
        parts = [w.widget(i) for i in range(w.count())]
        for p in sorted(parts, key=lambda p: -eff_min(p)):
            print(f"{ind}[Teil des Splitters] {eff_min(p)}  {describe(p)}")
            trace(p, depth + 1, seen)
        return
    if isinstance(w, QAbstractScrollArea) and hasattr(w, "widget"):
        trace(w.widget(), depth, seen)
        return
    lay = w.layout()
    if lay is None:
        return
    trace_layout(lay, depth, seen)


def trace_layout(lay, depth, seen):
    ind = "  " * depth
    items = [lay.itemAt(i) for i in range(lay.count())]
    items = [it for it in items if it is not None]
    print(f"{ind}{lay.metaObject().className()} min {lay.minimumSize().width()}:")
    for it in sorted(items, key=lambda it: -item_min(it))[:6]:
        print(f"{ind}  {item_min(it):5d}  {item_name(it)}")
    if not items:
        return
    top = max(items, key=item_min)
    if top.layout() is not None and top.widget() is None:
        trace_layout(top.layout(), depth + 1, seen)
    elif top.widget() is not None:
        trace(top.widget(), depth + 1, seen)


def report(name: str, root, n: int = 12):
    root.adjustSize()
    pump(0.3)
    print(f"\n=== {name}: Mindestbreite {root.minimumSizeHint().width()} px")
    trace(root)


from pdfdruck.app import Controller  # noqa: E402

ctl = Controller()
ctl.open_paths([os.path.join(ROOT, "tests", "sample.pdf")])
w = ctl.windows[-1]
w.resize(1400, 900)
w.show()
pump(2)

for name, attr in (("Prüfung", "pf_panel"), ("Farbe", "color_panel"), ("Bearbeiten", "edit_panel")):
    panel = getattr(w, attr, None)
    if panel is not None:
        report(name, panel)
tools = w.tools_dock.widget()
report("Werkzeuge", tools.widget() if hasattr(tools, "widget") else tools)

try:
    from pdfdruck.gui.vdpdialog import VdpDialog

    dlg = VdpDialog(w, w.doc, 0)
    dlg.show()
    pump(1)
    report("Variable Daten (ganzes Fenster)", dlg)
except Exception as e:  # noqa: BLE001 – diagnosis: go on with the rest
    print("\nVariable Daten: nicht prüfbar:", e)

try:
    from pdfdruck.gui.objectsdialog import SeparateDialog

    dlg = SeparateDialog(w, w.doc, 0)
    dlg.show()
    pump(1)
    report("Objekte trennen (ganzes Fenster)", dlg)
except Exception as e:  # noqa: BLE001 – diagnosis: go on with the rest
    print("\nObjekte trennen: nicht prüfbar:", e)

print("\nfertig")
sys.stdout.flush()
os._exit(0)
