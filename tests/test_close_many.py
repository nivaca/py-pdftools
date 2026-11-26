"""Salir con más de un documento abierto, o cerrar una ventana de pestañas que tiene varios, pregunta antes
(Settings > General > "Warn before closing several documents at once"); con uno solo, o con la casilla
apagada, no pregunta. "Warn me again next time" sin marcar apaga el aviso."""

from __future__ import annotations

import pymupdf
import pytest
from PySide6.QtWidgets import QApplication

from py_pdftools.core import config


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
    from py_pdftools.gui import tabs
    from py_pdftools.gui.window import _WINDOWS

    monkeypatch.setattr(tabs, "_ask_close_many", lambda parent, count, quitting: (True, True))
    for w in list(_WINDOWS):
        w.annotations = w.saved = []
        if w.host is not None:
            w.host.close()
        w.close()
    _WINDOWS.clear()
    QApplication.processEvents()


def asking(monkeypatch, answer):
    """The question answered with ANSWER (close, warn again); what it was asked, in the list returned."""
    from py_pdftools.gui import tabs

    asked = []

    def ask(parent, count, quitting):
        asked.append((count, quitting))
        return answer

    monkeypatch.setattr(tabs, "_ask_close_many", ask)
    return asked


def test_a_window_of_tabs(pdfs, monkeypatch):
    from py_pdftools.gui.tabs import open_in_tab

    first = open_in_tab(pdfs[0])
    open_in_tab(pdfs[1], near=first)
    host = first.host
    QApplication.processEvents()
    asked = asking(monkeypatch, (False, True))
    assert not host.close()  # (the user keeps them)
    assert asked == [(2, False)] and host.isVisible() and len(host.windows()) == 2
    asked = asking(monkeypatch, (True, True))
    assert host.close()
    assert asked == [(2, False)] and config.get("warn_many") is True


def test_one_document_and_the_setting(pdfs, monkeypatch):
    from py_pdftools.gui.tabs import may_close_many, open_in_tab

    first = open_in_tab(pdfs[0])
    QApplication.processEvents()
    asked = asking(monkeypatch, (True, False))
    assert may_close_many(None, [first])  # (one only: nothing asked)
    second = open_in_tab(pdfs[1], near=first)
    assert may_close_many(None, [first, second], quitting=True)
    assert asked == [(2, True)] and config.get("warn_many") is False  # ("Warn me again" left unticked)
    assert may_close_many(None, [first, second]) and len(asked) == 1  # (the warning is off now)


def test_quit(pdfs, monkeypatch):
    from py_pdftools import gui
    from py_pdftools.gui.tabs import open_in_tab

    first = open_in_tab(pdfs[0])
    open_in_tab(pdfs[1], near=first)
    QApplication.processEvents()
    asked = asking(monkeypatch, (False, True))
    assert not gui.quit_all()
    assert asked == [(2, True)] and first.is_open()
    quits = []
    monkeypatch.setattr(QApplication.instance(), "quit", lambda: quits.append(1))
    asking(monkeypatch, (True, True))
    assert gui.quit_all() and quits == [1] and not first.is_open()


def test_the_setting_in_the_dialog(pdfs):
    from py_pdftools.gui.prefs import SettingsDialog
    from py_pdftools.gui.tabs import open_in_tab

    win = open_in_tab(pdfs[0])
    dialog = SettingsDialog(win.prefs, win)
    assert dialog.warn_many.isChecked()
    dialog.warn_many.setChecked(False)
    dialog.accept()
    assert config.get("warn_many") is False
