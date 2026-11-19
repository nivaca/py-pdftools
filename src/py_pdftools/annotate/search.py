"""Finding text on the pages, for Find and highlight: a word, a phrase, words
with wildcards (* and ?) or a regular expression, found across line breaks
however it is spaced, and across words hyphenated at the end of a line; if
asked, without minding accents (acción, accion), and with u and v, i and j
taken as one letter (as in Latin and medieval texts). Each place found is given
with a rectangle for each of its lines, as the page is shown (what a highlight
over it needs)."""

from __future__ import annotations

import dataclasses
import re
import unicodedata

import pymupdf

from .annots import Rect


@dataclasses.dataclass(frozen=True)
class Match:
    page: int  # 0-based
    rects: tuple[Rect, ...]  # one for each line of the text found
    text: str  # what was found
    context: str  # with some words around it, the text found in [brackets]


def _shown(page: pymupdf.Page, rect) -> pymupdf.Rect:
    return (pymupdf.Rect(rect) * page.rotation_matrix).normalize()


HYPHENS = "-\u00ad\u2010"  # (a hyphen, a soft hyphen, the hyphen of Unicode)


def page_chars(page: pymupdf.Page) -> tuple[str, list]:
    """The text of PAGE, and for each of its characters (block, line, rectangle as the page
    is shown), or None for a space put between two lines. Runs of spaces are one space. A word
    hyphenated at the end of a line is one word ("jus-" "tice": "justice"), its hyphen left out."""
    text, where = [], []
    raw = page.get_text("rawdict", flags=pymupdf.TEXTFLAGS_SEARCH & ~pymupdf.TEXT_PRESERVE_IMAGES)
    for b, block in enumerate(raw.get("blocks", [])):
        for n, line in enumerate(block.get("lines", [])):
            first = True
            for span in line.get("spans", []):
                for ch in span.get("chars", []):
                    c = ch["c"]
                    if first and not c.isspace():
                        first = False
                        if not text:
                            pass
                        elif (text[-1] in HYPHENS and len(text) > 1 and text[-2].isalpha() and c.isalpha()
                                and c.islower()):
                            text.pop()  # (the word goes on: no hyphen, no space)
                            where.pop()
                        elif text[-1] != " ":
                            text.append(" ")
                            where.append(None)
                    if c.isspace():
                        if not text or text[-1] == " ":
                            continue
                        c = " "
                    text.append(c)
                    where.append((b, n, _shown(page, ch["bbox"])))
    return "".join(text), where


LIGATURES = {"æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "ß": "ss", "ſ": "s", "ø": "o", "Ø": "O", "đ": "d", "ł": "l",
             "Ł": "L"}
UV = str.maketrans({"v": "u", "V": "U", "j": "i", "J": "I"})


def fold(text: str, accents: bool = True, uv: bool = False) -> tuple[str, list[int]]:
    """TEXT without its accents (and ligatures, æ: ae; ſ: s), if ACCENTS; with v as u and j as i, if
    UV; and for each character of what is made, the place in TEXT of the one it comes from."""
    out, index = [], []
    for i, c in enumerate(text):
        f = c
        if accents:
            f = LIGATURES.get(c) or "".join(ch for ch in unicodedata.normalize("NFKD", c)
                                            if not unicodedata.combining(ch)) or c
        if uv:
            f = f.translate(UV)
        out.append(f)
        index.extend([i] * len(f))
    return "".join(out), index


def compile_query(query: str, case: bool = False, whole_words: bool = False, regex: bool = False,
                  wildcards: bool = False) -> re.Pattern:
    """QUERY as a regular expression (raises re.error if REGEX and it is wrong). WILDCARDS: in a
    query that isn't a regular expression, * stands for any letters (none too), ? for one."""
    def word(w: str) -> str:
        escaped = re.escape(w)
        if wildcards:
            escaped = escaped.replace(r"\*", r"\w*").replace(r"\?", r"\w")
        return escaped

    pattern = query if regex else r"\s+".join(word(w) for w in query.split())
    if whole_words:
        pattern = rf"(?<!\w)(?:{pattern})(?!\w)"
    return re.compile(pattern, 0 if case else re.IGNORECASE)


def find_text(doc: pymupdf.Document, query: str, pages: list[int] | None = None, case: bool = False,
              whole_words: bool = False, regex: bool = False, progress=None, accents: bool = False,
              uv: bool = False, wildcards: bool = False, cache: dict | None = None) -> list[Match]:
    """Where QUERY is on PAGES (0-based; all if None) of DOC, in page order. ACCENTS: without
    minding accents; UV: u and v, i and j as one (see fold); WILDCARDS: see compile_query. PROGRESS,
    if given, is called after each page with (pages done, pages in all); if it returns False,
    the search stops there, with what it found so far. CACHE, if given, keeps the text of each page
    read (for the next search in the same document)."""
    if not query.strip():
        return []
    folding = accents or uv
    if folding and not regex:  # (the query is folded as the text is; a regular expression is left as written)
        query = fold(query, accents, uv)[0]
    found_re = compile_query(query, case, whole_words, regex, wildcards)
    numbers = list(range(doc.page_count) if pages is None else pages)
    out = []
    for done, number in enumerate(numbers, 1):
        if cache is not None and number in cache:
            text, where = cache[number]
        else:
            text, where = page_chars(doc[number])
            if cache is not None:
                cache[number] = (text, where)
        if folding:
            searched, index = fold(text, accents, uv)
        else:
            searched, index = text, None
        for m in found_re.finditer(searched):
            start, end = m.span()
            if index is not None:
                if start == end:
                    continue
                start, end = index[start], index[end - 1] + 1
            chosen = [i for i in range(start, end) if where[i] is not None and not text[i].isspace()]
            if not chosen:
                continue
            lines: dict[tuple[int, int], pymupdf.Rect] = {}
            for i in chosen:
                b, n, r = where[i]
                lines[(b, n)] = lines[(b, n)] | r if (b, n) in lines else pymupdf.Rect(r)
            rects = tuple((round(r.x0, 2), round(r.y0, 2), round(r.x1, 2), round(r.y1, 2)) for r in lines.values())
            before = text[max(start - 40, 0):start].split(" ", 1)[-1] if start > 40 else text[:start]
            after = text[end:end + 40].rsplit(" ", 1)[0] if len(text) > end + 40 else text[end:]
            snippet = text[start:end].strip()  # (as written on the page, not as folded)
            context = " ".join(p for p in (before.strip(), f"[{snippet}]", after.strip()) if p)
            out.append(Match(number, rects, snippet, context))
        if progress is not None and progress(done, len(numbers)) is False:
            break
    return out
