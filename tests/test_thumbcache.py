"""Las miniaturas guardadas en el disco (core/thumbcache.py): se guardan y se leen por la huella de su página,
la carpeta no pasa de su límite, una copia censurada las borra todas, y una ventana que abre otra vez un
documento las muestra sin dibujarlas."""

from __future__ import annotations

import os
import time

import pymupdf
import pytest
from PySide6.QtWidgets import QApplication

from py_pdftools.core import thumbcache
from py_pdftools.gui import canvas as canvas_module
from py_pdftools.gui import performance
from py_pdftools.gui import window as window_module

PAGE_IMAGE = canvas_module.page_image
DRAWING = (8, 8)


def test_kept_and_read_again():
    assert thumbcache.load(b"page", (90, 120), DRAWING) is None
    thumbcache.save(b"page", (90, 120), DRAWING, 2, 1, b"\x01\x02\x03\x04\x05\x06")
    assert thumbcache.load(b"page", (90, 120), DRAWING) == (2, 1, b"\x01\x02\x03\x04\x05\x06")
    # (another size of thumbnails, or other antialiasing: another one)
    assert thumbcache.load(b"page", (120, 160), DRAWING) is None
    assert thumbcache.load(b"page", (90, 120), (0, 0)) is None
    thumbcache.clear()
    assert thumbcache.load(b"page", (90, 120), DRAWING) is None and not thumbcache.folder().exists()


def test_the_folder_keeps_to_its_limit():
    for n in range(10):
        thumbcache.save(bytes([n]), (90, 120), DRAWING, 10, 10, bytes(300))
        path = thumbcache._path(bytes([n]), (90, 120), DRAWING)
        os.utime(path, (1000 + n, 1000 + n))  # (each used after the one before)
    thumbcache.load(bytes([0]), (90, 120), DRAWING)  # (the oldest, used now: it stays)
    thumbcache.prune(limit=4 * (300 + thumbcache.HEADER.size))
    kept = [n for n in range(10) if thumbcache.load(bytes([n]), (90, 120), DRAWING) is not None]
    assert kept == [0, 7, 8, 9]


def test_a_redacted_copy_removes_them_all(tmp_path):
    from py_pdftools.redact.redact import Box, write_redacted

    thumbcache.save(b"page", (90, 120), DRAWING, 1, 1, b"\x00\x00\x00")
    source = tmp_path / "s.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 100), "Secret", fontsize=14)
    doc.save(source)
    write_redacted(source, [Box(0, (60, 85, 200, 105))], tmp_path / "out.pdf")
    assert not thumbcache.folder().exists()


@pytest.fixture
def pdf(tmp_path):
    path = tmp_path / "d.pdf"
    doc = pymupdf.open()
    for n in range(5):
        doc.new_page(width=300, height=400).insert_text((40, 60), f"Page {n + 1}", fontsize=24)
    doc.save(path)
    return path


def _open(pdf, drawn, app):
    w = window_module.MainWindow()
    w.ask_recover = lambda when: False
    w.resize(1000, 900)
    w.show()
    assert w.open_path(pdf)
    deadline = time.time() + 20
    while time.time() < deadline and (w.thumb_timer.isActive() or any(n not in w._thumbs for n in w._thumb_rows())):
        app.processEvents()
        time.sleep(0.005)
    return w


def test_a_document_opened_again_shows_them_without_drawing(pdf, tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    drawn = []
    monkeypatch.setattr(window_module, "page_image",
                        lambda page, *args, **kwargs: drawn.append(page.number) or PAGE_IMAGE(page, *args, **kwargs))
    performance.apply({**performance.settings(), "thumb_cache": True})
    try:
        w = _open(pdf, drawn, app)
        assert sorted(drawn) == [0, 1, 2, 3, 4] and len(list(thumbcache.folder().glob("*/*"))) == 5
        w.close()
        drawn.clear()
        w = _open(pdf, drawn, app)
        assert drawn == [] and sorted(w._thumbs) == [0, 1, 2, 3, 4]
        w.close()
    finally:
        # Turned off, nothing is left on disk.
        performance.apply({**performance.settings(), "thumb_cache": False})
    assert not window_module.DISK_THUMBS and not thumbcache.folder().exists()
