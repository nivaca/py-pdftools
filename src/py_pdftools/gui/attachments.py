"""El panel Archivos adjuntos (Ver > Paneles, F9): los archivos que lleva el documento, los suyos (adjuntos al
documento entero, en /EmbeddedFiles) y los de sus páginas (las anotaciones Archivo adjunto), cada uno con su
nombre, su tamaño, dónde está y su descripción. Se abren con el programa del escritorio (doble clic o Intro), se
guardan uno a uno o todos en una carpeta, y se añaden o quitan; añadir uno al documento, quitarlo o cambiar uno
de página es un cambio más del documento, que se deshace como los otros."""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView, QDockWidget, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ..core.interface import ntr, tr

WHAT = Qt.ItemDataRole.UserRole  # (("doc", its name in the document) or ("page", the index of its annotation))


def size_text(n: int) -> str:
    """N bytes, as people say it: 512 B, 3.4 KB, 1.2 MB."""
    if n < 1024:
        return f"{n} B"
    for unit in ("KB", "MB", "GB"):
        n /= 1024
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}"
    return ""


class AttachmentsMixin:
    """(Mixed into MainWindow: it uses its attributes.)"""

    def _build_attachments(self):
        """The panel of the attached files: a dock of its own, hidden until it is asked for (F9)."""
        self.attach_list = tree = QTreeWidget()
        tree.setColumnCount(4)
        tree.setHeaderLabels([tr("File"), tr("Size"), tr("Where"), tr("Description")])
        tree.setRootIsDecorated(False)
        tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2):
            tree.header().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        tree.setAccessibleName(tr("Attached files"))
        # Doble clic o Intro: el archivo se abre; elegir uno de una página lleva a ella.
        tree.itemActivated.connect(lambda item, _c: self.open_attached(item))
        tree.currentItemChanged.connect(lambda item, _old: self._attached_chosen(item))
        tree.itemSelectionChanged.connect(self._attach_enable)
        self.attach_count = QLabel()
        self.attach_count.setStyleSheet("color: palette(placeholder-text);")
        buttons = QHBoxLayout()
        self.attach_buttons = {}
        for key, text, tip, slot in (
                ("open", tr("Open"), tr("Open the file chosen with the program of the desktop for it"),
                 lambda: self.open_attached(self.attach_list.currentItem())),
                ("save", tr("Save…"), tr("Save the files chosen, out of the document"), self.save_attached),
                ("add", tr("Add…"), tr("Attach files to the document (not to a page: for that, the tool Attach "
                                      "file)"), self.add_attached),
                ("remove", tr("Remove"), tr("Take the files chosen out of the document"), self.remove_attached)):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            buttons.addWidget(b)
            self.attach_buttons[key] = b
        buttons.addStretch(1)
        inner = QWidget()
        inner.setMinimumWidth(320)
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self.attach_count)
        lay.addWidget(tree, 1)
        lay.addLayout(buttons)
        self.attach_dock = dock = QDockWidget(tr("Attached files"), self)
        dock.setObjectName("attachments")
        dock.setWidget(inner)
        dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        dock.hide()
        dock.visibilityChanged.connect(lambda shown: self.attachments_refresh() if shown else None)
        self.a_attachments = dock.toggleViewAction()
        self.a_attachments.setText(tr("Attached files"))
        self.a_attachments.setShortcut(QKeySequence("F9"))
        self.a_attachments.setToolTip(tr("The files the document carries, attached to it or to its pages, to open "
                                         "or save them"))

    # ----------------------------------------------------------------- the list

    def attached_files(self) -> list[tuple[tuple, str, int, str, str]]:
        """Every file the document carries: (what it is, its name, its size, where, its description); those of
        the document first, then those of the pages, in page order."""
        out = []
        doc = self.doc
        if doc is None:
            return out
        try:
            names = doc.embfile_names()
        except (RuntimeError, ValueError):
            names = []
        for name in names:
            try:
                info = doc.embfile_info(name)
            except (RuntimeError, ValueError):  # (uno dañado no impide ver los demás)
                continue
            size = info.get("size") or info.get("length") or 0
            out.append((("doc", name), info.get("filename") or name, int(size), tr("Document"),
                        info.get("description") or info.get("desc") or ""))
        pages = sorted((a.page, i) for i, a in enumerate(self.annotations) if a.kind == "attachment")
        labels = self.page_labels() if pages else []
        for page, i in pages:
            a = self.annotations[i]
            label = labels[page] if page < len(labels) and labels[page] else str(page + 1)
            out.append((("page", i), a.filename or tr("(no name)"), len(a.data), tr("Page {page}", page=label),
                        a.contents or ""))
        return out

    def attachments_refresh(self):
        """The list, as the document is now (only while the panel is shown: it is filled again when it opens)."""
        if not self.attach_dock.isVisible():
            return
        tree = self.attach_list
        current = tree.currentItem().data(0, WHAT) if tree.currentItem() is not None else None
        tree.clear()
        found = self.attached_files()
        for what, name, size, where, desc in found:
            # (PyMuPDF da como descripción el nombre del archivo, si no hay otra: repetirlo no dice nada)
            desc = "" if desc.strip() == name else desc
            item = QTreeWidgetItem([name, size_text(size), where, desc])
            item.setData(0, WHAT, what)
            item.setToolTip(0, name)
            item.setToolTip(3, desc)
            item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            tree.addTopLevelItem(item)
            if what == current:
                tree.setCurrentItem(item)
        self.attach_count.setText(tr("No attached files") if not found else
                                  ntr("{count} attached file", "{count} attached files", len(found)))
        self._attach_enable()

    def _attach_enable(self):
        chosen = bool(self.attach_list.selectedItems())
        self.attach_buttons["open"].setEnabled(self.attach_list.currentItem() is not None)
        self.attach_buttons["save"].setEnabled(chosen)
        self.attach_buttons["remove"].setEnabled(chosen and self.path is not None)
        self.attach_buttons["add"].setEnabled(self.path is not None)

    def _attached_chosen(self, item):
        # (uno de una página: la página se muestra, sin elegir la anotación)
        what = item.data(0, WHAT) if item is not None else None
        if what is not None and what[0] == "page" and self.attach_list.hasFocus() and what[1] < len(self.annotations):
            self.show_page(self.annotations[what[1]].page)

    def attached_data(self, what: tuple) -> tuple[str, bytes] | None:
        """The name and the bytes of the file WHAT; None if it can't be read."""
        kind, key = what
        if kind == "doc":
            try:
                info = self.doc.embfile_info(key)
                return info.get("filename") or key, self.doc.embfile_get(key)
            except (RuntimeError, ValueError) as e:
                self.status(tr("{name} cannot be read: {error}", name=key, error=e), error=True)
                return None
        if key < len(self.annotations):
            a = self.annotations[key]
            return a.filename or "file", a.data
        return None

    # ----------------------------------------------------------------- what can be done with them

    def open_attached(self, item) -> Path | None:
        """The file of ITEM, written to a folder of its own and opened with the desktop's program for it."""
        if item is None:
            return None
        found = self.attached_data(item.data(0, WHAT))
        if found is None:
            return None
        name, data = found
        refused = self.refused_to_run(name or "file")
        if refused is not None:  # (it would run: not opened; saved, if the user asks)
            if refused:  # (this one, the one double-clicked)
                self.attach_list.clearSelection()
                item.setSelected(True)
                self.save_attached()
            return None
        path = Path(tempfile.mkdtemp(prefix="py-pdftools-")) / (Path(name).name or "file")
        try:
            path.write_bytes(data)
        except OSError as e:
            self.status(tr("{path} cannot be written: {error}", path=path, error=e), error=True)
            return None
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        return path

    def save_attached(self, folder: Path | None = None) -> list[Path]:
        """The files chosen, saved: one where the user says; several, in a folder (FOLDER, or one asked for)."""
        items = self.attach_list.selectedItems()
        if not items:
            return []
        files = [f for f in (self.attached_data(i.data(0, WHAT)) for i in items) if f is not None]
        if len(files) == 1 and folder is None:
            name, data = files[0]
            target, _ = QFileDialog.getSaveFileName(self, tr("Save the attached file"),
                                                    str(Path(self.last_dir()) / Path(name).name))
            if not target:
                return []
            targets = [(Path(target), data)]
        else:
            if folder is None:
                chosen = QFileDialog.getExistingDirectory(self, tr("Save the attached files in"), self.last_dir())
                if not chosen:
                    return []
                folder = Path(chosen)
            targets, used = [], set()
            for name, data in files:
                # (no se pisa nada: ni otro de los que se guardan con el mismo nombre, ni un archivo que ya esté)
                path = folder / (Path(name).name or "file")
                n = 2
                while path in used or path.exists():
                    path = folder / f"{Path(name).stem} ({n}){Path(name).suffix}"
                    n += 1
                used.add(path)
                targets.append((path, data))
        done = []
        for path, data in targets:
            try:
                path.write_bytes(data)
                done.append(path)
            except OSError as e:
                self.status(tr("{path} cannot be written: {error}", path=path, error=e), error=True)
                return done
        self.status(ntr("{count} file saved", "{count} files saved", len(done)) if len(done) > 1
                    else tr("Saved {path}", path=done[0]))
        return done

    def add_attached(self, paths: list[Path] | None = None) -> bool:
        """Files (PATHS, or those the user chooses) attached to the document, as a change of it."""
        if self.path is None:
            return False
        if paths is None:
            names, _ = QFileDialog.getOpenFileNames(self, tr("Attach files to the document"), self.last_dir())
            paths = [Path(n) for n in names]
        if not paths:
            return False
        try:
            files = [(p.name, p.read_bytes()) for p in paths]
        except OSError as e:
            self.status(str(e), error=True)
            return False

        def edit(doc):
            have = set(doc.embfile_names())
            for name, data in files:
                # (un nombre que ya está se cambia: el documento no admite dos iguales)
                key, n = name, 2
                while key in have:
                    key = f"{Path(name).stem} ({n}){Path(name).suffix}"
                    n += 1
                have.add(key)
                doc.embfile_add(key, data, filename=key)

        done = self.edit_document(edit, message=ntr("{count} file attached", "{count} files attached", len(files)))
        self.attachments_refresh()
        return done

    def remove_attached(self) -> bool:
        """The files chosen taken out of the document: those of the document, and the annotations of those of
        the pages (each kind a change of its own, undone as the others)."""
        whats = [i.data(0, WHAT) for i in self.attach_list.selectedItems()]
        if not whats or self.path is None:
            return False
        names = [key for kind, key in whats if kind == "doc"]
        indices = {key for kind, key in whats if kind == "page"}
        done = True
        if indices:  # (primero las de las páginas: quitar las del documento vuelve a leer las anotaciones)
            self.change([a for i, a in enumerate(self.annotations) if i not in indices], [])
        if names:
            def edit(doc):
                for name in names:
                    doc.embfile_del(name)

            done = self.edit_document(edit, message=ntr("{count} attached file removed",
                                                        "{count} attached files removed", len(names)))
        self.attachments_refresh()
        return done
