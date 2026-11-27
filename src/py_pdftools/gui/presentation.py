"""Full screen, as a presentation (View > Full screen, F11): one page at a time (or the pair,
with two pages side by side), fitted on black. Arrows, Page Up/Down, Space, a click or the wheel turn the
pages; Home and End go to the first and the last; B makes the screen black, and any key brings the page
back; links are followed; Escape or a right click goes back to the window, at the page reached. A page with a display time (/Dur) turns by itself, and one with a transition (/Trans)
comes in fading. The pointer hides when it stays still."""

from __future__ import annotations

import pymupdf
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QImage, QPainter
from PySide6.QtWidgets import QWidget

from . import reading
from .canvas import page_image

HIDE_POINTER_MS = 2000
FADE_STEPS, FADE_MS = 10, 300


class Presentation(QWidget):
    """The pages of WINDOW's document, full screen, from PAGE; ended(page) when it is left."""

    ended = Signal(int)

    def __init__(self, window, page: int, pairs: bool = False):
        super().__init__(None)
        self.window = window
        self.doc = window.doc
        self.pairs = pairs and window.canvas.spread
        self.page = page
        self.image: QImage | None = None
        self.previous: QImage | None = None  # (the page before, while the new one fades in)
        self.fade = 1.0
        self.black = False  # (B: la pantalla en negro, como en Okular)
        self.boxes: list[tuple[QRectF, int, float]] = []  # (where each page is drawn, its number, its scale)
        self.setWindowTitle(window.windowTitle())
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.idle = QTimer(self, singleShot=True, interval=HIDE_POINTER_MS)
        self.idle.timeout.connect(lambda: self.setCursor(QCursor(Qt.CursorShape.BlankCursor)))
        self.timed = QTimer(self, singleShot=True)  # (a page with a display time)
        self.timed.timeout.connect(lambda: self.turn(1))
        self.fader = QTimer(self, interval=FADE_MS // FADE_STEPS)
        self.fader.timeout.connect(self._fade_step)

    def start(self):
        from .awake import Awake

        # (la pantalla despierta mientras dura: véase awake.py)
        self.awake = Awake()
        self.awake.start()
        self.showFullScreen()
        self.show_page(self.page, fade=False)
        self.idle.start()

    # ----------------------------------------------------------------- the pages

    def row(self, page: int) -> list[int]:
        return self.window.canvas.row_of(page) if self.pairs else [page]

    def show_page(self, page: int, fade: bool = True):
        page = max(0, min(page, self.doc.page_count - 1))
        self.black = False
        self.page = self.row(page)[0]
        old = self.image
        self.image = self._draw()
        self.previous = old if fade and old is not None and self._transition(self.page) else None
        self.fade = 0.0 if self.previous is not None else 1.0
        if self.previous is not None:
            self.fader.start()
        self.update()
        duration = self._duration(self.page)
        if duration is not None and self.page < self.doc.page_count - 1:
            self.timed.start(int(duration * 1000))
        else:
            self.timed.stop()

    def turn(self, step: int):
        rows = self.window.canvas.rows() if self.pairs else [[n] for n in range(self.doc.page_count)]
        i = next((k for k, r in enumerate(rows) if self.page in r), 0)
        target = rows[max(0, min(i + step, len(rows) - 1))][0]
        if target != self.page:
            self.show_page(target)

    def _draw(self) -> QImage:
        """The page (or the pair) fitted in the screen, on black."""
        size = self.size()
        image = QImage(size, QImage.Format.Format_RGB32)
        image.fill(QColor("black"))
        numbers = self.row(self.page)
        rects = [self.doc[n].rect for n in numbers]
        gap = 8
        total_w = sum(r.width for r in rects) + gap * (len(rects) - 1)
        total_h = max(r.height for r in rects)
        scale = min(size.width() / total_w, size.height() / total_h) * self.devicePixelRatioF()
        p = QPainter(image)
        x = (size.width() - total_w * scale / self.devicePixelRatioF()) / 2
        self.boxes = []
        for n, r in zip(numbers, rects):
            picture = page_image(self.doc[n], scale, tint=reading.TINT, screen=True, backend=self.window.canvas.backend)
            picture.setDevicePixelRatio(self.devicePixelRatioF())
            w, h = r.width * scale / self.devicePixelRatioF(), r.height * scale / self.devicePixelRatioF()
            box = QRectF(x, (size.height() - h) / 2, w, h)
            p.drawImage(box, picture)
            self.boxes.append((box, n, w / r.width))
            x += w + gap
        p.end()
        return image

    def _key(self, page: int, name: str):
        try:
            return self.doc.xref_get_key(self.doc[page].xref, name)
        except (RuntimeError, ValueError):
            return ("null", "null")

    def _duration(self, page: int) -> float | None:
        kind, value = self._key(page, "Dur")
        try:
            return float(value) if kind in ("int", "real") else None
        except ValueError:
            return None

    def _transition(self, page: int) -> bool:
        return self._key(page, "Trans")[0] != "null"

    def _fade_step(self):
        self.fade = min(1.0, self.fade + 1 / FADE_STEPS)
        if self.fade >= 1.0:
            self.fader.stop()
            self.previous = None
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("black"))
        if self.black:
            p.end()
            return
        if self.previous is not None:
            p.drawImage(0, 0, self.previous)
            p.setOpacity(self.fade)
        if self.image is not None:
            p.drawImage(0, 0, self.image)
        p.end()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.doc is not None and self.isVisible():
            self.image = self._draw()
            self.update()

    # ----------------------------------------------------------------- input

    def keyPressEvent(self, event):
        key = event.key()
        if self.black and key not in (Qt.Key.Key_Escape, Qt.Key.Key_F11):
            # (with the screen black, any key shows the page again, and only that)
            self.black = False
            self.update()
        elif key == Qt.Key.Key_B:
            self.black = True
            self.update()
        elif key in (Qt.Key.Key_Escape, Qt.Key.Key_F11):
            self.close()
        elif key in (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_PageDown, Qt.Key.Key_Space, Qt.Key.Key_Return,
                     Qt.Key.Key_Enter, Qt.Key.Key_N):
            self.turn(1)
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_PageUp, Qt.Key.Key_Backspace, Qt.Key.Key_P):
            self.turn(-1)
        elif key == Qt.Key.Key_Home:
            self.show_page(0)
        elif key == Qt.Key.Key_End:
            self.show_page(self.doc.page_count - 1)
        else:
            super().keyPressEvent(event)

    def _link_at(self, pos: QPointF) -> tuple[int, dict] | None:
        for box, n, scale in self.boxes:
            if box.contains(pos):
                point = QPointF((pos.x() - box.x()) / scale, (pos.y() - box.y()) / scale)
                return n, self.window.canvas.link_at(n, point) if self.window.canvas.doc is self.doc else None
        return None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.close()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        found = self._link_at(event.position())
        if found is not None and found[1] is not None:
            n, link = found
            if link.get("kind") == pymupdf.LINK_GOTO:
                self.show_page(link.get("page", 0))
            else:
                self.window.follow_link(n, link)
            return
        self.turn(1)

    def mouseMoveEvent(self, event):
        found = self._link_at(event.position())
        over = found is not None and found[1] is not None
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor if over else Qt.CursorShape.ArrowCursor))
        self.idle.start()

    def wheelEvent(self, event):
        self.turn(-1 if event.angleDelta().y() > 0 else 1)

    def closeEvent(self, event):
        self.timed.stop()
        self.fader.stop()
        if getattr(self, "awake", None) is not None:  # (the screen left to the system again)
            self.awake.stop()
        self.ended.emit(self.page)
        super().closeEvent(event)
