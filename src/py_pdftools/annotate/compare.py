"""Comparing two versions of a document: their words, in reading order, are lined up (difflib),
and what differs is told as places of this document, to be marked there (see the window's
compare_dialog): words changed, words only here, words only in the other version.

Nothing here uses Qt.
"""

from __future__ import annotations

import dataclasses
import difflib

import pymupdf

from . import annots
from .annots import Rect


@dataclasses.dataclass(frozen=True)
class Difference:
    kind: str  # 'changed' (words here that are others there), 'only_here', 'only_there'
    page: int  # of this document
    rects: tuple[Rect, ...]  # the lines of the words here; for 'only_there', the place where they would go
    here: str  # the words of this document
    there: str  # the words of the other one
    there_page: int  # where they are in the other one (-1 if nowhere)


def words(doc: pymupdf.Document) -> list[tuple[int, Rect, str]]:
    """The words of DOC, page after page, in reading order: (page, its rectangle as the page is
    shown, the word)."""
    return [(page.number, rect, text) for page in doc for rect, text in annots.page_text(page)]


def _lines(found: list[tuple[int, Rect, str]]) -> dict[int, list[Rect]]:
    """The rectangles of the lines that FOUND (words, in order) are on, page by page."""
    out: dict[int, list[Rect]] = {}
    # The words come in reading order, so a word is only joined to the last line found on its page.
    for page, (x0, y0, x1, y1), _ in found:
        lines = out.setdefault(page, [])
        if lines:
            a0, b0, a1, b1 = lines[-1]
            if abs((y0 + y1) / 2 - (b0 + b1) / 2) < (b1 - b0) / 2 and x0 >= a0 - 1:  # (the same line, further on)
                lines[-1] = (a0, min(b0, y0), max(a1, x1), max(b1, y1))
                continue
        lines.append((x0, y0, x1, y1))
    return out


SMALL = 3000  # (words: a stretch this short is compared word by word, exactly)


def opcodes(a: list[str], b: list[str]) -> list[tuple[str, int, int, int, int]]:
    """How A becomes B, as difflib's opcodes ('equal', 'replace', 'delete', 'insert', with the
    stretches of A and B), found as a patience diff: the words both begin and end with are set
    aside (as PdfCraft does); the words found once in each are lined up in order, as anchors; and
    the stretches between them are compared word by word. Long texts, of the same words again and
    again, are so compared quickly, and exactly."""
    out: list[tuple[str, int, int, int, int]] = []

    def add(op, i1, i2, j1, j2):
        if i1 == i2 and j1 == j2:
            return
        # Las operaciones seguidas del mismo tipo se funden, para no partir un cambio en pedazos.
        if out and out[-1][0] == op and out[-1][2] == i1 and out[-1][4] == j1:
            out[-1] = (op, out[-1][1], i2, out[-1][3], j2)
        else:
            out.append((op, i1, i2, j1, j2))

    def diff(i1, i2, j1, j2):
        # Se apartan el principio y el final comunes antes de comparar: suelen ser casi todo el texto.
        start = 0
        while i1 + start < i2 and j1 + start < j2 and a[i1 + start] == b[j1 + start]:
            start += 1
        add("equal", i1, i1 + start, j1, j1 + start)
        end = 0
        while i2 - end > i1 + start and j2 - end > j1 + start and a[i2 - 1 - end] == b[j2 - 1 - end]:
            end += 1
        x1, x2, y1, y2 = i1 + start, i2 - end, j1 + start, j2 - end
        # SequenceMatcher es cuadrático: se usa directamente en tramos cortos, o cuando un lado está vacío.
        if x2 - x1 <= SMALL and y2 - y1 <= SMALL or not (x1 < x2 and y1 < y2):
            for op, p1, p2, q1, q2 in difflib.SequenceMatcher(None, a[x1:x2], b[y1:y2], autojunk=False).get_opcodes():
                add(op, x1 + p1, x1 + p2, y1 + q1, y1 + q2)
        else:
            anchors = _anchors(a, x1, x2, b, y1, y2)
            if not anchors:  # (nothing found once in each: difflib's own way, fast and nearly right)
                for op, p1, p2, q1, q2 in difflib.SequenceMatcher(None, a[x1:x2], b[y1:y2]).get_opcodes():
                    add(op, x1 + p1, x1 + p2, y1 + q1, y1 + q2)
            else:
                # Each anchor is equal in both texts; the stretches between anchors are compared on their own.
                pi, pj = x1, y1
                for i, j in anchors:
                    diff(pi, i, pj, j)
                    add("equal", i, i + 1, j, j + 1)
                    pi, pj = i + 1, j + 1
                diff(pi, x2, pj, y2)
        add("equal", i2 - end, i2, j2 - end, j2)

    diff(0, len(a), 0, len(b))
    return out


def _anchors(a, x1, x2, b, y1, y2) -> list[tuple[int, int]]:
    """The words found once in A[x1:x2] and once in B[y1:y2], as pairs of places, the longest run of
    them in the same order in both."""
    # -1 marca una palabra repetida: solo las que aparecen una vez en cada lado sirven de ancla.
    once_a: dict[str, int] = {}
    for i in range(x1, x2):
        once_a[a[i]] = -1 if a[i] in once_a else i
    once_b: dict[str, int] = {}
    for j in range(y1, y2):
        once_b[b[j]] = -1 if b[j] in once_b else j
    pairs = sorted((i, once_b[w]) for w, i in once_a.items() if i >= 0 and once_b.get(w, -1) >= 0)
    # (the longest increasing run of the places in B: patience sorting)
    tails: list[int] = []
    # BACK keeps, for each pair, the one before it in its best run, to build the run again at the end.
    back: list[int] = [-1] * len(pairs)
    for k, (_, j) in enumerate(pairs):
        n = _bisect(pairs, tails, j)
        if n:
            back[k] = tails[n - 1]
        if n == len(tails):
            tails.append(k)
        else:
            tails[n] = k
    # La serie se reconstruye desde su último elemento, siguiendo BACK, y luego se invierte.
    run, k = [], tails[-1] if tails else -1
    while k >= 0:
        run.append(pairs[k])
        k = back[k]
    return run[::-1]


def _bisect(pairs, tails, j) -> int:
    """Where J goes among the places in B that end the runs TAILS (kept in order)."""
    lo, hi = 0, len(tails)
    while lo < hi:
        mid = (lo + hi) // 2
        if pairs[tails[mid]][1] < j:
            lo = mid + 1
        else:
            hi = mid
    return lo


def differences(here: pymupdf.Document, there: pymupdf.Document, ignore_case: bool = False) -> list[Difference]:
    """What differs between the words of HERE and THERE, as places of HERE."""
    a, b = words(here), words(there)
    # Con ignore_case se compara casefold(), pero lo que se informa es el texto tal como está.
    key = (lambda w: w[2].casefold()) if ignore_case else (lambda w: w[2])
    out = []
    for op, i1, i2, j1, j2 in opcodes([key(w) for w in a], [key(w) for w in b]):
        if op == "equal":
            continue
        theirs = " ".join(w[2] for w in b[j1:j2])
        there_page = b[j1][0] if j1 < j2 else -1
        if op == "insert":  # (missing here: marked where it would go, after the word before it)
            if not a:
                continue
            # i1 == 0: nothing comes before it, so the mark goes at the left edge of the first word.
            page, (x0, y0, x1, y1), _ = a[i1 - 1] if i1 > 0 else a[0]
            spot = (x1, y0, x1, y1) if i1 > 0 else (x0, y0, x0, y1)
            out.append(Difference("only_there", page, (spot,), "", theirs, there_page))
            continue
        ours = a[i1:i2]
        # Un cambio que pasa de una página a otra se parte en una diferencia por página.
        for page, rects in _lines(ours).items():
            mine = " ".join(w[2] for w in ours if w[0] == page)
            out.append(Difference("changed" if op == "replace" else "only_here", page, tuple(rects), mine,
                                  theirs, there_page))
    return out
