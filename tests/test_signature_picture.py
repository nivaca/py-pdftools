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
    assert d.kind == "drawn" and not d.transparent.isVisibleTo(d) and d.list.count() == 1
    assert d.use_picture(scan)
    assert d.kind == "picture" and d.picture_data and d.transparent.isVisibleTo(d) and not d.preview.pixmap().isNull()
    # The whole picture in the space it has (it was scaled before the dialog had its size, and showed cut)
    d.resize(560, 380)
    d.show()
    QApplication.processEvents()
    room, shown = d.preview.size(), d.preview.pixmap().size()
    assert shown.width() <= room.width() and shown.height() <= room.height()
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
        keep(w.settings, [picture_entry("1", scan)])
        a = w._signature(0, (100, 200, 100, 200))
        x0, y0, x1, y1 = a.rect
        assert a.kind == "stamp" and a.image and (x0, y0) == (100, 200) and x1 - x0 == w.SIGNATURE_WIDTH
        assert 0 < y1 - y0 < 30  # (its proportions kept)
        w.add_drawn(a)
        assert w.save()
        assert [(x.kind, bool(x.image)) for x in annots.read(pymupdf.open(tmp_path / "d.pdf"))] == [("stamp", True)]
        # Another, drawn, chosen: the drawing is what the tool puts from then on
        keep(w.settings, [picture_entry("1", scan), signature.Kept("2", "Initials", strokes=[[(0, 0), (1, 0.2)]])],
             "2")
        assert w._signature(0, (0, 0, 0, 0)).kind == "ink"
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
        keep(w.settings, [picture_entry("1", scan)])
        dragged = w._signature(0, (100, 100, 300, 100))
        assert dragged.rect[2] - dragged.rect[0] == 200
        d = signature.SignatureDialog(None, signature.kept(w.settings), "1", 120.0)
        assert d.width_cm.value() == 4.2
        d.width_cm.setValue(6.0)  # (the width of this signature)
        signature.save(w.settings, d.kept_entries(), d.chosen_id())
        clicked = w._signature(0, (100, 100, 100, 100))
        assert abs((clicked.rect[2] - clicked.rect[0]) - 6.0 / 2.54 * 72) < 0.5
    finally:
        w.drop_work()
        w.close()


def keep(settings, entries, chosen=""):
    signature.save(settings, entries, chosen or entries[0].id)


def picture_entry(kid, path, name="Signature"):
    return signature.Kept(kid, name, "picture", file=str(path), data=signature.prepared(path))


def test_a_negative_kept_before_is_not_used(tmp_path, scan):
    """The one picture an older version kept, as its negative (opaque black where the paper was), is not taken
    into the list: it is asked for again; a good one, transparent or on white paper, is."""
    from py_pdftools.core import config
    from py_pdftools.gui.state import State

    img = QImage(400, 100, QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 255))
    p = QPainter(img)
    p.setPen(QPen(QColor(40, 40, 40, 80), 6))
    p.drawLine(QPointF(50, 50), QPointF(350, 55))
    p.end()
    old = config.config_dir() / signature.OLD_PICTURE
    old.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(old))
    settings = State("window")
    settings.setValue(signature.OLD_SOURCE, "picture")
    assert signature.kept(settings) == [] and signature.chosen(settings) is None
    for transparent in (True, False):
        settings.remove(signature.KEPT)
        old.write_bytes(signature.prepared(scan, transparent))
        [entry] = signature.kept(settings)
        assert entry.kind == "picture" and signature.chosen(settings).id == entry.id


def test_one_signature_from_before_goes_into_the_list(scan):
    """An older version kept one signature, drawn (and maybe a picture too): both go into the list, the one it
    put chosen; the old ones are left where they were."""
    import json

    from py_pdftools.core import config
    from py_pdftools.gui.state import State

    settings = State("window")
    settings.setValue(signature.OLD_STROKES, json.dumps([[(0, 0), (1, 0.3)]]))
    (config.config_dir() / signature.OLD_PICTURE).write_bytes(signature.prepared(scan))
    settings.setValue(signature.OLD_SOURCE, "picture")
    drawn, picture = signature.kept(settings)
    assert (drawn.kind, picture.kind) == ("drawn", "picture") and drawn.strokes == [[(0, 0), (1, 0.3)]]
    assert signature.chosen(settings).id == picture.id and signature.picture_path(picture.id).is_file()
    assert settings.value(signature.OLD_STROKES)  # (left: an older version still finds it)
    assert len(signature.kept(settings)) == 2  # (done once)


def test_several_signatures(scan, tmp_path):
    """My signatures keeps a list: a new one drawn, one from a picture, renamed, its picture replaced, one
    deleted (its picture with it); OK keeps them, the one selected is the one the tool puts; the empty one is
    left out."""
    from py_pdftools.gui.state import State

    settings = State("window")
    d = signature.SignatureDialog(None, [], "", 120.0)
    assert d.list.count() == 1 and not d.b_delete.isEnabled()
    d.pad.strokes = [[(10.0, 10.0), (100.0, 40.0), (200.0, 20.0)]]
    d.name.setText("Whole")
    e = d.add()
    assert d.list.count() == 2 and d.list.currentRow() == 1 and d.pad.strokes == []
    assert d.use_picture(scan) and d.kind == "picture"
    d.name.setText("Scanned")
    d.add()  # (left empty: not kept)
    d.list.setCurrentRow(0)
    assert d.kind == "drawn" and d.name.text() == "Whole" and d.pad.strokes  # (shown again, to change it)
    d.width_cm.setValue(3.0)
    entries = d.kept_entries()
    assert [(x.name, x.kind) for x in entries] == [("Whole", "drawn"), ("Scanned", "picture")]
    assert abs(entries[0].width - 3.0 / 2.54 * 72) < 0.1 and e.id == entries[1].id
    signature.save(settings, entries, d.chosen_id())
    assert signature.chosen(settings).name == "Whole" and signature.picture_path(e.id).is_file()

    # Again: the picture replaced by another (on its paper), then the drawn one deleted
    d = signature.SignatureDialog(None, signature.kept(settings), e.id, 120.0)
    assert d.list.currentRow() == 1 and d.kind == "picture" and not d.preview.pixmap().isNull()
    assert d.transparent.isEnabled()  # (the picture it came from is still there: it can be made again)
    before = signature.picture_path(e.id).read_bytes()
    assert d.use_picture(scan)
    d.transparent.setChecked(False)
    d.list.setCurrentRow(0)
    d.delete()
    assert d.list.count() == 1 and d.chosen_id() == e.id
    signature.save(settings, d.kept_entries(), d.chosen_id())
    [only] = signature.kept(settings)
    assert only.id == e.id and not only.transparent and signature.picture_path(e.id).read_bytes() != before
    assert sorted(p.name for p in signature.folder().iterdir()) == [f"{e.id}.png"]


def test_a_drawn_signature_as_a_picture():
    """A drawn signature made a picture (for a digital signature): transparent around, dark blue strokes."""
    QApplication.instance() or QApplication([])
    data = signature.drawn_picture([[(0, 0), (0.5, 0.2), (1, 0)]], 400)
    out = QImage.fromData(data)
    assert 390 < out.width() < 420 and out.height() < 120
    assert out.pixelColor(0, out.height() - 1).alpha() == 0
    assert any(out.pixelColor(x, y).blue() > 100 and out.pixelColor(x, y).alpha() == 255
               for x in range(out.width()) for y in range(out.height()))
