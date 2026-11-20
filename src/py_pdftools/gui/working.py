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

The working copies are on disk, in the cache folder (see work_root), not in
the temporary folder: on many systems (Fedora's /tmp) that is in memory,
where each copy of a large document would take as much RAM. The history keeps
at most MAX_DOC_STEPS of them; older steps are forgotten, and their files
removed.
"""

from __future__ import annotations

import dataclasses
import os
import shutil
import tempfile
import time
from pathlib import Path

import pikepdf

from ..annotate import annots
from ..annotate.annots import AnnotateError, Annotation
from ..core.interface import tr


MAX_DOC_STEPS = 10  # changes of the document itself kept in the history (each with a copy of the file)
STALE_DAYS = 2  # folders of working copies older than this, left by a program that stopped, are removed
_cleaned = False


def work_root() -> Path | None:
    """The folder of the working copies, on disk: the cache folder (LOCALAPPDATA on Windows, else
    XDG_CACHE_HOME or ~/.cache), py-pdftools/work. None if it can't be made (then the temporary folder is
    used). The first time, folders left there by a program that stopped are removed."""
    global _cleaned
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        base = Path(os.environ["LOCALAPPDATA"])
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    root = base / "py-pdftools" / "work"
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    if not _cleaned:
        _cleaned = True
        # Solo las carpetas viejas: las de otra ventana abierta ahora, en otro proceso, son recientes.
        limit = time.time() - STALE_DAYS * 86400
        for folder in root.iterdir():
            try:
                if folder.is_dir() and folder.stat().st_mtime < limit:
                    shutil.rmtree(folder, ignore_errors=True)
            except OSError:
                pass
    return root


@dataclasses.dataclass(frozen=True)
class DocState:
    """The document as it was before a change of the document itself (a step of the history)."""
    work: Path | None  # the working copy it was shown from (None: the document's file)
    annotations: tuple[Annotation, ...]  # (as the window had them)
    page: int
    in_file: tuple[Annotation, ...] = ()  # the annotations as that file has them (see file_annotations)
    stamp: tuple | None = None  # (the time and size of that file then: if it changed, it is read again)


class WorkingMixin:
    """(Mixed into MainWindow: it uses its attributes.)"""

    work: Path | None = None
    _work_dir: tempfile.TemporaryDirectory | None = None
    # A counter for the names of the working copies: each change writes a new file, and the earlier ones
    # stay for undo.
    _works = 0
    # Lista de la clase como valor inicial; _load la reemplaza por una propia de cada ventana.
    # the annotations as the file shown has them (as read() gives them), kept when it is loaded or written:
    # what writes it next needn't read them again (see known_in_file)
    file_annotations: list[Annotation] = []

    @property
    def file(self) -> Path | None:
        """The file the document is read from: its working copy, if it has one, else its own."""
        return self.work or self.path

    def file_stamp(self) -> tuple | None:
        """The time and size of the file shown (None if it can't be read)."""
        # _source gives (path, password, stamp, bare); only the stamp is wanted here.
        source = self._source(self.file, self.password, False) if self.file is not None else None
        return source[2] if source is not None else None

    def known_in_file(self) -> list[Annotation] | None:
        """The annotations of the file shown, if the window knows them: unless the file changed since it
        was read (another program wrote it); else None (it must be read)."""
        stamp = self.file_stamp()
        # Sin fuente (ningún documento) o sin marca (el archivo no se lee): None, y quien escribe vuelve a leerlo.
        if self.canvas.source is None or stamp is None or stamp != self.canvas.source[2]:
            return None
        return self.file_annotations

    def _new_work(self, suffix: str = "") -> Path:
        # One temporary folder per window, made on the first change and removed by drop_work (save, open, close).
        if self._work_dir is None:
            # (on Windows a file still open, by a rendering process, can't be removed: it is left, not an error)
            self._work_dir = tempfile.TemporaryDirectory(prefix="py-pdftools-", dir=work_root(),
                                                         ignore_cleanup_errors=True)
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

    def _load_work(self, file: Path, page: int, known: list[Annotation] | None = None) -> list[Annotation] | None:
        """Show FILE (a working copy, or the document's own file), keeping the document's path. KNOWN: its
        annotations, if they are known (they are not read again)."""
        # _load cambia self.path al archivo que abre; aquí se restituye, porque la copia de trabajo no es el documento.
        path = self.path
        found = self._load(file, self.password, page, known=known)
        self.path = path
        if found is not None:
            # Loading the document's own file (undo back to the start) means there is no working copy any more.
            self.work = None if file == path else file
        return found

    def _state(self) -> DocState:
        return DocState(self.work, tuple(self.annotations), self.page, tuple(self.file_annotations),
                        self.file_stamp())

    def _step(self, before: DocState, found: list[Annotation], message: str, page: int | None = None):
        """(A change of the document itself, made: BEFORE, its step of the history; FOUND, the annotations.)"""
        # Un cambio nuevo invalida lo que había para rehacer, como en change().
        self.undo_stack.append(before)
        self.redo_stack.clear()
        self._limit_doc_steps()
        self.annotations = found
        self.selected = []
        # document_changed lets the mode Impose take the new file as its source.
        self.document_changed()
        self.refresh()
        if page is not None:
            self.show_page(page)
        if message:
            self.status(message)

    def transform(self, change, *args, page: int | None = None, message: str = "") -> bool:
        """Change the document itself with CHANGE(pdf, *ARGS) (a pikepdf.Pdf, changed in place), as a
        step of the history: see the module. PAGE: the page to show then (else the one shown).
        MESSAGE: for the status bar. Returns whether it was done."""
        if self.path is None:
            return False
        # Lo que esté a medio escribir (texto en el lienzo, comentario en el panel) entra antes de la instantánea.
        self.canvas.commit_text()
        self.keep_comment()
        before = self._state()
        # Two files: the annotations are written into the first, pikepdf changes it and saves the second; the
        # first is removed in finally. (If the file shown has them as they are, it is the first: one write
        # less, of the whole document.)
        same = self._annotations_in_file()
        written = self.file if same else self._new_work("-annotated")
        target = self._new_work()
        try:  # (the annotations of the window go into the document first: the change may move their pages)
            if not same:
                annots.write(self.file, self.annotations, written, self.password, shown=self.layers,
                             original=self.known_in_file())
            with pikepdf.open(written, password=self.password) as pdf:
                change(pdf, *args)
                # Si el documento estaba cifrado, la copia conserva el mismo cifrado (encryption=True).
                pdf.save(target, encryption=True if pdf.is_encrypted else None)
        except (AnnotateError, OSError, ValueError, pikepdf.PdfError) as e:
            self.status(str(e), error=True)
            return False
        finally:
            if not same:
                written.unlink(missing_ok=True)
        # (pikepdf numbers the objects anew: the annotations are read again)
        found = self._load_work(target, self.page if page is None else page)
        if found is None:
            return False
        # self.page, not PAGE: _load_work has gone to PAGE already, clamped to the new number of pages.
        self._step(before, found, message, self.page)
        return True

    def edit_document(self, edit, message: str = "") -> bool:
        """Change the document itself with EDIT(doc) (a pymupdf.Document, changed in place), as a step of the
        history: a change that leaves its pages and annotations as they are (its page labels). Quicker than
        transform: it is made while the annotations are written, and they are not read again."""
        if self.path is None:
            return False
        self.canvas.commit_text()
        self.keep_comment()
        before = self._state()
        target = self._new_work()
        # result recibe las anotaciones tal como quedaron escritas: no hay que leerlas otra vez.
        result: list[Annotation] = []
        try:
            annots.write(self.file, self.annotations, target, self.password, shown=self.layers, result=result,
                         original=self.known_in_file(), edit=edit)
        except AnnotateError as e:
            self.status(str(e), error=True)
            return False
        found = self._load_work(target, self.page, known=result)
        if found is None:
            return False
        self._step(before, found, message, self.page)
        return True

    def adopt_file(self, file: Path, message: str = "") -> bool:
        """Make the PDF FILE the document (the result of an imposition, applied), as a step of the history.
        Its annotations are those FILE has."""
        if self.path is None:
            return False
        before = self._state()
        target = self._new_work()
        try:
            target.write_bytes(file.read_bytes())
        except OSError as e:
            self.status(str(e), error=True)
            return False
        # Una imposición cambia las páginas: se vuelve a la primera.
        found = self._load_work(target, 0)
        if found is None:
            return False
        self._step(before, found, message)
        return True

    def _limit_doc_steps(self):
        """Keep at most MAX_DOC_STEPS changes of the document in the history: the oldest steps go, up to
        and with the oldest of those changes, and the working copies no step needs any more are removed."""
        states = [i for i, s in enumerate(self.undo_stack) if isinstance(s, DocState)]
        if len(states) <= MAX_DOC_STEPS:
            return
        # (the steps before a change of the document are of its file then: they go with it)
        del self.undo_stack[:states[len(states) - MAX_DOC_STEPS - 1] + 1]
        if self._work_dir is None:
            return
        needed = {self.work} | {s.work for s in self.undo_stack + self.redo_stack if isinstance(s, DocState)}
        for file in Path(self._work_dir.name).glob("work-*.pdf"):
            if file not in needed:
                file.unlink(missing_ok=True)

    def _annotations_in_file(self) -> bool:
        """Whether the file shown has the annotations (and layers) of the window, as they are: then a change
        made with pikepdf can start from it, without writing them first."""
        known = self.known_in_file()
        if known is None or list(self.annotations) != list(known):
            return False
        in_file = annots.layers(self.doc) if self.doc is not None else {}
        return all(in_file.get(name) == on for name, on in self.layers.items())

    def restore(self, state: DocState) -> bool:
        """Show the document as it was in STATE (undo, redo)."""
        # work None in STATE: the step goes back to the document's own file.
        file = state.work or self.path
        source = self._source(file, self.password, False)
        # Si el archivo no cambió desde la instantánea, sus anotaciones se reutilizan sin releerlo.
        known = list(state.in_file) if source is not None and source[2] == state.stamp else None
        found = self._load_work(file, state.page, known=known)
        if found is None:
            self.status(tr("{path} cannot be read: {error}", path=state.work, error=tr("it is gone")), error=True)
            return False
        # Las anotaciones de la ventana se reponen después de cargar: pueden diferir de las del archivo (sin guardar).
        self.annotations = list(state.annotations)
        self.selected = []
        self.document_changed()
        self.refresh()
        self.show_page(state.page)
        return True

    def document_changed(self):
        """(After a change of the document itself: what the modes keep of it is read again.)"""
        # The workspace exists only once the mode Impose has been built.
        if hasattr(self, "workspace"):
            self.impose_document_changed()
