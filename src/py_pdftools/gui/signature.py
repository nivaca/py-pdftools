"""A signature drawn by hand, once (with a tablet's pen or the mouse), kept, and put on documents as
a drawing (see the Signature tool of the window)."""

from __future__ import annotations

import json

from PySide6.QtCore import QPointF, QSettings, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPushButton, QVBoxLayout, QWidget

from ..annotate.annots import smooth_segments
from ..core.interface import tr

Strokes = list[list[tuple[float, float]]]
KEY = "signature"  # (in the window's QSettings: the strokes, as JSON, in a box of width 1)


def load(settings: QSettings) -> Strokes:
    try:
        strokes = json.loads(settings.value(KEY, "") or "[]")
        return [[(float(x), float(y)) for x, y in stroke] for stroke in strokes if stroke]
    except (TypeError, ValueError):
        return []


def store(settings: QSettings, strokes: Strokes) -> None:
    settings.setValue(KEY, json.dumps(normalized(strokes)))


def normalized(strokes: Strokes) -> Strokes:
    """STROKES moved to (0, 0) and scaled to a width of 1 (their height in proportion)."""
    points = [p for stroke in strokes for p in stroke]
    if not points:
        return []
    x0, y0 = min(p[0] for p in points), min(p[1] for p in points)
    width = max(max(p[0] for p in points) - x0, max(p[1] for p in points) - y0, 1e-6)
    return [[(round((x - x0) / width, 5), round((y - y0) / width, 5)) for x, y in stroke] for stroke in strokes]


class Pad(QWidget):
    """Where the signature is drawn."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.strokes: Strokes = []
        self.setMinimumSize(480, 180)
        self.setAttribute(Qt.WidgetAttribute.WA_StaticContents)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def mousePressEvent(self, event):
        p = event.position()
        self.strokes.append([(p.x(), p.y())])
        self.update()

    def mouseMoveEvent(self, event):
        if self.strokes and event.buttons() & Qt.MouseButton.LeftButton:
            p = event.position()
            last = self.strokes[-1][-1]
            if abs(p.x() - last[0]) + abs(p.y() - last[1]) >= 1.5:
                self.strokes[-1].append((p.x(), p.y()))
                self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), Qt.GlobalColor.white)
        p.setPen(QPen(Qt.GlobalColor.lightGray, 1, Qt.PenStyle.DashLine))
        base = self.height() * 0.75
        p.drawLine(QPointF(20, base), QPointF(self.width() - 20, base))
        pen = QPen(Qt.GlobalColor.darkBlue, 2.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        for stroke in self.strokes:
            if len(stroke) < 3:
                p.drawPoint(QPointF(*stroke[0]))
                continue
            path = QPainterPath(QPointF(*stroke[0]))
            for c1, c2, end in smooth_segments(stroke):
                path.cubicTo(QPointF(*c1), QPointF(*c2), QPointF(*end))
            p.drawPath(path)

    def clear(self):
        self.strokes = []
        self.update()


class SignatureDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("My signature"))
        lay = QVBoxLayout(self)
        note = QLabel(tr("Sign above the line, with the pen or the mouse. It is kept on this computer only, in "
                         "the settings of py-pdftools, and put on documents with the Signature tool."))
        note.setWordWrap(True)
        lay.addWidget(note)
        self.pad = Pad(self)
        lay.addWidget(self.pad, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        clear = QPushButton(tr("Clear"))
        clear.clicked.connect(self.pad.clear)
        buttons.addButton(clear, QDialogButtonBox.ButtonRole.ResetRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def strokes(self) -> Strokes:
        return [s for s in self.pad.strokes if s]
