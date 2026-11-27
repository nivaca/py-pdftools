"""Annotations flattened: all or some, with their comments written beside them, the others kept exactly."""

from __future__ import annotations

import pymupdf
from test_sidecar import editable, foreign

from py_pdftools.annotate import annots, flatten
from py_pdftools.annotate.annots import Annotation, Reply


def test_some_with_their_comments(sample, tmp_path):
    path = foreign(sample, tmp_path)  # (a note answered once, on page 1; a rectangle on page 2; keys of others)
    items = annots.read(annots.open_pdf(path))
    note = next(i for i, a in enumerate(items) if a.kind == "note")
    out = tmp_path / "flat.pdf"
    assert flatten.flatten(path, items, [note], out, comments=True) == 1
    doc = annots.open_pdf(out)
    left = editable(annots.read(doc))
    assert [a.kind for a in left] == ["rect"]
    assert doc.xref_get_key(left[0].xref, "OtherProgram")[1] == "<</Kept true/Count 3>>" or \
        "Kept" in doc.xref_get_key(left[0].xref, "OtherProgram")[1]  # (the one left: exactly as it was)
    text = doc[0].get_text()
    assert "note" in text and "B: an answer" in text  # (its comment and its reply, on the page now)
    assert not doc[0].annot_xrefs()


def test_all_without_comments(sample, tmp_path):
    items = [Annotation("note", 0, (100, 100, 116, 116), "#ffd54f", contents="hidden text",
                        replies=(Reply("B", "yes"),)),
             Annotation("rect", 0, (10, 10, 60, 60), "#ff0000", contents="a box"),
             Annotation("freetext", 1, (100, 100, 300, 140), contents="shown text")]
    out = tmp_path / "flat.pdf"
    assert flatten.flatten(sample, items, [0, 1, 2], out) == 3
    doc = pymupdf.open(out)
    assert all(not page.annot_xrefs() for page in doc)
    assert "hidden text" not in doc[0].get_text() and "shown text" in doc[1].get_text()
    assert doc[0].get_drawings()  # (the rectangle and the note's icon, drawn on the page)


def test_comment_box_beside():
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    a = Annotation("highlight", 0, (60, 100, 300, 114), contents="why?", quads=((60, 100, 300, 114),))
    box = flatten.comment_box(page, a)
    assert box.rect[0] >= 300 and box.rect[1] == 100 and box.contents == "why?"
    edge = Annotation("rect", 0, (420, 800, 590, 840), contents="near the corner")
    box = flatten.comment_box(page, edge)
    assert box.rect[2] <= 595 and box.rect[3] <= 842  # (inside the page)
    assert flatten.comment_box(page, Annotation("freetext", 0, (1, 1, 50, 50), contents="x")) is None
    assert flatten.comment_box(page, Annotation("rect", 0, (1, 1, 50, 50))) is None
