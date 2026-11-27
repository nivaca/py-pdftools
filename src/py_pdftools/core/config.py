"""The configuration file, shared by the command line and the window.

It is a small TOML file, ``config.toml``, in the user's configuration folder:

* Linux: ``$XDG_CONFIG_HOME/py-pdftools`` (usually ``~/.config/py-pdftools``);
* macOS: ``~/Library/Application Support/py-pdftools``;
* Windows: ``%APPDATA%\\py-pdftools``.

``$PY_PDFTOOLS_CONFIG`` names another folder. It holds the language of
the interface, and the settings of the window (see settings.py):

    [parameters]
    interface = "es"

and, after them, what the window keeps of itself between sessions (its size, the arrangement of each
mode, the documents opened last...), in the tables [window] and [impose] (see gui/state.py): one file
for everything, no longer a second one of Qt's.
"""

from __future__ import annotations

import os
import re
import sys
import tomllib
from pathlib import Path

ENV = "PY_PDFTOOLS_CONFIG"
SETTINGS = {"interface": "en", "pdfconform": "", "show_document": False,  # name: default (show_document: Impose)
            "background": False,  # (background: keep running after the last window, see gui/instance.py)
            # (Settings > Performance: see gui/performance.py)
            "memory": "normal", "transparency": True, "text_antialias": True, "graphics_antialias": True,
            "smooth": True,  # (smooth: zooming and the wheel animated, see gui/scrolling.py)
            "thumb_cache": False,  # (thumb_cache: the thumbnails kept on disk too, see core/thumbcache.py)
            "reopen": False,  # (reopen: the documents of the last session, at the start: see gui/__init__.py)
            "tabs": False, "lone_tab": False,  # (lone_tab: the tabbar with only one: see gui/tabs.py)
            "warn_many": True,  # (warn_many: ask before quitting with several documents open, gui/tabs.py)
            "reload": True,  # (reload: a document changed by another program, opened again: see gui/watching.py)
            "gpu": False,  # (gpu: the pages drawn with the graphics card, by OpenGL: see gui/canvas.py)
            # (backend: the engine that draws the pages, "mupdf", "pdfium" or "poppler"; ask_backend: asked when a
            # document is opened: see core/backends.py)
            "backend": "mupdf", "ask_backend": False,
            # (Settings > Appearance and Documents: see gui/appearance.py)
            "theme": "system", "icons": "system", "scale": 100, "hints": False, "tooltips": False, "sharpness": "sharper",
            "opening": "document", "places": True, "ask_links": True, "recent": 10, "dialogs": "last",
            "annot_panel": False,  # (annot_panel: the panel Annotations shown on entering Annotate: gui/window.py)
            # (annot_storage: where the annotations of a document without a file of them apart are saved: "pdf" or
            # "file", see gui/storing.py)
            "annot_storage": "pdf",
            "hide_notes": True,  # (hide_notes: those files hidden, .NAME.pdf.pdfnotes: see annotate/sidecar.py)
            "speech_rate": 0.0}  # (speech_rate: of reading aloud, from -1 to 1: see gui/readaloud.py)


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
    data["parameters"] = params
    return write(data)


# The tables written first, in this order; the others (what the window keeps: see gui/state.py) after them.
FIRST = ("parameters",)


def _key(name: str) -> str:
    return name if re.fullmatch(r"[A-Za-z0-9_-]+", name) else _string(name)


def _string(text: str) -> str:
    out = str(text).replace("\\", "\\\\").replace('"', '\\"')
    # (los caracteres de control no pueden ir tal cual en una cadena de TOML)
    out = re.sub(r"[\x00-\x1f\x7f]", lambda m: f"\\u{ord(m.group()):04x}", out)
    return f'"{out}"'


def _value(value) -> str:
    # bool va antes que int: en Python, True también es un int.
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_value(v) for v in value) + "]"
    return _string(value)


def _table(lines: list, name: str, values: dict) -> None:
    plain = {k: v for k, v in values.items() if not isinstance(v, dict)}
    lines += ["", f"[{name}]"] + [f"{_key(k)} = {_value(v)}" for k, v in plain.items()]
    for key, sub in values.items():
        if isinstance(sub, dict):
            _table(lines, f"{name}.{_key(key)}", sub)


def write(data: dict) -> Path:
    """Write the whole configuration DATA (its tables: [parameters] first). Returns the file's path."""
    # Importación diferida: config se carga muy pronto, y el módulo de idiomas solo hace falta al escribir.
    from .interface import tr

    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# " + tr("The settings of py-pdftools. Delete this file to use the usual values.")]
    names = [n for n in FIRST if n in data] + [n for n in data if n not in FIRST]
    for name in names:
        if isinstance(data[name], dict):
            _table(lines, _key(name), data[name])
    # Write a temporary file and rename it, so that a crash never leaves half a config.toml behind.
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def reset() -> Path | None:
    """All the settings back to their usual values: config.toml moved aside, as a copy dated now
    (config-YYYY-MM-DD-HHMMSS.toml, beside it). Returns that copy; None if there was no file. The other files
    of the folder (stamps, signatures, digital IDs, recipes, profiles, recovery copies) are not touched."""
    import time

    path = config_path()
    if not path.is_file():
        return None
    backup = path.with_name(time.strftime("config-%Y-%m-%d-%H%M%S.toml"))
    n = 1
    while backup.exists():  # (dos en el mismo segundo: la segunda lleva un número)
        n += 1
        backup = path.with_name(time.strftime(f"config-%Y-%m-%d-%H%M%S-{n}.toml"))
    # Mover es copiar y borrar a la vez: nunca queda la configuración borrada sin su copia.
    os.replace(path, backup)
    return backup


def write_table(name: str, values: dict) -> Path:
    """Replace the table NAME with VALUES (none: removed), keeping the others."""
    try:
        data = read()
    except ConfigError:
        data = {}
    if values:
        data[name] = values
    else:
        data.pop(name, None)
    return write(data)
