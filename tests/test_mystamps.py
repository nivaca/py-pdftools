"""Los sellos propios (annotate/mystamps.py y la herramienta Sello): de una imagen o de una página de un PDF, a su
tamaño verdadero, puestos en la página, guardados en el documento y leídos de nuevo."""

from __future__ import annotations

import pymupdf
import pytest
from PySide6.QtWidgets import QApplication

from py_pdftools.annotate import mystamps


def seal_pdf(path):
    """A circle of 60 points of radius, with a word in it, in the middle of an A4 page."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.draw_circle((300, 400), 60, color=(0.7, 0, 0), width=4)
    page.insert_text((265, 405), "SEAL", fontsize=18, color=(0.7, 0, 0))
    doc.new_page()  # (a second page, blank)
    doc.save(path)
    return path


def picture(path, w=600, h=300):
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, w, h), True)
    pix.clear_with(0)
    pix.save(path)
    return path


def test_the_library(tmp_path):
    assert mystamps.names() == []
    assert mystamps.add(seal_pdf(tmp_path / "seal.pdf")) == "seal"
    data, (w, h) = mystamps.image("seal")
    # (what is painted, at its size: about 124 points, the circle and its stroke; not the 200 its curves report)
    assert 120 < w < 132 and 120 < h < 132 and pymupdf.Pixmap(data).alpha
    with pytest.raises(mystamps.StampError, match="blank"):
        mystamps.add(tmp_path / "seal.pdf", "empty", page=2)
    with pytest.raises(mystamps.StampError, match="no page 5"):
        mystamps.add(tmp_path / "seal.pdf", "x", page=5)
    assert mystamps.add(picture(tmp_path / "logo.png"), "My logo") == "My logo"
    assert mystamps.image("My logo")[1] == (220.0, 110.0)  # (a wide picture made 220 points wide)
    assert mystamps.add(picture(tmp_path / "small.png", 150, 75), "small")
    assert mystamps.image("small")[1] == (72.0, 36.0)  # (150 pixels at 150 dpi: an inch)
    assert mystamps.names() == ["My logo", "seal", "small"]
    (tmp_path / "bad.png").write_text("not a picture")
    with pytest.raises(mystamps.StampError):
        mystamps.add(tmp_path / "bad.png")
    mystamps.remove("small")
    assert mystamps.names() == ["My logo", "seal"]
    with pytest.raises(mystamps.StampError):
        mystamps.image("small")
    assert mystamps.safe_name(' a/b: "c" ') == "a b c"


def test_kept_in_the_settings():
    from py_pdftools.annotate import settings

    assert settings.valid("stamp", "image:seal") and settings.valid("stamp", "text:OK")
    assert not settings.valid("stamp", "image:") and not settings.valid("stamp", "image:a\nb")


def test_put_on_a_page_and_saved(tmp_path, monkeypatch):
    from py_pdftools.annotate import annots
    from py_pdftools.gui.window import MainWindow

    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    mystamps.add(seal_pdf(tmp_path / "seal.pdf"))
    doc = pymupdf.open()
    doc.new_page()
    doc.save(tmp_path / "d.pdf")
    w = MainWindow()
    w.ask_recover = lambda when: False
    try:
        assert w.open_path(tmp_path / "d.pdf")
        w.set_stamp("image:seal")
        a = w.new_annotation("stamp", 0, (300, 400, 300, 400))  # (a click: centred there, at its own size)
        assert a.stamp == "" and a.image == mystamps.image("seal")[0] and a.contents == "seal"
        x0, y0, x1, y1 = a.rect
        assert 120 < x1 - x0 < 132 and abs((x0 + x1) / 2 - 300) < 1
        w.add(a)
        assert w.save()
        found = annots.read(pymupdf.open(tmp_path / "d.pdf"))
        assert [(x.kind, bool(x.image), x.stamp) for x in found] == [("stamp", True, "")]
        # A stamp removed from the library: the next one put is a standard one, and the window says why
        mystamps.remove("seal")
        b = w.new_annotation("stamp", 0, (100, 100, 100, 100))
        assert b.stamp == "Approved" and "no longer there" in w.statusBar().currentMessage()
    finally:
        w.drop_work()
        w.close()
