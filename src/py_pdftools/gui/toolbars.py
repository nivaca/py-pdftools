"""Toolbars made to measure (mixed into MainWindow): Settings > Toolbars (or a right click on a toolbar) sets
how all of them look (the position of the text, the size of the icons, whether they are locked); Customize
the toolbars sets it for each one, and chooses the buttons of each toolbar and their order, from every
action of the window that has a name (those of the menus, the tools, the modes); separators go between them;
new toolbars are added, and those added are removed. What is changed is kept (the setting
'toolbar_contents'), and each toolbar can go back to what it had at first.

Each action is known by a name that doesn't change with the language: that of its attribute in the window
('a_save'), 'tool:KEY' for a tool, 'mode:KEY' for a mode. The bar of the modes is not changed here."""

from __future__ import annotations

import json

from PySide6.QtCore import QByteArray, QEvent, QObject, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox, QProxyStyle, QPushButton, QSizePolicy, QStyle,
    QToolBar, QToolButton, QToolTip, QVBoxLayout, QWidget,
)

from ..core.interface import N_, tr

SEPARATOR = "|"
# Un espacio que se estira, como el «--- expanding spacer ---» de las barras de KDE: al final de una fila empuja lo
# que lo sigue hasta el borde; en otro lugar es un hueco pequeño (SPACER_MIN)
SPACER = "<->"
SPACER_NAME = "toolbar-spacer"  # (the object name of its action, by which bar_ids knows it)
SPACER_MIN = 16
HANDLE = 14  # the width of a toolbar's handle, in pixels, at least (Fusion's is 9: hard to take hold of)
SETTING = "toolbar_contents"
LOOKS = "toolbar_looks"  # (the setting of how the toolbars look: see looks())
# El orden de las barras de arriba: cuando cambia, las disposiciones guardadas se ponen en el nuevo una vez
ORDER = "toolbar_order"
ORDER_VERSION = 2  # (2: Herramientas del ratón y Herramientas, y Buscar y Herramientas al final, 1.12.2)
# how the buttons show: (key, name, Qt's style)
STYLES = [("icons", N_("Icons only"), Qt.ToolButtonStyle.ToolButtonIconOnly),
          ("text", N_("Text only"), Qt.ToolButtonStyle.ToolButtonTextOnly),
          ("beside", N_("Text alongside icons"), Qt.ToolButtonStyle.ToolButtonTextBesideIcon),
          ("under", N_("Text under icons"), Qt.ToolButtonStyle.ToolButtonTextUnderIcon)]
SIZES = [(16, N_("Small (16)")), (22, N_("Medium (22)")), (32, N_("Large (32)")), (48, N_("Huge (48)"))]
# (iconos pequeños, todas las barras igual, la de los modos también: sus iconos los distinguen, y su nombre está
# en la pista)
DEFAULT_LOOKS = {"style": "icons", "size": 16, "locked": False, "bars": {}}


def plain(text: str) -> str:
    """The text of an action as shown in a list: without its key marker (&) and its dots."""
    return text.replace("&&", "\0").replace("&", "").replace("\0", "&").rstrip("…").rstrip(".")


class _HandleStyle(QProxyStyle):
    """The style of the application, with a wider handle for the toolbars (by which they are dragged)."""

    def pixelMetric(self, metric, option=None, widget=None):
        value = super().pixelMetric(metric, option, widget)
        if metric == QStyle.PixelMetric.PM_ToolBarHandleExtent:
            return max(value, HANDLE)
        return value


class _DragEnd(QObject):
    """When a toolbar is let go (after being dragged), the rows of toolbars are packed again: see pack_toolbars."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonRelease:
            self.win.schedule_pack()
        return False


def button_tip(act: QAction) -> str:
    """The tooltip of the button of ACT on a toolbar: its name in bold, its shortcut, and what it does."""
    # En los textos de las acciones, & marca la tecla de acceso y && es un & literal; aquí se quiere el texto limpio.
    text = act.text().replace("&&", "\0").replace("&", "").replace("\0", "&")
    keys = act.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
    tip = f"<b>{text}</b>" + (f" &nbsp;<span style='color:gray'>{keys}</span>" if keys else "")
    if act.statusTip():
        tip += f"<br>{act.statusTip()}"
    return tip


class ButtonTips(QObject):
    """The tooltip of a toolbar's button, made when it is shown (button_tip), with the action's name and key as
    they are then: one set on the button was lost the next time its action changed, since Qt gives the button
    the action's own tooltip again."""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.ToolTip and isinstance(obj, QToolButton) and obj.defaultAction() is not None:
            QToolTip.showText(event.globalPos(), button_tip(obj.defaultAction()), obj)
            return True
        return False


def add_spacer(bar: QToolBar) -> QAction:
    """An expanding spacer at the end of BAR."""
    space = QWidget(bar)
    space.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    space.setMinimumSize(SPACER_MIN, SPACER_MIN)
    act = bar.addWidget(space)
    act.setObjectName(SPACER_NAME)
    return act


class ToolbarsMixin:
    """(Mixed into MainWindow: it uses its toolbars, tool_actions and mode_actions.)"""

    def order_top_toolbars(self, every: bool = False):
        """The toolbars at the top as the program puts them: the modes and those of every mode in one row, in
        their order (common_bars), and below them the others (those of each mode, as they were made). Those the
        user put on a side, at the bottom or out of the window stay there, and each keeps being shown or hidden;
        with EVERY, all come back to the top, shown (each mode then hides what isn't its own)."""
        top = Qt.ToolBarArea.TopToolBarArea
        here = [bar for bar in self.toolbars()
                if every or (self.toolBarArea(bar) == top and not bar.isFloating())]
        hidden = {id(bar): bar.isHidden() and not every for bar in here}
        first = [bar for bar in [self.modes_bar, *self.common_bars] if bar in here]
        rest = [bar for bar in here if bar not in first]
        for bar in here:
            self.removeToolBar(bar)
        for bar in first:
            self.addToolBar(top, bar)
        if rest:
            self.addToolBarBreak(top)
            for bar in rest:
                self.addToolBar(top, bar)
        for bar in here:
            bar.setHidden(hidden[id(bar)])

    def update_toolbar_order(self):
        """Once, when the order of the toolbars changed in a new version: each arrangement kept (the window's,
        and that of each mode) is opened, its toolbars at the top put in the new order, and kept again; the
        panels stay where they were."""
        try:
            done = int(self.settings.value(ORDER, 1))
        except (TypeError, ValueError):
            done = 1
        if done >= ORDER_VERSION:
            return
        for key in ["toolbars"] + [f"arrangement/{mode}/state" for mode in getattr(self, "modes", {})]:
            state = self.settings.value(key)
            if isinstance(state, QByteArray):
                self.restoreState(state)
                self.order_top_toolbars()
                self.settings.setValue(key, self.saveState())
        self.settings.setValue(ORDER, ORDER_VERSION)

    def reset_toolbars(self, ask: bool = True) -> bool:
        """Settings > Toolbars > Reset the toolbars: every toolbar as it was at first, in every window: its
        buttons (those added by the user removed), its place, in the order of the program, in the arrangement of
        each mode, and how it looks. The panels stay where they are. ASK: say what it does, and ask, first."""
        if ask and QMessageBox.question(
                self, tr("Reset the toolbars"),
                tr("Put every toolbar back as it was at first: its buttons, its place and how it looks? The "
                   "toolbars you added are removed. The panels stay where they are.")) \
                != QMessageBox.StandardButton.Yes:
            return False
        self._keep_looks(json.loads(json.dumps(DEFAULT_LOOKS)))
        for win in self._every_window():
            win.apply_toolbar_layout({"bars": {}, "custom": []})
            win.apply_bar_looks()
            if win.host is None:  # (una pestaña usa la disposición de su ventana)
                win._reset_arrangements()
        return True

    def _reset_arrangements(self):
        """The toolbars of every arrangement kept (the window's, and each mode's) put back at the top, in the
        program's order; then the mode on arranged again."""
        for key in ["toolbars"] + [f"arrangement/{mode}/state" for mode in getattr(self, "modes", {})]:
            state = self.settings.value(key)
            if isinstance(state, QByteArray):
                self.restoreState(state)
                self.order_top_toolbars(every=True)
                self.settings.setValue(key, self.saveState())
        self.order_top_toolbars(every=True)
        mode = getattr(self, "modes", {}).get(getattr(self, "mode", None))
        if mode is not None:
            # (lo que se ve, como en arrange: las barras del modo y las de todos, menos las que el modo no usa)
            for other in self.modes.values():
                for bar in other.bars:
                    bar.setVisible(other is mode)
            for bar in self.common_bars:
                bar.setVisible(bar.objectName() not in mode.without)
            self.keep_arrangement()
        self.schedule_pack()

    def _init_toolbars(self):
        """What each toolbar has at first (to go back to it), and the toolbars as they were left."""
        names = self.action_names()
        self._tb_defaults = {bar.objectName(): self.bar_ids(bar, names) for bar in self.editable_bars()}
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

    def action_names(self) -> dict[int, str]:
        """{id(action): name} of the actions of action_ids (made once for several toolbars: see bar_ids)."""
        return {id(a): n for n, a in self.action_ids().items()}

    def bar_ids(self, bar: QToolBar, names: dict[int, str] | None = None) -> list[str]:
        """The names of the actions of BAR, in order (NAMES: action_names, if made already)."""
        # (action_ids recorre todos los atributos de la ventana: una vez por barra costaba unos 9 ms al arrancar)
        names = self.action_names() if names is None else names
        return [SEPARATOR if a.isSeparator() else SPACER if a.objectName() == SPACER_NAME else names[id(a)]
                for a in bar.actions() if a.isSeparator() or a.objectName() == SPACER_NAME or id(a) in names]

    def editable_bars(self) -> list[QToolBar]:
        # (ni la barra de los modos ni Página y zoom, que lleva widgets fijos, no acciones)
        # (ni la barra Buscar mientras se escribe, hecha de un solo widget)
        return [bar for bar in self.toolbars()
                if bar is not getattr(self, "modes_bar", None) and bar.objectName() not in ("pagezoom", "findbar")]

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
        names = {id(a): n for n, a in actions.items()}
        for bar in self.editable_bars():
            ids = layout["bars"].get(bar.objectName(), self._tb_defaults.get(bar.objectName(), []))
            if self.bar_ids(bar, names) == ids:
                continue
            for act in bar.actions():  # (los espacios son de su barra: se van con ella)
                if act.objectName() == SPACER_NAME:
                    act.deleteLater()
            bar.clear()
            for name in ids:
                if name == SEPARATOR:
                    bar.addSeparator()
                elif name == SPACER:
                    add_spacer(bar)
                elif name in actions:
                    bar.addAction(actions[name])
            self._tool_button_menus(bar)
        self._toolbar_tips()
        if hasattr(self, "_tb_custom"):
            self.apply_bar_looks()
        if keep:
            now = {bar.objectName(): self.bar_ids(bar, names) for bar in self.editable_bars()}
            changed = {n: ids for n, ids in now.items() if ids != self._tb_defaults.get(n, [])}
            self.settings.setValue(SETTING, json.dumps({"bars": changed, "custom": layout["custom"]}))
            self.settings.sync()

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
        self.settings.sync()  # (en el disco enseguida, no un momento después)

    def _every_window(self) -> list:
        """This window and the others open (in tabs too): a change of the toolbars goes to all of them, or the
        others would keep showing them as they were."""
        from .window import _WINDOWS

        return [self] + [w for w in _WINDOWS if w is not self and hasattr(w, "apply_bar_looks")]

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
            bar.setMovable(not looks.get("locked") and bar.objectName() != "findbar")  # (esa, siempre abajo)
            self._fit_toolbar(bar)
        # (con otro tamaño, las barras quedarían separadas por los huecos que dejaron)
        self.schedule_pack()

    # ----------------------------------------------------------------- where they are

    def _fit_toolbar(self, bar: QToolBar):
        """BAR with a wider handle, and packed with its row when it is let go (once for each toolbar)."""
        if bar.property("fitted"):
            return
        if getattr(self, "_handle_style", None) is None:
            self._handle_style = _HandleStyle()  # (the application's style, whatever it is)
            self._drag_end = _DragEnd(self)
        bar.setStyle(self._handle_style)
        bar.installEventFilter(self._drag_end)
        bar.topLevelChanged.connect(lambda _floating: self.schedule_pack())
        bar.setProperty("fitted", True)

    def schedule_pack(self):
        """Pack the rows of toolbars a moment later (after a drag, Qt places the toolbar first)."""
        if not getattr(self, "_pack_due", False):
            self._pack_due = True
            QTimer.singleShot(0, self.pack_toolbars)

    def pack_toolbars(self) -> bool:
        """The toolbars of each row side by side, from its start, in their order, without the empty spaces a
        drag leaves between them (Qt keeps the place where a toolbar was let go, and stretches the one before
        it up to there); each stays in its row. Whether a row was packed. (An empty space where one is wanted:
        a spacer, in Customize the toolbars.)"""
        self._pack_due = False
        packed = False
        areas = {Qt.ToolBarArea.TopToolBarArea: True, Qt.ToolBarArea.BottomToolBarArea: True,
                 Qt.ToolBarArea.LeftToolBarArea: False, Qt.ToolBarArea.RightToolBarArea: False}
        for area, across in areas.items():
            rows: dict[int, list[QToolBar]] = {}
            for bar in self.toolbars():
                if self.toolBarArea(bar) == area and bar.isVisible() and not bar.isFloating():
                    rows.setdefault(bar.geometry().y() if across else bar.geometry().x(), []).append(bar)
            for row in rows.values():
                row.sort(key=lambda b: b.geometry().x() if across else b.geometry().y())
                if len(row) < 2 or not self._gaps(row, across):
                    continue
                # insertToolBar forgets where a toolbar was let go: each is put again before the last, which is
                # first put at the start of the row (so that it forgets its place too)
                last = row[-1]
                self.insertToolBar(row[0], last)
                for bar in row[:-1]:
                    self.insertToolBar(last, bar)
                for bar in row:
                    bar.show()
                packed = True
        if packed and getattr(self, "mode", None) and hasattr(self, "keep_arrangement"):
            self.keep_arrangement()  # (the mode's arrangement, as it is now)
        return packed

    @staticmethod
    def _gaps(row: list[QToolBar], across: bool) -> bool:
        """Whether ROW (of toolbars, in their order) has empty spaces: one before the first, or a toolbar
        stretched beyond what it needs up to the next one."""
        def start(b):
            return b.geometry().x() if across else b.geometry().y()

        def length(b):
            return b.width() if across else b.height()

        def wanted(b):
            hint = b.sizeHint()
            return hint.width() if across else hint.height()

        # (only across: a column of the sides begins under the toolbars of the top, not at 0)
        return (across and start(row[0]) > 2) or any(length(b) > wanted(b) + 2 for b in row[:-1])

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
        for win in self._every_window():
            win.apply_bar_looks()

    def set_bars_locked(self, locked: bool):
        looks = self.looks()
        looks["locked"] = locked
        self._keep_looks(looks)
        for win in self._every_window():
            win.apply_bar_looks()

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
            menu.addAction(tr("Reset the toolbars…"), self.reset_toolbars)

    def customize_toolbars(self) -> bool:
        layout = self.ask_toolbars()
        if layout is None:
            return False
        self.apply_toolbar_layout(layout)
        others = self._every_window()[1:]
        for win in others:
            win.apply_toolbar_layout(layout, keep=False)  # (the buttons of each toolbar, in every window)
        if "looks" in layout:
            looks = self.looks()
            looks["bars"] = layout["looks"]
            self._keep_looks(looks)
        for win in [self, *others]:
            win.apply_bar_looks()
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
        names = win.action_names()
        self.contents = {bar.objectName(): win.bar_ids(bar, names) for bar in win.editable_bars()}
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
        self.b_spacer = button(tr("Add a spacer"), self.add_spacer)
        self.b_spacer.setToolTip(tr("Empty space that stretches: at the end of a row of toolbars it pushes what "
                                    "follows to the edge of the window; elsewhere it is a small gap"))
        self.b_reset = button(tr("As it was at first"), self.reset)
        self.b_new = button(tr("New toolbar…"), self.new_bar)
        self.b_delete = button(tr("Delete this toolbar"), self.delete_bar)
        middle = QVBoxLayout()
        middle.addStretch(1)
        for b in (self.b_add, self.b_remove, self.b_up, self.b_down, self.b_separator, self.b_spacer):
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
        elif name == SPACER:
            item = QListWidgetItem(tr("— spacer —"))
            item.setToolTip(tr("Empty space that stretches: at the end of a row of toolbars it pushes what follows to "
                               "the edge of the window"))
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
            if name in (SEPARATOR, SPACER) or name in self.actions_:
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
            if name in (SEPARATOR, SPACER) or name not in ids:
                ids.insert(row, name)
                row += 1
        self._show_bar()
        self.chosen.setCurrentRow(row - 1)

    def add_separator(self):
        self.add([SEPARATOR])

    def add_spacer(self):
        self.add([SPACER])

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
