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
        # El menú de Imponer va justo antes de Capas en la barra de menús.
        self.menuBar().insertMenu(self.m_layers.menuAction(), self.workspace.menu)
        self.hints[KIND] = ""
        # Impose owns no annotation: the pages are not shown, so there is nothing to select.
        # (the pages are not shown: nothing to find, to move through or to zoom)
        return Mode(KIND, lambda a: False, menus=[self.workspace.menu.menuAction()],
                    without=("find", "navigation", "zoom", "pagezoom", "pagenav"),
                    entered=self._impose_entered, left=self._impose_left)

    def _impose_entered(self):
        # El área central pasa de las páginas al espacio de trabajo de Imponer, y vuelve al salir.
        self.central.setCurrentWidget(self.workspace)
        # Bookmarks lead to pages, which Impose doesn't show; and F5 is its Preview here (two actions with one
        # key: Qt would run neither). Their panel comes back, as it was, on leaving.
        self._outline_before_impose = self.outline_dock.isVisibleTo(self)
        self.outline_dock.hide()
        self.a_outline.setEnabled(False)
        self.give_impose_source()

    def _impose_left(self):
        self.central.setCurrentWidget(self.splitter)
        self.a_outline.setEnabled(True)
        self.outline_dock.setVisible(getattr(self, "_outline_before_impose", False))

    def impose_source(self) -> Path | None:
        """The file to impose: the document's own, or, if it has changes not yet saved, a copy with them."""
        if self.path is None:
            return None
        # Nothing unsaved: the document's own file is imposed as it is, with no copy.
        if self.work is None and self.annotations == self.saved:
            return self.path
        # La copia va a la carpeta temporal de la ventana, con las copias de trabajo; cada clave nueva deja otra, y
        # drop_work las borra todas juntas.
        target = self._new_work("-impose")
        try:
            annots.write(self.file, self.annotations, target, self.password, shown=self.layers)
        except AnnotateError as e:
            self.status(str(e), error=True)
            return None
        return target

    def give_impose_source(self):
        """Give the workspace the document as it is now (if that changed since it was last given)."""
        # Archivo, fecha de modificación y anotaciones: si nada de eso cambió, el espacio de trabajo no recibe una
        # copia nueva.
        key = (self.file, self.file.stat().st_mtime_ns if self.file else None, tuple(self.annotations))
        if key == self._impose_key:
            return
        self._impose_key = key
        ws = self.workspace
        ws.original = self.path
        ws.set_source(self.impose_source())

    def impose_document_changed(self):
        # Only while the mode is on; on entering it, give_impose_source runs anyway.
        if self.mode == KIND:
            self.give_impose_source()
