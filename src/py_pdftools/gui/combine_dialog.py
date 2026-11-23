"""File > Combine files and File > New PDF from pictures: the list of the files (added with a button or dropped
from the file manager, put in order by dragging them or with Up and Down), and how the result is made. See
pages/combine.py."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QPushButton, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout,
)

from ..core.interface import N_, tr
from ..pages import combine
from ..pages.combine import CombineError, PasswordNeeded

PATH = Qt.ItemDataRole.UserRole  # (la ruta de una fila)
PASSWORD = Qt.ItemDataRole.UserRole + 1


class FileTree(QTreeWidget):
    """A list of files that takes those dropped from outside (with SUFFIXES), and is ordered by dragging."""

    def __init__(self, suffixes: tuple[str, ...], add, parent=None):
        super().__init__(parent)
        self.suffixes, self.add_paths = suffixes, add
        self.setRootIsDecorated(False)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setAcceptDrops(True)

    def _paths(self, event) -> list[Path]:
        return [Path(u.toLocalFile()) for u in event.mimeData().urls()
                if u.isLocalFile() and u.toLocalFile().lower().endswith(self.suffixes)]

    def dragEnterEvent(self, event):
        if self._paths(event):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self._paths(event):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        paths = self._paths(event)
        if paths:
            event.acceptProposedAction()
            self.add_paths(paths)
        else:
            super().dropEvent(event)


class _ListDialog(QDialog):
    """The list, and the buttons to add, remove and order its files (for each dialog of files made one)."""

    title, suffixes, filter_text = "", (), ""

    def __init__(self, columns: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.title)
        self.tree = FileTree(self.suffixes, self.add_paths)
        self.tree.setHeaderLabels(columns)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.model().rowsInserted.connect(lambda *_a: self._check())
        self.tree.model().rowsRemoved.connect(lambda *_a: self._check())
        self.buttons_row = QHBoxLayout()
        for text, slot in ((tr("Add…"), self.add_dialog), (tr("Remove"), self.remove),
                           (tr("Up"), lambda: self.move(-1)), (tr("Down"), lambda: self.move(1))):
            b = QPushButton(text)
            b.clicked.connect(slot)
            self.buttons_row.addWidget(b)
        self.buttons_row.addStretch(1)
        self.form = QFormLayout()
        self.box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.b_ok = self.box.addButton(tr("Make the PDF…"), QDialogButtonBox.ButtonRole.AcceptRole)
        self.box.accepted.connect(self.accept)
        self.box.rejected.connect(self.reject)
        note = QLabel(tr("Drop files here, or add them; drag them to put them in order."))
        note.setWordWrap(True)
        lay = QVBoxLayout(self)
        lay.addWidget(note)
        lay.addWidget(self.tree, 1)
        lay.addLayout(self.buttons_row)
        lay.addLayout(self.form)
        lay.addWidget(self.box)
        self.resize(640, 480)

    def _check(self):
        self.b_ok.setEnabled(self.tree.topLevelItemCount() > 0)

    def paths(self) -> list[Path]:
        return [Path(self.tree.topLevelItem(r).data(0, PATH)) for r in range(self.tree.topLevelItemCount())]

    def add_dialog(self):
        names, _ = QFileDialog.getOpenFileNames(self, self.title, "", self.filter_text)
        self.add_paths([Path(n) for n in names])

    def add_paths(self, paths: list[Path]):
        for path in paths:
            item = self.make_item(path)
            if item is not None:
                self.tree.addTopLevelItem(item)
        self._check()

    def make_item(self, path: Path) -> QTreeWidgetItem | None:
        raise NotImplementedError

    def remove(self):
        for item in self.tree.selectedItems():
            self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(item))

    def move(self, step: int):
        rows = sorted((self.tree.indexOfTopLevelItem(i) for i in self.tree.selectedItems()), reverse=step > 0)
        if not rows or not 0 <= rows[0] + step < self.tree.topLevelItemCount():
            return
        for row in rows:
            item = self.tree.takeTopLevelItem(row)
            self.tree.insertTopLevelItem(row + step, item)
            item.setSelected(True)


class CombineDialog(_ListDialog):
    title = N_("Combine files")
    suffixes = (".pdf",)
    filter_text = N_("PDF files (*.pdf)")

    def __init__(self, parent=None, first: tuple[Path, str] | None = None):
        self.title, self.filter_text = tr(self.title), tr(self.filter_text)
        super().__init__([tr("File"), tr("Pages (empty: all)"), tr("It has")], parent)
        self.tree.itemChanged.connect(self._pages_typed)
        self.bookmarks = QComboBox()
        for value, name in (("files", tr("One for each file, with its own under it")),
                            ("keep", tr("Those of the files, as they are")), ("none", tr("None"))):
            self.bookmarks.addItem(name, value)
        self.labels = QCheckBox(tr("Keep the page labels of each file"))
        self.labels.setToolTip(tr("The numbers a viewer shows for the pages (i, ii, 1, 2…), as each file has "
                                  "them; else the pages are numbered 1, 2, 3… from the start"))
        self.form.addRow(tr("Bookmarks:"), self.bookmarks)
        self.form.addRow(self.labels)
        self.problem = QLabel()
        self.problem.setWordWrap(True)
        self.form.addRow(self.problem)
        self.tree.setToolTip(tr("Pages: which pages of each file, in their order ('1-3, 7', 'last-1'); empty "
                                "for all. Double-click to change them"))
        if first is not None:
            self.add_paths([first[0]], {first[0]: first[1]})
        self._check()

    def ask_password(self, path: Path) -> str | None:
        text, ok = QInputDialog.getText(self, tr("Password"), tr("{name} is protected. Its password:",
                                                                 name=path.name), QLineEdit.EchoMode.Password)
        return text if ok else None

    def add_paths(self, paths: list[Path], passwords: dict | None = None):
        self._passwords = passwords or {}
        super().add_paths(paths)

    def make_item(self, path: Path) -> QTreeWidgetItem | None:
        password = getattr(self, "_passwords", {}).get(path, "")
        while True:
            try:
                count = combine.page_count(path, password)
                break
            except PasswordNeeded:
                password = self.ask_password(path)
                if password is None:
                    return None
            except CombineError as e:
                self.problem.setText(str(e))
                return None
        item = QTreeWidgetItem([path.name, "", str(count)])
        item.setToolTip(0, str(path))
        item.setData(0, PATH, str(path))
        item.setData(0, PASSWORD, password)
        item.setData(2, PATH, count)
        item.setFlags((item.flags() | Qt.ItemFlag.ItemIsEditable) & ~Qt.ItemFlag.ItemIsDropEnabled)
        return item

    def _pages_typed(self, item: QTreeWidgetItem, column: int):
        if column == 1:
            self._check()

    def problem_text(self) -> str:
        for r in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(r)
            part = combine.Part(Path(item.data(0, PATH)), item.text(1))
            try:
                combine.chosen_pages(part, int(item.data(2, PATH)))
            except CombineError as e:
                return str(e)
        return ""

    def _check(self):
        if not hasattr(self, "problem"):
            return super()._check()
        text = self.problem_text()
        self.problem.setText(text)
        self.b_ok.setEnabled(self.tree.topLevelItemCount() > 0 and not text)

    def parts(self) -> list[combine.Part]:
        return [combine.Part(Path(item.data(0, PATH)), item.text(1), item.data(0, PASSWORD) or "")
                for item in (self.tree.topLevelItem(r) for r in range(self.tree.topLevelItemCount()))]

    def options(self) -> dict:
        return {"bookmarks": self.bookmarks.currentData(), "labels": self.labels.isChecked()}


class ImagesDialog(_ListDialog):
    title = N_("New PDF from images")
    suffixes = tuple(s[1:] for s in combine.IMAGES)
    filter_text = N_("Pictures ({patterns})")

    def __init__(self, parent=None, ocr: bool = True):
        self.title = tr(self.title)
        self.filter_text = tr(self.filter_text, patterns=" ".join(combine.IMAGES))
        super().__init__([tr("Picture"), tr("Folder")], parent)
        sort = QPushButton(tr("By name"))
        sort.setToolTip(tr("Put the pictures in the order of their names (as a camera or a scanner numbers them)"))
        sort.clicked.connect(self.sort_by_name)
        self.buttons_row.insertWidget(4, sort)
        self.paper = QComboBox()
        self.paper.addItem(tr("As big as each picture"), "")
        for name in combine.PAPERS:
            self.paper.addItem(name, name)
        self.orientation = QComboBox()
        for value, name in ((None, tr("As each picture is")), (False, tr("Portrait")), (True, tr("Landscape"))):
            self.orientation.addItem(name, value)
        self.margin = QDoubleSpinBox(suffix=" mm", decimals=1, maximum=100)
        self.ocr = QCheckBox(tr("Then read its text (OCR), so that it can be found and copied"))
        self.ocr.setChecked(ocr)
        self.ocr.setVisible(ocr)
        self.paper.currentIndexChanged.connect(lambda _i: self.orientation.setEnabled(bool(self.paper.currentData())))
        self.orientation.setEnabled(False)
        self.form.addRow(tr("Page size:"), self.paper)
        self.form.addRow(tr("Orientation:"), self.orientation)
        self.form.addRow(tr("Margin:"), self.margin)
        self.form.addRow(self.ocr)
        self._check()

    def make_item(self, path: Path) -> QTreeWidgetItem | None:
        item = QTreeWidgetItem([path.name, str(path.parent)])
        item.setToolTip(0, str(path))
        item.setData(0, PATH, str(path))
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDropEnabled)
        return item

    def sort_by_name(self):
        self.tree.sortItems(0, Qt.SortOrder.AscendingOrder)
        self.tree.setSortingEnabled(False)  # (y después, otra vez a mano)

    def options(self) -> dict:
        return {"paper": self.paper.currentData(), "landscape": self.orientation.currentData(),
                "margin": self.margin.value()}
