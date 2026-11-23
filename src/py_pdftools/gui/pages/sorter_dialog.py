"""Ver > Clasificador de páginas: todas las páginas en una cuadrícula de miniaturas grandes, que ocupa casi
toda la ventana, para ordenar un documento largo de una vez. Las páginas se arrastran a su nuevo lugar
(varias elegidas a la vez), se giran, se borran o se duplican; nada cambia en el documento hasta Aceptar,
que hace todo como un solo cambio (arrange.Sort), deshecho de una vez con Deshacer. «Como estaba» vuelve
al orden del documento. Las miniaturas se dibujan solo cuando se ven, para que un libro de cientos de
páginas se abra enseguida."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPalette, QPen, QPixmap, QShortcut, QTransform
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QListView, QListWidget, QListWidgetItem,
    QPushButton, QSlider, QVBoxLayout,
)

from ...core.interface import ntr, tr
from ...pages import arrange

PAGE = Qt.ItemDataRole.UserRole  # (the page of the document an item is: 1-based)
TURN = Qt.ItemDataRole.UserRole + 1  # (how much it is turned here, clockwise: 0, 90, 180, 270)
DRAWN = Qt.ItemDataRole.UserRole + 2  # (the size its picture was drawn at; 0: not yet)
SIZES = (100, 420)  # the smallest and largest side of a thumbnail, in pixels


def framed(pixmap: QPixmap) -> QPixmap:
    """PIXMAP with a thin grey border, so that a white page shows where it ends."""
    painter = QPainter(pixmap)
    painter.setPen(QPen(QColor(110, 110, 110), 1))
    painter.drawRect(0, 0, pixmap.width() - 1, pixmap.height() - 1)
    painter.end()
    return pixmap


class SorterDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle(tr("Page sorter"))
        self.labels = window.page_labels() if window.doc is not None else []
        self.side = 180

        self.grid = QListWidget()
        self.grid.setAccessibleName(tr("Page sorter"))
        self.grid.setViewMode(QListView.ViewMode.IconMode)
        self.grid.setFlow(QListView.Flow.LeftToRight)
        self.grid.setWrapping(True)
        self.grid.setResizeMode(QListView.ResizeMode.Adjust)
        self.grid.setMovement(QListView.Movement.Snap)
        self.grid.setUniformItemSizes(True)
        self.grid.setSpacing(10)
        # El mismo fondo que las páginas en la ventana: una página blanca se distingue de él
        palette = self.grid.palette()
        palette.setBrush(QPalette.ColorRole.Base, window.canvas.backgroundBrush())
        self.grid.setPalette(palette)
        # Arrastrar dentro de la cuadrícula mueve las páginas elegidas (Qt lleva consigo los datos de cada una)
        self.grid.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.grid.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.grid.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.grid.verticalScrollBar().valueChanged.connect(lambda _: self.draw_timer.start(0))
        self.grid.model().rowsMoved.connect(lambda *_: self._changed())
        self.grid.itemSelectionChanged.connect(self._show_state)
        # (una miniatura por vuelta del bucle de eventos, solo las que se ven)
        self.draw_timer = QTimer(self, interval=0)
        self.draw_timer.timeout.connect(self._draw_one)

        def button(text, slot, tip):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            return b

        self.b_left = button(tr("Rotate left"), lambda: self.turn(270), tr("The pages chosen, 90° counterclockwise"))
        self.b_right = button(tr("Rotate right"), lambda: self.turn(90), tr("The pages chosen, 90° clockwise"))
        self.b_duplicate = button(tr("Duplicate"), self.duplicate, tr("A copy of each page chosen, right after it"))
        self.b_delete = button(tr("Delete"), self.delete, tr("Take the pages chosen out (Del)"))
        self.b_reset = button(tr("As it was"), self.reset, tr("The pages in the order of the document, as at first"))
        QShortcut(QKeySequence(QKeySequence.StandardKey.Delete), self.grid, self.delete)
        QShortcut(QKeySequence("Ctrl+A"), self.grid, self.grid.selectAll)
        self.size = QSlider(Qt.Orientation.Horizontal)
        self.size.setRange(*SIZES)
        self.size.setValue(self.side)
        self.size.setMaximumWidth(220)
        self.size.setToolTip(tr("The size of the pages"))
        self.size.setAccessibleName(tr("The size of the pages"))
        self.size.valueChanged.connect(self.set_side)
        tools = QHBoxLayout()
        for b in (self.b_left, self.b_right, self.b_duplicate, self.b_delete, self.b_reset):
            tools.addWidget(b)
        tools.addStretch(1)
        tools.addWidget(QLabel(tr("Size:")))
        tools.addWidget(self.size)

        self.state = QLabel()
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        foot = QHBoxLayout()
        foot.addWidget(self.state, 1)
        foot.addWidget(self.buttons)

        lay = QVBoxLayout(self)
        lay.addLayout(tools)
        lay.addWidget(self.grid, 1)
        lay.addLayout(foot)
        # Casi toda la ventana: el clasificador es para ver muchas páginas a la vez
        size = window.size()
        self.resize(max(700, int(size.width() * 0.92)), max(500, int(size.height() * 0.9)))
        self.reset()

    # ----------------------------------------------------------------- the items

    def _item(self, page: int, turn: int = 0) -> QListWidgetItem:
        item = QListWidgetItem(self._caption(page))
        item.setData(PAGE, page)
        item.setData(TURN, turn % 360)
        item.setData(DRAWN, 0)
        item.setIcon(self._blank())
        item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
        return item

    def _caption(self, page: int) -> str:
        label = self.labels[page - 1] if page - 1 < len(self.labels) else ""
        # (el número de la página en el documento, y su etiqueta si no es ese número)
        return f"{page}" if not label or label == str(page) else f"{page}  ({label})"

    def _blank(self) -> QIcon:
        pixmap = QPixmap(self.side, self.side)
        pixmap.fill(Qt.GlobalColor.transparent)
        return QIcon(pixmap)

    def items(self) -> list[QListWidgetItem]:
        return [self.grid.item(r) for r in range(self.grid.count())]

    def reset(self):
        """The pages as the document has them."""
        self.grid.clear()
        for page in range(1, self.window.count + 1):
            self.grid.addItem(self._item(page))
        self.set_side(self.side, force=True)
        self._changed()

    def set_side(self, side: int, force: bool = False):
        if side == self.side and not force:
            return
        self.side = side
        self.grid.setIconSize(QSize(side, side))
        self.grid.setGridSize(QSize(side + 24, side + 40))
        for item in self.items():
            item.setData(DRAWN, 0)
        self.draw_timer.start(0)

    # ----------------------------------------------------------------- drawing, only what is seen

    def _draw_one(self):
        """Draw the next thumbnail in view not yet drawn at this size; stop when there is none."""
        doc = self.window.doc
        view = self.grid.viewport().rect()
        for item in self.items():
            if item.data(DRAWN) == self.side or not self.grid.visualItemRect(item).intersects(view):
                continue
            from ..canvas import page_image

            page = doc[item.data(PAGE) - 1]
            scale = self.side / max(page.rect.width, page.rect.height)
            image = page_image(page, scale)
            turn = item.data(TURN)
            if turn:
                image = image.transformed(QTransform().rotate(turn))
            item.setIcon(QIcon(framed(QPixmap.fromImage(image))))
            item.setData(DRAWN, self.side)
            return
        self.draw_timer.stop()

    def showEvent(self, event):
        super().showEvent(event)
        self.draw_timer.start(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.draw_timer.start(0)

    # ----------------------------------------------------------------- the changes

    def chosen(self) -> list[QListWidgetItem]:
        return sorted(self.grid.selectedItems(), key=self.grid.row)

    def turn(self, angle: int):
        for item in self.chosen():
            item.setData(TURN, (item.data(TURN) + angle) % 360)
            item.setData(DRAWN, 0)
        self.draw_timer.start(0)
        self._changed()

    def duplicate(self):
        for item in reversed(self.chosen()):
            copy = self._item(item.data(PAGE), item.data(TURN))
            self.grid.insertItem(self.grid.row(item) + 1, copy)
        self.draw_timer.start(0)
        self._changed()

    def delete(self):
        chosen = self.chosen()
        # Un PDF necesita al menos una página: no se pueden quitar todas
        if not chosen or len(chosen) >= self.grid.count():
            self.state.setText(tr("A document needs one page at least: not every page can be deleted"))
            return
        for item in chosen:
            self.grid.takeItem(self.grid.row(item))
        self._changed()

    def _changed(self):
        self.draw_timer.start(0)
        self._show_state()

    def _show_state(self):
        n = self.grid.count()
        text = ntr("{count} page", "{count} pages", n)
        chosen = len(self.grid.selectedItems())
        if chosen:
            text += " · " + ntr("{count} chosen", "{count} chosen", chosen)
        if self.operation() is not None:
            text += " · " + tr("changed: OK makes the changes, as one step that Undo takes back")
        self.state.setText(text)
        for b in (self.b_left, self.b_right, self.b_duplicate, self.b_delete):
            b.setEnabled(bool(chosen))

    def operation(self) -> arrange.Sort | None:
        """What the sorter does to the document (None: nothing)."""
        order = tuple(item.data(PAGE) for item in self.items())
        turns = tuple((place, item.data(TURN)) for place, item in enumerate(self.items(), 1) if item.data(TURN))
        op = arrange.Sort(order, turns, count=self.window.count)
        return op if op.moves_pages() or turns else None
