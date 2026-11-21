"""Combining PDFs into one: the pages of several files (all, or some of each, in any order), one after
another, with their links, annotations and form fields; their bookmarks under one for each file, or as
they are, or none; and, if wished, the page labels each file had. The files are not changed. Fields of the
same name in two files are renamed by PyMuPDF, so that each keeps its value.

Making a PDF from pictures (photographs, scans) is here too: one page for each picture (each page of a
TIFF of several), as big as the picture or on paper of a size, with a margin."""

from __future__ import annotations

import dataclasses
import os
import re
import tempfile
from pathlib import Path

import pymupdf

from ..core.interface import tr
from ..core.pagesel import PageError, parse_pages

BOOKMARKS = ("files", "keep", "none")  # one for each file (with its own under it), as they are, none
PAPERS = {"A3": (297, 420), "A4": (210, 297), "A5": (148, 210), "Letter": (215.9, 279.4),
          "Legal": (215.9, 355.6)}  # (milímetros)
IMAGES = ("*.png", "*.jpg", "*.jpeg", "*.tif", "*.tiff", "*.bmp", "*.gif", "*.webp", "*.jxr", "*.pnm", "*.pbm",
          "*.pgm", "*.ppm", "*.jp2")
MM = 72 / 25.4


class CombineError(Exception):
    pass


class PasswordNeeded(CombineError):
    """A file whose password is missing or wrong."""


@dataclasses.dataclass(frozen=True)
class Part:
    path: Path
    pages: str = ""  # which, as a list of pages ('1-3, 7'); '' for all
    password: str = ""


def _open(path: Path, password: str = "") -> pymupdf.Document:
    try:
        doc = pymupdf.open(path)
    except (pymupdf.FileNotFoundError, pymupdf.FileDataError, RuntimeError) as e:
        raise CombineError(tr("{path} cannot be read as a PDF: {error}", path=path, error=e)) from None
    if not doc.is_pdf:
        doc.close()
        raise CombineError(tr("{path} is not a PDF", path=path))
    if doc.needs_pass and not doc.authenticate(password):
        doc.close()
        raise PasswordNeeded(tr("{path} is protected by a password", path=path))
    return doc


def page_count(path: Path, password: str = "") -> int:
    with _open(path, password) as doc:
        return doc.page_count


def chosen_pages(part: Part, count: int) -> list[int]:
    """The pages of PART (0-based, in the order given) of a file of COUNT pages."""
    if not part.pages.strip():
        return list(range(count))
    try:
        return parse_pages(part.pages, count, keep_order=True)
    except PageError as e:
        raise CombineError(tr("The pages of {file} can't be read: {error}", file=part.path.name, error=e)) from None


# ----------------------------------------------------------------- page labels

_ROMAN = re.compile(r"^(?=[mdclxvi])m{0,4}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})$")


def _roman(text: str) -> int:
    values = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
    total = 0
    for a, b in zip(text, text[1:] + " ", strict=True):
        v = values[a]
        total += -v if b != " " and values[b] > v else v
    return total


def _style(label: str) -> tuple[str, int] | None:
    """(style, number) of LABEL, if it is a number in a style of page labels ('D', 'r', 'R')."""
    if label.isdigit() and not label.startswith("0"):
        return "D", int(label)
    if label and _ROMAN.match(label):
        return "r", _roman(label)
    if label and _ROMAN.match(label.lower()) and label.isupper():
        return "R", _roman(label.lower())
    return None


def label_rules(labels: list[str]) -> list[dict]:
    """The page label ranges (as PyMuPDF writes them) that give the pages LABELS: numbers that follow one
    another make one range; any other label is a range of one page, all prefix."""
    rules: list[dict] = []
    last: tuple[str, int] | None = None
    for i, label in enumerate(labels):
        s = _style(label)
        if s is not None and last is not None and s[0] == last[0] and s[1] == last[1] + 1:
            last = s
            continue
        if s is not None:
            rules.append({"startpage": i, "prefix": "", "style": s[0], "firstpagenum": s[1]})
        else:
            rules.append({"startpage": i, "prefix": label, "style": "", "firstpagenum": 1})
        last = s
    return rules


# ----------------------------------------------------------------- combining

def _title(doc: pymupdf.Document, path: Path) -> str:
    title = ((doc.metadata or {}).get("title") or "").strip()
    return title or path.stem


def _bookmarks(toc: list, kept: dict[int, int], offset: int, under: int) -> list:
    """The bookmarks TOC of a file whose pages KEPT (1-based: old -> new) are kept, moved by OFFSET pages and
    UNDER levels; those of pages left out go, and the levels are mended where they would jump."""
    out, last = [], under
    for entry in toc:
        level, title, page = entry[0], entry[1], entry[2]
        if page not in kept:
            continue
        level = min(level + under, last + 1)
        out.append([level, title, kept[page] + offset])
        last = level
    return out


def combine(parts: list[Part], target: Path, bookmarks: str = "files", labels: bool = False,
            progress=None) -> int:
    """The pages of PARTS, one file after another, saved as TARGET (which may be one of them). BOOKMARKS:
    one for each file with its own under it ('files'), those of the files as they are ('keep'), or none;
    LABELS: each page keeps its page label. PROGRESS(done, total), if given, is called after each file.
    Returns how many pages TARGET has."""
    if not parts:
        raise CombineError(tr("There are no files to combine"))
    out = pymupdf.open()
    toc: list = []
    all_labels: list[str] = []
    try:
        for done, part in enumerate(parts):
            with _open(part.path, part.password) as doc:
                pages = chosen_pages(part, doc.page_count)
                if not pages:
                    continue
                old_toc = doc.get_toc(simple=True)
                page_labels = [doc[n].get_label() or str(n + 1) for n in pages]
                title = _title(doc, part.path)
                if pages != list(range(doc.page_count)):
                    doc.select(pages)  # (en memoria: los enlaces entre las páginas que quedan las siguen)
                start = out.page_count
                out.insert_pdf(doc)
            kept: dict[int, int] = {}
            for new, old in enumerate(pages, 1):
                kept.setdefault(old + 1, new)  # (una página dada dos veces: sus marcadores van a la primera)
            if bookmarks == "files":
                toc.append([1, title, start + 1])
                toc += _bookmarks(old_toc, kept, start, 1)
            elif bookmarks == "keep":
                toc += _bookmarks(old_toc, kept, start, 0)
            all_labels += page_labels
            if progress is not None:
                progress(done + 1, len(parts))
        if not out.page_count:
            raise CombineError(tr("There are no pages to combine"))
        # El primer marcador debe ser de nivel 1: set_toc rechaza un índice que empiece más abajo.
        if toc:
            out.set_toc(toc)
        if labels:
            out.set_page_labels(label_rules(all_labels))
        count = out.page_count
        _save(out, target)
        return count
    finally:
        if not out.is_closed:
            out.close()


def _save(doc: pymupdf.Document, target: Path) -> None:
    """DOC saved as TARGET through a temporary file beside it (TARGET may be one of the files read)."""
    fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=target.parent)
    os.close(fd)
    try:
        doc.save(tmp, garbage=3, deflate=True)
        doc.close()
        os.replace(tmp, target)
    except (OSError, RuntimeError, ValueError) as e:
        Path(tmp).unlink(missing_ok=True)
        raise CombineError(tr("{path} cannot be written: {error}", path=target, error=e)) from None


# ----------------------------------------------------------------- from pictures

def _frames(path: Path) -> pymupdf.Document:
    """The picture at PATH as a PDF of one page for each of its frames, each as big as the frame is (at the
    resolution the picture says; at 96 dpi if it says none)."""
    try:
        with pymupdf.open(path) as img:
            if img.is_pdf:
                raise CombineError(tr("{path} is not a picture", path=path))
            return pymupdf.open("pdf", img.convert_to_pdf())
    except CombineError:
        raise
    except Exception as e:  # (MuPDF tiene errores propios para cada formato que no entiende)
        raise CombineError(tr("{path} cannot be read as a picture: {error}", path=path, error=e)) from None


def from_images(images: list[Path], target: Path, paper: str = "", landscape: bool | None = None,
                margin: float = 0, progress=None) -> int:
    """A PDF of IMAGES, a page for each (or for each frame of one), saved as TARGET. PAPER: a size of PAPERS
    on which each picture is put, as large as fits within MARGIN (millimetres), and centred; '' for pages as
    big as the pictures (and MARGIN around them). LANDSCAPE: the paper lying (True) or standing (False);
    None, as each picture is. Returns how many pages it has."""
    if not images:
        raise CombineError(tr("There are no pictures"))
    out = pymupdf.open()
    try:
        for done, path in enumerate(images):
            with _frames(path) as frames:
                for n in range(frames.page_count):
                    pic = frames[n].rect
                    m = margin * MM
                    if paper:
                        w, h = (v * MM for v in PAPERS[paper])
                        lying = pic.width > pic.height if landscape is None else landscape
                        if lying:
                            w, h = h, w
                    else:
                        w, h = pic.width + 2 * m, pic.height + 2 * m
                    page = out.new_page(width=w, height=h)
                    room = pymupdf.Rect(m, m, w - m, h - m)
                    if room.is_empty:
                        raise CombineError(tr("The margin leaves no room for the pictures"))
                    # keep_proportion: la imagen tan grande como quepa, centrada en el espacio que deja el margen.
                    page.show_pdf_page(room, frames, n, keep_proportion=True)
            if progress is not None:
                progress(done + 1, len(images))
        count = out.page_count
        _save(out, target)
        return count
    finally:
        if not out.is_closed:
            out.close()
