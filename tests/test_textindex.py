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
