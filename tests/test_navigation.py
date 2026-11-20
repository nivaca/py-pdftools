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


@pytest.fixture
def linked(tmp_path):
    """Page 1: a link to page 3 (low on it), a link to a web address, an address in the text, a mail address,
    a link to another PDF and one that starts a program."""
    other = tmp_path / "other.pdf"
    o = pymupdf.open()
    for _ in range(4):
        o.new_page()
    o.save(other)
    path = tmp_path / "linked.pdf"
    doc = pymupdf.open()
    for _ in range(4):
        doc.new_page()
    page = doc[0]
    page.insert_text((72, 300), "See www.example.org or write to someone@example.org.", fontsize=12)
    page.insert_link({"kind": pymupdf.LINK_GOTO, "from": pymupdf.Rect(72, 60, 200, 90), "page": 2,
                      "to": pymupdf.Point(0, 400)})
    page.insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(72, 120, 200, 150), "uri": "https://a.example"})
    page.insert_link({"kind": pymupdf.LINK_GOTOR, "from": pymupdf.Rect(72, 180, 200, 210), "file": "other.pdf",
                      "page": 3, "to": pymupdf.Point(0, 0)})
    page.insert_link({"kind": pymupdf.LINK_LAUNCH, "from": pymupdf.Rect(72, 230, 200, 260), "file": "/bin/true"})
    doc.save(path)
    return path


def press_release(w, page, point, modifiers=None):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    modifiers = modifiers or Qt.KeyboardModifier.NoModifier
    canvas = w.canvas
    pos = QPointF(canvas.mapFromScene(canvas.pages[page].mapToScene(QPointF(*point))))
    for kind, buttons in ((QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton),
                          (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton)):
        event = QMouseEvent(kind, pos, canvas.viewport().mapToGlobal(pos), Qt.MouseButton.LeftButton, buttons,
                            modifiers)
        (canvas.mousePressEvent if kind == QEvent.Type.MouseButtonPress else canvas.mouseReleaseEvent)(event)


def test_following_links(window, linked, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import QMessageBox

    assert window.open_path(linked)
    canvas = window.canvas
    kinds = [link["kind"] for _, link in canvas.page_links(0)]
    assert kinds.count(pymupdf.LINK_URI) == 3  # (the link, and the two addresses of the text)
    mail = [link["uri"] for _, link in canvas.page_links(0) if link.get("in_text")]
    assert mail == ["https://www.example.org", "mailto:someone@example.org"]
    window.set_tool("hand")
    press_release(window, 0, (100, 75))
    assert window.page == 2
    top = canvas.pages[2].mapFromScene(canvas.mapToScene(0, 0)).y()
    assert top > 300  # (low on the page, where the link points)
    window.show_page(0)
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(lambda url: opened.append(url.toString()) or True))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    press_release(window, 0, (100, 135))
    assert opened == []  # (asked first: and the answer was no)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    press_release(window, 0, (100, 135))
    assert opened == ["https://a.example"]
    window.set_tool("select")
    press_release(window, 0, (100, 75))  # (with Select, a plain click doesn't follow)
    assert window.page == 0
    press_release(window, 0, (100, 75), Qt.KeyboardModifier.ControlModifier)
    assert window.page == 2
    assert not window.follow_link(0, {"kind": pymupdf.LINK_LAUNCH, "file": "/bin/true"})
    window.show_page(1)
    assert window.follow_link(0, {"kind": pymupdf.LINK_NAMED, "name": "NextPage"}) and window.page == 2
    from py_pdftools.gui.window import _WINDOWS

    before = list(_WINDOWS)
    assert window.follow_link(0, canvas.page_links(0)[2][1])  # (to other.pdf, page 4)
    new = [w for w in _WINDOWS if w not in before]
    assert new and new[0].path.name == "other.pdf" and new[0].page == 3
    for w in new:
        w.close()


def test_the_history_of_jumps(window, book):
    """Bookmarks, the page box and links leave the place they leave in the history; Previous view and Next
    view go through it; a jump forgets what was ahead; another document starts afresh."""
    assert not window.a_back.isEnabled() and not window.a_forward.isEnabled()
    window._outline_go(window.outline_tree.topLevelItem(1))  # (Chapter 2: page 4)
    assert window.page == 3 and window.a_back.isEnabled()
    window.page_box.setText("6")
    window.page_box.returnPressed.emit()
    assert window.page == 5
    window.a_back.trigger()
    assert window.page == 3 and window.a_forward.isEnabled()
    window.a_back.trigger()
    assert window.page == 0 and not window.a_back.isEnabled()
    window.a_forward.trigger()
    assert window.page == 3
    window.go_place(1)  # (a new jump: what was ahead is forgotten)
    assert not window.a_forward.isEnabled()
    window.a_back.trigger()
    assert window.page == 3
    window.show_page(2)  # (moving page by page is not a jump)
    window.a_back.trigger()
    assert window.page == 0
    assert window.open_path(book)
    assert not window.a_back.isEnabled() and not window.a_forward.isEnabled()


def test_find_leaves_places_in_the_history(window):
    window.find_dialog("Page 5")
    finder = window.finder
    finder.search()
    finder.step(1)  # (to the first place found)
    QApplication.processEvents()
    assert finder.matches and window.page == 4
    window.a_back.trigger()
    assert window.page == 0
    finder.close()


def test_places_in_the_arguments(book):
    from py_pdftools.gui.navigation import split_place

    assert split_place(f"{book}#page=3") == (str(book), {"page": 3})
    assert split_place(f"{book}#nameddest=intro") == (str(book), {"name": "intro"})
    assert split_place(f"{book}#intro") == (str(book), {"name": "intro"})
    assert split_place(str(book)) == (str(book), {})
    assert split_place("missing.pdf#page=3") == ("missing.pdf#page=3", {})


def test_opening_where_it_was_left(window, book, tmp_path):
    other = tmp_path / "other.pdf"
    o = pymupdf.open()
    o.new_page()
    o.save(other)
    assert window.open_path(book, {"page": 3})
    assert window.page == 2
    window.canvas.set_zoom(1.5)
    window.go_place(4, 300)
    assert window.open_path(other)  # (the place of book.pdf, remembered)
    assert window.open_path(book)
    assert window.page == 4 and abs(window.canvas.zoom() - 1.5) < 0.01
    assert window._view_top() > 250


def test_opening_as_the_document_asks(window, tmp_path):
    path = tmp_path / "asks.pdf"
    doc = pymupdf.open()
    for _ in range(5):
        doc.new_page()
    doc.set_toc([[1, "One", 1], [1, "Three", 3]])
    catalog = doc.pdf_catalog()
    doc.xref_set_key(catalog, "PageMode", "/UseOutlines")
    doc.xref_set_key(catalog, "OpenAction", f"[{doc[2].xref} 0 R /FitH 842]")
    doc.save(path)
    window.outline_dock.hide()
    assert window.open_path(path)
    assert window.page == 2 and window.canvas.fit == "width" and window.outline_dock.isVisibleTo(window)


def test_the_last_session_opened_again(book, tmp_path, monkeypatch):
    from py_pdftools import gui
    from py_pdftools.core import config
    from py_pdftools.gui.window import _WINDOWS

    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    gui.save_session([book])
    monkeypatch.setattr(QApplication.instance(), "exec", lambda: 0)
    before = list(_WINDOWS)
    assert gui.main([]) == 0
    new = [w for w in _WINDOWS if w not in before]
    assert new and new[0].path is None  # (the setting is off)
    config.set("reopen", True)
    assert gui.main([]) == 0
    newer = [w for w in _WINDOWS if w not in before and w not in new]
    assert newer and newer[0].path == book
    for w in [w for w in _WINDOWS if w is not newer[0]]:
        w.close()
    gui.save_session([])
    newer[0].close()  # (the last window closed: its document is the session now)
    assert gui.session() == [str(book)]


def test_two_pages_side_by_side(window):
    canvas = window.canvas
    window.a_spread.setChecked(True)
    p = canvas.pages
    assert p[0].pos().y() == p[1].pos().y() and p[0].pos().x() < p[1].pos().x() < p[2].pos().x() + 1000
    assert p[2].pos().y() > p[0].pos().y()
    window.show_page(0)
    window.a_next.trigger()
    assert window.page == 2  # (a pair at a time)
    window.a_cover.setChecked(True)  # (the first page alone: then 1 and 2 together)
    p = canvas.pages
    assert p[1].pos().y() == p[2].pos().y() and p[0].pos().y() < p[1].pos().y()
    window.show_page(1)
    window.a_next.trigger()
    assert window.page == 3
    window.a_continuous.setChecked(False)  # (one pair at a time)
    assert sorted(canvas.pages) == [3, 4]
    window.a_continuous.setChecked(True)
    window.a_spread.setChecked(False)
    assert not window.a_cover.isEnabled()
    p = canvas.pages
    assert p[0].pos().y() < p[1].pos().y()


def test_a_document_asking_for_two_pages(window, tmp_path):
    path = tmp_path / "two.pdf"
    doc = pymupdf.open()
    for _ in range(5):
        doc.new_page()
    doc.xref_set_key(doc.pdf_catalog(), "PageLayout", "/TwoPageRight")
    doc.save(path)
    assert window.open_path(path)
    assert window.canvas.spread and window.canvas.cover
    assert window.settings.value("spread", "false") == "false"  # (the document's choice: not kept as the user's)


def test_more_zooms(window, tmp_path):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    canvas = window.canvas
    room = canvas.viewport().size()
    window.a_fit_height.trigger()
    page = canvas.pages[window.page]
    assert canvas.fit == "height" and abs(page.rect().height() * canvas.zoom() - (room.height() - 4) +
                                          2 * 12 * canvas.zoom()) < 3
    # (the inked area: a small block of text, far narrower than the page, fills the width)
    path = tmp_path / "ink.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((250, 400), "A short line", fontsize=12)
    doc.save(path)
    assert window.open_path(path)
    window.a_fit_width.trigger()
    width_zoom = canvas.zoom()
    window.a_fit_visible.trigger()
    ink = canvas.ink_rect(0)
    assert canvas.fit == "visible" and ink.width() < 150 and canvas.zoom() > width_zoom * 3
    window.a_actual.trigger()
    assert abs(canvas.zoom() - canvas.logicalDpiX() / 72) < 1e-6 and canvas.fit == ""
    window._choose_zoom("250 %")
    assert abs(canvas.zoom() - 2.5) < 1e-6 and window.zoom_label.currentText() == "250 %"
    window._choose_zoom(window.zoom_label.itemData(1))  # (Fit the width, chosen in the box)
    assert canvas.fit == "width"
    # (the tool Zoom to area: a frame dragged on the page fills the view)
    window.set_tool("zoomarea")
    item = canvas.pages[0]
    before = canvas.zoom()
    for kind, point in ((QEvent.Type.MouseButtonPress, QPointF(240, 380)), (QEvent.Type.MouseMove, QPointF(340, 410)),
                        (QEvent.Type.MouseButtonRelease, QPointF(340, 410))):
        pos = QPointF(canvas.mapFromScene(item.mapToScene(point)))
        buttons = Qt.MouseButton.NoButton if kind == QEvent.Type.MouseButtonRelease else Qt.MouseButton.LeftButton
        event = QMouseEvent(kind, pos, canvas.viewport().mapToGlobal(pos), Qt.MouseButton.LeftButton, buttons,
                            Qt.KeyboardModifier.NoModifier)
        {QEvent.Type.MouseButtonPress: canvas.mousePressEvent, QEvent.Type.MouseMove: canvas.mouseMoveEvent,
         QEvent.Type.MouseButtonRelease: canvas.mouseReleaseEvent}[kind](event)
    assert canvas.zoom() > before * 2
    centre = item.mapFromScene(canvas.mapToScene(canvas.viewport().rect().center()))
    assert abs(centre.x() - 290) < 10 and abs(centre.y() - 395) < 10
    window.set_mode("read")
    assert window.tool_actions["zoomarea"].isEnabled()


def test_rotating_the_view(window, book):
    canvas = window.canvas
    item = canvas.pages[0]
    w, h = item.rect().width(), item.rect().height()
    window.a_turn_right.trigger()
    item = canvas.pages[0]
    shown = item.sceneBoundingRect()
    assert canvas.turn == 90 and abs(shown.width() - h) < 1 and abs(shown.height() - w) < 1
    assert canvas.pages[1].sceneBoundingRect().top() > shown.bottom()  # (one under the other, as before)
    # (a point of the page is still found where it shows: the canvas works on the page's own coordinates)
    from PySide6.QtCore import QPointF
    corner = item.mapToScene(QPointF(10, 10))
    page, point = canvas.locate(canvas.mapFromScene(corner))
    assert page.number == 0 and abs(point.x() - 10) < 2 and abs(point.y() - 10) < 2
    assert pymupdf.open(book)[0].rotation == 0  # (the file as it was)
    window.a_turn_left.trigger()
    window.a_turn_left.trigger()
    assert canvas.turn == 270
    assert window.open_path(book)
    assert canvas.turn == 0


def test_reading_colours(window, monkeypatch):
    """The pages in view drawn in other colours (white on black...), not the file nor the thumbnails; kept
    for the next time."""
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QColorDialog

    from py_pdftools.gui import reading

    canvas = window.canvas

    def corner() -> QColor:  # (the colour of the page shown, near its corner, as drawn)
        canvas.render_page_now()
        return canvas.pages[window.page].pixmap.pixmap().toImage().pixelColor(3, 3)

    assert corner().lightness() > 240
    window.reading_actions["white"].trigger()
    assert reading.TINT == (0xFFFFFF, 0x000000) and corner().lightness() < 15
    assert window.reading_actions["white"].isChecked()
    window._thumbs.clear()
    window._draw_thumbnails()
    assert all(img.pixelColor(2, 2).lightness() > 240 for img in window._thumbs.values())  # (as they are)
    colours = iter([QColor("#ffff00"), QColor("#202060")])
    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *a, **k: next(colours)))
    window.reading_actions["custom"].trigger()
    assert reading.TINT == (0xFFFF00, 0x202060) and corner().name() == "#202060"
    other = MainWindow()  # (the next time: as they were left)
    assert reading.TINT == (0xFFFF00, 0x202060) and other.reading_actions["custom"].isChecked()
    other.close()
    window.reading_actions[""].trigger()
    assert reading.TINT is None and corner().lightness() > 240
