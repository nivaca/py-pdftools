"""The mode Redact of the window, driven as the user would: boxes drawn, over text and elsewhere,
moved, repeated on other pages, found, and applied in a redacted copy that is checked. (From the
tests of py-redact's window.)"""

from __future__ import annotations

import pymupdf
import pytest
from gui_helpers import close, double_click, drag
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from py_pdftools.annotate import annots
from py_pdftools.gui.window import MainWindow
from py_pdftools.redact import settings


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, sample, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))  # (QSettings)
    w = MainWindow()

    def warn(title, text):  # (a message box would wait for a click for ever)
        raise AssertionError(f"warning shown: {title}: {text}")

    def ask_bookmarks(name, leaks):  # (likewise)
        raise AssertionError(f"bookmarks asked about: {leaks}")

    w.warn, w.ask_bookmarks = warn, ask_bookmarks
    w.ask_recover = lambda when: False
    w.resize(1200, 800)
    w.show()
    app.processEvents()
    assert w.open_path(sample)
    w.set_mode("redact")
    app.processEvents()
    assert w.canvas.mode == "redact"  # (the tool of the mode)
    yield w
    w.annotations = w.saved = []
    w.close()


def boxes(w) -> list[annots.Annotation]:
    return [a for a in w.annotations if a.kind == "redact"]


def save_copy(w, tmp_path, name="out.pdf") -> list[str]:
    """The redacted copy saved, and the text of its pages."""
    from py_pdftools.redact.redact import box_of

    out = tmp_path / name
    assert w.save_redacted(out, [box_of(b) for b in boxes(w)])
    return [p.get_text() for p in pymupdf.open(out)]


def test_draw_move_resize(window):
    drag(window, (300, 400), (400, 450))  # (no text there: a box)
    (box,) = boxes(window)
    assert close(box.rect, (300, 400, 400, 450)) and box.fill == "#000000" and box.page == 0
    drag(window, (350, 425), (360, 435))  # (moved)
    assert close(boxes(window)[0].rect, (310, 410, 410, 460))
    drag(window, (410, 460), (430, 480))  # (resized by its corner)
    assert close(boxes(window)[0].rect, (310, 410, 430, 480))
    window.undo()
    assert close(boxes(window)[0].rect, (310, 410, 410, 460))


def test_tiny_drag_draws_nothing(window):
    drag(window, (300, 400), (301, 401))
    assert boxes(window) == []


def test_over_text_marks_it_ctrl_draws(window):
    drag(window, (70, 112), (200, 122))  # (on the words: a box over each line of the text)
    (box,) = boxes(window)
    assert box.rect[0] < 72 and box.rect[2] > 140 and box.rect[3] - box.rect[1] < 20
    window.pick([], False)
    drag(window, (72, 290), (300, 330), mods=Qt.KeyboardModifier.ControlModifier)  # (Ctrl: a box anyway)
    assert len(boxes(window)) == 2 and close(boxes(window)[1].rect, (72, 290, 300, 330))


def test_double_click_a_word(window):
    double_click(window, (80, 116))
    (box,) = boxes(window)
    assert box.rect[0] < 72 and box.rect[2] < 110  # ("Name:", only)


def test_repeat_on_pages_then_save(window, tmp_path):
    drag(window, (60, 40), (300, 66), mods=Qt.KeyboardModifier.ControlModifier)
    window.set_redact_color("#ffffff")
    window.set_redact_repeat("2-")
    (box,) = boxes(window)
    assert (box.fill, box.repeat, box.page) == ("#ffffff", "2-", 0)
    shown = sorted(item.annot.page for item in window.canvas.items_ if item.index == window.annotations.index(box))
    assert shown == [0, 1, 2, 3, 4]  # (its own page, where it was drawn, and those it goes on)
    window.set_redact_repeat("nonsense")
    assert boxes(window)[0].repeat == "2-"
    window.pick([], False)
    drag(window, (60, 105), (300, 126), mods=Qt.KeyboardModifier.ControlModifier)
    # (a new box takes neither the pages nor the colour of the one before: only the default colour)
    assert (boxes(window)[1].fill, boxes(window)[1].repeat) == ("#000000", "")
    window.set_redact_repeat("2-")
    pages = save_copy(window, tmp_path)
    assert "HEADER1" in pages[0] and not any("HEADER" in t or "Person" in t for t in pages[1:])
    assert "Person1" in pages[0] and all("Body text stays" in t for t in pages)


def test_a_box_moved_on_another_page_stays_of_its_own(window):
    drag(window, (300, 400), (400, 450))
    window.set_redact_repeat("all")
    window.show_page(2)
    index = window.annotations.index(boxes(window)[0])
    item = next(i for i in window.canvas.items_ if i.index == index and i.annot.page == 2)
    window.canvas.edited.emit(index, annots.moved(item.annot, 10, 10))
    (box,) = boxes(window)
    assert box.page == 0 and close(box.rect, (310, 410, 410, 460))


def test_default_colour_is_kept(window):
    drag(window, (300, 400), (400, 450))
    window.pick([], False)
    window.set_redact_color("#ff0000")  # (nothing selected: the colour of new boxes)
    drag(window, (300, 500), (400, 550))
    assert [b.fill for b in boxes(window)] == ["#000000", "#ff0000"]
    assert settings.load().color == "#ff0000"


def test_find_and_redact(window, tmp_path):
    window.redact_find_dialog("person")
    finder = window.redact_finder
    assert len(finder.matches) == 5 and "5" in finder.summary.text()
    finder.results.setCurrentRow(2)  # (shows the place)
    assert window.page == 2
    finder.results.item(0).setCheckState(Qt.CheckState.Unchecked)
    finder.mark.emit(finder.ticked())
    assert sorted(b.page for b in boxes(window)) == [1, 2, 3, 4]
    finder.mark.emit(finder.ticked(all_=True))  # (not twice over the same place)
    assert sorted(b.page for b in boxes(window)) == [0, 1, 2, 3, 4]
    assert not any("Person" in t for t in save_copy(window, tmp_path))


def test_find_several_and_patterns(window):
    window.find_in_mode()  # (Find, in this mode: and redact)
    f = window.redact_finder
    assert f is not None and window.finder is None
    f.mode.setCurrentIndex(1)
    f.terms.setPlainText("header1\nPerson2\n\nnothing like this")
    f.search()
    assert sorted(m.text for m in f.matches) == ["HEADER1", "Person2"]


def test_properties_codes_and_default(window, monkeypatch):
    from py_pdftools.gui import redacting

    drag(window, (300, 400), (400, 450))
    window.toggle_code("(b)(6)")
    window.toggle_code("(b)(7)(C)")
    assert boxes(window)[0].overlay == "(b)(6), (b)(7)(C)"
    window.toggle_code("(b)(6)")
    assert boxes(window)[0].overlay == "(b)(7)(C)"

    class Dialog:
        def __init__(self, chosen, *args):
            self.as_default = type("Box", (), {"isChecked": lambda self: True})()

        def exec(self):
            return redacting.QDialog.DialogCode.Accepted

        def apply(self, box):
            import dataclasses

            return dataclasses.replace(box, color="#808080", text="SECRET", text_color="#00ff00", note="why",
                                       locked=True)

    monkeypatch.setattr(redacting, "PropertiesDialog", Dialog)
    window.redact_properties_dialog()
    (box,) = boxes(window)
    assert (box.fill, box.overlay, box.color, box.contents, box.locked) == ("#808080", "SECRET", "#00ff00", "why",
                                                                            True)
    assert settings.load().color == "#808080" and settings.load().text == "SECRET"
    window.delete_selected()  # (locked: it stays)
    assert len(boxes(window)) == 1


def test_modes_keep_to_their_own(window):
    """A box is not touched in the mode Annotate, nor an annotation in the mode Redact; Edit works on
    those of the mode on."""
    drag(window, (300, 400), (400, 450))
    window.set_mode("annotate")
    window.set_tool("rect")
    drag(window, (100, 600), (200, 700))
    assert [a.kind for a in window.annotations] == ["redact", "rect"]
    window.set_tool("select")
    drag(window, (350, 425), (360, 435))  # (on the box: the mouse goes through it)
    assert close(window.annotations[0].rect, (300, 400, 400, 450)) and 0 not in window.selected
    window.select_page()
    assert window.selected == [1]
    window.set_mode("redact")
    assert window.selected == []  # (the rectangle is not of this mode)
    window.select_page()
    assert window.selected == [0]
    window.delete_selected()
    assert [a.kind for a in window.annotations] == ["rect"]


def test_marks_are_saved_with_the_document(window, sample):
    """Saving the document keeps the boxes in it, as the PDF's redaction marks, not applied; opened
    again, they are boxes again."""
    drag(window, (70, 112), (200, 122))
    window.set_redact_repeat("all")
    assert window.save()
    doc = pymupdf.open(sample)
    assert [a.type[1] for a in doc[0].annots()] == ["Redact"] and "Person1" in doc[0].get_text()
    doc.close()
    other = MainWindow()
    other.ask_recover = lambda when: False
    assert other.open_path(sample)
    (box,) = [a for a in other.annotations if a.kind == "redact"]
    assert box.repeat == "all"
    other.annotations = other.saved = []
    other.close()


def test_copy_asks_to_save_other_changes(window, tmp_path, monkeypatch):
    """The copy is made from the file: other changes are saved first, if the user wants."""
    window.set_mode("annotate")
    window.set_tool("rect")
    drag(window, (100, 600), (200, 700))
    window.set_mode("redact")
    drag(window, (70, 112), (200, 122))
    asked = []
    monkeypatch.setattr(window, "_ask_save_first", lambda: asked.append(1) or window.save())
    out = tmp_path / "copy.pdf"
    monkeypatch.setattr("py_pdftools.gui.redacting.QFileDialog.getSaveFileName", lambda *a, **k: (str(out), ""))
    assert window.save_redacted_dialog()
    assert asked and not window.is_modified()
    doc = pymupdf.open(out)
    assert "Person1" not in doc[0].get_text() and [a.type[1] for a in doc[0].annots()] == ["Square"]


def test_never_over_the_document(window, sample):
    drag(window, (70, 112), (200, 122))
    from py_pdftools.redact.redact import box_of

    assert not window.save_redacted(sample, [box_of(b) for b in boxes(window)])
    assert "Person1" in pymupdf.open(sample)[0].get_text()


def test_flattened_copies_leave_the_marks_out(window, tmp_path, monkeypatch):
    """A flattened copy would paint a box over what is still in the file: it leaves the marks out."""
    from py_pdftools.annotate.annots import Annotation
    from py_pdftools.gui.flatten_dialog import Choice

    drag(window, (70, 112), (200, 122))
    window.annotations = window.annotations + [Annotation("rect", 0, (300, 300, 400, 400), "#ff0000")]
    out = tmp_path / "flat.pdf"
    monkeypatch.setattr(window, "_ask_target", lambda *a, **k: out)
    chosen = []
    monkeypatch.setattr(window, "ask_flatten", lambda candidates, copy: chosen.append(candidates) or
                        Choice(candidates, False, copy))
    assert window.save_flattened_dialog()
    assert [window.annotations[i].kind for i in chosen[0]] == ["rect"]  # (the box is never offered)
    doc = pymupdf.open(out)
    assert not list(doc[0].annots()) and "Person1" in doc[0].get_text()


def test_bookmarks_that_give_away_are_asked_about(window, sample, tmp_path):
    doc = pymupdf.open(sample)
    doc.set_toc([[1, "Person1 is here", 1], [1, "Body", 2]])
    doc.saveIncr()
    doc.close()
    assert window.open_path(sample)
    window.set_mode("redact")
    asked = []
    window.ask_bookmarks = lambda name, leaks: asked.append(leaks) or "these"
    drag(window, (70, 112), (200, 122))
    save_copy(window, tmp_path)
    assert asked and [t[1] for t in asked[0]] == ["Person1 is here"]
    assert [t[1] for t in pymupdf.open(tmp_path / "out.pdf").get_toc()] == ["Body"]


def test_sanitize_and_metadata(window, tmp_path, monkeypatch):
    from py_pdftools.gui import redacting
    from py_pdftools.redact import metadata

    out = tmp_path / "clean.pdf"
    monkeypatch.setattr(redacting.QFileDialog, "getSaveFileName", lambda *a, **k: (str(out), ""))
    assert window.sanitize_dialog()
    assert "Person1" in pymupdf.open(out)[0].get_text()
    window.redact_meta = metadata.Metadata(info=(("Title", "A title"),))
    drag(window, (300, 400), (400, 450))
    save_copy(window, tmp_path, "meta.pdf")
    assert pymupdf.open(tmp_path / "meta.pdf").metadata["title"] == "A title"


def test_the_result(window):
    drag(window, (300, 400), (400, 450))
    window.a_redact_result.setChecked(True)
    window.canvas.grab()  # (painted as it will be)
    window.set_mode("annotate")
    assert not window.a_redact_result.isChecked()


def test_box_menu(window, monkeypatch):
    shown = []
    monkeypatch.setattr(window, "show_menu", lambda menu, where: shown.append(menu))
    drag(window, (300, 400), (400, 450))
    window.box_menu(window.selected[0], None, 0, None)
    texts = [a.text() for a in shown[-1].actions()]
    assert any("Apply the redaction" in t for t in texts) and "Properties…" in texts
    window.pick([], False)
    from PySide6.QtCore import QPointF

    window.box_menu(-1, None, 0, QPointF(80, 116))
    assert any("“Name:”" in a.text() for a in shown[-1].actions())


def test_saving_in_another_process(window, tmp_path, monkeypatch):
    """The copy is written and checked in a process of its own (as the window does it), and it comes
    out as it does here."""
    from py_pdftools.gui.redact import background

    monkeypatch.setattr(background, "ENABLED", True)
    drag(window, (70, 112), (200, 122))
    window.set_redact_repeat("all")
    pages = save_copy(window, tmp_path)
    assert not any("Person" in t for t in pages) and all("Body text stays" in t for t in pages)
    assert "checked" in window.statusBar().currentMessage()
