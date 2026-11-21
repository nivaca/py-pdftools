"""Where a PDF is split into several: every so many pages (one each, with the page's label in the name of its
file), at given pages, at its bookmarks of a level (each part named after its bookmark), or so that no part
is bigger than a size. plan() turns one of these into the parts: (first page, last page, a name for its file,
'' to number it)."""

from __future__ import annotations

import io
import re
from pathlib import Path

import pikepdf
import pymupdf

from ..core.interface import tr
from . import arrange
from .labels import LabelError

Part = tuple[int, int, str]  # (primera, última: desde 1; un nombre para su archivo, "" para numerarla)


def safe_name(text: str, most: int = 60) -> str:
    """TEXT as part of a file name: letters, digits and few signs, at most MOST characters."""
    text = re.sub(r"[^\w\s.,()-]+", " ", text, flags=re.UNICODE).strip()
    return re.sub(r"\s+", " ", text)[:most].strip(" .") or "part"


def at_bookmarks(toc: list, n: int, level: int = 1) -> list[Part]:
    """Parts that start at the pages of the bookmarks of LEVEL (of TOC, as PyMuPDF gives it) of a document of
    N pages, named after them; what comes before the first is a part of its own."""
    starts: dict[int, str] = {}
    for lvl, title, page, *_ in toc:
        if lvl == level and 1 <= page <= n and page not in starts:
            starts[page] = title
    if not starts:
        raise LabelError(tr("The document has no bookmarks of level {level}", level=level))
    if 1 not in starts:
        starts[1] = ""
    pages = sorted(starts)
    return [(s, (pages[i + 1] - 1) if i + 1 < len(pages) else n, safe_name(starts[s]) if starts[s] else "")
            for i, s in enumerate(pages)]


def _size(data: bytes, first: int, last: int, password: str) -> int:
    """How many bytes the part of pages FIRST-LAST of the PDF DATA takes, written."""
    with pikepdf.open(io.BytesIO(data), password=password) as pdf:
        arrange.Order(tuple(range(first, last + 1))).apply(pdf)
        out = io.BytesIO()
        pdf.save(out, compress_streams=True, object_stream_mode=pikepdf.ObjectStreamMode.generate)
        return out.tell()


def by_size(data: bytes, n: int, most: int, password: str = "") -> list[Part]:
    """Parts of the PDF DATA (N pages) of at most MOST bytes each (a single page bigger than that is a part by
    itself). Each part is measured as written; its length is guessed from the average size of a page, and
    then shortened or lengthened until it fits."""
    if most < 1:
        raise LabelError(tr("a part needs one page at least"))
    average = max(1, len(data) // max(1, n))
    parts, first = [], 1
    while first <= n:
        last = min(n, first + max(1, most // average) - 1)
        size = _size(data, first, last, password)
        while size > most and last > first:  # (demasiado: se acorta a la mitad hasta que quepa)
            last = first + (last - first) // 2
            size = _size(data, first, last, password)
        step = max(1, (last - first + 1) // 4)
        while last < n:  # (y se alarga mientras quepa, en pasos que se achican)
            longer = min(n, last + step)
            if _size(data, first, longer, password) <= most:
                last = longer
            elif step > 1:
                step = max(1, step // 2)
            else:
                break
        parts.append((first, last, ""))
        first = last + 1
    return parts


def plan(spec: dict, source: Path | bytes, password: str = "") -> list[Part]:
    """The parts SPEC asks for, of SOURCE (a PDF, or its bytes): {'every': N} ({'every': 1} names each part
    after its page's label), {'at': [pages]}, {'bookmarks': level} or {'size': bytes}."""
    data = source if isinstance(source, bytes) else Path(source).read_bytes()
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        if doc.needs_pass:
            doc.authenticate(password)
        n = doc.page_count
        if "bookmarks" in spec:
            return at_bookmarks(doc.get_toc(simple=True), n, int(spec["bookmarks"]))
        if spec.get("every") == 1:
            from ..annotate.exchange import doc_labels

            labels = doc_labels(doc)  # (como las lee pikepdf: el PyMuPDF de algunas distribuciones las lee mal)
            return [(i + 1, i + 1, safe_name(labels[i]) if labels[i] and labels[i] != str(i + 1) else "")
                    for i in range(n)]
    if "size" in spec:
        return by_size(data, n, int(spec["size"]), password)
    return [(f, last, "") for f, last in arrange.split_parts(n, int(spec.get("every", 0)), spec.get("at"))]


def file_names(stem: str, parts: list[Part]) -> list[str]:
    """The names of the files of PARTS: STEM-1.pdf, STEM-2.pdf..., or STEM-01-Its name.pdf when it has one;
    two parts never get the same name."""
    width = len(str(len(parts)))
    out, used = [], set()
    for k, (_, _, name) in enumerate(parts, 1):
        base = f"{stem}-{k:0{width}}-{name}" if name else f"{stem}-{k}"
        candidate, j = base, 2
        while candidate.lower() in used:
            candidate, j = f"{base}-{j}", j + 1
        used.add(candidate.lower())
        out.append(candidate + ".pdf")
    return out
