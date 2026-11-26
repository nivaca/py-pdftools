"""La imagen de una página mostrada a su propio tamaño (un píxel de ella sobre un píxel de la pantalla) se
dibuja sobre píxeles enteros y sin interpolar: la página cae a menudo entre dos píxeles, y OpenGL la
muestreaba allí, de modo que el texto se veía borroso a cualquier zoom."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QStyleOptionGraphicsItem

from py_pdftools.gui.canvas import SharpPixmapItem


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class Spy(QPainter):
    """Un pintor que anota con qué transformación y qué suavizado se dibuja cada imagen, y dónde."""

    def __init__(self, device):
        super().__init__(device)
        self.drawn = []

    def drawPixmap(self, *args):
        self.drawn.append((self.deviceTransform(), self.testRenderHint(QPainter.RenderHint.SmoothPixmapTransform)))
        self.target = args[0]
        super().drawPixmap(*args)


def paint(item: SharpPixmapItem, dx: float, dy: float, scale: float = 1.0) -> list:
    target = QImage(200, 200, QImage.Format.Format_RGB32)
    target.fill(Qt.GlobalColor.white)
    painter = Spy(target)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.translate(dx, dy)
    painter.scale(scale, scale)
    item.paint(painter, QStyleOptionGraphicsItem())
    painter.end()
    item.target = getattr(painter, "target", None)
    return painter.drawn


def test_a_page_shown_at_its_size_lands_on_whole_pixels(app):
    pixmap = QPixmap(100, 100)
    pixmap.fill(Qt.GlobalColor.black)
    item = SharpPixmapItem(pixmap)
    # (63.5 y 21.6: donde caía la página a 180 %, en una ventana de 1200 píxeles)
    [(transform, smooth)] = paint(item, 63.5, 21.6)
    # (dibujada en píxeles de la pantalla: la transformación es la identidad, y el rectángulo, de píxeles enteros)
    assert transform.isIdentity() and not smooth
    assert item.target == QRect(64, 22, 100, 100)
    # Zoom and rendering are rounded to three decimals: a scale within a pixel over the picture counts as 1.
    [(transform, _)] = paint(item, 10.3, 10.3, 1.004)
    assert transform.isIdentity() and item.target == QRect(10, 10, 101, 101)


def test_tiles_side_by_side_meet(app):
    """Two tiles whose pictures are a hair smaller than their place leave no seam: both edges are rounded."""
    target = QImage(400, 50, QImage.Format.Format_RGB32)
    target.fill(Qt.GlobalColor.white)
    pixmap = QPixmap(100, 20)
    pixmap.fill(Qt.GlobalColor.black)
    painter = QPainter(target)
    painter.translate(0.4, 10)
    painter.scale(1.006, 1)  # (so 100 points become 100.6 pixels)
    for x in (0, 100, 200):
        tile = SharpPixmapItem(pixmap)
        tile.setOffset(x, 0)
        tile.paint(painter, QStyleOptionGraphicsItem())
    painter.end()
    row = [target.pixelColor(x, 15).black() for x in range(0, 305)]
    # (0.4 a 302.2: de 0 a 301, sin una columna en blanco entre las teselas)
    assert row[:302] == [255] * 302 and row[302:] == [0, 0, 0]


def test_a_stand_in_is_still_scaled_smoothly(app):
    """A rendering of another zoom (or a thumbnail), shown meanwhile, is scaled as before: Qt draws it."""
    pixmap = QPixmap(100, 100)
    pixmap.fill(Qt.GlobalColor.black)
    assert paint(SharpPixmapItem(pixmap), 63.5, 21.6, 0.5) == []
