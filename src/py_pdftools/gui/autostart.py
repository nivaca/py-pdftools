"""Starting with the session (Settings > General): py-pdftools started when the user logs in, in the tray and
without a window (py-pdftools-gui --background), so that the first document of the day opens at once, as the
others do while it runs in the background (see instance.py). It is the desktop's own way of starting a
program at login: a .desktop file in the autostart folder (Linux and the like, XDG), a value in the key Run
of the user's registry (Windows: without the console that a .cmd of the folder Startup showed for a moment;
one left by an older version is removed), a launch agent (macOS)."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

APP = "py-pdftools"
# (the user's own key: HKEY_CURRENT_USER; the tests use another one)
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _windows() -> bool:
    return os.name == "nt"


def command() -> list[str]:
    """What starts the window: the AppImage that runs now (if it is one), the command py-pdftools-gui, or this
    Python with the module."""
    if os.environ.get("APPIMAGE"):
        return [os.environ["APPIMAGE"]]
    found = shutil.which("py-pdftools-gui")
    if found:
        return [found]
    python = Path(sys.executable)
    if os.name == "nt" and (python.parent / "pythonw.exe").is_file():
        python = python.parent / "pythonw.exe"  # (sin una consola que se quede abierta)
    return [str(python), "-m", "py_pdftools.gui"]


def startup_cmd() -> Path:
    """Where versions before 1.8.14 put it on Windows: a .cmd in the folder Startup of the menu."""
    base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    return base / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / f"{APP}.cmd"


def entry() -> Path:
    """The file that makes the desktop start py-pdftools at login (not on Windows: see RUN_KEY)."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "LaunchAgents" / "io.github.nivaca.py-pdftools.plist"
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "autostart" / f"{APP}.desktop"


def _run_value() -> str | None:
    """What the key Run says to start, for py-pdftools; None if nothing."""
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return str(winreg.QueryValueEx(key, APP)[0])
    except OSError:  # (ni la clave ni el valor: no empieza con la sesión)
        return None


def enabled() -> bool:
    if _windows():
        return _run_value() is not None or startup_cmd().is_file()
    return entry().is_file()


def _contents(args: list[str]) -> str:
    if sys.platform == "darwin":
        from xml.sax.saxutils import escape

        # (una ruta con & o < rompería el XML)
        items = "".join(f"\n    <string>{escape(a)}</string>" for a in args)
        return ('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                '<plist version="1.0">\n<dict>\n  <key>Label</key>\n  <string>io.github.nivaca.py-pdftools</string>\n'
                f"  <key>ProgramArguments</key>\n  <array>{items}\n  </array>\n"
                "  <key>RunAtLoad</key>\n  <true/>\n</dict>\n</plist>\n")
    return ("[Desktop Entry]\nType=Application\nName=py-pdftools\n"
            "Comment=py-pdftools in the background, to open documents at once\n"
            f"Exec={shlex.join(args)}\nIcon=py-pdftools\nTerminal=false\nNoDisplay=true\n"
            "X-GNOME-Autostart-enabled=true\n")


def enable(on: bool) -> Path | str:
    """Start with the session (ON), or not. Returns the file written or removed (on Windows, the value of the
    registry); OSError if it can't be."""
    if _windows():
        import winreg

        startup_cmd().unlink(missing_ok=True)  # (the way of the older versions, which showed a console)
        if on:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                winreg.SetValueEx(key, APP, 0, winreg.REG_SZ, subprocess.list2cmdline(command() + ["--background"]))
        elif _run_value() is not None:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, APP)
        return f"HKEY_CURRENT_USER\\{RUN_KEY}\\{APP}"
    path = entry()
    if on:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_contents(command() + ["--background"]), encoding="utf-8")
    else:
        path.unlink(missing_ok=True)
    return path
