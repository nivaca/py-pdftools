"""Making and changing the links of the document (mixed into MainWindow): the tool Link (in Annotate) draws
the area of a new link, and a click on a link with it changes or removes it; Edit > Links also makes links
of the web and mail addresses written in the text, and removes all the links. A link goes to a page of the
document, to a web or mail address, or to a page of another PDF. Each change is a step of the history (see
working.edit_document).

(PyMuPDF gives the area of a link as the page is shown, but writes it as the page is in the file, before
it is turned: links are written in that space, and a link changed is written anew.)"""

from __future__ import annotations

import pymupdf
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLineEdit,
    QPushButton, QRadioButton, QSpinBox, QVBoxLayout, QWidget,
)

from ..core.interface import ntr, tr
from .links import ADDRESS

def target_of(link: dict) -> dict:
    """What LINK goes to, as LinkDialog says it: {'kind': 'page'|'uri'|'file', ...}."""
    kind = link.get("kind")
    if kind == pymupdf.LINK_URI:
        return {"kind": "uri", "uri": link.get("uri", "")}
    if kind == pymupdf.LINK_GOTOR:
        return {"kind": "file", "file": link.get("file", ""), "page": max(0, link.get("page", 0))}
    return {"kind": "page", "page": max(0, link.get("page", 0))}


def link_dict(target: dict, rect) -> dict:
    """The link PyMuPDF writes: to TARGET, over RECT (as the page is in the file)."""
    r = pymupdf.Rect(rect)
    if target["kind"] == "uri":
        return {"kind": pymupdf.LINK_URI, "from": r, "uri": target["uri"]}
    if target["kind"] == "file":
        return {"kind": pymupdf.LINK_GOTOR, "from": r, "file": target["file"], "page": target["page"],
                "to": pymupdf.Point(0, 0)}
    return {"kind": pymupdf.LINK_GOTO, "from": r, "page": target["page"], "to": pymupdf.Point(0, 0)}


def address_uri(text: str) -> str:
    """The address of a web or mail address written in the text."""
    address = text.rstrip(".,;:)]}»”'")
    if "@" in address and not address.lower().startswith(("http", "www")):
        return "mailto:" + address
    return address if address.lower().startswith("http") else "https://" + address


class LinkDialog(QDialog):
    """Where a link goes: a page of the document (by its number or label), an address, or another PDF."""

    def __init__(self, count: int, labels: list[str], target: dict | None = None, can_remove: bool = False,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Link") if target is None else tr("Change the link"))
        self.removing = False
        self.group = QButtonGroup(self)
        self.to_page, self.to_uri, self.to_file = (QRadioButton(tr(t)) for t in (
            "A page of this document", "A web or mail address", "A page of another PDF"))
        for b in (self.to_page, self.to_uri, self.to_file):
            self.group.addButton(b)
        self.page = QComboBox()
        for n in range(count):
            label = labels[n] if n < len(labels) else ""
            self.page.addItem(str(n + 1) + (f"  ({label})" if label and label != str(n + 1) else ""), n)
        self.uri = QLineEdit()
        self.uri.setPlaceholderText("https://…  /  name@example.org")
        self.file = QLineEdit()
        browse = QPushButton(tr("Choose…"))
        browse.clicked.connect(self._choose_file)
        self.file_page = QSpinBox(minimum=1, maximum=100000)
        row = QHBoxLayout()
        row.addWidget(self.file, 1)
        row.addWidget(browse)
        file_box = QWidget()
        file_box.setLayout(row)
        form = QFormLayout()
        form.addRow(self.to_page, self.page)
        form.addRow(self.to_uri, self.uri)
        form.addRow(self.to_file, file_box)
        form.addRow(tr("Its page:"), self.file_page)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        if can_remove:
            remove = buttons.addButton(tr("Remove the link"), QDialogButtonBox.ButtonRole.DestructiveRole)
            remove.clicked.connect(self._remove)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.b_ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)
        target = target or {"kind": "page", "page": 0}
        {"page": self.to_page, "uri": self.to_uri, "file": self.to_file}[target["kind"]].setChecked(True)
        if target["kind"] == "page":
            self.page.setCurrentIndex(min(target.get("page", 0), count - 1))
        elif target["kind"] == "uri":
            self.uri.setText(target.get("uri", ""))
        else:
            self.file.setText(target.get("file", ""))
            self.file_page.setValue(target.get("page", 0) + 1)
        for w in (self.uri, self.file):
            w.textChanged.connect(lambda _t: self._check())
        self.group.buttonToggled.connect(lambda *_a: self._check())
        self.uri.textEdited.connect(lambda _t: self.to_uri.setChecked(True))
        self.file.textEdited.connect(lambda _t: self.to_file.setChecked(True))
        self.page.activated.connect(lambda _i: self.to_page.setChecked(True))
        self.setMinimumWidth(480)
        self._check()

    def _choose_file(self):
        name, _ = QFileDialog.getOpenFileName(self, tr("A page of another PDF"), self.file.text(),
                                              tr("PDF files (*.pdf)"))
        if name:
            self.file.setText(name)
            self.to_file.setChecked(True)

    def _check(self):
        ok = self.to_page.isChecked() or (self.to_uri.isChecked() and bool(self.uri.text().strip())) or \
            (self.to_file.isChecked() and bool(self.file.text().strip()))
        self.b_ok.setEnabled(ok)

    def _remove(self):
        self.removing = True
        self.accept()

    def target(self) -> dict | None:
        """What was chosen; None to remove the link."""
        if self.removing:
            return None
        if self.to_uri.isChecked():
            text = self.uri.text().strip()
            return {"kind": "uri", "uri": address_uri(text) if ADDRESS.fullmatch(text) else text}
        if self.to_file.isChecked():
            return {"kind": "file", "file": self.file.text().strip(), "page": self.file_page.value() - 1}
        return {"kind": "page", "page": self.page.currentData()}


class LinkEditMixin:
    """(Mixed into MainWindow: it uses its document, its canvas and edit_document.)"""

    def _build_link_tool(self, menu, tools_menu):
        """The tool Link (in the menu of the tools, and in the toolbar of the notes) and Edit > Links."""
        from .window import icon

        act = QAction(icon("pdftools-link"), tr("Link"), self, checkable=True)
        act.setToolTip(tr("Drag on the page to make a link there; click a link to change or remove it"))
        act.setStatusTip(act.toolTip())
        act.triggered.connect(lambda: self.set_tool("link"))
        self.tool_actions["select"].actionGroup().addAction(act)
        self.tool_actions["link"] = act
        tools_menu.addAction(act)
        sub = menu.addMenu(tr("Links"))
        sub.setToolTipsVisible(True)
        sub.addAction(act)
        self.a_links_from_text = self._action(
            sub, tr("Make links of the addresses in the text"), lambda: self.links_from_text(),
            tip=tr("Every web and mail address written in the text, on every page, becomes a link"))
        self.a_links_remove = self._action(sub, tr("Remove all the links…"), lambda: self.remove_all_links(),
                                           tip=tr("Take every link out of the document"))
        self.canvas.link_drawn.connect(self.new_link)
        self.canvas.link_edit.connect(self.change_link)

    def _link_rect(self, page: int, shown) -> pymupdf.Rect:
        """SHOWN (a rectangle as page PAGE is shown) as the page is in the file."""
        return (pymupdf.Rect(shown) * self.doc[page].derotation_matrix).normalize()

    def ask_link(self, target: dict | None = None, can_remove: bool = False) -> dict | None | bool:
        """The target chosen in LinkDialog; None to remove the link; False if cancelled."""
        dialog = LinkDialog(self.count, self.page_labels(), target, can_remove, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        return dialog.target()

    def new_link(self, page: int, shown) -> bool:
        """A link over SHOWN (as the page is shown) of PAGE, to where the user says."""
        if self.doc is None:
            return False
        target = self.ask_link()
        if not target:
            return False
        rect = self._link_rect(page, shown)
        return self.edit_document(lambda doc: doc[page].insert_link(link_dict(target, rect)),
                                  message=tr("Link made"))

    def change_link(self, page: int, link: dict) -> bool:
        """LINK (of PAGE, as get_links gives it) sent elsewhere, or removed."""
        if self.doc is None or link.get("in_text"):
            return False
        chosen = self.ask_link(target_of(link), can_remove=True)
        if chosen is False:
            return False
        rect = self._link_rect(page, link["from"])
        xref = link.get("xref", 0)

        def edit(doc):
            p = doc[page]
            old = next((lk for lk in p.get_links() if lk.get("xref") == xref), None)
            if old is not None:
                p.delete_link(old)
            if chosen is not None:
                p.insert_link(link_dict(chosen, rect))

        return self.edit_document(edit, message=tr("Link removed") if chosen is None else tr("Link changed"))

    def links_from_text(self) -> int:
        """A link over each web or mail address of the text that has none. Returns how many were made."""
        if self.doc is None:
            return 0
        found: dict[int, list] = {}
        for n in range(self.count):
            page = self.doc[n]
            # Las palabras vienen como la página está en el archivo; los enlaces, como se muestra: se comparan
            # en el espacio del archivo, que es el que insert_link espera.
            have = [self._link_rect(n, lk["from"]) for lk in page.get_links()]
            for w in page.get_text("words"):
                m = ADDRESS.search(w[4])
                if not m:
                    continue
                r = pymupdf.Rect(w[:4])
                if any(r.intersects(h) for h in have):
                    continue
                found.setdefault(n, []).append((r, address_uri(m.group(0))))
        total = sum(map(len, found.values()))
        if not total:
            self.status(tr("No address of the text is without a link"))
            return 0

        def edit(doc):
            for n, items in found.items():
                for rect, uri in items:
                    doc[n].insert_link({"kind": pymupdf.LINK_URI, "from": rect, "uri": uri})

        if not self.edit_document(edit, message=ntr("{count} link made", "{count} links made", total)):
            return 0
        return total

    def remove_all_links(self, ask: bool = True) -> int:
        if self.doc is None:
            return 0
        total = sum(len(self.doc[n].get_links()) for n in range(self.count))
        if not total:
            self.status(tr("The document has no links"))
            return 0
        if ask and not self.confirm_remove_links(total):
            return 0

        def edit(doc):
            for page in doc:
                for lk in page.get_links():
                    page.delete_link(lk)

        if not self.edit_document(edit, message=ntr("{count} link removed", "{count} links removed", total)):
            return 0
        return total

    def confirm_remove_links(self, total: int) -> bool:
        from PySide6.QtWidgets import QMessageBox

        return QMessageBox.question(self, tr("Remove all the links"),
                                    ntr("Remove the {count} link of the document?",
                                        "Remove the {count} links of the document?", total)) \
            == QMessageBox.StandardButton.Yes

