"""Colours offered in the menus (the palette of the settings, each with what
it means to the user), their names, and the squares that show them."""

from __future__ import annotations

from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

from ..annotate import settings
from ..core.interface import tr

_palette: list[tuple[str, str | None]] = [(c, None) for c, _, _ in settings.PALETTE]
_NAMES = {c: name for c, name, _ in settings.PALETTE}
_MEANINGS = {i: meaning for i, (_, _, meaning) in enumerate(settings.PALETTE)}


def set_palette(palette) -> None:
    """Use PALETTE ((colour, meaning or None for the usual one), from the settings)."""
    global _palette
    _palette = list(palette)


def meaning(index: int) -> str:
    color, text = _palette[index]
    if text is None:  # (the usual one, if the colour is the usual one)
        usual = settings.PALETTE[index]
        return tr(usual[2]) if color == usual[0] and usual[2] else ""
    return text


def swatches() -> list[tuple[str, str]]:
    """(colour, its name with its meaning) of each colour of the palette."""
    return [(color, label(color, meaning(i))) for i, (color, _) in enumerate(_palette)]


def label(color: str, means: str = "") -> str:
    name = tr(_NAMES[color]) if color in _NAMES else color
    return f"{name} — {means}" if means else name


def color_meaning(color: str) -> str:
    """What COLOR means to the user ('' if it isn't in the palette, or means nothing)."""
    for i, (c, _) in enumerate(_palette):
        if c == (color or "").lower():
            return meaning(i)
    return ""


def color_name(color: str) -> str:
    """COLOR's name, with its meaning: 'Yellow — Important'."""
    if not color:
        return tr("No colour")
    return label(color.lower(), color_meaning(color))


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
