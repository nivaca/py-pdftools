"""The matrices of PDF ([a b c d e f], as the operator cm takes them), which imposition and the stamps
of the pages (headers, footers, watermarks) both compute with.

(py-imposition and py-foliation each had their own; impose/pdfutil.py and pages/stamps.py give these
under the names they had.)
"""

from __future__ import annotations

Matrix = tuple[float, float, float, float, float, float]
IDENTITY: Matrix = (1, 0, 0, 1, 0, 0)


def multiply(m: Matrix, n: Matrix) -> Matrix:
    """The matrix of doing M, then N."""
    a, b, c, d, e, f = m
    A, B, C, D, E, F = n
    # Producto con vectores fila, [x y 1]·M·N, como en PDF: M se aplica primero, como con dos operadores cm.
    return (a * A + b * C, a * B + b * D, c * A + d * C, c * B + d * D, e * A + f * C + E, e * B + f * D + F)


def invert(m: Matrix) -> Matrix:
    """The matrix that undoes M."""
    a, b, c, d, e, f = m
    # No check for a singular matrix: a zero scale would raise ZeroDivisionError here.
    det = a * d - b * c
    ia, ib, ic, id_ = d / det, -b / det, -c / det, a / det
    return (ia, ib, ic, id_, -(e * ia + f * ic), -(e * ib + f * id_))


def apply(m: Matrix, x: float, y: float) -> tuple[float, float]:
    """The point (X, Y) moved by M."""
    a, b, c, d, e, f = m
    return a * x + c * y + e, b * x + d * y + f
