"""The modes of the window: Read, Redact, Annotate, Foliate and Impose, in that order, each with its own
arrangement of the window, given back when the mode is chosen again (in the same session or another)."""

from __future__ import annotations

import pymupdf
import pytest
from PySide6.QtWidgets import QApplication

from py_pdftools.annotate.annots import Annotation
from py_pdftools.gui import window as window_module
from py_pdftools.gui.window import MainWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def sample(tmp_path):
    path = tmp_path / "sample.pdf"
    doc = pymupdf.open()
    for i in range(3):
        doc.new_page().insert_text((72, 100), f"Page {i + 1}", fontsize=14)
    doc.save(path)
    return path


def make(app, sample):
    w = MainWindow()
    w.ask_recover = lambda when: False
    w.resize(1200, 800)
    w.show()
    assert w.open_path(sample)
    app.processEvents()
    return w


def close(w):
    w.annotations = w.saved = []
    w.drop_work()
    w.close()


def shown(item) -> bool:
    return not item.isHidden()


def test_the_modes_in_order(app, sample, monkeypatch):
    monkeypatch.setattr(window_module, "DEFAULT_MODE", "read")
    w = make(app, sample)
    assert list(w.modes) == ["read", "ocr", "redact", "annotate", "pages", "impose"]
    assert [a.text() for a in w.mode_actions.values()] == ["Read", "OCR", "Redact", "Annotate", "Foliate", "Impose"]
    assert [a.shortcut().toString() for a in w.mode_actions.values()] == [f"Ctrl+{n}" for n in range(1, 7)]
    # (the first time, Read: only the pages, the hand, and the toolbars of every mode but Edit)
    assert w.mode == "read" and w.canvas.mode == "hand"
    assert not any(shown(b) for m in w.modes.values() for b in m.bars + m.docks)
    assert [b.objectName() for b in w.common_bars if shown(b)] == ["file", "find", "navigation", "zoom", "pagenav"]
    close(w)


def test_read_touches_nothing(app, sample, monkeypatch):
    w = make(app, sample)
    w.set_mode("annotate")  # (the tests of a module share the settings: the window may start in another mode)
    w.add(Annotation("rect", 0, (100, 100, 200, 200), "#ff0000"))
    w.set_mode("read")
    assert not w.canvas.touchable(w.annotations[0]) and w.selected == []
    w.select_page()
    assert w.selected == []
    close(w)


def test_each_mode_keeps_its_arrangement(app, sample):
    """What is hidden in a mode stays so when it comes back, and in the next session; the panels of a mode
    are never shown in another."""
    w = make(app, sample)
    w.set_mode("annotate")
    w.panel.hide()
    w.tool_bars[2].hide()  # (Notes and text)
    w.a_thumbs.setChecked(False)
    w.set_mode("pages")
    assert shown(w.modes["pages"].docks[0]) and not shown(w.panel)
    assert all(shown(b) for b in w.modes["pages"].bars)
    w.set_mode("annotate")
    assert not shown(w.panel) and not shown(w.tool_bars[2]) and shown(w.tool_bars[0])
    assert not w.a_thumbs.isChecked()
    assert not any(shown(b) for b in w.modes["pages"].bars + w.modes["pages"].docks)
    close(w)
    again = make(app, sample)  # (another session: the mode it was left in, as it was arranged)
    assert again.mode == "annotate"
    assert not shown(again.panel) and not shown(again.tool_bars[2]) and shown(again.tool_bars[1])
    again.set_mode("read")
    assert not any(shown(b) for b in again.tool_bars) and not shown(again.panel)
    close(again)


def test_the_hint_of_a_mode_over_the_pages(app, sample):
    """A mode's hint shows over the bottom of the pages when the mode is chosen, a click on the pages takes
    it away, F1 shows it again, and it fades by itself; nothing is kept below the pages for it."""
    import time

    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    from py_pdftools.core import config

    config.set_many({"hints": True})  # (off at first: Settings > Appearance)
    w = make(app, sample)
    w.set_mode("read")
    hint = w.hint
    assert shown(hint) and hint.text() == w.hints["read"] and hint.parent() is w.canvas
    assert hint.geometry().bottom() <= w.canvas.height() and hint.geometry().top() > w.canvas.height() // 2
    assert w.canvas.parentWidget().layout().count() == 2  # (only the page bar and the pages)
    press = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(20, 20), QPointF(20, 20), Qt.MouseButton.LeftButton,
                        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(w.canvas.viewport(), press)
    assert not shown(hint)
    w.a_tips.trigger()
    assert shown(hint) and hint.text() == w.hints["read"]
    hint.timer.setInterval(10)
    hint.fade.setDuration(10)
    hint.timer.start()
    deadline = time.time() + 5
    while shown(hint) and time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert not shown(hint)
    w.set_mode("impose")  # (a mode without a hint: none shown)
    assert not shown(hint)
    close(w)
