"""Ayuda > Restablecer todos los ajustes (core/config.reset, gui.reset_settings): config.toml se aparta como
copia fechada, los demás archivos de la carpeta se quedan, nada se toca si se cancela o si una ventana no se
cierra, y lo que las ventanas escriben al cerrarse queda en la copia, no en una configuración nueva."""

from __future__ import annotations

import pytest

from py_pdftools.core import config


def test_reset_moves_the_file_aside():
    assert config.reset() is None  # (no settings yet)
    path = config.set("theme", "dark")
    (path.parent / "mystamps").mkdir()
    (path.parent / "codes.xml").write_text("<codes/>")
    text = path.read_text()
    first = config.reset()
    assert not path.exists() and first.parent == path.parent and first.read_text() == text
    assert first.name.startswith("config-") and first.suffix == ".toml"
    assert config.get("theme") == "system"  # (the usual value again)
    assert (path.parent / "mystamps").is_dir() and (path.parent / "codes.xml").is_file()
    config.set("theme", "light")
    second = config.reset()  # (in the same second, most likely: a name of its own)
    assert second != first and first.exists() and "light" in second.read_text()


@pytest.fixture
def window(monkeypatch):
    from PySide6.QtWidgets import QApplication

    from py_pdftools.gui.window import _WINDOWS, MainWindow

    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.ask_recover = lambda when: False
    _WINDOWS.append(w)
    w.show()
    yield w
    w.close()
    if w in _WINDOWS:
        _WINDOWS.remove(w)


def answer(monkeypatch, button: str):
    """The confirmation answered with BUTTON ('Reset and close' or 'Cancel'), and the program not ended."""
    from PySide6.QtWidgets import QMessageBox

    shown = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(QMessageBox, "clickedButton",
                        lambda self: next(b for b in self.buttons() if b.text().replace("&", "") == button))
    monkeypatch.setattr(QMessageBox, "information", lambda parent, title, text: shown.append(text))
    ended = []
    monkeypatch.setattr("py_pdftools.gui.end", lambda: ended.append(True))
    return shown, ended


def test_from_the_help_menu(window, monkeypatch):
    path = config.set("theme", "dark")
    assert window.a_reset_settings in window.menuBar().actions()[-1].menu().actions()
    shown, ended = answer(monkeypatch, "Cancel")
    assert not window.reset_settings_dialog() and path.exists() and window.isVisible()
    shown, ended = answer(monkeypatch, "Reset and close")
    assert window.reset_settings_dialog()
    backups = list(path.parent.glob("config-*.toml"))
    assert not window.isVisible() and ended == [True] and len(backups) == 1
    assert not path.exists()  # (what the window wrote as it closed went into the copy)
    assert 'theme = "dark"' in backups[0].read_text() and "[window]" in backups[0].read_text()
    assert str(backups[0]) in shown[0]


def test_a_window_that_stays(window, monkeypatch):
    path = config.set("theme", "dark")
    shown, ended = answer(monkeypatch, "Reset and close")
    window.maybe_discard = lambda: False  # (Cancel, asked about its unsaved changes)
    assert not window.reset_settings_dialog()
    assert path.exists() and not ended and not list(path.parent.glob("config-*.toml"))
    del window.maybe_discard
