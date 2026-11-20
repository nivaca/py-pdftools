"""The mode Impose of the window (from py-imposition): booklets, n-up, step
and repeat, the rest of its commands, sequences and hot folders, in py-
imposition's own workspace (impose/workspace.py), which takes the place of
the pages in the middle of the window while the mode is on.

What is imposed is the document as it is in the window: if it has changes
not yet saved (its annotations, or changes of the mode Pages), it is written
to a copy first, and that is imposed (see impose_source). Applying a result
makes it the document, as a step of the history (see working.py).
"""

from __future__ import annotations

from pathlib import Path

from ..annotate import annots
from ..annotate.annots import AnnotateError
from .impose.workspace import Workspace
from .modes import Mode

KIND = "impose"


class ImposeMixin:
    """(Mixed into MainWindow: it uses its attributes.)"""

    def _build_impose(self) -> Mode:
        self.workspace = Workspace(self)
        self.central.addWidget(self.workspace)
        self._impose_key = None  # (what the source given to the workspace was made from)
        self.menuBar().insertMenu(self.m_layers.menuAction(), self.workspace.menu)
        self.hints[KIND] = ""
        # (the pages are not shown: nothing to find, to move through or to zoom)
        return Mode(KIND, lambda a: False, menus=[self.workspace.menu.menuAction()],
                    without=("find", "navigation", "zoom"),
                    entered=self._impose_entered, left=self._impose_left)

    def _impose_entered(self):
        self.central.setCurrentWidget(self.workspace)
        self.give_impose_source()

    def _impose_left(self):
        self.central.setCurrentWidget(self.splitter)

    def impose_source(self) -> Path | None:
        """The file to impose: the document's own, or, if it has changes not yet saved, a copy with them."""
        if self.path is None:
            return None
        if self.work is None and self.annotations == self.saved:
            return self.path
        target = self._new_work("-impose")
        try:
            annots.write(self.file, self.annotations, target, self.password, shown=self.layers)
        except AnnotateError as e:
            self.status(str(e), error=True)
            return None
        return target

    def give_impose_source(self):
        """Give the workspace the document as it is now (if that changed since it was last given)."""
        key = (self.file, self.file.stat().st_mtime_ns if self.file else None, tuple(self.annotations))
        if key == self._impose_key:
            return
        self._impose_key = key
        ws = self.workspace
        ws.original = self.path
        ws.set_source(self.impose_source())

    def impose_document_changed(self):
        if self.mode == KIND:
            self.give_impose_source()
