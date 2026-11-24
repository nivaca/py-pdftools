"""El panel Buscar mientras se escribe (gui/findbar.py): baja deslizándose sobre la esquina de arriba de las
páginas y sube al cerrarse; muestra el primer lugar en cuanto lo encuentra, sin leer el resto del documento; cuenta los demás después, por tramos;
resalta los lugares, va de uno a otro, guarda los textos buscados, se vuelve rojiza si no encuentra nada, y no
cambia las otras búsquedas."""

from __future__ import annotations

import pymupdf
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from py_pdftools.gui.findbar import NAME
from py_pdftools.pages import arrange


@pytest.fixture
def window(tmp_path, monkeypatch):
    from py_pdftools.gui.window import MainWindow

    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    doc = pymupdf.open()
    for n in range(5):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {n + 1}: the scribe copies the text.")
        if n in (1, 3):
            page.insert_text((72, 120), "The Scribe again, and a scribe more.")
        if n == 2:
            page.insert_text((72, 160), "una canción y otra cancion", fontname="helv")
    doc.save(tmp_path / "d.pdf")
    w = MainWindow()
    w.ask_recover = lambda when: False
    w.resize(1200, 800)
    w.show()
    assert w.open_path(tmp_path / "d.pdf")
    yield w
    w.drop_work()
    w.close()


def count(bar):
    """What the idle slices do after a search: every page counted."""
    while bar.order:
        bar._work()
    if bar.q is not None and not bar.complete:
        bar._counted()


def type_in(bar, text):
    bar.box.clear()
    if text.isascii():
        QTest.keyClicks(bar.box, text)
    else:  # (QTest aborta con un carácter que no es ASCII: el texto se pone sin teclearlo)
        bar.box.setText(text)
    bar.timer.stop()
    bar.run()  # (lo que el reloj haría tras la pausa)
    count(bar)


def finish_slide(bar):
    """The slide of the panel, at its end (as the animation would leave it)."""
    bar.slide.setCurrentTime(bar.slide.duration())
    QApplication.processEvents()


def test_comes_down_from_the_top(window):
    w = window
    bar = w.find_bar
    view = w.canvas.viewport().geometry()
    assert not bar.isVisible() and bar.parent() is w.canvas
    w.a_find_bar.trigger()
    assert bar.isVisible() and bar.slide.state() == bar.slide.State.Running
    assert bar.slide.startValue().y() < view.top() <= bar.slide.endValue().y()  # (from out of sight, down)
    finish_slide(bar)
    # Over the top right of the pages, the status bar where it was
    view = w.canvas.viewport().geometry()
    assert bar.y() == view.top() and abs(bar.geometry().right() - (view.right() - 6)) <= 1
    assert w.statusBar().isVisible()
    # It follows the corner when the window changes size
    w.resize(w.width() - 100, w.height())
    QApplication.processEvents()
    assert abs(bar.geometry().right() - (w.canvas.viewport().geometry().right() - 6)) <= 1
    # Closing: it goes up, and then it is hidden
    bar.close_bar()
    assert bar.isVisible() and bar.closing
    finish_slide(bar)
    assert not bar.isVisible() and not bar.closing


def test_the_first_place_at_once(window):
    w = window
    bar = w.find_bar
    w.a_find_bar.trigger()
    finish_slide(bar)
    bar.index.pages.clear()  # (nothing read ahead yet)
    w.show_page(2)
    bar.box.setText("scribe")
    bar.run()
    # It stopped at the first place, on the page shown: no other page was read
    assert bar.hit.page == 2 and set(bar.index.pages) == {2} and not bar.complete
    assert bar.said.text() == "Found on page 3"
    # Next, before the counting ends, searches on from there
    bar.step(1)
    assert bar.hit.page == 3 and set(bar.index.pages) == {2, 3}
    count(bar)
    assert bar.complete and len(bar.hits) == 9 and bar.said.text() == "6 of 9"


def test_as_you_type(window):
    w = window
    bar = w.find_bar
    w.a_find_bar.trigger()
    QApplication.processEvents()
    # (the box where the cursor goes; hasFocus() needs the window active, which a test run may not give it)
    assert bar.isVisible() and w.focusWidget() in (bar.combo, bar.box)  # (the combo passes the keys to its box)
    QTest.keyClicks(bar.box, "scri")
    assert bar.timer.isActive()  # (each letter starts the pause again: it searches once the typing stops)
    bar.timer.stop()
    bar.run()
    count(bar)
    # (5 + 2 * 2 places, capitals not minded)
    assert len(bar.hits) == 9 and bar.said.text() == "1 of 9"
    assert w.canvas._found_pages == {0, 1, 2, 3, 4} and w.canvas._found_current[0] == 0
    # (the pages in view are highlighted, and the current place on its own)
    assert w.canvas._found_drawn and len(w.canvas._found_items) == len(w.canvas._found_drawn) + 1
    bar.step(1)
    bar.step(1)
    assert bar.hits.index(bar.hit) == 2 and w.page == 1
    bar.step(-1)
    bar.step(-1)
    bar.step(-1)
    assert bar.hits.index(bar.hit) == 8 and w.page == 4  # (round from the first to the last)
    # Match case
    bar.o_case.setChecked(True)
    count(bar)
    assert len(bar.hits) == 7  # (the "Scribe" with a capital, twice, left out)
    bar.o_case.setChecked(False)
    # Accents: not minded unless asked for
    type_in(bar, "cancion")
    assert len(bar.hits) == 2
    bar.o_accents.setChecked(True)
    count(bar)
    assert len(bar.hits) == 1 and w.settings.value("findbar_accents", type=bool) is True
    type_in(bar, "canción")
    assert len(bar.hits) == 1
    bar.o_accents.setChecked(False)
    count(bar)
    assert len(bar.hits) == 2
    type_in(bar, "scri")
    # All off: only the place shown is highlighted
    bar.b_all.click()
    assert w.canvas._found_pages == frozenset() and w.canvas._found_current is not None
    bar.b_all.click()
    # Nothing found: the box says so, reddish
    type_in(bar, "zebra")
    assert bar.hit is None and bar.said.text() == "Not found" and bar.box.property("missing")
    type_in(bar, "copies")
    assert len(bar.hits) == 5 and not bar.box.property("missing")


def test_history_close_and_the_rest_unchanged(window):
    w = window
    bar = w.find_bar
    w.a_find_bar.trigger()
    type_in(bar, "text")
    QTest.keyClick(bar.box, Qt.Key.Key_Return)  # (Enter: the next place, and the text kept)
    assert bar.combo.itemText(0) == "text" and w.settings.value("findbar_history") == ["text"]
    type_in(bar, "scribe")
    bar.step(1)
    assert [bar.combo.itemText(i) for i in range(bar.combo.count())] == ["scribe", "text"]
    # Esc closes it, and the highlights go
    QTest.keyClick(bar.box, Qt.Key.Key_Escape)
    finish_slide(bar)
    assert not bar.isVisible() and w.canvas._found_current is None and not w.canvas._found_items
    # Without "As you type", only Enter searches
    w.a_find_bar.trigger()
    bar.o_typing.setChecked(False)
    bar.box.clear()
    QTest.keyClicks(bar.box, "again")
    assert not bar.timer.isActive() and bar.hit is None
    QTest.keyClick(bar.box, Qt.Key.Key_Return)
    count(bar)
    assert len(bar.hits) == 2
    # The keys: Ctrl+F and / this panel; Ctrl+Shift+F the dialog with every option
    assert [k.toString() for k in w.a_find_bar.shortcuts()] == ["Ctrl+F", "/"]
    assert w.a_find.shortcut().toString() == "Ctrl+Shift+F"
    # Find all: the panel with this text
    bar.b_all_places.trigger()  # (in the panel's menu)
    assert w.results_dock.isVisible() and w.results_box.text() == "again" and w.results_list.topLevelItemCount() == 2
    # Another document: what was found is forgotten, and searched again
    w.labels_choice = lambda: arrange.FOLLOW
    w.arrange_pages(arrange.Rotate((1,), 90))
    assert bar.q is None and bar.hit is None
    # (the customizer of the toolbars leaves this one alone)
    assert all(b.objectName() != NAME for b in w.editable_bars())


def test_f3_and_the_toolbar(window):
    w = window
    bar = w.find_bar
    # F3 with the panel closed brings it down; with a text, it goes on through its places
    w.a_find_next.trigger()
    finish_slide(bar)
    assert bar.isVisible()
    type_in(bar, "scribe")
    first = bar.hit
    w.a_find_next.trigger()
    assert bar.hit != first
    w.a_find_previous.trigger()
    assert bar.hit == first
    # On the toolbar Find: the dialog and this panel; no quick find box any more
    find = next(b for b in w.toolbars() if b.objectName() == "find")
    assert w.a_find in find.actions() and w.a_find_bar in find.actions()
    assert not hasattr(w, "a_quick_find") and not hasattr(w, "quick_find_key")
