"""Leer en voz alta (gui/readaloud.py) con una voz de prueba: desde la página a la vista, página tras página
(salta las que no tienen texto), la palabra dicha resaltada en la página, pausa, velocidad guardada, y el fin
(solo, con F12 otra vez o al abrir otro documento)."""

from __future__ import annotations

import enum

import pymupdf
import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from py_pdftools.core import config
from py_pdftools.gui import readaloud
from py_pdftools.gui.window import MainWindow


class State(enum.Enum):  # (as QTextToSpeech.State, by name)
    Ready = 0
    Speaking = 1
    Paused = 2
    Error = 3


class Voice(QObject):
    """A voice of the test: it says nothing; the test sends its signals."""

    # (said one sentence at a time: see readaloud.sentences)

    sayingWord = Signal(str, int, int, int)
    stateChanged = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.said, self.paused, self._rate = [], None, 0.0

    def say(self, text):
        self.said.append(text)

    def setRate(self, rate):
        self._rate = rate

    def rate(self):
        return self._rate

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def stop(self):
        self.said.append("<stop>")

    def errorString(self):
        return "no voice"


@pytest.fixture
def window(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    path = tmp_path / "book.pdf"
    doc = pymupdf.open()
    for text in ("First page, the scribe.", "", "Third page here."):
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text, fontname="helv")
    doc.save(path)
    voices = []
    monkeypatch.setattr(readaloud, "unavailable", lambda: "")
    monkeypatch.setattr(readaloud, "make_speech", lambda parent: voices.append(Voice(parent)) or voices[-1])
    w = MainWindow()
    w.ask_recover = lambda when: False
    w.resize(1200, 900)
    w.show()
    assert w.open_path(path)
    QApplication.processEvents()
    w.voices = voices
    yield w
    w.annotations = w.saved = []
    w.close()


def test_reads_page_after_page(window):
    config.set("speech_rate", 0.3)
    window.show_page(0)
    window.a_read_aloud.trigger()
    voice = window.voices[0]
    assert voice.said == ["First page, the scribe."] and voice.rate() == 0.3 and window.a_read_pause.isEnabled()
    # (the sentence said, highlighted at once: a voice may not tell the words, as speech-dispatcher's)
    sentence = window._voice.marks
    assert len(sentence) == 1 and sentence[0].scene() is not None and 60 < sentence[0].rect().left() < 80
    # (where the voice tells the word said, "scribe": highlighted too, inside its sentence)
    start = voice.said[0].index("scribe")
    voice.sayingWord.emit("scribe", 0, start, 6)
    marks = window._voice.marks
    assert len(marks) == 2 and all(m.scene() is not None for m in marks)
    box = marks[1].rect()
    assert 120 < box.left() < 250 and 55 < box.top() < 80 and box.width() < 60
    # (the page said: the next with text, the third; the second has none)
    voice.stateChanged.emit(State.Ready)
    QApplication.processEvents()
    assert voice.said[-1] == "Third page here." and window._voice.page == 2
    window.a_read_pause.trigger()
    assert voice.paused is True
    window.a_read_pause.trigger()
    assert voice.paused is False
    window.read_faster()
    assert voice.rate() == 0.4 and config.get("speech_rate") == 0.4
    voice.stateChanged.emit(State.Ready)  # (the last page said: it ends)
    QApplication.processEvents()
    assert not window._voice.reading and not window.a_read_aloud.isChecked()
    assert not window.a_read_pause.isEnabled() and not window._voice.marks


def test_stopped(window, tmp_path):
    window.a_read_aloud.trigger()
    voice = window.voices[0]
    window.a_read_aloud.trigger()  # (F12 again)
    assert voice.said[-1] == "<stop>" and not window._voice.reading
    window.a_read_aloud.trigger()
    window._voice.speech.stateChanged.emit(State.Error)
    assert not window._voice.reading  # (the voice failed: it stops, and says why)
    window.a_read_aloud.trigger()
    other = tmp_path / "other.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Other", fontname="helv")
    doc.save(other)
    assert window.open_path(other)
    assert not window._voice.reading  # (another document: it stops)


def test_without_the_module(window, monkeypatch):
    shown = []
    monkeypatch.setattr(readaloud, "unavailable", lambda: "no module")
    window.warn = lambda title, text: shown.append(text)
    window.a_read_aloud.trigger()
    assert shown == ["no module"] and not window.a_read_aloud.isChecked() and window.voices == []


def test_sentences():
    text = "One. Two, still two! Three? Four; five: six " + "word " * 120
    said = [text[a:b] for a, b in readaloud.sentences(text)]
    assert said[:5] == ["One.", "Two, still two!", "Three?", "Four;", "five:"]
    assert all(len(s) <= readaloud.LONGEST for s in said) and "".join(said).replace(" ", "") == text.replace(" ", "")
    assert readaloud.sentences("   ") == []
