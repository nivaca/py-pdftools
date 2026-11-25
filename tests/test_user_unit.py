"""Las páginas con /UserUnit (una unidad de N puntos, en documentos de gran formato): MuPDF da sus lugares en
puntos, pero escribe y lee el tamaño de la letra y el ancho de las líneas en las unidades de la página;
annots los pasa a puntos al leer y a unidades al escribir, para que se vean del tamaño pedido."""

from __future__ import annotations

import pymupdf
import pytest

from py_pdftools.annotate import annots
from py_pdftools.annotate.annots import Annotation


def _doc(unit: float) -> pymupdf.Document:
    doc = pymupdf.open()
    page = doc.new_page(width=2448 / unit, height=3168 / unit)
    if unit != 1:
        doc.xref_set_key(page.xref, "UserUnit", f"{unit:g}")
    return pymupdf.open("pdf", doc.tobytes())


def _ink_rows(doc: pymupdf.Document, column: int | None = None) -> int:
    pix = doc[0].get_pixmap()
    s, w, n = pix.samples, pix.width, pix.n
    xs = [column] if column is not None else range(0, w, 3)
    return sum(1 for y in range(pix.height) if any(s[(y * w + x) * n] < 100 for x in xs))


def test_the_unit():
    assert annots.user_unit(_doc(1)[0]) == 1 and annots.user_unit(_doc(4)[0]) == 4
    assert _doc(4)[0].rect.width == pytest.approx(2448)  # (MuPDF: the places, in points)


@pytest.mark.parametrize("unit", [1, 4])
def test_text_and_lines_are_seen_as_asked(unit):
    doc = _doc(unit)
    box = Annotation("freetext", 0, (200, 200, 1400, 600), "#000000", font_size=48, width=0, contents="HHHH")
    line = Annotation("line", 0, (200, 1000, 2000, 1000), "#000000", width=8, paths=(((200, 1000), (2000, 1000)),))
    annots.apply(doc, [box, line])
    doc = pymupdf.open("pdf", doc.tobytes())
    # Read back in points, as written
    read = {a.kind: a for a in annots.read(doc)}
    assert read["freetext"].font_size == pytest.approx(48) and read["line"].width == pytest.approx(8)
    # And drawn of that size: 8 points of line are 8 pixels at 72 dpi, whatever the unit
    assert _ink_rows(doc, column=1000) == pytest.approx(8, abs=1)
    # (a text of 48 points: the same height of ink on both pages)
    clip = pymupdf.open()
    clip.insert_pdf(doc)
    clip[0].set_cropbox(pymupdf.Rect(200, 200, 1400, 600) if unit == 1 else pymupdf.Rect(50, 50, 350, 150))
    assert _ink_rows(clip) == pytest.approx(35, abs=3)


def test_a_change_keeps_the_sizes():
    doc = _doc(4)
    box = Annotation("freetext", 0, (200, 200, 1400, 600), "#000000", font_size=48, width=2, contents="Hi")
    annots.apply(doc, [box])
    old = annots.read(doc)[0]
    annots.apply(doc, [old.__class__(**{**old.__dict__, "font_size": 24.0})])
    after = annots.read(doc)[0]
    assert after.font_size == pytest.approx(24) and after.width == pytest.approx(2)
