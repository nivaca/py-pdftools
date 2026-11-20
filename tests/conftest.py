from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def own_config(tmp_path, monkeypatch):
    """A configuration folder of its own, so the tests don't read or change the user's."""
    monkeypatch.setenv("PY_PDFTOOLS_CONFIG", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    from py_pdftools.core import interface

    interface.use(None)


@pytest.fixture(autouse=True)
def pages_here(monkeypatch):
    """Pages rendered, and redacted copies saved, in the tests' own process, at once (a test may turn
    this off)."""
    from py_pdftools.gui import renderer
    from py_pdftools.gui.redact import background

    monkeypatch.setattr(renderer, "ENABLED", False)
    monkeypatch.setattr(background, "ENABLED", False)


@pytest.fixture(autouse=True)
def annotating_first(monkeypatch):
    """The window starts in the mode Annotate (its tests come from py-annotate's), not in Read, as it does
    the first time a user opens it (a test may set the mode itself)."""
    from py_pdftools.gui import window

    monkeypatch.setattr(window, "DEFAULT_MODE", "annotate")


@pytest.fixture(autouse=True)
def own_window_settings():
    """The window's own settings (QSettings: its mode, the arrangement of each mode, the toolbars...)
    cleared for each test: Qt reads where they are once in a process, so the tests would share them."""
    from PySide6.QtCore import QSettings

    for app in ("py-pdftools", "py-pdftools-impose"):
        QSettings("py-pdftools", app).clear()
    yield


@pytest.fixture(autouse=True)
def own_cache(tmp_path_factory, monkeypatch):
    """The cache folder (where the working copies go: see gui/working.work_root) in a folder of the
    tests, never the user's own."""
    cache = tmp_path_factory.mktemp("cache")
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache))
    monkeypatch.setenv("LOCALAPPDATA", str(cache))
