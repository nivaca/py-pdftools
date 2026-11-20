"""OCR in the window (Edit > Recognise text): the text of scanned pages read by tesseract (see
core/ocr.py) and written into the document, invisible, under the pictures of the pages, as a change of
the document itself (see working.py: undone like the others, saved with the document)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QProgressDialog

from ..core import ocr
from ..core.interface import ntr, tr


class OcrMixin:
    """(Mixed into MainWindow: it uses its attributes.)"""

    def recognise_dialog(self) -> bool:
        """Ask what to read and how (OcrDialog), read it, let the doubtful words be checked (ReviewDialog),
        and write the text."""
        from .ocr_dialog import OcrDialog, ReviewDialog

        if self.path is None:
            return False
        if not ocr.available():
            self.warn(tr("Recognise text (OCR)"), tr("tesseract is not installed: there is no OCR"))
            return False
        scanned = [page.number for page in self.doc if ocr.scanned(page)]
        selected = [n - 1 for n in self.selected_pages()] if self.page_list.selectedItems() else []
        dialog = OcrDialog(self, self.count, scanned, selected, self.page, self.prefs.ocr_language)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        results = self.recognise(dialog.page_list(), dialog.language.currentText(), dialog.rotate.isChecked())
        if results is None:
            return False
        corrections: dict[int, dict[int, str]] = {}
        if dialog.review.isChecked() and any(r.doubtful() for r in results):
            review = ReviewDialog(self, results)
            if review.exec() != QDialog.DialogCode.Accepted:
                self.status(tr("Nothing was written"))
                return False
            corrections = review.corrections()
        return self.write_recognised(results, corrections)

    def recognise(self, pages: list[int], language: str, rotate: bool = False) -> list[ocr.PageResult] | None:
        """Read PAGES (0-based; those that have text already are left out) with tesseract, showing how far it
        has got; None if it was stopped or failed (said in the status bar)."""
        self.canvas.commit_text()
        self.keep_comment()
        # (a page with text already would have its text twice)
        pages = [n for n in pages if 0 <= n < self.count and ocr.scanned(self.doc[n])]
        if not pages:
            self.status(tr("No page of those chosen is a scan without text"), error=True)
            return None
        progress = QProgressDialog(tr("Reading the scanned pages…"), tr("Stop"), 0, len(pages), self)
        # Window-modal: the document cannot be changed while its pages are being read.
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(500)

        def step(done: int, of: int) -> bool:
            progress.setValue(done)
            progress.setLabelText(tr("Reading the scanned pages: {done} of {of}…", done=done, of=of))
            QApplication.processEvents()
            return not progress.wasCanceled()

        try:
            return ocr.run(self.file, self.password, pages, language, rotate=rotate, progress=step)
        except ocr.OcrError as e:
            self.status(str(e), error=True)
            return None
        finally:
            progress.close()

    def write_recognised(self, results: list[ocr.PageResult],
                         corrections: dict[int, dict[int, str]] | None = None) -> bool:
        """Write the words of RESULTS into the document (as corrected), as one change of it."""
        corrections = corrections or {}
        written = [0]

        def edit(doc):
            for result in results:
                written[0] += ocr.write_words(doc[result.number], result, corrections.get(result.number))

        turned = sum(1 for r in results if r.rotate)
        message = ntr("Text recognised on {count} page", "Text recognised on {count} pages", len(results))
        done = self.edit_document(edit, message=message)
        if done:
            words = ntr("{count} word", "{count} words", written[0])
            extra = ", " + ntr("{count} page turned", "{count} pages turned", turned) if turned else ""
            self.status(f"{message}: {words}{extra}")
        return done
