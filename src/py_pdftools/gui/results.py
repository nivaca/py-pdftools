"""El panel Resultados de la búsqueda (Ver > Paneles, F8): todos los lugares donde está un texto, en una lista,
cada uno con su página y unas palabras alrededor, con lo encontrado en negrita. Un clic (o Intro) lleva a ese
lugar y lo muestra un momento, como la búsqueda rápida. Busca como ella: sin distinguir mayúsculas ni acentos,
o con las opciones de su casilla (mayúsculas, palabras enteras). Al abrirse, toma el texto de la búsqueda
rápida si el suyo está vacío; la lista se vacía cuando el documento cambia."""

from __future__ import annotations

import html

from PySide6.QtCore import QModelIndex, QRectF, QSize, Qt
from PySide6.QtGui import QAction, QKeySequence, QPalette, QTextDocument
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDockWidget, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QStyle,
    QStyledItemDelegate, QStyleOptionViewItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ..annotate import annots
from ..annotate.search import Match, find_text
from ..core.interface import tr

MATCH = Qt.ItemDataRole.UserRole  # (the index of the place found, in the list of matches)


class _Rich(QStyledItemDelegate):
    """The context of a place found, with the text found in bold (the column of the context)."""

    def paint(self, painter, option, index: QModelIndex):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text, opt.text = opt.text, ""
        style = opt.widget.style() if opt.widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        doc = QTextDocument()
        doc.setDefaultFont(opt.font)
        # (el color del texto, el de una fila elegida si lo está: el documento no lo toma solo de la paleta)
        selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        role = QPalette.ColorRole.HighlightedText if selected else QPalette.ColorRole.Text
        colour = opt.palette.color(role).name()
        doc.setHtml(f'<span style="color:{colour}">{_marked(text)}</span>')
        doc.setDocumentMargin(2)
        painter.save()
        painter.translate(opt.rect.topLeft())
        doc.drawContents(painter, QRectF(0, 0, opt.rect.width(), opt.rect.height()))
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        size = super().sizeHint(option, index)
        return QSize(size.width(), max(size.height(), option.fontMetrics.height() + 6))


def _short(context: str, before: int = 24) -> str:
    """CONTEXT on one line, with at most BEFORE characters before the text found (cut where a word begins, and
    marked with an ellipsis), so that what was found shows in a narrow panel."""
    context = " ".join(context.split())
    start = context.find("[")
    if start > before:
        cut = context[start - before:start]
        context = "…" + (cut.split(" ", 1)[-1] if " " in cut else cut) + context[start:]
    return context


def _marked(context: str) -> str:
    """CONTEXT (with the text found in [brackets], see search.Match) as HTML, the text found in bold."""
    start, end = context.find("["), context.rfind("]")
    if start < 0 or end < start:
        return html.escape(context)
    return (html.escape(context[:start]) + "<b>" + html.escape(context[start + 1:end]) + "</b>" +
            html.escape(context[end + 1:]))


class ResultsMixin:
    """(Mixed into MainWindow: it uses its attributes.)"""

    def _build_results(self):
        """The panel of the results: a dock of its own, hidden until it is asked for (F8)."""
        self.results_box = QLineEdit()
        self.results_box.setPlaceholderText(tr("Find in the text"))
        self.results_box.setClearButtonEnabled(True)
        self.results_box.setToolTip(tr("Enter lists every place where the text is"))
        self.results_box.returnPressed.connect(self.list_results)
        self.results_case = QCheckBox(tr("Match case"))
        self.results_whole = QCheckBox(tr("Whole words"))
        for box in (self.results_case, self.results_whole):
            box.toggled.connect(lambda _: self.list_results() if self.results_box.text().strip() else None)
        self.results_count = QLabel()
        self.results_count.setStyleSheet("color: palette(placeholder-text);")
        self.results_list = tree = QTreeWidget()
        tree.setColumnCount(2)
        tree.setHeaderLabels([tr("Page"), tr("Context")])
        tree.setRootIsDecorated(False)
        tree.setUniformRowHeights(True)
        tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        tree.setItemDelegateForColumn(1, _Rich(tree))
        tree.setAccessibleName(tr("Search results"))
        # Un clic o Intro llevan al lugar; recorrer la lista con las flechas también, para leerlos seguidos.
        tree.itemClicked.connect(lambda item, _c: self.go_result(item))
        tree.itemActivated.connect(lambda item, _c: self.go_result(item))
        tree.currentItemChanged.connect(lambda item, _old: self.go_result(item) if tree.hasFocus() else None)
        options = QHBoxLayout()
        options.addWidget(self.results_case)
        options.addWidget(self.results_whole)
        options.addStretch(1)
        inner = QWidget()
        inner.setMinimumWidth(320)
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self.results_box)
        lay.addLayout(options)
        lay.addWidget(self.results_count)
        lay.addWidget(tree, 1)
        self.results_dock = dock = QDockWidget(tr("Search results"), self)
        dock.setObjectName("results")
        dock.setWidget(inner)
        dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        dock.hide()
        dock.visibilityChanged.connect(self._results_shown)
        self.a_results = dock.toggleViewAction()
        self.a_results.setText(tr("Search results"))
        self.a_results.setShortcut(QKeySequence("F8"))
        self.a_results.setToolTip(tr("Every place where a text is, in a list, each with the words around it"))
        self.result_matches: list[Match] = []
        self._results_cache: dict = {}
        self._results_doc = None
        self.a_find_all = QAction(tr("Find all…"), self)
        self.a_find_all.setToolTip(tr("Every place of the text of Find as you type, in the panel Search results"))
        self.a_find_all.triggered.connect(self.find_all)

    def _results_shown(self, visible: bool):
        # (al abrirse, el texto de Buscar mientras se escribe, si el panel no tiene uno, y el cursor en la casilla)
        if not visible:
            return
        if not self.results_box.text().strip():
            text = self.find_bar.text().strip()
            if text:
                self.results_box.setText(text)
                self.list_results()
        self.results_box.setFocus()

    def find_all(self):
        """Find > Find all: the panel shown, with every place of the text of Find as you type (or its own)."""
        text = self.find_bar.text().strip()
        self.results_dock.show()
        self.results_dock.raise_()
        if text:
            self.results_box.setText(text)
            self.list_results()
        self.results_box.setFocus()

    def results_clear(self):
        """The list emptied (another document, or this one changed): its places may no longer be there."""
        self.result_matches = []
        self._results_cache = {}
        self.results_list.clear()
        self.results_count.setText("")

    def list_results(self) -> int:
        """Every place of the text of the box, in the list; how many."""
        self.results_list.clear()
        self.result_matches = []
        text = self.results_box.text()
        if self.doc is None or not text.strip():
            self.results_count.setText("")
            return 0
        if self._results_doc is not self.doc:  # (otro documento: sus páginas se vuelven a leer)
            self._results_cache, self._results_doc = {}, self.doc

        def progress(done, total):
            self.results_count.setText(tr("Looking… page {page} of {count}", page=done, count=total))
            QApplication.processEvents()
            return True

        case = self.results_case.isChecked()
        self.result_matches = find_text(self.doc, text, None, case=case, whole_words=self.results_whole.isChecked(),
                                        accents=not case, progress=progress, cache=self._results_cache)
        labels = self.page_labels() if hasattr(self, "page_labels") else []
        items = []
        for i, m in enumerate(self.result_matches):
            label = labels[m.page] if m.page < len(labels) and labels[m.page] else str(m.page + 1)
            item = QTreeWidgetItem([label, _short(m.context)])
            item.setData(0, MATCH, i)
            item.setToolTip(1, " ".join(m.context.split()))
            items.append(item)
        self.results_list.addTopLevelItems(items)
        count = len(self.result_matches)
        pages = len({m.page for m in self.result_matches})
        self.results_count.setText(tr("Not found") if not count else
                                   tr("Places found: {count} (pages: {pages})", count=count, pages=pages))
        return count

    def go_result(self, item: QTreeWidgetItem | None):
        """The place of ITEM, brought into view and shown for a moment."""
        if item is None:
            return
        i = item.data(0, MATCH)
        if i is None or not 0 <= i < len(self.result_matches):
            return
        m = self.result_matches[i]
        if m.page >= self.count:
            return
        self.remember_place()
        self.canvas.flash(m.page, annots.union(m.rects))
