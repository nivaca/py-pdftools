"""El diálogo de aplanar anotaciones (véase annotate/flatten.py): cuáles
(todas, las seleccionadas o las de algunos tipos), si sus comentarios se
escriben en la página, y dónde (en el documento mismo, como un cambio que
Deshacer revierte, o en una copia).
"""

from __future__ import annotations

import dataclasses

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QGroupBox, QLabel, QListWidget, QListWidgetItem,
    QRadioButton, QVBoxLayout,
)

from ..annotate.annots import Annotation
from ..core.interface import ntr, tr


@dataclasses.dataclass
class Choice:
    chosen: list[int]  # the indices of the annotations to flatten
    comments: bool  # their comments written on the page, beside each
    copy: bool  # in a copy (else in the document itself)


class FlattenDialog(QDialog):
    def __init__(self, annotations: list[Annotation], candidates: list[int], selected: list[int], parent=None,
                 copy: bool = False):
        super().__init__(parent)
        self.setWindowTitle(tr("Flatten annotations"))
        self.annotations, self.candidates = annotations, candidates
        selected = [i for i in selected if i in candidates]
        self.selected = selected
        lay = QVBoxLayout(self)
        intro = QLabel(tr("Flattened annotations become part of the pages: every program shows and prints them, "
                          "but they can no longer be edited, moved or removed."))
        intro.setWordWrap(True)
        lay.addWidget(intro)

        which = QGroupBox(tr("Which annotations"))
        box = QVBoxLayout(which)
        self.all = QRadioButton(ntr("All ({count})", "All ({count})", len(candidates)))
        self.some = QRadioButton(ntr("The one selected", "The {count} selected", len(selected)))
        self.some.setEnabled(bool(selected))
        self.kinds = QRadioButton(tr("Those of these kinds:"))
        self.scope = QButtonGroup(self)
        for b in (self.all, self.some, self.kinds):
            self.scope.addButton(b)
            box.addWidget(b)
        self.kind_list = QListWidget()
        counts: dict[str, int] = {}
        names: dict[str, str] = {}
        for i in candidates:
            a = annotations[i]
            counts[a.kind] = counts.get(a.kind, 0) + 1
            names.setdefault(a.kind, a.name())
        for kind, count in counts.items():
            item = QListWidgetItem(f"{names[kind]} ({count})")
            item.setData(Qt.ItemDataRole.UserRole, kind)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.kind_list.addItem(item)
        rows = min(max(len(counts), 2), 6)
        self.kind_list.setMaximumHeight(rows * self.kind_list.sizeHintForRow(0) + 2 * self.kind_list.frameWidth() + 2)
        box.addWidget(self.kind_list)
        (self.some if selected else self.all).setChecked(True)
        self.kind_list.itemChanged.connect(lambda _: self.kinds.setChecked(True))
        lay.addWidget(which)

        self.comments = QCheckBox(tr("Write their comments on the page, in a box beside each"))
        self.comments.setToolTip(tr("Flattened, a note keeps only its icon and a highlight only its colour: their "
                                    "texts, and their replies, would be lost. Text boxes and callouts show their "
                                    "text already."))
        self.comments.setChecked(True)
        lay.addWidget(self.comments)

        where = QGroupBox(tr("Where"))
        box = QVBoxLayout(where)
        self.here = QRadioButton(tr("In this document (Undo takes it back; Save keeps it)"))
        self.copy = QRadioButton(tr("In a copy (this document stays as it is)…"))
        group = QButtonGroup(self)
        for b in (self.here, self.copy):
            group.addButton(b)
            box.addWidget(b)
        (self.copy if copy else self.here).setChecked(True)
        lay.addWidget(where)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Flatten"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def chosen(self) -> list[int]:
        if self.some.isChecked():
            return list(self.selected)
        if self.kinds.isChecked():
            kinds = {self.kind_list.item(r).data(Qt.ItemDataRole.UserRole) for r in range(self.kind_list.count())
                     if self.kind_list.item(r).checkState() == Qt.CheckState.Checked}
            return [i for i in self.candidates if self.annotations[i].kind in kinds]
        return list(self.candidates)

    def choice(self) -> Choice:
        return Choice(self.chosen(), self.comments.isChecked(), self.copy.isChecked())


def ask_flatten(parent, annotations: list[Annotation], candidates: list[int], selected: list[int],
                copy: bool = False) -> Choice | None:
    dialog = FlattenDialog(annotations, candidates, selected, parent, copy)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return dialog.choice()
