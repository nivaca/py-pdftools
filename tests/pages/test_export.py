"""Exports (pages/export.py, File > Export, py-pdftools export): the pages as PNG, JPEG and TIFF pictures, at
a resolution and in grey; the pictures of the document, with their transparency; the text as Markdown
(headings, lists, words cut at the end of a line), HTML and plain text; and the window and the command."""

from __future__ import annotations

import pymupdf
import pytest

from py_pdftools.pages import export


@pytest.fixture
def doc(tmp_path):
    d = pymupdf.open()
    p = d.new_page()
    p.insert_text((72, 80), "Chapter One", fontsize=24)
    p.insert_text((72, 120), "Body text of the first para-", fontsize=11)
    p.insert_text((72, 134), "graph goes on here.", fontsize=11)
    p.insert_text((72, 170), "A Section", fontsize=15)
    p.insert_text((72, 200), "• an item", fontsize=11)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 100), 1)
    pix.clear_with(120)
    p.insert_image(pymupdf.Rect(72, 300, 272, 400), pixmap=pix)
    tiny = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 8), 0)
    p.insert_image(pymupdf.Rect(300, 300, 308, 308), pixmap=tiny)
    d.new_page().insert_text((72, 80), "Page two", fontsize=11)
    d.set_page_labels([{"startpage": 0, "prefix": "", "style": "r", "firstpagenum": 1}])
    d.save(tmp_path / "doc.pdf")
    return tmp_path / "doc.pdf"


@pytest.mark.parametrize("fmt", export.PICTURE_FORMATS)
def test_pages_as_pictures(doc, tmp_path, fmt):
    made = export.export_pages(doc, tmp_path / "out", fmt=fmt, dpi=72)
    assert [p.name for p in made] == [f"doc-1-i.{fmt}", f"doc-2-ii.{fmt}"]
    pix = pymupdf.Pixmap(str(made[0]))
    assert (pix.width, pix.height) == (595, 842) and pix.xres == 72


def test_grey_and_some_pages(doc, tmp_path):
    [made] = export.export_pages(doc, tmp_path, [1], "tiff", dpi=144, gray=True)
    pix = pymupdf.Pixmap(str(made))
    assert pix.n == 1 and pix.width == 1190
    assert export.export_pages(doc, tmp_path, [0], "jpg", 50, quality=30)[0].read_bytes()[:3] == b"\xff\xd8\xff"


def test_pictures(doc, tmp_path):
    made = export.export_images(doc, tmp_path / "pics")
    assert [p.suffix for p in made] == [".png"]  # (with its mask: transparent; the tiny one left out)
    assert pymupdf.Pixmap(str(made[0])).alpha
    assert len(export.export_images(doc, tmp_path / "all", smallest=0)) == 2
    assert export.export_images(doc, tmp_path / "none", pages=[1]) == []


def test_text(doc, tmp_path):
    export.export_text(doc, tmp_path / "t.md")
    md = (tmp_path / "t.md").read_text()
    assert md.startswith("# Chapter One\n\nBody text of the first paragraph goes on here.")
    assert "\n## A Section\n" in md and "\n- an item\n" in md and md.rstrip().endswith("Page two")
    export.export_text(doc, tmp_path / "t.html")
    page = (tmp_path / "t.html").read_text()
    assert page.startswith("<!DOCTYPE html>") and 'id="page-2"' in page and "Chapter One" in page
    assert export.export_text(doc, tmp_path / "t.txt", pages=[1]) > 0
    assert (tmp_path / "t.txt").read_text().strip() == "Page two"


def test_command_line(doc, tmp_path):
    from py_pdftools.cli import main

    assert main(["export", "pages", str(doc), "-o", str(tmp_path / "p"), "--pages", "2", "--format", "jpg"]) == 0
    assert [p.suffix for p in (tmp_path / "p").iterdir()] == [".jpg"]
    assert main(["export", "text", str(doc), "-o", str(tmp_path / "t.md")]) == 0
    assert main(["export", "images", str(doc), "-o", str(tmp_path / "i")]) == 0
    assert main(["export", "pages", str(doc), "-o", str(tmp_path / "p"), "--pages", "9"]) == 1


def test_in_the_window(doc, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from py_pdftools.gui.export_dialog import ExportDialog
    from py_pdftools.gui.window import MainWindow

    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    d = ExportDialog("pages", 2, 0)
    d.choice.setText("5")
    assert not d.b_ok.isEnabled()
    d.choice.setText("2")
    d.format.setCurrentIndex(d.format.findData("tiff"))
    assert d.options() == {"pages": [1], "fmt": "tiff", "dpi": 150, "gray": False, "quality": 90}
    w = MainWindow()
    w.ask_recover = lambda when: False
    try:
        assert w.open_path(doc)
        w.ask_export = lambda kind: ({"pages": None, "fmt": "png", "dpi": 36, "gray": False, "quality": 90}
                                     if kind == "pages" else {"pages": None, "smallest": 32}, tmp_path / "x")
        assert len(w.export_pages_dialog()) == 2
        assert len(w.export_images_dialog()) == 1
        w.ask_text_target = lambda fmt: tmp_path / "x" / "t.html"
        assert w.export_text_dialog() == tmp_path / "x" / "t.html"
        asked = []
        w.ask_text_target = lambda fmt: asked.append(fmt) or tmp_path / "x" / "t.txt"
        w.a_export_text_txt.trigger()  # (File > Export > Text (plain, UTF-8): .txt at first)
        assert asked == ["txt"] and "\f" in (tmp_path / "x" / "t.txt").read_text(encoding="utf-8")
    finally:
        w.close()
