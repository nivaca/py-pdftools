"""Archivo > Guardar una copia > Como imágenes: qué páginas se convierten en imágenes (sin texto), y con qué
resolución y formato (ver pages/rasterize.py)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QSpinBox, QVBoxLayout,
)

from ..core.interface import tr
from ..core.pagesel import PageError
from ..pages import rasterize
from .export_dialog import PagesChoice


class RasterizeDialog(QDialog):
    def __init__(self, count: int, current: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Save a copy with pages as pictures"))
        note = QLabel(tr("Each page chosen becomes a picture of itself: it looks the same, but its text can no "
                         "longer be found, selected or copied. Annotations and form fields become part of the "
                         "picture."))
        note.setWordWrap(True)
        self.choice = PagesChoice(count, current)
        self.dpi = QSpinBox(minimum=72, maximum=1200, value=300, suffix=" " + tr("dpi"))
        self.format = QComboBox()
        self.format.addItem(tr("PNG (lossless, sharper text)"), "png")
        self.format.addItem(tr("JPEG (smaller, for photographs)"), "jpg")
        self.quality = QSpinBox(minimum=10, maximum=100, value=85, suffix=" %")
        self.quality.setEnabled(False)
        self.format.currentIndexChanged.connect(self._format_changed)
        self.gray = QCheckBox(tr("In grey"))
        form = QFormLayout()
        form.addRow(tr("Pages:"), self.choice)
        form.addRow(tr("Resolution:"), self.dpi)
        form.addRow(tr("Format:"), self.format)
        form.addRow(tr("JPEG quality:"), self.quality)
        form.addRow(self.gray)
        self.problem = QLabel()
        self.problem.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.b_ok = buttons.addButton(tr("Save the copy…"), QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        # (a method, not a lambda holding the dialog: such lambdas can crash Qt at exit)
        self.choice.textChanged.connect(self._check)
        lay = QVBoxLayout(self)
        lay.addWidget(note)
        lay.addLayout(form)
        lay.addWidget(self.problem)
        lay.addWidget(buttons)
        self.setMinimumWidth(440)
        self._check()

    def _format_changed(self, _index: int):
        self.quality.setEnabled(self.format.currentData() == "jpg")

    def _check(self, *_):
        try:
            self.choice.pages()
            text = ""
        except PageError as e:
            text = str(e)
        self.problem.setText(text)
        self.b_ok.setEnabled(not text)

    def values(self) -> tuple[rasterize.Options, list[int] | None]:
        """(the options, the pages chosen: 0-based, None for all)."""
        return (rasterize.Options(self.dpi.value(), self.format.currentData(), self.quality.value(),
                                  self.gray.isChecked()), self.choice.pages())
