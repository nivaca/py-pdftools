"""Tabs and a split view: several documents in one window. A TabHost holds windows (MainWindow, each with its
document, its menus, its panels and its undo) as tabs, on one side or on two side by side (the split view),
so that two documents can be read beside each other. A tab is moved to the other side, or to a window of its
own, from its menu (a right click on it) or from View; File > Open in a new tab (Ctrl+T) adds one, and with
Settings > General > "Open documents in tabs" every document opened goes into a tab.

A window in a tab works as a window of its own; only its shortcuts are bound to it (they act where the focus
is, so that two windows side by side don't take each other's keys)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow, QMenu, QSplitter, QTabWidget

from ..core.interface import tr

_HOSTS: list[TabHost] = []


class TabHost(QMainWindow):
    """A window of tabs, on one side or two (see the module's text)."""

    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.closing = False
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.sides: list[QTabWidget] = [self._side(), self._side()]
        self.sides[1].hide()  # (until a tab is put there: the split view)
        self.setCentralWidget(self.splitter)
        self.resize(1360, 900)
        _HOSTS.append(self)

    def _side(self) -> QTabWidget:
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.setTabsClosable(True)
        tabs.setMovable(True)
        tabs.tabCloseRequested.connect(lambda i, t=tabs: t.widget(i).close())
        tabs.currentChanged.connect(lambda _i: self._title())
        tabs.tabBar().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tabs.tabBar().customContextMenuRequested.connect(lambda pos, t=tabs: self._menu(t, pos))
        self.splitter.addWidget(tabs)
        return tabs

    # ----------------------------------------------------------------- the windows in it

    def windows(self) -> list:
        return [t.widget(i) for t in self.sides for i in range(t.count())]

    def side_of(self, win) -> QTabWidget | None:
        return next((t for t in self.sides if t.indexOf(win) >= 0), None)

    def current(self):
        """The window of the tab in use (that with the focus, or the one in front on the left)."""
        for win in self.windows():
            if win.isAncestorOf(self.focusWidget()) if self.focusWidget() is not None else False:
                return win
        return self.sides[0].currentWidget() or self.sides[1].currentWidget()

    def add(self, win, side: int = 0, front: bool = True):
        """WIN as a tab, on SIDE (0, the left; 1, the right)."""
        win.host = self
        win.setWindowFlags(Qt.WindowType.Widget)
        win.menuBar().setNativeMenuBar(False)
        keep_shortcuts_inside(win)
        tabs = self.sides[side]
        index = tabs.addTab(win, self._tab_text(win))
        tabs.setTabToolTip(index, str(win.path) if win.path is not None else "")
        win.windowTitleChanged.connect(lambda _t, w=win: self._retitle(w))
        tabs.show()
        win.show()
        self.tab_bars()
        if front:
            self.show_window(win)

    def show_window(self, win):
        tabs = self.side_of(win)
        if tabs is not None:
            tabs.setCurrentWidget(win)
        self.show()
        self.raise_()
        self.activateWindow()
        win.canvas.setFocus()
        self._title()

    def take(self, win):
        """WIN out of its tab (it stays as it is, hidden)."""
        tabs = self.side_of(win)
        if tabs is not None:
            tabs.removeTab(tabs.indexOf(win))
        win.host = None
        for act in win.findChildren(QAction):
            if act.shortcutContext() == Qt.ShortcutContext.WidgetWithChildrenShortcut:
                act.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
                win.removeAction(act)
        win.setParent(None)
        win.setWindowFlags(Qt.WindowType.Window)
        self._tidy()

    def window_closed(self, win):
        """WIN closed itself (its Close, or the tab's ×): its tab goes; the window too, with the last."""
        tabs = self.side_of(win)
        if tabs is not None:
            tabs.removeTab(tabs.indexOf(win))
        win.host = None
        # (out of this window, hidden, as a window closed by itself stays: it must not go when this one is deleted)
        win.setParent(None)
        win.setWindowFlags(Qt.WindowType.Window)
        win.hide()
        self._tidy()

    def _tidy(self):
        # (a side left without tabs is hidden: the split view ends; with none at all, the window goes)
        if not self.sides[0].count() and self.sides[1].count():
            while self.sides[1].count():
                w = self.sides[1].widget(0)
                text = self.sides[1].tabText(0)
                self.sides[1].removeTab(0)
                self.sides[0].addTab(w, text)
        self.sides[1].setVisible(bool(self.sides[1].count()))
        self.tab_bars()
        if not self.windows() and not self.closing:
            self.close()
        else:
            self._title()

    def tab_bars(self):
        """The tabbars hidden while there is only one tab, unless Settings > General > Show the tabbar
        with only one document says otherwise; with the view split, always shown (each side's tab has its
        menu there, to bring it back)."""
        from ..core import config

        try:
            lone = bool(config.get("lone_tab"))
        except config.ConfigError:
            lone = False
        split = bool(self.sides[1].count())
        for tabs in self.sides:
            tabs.setTabBarAutoHide(not (lone or split))

    # ----------------------------------------------------------------- moving tabs

    def move_to_other_side(self, win) -> bool:
        """WIN to the other side (the split view begins or ends); not the only tab."""
        tabs = self.side_of(win)
        if tabs is None or len(self.windows()) < 2:
            return False
        other = self.sides[1] if tabs is self.sides[0] else self.sides[0]
        text = tabs.tabText(tabs.indexOf(win))
        tabs.removeTab(tabs.indexOf(win))
        other.addTab(win, text)
        other.show()
        win.show()
        other.setCurrentWidget(win)
        self._tidy()
        if not self.sides[1].count():
            self.sides[1].hide()
        else:
            self.splitter.setSizes([1, 1])
        return True

    def detach(self, win):
        """WIN to a window of its own."""
        geometry = self.geometry()
        self.take(win)
        win.setGeometry(geometry.translated(40, 40))
        win.show()
        win.raise_()
        win.activateWindow()

    def _menu(self, tabs: QTabWidget, pos):
        index = tabs.tabBar().tabAt(pos)
        if index < 0:
            return
        win = tabs.widget(index)
        menu = QMenu(self)
        other = menu.addAction(tr("Move to the other side"), lambda: self.move_to_other_side(win))
        other.setEnabled(len(self.windows()) > 1)
        menu.addAction(tr("Move to a window of its own"), lambda: self.detach(win))
        menu.addSeparator()
        menu.addAction(tr("Close"), win.close)
        menu.exec(tabs.tabBar().mapToGlobal(pos))

    # ----------------------------------------------------------------- titles

    @staticmethod
    def _tab_text(win) -> str:
        return win.path.name if win.path is not None else tr("No document")

    def _retitle(self, win):
        tabs = self.side_of(win)
        if tabs is not None:
            i = tabs.indexOf(win)
            tabs.setTabText(i, self._tab_text(win))
            tabs.setTabToolTip(i, str(win.path) if win.path is not None else "")
        self._title()

    def _title(self):
        win = self.current()
        if win is not None:
            self.setWindowTitle(win.windowTitle())

    def closeEvent(self, event):
        # Cada pestaña se cierra como una ventana (y pregunta por lo que no se guardó); si una se queda, todo se queda.
        self.closing = True
        try:
            for win in list(self.windows()):
                if not win.close():
                    event.ignore()
                    return
        finally:
            self.closing = False
        if self in _HOSTS:
            _HOSTS.remove(self)
        super().closeEvent(event)


def host_for_new_tab(near=None) -> TabHost:
    """The window of tabs a new tab goes to: NEAR's (wrapped in one, if it is a window by itself), else the last
    shown, else a new one."""
    if near is not None:
        if near.host is not None:
            return near.host
        host = TabHost()
        host.setGeometry(near.geometry())
        near_shown = near.isVisible()
        host.add(near)
        if near_shown:
            host.show()
        return host
    for host in reversed(_HOSTS):
        if host.isVisible():
            return host
    return TabHost()


def open_in_tab(path=None, near=None):
    """A new tab (with the document at PATH, a path or 'book.pdf#page=3'), beside NEAR's or in the last window
    of tabs; an empty tab there takes it instead."""
    from pathlib import Path

    from .navigation import split_place
    from .window import _WINDOWS, MainWindow

    host = host_for_new_tab(near)
    win = next((w for w in host.windows() if w.path is None), None) if path is not None else None
    if win is None:
        win = MainWindow()
        _WINDOWS.append(win)
        host.add(win)
    if path is not None:
        file, place = split_place(str(path))
        win.open_path(Path(file), place)
    host.show_window(win)
    return win


def apply_tab_bars():
    """The setting of the tabbars, in every window of tabs (when it changes)."""
    for host in list(_HOSTS):
        host.tab_bars()


def keep_shortcuts_inside(win, part=None):
    """The shortcuts of WIN (of PART of it, if given: one made after it became a tab) act only where the focus
    is: see the module's text."""
    for act in (part or win).findChildren(QAction):
        if act.shortcuts():
            act.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            win.addAction(act)
