"""Tests of headers and footers (headfoot.py, and 'py-pdftools header-footer')."""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import pikepdf
import pytest

from py_pdftools.core import config, interface

from py_pdftools.pages import headfoot, labels, stamps

from foliation_argv import main
from py_pdftools.pages.headfoot import HeaderFooter
from py_pdftools.pages.labels import LabelError, Range

EXAMPLE = Path(__file__).resolve().parents[2] / "docs" / "example" / "numbers-100.pdf"
NOW = datetime(2007, 11, 28, 15, 5, 9)


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


def text_of(path: Path, page: int) -> str:
    """The text of PAGE (1-based), as pdftotext reads it (the drawing as a viewer shows it)."""
    out = subprocess.run(["pdftotext", "-layout", "-f", str(page), "-l", str(page), str(path), "-"],
                         capture_output=True, text=True, check=True).stdout
    return " ".join(out.split())


needs_pdftotext = pytest.mark.skipif(shutil.which("pdftotext") is None, reason="needs pdftotext (poppler-utils)")


def doc_of(path: Path) -> headfoot.Document:
    with pikepdf.open(path) as pdf:
        return headfoot.document_of(pdf, path)


# =========================================================================== the variables and the pages


def test_variables(book):
    doc = doc_of(book)
    text = "$page/$totalpages $pagelabel $filename $date $shortdate $time $year $shortyear $month $day $$"
    assert headfoot.expand(text, 3, doc, NOW) == "3/100 iii book.pdf Nov 28, 2007 11/28/07 3:05 PM 2007 07 11 28 $"
    assert headfoot.expand("$hour $longhour $minute $second $ampm $bates", 12, doc, NOW, "B-01") == \
        "3 15 05 09 PM B-01"
    assert headfoot.expand("$pages $unknown", 1, doc, NOW) == "1s $unknown"  # (only the names it knows)
    interface.use("es")
    assert headfoot.expand("$date, $shortdate", 3, doc, NOW) == "28 nov 2007, 28/11/07"


def test_bookmarks(book):
    with pikepdf.open(book, allow_overwriting_input=True) as pdf:
        with pdf.open_outline() as outline:
            front = pikepdf.OutlineItem("Front matter", 0)
            text = pikepdf.OutlineItem("Text", 8)
            text.children.append(pikepdf.OutlineItem("Chapter 2", 49))
            outline.root.extend([front, text])
        pdf.save(book)
    doc = doc_of(book)
    assert doc.bookmarks[0] == doc.bookmarks[7] == "Front matter"
    assert doc.bookmarks[8] == doc.bookmarks[48] == "Text" and doc.bookmarks[49] == doc.bookmarks[99] == "Chapter 2"


def test_chosen_pages_and_bates():
    assert headfoot.chosen_pages(HeaderFooter(), 5) == [1, 2, 3, 4, 5]
    assert headfoot.chosen_pages(HeaderFooter(pages="2-4,9-", parity="even"), 10) == [2, 4, 10]
    assert headfoot.chosen_pages(HeaderFooter(pages="LAST-1-", parity="odd"), 9) == [9]
    assert headfoot.compact_pages([9, 3, 4, 5, 11]) == "3-5,9,11"
    hf = HeaderFooter(bates_prefix="ABC-", bates_start=7, bates_digits=4, bates_suffix="/x")
    assert [headfoot.bates_number(hf, i) for i in (0, 3)] == ["ABC-0007/x", "ABC-0010/x"]


def test_checks():
    assert headfoot.check(HeaderFooter(color="FF8000", background="#ABCDEF")).color == "#ff8000"
    for bad in (dict(color="orange"), dict(units="mm"), dict(font="arial"), dict(size=0), dict(top=-1),
                dict(parity="third"), dict(bates_digits=0)):
        with pytest.raises(LabelError):
            headfoot.check(HeaderFooter(**bad))
    assert headfoot.unwritable("Página ½ € «ok»") == ""
    assert headfoot.unwritable("Ελλάς") == "Εάλς"


def test_widths_and_layout():
    assert headfoot.text_width("A", "Helvetica", 10) == pytest.approx(6.67)
    assert headfoot.text_width("mmm", "Courier", 10) == pytest.approx(18)
    hf = HeaderFooter(units="pt", top=20, bottom=30, left=40, right=50, size=10)
    blocks = {b.slot: b for b in headfoot.layout(hf, {"header_left": "a", "header_right": "abc",
                                                       "footer_center": "x\ny"}, 600, 800)}
    assert blocks["header_left"].x == 40 and blocks["header_left"].y + blocks["header_left"].height == 780
    assert blocks["header_right"].x + blocks["header_right"].width == pytest.approx(550)
    assert blocks["footer_center"].y == 30 and blocks["footer_center"].lines == ("x", "y")
    assert blocks["footer_center"].x + blocks["footer_center"].width / 2 == pytest.approx(300)
    assert HeaderFooter(font="times", bold=True, italic=True).base_font() == "Times-BoldItalic"
    assert HeaderFooter(font="helvetica", italic=True).base_font() == "Helvetica-Oblique"


# =========================================================================== on the pages


@needs_pdftotext
def test_apply_and_remove(book, tmp_path):
    out = tmp_path / "out.pdf"
    with pikepdf.open(book) as pdf:
        before = [p.obj.Contents.read_bytes() for p in pdf.pages]
        hf = HeaderFooter(header_right="$date", footer_center="Page $pagelabel ($page of $totalpages)",
                          pages="5-12", parity="even", border=True, background="#eeeeee", font="times")
        assert headfoot.apply(pdf, hf, headfoot.document_of(pdf, book), NOW) == 4
        pdf.save(out)
    assert headfoot.pages_with(pikepdf.open(out)) == [6, 8, 10, 12]
    assert text_of(out, 10) == "Nov 28, 2007 10 Page 2 (10 of 100)"
    assert text_of(out, 9) == "9"  # (an odd page: left alone)
    with pikepdf.open(out, allow_overwriting_input=True) as pdf:
        assert headfoot.remove(pdf, "1-8") == 2
        assert headfoot.pages_with(pdf) == [10, 12]
        assert headfoot.remove(pdf) == 2
        assert [p.obj.Contents.read_bytes() for p in pdf.pages] == before  # (the pages as they were)
        assert all(stamps.KEY not in p.obj for p in pdf.pages)


def test_applied_again_replaces(book):
    with pikepdf.open(book) as pdf:
        doc = headfoot.document_of(pdf, book)
        headfoot.apply(pdf, HeaderFooter(footer_center="one"), doc, NOW)
        headfoot.apply(pdf, HeaderFooter(footer_center="two", pages="1"), doc, NOW)
        page = pdf.pages[0]
        assert len(page.obj.Contents) == 3  # (the original, and one pair of streams added)
        assert b"(two)" in page.obj.Contents[2].read_bytes() and b"(one)" not in page.obj.Contents[2].read_bytes()


@needs_pdftotext
def test_rotated_pages_and_shrink(book, tmp_path):
    out = tmp_path / "out.pdf"
    with pikepdf.open(book) as pdf:
        for i, angle in ((0, 90), (1, 180), (2, 270)):
            pdf.pages[i].obj.Rotate = angle
        link = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Annot, Subtype=pikepdf.Name.Link,
                                                    Rect=[100, 100, 200, 150]))
        pdf.pages[3].obj.Annots = pikepdf.Array([link])
        hf = HeaderFooter(header_center="TOP", footer_center="BOTTOM", shrink=True, size=14, pages="1-4")
        headfoot.apply(pdf, hf, headfoot.document_of(pdf, book), NOW)
        moved = [float(v) for v in pdf.pages[3].obj.Annots[0].Rect]
        assert moved != [100, 100, 200, 150] and moved[2] - moved[0] < 100  # (moved and scaled with the page)
        pdf.save(out)
    for page in (1, 2, 3, 4):  # (as a viewer shows them: the header on top, the footer below)
        words = text_of(out, page).split()
        assert words[0] == "TOP" and words[-1] == "BOTTOM", (page, words)
    with pikepdf.open(out) as pdf:
        headfoot.remove(pdf)
        assert [float(v) for v in pdf.pages[3].obj.Annots[0].Rect] == [100, 100, 200, 150]
        assert int(pdf.pages[0].obj.Rotate) == 90


def test_errors(book):
    with pikepdf.open(book) as pdf:
        doc = headfoot.document_of(pdf, book)
        with pytest.raises(LabelError, match="cannot write"):
            headfoot.apply(pdf, HeaderFooter(header_left="Ελλάς"), doc, NOW)
        with pytest.raises(LabelError, match="no text"):
            headfoot.apply(pdf, HeaderFooter(), doc, NOW)
        with pytest.raises(LabelError, match="too little room"):
            headfoot.apply(pdf, HeaderFooter(header_left="x", footer_left="y", shrink=True, units="in", top=5,
                                             bottom=5), doc, NOW)
        assert headfoot.pages_with(pdf) == []  # (nothing was changed)


def test_profiles():
    assert headfoot.read_profiles() == {}
    headfoot.save_profile(HeaderFooter(footer_center="$page", name="Simple", show_on_menu=True))
    headfoot.save_profile(HeaderFooter(header_left="x", name="Other", color="#123ABC"))
    profiles = headfoot.read_profiles()
    assert list(profiles) == ["Other", "Simple"] and profiles["Simple"].show_on_menu
    assert profiles["Other"].color == "#123abc"
    assert headfoot.delete_profile("Other") and not headfoot.delete_profile("Other")
    with pytest.raises(LabelError):
        headfoot.save_profile(HeaderFooter(footer_center="x"))  # (no name)
    headfoot.profiles_path().write_text("not json", encoding="utf-8")
    assert headfoot.read_profiles() == {}


# =========================================================================== the command line


@needs_pdftotext
def test_command(book, capsys):
    assert main(["header-footer", str(book), "--footer-center", "p. $pagelabel", "--header-right", "$totalpages",
                 "--pages", "9-", "--odd", "--font", "courier", "--bold", "-i"]) == 0
    out = capsys.readouterr().out
    assert "page 9:" in out and "Footer center: p. 1" in out and "on 46 pages" in out
    assert text_of(book, 11) == "100 11 p. 3"
    assert main(["show", str(book)]) == 0
    assert "header and footer, on 46 pages: 9,11,13" in capsys.readouterr().out
    assert main(["header-footer", str(book), "--remove", "-i"]) == 0
    with pikepdf.open(book) as pdf:
        assert headfoot.pages_with(pdf) == []


def test_command_profiles_and_dry_run(book, capsys):
    assert main(["header-footer", "--footer-right", "$bates", "--bates-prefix", "X", "--bates-digits", "3",
                 "--save-profile", "Bates", "--show-on-menu"]) == 0
    assert main(["header-footer", "--list-profiles"]) == 0
    assert "* Bates" in capsys.readouterr().out
    assert main(["header-footer", str(book), "--profile", "Bates", "--bates-start", "10", "-n"]) == 0
    out = capsys.readouterr().out
    assert "Footer right: X010" in out and "Footer right: X109" in out
    with pikepdf.open(book) as pdf:
        assert headfoot.pages_with(pdf) == []  # (a dry run)
    assert main(["header-footer", str(book), "--profile", "Nope", "-n"]) == 1
    assert main(["header-footer", str(book), "--header-left", "Ελλάς", "-n"]) == 1
    assert "cannot write" in capsys.readouterr().err
    assert main(["header-footer", "--delete-profile", "Bates"]) == 0
    assert headfoot.read_profiles() == {}
