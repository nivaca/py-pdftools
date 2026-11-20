"""Annotations drawn with Qt, as a viewer would show them, on the page and on
its thumbnail. The painter works in points of the page as it is shown."""

from __future__ import annotations

import math

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPolygonF, QTextDocument

from ..annotate.annots import STAMPS, Annotation, anchor, smooth_segments
from ..core.interface import tr

FAMILIES = {"helv": "Helvetica", "tiro": "Times", "cour": "Courier"}
_IMAGES: dict[int, QImage] = {}  # (id of the bytes of a stamp's image) -> the image, made once
_RICH: dict[tuple, QTextDocument] = {}  # (the look of a text box with rich text) -> its text laid out, made once


def qrect(r) -> QRectF:
    return QRectF(QPointF(r[0], r[1]), QPointF(r[2], r[3])).normalized()


def _pen(color: str, width: float, dashed: bool = False) -> QPen:
    pen = QPen(QColor(color), width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap if not dashed else Qt.PenCapStyle.FlatCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    if dashed:
        pen.setDashPattern([3 / max(width, 0.1), 3 / max(width, 0.1)])  # (3 points on, 3 off, as written)
    return pen


def _font(p: QPainter, family: str, size: float) -> QFont:
    font = QFont(FAMILIES.get(family, "Helvetica"))
    font.setStyleHint({"tiro": QFont.StyleHint.Serif, "cour": QFont.StyleHint.Monospace}.get(
        family, QFont.StyleHint.SansSerif))
    # (Qt's points are of the screen, at its dots per inch; the painter's units are the page's points)
    dpi = p.device().logicalDpiY() if p.device() is not None else 72
    font.setPointSizeF(max(size, 1) * 72 / (dpi or 72))
    return font


def _rich_document(p: QPainter, a: Annotation, width: float) -> QTextDocument:
    """The rich text of A laid out WIDTH wide, for painting it with P."""
    from .richtext import prepare

    dpi = p.device().logicalDpiY() if p.device() is not None else 72
    key = (a.rich, a.color, a.font, a.font_size, a.align, round(width, 1), dpi)
    doc = _RICH.get(key)
    if doc is None:
        if len(_RICH) > 200:
            _RICH.clear()
        doc = _RICH[key] = QTextDocument()
        if p.device() is not None:
            doc.documentLayout().setPaintDevice(p.device())
        prepare(doc, a, _font(p, a.font, a.font_size))
        doc.setTextWidth(width)
    return doc


def line_end(p: QPainter, tip: QPointF, start: QPointF, style: str, width: float, color: QColor) -> None:
    """The end STYLE (see annots.ENDS) of a line that goes from START to TIP."""
    if style == "None" or tip == start:
        return
    angle = math.atan2(tip.y() - start.y(), tip.x() - start.x())
    size = max(6.0, width * 3 + 4)
    reverse = style.startswith("R")
    if reverse:
        style = style[1:]
        angle += math.pi

    def at(length: float, turn: float) -> QPointF:
        return tip + QPointF(length * math.cos(angle + turn), length * math.sin(angle + turn))

    p.save()
    p.setPen(_pen(color.name(), width))
    if style in ("OpenArrow", "ClosedArrow"):
        base = at(size, 0) if reverse else tip
        wings = [base + QPointF(size * math.cos(angle + s), size * math.sin(angle + s)) for s in (2.6, -2.6)]
        if style == "OpenArrow":
            p.drawPolyline(QPolygonF([wings[0], base, wings[1]]))
        else:  # (outlined, as MuPDF draws it)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPolygon(QPolygonF([wings[0], base, wings[1]]))
    elif style in ("Circle", "Square", "Diamond"):
        r = size / 2
        p.setBrush(Qt.BrushStyle.NoBrush)
        if style == "Circle":
            p.drawEllipse(tip, r, r)
        elif style == "Square":
            p.drawRect(QRectF(tip.x() - r, tip.y() - r, 2 * r, 2 * r))
        else:
            p.drawPolygon(QPolygonF([tip + QPointF(r, 0), tip + QPointF(0, r), tip + QPointF(-r, 0),
                                     tip + QPointF(0, -r)]))
    elif style in ("Butt", "Slash"):
        turn = math.pi / 2 if style == "Butt" else math.pi / 3
        p.drawLine(at(size / 2, turn), at(size / 2, turn + math.pi))
    p.restore()


def cloud_path(points: list[QPointF], width: float) -> QPainterPath:
    """A cloudy border along the polygon of POINTS: little arcs bulging outwards."""
    area = sum(a.x() * b.y() - b.x() * a.y() for a, b in zip(points, points[1:] + points[:1]))
    side = 1 if area > 0 else -1  # (outwards, as the polygon turns)
    step = 8 + 2 * width
    path = QPainterPath(points[0])
    for a, b in zip(points, points[1:] + points[:1]):
        length = math.hypot(b.x() - a.x(), b.y() - a.y())
        n = max(1, round(length / step))
        nx, ny = (b.y() - a.y()) / (length or 1), -(b.x() - a.x()) / (length or 1)
        for i in range(n):
            s, e = a + (b - a) * (i / n), a + (b - a) * ((i + 1) / n)
            mid = (s + e) / 2
            bulge = QPointF(nx, ny) * (-side * step * 0.6)
            path.quadTo(mid + bulge, e)
    return path


def stamp_image(a: Annotation) -> QImage | None:
    if not a.image:
        return None
    key = hash(a.image)
    image = _IMAGES.get(key)
    if image is None:
        image = QImage.fromData(a.image)
        if len(_IMAGES) > 200:
            _IMAGES.clear()
        _IMAGES[key] = image
    return image if not image.isNull() else None


def _note(p: QPainter, r: QRectF, color: QColor, icon: str) -> None:
    p.setPen(QPen(color.darker(170), max(r.width() / 16, 0.5)))
    p.setBrush(color)
    if icon == "Comment":
        bubble = QPainterPath()
        bubble.addRoundedRect(r.adjusted(1, 1, -1, -r.height() * 0.3), r.width() / 6, r.width() / 6)
        tail = QPolygonF([QPointF(r.left() + r.width() * 0.3, r.bottom() - r.height() * 0.32),
                          QPointF(r.left() + r.width() * 0.25, r.bottom() - 1),
                          QPointF(r.left() + r.width() * 0.5, r.bottom() - r.height() * 0.32)])
        tail_path = QPainterPath()
        tail_path.addPolygon(tail)
        p.drawPath(bubble.united(tail_path))
        return
    p.drawRoundedRect(r.adjusted(1, 1, -1, -1), r.width() / 8, r.width() / 8)
    glyph = {"Help": "?", "Key": "⚷", "Insert": "‸", "Paragraph": "¶", "NewParagraph": "¶"}.get(icon)
    p.setPen(QPen(color.darker(220), max(r.width() / 20, 0.4)))
    if glyph:
        font = QFont("Helvetica")
        font.setPixelSize(max(int(r.height() * 0.7), 1))
        font.setBold(True)
        p.setFont(font)
        p.drawText(r, int(Qt.AlignmentFlag.AlignCenter), glyph)
        return
    for i in range(3):
        y = r.top() + r.height() * (0.35 + 0.18 * i)
        p.drawLine(QLineF(r.left() + r.width() * 0.25, y, r.right() - r.width() * 0.25, y))


def paint(p: QPainter, a: Annotation, thumbnail: bool = False) -> None:
    """Draw A with P. THUMBNAIL: small, so lines are kept visible and texts left out."""
    if a.kind == "other":  # (a link, an attached file...: the page shows it, as it is)
        return
    p.save()
    p.setOpacity(p.opacity() * a.opacity)
    color = QColor(a.color)
    if a.kind == "highlight":
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
        for q in a.quads:
            p.fillRect(qrect(q), color)
    elif a.kind in ("underline", "strikeout", "squiggly"):
        for q in a.quads:
            r = qrect(q)
            width = max(r.height() / 14, 0.6)
            p.setPen(_pen(a.color, width))
            if a.kind == "strikeout":
                p.drawLine(QLineF(r.left(), r.center().y(), r.right(), r.center().y()))
            elif a.kind == "underline":
                y = r.bottom() - width
                p.drawLine(QLineF(r.left(), y, r.right(), y))
            else:
                step = max(r.height() / 6, 1.5)
                path = QPainterPath(QPointF(r.left(), r.bottom() - step))
                x, up = r.left(), False
                while x < r.right():
                    x = min(x + step, r.right())
                    path.lineTo(x, r.bottom() - (step if up else 0))
                    up = not up
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(path)
    elif a.kind == "caret":
        r = qrect(a.rect)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        path = QPainterPath(QPointF(r.left(), r.bottom()))
        path.quadTo(QPointF(r.center().x(), r.bottom()), QPointF(r.center().x(), r.top()))
        path.quadTo(QPointF(r.center().x(), r.bottom()), QPointF(r.right(), r.bottom()))
        path.closeSubpath()
        p.drawPath(path)
    elif a.kind == "note":
        _note(p, qrect(a.rect), color, a.icon)
    elif a.kind == "attachment":  # (a paperclip)
        r = qrect(a.rect)
        p.setPen(_pen(a.color, max(r.width() / 10, 1)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        clip = QPainterPath()
        x, y, w, h = r.left(), r.top(), r.width(), r.height()
        clip.moveTo(x + w * 0.62, y + h * 0.30)
        clip.lineTo(x + w * 0.62, y + h * 0.72)
        clip.arcTo(QRectF(x + w * 0.30, y + h * 0.60, w * 0.32, h * 0.30), 0, -180)
        clip.lineTo(x + w * 0.30, y + h * 0.22)
        clip.arcTo(QRectF(x + w * 0.30, y + h * 0.05, w * 0.46, h * 0.34), 180, -180)
        clip.lineTo(x + w * 0.76, y + h * 0.70)
        p.drawPath(clip)
    elif a.kind in ("freetext", "callout"):
        r = qrect(a.rect)
        if a.kind == "callout" and a.paths:
            tip = QPointF(*a.paths[0][0])
            start = QPointF(*anchor(a.rect, a.paths[0][0]))
            p.setPen(_pen(a.border or a.color, max(a.width, 0.75), a.dashed))
            p.drawLine(start, tip)
            line_end(p, tip, start, a.ends[1], max(a.width, 0.75), QColor(a.border or a.color))
        p.setPen(_pen(a.border or a.color, a.width, a.dashed) if a.width > 0 else Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(a.fill)) if a.fill else Qt.BrushStyle.NoBrush)
        p.drawRect(r)
        if thumbnail:
            p.setPen(QPen(color, 0))
            for i in range(1, 4):
                y = r.top() + r.height() * i / 4
                if y < r.bottom():
                    p.drawLine(QLineF(r.left() + 2, y, r.right() - 2, y))
        elif a.rich:
            pad = 2 + a.width
            p.save()
            p.translate(r.left() + pad, r.top() + pad)
            box = QRectF(0, 0, r.width() - 2 * pad, r.height() - 2 * pad)
            p.setClipRect(box)
            _rich_document(p, a, box.width()).drawContents(p, box)
            p.restore()
        else:
            p.setFont(_font(p, a.font, a.font_size))
            p.setPen(color)
            align = {"center": Qt.AlignmentFlag.AlignHCenter, "right": Qt.AlignmentFlag.AlignRight}.get(
                a.align, Qt.AlignmentFlag.AlignLeft)
            pad = 2 + a.width
            p.drawText(r.adjusted(pad, pad, -pad, -pad), int(align | Qt.AlignmentFlag.AlignTop
                                                             | Qt.TextFlag.TextWordWrap), a.contents)
    elif a.kind == "area":
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
        p.fillRect(qrect(a.rect), QColor(a.fill or a.color))
    elif a.kind in ("rect", "ellipse"):
        p.setPen(_pen(a.color, a.width, a.dashed) if a.width > 0 else Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(a.fill)) if a.fill else Qt.BrushStyle.NoBrush)
        if a.kind == "rect":
            p.drawRect(qrect(a.rect))
        else:
            p.drawEllipse(qrect(a.rect))
    elif a.kind in ("polygon", "cloud") and a.paths:
        points = [QPointF(*pt) for pt in a.paths[0]]
        p.setPen(_pen(a.color, a.width, a.dashed and a.kind == "polygon") if a.width > 0 else Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(a.fill)) if a.fill else Qt.BrushStyle.NoBrush)
        if a.kind == "cloud" and len(points) > 2:
            p.drawPath(cloud_path(points, a.width))
        else:
            p.drawPolygon(QPolygonF(points))
    elif a.kind in ("line", "arrow", "polyline") and a.paths:
        points = [QPointF(*pt) for pt in a.paths[0]]
        if len(points) < 2:
            points = points * 2
        p.setPen(_pen(a.color, a.width, a.dashed))
        p.drawPolyline(QPolygonF(points))
        ends = a.ends if a.kind != "arrow" or a.ends != ("None", "None") else ("None", "OpenArrow")
        line_end(p, points[0], points[1], ends[0], a.width, color)
        line_end(p, points[-1], points[-2], ends[1], a.width, color)
    elif a.kind in ("ink", "marker"):
        if a.kind == "marker":  # (a highlight, drawn by hand: the text shows through it)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
        p.setPen(_pen(a.color, a.width))
        for path in a.paths:
            if len(path) == 1 or len(set(path)) == 1:  # (a dot)
                p.drawPoint(QPointF(*path[0]))
            elif len(path) == 2:
                p.drawLine(QPointF(*path[0]), QPointF(*path[1]))
            else:  # (a curve through its points, as the PDF draws it: see annots.smooth_segments)
                curve = QPainterPath(QPointF(*path[0]))
                for c1, c2, end in smooth_segments(path):
                    curve.cubicTo(QPointF(*c1), QPointF(*c2), QPointF(*end))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(curve)
    elif a.kind == "stamp":
        r = qrect(a.rect)
        image = stamp_image(a)
        if image is not None:
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.drawImage(r, image)
        else:  # (a stamp whose look is unknown)
            p.setPen(_pen(a.color, 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r, 4, 4)
            if not thumbnail:
                p.setFont(_font(p, "helv", min(r.height() * 0.5, 24)))
                p.drawText(r, int(Qt.AlignmentFlag.AlignCenter), tr(STAMPS[a.stamp]).upper() if a.stamp in STAMPS
                           else a.contents)
    p.restore()
