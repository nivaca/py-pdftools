"""The bookmarks of the document (its outline), in a panel of every mode (View > Bookmarks): a tree that
goes to the place each bookmark points at, filtered as typed (the parents of what matches stay), with the
label of each page, and the bookmark of the page shown marked as one reads."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QDockWidget, QHBoxLayout, QHeaderView, QLineEdit, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
    QWidget,
)

from ..core.interface import tr

PAGE, TOP = Qt.ItemDataRole.UserRole, Qt.ItemDataRole.UserRole + 1  # (the page, 0-based; the y it points at)


class OutlineMixin:
    """(Mixed into MainWindow: it uses its attributes.)"""

    def _build_outline(self):
        """The panel of the bookmarks: a dock of its own, not of a mode (each mode keeps whether it shows)."""
        self.outline_filter = QLineEdit()
        self.outline_filter.setPlaceholderText(tr("Find a bookmark…"))
        self.outline_filter.setClearButtonEnabled(True)
        self.outline_filter.textChanged.connect(self._filter_outline)
        self.outline_tree = tree = QTreeWidget()
        tree.setColumnCount(2)
        tree.setHeaderLabels([tr("Bookmark"), tr("Page")])
        tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        tree.header().setStretchLastSection(False)
        # Un clic (o Intro) lleva al sitio del marcador; recorrer el árbol con las flechas no mueve la vista.
        tree.itemClicked.connect(self._outline_go)
        tree.itemActivated.connect(self._outline_go)
        buttons = QHBoxLayout()
        for text, tip, slot in ((tr("Expand all"), tr("Show every bookmark"), tree.expandAll),
                                (tr("Top level"), tr("Only the bookmarks of the first level"), self._outline_top),
                                (tr("Collapse"), tr("Close every branch"), tree.collapseAll)):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            buttons.addWidget(b)
        buttons.addStretch(1)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self.outline_filter)
        lay.addWidget(tree, 1)
        lay.addLayout(buttons)
        self.outline_dock = dock = QDockWidget(tr("Bookmarks"), self)
        dock.setObjectName("bookmarks")
        dock.setWidget(inner)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        dock.hide()
        self.a_outline = dock.toggleViewAction()
        self.a_outline.setText(tr("Bookmarks"))
        self.a_outline.setShortcut(QKeySequence("F5"))
        self.a_outline.setToolTip(tr("The bookmarks of the document (its outline), to go to its parts"))

    def outline_refresh(self):
        """The tree, as the document's outline is now."""
        tree = self.outline_tree
        tree.clear()
        if self.doc is None:
            return
        try:
            toc = self.doc.get_toc(simple=False)
        except (RuntimeError, ValueError):
            toc = []
        found = self.page_labels() if hasattr(self, "page_labels") else []
        parents: list[QTreeWidgetItem] = []
        for entry in toc:
            level, title, page = entry[0], entry[1], entry[2]
            dest = entry[3] if len(entry) > 3 and isinstance(entry[3], dict) else {}
            n = page - 1
            label = found[n] if 0 <= n < len(found) and found[n] else (str(page) if page > 0 else "")
            item = QTreeWidgetItem([title.strip() or tr("(no title)"), label])
            item.setData(0, PAGE, n)
            to = dest.get("to")
            item.setData(0, TOP, float(to.y) if to is not None and n >= 0 else None)
            item.setToolTip(0, title)
            # (a bookmark of level L hangs from the last one of level L-1)
            parents = parents[:max(level - 1, 0)]
            if parents:
                parents[-1].addChild(item)
            else:
                tree.addTopLevelItem(item)
            parents.append(item)
        self._outline_top()
        self._filter_outline(self.outline_filter.text())
        self._outline_mark(self.page)

    def _outline_top(self):
        self.outline_tree.collapseAll()
        for i in range(self.outline_tree.topLevelItemCount()):
            self.outline_tree.topLevelItem(i).setExpanded(False)

    def _outline_go(self, item: QTreeWidgetItem, _column: int = 0):
        n = item.data(0, PAGE)
        if n is None or not 0 <= n < self.count:
            return
        top = item.data(0, TOP)
        self.show_page(n)
        if top is not None:
            self.canvas.scroll_to(n, top)

    def _filter_outline(self, text: str):
        """Only the bookmarks whose title has TEXT (any case), with their parents; all, without TEXT."""
        text = text.strip().casefold()

        def walk(item: QTreeWidgetItem) -> bool:
            shown = False
            for i in range(item.childCount()):
                shown = walk(item.child(i)) or shown
            mine = not text or text in item.text(0).casefold()
            item.setHidden(not (mine or shown))
            if text and shown:
                item.setExpanded(True)
            return mine or shown

        for i in range(self.outline_tree.topLevelItemCount()):
            walk(self.outline_tree.topLevelItem(i))

    def _outline_mark(self, page: int):
        """Mark the bookmark of PAGE (the last one at or before it, the deepest shown), without moving to it."""
        best = None

        def walk(item: QTreeWidgetItem):
            nonlocal best
            n = item.data(0, PAGE)
            if n is not None and 0 <= n <= page and (best is None or n >= best.data(0, PAGE)):
                best = item
            if item.isExpanded():
                for i in range(item.childCount()):
                    walk(item.child(i))

        for i in range(self.outline_tree.topLevelItemCount()):
            walk(self.outline_tree.topLevelItem(i))
        tree = self.outline_tree
        tree.blockSignals(True)
        tree.setCurrentItem(best) if best is not None else tree.clearSelection()
        tree.blockSignals(False)
