"""Un índice del texto de un documento, para buscar mientras se escribe (la barra Buscar mientras se escribe).

El texto de cada página se lee una sola vez y se guarda también sin acentos y en minúsculas (y, si se piden los
acentos, en minúsculas con ellos), así que buscar es solo str.find sobre cadenas ya preparadas. Si el texto buscado continúa el anterior («scri», luego «scrib»),
solo se busca en las páginas donde estaba el anterior. Un lugar encontrado es solo (página, inicio, fin): sus
rectángulos se calculan cuando hace falta mostrarlo, y solo para las páginas que se ven.

La lectura sigue las reglas de search.page_chars (una palabra cortada con guion al final de la línea es una
sola, los espacios seguidos son uno), pero guarda la caja de cada carácter como una tupla, sin girarla: el
giro de la página se aplica después, a los rectángulos de lo que se muestra. Así una página densa se lee en
unos 3 ms en lugar de 16. Aquí no hay nada de Qt."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import NamedTuple

import pymupdf

from .search import HYPHENS, LIGATURES, QUOTES, Match
from .search import fold as _fold_text

FLAGS = pymupdf.TEXTFLAGS_SEARCH & ~pymupdf.TEXT_PRESERVE_IMAGES
_FOLDED: dict[str, str] = {}  # (each character without its accents, worked out once)


class Hit(NamedTuple):
    """A place found: its page (0-based) and where it is in the page's text."""
    page: int
    start: int
    end: int


def _fold(text: str) -> tuple[str, list[int]]:
    """TEXT without accents nor ligatures (as search.fold), with each character's place in TEXT; quicker, since
    each different character is folded only once."""
    out, index = [], []
    for i, c in enumerate(text):
        f = _FOLDED.get(c)
        if f is None:
            # (y las comillas tipográficas, rectas: "x" halla “x”, don't halla don’t)
            f = _FOLDED[c] = (LIGATURES.get(c) or _fold_text(c)[0]).translate(QUOTES)
        out.append(f)
        if len(f) == 1:
            index.append(i)
        else:
            index.extend([i] * len(f))
    return "".join(out), index


def read_page(page: pymupdf.Page) -> tuple[str, list]:
    """The text of PAGE and, for each character, (block, line, x0, y0, x1, y1) unturned, or None for a space
    put between two lines (as search.page_chars, which gives the boxes turned)."""
    text: list[str] = []
    where: list = []
    raw = page.get_text("rawdict", flags=FLAGS)
    for b, block in enumerate(raw.get("blocks", ())):
        for n, line in enumerate(block.get("lines", ())):
            first = True
            for span in line.get("spans", ()):
                for ch in span.get("chars", ()):
                    c = ch["c"]
                    if c.isspace():
                        if not text or text[-1] == " ":
                            continue
                        c = " "
                    elif first:
                        first = False
                        if text:
                            # (al empezar una línea: fuera el guion si la palabra sigue en minúscula; si no, un espacio)
                            if (text[-1] in HYPHENS and len(text) > 1 and text[-2].isalpha() and c.isalpha()
                                    and c.islower()):
                                text.pop()
                                where.pop()
                            elif text[-1] != " ":
                                text.append(" ")
                                where.append(None)
                    text.append(c)
                    x0, y0, x1, y1 = ch["bbox"]
                    where.append((b, n, x0, y0, x1, y1))
    return "".join(text), where


class _Page:
    __slots__ = ("text", "where", "folded", "index", "lower", "matrix", "_text_lower", "_quoted")

    def __init__(self, page: pymupdf.Page):
        self.text, self.where = read_page(page)
        self.folded, self.index = _fold(self.text)
        lower = self.folded.lower()
        # (casi siempre del mismo largo; si no, como con 'İ', se busca sin distinguir mayúsculas con re)
        self.lower = lower if len(lower) == len(self.folded) else None
        self.matrix = page.rotation_matrix if page.rotation else None
        self._text_lower: str | None = ""  # (hecho la primera vez que se buscan acentos sin mayúsculas)
        self._quoted = ""  # (the same: see quoted)

    def quoted(self) -> str:
        """The text with its accents, its typographic quotes made straight (one character for one: the places
        don't change)."""
        if not self._quoted and self.text:
            self._quoted = self.text.translate(QUOTES)
        return self._quoted

    def text_lower(self) -> str | None:
        """The text with its accents (its quotes straight), in lower case (None if that changes its length)."""
        if self._text_lower == "":
            lower = self.quoted().lower()
            self._text_lower = lower if len(lower) == len(self.text) else None
        return self._text_lower


def prepare(query: str, case: bool, accents: bool = False) -> str:
    """QUERY as the index searches it: its spaces one space, without accents (if not ACCENTS), in lower case (if
    not CASE)."""
    q = " ".join(query.split()).translate(QUOTES)
    if not accents:
        q = _fold(q)[0]
    return q if case else q.lower()


class TextIndex:
    """The text of every page of DOC, read when first needed (or ahead, with read_some)."""

    def __init__(self, doc: pymupdf.Document):
        self.doc = doc
        self.pages: dict[int, _Page] = {}
        self.last: tuple[str, bool, bool, frozenset[int]] | None = None  # (the last search done whole, its pages)

    def page(self, number: int) -> _Page:
        p = self.pages.get(number)
        if p is None:
            p = self.pages[number] = _Page(self.doc[number])
        return p

    def complete(self) -> bool:
        return len(self.pages) >= self.doc.page_count

    def read_some(self, n: int = 10) -> bool:
        """Read N more pages ahead; False when every page has been read."""
        for number in range(self.doc.page_count):
            if number not in self.pages:
                if n <= 0:
                    return True
                self.page(number)
                n -= 1
        return False

    def read_some_for(self, until: float) -> bool:
        """Read pages ahead until the clock (time.perf_counter) says UNTIL, one at least; False when every page
        has been read."""
        import time

        for number in range(self.doc.page_count):
            if number not in self.pages:
                self.page(number)
                if time.perf_counter() >= until:
                    return not self.complete()
        return False

    def search(self, query: str, case: bool = False, start: int = 0,
               progress: Callable[[int, int, list[Hit]], bool] | None = None, accents: bool = False) -> list[Hit]:
        """Where QUERY is, in the order of the pages, looking first from page START to the end and then from
        the beginning; capitals are minded only with CASE, accents only with ACCENTS. PROGRESS(pages done, pages in all, hits
        so far) is called after each page read for the first time: if it returns False, the search stops."""
        q = prepare(query, case, accents)
        n = self.doc.page_count
        if not q or not n:
            return []
        order = list(range(start, n)) + list(range(0, start))
        # Si el texto continúa el anterior, solo puede estar donde estaba aquel
        if self.last is not None and self.last[1:3] == (case, accents) and q.startswith(self.last[0]):
            hits = self.last[3]
            order = [p for p in order if p in hits]
        found: list[Hit] = []
        for done, number in enumerate(order, 1):
            fresh = number not in self.pages
            found.extend(self._find(self.page(number), number, q, case, accents))
            if fresh and progress is not None and progress(done, len(order), found) is False:
                return sorted(found)  # (sin terminar: no sirve para acotar la búsqueda siguiente)
        self.last = (q, case, accents, frozenset(h.page for h in found))
        return sorted(found)

    @staticmethod
    def _find(page: _Page, number: int, q: str, case: bool, accents: bool) -> list[Hit]:
        if accents:  # (el texto tal como está, con sus acentos: sus posiciones son las del texto)
            index = None
            hay = page.quoted() if case else page.text_lower()
            plain = page.quoted()
        else:
            index = page.index
            hay = page.folded if case else page.lower
            plain = page.folded
        if hay is None:  # (minúsculas de otro largo, como con 'İ': se compara con re, sin distinguirlas)
            spans = [m.span() for m in re.finditer(re.escape(q), plain, re.IGNORECASE)]
        else:
            spans, size = [], len(q)
            at = hay.find(q)
            while at >= 0:
                spans.append((at, at + size))
                at = hay.find(q, at + size)
        if index is None:
            return [Hit(number, s, e) for s, e in spans]
        return [Hit(number, index[s], index[e - 1] + 1) for s, e in spans]

    def query(self, query: str, case: bool = False, accents: bool = False) -> tuple[str, bool, bool]:
        """QUERY prepared once (see prepare), with its options: what page_hits and next_hit take."""
        return prepare(query, case, accents), case, accents

    def candidates(self, q: tuple[str, bool, bool]) -> frozenset[int] | None:
        """The only pages where Q can be, if a search done whole before says so (None: any page)."""
        last = self.last
        if last is not None and last[1:3] == q[1:] and q[0].startswith(last[0]):
            return last[3]
        return None

    def page_hits(self, number: int, q: tuple[str, bool, bool]) -> list[Hit]:
        """The places of Q on page NUMBER (read now if it wasn't)."""
        return self._find(self.page(number), number, *q) if q[0] else []

    def next_hit(self, q: tuple[str, bool, bool], page: int, at: int, by: int = 1,
                 stop: Callable[[], bool] | None = None) -> Hit | None:
        """The first place of Q after the character AT of PAGE (BY 1), or the last one before it (BY -1),
        going round the document; it reads only the pages it must, and stops at the first place it finds.
        STOP, if given, is asked after each page read for the first time: True ends the search (None)."""
        n = self.doc.page_count
        if not q[0] or not n:
            return None
        only = self.candidates(q)
        for k in range(n + 1):  # (n + 1: la misma página otra vez, por su otra parte, al dar la vuelta)
            number = (page + by * k) % n
            if only is not None and number not in only:
                continue
            fresh = number not in self.pages
            hits = self.page_hits(number, q)
            if k == 0:
                hits = [h for h in hits if (h.start >= at if by > 0 else h.start < at)]
            elif k == n:
                hits = [h for h in hits if (h.start < at if by > 0 else h.start >= at)]
            if hits:
                return hits[0] if by > 0 else hits[-1]
            if fresh and stop is not None and stop():
                return None
        return None

    def finished(self, q: tuple[str, bool, bool], pages_hit: set[int]):
        """A search of Q was done over every page: kept, so that the next one, if it goes on from Q, looks
        only at PAGES_HIT."""
        self.last = (q[0], q[1], q[2], frozenset(pages_hit))

    def rects(self, hit: Hit) -> tuple[tuple[float, float, float, float], ...]:
        """The rectangles of HIT on its page as it is shown: one for each line it is on."""
        page = self.page(hit.page)
        text, where = page.text, page.where
        lines: dict[tuple[int, int], list[float]] = {}
        for i in range(hit.start, hit.end):
            w = where[i]
            if w is None or text[i] == " ":
                continue
            b, n, x0, y0, x1, y1 = w
            r = lines.get((b, n))
            if r is None:
                lines[(b, n)] = [x0, y0, x1, y1]
            else:
                r[0], r[1], r[2], r[3] = min(r[0], x0), min(r[1], y0), max(r[2], x1), max(r[3], y1)
        out = []
        for x0, y0, x1, y1 in lines.values():
            if page.matrix is not None:
                rr = (pymupdf.Rect(x0, y0, x1, y1) * page.matrix).normalize()
                x0, y0, x1, y1 = rr.x0, rr.y0, rr.x1, rr.y1
            out.append((round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)))
        return tuple(out)

    def match(self, hit: Hit) -> Match:
        """HIT as search.Match (its rectangles and its text; no context)."""
        page = self.page(hit.page)
        return Match(hit.page, self.rects(hit), page.text[hit.start:hit.end].strip(), "")
