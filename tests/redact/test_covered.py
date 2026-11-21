"""Text only covered (redact/covered.py): text drawn over by a box, a picture or an annotation is found, with
what covers it; what is drawn before the text (a background), what lets it show (a transparent fill, a
yellow highlight), and text that is not covered, are not. In the window, boxes put over what is found take
the text out of the redacted copy."""

from __future__ import annotations

import pymupdf
import pytest

from py_pdftools.redact import covered


def page_with(*texts):
    doc = pymupdf.open()
    page = doc.new_page()
    for y, text in texts:
        page.insert_text((72, y), text, fontsize=12)
    return doc, page


def bar(y):  # (the rectangle over a line of text written at height Y)
    return pymupdf.Rect(70, y - 12, 220, y + 4)


def centre(page, text):
    """The middle of TEXT on PAGE, as the page is shown (as the boxes are)."""
    r = (page.search_for(text)[0] * page.rotation_matrix).normalize()
    return pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)


def texts(doc):
    return [(c.kind, c.text) for c in covered.find(doc)]


def test_a_black_box_over_text():
    doc, page = page_with((100, "Secret name here"), (200, "Seen"))
    page.draw_rect(bar(100), color=None, fill=(0, 0, 0))
    found = covered.find(doc)
    assert [(c.kind, c.text) for c in found] == [("shape", "Secret name here")]
    # el lugar encontrado es el del texto, y una búsqueda encuentra ahí el texto
    assert pymupdf.Rect(found[0].rect).contains(centre(page, "Secret"))


def test_white_box_and_picture_and_annotation():
    doc, page = page_with((100, "Under white"), (200, "Under picture"), (300, "Under note"))
    page.draw_rect(bar(100), color=None, fill=(1, 1, 1))
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 30, 4), 0)
    pix.clear_with(0)
    page.insert_image(bar(200), pixmap=pix, keep_proportion=False)
    annot = page.add_rect_annot(bar(300))
    annot.set_colors(stroke=(0, 0, 0), fill=(0, 0, 0))
    annot.update()
    assert texts(doc) == [("shape", "Under white"), ("image", "Under picture"), ("annotation", "Under note")]


def test_what_does_not_hide_the_text():
    doc, page = page_with()
    page.draw_rect(bar(100), color=None, fill=(0, 0, 0))  # (antes del texto: un fondo)
    page.insert_text((72, 100), "On a background", fontsize=12)
    page.insert_text((72, 200), "Half seen", fontsize=12)
    page.draw_rect(bar(200), color=None, fill=(0, 0, 0), fill_opacity=0.3)
    page.insert_text((72, 300), "Shaded", fontsize=12)
    page.draw_rect(bar(300), color=None, fill=(1, 0.9, 0.3))  # (un color: seguramente un resaltado)
    page.insert_text((72, 400), "Highlighted", fontsize=12)
    page.add_highlight_annot(bar(400))  # (yellow)
    page.insert_text((72, 500), "Outlined", fontsize=12)
    page.add_rect_annot(bar(500))  # (no fill)
    page.insert_text((72, 600), "Invisible OCR", fontsize=12, render_mode=3)
    page.draw_rect(bar(600), color=None, fill=(0, 0, 0))
    assert texts(doc) == []


def test_a_dark_highlight_hides():
    doc, page = page_with((100, "Blacked out"))
    h = page.add_highlight_annot(bar(100))
    h.set_colors(stroke=(0, 0, 0))
    h.update()
    assert texts(doc) == [("annotation", "Blacked out")]


@pytest.mark.parametrize("turn", [0, 90, 180, 270])
def test_turned_page(turn):
    doc, page = page_with((100, "Secret"))
    page.draw_rect(bar(100), color=None, fill=(0, 0, 0))
    page.set_rotation(turn)
    [c] = covered.find(doc)
    assert pymupdf.Rect(c.rect).contains(centre(page, "Secret"))


def test_from_a_file_with_pages(tmp_path):
    doc, page = page_with((100, "One"))
    page.draw_rect(bar(100), color=None, fill=(0, 0, 0))
    second = doc.new_page()
    second.insert_text((72, 100), "Two", fontsize=12)
    second.draw_rect(bar(100), color=None, fill=(0, 0, 0))
    doc.save(tmp_path / "c.pdf")
    assert [(c.page, c.text) for c in covered.find(tmp_path / "c.pdf")] == [(0, "One"), (1, "Two")]
    assert [c.page for c in covered.find(tmp_path / "c.pdf", pages=[1])] == [1]


def test_in_the_window(tmp_path, monkeypatch):
    """Found from the menu, boxes put over all, and the redacted copy has the text no more."""
    from PySide6.QtWidgets import QApplication

    from py_pdftools.gui.window import MainWindow
    from py_pdftools.redact.redact import box_of

    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    doc, page = page_with((100, "Secret name"), (300, "Kept text"))
    page.draw_rect(bar(100), color=None, fill=(0, 0, 0))
    doc.save(tmp_path / "fake.pdf")
    w = MainWindow()
    w.ask_recover = lambda when: False
    try:
        assert w.open_path(tmp_path / "fake.pdf")
        w.set_mode("redact")
        app.processEvents()
        found = w.find_covered()
        assert [c.text for c in found] == ["Secret name"]
        dialog = w.covered_dialog
        assert dialog.isVisible() and dialog.table.rowCount() == 1
        dialog.b_mark.click()
        boxes = [a for a in w.annotations if a.kind == "redact"]
        assert len(boxes) == 1
        dialog.b_mark.click()  # (no dos veces)
        assert len([a for a in w.annotations if a.kind == "redact"]) == 1
        out = tmp_path / "out.pdf"
        assert w.save_redacted(out, [box_of(b) for b in boxes])
        text = pymupdf.open(out)[0].get_text()
        assert "Secret" not in text and "Kept text" in text
        dialog.close()
    finally:
        w.annotations = w.saved = []
        w.close()


def test_nothing_found_in_the_window(tmp_path, monkeypatch, sample):
    from PySide6.QtWidgets import QApplication

    from py_pdftools.gui.window import MainWindow

    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    w = MainWindow()
    w.ask_recover = lambda when: False
    try:
        assert w.open_path(sample)
        assert w.find_covered() == []
        assert "No text is hidden" in w.statusBar().currentMessage()
    finally:
        w.close()
