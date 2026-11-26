"""La pantalla despierta durante una presentación (gui/awake.py), con las funciones del sistema sustituidas:
lo que se pide al empezar y al terminar, en Linux, Windows y macOS."""

from __future__ import annotations

from py_pdftools.gui import awake


def test_linux(monkeypatch):
    calls = []
    monkeypatch.setattr(awake.sys, "platform", "linux")
    monkeypatch.setattr(awake, "_screensaver", lambda method, *args: calls.append((method, args)) or 41)
    a = awake.Awake()
    assert a.start() and calls == [("Inhibit", ("py-pdftools", awake.REASON))]
    assert a.start()  # (once only)
    a.stop()
    a.stop()
    assert calls[1:] == [("UnInhibit", (41,))] and not a.on


def test_windows_and_macos(monkeypatch):
    states = []
    monkeypatch.setattr(awake.sys, "platform", "win32")
    monkeypatch.setattr(awake, "_windows_state", lambda on: states.append(on) or True)
    a = awake.Awake()
    assert a.start()
    a.stop()
    assert states == [True, False]

    class Process:
        def __init__(self, args, **kwargs):
            self.args, self.ended = args, False

        def terminate(self):
            self.ended = True

    monkeypatch.setattr(awake.sys, "platform", "darwin")
    monkeypatch.setattr(awake, "_caffeinate", lambda: Process(["caffeinate", "-d", "-i", "-w", "1"]))
    a = awake.Awake()
    assert a.start() and a._caffeinate.args[:3] == ["caffeinate", "-d", "-i"]
    process = a._caffeinate
    a.stop()
    assert process.ended and not a.on


def test_nothing_to_ask(monkeypatch):
    """Without the service (a desktop without it): the presentation goes on, the screen as the system has it."""
    monkeypatch.setattr(awake.sys, "platform", "linux")
    a = awake.Awake()
    assert not a.start() and not a.on
    a.stop()
