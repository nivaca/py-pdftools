"""What the parts of the mode Redact share: the colours of boxes, and the choices of their pages."""

from __future__ import annotations

from ...core.interface import N_, tr
from ..colors import swatch  # noqa: F401  (the same squares as in Annotate)

SWATCHES = [("#000000", N_("Black")), ("#ffffff", N_("White")), ("#808080", N_("Grey")), ("", N_("No colour"))]
# the choices of "Pages": (what is kept in Box.repeat, its name); '*' is a list typed by the user
REPEATS = [("", N_("Only the page where it was drawn")), ("all", N_("All pages")), ("odd", N_("Odd pages")),
           ("even", N_("Even pages")), ("*", N_("These pages:"))]


def color_name(color: str) -> str:
    for value, name in SWATCHES:
        # Se compara en minúsculas; un color que no está en SWATCHES se muestra como #rrggbb.
        if value == color.lower():
            return tr(name)
    return color.lower()


# Points (1/72 inch) to whole millimetres, as text for the table of boxes.
def mm(points: float) -> str:
    return f"{points / 72 * 25.4:.0f}"
