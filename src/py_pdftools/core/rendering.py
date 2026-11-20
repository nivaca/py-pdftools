"""Rendering pages in a process of its own (see gui/renderer.py): MuPDF keeps
Python's lock while it renders, and a scanned page can take a fifth of a
second, so rendering in the window's process would stop the window meanwhile.

The pages are rendered from the document itself; when the window draws the
annotations of the document itself (those it can edit), the process takes them
out of each page before rendering it (in its own copy, in memory: the file
is never changed).

Nothing here uses Qt: the process imports only this, annotate/annots.py and PyMuPDF.
"""

from __future__ import annotations

import pymupdf

KEPT = 3  # documents kept open (one per window, usually)
# (path, bare) -> (stamp, the document): a document whose pages are drawn without their annotations (bare)
# is a copy of its own, apart from the one drawn whole, since taking them out of a page is for good
_docs: dict[tuple[str, bool], tuple[tuple, pymupdf.Document]] = {}
_bare: dict[str, set[int]] = {}  # path -> the pages of its bare copy taken out of their annotations


def _document(path: str, password: str, stamp: tuple, bare: bool = False) -> pymupdf.Document:
    """The document at PATH (BARE: the copy whose pages are drawn without their annotations), opened again
    if it changed (another STAMP)."""
    key = (path, bare)
    # A dict keeps the order of insertion: taking a document out and putting it back marks it as the last used.
    held = _docs.pop(key, None)
    if held is not None and held[0] == stamp:
        _docs[key] = held  # (the last used, last)
        return held[1]
    if held is not None:
        held[1].close()
    # Otro sello (fecha, tamaño) quiere decir que el archivo cambió: las páginas despojadas ya no valen.
    if bare:
        _bare.pop(path, None)
    doc = pymupdf.open(path)
    if doc.needs_pass:
        doc.authenticate(password)
    _docs[key] = (stamp, doc)
    # Se cierra el documento usado hace más tiempo, el primero del diccionario.
    while len(_docs) > KEPT:
        _docs.pop(next(iter(_docs)))[1].close()
    return doc


def ready() -> bool:
    """Nothing: a new process runs this first, so that the time it takes to start (and to import
    PyMuPDF) is not counted against the first page it renders (see renderer.py, LIMIT)."""
    return True


def render(path: str, password: str, stamp: tuple, number: int, scale: float,
           bare: bool = False, clip: tuple | None = None,
           antialias: tuple[int, int] | None = None) -> tuple[int, int, int, bytes]:
    """Page NUMBER of the document at PATH rendered at SCALE (BARE: without the annotations that
    the window draws itself): its width, height, bytes per line and RGB pixels. CLIP: only that
    part of the page (x0, y0, x1, y1, in points of the page as shown), for a tile of a deep zoom.
    ANTIALIAS: MuPDF's levels of antialiasing of (text, graphics), as the settings say."""
    if antialias is not None:
        pymupdf.mupdf.fz_set_text_aa_level(antialias[0])
        pymupdf.mupdf.fz_set_graphics_aa_level(antialias[1])
    doc = _document(path, password, stamp, bare)
    if bare and number not in _bare.setdefault(path, set()):
        from ..annotate.annots import remove_editable

        remove_editable(doc, [number])
        _bare[path].add(number)
    # alpha=False: the window wants plain RGB; the stride (bytes per line) may be more than width * 3.
    pix = doc[number].get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False,
                                 clip=pymupdf.Rect(clip) if clip is not None else None)
    return pix.width, pix.height, pix.stride, bytes(pix.samples)
