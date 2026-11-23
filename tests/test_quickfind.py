"""La búsqueda rápida (gui/quickfind.py): la casilla de la barra Buscar, que va de un lugar encontrado al
siguiente sin abrir el diálogo."""

from __future__ import annotations

import pymupdf
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLineEdit

from py_pdftools.gui.window import MainWindow


@pytest.fixture
def window(tmp_path, monkeypatch):
    path = tmp_path / "words.pdf"
    doc = pymupdf.open()
    for text in ("alpha", "nothing", "Árbol and alpha", "beta", "ALPHA"):
        doc.new_page().insert_text((72, 72), text, fontsize=20)
    doc.save(path)
    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    w = MainWindow()
    w.ask_recover = lambda when: False
    w.resize(1800, 900)  # (wide: in a narrow window the box goes to the overflow of its toolbar)
    w.show()
    assert w.open_path(path)
    QApplication.processEvents()
    yield w
    w.annotations = w.saved = []
    w.drop_work()
    w.close()


def box_of(window) -> QLineEdit:
    boxes = window.a_quick_find.boxes()
    assert boxes, "the toolbar Find has a quick find box"
    return boxes[0]


def found(window) -> str:
    from PySide6.QtWidgets import QLabel

    return window.a_quick_find.createdWidgets()[0].findChild(QLabel, "found").text()


def test_enter_goes_through_the_places_found(window):
    box = box_of(window)
    box.setText("alpha")
    pages = []
    for _ in range(4):  # (three places, without minding case: the fourth goes round to the first)
        window.a_quick_find.step(box, 1)
        pages.append(window.page)
    assert pages == [0, 2, 4, 0] and found(window) == "1/3"
    window.a_quick_find.step(box, -1)
    assert window.page == 4 and found(window) == "3/3"
    box.setText("arbol")  # (sin acentos: Árbol)
    window.a_quick_find.step(box, 1)
    assert window.page == 2 and found(window) == "1/1"
    box.setText("gamma")
    window.a_quick_find.step(box, 1)
    assert found(window) == "Not found" and window.a_quick_find.matches == []


def test_it_starts_from_the_page_shown(window):
    window.show_page(3)
    box = box_of(window)
    box.setText("alpha")
    window.a_quick_find.step(box, 1)
    assert window.page == 4
    box.setText("alph")
    window.show_page(3)
    window.a_quick_find.step(box, -1)
    assert window.page == 2


def test_the_key_puts_the_cursor_in_the_box_and_esc_takes_it_out(window):
    box = box_of(window)
    window.activateWindow()
    window.quick_find_key.trigger()
    QApplication.processEvents()
    assert window.focusWidget() is box, (window.focusWidget(), box.isVisible())
    from PySide6.QtTest import QTest

    QTest.keyClick(box, Qt.Key.Key_Escape)
    assert window.focusWidget() is window.canvas



def test_without_a_document_it_is_off(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    w = MainWindow()
    try:
        assert w.doc is None and not w.a_quick_find.isEnabled() and not w.quick_find_key.isEnabled()
    finally:
        w.close()


def test_f3_and_shift_f3_go_on_through_the_places(window):
    """F3 y Mayús+F3, como en Okular y los programas de KDE; sin texto, F3 pone el cursor en la casilla."""
    assert window.a_find_next.shortcut().toString() == "F3"
    assert window.a_find_previous.shortcut().toString() == "Shift+F3"
    assert "/" in [k.toString() for k in window.quick_find_key.shortcuts()]
    box = box_of(window)
    asked = []
    window.quick_find = lambda: asked.append(True)  # (sin ventana activa, el foco no se puede comprobar)
    window.a_find_next.trigger()
    assert asked
    box.setText("alpha")
    window.a_find_next.trigger()
    window.a_find_next.trigger()
    assert window.page == 2 and found(window) == "2/3"
    window.a_find_previous.trigger()
    assert window.page == 0 and found(window) == "1/3"


def test_the_panel_of_the_search_results(window):
    """Ver > Paneles > Resultados de la búsqueda (F8): todos los lugares, con su página y su contexto; un clic
    lleva a cada uno; toma el texto de la búsqueda rápida y se vacía con otro documento."""
    assert window.a_results.shortcut().toString() == "F8" and window.results_dock.isHidden()
    box_of(window).setText("alpha")
    window.find_all()
    assert window.results_dock.isVisible() and window.results_box.text() == "alpha"
    tree = window.results_list
    assert tree.topLevelItemCount() == 3
    assert [tree.topLevelItem(i).text(0) for i in range(3)] == ["1", "3", "5"]
    assert "[alpha]" in tree.topLevelItem(1).text(1) and "Árbol" in tree.topLevelItem(1).text(1)
    window.go_result(tree.topLevelItem(2))
    assert window.page == 4
    window.results_case.setChecked(True)  # (distinguir mayúsculas: ALPHA ya no es alpha)
    assert tree.topLevelItemCount() == 2
    window.results_box.setText("arbol")  # (sin mayúsculas ni acentos otra vez)
    window.results_case.setChecked(False)
    assert tree.topLevelItemCount() == 1 and window.list_results() == 1
    from py_pdftools.gui.results import _marked, _short

    assert _short("one two three four five six seven [it] after") == "…four five six seven [it] after"

    assert _marked("a <b> [x&y] c") == "a &lt;b&gt; <b>x&amp;y</b> c"
    window.results_clear()
    assert tree.topLevelItemCount() == 0
