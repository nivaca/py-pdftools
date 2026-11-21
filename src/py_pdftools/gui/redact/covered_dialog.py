"""Text only covered: the places where the check (redact/covered.py) found text hidden under something drawn
over it, with what covers it and the text that is still there. Not modal: a place clicked is shown on the
page; boxes are put over those chosen (or over all), so that the redacted copy takes the text out."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from ...core.interface import ntr, tr
from ...redact.covered import KIND_NAMES, Covered


class CoveredDialog(QDialog):
    show_place = Signal(object)  # Covered
    mark = Signal(list)  # [Covered]

    def __init__(self, found: list[Covered], labels: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Text only covered"))
        self.found = found
        pages = len({c.page for c in found})
        head = QLabel(ntr("This text is covered by something drawn over it, but it is still in the file: it can "
                          "be selected, copied or found. It was found in {count} place",
                          "This text is covered by something drawn over it, but it is still in the file: it can "
                          "be selected, copied or found. It was found in {count} places", len(found))
                      + ntr(", on {count} page.", ", on {count} pages.", pages) + " "
                      + tr("Put boxes over it to take it out in the redacted copy."))
        head.setWordWrap(True)
        self.table = table = QTableWidget(len(found), 3)
        table.setHorizontalHeaderLabels([tr("Page"), tr("Covered by"), tr("Text under it")])
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().hide()
        for row, c in enumerate(found):
            label = labels[c.page] if c.page < len(labels) and labels[c.page] else str(c.page + 1)
            text = QTableWidgetItem(c.text)
            text.setToolTip(c.text)
            for col, item in enumerate((QTableWidgetItem(label), QTableWidgetItem(tr(KIND_NAMES[c.kind])), text)):
                table.setItem(row, col, item)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.resizeColumnsToContents()
        table.itemSelectionChanged.connect(self._selected)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.b_mark = buttons.addButton(tr("Put boxes over all"), QDialogButtonBox.ButtonRole.ActionRole)
        self.b_mark.clicked.connect(lambda: self.mark.emit(self.chosen()))
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(head)
        lay.addWidget(table, 1)
        lay.addWidget(buttons)
        self.resize(680, 420)

    def chosen(self) -> list[Covered]:
        """The places selected; all, if none is."""
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return [self.found[r] for r in rows] if rows else list(self.found)

    def _selected(self):
        rows = {i.row() for i in self.table.selectedIndexes()}
        self.b_mark.setText(tr("Put boxes over those selected") if rows else tr("Put boxes over all"))
        if len(rows) == 1:
            self.show_place.emit(self.found[rows.pop()])
