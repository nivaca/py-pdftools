"""The bookmarks of the document (its outline), in a panel of every mode (View > Bookmarks): a tree that
goes to the place each bookmark points at, filtered as typed (the parents of what matches stay), with the
label of each page, and the bookmark of the page shown marked as one reads.

They are edited there too (its right-click menu, F2, Delete): added at the place shown, renamed, deleted,
moved, indented, made bold, italic or coloured, pointed at the place shown; or made from the headings of
the text (the lines in a larger type than the body). Each change is a change of the document itself (see
working.py), undone like the others."""

from __future__ import annotations

from collections import Counter

import pymupdf
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QColorDialog, QDockWidget, QHBoxLayout, QHeaderView, QInputDialog, QLineEdit, QMenu, QMessageBox, QToolButton,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ..core.interface import tr

PAGE, TOP = Qt.ItemDataRole.UserRole, Qt.ItemDataRole.UserRole + 1  # (the page, 0-based; the y it points at)
DEST = Qt.ItemDataRole.UserRole + 2  # (the rest of the bookmark, as PyMuPDF gives it: its kind, colour, style...)
HEADING_LEVELS = 3  # (the largest sizes of type above the body's become these levels of bookmarks)


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
        # Editarlos: el menú del botón derecho, F2 para el título, Supr para borrar.
        tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tree.customContextMenuRequested.connect(self._outline_menu)
        tree.itemChanged.connect(self._outline_renamed)
        for keys, slot in (("F2", self.rename_bookmark), ("Delete", self.delete_bookmark)):
            QShortcut(QKeySequence(keys), tree, slot, context=Qt.ShortcutContext.WidgetShortcut)
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
        tree.blockSignals(True)
        try:
            self._outline_fill()
        finally:
            tree.blockSignals(False)
        self._outline_top()
        self._filter_outline(self.outline_filter.text())
        self._outline_mark(self.page)

    def _outline_fill(self):
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
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            item.setData(0, PAGE, n)
            to = dest.get("to")
            item.setData(0, TOP, float(to.y) if to is not None and n >= 0 else None)
            item.setData(0, DEST, {k: v for k, v in dest.items() if k not in ("xref", "to", "page")})
            item.setToolTip(0, title)
            font = item.font(0)
            font.setBold(bool(dest.get("bold")))
            font.setItalic(bool(dest.get("italic")))
            item.setFont(0, font)
            if dest.get("color"):
                item.setForeground(0, QColor.fromRgbF(*dest["color"][:3]))
            # (a bookmark of level L hangs from the last one of level L-1)
            parents = parents[:max(level - 1, 0)]
            if parents:
                parents[-1].addChild(item)
            else:
                tree.addTopLevelItem(item)
            parents.append(item)

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

    # ----------------------------------------------------------------- editing them

    def _outline_items(self) -> list[tuple[int, QTreeWidgetItem]]:
        """Every bookmark, in order: (its level, from 1; its item)."""
        out = []

        def walk(item, level):
            out.append((level, item))
            for i in range(item.childCount()):
                walk(item.child(i), level + 1)

        for i in range(self.outline_tree.topLevelItemCount()):
            walk(self.outline_tree.topLevelItem(i), 1)
        return out

    def _outline_toc(self) -> list:
        """The tree as PyMuPDF's set_toc takes it."""
        toc = []
        for level, item in self._outline_items():
            n, top = item.data(0, PAGE), item.data(0, TOP)
            dest = dict(item.data(0, DEST) or {})
            if n is not None and n >= 0:
                dest["kind"] = pymupdf.LINK_GOTO
                dest["page"] = n
                if top is not None:
                    dest["to"] = pymupdf.Point(0, top)
            toc.append([level, item.text(0), (n + 1) if n is not None else -1, dest])
        return toc

    def write_outline(self, toc: list | None = None, message: str = "") -> bool:
        """Give the document the outline TOC (else the tree as it is), as a change of it (undone like the others);
        the bookmark chosen stays chosen."""
        toc = self._outline_toc() if toc is None else toc
        chosen = self.outline_tree.currentItem()
        place = [i for i, (_, item) in enumerate(self._outline_items()) if item is chosen]
        # Los niveles no pueden saltar: un marcador no puede estar dos niveles por debajo del anterior.
        for i, entry in enumerate(toc):
            entry[0] = max(1, min(entry[0], (toc[i - 1][0] + 1) if i else 1))
        done = self.edit_document(lambda doc: doc.set_toc(toc), message=message or tr("Bookmarks changed"))
        if done and place:
            items = self._outline_items()
            if place[0] < len(items):
                item = items[place[0]][1]
                for parent in _parents(item):
                    parent.setExpanded(True)
                self.outline_tree.setCurrentItem(item)
        return done

    def _outline_menu(self, pos):
        tree = self.outline_tree
        item = tree.itemAt(pos)
        if item is not None:
            tree.setCurrentItem(item)
        menu = QMenu(self)
        has = item is not None
        menu.addAction(tr("Add a bookmark here…"), self.add_bookmark).setEnabled(self.doc is not None)
        menu.addSeparator()
        menu.addAction(tr("Rename"), self.rename_bookmark).setEnabled(has)
        menu.addAction(tr("Point it here"), self.point_bookmark_here).setEnabled(has)
        menu.addAction(tr("Delete"), self.delete_bookmark).setEnabled(has)
        menu.addSeparator()
        for text, how in ((tr("Move up"), "up"), (tr("Move down"), "down"), (tr("Indent"), "in"),
                          (tr("Outdent"), "out")):
            menu.addAction(text, lambda h=how: self.move_bookmark(h)).setEnabled(has)
        style = menu.addMenu(tr("Style"))
        style.setEnabled(has)
        for text, key in ((tr("Bold"), "bold"), (tr("Italic"), "italic")):
            a = style.addAction(text, lambda k=key: self.style_bookmark(k))
            a.setCheckable(True)
            a.setChecked(bool(has and (item.data(0, DEST) or {}).get(key)))
        style.addAction(tr("Colour…"), lambda: self.style_bookmark("color"))
        style.addAction(tr("No colour"), lambda: self.style_bookmark("nocolor"))
        menu.addSeparator()
        menu.addAction(tr("Bookmarks from the headings…"), self.bookmarks_from_headings).setEnabled(self.doc is not None)
        self.show_menu(menu, tree.viewport().mapToGlobal(pos))

    def _view_top(self) -> float:
        """The height (in points, on the page shown) at the top of the view."""
        page = self.canvas.pages.get(self.page)
        if page is None:
            return 0.0
        return max(0.0, page.mapFromScene(self.canvas.mapToScene(0, 0)).y())

    def add_bookmark(self, title: str | None = None) -> bool:
        """A bookmark of the place shown, after the one chosen (at its level), or at the end."""
        if self.doc is None:
            return False
        if title is None:
            title, ok = QInputDialog.getText(self, tr("Add a bookmark"), tr("Its title:"),
                                             text=tr("Page {page}", page=self.page_box.text() or self.page + 1))
            if not ok or not title.strip():
                return False
        item = QTreeWidgetItem([title.strip(), ""])
        item.setData(0, PAGE, self.page)
        item.setData(0, TOP, self._view_top())
        item.setData(0, DEST, {})
        chosen = self.outline_tree.currentItem()
        if chosen is not None and chosen.parent() is not None:
            parent = chosen.parent()
            parent.insertChild(parent.indexOfChild(chosen) + 1, item)
        elif chosen is not None:
            self.outline_tree.insertTopLevelItem(self.outline_tree.indexOfTopLevelItem(chosen) + 1, item)
        else:
            self.outline_tree.addTopLevelItem(item)
        self.outline_tree.setCurrentItem(item)
        return self.write_outline(message=tr("Bookmark added"))

    def _set_item(self, item: QTreeWidgetItem, values: dict):
        """Change the data of ITEM without the tree taking it for a rename (see _outline_renamed)."""
        self.outline_tree.blockSignals(True)
        try:
            for role, value in values.items():
                item.setData(0, role, value)
        finally:
            self.outline_tree.blockSignals(False)

    def rename_bookmark(self):
        item = self.outline_tree.currentItem()
        if item is not None:
            self.outline_tree.editItem(item, 0)

    def _outline_renamed(self, item: QTreeWidgetItem, column: int):
        if column == 0 and item.text(0).strip():
            self.write_outline(message=tr("Bookmark renamed"))

    def delete_bookmark(self) -> bool:
        """The bookmark chosen, and those under it."""
        item = self.outline_tree.currentItem()
        if item is None:
            return False
        (item.parent() or self.outline_tree.invisibleRootItem()).removeChild(item)
        return self.write_outline(message=tr("Bookmark deleted"))

    def point_bookmark_here(self) -> bool:
        """The bookmark chosen leads to the place shown now."""
        item = self.outline_tree.currentItem()
        if item is None:
            return False
        dest = dict(item.data(0, DEST) or {})
        for key in ("uri", "file", "nameddest"):  # (now a place in this document, not elsewhere)
            dest.pop(key, None)
        self._set_item(item, {PAGE: self.page, TOP: self._view_top(), DEST: dest})
        return self.write_outline(message=tr("Bookmark moved to page {page}", page=self.page + 1))

    def move_bookmark(self, how: str) -> bool:
        """Up or down among its siblings; in (under the one before it) or out (after its parent)."""
        item = self.outline_tree.currentItem()
        if item is None:
            return False
        root = self.outline_tree.invisibleRootItem()
        parent = item.parent() or root
        i = parent.indexOfChild(item)
        if how == "up" and i > 0:
            parent.insertChild(i - 1, parent.takeChild(i))
        elif how == "down" and i < parent.childCount() - 1:
            parent.insertChild(i + 1, parent.takeChild(i))
        elif how == "in" and i > 0:
            before = parent.child(i - 1)
            before.addChild(parent.takeChild(i))
        elif how == "out" and parent is not root:
            grand = parent.parent() or root
            grand.insertChild(grand.indexOfChild(parent) + 1, parent.takeChild(i))
        else:
            return False
        self.outline_tree.setCurrentItem(item)
        return self.write_outline(message=tr("Bookmark moved"))

    def style_bookmark(self, key: str) -> bool:
        """Bold or italic (switched), a colour (asked), or none."""
        item = self.outline_tree.currentItem()
        if item is None:
            return False
        dest = dict(item.data(0, DEST) or {})
        if key in ("bold", "italic"):
            dest[key] = not dest.get(key)
        elif key == "color":
            start = QColor.fromRgbF(*dest["color"][:3]) if dest.get("color") else QColor("black")
            chosen = QColorDialog.getColor(start, self, tr("Colour"))
            if not chosen.isValid():
                return False
            dest["color"] = (chosen.redF(), chosen.greenF(), chosen.blueF())
        else:
            dest.pop("color", None)
        self._set_item(item, {DEST: dest})
        return self.write_outline(message=tr("Bookmark changed"))

    def headings(self) -> list[tuple[int, str, int, float]]:
        """The headings of the text: lines in a larger type than the body's (the most common size), the
        HEADING_LEVELS largest sizes as levels 1, 2 ...: (level, text, page, y), in reading order."""
        lines, sizes = [], Counter()
        for page in self.doc:
            for block in page.get_text("dict").get("blocks", []):
                for line in block.get("lines", []):
                    text = " ".join(s["text"] for s in line["spans"]).split()
                    if not text:
                        continue
                    size = round(max(s["size"] for s in line["spans"]), 1)
                    sizes[size] += len(text)
                    lines.append((size, " ".join(text), page.number, line["bbox"][1]))
        if not sizes:
            return []
        body = sizes.most_common(1)[0][0]
        levels = sorted((s for s in sizes if s > body * 1.15), reverse=True)[:HEADING_LEVELS]
        return [(levels.index(size) + 1, text[:200], n, y) for size, text, n, y in lines if size in levels]

    def bookmarks_from_headings(self) -> bool:
        """Bookmarks from the headings of the text (see headings), instead of those there are, or after them."""
        found = self.headings() if self.doc is not None else []
        if not found:
            self.status(tr("No heading was found: no line is in a larger type than the body"), error=True)
            return False
        toc = [[level, text, n + 1, {"kind": pymupdf.LINK_GOTO, "page": n, "to": pymupdf.Point(0, y)}]
               for level, text, n, y in found]
        if self.outline_tree.topLevelItemCount():
            answer = QMessageBox.question(
                self, tr("Bookmarks from the headings"),
                tr("Replace the bookmarks the document has with these {count}? (No: add them after them)",
                   count=len(toc)),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
            if answer == QMessageBox.StandardButton.Cancel:
                return False
            if answer == QMessageBox.StandardButton.No:
                toc = self._outline_toc() + toc
        return self.write_outline(toc, message=tr("Bookmarks made from {count} headings", count=len(found)))


def _parents(item: QTreeWidgetItem) -> list[QTreeWidgetItem]:
    out = []
    while item.parent() is not None:
        item = item.parent()
        out.append(item)
    return out

