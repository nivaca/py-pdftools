"""Settings > Performance (gui/performance.py): the memory profile sets the caches, the transparency of
selections and the antialiasing of text and graphics; the dialog keeps and applies them."""

from __future__ import annotations

import pymupdf
import pytest
from PySide6.QtWidgets import QApplication

from py_pdftools.core import config, rendering
from py_pdftools.gui import canvas, performance, renderer, window as window_module

NORMAL = {"memory": "normal", "transparency": True, "text_antialias": True, "graphics_antialias": True}


@pytest.fixture(autouse=True)
def usual():
    QApplication.instance() or QApplication([])
    yield
    performance.apply(dict(NORMAL))


@pytest.fixture
def text_pdf(tmp_path):
    path = tmp_path / "text.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=300, height=200)
    for i in range(4):
        page.insert_text((20, 40 + i * 30), "Antialiasing smooths the edges", fontsize=14)
    page.draw_line((20, 170), (280, 190), width=1.5)
    doc.save(path)
    return path


def test_the_profiles(monkeypatch):
    performance.apply({**NORMAL, "memory": "low"})
    assert (canvas.CACHED_PAGES, canvas.MAX_TILES, window_module.MAX_THUMBS, renderer.WORKERS["view"]) == \
        (4, 12, 100, 1)
    performance.apply(dict(NORMAL))
    assert (canvas.CACHED_PAGES, canvas.MAX_TILES, window_module.MAX_THUMBS, canvas.AHEAD) == (16, 48, 400, 0.5)
    monkeypatch.setattr(performance, "available_memory", lambda: 8 << 30)
    performance.apply({**NORMAL, "memory": "all"})
    assert canvas.CACHED_PAGES == (4 << 30) // performance.PAGE_BYTES and window_module.ALL_THUMBS
    assert window_module.MAX_THUMBS >= 400 and canvas.AHEAD > 1


def test_every_thumbnail_with_the_profile_all(tmp_path, monkeypatch):
    from py_pdftools.gui.window import MainWindow

    monkeypatch.setenv("HOME", str(tmp_path))
    path = tmp_path / "long.pdf"
    doc = pymupdf.open()
    for _ in range(60):
        doc.new_page()
    doc.save(path)
    w = MainWindow()
    w.ask_recover = lambda when: False
    w.resize(1000, 600)
    w.show()
    assert w.open_path(path)
    assert len(w._thumb_rows()) < 60
    performance.apply({**NORMAL, "memory": "all"})
    rows = w._thumb_rows()
    assert sorted(rows) == list(range(60)) and rows[0] == 0
    w.close()


def grey_pixels(path, antialias) -> int:
    """How many pixels of the page are neither white nor black: the soft edges of antialiasing."""
    st = path.stat()
    width, height, stride, data = rendering.render(str(path), "", (st.st_mtime_ns, st.st_size), 0, 2.0,
                                                   antialias=antialias)
    return sum(1 for v in data[::3] if 40 < v < 215)


def test_antialiasing(text_pdf):
    smooth = grey_pixels(text_pdf, (8, 8))
    hard = grey_pixels(text_pdf, (0, 0))
    text_only = grey_pixels(text_pdf, (8, 0))
    assert smooth > 200 and hard < smooth / 10 and hard < text_only < smooth
    performance.apply({**NORMAL, "text_antialias": False, "graphics_antialias": False})
    assert performance.ANTIALIAS == (0, 0)


def test_the_dialog_and_transparency(tmp_path, monkeypatch, text_pdf):
    from py_pdftools.gui.prefs import SettingsDialog
    from py_pdftools.gui.window import MainWindow

    monkeypatch.setenv("HOME", str(tmp_path))
    w = MainWindow()
    w.ask_recover = lambda when: False
    assert w.open_path(text_pdf)
    dialog = SettingsDialog(w.prefs, w)
    assert dialog.memory.currentData() == "normal" and dialog.transparency.isChecked()
    dialog.memory.setCurrentIndex(dialog.memory.findData("high"))
    dialog.transparency.setChecked(False)
    dialog.accept()
    assert config.get("memory") == "high" and config.get("transparency") is False
    assert canvas.CACHED_PAGES == 48 and not canvas.TRANSPARENT
    w.set_tool("selecttext")
    w.canvas.select_all_text(0)
    marks = w.canvas._sel_marks
    assert marks and all(m.brush().style().name == "NoBrush" for m in marks)  # (outlined, not shaded)
    w.close()
