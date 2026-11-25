"""Las notas y los adjuntos llevan las marcas NoZoom y NoRotate de PDF (su icono, del mismo tamaño y derecho en
los lectores que las siguen); las demás anotaciones, no."""

from __future__ import annotations

import pymupdf

from py_pdftools.annotate import annots
from py_pdftools.annotate.annots import Annotation

FIXED = pymupdf.PDF_ANNOT_IS_NO_ZOOM | pymupdf.PDF_ANNOT_IS_NO_ROTATE


def test_icons_are_fixed():
    doc = pymupdf.open()
    doc.new_page()
    annots.apply(doc, [
        Annotation("note", 0, (100, 100, 116, 116), "#ffd54f", contents="hi"),
        Annotation("attachment", 0, (200, 100, 216, 116), "#1e88e5", data=b"x", filename="x.txt"),
        Annotation("rect", 0, (100, 300, 200, 400), "#e53935"),
    ])
    doc = pymupdf.open("pdf", doc.tobytes())
    flags = {annot.type[1]: annot.flags for annot in doc[0].annots()}
    assert flags["Text"] & FIXED == FIXED and flags["FileAttachment"] & FIXED == FIXED
    assert flags["Square"] & FIXED == 0
    assert all(f & pymupdf.PDF_ANNOT_IS_PRINT for f in flags.values())
    # Read back as before: the note is still a note, where it was
    note = next(a for a in annots.read(doc) if a.kind == "note")
    assert note.rect[:2] == (100, 100) and note.contents == "hi"
