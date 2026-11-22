"""Navigation (gui/outline.py and the window): the bookmarks panel; and the rest of the navigation
taken from PDFCraft as it is added."""

from __future__ import annotations

import sys

import pymupdf
import pytest
from PySide6.QtWidgets import QApplication, QDockWidget, QLabel

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
    box = window.a_page_number.boxes()[0]
    box.setText("6")
    box.returnPressed.emit()
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
    # (the bookmarks it asks for stay hidden: their panel opens only when the user asks)
    assert window.page == 2 and window.canvas.fit == "width" and not window.outline_dock.isVisibleTo(window)


def test_the_bookmarks_start_hidden_and_stay_as_the_user_leaves_them(window, book):
    assert window.open_path(book)
    assert not window.outline_dock.isVisibleTo(window)
    window.a_outline.trigger()
    assert window.outline_dock.isVisibleTo(window)
    first = window.mode
    for _ in range(2):  # (the second time, each mode has an arrangement of its own to give back)
        for key in window.modes:
            window.set_mode(key)
            # (Impose shows no pages: there the panel is away, and back after it)
            assert window.outline_dock.isVisibleTo(window) == (key != "impose"), key
    window.set_mode(first)
    window.a_outline.trigger()
    assert not window.outline_dock.isVisibleTo(window)
    window.set_mode("annotate")
    assert not window.outline_dock.isVisibleTo(window)


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


def test_full_screen_presentation(window, book):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    window.show_page(1)
    show = window.present()
    assert show.isFullScreen() and show.page == 1 and show.image is not None

    def key(k):
        show.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, k, Qt.KeyboardModifier.NoModifier))

    key(Qt.Key.Key_Right)
    key(Qt.Key.Key_Space)
    assert show.page == 3
    key(Qt.Key.Key_Left)
    assert show.page == 2
    key(Qt.Key.Key_End)
    assert show.page == window.count - 1
    key(Qt.Key.Key_Home)
    key(Qt.Key.Key_Down)
    key(Qt.Key.Key_Escape)
    assert not show.isVisible() and window.page == 1  # (the window, at the page reached)


def test_a_presentation_with_timed_pages(window, tmp_path):
    path = tmp_path / "slides.pdf"
    doc = pymupdf.open()
    for _ in range(3):
        page = doc.new_page()
        doc.xref_set_key(page.xref, "Dur", "2")
        doc.xref_set_key(page.xref, "Trans", "<</S/Fade/D 0.3>>")
    doc.save(path)
    assert window.open_path(path)
    show = window.present(0)
    assert show.timed.isActive() and show.timed.interval() == 2000
    show.timed.timeout.emit()  # (the time is up: the next page, fading in)
    assert show.page == 1 and show.previous is not None and show.fader.isActive()
    show.show_page(2)
    assert not show.timed.isActive()  # (the last page stays)
    show.close()


def test_tabs_and_a_split_view(window, book, tmp_path):
    from py_pdftools.gui import open_window
    from py_pdftools.gui.tabs import open_in_tab

    other = tmp_path / "other.pdf"
    doc = pymupdf.open()
    doc.new_page()
    doc.save(other)
    window.show()
    second = open_in_tab(other, near=window)
    host = window.host
    assert host is not None and second.host is host and host.windows() == [window, second]
    assert window.is_open() and second.is_open()  # (open, though one tab is behind the other)
    assert host.sides[0].tabText(1) == "other.pdf" and host.windowTitle() == second.windowTitle()
    # The split view: the second document beside the first; again, back.
    second.a_split.trigger()
    assert host.sides[1].isVisibleTo(host) and host.side_of(second) is host.sides[1]
    assert not any(t.tabBarAutoHide() for t in host.sides)  # (split: each side's bar shown, with its menu)
    assert window.isVisible() and second.isVisible()  # (both in view)
    # Each window's shortcuts act only in it (no two actions take the same keys).
    from PySide6.QtCore import Qt
    assert second.a_next.shortcutContext() == Qt.ShortcutContext.WidgetWithChildrenShortcut
    second.a_split.trigger()
    assert not host.sides[1].isVisibleTo(host)
    # With the setting, documents opened go into tabs.
    from py_pdftools.core import config

    config.set("tabs", True)
    try:
        third = open_window(book)
    finally:
        config.set("tabs", False)
    assert third.host is host and len(host.windows()) == 3
    # A tab to a window of its own; one closed takes its tab with it.
    third.a_detach.trigger()
    assert third.host is None and third.isWindow() and third.isVisible() and len(host.windows()) == 2
    assert third.a_next.shortcutContext() == Qt.ShortcutContext.WindowShortcut
    third.close()
    second.close()
    assert host.windows() == [window] and host.isVisible()
    # One tab left: its bar hidden, unless Settings > General > Show the bar of the tabs says otherwise
    from py_pdftools.gui.tabs import apply_tab_bars

    assert host.sides[0].tabBarAutoHide() and not host.sides[0].tabBar().isVisible()
    config.set("lone_tab", True)
    apply_tab_bars()
    assert not host.sides[0].tabBarAutoHide() and host.sides[0].tabBar().isVisible()
    config.set("lone_tab", False)
    window.annotations = window.saved = []
    window.close()
    assert not host.isVisible()  # (the last tab closed: its window too)


@pytest.mark.skipif(sys.platform == "win32",
                    reason="Windows doesn't let another program replace a file open in the window")
def test_reloading_a_file_changed_on_disk(window, book, monkeypatch):
    import time

    from pathlib import Path

    from py_pdftools.annotate.annots import Annotation

    def change(pages: int):
        doc = pymupdf.open(book)
        for _ in range(pages):
            doc.new_page()
        doc.save(str(book) + ".new")
        doc.close()
        time.sleep(0.01)
        Path(str(book) + ".new").replace(book)  # (as many programs save: a new file in its place)

    window.show_page(3)
    change(1)
    # (the watcher tells the window; then, once the file has settled, it is read again)
    end = time.time() + 5
    while window.count != 7 and time.time() < end:
        QApplication.processEvents()
        time.sleep(0.02)
    assert window.count == 7 and window.page == 3  # (at the same place)
    # Its own saving is no change.
    window.annotations = [*window.annotations, Annotation("rect", 0, (50, 50, 100, 100))]
    assert window.save()
    assert not window.file_changed()
    # With something unsaved, it asks; said no, the change is not asked about again.
    window.annotations = [*window.annotations, Annotation("rect", 0, (150, 50, 200, 100))]
    asked = []
    monkeypatch.setattr(window, "ask_reload", lambda: asked.append(1) or False)
    change(1)
    assert not window.file_changed() and asked == [1] and window.count == 7
    assert not window.file_changed() and asked == [1]
    monkeypatch.setattr(window, "ask_reload", lambda: True)
    change(1)
    assert window.file_changed() and window.count == 9 and not window.is_modified()


def test_the_details_of_a_page_on_hover(window, tmp_path, monkeypatch):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QHelpEvent
    from PySide6.QtWidgets import QToolTip

    path = tmp_path / "sizes.pdf"
    doc = pymupdf.open()
    doc.new_page(width=595, height=842)  # (A4)
    doc.new_page(width=792, height=612).set_rotation(90)  # (Letter, lying, turned in the file)
    doc.save(path)
    assert window.open_path(path)
    text = window.page_details(0)
    assert "Page 1 of 2" in text and "210 × 297 mm" in text and "A4" in text and "portrait" in text
    text = window.page_details(1)
    assert "Letter" in text and "portrait" in text and "Turned 90°" in text  # (as it shows: upright)
    window.show_page(0)
    count = window.a_page_number.createdWidgets()[0].findChild(QLabel, "count")
    assert "A4" in count.toolTip()
    shown = []
    monkeypatch.setattr(QToolTip, "showText", staticmethod(lambda pos, text, *a: shown.append(text)))
    rect = window.pages.visualItemRect(window.pages.item(1))
    event = QHelpEvent(QEvent.Type.ToolTip, rect.center(), window.pages.viewport().mapToGlobal(rect.center()))
    QApplication.sendEvent(window.pages.viewport(), event)
    assert shown and "Page 2 of 2" in shown[0]


def test_scrolling_with_space_the_middle_button_and_the_wheel(window):
    from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
    from PySide6.QtGui import QKeyEvent, QMouseEvent, QWheelEvent
    from PySide6.QtWidgets import QGraphicsView

    canvas = window.canvas
    window.set_tool("select")
    # Space held: Hand for a moment.
    canvas.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier))
    assert canvas.mode == "hand" and canvas.dragMode() == QGraphicsView.DragMode.ScrollHandDrag
    canvas.keyReleaseEvent(QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier))
    assert canvas.mode == "select" and canvas.dragMode() == QGraphicsView.DragMode.NoDrag
    # The middle button: the pages run towards the pointer until the next click.
    window._fit("width")
    bar = canvas.verticalScrollBar()
    bar.setValue(0)

    def mouse(kind, x, y, button, buttons):
        pos = QPointF(x, y)
        return QMouseEvent(kind, pos, canvas.viewport().mapToGlobal(pos), button, buttons,
                           Qt.KeyboardModifier.NoModifier)

    canvas.mousePressEvent(mouse(QEvent.Type.MouseButtonPress, 300, 200, Qt.MouseButton.MiddleButton,
                                 Qt.MouseButton.MiddleButton))
    canvas.mouseReleaseEvent(mouse(QEvent.Type.MouseButtonRelease, 300, 200, Qt.MouseButton.MiddleButton,
                                   Qt.MouseButton.NoButton))
    canvas.mouseMoveEvent(mouse(QEvent.Type.MouseMove, 300, 320, Qt.MouseButton.NoButton, Qt.MouseButton.NoButton))
    for _ in range(5):
        canvas._auto_step()
    assert bar.value() > 50
    canvas.mousePressEvent(mouse(QEvent.Type.MouseButtonPress, 300, 320, Qt.MouseButton.LeftButton,
                                 Qt.MouseButton.LeftButton))
    assert canvas._auto_origin is None and not canvas._auto_timer.isActive()
    # One page at a time, two side by side: the wheel past the end goes on a pair.
    window.a_spread.setChecked(True)
    window.a_continuous.setChecked(False)
    window.show_page(0)
    bar.setValue(bar.maximum())
    wheel = QWheelEvent(QPointF(300, 300), QPointF(300, 300), QPoint(), QPoint(0, -120), Qt.MouseButton.NoButton,
                        Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    canvas.wheelEvent(wheel)
    assert window.page == 2
    window.a_continuous.setChecked(True)
    window.a_spread.setChecked(False)


def test_hiding_the_gaps_between_pages(window):
    canvas = window.canvas
    p = canvas.pages
    assert p[1].sceneBoundingRect().top() - p[0].sceneBoundingRect().bottom() == 12
    window.a_gaps.setChecked(False)
    p = canvas.pages
    assert p[1].sceneBoundingRect().top() == p[0].sceneBoundingRect().bottom()
    assert window.settings.value("gaps") == "false"
    other = MainWindow()  # (the next time, as it was left)
    assert other.canvas.gap == 0 and not other.a_gaps.isChecked()
    other.close()
    window.a_gaps.setChecked(True)
    assert canvas.pages[1].sceneBoundingRect().top() - canvas.pages[0].sceneBoundingRect().bottom() == 12


def test_the_page_navigation_bar(window):
    """The toolbar Page navigation (gui/pagebar.py): First, Previous, the box of the page, Next, Last, at the
    top of the window, after Navigation; the box takes a number, shows the page in view and how many there are; the bar can
    be customized as the others; Impose, which has no pages to move through, hides it."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel, QLineEdit, QToolBar

    bar = window.findChild(QToolBar, "pagenav")
    assert bar is not None and bar.isVisible()
    # (in the row of the toolbars of every mode, between Navigation and Zoom)
    assert window.toolBarArea(bar) == Qt.ToolBarArea.TopToolBarArea
    row = [b.objectName() for b in window.common_bars]
    assert row.index("navigation") + 1 == row.index("pagenav") == row.index("zoom") - 1
    assert window.bar_ids(bar) == ["a_first", "a_prev", "a_page_number", "a_next", "a_last"]
    # (and they are not also on the toolbar Navigation, which keeps the history and the tools)
    navigation = window.findChild(QToolBar, "navigation")
    assert window.bar_ids(navigation) == ["a_back", "a_forward", "tool:selecttext", "tool:hand", "tool:zoomarea"]
    box, count = bar.findChild(QLineEdit, "page"), bar.findChild(QLabel, "count")
    assert box.text() == "1" and count.text() == "of 6"
    window.a_last.trigger()
    QApplication.processEvents()
    assert window.page == 5 and box.text() == "6"
    box.setText("3")
    box.returnPressed.emit()
    QApplication.processEvents()
    assert window.page == 2 and box.text() == "3"
    window.a_first.trigger()
    QApplication.processEvents()
    assert window.page == 0 and box.text() == "1"
    # Editable: the box can go on another toolbar too, with a box of its own that follows the page
    window.apply_toolbar_layout({"bars": {"zoom": ["a_fit", "a_page_number"]}, "custom": []}, keep=False)
    other = window.findChild(QToolBar, "zoom").findChild(QLineEdit, "page")
    assert other is not None and other is not box and other.text() == "1"
    window.a_next.trigger()
    QApplication.processEvents()
    assert other.text() == box.text() == "2"
    window.apply_toolbar_layout({"bars": {}, "custom": []}, keep=False)
    window.set_mode("impose")
    assert not bar.isVisible()
    window.set_mode("read")
    assert bar.isVisible()


def test_ocr_from_the_thumbnails_in_every_mode(window, monkeypatch):
    """The right click on the thumbnails offers to read the pages chosen (OCR) in every mode, not only in OCR,
    whose own action is turned off while another mode is on."""
    from py_pdftools.annotate import ocr

    monkeypatch.setattr(ocr, "available", lambda: True)
    shown = []
    monkeypatch.setattr(window, "show_menu", lambda menu, pos: shown.append(menu))
    for mode in ("read", "annotate", "ocr"):
        window.set_mode(mode)
        rect = window.pages.visualItemRect(window.pages.item(0))
        window.thumbs_menu(rect.center())
        item = next(a for a in shown[-1].actions() if "(OCR)" in a.text())
        assert item.isEnabled(), mode
    monkeypatch.setattr(ocr, "available", lambda: False)
    window.thumbs_menu(window.pages.visualItemRect(window.pages.item(0)).center())
    assert not next(a for a in shown[-1].actions() if "(OCR)" in a.text()).isEnabled()


def test_extracted_pages_open_in_a_new_tab(window, tmp_path, monkeypatch):
    """Extract to a new PDF writes the pages chosen as a new file, and opens it in a tab beside the document."""
    from PySide6.QtWidgets import QFileDialog

    from py_pdftools.gui import paging

    target = tmp_path / "part.pdf"
    monkeypatch.setattr(paging, "ask_arrange", lambda *a, **k: [2, 3])
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), "")))
    window.show()
    assert window.arrange_dialog("extract", [2, 3])
    assert pymupdf.open(target).page_count == 2
    host = window.host
    assert host is not None and len(host.windows()) == 2
    new = host.windows()[1]
    assert new.path == target and host.current() is new
    new.close()


def test_the_thumbnails_are_in_the_middle_of_their_panel(window):
    window.show_thumbnails(True)
    window.splitter.setSizes([400, 700]) if hasattr(window, "splitter") else None
    window.thumbs_box.grab()  # (shown: the list gets its width, and lays its cells out again)
    QApplication.processEvents()
    view = window.pages.viewport().width()
    cell = window.pages.visualItemRect(window.pages.item(1))
    assert view > window.thumb.width() + 28  # (wider than a thumbnail: there is something to center)
    assert cell.width() == view and abs(cell.center().x() - view / 2) <= 1


def test_f5_is_preview_in_impose_and_the_bookmarks_elsewhere(window):
    window.a_outline.trigger()
    assert window.outline_dock.isVisibleTo(window)
    window.set_mode("impose")
    assert not window.a_outline.isEnabled() and not window.outline_dock.isVisibleTo(window)
    window.set_mode("read")
    assert window.a_outline.isEnabled() and window.outline_dock.isVisibleTo(window)


def test_left_and_right_turn_the_pages(window):
    """In the view of the pages, Left goes to the previous page and Right to the next (a pair, with two side
    by side); zoomed in wider than the view, they scroll sideways; with annotations chosen, they move them."""
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    canvas = window.canvas

    def press(key, modifiers=Qt.KeyboardModifier.NoModifier):
        canvas.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, modifiers))

    window.show()
    window._fit("page")
    window.show_page(1)
    press(Qt.Key.Key_Right)
    assert window.page == 2
    press(Qt.Key.Key_Left)
    press(Qt.Key.Key_Left)
    assert window.page == 0
    press(Qt.Key.Key_Left)  # (the first page: it stays)
    assert window.page == 0
    press(Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)  # (with a modifier: not a page)
    assert window.page == 0
    window.a_spread.setChecked(True)
    window._fit("page")
    window.show_page(0)
    press(Qt.Key.Key_Right)
    assert window.page == 2  # (a pair at a time)
    window.a_spread.setChecked(False)
    canvas.set_zoom(4.0)
    bar = canvas.horizontalScrollBar()
    assert bar.maximum() > 0
    bar.setValue(0)
    page = window.page
    press(Qt.Key.Key_Right)
    assert window.page == page and bar.value() > 0  # (scrolled sideways)


def test_floating_parts_go_with_their_tab(window, tmp_path):
    """A panel (or a toolbar) dragged out of a window that is a tab is hidden with it: when another tab comes
    to the front, and when the window of tabs is closed (they stayed on the screen, each with its icon in
    the taskbar); it comes back with its tab."""
    from py_pdftools.gui.tabs import open_in_tab

    other = tmp_path / "other.pdf"
    doc = pymupdf.open()
    doc.new_page()
    doc.save(other)
    window.set_mode("ocr")
    second = open_in_tab(other, near=window)
    host = window.host
    host.show_window(window)
    QApplication.processEvents()
    dock = next(d for d in window.findChildren(QDockWidget) if d.objectName() == "ocr")
    dock.setFloating(True)
    dock.show()
    QApplication.processEvents()
    assert dock.isVisible() and dock in window.floating_parts()
    host.show_window(second)  # (the other tab in front)
    QApplication.processEvents()
    assert not dock.isVisible()
    host.show_window(window)
    QApplication.processEvents()
    assert dock.isVisible() and dock.isFloating()
    window.annotations = window.saved = []
    second.annotations = second.saved = []
    host.close()
    QApplication.processEvents()
    assert not dock.isVisible()
    assert not [w for w in QApplication.topLevelWidgets() if w.isVisible() and w.parent() is window]
    # Back in its window: a panel left floating is a window of its own, which PySide destroys when Python
    # ends, and the offscreen display of the tests (Linux, macOS, Windows) then crashes.
    dock.setFloating(False)
    QApplication.processEvents()
