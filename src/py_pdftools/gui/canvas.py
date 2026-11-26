"""The pages being annotated, one under the other (or one at a time), and their
annotations: made with the tool chosen (dragging over text, dragging a box, a
line or a stroke, clicking the points of a polygon, or clicking), moved by
dragging them (or with the arrow keys), resized by dragging their edges and
corners, and reshaped by dragging their points; selected by clicking them or
by dragging a frame around them; erased with the eraser; and the text of a
text box or a note written where it is.

Each page is an item of the scene (PageItem), in points; the annotations of a
page are its children, so they are drawn and handled in the page's own
points, as the page is shown. Only the pages in view are rendered."""

from __future__ import annotations

import bisect
import dataclasses
import math
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable

import pymupdf
from PySide6.QtCore import QEvent, QPointF, QRect, QRectF, QSizeF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush, QColor, QCursor, QImage, QKeySequence, QPainter, QPainterPath, QPen, QPixmap, QPointingDevice,
    QTextOption, QTransform,
)
from PySide6.QtWidgets import (
    QToolTip,
    QApplication, QColorDialog, QGraphicsItem, QGraphicsPathItem, QGraphicsPixmapItem, QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem, QGraphicsView, QMenu,
)

from ..annotate import annots
from . import reading
from .links import FOLLOWED_BY, LinksMixin
from .scrolling import MAX_ZOOM, MIN_ZOOM, ScrollingMixin
from .textselect import TEXT_SELECT, TextSelectMixin
from ..annotate.annots import (
    CARET_SIZE, DRAWN, MARKUP, NOTE_SIZE, RESIZABLE, TEXTUAL, VERTICES, Annotation, Rect, nearest_word, text_rects,
)
from ..core.interface import tr
from .paint import _font, paint, qrect

GAP = 12  # points between the pages, and around them
MIN_SIZE = 3.0  # points: a smaller drag is a click
GRIP = 6  # pixels from an edge, or from a point of a line, where dragging resizes or reshapes
ERASER = 7  # pixels: the radius of the eraser
MAX_PIXELS = 40_000_000  # the largest rendering of a page
# Deep zoom, in tiles: a page whose rendering would be longer than TILE_ABOVE pixels is drawn whole at most
# BACKDROP_SIDE pixels long, and over it, only its part in view, in tiles of TILE pixels at the full scale
TILE_ABOVE = 4096
BACKDROP_SIDE = 2048
TILE = 1024
MAX_TILES = 48  # tiles kept (about 150 MB): those of the pages in view, and a few of before
# (these, and CACHE_BYTES and MAX_TILES, are those of the memory profile: see performance.py)
AHEAD = 0.5  # pages drawn ahead of the view (and behind it), in heights of the window
TRANSPARENT = True  # selections drawn with transparency (else outlines)
PRINT_SLICE = 0.006  # seconds of fingerprints worked out at each turn of the event loop (see want_print)
CACHE_BYTES = 256 << 20  # renderings kept, so that a page scrolled back to needn't render again (bytes of them)
SELECTED = QColor(42, 127, 255)
NEAR_TEXT = 3.0  # points: a drag that starts this close to a word selects text
FREETEXT_SIZE = (180.0, 40.0)  # points: a text box made by a click
NOTE_EDITOR = (220.0, 110.0)  # points: the field where the text of a note is written
BOXES = ("freetext", "typewriter", "area", "rect", "ellipse", "cloud", "redact")  # (tools that drag a box)
LINES = ("line", "arrow")
TEXT_TOOLS = MARKUP + ("replace",)  # (the tools that are dragged over text)
POLYGONS = ("polygon", "polyline")  # (tools that click point after point)
CLICKS = ("note", "caret", "stamp", "callout", "mark", "attachment", "signature")
MARK_SIZE = 12.0  # points: of a check mark, a cross...


# Sin canal alfa: la página siempre se pinta sobre blanco. El .copy() hace falta porque QImage
# no copia los bytes de pix.samples, que desaparecen con el Pixmap de PyMuPDF.
def rgb_image(data, width: int, height: int, stride: int, screen: bool = False) -> QImage:
    """A picture of its own from the RGB bytes DATA. For the SCREEN, in the format of the screen (RGB32): the
    one conversion it needs is done here, in one pass that also copies, and then turning it into a QPixmap
    costs nothing (from RGB888, a copy and then a conversion: 3 ms instead of 1.3 for a page at 300 %).
    Else as it is, a quarter smaller (the thumbnails, kept many at once)."""
    image = QImage(data, width, height, stride, QImage.Format.Format_RGB888)
    # (copy() o la conversión: QImage no es dueña de DATA, que puede desaparecer)
    return image.convertToFormat(QImage.Format.Format_RGB32) if screen else image.copy()


def page_image(page: pymupdf.Page, scale: float, clip: tuple | None = None, tint: tuple | None = None,
               sharpness: tuple | None = None, screen: bool = False) -> QImage:
    """PAGE rendered at SCALE (only CLIP of it, in points, if given; in the colours TINT, if given, and with the
    sharpness of the text SHARPNESS, by default that of the settings: see reading.py); for the SCREEN, in its
    format (see rgb_image)."""
    from ..core import rendering

    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False,
                          clip=pymupdf.Rect(clip) if clip is not None else None)
    sharpness = reading.SHARPEN if sharpness is None else sharpness
    if sharpness == rendering.AS_DRAWN:
        if tint is not None:
            pix.tint_with(tint[0], tint[1])
        return rgb_image(pix.samples_mv, pix.width, pix.height, pix.stride, screen)
    stride, data = rendering.sharpen(pix, sharpness)
    if tint is not None:
        data, stride = rendering.tinted(pix.width, pix.height, stride, data, tint), pix.width * 3
    return rgb_image(data, pix.width, pix.height, stride, screen)


def cache_bytes(pixmap: QPixmap) -> int:
    """The memory PIXMAP takes (32 bits a pixel, as the screen's)."""
    return pixmap.width() * pixmap.height() * 4


def _distance(p: QPointF, a: QPointF, b: QPointF) -> float:
    """From P to the segment from A to B."""
    dx, dy = b.x() - a.x(), b.y() - a.y()
    length = dx * dx + dy * dy
    # t es la proyección de P sobre la recta AB, recortada a [0, 1] para no salir del segmento.
    t = 0.0 if length == 0 else max(0.0, min(1.0, ((p.x() - a.x()) * dx + (p.y() - a.y()) * dy) / length))
    return math.hypot(p.x() - a.x() - t * dx, p.y() - a.y() - t * dy)


def _near_path(point: QPointF, path, reach: float, closed: bool = False) -> bool:
    pts = [QPointF(*pt) for pt in path]
    # Un polígono cerrado vuelve a su primer punto: se añade el lado que falta.
    if closed and len(pts) > 2:
        pts.append(pts[0])
    # A path of one point (a dot made with a tap) is hit within a circle around it.
    if len(pts) == 1:
        return math.hypot(point.x() - pts[0].x(), point.y() - pts[0].y()) <= reach
    return any(_distance(point, p, q) <= reach for p, q in zip(pts, pts[1:]))


def erase_ink(a: Annotation, centres: list[tuple[float, float]], radius: float) -> Annotation | None:
    """A, a drawing, without what lies within RADIUS of CENTRES: its strokes cut
    where they were erased (None if nothing is left of it)."""
    def gone(p) -> bool:
        return any((p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2 <= radius * radius for c in centres)

    # Cada trazo se parte donde pasó la goma; los pedazos de un solo punto se descartan,
    # porque ya no dibujan nada.
    paths = []
    for path in a.paths:
        piece: list = []
        for p in path:
            if gone(p):
                if len(piece) > 1:
                    paths.append(tuple(piece))
                piece = []
            else:
                piece.append(p)
        if len(piece) > 1:
            paths.append(tuple(piece))
    if not paths:
        return None
    # The frame is computed again from what is left, so the selection fits the remains.
    return dataclasses.replace(a, paths=tuple(paths), rect=annots.frame(a.kind, paths, a.width))


# The kinds whose comment is not seen on the page (a note shows its own sign, a text box its text; a stamp's and a
# signature's text are the program's): those get a sign when they have one
COMMENT_SIGN = MARKUP + ("caret", "area", "rect", "ellipse", "polygon", "cloud", "line", "arrow", "polyline", "ink",
                         "marker")


def has_comment(a: Annotation) -> bool:
    """Whether A has a comment of the user's that nothing on the page shows."""
    text = (a.contents or "").strip()
    if not text or a.kind not in COMMENT_SIGN:
        return False
    # (una firma dibujada es un trazo a mano con el texto «Firma», que pone el programa)
    return not (a.kind == "ink" and text in ("Signature", tr("Signature")))


class CommentSign(QGraphicsItem):
    """A small speech balloon with two lines of writing, in the colour of its annotation, beside the annotation's top
    right corner (after the bubble of its replies, if it has one): the annotation has a comment, which the balloon's
    tooltip shows, as the annotation's does. An item of its own, which ignores the view's zoom and turn: it keeps its
    size on the screen, and Qt draws it whole whatever the zoom (drawn by the annotation, it went out of its bounds
    when the pages were small)."""

    W, H = 12, 9  # (pixels)

    def __init__(self, parent: QGraphicsItem, color: str, beside: bool, tip: str):
        super().__init__(parent)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.setZValue(5)
        self.beside = beside
        self.color = QColor(color or "#555555")
        if self.color.lightness() > 140:  # (un amarillo de resaltado casi no se ve sobre el papel: más oscuro)
            self.color = self.color.darker(170)
        self.setToolTip(tip)

    def _left(self) -> float:
        return 2 + (8 * 1.3 + 3 if self.beside else 0)  # (después de la burbuja de las respuestas)

    def boundingRect(self) -> QRectF:
        return QRectF(self._left() - 1, -self.H - 3, self.W + 2, self.H + 6)

    def paint(self, painter, option, widget=None):
        x, y, w, h = self._left(), -self.H - 2, self.W, self.H
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        balloon = QPainterPath()
        balloon.addRoundedRect(QRectF(x, y, w, h), 2, 2)
        tail = QPainterPath()
        tail.moveTo(x + 2.5, y + h - 0.5)
        tail.lineTo(x + 2.5, y + h + 3)
        tail.lineTo(x + 6, y + h - 0.5)
        painter.setPen(QPen(self.color, 1.1))
        painter.setBrush(QColor(255, 255, 255, 235))
        painter.drawPath(balloon.united(tail))
        painter.setPen(QPen(self.color, 1))
        for k, length in ((1, w - 5), (2, (w - 5) * 0.65)):  # (dos renglones de escritura, el segundo más corto)
            painter.drawLine(QPointF(x + 2.5, y + h * k / 3), QPointF(x + 2.5 + length, y + h * k / 3))


# Kinds drawn as an icon of a fixed size in the PDF: on the screen, always NOTE_SIZE pixels
SCREEN_ICONS = ("note", "attachment")


class AnnotItem(QGraphicsItem):
    """An annotation on its page, drawn as it will look; when selected, a blue
    frame around it, with handles where it can be resized or reshaped."""

    def __init__(self, index: int, annotation: Annotation, selected: bool, parent=None):
        super().__init__(parent)
        self.index = index
        self.annot = annotation
        self.chosen = selected
        self.setZValue(2 if selected else 1)
        # El tooltip es HTML: el texto del usuario se escapa a mano (& y <) y se recorta a 300 caracteres.
        tip = f"<b>{annotation.name()}</b>"
        if annotation.author:
            tip += f" — {annotation.author}"
        if annotation.contents:
            text = annotation.contents if len(annotation.contents) <= 300 else annotation.contents[:298] + "…"
            tip += "<br>" + text.replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br>")
        # Only the last three replies, each cut to 80 characters, so the tooltip stays small.
        if annotation.replies:
            tip += "<br><i>" + "<br>".join(f"{r.author}: {r.contents[:80]}".replace("<", "&lt;")
                                           for r in annotation.replies[-3:]) + "</i>"
        self.setToolTip(tip)
        self.sign = None
        self.outlined = False  # (a box being dragged: a frame of dashes around it, as the one that selects)
        self._place_sign()

    def _place_sign(self):
        """The comment sign (CommentSign), at the top right corner of the annotation, if it has a comment that
        nothing on the page shows; none if not."""
        a = self.annot
        if not has_comment(a):
            if self.sign is not None and self.sign.scene() is not None:
                self.sign.scene().removeItem(self.sign)
            self.sign = None
            return
        if self.sign is None:
            self.sign = CommentSign(self, a.color, bool(a.replies or a.status()), self.toolTip())
        self.sign.setPos(qrect(a.rect).right(), qrect(a.rect).top())

    def set_annotation(self, annotation: Annotation):
        """Show ANNOTATION in its place (while it is dragged)."""
        self.prepareGeometryChange()
        self.annot = annotation
        self._place_sign()
        self.update()

    def _view_zoom(self) -> float:
        scene = self.scene()
        views = scene.views() if scene is not None else []
        return (views[0].transform().m11() or 1) if views else 1

    def rezoom(self):
        """The zoom changed: an icon's frame (see frame) changes with it."""
        if self.annot.kind in SCREEN_ICONS:
            self.prepareGeometryChange()
            self.update()

    def frame(self) -> QRectF:
        a = self.annot
        # El icono de una nota o de un adjunto se ve siempre de NOTE_SIZE píxeles, desde su esquina de arriba a la
        # izquierda, sea cual sea el zoom (como pide su marca NoZoom): en una página escaneada, 16 puntos son dos
        # píxeles con la página entera a la vista
        if a.kind in SCREEN_ICONS:
            r, side = qrect(a.rect), NOTE_SIZE / self._view_zoom()
            return QRectF(r.left(), r.top(), side, side)
        # Las anotaciones de marcado (resaltado, subrayado...) se miden por sus cuadriláteros, no por su rect.
        if a.kind in MARKUP:
            return qrect(annots.union(a.quads)) if a.quads else qrect(a.rect)
        # A callout's frame includes the point its line ends at, which is usually outside its box.
        if a.kind == "callout" and a.paths:
            tip = a.paths[0][0]
            return qrect(a.rect).united(QRectF(QPointF(*tip), QPointF(*tip)))
        return qrect(a.rect)

    def boundingRect(self) -> QRectF:
        # Margen amplio: los trazos anchos, las puntas de flecha y las asas se dibujan fuera del marco,
        # y Qt no repinta lo que quede fuera de boundingRect.
        pad = max(self.annot.width, 2) * 4 + 12
        return self.frame().adjusted(-pad, -pad, pad, pad)

    def handles(self) -> list[QPointF]:
        """The points that can be dragged one by one (of a line, a polygon; the place a callout points at)."""
        a = self.annot
        if (a.kind in VERTICES or a.kind == "callout") and a.paths:
            return [QPointF(*pt) for pt in a.paths[0]]
        return []

    def movable(self) -> bool:
        return self.annot.kind not in MARKUP and not self.annot.locked

    def hit(self, point: QPointF, grip: float) -> str | None:
        """What dragging at POINT does: None (it isn't there), '' (moves it), some of
        'l', 't', 'r', 'b' (resizes it by those edges), 'vN' (moves its point N)."""
        a = self.annot
        # Un resaltado solo se toca sobre sus cuadriláteros (con GRIP de margen) y nunca se redimensiona.
        if a.kind in MARKUP:
            inside = any(qrect(q).adjusted(-grip, -grip, grip, grip).contains(point) for q in a.quads)
            return "" if inside else None
        # The handles of points are tried first, so a vertex near an edge is reshaped rather than resized.
        if self.chosen and not a.locked:
            for i, h in enumerate(self.handles()):
                if math.hypot(point.x() - h.x(), point.y() - h.y()) <= grip * 1.5:
                    return f"v{i}"
        if a.kind in VERTICES and a.paths:
            reach = grip + a.width / 2
            if _near_path(point, a.paths[0], reach, closed=a.kind in ("polygon", "cloud")):
                return ""
            # Un polígono relleno (o una nube) se toma también por dentro; uno sin relleno, solo por sus lados.
            if a.kind in ("polygon", "cloud") and (a.fill or a.kind == "cloud") and \
                    qrect(a.rect).contains(point):
                return ""
            return None
        if a.kind == "callout" and a.paths and _near_path(point, (annots.anchor(a.rect, a.paths[0][0]),
                                                                  a.paths[0][0]), grip + 1):
            return ""
        r = self.frame() if a.kind in SCREEN_ICONS else qrect(a.rect)
        if a.kind in DRAWN and not self.chosen:  # (only on its lines; once selected, its frame too)
            return "" if any(_near_path(point, path, grip + a.width / 2) for path in a.paths) else None
        if not r.adjusted(-grip, -grip, grip, grip).contains(point):
            return None
        edges = ""
        # Los bordes se combinan: 'lt' es la esquina superior izquierda, 'rb' la inferior derecha.
        if a.kind in RESIZABLE and not a.locked and (self.chosen or a.kind not in DRAWN):
            if abs(point.x() - r.left()) <= grip:
                edges += "l"
            elif abs(point.x() - r.right()) <= grip:
                edges += "r"
            if abs(point.y() - r.top()) <= grip:
                edges += "t"
            elif abs(point.y() - r.bottom()) <= grip:
                edges += "b"
        if not edges and not r.contains(point):
            return None
        return edges

    def paint(self, painter, option, widget=None):
        a = self.annot
        if a.kind in SCREEN_ICONS:  # (at least NOTE_SIZE pixels: see frame)
            f = self.frame()
            a = dataclasses.replace(a, rect=(f.left(), f.top(), f.right(), f.bottom()))
        paint(painter, a)
        # m11 es el zoom de la vista: dividir por él da tamaños fijos en píxeles (burbuja, asas, candado)
        # sea cual sea el zoom.
        scale = painter.worldTransform().m11() or 1
        if a.replies or a.status():  # (a small speech bubble: it has replies, or a status)
            s = 8 / scale
            x, y = qrect(a.rect).right() + 2 / scale, qrect(a.rect).top() - s
            painter.setPen(QPen(QColor(90, 90, 90), 1 / scale))
            painter.setBrush(QColor({"Accepted": "#a5d6a7", "Rejected": "#ef9a9a", "Completed": "#90caf9",
                                     "Cancelled": "#e0e0e0"}.get(a.status(), "#fff59d")))
            painter.drawRoundedRect(QRectF(x, y, s * 1.3, s), s / 4, s / 4)
        if self.outlined and not self.chosen:
            # Mientras se arrastra: un cuadro de texto sin borde (o una figura sin color) no se vería
            pen = QPen(SELECTED, 1, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(qrect(a.rect))
        if not self.chosen:
            return
        frame = qrect(a.rect) if a.kind not in MARKUP else self.frame()
        pen = QPen(SELECTED, 1.2, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        side = 7 / scale
        handles = self.handles()
        # Lines and polylines get no dashed frame: the handles on their points are enough.
        if a.kind not in ("line", "arrow", "polyline"):
            painter.drawRect(frame.adjusted(-1 / scale, -1 / scale, 1 / scale, 1 / scale))
        if a.locked:  # (a small padlock in the corner)
            s = 9 / scale
            x, y = frame.right() - s - 2 / scale, frame.top() + 2 / scale
            painter.setPen(QPen(SELECTED, 1.2 / scale))
            painter.setBrush(QColor(255, 255, 255, 220))
            painter.drawRect(QRectF(x, y + s * 0.45, s, s * 0.55))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(QRectF(x + s * 0.2, y, s * 0.6, s * 0.9), 0, 180 * 16)
            return
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(SELECTED)
        # Filled squares at the corners resize; white circles mark the points that move one by one.
        corners = [] if a.kind not in RESIZABLE or a.kind in ("line", "arrow", "polyline") else \
            [frame.topLeft(), frame.topRight(), frame.bottomLeft(), frame.bottomRight()]
        for corner in corners:
            painter.drawRect(QRectF(corner.x() - side / 2, corner.y() - side / 2, side, side))
        painter.setBrush(QColor("white"))
        painter.setPen(QPen(SELECTED, 1.5 / scale))
        for h in handles:
            painter.drawEllipse(h, side / 2, side / 2)


class SharpPixmapItem(QGraphicsPixmapItem):
    """A rendering of a page (or a tile of one) that, shown at its own size (a pixel of it on a pixel of
    the screen), is drawn on whole pixels of the screen, as it is: never blurred."""

    def paint(self, painter: QPainter, option, widget=None):
        pixmap = self.pixmap()
        t = painter.deviceTransform()  # (in pixels of the screen, HiDPI included)
        # El zoom y la escala del render se redondean a tres decimales: se admite a lo sumo un píxel de diferencia
        # en todo el ancho de la imagen.
        side = max(pixmap.width(), pixmap.height(), 1)
        if pixmap.isNull() or t.type().value > QTransform.TransformationType.TxScale.value or \
                abs(t.m11() - 1) * side > 1 or abs(t.m22() - 1) * side > 1:
            super().paint(painter, option, widget)
            return
        # La página cae a menudo entre dos píxeles (63.5, por ejemplo); OpenGL la muestrea entonces entre ellos y
        # suaviza cada letra. Se lleva a píxeles enteros y se copia tal cual, sin interpolar.
        ratio = painter.device().devicePixelRatioF() or 1.0
        box = t.mapRect(QRectF(self.offset(), QSizeF(pixmap.size())))
        # Both edges are rounded, not the corner alone: two tiles side by side then meet on the same pixel.
        left, top = round(box.left()), round(box.top())
        target = QRect(left, top, round(box.right()) - left, round(box.bottom()) - top)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.setWorldTransform(QTransform.fromScale(1 / ratio, 1 / ratio))
        painter.drawPixmap(target, pixmap)
        painter.restore()


class PageItem(QGraphicsRectItem):
    """A page: white, with its rendering on it (once it is in view), and its annotations as children."""

    def __init__(self, number: int, size: QRectF, trim: QRectF | None = None):
        # Con los márgenes recortados (TRIM, en puntos de la página) el rectángulo es solo esa parte, y lo de fuera
        # (la imagen, las teselas, las anotaciones) no se ve; las coordenadas siguen siendo las de la página entera.
        super().__init__(trim if trim is not None else QRectF(0, 0, size.width(), size.height()))
        self.full = QRectF(0, 0, size.width(), size.height())  # (the whole page, trimmed or not)
        if trim is not None:
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape)
        self.number = number
        self.setPen(QPen(Qt.PenStyle.NoPen))
        # (white; or the page colour of the reading colours, while the page is drawn)
        self.setBrush(QBrush(QColor(reading.page_colour())))
        # La imagen renderizada y la capa de las teselas se crean al hacer falta (ver pixmap y tiles_layer): un
        # documento de miles de páginas no paga por las que nunca se ven.
        self._pixmap: QGraphicsPixmapItem | None = None
        self._tiles_layer: QGraphicsRectItem | None = None
        self.scale_shown = 0.0  # (of the rendering it shows; 0: none, or a stand-in)
        self.wanted: tuple | None = None  # (the key of the rendering asked for)
        self.tiles: dict[tuple, QGraphicsPixmapItem] = {}  # (scale, column, row) -> its picture

    @property
    def pixmap(self) -> QGraphicsPixmapItem:
        """The rendering of the page, a child of the white rectangle (white while it hasn't come)."""
        if self._pixmap is None:
            self._pixmap = SharpPixmapItem(self)
            self._pixmap.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
            # (under the tiles and the annotations, whichever is made first)
            self._pixmap.setZValue(0.1)
        return self._pixmap

    @property
    def tiles_layer(self) -> QGraphicsRectItem:
        """The layer of the tiles of a deep zoom: over the whole rendering, under the annotations (z 1 up)."""
        if self._tiles_layer is None:
            self._tiles_layer = QGraphicsRectItem(self)
            self._tiles_layer.setPen(QPen(Qt.PenStyle.NoPen))
            self._tiles_layer.setZValue(0.2)
        return self._tiles_layer

    def shows_nothing(self) -> bool:
        """Whether no rendering (nor stand-in) is shown yet."""
        return self._pixmap is None or self._pixmap.pixmap().isNull()

    def show_tile(self, key: tuple, pixmap: QPixmap, clip: tuple, scale: float):
        """Show the tile KEY ((scale, column, row)): PIXMAP, of the part CLIP of the page at SCALE."""
        tile = self.tiles.get(key)
        if tile is None:
            tile = self.tiles[key] = SharpPixmapItem(self.tiles_layer)
            tile.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        tile.setPixmap(pixmap)
        tile.setPos(clip[0], clip[1])
        tile.setScale(1 / scale)

    def clear_tiles(self, keep=lambda key: False):
        """Take away the tiles, but those whose key KEEP wants."""
        for key in [k for k in self.tiles if not keep(k)]:
            tile = self.tiles.pop(key)
            tile.setParentItem(None)
            if tile.scene() is not None:
                tile.scene().removeItem(tile)

    def show(self, pixmap: QPixmap, scale: float, final: bool = True):
        self.pixmap.setPixmap(pixmap)
        # Una imagen final se reduce por 1/scale (tiene scale píxeles por punto); un sustituto (miniatura o
        # render de otro zoom) se estira al ancho de la página, sea cual sea su tamaño.
        self.pixmap.setScale(1 / scale if final else self.full.width() / max(pixmap.width(), 1))
        if final:
            self.scale_shown = scale


class TextEditor(QGraphicsTextItem):
    """Where the text of a text box, a callout, a note or a caret is written, on the page:
    Ctrl+Enter, or a click elsewhere, keeps it; Escape gives it up."""

    def __init__(self, canvas: PageCanvas, parent, rich: bool = False):
        super().__init__(parent)
        self.canvas = canvas
        self.rich = rich  # (a text box's text, which can have bold, italic, colours and fonts)
        self.busy = False  # (while a dialog of its own is open: losing the focus to it doesn't end the writing)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setZValue(6)

    def sceneEvent(self, event):
        # Ctrl+B, Ctrl+I y Ctrl+U son del editor mientras se escribe: la ventana tiene Ctrl+B (añadir un marcador).
        if event.type() == QEvent.Type.ShortcutOverride and self.rich and \
                event.modifiers() == Qt.KeyboardModifier.ControlModifier and \
                event.key() in (Qt.Key.Key_B, Qt.Key.Key_I, Qt.Key.Key_U):
            event.accept()
            return True
        return super().sceneEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.canvas.cancel_text()
            return
        # Rich-text shortcuts only for text boxes; notes and carets keep plain text.
        keys = {Qt.Key.Key_B: "bold", Qt.Key.Key_I: "italic", Qt.Key.Key_U: "underline"}
        if self.rich and event.key() in keys and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self._format(keys[event.key()])
            return
        # Enter alone starts a new line; only Ctrl+Enter ends the writing.
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and \
                event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.canvas.commit_text()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        if event.reason() != Qt.FocusReason.PopupFocusReason and not self.busy:  # (not for its own menu)
            # Se difiere al siguiente turno del bucle de eventos: quitar el editor de la escena dentro de su
            # propio focusOutEvent no es seguro.
            QTimer.singleShot(0, lambda: self.canvas.commit_text(only=self))

    def _format(self, what: str, color: str = "", family: str = ""):
        from . import richtext

        cursor = self.textCursor()
        if what == "plain":
            richtext.plain(cursor)
        elif what in ("bold", "italic", "underline"):
            richtext.toggle(cursor, what)
        else:
            richtext.set_look(cursor, color, family)
        self.setTextCursor(cursor)

    def contextMenuEvent(self, event):
        if not self.rich:
            super().contextMenuEvent(event)
            return
        from ..annotate.annots import FONTS

        menu = QMenu()
        for what, name, keys in (("bold", tr("Bold"), "Ctrl+B"), ("italic", tr("Italic"), "Ctrl+I"),
                                 ("underline", tr("Underline"), "Ctrl+U")):
            action = menu.addAction(name, lambda w=what: self._format(w))
            action.setShortcut(QKeySequence(keys))
        menu.addAction(tr("Colour of the text…"), self._choose_color)
        fonts = menu.addMenu(tr("Font"))
        for key, name in FONTS.items():
            fonts.addAction(tr(name), lambda k=key: self._format("look", family=k))
        menu.addAction(tr("Plain text"), lambda: self._format("plain"))
        menu.addSeparator()
        for name, slot in ((tr("Cut"), self._cut), (tr("Copy"), self._copy), (tr("Paste"), self._paste)):
            menu.addAction(name, slot)
        # While the menu is open the editor loses the focus; busy keeps focusOutEvent from ending the writing.
        self.busy = True
        try:
            menu.exec(event.screenPos())
        finally:
            self.busy = False
        self.setFocus()

    def _choose_color(self):
        self.busy = True
        try:
            chosen = QColorDialog.getColor(self.defaultTextColor(), None, tr("Colour of the text"))
        finally:
            self.busy = False
        if chosen.isValid():
            self._format("look", color=chosen.name())
        self.setFocus()

    def _cut(self):
        self._copy()
        self.textCursor().removeSelectedText()

    def _copy(self):
        cursor = self.textCursor()
        if cursor.hasSelection():  # (as plain text: Ctrl+C keeps the formatting too)
            QApplication.clipboard().setText(cursor.selectedText().replace("\u2029", "\n"))

    def _paste(self):
        # Se pega como texto plano, sin el formato de origen.
        self.textCursor().insertText(QApplication.clipboard().text())



GPU_UNAVAILABLE = ""  # (why the graphics card wasn't used, when it was asked for: see use_gpu)


def opengl_works() -> str:
    """'' if OpenGL can draw here, else why not: a display without it (offscreen, a remote one), or a
    graphics card or driver that gives no context."""
    from PySide6.QtGui import QGuiApplication, QOffscreenSurface, QOpenGLContext

    if QGuiApplication.platformName() in ("offscreen", "minimal", "vnc"):
        return tr("This display ({name}) has no OpenGL", name=QGuiApplication.platformName())
    # Se prueba un contexto de verdad: un controlador sin OpenGL da pantallas negras, no un error
    context = QOpenGLContext()
    if not context.create():
        return tr("The graphics card gave no OpenGL context")
    surface = QOffscreenSurface()
    surface.create()
    try:
        if not context.makeCurrent(surface):
            return tr("The graphics card gave no OpenGL context")
        context.doneCurrent()
    finally:
        surface.destroy()
    return ""


def use_gpu(view: QGraphicsView) -> bool:
    """Draw VIEW with the graphics card, by OpenGL, if the settings ask for it (the setting gpu): its
    viewport becomes an OpenGL surface, which moves and scales the pictures of the pages there instead of
    on the processor. Whether it worked: where OpenGL can't draw (see opengl_works), or without its
    module, it stays as it was, and GPU_UNAVAILABLE says why."""
    global GPU_UNAVAILABLE
    from ..core import config

    try:
        if not config.get("gpu"):
            return False
        from PySide6.QtGui import QSurfaceFormat
        from PySide6.QtOpenGLWidgets import QOpenGLWidget
    except config.ConfigError:
        return False
    except ImportError:
        GPU_UNAVAILABLE = tr("The module of OpenGL of PySide6 is not installed")
        return False
    GPU_UNAVAILABLE = opengl_works()
    if GPU_UNAVAILABLE:
        return False
    surface = QOpenGLWidget()
    form = QSurfaceFormat()
    form.setSamples(4)  # (bordes suavizados también en la superficie de OpenGL)
    surface.setFormat(form)
    view.setViewport(surface)
    return True

class PageCanvas(TextSelectMixin, LinksMixin, ScrollingMixin, QGraphicsView):
    """The pages and their annotations. The annotations are identified by their
    index in the window's list; what the user does is reported with the signals."""

    drawn = Signal(object)  # Annotation: a new one (made by FACTORY), drawn on a page
    drawn_many = Signal(list)  # [Annotation]: new ones drawn at once (a stroke of a pen whose pressure changed)
    edited = Signal(int, object)  # index, Annotation: one moved, resized or reshaped
    erased = Signal(object)  # {index: Annotation, or None to delete it}: what the eraser did
    nudged = Signal(float, float)  # the selected annotations moved with the arrow keys, by (dx, dy) points
    picked = Signal(list, bool)  # indices clicked (or framed); whether to add them to the selection
    zoom_changed = Signal(float)
    page_changed = Signal(int)  # the page in view is another (scrolling)
    text_chosen = Signal(int, list)  # page, [Rect]: the lines of the text selected (with a markup tool)
    text_selected = Signal()  # the text selected with the tool Select text changed (see textselect.py)
    text_menu = Signal(object)  # QPoint (global): a right click on the text selected
    link_clicked = Signal(int, dict)  # page, the link clicked (see links.py)
    field_clicked = Signal(str, str)  # the name of a form field clicked, and the state of its button (see forming.py)
    sign_drawn = Signal(int, object)  # page, (x0, y0, x1, y1): the area of a visible signature (see signing.py)
    link_drawn = Signal(int, object)  # page, (x0, y0, x1, y1): the area of a new link, drawn with the tool Link
    link_edit = Signal(int, dict)  # page, a link of the document clicked with the tool Link
    double_clicked = Signal(int, int, tuple)  # index of the annotation (-1: none), page, (x, y) on it
    menu_asked = Signal(int, object, int, object)  # index (-1: none), place on the screen, page, place on it
    text_done = Signal(int, object)  # index (-1: a new one), the annotation with the text written

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        # Con la tarjeta gráfica (Configuración > Rendimiento, desde el próximo inicio), antes de lo demás:
        # lo que sigue se aplica a la superficie nueva.
        self.gpu = use_gpu(self)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setBackgroundBrush(self.palette().dark())
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        # (an OpenGL surface is drawn whole each time: partial updates of it cost more than they save)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate if self.gpu
                                   else QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.doc: pymupdf.Document | None = None
        self.continuous = True  # all the pages one under the other; else only the page shown
        self.page = 0  # the page in view (of a continuous view: the one in the middle of the window)
        self.fit = "page"  # 'page', 'width', 'height', 'visible' (the inked area: see ink_rect), or '' (a zoom of its own)
        self._ink: dict = {}  # (document, page) -> the inked area of the page (see ink_rect)
        self.trim = False  # (the margins trimmed: each page shows only its inked part, see trim_rect)
        self._trims: dict = {}  # (document, the size of a page) -> the part of such pages shown, trimmed
        self.spread = False  # (two pages side by side: see rows)
        self.cover = False  # (with spread: the first page alone, as the cover of a book)
        self.gap = GAP  # (between the pages and around them: 0 to hide the gaps, see set_gaps)
        self.turn = 0  # degrees (clockwise) the view turns every page: not the file (see set_turn)
        self._lens = None  # (la lupa, hecha la primera vez que se usa: magnifier.py)
        # 'select': selects, moves and resizes; 'hand': dragging scrolls; 'eraser': dragging erases;
        # else the kind of annotation that the tool makes: see annots.KINDS
        self.mode = "select"
        # makes the annotation of a kind, page, frame and paths with the style of new ones (the window's)
        self.factory: Callable[[str, int, Rect, tuple], Annotation] | None = None
        self.placeholder_for: Callable[[int], QImage | None] = lambda n: None  # (a thumbnail, until it is rendered)
        self.editable = True  # (False: the annotations are hidden, and nothing can be done to them)
        # which annotations can be selected, moved and erased: those of the mode of the window (the
        # others are shown, but the mouse goes through them)
        self.touchable = lambda annotation: True
        self.pages: dict[int, PageItem] = {}  # (those laid out)
        self._row_tops: list[float] = []  # (the top of each row laid out, in the scene, and its pages)
        self._row_pages: list[list[int]] = []
        self.shown_sizes: dict[int, QRectF] = {}  # (their sizes as the view shows them: see layout)
        self.items_: list[AnnotItem] = []
        self._shown_items: list[tuple[int, Annotation]] = []
        self._selected: list[int] = []
        self._words: dict[int, list] = {}
        self._init_text_select()
        self._init_links()
        self._init_scrolling()
        self._drag: dict | None = None
        self._poly: dict | None = None  # (a polygon being made: its page, its points, and its picture)
        self._editor: dict | None = None  # (a text being written: its item, frame, index and annotation)
        self._pressure: float | None = None  # (of a tablet's pen, while it touches)
        # how the pen's pressure counts ('along' the stroke, once for the whole 'stroke', or 'off'), and how
        # hard it must press ('soft', 'normal', 'firm'): see Settings
        self.pen_pressure, self.pen_curve = "stroke", "normal"
        self._pen_tool: str | None = None  # (the tool chosen, while the eraser end of the pen erases)
        self.pen_button = "pan"  # what the pen's side button does: 'pan' (moves the page while held) or 'menu'
        self._pen_pan: tuple | None = None  # (while it moves the page: where the pen and the scroll bars were)
        # the drawing made last, and when: a stroke made soon after, near it, is added to it (see _written)
        self._last_drawn: tuple[Annotation, float] | None = None
        self._quiet = False  # (scrolled by the program: the page in view is said by it)
        # El temporizador agrupa los cambios (desplazamiento, zoom, tamaño): se renderiza 90 ms después
        # del último, no en cada uno.
        self.render_timer = QTimer(self, singleShot=True, interval=90)
        self.render_timer.timeout.connect(self._render_visible)
        # Interval 0: one page rendered here per turn of the event loop, so the window stays responsive.
        self.local_timer = QTimer(self, singleShot=True, interval=0)
        self.local_timer.timeout.connect(self._render_next_here)
        self._here: list[tuple] = []  # (pages, or tiles, to render in this process, one at each turn)
        self._tile_cache: OrderedDict = OrderedDict()  # (document, page, scale, clip, column, row) -> QPixmap
        self._tiles_asked: set[tuple] = set()  # (the tiles asked for and not yet arrived)
        self._cache: OrderedDict = OrderedDict()  # (document, page number, scale) -> QPixmap
        # Los dibujos del documento de antes, por la huella de su página (ver carry_over): los de las páginas que un
        # cambio no tocó se muestran sin dibujarlas otra vez.
        self._carried: OrderedDict = OrderedDict()  # (fingerprint, scale) -> QPixmap
        self._prints = None  # (pageprint.Prints of the document shown, made when first asked for)
        # Las huellas de las páginas dibujadas se calculan en los ratos libres, unas pocas a la vez, para que un
        # cambio del documento las encuentre hechas (ver carry_over).
        self._print_queue: list[int] = []
        self.print_timer = QTimer(self, singleShot=True, interval=0)
        self.print_timer.timeout.connect(self._print_some)
        # (path, password, stamp) of the document on disk, if the pages can be rendered in
        # another process (see renderer.py)
        self.source = None
        self.verticalScrollBar().valueChanged.connect(self._scrolled)
        self.horizontalScrollBar().valueChanged.connect(lambda _: self.render_timer.start())

    # ----------------------------------------------------------------- the document and its layout

    field_at = None  # (set by the window: the form field at a place of a page; see forming.py)

    def set_document(self, doc: pymupdf.Document | None, page: int = 0):
        """Show DOC (None: nothing), at PAGE."""
        self.cancel_text()
        self.doc = doc
        self.page = page
        self._words = {}
        self._ink = {}
        self._trims = {}
        self._word_texts = {}
        self._links = {}
        self.text_sel, self._sel_marks = None, []
        self._found_of, self._found_pages, self._found_current = None, frozenset(), None
        # id(doc) forma parte de la clave de la caché, pero un documento nuevo puede heredar el id del viejo:
        # por eso se vacía.
        self._cache.clear()
        self._tile_cache.clear()
        self._tiles_asked.clear()
        self._shown_items, self._selected = [], []
        self._prints = None
        self._print_queue = []
        self.layout()
        self.go_to(page)
        # Con dibujos traídos del documento de antes, las páginas que siguen iguales se muestran ya, sin esperar
        # al temporizador (que dejaría ver la página en blanco un momento).
        if doc is not None and self._carried:
            self._render_visible()

    def page_print(self, number: int) -> bytes | None:
        """The fingerprint of page NUMBER of the document shown (see core/pageprint.py); None if it can't be
        worked out."""
        from ..core.pageprint import Prints

        if self.doc is None:
            return None
        if self._prints is None or self._prints.doc is not self.doc:
            self._prints = Prints(self.doc)
        try:
            return self._prints.page(number)
        except (RuntimeError, ValueError, IndexError):
            return None

    def want_print(self, number: int):
        """Work out the fingerprint of page NUMBER (drawn: its picture may be carried over) when there is time."""
        if self._prints is not None and number in self._prints._pages:
            return
        self._print_queue.append(number)
        if not self.print_timer.isActive():
            self.print_timer.start()

    def _print_some(self):
        """Some of the fingerprints waiting, for at most PRINT_SLICE seconds: the window answers between them."""
        end = time.monotonic() + PRINT_SLICE
        while self._print_queue and time.monotonic() < end:
            n = self._print_queue.pop(0)
            if self.doc is not None and n < self.doc.page_count:
                self.page_print(n)
        if self._print_queue:
            self.print_timer.start()

    def carry_over(self, images: dict[int, QImage] | None = None) -> dict[bytes, QImage]:
        """Before the document shown is closed for another state of itself (a change, undo, saving): keep its
        renderings by the fingerprints of their pages, so that those a change didn't touch, wherever they went,
        are shown again at once (see _render_visible). IMAGES: other pictures of its pages (the thumbnails), given
        back by fingerprint."""
        if self.doc is None:
            return {}
        mine = id(self.doc)
        carried = self._carried  # (the older ones first, as the cache: the oldest go first)
        for (doc_id, n, scale), pixmap in self._cache.items():
            fingerprint = self.page_print(n) if doc_id == mine else None
            if fingerprint is not None:
                carried[(fingerprint, scale)] = pixmap
                carried.move_to_end((fingerprint, scale))
        total = sum(cache_bytes(p) for p in carried.values())
        while total > CACHE_BYTES and len(carried) > 1:
            total -= cache_bytes(carried.popitem(last=False)[1])
        out = {}
        for n, image in (images or {}).items():
            fingerprint = self.page_print(n)
            if fingerprint is not None:
                out[fingerprint] = image
        return out

    def forget_carried(self):
        """Forget what carry_over kept (another document, or other settings of drawing)."""
        self._carried.clear()

    def page_rect(self, number: int) -> QRectF:
        r = self.doc[number].rect
        return QRectF(0, 0, r.width, r.height)

    def layout(self):
        """Lay out the pages (all of them, or only the page shown): a PageItem for each."""
        self.cancel_polygon()
        self._drag = None
        scene = self.scene()
        scene.clear()
        self.pages, self.items_ = {}, []
        self._found_items, self._found_drawn = [], set()  # (scene.clear() acaba de borrarlos)
        self.shown_sizes = {}
        self._row_tops, self._row_pages = [], []
        if self.doc is None:
            scene.setSceneRect(QRectF())
            return
        # En la vista de una página solo está su fila (una página, o dos lado a lado); el min() cubre un documento
        # que perdió páginas.
        rows = self.rows() if self.continuous else [self.row_of(min(self.page, self.doc.page_count - 1))]
        sizes = {n: self.page_rect(n) for row in rows for n in row}
        trims = {n: self.trim_rect(n, sizes[n]) for n in sizes} if self.trim else {}
        # (as the view turns them; from SIZES, not asking MuPDF for each page a second time)
        across = self.turn in (90, 270)
        shown = {n: QRectF(0, 0, r.height(), r.width()) if across else QRectF(0, 0, r.width(), r.height())
                 for n, r in ((n, trims.get(n, sizes[n])) for n in sizes)}
        # (kept: the fit reads them, instead of asking MuPDF for every page again at each resize)
        self.shown_sizes = shown
        widest = max(self._row_width(row, shown) for row in rows)
        y = self.gap
        for row in rows:
            # A row is centred on x = 0 in the scene, so pages of different widths line up along their middle;
            # two pages side by side meet there (the left one ends at GAP / 2 before it).
            if len(row) == 1:
                xs = [-shown[row[0]].width() / 2]
            else:
                xs = [-shown[row[0]].width() - self.gap / 2, self.gap / 2]
            # (the top of each row, in order: the pages near a place are found by bisection, see near_pages)
            self._row_tops.append(y)
            self._row_pages.append(row)
            for n, x in zip(row, xs):
                item = PageItem(n, sizes[n], trims.get(n))
                scene.addItem(item)
                if self.turn:
                    # (turned about its corner: then moved so that what shows starts at (x, y))
                    item.setRotation(self.turn)
                    corner = item.mapRectToScene(item.rect()).topLeft()
                    item.setPos(x - corner.x(), y - corner.y())
                else:
                    # (trimmed, the part shown starts at (x, y), not the page's corner)
                    item.setPos(x - item.rect().left(), y - item.rect().top())
                self.pages[n] = item
            y += max(shown[n].height() for n in row) + self.gap
        scene.setSceneRect(QRectF(-widest / 2 - self.gap, 0, widest + 2 * self.gap, y))
        self._place_annotations()
        self._place_found()
        self.render_timer.start()

    def shown_rect(self, number: int) -> QRectF:
        """Page NUMBER's rectangle as the view shows it (width and height swapped if turned 90° or 270°; only
        its inked part, with the margins trimmed)."""
        r = self.trim_rect(number) if self.trim else self.page_rect(number)
        r = QRectF(0, 0, r.width(), r.height())
        return QRectF(0, 0, r.height(), r.width()) if self.turn in (90, 270) else r

    def set_gaps(self, on: bool):
        """The gaps between the pages shown (ON) or hidden: the pages one against the other, as a scroll."""
        self.gap = GAP if on else 0
        if self.doc is not None:
            self.layout()
            self.apply_fit()
            self.go_to(self.page)

    def set_trim(self, on: bool):
        """The margins of the pages trimmed (ON): only the part of each page that has ink is shown."""
        self.trim = on
        if self.doc is not None:
            page = self.page
            self.layout()
            self.apply_fit()
            self.go_to(page)

    def trim_rect(self, number: int, size: QRectF | None = None) -> QRectF:
        """The part of page NUMBER shown with the margins trimmed, in its points: the same for every page of
        its size, the inked areas of a few of them put together (so that the text doesn't jump from page to
        page, and a long document isn't read whole)."""
        size = size if size is not None else self.page_rect(number)
        key = (id(self.doc), round(size.width()), round(size.height()))
        if key not in self._trims:
            count = self.doc.page_count
            # (doce páginas repartidas por el documento, de este tamaño; y esta, siempre)
            sample = {number} | {round(i * (count - 1) / 11) for i in range(12)} if count > 1 else {number}
            area = QRectF()
            for n in sorted(sample):
                if n != number and self.page_rect(n).size().toSize() != size.size().toSize():
                    continue
                ink = self.ink_rect(n)
                if ink != self.page_rect(n):  # (a blank page says nothing of the margins)
                    area = ink if area.isNull() else area | ink
            self._trims[key] = (area & size) if not area.isNull() else QRectF(size)
        return self._trims[key]

    def set_turn(self, degrees: int):
        """Turn the view of every page DEGREES (a multiple of 90, clockwise); the file stays as it is."""
        self.turn = degrees % 360
        if self.doc is not None:
            self.layout()
            self.apply_fit()
            self.go_to(self.page)

    def rows(self) -> list[list[int]]:
        """The pages in rows: one in each, or two side by side (spread), the first alone if it is a cover."""
        count = self.doc.page_count if self.doc is not None else 0
        if not self.spread:
            return [[n] for n in range(count)]
        out = [[0]] if self.cover and count else []
        start = 1 if self.cover else 0
        out += [list(range(n, min(n + 2, count))) for n in range(start, count, 2)]
        return out

    def _row_count(self) -> int:
        count = self.doc.page_count if self.doc is not None else 0
        if not self.spread or not count:
            return count
        return 1 + count // 2 if self.cover else (count + 1) // 2

    def _row_index(self, page: int) -> int:
        """The row PAGE is in (as rows() numbers them), worked out instead of searched for."""
        if not self.spread:
            return page
        if self.cover:
            return 0 if page == 0 else (page - 1) // 2 + 1
        return page // 2

    def _row_at(self, i: int) -> list[int]:
        count = self.doc.page_count if self.doc is not None else 0
        if not self.spread:
            return [i]
        if self.cover:
            if i == 0:
                return [0]
            start = 1 + 2 * (i - 1)
        else:
            start = 2 * i
        return list(range(start, min(start + 2, count)))

    def row_of(self, page: int) -> list[int]:
        # (en tiempo constante: antes se buscaba en rows(), que se rehacía entera para cada página)
        count = self.doc.page_count if self.doc is not None else 0
        if not 0 <= page < count:
            return [page]
        return self._row_at(self._row_index(page))

    def neighbour(self, page: int, step: int) -> int:
        """The page STEP rows after (or before) that of PAGE: its first page (with spread, a row is two pages)."""
        rows = self._row_count()
        if not rows:
            return 0
        count = self.doc.page_count
        i = self._row_index(page) if 0 <= page < count else 0
        return self._row_at(max(0, min(i + step, rows - 1)))[0]

    def _row_width(self, row: list[int], sizes: dict) -> float:
        if len(row) == 1:
            return sizes[row[0]].width()
        return 2 * max(sizes[row[0]].width(), sizes[row[1]].width()) + self.gap

    def set_spread(self, on: bool, cover: bool | None = None):
        """Two pages side by side (ON), the first alone if COVER; then the page shown stays in view."""
        self.spread = on
        if cover is not None:
            self.cover = cover
        if self.doc is not None:
            self.layout()
            self.apply_fit()
            self.go_to(self.page)

    def set_continuous(self, on: bool):
        if on != self.continuous:
            self.continuous = on
            self.layout()
            self.go_to(self.page)

    def set_annotations(self, items: list[tuple[int, Annotation]], selected: list[int]):
        """Show ITEMS ((index, annotation), on whatever page), SELECTED among them; the pages stay."""
        self._shown_items, self._selected = list(items), list(selected)
        self._place_annotations()

    def _place_annotations(self):
        """The items of the annotations: those that are as they were stay, the others are made again."""
        # Un arrastre de edición apunta a un item que aquí puede reemplazarse: se abandona.
        if self._drag is not None and self._drag.get("kind") == "edit":
            self._drag = None
        # Annotation is a frozen (hashable) dataclass: an item whose annotation and selection are unchanged
        # is reused instead of being made again.
        old = {(i.index, i.annot, i.chosen): i for i in self.items_}
        items = []
        for index, a in self._shown_items:
            parent = self.pages.get(a.page)
            if parent is None:
                continue
            item = old.pop((index, a, index in self._selected), None)
            if item is None or item.parentItem() is not parent:
                item = AnnotItem(index, a, index in self._selected, parent)
            else:  # (as it was before a drag or the eraser touched it)
                item.setOpacity(1.0)
                item.setVisible(True)
            items.append(item)
        for item in old.values():
            if item.scene() is not None:
                self.scene().removeItem(item)
        self.items_ = items

    def go_to(self, page: int, rect: Rect | None = None):
        """Bring PAGE into view (its top; or, if given, RECT on it)."""
        if self.doc is None:
            return
        self.stop_animations()  # (a jump: the wheel or the zoom that was running is finished first)
        page = max(0, min(page, self.doc.page_count - 1))
        changed = page != self.page
        self.page = page
        # In single-page view the page asked for may not be laid out yet: lay it out (and fit it) first.
        if not self.continuous and (page not in self.pages):
            self.layout()
            if self.fit:
                self.apply_fit()
        item = self.pages.get(page)
        if item is None:
            return
        # _quiet evita que _scrolled anuncie otra página mientras el programa mueve la vista.
        self._quiet = True
        if rect is not None:
            self.ensureVisible(item.mapRectToScene(qrect(rect)), 60, 60)
        else:
            top = item.sceneBoundingRect().topLeft()  # (the top of the page as it shows, turned or not)
            bar = self.verticalScrollBar()
            # Deja el borde superior de la página GAP puntos por debajo del borde de la vista.
            bar.setValue(round(self.mapFromScene(QPointF(0, top.y() - self.gap)).y() + bar.value()))
        self._quiet = False
        self.render_timer.start()
        if changed:
            self.page_changed.emit(page)

    def scroll_to(self, page: int, y: float):
        """Put the point at height Y (in points, from the top of PAGE as shown) at the top of the view."""
        item = self.pages.get(page)
        if item is None:
            return
        self._quiet = True
        # (a page turned sideways: its height runs across the view, so its top is gone to)
        point = item.mapToScene(QPointF(0, max(item.rect().top(), min(y, item.rect().bottom())))) if self.turn in (0, 180) \
            else item.sceneBoundingRect().topLeft()
        bar = self.verticalScrollBar()
        bar.setValue(round(self.mapFromScene(QPointF(0, point.y() - self.gap)).y() + bar.value()))
        self._quiet = False
        self.render_timer.start()

    def near_pages(self, top: float, bottom: float) -> list[PageItem]:
        """The pages of the rows between TOP and BOTTOM (scene coordinates), and of the row on each side:
        found by bisection on the tops of the rows, not by going through every page."""
        if not self._row_tops:
            return list(self.pages.values())
        first = max(0, bisect.bisect_right(self._row_tops, top) - 2)
        last = min(len(self._row_tops), bisect.bisect_right(self._row_tops, bottom) + 1)
        return [self.pages[n] for row in self._row_pages[first:last] for n in row if n in self.pages]

    def _scrolled(self, _value):
        self.render_timer.start()
        self._more_found()
        if self._quiet or not self.continuous or not self.pages:
            return
        # The page in view is the one under the middle of the window or, in the gap between two, the nearest.
        middle = self.mapToScene(self.viewport().rect().center()).y()
        here = min(self.near_pages(middle, middle), key=lambda p: 0 if p.sceneBoundingRect().top() <= middle
                   <= p.sceneBoundingRect().bottom() else min(abs(p.sceneBoundingRect().top() - middle),
                                                              abs(p.sceneBoundingRect().bottom() - middle)))
        if here.number != self.page:
            self.page = here.number
            self.page_changed.emit(here.number)

    def changeEvent(self, event):
        # El fondo detrás de las páginas sigue al tema (claro u oscuro), también si cambia con la ventana abierta
        if event.type() == QEvent.Type.PaletteChange:
            self.setBackgroundBrush(self.palette().dark())
        super().changeEvent(event)

    # ----------------------------------------------------------------- rendering

    def zoom(self) -> float:
        return self.transform().m11()

    def _rezoom_icons(self, *_):
        for item in self.items_:
            item.rezoom()

    def _full_scale(self) -> float:
        """The scale of the zoom on this screen (on HiDPI screens, in physical pixels)."""
        return round(self.zoom() * self.devicePixelRatioF(), 3)

    def _tiled(self, number: int) -> bool:
        """Whether page NUMBER is drawn in tiles at this zoom (see TILE_ABOVE)."""
        r = self.doc[number].rect
        return max(r.width, r.height) * self._full_scale() > TILE_ABOVE

    def _scale_for(self, number: int) -> float:
        """The scale to render page NUMBER at, whole, for the zoom and the screen (for a page drawn in
        tiles, that of its backdrop, at most BACKDROP_SIDE pixels long)."""
        # En pantallas HiDPI se renderiza a la resolución física (devicePixelRatio), no a la lógica.
        scale = self.zoom() * self.devicePixelRatioF()
        r = self.doc[number].rect
        if max(r.width, r.height) * scale > TILE_ABOVE:
            return round(min(scale, BACKDROP_SIDE / max(r.width, r.height)), 3)
        # Huge pages at a high zoom are capped at MAX_PIXELS, keeping the proportions; Qt scales the rest up.
        if r.width * scale * r.height * scale > MAX_PIXELS:
            scale *= (MAX_PIXELS / (r.width * scale * r.height * scale)) ** 0.5
        return round(scale, 3)

    def clear_cache(self):
        """Forget the renderings (another document was opened, or this one changed on disk)."""
        self._cache.clear()
        self._carried.clear()
        self._tile_cache.clear()
        self._tiles_asked.clear()
        for item in self.pages.values():
            item.scale_shown = 0.0
            item.clear_tiles()

    def _keep(self, key: tuple, image: QImage | QPixmap) -> QPixmap:
        pixmap = image if isinstance(image, QPixmap) else QPixmap.fromImage(image)
        self._cache[key] = pixmap
        if self.doc is not None and key[0] == id(self.doc):
            self.want_print(key[1])
        # Caché LRU sencilla: move_to_end al usar una entrada, popitem(last=False) para expulsar la más vieja. Se
        # cuentan los bytes, no las páginas; la última siempre se queda, aunque sola pase del límite.
        total = sum(cache_bytes(p) for p in self._cache.values())
        while total > CACHE_BYTES and len(self._cache) > 1:
            total -= cache_bytes(self._cache.popitem(last=False)[1])
        return pixmap

    def _remote(self):
        """The renderer of other processes, if pages are rendered there."""
        from .renderer import renderer

        # Without a document on disk (source is None) the other processes cannot open it: render here.
        r = renderer()
        if not getattr(self, "_hears_words", False):
            # (a method, not a lambda: a lambda holding a window made Qt crash at exit)
            r.words_found.connect(self._words_arrived)
            self._hears_words = True
        return r if self.source is not None and r.available() else None

    def _words_arrived(self, path: str, stamp, number: int, found):
        """The words of page NUMBER, read by the process that drew it: kept, if they are of the file shown."""
        if self.source is not None and (path, stamp) == (self.source[0], self.source[2]) and number not in self._words:
            self.take_words(number, found)

    def visible_pages(self, ahead: float | None = None) -> list[int]:
        """The pages in view (and those within AHEAD of a window's height of it), the middle one first."""
        if not self.pages:
            return []
        ahead = AHEAD if ahead is None else ahead
        view = self.mapToScene(self.viewport().rect()).boundingRect()
        view = view.adjusted(0, -view.height() * ahead, 0, view.height() * ahead)
        found = [item.number for item in self.near_pages(view.top(), view.bottom())
                 if item.sceneBoundingRect().intersects(view)]
        return sorted(found, key=lambda n: abs(n - self.page))

    def _render_visible(self):
        """Render the pages in view at the zoom of now: from the cache, in the other process, or here."""
        if self.doc is None:
            return
        remote = self._remote()
        wanted = self.visible_pages()
        if remote is not None:
            # Las peticiones de páginas que salieron de la vista se cancelan en los otros procesos.
            remote.drop("view", keep=lambda path, number: number in wanted)
        # (the tiles asked for pages no longer in view are dropped too: asked again if they come back)
        self._tiles_asked = {k for k in self._tiles_asked if k[1] in wanted}
        # La cola de este proceso se rehace: las teselas que esperaban en ella dejan de estar pedidas, o no se
        # volverían a pedir nunca.
        for n, scale, tile in self._here:
            if tile is not None and self.doc is not None:
                self._tiles_asked.discard((id(self.doc), n, scale, *tile))
        self._here = []
        for n in wanted:
            item = self.pages[n]
            try:
                scale = self._scale_for(n)
            except (RuntimeError, ValueError):  # (the document was closed meanwhile)
                return
            if abs(scale - item.scale_shown) < 1e-3:
                continue
            key = (id(self.doc), n, scale)
            if key in self._cache:
                self._cache.move_to_end(key)
                item.show(self._cache[key], scale)
                continue
            # La misma página, dibujada antes de un cambio que no la tocó (la misma huella): no se dibuja otra vez.
            fingerprint = self.page_print(n) if self._carried else None
            if fingerprint is not None and (fingerprint, scale) in self._carried:
                item.show(self._keep(key, self._carried[(fingerprint, scale)]), scale)
                continue
            if item.shows_nothing():  # (meanwhile, an older rendering, or the thumbnail)
                old = next((k for k in reversed(self._cache) if k[:2] == key[:2]), None)
                carried = next((k for k in reversed(self._carried) if k[0] == fingerprint), None) \
                    if fingerprint is not None else None
                if old is not None:
                    item.show(self._cache[old], old[2], final=False)
                elif carried is not None:  # (of another zoom, from before the change)
                    item.show(self._carried[carried], carried[1], final=False)
                else:
                    image = self.placeholder_for(n)
                    if image is not None and not image.isNull():
                        item.show(QPixmap.fromImage(image), 1.0, final=False)
            # Esta misma imagen ya se pidió y no ha llegado: no se pide dos veces.
            if item.wanted == key:
                continue
            item.wanted = key
            # The page in the middle goes first in the queue of the other processes; the rest wait.
            if remote is not None:
                # (its words too, the first time: read there, the window needn't stop to read them)
                remote.request("view", self.source, n, scale, lambda image, key=key: self._arrived(key, image),
                               first=n == self.page, words=n not in self._words)
            else:
                self._here.append((n, scale, None))
        self._render_tiles(wanted, remote)
        if self._here:
            self.local_timer.start()

    def _render_tiles(self, wanted: list[int], remote):
        """For the pages in view drawn in tiles (see TILE_ABOVE), ask for the tiles of the part in view
        that are missing; take away those of other zooms, and those of pages no longer in view."""
        view = self.mapToScene(self.viewport().rect()).boundingRect()
        full = self._full_scale()
        for n, item in self.pages.items():
            try:
                tiled = n in wanted and self._tiled(n)
            except (RuntimeError, ValueError):  # (the document was closed meanwhile)
                return
            area = item.mapFromScene(view).boundingRect() & item.rect() if tiled else QRectF()
            if area.isEmpty():
                item.clear_tiles()
                continue
            item.clear_tiles(keep=lambda key: key[0] == full)
            step, (w, h) = TILE / full, (item.full.width(), item.full.height())
            for row in range(int(area.top() // step), int(area.bottom() // step) + 1):
                for column in range(int(area.left() // step), int(area.right() // step) + 1):
                    clip = (round(column * step, 3), round(row * step, 3),
                            round(min((column + 1) * step, w), 3), round(min((row + 1) * step, h), 3))
                    if clip[2] <= clip[0] or clip[3] <= clip[1] or (full, column, row) in item.tiles:
                        continue
                    key = (id(self.doc), n, full, clip, column, row)
                    if key in self._tile_cache:
                        self._tile_cache.move_to_end(key)
                        item.show_tile((full, column, row), self._tile_cache[key], clip, full)
                        continue
                    if key in self._tiles_asked:
                        continue
                    self._tiles_asked.add(key)
                    if remote is not None:
                        remote.request("view", self.source, n, full,
                                       lambda image, key=key: self._tile_arrived(key, image), clip=clip)
                    else:
                        self._here.append((n, full, (clip, column, row)))

    def _tile_arrived(self, key: tuple, image):
        """A tile (None: render it here; a Skipped: grey)."""
        from .renderer import Skipped, skipped_image

        self._tiles_asked.discard(key)
        if self.doc is None or key[0] != id(self.doc):
            return
        _, n, scale, clip, column, row = key
        if isinstance(image, Skipped):
            image = skipped_image(round((clip[2] - clip[0]) * scale), round((clip[3] - clip[1]) * scale), image,
                                  words=False)
        if image is None:
            try:
                image = page_image(self.doc[n], scale, clip, reading.TINT, screen=True)
            except (RuntimeError, ValueError):
                return
        pixmap = QPixmap.fromImage(image)
        self._tile_cache[key] = pixmap
        while len(self._tile_cache) > MAX_TILES:
            self._tile_cache.popitem(last=False)
        item = self.pages.get(n)
        # Solo si sigue haciendo falta: la página puede haber salido de la vista, o el zoom cambiado.
        if item is not None and scale == self._full_scale() and n in self.visible_pages():
            item.show_tile((scale, column, row), pixmap, clip, scale)

    def _render_next_here(self):
        """Render one page (or one tile) in this process (the window answers between them)."""
        if not self._here or self.doc is None:
            return
        n, scale, tile = self._here.pop(0)
        if tile is not None:
            clip, column, row = tile
            self._tile_arrived((id(self.doc), n, scale, clip, column, row), None)
            if self._here:
                self.local_timer.start()
            return
        try:
            image = page_image(self.doc[n], scale, tint=reading.TINT, screen=True)
        # El documento se cerró o cambió entre dos turnos: se abandonan las páginas pendientes.
        except (RuntimeError, ValueError):
            self._here = []
            return
        self._arrived((id(self.doc), n, scale), image)
        if self._here:
            self.local_timer.start()

    def _arrived(self, key: tuple, image):
        """A rendering (None: it couldn't be made in the other process: here, then; a Skipped: the page
        took too long, or made that process die: a grey page that says so)."""
        from .renderer import Skipped, skipped_image

        # A rendering of a document no longer open (key[0] is its id) is dropped.
        if self.doc is None or key[0] != id(self.doc):
            return
        if isinstance(image, Skipped):
            try:
                r = self.doc[key[1]].rect
            except (RuntimeError, ValueError, IndexError):
                return
            image = skipped_image(round(r.width * key[2]), round(r.height * key[2]), image)
        if image is None:
            try:
                image = page_image(self.doc[key[1]], key[2], tint=reading.TINT, screen=True)
            except (RuntimeError, ValueError):
                return
        pixmap = self._keep(key, image)
        item = self.pages.get(key[1])
        # Solo se muestra si es la que la página espera: pudo llegar tarde, después de otro zoom.
        if item is not None and item.wanted == key:
            item.wanted = None
            item.show(pixmap, key[2])

    def render_page_now(self):
        """Render the page in view at once (for the tests, and before a picture of the window)."""
        if self.doc is None or self.page not in self.pages:
            return
        scale = self._scale_for(self.page)
        self._arrived((id(self.doc), self.page, scale), page_image(self.doc[self.page], scale, tint=reading.TINT, screen=True))
        self.pages[self.page].show(self._cache[(id(self.doc), self.page, scale)], scale)

    # ----------------------------------------------------------------- zoom

    def set_zoom(self, factor: float, fit: str = ""):
        # (a zoom of the program, or a fit: an animation that was running is ended first, where it went)
        self.stop_animations()
        factor = max(MIN_ZOOM, min(factor, MAX_ZOOM))
        # El centro de la vista, en coordenadas de escena, para volver a él después de cambiar la escala.
        anchor = self.mapToScene(self.viewport().rect().center())
        self.fit = fit
        self.resetTransform()
        self.scale(factor, factor)
        # A fit in a continuous view goes back to the top of the current page instead.
        if self.continuous and self.page in self.pages and fit:
            self.go_to(self.page)
        else:
            self.centerOn(anchor)
        self.render_timer.start()
        self.zoom_changed.emit(factor)
        self._rezoom_icons()

    def apply_fit(self):
        if self.doc is None or not self.fit or self.page not in self.pages:
            return
        room = self.viewport().size()
        # Ajustar al ancho usa la fila más ancha (una página, o dos lado a lado), no la actual: así el zoom no salta
        # al pasar de una página vertical a una apaisada.
        # Una sola pasada por las filas, con los tamaños guardados por layout(): ajustar era cuadrático en el
        # número de páginas (row_of rehacía todas las filas para cada página), y se hace a cada cambio de tamaño.
        sizes = self.shown_sizes if self.shown_sizes.keys() >= self.pages.keys() else {
            n: self.shown_rect(n) for n in self.pages}
        rows = [r for r in (self.rows() if self.continuous else [self.row_of(self.page)])
                if all(m in sizes for m in r)]
        widest = max((self._row_width(r, sizes) for r in rows), default=max(s.width() for s in sizes.values()))
        size = QRectF(0, 0, 0, max(sizes[n].height() if n in sizes else self.shown_rect(n).height()
                                   for n in self.row_of(self.page)))
        # Los 4 píxeles dejan sitio al borde de la vista, para que el ajuste no haga aparecer barras.
        by_width = (room.width() - 4) / (widest + 2 * self.gap)
        by_height = (room.height() - 4) / (size.height() + 2 * self.gap)
        if self.fit == "visible":  # (the inked area of the page shown, as wide as the view, and centred)
            ink = self.ink_rect(self.page)
            fit = self.fit
            across = ink.height() if self.turn in (90, 270) else ink.width()  # (as it shows, turned or not)
            self.set_zoom((room.width() - 4) / (across + 2 * self.gap), fit)
            centre = self.pages[self.page].mapToScene(ink.center())
            self.centerOn(centre.x(), self.mapToScene(self.viewport().rect().center()).y())
            return
        factor = {"width": by_width, "height": by_height}.get(self.fit, min(by_width, by_height))
        self.set_zoom(factor, self.fit)

    def zoom_to(self, page, rect: QRectF):
        """Zoom so that RECT (on PAGE, in its points) fills the view, and centre it."""
        room = self.viewport().size()
        factor = min((room.width() - 8) / rect.width(), (room.height() - 8) / rect.height())
        self.set_zoom(factor)
        self.centerOn(page.mapToScene(rect.center()))

    def actual_size(self):
        """The page at its printed size on this screen (its points are 1/72 inch)."""
        self.set_zoom(self.logicalDpiX() / 72)

    def ink_rect(self, number: int) -> QRectF:
        """The part of page NUMBER that has ink (what isn't white, found on a small rendering), in its points;
        the whole page if it is blank."""
        key = (id(self.doc), number)
        if key not in self._ink:
            page = self.doc[number]
            scale = 0.25
            pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False, colorspace=pymupdf.csGRAY)
            data, w, h, stride = pix.samples, pix.width, pix.height, pix.stride
            rows = [y for y in range(h) if min(data[y * stride:y * stride + w]) < 235]
            cols = [x for x in range(w) if any(data[y * stride + x] < 235 for y in rows)] if rows else []
            if rows and cols:
                pad = 4
                r = QRectF((cols[0] - pad) / scale, (rows[0] - pad) / scale, (cols[-1] - cols[0] + 2 * pad) / scale,
                           (rows[-1] - rows[0] + 2 * pad) / scale)
                self._ink[key] = r & self.page_rect(number)
            else:
                self._ink[key] = self.page_rect(number)
        return self._ink[key]

    def zoom_by(self, factor: float):
        """Zoom in or out by FACTOR (Zoom in, Zoom out): about the centre of the view, animated."""
        self.zoom_smoothly(factor)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.apply_fit()
        self.render_timer.start()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Ctrl+rueda acerca alrededor del puntero, que se queda sobre lo mismo (animado: ver scrolling.py)
            if event.angleDelta().y():
                self.zoom_smoothly(1.15 if event.angleDelta().y() > 0 else 1 / 1.15, event.position())
            event.accept()
        elif not self.continuous and self.doc is not None:  # (one page at a time: past its end, the next)
            bar = self.verticalScrollBar()
            down = event.angleDelta().y() < 0
            # (a pair at a time, with two pages side by side)
            if down and bar.value() >= bar.maximum() and self.neighbour(self.page, 1) != self.row_of(self.page)[0]:
                self.go_to(self.neighbour(self.page, 1))
            elif not down and bar.value() <= bar.minimum() and self.row_of(self.page)[0] > 0:
                self.go_to(self.neighbour(self.page, -1))
                bar.setValue(bar.maximum())
            else:
                super().wheelEvent(event)
        elif self.scroll_smoothly(event):  # (a turn of the wheel, animated: see scrolling.py)
            event.accept()
        else:
            super().wheelEvent(event)

    # ----------------------------------------------------------------- where the mouse is

    def locate(self, pos) -> tuple[PageItem | None, QPointF]:
        """The page at POS (view coordinates; None if none is there), and the point on it."""
        scene = self.mapToScene(pos)
        for item in self.pages.values():
            # Each page is widened by half the gap, so a click between two pages still lands on one.
            if item.sceneBoundingRect().adjusted(-GAP / 2, -GAP / 2, GAP / 2, GAP / 2).contains(scene):
                return item, item.mapFromScene(scene)
        return None, QPointF()

    def _hit(self, pos) -> tuple[AnnotItem | None, str]:
        """The annotation at POS (view coordinates), and what dragging it does (see AnnotItem.hit)."""
        page, point = self.locate(pos)
        if page is None:
            return None, ""
        # GRIP está en píxeles de pantalla; dividido por el zoom queda en puntos de la página.
        grip = GRIP / (self.zoom() or 1)
        # (the selected first, then those on top: the last drawn)
        for item in sorted((i for i in self.items_ if i.parentItem() is page and self.touchable(i.annot)),
                           key=lambda i: (-i.zValue(), -i.index)):
            edges = item.hit(point, grip)
            if edges is not None:
                return item, edges
        return None, ""

    @staticmethod
    def _cursor(edges: str, movable: bool) -> Qt.CursorShape:
        if not movable:
            return Qt.CursorShape.PointingHandCursor
        if edges in ("lt", "rb"):
            return Qt.CursorShape.SizeFDiagCursor
        if edges in ("rt", "lb"):
            return Qt.CursorShape.SizeBDiagCursor
        if edges in ("l", "r"):
            return Qt.CursorShape.SizeHorCursor
        if edges in ("t", "b"):
            return Qt.CursorShape.SizeVerCursor
        if edges.startswith("v"):
            return Qt.CursorShape.CrossCursor
        return Qt.CursorShape.SizeAllCursor

    @staticmethod
    def _clamp(page: PageItem, point: QPointF) -> QPointF:
        r = page.rect()
        return QPointF(min(max(point.x(), r.left()), r.right()), min(max(point.y(), r.top()), r.bottom()))

    def contextMenuEvent(self, event):
        if self.mode == TEXT_SELECT and self.text_sel:  # (the menu of the text selected: see the window)
            self.text_menu.emit(event.globalPos())
            event.accept()
            return
        page, point = self.locate(event.pos())
        if page is None:
            return
        self.cancel_polygon()
        item, _ = self._hit(event.pos())
        # Un clic derecho sobre una anotación no seleccionada la selecciona antes del menú.
        if item is not None and not item.chosen:
            self.picked.emit([item.index], False)
        self.menu_asked.emit(item.index if item else -1, event.globalPos(), page.number, point)
        event.accept()

    def page_words(self, number: int) -> list:
        """The words of page NUMBER: (their rectangle as the page is shown, block, line), in reading order."""
        if number not in self._words:
            self.take_words(number, self.doc[number].get_text("words", sort=False) if self.doc is not None else [])
        return self._words[number]

    def take_words(self, number: int, found: list):
        """FOUND, the words of page NUMBER as get_text('words') gives them (read here, or by the process that drew
        the page: see renderer.py), kept as both page_words and word_texts want them: one reading for both."""
        if self.doc is None or not 0 <= number < self.doc.page_count:
            return
        # Las cajas se pasan a la página tal como se muestra, como todo lo que dibuja la ventana (ver annots.words).
        turn = self.doc[number].rotation_matrix
        boxes = []
        for x0, y0, x1, y1, _text, block, line, *_ in found:
            r = (pymupdf.Rect(x0, y0, x1, y1) * turn).normalize()
            boxes.append(((r.x0, r.y0, r.x1, r.y1), block, line))
        self._words[number] = boxes
        self._word_texts[number] = [tuple(w) for w in found]

    def _text_selection(self, number: int, start: QPointF, end: QPointF) -> list[Rect]:
        found = self.page_words(number)
        # El texto va de la palabra más cercana al inicio del arrastre a la más cercana al final,
        # en el orden de lectura (ver annots.text_rects).
        a = nearest_word(found, start.x(), start.y())
        b = nearest_word(found, end.x(), end.y())
        return [] if a is None else text_rects(found, a, b)

    def _show_text(self, rects: list[Rect]):
        for item in self._drag["marks"]:
            self.scene().removeItem(item)
        color = QColor(SELECTED)
        color.setAlpha(80)
        marks = []
        for r in rects:
            mark = QGraphicsRectItem(qrect(r), self._drag["page"])
            # (without transparency effects: an outline, not a translucent fill)
            mark.setPen(QPen(Qt.PenStyle.NoPen) if TRANSPARENT else QPen(QColor(SELECTED), 0))
            mark.setBrush(QBrush(color) if TRANSPARENT else QBrush())
            mark.setZValue(3)
            marks.append(mark)
        self._drag["marks"] = marks

    def near_text(self, number: int, point: QPointF) -> bool:
        """Whether POINT (on page NUMBER) is on a word, or very close to one."""
        # TODO: near_text recorre todas las palabras de la página en cada movimiento del ratón; un índice
        # espacial (o por líneas) ayudaría en páginas con miles de palabras.
        for (x0, y0, x1, y1), _, _ in self.page_words(number):
            if x0 - NEAR_TEXT <= point.x() <= x1 + NEAR_TEXT and y0 - NEAR_TEXT <= point.y() <= y1 + NEAR_TEXT:
                return True
        return False

    def magnify(self, pos: QPointF):
        """The lens at POS (view coordinates), with the page under it (see magnifier.py)."""
        from .magnifier import Lens, lens_image

        if self._lens is None:
            self._lens = Lens(self.viewport())
        page, point = self.locate(pos.toPoint())
        self._lens.show_at(pos, lens_image(self, page, point) if page is not None else None)

    def set_mode(self, mode: str):
        self.cancel_polygon()
        if self._lens is not None:
            self._lens.hide()
        if mode != TEXT_SELECT:
            self.clear_text_selection()
        self.mode = mode
        # The hand tool uses QGraphicsView's own scroll drag; mousePressEvent hands those clicks to Qt.
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag if mode == "hand"
                         else QGraphicsView.DragMode.NoDrag)
        self.viewport().unsetCursor()

    def _new(self, kind: str, page: int, rect: Rect, paths: tuple = ()) -> Annotation:
        # La fábrica da a las anotaciones nuevas el estilo actual de la ventana (color, grosor, autor...).
        if self.factory is not None:
            return self.factory(kind, page, rect, paths)
        return Annotation(kind, page, rect, paths=paths)

    def _preview(self, page: PageItem, annotation: Annotation) -> AnnotItem:
        item = AnnotItem(-1, annotation, False, page)
        item.setZValue(3)
        return item

    def _remove_drag_items(self):
        if self._drag is None:
            return
        for mark in self._drag.get("marks", []):
            self.scene().removeItem(mark)
        if "box" in self._drag:  # (a note's pop-up, being dragged)
            self.scene().removeItem(self._drag["box"])
        # An edit drag's item is the real annotation, not a preview: it must stay in the scene.
        if "item" in self._drag and self._drag["kind"] != "edit":
            self.scene().removeItem(self._drag["item"])

    # ----------------------------------------------------------------- a tablet's pen

    CURVES = {"soft": 0.6, "normal": 1.0, "firm": 1.6}  # (the pressure, to this power)

    SIDE = Qt.MouseButton.RightButton | Qt.MouseButton.MiddleButton  # (the side buttons of a pen)

    def viewportEvent(self, event):
        kind = event.type()
        if kind in (QEvent.Type.TabletPress, QEvent.Type.TabletMove, QEvent.Type.TabletRelease) \
                and self._pen_moves_page(event):
            event.accept()  # (and no mouse event is made of it: no menu)
            return True
        if kind in (QEvent.Type.TabletPress, QEvent.Type.TabletMove):
            # La presión (de 0 a 1) se eleva a la potencia de la curva: menos de 1 hace el lápiz más sensible,
            # más de 1 obliga a apretar más.
            self._pressure = max(event.pressure(), 0.0) ** self.CURVES.get(self.pen_curve, 1.0) \
                if self.pen_pressure != "off" else None
            if kind == QEvent.Type.TabletPress and self._drag is None and self._pen_tool is None \
                    and event.pointerType() == QPointingDevice.PointerType.Eraser and self.mode != "eraser":
                self._pen_tool, self.mode = self.mode, "eraser"  # (the pen turned over: it erases, while it touches)
            drag = self._drag
            if drag is not None and drag.get("kind") == "ink":
                if self._pressure is not None:
                    drag.setdefault("pressures", []).append(self._pressure)
                if kind == QEvent.Type.TabletMove:  # (the pen's own place, finer and more often than the mouse's)
                    scene = self.viewportTransform().inverted()[0].map(event.position())
                    self._ink_to(drag, drag["page"].mapFromScene(scene))
                    drag["tablet"] = True
                    event.accept()
                    return True
            event.ignore()  # (Qt then gives the same as mouse events)
            return False
        if kind == QEvent.Type.TabletRelease:
            self._pressure = None
            if self._pen_tool is not None:  # (after the mouse's release, which ends the erasing)
                QTimer.singleShot(0, self._end_pen_eraser)
            event.ignore()
            return False
        return super().viewportEvent(event)

    def _pen_moves_page(self, event) -> bool:
        """With a side button of the pen held (if the settings say so), the page follows the pen,
        as with the hand tool. Whether EVENT was that."""
        kind = event.type()
        # On release, button() is the one let go; only buttons() tells whether a side button is still held.
        held = bool((event.button() | event.buttons()) & self.SIDE) if kind != QEvent.Type.TabletRelease \
            else bool(event.buttons() & self.SIDE)
        if self._pen_pan is None:
            if kind != QEvent.Type.TabletPress or self.pen_button != "pan" or not held or self._drag is not None:
                return False
            # Se guardan el punto de partida y las barras: el desplazamiento se calcula siempre desde ahí,
            # y los redondeos no se acumulan.
            self._pen_pan = (event.position(), self.horizontalScrollBar().value(), self.verticalScrollBar().value())
            self.viewport().setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
            return True
        start, h, v = self._pen_pan
        moved = event.position() - start
        self.horizontalScrollBar().setValue(round(h - moved.x()))
        self.verticalScrollBar().setValue(round(v - moved.y()))
        if kind == QEvent.Type.TabletRelease and not held:
            self._pen_pan = None
            self.viewport().unsetCursor()
        return True

    def _end_pen_eraser(self):
        if self._pen_tool is not None and self._drag is None:
            self.mode, self._pen_tool = self._pen_tool, None

    def _ink_to(self, drag: dict, point: QPointF):
        """The stroke being drawn (DRAG), on to POINT (of its page)."""
        page = drag["page"]
        p = self._clamp(page, point)
        # Un punto nuevo solo si el lápiz se movió 1,5 píxeles de pantalla: al ir despacio no se llena
        # el trazo de puntos casi iguales.
        if math.hypot(p.x() - drag["points"][-1][0], p.y() - drag["points"][-1][1]) * self.zoom() >= 1.5:
            drag["points"].append((p.x(), p.y()))
            # 'at' keeps one pressure per point (None with a mouse), to cut the stroke by pressure later.
            drag.setdefault("at", []).append(self._pressure)
        paths = (tuple(drag["points"]),)
        new = self._new(self.mode, page.number, annots.frame(self.mode, paths, 1), paths)
        drag["item"].set_annotation(self._pressed(new, drag))

    @staticmethod
    def smoothed(points: list, at: list) -> tuple[list, list]:
        """POINTS (with the pressure AT each) made a little smoother: each, but the first and the last,
        moved toward its neighbours (a pen's hand trembles; the tablet records it)."""
        if len(points) < 4:
            return points, at
        # Weights 1-2-1 on each point and its neighbours. The pressures are returned untouched.
        out = [points[0]]
        for i in range(1, len(points) - 1):
            (ax, ay), (bx, by), (cx, cy) = points[i - 1], points[i], points[i + 1]
            out.append(((ax + 2 * bx + cx) / 4, (ay + 2 * by + cy) / 4))
        return out + [points[-1]], at

    # ----------------------------------------------------------------- polygons, one click at a time
    # (a double-click, Enter or a click on the first point ends it, Escape gives it up)

    def _polygon_click(self, page: PageItem, point: QPointF):
        p = self._clamp(page, point)
        # Redondeado a centésimas de punto, como las coordenadas que se guardan.
        here = (round(p.x(), 2), round(p.y(), 2))
        if self._poly is None:
            # El primer clic crea la vista previa con un lado de longitud cero; los siguientes añaden puntos.
            self._poly = {"page": page, "points": [here],
                          "item": self._preview(page, self._new(self.mode, page.number, (*here, *here),
                                                                ((here, here),)))}
            return
        first = QPointF(*self._poly["points"][0])
        # A click near the first point (within GRIP pixels) closes the shape, once it has three points.
        if len(self._poly["points"]) > 2 and math.hypot(p.x() - first.x(), p.y() - first.y()) * self.zoom() <= GRIP:
            self.finish_polygon()
            return
        self._poly["points"].append(here)
        self._show_polygon(here)

    def _show_polygon(self, rubber: tuple[float, float] | None):
        # El punto 'elástico' sigue al ratón y muestra cómo quedaría el lado siguiente.
        points = list(self._poly["points"]) + ([rubber] if rubber else [])
        paths = (tuple(points),)
        self._poly["item"].set_annotation(self._new(self.mode, self._poly["page"].number,
                                                    annots.frame(self.mode, paths, 1), paths))

    def finish_polygon(self):
        poly, self._poly = self._poly, None
        if poly is None:
            return
        self.scene().removeItem(poly["item"])
        # Dos clics en el mismo sitio dan puntos iguales seguidos; se deja uno.
        points = [p for i, p in enumerate(poly["points"]) if i == 0 or p != poly["points"][i - 1]]
        if len(points) >= (3 if self.mode == "polygon" else 2):
            paths = (tuple(points),)
            # The frame is computed once the factory has set the width, which the frame depends on.
            annotation = self._new(self.mode, poly["page"].number, (0, 0, 0, 0), paths)
            self.drawn.emit(dataclasses.replace(annotation, rect=annots.frame(annotation.kind, paths,
                                                                              annotation.width)))

    def cancel_polygon(self):
        if self._poly is not None:
            if self._poly["item"].scene() is not None:
                self.scene().removeItem(self._poly["item"])
            self._poly = None

    # ----------------------------------------------------------------- writing on the page

    def edit_text(self, annotation: Annotation, index: int = -1):
        """Write the text of ANNOTATION (a text box, a callout, a note or a caret; INDEX -1: a
        new one) where it is: the text_done signal gives it, with its text, when it is kept."""
        # Si había otro texto a medio escribir, se guarda antes de abrir este.
        self.commit_text()
        page = self.pages.get(annotation.page)
        # En la vista de una página, la anotación puede estar en otra: se va a ella primero.
        if page is None:
            self.go_to(annotation.page)
            page = self.pages.get(annotation.page)
            if page is None:
                return
        editor = TextEditor(self, page, rich=annotation.kind in TEXTUAL)
        if annotation.kind in TEXTUAL:
            # Text boxes are written inside their own box, with their font, colour and alignment.
            box = qrect(annotation.rect)
            pad = 2 + annotation.width
            editor.setFont(_font_for(self, annotation))
            editor.setDefaultTextColor(QColor(annotation.color))
            frame_rect = box
            fill = QColor(annotation.fill) if annotation.fill else QColor(255, 255, 255, 230)
        else:  # (a note, a caret: a field beside its icon)
            # En una página mucho mayor que el papel (un escaneo), el campo y su letra crecen en proporción: 10
            # puntos ahí no se leerían (véase annots.page_scale). Y nunca menores en la pantalla que con el zoom
            # al 100 %: el texto de una nota no se dibuja en la página, el campo es solo para escribirlo
            f = max(self.page_scale(annotation.page), 1 / (self.zoom() or 1))
            w, h = NOTE_EDITOR[0] * f, NOTE_EDITOR[1] * f
            r = page.rect()
            x = min(annotation.rect[2] + 4 * f, r.right() - w)
            y = min(max(annotation.rect[1], r.top()), r.bottom() - h)
            frame_rect, pad = QRectF(x, y, w, h), 4 * f
            editor.setFont(_font_for(self, dataclasses.replace(annotation, font_size=10 * f)))
            editor.setDefaultTextColor(QColor("black"))
            fill = QColor("#fffde7")
        frame = QGraphicsRectItem(frame_rect, page)
        pen = QPen(SELECTED, 1.5, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        frame.setPen(pen)
        frame.setBrush(fill)
        frame.setZValue(5)
        # El -4 compensa el margen interno (documentMargin) de QGraphicsTextItem, para que el texto quede
        # donde se dibujará después en la página.
        editor.setPos(frame_rect.left() + pad - 4, frame_rect.top() + pad - 4)
        editor.setTextWidth(max(frame_rect.width() - 2 * pad + 8, 20))
        option = editor.document().defaultTextOption()
        option.setAlignment({"center": Qt.AlignmentFlag.AlignHCenter, "right": Qt.AlignmentFlag.AlignRight}.get(
            annotation.align, Qt.AlignmentFlag.AlignLeft) if annotation.kind in TEXTUAL else Qt.AlignmentFlag.AlignLeft)
        option.setWrapMode(QTextOption.WrapMode.WordWrap)
        editor.document().setDefaultTextOption(option)
        if annotation.kind in TEXTUAL:
            from .richtext import prepare

            prepare(editor.document(), annotation, _font_for(self, annotation), margin=None)
        else:
            editor.setPlainText(annotation.contents)
        self._editor = {"item": editor, "frame": frame, "index": index, "annotation": annotation}
        if annotation.kind in TEXTUAL and index >= 0:  # (the box shows the text being written, not the old)
            for item in self.items_:
                if item.index == index:
                    item.setVisible(False)
        self.ensureVisible(frame, 40, 40)
        self.setFocus()
        editor.setFocus()
        # The cursor goes to the end, so typing continues the text already there.
        cursor = editor.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        editor.setTextCursor(cursor)

    def editing(self) -> bool:
        return self._editor is not None

    def commit_text(self, text: str | None = None, only: TextEditor | None = None):
        """Keep the text written (or TEXT, if given), and say so (text_done). ONLY: only if that is
        the editor of now (an editor that loses the focus keeps its own text, never another's)."""
        if self._editor is None or (only is not None and self._editor["item"] is not only):
            return
        editor, self._editor = self._editor, None
        written = editor["item"].toPlainText() if text is None else text
        before = editor["annotation"]
        # Un TEXT dado igual al que ya había conserva su formato enriquecido; uno distinto lo pierde.
        rich = before.rich if text is not None and text == before.contents else ""
        if text is None and before.kind in TEXTUAL:
            from .richtext import rich_of

            rich = rich_of(editor["item"].document(), before)
        self._drop_editor(editor)
        # Blank lines at the start and the end are dropped; spaces are kept.
        self.text_done.emit(editor["index"], dataclasses.replace(before, contents=written.strip("\n"), rich=rich))

    def cancel_text(self):
        editor, self._editor = self._editor, None
        if editor is not None:
            self._drop_editor(editor)

    def _drop_editor(self, editor: dict):
        for item in (editor["item"], editor["frame"]):
            if item.scene() is not None:
                self.scene().removeItem(item)
        # Se vuelven a mostrar todas, no solo la que se ocultó al editar.
        for item in self.items_:
            item.setVisible(True)

    # ----------------------------------------------------------------- the keys and the mouse

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self.mode == "signarea":  # (la firma, sin dibujar: cancelada)
            self.sign_drawn.emit(-1, None)
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape and self.text_sel:  # (the text selected, unselected)
            self.clear_text_selection()
            event.accept()
            return
        if self._editor is not None:
            super().keyPressEvent(event)
            return
        if self.space_pressed(event):  # (Space held: Hand, for a moment: see scrolling.py)
            event.accept()
            return
        key = event.key()
        # Con un polígono a medias, Enter y Escape son suyos; si no, las flechas mueven la selección.
        if self._poly is not None and key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.finish_polygon()
        elif self._poly is not None and key == Qt.Key.Key_Escape:
            self.cancel_polygon()
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down) \
                and any(i.chosen for i in self.items_):
            # Shift multiplies the step by ten; the steps are points of the page, not pixels.
            step = 10.0 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1.0
            dx = {Qt.Key.Key_Left: -step, Qt.Key.Key_Right: step}.get(key, 0.0)
            dy = {Qt.Key.Key_Up: -step, Qt.Key.Key_Down: step}.get(key, 0.0)
            self.nudged.emit(dx, dy)
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Right) and self.turns_pages(event):
            # La flecha izquierda, la página anterior; la derecha, la siguiente (con dos lado a lado, un par)
            self.go_to(self.neighbour(self.page, -1 if key == Qt.Key.Key_Left else 1))
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def turns_pages(self, event) -> bool:
        """Whether Left or Right (EVENT) turns the page: without modifiers, and while the pages fit across
        the view; zoomed in wider than it, they scroll sideways, as before."""
        if self.doc is None or event.modifiers() not in (Qt.KeyboardModifier.NoModifier,
                                                         Qt.KeyboardModifier.KeypadModifier):
            return False
        bar = self.horizontalScrollBar()
        return bar.maximum() <= bar.minimum()

    def keyReleaseEvent(self, event):
        if self.space_released(event):
            event.accept()
            return
        super().keyReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self._editor is not None:
            super().mouseDoubleClickEvent(event)
            return
        if self.mode == TEXT_SELECT and self.doc is not None and event.button() == Qt.MouseButton.LeftButton:
            page, point = self.locate(event.position().toPoint())
            if page is not None:
                self._drag = None
                self.text_select_double(page, point)
            event.accept()
            return
        if self.doc is None or self.mode == "hand" or event.button() != Qt.MouseButton.LeftButton:
            super().mouseDoubleClickEvent(event)
            return
        if self._poly is not None:
            self.finish_polygon()
            event.accept()
            return
        page, point = self.locate(event.position().toPoint())
        if not self.editable or page is None:
            return
        item, _ = self._hit(event.position().toPoint())
        if item is not None and self.mode in TEXT_TOOLS and item.annot.kind in MARKUP:
            item = None  # (with a markup tool, the word under a mark is marked too)
        self._remove_drag_items()
        self._drag = None
        self.double_clicked.emit(item.index if item else -1, page.number, (point.x(), point.y()))
        event.accept()

    def mousePressEvent(self, event):
        # A press on a link, with a tool that follows it (or Ctrl with Select): followed on the release, if the
        # mouse hasn't moved (see mouseReleaseEvent); otherwise the press does what the tool does.
        self._link_press = None
        if self._editor is None and self.autoscroll_press(event):  # (the middle button: see scrolling.py)
            event.accept()
            return
        if self.doc is not None and event.button() == Qt.MouseButton.LeftButton and self._editor is None:
            ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            if self.mode in FOLLOWED_BY and self.field_at is not None:
                # Un campo de formulario va antes que un enlace: se rellena (ver forming.py).
                page, point = self.locate(event.position().toPoint())
                hit = self.field_at(page.number, point.x(), point.y()) if page is not None else None
                if hit is not None:
                    self.field_clicked.emit(*hit)
                    event.accept()
                    return
            if self.mode in FOLLOWED_BY or (self.mode == "select" and ctrl):
                page, point = self.locate(event.position().toPoint())
                link = self.link_at(page.number, point) if page is not None else None
                if link is not None:
                    self._link_press = (event.position(), page.number, link)
                    if self.mode == "select":  # (Ctrl+click on a link: only the link, not a selection)
                        event.accept()
                        return
        if self._editor is not None:
            # Un clic dentro del editor es para él (mover el cursor, seleccionar); fuera, lo cierra.
            if self._editor["item"].sceneBoundingRect().contains(self.mapToScene(event.position().toPoint())):
                super().mousePressEvent(event)
                return
            self.commit_text()
        if self.mode in ("link", "signarea") and self.doc is not None and \
                event.button() == Qt.MouseButton.LeftButton:
            # La herramienta Enlace: un clic sobre un enlace lo cambia; un arrastre dibuja el área de uno nuevo.
            # (El área de una firma visible se dibuja igual.)
            page, point = self.locate(event.position().toPoint())
            if page is not None:
                link = self.link_at(page.number, point) if self.mode == "link" else None
                if link is not None and not link.get("in_text"):
                    self.link_edit.emit(page.number, link)
                    event.accept()
                    return
                start = self._clamp(page, point)
                band = QGraphicsRectItem(QRectF(start, start), page)
                pen = QPen(SELECTED, 1, Qt.PenStyle.DashLine)
                pen.setCosmetic(True)
                band.setPen(pen)
                band.setZValue(4)
                self._drag = {"kind": "linkarea" if self.mode == "link" else "signarea", "page": page,
                              "start": start, "item": band}
            event.accept()
            return
        if self.mode == "magnifier" and self.doc is not None and event.button() == Qt.MouseButton.LeftButton:
            # La lupa: mientras el botón está pulsado, un círculo con la página más cerca (magnifier.py).
            self._drag = {"kind": "magnifier"}
            self.magnify(event.position())
            event.accept()
            return
        if self.mode == "zoomarea" and self.doc is not None and event.button() == Qt.MouseButton.LeftButton:
            # Zoom to area: a frame dragged on a page, zoomed to on the release (a click zooms in, there).
            page, point = self.locate(event.position().toPoint())
            if page is not None:
                start = self._clamp(page, point)
                band = QGraphicsRectItem(QRectF(start, start), page)
                pen = QPen(SELECTED, 1, Qt.PenStyle.DashLine)
                pen.setCosmetic(True)
                band.setPen(pen)
                band.setZValue(4)
                self._drag = {"kind": "zoomarea", "page": page, "start": start, "item": band}
            event.accept()
            return
        if self.mode == TEXT_SELECT and self.doc is not None and event.button() == Qt.MouseButton.LeftButton:
            # (text is selected also in a document that can't be changed)
            self.setFocus()
            page, point = self.locate(event.position().toPoint())
            if page is None:
                self.clear_text_selection()
            else:
                self.text_select_press(event, page, point)
            event.accept()
            return
        if self.mode == "hand" or self.doc is None or event.button() != Qt.MouseButton.LeftButton \
                or not self.editable:
            super().mousePressEvent(event)
            return
        self.setFocus()
        pos = event.position().toPoint()
        page, point = self.locate(pos)
        # Un clic fuera de las páginas vacía la selección.
        if page is None:
            self.picked.emit([], False)
            return
        if self._poly is not None:
            # Mientras se hace un polígono, los clics en otra página se ignoran.
            if page is self._poly["page"]:
                self._polygon_click(page, point)
            event.accept()
            return
        if self.mode == "eraser":
            # The eraser's mark is a square of side 2 * ERASER pixels around the pointer, moved at each step.
            mark = QGraphicsRectItem(QRectF(), page)
            mark.setPen(QPen(SELECTED, 0))
            mark.setBrush(QBrush(QColor(42, 127, 255, 40)) if TRANSPARENT else QBrush())
            mark.setZValue(4)
            self._drag = {"kind": "erase", "page": page, "start": point, "centres": [], "marks": [mark]}
            self._erase_at(point)
            event.accept()
            return
        add = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        item, edges = self._hit(pos)
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        n = page.number
        # (the tool Redact marks text when the drag starts on it, and draws a box elsewhere, or with Ctrl)
        redact_text = self.mode == "redact" and item is None and not add and self.near_text(n, point)
        if self.mode in TEXT_TOOLS and (item is None or item.annot.kind in MARKUP or shift) or redact_text:
            # (over a mark, dragging marks text too; a click selects the mark)
            self._drag = {"kind": "text", "page": page, "start": point, "marks": [], "candidate": item}
            if item is None:
                self.picked.emit([], False)
            if not self.page_words(n) and item is None:
                self._drag = None
            event.accept()
            return
        if self.mode in DRAWN:  # (a pen draws, even over what is there: selecting is for Select)
            item = None
        if item is not None and not shift:
            # Clic sobre una anotación no seleccionada (o con Ctrl): solo cambia la selección. Tras picked la
            # ventana rehace los items, así que se busca el nuevo item con el mismo índice.
            if not item.chosen or add:
                self.picked.emit([item.index], add)
                item = next((i for i in self.items_ if i.index == item.index), None)
                if item is None or add:
                    self._drag = None
                    event.accept()
                    return
            if not item.movable():  # (selected, but it stays where it is)
                self._drag = None
                event.accept()
                return
            # The original is kept: every move is computed from the start of the drag, not step by step.
            self._drag = {"kind": "edit", "page": page, "start": point, "item": item, "edges": edges,
                          "original": item.annot, "moved": False}
            event.accept()
            return
        # Sobre el vacío: se deselecciona (salvo con Ctrl) y empieza una anotación nueva o un marco.
        if not add:
            self.picked.emit([], False)
        start = self._clamp(page, point)
        here = (start.x(), start.y())
        if self.mode == "select":
            # Seleccionar: un marco elástico que tomará lo que toque.
            band = self._dashed_frame(page, QRectF(start, start))
            band.setBrush(QColor(42, 127, 255, 30) if TRANSPARENT else QBrush())
            self._drag = {"kind": "band", "page": page, "start": start, "item": band, "add": add}
        elif self.mode in CLICKS:
            self._drag = {"kind": "click", "page": page, "start": start}
            if self.mode == "callout":
                self._drag["item"] = self._preview(page, self._new("callout", n, (*here, *here), ((here,),)))
            elif self.mode == "signature":
                # Un marco de trazos, como el de seleccionar: el ancho que tendrá la firma si se arrastra
                self._drag["item"] = self._dashed_frame(page, QRectF(start, start))
            elif self.mode in ("note", "attachment"):
                # Where its icon goes, as large as it is seen (NOTE_SIZE pixels): it doesn't follow a drag.
                side = NOTE_SIZE / (self.transform().m11() or 1)
                bounds = page.rect()
                x = max(min(start.x(), bounds.right() - NOTE_SIZE), bounds.left())
                y = max(min(start.y(), bounds.bottom() - NOTE_SIZE), bounds.top())
                self._drag["item"] = self._dashed_frame(page, QRectF(x, y, side, side))
                self._drag["fixed"] = True
        elif self.mode in BOXES:
            self._drag = {"kind": "draw", "page": page, "start": start,
                          "item": self._preview(page, self._new(self.mode, n, (*here, *here),
                                                                self._box_paths(here, here)))}
            self._drag["item"].outlined = True
        elif self.mode in LINES or self.mode in DRAWN:
            paths = ((here, here),)
            self._drag = {"kind": "line" if self.mode in LINES else "ink", "page": page, "start": start,
                          "item": self._preview(page, self._new(self.mode, n, (*here, *here), paths)),
                          "points": [here], "pressures": [self._pressure] if self._pressure is not None else [],
                          "at": [self._pressure]}  # (the pressure at each point: None without a pen)
        elif self.mode in POLYGONS:
            self._polygon_click(page, point)
            self._drag = None
        else:
            self._drag = None
        event.accept()

    def _dashed_frame(self, page: PageItem, rect: QRectF) -> QGraphicsRectItem:
        """A frame of dashes at RECT of PAGE, over everything, while the mouse is pressed: Select's, the size of a
        signature, where a note goes."""
        band = QGraphicsRectItem(rect, page)
        pen = QPen(SELECTED, 1, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        band.setPen(pen)
        band.setZValue(4)
        return band

    def _box_paths(self, a: tuple, b: tuple) -> tuple:
        """The points of a cloud drawn as a box from A to B (other boxes have none)."""
        if self.mode != "cloud":
            return ()
        x0, x1 = sorted((a[0], b[0]))
        y0, y1 = sorted((a[1], b[1]))
        return (((x0, y0), (x1, y0), (x1, y1), (x0, y1)),)

    def _callout_box(self, page: PageItem, tip: QPointF, at: QPointF) -> Rect:
        """The box of a callout that points at TIP, put at AT (a click: above and to the right of TIP)."""
        f = self.page_scale(page.number)
        w, h = (v * f for v in FREETEXT_SIZE)
        # Under 6 pixels of drag is a click: the box goes above and to the right, at a fixed distance.
        if math.hypot(at.x() - tip.x(), at.y() - tip.y()) * self.zoom() < 6:
            at = QPointF(tip.x() + 30 * f, tip.y() - 30 * f - h)
        r = page.rect()
        x = max(min(at.x(), r.right() - w), r.left())
        y = max(min(at.y(), r.bottom() - h), r.top())
        return round(x, 2), round(y, 2), round(x + w, 2), round(y + h, 2)

    def _erase_at(self, point: QPointF):
        drag = self._drag
        radius = ERASER / (self.zoom() or 1)
        # Entre dos posiciones del ratón, la goma pasa también por lo de en medio: un movimiento rápido salta más
        # que su radio, y dejaba sin borrar lo que cruzaba
        before = len(drag["centres"])
        if drag["centres"]:
            x0, y0 = drag["centres"][-1]
            steps = int(math.hypot(point.x() - x0, point.y() - y0) / radius)
            drag["centres"].extend((x0 + (point.x() - x0) * k / (steps + 1), y0 + (point.y() - y0) * k / (steps + 1))
                                   for k in range(1, steps + 1))
        drag["centres"].append((point.x(), point.y()))
        drag["marks"][0].setRect(QRectF(point.x() - radius, point.y() - radius, 2 * radius, 2 * radius))
        mine = [i for i in self.items_ if i.parentItem() is drag["page"] and not i.annot.locked
                and self.touchable(i.annot)]
        for item in mine:
            if item.annot.kind in DRAWN:
                # Los dibujos se recortan siempre desde su original con todos los centros recorridos, así que el
                # resultado no depende de cuántos movimientos hubo.
                original = drag.setdefault("ink", {}).setdefault(item.index, item.annot)
                left = erase_ink(original, drag["centres"], radius)
                if left is None:
                    item.setOpacity(0.2)
                else:
                    item.set_annotation(left)
            elif item.opacity() > 0.5 and any(item.hit(QPointF(x, y), radius) is not None
                                              for x, y in drag["centres"][before:]):
                item.setOpacity(0.2)  # (to go, once the button is let go)

    def mouseMoveEvent(self, event):
        if self.autoscroll_move(event):
            return
        drag = self._drag
        pos = event.position().toPoint()
        if self._poly is not None:
            # Con un polígono a medias, el lado elástico sigue al ratón aunque no haya arrastre.
            p = self._clamp(self._poly["page"], self._poly["page"].mapFromScene(self.mapToScene(pos)))
            self._show_polygon((round(p.x(), 2), round(p.y(), 2)))
        if drag is not None and drag["kind"] == "select-text":
            self.text_select_move(pos)
            return
        if drag is not None and drag["kind"] == "magnifier":
            self.magnify(event.position())
            return
        if drag is None and self.doc is not None and self.mode in FOLLOWED_BY + ("select",):
            page, point = self.locate(pos)
            link = self.link_at(page.number, point) if page is not None else None
            if link is not None:
                # (a hand, and where it goes; with Select, Ctrl+click follows it)
                self.viewport().setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                tip = self.link_target(link)
                if self.mode == "select":
                    tip = tr("{target} (Ctrl+click to follow)", target=tip)
                QToolTip.showText(event.globalPosition().toPoint(), tip, self.viewport())
                super().mouseMoveEvent(event)
                return
            QToolTip.hideText()
            if self.mode == "hand":
                self.viewport().setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        if drag is None and self.mode == TEXT_SELECT and self.doc is not None:
            page, point = self.locate(pos)
            over = page is not None and self.near_text(page.number, point)
            self.viewport().setCursor(QCursor(Qt.CursorShape.IBeamCursor if over else Qt.CursorShape.ArrowCursor))
            super().mouseMoveEvent(event)
            return
        if drag is None:
            if self.doc is not None and self.mode != "hand" and self.editable and self._editor is None:
                # Sin arrastre, solo se elige el cursor según lo que hay bajo el ratón.
                page, point = self.locate(pos)
                item, edges = self._hit(pos)
                if page is None:
                    shape = Qt.CursorShape.ArrowCursor
                elif self.mode == "eraser":
                    shape = Qt.CursorShape.CrossCursor
                elif item is not None and not (self.mode in TEXT_TOOLS and item.annot.kind in MARKUP):
                    shape = self._cursor(edges, item.movable())
                elif self.mode in TEXT_TOOLS:
                    shape = Qt.CursorShape.IBeamCursor if self.near_text(page.number, point) \
                        else Qt.CursorShape.ArrowCursor
                elif self.mode != "select":
                    shape = Qt.CursorShape.CrossCursor
                else:
                    shape = Qt.CursorShape.ArrowCursor
                self.viewport().setCursor(QCursor(shape))
            super().mouseMoveEvent(event)
            return
        page = drag["page"]
        # La posición del evento en coma flotante, no la entera de pos: con zoom alto los trazos
        # saldrían escalonados.
        point = page.mapFromScene(self.viewportTransform().inverted()[0].map(event.position()))  # (not rounded)
        kind = drag["kind"]
        n = page.number
        if kind == "text":
            self._show_text(self._text_selection(n, drag["start"], point))
        elif kind == "erase":
            self._erase_at(point)
        elif kind in ("band", "zoomarea", "linkarea", "signarea"):
            drag["item"].setRect(QRectF(drag["start"], self._clamp(page, point)).normalized())
        elif kind == "click" and drag.get("fixed"):  # (the frame of a note's icon stays where it was pressed)
            end = self._clamp(page, point)
            if self.mode == "note" and (end - drag["start"]).manhattanLength() * self.zoom() > 6:
                # Arrastrando: un recuadro de trazos, el de la ventana emergente que tendrá la nota
                box = QRectF(drag["start"], end).normalized()
                if "box" in drag:
                    drag["box"].setRect(box)
                else:
                    drag["box"] = self._dashed_frame(page, box)
        elif kind == "click" and isinstance(drag.get("item"), QGraphicsRectItem):  # (the frame of a signature)
            drag["item"].setRect(QRectF(drag["start"], self._clamp(page, point)).normalized())
        elif kind == "click" and "item" in drag:  # (a callout: its box follows the mouse)
            tip = drag["start"]
            box = self._callout_box(page, tip, self._clamp(page, point))
            drag["item"].set_annotation(self._new("callout", n, box, (((tip.x(), tip.y()),),)))
        elif kind == "draw":
            # A box can be dragged in any direction; normalized() puts its corners in order.
            r = QRectF(drag["start"], self._clamp(page, point)).normalized()
            a, b = (r.left(), r.top()), (r.right(), r.bottom())
            drag["item"].set_annotation(self._new(self.mode, n, (*a, *b), self._box_paths(a, b)))
        elif kind == "ink":
            self._ink_to(drag, point)
        elif kind == "line":
            p = self._clamp(page, point)
            drag["points"] = [drag["points"][0], (p.x(), p.y())]
            paths = (tuple(drag["points"]),)
            drag["item"].set_annotation(self._new(self.mode, n, annots.frame(self.mode, paths, 1), paths))
        elif kind == "edit":
            new = self._edited(drag, point)
            if new is not None:
                drag["item"].set_annotation(new)
                drag["moved"] = True
        event.accept()

    WRITING_PAUSE = 1.5  # seconds: a stroke made sooner after the one before, near it, is part of the same drawing
    WRITING_NEAR = 40.0  # points: how near

    def _written(self, stroke: Annotation) -> bool:
        """Add STROKE (a drawing of one stroke, just made) to the drawing made just before, if it was
        made soon before and near it, with the same tool and look: so that a word, or a line, written
        stroke by stroke is one drawing. Whether it was."""
        last, when = self._last_drawn or (None, 0.0)
        if last is None or time.monotonic() - when > self.WRITING_PAUSE or last.page != stroke.page \
                or (last.kind, last.color, last.opacity, last.layer) != (stroke.kind, stroke.color, stroke.opacity,
                                                                           stroke.layer):
            return False
        # The previous drawing must still be shown: it may have been undone or deleted meanwhile.
        index = next((i for i, a in self._shown_items if a == last), None)
        x, y = stroke.paths[0][0]
        x0, y0, x1, y1 = last.rect
        near = self.WRITING_NEAR
        # Basta con que el primer punto del trazo caiga cerca del marco del dibujo anterior.
        if index is None or not (x0 - near <= x <= x1 + near and y0 - near <= y <= y1 + near):
            return False
        paths = last.paths + stroke.paths
        joined = dataclasses.replace(last, paths=paths, rect=annots.frame(last.kind, paths, last.width))
        self._last_drawn = (joined, time.monotonic())
        self.edited.emit(index, joined)
        return True

    LEVELS = 5  # (of the pressure of a pen, along a stroke: each a width of its own)

    @classmethod
    def _pieces(cls, a: Annotation, points: tuple, at: list) -> list[Annotation]:
        """The stroke A (through POINTS, with the pressure AT each one) cut where the pressure of the
        pen goes to another level: a drawing for each piece, as wide as its pressure, all one group.
        [] if the pressure stays at one level, or there is no pen."""
        if len(at) != len(points) or any(p is None for p in at):
            return []
        # Pressure 0..1 falls into LEVELS bands; a pressure of 1.0 goes into the top band, not a band of its own.
        levels = [min(int(max(p, 0) * cls.LEVELS), cls.LEVELS - 1) for p in at]
        runs: list[list[int]] = []  # (the points of each piece, by index)
        for i, level in enumerate(levels):
            if runs and levels[runs[-1][0]] == level:
                runs[-1].append(i)
            else:
                runs.append([i])
        merged: list[list[int]] = []
        for run in runs:  # (a piece of one or two points goes with the one before)
            if merged and len(run) < 3:
                merged[-1] += run
            else:
                merged.append(run)
        if len(merged) < 2:
            return []
        # Todas las piezas comparten grupo, para que se seleccionen y se muevan juntas.
        group = uuid.uuid4().hex[:12]
        out = []
        for k, run in enumerate(merged):
            idx = ([merged[k - 1][-1]] if k else []) + run  # (each starts where the one before ends)
            mean = sum(at[i] for i in run) / len(run)
            # El grosor va del 40 % (presión 0) al 160 % (presión 1) del grosor del lápiz, nunca menos de 0,25 pt.
            width = round(max(a.width * (0.4 + 1.2 * mean), 0.25), 2)
            path = tuple(points[i] for i in idx)
            b = dataclasses.replace(a, paths=(path,), width=width, group=group)
            out.append(dataclasses.replace(b, rect=annots.frame(b.kind, b.paths, width)))
        return out

    @staticmethod
    def _pressed(a: Annotation, drag: dict) -> Annotation:
        """A drawing as wide as the pressure of the tablet's pen says (if one draws it)."""
        pressures = [p for p in drag.get("pressures", []) if p is not None and p > 0]
        if not pressures:
            return a
        mean = sum(pressures) / len(pressures)
        # TODO: la fórmula del grosor (0.4 + 1.2 * presión) se repite en _pieces; una función común
        # evitaría que se separen.
        return dataclasses.replace(a, width=round(max(a.width * (0.4 + 1.2 * mean), 0.25), 2))

    def _edited(self, drag: dict, point: QPointF) -> Annotation | None:
        """The annotation dragged, as it is with the mouse at POINT."""
        a: Annotation = drag["original"]
        page = drag["page"]
        edges = drag["edges"]
        if a.kind in MARKUP or a.locked:  # (they belong to their text, or are locked)
            return None
        if edges.startswith("v"):
            # Dragging a point moves only that point; the rest of the shape stays where it is.
            p = self._clamp(page, point)
            return annots.with_vertex(a, int(edges[1:]), (p.x(), p.y()))
        r = qrect(a.rect)
        bounds = page.rect()
        if not edges:
            # Mover: el marco original se traslada por el desplazamiento total desde el inicio del arrastre.
            r.translate(point - drag["start"])
            # (kept on the page)
            dx = max(bounds.left() - r.left(), 0) + min(bounds.right() - r.right(), 0)
            dy = max(bounds.top() - r.top(), 0) + min(bounds.bottom() - r.bottom(), 0)
            r.translate(dx, dy)
            if a.popup:  # (a note: its pop-up window goes with it, see annots.moved)
                return annots.moved(a, r.left() - a.rect[0], r.top() - a.rect[1])
        else:
            p = self._clamp(page, point)
            # Redimensionar: solo se mueven los bordes agarrados, sin salir de la página.
            if "l" in edges:
                r.setLeft(p.x())
            if "r" in edges:
                r.setRight(p.x())
            if "t" in edges:
                r.setTop(p.y())
            if "b" in edges:
                r.setBottom(p.y())
            r = r.normalized()
            if r.width() < MIN_SIZE or r.height() < MIN_SIZE:
                return None
            if a.kind == "stamp" and a.image:  # (its picture keeps its proportions)
                # The width wins: the height follows it, to keep the picture's proportions.
                ratio = (a.rect[2] - a.rect[0]) / max(a.rect[3] - a.rect[1], 0.01)
                r.setHeight(r.width() / ratio)
        rect = (r.left(), r.top(), r.right(), r.bottom())
        if a.kind == "callout":  # (its box moves alone: it still points at the same place)
            return dataclasses.replace(a, rect=tuple(round(v, 2) for v in rect))
        # annots.fitted estira también el contenido (trazos, puntos) al marco nuevo.
        return annots.fitted(a, rect)

    def mouseReleaseEvent(self, event):
        if self.autoscroll_release(event):
            return
        pressed, self._link_press = self._link_press, None
        if pressed is not None and (event.position() - pressed[0]).manhattanLength() < 4:
            self._drag = None
            super().mouseReleaseEvent(event)
            self.link_clicked.emit(pressed[1], pressed[2])
            return
        drag, self._drag = self._drag, None
        if drag is not None and drag["kind"] == "magnifier":
            if self._lens is not None:
                self._lens.hide()
            return
        if drag is None or event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        page = drag["page"]
        point = page.mapFromScene(self.mapToScene(event.position().toPoint()))
        # Más de 3 píxeles de recorrido es un arrastre; menos, un clic.
        moved = (point - drag["start"]).manhattanLength() * self.zoom() > 3
        kind = drag["kind"]
        n = page.number
        if kind == "select-text":
            self.text_select_release(drag, moved)
            return
        if kind in ("linkarea", "signarea"):
            r = drag["item"].rect()
            self.scene().removeItem(drag["item"])
            if moved and r.width() > 2 and r.height() > 2:
                (self.link_drawn if kind == "linkarea" else self.sign_drawn).emit(
                    n, (r.left(), r.top(), r.right(), r.bottom()))
            return
        if kind == "zoomarea":
            r = drag["item"].rect()
            self.scene().removeItem(drag["item"])
            if moved and r.width() > 2 and r.height() > 2:
                self.zoom_to(page, r)
            else:  # (a click: in, twice as near, around it)
                self.set_zoom(self.zoom() * 2)
                self.centerOn(page.mapToScene(point))
            return
        if kind == "text":
            rects = self._text_selection(n, drag["start"], point) if moved else []
            for item in drag["marks"]:
                self.scene().removeItem(item)
            if rects:
                self.text_chosen.emit(n, rects)
            # A click without a drag on a mark selects it instead of marking text.
            elif drag["candidate"] is not None:
                self.picked.emit([drag["candidate"].index], False)
        elif kind == "erase":
            for mark in drag["marks"]:
                self.scene().removeItem(mark)
            radius = ERASER / (self.zoom() or 1)
            changes: dict = {}
            # Al soltar se calculan los cambios definitivos: dibujos recortados (None si no queda nada) y las
            # demás anotaciones atenuadas, que se borran.
            for item in self.items_:
                if item.annot.locked or item.parentItem() is not page or not self.touchable(item.annot):
                    continue
                if item.annot.kind in DRAWN and item.index in drag.get("ink", {}):
                    left = erase_ink(drag["ink"][item.index], drag["centres"], radius)
                    # Si la goma pasó cerca sin tocar el dibujo, no se informa ningún cambio.
                    if left != drag["ink"][item.index]:
                        changes[item.index] = left
                elif item.opacity() < 0.5:
                    changes[item.index] = None
            if changes:
                self.erased.emit(changes)
        elif kind == "band":
            r = drag["item"].rect()
            self.scene().removeItem(drag["item"])
            if moved:
                # The band takes what it touches, not only what lies wholly inside it.
                inside = [i.index for i in self.items_ if i.parentItem() is page and r.intersects(i.frame())
                          and self.touchable(i.annot)]
                self.picked.emit(inside, drag["add"])
        elif kind == "click":
            self._clicked(drag, point)
        elif kind == "draw":
            annotation = drag["item"].annot
            self.scene().removeItem(drag["item"])
            r = qrect(annotation.rect)
            if self.mode in ("freetext", "typewriter") and (r.width() < MIN_SIZE * 4 or r.height() < MIN_SIZE * 4):
                # A click (or a tiny drag) with a text box tool makes a box of the usual size at the click.
                w, h = (v * self.page_scale(n) for v in FREETEXT_SIZE)
                bounds = page.rect()
                x = max(min(drag["start"].x(), bounds.right() - w), bounds.left())
                y = max(min(drag["start"].y(), bounds.bottom() - h), bounds.top())
                self.drawn.emit(self._new(self.mode, n, (round(x, 2), round(y, 2), round(x + w, 2),
                                                          round(y + h, 2))))
            elif r.width() >= MIN_SIZE and r.height() >= MIN_SIZE:
                rounded = tuple(round(v, 2) for v in (r.left(), r.top(), r.right(), r.bottom()))
                paths = self._box_paths(rounded[:2], rounded[2:])
                annotation = self._new(self.mode, n, rounded, paths)
                if paths:
                    # Una nube toma su marco de sus puntos y su grosor: las ondas salen un poco de la caja arrastrada.
                    annotation = dataclasses.replace(annotation, rect=annots.frame(self.mode, paths, annotation.width))
                self.drawn.emit(annotation)
        elif kind in ("line", "ink"):
            self.scene().removeItem(drag["item"])
            raw, at = drag["points"], drag.get("at", [])
            # Solo se suavizan los trazos del lápiz de una tableta, que registra el temblor de la mano.
            if kind == "ink" and drag.get("tablet"):
                raw, at = self.smoothed(raw, at)
            points = tuple((round(x, 2), round(y, 2)) for x, y in raw)
            if kind == "line":
                # The end of a line is taken from the release, not from the last move, which may lag behind.
                p = self._clamp(page, point)
                points = (points[0], (round(p.x(), 2), round(p.y(), 2)))
            length = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:]))
            if kind == "ink" and length < MIN_SIZE:  # (a tap with the pen: a dot, as on an i, or a full stop)
                points, at = points[:1], at[:1]
                length = MIN_SIZE
            if length >= MIN_SIZE:
                base = self._new(self.mode, n, (0, 0, 0, 0), (points,))
                # Con presión 'along', el trazo se corta en piezas de distinto grosor; si sale una sola, va entero.
                pieces = self._pieces(base, points, at) if kind == "ink" and self.pen_pressure == "along" else []
                if len(pieces) > 1:
                    self.drawn_many.emit(pieces)
                    # A stroke cut into pieces is never joined to the next one: _written joins single drawings only.
                    self._last_drawn = None
                else:
                    annotation = self._pressed(base, drag)
                    annotation = dataclasses.replace(annotation, rect=annots.frame(
                        annotation.kind, annotation.paths, annotation.width))
                    if kind != "ink" or not self._written(annotation):
                        self.drawn.emit(annotation)
                        self._last_drawn = (annotation, time.monotonic()) if kind == "ink" else None
        elif kind == "edit":
            if drag["moved"]:
                # Un clic sin mover sobre una anotación seleccionada no cuenta como edición (no llega al deshacer).
                self.edited.emit(drag["item"].index, drag["item"].annot)
        event.accept()

    def _clicked(self, drag: dict, point: QPointF):
        """A click (or a drag) with a tool of CLICKS: a note, a caret or a stamp there, or a callout."""
        page = drag["page"]
        n = page.number
        start = drag["start"]
        bounds = page.rect()
        if drag.get("fixed"):  # (the frame of a note: the note takes its place)
            self.scene().removeItem(drag["item"])
        popup = None
        if "box" in drag:  # (dragged with Note: its pop-up window, where the box was)
            r = drag["box"].rect()
            self.scene().removeItem(drag["box"])
            if r.width() >= MIN_SIZE and r.height() >= MIN_SIZE:
                popup = tuple(round(v, 2) for v in (r.left(), r.top(), r.right(), r.bottom()))
        if self.mode == "callout":
            self.scene().removeItem(drag["item"])
            box = self._callout_box(page, start, self._clamp(page, point))
            self.drawn.emit(self._new("callout", n, box, (((round(start.x(), 2), round(start.y(), 2)),),)))
            return
        if self.mode == "signature":
            if "item" in drag:
                self.scene().removeItem(drag["item"])
            end = self._clamp(page, point)
            if (end - start).manhattanLength() * self.zoom() > 6:  # (dragged: as wide as that, its height its own)
                r = QRectF(start, end).normalized()
                self.drawn.emit(self._new("signature", n, (r.left(), r.top(), r.right(), r.top())))
            else:  # (its top left corner where the click was: of its usual width, which the window knows)
                self.drawn.emit(self._new("signature", n, (start.x(), start.y(), start.x(), start.y())))
            return
        if self.mode == "mark":  # (a check mark, a cross...: centred where the click was)
            s = MARK_SIZE * self.page_scale(n) / 2
            x = max(min(start.x(), bounds.right() - s), bounds.left() + s)
            y = max(min(start.y(), bounds.bottom() - s), bounds.top() + s)
            self.drawn.emit(self._new("mark", n, (round(x - s, 2), round(y - s, 2), round(x + s, 2), round(y + s, 2))))
            return
        if self.mode == "stamp":
            end = self._clamp(page, point)
            if (end - start).manhattanLength() * self.zoom() > 6:  # (dragged: as wide as that)
                r = QRectF(start, end).normalized()
                # Zero height on purpose: the window sets it from the stamp's proportions.
                self.drawn.emit(self._new("stamp", n, (r.left(), r.top(), r.right(), r.top())))
            else:  # (a click: of its usual size, there; the window knows it)
                self.drawn.emit(self._new("stamp", n, (start.x(), start.y(), start.x(), start.y())))
            return
        # La marca de inserción gira con la página: shown_size da su tamaño tal como se ve si está rotada.
        w, h = (NOTE_SIZE, NOTE_SIZE) if self.mode in ("note", "attachment") else \
            annots.shown_size(self.doc[n].rotation if self.doc is not None else 0, CARET_SIZE)
        if self.mode == "caret":  # (the caret's point where the click was)
            x, y = start.x() - w / 2, start.y() - h
        else:
            x, y = start.x(), start.y()
        x = max(min(x, bounds.right() - w), bounds.left())
        y = max(min(y, bounds.bottom() - h), bounds.top())
        made = self._new(self.mode, n, (round(x, 2), round(y, 2), round(x + w, 2), round(y + h, 2)))
        self.drawn.emit(dataclasses.replace(made, popup=popup) if popup else made)

    def page_scale(self, number: int) -> float:
        """How much larger than paper page NUMBER is (annots.page_scale): new annotations are made larger on it."""
        if self.doc is None or not 0 <= number < self.doc.page_count:
            return 1.0
        r = self.doc[number].rect
        return annots.page_scale(r.width, r.height)

    def word_at(self, number: int, point: QPointF) -> str:
        """The word under POINT (on page NUMBER), or ''."""
        if self.doc is None:
            return ""
        page = self.doc[number]
        # No usa page_words: esa caché guarda los rectángulos de las palabras, pero no su texto.
        for w in page.get_text("words", sort=False):
            # Las palabras vienen en coordenadas sin rotar; rotation_matrix las lleva a la página tal como se ve.
            r = pymupdf.Rect(w[:4]) * page.rotation_matrix
            if r.normalize().contains(pymupdf.Point(point.x(), point.y())):
                return w[4]
        return ""

    # ----------------------------------------------------------------- the places found by the find bar

    _found_of = None
    _found_pages: frozenset = frozenset()
    _found_current = None
    _found_items: list = []
    _found_drawn: set = set()

    def set_found(self, rects_of, pages, current: tuple[int, list[Rect]] | None):
        """Highlight the places found by the find bar: RECTS_OF(page) gives the rectangles of those on a page,
        PAGES which pages have some, CURRENT (page, rectangles) the one shown, more strongly (None: none). Only
        the pages in view, and near it, are highlighted; the others as they come into view."""
        self._found_of, self._found_pages, self._found_current = rects_of, frozenset(pages or ()), current
        self._place_found()

    def add_found(self, pages):
        """PAGES have places found too (counted after the others): highlighted, if they are in view."""
        self._found_pages = self._found_pages | frozenset(pages)
        self._more_found()

    def _place_found(self):
        for item in self._found_items:
            try:
                if item.scene() is not None:
                    item.scene().removeItem(item)
            except RuntimeError:  # (ya borrado con la escena)
                pass
        self._found_items, self._found_drawn = [], set()
        current = self._found_current
        if current is not None and current[0] in self.pages:
            self._found_items.append(self._found_item(current[0], current[1], True))
        self._more_found()

    def _found_item(self, number: int, rects, current: bool) -> QGraphicsPathItem:
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.WindingFill)  # (dos rectángulos que se tocan no se anulan)
        for r in rects:
            path.addRect(qrect(r).adjusted(-1, -1, 1, 1))
        item = QGraphicsPathItem(path, self.pages[number])
        if current:
            pen = QPen(QColor(230, 110, 0), 2)
            pen.setCosmetic(True)
            item.setPen(pen)
            item.setBrush(QBrush(QColor(255, 150, 0, 110)))
            item.setZValue(4)
        else:
            item.setPen(QPen(Qt.PenStyle.NoPen))
            item.setBrush(QBrush(QColor(255, 225, 0, 100)))
            item.setZValue(3)
        return item

    def _more_found(self):
        """The highlights of the pages that came into view (each page once, until the next search)."""
        if self._found_of is None or not self._found_pages or not self.pages:
            return
        for number in self.visible_pages():
            if number in self._found_pages and number not in self._found_drawn and number in self.pages:
                self._found_drawn.add(number)
                self._found_items.append(self._found_item(number, self._found_of(number), False))

    def flash(self, number: int, rect: Rect):
        """Bring RECT of page NUMBER into view, and show it for a moment."""
        self.go_to(number, rect)
        page = self.pages.get(number)
        if page is None:
            return
        pen = QPen(QColor(230, 120, 0), 2)
        pen.setCosmetic(True)
        item = QGraphicsRectItem(qrect(rect).adjusted(-3, -3, 3, 3), page)
        item.setPen(pen)
        item.setBrush(QBrush(QColor(255, 200, 0, 90)))
        item.setZValue(4)

        def remove():
            try:
                if item.scene() is not None:
                    item.scene().removeItem(item)
            except RuntimeError:  # (the page was laid out again meanwhile: the item is gone)
                pass

        QTimer.singleShot(900, remove)


def _font_for(canvas: PageCanvas, a: Annotation):
    """The font of A's text, for the editor on the page (in the page's points)."""
    # A painter on a 1x1 pixmap only because _font needs one; both are thrown away at once.
    pixmap = QPixmap(1, 1)
    painter = QPainter(pixmap)
    font = _font(painter, a.font, a.font_size)
    painter.end()
    return font

