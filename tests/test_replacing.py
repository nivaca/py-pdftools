"""core/replacing.py: reemplazar un archivo que otro proceso tiene abierto un momento (Windows)."""

from __future__ import annotations

import pytest

from py_pdftools.core import replacing


def flaky(times: int):
    """An os.replace that fails TIMES times with PermissionError, as on Windows while the target is held."""
    calls = []

    def fake(source, target):
        calls.append((source, target))
        if len(calls) <= times:
            raise PermissionError(13, "The process cannot access the file")

    return fake, calls


def test_windows_waits_for_the_file(monkeypatch):
    fake, calls = flaky(3)
    monkeypatch.setattr(replacing.os, "replace", fake)
    monkeypatch.setattr(replacing.sys, "platform", "win32")
    monkeypatch.setattr(replacing.time, "sleep", lambda s: None)
    replacing.replace("a", "b")
    assert len(calls) == 4


def test_windows_gives_up_at_last(monkeypatch):
    fake, calls = flaky(1000)
    monkeypatch.setattr(replacing.os, "replace", fake)
    monkeypatch.setattr(replacing.sys, "platform", "win32")
    monkeypatch.setattr(replacing.time, "sleep", lambda s: None)
    with pytest.raises(PermissionError):
        replacing.replace("a", "b")
    assert len(calls) == replacing.TRIES


def test_elsewhere_a_refusal_is_at_once(monkeypatch):
    fake, calls = flaky(1)
    monkeypatch.setattr(replacing.os, "replace", fake)
    monkeypatch.setattr(replacing.sys, "platform", "linux")
    with pytest.raises(PermissionError):
        replacing.replace("a", "b")
    assert len(calls) == 1


def test_a_real_file(tmp_path):
    (tmp_path / "new").write_text("new")
    (tmp_path / "old").write_text("old")
    replacing.replace(tmp_path / "new", tmp_path / "old")
    assert (tmp_path / "old").read_text() == "new" and not (tmp_path / "new").exists()
