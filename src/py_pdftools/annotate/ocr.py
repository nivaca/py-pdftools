"""A searchable copy of the document (File > Save a copy > Searchable): each scanned page with its
text, read by tesseract (see core/ocr.py), invisible, under its image, where the image shows it; so
that it can be found, copied, and marked with the tools that mark text. The annotations go into the
copy too. (Edit > Recognise text writes the text into the document itself: see gui/ocring.py.)

Tesseract is not needed otherwise: without it, there is no OCR (see available).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from . import annots
from .annots import AnnotateError, Annotation
from ..core import ocr
from ..core.interface import tr
from ..core.ocr import available, languages, scanned  # noqa: F401  (as before, for the window and the tests)


def save_searchable(source: Path, annotations: list[Annotation], target: Path, password: str, language: str,
                    progress: Callable[[int, int], bool] | None = None, rotate: bool = False) -> tuple[int, int]:
    """SOURCE with ANNOTATIONS, saved as TARGET with the text of its scanned pages read (turned first, if
    ROTATE and they lie sideways). PROGRESS(done, of), if given, is told how far it has got, and stops it
    by returning False. Returns how many pages were read, and how many words they had."""
    doc = annots.open_pdf(source, password)
    try:
        # Solo se leen las páginas sin texto: una página que ya tiene texto no se toca.
        pages = [page.number for page in doc if scanned(page)]
        try:
            results = ocr.run(source, password, pages, language, rotate=rotate, progress=progress)
        except ocr.OcrError as e:
            raise AnnotateError(tr("The copy was not made: {error}", error=e)) from None
        # The annotations are applied first, so that the searchable copy keeps them too.
        annots.apply(doc, annotations)
        words = sum(ocr.write_words(doc[r.number], r) for r in results)
        annots.save_doc(doc, target)
    except (RuntimeError, ValueError, OSError) as e:
        raise AnnotateError(tr("{path} cannot be written: {error}", path=target, error=e)) from None
    finally:
        if not doc.is_closed:
            doc.close()
    return len(pages), words
