"""Word index (from the author's pdf-word-finder): on which pages each word, phrase or pattern of a list appears,
by the labels of the pages (the numbers printed on them), as lines ready for the index of a book:

    Sharahzad 3, 5, 23, 34
    Nombre de Dios 5, 23

or as a detailed report, with how many times each term appears on each page and, if wished, a fragment of
text around each place. The text of the pages is made ready first: ligatures undone (NFKC), words split by a
hyphen at the end of a line joined again, and, if wished, accents taken away; a phrase may be split across
lines. A term is a regular expression if it begins with 're:' (or all are, with Options.regex).

The window (Edit > Word index) and the command line (py-pdftools find-words) both search here, so they always
find the same. Nothing here uses Qt.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from ..core.interface import ntr, tr

RE_PREFIX = "re:"
# Los guiones que pueden partir una palabra a final de renglón: el de teclado, el blando, los de U+2010 a U+2014
_HYPHENS = "-­‐‑‒–—"
_DEHYPH_RE = re.compile(rf"(\w)[{_HYPHENS}][ \t]*\n[ \t]*(\w)")
_WS_RE = re.compile(r"[ \t\r\f\v ]+")
CSV_HEADER = ["term", "sequential_page", "labelled_page", "occurrences", "context"]


class PatternError(Exception):
    """A regular expression that can't be read."""


# ----------------------------------------------------------------------------------------------- the text

def strip_accents(s: str) -> str:
    """'philología' -> 'philologia'."""
    return "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c))


def normalise(text: str, *, dehyphenate: bool = True, ignore_accents: bool = False) -> str:
    """The text of a page made ready for the search: ligatures and other compatibility forms undone (NFKC: ﬁ ->
    fi), the words split at the end of a line joined again (if wished), all on one line with single spaces, and
    the accents taken away (if wished)."""
    text = unicodedata.normalize("NFKC", text)
    if dehyphenate:
        text = _DEHYPH_RE.sub(r"\1\2", text)
    text = _WS_RE.sub(" ", text.replace("\n", " "))
    return strip_accents(text) if ignore_accents else text


def sort_key(s: str) -> str:
    """The key of the Spanish alphabetical order, which serves English too: accents and capitals left aside
    ('ámbito' and 'Ambito' go where 'ambito' would), but ñ a letter of its own, after n; ch and ll as c+h and
    l+l (the reform of 1994)."""
    s = unicodedata.normalize("NFC", s).casefold()
    # La eñe se cambia antes de quitar los diacríticos, que la volverían ene; U+FFFF va después de toda letra.
    return strip_accents(s.replace("ñ", "n￿"))


# ----------------------------------------------------------------------------------------------- the terms

def is_regex_term(term: str, as_regex: bool) -> bool:
    return as_regex or term.startswith(RE_PREFIX)


def display_term(term: str) -> str:
    """The term without its 're:', so that it serves as it is in an index."""
    return term.removeprefix(RE_PREFIX)


def build_pattern(term: str, *, as_regex: bool = False, substring: bool = False, case_sensitive: bool = False,
                  ignore_accents: bool = False, regex_word: bool = False) -> re.Pattern[str]:
    """The regular expression of TERM (PatternError if it can't be read)."""
    pattern_mode = is_regex_term(term, as_regex)
    term = term.removeprefix(RE_PREFIX)
    if ignore_accents:
        # (al texto de las páginas ya se le quitaron los acentos: también a los caracteres literales del patrón)
        term = strip_accents(unicodedata.normalize("NFKC", term))
    if pattern_mode:
        body = term
        # Una expresión regular se deja como está, salvo que se pidan límites de palabra también para ella
        if regex_word and not substring:
            body = rf"(?<!\w)(?:{body})(?!\w)"
    else:
        # (una frase puede partirse a final de renglón: los espacios entre sus palabras son flexibles)
        body = r"\s+".join(re.escape(w) for w in term.split())
        if not substring:
            # \b fails beside characters that are not letters; lookarounds work with apostrophes and hyphens too.
            body = rf"(?<!\w){body}(?!\w)"
    try:
        return re.compile(body, 0 if case_sensitive else re.IGNORECASE)
    except re.error as exc:
        raise PatternError(tr("A regular expression that can't be read, “{term}”: {error}", term=term,
                              error=exc)) from None


def read_terms(lines: Iterable[str]) -> list[str]:
    """The terms of a list, one on each line; '#' begins a comment, and empty lines are left out."""
    terms = []
    for line in lines:
        line = line.split("#", 1)[0].strip()
        if line:
            terms.append(line)
    return terms


# ----------------------------------------------------------------------------------------------- the search

@dataclass(frozen=True)
class Options:
    """How to search; context_width: None for no fragments of context, or so many characters on each side."""
    regex: bool = False
    regex_word: bool = False
    substring: bool = False
    case_sensitive: bool = False
    ignore_accents: bool = False
    dehyphenate: bool = True
    context_width: int | None = None


class Hit(NamedTuple):
    """The places of a term on a page."""
    logical: int  # the sequential page (its place in the file), from 1
    label: str  # the labelled page (the number printed on it)
    count: int  # how many times the term is on the page
    snippets: list[str]  # the fragments of context, if asked for


@dataclass
class Result:
    terms: list[str]
    hits: dict[str, list[Hit]]
    has_labels: bool
    total_pages: int
    empty_pages: int = 0

    def total(self) -> int:
        return sum(h.count for hits in self.hits.values() for h in hits)

    def pages_with_hits(self) -> int:
        return len({h.logical for hits in self.hits.values() for h in hits})


class Pages(NamedTuple):
    """What the search needs of a document: the text of each page, its label, and whether the labels are the
    document's own (or its page numbers, put in their place)."""
    texts: list[str]
    labels: list[str]
    has_labels: bool


def pages_of(doc, labels: list[str] | None = None) -> Pages:
    """The Pages of DOC (a PyMuPDF document), with its LABELS if given (those the window shows), else as the file
    has them (read as the rest of py-pdftools reads them)."""
    from ..annotate.exchange import doc_labels

    count = doc.page_count
    has = bool(labels) and any(labels)
    if labels is None:
        import io

        import pikepdf

        # (si el archivo tiene un árbol de etiquetas propio: sin él, sus etiquetas serían sus números de página)
        try:
            with pikepdf.open(io.BytesIO(doc.tobytes())) as pdf:
                has = "/PageLabels" in pdf.Root
        except (pikepdf.PdfError, RuntimeError, ValueError):
            has = False
        labels = doc_labels(doc) if has else []
    # Sin etiquetas propias (o en las páginas que no tienen), el número de la página en el archivo
    labels = [(labels[i] if i < len(labels) and labels[i] else str(i + 1)) for i in range(count)]
    return Pages([page.get_text("text") for page in doc], labels, has)


def _snippet(page: str, start: int, end: int, width: int) -> str:
    a, b = max(0, start - width), min(len(page), end + width)
    return ("…" if a else "") + page[a:b].strip() + ("…" if b < len(page) else "")


def search(pages: Pages, terms: list[str], opts: Options) -> Result:
    """Each of TERMS on each page (PatternError if a regular expression can't be read)."""
    texts = [normalise(t, dehyphenate=opts.dehyphenate, ignore_accents=opts.ignore_accents) for t in pages.texts]
    patterns = {t: build_pattern(t, as_regex=opts.regex, substring=opts.substring,
                                 case_sensitive=opts.case_sensitive, ignore_accents=opts.ignore_accents,
                                 regex_word=opts.regex_word) for t in terms}
    hits: dict[str, list[Hit]] = {t: [] for t in terms}
    for idx, text in enumerate(texts):
        for term, pattern in patterns.items():
            matches = list(pattern.finditer(text))
            if not matches:
                continue
            snippets = [] if opts.context_width is None else [
                _snippet(text, m.start(), m.end(), opts.context_width) for m in matches]
            hits[term].append(Hit(idx + 1, pages.labels[idx], len(matches), snippets))
    return Result(terms=list(terms), hits=hits, has_labels=pages.has_labels, total_pages=len(texts),
                  empty_pages=sum(1 for t in texts if not t.strip()))


# ----------------------------------------------------------------------------------------------- the report

def fmt_page(logical: int, label: str, show_logical: bool) -> str:
    """The labelled page; with SHOW_LOGICAL, its sequential one too, where they differ ('xiv [seq. 16]')."""
    if show_logical and label != str(logical):
        return tr("{label} [seq. {page}]", label=label, page=logical)
    return label


def alphabetical_terms(terms: list[str]) -> list[str]:
    return sorted(terms, key=lambda t: sort_key(display_term(t)))


def index_lines(result: Result, show_logical: bool = False, alphabetical: bool = False) -> list[str]:
    """The lines of the list: 'term page, page, page' (the terms not found left out)."""
    lines = []
    for term in alphabetical_terms(result.terms) if alphabetical else result.terms:
        hits = result.hits.get(term)
        if hits:
            lines.append(f"{display_term(term)} " + ", ".join(fmt_page(h.logical, h.label, show_logical)
                                                              for h in hits))
    return lines


def detailed_lines(result: Result, show_logical: bool = False) -> list[str]:
    """How many times each term appears, and a page on each line, with the fragments of context under it."""
    lines: list[str] = []
    for term in result.terms:
        hits = result.hits.get(term, [])
        shown = display_term(term)
        if not hits:
            lines.append(tr("“{term}”: not found", term=shown))
            continue
        total = sum(h.count for h in hits)
        lines.append(f"“{shown}”: " + ntr("{count} time", "{count} times", total) + " "
                     + ntr("on {count} page", "on {count} pages", len(hits)))
        for h in hits:
            lines.append(f"    {fmt_page(h.logical, h.label, show_logical)}" + (f" ×{h.count}" if h.count > 1 else ""))
            lines.extend(f"        {s}" for s in h.snippets)
        lines.append("")
    if result.has_labels and show_logical:
        lines.append(tr("Convention: labelled page [seq. sequential page]"))
    return lines


def build_report(result: Result, *, show_logical: bool = False, detailed: bool = False,
                 alphabetical: bool = False) -> tuple[str, str]:
    """(the report, the notes): the list (or, DETAILED, the detailed report), and apart what is worth knowing
    (no labels, pages without text, the terms not found)."""
    notes: list[str] = []
    if not result.has_labels:
        notes.append(tr("This PDF has no page labels: the pages are given by their place in the file."))
    if result.empty_pages:
        notes.append(tr("{empty} of {total} pages have no text (scanned, without OCR?).", empty=result.empty_pages,
                        total=result.total_pages))
    if detailed:
        lines = detailed_lines(result, show_logical)
    else:
        lines = index_lines(result, show_logical, alphabetical)
        missing = [display_term(t) for t in result.terms if not result.hits.get(t)]
        if missing:
            notes.append(tr("Not found: {terms}", terms=", ".join(missing)))
    return "\n".join(lines).rstrip("\n"), "\n".join(notes)


def write_txt(path: str | Path, result: Result, show_logical: bool = False) -> int:
    """The list, in alphabetical order, as a text file; how many lines (OSError if it can't be written)."""
    lines = index_lines(result, show_logical, alphabetical=True)
    Path(path).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return len(lines)


def write_csv(path: str | Path, result: Result) -> None:
    """A row for each term and page, in alphabetical order (OSError if it can't be written)."""
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(CSV_HEADER)
        for term in alphabetical_terms(result.terms):
            for h in result.hits.get(term, []):
                w.writerow([display_term(term), h.logical, h.label, h.count, " | ".join(h.snippets)])
