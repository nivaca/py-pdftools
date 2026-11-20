"""The tool Select text (gui/textselect.py): words, lines, drags across pages, columns, Shift+click; and
what the window does with the text selected (copy, mark, redact)."""

from __future__ import annotations

import pymupdf
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from py_pdftools.gui.window import MainWindow

LINES = [["alpha beta gamma", "delta epsilon zeta", "eta theta iota"],
         ["kappa lambda mu", "nu xi omicron", "pi rho sigma"]]


@pytest.fixture
def window(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    path = tmp_path / "text.pdf"
    doc = pymupdf.open()
    for lines in LINES:
        page = doc.new_page(width=400, height=300)
        for i, line in enumerate(lines):
            page.insert_text((40, 60 + i * 40), line, fontsize=16)
    doc.save(path)
    w = MainWindow()
    w.ask_recover = lambda when: False
    w.resize(1100, 900)
    w.show()
    assert w.open_path(path)
    w.set_mode("annotate")
    w.canvas.set_zoom(0.9)  # (both pages in view)
    QApplication.processEvents()
    w.set_tool("selecttext")
    yield w
    w.annotations = w.saved = []
    w.drop_work()
    w.close()


def at(w, page: int, word: str) -> QPointF:
    """Where WORD is on PAGE, in the coordinates of the page."""
    # (the whole word: search_for would find 'eta' in 'beta')
    x0, y0, x1, y1, *_ = next(w_ for w_ in w.doc[page].get_text("words") if w_[4] == word)
    return QPointF((x0 + x1) / 2, (y0 + y1) / 2)


def mouse(w, kind, page: int, point: QPointF, modifiers=Qt.KeyboardModifier.NoModifier):
    """A mouse event of KIND on POINT of PAGE, sent to the canvas."""
    canvas = w.canvas
    pos = QPointF(canvas.mapFromScene(canvas.pages[page].mapToScene(point)))
    buttons = Qt.MouseButton.NoButton if kind == QEvent.Type.MouseButtonRelease else Qt.MouseButton.LeftButton
    event = QMouseEvent(kind, pos, canvas.viewport().mapToGlobal(pos), Qt.MouseButton.LeftButton, buttons, modifiers)
    {QEvent.Type.MouseButtonPress: canvas.mousePressEvent, QEvent.Type.MouseMove: canvas.mouseMoveEvent,
     QEvent.Type.MouseButtonRelease: canvas.mouseReleaseEvent,
     QEvent.Type.MouseButtonDblClick: canvas.mouseDoubleClickEvent}[kind](event)


def drag(w, page0, point0, page1, point1, modifiers=Qt.KeyboardModifier.NoModifier):
    mouse(w, QEvent.Type.MouseButtonPress, page0, point0, modifiers)
    mouse(w, QEvent.Type.MouseMove, page1, point1, modifiers)
    mouse(w, QEvent.Type.MouseButtonRelease, page1, point1, modifiers)


def test_a_word_and_a_line(window):
    canvas = window.canvas
    mouse(window, QEvent.Type.MouseButtonDblClick, 0, at(window, 0, "epsilon"))
    assert canvas.selected_text() == "epsilon"
    mouse(window, QEvent.Type.MouseButtonPress, 0, at(window, 0, "epsilon"))  # (the third click)
    assert canvas.selected_text() == "delta epsilon zeta" and canvas._sel_marks


def test_a_drag_across_pages_copied_and_marked(window):
    canvas = window.canvas
    drag(window, 0, at(window, 0, "theta"), 1, at(window, 1, "lambda"))
    assert canvas.selected_text() == "theta iota\n\nkappa lambda"
    window.copy_selected()
    assert QApplication.clipboard().text() == "theta iota\n\nkappa lambda"
    assert window.mark_selected_text("highlight")
    marks = [(a.kind, a.page) for a in window.annotations]
    assert marks == [("highlight", 0), ("highlight", 1)] and canvas.text_sel is None


def test_column_shift_click_escape_and_redaction(window):
    canvas = window.canvas
    # (Alt+drag: the words inside the rectangle, from the first word of the page down the first column)
    start, end = at(window, 0, "alpha"), at(window, 0, "eta")
    drag(window, 0, QPointF(start.x() - 5, start.y() - 5), 0, QPointF(end.x() + 5, end.y() + 5),
         Qt.KeyboardModifier.AltModifier)
    assert canvas.selected_text() == "alpha\ndelta\neta"
    mouse(window, QEvent.Type.MouseButtonDblClick, 0, at(window, 0, "beta"))
    mouse(window, QEvent.Type.MouseButtonRelease, 0, at(window, 0, "beta"))
    canvas._last_double = (0.0, None)  # (not a triple click)
    mouse(window, QEvent.Type.MouseButtonPress, 0, at(window, 0, "zeta"), Qt.KeyboardModifier.ShiftModifier)
    assert canvas.selected_text() == "beta gamma\ndelta epsilon zeta"
    canvas.keyPressEvent(__import__("PySide6.QtGui", fromlist=["QKeyEvent"]).QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    assert canvas.text_sel is None and not canvas._sel_marks
    window.select_page()  # (Ctrl+A with the tool: the text of the page)
    assert canvas.selected_text() == "\n".join(LINES[0][0:1] + LINES[0][1:])
    assert window.redact_selected_text()
    assert [a.kind for a in window.annotations] == ["redact"] * 3


def test_in_every_mode(window):
    window.set_mode("read")
    act = window.tool_actions["selecttext"]
    assert act.isEnabled()
    assert any(act in bar.actions() for bar in window.common_bars if not bar.isHidden())
