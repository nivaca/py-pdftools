"""La comparación visual (pages/visual.py y gui/visualcompare.py): lo que difiere a la vista entre dos PDF, página
a página, enmarcado o superpuesto."""

from __future__ import annotations

import pymupdf
import pytest
from PySide6.QtWidgets import QApplication

from py_pdftools.gui.window import MainWindow
from py_pdftools.pages import visual


def book(path, changed: dict[int, str], pages: int = 6, box_on: int | None = None):
    """PAGES pages, each with a line; CHANGED gives another word for some pages; BOX_ON, a page with a box."""
    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 100), f"Page {i + 1}: the quick brown {changed.get(i, 'fox')}", fontsize=14)
        if i == box_on:
            page.draw_rect(pymupdf.Rect(300, 500, 400, 560), color=(0, 0, 0), fill=(0.5, 0.5, 0.5))
    doc.save(path)
    return path


def test_what_looks_different(tmp_path):
    a = pymupdf.open(book(tmp_path / "a.pdf", {}))
    b = pymupdf.open(book(tmp_path / "b.pdf", {0: "cat"}, box_on=0))
    rects = visual.differences(a[0], b[0])
    assert len(rects) == 2
    word, box = rects
    assert word[0] > 150 and word[1] < 100 < word[3] and word[2] < 260  # (the word, on its line)
    assert box[0] <= 300 and box[2] >= 400 and box[1] <= 500 and box[3] >= 560  # (the box, around it)
    assert visual.differences(a[1], b[1]) == []
    assert visual.differences(a[1], None) == [(0.0, 0.0, a[1].rect.width, a[1].rect.height)]
    pix = visual.tinted(a[0], visual.RED, 1.0)
    assert pix.pixel(0, 0) == (255, 255, 255)


@pytest.fixture
def window(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    w = MainWindow()
    w.ask_recover = lambda when: False
    w.resize(1200, 900)
    w.show()
    assert w.open_path(book(tmp_path / "here.pdf", {}))
    yield w
    w.annotations = w.saved = []
    w.drop_work()
    w.close()


def test_the_window_of_the_comparison(window, tmp_path):
    other = book(tmp_path / "there.pdf", {2: "cat", 4: "dog"}, pages=7)
    view = window.visual_compare(other)
    try:
        assert view is not None and view.count == 7 and view.page == 0
        assert "no difference" in view.said.text()
        assert view.go_difference(1) and view.page == 2 and "2 places" not in view.said.text()
        assert view.differences(2) and not view.picture.pixmap().isNull()
        side = view.picture.pixmap().height()
        view.how.setCurrentIndex(1)  # (superpuestas: una página sola a todo el ancho, el doble de alta)
        assert view.picture.pixmap().height() > side * 1.5
        assert view.go_difference(1) and view.page == 4
        assert view.go_difference(1) and view.page == 6 and "only in there.pdf" in view.said.text()
        assert not view.go_difference(1) and view.page == 6
        assert view.go_difference(-1) and view.page == 4
        view.number.setValue(2)
        assert view.page == 1
    finally:
        here, there = view.here, view.there
        view.close()
    assert here.is_closed and there.is_closed
    assert window.a_visual_compare.text() == "Compare visually…"
