"""Ways of moving through the pages with the mouse and the keyboard (mixed into PageCanvas):

- Space held down turns any tool into Hand for a moment: dragging moves the pages; let go, the tool is back.
- The middle button scrolls by itself (autoscroll): pressed and let go, the pages run towards where the pointer
  goes, faster the farther it is from where it was pressed, until the next click; held down and dragged, only
  while it is held.
- (One page at a time, the wheel goes on to the next page past the end of one: see PageCanvas.wheelEvent.)"""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QGraphicsView

DEAD_ZONE = 8  # pixels around the place pressed where the autoscroll stands still
SPEED = 1 / 6  # (pixels scrolled at each step, for each pixel away from that place)
STEP_MS = 16


class ScrollingMixin:
    """(Mixed into PageCanvas: it uses its mode and its scroll bars.)"""

    def _init_scrolling(self):
        self._space_mode: str | None = None  # (the tool to come back to, while Space is held)
        self._auto_origin: QPointF | None = None  # (where the middle button was pressed: autoscroll on)
        self._auto_held = False  # (the middle button dragged: the autoscroll ends when it is let go)
        self._auto_timer = QTimer(self, interval=STEP_MS)
        self._auto_timer.timeout.connect(self._auto_step)

    # ----------------------------------------------------------------- Space: Hand for a moment

    def space_pressed(self, event) -> bool:
        if event.key() != Qt.Key.Key_Space or event.modifiers() != Qt.KeyboardModifier.NoModifier:
            return False
        if event.isAutoRepeat():
            return self._space_mode is not None
        if self.doc is None or self._drag is not None or self.mode == "hand":
            return False
        self._space_mode = self.mode
        self.mode = "hand"
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.viewport().setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        return True

    def space_released(self, event) -> bool:
        if event.key() != Qt.Key.Key_Space or self._space_mode is None:
            return False
        if event.isAutoRepeat():
            return True
        self.mode, self._space_mode = self._space_mode, None
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.viewport().unsetCursor()
        return True

    # ----------------------------------------------------------------- the middle button: autoscroll

    def autoscroll_press(self, event) -> bool:
        """A press, while the autoscroll is on, ends it; one of the middle button starts it."""
        if self._auto_origin is not None:
            self.stop_autoscroll()
            return True
        if event.button() != Qt.MouseButton.MiddleButton or self.doc is None:
            return False
        self._auto_origin = event.position()
        self._auto_pointer = event.position()
        self._auto_held = False
        self.viewport().setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
        self._auto_timer.start()
        return True

    def autoscroll_move(self, event) -> bool:
        if self._auto_origin is None:
            return False
        self._auto_pointer = event.position()
        if event.buttons() & Qt.MouseButton.MiddleButton and \
                (event.position() - self._auto_origin).manhattanLength() > DEAD_ZONE:
            self._auto_held = True
        return True

    def autoscroll_release(self, event) -> bool:
        if self._auto_origin is None:
            return False
        if event.button() == Qt.MouseButton.MiddleButton and self._auto_held:
            self.stop_autoscroll()
        return True

    def stop_autoscroll(self):
        self._auto_timer.stop()
        self._auto_origin = None
        self.viewport().unsetCursor()

    def _auto_step(self):
        if self._auto_origin is None:
            return
        d = self._auto_pointer - self._auto_origin
        for bar, offset in ((self.horizontalScrollBar(), d.x()), (self.verticalScrollBar(), d.y())):
            if abs(offset) > DEAD_ZONE:
                move = (abs(offset) - DEAD_ZONE) * SPEED
                bar.setValue(bar.value() + round(move if offset > 0 else -move))
