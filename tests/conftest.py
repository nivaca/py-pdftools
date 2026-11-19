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
