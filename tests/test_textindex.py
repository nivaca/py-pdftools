"""El índice del texto (annotate/textindex.py): encuentra lo mismo que search.find_text, con y sin
mayúsculas y acentos, también en páginas giradas y con palabras cortadas al final de la línea, y acota la
búsqueda cuando el texto continúa el anterior."""

from __future__ import annotations

import pymupdf
import pytest

from py_pdftools.annotate.search import find_text
from py_pdftools.annotate.textindex import TextIndex


@pytest.fixture
def doc():
    d = pymupdf.open()
    for n in range(6):
        page = d.new_page()
        page.insert_text((72, 72), f"Page {n + 1}: the scribe copies the text.", fontname="helv")
        page.insert_text((72, 100), "Una canción, otra cancion, y la EDICIÓN de la obra.", fontname="helv")
        page.insert_text((72, 130), "a word cut at the end of the line: tran-", fontname="helv")
        page.insert_text((72, 144), "scription goes on", fontname="helv")
    d[2].set_rotation(90)
    d[4].set_rotation(270)
    return d


@pytest.mark.parametrize("query", ["scribe", "canción", "cancion", "edicion", "EDICIÓN", "transcription",
                                   "the text", "zzz", "a"])
@pytest.mark.parametrize("case", [False, True])
@pytest.mark.parametrize("accents", [False, True])
def test_as_find_text(doc, query, case, accents):
    ix = TextIndex(doc)
    old = [(m.page, m.rects, m.text) for m in find_text(doc, query, None, case=case, accents=not accents)]
    new = [(m.page, m.rects, m.text) for m in (ix.match(h) for h in ix.search(query, case, accents=accents))]
    assert new == old


def test_narrowing_and_order(doc):
    ix = TextIndex(doc)
    assert not ix.complete()
    while ix.read_some(2):
        pass
    assert ix.complete()
    assert len(ix.search("scrib")) == 6 and ix.last[3] == frozenset(range(6))
    assert [h.page for h in ix.search("scribe", start=4)] == list(range(6))  # (always in page order)
    # A text that goes on from the last one is looked for only where that one was (here made smaller by hand)
    ix.last = ("scrib", False, False, frozenset({1, 3}))
    assert {h.page for h in ix.search("scribe")} == {1, 3}
    assert len(ix.search("copies")) == 6  # (another text: every page again)


def test_progress_stops(doc):
    ix = TextIndex(doc)
    seen = []
    found = ix.search("scribe", progress=lambda done, total, hits: seen.append(done) or done < 2)
    assert seen == [1, 2] and len(found) == 2 and ix.last is None  # (unfinished: no narrowing from it)


def test_next_hit_stops_at_the_first(doc):
    ix = TextIndex(doc)
    q = ix.query("scribe")
    h = ix.next_hit(q, 3, 0)
    assert h.page == 3 and set(ix.pages) == {3}  # (only the page where it was found was read)
    h2 = ix.next_hit(q, h.page, h.start + 1)
    assert h2.page == 4 and set(ix.pages) == {3, 4}
    back = ix.next_hit(q, 0, 0, -1)
    assert back.page == 5  # (going back from the start goes round to the end)
    assert ix.next_hit(ix.query("zzz"), 0, 0) is None
    # A stop asked for ends the search
    ix2 = TextIndex(doc)
    assert ix2.next_hit(ix2.query("zzz"), 0, 0, stop=lambda: True) is None and len(ix2.pages) == 1


def test_find_text_with_the_index(doc):
    """find_text reading through a TextIndex finds exactly what it finds alone, and reads each page once for
    every search that shares the index."""
    ix = TextIndex(doc)
    for query, kw in (("scribe", {}), ("cancion", {"accents": True}), ("EDICIÓN", {"case": True}),
                      (r"tran\\w+", {"regex": True}), ("tran*", {"wildcards": True})):
        alone = [(m.page, m.rects, m.text, m.context) for m in find_text(doc, query, None, **kw)]
        shared = [(m.page, m.rects, m.text, m.context) for m in find_text(doc, query, None, cache=ix, **kw)]
        assert shared == alone, query
    assert ix.complete()


def test_one_index_for_every_search(tmp_path, monkeypatch):
    """The window keeps one index for the document shown, and Find as you type and Find all use it; another
    document, another index."""
    from PySide6.QtWidgets import QApplication

    from py_pdftools.gui.window import MainWindow

    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    d = pymupdf.open()
    for n in range(3):
        d.new_page().insert_text((72, 72), f"page {n} the scribe")
    d.save(tmp_path / "a.pdf")
    w = MainWindow()
    w.ask_recover = lambda when: False
    try:
        assert w.open_path(tmp_path / "a.pdf")
        ix = w.text_index()
        w.results_box.setText("scribe")
        assert w.list_results() == 3 and ix.complete()  # (read once, here)
        w.find_bar.open_bar()
        assert w.find_bar._index() is ix
        assert w.open_path(tmp_path / "a.pdf") and w.text_index() is not ix
    finally:
        w.find_bar.close_bar()
        w.drop_work()
        w.close()
