"""Changes of the document itself in the window (gui/working.py): made at once on a working copy,
with the annotations, undone and redone with them, and saved as the document."""

from __future__ import annotations

import pymupdf
import pytest
from PySide6.QtWidgets import QApplication

from py_pdftools.annotate.annots import Annotation
from py_pdftools.gui.window import MainWindow
from py_pdftools.pages import arrange, labels
from py_pdftools.pages.labels import Range


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def sample(tmp_path):
    path = tmp_path / "sample.pdf"
    doc = pymupdf.open()
    for i in range(4):
        doc.new_page().insert_text((72, 100), f"Page {i + 1}", fontsize=14)
    doc.save(path)
    return path


@pytest.fixture
def window(app, sample, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    w = MainWindow()
    w.ask_recover = lambda when: False
    assert w.open_path(sample)
    yield w
    w.annotations = w.saved = []
    w.drop_work()
    w.close()


def test_labels_then_undo_redo_and_save(window, sample):
    window.add(Annotation("rect", 2, (100, 200, 200, 300), "#ff0000"))
    assert window.transform(labels.write_labels, [Range(1, "r"), Range(3, "D")])
    assert window.work is not None and window.file != sample and window.path == sample
    assert [window.doc[i].get_label() for i in range(4)] == ["i", "ii", "1", "2"]
    assert [a.kind for a in window.annotations] == ["rect"] and window.is_modified()
    assert pymupdf.open(sample)[0].get_label() == ""  # (the file is as it was)
    window.undo()
    assert window.work is None and [window.doc[i].get_label() for i in range(4)] == ["", "", "", ""]
    assert [a.kind for a in window.annotations] == ["rect"]
    window.undo()  # (the rectangle: undone as before)
    assert window.annotations == []
    window.redo()
    window.redo()
    assert window.doc[0].get_label() == "i" and len(window.annotations) == 1
    assert window.save()
    assert window.work is None and not window.is_modified() and window.undo_stack == []
    doc = pymupdf.open(sample)
    assert doc[2].get_label() == "1" and [a.type[1] for a in doc[2].annots()] == ["Square"]


def test_pages_moved_with_their_annotations(window, sample):
    window.add(Annotation("rect", 2, (100, 200, 200, 300), "#ff0000"))
    assert window.transform(lambda pdf: arrange.Delete((1,)).apply(pdf))
    assert window.count == 3 and window.annotations[0].page == 1  # (it went with its page)
    assert "Page 2" in window.doc[0].get_text() + window.doc[1].get_text()
    window.add(Annotation("ellipse", 0, (100, 200, 200, 300), "#0000ff"))
    window.undo()
    window.undo()
    assert window.count == 4 and [a.page for a in window.annotations] == [2]
    window.redo()
    assert window.count == 3
    assert window.save()
    assert pymupdf.open(sample).page_count == 3


def test_redacted_copy_from_the_working_copy(window, sample, tmp_path):
    """The redacted copy is made from the document with its changes (it asks to save them, or not)."""
    from py_pdftools.redact.redact import box_of

    assert window.transform(lambda pdf: arrange.Delete((1,)).apply(pdf))
    box = window.new_box(0, (60, 80, 300, 110))
    out = tmp_path / "red.pdf"
    assert window.save_redacted(out, [box_of(box)])
    doc = pymupdf.open(out)
    assert doc.page_count == 3 and "Page 1" not in doc[0].get_text() and "Page 3" in doc[1].get_text()
