"""Toolbars made to measure (mixed into MainWindow): Settings > Customize the toolbars (or a right click on a
toolbar) chooses the buttons of each toolbar and their order, from every action of the window that has a name
(those of the menus, the tools, the modes); separators go between them; new toolbars are added, and those
added are removed. What is changed is kept (the setting 'toolbar_contents'), and each toolbar can go back to
what it had at first.

Each action is known by a name that doesn't change with the language: that of its attribute in the window
('a_save'), 'tool:KEY' for a tool, 'mode:KEY' for a mode. The bar of the modes is not changed here."""

from __future__ import annotations

import json

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMenu, QPushButton, QToolBar, QVBoxLayout,
)

from ..core.interface import N_, tr

SEPARATOR = "|"
SETTING = "toolbar_contents"
LOOKS = "toolbar_looks"  # (the setting of how the toolbars look: see looks())
# how the buttons show: (key, name, Qt's style)
STYLES = [("icons", N_("Icons only"), Qt.ToolButtonStyle.ToolButtonIconOnly),
          ("text", N_("Text only"), Qt.ToolButtonStyle.ToolButtonTextOnly),
          ("beside", N_("Text alongside icons"), Qt.ToolButtonStyle.ToolButtonTextBesideIcon),
          ("under", N_("Text under icons"), Qt.ToolButtonStyle.ToolButtonTextUnderIcon)]
SIZES = [(16, N_("Small (16)")), (22, N_("Medium (22)")), (32, N_("Large (32)")), (48, N_("Huge (48)"))]
DEFAULT_LOOKS = {"style": "icons", "size": 22, "locked": False, "bars": {"modes": {"style": "beside", "size": 20}}}


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
        self.apply_bar_looks()

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
        if hasattr(self, "_tb_custom"):
            self.apply_bar_looks()
        if keep:
            changed = {bar.objectName(): self.bar_ids(bar) for bar in self.editable_bars()
                       if self.bar_ids(bar) != self._tb_defaults.get(bar.objectName(), [])}
            self.settings.setValue(SETTING, json.dumps({"bars": changed, "custom": layout["custom"]}))

    # ----------------------------------------------------------------- how they look

    def looks(self) -> dict:
        """How the toolbars look: {'style': of STYLES, 'size': of the icons, 'locked': whether they stay where
        they are, 'bars': {name: {'style', 'size'}} of those that look otherwise}. (An older setting, labels
        under the icons, is read as the style 'under'.)"""
        try:
            found = json.loads(str(self.settings.value(LOOKS, "")))
        except (TypeError, ValueError):
            found = None
        if not isinstance(found, dict):
            found = json.loads(json.dumps(DEFAULT_LOOKS))
            if str(self.settings.value("toolbar_labels", "false")) == "true":
                found["style"] = "under"
        found.setdefault("bars", {})
        return found

    def _keep_looks(self, looks: dict):
        self.settings.setValue(LOOKS, json.dumps(looks))

    def look_of(self, bar: QToolBar) -> tuple[str, int]:
        """(style, size of the icons) of BAR: its own, or that of all."""
        looks = self.looks()
        own = looks["bars"].get(bar.objectName(), {})
        return own.get("style", looks["style"]), int(own.get("size", looks["size"]))

    def apply_bar_looks(self):
        """Every toolbar as looks() says."""
        looks = self.looks()
        styles = {k: style for k, _, style in STYLES}
        for bar in self.toolbars():
            style, size = self.look_of(bar)
            bar.setToolButtonStyle(styles.get(style, Qt.ToolButtonStyle.ToolButtonIconOnly))
            bar.setIconSize(QSize(size, size))
            bar.setMovable(not looks.get("locked"))

    def set_bar_look(self, bar: QToolBar | None = None, style: str | None = None, size: int | None = None):
        """STYLE and SIZE (those given) of BAR, or of all the toolbars (BAR None: then those of each go)."""
        looks = self.looks()
        for key, value in (("style", style), ("size", size)):
            if value is None:
                continue
            if bar is None:
                looks[key] = value
                for own in looks["bars"].values():
                    own.pop(key, None)
            else:
                looks["bars"].setdefault(bar.objectName(), {})[key] = value
        looks["bars"] = {n: v for n, v in looks["bars"].items() if v}
        self._keep_looks(looks)
        self.apply_bar_looks()

    def set_bars_locked(self, locked: bool):
        looks = self.looks()
        looks["locked"] = locked
        self._keep_looks(looks)
        self.apply_bar_looks()

    def show_labels(self, on: bool):
        """(As the setting of old:) the names under the icons of every toolbar, or only icons."""
        self.set_bar_look(None, "under" if on else "icons")

    def looks_menu(self, menu: QMenu, bar: QToolBar | None = None):
        """In MENU, Text position and Icon size, of BAR (or of all the toolbars), Lock the toolbars, and
        Customize the toolbars."""
        from PySide6.QtGui import QActionGroup

        style, size = self.look_of(bar) if bar is not None else (self.looks()["style"], self.looks()["size"])
        for title, items, current, setter in (
                (tr("Text position"), [(k, tr(n)) for k, n, _ in STYLES], style,
                 lambda v: self.set_bar_look(bar, style=v)),
                (tr("Icon size"), [(px, tr(n)) for px, n in SIZES], size, lambda v: self.set_bar_look(bar, size=v))):
            sub = menu.addMenu(title)
            group = QActionGroup(sub)
            for value, name in items:
                act = sub.addAction(name)
                act.setCheckable(True)
                act.setChecked(value == current)
                group.addAction(act)
                act.triggered.connect(lambda _=False, v=value, f=setter: f(v))
        lock = menu.addAction(tr("Lock the toolbars"))
        lock.setCheckable(True)
        lock.setChecked(bool(self.looks().get("locked")))
        lock.setToolTip(tr("The toolbars stay where they are: they can't be dragged elsewhere"))
        lock.toggled.connect(self.set_bars_locked)
        if hasattr(self, "a_customize_bars"):
            menu.addAction(self.a_customize_bars)

    def toolbar_at(self, pos) -> QToolBar | None:
        """The toolbar of the window at POS (on the screen), if there is one."""
        from PySide6.QtWidgets import QApplication

        w = QApplication.widgetAt(pos)
        while w is not None and not isinstance(w, QToolBar):
            w = w.parentWidget()
        return w if w is not None and w.parent() is self else None

    def customize_toolbars(self) -> bool:
        layout = self.ask_toolbars()
        if layout is None:
            return False
        self.apply_toolbar_layout(layout)
        if "looks" in layout:
            looks = self.looks()
            looks["bars"] = layout["looks"]
            self._keep_looks(looks)
            self.apply_bar_looks()
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
        self.bar_looks = {n: dict(v) for n, v in win.looks()["bars"].items()}

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
        # Cómo se ve la barra elegida: su texto y el tamaño de sus iconos, o como todas.
        self.style = QComboBox()
        self.style.addItem(tr("As all the toolbars"), None)
        for key, name, _ in STYLES:
            self.style.addItem(tr(name), key)
        self.size = QComboBox()
        self.size.addItem(tr("As all the toolbars"), None)
        for px, name in SIZES:
            self.size.addItem(tr(name), px)
        self.style.activated.connect(lambda _i: self._set_look("style", self.style.currentData()))
        self.size.activated.connect(lambda _i: self._set_look("size", self.size.currentData()))
        looks_row = QHBoxLayout()
        looks_row.addWidget(QLabel(tr("Text position:")))
        looks_row.addWidget(self.style)
        looks_row.addWidget(QLabel(tr("Icon size:")))
        looks_row.addWidget(self.size)
        looks_row.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addLayout(looks_row)
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
        own = self.bar_looks.get(self.current(), {})
        self.style.setCurrentIndex(max(0, self.style.findData(own.get("style"))) if "style" in own else 0)
        self.size.setCurrentIndex(max(0, self.size.findData(own.get("size"))) if "size" in own else 0)

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

    def _set_look(self, key: str, value):
        own = self.bar_looks.setdefault(self.current(), {})
        if value is None:
            own.pop(key, None)
        else:
            own[key] = value

    def layout_chosen(self) -> dict:
        return {"bars": {n: ids for n, ids in self.contents.items()
                         if ids != self.defaults.get(n, []) or any(n == c[0] for c in self.custom)},
                "custom": self.custom,
                "looks": {n: v for n, v in self.bar_looks.items() if v}}
