"""Stamps of the user's own: a text in capitals, in a frame, with the author
and the date under it if wanted; drawn with Qt into a picture, which is
written in the PDF as the stamp's image."""

from __future__ import annotations

import datetime

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPen

# 4 píxeles por punto equivalen a 288 ppp: el sello se ve nítido al ampliar o imprimir.
SCALE = 4  # pixels of the picture for each point of the stamp


def text_stamp(text: str, color: str, author: str = "", dated: bool = True) -> tuple[bytes, tuple[float, float]]:
    """The picture (a PNG) of a stamp that says TEXT, and its size in points."""
    # Los espacios repetidos y saltos de línea se reducen a uno; un texto vacío da '?'.
    title = " ".join(text.split()).upper() or "?"
    line = ", ".join(x for x in (author, datetime.date.today().isoformat() if dated else "") if x)
    big, small = QFont("Helvetica"), QFont("Helvetica")
    big.setBold(True)
    # Pixel sizes, not point sizes: the picture must not depend on the screen's dpi.
    big.setPixelSize(18 * SCALE)
    small.setPixelSize(8 * SCALE)
    m_big, m_small = QFontMetricsF(big), QFontMetricsF(small)
    pad = 6 * SCALE
    # El ancho lo marca la línea más larga (título o autor y fecha), más el relleno a cada lado.
    width = max(m_big.horizontalAdvance(title), m_small.horizontalAdvance(line) if line else 0) + 2 * pad
    height = m_big.height() + (m_small.height() if line else 0) + pad
    # ARGB32 with a transparent fill: outside the frame, the page shows through.
    image = QImage(int(width), int(height), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    ink = QColor(color)
    p.setPen(QPen(ink, 2.5 * SCALE))
    p.setBrush(Qt.BrushStyle.NoBrush)
    # The frame is drawn inset by half its pen width, so the line is not cut at the edges of the image.
    inset = 1.5 * SCALE
    p.drawRoundedRect(QRectF(inset, inset, width - 2 * inset, height - 2 * inset), 4 * SCALE, 4 * SCALE)
    p.setFont(big)
    top = pad / 2
    p.drawText(QRectF(0, top, width, m_big.height()), int(Qt.AlignmentFlag.AlignCenter), title)
    if line:
        p.setFont(small)
        # La línea pequeña sube un poco (SCALE) para quedar junto al título.
        p.drawText(QRectF(0, top + m_big.height() - SCALE, width, m_small.height()),
                   int(Qt.AlignmentFlag.AlignCenter), line)
    p.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    # The size in points is the size in pixels divided by SCALE: the stamp is placed at that size.
    return bytes(data.data()), (round(width / SCALE, 2), round(height / SCALE, 2))
