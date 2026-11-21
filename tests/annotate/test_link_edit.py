"""Making and changing links (gui/linking.py): the tool Link draws a link to a page, an address or another
PDF; a click on a link with it changes or removes it; the addresses written in the text become links; all
the links are removed; each change is undone; and on a turned page the link is where it was drawn."""

from __future__ import annotations

import pymupdf
import pytest
from gui_helpers import drag, mouse
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication

from py_pdftools.gui.linking import LinkDialog, address_uri
from py_pdftools.gui.window import MainWindow


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def make(path, turn=0):
    doc = pymupdf.open()
    for i in range(3):
        page = doc.new_page()
        page.insert_text((72, 100), f"Page {i + 1}, see www.example.org or me@example.org.", fontsize=12)
        page.set_rotation(turn)
    doc.save(path)
    return path


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    w = MainWindow()
    w.ask_recover = lambda when: False
    w.resize(1100, 800)
    w.show()
    yield w
    w.annotations = w.saved = []
    w.drop_work()  # (los cambios del documento sin guardar: cerrar no pregunta)
    w.close()


def links(w, page=0):
    return w.doc[page].get_links()


def look(w):
    """The first page whole in view (the points clicked are on the screen)."""
    w.show_page(0)
    w._fit("page")
    QApplication.processEvents()


def open_in(w, path):
    assert w.open_path(path)
    w.set_mode("annotate")
    w.set_tool("link")
    QApplication.processEvents()
    assert w.canvas.mode == "link"
    look(w)


def test_draw_change_remove_undo(window, tmp_path):
    open_in(window, make(tmp_path / "a.pdf"))
    window.ask_link = lambda target=None, can_remove=False: {"kind": "page", "page": 2}
    drag(window, (300, 300), (400, 330), page=0)
    [lk] = links(window)
    assert lk["kind"] == pymupdf.LINK_GOTO and lk["page"] == 2
    assert pymupdf.Rect(lk["from"]).contains(pymupdf.Point(350, 315))
    # a click on it, with the tool: changed to an address
    look(window)
    asked = []
    window.ask_link = lambda target=None, can_remove=False: (
        asked.append(target), {"kind": "uri", "uri": "https://example.org"})[1]
    mouse(window, QEvent.Type.MouseButtonPress, (350, 315), page=0)
    mouse(window, QEvent.Type.MouseButtonRelease, (350, 315), page=0)
    assert asked == [{"kind": "page", "page": 2}], asked
    [lk] = links(window)
    assert lk["kind"] == pymupdf.LINK_URI and lk["uri"] == "https://example.org"
    look(window)
    window.ask_link = lambda target=None, can_remove=False: None  # (Remove the link)
    mouse(window, QEvent.Type.MouseButtonPress, (350, 315), page=0)
    mouse(window, QEvent.Type.MouseButtonRelease, (350, 315), page=0)
    assert links(window) == []
    window.undo()
    assert len(links(window)) == 1
    assert window.save()
    assert len(pymupdf.open(tmp_path / "a.pdf")[0].get_links()) == 1


def test_on_a_turned_page(window, tmp_path):
    open_in(window, make(tmp_path / "t.pdf", turn=90))
    window.ask_link = lambda target=None, can_remove=False: {"kind": "page", "page": 1}
    drag(window, (300, 300), (400, 330), page=0)
    look(window)
    [lk] = links(window)
    # (where it was drawn, as the page is shown, and found there by the pointer)
    assert pymupdf.Rect(lk["from"]).contains(pymupdf.Point(350, 315))
    assert window.canvas.link_at(0, __import__("PySide6.QtCore").QtCore.QPointF(350, 315))["page"] == 1


def test_addresses_of_the_text_and_remove_all(window, tmp_path):
    open_in(window, make(tmp_path / "a.pdf"))
    assert window.links_from_text() == 6  # (two on each page)
    assert {lk["uri"] for lk in links(window)} == {"https://www.example.org", "mailto:me@example.org"}
    assert window.links_from_text() == 0  # (not twice)
    window.confirm_remove_links = lambda total: total == 6
    assert window.remove_all_links() == 6
    assert all(not links(window, n) for n in range(3))


def test_the_dialog(app):
    d = LinkDialog(3, ["i", "ii", "1"], {"kind": "page", "page": 1}, can_remove=True)
    assert d.page.currentData() == 1 and d.page.itemText(2) == "3  (1)"
    d.to_uri.setChecked(True)
    assert not d.b_ok.isEnabled()
    d.uri.setText("me@example.org")
    assert d.b_ok.isEnabled() and d.target() == {"kind": "uri", "uri": "mailto:me@example.org"}
    d.file.setText("/x/other.pdf")
    d.file_page.setValue(4)
    assert d.to_file.isChecked() is False  # (typed by the program, not by the user)
    d.to_file.setChecked(True)
    assert d.target() == {"kind": "file", "file": "/x/other.pdf", "page": 3}
    assert address_uri("www.a.org,") == "https://www.a.org"
