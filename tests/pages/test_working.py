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


def file_labels(path) -> list[str]:
    """The page labels of the PDF at PATH (read with pikepdf: PyMuPDF before 2.0 misreads some); with
    none, the numbers viewers show."""
    import pikepdf

    with pikepdf.open(path) as pdf:
        return labels.page_labels(labels.read_labels(pdf), len(pdf.pages))


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
    assert window.page_labels() == ["i", "ii", "1", "2"]
    assert [a.kind for a in window.annotations] == ["rect"] and window.is_modified()
    assert file_labels(sample) == ["1", "2", "3", "4"]  # (the file is as it was: no labels)
    window.undo()
    assert window.work is None and window.page_labels() == ["1", "2", "3", "4"] and window.ranges == []
    assert [a.kind for a in window.annotations] == ["rect"]
    window.undo()  # (the rectangle: undone as before)
    assert window.annotations == []
    window.redo()
    window.redo()
    assert window.page_labels()[0] == "i" and len(window.annotations) == 1
    assert window.save()
    assert window.work is None and not window.is_modified() and window.undo_stack == []
    doc = pymupdf.open(sample)
    assert file_labels(sample)[2] == "1" and [a.type[1] for a in doc[2].annots()] == ["Square"]


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


def test_labels_written_by_pymupdf_read_as_pikepdf_writes_them(tmp_path):
    """The labels the window writes with PyMuPDF (to write them with the annotations at once) are read back
    as those py-foliation writes with pikepdf: folios, prefixes, suffixes, numbers that don't start at 1."""
    import pikepdf

    from py_pdftools.gui.paging import write_page_labels

    ranges = [Range(1, "", prefix="Cover"), Range(2, "r", start=3), Range(6, "D", prefix="[A-", suffix="]"),
              Range(9, "f", start=24), Range(14, "A", prefix="Ápp (é)\\")]
    doc = pymupdf.open()
    for _ in range(20):
        doc.new_page()
    write_page_labels(doc, ranges)
    doc.save(tmp_path / "mupdf.pdf")
    with pikepdf.open(tmp_path / "mupdf.pdf") as pdf:
        mine = labels.read_labels(pdf)
        shown = labels.page_labels(mine, 20)
    with pikepdf.new() as pdf:
        for _ in range(20):
            pdf.add_blank_page()
        labels.write_labels(pdf, ranges)
        theirs = labels.read_labels(pdf)
        expected = labels.page_labels(theirs, 20)
    assert mine == theirs and shown == expected
    assert shown[0] == "Cover" and shown[1] == "iii" and shown[5] == "[A-1]" and shown[8] == "12v"
    write_page_labels(doc, [])
    doc.save(tmp_path / "none.pdf")
    with pikepdf.open(tmp_path / "none.pdf") as pdf:
        assert labels.read_labels(pdf) == []


def test_save_as_after_undoing_a_change_of_the_document(window, tmp_path):
    """After a change of the document itself is undone, the history still holds it (to redo): saving must
    not take it for a list of annotations."""
    window.add(Annotation("rect", 2, (100, 200, 200, 300), "#ff0000"))
    assert window.transform(labels.write_labels, [Range(1, "r")])
    window.undo()
    assert window.work is None and any(not isinstance(s, list) for s in window.redo_stack)
    out = tmp_path / "copy.pdf"
    assert window.save_to(out)
    assert [a.type[1] for a in pymupdf.open(out)[2].annots()] == ["Square"]
