"""La comparación visual de dos PDF: cada página de uno se dibuja junto a la del mismo número del otro, en gris y
a la misma escala, y se buscan los píxeles que no coinciden. Lo que difiere se da como rectángulos (en puntos de
la página), uniendo las celdas vecinas de una rejilla, para enmarcarlo; y una imagen superpuesta muestra el uno
en rojo y el otro en azul, en negro lo que tienen en común. No compara el texto (eso es Comparar con otra
versión, annotate/compare.py), sino lo que se ve: también las imágenes, los dibujos y la posición de cada cosa.

No usa numpy: las filas de píxeles se comparan como enteros (XOR) y los tramos distintos se buscan con una
expresión regular sobre los bytes, todo en C."""

from __future__ import annotations

import re

import pymupdf

SCALE = 1.0  # (píxeles por punto al comparar: 72 ppp bastan para ver qué cambió, y es rápido)
CELL = 6  # (el lado de una celda de la rejilla, en píxeles: los cambios a menos de una celda se unen)
LEVEL = 48  # (cuánto deben diferir dos grises para contar: el suavizado de los bordes no es un cambio)
RED, BLUE = 0xE53935, 0x1E88E5  # (this document, and the other, in the overlay)
_DIFFERENT = re.compile(rb"[^\x00]+")

Rect = tuple[float, float, float, float]


def _gray(page: pymupdf.Page | None, width: int, height: int, scale: float) -> bytes:
    """PAGE rendered in grey at SCALE, on a white sheet of WIDTH x HEIGHT pixels (a missing page: all white)."""
    sheet = bytearray(b"\xff" * (width * height))
    if page is None:
        return bytes(sheet)
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csGRAY, alpha=False)
    data, stride = pix.samples, pix.stride
    w, h = min(pix.width, width), min(pix.height, height)
    for y in range(h):
        sheet[y * width:y * width + w] = data[y * stride:y * stride + w]
    return bytes(sheet)


def _quantized(row: bytes) -> bytes:
    # (cada gris, a uno de pocos niveles: dos grises casi iguales quedan iguales)
    return row.translate(_LEVELS)


_LEVELS = bytes(min(255, (g // LEVEL) * LEVEL) for g in range(256))


def differences(page: pymupdf.Page | None, other: pymupdf.Page | None, scale: float = SCALE) -> list[Rect]:
    """Where PAGE and OTHER look different, as rectangles in points (of PAGE; both are laid from their top
    left corner); [] if they look the same. A page missing on one side differs wholly."""
    if page is None and other is None:
        return []
    rects = [p.rect for p in (page, other) if p is not None]
    width = max(round(r.width * scale) for r in rects)
    height = max(round(r.height * scale) for r in rects)
    if page is None or other is None:
        r = rects[0]
        return [(0.0, 0.0, r.width, r.height)]
    a = _gray(page, width, height, scale)
    b = _gray(other, width, height, scale)
    if a == b:
        return []
    columns, rows = (width + CELL - 1) // CELL, (height + CELL - 1) // CELL
    cells: set[tuple[int, int]] = set()
    for y in range(height):
        ra, rb = a[y * width:(y + 1) * width], b[y * width:(y + 1) * width]
        if ra == rb:
            continue
        ra, rb = _quantized(ra), _quantized(rb)
        if ra == rb:
            continue
        xor = (int.from_bytes(ra) ^ int.from_bytes(rb)).to_bytes(width)
        for m in _DIFFERENT.finditer(xor):
            for cx in range(m.start() // CELL, (m.end() - 1) // CELL + 1):
                cells.add((cx, y // CELL))
    return [(x0 * CELL / scale, y0 * CELL / scale, min(x1 * CELL, width) / scale, min(y1 * CELL, height) / scale)
            for x0, y0, x1, y1 in _boxes(cells, columns, rows)]


def _boxes(cells: set[tuple[int, int]], columns: int, rows: int) -> list[tuple[int, int, int, int]]:
    """The cells in groups of neighbours (touching, also by a corner, or one cell apart), each as the box
    around it, in cells: (x0, y0, x1, y1), x1 and y1 past the last."""
    left, out = set(cells), []
    while left:
        start = left.pop()
        group, todo = [start], [start]
        while todo:
            x, y = todo.pop()
            for dx in (-2, -1, 0, 1, 2):
                for dy in (-2, -1, 0, 1, 2):
                    n = (x + dx, y + dy)
                    if n in left:
                        left.remove(n)
                        group.append(n)
                        todo.append(n)
        xs, ys = [c[0] for c in group], [c[1] for c in group]
        out.append((min(xs), min(ys), max(xs) + 1, max(ys) + 1))
    return sorted(out, key=lambda b: (b[1], b[0]))


def tinted(page: pymupdf.Page | None, colour: int, scale: float) -> pymupdf.Pixmap | None:
    """PAGE rendered at SCALE with its black in COLOUR (and its white white), for the overlay."""
    if page is None:
        return None
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
    pix.tint_with(colour, 0xFFFFFF)
    return pix
