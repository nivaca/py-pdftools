"""Annotations kept apart, in book.pdf.pdfnotes: written and read with all their fields, combined with those the
PDF has, put in place on pages turned since, and written into the PDF again."""

from __future__ import annotations

import dataclasses
import os

import pikepdf
import pymupdf
import pytest
from test_annots import one_of_each

from py_pdftools.annotate import annots, exchange, sidecar
from py_pdftools.annotate.annots import AnnotateError, Annotation, Critical, Reply


def bare(items):
    """ITEMS without their xrefs (and those of their replies)."""
    return [dataclasses.replace(a, xref=0, replies=tuple(dataclasses.replace(r, xref=0) for r in a.replies))
            for a in items]


def editable(items):
    return [a for a in items if a.kind != annots.OTHER]


def keep(path, doc, items, in_pdf=()):
    target = sidecar.beside(path)
    sidecar.write(target, doc, path.name, items, sidecar.base_of(list(in_pdf)))
    return target


def test_names(sample):
    assert sidecar.beside(sample).name == "sample.pdf.pdfnotes"
    assert sidecar.find(sample) is None
    assert sidecar.place_for(sample) == sidecar.beside(sample)


def test_every_field_round_trip(sample):
    doc = annots.open_pdf(sample)
    odd = "line one\nline two\ttab — «ñ» \x0c form feed \x01"  # (XML 1.0 can't hold \x0c nor \x01)
    wanted = one_of_each(sample, 0) + one_of_each(sample, 2) + [
        Annotation("note", 1, (300.25, 200.125, 316.0, 216.0), "#ffd54f", contents=odd, author="A \x02 B",
                   popup=(320.0, 200.0, 500.0, 300.0), tags=("one", "two & <three>"), categories=("Key",),
                   created="D:20261126120000", modified="D:20261126130000", group="g1", layer="Review",
                   critical=Critical("variant", lemma="dixit", reading="dicit", witness="A", rationale="x\ny"),
                   replies=(Reply("B", "I agree\nfully", "Accepted", "D:20261126"), Reply("C", "", "None"))),
        Annotation("freetext", 1, (10, 10, 200, 60), "#000000", rich="<p>Bold <b>this</b></p>", font_size=13.5,
                   opacity=0.123456789, width=0.75),
        Annotation("stamp", 1, (10, 100, 110, 150), image=b"\x89PNG\r\n\x1a\n\x00\x01"),
        Annotation("attachment", 1, (500, 10, 516, 26), data=b"\x00\xffbytes", filename="notes.txt"),
        Annotation("redact", 1, (50, 700, 300, 720), "#ff0000", fill="#000000", overlay="GONE", overlay_repeat=True,
                   repeat="2-3"),
    ]
    target = keep(sample, doc, wanted)
    text = target.read_text(encoding="utf-8")
    assert text.startswith("<?xml") and 'format="py-pdftools"' in text
    assert '<page number="2" rotation="90"' in text
    kept = sidecar.read(target)
    assert kept.annotations == wanted and kept.pages == 3
    assert sidecar.find(sample) == target


def test_unreadable(sample):
    target = sidecar.beside(sample)
    target.write_text("<annotations format='other'/>", encoding="utf-8")
    with pytest.raises(AnnotateError):
        sidecar.read(target)
    target.write_text("<annotations", encoding="utf-8")
    with pytest.raises(AnnotateError):
        sidecar.read(target)


def annotated(sample, tmp_path):
    """A copy of SAMPLE with three annotations of its own, and those annotations as read()."""
    path = tmp_path / "book.pdf"
    annots.write(sample, [Annotation("rect", 0, (10, 10, 60, 60), "#ff0000", contents="first"),
                          Annotation("note", 0, (100, 100, 116, 116), "#ffd54f", contents="second",
                                     replies=(Reply("B", "yes"),)),
                          Annotation("ellipse", 1, (200, 200, 260, 240), "#0000ff", contents="third")], path)
    return path, annots.read(annots.open_pdf(path))


def test_combined_with_the_pdf(sample, tmp_path):
    path, in_pdf = annotated(sample, tmp_path)
    doc = annots.open_pdf(path)
    first, second, third = editable(in_pdf)
    # Kept apart: the first changed, the second deleted, the third as it was, and a new one.
    changed = dataclasses.replace(first, contents="first, changed")
    new = Annotation("highlight", 1, (10, 10, 100, 20), quads=((10, 10, 100, 20),))
    keep(path, doc, [changed, third, new], in_pdf)
    before = path.read_bytes()
    out = sidecar.combine(doc, in_pdf, sidecar.read(sidecar.find(path)))
    assert path.read_bytes() == before  # (the PDF untouched)
    assert editable(out.annotations) == [changed, third, new]
    assert out.annotations[0].xref == first.xref and out.annotations[2].xref == 0
    assert out.new_in_pdf == 0
    # Into the PDF again: the PDF's own are changed where they are, the deleted one goes, the new one is added.
    target = tmp_path / "back.pdf"
    annots.write(path, out.annotations, target, original=in_pdf)
    again = editable(annots.read(annots.open_pdf(target)))
    assert [(a.kind, a.contents) for a in again] == [("rect", "first, changed"), ("ellipse", "third"),
                                                     ("highlight", "")]
    assert again[0].xref == first.xref and again[1].xref == third.xref


def test_what_another_program_did(sample, tmp_path):
    path, in_pdf = annotated(sample, tmp_path)
    doc = annots.open_pdf(path)
    first, second, third = editable(in_pdf)
    keep(path, doc, [first, second, third], in_pdf)
    # Another program saves the PDF whole (new numbers for its objects) and adds an annotation of its own.
    with pikepdf.open(path, allow_overwriting_input=True) as pdf:
        pdf.save(path, object_stream_mode=pikepdf.ObjectStreamMode.generate)
    added = tmp_path / "added.pdf"
    annots.write(path, annots.read(annots.open_pdf(path)) + [Annotation("rect", 2, (5, 5, 50, 50), "#00ff00")], added)
    os.replace(added, path)
    doc = annots.open_pdf(path)
    in_pdf = annots.read(doc)
    out = sidecar.combine(doc, in_pdf, sidecar.read(sidecar.find(path)))
    assert bare(editable(out.annotations)) == bare([first, second, third]) + bare([editable(in_pdf)[-1]])
    assert out.new_in_pdf == 1
    # (each kept one has the xref the PDF gives it now, its reply too)
    now = {a.contents: a for a in in_pdf}
    assert [a.xref for a in editable(out.annotations)[:3]] == [now[c].xref for c in ("first", "second", "third")]
    assert editable(out.annotations)[1].replies[0].xref == now["second"].replies[0].xref


def test_page_turned_since(sample, tmp_path):
    doc = annots.open_pdf(sample)
    wanted = [Annotation("rect", 0, (100, 200, 180, 260), "#ff0000"),
              Annotation("ink", 0, (100, 300, 150, 330), paths=(((100, 300), (150, 330)),)),
              Annotation("highlight", 0, (60, 60, 300, 75), quads=((60, 60, 300, 75),))]
    keep(sample, doc, wanted)
    # What the PDF would show, had the annotations been in it when the page was turned.
    inside = sample.with_name("inside.pdf")
    annots.write(sample, wanted, inside)
    for path in (sample, inside):
        with pymupdf.open(path) as d:
            d[0].set_rotation(90)
            d.save(path, incremental=True, encryption=pymupdf.PDF_ENCRYPT_KEEP)
    expected = editable(annots.read(annots.open_pdf(inside)))
    doc = annots.open_pdf(sample)
    out = sidecar.combine(doc, [], sidecar.read(sidecar.find(sample)))
    assert out.turned == 3
    got, want = out.annotations, expected
    assert all(abs(x - y) < 1.5 for x, y in zip(got[0].rect, want[0].rect))
    # (an ink's frame is MuPDF's, wider than its stroke: the stroke is compared)
    assert all(abs(x - y) < 1.5 for p, q in zip(got[1].paths[0], want[1].paths[0], strict=True) for x, y in zip(p, q))
    assert all(abs(x - y) < 1.5 for x, y in zip(out.annotations[2].quads[0], expected[2].quads[0]))


def test_pages_gone(sample):
    doc = annots.open_pdf(sample)
    keep(sample, doc, [Annotation("rect", 2, (10, 10, 60, 60))])
    with pymupdf.open(sample) as d:
        d.delete_page(2)
        d.save(sample.with_name("two.pdf"))
    doc = annots.open_pdf(sample.with_name("two.pdf"))
    out = sidecar.combine(doc, [], sidecar.read(sidecar.beside(sample)))
    assert out.annotations == [] and out.dropped == 1


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="needs a folder that can't be written")
def test_folder_not_writable(sample, tmp_path):
    folder = tmp_path / "locked"
    folder.mkdir()
    pdf = folder / "book.pdf"
    pdf.write_bytes(sample.read_bytes())
    folder.chmod(0o555)
    try:
        place = sidecar.place_for(pdf)
        assert place == sidecar.in_config(pdf) and place.name.startswith("book-")
        keep_doc = annots.open_pdf(pdf)
        sidecar.write(place, keep_doc, pdf.name, [Annotation("rect", 0, (1, 1, 5, 5))], {})
        assert sidecar.find(pdf) == place
        sidecar.remove(pdf)
        assert sidecar.find(pdf) is None
    finally:
        folder.chmod(0o755)


def test_imported_from_a_copy_that_keeps_them_apart(sample, tmp_path):
    path, in_pdf = annotated(sample, tmp_path)
    doc = annots.open_pdf(path)
    first, second, third = editable(in_pdf)
    keep(path, doc, [dataclasses.replace(first, contents="changed"), third], in_pdf)
    found = exchange.import_pdf(path)
    assert [(a.contents, a.xref) for a in found] == [("changed", 0), ("third", 0)]
