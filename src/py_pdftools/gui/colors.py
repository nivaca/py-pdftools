"""Colours offered in the menus (the palette of the settings, each with what
it means to the user), their names, and the squares that show them."""

from __future__ import annotations

from PySide6.QtGui import QActionGroup, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu

from ..annotate import settings
from ..core.interface import tr

# Estado del módulo: la ventana lo cambia con set_palette al leer o cambiar los ajustes.
_palette: list[tuple[str, str | None]] = [(c, None) for c, _, _ in settings.PALETTE]
_NAMES = {c: name for c, name, _ in settings.PALETTE}


def set_palette(palette) -> None:
    """Use PALETTE ((colour, meaning or None for the usual one), from the settings)."""
    global _palette
    _palette = list(palette)


def meaning(index: int) -> str:
    color, text = _palette[index]
    # None es 'el de fábrica'; '' es que el usuario lo dejó vacío a propósito.
    if text is None:  # (the usual one, if the colour is the usual one)
        usual = settings.PALETTE[index]
        # If the user changed the colour, the usual meaning (of the old colour) no longer applies.
        return tr(usual[2]) if color == usual[0] and usual[2] else ""
    return text


def swatches() -> list[tuple[str, str]]:
    """(colour, its name with its meaning) of each colour of the palette."""
    return [(color, label(color, meaning(i))) for i, (color, _) in enumerate(_palette)]


def label(color: str, means: str = "") -> str:
    # Un color fuera de la paleta se nombra por su código, p. ej. #3a7bd5.
    name = tr(_NAMES[color]) if color in _NAMES else color
    return f"{name} — {means}" if means else name


def color_meaning(color: str) -> str:
    """What COLOR means to the user ('' if it isn't in the palette, or means nothing)."""
    for i, (c, _) in enumerate(_palette):
        # Comparación en minúsculas: los colores leídos de un PDF pueden venir como #FFEB3B.
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
    # Sin color, el cuadro es transparente y lleva una raya roja en diagonal, como un 'prohibido'.
    pixmap.fill(QColor(color) if color else QColor(0, 0, 0, 0))
    p = QPainter(pixmap)
    if not color:
        p.setPen(QColor(208, 48, 48))
        p.drawLine(1, size - 2, size - 2, 1)
    # A grey border, so that white and very light colours can be seen on a light menu.
    p.setPen(QColor(128, 128, 128))
    p.drawRect(0, 0, size - 1, size - 1)
    p.end()
    return QIcon(pixmap)


def colors_menu(menu: QMenu, title: str, current: str | None, choose, choices, other) -> QMenu:
    """A submenu TITLE of MENU with the colours CHOICES ((value, name)), CURRENT ticked, each given to
    CHOOSE; and 'Other colour…', which calls OTHER (it shows CURRENT if that isn't among them)."""
    sub = menu.addMenu(swatch(current) if current else QIcon(), title)
    group = QActionGroup(sub)
    for value, name in choices:
        act = sub.addAction(swatch(value), name, lambda v=value: choose(v))
        act.setCheckable(True)
        act.setChecked(value == current)
        group.addAction(act)
    sub.addSeparator()
    entry = sub.addAction(tr("Other colour…"), other)
    # Un color fuera de la paleta se muestra en «Otro color», para que se vea cuál es.
    if current and current not in [v for v, _ in choices]:
        entry.setText(tr("Other colour ({color})…", color=current))
        entry.setIcon(swatch(current))
    return sub
