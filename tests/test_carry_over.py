"""La huella de las páginas (core/pageprint.py) y lo que la ventana hace con ella: tras un cambio del documento,
una deshecha o un guardado, las páginas que el cambio no tocó se muestran con su dibujo de antes, sin dibujarlas
otra vez; las que cambió, sí se dibujan."""

from __future__ import annotations

import time
import traceback

import pikepdf
import pymupdf
import pytest
from PySide6.QtWidgets import QApplication

from py_pdftools.core.pageprint import Prints
from py_pdftools.gui import canvas as canvas_module
from py_pdftools.gui import window as window_module
from py_pdftools.pages import arrange

PAGE_IMAGE = canvas_module.page_image


@pytest.fixture
def pdf(tmp_path):
    path = tmp_path / "d.pdf"
    doc = pymupdf.open()
    for n in range(4):
        page = doc.new_page(width=300, height=400)
        page.insert_text((40, 60), f"Page {n + 1}", fontsize=24)
        page.draw_rect((40, 100, 200, 200), color=(0, 0, 1), fill=(1, 1, 0))
    doc.save(path)
    return path


def prints(path) -> list[bytes]:
    doc = pymupdf.open(path)
    p = Prints(doc)
    return [p.page(n) for n in range(len(doc))]


def test_a_fingerprint_follows_what_is_drawn(pdf, tmp_path):
    before = prints(pdf)
    assert len(set(before)) == 4  # (each page its own)
    # pikepdf numbers every object anew, and may write the keys of a dictionary in another order: same prints
    with pikepdf.open(pdf) as doc:
        doc.save(tmp_path / "same.pdf", compress_streams=True)
    assert prints(tmp_path / "same.pdf") == before
    # Pages moved: each keeps its own
    with pikepdf.open(pdf) as doc:
        doc.pages.reverse()
        doc.save(tmp_path / "moved.pdf")
    assert prints(tmp_path / "moved.pdf") == before[::-1]
    # Labels and bookmarks change nothing drawn; a word more on page 2, a turn of page 3 and a box of page 4 do
    doc = pymupdf.open(pdf)
    doc.set_page_labels([{"startpage": 0, "prefix": "A-", "style": "D"}])
    doc.set_toc([[1, "Start", 1]])
    doc[1].insert_text((40, 300), "more")
    doc[2].set_rotation(90)
    doc[3].set_cropbox(pymupdf.Rect(0, 0, 300, 300))
    doc.save(tmp_path / "changed.pdf")
    after = prints(tmp_path / "changed.pdf")
    assert [a == b for a, b in zip(after, before)] == [True, False, False, False]


def test_an_annotation_changes_the_print_of_its_page(pdf, tmp_path):
    doc = pymupdf.open(pdf)
    doc[0].add_rect_annot(pymupdf.Rect(10, 10, 50, 50))
    doc.save(tmp_path / "annotated.pdf")
    before, after = prints(pdf), prints(tmp_path / "annotated.pdf")
    assert after[0] != before[0] and after[1:] == before[1:]


@pytest.fixture
def window(pdf, tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    drawn, why, mine = [], [], []  # (mine: this test's window, once it is made)

    def counted(page, scale, *args, **kwargs):
        # Solo las páginas de esta ventana: una ventana de una prueba anterior, cerrada pero aún no destruida,
        # puede tener temporizadores pendientes que dibujan las suyas (en un equipo ocupado, durante esta).
        if not mine or page.parent is not mine[0].doc:
            return PAGE_IMAGE(page, scale, *args, **kwargs)
        drawn.append(page.number)
        # (who drew it, for the message of a test that fails)
        why.append(" < ".join(f.name for f in traceback.extract_stack()[-6:-1]))
        return PAGE_IMAGE(page, scale, *args, **kwargs)

    monkeypatch.setattr(canvas_module, "page_image", counted)
    monkeypatch.setattr(window_module, "page_image", counted)
    w = window_module.MainWindow()
    mine.append(w)
    w.ask_recover = lambda when: False
    w.labels_choice = lambda: arrange.FOLLOW
    w.resize(1100, 900)
    w.show()
    assert w.open_path(pdf)
    w.canvas.set_zoom(0.5)  # (the four pages in view)
    w.drawn, w.why = drawn, why
    w.idle = lambda: _idle(app, w)
    w.idle()
    yield w
    w.annotations = w.saved = []
    w.drop_work()
    w.close()


def _idle(app, w, seconds: float = 20.0):
    deadline, quiet = time.time() + seconds, 0
    while time.time() < deadline and quiet < 20:
        app.processEvents()
        # (not only the timers: until every page in view is drawn, and every thumbnail near them made)
        busy = w.canvas._here or w.canvas.local_timer.isActive() or w.thumb_timer.isActive() or \
            w.canvas.render_timer.isActive() or \
            any(w.canvas.pages[n].scale_shown == 0 for n in w.canvas.visible_pages(0)) or \
            any(n not in w._thumbs for n in w._thumb_rows())
        quiet = 0 if busy else quiet + 1
        time.sleep(0.005)


def test_a_change_draws_only_the_pages_it_changed(window):
    w = window
    assert sorted(set(w.drawn)) == [0, 1, 2, 3]  # (pages and thumbnails, all drawn once at first)
    # Labels: nothing to draw again, neither the pages nor their thumbnails
    w.drawn.clear()
    assert w.edit_document(lambda doc: doc.set_page_labels([{"startpage": 0, "prefix": "A-", "style": "D"}]))
    w.idle()
    assert w.drawn == [] and all(not item.shows_nothing() for item in w.canvas.pages.values())
    # Page 2 turned: only it, page and thumbnail
    assert w.arrange_pages(arrange.Rotate((2,), 90))
    w.idle()
    assert sorted(w.drawn) == [1, 1]
    # Pages moved: each keeps its picture, wherever it went
    w.drawn.clear()
    assert w.arrange_pages(arrange.Move((4,), 1))
    w.idle()
    assert w.drawn == []
    # Undone twice, back to pages whose pictures are still kept: nothing drawn
    w.undo()
    w.undo()
    w.idle()
    assert w.drawn == [] and w.doc[1].rotation == 0


def test_saving_draws_nothing_again(window, pdf):
    w = window
    assert w.edit_document(lambda doc: doc.set_toc([[1, "Start", 1]]))
    w.idle()
    w.drawn.clear()
    w.why.clear()
    assert w.save()
    w.idle()
    assert w.drawn == [], w.why


def test_other_settings_of_drawing_draw_again(window):
    """The pictures kept are of the colours and sharpness they were drawn with: other ones forget them."""
    w = window
    w.redraw_pages()
    w.idle()
    w.drawn.clear()
    assert w.edit_document(lambda doc: doc.set_toc([[1, "Start", 1]]))
    w.idle()
    assert w.drawn == []  # (those drawn after redraw_pages are kept)
    w.redraw_pages()
    w.idle()
    assert sorted(set(w.drawn)) == [0, 1, 2, 3]
