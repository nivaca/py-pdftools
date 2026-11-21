"""Edit > Word index (from the author's pdf-word-finder; the search is in pages/wordfinder.py): the terms, one on
each line (or read from a list), searched in the document open, as it is in the window, with its labels; the
report shows on which pages each one appears, as lines ready for an index, or in detail, with fragments of
context; it is copied, or saved as text or as CSV. A double click on a line of the detailed report goes to
its page."""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QMessageBox,
    QPlainTextEdit, QPushButton, QSpinBox, QSplitter, QVBoxLayout, QWidget,
)

from ..core.interface import ntr, tr
from ..pages import wordfinder as wf


class WordIndexDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle(tr("Word index"))
        self.result: wf.Result | None = None
        self._pages: wf.Pages | None = None  # (el texto de las páginas, leído una vez por diálogo)

        self.terms = QPlainTextEdit()
        self.terms.setPlaceholderText(tr("One word, phrase or pattern on each line (re: before a regular "
                                         "expression; # begins a comment)"))
        load = QPushButton(tr("Read a list…"))
        load.clicked.connect(self.load_list)
        left = QWidget()
        lay = QVBoxLayout(left)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QLabel(tr("Terms:")))
        lay.addWidget(self.terms, 1)
        lay.addWidget(load)

        def box(text, tip=""):
            check = QCheckBox(text)
            check.setToolTip(tip)
            return check

        self.whole = box(tr("Whole words only"), tr("Unticked, the terms are found inside words too"))
        self.whole.setChecked(True)
        self.case = box(tr("Match case"))
        self.accents = box(tr("Ignore accents"))
        self.dehyphen = box(tr("Join the words split at the end of a line"))
        self.dehyphen.setChecked(True)
        self.regex = box(tr("Every term is a regular expression"), tr("Or put re: before each one that is"))
        self.regex_word = box(tr("Regular expressions, too, as whole words"))
        self.logical = box(tr("Also the page in the file, where it differs from the label"))
        self.alpha = box(tr("In alphabetical order"))
        self.detailed = box(tr("Detailed: how many times, and on which pages"))
        self.context = box(tr("With context:"))
        self.width = QSpinBox()
        self.width.setRange(10, 400)
        self.width.setValue(60)
        self.width.setSuffix(" " + tr("characters"))
        self.context.toggled.connect(lambda on: self.detailed.setChecked(True) if on else None)
        options = QGridLayout()
        for i, check in enumerate((self.whole, self.case, self.accents, self.dehyphen, self.regex, self.regex_word,
                                   self.logical, self.alpha, self.detailed)):
            options.addWidget(check, i % 5, i // 5)
        ctx = QHBoxLayout()
        ctx.addWidget(self.context)
        ctx.addWidget(self.width)
        ctx.addStretch(1)
        options.addLayout(ctx, 4, 1)

        self.notes = QLabel()
        self.notes.setWordWrap(True)
        self.notes.setStyleSheet("color: palette(placeholder-text);")
        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.report.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.report.mouseDoubleClickEvent = self._go_to_line
        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.addWidget(QLabel(tr("Where they are:")))
        rlay.addWidget(self.notes)
        rlay.addWidget(self.report, 1)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([260, 540])

        find = QPushButton(tr("Find"))
        find.setDefault(True)
        find.clicked.connect(self.find)
        self.b_copy = QPushButton(tr("Copy"))
        self.b_copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.report.toPlainText()))
        self.b_txt = QPushButton(tr("Save as text…"))
        self.b_txt.setToolTip(tr("The list, in alphabetical order"))
        self.b_txt.clicked.connect(self.save_txt)
        self.b_csv = QPushButton(tr("Save as CSV…"))
        self.b_csv.setToolTip(tr("A row for each term and page, with how many times and the context"))
        self.b_csv.clicked.connect(self.save_csv)
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.reject)
        for b in (self.b_copy, self.b_txt, self.b_csv):
            b.setEnabled(False)
        buttons = QHBoxLayout()
        buttons.addWidget(find)
        buttons.addStretch(1)
        for b in (self.b_copy, self.b_txt, self.b_csv, close):
            buttons.addWidget(b)

        lay = QVBoxLayout(self)
        lay.addWidget(split, 1)
        lay.addLayout(options)
        lay.addLayout(buttons)
        self.resize(860, 600)

    # ----------------------------------------------------------------- the search

    def options(self) -> wf.Options:
        return wf.Options(regex=self.regex.isChecked(), regex_word=self.regex_word.isChecked(),
                          substring=not self.whole.isChecked(), case_sensitive=self.case.isChecked(),
                          ignore_accents=self.accents.isChecked(), dehyphenate=self.dehyphen.isChecked(),
                          context_width=self.width.value() if self.context.isChecked() else None)

    def pages(self) -> wf.Pages:
        """The text and the labels of the document as the window has it (its labels, as Foliate shows them)."""
        if self._pages is None:
            w = self.window
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                # (las etiquetas de la ventana, con lo que aún no se ha guardado; sin intervalos, no las hay)
                self._pages = wf.pages_of(w.doc, w.page_labels() if w.ranges else [])
            finally:
                QApplication.restoreOverrideCursor()
        return self._pages

    def find(self) -> bool:
        terms = wf.read_terms(self.terms.toPlainText().splitlines())
        if not terms:
            self.notes.setText(tr("Write the terms to find, one on each line."))
            return False
        try:
            self.result = wf.search(self.pages(), terms, self.options())
        except wf.PatternError as exc:
            QMessageBox.warning(self, tr("Word index"), str(exc))
            return False
        report, notes = wf.build_report(self.result, show_logical=self.logical.isChecked(),
                                        detailed=self.detailed.isChecked() or self.context.isChecked(),
                                        alphabetical=self.alpha.isChecked())
        found = sum(1 for t in terms if self.result.hits.get(t))
        summary = ntr("{count} term found", "{count} terms found", found) + ", " + ntr(
            "{count} time", "{count} times", self.result.total()) + ", " + ntr(
            "on {count} page", "on {count} pages", self.result.pages_with_hits()) + "."
        self.notes.setText("\n".join(x for x in (summary, notes) if x))
        self.report.setPlainText(report)
        for b in (self.b_copy, self.b_txt, self.b_csv):
            b.setEnabled(bool(report))
        return True

    def _go_to_line(self, event):
        """A double click on a page of the detailed report (or a page of the list) goes to it."""
        QPlainTextEdit.mouseDoubleClickEvent(self.report, event)
        if self.result is None:
            return
        cursor = self.report.cursorForPosition(event.position().toPoint())
        line = cursor.block().text()
        m = re.match(r"\s{4}(\S+)", line)  # (una página del informe detallado, con su sangría)
        word = cursor.selectedText().strip(",") if m is None else m.group(1)
        labels = self.pages().labels
        if word in labels:
            self.window.show_page(labels.index(word))

    # ----------------------------------------------------------------- the list, and saving

    def load_list(self):
        name, _ = QFileDialog.getOpenFileName(self, tr("A list of terms"), self.window.last_dir(),
                                              tr("Text files (*.txt);;All files (*)"))
        if not name:
            return
        try:
            text = Path(name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            QMessageBox.warning(self, tr("Word index"), tr("{path} could not be read: {error}", path=name,
                                                            error=exc))
            return
        self.terms.setPlainText(text)

    def _save(self, title, filter_text, suffix, write):
        if self.result is None:
            return
        stem = self.window.path.stem if self.window.path is not None else "index"
        start = str(Path(self.window.last_dir()) / f"{stem}-{tr('index')}{suffix}")
        name, _ = QFileDialog.getSaveFileName(self, title, start, filter_text)
        if not name:
            return
        try:
            write(name)
        except OSError as exc:
            QMessageBox.warning(self, tr("Word index"), tr("{path} could not be written: {error}", path=name,
                                                            error=exc))
            return
        self.window.status(tr("Saved {path}", path=name))

    def save_txt(self):
        self._save(tr("Save the list as text"), tr("Text files (*.txt)"), ".txt",
                   lambda name: wf.write_txt(name, self.result, self.logical.isChecked()))

    def save_csv(self):
        self._save(tr("Save as CSV"), tr("CSV files (*.csv)"), ".csv", lambda name: wf.write_csv(name, self.result))

