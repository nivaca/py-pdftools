"""Reading colours (View > Reading colours): the pages in view drawn in other colours, to rest the eyes or
read better: white, yellow or green text on black, light text on dark grey, or colours of one's own. Only
the view changes: not the file, the thumbnails or the annotations. Black becomes the colour of the text,
white that of the page, and the colours between them change with them (PyMuPDF's tint_with)."""

from __future__ import annotations

from ..core.interface import N_

# (name, title, colour of the text, colour of the page), as 0xRRGGBB
SCHEMES = [
    ("", N_("Normal"), None, None),
    ("white", N_("White on black"), 0xFFFFFF, 0x000000),
    ("yellow", N_("Yellow on black"), 0xFFFF00, 0x000000),
    ("green", N_("Green on black"), 0x33FF66, 0x000000),
    ("dim", N_("Light on dark grey"), 0xDDDDDD, 0x2B2B2B),
]
TINT: tuple[int, int] | None = None  # (colour of the text, colour of the page) of the pages in view; None: as they are
# The sharpness of the text of the pages in view (Settings > Appearance): (gamma, radius, percent). The gamma
# darkens the soft grey edges MuPDF draws letters and lines with (it doesn't snap them to the pixels, as the
# desktop's fonts are), and an unsharp mask makes them steeper (see core/rendering.sharpen); "drawn" leaves
# them as MuPDF draws them. Pictures get a little darker and sharper too.
SHARPNESS = {"drawn": (1.0, 0.0, 0), "sharper": (1.4, 0.5, 70), "sharpest": (1.4, 0.6, 120)}
SHARPEN = SHARPNESS["drawn"]


def tint_of(name: str, custom: tuple[int, int] | None = None) -> tuple[int, int] | None:
    """The (text, page) colours of the scheme NAME ('custom': CUSTOM); None for the normal colours."""
    if name == "custom":
        return custom
    for key, _, text, page in SCHEMES:
        if key == name and text is not None:
            return (text, page)
    return None


def page_colour() -> int:
    """The colour of a page not yet drawn (white, or that of the scheme)."""
    return TINT[1] if TINT is not None else 0xFFFFFF
