"""Lo que la ventana guarda de sí misma entre sesiones (su tamaño, la disposición de cada modo, las barras,
los documentos abiertos la última vez, las búsquedas...), en el mismo archivo de configuración que los
ajustes (config.toml, ver core/config.py), en una tabla propia: [window] la ventana, [impose] el espacio de
trabajo de Imponer.

Antes lo guardaba QSettings, en un segundo archivo (py-pdftools.conf en Linux; el registro en Windows, un
plist en macOS). State tiene lo que el programa usaba de QSettings (value, setValue, remove, contains, sync)
y devuelve los valores como los devolvía QSettings al leerlos de su archivo: los booleanos como "true" o
"false" (salvo con type=bool), los estados de Qt como QByteArray. Lo que quedaba en QSettings se trae la
primera vez, y QSettings se vacía (ver migrate).
"""

from __future__ import annotations

import base64
import os

from PySide6.QtCore import QByteArray

from ..core import config

BYTES = "@ByteArray:"  # (a state of Qt, saveState or saveGeometry: in base64 after this)
# The tables, and the name of each in QSettings (application "py-pdftools", organization "py-pdftools")
TABLES = {"window": "py-pdftools", "impose": "py-pdftools-impose"}

# Lo leído del archivo, por ruta: (mtime_ns, size) y las tablas; se vuelve a leer si otro (la línea de
# órdenes, otro proceso) lo cambió.
_CACHE: dict = {}


def _tables() -> dict:
    path = config.config_path()
    try:
        st = path.stat()
        stamp = (st.st_mtime_ns, st.st_size)
    except OSError:
        stamp = None
    cached = _CACHE.get(path)
    if cached is not None and cached[0] == stamp:
        return cached[1]
    try:
        data = config.read()
    except config.ConfigError:  # (un archivo dañado: la ventana empieza como la primera vez)
        data = {}
    tables = {name: dict(data.get(name, {})) for name in TABLES}
    _CACHE.clear()  # (solo la configuración en uso: los tests cambian de carpeta a cada prueba)
    _CACHE[path] = (stamp, tables)
    # (solo la configuración del usuario: con PY_PDFTOOLS_CONFIG, la de los tests u otra aparte, lo de QSettings
    # es del usuario, y no se toca)
    if not os.environ.get(config.ENV):
        migrate(tables)
    return tables


def _stored(value):
    """VALUE as it goes in the file."""
    if isinstance(value, (QByteArray, bytes, bytearray)):
        return BYTES + base64.b64encode(bytes(value)).decode("ascii")
    if isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_stored(v) for v in value]
    return str(value)


def _given(value):
    """VALUE as QSettings gave it back from its file."""
    if isinstance(value, str) and value.startswith(BYTES):
        try:
            return QByteArray(base64.b64decode(value[len(BYTES):]))
        except ValueError:
            return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return [_given(v) for v in value]
    return value


def _as(kind, value):
    if kind is bool:
        return value in (True, "true", "1", 1) if not isinstance(value, str) else value.lower() in ("true", "1")
    if kind in (int, float):
        try:
            return kind(value)
        except (TypeError, ValueError):
            return kind()
    return kind(value) if kind is not None else value


class State:
    """What the window (TABLE 'window') or Impose ('impose') keeps of itself: as a QSettings."""

    def __init__(self, table: str = "window"):
        if table not in TABLES:
            raise ValueError(table)
        self.table = table

    def value(self, key: str, default=None, type=None):  # noqa: A002 (el nombre de QSettings)
        values = _tables()[self.table]
        if key not in values:
            return default if type is None or default is None else _as(type, default)
        given = _given(values[key])
        return given if type is None else _as(type, given)

    def contains(self, key: str) -> bool:
        return key in _tables()[self.table]

    def setValue(self, key: str, value) -> None:  # noqa: N802 (el nombre de QSettings)
        if value is None:
            self.remove(key)
            return
        stored = _stored(value)
        tables = _tables()
        if tables[self.table].get(key) == stored:
            return  # (nada cambió: el archivo no se escribe otra vez)
        tables[self.table][key] = stored
        self._write(tables)

    def remove(self, key: str) -> None:
        tables = _tables()
        if tables[self.table].pop(key, None) is not None:
            self._write(tables)

    def clear(self) -> None:
        tables = _tables()
        tables[self.table] = {}
        self._write(tables)

    def sync(self) -> None:
        """(Written already, at each change: kept for the code written for QSettings.)"""

    def _write(self, tables: dict) -> None:
        try:
            path = config.write_table(self.table, tables[self.table])
            st = path.stat()
            _CACHE[path] = ((st.st_mtime_ns, st.st_size), tables)
        except OSError:  # (una carpeta sin permiso de escritura: queda en memoria, para esta sesión)
            pass


def migrate(tables: dict) -> bool:
    """Bring into TABLES (and the file) what QSettings kept, where versions before 1.8.15 put it, and empty
    QSettings (its file removed). Only when the table has nothing yet. Whether anything was brought."""
    from pathlib import Path

    from PySide6.QtCore import QSettings

    brought = False
    for table, application in TABLES.items():
        if tables[table]:
            continue
        old = QSettings("py-pdftools", application)
        keys = old.allKeys()
        if not keys:
            continue
        tables[table] = {k: _stored(old.value(k)) for k in keys if old.value(k) is not None}
        try:
            config.write_table(table, tables[table])
        except OSError:
            continue
        brought = True
        name = old.fileName()
        old.clear()
        old.sync()
        # (en Linux, un archivo .conf; en macOS, un .plist; en Windows, claves del registro, ya vacías)
        if name and Path(name).is_file():
            Path(name).unlink(missing_ok=True)
    if brought:
        path = config.config_path()
        st = path.stat()
        _CACHE[path] = ((st.st_mtime_ns, st.st_size), tables)
    return brought
