"""Changes to the document itself, not only to its annotations: its page labels,
the view when it is opened, headers, footers and watermarks, and the order of
its pages (the mode Pages; py-foliation's engine, which works with pikepdf).

Each such change is made at once, on a working copy: the document, with its
annotations as they are in the window, is written to a file of the window's
own, the change is made there with pikepdf, and the window goes on with that
file (``work``), showing its pages and reading its annotations again. Save
writes it as the document (the annotations as they are then, too); until
then, the document's file is as it was. Each change is a step of the history
(a DocState: the file before it, the annotations and the page), so Undo goes
back through it as through the changes of the annotations.

Whatever reads the document (saving, the copies, the redacted copy, the
exports) reads ``file``: the working copy, if there is one, else the
document's file. ``path`` stays the document's own.
"""

from __future__ import annotations

import dataclasses
import tempfile
from pathlib import Path

import pikepdf

from ..annotate import annots
from ..annotate.annots import AnnotateError, Annotation
from ..core.interface import tr


@dataclasses.dataclass(frozen=True)
class DocState:
    """The document as it was before a change of the document itself (a step of the history)."""
    work: Path | None  # the working copy it was shown from (None: the document's file)
    annotations: tuple[Annotation, ...]
    page: int


class WorkingMixin:
    """(Mixed into MainWindow: it uses its attributes.)"""

    work: Path | None = None
    _work_dir: tempfile.TemporaryDirectory | None = None
    _works = 0

    @property
    def file(self) -> Path | None:
        """The file the document is read from: its working copy, if it has one, else its own."""
        return self.work or self.path

    def _new_work(self, suffix: str = "") -> Path:
        if self._work_dir is None:
            self._work_dir = tempfile.TemporaryDirectory(prefix="py-pdftools-")
        self._works += 1
        return Path(self._work_dir.name) / f"work-{self._works}{suffix}.pdf"

    def drop_work(self):
        """Forget the working copies (the document was saved, or another opened)."""
        self.work = None
        if self._work_dir is not None:
            self._work_dir.cleanup()
            self._work_dir = None
        if any(isinstance(s, DocState) for s in self.undo_stack + self.redo_stack):
            # (their working copies are gone; and the annotations of the steps before them are of other files)
            self.undo_stack.clear()
            self.redo_stack.clear()

    def _load_work(self, file: Path, page: int) -> list[Annotation] | None:
        """Show FILE (a working copy, or the document's own file), keeping the document's path."""
        path = self.path
        found = self._load(file, self.password, page)
        self.path = path
        if found is not None:
            self.work = None if file == path else file
        return found

    def transform(self, change, *args, page: int | None = None, message: str = "") -> bool:
        """Change the document itself with CHANGE(pdf, *ARGS) (a pikepdf.Pdf, changed in place), as a
        step of the history: see the module. PAGE: the page to show then (else the one shown).
        MESSAGE: for the status bar. Returns whether it was done."""
        if self.path is None:
            return False
        self.canvas.commit_text()
        self.keep_comment()
        before = DocState(self.work, tuple(self.annotations), self.page)
        written = self._new_work("-annotated")
        target = self._new_work()
        try:  # (the annotations of the window go into the document first: the change may move their pages)
            annots.write(self.file, self.annotations, written, self.password, shown=self.layers)
            with pikepdf.open(written, password=self.password) as pdf:
                change(pdf, *args)
                pdf.save(target, encryption=True if pdf.is_encrypted else None)
        except (AnnotateError, OSError, ValueError, pikepdf.PdfError) as e:
            self.status(str(e), error=True)
            return False
        finally:
            written.unlink(missing_ok=True)
        found = self._load_work(target, self.page if page is None else page)
        if found is None:
            return False
        self.undo_stack.append(before)
        self.redo_stack.clear()
        self.annotations = found
        self.selected = []
        self.document_changed()
        self.refresh()
        self.show_page(self.page)
        if message:
            self.status(message)
        return True

    def adopt_file(self, file: Path, message: str = "") -> bool:
        """Make the PDF FILE the document (the result of an imposition, applied), as a step of the history.
        Its annotations are those FILE has."""
        if self.path is None:
            return False
        before = DocState(self.work, tuple(self.annotations), self.page)
        target = self._new_work()
        try:
            target.write_bytes(file.read_bytes())
        except OSError as e:
            self.status(str(e), error=True)
            return False
        found = self._load_work(target, 0)
        if found is None:
            return False
        self.undo_stack.append(before)
        self.redo_stack.clear()
        self.annotations = found
        self.selected = []
        self.document_changed()
        self.refresh()
        if message:
            self.status(message)
        return True

    def _state(self) -> DocState:
        return DocState(self.work, tuple(self.annotations), self.page)

    def restore(self, state: DocState) -> bool:
        """Show the document as it was in STATE (undo, redo)."""
        found = self._load_work(state.work or self.path, state.page)
        if found is None:
            self.status(tr("{path} cannot be read: {error}", path=state.work, error=tr("it is gone")), error=True)
            return False
        self.annotations = list(state.annotations)
        self.selected = []
        self.document_changed()
        self.refresh()
        self.show_page(state.page)
        return True

    def document_changed(self):
        """(After a change of the document itself: what the modes keep of it is read again.)"""
        if hasattr(self, "workspace"):
            self.impose_document_changed()
