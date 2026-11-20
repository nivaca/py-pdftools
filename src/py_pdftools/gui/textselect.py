"""The tool Select text of the pages (mixed into PageCanvas): dragging over text selects it in reading
order, also across pages; Alt+drag selects a column (the words inside a rectangle); a double click
selects a word, a triple click its line; Shift+click takes the selection to where it is clicked. The
selection stays (shaded) until another click, Escape or another tool; the window copies it (Ctrl+C) and
offers, on a right click, to copy, mark, redact or find it."""

from __future__ import annotations

import time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import QApplication, QGraphicsRectItem

from ..annotate.annots import Rect, nearest_word

TEXT_SELECT = "selecttext"  # (the name of the tool)
SHADE = QColor(42, 127, 255, 70)  # (the colour over the text selected)


class TextSelectMixin:
    """(Mixed into PageCanvas: it uses its doc, pages, page_words, locate and signals.)"""

    def _init_text_select(self):
        # {'anchor': (page, word), 'head': (page, word)}, in reading order; or {'column': (page, QRectF)}
        self.text_sel: dict | None = None
        self._sel_marks: list = []
        self._word_texts: dict[int, list] = {}  # page -> its words as get_text('words') gives them
        self._last_double = (0.0, None)  # (when, where): to tell a triple click

    # ----------------------------------------------------------------- what is selected

    def word_texts(self, number: int) -> list:
        """The words of page NUMBER: (x0, y0, x1, y1, text, block, line, word), in the order of page_words."""
        if number not in self._word_texts:
            self._word_texts[number] = self.doc[number].get_text("words", sort=False) if self.doc is not None else []
        return self._word_texts[number]

    def selected_words(self) -> dict[int, list[int]]:
        """{page: the indices of its words selected}, the pages in order."""
        sel = self.text_sel
        if not sel or self.doc is None:
            return {}
        if "column" in sel:
            n, area = sel["column"]
            found = [i for i, (r, *_) in enumerate(self.page_words(n)) if area.intersects(QRectF(*_qrect(r)))]
            return {n: found} if found else {}
        (p0, w0), (p1, w1) = sorted([sel["anchor"], sel["head"]])
        out = {}
        for n in range(p0, p1 + 1):
            count = len(self.page_words(n))
            first = w0 if n == p0 else 0
            last = w1 if n == p1 else count - 1
            if count and first <= last:
                out[n] = list(range(first, last + 1))
        return out

    def selected_text(self) -> str:
        """The text selected: the words of a line with spaces, the lines and pages on lines of their own."""
        pages = []
        for n, indices in self.selected_words().items():
            words = self.word_texts(n)
            lines, line, key = [], [], None
            for i in indices:
                w = words[i]
                if key is not None and (w[5], w[6]) != key:
                    lines.append(" ".join(line))
                    line = []
                key = (w[5], w[6])
                line.append(w[4])
            if line:
                lines.append(" ".join(line))
            pages.append("\n".join(lines))
        return "\n\n".join(p for p in pages if p)

    def selection_rects(self) -> dict[int, list[Rect]]:
        """{page: one rectangle for each line of text selected on it}."""
        out = {}
        for n, indices in self.selected_words().items():
            found = self.page_words(n)
            lines: dict[tuple, list[float]] = {}
            for i in indices:
                (x0, y0, x1, y1), block, line = found[i]
                r = lines.setdefault((block, line), [x0, y0, x1, y1])
                r[0], r[1], r[2], r[3] = min(r[0], x0), min(r[1], y0), max(r[2], x1), max(r[3], y1)
            out[n] = [tuple(round(v, 2) for v in r) for r in lines.values()]
        return out

    # ----------------------------------------------------------------- changing it

    def set_text_selection(self, selection: dict | None):
        self.text_sel = selection if selection and self.doc is not None else None
        self._show_text_selection()
        self.text_selected.emit()

    def clear_text_selection(self):
        if self.text_sel is not None or self._sel_marks:
            self.set_text_selection(None)

    def select_all_text(self, number: int):
        """All the text of page NUMBER."""
        count = len(self.page_words(number))
        self.set_text_selection({"anchor": (number, 0), "head": (number, count - 1)} if count else None)

    def _show_text_selection(self):
        for mark in self._sel_marks:
            if mark.scene() is not None:
                mark.scene().removeItem(mark)
        self._sel_marks = []
        for n, rects in self.selection_rects().items():
            page = self.pages.get(n)
            if page is None:  # (a page not laid out: in the view of one page at a time)
                continue
            for r in rects:
                mark = QGraphicsRectItem(QRectF(*_qrect(r)), page)
                mark.setPen(QPen(Qt.PenStyle.NoPen))
                mark.setBrush(QBrush(SHADE))
                mark.setZValue(3)
                self._sel_marks.append(mark)

    # ----------------------------------------------------------------- the mouse

    def _nearest(self, n: int, point: QPointF) -> int | None:
        return nearest_word(self.page_words(n), point.x(), point.y())

    def text_select_press(self, event, page, point) -> bool:
        """A press of the left button with the tool: starts a selection, or extends it (Shift), or (the
        third click) selects a line. True if it was taken."""
        n = page.number
        when, where = self._last_double
        if time.monotonic() - when < QApplication.doubleClickInterval() / 1000 and where == n:
            self._last_double = (0.0, None)
            i = self._nearest(n, point)
            if i is not None:  # (a triple click: the line of the word)
                found = self.page_words(n)
                line = [j for j, w in enumerate(found) if (w[1], w[2]) == (found[i][1], found[i][2])]
                self.set_text_selection({"anchor": (n, line[0]), "head": (n, line[-1])})
            return True
        mods = event.modifiers()
        i = self._nearest(n, point)
        if mods & Qt.KeyboardModifier.ShiftModifier and self.text_sel and "anchor" in self.text_sel and i is not None:
            self.set_text_selection({"anchor": self.text_sel["anchor"], "head": (n, i)})
            return True
        column = bool(mods & Qt.KeyboardModifier.AltModifier)
        self._drag = {"kind": "select-text", "page": page, "start": point, "column": column, "anchor": i}
        return True

    def text_select_move(self, pos) -> None:
        """While dragging: the selection from where it started to the word under the pointer (on any page),
        or the column of the rectangle (on the page it started)."""
        drag = self._drag
        if drag["column"]:
            page = drag["page"]
            point = page.mapFromScene(self.mapToScene(pos))
            self.set_text_selection({"column": (page.number, QRectF(drag["start"], point).normalized())})
            return
        page, point = self.locate(pos)
        if page is None or drag["anchor"] is None:
            return
        i = self._nearest(page.number, point)
        if i is not None:
            self.set_text_selection({"anchor": (drag["page"].number, drag["anchor"]), "head": (page.number, i)})

    def text_select_release(self, drag, moved: bool) -> None:
        if not moved:  # (a click: the selection goes)
            self.clear_text_selection()

    def text_select_double(self, page, point) -> None:
        """A double click: the word under the pointer (and a third click soon after: its line)."""
        i = self._nearest(page.number, point)
        self._last_double = (time.monotonic(), page.number)
        if i is not None:
            self.set_text_selection({"anchor": (page.number, i), "head": (page.number, i)})


def _qrect(r: Rect) -> tuple[float, float, float, float]:
    """(x, y, width, height) of R."""
    return r[0], r[1], r[2] - r[0], r[3] - r[1]
