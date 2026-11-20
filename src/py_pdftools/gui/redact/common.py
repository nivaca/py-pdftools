"""What the parts of the mode Redact share: the colours of boxes, and the choices of their pages."""

from __future__ import annotations

from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

from ...core.interface import N_, tr

SWATCHES = [("#000000", N_("Black")), ("#ffffff", N_("White")), ("#808080", N_("Grey")), ("", N_("No colour"))]
# the choices of "Pages": (what is kept in Box.repeat, its name); '*' is a list typed by the user
REPEATS = [("", N_("Only the page where it was drawn")), ("all", N_("All pages")), ("odd", N_("Odd pages")),
           ("even", N_("Even pages")), ("*", N_("These pages:"))]


def swatch(color: str, size: int = 16) -> QIcon:
    """A square of COLOR; for no colour (''), an empty square crossed out."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(color) if color else QColor(0, 0, 0, 0))
    p = QPainter(pixmap)
    if not color:
        p.setPen(QColor(208, 48, 48))
        p.drawLine(1, size - 2, size - 2, 1)
    p.setPen(QColor(128, 128, 128))
    p.drawRect(0, 0, size - 1, size - 1)
    p.end()
    return QIcon(pixmap)


def color_name(color: str) -> str:
    for value, name in SWATCHES:
        if value == color.lower():
            return tr(name)
    return color.lower()


def mm(points: float) -> str:
    return f"{points / 72 * 25.4:.0f}"
