# SPDX-License-Identifier: GPL-3.0-or-later
"""Widgets carry our own values in dynamic properties (setProperty/property). Such a name must not be one that Qt
already uses: setProperty("font", "Helvetica") does not store the text but tries to set the widget's font – and
property("font") then returns a QFont. That crashed "download free font" in the document check."""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
GUI = os.path.join(ROOT, "pdfdruck", "gui")

# properties Qt defines on the widgets we use (QObject, QWidget, buttons, combo boxes, line edits, spin boxes,
# labels, group boxes, scroll bars)
BUILTIN = set(
    """objectName modal windowModality enabled geometry frameGeometry normalGeometry x y pos frameSize size width
    height rect childrenRect childrenRegion sizePolicy minimumSize maximumSize minimumWidth minimumHeight
    maximumWidth maximumHeight sizeIncrement baseSize palette font cursor mouseTracking tabletTracking
    isActiveWindow focusPolicy focus contextMenuPolicy updatesEnabled visible minimized maximized fullScreen
    sizeHint minimumSizeHint acceptDrops windowTitle windowIcon windowIconText windowOpacity windowModified
    toolTip toolTipDuration statusTip whatsThis accessibleName accessibleDescription layoutDirection
    autoFillBackground styleSheet locale windowFilePath inputMethodHints text icon iconSize shortcut checkable
    checked autoRepeat autoExclusive autoRepeatDelay autoRepeatInterval down editable count currentText
    currentIndex currentData maxVisibleItems maxCount insertPolicy sizeAdjustPolicy minimumContentsLength
    duplicatesEnabled frame modelColumn placeholderText value minimum maximum singleStep pageStep prefix suffix
    alignment readOnly title flat default autoDefault orientation margin indent wordWrap pixmap scaledContents
    textFormat displayText maxLength echoMode cursorPosition selectedText inputMask acceptableInput
    clearButtonEnabled tristate tracking sliderPosition sliderDown invertedAppearance invertedControls""".split()
)
USE = re.compile(r"""\.(?:setProperty|property)\(\s*["']([^"']+)["']""")


def test_no_builtin_property_names():
    """No dynamic property in gui/ is named like a property Qt already has."""
    found = []
    for name in sorted(os.listdir(GUI)):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(GUI, name), encoding="utf-8") as f:
            for no, line in enumerate(f, 1):
                for prop in USE.findall(line):
                    if prop in BUILTIN:
                        found.append(f"{name}:{no}: {prop!r}")
    assert not found, "these names belong to Qt – pick another one:\n" + "\n".join(found)


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
