"""The mouse on the pages of the window, for the tests of its modes."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication


def mouse(w, kind, point, button=Qt.MouseButton.LeftButton, mods=Qt.KeyboardModifier.NoModifier, page=None):
    """A mouse event at POINT (in points) of PAGE (the page in view, if None)."""
    c = w.canvas
    item = c.pages[w.page if page is None else page]
    pos = c.mapFromScene(item.mapToScene(QPointF(*point)))
    handler = {QEvent.Type.MouseButtonPress: c.mousePressEvent, QEvent.Type.MouseMove: c.mouseMoveEvent,
               QEvent.Type.MouseButtonRelease: c.mouseReleaseEvent,
               QEvent.Type.MouseButtonDblClick: c.mouseDoubleClickEvent}[kind]
    buttons = Qt.MouseButton.NoButton if kind == QEvent.Type.MouseMove else button
    handler(QMouseEvent(kind, QPointF(pos), QPointF(c.viewport().mapToGlobal(pos)), buttons, button, mods))


def drag(w, *points, mods=Qt.KeyboardModifier.NoModifier, page=None):
    """Drag with the mouse on the page (PAGE, or the one in view), through POINTS (in points)."""
    mouse(w, QEvent.Type.MouseButtonPress, points[0], mods=mods, page=page)
    for p in points[1:]:
        mouse(w, QEvent.Type.MouseMove, p, mods=mods, page=page)
    mouse(w, QEvent.Type.MouseButtonRelease, points[-1], mods=mods, page=page)
    QApplication.processEvents()


def double_click(w, point, page=None):
    mouse(w, QEvent.Type.MouseButtonPress, point, page=page)
    mouse(w, QEvent.Type.MouseButtonRelease, point, page=page)
    mouse(w, QEvent.Type.MouseButtonDblClick, point, page=page)
    mouse(w, QEvent.Type.MouseButtonRelease, point, page=page)
    QApplication.processEvents()


def close(a, b, tolerance=2.0):
    return all(abs(x - y) <= tolerance for x, y in zip(a, b, strict=True))
