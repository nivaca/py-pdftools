"""File > PDF properties: what a document is (its metadata, its file, its contents, its security) and the
fonts it uses, as core/docinfo.py finds them; nothing is changed here (the metadata are changed in Redact >
Metadata, for the redacted copy). Copy puts all of it on the clipboard, as text."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QFormLayout, QLabel, QTabWidget, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from ..core import docinfo
from ..core.interface import tr


class DocumentPropertiesDialog(QDialog):
    def __init__(self, doc, path=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Document properties"))
        self.items = docinfo.properties(doc, path)
        self.font_list = docinfo.fonts(doc)
        tabs = QTabWidget()
        tabs.addTab(self._document_tab(), tr("Document"))
        tabs.addTab(self._fonts_tab(), tr("Fonts ({count})", count=len(self.font_list)))
        self.tabs = tabs
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        copy = buttons.addButton(tr("Copy"), QDialogButtonBox.ButtonRole.ActionRole)
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self.as_text()))
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(tabs)
        lay.addWidget(buttons)
        self.resize(620, 560)

    def _document_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        heading = None
        for head, label, value in self.items:
            if head != heading:
                heading = head
                title = QLabel(f"<b>{tr(head)}</b>")
                form.addRow(title)
            shown = QLabel(value or "—")
            shown.setWordWrap(True)
            # (se puede seleccionar y copiar, como en un visor)
            shown.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow(tr(label) + ":", shown)
        return page

    def _fonts_tab(self) -> QWidget:
        tree = QTreeWidget()
        tree.setRootIsDecorated(False)
        tree.setHeaderLabels([tr("Font"), tr("Type"), tr("Embedded"), tr("Encoding"), tr("Pages")])
        for font in self.font_list:
            embedded = (tr("Yes, a subset") if font["subset"] else tr("Yes")) if font["embedded"] else tr("No")
            item = QTreeWidgetItem([font["name"], font["type"], embedded, font["encoding"],
                                    docinfo.page_ranges(font["pages"])])
            item.setToolTip(4, item.text(4))
            tree.addTopLevelItem(item)
        for col in range(4):
            tree.resizeColumnToContents(col)
        self.fonts_tree = tree
        return tree

    def as_text(self) -> str:
        """All of it as plain text: the properties, then the fonts."""
        lines, heading = [], None
        for head, label, value in self.items:
            if head != heading:
                heading = head
                lines += ["", tr(head)] if lines else [tr(head)]
            lines.append(f"  {tr(label)}: {value or '—'}")
        lines += ["", tr("Fonts ({count})", count=len(self.font_list))]
        for font in self.font_list:
            embedded = (tr("Yes, a subset") if font["subset"] else tr("Yes")) if font["embedded"] else tr("No")
            lines.append(f"  {font['name']} ({font['type']}; {tr('Embedded')}: {embedded}; "
                         f"{font['encoding']}): {docinfo.page_ranges(font['pages'])}")
        return "\n".join(lines) + "\n"
