"""Pandoc (core/pandoc.py): Markdown made Word, ODT, EPUB, HTML and LaTeX documents; documents made PDFs (with
LuaLaTeX, XeLaTeX or Typst); the text of a PDF with its pictures; and, in the window, the text and the
annotations exported as documents, a PDF made from a document, and the entries turned off without Pandoc."""

from __future__ import annotations

import zipfile

import pymupdf
import pytest

from py_pdftools.core import pandoc
from py_pdftools.pages import export

needs_pandoc = pytest.mark.skipif(not pandoc.available(), reason="pandoc is not installed")
needs_engine = pytest.mark.skipif(not pandoc.available() or pandoc.engine() is None,
                                  reason="no program makes PDFs for pandoc")
TEXT = "# Título\n\nUn párrafo con *cursiva*, $5 y $6, \\ y μῆνιν ἄειδε.\n\n- uno\n- dos\n"


@pytest.fixture
def doc(tmp_path):
    """A PDF with a heading, a paragraph, a picture and a tiny picture (left out of the text)."""
    d = pymupdf.open()
    p = d.new_page()
    p.insert_text((72, 80), "Chapter One", fontsize=24)
    p.insert_text((72, 120), "Body text of the paragraph.", fontsize=11)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 100), 0)
    pix.clear_with(120)
    p.insert_image(pymupdf.Rect(72, 300, 272, 400), pixmap=pix)
    tiny = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 8), 0)
    p.insert_image(pymupdf.Rect(300, 300, 308, 308), pixmap=tiny)
    d.set_metadata({"title": "A Book"})
    d.save(tmp_path / "doc.pdf")
    return tmp_path / "doc.pdf"


def test_markdown_with_pictures(doc, tmp_path):
    pictures = tmp_path / "pics"
    pictures.mkdir()
    text = export.markdown(doc, pictures=pictures)
    assert text.startswith("# Chapter One\n\nBody text of the paragraph.")
    names = [p.name for p in pictures.iterdir()]
    assert len(names) == 1 and f"![]({names[0]})" in text  # (the tiny one left out)
    assert "![" not in export.markdown(doc)  # (without a folder, the text alone, as before)


@needs_pandoc
@pytest.mark.parametrize("ext", list(pandoc.OUTPUTS))
def test_from_markdown(tmp_path, ext):
    target = tmp_path / f"out.{ext}"
    pandoc.from_markdown(TEXT, target, title="Prueba")
    data = target.read_bytes()
    if ext in ("docx", "odt", "epub"):
        with zipfile.ZipFile(target) as z:
            inside = "".join(z.read(n).decode("utf-8", "replace") for n in z.namelist()
                             if n.endswith((".xml", ".xhtml")))
        assert "cursiva" in inside and "μῆνιν" in inside and "$5 y $6" in inside
    else:
        text = data.decode("utf-8")
        assert "cursiva" in text and "μῆνιν" in text and "Prueba" in text
    assert not list(tmp_path.glob("*.tmp")) and [p.name for p in tmp_path.iterdir()] == [target.name]


@needs_pandoc
def test_pictures_in_the_documents(doc, tmp_path):
    pictures = tmp_path / "pics"
    pictures.mkdir()
    text = export.markdown(doc, pictures=pictures)
    pandoc.from_markdown(text, tmp_path / "out.html", resources=pictures)
    assert "data:image/" in (tmp_path / "out.html").read_text(encoding="utf-8")  # (inside the page)
    pandoc.from_markdown(text, tmp_path / "out.docx", resources=pictures)
    with zipfile.ZipFile(tmp_path / "out.docx") as z:
        assert any(n.startswith("word/media/") for n in z.namelist())
    # LaTeX cita sus imágenes: van en una carpeta junto al archivo.
    pandoc.from_markdown(text, tmp_path / "out.tex", resources=pictures)
    media = tmp_path / "out_files"
    assert media.is_dir() and any(media.rglob("*.png"))


@needs_pandoc
def test_errors(tmp_path, monkeypatch):
    with pytest.raises(pandoc.PandocError):
        pandoc.from_markdown(TEXT, tmp_path / "out.xyz")
    with pytest.raises(pandoc.PandocError):
        pandoc.to_pdf(tmp_path / "picture.png", tmp_path / "out.pdf")
    (tmp_path / "in.md").write_text(TEXT, encoding="utf-8")
    monkeypatch.setattr(pandoc, "engine", lambda: None)
    with pytest.raises(pandoc.PandocError, match="LuaLaTeX"):
        pandoc.to_pdf(tmp_path / "in.md", tmp_path / "out.pdf")
    monkeypatch.setattr(pandoc, "program", lambda: None)
    with pytest.raises(pandoc.PandocError, match="Pandoc"):
        pandoc.from_markdown(TEXT, tmp_path / "out.docx")
    assert not (tmp_path / "out.pdf").exists() and not (tmp_path / "out.docx").exists()


@needs_engine
def test_to_pdf(tmp_path):
    source = tmp_path / "in.md"
    source.write_text(TEXT, encoding="utf-8")
    maker = pandoc.to_pdf(source, tmp_path / "out.pdf")
    assert maker in pandoc.ENGINES
    with pymupdf.open(tmp_path / "out.pdf") as d:
        text = d[0].get_text()
    assert "Título" in text and "cursiva" in text
    if pandoc.serif_font():  # (a font with Greek: LaTeX's own has none)
        assert "μῆνιν" in text
    # Lo auxiliar de LaTeX queda en la carpeta temporal, no junto al documento.
    assert sorted(p.name for p in tmp_path.iterdir()) == ["in.md", "out.pdf"]


@pytest.fixture
def win(doc, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from py_pdftools.gui.window import MainWindow

    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    w = MainWindow()
    w.ask_recover = lambda when: False
    assert w.open_path(doc)
    yield w
    w.annotations = w.saved = []
    w.close()


@needs_pandoc
def test_in_the_window(win, tmp_path):
    from py_pdftools.annotate.annots import Annotation, Critical

    assert win.a_export_document.isEnabled() and win.a_from_document.isEnabled()
    win.ask_document_target = lambda title, name: tmp_path / f"{name}.odt"
    assert win.export_document_dialog() == tmp_path / "doc.odt"
    with zipfile.ZipFile(tmp_path / "doc.odt") as z:
        assert "Chapter One" in z.read("content.xml").decode() and any(n.startswith("media/") or
                                                                        n.startswith("Pictures/")
                                                                        for n in z.namelist())
    win.change([Annotation("rect", 0, (72, 60, 200, 90), contents="look here"),
                Annotation("highlight", 0, (72, 108, 220, 124), quads=((72, 108, 220, 124),),
                           critical=Critical("variant", lemma="Body", reading="Corpus"))])
    win.ask_document_target = lambda title, name: tmp_path / f"{name}.docx"
    assert win.export_dialog("report-doc") and win.export_dialog("apparatus-doc")
    with zipfile.ZipFile(tmp_path / "doc-annotations.docx") as z:
        assert "look here" in z.read("word/document.xml").decode()
    with zipfile.ZipFile(tmp_path / "doc-apparatus.docx") as z:
        assert "Corpus" in z.read("word/document.xml").decode()
    assert "1 annotation exported" in win.statusBar().currentMessage()


@needs_engine
def test_pdf_from_a_document(win, tmp_path):
    source = tmp_path / "notes.md"
    source.write_text(TEXT, encoding="utf-8")
    out = tmp_path / "notes.pdf"
    win.ask_document_source = lambda: source
    win.ask_new_pdf = lambda title, name: out
    made = win.from_document_dialog()
    assert made is not None and made.path == out and out.is_file()
    if made is not win:
        made.close()


def test_without_pandoc(win, monkeypatch):
    monkeypatch.setattr(pandoc, "program", lambda: None)
    win._enable()
    for act in (win.a_export_document, win.a_from_document, win.a_export_report_doc, win.a_export_apparatus_doc):
        assert not act.isEnabled() and "Pandoc" in act.toolTip()
