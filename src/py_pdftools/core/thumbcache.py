"""Las miniaturas guardadas en el disco (Configuración > Rendimiento, desactivado al principio): al abrir otra
vez un documento escaneado, las miniaturas a la vista aparecen enseguida en lugar de dibujarse de nuevo, lo
que en un escaneo pesado tarda segundos.

Cada miniatura se guarda con el nombre de la huella de su página (ver pageprint.py), su tamaño y el suavizado
con que se dibujó: no depende del archivo ni de su ruta, y una página cambiada tiene otra huella, así que nunca
se muestra una miniatura vieja. El formato es el más rápido de leer, los píxeles RGB tal cual, tras una
cabecera con el ancho y el alto. La carpeta tiene un límite de tamaño; las que llevan más tiempo sin usarse se
borran primero.

Guardar imágenes de las páginas en el disco tiene un riesgo: las de un documento que luego se censura
seguirían ahí, con lo que la censura tapó. Por eso escribir una copia censurada vacía la carpeta entera
(redact.write_redacted), y desactivar el ajuste también."""

from __future__ import annotations

import hashlib
import os
import shutil
import struct
from pathlib import Path

FORMAT = 1  # (part of every name: a new format never reads the old files)
LIMIT = 200 << 20  # bytes the folder may take
HEADER = struct.Struct("<II")  # width, height
PRUNE_EVERY = 50  # (thumbnails saved between two looks at the size of the folder)

_saved = 0


def folder() -> Path:
    """The folder of the thumbnails: py-pdftools/thumbs in the cache folder (LOCALAPPDATA on Windows, else
    XDG_CACHE_HOME or ~/.cache), next to the working copies."""
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        base = Path(os.environ["LOCALAPPDATA"])
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "py-pdftools" / "thumbs"


def _path(fingerprint: bytes, size: tuple[int, int], drawing: tuple) -> Path:
    key = hashlib.blake2b(digest_size=16)
    key.update(repr((FORMAT, size, drawing)).encode())
    key.update(fingerprint)
    name = key.hexdigest()
    return folder() / name[:2] / name


def load(fingerprint: bytes, size: tuple[int, int], drawing: tuple) -> tuple[int, int, bytes] | None:
    """The thumbnail kept of the page whose fingerprint is FINGERPRINT, made for a box of SIZE (width, height)
    and drawn with DRAWING (the antialiasing): (width, height, RGB pixels), or None."""
    path = _path(fingerprint, size, drawing)
    try:
        data = path.read_bytes()
        width, height = HEADER.unpack_from(data)
        if len(data) != HEADER.size + width * height * 3:
            return None
        os.utime(path)  # (just used: the last to go, see prune)
    except (OSError, struct.error):
        return None
    return width, height, data[HEADER.size:]


def save(fingerprint: bytes, size: tuple[int, int], drawing: tuple, width: int, height: int, rgb: bytes) -> None:
    """Keep the thumbnail RGB (WIDTH × HEIGHT, three bytes a pixel, no padding) of the page FINGERPRINT."""
    global _saved
    path = _path(fingerprint, size, drawing)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Primero un archivo aparte, renombrado al final: otra ventana nunca lee una miniatura a medias.
        part = path.with_suffix(f".{os.getpid()}.part")
        part.write_bytes(HEADER.pack(width, height) + rgb)
        os.replace(part, path)
    except OSError:
        return
    _saved += 1
    if _saved % PRUNE_EVERY == 0:
        prune()


def prune(limit: int = LIMIT) -> None:
    """Remove the thumbnails used longest ago, until the folder takes at most LIMIT bytes."""
    files = []
    for path in folder().glob("*/*"):
        try:
            st = path.stat()
        except OSError:
            continue
        files.append((st.st_mtime, st.st_size, path))
    total = sum(size for _, size, _ in files)
    for _, size, path in sorted(files):
        if total <= limit:
            break
        path.unlink(missing_ok=True)
        total -= size


def clear() -> None:
    """Remove every thumbnail kept (a redacted copy was written, or the setting was turned off)."""
    shutil.rmtree(folder(), ignore_errors=True)
