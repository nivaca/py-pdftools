"""Running in the background (gui/instance.py): a second start gives its files to the program running,
which opens them; Quit ends it; the setting turns it on and off."""

from __future__ import annotations

import subprocess
import sys
import time
import uuid

import pymupdf
import pytest
from PySide6.QtWidgets import QApplication

from py_pdftools import gui
from py_pdftools.core import config
from py_pdftools.gui import instance
from py_pdftools.gui.window import _WINDOWS


@pytest.fixture
def app(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    # (a socket of the test's own: never that of a py-pdftools the user has running)
    monkeypatch.setenv("PY_PDFTOOLS_SOCKET", f"py-pdftools-test-{uuid.uuid4().hex[:8]}")
    monkeypatch.setenv("HOME", str(tmp_path))
    yield app
    gui.background(False)
    for win in list(_WINDOWS):
        win.annotations = win.saved = []
        win.close()
    _WINDOWS.clear()
    app.setQuitOnLastWindowClosed(True)


def pdf(path):
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), path.stem)
    doc.save(path)
    return path


def wait(app, done, seconds=10):
    end = time.time() + seconds
    while not done() and time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def test_files_given_to_the_program_running(app, tmp_path):
    before = list(_WINDOWS)  # (windows other tests left: not this test's)
    assert gui.background(True)
    assert not app.quitOnLastWindowClosed() and instance.server_name().startswith("py-pdftools-test-")
    # (another start, sending its files: a process of its own, as when py-pdftools-gui is started again; the
    # program running answers from here)
    files = [str(pdf(tmp_path / "one.pdf")), str(pdf(tmp_path / "two.pdf"))]
    sender = subprocess.Popen([sys.executable, "-c", f"from py_pdftools.gui import instance; "
                                                      f"print(instance.send({files!r}))"],
                              stdout=subprocess.PIPE, text=True)
    wait(app, lambda: sender.poll() is not None, seconds=30)
    assert sender.stdout.read().strip() == "True"
    def opened():
        return sorted(w.path.name for w in _WINDOWS if w not in before and w.path is not None)

    wait(app, lambda: len(opened()) == 2)
    assert opened() == ["one.pdf", "two.pdf"]
    # (the last window closed: the program goes on)
    for win in list(_WINDOWS):
        win.close()
    assert gui._INSTANCE.server is not None
    gui.background(False)
    assert app.quitOnLastWindowClosed() and gui._INSTANCE.server is None
    assert not instance.send([])  # (no program running: nobody answers)


def test_a_second_start_ends_at_once(app, tmp_path, monkeypatch):
    """With the setting on and a program running, the second start gives it the files and ends, without a
    window of its own."""
    config.set("background", True)
    sent = []
    monkeypatch.setattr(instance, "send", lambda files: sent.append(files) or True)
    before = len(_WINDOWS)
    assert gui.main([str(tmp_path / "x.pdf")]) == 0
    assert sent == [[str(tmp_path / "x.pdf")]] and len(_WINDOWS) == before
    config.set("background", False)
    monkeypatch.setattr(instance, "send", lambda files: pytest.fail("not asked when the setting is off"))
    monkeypatch.setattr(app, "exec", lambda: 0)
    assert gui.main([]) == 0 and len(_WINDOWS) == before + 1


def test_quit_and_the_setting(app, tmp_path, monkeypatch):
    from py_pdftools.gui.prefs import SettingsDialog

    win = gui.open_window(pdf(tmp_path / "doc.pdf"))
    dialog = SettingsDialog(win.prefs, win)
    assert not dialog.background.isChecked()
    dialog.background.setChecked(True)
    dialog.accept()
    assert config.get("background") is True and gui._INSTANCE.server is not None
    quits = []
    monkeypatch.setattr(app, "quit", lambda: quits.append(1))
    assert win.quit_program() and quits == [1] and not win.isVisible() and gui._INSTANCE.server is None


def test_the_name_of_the_socket(monkeypatch, tmp_path):
    monkeypatch.delenv("PY_PDFTOOLS_SOCKET", raising=False)
    short = tmp_path / "r"
    short.mkdir()
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run" if not short.exists() else str(short))
    name = instance.server_name()
    assert name == str(short / "py-pdftools.socket") or len(str(short)) > instance.MAX_PATH - 20
    long = tmp_path / ("x" * 120)
    long.mkdir()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(long))
    assert instance.server_name().startswith("py-pdftools-")  # (too long for a socket: a name)
