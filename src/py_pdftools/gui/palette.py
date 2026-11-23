"""La paleta de órdenes (Ayuda > Buscar una orden, Ctrl+Alt+I, como la barra de órdenes de KDE): una casilla
sobre la ventana que busca entre todas las acciones de los menús por su nombre, y la que se elige se ejecuta.
Cada una se muestra con su camino en los menús (Ver › Zoom › Ajustar al ancho) y su tecla; se encuentra por
cualquier palabra de ese camino, sin distinguir mayúsculas ni acentos, en el orden en que se escriban o no.
Solo aparecen las que se pueden usar en ese momento: las del modo elegido y activas."""

from __future__ import annotations

import unicodedata

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QAction, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QDialog, QLineEdit, QListWidget, QListWidgetItem, QMenu, QToolBar, QVBoxLayout, QWidgetAction,
)

from ..core.interface import tr

ACTION = Qt.ItemDataRole.UserRole
SHOWN = 400  # (as many as the list shows: more would only slow it)


def _plain(text: str) -> str:
    """TEXT for comparing: no accents, no capitals, no '&' of the menus' keys."""
    text = unicodedata.normalize("NFD", text.replace("&&", "\0").replace("&", "").replace("\0", "&"))
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


def _label(act: QAction) -> str:
    return act.text().replace("&&", "\0").replace("&", "").replace("\0", "&")


def commands(window) -> list[tuple[str, QAction]]:
    """Every action of WINDOW's menus that can be used now, with its path in them ('View › Zoom › Fit width');
    then those only on a toolbar shown (the modes, some tools), with the toolbar's name."""
    out, seen = [], set()

    def walk(menu: QMenu, path: list[str]):
        # (un menú que se rellena al abrirse se rellena ahora, para que sus acciones estén)
        menu.aboutToShow.emit()
        for act in menu.actions():
            if act.isSeparator() or not act.isVisible() or id(act) in seen:
                continue
            if act.menu() is not None:
                if act.isEnabled():
                    walk(act.menu(), [*path, _label(act)])
                continue
            if act.isEnabled() and act.text().strip():
                seen.add(id(act))
                out.append((" › ".join([*path, _label(act)]), act))

    for act in window.menuBar().actions():
        if act.menu() is not None and act.isVisible():
            walk(act.menu(), [_label(act)])
    for bar in window.findChildren(QToolBar):
        if bar.parent() is not window or not bar.isVisible():
            continue
        for act in bar.actions():
            # (no las casillas, como la de la página: no son órdenes)
            if isinstance(act, QWidgetAction) or act.isSeparator() or id(act) in seen:
                continue
            if act.isVisible() and act.isEnabled() and act.text().strip() and act.menu() is None:
                seen.add(id(act))
                out.append((bar.windowTitle().replace("&", "") + " › " + _label(act), act))
    return out


def matching(found: list[tuple[str, QAction]], query: str) -> list[tuple[str, QAction]]:
    """Those of FOUND whose path has every word of QUERY (in any order); those whose name begins with the
    first word go first."""
    words = _plain(query).split()
    if not words:
        return list(found)
    hits = [(path, act) for path, act in found if all(w in _plain(path) for w in words)]
    # (primero las que tienen la palabra al principio del nombre de la acción, no solo en su camino)
    return sorted(hits, key=lambda h: not _plain(h[0].rsplit(" › ", 1)[-1]).startswith(words[0]))


class Palette(QDialog):
    """The box and the list of the commands (see the module's text)."""

    def __init__(self, window):
        super().__init__(window, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.window = window
        self.found = commands(window)
        self.chosen: QAction | None = None
        self.box = QLineEdit()
        self.box.setPlaceholderText(tr("Find a command…"))
        self.box.setAccessibleName(tr("Find a command"))
        self.box.textChanged.connect(self.fill)
        self.box.installEventFilter(self)
        self.list = QListWidget()
        self.list.setIconSize(QSize(20, 20))
        # (las órdenes sin icono, con uno vacío: así todos los nombres empiezan en la misma columna)
        blank = QPixmap(20, 20)
        blank.fill(Qt.GlobalColor.transparent)
        self.blank = QIcon(blank)
        self.list.setAccessibleName(tr("Commands"))
        self.list.itemActivated.connect(lambda item: self.run(item))
        self.list.itemClicked.connect(lambda item: self.run(item))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addWidget(self.box)
        lay.addWidget(self.list)
        self.fill("")

    def fill(self, query: str):
        self.list.clear()
        for path, act in matching(self.found, query)[:SHOWN]:
            keys = act.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
            text = f"{path}    ({keys})" if keys else path
            if act.isCheckable():
                text = ("☑ " if act.isChecked() else "☐ ") + text
            item = QListWidgetItem(act.icon() if not act.icon().isNull() else self.blank, text)
            item.setData(ACTION, act)
            item.setToolTip(act.toolTip() if act.toolTip() != _label(act) else "")
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)

    def eventFilter(self, obj, event) -> bool:
        # Las flechas, Re Pág y Av Pág mueven la elección de la lista sin sacar el cursor de la casilla.
        if obj is self.box and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up, Qt.Key.Key_PageDown, Qt.Key.Key_PageUp):
                self.list.event(event)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.run(self.list.currentItem())
                return True
        return super().eventFilter(obj, event)

    def run(self, item: QListWidgetItem | None):
        """The command of ITEM, after the palette has closed (so that a dialog it opens is not under it)."""
        if item is None:
            return
        self.chosen = item.data(ACTION)
        self.accept()

    def place(self):
        """Over the top of WINDOW, in its middle, a third of its width (at least 480 pixels)."""
        w = self.window
        width = max(480, w.width() // 3)
        top = w.mapToGlobal(w.rect().topLeft())
        self.setGeometry(top.x() + (w.width() - width) // 2, top.y() + 60, width, min(420, w.height() - 80))


def open_palette(window) -> QAction | None:
    """The palette, over WINDOW; the action chosen in it, run (and returned), or None."""
    palette = Palette(window)
    palette.place()
    palette.box.setFocus()
    if palette.exec() and palette.chosen is not None:
        palette.chosen.trigger()
        return palette.chosen
    return None
