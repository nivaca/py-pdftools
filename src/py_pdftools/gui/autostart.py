"""Starting with the session (Settings > General): py-pdftools started when the user logs in, in the tray and
without a window (py-pdftools-gui --background), so that the first document of the day opens at once, as the
others do while it runs in the background (see instance.py). It is the desktop's own way of starting a
program at login: a .desktop file in the autostart folder (Linux and the like, XDG), a file in the folder
Startup of the menu (Windows), a launch agent (macOS)."""

from __future__ import annotations

import os
import shlex
import shutil
import sys
from pathlib import Path

APP = "py-pdftools"


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


def entry() -> Path:
    """The file that makes the desktop start py-pdftools at login."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "LaunchAgents" / "io.github.nivaca.py-pdftools.plist"
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return base / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / f"{APP}.cmd"
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "autostart" / f"{APP}.desktop"


def enabled() -> bool:
    return entry().is_file()


def _contents(args: list[str]) -> str:
    if sys.platform == "darwin":
        items = "".join(f"\n    <string>{a}</string>" for a in args)
        return ('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                '<plist version="1.0">\n<dict>\n  <key>Label</key>\n  <string>io.github.nivaca.py-pdftools</string>\n'
                f"  <key>ProgramArguments</key>\n  <array>{items}\n  </array>\n"
                "  <key>RunAtLoad</key>\n  <true/>\n</dict>\n</plist>\n")
    if os.name == "nt":
        quoted = " ".join(f'"{a}"' for a in args)
        return f'@echo off\r\nstart "" {quoted}\r\n'
    return ("[Desktop Entry]\nType=Application\nName=py-pdftools\n"
            "Comment=py-pdftools in the background, to open documents at once\n"
            f"Exec={shlex.join(args)}\nIcon=py-pdftools\nTerminal=false\nNoDisplay=true\n"
            "X-GNOME-Autostart-enabled=true\n")


def enable(on: bool) -> Path:
    """Start with the session (ON), or not. Returns the file written or removed; OSError if it can't be."""
    path = entry()
    if on:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_contents(command() + ["--background"]), encoding="utf-8")
    else:
        path.unlink(missing_ok=True)
    return path
