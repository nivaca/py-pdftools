"""Moving through the document (mixed into MainWindow): following the links the canvas reports (see
links.py); going to a place of it (a page, a height on it); and the history of those jumps (from links,
bookmarks, the page box and Find), gone through back and forth with Previous view and Next view
(Alt+Left, Alt+Right), as in a web browser."""

from __future__ import annotations

from pathlib import Path

import pymupdf
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox

from ..core.interface import tr

# named actions a link may have: (where it goes from the page shown)
NAMED_ACTIONS = {"NextPage": 1, "PrevPage": -1, "FirstPage": "first", "LastPage": "last"}
HISTORY = 100  # (places kept to go back to)


class NavigationMixin:
    """(Mixed into MainWindow: it uses its attributes.)"""

    def go_place(self, page: int, y: float | None = None, remember: bool = True):
        """Show PAGE (0-based), with the height Y of it (in points, from its top) at the top of the view; the place
        left is remembered (REMEMBER), to come back to it with Previous view."""
        if self.doc is None or not 0 <= page < self.count:
            return
        if remember:
            self.remember_place()
        self.show_page(page)
        if y is not None:
            self.canvas.scroll_to(page, y)

    # ----------------------------------------------------------------- the history of the places

    def _place(self) -> tuple[int, float] | None:
        return (self.page, round(self._view_top(), 1)) if self.doc is not None else None

    def remember_place(self):
        """Keep the place shown, to come back to it (Previous view); what was ahead is forgotten."""
        place = self._place()
        if place is None:
            return
        back = self.__dict__.setdefault("_back", [])
        if not back or back[-1] != place:
            back.append(place)
            del back[:-HISTORY]
        self.__dict__.setdefault("_forward", []).clear()
        self._update_history()

    def history_step(self, back: bool = True) -> bool:
        """Go to the place before (BACK) or after the one shown, in the history of the jumps."""
        source = self.__dict__.setdefault("_back" if back else "_forward", [])
        other = self.__dict__.setdefault("_forward" if back else "_back", [])
        if not source or self.doc is None:
            return False
        here = self._place()
        if here is not None:
            other.append(here)
        page, y = source.pop()
        self.go_place(min(page, self.count - 1), y, remember=False)
        self._update_history()
        return True

    def reset_history(self):
        self._back, self._forward = [], []
        self._update_history()

    def _update_history(self):
        if hasattr(self, "a_back"):
            self.a_back.setEnabled(bool(self.__dict__.get("_back")))
            self.a_forward.setEnabled(bool(self.__dict__.get("_forward")))

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
