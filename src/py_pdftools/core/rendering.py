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

import os
import sys

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
    # On Windows a file held open can't be replaced, and these processes keep documents open (KEPT): saving the
    # document, or protecting it, would fail. There they are read into memory, and the file is let go at once.
    if sys.platform == "win32":
        with open(path, "rb") as f:
            doc = pymupdf.open(stream=f.read(), filetype="pdf")
    else:
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


LOW_NICE = 10  # (how much lower the processes of the thumbnails run, on Linux and macOS)


def lower_priority() -> None:
    """Run this process below the others (the thumbnails' processes): when the computer is busy, the pages
    in view and the window get the processor first. On an idle computer it changes nothing."""
    try:
        if sys.platform == "win32":
            import ctypes

            # BELOW_NORMAL_PRIORITY_CLASS, no IDLE: con IDLE, un equipo ocupado podría no hacer nunca las miniaturas.
            kernel = ctypes.windll.kernel32
            kernel.SetPriorityClass(kernel.GetCurrentProcess(), 0x00004000)
        else:
            os.nice(LOW_NICE)
    except (OSError, AttributeError):  # (a system that doesn't allow it: the process runs as it is)
        pass


AS_DRAWN = (1.0, 0.0, 0)  # (gamma, radius and percent of the unsharp mask): the text as MuPDF draws it


def sharpen(pix: pymupdf.Pixmap, sharpness: tuple = AS_DRAWN) -> tuple[int, bytes]:
    """The RGB pixels of PIX with the sharpness of the text SHARPNESS, (gamma, radius, percent): the gamma
    darkens the soft grey edges of letters and lines (MuPDF doesn't snap them to the pixels, as the desktop's
    fonts are), and an unsharp mask of that radius and strength makes those edges steeper. Its stride (bytes
    per line) and its bytes."""
    gamma, radius, percent = sharpness
    if gamma != 1.0:
        pix.gamma_with(gamma)
    if not percent:
        return pix.stride, bytes(pix.samples)
    try:
        from PIL import Image, ImageFilter
    except ImportError:  # (sin Pillow, solo la gamma)
        return pix.stride, bytes(pix.samples)
    # Sin umbral: la máscara afila todos los bordes, también los suaves de las letras pequeñas
    img = Image.frombuffer("RGB", (pix.width, pix.height), pix.samples, "raw", "RGB", pix.stride, 1)
    img = img.filter(ImageFilter.UnsharpMask(radius=radius, percent=percent, threshold=0))
    return pix.width * 3, img.tobytes()


def tinted(width: int, height: int, stride: int, data: bytes, tint: tuple[int, int]) -> bytes:
    """DATA (RGB) in the colours TINT (see gui/reading.py), through a pixmap of PyMuPDF."""
    pix = pymupdf.Pixmap(pymupdf.csRGB, width, height, data[: stride * height] if stride == width * 3 else
                         b"".join(data[r * stride: r * stride + width * 3] for r in range(height)), False)
    pix.tint_with(tint[0], tint[1])
    return bytes(pix.samples)


def render(path: str, password: str, stamp: tuple, number: int, scale: float,
           bare: bool = False, clip: tuple | None = None,
           antialias: tuple[int, int] | None = None,
           tint: tuple[int, int] | None = None, sharpness: tuple = AS_DRAWN) -> tuple[int, int, int, bytes]:
    """Page NUMBER of the document at PATH rendered at SCALE (BARE: without the annotations that
    the window draws itself): its width, height, bytes per line and RGB pixels. CLIP: only that
    part of the page (x0, y0, x1, y1, in points of the page as shown), for a tile of a deep zoom.
    ANTIALIAS: MuPDF's levels of antialiasing of (text, graphics), as the settings say. TINT: (the colour black
    becomes, the colour white becomes), for reading colours (see gui/reading.py). SHARPNESS: the text made sharper
    (see sharpen; Settings > Appearance)."""
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
    if sharpness == AS_DRAWN:
        if tint is not None:
            pix.tint_with(tint[0], tint[1])
        return pix.width, pix.height, pix.stride, bytes(pix.samples)
    # Antes del tinte: se afila el texto en sus colores, que luego el tinte cambia
    stride, data = sharpen(pix, sharpness)
    if tint is not None:
        data, stride = tinted(pix.width, pix.height, stride, data, tint), pix.width * 3
    return pix.width, pix.height, stride, data
