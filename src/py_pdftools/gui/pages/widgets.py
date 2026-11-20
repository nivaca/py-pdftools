"""Widgets of the window: those of a row of the table of ranges, and the dialog that numbers pages."""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QValidator
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QSpinBox, QTableWidget,
    QVBoxLayout, QWidget,
)

from ...pages import labels
from ...core.interface import tr
from ...pages.labels import Range
from ...pages.numbers import folio_side, to_folio

FIRST, STYLE, START, PREFIX, SUFFIX, LABELS = range(6)  # the columns of the table of ranges
EDITABLE = (FIRST, STYLE, START, PREFIX, SUFFIX)


class StartSpin(QSpinBox):
    """The number a range starts at; for folios, a leaf and its side (12v)."""

    def __init__(self, folio: bool):
        super().__init__()
        self.folio = folio
        self.setRange(1, 999999)

    def set_folio(self, folio: bool):
        """Count leaves and sides (or not) from now on, keeping the number shown."""
        if folio != self.folio:
            value = self.value()
            value = folio_side(value, "r") if folio else (value + 1) // 2
            self.folio = folio
            self.setValue(value)
            self.lineEdit().setText(self.textFromValue(value))

    def textFromValue(self, value: int) -> str:
        return to_folio(value) if self.folio else str(value)

    def valueFromText(self, text: str) -> int:
        if not self.folio:
            return int(text)
        m = re.fullmatch(r"\s*(\d+)\s*([rv]?)\s*", text)
        return folio_side(int(m[1]), m[2]) if m and int(m[1]) else self.value()

    def validate(self, text: str, pos: int):
        if not self.folio:
            return super().validate(text, pos)
        if re.fullmatch(r"\s*[1-9]\d*\s*[rv]?\s*", text):
            return QValidator.State.Acceptable, text, pos
        return (QValidator.State.Intermediate if re.fullmatch(r"\s*\d*\s*", text)
                else QValidator.State.Invalid), text, pos


class NumberDialog(QDialog):
    """How to number some pages: a style, a start, a prefix and a suffix, with
    the labels they would get."""

    def __init__(self, parent, count: int):
        super().__init__(parent)
        self.count = count
        self.setWindowTitle(tr("Number these pages"))
        self.style = QComboBox()
        for code in labels.STYLES:
            if code:
                self.style.addItem(tr(labels.STYLE_TITLES[code]), code)
        self.start = StartSpin(False)
        self.prefix = QLineEdit()
        self.prefix.setPlaceholderText(tr("e.g. A-"))
        self.suffix = QLineEdit()
        self.suffix.setPlaceholderText(tr("e.g. ]"))
        self.preview = QLabel()
        form = QFormLayout()
        form.addRow(tr("Style"), self.style)
        form.addRow(tr("Starts at"), self.start)
        form.addRow(tr("Prefix"), self.prefix)
        form.addRow(tr("Suffix"), self.suffix)
        form.addRow(tr("Labels"), self.preview)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(tr("{count} pages, numbered one after the other:", count=count)))
        lay.addLayout(form)
        lay.addWidget(buttons)
        self.style.currentIndexChanged.connect(self._changed)
        self.start.valueChanged.connect(self._changed)
        self.prefix.textChanged.connect(self._changed)
        self.suffix.textChanged.connect(self._changed)
        self._changed()

    def values(self) -> tuple[str, str, int, str]:
        """(style, prefix, start, suffix)."""
        return self.style.currentData(), self.prefix.text(), self.start.value(), self.suffix.text()

    def _changed(self, *_):
        self.start.set_folio(self.style.currentData() == "f")
        style, prefix, start, suffix = self.values()
        self.preview.setText(labels.describe(Range(1, style, prefix, start, suffix), self.count))


# the field of a Range each editable column changes, and how to read it from its widget
FIELDS = {
    FIRST: ("page", QSpinBox.value),
    STYLE: ("style", QComboBox.currentData),
    START: ("start", QSpinBox.value),
    PREFIX: ("prefix", QLineEdit.text),
    SUFFIX: ("suffix", QLineEdit.text),
}


def edited_signal(widget: QWidget):
    """The signal a widget of the table sends when the user has changed it."""
    return widget.currentIndexChanged if isinstance(widget, QComboBox) else widget.editingFinished


def range_row(r: Range, last: int, count: int, first_row: bool) -> dict[int, QWidget]:
    """The widgets of the row of R (which lasts until LAST, in a document of COUNT pages), by column."""
    first = QSpinBox()
    first.setRange(1, max(count, 1))
    first.setValue(r.page)
    first.setEnabled(not first_row)  # (the first range starts at page 1)
    first.setToolTip(tr("The first page of the range (the pages of the file, from 1)"))

    style = QComboBox()
    for code in labels.STYLES:
        style.addItem(tr(labels.STYLE_TITLES[code]), code)
    style.setCurrentIndex(labels.STYLES.index(r.style))

    start = StartSpin(r.style == "f")
    start.setValue(r.start)
    start.setEnabled(bool(r.style))
    start.setToolTip(tr("The leaf and side of the first page of the range (12r, 12v)") if r.style == "f"
                     else tr("The number of the first page of the range"))

    prefix = QLineEdit(r.prefix)
    prefix.setMinimumWidth(110)
    prefix.setPlaceholderText(tr("e.g. A-"))
    prefix.setToolTip(tr("Text put before the number of each page"))

    suffix = QLineEdit(r.suffix)
    suffix.setMinimumWidth(70)
    suffix.setEnabled(bool(r.style))
    suffix.setPlaceholderText(tr("e.g. ]"))
    suffix.setToolTip(tr("Text put after the number of each page (PDF has no suffixes: such labels "
                         "are written one for each page)"))

    shown = QLabel(f"{labels.describe(r, last)}   ({labels.pages_text(r, last)})")
    shown.setTextFormat(Qt.TextFormat.PlainText)
    shown.setContentsMargins(6, 0, 6, 0)
    return {FIRST: first, STYLE: style, START: start, PREFIX: prefix, SUFFIX: suffix, LABELS: shown}


def header_width(table: QTableWidget, col: int) -> int:
    return table.horizontalHeader().fontMetrics().horizontalAdvance(table.horizontalHeaderItem(col).text()) + 16


def fit_columns(table: QTableWidget) -> None:
    """Make the editable columns as wide as their widgets and headers (ResizeToContents ignores
    cell widgets)."""
    for col in EDITABLE:
        widths = [table.cellWidget(row, col).sizeHint().width() for row in range(table.rowCount())]
        table.setColumnWidth(col, max(widths + [header_width(table, col)]) + 4)
