"""The links of the pages (mixed into PageCanvas): those the document has, and the web and mail addresses
written in its text, found under the pointer. A click follows them with the tools Hand and Select text, a
Ctrl+click with Select; over one, the pointer is a hand and a tip says where it goes. The window follows
them (see MainWindow.follow_link)."""

from __future__ import annotations

import re

import pymupdf
from PySide6.QtCore import QPointF

from ..core.interface import tr

# (a web address, or a mail address, in the text: as a word, with the punctuation around it left out)
ADDRESS = re.compile(r"(?:https?://|www\.)[^\s<>\"]+|[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.IGNORECASE)
FOLLOWED_BY = ("hand", "selecttext")  # (the tools that follow a link on a plain click; Select, on Ctrl+click)


class LinksMixin:
    """(Mixed into PageCanvas: it uses its doc, page_words and word_texts.)"""

    def _init_links(self):
        self._links: dict[int, list] = {}  # page -> [(its rectangle as the page is shown, the link)]
        self._link_press = None  # (where a press on a link was, to follow it on the release)

    def page_links(self, number: int) -> list:
        if number in self._links or self.doc is None:
            return self._links.get(number, [])
        page = self.doc[number]
        found = []
        for link in page.get_links():
            if link.get("kind") == pymupdf.LINK_NONE:
                continue
            r = pymupdf.Rect(link["from"]).normalize()  # (PyMuPDF lo da ya como la página se muestra)
            found.append(((r.x0, r.y0, r.x1, r.y1), link))
        # Las direcciones escritas en el texto, como enlaces: la palabra entera, sin la puntuación de alrededor.
        boxes, texts = self.page_words(number), self.word_texts(number)
        for (rect, *_), word in zip(boxes, texts, strict=False):
            m = ADDRESS.search(word[4])
            if not m:
                continue
            address = m.group(0).rstrip(".,;:)]}»”'")
            if "@" in address and not address.lower().startswith(("http", "www")):
                uri = "mailto:" + address
            else:
                uri = address if address.lower().startswith("http") else "https://" + address
            found.append((rect, {"kind": pymupdf.LINK_URI, "uri": uri, "in_text": True}))
        self._links[number] = found
        return found

    def link_at(self, number: int, point: QPointF) -> dict | None:
        """The link at POINT of page NUMBER (the document's before the addresses of the text)."""
        for (x0, y0, x1, y1), link in self.page_links(number):
            if x0 <= point.x() <= x1 and y0 <= point.y() <= y1:
                return link
        return None

    def link_target(self, link: dict) -> str:
        """Where LINK goes, said for a tip."""
        kind = link.get("kind")
        if kind == pymupdf.LINK_GOTO:
            return tr("Go to page {page}", page=link.get("page", 0) + 1)
        if kind == pymupdf.LINK_URI:
            return link.get("uri", "")
        if kind == pymupdf.LINK_GOTOR:
            return tr("Open {file}", file=link.get("file", "")) + (
                f" ({tr('page {page}', page=link['page'] + 1)})" if link.get("page", -1) >= 0 else "")
        if kind == pymupdf.LINK_NAMED:
            return link.get("nameddest") or link.get("name") or tr("A place in the document")
        if kind == pymupdf.LINK_LAUNCH:
            return tr("Starts a program (not followed)")
        return ""
