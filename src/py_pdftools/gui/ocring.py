"""OCR in the window: the mode OCR (its panel, toolbar and menu), and OCR from the menu of the thumbnails
in the other modes. The text of scanned pages is read by tesseract (see core/ocr.py) and written into the
document, invisible, under the pictures of the pages, as a change of the document itself (see working.py:
undone like the others, saved with the document)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QDockWidget, QLabel, QMenu, QProgressDialog, QPushButton, QVBoxLayout, QWidget,
)

from ..core import ocr
from ..core.interface import ntr, tr
from .modes import Mode

KIND = "ocr"


class OcrMixin:
    """(Mixed into MainWindow: it uses its attributes.)"""

    _scanned: tuple | None = None  # (the file's stamp, its scanned pages): see scanned_pages

    def _build_ocr(self) -> Mode:
        """The mode OCR: its panel (what to read and how), its toolbar and its menu."""
        from .ocr_dialog import OcrOptions

        self.a_recognise = self._action(None, tr("Recognise text (OCR)"), self.recognise_from_panel,
                                        "Ctrl+Shift+O",
                                        tip=tr("Read the text of the pages chosen in the panel with tesseract and "
                                               "write it into the document, invisible, under their pictures: it "
                                               "can then be found, copied and marked"))
        self.a_ocr_languages = self._action(None, tr("Languages…"), self.manage_ocr_languages,
                                            tip=tr("The languages tesseract can read here; download, update or "
                                                   "remove its more accurate models (and osd, to turn pages)"))
        m = QMenu(tr("&OCR"), self)
        for act in (self.a_recognise, self.a_ocr, self.a_ocr_languages):
            m.addAction(act)
        self.menuBar().insertMenu(self.m_layers.menuAction(), m)
        bars = [self.toolbar_of("ocr", tr("OCR"), [self.a_recognise, self.a_ocr, self.a_ocr_languages])]
        self.ocr_options = OcrOptions(self.prefs.ocr_language, self)
        self.ocr_summary = QLabel()
        self.ocr_summary.setWordWrap(True)
        self.ocr_summary.setStyleSheet("color: palette(placeholder-text);")
        read = QPushButton(tr("Recognise text"))
        read.clicked.connect(self.recognise_from_panel)
        self.ocr_read_button = read
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.addWidget(self.ocr_summary)
        lay.addWidget(self.ocr_options)
        lay.addWidget(read)
        lay.addStretch(1)
        dock = QDockWidget(tr("OCR"), self)
        dock.setObjectName("ocr")
        dock.setWidget(inner)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self.hints[KIND] = tr("Choose the pages to read and their languages in the panel, and press Recognise "
                              "text: the text of scanned pages is written into the document, under their pictures, "
                              "so that it can be found, copied and marked. Choose several pages in the thumbnails "
                              "with Ctrl or Shift.")
        # Nada es suyo: las anotaciones se ven, pero no se tocan en este modo.
        return Mode(KIND, lambda a: False, bars=bars, docks=[dock], menus=[m.menuAction()],
                    actions=[self.a_recognise], entered=lambda: self.ocr_refresh(full=True))

    def scanned_pages(self) -> list[int]:
        """The scanned pages without text (0-based), found once for each state of the file (reading the text
        of every page takes a while on a long document)."""
        if self.doc is None:
            return []
        stamp = (id(self.doc), self.file_stamp())
        if self._scanned is None or self._scanned[0] != stamp:
            self._scanned = (stamp, [page.number for page in self.doc if ocr.scanned(page)])
        return list(self._scanned[1])

    def ocr_refresh(self, full: bool = False):
        """The panel of the mode OCR as the document is now: the pages chosen, the one shown (FULL: also the
        scanned pages, and tesseract's languages)."""
        if not hasattr(self, "ocr_options") or self.mode != KIND:
            return
        if full:
            self.ocr_options.fill_languages(self.ocr_options.language() or self.prefs.ocr_language)
            self.ocr_options.refresh_osd()
        has = self.doc is not None and ocr.available()
        self.ocr_read_button.setEnabled(has)
        if self.doc is None:
            self.ocr_summary.setText(tr("No document is open."))
            return
        if not ocr.available():
            self.ocr_summary.setText(tr("tesseract is not installed: there is no OCR"))
            return
        scanned = self.scanned_pages()
        selected = [n - 1 for n in self.selected_pages()]
        self.ocr_options.set_pages(self.count, scanned, selected if len(selected) > 1 else [], self.page)
        self.ocr_summary.setText(
            tr("Tesseract {version}.", version=ocr.version()) + " "
            + (ntr("{count} page is a scan without text.", "{count} pages are scans without text.", len(scanned))
               if scanned else tr("No page is a scan without text.")))

    def recognise_from_panel(self) -> bool:
        """The button of the panel (and its action): read what the panel says, and write the text."""
        if self.path is None or not hasattr(self, "ocr_options"):
            return False
        if self.mode != KIND:  # (Ctrl+Shift+O elsewhere: the mode OCR, with its panel)
            self.set_mode(KIND)
        options = self.ocr_options
        if not options.check():
            return False
        done = self.recognise_and_write(options.page_list(), options.language(), options.rotate.isChecked(),
                                        options.review.isChecked(), options.doubtful.value())
        self.ocr_refresh(full=False)
        return done

    def recognise_dialog(self, chosen: bool = False) -> bool:
        """OCR from the menu of the thumbnails: ask what to read and how (OcrDialog: with CHOSEN, the pages
        chosen are what it offers first), then read and write it."""
        from .ocr_dialog import OcrDialog

        if self.path is None:
            return False
        if not ocr.available():
            self.warn(tr("Recognise text (OCR)"), tr("tesseract is not installed: there is no OCR"))
            return False
        # (the pages chosen in the thumbnails, or in Foliate's list: several, or one asked for with CHOSEN)
        selected = [n - 1 for n in self.selected_pages()]
        if len(selected) < 2 and not chosen:
            selected = []
        dialog = OcrDialog(self, self.count, self.scanned_pages(), selected, self.page, self.prefs.ocr_language,
                           prefer_chosen=chosen)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        o = dialog.options
        return self.recognise_and_write(o.page_list(), o.language(), o.rotate.isChecked(), o.review.isChecked(),
                                        o.doubtful.value())

    def recognise_and_write(self, pages: list[int], language: str, rotate: bool = False, review: bool = True,
                            doubtful: float = ocr.DOUBTFUL) -> bool:
        """Read PAGES, let the doubtful words (below DOUBTFUL) be checked if REVIEW (ReviewDialog), and write
        the text."""
        from .ocr_dialog import ReviewDialog

        results = self.recognise(pages, language, rotate, doubtful)
        if results is None:
            return False
        corrections: dict[int, dict[int, str]] = {}
        if review and any(r.doubtful(doubtful) for r in results):
            dialog = ReviewDialog(self, results, doubtful)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                self.status(tr("Nothing was written"))
                return False
            corrections = dialog.corrections()
        return self.write_recognised(results, corrections)

    def recognise(self, pages: list[int], language: str, rotate: bool = False,
                  doubtful: float = ocr.DOUBTFUL) -> list[ocr.PageResult] | None:
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
            return ocr.run(self.file, self.password, pages, language, rotate=rotate, doubtful=doubtful,
                           progress=step)
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

    def manage_ocr_languages(self):
        """OCR > Languages (also in the settings): see ocr_languages.py; then the panel, as things are now."""
        from .ocr_languages import LanguagesDialog

        LanguagesDialog(self).exec()
        self.ocr_refresh(full=True)
