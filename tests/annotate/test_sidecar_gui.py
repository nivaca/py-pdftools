"""The window with the annotations kept apart (book.pdf.pdfnotes): saved there without touching the PDF, opened
from there, switched to the PDF and back with all of them kept, and with changes of the document itself."""

from __future__ import annotations

import dataclasses

import pymupdf
import pytest
from PySide6.QtWidgets import QApplication

from py_pdftools.annotate import annots, sidecar
from py_pdftools.annotate.annots import Annotation, Reply
from py_pdftools.core import config
from py_pdftools.gui.window import MainWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def make(app, tmp_path, monkeypatch):
    """make(path) -> a window with PATH open; the questions answered as the test says (w.answers)."""
    monkeypatch.setenv("HOME", str(tmp_path))  # (QSettings)
    made = []

    def make(path):
        w = MainWindow()

        def warn(title, text):  # (a message box would wait for a click for ever)
            raise AssertionError(f"warning shown: {title}: {text}")

        w.warn = warn
        w.ask_recover = lambda when: False
        w.answers = {}
        w.ask_strip = lambda count: w.answers.pop("strip")
        w.ask_pdf_part = lambda: w.answers.pop("part")
        w.resize(1000, 700)
        w.show()
        app.processEvents()
        assert w.open_path(path)
        made.append(w)
        return w

    yield make
    for w in made:
        w.annotations = w.saved = []
        w.close()


@pytest.fixture
def book(sample, tmp_path):
    """A copy of SAMPLE with two annotations of its own (one with a reply)."""
    path = tmp_path / "book.pdf"
    annots.write(sample, [Annotation("rect", 0, (10, 10, 60, 60), "#ff0000", contents="first"),
                          Annotation("note", 1, (100, 100, 116, 116), "#ffd54f", contents="second",
                                     replies=(Reply("B", "yes"),))], path)
    return path


def editable(items):
    return [a for a in items if a.kind != annots.OTHER]


def test_apart_without_touching_the_pdf(make, book):
    w = make(book)
    assert not w.apart() and not w.a_apart.isChecked()
    before = book.read_bytes()
    w.answers["strip"] = "keep"
    assert w.set_apart(True)
    assert w.apart() and w.a_apart.isChecked() and w.a_embedded.isEnabled()
    xml = sidecar.beside(book)
    assert xml.is_file() and book.read_bytes() == before and not w.is_modified()
    # The PDF's own annotations are edited, deleted and added to: only the file apart changes.
    first, second = editable(w.annotations)
    w.change([dataclasses.replace(first, contents="first, changed"),
              Annotation("ellipse", 2, (200, 200, 260, 240), "#0000ff")])
    assert w.save()
    assert book.read_bytes() == before and not w.is_modified()
    assert "annotations saved in .book.pdf.pdfnotes" in w.statusBar().currentMessage()
    # Opened again: the annotations of the file apart, not those of the PDF.
    other = make(book)
    assert other.apart()
    assert [(a.kind, a.contents) for a in editable(other.annotations)] == [("rect", "first, changed"),
                                                                           ("ellipse", "")]
    assert editable(other.annotations)[0].xref == first.xref
    # Back into the PDF: the changed one where it was, the deleted one gone, the new one written; no file apart.
    assert other.set_apart(False)
    assert not other.apart() and not xml.exists() and book.read_bytes() != before
    in_pdf = editable(annots.read(annots.open_pdf(book)))
    assert [(a.kind, a.contents) for a in in_pdf] == [("rect", "first, changed"), ("ellipse", "")]
    assert in_pdf[0].xref == first.xref


def test_taken_out_of_the_pdf(make, book):
    w = make(book)
    kept = [dataclasses.replace(a, xref=0, replies=tuple(dataclasses.replace(r, xref=0) for r in a.replies))
            for a in editable(w.annotations)]
    w.answers["strip"] = "strip"
    assert w.set_apart(True)
    assert editable(annots.read(annots.open_pdf(book))) == []  # (other programs show the PDF bare)
    got = [dataclasses.replace(a, xref=0, origin="", replies=tuple(dataclasses.replace(r, xref=0) for r in a.replies))
           for a in editable(w.annotations)]
    assert got == kept and not w.is_modified()
    other = make(book)
    assert [a.contents for a in editable(other.annotations)] == ["first", "second"]
    assert editable(other.annotations)[1].replies[0].contents == "yes"


def test_default_from_the_settings(make, sample):
    config.set("annot_storage", "file")
    before = sample.read_bytes()
    w = make(sample)
    assert w.apart()
    w.change([Annotation("rect", 0, (50, 50, 90, 90), "#00ff00")])
    assert w.save()
    assert sample.read_bytes() == before and sidecar.beside(sample).is_file()


def test_document_changed_too(make, book):
    w = make(book)
    w.answers["strip"] = "keep"
    assert w.set_apart(True)
    # A change of the document itself (page 1 turned): saving writes the PDF too, here without the annotations.
    assert w.transform(lambda pdf: pdf.pages[0].rotate(90, relative=True))
    assert w.is_modified()
    w.answers["part"] = "strip"
    assert w.save()
    with pymupdf.open(book) as doc:
        assert doc[0].rotation == 90
    assert editable(annots.read(annots.open_pdf(book))) == []
    other = make(book)
    assert [a.contents for a in editable(other.annotations)] == ["first", "second"]
    # (the rect, kept on the page turned, where it was on it: as the window showed it after the turn)
    assert editable(other.annotations)[0].rect == editable(w.annotations)[0].rect


def test_save_as_and_a_copy_with_them(make, book, tmp_path):
    w = make(book)
    w.answers["strip"] = "keep"
    assert w.set_apart(True)
    w.change(w.annotations + [Annotation("rect", 2, (5, 5, 50, 50))])
    target = tmp_path / "another.pdf"
    assert w.save_to(target)
    assert w.path == target and target.read_bytes() == book.read_bytes()
    assert sidecar.beside(target).is_file() and len(editable(w.annotations)) == 3
    copy = tmp_path / "given.pdf"
    w._ask_target = lambda title, suffix, ext="pdf": copy
    assert w.save_embedded_dialog()
    assert len(editable(annots.read(annots.open_pdf(copy)))) == 3 and not sidecar.beside(copy).exists()


def test_changed_by_another_program(make, book, app):
    w = make(book)
    w.answers["strip"] = "keep"
    assert w.set_apart(True)
    # Another copy of the program (another computer, through Dropbox) saves the file apart.
    other = make(book)
    other.change(other.annotations + [Annotation("rect", 2, (5, 5, 50, 50))])
    assert other.save()
    assert w.file_changed()  # (nothing unsaved here: opened again, with the new one)
    assert len(editable(w.annotations)) == 3


def test_unreadable_file_kept(make, book):
    xml = sidecar.beside(book)
    xml.write_text("<annotations", encoding="utf-8")
    w = make(book)
    assert w.apart() and "cannot be read" in w.statusBar().currentMessage()
    assert [a.contents for a in editable(w.annotations)] == ["first", "second"]  # (the PDF's)
    w.change(w.annotations[:1])
    assert w.save()
    assert xml.with_name(xml.name + ".unreadable").read_text(encoding="utf-8") == "<annotations"
    assert len(sidecar.read(xml).annotations) == 1


def test_import_skim_notes(make, book, tmp_path):
    import plistlib

    source = tmp_path / "book.skim"
    source.write_bytes(plistlib.dumps([{"type": "Square", "pageIndex": 0, "bounds": "{{100, 700}, {50, 40}}",
                                        "contents": "from Skim", "color": [1, 0, 0, 1]}]))
    w = make(book)
    assert w.import_from(source, "skim")
    assert [a.contents for a in editable(w.annotations)] == ["first", "second", "from Skim"]
    assert w.import_from(source, "skim")  # (twice: not added again)
    assert len(editable(w.annotations)) == 3


def test_taken_out_and_back_exactly(make, book):
    with pymupdf.open(book) as d:
        for page in d:
            for xref, _, _ in page.annot_xrefs():
                d.xref_set_key(xref, "OtherProgram", "(kept)")
        d.save(book, incremental=True, encryption=pymupdf.PDF_ENCRYPT_KEEP)
    w = make(book)
    w.answers["strip"] = "strip"
    assert w.set_apart(True)
    assert editable(annots.read(annots.open_pdf(book))) == []
    assert all(a.origin in w.kept_raws for a in editable(w.annotations))
    # Opened again from the file apart, the second one changed, and back into the PDF.
    other = make(book)
    assert len(other.kept_raws) == 2
    first, second = editable(other.annotations)
    other.change([first, dataclasses.replace(second, contents="second, changed")])
    assert other.set_apart(False)
    doc = annots.open_pdf(book)
    back = editable(annots.read(doc))
    assert [a.contents for a in back] == ["first", "second, changed"]
    assert [doc.xref_get_key(a.xref, "OtherProgram")[1] for a in back] == ["kept", "kept"]
    assert back[1].replies[0].contents == "yes"


def test_hidden_or_not(make, book):
    w = make(book)
    w.answers["strip"] = "keep"
    assert w.set_apart(True)
    hidden, shown = sidecar.beside(book, hide=True), sidecar.beside(book, hide=False)
    assert hidden.name == ".book.pdf.pdfnotes" and hidden.is_file() and not shown.exists()
    # The setting changed: found under its old name, and moved to the new one at the next save.
    config.set("hide_notes", False)
    other = make(book)
    assert other.apart() and other.kept_file == hidden
    other.change(other.annotations[:1])
    assert other.save()
    assert shown.is_file() and not hidden.exists() and other.kept_file == shown


def test_settings_menu(make, book):
    # Las tres casillas están en Configuración > Anotaciones en un archivo aparte, ninguna en Archivo.
    w = make(book)
    assert w.a_apart not in w.m_file.actions()
    assert [a for a in w.m_apart.actions() if not a.isSeparator()] == [w.a_apart, w.a_apart_default,
                                                                        w.a_hide_notes]
    w._show_apart_settings()
    assert not w.a_apart_default.isChecked() and w.a_hide_notes.isChecked()
    w.a_apart_default.trigger()
    w.a_hide_notes.trigger()
    assert config.get("annot_storage") == "file" and config.get("hide_notes") is False
    w._show_apart_settings()
    assert w.a_apart_default.isChecked() and not w.a_hide_notes.isChecked()
    # (the document open stays as it was: the default is for those without a file yet)
    assert not w.apart()
