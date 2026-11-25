"""Páginas convertidas en imágenes (pages/rasterize.py, Archivo > Guardar una copia > Con las páginas como
imágenes, py-pdftools rasterize): el texto desaparece de las páginas elegidas y de los bytes del archivo, el
aspecto no cambia (con el giro, la caja de recorte, las anotaciones y los campos), las demás páginas, los
marcadores y los enlaces se quedan, la protección se mantiene; y la ventana y la línea de órdenes."""

from __future__ import annotations

import pymupdf
import pytest

from py_pdftools.pages import rasterize
from py_pdftools.pages.rasterize import Options


@pytest.fixture
def sample(tmp_path):
    """Three pages with text and a drawing; the second turned; on the first a highlight, a note, a filled
    field and a link; a bookmark."""
    path = tmp_path / "sample.pdf"
    doc = pymupdf.open()
    for i in range(3):
        page = doc.new_page(width=400, height=300)
        page.insert_text((50, 100), f"Secret words {i + 1}", fontsize=20)
        page.draw_rect(pymupdf.Rect(10, 10, 60, 60), color=(1, 0, 0), fill=(0, 0, 1))
    doc[1].set_rotation(90)
    doc[0].add_highlight_annot(pymupdf.Rect(50, 80, 200, 105))
    doc[0].add_text_annot((300, 50), "a note")
    w = pymupdf.Widget()
    w.field_name, w.field_type = "name", pymupdf.PDF_WIDGET_TYPE_TEXT
    w.rect, w.field_value = pymupdf.Rect(50, 150, 250, 180), "field value"
    doc[0].add_widget(w)
    doc[0].insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(0, 0, 40, 40), "uri": "https://example.org"})
    doc.set_toc([[1, "Chapter", 1]])
    doc.save(path)
    return path


def every_byte(doc: pymupdf.Document) -> bytes:
    """The objects and the (decoded) streams of DOC."""
    out = []
    for x in range(1, doc.xref_length()):
        out.append(doc.xref_object(x).encode())
        if doc.xref_is_stream(x):
            out.append(doc.xref_stream(x) or b"")
    return b"".join(out)


def difference(a: pymupdf.Pixmap, b: pymupdf.Pixmap) -> float:
    assert (a.width, a.height) == (b.width, b.height)
    return sum(abs(x - y) for x, y in zip(a.samples, b.samples)) / len(a.samples)


@pytest.mark.parametrize("fmt", ["png", "jpg"])
def test_text_gone_looks_kept(sample, tmp_path, fmt):
    before = [p.get_pixmap(dpi=72, annots=True) for p in pymupdf.open(sample)]
    out = tmp_path / "out.pdf"
    assert rasterize.rasterize(sample, out, Options(150, fmt), [0, 1]) == 2
    doc = pymupdf.open(out)
    assert [p.get_text().strip() for p in doc] == ["", "", "Secret words 3"]
    assert [p.rotation for p in doc] == [0, 90, 0]
    assert [list(p.annots()) for p in doc[:2]] == [[], []] and not list(doc[0].widgets())
    assert doc[0].get_links()[0]["uri"] == "https://example.org"
    assert doc.get_toc() == [[1, "Chapter", 1]]
    assert not doc[0].get_fonts() and doc[2].get_fonts()
    data = every_byte(doc)
    assert b"words 1" not in data and b"words 2" not in data and b"field value" not in data
    assert b"words 3" in data
    for i, page in enumerate(doc):
        assert difference(before[i], page.get_pixmap(dpi=72, annots=True)) < 3


def test_cropped_page_and_grey(tmp_path):
    path = tmp_path / "crop.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=600)
    page.insert_text((250, 300), "cropped", fontsize=30, color=(1, 0, 0))
    page.draw_circle((300, 300), 100)
    page.set_cropbox(pymupdf.Rect(200, 200, 500, 450))
    doc.save(path)
    before = pymupdf.open(path)[0].get_pixmap(dpi=72, colorspace=pymupdf.csGRAY)
    out = tmp_path / "out.pdf"
    rasterize.rasterize(path, out, Options(144, gray=True))
    doc = pymupdf.open(out)
    assert doc[0].get_text() == "" and doc[0].rect == pymupdf.Rect(0, 0, 300, 250)
    info = doc[0].get_images()[0]
    assert (info[2], info[3]) == (600, 500) and pymupdf.Pixmap(doc, info[0]).n == 1
    assert difference(before, doc[0].get_pixmap(dpi=72, colorspace=pymupdf.csGRAY)) < 3


def test_huge_page_is_drawn_smaller(monkeypatch, tmp_path):
    monkeypatch.setattr(rasterize, "MAX_PIXELS", 1_000_000)
    path = tmp_path / "big.pdf"
    doc = pymupdf.open()
    doc.new_page(width=2000, height=2000).insert_text((100, 100), "big")
    doc.save(path)
    rasterize.rasterize(path, tmp_path / "out.pdf", Options(300))
    info = pymupdf.open(tmp_path / "out.pdf")[0].get_images()[0]
    assert info[2] * info[3] <= 1_000_000


def test_pages_written_protected_and_errors(sample, tmp_path):
    from py_pdftools.core import protection

    out = tmp_path / "out.pdf"
    assert rasterize.rasterize(sample, out, Options(72), "2-last") == 2
    assert [p.get_text().split("\n")[0] for p in pymupdf.open(out)] == ["Secret words 1", "", ""]
    with pytest.raises(rasterize.RasterizeError):
        rasterize.rasterize(sample, out, Options(72), "9")
    with pytest.raises(rasterize.RasterizeError):
        rasterize.rasterize(sample, out, Options(72), [5])
    locked = tmp_path / "locked.pdf"
    protection.protect(sample, locked, open_password="pw")
    rasterize.rasterize(locked, out, Options(72), None, "pw")
    doc = pymupdf.open(out)
    assert doc.needs_pass and doc.authenticate("pw") and doc[0].get_text() == ""
    with pytest.raises(rasterize.RasterizeError):
        rasterize.rasterize(locked, out, Options(72))
    # In place: what SOURCE was is replaced only when all went well.
    rasterize.rasterize(sample, sample, Options(72), [2])
    assert pymupdf.open(sample)[2].get_text() == ""


def test_command_line(sample, tmp_path):
    from py_pdftools.cli import main

    out = tmp_path / "c.pdf"
    assert main(["rasterize", str(sample), "-o", str(out), "--pages", "1,3", "--dpi", "100", "--format", "jpg"]) == 0
    doc = pymupdf.open(out)
    assert [p.get_text().strip() for p in doc] == ["", "Secret words 2", ""]
    assert doc[0].get_images()[0][2] == round(400 * 100 / 72)
    assert main(["rasterize", str(tmp_path / "missing.pdf"), "-o", str(out)]) == 1
    assert main(["rasterize", str(sample), "-o", str(out), "--pages", "7"]) == 1
    assert main(["rasterize", str(sample), "-o", str(out), "--dpi", "0"]) == 1


def test_in_the_window(sample, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from py_pdftools.gui.rasterize_dialog import RasterizeDialog
    from py_pdftools.gui.window import MainWindow

    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    w = MainWindow()
    w.ask_recover = lambda when: False
    try:
        assert w.open_path(sample)
        d = RasterizeDialog(3, 0)
        d.choice.setText("2-")
        d.format.setCurrentIndex(1)
        d.gray.setChecked(True)
        assert d.quality.isEnabled() and d.b_ok.isEnabled()
        assert d.values() == (Options(300, "jpg", 85, True), [1, 2])
        d.choice.setText("12")
        assert not d.b_ok.isEnabled() and d.problem.text()
        out = tmp_path / "o.pdf"
        w.ask_rasterize = lambda: (Options(72), [0])
        w.ask_new_pdf = lambda title, name: out
        opened = []
        monkeypatch.setattr("py_pdftools.gui.tabs.open_in_tab", lambda path, near=None: opened.append((path, near)))
        assert w.save_rasterized_dialog()
        assert pymupdf.open(out)[0].get_text() == "" and "1 page as a picture" in w.statusBar().currentMessage()
        assert opened == [(out, w)]  # (the copy, in a new tab beside the document)
        w.ask_new_pdf = lambda title, name: sample
        assert not w.save_rasterized_dialog() and len(opened) == 1  # (not over the document open)
    finally:
        w.close()
