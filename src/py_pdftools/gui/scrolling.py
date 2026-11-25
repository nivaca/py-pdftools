"""Ways of moving through the pages with the mouse and the keyboard (mixed into PageCanvas):

- Space held down turns any tool into Hand for a moment: dragging moves the pages; let go, the tool is back.
- The middle button scrolls by itself (autoscroll): pressed and let go, the pages run towards where the pointer
  goes, faster the farther it is from where it was pressed, until the next click; held down and dragged, only
  while it is held.
- (One page at a time, the wheel goes on to the next page past the end of one: see PageCanvas.wheelEvent.)
- La rueda desplaza con suavidad, y el zoom (Ctrl+rueda, Acercar, Alejar) se anima: unas pocas imágenes en
  las que la tarjeta gráfica, o el procesador, escala la imagen que ya hay; la nítida se pide al terminar.
  Configuración > Rendimiento puede apagarlo (SMOOTH)."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPointF, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QCursor, QTransform
from PySide6.QtWidgets import QApplication, QGraphicsView

DEAD_ZONE = 8  # pixels around the place pressed where the autoscroll stands still
SPEED = 1 / 6  # (pixels scrolled at each step, for each pixel away from that place)
STEP_MS = 16
SMOOTH = True  # (zooming and scrolling with the wheel animated: Settings > Performance, see performance.py)
ZOOM_MS = 160  # how long a step of the zoom takes
SCROLL_MS = 140  # how long a turn of the wheel takes to scroll
# 5 % to 10000 %, for every zoom (set_zoom too): so deep, only the part in view is drawn, in tiles (see canvas.py)
MIN_ZOOM, MAX_ZOOM = 0.05, 100


class ScrollingMixin:
    """(Mixed into PageCanvas: it uses its mode and its scroll bars.)"""

    def _init_scrolling(self):
        self._space_mode: str | None = None  # (the tool to come back to, while Space is held)
        self._auto_origin: QPointF | None = None  # (where the middle button was pressed: autoscroll on)
        self._auto_held = False  # (the middle button dragged: the autoscroll ends when it is let go)
        self._auto_timer = QTimer(self, interval=STEP_MS)
        self._auto_timer.timeout.connect(self._auto_step)
        # El zoom animado: de la escala de ahora a la buscada, alrededor de un punto de la vista que no se mueve
        self._zoom_anim = QVariantAnimation(self)
        self._zoom_anim.setDuration(ZOOM_MS)
        self._zoom_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._zoom_anim.valueChanged.connect(lambda z: self._zoom_about(float(z), self._zoom_point, self._zoom_spot))
        self._zoom_anim.finished.connect(self._zoom_done)
        self._zoom_point = QPointF()
        # (lo que está bajo ese punto, en la escena, fijado al empezar: recalcularlo en cada cuadro sumaba los
        # redondeos de las barras, unos píxeles al final)
        self._zoom_spot = QPointF()
        # (the scroll of the wheel: towards a goal that each further turn moves on)
        self._scroll_anim = QVariantAnimation(self)
        self._scroll_anim.setDuration(SCROLL_MS)
        self._scroll_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._scroll_anim.valueChanged.connect(lambda v: self.verticalScrollBar().setValue(round(float(v))))
        self.verticalScrollBar().sliderPressed.connect(self._scroll_anim.stop)

    # ----------------------------------------------------------------- zoom and wheel, animated

    def _animating(self, animation: QVariantAnimation) -> bool:
        return animation.state() == QVariantAnimation.State.Running

    def zoom_smoothly(self, factor: float, point: QPointF | None = None):
        """Zoom by FACTOR about POINT of the view (its centre, if None), which stays where it is: animated if
        the settings say so, else at once. A step asked while another runs goes on from where that one goes."""
        start = float(self._zoom_anim.endValue()) if self._animating(self._zoom_anim) else self.zoom()
        goal = max(MIN_ZOOM, min(start * factor, MAX_ZOOM))
        self._zoom_point = QPointF(self.viewport().rect().center()) if point is None else QPointF(point)
        self._zoom_spot = self.mapToScene(self._zoom_point.toPoint())
        self._zoom_anim.stop()
        if not SMOOTH or not self.isVisible():
            self._zoom_about(goal, self._zoom_point, self._zoom_spot)
            self._zoom_done()
            return
        self._zoom_anim.setStartValue(self.zoom())
        self._zoom_anim.setEndValue(goal)
        self._zoom_anim.start()

    def _zoom_about(self, z: float, point: QPointF, spot: QPointF | None = None):
        """The scale Z, with what is at POINT of the view left there (SPOT, in the scene, if known)."""
        spot = self.mapToScene(point.toPoint()) if spot is None else spot
        anchor = self.transformationAnchor()
        # (sin ancla: Qt no mueve la vista por su cuenta; se mueve abajo, para que SPOT siga bajo POINT)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setTransform(QTransform.fromScale(z, z))
        moved = self.mapFromScene(spot) - point.toPoint()
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + moved.x())
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() + moved.y())
        self.setTransformationAnchor(anchor)
        self.fit = ""
        self.render_timer.start()  # (the sharp rendering, once the zoom stands still)
        self.zoom_changed.emit(z)
        self._rezoom_icons()

    def _zoom_done(self):
        self.render_timer.start()
        self.zoom_changed.emit(self.zoom())
        self._rezoom_icons()

    def stop_animations(self):
        """End the animations at once, where they were going (before a zoom or a jump of the program)."""
        if self._animating(self._zoom_anim):
            goal = float(self._zoom_anim.endValue())
            self._zoom_anim.stop()
            self._zoom_about(goal, self._zoom_point, self._zoom_spot)
            self._zoom_done()
        if self._animating(self._scroll_anim):
            goal = round(float(self._scroll_anim.endValue()))
            self._scroll_anim.stop()
            self.verticalScrollBar().setValue(goal)

    def scroll_smoothly(self, event) -> bool:
        """A turn of the wheel (not of a touchpad, which already scrolls by pixels) scrolls with an animation,
        as far as it would at once; whether it was taken."""
        dy = event.angleDelta().y()
        if (not SMOOTH or not self.isVisible() or not dy or not event.pixelDelta().isNull()
                or event.modifiers() != Qt.KeyboardModifier.NoModifier):
            return False
        bar = self.verticalScrollBar()
        # (lo mismo que la barra haría sola: líneas de la rueda por el paso de la barra, por cada 120 de giro)
        step = bar.singleStep() * QApplication.wheelScrollLines() * -dy / 120
        start = float(self._scroll_anim.endValue()) if self._animating(self._scroll_anim) else bar.value()
        goal = max(bar.minimum(), min(start + step, bar.maximum()))
        self._scroll_anim.stop()
        if round(goal) == bar.value():
            return True
        self._scroll_anim.setStartValue(float(bar.value()))
        self._scroll_anim.setEndValue(float(goal))
        self._scroll_anim.start()
        return True

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
