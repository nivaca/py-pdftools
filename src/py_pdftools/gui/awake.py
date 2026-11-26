"""La pantalla despierta mientras dura una presentación: sin tocar el teclado ni el ratón, el sistema la
apagaría (o pondría el protector de pantalla) en medio de una charla. Cada sistema a su modo: en Linux, el
servicio org.freedesktop.ScreenSaver por D-Bus (KDE, GNOME y los demás escritorios lo ofrecen); en Windows,
SetThreadExecutionState; en macOS, caffeinate, que dura lo que el proceso del programa. Calibre hace lo
mismo en su visor (viewer/control_sleep.py), salvo en Linux, donde no hace nada. Si el sistema no lo
permite, la presentación sigue igual."""

from __future__ import annotations

import os
import subprocess
import sys

# (el motivo, que el escritorio puede mostrar: «py-pdftools impide que se suspenda la pantalla»)
REASON = "Presentation"


class Awake:
    """Keeps the screen on from start() to stop(); stop() may be called more than once."""

    def __init__(self):
        self._cookie: int | None = None  # (Linux: what Inhibit gave, for UnInhibit)
        self._windows = False
        self._caffeinate: subprocess.Popen | None = None

    @property
    def on(self) -> bool:
        return self._cookie is not None or self._windows or self._caffeinate is not None

    def start(self) -> bool:
        """The screen kept on; whether the system said yes."""
        if self.on:
            return True
        try:
            if sys.platform == "win32":
                self._windows = _windows_state(on=True)
            elif sys.platform == "darwin":
                self._caffeinate = _caffeinate()
            else:
                self._cookie = _screensaver("Inhibit", "py-pdftools", REASON)
        except (OSError, ValueError, AttributeError):
            return False
        return self.on

    def stop(self) -> None:
        """The screen left to the system again."""
        if self._cookie is not None:
            _screensaver("UnInhibit", self._cookie)
            self._cookie = None
        if self._windows:
            _windows_state(on=False)
            self._windows = False
        if self._caffeinate is not None:
            self._caffeinate.terminate()
            self._caffeinate = None


def _caffeinate() -> subprocess.Popen:
    """macOS's caffeinate, keeping the display (-d) and the system (-i) awake while this process lives (-w)."""
    return subprocess.Popen(["caffeinate", "-d", "-i", "-w", str(os.getpid())], stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)


def _windows_state(on: bool) -> bool:
    import ctypes

    es_continuous, es_system, es_display = 0x80000000, 0x00000001, 0x00000002
    flags = es_continuous | (es_system | es_display if on else 0)
    return bool(ctypes.windll.kernel32.SetThreadExecutionState(flags))


def _screensaver(method: str, *args):
    """METHOD of org.freedesktop.ScreenSaver, by D-Bus, with ARGS: its answer (Inhibit's cookie), or None."""
    from PySide6.QtDBus import QDBusConnection, QDBusInterface

    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        return None
    iface = QDBusInterface("org.freedesktop.ScreenSaver", "/org/freedesktop/ScreenSaver",
                           "org.freedesktop.ScreenSaver", bus)
    if not iface.isValid():
        return None
    reply = iface.call(method, *args)
    values = reply.arguments() if reply.errorMessage() == "" else []
    return int(values[0]) if method == "Inhibit" and values else None
