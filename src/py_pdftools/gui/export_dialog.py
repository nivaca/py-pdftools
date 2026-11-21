"""File > Export > Pages as pictures, and The pictures of the document: which pages, and how (see
pages/export.py). The text is exported straight from a file dialog: its type says the format."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QSpinBox, QVBoxLayout,
)

from ..core.interface import tr
from ..core.pagesel import PageError, parse_pages


class PagesChoice(QLineEdit):
    """Which pages ('1-3, 7', 'odd'...; empty: all) of a document of COUNT pages."""

    def __init__(self, count: int, current: int):
        super().__init__()
        self.count = count
        self.setPlaceholderText(tr("All ({count})", count=count))
        self.setToolTip(tr("For example 1-3, 7, last; odd, even. Empty: all the pages. This page is {page}",
                           page=current + 1))

    def pages(self) -> list[int] | None:
        """The pages chosen (0-based), None for all; PageError if they can't be read."""
        if not self.text().strip():
            return None
        return parse_pages(self.text(), self.count, keep_order=True)


class ExportDialog(QDialog):
    """KIND 'pages': the pages as pictures (format, resolution, grey, quality); 'images': the pictures the
    document holds (the smallest left out)."""

    def __init__(self, kind: str, count: int, current: int, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setWindowTitle(tr("Export the pages as pictures") if kind == "pages"
                            else tr("Export the pictures of the document"))
        self.choice = PagesChoice(count, current)
        form = QFormLayout()
        form.addRow(tr("Pages:"), self.choice)
        if kind == "pages":
            self.format = QComboBox()
            for key, name in (("png", "PNG"), ("jpg", "JPEG"), ("tiff", "TIFF")):
                self.format.addItem(name, key)
            self.dpi = QSpinBox(minimum=36, maximum=1200, value=150, suffix=" " + tr("dpi"))
            self.gray = QCheckBox(tr("In grey"))
            self.quality = QSpinBox(minimum=10, maximum=100, value=90, suffix=" %")
            self.format.currentIndexChanged.connect(
                lambda _i: self.quality.setEnabled(self.format.currentData() == "jpg"))
            self.quality.setEnabled(False)
            form.addRow(tr("Format:"), self.format)
            form.addRow(tr("Resolution:"), self.dpi)
            form.addRow(tr("JPEG quality:"), self.quality)
            form.addRow(self.gray)
        else:
            self.smallest = QSpinBox(minimum=0, maximum=2000, value=32, suffix=" px")
            self.smallest.setToolTip(tr("Pictures smaller than this on a side (rules, bullets, marks) are left out"))
            form.addRow(tr("Leave out those smaller than:"), self.smallest)
        self.problem = QLabel()
        self.problem.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.b_ok = buttons.addButton(tr("Choose the folder…"), QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.choice.textChanged.connect(lambda _t: self._check())
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.problem)
        lay.addWidget(buttons)
        self.setMinimumWidth(420)
        self._check()

    def _check(self):
        try:
            self.choice.pages()
            text = ""
        except PageError as e:
            text = str(e)
        self.problem.setText(text)
        self.b_ok.setEnabled(not text)

    def options(self) -> dict:
        found = {"pages": self.choice.pages()}
        if self.kind == "pages":
            found |= {"fmt": self.format.currentData(), "dpi": self.dpi.value(), "gray": self.gray.isChecked(),
                      "quality": self.quality.value()}
        else:
            found |= {"smallest": self.smallest.value()}
        return found
