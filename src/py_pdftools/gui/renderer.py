"""Pages rendered in other processes, so that the window answers while they
are rendered (see rendering.py). There are two lanes: 'view' for the pages
shown and those next to them, 'thumbs' for the thumbnails; so a page asked
for never waits behind the thumbnails. Each lane has a few processes (its
slots), each rendering one page at a time; the lane keeps one queue, so a
request can go before the others (the page just asked for) and those no
longer wanted can be dropped (the pages next to one left behind).

A page that takes longer than LIMIT seconds, or that makes its process die,
is not tried again: its process is killed (or found dead) and replaced, and
those who asked for the page get a Skipped instead of a picture, which they
show as such. (The window must not render such a page itself: it would hang
or die with it.) If no process can be started at all, available() is False
and the window renders in its own process, as before.
"""

from __future__ import annotations

import multiprocessing
import os
import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter

from ..core import rendering
from . import performance, reading
from ..core.interface import tr

# Global switch read by available(); tests set it to False to render synchronously in the window.
ENABLED = True  # (the tests turn it off: they want the page drawn at once)
LIMIT = 20.0  # seconds a page may take to render, before its process is killed and the page skipped
# processes of each lane: two for the pages in view (the one in the middle and the next); for the
# thumbnails, more on a machine with more cores (each process holds its own copy of the documents)
WORKERS = {"view": 2, "thumbs": max(1, min(3, (os.cpu_count() or 2) // 4))}

# path, password, stamp (the file's time and size), and whether to render the pages without the
# annotations the window draws itself
Source = tuple[str, str, tuple, bool]


class Skipped:
    """What a request gets instead of a picture when its page was skipped: it took too long, or its
    process died (REASON says which, for the user)."""

    def __init__(self, reason: str):
        self.reason = reason

    def __repr__(self):
        return f"Skipped({self.reason!r})"


class Slot:
    """One process of a lane, and what it is doing."""

    def __init__(self):
        self.pool: ProcessPoolExecutor | None = None
        self.ready = False  # (the process has started: see rendering.ready)
        self.busy: tuple | None = None  # the key being rendered
        self.started = 0.0  # (when it began: see LIMIT)
        self.killed = False  # (by the watchdog: its page took too long)


class Lane:
    # Los procesos se crean la primera vez que hacen falta: así no se lanza ninguno si nunca se usa.
    def __init__(self, workers: int):
        self.slots = [Slot() for _ in range(workers)]
        self.waiting: list[tuple] = []  # (key, arguments), in order
        # Varias peticiones de la misma imagen esperan una sola renderización y reciben todas el resultado.
        self.callbacks: dict[tuple, list[Callable]] = {}

    def rendering(self, key: tuple) -> bool:
        return any(s.busy == key for s in self.slots)


class Renderer(QObject):
    # Futures finish in a thread of the executor; the signal moves the result to the GUI thread,
    # where QImage and the callbacks are safe to use.
    _arrived = Signal(object)  # (lane, slot, key, future): from the executor's thread to the window's

    def __init__(self):
        super().__init__()
        self.lanes: dict[str, Lane] = {}
        self.broken = False
        # pages skipped, (path, stamp, page) -> why: never tried again while the file is the same
        self.skipped: dict[tuple, str] = {}
        self._arrived.connect(self._deliver)
        # El vigilante mira cada medio segundo si algún proceso lleva demasiado tiempo con una página.
        self.watchdog = QTimer(self, interval=500)
        self.watchdog.timeout.connect(self._watch)

    def available(self) -> bool:
        return ENABLED and not self.broken

    def request(self, lane: str, source: Source, number: int, scale: float, callback: Callable,
                first: bool = False, clip: tuple | None = None) -> None:
        """Render page NUMBER of SOURCE at SCALE (only CLIP of it, if given), and give CALLBACK the
        QImage (None if it couldn't be rendered there; a Skipped if the page is skipped).
        FIRST: before those waiting."""
        ln = self.lanes.get(lane)
        if ln is None:
            ln = self.lanes[lane] = Lane(WORKERS.get(lane, 1))
        why = self.skipped.get((source[0], source[2], number))
        if why is not None:
            _call(callback, Skipped(why))
            return
        # La clave no lleva la contraseña: ruta, sello del archivo, página, escala, si van sin anotaciones
        # y el recorte. Si el archivo cambia en disco, el sello cambia y la clave también.
        # (reading colours: only for the pages in view, not the thumbnails)
        tint = reading.TINT if lane == "view" else None
        key = (source[0], source[2], number, scale, source[3], clip, performance.ANTIALIAS, tint)
        ln.callbacks.setdefault(key, []).append(callback)
        # Already being rendered: the callback is added and will get the same image.
        if ln.rendering(key):
            return
        # Una petición que ya esperaba se saca de la cola, para volver a ponerla delante o al final.
        entry = next((e for e in ln.waiting if e[0] == key), None)
        if entry is not None:
            ln.waiting.remove(entry)
        else:
            entry = (key, (source[0], source[1], source[2], number, scale, source[3], clip, performance.ANTIALIAS,
                           tint))
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
        # Only waiting requests are dropped; those being rendered finish and are delivered anyway.
        for entry in [e for e in ln.waiting if not keep(e[0][0], e[0][2])]:
            ln.waiting.remove(entry)
            ln.callbacks.pop(entry[0], None)

    def busy(self, lane: str) -> bool:
        ln = self.lanes.get(lane)
        return ln is not None and (any(s.busy is not None for s in ln.slots) or bool(ln.waiting))

    def _next(self, lane: str) -> None:
        ln = self.lanes.get(lane)
        if ln is None:
            return
        # Cada proceso libre toma la primera petición de la cola: la cola puede reordenarse hasta el último momento.
        for slot in ln.slots:
            if not ln.waiting:
                return
            if slot.busy is not None:
                continue
            try:
                if slot.pool is None:
                    # Spawn, not fork: a forked child would inherit Qt's state and threads, which is not safe.
                    slot.pool = ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn"))
                    slot.ready, slot.killed = False, False
                if not slot.ready:
                    # (the process starts: its first page waits until it is ready, so the time it takes to
                    # start is not counted against that page)
                    slot.busy = ("ready",)
                    future = slot.pool.submit(rendering.ready)
                else:
                    key, args = ln.waiting.pop(0)
                    slot.busy, slot.started = key, time.monotonic()
                    # Una vez enviada al proceso, la petición ya no se puede cancelar: drop() solo toca la cola.
                    future = slot.pool.submit(rendering.render, *args)
            except Exception:  # (no process could be started: render in the window's)
                self._fail()
                return
            future.add_done_callback(lambda f, slot=slot, key=slot.busy: self._arrived.emit((lane, slot, key, f)))
            if not self.watchdog.isActive():
                self.watchdog.start()

    def _deliver(self, item: tuple) -> None:
        lane, slot, key, future = item
        ln = self.lanes.get(lane)
        if ln is None or slot not in ln.slots:
            return  # (a lane emptied meanwhile, by _fail or shutdown)
        slot.busy = None
        if key == ("ready",):
            if future.exception() is None:
                slot.ready = True
            else:  # (the process could not start)
                self._fail()
                return
            self._next(lane)
            return
        result = None
        try:
            width, height, stride, data = future.result()
            # copy(): QImage does not own the bytes received from the other process.
            result = QImage(data, width, height, stride, QImage.Format.Format_RGB888).copy()
        except Exception as e:
            from concurrent.futures.process import BrokenProcessPool

            # El proceso murió (lo mató el vigilante, o la página lo hizo caer): se reemplaza, y la página no se
            # vuelve a intentar, ni aquí ni en la ventana. Otros errores (una página dañada) solo devuelven None a
            # quien la pidió, que la renderiza en la ventana.
            if isinstance(e, BrokenProcessPool):
                why = (tr("it took longer than {seconds:g} seconds to draw", seconds=LIMIT) if slot.killed
                       else tr("its drawing stopped the process that drew it"))
                self.skipped[(key[0], key[1], key[2])] = why
                slot.pool.shutdown(wait=False, cancel_futures=True)
                slot.pool, slot.ready, slot.killed = None, False, False
                result = Skipped(why)
                # Lo que esperaba de esa misma página en este carril tampoco se intenta.
                for other in [e for e in ln.waiting if e[0][:3] == key[:3]]:
                    ln.waiting.remove(other)
                    for callback in ln.callbacks.pop(other[0], []):
                        _call(callback, result)
        for callback in ln.callbacks.pop(key, []):
            _call(callback, result)
        self._next(lane)

    def _watch(self) -> None:
        """Kill the processes whose page has taken longer than LIMIT (see _deliver)."""
        now, working = time.monotonic(), False
        for ln in self.lanes.values():
            for slot in ln.slots:
                if slot.busy is None or slot.busy == ("ready",) or slot.killed:
                    working = working or slot.busy is not None
                    continue
                working = True
                if now - slot.started > LIMIT and slot.pool is not None:
                    slot.killed = True
                    # (the executor then fails the page's future with BrokenProcessPool: see _deliver)
                    for process in list(getattr(slot.pool, "_processes", {}).values()):
                        process.terminate()
        if not working:
            self.watchdog.stop()

    def _fail(self) -> None:
        """The processes can't render: tell all who wait (they render themselves)."""
        self.broken = True
        self.watchdog.stop()
        # Se vacían los carriles antes de llamar a nadie: una devolución de llamada podría pedir otra
        # página y no debe encontrar el carril viejo.
        lanes, self.lanes = self.lanes, {}
        for ln in lanes.values():
            for slot in ln.slots:
                if slot.pool is not None:
                    # wait=False: closing must not block the window on a page still being rendered.
                    slot.pool.shutdown(wait=False, cancel_futures=True)
            for callbacks in ln.callbacks.values():
                for callback in callbacks:
                    _call(callback, None)

    def shutdown(self) -> None:
        self.watchdog.stop()
        for ln in self.lanes.values():
            for slot in ln.slots:
                if slot.pool is not None:
                    slot.pool.shutdown(wait=False, cancel_futures=True)
        self.lanes = {}


def skipped_image(width: int, height: int, skipped: Skipped, words: bool = True) -> QImage:
    """A grey picture of WIDTH × HEIGHT in place of a page that was SKIPPED, saying why (WORDS)."""
    image = QImage(max(width, 1), max(height, 1), QImage.Format.Format_RGB888)
    image.fill(QColor(225, 225, 225))
    if words and width > 120 and height > 60:
        p = QPainter(image)
        p.setPen(QColor(90, 90, 90))
        font = QFont()
        font.setPixelSize(max(11, min(width, height) // 30))
        p.setFont(font)
        text = tr("This page was not drawn: {reason}.", reason=skipped.reason)
        p.drawText(image.rect().adjusted(20, 20, -20, -20),
                   int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap), text)
        p.end()
    return image


def _call(callback: Callable, image) -> None:
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
