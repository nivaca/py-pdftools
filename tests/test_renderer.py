"""The processes that render the pages (gui/renderer.py): several per lane, and a page that takes too
long, or makes its process die, is skipped (its process replaced) instead of hanging the others."""

from __future__ import annotations

import os
import time

import pymupdf
import pytest
from PySide6.QtWidgets import QApplication

from py_pdftools.gui import renderer as renderer_module
from py_pdftools.gui.renderer import Renderer, Skipped


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def slow_pdf(tmp_path_factory):
    """Page 1, a few words; page 2, a large picture of noise, slow to decode."""
    path = tmp_path_factory.mktemp("slow") / "slow.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Quick", fontsize=14)
    side = 4500
    noise = pymupdf.Pixmap(pymupdf.csRGB, side, side, os.urandom(side * side * 3), False)
    doc.new_page().insert_image(pymupdf.Rect(0, 0, 595, 842), stream=noise.tobytes("jpg", jpg_quality=95))
    doc.save(path)
    return path


def wait(app, done, seconds=90):
    deadline = time.time() + seconds
    while not done() and time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)


@pytest.fixture
def renderer(app, monkeypatch):
    monkeypatch.setattr(renderer_module, "ENABLED", True)
    r = Renderer()
    r.watchdog.setInterval(20)
    yield r
    r.shutdown()


def source(path):
    st = path.stat()
    return str(path), "", (st.st_mtime_ns, st.st_size), False


def test_a_slow_page_is_skipped_and_the_others_drawn(app, renderer, slow_pdf, monkeypatch):
    monkeypatch.setattr(renderer_module, "LIMIT", 0.15)
    got = {}
    renderer.request("view", source(slow_pdf), 1, 1.0, lambda image: got.setdefault("slow", image))
    renderer.request("view", source(slow_pdf), 0, 1.0, lambda image: got.setdefault("quick", image))
    wait(app, lambda: len(got) == 2)
    assert isinstance(got["slow"], Skipped) and "longer than" in got["slow"].reason
    assert not isinstance(got["quick"], Skipped) and got["quick"].width() == 595
    # (asked again, at another size: skipped at once, without being tried)
    again = []
    renderer.request("thumbs", source(slow_pdf), 1, 0.2, again.append)
    assert again and isinstance(again[0], Skipped)
    # (and the lane goes on with a new process)
    more = []
    renderer.request("view", source(slow_pdf), 0, 0.5, more.append)
    wait(app, lambda: more)
    assert not isinstance(more[0], Skipped) and more[0].width() == round(595 * 0.5)


def test_a_page_that_stops_its_process(app, renderer, slow_pdf):
    """A process that dies while it draws a page (here, killed from outside): the page is skipped,
    the window does not draw it itself, and the other pages are drawn by a new process."""
    got = []
    renderer.request("view", source(slow_pdf), 1, 1.0, got.append)

    def drawing():  # (the process that took the page)
        return next((s for s in renderer.lanes["view"].slots if s.busy and s.busy[2:3] == (1,)), None)

    wait(app, lambda: drawing() is not None)
    for process in list(drawing().pool._processes.values()):
        process.kill()
    wait(app, lambda: got)
    assert isinstance(got[0], Skipped) and "stopped" in got[0].reason
    other = []
    renderer.request("view", source(slow_pdf), 0, 1.0, other.append)
    wait(app, lambda: other)
    assert not isinstance(other[0], Skipped)


def test_the_canvas_shows_a_skipped_page(app, slow_pdf, tmp_path, monkeypatch):
    from py_pdftools.gui.window import MainWindow

    monkeypatch.setenv("HOME", str(tmp_path))
    w = MainWindow()
    w.ask_recover = lambda when: False
    assert w.open_path(slow_pdf)
    key = (id(w.canvas.doc), 0, 0.5)
    w.canvas.pages[0].wanted = key
    w.canvas._arrived(key, Skipped("a test"))
    shown = w.canvas.pages[0].pixmap.pixmap().toImage()
    assert shown.width() == round(595 * 0.5) and shown.pixelColor(2, 2).lightness() < 240  # (grey, not white)
    w.annotations = w.saved = []
    w.close()


def test_thumbnails_only_near_those_in_view(app, tmp_path, monkeypatch):
    """With many pages, only the thumbnails near those in view are made; scrolling the list makes the
    others, and those far away are forgotten beyond MAX_THUMBS."""
    from py_pdftools.gui import window as window_module
    from py_pdftools.gui.window import MainWindow

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(window_module, "MAX_THUMBS", 12)  # (about ten are wanted at each place of the list)
    path = tmp_path / "long.pdf"
    doc = pymupdf.open()
    for i in range(300):
        doc.new_page().insert_text((72, 72), f"Page {i + 1}", fontsize=14)
    doc.save(path)
    w = MainWindow()
    w.ask_recover = lambda when: False
    w.resize(1000, 700)
    w.show()
    assert w.open_path(path)

    def settle():  # (until no thumbnail is left to make: they wait, 50 ms at a time, for the pages)
        wait(app, lambda: not w.thumb_timer.isActive() and not w.canvas._here, seconds=20)

    settle()
    made = set(w._thumbs)
    assert 0 in made and 3 < len(made) <= 12 and 299 not in made
    bar = w.pages.verticalScrollBar()
    bar.setValue(bar.maximum())
    settle()
    assert 299 in w._thumbs and len(w._thumbs) <= 12 and 0 not in w._thumbs
    w.annotations = w.saved = []
    w.close()


def test_deep_zoom_in_tiles(app, tmp_path, monkeypatch):
    """At a zoom where a page would be longer than TILE_ABOVE pixels, it is drawn whole at most
    BACKDROP_SIDE pixels long, and the part in view in tiles at the full scale; back at a low zoom, no
    tiles are left."""
    from PySide6.QtCore import QRectF

    from py_pdftools.gui import canvas as canvas_module
    from py_pdftools.gui.window import MainWindow

    monkeypatch.setenv("HOME", str(tmp_path))
    path = tmp_path / "one.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Deep", fontsize=14)
    doc.save(path)
    w = MainWindow()
    w.ask_recover = lambda when: False
    w.resize(1000, 700)
    w.show()
    assert w.open_path(path)
    canvas = w.canvas

    def settle():
        canvas.render_timer.start(0)
        wait(app, lambda: not canvas.render_timer.isActive() and not canvas._here and not canvas._tiles_asked,
             seconds=20)

    canvas.set_zoom(8)
    settle()
    item = canvas.pages[0]
    assert item.scale_shown <= canvas_module.BACKDROP_SIDE / 842 + 0.01
    full = canvas._full_scale()
    assert item.tiles and all(key[0] == full for key in item.tiles)
    assert all(t.pixmap().width() <= canvas_module.TILE for t in item.tiles.values())
    covered = QRectF()
    for t in item.tiles.values():
        covered = covered.united(t.mapRectToParent(QRectF(t.pixmap().rect())))
    view = item.mapFromScene(canvas.mapToScene(canvas.viewport().rect()).boundingRect()).boundingRect() & item.rect()
    assert covered.adjusted(-0.5, -0.5, 0.5, 0.5).contains(view)
    canvas.set_zoom(1)
    settle()
    assert not item.tiles and item.scale_shown == canvas._full_scale()
    w.annotations = w.saved = []
    w.close()
