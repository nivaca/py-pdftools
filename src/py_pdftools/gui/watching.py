"""The document's file watched (mixed into MainWindow): when another program changes it on disk, the window
opens it again as it is now, at the same place, if nothing here is unsaved and the settings say so (Settings
> General, on by default); else it asks first. Its own saves are not taken for changes: the file's time and
size after each opening or saving are kept, and a change that leaves them so is no change. The file of its annotations
apart, if it has one (see storing.py), is watched with it."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QTimer
from PySide6.QtWidgets import QMessageBox

from ..core import config
from ..core.interface import tr

SETTLE_MS = 700  # (a program may write the file in several steps: it is read once they have stopped)


def stamp(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def reload_on() -> bool:
    try:
        return bool(config.get("reload"))
    except config.ConfigError:
        return True


class WatchMixin:
    """(Mixed into MainWindow: it uses its path, is_modified and open_path.)"""

    def _init_watch(self):
        self._watcher = QFileSystemWatcher(self)
        self._settle = QTimer(self, singleShot=True, interval=SETTLE_MS)
        self._watcher.fileChanged.connect(lambda _path: self._settle.start())
        self._settle.timeout.connect(self.file_changed)
        self._disk_stamp: tuple[int, int] | None = None
        self._asking_reload = False

    def _watched(self) -> list[Path]:
        """The files watched: the document's, and that of its annotations apart, if it has one."""
        if self.path is None:
            return []
        kept = getattr(self, "kept_file", None)
        return [self.path] + ([kept] if kept is not None and kept.is_file() else [])

    def _stamps(self) -> tuple:
        return tuple(stamp(p) for p in self._watched())

    def watch_file(self):
        """Watch the document's file (another's no longer), as it is now."""
        old = self._watcher.files()
        if old:
            self._watcher.removePaths(old)
        if self.path is not None:
            self._watcher.addPaths([str(p) for p in self._watched()])
            self._disk_stamp = self._stamps()

    def file_changed(self) -> bool:
        """The file changed on disk: opened again (or asked), unless the change was ours. True if reopened."""
        if self.path is None or self._asking_reload:
            return False
        now = stamp(self.path)
        if now is None:  # (gone: perhaps being replaced; looked at again in a moment)
            if not self.__dict__.get("_gone_once"):
                self._gone_once = True
                self._settle.start()
            else:
                self.status(tr("{file} is no longer on disk", file=self.path.name), error=True)
            return False
        self._gone_once = False
        # (a file replaced by a new one, as many programs save, is no longer watched: it is watched again)
        for p in self._watched():
            if str(p) not in self._watcher.files():
                self._watcher.addPath(str(p))
        now = self._stamps()
        if now == self._disk_stamp:
            return False
        self._disk_stamp = now  # (asked once for this change, not again)
        if self.is_modified() or not reload_on():
            self._asking_reload = True
            try:
                if not self.ask_reload():
                    return False
            finally:
                self._asking_reload = False
        return self.reload_file()

    def ask_reload(self) -> bool:
        text = tr("{file} has been changed by another program. Open it again as it is now?", file=self.path.name)
        if self.is_modified():
            text += "\n\n" + tr("What has not been saved here will be lost.")
        return QMessageBox.question(self, tr("The file has changed"), text) == QMessageBox.StandardButton.Yes

    def reload_file(self) -> bool:
        """The document opened again from its file, at the place shown; what was not saved is dropped."""
        if self.path is None:
            return False
        self.annotations, self.layers = list(self.saved), dict(self.saved_layers)
        self.drop_work()  # (nothing to ask about now: see open_path)
        done = self.open_path(self.path)
        if done:
            self.status(tr("{file} was opened again: another program changed it", file=self.path.name))
        return done
