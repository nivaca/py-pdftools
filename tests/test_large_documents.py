"""Documentos largos en la ventana: lo que se hace a cada desplazamiento o cambio de tamaño no puede
recorrer todas las páginas (ni, peor, recorrerlas una vez por página). Se comprueba que los atajos dan lo
mismo que el cálculo largo, y que este no se hace."""

from __future__ import annotations

import pymupdf
import pytest
from PySide6.QtWidgets import QApplication

from py_pdftools.gui.window import MainWindow

PAGES = 600


@pytest.fixture(scope="module")
def long_pdf(tmp_path_factory):
    path = tmp_path_factory.mktemp("long") / "long.pdf"
    doc = pymupdf.open()
    for i in range(PAGES):
        # (some pages lying, so that the rows are of different widths)
        page = doc.new_page(width=842 if i % 97 == 5 else 595, height=595 if i % 97 == 5 else 842)
        page.insert_text((72, 72), f"Page {i + 1}")
    doc.save(path)
    return path


@pytest.fixture
def window(long_pdf):
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.ask_recover = lambda when: False
    w.resize(1200, 800)
    assert w.open_path(long_pdf)
    yield w
    w.close()


def test_rows_worked_out(window):
    """row_of and neighbour, worked out, give what searching rows() gives, with or without spread and cover,
    for every count of pages (odd and even, one alone)."""
    canvas = window.canvas
    for count in (1, 2, 3, 4, 7):
        canvas.doc = pymupdf.open()
        for _ in range(count):
            canvas.doc.new_page()
        for spread, cover in ((False, False), (True, False), (True, True)):
            canvas.spread, canvas.cover = spread, cover
            rows = canvas.rows()
            assert canvas._row_count() == len(rows)
            for page in range(count):
                k = next(k for k, row in enumerate(rows) if page in row)
                assert canvas.row_of(page) == rows[k], (count, spread, cover, page)
                for step in (-2, -1, 0, 1, 2):
                    assert canvas.neighbour(page, step) == rows[max(0, min(k + step, len(rows) - 1))][0]
            assert canvas.row_of(count + 3) == [count + 3]  # (a page no longer there: alone)


def test_fitting_goes_through_the_rows_once(window, monkeypatch):
    """Fitting (at each resize of the window) makes the rows once, and asks MuPDF for no page's size."""
    canvas = window.canvas
    canvas.fit = "width"
    made = []
    rows = canvas.rows
    monkeypatch.setattr(canvas, "rows", lambda: made.append(1) or rows())
    asked = []
    page_rect = canvas.page_rect
    monkeypatch.setattr(canvas, "page_rect", lambda n: asked.append(n) or page_rect(n))
    canvas.apply_fit()
    assert len(made) <= 1 and len(asked) <= 2
    # (the widest row is a page lying down: the width fits it, as before)
    assert abs(canvas.zoom() - (canvas.viewport().width() - 4) / (842 + 2 * canvas.gap)) < 1e-6
    canvas.set_spread(True)
    made.clear()
    canvas.apply_fit()
    assert len(made) <= 1


def _page_in_view_slowly(canvas) -> int:
    # (lo que _scrolled hacía antes: recorrer todas las páginas)
    middle = canvas.mapToScene(canvas.viewport().rect().center()).y()

    def far(p):
        r = p.sceneBoundingRect()
        return 0 if r.top() <= middle <= r.bottom() else min(abs(r.top() - middle), abs(r.bottom() - middle))

    return min(canvas.pages.values(), key=far).number


def test_scrolling_finds_the_page_by_bisection(window, monkeypatch):
    """The page in view, and those to draw, are found among the rows near the view only: the same as going
    through every page, with one page or two in a row, turned or not, with gaps or without."""
    canvas = window.canvas
    window.show()
    bar = canvas.verticalScrollBar()
    for spread, turn, gaps in ((False, 0, True), (True, 0, True), (False, 90, True), (True, 0, False)):
        canvas.set_spread(spread)
        canvas.set_turn(turn)
        canvas.set_gaps(gaps)
        canvas.set_zoom(0.4)
        for i in range(0, 101, 7):
            bar.setValue(bar.maximum() * i // 100)
            assert canvas.page == _page_in_view_slowly(canvas), (spread, turn, gaps, i)
            view = canvas.mapToScene(canvas.viewport().rect()).boundingRect()
            view = view.adjusted(0, -view.height() / 2, 0, view.height() / 2)
            slow = {n for n, p in canvas.pages.items() if p.sceneBoundingRect().intersects(view)}
            assert set(canvas.visible_pages()) == slow
    # (and few pages are looked at: those of the rows about the middle, not all of them)
    looked = []
    real = type(canvas.pages[0]).sceneBoundingRect
    monkeypatch.setattr(type(canvas.pages[0]), "sceneBoundingRect", lambda self: looked.append(1) or real(self))
    canvas._scrolled(0)
    assert 0 < len(looked) < 40


def test_pages_get_their_pictures_when_drawn(window, monkeypatch):
    """Laying out asks MuPDF for each page's size once, and a page gets the items of its rendering and its
    tiles only when it is drawn: under the tiles, and both under the annotations."""
    canvas = window.canvas
    asked = []
    page_rect = canvas.page_rect
    monkeypatch.setattr(canvas, "page_rect", lambda n: asked.append(n) or page_rect(n))
    canvas.set_turn(90)
    assert sorted(asked) == list(range(PAGES))  # (once each, turned as they are)
    canvas.set_turn(0)
    far = canvas.pages[PAGES - 1]
    assert far._pixmap is None and far._tiles_layer is None and far.shows_nothing()
    window.show()
    canvas._render_visible()
    canvas.local_timer.timeout.emit()
    QApplication.processEvents()
    first = canvas.pages[canvas.page]
    assert first._pixmap is not None
    assert first.tiles_layer.zValue() > first.pixmap.zValue() and first.tiles_layer.zValue() < 1
    assert far._pixmap is None  # (still: it was never in view)
