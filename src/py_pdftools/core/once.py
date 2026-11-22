"""Valores que se buscan una sola vez y pueden buscarse por adelantado, en otro hilo.

Encontrar Tesseract y sus idiomas, o Ghostscript, obliga a ejecutarlos: unos milisegundos cada uno, que la
ventana pagaría al arrancar. ``once`` guarda el resultado como ``functools.cache``, pero con un candado:
``ahead`` lo pide en un hilo aparte mientras la ventana se construye, y quien lo necesite antes de que llegue
espera ese resultado en lugar de ejecutar el programa otra vez.
"""

from __future__ import annotations

import functools
import threading
from collections.abc import Callable


def once(f: Callable):
    """F (sin argumentos) calculada una sola vez, aunque la pidan dos hilos a la vez."""
    lock = threading.Lock()
    cached = functools.cache(f)

    @functools.wraps(f)
    def wrapper():
        with lock:
            return cached()

    wrapper.cache_clear = cached.cache_clear
    return wrapper


def ahead(*functions: Callable) -> None:
    """Las FUNCTIONS (hechas con once) calculadas ya, en un hilo que no retiene el programa al salir."""
    def run():
        for f in functions:
            # Un error se verá cuando se pida de veras, en el hilo de quien la pida.
            try:
                f()
            except Exception:  # noqa: BLE001
                f.cache_clear()

    threading.Thread(target=run, name="look-ahead", daemon=True).start()
