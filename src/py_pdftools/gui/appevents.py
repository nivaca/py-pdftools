"""Lo que macOS dice al programa que corre (en otros sistemas no llega): los documentos abiertos desde el
Finder, o arrastrados al icono del Dock, no llegan como argumentos, sino como un evento FileOpen al programa
que ya corre (macOS no arranca otro); y un clic en el icono del Dock, sin ninguna ventana a la vista (en
segundo plano), pide una ventana, como en los demás programas del sistema.

Se instala solo en macOS (ver gui/__init__.py): el primer filtro de eventos en Python cuesta unos 9 ms al
arrancar.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QEvent, QObject

# Started with the session (--background): an activation that comes this soon is the start's own, not a click
# on the Dock, and opens no window.
QUIET_S = 2.0


class AppEvents(QObject):
    """The filter of the application's events. OPEN(path or None) opens a window (with the document at
    path); SHOWN() says whether a window of the program is on the screen."""

    def __init__(self, open_window, shown, hidden: bool = False, parent=None):
        super().__init__(parent)
        self.open_window, self.shown = open_window, shown
        self.quiet_until = time.monotonic() + QUIET_S if hidden else 0.0

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind == QEvent.Type.FileOpen:
            path = event.file() or event.url().toLocalFile()
            if path:
                self.open_window(path)
                return True
        elif kind == QEvent.Type.ApplicationActivate and time.monotonic() >= self.quiet_until \
                and not self.shown():
            self.open_window(None)  # (el clic en el Dock, con el programa en segundo plano)
        return False


def install(app, open_window, shown, hidden: bool = False) -> AppEvents:
    """Filter APP's events with AppEvents (kept by the application)."""
    events = AppEvents(open_window, shown, hidden, parent=app)
    app.installEventFilter(events)
    return events
