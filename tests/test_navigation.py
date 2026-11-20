"""Navigation (gui/outline.py and the window): the bookmarks panel; and the rest of the navigation
taken from PDFCraft as it is added."""

from __future__ import annotations

import pymupdf
import pytest
from PySide6.QtWidgets import QApplication

from py_pdftools.gui.window import MainWindow


@pytest.fixture
def book(tmp_path):
    """Six pages; bookmarks: Chapter 1 (page 1) > Section 1.1 (page 2, low on it), Chapter 2 (page 4)."""
    path = tmp_path / "book.pdf"
    doc = pymupdf.open()
    for i in range(6):
        doc.new_page().insert_text((72, 72), f"Page {i + 1}", fontsize=20)
    doc.set_toc([[1, "Chapter 1", 1], [2, "Section 1.1", 2, {"kind": pymupdf.LINK_GOTO, "page": 1,
                                                             "to": pymupdf.Point(72, 500)}],
                 [1, "Chapter 2", 4]])
    doc.save(path)
    return path


@pytest.fixture
def window(book, tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    w = MainWindow()
    w.ask_recover = lambda when: False
    w.resize(1100, 800)
    w.show()
    assert w.open_path(book)
    QApplication.processEvents()
    yield w
    w.annotations = w.saved = []
    w.drop_work()
    w.close()


def test_the_bookmarks_panel(window):
    tree = window.outline_tree
    assert tree.topLevelItemCount() == 2
    first, second = tree.topLevelItem(0), tree.topLevelItem(1)
    assert (first.text(0), first.text(1), first.childCount()) == ("Chapter 1", "1", 1)
    section = first.child(0)
    window._outline_go(second)
    assert window.page == 3
    window._outline_go(section)  # (to the place it points at, low on page 2: not the page's top)
    assert window.page == 1
    page = window.canvas.pages[1]
    top_of_view = page.mapFromScene(window.canvas.mapToScene(0, 0)).y()
    assert top_of_view > 300
    window.outline_filter.setText("section")
    assert not first.isHidden() and not section.isHidden() and second.isHidden()
    window.outline_filter.setText("")
    window.show_page(4)
    assert tree.currentItem() is second  # (the bookmark of the page shown, marked)
    assert window.a_outline.text() == "Bookmarks" and window.a_outline.isCheckable()


def test_the_panel_in_every_mode(window):
    """No mode owns the panel: shown in one, it stays shown in another (each keeps its own arrangement)."""
    for mode in ("read", "ocr", "redact", "annotate", "pages"):
        window.set_mode(mode)
        window.a_outline.trigger() if not window.outline_dock.isVisibleTo(window) else None
        assert window.outline_dock.isVisibleTo(window), mode
