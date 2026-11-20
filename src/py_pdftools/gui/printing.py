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

MAX_DPI = 300  # (more only makes the job heavier)


def printable(source: Path, annotations: list[Annotation], password: str = "", with_them: bool = True
              ) -> pymupdf.Document:
    """SOURCE with ANNOTATIONS made part of its pages (or with none, if not WITH_THEM), in memory."""
    doc = annots.open_pdf(source, password)
    if with_them:
        annots.apply(doc, annotations)
    else:
        annots.remove_editable(doc)
    doc.bake(annots=True, widgets=True)
    return doc


def print_document(parent, source: Path, annotations: list[Annotation], password: str = "", page: int = 0,
                   with_them: bool = True) -> bool:
    """Ask for a printer and the pages, and print. Returns whether it was printed."""
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setDocName(source.name)
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
        dpi = min(printer.resolution(), MAX_DPI)
        for i, n in enumerate(numbers):
            if i:
                printer.newPage()
            pix = doc[n].get_pixmap(dpi=dpi, alpha=False)
            image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
            area = painter.viewport()
            scale = min(area.width() / image.width(), area.height() / image.height())
            w, h = image.width() * scale, image.height() * scale
            painter.drawImage(QRectF((area.width() - w) / 2, (area.height() - h) / 2, w, h), image)
    finally:
        painter.end()
    return True
