"""The dialogs of OCR (see ocring.py): what to read, and how (OcrDialog); and the doubtful words, to be
checked before the text is written (ReviewDialog)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QRadioButton, QScrollArea, QVBoxLayout, QWidget,
)

from ..core import ocr, pagesel
from ..core.interface import ntr, tr


class OcrDialog(QDialog):
    """Which pages to read (the scanned ones, those selected, the one shown, or a list), in which languages,
    whether to turn the pages lying sideways, and whether to check the doubtful words first."""

    def __init__(self, parent, count: int, scanned: list[int], selected: list[int], shown: int, language: str):
        super().__init__(parent)
        self.setWindowTitle(tr("Recognise text (OCR)"))
        self.count, self.scanned, self.selected, self.shown = count, scanned, selected, shown
        self.which = QButtonGroup(self)
        self.all = QRadioButton(ntr("The scanned page ({count})", "The scanned pages ({count})", len(scanned)))
        self.chosen = QRadioButton(ntr("The page selected in the list of pages ({count})",
                                       "The pages selected in the list of pages ({count})", len(selected)))
        self.chosen.setEnabled(bool(selected))
        self.current = QRadioButton(tr("The page shown ({page})", page=shown + 1))
        self.listed = QRadioButton(tr("These pages:"))
        self.pages = QLineEdit()
        self.pages.setPlaceholderText(tr("e.g. 9-200 or 1,3,9-"))
        self.pages.textEdited.connect(lambda _: self.listed.setChecked(True))
        for n, button in enumerate((self.all, self.chosen, self.current, self.listed)):
            self.which.addButton(button, n)
        (self.all if scanned else self.current).setChecked(True)
        row = QHBoxLayout()
        row.addWidget(self.listed)
        row.addWidget(self.pages, 1)
        note = QLabel(tr("Pages that already have text are left as they are."))
        note.setStyleSheet("color: palette(placeholder-text);")
        self.language = QComboBox()
        self.language.setEditable(True)
        self.language.addItems(ocr.languages())
        self.language.setCurrentText(language)
        self.language.setToolTip(tr("As tesseract names them; several with +, the main one first: lat+spa. "
                                    "Better models can be downloaded in the settings."))
        self.rotate = QCheckBox(tr("Turn the pages lying sideways or upside down"))
        if not ocr.has_osd():
            self.rotate.setEnabled(False)
            self.rotate.setToolTip(tr("Needs tesseract's orientation model (osd): download it in the settings"))
        self.review = QCheckBox(tr("Check the doubtful words before the text is written"))
        self.review.setChecked(True)
        self.problem = QLabel()
        self.problem.setStyleSheet("color: #c03030;")
        self.problem.setWordWrap(True)
        form = QFormLayout()
        form.addRow(tr("Languages:"), self.language)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Read"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        for button in (self.all, self.chosen, self.current):
            lay.addWidget(button)
        lay.addLayout(row)
        lay.addWidget(note)
        lay.addLayout(form)
        lay.addWidget(self.rotate)
        lay.addWidget(self.review)
        lay.addWidget(self.problem)
        lay.addWidget(buttons)

    def page_list(self) -> list[int]:
        """The pages chosen (0-based; those with text too: see OcrMixin.recognise). Raises PageError."""
        which = self.which.checkedId()
        if which == 0:
            return list(self.scanned)
        if which == 1:
            return list(self.selected)
        if which == 2:
            return [self.shown]
        return pagesel.parse_pages(self.pages.text(), self.count)

    def accept(self):
        """(only with pages, and languages tesseract has)"""
        try:
            if not self.page_list():
                raise ocr.OcrError(tr("no page is chosen"))
            ocr.parse_languages(self.language.currentText())
        except (ocr.OcrError, pagesel.PageError) as e:
            self.problem.setText(str(e))
            return
        super().accept()


class ReviewDialog(QDialog):
    """The doubtful words of RESULTS, each with its picture, to be corrected (or emptied, to leave it out)
    before the text is written. corrections() gives {page: {index of the word: text}}."""

    def __init__(self, parent, results: list[ocr.PageResult], below: float = ocr.DOUBTFUL):
        super().__init__(parent)
        self.setWindowTitle(tr("Doubtful words"))
        self.fields: list[tuple[int, int, str, QLineEdit]] = []  # (page, index, as read, its field)
        grid = QGridLayout()
        grid.setColumnStretch(3, 1)
        row = 0
        for result in results:
            for index, word in enumerate(result.words):
                if word.confidence >= below:
                    continue
                picture = QLabel()
                image = QPixmap()
                image.loadFromData(word.crop)
                if not image.isNull():
                    # (scanned at 300 dpi: shown at half that, about the size of the page on the screen)
                    picture.setPixmap(image.scaledToHeight(max(image.height() // 2, 16),
                                                           Qt.TransformationMode.SmoothTransformation))
                field = QLineEdit(word.text)
                field.setToolTip(tr("As read; correct it, or empty it to leave the word out"))
                grid.addWidget(QLabel(tr("p. {page}", page=result.number + 1)), row, 0)
                grid.addWidget(picture, row, 1)
                grid.addWidget(QLabel(f"{word.confidence:.0f} %"), row, 2)
                grid.addWidget(field, row, 3)
                self.fields.append((result.number, index, word.text, field))
                row += 1
        inner = QWidget()
        inner.setLayout(grid)
        scroll = QScrollArea()
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)
        intro = QLabel(ntr("Tesseract was not sure of {count} word. Correct it if it is wrong; the confidence is "
                           "beside it.",
                           "Tesseract was not sure of {count} words. Correct those that are wrong; the confidence "
                           "is beside each.", len(self.fields)))
        intro.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Write the text"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(intro)
        lay.addWidget(scroll, 1)
        lay.addWidget(buttons)
        self.resize(560, 520)

    def corrections(self) -> dict[int, dict[int, str]]:
        out: dict[int, dict[int, str]] = {}
        for page, index, read, field in self.fields:
            if field.text().strip() != read:
                out.setdefault(page, {})[index] = field.text().strip()
        return out
