"""Splitting (pages/split.py, Pages > Split, py-pdftools pages --split-...): at the bookmarks of a level (each
part named after its bookmark), one file per page (named after its label), and by size (no part bigger
than asked, measured as written); and the window."""

from __future__ import annotations

import random

import pymupdf
import pytest

from py_pdftools.pages import split


@pytest.fixture
def book(tmp_path):
    rnd = random.Random(1)
    d = pymupdf.open()
    for i in range(12):
        p = d.new_page()
        p.insert_text((72, 72), f"Page {i + 1}", fontsize=12)
        if i % 3 == 0:  # (algo de peso, para partir por tamaño)
            data = bytes(rnd.randrange(256) for _ in range(200 * 150 * 3))
            p.insert_image(pymupdf.Rect(72, 100, 272, 250), pixmap=pymupdf.Pixmap(pymupdf.csRGB, 200, 150, data, 0))
    d.set_toc([[1, "Prologue", 2], [1, "Chapter: One/Two", 4], [2, "A section", 5], [1, "End", 10]])
    d.set_page_labels([{"startpage": 0, "prefix": "", "style": "r", "firstpagenum": 1},
                       {"startpage": 2, "prefix": "", "style": "D", "firstpagenum": 1}])
    d.save(tmp_path / "book.pdf")
    return tmp_path / "book.pdf"


def test_at_bookmarks(book):
    assert split.plan({"bookmarks": 1}, book) == [(1, 1, ""), (2, 3, "Prologue"), (4, 9, "Chapter One Two"),
                                                  (10, 12, "End")]
    assert split.plan({"bookmarks": 2}, book) == [(1, 4, ""), (5, 12, "A section")]
    with pytest.raises(Exception, match="level 3"):
        split.plan({"bookmarks": 3}, book)


def test_one_per_page_and_names(book):
    parts = split.plan({"every": 1}, book)
    assert len(parts) == 12 and parts[:3] == [(1, 1, "i"), (2, 2, "ii"), (3, 3, "1")]
    names = split.file_names("book", parts)
    assert names[:3] == ["book-01-i.pdf", "book-02-ii.pdf", "book-03-1.pdf"]
    assert split.file_names("b", [(1, 1, "x"), (2, 2, "x"), (3, 3, "")]) == ["b-1-x.pdf", "b-2-x.pdf", "b-3.pdf"]
    assert split.file_names("b", [(1, 1, "X"), (2, 2, "x")])[1] == "b-2-x.pdf"
    assert split.plan({"every": 5}, book) == [(1, 5, ""), (6, 10, ""), (11, 12, "")]
    assert split.plan({"at": [4, 9]}, book) == [(1, 3, ""), (4, 8, ""), (9, 12, "")]


def test_by_size(book):
    data = book.read_bytes()
    most = 200_000
    parts = split.plan({"size": most}, book)
    assert parts[0][0] == 1 and parts[-1][1] == 12
    assert all(a[1] + 1 == b[0] for a, b in zip(parts, parts[1:], strict=False))  # (seguidas, sin huecos)
    assert all(split._size(data, f, last, "") <= most for f, last, _ in parts)
    assert len(parts) > 1
    # (a page bigger than the size asked is a part by itself)
    assert all(f == last for f, last, _ in split.plan({"size": 1000}, book))


def test_command_line(book, tmp_path):
    from py_pdftools.cli import main

    out = tmp_path / "parts"
    assert main(["pages", str(book), "--split-bookmarks", "1", "--output-dir", str(out)]) == 0
    assert sorted(p.name for p in out.iterdir()) == ["book-1.pdf", "book-2-Prologue.pdf", "book-3-Chapter One Two.pdf",
                                                     "book-4-End.pdf"]
    with pymupdf.open(out / "book-3-Chapter One Two.pdf") as d:
        from py_pdftools.annotate.exchange import doc_labels

        assert d.page_count == 6 and doc_labels(d)[0] == "2"  # (leídas con pikepdf, como el programa las lee)
    assert main(["pages", str(book), "--split-size", "0.2", "--output-dir", str(tmp_path / "s")]) == 0
    assert all(p.stat().st_size <= 260_000 for p in (tmp_path / "s").iterdir())


def test_in_the_window(book, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from py_pdftools.gui.pages.arrange_dialog import ArrangeDialog
    from py_pdftools.gui.window import MainWindow

    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    d = ArrangeDialog(None, "split", 12, folder=tmp_path)
    d.at_level.setValue(1)
    assert d.value() == ({"bookmarks": 1}, tmp_path)
    d.at_level.setValue(0)
    d.most.setValue(1.5)
    assert d.value() == ({"size": 1_500_000}, tmp_path)
    w = MainWindow()
    w.ask_recover = lambda when: False
    try:
        assert w.open_path(book)
        assert w.split_document({"every": 1}, tmp_path / "pages")
        assert len(list((tmp_path / "pages").iterdir())) == 12
        assert (tmp_path / "pages" / "book-01-i.pdf").is_file()
    finally:
        w.close()
