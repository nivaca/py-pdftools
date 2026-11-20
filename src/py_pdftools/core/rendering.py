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
_docs: dict[str, tuple[tuple, pymupdf.Document]] = {}  # path -> (stamp, the document)
_bare: dict[str, set[int]] = {}  # path -> the pages of its document taken out of their annotations


def _document(path: str, password: str, stamp: tuple) -> pymupdf.Document:
    """The document at PATH, opened again if it changed (another STAMP)."""
    # A dict keeps the order of insertion: taking a document out and putting it back marks it as the last used.
    held = _docs.pop(path, None)
    if held is not None and held[0] == stamp:
        _docs[path] = held  # (the last used, last)
        return held[1]
    if held is not None:
        held[1].close()
    # Otro sello (fecha, tamaño) quiere decir que el archivo cambió: las páginas despojadas ya no valen.
    _bare.pop(path, None)
    doc = pymupdf.open(path)
    if doc.needs_pass:
        doc.authenticate(password)
    _docs[path] = (stamp, doc)
    # Se cierra el documento usado hace más tiempo, el primero del diccionario.
    while len(_docs) > KEPT:
        _docs.pop(next(iter(_docs)))[1].close()
    return doc


def render(path: str, password: str, stamp: tuple, number: int, scale: float,
           bare: bool = False) -> tuple[int, int, int, bytes]:
    """Page NUMBER of the document at PATH rendered at SCALE (BARE: without the annotations that
    the window draws itself): its width, height, bytes per line and RGB pixels."""
    doc = _document(path, password, stamp)
    # TODO: una página despojada queda así en la copia en memoria: si después se pide sin BARE, sale sin sus
    # anotaciones. Habría que abrir el documento otra vez, o guardar aparte las páginas despojadas.
    if bare and number not in _bare.setdefault(path, set()):
        from ..annotate.annots import remove_editable

        remove_editable(doc, [number])
        _bare[path].add(number)
    # alpha=False: the window wants plain RGB; the stride (bytes per line) may be more than width * 3.
    pix = doc[number].get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
    return pix.width, pix.height, pix.stride, bytes(pix.samples)
