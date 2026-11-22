"""La revisión de la configuración (core/health.py y gui/health_dialog.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from py_pdftools.core import config, health


def statuses(checks, title) -> list[str]:
    return [c.status for c in checks if c.title == title]


def test_a_new_configuration_is_fine():
    checks = health.configuration()
    assert [c.status for c in checks] == [health.OK, health.OK]
    assert "not made yet" in checks[0].detail


def test_a_file_that_cant_be_read():
    config.config_path().parent.mkdir(parents=True, exist_ok=True)
    config.config_path().write_text("[parameters\nauthor = ", encoding="utf-8")
    (only,) = health.configuration()
    assert only.status == health.ERROR and only.fix


def test_values_wrong_and_unknown():
    config.set_many({"author": "Ana", "memory": "huge", "highlight_opacity": 7, "shortcut_highlight": "Shift+H",
                     "palette_2_color": "#00ff00", "rect_font_size": 12, "nothing_like_this": 1})
    checks = health.configuration()
    wrong = next(c for c in checks if c.status == health.WARNING)
    unknown = next(c for c in checks if c.status == health.INFO)
    # (font_size no vale para un rectángulo: no lleva texto)
    assert "memory" in wrong.detail and "highlight_opacity" in wrong.detail and "rect_font_size" in wrong.detail
    assert "author" not in wrong.detail and "palette_2_color" not in wrong.detail
    assert "nothing_like_this" in unknown.detail and "memory" not in unknown.detail


def test_every_setting_the_program_writes_is_known():
    from py_pdftools.annotate import settings

    defaults = settings.Settings(author="Ana", autosave=5, pdfconform="/x", categories=("A",), ocr_language="lat",
                                 pen_pressure="off", pen_curve="firm", pen_button="menu")
    settings.save(defaults)
    params = config.read()["parameters"]
    assert params and all(health.known(n) and health.valid(n, v) for n, v in params.items()), params


def test_without_tesseract(monkeypatch):
    from py_pdftools.core import ocr

    monkeypatch.setattr(ocr, "available", lambda: False)
    (only,) = health.ocr()
    assert only.status == health.WARNING and "tesseract" in only.fix


def test_ocr_languages_not_installed(monkeypatch):
    from py_pdftools.core import ocr

    monkeypatch.setattr(ocr, "available", lambda: True)
    monkeypatch.setattr(ocr, "version", lambda: "5")
    monkeypatch.setattr(ocr, "program", lambda: "/usr/bin/tesseract")
    monkeypatch.setattr(ocr, "languages", lambda: ["eng"])
    # (as on a computer that has only English: the check must report it, not stop at it)
    monkeypatch.setattr(ocr, "models", lambda: {"eng": Path("eng.traineddata")})
    config.set("ocr_language", "lat+eng")
    checks = health.ocr()
    assert checks[1].status == health.WARNING and "lat" in checks[1].detail and "eng" not in checks[1].detail


def test_report_and_worst():
    checks = [health.Check(health.OK, "A", "fine"), health.Check(health.WARNING, "B", "so so", "do this")]
    text = health.report(checks)
    assert "A: fine" in text and "B: so so" in text and "→ do this" in text
    assert health.worst(checks) == health.WARNING and health.worst([]) == health.OK


def test_python_and_libraries():
    assert health.python().status == health.OK
    assert all(c.status == health.OK for c in health.libraries())


@pytest.fixture
def window(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from py_pdftools.gui.window import MainWindow

    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    w = MainWindow()
    w.show()
    yield w
    w.close()


def test_the_shortcuts_of_the_window(window):
    from py_pdftools.annotate import settings
    from py_pdftools.gui import health_dialog

    (fine,) = health_dialog.shortcuts(window)
    assert fine.status == health.OK
    # Un atajo cambiado en la Configuración que ya es el de otra acción (Ctrl+F: Buscar y resaltar)
    window.prefs = settings.Settings(shortcuts=tuple((a, "Ctrl+F" if a == "highlight" else k)
                                                     for a, k in settings.SHORTCUTS.items()))
    settings.save(window.prefs)
    window.apply_shortcuts() if hasattr(window, "apply_shortcuts") else None
    checks = health_dialog.shortcuts(window)
    assert any(c.status == health.WARNING and "Ctrl+F" in c.detail for c in checks), checks


def test_the_dialog(window):
    from py_pdftools.gui.health_dialog import HealthDialog

    d = HealthDialog(window)
    assert d.list.topLevelItemCount() == len(d.checks) > 8
    d.close()


def test_the_graphics_card_when_asked_for(tmp_path, monkeypatch):
    """With the setting gpu, the pages are drawn by OpenGL where it works (the tests' Xvfb has it, by
    software), and as usual where it doesn't (offscreen); the check says which."""
    from PySide6.QtWidgets import QApplication

    from py_pdftools.gui import canvas as drawing
    from py_pdftools.gui import health_dialog
    from py_pdftools.gui.window import MainWindow

    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    config.set("gpu", True)
    w = MainWindow()
    w.show()
    QApplication.processEvents()
    try:
        works = drawing.opengl_works() == ""
        assert w.canvas.gpu == works
        assert type(w.canvas.viewport()).__name__ == ("QOpenGLWidget" if works else "QWidget")
        check = health_dialog.graphics(w)
        assert check.status == (health.OK if works else health.WARNING)
    finally:
        w.close()
    config.set("gpu", False)
    w = MainWindow()
    try:
        assert not w.canvas.gpu and health_dialog.graphics(w) is None
    finally:
        w.close()


def test_where_the_check_is(window, monkeypatch):
    """The check is in Help, and on the row of buttons of Settings, seen from every tab (at the foot of
    General, under a long list, it went unseen)."""
    from PySide6.QtWidgets import QDialogButtonBox

    from py_pdftools.gui import health_dialog
    from py_pdftools.gui.prefs import SettingsDialog

    opened = []
    monkeypatch.setattr(health_dialog.HealthDialog, "exec", lambda self: opened.append(self) or 0)
    assert window.a_check in window.menuBar().actions()[-1].menu().actions()
    window.a_check.trigger()
    d = SettingsDialog(window.prefs, window)
    assert isinstance(d.check.parent(), QDialogButtonBox)
    d.check.click()
    assert len(opened) == 2
