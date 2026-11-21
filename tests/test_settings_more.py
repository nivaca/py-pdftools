"""Settings > Appearance and Documents: the colours and the size of the interface, the hints of the modes, the
toolbars of every window; how a document opens, its place remembered or not, links asked about or not, the
recent documents, where the file dialogs start. Each kept in the configuration file and in effect at once."""

from __future__ import annotations

import pymupdf
import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from py_pdftools.core import config
from py_pdftools.gui import appearance
from py_pdftools.gui.prefs import SettingsDialog
from py_pdftools.gui.window import _WINDOWS, MainWindow


@pytest.fixture
def window(tmp_path):
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.ask_recover = lambda when: False
    _WINDOWS.append(w)
    yield w
    w.close()
    if w in _WINDOWS:
        _WINDOWS.remove(w)


def doc(path, pages=3):
    d = pymupdf.open()
    for _ in range(pages):
        d.new_page()
    d.save(path)
    return path


def test_defaults():
    assert [appearance.value(k) for k in ("theme", "scale", "hints", "opening", "places", "ask_links", "recent",
                                          "dialogs")] == ["system", 100, True, "document", True, True, 10, "last"]


def test_appearance(window):
    app = QApplication.instance()
    points = app.font().pointSizeF()
    d = SettingsDialog(window.prefs, window)
    d.scale.setCurrentIndex(d.scale.findData(125))
    d.theme.setCurrentIndex(d.theme.findData("dark"))
    d.hints.setChecked(False)
    d.bar_style.setCurrentIndex(d.bar_style.findData("beside"))
    d.bar_size.setCurrentIndex(d.bar_size.findData(32))
    d.accept()
    assert config.get("scale") == 125 and config.get("theme") == "dark" and config.get("hints") is False
    assert abs(app.font().pointSizeF() - points * 1.25) < 0.2
    bar = next(b for b in window.toolbars() if b.objectName() == "file")
    assert bar.toolButtonStyle().name == "ToolButtonTextBesideIcon" and bar.iconSize().width() == 32
    window.hint.show_text("")
    window.set_mode("annotate")
    assert not window.hint.isVisible()  # (no hint: the setting says so)
    appearance.apply_scale(100)
    appearance.apply_theme("system")


def test_documents(window, tmp_path, monkeypatch):
    first = doc(tmp_path / "a.pdf", 5)
    d = SettingsDialog(window.prefs, window)
    d.opening.setCurrentIndex(d.opening.findData("actual"))
    d.places.setChecked(False)
    d.ask_links.setChecked(False)
    d.recent.setValue(2)
    d.dialogs.setCurrentIndex(d.dialogs.findData("document"))
    d.accept()
    assert window.open_path(first)
    assert abs(window.canvas.zoom() - 1.0) < 0.01  # (opened at actual size)
    window.show_page(3)
    window.remember_file_place()
    assert window._places() == {}  # (places not remembered)
    assert window.last_dir() == str(tmp_path)  # (the document's folder)
    for name in ("b.pdf", "c.pdf"):
        window.open_path(doc(tmp_path / name))
    assert [p.name for p in window.recent_files()] == ["c.pdf", "b.pdf"]
    assert len([a for a in window.m_recent.actions() if a.text().startswith("&")]) == 2
    opened = []
    monkeypatch.setattr("py_pdftools.gui.navigation.QDesktopServices.openUrl", lambda url: opened.append(url) or True)
    monkeypatch.setattr(QMessageBox, "question", lambda *a: pytest.fail("not asked: the setting says so"))
    assert window.open_address("https://example.org") and len(opened) == 1
    d = SettingsDialog(window.prefs, window)
    d._clear_recent()
    assert window.recent_files() == []


def test_language_from_settings(window, monkeypatch):
    changed = []
    monkeypatch.setattr(window, "change_language", changed.append)
    d = SettingsDialog(window.prefs, window)
    d.language.setCurrentIndex(d.language.findData("es"))
    monkeypatch.setattr(SettingsDialog, "exec", lambda self: (self.language.setCurrentIndex(
        self.language.findData("es")), self.accept(), 1)[2])
    window.settings_dialog()
    for _ in range(5):
        QApplication.processEvents()
    assert changed == ["es"]
