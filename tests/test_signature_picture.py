"""La firma a mano tomada de una imagen (gui/signature.py): el papel vuelto transparente y la imagen recortada a
la firma; el diálogo la muestra; la herramienta Firma la pone como un sello de imagen, que se guarda en el PDF;
volver a dibujarla la deja de lado."""

from __future__ import annotations

import pymupdf
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QApplication

from py_pdftools.gui import signature


@pytest.fixture
def scan(tmp_path):
    """A photographed signature: a dark stroke on greyish paper, with much paper around it."""
    QApplication.instance() or QApplication([])
    img = QImage(1000, 500, QImage.Format.Format_RGB32)
    img.fill(QColor(238, 236, 230))
    p = QPainter(img)
    p.setPen(QPen(QColor(20, 30, 90), 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(QPointF(300, 250), QPointF(700, 280))
    p.end()
    path = tmp_path / "scan.jpg"
    img.save(str(path), "JPG", 90)
    return path


def test_prepared(scan, tmp_path):
    data = signature.prepared(scan)
    img = QImage.fromData(data)
    # (cut to the stroke, with a small margin; the paper transparent, the ink opaque)
    assert 400 <= img.width() <= 430 and 35 <= img.height() <= 60
    assert img.pixelColor(0, 0).alpha() == 0
    assert max(img.pixelColor(x, img.height() // 2).alpha() for x in range(img.width())) == 255
    opaque = QImage.fromData(signature.prepared(scan, transparent=False))
    assert opaque.pixelColor(0, 0).alpha() == 255
    blank = QImage(200, 100, QImage.Format.Format_RGB32)
    blank.fill(QColor("white"))
    blank.save(str(tmp_path / "blank.png"))
    with pytest.raises(signature.SignatureError, match="Nothing is drawn"):
        signature.prepared(tmp_path / "blank.png")
    (tmp_path / "bad.png").write_text("not a picture")
    with pytest.raises(signature.SignatureError):
        signature.prepared(tmp_path / "bad.png")


def test_the_dialog(scan):
    d = signature.SignatureDialog()
    assert d.kind == "drawn" and not d.transparent.isVisibleTo(d)
    assert d.use_picture(scan)
    assert d.kind == "picture" and d.picture_data and d.transparent.isVisibleTo(d) and not d.preview.pixmap().isNull()
    before = d.picture_data
    d.transparent.setChecked(False)  # (made again, with its paper)
    assert d.picture_data != before
    d.b_draw.click()
    assert d.kind == "drawn"


def test_put_with_the_tool(scan, tmp_path, monkeypatch):
    from py_pdftools.annotate import annots
    from py_pdftools.gui.window import MainWindow

    monkeypatch.setenv("HOME", str(tmp_path))
    doc = pymupdf.open()
    doc.new_page()
    doc.save(tmp_path / "d.pdf")
    w = MainWindow()
    w.ask_recover = lambda when: False
    try:
        assert w.open_path(tmp_path / "d.pdf")
        signature.store_picture(w.settings, signature.prepared(scan))
        assert signature.source(w.settings) == "picture"
        a = w._signature(0, (100, 200, 100, 200))
        x0, y0, x1, y1 = a.rect
        assert a.kind == "stamp" and a.image and (x0, y0) == (100, 200) and x1 - x0 == w.SIGNATURE_WIDTH
        assert 0 < y1 - y0 < 30  # (its proportions kept)
        w.add_drawn(a)
        assert w.save()
        assert [(x.kind, bool(x.image)) for x in annots.read(pymupdf.open(tmp_path / "d.pdf"))] == [("stamp", True)]
        # Drawn again: the drawing is what the tool puts from then on
        signature.store(w.settings, [[(0, 0), (10, 2)]])
        assert signature.source(w.settings) == "drawn" and w._signature(0, (0, 0, 0, 0)).kind == "ink"
    finally:
        w.drop_work()
        w.close()
