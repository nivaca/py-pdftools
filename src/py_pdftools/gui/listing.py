"""The panel of the annotations: the list of them (searched, filtered and
sorted), and the annotation selected: its colour, comment, tags, replies and
review status. The window fills it and answers what is done in it.

The list is a model of its own (AnnotationModel): a row is made only when it
is shown, so that a document with thousands of annotations is listed at once."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QMenu, QPlainTextEdit,
    QPushButton, QTableView, QToolButton, QVBoxLayout, QWidget,
)

from ..annotate.annots import STATES, Annotation, date_text
from ..core.interface import ntr, tr
from .colors import color_name, swatch

PAGE, KIND, AUTHOR, STATUS, CHANGED, TEXT = range(6)


class AnnotationModel(QAbstractTableModel):
    """The rows of the list: indices of the window's annotations, in the order shown."""

    # The model holds no annotations of its own: it asks the window each time (annotations()), so a
    # change in the window never leaves the list showing a stale copy.
    def __init__(self, annotations: Callable[[], list[Annotation]], marked: Callable[[Annotation], str]):
        super().__init__()
        self._annotations = annotations
        self._marked = marked
        self.rows: list[int] = []
        # Una sola fuente cursiva, hecha una vez: data() se llama miles de veces al desplazarse.
        self._italic = QFont()
        self._italic.setItalic(True)

    def set_rows(self, rows: list[int]):
        """Show ROWS; if they are the rows shown, only their contents are shown again."""
        # Mismas filas: basta con dataChanged, que conserva la selección y la posición del desplazamiento;
        # un reset las perdería.
        if rows == self.rows and rows:
            self.dataChanged.emit(self.index(0, 0), self.index(len(rows) - 1, self.columnCount() - 1))
            return
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 6

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return [tr("Page"), tr("Kind"), tr("Author"), tr("Status"), tr("Changed"), tr("Text")][section]
        return None

    def annotation(self, row: int) -> Annotation | None:
        annotations = self._annotations()
        # Defensive: the window may have fewer annotations than rows for a moment, while it updates the list.
        i = self.rows[row] if 0 <= row < len(self.rows) else -1
        return annotations[i] if 0 <= i < len(annotations) else None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        a = self.annotation(index.row())
        if a is None:
            return None
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if col == PAGE:
                # Las páginas se cuentan desde 0 en el código y desde 1 en la pantalla.
                return str(a.page + 1)
            if col == KIND:
                return a.name() + (f" ({len(a.replies)})" if a.replies else "") + \
                    (", " + tr("locked") if a.locked else "")
            if col == AUTHOR:
                return a.author
            if col == STATUS:
                return tr(STATES[a.status()]) if a.status() else ""
            if col == CHANGED:
                return date_text(a.modified or a.created)
            # Los saltos de línea y espacios repetidos del comentario se reducen a un espacio, para una fila.
            text = " ".join(a.contents.split())
            # Un resaltado sin comentario muestra entre comillas el texto que marca (en cursiva, ver FontRole).
            if not text and a.kind in ("highlight", "underline", "strikeout", "squiggly"):
                marked = self._marked(a)
                return f"“{marked}”" if marked else ""
            labels = " ".join(f"#{t}" for t in a.tags)
            return f"{text}  {labels}".strip() if labels else text
        if role == Qt.ItemDataRole.DecorationRole and col == KIND:
            return swatch(a.color)
        # The same markup kinds as in DisplayRole: the text they mark, shown instead of a comment, is in italics.
        if role == Qt.ItemDataRole.FontRole and col == TEXT and not a.contents.strip() and a.kind in (
                "highlight", "underline", "strikeout", "squiggly"):
            return self._italic
        if role == Qt.ItemDataRole.ToolTipRole:
            if col == KIND:
                tip = color_name(a.color)
                if a.replies:
                    tip += "\n" + ntr("{count} reply", "{count} replies", len(a.replies))
                return tip
            if col == CHANGED and a.created:
                return tr("Made: {made}; changed: {changed}", made=date_text(a.created),
                          changed=date_text(a.modified) or "—")
            if col == TEXT:
                lines = [a.contents] if a.contents else []
                if a.tags:
                    lines.append(tr("Tags: {tags}", tags=", ".join(a.tags)))
                if a.categories:
                    lines.append(tr("Categories: {categories}", categories=", ".join(a.categories)))
                return "\n".join(lines) or None
        return None


class ReplyList(QListWidget):
    deleted = Signal()

    def keyPressEvent(self, event):
        # Supr o Retroceso sobre una respuesta: la ventana pregunta y la borra.
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.currentRow() >= 0:
            self.deleted.emit()
            return
        super().keyPressEvent(event)


class CommentEdit(QPlainTextEdit):
    """The comment of the annotation selected; what is typed is kept when the field is left (finished)."""

    finished = Signal()

    def focusOutEvent(self, event):
        # Se guarda al salir del campo, no a cada tecla: así cada comentario es un solo paso de deshacer.
        super().focusOutEvent(event)
        self.finished.emit()


class Panel(QWidget):
    """The widgets of the panel (the window fills them, and answers their signals)."""

    def __init__(self, model: AnnotationModel, parent=None):
        super().__init__(parent)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Search the annotations…"))
        self.search.setClearButtonEnabled(True)
        self.search.setToolTip(tr("Their comments, texts, replies, tags and categories, the text they mark, their "
                                  "authors and kinds"))
        # Six filters in two rows of three; the window fills their items from the annotations of the document.
        self.f_kind, self.f_author, self.f_color = QComboBox(), QComboBox(), QComboBox()
        self.f_status, self.f_tag, self.f_category = QComboBox(), QComboBox(), QComboBox()
        for box, tip in ((self.f_kind, tr("Only annotations of this kind")),
                         (self.f_author, tr("Only annotations by this author")),
                         (self.f_color, tr("Only annotations of this colour")),
                         (self.f_status, tr("Only annotations with this review status")),
                         (self.f_tag, tr("Only annotations with this tag")),
                         (self.f_category, tr("Only annotations in this category"))):
            box.setToolTip(tip)
            # Sin esto, un nombre de autor largo ensancharía todo el panel.
            box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            box.setMinimumContentsLength(6)
        self.sort = QComboBox()
        self.listed = QLabel()
        self.listed.setStyleSheet("color: palette(placeholder-text);")
        self.model = model
        self.table = QTableView()
        self.table.setModel(model)
        self.table.verticalHeader().setVisible(False)
        # Altura fija de fila: con ella Qt no mide cada fila, lo que importa con miles.
        self.table.verticalHeader().setDefaultSectionSize(self.table.fontMetrics().height() + 8)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(False)
        header = self.table.horizontalHeader()
        # (the columns fit their contents as a sample of the rows shows it: measuring every row, at each
        # change, would make a long list slow)
        header.setResizeContentsPrecision(60)
        for col in (PAGE, KIND, AUTHOR, STATUS, CHANGED):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        # The text column takes the room left by the others.
        header.setSectionResizeMode(TEXT, QHeaderView.ResizeMode.Stretch)
        self.title = QLabel()
        self.title.setWordWrap(True)
        self.color_button = QToolButton()
        # El botón de color abre su menú al instante; la ventana lo llena con los colores de la paleta.
        self.color_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.color_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.color_button.setMenu(QMenu(self.color_button))
        self.comment_label = QLabel(tr("Comment:"))
        self.comment = CommentEdit()
        self.comment.setMinimumHeight(70)
        self.tags = QLineEdit()
        self.tags.setPlaceholderText(tr("Tags, separated by commas"))
        self.replies = ReplyList()
        self.replies.setWordWrap(True)
        self.replies.setMaximumHeight(130)
        self.replies.setToolTip(tr("Double-click a reply to change it; Delete takes it out"))
        self.reply_edit = QLineEdit()
        self.reply_edit.setPlaceholderText(tr("Write a reply…"))
        self.reply_button = QPushButton(tr("Reply"))
        self.status = QComboBox()
        self.status.setToolTip(tr("Give the annotation a review status (a reply that says it)"))
        self.b_props = QPushButton(tr("Properties…"))
        self.b_delete = QPushButton(tr("Delete"))

        # Disposición vertical: búsqueda, filtros, orden, la lista y, debajo, la anotación seleccionada.
        filters = QHBoxLayout()
        for box in (self.f_kind, self.f_author, self.f_color):
            filters.addWidget(box, 1)
        filters2 = QHBoxLayout()
        for box in (self.f_status, self.f_tag, self.f_category):
            filters2.addWidget(box, 1)
        sort_row = QHBoxLayout()
        sort_row.addWidget(self.listed, 1)
        sort_row.addWidget(self.sort)
        color_row = QHBoxLayout()
        color_row.addWidget(QLabel(tr("Colour:")))
        color_row.addWidget(self.color_button, 1)
        tags_row = QHBoxLayout()
        tags_row.addWidget(QLabel(tr("Tags:")))
        tags_row.addWidget(self.tags, 1)
        reply_row = QHBoxLayout()
        reply_row.addWidget(self.reply_edit, 1)
        reply_row.addWidget(self.reply_button)
        status_row = QHBoxLayout()
        status_row.addWidget(QLabel(tr("Status:")))
        status_row.addWidget(self.status, 1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.b_props)
        buttons.addWidget(self.b_delete)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self.search)
        lay.addLayout(filters)
        lay.addLayout(filters2)
        lay.addLayout(sort_row)
        # The list gets three parts of the spare height; the comment and the replies one each.
        lay.addWidget(self.table, 3)
        lay.addWidget(self.title)
        lay.addLayout(color_row)
        lay.addWidget(self.comment_label)
        lay.addWidget(self.comment, 1)
        lay.addLayout(tags_row)
        self.replies_label = QLabel(tr("Replies:"))
        lay.addWidget(self.replies_label)
        lay.addWidget(self.replies, 1)
        lay.addLayout(reply_row)
        lay.addLayout(status_row)
        lay.addLayout(buttons)
