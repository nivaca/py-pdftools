"""A PDF made of pictures (pages/combine.py from_images, File > New PDF from pictures, py-pdftools
from-images): a page for each picture, as big as it is or on paper with a margin, lying or standing;
photographs turned as the camera says; and the window, which opens the PDF made, in the mode OCR if asked."""

from __future__ import annotations

import struct

import pymupdf
import pytest

from py_pdftools.pages import combine
from py_pdftools.pages.combine import CombineError


def picture(path, w, h, grey=150):
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, w, h), 0)
    pix.clear_with(grey)
    pix.save(path)
    return path


def turned_photo(path, w, h):
    """A JPEG W × H whose EXIF says it is to be shown turned a quarter (as phones save them)."""
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, w, h), 0)
    pix.clear_with(90)
    jpg = pix.tobytes("jpg")
    tiff = b"II*\x00" + struct.pack("<I", 8) + struct.pack("<H", 1) + struct.pack("<HHIHH", 0x0112, 3, 1, 6, 0) \
        + struct.pack("<I", 0)
    app1 = b"Exif\x00\x00" + tiff
    path.write_bytes(jpg[:2] + b"\xff\xe1" + struct.pack(">H", len(app1) + 2) + app1 + jpg[2:])
    return path


def sizes(path):
    return [(round(p.rect.width), round(p.rect.height)) for p in pymupdf.open(path)]


@pytest.fixture
def pics(tmp_path):
    return picture(tmp_path / "wide.png", 400, 200), picture(tmp_path / "tall.jpg", 100, 300)


def test_as_big_as_the_pictures(pics, tmp_path):
    out = tmp_path / "o.pdf"
    assert combine.from_images(list(pics), out) == 2
    assert sizes(out) == [(300, 150), (75, 225)]  # (a 96 ppp, pues las imágenes no dicen ninguna)
    combine.from_images(list(pics), out, margin=10)
    assert sizes(out) == [(357, 207), (132, 282)]
    doc = pymupdf.open(out)
    assert len(doc[0].get_images()) == 1


def test_on_paper(pics, tmp_path):
    out = tmp_path / "o.pdf"
    combine.from_images(list(pics), out, paper="A4", margin=10)
    assert sizes(out) == [(842, 595), (595, 842)]  # (cada una como está su imagen)
    bbox = pymupdf.Rect(pymupdf.open(out)[0].get_image_info()[0]["bbox"])
    assert abs(bbox.x0 - 28.35) < 0.5 and abs(bbox.x1 - (842 - 28.35)) < 0.5  # (as wide as fits)
    combine.from_images(list(pics), out, paper="Letter", landscape=False)
    assert sizes(out) == [(612, 792), (612, 792)]


def test_turned_photograph(tmp_path):
    out = tmp_path / "o.pdf"
    combine.from_images([turned_photo(tmp_path / "phone.jpg", 400, 200)], out)
    assert sizes(out) == [(150, 300)]


def test_what_is_not_a_picture(pics, tmp_path):
    (tmp_path / "x.png").write_text("no")
    with pytest.raises(CombineError):
        combine.from_images([tmp_path / "x.png"], tmp_path / "o.pdf")
    with pytest.raises(CombineError):
        combine.from_images([], tmp_path / "o.pdf")
    with pytest.raises(CombineError):
        combine.from_images([pics[0]], tmp_path / "o.pdf", paper="A5", margin=80)


def test_command_line(pics, tmp_path):
    from py_pdftools.cli import main

    out = tmp_path / "c.pdf"
    assert main(["from-images", str(pics[1]), str(pics[0]), "-o", str(out), "--paper", "A4", "--landscape"]) == 0
    assert sizes(out) == [(842, 595), (842, 595)]


def test_in_the_window(pics, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from py_pdftools.gui.combine_dialog import ImagesDialog
    from py_pdftools.gui.window import MainWindow

    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    w = MainWindow()
    w.ask_recover = lambda when: False
    try:
        d = ImagesDialog(w)
        assert not d.b_ok.isEnabled()
        d.add_paths([pics[1], pics[0]])
        d.sort_by_name()
        assert [p.name for p in d.paths()] == ["tall.jpg", "wide.png"]
        d.paper.setCurrentIndex(d.paper.findData("A4"))
        assert d.orientation.isEnabled()
        out = tmp_path / "o.pdf"
        w.ask_images = lambda: (d.paths(), d.options(), True)
        w.ask_new_pdf = lambda title, name: out
        made = w.images_dialog()
        assert made is w and w.path == out and w.count == 2  # (no document here: opened here)
        assert w.mode == "ocr"
        assert sizes(out) == [(595, 842), (842, 595)]
    finally:
        w.close()
