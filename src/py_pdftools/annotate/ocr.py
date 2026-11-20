"""Recognising the text of scanned pages (OCR) with Tesseract, through PyMuPDF: a copy of the
document in which each scanned page has its text, invisible, under its image, where the image shows
it; so that it can be found, copied, and marked with the tools that mark text.

Tesseract is not needed otherwise: without it, there is no OCR (see available).
"""

from __future__ import annotations

import functools
import shutil
from collections.abc import Callable
from pathlib import Path

import pymupdf

from . import annots
from .annots import AnnotateError, Annotation
from ..core.interface import tr

DPI = 300  # (at which the pages are read)


@functools.cache
def tessdata() -> str | None:
    """The folder of Tesseract's languages; None if Tesseract is not installed. (Looked for once: the
    window asks each time it shows its menus.)"""
    # Tesseract's program must be on the PATH; PyMuPDF only finds the folder of its languages.
    if shutil.which("tesseract") is None:
        return None
    try:
        return pymupdf.get_tessdata() or None
    except (RuntimeError, ValueError, OSError):
        return None


def available() -> bool:
    return tessdata() is not None


def languages() -> list[str]:
    """The languages Tesseract can read here ('eng', 'spa', 'lat'...)."""
    folder = tessdata()
    if folder is None:
        return []
    # osd es el modelo de Tesseract que detecta la orientación y la escritura, no un idioma.
    return sorted(p.stem for p in Path(folder).glob("*.traineddata") if p.stem != "osd")


def scanned(page: pymupdf.Page) -> bool:
    """Whether PAGE is a scan: it has images, and no text."""
    return not page.get_text("text").strip() and bool(page.get_images())


def add_text(page: pymupdf.Page, language: str) -> int:
    """Read PAGE with Tesseract (in LANGUAGE: 'eng', or several, 'lat+eng') and write the words it
    finds, invisible, where they are on the image. Returns how many words."""
    # full=True: se reconoce la página entera, no solo las zonas de sus imágenes.
    found = page.get_textpage_ocr(language=language, dpi=DPI, full=True)
    words = page.get_text("words", textpage=found)
    # Las palabras vienen en la página sin girar: se pasan a la página como se muestra, y luego de vuelta.
    turn, back = page.rotation_matrix, page.derotation_matrix
    for x0, y0, x1, y1, word, *_ in words:
        shown = pymupdf.Rect(x0, y0, x1, y1) * turn  # (the word as the page is shown, upright)
        # Un 85 % de la altura de la caja se acerca al cuerpo de la letra; la línea base queda a un 20 % del fondo.
        size = max(shown.height * 0.85, 1)
        width = pymupdf.get_text_length(word, "helv", size) or 1
        start = pymupdf.Point(shown.x0, shown.y1 - shown.height * 0.2) * back
        # render_mode=3: texto invisible, que se puede buscar y copiar pero no se dibuja.
        page.insert_text(start, word, fontsize=size, fontname="helv", render_mode=3, rotate=page.rotation,
                         morph=(start, pymupdf.Matrix(shown.width / width, 0, 0, 1, 0, 0)))  # (as wide as on the image)
    return len(words)


def save_searchable(source: Path, annotations: list[Annotation], target: Path, password: str, language: str,
                    progress: Callable[[int, int], bool] | None = None) -> tuple[int, int]:
    """SOURCE with ANNOTATIONS, saved as TARGET with the text of its scanned pages read (see
    add_text). PROGRESS(done, of), if given, is told of each page, and stops it by returning
    False. Returns how many pages were read, and how many words they had."""
    doc = annots.open_pdf(source, password)
    try:
        # The annotations are applied first, so that the searchable copy keeps them too.
        annots.apply(doc, annotations)
        # Solo se leen las páginas sin texto: una página que ya tiene texto no se toca.
        pages = [page.number for page in doc if scanned(page)]
        words = 0
        for done, number in enumerate(pages):
            if progress is not None and not progress(done, len(pages)):
                raise AnnotateError(tr("Stopped: the copy was not made"))
            words += add_text(doc[number], language)
        annots.save_doc(doc, target)
    except (RuntimeError, ValueError, OSError) as e:
        raise AnnotateError(tr("{path} cannot be written: {error}", path=target, error=e)) from None
    finally:
        if not doc.is_closed:
            doc.close()
    return len(pages), words
