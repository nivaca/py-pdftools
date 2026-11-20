"""Small helpers on PDF documents (PyMuPDF) that annotate and redact both use: opening a PDF, rectangles,
colours, and the words of a page under the mouse.

(py-annotate and py-redact each had a copy of these; annotate/annots.py and redact/redact.py give them
under their old names, with their own errors.)
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pymupdf

from .interface import tr

Rect = tuple[float, float, float, float]


def normalized(rect: Rect) -> Rect:
    """RECT with x0 <= x1 and y0 <= y1 (as drawn from any corner)."""
    x0, y0, x1, y1 = rect
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def rgb(color: str) -> tuple[float, float, float]:
    """'#rrggbb' as PyMuPDF's (r, g, b), each from 0 to 1."""
    c = color.lstrip("#")
    # Seis cifras sin '#'; los colores cortos (#abc) no se aceptan aquí.
    if len(c) != 6:
        raise ValueError(color)
    return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))


def open_pdf(path: Path, password: str, error: type[Exception], password_error: type[Exception]
             ) -> pymupdf.Document:
    """The PDF at PATH, opened with PASSWORD if it needs one; else ERROR, or PASSWORD_ERROR if the
    password is missing or wrong (the errors of the module that asks)."""
    # PyMuPDF also opens images and other formats; is_pdf, below, turns them away.
    try:
        doc = pymupdf.open(path)
    except (pymupdf.FileNotFoundError, pymupdf.FileDataError, RuntimeError) as e:
        raise error(tr("{path} cannot be read as a PDF: {error}", path=path, error=e)) from None
    if not doc.is_pdf:
        doc.close()
        raise error(tr("{path} is not a PDF", path=path))
    # needs_pass is false for a file with only an owner password: such files open without asking.
    # authenticate() devuelve 0 si la contraseña no sirve.
    if doc.needs_pass and not doc.authenticate(password):
        doc.close()
        raise password_error(tr("{path} is protected by a password", path=path))
    return doc


# A word of a page: its rectangle, its block and its line first (then, maybe, its text)
Word = Sequence


def nearest_word(found: list[Word], x: float, y: float) -> int | None:
    """The index of the word at (X, Y), or else of the nearest one; None if there are none."""
    if not found:
        return None

    # Squared distance to the word's rectangle (0 inside it): the root is not needed to compare.
    def distance(i):
        x0, y0, x1, y1 = found[i][0]
        dx = max(x0 - x, 0, x - x1)
        dy = max(y0 - y, 0, y - y1)
        return dx * dx + 4 * dy * dy  # (the line it is on matters more)

    return min(range(len(found)), key=distance)


def text_rects(found: list[Word], first: int, last: int, pad: float = 0.0) -> list[Rect]:
    """The rectangles that cover the words FIRST to LAST (in either order) of FOUND: one for each line,
    PAD points larger than its words on every side (rounded to hundredths of a point)."""
    if first > last:
        first, last = last, first
    # Un rectángulo por línea (bloque, línea): las palabras de una misma línea se unen.
    lines: dict[tuple[int, int], list[float]] = {}
    for word in found[first:last + 1]:
        (x0, y0, x1, y1), block, line = word[0], word[1], word[2]
        r = lines.setdefault((block, line), [x0, y0, x1, y1])
        r[0], r[1], r[2], r[3] = min(r[0], x0), min(r[1], y0), max(r[2], x1), max(r[3], y1)
    return [(round(x0 - pad, 2), round(y0 - pad, 2), round(x1 + pad, 2), round(y1 + pad, 2))
            for x0, y0, x1, y1 in lines.values()]
