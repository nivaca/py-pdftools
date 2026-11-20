"""Tests of the layers headers, footers and watermarks add (stamps.py, watermark.py, changes.py, the
batches of files.py, and the commands header-footer and watermark)."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pikepdf
import pytest

from py_pdftools.core import config, interface

from py_pdftools.pages import files, headfoot, labels, stamps, watermark

from foliation_argv import main
from py_pdftools.pages.changes import Change
from py_pdftools.pages.headfoot import HeaderFooter
from py_pdftools.pages.labels import LabelError, Range
from py_pdftools.pages.watermark import Watermark

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "docs" / "example" / "numbers-100.pdf"
NOW = datetime(2007, 11, 28, 15, 5, 9)
needs_pdftotext = pytest.mark.skipif(shutil.which("pdftotext") is None, reason="needs pdftotext (poppler-utils)")


@pytest.fixture(autouse=True)
def english(tmp_path, monkeypatch):
    monkeypatch.setenv(config.ENV, str(tmp_path / "cfg"))
    yield
    interface.use("en")
    interface.translate_argparse()


@pytest.fixture()
def book(tmp_path) -> Path:
    path = tmp_path / "book.pdf"
    shutil.copyfile(EXAMPLE, path)
    with pikepdf.open(path, allow_overwriting_input=True) as pdf:
        labels.write_labels(pdf, [Range(1, "r"), Range(9, "D")])
        pdf.save(path)
    return path


def contents(pdf) -> list[bytes]:
    return [p.obj.Contents.read_bytes() for p in pdf.pages]


def text_of(path: Path, page: int) -> str:
    out = subprocess.run(["pdftotext", "-layout", "-f", str(page), "-l", str(page), str(path), "-"],
                         capture_output=True, text=True, check=True).stdout
    return " ".join(out.split())


# =========================================================================== layers


def test_several_layers_update_and_bates(book):
    with pikepdf.open(book) as pdf:
        before = contents(pdf)
        doc = stamps.document_of(pdf, book)
        headfoot.apply(pdf, HeaderFooter(footer_center="one"), doc, NOW)
        headfoot.apply(pdf, HeaderFooter(header_right="$bates", pages="1-10"), doc, NOW, keep=True)
        headfoot.apply(pdf, HeaderFooter(header_left="three"), doc, NOW, keep=True)
        assert [(a.id, len(a.pages), a.bates) for a in stamps.additions(pdf)] == [(1, 100, False), (2, 10, True),
                                                                                (3, 100, False)]
        addition, last = headfoot.last(pdf)
        assert addition == 3 and last.header_left == "three"  # (its settings are in the file)
        Change(HeaderFooter(header_left="three, again"), replaces=addition).apply(pdf, doc, NOW)
        assert [a.settings["header_left"] for a in stamps.additions(pdf)] == ["", "", "three, again"]
        assert headfoot.remove(pdf, bates_only=True) == 10
        assert [a.id for a in stamps.additions(pdf)] == [1, 3]
        headfoot.apply(pdf, HeaderFooter(footer_center="replaces all"), doc, NOW)  # (not kept: replaces them)
        assert [len(stamps.records(p)) for p in pdf.pages[:2]] == [1, 1]
        assert headfoot.remove(pdf) == 100 and contents(pdf) == before


def test_removing_a_layer_between_others_keeps_the_links_right(book):
    with pikepdf.open(book) as pdf:
        link = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Annot, Subtype=pikepdf.Name.Link,
                                                    Rect=[100, 100, 200, 150]))
        pdf.pages[0].obj.Annots = pikepdf.Array([link])
        doc = stamps.document_of(pdf, book)
        first = HeaderFooter(footer_center="a", shrink=True, pages="1")
        second = HeaderFooter(header_center="b", shrink=True, pages="1", size=20)
        headfoot.apply(pdf, first, doc, NOW)
        headfoot.apply(pdf, second, doc, NOW, keep=True)
        rect = lambda: [round(float(v), 3) for v in pdf.pages[0].obj.Annots[0].Rect]  # noqa: E731
        both = rect()
        stamps.remove(pdf, addition=1)  # (the first one: the link is where the second alone would put it)
        alone = pikepdf.open(book)
        alone.pages[0].obj.Annots = pikepdf.Array([alone.make_indirect(pikepdf.Dictionary(
            Type=pikepdf.Name.Annot, Subtype=pikepdf.Name.Link, Rect=[100, 100, 200, 150]))])
        headfoot.apply(alone, second, stamps.document_of(alone, book), NOW)
        assert rect() == [round(float(v), 3) for v in alone.pages[0].obj.Annots[0].Rect] != both
        stamps.remove(pdf, kind=None)
        assert rect() == [100, 100, 200, 150]


def test_files_of_version_0_7_are_read_and_cleaned(book, tmp_path):
    """A page with the one record of 0.7 (no kind, id or settings) is read as addition 0."""
    source = (ROOT / "src" / "py_pdftools" / "pages" / "headfoot.py").read_text()  # (0.7 drew in the same way)
    with pikepdf.open(book) as pdf:
        before = contents(pdf)
        headfoot.apply(pdf, HeaderFooter(footer_center="old"), stamps.document_of(pdf, book), NOW)
        for page in pdf.pages:  # (turn its records into 0.7's)
            record = stamps.records(page)[0]
            old = pikepdf.Dictionary(Streams=record.Streams, Font=record.Resources.Font[0])
            del page.obj[stamps.KEY]
            page.obj[stamps.LEGACY] = old
        assert source and [(a.id, a.kind, a.settings) for a in stamps.additions(pdf)] == [(0, "HeaderFooter", {})]
        assert headfoot.last(pdf) is None  # (no settings to update)
        headfoot.apply(pdf, HeaderFooter(header_left="new"), stamps.document_of(pdf, book), NOW, keep=True)
        assert headfoot.remove(pdf) == 100 and contents(pdf) == before
        assert all(stamps.LEGACY not in p.obj and stamps.KEY not in p.obj for p in pdf.pages)


def test_date_formats(book):
    with pikepdf.open(book) as pdf:
        doc = stamps.document_of(pdf, book)
    found = {code: stamps.expand("$date", 1, doc, NOW, date_format=code) for code in stamps.DATE_FORMATS}
    assert found == {"medium": "Nov 28, 2007", "long": "November 28, 2007", "m/d/yy": "11/28/07",
                     "m/d/yyyy": "11/28/2007", "mm/dd/yyyy": "11/28/2007", "d/m/yy": "28/11/07",
                     "d/m/yyyy": "28/11/2007", "dd/mm/yyyy": "28/11/2007", "dd.mm.yyyy": "28.11.2007",
                     "yyyy-mm-dd": "2007-11-28"}
    may = datetime(2026, 5, 3)
    assert stamps.format_date(may, "long") == "May 3, 2026" and stamps.format_date(may, "dd/mm/yyyy") == "03/05/2026"
    interface.use("es")
    assert stamps.format_date(may, "long") == "3 de mayo de 2026" and stamps.format_date(may, "medium") == "3 may 2026"
    with pytest.raises(LabelError):
        headfoot.check(HeaderFooter(date_format="someday"))


# =========================================================================== watermarks


@needs_pdftotext
def test_text_watermark(book, tmp_path):
    out = tmp_path / "out.pdf"
    with pikepdf.open(book) as pdf:
        before = contents(pdf)
        wm = Watermark(text="DRAFT $page", opacity=0.3, pages="2-3", rotation=0)  # (pdftotext reads it level)
        assert watermark.apply(pdf, wm, stamps.document_of(pdf, book), NOW) == 2
        page = pdf.pages[1]
        state = next(iter(page.obj.Resources.ExtGState.values()))
        assert float(state.ca) == pytest.approx(0.3)
        pdf.save(out)
    assert "DRAFT 2" in text_of(out, 2) and "DRAFT" not in text_of(out, 4)
    with pikepdf.open(out) as pdf:
        assert watermark.pages_with(pdf) == [2, 3] and watermark.remove(pdf) == 2
        assert contents(pdf) == before and "/ExtGState" not in pdf.pages[1].obj.Resources or \
            not len(pdf.pages[1].obj.Resources.ExtGState)


def test_watermark_from_a_page_behind_and_for_printing_only(book, tmp_path):
    with pikepdf.open(book) as pdf:
        before = contents(pdf)
        doc = stamps.document_of(pdf, book)
        wm = Watermark(source=str(EXAMPLE), source_page=7, scale=30, rotation=0, behind=True, on_screen=False,
                       halign="right", valign="bottom", pages="1")
        watermark.apply(pdf, wm, doc, NOW)
        page = pdf.pages[0]
        assert page.obj.Contents[0].read_bytes().startswith(b"q\n/OC")  # (behind: drawn before all)
        group = pdf.Root.OCProperties.OCGs[0]
        assert group.Usage.View.ViewState == pikepdf.Name.OFF and group.Usage.Print.PrintState == pikepdf.Name.ON
        assert next(iter(page.obj.Resources.XObject.values())).Subtype == pikepdf.Name.Form
        pdf.save(tmp_path / "out.pdf")
    with pikepdf.open(tmp_path / "out.pdf") as pdf:
        assert watermark.last(pdf)[1].source_page == 7
        watermark.remove(pdf)
        assert contents(pdf) == before and "/OCProperties" not in pdf.Root


def test_watermark_placement_and_checks():
    wm = Watermark(text="x", rotation=90, halign="left", valign="top", units="pt", hoffset=10, voffset=20)
    m = watermark.placement(wm, 100, 20, 600, 800)  # (turned: 20 wide, 100 high, at the top left)
    corners = [stamps.transform(m, x, y) for x in (0, 100) for y in (0, 20)]
    assert min(c[0] for c in corners) == pytest.approx(10) and max(c[1] for c in corners) == pytest.approx(780)
    half = watermark.placement(Watermark(text="x", rotation=0, scale=50), 100, 50, 600, 800)
    assert half[0] == pytest.approx(3.0)  # (half of the page's width: 300 points)
    for bad in (dict(), dict(text="x", source=str(EXAMPLE)), dict(text="x", opacity=2),
                dict(text="x", on_print=False, on_screen=False), dict(source="/nowhere.pdf")):
        with pytest.raises(LabelError):
            watermark.check(Watermark(**bad))


def test_profiles_of_watermarks():
    watermark.save_profile(Watermark(text="Copy", name="Copy", show_on_menu=True))
    assert watermark.read_profiles()["Copy"].show_on_menu and headfoot.read_profiles() == {}
    assert watermark.delete_profile("Copy") and watermark.read_profiles() == {}


# =========================================================================== several files


def test_batch_of_files(book, tmp_path):
    other = tmp_path / "other.pdf"
    shutil.copyfile(EXAMPLE, other)
    hf = HeaderFooter(footer_right="$bates", bates_prefix="C-", bates_digits=3, pages="1-20")
    results, used = files.batch([book, other], Change(hf), folder=tmp_path / "out", suffix="_b")
    assert [t.name for _, t, _ in results] == ["book_b.pdf", "other_b.pdf"] and used == 40
    with pikepdf.open(tmp_path / "out" / "other_b.pdf") as pdf:
        assert b"(C-021)" in pdf.pages[0].obj.Contents[-1].read_bytes()  # (goes on from the first file)
    results, _ = files.batch([tmp_path / "out" / "book_b.pdf"], Change(None, bates_only=True), overwrite=True)
    with pikepdf.open(results[0][1]) as pdf:
        assert headfoot.pages_with(pdf) == []
    results, _ = files.batch([book], Change(hf), suffix="")
    assert results[0][1] is None and "input" in results[0][2]  # (it would overwrite the input)


# =========================================================================== the command line


def test_commands(book, tmp_path, capsys):
    other = tmp_path / "other.pdf"
    shutil.copyfile(EXAMPLE, other)
    assert main(["header-footer", str(book), str(other), "--footer-right", "$bates", "--bates-prefix", "X-",
                 "--pages", "1-10", "--output-dir", str(tmp_path / "out"), "--name-prefix", "n_"]) == 0
    out = capsys.readouterr().out
    assert "Next Bates number: X-000021" in out and (tmp_path / "out" / "n_other.pdf").is_file()
    stamped = tmp_path / "out" / "n_book.pdf"
    assert main(["header-footer", str(stamped), "--header-left", "$date", "--date-format", "yyyy-mm-dd", "--add",
                 "-i"]) == 0
    assert main(["header-footer", str(stamped), "--update", "--header-left", "Final", "-i"]) == 0
    assert main(["watermark", str(stamped), "--text", "COPY", "--opacity", "25%", "--scale", "60", "-i"]) == 0
    capsys.readouterr()
    assert main(["show", str(stamped)]) == 0
    shown = capsys.readouterr().out
    assert "header and footer (with Bates numbers), on 10 pages: 1-10" in shown and "watermark, on 100" in shown
    with pikepdf.open(stamped) as pdf:
        assert [a.settings.get("header_left", a.settings.get("text")) for a in stamps.additions(pdf)] == \
            ["", "Final", "COPY"]
    assert main(["header-footer", str(stamped), "--remove-bates", "-i"]) == 0
    assert main(["watermark", str(stamped), "--remove", "-i"]) == 0
    with pikepdf.open(stamped) as pdf:
        assert [a.kind for a in stamps.additions(pdf)] == ["HeaderFooter"]
    assert main(["watermark", str(book), "--text", "x", "--file", str(other), "-n"]) == 1
    assert main(["header-footer", str(book), "--update", "-n"]) == 1
    assert main(["header-footer", str(book), "--footer-left", "x", "-i", "--name-suffix", "_z"]) == 1
    assert main(["watermark", str(book), "--text", "x", "--opacity", "lots", "-n"]) == 1


def test_output_paths(book, tmp_path):
    from py_pdftools.pages.cli import build_parser, output_path
    parse = build_parser().parse_args
    assert output_path(parse(["clear", str(book)]), book) == book.with_name("book-labelled.pdf")
    assert output_path(parse(["clear", str(book), "--output-dir", "x"]), book) == Path("x/book.pdf")
    assert output_path(parse(["clear", str(book), "--name-prefix", "a_", "--name-suffix", ""]), book) == \
        book.with_name("a_book.pdf")


@pytest.mark.skipif(importlib.util.find_spec("PySide6") is None, reason="needs PySide6")
def test_window_dialogs(book, tmp_path, monkeypatch):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from py_pdftools.gui.pages.batch_dialog import BatchDialog
    from py_pdftools.gui.pages.watermark_dialog import WatermarkDialog
    app = QApplication.instance() or QApplication(sys.argv[:1])
    dlg = WatermarkDialog(None, Watermark(text="DRAFT"), book, "", None, 3, existing=True)
    dlg.update_preview()
    assert dlg.problem.text() == "" and not dlg.preview.pixmap().isNull() and dlg.keep.isVisibleTo(dlg)
    dlg.is_file.setChecked(True)
    dlg.source.setText(str(EXAMPLE))
    dlg.relative.setChecked(True)
    dlg.scale.setValue(40)
    settings, pages, problem = dlg.check()
    assert problem == "" and settings.source == str(EXAMPLE) and settings.text == "" and settings.scale == 40
    dlg.reject()
    batch = BatchDialog(None, [book], tmp_path)
    other = tmp_path / "other.pdf"
    shutil.copyfile(EXAMPLE, other)
    batch.add_paths([other, book])  # (each file once)
    assert batch.paths() == [book, other] and not batch.run_button.isEnabled()  # (no settings yet)
    monkeypatch.setattr(BatchDialog, "ask", lambda self, kind, settings, source: (
        HeaderFooter(footer_right="$bates", bates_prefix="Z", pages="1-2"), False))
    assert batch.choose_settings() and batch.run_button.isEnabled()
    batch.list.setCurrentRow(1)
    batch.move(-1)
    assert batch.paths() == [other, book]
    batch.other.setChecked(True)
    batch.out_folder.setText(str(tmp_path / "batch"))
    assert batch.run() and "Next Bates number: Z000005" in batch.report.toPlainText()
    with pikepdf.open(tmp_path / "batch" / "book-labelled.pdf") as pdf:
        assert b"(Z000003)" in pdf.pages[0].obj.Contents[-1].read_bytes()
    batch.reject()
    app.processEvents()


def test_batch_dialog_greys_out_pdfa_without_pdfconform(book, tmp_path, monkeypatch):
    pytest.importorskip("PySide6.QtWidgets")
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from py_pdftools.core import conform
    from py_pdftools.gui.pages.batch_dialog import BatchDialog
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(conform, "command", lambda path=None: None)
    batch = BatchDialog(None, [book], tmp_path)
    model = batch.standard.model()
    assert model.item(0).isEnabled() and not model.item(2).isEnabled() and batch.standard.currentData() == ""
    batch.reject()
    monkeypatch.setattr(conform, "command", lambda path=None: ["pdf2iso"])
    made = []
    monkeypatch.setattr(conform, "convert", lambda source, target, standard, password="": (
        made.append((source, target, standard)) or "veraPDF: PASS"))
    batch = BatchDialog(None, [book], tmp_path)
    batch.action.setCurrentIndex(batch.action.findData("remove-watermark"))
    batch.standard.setCurrentIndex(batch.standard.findData("a-2b"))
    out = book.with_name("book-labelled.pdf")
    assert batch.run() and made == [(out, out, "a-2b")]
    assert "PDF/A-2b (veraPDF: PASS)" in batch.report.toPlainText()
    batch.reject()
