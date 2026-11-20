"""Tests of arranging pages (arrange.py, files.apply_all with operations, 'py-pdftools pages' and the
window)."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pikepdf
import pytest

from py_pdftools.core import config, interface

from py_pdftools.pages import arrange, files, headfoot, labels, stamps

from foliation_argv import main
from py_pdftools.pages.changes import Change
from py_pdftools.pages.labels import LabelError, Range

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "docs" / "example" / "numbers-100.pdf"
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
        labels.write_labels(pdf, [Range(1, "r"), Range(9, "D"), Range(91, "A")])
        pdf.save(path)
    return path


def numbers(path: Path) -> list[int]:
    """The number printed on each page (the example's pages show theirs)."""
    out = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, check=True).stdout
    return [int(page.split()[0]) for page in out.split("\f") if page.strip()]


def labels_of(path: Path) -> list[str]:
    with pikepdf.open(path) as pdf:
        return labels.page_labels(labels.read_labels(pdf), len(pdf.pages))


# =========================================================================== the operations


def test_page_lists_and_orders():
    assert arrange.parse_page_list("9-12,3", 20) == [3, 9, 10, 11, 12]
    assert arrange.parse_page_list("1-6,odd", 20) == [1, 3, 5] and arrange.parse_page_list("even", 6) == [2, 4, 6]
    assert arrange.parse_page_list("all", 3) == [1, 2, 3] and arrange.parse_page_list("LAST", 7) == [7]
    assert arrange.parse_order("3-1,5,5", 5) == [3, 2, 1, 5, 5]
    assert arrange.parse_where("start", 9) == 1 and arrange.parse_where("end", 9) == 10
    with pytest.raises(LabelError):
        arrange.parse_page_list("30", 20)


def test_what_the_operations_do():
    n = 6
    assert arrange.Move((5, 6), 2).items(n) == [1, 5, 6, 2, 3, 4]
    assert arrange.Move((1,), 7).items(n) == [2, 3, 4, 5, 6, 1]
    assert arrange.Delete((2, 4)).items(n) == [1, 3, 5, 6]
    assert arrange.Duplicate((2,)).items(n) == [1, 2, 2, 3, 4, 5, 6]
    assert arrange.Duplicate((2, 3), 1).items(n) == [2, 3, 1, 2, 3, 4, 5, 6]
    assert arrange.Reverse().items(n) == [6, 5, 4, 3, 2, 1]
    assert arrange.Reverse((2, 4, 6)).items(n) == [1, 6, 3, 4, 5, 2]
    assert arrange.Order((3, 3, 1)).items(n) == [3, 3, 1]
    inserted = arrange.Insert(str(EXAMPLE), (1, 2), 3).items(n)
    assert inserted[:2] == [1, 2] and inserted[2] == arrange.Inserted(str(EXAMPLE), 1) and inserted[4:] == [3, 4, 5, 6]
    with pytest.raises(LabelError, match="one page at least"):
        arrange.Delete(tuple(range(1, 7))).items(n)


def test_labels_follow_or_stay():
    ranges = [Range(1, "r"), Range(3, "D")]  # i ii 1 2 3 4
    move = arrange.Move((5, 6), 1)
    assert labels.page_labels(arrange.ranges_after(move, ranges, 6), 6) == ["3", "4", "i", "ii", "1", "2"]
    stay = arrange.Move((5, 6), 1, labels=arrange.POSITION)
    assert arrange.ranges_after(stay, ranges, 6) == ranges
    assert arrange.ranges_after(move, [], 6) == []  # (no labels: none)
    assert arrange.position_after(move, 1, 6) == 3 and arrange.position_after(arrange.Delete((1,)), 1, 6) is None


@needs_pdftotext
def test_pages_bookmarks_and_links_follow(book, tmp_path):
    with pikepdf.open(book) as pdf:
        with pdf.open_outline() as outline:
            outline.root.extend([pikepdf.OutlineItem("five", 4), pikepdf.OutlineItem("fifty", 49)])
        link = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Annot, Subtype=pikepdf.Name.Link,
                                                    Rect=[0, 0, 10, 10], Dest=[pdf.pages[4].obj, pikepdf.Name.Fit]))
        pdf.pages[0].obj.Annots = pikepdf.Array([link])
        for op in (arrange.Move((50,), 1), arrange.Delete((6,)), arrange.Duplicate((2,)), arrange.Rotate((3,), -90)):
            op.apply(pdf)
        pdf.save(tmp_path / "out.pdf")
    assert numbers(tmp_path / "out.pdf")[:6] == [50, 1, 1, 2, 3, 4]
    with pikepdf.open(tmp_path / "out.pdf") as pdf:
        at = {p.obj.objgen: i + 1 for i, p in enumerate(pdf.pages)}
        with pdf.open_outline() as outline:  # (five was deleted: its bookmark goes to the page after it, 6)
            assert [(i.title, at[i.destination[0].objgen]) for i in outline.root] == [("five", 7), ("fifty", 1)]
        assert int(pdf.pages[2].obj.Rotate) == 270  # (the copy, at 3: its original is not turned)
        assert int(pdf.pages[1].obj.get("/Rotate", 0)) == 0
        original, twin = pdf.pages[1].obj, pdf.pages[2].obj  # (the copy has links of its own)
        assert original.Annots[0].objgen != twin.Annots[0].objgen and twin.Annots[0].P.objgen == twin.objgen
        assert at[original.Annots[0].Dest[0].objgen] == 7  # (to the page after the one deleted)


@needs_pdftotext
def test_insert_and_replace(book, tmp_path):
    with pikepdf.open(book) as pdf:
        link = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Annot, Subtype=pikepdf.Name.Link,
                                                    Rect=[0, 0, 10, 10]))
        pdf.pages[1].obj.Annots = pikepdf.Array([link])
        arrange.Insert(str(EXAMPLE), (70, 71), 3).apply(pdf)
        arrange.Replace((2,), str(EXAMPLE), 99).apply(pdf)
        assert len(pdf.pages[1].obj.Annots) == 1  # (the page keeps its link)
        pdf.save(tmp_path / "out.pdf")
    assert numbers(tmp_path / "out.pdf")[:5] == [1, 99, 70, 71, 3]


def test_apply_all_with_operations_and_a_header(book, tmp_path):
    """A header added before pages move sees the labels the pages had then."""
    ranges = [Range(1, "r"), Range(9, "D"), Range(91, "A")]
    move = arrange.Move(tuple(range(91, 101)), 1)
    after = arrange.ranges_after(move, ranges, 100)
    changes = (Change(headfoot.HeaderFooter(footer_center="L=$pagelabel", pages="91")), move,
               arrange.Delete((100,)))
    after = arrange.ranges_after(changes[2], after, 100)
    files.write_copy(book, after, tmp_path / "out.pdf", changes=changes)
    assert labels_of(tmp_path / "out.pdf")[:12] == ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "i", "ii"]
    with pikepdf.open(tmp_path / "out.pdf") as pdf:
        assert len(pdf.pages) == 99 and stamps.pages_with(pdf) == [1]
        assert b"(L=A)" in pdf.pages[0].obj.Contents[-1].read_bytes()


# =========================================================================== the command line


@needs_pdftotext
def test_pages_command(book, tmp_path, capsys):
    out = tmp_path / "out.pdf"
    assert main(["pages", str(book), "--move", "91-100", "9", "--delete", "LAST", "--rotate", "even", "90",
                 "-o", str(out)]) == 0
    assert "Wrote" in capsys.readouterr().out and len(labels_of(out)) == 99
    assert labels_of(out)[7:10] == ["viii", "A", "B"] and numbers(out)[8] == 91
    assert main(["pages", str(book), "--order", "10-1", "--labels", "position", "-o", str(out)]) == 0
    assert numbers(out) == list(range(10, 0, -1)) and labels_of(out)[:2] == ["i", "ii"]
    assert main(["pages", str(book), "--insert", str(EXAMPLE), "start", "1-2", "--extract", "1-4",
                 "-o", str(out)]) == 0
    assert numbers(out) == [1, 2, 1, 2] and labels_of(out) == ["1", "2", "i", "ii"]
    assert main(["pages", str(book), "--split-every", "40", "--output-dir", str(tmp_path / "parts")]) == 0
    assert sorted(p.name for p in (tmp_path / "parts").iterdir()) == ["book-1.pdf", "book-2.pdf", "book-3.pdf"]
    assert labels_of(tmp_path / "parts" / "book-3.pdf")[0] == "73"
    capsys.readouterr()
    for bad in (["--delete", "all"], ["--rotate", "1", "45"], [], ["--move", "1"]):
        try:
            code = main(["pages", str(book), *bad, "-n"])
        except SystemExit as e:  # (argparse: a value missing)
            code = e.code
        assert code != 0, bad


# =========================================================================== the window


@pytest.mark.skipif(importlib.util.find_spec("PySide6") is None, reason="needs PySide6")
def test_window(book, tmp_path, monkeypatch):
    """The pages arranged in the mode Pages of the window: moved, their labels following them (as the
    user says), deleted, undone, dropped on the list, saved, and some saved as a new file."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QMimeData, QPointF, Qt
    from PySide6.QtGui import QDropEvent
    from PySide6.QtWidgets import QApplication

    from py_pdftools.gui import paging
    from py_pdftools.gui.window import MainWindow
    app = QApplication.instance() or QApplication(sys.argv[:1])
    monkeypatch.setenv("HOME", str(tmp_path))
    w = MainWindow()
    w.ask_recover = lambda when: False
    asked = []
    monkeypatch.setattr(paging, "ask_labels", lambda parent: (asked.append(1), (arrange.FOLLOW, False))[1])
    w.set_labels_rule("ask")
    assert w.open_path(book)
    w.set_mode("pages")
    assert w.set_view_part("page", 95)
    assert w.move_pages(list(range(91, 101)), 9) and asked == [1]
    assert w.count == 100 and [w.page_labels()[i - 1] for i in (9, 19)] == ["A", "1"]
    assert w.pages_state().opening.page == 13
    w.set_labels_rule(arrange.POSITION)  # (not asked: as Pages ▸ Labels says)
    assert w.arrange_pages(arrange.Delete((1,))) and asked == [1] and w.count == 99 and w.page_labels()[0] == "i"
    w.undo()
    assert w.count == 100
    # a drop on the list: the pages chosen go where they are dropped
    pl = w.page_list
    pl.clearSelection()
    pl.item(0).setSelected(True)
    rect = pl.visualItemRect(pl.item(4))
    dropped = []
    pl.moved.disconnect()
    pl.moved.connect(lambda pages, before, copied: dropped.append((pages, before, copied)))
    mime = QMimeData()  # (kept: the event holds no reference to it)
    event = QDropEvent(QPointF(rect.center().x(), rect.top() + 1), Qt.DropAction.MoveAction, mime,
                       Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier)
    pl.dropEvent(event)
    assert dropped == []  # (the move waits for the drag to be over)
    QApplication.processEvents()
    assert dropped == [([1], 5, True)]
    menu = w.build_pages_menu()
    assert "Move to the end" in [a.text() for a in menu.actions()]
    assert w.save() and w.count == 100 and labels_of(book)[8] == "A" and w.work is None
    assert w.write_parts([(tmp_path / "part.pdf", [9, 10])]) and labels_of(tmp_path / "part.pdf") == ["A", "B"]
    w.close()
    app.processEvents()


def test_blank_pages(book, tmp_path, capsys):
    with pikepdf.open(book) as pdf:
        pdf.pages[4].obj.MediaBox = pikepdf.Array([0, 0, 300, 400])
        pdf.pages[4].obj.Rotate = 90
        pdf.pages[4].obj.TrimBox = pikepdf.Array([10, 10, 290, 390])
        assert arrange.InsertBlank(6, 2).items(10)[5:7] == [arrange.Blank(5), arrange.Blank(5)]
        arrange.InsertBlank(6, 2).apply(pdf)  # (after page 5: its size, turned as it is)
        arrange.InsertBlank(1).apply(pdf)  # (at the start: the first page's size)
        assert len(pdf.pages) == 103
        for i in (6, 7):
            page = pdf.pages[i].obj
            assert list(page.MediaBox) == [0, 0, 300, 400] and int(page.Rotate) == 90
            assert list(page.TrimBox) == [10, 10, 290, 390] and page.Contents.read_bytes() == b""
        assert list(pdf.pages[0].obj.MediaBox) == [0, 0, 612, 792] and pdf.pages[0].obj.Contents.read_bytes() == b""
    assert arrange.labels_after(arrange.InsertBlank(2, 2), ["i", "ii", "1"], 3) == ["i", "", "", "ii", "1"]
    assert main(["pages", str(book), "--insert-blank", "9", "2", "-o", str(tmp_path / "out.pdf")]) == 0
    assert labels_of(tmp_path / "out.pdf")[7:11] == ["viii", "", "", "1"]
    assert main(["pages", str(book), "--insert-blank", "9", "two", "-n"]) == 1


def test_rebuild_keeps_and_changes_the_right_pages(book, tmp_path):
    """Each page of the result is the page it should be (only the pages that change are taken out
    and put in, the others are left where they are)."""
    def contents(path):
        with pikepdf.open(path) as pdf:
            return [page.obj.Contents.read_bytes() if "/Contents" in page.obj else b"" for page in pdf.pages]

    original = contents(book)
    n = len(original)
    other = tmp_path / "other.pdf"
    shutil.copy(book, other)
    for op in (arrange.Delete((7,)), arrange.Delete((1, 2, n)), arrange.Move((2,), 10), arrange.Move((n,), 1),
               arrange.Move((3, 4), n + 1), arrange.Duplicate((5, 6)), arrange.Duplicate((1,), n + 1),
               arrange.Reverse((10, 11, 12, 13)), arrange.Reverse(tuple(range(1, n + 1))),
               arrange.Insert(str(other), (2, 3), 50), arrange.InsertBlank(1), arrange.InsertBlank(n + 1),
               arrange.Order(tuple([2, 1] + list(range(3, n + 1))))):
        out = tmp_path / "out.pdf"
        files.write_copy(book, [], out, "", None, (op,))
        got = contents(out)
        items = op.items(n)
        assert len(got) == len(items), op
        for i, item in enumerate(items):
            if isinstance(item, int):
                assert got[i] == original[item - 1], (op, i)
            elif isinstance(item, arrange.Inserted):
                assert got[i] == original[item.page - 1], (op, i)
            else:
                assert got[i] == b"", (op, i)
