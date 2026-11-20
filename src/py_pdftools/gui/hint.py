"""The hint of a mode (what to do in it), shown for a while over the bottom of the pages when the mode is
chosen, and again with Help > Tips for this mode (F1): not in a line of its own below them, where it took
two or three lines from the pages all the time."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPropertyAnimation, Qt, QTimer
from PySide6.QtWidgets import QAbstractScrollArea, QGraphicsOpacityEffect, QLabel, QWidget

SECONDS = 8  # the time a hint stays, before it fades
FADE_MS = 600


class HintOverlay(QLabel):
    """A hint over the bottom of HOST (the pages): the mouse goes through it, and a click on HOST takes
    it away at once."""

    def __init__(self, host: QWidget):
        super().__init__(host)
        self.host = host
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # (clicks go to the pages under it)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        # Oscuro y algo transparente: se lee sobre una página blanca y sobre el fondo, con tema claro u oscuro.
        self.setStyleSheet("QLabel { background: rgba(32, 32, 32, 220); color: white; border-radius: 8px;"
                           " padding: 8px 14px; }")
        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self.fade = QPropertyAnimation(self.effect, b"opacity", self)
        self.fade.setDuration(FADE_MS)
        self.fade.setStartValue(1.0)
        self.fade.setEndValue(0.0)
        self.fade.finished.connect(self.hide)
        self.timer = QTimer(self, singleShot=True, interval=SECONDS * 1000)
        self.timer.timeout.connect(self.fade.start)
        host.installEventFilter(self)
        if isinstance(host, QAbstractScrollArea):  # (the clicks on the pages go to its viewport)
            host.viewport().installEventFilter(self)
        self.hide()

    def show_text(self, text: str):
        """Show TEXT for SECONDS, then fade it ('' takes the hint away)."""
        self.setText(text)
        if not text:
            self.dismiss()
            return
        self.fade.stop()
        self.effect.setOpacity(1.0)
        self._place()
        self.show()
        self.raise_()
        self.timer.start()

    def dismiss(self):
        self.timer.stop()
        self.fade.stop()
        self.hide()

    def _place(self):
        """Centred near the bottom of the host, at most 640 pixels wide."""
        width = max(min(self.host.width() - 48, 640), 160)
        self.setFixedWidth(width)
        self.setFixedHeight(self.heightForWidth(width))
        # (above the horizontal scroll bar, if the host has one)
        self.move((self.host.width() - width) // 2, max(self.host.height() - self.height() - 28, 0))

    def eventFilter(self, obj, event):
        if self.isVisible():
            if event.type() == QEvent.Type.Resize and obj is self.host:
                self._place()
            elif event.type() == QEvent.Type.MouseButtonPress:
                self.dismiss()
        return False
