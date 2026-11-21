"""Toolbars made to measure (mixed into MainWindow): Settings > Customize the toolbars (or a right click on a
toolbar) chooses the buttons of each toolbar and their order, from every action of the window that has a name
(those of the menus, the tools, the modes); separators go between them; new toolbars are added, and those
added are removed. What is changed is kept (the setting 'toolbar_contents'), and each toolbar can go back to
what it had at first.

Each action is known by a name that doesn't change with the language: that of its attribute in the window
('a_save'), 'tool:KEY' for a tool, 'mode:KEY' for a mode. The bar of the modes is not changed here."""

from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QPushButton, QToolBar, QVBoxLayout,
)

from ..core.interface import tr

SEPARATOR = "|"
SETTING = "toolbar_contents"


def plain(text: str) -> str:
    """The text of an action as shown in a list: without its key marker (&) and its dots."""
    return text.replace("&&", "\0").replace("&", "").replace("\0", "&").rstrip("…").rstrip(".")


class ToolbarsMixin:
    """(Mixed into MainWindow: it uses its toolbars, tool_actions and mode_actions.)"""

    def _init_toolbars(self):
        """What each toolbar has at first (to go back to it), and the toolbars as they were left."""
        self._tb_defaults = {bar.objectName(): self.bar_ids(bar) for bar in self.editable_bars()}
        self._tb_custom: list[QToolBar] = []
        self.apply_toolbar_layout(self.toolbar_layout(), keep=False)

    # ----------------------------------------------------------------- the actions, by name

    def action_ids(self) -> dict[str, QAction]:
        """{name: action} of every action that may go on a toolbar."""
        found: dict[str, QAction] = {}
        for key, act in getattr(self, "tool_actions", {}).items():
            found[f"tool:{key}"] = act
        for key, act in getattr(self, "mode_actions", {}).items():
            found[f"mode:{key}"] = act
        taken = {id(a) for a in found.values()}
        for name, value in vars(self).items():
            if isinstance(value, QAction) and name.startswith("a_") and id(value) not in taken and value.text():
                found[name] = value
                taken.add(id(value))
        return found

    def bar_ids(self, bar: QToolBar) -> list[str]:
        names = {id(a): n for n, a in self.action_ids().items()}
        return [SEPARATOR if a.isSeparator() else names[id(a)] for a in bar.actions()
                if a.isSeparator() or id(a) in names]

    def editable_bars(self) -> list[QToolBar]:
        return [bar for bar in self.toolbars() if bar is not getattr(self, "modes_bar", None)]

    def bar_title(self, bar: QToolBar) -> str:
        """The name of BAR, with that of its mode, if it is of one."""
        from .modes import TITLES

        for key, mode in getattr(self, "modes", {}).items():
            if bar in mode.bars:
                return f"{bar.windowTitle()} ({tr(TITLES[key])})"
        return bar.windowTitle()

    # ----------------------------------------------------------------- kept and applied

    def toolbar_layout(self) -> dict:
        """{'bars': {name: [action names]} of the toolbars changed, 'custom': [[name, title]] of those added}."""
        try:
            layout = json.loads(str(self.settings.value(SETTING, "{}")))
        except (TypeError, ValueError):
            return {"bars": {}, "custom": []}
        if not isinstance(layout, dict):
            return {"bars": {}, "custom": []}
        bars = layout.get("bars") if isinstance(layout.get("bars"), dict) else {}
        custom = [c for c in layout.get("custom", []) if isinstance(c, list) and len(c) == 2]
        return {"bars": bars, "custom": custom}

    def apply_toolbar_layout(self, layout: dict, keep: bool = True):
        """Give the toolbars what LAYOUT says (see toolbar_layout): those added made (or removed), and each
        filled with its actions; KEEP: kept for the next time."""
        wanted = {name for name, _ in layout["custom"]}
        for bar in list(self._tb_custom):
            if bar.objectName() not in wanted:
                self._tb_custom.remove(bar)
                if bar in self.common_bars:
                    self.common_bars.remove(bar)
                self.removeToolBar(bar)
                bar.setParent(None)  # (ya no es de la ventana, aunque se borre más tarde)
                bar.deleteLater()
        have = {bar.objectName() for bar in self._tb_custom}
        for name, title in layout["custom"]:
            if name not in have:
                bar = self.toolbar_of(name, title, [])
                bar.setToolButtonStyle(self._tb_style())
                self._tb_custom.append(bar)
                self.common_bars.append(bar)  # (of every mode)
        actions = self.action_ids()
        for bar in self.editable_bars():
            ids = layout["bars"].get(bar.objectName(), self._tb_defaults.get(bar.objectName(), []))
            if self.bar_ids(bar) == ids:
                continue
            bar.clear()
            for name in ids:
                if name == SEPARATOR:
                    bar.addSeparator()
                elif name in actions:
                    bar.addAction(actions[name])
            self._tool_button_menus(bar)
        self._toolbar_tips()
        if keep:
            changed = {bar.objectName(): self.bar_ids(bar) for bar in self.editable_bars()
                       if self.bar_ids(bar) != self._tb_defaults.get(bar.objectName(), [])}
            self.settings.setValue(SETTING, json.dumps({"bars": changed, "custom": layout["custom"]}))

    def _tb_style(self) -> Qt.ToolButtonStyle:
        on = getattr(self, "a_labels", None) is not None and self.a_labels.isChecked()
        return Qt.ToolButtonStyle.ToolButtonTextUnderIcon if on else Qt.ToolButtonStyle.ToolButtonIconOnly

    def customize_toolbars(self) -> bool:
        layout = self.ask_toolbars()
        if layout is None:
            return False
        self.apply_toolbar_layout(layout)
        self.status(tr("The toolbars were changed"))
        return True

    def ask_toolbars(self) -> dict | None:
        dialog = ToolbarsDialog(self)
        return dialog.layout_chosen() if dialog.exec() == QDialog.DialogCode.Accepted else None


class ToolbarsDialog(QDialog):
    """The buttons of each toolbar: those available on the left, those of the toolbar chosen on the right."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle(tr("Customize the toolbars"))
        self.actions_ = win.action_ids()
        self.defaults = dict(win._tb_defaults)
        self.titles = {bar.objectName(): win.bar_title(bar) for bar in win.editable_bars()}
        self.contents = {bar.objectName(): win.bar_ids(bar) for bar in win.editable_bars()}
        self.custom = [[bar.objectName(), bar.windowTitle()] for bar in win._tb_custom]

        self.bar = QComboBox()
        self.bar.currentIndexChanged.connect(lambda _i: self._show_bar())
        self.filter = QLineEdit()
        self.filter.setPlaceholderText(tr("Filter"))
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(lambda _t: self._fill_available())
        blank = QPixmap(22, 22)
        blank.fill(Qt.GlobalColor.transparent)
        self._blank = QIcon(blank)
        self.available = QListWidget()
        self.available.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.available.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.available.itemDoubleClicked.connect(lambda _i: self.add())
        self.chosen = QListWidget()
        self.chosen.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.chosen.model().rowsMoved.connect(lambda *_a: self._read_chosen())
        self.chosen.itemDoubleClicked.connect(lambda _i: self.remove())

        def button(text, slot):
            b = QPushButton(text)
            b.clicked.connect(slot)
            return b

        self.b_add, self.b_remove = button(tr("Add →"), self.add), button(tr("← Remove"), self.remove)
        self.b_up, self.b_down = button(tr("Up"), lambda: self.move(-1)), button(tr("Down"), lambda: self.move(1))
        self.b_separator = button(tr("Add a separator"), self.add_separator)
        self.b_reset = button(tr("As it was at first"), self.reset)
        self.b_new = button(tr("New toolbar…"), self.new_bar)
        self.b_delete = button(tr("Delete this toolbar"), self.delete_bar)
        middle = QVBoxLayout()
        middle.addStretch(1)
        for b in (self.b_add, self.b_remove, self.b_up, self.b_down, self.b_separator):
            middle.addWidget(b)
        middle.addStretch(1)
        grid = QGridLayout()
        grid.addWidget(QLabel(tr("Available:")), 0, 0)
        grid.addWidget(QLabel(tr("On the toolbar:")), 0, 2)
        grid.addWidget(self.filter, 1, 0)
        grid.addWidget(self.available, 2, 0)
        grid.addLayout(middle, 2, 1)
        grid.addWidget(self.chosen, 1, 2, 2, 1)
        top = QHBoxLayout()
        top.addWidget(QLabel(tr("Toolbar:")))
        top.addWidget(self.bar, 1)
        top.addWidget(self.b_new)
        top.addWidget(self.b_delete)
        top.addWidget(self.b_reset)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addLayout(grid, 1)
        lay.addWidget(buttons)
        self.resize(760, 520)
        self._fill_bars()

    # ----------------------------------------------------------------- the lists

    def _fill_bars(self, current: str = ""):
        self.bar.blockSignals(True)
        self.bar.clear()
        for name in self.contents:
            self.bar.addItem(self.titles[name], name)
        self.bar.blockSignals(False)
        index = self.bar.findData(current)
        self.bar.setCurrentIndex(max(index, 0))
        self._show_bar()

    def current(self) -> str:
        return self.bar.currentData() or ""

    def _item(self, name: str) -> QListWidgetItem:
        if name == SEPARATOR:
            item = QListWidgetItem("――――――――")
        else:
            act = self.actions_[name]
            # (una acción sin icono lleva uno vacío, para que los textos queden alineados)
            item = QListWidgetItem(act.icon() if not act.icon().isNull() else self._blank, plain(act.text()))
            item.setToolTip(act.toolTip())
        item.setData(Qt.ItemDataRole.UserRole, name)
        return item

    def _fill_available(self):
        words = self.filter.text().casefold().split()
        on_bar = set(self.contents.get(self.current(), []))
        self.available.clear()
        for name, act in sorted(self.actions_.items(), key=lambda kv: plain(kv[1].text()).casefold()):
            text = plain(act.text()).casefold()
            if name not in on_bar and all(w in text for w in words):
                self.available.addItem(self._item(name))

    def _show_bar(self):
        self.chosen.clear()
        for name in self.contents.get(self.current(), []):
            if name == SEPARATOR or name in self.actions_:
                self.chosen.addItem(self._item(name))
        self._fill_available()
        custom = any(name == self.current() for name, _ in self.custom)
        self.b_delete.setEnabled(custom)
        self.b_reset.setEnabled(not custom)

    def _read_chosen(self):
        self.contents[self.current()] = [self.chosen.item(r).data(Qt.ItemDataRole.UserRole)
                                         for r in range(self.chosen.count())]

    # ----------------------------------------------------------------- the changes

    def add(self, names: list[str] | None = None):
        """NAMES (those selected on the left, if None) put on the toolbar, after the button selected."""
        if names is None:
            names = [i.data(Qt.ItemDataRole.UserRole) for i in self.available.selectedItems()]
        row = self.chosen.currentRow() + 1 if self.chosen.currentRow() >= 0 else self.chosen.count()
        ids = self.contents.setdefault(self.current(), [])
        for name in names:
            if name == SEPARATOR or name not in ids:
                ids.insert(row, name)
                row += 1
        self._show_bar()
        self.chosen.setCurrentRow(row - 1)

    def add_separator(self):
        self.add([SEPARATOR])

    def remove(self):
        rows = sorted({self.chosen.row(i) for i in self.chosen.selectedItems()}, reverse=True)
        ids = self.contents.get(self.current(), [])
        for r in rows:
            del ids[r]
        self._show_bar()

    def move(self, step: int):
        row = self.chosen.currentRow()
        ids = self.contents.get(self.current(), [])
        if row < 0 or not 0 <= row + step < len(ids):
            return
        ids[row], ids[row + step] = ids[row + step], ids[row]
        self._show_bar()
        self.chosen.setCurrentRow(row + step)

    def reset(self):
        self.contents[self.current()] = list(self.defaults.get(self.current(), []))
        self._show_bar()

    def ask_title(self) -> str | None:
        title, ok = QInputDialog.getText(self, tr("New toolbar"), tr("Its name:"))
        return title.strip() if ok and title.strip() else None

    def new_bar(self, title: str | None = None):
        title = title or self.ask_title()
        if not title:
            return
        used = set(self.contents)
        n = 1
        while f"custom-{n}" in used:
            n += 1
        name = f"custom-{n}"
        self.custom.append([name, title])
        self.contents[name] = []
        self.titles[name] = title
        self._fill_bars(name)

    def delete_bar(self):
        name = self.current()
        self.custom = [c for c in self.custom if c[0] != name]
        self.contents.pop(name, None)
        self._fill_bars()

    def layout_chosen(self) -> dict:
        return {"bars": {n: ids for n, ids in self.contents.items()
                         if ids != self.defaults.get(n, []) or any(n == c[0] for c in self.custom)},
                "custom": self.custom}
