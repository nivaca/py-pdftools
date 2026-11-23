"""The languages of OCR (OCR > Languages, and the settings): every language tesseract can read, with what
there is of it here (installed with tesseract; a better model downloaded, its size and date); and the
better models (tessdata_best) downloaded, updated or removed (see core/ocr.py).

Para descargar varios de una vez, cada fila tiene su casilla: los idiomas marcados forman la lista de lo que
se descargará, que se muestra bajo la tabla, y se descargan todos seguidos; uno que falle no detiene los
demás."""

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
    """A table of the languages, filtered as typed; Download (or update) acts on the languages ticked (the list
    to download), or on the rows chosen if none is; Remove, on the rows chosen."""

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
        self.table.itemChanged.connect(self._ticked_changed)
        self.ticked: list[str] = []  # (the list to download, in the order ticked)
        self.listed = QLabel()
        self.listed.setWordWrap(True)
        self.clear_list = QPushButton(tr("Clear the list"))
        self.clear_list.clicked.connect(self.untick_all)
        self.download = QPushButton(tr("Download"))
        self.download.setToolTip(tr("Download Tesseract's most accurate model (tessdata_best) of the languages "
                                    "ticked, one after another (or of the rows chosen, if none is ticked), or "
                                    "download it again; needs the internet"))
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
        listed = QHBoxLayout()
        listed.addWidget(self.listed, 1)
        listed.addWidget(self.clear_list)
        lay.addLayout(listed)
        lay.addWidget(note)
        lay.addLayout(buttons)
        self.resize(640, 560)
        self.fill()

    def fill(self):
        """The table, as things are now (those there first: with tesseract, or downloaded)."""
        there = set(ocr.models())
        names = sorted(set(ocr.NAMES) | there, key=lambda n: (n not in there, tr(ocr.NAMES.get(n, n)).casefold()))
        own = ocr.own_tessdata()
        self.table.blockSignals(True)  # (las casillas se ponen aquí: no son cambios del usuario)
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
                if column == 0:  # (the box that puts the language in the list to download)
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Checked if name in self.ticked else Qt.CheckState.Unchecked)
                self.table.setItem(row, column, item)
        self.table.blockSignals(False)
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

    def _ticked_changed(self, item: QTableWidgetItem):
        if item.column() != 0:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        on = item.checkState() == Qt.CheckState.Checked
        if on and name not in self.ticked:
            self.ticked.append(name)
        elif not on and name in self.ticked:
            self.ticked.remove(name)
        self._enable()

    def tick(self, names: list[str], on: bool = True):
        """Put NAMES in the list to download (ON), or take them out."""
        rows = {self.table.item(r, 0).data(Qt.ItemDataRole.UserRole): r for r in range(self.table.rowCount())}
        for name in names:  # (en el orden dado: la lista se descarga en el orden en que se marcó)
            if name in rows:
                state = Qt.CheckState.Checked if on else Qt.CheckState.Unchecked
                self.table.item(rows[name], 0).setCheckState(state)

    def untick_all(self):
        self.tick(list(self.ticked), False)

    def to_download(self) -> list[str]:
        """The languages Download acts on: those ticked, or the rows chosen if none is."""
        return list(self.ticked) or self.chosen()

    def chosen(self) -> list[str]:
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return [self.table.item(r, 0).data(Qt.ItemDataRole.UserRole) for r in rows]

    def _enable(self):
        names = self.chosen()
        self.download.setEnabled(bool(self.to_download()) and ocr.program() is not None)
        self.remove.setEnabled(any(ocr.better(n) for n in names))
        count = len(self.ticked)
        self.download.setText(ntr("Download {count} language", "Download {count} languages", count)
                              if count else tr("Download"))
        self.clear_list.setVisible(bool(count))
        self.listed.setText(tr("To download: {languages}", languages=", ".join(
            tr(ocr.NAMES[n]) if n in ocr.NAMES else n for n in self.ticked)) if count
            else tr("Tick the languages to download, to download several at once."))

    def download_chosen(self) -> bool:
        """Download the list (see to_download), one language after another: one that fails doesn't stop the
        others, and what failed is said at the end. Whether all were downloaded."""
        names = self.to_download()
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

        failed, done = [], []
        try:
            for number, name in enumerate(names, 1):
                if progress.wasCanceled():
                    break
                label = tr(ocr.NAMES[name]) if name in ocr.NAMES else name
                progress.setLabelText(tr("Downloading {name} ({number} of {count})…", name=label, number=number,
                                         count=len(names)) if len(names) > 1 else tr("Downloading {name}…", name=name))
                try:
                    ocr.download([name], step)
                except ocr.OcrError as e:
                    if progress.wasCanceled():  # (Stop: the rest stay in the list)
                        break
                    failed.append(str(e))
                else:
                    done.append(name)
        finally:
            progress.close()
            self.tick(done, False)  # (out of the list, before the table is made again)
            self.ticked = [n for n in self.ticked if n not in done]
            self.fill()
        if failed:
            QMessageBox.warning(self, tr("OCR languages"), "\n".join(failed))
        return not failed and len(done) == len(names)

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
