"""Lo que la ventana guarda de sí misma (gui/state.py): en config.toml, con los ajustes, en las tablas [window]
e [impose]; devuelto como lo devolvía QSettings; y lo que QSettings guardaba antes, traído una vez."""

from __future__ import annotations

import sys

import pytest
from PySide6.QtCore import QByteArray, QSettings
from PySide6.QtWidgets import QApplication

from py_pdftools.core import config
from py_pdftools.gui import state
from py_pdftools.gui.state import State


def test_one_file_for_everything():
    config.set("tabs", True)
    window = State("window")
    window.setValue("geometry", QByteArray(b"\x00\x01\xffstate"))
    window.setValue("recent", ["/a/b.pdf", 'c "d".pdf'])
    window.setValue("thumbnails", True)
    window.setValue("thumb_height", 160)
    State("impose").setValue("mode", "basic")
    config.set("memory", "high")  # (a setting changed after: the window's tables are kept)
    data = config.read()
    assert data["parameters"] == {"tabs": True, "memory": "high"}
    assert set(data) == {"parameters", "window", "impose"} and data["impose"] == {"mode": "basic"}
    assert sorted(p.name for p in config.config_dir().iterdir()) == ["config.toml"]
    state._CACHE.clear()  # (as in another session)
    assert window.value("geometry") == QByteArray(b"\x00\x01\xffstate")
    assert window.value("recent") == ["/a/b.pdf", 'c "d".pdf']
    # (as QSettings gave them back from its file: booleans as text, unless asked for one)
    assert window.value("thumbnails") == "true" and window.value("thumbnails", type=bool) is True
    assert int(window.value("thumb_height")) == 160
    assert window.value("missing", "usual") == "usual" and window.value("missing", True, type=bool) is True
    window.remove("recent")
    assert not window.contains("recent") and "recent" not in config.read()["window"]


def test_a_change_from_outside_is_read(tmp_path):
    window = State("window")
    window.setValue("mode", "read")
    text = config.config_path().read_text(encoding="utf-8").replace('mode = "read"', 'mode = "ocr"')
    config.config_path().write_text(text + "\n", encoding="utf-8")
    assert window.value("mode") == "ocr"


def test_a_damaged_file_starts_afresh():
    config.config_dir().mkdir(parents=True, exist_ok=True)
    config.config_path().write_text("[window\nbroken", encoding="utf-8")
    assert State("window").value("mode", "read") == "read"


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="QSettings's own file, as on Linux")
def test_what_qsettings_kept_is_brought(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    old_dir = tmp_path / "old"
    QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, str(old_dir))
    try:
        old = QSettings("py-pdftools", "py-pdftools")
        old.setValue("mode", "ocr")
        old.setValue("toolbars", QByteArray(b"\x00bars"))
        old.setValue("session", ["/x.pdf", "/y.pdf"])
        old.sync()
        conf = old_dir / "py-pdftools" / "py-pdftools.conf"
        assert conf.is_file()
        del old
        monkeypatch.delenv(config.ENV)  # (the user's own configuration: only that one is migrated)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        state._CACHE.clear()
        window = State("window")
        assert window.value("mode") == "ocr" and window.value("toolbars") == QByteArray(b"\x00bars")
        assert window.value("session") == ["/x.pdf", "/y.pdf"]
        assert not conf.exists()  # (one file only, from now on)
        assert config.read()["window"]["mode"] == "ocr"
    finally:
        QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, str(tmp_path / "xdg"))


def test_not_brought_into_another_configuration(tmp_path):
    """With PY_PDFTOOLS_CONFIG (the tests', or another kept apart), QSettings is the user's: not touched."""
    QApplication.instance() or QApplication([])
    QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, str(tmp_path / "old"))
    try:
        old = QSettings("py-pdftools", "py-pdftools")
        old.setValue("mode", "ocr")
        old.sync()
        assert State("window").value("mode") is None
        assert QSettings("py-pdftools", "py-pdftools").value("mode") == "ocr"
    finally:
        QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, str(tmp_path / "xdg"))
