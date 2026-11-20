"""The mode Pages of the window: labels, headers and footers, watermarks and the view on opening,
each a step of the history, shown at once and written when the document is saved."""

from __future__ import annotations

import shutil
from pathlib import Path

import pikepdf
import pymupdf
import pytest
from PySide6.QtWidgets import QApplication

from py_pdftools.gui.window import MainWindow
from py_pdftools.pages import stamps
from py_pdftools.pages.headfoot import HeaderFooter
from py_pdftools.pages.labels import Range
from py_pdftools.pages.watermark import Watermark

EXAMPLE = Path(__file__).resolve().parents[2] / "docs" / "example" / "numbers-100.pdf"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    book = tmp_path / "book.pdf"
    shutil.copy(EXAMPLE, book)
    w = MainWindow()
    w.ask_recover = lambda when: False
    w.resize(1200, 800)
    w.show()
    assert w.open_path(book)
    w.set_mode("pages")
    app.processEvents()
    yield w
    w.annotations = w.saved = []
    w.drop_work()
    w.close()


def test_labels_in_the_table_and_the_list(window):
    assert window.ranges_table.rowCount() == 0 and window.page_list.count() == 100
    window.show_page(8)
    window.add_range()  # (at the page shown)
    assert window.ranges == [Range(1), Range(9)]
    window._edit(0, style="r")
    QApplication.processEvents()  # (the change waits for the signal of the widget to be over)
    assert window.page_labels()[:3] == ["i", "ii", "iii"] and window.ranges_table.rowCount() == 2
    assert window.page_list.item(0).text().endswith("i") and "9  1" in window.pages.item(8).text()
    assert "labels set" in window.cmd_line.text()
    window.page_list.clearSelection()
    for row in (99,):
        window.page_list.item(row).setSelected(True)
    window.label_selected = lambda: window.set_ranges(
        __import__("py_pdftools.pages.labels", fromlist=["relabel"]).relabel(window.ranges, 100, {100: "Cover"}))
    assert window.label_selected() and window.page_labels()[99] == "Cover"
    window.go_to_label("iii")
    assert window.page == 2
    window.undo()
    assert window.page_labels()[99] == "92"
    assert window.save()
    assert pymupdf.open(window.path)[0].get_label() == "i"


def test_list_of_labels(window, tmp_path, monkeypatch):
    from py_pdftools.gui import paging

    listed = tmp_path / "list.txt"
    listed.write_text("\n".join(["Cover"] + [str(i) for i in range(1, 100)]) + "\n")
    assert window.import_labels(listed)
    assert window.page_labels()[:3] == ["Cover", "1", "2"]
    out = tmp_path / "out.txt"
    monkeypatch.setattr(paging.QFileDialog, "getSaveFileName", lambda *a, **k: (str(out), ""))
    assert window.export_labels_dialog()
    assert out.read_text().split("\n")[:2] == ["Cover", "1"]


def test_header_footer_and_watermark(window):
    hf = HeaderFooter(footer_center="Page $pagelabel of $totalpages", pages="2-4")
    assert window.add_stamp(hf)
    assert window.pages_with(stamps.HEADER_FOOTER) == {2, 3, 4}
    assert "Page 3 of 100" in window.doc[2].get_text()  # (shown at once)
    assert window.add_stamp(Watermark(text="DRAFT"))
    assert window.pages_with(stamps.WATERMARK) == set(range(1, 101))
    assert window.remove_stamps(stamps.HEADER_FOOTER, [3])
    assert window.pages_with(stamps.HEADER_FOOTER) == {2, 4}
    window.undo()
    assert window.pages_with(stamps.HEADER_FOOTER) == {2, 3, 4}
    assert window.last_added(stamps.HEADER_FOOTER)[1].footer_center == "Page $pagelabel of $totalpages"
    assert window.save()
    with pikepdf.open(window.path) as pdf:
        assert stamps.pages_with(pdf) == [2, 3, 4]


def test_annotations_stay_on_their_pages(window):
    """An annotation made in the mode Annotate goes with its page when the pages move."""
    from py_pdftools.annotate.annots import Annotation

    window.set_mode("annotate")
    window.add(Annotation("rect", 4, (100, 100, 200, 200), "#ff0000"))
    window.set_mode("pages")
    window.set_labels_rule("follow")
    assert window.move_pages([5], 1)
    assert [a.page for a in window.annotations] == [0]
    assert "5" in window.doc[0].get_text()


def test_view_on_opening_and_menus(window, monkeypatch):
    assert window.set_view_part("layout", "TwoPageRight")
    assert window.pages_state().opening.layout == "TwoPageRight"
    shown = []
    monkeypatch.setattr(window, "show_menu", lambda menu, where: shown.append(menu))
    window.page_list.setCurrentRow(3)
    window.pages_menu(window.page_list.visualItemRect(window.page_list.item(3)).center())
    texts = [a.text() for a in shown[-1].actions()]
    assert "Number this page…" in texts and "Duplicate" in texts
    window._fill_stamp_menu(window.m_headfoot, stamps.HEADER_FOOTER)
    assert [a.text() for a in window.m_headfoot.actions()][:2] == ["Add…", "Update…"]


def test_the_page_actions_belong_to_the_mode(window):
    assert window.a_rotate_right.isEnabled()
    window.set_mode("annotate")
    assert not window.a_rotate_right.isEnabled() and not window.page_list.isVisible()
    window.set_mode("pages")
    assert window.a_rotate_right.isEnabled()
    (page,) = window.selected_pages()
    window.a_rotate_right.trigger()
    assert [window.doc[i].rotation for i in range(window.count)].count(90) == 1
    assert window.doc[page - 1].rotation == 90
