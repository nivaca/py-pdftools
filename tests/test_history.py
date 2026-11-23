"""El panel Historial (Ver > Paneles, F10): cada paso descrito, los que se pueden rehacer después, y un clic
que deshace o rehace hasta un paso de una vez."""

from __future__ import annotations

import dataclasses

import pymupdf
import pytest
from PySide6.QtWidgets import QApplication

from py_pdftools.annotate.annots import Annotation
from py_pdftools.gui.history import describe
from py_pdftools.pages import arrange


def note(page=0, created="D:1"):
    return Annotation("note", page, (10, 10, 26, 26), "#ffd54f", contents="?", created=created)


def test_describe():
    a, b, c = note(0, "D:1"), note(1, "D:2"), Annotation("rect", 2, (0, 0, 50, 50), "#e53935", created="D:3")
    assert describe([], [a]) == "Note added, page 1"
    assert describe([a], [a, b, c]) == "2 annotations added"
    assert describe([a, b], [b]) == "Note deleted, page 1"
    assert describe([a, b, c], []) == "3 annotations deleted"
    moved = dataclasses.replace(c, rect=(5, 5, 55, 55))
    assert describe([a, c], [a, moved]) == "Rectangle changed, page 3"
    assert describe([a, b], [dataclasses.replace(a, color="#000000"), dataclasses.replace(b, color="#000000")]) \
        == "2 annotations changed"
    assert describe([a, b], [b, a]) == "Annotations reordered"
    assert describe([a], [b]) == "Annotations changed"  # (one deleted, another added)


@pytest.fixture
def window(tmp_path, monkeypatch):
    from py_pdftools.gui.window import MainWindow

    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    doc = pymupdf.open()
    for n in range(3):
        doc.new_page().insert_text((72, 72), f"P{n + 1}")
    doc.save(tmp_path / "d.pdf")
    w = MainWindow()
    w.ask_recover = lambda when: False
    w.resize(1200, 800)
    w.show()
    assert w.open_path(tmp_path / "d.pdf")
    w.labels_choice = lambda: arrange.FOLLOW
    yield w
    w.annotations = w.saved = []
    w.drop_work()
    w.close()


def rows(w):
    return [w.history_list.item(r).text() for r in range(w.history_list.count())]


def test_the_panel(window):
    w = window
    w.a_history.trigger()
    QApplication.processEvents()
    assert w.history_dock.isVisible() and rows(w) == ["The document as it was opened"]
    w.add(note(1, "D:1"))
    w.add(note(2, "D:2"))
    w.arrange_pages(arrange.Rotate((1,), 90))  # (a change of the document itself: its own message)
    w.change([w.annotations[0]])
    assert rows(w) == ["The document as it was opened", "Note added, page 2", "Note added, page 3",
                       "Pages rotated", "Note deleted, page 3"]
    assert w.history_list.currentRow() == 4 and w.history_list.item(4).font().bold()
    # Undone, the steps stay below, to be redone; the document's change keeps its name both ways
    w.undo()
    w.undo()
    assert rows(w)[3:] == ["Pages rotated", "Note deleted, page 3"] and w.history_list.currentRow() == 2
    assert not w.history_list.item(3).font().bold()
    w.redo()
    assert rows(w)[3] == "Pages rotated" and w.doc[0].rotation == 90
    # A click goes to a step, undoing or redoing what is between
    w.history_jump(0)
    assert w.annotations == [] and not w.undo_stack and w.doc[0].rotation == 0
    w.history_jump(4)
    assert len(w.annotations) == 1 and not w.redo_stack and w.doc[0].rotation == 90
    w.history_jump(1)
    assert len(w.annotations) == 1 and len(w.redo_stack) == 3
    # A new change drops what could be redone, as Undo does
    w.add(note(0, "D:9"))
    assert rows(w)[-1] == "Note added, page 1" and len(rows(w)) == 3
