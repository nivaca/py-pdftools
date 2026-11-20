"""Arranging pages in the window: the list of pages that takes drags (to move pages, or with Ctrl
to copy them, and PDFs dropped on it to insert their pages), the dialog of each operation, and the
question of what the page labels do when pages move."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QListView, QListWidget, QMessageBox, QPushButton, QSpinBox, QVBoxLayout,
)

from ...pages import arrange
from ...core.interface import N_, tr
from ...pages.labels import LabelError
from ...pages.stamps import compact_pages


class PageList(QListWidget):
    """The pages of the document; dragging chosen pages moves them (with Ctrl, copies them), and
    dropping PDFs on it inserts their pages there."""

    moved = Signal(list, int, bool)  # (pages, before which page, copied)
    files_dropped = Signal(list, int)  # (paths, before which page)

    def __init__(self):
        super().__init__()
        # Qt's own move is replaced in dropEvent: the list only reports what was dropped and where, and the window
        # changes the document and fills the list again.
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDropIndicatorShown(True)

    def before_of(self, pos) -> int:
        """The page (1-based) before which something dropped at POS goes (count + 1: at the end)."""
        # Entre miniaturas no hay ningún elemento bajo el cursor; en modo icono se busca el más cercano para
        # que soltar en el hueco no mande las páginas al final.
        item = self.itemAt(pos)
        if item is None and self.viewMode() == QListView.ViewMode.IconMode:
            item = self._nearest(pos)
        if item is None:
            return self.count() + 1
        row = self.row(item)
        rect = self.visualItemRect(item)
        # In a grid the halves are left and right; in a plain list, top and bottom.
        if self.viewMode() == QListView.ViewMode.IconMode:
            after = pos.x() > rect.center().x()
        else:
            after = pos.y() > rect.center().y()
        return row + 2 if after else row + 1

    def _nearest(self, pos):
        """In icon mode: the thumbnail beside POS, when POS is in the room between thumbnails (or
        to the right of the last of a row)."""
        grid = self.gridSize()
        if not self.count() or grid.isEmpty():
            return None
        # Se mide el hueco entre celdas con la primera miniatura, suponiendo que todas tienen el mismo tamaño.
        cell = self.visualItemRect(self.item(0))
        gap_x = max(grid.width() - cell.width(), 1)
        gap_y = max(grid.height() - cell.height(), 1)
        # Se prueba a izquierda y derecha, arriba y en diagonal; los dos últimos desplazamientos (una celda entera)
        # cubren el espacio a la derecha de la última miniatura de una fila.
        for dx, dy in ((-gap_x, 0), (gap_x, 0), (0, -gap_y), (-gap_x, -gap_y), (gap_x, -gap_y),
                       (-grid.width(), 0), (-grid.width(), -gap_y)):
            item = self.itemAt(pos + QPoint(dx, dy))
            if item is not None:
                return item
        return None

    def _ours(self, mime) -> bool:
        """Whether MIME is files, or pages dragged in this list (whose drags never carry files)."""
        # Drags from other applications (text, images) are refused, so that the cursor shows they cannot be dropped.
        return mime.hasUrls() or any(mime.hasFormat(f) for f in self.mimeTypes())

    def dragEnterEvent(self, event):
        if self._ours(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._ours(event.mimeData()):
            event.acceptProposedAction()
            super().dragMoveEvent(event)
        else:
            event.ignore()

    def dropEvent(self, event):
        before = self.before_of(event.position().toPoint())
        # Solo se aceptan archivos .pdf; los demás se descartan sin aviso.
        if event.mimeData().hasUrls():
            paths = [Path(u.toLocalFile()) for u in event.mimeData().urls()
                     if u.toLocalFile().lower().endswith(".pdf")]
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            if paths:
                # Emitted after the drop ends, so that the window can open dialogs without the drag
                # still running.
                QTimer.singleShot(0, lambda: self.files_dropped.emit(paths, before))
            return
        pages = sorted(self.row(i) + 1 for i in self.selectedItems())
        copied = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        event.setDropAction(Qt.DropAction.IgnoreAction)  # (the window does it, and fills the list again)
        event.accept()
        if pages:  # (once the drag is over: the window may ask what the labels do)
            QTimer.singleShot(0, lambda: self.moved.emit(pages, before, copied))


def ask_labels(parent) -> tuple[str, bool] | None:
    """(what the labels do, whether to do so from now on) as the user chooses (None if cancelled)."""
    # Un QMessageBox con dos botones propios en lugar de Sí/No: cada uno lleva el texto de su opción.
    box = QMessageBox(QMessageBox.Icon.Question, tr("The page labels"),
                      tr("The pages change places. What should their labels do?"), parent=parent)
    follow = box.addButton(tr(arrange.LABEL_CHOICES[arrange.FOLLOW]), QMessageBox.ButtonRole.AcceptRole)
    position = box.addButton(tr(arrange.LABEL_CHOICES[arrange.POSITION]), QMessageBox.ButtonRole.AcceptRole)
    box.addButton(QMessageBox.StandardButton.Cancel)
    box.setDefaultButton(follow)
    remember = QCheckBox(tr("Do so from now on (Pages ▸ The labels, to change it)"))
    box.setCheckBox(remember)
    box.exec()
    # Closing the box with Escape or the title bar leaves clickedButton on Cancel (or None): both mean cancelled.
    chosen = box.clickedButton()
    if chosen is follow:
        return arrange.FOLLOW, remember.isChecked()
    if chosen is position:
        return arrange.POSITION, remember.isChecked()
    return None


# what the dialog can do: code -> its title
MODES = {
    "rotate": N_("Rotate pages"),
    "delete": N_("Delete pages"),
    "move": N_("Move pages"),
    "duplicate": N_("Duplicate pages"),
    "reverse": N_("Reverse the order of pages"),
    "order": N_("New order of the pages"),
    "blank": N_("Insert blank pages"),
    "insert": N_("Insert pages from a PDF"),
    "replace": N_("Replace pages by those of a PDF"),
    "extract": N_("Extract pages to a new PDF"),
    "split": N_("Split into several PDFs"),
}


class ArrangeDialog(QDialog):
    """One operation on the pages (MODE: see MODES) of a document of COUNT pages, starting from the
    pages chosen (PAGES) and the page shown (PAGE)."""

    def __init__(self, parent, mode: str, count: int, pages: list[int] | None = None, page: int = 1,
                 folder: Path | None = None):
        super().__init__(parent)
        self.mode, self.count, self.folder = mode, count, folder or Path.home()
        self.setWindowTitle(tr(MODES[mode]))
        form = QFormLayout()
        # Las páginas elegidas se escriben de forma compacta (1-3,7) como valor inicial del campo.
        compact = compact_pages(pages) if pages else ""

        self.pages = QLineEdit(compact)
        self.pages.setPlaceholderText(tr("e.g. 9-20,31; all; even; 1-50,odd"))
        self.pages.setToolTip(tr("The pages of the file, from 1; LAST counts from the end"))
        if mode in ("rotate", "delete", "move", "duplicate", "reverse", "replace", "extract"):
            form.addRow(tr("Pages:"), self.pages)
        # Reverse on all pages is the common case, so the field starts with "all" when no pages were chosen.
        if mode == "reverse" and not compact:
            self.pages.setText("all")
        self.angle = QComboBox()
        for angle, text in ((90, N_("90° clockwise")), (270, N_("90° counterclockwise")), (180, N_("180°"))):
            self.angle.addItem(tr(text), angle)
        if mode == "rotate":
            form.addRow(tr("Turn:"), self.angle)
        # For a new order, the field starts with the current order, which the user then edits.
        self.order = QLineEdit(f"1-{count}")
        self.order.setToolTip(tr("Pages may be repeated or left out; 10-1 goes backwards"))
        if mode == "order":
            form.addRow(tr("The pages in this order:"), self.order)
        self.source = QLineEdit()
        self.source.setPlaceholderText(tr("a PDF file"))
        browse = QPushButton(tr("Choose…"))
        browse.clicked.connect(self.choose_source)
        source_row = QHBoxLayout()
        source_row.addWidget(self.source, 1)
        source_row.addWidget(browse)
        self.source_pages = QLineEdit()
        self.source_pages.setPlaceholderText(tr("all"))
        # "replace" toma tantas páginas del PDF de origen como las que reemplaza, a partir de esta.
        self.source_first = QSpinBox()
        self.source_first.setRange(1, 999999)
        self.source_password = QLineEdit()
        self.source_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.source_password.setPlaceholderText(tr("if it has one"))
        if mode in ("insert", "replace"):
            form.addRow(tr("From the PDF:"), source_row)
            if mode == "insert":
                form.addRow(tr("Its pages:"), self.source_pages)
            else:
                form.addRow(tr("From its page:"), self.source_first)
            form.addRow(tr("Its password:"), self.source_password)
        self.where = QSpinBox()
        self.where.setRange(1, count + 1)
        # La posición inicial es la página mostrada, limitada al intervalo válido (count + 1 es el final).
        self.where.setValue(min(max(page, 1), count + 1))
        self.where.setToolTip(tr("{count} + 1: at the end", count=count))
        self.blanks = QSpinBox()
        self.blanks.setRange(1, 10000)
        self.blanks.setToolTip(tr("As big as the page before them (at the start, as the first page)"))
        if mode == "blank":
            form.addRow(tr("Blank pages:"), self.blanks)
        if mode in ("move", "duplicate", "insert", "blank"):
            form.addRow(tr("Before page:") if mode != "duplicate" else tr("Before page (0: right after them):"),
                        self.where)
            # En Duplicar, 0 significa "justo después de las páginas duplicadas"; por eso el mínimo baja a 0.
            if mode == "duplicate":
                self.where.setRange(0, count + 1)
                self.where.setValue(0)
        # "0" is shown as "no", so that the split can be given by the starting pages instead.
        self.every = QSpinBox()
        self.every.setRange(0, max(count, 1))
        self.every.setSpecialValueText(tr("no"))
        self.at = QLineEdit()
        self.at.setPlaceholderText(tr("e.g. 9,91 (each part starts there)"))
        self.target_folder = QLineEdit(str(self.folder))
        if mode == "split":
            form.addRow(tr("Every so many pages:"), self.every)
            form.addRow(tr("Or starting at pages:"), self.at)
            form.addRow(tr("In the folder:"), self.target_folder)
        self.labels = QComboBox()
        for code, text in arrange.LABEL_CHOICES.items():
            self.labels.addItem(tr(text), code)
        # Labels are offered only for the operations that move, add or remove pages; rotation and replacement keep them.
        if mode in ("delete", "move", "duplicate", "reverse", "order", "insert", "blank"):
            form.addRow(tr("Labels:"), self.labels)
        self.problem = QLabel()
        self.problem.setWordWrap(True)
        self.problem.setStyleSheet("color: #c0392b;")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.try_accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.problem)
        lay.addWidget(buttons)
        self.result_value = None

    def choose_source(self):
        name, _ = QFileDialog.getOpenFileName(self, tr("A PDF"), str(self.folder), tr("PDF files (*.pdf)"))
        if name:
            self.source.setText(name)

    def value(self):
        """What the dialog asks for: an arrange.Operation; for extract, the pages; for split, (parts,
        folder). Raises LabelError if something is wrong."""
        # Todas las operaciones reciben la misma elección de etiquetas (kw), aunque solo la usen las que mueven páginas.
        n, kw = self.count, {"labels": self.labels.currentData()}

        def pages():
            # An empty field means all the pages.
            return tuple(arrange.parse_page_list(self.pages.text() or "all", n))

        mode = self.mode
        if mode == "rotate":
            return arrange.Rotate(pages(), self.angle.currentData(), **kw)
        if mode == "delete":
            return arrange.Delete(pages(), **kw)
        if mode == "move":
            return arrange.Move(pages(), self.where.value(), **kw)
        if mode == "duplicate":
            return arrange.Duplicate(pages(), self.where.value(), **kw)
        if mode == "reverse":
            # For Reverse, an empty tuple means the whole document.
            return arrange.Reverse(() if self.pages.text().strip().lower() in ("", "all") else pages(), **kw)
        if mode == "order":
            return arrange.Order(tuple(arrange.parse_order(self.order.text(), n)), **kw)
        if mode == "blank":
            return arrange.InsertBlank(self.where.value(), self.blanks.value(), **kw)
        if mode in ("insert", "replace"):
            source = self.source.text().strip()
            if not source:
                raise LabelError(tr("choose the PDF the pages come from"))
            password = self.source_password.text()
            # Se abre el PDF de origen ya aquí, para validar las páginas pedidas contra su número real de páginas
            # y para que una contraseña errónea se muestre en el diálogo.
            count = arrange.source_count(source, password)
            if mode == "insert":
                chosen = tuple(arrange.parse_page_list(self.source_pages.text(), count)) \
                    if self.source_pages.text().strip() else ()
                return arrange.Insert(source, chosen, self.where.value(), password, **kw)
            return arrange.Replace(pages(), source, self.source_first.value(), password, **kw)
        if mode == "extract":
            return list(pages())
        if mode == "split":
            # Si se dan las dos cosas, "cada N páginas" tiene prioridad sobre las páginas de inicio
            # (ver arrange.split_parts).
            at = arrange.parse_page_list(self.at.text(), n) if self.at.text().strip() else None
            if not self.every.value() and not at:
                raise LabelError(tr("say every how many pages, or at which pages, to split"))
            return arrange.split_parts(n, self.every.value(), at), Path(self.target_folder.text().strip() or ".")
        raise LabelError(mode)

    def try_accept(self):
        # Los errores se muestran en rojo dentro del diálogo, que sigue abierto para corregirlos.
        try:
            value = self.value()
            if isinstance(value, arrange.Operation) and value.moves_pages():
                value.items(self.count)  # (checked before the dialog closes)
        except LabelError as e:
            self.problem.setText(str(e))
            return
        self.result_value = value
        self.accept()


def ask_arrange(parent, mode: str, count: int, pages: list[int] | None = None, page: int = 1,
                folder: Path | None = None):
    """What the dialog of MODE gives (see ArrangeDialog.value), or None if cancelled."""
    dlg = ArrangeDialog(parent, mode, count, pages, page, folder)
    # The value is computed and kept by try_accept, so the caller does not have to parse the fields again.
    return dlg.result_value if dlg.exec() == QDialog.DialogCode.Accepted else None
