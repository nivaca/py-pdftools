"""Reemplazar un archivo por otro ya escrito (os.replace), también en Windows, donde falla con
PermissionError mientras otro proceso tiene abierto el archivo de destino: el antivirus, el indexador o los
procesos que dibujan las páginas, que lo leen un momento después de abrir el documento. Se reintenta unos
instantes antes de dar el error; en Linux y macOS, os.replace no falla por eso."""

from __future__ import annotations

import os
import sys
import time

TRIES = 20  # (unos dos segundos en total)
PAUSE = 0.1  # seconds between tries


def replace(source, target) -> None:
    """os.replace(SOURCE, TARGET), tried again for a moment on Windows if TARGET is held by another process."""
    for attempt in range(TRIES):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            # Solo en Windows tiene sentido esperar: en los demás sistemas es un permiso de verdad
            if sys.platform != "win32" or attempt == TRIES - 1:
                raise
            time.sleep(PAUSE)
