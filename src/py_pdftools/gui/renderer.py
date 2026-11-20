"""Pages rendered in other processes, so that the window answers while they
are rendered (see rendering.py). There are two lanes, each with a process
of its own: 'view' for the page shown and the pages next to it, 'thumbs' for
the thumbnails; so a page asked for never waits behind the thumbnails.

Each lane renders one page at a time and keeps its own queue, so a request
can go before the others (the page just asked for) and those no longer
wanted can be dropped (the pages next to one left behind). If the processes
can't be started, or die, available() is False and the window renders in
its own process, as before.
"""

from __future__ import annotations

import multiprocessing
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage

from ..core import rendering

# Global switch read by available(); tests set it to False to render synchronously in the window.
ENABLED = True  # (the tests turn it off: they want the page drawn at once)

# path, password, stamp (the file's time and size), and whether to render the pages without the
# annotations the window draws itself
Source = tuple[str, str, tuple, bool]


class Lane:
    # El pool se crea la primera vez que hace falta: así no se lanza ningún proceso si nunca se usa.
    def __init__(self):
        self.pool: ProcessPoolExecutor | None = None
        self.busy: tuple | None = None  # the key being rendered
        self.waiting: list[tuple] = []  # (key, arguments), in order
        # Varias peticiones de la misma imagen esperan una sola renderización y reciben todas el resultado.
        self.callbacks: dict[tuple, list[Callable]] = {}


class Renderer(QObject):
    # Futures finish in a thread of the executor; the signal moves the result to the GUI thread,
    # where QImage and the callbacks are safe to use.
    _arrived = Signal(object)  # (lane, key, future): from the executor's thread to the window's

    def __init__(self):
        super().__init__()
        self.lanes: dict[str, Lane] = {}
        self.broken = False
        self._arrived.connect(self._deliver)

    def available(self) -> bool:
        return ENABLED and not self.broken

    def request(self, lane: str, source: Source, number: int, scale: float, callback: Callable,
                first: bool = False) -> None:
        """Render page NUMBER of SOURCE at SCALE, and give CALLBACK the QImage (or
        None if it couldn't be rendered there). FIRST: before those waiting."""
        ln = self.lanes.setdefault(lane, Lane())
        # La clave no lleva la contraseña: ruta, sello del archivo, página, escala y si van sin anotaciones.
        # Si el archivo cambia en disco, el sello cambia y la clave también.
        key = (source[0], source[2], number, scale, source[3])
        ln.callbacks.setdefault(key, []).append(callback)
        # Already being rendered: the callback is added and will get the same image.
        if key == ln.busy:
            return
        # Una petición que ya esperaba se saca de la cola, para volver a ponerla delante o al final.
        entry = next((e for e in ln.waiting if e[0] == key), None)
        if entry is not None:
            ln.waiting.remove(entry)
        else:
            entry = (key, (source[0], source[1], source[2], number, scale, source[3]))
        if first:
            ln.waiting.insert(0, entry)
        else:
            ln.waiting.append(entry)
        self._next(lane)

    def drop(self, lane: str, keep: Callable[[str, int], bool] = lambda path, number: False) -> None:
        """Forget the requests waiting in LANE, but those whose (path, page) KEEP wants."""
        ln = self.lanes.get(lane)
        if ln is None:
            return
        # Only waiting requests are dropped; the one being rendered finishes and is delivered anyway.
        for entry in [e for e in ln.waiting if not keep(e[0][0], e[0][2])]:
            ln.waiting.remove(entry)
            ln.callbacks.pop(entry[0], None)

    def busy(self, lane: str) -> bool:
        ln = self.lanes.get(lane)
        return ln is not None and (ln.busy is not None or bool(ln.waiting))

    def _next(self, lane: str) -> None:
        ln = self.lanes[lane]
        # Una sola página a la vez por carril: la cola puede reordenarse hasta el último momento.
        if ln.busy is not None or not ln.waiting:
            return
        key, args = ln.waiting.pop(0)
        try:
            if ln.pool is None:
                # Spawn, not fork: a forked child would inherit Qt's state and threads, which is not safe.
                # One worker per lane, so 'view' never waits behind 'thumbs'.
                ln.pool = ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn"))
            # Una vez enviada al proceso, la petición ya no se puede cancelar: por eso drop() solo toca la cola.
            future = ln.pool.submit(rendering.render, *args)
        except Exception:  # (no process could be started: render in the window's)
            self._fail()
            return
        ln.busy = key
        future.add_done_callback(lambda f: self._arrived.emit((lane, key, f)))

    def _deliver(self, item: tuple) -> None:
        lane, key, future = item
        ln = self.lanes[lane]
        ln.busy = None
        image = None
        try:
            width, height, stride, data = future.result()
            # copy(): QImage does not own the bytes received from the other process.
            image = QImage(data, width, height, stride, QImage.Format.Format_RGB888).copy()
        except Exception as e:
            from concurrent.futures.process import BrokenProcessPool

            # Si el proceso murió, se deja de usar para siempre; otros errores (una página dañada) solo
            # devuelven None a quien la pidió, que la renderiza en la ventana.
            if isinstance(e, BrokenProcessPool):
                self._fail()
                return
        for callback in ln.callbacks.pop(key, []):
            _call(callback, image)
        self._next(lane)

    def _fail(self) -> None:
        """The processes can't render: tell all who wait (they render themselves)."""
        self.broken = True
        # Se vacían los carriles antes de llamar a nadie: una devolución de llamada podría pedir otra
        # página y no debe encontrar el carril viejo.
        lanes, self.lanes = self.lanes, {}
        for ln in lanes.values():
            if ln.pool is not None:
                # wait=False: closing must not block the window on a page still being rendered.
                ln.pool.shutdown(wait=False, cancel_futures=True)
            for callbacks in ln.callbacks.values():
                for callback in callbacks:
                    _call(callback, None)

    def shutdown(self) -> None:
        for ln in self.lanes.values():
            if ln.pool is not None:
                ln.pool.shutdown(wait=False, cancel_futures=True)
        self.lanes = {}


def _call(callback: Callable, image: QImage | None) -> None:
    try:
        callback(image)
    except RuntimeError:  # (its window was closed meanwhile)
        pass


_RENDERER: Renderer | None = None


def renderer() -> Renderer:
    """The one renderer of the application, for all its windows."""
    global _RENDERER
    # Un solo renderizador para todas las ventanas: los procesos se comparten y se cierran al salir.
    if _RENDERER is None:
        _RENDERER = Renderer()
        from PySide6.QtCore import QCoreApplication

        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(_RENDERER.shutdown)
    return _RENDERER

