"""Páginas convertidas en imágenes: cada página elegida se dibuja como imagen, a la resolución pedida, y su
contenido (texto, fuentes, dibujos, anotaciones, campos de formulario) se reemplaza por esa imagen. Lo que
se veía sigue viéndose igual, pero ya no hay texto que buscar, copiar o extraer. El archivo no cambia: se
escribe una copia. Las páginas no elegidas, los marcadores, las etiquetas de página y los enlaces se quedan
como estaban."""

from __future__ import annotations

import dataclasses
import os
import tempfile
from pathlib import Path

import pymupdf

from ..core import pdfdoc
from ..core.pagesel import PageError, parse_pages
from ..core.interface import tr

# Una página muy grande (un plano, un cartel) a 600 ppp pasaría de los mil millones de píxeles: por encima de
# este número se dibuja a la resolución que cabe en él.
MAX_PIXELS = 120_000_000


class RasterizeError(Exception):
    pass


@dataclasses.dataclass(frozen=True)
class Options:
    dpi: int = 300
    fmt: str = "png"  # 'png' (sin pérdida, el texto nítido) o 'jpg' (más pequeño)
    quality: int = 85  # of the JPEG, 1-100
    gray: bool = False


def _dpi_for(rect: pymupdf.Rect, dpi: int) -> int:
    """DPI, or less if a page of RECT (in points) would be above MAX_PIXELS at it."""
    pixels = rect.width * rect.height * (dpi / 72) ** 2
    if pixels <= MAX_PIXELS:
        return dpi
    return max(1, int(dpi * (MAX_PIXELS / pixels) ** 0.5))


def _empty_stream(doc: pymupdf.Document) -> int:
    xref = doc.get_new_xref()
    doc.update_object(xref, "<<>>")
    doc.update_stream(xref, b"")
    return xref


def rasterize_page(doc: pymupdf.Document, index: int, options: Options) -> None:
    """Page INDEX of DOC drawn as a picture (with its annotations and fields) that takes the place of all it
    had."""
    page = doc[index]
    # Se dibuja sin girar y se vuelve a girar al final: la imagen ocupa la página tal como está guardada, y el
    # giro (/Rotate) la sigue mostrando como antes.
    rotation = page.rotation
    if rotation:
        page.set_rotation(0)
    cs = pymupdf.csGRAY if options.gray else pymupdf.csRGB
    pix = page.get_pixmap(dpi=_dpi_for(page.rect, options.dpi), colorspace=cs, alpha=False, annots=True)
    # The annotations and the fields are in the picture now: as objects they would show twice (and a field
    # keeps its value as text).
    for widget in list(page.widgets()):
        page.delete_widget(widget)
    for annot in list(page.annots()):
        try:
            page.delete_annot(annot)
        except (RuntimeError, ValueError):  # (a popup goes with its parent)
            pass
    page = doc[index]
    # Un contenido nuevo y vacío, y unos recursos vacíos, en lugar de vaciar los que tenía: esos objetos pueden
    # ser compartidos con otras páginas (que no se convierten). Las fuentes sin uso se van al guardar.
    doc.xref_set_key(page.xref, "Contents", f"{_empty_stream(doc)} 0 R")
    doc.xref_set_key(page.xref, "Resources", "<<>>")
    page = doc[index]
    if options.fmt == "jpg":
        page.insert_image(page.rect, stream=pix.tobytes("jpeg", jpg_quality=options.quality))
    else:
        page.insert_image(page.rect, pixmap=pix)
    if rotation:
        page.set_rotation(rotation)


def rasterize(source: Path, target: Path, options: Options, pages: list[int] | str | None = None,
              password: str = "") -> int:
    """SOURCE with PAGES (0-based, or written as '1-3, 7, last'; None: all) made pictures, saved as TARGET
    (which may be SOURCE). Returns how many pages were. Its protection, if it has one, is kept."""
    doc = pdfdoc.open_pdf(source, password, RasterizeError, RasterizeError)
    if isinstance(pages, str):
        try:
            pages = parse_pages(pages, doc.page_count)
        except PageError as e:
            doc.close()
            raise RasterizeError(str(e)) from None
    chosen = sorted(set(range(doc.page_count) if pages is None else pages))
    fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=target.parent)
    os.close(fd)
    try:
        if any(not 0 <= i < doc.page_count for i in chosen):
            raise RasterizeError(tr("The document has only {count} pages", count=doc.page_count))
        for i in chosen:
            rasterize_page(doc, i, options)
        keep = pdfdoc.kept_encryption(doc)
        # garbage=3: las fuentes, imágenes y flujos que ya nadie usa salen del archivo (con ellas, el texto).
        doc.save(tmp, garbage=3, deflate=True, encryption=keep)
        doc.close()
        os.replace(tmp, target)
        return len(chosen)
    except BaseException as e:
        if not doc.is_closed:
            doc.close()
        Path(tmp).unlink(missing_ok=True)
        if isinstance(e, (OSError, RuntimeError, ValueError)):
            raise RasterizeError(tr("{path} cannot be written: {error}", path=target, error=e)) from None
        raise
