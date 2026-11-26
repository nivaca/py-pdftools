from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import sys

import pytest


def _virtual_display() -> bool:
    """Start an X server of the tests' own (Xvfb), if it is installed: the windows are then drawn by a
    real X server, as on a desktop, without showing on the user's screen. Stopped when the tests end.
    False if it couldn't be started."""
    if not sys.platform.startswith("linux") or not shutil.which("Xvfb"):
        return False
    try:
        # -displayfd: Xvfb picks a free display, and writes its number on that file descriptor.
        server = subprocess.Popen(["Xvfb", "-displayfd", "1", "-screen", "0", "1920x1080x24", "-nolisten", "tcp"],
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        number = server.stdout.readline().decode().strip()
    except OSError:
        return False
    if not number.isdigit():
        server.kill()
        return False
    atexit.register(server.terminate)
    os.environ["DISPLAY"] = f":{number}"
    os.environ.pop("WAYLAND_DISPLAY", None)  # (Qt must take the X server, not the desktop's Wayland)
    os.environ["QT_QPA_PLATFORM"] = "xcb"
    return True


# Where the tests draw their windows, as PY_PDFTOOLS_TEST_DISPLAY says: 'xvfb' (the usual: an X server of their
# own, if Xvfb is installed, else offscreen), 'offscreen' (in memory), or 'screen' (the desktop's own display,
# to watch them). Not as QT_QPA_PLATFORM says: a desktop session sets it (to wayland), and the windows of the
# tests would show on the user's screen.
_DISPLAY = os.environ.get("PY_PDFTOOLS_TEST_DISPLAY", "xvfb")
if _DISPLAY != "screen" and not (_DISPLAY == "xvfb" and _virtual_display()):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"


@pytest.fixture(autouse=True)
def own_config(tmp_path, monkeypatch):
    """A configuration folder of its own, so the tests don't read or change the user's."""
    monkeypatch.setenv("PY_PDFTOOLS_CONFIG", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    from py_pdftools.core import interface

    interface.use(None)
    yield
    from py_pdftools.gui import appearance

    appearance.apply_tooltips(True)  # (a test that applied the settings leaves the tooltips as Qt has them)


@pytest.fixture(autouse=True)
def pages_here(monkeypatch):
    """Pages rendered, and redacted copies saved, in the tests' own process, at once (a test may turn
    this off)."""
    from py_pdftools.gui import renderer
    from py_pdftools.gui.redact import background

    monkeypatch.setattr(renderer, "ENABLED", False)
    monkeypatch.setattr(background, "ENABLED", False)


@pytest.fixture(autouse=True)
def screen_left_alone(monkeypatch):
    """A presentation in a test doesn't keep the screen of whoever runs the tests awake (see gui/awake.py: its
    own test calls the system's functions through stand-ins)."""
    from py_pdftools.gui import awake

    monkeypatch.setattr(awake, "_screensaver", lambda method, *args: None)
    monkeypatch.setattr(awake, "_windows_state", lambda on: False)
    monkeypatch.setattr(awake, "_caffeinate", _no_caffeinate)


def _no_caffeinate():
    raise OSError("not in the tests")


@pytest.fixture(autouse=True)
def annotating_first(monkeypatch):
    """The window starts in the mode Annotate (its tests come from py-annotate's), not in Read, as it does
    the first time a user opens it (a test may set the mode itself)."""
    from py_pdftools.gui import window

    monkeypatch.setattr(window, "DEFAULT_MODE", "annotate")


@pytest.fixture(autouse=True)
def own_window_settings():
    """What the window keeps of itself (its mode, the arrangement of each mode, the toolbars...: see
    gui/state.py) goes in each test's own configuration folder (see own_config); what was read of another
    is forgotten."""
    from py_pdftools.gui import state

    state._CACHE.clear()
    yield


@pytest.fixture(autouse=True)
def own_cache(tmp_path_factory, monkeypatch):
    """The cache folder (where the working copies go: see gui/working.work_root) in a folder of the
    tests, never the user's own."""
    cache = tmp_path_factory.mktemp("cache")
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache))
    monkeypatch.setenv("LOCALAPPDATA", str(cache))
