"""The sidebar as its own window (1.20.1).

The button left of the page takes the sidebar (Seiten, Prüfung, Farbe, Ausgabevorschau, Bearbeiten …) out of the
document window into a window of its own and docks it back when pressed again. The window always shows the panels
of the document in front: it follows the tabs of its frame (TabHost). Closing it docks the panels back; it closes
together with its frame.

The panels are the document window's own QDockWidgets – they are moved between the two main windows, nothing is
built twice, so everything in them (check results, colours, thumbnails …) stays as it is.
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow

from ..l10n import tr

LEFT = Qt.DockWidgetArea.LeftDockWidgetArea


def frame_of(win):
    """The window the sidebar window belongs to: the tab frame of the document, otherwise the window itself."""
    return getattr(win, "_host", None) or win


def window_of(win, create: bool = False):
    """The sidebar window of the frame of ``win`` (None if there is none yet and ``create`` is off)."""
    f = frame_of(win)
    sb = getattr(f, "_pm_sidebar", None)
    if sb is None and create:
        sb = SidebarWindow(f)
        f._pm_sidebar = sb
    return sb


def is_floating(win) -> bool:
    """Is the sidebar of the frame of ``win`` out in its own window?"""
    sb = window_of(win)
    return bool(sb is not None and sb.active)


def release(win):
    """Document window ``win`` closes: its panels must come home first (they are deleted with it)."""
    sb = window_of(win)
    if sb is None:
        return
    if frame_of(win) is win:  # no tab frame: the sidebar window goes with this window
        sb.shutdown()
    elif sb.owner is win:
        sb.give_back()


def refresh(frame):
    """Update the sidebar button of every document window of ``frame``."""
    wins = frame.windows() if hasattr(type(frame), "windows") else [frame]
    for w in wins:
        try:
            w._sidebar_shown()
        except (AttributeError, RuntimeError):  # still being built / already deleted
            pass


def _alive(obj) -> bool:
    if obj is None:
        return False
    try:
        import shiboken6
    except ImportError:
        return True
    return shiboken6.isValid(obj)


def _move(docks: list, src, dst):
    """Move the panels ``docks`` from main window ``src`` to ``dst``, as tabs in this order. Open panels stay
    open, the one in front stays in front. Returns the panel in front."""
    open_ = [d for d in docks if d.toggleViewAction().isChecked()]
    front = next((d for d in open_ if d.isVisible()), open_[0] if open_ else None)
    for d in docks:
        src.removeDockWidget(d)
    first = docks[0]
    dst.addDockWidget(LEFT, first)
    for d in docks[1:]:
        dst.addDockWidget(LEFT, d)
        dst.tabifyDockWidget(first, d)
    for d in docks:
        d.setVisible(d in open_)
    if front is not None:
        QTimer.singleShot(0, front.raise_)
    return front


class SidebarWindow(QMainWindow):
    """Own window for the sidebar of one frame; holds the panels of the document in front (``owner``)."""

    def __init__(self, frame):
        super().__init__(frame, Qt.WindowType.Window)
        self.frame = frame
        self.owner = None  # document window whose panels are here
        self.held = []  # its panels, in tab order
        self.active = False  # sidebar is out (also while no document is in front)
        self._keys = []  # its keyboard shortcuts, so they also work in this window
        self._geom = None
        self._width = 0
        self._busy = False
        self._watched = set()
        self.setObjectName("sidebarWindow")
        self.setWindowTitle(tr("Seitenleiste"))
        self.setDockNestingEnabled(True)

    # ---------------------------------------------------------------- #
    def open_for(self, owner):
        """Take the sidebar of ``owner`` out into this window."""
        self.active = True
        self.take(owner)
        self._place()
        self.show()
        self.raise_()
        refresh(self.frame)

    def dock(self):
        """Back into the document window (button pressed again or window closed)."""
        if self.isVisible():
            self._geom = self.saveGeometry()
        self.active = False
        self.give_back()
        self.hide()
        refresh(self.frame)

    def shutdown(self):
        """The frame closes: panels home, window gone."""
        self.active = False
        self.give_back()
        self.hide()
        self.deleteLater()
        if getattr(self.frame, "_pm_sidebar", None) is self:
            self.frame._pm_sidebar = None

    # ---------------------------------------------------------------- #
    def take(self, owner):
        """Show the panels of ``owner`` (the document now in front); the previous one gets its own back."""
        if owner is self.owner:
            return
        self.give_back()
        if owner is None or not _alive(owner):
            self.hide()  # no document in front – comes back with the next one
            return
        docks = owner._left_docks()
        if not docks:
            return
        if not any(d.toggleViewAction().isChecked() for d in docks):
            owner._pages_dock.show()  # nothing open: at least the pages
        shown = [d.width() for d in docks if d.isVisible()]
        self._width = max(shown) if shown else self._width
        self._busy = True
        try:
            _move(docks, owner, self)
        finally:
            self._busy = False
        self.owner, self.held = owner, docks
        for d in docks:
            if id(d) not in self._watched:
                self._watched.add(id(d))
                d.visibilityChanged.connect(lambda vis, d=d: self._dock_shown(d, vis))
        self._keys = [a for a in owner.findChildren(QAction) if not a.shortcut().isEmpty()]
        self.addActions(self._keys)
        name = getattr(owner, "display_name", "") or ""
        self.setWindowTitle(tr("Seitenleiste – {0}").format(name) if name else tr("Seitenleiste"))
        if self.active and not self.isVisible():
            self.show()
        refresh(self.frame)  # e.g. a newly opened document: its button shows "dock back"

    def give_back(self):
        """Put the panels back into the document window they belong to."""
        owner, held = self.owner, self.held
        self.owner, self.held = None, []
        for a in self._keys:
            self.removeAction(a)
        self._keys = []
        if not held:
            return
        if not _alive(owner):  # its window is gone – the panels go too
            for d in held:
                d.deleteLater()
            return
        width = self.width() if self.isVisible() else self._width
        self._busy = True
        try:
            front = _move(held, self, owner)
        finally:
            self._busy = False
        if front is not None and width:
            QTimer.singleShot(
                0, lambda: _alive(owner) and owner.resizeDocks([front], [width], Qt.Orientation.Horizontal)
            )

    # ---------------------------------------------------------------- #
    def _dock_shown(self, d, vis: bool):
        """A panel is brought up from the program (e.g. Ctrl+Alt+Y): show this window in front."""
        if vis and self.active and not self._busy and d in self.held and not self.isActiveWindow():
            self.show()
            self.raise_()

    def _place(self):
        """First time beside the frame (left of it if there is room), later where it was."""
        if self._geom is not None and self.restoreGeometry(self._geom):
            return
        fr = self.frame.frameGeometry()
        scr = self.frame.screen().availableGeometry()
        w = max(int(self._width or 0), 260)
        h = min(fr.height(), scr.height() - 60)
        x = fr.left() - w - 12
        if x < scr.left():
            x = fr.left() + 40
        self.setGeometry(x, max(fr.top(), scr.top() + 30), w, h)

    def closeEvent(self, e):
        if self.active:  # the window's own close button: dock back
            self._geom = self.saveGeometry()
            self.active = False
            self.give_back()
            refresh(self.frame)
        e.accept()
