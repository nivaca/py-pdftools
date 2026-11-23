"""El panel Historial (Ver > Paneles, F10): todo lo hecho al documento, paso a paso, desde que se abrió; lo
que Rehacer puede devolver, debajo, en gris. Un clic en un paso deshace o rehace hasta él, de una vez.

Cada paso se describe sin guardar nada aparte: un cambio del documento mismo lleva su mensaje en su DocState
("Páginas movidas"); uno de las anotaciones se compara con el estado siguiente. Como un cambio hace una lista
nueva con los mismos objetos de antes, salvo los que cambió, comparar por identidad dice qué se añadió, qué se
borró y qué cambió, y rápido aun con miles de anotaciones."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QKeySequence
from PySide6.QtWidgets import QDockWidget, QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from ..core.interface import ntr, tr
from .working import DocState

ROW = Qt.ItemDataRole.UserRole  # (the place of a row in the history: 0, the document as it was opened)


def annotations_of(state) -> list:
    """The annotations of a step of the history (a list of them, or a DocState)."""
    return list(state.annotations) if isinstance(state, DocState) else list(state)


def describe(before: list, after: list) -> str:
    """What a change of the annotations from BEFORE to AFTER was, in a few words."""
    after_ids = {id(a) for a in after}
    before_ids = {id(a) for a in before}
    gone = [a for a in before if id(a) not in after_ids]
    new = [a for a in after if id(a) not in before_ids]
    # Una anotación cambiada sale y vuelve a entrar: se empareja por su tipo y su fecha de creación
    pairs = 0
    left = list(new)
    for a in gone:
        twin = next((b for b in left if b.kind == a.kind and b.created == a.created), None)
        if twin is not None:
            left.remove(twin)
            pairs += 1
    added, removed = len(new) - pairs, len(gone) - pairs
    if pairs and not added and not removed:
        if pairs == 1:
            changed = next(b for b in new if any(a.kind == b.kind and a.created == b.created for a in gone))
            return tr("{what} changed, page {page}", what=changed.name(), page=changed.page + 1)
        return ntr("{count} annotation changed", "{count} annotations changed", pairs)
    if added and not removed and not pairs:
        if added == 1:
            return tr("{what} added, page {page}", what=new[0].name(), page=new[0].page + 1)
        return ntr("{count} annotation added", "{count} annotations added", added)
    if removed and not added and not pairs:
        if removed == 1:
            return tr("{what} deleted, page {page}", what=gone[0].name(), page=gone[0].page + 1)
        return ntr("{count} annotation deleted", "{count} annotations deleted", removed)
    if not (added or removed or pairs):
        return tr("Annotations reordered")
    return tr("Annotations changed")


class HistoryMixin:
    """(Mixed into MainWindow: it uses undo_stack, redo_stack, annotations, undo and redo.)"""

    def _build_history(self):
        self.history_list = QListWidget()
        self.history_list.setAccessibleName(tr("History"))
        self.history_list.itemActivated.connect(lambda item: self.history_jump(item.data(ROW)))
        self.history_list.itemClicked.connect(lambda item: self.history_jump(item.data(ROW)))
        note = QLabel(tr("A click on a step undoes or redoes everything up to it"))
        note.setWordWrap(True)
        note.setStyleSheet("color: palette(placeholder-text);")
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(note)
        lay.addWidget(self.history_list, 1)
        self.history_dock = dock = QDockWidget(tr("History"), self)
        dock.setObjectName("history")
        dock.setWidget(inner)
        dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        dock.hide()
        dock.visibilityChanged.connect(lambda shown: self.history_refresh() if shown else None)
        self.a_history = dock.toggleViewAction()
        self.a_history.setText(tr("History"))
        self.a_history.setShortcut(QKeySequence("F10"))
        self.a_history.setToolTip(tr("Everything done to the document, step by step; a click on a step undoes or "
                                     "redoes up to it"))

    def history_steps(self) -> list[tuple[str, bool]]:
        """The rows of the history: (what, done), the first the document as it was opened; those not done are
        what Redo can bring back, the next one first."""
        rows = [(tr("The document as it was opened"), True)]
        undo, redo = self.undo_stack, self.redo_stack
        for k, state in enumerate(undo):
            if isinstance(state, DocState):
                rows.append((state.what or tr("A change of the document"), True))
                continue
            after = annotations_of(undo[k + 1]) if k + 1 < len(undo) else list(self.annotations)
            rows.append((describe(list(state), after), True))
        before = list(self.annotations)
        for state in reversed(redo):
            if isinstance(state, DocState):
                rows.append((state.what or tr("A change of the document"), False))
            else:
                rows.append((describe(before, list(state)), False))
            before = annotations_of(state)
        return rows

    def history_refresh(self):
        """The list again, if it is shown (it is made again when it is shown)."""
        if not hasattr(self, "history_dock") or not self.history_dock.isVisible():
            return
        lst = self.history_list
        lst.blockSignals(True)
        lst.clear()
        now = len(self.undo_stack)
        for row, (what, done) in enumerate(self.history_steps()):
            item = QListWidgetItem(what)
            item.setData(ROW, row)
            if row == now:  # (where the document is now)
                font = QFont(item.font())
                font.setBold(True)
                item.setFont(font)
            elif not done:
                item.setForeground(lst.palette().placeholderText())
            lst.addItem(item)
        lst.setCurrentRow(now)
        lst.scrollToItem(lst.item(now))
        lst.blockSignals(False)

    def history_jump(self, row: int):
        """Undo or redo until the document is as it was after the step ROW (0: as it was opened)."""
        now = len(self.undo_stack)
        if row is None or row == now:
            return
        # (paso a paso, como con las teclas: cada uno deja el documento en un estado que ya existió)
        for _ in range(now - row):
            if not self.undo_stack:
                break
            self.undo()
        for _ in range(row - now):
            if not self.redo_stack:
                break
            self.redo()
        self.history_refresh()
