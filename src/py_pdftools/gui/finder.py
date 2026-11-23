"""Find and highlight: look for a word, a phrase, words with wildcards or a
regular expression (without minding accents, if asked; with u and v, i and j as
one, for Latin and medieval texts), on all the pages or on the page shown, go
from one place found to the next, and highlight (or underline, strike out...)
all the places found, or those chosen. The searches made are remembered."""

from __future__ import annotations

import json
import re

from PySide6.QtCore import QStringListModel, Qt, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QCompleter, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QVBoxLayout,
)

from ..annotate.annots import MARKUP, NAMES
from ..core.interface import N_, ntr, tr
from ..annotate.search import Match, find_text

HISTORY = 20  # searches remembered
# N_ solo marca los nombres para traducir; tr() los traduce al llenar el desplegable.
SCOPES = [("all", N_("All pages")), ("page", N_("This page")), ("from", N_("From this page to the end"))]


def _history(value) -> list[str]:
    """The searches remembered, from what the window keeps (JSON: see state.py)."""
    try:
        found = json.loads(value) if isinstance(value, str) and value else []
    except ValueError:
        return []
    # Anything that is not a list of strings (a hand-edited or older setting) is ignored, not trusted.
    return [h for h in found if isinstance(h, str)][:HISTORY] if isinstance(found, list) else []


class FindDialog(QDialog):
    """Not modal: the window stays usable while it is open. It asks the window (through the
    signals) to show a place found, and to mark the places chosen."""

    show_match = Signal(object)  # Match
    mark = Signal(list, str)  # [Match], the kind of mark

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle(tr("Find and highlight"))
        self.matches: list[Match] = []
        self.searching = False
        self.stop_asked = False
        # Enter en el campo de búsqueda busca, igual que el botón Buscar.
        self.query = QLineEdit()
        self.query.setPlaceholderText(tr("Text to find"))
        self.query.returnPressed.connect(self.search)
        self.settings = window.settings  # (where the window keeps its own state: the same on every system)
        self.history = _history(self.settings.value("find_history", ""))
        self.history_model = QStringListModel(self.history)
        # The completer offers the searches remembered, whatever their case.
        completer = QCompleter(self.history_model, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.query.setCompleter(completer)
        self.case = QCheckBox(tr("Match case"))
        self.whole = QCheckBox(tr("Whole words"))
        self.regex = QCheckBox(tr("Regular expression"))
        self.accents = QCheckBox(tr("Ignore accents"))
        self.accents.setToolTip(tr("accion finds acción; caesar, cæsar"))
        self.uv = QCheckBox(tr("u = v, i = j"))
        self.uv.setToolTip(tr("As in Latin and medieval texts: iustitia finds justitia; uirtus, virtus"))
        self.wildcards = QCheckBox(tr("Wildcards"))
        self.wildcards.setToolTip(tr("* stands for any letters, ? for one: iust* finds iustitia, iustus, iusto…"))
        # Estas tres opciones se recuerdan entre sesiones; las otras (mayúsculas, palabras, regex) empiezan
        # siempre desmarcadas.
        for box, key, usual in ((self.accents, "find_accents", True), (self.uv, "find_uv", False),
                                (self.wildcards, "find_wildcards", True)):
            box.setChecked(self.settings.value(key, usual, type=bool))
            box.toggled.connect(lambda on, k=key: self.settings.setValue(k, on))
        # TODO: the cache is emptied only when another Document object is searched; if the text of the
        # same document changes (a redaction applied in place), the search still sees the old text.
        self.cache: dict = {}  # (the text of the pages read: see find_text)
        self.cache_doc = None
        self.scope = QComboBox()
        for value, name in SCOPES:
            self.scope.addItem(tr(name), value)
        self.kind = QComboBox()
        for kind in MARKUP:
            self.kind.addItem(tr(NAMES[kind]), kind)
        self.find_button = QPushButton(tr("Find"))
        self.find_button.setDefault(True)
        self.find_button.clicked.connect(self.search)
        self.results = QListWidget()
        self.results.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        # Moving through the list with the keys shows each place as it becomes current.
        self.results.itemDoubleClicked.connect(lambda item: self.show_match.emit(self._match(item)))
        self.results.currentItemChanged.connect(lambda item, _: self.show_match.emit(self._match(item))
                                                if item is not None else None)
        self.summary = QLabel()
        self.mark_all = QPushButton(tr("Mark all"))
        self.mark_all.clicked.connect(lambda: self._mark(self.matches))
        self.mark_chosen = QPushButton(tr("Mark those chosen"))
        self.mark_chosen.clicked.connect(lambda: self._mark([self._match(i) for i in self.results.selectedItems()]))
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.close)
        options = QHBoxLayout()
        for box in (self.case, self.whole, self.regex):
            options.addWidget(box)
        options.addStretch(1)
        more = QHBoxLayout()
        for box in (self.accents, self.uv, self.wildcards):
            more.addWidget(box)
        more.addStretch(1)
        self.previous = QPushButton(tr("Previous"))
        self.previous.clicked.connect(lambda: self.step(-1))
        self.next = QPushButton(tr("Next"))
        self.next.clicked.connect(lambda: self.step(1))
        form = QFormLayout()
        row = QHBoxLayout()
        row.addWidget(self.query, 1)
        row.addWidget(self.find_button)
        form.addRow(tr("Find:"), row)
        form.addRow("", options)
        form.addRow("", more)
        form.addRow(tr("Where:"), self.scope)
        form.addRow(tr("Mark as:"), self.kind)
        buttons = QHBoxLayout()
        buttons.addWidget(self.previous)
        buttons.addWidget(self.next)
        buttons.addWidget(self.mark_all)
        buttons.addWidget(self.mark_chosen)
        buttons.addStretch(1)
        buttons.addWidget(close)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.results, 1)
        lay.addWidget(self.summary)
        lay.addLayout(buttons)
        self.resize(560, 520)
        self._enable()

    def start(self, text: str = ""):
        if text:
            self.query.setText(text)
        self.show()
        self.raise_()
        self.activateWindow()
        self.query.setFocus()
        self.query.selectAll()

    def _match(self, item: QListWidgetItem) -> Match:
        return self.matches[item.data(Qt.ItemDataRole.UserRole)]

    def step(self, by: int):
        """Show the place found BY places after (or before) the one shown, going round."""
        if not self.matches:
            return
        row = self.results.currentRow()
        # Sin fila actual, Siguiente va al primero y Anterior al último; si no, da la vuelta.
        row = (row + by) % len(self.matches) if row >= 0 else (0 if by > 0 else len(self.matches) - 1)
        self.results.setCurrentRow(row)

    def _remember(self, query: str):
        # La búsqueda repetida sube al principio, sin duplicarse, y la lista no pasa de HISTORY.
        self.history = [query] + [h for h in self.history if h != query][:HISTORY - 1]
        self.history_model.setStringList(self.history)
        # (as JSON: a list in QSettings comes back as it went only on some systems; on Windows, one of a
        # single item comes back as that item)
        self.settings.setValue("find_history", json.dumps(self.history, ensure_ascii=False))

    def _enable(self):
        # Previous and Next need two places at least; with one, it is already shown.
        self.previous.setEnabled(len(self.matches) > 1 and not self.searching)
        self.next.setEnabled(len(self.matches) > 1 and not self.searching)
        self.mark_all.setEnabled(bool(self.matches) and not self.searching)
        self.mark_chosen.setEnabled(bool(self.matches) and not self.searching)

    def pages(self) -> list[int] | None:
        scope = self.scope.currentData()
        if scope == "page":
            return [self.window.page]
        if scope == "from":
            # Desde la página mostrada hasta el final del documento.
            return list(range(self.window.page, self.window.count))
        # None: all the pages (find_text reads it so).
        return None

    def search(self):
        """Find (or, while it looks, stop)."""
        # El mismo botón sirve para detener: mientras se busca dice Detener.
        if self.searching:
            self.stop_asked = True
            return
        doc = self.window.doc
        self.matches, self.stop_asked = [], False
        self.results.clear()
        if doc is None or not self.query.text().strip():
            self.summary.setText("")
            self._enable()
            return
        self.searching = True
        self.find_button.setText(tr("Stop"))
        self._enable()

        # Called by find_text after each page: processEvents keeps the window alive (and lets Stop be
        # clicked); returning False stops the search.
        def progress(done, total):
            self.summary.setText(tr("Looking… page {page} of {count}", page=done, count=total))
            QApplication.processEvents()
            return not self.stop_asked

        error = ""
        try:
            if self.cache_doc is not doc:  # (another document: its pages are read again)
                self.cache, self.cache_doc = {}, doc
            # Los comodines no se combinan con una expresión regular: con regex, * y ? son de la regex.
            self.matches = find_text(doc, self.query.text(), self.pages(), self.case.isChecked(),
                                     self.whole.isChecked(), self.regex.isChecked(), progress,
                                     accents=self.accents.isChecked(), uv=self.uv.isChecked(),
                                     wildcards=self.wildcards.isChecked() and not self.regex.isChecked(),
                                     cache=self.cache)
            self._remember(self.query.text().strip())
        # Una expresión regular mal escrita se informa en el resumen, sin cuadro de error.
        except re.error as e:
            error = tr("The regular expression is not right: {error}", error=e)
            self.matches = []
        finally:
            self.searching = False
            self.find_button.setText(tr("Find"))
        for n, m in enumerate(self.matches):
            item = QListWidgetItem(tr("Page {page}", page=m.page + 1) + ": " + m.context)
            # Each row keeps the index of its match, so the list can be sorted or filtered without losing it.
            item.setData(Qt.ItemDataRole.UserRole, n)
            self.results.addItem(item)
        if error:
            self.summary.setText(error)
        elif self.matches:
            # Places and pages are counted apart: one page can hold several places.
            self.summary.setText(ntr("{count} place found", "{count} places found", len(self.matches))
                                 + ntr(", on {count} page", ", on {count} pages",
                                       len({m.page for m in self.matches})))
        else:
            self.summary.setText(tr("Not found"))
        self._enable()

    def _mark(self, matches: list[Match]):
        if matches:
            self.mark.emit(matches, self.kind.currentData())
