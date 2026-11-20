"""Moving through the document (mixed into MainWindow): following the links the canvas reports (see
links.py), and going to a place of it (a page, a height on it)."""

from __future__ import annotations

from pathlib import Path

import pymupdf
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox

from ..core.interface import tr

# named actions a link may have: (where it goes from the page shown)
NAMED_ACTIONS = {"NextPage": 1, "PrevPage": -1, "FirstPage": "first", "LastPage": "last"}


class NavigationMixin:
    """(Mixed into MainWindow: it uses its attributes.)"""

    def go_place(self, page: int, y: float | None = None):
        """Show PAGE (0-based), with the height Y of it (in points, from its top) at the top of the view."""
        if self.doc is None or not 0 <= page < self.count:
            return
        self.show_page(page)
        if y is not None:
            self.canvas.scroll_to(page, y)

    def follow_link(self, page: int, link: dict) -> bool:
        """Follow LINK (clicked on PAGE): to a place of the document, to another PDF, or (asked first) to a
        web or mail address. Links that start a program are not followed."""
        kind = link.get("kind")
        if kind == pymupdf.LINK_GOTO:
            to = link.get("to")
            self.go_place(link.get("page", 0), to.y if to is not None else None)
            return True
        if kind == pymupdf.LINK_NAMED:
            return self._follow_named(link)
        if kind == pymupdf.LINK_URI:
            return self.open_address(link.get("uri", ""))
        if kind == pymupdf.LINK_GOTOR:
            return self._follow_other_file(link)
        if kind == pymupdf.LINK_LAUNCH:
            self.status(tr("A link that starts a program is not followed"), error=True)
        return False

    def _follow_named(self, link: dict) -> bool:
        name = link.get("nameddest") or link.get("name") or ""
        step = NAMED_ACTIONS.get(name)
        if step is not None:  # (Next page, First page...)
            target = {"first": 0, "last": self.count - 1}.get(step, self.page + (step if isinstance(step, int) else 0))
            self.go_place(max(0, min(target, self.count - 1)))
            return True
        try:
            dest = self.doc.resolve_names().get(name)
        except (RuntimeError, ValueError, AttributeError):
            dest = None
        if not dest or dest.get("page", -1) < 0:
            self.status(tr("The place {name} is not in the document", name=name), error=True)
            return False
        to = dest.get("to")
        self.go_place(dest["page"], to[1] if isinstance(to, (tuple, list)) and len(to) > 1 else None)
        return True

    def _follow_other_file(self, link: dict) -> bool:
        """A link to another PDF: opened in a window of its own, at the page it says."""
        name = link.get("file", "")
        base = self.path.parent if self.path is not None else Path.cwd()
        path = (base / name).resolve() if name else None
        if path is None or not path.is_file():
            self.status(tr("{file} is not there", file=name or "?"), error=True)
            return False
        from . import open_window

        win = open_window(path)
        page = link.get("page", -1)
        if page is not None and page >= 0:
            win.go_place(page)
        return True

    def open_address(self, uri: str) -> bool:
        """A web or mail address, opened by the desktop's program for it, once the user says so."""
        if not uri:
            return False
        answer = QMessageBox.question(self, tr("Open the address"),
                                      tr("Open this address, outside py-pdftools?") + "\n\n" + uri)
        if answer != QMessageBox.StandardButton.Yes:
            return False
        return QDesktopServices.openUrl(QUrl(uri))
