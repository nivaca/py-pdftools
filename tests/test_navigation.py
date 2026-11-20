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


def titles(window) -> list[tuple[int, str]]:
    return [(e[0], e[1]) for e in window.doc.get_toc()]


def test_editing_bookmarks(window, monkeypatch):
    """Added at the place shown, renamed, moved, indented, styled, pointed elsewhere, deleted; each a change
    of the document, undone like the others."""
    from PySide6.QtWidgets import QColorDialog

    tree = window.outline_tree
    window.show_page(2)
    assert window.add_bookmark("Interlude")
    # (after the bookmark marked for page 3: Chapter 1, its branch closed)
    assert titles(window) == [(1, "Chapter 1"), (2, "Section 1.1"), (1, "Interlude"), (1, "Chapter 2")]
    tree.setCurrentItem(next(item for _, item in window._outline_items() if item.text(0) == "Interlude"))
    assert window.move_bookmark("in")  # (under Chapter 1, after Section 1.1)
    assert (2, "Interlude") in titles(window)
    item = next(i for _, i in window._outline_items() if i.text(0) == "Interlude")
    tree.setCurrentItem(item)
    assert window.move_bookmark("up")
    assert titles(window)[:3] == [(1, "Chapter 1"), (2, "Interlude"), (2, "Section 1.1")]
    tree.setCurrentItem(next(i for _, i in window._outline_items() if i.text(0) == "Interlude"))
    item = tree.currentItem()
    item.setText(0, "Prelude")  # (as typed after F2)
    assert ("Prelude" in [t for _, t in titles(window)])
    tree.setCurrentItem(next(i for _, i in window._outline_items() if i.text(0) == "Prelude"))
    assert window.style_bookmark("bold")
    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *a, **k: __import__(
        "PySide6.QtGui", fromlist=["QColor"]).QColor("#ff0000")))
    tree.setCurrentItem(next(i for _, i in window._outline_items() if i.text(0) == "Prelude"))
    assert window.style_bookmark("color")
    full = {e[1]: e[3] for e in window.doc.get_toc(simple=False)}
    assert full["Prelude"].get("bold") and full["Prelude"].get("color") == (1.0, 0.0, 0.0)
    window.show_page(5)
    tree.setCurrentItem(next(i for _, i in window._outline_items() if i.text(0) == "Prelude"))
    assert window.point_bookmark_here()
    assert {e[1]: e[2] for e in window.doc.get_toc()}["Prelude"] == 6
    tree.setCurrentItem(next(i for _, i in window._outline_items() if i.text(0) == "Prelude"))
    assert window.delete_bookmark()
    assert "Prelude" not in [t for _, t in titles(window)]
    window.undo()
    assert "Prelude" in [t for _, t in titles(window)]


def test_bookmarks_from_the_headings(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    path = tmp_path / "headed.pdf"
    doc = pymupdf.open()
    for c in (1, 2):
        page = doc.new_page()
        page.insert_text((72, 80), f"Chapter {c}", fontsize=24)
        page.insert_text((72, 130), f"Part {c}.1", fontsize=16)
        for i in range(12):
            page.insert_text((72, 170 + i * 18), "Body text of the chapter, in a smaller type.", fontsize=11)
    doc.save(path)
    w = MainWindow()
    w.ask_recover = lambda when: False
    assert w.open_path(path)
    assert w.bookmarks_from_headings()
    assert titles(w) == [(1, "Chapter 1"), (2, "Part 1.1"), (1, "Chapter 2"), (2, "Part 2.1")]
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    assert w.bookmarks_from_headings()  # (added after those there were)
    assert len(titles(w)) == 8
    w.annotations = w.saved = []
    w.drop_work()
    w.close()
