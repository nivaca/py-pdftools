"""Las páginas mucho mayores que el papel (un escaneo puesto a 72 puntos por píxel: una página A4 escaneada a
300 ppp mide más de un metro): las anotaciones nuevas crecen en proporción (annots.page_scale), para que su texto
se lea; en el papel de siempre, nada cambia."""

from __future__ import annotations

import pymupdf
import pytest
from PySide6.QtWidgets import QApplication

from py_pdftools.annotate.annots import page_scale


def test_the_scale():
    assert page_scale(612, 792) == 1.0 and page_scale(595, 842) == 1.0  # (Letter, A4)
    assert page_scale(842, 1191) == 1.0 and page_scale(792, 1224) == 1.0  # (A3, tabloid: paper still)
    assert page_scale(2480, 3508) == pytest.approx(4.05, abs=0.01)  # (A4 at 300 ppp, as 72 points to the pixel)
    assert page_scale(3508, 2480) == page_scale(2480, 3508)  # (landscape the same)


@pytest.fixture
def window(tmp_path, monkeypatch):
    from py_pdftools.gui.window import MainWindow

    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    doc = pymupdf.open()
    doc.new_page(width=595, height=842)  # (A4)
    doc.new_page(width=2480, height=3508)  # (a scan at 300 ppp, as 72 points to the pixel)
    doc.save(tmp_path / "d.pdf")
    w = MainWindow()
    w.ask_recover = lambda when: False
    w.show()
    assert w.open_path(tmp_path / "d.pdf")
    yield w
    w.annotations = w.saved = []
    w.drop_work()
    w.close()


def test_new_annotations_follow_the_page(window):
    w = window
    paper = w.new_annotation("freetext", 0, (100, 100, 280, 140))
    scan = w.new_annotation("freetext", 1, (100, 100, 280, 140))
    assert paper.font_size == w.prefs.style("freetext").font_size
    assert scan.font_size == pytest.approx(paper.font_size * 4.05, abs=0.1)
    line = w.new_annotation("rect", 1, (100, 100, 300, 300))
    assert line.width == pytest.approx(w.prefs.style("rect").width * 4.05, abs=0.01)
    # A stamp clicked: larger, and centred where the click was
    small = w.new_annotation("stamp", 0, (300, 400, 300, 400))
    big = w.new_annotation("stamp", 1, (1200, 1700, 1200, 1700))
    assert (big.rect[2] - big.rect[0]) == pytest.approx((small.rect[2] - small.rect[0]) * 4.05, rel=0.01)
    assert (big.rect[0] + big.rect[2]) / 2 == pytest.approx(1200, abs=0.5)
    # The text box and the check mark made by a click, in the canvas
    assert w.canvas.page_scale(0) == 1.0 and w.canvas.page_scale(1) == pytest.approx(4.05, abs=0.01)
