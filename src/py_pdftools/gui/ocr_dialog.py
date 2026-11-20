"""What to read with OCR, and how (OcrOptions: in the panel of the mode OCR, and in OcrDialog, which the
menu of the thumbnails opens in the other modes); and the doubtful words, to be checked before the text is
written (ReviewDialog). See ocring.py."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QRadioButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from ..core import ocr, pagesel
from ..core.interface import ntr, tr


class OcrOptions(QWidget):
    """Which pages to read (the scanned ones, those chosen, the one shown, or a list), in which languages
    (ticked, the main one first: they can be dragged), whether to turn the pages lying sideways, whether to
    check the doubtful words first, and below which confidence a word is doubtful."""

    changed = Signal()  # (a choice changed)

    def __init__(self, language: str, parent=None):
        super().__init__(parent)
        self.count, self.scanned, self.selected, self.shown = 0, [], [], 0
        self.which = QButtonGroup(self)
        self.all = QRadioButton()
        self.chosen = QRadioButton()
        self.current = QRadioButton()
        self.listed = QRadioButton(tr("These pages:"))
        self.pages = QLineEdit()
        self.pages.setPlaceholderText(tr("e.g. 9-200 or 1,3,9-"))
        self.pages.textEdited.connect(lambda _: self.listed.setChecked(True))
        for n, button in enumerate((self.all, self.chosen, self.current, self.listed)):
            self.which.addButton(button, n)
        self.which.idToggled.connect(lambda *_: self.changed.emit())
        row = QHBoxLayout()
        row.addWidget(self.listed)
        row.addWidget(self.pages, 1)
        note = QLabel(tr("Pages that already have text are left as they are."))
        note.setStyleSheet("color: palette(placeholder-text);")
        note.setWordWrap(True)
        self.languages = QListWidget()
        self.languages.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.languages.setToolTip(tr("Tick the languages of the text; drag them to put the main one first. "
                                     "OCR > Languages downloads others, and better models."))
        self.languages.setMaximumHeight(150)
        self.languages.itemChanged.connect(lambda *_: self.changed.emit())
        self.fill_languages(language)
        self.rotate = QCheckBox(tr("Turn the pages lying sideways or upside down"))
        self.review = QCheckBox(tr("Check the doubtful words before the text is written"))
        self.review.setChecked(True)
        self.doubtful = QSpinBox()
        self.doubtful.setRange(1, 100)
        self.doubtful.setValue(int(ocr.DOUBTFUL))
        self.doubtful.setSuffix(" %")
        self.doubtful.setToolTip(tr("A word read with less confidence than this is doubtful"))
        self.problem = QLabel()
        self.problem.setStyleSheet("color: #c03030;")
        self.problem.setWordWrap(True)
        form = QFormLayout()
        form.addRow(tr("Doubtful below:"), self.doubtful)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        for button in (self.all, self.chosen, self.current):
            lay.addWidget(button)
        lay.addLayout(row)
        lay.addWidget(note)
        lay.addWidget(QLabel(tr("Languages:")))
        lay.addWidget(self.languages)
        lay.addWidget(self.rotate)
        lay.addWidget(self.review)
        lay.addLayout(form)
        lay.addWidget(self.problem)
        self.refresh_osd()

    def fill_languages(self, language: str):
        """The languages tesseract has here, those of LANGUAGE ('lat+spa') ticked and first, in its order."""
        wanted = [n for n in language.split("+") if n]
        there = ocr.languages()
        self.languages.blockSignals(True)
        self.languages.clear()
        for name in [*[n for n in wanted if n in there], *[n for n in there if n not in wanted]]:
            title = tr(ocr.NAMES[name]) if name in ocr.NAMES else name
            item = QListWidgetItem(f"{title} ({name})" + (" ★" if ocr.better(name) else ""))
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if name in wanted else Qt.CheckState.Unchecked)
            self.languages.addItem(item)
        self.languages.blockSignals(False)

    def refresh_osd(self):
        """Turning pages needs tesseract's osd model: without it, the box is off, and says so."""
        self.rotate.setEnabled(ocr.has_osd())
        self.rotate.setToolTip("" if ocr.has_osd() else
                               tr("Needs tesseract's orientation model (osd): download it in OCR > Languages"))
        if not ocr.has_osd():
            self.rotate.setChecked(False)

    def set_pages(self, count: int, scanned: list[int], selected: list[int], shown: int, prefer_chosen=False):
        """The document's pages: COUNT, the SCANNED ones, the SELECTED ones, the one SHOWN (0-based)."""
        self.count, self.scanned, self.selected, self.shown = count, scanned, selected, shown
        self.all.setText(ntr("The scanned page ({count})", "The scanned pages ({count})", len(scanned)))
        self.chosen.setText(ntr("The page selected in the list of pages ({count})",
                                "The pages selected in the list of pages ({count})", len(selected)))
        self.chosen.setEnabled(bool(selected))
        self.current.setText(tr("The page shown ({page})", page=shown + 1))
        checked = self.which.checkedButton()
        if prefer_chosen and selected:
            self.chosen.setChecked(True)
        elif checked is None or not checked.isEnabled():
            (self.all if scanned else self.current).setChecked(True)

    def language(self) -> str:
        """The languages ticked, in their order: 'lat+spa'."""
        items = [self.languages.item(n) for n in range(self.languages.count())]
        return "+".join(i.data(Qt.ItemDataRole.UserRole) for i in items if i.checkState() == Qt.CheckState.Checked)

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

    def check(self) -> bool:
        """Whether there are pages and languages tesseract has (else the problem, said)."""
        try:
            if not self.page_list():
                raise ocr.OcrError(tr("no page is chosen"))
            ocr.parse_languages(self.language())
        except (ocr.OcrError, pagesel.PageError) as e:
            self.problem.setText(str(e))
            return False
        self.problem.setText("")
        return True


class OcrDialog(QDialog):
    """OcrOptions in a dialog (OCR from the menu of the thumbnails, in a mode other than OCR)."""

    def __init__(self, parent, count: int, scanned: list[int], selected: list[int], shown: int, language: str,
                 prefer_chosen: bool = False):
        super().__init__(parent)
        self.setWindowTitle(tr("Recognise text (OCR)"))
        self.options = OcrOptions(language, self)
        self.options.set_pages(count, scanned, selected, shown, prefer_chosen)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Read"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.options)
        lay.addWidget(buttons)

    def accept(self):
        """(only with pages, and languages tesseract has)"""
        if self.options.check():
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
