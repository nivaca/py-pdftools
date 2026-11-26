"""Lo que la ventana hace al abrir un documento, ir a una página, desplazarse y cambiar el zoom se cuenta (las
páginas dibujadas, las miniaturas) en uno de 50 páginas y en uno de 500: el largo no puede pedir más trabajo
que el corto. Se cuentan cosas, no se miden tiempos, así que la prueba no falla por una máquina ocupada."""

from __future__ import annotations

import time

import pymupdf
import pytest
from PySide6.QtWidgets import QApplication

from py_pdftools.gui import canvas as canvas_module
from py_pdftools.gui import window as window_module


PAGE_IMAGE = canvas_module.page_image


def _pdf(folder, pages: int):
    path = folder / f"{pages}.pdf"
    doc = pymupdf.open()
    for i in range(pages):
        doc.new_page(width=595, height=842).insert_text((72, 72), f"Page {i + 1}", fontsize=14)
    doc.save(path)
    return path


@pytest.fixture(scope="module")
def pdfs(tmp_path_factory):
    folder = tmp_path_factory.mktemp("counts")
    return {n: _pdf(folder, n) for n in (50, 500)}


def _idle(app, w, seconds: float = 20.0):
    """Until nothing is left to draw: no pages waiting here, no thumbnails due."""
    deadline = time.time() + seconds
    quiet = 0
    while time.time() < deadline and quiet < 20:
        app.processEvents()
        busy = w.canvas._here or w.canvas.local_timer.isActive() or w.thumb_timer.isActive()
        quiet = 0 if busy else quiet + 1
        time.sleep(0.005)


def _work(path, monkeypatch, tmp_path) -> dict[str, int]:
    """The pages drawn and the thumbnails made while opening PATH, going to its middle, scrolling two screens
    and zooming in."""
    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    counts = {"pages": 0, "thumbnails": 0}
    page_image = PAGE_IMAGE  # (not the module's: a run before may have left its own counter there)

    def counted(kind):
        def draw(*args, **kwargs):
            counts[kind] += 1
            return page_image(*args, **kwargs)
        return draw

    monkeypatch.setattr(canvas_module, "page_image", counted("pages"))
    monkeypatch.setattr(window_module, "page_image", counted("thumbnails"))
    w = window_module.MainWindow()
    w.ask_recover = lambda when: False
    w.resize(1100, 800)
    w.show()
    try:
        assert w.open_path(path)
        _idle(app, w)
        w.canvas.go_to(25)
        _idle(app, w)
        bar = w.canvas.verticalScrollBar()
        bar.setValue(bar.value() + 2 * w.canvas.viewport().height())
        _idle(app, w)
        w.canvas.set_zoom(w.canvas.zoom() * 1.5)
        _idle(app, w)
    finally:
        w.annotations = w.saved = []
        w.close()
    return counts


def test_a_long_document_asks_for_no_more_work(pdfs, monkeypatch, tmp_path):
    short = _work(pdfs[50], monkeypatch, tmp_path)
    long = _work(pdfs[500], monkeypatch, tmp_path)
    assert short["pages"] > 0 and short["thumbnails"] > 0  # (the counting works)
    for kind in short:
        assert long[kind] <= short[kind], (kind, short, long)
