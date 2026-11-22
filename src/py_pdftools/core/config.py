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
SETTINGS = {"interface": "en", "pdfconform": "", "show_document": False,  # name: default (show_document: Impose)
            "background": False,  # (background: keep running after the last window, see gui/instance.py)
            # (Settings > Performance: see gui/performance.py)
            "memory": "normal", "transparency": True, "text_antialias": True, "graphics_antialias": True,
            "smooth": True,  # (smooth: zooming and the wheel animated, see gui/scrolling.py)
            "reopen": False,  # (reopen: the documents of the last session, at the start: see gui/__init__.py)
            "tabs": False, "lone_tab": False,  # (lone_tab: the bar of the tabs with only one: see gui/tabs.py)
            "reload": True,  # (reload: a document changed by another program, opened again: see gui/watching.py)
            "gpu": False,  # (gpu: the pages drawn with the graphics card, by OpenGL: see gui/canvas.py)
            # (Settings > Appearance and Documents: see gui/appearance.py)
            "theme": "system", "scale": 100, "hints": False, "tooltips": False, "sharpness": "sharper",
            "opening": "document", "places": True, "ask_links": True, "recent": 10, "dialogs": "last"}


class ConfigError(Exception):
    """A configuration file that cannot be read."""


def config_dir() -> Path:
    # La variable de entorno manda: así los tests, o quien quiera una configuración aparte, no tocan la del usuario.
    if os.environ.get(ENV):
        return Path(os.environ[ENV])
    if sys.platform == "win32":
        # Without APPDATA (a service, a reduced environment) the usual Roaming folder is used.
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
    # Un archivo que existe pero no es TOML válido es un error, no una configuración vacía: decide quien llama.
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: {e}") from None
    return data if isinstance(data, dict) else {}


def get(name: str):
    # Un archivo dañado no debe impedir que el programa arranque: se usa el valor por omisión.
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
    # Importación diferida: config se carga muy pronto, y el módulo de idiomas solo hace falta al escribir.
    from .interface import tr

    # If the present file is damaged, it is written again from scratch with the new values.
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
    # TODO: solo se escribe la tabla [parameters]: cualquier otra tabla del archivo se pierde, y una lista o
    # tabla anidada saldría como cadena. Convendría un escritor de TOML completo (tomli-w, por ejemplo).
    lines = ["# " + tr("The settings of py-pdftools. Delete this file to use the usual values."), "",
             "[parameters]"]
    # A small TOML writer of our own: only booleans, numbers and strings are kept in [parameters].
    for key, val in params.items():
        # bool va antes que int: en Python, True también es un int.
        if isinstance(val, bool):
            lines.append(f"{key} = {'true' if val else 'false'}")
        elif isinstance(val, (int, float)):
            lines.append(f"{key} = {val}")
        else:
            lines.append(f'{key} = "' + str(val).replace("\\", "\\\\").replace('"', '\\"') + '"')
    # Write a temporary file and rename it, so that a crash never leaves half a config.toml behind.
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path
