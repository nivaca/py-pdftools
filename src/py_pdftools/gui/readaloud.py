"""Leer en voz alta (Ver > Leer en voz alta, F12): el texto del documento, desde la página a la vista, página
tras página, con la voz del sistema (QTextToSpeech de Qt: speech-dispatcher en Linux, las voces de Windows y
de macOS). La palabra que se dice se resalta en la página, y la vista la sigue. Se puede pausar, acelerar o
frenar (la velocidad se guarda), y termina al acabar el documento, con F12 otra vez o al cerrar la ventana.

QtTextToSpeech no siempre está: viene en el PySide6 de Fedora y de las demás distribuciones, pero en pip es
parte de PySide6-Addons, aparte; sin ella, la orden se ve desactivada y dice por qué. La idea, de Calibre (su
visor lee en voz alta y marca la palabra con sayingWord)."""

from __future__ import annotations

import re

from PySide6.QtCore import QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import QGraphicsRectItem

from ..annotate.search import page_chars
from ..core.interface import tr

RATE_STEP = 0.1  # (Faster and Slower: QTextToSpeech's rate goes from -1, slowest, to 1)


SENTENCE_END = re.compile(r"(?<=[.!?;:])\s+")
LONGEST = 400  # (characters: a 'sentence' longer than this, a list without full stops, is said in pieces)


def sentences(text: str) -> list[tuple[int, int]]:
    """Where each sentence of TEXT begins and ends (after . ! ? ; or :, and a space), those longer than LONGEST
    cut at a space; none of spaces only."""
    out, at = [], 0
    for m in list(SENTENCE_END.finditer(text)) + [None]:
        end = m.start() if m is not None else len(text)
        while end - at > LONGEST:
            cut = text.rfind(" ", at, at + LONGEST)
            cut = cut if cut > at else at + LONGEST
            out.append((at, cut))
            at = cut
        out.append((at, end))
        at = m.end() if m is not None else len(text)
    return [(a, b) for a, b in out if text[a:b].strip()]


def unavailable() -> str:
    """Why reading aloud can't be done here ('' if it can)."""
    try:
        from PySide6.QtTextToSpeech import QTextToSpeech
    except ImportError:
        return tr("Reading aloud needs the module QtTextToSpeech of PySide6 (in PySide6-Addons, if PySide6 was "
                  "installed with pip)")
    if not [e for e in QTextToSpeech.availableEngines() if e != "mock"]:
        return tr("The system has no voice to read with (on Linux: speech-dispatcher)")
    return ""


def make_speech(parent):
    """The system's voice (a QTextToSpeech); the tests replace it."""
    from PySide6.QtTextToSpeech import QTextToSpeech

    return QTextToSpeech(parent)


class ReadAloud(QObject):
    """Reads WINDOW's document aloud with SPEECH (a QTextToSpeech, or one alike), from a page on; finished()
    when it ends, by itself or stopped."""

    finished = Signal()

    def __init__(self, window, speech):
        super().__init__(window)
        self.window, self.speech = window, speech
        self.page = -1
        self.text, self.where = "", []
        self.chunks: list[tuple[int, int]] = []  # (the sentences of the page: where each begins and ends)
        self.chunk = 0
        self.saying = False  # (a sentence being said: its end sends the next)
        self.marks: list[QGraphicsRectItem] = []  # (the sentence said, and the word, where the voice tells it)
        speech.sayingWord.connect(self._word)
        speech.stateChanged.connect(self._state)

    @property
    def reading(self) -> bool:
        return self.page >= 0

    def start(self, page: int, rate: float = 0.0):
        self.speech.setRate(max(-1.0, min(1.0, rate)))
        self.page = page
        self._say_page()

    def _say_page(self):
        doc = self.window.doc
        while doc is not None and 0 <= self.page < doc.page_count:
            self.text, self.where = page_chars(doc[self.page])
            self.chunks = sentences(self.text)
            if self.chunks:  # (a page without text, a picture: the next)
                self.chunk = 0
                self._say_chunk()
                return
            self.page += 1
        self.stop()

    def _say_chunk(self):
        # Una oración a la vez: así se sabe cuál se dice, aunque la voz no diga qué palabra (speech-dispatcher no
        # lo dice), y se resalta entera
        start, end = self.chunks[self.chunk]
        self.saying = True
        self._mark(start, end, word=False)
        self.speech.say(self.text[start:end])

    def _state(self, state):
        # (by its name: QTextToSpeech.State.Ready, without importing the module, which may be missing)
        name = getattr(state, "name", str(state))
        if name == "Ready" and self.saying:  # (the sentence said: the next one, or the next page)
            self.saying = False
            QTimer.singleShot(0, self._next)
        elif name == "Error":
            self.window.status(tr("The voice stopped: {error}", error=self.speech.errorString()), error=True)
            self.stop()

    def _next(self):
        if not self.reading:
            return
        self.chunk += 1
        if self.chunk < len(self.chunks):
            self._say_chunk()
        else:
            self.page += 1
            self._say_page()

    def _word(self, _word: str, _id: int, start: int, length: int):
        """The word said now (START, LENGTH in the sentence said), where the voice tells it (Windows, macOS):
        highlighted, with its sentence."""
        if not self.chunks or self.chunk >= len(self.chunks):
            return
        first = self.chunks[self.chunk][0]
        self._mark(*self.chunks[self.chunk], word=False)
        self._mark(first + start, first + start + length, word=True, clear=False)

    def _mark(self, start: int, end: int, word: bool, clear: bool = True):
        """The characters START to END of the page's text highlighted (a sentence, lightly; a word, more), and
        kept in view."""
        if clear:
            self._clear_marks()
        page = self.window.canvas.pages.get(self.page)
        if page is None:
            return
        lines: dict[tuple[int, int], QRectF] = {}
        for at in range(max(start, 0), min(end, len(self.where))):
            place = self.where[at]
            if place is None:  # (the space between two lines)
                continue
            b, n, r = place
            box = QRectF(r.x0, r.y0, r.width, r.height)
            lines[(b, n)] = lines[(b, n)].united(box) if (b, n) in lines else box
        pen = QPen(QColor(30, 110, 220), 1.5) if word else QPen(Qt.PenStyle.NoPen)
        pen.setCosmetic(True)
        for box in lines.values():
            item = QGraphicsRectItem(box.adjusted(-1, -1, 1, 1), page)
            item.setPen(pen)
            item.setBrush(QBrush(QColor(30, 110, 220, 70 if word else 35)))
            item.setZValue(5)
            self.marks.append(item)
        if self.marks and not word:
            self.window.canvas.ensureVisible(self.marks[0], 40, 80)

    def _clear_marks(self):
        for item in self.marks:
            try:
                if item.scene() is not None:
                    item.scene().removeItem(item)
            except RuntimeError:  # (the page was laid out again meanwhile: the item is gone)
                pass
        self.marks = []

    def pause(self, paused: bool):
        if paused:
            self.speech.pause()
        else:
            self.speech.resume()

    def change_rate(self, step: float) -> float:
        """The voice faster (STEP > 0) or slower; the rate it has now."""
        rate = max(-1.0, min(1.0, round(self.speech.rate() + step, 2)))
        self.speech.setRate(rate)
        return rate

    def stop(self):
        was = self.reading
        self.saying = False
        self.page = -1
        self.speech.stop()
        self._clear_marks()
        if was:
            self.finished.emit()
