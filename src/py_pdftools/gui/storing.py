"""Dónde guarda la ventana las anotaciones de su documento (mezclado en
MainWindow): en el PDF mismo, como siempre (``storage`` "pdf"), o aparte, en
libro.pdf.pdfnotes, junto al PDF, sin tocarlo ("file"; véase
annotate/sidecar.py).

Un documento que tiene ese archivo se abre con sus anotaciones; uno que no lo
tiene, como digan los ajustes (Ajustes > Documentos, en el PDF por omisión).
Archivo > Anotaciones en un archivo aparte pasa de una manera a la otra, y
guarda enseguida: hacia el archivo aparte, pregunta si el PDF se queda con sus
anotaciones o se le quitan; hacia el PDF, las escribe en él (las que vinieron
del PDF, cambiadas donde están) y borra el archivo aparte.

Guardar aparte no toca el PDF, salvo cuando el documento mismo cambió (sus
páginas, sus rótulos: véase working.py): entonces se escribe el PDF también,
y se pregunta si con las anotaciones dentro o sin ellas.
"""

from __future__ import annotations

import dataclasses
import os
import shutil
import tempfile
from pathlib import Path

from PySide6.QtWidgets import QMessageBox

from ..annotate import annots, recovery, sidecar
from ..annotate.annots import OTHER, AnnotateError, Annotation
from ..core import config
from ..core.interface import ntr, tr

STORAGES = ("pdf", "file")


def default_storage() -> str:
    """Where the annotations of a document without a file of them apart are saved (Settings > Documents)."""
    try:
        value = config.get("annot_storage")
    except config.ConfigError:
        return "pdf"
    return value if value in STORAGES else "pdf"


def _fresh(items: list[Annotation]) -> list[Annotation]:
    """ITEMS as new annotations (no xrefs: they are no longer the PDF's)."""
    return [dataclasses.replace(a, xref=0, replies=tuple(dataclasses.replace(r, xref=0) for r in a.replies))
            for a in items]


def _copy(source: Path, target: Path) -> None:
    """SOURCE copied as TARGET, safely (a file of its own in TARGET's folder, put in its place at the end)."""
    fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=target.parent)
    os.close(fd)
    try:
        shutil.copyfile(source, tmp)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class StorageMixin:
    """(Mixed into MainWindow: it uses its document, its annotations and the history.)"""

    storage = "pdf"  # where the annotations of the document are saved: "pdf" or "file" (see the module)
    kept_file: Path | None = None  # the file of annotations apart, if the document has one
    _kept_layers: dict[str, bool] | None = None
    _kept_note = ""  # (what the opening found, for the status bar: see open_path)
    _kept_unreadable = False

    def apart(self) -> bool:
        """Whether the annotations are saved apart, not in the PDF."""
        return self.storage == "file"

    # ----------------------------------------------------------------- opening

    def _read_apart(self, path: Path, found: list[Annotation]) -> list[Annotation]:
        """(The document at PATH just loaded, with FOUND, the annotations its PDF has.) Its annotations: those of
        its file apart, if it has one, else FOUND; and where they are to be saved."""
        self.kept_file, self._kept_layers, self._kept_note = sidecar.find(path), None, ""
        self._kept_unreadable = False
        if self.kept_file is None:
            self.storage = default_storage()
            return found
        self.storage = "file"
        self.watch_file()  # (ese archivo también: _load vigiló solo el PDF, sin saber de él todavía)
        try:
            kept = sidecar.read(self.kept_file)
        except AnnotateError as e:
            # Lo ilegible no se pierde: al guardar se aparta con otro nombre (véase _write_kept).
            self._kept_unreadable = True
            self._kept_note = str(e)
            return found
        out = sidecar.combine(self.doc, found, kept)
        self._kept_layers = kept.layers
        notes = [tr("annotations from {file}", file=self.kept_file.name)]
        if out.new_in_pdf:
            notes.append(ntr("{count} more in the PDF, new or changed since",
                             "{count} more in the PDF, new or changed since", out.new_in_pdf))
        if out.turned:
            notes.append(ntr("{count} put in place on a page turned since",
                             "{count} put in place on pages turned since", out.turned))
        if out.dropped:
            notes.append(ntr("{count} of a page the document no longer has, left out",
                             "{count} of pages the document no longer has, left out", out.dropped))
        self._kept_note = "; ".join(notes)
        return out.annotations

    def apart_layers(self, layers: dict[str, bool]) -> dict[str, bool]:
        """LAYERS (as the PDF shows or hides them), as the file apart says."""
        if not self._kept_layers:
            return layers
        return {name: self._kept_layers.get(name, on) for name, on in layers.items()}

    # ----------------------------------------------------------------- saving

    def _write_kept(self, pdf: Path, items: list[Annotation], base: dict[int, str]) -> Path:
        """ITEMS written as the file apart of PDF (the document shown); returns where (raises OSError)."""
        place = sidecar.place_for(pdf)
        if self._kept_unreadable and place.is_file():
            # (el archivo que no se pudo leer queda al lado, por si se quiere)
            os.replace(place, place.with_name(place.name + ".unreadable"))
            self._kept_unreadable = False
        sidecar.write(place, self.doc, pdf.name, items, base, self.layers)
        return place

    def ask_pdf_part(self) -> str | None:
        """(Saving apart a document whose PDF must be written too: it has changes of its own.) Whether the PDF
        gets the annotations as well ("embed") or none ("strip"); None: cancelled."""
        box = QMessageBox(QMessageBox.Icon.Question, tr("Annotations in a separate file"),
                          tr("The document itself has changed, so its PDF is written again. Should it have the "
                             "annotations in it too, as they are now, or only the separate file?"),
                          QMessageBox.StandardButton.Cancel, self)
        embed = box.addButton(tr("In the PDF too"), QMessageBox.ButtonRole.AcceptRole)
        strip = box.addButton(tr("Only in the separate file"), QMessageBox.ButtonRole.AcceptRole)
        box.setDefaultButton(strip)
        box.exec()
        return {embed: "embed", strip: "strip"}.get(box.clickedButton())

    def save_apart(self, target: Path, pdf_part: str | None = None) -> bool:
        """Save the annotations apart, for the document at TARGET (which may be the document itself): in
        TARGET.pdfnotes. The PDF is not written if TARGET is the document and it has no changes of its own;
        else it is written ("copy": as it is; "embed": with the annotations in it; "strip": without them; None:
        asked if the document changed). Then the window goes on with TARGET."""
        self.canvas.commit_text()
        self.keep_comment()
        replacing = target.resolve() == self.path.resolve()
        if replacing and self.work is None and pdf_part in (None, "copy"):
            return self._save_kept_only()
        if pdf_part is None:
            pdf_part = "copy" if self.work is None else self.ask_pdf_part()
            if pdf_part is None:
                return False
        source, page, old = self.file, self.page, self.path
        known = self.known_in_file()
        if replacing:  # (the file is about to change under the open document)
            self._close_doc(carry=True)
        try:
            if pdf_part == "copy":
                _copy(source, target)
            else:
                keep = self.annotations if pdf_part == "embed" else [a for a in self.annotations if a.kind == OTHER]
                annots.write(source, keep, target, self.password, original=known, shown=self.layers)
        except (AnnotateError, OSError) as e:
            if replacing:
                self._load_work(source, page)
                self.refresh()
            self.status(tr("{path} cannot be written: {error}", path=target, error=e), error=True)
            return False
        found = self._load(target, self.password, page, carry=True)
        if found is None:
            return False
        mine = [a for a in self.annotations if a.kind != OTHER]
        # Lo que el archivo aparte guarda: con el PDF copiado, las anotaciones tal cual (sus xref siguen valiendo);
        # con ellas dentro del PDF, las que el PDF tiene ahora; sin ellas, todas como nuevas.
        items = {"copy": mine, "embed": [a for a in found if a.kind != OTHER], "strip": _fresh(mine)}[pdf_part]
        base = sidecar.base_of(found)
        try:
            self.kept_file = self._write_kept(target, items, base)
        except OSError as e:
            self.status(tr("{path} cannot be written: {error}", path=sidecar.place_for(target), error=e), error=True)
            return False
        combined = sidecar.combine(self.doc, found, sidecar.Kept(items, base, {}, dict(self.layers))).annotations
        self.watch_file()  # (the file apart, as just written: no change of another program)
        recovery.discard(old)
        if self.work is not None or pdf_part != "copy":
            # (los pasos del historial son de archivos que ya no están, o sus xref ya no son los del PDF)
            self.drop_work()
            self.undo_stack.clear()
            self.redo_stack.clear()
        self.storage = "file"
        self.annotations, self.saved = list(combined), list(combined)
        self.saved_layers = dict(self.layers)
        self.selected = []
        self.settings.setValue("last_dir", str(target.parent))
        self.add_recent(target)
        self.refresh()
        self.show_page(page)
        self.status(tr("Saved {path}", path=target) + " — "
                    + ntr("{count} annotation in {file}", "{count} annotations in {file}", len(items),
                          file=self.kept_file.name))
        return True

    def _save_kept_only(self) -> bool:
        """Save the annotations in the file apart; the PDF is left as it is."""
        known = self.known_in_file()
        if known is None:  # (otro programa cambió el PDF después de leerlo)
            try:
                with annots.open_pdf(self.path, self.password) as doc:
                    known = annots.read(doc)
            except AnnotateError as e:
                self.status(str(e), error=True)
                return False
        mine = [a for a in self.annotations if a.kind != OTHER]
        try:
            self.kept_file = self._write_kept(self.path, mine, sidecar.base_of(known))
        except OSError as e:
            self.status(tr("{path} cannot be written: {error}", path=sidecar.place_for(self.path), error=e),
                        error=True)
            return False
        recovery.discard(self.path)
        self.storage = "file"
        self.saved = list(self.annotations)
        self.saved_layers = dict(self.layers)
        self.watch_file()  # (lo que ella misma guarda no es un cambio de los archivos vigilados)
        self.refresh()
        self.status(ntr("{count} annotation saved in {file} (the PDF is as it was)",
                        "{count} annotations saved in {file} (the PDF is as it was)", len(mine),
                        file=self.kept_file.name))
        return True

    def save_embedded_dialog(self) -> bool:
        """File > Save a copy > With the annotations in the PDF: a copy of the document with them written in it
        (the window goes on as it was)."""
        if self.path is None:
            return False
        target = self._ask_target(tr("Save a copy with the annotations in the PDF"), "-annotated")
        if target is None:
            return False
        if target.resolve() == self.path.resolve():
            self.status(tr("Choose another name: this is the document itself"), error=True)
            return False
        self.canvas.commit_text()
        self.keep_comment()
        try:
            written = annots.write(self.file, self.annotations, target, self.password,
                                   original=self.known_in_file(), shown=self.layers)
        except AnnotateError as e:
            self.status(str(e), error=True)
            return False
        self.status(tr("Saved {path}", path=target) + " — "
                    + ntr("{count} annotation written", "{count} annotations written", written))
        return True

    # ----------------------------------------------------------------- switching

    def ask_strip(self, count: int) -> str | None:
        """(Going apart.) Whether the PDF keeps its own COUNT annotations ("keep") or they are taken out of it
        ("strip"), now that the separate file has them; None: cancelled."""
        box = QMessageBox(QMessageBox.Icon.Question, tr("Annotations in a separate file"),
                          ntr("The PDF has {count} annotation of its own. From now on it is in the separate file "
                              "too, and edited there. Take it out of the PDF, so that other programs show the PDF "
                              "without it?",
                              "The PDF has {count} annotations of its own. From now on they are in the separate "
                              "file too, and edited there. Take them out of the PDF, so that other programs show "
                              "the PDF without them?", count),
                          QMessageBox.StandardButton.Cancel, self)
        keep = box.addButton(tr("Leave the PDF as it is"), QMessageBox.ButtonRole.AcceptRole)
        strip = box.addButton(tr("Take them out of the PDF"), QMessageBox.ButtonRole.DestructiveRole)
        box.setDefaultButton(keep)
        box.exec()
        return {keep: "keep", strip: "strip"}.get(box.clickedButton())

    def set_apart(self, on: bool) -> bool:
        """Keep the annotations of the document apart (ON) or in the PDF, saving them so at once. Returns
        whether it was done."""
        if self.path is None or on == self.apart():
            self._show_storage()
            return False
        self.canvas.commit_text()
        self.keep_comment()
        if on:
            known = self.known_in_file()
            own = [a for a in (known if known is not None else self.file_annotations) if a.kind != OTHER]
            choice = self.ask_strip(len(own)) if own else "keep"
            if choice is None:
                self._show_storage()
                return False
            if choice == "strip":
                part = "strip"
            else:  # (the PDF as it is; written with the annotations in it only if it has changes of its own)
                part = "copy" if self.work is None else "embed"
            done = self.save_apart(self.path, part)
        else:
            self.storage = "pdf"
            done = self.save_to(self.path)
            if done:
                try:
                    sidecar.remove(self.path)
                except OSError as e:
                    self.status(tr("{path} cannot be removed: {error}", path=self.kept_file, error=e), error=True)
                self.kept_file = None
                self.watch_file()
                self.status(tr("The annotations are in the PDF now: {path}", path=self.path.name))
            else:
                self.storage = "file"
        self._show_storage()
        return done

    def _show_storage(self):
        """The menu entry and the tooltip of Save, as the document's annotations are saved."""
        act = getattr(self, "a_apart", None)
        if act is None:
            return
        act.blockSignals(True)
        act.setChecked(self.apart())
        act.blockSignals(False)
        act.setEnabled(self.path is not None)
        self.a_embedded.setEnabled(self.path is not None and self.apart())
        if self.apart() and self.path is not None:
            self.a_save.setToolTip(tr("Write the annotations in {file}, beside the document (the PDF is not "
                                      "changed)", file=sidecar.place_for(self.path).name))
        else:
            self.a_save.setToolTip(tr("Write the annotations in the document (its signatures stay valid for what "
                                      "they signed)"))
