"""Page labels where they can be seen: under each thumbnail ('5  i' when the label isn't the number), changed
at once by Labels > Number this page (in any mode, from the thumbnails' menu), and back with Undo; the status
bar says what changed, or that nothing did."""

from __future__ import annotations

import pymupdf
import pytest
from PySide6.QtWidgets import QApplication, QDialog

from py_pdftools.gui import paging
from py_pdftools.gui.window import MainWindow


@pytest.fixture
def window(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    d = pymupdf.open()
    for i in range(6):
        d.new_page().insert_text((72, 72), f"p{i + 1}")
    d.save(tmp_path / "num.pdf")
    w = MainWindow()
    w.ask_recover = lambda when: False
    w.show()
    assert w.open_path(tmp_path / "num.pdf")
    yield w
    w.drop_work()
    w.close()


def captions(w):
    return [w.pages.item(i).text() for i in range(w.pages.count())]


def number(w, monkeypatch, row: int, style: str, start: int = 1):
    """Labels > Number this page, from the menu of the thumbnail ROW, with STYLE from START."""
    shown = {}
    monkeypatch.setattr(w, "show_menu", lambda menu, where: shown.setdefault("menu", menu))

    def chosen(dialog):
        dialog.style.setCurrentIndex(dialog.style.findData(style))
        dialog.start.setValue(start)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(paging.NumberDialog, "exec", chosen)
    w.thumbs_menu(w.pages.visualItemRect(w.pages.item(row)).center())
    names = next(a.menu() for a in shown["menu"].actions() if a.menu() and a.text() == "Labels")
    next(a for a in names.actions() if a.text().startswith("Number")).trigger()
    QApplication.processEvents()


def test_number_this_page_in_read_mode(window, monkeypatch):
    window.set_mode("read")
    assert captions(window) == ["1", "2", "3", "4", "5", "6"]
    number(window, monkeypatch, 4, "r")
    assert window.page_labels()[4] == "i"
    assert captions(window) == ["1", "2", "3", "4", "5  i", "6"]
    assert "page 5 is now i" in window.statusBar().currentMessage()
    window.undo()
    assert captions(window)[4] == "5"
    window.redo()
    assert captions(window)[4] == "5  i"


def test_nothing_to_change_is_said(window, monkeypatch):
    number(window, monkeypatch, 0, "D", 1)  # (page 1 is 1 already)
    assert "already" in window.statusBar().currentMessage()
    assert captions(window)[0] == "1"

