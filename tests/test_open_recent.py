"""Archivo > Abrir reciente: en la ventana sin documento, ahí; con un documento, en una pestaña nueva a su lado
(antes lo reemplazaba); un documento ya abierto solo pasa al frente."""

from __future__ import annotations

import pymupdf
import pytest
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


def test_open_recent(pdfs, tmp_path):
    from py_pdftools.gui import open_window

    win = open_window(None)
    win.ask_recover = lambda when: False
    QApplication.processEvents()
    assert win.open_recent(pdfs[0]) and win.path == pdfs[0]  # (an empty window takes it)
    assert win.open_recent(pdfs[1])
    QApplication.processEvents()
    ones = open_ones()
    assert win.path == pdfs[0] and len(ones) == 2  # (the other one in a tab beside it)
    other = next(w for w in ones if w is not win)
    assert other.path == pdfs[1] and other.host is not None and other.host is win.host
    assert win.open_recent(pdfs[1]) and len(open_ones()) == 2  # (already open: only shown)
    assert win.host.current() is other
    assert not win.open_recent(tmp_path / "gone.pdf")
    QApplication.processEvents()
    assert len(open_ones()) == 2
