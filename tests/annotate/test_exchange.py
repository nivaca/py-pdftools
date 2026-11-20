"""Annotations exported, imported, kept for recovery; flattened copies and copies without them; the settings."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pymupdf
from test_annots import one_of_each

from py_pdftools.annotate import annots, exchange, recovery, settings
from py_pdftools.annotate.annots import Annotation


def test_json_round_trip(sample, tmp_path):
    wanted = one_of_each(sample, 0)
    doc = annots.open_pdf(sample)
    target = tmp_path / "out.json"
    exchange.export_json(doc, sample, wanted, target)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["document"]["pages"] == 3 and data["annotations"][0]["marked_text"] == "First line of page 1"
    assert exchange.import_json(target) == wanted


def test_import_from_another_copy(sample, tmp_path):
    other = tmp_path / "other.pdf"
    annots.write(sample, [Annotation("rect", 1, (10, 10, 60, 60), "#000000", author="Reviewer B")], other)
    found = exchange.import_pdf(other)
    assert [(a.kind, a.author, a.xref) for a in found] == [("rect", "Reviewer B", 0)]
    assert exchange.merged(found, exchange.import_pdf(other)) == []  # (already there)


def test_report_and_csv(sample, tmp_path):
    wanted = one_of_each(sample, 0)
    doc = annots.open_pdf(sample)
    text = exchange.report(doc, sample, wanted)
    assert text.startswith("# Annotations of sample.pdf") and "> First line of page 1" in text
    assert "* Highlight: 1" in text
    exchange.export_csv(doc, wanted, tmp_path / "out.csv")
    rows = list(csv.reader((tmp_path / "out.csv").open(encoding="utf-8")))
    assert rows[0][0] == "page" and len(rows) == len(wanted) + 1
    assert exchange.quotation(doc, wanted[0], "sample.pdf") == "“First line of page 1” (sample.pdf, p. 1)"


def test_flattened_and_without(sample, tmp_path):
    flat = tmp_path / "flat.pdf"
    exchange.save_flattened(sample, [Annotation("rect", 0, (10, 10, 60, 60), "#ff0000", width=4)], flat)
    doc = pymupdf.open(flat)
    assert list(doc[0].annots()) == [] and doc[0].get_drawings()  # (drawn on the page now)
    annotated = tmp_path / "annotated.pdf"
    annots.write(sample, one_of_each(sample, 0), annotated)
    assert exchange.save_without(annotated, tmp_path / "bare.pdf") >= len(one_of_each(sample, 0))
    assert list(pymupdf.open(tmp_path / "bare.pdf")[0].annots()) == []


def test_recovery(sample):
    kept = [Annotation("rect", 0, (10, 10, 60, 60), "#000000", xref=12)]
    recovery.keep(sample, kept)
    when, found = recovery.find(sample)
    assert found == kept and when
    sample.write_bytes(sample.read_bytes() + b"\n")  # (the file changed: the copy is of no use)
    assert recovery.find(sample) is None
    recovery.discard(sample)


def test_settings_round_trip():
    prefs = settings.load()
    assert prefs == settings.DEFAULTS
    style = settings.Style("#123456", fill="#abcdef", width=3.0, font="tiro", start="Circle", end="ClosedArrow",
                           dashed=True, sticky=False, show="properties")
    prefs = prefs.with_style("line", style)
    prefs = settings.Settings(author="Me", styles=prefs.styles, palette=(("#ffeb3b", "Key ideas"),)
                              + prefs.palette[1:], shortcuts=tuple((k, "Ctrl+Alt+H" if k == "highlight" else v) for k, v in prefs.shortcuts),
                              autosave=5)
    settings.save(prefs)
    again = settings.load()
    line = again.style("line")
    # (what a line has no use for is not kept: its fill and font)
    assert (line.color, line.width, line.start, line.end, line.dashed, line.sticky, line.show) == \
        ("#123456", 3.0, "Circle", "ClosedArrow", True, False, "properties")
    assert line.fill == "" and line.font == "helv"
    assert again.author == "Me" and again.autosave == 5 and again.palette[0] == ("#ffeb3b", "Key ideas")
    assert again.shortcut("highlight") == "Ctrl+Alt+H"


def test_conform_missing(sample, tmp_path, monkeypatch):
    from py_pdftools.core import conform

    monkeypatch.setattr(conform, "command", lambda path=None: None)
    import pytest

    with pytest.raises(conform.ConformError):
        conform.convert(sample, tmp_path / "x.pdf", "a-2b")




def test_partly_flattened(sample, tmp_path):
    tri = ((60.0, 500.0), (160.0, 520.0), (110.0, 580.0))
    wanted = [Annotation("polygon", 0, annots.frame("polygon", (tri,), 1.5), "#000000", paths=(tri,)),
              Annotation("rect", 0, (10, 10, 60, 60), "#ff0000")]
    target = tmp_path / "out.pdf"
    exchange.save_partly_flattened(sample, wanted, target, kinds={"polygon"})
    doc = annots.open_pdf(target)
    assert [a.kind for a in annots.read(doc)] == ["rect"] and doc[0].get_drawings()
    assert exchange.kinds_lost(wanted, target) == {"polygon": 1}


import dataclasses  # noqa: E402

import pytest  # noqa: E402


@pytest.mark.parametrize("page", [0, 2])
def test_xfdf_round_trip(sample, tmp_path, page):
    wanted = one_of_each(sample, page)
    wanted[0] = dataclasses.replace(wanted[0], replies=(annots.Reply("B", "Why?"),
                                                        annots.Reply("C", "Agreed", state="Accepted")))
    doc = annots.open_pdf(sample)
    target = tmp_path / "out.xfdf"
    exchange.export_xfdf(doc, sample, wanted, target)
    text = target.read_text(encoding="utf-8")
    assert text.startswith('<?xml') and "<highlight" in text and 'inreplyto="py-pdftools-1"' in text
    got = exchange.import_xfdf(doc, target)
    assert [a.kind for a in got] == [a.kind for a in wanted]
    for w, g in zip(wanted, got):
        assert annots.same(dataclasses.replace(w, image=b""), dataclasses.replace(g, image=b""), tolerance=1.5), \
            (w.kind, w, g)
    assert [(r.author, r.contents, r.state) for r in got[0].replies] == [("B", "Why?", ""),
                                                                         ("C", "Agreed", "Accepted")]


def test_summary(sample, tmp_path):
    wanted = one_of_each(sample, 0)[:3] + [Annotation("note", 1, (300, 200, 316, 216), "#ffd54f",
                                                      contents="See page two", author="B")]
    target = tmp_path / "summary.pdf"
    pages = exchange.save_summary(sample, wanted, target)
    doc = pymupdf.open(target)
    assert pages == doc.page_count == 2
    text = doc[0].get_text()
    assert "Page 1" in text and "1. Highlight" in text and "First line of page 1" in text and "look" in text
    assert "See page two" in doc[1].get_text() and doc[0].rect.width > 595


def test_textual_criticism(sample, tmp_path):
    """An entry of textual criticism is kept in the PDF, in JSON and in the CSV, and makes the
    critical apparatus, in the order of the text."""
    from py_pdftools.annotate.annots import Critical

    doc = annots.open_pdf(sample)
    found = annots.words(doc[0])
    rects = annots.text_rects(found, 0, 0)  # (the first word)
    entry = Critical("variant", lemma="iustitia", reading="iusticia", witness="B", location="f. 3r",
                     source="ed. Smith", rationale="orthographic", confidence="probable")
    made = [Annotation("highlight", 0, annots.union(rects[:1]), quads=tuple(rects[:1]), critical=entry),
            Annotation("rect", 0, (60, 300, 120, 340), "#000000", critical=Critical("lacuna")),
            Annotation("rect", 1, (60, 300, 120, 340), "#000000")]
    path = tmp_path / "doc.pdf"
    annots.write(sample, made, path)
    got = annots.read(annots.open_pdf(path))
    assert [a.critical for a in got] == [entry, Critical("lacuna"), None]
    assert [exchange.from_data(exchange.to_data(a)) for a in made] == made
    exchange.export_csv(doc, got, tmp_path / "a.csv")
    rows = list(csv.DictReader((tmp_path / "a.csv").open(encoding="utf-8")))
    assert rows[0]["lemma"] == "iustitia" and rows[0]["witness"] == "B" and rows[2]["critical_type"] == ""
    text = exchange.apparatus(doc, path, got)
    lines = [line for line in text.splitlines() if line.startswith("* ")]
    assert len(lines) == 2
    assert lines[0].startswith("* **p. 1** *iustitia* ] iusticia B (f. 3r) — Variant reading; probable.")
    assert "ed. Smith. orthographic." in lines[0]
    assert "Lacuna." in lines[1]


def scanned_pdf(path, rotation=0):
    """A PDF of one scanned page: an image of a text, without text (turned, if ROTATION)."""
    import pymupdf

    src = pymupdf.open()
    page = src.new_page()
    page.insert_textbox((72, 72, 520, 300), "Quod iustitia est, quaerimus. The question of justice is old.",
                        fontsize=16)
    pix = page.get_pixmap(dpi=200)
    doc = pymupdf.open()
    if rotation:
        page = doc.new_page(width=842, height=595)
        page.insert_image(page.rect, pixmap=pix, rotate=rotation)
        page.set_rotation(rotation)
    else:
        page = doc.new_page(width=595, height=842)
        page.insert_image(page.rect, pixmap=pix)
    doc.save(path)
    return path


@pytest.mark.parametrize("rotation", [0, 90])
def test_ocr(tmp_path, rotation):
    """The text of a scanned page is read and written under its image, where the image has it, so it
    is found and marked; the annotations go into the copy too."""
    from py_pdftools.annotate import ocr

    if not ocr.available() or "eng" not in ocr.languages():
        pytest.skip("Tesseract (with English) is not installed")
    source = scanned_pdf(tmp_path / "scan.pdf", rotation)
    doc = annots.open_pdf(source)
    assert ocr.scanned(doc[0]) and annots.words(doc[0]) == []
    note = Annotation("rect", 0, (60, 600 if not rotation else 400, 120, 640 if not rotation else 440), "#ff0000")
    seen = []
    pages, words = ocr.save_searchable(source, [note], tmp_path / "out.pdf", "", "eng",
                                       lambda done, of: seen.append((done, of)) or True)
    assert pages == 1 and words >= 8 and seen == [(0, 1)]
    out = annots.open_pdf(tmp_path / "out.pdf")
    assert not ocr.scanned(out[0])
    found = annots.page_text(out[0])
    texts = [t for _, t in found]
    assert "justice" in texts and "iustitia" in texts
    hits = out[0].search_for("justice")
    assert hits and len(annots.read(out)) == 1
    # (where the word is on the image: OCR of the copy rendered finds it in the same place)
    page = out[0]
    again = page.get_text("words", textpage=page.get_textpage_ocr(language="eng", dpi=200, full=True))
    box = next(pymupdf.Rect(w[:4]) for w in again if w[4] == "justice")
    assert hits[0].intersects(box)


def version(path, text):
    import pymupdf

    doc = pymupdf.open()
    doc.new_page().insert_textbox((72, 72, 520, 760), text, fontsize=12)
    doc.save(path)
    return path


def test_compare(tmp_path):
    """The words of two versions lined up: what changed, what is only here, what is only there."""
    from py_pdftools.annotate import compare

    here = annots.open_pdf(version(tmp_path / "a.pdf", "Quod iustitia est, quaerimus. The question of justice is "
                                                       "very old.\nIt was asked by Plato."))
    there = annots.open_pdf(version(tmp_path / "b.pdf", "Quod iustitia sit, quaerimus. The question of justice is "
                                                        "old.\nIt was asked long ago by Plato."))
    found = compare.differences(here, there)
    assert [(d.kind, d.here, d.there) for d in found] == [
        ("changed", "est,", "sit,"), ("only_here", "very", ""), ("only_there", "", "long ago")]
    assert all(d.page == 0 and d.rects for d in found)
    assert compare.differences(here, here) == []
    shouting = annots.open_pdf(version(tmp_path / "c.pdf", "QUOD iustitia est, quaerimus. The question of justice "
                                                           "is very old.\nIt was asked by Plato."))
    assert len(compare.differences(here, shouting)) == 1 and compare.differences(here, shouting, ignore_case=True) == []


def test_compare_long_texts():
    """Long texts made of the same few words again and again are compared exactly (and quickly):
    patience diff, anchored on the words found once in each."""
    import random
    import time

    from py_pdftools.annotate import compare

    random.seed(3)
    vocab = [f"w{i}" for i in range(3000)]
    weights = [1 / (i + 1) for i in range(3000)]
    a = random.choices(vocab, weights, k=60000)
    b = list(a)
    b[1000] = "CHANGED"
    del b[30000]
    b.insert(50000, "ADDED")
    start = time.monotonic()
    ops = [op for op in compare.opcodes(a, b) if op[0] != "equal"]
    assert time.monotonic() - start < 10
    assert [op[0] for op in ops] == ["replace", "delete", "insert"]
    assert ops[0][1:3] == (1000, 1001) and ops[1][1:3] == (30000, 30001)
    rebuilt = []  # (the opcodes make B of A)
    for op, i1, i2, j1, j2 in compare.opcodes(a, b):
        rebuilt += a[i1:i2] if op == "equal" else b[j1:j2]
    assert rebuilt == b


def test_search_enhanced(tmp_path):
    """Words hyphenated at a line's end are found whole; accents, ligatures and (if asked) u/v and i/j
    are not minded; * and ? are wildcards; the text of the pages read is kept for the next search."""
    import pymupdf

    from py_pdftools.annotate.search import find_text, fold

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "The question of jus-", fontsize=12)
    page.insert_text((72, 116), "tice is old. Acción y cæsar.", fontsize=12)
    page.insert_text((72, 132), "Iustitia est uirtus; justitia, virtus. Iustus, iusto.", fontsize=12)
    found = find_text(doc, "justice")
    assert len(found) == 1 and len(found[0].rects) == 2  # (on two lines, one word)
    assert find_text(doc, "accion") == [] and len(find_text(doc, "accion", accents=True)) == 1
    assert len(find_text(doc, "caesar", accents=True)) == 1
    assert len(find_text(doc, "iustitia")) == 1 and len(find_text(doc, "iustitia", uv=True)) == 2
    assert len(find_text(doc, "virtus", uv=True)) == 2
    assert {m.text for m in find_text(doc, "iust*", wildcards=True)} == {"Iustitia", "Iustus", "iusto"}
    assert {m.text for m in find_text(doc, "iust?", wildcards=True, whole_words=True)} == {"iusto"}  # (one letter)
    assert find_text(doc, "acción", accents=True)[0].text == "Acción"  # (the text found, as it is written)
    cache: dict = {}
    find_text(doc, "old", cache=cache)
    assert 0 in cache and len(find_text(doc, "old", cache=cache)) == 1
    assert fold("Æneas, ſtrange") == ("AEneas, strange", [0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13])
