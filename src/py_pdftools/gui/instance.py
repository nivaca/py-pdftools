"""Running in the background, to open documents faster (the setting 'background'): when the last window is
closed, the program goes on running, with its processes of rendering ready, and a tray icon (where the
desktop has one) to open a window again or quit; and py-pdftools-gui, started again, gives the files it is
asked to open to the program running (through a local socket), which opens them at once, instead of
starting another one.

File > Quit (and the tray's Quit) ends it, after each window has asked about what is not saved.
"""

from __future__ import annotations

import getpass
import json
import os
from pathlib import Path

from PySide6.QtCore import QObject
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from ..core import config
from ..core.interface import tr

TIMEOUT_MS = 1500  # (to reach the program running: if it doesn't answer by then, another one is started)


# (a Unix socket's path can't be longer than about 108 bytes)
MAX_PATH = 100


def server_name() -> str:
    """The local socket of the program running: PY_PDFTOOLS_SOCKET if set (the tests' own); in the user's
    runtime folder where there is one (only the user can reach it); else a name of the user's."""
    if os.environ.get("PY_PDFTOOLS_SOCKET"):
        return os.environ["PY_PDFTOOLS_SOCKET"]
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime and Path(runtime).is_dir() and len(str(Path(runtime) / "py-pdftools.socket")) <= MAX_PATH:
        return str(Path(runtime) / "py-pdftools.socket")
    try:
        user = getpass.getuser()
    except (OSError, KeyError):
        user = "user"
    return f"py-pdftools-{user}"


def enabled() -> bool:
    """Whether the setting says to keep running in the background."""
    try:
        return bool(config.get("background"))
    except config.ConfigError:
        return False


def running() -> bool:
    """Whether the program runs in the background already (it answers a ping, and opens nothing)."""
    socket = QLocalSocket()
    socket.connectToServer(server_name())
    if not socket.waitForConnected(TIMEOUT_MS):
        return False
    socket.write(json.dumps({"ping": True}).encode() + b"\n")
    ok = socket.waitForBytesWritten(TIMEOUT_MS) and socket.waitForReadyRead(TIMEOUT_MS) and \
        socket.readAll().data().strip() == b"ok"
    socket.disconnectFromServer()
    return ok


def send(files: list[str]) -> bool:
    """Give FILES (paths; none: just a window) to the program running in the background, if there is one.
    Whether it took them."""
    socket = QLocalSocket()
    socket.connectToServer(server_name())
    if not socket.waitForConnected(TIMEOUT_MS):
        return False
    from .navigation import split_place

    def absolute(arg: str) -> str:  # (the file made absolute, its place kept: book.pdf#page=3)
        path, place = split_place(arg)
        rest = arg[len(path):] if place else ""
        return str(Path(path).resolve()) + rest

    message = json.dumps({"open": [absolute(f) for f in files]}).encode() + b"\n"
    socket.write(message)
    if not socket.waitForBytesWritten(TIMEOUT_MS):
        return False
    # (the answer says it was read: else a program that is ending could lose the files)
    ok = socket.waitForReadyRead(TIMEOUT_MS) and socket.readAll().data().strip() == b"ok"
    socket.disconnectFromServer()
    return ok


class Instance(QObject):
    """The program running in the background: its server (see send) and its tray icon. OPEN(path or None)
    opens a window (with the document at path)."""

    def __init__(self, open_window, quit_all, parent=None):
        super().__init__(parent)
        self.open_window, self.quit_all = open_window, quit_all
        self.server: QLocalServer | None = None
        self.tray = None

    def start(self) -> bool:
        """Listen for the files of other starts, and show the tray icon. Whether the server could start."""
        from PySide6.QtWidgets import QApplication

        if self.server is None:
            # (a socket left by a program that stopped is removed first; one that runs answers send, and then
            # this one is never started)
            QLocalServer.removeServer(server_name())
            self.server = QLocalServer(self)
            self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
            self.server.newConnection.connect(self._connection)
            if not self.server.listen(server_name()):
                self.server = None
                return False
        QApplication.instance().setQuitOnLastWindowClosed(False)
        self._show_tray()
        return True

    def stop(self):
        """Back to a program that ends with its last window."""
        from PySide6.QtWidgets import QApplication

        if self.server is not None:
            self.server.close()
            self.server = None
        if self.tray is not None:
            self.tray.hide()
            self.tray = None
        QApplication.instance().setQuitOnLastWindowClosed(True)

    def _connection(self):
        while self.server is not None and self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            # The other start writes its line as soon as it is connected: it is waited for here (a moment, at
            # most TIMEOUT_MS), rather than left to a signal that may come before it is connected.
            while not socket.canReadLine() and socket.waitForReadyRead(TIMEOUT_MS):
                pass
            self._read(socket)

    def _read(self, socket: QLocalSocket):
        if not socket.canReadLine():
            return
        try:
            message = json.loads(socket.readLine().data().decode())
            files = message.get("open", [])
        except (ValueError, AttributeError):
            message, files = {}, []
        socket.write(b"ok\n")
        # (written before hanging up: else the answer may be lost, and the other start opens a window too)
        socket.waitForBytesWritten(TIMEOUT_MS)
        socket.disconnectFromServer()
        if isinstance(message, dict) and message.get("ping"):  # (only whether it runs: see running)
            return
        for path in files or [None]:
            self.open_window(path or None)

    def _show_tray(self):
        from PySide6.QtWidgets import QMenu, QSystemTrayIcon

        from . import app_icon

        if self.tray is not None or not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip(tr("py-pdftools (in the background)"))
        menu = QMenu()
        menu.addAction(tr("New window"), lambda: self.open_window(None))
        menu.addSeparator()
        menu.addAction(tr("Quit py-pdftools"), self.quit_all)
        self.tray.setContextMenu(menu)
        self._menu = menu  # (kept: the tray doesn't own it)
        self.tray.activated.connect(lambda reason: self.open_window(None)
                                    if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()
