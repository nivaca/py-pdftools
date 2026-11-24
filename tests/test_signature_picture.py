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


def test_a_photo_taken_indoors(tmp_path):
    """A photo under a lamp: the paper grey and bluish, darker towards a corner. It is all paper all the same:
    transparent, and the picture cut to the signature (with a fixed threshold, it stayed a blue-grey box)."""
    import random

    QApplication.instance() or QApplication([])
    img = QImage(800, 400, QImage.Format.Format_RGB32)
    random.seed(1)
    for y in range(400):
        for x in range(800):
            shade = 190 - int(25 * (x + y) / 1200) + random.randint(-6, 6)
            img.setPixelColor(x, y, QColor(shade - 8, shade - 2, shade + 10))
    p = QPainter(img)
    p.setPen(QPen(QColor(25, 25, 60), 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(QPointF(200, 200), QPointF(600, 220))
    p.end()
    path = tmp_path / "indoor.jpg"
    img.save(str(path), "JPG", 85)
    out = QImage.fromData(signature.prepared(path))
    assert out.width() < 450 and out.height() < 60  # (cut to the stroke, not the whole photo)
    corners = [out.pixelColor(x, y).alpha() for x in (0, out.width() - 1) for y in (0, out.height() - 1)]
    assert corners == [0, 0, 0, 0]


def test_a_picture_with_its_own_transparency(tmp_path):
    """A PNG already transparent around the signature, black under its transparent pixels (as many are): not
    turned into its negative."""
    QApplication.instance() or QApplication([])
    img = QImage(600, 300, QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))  # (transparent, and black underneath)
    p = QPainter(img)
    p.setPen(QPen(QColor(0, 0, 0), 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(QPointF(150, 150), QPointF(450, 160))
    p.end()
    path = tmp_path / "clear.png"
    img.save(str(path))
    out = QImage.fromData(signature.prepared(path))
    assert out.width() < 330 and out.height() < 40  # (cut to the stroke: not a black box)
    assert out.pixelColor(0, 0).alpha() == 0
    assert max(out.pixelColor(x, out.height() // 2).alpha() for x in range(out.width())) == 255


def test_the_size(tmp_path, monkeypatch, scan):
    """A drag with the tool makes the signature as wide as the box; a click, of the width set in My signature."""
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
        dragged = w._signature(0, (100, 100, 300, 100))
        assert dragged.rect[2] - dragged.rect[0] == 200
        d = signature.SignatureDialog(None, 120.0)
        assert d.width_cm.value() == 4.2
        d.width_cm.setValue(6.0)
        w.settings.setValue(signature.WIDTH, d.width_points())
        clicked = w._signature(0, (100, 100, 100, 100))
        assert abs((clicked.rect[2] - clicked.rect[0]) - 6.0 / 2.54 * 72) < 0.5
    finally:
        w.drop_work()
        w.close()
