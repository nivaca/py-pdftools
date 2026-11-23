"""La accesibilidad de la ventana: cada casilla, lista y vista tiene un nombre para los lectores de pantalla, el
foco pasa de panel en panel con el teclado (Ctrl+F6), y hay un tema de alto contraste."""

from __future__ import annotations

import pymupdf
import pytest
from PySide6.QtWidgets import (
    QAbstractItemView, QAbstractSpinBox, QApplication, QComboBox, QGraphicsView, QHeaderView, QLabel, QLineEdit,
)

from py_pdftools.gui.window import MainWindow


@pytest.fixture
def window(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    path = tmp_path / "doc.pdf"
    doc = pymupdf.open()
    for i in range(3):
        doc.new_page().insert_text((72, 72), f"Page {i + 1}", fontsize=20)
    doc.set_toc([[1, "One", 1], [1, "Two", 2]])
    doc.save(path)
    w = MainWindow()
    w.ask_recover = lambda when: False
    w.resize(1500, 900)
    w.show()
    assert w.open_path(path)
    QApplication.processEvents()
    yield w
    w.annotations = w.saved = []
    w.drop_work()
    w.close()


def unnamed(window) -> list[str]:
    """The fields, lists and views of WINDOW without a name a screen reader can say (nor a label for them)."""
    labelled = {id(label.buddy()) for label in window.findChildren(QLabel) if label.buddy() is not None}
    out = []
    for kind in (QLineEdit, QComboBox, QAbstractSpinBox, QAbstractItemView, QGraphicsView):
        for w in window.findChildren(kind):
            # (the line edit inside an editable combo box, or a spin box, is named through it)
            if isinstance(w, QLineEdit) and isinstance(w.parent(), (QComboBox, QAbstractSpinBox)):
                continue
            if isinstance(w, QAbstractItemView) and isinstance(w.parent(), QComboBox):
                continue
            if w.window() is not window or id(w) in labelled or isinstance(w, QHeaderView):
                continue
            if not w.accessibleName().strip():
                out.append(f"{type(w).__name__} {w.objectName()!r} {w.toolTip()[:40]!r}")
    return out


def test_everything_has_a_name(window):
    for mode in ("read", "ocr", "annotate", "redact", "pages", "impose"):
        window.set_mode(mode)
        assert unnamed(window) == [], mode


def test_the_keyboard_goes_from_panel_to_panel(window):
    """Ctrl+F6 lleva el foco a la parte siguiente (miniaturas, páginas, cada panel visible); Ctrl+Mayús+F6, a
    la anterior; y da la vuelta."""
    from py_pdftools.gui import access

    assert window.a_next_panel.shortcut().toString() == "Ctrl+F6"
    assert window.a_prev_panel.shortcut().toString() == "Ctrl+Shift+F6"
    window.set_mode("read")
    window.outline_dock.show()
    QApplication.processEvents()
    targets = access.focus_targets(window)
    assert targets[:2] == [window.pages, window.canvas] and window.outline_filter in targets
    seen = [access.focus_panel(window, 1) for _ in range(len(targets))]
    assert set(map(id, seen)) == set(map(id, targets))  # (each once, in turn)
    first = access.focus_panel(window, 1)
    assert access.focus_panel(window, -1) is seen[-1] and first is seen[0]


def test_names_from_tooltips_and_placeholders():
    from py_pdftools.gui.access import _first_clause

    assert _first_clause("The zoom: type a percentage and press Enter") == "The zoom"
    assert _first_clause("Only annotations of this kind") == "Only annotations of this kind"
    assert _first_clause("<b>Bold</b> thing. More") == "Bold thing"


def test_a_theme_of_high_contrast():
    from PySide6.QtGui import QPalette

    from py_pdftools.gui import appearance

    QApplication.instance() or QApplication([])
    assert "contrast" in appearance.THEMES
    pal = appearance.palette("contrast")
    assert pal.color(QPalette.ColorRole.Window).name() == "#000000"
    assert pal.color(QPalette.ColorRole.WindowText).name() == "#ffffff"
    assert pal.color(QPalette.ColorRole.Highlight).name() == "#ffff00"
    assert pal.color(QPalette.ColorRole.HighlightedText).name() == "#000000"
    appearance.apply_theme("contrast")
    try:
        assert QApplication.palette().color(QPalette.ColorRole.Base).name() == "#000000"
        assert "#ffff00" in QApplication.instance().styleSheet()  # (the field with the focus, framed in yellow)
    finally:
        appearance.apply_theme("system")
    assert QApplication.instance().styleSheet() == ""
