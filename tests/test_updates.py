"""Ayuda > Buscar una versión nueva: la última versión, preguntada a GitHub (aquí, a un urlopen de prueba:
las pruebas no salen a la red), comparada con esta, y cómo se actualiza cada clase de instalación."""

from __future__ import annotations

import io
import json
import time
import urllib.request
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from py_pdftools import __version__
from py_pdftools.core import updates


class Answer(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def answering(monkeypatch, body: bytes | Exception, delay: float = 0) -> list:
    """GitHub's answer, BODY (or the error), after DELAY seconds; the requests made, in the list returned."""
    asked = []

    def urlopen(request, timeout=0):
        asked.append(request)
        time.sleep(delay)
        if isinstance(body, Exception):
            raise body
        return Answer(body)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return asked


def release(tag: str) -> bytes:
    return json.dumps({"tag_name": tag, "html_url": f"https://github.com/nivaca/py-pdftools/releases/tag/{tag}",
                       "assets": []}).encode()


def test_versions_compared():
    assert updates.parse_version("v1.8.11") == (1, 8, 11)
    assert updates.parse_version("2.0rc1") == (2, 0)
    assert updates.newer("1.8.9", "1.8.10")  # (as numbers, not as text)
    assert not updates.newer("1.8.10", "1.8.9")
    assert not updates.newer("1.9", "1.9.0") and not updates.newer("1.9.0", "1.9")
    with pytest.raises(updates.UpdateError):
        updates.parse_version("latest")


def test_latest_asked_plainly(monkeypatch):
    asked = answering(monkeypatch, release("v9.1.0"))
    found = updates.latest()
    assert found == updates.Release("9.1.0", "https://github.com/nivaca/py-pdftools/releases/tag/v9.1.0")
    (request,) = asked
    assert request.full_url == updates.LATEST_URL
    # (nothing about the user goes with it)
    assert request.get_header("User-agent") == "py-pdftools" and request.data is None


@pytest.mark.parametrize("body", [OSError("no connection"), b"<html>", json.dumps({"message": "Not Found"}).encode(),
                                  json.dumps({"tag_name": "nightly"}).encode()])
def test_latest_not_found_out(monkeypatch, body):
    answering(monkeypatch, body)
    with pytest.raises(updates.UpdateError):
        updates.latest()


def test_a_page_elsewhere_is_not_opened(monkeypatch):
    answering(monkeypatch, json.dumps({"tag_name": "v9.0", "html_url": "javascript:alert(1)"}).encode())
    assert updates.latest().url == updates.RELEASES


@pytest.mark.parametrize(("path", "appimage", "kind"), [
    ("/opt/py-pdftools/usr/lib/python3.14/site-packages/py_pdftools", "", "deb"),
    ("/tmp/.mount_py-pdfAbc/usr/lib/python3.14/site-packages/py_pdftools", "/home/u/py.AppImage", "appimage"),
    ("/usr/lib/python3.14/site-packages/py_pdftools", "", "rpm"),
    ("/usr/local/lib/python3.14/site-packages/py_pdftools", "", "pip"),
    ("/home/u/.local/share/py-pdftools/venv/lib/python3.14/site-packages/py_pdftools", "", "installer"),
    ("/home/u/.local/lib/python3.14/site-packages/py_pdftools", "", "pip"),
])
def test_installation(monkeypatch, path, appimage, kind):
    monkeypatch.setenv("APPIMAGE", appimage)
    monkeypatch.setattr(updates.sys, "platform", "linux")
    monkeypatch.setattr(Path, "resolve", lambda self, strict=False: self)
    assert updates.installation(Path(path)) == kind


def test_installation_from_source(tmp_path, monkeypatch):
    monkeypatch.delenv("APPIMAGE", raising=False)
    (tmp_path / "src" / "py_pdftools").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text("")
    (tmp_path / ".git").mkdir()
    assert updates.installation(tmp_path / "src" / "py_pdftools") == "source"


def test_how_to_update_says_the_file():
    for kind in ("deb", "appimage", "installer", "pip"):
        assert "9.1.0" in updates.how_to_update(kind, "9.1.0")
    assert "dnf upgrade" in updates.how_to_update("rpm", "9.1.0")
    assert "git pull" in updates.how_to_update("source", "9.1.0")


@pytest.fixture
def said(monkeypatch):
    QApplication.instance() or QApplication([])
    out = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda _p, _t, text: out.append(("info", text))))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda _p, _t, text: out.append(("warning", text))))
    monkeypatch.setattr(QMessageBox, "exec", lambda box: out.append(("box", box.text(), box.informativeText())))
    return out


def test_window_says_a_newer_one(monkeypatch, said):
    from py_pdftools.gui.updating import check_for_updates

    answering(monkeypatch, release("v99.0.0"), delay=0.2)  # (the dialog waits for it)
    assert check_for_updates(None) == "newer"
    ((kind, text, how),) = said
    assert kind == "box" and "99.0.0" in text and __version__ in text and how


def test_window_says_this_is_the_latest(monkeypatch, said):
    from py_pdftools.gui.updating import check_for_updates

    answering(monkeypatch, release(f"v{__version__}"))
    assert check_for_updates(None) == "latest"
    answering(monkeypatch, release("v0.1"))
    assert check_for_updates(None) == "ahead"
    answering(monkeypatch, OSError("no connection"))
    assert check_for_updates(None) == "error"
    assert [k for k, _ in said] == ["info", "info", "warning"] and "no connection" in said[2][1]


def test_in_the_menu_help():
    QApplication.instance() or QApplication([])
    from py_pdftools.gui.window import MainWindow

    w = MainWindow()
    try:
        help_menu = next(a.menu() for a in w.menuBar().actions() if a.menu() and w.a_check in a.menu().actions())
        assert w.a_updates in help_menu.actions()
    finally:
        w.close()
