"""Configuración > General > Revisar la configuración: las revisiones de core/health.py, y además las de la
ventana (dos acciones con el mismo atajo, que Qt deja sin efecto: ninguna de las dos responde), en una
lista con el estado de cada una, lo hallado y qué hacer; el informe se puede copiar como texto."""

from __future__ import annotations

from collections import defaultdict

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QLabel, QMenu, QMenuBar, QToolBar, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from ..core import health
from ..core.health import Check
from ..core.interface import ntr, tr

ICONS = {health.OK: "dialog-ok", health.INFO: "dialog-information", health.WARNING: "dialog-warning",
         health.ERROR: "dialog-error"}


def _reachable(action: QAction, seen=None) -> bool:
    """Whether the window can run ACTION by its shortcut now, as Qt decides it: enabled, and in a menu
    that is shown in the menu bar (or in a menu so shown), in a toolbar that shows, or in the window."""
    if not action.isEnabled():
        return False
    seen = set() if seen is None else seen
    if id(action) in seen:
        return False
    seen.add(id(action))
    for owner in action.associatedObjects():
        if isinstance(owner, QMenu):
            # Un menú cuenta si su propia acción está visible y se llega a ella (desde la barra de menús)
            menu_action = owner.menuAction()
            if menu_action.isVisible() and (not menu_action.associatedObjects()
                                            or any(isinstance(o, QMenuBar) for o in menu_action.associatedObjects())
                                            or _reachable(menu_action, seen)):
                return True
        elif isinstance(owner, QToolBar):
            # A toolbar hidden (or of another mode) gives no shortcut to its actions
            if owner.isVisible():
                return True
        elif isinstance(owner, QWidget) and owner.isVisible():
            return True
    return False


def _keys(action: QAction) -> list[str]:
    return [k.toString() for k in action.shortcuts() if not k.isEmpty()]


def shortcuts(window) -> list[Check]:
    """The shortcuts of the window: two actions working now with the same one (Qt then runs neither), and
    a shortcut changed in Settings that is also the fixed one of another action."""
    from ..annotate import settings

    title = tr("Keyboard shortcuts")
    # (those of the mode Impose too, whose workspace is otherwise made only when the mode is first entered)
    getattr(window, "workspace", None)
    # (only the shortcuts of the window: those of a widget, such as Delete in the bookmarks, can't clash)
    actions = [a for a in window.findChildren(QAction)
               if a.shortcutContext() in (Qt.ShortcutContext.WindowShortcut, Qt.ShortcutContext.ApplicationShortcut)]
    live: dict[str, set[str]] = defaultdict(set)
    for action in actions:
        if _reachable(action):
            for key in _keys(action):
                live[key].add(action.text().replace("&", ""))
    out = []
    clashes = [f"{key} ({', '.join(sorted(names))})" for key, names in sorted(live.items()) if len(names) > 1]
    if clashes:
        out.append(Check(health.WARNING, title, tr("The same shortcut for several actions, so none of them "
                                                   "responds to it: {keys}", keys="; ".join(clashes)),
                         tr("Give one of them another shortcut, in Settings > Shortcuts")))
    # Los atajos que el usuario cambió: ¿alguno lo tiene también otra acción de la ventana (en cualquier modo)?
    prefs = settings.load()
    changed = sorted({key for action, key in prefs.shortcuts if key and key != settings.SHORTCUTS.get(action)})
    taken = []
    for key in changed:
        names = sorted({a.text().replace("&", "") for a in actions if key in _keys(a)})
        if len(names) > 1:
            taken.append(f"{key} ({', '.join(names)})")
    if taken:
        out.append(Check(health.WARNING, tr("Shortcuts changed in Settings"),
                         tr("Also the shortcut of another action: {keys}", keys="; ".join(taken)),
                         tr("Give one of them another shortcut, in Settings > Shortcuts")))
    if not out:
        out.append(Check(health.OK, title, tr("No shortcut is used twice")))
    return out


def graphics(window) -> Check | None:
    """With the pages drawn by the graphics card (Settings > Performance): whether OpenGL gave a surface."""
    from ..core import config

    canvas = getattr(window, "canvas", None)
    if canvas is None or not config.get("gpu"):
        return None
    from . import canvas as drawing

    title = tr("Graphics card (OpenGL)")
    if not getattr(canvas, "gpu", False):
        if drawing.GPU_UNAVAILABLE:
            return Check(health.WARNING, title, tr("Chosen in Settings, but not used: {why}",
                                                   why=drawing.GPU_UNAVAILABLE),
                         tr("The pages are drawn as usual; turn it off in Settings > Performance"))
        return Check(health.INFO, title, tr("Chosen in Settings; it is used from the next start"))
    context = canvas.viewport().context() if hasattr(canvas.viewport(), "context") else None
    if context is None and not canvas.isVisible():  # (its surface gets a context only once drawn)
        return Check(health.OK, title, tr("In use"))
    if context is None or not context.isValid():
        return Check(health.WARNING, title, tr("The graphics card gave no OpenGL surface: the pages may not show"),
                     tr("Turn it off in Settings > Performance"))
    fmt = context.format()
    return Check(health.OK, title, f"OpenGL {fmt.majorVersion()}.{fmt.minorVersion()}")


def run(window=None) -> list[Check]:
    checks = health.run()
    if window is not None and hasattr(window, "modes"):
        checks += shortcuts(window)
        gpu = graphics(window)
        if gpu is not None:
            checks.append(gpu)
    return checks


class HealthDialog(QDialog):
    def __init__(self, window=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Check the configuration"))
        self.window_ = window
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.list = QTreeWidget()
        self.list.setColumnCount(2)
        self.list.setHeaderLabels([tr("What"), tr("Found")])
        self.list.setRootIsDecorated(False)
        self.list.setWordWrap(True)
        self.list.setColumnWidth(0, 230)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        again = buttons.addButton(tr("Check again"), QDialogButtonBox.ButtonRole.ActionRole)
        copy = buttons.addButton(tr("Copy the report"), QDialogButtonBox.ButtonRole.ActionRole)
        copy.setToolTip(tr("As plain text, to paste into a message asking for help"))
        again.clicked.connect(self.refresh)
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(health.report(self.checks)))
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.summary)
        lay.addWidget(self.list, 1)
        lay.addWidget(buttons)
        self.resize(760, 520)
        self.checks: list[Check] = []
        self.refresh()

    def refresh(self):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.checks = run(self.window_)
        finally:
            QApplication.restoreOverrideCursor()
        self.list.clear()
        for c in self.checks:
            text = c.detail + (f"\n→ {c.fix}" if c.fix else "")
            item = QTreeWidgetItem([c.title, text])
            item.setIcon(0, QIcon.fromTheme(ICONS[c.status]))
            item.setToolTip(0, tr(health.STATUS[c.status]))
            item.setToolTip(1, text)
            self.list.addTopLevelItem(item)
        problems = sum(c.status in (health.WARNING, health.ERROR) for c in self.checks)
        # Una frase para todo: lo primero que se lee al abrir la revisión.
        self.summary.setText(ntr("{count} thing to look at, marked below.", "{count} things to look at, marked below.",
                                 problems) if problems else tr("Everything is in order."))
