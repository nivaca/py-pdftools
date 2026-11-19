"""The configuration file, shared by the command line and the window.

It is a small TOML file, ``config.toml``, in the user's configuration folder:

* Linux: ``$XDG_CONFIG_HOME/py-pdftools`` (usually ``~/.config/py-pdftools``);
* macOS: ``~/Library/Application Support/py-pdftools``;
* Windows: ``%APPDATA%\\py-pdftools``.

``$PY_PDFTOOLS_CONFIG`` names another folder. It holds the language of
the interface, and the settings of the window (see settings.py):

    [parameters]
    interface = "es"
"""

from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path

ENV = "PY_PDFTOOLS_CONFIG"
SETTINGS = {"interface": "en", "pdfconform": ""}  # name: default


class ConfigError(Exception):
    """A configuration file that cannot be read."""


def config_dir() -> Path:
    if os.environ.get(ENV):
        return Path(os.environ[ENV])
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "py-pdftools"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "py-pdftools"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "py-pdftools"


def config_path() -> Path:
    return config_dir() / "config.toml"


def read() -> dict[str, dict]:
    """The configuration ({} if there is no file; raises ConfigError if it is wrong)."""
    path = config_path()
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as e:
        raise ConfigError(f"{path}: {e}") from None
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: {e}") from None
    return data if isinstance(data, dict) else {}


def get(name: str):
    try:
        value = read().get("parameters", {}).get(name)
    except ConfigError:
        value = None
    return SETTINGS[name] if value is None else value


def set(name: str, value) -> Path:
    """Change one setting, keeping the others (None removes it). Returns the file's path."""
    return set_many({name: value})


def set_many(values: dict) -> Path:
    """Change several settings at once, keeping the others (a value None
    removes its setting). Returns the file's path."""
    from .interface import tr

    try:
        data = read()
    except ConfigError:
        data = {}
    params = dict(data.get("parameters", {}))
    for name, value in values.items():
        if value is None:
            params.pop(name, None)
        else:
            params[name] = value
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# " + tr("The settings of py-pdftools. Delete this file to use the usual values."), "",
             "[parameters]"]
    for key, val in params.items():
        if isinstance(val, bool):
            lines.append(f"{key} = {'true' if val else 'false'}")
        elif isinstance(val, (int, float)):
            lines.append(f"{key} = {val}")
        else:
            lines.append(f'{key} = "' + str(val).replace("\\", "\\\\").replace('"', '\\"') + '"')
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path
