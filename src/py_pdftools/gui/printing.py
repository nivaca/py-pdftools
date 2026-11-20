"""Printing the document with its annotations (or without them): each page is
rendered at the printer's resolution and drawn on a sheet, fitted to it."""

from __future__ import annotations

from pathlib import Path

import pymupdf
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtPrintSupport import QPrintDialog, QPrinter

from ..annotate import annots
from ..annotate.annots import Annotation
from ..core.interface import tr

# A 300 ppp el texto ya sale nítido en casi cualquier impresora; más solo engorda el trabajo enviado.
MAX_DPI = 300  # (more only makes the job heavier)


def printable(source: Path, annotations: list[Annotation], password: str = "", with_them: bool = True
              ) -> pymupdf.Document:
    """SOURCE with ANNOTATIONS made part of its pages (or with none, if not WITH_THEM), in memory."""
    doc = annots.open_pdf(source, password)
    # Las anotaciones de la ventana se escriben en una copia en memoria; el archivo en disco no se toca.
    if with_them:
        annots.apply(doc, annotations)
    else:
        annots.remove_editable(doc)
    # bake() turns annotations and form fields into page content, so get_pixmap draws them all.
    doc.bake(annots=True, widgets=True)
    return doc


def print_document(parent, source: Path, annotations: list[Annotation], password: str = "", page: int = 0,
                   with_them: bool = True) -> bool:
    """Ask for a printer and the pages, and print. Returns whether it was printed."""
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setDocName(source.name)
    # The document is not open yet, so the page count is unknown: the range is left wide open and
    # print_document clips it to the real number of pages.
    printer.setFromTo(1, 1)
    dialog = QPrintDialog(printer, parent)
    dialog.setWindowTitle(tr("Print"))
    dialog.setOption(QPrintDialog.PrintDialogOption.PrintPageRange, True)
    dialog.setOption(QPrintDialog.PrintDialogOption.PrintCurrentPage, True)
    dialog.setMinMax(1, 999999)
    if dialog.exec() != QPrintDialog.DialogCode.Accepted:
        return False
    doc = printable(source, annotations, password, with_them)
    try:
        if printer.printRange() == QPrinter.PrintRange.PageRange:
            # El diálogo cuenta las páginas desde 1; aquí se pasan a índices desde 0, sin salir del documento.
            numbers = list(range(max(printer.fromPage() - 1, 0), min(printer.toPage(), doc.page_count)))
        elif printer.printRange() == QPrinter.PrintRange.CurrentPage:
            numbers = [page]
        else:
            numbers = list(range(doc.page_count))
        return render(printer, doc, numbers)
    finally:
        doc.close()


def render(printer, doc: pymupdf.Document, numbers: list[int]) -> bool:
    """Draw pages NUMBERS of DOC on PRINTER (any QPagedPaintDevice: a QPdfWriter too), one on each sheet."""
    painter = QPainter()
    if not painter.begin(printer):
        return False
    try:
        # Se renderiza a la resolución de la impresora, con un tope: una impresora de 1200 ppp no gana nada.
        dpi = min(printer.resolution(), MAX_DPI)
        for i, n in enumerate(numbers):
            if i:
                printer.newPage()
            # Sin .copy(): pix sigue vivo hasta que drawImage termina en esta misma vuelta.
            pix = doc[n].get_pixmap(dpi=dpi, alpha=False)
            image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
            area = painter.viewport()
            # TODO: a landscape page on a portrait sheet is only shrunk, not turned; rotating it would
            # use the sheet better.
            scale = min(area.width() / image.width(), area.height() / image.height())
            w, h = image.width() * scale, image.height() * scale
            # La página se centra en la hoja, con sus proporciones.
            painter.drawImage(QRectF((area.width() - w) / 2, (area.height() - h) / 2, w, h), image)
    finally:
        painter.end()
    return True
