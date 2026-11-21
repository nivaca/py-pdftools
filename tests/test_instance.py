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


def test_ping_opens_nothing(app, tmp_path):
    assert not instance.running()
    before = len(_WINDOWS)
    assert gui.background(True)
    pinger = subprocess.Popen([sys.executable, "-c", "from py_pdftools.gui import instance; "
                                                     "print(instance.running())"], stdout=subprocess.PIPE, text=True)
    wait(app, lambda: pinger.poll() is not None, seconds=30)
    assert pinger.stdout.read().strip() == "True"
    for _ in range(20):
        app.processEvents()
    assert len(_WINDOWS) == before  # (asked whether it runs: no window opened)


def test_started_in_the_tray(app, tmp_path, monkeypatch):
    """--background: no window, the program waiting in the background; a second --background ends at once."""
    monkeypatch.setattr(app, "exec", lambda: 0)
    before = len(_WINDOWS)
    assert gui.main(["--background"]) == 0
    assert len(_WINDOWS) == before and gui._INSTANCE.server is not None
    monkeypatch.setattr(instance, "running", lambda: True)
    calls, real = [], gui.background
    monkeypatch.setattr(gui, "background", lambda on: calls.append(on))
    assert gui.main(["--background"]) == 0 and calls == []  # (not started twice)
    monkeypatch.setattr(gui, "background", real)


def test_a_window_kept_ready(app, tmp_path, monkeypatch):
    monkeypatch.setattr(gui, "SPARE_DELAY_MS", 0)
    assert gui.take_spare() is None
    assert gui.background(True)
    gui.prepare_spare()
    spare = gui._SPARE[0]
    assert not spare.isVisible()
    win = gui.open_window(pdf(tmp_path / "a.pdf"))
    assert win is spare and win.isVisible() and win.path.name == "a.pdf"
    wait(app, lambda: gui._SPARE is not None, seconds=5)  # (another one, made after)
    assert gui._SPARE is not None and gui._SPARE[0] is not spare
    # a setting changed since it was made: not used (it would show the settings as they were)
    config.set("reload", False)
    stale = gui._SPARE[0]
    other = gui.open_window(pdf(tmp_path / "b.pdf"))
    assert other is not stale and other.path.name == "b.pdf"
    gui.background(False)
    assert gui._SPARE is None


def test_start_with_the_session(app, tmp_path, monkeypatch):
    from py_pdftools.gui import autostart
    from py_pdftools.gui.prefs import SettingsDialog

    # Every system's place in the test's own folder, never the real one (on Windows, the folder Startup)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("HOME", str(tmp_path))
    expected = {"win32": tmp_path / "appdata" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
                / "py-pdftools.cmd",
                "darwin": tmp_path / "Library" / "LaunchAgents" / "io.github.nivaca.py-pdftools.plist"}.get(
        sys.platform, tmp_path / "xdg" / "autostart" / "py-pdftools.desktop")
    assert not autostart.enabled()
    path = autostart.enable(True)
    assert path == expected and "--background" in path.read_text()
    if sys.platform.startswith("linux"):
        text = path.read_text()
        assert "Exec=" in text and text.split("Exec=")[1].split("\n")[0].endswith("--background")
    autostart.enable(False)
    assert not path.exists()
    if sys.platform.startswith("linux"):
        monkeypatch.setenv("APPIMAGE", "/opt/My Apps/py-pdftools.AppImage")
        assert "Exec='/opt/My Apps/py-pdftools.AppImage' --background" in autostart.enable(True).read_text()
        autostart.enable(False)
    win = gui.open_window(pdf(tmp_path / "doc.pdf"))
    dialog = SettingsDialog(win.prefs, win)
    assert not dialog.login.isChecked() and not dialog.background.isChecked()
    dialog.login.setChecked(True)
    assert dialog.background.isChecked()  # (it needs the background: turned on with it)
    dialog.accept()
    assert autostart.enabled() and config.get("background") is True
    dialog = SettingsDialog(win.prefs, win)
    assert dialog.login.isChecked()
    dialog.background.setChecked(False)
    assert not dialog.login.isChecked()
    dialog.accept()
    assert not autostart.enabled()
