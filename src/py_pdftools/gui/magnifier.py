"""La lupa (herramienta Lupa, Mayús+Z, como la de Okular): mientras se mantiene pulsado el botón del ratón sobre
una página, un círculo junto al puntero muestra esa parte de la página tres veces más cerca. No es una imagen
ampliada de lo que ya se ve: la página se dibuja de nuevo, solo ese trozo, a la escala de la lupa, así que el
texto se lee nítido. La vista y el documento no cambian."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap, QTransform
from PySide6.QtWidgets import QLabel, QWidget

from . import reading

SIZE = 240  # (el diámetro de la lupa, en píxeles de pantalla)
POWER = 3.0  # (cuántas veces más cerca que la vista)
MOST = 40.0  # (la escala más alta a la que se dibuja: 4000 %)


class Lens(QLabel):
    """The round lens, over the view of the pages (a child of its viewport)."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setFixedSize(SIZE, SIZE)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.hide()

    def show_at(self, pos: QPointF, image: QImage | None):
        """The lens centred on POS (in its parent's coordinates), showing IMAGE (None: grey)."""
        ratio = self.devicePixelRatioF()
        pixmap = QPixmap(round(SIZE * ratio), round(SIZE * ratio))
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.GlobalColor.transparent)
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        circle = QPainterPath()
        circle.addEllipse(QRectF(1, 1, SIZE - 2, SIZE - 2))
        p.setClipPath(circle)
        p.fillRect(QRectF(0, 0, SIZE, SIZE), QColor("#808080"))
        if image is not None:
            # (la imagen se centra: cerca del borde de la página es más pequeña que la lupa)
            w, h = image.width() / ratio, image.height() / ratio
            p.drawImage(QRectF((SIZE - w) / 2, (SIZE - h) / 2, w, h), image)
        p.setClipping(False)
        pen = QPen(QColor("#404040"), 2)
        p.setPen(pen)
        p.drawEllipse(QRectF(1, 1, SIZE - 2, SIZE - 2))
        p.end()
        self.setPixmap(pixmap)
        self.move(round(pos.x() - SIZE / 2), round(pos.y() - SIZE / 2))
        self.show()
        self.raise_()


def lens_image(canvas, page_item, point: QPointF) -> QImage | None:
    """The part of the page of PAGE_ITEM around POINT (in points of the page), as the lens shows it: POWER times
    nearer than CANVAS shows it, turned as the view turns the pages."""
    from .canvas import page_image

    doc = canvas.doc
    if doc is None:
        return None
    ratio = canvas.viewport().devicePixelRatioF()
    scale = min(canvas.zoom() * POWER, MOST)
    half = SIZE / 2 / scale  # (medio diámetro de la lupa, en puntos de la página)
    rect = doc[page_item.number].rect
    clip = (max(point.x() - half, 0.0), max(point.y() - half, 0.0),
            min(point.x() + half, rect.width), min(point.y() + half, rect.height))
    if clip[2] <= clip[0] or clip[3] <= clip[1]:
        return None
    try:
        image = page_image(doc[page_item.number], scale * ratio, clip, reading.TINT, backend=canvas.backend)
    except (RuntimeError, ValueError):
        return None
    if canvas.turn:
        image = image.transformed(QTransform().rotate(canvas.turn))
    # Fuera de la página la lupa es gris: la imagen se desplaza para que POINT quede en su centro.
    dx = ((point.x() - half) - clip[0]) * scale * ratio
    dy = ((point.y() - half) - clip[1]) * scale * ratio
    if not canvas.turn and (dx or dy):
        full = QImage(round(SIZE * ratio), round(SIZE * ratio), QImage.Format.Format_RGB32)
        full.fill(QColor("#808080"))
        p = QPainter(full)
        p.drawImage(QPointF(-dx, -dy), image)
        p.end()
        image = full
    return image
