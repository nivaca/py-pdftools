"""Archivo > Cerrar el documento (Ctrl+W): solo el documento, su pestaña o su ventana; el último deja una ventana
(o pestaña) vacía y el programa sigue abierto; si el usuario conserva el documento (sus cambios), la vacía se
va. Salir (Ctrl+Q, y también Alt+F4) cierra todo."""

from __future__ import annotations

import pymupdf
import pytest
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication


@pytest.fixture
def pdfs(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    paths = []
    for name in ("one", "two"):
        path = tmp_path / f"{name}.pdf"
        doc = pymupdf.open()
        doc.new_page().insert_text((72, 72), name)
        doc.save(path)
        paths.append(path)
    yield paths
    from py_pdftools.gui.window import _WINDOWS

    for w in list(_WINDOWS):
        w.annotations = w.saved = []
        if w.host is not None:
            w.host.close()
        w.close()
    _WINDOWS.clear()
    QApplication.processEvents()


def open_ones():
    from py_pdftools.gui.window import _WINDOWS

    return [w for w in _WINDOWS if w.is_open()]


def test_the_keys():
    from py_pdftools.gui.window import MainWindow

    QApplication.instance() or QApplication([])
    w = MainWindow()
    try:
        assert QKeySequence(QKeySequence.StandardKey.Close) in w.a_close.shortcuts()
        assert w.a_close.text() == "Close document"
        assert QKeySequence("Alt+F4") in w.a_quit.shortcuts()
        assert QKeySequence(QKeySequence.StandardKey.Quit) in w.a_quit.shortcuts()
    finally:
        w.close()


def test_tabs(pdfs):
    from py_pdftools.gui.tabs import open_in_tab

    first = open_in_tab(pdfs[0])
    second = open_in_tab(pdfs[1], near=first)
    host = first.host
    QApplication.processEvents()
    assert second.close_document()  # (one of two: only its tab goes)
    assert host.windows() == [first] and host.isVisible()
    assert first.close_document()  # (the last: an empty tab takes its place)
    QApplication.processEvents()
    left = open_ones()
    assert host.isVisible() and len(left) == 1 and left[0] is not first and left[0].path is None
    assert left[0].host is host
    assert not left[0].close_document()  # (nothing to close: it stays)
    assert open_ones() == left


def test_a_window_by_itself(pdfs):
    from py_pdftools.gui import open_window

    win = open_window(pdfs[0])
    win.ask_recover = lambda when: False
    QApplication.processEvents()
    win.maybe_discard = lambda: False  # (the user keeps its unsaved changes)
    assert not win.close_document()
    assert open_ones() == [win] and win.path == pdfs[0]
    del win.maybe_discard
    assert win.close_document()
    QApplication.processEvents()
    left = open_ones()
    assert len(left) == 1 and left[0] is not win and left[0].path is None and left[0].isVisible()
