"""The languages of OCR (OCR > Languages, and the settings): every language tesseract can read, with what
there is of it here (installed with tesseract; a better model downloaded, its size and date); and the
better models (tessdata_best) downloaded, updated or removed (see core/ocr.py)."""

from __future__ import annotations

import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QProgressDialog, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from ..core import ocr
from ..core.interface import ntr, tr


class LanguagesDialog(QDialog):
    """A table of the languages, filtered as typed; Download (or update) and Remove act on the rows chosen."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("OCR languages"))
        self.about = QLabel()
        self.about.setWordWrap(True)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText(tr("Find a language…"))
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(self._filter)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([tr("Code"), tr("Language"), tr("With tesseract"), tr("Better model")])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._enable)
        self.download = QPushButton(tr("Download"))
        self.download.setToolTip(tr("Download Tesseract's most accurate model (tessdata_best) of the languages "
                                    "chosen, or download it again; needs the internet"))
        self.download.clicked.connect(self.download_chosen)
        self.remove = QPushButton(tr("Remove"))
        self.remove.setToolTip(tr("Remove the better model of the languages chosen (the one installed with "
                                  "tesseract, if any, is used again)"))
        self.remove.clicked.connect(self.remove_chosen)
        note = QLabel(tr("The languages installed with tesseract are installed and removed with the system's "
                         "packages (tesseract-langpack-… on Fedora, tesseract-ocr-… on Debian and Ubuntu)."))
        note.setWordWrap(True)
        note.setStyleSheet("color: palette(placeholder-text);")
        buttons = QHBoxLayout()
        buttons.addWidget(self.download)
        buttons.addWidget(self.remove)
        buttons.addStretch(1)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        buttons.addWidget(close)
        lay = QVBoxLayout(self)
        lay.addWidget(self.about)
        lay.addWidget(self.filter)
        lay.addWidget(self.table, 1)
        lay.addWidget(note)
        lay.addLayout(buttons)
        self.resize(640, 560)
        self.fill()

    def fill(self):
        """The table, as things are now (those there first: with tesseract, or downloaded)."""
        there = set(ocr.models())
        names = sorted(set(ocr.NAMES) | there, key=lambda n: (n not in there, tr(ocr.NAMES.get(n, n)).casefold()))
        own = ocr.own_tessdata()
        self.table.setRowCount(len(names))
        for row, name in enumerate(names):
            better = ""
            if ocr.better(name):
                model = own / f"{name}.traineddata"
                st = model.stat()
                when = datetime.date.fromtimestamp(st.st_mtime).isoformat()
                better = f"{st.st_size / 1e6:.0f} MB, {when}"
            cells = [name, tr(ocr.NAMES[name]) if name in ocr.NAMES else name,
                     tr("yes") if ocr.installed(name) else "", better]
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, name)
                self.table.setItem(row, column, item)
        self.table.resizeColumnToContents(0)
        self.table.resizeColumnToContents(2)
        self.table.resizeColumnToContents(3)
        version = ocr.version()
        self.about.setText(
            (tr("Tesseract {version}.", version=version) if version else tr("Tesseract is not installed: there is "
                                                                           "no OCR."))
            + " " + ntr("{count} language can be read here.", "{count} languages can be read here.",
                        len([n for n in there if n != "osd"]))
            + " " + tr("Better models go into {path}.", path=own))
        self._filter(self.filter.text())
        self._enable()

    def _filter(self, text: str):
        text = text.strip().casefold()
        for row in range(self.table.rowCount()):
            words = " ".join(self.table.item(row, c).text() for c in (0, 1)).casefold()
            self.table.setRowHidden(row, bool(text) and text not in words)

    def chosen(self) -> list[str]:
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return [self.table.item(r, 0).data(Qt.ItemDataRole.UserRole) for r in rows]

    def _enable(self):
        names = self.chosen()
        self.download.setEnabled(bool(names) and ocr.program() is not None)
        self.remove.setEnabled(any(ocr.better(n) for n in names))

    def download_chosen(self) -> bool:
        names = self.chosen()
        if not names:
            return False
        progress = QProgressDialog(tr("Downloading…"), tr("Stop"), 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(300)

        def step(done: int, total: int) -> bool:
            progress.setMaximum(total)
            progress.setValue(min(done, total) if total else 0)
            QApplication.processEvents()
            return not progress.wasCanceled()

        try:
            for name in names:
                progress.setLabelText(tr("Downloading {name}…", name=name))
                ocr.download([name], step)
        except ocr.OcrError as e:
            QMessageBox.warning(self, tr("OCR languages"), str(e))
            return False
        finally:
            progress.close()
            self.fill()
        return True

    def remove_chosen(self) -> bool:
        names = [n for n in self.chosen() if ocr.better(n)]
        if not names:
            return False
        try:
            for name in names:
                ocr.remove(name)
        except ocr.OcrError as e:
            QMessageBox.warning(self, tr("OCR languages"), str(e))
            return False
        finally:
            self.fill()
        return True
