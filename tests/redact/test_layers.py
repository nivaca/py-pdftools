"""Hidden layers (redact/hidden.py): the layers switched off are counted, and taken out when the document is
sanitized or its redacted copy cleaned: the text, drawings, pictures, forms and annotations in them, and
their names; the layers shown, and what is in no layer, stay."""

from __future__ import annotations

import pymupdf
import pytest

from py_pdftools.redact import hidden
from py_pdftools.redact.redact import Box, sanitize, write_redacted


def layered(path, base_off=False):
    """A page with text in no layer, in a layer shown and in one switched off (with a drawing, a picture, a
    form and a note in it too)."""
    doc = pymupdf.open()
    page = doc.new_page()
    on = doc.add_ocg("Shown", on=True)
    off = doc.add_ocg("Secret notes", on=False)
    page.insert_text((72, 100), "Always here", fontsize=12)
    page.insert_text((72, 150), "Visible layer", fontsize=12, oc=on)
    page.insert_text((72, 200), "Hidden layer text", fontsize=12, oc=off)
    page.draw_rect(pymupdf.Rect(50, 50, 100, 100), oc=off)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 4, 4), 0)
    page.insert_image(pymupdf.Rect(200, 300, 250, 350), pixmap=pix, oc=off)
    src = pymupdf.open()
    src.new_page(width=200, height=100).insert_text((10, 50), "Form in hidden layer", fontsize=12)
    page.show_pdf_page(pymupdf.Rect(300, 400, 500, 500), src, 0, oc=off)
    note = page.add_text_annot((300, 300), "a note")
    note.set_oc(off)
    note.update()
    page.add_text_annot((400, 300), "a note seen")
    if base_off:  # (all off but those said to be on)
        cat = doc.pdf_catalog()
        doc.xref_set_key(cat, "OCProperties/D/BaseState", "/OFF")
        doc.xref_set_key(cat, "OCProperties/D/OFF", "[]")
    doc.save(path)
    return path


def all_text(path_or_doc) -> str:
    """The text of the first page, with every layer switched on (else what is in those off is not read)."""
    doc = pymupdf.open(path_or_doc) if not isinstance(path_or_doc, pymupdf.Document) else path_or_doc
    copy = pymupdf.open("pdf", doc.tobytes())
    copy.xref_set_key(copy.pdf_catalog(), "OCProperties", "null")  # (no layers: all is shown)
    return pymupdf.open("pdf", copy.tobytes())[0].get_text()


def check_clean(path):
    doc = pymupdf.open(path)
    page = doc[0]
    text = all_text(doc)
    assert "Always here" in text and "Visible layer" in text
    assert "Hidden layer" not in text and "Form in hidden" not in text
    assert page.get_images() == []
    assert not any(pymupdf.Rect(d["rect"]).intersects((50, 50, 100, 100)) for d in page.get_drawings())
    assert [a.info["content"] for a in page.annots()] == ["a note seen"]
    assert [o["name"] for o in doc.get_ocgs().values()] == ["Shown"]
    assert b"Secret notes" not in path.read_bytes()


def test_counted(tmp_path):
    doc = pymupdf.open(layered(tmp_path / "l.pdf"))
    assert hidden.inspect(doc)["layers"] == 1
    assert hidden.inspect(pymupdf.open(layered(tmp_path / "b.pdf", base_off=True)))["layers"] == 1


@pytest.mark.parametrize("base_off", [False, True])
def test_sanitized(tmp_path, base_off):
    out = tmp_path / "out.pdf"
    sanitize(layered(tmp_path / "l.pdf", base_off), out, kinds={"layers", "unused"})
    check_clean(out)
    assert hidden.inspect(pymupdf.open(out))["layers"] == 0


def test_only_layers_kind_removes_them(tmp_path):
    out = tmp_path / "out.pdf"
    sanitize(layered(tmp_path / "l.pdf"), out, kinds={"metadata"})
    assert "Hidden layer text" in all_text(out)


def test_all_hidden_then_no_layers_left(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page()
    off = doc.add_ocg("Only", on=False)
    page.insert_text((72, 100), "Gone", fontsize=12, oc=off)
    page.insert_text((72, 200), "Stays", fontsize=12)
    assert hidden.remove_hidden_layers(doc) == 1
    assert doc.xref_get_key(doc.pdf_catalog(), "OCProperties")[0] == "null"
    assert all_text(doc).split() == ["Stays"]


def test_combination_of_layers(tmp_path):
    """Content marked with a combination (an /OCMD) is hidden as the combination says."""
    doc = pymupdf.open()
    page = doc.new_page()
    on, off = doc.add_ocg("On", on=True), doc.add_ocg("Off", on=False)
    any_on = doc.set_ocmd(ocgs=[on, off], policy="AnyOn")
    all_on = doc.set_ocmd(ocgs=[on, off], policy="AllOn")
    page.insert_text((72, 100), "AnyOn shows", fontsize=12, oc=any_on)
    page.insert_text((72, 200), "AllOn hides", fontsize=12, oc=all_on)
    hidden.remove_hidden_layers(doc)
    assert all_text(doc).split() == ["AnyOn", "shows"]


def test_redacted_copy_cleaned(tmp_path):
    source = layered(tmp_path / "l.pdf")
    out = tmp_path / "red.pdf"
    write_redacted(source, [Box(0, (60, 85, 200, 105))], out, clean=True)
    text = all_text(out)
    assert "Always" not in text and "Hidden layer" not in text and "Visible layer" in text
    write_redacted(source, [Box(0, (60, 85, 200, 105))], out, clean=False)
    assert "Hidden layer" in all_text(out)
