"""The setting pdfconform (another pdf2iso to run instead of the one of py-pdftools, see core/conform.py),
as the settings of Annotate and Redact and the dialog of Impose show it: the path, a button to choose it,
and, below, which pdf2iso will be used.

(Each of the three dialogs had its own copy of this.)
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget

from ..core import conform
from ..core.interface import tr


class Pdf2isoField:
    """The widgets of the setting: EDIT (the path), its button, and FOUND (which pdf2iso will be used)."""

    def __init__(self, parent: QWidget, text: str = ""):
        self.parent = parent
        self.edit = QLineEdit(text)
        self.edit.setPlaceholderText(tr("Empty: the one of py-pdftools"))
        self.edit.setToolTip(tr("Another pdf2iso to use instead of the one of py-pdftools (a script, with or "
                                "without the .py extension); empty for its own"))
        # La etiqueta de abajo se actualiza con cada tecla: así se ve enseguida si la ruta existe.
        self.edit.textChanged.connect(self.show_found)
        choose = QPushButton(tr("Choose…"))
        choose.clicked.connect(self.choose)
        self.row = QHBoxLayout()
        self.row.addWidget(self.edit, 1)
        self.row.addWidget(choose)
        self.found = QLabel()
        self.found.setWordWrap(True)
        self.found.setStyleSheet("color: palette(placeholder-text);")
        self.show_found()

    def add_to(self, form: QFormLayout):
        form.addRow(tr("pdf2iso:"), self.row)
        form.addRow("", self.found)

    def text(self) -> str:
        return self.edit.text().strip()

    def show_found(self, *_):
        """Say which pdf2iso will be used (File > Save a copy > PDF/A, PDF/X)."""
        path = self.text()
        if path:
            found = conform.find(path)
            self.found.setText(tr("It will be {path}", path=found) if found is not None
                               else tr("There is no such file"))
            return
        # Sin ruta, el de py-pdftools: solo falta Ghostscript, y si no está se dice aquí.
        problem = conform.ghostscript()
        self.found.setText(tr("The one of py-pdftools, with Ghostscript") if not problem else
                           tr("The one of py-pdftools; but PDF/A and PDF/X can't be made: {error}", error=problem))

    def choose(self):
        start = self.text() or str(Path.home())
        name, _ = QFileDialog.getOpenFileName(self.parent, tr("Where is pdf2iso?"), start,
                                              tr("pdf2iso (pdf2iso pdf2iso.py);;All files (*)"))
        if name:
            self.edit.setText(name)
