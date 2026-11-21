"""The copies of the document (flattened, without annotations, as PDF/A or PDF/X), printing, and
the export and import of the annotations: the part of the main window (see window.py) that writes
or reads other files than the document itself."""

from __future__ import annotations

import dataclasses
import os
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from ..core import conform

from ..annotate import annots, exchange
from ..annotate.annots import AnnotateError, PasswordError
from ..core.interface import ntr, tr
from . import colors
from .colors import color_name


def ask_save(parent, title: str, text: str) -> QMessageBox.StandardButton:
    """Ask whether to save what is unsaved before going on: Save (the default), Discard or Cancel."""
    box = QMessageBox(QMessageBox.Icon.Warning, title, text,
                      QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                      | QMessageBox.StandardButton.Cancel, parent)
    box.setDefaultButton(QMessageBox.StandardButton.Save)
    return QMessageBox.StandardButton(box.exec())


class FilesMixin:
    """Methods of MainWindow (which has the document, its annotations and the status line)."""

    # ----------------------------------------------------------------- new documents, from others

    def ask_new_pdf(self, title: str, name: str) -> Path | None:
        """Where to write a new PDF (NAME, in the last folder used, at first)."""
        chosen, _ = QFileDialog.getSaveFileName(self, title, str(Path(self.last_dir()) / name),
                                                tr("PDF files (*.pdf)"))
        if not chosen:
            return None
        target = Path(chosen)
        return target if target.suffix.lower() == ".pdf" else target.with_suffix(".pdf")

    def open_made(self, target: Path):
        """The PDF just made (TARGET), opened here if this window has no document, else in another."""
        if self.doc is None:
            return self if self.open_path(target) else None
        from . import open_window

        return open_window(target)

    def ask_combine(self):
        """(parts, options) chosen in the dialog of Combine files; None if cancelled."""
        from PySide6.QtWidgets import QDialog

        from .combine_dialog import CombineDialog

        dialog = CombineDialog(self, (self.path, self.password) if self.path is not None else None)
        return (dialog.parts(), dialog.options()) if dialog.exec() == QDialog.DialogCode.Accepted else None

    def combine_dialog(self):
        """File > Combine files: the PDF made of those chosen, opened. Returns its window (None if not made)."""
        from ..pages import combine
        from .redact import background

        chosen = self.ask_combine()
        if chosen is None:
            return None
        parts, options = chosen
        if self.path is not None and self.is_modified() and any(p.path == self.path for p in parts):
            # Se combina el archivo tal como está guardado: lo que no se guardó, antes.
            answer = ask_save(self, tr("Unsaved changes"),
                              tr("The files are combined as they are saved. Save the changes of this one first?"))
            if answer == QMessageBox.StandardButton.Cancel or \
                    answer == QMessageBox.StandardButton.Save and not self.save():
                return None
        target = self.ask_new_pdf(tr("Combine files"), "combined.pdf")
        if target is None:
            return None
        if self.path is not None and self._same_file(target):
            return None
        try:
            count = background.run(self, tr("Combining the files…"), combine.combine, parts, target,
                                   options["bookmarks"], options["labels"])
        except combine.CombineError as e:
            self.status(str(e), error=True)
            return None
        made = self.open_made(target)
        if made is not None:
            made.status(tr("Saved {path}", path=target) + " (" + ntr("{count} page", "{count} pages", count) + ")")
        return made

    # ----------------------------------------------------------------- passwords

    def protection_dialog(self) -> bool:
        """Protect the document's file with passwords, or remove its protection (see core/protection.py); the
        document is then opened again from it."""
        from ..core import protection

        if self.path is None:
            return False
        if self.is_modified():
            # La protección se pone al archivo tal como está guardado: lo que no se guardó, antes.
            answer = ask_save(self, tr("Unsaved changes"),
                              tr("The protection is put on the file as it is saved. Save the changes first?"))
            if answer != QMessageBox.StandardButton.Save or not self.save():
                return False
        key = self.password
        try:
            current = protection.read(self.path, key)
            if current.encrypted and not current.owner:
                # Abierto sin la contraseña de permisos: solo con ella se cambia la protección.
                key = self.ask_owner_password()
                if key is None:
                    return False
                current = protection.read(self.path, key)
                if not current.owner:
                    self.status(tr("That is not its permissions password"), error=True)
                    return False
        except protection.ProtectionError as e:
            self.status(str(e), error=True)
            return False
        chosen = self.ask_protection(current)
        if chosen is None:
            return False
        try:
            if chosen.get("remove"):
                protection.unprotect(self.path, self.path, key)
                opening = ""
            else:
                protection.protect(self.path, self.path, password=key, **chosen)
                opening = chosen["open_password"]
        except protection.ProtectionError as e:
            self.status(str(e), error=True)
            return False
        # The file changed under the window: opened again, with the new password, where it was.
        self.drop_work()
        if not self.open_path(self.path, password=opening):
            return False
        self.status(tr("{file} is no longer protected", file=self.path.name) if chosen.get("remove")
                    else tr("{file} is protected", file=self.path.name))
        return True

    def ask_owner_password(self) -> str | None:
        from PySide6.QtWidgets import QInputDialog, QLineEdit

        text, ok = QInputDialog.getText(self, tr("Permissions password"),
                                        tr("Its protection can be changed only with its permissions password:"),
                                        QLineEdit.EchoMode.Password)
        return text if ok and text else None

    def ask_protection(self, current) -> dict | None:
        """The protection chosen (see ProtectDialog.result_values); None if cancelled."""
        from PySide6.QtWidgets import QDialog

        from .protect_dialog import ProtectDialog

        dialog = ProtectDialog(current, self)
        return dialog.result_values() if dialog.exec() == QDialog.DialogCode.Accepted else None

    def _same_file(self, target: Path) -> bool:
        # resolve() sigue los enlaces simbólicos: un enlace al documento abierto también cuenta como él.
        if target.resolve() == self.path.resolve():
            self.status(tr("Choose another name: the document stays open"), error=True)
            return True
        return False

    def save_flattened_dialog(self) -> bool:
        if self.path is None:
            return False
        target = self._ask_target(tr("Save a flattened copy"), "-flattened")
        if target is None or self._same_file(target):
            return False
        # Lo que se está escribiendo en la página y en el campo de comentario entra en la copia.
        self.canvas.commit_text()
        self.keep_comment()
        try:
            # unmarked(): without the redaction boxes. Flattened, a box would only cover the text, which would
            # still be in the file.
            exchange.save_flattened(self.file, self.unmarked(), target, self.password)
        except AnnotateError as e:
            self.status(str(e), error=True)
            return False
        self.status(tr("Saved {path}, with the annotations made part of the pages", path=target))
        return True

    def save_without_dialog(self) -> bool:
        if self.path is None:
            return False
        target = self._ask_target(tr("Save a copy without annotations"), "-clean")
        if target is None or self._same_file(target):
            return False
        try:
            # Aquí no se llama a commit_text: el texto a medio escribir no importa en una copia sin anotaciones.
            count = exchange.save_without(self.file, target, self.password)
        except AnnotateError as e:
            self.status(str(e), error=True)
            return False
        self.status(tr("Saved {path}", path=target) + " — "
                    + ntr("{count} annotation taken out", "{count} annotations taken out", count))
        return True

    def save_standard_dialog(self, standard: str) -> bool:
        """Save a copy with the annotations as STANDARD ('a-2b', 'x-4'...), made by pdf2iso."""
        if self.path is None:
            return False
        # pdf2iso is an external script (it calls Ghostscript); without it there is nothing to do.
        if not conform.available():
            self.warn(conform.label(standard), tr("{command} is not installed (or not where Settings say)",
                                                  command=conform.COMMAND))
            return False
        target = self._ask_target(tr("Save a copy as {standard}", standard=conform.label(standard)),
                                  "-pdfx" if standard.startswith("x") else "-pdfa")
        if target is None or self._same_file(target):
            return False
        return self.save_standard(target, standard)

    def save_standard(self, target: Path, standard: str, flatten: set[str] = frozenset()) -> bool:
        """Write TARGET: a copy with the annotations (those of the kinds FLATTEN, made part of the
        pages), made STANDARD by pdf2iso. If Ghostscript leaves out annotations of some kinds,
        offer to do it again with those flattened."""
        self.canvas.commit_text()
        self.keep_comment()
        # El archivo intermedio va en la carpeta de destino, no en /tmp: así está en el mismo disco y
        # pdf2iso puede leerlo aunque /tmp sea pequeño o esté aislado.
        fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=target.parent)
        os.close(fd)
        tmp = Path(tmp)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.status(tr("Making {standard} with {command}…", standard=conform.label(standard),
                       command=conform.COMMAND))
        # Let the status line and the wait cursor be drawn before the long conversion starts.
        QApplication.processEvents()
        try:
            if flatten:
                exchange.save_partly_flattened(self.file, self.annotations, tmp, self.password, set(flatten))
            else:
                annots.write(self.file, self.annotations, tmp, self.password)
            check = conform.convert(tmp, target, standard, self.password)
            # Se comprueba en la copia hecha qué anotaciones se perdieron: Ghostscript descarta en silencio
            # algunos tipos al hacer PDF/A o PDF/X.
            kept = [a for a in self.annotations if a.kind not in flatten]
            lost = exchange.kinds_lost(kept, target)
        except (AnnotateError, conform.ConformError) as e:
            QApplication.restoreOverrideCursor()
            self.status("", error=False)
            self.warn(conform.label(standard), tr("The copy could not be made {standard}:\n\n{error}",
                                                  standard=conform.label(standard), error=e))
            return False
        finally:
            # The intermediate file goes away in every case, also after an error.
            tmp.unlink(missing_ok=True)
        QApplication.restoreOverrideCursor()
        if lost:
            from .window import tool_name

            names = ", ".join(f"{tool_name(kind).lower()} ({count})" for kind, count in lost.items())
            if self.ask_flatten_lost(conform.label(standard), names):
                # Ghostscript reads clouds as polygons, so a lost polygon may be a cloud: both are flattened.
                kinds = set(lost) | ({"cloud"} if "polygon" in lost else set())
                # Se repite todo con esos tipos aplanados; como cada vuelta aplana más tipos, termina.
                return self.save_standard(target, standard, set(flatten) | kinds)
        message = tr("Saved {path} as {standard}", path=target, standard=conform.label(standard))
        if check:
            message += f" ({check})"
        if flatten:
            message += " — " + tr("some annotations were made part of the pages")
        elif lost:
            message += " — " + ntr("{count} annotation was left out", "{count} annotations were left out",
                                   sum(lost.values()))
        # PDF/A and PDF/X forbid encryption, so the password is dropped from the copy.
        if self.password:
            message += " — " + tr("PDF/A and PDF/X can't be protected: the copy has no password")
        self.status(message)
        return True

    def save_searchable_dialog(self) -> bool:
        """Save a copy in which the text of the scanned pages is read (OCR), and offer to open it."""
        if self.path is None:
            return False
        from ..annotate import ocr

        if not ocr.available():
            self.warn(tr("Searchable (OCR)"), tr("Tesseract is not installed: there is no OCR"))
            return False
        # Solo tiene sentido si alguna página es una imagen sin texto.
        if not any(ocr.scanned(page) for page in self.doc):
            self.status(tr("No page of this document is a scan without text"), error=True)
            return False
        target = self._ask_target(tr("Save a searchable copy"), "-ocr")
        if target is None or self._same_file(target):
            return False
        return self.save_searchable(target)

    def save_searchable(self, target: Path) -> bool:
        from PySide6.QtWidgets import QProgressDialog

        from ..annotate import ocr

        self.canvas.commit_text()
        self.keep_comment()
        progress = QProgressDialog(tr("Reading the scanned pages…"), tr("Stop"), 0, 1, self)
        # Window-modal: the document cannot be changed while its pages are being read.
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(500)

        # Llamada por ocr.save_searchable tras cada página; devolver False detiene la lectura.
        def step(done: int, of: int) -> bool:
            progress.setMaximum(of)
            progress.setValue(done)
            progress.setLabelText(tr("Reading page {done} of {of}…", done=done + 1, of=of))
            QApplication.processEvents()
            return not progress.wasCanceled()

        try:
            pages, words = ocr.save_searchable(self.file, self.unmarked(), target, self.password,
                                               self.prefs.ocr_language, step)
        except AnnotateError as e:
            self.status(str(e), error=True)
            return False
        finally:
            progress.close()
        self.status(tr("Saved {path}", path=target) + " — "
                    + ntr("{count} page read", "{count} pages read", pages) + ", "
                    + ntr("{count} word", "{count} words", words))
        if self.ask_open_copy(target):
            self.open_path(target)  # (it asks first about what is not saved here: the copy has it, though)
        return True

    def ask_open_copy(self, target: Path) -> bool:
        return QMessageBox.question(self, tr("Searchable (OCR)"),
                                    tr("Open {name}, to mark its text?", name=target.name)) \
            == QMessageBox.StandardButton.Yes

    def compare_dialog(self) -> bool:
        if self.doc is None:
            return False
        name, _ = QFileDialog.getOpenFileName(self, tr("Compare with another version"), self.last_dir(),
                                              tr("PDF files (*.pdf)"))
        return self.compare_with(Path(name)) if name else False

    # Naranja: palabras cambiadas; rojo: solo aquí; azul: faltan aquí (están en la otra versión).
    COMPARE_COLORS = {"changed": "#ffb74d", "only_here": "#ef9a9a", "only_there": "#1e88e5"}

    def compare_with(self, other: Path) -> bool:
        """Mark on this document what differs from OTHER (another version of its text): words changed
        (with the other version's in the comment), words only here, and where words of the other are
        missing (an insert-text mark, with them); all tagged with the other's name, so that the list
        shows them alone, and one undo takes them back."""
        from ..annotate import compare

        # Se prueba sin contraseña y se pide una mientras sea incorrecta; None es que el usuario canceló.
        # TODO: este bucle de contraseña se repite casi igual en import_from; podría ser un método común.
        password = ""
        while True:
            try:
                there = annots.open_pdf(other, password)
                break
            except PasswordError:
                password = self.ask_password(other, again=bool(password))
                if password is None:
                    return False
            except AnnotateError as e:
                self.status(str(e), error=True)
                return False
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            found = compare.differences(self.doc, there)
            # Sin texto en alguno de los dos, 'sin diferencias' sería engañoso: se avisa aparte.
            empty = not compare.words(self.doc) or not compare.words(there)
        finally:
            there.close()
            QApplication.restoreOverrideCursor()
        if empty:
            self.status(tr("One of the two has no text to compare (a scan? Save a searchable copy first)"),
                        error=True)
            return False
        if not found:
            self.status(tr("No difference: the words of {name} are those of this document", name=other.name))
            return True
        # Una sola etiqueta con el nombre del otro archivo, para filtrarlas en la lista o borrarlas juntas.
        tag = tr("Compared with {name}", name=other.name)
        w, h = annots.CARET_SIZE
        new = []
        for d in found:
            color = self.COMPARE_COLORS[d.kind]
            if d.kind == "only_there":
                # The caret goes at the bottom right corner of the word before the gap, where the missing words go.
                x, y = d.rects[0][2], d.rects[0][3]
                a = self.new_annotation("caret", d.page, (x - w / 2, y - h / 2, x + w / 2, y + h / 2))
                text = tr("In {name}, here: {words}", name=other.name, words=d.there)
            else:
                a = self.new_annotation("highlight", d.page, annots.union(list(d.rects)), quads=d.rects)
                text = (tr("In {name}: {words}", name=other.name, words=d.there) if d.kind == "changed"
                        else tr("Not in {name}", name=other.name))
            new.append(dataclasses.replace(a, color=color, contents=text, tags=(tag,), layer=self.layer))
        # A single change: one undo takes back all the marks of the comparison.
        self.change(self.annotations + new, [])
        self.status(ntr("{count} difference marked, tagged “{tag}”", "{count} differences marked, tagged “{tag}”",
                        len(new), tag=tag))
        return True

    def ask_flatten_lost(self, standard: str, names: str) -> bool:
        """Whether to make part of the pages the annotations (NAMES: their kinds and how many) that
        Ghostscript could not keep in STANDARD."""
        box = QMessageBox(QMessageBox.Icon.Warning, standard,
                          tr("Ghostscript could not keep these annotations in {standard}, and left them out: "
                             "{kinds}.\n\nThey can be made part of the pages instead: they will be seen and "
                             "printed, but no longer edited. The other annotations stay as they are.",
                             standard=standard, kinds=names), QMessageBox.StandardButton.NoButton, self)
        flatten = box.addButton(tr("Make them part of the pages"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(tr("Leave them out"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(flatten)
        box.exec()
        return box.clickedButton() is flatten

    def print_dialog(self) -> bool:
        if self.path is None:
            return False
        from .printing import print_document

        self.canvas.commit_text()
        self.keep_comment()
        try:
            # Se imprimen las anotaciones que dejan ver los filtros, pero no los recuadros de censura sin
            # aplicar: en papel parecerían una censura hecha, y el texto seguiría en el archivo.
            chosen = [self.annotations[i] for i in self.shown() if self.annotations[i].kind != "redact"]
            done = print_document(self, self.file, chosen, self.password, self.page, with_them=True)
        except (AnnotateError, RuntimeError, ValueError) as e:
            self.status(str(e), error=True)
            return False
        if done:
            self.status(tr("Sent to the printer"))
        return done

    def export_dialog(self, kind: str) -> bool:
        """Export the annotations the list shows (all, if nothing is filtered) as KIND: 'json',
        'md', 'csv', 'xfdf', or 'pdf' (a summary of the comments)."""
        if self.doc is None:
            return False
        self.canvas.commit_text()
        self.keep_comment()
        chosen = [self.annotations[i] for i in self._rows]
        # Exports follow the list: what is filtered out there is not exported.
        if self.f_kind.currentData() != annots.OTHER:  # (links and the like, only if the list shows only them)
            chosen = [a for a in chosen if a.kind != annots.OTHER]
        # El aparato crítico solo reúne las anotaciones con una entrada de crítica textual.
        if kind == "apparatus":
            chosen = [a for a in chosen if a.critical]
        if not chosen:
            self.status(tr("There are no annotations to export"), error=True)
            return False
        target = self._ask_target(tr("Export the annotations"),
                                  {"pdf": "-summary", "apparatus": "-apparatus"}.get(kind, "-annotations"),
                                  "md" if kind == "apparatus" else kind)
        if target is None:
            return False
        # Only the PDF summary could overwrite the document itself; the other formats have other extensions.
        if kind == "pdf" and self._same_file(target):
            return False
        try:
            if kind == "json":
                exchange.export_json(self.doc, self.file, chosen, target)
            elif kind == "csv":
                exchange.export_csv(self.doc, chosen, target, colors.color_meaning)
            elif kind == "xfdf":
                exchange.export_xfdf(self.doc, self.file, chosen, target)
            elif kind == "apparatus":
                exchange.export_apparatus(self.doc, self.file, chosen, target)
            elif kind == "pdf":
                exchange.save_summary(self.file, chosen, target, self.password, color_name)
            else:
                exchange.export_markdown(self.doc, self.file, chosen, target, color_name)
        except (OSError, AnnotateError) as e:
            self.status(tr("{path} cannot be written: {error}", path=target, error=e), error=True)
            return False
        self.status(ntr("{count} annotation exported to {path}", "{count} annotations exported to {path}",
                        len(chosen), path=target))
        return True

    def import_dialog(self, kind: str) -> bool:
        """Bring in annotations from a JSON file (KIND 'json'), an XFDF file ('xfdf') or another PDF ('pdf')."""
        if self.doc is None:
            return False
        filters = {"json": tr("Annotations (*.json)"), "xfdf": tr("XFDF files (*.xfdf)"),
                   "pdf": tr("PDF files (*.pdf)")}[kind]
        name, _ = QFileDialog.getOpenFileName(self, tr("Import annotations"), self.last_dir(), filters)
        if not name:
            return False
        return self.import_from(Path(name), kind)

    def import_from(self, source: Path, kind: str) -> bool:
        try:
            if kind == "json":
                found = exchange.import_json(source)
            elif kind == "xfdf":
                found = exchange.import_xfdf(self.doc, source)
            else:
                password = ""
                while True:
                    try:
                        found = exchange.import_pdf(source, password)
                        break
                    except PasswordError:
                        password = self.ask_password(source, again=bool(password))
                        if password is None:
                            # Al cancelar se relanza PasswordError, que es un AnnotateError:
                            # lo recoge el except de fuera.
                            raise
        except AnnotateError as e:
            self.status(str(e), error=True)
            return False
        # Las anotaciones de páginas que este documento no tiene se descartan sin aviso.
        found = [a for a in found if 0 <= a.page < self.count]
        # merged() quita las que ya están en el mismo sitio, así que importar dos veces no las duplica.
        new = exchange.merged(self.annotations, found)
        if new:
            # The imported annotations become the selection, so they can be seen and moved at once.
            self.change(self.annotations + new, list(range(len(self.annotations), len(self.annotations) + len(new))))
        self.status(ntr("{count} annotation imported", "{count} annotations imported", len(new))
                    + (" — " + ntr("{count} was here already", "{count} were here already", len(found) - len(new))
                       if len(found) > len(new) else ""))
        return True
