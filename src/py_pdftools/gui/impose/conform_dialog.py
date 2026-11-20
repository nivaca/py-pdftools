"""Settings ▸ pdf2iso: another pdf2iso to run instead of the one of py-pdftools (kept in the
configuration file; empty for its own, see conform.find)."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QVBoxLayout

from ..conform_field import Pdf2isoField


# Un diálogo pequeño: solo la ruta de pdf2iso, y debajo, cuál se usará de verdad.
class ConformDialog(QDialog):
    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("pdf2iso")
        self.field = Pdf2isoField(self, path)
        self.field.edit.setMinimumWidth(380)
        form = QFormLayout()
        self.field.add_to(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def path(self) -> str:
        return self.field.text()
