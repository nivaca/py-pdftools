"""Headers and footers, Bates numbers or watermarks on several files at once: the files, in the
order the Bates numbers follow, what to do, and where to save the results."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QPlainTextEdit, QPushButton, QRadioButton, QVBoxLayout,
)

from ...core import conform
from ...pages import files, headfoot, stamps, watermark
from ...pages.changes import Change
from ...core.interface import N_, tr
from .headfoot_dialog import ask_header_footer
from .watermark_dialog import ask_watermark

# what the dialog can do: code -> what it says
ACTIONS = {
    "add-header-footer": N_("Add a header and footer"),
    "add-watermark": N_("Add a watermark"),
    "remove-header-footer": N_("Remove the headers and footers"),
    "remove-bates": N_("Remove the Bates numbers"),
    "remove-watermark": N_("Remove the watermarks"),
}


class BatchDialog(QDialog):
    """FILES to start the list with; FOLDER, where the file dialogs open."""

    def __init__(self, parent, files_: list[Path], folder: Path):
        super().__init__(parent)
        self.setWindowTitle(tr("On several files"))
        self.folder = folder
        # Los ajustes se eligen una sola vez, previsualizados sobre el primer archivo, y se aplican a todos.
        self.settings = None  # (a HeaderFooter or a Watermark, once chosen)
        self.keep = False
        self.written: list[Path] = []

        # ------------------------------------------------- the files
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.list.setToolTip(tr("The Bates numbers go on from one file to the next, in this order"))
        buttons = QVBoxLayout()
        # The order of the list matters: Bates numbers run on from one file to the next in it.
        for text, slot in ((tr("Add files…"), self.add_files), (tr("Add a folder…"), self.add_folder),
                           (tr("Remove"), self.remove_chosen), (tr("Move up"), lambda: self.move(-1)),
                           (tr("Move down"), lambda: self.move(1)), (tr("Sort by name"), self.sort)):
            b = QPushButton(text)
            # The slot is bound as a default argument: a plain closure would see only the last slot of the loop.
            b.clicked.connect(lambda *_, s=slot: s())
            buttons.addWidget(b)
        buttons.addStretch(1)
        row = QHBoxLayout()
        row.addWidget(self.list, 1)
        row.addLayout(buttons)
        files_box = QGroupBox(tr("Files"))
        files_box.setLayout(row)
        self.add_paths(files_)

        # ------------------------------------------------- what
        self.action = QComboBox()
        for code, text in ACTIONS.items():
            self.action.addItem(tr(text), code)
        self.action.currentIndexChanged.connect(self._action_chosen)
        self.choose = QPushButton(tr("Settings…"))
        self.choose.clicked.connect(self.choose_settings)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        row = QHBoxLayout()
        row.addWidget(self.action, 1)
        row.addWidget(self.choose)
        what = QVBoxLayout()
        what.addLayout(row)
        what.addWidget(self.summary)
        what_box = QGroupBox(tr("What to do"))
        what_box.setLayout(what)

        # ------------------------------------------------- where
        self.same = QRadioButton(tr("Next to each file"))
        self.other = QRadioButton(tr("In this folder:"))
        self.same.setChecked(True)
        self.out_folder = QLineEdit()
        # Escribir una carpeta marca por sí solo la opción "En esta carpeta".
        self.out_folder.textChanged.connect(lambda *_: self.other.setChecked(True) if self.out_folder.text() else None)
        browse = QPushButton(tr("Choose…"))
        browse.clicked.connect(self.choose_folder)
        self.overwrite = QCheckBox(tr("Change the files themselves"))
        self.prefix = QLineEdit()
        self.suffix = QLineEdit("-labelled")
        self.overwrite.toggled.connect(self._overwrite_toggled)
        self.standard = QComboBox()
        # Sin pdf2iso, las opciones PDF/A y PDF/X se muestran pero deshabilitadas, para que se sepa que existen.
        have = conform.available()
        for value, name in [("", N_("PDF"))] + conform.STANDARDS:
            self.standard.addItem(tr(name), value)
            if value and not have:  # (greyed out without pdf2iso)
                self.standard.model().item(self.standard.count() - 1).setEnabled(False)
        self.standard.setToolTip(tr("PDF/A and PDF/X are made by pdf2iso") if have else
                                 tr("Needs {command}: install it, or say where it is in Settings",
                                    command=conform.COMMAND))
        form = QFormLayout()
        row = QHBoxLayout()
        row.addWidget(self.other)
        row.addWidget(self.out_folder, 1)
        row.addWidget(browse)
        form.addRow(self.same)
        form.addRow(row)
        form.addRow(self.overwrite)
        form.addRow(tr("Before the names"), self.prefix)
        form.addRow(tr("After the names"), self.suffix)
        form.addRow(tr("Save as"), self.standard)
        where_box = QGroupBox(tr("Saving"))
        where_box.setLayout(form)

        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setMaximumHeight(110)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.run_button = self.buttons.addButton(tr("Run"), QDialogButtonBox.ButtonRole.ActionRole)
        self.run_button.clicked.connect(self.run)
        self.buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(files_box, 1)
        lay.addWidget(what_box)
        lay.addWidget(where_box)
        lay.addWidget(self.report)
        lay.addWidget(self.buttons)
        self.resize(680, 640)
        self._action_chosen()

    # ----------------------------------------------------------------- the files

    def paths(self) -> list[Path]:
        return [Path(self.list.item(i).text()) for i in range(self.list.count())]

    def add_paths(self, paths):
        # Duplicates and files that are not PDFs are skipped silently.
        have = set(self.paths())
        for p in paths:
            if p and Path(p) not in have and str(p).lower().endswith(".pdf"):
                self.list.addItem(str(p))
                have.add(Path(p))
        self._enable()

    def add_files(self):
        names, _ = QFileDialog.getOpenFileNames(self, tr("Add files"), str(self.folder), tr("PDF files (*.pdf)"))
        self.add_paths(names)

    def add_folder(self):
        name = QFileDialog.getExistingDirectory(self, tr("Add a folder"), str(self.folder))
        if name:
            # Dos patrones, para .pdf y .PDF; otras mezclas de mayúsculas no se encuentran.
            self.add_paths(sorted(Path(name).glob("*.pdf")) + sorted(Path(name).glob("*.PDF")))

    def remove_chosen(self):
        for item in self.list.selectedItems():
            self.list.takeItem(self.list.row(item))
        self._enable()

    def move(self, step: int):
        row = self.list.currentRow()
        if row < 0 or not 0 <= row + step < self.list.count():
            return
        item = self.list.takeItem(row)
        self.list.insertItem(row + step, item)
        self.list.setCurrentRow(row + step)

    def sort(self):
        # Ordena por nombre sin distinguir mayúsculas; la carpeta no cuenta.
        paths = sorted(self.paths(), key=lambda p: p.name.casefold())
        self.list.clear()
        self.add_paths(paths)

    # ----------------------------------------------------------------- what and where

    def _action_chosen(self, *_):
        adding = self.action.currentData().startswith("add-")
        self.choose.setEnabled(adding)
        kind = stamps.WATERMARK if self.action.currentData() == "add-watermark" else stamps.HEADER_FOOTER
        # Si se pasa de encabezado a marca de agua (o al revés), los ajustes anteriores ya no sirven.
        if self.settings is not None and self.settings.KIND != kind:
            self.settings = None
        self.summary.setText("" if not adding else
                             tr("Settings chosen") if self.settings is not None else tr("Choose the settings"))
        self._enable()

    def ask(self, kind: str, settings, source: Path):
        """(settings, keep) from the dialog of KIND, previewing SOURCE (None if cancelled)."""
        ask = ask_header_footer if kind == stamps.HEADER_FOOTER else ask_watermark
        # Sin contraseña ni etiquetas de página: la vista previa usa la página 1 del primer archivo,
        # y "existing" en True ofrece la opción de conservar lo que ya tenga.
        return ask(self, settings, source, "", None, 1, True)

    def choose_settings(self) -> bool:
        paths = self.paths()
        if not paths:
            return False
        kind = stamps.WATERMARK if self.action.currentData() == "add-watermark" else stamps.HEADER_FOOTER
        start = self.settings or (headfoot.HeaderFooter() if kind == stamps.HEADER_FOOTER else watermark.Watermark())
        try:
            answer = self.ask(kind, start, paths[0])
        # Any error opening the first file (encrypted, damaged) is shown in the report instead of escaping the dialog.
        except Exception as e:  # (the first file cannot be read: say so)
            self.report.setPlainText(str(e))
            return False
        if answer is None:
            return False
        self.settings, self.keep = answer
        self._action_chosen()
        return True

    def choose_folder(self):
        name = QFileDialog.getExistingDirectory(self, tr("Save in"), str(self.folder))
        if name:
            self.out_folder.setText(name)

    def _overwrite_toggled(self, on: bool):
        # Sobrescribir los originales hace inútiles el prefijo, el sufijo y la carpeta de destino.
        for w in (self.prefix, self.suffix, self.other, self.out_folder):
            w.setEnabled(not on)
        if on:
            self.same.setChecked(True)

    def _enable(self):
        # _enable runs from add_paths during construction, before the buttons exist.
        if hasattr(self, "run_button"):
            adding = self.action.currentData().startswith("add-")
            self.run_button.setEnabled(bool(self.paths()) and (not adding or self.settings is not None))

    def change(self) -> Change:
        code = self.action.currentData()
        if code.startswith("add-"):
            return Change(self.settings, keep=self.keep)
        if code == "remove-watermark":
            return Change(None, kind=stamps.WATERMARK)
        return Change(None, kind=stamps.HEADER_FOOTER, bates_only=code == "remove-bates")

    # ----------------------------------------------------------------- running

    def run(self) -> bool:
        # Sin carpeta de destino, files.batch escribe cada resultado junto a su original.
        folder = Path(self.out_folder.text()) if self.other.isChecked() and self.out_folder.text().strip() else None
        change = self.change()
        # files.batch devuelve, por cada archivo, (origen, destino o None, error), y cuántos números Bates usó en total.
        results, used = files.batch(self.paths(), change, folder=folder, prefix=self.prefix.text(),
                                    suffix=self.suffix.text(), overwrite=self.overwrite.isChecked())
        standard = self.standard.currentData()
        lines = []
        for source, target, error in results:
            # La conversión a PDF/A o PDF/X se hace después, archivo por archivo, sobre el resultado ya escrito.
            # If it fails the plain PDF stays, and the report says so.
            if target and standard:
                # TODO: the conversion runs in the GUI thread, file after file, and freezes the dialog on long batches;
                # it could run in a worker thread with a progress bar.
                QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                try:
                    check = conform.convert(target, target, standard)
                except conform.ConformError as e:
                    lines.append(tr("{path}: saved as a plain PDF, but it could not be made {standard}: {error}",
                                    path=target.name, standard=conform.label(standard), error=e))
                else:
                    lines.append(tr("Wrote {path}", path=target) + " — " + conform.label(standard)
                                 + (f" ({check})" if check else ""))
                finally:
                    QApplication.restoreOverrideCursor()
                self.written.append(target)
                continue
            lines.append(tr("Wrote {path}", path=target) if target else tr("{path}: {error}", path=source.name,
                                                                            error=error))
            if target:
                self.written.append(target)
        # Shown so that the user can start the next batch where this one stopped.
        if used and change.settings is not None:
            lines.append(tr("Next Bates number: {number}", number=stamps.bates_number(change.settings, used)))
        self.report.setPlainText("\n".join(lines))
        return all(target for _, target, _ in results)
