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
