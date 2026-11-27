"""The mode Pages of the window: labels, headers and footers, watermarks and the view on opening,
each a step of the history, shown at once and written when the document is saved."""

from __future__ import annotations

import shutil
from pathlib import Path

import pikepdf
import pymupdf
import pytest
from PySide6.QtWidgets import QApplication, QLabel

from py_pdftools.gui.window import MainWindow
from py_pdftools.pages import labels, stamps
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
    assert window.page_list.item(0).text().endswith("i") and window.pages.item(8).text() == "1"  # (the label only, not "9  1")
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
    with pikepdf.open(window.path) as pdf:  # (PyMuPDF before 2.0 misreads some labels)
        assert labels.page_labels(labels.read_labels(pdf), 100)[0] == "i"


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


def all_texts(menu) -> list[str]:
    """The texts of MENU's entries, and of those of its submenus."""
    out = []
    for a in menu.actions():
        out.append(a.text())
        if a.menu() is not None:
            out += all_texts(a.menu())
    return out


def test_view_on_opening_and_menus(window, monkeypatch):
    assert window.set_view_part("layout", "TwoPageRight")
    assert window.pages_state().opening.layout == "TwoPageRight"
    shown = []
    monkeypatch.setattr(window, "show_menu", lambda menu, where: shown.append(menu))
    window.page_list.setCurrentRow(3)
    window.pages_menu(window.page_list.visualItemRect(window.page_list.item(3)).center())
    texts = all_texts(shown[-1])
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


def test_the_page_box_shows_and_takes_labels(window, app):
    """The page box (of Page navigation, the only one) shows the label of the page shown, and goes to a page
    by its label, by (n) or by a number; beside it, how many pages there are, with the page's details as tip."""
    window.set_ranges([Range(1, "r"), Range(5, "D")])
    window.show_page(2)
    box = window.a_page_number.boxes()[0]
    count = window.a_page_number.createdWidgets()[0].findChild(QLabel, "count")
    assert box.text() == "iii" and count.text() == "of 100"
    assert "Page 3 of 100" in count.toolTip()
    for typed, page in (("IV", 3), ("1", 4), ("(2)", 1), ("100", 99)):  # (no page is labelled 100)
        box.setText(typed)
        box.returnPressed.emit()
        assert window.page == page, typed
    window.show_page(6)
    assert box.text() == "3" and count.text() == "of 100"
    assert not window.go_to_typed("nothing") and window.page == 6 and box.text() == "3"


def test_the_page_box_is_shown_once(window):
    """Only Page navigation has a box of the page: the toolbar at the top has the zoom alone."""
    from PySide6.QtWidgets import QComboBox, QLineEdit

    bar = next(b for b in window.toolbars() if b.objectName() == "pagezoom")
    assert bar.findChildren(QComboBox) == [window.zoom_label]
    assert [e for e in bar.findChildren(QLineEdit) if e is not window.zoom_label.lineEdit()] == []


def test_several_thumbnails_chosen_in_any_mode(window, app, monkeypatch):
    """Ctrl+click chooses several thumbnails without moving; they are Foliate's pages chosen too; the page
    shown follows the view without losing them; their menu is the menu of pages, in any mode."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    window.set_mode("annotate")
    window.show_page(1)
    thumbs = window.pages
    monkeypatch.setattr(QApplication, "keyboardModifiers", staticmethod(lambda: Qt.KeyboardModifier.ControlModifier))
    for row in (4, 6):
        thumbs.item(row).setSelected(True)
        thumbs.setCurrentRow(row, __import__("PySide6.QtCore", fromlist=["QItemSelectionModel"])
                             .QItemSelectionModel.SelectionFlag.NoUpdate)
    assert window.page == 1 and window.selected_pages() == [2, 5, 7]
    assert sorted(window.page_list.row(i) for i in window.page_list.selectedItems()) == [1, 4, 6]
    monkeypatch.setattr(QApplication, "keyboardModifiers", staticmethod(lambda: Qt.KeyboardModifier.NoModifier))
    window.show_page(9)  # (the view moves: the pages chosen stay chosen)
    assert window.selected_pages() == [2, 5, 7] and thumbs.currentRow() == 9
    shown = []
    monkeypatch.setattr(window, "show_menu", lambda menu, where: shown.append(
        [a.text() for a in menu.actions() if a.text()]))
    window.thumbs_menu(thumbs.visualItemRect(thumbs.item(4)).center())
    assert any("Delete" in t for t in shown[0]) and any("OCR" in t for t in shown[0])
    # (a page right-clicked outside them becomes the one chosen)
    window.thumbs_menu(thumbs.visualItemRect(thumbs.item(9)).center())
    assert window.selected_pages() == [10]
    # (Foliate's list chooses for the thumbnails too)
    window.page_list.clearSelection()
    for row in (0, 1):
        window.page_list.item(row).setSelected(True)
    assert window.selected_pages() == [1, 2] and {i.row() for i in thumbs.selectedIndexes()} == {0, 1}


def test_the_menu_of_pages_in_groups(window):
    """The menu of the pages chosen: a heading naming them, the actions used most at its top, the others
    in submenus by kind."""
    window.set_ranges([Range(1, "r"), Range(5, "D")])
    window.page_list.clearSelection()
    window.page_list.item(2).setSelected(True)
    menu = window.build_pages_menu()
    top = [a.text() for a in menu.actions() if a.text()]
    assert top[0] == "Page 3 (iii)"
    assert top[1:6] == ["Rotate", "Duplicate", "Copy to a new PDF…", "Move to a new PDF…", "Delete"]
    subs = [a.text() for a in menu.actions() if a.menu() is not None]
    assert subs == ["Rotate", "Move", "Insert", "Labels", "Header, footer and watermark", "More page actions",
                    "Initial view"]
    labels_menu = next(a.menu() for a in menu.actions() if a.text() == "Labels")
    assert "Number this page…" in all_texts(labels_menu) and len(top) < 14
    # "More page actions" has only what the menu has nowhere else (no Extract, Move…, Insert from file, Replace).
    more = next(a.menu() for a in menu.actions() if a.text() == "More page actions")
    assert [a.text() or "-" for a in more.actions()] == ["Rotate…", "Delete…", "Duplicate…", "Reverse pages…",
                                                          "New order…", "-", "Insert blank pages…", "-", "Split…"]
    for row in (3, 4, 5, 8):
        window.page_list.item(row).setSelected(True)
    menu = window.build_pages_menu()
    assert menu.actions()[0].text() == "Pages 3–6, 9 (5)"
    assert "Reverse their order" in all_texts(next(a.menu() for a in menu.actions() if a.text() == "Move"))
    # (the thumbnails' menu is the same, with OCR at its end)
    shown = []
    window.show_menu = lambda m, where: shown.append(m)
    window.thumbs_menu(window.pages.visualItemRect(window.pages.item(4)).center())
    assert shown and "OCR" in [a.text() for a in shown[0].actions() if a.text()][-1]


def test_pages_copied_and_moved_to_a_new_pdf(window, tmp_path, monkeypatch):
    from py_pdftools.annotate import annots
    from py_pdftools.annotate.annots import Annotation
    from py_pdftools.gui import tabs

    opened = []
    monkeypatch.setattr(tabs, "open_in_tab", lambda path, near=None: opened.append(path))
    count = window.count
    window.change([Annotation("rect", 1, (50, 50, 150, 150), "#ff0000", contents="on page 2")])
    # Copied: the new PDF has pages 2 and 3, with the annotation; the document is as it was.
    copy = tmp_path / "copy.pdf"
    window.ask_new_pdf = lambda title, name: copy
    assert window.pages_to_new_pdf([2, 3])
    with pymupdf.open(copy) as doc:
        assert doc.page_count == 2
    assert [a.contents for a in annots.read(annots.open_pdf(copy)) if a.kind != annots.OTHER] == ["on page 2"]
    assert window.count == count and opened == [copy]
    # Moved: the same, and the pages deleted here, as a step Undo takes back.
    moved = tmp_path / "moved.pdf"
    window.ask_new_pdf = lambda title, name: moved
    assert window.pages_to_new_pdf([2, 3], move=True)
    assert pymupdf.open(moved).page_count == 2 and window.count == count - 2 and opened[-1] == moved
    assert all(a.page != 1 or a.kind == annots.OTHER for a in window.annotations)
    window.undo()
    assert window.count == count
    # Never all of them: a document keeps one page.
    assert not window.pages_to_new_pdf(list(range(1, count + 1)), move=True)
